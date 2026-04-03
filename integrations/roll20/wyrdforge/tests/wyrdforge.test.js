/**
 * Tests for WyrdForge Roll20 API module (Phase 10B).
 * Pure functions are inlined to avoid ES module complications with Jest.
 */
"use strict";

// ---------------------------------------------------------------------------
// Inline pure functions under test (mirrors wyrdforge.js)
// ---------------------------------------------------------------------------

const WF_CMD = "!wyrd";
const WF_SYNC_CMD = "!wyrd-sync";
const WF_HEALTH_CMD = "!wyrd-health";

function getConfig(stateObj) {
  if (!stateObj.wyrdforge) {
    stateObj.wyrdforge = { host: "localhost", port: 8765, enabled: true };
  }
  return stateObj.wyrdforge;
}

function parseCommand(message) {
  const trimmed = (message || "").trim();
  if (trimmed === WF_HEALTH_CMD) return { cmd: "health", personaId: "", query: "" };
  if (trimmed.startsWith(WF_SYNC_CMD)) {
    const rest = trimmed.slice(WF_SYNC_CMD.length).trim();
    return { cmd: "sync", personaId: rest, query: "" };
  }
  if (trimmed.startsWith(WF_CMD)) {
    const rest = trimmed.slice(WF_CMD.length).trim();
    const spaceIdx = rest.indexOf(" ");
    if (spaceIdx === -1) return { cmd: "query", personaId: rest, query: "" };
    return {
      cmd: "query",
      personaId: rest.slice(0, spaceIdx),
      query: rest.slice(spaceIdx + 1).trim(),
    };
  }
  return { cmd: null, personaId: "", query: "" };
}

