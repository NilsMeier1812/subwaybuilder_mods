"""
Aus Einwohnern, Arbeitsplätzen und Pendlerzahlen die Nachfragepunkte und
Pendlerbeziehungen bauen.

Ablauf:

1. **Aggregieren** — das 100-m-Zensusgitter und die Gebäude sind viel zu fein
   für das Spiel. Beides wird auf ein gröberes Raster gelegt; jede belegte
   Rasterzelle wird ein Nachfragepunkt mit ``residents`` und ``jobs``.
2. **Verteilen** — die amtlichen Pendlerzahlen (Gemeinde -> Gemeinde) sind
   Randsummen. Innerhalb eines Gemeindepaars werden sie über ein
   Gravitationsmodell auf die Punkte verteilt: viele Einwohner, viele
   Arbeitsplätze und kurze Wege ziehen mehr Pendler.
3. **Runden** — nach dem Hare-Niemeyer-Verfahren, damit die amtlichen Summen
   exakt erhalten bleiben.

Ohne Pendlermatrix läuft Schritt 2 als ein einziges großes Gravitationsmodell
über das gesamte Gebiet — schlechtere Datenqualität, aber lauffähig.
"""

import math
from collections import defaultdict

from . import laea
from .geo import haversine


class Params:
    """Stellschrauben des Modells."""

    def __init__(
        self,
        cell_size_m=400,
        employment_rate=0.52,
        decay_km=6.0,
        top_k=15,
        max_distance_km=45.0,
        max_pop_size=200,
        min_pop_size=1,
    ):
        self.cell_size_m = cell_size_m
        # Anteil der Einwohner, die einer Arbeit nachgehen. Deutschland liegt
        # bei rund 52 % (Erwerbstätige je Einwohner, alle Altersgruppen).
        self.employment_rate = employment_rate
        # Abstandsempfindlichkeit: exp(-d / decay). 6 km entspricht etwa dem
        # mittleren Arbeitsweg in einer deutschen Großstadtregion.
        self.decay_km = decay_km
        # Nur die besten K Ziele je Wohnpunkt behalten — hält die Zahl der
        # Beziehungen im Rahmen.
        self.top_k = top_k
        self.max_distance_km = max_distance_km
        self.max_pop_size = max_pop_size
        self.min_pop_size = min_pop_size


def aggregate_points(resident_cells, job_records, params, ags_of=None):
    """
    Legt Einwohner und Arbeitsplätze auf ein gemeinsames Raster.

    ``resident_cells``: Dicts mit lon/lat/residents (aus dem Zensusgitter).
    ``job_records``:    Dicts mit lon/lat/jobs (aus den Gebäuden).
    ``ags_of``:         optionale Funktion (lon, lat) -> AGS, falls die
                        Datensätze noch keine Gemeinde tragen.

    Rückgabe: Liste von Punkten
    ``{"id", "lon", "lat", "residents", "jobs", "ags", "x", "y"}``
    """
    size = float(params.cell_size_m)
    buckets = {}

    def add(lon, lat, residents, jobs, ags):
        x, y = laea.forward(lon, lat)
        key = (int(math.floor(x / size)), int(math.floor(y / size)))
        entry = buckets.get(key)
        if entry is None:
            entry = {
                "residents": 0.0,
                "jobs": 0.0,
                "wx": 0.0,
                "wy": 0.0,
                "w": 0.0,
                "ags_weight": defaultdict(float),
            }
            buckets[key] = entry
        entry["residents"] += residents
        entry["jobs"] += jobs
        weight = residents + jobs
        if weight <= 0:
            weight = 1e-6
        entry["wx"] += x * weight
        entry["wy"] += y * weight
        entry["w"] += weight
        if ags:
            entry["ags_weight"][ags] += weight

    for cell in resident_cells:
        residents = float(cell.get("residents") or 0.0)
        if residents <= 0:
            continue
        ags = cell.get("ags") or (ags_of(cell["lon"], cell["lat"]) if ags_of else None)
        add(cell["lon"], cell["lat"], residents, 0.0, ags)

    for rec in job_records:
        jobs = float(rec.get("jobs") or 0.0)
        if jobs <= 0:
            continue
        ags = rec.get("ags") or (ags_of(rec["lon"], rec["lat"]) if ags_of else None)
        add(rec["lon"], rec["lat"], 0.0, jobs, ags)

    points = []
    for key in sorted(buckets):  # sortiert => reproduzierbare IDs
        entry = buckets[key]
        x = entry["wx"] / entry["w"]
        y = entry["wy"] / entry["w"]
        lon, lat = laea.inverse(x, y)
        ags = None
        if entry["ags_weight"]:
            ags = max(entry["ags_weight"].items(), key=lambda kv: (kv[1], kv[0]))[0]
        points.append(
            {
                "id": f"p{len(points)}",
                "lon": lon,
                "lat": lat,
                "x": x,
                "y": y,
                "residents": entry["residents"],
                "jobs": entry["jobs"],
                "ags": ags,
            }
        )
    return points


