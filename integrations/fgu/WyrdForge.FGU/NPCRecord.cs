namespace WyrdForge.FGU;

/// <summary>
/// Represents an NPC record as read from a Fantasy Grounds Unity campaign database.
/// Maps to the WYRD persona/entity model.
/// </summary>
public sealed record NPCRecord(
    string Id,
    string Name,
    string? Race,
    string? Class,
    string? Description,
    string? Location
);

/// <summary>
/// Pure helpers for mapping FGU NPC records to WYRD personas.
/// </summary>
public static class NPCMapper
{
    /// <summary>
    /// Normalize an FGU NPC name to a WYRD persona_id.
    /// Lowercases, replaces non-alphanumeric chars with underscores, collapses, truncates.
    /// </summary>
    public static string ToPersonaId(string name)
    {
        if (string.IsNullOrEmpty(name)) return string.Empty;

        var chars = name.ToLowerInvariant().ToCharArray();
        var sb = new System.Text.StringBuilder(chars.Length);
        bool lastUnderscore = false;
        foreach (var c in chars)
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
    /// Build the list of WYRD fact payloads to push for an NPC record.
    /// Each tuple is (subject_id, key, value).
    /// </summary>
    public static IReadOnlyList<(string Key, string Value)> ToFacts(NPCRecord npc)
    {
        var facts = new List<(string, string)>();
        if (!string.IsNullOrEmpty(npc.Name))      facts.Add(("name", npc.Name));
        if (!string.IsNullOrEmpty(npc.Race))       facts.Add(("race", npc.Race!));
        if (!string.IsNullOrEmpty(npc.Class))      facts.Add(("class", npc.Class!));
        if (!string.IsNullOrEmpty(npc.Description)) facts.Add(("description", npc.Description!));
        if (!string.IsNullOrEmpty(npc.Location))   facts.Add(("location", npc.Location!));
        return facts;
    }
}
