---
numero: 002
titre: Conférences diplomatiques et menu roue sur la carte
depot: autre (thmans-pixel/pax)
statut: en cours    # brouillon → validée → en cours → livrée
date: 2026-11-23
---

# 002 — Conférences diplomatiques et menu roue sur la carte

## Le besoin, en une phrase
Thibault veut « parler à plusieurs dans Diplomatie » et « des raccourcis sur la carte, genre
diplomatie » : réunir plusieurs dirigeants dans une même conversation, et un **menu roue** qui
s'ouvre sur un pays de la carte pour aller droit aux actions qui le concernent.

## Ce que ça change pour qui
- Le joueur : il peut réunir, par exemple, le Royaume-Uni et la Pologne autour d'une même table.
  Il écrit un message, et **chaque dirigeant invité répond à son tour**, en tenant compte de ce
  que disent les autres. Sur la carte, un clic sur un pays ouvre une roue avec quatre actions.
- L'IA : une seule demande par message de conférence, qui contient les réponses de tous les
  dirigeants (même file d'attente qu'aujourd'hui).

## Hors périmètre
- Des conférences entre nations de l'IA sans le joueur.
- Des votes ou des traités signés automatiquement : une conférence reste une discussion. Ses
  effets passent, comme les discussions à deux, par le narrateur du tour suivant, borné par le
  code.
- Le menu roue sur mobile tactile au doigt (on garde un appui long simple, sans geste de balayage).

## Maquette

```
 Onglet Diplomatie
 ┌───────────────────────────────────────────────┐
 │ Conversations : [Royaume-Uni] [Italie]        │
 │                 [Conférence : R-U, Pologne] + │  ← « + » : nouvelle conférence
 ├───────────────────────────────────────────────┤
 │ Conférence — Royaume-Uni, Pologne   [+ inviter]│
 │  Vous : Formons un front commun à l'Est.      │
 │  Chamberlain (R-U) : Londres soutient…        │
 │  Mościcki (Pologne) : Varsovie demande…       │
 │  [ Votre message…                 ] [Envoyer] │
 └───────────────────────────────────────────────┘

 Carte : clic sur l'Italie
            ┌─────────┐
            │ Parler  │
     ┌──────┴──┐  ┌───┴──────┐
     │ Ordre   │ ● │ Conseil │      ● = l'Italie (nom au centre)
     └──────┬──┘  └───┬──────┘
            │ Fiche   │
            └─────────┘
```

## Critères d'acceptation

**Conférences**
1. [x] Dans Diplomatie, le joueur crée une conférence en choisissant 2 à 5 nations (non
   disparues, pas la sienne) ; il peut en inviter une de plus ensuite, jusqu'à 5. —
   *Vérification :* test (création, limite, nation refusée).
2. [x] Un message du joueur en conférence donne une réponse de **chaque** dirigeant invité,
   dans l'ordre, en une seule demande à l'IA (schéma JSON : une entrée par nation invitée,
   toutes les clés obligatoires). Une réponse manquante est signalée sans perdre les autres. —
   *Vérification :* test avec le faux Ollama (une requête, N réponses).
3. [x] Qui sait quoi : chaque dirigeant ne reçoit que les événements publics, ceux de la
   conférence, les secrets partagés par **tous** les participants (joueur compris), et ni les
   conversations à deux ni le conseiller. Un secret connu d'un seul invité n'est pas envoyé. —
   *Vérification :* test (marqueurs secrets absents de la requête).
4. [x] Ce qui s'est dit en conférence depuis le dernier tour est transmis au narrateur, comme
   les discussions à deux, dans le même budget de contexte (critère 15 de la spec 001). —
   *Vérification :* test.
5. [x] Conversations gardées dans la sauvegarde, bornées (60 messages, 20 envoyés à l'IA),
   messages du joueur limités à 1000 caractères ; anciennes sauvegardes lisibles. —
   *Vérification :* test.
6. [x] Même file d'attente, même message « en attente », même comportement PC éteint, pas
   d'annulation de tour pendant une conférence en cours. — *Vérification :* test.

**Menu roue sur la carte**
7. [ ] Un clic sur un pays (autre que le sien) ouvre une roue autour du curseur avec : **Parler**
   (ouvre Diplomatie sur ce pays ; si une conférence est ouverte, propose de l'y inviter),
   **Ordre** (ajoute dans les ordres une ligne « Envers <nation> : »), **Conseil** (ouvre le
   Conseiller avec « Que penses-tu de <nation> ? » prêt à envoyer), **Fiche** (fiche détaillée :
   chiffres, relation avec le joueur, guerres, territoires — ce que la nation du joueur sait).
   Échap ou un clic ailleurs la ferme. — *Vérification :* à la main dans le navigateur.
8. [ ] Sur son propre pays, la roue propose Ordre, Conseil et Fiche (pas Parler). Sur une nation
   disparue ou un territoire sans nation jouable, seulement Fiche. — *Vérification :* à la main.
9. [ ] La roue se manipule au clavier (Tab, Entrée) et un appui long l'ouvre sur écran tactile ;
   le glisser de la carte (déplacement) n'ouvre pas la roue. — *Vérification :* à la main.
10. [x] Aucun texte venant de l'IA ou d'un scénario n'est inséré en HTML dans la roue ou la fiche
    (textContent seulement). — *Vérification :* test (absence d'innerHTML) et relecture.

**Ensemble**
11. [x] `pytest` vert sans Ollama.

## Conception
- Sauvegarde : `etat["conferences"]` = liste de `{id, nations: [...], messages: [{role, nation?,
  texte, tour}]}` ; une conférence est identifiée par un id court. Les discussions à deux
  (`etat["diplomatie"]`) ne changent pas.
- Requête de conférence (`app/aides.py`) : pour chaque invité, sa fiche, sa relation avec le
  joueur et avec les autres invités, les guerres ; les événements filtrés par
  `evenement_visible` pour **l'intersection** des participants ; jamais `histoire[].resume` ni
  `faits_etablis`. Schéma : `{"reponses": [{"nation": id, "texte": "..."}]}`, `reponses` et ses
  sous-clés obligatoires ; le code garde une réponse par invité, dans l'ordre des invités.
- Narrateur (`app/tour.py`) : section « Discussions diplomatiques » étendue aux conférences
  (nations citées), même raccourcissement que les dialogues à deux.
- Routes : `POST /partie/{id}/aide` existant, avec `genre = "conference"` et
  `conference = id` ou `nations = [...]` pour la créer ; `POST /partie/{id}/conference/{cid}/inviter`.
- Roue : `app/static/roue.js`, en SVG/HTML positionné sur la carte, sans dépendance ; branchée
  sur l'événement de clic existant de `carte.js` (en distinguant clic et glisser). « Fiche »
  réutilise la fiche du bas de page, enrichie de la relation et des guerres connues.

## Fichiers touchés (prévision)
`app/aides.py`, `app/execution.py`, `app/main.py`, `app/tour.py`, `app/templates/partie.html`,
`app/static/aides.js`, `app/static/carte.js`, `app/static/roue.js` (nouveau), `app/static/style.css`,
`tests/test_aides.py`, `tests/test_conferences.py` (nouveau).

## Risques
- Réponse plus longue (plusieurs dirigeants) : plus de temps et de contexte. Borne : 5 invités,
  réponses de 600 caractères au plus chacune.
- Le modèle peut faire parler un dirigeant à la place d'un autre ou oublier quelqu'un : le code
  attribue par `nation`, signale l'absent, ignore l'inconnu.
- Fuite de secret entre invités : couverte par le critère 3 (intersection).

## Étapes
1. **Conférences** (une PR) : critères 1 à 6, 11.
2. **Menu roue** (une PR) : critères 7 à 10, 11.

## Questions ouvertes
Aucune. Réponses de Thibault (23/11/2026) : chaque dirigeant invité répond à son tour ;
la roue propose les quatre actions (Parler, Ordre, Conseil, Fiche).

## Livraison — étape 1 (conférences, version 0.5.0)

**Fait**
- `app/aides.py` : genre `conference`, schéma `{"reponses": [{"nation" (enum des invités), "texte"}]}` (toutes les clés
  obligatoires), consigne, contexte (fiches des invités, relations joueur/invités et entre invités, guerres, événements
  par **intersection** : publics, ou secrets connus du joueur et de tous les invités), transcription des 20 derniers
  messages, lecture tolérante (attribution par id ou par nom, inconnu et doublon ignorés, réponse de 600 caractères au
  plus, ordre des invités), bornes (60 gardés, 1 000 caractères par message du joueur).
- `app/execution.py` : même file unique, même `Aide`, état relu sous `tours.verrou` avant d'écrire ; la conférence n'est
  créée dans la sauvegarde qu'une fois l'IA répondue (un échec ne laisse rien d'orphelin) ; `chat_flux` (donc `think:
  false`) réutilisé ; une seule relance si aucune réponse n'est utilisable ; annulation refusée pendant l'aide (comme
  avant) ; l'annulation conserve les conférences.
- `app/main.py` : `POST /partie/{id}/aide` avec `genre=conference` + `nations` (création, 2 à 5) ou `conference` (id) ;
  `POST /partie/{id}/conference/{cid}/inviter` (5 au plus, nation vivante, pas la sienne, pas deux fois).
- `app/tour.py` : les conférences du tour courant rejoignent la section « Discussions diplomatiques » (même niveau de
  raccourcissement que les dialogues à deux).
- Interface (`partie.html`, `aides.js`, `style.css`) : « + Nouvelle conférence… » et conférences existantes dans la liste
  de l'onglet Diplomatie, cases à cocher, invitation ; tout texte par `textContent`. Crochet `window.paxDiplomatie`
  réservé à la roue (étape 2).

**Tests** (`tests/test_conferences.py`, 17 tests) : critère 1 `test_01_*`, 2 `test_02_*`, 3 `test_03_*`, 4 `test_04_*`,
5 `test_05_*`, 6 `test_06_*`, 11 `pytest tests` vert (130 tests).

**À vérifier à la main** : l'interface de conférence dans un vrai navigateur (créer, inviter, lire les bulles) ; la
qualité des réponses du vrai modèle (un dirigeant qui parle pour un autre, JSON respecté, durée) ; mise à jour du
paquet YunoHost en 0.5.0 (non testable hors de thnas).

**Limites** : une conférence ne se supprime pas ; un invité disparu reste affiché mais ne répond plus.

## Livraison — étape 2 (menu roue, version 0.5.1)

**Fait**
- `app/static/roue.js` (nouveau) : roue HTML positionnée sur la carte (Parler en haut, Ordre à gauche, Conseil à
  droite, Fiche en bas, nom de la nation au centre), boutons réels (Tab tourne dans la roue, Entrée valide), Échap ou
  clic ailleurs ou zoom ferment, appui long de 500 ms sur écran tactile (annulé au-delà de 8 px de déplacement).
  Sur son pays : pas de « Parler » ; nation disparue ou territoire sans nation : seulement « Fiche ».
- `app/static/carte.js` : n'annonce le pays à la roue (événement `pax:pays`) que pour un vrai clic, jamais après un
  glisser (seuil existant de 4 px) ; `innerHTML` retiré (la fiche utilise `textContent`) ; la fiche du bas affiche en
  plus la relation avec le joueur et les guerres de la nation.
- Actions : **Ordre** ajoute « Envers <nation> : » dans une ligne vide (ou une nouvelle, limite de 10 respectée, message
  sinon) ; **Conseil** ouvre le Conseiller avec « Que penses-tu de <nation> ? » dans la saisie, sans l'envoyer ;
  **Parler** ouvre Diplomatie sur la nation, ou, si une conférence est affichée, demande (confirm) s'il faut y inviter la
  nation ; **Fiche** affiche et met au point la fiche du bas.
- `app/monde.py` : `fiche_nation(..., pour_joueur=True)` ajoute relation avec le joueur et guerres (déjà visibles dans
  l'onglet État) ; l'écran de choix de nation n'en ajoute pas.

**Tests** (`tests/test_roue.py`) : 7 et 8 données de la fiche (relation, guerres, joueur, disparue) ; 7 aucun secret
(événement secret d'autrui, résumé, faits établis, corrections, conseiller) dans les fiches ; 10 aucun `innerHTML`
(roue, carte, aides) et `textContent` ; 9 garde-fou de lecture du code (pas une preuve) ; syntaxe `node --check`
des trois scripts ; 11 `pytest tests` vert (142 tests). Les critères 7, 8 et 9 restent **à vérifier à la main**.

**À vérifier à la main (navigateur)** : clic sur un pays autre que le sien (4 actions, position près des bords), sur son
pays (3 actions), sur une nation disparue et sur un territoire sans nation (Fiche seule) ; Échap et clic ailleurs ;
glisser la carte n'ouvre rien ; Tab / Maj+Tab / Entrée dans la roue ; appui long sur tablette ou téléphone (et que le
relâchement ne ferme pas la roue) ; « Ordre » avec 10 ordres déjà saisis ; « Parler » avec une conférence affichée.

**Limites** : la roue s'ouvre à la souris ou au doigt, pas encore au clavier seul (les pays ne sont pas atteignables
par Tab) ; sur son propre pays, l'ordre commence par « Pour <nation> : » (et non « Envers ») ; la proposition
d'invitation utilise la boîte de dialogue du navigateur.
