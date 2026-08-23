#!/usr/bin/env python3
"""
Basiskarte Nürnberg / Fürth / Erlangen für Subway Builder erzeugen.

Erzeugt die vier Nicht-Nachfrage-Dateien, die das Spiel braucht:

    NUE/NUE.pmtiles                 Vektorkacheln inkl. Labels
    NUE/NUE_foundations.pmtiles     Fundament-Layer
    NUE/buildings_index.json        Gebäude-Index (Kollisionen)
    NUE/roads.geojson               Straßennetz
    NUE/runways_taxiways.geojson    Start-/Rollbahnen Flughafen Nürnberg

Voraussetzungen (siehe ../README.md):
    pip install depot   (aus https://github.com/Subway-Builder-Modded/depot)
    node, mapshaper, osmium, java, tippecanoe/tile-join, sqlite3, jq,
    pmtiles, planetiler.jar

Aufruf:
    python3 mapgen_nue.py
"""

import os
import requests

from depot.maps import MapGen

# --- Eingabedaten -----------------------------------------------------------

# Mittelfranken enthält Nürnberg, Fürth, Erlangen und Schwabach komplett.
PBF = "mittelfranken-latest.osm.pbf"
PBF_URL = "https://download.geofabrik.de/europe/germany/bayern/mittelfranken-latest.osm.pbf"

# [min_lon, min_lat, max_lon, max_lat] — identisch zu BBOX in ../index.js.
# N: Erlangen-Nord | S: Nürnberg-Katzwang und Flughafen
# W: Zirndorf/Stein | O: Lauf a. d. Pegnitz / Röthenbach
BBOX = [10.85, 49.32, 11.28, 49.66]

if not os.path.exists(PBF):
    print("Lade", PBF_URL, flush=True)
    resp = requests.get(PBF_URL, timeout=600)
    resp.raise_for_status()
    with open(PBF, "wb") as f:
        f.write(resp.content)

# --- Kartengenerierung ------------------------------------------------------

obj = MapGen(
    city="NUE",
    bbox=BBOX,
    osmpbf=PBF,
    outputdir=".",

    # Deutsche Innenstädte haben viel Kleingebäude (Garagen, Schuppen).
    # 40 m² filtert die weg, ohne Wohnhäuser zu verlieren.
    building_index_filter_size=40,
    building_tile_filter_size=40,
    building_index_simplification=1,
    building_tile_simplification=1,

    # Binnenland: Meerestiefen sind irrelevant, spart Rechenzeit und
    # PMTiles-Größe. Gebäudefundamente bleiben an.
    create_building_foundations=True,
    create_ocean_foundations=False,

    # Deutsche OSM-place-Tags. Mit check_labels() gegenprüfen und ggf. anpassen.
    #   city         -> Nürnberg, Fürth, Erlangen
    #   town         -> Schwabach, Zirndorf, Stein, Herzogenaurach, Lauf
    #   suburb       -> Gostenhof, Johannis, Bruck, Tennenlohe ...
    #   quarter      -> feinere Stadtviertel
    cities=["city", "borough", "town"],
    suburbs=["suburb", "village", "town"],
    neighborhoods=["neighbourhood", "quarter", "hamlet", "locality", "suburb"],

    # Deutsche Namen erzwingen (OSM führt hier ohnehin meist nur `name`).
    label_name_language="prefer:de",
    road_name_preferred_language="de",

    maxzoom=15,
    ncores=None,      # alle Kerne
    RAM=8,            # bei Heap-Fehlern in mapshaper erhöhen
    cleanup_files=True,
    verb=True,
)

# Reihenfolge ist vorgeschrieben: extract_base_data zuerst,
# process_buildings vor generate_pmtiles, generate_pmtiles vor add_labels.
obj.extract_base_data()
obj.process_buildings()
obj.process_roads_and_aeroways()
obj.generate_pmtiles()

# Vor add_labels lohnt ein Blick, welche place-Tags es hier überhaupt gibt:
obj.check_labels()

obj.add_labels()

print("Fertig. Ergebnisse liegen in ./NUE/")
