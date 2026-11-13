#!/usr/bin/env python3
"""
Schritt 3: Nachfragedaten (demand_data.json) bauen.

Ablauf
------
1. Gemeinden im Ausschnitt mit Erwerbstätigen am Wohn- und Arbeitsort
   (Pendlerrechnung der Statistischen Ämter, Stichtag 30.6.2024).
2. Gemeinde -> Gemeinde-Pendlermatrix: amtliche Innerorts- und Top-10-Ströme,
   Rest per IPF (nef/od.py).
3. Wohnorte: Erwerbstätige je Gemeinde auf die 100-m-Zensuszellen verteilt,
   gewichtet mit den 18- bis 64-Jährigen.
4. Arbeitsorte: Erwerbstätige am Arbeitsort auf Gebäude verteilt (nef/jobs.py).
5. Nachfragepunkte: Raster von GRID_M Metern je Gemeinde, Lage = Schwerpunkt.
6. Punkt -> Punkt-Matrix: dreifach beschränktes IPF (Wohnpunkte, Arbeitspunkte,
   Gemeindepaare) mit Distanzabfall.
7. Ganzzahlige Pendlergruppen (pops), Sonderziele, Autofahrzeiten.
8. Prüfungen wie im Railyard-Register, Ausgabe.
"""

import json
import math
from collections import defaultdict

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from nef import jobs, od, residents, routing, zones
from nef.common import BBOX, BUILD_DIR, CODE, OUT, RAW, REGION, haversine_m, log, write_json

GRID_M = 300            # Kantenlänge der Nachfragezellen
MIN_ACTIVITY = 12       # kleinere Zellen werden mit der nächsten zusammengelegt
DECAY_KM = 6.0          # Distanzabfall innerhalb eines Gemeindepaars
POP_TARGET = 12         # mittlere Gruppengröße
MAX_POP = 200           # Railyard: höchstens 200 empfohlen, 231 hart
SEED = 20241113
OSM = RAW / "osm" / "region.osm.pbf"


def hare_niemeyer(total, weights):
    """Ganzzahlige Aufteilung von `total` proportional zu `weights`."""
    w = np.asarray(weights, dtype=float)
    if total <= 0 or w.sum() <= 0:
        return np.zeros(len(w), dtype=int)
    q = w / w.sum() * total
    base = np.floor(q).astype(int)
    rest = int(round(total - base.sum()))
    if rest > 0:
        base[np.argsort(-(q - base), kind="stable")[:rest]] += 1
    return base


# --------------------------------------------------------------------------

def build_points(cells, blds):
    """Zensuszellen und Gebäude zu Nachfragepunkten bündeln."""
    a = pd.DataFrame({"ARS": cells["ARS"], "x": cells["x"], "y": cells["y"], "res": cells["E"], "job": 0.0})
    b = pd.DataFrame({"ARS": blds["ARS"], "x": blds.geometry.x, "y": blds.geometry.y, "res": 0.0, "job": blds["J"]})
    act = pd.concat([a, b], ignore_index=True)
    act = act[(act["res"] + act["job"]) > 0]
    act["gx"] = np.floor(act["x"] / GRID_M).astype(int)
    act["gy"] = np.floor(act["y"] / GRID_M).astype(int)
    act["w"] = act["res"] + act["job"]
    act["wx"] = act["x"] * act["w"]
    act["wy"] = act["y"] * act["w"]
    p = act.groupby(["ARS", "gx", "gy"]).agg(res=("res", "sum"), job=("job", "sum"), w=("w", "sum"),
                                              wx=("wx", "sum"), wy=("wy", "sum")).reset_index()
    p["x"] = p["wx"] / p["w"]
    p["y"] = p["wy"] / p["w"]
    p = p[["ARS", "x", "y", "res", "job"]]

    # Kleine Punkte in den nächsten größeren derselben Gemeinde verschieben
    from scipy.spatial import cKDTree
    merged = []
    for ars, grp in p.groupby("ARS"):
        grp = grp.copy()
        big = grp[(grp["res"] + grp["job"]) >= MIN_ACTIVITY]
        small = grp[(grp["res"] + grp["job"]) < MIN_ACTIVITY]
        if len(big) == 0 or len(small) == 0:
            merged.append(grp)
            continue
        tree = cKDTree(big[["x", "y"]].to_numpy())
        d, k = tree.query(small[["x", "y"]].to_numpy())
        keep = d > 1500          # zu weit weg -> eigener Punkt (Weiler)
        res = big["res"].to_numpy(copy=True)
        job = big["job"].to_numpy(copy=True)
        np.add.at(res, k[~keep], small["res"].to_numpy()[~keep])
        np.add.at(job, k[~keep], small["job"].to_numpy()[~keep])
        big = big.assign(res=res, job=job)
        merged.append(pd.concat([big, small[keep]]))
    p = pd.concat(merged, ignore_index=True)
    return p


