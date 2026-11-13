"""
Autofahrzeiten und -strecken auf dem OSM-Straßennetz (eigener Router).

Das Spiel vergleicht für jede Pendlergruppe die ÖPNV-Reisezeit mit der
Autofahrt (`drivingSeconds`, `drivingDistance`). Statt eines OSRM-Servers
wird hier das Netz direkt aus OSM aufgebaut und mit Dijkstra (scipy)
durchsucht:

  * Knoten = Kreuzungen und Wegenden (Zwischenpunkte werden zu Kanten zusammengefasst)
  * Geschwindigkeit aus `maxspeed`, sonst Richtwert je Straßenklasse,
    abgemindert für Ampeln/Verkehr
  * Einbahnstraßen und Kreisverkehre werden beachtet
  * Zuschlag für Parken + Fußweg zum Auto
"""

import json
import re

import numpy as np
from pyproj import Transformer
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from nef.common import TMP, log, run, utm_epsg

CAR_ROADS = ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
             "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
             "residential", "living_street", "service"]
# effektive km/h, wenn kein maxspeed angegeben ist
SPEED = {"motorway": 105, "motorway_link": 55, "trunk": 80, "trunk_link": 45, "primary": 42,
         "primary_link": 32, "secondary": 36, "secondary_link": 28, "tertiary": 30,
         "tertiary_link": 25, "unclassified": 32, "residential": 20, "living_street": 7,
         "service": 12}
PARK_SECONDS = 120     # Parkplatzsuche, Weg zum/vom Auto
ACCESS_KMH = 15        # Luftlinie Punkt -> nächster Netzknoten


def _speed(p):
    hw = p.get("highway")
    base = SPEED.get(hw, 25)
    ms = p.get("maxspeed")
    if ms:
        m = re.match(r"\s*(\d+)", str(ms))
        if m:
            v = float(m.group(1))
            if "mph" in str(ms):
                v *= 1.609
            factor = 0.75 if v <= 60 else 0.85 if v <= 100 else 0.9
            return max(5.0, min(v * factor, base * 1.4))
        if "walk" in str(ms):
            return 7.0
    return float(base)


class RoadGraph:
    def __init__(self, osm_pbf):
        pbf = TMP / "car_roads.osm.pbf"
        gj = TMP / "car_roads.geojsonseq"
        run(["osmium", "tags-filter", str(osm_pbf), "w/highway=" + ",".join(CAR_ROADS),
             "-o", str(pbf), "--overwrite"])
        run(["osmium", "export", str(pbf), "-f", "geojsonseq", "-o", str(gj),
             "--geometry-types=linestring", "--overwrite"])
        tr = Transformer.from_crs(4326, utm_epsg(), always_xy=True)
        ways = []
        for line in open(gj, encoding="utf-8"):
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            f = json.loads(line)
            p = f["properties"]
            if p.get("access") in ("no", "private") or p.get("motor_vehicle") in ("no", "private"):
                continue
            if p.get("highway") == "service" and p.get("service") in ("parking_aisle", "driveway", "drive-through"):
                continue
            c = np.array(f["geometry"]["coordinates"])
            x, y = tr.transform(c[:, 0], c[:, 1])
            ow = p.get("oneway")
            oneway = 1 if ow in ("yes", "true", "1") or p.get("junction") in ("roundabout", "circular") \
                or p.get("highway") in ("motorway",) and ow != "no" else -1 if ow == "-1" else 0
            ways.append((np.round(x, 1), np.round(y, 1), _speed(p) / 3.6, oneway))

        # Knoten: Koordinaten, die in mehreren Wegen vorkommen, plus Wegenden
        keys = {}
        count = {}
        for x, y, _, _ in ways:
            for k in zip(x.tolist(), y.tolist()):
                count[k] = count.get(k, 0) + 1
        src, dst, tt, ll = [], [], [], []
        for x, y, v, ow in ways:
            seg = np.hypot(np.diff(x), np.diff(y))
            pts = list(zip(x.tolist(), y.tolist()))
            start, acc = 0, 0.0
            for i in range(1, len(pts)):
                acc += seg[i - 1]
                if i == len(pts) - 1 or count[pts[i]] > 1:
                    a = keys.setdefault(pts[start], len(keys))
                    b = keys.setdefault(pts[i], len(keys))
                    if a != b and acc > 0:
                        if ow >= 0:
                            src.append(a); dst.append(b); tt.append(acc / v); ll.append(acc)
                        if ow <= 0:
                            src.append(b); dst.append(a); tt.append(acc / v); ll.append(acc)
                    start, acc = i, 0.0
        n = len(keys)
        self.xy = np.array(list(keys.keys()))
        import pandas as pd
        # Parallele Kanten: jeweils die schnellste bzw. kürzeste behalten
        e = pd.DataFrame({"s": src, "d": dst, "t": tt, "l": ll}).groupby(["s", "d"]).min().reset_index()
        src, dst = e["s"].values, e["d"].values
        self.time = coo_matrix((e["t"].values, (src, dst)), shape=(n, n)).tocsr()
        self.length = coo_matrix((e["l"].values, (src, dst)), shape=(n, n)).tocsr()
        _, lab = connected_components(self.time, directed=True, connection="strong")
        main = np.bincount(lab).argmax()
        self.ok = lab == main
        self.tree = cKDTree(self.xy[self.ok])
        self.ok_idx = np.flatnonzero(self.ok)
        log(f"  Straßengraph: {n} Knoten, {len(src)} Kanten, größte Komponente {self.ok.sum()}")

    def snap(self, xy):
        d, i = self.tree.query(xy)
        return self.ok_idx[i], d

    def matrix(self, orig_xy, dest_xy, pairs):
        """Fahrzeit (s) und Strecke (m) für die gewünschten Paare (i, j)."""
        on, od_ = self.snap(orig_xy)
        dn, dd = self.snap(dest_xy)
        pairs = np.asarray(pairs)
        secs = np.zeros(len(pairs))
        dist = np.zeros(len(pairs))
        order = np.argsort(pairs[:, 0], kind="stable")
        uniq_o, starts = np.unique(pairs[order, 0], return_index=True)
        bounds = np.append(starts, len(order))
        batch = 64
        for b in range(0, len(uniq_o), batch):
            os_ = uniq_o[b:b + batch]
            nodes = on[os_]
            T = dijkstra(self.time, indices=nodes)
            L = dijkstra(self.length, indices=nodes)
            for k, o in enumerate(os_):
                sel = order[bounds[b + k]:bounds[b + k + 1]]
                js = pairs[sel, 1]
                secs[sel] = T[k, dn[js]]
                dist[sel] = L[k, dn[js]]
        access = od_[pairs[:, 0]] + dd[pairs[:, 1]]
        secs = secs + access / (ACCESS_KMH / 3.6) + PARK_SECONDS
        dist = dist + access
        bad = ~np.isfinite(secs)
        if bad.any():
            log(f"  {bad.sum()} Paare ohne Straßenverbindung -> Luftlinienschätzung")
            straight = np.hypot(*(orig_xy[pairs[bad, 0]] - dest_xy[pairs[bad, 1]]).T)
            secs[bad] = straight * 1.3 / (30 / 3.6) + PARK_SECONDS
            dist[bad] = straight * 1.3
        return secs, dist
