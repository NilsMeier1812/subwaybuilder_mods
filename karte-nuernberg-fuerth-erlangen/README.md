# Karte Nürnberg / Fürth / Erlangen — Subway Builder

Eigene Karte für [Subway Builder](https://www.subwaybuilder.com): die
Metropolregion Nürnberg – Fürth – Erlangen unter dem Stadtcode **NUE**.

> **Stand:** Code fertig und getestet, Kartendaten noch nicht gebaut.
> Was noch zu tun ist, steht Schritt für Schritt in
> [**ANLEITUNG.md**](ANLEITUNG.md). Der Bau muss auf einem Rechner mit
> Internetzugang zu Geofabrik, Overture und den Statistikportalen laufen —
> in der Cloud-Session, in der dieses Projekt entstanden ist, sperrt der
> Netzwerk-Proxy diese Hosts.

## Kartenausschnitt

| | |
| --- | --- |
| Stadtcode | `NUE` (IATA-Code Flughafen Nürnberg) |
| BBox | `10.85, 49.32, 11.28, 49.66` (min_lon, min_lat, max_lon, max_lat) |
| Fläche | ca. 34 × 38 km ≈ 1 300 km² |
| Startkamera | Nürnberg Hbf, 49.4455 / 11.0823, Zoom 12.5 |
| Einwohner im Ausschnitt | ca. 880 000 |

Enthalten: Nürnberg komplett inkl. Flughafen und Langwasser, Fürth, Erlangen
bis Erlangen-Nord, dazu Stein, Zirndorf, Oberasbach, Schwabach-Nord,
Herzogenaurach-Ost, Lauf a. d. Pegnitz und Röthenbach.

Zum Vergleich: die bestehende Community-Karte Berlin hat rund 1 344 km²
spielbare Fläche — die Größenordnung passt also.

## Was das Spiel braucht

Nach der offiziellen Doku (Guides → *Custom Cities*, API-Referenz → *Cities*
und *Map*) besteht eine Karte aus drei Aufrufen und sechs Datendateien:

```js
api.registerCity({ name, code, description, population, initialViewState });
api.map.setTileURLOverride({ cityCode, tilesUrl, foundationTilesUrl, maxZoom });
api.cities.setCityDataFiles(code, {
  buildingsIndex, demandData, roads, runwaysTaxiways /*, oceanDepthIndex, buildingTags */
});
```

| Datei | Inhalt | Woher |
| --- | --- | --- |
| `NUE.pmtiles` | Vektorkacheln: Gebäude, Straßen, Wasser, Grün, Labels | `build/mapgen_nue.py` |
| `NUE_foundations.pmtiles` | Gebäudefundamente (Bautiefe) | `build/mapgen_nue.py` |
| `buildings_index.json(.gz)` | Gebäudegeometrie für Kollisionen beim Tunnelbau | `build/mapgen_nue.py` |
| `roads.geojson(.gz)` | Straßennetz für oberirdische Trassen | `build/mapgen_nue.py` |
| `runways_taxiways.geojson(.gz)` | Start-/Rollbahnen Flughafen Nürnberg | `build/mapgen_nue.py` |
| `demand_data.json(.gz)` | Wohn-/Arbeitspunkte + Pendlerbeziehungen | eigener Schritt, siehe unten |
| `config.json` | Metadaten für Railyard-Import | `build/config.json` (Vorlage) |

`ocean_depth_index.json` entfällt — Binnenland ohne Meer.

## Bauen

### 1. Werkzeuge

`depot` (die Python-Bibliothek der Modding-Community) übernimmt die
Kartenerzeugung. Auf Windows nur unter WSL.

```bash
git clone https://github.com/Subway-Builder-Modded/depot.git
cd depot
conda env create -f environment.yml     # oder eigene Umgebung, Versionen s. dortige README
conda activate depot
pip install .
```

Zusätzlich müssen im `PATH` liegen und ausführbar sein:
`node`, [`mapshaper`](https://github.com/mbloch/mapshaper),
[`osmium`](https://osmcode.org/osmium-tool/), `java`,
[`tippecanoe` + `tile-join`](https://github.com/felt/tippecanoe), `sqlite3`,
`jq`, [`pmtiles`](https://github.com/protomaps/go-pmtiles/releases) sowie
[`planetiler.jar`](https://github.com/onthegomap/planetiler/releases).
Für die Fahrzeitberechnung zusätzlich Docker (OSRM).

Richtwerte: 16 GB RAM, ~20 GB freier Platz, mehrere Stunden Rechenzeit.

### 2. Basiskarte

```bash
cd karte-nuernberg-fuerth-erlangen/build
python3 mapgen_nue.py
```

Das Skript lädt `mittelfranken-latest.osm.pbf` von der Geofabrik (~100 MB),
holt die Gebäude von Overture und schreibt alles nach `./NUE/`.

`check_labels()` läuft mit und zeigt, welche `place`-Tags es in der Region
gibt — danach ggf. die Listen `cities` / `suburbs` / `neighborhoods` im Skript
nachjustieren und nur `add_labels()` erneut laufen lassen.

### 3. Nachfragedaten

```bash
cd build/demand
python3 build_demand.py \
    --zensus    ../../../daten/zensus_nue.csv \
    --buildings ../NUE/buildings.geojson \
    --gemeinden ../../../daten/gemeinden.geojson \
    --jobs      ../../../daten/beschaeftigte_arbeitsort.csv \
    --pendler   ../../../daten/pendler.csv \
    --osrm      http://127.0.0.1:5000 \
    --out       ../NUE/demand_data.json
```

Die Pipeline liegt fertig in [`build/demand/`](build/demand/) und läuft mit
der Python-Standardbibliothek — kein numpy, pandas, geopandas oder pyproj:

1. **Einwohner** aus dem Zensus-2022-100-m-Gitter. Die Koordinaten stecken in
   der INSPIRE-Gitter-ID (EPSG:3035); die Rückprojektion nach WGS84 rechnet
   `nuedemand/laea.py` selbst.
2. **Arbeitsplätze** aus den SV-Beschäftigten am Arbeitsort je Gemeinde,
   innerhalb der Gemeinde nach Gebäudenutzung und Geschossfläche verteilt.
3. **Pendlerbeziehungen** aus der BA-Matrix als Randverteilung, darin ein
   Gravitationsmodell auf die Punkte. Gerundet nach Hare-Niemeyer, damit die
   amtlichen Summen exakt erhalten bleiben.
4. **Fahrzeiten** von einem lokalen OSRM-Server, ersatzweise geschätzt.
5. **Sonderziele** (Flughafen, FAU, TH, Kliniken, Stadion, Messe, Tiergarten,
   Innenstädte) aus `region.json` über `add_special_demand.py` — das nutzt
   `depot`, damit Typ-Taxonomie und Schemadateien stimmen.

Fehlen amtliche Zahlen, läuft alles trotzdem durch: dann Gravitationsmodell
über das Gesamtgebiet und geschätzte Arbeitsplätze — schlechtere
Datenqualität, aber ein spielbares Ergebnis.

```bash
python3 tests/test_pipeline.py     # 42 Tests, laufen ohne echte Daten
```

Getestet werden unter anderem die Projektion gegen Haversine-Distanzen, alle
CSV-Formatvarianten des Zensus, die exakte Erhaltung der amtlichen Summen und
ein kompletter Durchlauf auf synthetischen Daten für die Region — inklusive
Mock-OSRM-Server.

Details und Stellschrauben: [`build/demand/README.md`](build/demand/README.md)

### 4. Im Spiel testen

```bash
cd build/NUE
python3 -m http.server 8080
```

Dann diesen Ordner als Mod verlinken (`../install.sh` im Repo-Wurzelverzeichnis)
und im Spiel unter *Einstellungen → Mods* aktivieren. Die Stadt taucht im
Städte-Auswahlmenü im Reiter **Modded** auf.

Passt der Port oder Pfad nicht, `BASE_URL` oben in [`index.js`](index.js)
anpassen.

### 5. Optional veröffentlichen

Über den [Railyard](https://github.com/Subway-Builder-Modded/The-Railyard):
`build/config.json` ausfüllen, Karte irgendwo hosten (GitHub Releases),
dann im Registry-Repo per Issue-Template einreichen. Die CI prüft das
Manifest und öffnet automatisch einen PR.

## Dateien in diesem Ordner

```
karte-nuernberg-fuerth-erlangen/
├── manifest.json               Mod-Metadaten
├── index.js                    registerCity + Kachel-/Datei-URLs
├── README.md                   diese Datei
├── ANLEITUNG.md                Schritt für Schritt: was noch zu tun ist
└── build/
    ├── mapgen_nue.py           erzeugt die Basiskarte mit depot
    ├── config.json             Vorlage für den Railyard-Import
    ├── DATENQUELLEN.md         Datenprüfung mit Quellen und Lizenzen
    └── demand/                 Nachfrage-Pipeline (Standardbibliothek)
        ├── build_demand.py     Hauptskript
        ├── verify_pois.py      Sonderziele prüfen
        ├── add_special_demand.py
        ├── region.json         Ausschnitt, Gemeinden, 13 Sonderziele
        ├── nuedemand/          Module
        └── tests/              42 Tests
```

Die erzeugten Kartendaten (mehrere hundert MB) gehören **nicht** ins Repo.