def fill_missing_ags(points):
    """
    Punkte ohne Gemeinde bekommen die des nächstgelegenen zugeordneten Punkts.

    Das betrifft Randfälle: Zensuszellen und Gebäude, deren Mittelpunkt knapp
    neben der Gemeindegrenze liegt (Rundung, vereinfachte Geometrien). Ohne
    diese Zuordnung fielen sie aus der Pendlermatrix heraus und ihre Einwohner
    wären für das Spiel verloren.
    """
    known = [p for p in points if p["ags"]]
    unknown = [p for p in points if not p["ags"]]
    if not known or not unknown:
        return 0
    for p in unknown:
        best = min(
            known,
            key=lambda q: (q["x"] - p["x"]) ** 2 + (q["y"] - p["y"]) ** 2,
        )
        p["ags"] = best["ags"]
    return len(unknown)


def _largest_remainder(values, total):
    """
    Hare-Niemeyer: reelle Anteile so runden, dass die Summe exakt ``total`` ist.
    """
    total = int(round(total))
    if total <= 0 or not values:
        return [0] * len(values)
    weight_sum = sum(values)
    if weight_sum <= 0:
        return [0] * len(values)

    exact = [v * total / weight_sum for v in values]
    floors = [int(math.floor(v)) for v in exact]
    rest = total - sum(floors)
    if rest > 0:
        order = sorted(
            range(len(values)), key=lambda i: (-(exact[i] - floors[i]), i)
        )
        for i in order[:rest]:
            floors[i] += 1
    return floors


def _pair_flows(sources, targets, total, params):
    """
    Verteilt ``total`` Pendler auf Wohn-/Arbeitspunktpaare (Gravitationsmodell).

    Gibt eine Liste von ``(source, target, anzahl)`` mit ganzzahligen Anzahlen
    zurück, deren Summe exakt ``total`` ist.
    """
    if total <= 0 or not sources or not targets:
        return []

    decay_m = params.decay_km * 1000.0
    max_d = params.max_distance_km * 1000.0

    pairs = []
    weights = []
    for src in sources:
        if src["residents"] <= 0:
            continue
        candidates = []
        for dst in targets:
            if dst["jobs"] <= 0:
                continue
            # Euklidisch in EPSG:3035 — flächentreu, lokal genau genug und
            # deutlich schneller als Haversine in der inneren Schleife.
            d = math.hypot(src["x"] - dst["x"], src["y"] - dst["y"])
            if d > max_d:
                continue
            w = dst["jobs"] * math.exp(-d / decay_m)
            if w > 0:
                candidates.append((w, dst))
        if not candidates:
            continue
        if len(candidates) > params.top_k:
            candidates.sort(key=lambda t: (-t[0], t[1]["id"]))
            candidates = candidates[: params.top_k]
        norm = sum(w for w, _ in candidates)
        for w, dst in candidates:
            pairs.append((src, dst))
            weights.append(src["residents"] * w / norm)

    counts = _largest_remainder(weights, total)
    return [
        (pairs[i][0], pairs[i][1], counts[i]) for i in range(len(pairs)) if counts[i] > 0
    ]


