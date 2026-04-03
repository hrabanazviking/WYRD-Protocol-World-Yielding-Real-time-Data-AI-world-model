/**
 * WyrdClient — HTTP client for the WYRD Protocol WyrdHTTPServer.
 *
 * Usage:
 * ```ts
 * import { WyrdClient } from "wyrdforge-js";
 *
 * const wyrd = new WyrdClient({ host: "localhost", port: 8765 });
 * const reply = await wyrd.query("sigrid", "What do the runes say?");
 * console.log(reply);
 * ```
 */

import {
  FactRecord,
  QueryOptions,
  WyrdAPIError,
  WyrdClientOptions,
  WyrdConnectionError,
  WyrdEventPayload,
  WyrdEventType,
  WorldContextPacket,
} from "./types.js";

const DEFAULT_HOST = "localhost";
const DEFAULT_PORT = 8765;
const DEFAULT_TIMEOUT_MS = 10_000;

export class WyrdClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  /**
   * Create a WyrdClient.
   *
   * @param options - Connection options. All fields optional.
   */
  constructor(options: WyrdClientOptions = {}) {
    const host = options.host ?? DEFAULT_HOST;
    const port = options.port ?? DEFAULT_PORT;
    this.baseUrl = `http://${host}:${port}`;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  /**
   * Query a character and return their response string.
   *
   * When `useTurnLoop` is true (default), the exchange is written to WYRD
   * memory and conversation history is maintained server-side per persona.
   * Set `useTurnLoop: false` to get a pure context render without LLM
   * generation — useful for testing or when Ollama is unavailable.
   *
   * @param personaId  - ID of the active character/persona.
   * @param userInput  - Player or user message text.
   * @param options    - Optional overrides (locationId, bondId, useTurnLoop).
   * @returns The character's response as a plain string.
   */
  async query(
    personaId: string,
    userInput: string,
    options: QueryOptions = {}
  ): Promise<string> {
    const body: Record<string, unknown> = {
      persona_id: personaId,
      user_input: userInput,
      use_turn_loop: options.useTurnLoop ?? true,
    };
    if (options.locationId !== undefined) body.location_id = options.locationId;
    if (options.bondId !== undefined) body.bond_id = options.bondId;

    const data = await this._post<{ response: string }>("/query", body);
    return data.response;
  }

  /**
   * Fetch the current WorldContextPacket from the server.
   *
   * @returns The live world state as a WorldContextPacket.
   */
  async getWorld(): Promise<WorldContextPacket> {
    return this._get<WorldContextPacket>("/world");
  }

  /**
   * Fetch canonical facts for a specific entity.
   *
   * @param entityId - Entity to query facts for.
   * @returns Array of FactRecord objects.
   */
  async getFacts(entityId: string): Promise<FactRecord[]> {
    const encoded = encodeURIComponent(entityId);
    const data = await this._get<{ facts: FactRecord[] }>(`/facts?entity_id=${encoded}`);
    return data.facts;
  }

  /**
   * Push a world event to the WYRD server.
   *
   * Supported event types:
   * - `"observation"` — payload must have `title` and `summary`.
   * - `"fact"` — payload must have `subject_id`, `key`, `value`,
   *   and optionally `confidence` and `domain`.
   *
   * @param eventType - Type of event.
   * @param payload   - Event data matching the type.
   * @returns true if the server accepted the event.
   */
  async pushEvent(
    eventType: WyrdEventType,
    payload: WyrdEventPayload
  ): Promise<boolean> {
    const data = await this._post<{ ok: boolean }>("/event", {
      event_type: eventType,
      payload,
    });
    return data.ok === true;
  }

  /**
   * Check whether the WYRD server is reachable and healthy.
   *
   * @returns true if the server responds with status "ok".
   */
  async health(): Promise<boolean> {
    try {
      const data = await this._get<{ status: string }>("/health");
      return data.status === "ok";
    } catch {
      return false;
    }
  }

  // --------------------------------------------------------------------------
  // Internal helpers
  // --------------------------------------------------------------------------

  private async _get<T>(path: string): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let response: Response;
    try {
      response = await fetch(url, { signal: AbortSignal.timeout(this.timeoutMs) });
    } catch (err) {
      throw new WyrdConnectionError(
        `WYRD server unreachable at ${url}`,
        err
      );
    }
    return this._parseResponse<T>(response, url);
  }

  private async _post<T>(path: string, body: unknown): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      throw new WyrdConnectionError(
        `WYRD server unreachable at ${url}`,
        err
      );
    }
    return this._parseResponse<T>(response, url);
  }

  private async _parseResponse<T>(response: Response, url: string): Promise<T> {
    let json: unknown;
    try {
      json = await response.json();
    } catch {
      throw new WyrdAPIError(
        `WYRD server returned non-JSON response from ${url}`,
        response.status,
        null
      );
    }
    if (!response.ok) {
      const message =
        typeof json === "object" && json !== null && "error" in json
          ? String((json as Record<string, unknown>).error)
          : `HTTP ${response.status}`;
      throw new WyrdAPIError(message, response.status, json);
    }
    return json as T;
  }
}
