"""
ETRS89 / LAEA Europe (EPSG:3035) <-> WGS84.

Das Zensus-2022-Gitter liegt im INSPIRE-Gitter, also in EPSG:3035. Um die
Zellen auf Lon/Lat für Subway Builder zu bringen, brauchen wir die
Rückprojektion. pyproj wäre der bequeme Weg, ist aber eine schwere
Abhängigkeit — die Formeln (Snyder, "Map Projections: A Working Manual",
Lambert Azimuthal Equal-Area, schiefachsig) sind kurz genug für die Standard-
bibliothek.

EPSG:3035:
    Ellipsoid GRS80, lat_0 = 52° N, lon_0 = 10° E,
    false easting 4 321 000 m, false northing 3 210 000 m
"""

import math

# GRS80
A = 6378137.0
F = 1.0 / 298.257222101
E2 = F * (2 - F)
E = math.sqrt(E2)

LAT_0 = math.radians(52.0)
LON_0 = math.radians(10.0)
X_0 = 4321000.0
Y_0 = 3210000.0


def _q(sin_phi):
    """Authalischer Hilfsterm q(phi) nach Snyder (3-12)."""
    if E < 1e-12:
        return 2.0 * sin_phi
    t = E * sin_phi
    return (1 - E2) * (
        sin_phi / (1 - t * t) - (1.0 / (2 * E)) * math.log((1 - t) / (1 + t))
    )


_QP = _q(1.0)
_RQ = A * math.sqrt(_QP / 2.0)
_BETA_0 = math.asin(_q(math.sin(LAT_0)) / _QP)
_D = (
    A
    * math.cos(LAT_0)
    / (math.sqrt(1 - E2 * math.sin(LAT_0) ** 2) * _RQ * math.cos(_BETA_0))
)

# Reihe für die Rückrechnung authalische -> geodätische Breite (Snyder 3-18)
_C1 = E2 / 3.0 + 31 * E2**2 / 180.0 + 517 * E2**3 / 5040.0
_C2 = 23 * E2**2 / 360.0 + 251 * E2**3 / 3780.0
_C3 = 761 * E2**3 / 45360.0


def forward(lon, lat):
    """WGS84 (Grad) -> EPSG:3035 (Meter). Gibt (x, y) zurück."""
    lam = math.radians(lon)
    phi = math.radians(lat)

    beta = math.asin(_q(math.sin(phi)) / _QP)
    dlam = lam - LON_0

    denom = 1 + math.sin(_BETA_0) * math.sin(beta) + math.cos(_BETA_0) * math.cos(
        beta
    ) * math.cos(dlam)
    if denom <= 0:
        raise ValueError("Punkt liegt auf der Gegenseite der Projektion")
    b = _RQ * math.sqrt(2.0 / denom)

    x = b * _D * math.cos(beta) * math.sin(dlam)
    y = (b / _D) * (
        math.cos(_BETA_0) * math.sin(beta)
        - math.sin(_BETA_0) * math.cos(beta) * math.cos(dlam)
    )
    return x + X_0, y + Y_0


def inverse(x, y):
    """EPSG:3035 (Meter) -> WGS84 (Grad). Gibt (lon, lat) zurück."""
    x = x - X_0
    y = y - Y_0

    xd = x / _D
    yd = _D * y
    rho = math.hypot(xd, yd)
    if rho < 1e-9:
        beta = _BETA_0
        lam = LON_0
    else:
        arg = rho / (2.0 * _RQ)
        arg = max(-1.0, min(1.0, arg))
        c = 2.0 * math.asin(arg)
        sin_c, cos_c = math.sin(c), math.cos(c)

        sin_beta = cos_c * math.sin(_BETA_0) + (yd * sin_c * math.cos(_BETA_0)) / rho
        sin_beta = max(-1.0, min(1.0, sin_beta))
        beta = math.asin(sin_beta)

        lam = LON_0 + math.atan2(
            x * sin_c,
            _D * rho * cos_c * math.cos(_BETA_0) - _D * _D * y * sin_c * math.sin(_BETA_0),
        )

    phi = (
        beta
        + _C1 * math.sin(2 * beta)
        + _C2 * math.sin(4 * beta)
        + _C3 * math.sin(6 * beta)
    )
    return math.degrees(lam), math.degrees(phi)


def parse_grid_id(grid_id):
    """
    Zellmittelpunkt aus einer INSPIRE-Gitter-ID lesen.

    Die Zensus-Dateien führen IDs wie ``CRS3035RES100mN2691700E4341100``.
    N/E bezeichnen die *südwestliche* Ecke der Zelle; wir liefern den
    Mittelpunkt in EPSG:3035 zurück.

    Gibt (x, y, zellgroesse_m) zurück.
    """
    s = grid_id.strip().upper()
    try:
        res_part = s.split("RES", 1)[1]
        size_str = res_part.split("M", 1)[0]
        size = float(size_str)
        rest = res_part.split("M", 1)[1]
        n_str, e_str = rest.split("N", 1)[1].split("E", 1)
        north = float(n_str)
        east = float(e_str)
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Unlesbare Gitter-ID: {grid_id!r}") from exc

    return east + size / 2.0, north + size / 2.0, size


def grid_id_to_lonlat(grid_id):
    """INSPIRE-Gitter-ID -> (lon, lat) des Zellmittelpunkts."""
    x, y, _ = parse_grid_id(grid_id)
    return inverse(x, y)
