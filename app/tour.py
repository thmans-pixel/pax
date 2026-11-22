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

# Plafonds par tour : (variation d'un chiffre, variation d'une relation, transferts de territoires)
PLAFONDS = {
    "1sem": (5, 20, 3), "1mois": (5, 20, 3),
    "3mois": (10, 30, 6), "6mois": (10, 30, 6),
    "1an": (15, 40, 10),
}


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
            "nouvelle_nation": {"type": ["object", "null"], "properties": {
                "nom": texte, "dirigeant": texte, "regime": texte, "couleur": texte,
                "territoires": liste_ids}},
            "resume": texte,
            "faits": liste_ids,
        },
        "required": ["evenements", "ordres", "resume"],
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
- Reste réaliste : l'histoire peut dévier de la réalité à cause des ordres du joueur, mais sans miracle.
- Les variations de chiffres et de relations doivent rester modestes et respecter les plafonds donnés.
- Un territoire ne change de mains que par une guerre en cours (« guerre »), un traité ou une \
annexion décrits dans un événement du même tour (« traité », « annexion »), ou une indépendance \
(« indépendance », avec « nouvelle_nation », une seule par tour). Les événements qui impliquent \
deux nations doivent citer les deux dans « pays ».
- Un événement « secret » n'est connu que de ceux qui y participent ; mets les nations concernées \
dans « pays ».
- Les événements ont une date comprise entre le début et la fin du tour (AAAA-MM-JJ).
- « resume » : un paragraphe qui résume tout le tour. « faits » : les faits nouveaux et durables \
à retenir (une phrase chacun).
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
    paliers_reduction = [(TOURS_DETAILLES, len(histoire), False)]
    paliers_reduction += [(0, len(histoire), False)]
    for k in (20, 10, 5, 2, 0):
        if k < len(histoire):
            paliers_reduction.append((0, k, False))
    paliers_reduction.append((0, 0, True))
    for detail, garde, serre in paliers_reduction:
        messages = _assembler(etat, noms_terr, ordres, duree, detail, garde, serre)
        jetons = estimer_jetons(messages)
        if jetons <= budget:
            return messages, {"jetons": jetons, "budget": budget, "detail": detail,
                              "resumes": garde, "serre": serre}
    raise ContexteTropPetit(
        f"Le tour ne tient pas dans le contexte de {num_ctx} jetons (il en faut environ {jetons + RESERVE_REPONSE}). "
        "Augmentez la taille de contexte dans les réglages.")


