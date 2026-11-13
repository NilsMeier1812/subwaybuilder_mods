"""
Arbeitsplätze auf Gebäude verteilen.

Die amtliche Zahl der Erwerbstätigen am Arbeitsort je Gemeinde
(Pendlerrechnung) wird innerhalb der Gemeinde auf die Gebäude verteilt:

    Gewicht = Geschossfläche × Beschäftigtendichte(Gebäudetyp)
            + Beschäftigte der Betriebe (POIs) im Gebäude

Der Gebäudetyp kommt aus Overture/OSM (`class`/`subtype`); fehlt er, aus der
umgebenden OSM-Flächennutzung (Gewerbe-, Industrie-, Wohngebiet …).
Die Dichten sind übliche Planungsrichtwerte (m² Bruttogeschossfläche je
Arbeitsplatz), keine lokal kalibrierten Werte.
"""

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from nef.common import RAW, TMP, log, run

# m² Geschossfläche je Arbeitsplatz (größer = weniger Jobs). None = keine Jobs.
M2_PER_JOB = {
    "office": 25, "commercial": 35, "retail": 45, "supermarket": 60, "kiosk": 30,
    "industrial": 90, "manufacture": 90, "warehouse": 180, "factory": 90,
    "hospital": 35, "medical": 40, "clinic": 40,
    "school": 80, "university": 45, "college": 50, "kindergarten": 70, "education": 70,
    "civic": 40, "public": 40, "government": 30, "townhall": 30, "fire_station": 80,
    "hotel": 90, "train_station": 60, "transportation": 120, "service": 300,
    "religious": 800, "church": 800, "chapel": None, "entertainment": 120,
    "sports_hall": 300, "sports_centre": 300, "stadium": 400,
    "agricultural": 1500, "farm": 1500, "farm_auxiliary": 3000, "barn": 3000,
    "military": 150,
    # Wohngebäude: wenige Jobs (Praxen, Läden im EG, Selbstständige)
    "apartments": 1200, "residential": 1500, "house": 3000, "detached": 3000,
    "semidetached_house": 3000, "terrace": 3000, "bungalow": 4000, "dormitory": 3000,
}
NO_JOBS = {"garage", "garages", "carport", "shed", "hut", "roof", "allotment_house",
           "greenhouse", "transformer_tower", "parking", "outbuilding", "bunker",
           "container", "ruins", "construction", "toilets", "chapel"}

# Flächennutzung -> Ersatztyp für Gebäude ohne Klasse
LANDUSE_TYPE = {"industrial": "industrial", "commercial": "commercial", "retail": "retail",
                "railway": "transportation", "military": "military", "education": "education",
                "institutional": "civic", "religious": "religious", "farmyard": "agricultural",
                "residential": "residential", "construction": "residential"}

# Beschäftigte je POI nach Overture-Kategorie (Schlüsselwort im Kategoriepfad)
POI_JOBS = [
    ("hospital", 0), ("doctor", 5), ("dentist", 6), ("pharmacy", 6), ("clinic", 8),
    ("restaurant", 8), ("cafe", 5), ("bar", 4), ("fast_food", 6), ("bakery", 5),
    ("supermarket", 25), ("grocery", 10), ("department_store", 60), ("shopping", 6),
    ("store", 5), ("retail", 5), ("bank", 12), ("insurance", 10), ("lawyer", 6),
    ("accountant", 6), ("real_estate", 5), ("office", 15), ("corporate", 30),
    ("software", 25), ("engineering", 20), ("hotel", 15), ("school", 0),
    ("beauty", 3), ("hair", 3), ("automotive", 6), ("car_dealer", 15),
    ("government", 20), ("post_office", 8), ("gym", 4), ("church", 1),
]
DEFAULT_POI_JOBS = 3
FLOOR_HEIGHT = 3.2


def landuse_polygons(osm_pbf):
    pbf = TMP / "landuse.osm.pbf"
    gj = TMP / "landuse.geojson"
    run(["osmium", "tags-filter", str(osm_pbf), "wr/landuse", "-o", str(pbf), "--overwrite"])
    run(["osmium", "export", str(pbf), "-o", str(gj), "--geometry-types=polygon", "--overwrite"])
    lu = gpd.read_file(gj)[["landuse", "geometry"]]
    lu = lu[lu["landuse"].isin(LANDUSE_TYPE)]
    lu["lu_type"] = lu["landuse"].map(LANDUSE_TYPE)
    return lu


