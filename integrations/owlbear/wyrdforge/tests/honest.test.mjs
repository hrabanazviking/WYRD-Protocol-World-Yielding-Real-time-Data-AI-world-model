/**
 * HONEST tests for the WyrdForge Owlbear Rodeo extension (E1).
 *
 * Loads the SHIPPED `../wyrdforge.js` verbatim as an ES module (its
 * OBR bootstrap is guarded by `typeof OBR !== "undefined"`) and
 * exercises the real exported functions. The older
 * `wyrdforge.test.js` inlines copies and tests the copy.
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
const SHIPPED = path.join(here, "..", "wyrdforge.js");

// Objects returned from the vm realm carry that realm's prototypes;
// normalise through JSON before strict deep comparison.
function plain(v) { return v === undefined ? v : JSON.parse(JSON.stringify(v)); }
function deepEq(actual, expected) { assert.deepEqual(plain(actual), plain(expected)); }

async function loadShipped() {
  const source = fs.readFileSync(SHIPPED, "utf8");
  const fetchCalls = [];
  const context = vm.createContext({
    console,
    AbortSignal,
    fetch: async (url, opts) => {
      fetchCalls.push({ url, opts });
      return { ok: true, status: 200, json: async () => ({ response: "news" }) };
    },
  });
  const mod = new vm.SourceTextModule(source, { context, identifier: SHIPPED });
  await mod.link(() => { throw new Error("shipped file has no imports to stub"); });
  await mod.evaluate();
  return { ns: mod.namespace, fetchCalls };
}

const { ns, fetchCalls } = await loadShipped();

test("shipped normalizePersonaId", () => {
  assert.equal(ns.normalizePersonaId("Erik Red"), "erik_red");
  assert.equal(ns.normalizePersonaId(null), "");
  assert.equal(ns.normalizePersonaId("x".repeat(100)).length, 64);
});

test("shipped config helpers round-trip through room metadata", () => {
  deepEq(ns.getConfigFromMeta({}), { host: "localhost", port: 8765 });
  deepEq(ns.getConfigFromMeta(null), { host: "localhost", port: 8765 });
  const meta = ns.buildConfigMeta("wyrd.local", 9999);
  deepEq(ns.getConfigFromMeta(meta), { host: "wyrd.local", port: 9999 });
});

test("shipped personaIdFromItem prefers metadata persona, then name", () => {
  assert.equal(ns.personaIdFromItem({ metadata: { "wyrdforge.persona_id": "Sigrid" }, name: "Other" }), "sigrid");
  assert.equal(ns.personaIdFromItem({ name: "Big Boss" }), "big_boss");
  assert.equal(ns.personaIdFromItem({}), "");
});

test("shipped formatResponse", () => {
  assert.equal(ns.formatResponse("sigrid", { response: "news" }), "[sigrid]\nnews");
  assert.equal(ns.formatResponse("sigrid", null), "[sigrid]\n");
});

test("shipped panelReducer drives the real state machine", () => {
  let s = ns.initialPanelState();
  deepEq(s, { personaId: "", query: "", output: "", loading: false, error: null });
  s = ns.panelReducer(s, { type: "SET_PERSONA", payload: "sigrid" });
  assert.equal(s.personaId, "sigrid");
  s = ns.panelReducer(s, { type: "QUERY_START" });
  assert.equal(s.loading, true);
  s = ns.panelReducer(s, { type: "QUERY_SUCCESS", payload: "done" });
  deepEq([s.loading, s.output], [false, "done"]);
  s = ns.panelReducer(s, { type: "QUERY_ERROR", payload: "boom" });
  assert.equal(s.error, "boom");
  s = ns.panelReducer(s, { type: "CLEAR" });
  deepEq(s, ns.initialPanelState());
  const same = ns.panelReducer(s, { type: "UNKNOWN" });
  assert.equal(same, s);
});

test("shipped renderPanel escapes output and reflects loading", () => {
  const html = ns.renderPanel({ ...ns.initialPanelState(), output: "<b>x</b>", loading: true });
  // Shipped behaviour (pinned as-is): only "<" is escaped.
  assert.match(html, /&lt;b>x&lt;\/b>/);
  assert.match(html, /Loading…/);
});

test("shipped WyrdClient.query POSTs to the unversioned /query with the real body", async () => {
  fetchCalls.length = 0;
  const client = new ns.WyrdClient({ host: "example.org", port: 9999 });
  await client.query("sigrid", "news?", { locationId: "hall" });
  assert.equal(fetchCalls[0].url, "http://example.org:9999/query");
  deepEq(JSON.parse(fetchCalls[0].opts.body), {
    persona_id: "sigrid", user_input: "news?", use_turn_loop: false, location_id: "hall",
  });
});
