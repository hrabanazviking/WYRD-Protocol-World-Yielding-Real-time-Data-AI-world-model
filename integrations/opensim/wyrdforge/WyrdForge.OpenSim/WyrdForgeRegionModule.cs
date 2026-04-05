// WyrdForgeRegionModule.cs — WYRD Protocol OpenSim region module (Phase 12A).
//
// This class implements the OpenSim IRegionModuleBase pattern.
// It wraps WyrdForge.Client to provide:
//   - Avatar sync on region entry (OnMakeRootAgent)
//   - Context queries via in-world chat commands (OnChatFromClient)
//   - Admin console commands
//   - Health monitoring
//
// OPENSIM DEPLOYMENT
// ------------------
// 1. Build this project and copy WyrdForge.OpenSim.dll + WyrdForge.Client.dll
//    to your OpenSim bin/ directory.
// 2. Add to OpenSim.ini [Modules] section:
//    WyrdForgeModule = true
// 3. In [WyrdForge] section set Host and Port to your WyrdHTTPServer address.
// 4. The module auto-discovers via OpenSim's IRegionModuleBase reflection loader.
//
// IRegionModuleBase WIRING (add when referencing OpenSim.Framework.dll):
//   public class WyrdForgeRegionModule : IRegionModuleBase { ... }
//   and wire the events shown in the comments below.

using WyrdForge.Client;

namespace WyrdForge.OpenSim;

/// <summary>Configuration for WyrdForgeRegionModule.</summary>
public sealed record OpenSimBridgeOptions(
    string Host = "localhost",
    int Port = 8765,
    int TimeoutMs = 10000,
    /// <summary>Auto-sync avatars to WYRD when they enter the region.</summary>
    bool AutoSyncAvatars = true,
    /// <summary>Respond to /wyrd chat commands in local chat (channel 0).</summary>
    bool EnableChatCommands = true
);

/// <summary>
/// WYRD Protocol region module for OpenSim / Second Life.
///
/// Provides avatar sync, context queries, and chat command dispatch.
/// All network calls are async to avoid blocking the OpenSim thread pool.
/// </summary>
public sealed class WyrdForgeRegionModule : IDisposable
{
    private readonly WyrdClient _client;
    private readonly OpenSimBridgeOptions _options;

    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------

    public WyrdForgeRegionModule(OpenSimBridgeOptions? options = null)
    {
        _options = options ?? new OpenSimBridgeOptions();
        _client = new WyrdClient(new WyrdClientOptions
        {
            Host    = _options.Host,
            Port    = _options.Port,
            Timeout = TimeSpan.FromMilliseconds(_options.TimeoutMs),
        });
    }

    // -------------------------------------------------------------------------
    // IRegionModuleBase lifecycle (wire these when referencing OpenSim.Framework)
    // -------------------------------------------------------------------------

    /// <summary>
    /// Module name — returned to OpenSim's module loader.
    /// Maps to: public string Name => "WyrdForge";
    /// </summary>
    public string Name => "WyrdForge";

    /// <summary>
    /// Called when the module is added to a region.
    /// Wire OpenSim events here, for example:
    ///
    ///   scene.EventManager.OnMakeRootAgent  += OnAvatarEnterRegion;
    ///   scene.EventManager.OnClientClosed   += OnAvatarLeaveRegion;
    ///   scene.EventManager.OnChatFromClient += OnChatFromClient;
    ///   scene.EventManager.OnChatBroadcast  += OnChatFromClient;
    /// </summary>
    public void AddRegion(/* Scene scene */ object scene)
    {
        // Wire events here when OpenSim.Framework is referenced.
        // Example:
        //   if (scene is Scene s)
        //   {
        //       s.EventManager.OnMakeRootAgent  += OnAvatarEnterRegion;
        //       s.EventManager.OnClientClosed   += OnAvatarLeaveRegion;
        //       s.EventManager.OnChatFromClient += OnChatFromClient;
        //   }
    }

