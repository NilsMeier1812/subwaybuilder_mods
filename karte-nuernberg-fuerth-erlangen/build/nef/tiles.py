"""
Basiskacheln ins Schema von Subway Builder umbauen.

planetiler erzeugt Kacheln im OpenMapTiles-Schema. Das Spiel erwartet eigene
Layer (siehe Doku *Map Customization* und die Community-Karten):

    water        Gewässerflächen          kind=water
    landuse      Grünflächen + Flughafen  kind=park | aerodrome
    commercial   Gewerbe/Handel/Hochschul kind=commercial|retail, type=college
    hospital     Kliniken                 kind=hospital
    industrial   Industrie                kind=industrial
    residential  Wohngebiete              kind=residential

Straßen und Rollbahnen kommen nicht aus den Kacheln, sondern aus
roads.geojson / runways_taxiways.geojson. Gebäude und Labels werden getrennt
mit tippecanoe gebaut und danach zusammengeführt.
"""

import gzip
import math
import sqlite3
from multiprocessing import Pool

import mapbox_vector_tile
import shapely
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

EXTENT = 4096
WEB_MERC = 20037508.342789244

WATER = {"river", "canal", "lake", "pond", "reservoir", "basin", "ocean", "lagoon",
         "swimming_pool", "dock", "water", "stream", "ditch", "drain", "oxbow"}
GREEN = {"park", "nature_reserve", "protected_area", "national_park", "cemetery",
         "pitch", "zoo", "grass", "wood", "forest", "scrub", "wetland", "garden",
         "playground", "golf_course", "recreation_ground", "meadow", "village_green",
         "allotments", "heath"}

_BBOX = None


def _init(bbox):
    global _BBOX
    _BBOX = bbox


def _merc(lon, lat):
    x = lon * WEB_MERC / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    return x, y * WEB_MERC / 180.0


def _local_bbox(z, x, y_tms):
    """Kartenausschnitt in lokalen Kachelkoordinaten (y nach oben, TMS-Zeile)."""
    size = 2 * WEB_MERC / 2 ** z
    tx0, ty0 = -WEB_MERC + x * size, -WEB_MERC + y_tms * size
    mx0, my0 = _merc(_BBOX[0], _BBOX[1])
    mx1, my1 = _merc(_BBOX[2], _BBOX[3])
    f = EXTENT / size
    lx0 = min(max((mx0 - tx0) * f, 0), EXTENT)
    lx1 = min(max((mx1 - tx0) * f, 0), EXTENT)
    ly0 = min(max((my0 - ty0) * f, 0), EXTENT)
    ly1 = min(max((my1 - ty0) * f, 0), EXTENT)
    return box(lx0, ly0, lx1, ly1) if lx1 > lx0 and ly1 > ly0 else None


def _units_per_m(z):
    return EXTENT / (2 * WEB_MERC / 2 ** z)


def _polys(g):
    """Nur Flächenanteile zurückgeben (make_valid liefert manchmal Linien)."""
    if g is None or g.is_empty:
        return None
    if not g.is_valid:
        g = shapely.make_valid(g)
    if isinstance(g, (Polygon, MultiPolygon)):
        return g
    parts = [p for p in getattr(g, "geoms", []) if isinstance(p, (Polygon, MultiPolygon))]
    return unary_union(parts) if parts else None


def _explode(g, min_area=1.0):
    g = _polys(g)
    if g is None:
        return []
    parts = list(g.geoms) if isinstance(g, MultiPolygon) else [g]
    return [orient(p, 1.0) for p in parts if p.area >= min_area]


def _feat(geom, props):
    return {"geometry": mapping(geom), "properties": props}


