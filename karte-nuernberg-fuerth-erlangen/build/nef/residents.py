"""
Wohnbevölkerung aus dem Zensus 2022 (100-m-Gitter, EPSG:3035).

Als Herkunftsseite der Pendler zählen die 18- bis 64-Jährigen je Gitterzelle.
Wo das Alter aus Datenschutzgründen gesperrt ist ("–", kleine Zellen),
wird der Anteil der Gemeinde angesetzt.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from nef.common import RAW, log

Z = RAW / "zensus"


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(r"[^\d]", "", regex=True).replace("", np.nan), errors="coerce")


def load_cells(zones):
    """Alle 100-m-Zellen in den Gemeinden des Ausschnitts (ganze Gemeindeflächen).

    Rückgabe: DataFrame mit x, y (EPSG:25832), lon, lat, pop, wa (18–64).
    """
    xmin, ymin, xmax, ymax = zones.to_crs(3035).total_bounds
    log("Zensus-Gitter lesen …")
    chunks = []
    for ch in pd.read_csv(Z / "bevoelkerung_100m.csv", sep=";", dtype=str, chunksize=1_000_000):
        x = pd.to_numeric(ch["x_mp_100m"]); y = pd.to_numeric(ch["y_mp_100m"])
        m = (x >= xmin - 100) & (x <= xmax + 100) & (y >= ymin - 100) & (y <= ymax + 100)
        if m.any():
            chunks.append(pd.DataFrame({"id": ch["GITTER_ID_100m"][m], "x3035": x[m], "y3035": y[m],
                                        "pop": _num(ch["Einwohner"][m])}))
    cells = pd.concat(chunks, ignore_index=True)
    ages = []
    for ch in pd.read_csv(Z / "alter5_100m.csv", sep=";", dtype=str, chunksize=1_000_000):
        ch = ch[ch["GITTER_ID_100m"].isin(cells["id"])]
        if len(ch):
            wa = _num(ch["a18bis29"]) + _num(ch["a30bis49"]) + _num(ch["a50bis64"])
            ages.append(pd.DataFrame({"id": ch["GITTER_ID_100m"], "wa_raw": wa,
                                      "pop_age": _num(ch["Insgesamt_Bevoelkerung"])}))
    cells = cells.merge(pd.concat(ages), on="id", how="left")
    cells = cells[cells["pop"] > 0].reset_index(drop=True)

    g = gpd.GeoSeries(gpd.points_from_xy(cells["x3035"], cells["y3035"]), crs=3035)
    utm = g.to_crs(zones.crs)
    wgs = g.to_crs(4326)
    cells["x"], cells["y"] = utm.x.values, utm.y.values
    cells["lon"], cells["lat"] = wgs.x.values, wgs.y.values
    log(f"  {len(cells)} bewohnte Zellen, {int(cells['pop'].sum())} Einwohner")
    return cells


def working_age(cells):
    """18–64-Jährige je Zelle; gesperrte Zellen mit dem Gemeindeanteil auffüllen."""
    known = cells["wa_raw"].notna() & (cells["pop_age"] > 0)
    share = (cells[known].groupby("ARS")["wa_raw"].sum() / cells[known].groupby("ARS")["pop_age"].sum())
    fallback = cells["ARS"].map(share).fillna(share.median() if len(share) else 0.62)
    wa = cells["wa_raw"].where(known, cells["pop"] * fallback)
    # Gesperrte Einzelwerte können die Gesamtzahl übersteigen -> deckeln
    return np.minimum(wa.fillna(0).values, cells["pop"].values)
