/**
 * Tests for WyrdForge Owlbear Rodeo 2 extension (Phase 10D).
 * Pure functions inlined to avoid ES module complications with Jest.
 */
"use strict";

// ---------------------------------------------------------------------------
// Inline pure functions under test (mirrors wyrdforge.js)
// ---------------------------------------------------------------------------

const META_KEY = "wyrdforge.config";

class WyrdConnectionError extends Error {
  constructor(message, cause) { super(message); this.name = "WyrdConnectionError"; this.cause = cause; }
}
class WyrdAPIError extends Error {
  constructor(message, status, body) { super(message); this.name = "WyrdAPIError"; this.status = status; this.body = body; }
}

class WyrdClient {
  constructor({ host = "localhost", port = 8765, timeoutMs = 8000 } = {}) {
    this.baseUrl = `http://${host}:${port}`;
    this.timeoutMs = timeoutMs;
  }
  async health() { return this._get("/health"); }
  async query(personaId, userInput = "", { locationId = null, useTurnLoop = false } = {}) {
    const body = { persona_id: personaId, user_input: userInput, use_turn_loop: useTurnLoop };
    if (locationId) body.location_id = locationId;
    return this._post("/query", body);
  }
  async pushEvent(eventType, payload) { return this._post("/event", { event_type: eventType, payload }); }
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
    if (!resp.ok) { const msg = (data && data.error) ? data.error : `HTTP ${resp.status}`; throw new WyrdAPIError(msg, resp.status, data); }
    return data;
  }
}

function getConfigFromMeta(metadata) {
  const cfg = metadata?.[META_KEY];
  return { host: (cfg && cfg.host) ? String(cfg.host) : "localhost", port: (cfg && cfg.port) ? Number(cfg.port) : 8765 };
}

function buildConfigMeta(host, port) {
  return { [META_KEY]: { host, port } };
}

