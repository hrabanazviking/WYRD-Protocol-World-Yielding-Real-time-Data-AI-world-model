/**
 * WyrdForge World Context — SillyTavern Extension
 *
 * Injects WYRD Protocol world context into SillyTavern prompts before
 * each generation.  Uses setExtensionPrompt() to insert the WYRD context
 * block after world info, before the main prompt.
 *
 * Settings (stored in extension_settings.wyrdforge):
 *   - enabled        {boolean}  Master on/off switch
 *   - serverUrl      {string}   WyrdHTTPServer base URL (default: http://localhost:8765)
 *   - personaId      {string}   Active WYRD persona/character ID
 *   - useTurnLoop    {boolean}  Use WYRD TurnLoop (writes to memory) vs context-only
 *   - maxChars       {number}   Truncate injected block at N chars (0 = unlimited)
 *   - injectPosition {number}   ST injection position (0 = after world info)
 *   - showDebug      {boolean}  Log WYRD calls to browser console
 */

import { eventSource, event_types, setExtensionPrompt, extension_prompt_positions }
  from "../../../../script.js";
import { extension_settings, getContext, saveSettingsDebounced }
  from "../../../extensions.js";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXT_NAME = "wyrdforge";
const DEFAULT_SETTINGS = {
  enabled: true,
  serverUrl: "http://localhost:8765",
  personaId: "",
  useTurnLoop: false,
  maxChars: 2000,
  injectPosition: extension_prompt_positions.AFTER_WORLD_INFO_AND_BEFORE_PROMPT ?? 1,
  showDebug: false,
};

// ---------------------------------------------------------------------------
// Settings helpers
// ---------------------------------------------------------------------------

function getSettings() {
  if (!extension_settings[EXT_NAME]) {
    extension_settings[EXT_NAME] = { ...DEFAULT_SETTINGS };
  }
  return extension_settings[EXT_NAME];
}

function saveSettings() {
  saveSettingsDebounced();
}

// ---------------------------------------------------------------------------
// WYRD HTTP helpers
// ---------------------------------------------------------------------------

/**
 * Query the WYRD server's /query endpoint.
 * @param {string} personaId
 * @param {string} userInput
 * @param {object} opts
 * @returns {Promise<string>} Character response or formatted context block
 */
async function wyrdQuery(personaId, userInput, opts = {}) {
  const s = getSettings();
  const url = `${s.serverUrl}/query`;
  const body = {
    persona_id: personaId,
    user_input: userInput || "What is the current situation?",
    use_turn_loop: Boolean(opts.useTurnLoop ?? s.useTurnLoop),
  };
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(8000),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(`WYRD /query error ${resp.status}: ${err.error ?? resp.statusText}`);
  }
  const data = await resp.json();
  return data.response ?? "";
}

/**
 * Fetch world state from /world endpoint.
 * @returns {Promise<string>} formatted_for_llm text
 */
