"""Spec 002, étape 1 — conférences diplomatiques (critères 1 à 6 et 11)."""
import json

import pytest

from app import aides, tour as moteur
from tests.test_aides import attendre_aide, tout_envoye
from tests.test_tour import (ORIG, avancer, attendre, creer, etat39, faux, jouer, noms, reponse,  # noqa: F401
                             sauvegarde)


def conf(client, pid, message, nations=None, conference=None):
    corps = {"genre": "conference", "message": message}
    if nations is not None:
        corps["nations"] = nations
    if conference is not None:
        corps["conference"] = conference
    return client.post(f"/partie/{pid}/aide", json_=corps, entetes=ORIG)


def reponses(*ids, texte="Ma réponse"):
    return {"reponses": [{"nation": i, "texte": f"{texte} de {i}"} for i in ids]}


def lancer(client, pid, faux, rep, message, nations=None, conference=None):
    faux.programmer(rep)
    r = conf(client, pid, message, nations, conference)
    assert r.status == 202, r.texte
    return attendre_aide(client, pid)


def inviter(client, pid, cid, nation):
    return client.post(f"/partie/{pid}/conference/{cid}/inviter", json_={"nation": nation}, entetes=ORIG)


# ------------------------------------------------------------------ 1
def test_01_creation_limites_et_refus(thibault, faux, app):
    pid = creer(thibault)
    for mauvais in (["italie"], [], ["italie", "italie"], ["italie", "france"], ["italie", "atlantide"],
                    ["italie", "allemagne", "urss", "pologne", "royaume-uni", "belgique"], "italie", [["italie"], "urss"], None):
        assert conf(thibault, pid, "bonjour", mauvais).status == 400, mauvais
    assert conf(thibault, pid, "bonjour", conference="cinconnu").status == 400
    assert conf(thibault, pid, "bonjour", conference="../x").status == 400
    assert not faux.requetes
    d = lancer(thibault, pid, faux, reponses("italie", "urss"), "Formons un front commun", ["italie", "urss"])
    assert d["etat"] == "termine" and d["resultat"]["nouvelle"] is True
    cid = d["resultat"]["conference"]
    assert sauvegarde(app, pid)["conferences"][0]["nations"] == ["italie", "urss"]
    # invitations : une de plus jusqu'à 5, jamais deux fois, jamais soi-même, ni une nation disparue
    assert inviter(thibault, pid, cid, "italie").status == 400
    assert inviter(thibault, pid, cid, "france").status == 400
    assert inviter(thibault, pid, cid, "atlantide").status == 400
    assert inviter(thibault, pid, cid, None).status == 400
    assert inviter(thibault, pid, "cinconnu", "pologne").status == 404
    for nation in ("pologne", "royaume-uni", "allemagne"):
        r = inviter(thibault, pid, cid, nation)
        assert r.status == 200 and r.json()["nations"][-1] == nation
    assert sauvegarde(app, pid)["conferences"][0]["nations"] == ["italie", "urss", "pologne", "royaume-uni", "allemagne"]
    assert inviter(thibault, pid, cid, "belgique").status == 400                       # 6e refusée
    e = sauvegarde(app, pid)
    e["territoires"] = {t: ("allemagne" if n == "belgique" else n) for t, n in e["territoires"].items()}
    app.state.sauvegarde.enregistrer("thibault", e)
    petite = lancer(thibault, pid, faux, reponses("italie"), "x", ["italie", "urss"])
    assert petite["etat"] == "termine"
    assert inviter(thibault, pid, petite["resultat"]["conference"], "belgique").status == 400   # disparue


def test_01_securite(thibault, lea, anonyme, faux, app):
    pid = creer(thibault)
    assert conf(lea, pid, "intrus", ["italie", "urss"]).status == 404
    d = lancer(thibault, pid, faux, reponses("italie", "urss"), "a", ["italie", "urss"])
    cid = d["resultat"]["conference"]
    assert inviter(lea, pid, cid, "pologne").status == 404
    assert inviter(anonyme, pid, cid, "pologne").status == 401
    r = thibault.post(f"/partie/{pid}/conference/{cid}/inviter", json_={"nation": "pologne"},
                      entetes={"Origin": "http://evil.example"})
    assert r.status == 403
    assert sauvegarde(app, pid)["conferences"][0]["nations"] == ["italie", "urss"]


