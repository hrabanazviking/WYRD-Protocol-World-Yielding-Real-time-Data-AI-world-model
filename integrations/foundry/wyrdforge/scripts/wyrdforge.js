/**
 * WyrdForge — WYRD Protocol integration for Foundry VTT (Phase 10A).
 *
 * Connects a running WyrdHTTPServer to Foundry VTT. Features:
 *   - /wyrd <persona_id> [message]  — chat command to query world context
 *   - Actor sheet sidebar panel with live WYRD context block
 *   - Automatic actor-name → persona_id sync on token placement
 *   - Module settings: host, port, enabled toggle, auto-sync toggle
 *
 * Compatible with Foundry V11 and V12.
 */

const MODULE_ID = "wyrdforge";
const CHAT_COMMAND = "/wyrd";
const SECTION_ATTR = "data-wyrd-context";

// ---------------------------------------------------------------------------
// Inline WyrdClient (mirrors wyrdforge-js SDK — no build step needed)
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
  /**
   * @param {object} opts
   * @param {string} [opts.host="localhost"]
   * @param {number} [opts.port=8765]
   * @param {number} [opts.timeoutMs=8000]
   */
  constructor({ host = "localhost", port = 8765, timeoutMs = 8000 } = {}) {
    this.baseUrl = `http://${host}:${port}`;
    this.timeoutMs = timeoutMs;
  }

  async health() {
    return this._get("/health");
  }

  async getWorld() {
    return this._get("/world");
  }

  async getFacts(entityId) {
    return this._get(`/facts?entity_id=${encodeURIComponent(entityId)}`);
  }

  /**
   * @param {string} personaId
   * @param {string} [userInput=""]
   * @param {object} [opts]
   * @param {string|null} [opts.locationId]
   * @param {boolean} [opts.useTurnLoop=false]
   */
  async query(personaId, userInput = "", { locationId = null, useTurnLoop = false } = {}) {
    const body = { persona_id: personaId, user_input: userInput, use_turn_loop: useTurnLoop };
    if (locationId) body.location_id = locationId;
    return this._post("/query", body);
  }

  /**
   * @param {"observation"|"fact"} eventType
   * @param {object} payload
   */
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
    try {
      data = await resp.json();
    } catch {
      data = null;
    }
    if (!resp.ok) {
      const msg = (data && data.error) ? data.error : `HTTP ${resp.status}`;
      throw new WyrdAPIError(msg, resp.status, data);
    }
    return data;
  }
}

// ---------------------------------------------------------------------------
// Settings helpers (pure, exportable for tests)
// ---------------------------------------------------------------------------

export function registerSettings(settingsAPI) {
  settingsAPI.register(MODULE_ID, "host", {
    name: "WYRD Server Host",
    hint: "Hostname of the running WyrdHTTPServer.",
    scope: "world",
    config: true,
    type: String,
    default: "localhost",
  });

  settingsAPI.register(MODULE_ID, "port", {
    name: "WYRD Server Port",
    hint: "Port of the running WyrdHTTPServer (default: 8765).",
    scope: "world",
    config: true,
    type: Number,
    default: 8765,
  });

  settingsAPI.register(MODULE_ID, "enabled", {
    name: "Enable WYRD Integration",
    hint: "Toggle world context injection on/off.",
    scope: "world",
    config: true,
    type: Boolean,
    default: true,
  });

  settingsAPI.register(MODULE_ID, "autoSync", {
    name: "Auto-sync Token Placement",
    hint: "When a token is placed, register that actor as a WYRD entity.",
    scope: "world",
    config: true,
    type: Boolean,
    default: true,
  });
}

export function getClient(settingsAPI) {
  const host = settingsAPI.get(MODULE_ID, "host");
  const port = settingsAPI.get(MODULE_ID, "port");
  return new WyrdClient({ host, port });
}

// ---------------------------------------------------------------------------
// Chat command parser (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Parse a raw chat message string.
 * @param {string} message
 * @returns {{ isWyrd: boolean, personaId: string, query: string }}
 */
export function parseChatCommand(message) {
  const trimmed = message.trim();
  if (!trimmed.startsWith(CHAT_COMMAND)) {
    return { isWyrd: false, personaId: "", query: "" };
  }
  const rest = trimmed.slice(CHAT_COMMAND.length).trim();
  const spaceIdx = rest.indexOf(" ");
  if (spaceIdx === -1) {
    return { isWyrd: true, personaId: rest, query: "" };
  }
  return {
    isWyrd: true,
    personaId: rest.slice(0, spaceIdx),
    query: rest.slice(spaceIdx + 1).trim(),
  };
}

// ---------------------------------------------------------------------------
// Context block formatter (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Format a WYRD query response into a Foundry chat card HTML string.
 * @param {string} personaId
 * @param {object} responseData  — JSON from /query endpoint
 * @returns {string}
 */
