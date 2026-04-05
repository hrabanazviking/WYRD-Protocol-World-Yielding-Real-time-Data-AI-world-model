/**
 * WyrdForge — WYRD Protocol Construct 3 addon (Phase 11D).
 * Runtime instance class.
 *
 * This is the core of the addon. Each game instance of the WyrdForge
 * plugin object is backed by one of these. Since the plugin is
 * single-global there will only ever be one.
 *
 * Implements:
 *   - WyrdHTTPServer fetch()-based client (no external dependencies)
 *   - Init / QueryCharacter / PushObservation / PushFact action handlers
 *   - IsReady condition
 *   - LastResponse / LastError expressions
 *   - OnQueryComplete / OnQueryError trigger dispatch
 *
 * Usage (Event Sheet):
 *   On start of layout:
 *     WyrdForge | Initialize | host "localhost" port 8765 timeout 8000
 *
 *   On trigger:
 *     WyrdForge | Query character context | "sigrid" "What is happening?"
 *   + WyrdForge | On query complete:
 *     → use WyrdForge.LastResponse expression
 */
"use strict";

{
  const C3 = globalThis.C3;

  // -------------------------------------------------------------------------
  // Pure helpers (exported to WyrdForge._helpers for testing)
  // -------------------------------------------------------------------------

  /**
   * Normalize a name to a valid WYRD persona_id.
   * @param {string} name
   * @returns {string}
   */
  function normalizePersonaId(name) {
    return (name || "")
      .toLowerCase()
      .replace(/[^a-z0-9_]/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 64);
  }

  /**
   * Build a /query request body.
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
   * Build a /event request body.
   * @param {string} eventType  "observation" | "fact"
   * @param {object} payload
   * @returns {object}
   */
  function buildEventBody(eventType, payload) {
    return { event_type: eventType, payload };
  }

  /**
   * Parse and validate a JSON response from WyrdHTTPServer.
   * @param {Response} response  — fetch() Response
   * @returns {Promise<object>}  — parsed body or throws on error
   */
  async function parseResponse(response) {
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(`WyrdForge: invalid JSON response (HTTP ${response.status})`);
    }
    if (!response.ok) {
      throw new Error(
        `WyrdForge: HTTP ${response.status} — ${data?.error ?? "unknown error"}`
      );
    }
    return data;
  }

  // -------------------------------------------------------------------------
  // Instance class
  // -------------------------------------------------------------------------

  C3.Plugins["WyrdForge"].Instance = class WyrdForgeInstance extends C3.SDKInstanceBase {
    constructor(inst, properties) {
      super(inst);

      // Plugin properties (from addon.json defaults)
      this._host = (properties && properties[0]) ? String(properties[0]) : "localhost";
      this._port = (properties && properties[1]) ? Number(properties[1]) : 8765;
      this._timeoutMs = (properties && properties[2]) ? Number(properties[2]) : 8000;
      this._enabled = (properties && properties[3] !== undefined) ? Boolean(properties[3]) : true;

      this._initialized = false;
      this._lastResponse = "";
      this._lastError = "";
    }

    Release() {
      super.Release();
    }

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    /** @returns {string} */
    get _baseUrl() {
      return `http://${this._host}:${this._port}`;
    }

    /** @returns {boolean} */
    _IsReady() {
      return this._initialized && this._enabled;
    }

    /**
     * Send a POST request to WyrdHTTPServer.
     * @param {string} path
     * @param {object} body
     * @returns {Promise<object>}
     */
    async _post(path, body) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this._timeoutMs);
      try {
        const response = await fetch(this._baseUrl + path, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        return await parseResponse(response);
      } finally {
        clearTimeout(timer);
      }
    }

    // -----------------------------------------------------------------------
    // Action implementations
    // -----------------------------------------------------------------------

    /**
     * Configure the WyrdHTTPServer connection.
     * @param {string} host
     * @param {number} port
     * @param {number} timeoutMs
     */
    _Init(host, port, timeoutMs) {
      this._host = String(host || "localhost");
      this._port = Number(port) || 8765;
      this._timeoutMs = Number(timeoutMs) || 8000;
      this._initialized = true;
      this._lastError = "";
    }

    /**
     * Query WYRD world context for a character.
     * Fires OnQueryComplete or OnQueryError trigger on completion.
     * @param {string} personaId
     * @param {string} query
     */
    async _QueryCharacter(personaId, query) {
      if (!this._IsReady()) return;

      const pid = normalizePersonaId(personaId);
      const body = buildQueryBody(pid, query);

      try {
        const data = await this._post("/query", body);
        this._lastResponse = String(data?.response ?? data?.context ?? "");
        this._lastError = "";
        this._TriggerOnQueryComplete();
      } catch (err) {
        this._lastError = err.message || String(err);
        this._TriggerOnQueryError();
      }
    }

    /**
     * Push an event (observation or fact) to WYRD.
     * Fires OnQueryError trigger on failure.
     * @param {string} eventType
     * @param {object} payload
     */
    async _PushEvent(eventType, payload) {
      if (!this._IsReady()) return;

      const body = buildEventBody(eventType, payload);
      try {
        await this._post("/event", body);
        this._lastError = "";
      } catch (err) {
        this._lastError = err.message || String(err);
        this._TriggerOnQueryError();
      }
    }

    // -----------------------------------------------------------------------
    // Trigger dispatch
    // -----------------------------------------------------------------------

    _TriggerOnQueryComplete() {
      this._GetCnds("OnQueryComplete").then(cnd => {
        if (cnd) this._runtime.Trigger(cnd, this._inst);
      }).catch(() => {});
    }

    _TriggerOnQueryError() {
      this._GetCnds("OnQueryError").then(cnd => {
        if (cnd) this._runtime.Trigger(cnd, this._inst);
      }).catch(() => {});
    }

    // -----------------------------------------------------------------------
    // State save/load (for C3 save/load game state support)
    // -----------------------------------------------------------------------

    SaveToJson() {
      return {
        host: this._host,
        port: this._port,
        timeoutMs: this._timeoutMs,
        enabled: this._enabled,
        initialized: this._initialized,
        lastResponse: this._lastResponse,
        lastError: this._lastError,
      };
    }

    LoadFromJson(o) {
      this._host = o.host || "localhost";
      this._port = Number(o.port) || 8765;
      this._timeoutMs = Number(o.timeoutMs) || 8000;
      this._enabled = Boolean(o.enabled);
      this._initialized = Boolean(o.initialized);
      this._lastResponse = o.lastResponse || "";
      this._lastError = o.lastError || "";
    }
  };

  // -------------------------------------------------------------------------
  // Expose pure helpers for testing
  // -------------------------------------------------------------------------

  if (typeof globalThis !== "undefined") {
    globalThis.WyrdForgeHelpers = {
      normalizePersonaId,
      buildQueryBody,
      buildEventBody,
      parseResponse,
    };
  }
}
