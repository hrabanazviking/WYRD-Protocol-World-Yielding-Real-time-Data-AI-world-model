/**
 * WyrdForge — WYRD Protocol core logic for D&D Beyond extension (Phase 10E).
 * Pure functions shared between content.js, popup.js, and background.js.
 * No DOM or browser API dependencies — fully testable in Node.js.
 */

// ---------------------------------------------------------------------------
// WyrdClient
// ---------------------------------------------------------------------------

export class WyrdConnectionError extends Error {
  constructor(message, cause) {
    super(message);
    this.name = "WyrdConnectionError";
    this.cause = cause;
  }
}

export class WyrdAPIError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "WyrdAPIError";
    this.status = status;
    this.body = body;
  }
}

export class WyrdClient {
  constructor({ host = "localhost", port = 8765, timeoutMs = 8000 } = {}) {
    this.baseUrl = `http://${host}:${port}`;
    this.timeoutMs = timeoutMs;
  }

  async health() { return this._get("/health"); }
  async getWorld() { return this._get("/world"); }

  async query(personaId, userInput = "", { locationId = null, useTurnLoop = false } = {}) {
    const body = { persona_id: personaId, user_input: userInput, use_turn_loop: useTurnLoop };
    if (locationId) body.location_id = locationId;
    return this._post("/query", body);
  }

  async pushEvent(eventType, payload) {
    return this._post("/event", { event_type: eventType, payload });
  }

  async _get(path) {
    let resp;
    try {
      resp = await fetch(`${this.baseUrl}${path}`, {
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      throw new WyrdConnectionError(`Cannot reach WyrdHTTPServer at ${this.baseUrl}`, err);
    }
    return this._parseResponse(resp);
  }

  async _post(path, body) {
    let resp;
    try {
      resp = await fetch(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      throw new WyrdConnectionError(`Cannot reach WyrdHTTPServer at ${this.baseUrl}`, err);
    }
    return this._parseResponse(resp);
  }

  async _parseResponse(resp) {
    let data;
    try { data = await resp.json(); } catch { data = null; }
    if (!resp.ok) {
      const msg = (data && data.error) ? data.error : `HTTP ${resp.status}`;
      throw new WyrdAPIError(msg, resp.status, data);
    }
    return data;
  }
}

// ---------------------------------------------------------------------------
// DDB page scraper helpers (pure DOM-free logic, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Classify a DDB URL.
 * @param {string} url
 * @returns {"character"|"monster"|"npc"|"unknown"}
 */
export function classifyDDBUrl(url) {
  if (/dndbeyond\.com\/characters\/\d+/.test(url)) return "character";
  if (/dndbeyond\.com\/monsters\//.test(url)) return "monster";
  if (/dndbeyond\.com\/npcs\//.test(url)) return "npc";
  return "unknown";
}

/**
 * Extract the numeric ID from a DDB character URL.
 * @param {string} url
 * @returns {string|null}
 */
export function extractDDBId(url) {
  const m = url.match(/\/(\d+)(?:[/?#]|$)/);
  return m ? m[1] : null;
}

/**
 * Normalize a D&D character/NPC name to a WYRD persona_id.
 * @param {string} name
 * @returns {string}
 */
export function normalizePersonaId(name) {
  return (name || "")
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/_+/g, "_")
    .slice(0, 64);
}

// ---------------------------------------------------------------------------
// Settings helpers (pure, uses chrome.storage shape)
// ---------------------------------------------------------------------------

const STORAGE_KEY = "wyrdforge_config";

/**
 * Extract WyrdForge config from chrome.storage data object.
 * @param {object} storageData
 * @returns {{ host: string, port: number, enabled: boolean }}
 */
export function getConfigFromStorage(storageData) {
  const cfg = storageData?.[STORAGE_KEY];
  return {
    host: (cfg?.host) ? String(cfg.host) : "localhost",
    port: (cfg?.port) ? Number(cfg.port) : 8765,
    enabled: (cfg?.enabled !== undefined) ? Boolean(cfg.enabled) : true,
  };
}

/**
 * Build a chrome.storage.sync.set payload for saving config.
 * @param {string} host
 * @param {number} port
 * @param {boolean} enabled
 * @returns {object}
 */
export function buildStoragePayload(host, port, enabled) {
  return { [STORAGE_KEY]: { host, port, enabled } };
}

// ---------------------------------------------------------------------------
// Context panel HTML renderer (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Render the DDB sidebar panel HTML.
 * @param {{ personaId: string, loading: boolean, output: string, error: string|null }} state
 * @returns {string}
 */
export function renderSidebarPanel(state) {
  const spinner = state.loading ? '<span class="wyrd-spinner">⟳</span>' : "";
  const errorHtml = state.error
    ? `<p class="wyrd-error">${state.error}</p>`
    : "";
  const outputHtml = state.output
    ? `<pre class="wyrd-output">${state.output.replace(/</g, "&lt;")}</pre>`
    : "";
  return `<div class="wyrd-ddb-panel">
  <h4 class="wyrd-title">&#x16B9; WYRD${spinner}</h4>
  <p class="wyrd-persona-label">${state.personaId || "—"}</p>
  <button class="wyrd-refresh">Refresh Context</button>
  ${errorHtml}${outputHtml}
</div>`;
}

// ---------------------------------------------------------------------------
// Message protocol (for content↔background communication via chrome.runtime)
// ---------------------------------------------------------------------------

/**
 * Build a WYRD query message for chrome.runtime.sendMessage.
 * @param {string} personaId
 * @param {string} query
 * @returns {object}
 */
export function buildQueryMessage(personaId, query = "") {
  return { type: "WYRD_QUERY", personaId, query };
}

/**
 * Build a sync message for chrome.runtime.sendMessage.
 * @param {string} personaId
 * @param {string} name
 * @returns {object}
 */
export function buildSyncMessage(personaId, name) {
  return { type: "WYRD_SYNC", personaId, name };
}

/**
 * Build a health check message.
 * @returns {object}
 */
export function buildHealthMessage() {
  return { type: "WYRD_HEALTH" };
}

/**
 * Validate an incoming runtime message.
 * @param {object} msg
 * @returns {boolean}
 */
export function isValidMessage(msg) {
  return (
    msg != null &&
    typeof msg === "object" &&
    typeof msg.type === "string" &&
    ["WYRD_QUERY", "WYRD_SYNC", "WYRD_HEALTH"].includes(msg.type)
  );
}
