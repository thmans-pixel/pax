"""Les parties : un fichier JSON par partie, rangé par joueur.

data/parties/<identifiant YunoHost>/<id de partie>.json
Un joueur ne voit que ses propres parties ; l'identifiant vient de YunoHost, jamais d'un
champ de formulaire.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .monde import VERSION_FORMAT, date_fr

UTILISATEUR = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")
IDENT_PARTIE = re.compile(r"^[0-9a-f]{16}$")


class PartieIntrouvable(Exception):
    pass


class Sauvegarde:
    def __init__(self, racine: Path):
        self.racine = Path(racine) / "parties"

    def _dossier(self, utilisateur: str) -> Path:
        # l'utilisateur est contrôlé deux fois : ce nom devient un nom de dossier
        if not UTILISATEUR.fullmatch(utilisateur) or utilisateur in (".", ".."):
            raise PartieIntrouvable("utilisateur invalide")
        return self.racine / utilisateur

    def _fichier(self, utilisateur: str, pid: str) -> Path:
        if not IDENT_PARTIE.fullmatch(pid or ""):
            raise PartieIntrouvable("partie introuvable")
        return self._dossier(utilisateur) / f"{pid}.json"

    def creer(self, utilisateur: str, etat: dict) -> str:
        pid = secrets.token_hex(8)
        etat["id"] = pid
        etat["version_format"] = VERSION_FORMAT
        etat["cree_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.enregistrer(utilisateur, etat)
        return pid

    def enregistrer(self, utilisateur: str, etat: dict) -> None:
        """Écriture atomique : on n'abîme jamais la partie en cas d'arrêt en plein milieu."""
        fichier = self._fichier(utilisateur, etat["id"])
        fichier.parent.mkdir(parents=True, exist_ok=True)
        etat["modifie_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fd, tmp = tempfile.mkstemp(dir=fichier.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(etat, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, fichier)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def lire(self, utilisateur: str, pid: str) -> dict:
        fichier = self._fichier(utilisateur, pid)
        try:
            return json.loads(fichier.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            raise PartieIntrouvable("partie introuvable") from None

    def supprimer(self, utilisateur: str, pid: str) -> None:
        fichier = self._fichier(utilisateur, pid)
        try:
            fichier.unlink()
        except FileNotFoundError:
            raise PartieIntrouvable("partie introuvable") from None

    def lister(self, utilisateur: str) -> list[dict]:
        """Résumés des parties du joueur, la plus récemment jouée d'abord."""
        dossier = self._dossier(utilisateur)
        if not dossier.is_dir():
            return []
        res = []
        for f in dossier.glob("*.json"):
            if not IDENT_PARTIE.match(f.stem):
                continue
            try:
                e = json.loads(f.read_text(encoding="utf-8"))
                res.append({
                    "id": e["id"], "scenario": e["scenario"]["nom"],
                    "nation": e["nations"][e["nation_joueur"]]["nom"],
                    "date": date_fr(e["date"]), "tour": e["tour"],
                    "modifie_le": e.get("modifie_le", ""),
                })
            except (OSError, ValueError, KeyError):
                continue          # une partie abîmée ne doit pas empêcher d'ouvrir les autres
        res.sort(key=lambda p: p["modifie_le"], reverse=True)
        return res