def _assembler(etat: dict, noms_terr: dict[str, str], ordres: list[str], duree: str,
               nb_detail: int, nb_resumes: int, serre: bool) -> list[dict]:
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
    if regles:
        section("Règles de simulation utiles pour cette période",
                [f"- {(date_fr(r['date']) + ' : ') if r['date'] else ''}{r['texte']}" for r in regles])
    section("Ce tour", [
        f"Début : {date_fr(debut)} ({debut}). Fin : {date_fr(fin)} ({fin}). Durée : {DUREES[duree]['libelle']}.",
        f"Plafonds pour ce tour : un chiffre varie de ±{p['chiffre']} au plus, une relation de "
        f"±{p['relation']} au plus, {p['transferts']} transferts de territoires au plus.",
        f"Tour numéro {etat['tour'] + 1}."])
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
    section("Guerres en cours", [
        f"- {g['nom']} : {', '.join(g['camp_a'])} contre {', '.join(g['camp_b'])}" for g in etat["guerres"]] or ["(aucune)"])
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
                lignes.append(f"    · {ev['titre']}{' (secret)' if ev.get('secret') else ''}")
        section("Histoire récente (du plus ancien au plus récent)", lignes)
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
              "guerres": False, "territoires": False, "faits": False}
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
        self.corrections: list[str] = []
        self.index_nations: dict[str, str] = {}
        for nid, n in etat["nations"].items():
            self.index_nations[_norm(nid)] = nid
            self.index_nations.setdefault(_norm(n["nom"]), nid)
        self.index_terr = {t.casefold(): t for t in etat["territoires"]}
        for t, nom in noms_terr.items():
            self.index_terr.setdefault(_norm(nom), t)

    def corr(self, texte: str):
        self.corrections.append(texte)

    def nation(self, v, contexte: str, vivante: bool = False) -> str | None:
        nid = self.index_nations.get(_norm(v)) if isinstance(v, str) else None
        if nid is None:
            self.corr(f"{contexte} : nation inconnue « {v} », ignorée.")
        elif vivante and est_disparue(self.etat, nid):
            self.corr(f"{contexte} : la nation « {self.etat['nations'][nid]['nom']} » n'a plus de territoire, ignorée.")
            return None
        return nid

    def territoire(self, v, contexte: str) -> str | None:
        t = None
        if isinstance(v, str):
            t = self.index_terr.get(v.strip().casefold()) or self.index_terr.get(_norm(v))
        if t is None or t not in self.etat["territoires"]:
            self.corr(f"{contexte} : territoire inconnu « {v} », ignoré.")
            return None
        return t

    # -- les parties de la réponse
    def evenements(self, bruts: list, debut: str, fin: str) -> list[dict]:
        res = []
        for ev in bruts:
            pays = []
            for v in ev.get("pays") or []:
                nid = self.nation(v, f"Événement « {str(ev.get('titre', ''))[:40]} »")
                if nid and nid not in pays:
                    pays.append(nid)
            d = ev.get("date")
            try:
                d = date.fromisoformat(str(d).strip()[:10]).isoformat()
            except ValueError:
                d = fin
            d = max(debut, min(fin, d))
            titre = " ".join(str(ev.get("titre") or "").split())[:160]
            if not titre:
                continue
            res.append({"tour": self.etat["tour"] + 1, "date": d, "titre": titre,
                        "texte": str(ev.get("texte") or "").strip()[:1500], "pays": pays,
                        "secret": ev.get("secret") is True})
        res.sort(key=lambda e: e["date"])
        return res

    def chiffres(self, bruts: list):
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
            borne = _borner(v, -self.p["chiffre"], self.p["chiffre"])
            if borne != v:
                self.corr(f"{LIBELLES_CHIFFRES[cle]} de {self.etat['nations'][nid]['nom']} : {v:+d} ramené à "
                          f"{borne:+d} (plafond de ±{self.p['chiffre']} pour ce tour).")
            n = self.etat["nations"][nid]
            n[cle] = _borner(n[cle] + borne, 0, 100)

    def relations(self, bruts: list):
        for r in bruts:
            a = self.nation(r.get("nation_a"), "Variation de relation", vivante=True)
            b = self.nation(r.get("nation_b"), "Variation de relation", vivante=True)
            v = _entier(r.get("variation"))
            if a is None or b is None:
                continue
            nom = f"{self.etat['nations'][a]['nom']} / {self.etat['nations'][b]['nom']}"
            if a == b or v is None:
                self.corr(f"Relation {nom} : demande illisible, ignorée.")
                continue
            borne = _borner(v, -self.p["relation"], self.p["relation"])
            if borne != v:
                self.corr(f"Relation {nom} : {v:+d} ramené à {borne:+d} (plafond de ±{self.p['relation']} pour ce tour).")
            cle = cle_relation(a, b)
            self.etat["relations"][cle] = _borner(self.etat["relations"].get(cle, 0) + borne, -100, 100)

    def declarations(self, bruts: list, debut: str):
        for g in bruts:
            if _norm(g.get("action")).startswith("decl"):
                camps = []
                for cle in ("camp_a", "camp_b"):
                    ids = []
                    for v in g.get(cle) or []:
                        nid = self.nation(v, "Déclaration de guerre", vivante=True)
                        if nid and nid not in ids:
                            ids.append(nid)
                    camps.append(ids)
                if not camps[0] or not camps[1] or set(camps[0]) & set(camps[1]):
                    self.corr("Déclaration de guerre : camps vides ou qui se recoupent, ignorée.")
                    continue
                if en_guerre(self.etat, camps[0][0], camps[1][0]):
                    continue
                nom = " ".join(str(g.get("nom") or "").split())[:100] or "Guerre"
                self.etat["guerres"].append({"nom": nom, "camp_a": camps[0], "camp_b": camps[1], "depuis": debut})

    def paix(self, bruts: list):
        for g in bruts:
            if not _norm(g.get("action")).startswith("paix"):
                continue
            nom = _norm(g.get("nom"))
            ids = {self.index_nations.get(_norm(v)) for v in (g.get("camp_a") or []) + (g.get("camp_b") or [])
                   if isinstance(v, str)} - {None}
            trouvee = None
            for w in self.etat["guerres"]:
                if (nom and _norm(w["nom"]) == nom) or (ids and ids <= set(w["camp_a"]) | set(w["camp_b"])
                                                         and ids & set(w["camp_a"]) and ids & set(w["camp_b"])):
                    trouvee = w
                    break
            if trouvee is None:
                self.corr(f"Paix « {g.get('nom') or '?'} » : aucune guerre correspondante, ignorée.")
            else:
                self.etat["guerres"].remove(trouvee)

    def territoires(self, bruts: list, nouvelle: dict | None, evenements: list[dict]):
        """Transferts, dans l'ordre donné, jusqu'au plafond. Chaque refus est une correction."""
        nouvelle_id = None
        if nouvelle is not None:
            nom = " ".join(str(nouvelle.get("nom") or "").split())[:80]
            if not nom:
                self.corr("Nouvelle nation : nom manquant, ignorée.")
                nouvelle = None
            else:
                nouvelle_id = _slug(nom)
                while nouvelle_id in self.etat["nations"]:
                    nouvelle_id += "-2"
        demandes = [dict(t) for t in bruts]
        if nouvelle is not None:
            for v in nouvelle.get("territoires") or []:
                demandes.append({"territoire": v, "vers": nouvelle_id, "base": "indépendance"})
        faits = 0
        cree = False
        for d in demandes:
            nomt = self.noms_terr.get(str(d.get("territoire")), str(d.get("territoire")))
            ctx = f"Transfert de « {nomt} »"
            terr = self.territoire(d.get("territoire"), ctx)
            if terr is None:
                continue
            vers = d.get("vers")
            if nouvelle_id and (vers == nouvelle_id or _norm(vers) == _norm(nouvelle.get("nom"))):
                dest = nouvelle_id
            else:
                dest = self.nation(vers, ctx, vivante=True)
                if dest is None:
                    continue
            ancien = self.etat["territoires"][terr]
            nom_ancien = self.etat["nations"][ancien]["nom"]
            nom_dest = nouvelle["nom"] if dest == nouvelle_id else self.etat["nations"][dest]["nom"]
            if ancien == dest:
                self.corr(f"{ctx} : appartient déjà à {nom_dest}, ignoré.")
                continue
            base = _norm(d.get("base"))
            if base.startswith("guerre"):
                ok = en_guerre(self.etat, ancien, dest)
                pourquoi = f"{nom_ancien} et {nom_dest} ne sont pas en guerre"
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
                self.corr(f"{ctx} vers {nom_dest} refusé : {pourquoi}.")
                continue
            if faits >= self.p["transferts"]:
                self.corr(f"{ctx} vers {nom_dest} refusé : plafond de {self.p['transferts']} transferts atteint pour ce tour.")
                continue
            if dest == nouvelle_id and not cree:
                self._creer_nation(nouvelle_id, nouvelle)
                cree = True
            self.etat["territoires"][terr] = dest
            faits += 1
        if nouvelle is not None and not cree:
            self.corr(f"Nouvelle nation « {nouvelle.get('nom')} » : aucun territoire n'a pu lui être donné, non créée.")

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
    a.declarations(reponse.get("guerres") or [], debut)
    nouvelle = reponse.get("nouvelle_nation")
    a.territoires(reponse.get("territoires") or [], nouvelle if isinstance(nouvelle, dict) else None, evenements)
    a.paix(reponse.get("guerres") or [])
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
            a.corr(f"Ordre {i} : issue « {o.get('issue')} » non reconnue.")
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
    neuf["corrections"] = a.corrections[:40]
    neuf["dernier_tour"] = {"tour": tour, "ordres": list(ordres), "duree": duree, "issues": issues}
    neuf["brouillon"] = None
    return neuf, a.corrections
