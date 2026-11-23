"""Étape 2 — le tour : critères 9 à 17 (avec le faux Ollama)."""
import copy
import json
import re
import time

import pytest

from app import tour as moteur
from app.monde import etat_initial
from app.scenarios import charger_dossiers
from tests.faux_ollama import FauxOllama
from tests.test_web import ORIG, creer


# ------------------------------------------------------------------ outils
@pytest.fixture
def faux(app):
    with FauxOllama(["m"]) as f:
        app.state.reglages.ecrire({"ollama_adresse": f.adresse, "modele": "m", "contexte": 16384})
        yield f


def reponse(n=1, **plus):
    base = {
        "evenements": [{"date": "1939-09-10", "titre": "Mobilisation en France", "texte": "La France mobilise.",
                        "pays": ["france"], "secret": False}],
        "ordres": [{"numero": i, "issue": "réussi", "explication": f"L'ordre {i} aboutit, malgré les réticences du Parlement et de l'état-major."} for i in range(1, n + 1)],
        "chiffres": [], "relations": [], "guerres": [], "territoires": [], "nouvelle_nation": None,
        "resume": "Un mois de mobilisation.", "faits": ["La France a mobilisé."],
    }
    base.update(plus)
    return base


def avancer(client, pid, ordres=("Mobiliser l'armée",), duree="1mois"):
    r = client.post(f"/partie/{pid}/tour", json_={"ordres": list(ordres), "duree": duree}, entetes=ORIG)
    return r


def attendre(client, pid, delai=15):
    """Interroge la progression jusqu'à la fin du tour ; renvoie le dernier état connu."""
    fin = time.time() + delai
    while time.time() < fin:
        d = client.get(f"/partie/{pid}/tour").json()
        if d["etat"] in ("termine", "echec", "aucun"):
            return d
        time.sleep(0.05)
    raise AssertionError("le tour ne finit pas")


def jouer(client, pid, faux, rep, **kw):
    faux.programmer(rep)
    assert avancer(client, pid, **kw).status == 202
    return attendre(client, pid)


def sauvegarde(app, pid, user="thibault"):
    return app.state.sauvegarde.lire(user, pid)


@pytest.fixture
def noms(app):
    return app.state.carte.noms


@pytest.fixture
def etat39(app):
    s, _ = charger_dossiers(app.state.config.scenarios, app.state.carte.noms)
    return etat_initial(s["seconde-guerre-1939"], "france", "Tenir")


# ------------------------------------------------------------------ 9
def test_9_une_requete_et_date_exacte(thibault, faux, app):
    pid = creer(thibault)
    d = jouer(thibault, pid, faux, reponse(3), ordres=["A", "B", "C"], duree="1mois")
    assert d["etat"] == "termine"
    assert len(faux.requetes) == 1                                   # une seule requête
    e = sauvegarde(app, pid)
    assert e["date"] == "1939-10-01" and e["tour"] == 1
    req = faux.requetes[0]
    assert req["stream"] is True and req["options"]["num_ctx"] == 16384 and "properties" in req["format"]
    corps = json.dumps(req, ensure_ascii=False)
    assert "thibault" not in corps and "1. A" in corps and "3. C" in corps   # ni identifiant, ordres numérotés


def test_9_durees():
    assert moteur.ajouter_duree("1939-09-01", "1sem") == "1939-09-08"
    assert moteur.ajouter_duree("1939-09-01", "1mois") == "1939-10-01"
    assert moteur.ajouter_duree("1939-01-31", "1mois") == "1939-02-28"
    assert moteur.ajouter_duree("1939-12-15", "1mois") == "1940-01-15"
    assert moteur.ajouter_duree("1939-09-01", "3mois") == "1939-12-01"
    assert moteur.ajouter_duree("1939-09-01", "6mois") == "1940-03-01"
    assert moteur.ajouter_duree("1939-09-01", "1an") == "1940-09-01"
    assert moteur.ajouter_duree("1940-02-29", "1an") == "1941-02-28"


def test_9_ordres_de_1_a_10(thibault, faux):
    pid = creer(thibault)
    assert avancer(thibault, pid, ordres=[]).status == 400
    assert avancer(thibault, pid, ordres=["  "]).status == 400
    assert avancer(thibault, pid, ordres=[str(i) for i in range(11)]).status == 400
    assert avancer(thibault, pid, duree="2ans").status == 400
    assert thibault.post(f"/partie/{pid}/tour", json_={"ordres": ["x"], "duree": "1mois"},
                         entetes={"Origin": "http://evil.example"}).status == 403
    assert len(faux.requetes) == 0
    d = jouer(thibault, pid, faux, reponse(10), ordres=[f"ordre {i}" for i in range(10)])
    assert d["etat"] == "termine"


