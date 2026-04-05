// AvatarRecord.cs — Avatar/NPC data types and WYRD mapping helpers (Phase 12A).

namespace WyrdForge.OpenSim;

/// <summary>
/// Represents an OpenSim/Second Life avatar or NPC, mapped to the WYRD entity model.
/// </summary>
public sealed record AvatarRecord(
    /// <summary>OpenSim agent UUID string.</summary>
    string AgentId,
    /// <summary>Avatar display name (First Last format in SL).</summary>
    string Name,
    /// <summary>Region the avatar is currently in, if known.</summary>
    string? Region = null,
    /// <summary>Primary group tag, if known.</summary>
    string? Group = null,
    /// <summary>Additional key/value facts to sync to WYRD.</summary>
    Dictionary<string, string>? CustomFacts = null
);

/// <summary>
/// Result of a WyrdForge context query for an avatar.
/// </summary>
public sealed record WyrdContextResult(
    bool Success,
    string PersonaId,
    string ContextText,
    string? ErrorMessage = null
);

/// <summary>
/// Result of a WyrdForge avatar sync operation.
/// </summary>
public sealed record WyrdSyncResult(
    bool Success,
    string PersonaId,
    string? ErrorMessage = null
);

/// <summary>
/// Pure helpers for mapping OpenSim avatar records to WYRD personas and facts.
/// </summary>
public static class AvatarMapper
{
    /// <summary>
    /// Normalize an avatar display name to a WYRD persona_id (snake_case, max 64 chars).
    /// Example: "Sigrid Stormborn" → "sigrid_stormborn"
    /// </summary>
    public static string ToPersonaId(string name)
    {
        if (string.IsNullOrEmpty(name)) return string.Empty;

        var sb = new System.Text.StringBuilder(name.Length);
        bool lastUnderscore = false;

        foreach (var c in name.ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(c) || c == '_')
            {
                sb.Append(c);
                lastUnderscore = false;
            }
            else if (!lastUnderscore)
            {
                sb.Append('_');
                lastUnderscore = true;
            }
        }

        var result = sb.ToString().Trim('_');
        return result.Length > 64 ? result[..64] : result;
    }

    /// <summary>
    /// Build the list of WYRD facts to push for an avatar record.
    /// Returns (key, value) tuples. Omits null/empty fields.
    /// </summary>
    public static IReadOnlyList<(string Key, string Value)> ToFacts(AvatarRecord avatar)
    {
        var facts = new List<(string, string)>();

        if (!string.IsNullOrEmpty(avatar.Name))
            facts.Add(("name", avatar.Name));

        if (!string.IsNullOrEmpty(avatar.AgentId))
            facts.Add(("agent_id", avatar.AgentId));

        if (!string.IsNullOrEmpty(avatar.Region))
            facts.Add(("region", avatar.Region!));

        if (!string.IsNullOrEmpty(avatar.Group))
            facts.Add(("group", avatar.Group!));

        if (avatar.CustomFacts is { Count: > 0 })
        {
            foreach (var kvp in avatar.CustomFacts)
            {
                if (!string.IsNullOrEmpty(kvp.Key) && !string.IsNullOrEmpty(kvp.Value))
                    facts.Add((kvp.Key, kvp.Value));
            }
        }

        return facts;
    }
}
