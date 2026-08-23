# Karte Nürnberg / Fürth / Erlangen — was noch zu tun ist

Der Code ist fertig und getestet. Was fehlt, sind die echten Daten: die
Cloud-Session, in der dieses Projekt entstanden ist, kommt weder an die
Geofabrik noch an Overture oder die Statistikportale — der Netzwerk-Proxy
sperrt alles außer GitHub und den Paketquellen. Alles Folgende musst du
deshalb auf deinem eigenen Rechner machen.

**Aufwand:** ein halber Tag Handarbeit, dazu mehrere Stunden Rechenzeit, die
nebenher laufen können.

---

## Übersicht

| # | Schritt | Dauer | Womit |
| --- | --- | --- | --- |
| 1 | Werkzeuge installieren | 1 h | Paketmanager, conda |
| 2 | Daten herunterladen | 30 min | Browser, 5 Downloads |
| 3 | Daten aufbereiten | 1 h | Tabellenkalkulation, osmium |
| 4 | Basiskarte bauen | 2–5 h Rechenzeit | `build/mapgen_nue.py` |
| 5 | Grundnachfrage bauen | 5 min | `build/demand/build_demand.py` |
| 6 | Sonderziele ergänzen | 30 min | `build/demand/add_special_demand.py` |
| 7 | Im Spiel testen | 30 min | `install.sh`, lokaler Webserver |
| 8 | Veröffentlichen (optional) | 1 h | Railyard |

---

## 1. Werkzeuge installieren

Unter Windows: **alles in WSL**, `depot` unterstützt nichts anderes.

```bash
# Debian/Ubuntu bzw. WSL
sudo apt update
sudo apt install -y osmium-tool sqlite3 jq default-jre nodejs npm python3-pip unzip
sudo npm install -g mapshaper
```

Dazu noch, weil sie nicht in den Paketquellen liegen:

- **tippecanoe** und **tile-join** — https://github.com/felt/tippecanoe (selbst bauen: `make && sudo make install`)
- **pmtiles** — https://github.com/protomaps/go-pmtiles/releases (Binary, ausführbar machen und in den `PATH`)
- **planetiler.jar** — https://github.com/onthegomap/planetiler/releases (jar herunterladen, Pfad merken)
- **Docker** — nur für OSRM in Schritt 5 nötig

Wichtig: Alle bis auf `planetiler.jar` müssen **ausführbar im PATH** liegen,
sonst hält `depot` sie für nicht vorhanden und bricht ab.

Dann `depot`:

```bash
git clone https://github.com/Subway-Builder-Modded/depot.git
cd depot
conda env create -f environment.yml    # conda: https://conda-forge.org/miniforge
conda activate depot
pip install .
```

**Prüfen:**

```bash
for t in node mapshaper osmium java tippecanoe tile-join sqlite3 jq pmtiles; do
  command -v $t >/dev/null && echo "OK   $t" || echo "FEHLT $t"
done
python3 -c "import depot; print('depot OK')"
```

---

## 2. Daten herunterladen

Lege dir einen Ordner `daten/` an und sammle dort alles.

### 2.1 OpenStreetMap — Mittelfranken

```bash
wget https://download.geofabrik.de/europe/germany/bayern/mittelfranken-latest.osm.pbf
```

Rund 100 MB. Enthält Nürnberg, Fürth, Erlangen und Schwabach vollständig.
(Das Skript in Schritt 4 lädt die Datei sonst selbst.)

### 2.2 Zensus 2022 — Bevölkerung im 100-m-Gitter

Die wichtigste Datei des ganzen Projekts.

1. https://www.zensus2022.de → **Ergebnisse des Zensus** → **Downloads**
2. Suche nach der gitterzellenbasierten Auswertung, 100-Meter-Gitter,
   Merkmal **Bevölkerungszahl** (ZIP, mehrere hundert MB für ganz
   Deutschland)
3. Entpacken. Die CSV hat entweder die Spalten `GITTER_ID_100m;werte` oder
   zusätzlich `x_mp_100m;y_mp_100m` — beide Varianten liest das Skript.

Ganz Deutschland ist unnötig groß. Vorher zuschneiden geht so (die
Gitter-ID enthält die EPSG:3035-Koordinaten, unser Ausschnitt liegt etwa bei
E 4 375 000 – 4 407 000 und N 2 906 000 – 2 950 000):

