"""Lecture et vérification des scénarios (fichiers YAML).

Un fichier fautif est écarté avec un message qui nomme le fichier et la faute ; les autres
scénarios restent jouables. Les territoires qu'aucune nation du scénario ne réclame restent
à leur pays actuel, sous forme de nation mineure aux chiffres par défaut.
"""
from __future__ import annotations

import colorsys
import re
import zlib
from datetime import date, datetime
from pathlib import Path

import yaml

CHIFFRES = ("economie", "armee", "stabilite", "influence")
CHIFFRES_DEFAUT = {"economie": 30, "armee": 25, "stabilite": 50, "influence": 15}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")
PREFIXE_MINEURE = "pays_"


class ScenarioInvalide(Exception):
    def __init__(self, fautes: list[str]):
        super().__init__("; ".join(fautes))
        self.fautes = fautes


def _date(valeur, nom: str, fautes: list[str]) -> str | None:
    if isinstance(valeur, datetime):
        valeur = valeur.date()
    if isinstance(valeur, date):
        return valeur.isoformat()
    if isinstance(valeur, str):
        try:
            return date.fromisoformat(valeur.strip()).isoformat()
        except ValueError:
            pass
    fautes.append(f"{nom} : date invalide (attendu AAAA-MM-JJ)")
    return None


def _entier(valeur, mini: int, maxi: int) -> bool:
    return isinstance(valeur, int) and not isinstance(valeur, bool) and mini <= valeur <= maxi


