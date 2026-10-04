"""Client de chat TCP privé et de groupe."""

from __future__ import annotations

import json
import socket
import threading
from typing import Any

SERVER_PORT = 5050
DISCOVERY_PORT = 5051
DISCOVERY_MESSAGE = b"CHAT_DISCOVERY_V1"
DISCOVERY_TIMEOUT = 2.0
BUFFER_SIZE = 4096


def send_json(connection: socket.socket, payload: dict[str, Any]) -> None:
    """Sérialise un payload et l'envoie au format JSON Lines."""
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    connection.sendall(data)


def discover_server() -> tuple[str, int] | None:
    """Recherche automatiquement un serveur Chat sur le réseau local."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as discovery_socket:
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        discovery_socket.settimeout(DISCOVERY_TIMEOUT)
        discovery_socket.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", DISCOVERY_PORT))
        try:
            response, address = discovery_socket.recvfrom(1024)
            payload = json.loads(response.decode("utf-8"))
            if payload.get("type") == "chat_server":
                return address[0], int(payload["port"])
        except (socket.timeout, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
    return None


def receive_messages(connection: socket.socket) -> None:
    """Thread de réception : affiche chaque message envoyé par le serveur."""
    buffer = b""
    try:
        while True:
            data = connection.recv(BUFFER_SIZE)
            if not data:
                print("\nConnexion au serveur fermée.")
                return
            buffer += data
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                if not raw_line.strip():
                    continue
                try:
                    payload = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    print("\nRéponse invalide reçue du serveur.")
                    continue

                message_type = payload.get("type") if isinstance(payload, dict) else None
                if message_type == "private":
                    print(f"\n[Privé] {payload['sender']}: {payload['content']}")
                elif message_type == "group":
                    print(
                        f"\n[{payload['target']}] {payload['sender']}: "
                        f"{payload['content']}"
                    )
                elif message_type in {"system", "error"}:
                    print(f"\n[{message_type}] {payload.get('content', '')}")
                elif message_type == "users":
                    users = ", ".join(payload.get("users", []))
                    print(f"\n[Utilisateurs connectés] {users or 'personne'}")
                else:
                    print(f"\n[Serveur] {payload}")
    except (ConnectionError, OSError):
        print("\nConnexion au serveur interrompue.")


def send_messages(connection: socket.socket, username: str) -> None:
    """Thread d'envoi : transforme les commandes CLI en payloads JSON."""
    print(
        "Commandes : /msg <utilisateur> <message>, /join <groupe>, "
        "/gmsg <groupe> <message>, /users, /quit"
    )
    while True:
        try:
            command = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            command = "/quit"

        if command == "/quit":
            return
        if not command:
            continue

        parts = command.split(maxsplit=2)
        try:
            if parts[0] == "/msg" and len(parts) == 3:
                payload = {
                    "type": "private",
                    "sender": username,
                    "target": parts[1],
                    "content": parts[2],
                }
            elif parts[0] == "/join" and len(parts) == 2:
                payload = {"type": "join", "sender": username, "target": parts[1]}
            elif parts[0] == "/gmsg" and len(parts) == 3:
                payload = {
                    "type": "group",
                    "sender": username,
                    "target": parts[1],
                    "content": parts[2],
                }
            elif parts[0] == "/users" and len(parts) == 1:
                payload = {"type": "list_users", "sender": username}
            else:
                print("Commande invalide. Consultez la liste des commandes.")
                continue
            send_json(connection, payload)
        except OSError:
            print("Impossible d'envoyer le message : connexion fermée.")
            return


def main() -> None:
    """Connecte le client, l'inscrit, puis démarre les deux threads."""
    username = input("Choisissez un pseudo : ").strip()
    if not username:
        print("Le pseudo ne peut pas être vide.")
        return

    print("Recherche automatique du serveur sur le réseau local...")
    server = discover_server()
    if server is None:
        print(
            "Aucun serveur trouvé. Vérifiez que serveur.py est lancé sur le même "
            "réseau local et que le pare-feu autorise UDP 5051 et TCP 5050."
        )
        return

    server_host, server_port = server
    print(f"Serveur trouvé : {server_host}:{server_port}")
    try:
        with socket.create_connection((server_host, server_port)) as connection:
            send_json(connection, {"type": "register", "sender": username})
            receiver = threading.Thread(
                target=receive_messages, args=(connection,), daemon=True
            )
            receiver.start()
            send_messages(connection, username)
    except ConnectionRefusedError:
        print(f"Serveur inaccessible sur {server_host}:{server_port}.")
    except OSError as error:
        print(f"Erreur réseau : {error}")


if __name__ == "__main__":
    main()