```bash
head -1 Zensus2022_Bevoelkerungszahl_100m-Gitter.csv > daten/zensus_nue.csv
grep -E "N29[0-4][0-9]{5}E4[34][0-9]{5}" Zensus2022_Bevoelkerungszahl_100m-Gitter.csv >> daten/zensus_nue.csv
```

Das ist ein grober Vorfilter — `build_demand.py` schneidet danach exakt auf
die Bounding Box zu. Zu viel drin zu haben schadet nicht, zu wenig schon.

### 2.3 Beschäftigte am Arbeitsort je Gemeinde

1. https://statistik.arbeitsagentur.de → **Statistiken nach Themen** →
   **Beschäftigung** → **Beschäftigte nach Wohn- und Arbeitsort**
2. Gemeindedaten für Bayern, aktuellster Stichtag, als Excel herunterladen
3. Interessant ist die Spalte **sozialversicherungspflichtig Beschäftigte am
   Arbeitsort**

### 2.4 Pendlerverflechtungen

1. Ebenda → **Pendlerverflechtungen der sozialversicherungspflichtig
   Beschäftigten** (oder der interaktive
   [Pendleratlas](https://statistik.arbeitsagentur.de/DE/Navigation/Statistiken/Interaktive-Statistiken/Pendleratlas/Pendleratlas-Nav.html))
2. Gemeindeebene, Bayern bzw. Mittelfranken
3. Gebraucht wird: Wohnortgemeinde, Arbeitsortgemeinde, Anzahl

### 2.5 Gemeindegrenzen

Zwei Wege — der erste ist sauberer:

**BKG (empfohlen):** https://gdz.bkg.bund.de → **Verwaltungsgebiete** →
VG250 als GeoJSON oder Shapefile, Ebene `VG250_GEM`. Enthält die Felder
`AGS` und `GEN`, Lizenz dl-de/by-2-0. Shapefile umwandeln:

```bash
mapshaper VG250_GEM.shp -filter '/^09(56|57)/.test(AGS)' -o format=geojson daten/gemeinden.geojson
```

**Aus OSM (ohne weiteren Download):**

```bash
osmium tags-filter mittelfranken-latest.osm.pbf \
    r/boundary=administrative -o boundaries.osm.pbf
osmium export boundaries.osm.pbf -f geojson \
    --geometry-types=polygon -o daten/gemeinden_osm.geojson
```

Der Gemeindeschlüssel heißt dort `de:amtlicher_gemeindeschluessel`, der Name
`name` — beides erkennt `build_demand.py` selbst. Nachteil: alle
Verwaltungsebenen sind enthalten, du musst auf `admin_level=8` filtern.

---

## 3. Daten aufbereiten

Aus den beiden Excel-Dateien der Arbeitsagentur müssen zwei schlanke CSVs
werden. Öffne sie in LibreOffice/Excel und speichere sie in genau diesem
Format als CSV mit Semikolon:

**`daten/beschaeftigte_arbeitsort.csv`**

```
ags;name;beschaeftigte
09564000;Nürnberg;285000
09563000;Fürth;48000
09562000;Erlangen;75000
```

**`daten/pendler.csv`**

```
von_ags;nach_ags;anzahl
09564000;09564000;180000
09563000;09564000;22000
```

Die Spaltennamen dürfen abweichen — die Skripte erkennen auch `Wohnort`,
`Arbeitsort`, `Pendler`, `Gemeindeschlüssel` und ähnliche. Deutsche
Tausenderpunkte, Anführungszeichen und gesperrte Werte (`x`, `-`, `*`) werden
korrekt behandelt.

**Welche Gemeinden brauchst du?** Genau die im Kartenausschnitt. Frag sie ab:

```bash
cd karte-nuernberg-fuerth-erlangen/build/demand
python3 build_demand.py --gemeinden ../../daten/gemeinden.geojson \
    --list-gemeinden --zensus x --buildings x
```

Sicher dabei sind die vier kreisfreien Städte:

| AGS | Gemeinde |
| --- | --- |
| 09564000 | Nürnberg |
| 09563000 | Fürth |
| 09562000 | Erlangen |
| 09565000 | Schwabach |

Dazu kommen Umlandgemeinden aus den Landkreisen Fürth (09573),
Erlangen-Höchstadt (09572), Nürnberger Land (09574) und Roth (09576) —
Stein, Zirndorf, Oberasbach, Herzogenaurach, Lauf, Röthenbach, Feucht und
weitere. Deren Schlüssel liest du aus der Ausgabe oben ab, statt sie zu raten.

---

## 4. Basiskarte bauen

```bash
cd karte-nuernberg-fuerth-erlangen/build
conda activate depot
python3 mapgen_nue.py
```

Läuft mehrere Stunden und braucht etwa 16 GB RAM sowie 20 GB Plattenplatz.
Ergebnis in `build/NUE/`:

- `NUE.pmtiles`, `NUE_foundations.pmtiles`
- `buildings_index.json` **und** `buildings_index.bin` — depot schreibt beide
  Formate. Die offizielle Doku zeigt die gzip-JSON-Variante, die Berlin-Karte
  im Railyard liefert die kleinere Binärdatei aus. Lädt das Spiel die eine
  nicht, in `index.js` die Konstante `BUILDINGS_INDEX` umstellen.
- `roads.geojson`
- `runways_taxiways.geojson`
- `buildings.geojson` (Zwischenergebnis — wird in Schritt 5 gebraucht!)

**Wenn `mapshaper` mit einem Heap-Fehler abbricht:** im Skript `RAM=8` auf
`RAM=12` oder höher setzen.

**Labels prüfen:** Das Skript ruft `check_labels()` auf und zeigt, welche
`place`-Tags in der Region vorkommen. Passen die Listen `cities`, `suburbs`
und `neighborhoods` nicht, im Skript ändern und nur `add_labels()` erneut
laufen lassen — nicht alles neu bauen.

---

## 5. Grundnachfrage bauen

Optional, aber deutlich besser: **OSRM für echte Fahrzeiten**. Einmalig
vorbereiten (dauert ca. 20 Minuten):

```bash
cd daten
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend \
    osrm-extract -p /opt/car.lua /data/mittelfranken-latest.osm.pbf
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend \
    osrm-partition /data/mittelfranken-latest.osrm
docker run -t -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend \
    osrm-customize /data/mittelfranken-latest.osrm
docker run -d -p 5000:5000 -v "${PWD}:/data" ghcr.io/project-osrm/osrm-backend \
    osrm-routed --algorithm mld /data/mittelfranken-latest.osrm
```

Dann die Nachfrage bauen — das dauert nur Minuten:

```bash
cd karte-nuernberg-fuerth-erlangen/build/demand
python3 build_demand.py \
    --zensus    ../../../daten/zensus_nue.csv \
    --buildings ../NUE/buildings.geojson \
    --gemeinden ../../../daten/gemeinden.geojson \
    --jobs      ../../../daten/beschaeftigte_arbeitsort.csv \
    --pendler   ../../../daten/pendler.csv \
    --osrm      http://127.0.0.1:5000 \
    --out       ../NUE/demand_data.json \
    --stats-out ../NUE/demand_stats.json
```

Ohne `--jobs`/`--pendler`/`--osrm` läuft es auch, nur mit schlechteren Daten.

**Ergebnis gegenlesen.** Am Ende stehen Kennzahlen; die Berlin-Karte im
Railyard als Maßstab:

| Kennzahl | Berlin (Railyard) | Erwartung für NUE |
| --- | --- | --- |
| Punkte | 921 | 1 000 – 2 000 |
| Gruppen (pops) | 39 805 | 30 000 – 80 000 |
| Einwohner | 3,9 Mio | ca. 880 000 |
| mittlerer Arbeitsweg | 14,9 km | 8 – 13 km |

Weicht etwas stark ab, hilft `--cell-size` (Punktzahl) oder `--top-k`
(Beziehungen) — die Stellschrauben stehen in `demand/README.md`.

---

## 6. Sonderziele ergänzen

Erst prüfen — die Koordinaten in `region.json` habe ich nach bestem Wissen
eingetragen, aber **nicht** gegen OSM verifiziert:

```bash
python3 verify_pois.py --region region.json --buildings ../NUE/buildings.geojson
```

Das Skript meldet Punkte ohne Bebauung ringsum und schreibt `pois.geojson`.
Zieh die Datei auf https://geojson.io oder öffne sie in QGIS über der echten
Karte und schau alle 13 Punkte durch. Was danebenliegt, in `region.json`
korrigieren.

Auch die **Kapazitäten** sind Schätzungen (Quellen stehen bei jedem Eintrag im
Feld `quelle`). Wenn du bessere Zahlen hast — Messebesucher pro Jahr,
Beschäftigte der Kliniken — trag sie ein.

Dann anhängen:

```bash
conda activate depot
python3 add_special_demand.py --demand ../NUE/demand_data.json --outdir ../NUE
```

Erzeugt zusätzlich `special_demand_types.json`, `special_demand_points.json`
und `config.json`.

**Noch offen:** Ein- und Auspendler über den Kartenrand (Ansbach, Bamberg,
Forchheim, Neumarkt, Hersbruck). `build_demand.py` nennt die Zahlen beim
Einlesen der Pendlermatrix. Sie gehören als Sonderziele vom Typ
`outside_connection` an die Ränder der Karte — dort, wo A3, A6, A9 und die
Bahnstrecken den Ausschnitt verlassen. Ergänze sie in `region.json`, sobald
du die Zahlen hast.

---

## 7. Im Spiel testen

```bash
cd karte-nuernberg-fuerth-erlangen/build/NUE
gzip -k buildings_index.json demand_data.json roads.geojson runways_taxiways.geojson
python3 -m http.server 8080
```

In einem zweiten Terminal den Mod verlinken und das Spiel starten:

```bash
cd /pfad/zu/subwaybuilder_mods
./install.sh
```

Im Spiel: **Einstellungen → Mods** aktivieren, dann im Städtemenü den Reiter
**Modded** öffnen — dort steht Nürnberg.

Passt der Port nicht, `BASE_URL` oben in `index.js` ändern.

**Wenn nichts erscheint:** Konsole des Spiels öffnen und nach `[Karte NUE]`
suchen. Fehlt die Zeile, wird der Mod nicht geladen; steht dort ein
404-Fehler, stimmen die Dateinamen unter `BASE_URL` nicht.

---

## 8. Veröffentlichen (optional)

Über den [Railyard](https://github.com/Subway-Builder-Modded/The-Railyard):

1. `config.json` prüfen (aus Schritt 6), `population` auf die tatsächliche
   Summe aus `demand_stats.json` setzen
2. Kartendaten irgendwo hosten — GitHub Releases reicht
3. Im Registry-Repo per Issue-Template einreichen; die CI prüft und öffnet
   automatisch einen PR
4. Für die Datenqualitätsangabe: Zensus-2022-Gitter für die Einwohner
   (Mesh ≤ 125 m, direkt gemessen), BA-Gemeindedaten für die Arbeitsplätze
   (ADM3 mit Gebäude-Dasymetrie), BA-Pendlermatrix für die O/D-Beziehungen
   (ADM3-Randverteilungen). Das ist deutlich mehr als die bestehende
   Berlin-Karte vorweisen kann, die rein aus OSM generiert wurde.

**Lizenzhinweise nicht vergessen:** „© OpenStreetMap-Mitwirkende" (ODbL) und
„Datenlizenz Deutschland – Namensnennung 2.0" für Zensus und BA-Statistiken.

---

## Wenn etwas klemmt

| Symptom | Ursache | Abhilfe |
| --- | --- | --- |
| `depot` bricht mit „missing requirement" ab | ein CLI-Werkzeug fehlt oder ist nicht ausführbar | Prüfschleife aus Schritt 1 laufen lassen |
| mapshaper: „heap out of memory" | zu wenig RAM zugeteilt | `RAM=` in `mapgen_nue.py` erhöhen |
| „keine Zensuszellen im Ausschnitt" | falscher Vorfilter oder falsche Datei | ohne `grep`-Vorfilter erneut versuchen |
| „keine Gebäude für AGS …" | Gemeinde liegt außerhalb des Ausschnitts | ist normal, betrifft nur Randgemeinden |
| viele „Punkte ohne Pendlerbeziehung" | `--top-k` zu klein oder Gemeindegrenzen passen nicht | `--top-k 25` probieren |
| Stadt fehlt im Spiel | Mod nicht geladen oder Server nicht erreichbar | Spielkonsole auf `[Karte NUE]` prüfen |
| Karte lädt, Gebäude fehlen | falsches Format des Gebäude-Index | `BUILDINGS_INDEX` in `index.js` auf `buildings_index.bin` umstellen |
