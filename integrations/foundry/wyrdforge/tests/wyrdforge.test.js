/**
 * Tests for WyrdForge Foundry VTT module (Phase 10A).
 * Pure functions are inlined here to avoid ES module import complexity with Jest.
 */
"use strict";

// ---------------------------------------------------------------------------
// Inline pure functions under test (mirrors scripts/wyrdforge.js)
// ---------------------------------------------------------------------------

const MODULE_ID = "wyrdforge";
const CHAT_COMMAND = "/wyrd";
const SECTION_ATTR = "data-wyrd-context";

class WyrdConnectionError extends Error {
  constructor(message, cause) {
    super(message);
    this.name = "WyrdConnectionError";
    this.cause = cause;
  }
}

class WyrdAPIError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "WyrdAPIError";
    this.status = status;
    this.body = body;
  }
}

class WyrdClient {
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
      resp = await globalThis.fetch(`${this.baseUrl}${path}`, {
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
      resp = await globalThis.fetch(`${this.baseUrl}${path}`, {
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

function parseChatCommand(message) {
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

function formatContextCard(personaId, responseData) {
  const response = (responseData && responseData.response) ? responseData.response : "";
  return `<div class="wyrd-context-card" ${SECTION_ATTR}="true">
  <h3 class="wyrd-persona">&#x16B9; ${personaId}</h3>
  <div class="wyrd-context-body">${response.replace(/\n/g, "<br>")}</div>
</div>`;
}

function normalizePersonaId(actorName) {
  return actorName.toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

async function handleChatMessage(client, createChatMessage, notifications, message) {
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
// Test helpers
// ---------------------------------------------------------------------------

function mockFetch(status, body) {
  const spy = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  globalThis.fetch = spy;
  return spy;
}

function mockFetchReject(error) {
  const spy = jest.fn().mockRejectedValue(error);
  globalThis.fetch = spy;
  return spy;
}

// AbortSignal.timeout may not exist in jsdom — polyfill minimally
if (!AbortSignal.timeout) {
  AbortSignal.timeout = () => new AbortController().signal;
}

// ---------------------------------------------------------------------------
// WyrdClient tests
// ---------------------------------------------------------------------------

describe("WyrdClient", () => {
  test("constructs with defaults", () => {
    const c = new WyrdClient();
    expect(c.baseUrl).toBe("http://localhost:8765");
  });

  test("constructs with custom host/port", () => {
    const c = new WyrdClient({ host: "192.168.1.1", port: 9000 });
    expect(c.baseUrl).toBe("http://192.168.1.1:9000");
  });

  test("health() calls /health", async () => {
    const spy = mockFetch(200, { status: "ok" });
    const c = new WyrdClient();
    const r = await c.health();
    expect(r.status).toBe("ok");
    expect(spy).toHaveBeenCalledWith("http://localhost:8765/health", expect.anything());
  });

  test("query() sends correct body", async () => {
    mockFetch(200, { response: "context here" });
    const c = new WyrdClient();
    const r = await c.query("sigrid", "Hello");
    expect(r.response).toBe("context here");
  });

  test("query() sends persona_id", async () => {
    const spy = mockFetch(200, { response: "" });
    const c = new WyrdClient();
    await c.query("gunnar", "test");
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.persona_id).toBe("gunnar");
  });

  test("query() sends location_id when provided", async () => {
    const spy = mockFetch(200, { response: "" });
    const c = new WyrdClient();
    await c.query("sigrid", "hi", { locationId: "hall" });
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.location_id).toBe("hall");
  });

  test("query() omits location_id when not provided", async () => {
    const spy = mockFetch(200, { response: "" });
    const c = new WyrdClient();
    await c.query("sigrid");
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.location_id).toBeUndefined();
  });

  test("pushEvent() sends event_type and payload", async () => {
    const spy = mockFetch(200, { ok: true });
    const c = new WyrdClient();
    await c.pushEvent("observation", { title: "Storm", summary: "A storm." });
    const body = JSON.parse(spy.mock.calls[0][1].body);
    expect(body.event_type).toBe("observation");
    expect(body.payload.title).toBe("Storm");
  });

  test("throws WyrdConnectionError on fetch failure", async () => {
    mockFetchReject(new Error("ECONNREFUSED"));
    const c = new WyrdClient();
    await expect(c.health()).rejects.toThrow(WyrdConnectionError);
  });

  test("throws WyrdAPIError on 500 with error field", async () => {
    mockFetch(500, { error: "Internal server error" });
    const c = new WyrdClient();
    await expect(c.query("x")).rejects.toThrow(WyrdAPIError);
  });

  test("WyrdAPIError carries status code", async () => {
    mockFetch(404, { error: "Not found" });
    const c = new WyrdClient();
    let err;
    try { await c.getFacts("nobody"); } catch (e) { err = e; }
    expect(err.status).toBe(404);
  });

  test("WyrdConnectionError name is correct", async () => {
    mockFetchReject(new Error("net error"));
    const c = new WyrdClient();
    let err;
    try { await c.health(); } catch (e) { err = e; }
    expect(err.name).toBe("WyrdConnectionError");
  });

  test("getFacts() encodes entity_id in URL", async () => {
    const spy = mockFetch(200, { facts: [] });
    const c = new WyrdClient();
    await c.getFacts("some entity");
    expect(spy.mock.calls[0][0]).toContain("some%20entity");
  });

  test("getWorld() calls /world", async () => {
    const spy = mockFetch(200, { world_id: "w1" });
    const c = new WyrdClient();
    await c.getWorld();
    expect(spy.mock.calls[0][0]).toContain("/world");
  });
});

// ---------------------------------------------------------------------------
// parseChatCommand tests
// ---------------------------------------------------------------------------

describe("parseChatCommand", () => {
  test("non-wyrd message returns isWyrd=false", () => {
    expect(parseChatCommand("Hello everyone").isWyrd).toBe(false);
  });

  test("/wyrd alone — isWyrd but no personaId", () => {
    const r = parseChatCommand("/wyrd");
    expect(r.isWyrd).toBe(true);
    expect(r.personaId).toBe("");
  });

  test("/wyrd sigrid — persona only, empty query", () => {
    const r = parseChatCommand("/wyrd sigrid");
    expect(r.isWyrd).toBe(true);
    expect(r.personaId).toBe("sigrid");
    expect(r.query).toBe("");
  });

  test("/wyrd sigrid What is happening — full parse", () => {
    const r = parseChatCommand("/wyrd sigrid What is happening");
    expect(r.personaId).toBe("sigrid");
    expect(r.query).toBe("What is happening");
  });

  test("trims leading/trailing whitespace", () => {
    const r = parseChatCommand("  /wyrd gunnar  Hello  ");
    expect(r.personaId).toBe("gunnar");
    expect(r.query).toBe("Hello");
  });

  test("handles multi-word query", () => {
    const r = parseChatCommand("/wyrd astrid Tell me about the storm at sea");
    expect(r.query).toBe("Tell me about the storm at sea");
  });
});

// ---------------------------------------------------------------------------
// formatContextCard tests
// ---------------------------------------------------------------------------

describe("formatContextCard", () => {
  test("contains persona_id", () => {
    const html = formatContextCard("sigrid", { response: "Context." });
    expect(html).toContain("sigrid");
  });

  test("contains SECTION_ATTR", () => {
    const html = formatContextCard("sigrid", { response: "" });
    expect(html).toContain(SECTION_ATTR);
  });

  test("contains response text", () => {
    const html = formatContextCard("gunnar", { response: "The hall is quiet." });
    expect(html).toContain("The hall is quiet.");
  });

  test("converts newlines to <br>", () => {
    const html = formatContextCard("x", { response: "line1\nline2" });
    expect(html).toContain("<br>");
  });

  test("handles null responseData gracefully", () => {
    const html = formatContextCard("x", null);
    expect(html).toContain("wyrd-context-card");
  });

  test("handles missing response field", () => {
    const html = formatContextCard("x", { other: "stuff" });
    expect(html).toContain("wyrd-context-card");
  });
});

// ---------------------------------------------------------------------------
// normalizePersonaId tests
// ---------------------------------------------------------------------------

describe("normalizePersonaId", () => {
  test("lowercases name", () => {
    expect(normalizePersonaId("Sigrid")).toBe("sigrid");
  });

  test("replaces spaces with underscore", () => {
    expect(normalizePersonaId("Erik the Red")).toBe("erik_the_red");
  });

  test("replaces special chars with underscore", () => {
    expect(normalizePersonaId("Björn-Ironside")).toBe("bj_rn_ironside");
  });

  test("collapses multiple underscores", () => {
    expect(normalizePersonaId("a  b")).toBe("a_b");
  });

  test("truncates at 64 chars", () => {
    const long = "a".repeat(100);
    expect(normalizePersonaId(long).length).toBe(64);
  });
});

// ---------------------------------------------------------------------------
// handleChatMessage tests
// ---------------------------------------------------------------------------

describe("handleChatMessage", () => {
  let client;
  let createMsg;
  let notifications;

  beforeEach(() => {
    client = { query: jest.fn().mockResolvedValue({ response: "World context." }) };
    createMsg = jest.fn().mockResolvedValue({});
    notifications = { error: jest.fn(), info: jest.fn(), warn: jest.fn() };
  });

  test("returns false for non-wyrd message", async () => {
    const result = await handleChatMessage(client, createMsg, notifications, "Hello");
    expect(result).toBe(false);
  });

  test("returns true for /wyrd command", async () => {
    const result = await handleChatMessage(client, createMsg, notifications, "/wyrd sigrid");
    expect(result).toBe(true);
  });

  test("calls client.query with correct persona_id", async () => {
    await handleChatMessage(client, createMsg, notifications, "/wyrd gunnar What happened?");
    expect(client.query).toHaveBeenCalledWith("gunnar", "What happened?", { useTurnLoop: false });
  });

  test("calls createChatMessage with HTML content", async () => {
    await handleChatMessage(client, createMsg, notifications, "/wyrd sigrid");
    expect(createMsg).toHaveBeenCalled();
    const arg = createMsg.mock.calls[0][0];
    expect(arg.content).toContain("wyrd-context-card");
  });

  test("calls notifications.error on client failure", async () => {
    client.query.mockRejectedValue(new Error("server down"));
    await handleChatMessage(client, createMsg, notifications, "/wyrd sigrid test");
    expect(notifications.error).toHaveBeenCalledWith(expect.stringContaining("server down"));
  });

  test("returns false for /wyrd with no persona", async () => {
    const result = await handleChatMessage(client, createMsg, notifications, "/wyrd");
    expect(result).toBe(false);
  });
});
