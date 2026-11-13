#!/usr/bin/env python3
"""
Schritt 2: Basiskarte bauen.

Erzeugt in work/out/NEF/:

    NEF.pmtiles              Vektorkacheln: Wasser, Grün, Nutzung, Gebäude, Labels
    NEF_foundations.pmtiles  Fundamenttiefen der Gebäude (Kartenebene im Spiel)
    buildings_index.bin.gz   Kollisionsdaten für den Trassenbau
    roads.geojson.gz         Straßennetz
    runways_taxiways.geojson.gz  Start- und Rollbahnen Flughafen Nürnberg

Werkzeuge: java + planetiler.jar, tippecanoe, tile-join, pmtiles, osmium.
"""

import gzip
import json
import os
import sqlite3
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import box, mapping

from nef import buildings_index, tiles
from nef.common import BBOX, CODE, MAXZOOM, OUT, RAW, REGION, TMP, log, run, utm_epsg, write_json

OSM = RAW / "osm" / "region.osm.pbf"
BUILD_TMP = TMP / "basemap"
BUILD_TMP.mkdir(parents=True, exist_ok=True)
NCORES = os.cpu_count() or 4


def find_planetiler():
    for d in os.environ["PATH"].split(os.pathsep):
        p = Path(d) / "planetiler.jar"
        if p.exists():
            return p
    raise SystemExit("planetiler.jar nicht im PATH (oder NEF_TOOLS) gefunden")


# --------------------------------------------------------------------------
# 1. Basiskacheln
# --------------------------------------------------------------------------

def base_tiles():
    raw = BUILD_TMP / "planetiler.mbtiles"
    fixed = BUILD_TMP / "base.mbtiles"
    if not raw.exists():
        run(["java", "-Xmx8g", "-jar", str(find_planetiler()),
             f"--osm-path={OSM}", f"--output={raw}",
             "--bounds=" + ",".join(map(str, BBOX)),
             "--download", f"--download_dir={TMP / 'planetiler-sources'}",
             f"--tmpdir={TMP / 'planetiler-tmp'}",
             "--minzoom=0", f"--maxzoom={MAXZOOM}",
             "--only-layers=aeroway,landcover,landuse,park,water,waterway",
             "--force"])
    if fixed.exists():
        fixed.unlink()
    n_in, n_out = tiles.convert(raw, fixed, BBOX, workers=NCORES)
    log(f"Basiskacheln umgebaut: {n_in} -> {n_out}")
    return fixed


# --------------------------------------------------------------------------
# 2. Gebäude
# --------------------------------------------------------------------------

# Geschätzte Höhen (m) nach Overture-/OSM-Gebäudeklasse, falls weder Höhe
# noch Geschosszahl bekannt sind.
CLASS_HEIGHT = {
    "apartments": 14, "residential": 11, "house": 8, "detached": 8,
    "semidetached_house": 8, "terrace": 9, "bungalow": 4, "dormitory": 14,
    "garage": 3, "garages": 3, "carport": 3, "shed": 3, "hut": 3, "roof": 4,
    "allotment_house": 3, "greenhouse": 4, "farm_auxiliary": 6, "barn": 7,
    "industrial": 10, "warehouse": 10, "manufacture": 10, "service": 4,
    "commercial": 12, "retail": 8, "office": 16, "supermarket": 7,
    "school": 12, "university": 16, "college": 14, "kindergarten": 6,
    "hospital": 20, "church": 18, "cathedral": 30, "hotel": 18,
    "train_station": 12, "transformer_tower": 6, "parking": 10, "stadium": 25,
}
DEFAULT_HEIGHT = 7.0


def estimate_height(df):
    h = pd.to_numeric(df["height"], errors="coerce")
    floors = pd.to_numeric(df["num_floors"], errors="coerce")
    from_floors = floors * 3.0 + 1.5
    from_class = df["class"].map(CLASS_HEIGHT)
    out = h.where(h > 0, from_floors.where(floors > 0, from_class))
    return out.fillna(DEFAULT_HEIGHT).clip(2.5, 200.0)


def foundation_depth(geoms_utm, height, alpha=0.25):
    """Fundamenttiefe aus Höhe und Schmalseite der Grundfläche, 10…80 m."""
    rect = shapely.oriented_envelope(geoms_utm)
    coords = shapely.get_coordinates(shapely.get_exterior_ring(rect)).reshape(len(rect), -1, 2)
    s1 = np.hypot(*(coords[:, 1] - coords[:, 0]).T)
    s2 = np.hypot(*(coords[:, 2] - coords[:, 1]).T)
    w = np.minimum(s1, s2)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = alpha * height * (height / w) ** 0.25
    d = np.where(w > 0, d, 10)
    return np.clip(d, 10, 80).astype(int)


