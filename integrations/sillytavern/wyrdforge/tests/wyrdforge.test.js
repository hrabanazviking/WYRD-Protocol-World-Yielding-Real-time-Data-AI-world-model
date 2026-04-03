/**
 * Tests for WyrdForge SillyTavern extension logic.
 *
 * Extracts and tests pure functions from index.js without ST globals.
 * All HTTP calls are mocked via globalThis.fetch.
 */

"use strict";

// ---------------------------------------------------------------------------
// Inline the testable logic (avoids ES module import complications with Jest)
// ---------------------------------------------------------------------------

const DEFAULT_SETTINGS = {
  enabled: true,
  serverUrl: "http://localhost:8765",
  personaId: "",
  useTurnLoop: false,
  maxChars: 2000,
  showDebug: false,
};

// Minimal settings store
let _settings = { ...DEFAULT_SETTINGS };
function getSettings() { return _settings; }
function resetSettings() { _settings = { ...DEFAULT_SETTINGS }; }

// Pure helper functions extracted from index.js

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

async function wyrdGetWorld() {
  const s = getSettings();
  const resp = await fetch(`${s.serverUrl}/world`, {
    signal: AbortSignal.timeout(5000),
  });
  if (!resp.ok) throw new Error(`WYRD /world error ${resp.status}`);
  const data = await resp.json();
  return data.formatted_for_llm ?? "";
}

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

// ---------------------------------------------------------------------------
// Mock fetch helper
// ---------------------------------------------------------------------------

function mockFetch(status, body) {
  return jest.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
  });
}

function mockFetchReject(err) {
  return jest.spyOn(globalThis, "fetch").mockRejectedValue(err);
}

afterEach(() => {
  jest.restoreAllMocks();
  resetSettings();
});

// ---------------------------------------------------------------------------
// DEFAULT_SETTINGS
// ---------------------------------------------------------------------------

describe("DEFAULT_SETTINGS", () => {
  test("enabled is true by default", () => {
    expect(DEFAULT_SETTINGS.enabled).toBe(true);
  });

  test("serverUrl defaults to localhost:8765", () => {
    expect(DEFAULT_SETTINGS.serverUrl).toBe("http://localhost:8765");
  });

  test("personaId defaults to empty string", () => {
    expect(DEFAULT_SETTINGS.personaId).toBe("");
  });

  test("useTurnLoop defaults to false", () => {
    expect(DEFAULT_SETTINGS.useTurnLoop).toBe(false);
  });

  test("maxChars defaults to 2000", () => {
    expect(DEFAULT_SETTINGS.maxChars).toBe(2000);
  });
});

// ---------------------------------------------------------------------------
// wyrdHealth()
// ---------------------------------------------------------------------------

describe("wyrdHealth()", () => {
  test("returns true when server responds ok", async () => {
    mockFetch(200, { status: "ok" });
    expect(await wyrdHealth()).toBe(true);
  });

  test("returns false when server unreachable", async () => {
    mockFetchReject(new TypeError("fetch failed"));
    expect(await wyrdHealth()).toBe(false);
  });

  test("returns false when status not ok", async () => {
    mockFetch(200, { status: "degraded" });
    expect(await wyrdHealth()).toBe(false);
  });

  test("returns false on non-200 HTTP status", async () => {
    mockFetch(500, { error: "server error" });
    expect(await wyrdHealth()).toBe(false);
  });

  test("uses serverUrl from settings", async () => {
    const spy = mockFetch(200, { status: "ok" });
    getSettings().serverUrl = "http://192.168.1.5:9000";
    await wyrdHealth();
    expect(spy.mock.calls[0][0]).toContain("192.168.1.5:9000");
  });
});

// ---------------------------------------------------------------------------
// wyrdGetWorld()
// ---------------------------------------------------------------------------