# ------------------------------------------------------------------ 2
def test_02_une_requete_une_reponse_par_dirigeant(thibault, faux, app):
    pid = creer(thibault)
    d = lancer(thibault, pid, faux, reponses("urss", "italie", "pologne"), "Front commun ?", ["italie", "urss", "pologne"])
    assert len(faux.requetes) == 1                                                     # une seule demande à l'IA
    req = faux.requetes[0]
    sch = req["format"]
    assert sch["required"] == ["reponses"]
    entree = sch["properties"]["reponses"]["items"]
    assert entree["required"] == ["nation", "texte"] and set(entree["properties"]) == {"nation", "texte"}
    assert entree["properties"]["nation"]["enum"] == ["italie", "urss", "pologne"]
    assert req["think"] is False                                                       # pas de « réflexion »
    assert "Front commun ?" in req["messages"][-1]["content"]
    # le code garde une réponse par invité, dans l'ordre des invités, même si le modèle les mélange
    assert [r["nation"] for r in d["resultat"]["reponses"]] == ["italie", "urss", "pologne"]
    msgs = sauvegarde(app, pid)["conferences"][0]["messages"]
    assert [(m["role"], m.get("nation")) for m in msgs] == [("joueur", None), ("dirigeant", "italie"),
                                                            ("dirigeant", "urss"), ("dirigeant", "pologne")]
    assert msgs[1]["texte"] == "Ma réponse de italie" and all(m["tour"] == 0 for m in msgs)


def test_02_reponse_manquante_inconnue_et_doublon(thibault, faux, app):
    pid = creer(thibault)
    rep = {"reponses": [{"nation": "Pologne", "texte": "Varsovie demande des garanties."},          # par le nom
                        {"nation": "atlantide", "texte": "Intrus"},                                    # inconnue : ignorée
                        {"nation": "pologne", "texte": "Doublon"},                                    # doublon : ignoré
                        {"nation": "italie", "texte": ""}]}                                           # vide : absent
    d = lancer(thibault, pid, faux, rep, "Qui me suit ?", ["italie", "pologne"])
    assert d["etat"] == "termine"
    assert d["resultat"]["reponses"] == [{"nation": "pologne", "texte": "Varsovie demande des garanties."}]
    assert d["resultat"]["manquants"] == ["italie"]                                      # signalé, rien de perdu
    assert len(faux.requetes) == 1
    flux = json.dumps(sauvegarde(app, pid)["conferences"], ensure_ascii=False)
    assert "Intrus" not in flux and "Doublon" not in flux
    # texte trop long : borné
    long = {"reponses": [{"nation": "italie", "texte": "x" * 2000}, {"nation": "pologne", "texte": "ok"}]}
    d = lancer(thibault, pid, faux, long, "encore", conference=d["resultat"]["conference"])
    assert len(d["resultat"]["reponses"][0]["texte"]) == aides.LONGUEUR_REPONSE_CONF


def test_02_aucune_reponse_utilisable_relance_une_fois(thibault, faux, app):
    pid = creer(thibault)
    vide = {"reponses": []}
    faux.programmer(vide)
    d = lancer(thibault, pid, faux, vide, "x", ["italie", "urss"])
    assert d["etat"] == "echec" and "inexploitable" in d["message"] and len(faux.requetes) == 2
    assert not sauvegarde(app, pid).get("conferences")                                   # rien d'orphelin
    ok = lancer(thibault, pid, faux, "<think>hm</think>" + json.dumps(reponses("italie", "urss")), "x", ["italie", "urss"])
    assert ok["etat"] == "termine"


