"""Le serveur web de pax (Starlette).

Lancement : uvicorn --factory app.main:creer_app
Qui est le joueur : YunoHost 12 (SSOwat) le transmet dans l'en-tête Authorization (Basic).
Le serveur n'écoute que sur 127.0.0.1 : seul nginx peut lui parler.
"""
from __future__ import annotations

import asyncio
import base64
import functools
import re
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from . import __version__
from .carte import Carte
from .config import Config
from . import aides, execution, tour as moteur
from .monde import est_disparue, etat_initial, evenements_visibles, fiche_nation, resume_etat, date_fr, PALIERS, LIBELLES_CHIFFRES
from .ollama import OllamaIndisponible, lister_modeles, normaliser_adresse
from .reglages import Reglages
from .sauvegarde import PartieIntrouvable, Sauvegarde, UTILISATEUR
from .scenarios import charger_dossiers

CONF_ID = re.compile(r"c[0-9a-f]{6}")
LONGUEUR_OBJECTIF = 500
DELAI_STATUT = 3.0          # secondes avant de dire que le PC de l'IA ne répond pas
VALIDITE_STATUT = 5.0       # on ne redemande pas à Ollama plus souvent


# ------------------------------------------------------------------ identification
def utilisateur(request: Request) -> str | None:
    """Le joueur, d'après l'en-tête Authorization que SSOwat (YunoHost 12) pose à chaque requête.

    SSOwat remplace cet en-tête par « Basic base64(identifiant:-) » ; on ne lit que l'identifiant.
    Remote-User n'est PAS lu : SSOwat ne l'écrase pas, un joueur pourrait l'envoyer lui-même.
    """
    cfg: Config = request.app.state.config
    if cfg.utilisateur_dev:
        return cfg.utilisateur_dev
    auth = request.headers.get("authorization", "")
    if not auth[:6].lower() == "basic ":
        return None
    try:
        login = base64.b64decode(auth[6:].strip(), validate=True).decode("utf-8").split(":", 1)[0]
    except (ValueError, UnicodeDecodeError):
        return None
    if UTILISATEUR.fullmatch(login) and login not in (".", ".."):
        return login
    return None


def origine_ok(request: Request) -> bool:
    """Refuse une écriture demandée depuis une autre page web (protection CSRF)."""
    site = request.headers.get("sec-fetch-site")
    if site and site not in ("same-origin", "none"):
        return False
    origine = request.headers.get("origin")
    if origine:
        hote = (request.headers.get("x-forwarded-host") or request.headers.get("host", "")).split(",")[0].strip()
        return urlsplit(origine).netloc == hote
    return True


def protege(admin: bool = False, ecriture: bool = False):
    def deco(fn):
        @functools.wraps(fn)
        async def enveloppe(request: Request):
            cfg: Config = request.app.state.config
            user = utilisateur(request)
            if not user:
                return erreur(request, 401, "Connexion requise",
                              "Connectez-vous avec votre compte YunoHost pour jouer.")
            request.state.user = user
            if ecriture and not origine_ok(request):
                return erreur(request, 403, "Demande refusée", "Cette demande vient d'une autre page web.")
            if admin and user not in cfg.admins:
                return erreur(request, 403, "Réservé aux administrateurs", "Vous n'avez pas accès à cette page.")
            return await fn(request)
        return enveloppe
    return deco


# ------------------------------------------------------------------ outils de page
def contexte(request: Request, **kw) -> dict:
    cfg: Config = request.app.state.config
    user = getattr(request.state, "user", None)
    return {"request": request, "user": user, "admin": bool(user and user in cfg.admins),
            "version": __version__, **kw}


def page(request: Request, nom: str, statut: int = 200, **kw) -> Response:
    return request.app.state.templates.TemplateResponse(request, nom, contexte(request, **kw), status_code=statut)


def erreur(request: Request, statut: int, titre: str, texte: str) -> Response:
    return page(request, "erreur.html", statut, titre=titre, texte=texte)


def scenarios_et_erreurs(request: Request):
    app = request.app
    return charger_dossiers(app.state.config.scenarios, app.state.carte.noms)


async def formulaire(request: Request) -> dict[str, str]:
    corps = (await request.body()).decode("utf-8", errors="replace")
    return {k: v[0] for k, v in parse_qs(corps, keep_blank_values=True).items()}


