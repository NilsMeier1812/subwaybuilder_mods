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
 * Die Werte werden direkt im Spiel über Zahlenfelder eingegeben
 * (Einstellungen-Menü bzw. schwebendes Panel) und dauerhaft gespeichert.
 */

(function () {
  "use strict";

  const MOD_ID = "com.nilsmeier.crossing-tph-override";
  const MOD_VERSION = "2.0.0";
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

  // Zusätzliche Optionen
  const OPTIONS = {
    // Auch Zugtypen anfassen, die aktuell gar keine Straßen kreuzen dürfen
    // (z. B. reine U-Bahnen). Standard: aus.
    applyToAllTrains: false,
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

  // Originalwerte je Zugtyp, damit "Zurücksetzen" die Vanilla-Werte
  // wiederherstellen kann. Wird beim allerersten Auslesen befüllt.
  const originalLimits = {};

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
    if (trainType) {
      for (const k of Object.keys(trainType)) {
        if (/grade.*cross.*tph|crossing.*tph/i.test(k)) return k;
      }
    }
    return "gradeCrossingTphLimit";
  }

  function isLimitObject(v) {
    return v && typeof v === "object" && !Array.isArray(v);
  }

  /** Darf dieser Zugtyp Straßen ebenerdig kreuzen? */
  function canCross(trainType, currentLimit) {
    if (trainType && trainType.allowAtGradeRoadCrossing === true) return true;
    if (isLimitObject(currentLimit)) return true;
    return false;
  }

  /** Wandelt eine Eingabe in einen Limit-Wert (Zahl oder null). */
  function normalizeValue(raw) {
    if (raw === null || raw === undefined || raw === "") return null;
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0) return null; // 0 / ungültig = gesperrt
    return Math.round(n);
  }

  // --------------------------------------------------------------------------
  //  Kernlogik
  // --------------------------------------------------------------------------

  let lastSummary = [];

  /**
   * Wendet die aktuellen LIMITS auf alle passenden Zugtypen an.
   * @param {string} reason  Nur für die Konsolenausgabe.
   * @param {boolean} restoreOriginal  true = Vanilla-Werte wiederherstellen.
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
      const key = resolveCrossingKey(trainType);
      const current = trainType ? trainType[key] : undefined;

      // Originalwerte einmalig sichern (vor der ersten Änderung).
      if (!(id in originalLimits)) {
        originalLimits[id] = isLimitObject(current)
          ? Object.assign({}, current)
          : current === undefined
            ? undefined
            : current;
      }

      if (!OPTIONS.applyToAllTrains && !canCross(trainType, originalLimits[id])) {
        continue; // Zugtyp kreuzt keine Straßen -> überspringen
      }

      let newLimit;
      if (restoreOriginal) {
        const orig = originalLimits[id];
        newLimit = isLimitObject(orig) ? Object.assign({}, orig) : DEFAULT_LIMIT;
      } else {
        // Basis: bestehende Struktur, damit unbekannte Straßenklassen erhalten
        // bleiben. Konfigurierte Klassen werden überschrieben.
        const base = isLimitObject(current)
          ? current
          : isLimitObject(originalLimits[id])
            ? originalLimits[id]
            : DEFAULT_LIMIT;

        newLimit = {};
        for (const roadClass of Object.keys(base)) {
          newLimit[roadClass] = base[roadClass];
        }
        for (const roadClass of Object.keys(LIMITS)) {
          newLimit[roadClass] = normalizeValue(LIMITS[roadClass]);
        }
      }

      try {
        api.trains.modifyTrainType(id, { [key]: newLimit });
        changed++;
        summary.push({
          id: id,
          name: (trainType && trainType.name) || id,
          before: current,
          after: newLimit,
        });
      } catch (err) {
        console.error(`${TAG} Fehler beim Ändern von Zugtyp "${id}":`, err);
      }
    }

    lastSummary = summary;
    console.log(`${TAG} ${reason}: ${changed} Zugtyp(en) angepasst.`, summary);
    return changed;
  }

  /** Namen der aktuell betroffenen Zugtypen. */
  function affectedTrainNames() {
    return lastSummary.map(function (s) {
      return s.name;
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
        const saved = await api.storage.get(MOD_ID + "." + STORAGE_KEY, null);
        if (saved && typeof saved === "object") {
          if (saved.limits && typeof saved.limits === "object") {
            for (const k of Object.keys(saved.limits)) {
              LIMITS[k] = saved.limits[k];
            }
          }
          if (saved.options && typeof saved.options === "object") {
            for (const k of Object.keys(saved.options)) {
              OPTIONS[k] = saved.options[k];
            }
          }
          console.log(`${TAG} Gespeicherte Werte geladen:`, LIMITS);
        }
      } catch (err) {
        // storage ist im Browser ein No-Op – kein Fehlerfall.
        console.warn(`${TAG} Keine gespeicherten Werte geladen:`, err);
      }
    })();
    return settingsPromise;
  }

  // --------------------------------------------------------------------------
  //  Oberfläche: Zahleneingabe je Straßenklasse
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
      // Eingaben als Text halten, damit man frei tippen kann.
      const initial = {};
      for (const rc of ROAD_ORDER) {
        const v = LIMITS[rc];
        initial[rc] = v === null || v === undefined ? "" : String(v);
      }

      const [draft, setDraft] = React.useState(initial);
      const [status, setStatus] = React.useState("");
      const [allTrains, setAllTrains] = React.useState(OPTIONS.applyToAllTrains);

      function setField(roadClass, value) {
        // Nur Ziffern zulassen (leer = gesperrt).
        const clean = String(value).replace(/[^0-9]/g, "");
        setDraft(function (prev) {
          return Object.assign({}, prev, { [roadClass]: clean });
        });
      }

      function apply() {
        for (const rc of ROAD_ORDER) {
          LIMITS[rc] = normalizeValue(draft[rc]);
        }
        OPTIONS.applyToAllTrains = allTrains;
        saveSettings();
        const n = applyOverrides("Über Panel angewendet", false);
        const names = affectedTrainNames();
        setStatus(
          n > 0
            ? `${n} Zugtyp(en) angepasst: ${names.join(", ")}`
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
        // Eingabefelder auf die Originalwerte des ersten betroffenen Zugtyps
        // setzen, damit man sieht, was Vanilla war.
        const firstOrig = lastSummary.length ? lastSummary[0].after : DEFAULT_LIMIT;
        const next = {};
        for (const rc of ROAD_ORDER) {
          const v = firstOrig ? firstOrig[rc] : DEFAULT_LIMIT[rc];
          next[rc] = v === null || v === undefined ? "" : String(v);
        }
        setDraft(next);
        for (const rc of ROAD_ORDER) {
          LIMITS[rc] = normalizeValue(next[rc]);
        }
        saveSettings();
        setStatus(`Vanilla-Werte wiederhergestellt (${n} Zugtypen).`);
        try {
          api.ui.showNotification("Bahnübergang-Limit zurückgesetzt.", "info");
        } catch (e) {
          /* optional */
        }
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
        { style: { padding: "10px", minWidth: "260px" } },
        h(
          "div",
          { style: { fontSize: "12px", opacity: 0.75, marginBottom: "8px" } },
          "Züge pro Stunde je Straßenklasse. Leer oder 0 = Übergang gesperrt."
        ),
        rows,
        h(
          "label",
          {
            style: {
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              margin: "10px 0",
            },
          },
          h("input", {
            type: "checkbox",
            checked: allTrains,
            onChange: function (e) {
              setAllTrains(e.target.checked);
            },
          }),
          "Auf alle Zugtypen anwenden (auch nicht-kreuzende)"
        ),
        h(
          "div",
          { style: { display: "flex", gap: "8px" } },
          h(ButtonComp, { onClick: apply }, "Anwenden"),
          h(ButtonComp, { onClick: resetToVanilla, variant: "outline" }, "Zurücksetzen")
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
          defaultWidth: 300,
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
