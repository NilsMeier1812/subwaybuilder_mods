"""
Gebäude-Index für Subway Builder im gepackten Binärformat (buildings_index.bin).

Das Spiel nutzt den Index für Kollisionen beim Trassenbau: jedes Gebäude hat
eine Bounding Box, eine Fundamenttiefe und ein Polygon; ein Raster aus
~100-m-Zellen (0.0009° Breite) verweist auf die Gebäude, die es berührt.

Aufbau (little endian), Version 1:

    Header, 88 Byte:
      u32 magic 0x49424253 ("SBBI"), u8 version=1, u8 0, u16 0,
      u32 buildingCount, u32 cols, u32 rows, u32 ringCount, u32 coordCount,
      u32 cellCount, u32 cellRefCount, u32 0,
      f64 cellSize, f64 maxFoundationDepth,
      f64 minLon, f64 minLat, f64 maxLon, f64 maxLat
    f64[4]  × buildings     Bounding Box je Gebäude
    f32     × buildings     Fundamenttiefe (m)
    (auf 8 Byte ausrichten)
    u32     × (buildings+1) erster Ring je Gebäude
    u32     × (rings+1)     erste Koordinate je Ring
    (auf 8 Byte ausrichten)
    f64[2]  × coords        lon/lat
    u32     × (rows+1)      erste belegte Zelle je Zeile (CSR)
    u32     × cells         Spalte der Zelle
    u32     × (cells+1)     erster Verweis je Zelle
    u32     × cellRefs      Gebäude-IDs

Entspricht dem, was window.SubwayBuilderAPI.utils.buildings.encode() im
Spiel erzeugt; decode() unten liest es zur Kontrolle wieder ein.
"""

import math
import struct

import numpy as np

MAGIC = 0x49424253
VERSION = 1
HEADER = struct.Struct("<IBBHI7Id5d")
assert HEADER.size == 88
CELL = 0.0009


def _r5(v):
    return np.floor(np.asarray(v, dtype=np.float64) * 1e5 + 0.5) / 1e5


