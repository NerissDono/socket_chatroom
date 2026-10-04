"""Serveur de chat TCP privé et de groupe.

Le protocole utilisé est constitué d'un objet JSON par ligne (UTF-8).
Cette délimitation permet à ``recv`` de traiter plusieurs messages reçus
en une seule fois, ou un message reçu en plusieurs fragments.
"""

from __future__ import annotations

import json
import socket
import threading
from typing import Any

HOST = "0.0.0.0"
PORT = 5050
DISCOVERY_PORT = 5051
DISCOVERY_MESSAGE = b"CHAT_DISCOVERY_V1"
BUFFER_SIZE = 4096

# Ces dictionnaires sont partagés par les threads clients.
clients: dict[str, socket.socket] = {}
groups: dict[str, set[str]] = {}
state_lock = threading.Lock()


def discovery_responder() -> None:
    """Répond aux recherches UDP des clients présents sur le réseau local."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as discovery_socket:
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        discovery_socket.bind((HOST, DISCOVERY_PORT))
        while True:
            message, address = discovery_socket.recvfrom(1024)
            if message != DISCOVERY_MESSAGE:
                continue
            response = json.dumps(
                {"type": "chat_server", "port": PORT}
            ).encode("utf-8")
            discovery_socket.sendto(response, address)


def send_json(connection: socket.socket, payload: dict[str, Any]) -> None:
    """Sérialise et envoie un payload JSON terminé par un saut de ligne."""
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    connection.sendall(data)


def send_error(connection: socket.socket, message: str) -> None:
    """Retourne une erreur structurée au client qui a envoyé la requête."""
    try:
        send_json(connection, {"type": "error", "content": message})
    except OSError:
        # La connexion est déjà fermée : le nettoyage du thread s'en chargera.
        pass


def broadcast_to_group(
    group_name: str, payload: dict[str, Any], excluded_user: str | None = None
) -> None:
    """Diffuse un payload aux membres connectés d'un groupe."""
    with state_lock:
        member_names = tuple(groups.get(group_name, set()))
        recipients = [
            clients[name]
            for name in member_names
            if name != excluded_user and name in clients
        ]

    for recipient in recipients:
        try:
            send_json(recipient, payload)
        except OSError:
            # Le thread propriétaire supprimera bientôt cette connexion.
            continue


def handle_message(
    connection: socket.socket, username: str, payload: dict[str, Any]
) -> None:
    """Traite une commande reçue après l'enregistrement de l'utilisateur."""
    message_type = payload.get("type")

    if message_type == "private":
        target = payload.get("target")
        content = payload.get("content")
        if not isinstance(target, str) or not isinstance(content, str) or not content:
            send_error(connection, "Un message privé doit contenir target et content.")
            return

        with state_lock:
            recipient = clients.get(target)
        if recipient is None:
            send_error(connection, f"L'utilisateur « {target} » n'est pas connecté.")
            return

        try:
            send_json(
                recipient,
                {
                    "type": "private",
                    "sender": username,
                    "target": target,
                    "content": content,
                },
            )
        except OSError:
            send_error(connection, f"Impossible de joindre « {target} ».")
        return

    if message_type == "join":
        group_name = payload.get("target")
        if not isinstance(group_name, str) or not group_name.strip():
            send_error(connection, "Le nom du groupe est obligatoire.")
            return
        group_name = group_name.strip()

        with state_lock:
            groups.setdefault(group_name, set()).add(username)

        send_json(
            connection,
            {"type": "system", "content": f"Vous avez rejoint le groupe « {group_name} »."},
        )
        broadcast_to_group(
            group_name,
            {
                "type": "group",
                "sender": "serveur",
                "target": group_name,
                "content": f"{username} a rejoint le groupe.",
            },
            excluded_user=username,
        )
        return

    if message_type == "group":
        group_name = payload.get("target")
        content = payload.get("content")
        if not isinstance(group_name, str) or not isinstance(content, str) or not content:
            send_error(connection, "Un message de groupe doit contenir target et content.")
            return

        with state_lock:
            is_member = username in groups.get(group_name, set())
        if not is_member:
            send_error(connection, f"Rejoignez d'abord le groupe « {group_name} ».")
            return

        broadcast_to_group(
            group_name,
            {
                "type": "group",
                "sender": username,
                "target": group_name,
                "content": content,
            },
        )
        return

    if message_type == "list_users":
        with state_lock:
            user_names = sorted(clients)
        send_json(connection, {"type": "users", "users": user_names})
        return

    send_error(connection, "Type de message inconnu.")


def register_client(connection: socket.socket, payload: dict[str, Any]) -> str | None:
    """Enregistre un pseudo unique et confirme l'inscription au client."""
    username = payload.get("sender")
    if not isinstance(username, str):
        send_error(connection, "Le pseudo doit être une chaîne de caractères.")
        return None
    username = username.strip()
    if not username or len(username) > 32 or any(char.isspace() for char in username):
        send_error(connection, "Le pseudo doit contenir 1 à 32 caractères sans espace.")
        return None

    with state_lock:
        if username in clients:
            send_error(connection, "Ce pseudo est déjà utilisé.")
            return None
        clients[username] = connection

    send_json(connection, {"type": "system", "content": f"Bienvenue, {username}."})
    print(f"[+] {username} connecté.")
    return username


def remove_client(username: str | None, connection: socket.socket) -> None:
    """Retire un client de tous les groupes et ferme son socket."""
    if username is not None:
        with state_lock:
            if clients.get(username) is connection:
                del clients[username]
            for group_members in groups.values():
                group_members.discard(username)
            empty_groups = [name for name, members in groups.items() if not members]
            for name in empty_groups:
                del groups[name]
        print(f"[-] {username} déconnecté.")

    try:
        connection.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    connection.close()


def client_thread(connection: socket.socket, address: tuple[str, int]) -> None:
    """Gère la durée de vie d'un client dans un thread dédié."""
    username: str | None = None
    buffer = b""
    try:
        while username is None:
            data = connection.recv(BUFFER_SIZE)
            if not data:
                return
            buffer += data
            if b"\n" not in buffer:
                continue
            raw_line, buffer = buffer.split(b"\n", 1)
            try:
                payload = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                send_error(connection, "Le message doit être un JSON UTF-8 valide.")
                return
            if not isinstance(payload, dict) or payload.get("type") != "register":
                send_error(connection, "Le premier message doit être une inscription.")
                return
            username = register_client(connection, payload)

        while True:
            data = connection.recv(BUFFER_SIZE)
            if not data:
                break
            buffer += data
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                if not raw_line.strip():
                    continue
                try:
                    payload = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    send_error(connection, "Le message doit être un JSON UTF-8 valide.")
                    continue
                if isinstance(payload, dict):
                    handle_message(connection, username, payload)
                else:
                    send_error(connection, "Le payload JSON doit être un objet.")
    except (ConnectionError, OSError) as error:
        print(f"[!] Connexion interrompue avec {address}: {error}")
    finally:
        remove_client(username, connection)


def main() -> None:
    """Crée le socket d'écoute puis accepte les clients en parallèle."""
    threading.Thread(target=discovery_responder, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()
        print(f"Serveur en écoute sur {HOST}:{PORT}")

        while True:
            connection, address = server.accept()
            thread = threading.Thread(
                target=client_thread, args=(connection, address), daemon=True
            )
            thread.start()


if __name__ == "__main__":
    main()
