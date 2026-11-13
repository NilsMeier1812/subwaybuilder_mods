#!/usr/bin/env python3
"""
Schritt 1: alle Rohdaten herunterladen.

  * OpenStreetMap: BBBike-Extrakte Nürnberg + Erlangen, zusammengeführt,
    plus ein Flicken über die OSM-API für die Ecke, die beide nicht abdecken
  * Overture Maps: Gebäude (mit Höhe, Geschossen, Nutzungsklasse) und Orte (POIs)
  * Zensus 2022: Bevölkerung und Altersklassen im 100-m-Gitter
  * Pendlerrechnung der Statistischen Ämter (Pendleratlas): Erwerbstätige je
    Gemeinde und die stärksten Pendlerbeziehungen Gemeinde -> Gemeinde
  * Gemeindegrenzen (aus dem Pendleratlas, Stand 2024)

Bereits vorhandene Dateien werden nicht erneut geladen.
"""

import io
import shutil
import urllib.request
import zipfile

from nef.common import BBOX, RAW, REGION, log, run

SRC = REGION["sources"]
UA = {"User-Agent": "subwaybuilder-map-build/1.0"}


def fetch(url, dest, timeout=900):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log(f"vorhanden: {dest.name}")
        return dest
    log(f"lade {url}")
    req = urllib.request.Request(url, headers=UA)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as fh:
        shutil.copyfileobj(r, fh, 1 << 20)
    tmp.rename(dest)
    return dest


def osm():
    d = RAW / "osm"
    final = d / "region.osm.pbf"
    if final.exists():
        log("vorhanden: region.osm.pbf")
        return
    parts = [fetch(u, d / u.rsplit("/", 1)[1]) for u in SRC["osm_extracts"]]
    for i, bb in enumerate(SRC.get("osm_api_patches", [])):
        xml = d / f"patch{i}.osm"
        fetch("https://api.openstreetmap.org/api/0.6/map?bbox=" + ",".join(map(str, bb)), xml)
        run(["osmium", "sort", str(xml), "-o", str(d / f"patch{i}.osm.pbf"), "--overwrite"])
        parts.append(d / f"patch{i}.osm.pbf")
    run(["osmium", "merge", *map(str, parts), "-o", str(d / "merged.osm.pbf"), "--overwrite"])
    # Mehrere Versionen desselben Objekts (Extrakt vs. API) -> nur die neueste
    run(["osmium", "time-filter", str(d / "merged.osm.pbf"), "-o", str(d / "latest.osm.pbf"), "--overwrite"])
    pad = 0.05
    bb = [BBOX[0] - pad, BBOX[1] - pad, BBOX[2] + pad, BBOX[3] + pad]
    run(["osmium", "extract", "-b", ",".join(map(str, bb)), "-s", "smart",
         str(d / "latest.osm.pbf"), "-o", str(final), "--overwrite"])


def zensus():
    d = RAW / "zensus"
    for key, name in (("zensus_population", "bevoelkerung"), ("zensus_age5", "alter5")):
        csv = d / f"{name}_100m.csv"
        if csv.exists():
            log(f"vorhanden: {csv.name}")
            continue
        z = fetch(SRC[key], d / f"{name}.zip")
        with zipfile.ZipFile(z) as zf:
            member = next(n for n in zf.namelist() if n.endswith("100m-Gitter.csv"))
            with zf.open(member) as src, open(csv, "wb") as dst:
                shutil.copyfileobj(src, dst)
        z.unlink()


def pendleratlas():
    d = RAW / "pendler"
    y = SRC["pendleratlas_year"]
    base = SRC["pendleratlas_base"]
    for f in (f"{y}_Verfl_L09.csv", f"{y}_EZ_L09.csv", f"{y}_StB_L09.csv"):
        fetch(f"{base}/csv/{y}/{f}", d / f)
    # Gemeindemittelpunkte ganz Deutschlands (Ziele außerhalb der Karte)
    fetch(f"{base}/geojson/gemeinden_{y}.json", d / f"gemeinden_{y}.json")


def gemeindegrenzen():
    """Amtliche Gemeindegrenzen (BKG VG250), nur Mittelfranken behalten."""
    import geopandas as gpd
    out = RAW / "vg250_gemeinden_mfr.gpkg"
    if out.exists():
        log("vorhanden: vg250_gemeinden_mfr.gpkg")
        return
    z = fetch(SRC["vg250"], RAW / "vg250.zip")
    with zipfile.ZipFile(z) as zf:
        member = next(n for n in zf.namelist() if n.endswith(".gpkg"))
        zf.extract(member, RAW / "vg250")
    g = gpd.read_file(RAW / "vg250" / member, layer="vg250_gem")
    g = g[g["ARS"].str.startswith("095") & (g["GF"] == 4)]   # Mittelfranken, nur Landflächen
    g[["ARS", "AGS", "GEN", "BEZ", "geometry"]].to_file(out, driver="GPKG")
    shutil.rmtree(RAW / "vg250")
    z.unlink()


def overture():
    import duckdb
    import json
    d = RAW / "overture"
    d.mkdir(parents=True, exist_ok=True)
    rel = json.load(urllib.request.urlopen(urllib.request.Request(SRC["overture_stac"], headers=UA)))["latest"]
    log(f"Overture-Release {rel}")
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    # Öffentlicher Bucket: ausdrücklich anonym zugreifen, damit eventuell
    # gesetzte AWS-Umgebungsvariablen nicht stören.
    con.execute("CREATE OR REPLACE SECRET overture (TYPE s3, KEY_ID '', SECRET '', REGION 'us-west-2')")
    w = (f"bbox.xmin >= {BBOX[0]} AND bbox.xmax <= {BBOX[2]} AND "
         f"bbox.ymin >= {BBOX[1]} AND bbox.ymax <= {BBOX[3]}")
    root = f"s3://overturemaps-us-west-2/release/{rel}"
    jobs = {
        "buildings.parquet": f"""
            SELECT id, height, num_floors, class, subtype, names.primary AS name,
                   ST_AsWKB(geometry) AS geom
            FROM read_parquet('{root}/theme=buildings/type=building/*', hive_partitioning=1)
            WHERE {w}""",
        "places.parquet": f"""
            SELECT id, names.primary AS name, taxonomy.primary AS category,
                   array_to_string(taxonomy.hierarchy, '>') AS hierarchy,
                   basic_category, operating_status, confidence, ST_X(geometry) AS lon, ST_Y(geometry) AS lat
            FROM read_parquet('{root}/theme=places/type=place/*', hive_partitioning=1)
            WHERE {w}""",
    }
    for fname, q in jobs.items():
        out = d / fname
        if out.exists():
            log(f"vorhanden: {fname}")
            continue
        log(f"Overture-Abfrage {fname} …")
        con.execute(f"COPY ({q}) TO '{out}' (FORMAT parquet)")
        log(f"  {con.execute(f'SELECT count(*) FROM read_parquet(\'{out}\')').fetchone()[0]} Datensätze")
    (d / "RELEASE").write_text(rel)


if __name__ == "__main__":
    osm()
    zensus()
    pendleratlas()
    gemeindegrenzen()
    overture()
    log("Download fertig.")
