"""Gemeinsame Pfade, Konfiguration und kleine Helfer für den Kartenbau."""

import gzip
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent.parent
REGION = json.loads((BUILD_DIR / "region.json").read_text(encoding="utf-8"))

# Arbeitsverzeichnis für Rohdaten und Zwischenstände (groß, nicht im Repo).
WORK = Path(os.environ.get("NEF_WORK", BUILD_DIR / "work")).resolve()
RAW = WORK / "raw"
TMP = WORK / "tmp"
OUT = WORK / "out" / REGION["code"]       # fertige Spieldateien
DIST = BUILD_DIR.parent / "dist"           # fertiges ZIP (im Repo)

for _d in (RAW, TMP, OUT):
    _d.mkdir(parents=True, exist_ok=True)

CODE = REGION["code"]
BBOX = REGION["bbox"]                      # [min_lon, min_lat, max_lon, max_lat]
MAXZOOM = 15

# Externe Werkzeuge: zuerst NEF_TOOLS, dann PATH.
TOOLS = os.environ.get("NEF_TOOLS")
if TOOLS:
    os.environ["PATH"] = TOOLS + os.pathsep + os.environ["PATH"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd, **kw):
    """Externes Programm ausführen, bei Fehler abbrechen."""
    shown = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    log("$ " + (shown if len(shown) < 300 else shown[:300] + " …"))
    res = subprocess.run(cmd, shell=isinstance(cmd, str), **kw)
    if res.returncode != 0:
        sys.exit(f"Befehl fehlgeschlagen ({res.returncode}): {shown[:200]}")
    return res


def write_json(path, obj, gz=False):
    path = Path(path)
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if gz:
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
            fh.write(data)
    else:
        path.write_text(data, encoding="utf-8")


def read_json(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


EARTH_R = 6371008.8


def haversine_m(lon1, lat1, lon2, lat2):
    """Großkreisdistanz in Metern; funktioniert mit Skalaren und numpy-Arrays."""
    import numpy as np
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.sqrt(a))


def utm_epsg():
    lon = (BBOX[0] + BBOX[2]) / 2
    return 32600 + int(math.floor((lon + 180) / 6) + 1)   # 32632 für Franken
