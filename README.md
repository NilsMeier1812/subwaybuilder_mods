# Bahnübergang-Limit Override — Subway Builder Mod

Mod für [Subway Builder](https://www.subwaybuilder.com) mit zwei Funktionen:

1. **Limit überschreiben** — legt fest, wie viele Züge pro Stunde (tph) einen
   ebenerdigen Bahnübergang befahren dürfen, einstellbar je Straßenklasse.
2. **Straßenquerung freischalten** — erlaubt **Heavy Metro** und **Light Metro**,
   Straßen ebenerdig zu kreuzen. Im Vanilla-Spiel ist das verboten.

## Wie das im Spiel funktioniert

Jeder Zugtyp hat zwei relevante Eigenschaften:

```js
allowAtGradeRoadCrossing: false                                  // darf kreuzen?
gradeCrossingTphLimit: { highway: null, major: 6, medium: 8, minor: 10 }
```

- `allowAtGradeRoadCrossing` (Alias `canCrossRoads`) entscheidet, ob der Zugtyp
  Straßen überhaupt ebenerdig kreuzen darf. Bei Heavy/Light Metro steht sie auf
  `false` — deshalb blockt das Spiel dort jeden Übergang.
- `gradeCrossingTphLimit` ist die Obergrenze (kombinierte Fahrtrichtungen,
  Züge/Stunde) je Straßenklasse. `null` = an dieser Straßenklasse verboten.

Der Mod liest beides zur Laufzeit über `api.trains.getTrainTypes()` aus und
ersetzt es über `api.trains.modifyTrainType()`.

## Installation

1. Mods-Ordner öffnen — im Spiel unter **Einstellungen → Mod Manager →
   „Open Mods Folder"**, oder manuell:
   - **Windows:** `%APPDATA%\SubwayBuilder\mods\` (bzw. `metro-maker4`)
   - **macOS:** `~/Library/Application Support/SubwayBuilder/mods/`
   - **Linux:** `~/.config/SubwayBuilder/mods/`

   Existiert kein `mods`-Ordner, einfach selbst anlegen.

2. Diesen Mod-Ordner (mit `manifest.json` und `index.js`) dort hineinkopieren:
   ```
   mods/
   └── subwaybuilder_mods/
       ├── manifest.json
       ├── index.js
       └── README.md
   ```

3. Spiel starten → **Einstellungen → Mods** → Mod aktivieren.
   Im laufenden Spiel neu laden mit `Strg+Umschalt+R` (Mac: `Cmd+Umschalt+R`).

## Bedienung

Das Bedienfeld findest du an zwei Stellen:

- **Einstellungen-Menü** — als eigener Abschnitt eingebettet.
- **Schwebendes Panel „Bahnübergang-Limit"** — frei verschiebbar.

### Züge pro Stunde

Ein Zahlenfeld je Straßenklasse:

| Feld | Straßenklasse | Vanilla-Wert |
| --- | --- | --- |
| Autobahn / Schnellstraße | `highway` | gesperrt |
| Hauptstraße | `major` | 6 |
| Sammelstraße | `medium` | 8 |
| Nebenstraße | `minor` | 10 |

**Leeres Feld oder `0`** = Übergang an dieser Straßenklasse gesperrt.
In den Feldern sind nur Ziffern erlaubt.

### Straßenquerung erlauben

- **„Heavy & Light Metro dürfen Straßen kreuzen"** — schaltet die beiden
  Metro-Typen frei (standardmäßig **aktiv**).
- **„Alle Zugtypen dürfen Straßen kreuzen"** — schaltet zusätzlich alle
  übrigen Typen frei (z. B. Intercity).

### Knöpfe

- **„Anwenden"** — übernimmt alles und speichert es dauerhaft.
- **„Zurücksetzen"** — stellt den originalen Vanilla-Zustand wieder her:
  Limits **und** Kreuzungsverbote. Der Mod sichert sich den Originalzustand je
  Zugtyp beim allerersten Auslesen, bevor er etwas ändert.
- **Escape-Menü → „Bahnübergang-Limit anwenden"** — Werte erneut anwenden.

Die Einstellungen werden über `api.storage` gespeichert und beim Spielstart
sowie bei jedem Städtewechsel automatisch wieder angewendet.

## Startwerte anpassen (optional)

Wer die Vorgabewerte direkt im Code ändern will, findet sie oben in `index.js`:

```js
const LIMITS = {
  highway: null, // Autobahn (Vanilla: verboten)
  major: 30,     // Hauptstraße (Vanilla: 6)
  medium: 40,    // Sammelstraße (Vanilla: 8)
  minor: 60,     // Nebenstraße (Vanilla: 10)
};

const OPTIONS = {
  enableMetroCrossing: true,          // Heavy + Light Metro freischalten
  enableCrossingForAllTrains: false,  // alle Zugtypen freischalten
};

const METRO_TRAIN_IDS = ["heavy-metro", "light-metro"];
```

Bereits im Spiel gespeicherte Werte haben Vorrang vor diesen Startwerten.

## Hinweise

- Die tph-Werte gelten für **alle** kreuzenden Zugtypen gleich — die
  individuellen Vanilla-Unterschiede zwischen z. B. S-Bahn und Tram werden
  dabei überschrieben. „Zurücksetzen" stellt sie je Zugtyp wieder her.
- Neu freigeschaltete Zugtypen bekommen die konfigurierten Limits; sie starten
  also nicht mit den Vanilla-Werten anderer Zugtypen.
- Mehr Züge über einen Übergang beeinflussen die Straßen-/Verkehrssimulation —
  genau das ist ja gewollt.
