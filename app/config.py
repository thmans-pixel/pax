"""Où le jeu cherche ses fichiers et qui est administrateur."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    data: Path                                   # parties, réglages
    scenarios: list[Path]                        # dossiers de scénarios (livrés, puis ajoutés à la main)
    donnees: Path                                # contours des pays
    prefixe: str = ""                            # "" ou "/pax" quand le jeu est installé dans un chemin
    admins: tuple[str, ...] = ()                 # comptes YunoHost qui règlent le jeu
    utilisateur_dev: str | None = None           # développement local sans YunoHost
    ollama_defaut: str = "http://localhost:11434"
    extras: dict = field(default_factory=dict)

    @classmethod
    def depuis_env(cls) -> "Config":
        data = Path(os.environ.get("PAX_DATA", RACINE / "data"))
        livres = Path(os.environ.get("PAX_SCENARIOS", RACINE / "scenarios"))
        prefixe = os.environ.get("PAX_PREFIXE", "").rstrip("/")
        admins = tuple(a.strip() for a in os.environ.get("PAX_ADMINS", "").split(",") if a.strip())
        dev = os.environ.get("PAX_DEV_UTILISATEUR") or None
        if dev and dev not in admins:
            admins = admins + (dev,)
        return cls(
            data=data,
            scenarios=[livres, data / "scenarios"],
            donnees=Path(os.environ.get("PAX_DONNEES", RACINE / "donnees")),
            prefixe=prefixe,
            admins=admins,
            utilisateur_dev=dev,
            ollama_defaut=os.environ.get("PAX_OLLAMA", "http://localhost:11434"),
        )
