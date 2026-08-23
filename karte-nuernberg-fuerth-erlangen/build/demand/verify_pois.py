#!/usr/bin/env python3
"""
Sonderziele aus region.json prüfen.

Die Koordinaten in region.json sind von Hand eingetragen und damit die
fehleranfälligste Stelle des ganzen Projekts — ein vertippter Wert setzt den
Flughafen auf ein Feld bei Fürth. Dieses Skript prüft, was sich ohne Netz
prüfen lässt, und schreibt eine GeoJSON-Datei zum Draufschauen.

    python3 verify_pois.py --region region.json --out pois.geojson

Die Ausgabe lässt sich auf geojson.io ziehen oder in JOSM/QGIS über die
OSM-Karte legen. Liegt ein Punkt daneben, in region.json korrigieren.

Mit --buildings <datei> wird zusätzlich geprüft, ob am Zielort überhaupt
Bebauung liegt — ein Punkt mitten im Wald ist fast immer ein Tippfehler.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuedemand import buildings as buildings_mod
from nuedemand.geo import bbox_contains, haversine

# Typ -> Kürzel der Sonderbedarf-Taxonomie. Das Kürzel wird zum Präfix der
# Punkt-ID im Spiel (z. B. AIR_NUE). Maßgeblich ist
# depot/src/depot/special_demand_types.json; diese Kopie erlaubt die Prüfung,
# ohne depot installiert zu haben. Ist depot vorhanden, wird dessen Datei
# gelesen und diese Tabelle ignoriert.
SPECIAL_DEMAND_CODES = {
    'airport': 'AIR',
    'amusement_park': 'AMU',
    'aquarium': 'AQU',
    'archive': 'MUS',
    'arena': 'SPO',
    'art_museum': 'MUS',
    'athletic_field': 'SPO',
    'athletics_track': 'SPO',
    'baseball_field': 'SPO',
    'bathhouse': 'BTH',
    'beach': 'NAT',
    'botanical_garden': 'PRK',
    'casino': 'SHP',
    'cave': 'NAT',
    'childrens_center': 'CUL',
    'civic_center': 'CUL',
    'community_college': 'UNI',
    'concert_hall': 'CUL',
    'consolidated': 'SCH',
    'convention_center': 'CNV',
    'cultural_center': 'CUL',
    'custom': 'CUS',
    'domestic_terminal': 'AIR',
    'elementary': 'SCH',
    'events': 'EVT',
    'gallery': 'MUS',
    'garden': 'PRK',
    'gorge': 'NAT',
    'government_facility': 'GOV',
    'gymnasium': 'SPO',
    'heritage_site': 'HER',
    'high_school': 'SCH',
    'historic_building': 'HER',
    'hospital': 'HOS',
    'ice_rink': 'SPO',
    'international_terminal': 'AIR',
    'junior_college': 'UNI',
    'junior_high': 'SCH',
    'lake': 'NAT',
    'library': 'LIB',
    'marina': 'PORT',
    'marketplace': 'SHP',
    'martial_arts_hall': 'SPO',
    'middle_school': 'SCH',
    'military_base': 'MIL',
    'mountain': 'NAT',
    'museum': 'MUS',
    'natural_feature': 'NAT',
    'nature_park': 'PRK',
    'outside_connection': 'EXT',
    'park': 'PRK',
    'pool': 'SPO',
    'port': 'PORT',
    'racetrack': 'SPO',
    'religious_institution': 'REL',
    'resort': 'RST',
    'safari_park': 'ZOO',
    'scenic_spot': 'NAT',
    'school': 'SCH',
    'science_museum': 'MUS',
    'shipyard': 'PORT',
    'shop': 'SHP',
    'shopping_center': 'SHP',
    'shrine': 'REL',
    'special_support': 'SCH',
    'sports_complex': 'SPO',
    'sports_facility': 'SPO',
    'sports_park': 'SPO',
    'stadium': 'SPO',
    'technical_college': 'UNI',
    'temple': 'REL',
    'tennis_court': 'SPO',
    'theater': 'CUL',
    'theme_park': 'AMU',
    'university': 'UNI',
    'waterfall': 'NAT',
    'world_heritage': 'HER',
    'zoo': 'ZOO',
}


def load_codes():
    """Taxonomie aus depot laden, sonst die eingebaute Tabelle nehmen."""
    try:
        import depot
        path = os.path.join(os.path.dirname(depot.__file__), "special_demand_types.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        codes = {}
        for entry in data.get("types", []):
            codes[entry["id"]] = entry["code"]
            for sub in entry.get("sub_types", []):
                codes[sub["id"]] = sub.get("code", entry["code"])
        return codes, "depot"
    except Exception:
        return dict(SPECIAL_DEMAND_CODES), "eingebaute Tabelle"



def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="region.json")
    ap.add_argument("--buildings", help="buildings.geojson für die Umgebungsprüfung")
    ap.add_argument("--radius", type=float, default=400.0, help="Suchradius für Bebauung in m")
    ap.add_argument("--out", default="pois.geojson")
    args = ap.parse_args(argv)

    with open(args.region, encoding="utf-8") as fh:
        region = json.load(fh)
    bbox = region["bbox"]
    pois = region["special_demand"]

    codes, codes_source = load_codes()
    print(f"Typprüfung gegen: {codes_source} ({len(codes)} Typen)")

    nearby = None
    if args.buildings:
        print(f"Lese Gebäude aus {args.buildings} …")
        nearby = buildings_mod.read_buildings(args.buildings, bbox=bbox)
        print(f"  {len(nearby)} Gebäude im Ausschnitt")

    problems = 0
    features = []
    print(f"\n{'Ziel':34s} {'Punkt-ID':14s} {'Lon':>8s} {'Lat':>8s}  Status")
    print("-" * 90)
    for poi in pois:
        lon, lat = poi["location"]
        notes = []

        code = codes.get(poi["type"])
        if code is None:
            notes.append(f"UNBEKANNTER Typ '{poi['type']}'")
            problems += 1

        if not bbox_contains(bbox, lon, lat):
            notes.append("AUSSERHALB der bbox")
            problems += 1
        else:
            # Randlage melden: näher als 1 km an der Kartengrenze
            margin_deg = 1000.0 / 111320.0
            if (lon - bbox[0] < margin_deg or bbox[2] - lon < margin_deg
                    or lat - bbox[1] < margin_deg or bbox[3] - lat < margin_deg):
                notes.append("dicht am Kartenrand")

        if nearby is not None:
            count = sum(
                1 for b in nearby if haversine((lon, lat), (b["lon"], b["lat"])) <= args.radius
            )
            if count == 0:
                notes.append(f"KEINE Bebauung im Umkreis von {int(args.radius)} m")
                problems += 1
            else:
                notes.append(f"{count} Gebäude in {int(args.radius)} m")

        status = "; ".join(notes) if notes else "ok"
        point_id = f"{code}_{poi.get('code') or poi['name'].replace(' ', '_')}" if code else "?"
        print(f"{poi['name'][:34]:34s} {point_id[:14]:14s} {lon:8.4f} {lat:8.4f}  {status}")

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": poi["name"],
                "typ": poi["type"],
                "code": poi.get("code", ""),
                "punkt_id": f"{code}_{poi.get('code') or poi['name'].replace(' ', '_')}" if code else "",
                "kapazitaet": poi["total_capacity"],
                "quelle": poi.get("quelle", ""),
                "status": status,
            },
        })

    # Kartenrahmen als Kontrollgeometrie mitgeben
    features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [[
            [bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]],
            [bbox[0], bbox[3]], [bbox[0], bbox[1]]]]},
        "properties": {"name": "Kartenausschnitt NUE"},
    })

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh,
                  indent=1, ensure_ascii=False)

    print("-" * 90)
    total = f"{sum(p['total_capacity'] for p in pois):,}".replace(",", ".")
    print(f"{len(pois)} Ziele, {total} Personen gesamt")
    print(f"Geschrieben: {args.out}")
    if problems:
        print(f"\n{problems} Punkt(e) auffällig — bitte in {args.region} nachbessern.")
        return 1
    print("\nKeine offensichtlichen Fehler. Trotzdem einmal auf der Karte gegenprüfen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