# ------------------------------------------------------------------ 10
def test_10_progression_visible_et_pas_d_abandon_tant_que_ca_envoie(thibault, faux, app):
    app.state.config.extras["delai_silence"] = 0.6
    faux.pause, faux.morceau = 0.1, 40                    # plus de 0,6 s au total, jamais 0,6 s de silence
    texte = json.dumps(reponse(1), ensure_ascii=False)
    assert len(texte) > 400
    pid = creer(thibault)
    faux.programmer(texte)
    assert avancer(thibault, pid).status == 202
    vus = []
    fin = time.time() + 15
    while time.time() < fin:
        d = thibault.get(f"/partie/{pid}/tour").json()
        vus.append(d)
        if d["etat"] in ("termine", "echec"):
            break
        time.sleep(0.05)
    assert vus[-1]["etat"] == "termine", vus[-1]
    assert any(d["etat"] == "ecriture" and d["mots"] > 0 and "secondes" in d for d in vus)
    assert all("apercu" not in d for d in vus)            # le texte reçu (secrets compris) n'est jamais montré


def test_10_abandon_apres_silence(thibault, faux, app):
    app.state.config.extras["delai_silence"] = 0.4
    faux.silence = 1.5
    pid = creer(thibault)
    avant = sauvegarde(app, pid)
    d = jouer(thibault, pid, faux, reponse(1))
    assert d["etat"] == "echec" and "plus rien envoyé" in d["message"]
    apres = sauvegarde(app, pid)
    assert apres["tour"] == 0 and apres["date"] == avant["date"]
    assert apres["brouillon"]["ordres"] == ["Mobiliser l'armée"]


# ------------------------------------------------------------------ 11
def test_11_reponse_valide_appliquee(thibault, faux, app):
    pid = creer(thibault)
    rep = reponse(
        2,
        ordres=[{"numero": 1, "issue": "réussi", "explication": "Les troupes sont prêtes."},
                {"numero": 2, "issue": "partiel", "explication": "Le Parlement hésite."}],
        chiffres=[{"nation": "france", "chiffre": "armee", "variation": 4, "raison": "mobilisation"}],
        relations=[{"nation_a": "france", "nation_b": "royaume-uni", "variation": 10, "raison": "front commun"}],
        guerres=[{"action": "déclaration", "nom": "Guerre de Pologne", "camp_a": ["france"], "camp_b": ["allemagne"]}],
        territoires=[{"territoire": "AUT", "vers": "france", "base": "guerre", "raison": "offensive"}])
    d = jouer(thibault, pid, faux, rep, ordres=["Mobiliser", "Voter les crédits"])
    assert d["etat"] == "termine"
    e = sauvegarde(app, pid)
    avant = etat_initial_de(app, "france")
    assert e["nations"]["france"]["armee"] == avant["nations"]["france"]["armee"] + 4
    cle = "france|royaume-uni"
    assert e["relations"][cle] == avant["relations"].get(cle, 0) + 10
    assert any(g["nom"] == "Guerre de Pologne" for g in e["guerres"])
    assert e["territoires"]["AUT"] == "france"
    assert [x["titre"] for x in e["journal"]] == ["Mobilisation en France"]
    page = thibault.get(f"/partie/{pid}").texte
    assert "Mobilisation en France" in page                       # Journal
    assert "Les troupes sont prêtes." in page and "Le Parlement hésite." in page
    assert "réussi" in page and "partiel" in page                 # issue de chaque ordre
    couleur = e["nations"]["france"]["couleur"]
    assert re.search(r'id="t-AUT"[^>]*fill="%s"|fill="%s"[^>]*id="t-AUT"' % (couleur, couleur), page)   # carte recolorée


def etat_initial_de(app, nation):
    s, _ = charger_dossiers(app.state.config.scenarios, app.state.carte.noms)
    return etat_initial(s["seconde-guerre-1939"], nation)


# ------------------------------------------------------------------ 12
def appliquer(etat39, noms, rep, duree="1mois", ordres=("x",)):
    return moteur.appliquer(etat39, rep, noms, list(ordres), duree)


