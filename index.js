/**
 * Bahnübergang-Mod für Subway Builder
 * -----------------------------------
 *  1. Schaltet echte Bahnübergänge für Heavy Metro und Light Metro frei.
 *  2. Überschreibt das Limit "Züge pro Stunde" (tph) an Bahnübergängen.
 *
 * Hintergrund — das Spiel führt fünf relevante Eigenschaften je Zugtyp:
 *
 *   allowGradeCrossing              erzeugt einen echten Bahnübergang
 *   allowAtGradeRoadCrossing        erlaubt das Queren der Straße überhaupt
 *   gradeCrossingTphLimit           Züge/Stunde je Straßenklasse
 *   gradeCrossingBaseCost           Baukosten je Übergang
 *   gradeCrossingMaintenancePerDay  laufende Kosten je Übergang
 *
 * Bei Heavy/Light Metro stehen beide Flags auf `false` und die Kostenfelder
 * fehlen ganz. Setzt man nur `allowAtGradeRoadCrossing`, quert das Gleis die
 * Straße zwar, es entsteht aber kein Bahnübergang. Deshalb setzt der Mod alle
 * fünf Eigenschaften und übernimmt die Kosten von einem Zugtyp, der im
 * Vanilla-Spiel bereits Übergänge baut (Commuter Rail).
 *
 * Alle Werte werden im Spiel über Zahlenfelder eingegeben und dauerhaft
 * gespeichert.
 */

