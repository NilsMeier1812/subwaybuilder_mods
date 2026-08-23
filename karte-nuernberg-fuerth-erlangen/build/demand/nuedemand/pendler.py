"""
Pendlerverflechtungen Gemeinde -> Gemeinde einlesen.

Quelle: Bundesagentur für Arbeit, "Pendlerverflechtungen der
sozialversicherungspflichtig Beschäftigten" bzw. der Pendleratlas. Die
Rohdateien sind Excel-Tabellen; für dieses Skript wird daraus eine schlanke
CSV erwartet:

    von_ags;nach_ags;anzahl
    09564000;09564000;180000
    09563000;09564000;22000

Die Umwandlung Excel -> CSV steht in ../ANLEITUNG.md.
"""

import csv
import io

FROM_COLUMNS = ("von_ags", "von", "wohnort", "wohnort_ags", "from", "from_ags", "quelle")
TO_COLUMNS = ("nach_ags", "nach", "arbeitsort", "arbeitsort_ags", "to", "to_ags", "ziel")
COUNT_COLUMNS = ("anzahl", "pendler", "count", "werte", "wert", "beschaeftigte", "insgesamt")


class PendlerFormatError(ValueError):
    pass


def _pick(fieldnames, candidates):
    lowered = {n.strip().lower(): n for n in fieldnames if n}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    return None


def _to_int(text):
    if text is None:
        return None
    text = str(text).strip().replace('"', "").replace(".", "").replace(" ", "")
    if not text or text in ("-", "x", "*"):
        return None
    try:
        return int(round(float(text.replace(",", "."))))
    except ValueError:
        return None


def read_matrix(path, keep_ags=None):
    """
    Liest die Pendlermatrix.

    ``keep_ags``: optionale Menge von AGS. Beziehungen, bei denen eine Seite
    nicht dazugehört, werden dann übersprungen und getrennt gezählt
    (Außenpendler).

    Rückgabe: ``(matrix, info)`` mit ``matrix = {(von, nach): anzahl}``.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            handle = io.StringIO(data.decode(encoding))
            break
        except UnicodeDecodeError:
            continue
    else:
        raise PendlerFormatError(f"Zeichenkodierung von {path} nicht erkannt")

    sample = handle.read(4096)
    handle.seek(0)
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        delimiter = ";"

    reader = csv.DictReader(handle, delimiter=delimiter)
    if not reader.fieldnames:
        raise PendlerFormatError(f"{path} hat keine Kopfzeile")

    from_col = _pick(reader.fieldnames, FROM_COLUMNS)
    to_col = _pick(reader.fieldnames, TO_COLUMNS)
    count_col = _pick(reader.fieldnames, COUNT_COLUMNS)
    if not (from_col and to_col and count_col):
        raise PendlerFormatError(
            f"Spalten für Wohnort/Arbeitsort/Anzahl fehlen in {path}. "
            f"Gefunden: {reader.fieldnames}"
        )

    matrix = {}
    info = {"rows": 0, "inbound_outside": 0, "outbound_outside": 0, "dropped": 0}
    for row in reader:
        src = (row.get(from_col) or "").strip().strip('"')
        dst = (row.get(to_col) or "").strip().strip('"')
        count = _to_int(row.get(count_col))
        if not src or not dst or not count or count <= 0:
            continue
        info["rows"] += 1

        if keep_ags is not None:
            src_in = src in keep_ags
            dst_in = dst in keep_ags
            if not (src_in and dst_in):
                if dst_in:
                    info["inbound_outside"] += count
                elif src_in:
                    info["outbound_outside"] += count
                else:
                    info["dropped"] += count
                continue

        matrix[(src, dst)] = matrix.get((src, dst), 0) + count

    return matrix, info