def test_12_plafond_de_chiffre(etat39, noms):
    rep = reponse(1, chiffres=[{"nation": "france", "chiffre": "economie", "variation": 40, "raison": "?"},
                               {"nation": "france", "chiffre": "armee", "variation": -40, "raison": "?"}])
    neuf, corr = appliquer(etat39, noms, rep, "1mois")
    assert neuf["nations"]["france"]["economie"] == etat39["nations"]["france"]["economie"] + 5
    assert neuf["nations"]["france"]["armee"] == etat39["nations"]["france"]["armee"] - 5
    assert len(corr) == 2 and "plafond" in corr[0]
    neuf, _ = appliquer(etat39, noms, rep, "1an")                  # plafond plus large pour 1 an
    assert neuf["nations"]["france"]["economie"] == etat39["nations"]["france"]["economie"] + 15
    neuf, _ = appliquer(etat39, noms, rep, "6mois")
    assert neuf["nations"]["france"]["economie"] == etat39["nations"]["france"]["economie"] + 10


def test_12_plafond_de_relation(etat39, noms):
    rep = reponse(1, relations=[{"nation_a": "france", "nation_b": "italie", "variation": -90, "raison": "?"}])
    neuf, corr = appliquer(etat39, noms, rep, "1mois")
    avant = etat39["relations"].get("france|italie", 0)
    assert neuf["relations"]["france|italie"] == max(-100, avant - 20)
    assert corr and "±20" in corr[0]
    neuf, _ = appliquer(etat39, noms, rep, "1an")
    assert neuf["relations"]["france|italie"] == max(-100, avant - 40)


def test_12_transfert_refuse_sans_guerre_ni_traite(etat39, noms):
    # France et Italie ne sont pas en guerre : « guerre » refusé
    rep = reponse(1, territoires=[{"territoire": "ITA", "vers": "france", "base": "guerre", "raison": "?"}])
    neuf, corr = appliquer(etat39, noms, rep)
    assert neuf["territoires"]["ITA"] == etat39["territoires"]["ITA"]
    assert any("ne sont pas en guerre" in c for c in corr)
    # traité non décrit dans un événement du tour : refusé
    rep = reponse(1, territoires=[{"territoire": "ITA", "vers": "france", "base": "traité", "raison": "?"}])
    neuf, corr = appliquer(etat39, noms, rep)
    assert neuf["territoires"]["ITA"] == etat39["territoires"]["ITA"] and any("traité" in c for c in corr)
    # traité décrit (événement citant les deux nations) : accepté
    rep["evenements"].append({"date": "1939-09-12", "titre": "Traité franco-italien", "texte": "t",
                              "pays": ["france", "italie"], "secret": False})
    neuf, corr = appliquer(etat39, noms, rep)
    assert neuf["territoires"]["ITA"] == "france"
    # en guerre déjà (Allemagne/Pologne) : accepté
    rep = reponse(1, territoires=[{"territoire": "POL", "vers": "allemagne", "base": "guerre", "raison": "?"}])
    neuf, _ = appliquer(etat39, noms, rep)
    assert neuf["territoires"]["POL"] == "allemagne"


def test_12_plafond_de_transferts(etat39, noms):
    cibles = ["AUT", "CZE", "ITA", "ESP", "PRT"]
    for t in cibles:
        etat39["territoires"][t] = "allemagne"
    rep = reponse(1, guerres=[{"action": "déclaration", "nom": "G", "camp_a": ["france"], "camp_b": ["allemagne"]}],
                  territoires=[{"territoire": t, "vers": "france", "base": "guerre", "raison": "?"} for t in cibles])
    neuf, corr = appliquer(etat39, noms, rep, "1mois")
    assert [neuf["territoires"][t] for t in cibles] == ["france"] * 3 + ["allemagne"] * 2
    assert sum("plafond de 3 transferts" in c for c in corr) == 2
    neuf, corr = appliquer(etat39, noms, rep, "6mois")
    assert [neuf["territoires"][t] for t in cibles] == ["france"] * 5 and not corr


def test_12_inconnu_ignore(etat39, noms):
    rep = reponse(1,
                  chiffres=[{"nation": "atlantide", "chiffre": "armee", "variation": 3, "raison": "?"}],
                  relations=[{"nation_a": "france", "nation_b": "mordor", "variation": 3, "raison": "?"}],
                  territoires=[{"territoire": "XXX", "vers": "france", "base": "guerre", "raison": "?"},
                               {"territoire": "ITA", "vers": "narnia", "base": "guerre", "raison": "?"}])
    rep["evenements"][0]["pays"] = ["france", "lemuria"]
    neuf, corr = appliquer(etat39, noms, rep)
    assert neuf["relations"] == etat39["relations"] and neuf["territoires"] == etat39["territoires"]
    assert neuf["journal"][0]["pays"] == ["france"]
    assert len(corr) == 5 and all("inconnu" in c for c in corr)


