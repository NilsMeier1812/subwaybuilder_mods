"""
Arbeitsplätze aus der Beschäftigtenstatistik auf Gebäude verteilen.

Die Bundesagentur für Arbeit veröffentlicht die sozialversicherungspflichtig
Beschäftigten **am Arbeitsort** je Gemeinde. Diese Summe ist der Anker; die
räumliche Verteilung darunter kommt aus den Gebäuden (siehe buildings.py).

Zur Gemeindesumme kommt noch ein Aufschlag für Selbstständige, Beamte und
geringfügig Beschäftigte, die in der SV-Statistik fehlen — in Deutschland
grob +20 bis +25 % (Parameter ``non_sv_factor``).
"""

import csv
import io

AGS_COLUMNS = ("ags", "gemeindeschluessel", "gemeindeschlüssel", "ags8", "code", "id")
JOB_COLUMNS = (
    "beschaeftigte",
    "beschäftigte",
    "beschaeftigte_am_arbeitsort",
    "sv_arbeitsort",
    "arbeitsort",
    "jobs",
    "werte",
    "wert",
    "anzahl",
)
NAME_COLUMNS = ("name", "gemeinde", "gemeindename", "bezeichnung")


class JobsFormatError(ValueError):
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
    if not text or text in ("-", "x", "*", "."):
        return None  # gesperrter oder fehlender Wert
    text = text.replace(",", ".")
    try:
        return int(round(float(text)))
    except ValueError:
        return None


def read_jobs_csv(path, non_sv_factor=1.22):
    """
    Liest Beschäftigte je Gemeinde.

    Erwartet eine CSV mit einer AGS- und einer Beschäftigtenspalte, z. B.

        ags;name;beschaeftigte
        09564000;Nürnberg;285000

    Rückgabe: ``{ags: jobs}`` — bereits um ``non_sv_factor`` erhöht, damit
    Selbstständige und Beamte enthalten sind.
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
        raise JobsFormatError(f"Zeichenkodierung von {path} nicht erkannt")

    sample = handle.read(4096)
    handle.seek(0)
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        delimiter = ";"

    reader = csv.DictReader(handle, delimiter=delimiter)
    if not reader.fieldnames:
        raise JobsFormatError(f"{path} hat keine Kopfzeile")

    ags_col = _pick(reader.fieldnames, AGS_COLUMNS)
    job_col = _pick(reader.fieldnames, JOB_COLUMNS)
    if ags_col is None or job_col is None:
        raise JobsFormatError(
            f"AGS- oder Beschäftigtenspalte fehlt in {path}. Spalten: {reader.fieldnames}"
        )

    out = {}
    for row in reader:
        ags = (row.get(ags_col) or "").strip().strip('"')
        jobs = _to_int(row.get(job_col))
        if not ags or jobs is None:
            continue
        out[ags] = out.get(ags, 0) + int(round(jobs * non_sv_factor))
    return out


def assign_to_municipality(records, gem_index):
    """
    Trägt jedem Datensatz seine Gemeinde (``ags``) ein.

    ``records`` sind Dicts mit ``lon``/``lat``; ohne Treffer bleibt ``ags``
    None. Gibt die Zahl der nicht zugeordneten Datensätze zurück.
    """
    unmatched = 0
    for rec in records:
        ags = gem_index.lookup(rec["lon"], rec["lat"]) if gem_index else None
        rec["ags"] = ags
        if ags is None:
            unmatched += 1
    return unmatched


def distribute(buildings, jobs_by_ags, fallback_total=None):
    """
    Verteilt die Gemeindesummen auf die Gebäude.

    Setzt voraus, dass ``assign_to_municipality`` schon gelaufen ist. Trägt
    jedem Gebäude ``jobs`` ein und gibt einen Report zurück.
    """
    by_ags = {}
    for b in buildings:
        by_ags.setdefault(b.get("ags"), []).append(b)

    report = {"assigned": {}, "missing_buildings": [], "unknown_ags": 0}

    for ags, total in sorted(jobs_by_ags.items()):
        group = by_ags.get(ags) or []
        weight_sum = sum(b["weight"] for b in group)
        if not group or weight_sum <= 0:
            report["missing_buildings"].append(ags)
            continue
        for b in group:
            b["jobs"] = total * b["weight"] / weight_sum
        report["assigned"][ags] = total

    # Gebäude ohne bekannte Gemeinde: optional über eine Restsumme bedienen
    orphans = by_ags.get(None) or []
    if orphans:
        report["unknown_ags"] = len(orphans)
        weight_sum = sum(b["weight"] for b in orphans)
        if fallback_total and weight_sum > 0:
            for b in orphans:
                b["jobs"] = fallback_total * b["weight"] / weight_sum

    for b in buildings:
        b.setdefault("jobs", 0.0)

    return report
