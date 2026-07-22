/**
 * Bahnübergang-Limit Override
 * ----------------------------
 * Subway Builder Mod, der das Limit "Züge pro Stunde" (tph) an Bahnübergängen
 * überschreibt.
 *
 * Hintergrund: Jeder Zugtyp, der Straßen ebenerdig kreuzen darf, hat die
 * Eigenschaft `gradeCrossingTphLimit`. Das ist ein Objekt mit einer Obergrenze
 * (kombinierte Fahrtrichtungen, Züge/Stunde) je Straßenklasse:
 *
 *     gradeCrossingTphLimit: { highway: null, major: 6, medium: 8, minor: 10 }
 *
 * `null` bedeutet: an dieser Straßenklasse ist ein ebenerdiger Übergang
 * verboten. Dieser Mod liest diese Werte zur Laufzeit aus und ersetzt sie
 * über `api.trains.modifyTrainType()`.
 *
 * API-Referenz:
 *   - api.trains.getTrainTypes()               -> Record<id, TrainType>
 *   - api.trains.modifyTrainType(id, updates)  -> Teil-Update eines Zugtyps
 */

(function () {
  "use strict";

  const MOD_ID = "com.nilsmeier.crossing-tph-override";
  const MOD_VERSION = "1.0.0";
  const TAG = "[BahnübergangTPH]";

  // ==========================================================================
  //  KONFIGURATION  —  hier die gewünschten Werte einstellen
  // ==========================================================================
  const CONFIG = {
    // Modus, wie die bestehenden Limits ersetzt werden:
    //   "multiply"  -> bestehende Limits mit `multiplier` multiplizieren
    //   "set"       -> feste Werte aus `values` verwenden
    //   "unlimited" -> Limit praktisch aufheben (Wert = `unlimitedValue`)
    mode: "multiply",

    // Für mode === "multiply": Faktor, mit dem jedes bestehende Limit
    // multipliziert wird (z. B. 3 = dreifache Kapazität).
    multiplier: 3,

    // Für mode === "set": feste Grenzen (Züge/Stunde) je Straßenklasse.
    // `null` = Übergang an dieser Straßenklasse bleibt verboten.
    values: {
      highway: null,
      major: 30,
      medium: 40,
      minor: 60,
    },

    // Für mode === "unlimited": Wert, der als "quasi unbegrenzt" gesetzt wird.
    unlimitedValue: 999,

    // Wenn true, wird auch an Autobahnen/Highways (Standard: verboten = null)
    // ein Übergang erlaubt. Der dann verwendete Wert richtet sich nach dem
    // gewählten Modus (multiply nutzt highwayBaseValue als Ausgangswert).
    allowHighwayCrossing: false,

    // Ausgangswert für Highways, falls allowHighwayCrossing im "multiply"-Modus
    // aktiv ist und aktuell kein Wert (null) hinterlegt ist.
    highwayBaseValue: 4,

    // Wenn true, werden auch Zugtypen bearbeitet, die aktuell KEIN Crossing-
    // Limit besitzen (z. B. reine U-Bahnen). Standard: false — es werden nur
    // Zugtypen angefasst, die ohnehin Straßen ebenerdig kreuzen dürfen.
    applyToAllTrains: false,
  };
  // ==========================================================================

  // Fallback-Standardwerte, falls ein Zugtyp (noch) kein Limit-Objekt hat,
  // aber Straßen kreuzen darf. Entspricht den Vanilla-Werten des Spiels.
  const DEFAULT_LIMIT = { highway: null, major: 6, medium: 8, minor: 10 };

  const api = window.SubwayBuilderAPI;
  if (!api) {
    console.error(`${TAG} SubwayBuilderAPI nicht gefunden – Mod wird nicht geladen.`);
    return;
  }

  console.log(`${TAG} v${MOD_VERSION} | API v${api.version}`);

  // --------------------------------------------------------------------------
  //  Hilfsfunktionen
  // --------------------------------------------------------------------------

  /**
   * Findet den Namen der Crossing-Limit-Eigenschaft an einem Zugtyp.
   * Standardname ist `gradeCrossingTphLimit`, wir tolerieren aber auch leichte
   * Schreibvarianten, damit der Mod robust gegenüber Spielversionen bleibt.
   */
  function resolveCrossingKey(trainType) {
    const known = [
      "gradeCrossingTphLimit",
      "gradeCrossingTPHLimit",
      "gradeCrossingTphLimits",
    ];
    for (const k of known) {
      if (trainType && Object.prototype.hasOwnProperty.call(trainType, k)) return k;
    }
    // Heuristik: irgendein Key, der nach "grade crossing tph" aussieht.
    if (trainType) {
      for (const k of Object.keys(trainType)) {
        if (/grade.*cross.*tph|crossing.*tph/i.test(k)) return k;
      }
    }
    return "gradeCrossingTphLimit"; // Standard, falls nichts gefunden
  }

  /** Prüft, ob ein Wert ein sinnvolles Limit-Objekt ist. */
  function isLimitObject(v) {
    return v && typeof v === "object" && !Array.isArray(v);
  }

  /** Darf dieser Zugtyp aktuell Straßen ebenerdig kreuzen? */
  function canCross(trainType, currentLimit) {
    if (trainType && trainType.allowAtGradeRoadCrossing === true) return true;
    if (isLimitObject(currentLimit)) return true;
    return false;
  }

  /**
   * Berechnet ein neues Limit-Objekt aus dem bestehenden.
   * Unbekannte/zusätzliche Straßenklassen werden ebenfalls berücksichtigt.
   */
  function computeNewLimit(current) {
    const base = isLimitObject(current) ? current : DEFAULT_LIMIT;
    const result = {};

    for (const roadClass of Object.keys(base)) {
      const oldVal = base[roadClass];
      const isHighway = roadClass === "highway";

      // Highways bleiben verboten, außer der Nutzer erlaubt sie ausdrücklich.
      if (isHighway && !CONFIG.allowHighwayCrossing) {
        result[roadClass] = null;
        continue;
      }

      if (CONFIG.mode === "unlimited") {
        result[roadClass] = CONFIG.unlimitedValue;
      } else if (CONFIG.mode === "set") {
        // Bei "set" nehmen wir den konfigurierten Wert; fehlt einer, behalten
        // wir den alten Wert bei.
        const setVal = CONFIG.values[roadClass];
        result[roadClass] = setVal === undefined ? oldVal : setVal;
      } else {
        // "multiply"
        let start = oldVal;
        if (isHighway && (start === null || start === undefined)) {
          start = CONFIG.highwayBaseValue;
        }
        if (typeof start === "number") {
          result[roadClass] = Math.max(1, Math.round(start * CONFIG.multiplier));
        } else {
          result[roadClass] = start; // null/undefined unverändert lassen
        }
      }
    }

    return result;
  }

  // --------------------------------------------------------------------------
  //  Kernlogik: Überschreiben aller relevanten Zugtypen
  // --------------------------------------------------------------------------

  let lastSummary = [];

  function applyOverrides(reason) {
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
      const key = resolveCrossingKey(trainType);
      const current = trainType ? trainType[key] : undefined;

      if (!CONFIG.applyToAllTrains && !canCross(trainType, current)) {
        continue; // Zugtyp kreuzt keine Straßen -> überspringen
      }

      const newLimit = computeNewLimit(current);

      try {
        api.trains.modifyTrainType(id, { [key]: newLimit });
        changed++;
        summary.push({ id, name: (trainType && trainType.name) || id, before: current, after: newLimit });
      } catch (err) {
        console.error(`${TAG} Fehler beim Ändern von Zugtyp "${id}":`, err);
      }
    }

    lastSummary = summary;
    console.log(
      `${TAG} ${reason}: ${changed} Zugtyp(en) angepasst (Modus: ${CONFIG.mode}).`,
      summary
    );
    return changed;
  }

  /** Kurze, menschenlesbare Zusammenfassung für Benachrichtigungen. */
  function summaryText() {
    if (!lastSummary.length) return "Keine kreuzenden Zugtypen gefunden.";
    return lastSummary
      .map((s) => {
        const a = s.after || {};
        const parts = Object.keys(a).map((k) => `${k}:${a[k] === null ? "–" : a[k]}`);
        return `${s.name} → ${parts.join(", ")}`;
      })
      .join("\n");
  }

  // --------------------------------------------------------------------------
  //  Benutzeroberfläche (best-effort, bricht den Mod bei Fehlern nicht ab)
  // --------------------------------------------------------------------------

  function safeUi(fn) {
    try {
      fn();
    } catch (err) {
      console.warn(`${TAG} UI-Element konnte nicht hinzugefügt werden:`, err);
    }
  }

  function setupUi() {
    // Knopf: Limits neu anwenden + Zusammenfassung anzeigen
    safeUi(() =>
      api.ui.addButton("escape-menu", {
        id: MOD_ID + ".apply",
        label: "Bahnübergang-Limit anwenden",
        onClick: () => {
          const n = applyOverrides("Manuell ausgelöst");
          api.ui.showNotification(
            `Bahnübergang-Limit aktualisiert (${n} Zugtypen).\n${summaryText()}`,
            "success"
          );
        },
      })
    );

    // Schieberegler: Multiplikator (wirkt im Modus "multiply")
    safeUi(() =>
      api.ui.addSlider("settings-menu", {
        id: MOD_ID + ".multiplier",
        label: "Bahnübergang-Limit ×Faktor",
        min: 1,
        max: 20,
        step: 1,
        defaultValue: CONFIG.multiplier,
        onChange: (value) => {
          CONFIG.multiplier = value;
          CONFIG.mode = "multiply";
          applyOverrides(`Faktor auf ${value} gesetzt`);
        },
      })
    );

    // Umschalter: Limit komplett aufheben
    safeUi(() =>
      api.ui.addToggle("settings-menu", {
        id: MOD_ID + ".unlimited",
        label: "Bahnübergang-Limit aufheben",
        defaultValue: CONFIG.mode === "unlimited",
        onChange: (enabled) => {
          CONFIG.mode = enabled ? "unlimited" : "multiply";
          applyOverrides(enabled ? "Limit aufgehoben" : "Faktor-Modus");
        },
      })
    );
  }

  // --------------------------------------------------------------------------
  //  Initialisierung
  // --------------------------------------------------------------------------

  let uiReady = false;

  function init(reason) {
    applyOverrides(reason);
    if (!uiReady) {
      uiReady = true;
      setupUi();
    }
  }

  // Beim Spielstart und bei jedem Städtewechsel neu anwenden, da Zugtypen
  // dabei (neu) initialisiert werden können.
  try {
    api.hooks.onGameInit(() => init("onGameInit"));
  } catch (err) {
    console.warn(`${TAG} onGameInit-Hook nicht verfügbar:`, err);
  }

  try {
    api.hooks.onCityLoad((cityCode) => init(`onCityLoad(${cityCode})`));
  } catch (err) {
    console.warn(`${TAG} onCityLoad-Hook nicht verfügbar:`, err);
  }

  try {
    api.hooks.onMapReady(() => init("onMapReady"));
  } catch (err) {
    console.warn(`${TAG} onMapReady-Hook nicht verfügbar:`, err);
  }

  // Falls das Spiel bereits läuft, während der Mod (neu) geladen wird.
  init("Sofort-Anwendung beim Laden");
})();