(function () {
  "use strict";

  const MOD_ID = "com.nilsmeier.crossing-tph-override";
  const MOD_VERSION = "4.1.0";
  const TAG = "[BahnübergangTPH]";

  // ==========================================================================
  //  STARTWERTE  —  Züge pro Stunde je Straßenklasse
  //  (im Spiel änderbar; gespeicherte Werte haben Vorrang)
  //  null oder 0 = ebenerdiger Übergang an dieser Straßenklasse verboten
  // ==========================================================================
  const LIMITS = {
    highway: null, // Autobahn / Schnellstraße
    major: 30, // Hauptstraße
    medium: 40, // Sammelstraße
    minor: 60, // Nebenstraße
  };

  // Kosten für neu freigeschaltete Übergänge.
  // null = automatisch vom Vanilla-Kreuzer (Commuter Rail) übernehmen.
  const COSTS = {
    baseCost: null, // Baukosten je Übergang
    maintenancePerDay: null, // laufende Kosten je Übergang und Tag
  };

  const OPTIONS = {
    // Heavy Metro und Light Metro bekommen echte Bahnübergänge.
    enableMetroCrossing: true,
    // Jeder Zugtyp bekommt echte Bahnübergänge.
    enableCrossingForAllTrains: false,
  };

  // Zugtypen, die per "enableMetroCrossing" freigeschaltet werden.
  const METRO_TRAIN_IDS = ["heavy-metro", "light-metro"];

  // Alle Eigenschaften rund um Bahnübergänge. Diese werden gesichert,
  // überschrieben und beim Zurücksetzen wiederhergestellt.
  const CROSSING_PROPS = [
    "allowGradeCrossing",
    "allowAtGradeRoadCrossing",
    "gradeCrossingTphLimit",
    "gradeCrossingBaseCost",
    "gradeCrossingMaintenancePerDay",
  ];

  // Notfall-Werte, falls kein Vanilla-Kreuzer gefunden wird.
  const FALLBACK_BASE_COST = 300000;
  const FALLBACK_MAINTENANCE = 5000;

  /**
   * Bekannter Vanilla-Zustand für die Zugtypen, die der Mod verändert.
   * Nötig, weil der Mod beim Neuladen (Strg+Umschalt+R) sonst den bereits
   * veränderten Zustand als "Original" sichern würde.
   */
  const VANILLA_KNOWN = {
    "heavy-metro": { allowGradeCrossing: false, allowAtGradeRoadCrossing: false },
    "light-metro": { allowGradeCrossing: false, allowAtGradeRoadCrossing: false },
  };

  const ROAD_LABELS = {
    highway: "Autobahn / Schnellstraße",
    major: "Hauptstraße",
    medium: "Sammelstraße",
    minor: "Nebenstraße",
  };
  const ROAD_ORDER = ["highway", "major", "medium", "minor"];

  const api = window.SubwayBuilderAPI;
  if (!api) {
    console.error(`${TAG} SubwayBuilderAPI nicht gefunden – Mod wird nicht geladen.`);
    return;
  }

  console.log(`${TAG} v${MOD_VERSION} | API v${api.version}`);

  /** Originalzustand je Zugtyp: { id -> { prop: wert } }. */
  const originals = {};
  let storedOriginals = null;
  let newOriginalsToPersist = false;

  // --------------------------------------------------------------------------
  //  Hilfsfunktionen
  // --------------------------------------------------------------------------

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

  /** Wandelt eine Kosten-Eingabe um ("" = automatisch übernehmen). */
  function normalizeCost(raw) {
    if (raw === null || raw === undefined || raw === "") return null;
    const n = Number(raw);
    if (!Number.isFinite(n) || n < 0) return null;
    return Math.round(n);
  }

  /**
   * Sichert den Originalzustand eines Zugtyps genau einmal.
   * Reihenfolge: gespeichert -> bekannt -> aktuell.
   */
  function captureOriginal(id, trainType) {
    if (id in originals) return originals[id];

    if (storedOriginals && storedOriginals[id]) {
      originals[id] = Object.assign({}, storedOriginals[id]);
      return originals[id];
    }

    const snapshot = {};
    if (VANILLA_KNOWN[id]) {
      // Bekannter Vanilla-Zustand; alle übrigen Eigenschaften fehlen dort.
      for (const p of CROSSING_PROPS) {
        snapshot[p] = VANILLA_KNOWN[id][p];
      }
    } else {
      for (const p of CROSSING_PROPS) {
        const v = trainType ? trainType[p] : undefined;
        snapshot[p] = isLimitObject(v) ? Object.assign({}, v) : v;
      }
      // Ältere Builds nennen das Flag `canCrossRoads`.
      if (
        snapshot.allowAtGradeRoadCrossing === undefined &&
        trainType &&
        Object.prototype.hasOwnProperty.call(trainType, "canCrossRoads")
      ) {
        snapshot.allowAtGradeRoadCrossing = trainType.canCrossRoads;
      }
    }

    originals[id] = snapshot;
    newOriginalsToPersist = true;
    return snapshot;
  }

  /** Baute dieser Zugtyp im Original bereits echte Bahnübergänge? */
  function crossedOriginally(orig) {
    return (
      orig.allowGradeCrossing === true ||
      orig.allowAtGradeRoadCrossing === true ||
      isLimitObject(orig.gradeCrossingTphLimit)
    );
  }

  /** Soll dieser Zugtyp nach aktueller Konfiguration Übergänge bauen? */
  function shouldCross(id, orig) {
    if (crossedOriginally(orig)) return true;
    if (OPTIONS.enableCrossingForAllTrains) return true;
    if (OPTIONS.enableMetroCrossing && METRO_TRAIN_IDS.indexOf(id) !== -1) return true;
    return false;
  }

  /**
   * Sucht einen Zugtyp, der im Vanilla-Spiel echte Bahnübergänge baut.
   * Dessen Kosten dienen als Vorlage für neu freigeschaltete Zugtypen.
   */
  function findVanillaCrossingTemplate(trainTypes) {
    for (const id of Object.keys(trainTypes)) {
      const orig = originals[id];
      if (orig && orig.allowGradeCrossing === true) {
        return {
          id: id,
          baseCost: orig.gradeCrossingBaseCost,
          maintenancePerDay: orig.gradeCrossingMaintenancePerDay,
          tphLimit: orig.gradeCrossingTphLimit,
        };
      }
    }
    return null;
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

    // Erst alle Originale sichern, dann die Kostenvorlage bestimmen.
    for (const [id, trainType] of Object.entries(trainTypes)) {
      captureOriginal(id, trainType);
    }
    const template = findVanillaCrossingTemplate(trainTypes);

    const baseCost =
      COSTS.baseCost !== null
        ? COSTS.baseCost
        : template && template.baseCost !== undefined
          ? template.baseCost
          : FALLBACK_BASE_COST;

    const maintenance =
      COSTS.maintenancePerDay !== null
        ? COSTS.maintenancePerDay
        : template && template.maintenancePerDay !== undefined
          ? template.maintenancePerDay
          : FALLBACK_MAINTENANCE;

    const summary = [];
    let changed = 0;

    for (const [id, trainType] of Object.entries(trainTypes)) {
      const orig = originals[id];
      let update;

      if (restoreOriginal) {
        // Nur Zugtypen anfassen, an denen wir überhaupt etwas verändert haben.
        const touched = CROSSING_PROPS.some(function (p) {
          return orig[p] !== undefined;
        });
        if (!touched && !crossedOriginally(orig)) continue;

        update = {};
        for (const p of CROSSING_PROPS) {
          update[p] = isLimitObject(orig[p]) ? Object.assign({}, orig[p]) : orig[p];
        }
      } else {
        if (!shouldCross(id, orig)) continue;

        // Limit-Objekt: bestehende Struktur erhalten, konfigurierte Klassen
        // überschreiben. So bleiben unbekannte Straßenklassen unangetastet.
        const current = trainType ? trainType.gradeCrossingTphLimit : undefined;
        const base = isLimitObject(current)
          ? current
          : isLimitObject(orig.gradeCrossingTphLimit)
            ? orig.gradeCrossingTphLimit
            : template && isLimitObject(template.tphLimit)
              ? template.tphLimit
              : { highway: null, major: null, medium: null, minor: null };

        const newLimit = {};
        for (const roadClass of Object.keys(base)) {
          newLimit[roadClass] = base[roadClass];
        }
        for (const roadClass of Object.keys(LIMITS)) {
          newLimit[roadClass] = normalizeValue(LIMITS[roadClass]);
        }

        update = {
          allowGradeCrossing: true,
          allowAtGradeRoadCrossing: true,
          gradeCrossingTphLimit: newLimit,
          gradeCrossingBaseCost: baseCost,
          gradeCrossingMaintenancePerDay: maintenance,
        };
      }

      // Ältere Builds nennen das Flag `canCrossRoads` – dann mitschreiben.
      if (trainType && Object.prototype.hasOwnProperty.call(trainType, "canCrossRoads")) {
        update.canCrossRoads = update.allowAtGradeRoadCrossing;
      }

      try {
        api.trains.modifyTrainType(id, update);
        changed++;
        summary.push({
          id: id,
          name: (trainType && trainType.name) || id,
          newlyEnabled: !restoreOriginal && !crossedOriginally(orig),
          crossing: update.allowGradeCrossing,
          limit: update.gradeCrossingTphLimit,
          baseCost: update.gradeCrossingBaseCost,
          maintenancePerDay: update.gradeCrossingMaintenancePerDay,
        });
      } catch (err) {
        console.error(`${TAG} Fehler beim Ändern von Zugtyp "${id}":`, err);
      }
    }

    lastSummary = summary;
    persistOriginals();
    console.log(
      `${TAG} ${reason}: ${changed} Zugtyp(en) angepasst` +
        (template ? ` (Kostenvorlage: ${template.id})` : " (keine Kostenvorlage gefunden)") +
        ".",
      summary
    );
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
      const p = api.storage.set(MOD_ID + ".originals.v2", merged);
      if (p && typeof p.catch === "function") {
        p.catch(function (err) {
          console.warn(`${TAG} Originalwerte konnten nicht gespeichert werden:`, err);
        });
      }
    } catch (err) {
      console.warn(`${TAG} Originalwerte konnten nicht gespeichert werden:`, err);
    }
  }

  function affectedTrainNames() {
    return lastSummary.map(function (s) {
      return s.newlyEnabled ? s.name + " (neu)" : s.name;
    });
  }

  // --------------------------------------------------------------------------
  //  Diagnose (rein lesend)
  // --------------------------------------------------------------------------

  function dumpDiagnostics() {
    const out = { trainTypes: {}, crossingConstants: {}, trackSample: null, routes: null };

    let trainTypes = {};
    try {
      trainTypes = api.trains.getTrainTypes() || {};
    } catch (err) {
      console.error(`${TAG} Diagnose: Zugtypen nicht lesbar:`, err);
    }

    for (const [id, t] of Object.entries(trainTypes)) {
      if (!t) continue;
      const entry = { jetzt: {}, original: originals[id] || "nicht erfasst" };
      for (const p of CROSSING_PROPS) entry.jetzt[p] = t[p];
      out.trainTypes[id] = entry;
    }

    try {
      const constants = api.utils.getConstants() || {};
      for (const k of Object.keys(constants)) {
        if (/cross|grade|road|tph|street/i.test(k)) out.crossingConstants[k] = constants[k];
      }
    } catch (err) {
      console.warn(`${TAG} Diagnose: Konstanten nicht lesbar:`, err);
    }

    try {
      const tracks = api.gameState.getTracks() || [];
      const atGrade = tracks.filter(function (t) {
        return t.startElevation > -3 && t.startElevation < 4.5;
      });
      out.trackSample = {
        totalTracks: tracks.length,
        atGradeTracks: atGrade.length,
        atGradeByTrainType: atGrade.reduce(function (acc, t) {
          acc[t.trackType] = (acc[t.trackType] || 0) + 1;
          return acc;
        }, {}),
      };
    } catch (err) {
      console.warn(`${TAG} Diagnose: Gleise nicht lesbar:`, err);
    }

    // Linien: lässt sich die Wagenzahl zur Laufzeit überhaupt anfassen?
    // Rein lesend – es wird nichts verändert.
    try {
      const routes = api.gameState.getRoutes() || [];
      const again = api.gameState.getRoutes() || [];
      const r = routes[0];

      out.routes = {
        count: routes.length,
        // Liefert getRoutes() dieselben Objekte (Live-Referenz) oder Kopien?
        liveReferences: routes.length > 0 && again.length > 0 ? routes[0] === again[0] : null,
        example: r
          ? {
              id: r.id,
              bullet: r.bullet,
              trainType: r.trainType,
              carsPerTrain: r.carsPerTrain,
              idealTrainCount: r.idealTrainCount,
              trainSchedule: r.trainSchedule,
              keys: Object.keys(r),
              frozen: Object.isFrozen(r),
              sealed: Object.isSealed(r),
              // Ist carsPerTrain überhaupt beschreibbar?
              carsPerTrainDescriptor: Object.getOwnPropertyDescriptor(r, "carsPerTrain"),
            }
          : "keine Linien vorhanden",
      };

      // Wagenzahl der tatsächlich fahrenden Züge je Linie.
      const trains = api.gameState.getTrains() || [];
      out.routes.trainCars = trains.slice(0, 10).map(function (t) {
        return { id: t.id, routeId: t.routeId, cars: t.cars, trainType: t.trainType };
      });
      out.routes.totalTrains = trains.length;
    } catch (err) {
      console.warn(`${TAG} Diagnose: Linien nicht lesbar:`, err);
    }

    console.log(`${TAG} ===== DIAGNOSE BAHNÜBERGANG =====`);
    console.log(out);
    try {
      window.__bahnuebergangDiagnose = out;
      console.log(
        `${TAG} Als Text kopieren mit:  copy(JSON.stringify(window.__bahnuebergangDiagnose, null, 2))`
      );
    } catch (e) {
      /* optional */
    }
    return out;
  }

  // --------------------------------------------------------------------------
  //  Speichern / Laden
  // --------------------------------------------------------------------------

  function saveSettings() {
    try {
      const p = api.storage.set(MOD_ID + ".limits", {
        limits: LIMITS,
        costs: COSTS,
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
        const savedOriginals = await api.storage.get(MOD_ID + ".originals.v2", null);
        if (savedOriginals && typeof savedOriginals === "object") {
          storedOriginals = savedOriginals;
          console.log(`${TAG} Originalwerte aus Speicher geladen.`);
        }

        const saved = await api.storage.get(MOD_ID + ".limits", null);
        if (saved && typeof saved === "object") {
          if (saved.limits) {
            for (const k of Object.keys(saved.limits)) LIMITS[k] = saved.limits[k];
          }
          if (saved.costs) {
            for (const k of Object.keys(saved.costs)) {
              if (k in COSTS) COSTS[k] = saved.costs[k];
            }
          }
          if (saved.options) {
            for (const k of Object.keys(saved.options)) {
              if (k in OPTIONS) OPTIONS[k] = saved.options[k];
            }
          }
          console.log(`${TAG} Gespeicherte Werte geladen:`, LIMITS, COSTS, OPTIONS);
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

  function createPanel() {
    if (!React) return null;

    const InputComp = gameComponents.Input || "input";
    const ButtonComp = gameComponents.Button || "button";

    function numberField(value, onChange, placeholder) {
      return h(InputComp, {
        type: "text",
        inputMode: "numeric",
        value: value,
        placeholder: placeholder,
        onChange: function (e) {
          onChange(
            String(e && e.target ? e.target.value : e).replace(/[^0-9]/g, "")
          );
        },
        style: { width: "110px", textAlign: "right", padding: "2px 6px" },
      });
    }

    function row(label, control) {
      return h(
        "div",
        {
          style: {
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "8px",
            marginBottom: "6px",
          },
        },
        h("span", { style: { fontSize: "13px" } }, label),
        control
      );
    }

    return function CrossingPanel() {
      const initial = {};
      for (const rc of ROAD_ORDER) {
        const v = LIMITS[rc];
        initial[rc] = v === null || v === undefined ? "" : String(v);
      }

      const [draft, setDraft] = React.useState(initial);
      const [baseCost, setBaseCost] = React.useState(
        COSTS.baseCost === null ? "" : String(COSTS.baseCost)
      );
      const [maint, setMaint] = React.useState(
        COSTS.maintenancePerDay === null ? "" : String(COSTS.maintenancePerDay)
      );
      const [metroCross, setMetroCross] = React.useState(OPTIONS.enableMetroCrossing);
      const [allCross, setAllCross] = React.useState(OPTIONS.enableCrossingForAllTrains);
      const [status, setStatus] = React.useState("");

      function apply() {
        for (const rc of ROAD_ORDER) LIMITS[rc] = normalizeValue(draft[rc]);
        COSTS.baseCost = normalizeCost(baseCost);
        COSTS.maintenancePerDay = normalizeCost(maint);
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
            `Bahnübergänge aktualisiert (${n} Zugtypen).`,
            n > 0 ? "success" : "warning"
          );
        } catch (e) {
          /* optional */
        }
      }

      function resetToVanilla() {
        const n = applyOverrides("Auf Vanilla zurückgesetzt", true);
        setMetroCross(false);
        setAllCross(false);
        OPTIONS.enableMetroCrossing = false;
        OPTIONS.enableCrossingForAllTrains = false;
        saveSettings();
        setStatus(`Vanilla-Zustand wiederhergestellt (${n} Zugtypen).`);
        try {
          api.ui.showNotification("Bahnübergänge zurückgesetzt.", "info");
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

      const separator = h("div", {
        style: { height: "1px", background: "currentColor", opacity: 0.15, margin: "10px 0" },
      });

      return h(
        "div",
        { style: { padding: "10px", minWidth: "300px" } },
        h(
          "div",
          { style: { fontSize: "12px", opacity: 0.75, marginBottom: "8px" } },
          "Züge pro Stunde je Straßenklasse. Leer oder 0 = Übergang gesperrt."
        ),
        ROAD_ORDER.map(function (rc) {
          return h(
            "div",
            { key: rc },
            row(
              ROAD_LABELS[rc] || rc,
              numberField(
                draft[rc],
                function (v) {
                  setDraft(function (prev) {
                    return Object.assign({}, prev, { [rc]: v });
                  });
                },
                "gesperrt"
              )
            )
          );
        }),
        separator,
        h(
          "div",
          { style: { fontSize: "12px", opacity: 0.75, marginBottom: "6px" } },
          "Kosten je Übergang (leer = wie Commuter Rail):"
        ),
        row("Baukosten", numberField(baseCost, setBaseCost, "automatisch")),
        row("Unterhalt pro Tag", numberField(maint, setMaint, "automatisch")),
        separator,
        h(
          "div",
          { style: { fontSize: "12px", opacity: 0.75, marginBottom: "6px" } },
          "Bahnübergänge freischalten:"
        ),
        checkbox("Heavy & Light Metro", metroCross, setMetroCross),
        checkbox("Alle Zugtypen", allCross, setAllCross),
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
          ? h("div", { style: { fontSize: "11px", opacity: 0.75, marginTop: "8px" } }, status)
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
      safeUi(function () {
        api.ui.registerComponent("settings-menu", {
          id: MOD_ID + ".panel",
          component: Panel,
        });
      });
      safeUi(function () {
        api.ui.addFloatingPanel({
          id: MOD_ID + ".floating",
          title: "Bahnübergänge",
          icon: "TrainFront",
          defaultWidth: 340,
          render: Panel,
        });
      });
    } else {
      console.warn(`${TAG} React nicht verfügbar – Zahlenfelder werden nicht angezeigt.`);
    }

    safeUi(function () {
      api.ui.addButton("escape-menu", {
        id: MOD_ID + ".apply",
        label: "Bahnübergänge anwenden",
        onClick: function () {
          const n = applyOverrides("Manuell ausgelöst", false);
          api.ui.showNotification(`Bahnübergänge angewendet (${n} Zugtypen).`, "success");
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
