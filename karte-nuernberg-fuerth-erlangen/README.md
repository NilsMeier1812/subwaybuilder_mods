# Karte Nürnberg / Fürth / Erlangen — Subway Builder

Eigene Karte für [Subway Builder](https://www.subwaybuilder.com): die
Metropolregion Nürnberg – Fürth – Erlangen unter dem Stadtcode **NUE**.

> **Stand:** Gerüst fertig, Kartendaten noch nicht gebaut. Die Datenprüfung
> ist abgeschlossen — alles, was das Spiel verlangt, ist für die Region
> verfügbar (Details in [`build/DATENQUELLEN.md`](build/DATENQUELLEN.md)).
> Der eigentliche Bau muss auf einem Rechner mit Internetzugang zu Geofabrik
> und Overture laufen; in der Cloud-Session, in der dieses Gerüst entstanden
> ist, sind diese Hosts gesperrt.

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

Dieser Schritt ist noch offen und der eigentliche Aufwand. `depot` kann eine
vorhandene `demand_data.json` bearbeiten (zusammenfassen, skalieren, routen),
erzeugt sie aber nicht aus deutschen Statistiken — die mitgelieferten Beispiele
beruhen auf US-LODES-Daten.

Der Weg für Nürnberg:

1. **Wohnpunkte** aus dem Zensus-2022-100-m-Gitter — jede Zelle im BBox wird
   zu einem Punkt mit `residents`.
2. **Arbeitspunkte** aus den SV-Beschäftigten am Arbeitsort je Gemeinde,
   innerhalb der Gemeinde auf Gebäude mit passender Nutzung verteilt
   (`building=office/retail/industrial/commercial`, gewichtet nach Grundfläche).
3. **Pendlerbeziehungen** aus dem BA-Pendleratlas als Randverteilung
   Gemeinde → Gemeinde; innerhalb dieser Summen ein Gravitationsmodell auf die
   Punkte.
4. **Fahrzeiten** mit einem lokalen OSRM-Server auf demselben `.osm.pbf`:
   `DemandData.prepare_osrm()` + `calculate_routes()`.
5. **Sonderziele** (Flughafen, FAU, TH, Messe, Stadion, Tiergarten) über die
   Special-Demand-Konfiguration ergänzen — Kennzahlen in
   [`build/DATENQUELLEN.md`](build/DATENQUELLEN.md).
6. Aufräumen: `consolidate_pops()`, `merge_identical_commutes()`,
   `enforce_max_pop_size()`, dann `save()` als `demand_data.json`.

Als Zwischenlösung geht auch der rein OSM-basierte Generator des
[Map-Patchers](https://github.com/stepanskur/Subway-Builder-map-patcher) —
so ist die Berlin-Karte entstanden. Die Datenqualität ist dann allerdings nur
`low`, weil kein Zensus-Anker dahintersteht. Mit dem Zensus-Gitter landet
Nürnberg in der Rubrik deutlich höher.

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
├── manifest.json           Mod-Metadaten
├── index.js                registerCity + Kachel-/Datei-URLs
├── README.md               diese Datei
└── build/
    ├── mapgen_nue.py       erzeugt die Basiskarte mit depot
    ├── config.json         Vorlage für den Railyard-Import
    └── DATENQUELLEN.md     Datenprüfung mit Quellen und Lizenzen
```

Die erzeugten Kartendaten (mehrere hundert MB) gehören **nicht** ins Repo.