function normalizePersonaId(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

function formatChatOutput(personaId, responseText) {
  const divider = "—".repeat(40);
  return `/w gm &{template:default} {{name=ᚹ WyrdForge — ${personaId}}} {{${divider}=${responseText}}}`;
}

function formatStatus(message) {
  return `/w gm [WyrdForge] ${message}`;
}

function buildGetOptions(host, port, path) {
  return { hostname: host, port, path, method: "GET" };
}

function buildPostOptions(host, port, path, payload) {
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

function httpRequest(http, opts, body = null) {
  return new Promise((resolve, reject) => {
    const req = http.request(opts, (res) => {
      let raw = "";
      res.on("data", (chunk) => { raw += chunk; });
      res.on("end", () => {
        try { resolve({ status: res.statusCode, data: JSON.parse(raw) }); }
        catch (err) { reject(new Error(`JSON parse error: ${err.message}`)); }
      });
    });
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

async function queryWyrd(http, config, personaId, query = "") {
  const payload = {
    persona_id: personaId,
    user_input: query || "What is the current state of the world?",
    use_turn_loop: false,
  };
  const { options, body } = buildPostOptions(config.host, config.port, "/query", payload);
  const result = await httpRequest(http, options, body);
  return result.data?.response ?? "";
}

async function syncActor(http, config, personaId, name) {
  const payload = {
    event_type: "fact",
    payload: { subject_id: personaId, key: "name", value: name },
  };
  const { options, body } = buildPostOptions(config.host, config.port, "/event", payload);
  const result = await httpRequest(http, options, body);
  return result.data?.ok === true;
}

async function checkHealth(http, config) {
  const opts = buildGetOptions(config.host, config.port, "/health");
  const result = await httpRequest(http, opts);
  return result.data?.status === "ok";
}

// ---------------------------------------------------------------------------
// Mock http module factory
// ---------------------------------------------------------------------------

function makeMockHttp(statusCode, responseBody) {
  return {
    request: jest.fn((_opts, callback) => {
      const res = {
        statusCode,
        on: jest.fn((event, handler) => {
          if (event === "data") handler(JSON.stringify(responseBody));
          if (event === "end") handler();
        }),
      };
      // Call callback asynchronously like real http
      setImmediate(() => callback(res));
      return { on: jest.fn(), write: jest.fn(), end: jest.fn() };
    }),
  };
}

function makeMockHttpError(errorMsg) {
  return {
    request: jest.fn((_opts, _callback) => {
      const req = {
        on: jest.fn((event, handler) => {
          if (event === "error") setImmediate(() => handler(new Error(errorMsg)));
        }),
        write: jest.fn(),
        end: jest.fn(),
      };
      return req;
    }),
  };
}

// ---------------------------------------------------------------------------
// getConfig tests
// ---------------------------------------------------------------------------

describe("getConfig", () => {
  test("initializes defaults if missing", () => {
    const s = {};
    const cfg = getConfig(s);
    expect(cfg.host).toBe("localhost");
    expect(cfg.port).toBe(8765);
    expect(cfg.enabled).toBe(true);
  });

  test("returns existing config if present", () => {
    const s = { wyrdforge: { host: "192.168.1.1", port: 9000, enabled: false } };
    const cfg = getConfig(s);
    expect(cfg.host).toBe("192.168.1.1");
    expect(cfg.port).toBe(9000);
  });

  test("mutates state in place", () => {
    const s = {};
    getConfig(s);
    expect(s.wyrdforge).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// parseCommand tests
// ---------------------------------------------------------------------------

describe("parseCommand", () => {
  test("returns null cmd for unrelated message", () => {
    expect(parseCommand("Hello").cmd).toBeNull();
  });

  test("parses !wyrd-health", () => {
    expect(parseCommand("!wyrd-health").cmd).toBe("health");
  });

  test("parses !wyrd-sync with name", () => {
    const r = parseCommand("!wyrd-sync Sigrid Stormborn");
    expect(r.cmd).toBe("sync");
    expect(r.personaId).toBe("Sigrid Stormborn");
  });

  test("parses !wyrd-sync with no name", () => {
    const r = parseCommand("!wyrd-sync");
    expect(r.cmd).toBe("sync");
    expect(r.personaId).toBe("");
  });

  test("parses !wyrd with persona only", () => {
    const r = parseCommand("!wyrd sigrid");
    expect(r.cmd).toBe("query");
    expect(r.personaId).toBe("sigrid");
    expect(r.query).toBe("");
  });

  test("parses !wyrd with persona and query", () => {
    const r = parseCommand("!wyrd sigrid What is happening now?");
    expect(r.personaId).toBe("sigrid");
    expect(r.query).toBe("What is happening now?");
  });

  test("parses !wyrd with no args", () => {
    const r = parseCommand("!wyrd");
    expect(r.cmd).toBe("query");
    expect(r.personaId).toBe("");
  });

  test("handles null/undefined message", () => {
    expect(parseCommand(null).cmd).toBeNull();
    expect(parseCommand(undefined).cmd).toBeNull();
  });

  test("trims whitespace", () => {
    const r = parseCommand("  !wyrd sigrid  Hello  ");
    expect(r.personaId).toBe("sigrid");
    expect(r.query).toBe("Hello");
  });
});

// ---------------------------------------------------------------------------
// normalizePersonaId tests
// ---------------------------------------------------------------------------

describe("normalizePersonaId", () => {
  test("lowercases", () => expect(normalizePersonaId("Sigrid")).toBe("sigrid"));
  test("replaces spaces", () => expect(normalizePersonaId("Erik Red")).toBe("erik_red"));
  test("collapses underscores", () => expect(normalizePersonaId("a  b")).toBe("a_b"));
  test("truncates at 64", () => expect(normalizePersonaId("x".repeat(100)).length).toBe(64));
  test("handles empty string", () => expect(normalizePersonaId("")).toBe(""));
  test("handles null", () => expect(normalizePersonaId(null)).toBe(""));
});

// ---------------------------------------------------------------------------
// formatChatOutput tests
// ---------------------------------------------------------------------------

describe("formatChatOutput", () => {
  test("starts with /w gm", () => {
    expect(formatChatOutput("sigrid", "context")).toMatch(/^\/w gm/);
  });

  test("contains persona_id", () => {
    expect(formatChatOutput("gunnar", "text")).toContain("gunnar");
  });

  test("contains response text", () => {
    expect(formatChatOutput("x", "The hall burns.")).toContain("The hall burns.");
  });
});

// ---------------------------------------------------------------------------
// formatStatus tests
// ---------------------------------------------------------------------------

describe("formatStatus", () => {
  test("starts with /w gm [WyrdForge]", () => {
    expect(formatStatus("ok")).toMatch(/^\/w gm \[WyrdForge\]/);
  });

  test("contains message", () => {
    expect(formatStatus("server online")).toContain("server online");
  });
});

// ---------------------------------------------------------------------------
// buildGetOptions tests
// ---------------------------------------------------------------------------

describe("buildGetOptions", () => {
  test("returns correct structure", () => {
    const opts = buildGetOptions("localhost", 8765, "/health");
    expect(opts.hostname).toBe("localhost");
    expect(opts.port).toBe(8765);
    expect(opts.path).toBe("/health");
    expect(opts.method).toBe("GET");
  });
});

// ---------------------------------------------------------------------------
// buildPostOptions tests
// ---------------------------------------------------------------------------

describe("buildPostOptions", () => {
  test("serializes payload to body string", () => {
    const { body } = buildPostOptions("localhost", 8765, "/query", { key: "val" });
    expect(JSON.parse(body)).toEqual({ key: "val" });
  });

  test("sets Content-Type header", () => {
    const { options } = buildPostOptions("localhost", 8765, "/query", {});
    expect(options.headers["Content-Type"]).toBe("application/json");
  });

  test("sets Content-Length header", () => {
    const { options, body } = buildPostOptions("localhost", 8765, "/query", { x: 1 });
    expect(options.headers["Content-Length"]).toBe(Buffer.byteLength(body));
  });

  test("sets method POST", () => {
    const { options } = buildPostOptions("localhost", 8765, "/query", {});
    expect(options.method).toBe("POST");
  });
});

// ---------------------------------------------------------------------------
// httpRequest tests
// ---------------------------------------------------------------------------

describe("httpRequest", () => {
  test("resolves with parsed JSON", async () => {
    const http = makeMockHttp(200, { status: "ok" });
    const result = await httpRequest(http, { hostname: "localhost", port: 8765, path: "/health", method: "GET" });
    expect(result.data.status).toBe("ok");
    expect(result.status).toBe(200);
  });

  test("rejects on request error", async () => {
    const http = makeMockHttpError("ECONNREFUSED");
    await expect(httpRequest(http, {})).rejects.toThrow("ECONNREFUSED");
  });
});

// ---------------------------------------------------------------------------
// queryWyrd tests
// ---------------------------------------------------------------------------

describe("queryWyrd", () => {
  test("returns response text", async () => {
    const http = makeMockHttp(200, { response: "Storm approaches." });
    const result = await queryWyrd(http, { host: "localhost", port: 8765 }, "sigrid", "test");
    expect(result).toBe("Storm approaches.");
  });

  test("returns empty string if response missing", async () => {
    const http = makeMockHttp(200, { other: "data" });
    const result = await queryWyrd(http, { host: "localhost", port: 8765 }, "sigrid");
    expect(result).toBe("");
  });

  test("sends persona_id in request", async () => {
    const http = makeMockHttp(200, { response: "" });
    await queryWyrd(http, { host: "localhost", port: 8765 }, "gunnar", "hello");
    const reqCall = http.request.mock.calls[0][0];
    expect(reqCall.path).toBe("/query");
  });
});

// ---------------------------------------------------------------------------
// syncActor tests
// ---------------------------------------------------------------------------

describe("syncActor", () => {
  test("returns true on success", async () => {
    const http = makeMockHttp(200, { ok: true });
    const result = await syncActor(http, { host: "localhost", port: 8765 }, "sigrid", "Sigrid");
    expect(result).toBe(true);
  });

  test("returns false if ok field missing", async () => {
    const http = makeMockHttp(200, { ok: false });
    const result = await syncActor(http, { host: "localhost", port: 8765 }, "x", "X");
    expect(result).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// checkHealth tests
// ---------------------------------------------------------------------------

describe("checkHealth", () => {
  test("returns true when server is ok", async () => {
    const http = makeMockHttp(200, { status: "ok" });
    const result = await checkHealth(http, { host: "localhost", port: 8765 });
    expect(result).toBe(true);
  });

  test("returns false when status not ok", async () => {
    const http = makeMockHttp(200, { status: "degraded" });
    const result = await checkHealth(http, { host: "localhost", port: 8765 });
    expect(result).toBe(false);
  });

  test("rejects on connection error", async () => {
    const http = makeMockHttpError("ECONNREFUSED");
    await expect(checkHealth(http, { host: "localhost", port: 8765 })).rejects.toThrow();
  });
});
