#!/usr/bin/env bash
# Komplette Karte bauen: Download -> Basiskarte -> Nachfrage -> ZIP.
# Dauer auf 4 Kernen / 16 GB RAM: etwa 15 Minuten (ohne Downloads).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 01_download.py
python3 02_basemap.py
python3 03_demand.py
python3 04_package.py
