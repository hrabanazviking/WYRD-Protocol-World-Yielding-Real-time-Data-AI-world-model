/**
 * Tests for WyrdForge RPG Maker MZ/MV plugin (Phase 11B).
 * Pure functions inlined to avoid IIFE/PluginManager dependencies.
 */
"use strict";

// ---------------------------------------------------------------------------
// Inline pure functions under test
// ---------------------------------------------------------------------------

function normalizePersonaId(name) {
  return (name || "").toLowerCase().replace(/[^a-z0-9_]/g, "_").replace(/_+/g, "_").slice(0, 64);
}

function buildQueryBody(personaId, query) {
  return {
    persona_id: personaId,
    user_input: query || "What is the current world state?",
    use_turn_loop: false,
  };
}

function buildObservationBody(title, summary) {
  return { event_type: "observation", payload: { title, summary } };
}

function buildFactBody(personaId, key, value) {
  return { event_type: "fact", payload: { subject_id: personaId, key, value } };
}

function parseMVCommand(command, args) {
  if ((command || "").toLowerCase() !== "wyrdforge") return null;
  const sub = (args[0] || "").toLowerCase();
  return { subcommand: sub, rest: args.slice(1) };
}

function extractActorData(gameActors, actorId) {
  const actor = gameActors?.actor?.(actorId);
  if (!actor) return null;
  return {
    name: typeof actor.name === "function" ? actor.name() : (actor.name ?? ""),
    class: actor.currentClass ? (actor.currentClass()?.name ?? "") : (actor._className ?? ""),
    level: actor.level ?? 1,
  };
}

// ---------------------------------------------------------------------------
// normalizePersonaId
// ---------------------------------------------------------------------------

describe("normalizePersonaId", () => {
  test("lowercases", () => expect(normalizePersonaId("Sigrid")).toBe("sigrid"));
  test("replaces spaces", () => expect(normalizePersonaId("Erik Red")).toBe("erik_red"));
  test("collapses underscores", () => expect(normalizePersonaId("a  b")).toBe("a_b"));
  test("truncates at 64", () => expect(normalizePersonaId("x".repeat(100)).length).toBe(64));
  test("handles null", () => expect(normalizePersonaId(null)).toBe(""));
  test("handles empty", () => expect(normalizePersonaId("")).toBe(""));
  test("handles special chars", () => expect(normalizePersonaId("Björn!")).toMatch(/^bj/));
});

// ---------------------------------------------------------------------------
// buildQueryBody
// ---------------------------------------------------------------------------

describe("buildQueryBody", () => {
  test("sets persona_id", () => {
    expect(buildQueryBody("sigrid", "").persona_id).toBe("sigrid");
  });
  test("uses provided query", () => {
    expect(buildQueryBody("x", "What is happening?").user_input).toBe("What is happening?");
  });
  test("defaults to world state query when empty", () => {
    expect(buildQueryBody("x", "").user_input).toContain("world state");
  });
  test("sets use_turn_loop to false", () => {
    expect(buildQueryBody("x", "hi").use_turn_loop).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// buildObservationBody
// ---------------------------------------------------------------------------

describe("buildObservationBody", () => {
  test("sets event_type to observation", () => {
    expect(buildObservationBody("Storm", "A storm came.").event_type).toBe("observation");
  });
  test("sets title and summary in payload", () => {
    const b = buildObservationBody("Storm", "A storm came.");
    expect(b.payload.title).toBe("Storm");
    expect(b.payload.summary).toBe("A storm came.");
  });
});

// ---------------------------------------------------------------------------
// buildFactBody
// ---------------------------------------------------------------------------

describe("buildFactBody", () => {
  test("sets event_type to fact", () => {
    expect(buildFactBody("sigrid", "role", "seer").event_type).toBe("fact");
  });
  test("sets subject_id, key, value in payload", () => {
    const b = buildFactBody("sigrid", "role", "seer");
    expect(b.payload.subject_id).toBe("sigrid");
    expect(b.payload.key).toBe("role");
    expect(b.payload.value).toBe("seer");
  });
});

// ---------------------------------------------------------------------------
// parseMVCommand
// ---------------------------------------------------------------------------

describe("parseMVCommand", () => {
  test("returns null for non-wyrdforge command", () => {
    expect(parseMVCommand("SomeOther", ["x"])).toBeNull();
  });
  test("parses query subcommand", () => {
    const r = parseMVCommand("WyrdForge", ["query", "1", "5", "What happened?"]);
    expect(r.subcommand).toBe("query");
    expect(r.rest).toEqual(["1", "5", "What happened?"]);
  });
  test("parses sync subcommand", () => {
    const r = parseMVCommand("WyrdForge", ["sync", "2"]);
    expect(r.subcommand).toBe("sync");
    expect(r.rest).toEqual(["2"]);
  });
  test("parses observe subcommand", () => {
    const r = parseMVCommand("WyrdForge", ["observe", "Storm", "A storm came"]);
    expect(r.subcommand).toBe("observe");
    expect(r.rest).toEqual(["Storm", "A storm came"]);
  });
  test("case insensitive command", () => {
    expect(parseMVCommand("WYRDFORGE", ["query"])).not.toBeNull();
    expect(parseMVCommand("wyrdforge", ["query"])).not.toBeNull();
  });
  test("handles empty args", () => {
    const r = parseMVCommand("WyrdForge", []);
    expect(r.subcommand).toBe("");
  });
  test("returns null for null command", () => {
    expect(parseMVCommand(null, [])).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// extractActorData
// ---------------------------------------------------------------------------

describe("extractActorData", () => {
  test("returns null when actor not found", () => {
    const ga = { actor: () => null };
    expect(extractActorData(ga, 1)).toBeNull();
  });

  test("extracts name as string property", () => {
    const ga = { actor: (id) => id === 1 ? { name: "Sigrid", level: 5, _className: "Warrior" } : null };
    expect(extractActorData(ga, 1).name).toBe("Sigrid");
  });

  test("extracts name from function property", () => {
    const ga = { actor: () => ({ name: () => "Gunnar", level: 3, _className: "Fighter" }) };
    expect(extractActorData(ga, 1).name).toBe("Gunnar");
  });

  test("extracts level", () => {
    const ga = { actor: () => ({ name: "x", level: 7 }) };
    expect(extractActorData(ga, 1).level).toBe(7);
  });

  test("defaults level to 1 when missing", () => {
    const ga = { actor: () => ({ name: "x" }) };
    expect(extractActorData(ga, 1).level).toBe(1);
  });

  test("extracts class from currentClass()", () => {
    const ga = { actor: () => ({ name: "x", level: 1, currentClass: () => ({ name: "Mage" }) }) };
    expect(extractActorData(ga, 1).class).toBe("Mage");
  });

  test("extracts class from _className fallback", () => {
    const ga = { actor: () => ({ name: "x", level: 1, _className: "Rogue" }) };
    expect(extractActorData(ga, 1).class).toBe("Rogue");
  });

  test("handles null gameActors", () => {
    expect(extractActorData(null, 1)).toBeNull();
  });

  test("handles gameActors with no actor() method", () => {
    expect(extractActorData({}, 1)).toBeNull();
  });
});
