from pathlib import Path

import pytest
import yaml

from app.carte import Carte
from app.monde import etat_initial, resume_etat
from app.scenarios import ScenarioInvalide, charger_dossiers, lire_scenario

RACINE = Path(__file__).resolve().parent.parent
CARTE = Carte(RACINE / "donnees" / "pays-110m.json")


def base():
    return {"id": "test", "nom": "Test", "date_depart": "2000-01-01", "description": "d", "contexte": "c",
            "nations": [
                {"id": "a", "nom": "A", "couleur": "#112233", "territoires": ["FRA"]},
                {"id": "b", "nom": "B", "couleur": "#445566", "territoires": ["DEU"]}],
            "relations": [["a", "b", 10]], "guerres": []}


def lire(d):
    return lire_scenario(yaml.safe_dump(d), "test.yaml", CARTE.noms)


def fautes(d):
    with pytest.raises(ScenarioInvalide) as e:
        lire(d)
    return " | ".join(e.value.fautes)


def test_scenario_minimal_valide_et_territoires_restants_en_mineures():
    s = lire(base())
    assert s["nations"]["pays_usa"]["jouable"]
    assert len(s["nations"]) == 2 + len(CARTE.noms) - 2


def test_livres_valides():
    sc, err = charger_dossiers([RACINE / "scenarios"], CARTE.noms)
    assert not err
    assert set(sc) == {"monde-actuel", "seconde-guerre-1939"}


def test_1939_critere_7():
    sc, _ = charger_dossiers([RACINE / "scenarios"], CARTE.noms)
    s = sc["seconde-guerre-1939"]
    etat = etat_initial(s, "france")
    t = etat["territoires"]
    assert t["AUT"] == "allemagne" and t["CZE"] == "allemagne"
    assert t["IND"] == "royaume-uni" and t["UKR"] == "urss" and t["POL"] == "pologne"
    assert resume_etat(etat, CARTE.noms)


def test_nation_sans_territoire():
    d = base()
    d["nations"][1]["territoires"] = []
    assert "territoire" in fautes(d)


def test_territoire_inconnu():
    d = base()
    d["nations"][1]["territoires"] = ["ZZZ"]
    assert "ZZZ" in fautes(d)


def test_territoire_en_double():
    d = base()
    d["nations"][1]["territoires"] = ["FRA"]
    assert "FRA" in fautes(d)


def test_relation_vers_nation_inconnue():
    d = base()
    d["relations"] = [["a", "zzz", 5]]
    assert "zzz" in fautes(d)


def test_fautes_cumulees():
    d = base()
    d["nations"][0]["territoires"] = ["ZZZ"]
    d["relations"] = [["a", "q", 500]]
    assert len(lire_faute_liste(d)) >= 2


def lire_faute_liste(d):
    with pytest.raises(ScenarioInvalide) as e:
        lire(d)
    return e.value.fautes


def test_yaml_casse_ecarte_sans_bloquer_les_autres(tmp_path):
    (tmp_path / "casse.yaml").write_text("id: [pas fini\n  : :", encoding="utf-8")
    sc, err = charger_dossiers([RACINE / "scenarios", tmp_path], CARTE.noms)
    assert "monde-actuel" in sc
    assert any("casse.yaml" in e for e in err)


@pytest.mark.parametrize("modif", [
    lambda d: d.update(relations=[[["x"], "a", 1]]),
    lambda d: d.update(guerres=[{"nom": "g", "camp_a": [{"a": 1}], "camp_b": ["b"]}]),
    lambda d: d.update(conseil_nations=[["a"]]),
    lambda d: d.update(ecarts=5),
])
def test_fautes_de_structure_ne_plantent_pas(modif, tmp_path):
    d = base()
    modif(d)
    (tmp_path / "mauvais.yaml").write_text(yaml.safe_dump(d), encoding="utf-8")
    sc, err = charger_dossiers([RACINE / "scenarios", tmp_path], CARTE.noms)
    assert "monde-actuel" in sc and any("mauvais.yaml" in e for e in err)
