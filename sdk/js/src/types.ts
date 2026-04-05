/**
 * TypeScript types mirroring the WYRD Protocol Python models.
 * These reflect the JSON shape returned by WyrdHTTPServer endpoints.
 */

// ---------------------------------------------------------------------------
// World context
// ---------------------------------------------------------------------------

export interface EntitySummary {
  entity_id: string;
  name: string | null;
  description: string | null;
  status: string | null;
  tags: string[];
  location_id: string | null;
}

export interface LocationResult {
  entity_id: string;
  location_id: string | null;
  location_name: string | null;
  zone_id: string | null;
  region_id: string | null;
  path: string[];
}

export interface FactSummary {
  fact_key: string;
  fact_value: string;
  confidence: number;
  domain: string;
}

export interface PolicySummary {
  policy_key: string;
  rule_text: string;
  applies_to_domains: string[];
}

export interface ObservationSummary {
  title: string;
  summary: string;
  salience: number;
}

export interface WorldContextPacket {
  query_timestamp: string;
  world_id: string | null;
  focus_entities: EntitySummary[];
  location_context: LocationResult | null;
  present_entities: EntitySummary[];
  canonical_facts: Record<string, FactSummary[]>;
  active_policies: PolicySummary[];
  recent_observations: ObservationSummary[];
  open_contradiction_count: number;
  formatted_for_llm: string;
}

// ---------------------------------------------------------------------------
// Memory / facts
// ---------------------------------------------------------------------------

export interface CanonicalFactPayload {
  fact_subject_id: string;
  fact_key: string;
  fact_value: string;
  value_type: string;
  domain: string;
}

export interface MemoryContent {
  title: string;
  structured_payload: CanonicalFactPayload;
}

export interface FactRecord {
  record_id: string;
  record_type: string;
  content: MemoryContent;
}

// ---------------------------------------------------------------------------
// Query options
// ---------------------------------------------------------------------------

export interface QueryOptions {
  /** Override location for world context. */
  locationId?: string;
  /** Bond edge ID for relationship context. */
  bondId?: string;
  /**
   * When true (default), uses the full TurnLoop — writes to memory and
   * maintains conversation history.  Set false for context-only output
   * without LLM generation.
   */
  useTurnLoop?: boolean;
}

// ---------------------------------------------------------------------------
// Event types
// ---------------------------------------------------------------------------

export interface ObservationPayload {
  title: string;
  summary: string;
}

export interface FactPayload {
  subject_id: string;
  key: string;
  value: string;
  confidence?: number;
  domain?: string;
}

export type WyrdEventType = "observation" | "fact";
export type WyrdEventPayload = ObservationPayload | FactPayload;

// ---------------------------------------------------------------------------
// Client config
// ---------------------------------------------------------------------------

export interface WyrdClientOptions {
  /** Hostname of the WyrdHTTPServer. Default: "localhost" */
  host?: string;
  /** Port of the WyrdHTTPServer. Default: 8765 */
  port?: number;
  /** Request timeout in milliseconds. Default: 10000 */
  timeoutMs?: number;
}

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

export class WyrdConnectionError extends Error {
  constructor(message: string, public readonly cause?: unknown) {
    super(message);
    this.name = "WyrdConnectionError";
  }
}

export class WyrdAPIError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: unknown
  ) {
    super(message);
    this.name = "WyrdAPIError";
  }
}
