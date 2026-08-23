"""
Einlesen des Zensus-2022-Bevölkerungsgitters (100 m, INSPIRE / EPSG:3035).

Das Statistische Bundesamt liefert die Datei als CSV mit Semikolon. Je nach
Download-Variante heißen die Spalten unterschiedlich und die Koordinaten sind
mal explizit enthalten, mal nur in der Gitter-ID kodiert. Beides wird hier
unterstützt; die Spaltenerkennung läuft über Kandidatenlisten statt fester
Namen, damit ein Formatwechsel nicht sofort alles bricht.

Erwartet wird eine der beiden Formen:

    GITTER_ID_100m;werte
    CRS3035RES100mN2986600E4419500;12

    GITTER_ID_100m;x_mp_100m;y_mp_100m;werte
    CRS3035RES100mN2986600E4419500;4419550;2986650;12
"""

import csv
import gzip
import io
import os

from . import laea
from .geo import bbox_contains

ID_COLUMNS = ("gitter_id_100m", "gitter_id", "grid_id", "id", "gitter_id_100m_neu")
VALUE_COLUMNS = (
    "werte",
    "wert",
    "einwohner",
    "anzahl",
    "value",
    "insgesamt",
    "bevoelkerung",
    "bevölkerung",
)
X_COLUMNS = ("x_mp_100m", "x_mp", "x_sw", "x")
Y_COLUMNS = ("y_mp_100m", "y_mp", "y_sw", "y")


class ZensusFormatError(ValueError):
    pass


def _open_text(path):
    """Öffnet CSV oder CSV.GZ und behandelt utf-8-BOM sowie Latin-1."""
    raw = gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")
    data = raw.read()
    raw.close()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return io.StringIO(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise ZensusFormatError(f"Zeichenkodierung von {path} nicht erkannt")


def _pick(fieldnames, candidates):
    lowered = {name.strip().lower(): name for name in fieldnames if name}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    return None


def _to_number(text):
    if text is None:
        return None
    text = text.strip().replace('"', "")
    if not text:
        return None
    # Deutsche Dezimalkommas kommen in manchen Exporten vor
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def read_population_grid(path, bbox=None, min_residents=1):
    """
    Liest das Bevölkerungsgitter und liefert eine Liste von Zellen.

    Rückgabe je Zelle: ``{"lon": float, "lat": float, "residents": int,
    "grid_id": str}``

    Zellen mit gesperrten Werten (in den amtlichen Dateien ``-1``) und Zellen
    außerhalb der ``bbox`` werden übersprungen.
    """
    handle = _open_text(path)
    sample = handle.read(8192)
    handle.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"

    reader = csv.DictReader(handle, delimiter=delimiter)
    if not reader.fieldnames:
        raise ZensusFormatError(f"{path} hat keine Kopfzeile")

    id_col = _pick(reader.fieldnames, ID_COLUMNS)
    val_col = _pick(reader.fieldnames, VALUE_COLUMNS)
    x_col = _pick(reader.fieldnames, X_COLUMNS)
    y_col = _pick(reader.fieldnames, Y_COLUMNS)

    if val_col is None:
        raise ZensusFormatError(
            f"Keine Wertespalte in {path} gefunden. "
            f"Spalten: {reader.fieldnames}. Erwartet eine von {VALUE_COLUMNS}"
        )
    if id_col is None and not (x_col and y_col):
        raise ZensusFormatError(
            f"Weder Gitter-ID noch Koordinatenspalten in {path}. "
            f"Spalten: {reader.fieldnames}"
        )

    cells = []
    for row in reader:
        value = _to_number(row.get(val_col))
        if value is None or value < min_residents:
            continue  # leer, gesperrt (-1) oder unter der Schwelle

        if x_col and y_col:
            x = _to_number(row.get(x_col))
            y = _to_number(row.get(y_col))
            if x is None or y is None:
                continue
        else:
            try:
                x, y, _size = laea.parse_grid_id(row[id_col])
            except (KeyError, ValueError):
                continue

        lon, lat = laea.inverse(x, y)
        if bbox and not bbox_contains(bbox, lon, lat):
            continue

        cells.append(
            {
                "lon": lon,
                "lat": lat,
                "residents": int(round(value)),
                "grid_id": (row.get(id_col) or "").strip(),
            }
        )
    handle.close()
    return cells


def de_int(n):
    """Ganzzahl mit deutschem Tausenderpunkt."""
    return f"{int(n):,}".replace(",", ".")


def total_residents(cells):
    return sum(c["residents"] for c in cells)


def describe(cells, label="Zensus-Gitter"):
    if not cells:
        return f"{label}: keine Zellen"
    lons = [c["lon"] for c in cells]
    lats = [c["lat"] for c in cells]
    return (
        f"{label}: {de_int(len(cells))} Zellen, "
        f"{de_int(total_residents(cells))} Einwohner, "
        f"bbox {min(lons):.4f},{min(lats):.4f},{max(lons):.4f},{max(lats):.4f}"
    )


def find_default_file(directory="."):
    """Sucht eine plausible Zensus-Gitterdatei im Verzeichnis."""
    hits = []
    for name in sorted(os.listdir(directory)):
        low = name.lower()
        if not (low.endswith(".csv") or low.endswith(".csv.gz")):
            continue
        if "gitter" in low or "100m" in low or "zensus" in low:
            hits.append(os.path.join(directory, name))
    return hits[0] if hits else None
