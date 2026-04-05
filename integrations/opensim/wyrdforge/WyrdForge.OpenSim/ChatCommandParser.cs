// ChatCommandParser.cs — OpenSim/SL chat command parser for WyrdForge (Phase 12A).

namespace WyrdForge.OpenSim;

public enum ChatCommandType
{
    None,
    Query,   // /wyrd <persona_id> [query text]
    Sync,    // /wyrd-sync <avatar_name>
    Health,  // /wyrd-health
}

/// <summary>Parsed result of a WyrdForge chat command.</summary>
public sealed record ChatCommandResult(
    ChatCommandType Type,
    string PersonaId,
    string Query
);

/// <summary>
/// Parser for WyrdForge chat commands in OpenSim/Second Life.
///
/// Supported commands (typed in-world local chat):
///   /wyrd &lt;persona_id&gt; [query]   — query WYRD world context for a persona
///   /wyrd-sync &lt;avatar_name&gt;     — register/sync an avatar to WYRD
///   /wyrd-health                  — check WyrdHTTPServer connectivity
///
/// Wire into OpenSim via:
///   scene.EventManager.OnChatFromClient += OnChatFromClient;
///   scene.EventManager.OnChatBroadcast  += OnChatFromClient;
/// </summary>
public static class ChatCommandParser
{
    private const string CmdWyrd   = "/wyrd";
    private const string CmdSync   = "/wyrd-sync";
    private const string CmdHealth = "/wyrd-health";

    /// <summary>Parse a raw in-world chat message. Returns None if not a WYRD command.</summary>
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