def load_buildings():
    df = pd.read_parquet(RAW / "overture" / "buildings.parquet")
    g = gpd.GeoDataFrame(df.drop(columns="geom"), geometry=gpd.GeoSeries.from_wkb(df["geom"]), crs=4326)
    g = g.explode(index_parts=False).reset_index(drop=True)
    g = g[g.geom_type == "Polygon"]
    g["height"] = estimate_height(g)
    utm = g.to_crs(utm_epsg())
    utm["geometry"] = shapely.make_valid(utm.geometry.values)
    utm = utm.explode(index_parts=False)
    utm = utm[utm.geom_type == "Polygon"].reset_index(drop=True)
    utm["area"] = utm.area
    return utm


def buildings():
    log("Gebäude laden …")
    utm = load_buildings()
    log(f"  {len(utm)} Grundrisse")

    # Für Kollisionen: >= 40 m², auf 1 m vereinfacht
    idx = utm[utm["area"] >= 40].copy()
    idx["geometry"] = shapely.simplify(idx.geometry.values, 1.0, preserve_topology=True)
    idx = idx[~idx.geometry.is_empty & idx.geometry.is_valid]
    idx["depth"] = foundation_depth(idx.geometry.values, idx["height"].values)
    wgs = idx.to_crs(4326)
    items = []
    for geom, d in zip(wgs.geometry.values, wgs["depth"].values):
        rings = [np.asarray(geom.exterior.coords)] + [np.asarray(r.coords) for r in geom.interiors]
        items.append((rings, d))
    buf = buildings_index.encode(items)
    info = buildings_index.decode(buf)
    log(f"  Gebäude-Index: {info['count']} Gebäude, {info['cells']} Zellen, "
        f"max. Tiefe {info['maxDepth']:.0f} m, {len(buf) / 1e6:.1f} MB")
    with gzip.open(OUT / "buildings_index.bin.gz", "wb", compresslevel=9) as fh:
        fh.write(buf)
    # Zusätzlich das JSON-Format: Railyard nimmt es, wenn es die Spielversion
    # nicht erkennt oder sie <= 1.3.0 ist (sonst wird die Karte übersprungen).
    write_json(OUT / "buildings_index.json.gz", buildings_index.encode_json(items), gz=True)
    log(f"  buildings_index.json.gz: {(OUT / 'buildings_index.json.gz').stat().st_size / 1e6:.1f} MB")

    # Für die Kacheln: >= 25 m², auf 0.5 m vereinfacht
    tl = utm[utm["area"] >= 25].copy()
    tl["geometry"] = shapely.simplify(tl.geometry.values, 0.5, preserve_topology=True)
    tl = tl[~tl.geometry.is_empty & tl.geometry.is_valid]
    tl["foundationDepth"] = foundation_depth(tl.geometry.values, tl["height"].values)
    tl = tl.to_crs(4326)
    bjson = BUILD_TMP / "buildings.geojsonl"
    fjson = BUILD_TMP / "foundations.geojsonl"
    with open(bjson, "w") as fb, open(fjson, "w") as ff:
        for geom, h, d in zip(tl.geometry.values, tl["height"].values, tl["foundationDepth"].values):
            gm = json.dumps(mapping(shapely.set_precision(geom, 1e-6)))
            fb.write(f'{{"type":"Feature","properties":{{"height":{round(float(h), 1)}}},"geometry":{gm}}}\n')
            ff.write(f'{{"type":"Feature","properties":{{"foundationDepth":{int(d)}}},"geometry":{gm}}}\n')
    limit = ["--drop-smallest-as-needed", "--maximum-tile-bytes=450000"]
    bmb = BUILD_TMP / "buildings.mbtiles"
    fmb = BUILD_TMP / "foundations.mbtiles"
    run(["tippecanoe", "-o", str(bmb), "--layer=buildings", "--include=height", *limit,
         "-Z12", f"-z{MAXZOOM}", "-P", str(bjson), "--force", "--quiet"])
    run(["tippecanoe", "-o", str(fmb), "--layer=foundations", "--include=foundationDepth", *limit,
         "-Z12", f"-z{MAXZOOM}", "-P", str(fjson), "--force", "--quiet"])
    return bmb, fmb


# --------------------------------------------------------------------------
# 3. Labels
# --------------------------------------------------------------------------

def labels():
    lab = REGION["labels"]
    layer_files = []
    places = BUILD_TMP / "places.geojson"
    run(["osmium", "tags-filter", str(OSM), "n/place", "-o", str(BUILD_TMP / "places.osm.pbf"), "--overwrite"])
    run(["osmium", "export", str(BUILD_TMP / "places.osm.pbf"), "-o", str(places), "--overwrite"])
    feats = json.loads(places.read_text())["features"]
    clip = box(*BBOX)
    counts = {}
    for layer, kinds in (("city_labels", lab["cities"]), ("suburb_labels", lab["suburbs"]),
                         ("neighborhood_labels", lab["neighborhoods"])):
        sel = []
        for f in feats:
            p = f["properties"]
            name = p.get("name:de") or p.get("name")
            if p.get("place") in kinds and name and clip.contains(shapely.geometry.shape(f["geometry"])):
                sel.append({"type": "Feature", "properties": {"name": name, "place": p["place"]},
                            "geometry": f["geometry"]})
        counts[layer] = len(sel)
        path = BUILD_TMP / f"{layer}.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": sel}, ensure_ascii=False))
        layer_files += ["-L", f"{layer}:{path}"]
    log(f"  Labels: {counts}")
    out = BUILD_TMP / "labels.mbtiles"
    run(["tippecanoe", "-Z", "6", "-z", str(MAXZOOM), "-r", "1", "-y", "name", "-y", "place",
         "-o", str(out), "--no-tile-size-limit", "--clip-bounding-box=" + ",".join(map(str, BBOX)),
         "--force", "--quiet", *layer_files])
    return out


