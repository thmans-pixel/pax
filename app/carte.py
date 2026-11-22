"""La carte du monde en SVG : un territoire = un pays actuel, coloré selon sa nation."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

# projection plate : x = longitude, y = -latitude (le 110m n'a rien au-delà de 84°N / 56°S)
VUE = (-180, -85, 360, 142)


def _chemin(contours: list[list[list[float]]]) -> str:
    morceaux = []
    for anneau in contours:
        pts: list[tuple[str, str]] = []
        for lon, lat in anneau:
            p = (f"{lon:.1f}".rstrip("0").rstrip("."), f"{-lat:.1f}".rstrip("0").rstrip("."))
            if not pts or pts[-1] != p:
                pts.append(p)
        if len(pts) < 3:
            continue
        morceaux.append("M" + "L".join(f"{x} {y}" for x, y in pts) + "Z")
    return "".join(morceaux)


class Carte:
    def __init__(self, fichier: Path):
        donnees = json.loads(Path(fichier).read_text(encoding="utf-8"))
        self.noms: dict[str, str] = {}
        self.continents: dict[str, str] = {}
        self._chemins: dict[str, str] = {}
        for p in donnees["pays"]:
            self.noms[p["id"]] = p["nom"]
            self.continents[p["id"]] = p["continent"]
            self._chemins[p["id"]] = _chemin(p["contours"])

    @property
    def ids(self) -> set[str]:
        return set(self.noms)

    def svg(self, territoires: dict[str, str], nations: dict[str, dict]) -> str:
        """`territoires` : territoire -> id de nation ; `nations` : id -> {couleur, ...}."""
        x, y, l, h = VUE
        parts = [
            f'<svg id="carte" xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {l} {h}" '
            f'role="img" aria-label="Carte du monde" preserveAspectRatio="xMidYMid meet">',
            f'<rect class="mer" x="{x}" y="{y}" width="{l}" height="{h}"/>',
            '<g id="pays">',
        ]
        for tid, d in self._chemins.items():
            nid = territoires.get(tid)
            couleur = nations.get(nid, {}).get("couleur", "#777777") if nid else "#777777"
            parts.append(
                f'<path id="t-{escape(tid)}" class="pays" data-t="{escape(tid)}" '
                f'data-n="{escape(nid or "")}" fill="{escape(couleur)}" d="{d}"/>')
        parts.append("</g></svg>")
        return "".join(parts)
