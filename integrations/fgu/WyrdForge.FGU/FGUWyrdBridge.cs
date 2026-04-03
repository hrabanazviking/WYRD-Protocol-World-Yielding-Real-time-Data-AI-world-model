using WyrdForge.Client;

namespace WyrdForge.FGU;

/// <summary>
/// Configuration for FGUWyrdBridge.
/// </summary>
public sealed record FGUBridgeOptions(
    string Host = "localhost",
    int Port = 8765,
    int TimeoutMs = 8000
);

/// <summary>
/// Result of a WyrdForge context query from FGU.
/// </summary>
public sealed record FGUContextResult(
    bool Success,
    string PersonaId,
    string ContextText,
    string? ErrorMessage = null
);

/// <summary>
/// Result of a sync operation.
/// </summary>
public sealed record FGUSyncResult(
    bool Success,
    string PersonaId,
    string? ErrorMessage = null
);

/// <summary>
/// WYRD Protocol bridge for Fantasy Grounds Unity.
///
/// Wraps WyrdForge.Client.WyrdClient with FGU-specific helpers:
///   - NPC record sync (name/race/class/description → WYRD facts)
///   - Context query for character sheets
///   - Chat command dispatch
///   - Health check
///
/// FGU extension integration pattern:
///   1. Instantiate FGUWyrdBridge in your extension's OnInit().
///   2. Call SyncNPCAsync() when campaign data loads.
///   3. Call QueryContextAsync() when a character sheet opens.
///   4. Call DispatchChatCommandAsync() in your chat message handler.
/// </summary>
public sealed class FGUWyrdBridge : IDisposable
{
    private readonly WyrdClient _client;

    public FGUWyrdBridge(FGUBridgeOptions? options = null)
    {
        var opts = options ?? new FGUBridgeOptions();
        _client = new WyrdClient(new WyrdClientOptions
        {
            Host = opts.Host,
            Port = opts.Port,
            Timeout = TimeSpan.FromMilliseconds(opts.TimeoutMs),
        });
    }

    /// <summary>Check that WyrdHTTPServer is reachable.</summary>
    public async Task<bool> IsHealthyAsync(CancellationToken ct = default)
    {
        try
        {
            return await _client.HealthAsync(ct);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Query WYRD world context for a persona.
    /// </summary>
    public async Task<FGUContextResult> QueryContextAsync(
        string personaId,
        string query = "",
        CancellationToken ct = default)
    {
        try
        {
            var response = await _client.QueryAsync(
                personaId,
                string.IsNullOrEmpty(query) ? "What is the current world state?" : query,
                new QueryOptions { UseTurnLoop = false },
                ct);

            return new FGUContextResult(true, personaId, response);
        }
        catch (Exception ex)
        {
            return new FGUContextResult(false, personaId, string.Empty, ex.Message);
        }
    }

    /// <summary>
    /// Sync an NPC record to WYRD memory as a set of facts.
    /// </summary>
    public async Task<FGUSyncResult> SyncNPCAsync(
        NPCRecord npc,
        CancellationToken ct = default)
    {
        var personaId = NPCMapper.ToPersonaId(npc.Name);
        if (string.IsNullOrEmpty(personaId))
            return new FGUSyncResult(false, personaId, "Empty persona_id after normalization.");

        var facts = NPCMapper.ToFacts(npc);
        try
        {
            foreach (var (key, value) in facts)
            {
                await _client.PushFactAsync(personaId, key, value, ct: ct);
            }
            return new FGUSyncResult(true, personaId);
        }
        catch (Exception ex)
        {
            return new FGUSyncResult(false, personaId, ex.Message);
        }
    }

    /// <summary>
    /// Dispatch a parsed chat command, returning a reply string for the chat log.
    /// Returns null if the command is not a WYRD command.
    /// </summary>
    public async Task<string?> DispatchChatCommandAsync(
        string rawMessage,
        CancellationToken ct = default)
    {
        var cmd = ChatCommandParser.Parse(rawMessage);

        return cmd.Type switch
        {
            ChatCommandType.Health =>
                await IsHealthyAsync(ct)
                    ? "[WyrdForge] Server is online."
                    : "[WyrdForge] Server unreachable.",

            ChatCommandType.Sync when !string.IsNullOrEmpty(cmd.PersonaId) =>
                await SyncActorByNameAsync(cmd.PersonaId, ct),

            ChatCommandType.Query when !string.IsNullOrEmpty(cmd.PersonaId) =>
                await QueryAndFormatAsync(cmd.PersonaId, cmd.Query, ct),

            ChatCommandType.Query =>
                "[WyrdForge] Usage: /wyrd <persona_id> [query]",

            ChatCommandType.Sync =>
                "[WyrdForge] Usage: /wyrd-sync <actor_name>",

            _ => null,
        };
    }

    private async Task<string> SyncActorByNameAsync(string name, CancellationToken ct)
    {
        var npc = new NPCRecord(
            Id: NPCMapper.ToPersonaId(name),
            Name: name,
            Race: null, Class: null, Description: null, Location: null
        );
        var result = await SyncNPCAsync(npc, ct);
        return result.Success
            ? $"[WyrdForge] Synced '{result.PersonaId}' to WYRD."
            : $"[WyrdForge] Sync failed: {result.ErrorMessage}";
    }

    private async Task<string> QueryAndFormatAsync(string personaId, string query, CancellationToken ct)
    {
        var result = await QueryContextAsync(personaId, query, ct);
        if (!result.Success)
            return $"[WyrdForge] Query failed: {result.ErrorMessage}";
        return $"[WyrdForge — {result.PersonaId}]\n{result.ContextText}";
    }

    public void Dispose() => _client.Dispose();
}
