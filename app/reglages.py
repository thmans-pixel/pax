"""Réglages de l'IA : adresse d'Ollama, modèle, taille de contexte. data/reglages.json."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .ollama import normaliser_adresse

CONTEXTE_MINI, CONTEXTE_MAXI = 2048, 131072
CONTEXTE_DEFAUT = 16384


class Reglages:
    def __init__(self, fichier: Path, adresse_defaut: str):
        self.fichier = Path(fichier)
        self.adresse_defaut = adresse_defaut

    def lire(self) -> dict:
        base = {"ollama_adresse": self.adresse_defaut, "modele": "", "contexte": CONTEXTE_DEFAUT}
        try:
            stocke = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return base
        if isinstance(stocke, dict):
            for k in base:
                if k in stocke:
                    base[k] = stocke[k]
        return base

    def valider(self, adresse: str, modele: str, contexte) -> dict:
        """Renvoie des réglages propres ou lève ValueError avec un message clair."""
        adresse = normaliser_adresse(adresse)
        modele = (modele or "").strip()
        if len(modele) > 120 or any(c in modele for c in "\n\r\t"):
            raise ValueError("nom de modèle invalide")
        try:
            contexte = int(contexte)
        except (TypeError, ValueError):
            raise ValueError("la taille de contexte doit être un nombre") from None
        if not CONTEXTE_MINI <= contexte <= CONTEXTE_MAXI:
            raise ValueError(f"la taille de contexte doit être entre {CONTEXTE_MINI} et {CONTEXTE_MAXI}")
        return {"ollama_adresse": adresse, "modele": modele, "contexte": contexte}

    def ecrire(self, reglages: dict) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.fichier.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(reglages, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.fichier)
