# Bahnübergang-Limit Override — Subway Builder Mod

Überschreibt das Limit für **Züge pro Stunde (tph) an Bahnübergängen** in
[Subway Builder](https://www.subwaybuilder.com). Standardmäßig begrenzt das
Spiel, wie viele Züge einen ebenerdigen Straßenübergang je nach Straßenklasse
befahren dürfen. Dieser Mod lässt dich die Werte **direkt im Spiel eingeben**.

## Wie das Limit im Spiel funktioniert

Jeder Zugtyp, der Straßen ebenerdig kreuzen darf, besitzt die Eigenschaft
`gradeCrossingTphLimit` — eine Obergrenze (kombinierte Fahrtrichtungen,
Züge/Stunde) je Straßenklasse:

```js
gradeCrossingTphLimit: { highway: null, major: 6, medium: 8, minor: 10 }
```

- `null` = an dieser Straßenklasse ist ein ebenerdiger Übergang **verboten**
- Zahlen = maximale Züge pro Stunde über den Übergang

Der Mod liest diese Werte zur Laufzeit über `api.trains.getTrainTypes()` aus
und ersetzt sie über `api.trains.modifyTrainType(id, { gradeCrossingTphLimit })`.

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

Die Werte werden **im Spiel per Zahleneingabe** gesetzt — je ein Feld pro
Straßenklasse:

| Feld | Straßenklasse | Vanilla-Wert |
| --- | --- | --- |
| Autobahn / Schnellstraße | `highway` | gesperrt |
| Hauptstraße | `major` | 6 |
| Sammelstraße | `medium` | 8 |
| Nebenstraße | `minor` | 10 |

Das Eingabefeld findest du an zwei Stellen:

- **Einstellungen-Menü** — dort ist der Mod als eigener Abschnitt eingebettet.
- **Schwebendes Panel „Bahnübergang-Limit"** — frei verschiebbar.

Dazu gibt es:

- **„Anwenden"** — übernimmt die eingegebenen Werte und speichert sie dauerhaft.
- **„Zurücksetzen"** — stellt die originalen Vanilla-Werte wieder her.
- **Häkchen „Auf alle Zugtypen anwenden"** — bezieht auch Zugtypen ein, die
  normalerweise gar keine Straßen kreuzen dürfen (z. B. reine U-Bahnen).
- **Escape-Menü → „Bahnübergang-Limit anwenden"** — Werte erneut anwenden.

**Leeres Feld oder `0`** bedeutet: Übergang an dieser Straßenklasse gesperrt.
In den Feldern sind nur Ziffern erlaubt.

Die Werte werden über `api.storage` gespeichert und beim Spielstart sowie bei
jedem Städtewechsel automatisch wieder angewendet.

## Startwerte anpassen (optional)

Wer die Vorgabewerte direkt im Code ändern will, findet sie oben in `index.js`:

```js
const LIMITS = {
  highway: null, // Autobahn (Vanilla: verboten)
  major: 30,     // Hauptstraße (Vanilla: 6)
  medium: 40,    // Sammelstraße (Vanilla: 8)
  minor: 60,     // Nebenstraße (Vanilla: 10)
};
```

Bereits gespeicherte Werte aus dem Spiel haben Vorrang vor diesen Startwerten.

## Hinweise

- Der Mod ändert nur Zugtypen, die Straßen ebenerdig kreuzen dürfen
  (`allowAtGradeRoadCrossing` bzw. vorhandenes `gradeCrossingTphLimit`), außer
  das Häkchen „Auf alle Zugtypen anwenden" ist gesetzt.
- Die Werte gelten für **alle** kreuzenden Zugtypen gleich — die individuellen
  Vanilla-Unterschiede zwischen z. B. S-Bahn und Tram werden dabei überschrieben.
  „Zurücksetzen" stellt die ursprünglichen Werte je Zugtyp wieder her.
- Mehr Züge über einen Übergang können die Straßen-/Verkehrssimulation
  beeinflussen — genau das ist ja gewollt.
