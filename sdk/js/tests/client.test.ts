/**
 * Tests for WyrdClient — Phase 8A JS/TS SDK.
 * All tests mock globalThis.fetch; no real server required.
 */

import { WyrdClient, WyrdAPIError, WyrdConnectionError } from "../src/index.js";
import type { WorldContextPacket, FactRecord } from "../src/index.js";

// ---------------------------------------------------------------------------
// Fetch mock helpers
// ---------------------------------------------------------------------------

function mockFetch(status: number, body: unknown): jest.SpyInstance {
  return jest.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
}

function mockFetchReject(error: Error): jest.SpyInstance {
  return jest.spyOn(globalThis, "fetch").mockRejectedValue(error);
}

afterEach(() => {
  jest.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Constructor defaults
// ---------------------------------------------------------------------------

describe("WyrdClient — construction", () => {
  it("constructs with default options", () => {
    const client = new WyrdClient();
    expect(client).toBeInstanceOf(WyrdClient);
  });

  it("constructs with custom options", () => {
    const client = new WyrdClient({ host: "192.168.1.5", port: 9000, timeoutMs: 5000 });
    expect(client).toBeInstanceOf(WyrdClient);
  });
});

// ---------------------------------------------------------------------------
// health()
// ---------------------------------------------------------------------------

describe("WyrdClient.health()", () => {
  it("returns true when server responds ok", async () => {
    mockFetch(200, { status: "ok" });
    const client = new WyrdClient();
    expect(await client.health()).toBe(true);
  });

  it("returns false when server is unreachable", async () => {
    mockFetchReject(new TypeError("fetch failed"));
    const client = new WyrdClient();
    expect(await client.health()).toBe(false);
  });

  it("returns false when status is not ok", async () => {
    mockFetch(200, { status: "degraded" });
    const client = new WyrdClient();
    expect(await client.health()).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// query()
// ---------------------------------------------------------------------------

describe("WyrdClient.query()", () => {
  it("returns response string", async () => {
    mockFetch(200, { response: "The runes speak of change." });
    const client = new WyrdClient();
    const reply = await client.query("sigrid", "What do you see?");
    expect(reply).toBe("The runes speak of change.");
  });

  it("sends persona_id and user_input in POST body", async () => {
    const spy = mockFetch(200, { response: "test" });
    const client = new WyrdClient();
    await client.query("sigrid", "Hello");
    const call = spy.mock.calls[0];
    const body = JSON.parse((call[1] as RequestInit).body as string);
    expect(body.persona_id).toBe("sigrid");
    expect(body.user_input).toBe("Hello");
  });

  it("sends use_turn_loop true by default", async () => {
    const spy = mockFetch(200, { response: "ok" });
    const client = new WyrdClient();
    await client.query("sigrid", "Hello");
    const body = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.use_turn_loop).toBe(true);
  });

  it("sends use_turn_loop false when specified", async () => {
    const spy = mockFetch(200, { response: "ok" });
    const client = new WyrdClient();
    await client.query("sigrid", "Hello", { useTurnLoop: false });
    const body = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.use_turn_loop).toBe(false);
  });

  it("includes location_id when provided", async () => {
    const spy = mockFetch(200, { response: "ok" });
    const client = new WyrdClient();
    await client.query("sigrid", "Hello", { locationId: "hall" });
    const body = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.location_id).toBe("hall");
  });

  it("includes bond_id when provided", async () => {
    const spy = mockFetch(200, { response: "ok" });
    const client = new WyrdClient();
    await client.query("sigrid", "Hello", { bondId: "bond-001" });
    const body = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.bond_id).toBe("bond-001");
  });

  it("throws WyrdConnectionError when fetch rejects", async () => {
    mockFetchReject(new TypeError("fetch failed"));
    const client = new WyrdClient();
    await expect(client.query("sigrid", "Hi")).rejects.toBeInstanceOf(WyrdConnectionError);
  });

  it("throws WyrdAPIError on 400 response", async () => {
    mockFetch(400, { error: "persona_id required" });
    const client = new WyrdClient();
    await expect(client.query("", "Hi")).rejects.toBeInstanceOf(WyrdAPIError);
  });

  it("WyrdAPIError carries status code", async () => {
    mockFetch(400, { error: "bad input" });
    const client = new WyrdClient();
    try {
      await client.query("", "Hi");
    } catch (err) {
      expect((err as WyrdAPIError).status).toBe(400);
    }
  });

  it("WyrdAPIError carries error message from body", async () => {
    mockFetch(400, { error: "persona_id and user_input are required" });
    const client = new WyrdClient();
    try {
      await client.query("", "Hi");
    } catch (err) {
      expect((err as WyrdAPIError).message).toContain("persona_id");
    }
  });
});

// ---------------------------------------------------------------------------
// getWorld()
// ---------------------------------------------------------------------------

describe("WyrdClient.getWorld()", () => {
  const mockPacket: WorldContextPacket = {
    query_timestamp: "2026-04-02T12:00:00Z",
    world_id: "test_world",
    focus_entities: [],
    location_context: null,
    present_entities: [],
    canonical_facts: {},
    active_policies: [],
    recent_observations: [],
    open_contradiction_count: 0,
    formatted_for_llm: "=== WORLD STATE ===\nNo entities present.",
  };

  it("returns WorldContextPacket", async () => {
    mockFetch(200, mockPacket);
    const client = new WyrdClient();
    const world = await client.getWorld();
    expect(world.world_id).toBe("test_world");
  });

  it("returned packet has formatted_for_llm", async () => {
    mockFetch(200, mockPacket);
    const client = new WyrdClient();
    const world = await client.getWorld();
    expect(typeof world.formatted_for_llm).toBe("string");
  });

  it("throws WyrdConnectionError when unreachable", async () => {
    mockFetchReject(new TypeError("fetch failed"));
    const client = new WyrdClient();
    await expect(client.getWorld()).rejects.toBeInstanceOf(WyrdConnectionError);
  });

  it("throws WyrdAPIError on 500", async () => {
    mockFetch(500, { error: "internal error" });
    const client = new WyrdClient();
    await expect(client.getWorld()).rejects.toBeInstanceOf(WyrdAPIError);
  });
});

// ---------------------------------------------------------------------------
// getFacts()
// ---------------------------------------------------------------------------

describe("WyrdClient.getFacts()", () => {
  const mockFacts: FactRecord[] = [
    {
      record_id: "rec-001",
      record_type: "canonical_fact",
      content: {
        title: "sigrid.role = völva",
        structured_payload: {
          fact_subject_id: "sigrid",
          fact_key: "role",
          fact_value: "völva",
          value_type: "string",
          domain: "identity",
        },
      },
    },
  ];

  it("returns array of FactRecord", async () => {
    mockFetch(200, { facts: mockFacts });
    const client = new WyrdClient();
    const facts = await client.getFacts("sigrid");
    expect(Array.isArray(facts)).toBe(true);
    expect(facts.length).toBe(1);
  });

  it("fact has expected shape", async () => {
    mockFetch(200, { facts: mockFacts });
    const client = new WyrdClient();
    const facts = await client.getFacts("sigrid");
    expect(facts[0].content.structured_payload.fact_value).toBe("völva");
  });

  it("encodes entity_id in URL", async () => {
    const spy = mockFetch(200, { facts: [] });
    const client = new WyrdClient();
    await client.getFacts("entity with spaces");
    const url = spy.mock.calls[0][0] as string;
    expect(url).toContain("entity%20with%20spaces");
  });

  it("returns empty array for unknown entity", async () => {
    mockFetch(200, { facts: [] });
    const client = new WyrdClient();
    const facts = await client.getFacts("nobody");
    expect(facts).toEqual([]);
  });

  it("throws WyrdAPIError on 400 (missing entity_id)", async () => {
    mockFetch(400, { error: "entity_id query param required" });
    const client = new WyrdClient();
    await expect(client.getFacts("")).rejects.toBeInstanceOf(WyrdAPIError);
  });
});

// ---------------------------------------------------------------------------
// pushEvent()
// ---------------------------------------------------------------------------

describe("WyrdClient.pushEvent()", () => {
  it("returns true on success", async () => {
    mockFetch(200, { ok: true });
    const client = new WyrdClient();
    const result = await client.pushEvent("observation", {
      title: "Storm",
      summary: "A storm arrived.",
    });
    expect(result).toBe(true);
  });

  it("sends event_type and payload", async () => {
    const spy = mockFetch(200, { ok: true });
    const client = new WyrdClient();
    await client.pushEvent("fact", {
      subject_id: "gunnar",
      key: "weapon",
      value: "axe",
    });
    const body = JSON.parse((spy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.event_type).toBe("fact");
    expect(body.payload.subject_id).toBe("gunnar");
  });

  it("throws WyrdAPIError on 400 (missing event_type)", async () => {
    mockFetch(400, { error: "event_type is required" });
    const client = new WyrdClient();
    await expect(
      client.pushEvent("observation", { title: "", summary: "" })
    ).rejects.toBeInstanceOf(WyrdAPIError);
  });

  it("throws WyrdConnectionError when unreachable", async () => {
    mockFetchReject(new TypeError("fetch failed"));
    const client = new WyrdClient();
    await expect(
      client.pushEvent("observation", { title: "x", summary: "y" })
    ).rejects.toBeInstanceOf(WyrdConnectionError);
  });
});

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

describe("Error classes", () => {
  it("WyrdConnectionError has correct name", () => {
    const err = new WyrdConnectionError("test");
    expect(err.name).toBe("WyrdConnectionError");
    expect(err).toBeInstanceOf(Error);
  });

  it("WyrdAPIError carries status and body", () => {
    const err = new WyrdAPIError("bad input", 400, { error: "bad" });
    expect(err.status).toBe(400);
    expect(err.body).toEqual({ error: "bad" });
    expect(err.name).toBe("WyrdAPIError");
  });
});
