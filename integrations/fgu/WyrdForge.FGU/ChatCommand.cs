namespace WyrdForge.FGU;

/// <summary>
/// Parsed result of a WyrdForge FGU chat command.
/// </summary>
public sealed record ChatCommandResult(
    ChatCommandType Type,
    string PersonaId,
    string Query
);

public enum ChatCommandType
{
    None,
    Query,
    Sync,
    Health,
}

/// <summary>
/// Parser for WyrdForge chat commands typed in Fantasy Grounds Unity.
///
/// Supported commands:
///   /wyrd &lt;persona_id&gt; [query]  — query WYRD world context
///   /wyrd-sync &lt;actor_name&gt;     — register actor as WYRD entity
///   /wyrd-health                 — check server connectivity
/// </summary>
public static class ChatCommandParser
{
    private const string CmdWyrd = "/wyrd";
    private const string CmdSync = "/wyrd-sync";
    private const string CmdHealth = "/wyrd-health";

    /// <summary>Parse a raw FGU chat message string.</summary>
    public static ChatCommandResult Parse(string? message)
    {
        var trimmed = message?.Trim() ?? string.Empty;

        if (trimmed.Equals(CmdHealth, StringComparison.OrdinalIgnoreCase))
            return new(ChatCommandType.Health, string.Empty, string.Empty);

        if (trimmed.StartsWith(CmdSync, StringComparison.OrdinalIgnoreCase))
        {
            var rest = trimmed[CmdSync.Length..].Trim();
            return new(ChatCommandType.Sync, rest, string.Empty);
        }

        if (trimmed.StartsWith(CmdWyrd, StringComparison.OrdinalIgnoreCase))
        {
            var rest = trimmed[CmdWyrd.Length..].Trim();
            var spaceIdx = rest.IndexOf(' ');
            if (spaceIdx < 0)
                return new(ChatCommandType.Query, rest, string.Empty);
            return new(
                ChatCommandType.Query,
                rest[..spaceIdx],
                rest[(spaceIdx + 1)..].Trim()
            );
        }

        return new(ChatCommandType.None, string.Empty, string.Empty);
    }
}
