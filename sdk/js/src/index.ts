/**
 * wyrdforge-js — JavaScript/TypeScript SDK for the WYRD Protocol.
 *
 * @example
 * ```ts
 * import { WyrdClient } from "wyrdforge-js";
 *
 * const wyrd = new WyrdClient({ host: "localhost", port: 8765 });
 *
 * // Check the server is up
 * const alive = await wyrd.health();
 *
 * // Query a character
 * const reply = await wyrd.query("sigrid", "What do the runes say?");
 *
 * // Push a world event
 * await wyrd.pushEvent("observation", { title: "Storm", summary: "A storm rolled in." });
 *
 * // Read world state
 * const world = await wyrd.getWorld();
 * console.log(world.formatted_for_llm);
 * ```
 */

export { WyrdClient } from "./client.js";
export type {
  WyrdClientOptions,
  QueryOptions,
  WorldContextPacket,
  EntitySummary,
  LocationResult,
  FactSummary,
  PolicySummary,
  ObservationSummary,
  FactRecord,
  MemoryContent,
  CanonicalFactPayload,
  WyrdEventType,
  WyrdEventPayload,
  ObservationPayload,
  FactPayload,
} from "./types.js";
export { WyrdConnectionError, WyrdAPIError } from "./types.js";