# ------------------------------------------------------------------ 3
def test_03_qui_sait_quoi(thibault, faux, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    e["journal"] += [
        {"tour": 1, "date": "1939-09-05", "titre": "PACTE-NOIR-ALPHA", "texte": "Berlin et Moscou.", "pays": ["allemagne", "urss"], "secret": True},
        {"tour": 1, "date": "1939-09-06", "titre": "SECRET-ITALIE-SEUL", "texte": "x", "pays": ["france", "italie"], "secret": True},
        {"tour": 1, "date": "1939-09-07", "titre": "SECRET-PARTAGE-TOUS", "texte": "x", "pays": ["france", "italie", "urss"], "secret": True},
        {"tour": 1, "date": "1939-09-08", "titre": "Sommet public", "texte": "Rencontre publique.", "pays": ["italie"], "secret": False}]
    e["histoire"] += [{"tour": 1, "du": "1939-09-01", "au": "1939-10-01", "duree": "1mois",
                       "resume": "RESUME-SECRET-GAMMA", "ordres": ["x"]}]
    e["faits_etablis"] += ["FAIT-SECRET-DELTA"]
    e["corrections"] = ["CORRECTION-SECRETE-EPSILON"]
    e["conseiller"] = [{"de": "joueur", "texte": "CONSEIL-PRIVE", "tour": 0, "date": e["date"]}]
    e["diplomatie"] = {"italie": [{"de": "joueur", "texte": "DEUX-A-DEUX-ITALIE", "tour": 0, "date": e["date"]}]}
    e["tour"] = 1
    app.state.sauvegarde.enregistrer("thibault", e)
    lancer(thibault, pid, faux, reponses("italie", "urss"), "Parlons", ["italie", "urss"])
    lancer(thibault, pid, faux, reponses("italie", "pologne"), "Parlons", ["italie", "pologne"])
    a, b = (json.dumps(r, ensure_ascii=False) for r in faux.requetes)
    for flux in (a, b):
        for interdit in ("PACTE-NOIR-ALPHA", "RESUME-SECRET-GAMMA", "FAIT-SECRET-DELTA", "CORRECTION-SECRETE-EPSILON",
                         "CONSEIL-PRIVE", "DEUX-A-DEUX-ITALIE", "Tenir"):
            assert interdit not in flux
        assert "Sommet public" in flux                                                   # le public passe
        assert "SECRET-ITALIE-SEUL" not in flux                                          # connu d'un seul invité
    assert "SECRET-PARTAGE-TOUS" in a                                                    # joueur + Italie + URSS
    assert "SECRET-PARTAGE-TOUS" not in b                                                # la Pologne l'ignore
    assert "thibault" not in tout_envoye(faux).lower()


def test_03_garde_fou_de_construire_aide(etat39, noms):
    e = etat39
    e["journal"] += [{"tour": 1, "date": "1939-09-05", "titre": "PACTE-NOIR-ALPHA", "texte": "x", "pays": ["allemagne", "urss"], "secret": True}]
    e["histoire"] += [{"tour": 1, "du": "1939-09-01", "au": "1939-10-01", "duree": "1mois", "resume": "RESUME-SECRET-GAMMA", "ordres": []}]
    e["faits_etablis"] += ["FAIT-SECRET-DELTA"]
    for ctx in (131072, 8192):
        m, _ = aides.construire_aide(e, noms, "conference", ctx, "q", invites=["allemagne", "urss"])
        flux = json.dumps(m, ensure_ascii=False)
        assert not any(s in flux for s in ("PACTE-NOIR-ALPHA", "RESUME-SECRET-GAMMA", "FAIT-SECRET-DELTA"))
        assert moteur.estimer_jetons(m) <= ctx - 4096


# ------------------------------------------------------------------ 4
def test_04_transmis_au_narrateur(thibault, faux, app):
    pid = creer(thibault)
    lancer(thibault, pid, faux, reponses("italie", "urss"), "Je promets de défendre la Pologne", ["italie", "urss"])
    jouer(thibault, pid, faux, reponse(1))
    narrateur = faux.requetes[-1]["messages"][-1]["content"]
    assert "Discussions diplomatiques depuis le dernier tour" in narrateur
    nom = lambda i: sauvegarde(app, pid)["nations"][i]["nom"]
    assert f"Conférence : {nom('italie')} [italie], {nom('urss')} [urss]" in narrateur
    assert "Je promets de défendre la Pologne" in narrateur and "Ma réponse de urss" in narrateur
    jouer(thibault, pid, faux, reponse(1))                                              # consommé
    assert "Je promets de défendre" not in faux.requetes[-1]["messages"][-1]["content"]


def test_04_budget_de_contexte(etat39, noms):
    e = etat39
    e["tour"] = 5
    for nid in ("allemagne", "italie"):
        e["diplomatie"][nid] = [{"de": "joueur" if i % 2 == 0 else "dirigeant", "texte": f"{nid} {i} " + "blabla " * 140,
                                 "tour": 5, "date": e["date"]} for i in range(24)]
    e["conferences"] = [{"id": "c000001", "nations": ["italie", "urss", "pologne"], "messages": [
        {"role": "joueur" if i % 4 == 0 else "dirigeant", "nation": ["italie", "urss", "pologne"][i % 3],
         "texte": f"conf {i} " + "blabla " * 85, "tour": 5} for i in range(60)]}]
    ordres = ["Ordre capital numéro un", "Ordre capital numéro deux"]
    complet, infos = moteur.construire_requete(e, noms, ordres, "1mois", 131072)
    assert "conf 59 " in complet[-1]["content"] and "conf 39 " not in complet[-1]["content"]   # 20 derniers
    messages, infos = moteur.construire_requete(e, noms, ordres, "1mois", 8192)
    assert moteur.estimer_jetons(messages) <= 8192 - 4096
    assert infos["dialogues"] >= 1
    assert "1. Ordre capital numéro un" in messages[-1]["content"] and "Daladier" in messages[-1]["content"]


# ------------------------------------------------------------------ 5
def test_05_bornes_et_anciennes_sauvegardes(thibault, faux, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    e.pop("conferences", None)
    app.state.sauvegarde.enregistrer("thibault", e)                                      # ancienne sauvegarde
    assert thibault.get(f"/partie/{pid}").status == 200
    d = lancer(thibault, pid, faux, reponses("italie", "urss"), "premier", ["italie", "urss"])
    cid = d["resultat"]["conference"]
    assert conf(thibault, pid, "x" * 1001, conference=cid).status == 400
    assert conf(thibault, pid, "   ", conference=cid).status == 400
    assert conf(thibault, pid, 12, conference=cid).status == 400
    e = sauvegarde(app, pid)
    e["conferences"][0]["messages"] = [{"role": "joueur", "texte": f"m{i}", "tour": 0} for i in range(aides.MESSAGES_GARDES)]
    app.state.sauvegarde.enregistrer("thibault", e)
    faux.requetes.clear()
    lancer(thibault, pid, faux, reponses("italie", "urss"), "dernier", conference=cid)
    msgs = sauvegarde(app, pid)["conferences"][0]["messages"]
    assert len(msgs) == aides.MESSAGES_GARDES and msgs[-1]["texte"] == "Ma réponse de urss"      # borné à 60
    envoye = faux.requetes[0]["messages"][-1]["content"]
    assert "m39" not in envoye and "m40" in envoye and "m59" in envoye
    assert envoye.count("- Le joueur : m") == aides.MESSAGES_ENVOYES                    # 20 derniers envoyés
    page = thibault.get(f"/partie/{pid}").texte
    assert "ponse de urss" in page and "max_conference" in page                     # rendue au rechargement


def test_05_annulation_garde_les_conferences(thibault, faux, app):
    pid = creer(thibault)
    lancer(thibault, pid, faux, reponses("italie", "urss"), "Salut", ["italie", "urss"])
    jouer(thibault, pid, faux, reponse(1))
    assert thibault.post(f"/partie/{pid}/annuler", entetes=ORIG).status == 303
    e = sauvegarde(app, pid)
    assert e["tour"] == 0 and e["conferences"][0]["messages"][0]["texte"] == "Salut"
    assert all("conferences" not in h for h in e["historique"])


def test_05_le_texte_de_l_ia_reste_du_texte(thibault, faux):
    pid = creer(thibault)
    lancer(thibault, pid, faux, {"reponses": [{"nation": "italie", "texte": "</script><img src=x onerror=alert(1)>"},
                                              {"nation": "urss", "texte": "ok"}]}, "salut", ["italie", "urss"])
    page = thibault.get(f"/partie/{pid}").texte
    assert "</script><img" not in page and page.count("</script>") == page.count("<script")


# ------------------------------------------------------------------ 6
def test_06_meme_file_et_attente(thibault, lea, faux, app):
    faux.pause, faux.morceau = 0.1, 20
    p1, p2 = creer(thibault), creer(lea)
    faux.programmer(reponses("italie", "urss"), {"reponse": "deux"})
    assert conf(thibault, p1, "a", ["italie", "urss"]).status == 202
    assert lea.post(f"/partie/{p2}/aide", json_={"genre": "conseiller", "message": "b"}, entetes=ORIG).status == 202
    d = lea.get(f"/partie/{p2}/aide").json()
    assert d["etat"] == "attente" and d["message"] == "en attente, 1 demande avant vous"
    assert conf(thibault, p1, "encore", ["italie", "urss"]).status == 409                # une seule aide à la fois
    assert attendre_aide(thibault, p1)["etat"] == "termine" and attendre_aide(lea, p2)["etat"] == "termine"


def test_06_conference_apres_un_tour_aucune_ecriture_perdue(thibault, faux, app):
    faux.pause, faux.morceau = 0.1, 20
    pid = creer(thibault)
    faux.programmer(reponse(1), reponses("italie", "urss"))
    assert avancer(thibault, pid).status == 202
    assert conf(thibault, pid, "pendant le tour", ["italie", "urss"]).status == 202
    assert thibault.get(f"/partie/{pid}/aide").json()["message"] == "en attente, 1 demande avant vous"
    assert attendre(thibault, pid)["etat"] == "termine" and attendre_aide(thibault, pid)["etat"] == "termine"
    e = sauvegarde(app, pid)
    assert e["tour"] == 1 and e["conferences"][0]["messages"][0]["texte"] == "pendant le tour"


def test_06_pc_eteint_rien_de_perdu(thibault, faux, app):
    pid = creer(thibault)
    d = lancer(thibault, pid, faux, reponses("italie", "urss"), "avant", ["italie", "urss"])
    cid = d["resultat"]["conference"]
    avant = sauvegarde(app, pid)["conferences"]
    faux.eteindre()
    assert conf(thibault, pid, "perdu ?", conference=cid).status == 202
    d = attendre_aide(thibault, pid)
    assert d["etat"] == "echec" and "Le PC de l'IA ne répond pas" in d["message"] and "Rien n'est perdu" in d["message"]
    assert conf(thibault, pid, "perdu ?", ["pologne", "urss"]).status == 202
    assert attendre_aide(thibault, pid)["etat"] == "echec"
    assert sauvegarde(app, pid)["conferences"] == avant


def test_06_annulation_refusee_pendant_une_conference(thibault, faux, app):
    pid = creer(thibault)
    faux.programmer(reponse(1))
    assert avancer(thibault, pid).status == 202
    attendre(thibault, pid)
    faux.pause, faux.morceau = 0.1, 20
    faux.programmer(reponses("italie", "urss"))
    assert conf(thibault, pid, "lent", ["italie", "urss"]).status == 202
    assert thibault.post(f"/partie/{pid}/annuler", entetes=ORIG).status == 409
    attendre_aide(thibault, pid)
    assert thibault.post(f"/partie/{pid}/annuler", entetes=ORIG).status in (200, 303)


def test_06_partie_terminee_refusee(thibault, faux, app):
    pid = creer(thibault)
    e = sauvegarde(app, pid)
    e["territoires"] = {t: ("allemagne" if n == "france" else n) for t, n in e["territoires"].items()}
    app.state.sauvegarde.enregistrer("thibault", e)
    assert conf(thibault, pid, "x", ["italie", "urss"]).status == 409


def test_03_invite_tardif_ne_lit_pas_ce_qui_precede(thibault, faux, app):
    # relecture : un secret dit avant l'arrivée d'un invité ne doit pas lui être transmis
    pid = creer(thibault)
    lancer(thibault, pid, faux, reponses("royaume-uni", "pologne", texte="PLAN-SECRET-X1"),
           "Notre PLAN-SECRET-X1 contre Berlin", ["royaume-uni", "pologne"])
    cid = app.state.sauvegarde.lire("thibault", pid)["conferences"][0]["id"]
    assert inviter(thibault, pid, cid, "etats-unis").status == 200
    lancer(thibault, pid, faux, reponses("royaume-uni", "pologne", "etats-unis"), "Bienvenue", conference=cid)
    assert "PLAN-SECRET-X1" not in json.dumps(faux.requetes[-1], ensure_ascii=False)
    assert "PLAN-SECRET-X1" in json.dumps(faux.requetes[0], ensure_ascii=False)


def test_06_invitation_refusee_pendant_la_reponse(thibault, faux, app):
    pid = creer(thibault)
    lancer(thibault, pid, faux, reponses("italie", "urss"), "a", ["italie", "urss"])
    cid = app.state.sauvegarde.lire("thibault", pid)["conferences"][0]["id"]
    faux.pause, faux.morceau = 0.1, 20
    faux.programmer(reponses("italie", "urss"))
    assert conf(thibault, pid, "lent", conference=cid).status == 202
    assert inviter(thibault, pid, cid, "pologne").status == 409
    attendre_aide(thibault, pid)
    assert inviter(thibault, pid, cid, "pologne").status == 200


def test_css_bloc_inviter_masquable():
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "app" / "static" / "style.css").read_text(encoding="utf-8")
    assert ".conf-inviter[hidden]" in css
