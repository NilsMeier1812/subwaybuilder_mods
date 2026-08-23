#!/usr/bin/env python3
"""
Sonderziele an eine fertige demand_data.json anhängen.

Flughafen, Hochschulen, Stadion, Messe, Tiergarten — das sind Ziele, deren
Nachfrage nicht aus Wohnen und Arbeiten folgt und die im Spiel den Reiz
ausmachen. Subway Builder erwartet dafür Punkte mit einem Typ-Präfix in der
ID (``AIR_NUE``, ``UNI_THN`` …) plus zwei Schemadateien.

Dieses Skript nutzt dafür ``depot`` — die Bibliothek der Modding-Community —
statt das Format nachzubauen: sie kennt die Typ-Taxonomie und schreibt
``special_demand_types.json`` und ``special_demand_points.json`` korrekt.

    pip install .   # im geklonten depot-Repo
    python3 add_special_demand.py \\
        --demand ../NUE/demand_data.json \\
        --region region.json \\
        --outdir ../NUE

Ohne depot läuft das Skript nicht — die Basiskarte und die Grundnachfrage
(build_demand.py) sind davon unabhängig und laufen mit der
Standardbibliothek.
"""

import argparse
import json
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demand", required=True, help="vorhandene demand_data.json")
    ap.add_argument("--region", default="region.json")
    ap.add_argument("--outdir", default=".", help="Zielverzeichnis für die Ausgabedateien")
    ap.add_argument("--map-code", default="NUE")
    ap.add_argument("--dry-run", action="store_true", help="nur zeigen, was übergeben würde")
    args = ap.parse_args(argv)

    with open(args.region, encoding="utf-8") as fh:
        region = json.load(fh)

    poi = []
    for item in region["special_demand"]:
        entry = {
            "type": item["type"],
            "name": item["name"],
            "location": item["location"],
            "total_capacity": int(item["total_capacity"]),
            "pop_size": int(item.get("pop_size", 100)),
        }
        if item.get("code"):
            entry["code"] = item["code"]
        if item.get("residential_split"):
            entry["residential_split"] = float(item["residential_split"])
        if item.get("max_distance"):
            entry["max_distance"] = item["max_distance"]
        if item.get("exponent") is not None:
            entry["exponent"] = item["exponent"]
        poi.append(entry)

    print(f"{len(poi)} Sonderziele aus {args.region}:")
    for entry in poi:
        print(f"   {entry['type']:18s} {entry['name'][:40]:40s} "
              f"{entry['total_capacity']:>7} Personen")

    if args.dry_run:
        print("\n--dry-run: nichts geschrieben.")
        return 0

    try:
        from depot.demand import DemandData
    except ImportError:
        print("\nFEHLER: 'depot' ist nicht installiert.\n"
              "  git clone https://github.com/Subway-Builder-Modded/depot.git\n"
              "  cd depot && pip install .\n"
              "Siehe ../../ANLEITUNG.md, Schritt 6.", file=sys.stderr)
        return 2

    data = DemandData(args.demand, map_code=args.map_code,
                      bbox=region["bbox"], outputdir=args.outdir)
    data.add_points(poi)
    data.print_stats()
    data.save()
    data.save_schemas()

    data.create_config(
        name=region.get("name", "Nürnberg"),
        bbox=region["bbox"],
        description=region.get("description", "Metropolregion Nürnberg – Fürth – Erlangen."),
        creator=region.get("creator", ""),
        version=region.get("version", "0.1.0"),
        country=region.get("country", "DE"),
        initial_view_state=[
            region["initial_view_state"]["longitude"],
            region["initial_view_state"]["latitude"],
        ],
    )
    print(f"\nGeschrieben nach {os.path.abspath(args.outdir)}: "
          "demand_data.json, special_demand_types.json, "
          "special_demand_points.json, config.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
