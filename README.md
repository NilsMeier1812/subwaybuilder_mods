# Bahnübergang-Limit Override — Subway Builder Mod

Überschreibt das Limit für **Züge pro Stunde (tph) an Bahnübergängen** in
[Subway Builder](https://www.subwaybuilder.com). Standardmäßig begrenzt das
Spiel, wie viele Züge einen ebenerdigen Straßenübergang je nach Straßenklasse
befahren dürfen. Dieser Mod hebt diese Grenzen an oder ganz auf.

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

1. Ordner in dein Subway-Builder-Mods-Verzeichnis kopieren (der Ordner muss
   `manifest.json` und `index.js` enthalten).
2. Spiel starten → **Einstellungen → Mods** → Mod aktivieren.
3. Im laufenden Spiel neu laden mit `Strg+Umschalt+R` (Mac: `Cmd+Umschalt+R`).

## Konfiguration

Alle Einstellungen stehen oben in `index.js` im `CONFIG`-Block:

| Option | Bedeutung |
| --- | --- |
| `mode` | `"multiply"` (Faktor), `"set"` (feste Werte) oder `"unlimited"` (praktisch unbegrenzt) |
| `multiplier` | Faktor im Modus `"multiply"` (z. B. `3` = dreifaches Limit) |
| `values` | Feste Grenzen je Straßenklasse im Modus `"set"` (`null` = weiterhin verboten) |
| `unlimitedValue` | Wert im Modus `"unlimited"` (Standard `999`) |
| `allowHighwayCrossing` | Auch an Autobahnen/Highways Übergänge erlauben (Standard: aus) |
| `applyToAllTrains` | Auch Zugtypen anfassen, die aktuell gar nicht kreuzen dürfen |

### Beispiele

**Limit verdreifachen (Standard):**
```js
mode: "multiply",
multiplier: 3,
```

**Feste Werte setzen:**
```js
mode: "set",
values: { highway: null, major: 30, medium: 40, minor: 60 },
```

**Limit komplett aufheben:**
```js
mode: "unlimited",
unlimitedValue: 999,
```

## Bedienung im Spiel

Der Mod fügt zusätzlich Bedienelemente hinzu:

- **Escape-Menü → „Bahnübergang-Limit anwenden"** — wendet die Werte erneut an
  und zeigt eine Zusammenfassung.
- **Einstellungen → Schieberegler „Bahnübergang-Limit ×Faktor"** — Faktor live
  ändern.
- **Einstellungen → Schalter „Bahnübergang-Limit aufheben"** — Limit an/aus.

Die Werte werden automatisch beim Spielstart und bei jedem Städtewechsel
angewendet.

## Hinweise

- Der Mod ändert nur Zugtypen, die Straßen ebenerdig kreuzen dürfen
  (`allowAtGradeRoadCrossing` bzw. vorhandenes `gradeCrossingTphLimit`), außer
  `applyToAllTrains` ist aktiv.
- Erlaubt der Mod mehr Züge über einen Übergang, kann das die Straßen-/Verkehrs-
  simulation beeinflussen — genau das ist ja gewollt.
