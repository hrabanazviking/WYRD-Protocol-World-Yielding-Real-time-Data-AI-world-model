/**
 * HONEST tests for the WyrdForge Construct 3 addon runtime (E1).
 *
 * Executes the SHIPPED `../c3runtime/instance.js` verbatim as a
 * classic script in a vm context with the Construct 3 runtime global
 * (`globalThis.C3`) stubbed. The shipped file's own test surface —
 * `globalThis.WyrdForgeHelpers` plus the registered Instance class —
 * is then exercised: the real code, not copies. The older
 * `wyrdforge.test.js` inlines copies and tests the copy. The
 * editor-side `plugin.js` files are not executed here (they need the
 * C3 editor SDK); the runtime instance is the shipped logic core.
 *
 * Run:  node --test honest.test.mjs
 */
"use strict";

import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const SHIPPED = path.join(here, "..", "c3runtime", "instance.js");

// Objects returned from the vm realm carry that realm's prototypes;
// normalise through JSON before strict deep comparison.
function plain(v) { return v === undefined ? v : JSON.parse(JSON.stringify(v)); }
function deepEq(actual, expected) { assert.deepEqual(plain(actual), plain(expected)); }

function loadShipped(fetchImpl) {
  const source = fs.readFileSync(SHIPPED, "utf8");
  class SDKInstanceBase {
    constructor(inst) { this._inst = inst; this._runtime = null; }
    Release() {}
    _GetCnds() { return Promise.resolve(null); }
  }
  const fetchCalls = [];
  const context = vm.createContext({
    console,
    setTimeout,
    clearTimeout,
    AbortController,
    fetch: async (url, opts) => {
      fetchCalls.push({ url, opts });
      return fetchImpl(url, opts);
    },
    C3: { Plugins: { WyrdForge: {} }, SDKInstanceBase },
  });
  new vm.Script(source, { filename: SHIPPED }).runInContext(context);
  const get = (expr) => new vm.Script(expr).runInContext(context);
  return {
    helpers: get("globalThis.WyrdForgeHelpers"),
    Instance: get("globalThis.C3.Plugins.WyrdForge.Instance"),
    fetchCalls,
  };
}

const okFetch = async () => ({
  ok: true,
  status: 200,
  json: async () => ({ response: "the hall is warm" }),
});
const { helpers, Instance, fetchCalls } = loadShipped(okFetch);

test("shipped normalizePersonaId strips edge underscores (C3 variant)", () => {
  assert.equal(helpers.normalizePersonaId("Sigrid"), "sigrid");
  assert.equal(helpers.normalizePersonaId("__Erik  Red__"), "erik_red");
  assert.equal(helpers.normalizePersonaId(null), "");
  assert.equal(helpers.normalizePersonaId("x".repeat(100)).length, 64);
});

test("shipped body builders", () => {
  deepEq(helpers.buildQueryBody("sigrid", ""), {
    persona_id: "sigrid",
    user_input: "What is the current world state?",
    use_turn_loop: false,
  });
  deepEq(helpers.buildEventBody("fact", { a: 1 }),
    { event_type: "fact", payload: { a: 1 } });
});

test("shipped parseResponse returns data and throws the shipped errors", async () => {
  const data = await helpers.parseResponse(
    { ok: true, status: 200, json: async () => ({ a: 1 }) });
  deepEq(data, { a: 1 });
  await assert.rejects(
    () => helpers.parseResponse(
      { ok: false, status: 503, json: async () => ({ error: "down" }) }),
    /WyrdForge: HTTP 503 — down/);
  await assert.rejects(
    () => helpers.parseResponse(
      { ok: true, status: 200, json: async () => { throw new Error("bad"); } }),
    /invalid JSON response/);
});

test("shipped Instance honours plugin properties and _Init", () => {
  const inst = new Instance({}, ["myhost", 9999, 5000, true]);
  assert.equal(inst._IsReady(), false);
  inst._Init("localhost", 8765, 8000);
  assert.equal(inst._IsReady(), true);
  deepEq(inst.SaveToJson(), {
    host: "localhost", port: 8765, timeoutMs: 8000,
    enabled: true, initialized: true, lastResponse: "", lastError: "",
  });
});

test("shipped Instance SaveToJson/LoadFromJson round-trips", () => {
  const a = new Instance({}, []);
  a._Init("h", 1, 2);
  const b = new Instance({}, []);
  b.LoadFromJson(a.SaveToJson());
  deepEq(b.SaveToJson(), a.SaveToJson());
});

test("shipped Instance _QueryCharacter posts via the real chain and stores the response", async () => {
  fetchCalls.length = 0;
  const inst = new Instance({}, ["localhost", 8765, 8000, true]);
  inst._Init("example.org", 9999, 8000);
  await inst._QueryCharacter("Erik Red", "news?");
  assert.equal(inst._lastResponse, "the hall is warm");
  assert.equal(inst._lastError, "");
  assert.equal(fetchCalls.length, 1);
  assert.equal(fetchCalls[0].url, "http://example.org:9999/query");
  deepEq(JSON.parse(fetchCalls[0].opts.body), {
    persona_id: "erik_red", user_input: "news?", use_turn_loop: false,
  });
});

test("shipped Instance _QueryCharacter is a no-op before _Init", async () => {
  fetchCalls.length = 0;
  const inst = new Instance({}, ["localhost", 8765, 8000, true]);
  await inst._QueryCharacter("sigrid", "news?");
  assert.equal(fetchCalls.length, 0);
});
