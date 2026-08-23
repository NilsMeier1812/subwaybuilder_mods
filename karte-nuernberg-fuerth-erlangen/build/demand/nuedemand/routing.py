"""
Fahrzeiten und -strecken für die Pendlerbeziehungen.

Subway Builder braucht je Beziehung ``drivingSeconds`` und
``drivingDistance`` — also wie lange die Fahrt mit dem Auto dauert. Das ist
die Referenz, gegen die der Spieler mit seinem Netz antritt.

Zwei Wege:

* ``estimate`` — Luftlinie mal Umwegfaktor, Geschwindigkeit abhängig von der
  Entfernung. Braucht nichts weiter und ist für einen ersten Durchlauf gut
  genug.
* ``OSRMClient`` — echte Routen von einem lokalen OSRM-Server. Genauer,
  braucht aber Docker und den Mittelfranken-Extrakt (siehe ../../ANLEITUNG.md).
"""

import json
import math
import urllib.error
import urllib.request

from .geo import haversine

# Umwegfaktor Luftlinie -> Straße. Für die gut erschlossene Region
# Nürnberg/Fürth/Erlangen passen etwa 1,25 (Hbf Nürnberg -> Hbf Fürth:
# 7,7 km Luftlinie, rund 9 km über die Straße).
DETOUR_FACTOR = 1.25


def speed_kmh(distance_m):
    """
    Mittlere Reisegeschwindigkeit in Abhängigkeit von der Streckenlänge.

    Kurze Fahrten sind langsam (Ampeln, Parkplatzsuche), lange Fahrten laufen
    über Ring und Autobahn. Nähert sich asymptotisch 80 km/h.

    Die Kurve ist auf freie Strecke geeicht — genau wie das Standardprofil von
    OSRM, damit geschätzte und geroutete Werte zusammenpassen:
    5 km ~ 35 km/h, 10 km ~ 48 km/h, 25 km ~ 68 km/h.
    """
    return 18.0 + 62.0 * (1.0 - math.exp(-distance_m / 15000.0))


def estimate(a, b, detour=DETOUR_FACTOR):
    """Schätzt (Sekunden, Meter) zwischen zwei (lon, lat)-Punkten."""
    straight = haversine(a, b)
    distance = straight * detour
    if distance < 1.0:
        return 60, 0  # gleicher Ort: Mindestwert, damit nichts durch 0 teilt
    seconds = distance / (speed_kmh(distance) / 3.6)
    return int(round(seconds)), int(round(distance))


class OSRMClient:
    """
    Minimaler Client für die ``/table``-Schnittstelle eines OSRM-Servers.

    Start des Servers (siehe ../../ANLEITUNG.md):

        docker run -t -i -p 5000:5000 -v "${PWD}:/data" \\
            ghcr.io/project-osrm/osrm-backend osrm-routed \\
            --algorithm mld /data/mittelfranken-latest.osrm
    """

    def __init__(self, base_url="http://127.0.0.1:5000", profile="driving",
                 chunk=90, timeout=120):
        self.base_url = base_url.rstrip("/")
        self.profile = profile
        self.chunk = chunk
        self.timeout = timeout

    def _request(self, url):
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def available(self):
        try:
            self._request(f"{self.base_url}/route/v1/{self.profile}/11.08,49.44;11.09,49.45")
            return True
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def table(self, sources, destinations):
        """
        Fahrzeit- und Streckenmatrix.

        ``sources`` und ``destinations`` sind Listen von (lon, lat).
        Rückgabe: ``(durations, distances)`` als verschachtelte Listen
        [len(sources)][len(destinations)] in Sekunden bzw. Metern.
        """
        durations = [[None] * len(destinations) for _ in sources]
        distances = [[None] * len(destinations) for _ in sources]

        for si in range(0, len(sources), self.chunk):
            src = sources[si : si + self.chunk]
            for di in range(0, len(destinations), self.chunk):
                dst = destinations[di : di + self.chunk]
                coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in src + dst)
                src_idx = ";".join(str(i) for i in range(len(src)))
                dst_idx = ";".join(str(i + len(src)) for i in range(len(dst)))
                url = (
                    f"{self.base_url}/table/v1/{self.profile}/{coords}"
                    f"?sources={src_idx}&destinations={dst_idx}"
                    f"&annotations=duration,distance"
                )
                data = self._request(url)
                if data.get("code") != "Ok":
                    raise RuntimeError(f"OSRM-Fehler: {data.get('message', data.get('code'))}")
                for i, row in enumerate(data.get("durations") or []):
                    for j, value in enumerate(row):
                        durations[si + i][di + j] = value
                for i, row in enumerate(data.get("distances") or []):
                    for j, value in enumerate(row):
                        distances[si + i][di + j] = value

        return durations, distances


def route_pairs(pairs, client=None, detour=DETOUR_FACTOR, progress=None):
    """
    Berechnet (Sekunden, Meter) für eine Liste von ((lon,lat), (lon,lat)).

    Ohne ``client`` wird geschätzt. Mit Client wird gruppenweise über
    ``/table`` gefragt und bei Lücken auf die Schätzung zurückgefallen.
    """
    if client is None:
        return [estimate(a, b, detour) for a, b in pairs]

    # Eindeutige Koordinaten sammeln, damit die Matrix klein bleibt
    index = {}
    for a, b in pairs:
        index.setdefault(a, len(index))
        index.setdefault(b, len(index))
    coords = [None] * len(index)
    for coord, i in index.items():
        coords[i] = coord

    durations, distances = client.table(coords, coords)
    if progress:
        progress(len(coords))

    out = []
    for a, b in pairs:
        i, j = index[a], index[b]
        dur = durations[i][j]
        dist = distances[i][j]
        if dur is None or dist is None:
            out.append(estimate(a, b, detour))
        else:
            out.append((int(round(dur)), int(round(dist))))
    return out