def poi_jobs(cat):
    if not isinstance(cat, str):
        return DEFAULT_POI_JOBS
    c = cat.lower()
    for key, n in POI_JOBS:
        if key in c:
            return n
    return DEFAULT_POI_JOBS


def building_weights(crs, osm_pbf):
    """Gebäude mit Job-Gewicht; Rückgabe in `crs` (Mittelpunkte)."""
    df = pd.read_parquet(RAW / "overture" / "buildings.parquet")
    b = gpd.GeoDataFrame(df.drop(columns="geom"), geometry=gpd.GeoSeries.from_wkb(df["geom"]), crs=4326).to_crs(crs)
    b["footprint"] = b.area
    b = b[b["footprint"] >= 15].copy()

    h = pd.to_numeric(b["height"], errors="coerce")
    fl = pd.to_numeric(b["num_floors"], errors="coerce")
    floors = fl.where(fl > 0, (h / FLOOR_HEIGHT).round()).fillna(np.nan)

    lu = landuse_polygons(osm_pbf).to_crs(crs)
    cent = gpd.GeoDataFrame(geometry=b.geometry.representative_point(), crs=crs, index=b.index)
    hit = gpd.sjoin(cent, lu[["lu_type", "geometry"]], how="left", predicate="within")
    hit = hit[~hit.index.duplicated()]
    b["lu_type"] = hit["lu_type"]

    cls = b["class"].where(b["class"].notna(), b["subtype"])
    btype = cls.where(cls.notna(), b["lu_type"]).fillna("unknown")
    b["btype"] = btype
    # Geschosse schätzen, wenn unbekannt
    default_floors = btype.map({"apartments": 4, "office": 4, "commercial": 3, "hospital": 5,
                                "university": 4, "industrial": 1, "warehouse": 1, "retail": 1,
                                "house": 2, "detached": 2, "residential": 3}).fillna(2)
    b["floors"] = floors.fillna(default_floors).clip(1, 40)
    b["gfa"] = b["footprint"] * b["floors"]

    m2 = btype.map(M2_PER_JOB)
    m2 = m2.where(~btype.isin(NO_JOBS), np.inf)
    # Unbekannter Typ: kleine Gebäude wie Nebengebäude, sonst wie Wohnhaus
    unk = btype.eq("unknown")
    m2 = m2.where(~unk, np.where(b["footprint"] < 60, np.inf, 3000))
    m2 = m2.fillna(400)   # bekannte, aber nicht gelistete Typen
    b["w_area"] = (b["gfa"] / m2).replace([np.inf, -np.inf], 0).fillna(0)

    # POIs (Overture Places) den Gebäuden zuordnen
    p = pd.read_parquet(RAW / "overture" / "places.parquet")
    p = p[(p["confidence"] >= 0.5) & (p["operating_status"].fillna("open") == "open")]
    pg = gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p["lon"], p["lat"]), crs=4326).to_crs(crs)
    pg["pjobs"] = (pg["hierarchy"].fillna(pg["category"])).map(poi_jobs)
    near = gpd.sjoin_nearest(pg[["pjobs", "geometry"]], b[["geometry"]], how="left", max_distance=25)
    near = near[~near.index.duplicated()]
    pj = near.groupby("index_right")["pjobs"].sum()
    b["w_poi"] = pj.reindex(b.index).fillna(0)
    unmatched = near["index_right"].isna().sum()
    log(f"  POIs: {len(pg)} zugeordnet, davon {unmatched} ohne Gebäude in 25 m")

    b["w"] = b["w_area"] + b["w_poi"]
    out = gpd.GeoDataFrame(b[["btype", "gfa", "w", "w_area", "w_poi"]],
                           geometry=b.geometry.representative_point(), crs=crs)
    log(f"  {len(out)} Gebäude, {int((out['w'] > 0).sum())} mit Arbeitsplätzen")
    return out
