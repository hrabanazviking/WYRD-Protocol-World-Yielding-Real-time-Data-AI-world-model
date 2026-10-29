/**
 * HONEST tests for the WyrdForge RPG Maker MZ/MV plugin (E1).
 *
 * Executes the SHIPPED `../WyrdForge.js` verbatim as a classic script
 * in a vm context with the RPG Maker host globals stubbed
 * (PluginManager, Game_Interpreter, XMLHttpRequest, window). The
 * plugin's own public namespace (`window.WyrdForge`) is then
 * exercised — the real functions, not copies. The older
 * `wyrdforge.test.js` inlines copies and tests the copy.
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
const SHIPPED = path.join(here, "..", "WyrdForge.js");

// Objects returned from the vm realm carry that realm's prototypes;
// normalise through JSON before strict deep comparison.
function plain(v) { return v === undefined ? v : JSON.parse(JSON.stringify(v)); }
function deepEq(actual, expected) { assert.deepEqual(plain(actual), plain(expected)); }

function loadShipped() {
  const source = fs.readFileSync(SHIPPED, "utf8");
  const registered = [];
  const windowObj = {};
  function GameInterpreter() {}
  GameInterpreter.prototype.pluginCommand = function () {};
  const context = vm.createContext({
    console,
    window: windowObj,
    PluginManager: {
      parameters: () => ({ host: "example.org", port: "9999", timeoutMs: "5000", enabled: "true" }),
      registerCommand: (plugin, name) => registered.push(`${plugin}:${name}`),
    },
    Game_Interpreter: GameInterpreter,
    XMLHttpRequest: class {},
  });
  new vm.Script(source, { filename: SHIPPED }).runInContext(context);
  return { WF: windowObj.WyrdForge, registered, GameInterpreter };
}

const { WF, registered, GameInterpreter } = loadShipped();

test("shipped plugin registers its three MZ commands at load", () => {
  deepEq(registered,
    ["WyrdForge:QueryContext", "WyrdForge:SyncActor", "WyrdForge:WriteObservation"]);
});

test("shipped plugin patches Game_Interpreter.pluginCommand for MV", () => {
  assert.equal(typeof GameInterpreter.prototype.pluginCommand, "function");
});

test("shipped normalizePersonaId", () => {
  assert.equal(WF.normalizePersonaId("Sigrid"), "sigrid");
  assert.equal(WF.normalizePersonaId("Erik Red"), "erik_red");
  assert.equal(WF.normalizePersonaId(null), "");
  assert.equal(WF.normalizePersonaId("x".repeat(100)).length, 64);
});

test("shipped body builders produce the real request shapes", () => {
  deepEq(WF.buildQueryBody("sigrid", ""), {
    persona_id: "sigrid",
    user_input: "What is the current world state?",
    use_turn_loop: false,
  });
  deepEq(WF.buildQueryBody("sigrid", "news?"), {
    persona_id: "sigrid", user_input: "news?", use_turn_loop: false,
  });
  deepEq(WF.buildObservationBody("T", "S"),
    { event_type: "observation", payload: { title: "T", summary: "S" } });
  deepEq(WF.buildFactBody("sigrid", "name", "Sigrid"),
    { event_type: "fact", payload: { subject_id: "sigrid", key: "name", value: "Sigrid" } });
});

test("shipped parseMVCommand", () => {
  deepEq(WF.parseMVCommand("WyrdForge", ["Query", "1"]),
    { subcommand: "query", rest: ["1"] });
  assert.equal(WF.parseMVCommand("OtherPlugin", ["query"]), null);
  deepEq(WF.parseMVCommand("wyrdforge", []), { subcommand: "", rest: [] });
});

test("shipped extractActorData reads function and property shapes", () => {
  const gameActors = {
    actor: (id) => (id === 1
      ? { name: () => "Sigrid", currentClass: () => ({ name: "Seer" }), level: 7 }
      : null),
  };
  deepEq(WF.extractActorData(gameActors, 1),
    { name: "Sigrid", class: "Seer", level: 7 });
  assert.equal(WF.extractActorData(gameActors, 99), null);
});

test("shipped WyrdClient builds its base URL from constructor args", () => {
  const client = new WF.WyrdClient("example.org", 9999, 5000);
  assert.equal(client.baseUrl, "http://example.org:9999");
  assert.equal(client.timeoutMs, 5000);
});
