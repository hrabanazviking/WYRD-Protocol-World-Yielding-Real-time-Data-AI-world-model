/**
 * HONEST tests for the WyrdForge Roll20 API script (E1).
 *
 * Loads the SHIPPED `../wyrdforge.js` verbatim as an ES module (its
 * Roll20 entry point is guarded by `typeof on !== "undefined"`, so no
 * host stubs are needed) and exercises the real exported functions.
 * The older `wyrdforge.test.js` inlines copies and tests the copy.
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
  const context = vm.createContext({ console, Buffer });
  const mod = new vm.SourceTextModule(source, { context, identifier: SHIPPED });
  await mod.link(() => { throw new Error("shipped file has no imports to stub"); });
  await mod.evaluate();
  return mod.namespace;
}

const ns = await loadShipped();

test("shipped getConfig creates defaults and returns the same object", () => {
  const state = {};
  const cfg = ns.getConfig(state);
  deepEq(cfg, { host: "localhost", port: 8765, enabled: true });
  assert.equal(ns.getConfig(state), cfg);
});

test("shipped parseCommand handles health, sync, query, and non-commands", () => {
  deepEq(ns.parseCommand("!wyrd-health"),
    { cmd: "health", personaId: "", query: "" });
  deepEq(ns.parseCommand("!wyrd-sync Erik Red"),
    { cmd: "sync", personaId: "Erik Red", query: "" });
  deepEq(ns.parseCommand("!wyrd sigrid what news?"),
    { cmd: "query", personaId: "sigrid", query: "what news?" });
  deepEq(ns.parseCommand("!wyrd sigrid"),
    { cmd: "query", personaId: "sigrid", query: "" });
  deepEq(ns.parseCommand("hello"),
    { cmd: null, personaId: "", query: "" });
});

test("shipped normalizePersonaId matches the shipped (unstripped) behaviour", () => {
  assert.equal(ns.normalizePersonaId("Sigrid"), "sigrid");
  assert.equal(ns.normalizePersonaId("Erik Red"), "erik_red");
  assert.equal(ns.normalizePersonaId(null), "");
  assert.equal(ns.normalizePersonaId("x".repeat(100)).length, 64);
});

test("shipped buildPostOptions JSON-encodes with byte-length header", () => {
  const { options, body } = ns.buildPostOptions("h", 8765, "/query", { a: "ᚹ" });
  assert.equal(options.method, "POST");
  assert.equal(options.path, "/query");
  assert.equal(body, JSON.stringify({ a: "ᚹ" }));
  assert.equal(options.headers["Content-Length"], Buffer.byteLength(body));
});

test("shipped buildGetOptions shape", () => {
  deepEq(ns.buildGetOptions("h", 1, "/health"),
    { hostname: "h", port: 1, path: "/health", method: "GET" });
});

test("shipped formatStatus and formatChatOutput", () => {
  assert.equal(ns.formatStatus("online"), "/w gm [WyrdForge] online");
  const out = ns.formatChatOutput("sigrid", "news");
  assert.match(out, /sigrid/);
  assert.match(out, /news/);
});

test("shipped httpRequest parses JSON and honours the mock http module", async () => {
  const { EventEmitter } = await import("node:events");
  const fakeHttp = {
    request(opts, cb) {
      const req = new EventEmitter();
      req.write = () => {};
      req.end = () => {
        const res = new EventEmitter();
        res.statusCode = 200;
        cb(res);
        res.emit("data", JSON.stringify({ status: "ok" }));
        res.emit("end");
      };
      return req;
    },
  };
  const result = await ns.httpRequest(fakeHttp, { hostname: "h" });
  deepEq(result, { status: 200, data: { status: "ok" } });
});

test("shipped queryWyrd builds the /query payload via the real chain", async () => {
  const { EventEmitter } = await import("node:events");
  let seenBody = "";
  const fakeHttp = {
    request(opts, cb) {
      const req = new EventEmitter();
      req.write = (b) => { seenBody += b; };
      req.end = () => {
        const res = new EventEmitter();
        res.statusCode = 200;
        cb(res);
        res.emit("data", JSON.stringify({ response: "the hall is warm" }));
        res.emit("end");
      };
      return req;
    },
  };
  const text = await ns.queryWyrd(fakeHttp, { host: "h", port: 8765 }, "sigrid", "");
  assert.equal(text, "the hall is warm");
  deepEq(JSON.parse(seenBody), {
    persona_id: "sigrid",
    user_input: "What is the current state of the world?",
    use_turn_loop: false,
  });
});

test("shipped checkHealth reads data.status", async () => {
  const { EventEmitter } = await import("node:events");
  const fakeHttp = {
    request(opts, cb) {
      const req = new EventEmitter();
      req.write = () => {};
      req.end = () => {
        const res = new EventEmitter();
        res.statusCode = 200;
        cb(res);
        res.emit("data", JSON.stringify({ status: "ok" }));
        res.emit("end");
      };
      return req;
    },
  };
  assert.equal(await ns.checkHealth(fakeHttp, { host: "h", port: 1 }), true);
});