def encode(buildings):
    """buildings: Liste von (polygon_rings, foundation_depth).

    polygon_rings: Liste von Ringen, jeder Ring ein (n, 2)-Array lon/lat,
    geschlossen (erster == letzter Punkt), Außenring zuerst.
    """
    rings_all, ring_counts, bounds, depths = [], [], [], []
    for rings, depth in buildings:
        rr = [_r5(r) for r in rings if len(r) >= 4]
        if not rr:
            continue
        ext = rr[0]
        bounds.append((ext[:, 0].min(), ext[:, 1].min(), ext[:, 0].max(), ext[:, 1].max()))
        depths.append(float(depth))
        ring_counts.append(len(rr))
        rings_all.extend(rr)

    n = len(bounds)
    bounds = np.array(bounds, dtype=np.float64)
    depths = np.array(depths, dtype=np.float32)
    min_lon, min_lat = float(_r5(bounds[:, 0].min())), float(_r5(bounds[:, 1].min()))
    max_lon, max_lat = float(_r5(bounds[:, 2].max())), float(_r5(bounds[:, 3].max()))

    cs_lon = CELL / math.cos(math.radians((min_lat + max_lat) / 2))
    cols = math.ceil((max_lon - min_lon) / cs_lon)
    rows = math.ceil((max_lat - min_lat) / CELL)

    # Zellen je Gebäude (alle Zellen, die die Bounding Box berührt)
    c0 = np.clip(np.floor((bounds[:, 0] - min_lon) / cs_lon).astype(np.int64), 0, cols - 1)
    c1 = np.clip(np.floor((bounds[:, 2] - min_lon) / cs_lon).astype(np.int64), 0, cols - 1)
    r0 = np.clip(np.floor((bounds[:, 1] - min_lat) / CELL).astype(np.int64), 0, rows - 1)
    r1 = np.clip(np.floor((bounds[:, 3] - min_lat) / CELL).astype(np.int64), 0, rows - 1)
    keys, ids = [], []
    for b in range(n):
        for r in range(r0[b], r1[b] + 1):
            for c in range(c0[b], c1[b] + 1):
                keys.append(r * cols + c)
                ids.append(b)
    keys = np.array(keys, dtype=np.int64)
    ids = np.array(ids, dtype=np.uint32)
    order = np.lexsort((ids, keys))
    keys, ids = keys[order], ids[order]
    ukeys, starts = np.unique(keys, return_index=True)
    cell_rows = (ukeys // cols).astype(np.int64)
    cell_cols = (ukeys % cols).astype(np.uint32)
    cell_offsets = np.append(starts, len(ids)).astype(np.uint32)
    row_starts = np.searchsorted(cell_rows, np.arange(rows + 1), side="left").astype(np.uint32)

    ring_offsets = np.concatenate([[0], np.cumsum(ring_counts)]).astype(np.uint32)
    coord_counts = [len(r) for r in rings_all]
    coord_offsets = np.concatenate([[0], np.cumsum(coord_counts)]).astype(np.uint32)
    coords = np.concatenate(rings_all).astype(np.float64)

    def pad8(b):
        return b + b"\0" * ((-len(b)) % 8)

    head = HEADER.pack(MAGIC, VERSION, 0, 0, n, cols, rows, len(rings_all), len(coords),
                       len(ukeys), len(ids), 0, CELL, float(depths.max()),
                       min_lon, min_lat, max_lon, max_lat)
    body = pad8(head + bounds.astype("<f8").tobytes() + depths.astype("<f4").tobytes())
    body = pad8(body + ring_offsets.astype("<u4").tobytes() + coord_offsets.astype("<u4").tobytes())
    body += coords.astype("<f8").tobytes()
    body += row_starts.astype("<u4").tobytes() + cell_cols.astype("<u4").tobytes()
    body += cell_offsets.astype("<u4").tobytes() + ids.astype("<u4").tobytes()
    return body


def encode_json(buildings):
    """Älteres JSON-Format (buildings_index.json), das Spielversionen bis 1.3.0
    lesen und das Railyard verlangt, wenn es die Spielversion nicht erkennt.

    {"cs": 0.0009, "bbox": [...], "grid": [cols, rows],
     "cells": [[col, row, id, id, …], …],
     "buildings": [{"b": bbox, "f": Fundamenttiefe, "p": Ringe}, …],
     "stats": {"count": n, "maxDepth": d}}

    Jedes Gebäude steht in genau einer Zelle (der seines Schwerpunkts).
    """
    out, cent = [], []
    for rings, depth in buildings:
        rr = [_r5(r) for r in rings if len(r) >= 4]
        if not rr:
            continue
        ext = rr[0]
        out.append({"b": [float(ext[:, 0].min()), float(ext[:, 1].min()),
                          float(ext[:, 0].max()), float(ext[:, 1].max())],
                    "f": int(depth), "p": [r.tolist() for r in rr]})
        cent.append(ext[:-1].mean(axis=0))
    cent = np.array(cent)
    b = np.array([o["b"] for o in out])
    min_lon, min_lat, max_lon, max_lat = b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()
    cs_x = CELL / math.cos(math.radians((min_lat + max_lat) / 2))
    cols = math.ceil((max_lon - min_lon) / cs_x)
    rows = math.ceil((max_lat - min_lat) / CELL)
    gx = np.clip(((cent[:, 0] - min_lon) / cs_x).astype(int), 0, cols - 1)
    gy = np.clip(((cent[:, 1] - min_lat) / CELL).astype(int), 0, rows - 1)
    cells = {}
    for i, k in enumerate(zip(gx.tolist(), gy.tolist())):
        cells.setdefault(k, []).append(i)
    return {"cs": CELL, "bbox": [float(min_lon), float(min_lat), float(max_lon), float(max_lat)],
            "grid": [cols + 1, rows + 1],
            "cells": [[x, y] + ids for (x, y), ids in cells.items()],
            "buildings": out,
            "stats": {"count": len(out), "maxDepth": max(o["f"] for o in out)}}


def decode(buf):
    """Liest den Index wieder ein und prüft die innere Konsistenz."""
    (magic, ver, _, _, n, cols, rows, nr, nc, ncell, nref, _,
     cs, maxd, x0, y0, x1, y1) = HEADER.unpack_from(buf, 0)
    assert magic == MAGIC and ver == VERSION, "falsche Kennung/Version"
    o = 88
    bounds = np.frombuffer(buf, "<f8", n * 4, o).reshape(n, 4); o += n * 32
    depths = np.frombuffer(buf, "<f4", n, o); o += n * 4
    o = (o + 7) & ~7
    ring_off = np.frombuffer(buf, "<u4", n + 1, o); o += (n + 1) * 4
    coord_off = np.frombuffer(buf, "<u4", nr + 1, o); o += (nr + 1) * 4
    o = (o + 7) & ~7
    coords = np.frombuffer(buf, "<f8", nc * 2, o).reshape(nc, 2); o += nc * 16
    row_starts = np.frombuffer(buf, "<u4", rows + 1, o); o += (rows + 1) * 4
    cell_cols = np.frombuffer(buf, "<u4", ncell, o); o += ncell * 4
    cell_off = np.frombuffer(buf, "<u4", ncell + 1, o); o += (ncell + 1) * 4
    ids = np.frombuffer(buf, "<u4", nref, o); o += nref * 4
    assert o == len(buf), f"Länge passt nicht: {o} != {len(buf)}"
    assert ring_off[-1] == nr and coord_off[-1] == nc and cell_off[-1] == nref
    assert row_starts[-1] == ncell and (np.diff(row_starts.astype(np.int64)) >= 0).all()
    assert ids.max() < n and cell_cols.max() < cols
    assert (depths > 0).all()
    return dict(count=n, cols=cols, rows=rows, rings=nr, coords=nc, cells=ncell,
                refs=nref, cellSize=cs, maxDepth=maxd, bbox=(x0, y0, x1, y1))
