// WyrdForgeRegionModule.cs — WYRD Protocol OpenSim bridge core (Phase 12A).
//
// This class is the host-free bridge core. It wraps WyrdForge.Client to
// provide the operations the region module serves:
//   - Avatar sync (SyncAvatarAsync)
//   - Context queries via in-world chat commands (DispatchChatCommandAsync)
//   - Health monitoring (IsHealthyAsync)
//
// It deliberately does NOT implement IRegionModuleBase itself: that
// interface's types (Scene, IConfigSource, ...) live in the OpenSim
// assemblies, and this project must stay compilable and unit-testable
// with nothing but the dotnet SDK.
//
// OPENSIM DEPLOYMENT (E3 — the host now ships)
// --------------------------------------------
// The real region module is WyrdForgeRegionModuleHost in the sibling
// project WyrdForge.OpenSim.RegionModule: it implements
// INonSharedRegionModule / IRegionModuleBase, reads the [WyrdForge]
// section of OpenSim.ini in Initialise, wires this bridge to the
// region's events in AddRegion, and unwires them in RemoveRegion.
// Build THAT project against your OpenSim bin/ directory and deploy
// as its README.md describes.

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
    // Module-shaped surface (the host in WyrdForge.OpenSim.RegionModule
    // exposes the real IRegionModuleBase members; these remain so the
    // bridge core carries the module's name without an OpenSim reference)
    // -------------------------------------------------------------------------

    /// <summary>Module name — the host reports the same name to OpenSim's loader.</summary>
    public string Name => "WyrdForge";

    /// <summary>
    /// Host-free stand-in kept for API compatibility: the REAL AddRegion
    /// (Scene-typed, event-wiring) is WyrdForgeRegionModuleHost.AddRegion
    /// in the deployment project. This overload intentionally does
    /// nothing — there is no Scene to wire without OpenSim.Framework.
    /// </summary>
    public void AddRegion(object scene)
    {
        // No-op by design (see summary). Event wiring lives in the host.
    }

    /// <summary>
    /// Host-free stand-in kept for API compatibility: the REAL
    /// RemoveRegion is WyrdForgeRegionModuleHost.RemoveRegion in the
    /// deployment project. This overload intentionally does nothing.
    /// </summary>
    public void RemoveRegion(object scene)
    {
        // No-op by design (see summary). Event unwiring lives in the host.
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
