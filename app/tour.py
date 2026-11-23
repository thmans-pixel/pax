"""Un tour de jeu : durées, plafonds, requête envoyée à l'IA, lecture de sa réponse, application.

Principe : l'IA propose un JSON de changements ; ICI le code le vérifie, le borne, l'applique et
note chaque correction. Rien de ce que dit l'IA n'entre dans l'état sans être passé par `appliquer`.
"""
from __future__ import annotations

import calendar
import copy
import json
import re
import unicodedata
from datetime import date, timedelta

from .monde import evenement_visible, evenements_visibles, CHIFFRES, LIBELLES_CHIFFRES, cle_relation, date_fr, est_disparue, palier, territoires_de
from .scenarios import CHIFFRES_DEFAUT, COULEUR, couleur_par_defaut

# ------------------------------------------------------------------ durées et plafonds
DUREES = {
    "1sem": {"libelle": "1 semaine", "jours": 7},
    "1mois": {"libelle": "1 mois", "mois": 1},
    "3mois": {"libelle": "3 mois", "mois": 3},
    "6mois": {"libelle": "6 mois", "mois": 6},
    "1an": {"libelle": "1 an", "mois": 12},
}
DUREE_DEFAUT = "1mois"
MAX_ORDRES = 10
LONGUEUR_ORDRE = 500
HISTORIQUE_MAX = 10          # états gardés pour « Annuler »
RESERVE_REPONSE = 4096       # jetons gardés pour la réponse de l'IA
TOURS_DETAILLES = 3
MESSAGES_NARRATEUR = 20      # messages par nation donnés au narrateur (échanges depuis le dernier tour)

# Plafonds par tour : (variation d'un chiffre, variation d'une relation, transferts de territoires)
PLAFONDS = {
    "1sem": (5, 20, 3), "1mois": (5, 20, 3),
    "3mois": (10, 30, 6), "6mois": (10, 30, 6),
    "1an": (15, 40, 10),
}


SEUIL_RENDEMENT = 90         # au-dessus, une hausse de chiffre est divisée par deux
CODES_PAR_CAMP = 30          # territoires listés par camp et par guerre dans la requête (budget de contexte)


def plafonds(duree: str) -> dict:
    c, r, t = PLAFONDS[duree]
    return {"chiffre": c, "relation": r, "transferts": t}


def ajouter_duree(iso: str, duree: str) -> str:
    """1 semaine = 7 jours ; n mois = même jour n mois plus tard (le dernier jour du mois si besoin)."""
    d = date.fromisoformat(iso)
    spec = DUREES[duree]
    if "jours" in spec:
        return (d + timedelta(days=spec["jours"])).isoformat()
    m = d.month - 1 + spec["mois"]
    annee, mois = d.year + m // 12, m % 12 + 1
    jour = min(d.day, calendar.monthrange(annee, mois)[1])
    return date(annee, mois, jour).isoformat()


# ------------------------------------------------------------------ petits outils
def _norm(texte) -> str:
    t = unicodedata.normalize("NFD", str(texte or "")).casefold()
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def _entier(v):
    """Un nombre entier à partir de ce que dit l'IA (3, 3.0, « +3 », « 3 »), sinon None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(round(v))
    if isinstance(v, str):
        m = re.fullmatch(r"\s*([+-]?\d+)\s*", v)
        if m:
            return int(m.group(1))
    return None


def _liste_textes(v) -> list[str]:
    """Une liste de textes à partir de ce que dit l'IA (liste, texte seul, nombre) ; le reste est écarté."""
    if isinstance(v, (str, int)) and not isinstance(v, bool):
        v = [v]
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if isinstance(x, (str, int)) and not isinstance(x, bool) and str(x).strip()]


MOTS_SECRET = re.compile(r"\b(secr[eè]t(e|s|es)?|confidentiel(le)?s?|clandestin(e)?s?)\b", re.IGNORECASE)
MENTION_SECRET = re.compile(r"\s*[\(\[]\s*(secret|confidentiel)\s*[\)\]]", re.IGNORECASE)


def _secret(v) -> bool:
    """Secret par défaut : seul un « non » explicite (False, « false », « non », 0) rend l'événement public."""
    if v is None or v is False:
        return False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0
    if isinstance(v, str):
        return _norm(v) not in ("", "false", "faux", "non", "no", "0")
    return True


def _cite(v) -> str:
    """Une valeur venue de l'IA, citée dans une correction : tronquée."""
    t = " ".join(str(v).split())
    return t if len(t) <= 80 else t[:79] + "…"


def _borner(v: int, mini: int, maxi: int) -> int:
    return max(mini, min(maxi, v))


def en_guerre(etat: dict, a: str, b: str) -> bool:
    return any((a in g["camp_a"] and b in g["camp_b"]) or (a in g["camp_b"] and b in g["camp_a"])
               for g in etat["guerres"])


def partie_terminee(etat: dict) -> bool:
    return est_disparue(etat, etat["nation_joueur"])


def nettoyer_ordres(ordres) -> list[str]:
    """Ordres écrits par le joueur : de 1 à 10, non vides. Lève ValueError avec un message clair."""
    if not isinstance(ordres, list):
        raise ValueError("Les ordres sont mal formés.")
    propres = []
    for o in ordres:
        if not isinstance(o, str):
            raise ValueError("Un ordre doit être un texte.")
        o = " ".join(o.split())
        if o:
            propres.append(o)
    if not propres:
        raise ValueError("Écrivez au moins un ordre.")
    if len(propres) > MAX_ORDRES:
        raise ValueError(f"{MAX_ORDRES} ordres au plus par tour.")
    if any(len(o) > LONGUEUR_ORDRE for o in propres):
        raise ValueError(f"Un ordre ne peut pas dépasser {LONGUEUR_ORDRE} caractères.")
    return propres


# ------------------------------------------------------------------ schéma de la réponse
ISSUES = ["réussi", "partiel", "échec"]
BASES = ["guerre", "traité", "annexion", "indépendance"]


