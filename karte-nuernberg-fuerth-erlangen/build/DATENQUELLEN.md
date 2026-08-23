# Datenquellen für die Karte Nürnberg / Fürth / Erlangen

Prüfung, ob alle Daten vorhanden sind, die Subway Builder für eine eigene
Karte verlangt. Kurzfassung: **ja, alle** — und beim Wohnbevölkerungs-Anteil
ist Deutschland sogar eine der besten Datenlagen weltweit.

## 1. Basiskarte (Gebäude, Straßen, Wasser, Labels)

| Was | Quelle | Verfügbar? | Bemerkung |
| --- | --- | --- | --- |
| OSM-Rohdaten | [Geofabrik: Mittelfranken](https://download.geofabrik.de/europe/germany/bayern/mittelfranken-latest.osm.pbf) | ja, ca. 100 MB | enthält Nürnberg, Fürth, Erlangen, Schwabach komplett |
| Gebäudegrundrisse | [Overture Maps](https://overturemaps.org) (OSM ∪ Google ∪ Microsoft ∪ Esri) — holt `depot` selbst | ja | OSM-Gebäudeabdeckung in NBG/FÜ/ER ist sehr gut, Overture schließt Reste |
| Straßennetz | dieselbe OSM-Extraktion | ja | |
| Start-/Rollbahnen | OSM, Flughafen Nürnberg (EDDN) | ja | eine Bahn 10/28 |
| Gewässertiefen | GEBCO — **nicht nötig** | entfällt | Binnenland; `create_ocean_foundations=False` |
| Labels | OSM `place=*` | ja | `city` für NBG/FÜ/ER, `town` für Schwabach/Zirndorf/Lauf, `suburb`/`quarter` für Stadtteile |

## 2. Nachfragedaten (`demand_data.json`)

Das ist der aufwändige Teil. Das Spiel erwartet zwei Listen:

```jsonc
{
  "points": [
    { "id": "…", "location": [lon, lat], "jobs": 0, "residents": 0, "popIds": ["…"] }
  ],
  "pops": [
    { "id": "…", "size": 1, "residenceId": "…", "jobId": "…",
      "drivingSeconds": 120, "drivingDistance": 699 }
  ]
}
```

Also: Wohnorte, Arbeitsorte und wer von wo nach wo pendelt — plus Fahrzeit und
Fahrstrecke mit dem Auto je Beziehung.

| Baustein | Quelle | Verfügbar? | Güte nach [Registry-Rubrik](https://github.com/Subway-Builder-Modded/The-Railyard/blob/main/docs/data-quality.md) |
| --- | --- | --- | --- |
| **Einwohner** | [Zensus 2022 — Bevölkerungszahl im 100-m-Gitter](https://www.zensus2022.de/DE/Ergebnisse-des-Zensus/) (INSPIRE-Gitter) | ja, offen | Mesh ≤ 125 m, **direkt gemessen** → Auflösung 0.9 / Intensität 1.0. Bestmögliche Stufe außerhalb von Gebäuderegistern |
| **Arbeitsplätze** | [Bundesagentur für Arbeit: SV-pflichtig Beschäftigte am Arbeitsort](https://statistik.arbeitsagentur.de) je Gemeinde | ja, offen | ADM3 (Gemeinde). Feinere Verteilung über Gebäudenutzung (`building=office/retail/industrial`, Betriebsflächen) → Dasymetrie |
| **Pendlerbeziehungen (O/D)** | [BA-Pendleratlas / Pendlerverflechtungen](https://statistik.arbeitsagentur.de/DE/Navigation/Statistiken/Interaktive-Statistiken/Pendleratlas/Pendleratlas-Nav.html), Gemeinde → Gemeinde | ja, offen | ADM3-Randverteilungen — deckt genau die relevanten Ströme ab (Fürth→Nürnberg, Erlangen→Nürnberg, Herzogenaurach→Erlangen) |
| **Fahrzeiten/-strecken** | eigener OSRM-Server (Docker) auf demselben `.osm.pbf` | ja | `depot.demand.DemandData.prepare_osrm()` / `calculate_routes()` |

Ergänzend, falls feiner gewünscht:

* Zensus 2022 Gebäude- und Wohnungszählung (Wohnungen je 100-m-Zelle) — zur
  Plausibilisierung der Wohnpunkte.
* [Mobilität in Deutschland (MiD 2017)](https://www.mobilitaet-in-deutschland.de) —
  Wegezwecke und Modal Split für die Region.

## 3. Sonderziele (special demand)

Alles öffentlich belegbar:

| Ziel | Kennzahl | Quelle |
| --- | --- | --- |
| Flughafen Nürnberg (NUE) | ~4,4 Mio Passagiere/Jahr (2024) ≈ 12 000/Tag | ADV-Monatsstatistik |
| FAU Erlangen-Nürnberg | ~39 000 Studierende, Standorte Erlangen Süd/Innenstadt + Nürnberg | FAU Zahlen & Fakten |
| TH Nürnberg | ~13 000 Studierende, Campus Keßlerplatz | TH Nürnberg |
| NürnbergMesse | Messegelände Langwasser, mehrere Mio Besucher/Jahr | NürnbergMesse |
| Max-Morlock-Stadion | 50 000 Plätze | 1. FCN |
| Tiergarten Nürnberg | ~1,1 Mio Besucher/Jahr | Stadt Nürnberg |
| Altstadt / Christkindlesmarkt | saisonal, optional | Stadt Nürnberg |
| Siemens Healthineers Erlangen, Adidas/Puma Herzogenaurach | große Einzelarbeitgeber | Geschäftsberichte |

## 4. Lizenzen

* OSM und Overture: ODbL — Namensnennung „© OpenStreetMap-Mitwirkende“ nötig.
* Zensus 2022 und BA-Statistiken: Datenlizenz Deutschland – Namensnennung 2.0
  (dl-de/by-2-0), freie Weiterverwendung inkl. kommerziell.

Damit ist die Karte auch für eine Veröffentlichung im
[Railyard](https://github.com/Subway-Builder-Modded/The-Railyard) unproblematisch.