def test_12_encart_corrections_puis_renvoi_a_l_ia(thibault, faux, app):
    pid = creer(thibault)
    rep = reponse(1, chiffres=[{"nation": "france", "chiffre": "armee", "variation": 30, "raison": "?"}])
    jouer(thibault, pid, faux, rep)
    page = thibault.get(f"/partie/{pid}").texte
    assert 'id="corrections"' in page and "ramené à +5" in page
    jouer(thibault, pid, faux, reponse(1))
    dernier = faux.requetes[-1]["messages"][-1]["content"]
    assert "Corrections du tour précédent" in dernier and "ramené à +5" in dernier
    assert "ramené" not in thibault.get(f"/partie/{pid}").texte           # remplacées par celles du nouveau tour


def test_12_nouvelle_nation(etat39, noms):
    rep = reponse(1, nouvelle_nation={"nom": "Libre Pologne", "dirigeant": "X", "regime": "exil",
                                      "territoires": ["POL"]})
    neuf, corr = appliquer(etat39, noms, rep)
    assert neuf["territoires"]["POL"] == "libre-pologne" and neuf["nations"]["libre-pologne"]["nom"] == "Libre Pologne"
    rep = reponse(1, nouvelle_nation={"nom": "Vide", "territoires": []})
    neuf, corr = appliquer(etat39, noms, rep)
    assert "vide" not in neuf["nations"] and corr


# ------------------------------------------------------------------ 13
def test_13_lecture_tolerante():
    obj = reponse(1)
    brut = json.dumps(obj, ensure_ascii=False)
    for texte in (
        "Voici le tour :\n```json\n" + brut + "\n```\nBonne partie !",
        "<think>Je réfléchis {pas du json}</think>" + brut,
        brut.replace('"resume"', '"resume"')[:-1] + ',}',                      # virgule en trop
        brut.replace('"faits": [', '"faits": [').replace('"]}', '",]}'),       # virgule dans une liste
    ):
        lu, fautes = moteur.lire_reponse(texte)
        assert lu is not None and not moteur.verifier_forme(lu), (texte[:60], fautes)
        assert lu["resume"] == obj["resume"]
    lu, fautes = moteur.lire_reponse("pas de JSON ici")
    assert lu is None and fautes


def test_13_reponse_mal_formee_reparee_sans_relance(thibault, faux, app):
    pid = creer(thibault)
    brut = "<think>hmm</think>Voici : " + json.dumps(reponse(1), ensure_ascii=False)[:-1] + ",}"
    d = jouer(thibault, pid, faux, brut)
    assert d["etat"] == "termine" and len(faux.requetes) == 1


def test_13_une_relance_listant_les_fautes(thibault, faux, app):
    pid = creer(thibault)
    mauvais = reponse(1)
    del mauvais["resume"]
    faux.programmer(json.dumps(mauvais), reponse(1))
    assert avancer(thibault, pid).status == 202
    assert attendre(thibault, pid)["etat"] == "termine"
    assert len(faux.requetes) == 2
    assert "resume" in faux.requetes[1]["messages"][-1]["content"]
    assert sauvegarde(app, pid)["tour"] == 1


def test_13_echec_apres_relance_etat_inchange_ordres_gardes(thibault, faux, app):
    pid = creer(thibault)
    avant = sauvegarde(app, pid)
    faux.programmer("du texte sans json", "toujours rien")
    assert avancer(thibault, pid, ordres=["Ordre un", "Ordre deux"]).status == 202
    d = attendre(thibault, pid)
    assert d["etat"] == "echec" and "inexploitable" in d["message"]
    assert len(faux.requetes) == 2                                    # une seule relance, pas plus
    apres = sauvegarde(app, pid)
    for cle in ("modifie_le", "brouillon"):
        avant.pop(cle, None), apres.pop(cle, None)
    assert apres == avant
    page = thibault.get(f"/partie/{pid}").texte
    assert "Ordre un" in page and "Ordre deux" in page               # ordres revenus dans la zone de saisie


# ------------------------------------------------------------------ 14
def _sans_volatil(e):
    e = copy.deepcopy(e)
    for k in ("modifie_le", "historique", "brouillon"):
        e.pop(k, None)
    return e


