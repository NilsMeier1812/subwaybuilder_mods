/**
 * Zuglängen nach Tageszeit
 * ------------------------
 * Subway Builder Mod: stellt die Wagenzahl einer Linie abhängig von der
 * Uhrzeit ein — z. B. 10 Wagen zur Hauptverkehrszeit, 5 Wagen nachts.
 *
 * Hintergrund: Eine Linie (Route) hat im Spiel nur einen einzigen Wert
 * `carsPerTrain`. Die Nachfrage-Stufen des Spiels (`trainSchedule` mit
 * highDemand / mediumDemand / lowDemand / veryLowDemand) steuern nur die
 * ANZAHL der Züge, nicht deren Länge.
 *
 * `api.gameState.getRoutes()` liefert Live-Referenzen auf den Spielzustand;
 * `carsPerTrain` ist beschreibbar (writable, nicht frozen/sealed). Der Mod
 * schreibt diesen Wert also direkt, sobald sich die Stunde ändert.
 *
 * WICHTIG: Bereits fahrende Züge behalten ihre Länge. Die neue Wagenzahl
 * greift, wenn das Spiel Züge neu einsetzt. Mit der Option "Züge erneuern"
 * lassen sich die Züge einer Linie gezielt austauschen.
 */

(function () {
  "use strict";

  const MOD_ID = "com.nilsmeier.train-length-by-time";
  const MOD_VERSION = "1.0.0";
  const TAG = "[Zuglängen]";

  // ==========================================================================
  //  STANDARDPROFIL  —  Wagenzahl je Zeitfenster
  //  Ein Fenster gilt von "from" (einschließlich) bis "to" (ausschließlich).
  //  Fenster dürfen über Mitternacht gehen (from > to).
  //  Alle nicht abgedeckten Stunden nutzen "fallbackCars".
  // ==========================================================================
  const DEFAULT_PROFILE = {
    windows: [
      { from: 6, to: 9, cars: 10 }, // Morgenspitze
      { from: 9, to: 16, cars: 7 }, // Tagesverkehr
      { from: 16, to: 19, cars: 10 }, // Abendspitze
    ],
    fallbackCars: 5, // Abends/nachts
  };

  const OPTIONS = {
    // Mod aktiv?
    enabled: true,
    // Nach einer Änderung die Züge der Linie austauschen, damit die neue
    // Länge sofort wirkt (statt erst beim nächsten Einsetzen durch das Spiel).
    recycleTrains: false,
  };

  /** Profile je Linie: { routeId -> profil }. Fehlt eins, gilt DEFAULT. */
  const routeProfiles = {};

  const api = window.SubwayBuilderAPI;
  if (!api) {
    console.error(`${TAG} SubwayBuilderAPI nicht gefunden – Mod wird nicht geladen.`);
    return;
  }

  console.log(`${TAG} v${MOD_VERSION} | API v${api.version}`);

  /** Ursprüngliche Wagenzahl je Linie, für "Zurücksetzen". */
  let originalCars = {};
  let originalsDirty = false;

  // --------------------------------------------------------------------------
  //  Hilfsfunktionen
  // --------------------------------------------------------------------------

  function clampInt(value, min, max) {
    const n = Math.round(Number(value));
    if (!Number.isFinite(n)) return min;
    return Math.min(max, Math.max(min, n));
  }

  /** Liegt "hour" im Fenster [from, to)? Fenster darf über Mitternacht gehen. */
  function hourInWindow(hour, from, to) {
    if (from === to) return false;
    if (from < to) return hour >= from && hour < to;
    return hour >= from || hour < to; // über Mitternacht
  }

  /** Das für diese Linie geltende Profil. */
  function profileFor(routeId) {
    return routeProfiles[routeId] || DEFAULT_PROFILE;
  }

  /** Gewünschte Wagenzahl für eine Linie zur gegebenen Stunde. */
  function targetCarsFor(routeId, hour) {
    const profile = profileFor(routeId);
    for (const w of profile.windows) {
      if (hourInWindow(hour, w.from, w.to)) return w.cars;
    }
    return profile.fallbackCars;
  }

  /**
   * Grenzen des Zugtyps holen. Ohne diese Begrenzung könnte man Züge bauen,
   * die länger als der Bahnsteig sind.
   */
  function carLimitsFor(route) {
    let min = 1;
    let max = 99;
    try {
      const t = route && route.trainType ? api.trains.getTrainType(route.trainType) : null;
      if (t && t.stats) {
        if (Number.isFinite(t.stats.minCars)) min = t.stats.minCars;
        if (Number.isFinite(t.stats.maxCars)) max = t.stats.maxCars;
      }
    } catch (err) {
      console.warn(`${TAG} Zugtyp-Grenzen nicht lesbar:`, err);
    }
    return { min: min, max: max };
  }

  // --------------------------------------------------------------------------
  //  Kernlogik
  // --------------------------------------------------------------------------

  let lastAppliedHour = null;
  let lastSummary = [];

  /**
   * Setzt die Wagenzahl aller Linien passend zur aktuellen Stunde.
   * @param {string} reason  Nur für die Konsolenausgabe.
   * @param {boolean} force  true = auch anwenden, wenn die Stunde gleich blieb.
   */
  function applyForCurrentHour(reason, force) {
    if (!OPTIONS.enabled && !force) return 0;

    let hour;
    let routes;
    try {
      hour = api.gameState.getCurrentHour();
      routes = api.gameState.getRoutes() || [];
    } catch (err) {
      console.error(`${TAG} Spielzustand nicht lesbar:`, err);
      return 0;
    }

    if (!force && hour === lastAppliedHour) return 0;
    lastAppliedHour = hour;

    const summary = [];
    let changed = 0;

    for (const route of routes) {
      if (!route || !route.id) continue;

      // Ursprungswert einmalig sichern.
      if (!(route.id in originalCars)) {
        originalCars[route.id] = route.carsPerTrain;
        originalsDirty = true;
      }

      const limits = carLimitsFor(route);
      const target = clampInt(targetCarsFor(route.id, hour), limits.min, limits.max);
      const before = route.carsPerTrain;
      if (before === target) continue;

      try {
        route.carsPerTrain = target;
        changed++;
        summary.push({
          route: route.bullet || route.id,
          trainType: route.trainType,
          von: before,
          nach: target,
          grenzen: limits.min + "-" + limits.max,
        });
      } catch (err) {
        console.error(`${TAG} Linie "${route.bullet || route.id}" nicht änderbar:`, err);
      }
    }

    if (changed > 0 && OPTIONS.recycleTrains) {
      recycleTrainsForRoutes(
        summary.map(function (s) {
          return s.route;
        })
      );
    }

    lastSummary = summary;
    persistOriginals();
    if (changed > 0) {
      console.log(`${TAG} ${reason} — Stunde ${hour}: ${changed} Linie(n) angepasst.`, summary);
    }
    return changed;
  }

  /**
   * Tauscht die Züge betroffener Linien aus, damit die neue Wagenzahl sofort
   * greift. Ohne diesen Schritt behalten fahrende Züge ihre alte Länge.
   */
  function recycleTrainsForRoutes(routeLabels) {
    let routes;
    let trains;
    try {
      routes = api.gameState.getRoutes() || [];
      trains = api.gameState.getTrains() || [];
    } catch (err) {
      console.warn(`${TAG} Züge nicht lesbar:`, err);
      return;
    }

    const affected = routes.filter(function (r) {
      return routeLabels.indexOf(r.bullet || r.id) !== -1;
    });

    for (const route of affected) {
      const routeTrains = trains.filter(function (t) {
        return t.routeId === route.id;
      });
      if (!routeTrains.length) continue;

      let removed = 0;
      for (const t of routeTrains) {
        try {
          if (api.build.deleteTrain(t.id)) removed++;
        } catch (err) {
          console.warn(`${TAG} Zug ${t.id} nicht entfernbar:`, err);
        }
      }

      for (let i = 0; i < removed; i++) {
        try {
          api.build.addTrainToRoute(route.id, 0);
        } catch (err) {
          console.warn(`${TAG} Zug für Linie ${route.bullet || route.id} nicht einsetzbar:`, err);
          break;
        }
      }
      console.log(`${TAG} Linie ${route.bullet || route.id}: ${removed} Zug/Züge erneuert.`);
    }
  }

  /** Stellt die ursprünglichen Wagenzahlen wieder her. */
  function restoreOriginals() {
    let routes;
    try {
      routes = api.gameState.getRoutes() || [];
    } catch (err) {
      console.error(`${TAG} Linien nicht lesbar:`, err);
      return 0;
    }

    let changed = 0;
    for (const route of routes) {
      if (!route || !(route.id in originalCars)) continue;
      const orig = originalCars[route.id];
      if (orig === undefined || route.carsPerTrain === orig) continue;
      try {
        route.carsPerTrain = orig;
        changed++;
      } catch (err) {
        console.error(`${TAG} Linie nicht zurücksetzbar:`, err);
      }
    }
    lastAppliedHour = null;
    console.log(`${TAG} Zurückgesetzt: ${changed} Linie(n).`);
    return changed;
  }

  // --------------------------------------------------------------------------
  //  Speichern / Laden
  // --------------------------------------------------------------------------

  function storageSet(key, value) {
    try {
      const p = api.storage.set(MOD_ID + "." + key, value);
      if (p && typeof p.catch === "function") {
        p.catch(function (err) {
          console.warn(`${TAG} Speichern fehlgeschlagen:`, err);
        });
      }
    } catch (err) {
      console.warn(`${TAG} Speichern fehlgeschlagen:`, err);
    }
  }

  function saveSettings() {
    storageSet("settings", {
      defaultProfile: DEFAULT_PROFILE,
      routeProfiles: routeProfiles,
      options: OPTIONS,
    });
  }

  function persistOriginals() {
    if (!originalsDirty) return;
    originalsDirty = false;
    storageSet("originalCars", originalCars);
  }

  let settingsPromise = null;

  function loadSettings() {
    if (settingsPromise) return settingsPromise;
    settingsPromise = (async function () {
      try {
        const savedOriginals = await api.storage.get(MOD_ID + ".originalCars", null);
        if (savedOriginals && typeof savedOriginals === "object") {
          originalCars = savedOriginals;
        }

        const saved = await api.storage.get(MOD_ID + ".settings", null);
        if (saved && typeof saved === "object") {
          if (saved.defaultProfile && Array.isArray(saved.defaultProfile.windows)) {
            DEFAULT_PROFILE.windows = saved.defaultProfile.windows;
            DEFAULT_PROFILE.fallbackCars = saved.defaultProfile.fallbackCars;
          }
          if (saved.routeProfiles && typeof saved.routeProfiles === "object") {
            for (const k of Object.keys(saved.routeProfiles)) {
              routeProfiles[k] = saved.routeProfiles[k];
            }
          }
          if (saved.options) {
            for (const k of Object.keys(saved.options)) {
              if (k in OPTIONS) OPTIONS[k] = saved.options[k];
            }
          }
          console.log(`${TAG} Gespeicherte Einstellungen geladen.`);
        }
      } catch (err) {
        console.warn(`${TAG} Keine gespeicherten Einstellungen geladen:`, err);
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

    function num(value, onChange, width, placeholder) {
      return h(InputComp, {
        type: "text",
        inputMode: "numeric",
        value: value,
        placeholder: placeholder || "",
        onChange: function (e) {
          onChange(String(e && e.target ? e.target.value : e).replace(/[^0-9]/g, ""));
        },
        style: { width: width || "56px", textAlign: "right", padding: "2px 6px" },
      });
    }

    return function TrainLengthPanel() {
      const [selected, setSelected] = React.useState("__default__");
      const [tick, setTick] = React.useState(0);
      const [status, setStatus] = React.useState("");

      let routes = [];
      try {
        routes = api.gameState.getRoutes() || [];
      } catch (e) {
        routes = [];
      }

      const isDefault = selected === "__default__";
      const profile = isDefault ? DEFAULT_PROFILE : profileFor(selected);
      // Für eine Linie ohne eigenes Profil zunächst eine Kopie des Standards.
      const working =
        isDefault || routeProfiles[selected]
          ? profile
          : { windows: profile.windows.map(function (w) {
              return { from: w.from, to: w.to, cars: w.cars };
            }), fallbackCars: profile.fallbackCars };

      function commit(next) {
        if (isDefault) {
          DEFAULT_PROFILE.windows = next.windows;
          DEFAULT_PROFILE.fallbackCars = next.fallbackCars;
        } else {
          routeProfiles[selected] = next;
        }
        saveSettings();
        setTick(tick + 1);
      }

      function setWindowField(idx, field, raw) {
        const next = {
          windows: working.windows.map(function (w, i) {
            if (i !== idx) return { from: w.from, to: w.to, cars: w.cars };
            const copy = { from: w.from, to: w.to, cars: w.cars };
            copy[field] = raw === "" ? 0 : Number(raw);
            return copy;
          }),
          fallbackCars: working.fallbackCars,
        };
        commit(next);
      }

      function setFallback(raw) {
        commit({
          windows: working.windows.map(function (w) {
            return { from: w.from, to: w.to, cars: w.cars };
          }),
          fallbackCars: raw === "" ? 0 : Number(raw),
        });
      }

      const rows = working.windows.map(function (w, idx) {
        return h(
          "div",
          {
            key: idx,
            style: {
              display: "flex",
              alignItems: "center",
              gap: "6px",
              marginBottom: "6px",
              fontSize: "12px",
            },
          },
          h("span", { style: { width: "28px" } }, "von"),
          num(String(w.from), function (v) {
            setWindowField(idx, "from", v);
          }),
          h("span", null, "bis"),
          num(String(w.to), function (v) {
            setWindowField(idx, "to", v);
          }),
          h("span", { style: { marginLeft: "6px" } }, "Uhr →"),
          num(String(w.cars), function (v) {
            setWindowField(idx, "cars", v);
          }),
          h("span", null, "Wagen")
        );
      });

      const routeOptions = [
        h("option", { key: "__default__", value: "__default__" }, "Standard (alle Linien)"),
      ].concat(
        routes.map(function (r) {
          const own = routeProfiles[r.id] ? " ✓" : "";
          return h(
            "option",
            { key: r.id, value: r.id },
            (r.bullet || r.id.slice(0, 6)) + " – " + (r.trainType || "?") + own
          );
        })
      );

      let currentHour = "?";
      try {
        currentHour = api.gameState.getCurrentHour();
      } catch (e) {
        /* egal */
      }

      return h(
        "div",
        { style: { padding: "10px", minWidth: "330px" } },
        h(
          "div",
          { style: { fontSize: "12px", opacity: 0.75, marginBottom: "8px" } },
          "Wagenzahl je Tageszeit. Aktuelle Spielstunde: " + currentHour
        ),
        h("select", {
          value: selected,
          onChange: function (e) {
            setSelected(e.target.value);
          },
          style: { width: "100%", marginBottom: "10px", padding: "3px" },
        }, routeOptions),
        rows,
        h(
          "div",
          { style: { display: "flex", alignItems: "center", gap: "6px", fontSize: "12px" } },
          h("span", { style: { width: "104px" } }, "sonst →"),
          num(String(working.fallbackCars), setFallback),
          h("span", null, "Wagen")
        ),
        !isDefault && routeProfiles[selected]
          ? h(
              "div",
              { style: { marginTop: "8px" } },
              h(
                ButtonComp,
                {
                  variant: "ghost",
                  onClick: function () {
                    delete routeProfiles[selected];
                    saveSettings();
                    setTick(tick + 1);
                    setStatus("Linie nutzt wieder das Standardprofil.");
                  },
                },
                "Eigenes Profil entfernen"
              )
            )
          : null,
        h("div", {
          style: { height: "1px", background: "currentColor", opacity: 0.15, margin: "10px 0" },
        }),
        h(
          "label",
          { style: { display: "flex", alignItems: "center", gap: "6px", fontSize: "12px" } },
          h("input", {
            type: "checkbox",
            checked: OPTIONS.enabled,
            onChange: function (e) {
              OPTIONS.enabled = e.target.checked;
              saveSettings();
              setTick(tick + 1);
            },
          }),
          "Automatisch nach Tageszeit umstellen"
        ),
        h(
          "label",
          {
            style: {
              display: "flex",
              alignItems: "center",
              gap: "6px",
              fontSize: "12px",
              marginTop: "4px",
            },
          },
          h("input", {
            type: "checkbox",
            checked: OPTIONS.recycleTrains,
            onChange: function (e) {
              OPTIONS.recycleTrains = e.target.checked;
              saveSettings();
              setTick(tick + 1);
            },
          }),
          "Züge sofort erneuern (sonst erst beim Neueinsetzen)"
        ),
        h(
          "div",
          { style: { display: "flex", gap: "8px", marginTop: "10px" } },
          h(
            ButtonComp,
            {
              onClick: function () {
                const n = applyForCurrentHour("Manuell angewendet", true);
                setStatus(
                  n > 0
                    ? n + " Linie(n) angepasst: " +
                        lastSummary
                          .map(function (s) {
                            return s.route + " " + s.von + "→" + s.nach;
                          })
                          .join(", ")
                    : "Nichts zu ändern – alle Linien passen schon."
                );
              },
            },
            "Jetzt anwenden"
          ),
          h(
            ButtonComp,
            {
              variant: "outline",
              onClick: function () {
                const n = restoreOriginals();
                setStatus(n + " Linie(n) auf Ursprungswert zurückgesetzt.");
              },
            },
            "Zurücksetzen"
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
    if (!Panel) {
      console.warn(`${TAG} React nicht verfügbar – Panel wird nicht angezeigt.`);
      return;
    }

    safeUi(function () {
      api.ui.registerComponent("settings-menu", {
        id: MOD_ID + ".panel",
        component: Panel,
      });
    });

    safeUi(function () {
      api.ui.addFloatingPanel({
        id: MOD_ID + ".floating",
        title: "Zuglängen nach Tageszeit",
        icon: "Clock",
        defaultWidth: 360,
        render: Panel,
      });
    });
  }

  // --------------------------------------------------------------------------
  //  Initialisierung
  // --------------------------------------------------------------------------

  let uiReady = false;
  let pollTimer = null;

  /**
   * Es gibt keinen Hook für den Stundenwechsel, deshalb wird die Spielzeit
   * regelmäßig abgefragt. Angewendet wird nur, wenn sich die Stunde ändert.
   */
  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(function () {
      try {
        applyForCurrentHour("Stundenwechsel", false);
      } catch (err) {
        console.error(`${TAG} Fehler beim Anwenden:`, err);
      }
    }, 3000);
  }

  function init(reason) {
    loadSettings().then(function () {
      applyForCurrentHour(reason, true);
      startPolling();
      if (!uiReady) {
        uiReady = true;
        setupUi();
      }
    });
  }

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

  init("Sofort-Anwendung beim Laden");
})();