function normalizePersonaId(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

function formatResponse(personaId, responseData) {
  const text = responseData?.response ?? "";
  return `[${personaId}]\n${text}`;
}

function personaIdFromItem(item) {
  const name = item?.metadata?.["wyrdforge.persona_id"] || item?.metadata?.name || item?.name || "";
  return normalizePersonaId(name);
}

function initialPanelState() {
  return { personaId: "", query: "", output: "", loading: false, error: null };
}

function panelReducer(state, action) {
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

function renderPanel(state) {
  const loadingAttr = state.loading ? " disabled" : "";
  const errorHtml = state.error ? `<p class="wyrd-error">${state.error}</p>` : "";
  const outputHtml = state.output ? `<pre class="wyrd-output">${state.output.replace(/</g, "&lt;")}</pre>` : "";
  return `<div class="wyrd-panel">
  <label>Persona ID<input id="wyrd-persona" type="text" value="${state.personaId}"${loadingAttr}></label>
  <label>Query<input id="wyrd-query" type="text" value="${state.query}"${loadingAttr} placeholder="optional"></label>
  <button id="wyrd-submit"${loadingAttr}>${state.loading ? "Loading…" : "Query WYRD"}</button>
  <button id="wyrd-sync"${loadingAttr}>Sync Selected Token</button>
  ${errorHtml}${outputHtml}
</div>`;
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
function mockFetchReject(error) {
  const spy = jest.fn().mockRejectedValue(error);
  globalThis.fetch = spy;
  return spy;
}

// ---------------------------------------------------------------------------
// WyrdClient
// ---------------------------------------------------------------------------

describe("WyrdClient", () => {
  test("constructs with defaults", () => {
    expect(new WyrdClient().baseUrl).toBe("http://localhost:8765");
  });
  test("health() fetches /health", async () => {
    const spy = mockFetch(200, { status: "ok" });
    await new WyrdClient().health();
    expect(spy.mock.calls[0][0]).toContain("/health");
  });
  test("query() sends persona_id", async () => {
    const spy = mockFetch(200, { response: "" });
    await new WyrdClient().query("sigrid", "hi");
    expect(JSON.parse(spy.mock.calls[0][1].body).persona_id).toBe("sigrid");
  });
  test("pushEvent() sends event_type", async () => {
    const spy = mockFetch(200, { ok: true });
    await new WyrdClient().pushEvent("observation", { title: "Storm", summary: "A storm." });
    expect(JSON.parse(spy.mock.calls[0][1].body).event_type).toBe("observation");
  });
  test("throws WyrdConnectionError on fetch failure", async () => {
    mockFetchReject(new Error("ECONNREFUSED"));
    await expect(new WyrdClient().health()).rejects.toThrow(WyrdConnectionError);
  });
  test("throws WyrdAPIError on 500", async () => {
    mockFetch(500, { error: "Server error" });
    await expect(new WyrdClient().query("x")).rejects.toThrow(WyrdAPIError);
  });
});

// ---------------------------------------------------------------------------
// getConfigFromMeta
// ---------------------------------------------------------------------------

describe("getConfigFromMeta", () => {
  test("returns defaults when metadata is empty", () => {
    const cfg = getConfigFromMeta({});
    expect(cfg.host).toBe("localhost");
    expect(cfg.port).toBe(8765);
  });
  test("returns configured values", () => {
    const cfg = getConfigFromMeta({ [META_KEY]: { host: "192.168.1.1", port: 9000 } });
    expect(cfg.host).toBe("192.168.1.1");
    expect(cfg.port).toBe(9000);
  });
  test("handles null metadata", () => {
    const cfg = getConfigFromMeta(null);
    expect(cfg.host).toBe("localhost");
  });
  test("coerces port to number", () => {
    const cfg = getConfigFromMeta({ [META_KEY]: { host: "x", port: "9999" } });
    expect(typeof cfg.port).toBe("number");
  });
});

// ---------------------------------------------------------------------------
// buildConfigMeta
// ---------------------------------------------------------------------------

describe("buildConfigMeta", () => {
  test("sets host and port under META_KEY", () => {
    const meta = buildConfigMeta("myhost", 1234);
    expect(meta[META_KEY].host).toBe("myhost");
    expect(meta[META_KEY].port).toBe(1234);
  });
});

// ---------------------------------------------------------------------------
// normalizePersonaId
// ---------------------------------------------------------------------------

describe("normalizePersonaId", () => {
  test("lowercases", () => expect(normalizePersonaId("Sigrid")).toBe("sigrid"));
  test("replaces spaces", () => expect(normalizePersonaId("Erik Red")).toBe("erik_red"));
  test("truncates at 64", () => expect(normalizePersonaId("a".repeat(100)).length).toBe(64));
  test("handles null", () => expect(normalizePersonaId(null)).toBe(""));
});

// ---------------------------------------------------------------------------
// formatResponse
// ---------------------------------------------------------------------------

describe("formatResponse", () => {
  test("includes personaId", () => {
    expect(formatResponse("sigrid", { response: "Context." })).toContain("sigrid");
  });
  test("includes response text", () => {
    expect(formatResponse("x", { response: "Storm coming." })).toContain("Storm coming.");
  });
  test("handles null responseData", () => {
    const r = formatResponse("x", null);
    expect(r).toContain("[x]");
  });
});

// ---------------------------------------------------------------------------
// personaIdFromItem
// ---------------------------------------------------------------------------

describe("personaIdFromItem", () => {
  test("uses metadata.wyrdforge.persona_id if present", () => {
    const item = { metadata: { "wyrdforge.persona_id": "Sigrid" }, name: "Other" };
    expect(personaIdFromItem(item)).toBe("sigrid");
  });
  test("falls back to metadata.name", () => {
    const item = { metadata: { name: "Gunnar" }, name: "Other" };
    expect(personaIdFromItem(item)).toBe("gunnar");
  });
  test("falls back to item.name", () => {
    const item = { name: "Astrid" };
    expect(personaIdFromItem(item)).toBe("astrid");
  });
  test("returns empty string for null item", () => {
    expect(personaIdFromItem(null)).toBe("");
  });
  test("handles undefined item", () => {
    expect(typeof personaIdFromItem(undefined)).toBe("string");
  });
});

// ---------------------------------------------------------------------------
// panelReducer
// ---------------------------------------------------------------------------

describe("panelReducer", () => {
  test("initialPanelState returns defaults", () => {
    const s = initialPanelState();
    expect(s.loading).toBe(false);
    expect(s.personaId).toBe("");
    expect(s.error).toBeNull();
  });

  test("SET_PERSONA updates personaId", () => {
    const s = panelReducer(initialPanelState(), { type: "SET_PERSONA", payload: "sigrid" });
    expect(s.personaId).toBe("sigrid");
  });

  test("SET_PERSONA clears error", () => {
    let s = panelReducer(initialPanelState(), { type: "QUERY_ERROR", payload: "oops" });
    s = panelReducer(s, { type: "SET_PERSONA", payload: "x" });
    expect(s.error).toBeNull();
  });

  test("SET_QUERY updates query", () => {
    const s = panelReducer(initialPanelState(), { type: "SET_QUERY", payload: "Hello" });
    expect(s.query).toBe("Hello");
  });

  test("QUERY_START sets loading=true and clears output", () => {
    let s = panelReducer(initialPanelState(), { type: "QUERY_SUCCESS", payload: "old" });
    s = panelReducer(s, { type: "QUERY_START" });
    expect(s.loading).toBe(true);
    expect(s.output).toBe("");
    expect(s.error).toBeNull();
  });

  test("QUERY_SUCCESS sets loading=false and output", () => {
    let s = panelReducer(initialPanelState(), { type: "QUERY_START" });
    s = panelReducer(s, { type: "QUERY_SUCCESS", payload: "result text" });
    expect(s.loading).toBe(false);
    expect(s.output).toBe("result text");
  });

  test("QUERY_ERROR sets loading=false and error", () => {
    let s = panelReducer(initialPanelState(), { type: "QUERY_START" });
    s = panelReducer(s, { type: "QUERY_ERROR", payload: "connection failed" });
    expect(s.loading).toBe(false);
    expect(s.error).toBe("connection failed");
  });

  test("CLEAR resets to initial", () => {
    let s = panelReducer(initialPanelState(), { type: "SET_PERSONA", payload: "sigrid" });
    s = panelReducer(s, { type: "CLEAR" });
    expect(s.personaId).toBe("");
  });

  test("unknown action returns state unchanged", () => {
    const s = initialPanelState();
    expect(panelReducer(s, { type: "UNKNOWN" })).toEqual(s);
  });
});

// ---------------------------------------------------------------------------
// renderPanel
// ---------------------------------------------------------------------------

describe("renderPanel", () => {
  test("includes persona input with value", () => {
    const s = { ...initialPanelState(), personaId: "gunnar" };
    expect(renderPanel(s)).toContain('value="gunnar"');
  });

  test("includes disabled attribute when loading", () => {
    const s = { ...initialPanelState(), loading: true };
    expect(renderPanel(s)).toContain("disabled");
  });

  test("shows Loading text when loading", () => {
    const s = { ...initialPanelState(), loading: true };
    expect(renderPanel(s)).toContain("Loading");
  });

  test("shows error paragraph when error set", () => {
    const s = { ...initialPanelState(), error: "server down" };
    expect(renderPanel(s)).toContain("wyrd-error");
    expect(renderPanel(s)).toContain("server down");
  });

  test("shows output pre when output set", () => {
    const s = { ...initialPanelState(), output: "context here" };
    expect(renderPanel(s)).toContain("wyrd-output");
    expect(renderPanel(s)).toContain("context here");
  });

  test("escapes < in output", () => {
    const s = { ...initialPanelState(), output: "<script>" };
    expect(renderPanel(s)).toContain("&lt;script>");
  });

  test("no error or output sections when both empty", () => {
    const html = renderPanel(initialPanelState());
    expect(html).not.toContain("wyrd-error");
    expect(html).not.toContain("wyrd-output");
  });
});