def test_14_annuler_jusqu_a_10_tours(thibault, faux, app):
    pid = creer(thibault)
    etats = [sauvegarde(app, pid)]
    for i in range(11):
        assert jouer(thibault, pid, faux, reponse(1), ordres=[f"ordre du tour {i + 1}"], duree="1sem")["etat"] == "termine"
        etats.append(sauvegarde(app, pid))
    assert len(etats[-1]["historique"]) == 10                            # 10 états gardés, pas 11
    for i in range(10):
        r = thibault.post(f"/partie/{pid}/annuler", entetes=ORIG)
        assert r.status == 303
        e = sauvegarde(app, pid)
        assert _sans_volatil(e) == _sans_volatil(etats[10 - i])         # exactement l'état d'avant
        assert e["brouillon"]["ordres"] == [f"ordre du tour {11 - i}"]  # les ordres reviennent
    assert f"ordre du tour 2" in thibault.get(f"/partie/{pid}").texte
    assert thibault.post(f"/partie/{pid}/annuler", entetes=ORIG).status == 400    # au-delà de 10 : impossible


def test_14_annuler_refuse_pendant_un_tour_et_par_autrui(thibault, lea, faux, app):
    pid = creer(thibault)
    jouer(thibault, pid, faux, reponse(1))
    assert lea.post(f"/partie/{pid}/annuler", entetes=ORIG).status == 404
    assert thibault.post(f"/partie/{pid}/annuler", entetes={"Origin": "http://evil.example"}).status == 403


# ------------------------------------------------------------------ 15
def test_15_contexte_8192_apres_30_tours(etat39, noms):
    e = etat39
    for i in range(1, 31):
        e["tour"] = i
        e["histoire"].append({"tour": i, "du": "1939-09-01", "au": "1939-10-01", "duree": "1mois",
                              "resume": f"Résumé du tour {i}. " + "Les armées bougent et les diplomates parlent. " * 8,
                              "ordres": ["x"]})
        e["journal"] += [{"tour": i, "date": "1939-09-15", "titre": f"Événement {i}-{k}", "texte": "t" * 300,
                          "pays": ["france"], "secret": k == 0} for k in range(4)]
        e["faits_etablis"].append(f"Fait établi numéro {i}.")
    ordres = ["Ordre capital numéro un", "Ordre capital numéro deux"]
    complet, infos_large = moteur.construire_requete(e, noms, ordres, "1mois", 131072)
    messages, infos = moteur.construire_requete(e, noms, ordres, "1mois", 8192)
    assert moteur.estimer_jetons(messages) <= 8192 - 4096
    assert infos["detail"] == 0 and infos["resumes"] < 30              # réduit : détail puis anciens retirés
    assert moteur.estimer_jetons(complet) > moteur.estimer_jetons(messages)
    texte = messages[-1]["content"]
    assert "1. Ordre capital numéro un" in texte and "2. Ordre capital numéro deux" in texte   # ordres
    assert "Daladier" in texte                                           # état du joueur
    assert "Règles de simulation" in texte and "Pologne" in texte        # règles et contexte du scénario
    assert "Résumé du tour 1." not in texte
    moyen, _ = moteur.construire_requete(e, noms, ordres, "1mois", 10240)
    tm = moyen[-1]["content"]
    assert "Résumé du tour 30." in tm and "Résumé du tour 1." not in tm   # les plus anciens partent d'abord
    with pytest.raises(moteur.ContexteTropPetit):
        moteur.construire_requete(e, noms, ordres, "1mois", 4200)


def test_15_requete_reelle_respecte_le_contexte(thibault, faux, app):
    app.state.reglages.ecrire({"ollama_adresse": faux.adresse, "modele": "m", "contexte": 8192})
    pid = creer(thibault)
    assert jouer(thibault, pid, faux, reponse(1))["etat"] == "termine"
    req = faux.requetes[0]
    assert req["options"]["num_ctx"] == 8192
    assert moteur.estimer_jetons(req["messages"]) <= 8192 - 4096
    app.state.reglages.ecrire({"ollama_adresse": faux.adresse, "modele": "m", "contexte": 4500})
    faux.programmer(reponse(1))
    avancer(thibault, pid)
    d = attendre(thibault, pid)
    assert d["etat"] == "echec" and "contexte" in d["message"] and len(faux.requetes) == 1   # rien d'envoyé