def donnees_carte(carte: Carte, etat: dict) -> dict:
    return {
        "noms": carte.noms,
        "nations": {nid: n["nom"] for nid, n in etat["nations"].items()},
        "fiches": {nid: fiche_nation(etat, nid, carte.noms) for nid in etat["nations"]},
        "territoires": etat["territoires"],
        "joueur": etat["nation_joueur"],
    }


# ------------------------------------------------------------------ pages
@protege()
async def accueil(request: Request):
    parties = request.app.state.sauvegarde.lister(request.state.user)
    return page(request, "accueil.html", parties=parties)


@protege()
async def nouvelle(request: Request):
    scenarios, erreurs = scenarios_et_erreurs(request)
    liste = sorted(scenarios.values(), key=lambda s: s["date_depart"], reverse=True)
    for s in liste:
        s["date_lisible"] = date_fr(s["date_depart"])
    return page(request, "nouvelle.html", scenarios=liste, erreurs=erreurs)


@protege()
async def nouvelle_carte(request: Request):
    scenarios, _ = scenarios_et_erreurs(request)
    s = scenarios.get(request.path_params["sid"])
    if not s:
        return erreur(request, 404, "Scénario introuvable", "Ce scénario n'existe pas (ou plus).")
    carte: Carte = request.app.state.carte
    premier = next((n for n, v in s["nations"].items() if v["jouable"]), None)
    if premier is None:
        return erreur(request, 404, "Scénario injouable", "Aucune nation n'est jouable dans ce scénario.")
    etat = etat_initial(s, premier)
    data = donnees_carte(carte, etat)
    data["conseil"] = s["conseil_nations"]
    data["joueur"] = None            # on choisit sa nation en cliquant
    data["jouables"] = [n for n, v in s["nations"].items() if v["jouable"]]
    return page(request, "nouvelle_carte.html", scenario=s, date_lisible=date_fr(s["date_depart"]),
                svg=carte.svg(etat["territoires"], etat["nations"]), data=data,
                max_objectif=LONGUEUR_OBJECTIF)


@protege(ecriture=True)
async def creer_partie(request: Request):
    f = await formulaire(request)
    scenarios, _ = scenarios_et_erreurs(request)
    s = scenarios.get(f.get("scenario", ""))
    nation = f.get("nation", "")
    objectif = f.get("objectif", "")
    if not s or nation not in s["nations"] or not s["nations"][nation]["jouable"]:
        return erreur(request, 400, "Demande invalide", "Scénario ou nation inconnus.")
    if len(objectif) > LONGUEUR_OBJECTIF:
        return erreur(request, 400, "Objectif trop long", f"{LONGUEUR_OBJECTIF} caractères au plus.")
    etat = etat_initial(s, nation, objectif)
    pid = request.app.state.sauvegarde.creer(request.state.user, etat)
    return RedirectResponse(f"{request.app.state.config.prefixe}/partie/{pid}", status_code=303)


