"""Étape 3 — les aides de l'IA : critères 16 (suite), 19, 20, 21 (avec le faux Ollama)."""
import json
import re
import time

import pytest

from app import aides, tour as moteur
from tests.test_tour import (ORIG, avancer, attendre, creer, etat39, faux, jouer, noms, reponse,  # noqa: F401
                             sauvegarde)

RAPPORT = {"situation": "La France mobilise face à l'Allemagne.", "menaces": ["Offensive allemande", "Crise sociale"],
           "occasions": ["Alliance avec la Belgique"],
           "suggestions": ["Mobiliser l'armée du Nord", "Proposer une alliance défensive à la Belgique",
                           "Renforcer la ligne Maginot", "Une quatrième de trop"]}


def demander(client, pid, genre, message=None, nation=None, **kw):
    corps = {"genre": genre}
    if message is not None:
        corps["message"] = message
    if nation is not None:
        corps["nation"] = nation
    return client.post(f"/partie/{pid}/aide", json_=corps, entetes=ORIG, **kw)


def attendre_aide(client, pid, delai=15):
    fin = time.time() + delai
    while time.time() < fin:
        d = client.get(f"/partie/{pid}/aide").json()
        if d["etat"] in ("termine", "echec", "aucun"):
            return d
        time.sleep(0.05)
    raise AssertionError("l'aide ne finit pas")


def aide(client, pid, faux, rep, genre, message=None, nation=None):
    faux.programmer(rep)
    r = demander(client, pid, genre, message, nation)
    assert r.status == 202, r.texte
    return attendre_aide(client, pid)


def tout_envoye(faux) -> str:
    return json.dumps(faux.requetes, ensure_ascii=False)


# ------------------------------------------------------------------ 19
def test_19_rapport_de_situation(thibault, faux, app):
    pid = creer(thibault)
    d = aide(thibault, pid, faux, RAPPORT, "rapport")
    assert d["etat"] == "termine"
    r = d["resultat"]["rapport"]
    assert r["situation"].startswith("La France mobilise")
    assert r["menaces"] == RAPPORT["menaces"] and r["occasions"] == RAPPORT["occasions"]
    assert r["suggestions"] == RAPPORT["suggestions"][:3]                      # exactement 3 ordres suggérés
    req = faux.requetes[0]
    assert len(faux.requetes) == 1
    assert set(req["format"]["required"]) == {"situation", "menaces", "occasions", "suggestions"}   # tout obligatoire
    assert "Daladier" in req["messages"][-1]["content"] and "Tenir" in req["messages"][-1]["content"]
    assert sauvegarde(app, pid)["rapport"]["suggestions"] == r["suggestions"]   # gardé : la page le réaffiche
    page = thibault.get(f"/partie/{pid}").texte
    assert 'id="rapport-bouton"' in page and "Offensive allemande" in page      # rendu depuis la sauvegarde
    js = (app.state.config.donnees.parent / "app" / "static" / "aides.js").read_text(encoding="utf-8")
    assert "ajouterOrdre" in js and "innerHTML" not in js                       # clic = ajout aux ordres ; textContent seul


def test_19_rapport_lecture_tolerante_et_relance(thibault, faux):
    pid = creer(thibault)
    entoure = "<think>je réfléchis</think>Voici : " + json.dumps(RAPPORT, ensure_ascii=False).replace("]}", "],}")
    assert aide(thibault, pid, faux, entoure, "rapport")["etat"] == "termine"
    assert len(faux.requetes) == 1                                              # réparé sans relance
    vide = {"situation": "", "menaces": [], "occasions": [], "suggestions": []}
    faux.programmer(vide)                                                       # la relance reçoit la même faute
    d = aide(thibault, pid, faux, vide, "rapport")
    assert d["etat"] == "echec" and "inexploitable" in d["message"]
    assert len(faux.requetes) == 3                                              # une seule relance de plus


