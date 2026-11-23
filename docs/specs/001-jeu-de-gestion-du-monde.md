---
numero: 001
titre: Jeu de gestion du monde au tour par tour avec Ollama
depot: autre (thmans-pixel/pax)
statut: en cours   # brouillon → validée → en cours → livrée
date: 2026-11-22
---

# 001 — Jeu de gestion du monde au tour par tour avec Ollama

## Le besoin, en une phrase
Thibault veut « un jeu de plateau de gestion du monde en tour par tour comme Pax Historia,
qui tourne avec Ollama, en Python » : on charge un scénario (monde actuel, Seconde Guerre
mondiale…), on choisit une nation, on écrit ses décisions, l'IA fait vivre le reste du monde,
et des aides de l'IA (état de la partie, conseiller) accompagnent le joueur.

## Ce que ça change pour qui
- Thibault : un jeu de stratégie installé sur thnas comme appli YunoHost, sans clé ni
  abonnement ; l'IA est l'Ollama de son PC, appelé par le réseau local. Rien ne part vers un
  service extérieur.
- Les adultes à qui Thibault donne l'accès dans YunoHost : chacun entre avec son compte
  et retrouve ses propres parties. Le jeu ne garde que l'identifiant YunoHost et les parties.
- Léo / Arthur : pas d'accès dans un premier temps (le jeu n'a aucun filtre de contenu).
- Tout le monde : l'IA ne marche que si le PC est allumé avec Ollama ; sinon on peut
  consulter ses parties, pas avancer.

## Hors périmètre
- Copier le code, les textes de consigne ou les scénarios d'Open Historia ou de Pax Historia
  (on reprend des idées, voir `docs/etude-open-historia.md`). Le nom « Pax Historia » n'est
  pas utilisé ; « pax » est un titre de travail.
- Éditeur de cartes ou de scénarios dans le jeu : un scénario s'écrit à la main dans un
  fichier YAML.
- Troupes placées et déplacées sur la carte, combats positionnés : les guerres se jouent
  par les ordres écrits et sont résolues par l'IA.