async function wyrdGetWorld() {
  const s = getSettings();
  const resp = await fetch(`${s.serverUrl}/world`, {
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) throw new Error(`WYRD /world error ${resp.status}`);
  const data = await resp.json();
  return data.formatted_for_llm ?? "";
}

/**
 * Check server health.
 * @returns {Promise<boolean>}
 */
async function wyrdHealth() {
  try {
    const s = getSettings();
    const resp = await fetch(`${s.serverUrl}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Context injection
// ---------------------------------------------------------------------------

/**
 * Build the WYRD context block and inject it via setExtensionPrompt.
 * Called before each generation.
 */
async function injectWyrdContext() {
  const s = getSettings();
  if (!s.enabled) return;

  const personaId = s.personaId.trim();
  if (!personaId) {
    _debug("WyrdForge: no personaId set, skipping injection");
    return;
  }

  let contextBlock = "";
  try {
    const ctx = getContext();
    const lastUserMessage = _lastUserMessage(ctx);

    contextBlock = await wyrdQuery(personaId, lastUserMessage, {
      useTurnLoop: s.useTurnLoop,
    });
  } catch (err) {
    _debug(`WyrdForge: query failed, falling back to /world — ${err.message}`);
    try {
      contextBlock = await wyrdGetWorld();
    } catch (fallbackErr) {
      _debug(`WyrdForge: /world fallback also failed — ${fallbackErr.message}`);
      return;
    }
  }

  if (!contextBlock) return;

  if (s.maxChars > 0 && contextBlock.length > s.maxChars) {
    contextBlock = contextBlock.slice(0, s.maxChars) + "\n... [wyrd truncated]";
  }

  const wrapped = `[WYRD WORLD CONTEXT]\n${contextBlock}\n[/WYRD WORLD CONTEXT]`;
  setExtensionPrompt(EXT_NAME, wrapped, s.injectPosition, 0);
  _debug(`WyrdForge: injected ${wrapped.length} chars for persona "${personaId}"`);
}

function _lastUserMessage(ctx) {
  if (!ctx?.chat?.length) return "";
  for (let i = ctx.chat.length - 1; i >= 0; i--) {
    if (ctx.chat[i].is_user) return ctx.chat[i].mes ?? "";
  }
  return "";
}

function _debug(msg) {
  if (getSettings().showDebug) console.log(`[WyrdForge] ${msg}`);
}

// ---------------------------------------------------------------------------
// Settings UI
// ---------------------------------------------------------------------------

const SETTINGS_HTML = `
<div id="wyrdforge_settings">
  <div class="wyrdforge-row">
    <label class="wyrdforge-label">
      <input id="wyrdforge_enabled" type="checkbox" />
      Enable WyrdForge context injection
    </label>
  </div>
  <div class="wyrdforge-row">
    <label class="wyrdforge-label" for="wyrdforge_server_url">Server URL</label>
    <input id="wyrdforge_server_url" class="text_pole" type="text"
      placeholder="http://localhost:8765" />
  </div>
  <div class="wyrdforge-row">
    <label class="wyrdforge-label" for="wyrdforge_persona_id">Persona ID</label>
    <input id="wyrdforge_persona_id" class="text_pole" type="text"
      placeholder="sigrid" />
  </div>
  <div class="wyrdforge-row">
    <label class="wyrdforge-label" for="wyrdforge_max_chars">Max chars (0 = unlimited)</label>
    <input id="wyrdforge_max_chars" class="text_pole" type="number" min="0" />
  </div>
  <div class="wyrdforge-row">
    <label class="wyrdforge-label">
      <input id="wyrdforge_use_turn_loop" type="checkbox" />
      Use TurnLoop (writes to WYRD memory)
    </label>
  </div>
  <div class="wyrdforge-row">
    <label class="wyrdforge-label">
      <input id="wyrdforge_show_debug" type="checkbox" />
      Show debug logs in console
    </label>
  </div>
  <div class="wyrdforge-row">
    <button id="wyrdforge_test_btn" class="menu_button">Test Connection</button>
    <span id="wyrdforge_status" class="wyrdforge-status"></span>
  </div>
</div>
`;

function buildSettingsUI() {
  $("#extensions_settings").append(SETTINGS_HTML);
  _syncUIFromSettings();
  _bindUIEvents();
}

function _syncUIFromSettings() {
  const s = getSettings();
  $("#wyrdforge_enabled").prop("checked", s.enabled);
  $("#wyrdforge_server_url").val(s.serverUrl);
  $("#wyrdforge_persona_id").val(s.personaId);
  $("#wyrdforge_max_chars").val(s.maxChars);
  $("#wyrdforge_use_turn_loop").prop("checked", s.useTurnLoop);
  $("#wyrdforge_show_debug").prop("checked", s.showDebug);
}

function _bindUIEvents() {
  $("#wyrdforge_enabled").on("change", function () {
    getSettings().enabled = this.checked;
    if (!this.checked) setExtensionPrompt(EXT_NAME, "", 0, 0);
    saveSettings();
  });
  $("#wyrdforge_server_url").on("input", function () {
    getSettings().serverUrl = this.value.trim();
    saveSettings();
  });
  $("#wyrdforge_persona_id").on("input", function () {
    getSettings().personaId = this.value.trim();
    saveSettings();
  });
  $("#wyrdforge_max_chars").on("input", function () {
    getSettings().maxChars = parseInt(this.value, 10) || 0;
    saveSettings();
  });
  $("#wyrdforge_use_turn_loop").on("change", function () {
    getSettings().useTurnLoop = this.checked;
    saveSettings();
  });
  $("#wyrdforge_show_debug").on("change", function () {
    getSettings().showDebug = this.checked;
    saveSettings();
  });
  $("#wyrdforge_test_btn").on("click", async function () {
    const $status = $("#wyrdforge_status");
    $status.text("Testing…").css("color", "#aaa");
    const ok = await wyrdHealth();
    if (ok) {
      $status.text("✓ Connected").css("color", "#6f6");
    } else {
      $status.text("✗ Unreachable").css("color", "#f66");
    }
  });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

jQuery(async () => {
  buildSettingsUI();
  eventSource.on(event_types.GENERATE_BEFORE_COMBINE_PROMPTS, injectWyrdContext);
  console.log("[WyrdForge] Extension loaded — WYRD world context injection active.");
});

// ---------------------------------------------------------------------------
// Exports (for testing)
// ---------------------------------------------------------------------------

export {
  wyrdQuery,
  wyrdGetWorld,
  wyrdHealth,
  injectWyrdContext,
  getSettings,
  DEFAULT_SETTINGS,
  _lastUserMessage,
  _debug,
};
