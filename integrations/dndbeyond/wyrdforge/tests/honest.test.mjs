/**
 * HONEST tests for the WyrdForge D&D Beyond extension core (E1).
 *
 * Loads the SHIPPED `../wyrdforge.js` verbatim as an ES module — the
 * file states it has "No DOM or browser API dependencies" and it is
 * the shared core used by content.js / popup.js / background.js —
 * and exercises its real exported functions. The older
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
      return { ok: true, status: 200, json: async () => ({ status: "ok" }) };
    },
  });
  const mod = new vm.SourceTextModule(source, { context, identifier: SHIPPED });
  await mod.link(() => { throw new Error("shipped file has no imports to stub"); });
  await mod.evaluate();
  return { ns: mod.namespace, fetchCalls };
}

const { ns, fetchCalls } = await loadShipped();

test("shipped classifyDDBUrl", () => {
  assert.equal(ns.classifyDDBUrl("https://www.dndbeyond.com/characters/123"), "character");
  assert.equal(ns.classifyDDBUrl("https://www.dndbeyond.com/monsters/beholder"), "monster");
  assert.equal(ns.classifyDDBUrl("https://www.dndbeyond.com/npcs/x"), "npc");
  assert.equal(ns.classifyDDBUrl("https://example.org/"), "unknown");
});

test("shipped extractDDBId", () => {
  assert.equal(ns.extractDDBId("https://www.dndbeyond.com/characters/123"), "123");
  assert.equal(ns.extractDDBId("https://www.dndbeyond.com/monsters/"), null);
});

test("shipped normalizePersonaId", () => {
  assert.equal(ns.normalizePersonaId("Erik Red"), "erik_red");
  assert.equal(ns.normalizePersonaId(""), "");
  assert.equal(ns.normalizePersonaId(null), "");
});

test("shipped storage config helpers round-trip", () => {
  deepEq(ns.getConfigFromStorage({}),
    { host: "localhost", port: 8765, enabled: true });
  const payload = ns.buildStoragePayload("wyrd.local", 9999, false);
  deepEq(ns.getConfigFromStorage(payload),
    { host: "wyrd.local", port: 9999, enabled: false });
});

test("shipped message builders and validator", () => {
  deepEq(ns.buildQueryMessage("sigrid", "hi"),
    { type: "WYRD_QUERY", personaId: "sigrid", query: "hi" });
  deepEq(ns.buildSyncMessage("sigrid", "Sigrid"),
    { type: "WYRD_SYNC", personaId: "sigrid", name: "Sigrid" });
  deepEq(ns.buildHealthMessage(), { type: "WYRD_HEALTH" });
  assert.equal(ns.isValidMessage(ns.buildHealthMessage()), true);
  assert.equal(ns.isValidMessage({ type: "NOPE" }), false);
  assert.equal(ns.isValidMessage(null), false);
});

test("shipped renderSidebarPanel reflects state and escapes output", () => {
  const html = ns.renderSidebarPanel(
    { personaId: "sigrid", loading: true, output: "<x>", error: null });
  assert.match(html, /sigrid/);
  // Shipped behaviour (pinned as-is): only "<" is escaped.
  assert.match(html, /&lt;x>/);
  assert.match(html, /wyrd-spinner/);
});

test("shipped WyrdClient health/query hit the unversioned surface", async () => {
  fetchCalls.length = 0;
  const client = new ns.WyrdClient({ host: "example.org", port: 9999 });
  await client.health();
  assert.equal(fetchCalls[0].url, "http://example.org:9999/health");
  await client.query("sigrid", "news?");
  assert.equal(fetchCalls[1].url, "http://example.org:9999/query");
  deepEq(JSON.parse(fetchCalls[1].opts.body), {
    persona_id: "sigrid", user_input: "news?", use_turn_loop: false,
  });
});
