# Bahnübergänge für Metro — Subway Builder Mod

Mod für [Subway Builder](https://www.subwaybuilder.com) mit zwei Funktionen:

1. **Echte Bahnübergänge für Heavy Metro und Light Metro** — im Vanilla-Spiel
   können nur Commuter-Rail-Gleise Straßen ebenerdig kreuzen.
2. **Limit überschreiben** — wie viele Züge pro Stunde (tph) einen Übergang
   befahren dürfen, einstellbar je Straßenklasse.

## Wie das im Spiel funktioniert

Das Spiel führt je Zugtyp fünf Eigenschaften rund um Bahnübergänge:

| Eigenschaft | Bedeutung | Commuter Rail | Heavy Metro (Vanilla) |
| --- | --- | --- | --- |
| `allowGradeCrossing` | **erzeugt einen echten Bahnübergang** | `true` | `false` |
| `allowAtGradeRoadCrossing` | erlaubt das Queren der Straße überhaupt | `true` | `false` |
| `gradeCrossingTphLimit` | Züge/Stunde je Straßenklasse | Objekt | fehlt |
| `gradeCrossingBaseCost` | Baukosten je Übergang | `300000` | fehlt |
| `gradeCrossingMaintenancePerDay` | laufende Kosten je Übergang | `5000` | fehlt |

Der entscheidende Punkt: Setzt man **nur** `allowAtGradeRoadCrossing`, quert das
Gleis die Straße zwar, es entsteht aber **kein** Bahnübergang. Erst
`allowGradeCrossing` erzeugt einen — zusammen mit den beiden Kostenfeldern, die
Heavy/Light Metro sonst ganz fehlen.

Der Mod setzt alle fünf Eigenschaften über `api.trains.modifyTrainType()` und
übernimmt die Kosten automatisch von einem Zugtyp, der im Vanilla-Spiel bereits
Übergänge baut (Commuter Rail).

Passend dazu kennt das Spiel diese Konstanten:
`GRADE_CROSSING_SIGNAL_RADIUS` (200), `GRADE_CROSSING_APPROACH_SECONDS` (20),
`GRADE_CROSSING_CLEAR_SECONDS` (15).

## Installation

1. Mods-Ordner öffnen — im Spiel unter **Einstellungen → Mod Manager →
   „Open Mods Folder"**, oder manuell:
   - **Windows:** `%APPDATA%\SubwayBuilder\mods\`
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

> **Nach einem Update des Mods bitte das Spiel komplett neu starten** (nicht nur
> `Strg+Umschalt+R`). Nur dann sieht der Mod die unverfälschten Vanilla-Werte
> und merkt sie sich dauerhaft für „Zurücksetzen".

## Bedienung

Das Bedienfeld gibt es im **Einstellungen-Menü** und als verschiebbares Panel
**„Bahnübergänge"**.

### Züge pro Stunde

Ein Zahlenfeld je Straßenklasse — leeres Feld oder `0` = an dieser
Straßenklasse gesperrt:

| Feld | Straßenklasse |
| --- | --- |
| Autobahn / Schnellstraße | `highway` |
| Hauptstraße | `major` |
| Sammelstraße | `medium` |
| Nebenstraße | `minor` |

### Kosten je Übergang

**Baukosten** und **Unterhalt pro Tag**. Leer lassen = automatisch die Werte von
Commuter Rail übernehmen.

### Bahnübergänge freischalten

- **„Heavy & Light Metro"** — schaltet die beiden Metro-Typen frei (Standard: an)
- **„Alle Zugtypen"** — schaltet zusätzlich alle übrigen Typen frei

### Knöpfe

- **„Anwenden"** — übernimmt alles und speichert es dauerhaft.
- **„Zurücksetzen"** — stellt den originalen Vanilla-Zustand wieder her, inklusive
  Kreuzungsverbote und Kosten.
- **„Diagnose in Konsole"** — schreibt einen rein lesenden Bericht in die
  Konsole (`F12`): aktueller und ursprünglicher Zustand aller Zugtypen,
  Bahnübergangs-Konstanten und wie viele Gleise oberirdisch liegen.
- **Escape-Menü → „Bahnübergänge anwenden"**

Alles wird über `api.storage` gespeichert und beim Spielstart sowie bei jedem
Städtewechsel automatisch wieder angewendet.

## Startwerte anpassen (optional)

Oben in `index.js`:

```js
const LIMITS = { highway: null, major: 30, medium: 40, minor: 60 };

const COSTS = {
  baseCost: null,          // null = von Commuter Rail übernehmen
  maintenancePerDay: null,
};

const OPTIONS = {
  enableMetroCrossing: true,
  enableCrossingForAllTrains: false,
};

const METRO_TRAIN_IDS = ["heavy-metro", "light-metro"];
```

Im Spiel gespeicherte Werte haben Vorrang vor diesen Startwerten.

## Hinweise

- Die tph-Werte gelten für **alle** kreuzenden Zugtypen gleich, auch für
  Commuter Rail. „Zurücksetzen" stellt die Originalwerte je Zugtyp wieder her.
- Der Mod sichert den Vanilla-Zustand beim ersten Lauf und legt ihn unter dem
  Speicherschlüssel `…originals.v2` ab. Wurde dabei versehentlich ein bereits
  veränderter Zustand gesichert, hilft ein vollständiger Spiel-Neustart mit
  deaktiviertem Mod, gefolgt von einer erneuten Aktivierung.
- Mehr Züge über einen Übergang beeinflussen die Straßen-/Verkehrssimulation —
  genau das ist ja gewollt.
