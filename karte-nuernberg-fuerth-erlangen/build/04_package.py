#!/usr/bin/env python3
"""
Schritt 4: config.json schreiben, alles prüfen und das Karten-ZIP packen.

Das ZIP hat genau den Aufbau, den der Railyard-Manager und die
Integritätsprüfung des Registers erwarten (alle Dateien auf oberster Ebene):

    config.json
    NEF.pmtiles
    NEF_foundations.pmtiles
    buildings_index.bin.gz
    demand_data.json.gz
    roads.geojson.gz
    runways_taxiways.geojson.gz
"""

import gzip
import json
import zipfile

from nef import buildings_index
from nef.common import BBOX, CODE, DIST, OUT, REGION, log, read_json

FILES = [f"{CODE}.pmtiles", f"{CODE}_foundations.pmtiles", "buildings_index.bin.gz",
         "demand_data.json.gz", "roads.geojson.gz", "runways_taxiways.geojson.gz"]


def main():
    for f in FILES:
        if not (OUT / f).exists():
            raise SystemExit(f"fehlt: {f} – erst 02_basemap.py und 03_demand.py ausführen")

    demand = read_json(OUT / "demand_data.json.gz")
    population = sum(p["size"] for p in demand["pops"])
    info = buildings_index.decode(gzip.decompress((OUT / "buildings_index.bin.gz").read_bytes()))
    log(f"Gebäude-Index ok: {info['count']} Gebäude")
    for f in ("roads.geojson.gz", "runways_taxiways.geojson.gz"):
        n = len(read_json(OUT / f)["features"])
        log(f"{f}: {n} Features")

    iv = REGION["initial_view"]
    config = {
        "code": CODE,
        "name": REGION["name"],
        "bbox": BBOX,
        "description": REGION["description"],
        "population": population,
        "initialViewState": {"latitude": iv["latitude"], "longitude": iv["longitude"],
                             "zoom": iv["zoom"], "bearing": 0},
        "creator": REGION["creator"],
        "version": REGION["version"],
        "country": REGION["country"],
    }
    (OUT / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    DIST.mkdir(parents=True, exist_ok=True)
    zpath = DIST / f"{CODE}-{REGION['version']}.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.write(OUT / "config.json", "config.json", compress_type=zipfile.ZIP_DEFLATED)
        for f in FILES:
            zf.write(OUT / f, f)     # bereits komprimiert
    log(f"{zpath.name}: {zpath.stat().st_size / 1e6:.1f} MB, Bevölkerung {population}")
    stats = OUT / "demand_stats.json"
    if stats.exists():
        (DIST / f"{CODE}-{REGION['version']}-kennzahlen.json").write_text(stats.read_text(encoding="utf-8"),
                                                                          encoding="utf-8")


if __name__ == "__main__":
    main()