@protege()
async def partie(request: Request):
    try:
        etat = request.app.state.sauvegarde.lire(request.state.user, request.path_params["pid"])
    except PartieIntrouvable:
        return erreur(request, 404, "Partie introuvable", "Cette partie n'existe pas ou n'est pas à vous.")
    carte: Carte = request.app.state.carte
    visibles = evenements_visibles(etat)
    par_tour: dict[int, list[dict]] = {}
    for e in reversed(visibles):
        par_tour.setdefault(e["tour"], []).append({**e, "date_lisible": date_fr(e["date"])})
    mesures = {h["tour"]: _mesure_lisible(h["mesure"]) for h in etat.get("histoire", []) if h.get("mesure")}
    brouillon = etat.get("brouillon") or {}
    interlocuteurs = sorted(({"id": nid, "nom": n["nom"], "dirigeant": n["dirigeant"]}
                             for nid, n in etat["nations"].items()
                             if nid != etat["nation_joueur"] and not est_disparue(etat, nid)),
                            key=lambda x: x["nom"].casefold())
    dip = etat.get("diplomatie") or {}
    donnees_aides = {"conseiller": etat.get("conseiller") or [],
                     "conferences": etat.get("conferences") or [],
                     "max_conference": aides.MAX_CONFERENCE,
                     "noms": {nid: n["nom"] for nid, n in etat["nations"].items()},
                     "dirigeants": {nid: n["dirigeant"] for nid, n in etat["nations"].items()},
                     "vivantes": [x["id"] for x in interlocuteurs],
                     "diplomatie": {x["id"]: dip.get(x["id"]) or [] for x in interlocuteurs if dip.get(x["id"])},
                     "rapport": etat.get("rapport")}
    return page(request, "partie.html", etat=etat, resume=resume_etat(etat, carte.noms),
                svg=carte.svg(etat["territoires"], etat["nations"]), data=donnees_carte(carte, etat),
                paliers=PALIERS, libelles=LIBELLES_CHIFFRES, durees=moteur.DUREES,
                journal=sorted(par_tour.items(), reverse=True), mesures=mesures, fin=moteur.partie_terminee(etat),
                ordres_saisis=brouillon.get("ordres") or [""],
                duree_choisie=brouillon.get("duree") or (etat.get("dernier_tour") or {}).get("duree") or moteur.DUREE_DEFAUT,
                dernier=etat.get("dernier_tour"), corrections=etat.get("corrections_joueur") or [],
                peut_annuler=bool(etat.get("historique")), max_ordres=moteur.MAX_ORDRES,
                longueur_ordre=moteur.LONGUEUR_ORDRE, interlocuteurs=interlocuteurs,
                donnees_aides=donnees_aides, longueur_message=aides.LONGUEUR_MESSAGE)


@protege(ecriture=True)
async def lancer_tour(request: Request):
    """Démarre un tour en arrière-plan ; la page suit sa progression avec GET /partie/<id>/tour."""
    app = request.app
    user, pid = request.state.user, request.path_params["pid"]
    try:
        app.state.sauvegarde.lire(user, pid)
    except PartieIntrouvable:
        return JSONResponse({"ok": False, "message": "Cette partie n'existe pas ou n'est pas à vous."}, status_code=404)
    try:
        donnees = await request.json()
        ordres = moteur.nettoyer_ordres(donnees.get("ordres"))
        duree = donnees.get("duree")
        if duree not in moteur.DUREES:
            raise ValueError("Choisissez une durée.")
    except (ValueError, AttributeError) as e:
        return JSONResponse({"ok": False, "message": str(e) or "Demande mal formée."}, status_code=400)
    if not app.state.reglages.lire()["modele"]:
        return JSONResponse({"ok": False, "message": "Aucun modèle n'est choisi dans les réglages."}, status_code=409)
    tours: execution.Gestionnaire = app.state.tours
    with tours.verrou:
        if tours.actif(user, pid):
            return JSONResponse({"ok": False, "message": "Un tour est déjà en cours pour cette partie."}, status_code=409)
        try:
            etat = app.state.sauvegarde.lire(user, pid)       # relu sous verrou : jamais d'écrasement d'un tour fini
        except PartieIntrouvable:
            return JSONResponse({"ok": False, "message": "Cette partie n'existe pas ou n'est pas à vous."}, status_code=404)
        if moteur.partie_terminee(etat):
            return JSONResponse({"ok": False, "message": "La partie est terminée."}, status_code=409)
        etat["brouillon"] = {"ordres": ordres, "duree": duree}      # les ordres survivent à un échec
        app.state.sauvegarde.enregistrer(user, etat)
        tours.lancer(app, user, pid, ordres, duree)
    return JSONResponse({"ok": True}, status_code=202)


