"""L'état du monde : création d'une partie, lecture des relations, résumé de la situation.

Tout ici est du Python simple, sans IA : c'est le code qui tient les comptes.
"""
from __future__ import annotations

from datetime import date

VERSION_FORMAT = 1
CHIFFRES = ("economie", "armee", "stabilite", "influence")
LIBELLES_CHIFFRES = {"economie": "Économie", "armee": "Armée", "stabilite": "Stabilité", "influence": "Influence"}
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
# ordre d'affichage : du plus proche au plus hostile
PALIERS = ["allié", "ami", "neutre", "tendu", "hostile"]


def date_fr(iso: str) -> str:
    d = date.fromisoformat(iso)
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{jour} {MOIS[d.month - 1]} {d.year}"


def palier(note: int) -> str:
    if note < -60:
        return "hostile"
    if note < -20:
        return "tendu"
    if note <= 20:
        return "neutre"
    if note <= 60:
        return "ami"
    return "allié"


def cle_relation(a: str, b: str) -> str:
    x, y = sorted((a, b))
    return f"{x}|{y}"


def etat_initial(scenario: dict, nation_joueur: str, objectif: str = "") -> dict:
    """Crée l'état d'une nouvelle partie à partir d'un scénario vérifié."""
    nations = scenario["nations"]
    if nation_joueur not in nations or not nations[nation_joueur]["jouable"]:
        raise ValueError("nation non jouable")
    etat_nations = {}
    for nid, n in nations.items():
        depart = {c: n[c] for c in CHIFFRES}
        etat_nations[nid] = {
            "nom": n["nom"], "couleur": n["couleur"], "dirigeant": n["dirigeant"],
            "regime": n["regime"], "majeure": n["majeure"], "mineure": n["mineure"],
            **depart, "depart": dict(depart),
        }
    return {
        "version_format": VERSION_FORMAT,
        "scenario": {
            "id": scenario["id"], "nom": scenario["nom"], "contexte": scenario["contexte"],
            "regles": scenario["regles"], "description": scenario["description"],
        },
        "nation_joueur": nation_joueur,
        "objectif": objectif.strip(),
        "date_depart": scenario["date_depart"],
        "date": scenario["date_depart"],
        "tour": 0,
        "nations": etat_nations,
        "territoires": dict(scenario["territoires"]),
        "relations": {cle_relation(a, b): note for a, b, note in scenario["relations"]},
        "guerres": [dict(g) for g in scenario["guerres"]],
        "journal": [],
        "corrections": [],
        "corrections_joueur": [],
        "dernier_tour": None,
        "brouillon": None,
        "historique": [],
        "histoire": [],
        "faits_etablis": [],
        "conseiller": [],
        "diplomatie": {},
    }


def evenement_visible(etat: dict, ev: dict) -> bool:
    """Ce que le joueur (et le conseiller, le rapport, les dirigeants) a le droit de savoir :
    les événements publics et ceux qui impliquent la nation du joueur. Le narrateur voit tout."""
    return (not ev.get("secret")) or etat["nation_joueur"] in ev.get("pays", [])


def evenements_visibles(etat: dict) -> list[dict]:
    return [e for e in etat["journal"] if evenement_visible(etat, e)]


def territoires_de(etat: dict, nid: str) -> list[str]:
    return sorted(t for t, n in etat["territoires"].items() if n == nid)


def est_disparue(etat: dict, nid: str) -> bool:
    return not any(n == nid for n in etat["territoires"].values())


def relations_de(etat: dict, nid: str) -> dict[str, list[dict]]:
    """Relations d'une nation avec les autres, classées par palier (les plus fortes d'abord)."""
    par_palier: dict[str, list[dict]] = {p: [] for p in PALIERS}
    for cle, note in etat["relations"].items():
        a, b = cle.split("|")
        if nid not in (a, b):
            continue
        autre = b if a == nid else a
        if autre not in etat["nations"] or est_disparue(etat, autre):
            continue
        par_palier[palier(note)].append(
            {"id": autre, "nom": etat["nations"][autre]["nom"], "note": note})
    for liste in par_palier.values():
        liste.sort(key=lambda r: (-abs(r["note"]), r["nom"]))
    return {p: l for p, l in par_palier.items() if l}


def guerres_de(etat: dict, nid: str) -> list[dict]:
    """Guerres où la nation est engagée, avec les noms des deux camps."""
    res = []
    for g in etat["guerres"]:
        if nid in g["camp_a"] or nid in g["camp_b"]:
            res.append(_guerre_lisible(etat, g))
    return res


def _guerre_lisible(etat: dict, g: dict) -> dict:
    nom = lambda ids: [etat["nations"][i]["nom"] for i in ids if i in etat["nations"]]
    return {"nom": g["nom"], "camp_a": nom(g["camp_a"]), "camp_b": nom(g["camp_b"]),
            "depuis": date_fr(g["depuis"]) if g.get("depuis") else ""}


def fiche_nation(etat: dict, nid: str, noms_territoires: dict[str, str], pour_joueur: bool = False) -> dict:
    """La fiche d'une nation. `pour_joueur` ajoute ce que la nation du joueur sait : sa relation avec elle
    et les guerres où elle est engagée (toutes visibles dans l'onglet État). Jamais d'histoire, de fait
    établi ni d'événement secret."""
    n = etat["nations"][nid]
    terr = territoires_de(etat, nid)
    fiche = {
        "id": nid, "nom": n["nom"], "dirigeant": n["dirigeant"], "regime": n["regime"],
        "majeure": n["majeure"], "couleur": n["couleur"],
        "chiffres": {c: n[c] for c in CHIFFRES},
        "territoires": [noms_territoires.get(t, t) for t in terr],
        "disparue": not terr,
    }
    if pour_joueur:
        fiche["joueur"] = nid == etat["nation_joueur"]
        if nid != etat["nation_joueur"]:
            note = etat["relations"].get(cle_relation(nid, etat["nation_joueur"]), 0)
            fiche["relation"] = {"note": note, "palier": palier(note)}
        fiche["guerres"] = guerres_de(etat, nid)
    return fiche


def resume_etat(etat: dict, noms_territoires: dict[str, str]) -> dict:
    """Tout ce que montre l'onglet État, sans IA."""
    nid = etat["nation_joueur"]
    n = etat["nations"][nid]
    chiffres = []
    for c in CHIFFRES:
        ecart = n[c] - n["depart"][c]
        chiffres.append({"cle": c, "libelle": LIBELLES_CHIFFRES[c], "valeur": n[c], "ecart": ecart})
    return {
        "date": date_fr(etat["date"]),
        "tour": etat["tour"],
        "nation": fiche_nation(etat, nid, noms_territoires),
        "chiffres": chiffres,
        "relations": relations_de(etat, nid),
        "guerres": [_guerre_lisible(etat, g) for g in etat["guerres"]
                    if nid in g["camp_a"] or nid in g["camp_b"]],
        "guerres_monde": [_guerre_lisible(etat, g) for g in etat["guerres"]
                          if nid not in g["camp_a"] and nid not in g["camp_b"]],
        "evenements": [{**e, "date": date_fr(e["date"])} for e in reversed(evenements_visibles(etat)[-5:])],
        "objectif": etat["objectif"],
    }
