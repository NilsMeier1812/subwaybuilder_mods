"""Geometrie-Grundlagen: Distanzen, Flächen, Punkt-in-Polygon."""

import math

from . import laea

EARTH_R = 6371008.8


def haversine(a, b):
    """Großkreisdistanz in Metern zwischen zwei (lon, lat)-Punkten."""
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(min(1.0, h)))


def bbox_contains(bbox, lon, lat):
    """bbox = [min_lon, min_lat, max_lon, max_lat]."""
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def ring_area_m2(ring):
    """
    Fläche eines Rings [[lon, lat], ...] in m².

    Gerechnet wird in EPSG:3035 — die Projektion ist flächentreu, das Ergebnis
    also auch für größere Polygone belastbar.
    """
    if len(ring) < 3:
        return 0.0
    pts = [laea.forward(lon, lat) for lon, lat in ring]
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_area_m2(coords):
    """Fläche eines GeoJSON-Polygons (Außenring minus Löcher)."""
    if not coords:
        return 0.0
    area = ring_area_m2(coords[0])
    for hole in coords[1:]:
        area -= ring_area_m2(hole)
    return max(0.0, area)


def ring_centroid(ring):
    """Flächenschwerpunkt eines Rings, zurück als (lon, lat)."""
    pts = [laea.forward(lon, lat) for lon, lat in ring]
    if len(pts) < 3:
        n = float(len(pts)) or 1.0
        return laea.inverse(sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)

    a = cx = cy = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:  # entartetes Polygon
        n = float(len(pts))
        return laea.inverse(sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    a *= 0.5
    return laea.inverse(cx / (6 * a), cy / (6 * a))


def point_in_ring(lon, lat, ring):
    """Ray-Casting. Punkte exakt auf der Kante gelten als innen."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x_cross = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x_cross == lon:
                return True
            if x_cross > lon:
                inside = not inside
    return inside


def point_in_polygon(lon, lat, coords):
    """GeoJSON-Polygon: im Außenring und in keinem Loch."""
    if not coords or not point_in_ring(lon, lat, coords[0]):
        return False
    return not any(point_in_ring(lon, lat, hole) for hole in coords[1:])


def geometry_bbox(geom):
    """Bounding Box einer GeoJSON-Geometrie als [min_lon, min_lat, max_lon, max_lat]."""
    lons, lats = [], []

    def walk(node):
        if isinstance(node, (list, tuple)):
            if node and isinstance(node[0], (int, float)):
                lons.append(node[0])
                lats.append(node[1])
            else:
                for child in node:
                    walk(child)

    walk(geom.get("coordinates", []))
    if not lons:
        return None
    return [min(lons), min(lats), max(lons), max(lats)]


def polygons_of(geom):
    """Liefert die Polygonliste einer Polygon- oder MultiPolygon-Geometrie."""
    if not geom:
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []
    if gtype == "Polygon":
        return [coords]
    if gtype == "MultiPolygon":
        return list(coords)
    return []


def geometry_area_m2(geom):
    return sum(polygon_area_m2(p) for p in polygons_of(geom))


def geometry_centroid(geom):
    """Flächengewichteter Schwerpunkt einer (Multi)Polygon-Geometrie."""
    polys = polygons_of(geom)
    if not polys:
        if geom and geom.get("type") == "Point":
            c = geom["coordinates"]
            return (c[0], c[1])
        return None
    total = 0.0
    sx = sy = 0.0
    for poly in polys:
        area = polygon_area_m2(poly)
        if area <= 0:
            continue
        lon, lat = ring_centroid(poly[0])
        x, y = laea.forward(lon, lat)
        sx += x * area
        sy += y * area
        total += area
    if total <= 0:
        lon, lat = ring_centroid(polys[0][0])
        return (lon, lat)
    return laea.inverse(sx / total, sy / total)


class PolygonIndex:
    """
    Einfacher Index über Flächen (z. B. Gemeindegrenzen).

    Bounding-Box-Vorfilter, danach exakter Punkt-in-Polygon-Test. Für die
    gut hundert Gemeinden im Kartenausschnitt völlig ausreichend.
    """

    def __init__(self, features, key_property):
        self.entries = []
        for feat in features:
            geom = feat.get("geometry")
            polys = polygons_of(geom)
            if not polys:
                continue
            bbox = geometry_bbox(geom)
            key = feat.get("properties", {}).get(key_property)
            if key is None:
                continue
            self.entries.append((str(key), bbox, polys))

    def __len__(self):
        return len(self.entries)

    @property
    def keys(self):
        return [e[0] for e in self.entries]

    def lookup(self, lon, lat):
        """Schlüssel der Fläche, in der der Punkt liegt — sonst None."""
        for key, bbox, polys in self.entries:
            if not bbox_contains(bbox, lon, lat):
                continue
            for poly in polys:
                if point_in_polygon(lon, lat, poly):
                    return key
        return None
