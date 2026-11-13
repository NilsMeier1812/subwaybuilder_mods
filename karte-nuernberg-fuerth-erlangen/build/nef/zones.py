"""Gemeinden im Kartenausschnitt und ihre amtlichen Pendlerzahlen."""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from nef.common import BBOX, RAW, REGION

YEAR = REGION["sources"]["pendleratlas_year"]
PENDLER = RAW / "pendler"


def read_pa(name):
    """CSV aus dem Pendleratlas lesen (Semikolon, Latin-1, 'x' = gesperrt)."""
    df = pd.read_csv(PENDLER / f"{YEAR}_{name}_L09.csv", sep=";", dtype=str, encoding="latin1")
    for c in df.columns:
        if c.startswith("ARS"):
            continue
        df[c] = pd.to_numeric(df[c].str.replace(",", "."), errors="coerce")
    return df


def load_zones():
    """Gemeinden, die den Ausschnitt berühren, mit Erwerbstätigenzahlen.

    Spalten: ARS, GEN, geometry (EPSG:25832), AUSP, EIP, IOP, R (Erwerbstätige
    am Wohnort), W (am Arbeitsort). Gemeindefreie Gebiete (Forste) haben keine
    Zahlen und werden später der nächsten Gemeinde zugeschlagen.
    """
    g = gpd.read_file(RAW / "vg250_gemeinden_mfr.gpkg")
    bb = gpd.GeoSeries([box(*BBOX)], crs=4326).to_crs(g.crs).iloc[0]
    g = g[g.intersects(bb)].copy()
    ez = read_pa("EZ")[["ARS", "AUSP", "EIP", "IOP", "Bev"]]
    g = g.merge(ez, on="ARS", how="left")
    g["R"] = g["AUSP"] + g["IOP"]
    g["W"] = g["EIP"] + g["IOP"]
    g["has_data"] = g["R"].notna()
    return g.reset_index(drop=True)


def assign_zone(points_xy, zones):
    """Jedem Punkt (EPSG:25832) die Gemeinde mit Daten zuordnen.

    Punkte in gemeindefreien Gebieten gehen an die nächstgelegene Gemeinde.
    """
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(points_xy[:, 0], points_xy[:, 1]), crs=zones.crs)
    real = zones[zones["has_data"]][["ARS", "geometry"]]
    hit = gpd.sjoin(pts, real, how="left", predicate="within")
    hit = hit[~hit.index.duplicated()]
    miss = hit["ARS"].isna().values
    if miss.any():
        near = gpd.sjoin_nearest(pts[miss], real, how="left")
        near = near[~near.index.duplicated()]
        hit.loc[miss, "ARS"] = near["ARS"].values
    return hit["ARS"].values