# ------------------------------------------------------------------ 20
def test_20_conseiller(thibault, faux, app):
    pid = creer(thibault)
    d = aide(thibault, pid, faux, {"reponse": "Mobilisez, Monsieur."}, "conseiller", "Que faire face à l'Allemagne ?")
    assert d["etat"] == "termine" and d["resultat"]["reponse"] == "Mobilisez, Monsieur."
    req = faux.requetes[0]
    assert req["format"]["required"] == ["reponse"]
    sysmsg = req["messages"][0]["content"]
    assert "français" in sysmsg and "Daladier" in sysmsg and "Tenir" in sysmsg           # état, objectif
    assert "Pologne" in sysmsg and "Allemagne" in sysmsg                                 # ce qu'elle sait du monde
    assert req["messages"][-1] == {"role": "user", "content": "Que faire face à l'Allemagne ?"}
    d = aide(thibault, pid, faux, {"reponse": "Soyez prudent."}, "conseiller", "Et la Belgique ?")
    roles = [(m["role"], m["content"]) for m in faux.requetes[1]["messages"][1:]]
    assert roles == [("user", "Que faire face à l'Allemagne ?"), ("assistant", "Mobilisez, Monsieur."),
                     ("user", "Et la Belgique ?")]                                       # la conversation suit
    conv = sauvegarde(app, pid)["conseiller"]                                            # gardée dans la sauvegarde
    assert [m["de"] for m in conv] == ["joueur", "conseiller", "joueur", "conseiller"]
    assert "Soyez prudent." in thibault.get(f"/partie/{pid}").texte                      # et rendue au rechargement


def test_20_conversation_survit_a_un_tour_et_a_l_annulation(thibault, faux, app):
    pid = creer(thibault)
    aide(thibault, pid, faux, {"reponse": "Oui."}, "conseiller", "Bonjour")
    jouer(thibault, pid, faux, reponse(1))
    assert len(sauvegarde(app, pid)["conseiller"]) == 2
    assert thibault.post(f"/partie/{pid}/annuler", entetes=ORIG).status == 303
    e = sauvegarde(app, pid)
    assert e["tour"] == 0 and [m["texte"] for m in e["conseiller"]] == ["Bonjour", "Oui."]
    assert all("conseiller" not in h and "diplomatie" not in h for h in e["historique"])


def test_20_texte_libre_accepte_et_messages_bornes(thibault, faux, app):
    pid = creer(thibault)
    assert aide(thibault, pid, faux, "<think>hm</think>Allons-y.", "conseiller", "Salut")["resultat"]["reponse"] == "Allons-y."
    assert demander(thibault, pid, "conseiller", "x" * 1001).status == 400
    assert demander(thibault, pid, "conseiller", "   ").status == 400
    assert demander(thibault, pid, "conseiller", 12).status == 400
    assert demander(thibault, pid, "inconnue", "a").status == 400
    assert len(faux.requetes) == 1
    e = sauvegarde(app, pid)
    e["conseiller"] = [{"de": "joueur", "texte": f"m{i}", "tour": 0, "date": e["date"]} for i in range(aides.MESSAGES_GARDES)]
    app.state.sauvegarde.enregistrer("thibault", e)
    aide(thibault, pid, faux, {"reponse": "r"}, "conseiller", "dernier")
    conv = sauvegarde(app, pid)["conseiller"]
    assert len(conv) == aides.MESSAGES_GARDES and conv[-1]["texte"] == "r"             # historique borné
    assert len(faux.requetes[-1]["messages"]) == 1 + aides.MESSAGES_ENVOYES + 1         # 20 derniers envoyés