def point_ipf(pts, zone_T, zone_codes, iters=40):
    """Punktmatrix an Wohn-, Arbeits- und Gemeindepaar-Summen anpassen."""
    n = len(pts)
    zi = {c: k for k, c in enumerate(zone_codes)}
    z = pts["ARS"].map(zi).values
    G = len(zone_codes)
    xy = pts[["x", "y"]].values / 1000.0
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1)).astype(np.float32)
    M = np.exp(-d / DECAY_KM).astype(np.float32)
    del d
    np.fill_diagonal(M, 0)            # niemand pendelt innerhalb derselben Zelle
    R = pts["res"].values.astype(np.float32)
    J = pts["job"].values.astype(np.float32)
    M *= R[:, None]
    M *= J[None, :]
    onehot = np.zeros((n, G), dtype=np.float32)
    onehot[np.arange(n), z] = 1
    for it in range(iters):
        S = onehot.T @ (M @ onehot)
        F = np.divide(zone_T, S, out=np.zeros_like(S), where=S > 0).astype(np.float32)
        M *= F[z][:, z]
        rs = M.sum(1)
        M *= np.divide(R, rs, out=np.zeros_like(rs), where=rs > 0)[:, None]
        cs = M.sum(0)
        M *= np.divide(J, cs, out=np.zeros_like(cs), where=cs > 0)[None, :]
    S = onehot.T @ (M @ onehot)
    err_zone = np.abs(S - zone_T).sum() / zone_T.sum()
    err_row = np.abs(M.sum(1) - R).sum() / R.sum()
    log(f"  Punkt-IPF: {n} Punkte, Abweichung Gemeindepaare {err_zone:.2%}, Wohnorte {err_row:.2%}")
    return M


def make_pops(M, rng):
    """Zeilenweise systematische Stichprobe -> ganzzahlige Gruppen."""
    n = M.shape[0]
    rows = M.sum(1)
    res_int = hare_niemeyer(int(round(rows.sum())), rows)
    pops = []
    for i in range(n):
        Ri = int(res_int[i])
        if Ri <= 0:
            continue
        p = M[i].astype(np.float64)
        p /= p.sum()
        k = max(1, math.ceil(Ri / POP_TARGET))
        cum = np.cumsum(p)
        u = (rng.random() + np.arange(k)) / k
        dest = np.minimum(np.searchsorted(cum, u), n - 1)
        js, cnt = np.unique(dest, return_counts=True)
        sizes = hare_niemeyer(Ri, cnt)
        for j, s in zip(js, sizes):
            while s > 0:
                part = min(s, MAX_POP)
                pops.append((i, int(j), part))
                s -= part
    return pops


def add_specials(pts, pops, rng):
    spec = json.loads((BUILD_DIR / "specials.json").read_text(encoding="utf-8"))["specials"]
    res = np.zeros(len(pts))
    for i, _, s in pops:
        res[i] += s
    lon, lat = pts["lon"].values, pts["lat"].values
    new_pts = []
    for s in spec:
        d = haversine_m(s["location"][0], s["location"][1], lon, lat) / 1000
        w = res * np.exp(-d / s["decay_km"])
        w[d < 0.4] = 0
        w /= w.sum()
        k = max(1, round(s["capacity"] / s["pop_size"]))
        draws = rng.choice(len(pts), size=k, p=w)
        js = len(pts) + len(new_pts)
        o, cnt = np.unique(draws, return_counts=True)
        sizes = hare_niemeyer(s["capacity"], cnt)
        for i, sz in zip(o, sizes):
            while sz > 0:
                part = min(sz, MAX_POP)
                pops.append((int(i), js, int(part)))
                sz -= part
        new_pts.append(s)
    log(f"  Sonderziele: {len(spec)} Punkte, {sum(s['capacity'] for s in spec)} Personen")
    return new_pts


