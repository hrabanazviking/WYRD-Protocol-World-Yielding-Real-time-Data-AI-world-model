// WyrdForge.Client — C# models mirroring the WYRD Protocol Python types.
// All types use System.Text.Json for serialization.

using System.Text.Json.Serialization;

namespace WyrdForge.Client;

// ---------------------------------------------------------------------------
// World context
// ---------------------------------------------------------------------------

public record EntitySummary(
    [property: JsonPropertyName("entity_id")] string EntityId,
    [property: JsonPropertyName("name")] string? Name,
    [property: JsonPropertyName("description")] string? Description,
    [property: JsonPropertyName("status")] string? Status,
    [property: JsonPropertyName("tags")] List<string> Tags,
    [property: JsonPropertyName("location_id")] string? LocationId
);

public record LocationResult(
    [property: JsonPropertyName("entity_id")] string EntityId,
    [property: JsonPropertyName("location_id")] string? LocationId,
    [property: JsonPropertyName("location_name")] string? LocationName,
    [property: JsonPropertyName("zone_id")] string? ZoneId,
    [property: JsonPropertyName("region_id")] string? RegionId,
    [property: JsonPropertyName("path")] List<string> Path
);

public record FactSummary(
    [property: JsonPropertyName("fact_key")] string FactKey,
    [property: JsonPropertyName("fact_value")] string FactValue,
    [property: JsonPropertyName("confidence")] double Confidence,
    [property: JsonPropertyName("domain")] string Domain
);

public record PolicySummary(
    [property: JsonPropertyName("policy_key")] string PolicyKey,
    [property: JsonPropertyName("rule_text")] string RuleText,
    [property: JsonPropertyName("applies_to_domains")] List<string> AppliesToDomains
);

public record ObservationSummary(
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("summary")] string Summary,
    [property: JsonPropertyName("salience")] double Salience
);

public record WorldContextPacket(
    [property: JsonPropertyName("query_timestamp")] string QueryTimestamp,
    [property: JsonPropertyName("world_id")] string? WorldId,
    [property: JsonPropertyName("focus_entities")] List<EntitySummary> FocusEntities,
    [property: JsonPropertyName("location_context")] LocationResult? LocationContext,
    [property: JsonPropertyName("present_entities")] List<EntitySummary> PresentEntities,
    [property: JsonPropertyName("canonical_facts")] Dictionary<string, List<FactSummary>> CanonicalFacts,
    [property: JsonPropertyName("active_policies")] List<PolicySummary> ActivePolicies,
    [property: JsonPropertyName("recent_observations")] List<ObservationSummary> RecentObservations,
    [property: JsonPropertyName("open_contradiction_count")] int OpenContradictionCount,
    [property: JsonPropertyName("formatted_for_llm")] string FormattedForLlm
);

// ---------------------------------------------------------------------------
// Facts
// ---------------------------------------------------------------------------

public record CanonicalFactPayload(
    [property: JsonPropertyName("fact_subject_id")] string FactSubjectId,
    [property: JsonPropertyName("fact_key")] string FactKey,
    [property: JsonPropertyName("fact_value")] string FactValue,
    [property: JsonPropertyName("value_type")] string ValueType,
    [property: JsonPropertyName("domain")] string Domain
);

public record MemoryContent(
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("structured_payload")] CanonicalFactPayload StructuredPayload
);

public record FactRecord(
    [property: JsonPropertyName("record_id")] string RecordId,
    [property: JsonPropertyName("record_type")] string RecordType,
    [property: JsonPropertyName("content")] MemoryContent Content
);

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

public record ObservationEvent(
    [property: JsonPropertyName("title")] string Title,
    [property: JsonPropertyName("summary")] string Summary
);

public record FactEvent(
    [property: JsonPropertyName("subject_id")] string SubjectId,
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("value")] string Value,
    [property: JsonPropertyName("confidence")] double? Confidence = null,
    [property: JsonPropertyName("domain")] string? Domain = null
);

// ---------------------------------------------------------------------------
// Exceptions
// ---------------------------------------------------------------------------

/// <summary>Thrown when the WYRD server cannot be reached.</summary>
public class WyrdConnectionException(string message, Exception? inner = null)
    : Exception(message, inner);

/// <summary>Thrown when the WYRD server returns a non-success HTTP status.</summary>
public class WyrdApiException(string message, int statusCode, string? body = null)
    : Exception(message)
{
    public int StatusCode { get; } = statusCode;
    public string? Body { get; } = body;
}
