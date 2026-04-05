/**
 * WyrdForge — WYRD Protocol integration for Roll20 API (Phase 10B).
 *
 * Roll20 API script. Requires Roll20 Pro (API access).
 * Communicates with WyrdHTTPServer via Roll20's `sendChat` + external fetch
 * (Roll20 API scripts run in Node.js and have access to require/https).
 *
 * Features:
 *   !wyrd <persona_id> [query]   — chat command to query world context
 *   !wyrd-sync <actor_name>      — register a character as a WYRD entity
 *   !wyrd-health                 — check server connectivity
 *
 * Setup:
 *   1. In Roll20 API console, set the following state defaults (or edit below):
 *      state.wyrdforge = { host: "your-server", port: 8765, enabled: true }
 *   2. Add this script to your Roll20 campaign API scripts.
 *   3. Run !wyrd-health to verify connectivity.
 */

/* global on, sendChat, state, log, getAttrByName */

const WF_MODULE = "WyrdForge";
const WF_CMD = "!wyrd";
const WF_SYNC_CMD = "!wyrd-sync";
const WF_HEALTH_CMD = "!wyrd-health";

// ---------------------------------------------------------------------------
// Config helpers (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * @param {object} stateObj  — Roll20 state object
 * @returns {{ host: string, port: number, enabled: boolean }}
 */
export function getConfig(stateObj) {
  if (!stateObj.wyrdforge) {
    stateObj.wyrdforge = { host: "localhost", port: 8765, enabled: true };
  }
  return stateObj.wyrdforge;
}

// ---------------------------------------------------------------------------
// Chat command parser (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Parse a Roll20 chat message content string.
 * @param {string} message
 * @returns {{ cmd: string|null, personaId: string, query: string }}
 */
export function parseCommand(message) {
  const trimmed = (message || "").trim();

  if (trimmed === WF_HEALTH_CMD) {
    return { cmd: "health", personaId: "", query: "" };
  }

  if (trimmed.startsWith(WF_SYNC_CMD)) {
    const rest = trimmed.slice(WF_SYNC_CMD.length).trim();
    return { cmd: "sync", personaId: rest, query: "" };
  }

  if (trimmed.startsWith(WF_CMD)) {
    const rest = trimmed.slice(WF_CMD.length).trim();
    const spaceIdx = rest.indexOf(" ");
    if (spaceIdx === -1) {
      return { cmd: "query", personaId: rest, query: "" };
    }
    return {
      cmd: "query",
      personaId: rest.slice(0, spaceIdx),
      query: rest.slice(spaceIdx + 1).trim(),
    };
  }

  return { cmd: null, personaId: "", query: "" };
}

// ---------------------------------------------------------------------------
// Persona ID normalizer (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * @param {string} name
 * @returns {string}
 */
export function normalizePersonaId(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

// ---------------------------------------------------------------------------
// Chat message formatter (pure, exportable for tests)
// ---------------------------------------------------------------------------

/**
 * Format a WYRD response as a Roll20 chat output string.
 * @param {string} personaId
 * @param {string} responseText
 * @returns {string}
 */
export function formatChatOutput(personaId, responseText) {
  const divider = "—".repeat(40);
  return `/w gm &{template:default} {{name=ᚹ WyrdForge — ${personaId}}} {{${divider}=${responseText}}}`;
}

/**
 * Format a simple status/info message for GM whisper.
 * @param {string} message
 * @returns {string}
 */
export function formatStatus(message) {
  return `/w gm [WyrdForge] ${message}`;
}

// ---------------------------------------------------------------------------
// HTTP client helpers (pure logic, testable with mock http)
// ---------------------------------------------------------------------------

/**
 * Build the options for a GET request to WyrdHTTPServer.
 * @param {string} host
 * @param {number} port
 * @param {string} path
 * @returns {{ hostname: string, port: number, path: string, method: string }}
 */
export function buildGetOptions(host, port, path) {
  return { hostname: host, port, path, method: "GET" };
}

/**
 * Build the options and body for a POST request to WyrdHTTPServer.
 * @param {string} host
 * @param {number} port
 * @param {string} path
 * @param {object} payload
 * @returns {{ options: object, body: string }}
 */
export function buildPostOptions(host, port, path, payload) {
  const body = JSON.stringify(payload);
  return {
    options: {
      hostname: host,
      port,
      path,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
    },
    body,
  };
}

// ---------------------------------------------------------------------------
// HTTP request wrapper (uses Node.js http module — Roll20 API environment)
// ---------------------------------------------------------------------------

/**
 * Make an HTTP request. Returns a Promise.
 * @param {object} http   — Node.js `http` module (or mock)
 * @param {object} opts   — http.request options
 * @param {string} [body] — POST body
 * @returns {Promise<object>}
 */
export function httpRequest(http, opts, body = null) {
  return new Promise((resolve, reject) => {
    const req = http.request(opts, (res) => {
      let raw = "";
      res.on("data", (chunk) => { raw += chunk; });
      res.on("end", () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(raw) });
        } catch (err) {
          reject(new Error(`JSON parse error: ${err.message}`));
        }
      });
    });
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// High-level operations (use http + config)
// ---------------------------------------------------------------------------

