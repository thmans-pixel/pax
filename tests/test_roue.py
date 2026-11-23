"""Spec 002, étape 2 — menu roue sur la carte (critères 7 à 10 et 11).

Le comportement dans le navigateur (clic, glisser, appui long, clavier) se vérifie à la main ; ici on prouve
ce qui se teste côté serveur : les données de la fiche (ce que la nation du joueur sait, aucune fuite de
secret) et le fait que le texte n'entre jamais en HTML."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_tour import creer, etat39, noms, sauvegarde  # noqa: F401

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def donnees_page(page: str) -> dict:
    m = re.search(r'<script type="application/json" id="pax-data">(.*?)</script>', page, re.S)
    return json.loads(m.group(1))


# ------------------------------------------------------------------ 7 et 8 : données de la fiche
def test_07_fiche_relation_et_guerres_connues_du_joueur(thibault, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    d = donnees_page(thibault.get(f"/partie/{pid}").texte)
    f = d["fiches"]["allemagne"]
    note = e["relations"].get("allemagne|france", 0)
    assert f["relation"] == {"note": note, "palier": f["relation"]["palier"]} and f["joueur"] is False
    assert set(f["chiffres"]) == {"economie", "armee", "stabilite", "influence"} and f["territoires"]
    assert isinstance(f["guerres"], list)
    # une guerre où l'Allemagne est engagée figure dans sa fiche, avec les noms des camps
    g = e["guerres"][0]
    for nid in g["camp_a"] + g["camp_b"]:
        assert any(x["nom"] == g["nom"] for x in d["fiches"][nid]["guerres"])
    ailleurs = next(n for n in e["nations"] if not any(n in w["camp_a"] + w["camp_b"] for w in e["guerres"]))
    assert d["fiches"][ailleurs]["guerres"] == []


def test_08_son_pays_et_nation_disparue(thibault, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    e["territoires"] = {t: ("allemagne" if n == "italie" else n) for t, n in e["territoires"].items()}
    app.state.sauvegarde.enregistrer("thibault", e)
    d = donnees_page(thibault.get(f"/partie/{pid}").texte)
    assert d["joueur"] == "france"
    assert d["fiches"]["france"]["joueur"] is True and "relation" not in d["fiches"]["france"]   # pas de « Parler »
    assert d["fiches"]["italie"]["disparue"] is True                                              # seulement « Fiche »
    page = thibault.get(f"/partie/{pid}").texte
    assert '/static/roue.js' in page


def test_07_aucun_secret_dans_les_fiches(thibault, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    e["journal"] += [{"tour": 1, "date": "1939-09-05", "titre": "PACTE-NOIR-ALPHA", "texte": "Berlin et Moscou.",
                      "pays": ["allemagne", "urss"], "secret": True}]
    e["histoire"] += [{"tour": 1, "du": "1939-09-01", "au": "1939-10-01", "duree": "1mois",
                       "resume": "RESUME-SECRET-GAMMA", "ordres": ["x"]}]
    e["faits_etablis"] += ["FAIT-SECRET-DELTA"]
    e["corrections"] = ["CORRECTION-SECRETE-EPSILON"]
    e["conseiller"] = [{"de": "joueur", "texte": "CONSEIL-PRIVE", "tour": 0, "date": e["date"]}]
    e["relations"]["allemagne|urss"] = 55                     # une relation entre deux autres nations : pas pour la fiche
    app.state.sauvegarde.enregistrer("thibault", e)
    d = donnees_page(thibault.get(f"/partie/{pid}").texte)
    flux = json.dumps(d, ensure_ascii=False)
    for interdit in ("PACTE-NOIR-ALPHA", "RESUME-SECRET-GAMMA", "FAIT-SECRET-DELTA", "CORRECTION-SECRETE-EPSILON", "CONSEIL-PRIVE"):
        assert interdit not in flux
    assert d["fiches"]["urss"]["relation"]["note"] == e["relations"].get("france|urss", 0)    # la sienne, pas 55
    assert "Tenir" not in flux                                # l'objectif reste dans l'onglet État, pas dans la carte
    assert all(set(f) <= {"id", "nom", "dirigeant", "regime", "majeure", "couleur", "chiffres", "territoires", "disparue",
                          "joueur", "relation", "guerres"} for f in d["fiches"].values())


def test_07_ecran_de_choix_sans_relation(thibault):
    # l'écran de choix de nation n'a pas encore de joueur : aucune relation inventée
    r = thibault.get("/nouvelle/seconde-guerre-1939")
    assert r.status == 200
    d = donnees_page(r.texte)
    assert d["fiches"] and all("relation" not in f and "guerres" not in f for f in d["fiches"].values())


# ------------------------------------------------------------------ 9 et 10 : le code JavaScript
@pytest.mark.parametrize("nom", ["roue.js", "carte.js", "aides.js"])
def test_10_aucun_html_construit_avec_des_donnees(nom):
    js = (STATIC / nom).read_text(encoding="utf-8")
    for interdit in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert interdit not in js, f"{interdit} dans {nom}"


def test_10_roue_texte_par_textcontent():
    js = (STATIC / "roue.js").read_text(encoding="utf-8")
    assert js.count("textContent") >= 3 and "createElement('button')" in js


def test_09_roue_comportements_attendus_dans_le_code():
    """Garde-fou de lecture : la vérification réelle se fait dans le navigateur (voir la spec)."""
    js = (STATIC / "roue.js").read_text(encoding="utf-8")
    assert "'Escape'" in js and "'Tab'" in js and "DELAI_LONG = 500" in js and "SEUIL" in js
    assert "'Envers '" in js and "Que penses-tu de " in js
    assert "pax:pays" in (STATIC / "carte.js").read_text(encoding="utf-8")
    # clic et glisser : la roue n'est annoncée que si le pointeur n'a pas bougé
    carte = (STATIC / "carte.js").read_text(encoding="utf-8")
    assert "if (bouge) return;" in carte


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
@pytest.mark.parametrize("nom", ["roue.js", "carte.js", "aides.js"])
def test_syntaxe_javascript(nom):
    r = subprocess.run(["node", "--check", str(STATIC / nom)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
