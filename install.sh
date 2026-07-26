#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Verlinkt jeden Mod-Ordner dieses Repos in den Subway-Builder-Mods-Ordner.
#  Nach einem "git pull" sind die Änderungen sofort im Spiel.
#
#  Aufruf:   ./install.sh
#  Optional: ./install.sh /pfad/zum/mods/ordner
# ---------------------------------------------------------------------------
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODS="${1:-}"

if [ -z "$MODS" ]; then
  # Der Ordnername unterscheidet sich je nach Spielversion.
  for base in \
    "$HOME/Library/Application Support/SubwayBuilder" \
    "$HOME/Library/Application Support/metro-maker4" \
    "$HOME/.config/SubwayBuilder" \
    "$HOME/.config/metro-maker4"
  do
    if [ -d "$base" ]; then
      MODS="$base/mods"
      break
    fi
  done
fi

if [ -z "$MODS" ]; then
  echo "[FEHLER] Kein Subway-Builder-Ordner gefunden." >&2
  echo "         Pfad zum mods-Ordner bitte angeben: ./install.sh /pfad/zu/mods" >&2
  exit 1
fi

mkdir -p "$MODS"
echo "Mods-Ordner: $MODS"
echo

count=0
for dir in "$REPO"/*/; do
  [ -f "${dir}manifest.json" ] || continue
  name="$(basename "$dir")"
  target="$MODS/$name"

  if [ -L "$target" ]; then
    rm "$target"                      # alte Verknüpfung ersetzen
  elif [ -e "$target" ]; then
    echo "[ÜBERSPRUNGEN] $name – dort liegt ein echter Ordner."
    echo "               Bitte von Hand entfernen und erneut ausführen."
    continue
  fi

  ln -s "${dir%/}" "$target"
  echo "[OK] $name"
  count=$((count + 1))
done

echo
echo "$count Mod(s) verlinkt."
echo "Spiel starten und unter Einstellungen > Mods aktivieren."
