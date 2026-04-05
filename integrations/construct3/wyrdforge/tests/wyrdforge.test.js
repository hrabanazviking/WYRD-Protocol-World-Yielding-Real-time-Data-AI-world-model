/**
 * Tests for WyrdForge Construct 3 addon (Phase 11D).
 *
 * Pure functions are inlined here to avoid C3 SDK / browser dependencies.
 * These tests verify the logic of helpers that live in c3runtime/instance.js.
 */
"use strict";

// ---------------------------------------------------------------------------
// Inline pure functions under test (mirrors c3runtime/instance.js)
// ---------------------------------------------------------------------------

function normalizePersonaId(name) {
  return (name || "")
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
}

function buildQueryBody(personaId, query) {
  return {
    persona_id: personaId,
    user_input: query || "What is the current world state?",
    use_turn_loop: false,
  };
}

function buildEventBody(eventType, payload) {
  return { event_type: eventType, payload };
}

/** Simulates parseResponse() logic for unit testing. */
function parseResponseLogic(ok, status, jsonBody) {
  if (!ok) {
    const data = typeof jsonBody === "object" ? jsonBody : null;
    throw new Error(`WyrdForge: HTTP ${status} — ${data?.error ?? "unknown error"}`);
  }
  return jsonBody;
}

// ---------------------------------------------------------------------------
// normalizePersonaId
// ---------------------------------------------------------------------------

describe("normalizePersonaId", () => {
  test("lowercases input", () => expect(normalizePersonaId("Sigrid")).toBe("sigrid"));
  test("replaces spaces with underscores", () => expect(normalizePersonaId("Erik Red")).toBe("erik_red"));
  test("collapses multiple underscores", () => expect(normalizePersonaId("a  b")).toBe("a_b"));
  test("strips leading underscores", () => expect(normalizePersonaId("_sigrid")).toBe("sigrid"));
  test("strips trailing underscores", () => expect(normalizePersonaId("sigrid_")).toBe("sigrid"));
  test("truncates at 64 chars", () => expect(normalizePersonaId("x".repeat(100)).length).toBe(64));
  test("handles empty string", () => expect(normalizePersonaId("")).toBe(""));
  test("handles null", () => expect(normalizePersonaId(null)).toBe(""));
  test("handles numbers in name", () => expect(normalizePersonaId("npc_001")).toBe("npc_001"));
  test("handles special chars", () => expect(normalizePersonaId("Björn!")).toMatch(/^bj/));
  test("handles already valid id", () => expect(normalizePersonaId("sigrid")).toBe("sigrid"));
  test("replaces dots", () => expect(normalizePersonaId("npc.archer")).toBe("npc_archer"));
  test("replaces dashes", () => expect(normalizePersonaId("npc-one")).toBe("npc_one"));
});

// ---------------------------------------------------------------------------
// buildQueryBody
// ---------------------------------------------------------------------------

describe("buildQueryBody", () => {
  test("sets persona_id", () => {
    expect(buildQueryBody("sigrid", "What happened?").persona_id).toBe("sigrid");
  });

  test("uses provided query as user_input", () => {
    expect(buildQueryBody("x", "Dragon appears").user_input).toBe("Dragon appears");
  });

  test("defaults to world state query when query is empty", () => {
    expect(buildQueryBody("x", "").user_input).toContain("world state");
  });

  test("defaults to world state query when query is null", () => {
    expect(buildQueryBody("x", null).user_input).toContain("world state");
  });

  test("sets use_turn_loop to false", () => {
    expect(buildQueryBody("x", "hi").use_turn_loop).toBe(false);
  });

  test("is JSON-serializable", () => {
    expect(() => JSON.stringify(buildQueryBody("sigrid", "Hello"))).not.toThrow();
  });

  test("has exactly the expected keys", () => {
    const keys = Object.keys(buildQueryBody("x", "y")).sort();
    expect(keys).toEqual(["persona_id", "use_turn_loop", "user_input"]);
  });
});

// ---------------------------------------------------------------------------
// buildEventBody — observation
// ---------------------------------------------------------------------------