@protege(ecriture=True)
async def demander_aide(request: Request):
    """Démarre une aide de l'IA (rapport, conseiller, dirigeant) ; suivi par GET /partie/<id>/aide."""
    app = request.app
    user, pid = request.state.user, request.path_params["pid"]
    introuvable = JSONResponse({"ok": False, "message": "Cette partie n'existe pas ou n'est pas à vous."}, status_code=404)
    try:
        app.state.sauvegarde.lire(user, pid)
    except PartieIntrouvable:
        return introuvable
    try:
        donnees = await request.json()
        genre = donnees.get("genre")
        if genre not in aides.GENRES:
            raise ValueError("Aide inconnue.")
        message = aides.nettoyer_message(donnees.get("message")) if genre != "rapport" else ""
        nation = donnees.get("nation") if genre == "diplomatie" else ""
        conf_id, conf_nations = "", []
        if genre == "conference":
            conf_id = donnees.get("conference")
            conf_nations = donnees.get("nations")
            if conf_id is not None and not (isinstance(conf_id, str) and CONF_ID.fullmatch(conf_id)):
                raise ValueError("Conférence inconnue.")
            if conf_id is None and not isinstance(conf_nations, list):
                raise ValueError("Choisissez les nations de la conférence.")
    except (ValueError, AttributeError) as e:
        return JSONResponse({"ok": False, "message": str(e) or "Demande mal formée."}, status_code=400)
    if not app.state.reglages.lire()["modele"]:
        return JSONResponse({"ok": False, "message": "Aucun modèle n'est choisi dans les réglages."}, status_code=409)
    tours: execution.Gestionnaire = app.state.tours
    with tours.verrou:
        if tours.aide_active(user, pid):
            return JSONResponse({"ok": False, "message": "Une demande à l'IA est déjà en cours pour cette partie."}, status_code=409)
        try:
            etat = app.state.sauvegarde.lire(user, pid)
        except PartieIntrouvable:
            return introuvable
        if moteur.partie_terminee(etat):
            return JSONResponse({"ok": False, "message": "La partie est terminée."}, status_code=409)
        if genre == "diplomatie" and not (isinstance(nation, str) and nation in etat["nations"]
                                          and nation != etat["nation_joueur"] and not est_disparue(etat, nation)):
            return JSONResponse({"ok": False, "message": "Choisissez une nation qui existe encore."}, status_code=400)
        if genre == "conference":
            if conf_id:
                conf = aides.trouver_conference(etat, conf_id)
                if conf is None:
                    return JSONResponse({"ok": False, "message": "Cette conférence n'existe pas."}, status_code=400)
                if not any(i in etat["nations"] and not est_disparue(etat, i) for i in conf["nations"]):
                    return JSONResponse({"ok": False, "message": "Tous les invités ont disparu."}, status_code=400)
                conf_nations = []
            else:
                faute = _verifier_invites(etat, conf_nations, 2)
                if faute:
                    return JSONResponse({"ok": False, "message": faute}, status_code=400)
                conf_id = "c" + secrets.token_hex(3)
                while aides.trouver_conference(etat, conf_id):
                    conf_id = "c" + secrets.token_hex(3)
        tours.lancer_aide(app, user, pid, genre, message, nation or "", conf_id or "", conf_nations)
    return JSONResponse({"ok": True}, status_code=202)


def _verifier_invites(etat: dict, nations, minimum: int) -> str | None:
    """Une faute lisible, ou None si la liste d'invités est valable (2 à 5, vivantes, pas la sienne, sans doublon)."""
    if not (isinstance(nations, list) and all(isinstance(n, str) for n in nations)):
        return "Choisissez les nations de la conférence."
    if len(set(nations)) != len(nations):
        return "Une nation ne peut être invitée qu'une fois."
    if not minimum <= len(nations) <= aides.MAX_CONFERENCE:
        return f"Une conférence réunit de {minimum} à {aides.MAX_CONFERENCE} nations."
    if any(n not in etat["nations"] or n == etat["nation_joueur"] or est_disparue(etat, n) for n in nations):
        return "Choisissez des nations qui existent encore, autres que la vôtre."
    return None


@protege(ecriture=True)
async def inviter_conference(request: Request):
    """Invite une nation de plus à une conférence (5 au plus)."""
    app = request.app
    user, pid, cid = request.state.user, request.path_params["pid"], request.path_params["cid"]
    try:
        donnees = await request.json()
        nation = donnees.get("nation")
    except (ValueError, AttributeError) as e:
        return JSONResponse({"ok": False, "message": "Demande mal formée."}, status_code=400)
    with app.state.tours.verrou:
        try:
            etat = app.state.sauvegarde.lire(user, pid)
        except PartieIntrouvable:
            return JSONResponse({"ok": False, "message": "Cette partie n'existe pas ou n'est pas à vous."}, status_code=404)
        conf = aides.trouver_conference(etat, cid)
        if conf is None:
            return JSONResponse({"ok": False, "message": "Cette conférence n'existe pas."}, status_code=404)
        if moteur.partie_terminee(etat):
            return JSONResponse({"ok": False, "message": "La partie est terminée."}, status_code=409)
        if app.state.tours.aide_active(user, pid):
            return JSONResponse({"ok": False, "message": "Attendez la réponse de l'IA avant d'inviter."}, status_code=409)
        if len(conf["nations"]) >= aides.MAX_CONFERENCE:
            return JSONResponse({"ok": False, "message": f"Une conférence réunit {aides.MAX_CONFERENCE} nations au plus."}, status_code=400)
        if isinstance(nation, str) and nation in conf["nations"]:
            return JSONResponse({"ok": False, "message": "Cette nation est déjà invitée."}, status_code=400)
        faute = _verifier_invites(etat, [nation], 1)
        if faute:
            return JSONResponse({"ok": False, "message": faute}, status_code=400)
        conf["nations"].append(nation)
        conf["coupure"] = len(conf.get("messages") or [])   # le nouvel invité ne lit pas ce qui précède
        app.state.sauvegarde.enregistrer(user, etat)
    return JSONResponse({"ok": True, "nations": conf["nations"]})


