"""Prépare donnees/pays-110m.json à partir du fichier Natural Earth (domaine public).

Usage : python3 outils/preparer_carte.py ne_110m_admin_0_countries.geojson donnees/pays-110m.json

Le fichier produit garde, pour chaque pays : un identifiant stable (ADM0_A3), le nom
français, le nom anglais, le continent, et les contours arrondis à 2 décimales.
L'Antarctique est retiré (il écrase la carte sans servir au jeu).
"""
import json
import sys


def anneau(points):
    return [[round(x, 2), round(y, 2)] for x, y in points]


def main(source, sortie):
    with open(source, encoding="utf-8") as f:
        donnees = json.load(f)
    pays = []
    for f in donnees["features"]:
        p = f["properties"]
        ident = p["ADM0_A3"]
        if ident == "ATA":
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        # on ne garde que les anneaux extérieurs : le 110m n'a pas de trous utiles
        contours = [anneau(poly[0]) for poly in polys]
        pays.append({
            "id": ident,
            "nom": p.get("NAME_FR") or p["ADMIN"],
            "nom_en": p["ADMIN"],
            "continent": p["CONTINENT"],
            "contours": contours,
        })
    pays.sort(key=lambda x: x["id"])
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump({"source": "Natural Earth 1:110m admin 0 (domaine public)", "pays": pays},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(len(pays), "pays écrits dans", sortie)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