describe("buildEventBody — observation", () => {
  test("sets event_type to observation", () => {
    const b = buildEventBody("observation", { title: "Storm", summary: "Rain fell." });
    expect(b.event_type).toBe("observation");
  });

  test("carries title in payload", () => {
    const b = buildEventBody("observation", { title: "Storm", summary: "Rain fell." });
    expect(b.payload.title).toBe("Storm");
  });

  test("carries summary in payload", () => {
    const b = buildEventBody("observation", { title: "Storm", summary: "Rain fell." });
    expect(b.payload.summary).toBe("Rain fell.");
  });

  test("is JSON-serializable", () => {
    const b = buildEventBody("observation", { title: "x", summary: "y" });
    expect(() => JSON.stringify(b)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// buildEventBody — fact
// ---------------------------------------------------------------------------

describe("buildEventBody — fact", () => {
  test("sets event_type to fact", () => {
    const b = buildEventBody("fact", { subject_id: "sigrid", key: "role", value: "seer" });
    expect(b.event_type).toBe("fact");
  });

  test("carries subject_id in payload", () => {
    const b = buildEventBody("fact", { subject_id: "sigrid", key: "role", value: "seer" });
    expect(b.payload.subject_id).toBe("sigrid");
  });

  test("carries key in payload", () => {
    const b = buildEventBody("fact", { subject_id: "sigrid", key: "role", value: "seer" });
    expect(b.payload.key).toBe("role");
  });

  test("carries value in payload", () => {
    const b = buildEventBody("fact", { subject_id: "sigrid", key: "role", value: "seer" });
    expect(b.payload.value).toBe("seer");
  });

  test("is JSON-serializable", () => {
    const b = buildEventBody("fact", { subject_id: "x", key: "k", value: "v" });
    expect(() => JSON.stringify(b)).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// parseResponseLogic
// ---------------------------------------------------------------------------

describe("parseResponseLogic", () => {
  test("returns data on ok=true", () => {
    const data = { response: "World is calm." };
    expect(parseResponseLogic(true, 200, data)).toEqual(data);
  });

  test("throws on non-ok status with error key", () => {
    expect(() => parseResponseLogic(false, 500, { error: "internal" })).toThrow("HTTP 500 — internal");
  });

  test("throws on non-ok status without error key", () => {
    expect(() => parseResponseLogic(false, 404, null)).toThrow("HTTP 404 — unknown error");
  });

  test("throws on non-ok status with string body", () => {
    expect(() => parseResponseLogic(false, 503, "bad")).toThrow("HTTP 503 — unknown error");
  });

  test("passes through empty response on ok", () => {
    expect(parseResponseLogic(true, 200, {})).toEqual({});
  });

  test("passes through response with ok key", () => {
    expect(parseResponseLogic(true, 200, { ok: true })).toEqual({ ok: true });
  });
});

// ---------------------------------------------------------------------------
// SaveToJson / LoadFromJson (state round-trip)
// ---------------------------------------------------------------------------

describe("SaveToJson / LoadFromJson round-trip", () => {
  /**
   * Simulated minimal instance (no C3 deps) for testing save/load logic.
   */
  class FakeInstance {
    constructor() {
      this._host = "localhost";
      this._port = 8765;
      this._timeoutMs = 8000;
      this._enabled = true;
      this._initialized = false;
      this._lastResponse = "";
      this._lastError = "";
    }

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
  }

  test("round-trips host", () => {
    const inst = new FakeInstance();
    inst._host = "192.168.1.5";
    const restored = new FakeInstance();
    restored.LoadFromJson(inst.SaveToJson());
    expect(restored._host).toBe("192.168.1.5");
  });

  test("round-trips port", () => {
    const inst = new FakeInstance();
    inst._port = 9999;
    const restored = new FakeInstance();
    restored.LoadFromJson(inst.SaveToJson());
    expect(restored._port).toBe(9999);
  });

  test("round-trips initialized flag", () => {
    const inst = new FakeInstance();
    inst._initialized = true;
    const restored = new FakeInstance();
    restored.LoadFromJson(inst.SaveToJson());
    expect(restored._initialized).toBe(true);
  });

  test("round-trips lastResponse", () => {
    const inst = new FakeInstance();
    inst._lastResponse = "Sigrid stands by the fire.";
    const restored = new FakeInstance();
    restored.LoadFromJson(inst.SaveToJson());
    expect(restored._lastResponse).toBe("Sigrid stands by the fire.");
  });

  test("round-trips lastError", () => {
    const inst = new FakeInstance();
    inst._lastError = "HTTP 503 — server down";
    const restored = new FakeInstance();
    restored.LoadFromJson(inst.SaveToJson());
    expect(restored._lastError).toBe("HTTP 503 — server down");
  });

  test("LoadFromJson uses defaults for missing keys", () => {
    const restored = new FakeInstance();
    restored.LoadFromJson({});
    expect(restored._host).toBe("localhost");
    expect(restored._port).toBe(8765);
    expect(restored._timeoutMs).toBe(8000);
    expect(restored._lastResponse).toBe("");
  });

  test("SaveToJson is JSON-serializable", () => {
    const inst = new FakeInstance();
    inst._lastResponse = "World is calm.";
    expect(() => JSON.stringify(inst.SaveToJson())).not.toThrow();
  });
});