# ------------------------------------------------------------------ 16
def test_16_evenement_secret(thibault, faux, app):
    pid = creer(thibault)
    secret_autres = {"date": "1939-09-05", "titre": "Pacte des loups", "texte": "Berlin et Moscou s'entendent en secret.",
                     "pays": ["allemagne", "urss"], "secret": True}
    secret_france = {"date": "1939-09-06", "titre": "Espion démasqué", "texte": "Un agent est arrêté.",
                     "pays": ["france", "allemagne"], "secret": True}
    rep = reponse(1)
    rep["evenements"] += [secret_autres, secret_france]
    jouer(thibault, pid, faux, rep)
    e = sauvegarde(app, pid)
    assert {x["titre"] for x in e["journal"]} >= {"Pacte des loups", "Espion démasqué"}      # l'état garde tout
    page = thibault.get(f"/partie/{pid}").texte
    assert "Pacte des loups" not in page and "Berlin et Moscou" not in page
    assert "Espion démasqué" in page and "Mobilisation en France" in page
    from app.monde import evenements_visibles, resume_etat
    assert [x["titre"] for x in evenements_visibles(e)] == ["Espion démasqué", "Mobilisation en France"]
    assert "Pacte des loups" not in json.dumps(resume_etat(e, app.state.carte.noms), ensure_ascii=False)
    jouer(thibault, pid, faux, reponse(1))
    assert "Pacte des loups" in faux.requetes[-1]["messages"][-1]["content"]                 # le narrateur le voit


# ------------------------------------------------------------------ 16 bis
def test_16bis_file_d_attente(thibault, lea, faux, app):
    faux.pause, faux.morceau = 0.1, 40
    p1, p2 = creer(thibault), creer(lea)
    faux.programmer(reponse(1), reponse(1))
    assert avancer(thibault, p1).status == 202
    assert avancer(lea, p2).status == 202
    d = lea.get(f"/partie/{p2}/tour").json()
    assert d["etat"] == "attente" and d["message"] == "en attente, 1 demande avant vous"
    assert thibault.get(f"/partie/{p1}/tour").json()["etat"] in ("ecriture", "attente")
    assert attendre(thibault, p1)["etat"] == "termine"
    assert attendre(lea, p2)["etat"] == "termine"
    assert len(faux.requetes) == 2
    assert sauvegarde(app, p1)["tour"] == 1 and sauvegarde(app, p2, "lea")["tour"] == 1


def test_16bis_un_seul_tour_a_la_fois_par_partie(thibault, faux):
    faux.pause = 0.1
    pid = creer(thibault)
    faux.programmer(reponse(1))
    assert avancer(thibault, pid).status == 202
    assert avancer(thibault, pid).status == 409
    assert attendre(thibault, pid)["etat"] == "termine"


# ------------------------------------------------------------------ 16 ter
def test_16ter_pc_eteint(thibault, faux, app):
    pid = creer(thibault)
    avant = sauvegarde(app, pid)
    faux.eteindre()
    assert avancer(thibault, pid, ordres=["Garder mes ordres"]).status == 202
    d = attendre(thibault, pid)
    assert d["etat"] == "echec" and "Le PC de l'IA ne répond pas" in d["message"]
    apres = sauvegarde(app, pid)
    assert apres["tour"] == 0 and apres["date"] == avant["date"] and apres["brouillon"]["ordres"] == ["Garder mes ordres"]
    assert "Garder mes ordres" in thibault.get(f"/partie/{pid}").texte
    s = thibault.get("/api/ia/statut").json()
    assert s["pret"] is False and s["message"] == "Le PC de l'IA ne répond pas."       # boutons grisés côté page


def test_modele_non_choisi(thibault, app):
    pid = creer(thibault)
    assert avancer(thibault, pid).status == 409


