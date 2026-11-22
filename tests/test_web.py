import json
import re
from pathlib import Path

import yaml

from tests.client import Client
from tests.faux_ollama import FauxOllama

ORIG = {"Origin": "http://testserver"}


def creer(client, scenario="seconde-guerre-1939", nation="france", objectif="Tenir"):
    r = client.post("/parties", donnees={"scenario": scenario, "nation": nation, "objectif": objectif},
                    entetes=ORIG)
    assert r.status == 303, r.texte
    return r.headers["location"].rsplit("/", 1)[1]


def test_401_sans_identifiant(anonyme):
    for chemin in ("/", "/nouvelle", "/moi", "/api/ia/statut"):
        assert anonyme.get(chemin).status == 401


def test_moi(thibault, lea):
    assert thibault.get("/moi").json() == {"utilisateur": "thibault", "admin": True}
    assert lea.get("/moi").json() == {"utilisateur": "lea", "admin": False}


def _basic(login):
    import base64
    return {"Authorization": "Basic " + base64.b64encode(f"{login}:-".encode()).decode()}


def test_identifiant_invalide_refuse(app):
    assert Client(app, _basic("../etc")).get("/").status == 401


def test_parcours_scenarios_et_carte(thibault):
    r = thibault.get("/nouvelle")
    assert r.status == 200 and "Seconde Guerre mondiale" in r.texte and "Monde actuel" in r.texte
    r = thibault.get("/nouvelle/seconde-guerre-1939")
    assert r.status == 200 and 'id="t-POL"' in r.texte
    assert thibault.get("/nouvelle/inconnu").status == 404


def test_creation_reprise_identique(thibault, app):
    pid = creer(thibault)
    r = thibault.get(f"/partie/{pid}")
    assert r.status == 200 and "France" in r.texte
    fichier = app.state.config.data / "parties" / "thibault" / f"{pid}.json"
    avant = json.loads(fichier.read_text())
    assert avant["nation_joueur"] == "france" and avant["version_format"] == 1
    # reprise : relire puis réenregistrer ne change rien d'important
    etat = app.state.sauvegarde.lire("thibault", pid)
    app.state.sauvegarde.enregistrer("thibault", etat)
    apres = json.loads(fichier.read_text())
    avant.pop("modifie_le"), apres.pop("modifie_le")
    assert avant == apres


def test_nation_non_jouable_ou_inconnue(thibault):
    r = thibault.post("/parties", donnees={"scenario": "monde-actuel", "nation": "zzz"}, entetes=ORIG)
    assert r.status == 400


def test_isolation_entre_joueurs(thibault, lea):
    pid = creer(thibault)
    assert lea.get(f"/partie/{pid}").status == 404
    assert lea.post(f"/partie/{pid}/supprimer", entetes=ORIG).status == 404
    assert thibault.get(f"/partie/{pid}").status == 200
    assert pid not in lea.get("/").texte
    assert pid in thibault.get("/").texte


def test_suppression(thibault):
    pid = creer(thibault)
    assert thibault.post(f"/partie/{pid}/supprimer", entetes=ORIG).status == 303
    assert thibault.get(f"/partie/{pid}").status == 404


def test_identifiant_de_partie_malveillant(thibault):
    assert thibault.get("/partie/..%2F..%2Fx").status == 404


def test_csrf(thibault):
    r = thibault.post("/parties", donnees={"scenario": "monde-actuel", "nation": "france"},
                      entetes={"Origin": "http://evil.example"})
    assert r.status == 403
    r = thibault.post("/parties", donnees={"scenario": "monde-actuel", "nation": "france"},
                      entetes={"Sec-Fetch-Site": "cross-site"})
    assert r.status == 403


def test_reglages_reserves_aux_admins(lea, thibault):
    assert lea.get("/reglages").status == 403
    assert lea.post("/reglages", donnees={}, entetes=ORIG).status == 403
    assert thibault.get("/reglages").status == 200