def validate(points, popl):
    """Dieselben Prüfungen wie die Integritätsprüfung des Railyard-Registers."""
    ids = {p["id"] for p in points}
    pid = {p["id"]: p for p in popl}
    assert len(ids) == len(points), "doppelte Punkt-IDs"
    assert len(pid) == len(popl), "doppelte Pop-IDs"
    for p in popl:
        assert p["residenceId"] in ids and p["jobId"] in ids, "Pop verweist ins Leere"
        assert 1 <= p["size"] <= MAX_POP, f"Pop-Größe {p['size']}"
        assert p["drivingSeconds"] > 0 and p["drivingDistance"] > 0
    res_pts = sum(p["residents"] for p in points)
    res_pops = sum(p["size"] for p in popl)
    assert res_pts == res_pops, f"Einwohnersummen {res_pts} != {res_pops}"
    assert sum(p["jobs"] for p in points) == res_pops
    phantom = [p["id"] for p in points if p["residents"] == 0 and p["jobs"] == 0]
    assert not phantom, f"Phantompunkte: {phantom[:5]}"
    for p in points:
        for q in p["popIds"]:
            pp = pid[q]
            assert p["id"] in (pp["residenceId"], pp["jobId"])
    lonlat = np.array([p["location"] for p in points])
    from scipy.spatial import cKDTree
    d, _ = cKDTree(lonlat).query(lonlat, k=2)
    assert d[:, 1].max() < 0.5, "isolierter Punkt"
    assert ((lonlat[:, 0] >= BBOX[0]) & (lonlat[:, 0] <= BBOX[2]) &
            (lonlat[:, 1] >= BBOX[1]) & (lonlat[:, 1] <= BBOX[3])).all(), "Punkt außerhalb der BBox"