def couleur_par_defaut(ident: str) -> str:
    """Une couleur sourde et stable pour une nation mineure."""
    h = (zlib.crc32(ident.encode()) % 360) / 360
    r, g, b = colorsys.hls_to_rgb(h, 0.62, 0.28)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def lire_scenario(contenu: str, nom_fichier: str, territoires: dict[str, str]) -> dict:
    """Vérifie un scénario. `territoires` : identifiant de territoire -> nom.

    Renvoie le scénario complet (avec ses nations mineures), ou lève ScenarioInvalide
    avec TOUTES les fautes trouvées.
    """
    try:
        brut = yaml.safe_load(contenu)
    except yaml.YAMLError as e:
        marque = getattr(e, "problem_mark", None)
        ou = f" (ligne {marque.line + 1})" if marque else ""
        raise ScenarioInvalide([f"YAML illisible{ou}"]) from e
    if not isinstance(brut, dict):
        raise ScenarioInvalide(["le fichier doit être un dictionnaire YAML"])

    fautes: list[str] = []

    sid = brut.get("id")
    if not isinstance(sid, str) or not SLUG.match(sid):
        fautes.append("id manquant ou invalide (minuscules, chiffres et tirets)")
        sid = None
    nom = brut.get("nom")
    if not isinstance(nom, str) or not nom.strip():
        fautes.append("nom manquant")
        nom = ""
    date_depart = _date(brut.get("date_depart"), "date_depart", fautes) if "date_depart" in brut else None
    if "date_depart" not in brut:
        fautes.append("date_depart manquante")
    description = str(brut.get("description") or "").strip()
    contexte = str(brut.get("contexte") or "").strip()

    chiffres_defaut = dict(CHIFFRES_DEFAUT)
    cd = brut.get("chiffres_defaut")
    if cd is not None:
        if not isinstance(cd, dict):
            fautes.append("chiffres_defaut doit être un dictionnaire")
        else:
            for k, v in cd.items():
                if k not in CHIFFRES or not _entier(v, 0, 100):
                    fautes.append(f"chiffres_defaut : « {k} » invalide (0 à 100 pour {', '.join(CHIFFRES)})")
                else:
                    chiffres_defaut[k] = v

    # --- nations -------------------------------------------------------------
    nations: dict[str, dict] = {}
    proprietaire: dict[str, str] = {}
    liste = brut.get("nations")
    if not isinstance(liste, list) or not liste:
        fautes.append("nations manquantes (au moins une nation)")
        liste = []
    for i, n in enumerate(liste, 1):
        if not isinstance(n, dict):
            fautes.append(f"nation n°{i} : doit être un dictionnaire")
            continue
        nid = n.get("id")
        etiquette = f"nation « {nid} »" if isinstance(nid, str) else f"nation n°{i}"
        if not isinstance(nid, str) or not SLUG.match(nid):
            fautes.append(f"{etiquette} : id invalide (minuscules, chiffres et tirets)")
            continue
        if nid in nations:
            fautes.append(f"{etiquette} : id en double")
            continue
        nnom = n.get("nom")
        if not isinstance(nnom, str) or not nnom.strip():
            fautes.append(f"{etiquette} : nom manquant")
        coul = n.get("couleur")
        if not isinstance(coul, str) or not COULEUR.match(coul):
            fautes.append(f"{etiquette} : couleur invalide (attendu #rrggbb)")
            coul = "#888888"
        terr = n.get("territoires")
        if not isinstance(terr, list) or not terr:
            fautes.append(f"{etiquette} : aucun territoire")
            terr = []
        valides = []
        for t in terr:
            if not isinstance(t, str) or t not in territoires:
                fautes.append(f"{etiquette} : territoire inconnu « {t} »")
            elif t in proprietaire:
                fautes.append(f"{etiquette} : territoire « {t} » déjà donné à {proprietaire[t]}")
            else:
                proprietaire[t] = nid
                valides.append(t)
        ch = {}
        for c in CHIFFRES:
            v = n.get(c, chiffres_defaut[c])
            if not _entier(v, 0, 100):
                fautes.append(f"{etiquette} : {c} doit être un entier de 0 à 100")
                v = chiffres_defaut[c]
            ch[c] = v
        majeure = n.get("majeure", False)
        jouable = n.get("jouable", True)
        if not isinstance(majeure, bool) or not isinstance(jouable, bool):
            fautes.append(f"{etiquette} : majeure et jouable doivent valoir true ou false")
            majeure, jouable = bool(majeure), bool(jouable)
        nations[nid] = {
            "nom": str(nnom or nid).strip(),
            "couleur": coul.lower(),
            "dirigeant": str(n.get("dirigeant") or "").strip(),
            "regime": str(n.get("regime") or "").strip(),
            "majeure": majeure,
            "jouable": jouable,
            "mineure": False,
            **ch,
            "territoires": valides,
        }

    # --- nations mineures : tout territoire non réclamé garde son pays actuel --------
    for tid, tnom in territoires.items():
        if tid in proprietaire:
            continue
        mid = PREFIXE_MINEURE + tid.lower()
        nations[mid] = {
            "nom": tnom, "couleur": couleur_par_defaut(tid), "dirigeant": "", "regime": "",
            "majeure": False, "jouable": True, "mineure": True, **chiffres_defaut,
            "territoires": [tid],
        }
        proprietaire[tid] = mid

    # --- relations -----------------------------------------------------------
    relations: list[list] = []
    vues: set[frozenset] = set()
    rel = brut.get("relations") or []
    if not isinstance(rel, list):
        fautes.append("relations doit être une liste")
        rel = []
    for r in rel:
        if not (isinstance(r, list) and len(r) == 3):
            fautes.append(f"relation mal formée : {r!r} (attendu [nation, nation, note])")
            continue
        a, b, note = r
        if not (isinstance(a, str) and isinstance(b, str)):
            fautes.append(f"relation mal formée : {r!r} (les nations sont des identifiants)")
            continue
        if a not in nations or b not in nations:
            inconnue = a if a not in nations else b
            fautes.append(f"relation vers une nation inconnue : « {inconnue} »")
            continue
        if a == b:
            fautes.append(f"relation d'une nation avec elle-même : « {a} »")
            continue
        if not _entier(note, -100, 100):
            fautes.append(f"relation {a}/{b} : note invalide (entier de -100 à 100)")
            continue
        paire = frozenset((a, b))
        if paire in vues:
            fautes.append(f"relation {a}/{b} donnée deux fois")
            continue
        vues.add(paire)
        relations.append([a, b, note])

    # --- guerres -------------------------------------------------------------
    guerres: list[dict] = []
    gl = brut.get("guerres") or []
    if not isinstance(gl, list):
        fautes.append("guerres doit être une liste")
        gl = []
    for g in gl:
        if not isinstance(g, dict):
            fautes.append("guerre mal formée (attendu un dictionnaire)")
            continue
        gnom = str(g.get("nom") or "").strip() or "Guerre"
        camps = []
        for cle in ("camp_a", "camp_b"):
            camp = g.get(cle)
            if not isinstance(camp, list) or not camp:
                fautes.append(f"guerre « {gnom} » : {cle} vide ou absent")
                camp = []
            camp = [x for x in camp if isinstance(x, str) or fautes.append(f"guerre « {gnom} » : identifiant de nation invalide « {x!r} »")]
            for nid in camp:
                if nid not in nations:
                    fautes.append(f"guerre « {gnom} » : nation inconnue « {nid} »")
            camps.append([x for x in camp if x in nations])
        if set(camps[0]) & set(camps[1]):
            fautes.append(f"guerre « {gnom} » : une nation est dans les deux camps")
        depuis = _date(g["depuis"], f"guerre « {gnom} » : depuis", fautes) if "depuis" in g else date_depart
        guerres.append({"nom": gnom, "camp_a": camps[0], "camp_b": camps[1], "depuis": depuis})

    # --- règles de simulation ---------------------------------------------------
    regles = []
    rl = brut.get("regles") or []
    if not isinstance(rl, list):
        fautes.append("regles doit être une liste")
        rl = []
    for r in rl:
        if not isinstance(r, dict) or not str(r.get("texte") or "").strip():
            fautes.append(f"règle mal formée : {r!r} (attendu date et texte)")
            continue
        d = _date(r["date"], "règle : date", fautes) if r.get("date") is not None else None
        regles.append({"date": d, "texte": str(r["texte"]).strip()})

    # --- nations conseillées ----------------------------------------------------
    conseil = brut.get("conseil_nations") or []
    if not isinstance(conseil, list):
        fautes.append("conseil_nations doit être une liste")
        conseil = []
    conseil = [n for n in conseil if isinstance(n, str) or fautes.append(f"conseil_nations : identifiant invalide « {n!r} »")]
    for nid in conseil:
        if nid not in nations:
            fautes.append(f"conseil_nations : nation inconnue « {nid} »")
        elif not nations[nid]["jouable"]:
            fautes.append(f"conseil_nations : « {nid} » n'est pas jouable")
    conseil = [n for n in conseil if n in nations and nations[n]["jouable"]]

    ec = brut.get("ecarts") or []
    if not isinstance(ec, list):
        fautes.append("ecarts doit être une liste")
        ec = []
    ecarts = [str(e).strip() for e in ec if str(e).strip()]

    if fautes:
        raise ScenarioInvalide(fautes)
    return {
        "id": sid, "nom": nom.strip(), "date_depart": date_depart, "description": description,
        "contexte": contexte, "chiffres_defaut": chiffres_defaut, "nations": nations,
        "territoires": proprietaire, "relations": relations, "guerres": guerres,
        "regles": regles, "conseil_nations": conseil, "ecarts": ecarts, "fichier": nom_fichier,
    }


def charger_dossiers(dossiers: list[Path], territoires: dict[str, str]) -> tuple[dict[str, dict], list[str]]:
    """Charge tous les scénarios des dossiers. Renvoie (scénarios par id, messages d'erreur)."""
    scenarios: dict[str, dict] = {}
    erreurs: list[str] = []
    for dossier in dossiers:
        if not dossier.is_dir():
            continue
        for chemin in sorted(list(dossier.glob("*.yaml")) + list(dossier.glob("*.yml"))):
            try:
                s = lire_scenario(chemin.read_text(encoding="utf-8"), chemin.name, territoires)
            except ScenarioInvalide as e:
                erreurs.extend(f"{chemin.name} : {f}" for f in e.fautes)
                continue
            except Exception as e:  # un fichier fautif ne doit jamais bloquer les autres
                erreurs.append(f"{chemin.name} : fichier inutilisable ({e.__class__.__name__})")
                continue
            if s["id"] in scenarios:
                erreurs.append(f"{chemin.name} : l'id « {s['id']} » est déjà pris par {scenarios[s['id']]['fichier']}")
                continue
            scenarios[s["id"]] = s
    return scenarios, erreurs
