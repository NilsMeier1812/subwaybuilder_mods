#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Werkzeuge für den Kartenbau installieren (Debian/Ubuntu oder WSL).
#
#  Legt alles unter ./tools ab (kein sudo für die Binärdateien nötig) und
#  eine Python-Umgebung unter ./.venv. Danach:
#
#      source ./env.sh && ./build_all.sh
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
TOOLS="$PWD/tools"
mkdir -p "$TOOLS"

echo "== Systempakete (osmium, sqlite3, Java, Compiler für tippecanoe)"
if command -v apt-get >/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq osmium-tool sqlite3 default-jre-headless build-essential \
       libsqlite3-dev zlib1g-dev git curl python3-venv
fi

echo "== tippecanoe + tile-join"
if [ ! -x "$TOOLS/tippecanoe" ]; then
  rm -rf "$TOOLS/src-tippecanoe"
  git clone -q --depth 1 https://github.com/felt/tippecanoe.git "$TOOLS/src-tippecanoe"
  make -C "$TOOLS/src-tippecanoe" -j"$(nproc)" >/dev/null
  cp "$TOOLS/src-tippecanoe/tippecanoe" "$TOOLS/src-tippecanoe/tile-join" "$TOOLS/"
fi

echo "== pmtiles"
if [ ! -x "$TOOLS/pmtiles" ]; then
  curl -sL -o "$TOOLS/pmtiles.tgz" \
    https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles_1.31.2_Linux_x86_64.tar.gz
  tar xzf "$TOOLS/pmtiles.tgz" -C "$TOOLS" pmtiles && rm "$TOOLS/pmtiles.tgz"
fi

echo "== planetiler"
[ -f "$TOOLS/planetiler.jar" ] || curl -sL -o "$TOOLS/planetiler.jar" \
  https://github.com/onthegomap/planetiler/releases/download/v0.10.2/planetiler.jar

echo "== Python-Umgebung"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

cat > env.sh <<EOF
export NEF_TOOLS="$TOOLS"
export PATH="$TOOLS:\$PATH"
source "$PWD/.venv/bin/activate"
EOF
echo "Fertig. Jetzt: source ./env.sh && ./build_all.sh"