def schema_reponse() -> dict:
    texte = {"type": "string"}
    liste_ids = {"type": "array", "items": texte}
    return {
        "type": "object",
        "properties": {
            "evenements": {"type": "array", "items": {"type": "object", "properties": {
                "date": texte, "titre": texte, "texte": texte, "pays": liste_ids,
                "secret": {"type": "boolean"}}, "required": ["titre", "texte"]}},
            "ordres": {"type": "array", "items": {"type": "object", "properties": {
                "numero": {"type": "integer"}, "issue": {"type": "string", "enum": ISSUES},
                "explication": texte}, "required": ["numero", "issue", "explication"]}},
            "chiffres": {"type": "array", "items": {"type": "object", "properties": {
                "nation": texte, "chiffre": {"type": "string", "enum": list(CHIFFRES)},
                "variation": {"type": "integer"}, "raison": texte},
                "required": ["nation", "chiffre", "variation"]}},
            "relations": {"type": "array", "items": {"type": "object", "properties": {
                "nation_a": texte, "nation_b": texte, "variation": {"type": "integer"}, "raison": texte},
                "required": ["nation_a", "nation_b", "variation"]}},
            "guerres": {"type": "array", "items": {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["déclaration", "paix"]}, "nom": texte,
                "camp_a": liste_ids, "camp_b": liste_ids}, "required": ["action"]}},
            "territoires": {"type": "array", "items": {"type": "object", "properties": {
                "territoire": texte, "vers": texte, "base": {"type": "string", "enum": BASES},
                "raison": texte}, "required": ["territoire", "vers", "base"]}},
            "fronts": {"type": "array", "items": {"type": "object", "properties": {
                "guerre": texte, "avance": {"type": "string", "enum": ["a", "b", "aucun"]},
                "par": texte, "territoires_pris": liste_ids, "explication": texte},
                "required": ["guerre", "avance", "par", "territoires_pris", "explication"]}},
            "nouvelle_nation": {"type": ["object", "null"], "properties": {
                "nom": texte, "dirigeant": texte, "regime": texte, "couleur": texte,
                "territoires": liste_ids}},
            "resume": texte,
            "faits": liste_ids,
        },
        # Tout est obligatoire : avec la sortie contrainte d'Ollama, un modèle saute les clés
        # facultatives et ne change alors jamais l'état du monde (constaté sur thnas).
        "required": ["evenements", "ordres", "chiffres", "relations", "guerres", "territoires",
                     "fronts", "nouvelle_nation", "resume", "faits"],
    }


CONSIGNES = """\
Tu es le narrateur d'un jeu de stratégie au tour par tour : une simulation historique du monde, \
écrite en français. Le joueur dirige une nation ; il vient de donner des ordres et choisi une \
durée. Tu fais passer le temps : tu racontes ce qui se passe dans le monde pendant cette durée, \
y compris chez les autres nations, qui agissent selon leurs intérêts, leur régime et l'époque.

Règles à respecter :
- Réponds UNIQUEMENT par un objet JSON conforme au schéma, sans texte autour.
- Écris en français. Les titres sont courts, les textes tiennent en deux à quatre phrases.
- Désigne les nations par leur identifiant (celui entre crochets) et les territoires par leur code.
- Juge chaque ordre selon la situation réelle de la nation (chiffres, alliances, guerres) : \
« réussi », « partiel » ou « échec », avec une explication. Donne une issue à CHAQUE ordre, par son numéro.
- Reste réaliste : l'histoire peut dévier de la réalité à cause des ordres du joueur, mais sans miracle. \
Seules les technologies de l'époque du scénario existent : un ordre qui demande une invention \
impossible à cette date (arme nucléaire en 1939, ordinateurs modernes…) est un « échec ».
- L'état du monde doit suivre le récit. Chaque événement important a ses conséquences chiffrées : \
une guerre déclarée apparaît dans « guerres » (action « déclaration »), une conquête dans \
« territoires », un rapprochement ou une crise dans « relations », un effort ou une perte dans \
« chiffres ». Un ordre « réussi » ou « partiel » change au moins un chiffre ou une relation. \
Ne laisse ces listes vides que s'il ne s'est vraiment rien passé.
- Ne raconte pas de nouveau un événement des tours précédents (il est déjà dans l'histoire).
- Les « règles de simulation » datées dans la période du tour se produisent, avec leurs \
conséquences dans les listes (une invasion : « guerres » et « territoires »), sauf si les ordres \
du joueur ou la situation les ont rendues impossibles ; dis-le alors dans un événement.
- « fronts » est OBLIGATOIRE : une entrée par guerre de « Guerres en cours » (nom exact) : « avance » \
(« a », « b » ou « aucun »), « par » (nation du camp qui avance qui reçoit les territoires), \
« territoires_pris » (codes tenus par le camp qui recule) et « explication ». Le front bouge selon la \
durée et le rapport de forces, dans la limite des plafonds ; le dernier territoire d'une nation ne tombe que face à une armée double de la sienne. \
Les fronts reflètent les règles datées de « Ce tour ».
- Tout effort a un coût : plus d'armée se paie en économie ou stabilité ; une guerre use l'économie \
et la stabilité des deux camps ; un succès n'augmente pas tout à la fois. La hausse totale des chiffres \
d'une nation ne dépasse pas le plafond d'un chiffre ; au-dessus de 90, une hausse est divisée par deux.
- Une paix doit être racontée par un événement du tour citant les deux camps dans « pays ».
- « nom » d'une guerre déclarée : un nom court comme « Guerre franco-allemande ».
- Un territoire ne change de mains que par une guerre en cours (« guerre »), un traité ou une \
annexion décrits dans un événement du même tour (« traité », « annexion »), ou une indépendance \
(« indépendance », avec « nouvelle_nation », une seule par tour). Les événements qui impliquent \
deux nations doivent citer les deux dans « pays ».
- Un événement « secret » n'est connu que de ceux qui y participent : mets « secret » à true et les \
nations concernées dans « pays ». N'écris jamais « secret » ni « confidentiel » dans le titre ou le texte.
- Les événements ont une date comprise entre le début et la fin du tour (AAAA-MM-JJ).
- « resume » : un paragraphe qui résume tout le tour. « faits » : les faits nouveaux et durables \
à retenir (une phrase chacun).
- Les « discussions diplomatiques depuis le dernier tour » sont les paroles échangées entre le joueur \
et des dirigeants : les promesses, demandes et menaces du joueur comptent (une promesse non tenue a \
des conséquences sur les relations). Ce sont des paroles, pas des faits : elles ne changent l'état \
du monde que par les listes de ta réponse.
- Si des corrections du tour précédent sont listées, tiens-en compte : ce sont des propositions \
que le jeu a refusées ou ramenées à la limite.
"""


# ------------------------------------------------------------------ la requête
class ContexteTropPetit(Exception):
    pass