# ------------------------------------------------------------------ 21
def test_21_dirigeant_ne_recoit_que_sa_conversation(thibault, faux, app):
    pid = creer(thibault)
    aide(thibault, pid, faux, {"reponse": "SECRET-DU-CONSEILLER"}, "conseiller", "Question privée au conseiller")
    aide(thibault, pid, faux, {"reponse": "Nein."}, "diplomatie", "Allemagne : cédez Dantzig", "allemagne")
    aide(thibault, pid, faux, {"reponse": "Forse."}, "diplomatie", "Italie : restez neutres", "italie")
    d = aide(thibault, pid, faux, {"reponse": "Ja, vielleicht."}, "diplomatie", "Allemagne : et un traité ?", "allemagne")
    assert d["etat"] == "termine" and d["resultat"] == {"reponse": "Ja, vielleicht.", "nation": "allemagne"}
    req = faux.requetes[-1]
    flux = json.dumps(req, ensure_ascii=False)
    assert "Hitler" in req["messages"][0]["content"]                                      # sa propre nation
    assert [(m["role"], m["content"]) for m in req["messages"][1:]] == [
        ("user", "Allemagne : cédez Dantzig"), ("assistant", "Nein."), ("user", "Allemagne : et un traité ?")]
    for interdit in ("Italie : restez neutres", "Forse.", "Question privée au conseiller", "SECRET-DU-CONSEILLER"):
        assert interdit not in flux                                                       # ni autres nations ni conseiller
    assert "Tenir" not in flux                                                            # l'objectif du joueur reste privé
    e = sauvegarde(app, pid)
    assert [m["texte"] for m in e["diplomatie"]["italie"]] == ["Italie : restez neutres", "Forse."]
    assert "Nein." in thibault.get(f"/partie/{pid}").texte


