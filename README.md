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

1. Mods-Ordner öffnen — im Spiel unter **Einstellungen → Mod Manager →
   „Open Mods Folder"**, oder manuell:
   - **Windows:** `%APPDATA%\SubwayBuilder\mods\`
   - **macOS:** `~/Library/Application Support/SubwayBuilder/mods/`
   - **Linux:** `~/.config/SubwayBuilder/mods/`

   Existiert kein `mods`-Ordner, einfach selbst anlegen.

2. **Die gewünschten Mod-Ordner** aus diesem Repo dorthin kopieren — nicht das
   Repo selbst. Danach sieht es so aus:

   ```
   mods/
   ├── bahnuebergaenge-metro/
   │   ├── manifest.json
   │   └── index.js
   └── zuglaenge-nach-tageszeit/
       ├── manifest.json
       └── index.js
   ```

3. Spiel starten → **Einstellungen → Mods** → Mods aktivieren.

### Bequemer: verlinken statt kopieren

Beim Entwickeln lohnt es sich, die Ordner zu verlinken. Dann wirkt jede
Code-Änderung sofort, ohne erneutes Kopieren.

**Windows** (Eingabeaufforderung als Administrator):
```cmd
mklink /D "%APPDATA%\SubwayBuilder\mods\bahnuebergaenge-metro" "C:\Pfad\zum\repo\bahnuebergaenge-metro"
```

**macOS / Linux:**
```bash
ln -s ~/pfad/zum/repo/bahnuebergaenge-metro ~/.config/SubwayBuilder/mods/bahnuebergaenge-metro
```

Im Spiel lädt `Strg+Umschalt+R` (Mac: `Cmd+Umschalt+R`) die Mods neu.

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

## Entwicklungshinweise

- Die Modding-API ist unter `window.SubwayBuilderAPI` erreichbar; Typdefinitionen
  gibt es im [offiziellen Template](https://github.com/Subway-Builder-Modded/SubwayBuilderTemplateMod).
- Konsole im Spiel mit `F12`. Beide Mods hier loggen mit einem eigenen Präfix
  (`[BahnübergangTPH]`, `[Zuglängen]`).
- `api.storage` funktioniert nur in der Desktop-Version (Electron); im Browser
  sind Speicheraufrufe wirkungslos.