def estimer_jetons(messages: list[dict]) -> int:
    """Estimation prudente : 1 jeton pour 3 caractères (le français et le JSON coûtent cher)."""
    return sum(-(-len(m["content"]) // 3) + 8 for m in messages)


def _ligne_nation(etat: dict, nid: str, noms_terr: dict[str, str], complete: bool) -> str:
    n = etat["nations"][nid]
    terr = territoires_de(etat, nid)
    if not complete:
        return f"- {n['nom']} [{nid}] — {', '.join(terr)}"
    chiffres = ", ".join(f"{LIBELLES_CHIFFRES[c]} {n[c]}" for c in CHIFFRES)
    detail = ", ".join(f"{t} ({noms_terr.get(t, t)})" for t in terr)
    return (f"- {n['nom']} [{nid}] — dirigeant : {n['dirigeant'] or 'inconnu'} ; régime : "
            f"{n['regime'] or 'inconnu'} ; {chiffres} ; territoires : {detail}")


def _en_vue(etat: dict) -> list[str]:
    joueur = etat["nation_joueur"]
    res = []
    for nid, n in etat["nations"].items():
        if nid == joueur or est_disparue(etat, nid):
            continue
        note = etat["relations"].get(cle_relation(nid, joueur), 0)
        if n["majeure"] or en_guerre(etat, nid, joueur) or palier(note) == "allié":
            res.append(nid)
    return sorted(res)


def _codes_camp(etat: dict, camp: list[str]) -> str:
    """« nation [CODES] ; … » : les territoires tenus par un camp, bornés (CODES_PAR_CAMP au plus)."""
    vivants = [n for n in camp if n in etat["nations"]]
    par = max(3, CODES_PAR_CAMP // max(1, len(vivants)))
    morceaux = []
    for n in vivants:
        terr = territoires_de(etat, n)
        reste = len(terr) - par
        liste = ", ".join(terr[:par]) + (f", … (+{reste} autres)" if reste > 0 else "")
        morceaux.append(f"{n} [{liste or 'aucun territoire'}]")
    return " + ".join(morceaux)


def _lignes_guerres(etat: dict) -> list[str]:
    lignes = []
    for g in etat["guerres"]:
        lignes.append(f"- « {g['nom']} » — camp a : {_codes_camp(etat, g['camp_a'])} ; "
                      f"camp b : {_codes_camp(etat, g['camp_b'])}")
    return lignes or ["(aucune)"]


def _regles_utiles(etat: dict, debut: str, fin: str) -> list[dict]:
    limite = (date.fromisoformat(fin) + timedelta(days=30)).isoformat()
    return [r for r in etat["scenario"]["regles"] if r["date"] is None or debut <= r["date"] <= limite]


def construire_requete(etat: dict, noms_terr: dict[str, str], ordres: list[str], duree: str,
                       num_ctx: int) -> tuple[list[dict], dict]:
    """Les messages à envoyer, réduits au besoin pour tenir dans `num_ctx` moins 4 096 jetons.

    On réduit dans cet ordre : les 3 derniers tours détaillés passent à leur résumé, puis les
    résumés les plus anciens sont retirés, puis (dernier recours) les nations « une ligne » qui
    n'ont pas de lien avec le joueur. Jamais : les ordres, l'état du joueur, les règles utiles.
    Renvoie (messages, infos) ; lève ContexteTropPetit si même cela ne suffit pas.
    """
    budget = num_ctx - RESERVE_REPONSE
    histoire = etat.get("histoire", [])
    paliers_reduction = [(TOURS_DETAILLES, len(histoire), False, 0)]
    paliers_reduction += [(0, len(histoire), False, 0)]
    for k in (20, 10, 5, 2, 0):
        if k < len(histoire):
            paliers_reduction.append((0, k, False, 0))
    # les paroles données au joueur (promesses) comptent plus que l'histoire ancienne : on les
    # raccourcit seulement après avoir tout retiré de l'histoire, et on les retire en tout dernier.
    paliers_reduction += [(0, 0, False, 1), (0, 0, True, 1), (0, 0, True, 2)]
    for detail, garde, serre, dial in paliers_reduction:
        messages = _assembler(etat, noms_terr, ordres, duree, detail, garde, serre, dial)
        jetons = estimer_jetons(messages)
        if jetons <= budget:
            return messages, {"jetons": jetons, "budget": budget, "detail": detail,
                              "resumes": garde, "serre": serre, "dialogues": dial}
    raise ContexteTropPetit(
        f"Le tour ne tient pas dans le contexte de {num_ctx} jetons (il en faut environ {jetons + RESERVE_REPONSE}). "
        "Augmentez la taille de contexte dans les réglages.")


def _lignes_dialogues(etat: dict, niveau: int) -> list[str]:
    """Les échanges diplomatiques tenus depuis le dernier tour (le narrateur voit tout).
    Niveau 0 : jusqu'à 20 messages par nation ; 1 : 4 messages de 200 caractères ; 2 : rien."""
    if niveau >= 2:
        return []
    maxi, coupe = (MESSAGES_NARRATEUR, None) if niveau == 0 else (4, 200)
    lignes = []
    for nid, msgs in (etat.get("diplomatie") or {}).items():
        if nid not in etat["nations"] or not isinstance(msgs, list):
            continue
        # « depuis le dernier tour » : dits au tour courant (ou plus tard, si un tour a été annulé)
        recents = [m for m in msgs if m.get("tour", 0) >= etat["tour"]][-maxi:]
        if not recents:
            continue
        n = etat["nations"][nid]
        lignes.append(f"### {n['nom']} [{nid}] — dirigeant : {n['dirigeant'] or 'inconnu'}")
        for m in recents:
            texte = " ".join(str(m.get("texte", "")).split())
            if coupe and len(texte) > coupe:
                texte = texte[:coupe - 1] + "…"
            lignes.append(f"- {'Le joueur' if m.get('de') == 'joueur' else 'Le dirigeant'} : {texte}")
    for c in etat.get("conferences") or []:
        noms = [etat["nations"][i]["nom"] + f" [{i}]" for i in c.get("nations", []) if i in etat["nations"]]
        recents = [m for m in c.get("messages") or [] if m.get("tour", 0) >= etat["tour"]][-maxi:]
        if not noms or not recents:
            continue
        lignes.append("### Conférence : " + ", ".join(noms))
        for m in recents:
            texte = " ".join(str(m.get("texte", "")).split())
            if coupe and len(texte) > coupe:
                texte = texte[:coupe - 1] + "…"
            if m.get("role") == "joueur":
                lignes.append(f"- Le joueur : {texte}")
            elif m.get("nation") in etat["nations"]:
                lignes.append(f"- {etat['nations'][m['nation']]['nom']} : {texte}")
    return lignes


def _assembler(etat: dict, noms_terr: dict[str, str], ordres: list[str], duree: str,
               nb_detail: int, nb_resumes: int, serre: bool, dial: int = 0) -> list[dict]:
    joueur = etat["nation_joueur"]
    debut = etat["date"]
    fin = ajouter_duree(debut, duree)
    p = plafonds(duree)
    L: list[str] = []

    def section(titre: str, lignes: list[str]):
        L.append(f"## {titre}")
        L.extend(lignes)
        L.append("")

    section("Contexte du scénario", [etat["scenario"]["contexte"].strip()])
    regles = _regles_utiles(etat, debut, fin)
    datees = [r for r in regles if r["date"] and debut <= r["date"] <= fin]      # mises en avant dans « Ce tour »
    autres_regles = [r for r in regles if r not in datees]
    if autres_regles:
        section("Règles de simulation utiles pour cette période",
                [f"- {(date_fr(r['date']) + ' : ') if r['date'] else ''}{r['texte']}" for r in autres_regles])
    ce_tour = [
        f"Début : {date_fr(debut)} ({debut}). Fin : {date_fr(fin)} ({fin}). Durée : {DUREES[duree]['libelle']}.",
        f"Plafonds pour ce tour : un chiffre varie de ±{p['chiffre']} au plus, une relation de "
        f"±{p['relation']} au plus, {p['transferts']} transferts de territoires au plus (fronts compris). "
        f"Pour chaque nation, la hausse totale de ses chiffres ne dépasse pas {p['chiffre']}.",
        f"Tour numéro {etat['tour'] + 1}."]
    for r in datees:
        texte = " ".join(r["texte"].split())
        ce_tour.append(f"À cette date ({date_fr(r['date'])}) dans l'histoire réelle : {texte} — fais-le arriver, "
                       "sauf si les ordres du joueur l'empêchent ; « fronts » reflète ces règles.")
    section("Ce tour", ce_tour)
    section("La nation du joueur", [_ligne_nation(etat, joueur, noms_terr, True)])
    vue = _en_vue(etat)
    section("Puissances en vue", [_ligne_nation(etat, n, noms_terr, True) for n in vue] or ["(aucune)"])
    deja = set(vue) | {joueur}
    autres = []
    for nid in etat["nations"]:
        if nid in deja or est_disparue(etat, nid):
            continue
        if serre and cle_relation(nid, joueur) not in etat["relations"] and not any(
                nid in g["camp_a"] or nid in g["camp_b"] for g in etat["guerres"]):
            continue
        autres.append(_ligne_nation(etat, nid, noms_terr, False))
    section("Autres nations (une ligne chacune)" + (" — seules celles liées au joueur ou en guerre" if serre else ""),
            autres or ["(aucune)"])
    notables = sorted(((abs(n), k, n) for k, n in etat["relations"].items() if abs(n) >= 50), reverse=True)
    rel = []
    for _, cle, note in notables[:40]:
        a, b = cle.split("|")
        if a in etat["nations"] and b in etat["nations"] and not est_disparue(etat, a) and not est_disparue(etat, b):
            rel.append(f"- {a} / {b} : {note:+d} ({palier(note)})")
    section("Relations notables", rel or ["(aucune)"])
    section("Guerres en cours (une entrée « fronts » par guerre, avec ce nom exact)", _lignes_guerres(etat))
    if etat.get("faits_etablis"):
        section("Faits établis", [f"- {f}" for f in etat["faits_etablis"][-60:]])
    hist = etat.get("histoire", [])
    if hist and (nb_detail or nb_resumes):
        lignes = []
        recents = hist[max(0, len(hist) - nb_detail):] if nb_detail else []
        anciens = hist[:len(hist) - len(recents)]
        anciens = anciens[len(anciens) - min(nb_resumes, len(anciens)):] if nb_resumes else []
        for h in anciens:
            lignes.append(f"- Tour {h['tour']} ({date_fr(h['du'])} → {date_fr(h['au'])}) : {h['resume']}")
        for h in recents:
            lignes.append(f"- Tour {h['tour']} ({date_fr(h['du'])} → {date_fr(h['au'])}) : {h['resume']}")
            for ev in [e for e in etat["journal"] if e.get("tour") == h["tour"]]:
                lignes.append(f"    · {ev['titre']}" + (f" [connu seulement de : {', '.join(ev.get('pays') or [])}]" if ev.get('secret') else ''))
        section("Histoire récente (du plus ancien au plus récent)", lignes)
    dialogues = _lignes_dialogues(etat, dial)
    if dialogues:
        section("Discussions diplomatiques depuis le dernier tour (ce que le joueur a dit ou promis, "
                "et ce que les dirigeants ont répondu, à deux ou en conférence)", dialogues)
    if etat.get("objectif"):
        section("Objectif permanent du joueur", [etat["objectif"]])
    if etat.get("corrections"):
        section("Corrections du tour précédent (propositions que le jeu a refusées ou ramenées)",
                [f"- {c}" for c in etat["corrections"]])
    section("Ordres du joueur", [f"{i}. {o}" for i, o in enumerate(ordres, 1)])
    L.append("Réponds maintenant par l'objet JSON du tour.")
    return [{"role": "system", "content": CONSIGNES}, {"role": "user", "content": "\n".join(L)}]


# ------------------------------------------------------------------ lecture tolérante
def _sans_virgules_en_trop(s: str) -> str:
    """Retire les virgules juste avant « } » ou « ] », sans toucher à l'intérieur des textes."""
    sortie, i, n, dans = [], 0, len(s), False
    while i < n:
        c = s[i]
        if dans:
            sortie.append(c)
            if c == "\\" and i + 1 < n:
                i += 1
                sortie.append(s[i])
            elif c == '"':
                dans = False
        elif c == '"':
            dans = True
            sortie.append(c)
        elif c == ",":
            j = i + 1
            while j < n and s[j].isspace():
                j += 1
            if not (j < n and s[j] in "}]"):
                sortie.append(c)
        else:
            sortie.append(c)
        i += 1
    return "".join(sortie)


def lire_reponse(texte: str) -> tuple[dict | None, list[str]]:
    """Tire l'objet JSON d'un texte d'IA : bloc <think>, texte autour, ``` et virgules en trop tolérés."""
    t = re.sub(r"<think>.*?</think>", "", texte or "", flags=re.S | re.I)
    t = re.sub(r"<think>.*\Z", "", t, flags=re.S | re.I)      # bloc jamais refermé
    t = re.sub(r"```(?:json)?", "", t, flags=re.I)
    debut = t.find("{")
    if debut < 0:
        return None, ["la réponse ne contient aucun objet JSON"]
    erreur = ""
    dec = json.JSONDecoder()
    for essai in (t[debut:], _sans_virgules_en_trop(t[debut:])):
        try:
            obj, _ = dec.raw_decode(essai)
        except ValueError as e:
            erreur = str(e)
            continue
        if isinstance(obj, dict):
            return obj, []
    return None, [f"le JSON est invalide ({erreur})"]


def verifier_forme(obj: dict) -> list[str]:
    """Fautes de forme qui justifient une relance (le reste est corrigé sans relance)."""
    f = []
    listes = {"evenements": True, "ordres": True, "chiffres": False, "relations": False,
              "guerres": False, "territoires": False, "fronts": False, "faits": False}
    for cle, obligatoire in listes.items():
        v = obj.get(cle)
        if v is None:
            if obligatoire:
                f.append(f"la clé « {cle} » est absente")
        elif not isinstance(v, list):
            f.append(f"« {cle} » doit être une liste")
        elif any(not isinstance(x, (dict if cle != "faits" else str)) for x in v):
            f.append(f"« {cle} » contient un élément mal formé")
    if not isinstance(obj.get("resume"), str) or not obj.get("resume", "").strip():
        f.append("« resume » doit être un paragraphe de texte non vide")
    nn = obj.get("nouvelle_nation")
    if nn is not None and not isinstance(nn, dict):
        f.append("« nouvelle_nation » doit être un objet ou null")
    return f


def message_relance(fautes: list[str]) -> str:
    return ("Ta réponse précédente n'est pas exploitable :\n" + "\n".join(f"- {x}" for x in fautes)
            + "\nRenvoie l'objet JSON complet du tour, corrigé, sans aucun texte autour.")


# ------------------------------------------------------------------ application
def _issue(v) -> str | None:
    v = _norm(v)
    if v.startswith(("reuss", "succes", "ok")):
        return "réussi"
    if v.startswith(("partiel", "mitige")):
        return "partiel"
    if v.startswith(("echec", "echoue", "rate")):
        return "échec"
    return None


def _repartir(hausses: dict[str, int], permis: int) -> dict[str, int]:
    """Ramène des hausses à une somme de `permis`, proportionnellement (restes aux plus grosses hausses)."""
    total = sum(hausses.values())
    part = {c: h * permis // total for c, h in hausses.items()}
    reste = permis - sum(part.values())
    for c in sorted(hausses, key=lambda c: (-(hausses[c] * permis % total), -hausses[c])):
        if reste <= 0:
            break
        part[c] += 1
        reste -= 1
    return part


def _slug(nom: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", _norm(nom)).strip("-")
    return s or "nouvelle-nation"


class Application:
    """Applique une réponse validée sur une COPIE de l'état et collecte les corrections."""

    def __init__(self, etat: dict, noms_terr: dict[str, str], duree: str):
        self.etat = etat
        self.noms_terr = noms_terr
        self.duree = duree
        self.p = plafonds(duree)
        self.transferts = 0                       # transferts de territoires faits ce tour (fronts compris)
        self.corrections: list[str] = []          # toutes : renvoyées à l'IA au tour suivant
        self.corrections_joueur: list[str] = []   # celles que le joueur a le droit de lire
        self.index_nations: dict[str, str] = {}
        for nid, n in etat["nations"].items():
            self.index_nations[_norm(nid)] = nid
            self.index_nations.setdefault(_norm(n["nom"]), nid)
        self.index_terr = {t.casefold(): t for t in etat["territoires"]}
        for t, nom in noms_terr.items():
            self.index_terr.setdefault(_norm(nom), t)

    def corr(self, texte: str, prive: bool = False):
        """`prive` : la correction révélerait quelque chose que le joueur ne doit pas savoir."""
        self.corrections.append(texte)
        if not prive:
            self.corrections_joueur.append(texte)

    def implique_joueur(self, *nations) -> bool:
        return self.etat["nation_joueur"] in nations

    def nation(self, v, contexte: str, vivante: bool = False, prive: bool = False) -> str | None:
        nid = self.index_nations.get(_norm(v)) if isinstance(v, str) else None
        if nid is None:
            self.corr(f"{contexte} : nation inconnue « {_cite(v)} », ignorée.", prive)
        elif vivante and est_disparue(self.etat, nid):
            self.corr(f"{contexte} : la nation « {self.etat['nations'][nid]['nom']} » n'a plus de territoire, ignorée.", prive)
            return None
        return nid

    def territoire(self, v, contexte: str, prive: bool = False) -> str | None:
        t = None
        if isinstance(v, str):
            t = self.index_terr.get(v.strip().casefold()) or self.index_terr.get(_norm(v))
        if t is None or t not in self.etat["territoires"]:
            self.corr(f"{contexte} : territoire inconnu « {_cite(v)} », ignoré.", prive)
            return None
        return t

    # -- les parties de la réponse
    def evenements(self, bruts: list, debut: str, fin: str) -> list[dict]:
        res = []
        for ev in bruts:
            pays, inconnus = [], []
            for v in _liste_textes(ev.get("pays")):
                nid = self.index_nations.get(_norm(v))
                if nid is None:
                    inconnus.append(v)
                elif nid not in pays:
                    pays.append(nid)
            titre = " ".join(str(ev.get("titre") or "").split())[:160]
            texte = str(ev.get("texte") or "").strip()[:1500]
            # Prudence : un modèle écrit parfois « (secret) » dans le titre en laissant secret à false.
            secret = _secret(ev.get("secret")) or bool(MOTS_SECRET.search(titre + " " + texte))
            titre = MENTION_SECRET.sub("", titre).strip() or titre
            # un événement secret qui n'implique pas le joueur ne doit pas fuiter par une correction
            prive = secret and not self.implique_joueur(*pays)
            for v in inconnus:
                self.corr(f"Événement « {_cite(titre)[:40]} » : nation inconnue « {_cite(v)} », ignorée.", prive)
            d = ev.get("date")
            try:
                d = date.fromisoformat(str(d).strip()[:10]).isoformat()
            except ValueError:
                d = fin
            d = max(debut, min(fin, d))
            if not titre:
                continue
            res.append({"tour": self.etat["tour"] + 1, "date": d, "titre": titre,
                        "texte": texte, "pays": pays, "secret": secret})
        res.sort(key=lambda e: e["date"])
        return res

    def chiffres(self, bruts: list):
        """Les variations d'une même nation et d'un même chiffre sont CUMULÉES, puis le cumul est borné."""
        cumul: dict[tuple[str, str], int] = {}
        for c in bruts:
            nid = self.nation(c.get("nation"), "Variation de chiffre", vivante=True)
            cle = next((k for k in CHIFFRES if _norm(c.get("chiffre")) == _norm(k)
                        or _norm(c.get("chiffre")) == _norm(LIBELLES_CHIFFRES[k])), None)
            v = _entier(c.get("variation"))
            if nid is None:
                continue
            if cle is None or v is None:
                self.corr(f"Variation de chiffre de {self.etat['nations'][nid]['nom']} : chiffre ou valeur illisible, ignorée.")
                continue
            cumul[(nid, cle)] = cumul.get((nid, cle), 0) + v
        # 1. plafond par chiffre (après cumul), 2. hausse divisée par deux au-dessus de 90,
        # 3. coût : la hausse nette d'une nation ne dépasse pas le plafond d'un seul chiffre.
        par_nation: dict[str, dict[str, int]] = {}
        for (nid, cle), v in cumul.items():
            n = self.etat["nations"][nid]
            nom = n["nom"]
            borne = _borner(v, -self.p["chiffre"], self.p["chiffre"])
            if borne != v:
                self.corr(f"{LIBELLES_CHIFFRES[cle]} de {nom} : {v:+d} au total ramené à "
                          f"{borne:+d} (plafond de ±{self.p['chiffre']} pour ce tour).")
            if borne > 0 and n[cle] > SEUIL_RENDEMENT:
                moitie = borne // 2
                self.corr(f"{LIBELLES_CHIFFRES[cle]} de {nom} : {borne:+d} ramené à {moitie:+d} "
                          f"(au-dessus de {SEUIL_RENDEMENT}, une hausse est divisée par deux).")
                borne = moitie
            par_nation.setdefault(nid, {})[cle] = borne
        for nid, deltas in par_nation.items():
            nom = self.etat["nations"][nid]["nom"]
            hausses = {c: d for c, d in deltas.items() if d > 0}
            baisses = -sum(d for d in deltas.values() if d < 0)
            permis = self.p["chiffre"] + baisses            # hausses totales permises : net <= plafond
            total = sum(hausses.values())
            if total > permis:
                net = total - baisses
                nouveau = _repartir(hausses, permis)
                self.corr(f"{nom} : hausse nette de {net:+d} au total ramenée à {self.p['chiffre']:+d} "
                          f"(tout effort a un coût ; plafond de {self.p['chiffre']} pour ce tour).")
                deltas.update(nouveau)
            n = self.etat["nations"][nid]
            for cle, d in deltas.items():
                n[cle] = _borner(n[cle] + d, 0, 100)

    def relations(self, bruts: list):
        """Même principe : cumul par paire de nations, puis plafond."""
        cumul: dict[str, int] = {}
        for r in bruts:
            a = self.nation(r.get("nation_a"), "Variation de relation", vivante=True)
            b = self.nation(r.get("nation_b"), "Variation de relation", vivante=True)
            v = _entier(r.get("variation"))
            if a is None or b is None:
                continue
            nom = f"{self.etat['nations'][a]['nom']} / {self.etat['nations'][b]['nom']}"
            if a == b or v is None:
                self.corr(f"Relation {nom} : demande illisible, ignorée.", not self.implique_joueur(a, b))
                continue
            cle = cle_relation(a, b)
            cumul[cle] = cumul.get(cle, 0) + v
        for cle, v in cumul.items():
            a, b = cle.split("|")
            nom = f"{self.etat['nations'][a]['nom']} / {self.etat['nations'][b]['nom']}"
            borne = _borner(v, -self.p["relation"], self.p["relation"])
            if borne != v:
                self.corr(f"Relation {nom} : {v:+d} au total ramené à {borne:+d} (plafond de ±{self.p['relation']} pour ce tour).",
                          not self.implique_joueur(a, b))
            self.etat["relations"][cle] = _borner(self.etat["relations"].get(cle, 0) + borne, -100, 100)

    def declarations(self, bruts: list, debut: str):
        for g in bruts:
            if _norm(g.get("action")).startswith("decl"):
                camps = []
                for cle in ("camp_a", "camp_b"):
                    ids = []
                    for v in _liste_textes(g.get(cle)):
                        nid = self.nation(v, "Déclaration de guerre", vivante=True)
                        if nid and nid not in ids:
                            ids.append(nid)
                    camps.append(ids)
                if not camps[0] or not camps[1] or set(camps[0]) & set(camps[1]):
                    self.corr("Déclaration de guerre : camps vides ou qui se recoupent, ignorée.")
                    continue
                if all(en_guerre(self.etat, x, y) for x in camps[0] for y in camps[1]):
                    continue
                nom = " ".join(str(g.get("nom") or "").split())[:100] or "Guerre"
                self.etat["guerres"].append({"nom": nom, "camp_a": camps[0], "camp_b": camps[1], "depuis": debut})

    def paix(self, bruts: list, evenements: list[dict]):
        """Une paix n'est appliquée que si un événement du tour la raconte en citant les deux camps."""
        for g in bruts:
            if not _norm(g.get("action")).startswith("paix"):
                continue
            nom = _norm(g.get("nom"))
            ids = {self.index_nations.get(_norm(v)) for v in _liste_textes(g.get("camp_a")) + _liste_textes(g.get("camp_b"))} - {None}
            trouvee = None
            for w in self.etat["guerres"]:
                if (nom and _norm(w["nom"]) == nom) or (ids and ids <= set(w["camp_a"]) | set(w["camp_b"])
                                                         and ids & set(w["camp_a"]) and ids & set(w["camp_b"])):
                    trouvee = w
                    break
            if trouvee is None:
                self.corr(f"Paix « {_cite(g.get('nom') or '?')} » : aucune guerre correspondante, ignorée.")
                continue
            raconte = any(set(e["pays"]) & set(trouvee["camp_a"]) and set(e["pays"]) & set(trouvee["camp_b"])
                          for e in evenements)
            if not raconte:
                self.corr(f"Paix « {_cite(trouvee['nom'])} » refusée : aucun événement du tour ne la raconte en citant "
                          "les nations des deux camps dans « pays ». La guerre continue.",
                          not self.implique_joueur(*trouvee["camp_a"], *trouvee["camp_b"]))
                continue
            self.etat["guerres"].remove(trouvee)

    def fronts(self, bruts: list, avant: list[dict]):
        """Les fronts : une entrée par guerre en cours. Les territoires pris passent par `transferer`
        (même plafond que les transferts ordinaires)."""
        vus: set[int] = set()
        resultats = []
        for f in bruts:
            nom = _norm(f.get("guerre"))
            g = next((w for w in self.etat["guerres"] if _norm(w["nom"]) == nom), None) if nom else None
            if g is None:
                self.corr(f"Front « {_cite(f.get('guerre') or '?')} » : aucune guerre en cours de ce nom, ignoré.")
                continue
            vus.add(id(g))
            prive = not self.implique_joueur(*g["camp_a"], *g["camp_b"])
            av = _norm(f.get("avance"))
            explication = " ".join(str(f.get("explication") or "").split())[:400]
            pris = []
            if av not in ("a", "b"):
                if av not in ("", "aucun", "aucune", "non"):
                    self.corr(f"Front « {_cite(g['nom'])} » : « avance » doit être a, b ou aucun (« {_cite(f.get('avance'))} »), traité comme aucun.", prive)
                if _liste_textes(f.get("territoires_pris")):
                    self.corr(f"Front « {_cite(g['nom'])} » : des territoires sont pris alors que personne n'avance, ignorés.", prive)
                resultats.append({"guerre": g["nom"], "avance": "aucun", "territoires_pris": [], "explication": explication})
                continue
            gagnant, perdant = (g["camp_a"], g["camp_b"]) if av == "a" else (g["camp_b"], g["camp_a"])
            vivants = [n for n in gagnant if n in self.etat["nations"] and not est_disparue(self.etat, n)]
            par = self.index_nations.get(_norm(f.get("par"))) if isinstance(f.get("par"), str) else None
            if par not in vivants:
                if _liste_textes(f.get("territoires_pris")) and f.get("par"):
                    self.corr(f"Front « {_cite(g['nom'])} » : « {_cite(f.get('par'))} » n'est pas une nation vivante du camp qui avance, "
                              "territoires attribués à la première nation de ce camp.", prive)
                par = vivants[0] if vivants else None
            for v in _liste_textes(f.get("territoires_pris")):
                if par is None:
                    break
                ctx = f"Front « {_cite(g['nom'])} », territoire « {_cite(self.noms_terr.get(v, v))} »"
                terr = self.territoire(v, ctx, prive)
                if terr is None:
                    continue
                ancien = self.etat["territoires"][terr]
                if ancien not in perdant:
                    nom_ancien = self.etat["nations"][ancien]["nom"]
                    self.corr(f"{ctx} refusé : il appartient à {nom_ancien}, qui n'est pas dans le camp qui recule.", prive)
                    continue
                pourquoi = self.conquete_totale_refusee(ancien, vivants)
                if pourquoi:
                    self.corr(f"{ctx} refusé : {pourquoi}", prive)
                    continue
                if self.transferer(terr, par, ctx, prive):
                    pris.append(terr)
            resultats.append({"guerre": g["nom"], "avance": av, "territoires_pris": pris, "explication": explication})
        for g in self.etat["guerres"]:
            if any(g is w for w in avant) and id(g) not in vus:
                self.corr(f"Guerre « {_cite(g['nom'])} » : absente de « fronts » (une entrée par guerre en cours est obligatoire), front figé.",
                          not self.implique_joueur(*g["camp_a"], *g["camp_b"]))
        return resultats

    def conquete_totale_refusee(self, victime: str, attaquants: list[str]) -> str | None:
        """Une nation ne perd son DERNIER territoire que submergée : armées des attaquants au moins
        double de la sienne. Sinon un pays d'un seul territoire (Chine, Pologne…) tombait d'un coup
        (constaté sur thnas : la Chine prise en un mois)."""
        if len(territoires_de(self.etat, victime)) > 1:
            return None
        force = sum(self.etat["nations"][n]["armee"] for n in attaquants if n in self.etat["nations"])
        defense = self.etat["nations"][victime]["armee"]
        if force >= 2 * defense:
            return None
        nom = self.etat["nations"][victime]["nom"]
        return (f"c'est le dernier territoire de {nom}, qui ne peut être conquise que par des armées au moins "
                f"deux fois plus fortes (attaque {force}, défense {defense}) ; le front avance sans conquête totale.")

    def transferer(self, terr: str, dest: str, ctx: str, prive: bool) -> bool:
        """Applique un transfert déjà validé, dans la limite du plafond du tour (partagé par tous les chemins)."""
        if self.transferts >= self.p["transferts"]:
            nom_dest = self.etat["nations"][dest]["nom"] if dest in self.etat["nations"] else dest
            self.corr(f"{ctx} vers {nom_dest} refusé : plafond de {self.p['transferts']} transferts atteint pour ce tour.", prive)
            return False
        self.etat["territoires"][terr] = dest
        self.transferts += 1
        return True

    def territoires(self, bruts: list, nouvelle: dict | None, evenements: list[dict]):
        """Transferts, dans l'ordre donné, jusqu'au plafond. Chaque refus est une correction.

        Un refus entre deux nations dont aucune n'est celle du joueur reste caché au joueur (il pourrait
        révéler un conflit ou un traité qu'il ne connaît pas)."""
        nouvelle_id = None
        if nouvelle is not None:
            nom = " ".join(str(nouvelle.get("nom") or "").split())[:80]
            if not nom:
                self.corr("Nouvelle nation : nom manquant, ignorée.")
                nouvelle = None
            else:
                nouvelle = dict(nouvelle, nom=nom)
                nouvelle_id = _slug(nom)
                while nouvelle_id in self.etat["nations"]:
                    nouvelle_id += "-2"
        demandes = [dict(t) for t in bruts]
        if nouvelle is not None:
            for v in _liste_textes(nouvelle.get("territoires")):
                demandes.append({"territoire": v, "vers": nouvelle_id, "base": "indépendance"})
        cree = False
        for d in demandes:
            brut_t = d.get("territoire")
            nomt = self.noms_terr.get(brut_t, brut_t) if isinstance(brut_t, str) else brut_t
            ctx = f"Transfert de « {_cite(nomt)} »"
            terr = self.territoire(brut_t, ctx)
            if terr is None:
                continue
            vers = d.get("vers")
            ancien = self.etat["territoires"][terr]
            if nouvelle_id and (vers == nouvelle_id or _norm(vers) == _norm(nouvelle["nom"])):
                dest = nouvelle_id
            else:
                dest = self.nation(vers, ctx, vivante=True, prive=not self.implique_joueur(ancien))
                if dest is None:
                    continue
            nom_ancien = self.etat["nations"][ancien]["nom"]
            nom_dest = nouvelle["nom"] if dest == nouvelle_id else self.etat["nations"][dest]["nom"]
            prive = not self.implique_joueur(ancien, dest)
            if ancien == dest:
                self.corr(f"{ctx} : appartient déjà à {nom_dest}, ignoré.", prive)
                continue
            base = _norm(d.get("base"))
            if base.startswith("guerre"):
                ok = en_guerre(self.etat, ancien, dest)
                pourquoi = f"{nom_ancien} et {nom_dest} ne sont pas en guerre"
                if ok:
                    camp = {n for w in self.etat["guerres"] for c, o in ((w["camp_a"], w["camp_b"]), (w["camp_b"], w["camp_a"]))
                            if dest in c and ancien in o for n in c if not est_disparue(self.etat, n)}
                    refus = self.conquete_totale_refusee(ancien, sorted(camp) or [dest])
                    ok, pourquoi = (False, refus.rstrip(".")) if refus else (True, pourquoi)
            elif base.startswith(("traite", "annex")):
                ok = any(ancien in e["pays"] and dest in e["pays"] for e in evenements)
                pourquoi = f"aucun événement du tour ne décrit le traité ou l'annexion entre {nom_ancien} et {nom_dest}"
            elif base.startswith("independ"):
                ok = dest == nouvelle_id
                pourquoi = "l'indépendance exige une nouvelle nation (une seule par tour)"
            else:
                ok = False
                pourquoi = "la base du transfert (guerre, traité, annexion, indépendance) est inconnue"
            if not ok:
                self.corr(f"{ctx} vers {nom_dest} refusé : {pourquoi}.", prive)
                continue
            if self.transferts >= self.p["transferts"]:
                self.corr(f"{ctx} vers {nom_dest} refusé : plafond de {self.p['transferts']} transferts atteint pour ce tour.", prive)
                continue
            if dest == nouvelle_id and not cree:
                self._creer_nation(nouvelle_id, nouvelle)
                cree = True
            self.etat["territoires"][terr] = dest
            self.transferts += 1
        if nouvelle is not None and not cree:
            self.corr(f"Nouvelle nation « {_cite(nouvelle.get('nom'))} » : aucun territoire n'a pu lui être donné, non créée.")

    def _creer_nation(self, nid: str, brut: dict):
        couleur = str(brut.get("couleur") or "")
        depart = dict(CHIFFRES_DEFAUT)
        self.etat["nations"][nid] = {
            "nom": " ".join(str(brut["nom"]).split())[:80],
            "couleur": couleur if COULEUR.match(couleur) else couleur_par_defaut(nid),
            "dirigeant": " ".join(str(brut.get("dirigeant") or "").split())[:80],
            "regime": " ".join(str(brut.get("regime") or "").split())[:120],
            "majeure": False, "mineure": True, **depart, "depart": dict(depart)}
        self.index_nations[_norm(nid)] = nid
        self.index_nations.setdefault(_norm(self.etat["nations"][nid]["nom"]), nid)


def appliquer(etat: dict, reponse: dict, noms_terr: dict[str, str], ordres: list[str],
              duree: str) -> tuple[dict, list[str]]:
    """Renvoie (nouvel état, corrections). L'état reçu n'est pas modifié."""
    neuf = copy.deepcopy(etat)
    neuf.pop("historique", None)
    debut = etat["date"]
    fin = ajouter_duree(debut, duree)
    a = Application(neuf, noms_terr, duree)
    evenements = a.evenements(reponse.get("evenements") or [], debut, fin)
    a.chiffres(reponse.get("chiffres") or [])
    a.relations(reponse.get("relations") or [])
    avant_guerres = list(neuf["guerres"])                    # les guerres que la requête a listées
    a.declarations(reponse.get("guerres") or [], debut)
    fronts = a.fronts(reponse.get("fronts") or [], avant_guerres)
    nouvelle = reponse.get("nouvelle_nation")
    a.territoires(reponse.get("territoires") or [], nouvelle if isinstance(nouvelle, dict) else None, evenements)
    a.paix(reponse.get("guerres") or [], evenements)
    # issue de chaque ordre
    issues = []
    donnees = {}
    for o in reponse.get("ordres") or []:
        n = _entier(o.get("numero"))
        if n is not None and 1 <= n <= len(ordres) and n not in donnees:
            donnees[n] = o
    for i, texte in enumerate(ordres, 1):
        o = donnees.get(i)
        issue = _issue(o.get("issue")) if o else None
        if o is None:
            a.corr(f"Ordre {i} : l'IA n'a donné aucune issue.")
        elif issue is None:
            a.corr(f"Ordre {i} : issue « {_cite(o.get('issue'))} » non reconnue.")
        issues.append({"numero": i, "ordre": texte, "issue": issue,
                       "explication": str((o or {}).get("explication") or "").strip()[:800]})
    tour = etat["tour"] + 1
    neuf["tour"] = tour
    neuf["date"] = fin
    neuf["journal"] = neuf["journal"] + evenements
    neuf["histoire"] = neuf["histoire"] + [{
        "tour": tour, "du": debut, "au": fin, "duree": duree,
        "resume": " ".join(str(reponse.get("resume") or "").split())[:2000], "ordres": list(ordres)}]
    for f in reponse.get("faits") or []:
        f = " ".join(str(f).split())[:300]
        if f and f not in neuf["faits_etablis"]:
            neuf["faits_etablis"].append(f)
    neuf["corrections"] = a.corrections[:40]                 # pour l'IA au tour suivant
    neuf["corrections_joueur"] = a.corrections_joueur[:40]   # pour l'encart du joueur
    neuf["dernier_tour"] = {"tour": tour, "ordres": list(ordres), "duree": duree, "issues": issues,
                            "fronts": fronts}
    neuf["brouillon"] = None
    return neuf, a.corrections