def test_statut_ia_hors_ligne_et_en_ligne(app, thibault, lea):
    r = thibault.get("/api/ia/statut").json()
    assert r["ok"] is False and r["pret"] is False
    with FauxOllama(["llama3.1:8b"]) as faux:
        r = thibault.post("/reglages", donnees={"ollama_adresse": faux.adresse, "modele": "llama3.1:8b",
                                                "contexte": "16384"}, entetes=ORIG)
        assert r.status == 200 and "enregistrés" in r.texte
        s = lea.get("/api/ia/statut").json()
        assert s["pret"] is True and "detail" not in s       # un non-admin ne voit pas les détails
        assert thibault.get("/api/ia/statut").json()["modele"] == "llama3.1:8b"
        r = thibault.post("/reglages", donnees={"ollama_adresse": faux.adresse, "modele": "autre",
                                                "contexte": "16384"}, entetes=ORIG)
        assert "pas installé" in lea.get("/api/ia/statut").json()["message"]


def test_reglages_invalides(thibault):
    r = thibault.post("/reglages", donnees={"ollama_adresse": "ftp://x", "modele": "m", "contexte": "10"},
                      entetes=ORIG)
    assert r.status == 400


def test_tester_connexion(thibault, lea):
    with FauxOllama(["a", "b"]) as faux:
        r = thibault.post("/api/ia/tester", json_={"adresse": faux.adresse}, entetes=ORIG)
        assert r.json() == {"ok": True, "message": "Connexion OK", "modeles": ["a", "b"]}
    r = thibault.post("/api/ia/tester", json_={"adresse": "http://127.0.0.1:9"}, entetes=ORIG)
    assert r.json()["ok"] is False and r.json()["message"]
    assert lea.post("/api/ia/tester", json_={"adresse": "http://127.0.0.1:9"}, entetes=ORIG).status == 403


def test_scenario_ajoute_a_la_main(thibault, config):
    d = config.data / "scenarios"
    d.mkdir(parents=True)
    (d / "mini.yaml").write_text(yaml.safe_dump({
        "id": "mini", "nom": "Mini monde", "date_depart": "1900-01-01", "description": "d", "contexte": "c",
        "nations": [{"id": "a", "nom": "A", "couleur": "#112233", "territoires": ["FRA"]}]}), encoding="utf-8")
    assert "Mini monde" in thibault.get("/nouvelle").texte


def test_scenario_fautif_signale(thibault, config):
    d = config.data / "scenarios"
    d.mkdir(parents=True)
    (d / "faux.yaml").write_text("id: x\nnom: X\n", encoding="utf-8")
    r = thibault.get("/nouvelle")
    assert r.status == 200 and "faux.yaml" in r.texte and "Monde actuel" in r.texte


def test_bouton_avancer_desactive_au_rendu_et_etat_sans_ia(thibault):
    pid = creer(thibault, scenario="monde-actuel", nation="france")
    t = thibault.get(f"/partie/{pid}").texte
    assert 'id="avancer"' in t and "data-bientot" not in t and "disabled" in t
    assert "22 novembre 2026" in t


def test_cartes_pas_d_injection_dans_objectif(thibault):
    pid = creer(thibault, objectif="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in thibault.get(f"/partie/{pid}").texte


def test_remote_user_ignore(app):
    # SSOwat n'écrase pas Remote-User : un joueur ne doit pas pouvoir se faire passer pour un autre
    assert Client(app, {"Remote-User": "thibault"}).get("/moi").status == 401
    r = Client(app, {**_basic("lea"), "Remote-User": "thibault"}).get("/moi").json()
    assert r == {"utilisateur": "lea", "admin": False}


def test_authorization_mal_formee(app):
    assert Client(app, {"Authorization": "Basic %%%"}).get("/moi").status == 401
    assert Client(app, {"Authorization": "Bearer abc"}).get("/moi").status == 401


def test_identifiants_point_refuses(app):
    assert Client(app, _basic("..")).get("/").status == 401


def test_adresse_ollama_invalide(thibault):
    r = thibault.post("/reglages", donnees={"ollama_adresse": "http://127.0.0.1:abc", "modele": "m",
                                            "contexte": "16384"}, entetes=ORIG)
    assert r.status == 400


def test_port_non_http_ne_plante_pas(thibault):
    import socket, threading
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1)
    def serv():
        c, _ = s.accept(); c.sendall(b"SSH-2.0-faux\r\n"); c.close()
    threading.Thread(target=serv, daemon=True).start()
    r = thibault.post("/api/ia/tester", json_={"adresse": f"http://127.0.0.1:{s.getsockname()[1]}"}, entetes=ORIG)
    assert r.status == 200 and r.json()["ok"] is False
    s.close()
