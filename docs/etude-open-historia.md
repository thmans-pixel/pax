# Étude d'Open Historia

Lecture du dépôt [Open-Historia/open-historia](https://github.com/Open-Historia/open-historia)
faite le 22/11/2026 (dernier commit lu : 13/11/2026). Fichiers lus : `README.md`,
`CONTEXT.md`, `docs/ai-overview.md`, `docs/ai-schemas.md`, `docs/world-state.md`,
`scripts/presets/wwii-1939.spec.mjs`, sommaire du `wiki/`.

Ce document sert à préparer le cahier des charges. Ce n'est pas une spec.

## Ce que c'est

Un jeu de grande stratégie sur carte du monde, qui se présente comme une alternative libre
à Pax Historia. Jouable dans le navigateur, en appli de bureau (Windows, macOS, Linux en
AppImage) et sur Android.

- Technique : JavaScript/TypeScript, Node 20+, Vite, Electron, Capacitor, OpenLayers.
- Taille : environ 1 700 commits ; `server/server.js` fait 2 400 lignes ; la doc de l'IA
  seule fait 3 600 lignes.
- IA : chaque joueur apporte sa clé (Gemini par défaut, OpenAI, Anthropic) ou un serveur
  local « OpenAI Compatible », dont Ollama (`http://localhost:11434/v1`).
- Scénarios : « Modern Day » livré d'origine ; 1939, 1200, 1650, Rome 117, âge du bronze
  sur leur Scenario Hub.

## Idées à reprendre

1. **Un tour = une requête.** Leur « saut dans le temps » tient en une seule requête à
   l'IA, pas une par nation. Indispensable avec un modèle local.
2. **L'IA propose, le code applique.** La réponse est un JSON conforme à un schéma. Le
   code la valide, retire seulement ce qui est faux, puis applique les changements à
   l'état du monde.
3. **Lecture tolérante pour les petits modèles.** Blocs `<think>` retirés, guillemets et
   virgules réparés, JSON repêché dans du texte, puis nouvelle demande ciblée
   (« réponds seulement avec le JSON corrigé »).
4. **Contexte économe.** Les puissances « en vue » (le joueur, ses voisins, les acteurs de
   l'intrigue) sont décrites en entier, les autres en une ligne. On signale ce qui a
   changé depuis le tour précédent.
5. **Histoire par paliers.** Tours récents détaillés, années plus anciennes résumées,
   et une liste de faits établis qui ne s'effacent jamais.
6. **Qui sait quoi.** Le narrateur voit tout ; un dirigeant ne voit que ce que son pays
   peut connaître, et ne lit pas les discussions où il n'était pas.
7. **Scénario = carte de départ + règles de simulation.** Dans leur 1939, la carte est
   celle du 1er septembre ; l'invasion soviétique du 17 septembre et les annexions de 1940
   sont écrites dans les règles, pas sur la carte. L'auteur règle aussi le rythme
   (nombre d'événements par période) et des règles prioritaires.
8. **Objectif permanent du joueur**, connu du conseiller et du narrateur, jamais des
   autres dirigeants.
9. **Conseiller avec les chiffres du pays** (fiche de statistiques, réputation,
   renseignement) et note de rattrapage quand le monde a avancé depuis sa dernière réponse.
10. **Points de restauration** (jusqu'à douze) pour annuler un tour.
11. **Console de maître du jeu** pour corriger le monde à la main ; ces corrections sont
    annoncées au tour suivant.
12. **Relations bilatérales** : une note chiffrée, un palier (allié, hostile…) et un
    résumé en une phrase par paire de pays.

## Ce qu'on laisse de côté

- l'éditeur de cartes vectoriel ;
- le hub communautaire de scénarios ;
- les troupes déplacées sur la carte et les combats positionnés ;
- les événements interactifs joués scène par scène ;
- le réseau social intégré (« Rostra ») ;
- les versions Android et bureau ;
- la liste de secours entre plusieurs fournisseurs d'IA (un seul moteur : Ollama).

## Mises en garde tirées de leur doc

- Un très petit modèle local donne un monde et un conseiller plus pauvres.
- Un modèle local peut être très lent : prévoir l'affichage de la progression et un délai
  d'attente long (eux : dix minutes de silence avant d'abandonner).
- La fenêtre de contexte du modèle doit être connue avant d'envoyer : ne pas envoyer ce
  qui ne rentre pas.

## Licences

- Code d'Open Historia : AGPL-3.0-or-later.
- Scénarios publiés : CC BY 4.0. Le fichier `wwii-1939.spec.mjs` du dépôt est, lui,
  marqué AGPL.

Conséquence retenue : on reprend les idées et on réécrit tout en Python. Si un jour on
copie du code, un texte de consigne ou un scénario, le jeu devra suivre la licence
correspondante (AGPL pour le code, attribution pour les scénarios).

## Points à trancher dans le cahier des charges

1. Interface : page web servie par Python avec carte cliquable, ou terminal.
2. Machine : PC Bazzite (Ollama sur la carte graphique) ou thnas.
3. Nombre de nations actives par tour et niveau de détail des autres.
4. Modèle Ollama visé et taille de contexte.
5. Format des fichiers de scénario.
