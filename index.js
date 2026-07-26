/**
 * Bahnübergang-Limit Override
 * ----------------------------
 * Subway Builder Mod mit zwei Funktionen:
 *
 *  1. Überschreibt das Limit "Züge pro Stunde" (tph) an Bahnübergängen.
 *  2. Erlaubt Zugtypen, die das im Spiel nicht dürfen (Heavy Metro,
 *     Light Metro), Straßen ebenerdig zu kreuzen.
 *
 * Hintergrund: Jeder Zugtyp hat die Eigenschaft `allowAtGradeRoadCrossing`
 * (Alias `canCrossRoads`), die bestimmt, ob er Straßen ebenerdig kreuzen darf.
 * Bei Heavy/Light Metro steht sie auf `false`. Zusätzlich gibt es
 * `gradeCrossingTphLimit` — eine Obergrenze (kombinierte Fahrtrichtungen,
 * Züge/Stunde) je Straßenklasse:
 *
 *     gradeCrossingTphLimit: { highway: null, major: 6, medium: 8, minor: 10 }
 *
 * `null` bedeutet: an dieser Straßenklasse ist ein ebenerdiger Übergang
 * verboten. Der Mod liest beides zur Laufzeit aus und ersetzt es über
 * `api.trains.modifyTrainType()`.
 *
 * Alle Werte werden direkt im Spiel über Zahlenfelder eingegeben
 * (Einstellungen-Menü bzw. schwebendes Panel) und dauerhaft gespeichert.
 */