def test_21_dirigeant_20_derniers_messages(thibault, faux, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    e["diplomatie"] = {"italie": [{"de": "joueur" if i % 2 == 0 else "dirigeant", "texte": f"propos{i:02d}", "tour": 0,
                                   "date": e["date"]} for i in range(30)]}
    app.state.sauvegarde.enregistrer("thibault", e)
    aide(thibault, pid, faux, {"reponse": "ok"}, "diplomatie", "dernier mot", "italie")
    contenus = [m["content"] for m in faux.requetes[0]["messages"][1:]]
    assert contenus[:-1] == [f"propos{i:02d}" for i in range(10, 30)] and contenus[-1] == "dernier mot"


def test_21_choix_de_la_nation(thibault, faux, app):
    pid = creer(thibault)
    for nation in (None, "", "atlantide", "france", ["italie"], "pologne-inexistante"):
        assert demander(thibault, pid, "diplomatie", "bonjour", nation).status == 400
    e = sauvegarde(app, pid)
    e["territoires"] = {t: ("allemagne" if n == "italie" else n) for t, n in e["territoires"].items()}   # l'Italie disparaît
    app.state.sauvegarde.enregistrer("thibault", e)
    assert demander(thibault, pid, "diplomatie", "bonjour", "italie").status == 400
    assert not faux.requetes
    page = thibault.get(f"/partie/{pid}").texte
    assert 'value="allemagne"' in page and 'value="italie"' not in page and 'value="france"' not in page


def test_21_discussion_transmise_au_narrateur(thibault, faux, app):
    pid = creer(thibault)
    aide(thibault, pid, faux, {"reponse": "Nous y réfléchirons."}, "diplomatie", "Je promets de respecter votre frontière polonaise", "allemagne")
    aide(thibault, pid, faux, {"reponse": "Intérêt."}, "conseiller", "Mon conseiller doit rester discret")
    jouer(thibault, pid, faux, reponse(1))
    narrateur = faux.requetes[-1]["messages"][-1]["content"]
    assert "Discussions diplomatiques depuis le dernier tour" in narrateur
    assert "Je promets de respecter votre frontière polonaise" in narrateur and "Nous y réfléchirons." in narrateur
    assert "Mon conseiller doit rester discret" not in narrateur                           # le conseiller reste privé
    jouer(thibault, pid, faux, reponse(1))                                                  # consommé : plus transmis
    assert "Je promets de respecter" not in faux.requetes[-1]["messages"][-1]["content"]


def test_21_discussion_dans_le_budget_de_contexte(etat39, noms):
    e = etat39
    e["tour"] = 5
    for nid in ("allemagne", "italie", "urss", "royaume-uni", "pologne"):
        e["diplomatie"][nid] = [{"de": "joueur" if i % 2 == 0 else "dirigeant", "texte": f"{nid} {i} " + "blabla " * 140,
                                 "tour": 5, "date": e["date"]} for i in range(24)]
    ordres = ["Ordre capital numéro un", "Ordre capital numéro deux"]
    complet, infos = moteur.construire_requete(e, noms, ordres, "1mois", 131072)
    assert infos["dialogues"] == 0 and "allemagne 23 " in complet[-1]["content"] and "allemagne 3 " not in complet[-1]["content"]
    messages, infos = moteur.construire_requete(e, noms, ordres, "1mois", 8192)
    assert moteur.estimer_jetons(messages) <= 8192 - 4096
    texte = messages[-1]["content"]
    assert infos["dialogues"] >= 1                                                          # dialogues raccourcis ou retirés
    assert "1. Ordre capital numéro un" in texte and "2. Ordre capital numéro deux" in texte
    assert "Daladier" in texte and "Règles de simulation" in texte                          # ordres, joueur, règles : intacts
    un_peu = moteur.construire_requete(e, noms, ordres, "1mois", 12288)[0][-1]["content"]
    assert "allemagne 23 " in un_peu                                                         # les promesses survivent à l'histoire


# ------------------------------------------------------------------ 16 (suite)
SECRETS = ("PACTE-NOIR-ALPHA", "COMPLOT-VERT-BETA", "RESUME-SECRET-GAMMA", "FAIT-SECRET-DELTA", "CORRECTION-SECRETE-EPSILON",
           "NOTE-RELATIONS-ZETA")


def _monde_avec_secrets(app, pid):
    e = sauvegarde(app, pid)
    e["journal"] += [
        {"tour": 1, "date": "1939-09-05", "titre": "PACTE-NOIR-ALPHA", "texte": "Berlin et Moscou s'entendent (NOTE-RELATIONS-ZETA).",
         "pays": ["allemagne", "urss"], "secret": True},
        {"tour": 1, "date": "1939-09-06", "titre": "COMPLOT-VERT-BETA", "texte": "Rome et Londres complotent.",
         "pays": ["italie", "royaume-uni"], "secret": True},
        {"tour": 1, "date": "1939-09-07", "titre": "Espion démasqué", "texte": "Un agent allemand est arrêté.",
         "pays": ["france", "allemagne"], "secret": True},
        {"tour": 1, "date": "1939-09-08", "titre": "Sommet public", "texte": "Rencontre publique.", "pays": ["italie"], "secret": False}]
    e["histoire"] += [{"tour": 1, "du": "1939-09-01", "au": "1939-10-01", "duree": "1mois",
                       "resume": "Le narrateur raconte RESUME-SECRET-GAMMA.", "ordres": ["x"]}]
    e["faits_etablis"] += ["FAIT-SECRET-DELTA : Berlin et Moscou sont d'accord."]
    e["corrections"] = ["CORRECTION-SECRETE-EPSILON"]
    e["tour"] = 1
    app.state.sauvegarde.enregistrer("thibault", e)
    return e


def test_16_aucun_secret_chez_conseiller_rapport_dirigeants(thibault, faux, app):
    pid = creer(thibault)
    e = _monde_avec_secrets(app, pid)
    aide(thibault, pid, faux, RAPPORT, "rapport")
    aide(thibault, pid, faux, {"reponse": "ok"}, "conseiller", "Que savons-nous ?")
    aide(thibault, pid, faux, {"reponse": "ok"}, "diplomatie", "Parlons", "allemagne")      # impliqué dans le secret du joueur
    aide(thibault, pid, faux, {"reponse": "ok"}, "diplomatie", "Parlons", "italie")
    aide(thibault, pid, faux, {"reponse": "ok"}, "diplomatie", "Parlons", "urss")
    assert len(faux.requetes) == 5
    for i, req in enumerate(faux.requetes):
        flux = json.dumps(req, ensure_ascii=False)
        for secret in SECRETS:
            assert secret not in flux, f"{secret} fuit dans la requête {i}"
        assert e["scenario"]["regles"][0]["texte"][:60] not in flux                          # règles du narrateur
        assert e["scenario"]["contexte"].strip()[:80] not in flux
    # ce qui est permis est bien envoyé
    flux = [json.dumps(r, ensure_ascii=False) for r in faux.requetes]
    assert "Espion démasqué" in flux[0] and "Espion démasqué" in flux[1]                     # secret qui implique le joueur
    assert "Espion démasqué" in flux[2]                                                      # partagé joueur + Allemagne
    assert "Espion démasqué" not in flux[3] and "Espion démasqué" not in flux[4]             # l'Italie et l'URSS l'ignorent
    assert "Sommet public" in flux[3]
    # le narrateur, lui, voit tout
    jouer(thibault, pid, faux, reponse(1))
    n = faux.requetes[-1]["messages"][-1]["content"]
    assert "PACTE-NOIR-ALPHA" in n and "RESUME-SECRET-GAMMA" in n and "FAIT-SECRET-DELTA" in n


def test_16_garde_fou_de_construire_aide(etat39, noms):
    e = etat39
    e["journal"] += [{"tour": 1, "date": "1939-09-05", "titre": "PACTE-NOIR-ALPHA", "texte": "x", "pays": ["allemagne", "urss"], "secret": True}]
    e["histoire"] += [{"tour": 1, "du": "1939-09-01", "au": "1939-10-01", "duree": "1mois", "resume": "RESUME-SECRET-GAMMA", "ordres": []}]
    e["faits_etablis"] += ["FAIT-SECRET-DELTA"]
    for genre, kw in (("rapport", {}), ("conseiller", {"message": "q"}), ("diplomatie", {"message": "q", "nation": "allemagne"})):
        for ctx in (131072, 8192):
            m, _ = aides.construire_aide(e, noms, genre, ctx, **kw)
            flux = json.dumps(m, ensure_ascii=False)
            assert not any(s in flux for s in ("PACTE-NOIR-ALPHA", "RESUME-SECRET-GAMMA", "FAIT-SECRET-DELTA"))
            assert moteur.estimer_jetons(m) <= ctx - 4096
    with pytest.raises(moteur.ContexteTropPetit):
        aides.construire_aide(e, noms, "rapport", 4200)


# ------------------------------------------------------------------ 16 bis / 16 ter pour les aides
def test_16bis_aide_file_d_attente(thibault, lea, faux, app):
    faux.pause, faux.morceau = 0.1, 20
    p1, p2 = creer(thibault), creer(lea)
    faux.programmer({"reponse": "un"}, {"reponse": "deux"})
    assert demander(thibault, p1, "conseiller", "a").status == 202
    assert demander(lea, p2, "conseiller", "b").status == 202
    d = lea.get(f"/partie/{p2}/aide").json()
    assert d["etat"] == "attente" and d["message"] == "en attente, 1 demande avant vous"
    assert attendre_aide(thibault, p1)["etat"] == "termine" and attendre_aide(lea, p2)["etat"] == "termine"
    assert len(faux.requetes) == 2


def test_16bis_aide_apres_un_tour_meme_file(thibault, faux, app):
    faux.pause, faux.morceau = 0.1, 20
    pid = creer(thibault)
    faux.programmer(reponse(1), {"reponse": "reçu"})
    assert avancer(thibault, pid).status == 202
    assert demander(thibault, pid, "conseiller", "pendant le tour").status == 202
    assert thibault.get(f"/partie/{pid}/aide").json()["message"] == "en attente, 1 demande avant vous"
    assert attendre(thibault, pid)["etat"] == "termine" and attendre_aide(thibault, pid)["etat"] == "termine"
    e = sauvegarde(app, pid)                                                                 # aucune écriture perdue
    assert e["tour"] == 1 and [m["texte"] for m in e["conseiller"]] == ["pendant le tour", "reçu"]
    assert demander(thibault, pid, "conseiller", "x").status == 202 and demander(thibault, pid, "conseiller", "y").status == 409
    faux.programmer({"reponse": "z"})
    attendre_aide(thibault, pid)


def test_16ter_aides_pc_eteint(thibault, faux, app):
    pid = creer(thibault)
    aide(thibault, pid, faux, {"reponse": "avant"}, "conseiller", "premier")
    avant = sauvegarde(app, pid)
    faux.eteindre()
    for genre, msg, nation in (("rapport", None, None), ("conseiller", "perdu ?", None), ("diplomatie", "perdu ?", "italie")):
        assert demander(thibault, pid, genre, msg, nation).status == 202
        d = attendre_aide(thibault, pid)
        assert d["etat"] == "echec" and "Le PC de l'IA ne répond pas" in d["message"] and "Rien n'est perdu" in d["message"]
    apres = sauvegarde(app, pid)
    assert apres["conseiller"] == avant["conseiller"] and apres["diplomatie"] == avant["diplomatie"]
    assert not apres.get("rapport")


# ------------------------------------------------------------------ sécurité
def test_aides_securite(thibault, lea, anonyme, faux, app):
    pid = creer(thibault)
    assert demander(lea, pid, "conseiller", "intrus").status == 404                          # pas sa partie
    assert lea.get(f"/partie/{pid}/aide").status == 404
    assert demander(anonyme, pid, "conseiller", "x").status == 401
    r = thibault.post(f"/partie/{pid}/aide", json_={"genre": "rapport"}, entetes={"Origin": "http://evil.example"})
    assert r.status == 403                                                                   # autre page web
    assert thibault.post(f"/partie/{pid}/aide", json_=["pas", "un", "objet"], entetes=ORIG).status == 400
    assert not faux.requetes
    # un joueur ne se retrouve jamais dans la requête
    aide(thibault, pid, faux, {"reponse": "ok"}, "conseiller", "salut")
    assert "thibault" not in tout_envoye(faux).lower()


def test_aides_texte_de_l_ia_jamais_en_html(thibault, faux, app):
    pid = creer(thibault)
    aide(thibault, pid, faux, {"reponse": "</script><img src=x onerror=alert(1)>"}, "conseiller", "salut")
    page = thibault.get(f"/partie/{pid}").texte
    assert "</script><img" not in page and "onerror" in page                                 # présent, mais échappé dans le JSON
    assert page.count("</script>") == page.count("<script")


def test_aides_anciennes_sauvegardes_lisibles(thibault, faux, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    for cle in ("conseiller", "diplomatie", "rapport"):
        e.pop(cle, None)
    app.state.sauvegarde.enregistrer("thibault", e)
    assert thibault.get(f"/partie/{pid}").status == 200
    assert aide(thibault, pid, faux, {"reponse": "ok"}, "diplomatie", "bonjour", "italie")["etat"] == "termine"
    assert aide(thibault, pid, faux, {"reponse": "ok"}, "conseiller", "bonjour")["etat"] == "termine"
    jouer(thibault, pid, faux, reponse(1))                                                   # un tour sans ces clés


def test_aides_partie_terminee_refusee(thibault, faux, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    e["territoires"] = {t: ("allemagne" if n == "france" else n) for t, n in e["territoires"].items()}
    app.state.sauvegarde.enregistrer("thibault", e)
    assert demander(thibault, pid, "conseiller", "x").status == 409


def test_annulation_refusee_pendant_une_aide(thibault, faux, app):
    # relecture étape 3 : une aide en cours répondrait d'après le tour annulé
    pid = creer(thibault)
    faux.programmer(reponse(1))
    assert avancer(thibault, pid).status == 202
    attendre(thibault, pid)
    faux.pause, faux.morceau = 0.1, 20
    faux.programmer({"reponse": "lent"})
    assert demander(thibault, pid, "conseiller", "a").status == 202
    r = thibault.post(f"/partie/{pid}/annuler", entetes={"Origin": "http://testserver"})
    assert r.status == 409
    attendre_aide(thibault, pid)
    assert thibault.post(f"/partie/{pid}/annuler", entetes={"Origin": "http://testserver"}).status in (200, 303)
