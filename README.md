# pax

Jeu de gestion du monde au tour par tour, en Python, dont le moteur narratif est un modèle
local servi par Ollama. On choisit un scénario (monde actuel, Seconde Guerre mondiale…),
on prend la tête d'une nation, on écrit ses décisions, et l'IA fait vivre le reste du monde.

Titre de travail : « pax » (nom définitif à choisir, différent de « Pax Historia », qui est
une marque).

## État

Étape 1 de la spec 001 faite : scénarios, carte, choix de la nation, parties enregistrées, Réglages.
L'IA ne joue pas encore (étapes 2 à 4, voir `docs/specs/`).

Essai local : `./lancer.sh` puis http://127.0.0.1:8800 — tests : `pip install -r requirements-dev.txt && python -m pytest tests`.

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

Le jeu fait confiance à l'en-tête `Remote-User` posé par YunoHost : **ne donnez jamais la permission
du jeu au groupe « visiteurs »**, et ne l'exposez pas sans SSOwat. Il n'écoute que sur 127.0.0.1.