(function () {
  "use strict";

  const MOD_ID = "com.nilsmeier.crossing-tph-override";
  const MOD_VERSION = "3.2.0";
  const TAG = "[BahnübergangTPH]";
  const STORAGE_KEY = "limits";

  // ==========================================================================
  //  STARTWERTE  —  Züge pro Stunde je Straßenklasse
  //  (im Spiel änderbar; gespeicherte Werte haben Vorrang)
  //  null oder 0 = ebenerdiger Übergang an dieser Straßenklasse verboten
  // ==========================================================================
  const LIMITS = {
    highway: null, // Autobahn / Schnellstraße (Vanilla: verboten)
    major: 30, // Hauptstraße (Vanilla: 6)
    medium: 40, // Sammelstraße (Vanilla: 8)
    minor: 60, // Nebenstraße (Vanilla: 10)
  };

  const OPTIONS = {
    // Heavy Metro und Light Metro dürfen Straßen ebenerdig kreuzen.
    // Im Vanilla-Spiel ist das verboten.
    enableMetroCrossing: true,

    // Jeder Zugtyp darf Straßen ebenerdig kreuzen (auch Intercity o. Ä.).
    enableCrossingForAllTrains: false,
  };

  // Zugtypen, die per "enableMetroCrossing" freigeschaltet werden.
  const METRO_TRAIN_IDS = ["heavy-metro", "light-metro"];

  // Zugtypen, die im Vanilla-Spiel Straßen kreuzen dürfen (Referenz für die
  // Diagnose und für die Erkennung des Originalzustands).
  const VANILLA_CROSSING_IDS = ["s-train", "regional", "tram", "commuter-rail"];

  /**
   * Bekannter Vanilla-Zustand für Zugtypen, die der Mod verändert.
   * Nötig, weil der Mod beim Neuladen (Strg+Umschalt+R) sonst den bereits
   * veränderten Zustand als "Original" sichern würde – dann könnte
   * "Zurücksetzen" die echten Werte nicht mehr herstellen.
   */
  const VANILLA_KNOWN = {
    "heavy-metro": { allow: false, limit: undefined },
    "light-metro": { allow: false, limit: undefined },
  };

  // Anzeigenamen der Straßenklassen für die Oberfläche
  const ROAD_LABELS = {
    highway: "Autobahn / Schnellstraße",
    major: "Hauptstraße",
    medium: "Sammelstraße",
    minor: "Nebenstraße",
  };

  // Reihenfolge in der Oberfläche
  const ROAD_ORDER = ["highway", "major", "medium", "minor"];

  // Vanilla-Standardwerte als Rückfallebene
  const DEFAULT_LIMIT = { highway: null, major: 6, medium: 8, minor: 10 };

  const api = window.SubwayBuilderAPI;
  if (!api) {
    console.error(`${TAG} SubwayBuilderAPI nicht gefunden – Mod wird nicht geladen.`);
    return;
  }

  console.log(`${TAG} v${MOD_VERSION} | API v${api.version}`);

  /**
   * Originalzustand je Zugtyp, damit "Zurücksetzen" die Vanilla-Werte
   * wiederherstellen kann. Wird beim allerersten Auslesen befüllt.
   * Form: { limitKey, limit, allowKey, allow, hasAliasKey }
   */
  const originals = {};

  /** Aus api.storage geladene Originalwerte (überleben das Mod-Neuladen). */
  let storedOriginals = null;
  let newOriginalsToPersist = false;

  // --------------------------------------------------------------------------
  //  Hilfsfunktionen
  // --------------------------------------------------------------------------

  /**
   * Findet den Namen der Crossing-Limit-Eigenschaft an einem Zugtyp.
   * Standardname ist `gradeCrossingTphLimit`, wir tolerieren aber auch leichte
   * Schreibvarianten, damit der Mod robust gegenüber Spielversionen bleibt.
   */
  function resolveLimitKey(trainType) {
    const known = [
      "gradeCrossingTphLimit",
      "gradeCrossingTPHLimit",
      "gradeCrossingTphLimits",
    ];
    for (const k of known) {
      if (trainType && Object.prototype.hasOwnProperty.call(trainType, k)) return k;
    }
    if (trainType) {
      for (const k of Object.keys(trainType)) {
        if (/grade.*cross.*tph|crossing.*tph/i.test(k)) return k;
      }
    }
    return "gradeCrossingTphLimit";
  }

  /**
   * Findet den Namen der "darf kreuzen"-Eigenschaft. Offiziell heißt sie
   * `allowAtGradeRoadCrossing`, ältere/andere Builds nutzen `canCrossRoads`.
   */
  function resolveAllowKey(trainType) {
    if (trainType && Object.prototype.hasOwnProperty.call(trainType, "allowAtGradeRoadCrossing")) {
      return "allowAtGradeRoadCrossing";
    }
    if (trainType && Object.prototype.hasOwnProperty.call(trainType, "canCrossRoads")) {
      return "canCrossRoads";
    }
    return "allowAtGradeRoadCrossing";
  }

  function isLimitObject(v) {
    return v && typeof v === "object" && !Array.isArray(v);
  }

  /** Wandelt eine Eingabe in einen Limit-Wert (Zahl oder null). */
  function normalizeValue(raw) {
    if (raw === null || raw === undefined || raw === "") return null;
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return null; // 0 / ungültig = gesperrt
    return Math.round(n);
  }

  /**
   * Sichert den Originalzustand eines Zugtyps genau einmal.
   *
   * Wichtig: Beim Mod-Neuladen sind die Zugtypen eventuell schon verändert.
   * Deshalb gilt die Reihenfolge:
   *   1. bereits gespeicherter Originalzustand (aus api.storage)
   *   2. bekannter Vanilla-Zustand (VANILLA_KNOWN)
   *   3. aktueller Zustand des Zugtyps
   */
  function captureOriginal(id, trainType) {
    if (id in originals) return originals[id];

    const limitKey = resolveLimitKey(trainType);
    const allowKey = resolveAllowKey(trainType);
    const hasAliasKey =
      trainType && Object.prototype.hasOwnProperty.call(trainType, "canCrossRoads");

    // 1. Aus dem Speicher wiederhergestellt?
    if (storedOriginals && storedOriginals[id]) {
      const s = storedOriginals[id];
      originals[id] = {
        limitKey: s.limitKey || limitKey,
        allowKey: s.allowKey || allowKey,
        limit: s.limit,
        allow: s.allow,
        hasAliasKey: s.hasAliasKey === undefined ? hasAliasKey : s.hasAliasKey,
        source: "storage",
      };
      return originals[id];
    }

    // 2. Bekannter Vanilla-Zustand für die vom Mod veränderten Zugtypen.
    if (VANILLA_KNOWN[id]) {
      originals[id] = {
        limitKey: limitKey,
        allowKey: allowKey,
        limit: VANILLA_KNOWN[id].limit,
        allow: VANILLA_KNOWN[id].allow,
        hasAliasKey: hasAliasKey,
        source: "known",
      };
      newOriginalsToPersist = true;
      return originals[id];
    }

    // 3. Aktueller Zustand (unveränderter Zugtyp).
    const limit = trainType ? trainType[limitKey] : undefined;
    originals[id] = {
      limitKey: limitKey,
      allowKey: allowKey,
      limit: isLimitObject(limit) ? Object.assign({}, limit) : limit,
      allow: trainType ? trainType[allowKey] : undefined,
      hasAliasKey: hasAliasKey,
      source: "live",
    };
    newOriginalsToPersist = true;
    return originals[id];
  }

  /** Durfte dieser Zugtyp im Original bereits Straßen kreuzen? */
  function crossedOriginally(orig) {
    return orig.allow === true || isLimitObject(orig.limit);
  }

  /** Soll dieser Zugtyp nach aktueller Konfiguration kreuzen dürfen? */
  function shouldCross(id, orig) {
    if (crossedOriginally(orig)) return true;
    if (OPTIONS.enableCrossingForAllTrains) return true;
    if (OPTIONS.enableMetroCrossing && METRO_TRAIN_IDS.indexOf(id) !== -1) return true;
    return false;
  }

  // --------------------------------------------------------------------------
  //  Kernlogik
  // --------------------------------------------------------------------------

  let lastSummary = [];

  /**
   * Wendet die aktuelle Konfiguration auf alle passenden Zugtypen an.
   * @param {string} reason  Nur für die Konsolenausgabe.
   * @param {boolean} restoreOriginal  true = Vanilla-Zustand wiederherstellen.
   */
  function applyOverrides(reason, restoreOriginal) {
    let trainTypes;
    try {
      trainTypes = api.trains.getTrainTypes();
    } catch (err) {
      console.error(`${TAG} Konnte Zugtypen nicht laden:`, err);
      return 0;
    }
    if (!trainTypes) return 0;

    const summary = [];
    let changed = 0;

    for (const [id, trainType] of Object.entries(trainTypes)) {
      const orig = captureOriginal(id, trainType);
      const current = trainType ? trainType[orig.limitKey] : undefined;

      const update = {};
      let newLimit;
      let newAllow;

      if (restoreOriginal) {
        newLimit = isLimitObject(orig.limit) ? Object.assign({}, orig.limit) : orig.limit;
        newAllow = orig.allow;
        // Zugtypen, die nie angefasst wurden, überspringen.
        if (newLimit === undefined && newAllow === undefined) continue;
      } else {
        if (!shouldCross(id, orig)) continue;

        // Basis: bestehende Struktur, damit unbekannte Straßenklassen erhalten
        // bleiben. Konfigurierte Klassen werden überschrieben.
        const base = isLimitObject(current)
          ? current
          : isLimitObject(orig.limit)
            ? orig.limit
            : DEFAULT_LIMIT;

        newLimit = {};
        for (const roadClass of Object.keys(base)) {
          newLimit[roadClass] = base[roadClass];
        }
        for (const roadClass of Object.keys(LIMITS)) {
          newLimit[roadClass] = normalizeValue(LIMITS[roadClass]);
        }
        newAllow = true;
      }

      update[orig.limitKey] = newLimit;
      update[orig.allowKey] = newAllow;
      // Falls der Build beide Schreibweisen kennt, beide setzen.
      if (orig.hasAliasKey && orig.allowKey !== "canCrossRoads") {
        update.canCrossRoads = newAllow;
      }

      try {
        api.trains.modifyTrainType(id, update);
        changed++;
        summary.push({
          id: id,
          name: (trainType && trainType.name) || id,
          newlyEnabled: !restoreOriginal && !crossedOriginally(orig),
          before: current,
          after: newLimit,
        });
      } catch (err) {
        console.error(`${TAG} Fehler beim Ändern von Zugtyp "${id}":`, err);
      }
    }

    lastSummary = summary;
    persistOriginals();
    console.log(`${TAG} ${reason}: ${changed} Zugtyp(en) angepasst.`, summary);
    return changed;
  }

  /** Schreibt neu gesicherte Originalwerte einmalig in den Speicher. */
  function persistOriginals() {
    if (!newOriginalsToPersist) return;
    newOriginalsToPersist = false;
    const merged = Object.assign({}, storedOriginals || {});
    for (const id of Object.keys(originals)) {
      if (!merged[id]) merged[id] = originals[id];
    }
    storedOriginals = merged;
    try {
      const p = api.storage.set(MOD_ID + ".originals", merged);
      if (p && typeof p.catch === "function") {
        p.catch(function (err) {
          console.warn(`${TAG} Originalwerte konnten nicht gespeichert werden:`, err);
        });
      }
    } catch (err) {
      console.warn(`${TAG} Originalwerte konnten nicht gespeichert werden:`, err);
    }
  }

  // --------------------------------------------------------------------------
  //  Diagnose: Warum erzeugt das Spiel (k)einen Bahnübergang?
  // --------------------------------------------------------------------------

  /**
   * Vergleicht einen Zugtyp, der im Vanilla-Spiel Bahnübergänge erzeugt
   * (z. B. s-train / regional), mit den neu freigeschalteten Metro-Typen und
   * gibt alle Unterschiede aus. Zusätzlich werden die Spielkonstanten nach
   * Bahnübergangs-Einträgen durchsucht.
   *
   * Rein lesend – ändert nichts am Spielstand.
   */
  function dumpDiagnostics() {
    const out = {
      trainTypeIds: [],
      crossingCapableTypes: {},
      metroVsVanillaDiff: {},
      crossingConstants: {},
      mapLayers: {},
      apiCrossingEntries: [],
      trackSample: null,
    };

    let trainTypes = {};
    try {
      trainTypes = api.trains.getTrainTypes() || {};
    } catch (err) {
      console.error(`${TAG} Diagnose: Zugtypen nicht lesbar:`, err);
    }
    out.trainTypeIds = Object.keys(trainTypes);

    // Alle Zugtypen: welche tragen Kreuzungs-Eigenschaften?
    for (const [id, t] of Object.entries(trainTypes)) {
      if (!t) continue;
      const entry = {};
      for (const k of Object.keys(t)) {
        if (/cross|grade|road/i.test(k)) entry[k] = t[k];
      }
      if (t.stats) {
        for (const k of Object.keys(t.stats)) {
          if (/cross|grade|road|tph/i.test(k)) entry["stats." + k] = t.stats[k];
        }
      }
      out.crossingCapableTypes[id] = entry;
    }

    // Gezielt gegen einen echten Vanilla-Kreuzer vergleichen (nicht gegen
    // einen vom Mod veränderten Zugtyp).
    let referenceId = null;
    for (const cand of VANILLA_CROSSING_IDS) {
      if (trainTypes[cand]) {
        referenceId = cand;
        break;
      }
    }

    if (referenceId) {
      const ref = trainTypes[referenceId];
      for (const id of METRO_TRAIN_IDS) {
        const t = trainTypes[id];
        if (!t) continue;
        const diff = {};
        const allKeys = new Set(Object.keys(ref || {}).concat(Object.keys(t)));
        for (const k of allKeys) {
          // Reine Zahlenwerte/Optik sind für Bahnübergänge irrelevant.
          if (k === "stats" || k === "appearance" || k === "description") continue;
          const a = JSON.stringify(ref ? ref[k] : undefined);
          const b = JSON.stringify(t[k]);
          if (a !== b) diff[k] = { [referenceId]: ref ? ref[k] : undefined, [id]: t[k] };
        }
        out.metroVsVanillaDiff[id] = diff;
      }
      out.metroVsVanillaDiff.__reference = referenceId;
    } else {
      out.metroVsVanillaDiff.__reference =
        "kein Vanilla-Kreuzer vorhanden (gesucht: " + VANILLA_CROSSING_IDS.join(", ") + ")";
    }

    // Spielkonstanten nach Bahnübergangs-Einträgen durchsuchen.
    try {
      const constants = api.utils.getConstants() || {};
      out.crossingConstants.__allKeys = Object.keys(constants);
      for (const k of Object.keys(constants)) {
        if (/cross|grade|road|tph|barrier/i.test(k)) {
          out.crossingConstants[k] = constants[k];
        }
      }
    } catch (err) {
      console.warn(`${TAG} Diagnose: Konstanten nicht lesbar:`, err);
    }

    // Kartenebenen: rendert das Spiel Bahnübergänge als eigene Ebene?
    try {
      const map = api.utils.getMap();
      if (map && typeof map.getStyle === "function") {
        const style = map.getStyle() || {};
        const layers = style.layers || [];
        out.mapLayers.matching = layers
          .filter(function (l) {
            return /cross|grade|barrier|gate|signal/i.test(l.id);
          })
          .map(function (l) {
            return { id: l.id, type: l.type, source: l.source, sourceLayer: l["source-layer"] };
          });
        out.mapLayers.allLayerIds = layers.map(function (l) {
          return l.id;
        });
        out.mapLayers.sourceIds = Object.keys(style.sources || {});

        // Falls es eine Crossing-Ebene gibt: ein paar Features anschauen.
        const first = out.mapLayers.matching[0];
        if (first && typeof map.querySourceFeatures === "function") {
          try {
            const feats = map.querySourceFeatures(first.source, {
              sourceLayer: first.sourceLayer,
            });
            out.mapLayers.sampleFeatures = feats.slice(0, 5).map(function (f) {
              return f.properties;
            });
            out.mapLayers.featureCount = feats.length;
          } catch (e) {
            out.mapLayers.sampleFeatures = "nicht abfragbar: " + e.message;
          }
        }
      } else {
        out.mapLayers = "Karte nicht verfügbar";
      }
    } catch (err) {
      console.warn(`${TAG} Diagnose: Karte nicht lesbar:`, err);
    }

    // Gibt es irgendwo in der API einen Bahnübergangs-Einstieg?
    try {
      for (const ns of Object.keys(api)) {
        if (/cross|grade/i.test(ns)) out.apiCrossingEntries.push(ns);
        const v = api[ns];
        if (v && typeof v === "object") {
          for (const fn of Object.keys(v)) {
            if (/cross|grade/i.test(fn)) out.apiCrossingEntries.push(ns + "." + fn);
          }
        }
      }
    } catch (err) {
      console.warn(`${TAG} Diagnose: API nicht scanbar:`, err);
    }

    // Ein gebautes Gleis anschauen: gibt es dort Bahnübergangs-Felder?
    try {
      const tracks = api.gameState.getTracks() || [];
      if (tracks.length) {
        // Bevorzugt ein oberirdisches Gleis zeigen (dort entstünde ein Übergang).
        const atGrade = tracks.filter(function (t) {
          return t.startElevation > -3 && t.startElevation < 4.5;
        });
        out.trackSample = {
          totalTracks: tracks.length,
          atGradeTracks: atGrade.length,
          keys: Object.keys(tracks[0]),
          atGradeExample: atGrade.length ? atGrade[0] : null,
        };
        out.trackSample.tracksWithCrossingFields = tracks.filter(function (t) {
          return Object.keys(t).some(function (k) {
            return /cross|grade|road/i.test(k);
          });
        }).length;
      } else {
        out.trackSample = "keine Gleise gebaut";
      }
    } catch (err) {
      console.warn(`${TAG} Diagnose: Gleise nicht lesbar:`, err);
    }

    console.log(`${TAG} ===== DIAGNOSE BAHNÜBERGANG =====`);
    console.log(out);
    try {
      // Zum Kopieren als Text bereitstellen.
      window.__bahnuebergangDiagnose = out;
      console.log(
        `${TAG} Als Text kopieren mit:  copy(JSON.stringify(window.__bahnuebergangDiagnose, null, 2))`
      );
    } catch (e) {
      /* optional */
    }
    return out;
  }

  /** Namen der aktuell betroffenen Zugtypen. */
  function affectedTrainNames() {
    return lastSummary.map(function (s) {
      return s.newlyEnabled ? s.name + " (neu freigeschaltet)" : s.name;
    });
  }

  // --------------------------------------------------------------------------
  //  Speichern / Laden
  // --------------------------------------------------------------------------

  function saveSettings() {
    try {
      const p = api.storage.set(MOD_ID + "." + STORAGE_KEY, {
        limits: LIMITS,
        options: OPTIONS,
      });
      if (p && typeof p.catch === "function") {
        p.catch(function (err) {
          console.warn(`${TAG} Speichern fehlgeschlagen:`, err);
        });
      }
    } catch (err) {
      console.warn(`${TAG} Speichern fehlgeschlagen:`, err);
    }
  }

  let settingsPromise = null;

  function loadSettings() {
    if (settingsPromise) return settingsPromise;
    settingsPromise = (async function () {
      try {
        const savedOriginals = await api.storage.get(MOD_ID + ".originals", null);
        if (savedOriginals && typeof savedOriginals === "object") {
          storedOriginals = savedOriginals;
          console.log(`${TAG} Originalwerte aus Speicher geladen.`);
        }

        const saved = await api.storage.get(MOD_ID + "." + STORAGE_KEY, null);
        if (saved && typeof saved === "object") {
          if (saved.limits && typeof saved.limits === "object") {
            for (const k of Object.keys(saved.limits)) {
              LIMITS[k] = saved.limits[k];
            }
          }
          if (saved.options && typeof saved.options === "object") {
            for (const k of Object.keys(saved.options)) {
              if (k in OPTIONS) OPTIONS[k] = saved.options[k];
            }
          }
          console.log(`${TAG} Gespeicherte Werte geladen:`, LIMITS, OPTIONS);
        }
      } catch (err) {
        // storage ist im Browser ein No-Op – kein Fehlerfall.
        console.warn(`${TAG} Keine gespeicherten Werte geladen:`, err);
      }
    })();
    return settingsPromise;
  }

  // --------------------------------------------------------------------------
  //  Oberfläche
  // --------------------------------------------------------------------------

  const React = api.utils && api.utils.React;
  const gameComponents = (api.utils && api.utils.components) || {};
  const h = React ? React.createElement : null;

  /** Erzeugt das Einstellungs-Panel als React-Komponente. */
  function createPanel() {
    if (!React) return null;

    const InputComp = gameComponents.Input || "input";
    const ButtonComp = gameComponents.Button || "button";

    return function CrossingTphPanel() {
      const initial = {};
      for (const rc of ROAD_ORDER) {
        const v = LIMITS[rc];
        initial[rc] = v === null || v === undefined ? "" : String(v);
      }

      const [draft, setDraft] = React.useState(initial);
      const [status, setStatus] = React.useState("");
      const [metroCross, setMetroCross] = React.useState(OPTIONS.enableMetroCrossing);
      const [allCross, setAllCross] = React.useState(OPTIONS.enableCrossingForAllTrains);

      function setField(roadClass, value) {
        const clean = String(value).replace(/[^0-9]/g, "");
        setDraft(function (prev) {
          return Object.assign({}, prev, { [roadClass]: clean });
        });
      }

      function apply() {
        for (const rc of ROAD_ORDER) {
          LIMITS[rc] = normalizeValue(draft[rc]);
        }
        OPTIONS.enableMetroCrossing = metroCross;
        OPTIONS.enableCrossingForAllTrains = allCross;
        saveSettings();
        const n = applyOverrides("Über Panel angewendet", false);
        setStatus(
          n > 0
            ? `${n} Zugtyp(en): ${affectedTrainNames().join(", ")}`
            : "Keine passenden Zugtypen gefunden."
        );
        try {
          api.ui.showNotification(
            `Bahnübergang-Limit gesetzt (${n} Zugtypen).`,
            n > 0 ? "success" : "warning"
          );
        } catch (e) {
          /* Benachrichtigung ist optional */
        }
      }

      function resetToVanilla() {
        const n = applyOverrides("Auf Vanilla zurückgesetzt", true);
        const next = {};
        for (const rc of ROAD_ORDER) {
          const v = DEFAULT_LIMIT[rc];
          next[rc] = v === null || v === undefined ? "" : String(v);
        }
        setDraft(next);
        for (const rc of ROAD_ORDER) {
          LIMITS[rc] = normalizeValue(next[rc]);
        }
        setMetroCross(false);
        setAllCross(false);
        OPTIONS.enableMetroCrossing = false;
        OPTIONS.enableCrossingForAllTrains = false;
        saveSettings();
        setStatus(`Vanilla-Zustand wiederhergestellt (${n} Zugtypen).`);
        try {
          api.ui.showNotification("Bahnübergang-Limit zurückgesetzt.", "info");
        } catch (e) {
          /* optional */
        }
      }

      function checkbox(label, checked, onChange) {
        return h(
          "label",
          {
            style: {
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              marginBottom: "4px",
            },
          },
          h("input", {
            type: "checkbox",
            checked: checked,
            onChange: function (e) {
              onChange(e.target.checked);
            },
          }),
          label
        );
      }

      const rows = ROAD_ORDER.map(function (rc) {
        return h(
          "div",
          {
            key: rc,
            style: {
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "8px",
              marginBottom: "6px",
            },
          },
          h("span", { style: { fontSize: "13px" } }, ROAD_LABELS[rc] || rc),
          h(InputComp, {
            type: "text",
            inputMode: "numeric",
            value: draft[rc],
            placeholder: "gesperrt",
            onChange: function (e) {
              setField(rc, e && e.target ? e.target.value : e);
            },
            style: {
              width: "80px",
              textAlign: "right",
              padding: "2px 6px",
            },
          })
        );
      });

      return h(
        "div",
        { style: { padding: "10px", minWidth: "280px" } },
        h(
          "div",
          { style: { fontSize: "12px", opacity: 0.75, marginBottom: "8px" } },
          "Züge pro Stunde je Straßenklasse. Leer oder 0 = Übergang gesperrt."
        ),
        rows,
        h("div", { style: { height: "1px", background: "currentColor", opacity: 0.15, margin: "10px 0" } }),
        h(
          "div",
          { style: { fontSize: "12px", opacity: 0.75, marginBottom: "6px" } },
          "Straßenquerung erlauben:"
        ),
        checkbox("Heavy & Light Metro dürfen Straßen kreuzen", metroCross, setMetroCross),
        checkbox("Alle Zugtypen dürfen Straßen kreuzen", allCross, setAllCross),
        h(
          "div",
          { style: { display: "flex", gap: "8px", marginTop: "10px" } },
          h(ButtonComp, { onClick: apply }, "Anwenden"),
          h(ButtonComp, { onClick: resetToVanilla, variant: "outline" }, "Zurücksetzen")
        ),
        h(
          "div",
          { style: { marginTop: "8px" } },
          h(
            ButtonComp,
            {
              variant: "ghost",
              onClick: function () {
                dumpDiagnostics();
                setStatus("Diagnose in die Konsole geschrieben (F12).");
              },
            },
            "Diagnose in Konsole"
          )
        ),
        status
          ? h(
              "div",
              { style: { fontSize: "11px", opacity: 0.75, marginTop: "8px" } },
              status
            )
          : null
      );
    };
  }

  function safeUi(fn) {
    try {
      fn();
    } catch (err) {
      console.warn(`${TAG} UI-Element konnte nicht hinzugefügt werden:`, err);
    }
  }

  function setupUi() {
    const Panel = createPanel();

    if (Panel) {
      // Im Einstellungen-Menü (dort gehören Mod-Optionen hin)
      safeUi(function () {
        api.ui.registerComponent("settings-menu", {
          id: MOD_ID + ".panel",
          component: Panel,
        });
      });

      // Zusätzlich als verschiebbares Panel
      safeUi(function () {
        api.ui.addFloatingPanel({
          id: MOD_ID + ".floating",
          title: "Bahnübergang-Limit",
          icon: "TrainFront",
          defaultWidth: 320,
          render: Panel,
        });
      });
    } else {
      console.warn(`${TAG} React nicht verfügbar – Zahlenfelder werden nicht angezeigt.`);
    }

    // Knopf im Escape-Menü: Werte erneut anwenden
    safeUi(function () {
      api.ui.addButton("escape-menu", {
        id: MOD_ID + ".apply",
        label: "Bahnübergang-Limit anwenden",
        onClick: function () {
          const n = applyOverrides("Manuell ausgelöst", false);
          api.ui.showNotification(
            `Bahnübergang-Limit angewendet (${n} Zugtypen).`,
            "success"
          );
        },
      });
    });
  }

  // --------------------------------------------------------------------------
  //  Initialisierung
  // --------------------------------------------------------------------------

  let uiReady = false;

  function init(reason) {
    loadSettings().then(function () {
      applyOverrides(reason, false);
      if (!uiReady) {
        uiReady = true;
        setupUi();
      }
    });
  }

  // Beim Spielstart und bei jedem Städtewechsel neu anwenden, da Zugtypen
  // dabei (neu) initialisiert werden können.
  try {
    api.hooks.onGameInit(function () {
      init("onGameInit");
    });
  } catch (err) {
    console.warn(`${TAG} onGameInit-Hook nicht verfügbar:`, err);
  }

  try {
    api.hooks.onCityLoad(function (cityCode) {
      init("onCityLoad(" + cityCode + ")");
    });
  } catch (err) {
    console.warn(`${TAG} onCityLoad-Hook nicht verfügbar:`, err);
  }

  try {
    api.hooks.onMapReady(function () {
      init("onMapReady");
    });
  } catch (err) {
    console.warn(`${TAG} onMapReady-Hook nicht verfügbar:`, err);
  }

  // Falls das Spiel bereits läuft, während der Mod (neu) geladen wird.
  init("Sofort-Anwendung beim Laden");
})();
