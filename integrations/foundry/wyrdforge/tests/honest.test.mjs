/**
 * HONEST tests for the WyrdForge Foundry VTT module (E1).
 *
 * These tests load the SHIPPED file `../scripts/wyrdforge.js` verbatim
 * (read from disk, evaluated as an ES module in a vm context with the
 * Foundry host globals stubbed) and exercise its real exported
 * functions. Nothing is copied or re-implemented here: if the shipped
 * file changes behaviour, these tests see the change.
 *
 * The older `wyrdforge.test.js` in this directory inlines copies of
 * the functions — it tests a copy, not the shipped code (see
 * ../TESTING.md). This file is the honest harness.
 *
 * Run:  node --experimental-vm-modules --test honest.test.mjs
 */
"use strict";

import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SHIPPED = path.join(here, "..", "scripts", "wyrdforge.js");

// Objects returned from the vm realm carry that realm's prototypes;
// normalise through JSON before strict deep comparison.
function plain(v) { return v === undefined ? v : JSON.parse(JSON.stringify(v)); }
function deepEq(actual, expected) { assert.deepEqual(plain(actual), plain(expected)); }

async function loadShipped() {
  const source = fs.readFileSync(SHIPPED, "utf8");
  const fetchCalls = [];
  let fetchImpl = async () => ({
    ok: true,
    status: 200,
    json: async () => ({ status: "ok", response: "runic reply" }),
  });
  const context = vm.createContext({
    console,
    AbortSignal,
    fetch: async (url, opts) => {
      fetchCalls.push({ url, opts });
      return fetchImpl(url, opts);
    },
    Hooks: { once: () => {}, on: () => {} },
    game: { settings: { get: () => true, register: () => {} } },
    ui: { notifications: { info: () => {}, warn: () => {}, error: () => {} } },
    ChatMessage: { create: async () => {} },
    document: { createElement: () => ({}) },
  });
  const mod = new vm.SourceTextModule(source, { context, identifier: SHIPPED });
  await mod.link(() => { throw new Error("shipped file has no imports to stub"); });
  await mod.evaluate();
  return {
    ns: mod.namespace,
    fetchCalls,
    setFetch: (fn) => { fetchImpl = fn; },
  };
}

const { ns, fetchCalls, setFetch } = await loadShipped();

test("shipped normalizePersonaId lowercases and underscores", () => {
  assert.equal(ns.normalizePersonaId("Sigrid"), "sigrid");
  assert.equal(ns.normalizePersonaId("Erik Red"), "erik_red");
  assert.equal(ns.normalizePersonaId("npc.archer-1"), "npc_archer_1");
  assert.equal(ns.normalizePersonaId("x".repeat(100)).length, 64);
});

test("shipped parseChatCommand splits persona and query", () => {
  deepEq(ns.parseChatCommand("/wyrd sigrid hello there"),
    { isWyrd: true, personaId: "sigrid", query: "hello there" });
  deepEq(ns.parseChatCommand("/wyrd sigrid"),
    { isWyrd: true, personaId: "sigrid", query: "" });
  deepEq(ns.parseChatCommand("just chatting"),
    { isWyrd: false, personaId: "", query: "" });
});

test("shipped formatContextCard embeds persona and response", () => {
  const html = ns.formatContextCard("sigrid", { response: "line1\nline2" });
  assert.match(html, /sigrid/);
  assert.match(html, /line1<br>line2/);
  assert.match(html, /data-wyrd-context="true"/);
});

test("shipped WyrdClient.query POSTs the real body shape to /query", async () => {
  fetchCalls.length = 0;
  const client = new ns.WyrdClient({ host: "example.org", port: 9999 });
  const out = await client.query("sigrid", "what news?", { locationId: "tavern" });
  assert.equal(out.response, "runic reply");
  assert.equal(fetchCalls.length, 1);
  assert.equal(fetchCalls[0].url, "http://example.org:9999/query");
  const body = JSON.parse(fetchCalls[0].opts.body);
  deepEq(body, {
    persona_id: "sigrid",
    user_input: "what news?",
    use_turn_loop: false,
    location_id: "tavern",
  });
});

test("shipped WyrdClient defaults to localhost:8765 (unversioned alias surface)", async () => {
  fetchCalls.length = 0;
  const client = new ns.WyrdClient();
  await client.health();
  assert.equal(fetchCalls[0].url, "http://localhost:8765/health");
});

test("shipped WyrdClient.pushEvent wraps event_type and payload", async () => {
  fetchCalls.length = 0;
  const client = new ns.WyrdClient({ host: "h", port: 1 });
  await client.pushEvent("fact", { subject_id: "sigrid", key: "name", value: "Sigrid" });
  const body = JSON.parse(fetchCalls[0].opts.body);
  deepEq(body, {
    event_type: "fact",
    payload: { subject_id: "sigrid", key: "name", value: "Sigrid" },
  });
});

test("shipped WyrdClient surfaces HTTP errors as WyrdAPIError", async () => {
  setFetch(async () => ({
    ok: false,
    status: 503,
    json: async () => ({ error: "server down" }),
  }));
  const client = new ns.WyrdClient({ host: "h", port: 1 });
  await assert.rejects(() => client.health(), (err) => {
    assert.equal(err.name, "WyrdAPIError");
    assert.equal(err.status, 503);
    assert.equal(err.message, "server down");
    return true;
  });
  setFetch(async () => ({
    ok: true, status: 200, json: async () => ({ status: "ok" }),
  }));
});

test("shipped getClient builds a client from settings values", () => {
  const settings = {
    get: (mod, key) => ({ host: "wyrd.local", port: 4321 })[key],
  };
  const client = ns.getClient(settings);
  assert.equal(client.baseUrl, "http://wyrd.local:4321");
});

test("shipped registerSettings registers the four module settings", () => {
  const registered = [];
  ns.registerSettings({ register: (mod, key) => registered.push(key) });
  deepEq(registered, ["host", "port", "enabled", "autoSync"]);
});
