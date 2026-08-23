# Nachfragedaten für die Karte Nürnberg / Fürth / Erlangen

Erzeugt die `demand_data.json`, die Subway Builder für eine eigene Karte
braucht: wer wohnt wo, wer arbeitet wo, und wer pendelt zwischen welchen
Punkten — inklusive Fahrzeit und Fahrstrecke mit dem Auto als Referenz.

**Läuft mit der Python-Standardbibliothek.** Kein numpy, pandas, geopandas
oder pyproj. Python 3.9 oder neuer genügt.

```bash
python3 tests/test_pipeline.py     # 42 Tests, laufen ohne echte Daten
```

## Warum eigener Code und nicht `depot`?

[`depot`](https://github.com/Subway-Builder-Modded/depot) ist das Werkzeug der
Community und übernimmt hier die **Basiskarte** (`../mapgen_nue.py`) und die
**Sonderziele** (`add_special_demand.py`). Für die Grundnachfrage hilft es
nicht weiter: es bearbeitet eine vorhandene `demand_data.json`, erzeugt sie
aber nicht — die mitgelieferten Beispiele beruhen auf US-LODES-Daten, die es
für Deutschland nicht gibt.

Deutschland hat dafür etwas Besseres: das **Zensus-2022-Gitter mit 100 m
Kantenlänge**, in dem jede Zelle ihre gemessene Einwohnerzahl trägt. In der
[Datenqualitäts-Rubrik des Railyard](https://github.com/Subway-Builder-Modded/The-Railyard/blob/main/docs/data-quality.md)
ist das die zweitbeste erreichbare Stufe — besser als alles, was ein
OSM-Generator liefern kann.

## Ablauf

```
Zensus-100m-Gitter ─┐
                    ├─► Punkte (400-m-Raster) ─┐
Gebäude + BA-Zahlen ┘                          ├─► demand_data.json
                                               │
BA-Pendlermatrix ──► Gravitationsmodell ───────┤
                                               │
OSRM (oder Schätzung) ──► Fahrzeiten ──────────┘
```

1. **Einwohner** — `zensus.py` liest das 100-m-Gitter. Die Koordinaten stecken
   in der INSPIRE-Gitter-ID (EPSG:3035); `laea.py` rechnet sie ohne pyproj
   nach WGS84 um.
2. **Arbeitsplätze** — `buildings.py` klassifiziert die Gebäude nach Nutzung
   und gewichtet sie nach Geschossfläche, `jobs.py` verteilt die amtliche
   Beschäftigtenzahl je Gemeinde auf diese Gewichte (Dasymetrie).
3. **Aggregation** — `commute.py` legt beides auf ein gemeinsames Raster
   (Standard 400 m). Jede belegte Zelle wird ein Nachfragepunkt.
4. **Pendler** — die amtliche Matrix Gemeinde → Gemeinde ist die Randsumme;
   innerhalb eines Gemeindepaars verteilt ein Gravitationsmodell
   (`exp(-d/6 km)`, beste 15 Ziele je Wohnpunkt). Gerundet wird nach
   Hare-Niemeyer, damit die amtlichen Summen exakt erhalten bleiben.
5. **Fahrzeiten** — `routing.py` fragt einen lokalen OSRM-Server oder schätzt
   aus Luftlinie × 1,25 mit entfernungsabhängiger Geschwindigkeit.

Fehlt die Pendlermatrix oder die Beschäftigtenstatistik, läuft alles trotzdem
durch — dann eben mit Gravitationsmodell über das Gesamtgebiet und geschätzten
Arbeitsplätzen. Die Datenqualität fällt entsprechend.

## Aufruf

```bash
python3 build_demand.py \
    --zensus    daten/Zensus2022_Bevoelkerungszahl_100m-Gitter.csv \
    --buildings ../NUE/buildings.geojson \
    --gemeinden daten/gemeinden.geojson \
    --jobs      daten/beschaeftigte_arbeitsort.csv \
    --pendler   daten/pendler.csv \
    --osrm      http://127.0.0.1:5000 \
    --out       ../NUE/demand_data.json \
    --stats-out ../NUE/demand_stats.json \
    --gzip
```

Welche Gemeinden im Ausschnitt liegen (für den Zuschnitt der BA-Dateien):

```bash
python3 build_demand.py --gemeinden daten/gemeinden.geojson --list-gemeinden \
    --zensus x --buildings x
```

### Stellschrauben

| Option | Standard | Wirkung |
| --- | --- | --- |
| `--cell-size` | 400 | Rasterweite der Punkte in m. Kleiner = mehr Punkte, größere Datei, feineres Spiel |
| `--top-k` | 15 | Ziele je Wohnpunkt. Höher = mehr Beziehungen, realistischere Streuung |
| `--decay-km` | 6.0 | Abstandsempfindlichkeit. Kleiner = mehr Nahverkehr im Quartier |
| `--employment-rate` | 0.52 | Anteil Erwerbstätiger an den Einwohnern |
| `--max-pop-size` | 200 | Größte Personengruppe je Beziehung |
| `--non-sv-factor` | 1.22 | Aufschlag auf die SV-Beschäftigten für Selbstständige und Beamte |

Zum Vergleich die Werte der bestehenden Berlin-Karte im Railyard: 921 Punkte,
39 805 Gruppen, mittlerer Arbeitsweg 14,9 km. Erreicht die eigene Karte
ähnliche Größenordnungen, passt es.

## Sonderziele

```bash
python3 verify_pois.py --region region.json --buildings ../NUE/buildings.geojson
python3 add_special_demand.py --demand ../NUE/demand_data.json --outdir ../NUE
```

`region.json` enthält Flughafen, FAU (drei Standorte), TH Nürnberg, die beiden
großen Kliniken, Stadion, Messe, Tiergarten, Playmobil-FunPark sowie die
Innenstädte von Nürnberg und Fürth. **Die Koordinaten sind von Hand
eingetragen und nicht gegen OSM geprüft** — `verify_pois.py` schreibt eine
GeoJSON-Datei, die sich auf geojson.io oder in QGIS über die echte Karte legen
lässt. Bitte einmal durchsehen.

`add_special_demand.py` braucht `depot`; alles andere hier nicht.

## Dateien

```
demand/
├── build_demand.py         Hauptskript
├── verify_pois.py          Sonderziele prüfen, GeoJSON zum Gegenlesen
├── add_special_demand.py   Sonderziele anhängen (braucht depot)
├── region.json             Kartenausschnitt, Gemeinden, Sonderziele
├── nuedemand/
│   ├── laea.py             EPSG:3035 <-> WGS84 ohne pyproj
│   ├── geo.py              Distanzen, Flächen, Punkt-in-Polygon
│   ├── zensus.py           Zensus-100m-Gitter lesen
│   ├── buildings.py        Gebäude klassifizieren und gewichten
│   ├── jobs.py             Beschäftigte je Gemeinde verteilen
│   ├── pendler.py          Pendlermatrix lesen
│   ├── commute.py          Aggregation, Gravitationsmodell, Ausgabeformat
│   └── routing.py          Fahrzeiten (OSRM oder Schätzung)
└── tests/
    ├── make_fixtures.py    synthetische Testdaten für die Region
    └── test_pipeline.py    42 Tests, davon ein kompletter Durchlauf
```

## Format der Ausgabe

```jsonc
{
  "points": [
    { "id": "p0", "location": [11.0823, 49.4455],
      "jobs": 1200, "residents": 340, "popIds": ["0", "1", "17"] }
  ],
  "pops": [
    { "id": "0", "size": 42, "residenceId": "p0", "jobId": "p88",
      "drivingSeconds": 612, "drivingDistance": 7431 }
  ]
}
```

Getestet wird unter anderem, dass jede `residenceId`/`jobId` auf einen
existierenden Punkt zeigt, dass die `popIds` beidseitig zurückverweisen und
dass die Summe aller Gruppengrößen exakt der amtlichen Pendlersumme
entspricht.
