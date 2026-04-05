/*:
 * @target MZ MV
 * @plugindesc WyrdForge — WYRD Protocol integration for RPG Maker MZ/MV
 * @author RuneForgeAI
 * @version 1.0.0
 * @url https://github.com/hrabanazviking/WYRD-Protocol-World-Yielding-Real-time-Data-AI-world-model
 *
 * @help
 * WyrdForge connects RPG Maker MZ/MV to a running WyrdHTTPServer.
 * It provides plugin commands for querying world context, syncing
 * actor data, and writing observations to WYRD memory.
 *
 * Requires a WyrdHTTPServer running on localhost (or configured host).
 *
 * Plugin Commands (MZ):
 *   WyrdForge QueryContext
 *     - ActorId: Game actor ID (number)
 *     - Query: Text query (optional)
 *     - VariableId: Game variable ID to store the response
 *
 *   WyrdForge SyncActor
 *     - ActorId: Game actor ID to sync to WYRD
 *
 *   WyrdForge WriteObservation
 *     - Title: Observation title
 *     - Summary: Observation summary text
 *
 * For MV, use Plugin Command text:
 *   WyrdForge query <actorId> <variableId> [query text]
 *   WyrdForge sync <actorId>
 *   WyrdForge observe <title> <summary>
 *
 * @param host
 * @text WYRD Server Host
 * @type string
 * @default localhost
 * @desc Hostname where WyrdHTTPServer is running.
 *
 * @param port
 * @text WYRD Server Port
 * @type number
 * @default 8765
 * @desc Port where WyrdHTTPServer is listening.
 *
 * @param timeoutMs
 * @text Request Timeout (ms)
 * @type number
 * @default 8000
 * @desc HTTP request timeout in milliseconds.
 *
 * @param enabled
 * @text Enable WyrdForge
 * @type boolean
 * @default true
 * @desc Toggle WyrdForge on/off.
 *
 * @command QueryContext
 * @text Query World Context
 * @desc Query WYRD world context for an actor and store the result in a game variable.
 *
 * @arg actorId
 * @text Actor ID
 * @type actor
 * @desc The RPG Maker actor to query WYRD context for.
 *
 * @arg variableId
 * @text Variable ID
 * @type variable
 * @desc Game variable to store the WYRD context response.
 *
 * @arg query
 * @text Query
 * @type string
 * @default
 * @desc Optional query text to refine world context.
 *
 * @command SyncActor
 * @text Sync Actor to WYRD
 * @desc Register an RPG Maker actor as a WYRD entity.
 *
 * @arg actorId
 * @text Actor ID
 * @type actor
 * @desc The actor to sync.
 *
 * @command WriteObservation
 * @text Write Observation
 * @desc Write a world observation to WYRD memory.
 *
 * @arg title
 * @text Title
 * @type string
 * @desc Short title for the observation.
 *
 * @arg summary
 * @text Summary
 * @type string
 * @desc Description of what happened.
 */

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Pure helpers (exported via WyrdForge namespace — testable in isolation)
  // -------------------------------------------------------------------------

  /**
   * Normalize an actor name to a WYRD persona_id.
   * @param {string} name
   * @returns {string}
   */
  function normalizePersonaId(name) {
    return (name || "")
      .toLowerCase()
      .replace(/[^a-z0-9_]/g, "_")
      .replace(/_+/g, "_")
      .slice(0, 64);
  }

  /**
   * Build a WYRD /query request body.
   * @param {string} personaId
   * @param {string} query
   * @returns {object}
   */
  function buildQueryBody(personaId, query) {
    return {
      persona_id: personaId,
      user_input: query || "What is the current world state?",
      use_turn_loop: false,
    };
  }

  /**
   * Build a WYRD /event request body for an observation.
   * @param {string} title
   * @param {string} summary
   * @returns {object}
   */
  function buildObservationBody(title, summary) {
    return {
      event_type: "observation",
      payload: { title, summary },
    };
  }

  /**
   * Build a WYRD /event request body for a fact.
   * @param {string} personaId
   * @param {string} key
   * @param {string} value
   * @returns {object}
   */
  function buildFactBody(personaId, key, value) {
    return {
      event_type: "fact",
      payload: { subject_id: personaId, key, value },
    };
  }

  /**
   * Parse a legacy MV plugin command string.
   * Format: WyrdForge <subcommand> <args...>
   * @param {string} command   — e.g. "WyrdForge"
   * @param {string[]} args    — rest of plugin command tokens
   * @returns {{ subcommand: string, rest: string[] }|null}
   */
  function parseMVCommand(command, args) {
    if ((command || "").toLowerCase() !== "wyrdforge") return null;
    const sub = (args[0] || "").toLowerCase();
    return { subcommand: sub, rest: args.slice(1) };
  }

  /**
   * Extract actor data from $gameActors for syncing.
   * @param {object} gameActors  — $gameActors object
   * @param {number} actorId
   * @returns {{ name: string, class: string, level: number }|null}
   */
  function extractActorData(gameActors, actorId) {
    const actor = gameActors?.actor?.(actorId);
    if (!actor) return null;
    return {
      name: typeof actor.name === "function" ? actor.name() : (actor.name ?? ""),
      class: actor.currentClass ? (actor.currentClass()?.name ?? "") : (actor._className ?? ""),
      level: actor.level ?? 1,
    };
  }

  // -------------------------------------------------------------------------
  // WyrdClient (inline, no ES module dependencies)
  // -------------------------------------------------------------------------

  function WyrdClient(host, port, timeoutMs) {
    this.baseUrl = "http://" + host + ":" + port;
    this.timeoutMs = timeoutMs || 8000;
  }

  WyrdClient.prototype._post = function (path, bodyObj) {
    const self = this;
    return new Promise(function (resolve, reject) {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", self.baseUrl + path, true);
      xhr.setRequestHeader("Content-Type", "application/json");
      xhr.timeout = self.timeoutMs;
      xhr.ontimeout = function () { reject(new Error("Request timed out")); };
      xhr.onerror = function () { reject(new Error("Network error")); };
      xhr.onload = function () {
        let data;
        try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error((data && data.error) ? data.error : "HTTP " + xhr.status));
        }
      };
      xhr.send(JSON.stringify(bodyObj));
    });
  };

  WyrdClient.prototype._get = function (path) {
    const self = this;
    return new Promise(function (resolve, reject) {
      const xhr = new XMLHttpRequest();
      xhr.open("GET", self.baseUrl + path, true);
      xhr.timeout = self.timeoutMs;
      xhr.ontimeout = function () { reject(new Error("Request timed out")); };
      xhr.onerror = function () { reject(new Error("Network error")); };
      xhr.onload = function () {
        let data;
        try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error((data && data.error) ? data.error : "HTTP " + xhr.status));
        }
      };
      xhr.send();
    });
  };

  WyrdClient.prototype.health = function () { return this._get("/health"); };
  WyrdClient.prototype.query = function (personaId, query) {
    return this._post("/query", buildQueryBody(personaId, query));
  };
  WyrdClient.prototype.pushEvent = function (eventType, payload) {
    return this._post("/event", { event_type: eventType, payload });
  };

  // -------------------------------------------------------------------------
  // Plugin parameters
  // -------------------------------------------------------------------------

  const params = PluginManager.parameters("WyrdForge");
  const _host = String(params.host || "localhost");
  const _port = Number(params.port || 8765);
  const _timeoutMs = Number(params.timeoutMs || 8000);
  const _enabled = String(params.enabled) !== "false";

  function getClient() {
    return new WyrdClient(_host, _port, _timeoutMs);
  }

  // -------------------------------------------------------------------------
  // MZ Plugin Commands
  // -------------------------------------------------------------------------

  if (typeof PluginManager.registerCommand === "function") {
    PluginManager.registerCommand("WyrdForge", "QueryContext", async function (args) {
      if (!_enabled) return;
      const actorId = Number(args.actorId);
      const variableId = Number(args.variableId);
      const query = String(args.query || "");

      const actorData = extractActorData($gameActors, actorId);
      const personaId = normalizePersonaId(actorData?.name || String(actorId));

      try {
        const result = await getClient().query(personaId, query);
        if (variableId > 0) {
          $gameVariables.setValue(variableId, result?.response ?? "");
        }
      } catch (err) {
        console.error("WyrdForge QueryContext error:", err.message);
      }
    });

    PluginManager.registerCommand("WyrdForge", "SyncActor", async function (args) {
      if (!_enabled) return;
      const actorId = Number(args.actorId);
      const actorData = extractActorData($gameActors, actorId);
      if (!actorData) return;

      const personaId = normalizePersonaId(actorData.name);
      const client = getClient();
      try {
        await client.pushEvent("fact", { subject_id: personaId, key: "name", value: actorData.name });
        if (actorData.class) {
          await client.pushEvent("fact", { subject_id: personaId, key: "class", value: actorData.class });
        }
        await client.pushEvent("fact", { subject_id: personaId, key: "level", value: String(actorData.level) });
      } catch (err) {
        console.error("WyrdForge SyncActor error:", err.message);
      }
    });

    PluginManager.registerCommand("WyrdForge", "WriteObservation", async function (args) {
      if (!_enabled) return;
      const title = String(args.title || "");
      const summary = String(args.summary || "");
      try {
        await getClient().pushEvent("observation", { title, summary });
      } catch (err) {
        console.error("WyrdForge WriteObservation error:", err.message);
      }
    });
  }

  // -------------------------------------------------------------------------
  // MV Plugin Commands (legacy)
  // -------------------------------------------------------------------------

  const _alias_pluginCommand = Game_Interpreter.prototype.pluginCommand;
  Game_Interpreter.prototype.pluginCommand = function (command, args) {
    _alias_pluginCommand.call(this, command, args);
    if (!_enabled) return;

    const parsed = parseMVCommand(command, args);
    if (!parsed) return;

    const client = getClient();
    if (parsed.subcommand === "query") {
      const actorId = Number(parsed.rest[0]) || 1;
      const variableId = Number(parsed.rest[1]) || 0;
      const query = parsed.rest.slice(2).join(" ");
      const actorData = extractActorData($gameActors, actorId);
      const personaId = normalizePersonaId(actorData?.name || String(actorId));
      client.query(personaId, query).then(function (result) {
        if (variableId > 0) $gameVariables.setValue(variableId, result?.response ?? "");
      }).catch(function (err) { console.error("WyrdForge query error:", err.message); });

    } else if (parsed.subcommand === "sync") {
      const actorId = Number(parsed.rest[0]) || 1;
      const actorData = extractActorData($gameActors, actorId);
      if (actorData) {
        const personaId = normalizePersonaId(actorData.name);
        client.pushEvent("fact", { subject_id: personaId, key: "name", value: actorData.name })
          .catch(function (err) { console.error("WyrdForge sync error:", err.message); });
      }

    } else if (parsed.subcommand === "observe") {
      const title = parsed.rest[0] || "";
      const summary = parsed.rest.slice(1).join(" ");
      client.pushEvent("observation", { title, summary })
        .catch(function (err) { console.error("WyrdForge observe error:", err.message); });
    }
  };

  // -------------------------------------------------------------------------
  // Public namespace (for testing and external access)
  // -------------------------------------------------------------------------

  window.WyrdForge = {
    normalizePersonaId,
    buildQueryBody,
    buildObservationBody,
    buildFactBody,
    parseMVCommand,
    extractActorData,
    WyrdClient,
  };

})();