# --------------------------------------------------------------------------
# 4. Straßen und Rollbahnen
# --------------------------------------------------------------------------

ROADS = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
         "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential"]


def osm_lines(filter_expr, name, geom_types="linestring"):
    pbf = BUILD_TMP / f"{name}.osm.pbf"
    gj = BUILD_TMP / f"{name}.geojson"
    run(["osmium", "tags-filter", str(OSM), filter_expr, "-o", str(pbf), "--overwrite"])
    run(["osmium", "export", str(pbf), "-o", str(gj), f"--geometry-types={geom_types}",
         "--add-unique-id=type_id", "--overwrite"])
    return json.loads(gj.read_text())["features"]


def roads():
    clip = box(*BBOX)
    out = []
    for f in osm_lines("w/highway=" + ",".join(ROADS), "roads"):
        p = f["properties"]
        hw = p.get("highway")
        g = shapely.geometry.shape(f["geometry"]).intersection(clip)
        if g.is_empty:
            continue
        out.append({"type": "Feature", "properties": {
            "roadClass": "highway" if hw in ("motorway", "trunk") else
                         "major" if hw in ("primary", "secondary") else "minor",
            "structure": "bridge" if p.get("bridge") not in (None, "no") else
                         "tunnel" if p.get("tunnel") not in (None, "no") else "normal",
            "name": p.get("name:de") or p.get("name") or ""},
            "geometry": mapping(g)})
    with gzip.open(OUT / "roads.geojson.gz", "wt", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": out}, fh, ensure_ascii=False, separators=(",", ":"))
    log(f"  Straßen: {len(out)} Abschnitte")

    aero = []
    for f in osm_lines("wr/aeroway=runway,taxiway", "aeroways", "linestring,polygon"):
        p = f["properties"]
        g = shapely.geometry.shape(f["geometry"])
        if g.geom_type in ("LineString", "MultiLineString"):
            g = g.buffer(0.00015, cap_style=2)
        g = g.intersection(clip)
        if g.is_empty:
            continue
        parts = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        for part in parts:
            if part.geom_type != "Polygon":
                continue
            aero.append({"type": "Feature", "properties": {
                "roadType": p.get("aeroway", "runway"), "z_order": 0,
                "osm_way_id": str(f.get("id", "")).lstrip("awrn"), "area": 0},
                "geometry": mapping(part)})
    with gzip.open(OUT / "runways_taxiways.geojson.gz", "wt", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": aero}, fh, separators=(",", ":"))
    log(f"  Start-/Rollbahnen: {len(aero)} Flächen")


# --------------------------------------------------------------------------
# 5. Zusammenführen
# --------------------------------------------------------------------------

def set_meta(mbtiles):
    con = sqlite3.connect(mbtiles)
    for k, v in (("name", f"{CODE} Basemap"), ("type", "baselayer"),
                 ("bounds", ",".join(map(str, BBOX))),
                 ("attribution", "© OpenStreetMap-Mitwirkende, Overture Maps Foundation")):
        con.execute("DELETE FROM metadata WHERE name=?", (k,))
        con.execute("INSERT INTO metadata VALUES (?, ?)", (k, v))
    con.execute("DELETE FROM metadata WHERE name='generator_options'")
    con.commit()
    con.close()


def assemble(base, bmb, fmb, lmb):
    merged = BUILD_TMP / f"{CODE}.mbtiles"
    run(["tile-join", "--force", "--no-tile-size-limit", "-o", str(merged), str(base), str(bmb), str(lmb)])
    set_meta(merged)
    run(["pmtiles", "convert", str(merged), str(OUT / f"{CODE}.pmtiles")])
    set_meta(fmb)
    run(["pmtiles", "convert", str(fmb), str(OUT / f"{CODE}_foundations.pmtiles")])
    for f in (f"{CODE}.pmtiles", f"{CODE}_foundations.pmtiles"):
        log(f"  {f}: {(OUT / f).stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    import sys
    if "--nur-gebaeude" in sys.argv:      # nur Gebäude neu (z. B. nach Formatänderung)
        buildings()
        raise SystemExit
    base = base_tiles()
    bmb, fmb = buildings()
    lmb = labels()
    roads()
    assemble(base, bmb, fmb, lmb)
    log("Basiskarte fertig.")
