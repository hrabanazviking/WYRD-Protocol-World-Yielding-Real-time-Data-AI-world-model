/**
 * WyrdForge — WYRD Protocol integration for Owlbear Rodeo 2 (Phase 10D).
 *
 * Owlbear Rodeo 2 extension. Runs inside the OBR Action panel iframe.
 * Requires Owlbear Rodeo 2 with extension support (OBR SDK).
 *
 * Features:
 *   - Action panel UI: query world context for any persona
 *   - Sync selected token's character name → WYRD entity
 *   - Settings: host, port, persist in OBR.room.setMetadata
 *   - Displays response in the Action panel
 *
 * Owlbear Rodeo 2 OBR SDK APIs used:
 *   OBR.onReady(callback)
 *   OBR.player.getName()
 *   OBR.selection.getSelection()
 *   OBR.scene.items.getItems(ids)
 *   OBR.room.getMetadata() / OBR.room.setMetadata()
 *   OBR.notification.show(message, severity)
 */

// ---------------------------------------------------------------------------
// WyrdClient (inline, mirrors wyrdforge-js SDK)
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
  async getFacts(entityId) { return this._get(`/facts?entity_id=${encodeURIComponent(entityId)}`); }

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
// Config helpers (pure, exportable for tests)
// ---------------------------------------------------------------------------

const META_KEY = "wyrdforge.config";

/**
 * Extract WyrdForge config from OBR room metadata.
 * @param {object} metadata  — result of OBR.room.getMetadata()
 * @returns {{ host: string, port: number }}
 */
export function getConfigFromMeta(metadata) {
  const cfg = metadata?.[META_KEY];
  return {
    host: (cfg && cfg.host) ? String(cfg.host) : "localhost",
    port: (cfg && cfg.port) ? Number(cfg.port) : 8765,
  };
}

/**
 * Build a metadata patch for saving WyrdForge config to OBR room.
 * @param {string} host
 * @param {number} port
 * @returns {object}
 */
export function buildConfigMeta(host, port) {
  return { [META_KEY]: { host, port } };
}

// ---------------------------------------------------------------------------
// Persona ID helpers (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Normalize an OBR token/character name to a WYRD persona_id.
 * @param {string} name
 * @returns {string}
 */
export function normalizePersonaId(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

// ---------------------------------------------------------------------------
// Response formatter (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Format a WYRD query response for display in the OBR Action panel.
 * @param {string} personaId
 * @param {object|null} responseData
 * @returns {string}  — plain text for display
 */
export function formatResponse(personaId, responseData) {
  const text = responseData?.response ?? "";
  return `[${personaId}]\n${text}`;
}

// ---------------------------------------------------------------------------
// Token-to-persona extraction (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Extract persona_id from an OBR item (token) object.
 * Tries metadata.name, then item.name.
 * @param {object} item  — OBR scene item
 * @returns {string}
 */
export function personaIdFromItem(item) {
  const name = item?.metadata?.["wyrdforge.persona_id"]
    || item?.metadata?.name
    || item?.name
    || "";
  return normalizePersonaId(name);
}

// ---------------------------------------------------------------------------
// Action panel state machine (pure logic, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * @typedef {object} PanelState
 * @property {string} personaId
 * @property {string} query
 * @property {string} output
 * @property {boolean} loading
 * @property {string|null} error
 */

/**
 * @returns {PanelState}
 */
export function initialPanelState() {
  return { personaId: "", query: "", output: "", loading: false, error: null };
}

/**
 * Reduce a panel action into a new state.
 * @param {PanelState} state
 * @param {{ type: string, payload?: any }} action
 * @returns {PanelState}
 */
export function panelReducer(state, action) {
  switch (action.type) {
    case "SET_PERSONA": return { ...state, personaId: action.payload, error: null };
    case "SET_QUERY": return { ...state, query: action.payload };
    case "QUERY_START": return { ...state, loading: true, error: null, output: "" };
    case "QUERY_SUCCESS": return { ...state, loading: false, output: action.payload };
    case "QUERY_ERROR": return { ...state, loading: false, error: action.payload };
    case "CLEAR": return initialPanelState();
    default: return state;
  }
}

// ---------------------------------------------------------------------------
// Action panel HTML renderer (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Render the action panel HTML string from current state.
 * @param {PanelState} state
 * @returns {string}
 */
export function renderPanel(state) {
  const loadingAttr = state.loading ? " disabled" : "";
  const errorHtml = state.error
    ? `<p class="wyrd-error">${state.error}</p>`
    : "";
  const outputHtml = state.output
    ? `<pre class="wyrd-output">${state.output.replace(/</g, "&lt;")}</pre>`
    : "";
  return `<div class="wyrd-panel">
  <label>Persona ID<input id="wyrd-persona" type="text" value="${state.personaId}"${loadingAttr}></label>
  <label>Query<input id="wyrd-query" type="text" value="${state.query}"${loadingAttr} placeholder="optional"></label>
  <button id="wyrd-submit"${loadingAttr}>${state.loading ? "Loading…" : "Query WYRD"}</button>
  <button id="wyrd-sync"${loadingAttr}>Sync Selected Token</button>
  ${errorHtml}${outputHtml}
</div>`;
}

// ---------------------------------------------------------------------------
// OBR Action panel bootstrap — only runs in OBR environment
// ---------------------------------------------------------------------------

/* c8 ignore start */
if (typeof OBR !== "undefined") {
  OBR.onReady(async () => {
    const meta = await OBR.room.getMetadata();
    const cfg = getConfigFromMeta(meta);
    const client = new WyrdClient({ host: cfg.host, port: cfg.port });

    let state = initialPanelState();

    function render() {
      document.body.innerHTML = renderPanel(state);

      document.getElementById("wyrd-persona")?.addEventListener("input", (e) => {
        state = panelReducer(state, { type: "SET_PERSONA", payload: e.target.value });
      });

      document.getElementById("wyrd-query")?.addEventListener("input", (e) => {
        state = panelReducer(state, { type: "SET_QUERY", payload: e.target.value });
      });

      document.getElementById("wyrd-submit")?.addEventListener("click", async () => {
        if (!state.personaId) {
          state = panelReducer(state, { type: "QUERY_ERROR", payload: "Enter a persona ID." });
          render();
          return;
        }
        state = panelReducer(state, { type: "QUERY_START" });
        render();
        try {
          const result = await client.query(state.personaId, state.query, { useTurnLoop: false });
          const text = formatResponse(state.personaId, result);
          state = panelReducer(state, { type: "QUERY_SUCCESS", payload: text });
        } catch (err) {
          state = panelReducer(state, { type: "QUERY_ERROR", payload: err.message });
        }
        render();
      });

      document.getElementById("wyrd-sync")?.addEventListener("click", async () => {
        const selection = await OBR.selection.getSelection();
        if (!selection || selection.length === 0) {
          await OBR.notification.show("Select a token first.", "WARNING");
          return;
        }
        const items = await OBR.scene.items.getItems(selection);
        for (const item of items) {
          const personaId = personaIdFromItem(item);
          if (!personaId) continue;
          const name = item?.name || personaId;
          try {
            await client.pushEvent("fact", { subject_id: personaId, key: "name", value: name });
            await OBR.notification.show(`Synced '${personaId}' to WYRD.`, "SUCCESS");
          } catch (err) {
            await OBR.notification.show(`Sync failed: ${err.message}`, "ERROR");
          }
        }
      });
    }

    render();
  });
}
/* c8 ignore end */
