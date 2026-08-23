#!/usr/bin/env python3
"""
demand_data.json für die Subway-Builder-Karte Nürnberg / Fürth / Erlangen bauen.

Beispiel:

    python3 build_demand.py \\
        --zensus  daten/Zensus2022_Bevoelkerungszahl_100m-Gitter.csv \\
        --buildings ../NUE/buildings.geojson \\
        --gemeinden daten/gemeinden.geojson \\
        --jobs    daten/beschaeftigte_arbeitsort.csv \\
        --pendler daten/pendler.csv \\
        --osrm    http://127.0.0.1:5000 \\
        --out     ../NUE/demand_data.json

Alles außer --zensus und --buildings ist optional; fehlt die Pendlermatrix,
rechnet das Skript ein reines Gravitationsmodell, fehlt OSRM, schätzt es die
Fahrzeiten. Läuft mit der Standardbibliothek, ohne numpy/pandas/pyproj.
"""

import argparse
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nuedemand import buildings as buildings_mod
from nuedemand.zensus import de_int
from nuedemand import commute, geo, jobs as jobs_mod, pendler, routing, zensus


QUIET = False


def log(msg):
    if not QUIET:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_bbox(text):
    parts = [float(v) for v in text.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox braucht 4 Werte: min_lon,min_lat,max_lon,max_lat")
    return parts


def load_geojson_features(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        return data.get("features", [])
    if isinstance(data, list):
        return data
    return [data]


def detect_key_property(features, preferred=None):
    """Findet die Spalte mit dem Gemeindeschlüssel."""
    if preferred:
        return preferred
    candidates = (
        "AGS", "ags", "AGS_0", "ARS", "ars",            # BKG VG250
        "de:amtlicher_gemeindeschluessel",              # OSM
        "ref:de:amtlicher_gemeindeschluessel",
        "gemeindeschluessel", "gemeindeschlüssel",
    )
    props = features[0].get("properties", {}) if features else {}
    for cand in candidates:
        if cand in props:
            return cand
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zensus", required=True, help="Zensus-2022-Gitter CSV (100 m)")
    ap.add_argument("--buildings", required=True, help="buildings.geojson aus dem Kartenbau")
    ap.add_argument("--gemeinden", help="GeoJSON mit Gemeindegrenzen")
    ap.add_argument("--gemeinde-key", help="Property mit dem AGS (wird sonst erraten)")
    ap.add_argument("--gemeinde-name-key", default="GEN",
                    help="Property mit dem Gemeindenamen (BKG: GEN, OSM: name)")
    ap.add_argument("--jobs", help="CSV: Beschäftigte am Arbeitsort je Gemeinde")
    ap.add_argument("--pendler", help="CSV: Pendlermatrix Gemeinde -> Gemeinde")
    ap.add_argument("--bbox", type=parse_bbox, default=[10.85, 49.32, 11.28, 49.66])
    ap.add_argument("--cell-size", type=int, default=400, help="Rasterweite der Nachfragepunkte in m")
    ap.add_argument("--top-k", type=int, default=15, help="Ziele je Wohnpunkt")
    ap.add_argument("--decay-km", type=float, default=6.0, help="Abstandsempfindlichkeit")
    ap.add_argument("--employment-rate", type=float, default=0.52)
    ap.add_argument("--max-pop-size", type=int, default=200)
    ap.add_argument("--non-sv-factor", type=float, default=1.22,
                    help="Aufschlag für Selbstständige/Beamte auf die SV-Beschäftigten")
    ap.add_argument("--jobs-fallback", type=int,
                    help="Gesamtzahl Arbeitsplätze, falls keine --jobs-CSV vorliegt")
    ap.add_argument("--osrm", help="Basis-URL eines OSRM-Servers, z. B. http://127.0.0.1:5000")
    ap.add_argument("--out", default="demand_data.json")
    ap.add_argument("--stats-out", help="Kennzahlen zusätzlich als JSON ablegen")
    ap.add_argument("--gzip", action="store_true", help="Ausgabe zusätzlich als .gz schreiben")
    ap.add_argument("--quiet", action="store_true", help="keine Fortschrittsausgabe")
    ap.add_argument("--list-gemeinden", action="store_true",
                    help="Nur die Gemeinden im Ausschnitt auflisten und beenden")
    args = ap.parse_args(argv)

    global QUIET
    QUIET = args.quiet
    bbox = args.bbox

    # --- Gemeindegrenzen ---------------------------------------------------
    gem_index = None
    gem_names = {}
    if args.gemeinden:
        feats = load_geojson_features(args.gemeinden)
        key = detect_key_property(feats, args.gemeinde_key)
        if not key:
            log(f"FEHLER: kein AGS-Feld in {args.gemeinden}. "
                f"Vorhandene Felder: {sorted((feats[0].get('properties') or {}).keys())[:20]}")
            return 2
        gem_index = geo.PolygonIndex(feats, key)
        name_key = args.gemeinde_name_key
        first_props = (feats[0].get("properties") or {}) if feats else {}
        if name_key not in first_props:
            for cand in ("GEN", "name", "NAME", "gemeinde", "GEMEINDE"):
                if cand in first_props:
                    name_key = cand
                    break
        for f in feats:
            props = f.get("properties") or {}
            if props.get(key) is not None:
                gem_names[str(props[key])] = props.get(name_key) or ""
        log(f"Gemeindegrenzen: {len(gem_index)} Flächen, Schlüsselfeld '{key}'")

        if args.list_gemeinden:
            hits = {}
            step_lon = (bbox[2] - bbox[0]) / 120.0
            step_lat = (bbox[3] - bbox[1]) / 120.0
            for i in range(121):
                for j in range(121):
                    ags = gem_index.lookup(bbox[0] + i * step_lon, bbox[1] + j * step_lat)
                    if ags:
                        hits[ags] = hits.get(ags, 0) + 1
            print(f"\n{len(hits)} Gemeinden im Ausschnitt:\n")
            for ags, count in sorted(hits.items(), key=lambda kv: -kv[1]):
                print(f"  {ags}  {gem_names.get(ags, ''):35s} ~{count/146.41:5.1f} % der Fläche")
            return 0
    elif args.list_gemeinden:
        log("FEHLER: --list-gemeinden braucht --gemeinden")
        return 2

    # --- Einwohner ---------------------------------------------------------
    log(f"Lese Zensus-Gitter {args.zensus}")
    cells = zensus.read_population_grid(args.zensus, bbox=bbox)
    log(zensus.describe(cells))
    if not cells:
        log("FEHLER: keine Zensuszellen im Ausschnitt — stimmen bbox und Datei?")
        return 1

    # --- Gebäude -----------------------------------------------------------
    log(f"Lese Gebäude {args.buildings}")
    blds = buildings_mod.read_buildings(args.buildings, bbox=bbox)
    log(f"Gebäude: {de_int(len(blds))}")
    for kind, stat in sorted(buildings_mod.summarize(blds).items(), key=lambda kv: -kv[1]["weight"]):
        log(f"   {kind:12s} {de_int(stat['count']):>9} Stück, Gewicht {de_int(stat['weight']):>12}")
    if not blds:
        log("FEHLER: keine Gebäude im Ausschnitt")
        return 1

    # --- Gemeindezuordnung -------------------------------------------------
    if gem_index:
        unmatched_b = jobs_mod.assign_to_municipality(blds, gem_index)
        unmatched_c = jobs_mod.assign_to_municipality(cells, gem_index)
        log(f"Ohne Gemeinde: {unmatched_b} Gebäude, {unmatched_c} Zensuszellen")

    # --- Arbeitsplätze -----------------------------------------------------
    if args.jobs and gem_index:
        jobs_by_ags = jobs_mod.read_jobs_csv(args.jobs, non_sv_factor=args.non_sv_factor)
        inside = set(b.get("ags") for b in blds)
        relevant = {k: v for k, v in jobs_by_ags.items() if k in inside}
        log(f"Beschäftigte: {len(relevant)} von {len(jobs_by_ags)} Gemeinden liegen im "
            f"Ausschnitt, {de_int(sum(relevant.values()))} Arbeitsplätze")
        report = jobs_mod.distribute(blds, relevant)
        if report["missing_buildings"]:
            log(f"WARNUNG: keine Gebäude für AGS {report['missing_buildings']}")
    else:
        # Ohne amtliche Zahlen: Gesamtsumme schätzen und rein über die
        # Gebäudegewichte verteilen. Deutlich schlechtere Datenqualität.
        total_jobs = args.jobs_fallback or int(
            zensus.total_residents(cells) * args.employment_rate
        )
        log(f"Keine --jobs-CSV: verteile geschätzte {de_int(total_jobs)} Arbeitsplätze "
            f"nur nach Gebäudegewicht")
        weight_sum = sum(b["weight"] for b in blds)
        for b in blds:
            b["jobs"] = total_jobs * b["weight"] / weight_sum

    # --- Punkte aggregieren ------------------------------------------------
    params = commute.Params(
        cell_size_m=args.cell_size,
        employment_rate=args.employment_rate,
        decay_km=args.decay_km,
        top_k=args.top_k,
        max_pop_size=args.max_pop_size,
    )
    log(f"Aggregiere auf {args.cell_size} m Raster")
    points = commute.aggregate_points(cells, blds, params)
    log(f"Nachfragepunkte: {de_int(len(points))}")
    moved = commute.fill_missing_ags(points)
    if moved:
        log(f"{moved} Punkte ohne Gemeinde der nächstgelegenen zugeordnet")

    # --- Pendlerbeziehungen ------------------------------------------------
    matrix = None
    if args.pendler:
        keep = set(p["ags"] for p in points if p["ags"])
        matrix, info = pendler.read_matrix(args.pendler, keep_ags=keep or None)
        log(f"Pendlermatrix: {len(matrix)} Binnenbeziehungen, "
            f"{de_int(info['inbound_outside'])} Einpendler und "
            f"{de_int(info['outbound_outside'])} Auspendler über den Kartenrand "
            f"(bleiben außen vor)")

    flow_report = {}
    log("Verteile Pendler auf die Punkte")
    flows = commute.build_flows(points, params, matrix=matrix, report=flow_report)
    log(f"Beziehungen: {de_int(len(flows))} | Modus: {flow_report['mode']} | "
        f"verteilte Pendler: {de_int(flow_report['used_total'])}")
    if flow_report.get("skipped_pairs"):
        skipped = sum(s["count"] for s in flow_report["skipped_pairs"])
        log(f"WARNUNG: {len(flow_report['skipped_pairs'])} Gemeindepaare ohne Punkte "
            f"({de_int(skipped)} Pendler) übersprungen")

    # --- Fahrzeiten --------------------------------------------------------
    route_fn = None
    if args.osrm:
        client = routing.OSRMClient(args.osrm)
        if client.available():
            log(f"OSRM erreichbar unter {args.osrm} — route echte Fahrten")
            route_fn = lambda pairs: routing.route_pairs(pairs, client=client)
        else:
            log(f"WARNUNG: OSRM unter {args.osrm} nicht erreichbar — schätze Fahrzeiten")
    if route_fn is None:
        log("Fahrzeiten werden geschätzt (Luftlinie x Umwegfaktor)")

    demand = commute.to_demand_data(points, flows, route_fn=route_fn, params=params)

    # --- Ausgabe -----------------------------------------------------------
    stats = commute.statistics(demand)
    dropped = len(points) - stats["points_count"]
    if dropped:
        lost_res = sum(p["residents"] for p in points) - stats["residents_total"]
        log(f"HINWEIS: {dropped} Punkte ohne Pendlerbeziehung entfallen "
            f"({de_int(lost_res)} Einwohner). Bei Bedarf --top-k erhöhen "
            f"oder --cell-size vergrößern.")
    log("Kennzahlen:")
    for key, value in stats.items():
        log(f"   {key:20s} {value}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(demand, fh, separators=(",", ":"))
    size_mb = os.path.getsize(args.out) / 1e6
    log(f"Geschrieben: {args.out} ({size_mb:.1f} MB)")

    if args.gzip:
        with open(args.out, "rb") as src, gzip.open(args.out + ".gz", "wb") as dst:
            dst.write(src.read())
        log(f"Geschrieben: {args.out}.gz ({os.path.getsize(args.out + '.gz')/1e6:.1f} MB)")

    if args.stats_out:
        with open(args.stats_out, "w", encoding="utf-8") as fh:
            json.dump({"stats": stats, "flows": flow_report}, fh, indent=2, ensure_ascii=False)
        log(f"Geschrieben: {args.stats_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