@protege()
async def progression_aide(request: Request):
    try:
        request.app.state.sauvegarde.lire(request.state.user, request.path_params["pid"])
    except PartieIntrouvable:
        return JSONResponse({"etat": "aucun"}, status_code=404)
    d = request.app.state.tours.consulter_aide(request.state.user, request.path_params["pid"],
                                               initial=request.query_params.get("initial") == "1")
    return JSONResponse(d, headers={"Cache-Control": "no-store"})


@protege()
async def progression_tour(request: Request):
    d = request.app.state.tours.consulter(request.state.user, request.path_params["pid"],
                                          initial=request.query_params.get("initial") == "1")
    return JSONResponse(d, headers={"Cache-Control": "no-store"})


@protege(ecriture=True)
async def annuler_tour(request: Request):
    app = request.app
    user, pid = request.state.user, request.path_params["pid"]
    try:
        execution.annuler(app, user, pid)
    except execution.TourEnCours as e:
        return erreur(request, 409, "Un tour est en cours", str(e))
    except PartieIntrouvable:
        return erreur(request, 404, "Partie introuvable", "Cette partie n'existe pas ou n'est pas à vous.")
    except ValueError as e:
        return erreur(request, 400, "Rien à annuler", str(e))
    return RedirectResponse(f"{app.state.config.prefixe}/partie/{pid}", status_code=303)


@protege(ecriture=True)
async def supprimer_partie(request: Request):
    app, user, pid = request.app, request.state.user, request.path_params["pid"]
    with app.state.tours.verrou:
        if app.state.tours.actif(user, pid):
            return erreur(request, 409, "Un tour est en cours", "Attendez la fin du tour avant de supprimer la partie.")
        try:
            app.state.sauvegarde.supprimer(user, pid)
        except PartieIntrouvable:
            return erreur(request, 404, "Partie introuvable", "Cette partie n'existe pas ou n'est pas à vous.")
    return RedirectResponse(f"{request.app.state.config.prefixe}/", status_code=303)


# ------------------------------------------------------------------ IA
async def sonder(app: Starlette, adresse: str, delai: float = DELAI_STATUT) -> dict:
    """Interroge Ollama sans bloquer le serveur. Ne lève jamais."""
    try:
        modeles = await asyncio.to_thread(lister_modeles, adresse, delai)
    except OllamaIndisponible as e:
        return {"ok": False, "message": str(e), "modeles": []}
    except ValueError as e:
        return {"ok": False, "message": f"Adresse invalide : {e}", "modeles": []}
    return {"ok": True, "message": "Connexion OK", "modeles": modeles}


@protege()
async def statut_ia(request: Request):
    app = request.app
    cfg: Config = app.state.config
    reg = app.state.reglages.lire()
    cache = app.state.cache_statut
    if cache.get("adresse") != reg["ollama_adresse"] or time.monotonic() - cache.get("t", -1e9) > VALIDITE_STATUT:
        cache.update(res=await sonder(app, reg["ollama_adresse"]), t=time.monotonic(), adresse=reg["ollama_adresse"])
    res = cache["res"]
    pret = res["ok"] and bool(reg["modele"]) and reg["modele"] in res["modeles"]
    if not res["ok"]:
        message = "Le PC de l'IA ne répond pas."
    elif not reg["modele"]:
        message = "Aucun modèle n'est choisi dans les réglages."
    elif not pret:
        message = "Le modèle choisi n'est pas installé sur le PC de l'IA."
    else:
        message = "IA prête."
    corps = {"ok": res["ok"], "pret": pret, "message": message}
    if request.state.user in cfg.admins:
        corps["detail"] = res["message"]
        corps["modele"] = reg["modele"]
    return JSONResponse(corps, headers={"Cache-Control": "no-store"})


