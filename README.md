# Subway Builder Mods

Sammlung eigener Mods für [Subway Builder](https://www.subwaybuilder.com).
Jeder Mod liegt in einem eigenen Unterordner und ist unabhängig von den anderen
— du kannst einzeln installieren, was du brauchst.

| Mod | Was er macht |
| --- | --- |
| [`bahnuebergaenge-metro/`](bahnuebergaenge-metro/) | Schaltet echte Bahnübergänge für Heavy Metro und Light Metro frei und überschreibt das Züge-pro-Stunde-Limit je Straßenklasse. |
| [`zuglaenge-nach-tageszeit/`](zuglaenge-nach-tageszeit/) | Stellt die Wagenzahl je Linie nach Uhrzeit ein — z. B. 10 Wagen zur Hauptverkehrszeit, 5 nachts. |

## Aufbau

```
subwaybuilder_mods/
├── README.md                    ← diese Übersicht
├── install.cmd                  ← verlinkt alle Mods (Windows)
├── install.sh                   ← verlinkt alle Mods (macOS/Linux)
├── bahnuebergaenge-metro/
│   ├── manifest.json
│   ├── index.js
│   └── README.md
└── zuglaenge-nach-tageszeit/
    ├── manifest.json
    ├── index.js
    └── README.md
```

Ein Mod ist genau ein Ordner mit `manifest.json` und `index.js`. Die
`manifest.json` muss in diesem Ordner liegen, nicht eine Ebene darüber.

## Installation

Der Mods-Ordner liegt hier (im Spiel: **Einstellungen → Mod Manager →
„Open Mods Folder"**):

- **Windows:** `%APPDATA%\SubwayBuilder\mods\`
- **macOS:** `~/Library/Application Support/SubwayBuilder/mods/`
- **Linux:** `~/.config/SubwayBuilder/mods/`

Je nach Spielversion heißt der Ordner statt `SubwayBuilder` auch `metro-maker4`.

**Wichtig:** Das Spiel erwartet die Mods **direkt** in `mods/`, also
`mods/<mod-name>/manifest.json`. Klont man dieses Repo einfach in den
Mods-Ordner, liegt alles eine Ebene zu tief und das Spiel meldet einen Fehler:

```
mods/
└── subwaybuilder_mods/          ← so nicht: eine Ebene zu viel
    └── bahnuebergaenge-metro/
        └── manifest.json
```

Dafür gibt es zwei saubere Lösungen.

### Variante A: verlinken (empfohlen)

Repo an einen beliebigen Ort klonen (z. B. `C:\dev\` oder `~/dev/`) und die
mitgelieferten Skripte ausführen. Sie legen für jeden Mod-Ordner eine
Verknüpfung im Mods-Ordner an:

**Windows** — normale Eingabeaufforderung, **keine** Administratorrechte nötig
(das Skript nutzt Verzeichnis-Junctions):
```cmd
cd C:\dev\subwaybuilder_mods
install.cmd
```

**macOS / Linux:**
```bash
cd ~/dev/subwaybuilder_mods
./install.sh
```

Findet das Skript den Mods-Ordner nicht, gib ihn als Argument mit:
`install.cmd "C:\Pfad\zu\mods"` bzw. `./install.sh /pfad/zu/mods`.

Danach genügt `git pull` — die Änderungen sind sofort im Spiel, ohne erneutes
Kopieren oder erneutes Ausführen des Skripts. Nur wenn ein **neuer** Mod-Ordner
dazukommt, das Skript noch einmal laufen lassen.

Die Skripte sind gefahrlos wiederholbar: bestehende Verknüpfungen werden
ersetzt, echte Ordner werden nie gelöscht, sondern übersprungen.

### Variante B: Repo direkt als Mods-Ordner

Alternativ wird der Mods-Ordner selbst zum Repo — dann liegen die Mod-Ordner
von vornherein an der richtigen Stelle. In einem **leeren** Mods-Ordner:

```bash
cd "<mods-ordner>"
git clone https://github.com/NilsMeier1812/subwaybuilder_mods.git .
```

Liegen dort schon andere Mods, geht es so ohne Löschen:

```bash
cd "<mods-ordner>"
git init
git remote add origin https://github.com/NilsMeier1812/subwaybuilder_mods.git
git fetch origin main
git checkout -t origin/main
```

Aktualisiert wird dann direkt im Mods-Ordner mit `git pull`. Nachteil: fremde
Mods im selben Ordner tauchen bei `git status` als unversionierte Dateien auf.

### Danach

Spiel starten → **Einstellungen → Mods** → Mods aktivieren.
Im laufenden Spiel lädt `Strg+Umschalt+R` (Mac: `Cmd+Umschalt+R`) die Mods neu.

## Einen neuen Mod anlegen

1. Neuen Ordner im Repo erstellen, z. B. `mein-neuer-mod/`.
2. `manifest.json` hineinlegen — die `id` muss über alle Mods eindeutig sein:

   ```json
   {
     "id": "com.nilsmeier.mein-neuer-mod",
     "name": "Mein neuer Mod",
     "description": "Was er macht.",
     "version": "1.0.0",
     "author": { "name": "Nils Meier" },
     "main": "index.js"
   }
   ```

3. `index.js` schreiben. Einstieg ist immer `window.SubwayBuilderAPI`.
4. Diese Übersicht oben in der Tabelle ergänzen.
5. Bei Variante A einmal `install.cmd` bzw. `./install.sh` ausführen, damit der
   neue Ordner verlinkt wird.

## Entwicklungshinweise

- Die Modding-API ist unter `window.SubwayBuilderAPI` erreichbar; Typdefinitionen
  gibt es im [offiziellen Template](https://github.com/Subway-Builder-Modded/SubwayBuilderTemplateMod).
- Konsole im Spiel mit `F12`. Beide Mods hier loggen mit einem eigenen Präfix
  (`[BahnübergangTPH]`, `[Zuglängen]`).
- `api.storage` funktioniert nur in der Desktop-Version (Electron); im Browser
  sind Speicheraufrufe wirkungslos.