/**
 * Query WYRD world context for a persona.
 * @param {object} http
 * @param {{ host: string, port: number }} config
 * @param {string} personaId
 * @param {string} [query=""]
 * @returns {Promise<string>}  — response text
 */
export async function queryWyrd(http, config, personaId, query = "") {
  const payload = {
    persona_id: personaId,
    user_input: query || "What is the current state of the world?",
    use_turn_loop: false,
  };
  const { options, body } = buildPostOptions(config.host, config.port, "/query", payload);
  const result = await httpRequest(http, options, body);
  return result.data?.response ?? "";
}

/**
 * Push a fact to WYRD memory.
 * @param {object} http
 * @param {{ host: string, port: number }} config
 * @param {string} personaId
 * @param {string} name
 * @returns {Promise<boolean>}
 */
export async function syncActor(http, config, personaId, name) {
  const payload = {
    event_type: "fact",
    payload: { subject_id: personaId, key: "name", value: name },
  };
  const { options, body } = buildPostOptions(config.host, config.port, "/event", payload);
  const result = await httpRequest(http, options, body);
  return result.data?.ok === true;
}

/**
 * Health-check the WyrdHTTPServer.
 * @param {object} http
 * @param {{ host: string, port: number }} config
 * @returns {Promise<boolean>}
 */
export async function checkHealth(http, config) {
  const opts = buildGetOptions(config.host, config.port, "/health");
  const result = await httpRequest(http, opts);
  return result.data?.status === "ok";
}

// ---------------------------------------------------------------------------
// Roll20 entry point — only runs in Roll20 API environment
// ---------------------------------------------------------------------------

/* c8 ignore start */
if (typeof on !== "undefined") {
  const http = require("http"); // eslint-disable-line no-undef

  on("ready", () => {
    log(`${WF_MODULE}: loaded. Type !wyrd-health to check server connectivity.`);
  });

  on("chat:message", async (msg) => {
    if (msg.type !== "api") return;
    const cfg = getConfig(state);
    if (!cfg.enabled) return;

    const parsed = parseCommand(msg.content);
    if (!parsed.cmd) return;

    const speaker = msg.who || "API";

    try {
      if (parsed.cmd === "health") {
        const ok = await checkHealth(http, cfg);
        sendChat(WF_MODULE, formatStatus(ok ? "WYRD server is online." : "WYRD server unreachable."));

      } else if (parsed.cmd === "sync") {
        if (!parsed.personaId) {
          sendChat(WF_MODULE, formatStatus("Usage: !wyrd-sync <actor_name>"));
          return;
        }
        const pid = normalizePersonaId(parsed.personaId);
        const ok = await syncActor(http, cfg, pid, parsed.personaId);
        sendChat(WF_MODULE, formatStatus(ok ? `Synced '${pid}' to WYRD.` : `Sync failed for '${pid}'.`));

      } else if (parsed.cmd === "query") {
        if (!parsed.personaId) {
          sendChat(WF_MODULE, formatStatus("Usage: !wyrd <persona_id> [query]"));
          return;
        }
        const pid = normalizePersonaId(parsed.personaId);
        const response = await queryWyrd(http, cfg, pid, parsed.query);
        sendChat(WF_MODULE, formatChatOutput(pid, response));
      }
    } catch (err) {
      sendChat(WF_MODULE, formatStatus(`Error: ${err.message}`));
      log(`${WF_MODULE} error: ${err.message}`);
    }
  });
}
/* c8 ignore end */
