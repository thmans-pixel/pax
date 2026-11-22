"""L'exécution d'un tour en arrière-plan : file d'attente, appel à Ollama, relance, application.

Le tour tourne dans un fil (threading) : la page interroge sa progression toutes les secondes
(GET /partie/<id>/tour). Plus simple et plus robuste qu'un flux SSE derrière nginx, et le tour
continue si l'on ferme l'onglet.
"""
from __future__ import annotations

import copy
import logging
import threading
import time

from .file_ia import FileIA
from .ollama import OllamaIndisponible, OllamaSilence, DELAI_SILENCE, chat_flux, lister_modeles
from .sauvegarde import PartieIntrouvable
from . import tour as t

journal = logging.getLogger("pax.tour")
MSG_PC = "Le PC de l'IA ne répond pas."


class Tour:
    """Ce que la page sait d'un tour en cours ou qui vient de finir."""

    def __init__(self, ticket, ordres: list[str], duree: str):
        self.ticket = ticket
        self.ordres = ordres
        self.duree = duree
        self.etat = "attente"           # attente | ecriture | termine | echec
        self.message = ""
        self.mots = 0
        self.caracteres = 0
        self.relance = False
        self.debut = time.monotonic()
        self.debut_ecriture: float | None = None
        self.fin: float | None = None

    @property
    def actif(self) -> bool:
        return self.etat in ("attente", "ecriture")

    def maj(self, texte: str):
        self.caracteres = len(texte)
        self.mots = len(texte.split())

    def decrire(self, file: FileIA) -> dict:
        fin = self.fin if self.fin is not None else time.monotonic()
        d = {"etat": self.etat, "secondes": int((fin - (self.debut_ecriture or self.debut)) if self.etat != "attente" else 0),
             "mots": self.mots, "caracteres": self.caracteres, "relance": self.relance, "message": self.message}
        if self.etat == "attente":
            n = file.devant(self.ticket)
            d["devant"] = n
            d["message"] = (f"en attente, {n} demande{'s' if n > 1 else ''} avant vous" if n
                            else "en attente, c'est bientôt votre tour")
        elif self.etat == "ecriture":
            d["message"] = ("l'IA reprend sa réponse…" if self.relance else "l'IA écrit…")
        return d