    /// <summary>
    /// Called when the module is removed from a region.
    /// Unwire all events here.
    /// </summary>
    public void RemoveRegion(/* Scene scene */ object scene)
    {
        // Unwire events here when OpenSim.Framework is referenced.
    }

    // -------------------------------------------------------------------------
    // Core operations
    // -------------------------------------------------------------------------

    /// <summary>Check that WyrdHTTPServer is reachable.</summary>
    public async Task<bool> IsHealthyAsync(CancellationToken ct = default)
    {
        try { return await _client.HealthAsync(ct); }
        catch { return false; }
    }

    /// <summary>
    /// Query WYRD world context for a persona.
    /// Called from chat command handler or avatar entry event.
    /// </summary>
    public async Task<WyrdContextResult> QueryContextAsync(
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
            return new WyrdContextResult(true, personaId, response);
        }
        catch (Exception ex)
        {
            return new WyrdContextResult(false, personaId, string.Empty, ex.Message);
        }
    }

    /// <summary>
    /// Sync an avatar record to WYRD as a set of entity facts.
    /// Call from OnMakeRootAgent or on demand.
    /// </summary>
    public async Task<WyrdSyncResult> SyncAvatarAsync(
        AvatarRecord avatar,
        CancellationToken ct = default)
    {
        var personaId = AvatarMapper.ToPersonaId(avatar.Name);
        if (string.IsNullOrEmpty(personaId))
            return new WyrdSyncResult(false, personaId, "Empty persona_id after normalization.");

        try
        {
            foreach (var (key, value) in AvatarMapper.ToFacts(avatar))
                await _client.PushFactAsync(personaId, key, value, ct: ct);

            return new WyrdSyncResult(true, personaId);
        }
        catch (Exception ex)
        {
            return new WyrdSyncResult(false, personaId, ex.Message);
        }
    }

    /// <summary>
    /// Dispatch a parsed in-world chat message.
    /// Returns a reply string to say back to the region, or null if not a WYRD command.
    ///
    /// Wire to OpenSim's OnChatFromClient event:
    ///   async void OnChatFromClient(object sender, OSChatMessage chat)
    ///   {
    ///       var reply = await DispatchChatCommandAsync(chat.Message);
    ///       if (reply != null) scene.SimChat(reply, ChatTypeEnum.Say, 0, ...);
    ///   }
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
                    ? "[WyrdForge] Server online."
                    : "[WyrdForge] Server unreachable.",

            ChatCommandType.Sync when !string.IsNullOrEmpty(cmd.PersonaId) =>
                await SyncByNameAsync(cmd.PersonaId, ct),

            ChatCommandType.Sync =>
                "[WyrdForge] Usage: /wyrd-sync <avatar_name>",

            ChatCommandType.Query when !string.IsNullOrEmpty(cmd.PersonaId) =>
                await QueryAndFormatAsync(cmd.PersonaId, cmd.Query, ct),

            ChatCommandType.Query =>
                "[WyrdForge] Usage: /wyrd <persona_id> [query]",

            _ => null,
        };
    }

    // -------------------------------------------------------------------------
    // Private helpers
    // -------------------------------------------------------------------------

    private async Task<string> SyncByNameAsync(string name, CancellationToken ct)
    {
        var avatar = new AvatarRecord(
            AgentId: AvatarMapper.ToPersonaId(name),
            Name: name
        );
        var result = await SyncAvatarAsync(avatar, ct);
        return result.Success
            ? $"[WyrdForge] Synced '{result.PersonaId}' to WYRD."
            : $"[WyrdForge] Sync failed: {result.ErrorMessage}";
    }

    private async Task<string> QueryAndFormatAsync(
        string personaId, string query, CancellationToken ct)
    {
        var result = await QueryContextAsync(personaId, query, ct);
        return result.Success
            ? $"[WyrdForge — {result.PersonaId}]\n{result.ContextText}"
            : $"[WyrdForge] Query failed: {result.ErrorMessage}";
    }

    // -------------------------------------------------------------------------
    // IDisposable
    // -------------------------------------------------------------------------

    public void Dispose() => _client.Dispose();
}