describe("wyrdGetWorld()", () => {
  test("returns formatted_for_llm string", async () => {
    mockFetch(200, { formatted_for_llm: "=== WORLD STATE ===" });
    const result = await wyrdGetWorld();
    expect(result).toBe("=== WORLD STATE ===");
  });

  test("returns empty string when field missing", async () => {
    mockFetch(200, {});
    const result = await wyrdGetWorld();
    expect(result).toBe("");
  });

  test("throws on non-200 status", async () => {
    mockFetch(500, { error: "server error" });
    await expect(wyrdGetWorld()).rejects.toThrow("WYRD /world error 500");
  });
});

// ---------------------------------------------------------------------------
// wyrdQuery()
// ---------------------------------------------------------------------------

describe("wyrdQuery()", () => {
  test("returns response string", async () => {
    mockFetch(200, { response: "The runes speak." });
    const result = await wyrdQuery("sigrid", "What do you see?");
    expect(result).toBe("The runes speak.");
  });

  test("sends persona_id and user_input", async () => {
    const spy = mockFetch(200, { response: "ok" });
    await wyrdQuery("sigrid", "Hello");
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.persona_id).toBe("sigrid");
    expect(body.user_input).toBe("Hello");
  });

  test("sends use_turn_loop false by default", async () => {
    const spy = mockFetch(200, { response: "ok" });
    await wyrdQuery("sigrid", "Hello");
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.use_turn_loop).toBe(false);
  });

  test("sends use_turn_loop true when specified", async () => {
    const spy = mockFetch(200, { response: "ok" });
    await wyrdQuery("sigrid", "Hello", { useTurnLoop: true });
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.use_turn_loop).toBe(true);
  });

  test("uses default input when userInput is empty", async () => {
    const spy = mockFetch(200, { response: "ok" });
    await wyrdQuery("sigrid", "");
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.user_input).toBe("What is the current situation?");
  });

  test("throws on 400 response", async () => {
    mockFetch(400, { error: "persona_id required" });
    await expect(wyrdQuery("", "Hi")).rejects.toThrow("WYRD /query error 400");
  });

  test("throws when fetch rejects", async () => {
    mockFetchReject(new TypeError("fetch failed"));
    await expect(wyrdQuery("sigrid", "Hi")).rejects.toThrow();
  });

  test("returns empty string when response field missing", async () => {
    mockFetch(200, {});
    const result = await wyrdQuery("sigrid", "Hi");
    expect(result).toBe("");
  });
});

// ---------------------------------------------------------------------------
// _lastUserMessage()
// ---------------------------------------------------------------------------

describe("_lastUserMessage()", () => {
  test("returns last user message", () => {
    const ctx = {
      chat: [
        { is_user: true, mes: "First message" },
        { is_user: false, mes: "Response" },
        { is_user: true, mes: "Second message" },
        { is_user: false, mes: "Another response" },
      ],
    };
    expect(_lastUserMessage(ctx)).toBe("Second message");
  });

  test("returns empty string when no user messages", () => {
    const ctx = {
      chat: [
        { is_user: false, mes: "System message" },
      ],
    };
    expect(_lastUserMessage(ctx)).toBe("");
  });

  test("returns empty string when chat is empty", () => {
    expect(_lastUserMessage({ chat: [] })).toBe("");
  });

  test("returns empty string when ctx is null", () => {
    expect(_lastUserMessage(null)).toBe("");
  });

  test("returns empty string when ctx is undefined", () => {
    expect(_lastUserMessage(undefined)).toBe("");
  });

  test("handles missing mes field", () => {
    const ctx = { chat: [{ is_user: true }] };
    expect(_lastUserMessage(ctx)).toBe("");
  });
});

// ---------------------------------------------------------------------------
// Settings mutation
// ---------------------------------------------------------------------------

describe("settings", () => {
  test("getSettings returns current settings", () => {
    const s = getSettings();
    expect(s).toHaveProperty("enabled");
    expect(s).toHaveProperty("serverUrl");
  });

  test("mutating settings persists within test", () => {
    getSettings().personaId = "sigrid";
    expect(getSettings().personaId).toBe("sigrid");
  });

  test("resetSettings restores defaults", () => {
    getSettings().personaId = "sigrid";
    resetSettings();
    expect(getSettings().personaId).toBe("");
  });
});