class Gestionnaire:
    """Les tours en cours, par (joueur, partie), et la file unique vers Ollama."""

    def __init__(self):
        self.file = FileIA()
        self.tours: dict[tuple[str, str], Tour] = {}
        self.verrou = threading.RLock()       # protège `tours` et les écritures de parties

    def actif(self, user: str, pid: str) -> bool:
        with self.verrou:
            j = self.tours.get((user, pid))
            return bool(j and j.actif)

    def lancer(self, app, user: str, pid: str, ordres: list[str], duree: str) -> Tour:
        with self.verrou:
            ticket = self.file.prendre()
            job = Tour(ticket, ordres, duree)
            self.tours[(user, pid)] = job
        fil = threading.Thread(target=self._executer, args=(app, user, pid, job), daemon=True,
                               name=f"tour-{pid}")
        fil.start()
        return job

    def consulter(self, user: str, pid: str) -> dict:
        """État du tour pour la page. Un tour fini n'est rendu qu'une fois."""
        with self.verrou:
            j = self.tours.get((user, pid))
            if j is None:
                return {"etat": "aucun"}
            d = j.decrire(self.file)
            if not j.actif:
                del self.tours[(user, pid)]
            return d

    # ------------------------------------------------------------ le fil
    def _executer(self, app, user: str, pid: str, job: Tour):
        try:
            self.file.attendre(job.ticket)
            job.etat, job.debut_ecriture = "ecriture", time.monotonic()
            self._tour(app, user, pid, job)
            job.etat = "termine"
        except OllamaSilence as e:
            job.etat, job.message = "echec", f"{e} Le tour est abandonné ; rien n'est perdu, vos ordres sont conservés."
        except OllamaIndisponible as e:
            job.etat, job.message = "echec", f"{MSG_PC} {e} Rien n'est perdu, vos ordres sont conservés."
        except t.ContexteTropPetit as e:
            job.etat, job.message = "echec", f"{e} Rien n'est perdu, vos ordres sont conservés."
        except _Inexploitable as e:
            job.etat, job.message = "echec", (
                "La réponse de l'IA est restée inexploitable, même après une relance ("
                + "; ".join(e.args[0][:3]) + "). Le tour n'est pas appliqué ; vos ordres sont conservés.")
        except Exception:                                    # un tour qui plante ne doit rien abîmer
            journal.exception("tour %s", pid)
            job.etat, job.message = "echec", "Erreur inattendue dans le jeu. Rien n'est perdu, vos ordres sont conservés."
        finally:
            job.fin = time.monotonic()
            self.file.liberer(job.ticket)

    def _tour(self, app, user: str, pid: str, job: Tour):
        reg = app.state.reglages.lire()
        delai = float(app.state.config.extras.get("delai_silence", DELAI_SILENCE))
        # sonde courte : un PC éteint ne doit pas faire attendre 10 minutes
        lister_modeles(reg["ollama_adresse"], float(app.state.config.extras.get("delai_sonde", 5.0)))
        with self.verrou:
            etat = app.state.sauvegarde.lire(user, pid)
        messages, _ = t.construire_requete(etat, app.state.carte.noms, job.ordres, job.duree, reg["contexte"])
        schema = t.schema_reponse()
        texte = chat_flux(reg["ollama_adresse"], reg["modele"], messages, schema, reg["contexte"], delai, job.maj)
        obj, fautes = t.lire_reponse(texte)
        if obj is not None:
            fautes = t.verifier_forme(obj)
        if fautes:                                           # une seule relance, qui liste les fautes
            job.relance = True
            echo = texte[:6000]
            suite = messages + [{"role": "assistant", "content": echo},
                                {"role": "user", "content": t.message_relance(fautes)}]
            if t.estimer_jetons(suite) > reg["contexte"] - t.RESERVE_REPONSE:
                suite = messages + [{"role": "user", "content": t.message_relance(fautes)}]
            job.maj("")
            texte = chat_flux(reg["ollama_adresse"], reg["modele"], suite, schema, reg["contexte"], delai, job.maj)
            obj, fautes = t.lire_reponse(texte)
            if obj is not None:
                fautes = t.verifier_forme(obj)
            if fautes:
                raise _Inexploitable(fautes)
        with self.verrou:
            etat = app.state.sauvegarde.lire(user, pid)
            neuf, _ = t.appliquer(etat, obj, app.state.carte.noms, job.ordres, job.duree)
            avant = copy.deepcopy(etat)
            avant.pop("historique", None)
            avant["brouillon"] = None
            neuf["historique"] = (etat.get("historique") or []) + [avant]
            neuf["historique"] = neuf["historique"][-t.HISTORIQUE_MAX:]
            app.state.sauvegarde.enregistrer(user, neuf)


class _Inexploitable(Exception):
    pass


def annuler(app, user: str, pid: str) -> dict:
    """Revient à l'état d'avant le dernier tour ; les ordres de ce tour reviennent dans la zone."""
    g: Gestionnaire = app.state.tours
    with g.verrou:
        etat = app.state.sauvegarde.lire(user, pid)
        hist = etat.get("historique") or []
        if not hist:
            raise ValueError("Il n'y a plus de tour à annuler.")
        ancien = hist[-1]
        dernier = etat.get("dernier_tour") or {}
        ancien["historique"] = hist[:-1]
        ancien["brouillon"] = {"ordres": dernier.get("ordres", []), "duree": dernier.get("duree", t.DUREE_DEFAUT)}
        app.state.sauvegarde.enregistrer(user, ancien)
        return ancien
