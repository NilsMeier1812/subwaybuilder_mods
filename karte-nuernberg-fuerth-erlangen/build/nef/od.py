"""
Pendlermatrix Gemeinde -> Gemeinde aus der Pendlerrechnung der Länder.

Der Pendleratlas veröffentlicht je bayerischer Gemeinde

  * Innerortspendler (IOP), Aus- und Einpendler insgesamt (AUSP/EIP) und
  * die zehn stärksten Aus- und Einpendlerbeziehungen mit genauer Zahl.

Diese Werte werden fest übernommen. Der Rest (kleinere Beziehungen) wird per
doppelt beschränktem Gravitationsmodell (IPF) über alle 2 056 bayerischen
Gemeinden geschätzt, so dass jede Gemeinde ihre amtlichen Aus- und
Einpendlersummen exakt behält. Ein Sammelknoten nimmt Ströme über die
Landesgrenze auf.
"""

import json

import numpy as np
import pandas as pd

from nef.common import RAW, log
from nef.zones import PENDLER, YEAR, read_pa

OUTSIDE = "AUSSERHALB"
DECAY_KM = 18.0     # Abklingweite für die kleinen Restströme
OFFSET_KM = 3.0


def _centroids():
    d = json.loads((PENDLER / f"gemeinden_{YEAR}.json").read_text(encoding="utf-8"))
    return {f["ars"]: (f["x"], f["y"]) for f in d["features"]}


def gemeinde_matrix():
    """Rückgabe: (codes, T) mit T[i, j] = Erwerbstätige mit Wohnort i, Arbeitsort j."""
    ez = read_pa("EZ").set_index("ARS")
    vf = read_pa("Verfl")
    codes = list(ez.index) + [OUTSIDE]
    idx = {c: i for i, c in enumerate(codes)}
    n = len(codes)
    xy = _centroids()

    known = np.full((n, n), np.nan)
    np.fill_diagonal(known[:-1, :-1], ez["IOP"].fillna(0).values)
    for _, r in vf.iterrows():
        g = r["ARS"]
        if g not in idx:
            continue
        # Auspendler: g -> ARS_AO, Einpendler: ARS_WO -> g
        for other, val, out in ((r["ARS_AO"], r["AUSP_AO"], True), (r["ARS_WO"], r["EIP_WO"], False)):
            if pd.isna(val) or not isinstance(other, str):
                continue
            o = idx.get(other, idx[OUTSIDE])
            i, j = (idx[g], o) if out else (o, idx[g])
            if i == j:
                continue
            if o == idx[OUTSIDE]:
                # mehrere Ziele außerhalb Bayerns aufsummieren
                known[i, j] = np.nansum([known[i, j], val])
            else:
                known[i, j] = np.nanmax([known[i, j], val])

    ausp = np.append(ez["AUSP"].fillna(0).values, 0.0)
    eip = np.append(ez["EIP"].fillna(0).values, 0.0)
    kn = np.nan_to_num(known)
    off = kn.copy()
    np.fill_diagonal(off, 0)
    res_out = np.maximum(ausp - off.sum(1), 0)
    res_in = np.maximum(eip - off.sum(0), 0)
    res_out[-1] = res_in[-1] = 0
    # Sammelknoten gleicht die Summen aus (Ströme über die Landesgrenze)
    gap = res_out.sum() - res_in.sum()
    res_in[-1] = max(gap, 0) + 0.02 * res_out.sum()
    res_out[-1] = max(-gap, 0) + 0.02 * res_out.sum()

    pts = np.array([xy.get(c, (np.nan, np.nan)) for c in codes], dtype=float)
    # Web-Mercator -> km (Maßstab bei ~49° Breite)
    pts = pts * np.cos(np.radians(49.4)) / 1000
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    d[-1, :] = d[:, -1] = 200.0
    d = np.nan_to_num(d, nan=200.0)
    seed = np.exp(-d / DECAY_KM) / (d + OFFSET_KM) ** 1.0
    seed[~np.isnan(known)] = 0          # feste Werte nicht neu verteilen
    np.fill_diagonal(seed, 0)

    m = seed * res_out[:, None]
    for it in range(200):
        cs = m.sum(0)
        m *= np.divide(res_in, cs, out=np.zeros_like(cs), where=cs > 0)[None, :]
        rs = m.sum(1)
        m *= np.divide(res_out, rs, out=np.zeros_like(rs), where=rs > 0)[:, None]
        err = np.abs(m.sum(0) - res_in).sum() / max(res_in.sum(), 1)
        if err < 1e-4:
            break
    log(f"  Gemeindematrix: {len(codes) - 1} Gemeinden, IPF {it + 1} Runden, Restfehler {err:.1e}")
    T = kn + m
    return codes, T