def build_flows(points, params, matrix=None, report=None):
    """
    Baut die Pendlerbeziehungen.

    ``matrix``: Dict ``{(von_ags, nach_ags): anzahl}``. Paare, bei denen eine
    Seite außerhalb des Kartenausschnitts liegt, werden übersprungen und im
    Report vermerkt — solche Außenpendler gehören später als
    ``outside_connection`` (Sonderbedarf) an den Rand der Karte.

    Ohne Matrix wird ein einziges Gravitationsmodell über alle Punkte
    gerechnet, mit ``employment_rate`` × Einwohner als Gesamtsumme.
    """
    report = report if report is not None else {}
    report.setdefault("skipped_pairs", [])
    report.setdefault("matrix_total", 0)
    report.setdefault("used_total", 0)

    if not matrix:
        total = sum(p["residents"] for p in points) * params.employment_rate
        flows = _pair_flows(points, points, total, params)
        report["mode"] = "gravity"
        report["used_total"] = sum(f[2] for f in flows)
        return flows

    by_ags = defaultdict(list)
    for p in points:
        if p["ags"]:
            by_ags[p["ags"]].append(p)

    flows = []
    for (src_ags, dst_ags), count in sorted(matrix.items()):
        report["matrix_total"] += count
        sources = by_ags.get(src_ags)
        targets = by_ags.get(dst_ags)
        if not sources or not targets:
            report["skipped_pairs"].append(
                {"from": src_ags, "to": dst_ags, "count": count}
            )
            continue
        flows.extend(_pair_flows(sources, targets, count, params))

    report["mode"] = "matrix"
    report["used_total"] = sum(f[2] for f in flows)
    return flows


def to_demand_data(points, flows, route_fn=None, params=None):
    """
    Baut das ``demand_data.json``-Objekt, das Subway Builder erwartet.

    ``route_fn(paare)`` bekommt eine Liste von ((lon,lat),(lon,lat)) und
    liefert eine gleich lange Liste von (sekunden, meter). Ohne Angabe wird
    geschätzt (routing.estimate).
    """
    from . import routing

    params = params or Params()
    route_fn = route_fn or (lambda pairs: [routing.estimate(a, b) for a, b in pairs])

    used = {}
    for src, dst, _count in flows:
        used[src["id"]] = src
        used[dst["id"]] = dst

    # Beziehungen ggf. in mehrere Pops aufteilen, damit keine riesigen
    # Einzelgruppen entstehen (das Spiel bewegt sie als Block).
    split_flows = []
    for src, dst, count in flows:
        remaining = int(count)
        while remaining > 0:
            chunk = min(remaining, params.max_pop_size)
            split_flows.append((src, dst, chunk))
            remaining -= chunk

    coords = [((f[0]["lon"], f[0]["lat"]), (f[1]["lon"], f[1]["lat"])) for f in split_flows]
    routed = route_fn(coords) if coords else []

    pops = []
    pop_ids_by_point = defaultdict(list)
    for i, (src, dst, count) in enumerate(split_flows):
        pop_id = str(i)
        seconds, meters = routed[i]
        pops.append(
            {
                "id": pop_id,
                "size": int(count),
                "residenceId": src["id"],
                "jobId": dst["id"],
                "drivingSeconds": int(seconds),
                "drivingDistance": int(meters),
            }
        )
        pop_ids_by_point[src["id"]].append(pop_id)
        if dst["id"] != src["id"]:
            pop_ids_by_point[dst["id"]].append(pop_id)

    out_points = []
    for pid in sorted(used, key=lambda k: int(k[1:])):
        p = used[pid]
        out_points.append(
            {
                "id": pid,
                "location": [round(p["lon"], 7), round(p["lat"], 7)],
                "jobs": int(round(p["jobs"])),
                "residents": int(round(p["residents"])),
                "popIds": pop_ids_by_point[pid],
            }
        )

    return {"points": out_points, "pops": pops}


def statistics(demand):
    """Kennzahlen zum Gegenlesen — vergleichbar mit den Railyard-Angaben."""
    points = demand["points"]
    pops = demand["pops"]
    total = sum(p["size"] for p in pops)

    def weighted_percentile(q):
        """Perzentil der Fahrstrecke, gewichtet nach Gruppengröße."""
        if not pops or total == 0:
            return 0.0
        ordered = sorted(pops, key=lambda p: p["drivingDistance"])
        target = q * total
        cumulative = 0
        for pop in ordered:
            cumulative += pop["size"]
            if cumulative >= target:
                return pop["drivingDistance"] / 1000.0
        return ordered[-1]["drivingDistance"] / 1000.0

    mean_km = (
        sum(p["drivingDistance"] * p["size"] for p in pops) / total / 1000.0
        if total
        else 0.0
    )
    return {
        "points_count": len(points),
        "population_count": len(pops),
        "residents_total": sum(p["residents"] for p in points),
        "jobs_total": sum(p["jobs"] for p in points),
        "commuters_total": total,
        "mean_commute_km": round(mean_km, 2),
        "commute_km_p10": round(weighted_percentile(0.10), 2),
        "commute_km_p50": round(weighted_percentile(0.50), 2),
        "commute_km_p90": round(weighted_percentile(0.90), 2),
        "max_pop_size": max((p["size"] for p in pops), default=0),
    }
