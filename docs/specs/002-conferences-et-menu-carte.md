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
1. [ ] Dans Diplomatie, le joueur crée une conférence en choisissant 2 à 5 nations (non
   disparues, pas la sienne) ; il peut en inviter une de plus ensuite, jusqu'à 5. —
   *Vérification :* test (création, limite, nation refusée).
2. [ ] Un message du joueur en conférence donne une réponse de **chaque** dirigeant invité,
   dans l'ordre, en une seule demande à l'IA (schéma JSON : une entrée par nation invitée,
   toutes les clés obligatoires). Une réponse manquante est signalée sans perdre les autres. —
   *Vérification :* test avec le faux Ollama (une requête, N réponses).
3. [ ] Qui sait quoi : chaque dirigeant ne reçoit que les événements publics, ceux de la
   conférence, les secrets partagés par **tous** les participants (joueur compris), et ni les
   conversations à deux ni le conseiller. Un secret connu d'un seul invité n'est pas envoyé. —
   *Vérification :* test (marqueurs secrets absents de la requête).
4. [ ] Ce qui s'est dit en conférence depuis le dernier tour est transmis au narrateur, comme
   les discussions à deux, dans le même budget de contexte (critère 15 de la spec 001). —
   *Vérification :* test.
5. [ ] Conversations gardées dans la sauvegarde, bornées (60 messages, 20 envoyés à l'IA),
   messages du joueur limités à 1000 caractères ; anciennes sauvegardes lisibles. —
   *Vérification :* test.
6. [ ] Même file d'attente, même message « en attente », même comportement PC éteint, pas
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
10. [ ] Aucun texte venant de l'IA ou d'un scénario n'est inséré en HTML dans la roue ou la fiche
    (textContent seulement). — *Vérification :* test (absence d'innerHTML) et relecture.

**Ensemble**
11. [ ] `pytest` vert sans Ollama.

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
