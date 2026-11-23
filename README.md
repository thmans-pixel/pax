# pax

Jeu de gestion du monde au tour par tour, en Python, dont le moteur narratif est un modèle
local servi par Ollama. On choisit un scénario (monde actuel, Seconde Guerre mondiale…),
on prend la tête d'une nation, on écrit ses décisions, et l'IA fait vivre le reste du monde.

Titre de travail : « pax » (nom définitif à choisir, différent de « Pax Historia », qui est
une marque).

## État

Jouable : scénarios, carte, tours joués par l'IA (ordres, journal, corrections, annulation),
rapport de situation, conseiller, diplomatie. Spec : `docs/specs/001-jeu-de-gestion-du-monde.md`.

## Installer sur un serveur YunoHost 12

YunoHost refuse une adresse GitHub de branche : on installe depuis un clone local.

```
git clone https://github.com/thmans-pixel/pax.git ~/pax
sudo yunohost app install ~/pax
```

Questions : domaine, chemin (`/` pour un domaine dédié, sinon `/pax`), groupe d'accès
(laisser `admins` au début), administrateur du jeu (accès aux Réglages), adresse d'Ollama
(modifiable ensuite dans Réglages).

Donner l'accès à un autre compte : `sudo yunohost user permission add pax.main <compte>`.

Mettre à jour :

```
cd ~/pax && git pull
sudo yunohost app upgrade pax -u ~/pax
```

Vérifier l'identification : ouvrir `<adresse du jeu>/moi`, qui doit afficher votre compte.

## Brancher l'IA (Ollama sur un autre PC du réseau)

1. Sur le PC, Ollama doit écouter le réseau : `Environment=OLLAMA_HOST=0.0.0.0:11434` dans son
   service systemd, puis redémarrer le service. Le pare-feu du PC doit laisser passer le port
   11434 depuis le serveur (idéalement depuis lui seul).
2. Depuis le serveur, vérifier : `curl -s -m 5 http://<ip du PC>:11434/api/tags`.
3. Dans le jeu, page **Réglages** : adresse `http://<ip du PC>:11434`, **Tester la connexion**,
   choisir le modèle, **Enregistrer**. Le badge en haut à droite passe à « IA prête ».

Avec 16 Go de mémoire graphique : un modèle de 12 à 14 milliards de paramètres et un contexte de
16 384 jetons. Le Journal indique, pour chaque tour, sa durée et le modèle utilisé.

## Essai local et tests

`./lancer.sh` puis http://127.0.0.1:8800 (identité fixe `dev`, sans YunoHost).
Tests : `pip install -r requirements-dev.txt && python -m pytest tests` (un faux Ollama, sans réseau).

## Demande d'origine (22/11/2026)

- jeu de plateau de gestion du monde, tour par tour, dans l'esprit de Pax Historia ;
- en Python, avec Ollama ;
- plusieurs scénarios chargeables (monde actuel, Seconde Guerre mondiale, etc.) ;
- on choisit une nation ;
- des aides de l'IA, comme l'état actuel de la partie.

## Inspiration

Le projet libre [Open Historia](https://github.com/Open-Historia/open-historia) sert de
référence pour les idées. Voir [docs/etude-open-historia.md](docs/etude-open-historia.md).
Aucun code, aucun texte de consigne et aucun fichier de scénario n'en est copié.

## Sécurité à connaître

Le jeu fait confiance à l'en-tête `Authorization` posé par SSOwat (YunoHost 12) : **ne donnez jamais la permission
du jeu au groupe « visiteurs »**, et ne l'exposez pas sans SSOwat. Il n'écoute que sur 127.0.0.1.