# ------------------------------------------------------------------ 17
def test_17_fin_de_partie(thibault, faux, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    for t, n in e["territoires"].items():                  # la France ne garde qu'un territoire
        if n == "france" and t != "FRA":
            e["territoires"][t] = "allemagne"
    app.state.sauvegarde.enregistrer("thibault", e)
    assert 'id="fin-partie"' not in thibault.get(f"/partie/{pid}").texte
    rep = reponse(1, guerres=[{"action": "déclaration", "nom": "Chute", "camp_a": ["allemagne"], "camp_b": ["france"]}],
                  territoires=[{"territoire": "FRA", "vers": "allemagne", "base": "guerre", "raison": "invasion"}])
    assert jouer(thibault, pid, faux, rep)["etat"] == "termine"
    page = thibault.get(f"/partie/{pid}").texte
    assert 'id="fin-partie"' in page and "Fin de la partie" in page
    assert f"/partie/{pid}/annuler" in page                         # annulation proposée
    assert 'id="avancer"' not in page
    assert avancer(thibault, pid).status == 409
    assert thibault.post(f"/partie/{pid}/annuler", entetes=ORIG).status == 303
    page = thibault.get(f"/partie/{pid}").texte
    assert 'id="fin-partie"' not in page and 'id="avancer"' in page


# ------------------------------------------------------------------ relecture : corrections
def test_B1_plafond_non_contournable_par_repetition(etat39, noms):
    rep = reponse(1,
                  chiffres=[{"nation": "france", "chiffre": "economie", "variation": 5, "raison": "?"}] * 10,
                  relations=[{"nation_a": "france", "nation_b": "italie", "variation": 20, "raison": "?"}] * 5)
    neuf, corr = appliquer(etat39, noms, rep, "1mois")
    assert neuf["nations"]["france"]["economie"] == etat39["nations"]["france"]["economie"] + 5
    avant = etat39["relations"].get("france|italie", 0)
    assert neuf["relations"]["france|italie"] == min(100, avant + 20)
    assert any("au total ramené" in c and "Économie" in c for c in corr)
    assert any("au total ramené" in c and "Relation" in c for c in corr)
    # la paire est la même dans les deux sens
    rep = reponse(1, relations=[{"nation_a": "france", "nation_b": "italie", "variation": 15, "raison": "?"},
                                {"nation_a": "italie", "nation_b": "france", "variation": 15, "raison": "?"}])
    neuf, _ = appliquer(etat39, noms, rep, "1mois")
    assert neuf["relations"]["france|italie"] == min(100, avant + 20)


def test_B2_corrections_du_joueur_sans_secret(thibault, faux, app):
    pid = creer(thibault)
    rep = reponse(
        1,
        evenements=[{"date": "1939-09-05", "titre": "Pacte des loups", "texte": "t", "pays": ["allemagne", "urss", "atlantide"],
                     "secret": True},
                    {"date": "1939-09-06", "titre": "Fête publique", "texte": "t", "pays": ["france", "lemuria"]}],
        guerres=[{"action": "déclaration", "nom": "G", "camp_a": ["allemagne"], "camp_b": ["urss"]}],
        territoires=[{"territoire": "UKR", "vers": "pologne", "base": "traité", "raison": "?"}],
        relations=[{"nation_a": "allemagne", "nation_b": "urss", "variation": 90, "raison": "?"}])
    jouer(thibault, pid, faux, rep)
    e = sauvegarde(app, pid)
    complet = " ".join(e["corrections"])
    assert "Pacte des loups" in complet and "Allemagne" in complet          # l'IA reçoit tout
    page = thibault.get(f"/partie/{pid}").texte
    zone = page[page.index('id="corrections"'):]
    zone = zone[:zone.index("</div>")]
    assert "Pacte des loups" not in zone and "atlantide" not in zone       # événement secret des autres
    assert "Allemagne" not in zone and "Union soviétique" not in zone and "Pologne" not in zone
    assert "Fête publique" in zone and "lemuria" in zone                   # ce qui le concerne reste visible
    jouer(thibault, pid, faux, reponse(1))
    assert "Pacte des loups" in faux.requetes[-1]["messages"][-1]["content"]


def test_I1_secret_par_defaut(etat39, noms):
    for v in ("true", "oui", 1, "Vrai", "peut-être"):
        rep = reponse(1, evenements=[{"titre": "E", "texte": "t", "pays": ["allemagne"], "secret": v}])
        assert appliquer(etat39, noms, rep)[0]["journal"][0]["secret"] is True, v
    for v in (False, "false", "non", 0, None):
        rep = reponse(1, evenements=[{"titre": "E", "texte": "t", "pays": ["allemagne"], "secret": v}])
        assert appliquer(etat39, noms, rep)[0]["journal"][0]["secret"] is False, v


def test_I2_types_inattendus_ne_plantent_pas(etat39, noms):
    rep = reponse(1,
                  evenements=[{"titre": "E", "texte": "t", "pays": 5}, {"titre": "F", "texte": "t", "pays": "france"}],
                  guerres=[{"action": "déclaration", "nom": "G", "camp_a": "france", "camp_b": 7},
                           {"action": "paix", "nom": "x", "camp_a": 3, "camp_b": None}],
                  nouvelle_nation={"nom": "Z", "territoires": "POL"},
                  territoires=[{"territoire": 12, "vers": ["x"], "base": 3}])
    neuf, corr = appliquer(etat39, noms, rep)
    assert neuf["journal"][1]["pays"] == ["france"]
    assert neuf["territoires"]["POL"] == "z"            # texte seul accepté comme liste d'un élément


def test_I3_supprimer_et_annuler_refuses_pendant_un_tour(thibault, faux, app):
    faux.pause = 0.1
    pid = creer(thibault)
    jouer(thibault, pid, faux, reponse(1))
    faux.programmer(reponse(1))
    assert avancer(thibault, pid).status == 202
    assert thibault.post(f"/partie/{pid}/supprimer", entetes=ORIG).status == 409
    assert thibault.post(f"/partie/{pid}/annuler", entetes=ORIG).status == 409
    assert attendre(thibault, pid)["etat"] == "termine"
    assert sauvegarde(app, pid)["tour"] == 2                       # rien n'a été écrasé


def test_D1_ticket_libere_si_le_fil_ne_demarre_pas(app, monkeypatch):
    import threading
    from app.execution import Gestionnaire
    g = Gestionnaire()
    monkeypatch.setattr(threading.Thread, "start", lambda self: (_ for _ in ()).throw(RuntimeError("non")))
    with pytest.raises(RuntimeError):
        g.lancer(app, "thibault", "0" * 16, ["x"], "1mois")
    assert g.file.taille() == 0 and not g.actif("thibault", "0" * 16)


def test_D2_num_predict_et_compteur_incremental(thibault, faux):
    pid = creer(thibault)
    jouer(thibault, pid, faux, reponse(1))
    assert faux.requetes[0]["options"]["num_predict"] == 8192
    from app.execution import Tour
    j = Tour(None, [], "1mois")
    for m in ("Bon", "jour le ", "mon", "de  ", "!"):
        j.ajouter(m)
    assert (j.mots, j.caracteres) == (4, 19)


def test_D3_un_second_onglet_voit_le_tour_termine(thibault, faux):
    pid = creer(thibault)
    jouer(thibault, pid, faux, reponse(1))
    assert thibault.get(f"/partie/{pid}/tour").json()["etat"] == "termine"
    assert thibault.get(f"/partie/{pid}/tour").json()["etat"] == "termine"
    assert thibault.get(f"/partie/{pid}/tour?initial=1").json()["etat"] == "aucun"   # pas de rechargement sans fin


def test_D4_valeurs_de_l_ia_tronquees(etat39, noms):
    rep = reponse(1, chiffres=[{"nation": "x" * 500, "chiffre": "armee", "variation": 1}])
    _, corr = appliquer(etat39, noms, rep)
    assert corr and len(corr[0]) < 200 and "…" in corr[0]


def test_D5_declaration_de_guerre_tous_les_membres(etat39, noms):
    # Allemagne/Pologne déjà en guerre ; la France contre l'Allemagne ET la Pologne est une guerre nouvelle
    n = len(etat39["guerres"])
    rep = reponse(1, guerres=[{"action": "déclaration", "nom": "Nouvelle", "camp_a": ["allemagne"], "camp_b": ["pologne"]}])
    assert len(appliquer(etat39, noms, rep)[0]["guerres"]) == n
    rep = reponse(1, guerres=[{"action": "déclaration", "nom": "Large", "camp_a": ["allemagne", "france"], "camp_b": ["pologne"]}])
    assert len(appliquer(etat39, noms, rep)[0]["guerres"]) == n + 1



def test_schema_tout_obligatoire():
    # sans cela, la sortie contrainte d'Ollama saute chiffres/relations/guerres (constaté sur thnas)
    req = moteur.schema_reponse()["required"]
    for cle in ("chiffres", "relations", "guerres", "territoires", "nouvelle_nation", "faits"):
        assert cle in req


def test_mention_secret_dans_le_titre_rend_secret(etat39, noms):
    rep = reponse(1, evenements=[
        {"titre": "Combats de Khalkhin Gol (secret)", "texte": "t", "pays": ["urss", "japon"], "secret": False},
        {"titre": "Pacte", "texte": "Cette information est confidentielle.", "pays": ["urss"], "secret": False},
        {"titre": "Mobilisation", "texte": "Les alliés mobilisent.", "pays": ["france"], "secret": False}])
    j = {e["titre"]: e for e in appliquer(etat39, noms, rep)[0]["journal"]}
    assert j["Combats de Khalkhin Gol"]["secret"] is True          # mention retirée du titre
    assert j["Pacte"]["secret"] is True and j["Mobilisation"]["secret"] is False


def test_23_duree_et_modele_affiches_dans_le_journal(thibault, faux, app):
    pid = creer(thibault)
    faux.programmer(reponse(1))
    assert avancer(thibault, pid).status == 202
    attendre(thibault, pid)
    e = app.state.sauvegarde.lire("thibault", pid)
    m = e["histoire"][-1]["mesure"]
    assert m["secondes"] >= 0 and m["modele"] and m["relance"] is False
    assert "joué en" in thibault.get(f"/partie/{pid}").texte