def process_tile(args):
    z, x, y, data = args
    raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
    layers = mapbox_vector_tile.decode(raw)
    clip = _local_bbox(z, x, y)
    if clip is None:
        return None

    water, green, aero = [], [], []
    other = {"commercial": [], "hospital": [], "industrial": [], "residential": []}
    college = []
    upm = _units_per_m(z)

    for lname, layer in layers.items():
        for f in layer["features"]:
            p = f.get("properties", {})
            cls = str(p.get("class") or p.get("subclass") or "").lower()
            gtype = f["geometry"]["type"]
            if lname in ("transportation", "boundary", "aerodrome_label", "water_name", "building"):
                continue
            if lname == "aeroway":
                if gtype.endswith("Polygon") and cls in ("aerodrome",):
                    aero.append(shape(f["geometry"]))
                continue
            try:
                g = shape(f["geometry"])
            except Exception:
                continue
            if lname == "waterway" or (lname == "water" and "LineString" in gtype):
                # Linien nur für größere Gewässer; Bäche erst nah herangezoomt
                if cls in ("river", "canal") or (z >= 13 and cls == "stream"):
                    width = 12 if cls in ("river", "canal") else 3
                    water.append(g.buffer(max(width / 2 * upm, 2.0), cap_style=2))
                continue
            if not gtype.endswith("Polygon"):
                continue
            if lname == "water" or cls in WATER:
                water.append(g)
            elif cls == "aerodrome" or (cls == "military"):
                aero.append(g)
            elif cls in GREEN or lname == "park":
                green.append(g)
            elif cls in ("commercial", "retail"):
                other["commercial"].append((g, cls))
            elif cls in ("college", "university", "school", "kindergarten"):
                college.append(g)
            elif cls in ("hospital", "industrial", "residential"):
                other[cls].append((g, cls))

    out = {}
    water_u = None
    if water:
        water_u = _polys(unary_union([_polys(w.buffer(0)) for w in water if _polys(w.buffer(0))]))
        if water_u is not None:
            water_u = shapely.set_precision(water_u.intersection(clip), 1.0)
            out["water"] = [_feat(p, {"kind": "water", "sort_rank": 200}) for p in _explode(water_u, 2.0)]

    aero_u = _polys(unary_union([_polys(a) for a in aero if _polys(a)]).intersection(clip)) if aero else None
    comm_u = None
    if other["commercial"]:
        comm_u = _polys(unary_union([_polys(g) for g, _ in other["commercial"] if _polys(g)]))

    land = []
    if green:
        g = _polys(unary_union([_polys(g) for g in green if _polys(g)]))
        if g is not None:
            g = _polys(g.buffer(4).buffer(-4))
            g = _polys(shapely.set_precision(g.intersection(clip), 1.0))
            for mask in (water_u, aero_u, comm_u):
                if g is not None and mask is not None and g.intersects(mask):
                    g = _polys(g.difference(mask))
            land += [_feat(p, {"kind": "park", "sort_rank": 189}) for p in _explode(g)]
    if aero_u is not None:
        a = aero_u
        if water_u is not None and a.intersects(water_u):
            a = _polys(a.difference(water_u))
        land += [_feat(p, {"kind": "aerodrome", "sort_rank": 189}) for p in _explode(a)]
    if land:
        out["landuse"] = land

    comm = []
    for g, cls in other["commercial"]:
        g = _polys(_polys(g).intersection(clip)) if _polys(g) else None
        for mask in (water_u, aero_u):
            if g is not None and mask is not None and g.intersects(mask):
                g = _polys(g.difference(mask))
        comm += [_feat(p, {"kind": cls, "sort_rank": 0}) for p in _explode(g)]
    for g in college:
        g = _polys(_polys(g).intersection(clip)) if _polys(g) else None
        comm += [_feat(p, {"type": "college", "sort_rank": 0}) for p in _explode(g)]
    if comm:
        out["commercial"] = comm
    for name in ("hospital", "industrial", "residential"):
        feats = []
        for g, cls in other[name]:
            g = _polys(_polys(g).intersection(clip)) if _polys(g) else None
            feats += [_feat(p, {"kind": cls, "sort_rank": 0}) for p in _explode(g)]
        if feats:
            out[name] = feats

    if not out:
        return None
    enc = mapbox_vector_tile.encode(
        [{"name": k, "features": v} for k, v in out.items()],
        default_options={"extents": EXTENT, "y_coord_down": False},
    )
    return z, x, y, gzip.compress(enc)


def convert(src_mbtiles, dst_mbtiles, bbox, workers=4):
    """Alle Kacheln aus src umbauen und als neue MBTiles schreiben."""
    src = sqlite3.connect(src_mbtiles)
    tiles = src.execute("SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles").fetchall()
    meta = src.execute("SELECT name, value FROM metadata").fetchall()
    src.close()
    with Pool(workers, initializer=_init, initargs=(bbox,)) as pool:
        res = [r for r in pool.imap_unordered(process_tile, tiles, chunksize=16) if r]
    dst = sqlite3.connect(dst_mbtiles)
    dst.execute("CREATE TABLE metadata (name text, value text)")
    dst.execute("CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob)")
    dst.execute("CREATE UNIQUE INDEX tile_index on tiles (zoom_level, tile_column, tile_row)")
    keep = {"minzoom", "maxzoom", "center", "format", "attribution"}
    dst.executemany("INSERT INTO metadata VALUES (?, ?)", [(k, v) for k, v in meta if k in keep])
    import json
    layers = [{"id": n, "fields": {"kind": "String", "type": "String", "sort_rank": "Number"}}
              for n in ("water", "landuse", "commercial", "hospital", "industrial", "residential")]
    dst.execute("INSERT INTO metadata VALUES ('json', ?)", (json.dumps({"vector_layers": layers}),))
    dst.executemany("INSERT INTO tiles VALUES (?, ?, ?, ?)", res)
    dst.commit()
    dst.close()
    return len(tiles), len(res)