export function formatContextCard(personaId, responseData) {
  const response = (responseData && responseData.response) ? responseData.response : "";
  return `<div class="wyrd-context-card" ${SECTION_ATTR}="true">
  <h3 class="wyrd-persona">&#x16B9; ${personaId}</h3>
  <div class="wyrd-context-body">${response.replace(/\n/g, "<br>")}</div>
</div>`;
}

/**
 * Normalize an actor name to a WYRD persona_id.
 * @param {string} actorName
 * @returns {string}
 */
export function normalizePersonaId(actorName) {
  return actorName.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

// ---------------------------------------------------------------------------
// Chat message handler (async, uses client)
// ---------------------------------------------------------------------------

/**
 * Handle a Foundry chat message. Returns true if the message was consumed.
 * @param {WyrdClient} client
 * @param {Function} createChatMessage  — ChatMessage.create
 * @param {object}   notifications      — ui.notifications
 * @param {string}   message
 * @returns {Promise<boolean>}
 */
export async function handleChatMessage(client, createChatMessage, notifications, message) {
  const parsed = parseChatCommand(message);
  if (!parsed.isWyrd || !parsed.personaId) return false;

  try {
    const result = await client.query(parsed.personaId, parsed.query, { useTurnLoop: false });
    const html = formatContextCard(parsed.personaId, result);
    await createChatMessage({ content: html, type: 0 });
  } catch (err) {
    notifications.error(`WyrdForge: ${err.message}`);
  }
  return true;
}

// ---------------------------------------------------------------------------
// Actor sheet injection (async, uses client)
// ---------------------------------------------------------------------------

/**
 * Inject WYRD context into an actor sheet's sidebar.
 * @param {WyrdClient} client
 * @param {HTMLElement} html
 * @param {object}      actorData  — { name: string }
 */
export async function injectActorSheetContext(client, html, actorData) {
  const personaId = normalizePersonaId(actorData.name || "unknown");
  const container = html.querySelector?.(".sheet-sidebar") || html.find?.(".sheet-sidebar")?.[0];
  if (!container) return;

  const panel = document.createElement("div");
  panel.className = "wyrd-actor-panel";
  panel.innerHTML = '<p class="wyrd-loading">&#x16B9; Loading WYRD context…</p>';
  container.appendChild(panel);

  try {
    const result = await client.query(personaId, "", { useTurnLoop: false });
    const response = result?.response ?? "";
    panel.innerHTML = `<div class="wyrd-actor-context"><h4>&#x16B9; WYRD</h4><p>${response.replace(/\n/g, "<br>")}</p></div>`;
  } catch {
    panel.innerHTML = '<p class="wyrd-offline">WYRD server offline</p>';
  }
}

// ---------------------------------------------------------------------------
// Token placement sync (async, uses client)
// ---------------------------------------------------------------------------

/**
 * When a token is placed, register its actor as a WYRD entity.
 * @param {WyrdClient} client
 * @param {object}     tokenDoc  — { actor: { name: string } }
 */
export async function syncTokenActor(client, tokenDoc) {
  const actorName = tokenDoc?.actor?.name;
  if (!actorName) return;
  const personaId = normalizePersonaId(actorName);
  try {
    await client.pushEvent("fact", { subject_id: personaId, key: "name", value: actorName });
  } catch {
    // Graceful degradation — server may not be running
  }
}

// ---------------------------------------------------------------------------
// Module bootstrap (Foundry entry point)
// ---------------------------------------------------------------------------

Hooks.once("init", () => {
  registerSettings(game.settings);
});

Hooks.once("ready", async () => {
  if (!game.settings.get(MODULE_ID, "enabled")) return;

  const client = getClient(game.settings);
  try {
    await client.health();
    ui.notifications.info("WyrdForge: connected to WYRD world server.");
  } catch {
    ui.notifications.warn("WyrdForge: WYRD server not reachable — context injection disabled.");
  }
});

Hooks.on("chatMessage", (_chatLog, message, _data) => {
  if (!game.settings.get(MODULE_ID, "enabled")) return;
  const client = getClient(game.settings);
  handleChatMessage(client, ChatMessage.create.bind(ChatMessage), ui.notifications, message).then(
    (consumed) => {
      if (consumed) return false; // prevent default Foundry message handling
    }
  );
});

Hooks.on("renderActorSheet", (_app, html, data) => {
  if (!game.settings.get(MODULE_ID, "enabled")) return;
  const client = getClient(game.settings);
  injectActorSheetContext(client, html[0] ?? html, data.actor ?? data.document ?? {});
});

Hooks.on("createToken", (tokenDoc, _options, _userId) => {
  if (!game.settings.get(MODULE_ID, "enabled")) return;
  if (!game.settings.get(MODULE_ID, "autoSync")) return;
  const client = getClient(game.settings);
  syncTokenActor(client, tokenDoc);
});
