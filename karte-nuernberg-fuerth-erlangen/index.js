/**
 * Karte Nürnberg / Fürth / Erlangen — Subway Builder Mod
 * ------------------------------------------------------
 * Registriert die Metropolregion als spielbare Stadt (Code "NUE") und sagt
 * dem Spiel, wo die Kartendaten liegen.
 *
 * Der Mod bringt die Daten NICHT mit — die sind mehrere hundert MB groß und
 * gehören nicht in ein Git-Repo. Sie werden einmalig lokal erzeugt
 * (siehe build/README bzw. build/mapgen_nue.py) und dann über einen kleinen
 * HTTP-Server ausgeliefert:
 *
 *     cd NUE && python3 -m http.server 8080
 *
 * Erwartete Dateien unter BASE_URL:
 *
 *     NUE.pmtiles                    Vektorkacheln (Gebäude, Straßen, Wasser, Labels)
 *     NUE_foundations.pmtiles        Fundament-Layer (Gebäudetiefen)
 *     buildings_index.json.gz        Gebäude-Index für Kollisionen
 *       oder buildings_index.bin     (Binärvariante, siehe BUILDINGS_INDEX)
 *     roads.geojson.gz               Straßennetz
 *     runways_taxiways.geojson.gz    Start-/Rollbahnen (Flughafen Nürnberg)
 *     demand_data.json.gz            Nachfrage: Wohn-/Arbeitspunkte + Pendlerbeziehungen
 *
 * Der Ablauf folgt der offiziellen Doku (Guides → Custom Cities):
 *   1. api.registerCity(...)              Stadt anlegen
 *   2. api.map.setTileURLOverride(...)    Kachelquelle setzen
 *   3. api.cities.setCityDataFiles(...)   Datendateien setzen
 */

(function () {
  "use strict";

  const MOD_ID = "com.nilsmeier.karte-nuernberg";
  const MOD_VERSION = "0.1.0";
  const TAG = "[Karte NUE]";

  // ==========================================================================
  //  KONFIGURATION
  // ==========================================================================

  // Wo liegen die erzeugten Kartendaten? Ohne Schrägstrich am Ende.
  // Lokaler Python-Server: "http://127.0.0.1:8080"
  const BASE_URL = "http://127.0.0.1:8080";

  const CITY_CODE = "NUE"; // IATA-Code Flughafen Nürnberg
  const MAX_ZOOM = 15; // muss zum maxzoom aus mapgen_nue.py passen

  // depot erzeugt den Gebäude-Index in zwei Formaten. Die offizielle Doku
  // zeigt die gzip-JSON-Variante; die Berlin-Karte im Railyard liefert die
  // deutlich kleinere Binärvariante aus. Lädt das Spiel die eine nicht,
  // hier auf die andere umstellen.
  const BUILDINGS_INDEX = "buildings_index.json.gz"; // Alternative: "buildings_index.bin"

  // Bounding Box der Karte: [min_lon, min_lat, max_lon, max_lat]
  // Deckt ab: Erlangen (N), Nürnberg-Katzwang/Flughafen (S), Zirndorf/Stein (W),
  // Lauf a. d. Pegnitz / Röthenbach (O). Muss identisch zu mapgen_nue.py sein.
  const BBOX = [10.85, 49.32, 11.28, 49.66];

  // Einwohner im Kartenausschnitt (Nürnberg ~545k, Fürth ~130k, Erlangen ~117k
  // plus Umland). Nach dem Bau der Nachfragedaten auf die tatsächliche Summe
  // aus demand_data.json setzen.
  const POPULATION = 880000;

  // ==========================================================================

  const api = window.SubwayBuilderAPI;
  if (!api) {
    console.error(`${TAG} SubwayBuilderAPI nicht gefunden – Mod wird nicht geladen.`);
    return;
  }
  console.log(`${TAG} v${MOD_VERSION} | API v${api.version}`);

  // --- 1. Stadt registrieren ------------------------------------------------
  api.registerCity({
    name: "Nürnberg",
    code: CITY_CODE,
    description:
      "Metropolregion Nürnberg – Fürth – Erlangen. Drei gewachsene Zentren, " +
      "ein durchgehend besiedeltes Band entlang der Pegnitz und Regnitz, " +
      "dazu Flughafen, Messe und die FAU auf zwei Standorten.",
    population: POPULATION,
    initialViewState: {
      // Nürnberg Hauptbahnhof
      latitude: 49.4455,
      longitude: 11.0823,
      zoom: 12.5,
      bearing: 0,
    },
  });

  // --- 2. Kachelquelle ------------------------------------------------------
  api.map.setTileURLOverride({
    cityCode: CITY_CODE,
    tilesUrl: `${BASE_URL}/NUE.pmtiles`,
    foundationTilesUrl: `${BASE_URL}/NUE_foundations.pmtiles`,
    maxZoom: MAX_ZOOM,
  });

  // --- 3. Datendateien ------------------------------------------------------
  api.cities.setCityDataFiles(CITY_CODE, {
    buildingsIndex: `${BASE_URL}/${BUILDINGS_INDEX}`,
    demandData: `${BASE_URL}/demand_data.json.gz`,
    roads: `${BASE_URL}/roads.geojson.gz`,
    runwaysTaxiways: `${BASE_URL}/runways_taxiways.geojson.gz`,
    // Binnenland ohne Meer — ocean_depth_index wird nicht gebraucht.
    // oceanDepthIndex: `${BASE_URL}/ocean_depth_index.json.gz`,
  });

  console.log(`${TAG} Stadt "${CITY_CODE}" registriert, Daten von ${BASE_URL}`);
  console.log(`${TAG} BBox ${BBOX.join(", ")}`);
})();
