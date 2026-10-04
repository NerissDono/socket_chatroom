# Application de chat TCP

Cette application est un chat client-serveur développé en Python avec des
sockets TCP et le module `threading`. Elle permet à plusieurs utilisateurs de
communiquer en messages privés ou dans des groupes.

## Fonctionnement général

- Un seul ordinateur du réseau local lance `serveur.py`.
- Chaque utilisateur lance ensuite `client.py` sur son ordinateur.
- Les clients recherchent automatiquement le serveur sur le réseau local :
  aucune adresse IP locale n'est à saisir dans le code.
- La communication des messages utilise TCP sur le port `5050`.
- La découverte automatique du serveur utilise UDP sur le port `5051`.
- Les échanges de données sont structurés en JSON encodé en UTF-8.

Le serveur doit rester lancé pendant toute la durée de l'utilisation de
l'application.

## Installation

Python 3.10 ou une version plus récente est recommandée. Aucun paquet externe
n'est nécessaire : l'application utilise uniquement la bibliothèque standard
Python.

Placez les fichiers suivants dans le même dossier :

- `serveur.py`
- `client.py`

## Lancement

### 1. Lancer le serveur

Sur une machine choisie comme serveur :

```bash
python serveur.py
```

Le serveur doit afficher qu'il écoute sur le port `5050`.

### 2. Lancer les clients

Sur chaque machine participante :

```bash
python client.py
```

Chaque utilisateur choisit ensuite un pseudo unique. Le client recherche
automatiquement le serveur disponible sur le réseau local.

## Commandes disponibles

```text
/msg <utilisateur> <message>
```

Envoie un message privé à un utilisateur connecté.

```text
/join <groupe>
```

Rejoint un groupe. Le groupe est créé automatiquement s'il n'existe pas.

```text
/gmsg <groupe> <message>
```

Envoie un message à tous les membres du groupe.

```text
/users
```

Affiche la liste des utilisateurs connectés au serveur.

```text
/quit
```

Ferme le client.

## Ce qui est possible

- Connecter plusieurs clients au même serveur.
- Envoyer des messages privés entre deux utilisateurs.
- Créer et utiliser plusieurs groupes simultanément.
- Utiliser les discussions privées et les discussions de groupe en parallèle.
- Découvrir automatiquement le serveur lorsqu'il est présent sur le même
  réseau local.
- Gérer les déconnexions et supprimer automatiquement les utilisateurs
  déconnectés de la liste active.

## Limites réseau

La découverte automatique fonctionne uniquement sur un même réseau local ou
sur un réseau virtuel qui autorise les broadcasts UDP.

L'application ne fonctionne pas directement entre deux réseaux distants
différents, par exemple deux box Internet distinctes, sans configuration
réseau supplémentaire. Il faudrait alors notamment :

- utiliser l'adresse IP publique du réseau du serveur ;
- configurer une redirection du port TCP `5050` sur le routeur ;
- autoriser les ports TCP `5050` et UDP `5051` dans les pare-feux ;
- gérer les changements d'adresse IP publique ;
- vérifier que le fournisseur d'accès n'utilise pas de CGNAT.


## Pare-feu

Le pare-feu de la machine qui exécute `serveur.py` doit autoriser Python ou
les ports suivants :

- **TCP 5050** : connexion et messages du chat ;
- **UDP 5051** : découverte automatique du serveur.

Les machines doivent également être sur le même réseau local et ne pas être
isolées par le point d'accès Wi-Fi. Certains réseaux invités bloquent les
communications entre appareils.

## Architecture simplifiée

```text
Client A ─┐
Client B ─┼── TCP 5050 ──> Serveur
Client C ─┘

Clients ── UDP broadcast 5051 ──> Découverte automatique du serveur
```

Le serveur utilise un thread distinct pour chaque client connecté. Les
messages sont ensuite routés selon leur type : privé, groupe ou commande
système.