def lire_diagnostic(app) -> str | None:
    try:
        return execution.fichier_diagnostic(app.state.config.data).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


@protege(admin=True)
async def reglages_page(request: Request):
    reg = request.app.state.reglages.lire()
    return page(request, "reglages.html", reg=reg, message=None, faute=None, diagnostic=lire_diagnostic(request.app))


@protege(admin=True, ecriture=True)
async def reglages_enregistrer(request: Request):
    f = await formulaire(request)
    app = request.app
    try:
        reg = app.state.reglages.valider(f.get("ollama_adresse", ""), f.get("modele", ""), f.get("contexte", ""))
    except ValueError as e:
        return page(request, "reglages.html", 400, reg=app.state.reglages.lire(), message=None, faute=str(e),
                    diagnostic=lire_diagnostic(app))
    app.state.reglages.ecrire(reg)
    app.state.cache_statut.clear()
    return page(request, "reglages.html", reg=reg, message="Réglages enregistrés.", faute=None,
                diagnostic=lire_diagnostic(app))


@protege(admin=True, ecriture=True)
async def reglages_tester(request: Request):
    try:
        donnees = await request.json()
        adresse = normaliser_adresse(str(donnees.get("adresse", "")))
    except (ValueError, AttributeError):
        return JSONResponse({"ok": False, "message": "Adresse invalide.", "modeles": []}, status_code=400)
    res = await sonder(request.app, adresse, delai=5.0)
    return JSONResponse(res, headers={"Cache-Control": "no-store"})


@protege()
async def moi(request: Request):
    """Pour vérifier l'installation : qui le jeu croit-il que vous êtes ?"""
    cfg: Config = request.app.state.config
    return JSONResponse({"utilisateur": request.state.user, "admin": request.state.user in cfg.admins})


# ------------------------------------------------------------------ assemblage

def _mesure_lisible(m: dict) -> str:
    s = int(m.get("secondes") or 0)
    duree = f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"
    return f"joué en {duree} avec {m.get('modele') or '?'}" + (" (après une relance)" if m.get("relance") else "")

def creer_app(config: Config | None = None) -> Starlette:
    config = config or Config.depuis_env()
    racine = Path(__file__).resolve().parent
    app = Starlette(routes=[
        Route("/", accueil),
        Route("/nouvelle", nouvelle),
        Route("/nouvelle/{sid}", nouvelle_carte),
        Route("/parties", creer_partie, methods=["POST"]),
        Route("/partie/{pid}", partie),
        Route("/partie/{pid}/tour", lancer_tour, methods=["POST"]),
        Route("/partie/{pid}/tour", progression_tour),
        Route("/partie/{pid}/aide", demander_aide, methods=["POST"]),
        Route("/partie/{pid}/aide", progression_aide),
        Route("/partie/{pid}/conference/{cid}/inviter", inviter_conference, methods=["POST"]),
        Route("/partie/{pid}/annuler", annuler_tour, methods=["POST"]),
        Route("/partie/{pid}/supprimer", supprimer_partie, methods=["POST"]),
        Route("/reglages", reglages_page),
        Route("/reglages", reglages_enregistrer, methods=["POST"]),
        Route("/api/ia/statut", statut_ia),
        Route("/api/ia/tester", reglages_tester, methods=["POST"]),
        Route("/moi", moi),
        Mount("/static", StaticFiles(directory=racine / "static"), name="static"),
    ])
    templates = Jinja2Templates(directory=racine / "templates")
    prefixe = config.prefixe
    templates.env.globals["u"] = lambda chemin: prefixe + chemin
    templates.env.globals["prefixe"] = prefixe
    app.state.config = config
    app.state.templates = templates
    app.state.carte = Carte(config.donnees / "pays-110m.json")
    app.state.sauvegarde = Sauvegarde(config.data)
    app.state.reglages = Reglages(config.data / "reglages.json", config.ollama_defaut)
    app.state.cache_statut = {}
    app.state.tours = execution.Gestionnaire()
    return app
