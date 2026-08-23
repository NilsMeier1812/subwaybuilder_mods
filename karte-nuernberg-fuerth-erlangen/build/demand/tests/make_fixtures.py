#!/usr/bin/env python3
"""
Erzeugt synthetische, aber realistisch geformte Testdaten für die Region
Nürnberg / Fürth / Erlangen.

Damit lässt sich die komplette Pipeline durchspielen, ohne die echten
Datensätze (mehrere GB) herunterzuladen. Die Zahlen sind erfunden, die
Struktur ist die der echten Dateien.
"""

import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from nuedemand import laea

BBOX = [10.85, 49.32, 11.28, 49.66]

# (AGS, Name, lon, lat, Einwohner, Arbeitsplätze, Radius km)
CITIES = [
    ("09564000", "Nürnberg", 11.0777, 49.4521, 545000, 320000, 6.0),
    ("09563000", "Fürth", 10.9887, 49.4783, 130000, 55000, 3.2),
    ("09562000", "Erlangen", 11.0044, 49.5967, 117000, 85000, 3.0),
    ("09565000", "Schwabach", 11.0208, 49.3300, 41000, 17000, 2.0),
]

KINDS = [
    ("office", 0.10),
    ("retail", 0.12),
    ("industrial", 0.08),
    ("residential", 0.62),
    ("education", 0.04),
    ("health", 0.02),
    ("warehouse", 0.02),
]


def jitter(lon, lat, radius_km, rng):
    """Punkt normalverteilt um ein Zentrum, in km-Radius."""
    r = abs(rng.gauss(0, radius_km / 2.0)) * 1000.0
    a = rng.uniform(0, 2 * math.pi)
    x, y = laea.forward(lon, lat)
    return laea.inverse(x + r * math.cos(a), y + r * math.sin(a))


def snap_to_grid(lon, lat, size=100):
    """Auf die SW-Ecke einer INSPIRE-Zelle runden und die ID bauen."""
    x, y = laea.forward(lon, lat)
    east = int(math.floor(x / size) * size)
    north = int(math.floor(y / size) * size)
    return f"CRS3035RES{size}mN{north}E{east}"


def square(lon, lat, side_m):
    dlat = side_m / 111320.0
    dlon = side_m / (111320 * math.cos(math.radians(lat)))
    return [[[lon, lat], [lon + dlon, lat], [lon + dlon, lat + dlat], [lon, lat + dlat], [lon, lat]]]


def build(outdir, seed=20260823, scale=1.0):
    os.makedirs(outdir, exist_ok=True)
    rng = random.Random(seed)

    # --- Zensusgitter ------------------------------------------------------
    grid = {}
    for _ags, _name, lon, lat, pop, _jobs, radius in CITIES:
        pop = int(pop * scale)
        cells = max(50, pop // 60)
        per_cell = pop / cells
        for _ in range(cells):
            clon, clat = jitter(lon, lat, radius, rng)
            if not (BBOX[0] <= clon <= BBOX[2] and BBOX[1] <= clat <= BBOX[3]):
                continue
            gid = snap_to_grid(clon, clat)
            grid[gid] = grid.get(gid, 0) + max(1, int(rng.gauss(per_cell, per_cell / 3)))

    zensus_path = os.path.join(outdir, "zensus_100m.csv")
    with open(zensus_path, "w", encoding="utf-8") as fh:
        fh.write("GITTER_ID_100m;werte\n")
        for gid, value in sorted(grid.items()):
            fh.write(f"{gid};{value}\n")
        fh.write("CRS3035RES100mN2926400E4399300;-1\n")  # gesperrte Zelle

    # --- Gebäude -----------------------------------------------------------
    features = []
    for _ags, _name, lon, lat, pop, _jobs, radius in CITIES:
        count = max(80, int(pop * scale / 120))
        for _ in range(count):
            blon, blat = jitter(lon, lat, radius, rng)
            if not (BBOX[0] <= blon <= BBOX[2] and BBOX[1] <= blat <= BBOX[3]):
                continue
            roll = rng.random()
            acc = 0.0
            kind = "residential"
            for name, share in KINDS:
                acc += share
                if roll <= acc:
                    kind = name
                    break
            side = rng.uniform(9, 45)
            props = {"building": {"office": "office", "retail": "retail",
                                  "industrial": "industrial", "residential": "apartments",
                                  "education": "school", "health": "hospital",
                                  "warehouse": "warehouse"}[kind]}
            if rng.random() < 0.4:
                props["building:levels"] = str(rng.randint(1, 8))
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": square(blon, blat, side)},
                "properties": props,
            })
    # ein paar Garagen und Winzlinge, die herausgefiltert werden müssen
    for _ in range(40):
        blon, blat = jitter(11.0777, 49.4521, 5, rng)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": square(blon, blat, 4)},
            "properties": {"building": "garage"},
        })

    buildings_path = os.path.join(outdir, "buildings.geojson")
    with open(buildings_path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh)

    # --- Gemeindegrenzen (grobe Kacheln, die sich nicht überlappen) --------
    gem_features = []
    bounds = {
        "09564000": [11.00, 49.38, 11.20, 49.52],
        "09563000": [10.92, 49.42, 11.00, 49.52],
        "09562000": [10.94, 49.54, 11.10, 49.66],
        "09565000": [10.96, 49.30, 11.10, 49.38],
    }
    for ags, name, *_ in CITIES:
        b = bounds[ags]
        gem_features.append({
            "type": "Feature",
            "properties": {"AGS": ags, "GEN": name},
            "geometry": {"type": "Polygon", "coordinates": [[
                [b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]]},
        })
    gemeinden_path = os.path.join(outdir, "gemeinden.geojson")
    with open(gemeinden_path, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": gem_features}, fh)

    # --- Beschäftigte je Gemeinde -----------------------------------------
    jobs_path = os.path.join(outdir, "beschaeftigte.csv")
    with open(jobs_path, "w", encoding="utf-8") as fh:
        fh.write("ags;name;beschaeftigte\n")
        for ags, name, _lon, _lat, _pop, jobs, _r in CITIES:
            fh.write(f"{ags};{name};{int(jobs * scale)}\n")
        fh.write("09999000;Anderswo;12345\n")  # außerhalb des Ausschnitts

    # --- Pendlermatrix -----------------------------------------------------
    pendler_path = os.path.join(outdir, "pendler.csv")
    with open(pendler_path, "w", encoding="utf-8") as fh:
        fh.write("von_ags;nach_ags;anzahl\n")
        for ags_from, _n1, _lo1, _la1, pop, _j1, _r1 in CITIES:
            workers = int(pop * scale * 0.52)
            for ags_to, _n2, _lo2, _la2, _p2, jobs, _r2 in CITIES:
                share = 0.62 if ags_from == ags_to else 0.10
                fh.write(f"{ags_from};{ags_to};{int(workers * share)}\n")
            fh.write(f"{ags_from};09999000;{int(workers * 0.08)}\n")  # Auspendler
        fh.write(f"09999000;09564000;40000\n")  # Einpendler

    return {
        "zensus": zensus_path,
        "buildings": buildings_path,
        "gemeinden": gemeinden_path,
        "jobs": jobs_path,
        "pendler": pendler_path,
        "bbox": BBOX,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="fixtures")
    ap.add_argument("--scale", type=float, default=1.0)
    args = ap.parse_args()
    paths = build(args.out, scale=args.scale)
    for key, value in paths.items():
        print(f"{key:12s} {value}")