- Plusieurs joueurs dans une même partie. Comptes propres au jeu (on s'appuie sur YunoHost).
- Accès public sans compte YunoHost.
- Autres moteurs d'IA qu'Ollama (OpenAI, Claude, Mammouth…).
- Console de « maître du jeu » pour modifier le monde à la main (spec ultérieure possible).
- Événements interactifs scène par scène, réseau social, musique, versions mobile ou bureau.
- Filtre de contenu ou réglage de ton pour les enfants : le jeu est pour des adultes.
- Conditions de victoire : c'est un bac à sable. La seule fin est la disparition de la
  nation du joueur.

## Maquette de l'écran de partie

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ pax · Seconde Guerre mondiale · France   📅 15 octobre 1939 · tour 3   ↶ Annuler │
├──────────────────────────────────────────────┬────────────────────────────────┤
│                                              │ [Ordres] Journal Conseiller    │
│        CARTE DU MONDE (SVG)                  │  Diplomatie  État              │
│   territoires colorés selon leur nation      │ ┌────────────────────────────┐ │
│   survol : « Autriche — Allemagne »          │ │1. Mobiliser l'armée du Nord│ │
│   clic : fiche de la nation                  │ │2. Proposer une alliance    │ │
│   molette : zoom · glisser : déplacer        │ │   défensive à la Belgique  │ │
│                                              │ │+ ajouter un ordre          │ │
│                                              │ └────────────────────────────┘ │
│                                              │ Avancer de : (1 sem)(1 mois)   │
│                                              │   (3 mois)(6 mois)(1 an)       │
│                                              │ [ Avancer → 15 nov. 1939 ]     │
│                                              │ ▓▓▓▓▓░░░ l'IA écrit… 812 mots  │
├──────────────────────────────────────────────┴────────────────────────────────┤
│ Fiche : France · Daladier · IIIe République · Éco 62 Armée 58 Stab. 55 Infl. 70 │
└───────────────────────────────────────────────────────────────────────────────┘
```

Autres écrans : **Accueil** (parties sauvegardées : reprendre, supprimer ; nouvelle partie),
**Nouvelle partie** (liste des scénarios → carte → clic sur une nation → sa fiche → objectif
facultatif → Commencer), **Réglages** (adresse d'Ollama, modèle choisi dans la liste des
modèles installés, taille de contexte, bouton « Tester »).

## Critères d'acceptation
Chacun se vérifie par un test automatique ou par une manipulation précise.

**Socle**
1. [x] Quand on installe l'appli sur thnas (`yunohost app install` depuis le dépôt), alors
   elle répond à son adresse YunoHost ; à l'installation, aucun compte n'y a accès sauf
   celui de Thibault, les autres s'ajoutent un par un ; un visiteur sans compte autorisé est
   renvoyé vers la connexion YunoHost ; `./lancer.sh` la démarre aussi en local sur `localhost:8800` pour le
   développement. — *Vérification :* installation réelle sur thnas + manipulation.
2. [x] Quand Ollama répond, alors Réglages affiche « Connexion OK » et la liste des modèles
   installés ; quand il ne répond pas, alors un message dit quoi vérifier, la carte et les
   parties restent consultables et les boutons qui demandent l'IA sont grisés.
   — *Vérification :* test avec faux Ollama allumé puis éteint.
3. [x] Quand on ouvre « Nouvelle partie », alors les deux scénarios livrés apparaissent avec
   nom, date de départ et description. — *Vérification :* test.
4. [x] Quand un fichier de scénario est invalide (nation sans territoire, territoire inconnu,
   relation vers une nation inconnue, YAML cassé), alors il est écarté avec un message qui
   nomme le fichier et la faute, et les autres scénarios restent jouables.
   — *Vérification :* test avec trois fichiers fautifs.
5. [x] Quand on dépose un nouveau fichier YAML valide dans `scenarios/`, alors il apparaît
   au rechargement de la page, sans toucher au code. — *Vérification :* test.
6. [x] Sur la carte, chaque territoire a la couleur de sa nation ; au survol s'affichent le
   territoire et sa nation ; un clic ouvre la fiche de la nation ; la molette zoome et le
   glisser déplace. — *Vérification :* manipulation dans Brave sur le PC.
7. [x] Dans le scénario 1939 au départ, l'Autriche et la Tchéquie appartiennent à
   l'Allemagne, l'Inde au Royaume-Uni, l'Ukraine à l'URSS, et la Pologne est indépendante.
   — *Vérification :* test sur l'état chargé.
8. [x] Quand on choisit une nation et qu'on commence, alors la partie est enregistrée dans
   `data/parties/` ; après arrêt et relance du jeu, « Reprendre » rend exactement le même état.
   — *Vérification :* test (comparaison du JSON avant/après).
8 bis. [x] Chaque joueur ne voit, ne reprend et ne supprime que ses propres parties, d'après
   l'identifiant transmis par YunoHost ; une requête sans identifiant est refusée (sauf en
   mode développement local). — *Vérification :* test avec deux identifiants.

**Le tour**
9. [x] Quand on écrit de 1 à 10 ordres, qu'on choisit une durée et qu'on clique « Avancer »,
   alors le jeu envoie **une seule** requête à Ollama et la date avance exactement de la
   durée choisie (1 semaine = 7 jours, 1 mois = même jour du mois suivant).
   — *Vérification :* test (le faux Ollama compte les requêtes).
10. [x] Pendant le tour, la progression est visible (texte reçu, temps écoulé) ; le jeu
   n'abandonne pas tant qu'Ollama envoie quelque chose, et seulement après 10 minutes sans
   rien recevoir. — *Vérification :* test avec faux Ollama lent + manipulation.
11. [x] Quand la réponse est valide, alors les événements entrent dans le Journal, les
   chiffres, relations, guerres et territoires sont mis à jour, la carte est recolorée et
   chaque ordre affiche son issue (réussi, partiel, échec) avec une explication.
   — *Vérification :* test avec réponse enregistrée.
12. [x] Le code borne ce que l'IA propose : une variation de chiffre au-delà du plafond est
   ramenée au plafond ; un transfert de territoire entre deux pays qui ne sont ni en guerre ni
   liés par un traité ou une annexion décrits dans le tour est refusé ; un pays ou territoire
   inconnu est ignoré. Chaque correction apparaît dans un encart « Corrections » et est
   signalée à l'IA au tour suivant. — *Vérification :* tests, un par règle.
13. [x] Quand la réponse est mal formée (texte autour du JSON, bloc `<think>`, virgule en
   trop), alors elle est réparée ; si elle reste fausse, le jeu relance **une fois** en
   listant les fautes ; si ça échoue encore, le tour n'est pas appliqué, l'état est inchangé
   et les ordres restent dans la zone de saisie. — *Vérification :* tests.
14. [x] Quand on clique « Annuler » (le dernier tour), alors l'état redevient exactement celui
   d'avant et les ordres de ce tour reviennent dans la zone ; on peut remonter jusqu'à 10 tours.
   — *Vérification :* test (comparaison du JSON).
15. [x] La requête d'un tour ne dépasse jamais la taille de contexte moins 4 096 jetons
   réservés à la réponse ; pour tenir, on réduit d'abord les tours anciens à leur résumé puis
   on les retire, jamais les ordres, l'état du joueur ni les règles du scénario.
   — *Vérification :* test avec contexte réglé à 8 192 après 30 tours simulés.
16. [x] Un événement secret qui n'implique pas la nation du joueur n'apparaît ni dans son
   Journal, ni dans ce qui est envoyé au conseiller ou aux dirigeants ; le narrateur du tour,
   lui, le voit. — *Vérification :* test sur le contenu des requêtes.
16 bis. [x] Quand deux joueurs demandent l'IA en même temps, alors les demandes passent l'une
   après l'autre et celui qui attend voit « en attente, 1 demande avant vous ».
   — *Vérification :* test avec deux demandes simultanées.
16 ter. [x] Quand le PC est éteint ou qu'Ollama n'y répond pas, alors « Avancer » et les aides
   affichent « Le PC de l'IA ne répond pas » et rien n'est perdu.
   — *Vérification :* test avec faux Ollama éteint + essai réel PC éteint.
17. [x] Quand la nation du joueur n'a plus aucun territoire, alors un écran de fin de partie
   s'affiche, avec la possibilité d'annuler le dernier tour. — *Vérification :* test.

**Les aides de l'IA**
18. [x] L'onglet État affiche sans IA : date, tour, chiffres de la nation et leur évolution
   depuis le début, relations classées, guerres en cours, derniers événements.
   — *Vérification :* test du rendu.
19. [x] Le bouton « Rapport de situation » renvoie : la situation en quelques lignes, les
   menaces, les occasions et 3 suggestions d'ordres ; un clic sur une suggestion l'ajoute aux
   ordres. — *Vérification :* test (lecture de la réponse) + manipulation.
20. [x] Le Conseiller répond en français à partir de l'état de la nation, de ce qu'elle sait
   du monde et de l'objectif du joueur ; la conversation est gardée dans la sauvegarde.
   — *Vérification :* test du contenu envoyé + manipulation.
21. [x] En Diplomatie, on discute avec le dirigeant d'une nation ; il ne reçoit ni les
   échanges avec d'autres nations ni ceux du conseiller ; ce qui s'est dit depuis le dernier
   tour est transmis au narrateur du tour suivant (une promesse compte).
   — *Vérification :* test du contenu des requêtes.

**Ensemble**
22. [x] `pytest` passe sans Ollama (faux Ollama). — *Vérification :* lancer `pytest`.
23. [ ] Depuis thnas avec l'Ollama du PC, 5 tours d'un mois dans le scénario 1939 avec le modèle retenu : aucun
   tour perdu, durée de chaque tour notée dans la PR. — *Vérification :* partie réelle.

## Conception

**Principe : l'IA raconte et propose, Python tient les comptes.** L'état du monde (nations,
chiffres, relations, guerres, territoires) vit dans le code. À chaque tour, une seule requête
demande à l'IA un JSON de changements ; le code le vérifie, le borne, puis l'applique. C'est ce
qui rend le jeu tenable avec un modèle local de 16 Go de VRAM.

- **Ce qui existe déjà et qu'on réutilise :** rien dans le dépôt (vide hormis le README et
  l'étude). Idées reprises d'Open Historia, réécrites : un tour = une requête, réponse JSON
  validée puis appliquée, lecture tolérante, contexte économe (puissances « en vue » en entier,
  les autres en une ligne), histoire par paliers et faits établis, « qui sait quoi »,
  points de restauration, objectif permanent du joueur.

- **Technique :** Python 3.11+, FastAPI + uvicorn, gabarits Jinja2, httpx pour Ollama,
  PyYAML pour les scénarios. Page web en HTML + petit JavaScript sans bibliothèque (zoom de la
  carte, progression du tour). Pas de base de données : des fichiers JSON.

- **La carte :** contours des pays de Natural Earth au 1:110 millions (domaine public, environ
  175 territoires), dessinés en SVG par Python (projection simple). Un **territoire** = un pays
  actuel ; chaque territoire a une **nation propriétaire**. Ainsi 1939 se construit en donnant
  l'Autriche à l'Allemagne, l'Inde au Royaume-Uni, etc. Les écarts avec les vraies frontières de
  l'époque sont listés dans le fichier du scénario.

- **Un scénario** (`scenarios/*.yaml`) : nom, date de départ, description, contexte (texte
  pour l'IA), nations (nom, couleur, dirigeant, régime, chiffres, territoires, « majeure » oui
  ou non, jouable oui ou non), relations de départ, guerres en cours, règles de simulation
  (ce qui doit ou peut arriver et quand, ex. « 17/09/1939 : l'URSS envahit l'est de la Pologne
  sauf si… »), nations conseillées au joueur. Les territoires non attribués restent à leur
  pays actuel, nation mineure avec des chiffres par défaut. Deux scénarios livrés :
  **Monde actuel** (départ fin 2026, faits vérifiés sur le web à l'étape 1 et relus par
  Thibault) et **Seconde Guerre mondiale** (1er septembre 1939).

- **Une nation :** dirigeant, régime, quatre chiffres de 0 à 100 (économie, armée,
  stabilité, influence), territoires. Relation entre deux nations : note de −100 à +100 et
  palier (hostile, tendu, neutre, ami, allié), « en guerre » à part. Une nation sans territoire
  est « disparue » mais reste dans l'histoire. L'IA peut créer au plus une nouvelle nation par
  tour (indépendance, sécession), prise sur des territoires existants.

- **Plafonds par tour** (réglables dans le code) :

  | Durée du tour | Variation d'un chiffre | Variation d'une relation | Transferts de territoires |
  |---|---|---|---|
  | jusqu'à 1 mois | ±5 | ±20 | 3 |
  | jusqu'à 6 mois | ±10 | ±30 | 6 |
  | 1 an | ±15 | ±40 | 10 |

- **La réponse d'un tour** (JSON, clés en français, schéma passé à Ollama par son champ
  `format`) : événements (date, titre, texte, pays concernés, public ou secret), issue de
  chaque ordre, variations de chiffres avec raison, variations de relations, déclarations de
  guerre et paix, transferts de territoires avec leur base (guerre, traité, annexion,
  indépendance), nouvelle nation éventuelle, résumé du tour en un paragraphe, nouveaux faits
  établis. Lecture tolérante puis une relance ciblée au plus (critère 13).

- **Ce que voit le narrateur du tour :** consignes et schéma, contexte et règles du scénario
  utiles pour la période, date et durée, la nation du joueur en entier, les puissances « en
  vue » en entier (nations majeures du scénario, nations en guerre avec le joueur ou très
  liées à lui), les autres en une ligne, relations notables, guerres, faits établis, histoire
  (3 derniers tours détaillés, plus anciens en résumé), discussions diplomatiques depuis le
  dernier tour, objectif du joueur, ordres numérotés, corrections du tour précédent. Taille
  estimée avant envoi (critère 15). Tout en français.

- **Qui sait quoi :** le narrateur voit tout ; le joueur, le conseiller et le rapport de
  situation voient les événements publics et ceux qui impliquent la nation du joueur ; un
  dirigeant voit les événements publics, sa propre nation, sa relation avec le joueur et sa
  propre conversation avec lui (20 derniers messages).

- **Ollama :** `/api/chat` en flux (pour la progression), `format` = schéma JSON, taille de
  contexte réglable (16 384 par défaut), modèle choisi dans Réglages parmi ceux installés
  (`/api/tags`). Le modèle par défaut sera choisi à l'étape 2 en comparant 2 ou 3 modèles qui
  tiennent dans 16 Go sur une même partie ; le résultat est noté dans la PR.

- **Sauvegarde :** un fichier JSON par partie (`data/parties/<identifiant>/<id>.json`, avec un numéro de
  version du format), enregistré après chaque tour, avec les 10 derniers états pour
  « Annuler ».

- **Installation :** paquet YunoHost dans le dépôt (manifeste, scripts d'installation, de
  mise à jour, de sauvegarde et de restauration, service systemd, nginx), sur le modèle de
  Rick (`yunohost app install` / `upgrade` depuis un dossier). Accès réservé aux comptes
  YunoHost autorisés ; le jeu lit l'identifiant transmis par YunoHost et range les parties
  dans `data/parties/<identifiant>/`. Réglages (adresse d'Ollama, modèle, contexte) réservés
  aux administrateurs. `lancer.sh` reste pour le développement local.

- **L'IA à distance :** thnas appelle l'Ollama du PC Bazzite par le réseau local. Il faut
  que l'Ollama du PC écoute sur le réseau local et que le pare-feu du PC n'ouvre ce port
  qu'à thnas (réglage à faire une fois, guidé pas à pas à l'étape 1). Une seule demande à la
  fois vers Ollama : file d'attente dans le jeu.

- **Choix écartés :**
  - Une requête par nation à chaque tour : trop lent avec un modèle local (175 nations).
  - Laisser l'IA tenir seule l'état du monde en texte : un modèle local oublie et se contredit.
  - Carte avec Leaflet ou OpenLayers : bibliothèque lourde pour un simple coloriage de pays ;
    le SVG suffit.
  - Partir du code d'Open Historia : JavaScript, très gros, sous AGPL ; la demande est du Python.
  - Base SQLite : une partie tient dans un fichier JSON, plus simple à sauvegarder et lire.

## Fichiers touchés (prévision)
- `app/main.py` — serveur web, pages et routes
- `app/scenarios.py` — lecture et vérification des scénarios
- `app/monde.py` — état du monde, plafonds, application des changements
- `app/tour.py` — préparation du contexte, schéma, lecture de la réponse, corrections
- `app/aides.py` — conseiller, rapport de situation, diplomatie
- `app/ollama.py` — client Ollama (flux, délais, modèles)
- `app/carte.py` — dessin SVG de la carte
- `app/sauvegarde.py` — parties, états d'annulation
- `app/templates/`, `app/static/carte.js`, `app/static/style.css`
- `scenarios/monde-actuel.yaml`, `scenarios/seconde-guerre-1939.yaml`
- `donnees/pays-110m.geojson` — Natural Earth (domaine public)
- `tests/` — tests et faux Ollama avec réponses enregistrées
- `manifest.toml`, `scripts/`, `conf/` — paquet YunoHost
- `requirements.txt`, `lancer.sh`, `README.md`, `CLAUDE.md`

## Risques
- Enfants / ce qui part à une IA : rien ne sort de la maison (thnas → PC), aucune donnée
  personnelle dans les requêtes (ni nom ni identifiant du joueur). Le jeu est réservé aux
  adultes dans un premier temps et **n'a aucun filtre de contenu** : le scénario 1939 touche
  la guerre, les crimes de guerre et la Shoah. La seule protection est la permission
  YunoHost de l'appli, donnée compte par compte (pas au groupe « tous les utilisateurs »).
  Ouvrir le jeu à un enfant demandera une nouvelle spec, relue par `gardien-enfants`.
- Réseau : l'Ollama du PC devient joignable sur le réseau local ; port limité à thnas par
  le pare-feu. La carte graphique est partagée avec Rick et les jeux du PC : un tour peut
  attendre.
- thnas n'est pas stable : les parties entrent dans la sauvegarde YunoHost de l'appli.
- Justesse historique : un modèle local peut se tromper ou inventer ; c'est un jeu
  d'histoire alternative, pas un cours. Le scénario fixe les faits de départ.
- Monde actuel : les faits de fin 2026 sont postérieurs à ce que je sais de façon sûre ; ils
  seront cherchés sur le web à l'étape 1 et Thibault relira le fichier.
- Qualité et vitesse : avec 16 Go de VRAM, modèle d'environ 12 à 14 milliards de paramètres
  quantifié ; un contexte plus grand prend de la VRAM. Un tour peut prendre plusieurs minutes.
- Données : format de sauvegarde versionné dès le départ pour les évolutions futures.
- Licences : aucun code ni scénario d'Open Historia ; Natural Earth est dans le domaine public.

## Étapes
1. **Socle sans IA de jeu** (une PR) : format et vérification des scénarios, les deux
   scénarios, carte SVG, choix de la nation, sauvegarde et reprise par joueur, paquet
   YunoHost, Ollama du PC ouvert à thnas, Réglages avec test de connexion.
   Critères 1 à 8 bis, 18, 22.
2. **Le tour** (une PR) : ordres, durée, contexte, requête unique, lecture et corrections,
   journal, annulation, file d'attente, PC éteint, fin de partie, choix du modèle par défaut.
   Critères 9 à 17, 22.
3. **Les aides** (une PR) : rapport de situation, conseiller, diplomatie. Critères 19 à 21.
4. **Partie réelle et finitions** (une PR) : 5 tours en 1939 depuis thnas, réglage des
   consignes et des plafonds d'après la partie, README de lancement. Critère 23.

## Questions ouvertes
Aucune. Réponses de Thibault (22/11/2026) : page web avec carte ; jeu sur thnas, IA du PC ;
accès par les comptes YunoHost, adultes seulement pour commencer, sans filtre de contenu ;
durée des tours au choix du joueur.

## Livraison — étape 1 (socle)

**Fait** : format et vérification des scénarios (fautes cumulées, fichier fautif écarté), deux
scénarios livrés (Monde actuel au 22/11/2026 : 171 nations ; Seconde Guerre mondiale au
01/09/1939 : 69 nations), carte SVG cliquable, choix de la nation, sauvegarde/reprise par joueur,
Réglages avec test de connexion, statut de l'IA, paquet YunoHost, `lancer.sh`. 27 tests `pytest` verts
(sans Ollama, avec un faux Ollama). Critères cochés : 2, 3, 4, 5, 7, 8, 8 bis, 18, 22.

**Écart avec la spec** : Starlette + `urllib` au lieu de FastAPI + `httpx` (non installables dans
l'environnement de réalisation). Sans conséquence pour l'usage.

**À vérifier à la main (non testable ici)** :
- critère 1 : l'installation sur thnas (paquet YunoHost écrit mais jamais exécuté) ;
- critère 6 (partie JavaScript) : survol et clic sur la carte dans un vrai navigateur ;
- l'en-tête d'identification envoyé par YunoHost (ouvrir `/moi` après installation) ;
- ouverture d'Ollama du PC à thnas (`OLLAMA_HOST`, pare-feu).
- les faits du scénario « Monde actuel » : voir la liste `ecarts` du fichier (dirigeants non revérifiés).

Le bouton « Avancer » est volontairement désactivé jusqu'à l'étape 2.

## Livraison — étape 2 (le tour)

**Fait** : ordres (1 à 10) et durée (1 sem. / 1 mois / 3 mois / 6 mois / 1 an), requête unique vers
Ollama (`/api/chat` en flux, `format` = schéma JSON, `num_ctx`, délai de 10 min **sans rien recevoir**),
lecture tolérante (texte autour, `<think>`, virgule en trop) puis une seule relance listant les fautes,
application bornée par les plafonds de la spec avec encart « Corrections » (renvoyé à l'IA au tour
suivant), Journal, issue de chaque ordre, annulation (10 états dans la sauvegarde), écran de fin de
partie, file d'attente unique (« en attente, N demande(s) avant vous »), progression du tour (mots reçus,
temps écoulé), « Le PC de l'IA ne répond pas ». Critères cochés : 1 et 6 (vérifiés à la main sur thnas le
22/11/2026) et 9 à 17 (dont 16 bis et 16 ter) ; 22 reste vrai (73 tests `pytest`, sans Ollama).

**Choix de réalisation (écarts avec la spec)**
- Le tour tourne dans un **fil d'exécution** (`threading`) et la page l'interroge chaque seconde
  (`GET /partie/<id>/tour`) : plus simple et plus sûr derrière nginx qu'un flux SSE, et le tour continue
  si l'on ferme l'onglet. La page n'affiche que des **compteurs** (mots, secondes), jamais le texte reçu :
  il peut contenir des événements secrets.
- Plafonds : « 1 semaine » suit la ligne « jusqu'à 1 mois » ; « 3 mois » suit « jusqu'à 6 mois ».
- Transfert de territoire : « guerre » = les deux nations sont dans des camps opposés d'une guerre
  (existante ou déclarée dans la même réponse) ; « traité » et « annexion » = un événement du même tour
  cite les deux nations ; « indépendance » = vers la nouvelle nation du tour (une seule, créée seulement si
  elle reçoit un territoire).
- Si le contexte est trop petit, après avoir réduit l'histoire, on retire en dernier recours les nations
  « une ligne » sans lien avec le joueur ; si cela ne suffit pas, le tour n'est pas envoyé et le message
  demande d'augmenter la taille de contexte. Estimation : 1 jeton pour 3 caractères (prudent).
- Avant chaque tour, une sonde de 5 s (`/api/tags`) : un PC éteint ne fait pas attendre 10 minutes.

**Pour l'étape 3** : `histoire[].resume` et `faits_etablis` sont écrits par l'IA sans filtre de secret ;
ils ne devront être donnés qu'au narrateur (ou stockés avec un niveau de secret) quand le conseiller, le
rapport de situation et les dirigeants arriveront. Les corrections sont gardées en deux listes
(`corrections` pour l'IA, `corrections_joueur` filtrée pour l'encart).

**À vérifier à la main (non testable ici)**
- **Choix du modèle par défaut** (fin de l'étape 2 dans la spec) : comparer 2 ou 3 modèles tenant dans
  16 Go sur une même partie, avec le vrai Ollama, sur thnas. Aujourd'hui `qwen2.5:7b` est choisi.
  Noter durées et qualité dans la PR.
- Le JavaScript de la page de partie (onglets, ajout d'ordres, progression, bouton grisé) dans un vrai
  navigateur, derrière nginx (`proxy_buffering off` est déjà dans `conf/nginx.conf`).
- Un tour avec le vrai modèle : la qualité du JSON produit, le temps, la pertinence des corrections.
- Essai réel PC éteint (critère 16 ter) : message « Le PC de l'IA ne répond pas ».
- La mise à jour du paquet YunoHost en 0.2.0 (`yunohost app upgrade`), jamais exécutée ici.

## Livraison — étape 3 (les aides)

**Fait** : bouton « Rapport de situation » (situation, menaces, occasions, 3 ordres suggérés ; un clic sur
« + ajouter » place l'ordre dans la zone, le dernier rapport est gardé dans la sauvegarde), onglet Conseiller
(conversation française, gardée dans `etat["conseiller"]`), onglet Diplomatie (choix d'une nation non disparue,
conversation par nation dans `etat["diplomatie"]`), section « Discussions diplomatiques depuis le dernier
tour » dans la requête du narrateur. Version 0.3.0. Critères cochés : 19, 20, 21 et 16 (complété) ; 94 tests
`pytest` verts (19 nouveaux, sans Ollama).

**Choix de réalisation**
- Nouveau module `app/aides.py` (contexte, schémas, lecture) ; l'exécution réutilise le même schéma que le tour :
  fil d'exécution, file unique (même message « en attente, N demande(s) avant vous », même « Le PC de l'IA ne
  répond pas »), sonde de 5 s, lecture tolérante, une relance. Routes `POST /partie/<id>/aide` et
  `GET /partie/<id>/aide`. Une seule aide à la fois par partie ; le joueur envoie au plus 1 000 caractères.
- **Qui sait quoi** : conseiller et rapport reçoivent `evenements_visibles()`, la fiche du joueur, les fiches
  publiques des puissances en vue, ses relations, les guerres, l'objectif (pas le rapport) ; JAMAIS
  `histoire[].resume`, `faits_etablis`, `corrections`, ni le contexte et les règles du scénario. Un dirigeant
  reçoit sa nation, sa relation avec le joueur, ses guerres, les événements publics (et les secrets qu'il partage
  avec le joueur) et SA conversation (20 derniers messages) ; ni l'objectif, ni le conseiller, ni les autres
  conversations. Aucun identifiant de joueur.
- Écriture : l'état est lu au tour de la demande, puis RELU sous verrou avant d'ajouter l'échange : un tour ou une
  annulation n'est jamais écrasé. Les conversations sont retirées des 10 états d'annulation et conservées par
  « Annuler » (ce qui a été dit reste dit). Historique gardé : 60 messages par conversation.
- « Depuis le dernier tour » = messages dont `tour` >= tour courant. Dans le budget de contexte, les échanges
  sont raccourcis (4 messages de 200 caractères) seulement après avoir retiré toute l'histoire ancienne, et
  retirés en tout dernier ; ordres, état du joueur et règles ne sont jamais retirés.
- Les dirigeants ne voient pas les chiffres du joueur ; le conseiller ne connaît que ce que la carte montre déjà
  (fiches publiques), pas les relations entre autres nations.

**À vérifier à la main (non testable ici)**
- Le JavaScript (onglets, clic sur une suggestion, conversation, statut d'attente) dans un vrai navigateur.
- La qualité des réponses du vrai modèle : JSON respecté, ton des dirigeants, suggestions utilisables ; durée.
- Essai réel PC éteint pour les aides ; mise à jour du paquet YunoHost en 0.3.0.

## Livraison — étape 4 (réglages d'après la partie réelle)

**Constats d'une vraie partie sur thnas** (gemma4:12b, scénario 1939, France, 14 tours jusqu'en mars 1944) :
1. La carte n'a jamais bougé : la Pologne entière en 1944 alors que « Invasion de la Pologne » durait encore,
   l'offensive allemande de mai 1940 (règle datée) n'a jamais eu lieu. Le modèle laissait « territoires » vide malgré
   les consignes : avec la sortie contrainte d'Ollama, ce que le schéma n'impose pas est omis.
2. Les chiffres du joueur ne faisaient que monter (armée 100, stabilité 88, influence 100) : chaque variation
   respectait le plafond par tour, mais rien n'avait de coût.
3. On ne voyait pas ce que le modèle avait réellement répondu. La guerre France/Allemagne avait disparu sans cause.

**Réglages (version 0.4.0)**
- **Fronts obligatoires** : nouvelle clé `fronts` du schéma, une entrée par guerre en cours
  `{guerre, avance (a|b|aucun), par, territoires_pris, explication}`. La requête liste chaque guerre avec ses camps et,
  par camp, les codes de territoires tenus (30 au plus par camp, « … (+N autres) » au-delà ; il n'y a pas de données
  de voisinage). Python valide : la guerre existe, les territoires pris appartiennent au camp qui recule, ils vont à
  `par` (nation vivante du camp qui avance, sinon la première, avec une correction) ; ils comptent dans le même
  plafond de transferts que « territoires » (compteur unique, fronts traités d'abord). Une guerre en cours absente de
  `fronts` est signalée en correction. Les règles datées de la période sont recopiées dans « Ce tour » (« À cette date
  dans l'histoire réelle : … — fais-le arriver, sauf si les ordres du joueur l'empêchent ») et la consigne dit que les
  fronts les reflètent.
- **Coûts** : pour chaque nation et chaque tour, la hausse nette (hausses moins baisses, après plafond individuel et
  cumul) ne dépasse pas le plafond d'un chiffre ; sinon les hausses sont réduites proportionnellement (« au total
  ramenée »). Au-dessus de 90, une hausse est divisée par deux (arrondi vers le bas), avant le plafond net. Consignes :
  tout effort a un coût, la guerre use les deux camps, un succès n'augmente pas tout.
- **Paix** : appliquée seulement si un événement du même tour cite des nations des deux camps ; sinon correction.
- **Diagnostic** : `data/diagnostic/dernier_tour.txt` (date, partie, modèle, réponse brute de l'IA et relance, 20 000
  caractères au plus chacune, écrasé à chaque tour, sans identifiant de joueur ni ordres), affiché dans Réglages
  (administrateurs seulement, dans un `<details>`, échappé). Il peut contenir des événements secrets : voulu.
- `fronts` n'est pas exigé par la vérification de forme (pas de relance pour cela) : son absence est corrigée guerre
  par guerre. Les anciennes sauvegardes restent lisibles (`dernier_tour.fronts` est facultatif).

**Limites** : la paix est acceptée dès qu'un événement cite les deux camps (sans contrôle du sujet de l'événement) ;
le choix des territoires proposés au modèle n'est pas géographique ; l'effet réel de ces consignes sur gemma4:12b
n'est pas mesuré. **Critère 23 non coché** : à refaire sur thnas (5 tours, carte qui bouge, chiffres qui ne montent plus
tous ensemble, diagnostic lisible).
