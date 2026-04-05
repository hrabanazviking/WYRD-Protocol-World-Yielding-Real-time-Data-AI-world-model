/**
 * Tests for WyrdForge D&D Beyond browser extension (Phase 10E).
 * Pure functions inlined to avoid ES module complications with Jest.
 */
"use strict";

// ---------------------------------------------------------------------------
// Inline pure functions under test (mirrors wyrdforge.js)
// ---------------------------------------------------------------------------

class WyrdConnectionError extends Error {
  constructor(m, c) { super(m); this.name = "WyrdConnectionError"; this.cause = c; }
}
class WyrdAPIError extends Error {
  constructor(m, s, b) { super(m); this.name = "WyrdAPIError"; this.status = s; this.body = b; }
}

class WyrdClient {
  constructor({ host = "localhost", port = 8765, timeoutMs = 8000 } = {}) {
    this.baseUrl = `http://${host}:${port}`;
    this.timeoutMs = timeoutMs;
  }
  async health() { return this._get("/health"); }
  async query(personaId, userInput = "", { useTurnLoop = false } = {}) {
    return this._post("/query", { persona_id: personaId, user_input: userInput, use_turn_loop: useTurnLoop });
  }
  async pushEvent(eventType, payload) {
    return this._post("/event", { event_type: eventType, payload });
  }
  async _get(path) {
    let resp;
    try { resp = await globalThis.fetch(`${this.baseUrl}${path}`, { signal: AbortSignal.timeout(this.timeoutMs) }); }
    catch (err) { throw new WyrdConnectionError(`Cannot reach ${this.baseUrl}`, err); }
    return this._parseResponse(resp);
  }
  async _post(path, body) {
    let resp;
    try {
      resp = await globalThis.fetch(`${this.baseUrl}${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) { throw new WyrdConnectionError(`Cannot reach ${this.baseUrl}`, err); }
    return this._parseResponse(resp);
  }
  async _parseResponse(resp) {
    let data; try { data = await resp.json(); } catch { data = null; }
    if (!resp.ok) { throw new WyrdAPIError((data?.error) ? data.error : `HTTP ${resp.status}`, resp.status, data); }
    return data;
  }
}

function classifyDDBUrl(url) {
  if (/dndbeyond\.com\/characters\/\d+/.test(url)) return "character";
  if (/dndbeyond\.com\/monsters\//.test(url)) return "monster";
  if (/dndbeyond\.com\/npcs\//.test(url)) return "npc";
  return "unknown";
}

function extractDDBId(url) {
  const m = url.match(/\/(\d+)(?:[/?#]|$)/);
  return m ? m[1] : null;
}

function normalizePersonaId(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

const STORAGE_KEY = "wyrdforge_config";

function getConfigFromStorage(storageData) {
  const cfg = storageData?.[STORAGE_KEY];
  return {
    host: (cfg?.host) ? String(cfg.host) : "localhost",
    port: (cfg?.port) ? Number(cfg.port) : 8765,
    enabled: (cfg?.enabled !== undefined) ? Boolean(cfg.enabled) : true,
  };
}

function buildStoragePayload(host, port, enabled) {
  return { [STORAGE_KEY]: { host, port, enabled } };
}

function renderSidebarPanel(state) {
  const spinner = state.loading ? '<span class="wyrd-spinner">⟳</span>' : "";
  const errorHtml = state.error ? `<p class="wyrd-error">${state.error}</p>` : "";
  const outputHtml = state.output ? `<pre class="wyrd-output">${state.output.replace(/</g, "&lt;")}</pre>` : "";
  return `<div class="wyrd-ddb-panel">
  <h4 class="wyrd-title">&#x16B9; WYRD${spinner}</h4>
  <p class="wyrd-persona-label">${state.personaId || "—"}</p>
  <button class="wyrd-refresh">Refresh Context</button>
  ${errorHtml}${outputHtml}
</div>`;
}

function buildQueryMessage(personaId, query = "") {
  return { type: "WYRD_QUERY", personaId, query };
}

function buildSyncMessage(personaId, name) {
  return { type: "WYRD_SYNC", personaId, name };
}

function buildHealthMessage() {
  return { type: "WYRD_HEALTH" };
}

function isValidMessage(msg) {
  return (
    msg != null &&
    typeof msg === "object" &&
    typeof msg.type === "string" &&
    ["WYRD_QUERY", "WYRD_SYNC", "WYRD_HEALTH"].includes(msg.type)
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

if (!AbortSignal.timeout) AbortSignal.timeout = () => new AbortController().signal;

function mockFetch(status, body) {
  const spy = jest.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  globalThis.fetch = spy;
  return spy;
}
function mockFetchReject(err) {
  globalThis.fetch = jest.fn().mockRejectedValue(err);
}

// ---------------------------------------------------------------------------
// WyrdClient
// ---------------------------------------------------------------------------

describe("WyrdClient", () => {
  test("constructs with defaults", () => expect(new WyrdClient().baseUrl).toBe("http://localhost:8765"));
  test("health() calls /health", async () => {
    const spy = mockFetch(200, { status: "ok" });
    await new WyrdClient().health();
    expect(spy.mock.calls[0][0]).toContain("/health");
  });
  test("query() sends correct body", async () => {
    const spy = mockFetch(200, { response: "ctx" });
    await new WyrdClient().query("sigrid", "hi");
    expect(JSON.parse(spy.mock.calls[0][1].body).persona_id).toBe("sigrid");
  });
  test("throws WyrdConnectionError on failure", async () => {
    mockFetchReject(new Error("net"));
    await expect(new WyrdClient().health()).rejects.toThrow(WyrdConnectionError);
  });
  test("throws WyrdAPIError on non-2xx", async () => {
    mockFetch(404, { error: "not found" });
    await expect(new WyrdClient().health()).rejects.toThrow(WyrdAPIError);
  });
});

// ---------------------------------------------------------------------------
// classifyDDBUrl
// ---------------------------------------------------------------------------

describe("classifyDDBUrl", () => {
  test("classifies character URL", () => {
    expect(classifyDDBUrl("https://www.dndbeyond.com/characters/12345")).toBe("character");
  });
  test("classifies monster URL", () => {
    expect(classifyDDBUrl("https://www.dndbeyond.com/monsters/goblin")).toBe("monster");
  });
  test("classifies NPC URL", () => {
    expect(classifyDDBUrl("https://www.dndbeyond.com/npcs/commoner")).toBe("npc");
  });
  test("returns unknown for other URL", () => {
    expect(classifyDDBUrl("https://www.dndbeyond.com/spells/fireball")).toBe("unknown");
  });
  test("classifies character with query params", () => {
    expect(classifyDDBUrl("https://www.dndbeyond.com/characters/12345?tab=details")).toBe("character");
  });
});

// ---------------------------------------------------------------------------
// extractDDBId
// ---------------------------------------------------------------------------

describe("extractDDBId", () => {
  test("extracts numeric ID from URL", () => {
    expect(extractDDBId("https://www.dndbeyond.com/characters/98765")).toBe("98765");
  });
  test("returns null for URL without numeric ID", () => {
    expect(extractDDBId("https://www.dndbeyond.com/monsters/goblin")).toBeNull();
  });
  test("returns null for non-matching URL", () => {
    expect(extractDDBId("https://example.com")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// normalizePersonaId
// ---------------------------------------------------------------------------

describe("normalizePersonaId", () => {
  test("lowercases", () => expect(normalizePersonaId("Sigrid")).toBe("sigrid"));
  test("replaces spaces with underscore", () => expect(normalizePersonaId("Erik Red")).toBe("erik_red"));
  test("collapses underscores", () => expect(normalizePersonaId("a  b")).toBe("a_b"));
  test("truncates at 64", () => expect(normalizePersonaId("x".repeat(100)).length).toBe(64));
  test("handles null", () => expect(normalizePersonaId(null)).toBe(""));
});

// ---------------------------------------------------------------------------
// getConfigFromStorage
// ---------------------------------------------------------------------------

describe("getConfigFromStorage", () => {
  test("returns defaults when empty", () => {
    const cfg = getConfigFromStorage({});
    expect(cfg.host).toBe("localhost");
    expect(cfg.port).toBe(8765);
    expect(cfg.enabled).toBe(true);
  });
  test("returns stored values", () => {
    const cfg = getConfigFromStorage({ wyrdforge_config: { host: "myhost", port: 9000, enabled: false } });
    expect(cfg.host).toBe("myhost");
    expect(cfg.port).toBe(9000);
    expect(cfg.enabled).toBe(false);
  });
  test("handles null storageData", () => {
    const cfg = getConfigFromStorage(null);
    expect(cfg.host).toBe("localhost");
  });
});

// ---------------------------------------------------------------------------
// buildStoragePayload
// ---------------------------------------------------------------------------

describe("buildStoragePayload", () => {
  test("includes all fields", () => {
    const p = buildStoragePayload("h", 1234, false);
    expect(p.wyrdforge_config.host).toBe("h");
    expect(p.wyrdforge_config.port).toBe(1234);
    expect(p.wyrdforge_config.enabled).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// renderSidebarPanel
// ---------------------------------------------------------------------------

describe("renderSidebarPanel", () => {
  test("shows persona label", () => {
    const html = renderSidebarPanel({ personaId: "sigrid", loading: false, output: "", error: null });
    expect(html).toContain("sigrid");
  });
  test("shows dash when no personaId", () => {
    const html = renderSidebarPanel({ personaId: "", loading: false, output: "", error: null });
    expect(html).toContain("—");
  });
  test("shows spinner when loading", () => {
    const html = renderSidebarPanel({ personaId: "x", loading: true, output: "", error: null });
    expect(html).toContain("wyrd-spinner");
  });
  test("shows error", () => {
    const html = renderSidebarPanel({ personaId: "x", loading: false, output: "", error: "oops" });
    expect(html).toContain("wyrd-error");
    expect(html).toContain("oops");
  });
  test("shows output", () => {
    const html = renderSidebarPanel({ personaId: "x", loading: false, output: "context", error: null });
    expect(html).toContain("wyrd-output");
    expect(html).toContain("context");
  });
  test("escapes < in output", () => {
    const html = renderSidebarPanel({ personaId: "x", loading: false, output: "<b>", error: null });
    expect(html).toContain("&lt;b>");
  });
});

// ---------------------------------------------------------------------------
// Message helpers
// ---------------------------------------------------------------------------

describe("buildQueryMessage", () => {
  test("has correct type", () => expect(buildQueryMessage("x").type).toBe("WYRD_QUERY"));
  test("has personaId", () => expect(buildQueryMessage("sigrid").personaId).toBe("sigrid"));
  test("includes query", () => expect(buildQueryMessage("x", "hello").query).toBe("hello"));
});

describe("buildSyncMessage", () => {
  test("has correct type", () => expect(buildSyncMessage("x", "Name").type).toBe("WYRD_SYNC"));
  test("has name field", () => expect(buildSyncMessage("x", "Sigrid").name).toBe("Sigrid"));
});

describe("buildHealthMessage", () => {
  test("has correct type", () => expect(buildHealthMessage().type).toBe("WYRD_HEALTH"));
});

describe("isValidMessage", () => {
  test("returns true for WYRD_QUERY", () => expect(isValidMessage({ type: "WYRD_QUERY" })).toBe(true));
  test("returns true for WYRD_SYNC", () => expect(isValidMessage({ type: "WYRD_SYNC" })).toBe(true));
  test("returns true for WYRD_HEALTH", () => expect(isValidMessage({ type: "WYRD_HEALTH" })).toBe(true));
  test("returns false for unknown type", () => expect(isValidMessage({ type: "OTHER" })).toBe(false));
  test("returns false for null", () => expect(isValidMessage(null)).toBe(false));
  test("returns false for non-object", () => expect(isValidMessage("string")).toBe(false));
});
