# Zuglängen nach Tageszeit — Subway Builder Mod

Stellt die **Wagenzahl je Linie abhängig von der Uhrzeit** ein — z. B. 10 Wagen
zur Hauptverkehrszeit, 7 tagsüber und 5 nachts.

## Wie das funktioniert

Eine Linie hat im Spiel nur einen einzigen Wert `carsPerTrain`. Die
Nachfrage-Stufen des Spiels (`trainSchedule` mit `highDemand`, `mediumDemand`,
`lowDemand`, `veryLowDemand`) steuern nur die **Anzahl** der Züge, nicht deren
Länge.

`api.gameState.getRoutes()` liefert Live-Referenzen auf den Spielzustand, und
`carsPerTrain` ist beschreibbar. Der Mod schreibt diesen Wert, sobald sich die
Spielstunde ändert. Da es keinen Hook für den Stundenwechsel gibt, fragt der Mod
die Spielzeit alle 3 Sekunden ab und wird nur bei einem Stundenwechsel aktiv.

Die Wagenzahl wird immer auf `minCars`/`maxCars` des jeweiligen Zugtyps
begrenzt, damit keine Züge entstehen, die länger als der Bahnsteig sind.

> **Bereits fahrende Züge behalten ihre Länge.** Die neue Wagenzahl greift, wenn
> das Spiel Züge neu einsetzt. Wer den Effekt sofort will, aktiviert
> **„Züge sofort erneuern"** — dann tauscht der Mod die Züge der betroffenen
> Linien aus.

## Installation

Ordner in den Mods-Ordner kopieren (siehe [Repo-README](../README.md)), Spiel
starten, unter **Einstellungen → Mods** aktivieren.

## Bedienung

Panel im **Einstellungen-Menü** und als verschiebbares Panel
**„Zuglängen nach Tageszeit"**.

### Zeitfenster

Drei Fenster plus ein Sammelwert:

```
von  6 bis  9 Uhr → 10 Wagen     (Morgenspitze)
von  9 bis 16 Uhr →  7 Wagen     (Tagesverkehr)
von 16 bis 19 Uhr → 10 Wagen     (Abendspitze)
sonst             →  5 Wagen     (Abend/Nacht)
```

Ein Fenster gilt von `von` (einschließlich) bis `bis` (ausschließlich) und darf
über Mitternacht gehen (`von` größer als `bis`, z. B. 22 bis 5). Alle nicht
abgedeckten Stunden nutzen den Sammelwert.

### Standard oder einzelne Linie

Im Auswahlfeld oben wählst du:

- **„Standard (alle Linien)"** — gilt für alle Linien ohne eigenes Profil.
- **eine konkrete Linie** — bekommt ein eigenes Profil. Linien mit eigenem
  Profil sind in der Liste mit ✓ markiert. Mit **„Eigenes Profil entfernen"**
  gilt wieder der Standard.

### Optionen

- **„Automatisch nach Tageszeit umstellen"** — Automatik an/aus.
- **„Züge sofort erneuern"** — tauscht nach einer Änderung die Züge der
  betroffenen Linien aus, damit die neue Länge sofort wirkt.

### Knöpfe

- **„Jetzt anwenden"** — wendet das Profil sofort auf die aktuelle Stunde an.
- **„Zurücksetzen"** — stellt die ursprüngliche Wagenzahl je Linie wieder her.

Alle Einstellungen werden über `api.storage` gespeichert.

## Startwerte anpassen (optional)

Oben in `index.js`:

```js
const DEFAULT_PROFILE = {
  windows: [
    { from: 6,  to: 9,  cars: 10 },
    { from: 9,  to: 16, cars: 7  },
    { from: 16, to: 19, cars: 10 },
  ],
  fallbackCars: 5,
};
```

Im Spiel gespeicherte Werte haben Vorrang.

## Hinweise

- Der Mod schreibt direkt in den Spielzustand. Das ist von der Modding-API nicht
  ausdrücklich als Schnittstelle vorgesehen — `getRoutes()` liefert aber
  Live-Referenzen mit beschreibbarem `carsPerTrain`. Bei einem Spiel-Update kann
  sich das ändern; dann meldet die Konsole Fehler unter `[Zuglängen]`.
- „Züge sofort erneuern" entfernt Züge und setzt sie neu ein. Das kostet
  Fahrzeit und kann den Takt kurz stören.
