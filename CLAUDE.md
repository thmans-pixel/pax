# pax — jeu de gestion du monde (clone de Pax Historia)

Python 3, Starlette + Jinja2 + uvicorn, Ollama du PC via urllib. Installé sur thnas comme appli YunoHost.
Spec : `docs/specs/001-jeu-de-gestion-du-monde.md` (suivre ses étapes, une PR par étape).

## Règles
- L'IA raconte et propose ; **Python tient l'état** (chiffres plafonnés, validés). Jamais l'inverse.
- Identité du joueur = en-tête `Authorization: Basic identifiant:-` posé par SSOwat (YunoHost 12),
  jamais un champ de formulaire. Ne PAS lire `Remote-User` : SSOwat ne l'écrase pas.
- Aucun code ni texte copié d'Open Historia (AGPL / CC BY) : idées seulement.
- Fond de carte : Natural Earth (domaine public), préparé par `outils/preparer_carte.py`.
- Tests : `python -m pytest tests` (client ASGI maison `tests/client.py`, faux Ollama `tests/faux_ollama.py`).
- Lancer en local : `./lancer.sh`.
- Le paquet YunoHost (`manifest.toml`, `scripts/`, `conf/`) ne peut pas être testé hors de thnas : le dire.

## Pièges
- Ids de scénario : minuscules/chiffres/tirets (pas d'underscore) ; `pays_xxx` est réservé aux nations mineures.
- Le chemin d'installation (`PAX_PREFIXE`) passe par `u()` dans les gabarits et `config.prefixe` dans les redirections.