def main():
    rng = np.random.default_rng(SEED)

    # 1 + 2: Gemeinden und Gemeindematrix
    zn = zones.load_zones()
    codes, T = od.gemeinde_matrix()
    cidx = {c: k for k, c in enumerate(codes)}

    # 3: Wohnbevölkerung
    cells = residents.load_cells(zn)
    cells["ARS"] = zones.assign_zone(cells[["x", "y"]].values, zn)
    cells["wa"] = residents.working_age(cells)
    inside = ((cells["lon"] >= BBOX[0]) & (cells["lon"] <= BBOX[2]) &
              (cells["lat"] >= BBOX[1]) & (cells["lat"] <= BBOX[3]))
    wa_all = cells.groupby("ARS")["wa"].sum()
    wa_in = cells[inside].groupby("ARS")["wa"].sum()
    frac = (wa_in / wa_all).fillna(0)
    cells = cells[inside].copy()
    mz = [c for c in frac.index if frac[c] > 0 and c in cidx]
    fr = np.array([frac[c] for c in mz])
    ix = [cidx[c] for c in mz]
    zone_T = T[np.ix_(ix, ix)] * fr[:, None] * fr[None, :]
    A = pd.Series(zone_T.sum(1), index=mz)      # Wohnseite im Modell
    B = pd.Series(zone_T.sum(0), index=mz)      # Arbeitsseite im Modell
    cells["E"] = cells["wa"] / cells["ARS"].map(cells.groupby("ARS")["wa"].sum()) * cells["ARS"].map(A)
    cells["E"] = cells["E"].fillna(0)

    # 4: Arbeitsplätze
    log("Arbeitsplätze verteilen …")
    blds = jobs.building_weights(zn.crs, OSM)
    bb = gpd.GeoSeries([box(*BBOX)], crs=4326).to_crs(zn.crs).iloc[0]
    blds = blds[blds.within(bb)].copy()
    blds["ARS"] = zones.assign_zone(np.c_[blds.geometry.x, blds.geometry.y], zn)
    wsum = blds.groupby("ARS")["w"].sum()
    blds["J"] = blds["w"] / blds["ARS"].map(wsum) * blds["ARS"].map(B)
    blds["J"] = blds["J"].fillna(0)

    # 5: Nachfragepunkte
    pts = build_points(cells, blds)
    pts = pts[pts["ARS"].isin(mz)].reset_index(drop=True)
    wgs = gpd.GeoSeries(gpd.points_from_xy(pts["x"], pts["y"]), crs=zn.crs).to_crs(4326)
    pts["lon"], pts["lat"] = wgs.x.values, wgs.y.values
    log(f"  {len(pts)} Nachfragepunkte")

    # 6: Punktmatrix
    M = point_ipf(pts, zone_T.astype(np.float32), mz)

    # 7: Gruppen, Sonderziele, Fahrzeiten
    pops = make_pops(M, rng)
    del M
    specials = add_specials(pts, pops, rng)

    names = dict(zip(zn["ARS"], zn["GEN"]))
    point_ids = [f"{CODE}_{i}" for i in range(len(pts))] + [s["id"] for s in specials]
    lonlat = np.vstack([pts[["lon", "lat"]].values, np.array([s["location"] for s in specials])])
    xy_all = np.vstack([pts[["x", "y"]].values,
                        gpd.GeoSeries(gpd.points_from_xy(lonlat[len(pts):, 0], lonlat[len(pts):, 1]),
                                      crs=4326).to_crs(zn.crs).get_coordinates().values])

    log("Fahrzeiten berechnen …")
    pairs = np.array(sorted({(i, j) for i, j, _ in pops}))
    g = routing.RoadGraph(OSM)
    secs, dist = g.matrix(xy_all, xy_all, pairs)
    tt = {(int(a), int(b)): (s, d) for (a, b), s, d in zip(pairs, secs, dist)}

    # 8: Ausgabe
    points = [{"id": pid, "location": [round(float(lo), 6), round(float(la), 6)],
               "jobs": 0, "residents": 0, "popIds": []} for pid, (lo, la) in zip(point_ids, lonlat)]
    popl = []
    for k, (i, j, s) in enumerate(pops):
        sec, dm = tt[(i, j)]
        pid = str(k)
        popl.append({"id": pid, "size": int(s), "residenceId": point_ids[i], "jobId": point_ids[j],
                     "drivingSeconds": int(round(sec)), "drivingDistance": int(round(dm))})
        points[i]["residents"] += int(s)
        points[j]["jobs"] += int(s)
        points[i]["popIds"].append(pid)
        if j != i:
            points[j]["popIds"].append(pid)
    points = [p for p in points if p["residents"] or p["jobs"]]
    validate(points, popl)
    data = {"points": points, "pops": popl}
    write_json(OUT / "demand_data.json.gz", data, gz=True)

    # Kennzahlen
    sizes = np.array([p["size"] for p in popl])
    dm = np.array([p["drivingDistance"] for p in popl])
    ds = np.array([p["drivingSeconds"] for p in popl])
    straight = haversine_m(lonlat[[p_[0] for p_ in pops], 0], lonlat[[p_[0] for p_ in pops], 1],
                           lonlat[[p_[1] for p_ in pops], 0], lonlat[[p_[1] for p_ in pops], 1])
    zone_res = defaultdict(int)
    zone_job = defaultdict(int)
    for (i, j, s) in pops:
        if i < len(pts):
            zone_res[names[pts["ARS"].iat[i]]] += int(s)
        if j < len(pts):
            zone_job[names[pts["ARS"].iat[j]]] += int(s)
    stats = {
        "points": len(points), "pops": len(popl), "population": int(sizes.sum()),
        "regular_commuters": int(sum(s for i, j, s in pops if j < len(pts))),
        "special_trips": int(sum(s for i, j, s in pops if j >= len(pts))),
        "mean_pop_size": round(float(sizes.mean()), 1), "max_pop_size": int(sizes.max()),
        "commute_km_mean_weighted": round(float((dm * sizes).sum() / sizes.sum() / 1000), 2),
        "commute_km_straight_mean_weighted": round(float((straight * sizes).sum() / sizes.sum() / 1000), 2),
        "drive_min_mean_weighted": round(float((ds * sizes).sum() / sizes.sum() / 60), 1),
        "residents_by_municipality": dict(sorted(zone_res.items(), key=lambda kv: -kv[1])),
        "jobs_by_municipality": dict(sorted(zone_job.items(), key=lambda kv: -kv[1])),
    }
    (OUT / "demand_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Fertig: {stats['points']} Punkte, {stats['pops']} Gruppen, {stats['population']} Personen, "
        f"Ø Arbeitsweg {stats['commute_km_mean_weighted']} km / {stats['drive_min_mean_weighted']} min")


if __name__ == "__main__":
    main()
