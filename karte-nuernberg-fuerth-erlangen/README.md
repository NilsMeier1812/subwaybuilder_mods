# Karte Nürnberg – Erlangen – Fürth (`NEF`)

Eigene Karte für [Subway Builder](https://www.subwaybuilder.com): die
Städteachse Nürnberg – Fürth – Erlangen samt Umland, gebaut aus amtlichen
Daten (Zensus 2022, Pendlerrechnung 2024) und OpenStreetMap/Overture.

**Fertige Karte:** [`dist/NEF-1.0.1.zip`](dist/NEF-1.0.1.zip) (74 MB)

## Installieren

1. [Railyard](https://subwaybuildermodded.com) (Map-/Mod-Manager der
   Community) installieren und starten.
2. ZIP herunterladen (auf GitHub die Datei öffnen → „Download raw file“),
   dann in Railyard unter **Library → Import Assets** die Datei
   `NEF-1.0.1.zip` als Karte (Map) importieren.
3. Spiel über Railyard starten. Die Karte steht in der Städteauswahl unter
   dem Reiter **DE** als „Nürnberg – Erlangen – Fürth“.

Der Code `NEF` kollidiert nicht mit der Community-Karte `NUE` (pierreggt);
beide können gleichzeitig installiert sein.

## Was drin ist

| | |
| --- | --- |
| Ausschnitt | 10,80–11,32 °O / 49,28–49,66 °N, rund 38 × 42 km |
| Enthalten | Nürnberg, Fürth, Erlangen, Schwabach komplett; Zirndorf, Oberasbach, Stein, Herzogenaurach, Lauf, Röthenbach, Schwaig, Feucht, Wendelstein, Eckental, Heroldsberg, Cadolzburg, Roßtal u. a. — 60 Gemeinden |
| Nachfragepunkte | 4 880 (300-m-Raster je Gemeinde, Lage = Schwerpunkt von Wohnungen und Arbeitsplätzen) |
| Pendlergruppen | 49 042, Ø 12,7 Personen |
| Personen gesamt | 623 460 — davon 537 960 Berufspendler, 85 500 Sonderziel-Fahrten |
| Ø Arbeitsweg | 8,9 km Straße / 6,9 km Luftlinie, 15 min mit dem Auto |
| Gebäude | 309 000 im Kollisionsindex, 380 000 in der Karte |
| Sonderziele | Flughafen, FAU (3 Standorte), TH Nürnberg, 4 Kliniken, Stadion, Messe, Tiergarten, Playmobil-FunPark, 3 Innenstädte, 2 Einkaufszentren |

Alle Kennzahlen je Gemeinde: [`dist/NEF-1.0.1-kennzahlen.json`](dist/NEF-1.0.1-kennzahlen.json).

Im Modell stehen nur Fahrten, deren Wohn- **und** Arbeitsort auf der Karte
liegen (geschlossenes System, wie bei allen Subway-Builder-Karten). Wer aus
Bamberg nach Erlangen pendelt, fehlt also — deshalb hat Erlangen im Modell
79 000 statt 114 000 Arbeitsplätze.

## Wie die Nachfrage entsteht

| Baustein | Quelle | Verfahren |
| --- | --- | --- |
| Erwerbstätige am Wohn- und Arbeitsort je Gemeinde | [Pendlerrechnung der Statistischen Ämter](https://pendleratlas.statistikportal.de), Stichtag 30.6.2024 — alle Erwerbstätigen inkl. Beamte und Selbstständige | direkt übernommen |
| Pendlerströme Gemeinde → Gemeinde | dieselbe Quelle: Innerortspendler und die zehn stärksten Aus-/Einpendlerbeziehungen je Gemeinde | fest übernommen; Rest per doppelt beschränktem Gravitationsmodell (IPF) über alle 2 056 bayerischen Gemeinden, so dass jede Gemeinde ihre amtlichen Summen exakt behält |
| Wohnorte innerhalb der Gemeinde | [Zensus 2022, 100-m-Gitter](https://www.zensus2022.de) — 18- bis 64-Jährige je Zelle | Erwerbstätige der Gemeinde proportional verteilt |
| Arbeitsorte innerhalb der Gemeinde | [Overture](https://overturemaps.org) Gebäude (Grundfläche, Geschosse, Nutzungsklasse), OSM-Flächennutzung, 64 000 Overture-POIs | Geschossfläche × Beschäftigtendichte je Gebäudetyp + Beschäftigte je Betrieb |
| Punkt → Punkt | — | dreifach beschränktes IPF: Wohnpunkte, Arbeitspunkte und Gemeindepaare, Distanzabfall exp(−d / 6 km) |
| Fahrzeiten | OSM-Straßennetz | eigener Router (Dijkstra), Geschwindigkeit aus `maxspeed` bzw. Straßenklasse, Einbahnstraßen, +2 min Parken |
| Sonderziele | eigene Schätzung (Quellen in [`build/specials.json`](build/specials.json)) | Gruppen von Wohnpunkten mit Distanzabfall je Zieltyp |

Einordnung nach der [Datenqualitäts-Rubrik des Railyard](https://github.com/Subway-Builder-Modded/The-Railyard/blob/main/docs/data-quality.md)
(zum Vergleich die bestehende `NUE`-Karte, Stufe „low“):

| Faktor | NEF | NUE (pierreggt) |
| --- | --- | --- |
| Arbeitsplätze: Zählung | Erwerbstätige am Arbeitsort, alle Gemeinden (ADM3) | dto., nur Kerngemeinden |
| Arbeitsplätze: Verteilung | Gebäudetypen mit generischen Dichten + POIs | binär (Gewerbe/Wohnen) |
| Wohnorte: Zählung | Erwerbstätige je Gemeinde (Employed Residents, ADM3) | Gesamtbevölkerung |
| Wohnorte: Verteilung | 100-m-Gitter, gemessen (18–64-Jährige) | Gitter, auf Gebäude umgelegt |
| Pendlerströme | amtliche Innerorts- und Top-10-Ströme aller Gemeinden + IPF (Structured Marginals) | nur Kernströme |

## Neu bauen

Alles läuft auf einem Linux-Rechner bzw. unter WSL, ohne Docker und ohne
fremde Kartenbibliothek — die Skripte in [`build/`](build/) sind
vollständig eigenständig.

```bash
cd karte-nuernberg-fuerth-erlangen/build
./00_tools.sh                  # einmalig: osmium, tippecanoe, pmtiles, planetiler, Python-Umgebung
source ./env.sh
./build_all.sh                 # ~15 min Rechenzeit + Downloads (~700 MB)
```

| Schritt | Skript | Ergebnis |
| --- | --- | --- |
| 1 | `01_download.py` | OSM (BBBike-Extrakte + OSM-API-Flicken), Overture-Gebäude und -POIs, Zensus-Gitter, Pendlerrechnung, Gemeindegrenzen (BKG VG250) |
| 2 | `02_basemap.py` | `NEF.pmtiles`, `NEF_foundations.pmtiles`, `buildings_index.bin.gz`, `roads.geojson.gz`, `runways_taxiways.geojson.gz` |
| 3 | `03_demand.py` | `demand_data.json.gz`, `demand_stats.json` — mit denselben Prüfungen wie die Integritätsprüfung des Registers |
| 4 | `04_package.py` | `config.json` und `dist/NEF-<version>.zip` |

Stellschrauben stehen oben in den Skripten (`GRID_M`, `DECAY_KM`,
`POP_TARGET` in `03_demand.py`; Ausschnitt, Name, Version in
[`build/region.json`](build/region.json); Sonderziele in
[`build/specials.json`](build/specials.json)). Zwischenstände landen in
`build/work/` (nicht im Repo).

### Module

```
build/nef/
├── common.py            Pfade, Konfiguration, Helfer
├── tiles.py             planetiler-Kacheln -> Layer des Spiels (water, landuse, commercial, …)
├── buildings_index.py   Gebäude-Index im Binärformat des Spiels (+ Lesefunktion zur Kontrolle)
├── zones.py             Gemeinden, Erwerbstätige, Zuordnung von Punkten
├── od.py                Gemeinde-Pendlermatrix (amtliche Ströme + IPF)
├── residents.py         Zensus-Gitter, 18- bis 64-Jährige
├── jobs.py              Arbeitsplatzgewichte je Gebäude
└── routing.py           Straßengraph und Fahrzeiten
```

## Veröffentlichen (optional)

Über den [Railyard](https://github.com/Subway-Builder-Modded/The-Railyard):
ZIP als GitHub-Release hochladen, dann im Registry-Repo das Issue-Formular
„Publish a New Map“ ausfüllen. Die Angaben für die Datenqualität stehen in
der Tabelle oben.

## Lizenzen

* Kartendaten © OpenStreetMap-Mitwirkende (ODbL), Overture Maps Foundation (ODbL / CDLA)
* Zensus 2022 © Statistische Ämter des Bundes und der Länder, Pendlerrechnung
  © Statistische Ämter der Länder, VG250 © BKG — jeweils Datenlizenz
  Deutschland – Namensnennung 2.0
