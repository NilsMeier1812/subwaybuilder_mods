"""
Gebäude einlesen und nach Nutzung gewichten.

Das Ergebnis ist die Dasymetrie für die Arbeitsplätze: die amtliche Zahl der
Beschäftigten liegt nur je Gemeinde vor (ADM3), verteilt wird sie innerhalb
der Gemeinde auf Gebäude — gewichtet nach Nutzungsart und Geschossfläche.

Die Dichtewerte unten sind Planungsrichtwerte (Beschäftigte je m²
Geschossfläche). Absolut sind sie nicht entscheidend, weil am Ende ohnehin
auf die amtliche Gemeindesumme skaliert wird — es kommt nur auf die
Verhältnisse zwischen den Nutzungsarten an.
"""

import gzip
import json

from .geo import bbox_contains, geometry_area_m2, geometry_centroid

# Beschäftigte je m² Geschossfläche, plus Standard-Geschosszahl je Nutzung
JOB_DENSITY = {
    "office": (1 / 25.0, 4),
    "retail": (1 / 40.0, 2),
    "industrial": (1 / 80.0, 1),
    "warehouse": (1 / 250.0, 1),
    "education": (1 / 60.0, 3),
    "health": (1 / 50.0, 4),
    "hotel": (1 / 100.0, 4),
    "civic": (1 / 35.0, 3),
    "residential": (1 / 400.0, 3),
    "other": (1 / 150.0, 2),
}

# OSM-/Overture-Werte des building-Tags -> Nutzungsklasse
BUILDING_KIND = {
    "office": "office",
    "commercial": "office",
    "retail": "retail",
    "supermarket": "retail",
    "shop": "retail",
    "kiosk": "retail",
    "mall": "retail",
    "industrial": "industrial",
    "factory": "industrial",
    "manufacture": "industrial",
    "works": "industrial",
    "warehouse": "warehouse",
    "storage_tank": "warehouse",
    "hangar": "warehouse",
    "school": "education",
    "university": "education",
    "college": "education",
    "kindergarten": "education",
    "hospital": "health",
    "clinic": "health",
    "hotel": "hotel",
    "motel": "hotel",
    "hostel": "hotel",
    "civic": "civic",
    "public": "civic",
    "government": "civic",
    "government_office": "civic",
    "train_station": "civic",
    "transportation": "civic",
    "fire_station": "civic",
    "museum": "civic",
    "sports_hall": "civic",
    "stadium": "civic",
    "house": "residential",
    "detached": "residential",
    "semidetached_house": "residential",
    "residential": "residential",
    "apartments": "residential",
    "terrace": "residential",
    "dormitory": "residential",
    "bungalow": "residential",
    "farm": "residential",
    "static_caravan": "residential",
}

# Gebäude, die nie Arbeitsplätze tragen sollen
IGNORED_BUILDINGS = {
    "garage",
    "garages",
    "carport",
    "shed",
    "hut",
    "roof",
    "canopy",
    "ruins",
    "greenhouse",
    "barn",
    "silo",
    "bunker",
    "toilets",
    "service",
    "transformer_tower",
}


def classify(props):
    """Nutzungsklasse eines Gebäudes aus seinen Tags bestimmen."""
    if not props:
        return "other"

    # Zusatz-Tags schlagen den reinen building-Wert
    if props.get("office"):
        return "office"
    if props.get("shop"):
        return "retail"

    amenity = str(props.get("amenity") or "").lower()
    if amenity in ("school", "college", "university", "kindergarten"):
        return "education"
    if amenity in ("hospital", "clinic", "doctors", "nursing_home"):
        return "health"
    if amenity in ("townhall", "police", "fire_station", "courthouse", "library"):
        return "civic"

    for key in ("building", "class", "subtype", "type"):
        value = str(props.get(key) or "").lower()
        if not value or value in ("yes", "true", "1"):
            continue
        if value in IGNORED_BUILDINGS:
            return None
        if value in BUILDING_KIND:
            return BUILDING_KIND[value]

    landuse = str(props.get("landuse") or "").lower()
    if landuse in ("industrial", "commercial", "retail"):
        return BUILDING_KIND.get(landuse, "other")

    return "other"


def _levels(props, default):
    for key in ("building:levels", "levels", "building_levels", "num_floors"):
        raw = props.get(key)
        if raw in (None, ""):
            continue
        try:
            value = float(str(raw).split(";")[0].replace(",", "."))
        except ValueError:
            continue
        if 0 < value <= 80:
            return value
    return float(default)


def _iter_features(path):
    """Liest FeatureCollection (.geojson) oder zeilenweises GeoJSON (.geojsonl)."""
    opener = gzip.open if path.endswith(".gz") else open
    stripped = path[:-3] if path.endswith(".gz") else path

    if stripped.endswith((".geojsonl", ".ndjson", ".jsonl")):
        with opener(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip().rstrip(",")
                if not line or line in ("[", "]"):
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        return

    with opener(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        for feat in data.get("features", []):
            yield feat
    elif isinstance(data, list):
        for feat in data:
            yield feat
    else:
        yield data


def read_buildings(path, bbox=None, min_area_m2=40.0):
    """
    Gebäude einlesen.

    Rückgabe je Gebäude: ``{"lon", "lat", "area_m2", "floor_m2", "kind",
    "weight"}``. ``weight`` ist die erwartete Beschäftigtenzahl vor der
    Skalierung auf die amtliche Gemeindesumme.

    Große Dateien am besten als ``.geojsonl`` bereitstellen — dann wird
    zeilenweise gelesen und der Speicherbedarf bleibt klein.
    """
    out = []
    for feat in _iter_features(path):
        geom = feat.get("geometry")
        if not geom:
            continue
        props = feat.get("properties") or {}
        kind = classify(props)
        if kind is None:
            continue

        area = geometry_area_m2(geom)
        if area < min_area_m2:
            continue

        centroid = geometry_centroid(geom)
        if not centroid:
            continue
        lon, lat = centroid
        if bbox and not bbox_contains(bbox, lon, lat):
            continue

        density, default_levels = JOB_DENSITY[kind]
        floor = area * _levels(props, default_levels)
        out.append(
            {
                "lon": lon,
                "lat": lat,
                "area_m2": area,
                "floor_m2": floor,
                "kind": kind,
                "weight": floor * density,
            }
        )
    return out


def summarize(buildings):
    """Zählt Gebäude und Gewichte je Nutzungsklasse."""
    stats = {}
    for b in buildings:
        entry = stats.setdefault(b["kind"], {"count": 0, "area_m2": 0.0, "weight": 0.0})
        entry["count"] += 1
        entry["area_m2"] += b["area_m2"]
        entry["weight"] += b["weight"]
    return stats
