// WyrdSystem — WYRD Protocol game-loop integration for MonoGame / FNA (Phase 11E).
//
// Drop WyrdSystem into your Game class and call Update() each frame.
// Async queries are fired on the thread pool and their completion callbacks
// are safely dispatched back to the game update thread via an internal queue.
//
// MonoGame quick-start:
//
//   WyrdSystem _wyrd;
//
//   protected override void Initialize()
//   {
//       _wyrd = new WyrdSystem(new WyrdSystemOptions { Host = "localhost", Port = 8765 });
//       base.Initialize();
//   }
//
//   protected override void Update(GameTime gameTime)
//   {
//       _wyrd.Update(gameTime.ElapsedGameTime);          // drains completion queue
//
//       if (playerSpoke)
//           _wyrd.QueueQuery("sigrid", playerText, result =>
//           {
//               if (result.Success) ShowDialogue(result.Response);
//           });
//
//       base.Update(gameTime);
//   }
//
//   protected override void UnloadContent()
//   {
//       _wyrd.Dispose();
//       base.UnloadContent();
//   }

using System.Collections.Concurrent;
using System.Text.RegularExpressions;
using WyrdForge.Client;

namespace WyrdForge.MonoGame;

// ---------------------------------------------------------------------------
// Options
// ---------------------------------------------------------------------------

/// <summary>Configuration for <see cref="WyrdSystem"/>.</summary>
public sealed record WyrdSystemOptions
{
    /// <summary>WyrdHTTPServer hostname. Default: "localhost"</summary>
    public string Host { get; init; } = "localhost";

    /// <summary>WyrdHTTPServer port. Default: 8765</summary>
    public int Port { get; init; } = 8765;

    /// <summary>Per-request HTTP timeout. Default: 10 seconds</summary>
    public TimeSpan Timeout { get; init; } = TimeSpan.FromSeconds(10);

    /// <summary>
    /// How often WyrdSystem checks server health in the background.
    /// Set to <see cref="TimeSpan.Zero"/> to disable automatic health checks.
    /// Default: 30 seconds.
    /// </summary>
    public TimeSpan HealthCheckInterval { get; init; } = TimeSpan.FromSeconds(30);
}

// ---------------------------------------------------------------------------
// Result types
// ---------------------------------------------------------------------------

/// <summary>Result of a <see cref="WyrdSystem.QueryAsync"/> or queued query.</summary>
public sealed record WyrdQueryResult(
    bool Success,
    string PersonaId,
    string Response,
    string? Error = null
);

// ---------------------------------------------------------------------------
// WyrdSystem
// ---------------------------------------------------------------------------

/// <summary>
/// WYRD Protocol integration for MonoGame / FNA games.
///
/// Call <see cref="Update(TimeSpan)"/> in your game's Update loop.
/// Async query completions are dispatched back to the Update thread
/// via an internal <see cref="ConcurrentQueue{T}"/>, so callbacks
/// run on the same thread as your game logic.
/// </summary>
public sealed class WyrdSystem : IDisposable
{
    private static readonly Regex _invalidChars =
        new(@"[^a-z0-9_]", RegexOptions.Compiled);
    private static readonly Regex _multiUnder =
        new(@"_+", RegexOptions.Compiled);

    private readonly WyrdClient _client;
    private readonly WyrdSystemOptions _options;
    private readonly ConcurrentQueue<Action> _completionQueue = new();
    private readonly Dictionary<string, WyrdEntity> _entities = [];
    private readonly object _entitiesLock = new();

    private TimeSpan _healthTimer = TimeSpan.Zero;
    private bool _isConnected;
    private string _lastError = string.Empty;
    private bool _disposed;

    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------

    /// <summary>Create a WyrdSystem with default options (localhost:8765).</summary>
    public WyrdSystem() : this(new WyrdSystemOptions()) { }

    /// <summary>Create a WyrdSystem with explicit options.</summary>
    public WyrdSystem(WyrdSystemOptions options)
    {
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _client = new WyrdClient(new WyrdClientOptions
        {
            Host = options.Host,
            Port = options.Port,
            Timeout = options.Timeout,
        });
    }

    // -------------------------------------------------------------------------
    // State
    // -------------------------------------------------------------------------

    /// <summary>True if the last background health check succeeded.</summary>
    public bool IsConnected => _isConnected;

    /// <summary>The error message from the last failed operation, or empty.</summary>
    public string LastError => _lastError;

    // -------------------------------------------------------------------------
    // Game loop
    // -------------------------------------------------------------------------

    /// <summary>
    /// Call once per frame in Game.Update().
    /// Usage: <c>_wyrd.Update(gameTime.ElapsedGameTime);</c>
    ///
    /// Drains the completion callback queue and, if enabled, fires
    /// periodic health checks in the background.
    /// </summary>
    /// <param name="elapsed">Time elapsed since last frame.</param>
    public void Update(TimeSpan elapsed)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        // Drain completion callbacks — runs them on the game thread.
        while (_completionQueue.TryDequeue(out var action))
        {
            try { action(); }
            catch { /* swallow; game must not crash on WYRD callback errors */ }
        }

        // Periodic health check.
        if (_options.HealthCheckInterval > TimeSpan.Zero)
        {
            _healthTimer += elapsed;
            if (_healthTimer >= _options.HealthCheckInterval)
            {
                _healthTimer = TimeSpan.Zero;
                _ = RunHealthCheckAsync();
            }
        }
    }

    // -------------------------------------------------------------------------
    // Queries
    // -------------------------------------------------------------------------

    /// <summary>
    /// Queue a WYRD character context query. The <paramref name="onComplete"/>
    /// callback runs on the game thread during the next <see cref="Update"/> call.
    /// Safe to call from anywhere in the game loop.
    /// </summary>
    public void QueueQuery(
        string personaId,
        string query,
        Action<WyrdQueryResult>? onComplete = null)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _ = Task.Run(async () =>
        {
            var result = await QueryInternalAsync(personaId, query, CancellationToken.None);
            if (onComplete is not null)
                _completionQueue.Enqueue(() => onComplete(result));
        });
    }

    /// <summary>
    /// Directly await a WYRD context query. For use outside the Update loop
    /// (e.g. loading screens, async game logic).
    /// </summary>
    public async Task<WyrdQueryResult> QueryAsync(
        string personaId,
        string query,
        CancellationToken ct = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        return await QueryInternalAsync(personaId, query, ct);
    }

    // -------------------------------------------------------------------------
    // Fire-and-forget pushes
    // -------------------------------------------------------------------------

    /// <summary>
    /// Push a world observation to WYRD. Fire-and-forget — errors are
    /// captured in <see cref="LastError"/> and do not throw.
    /// </summary>
    public void PushObservation(string title, string summary)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _ = Task.Run(async () =>
        {
            try
            {
                await _client.PushObservationAsync(title, summary);
            }
            catch (Exception ex)
            {
                _completionQueue.Enqueue(() => _lastError = ex.Message);
            }
        });
    }

    /// <summary>
    /// Push a canonical world fact to WYRD. Fire-and-forget.
    /// </summary>
    public void PushFact(string subjectId, string key, string value)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _ = Task.Run(async () =>
        {
            try
            {
                await _client.PushFactAsync(subjectId, key, value);
            }
            catch (Exception ex)
            {
                _completionQueue.Enqueue(() => _lastError = ex.Message);
            }
        });
    }

    // -------------------------------------------------------------------------
    // Entity management
    // -------------------------------------------------------------------------

    /// <summary>
    /// Register a game entity with WyrdSystem. Replaces any existing
    /// entity with the same <see cref="WyrdEntity.EntityId"/>.
    /// </summary>
    public void RegisterEntity(WyrdEntity entity)
    {
        ArgumentNullException.ThrowIfNull(entity);
        if (string.IsNullOrEmpty(entity.EntityId))
            throw new ArgumentException("WyrdEntity.EntityId must not be empty.", nameof(entity));

        lock (_entitiesLock)
            _entities[entity.EntityId] = entity;
    }

    /// <summary>Remove a previously registered entity.</summary>
    public void UnregisterEntity(string entityId)
    {
        lock (_entitiesLock)
            _entities.Remove(entityId);
    }

    /// <summary>
    /// Push all registered facts for a single entity to WYRD.
    /// </summary>
    public async Task SyncEntityAsync(string entityId, CancellationToken ct = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        WyrdEntity? entity;
        lock (_entitiesLock)
            _entities.TryGetValue(entityId, out entity);

        if (entity is null) return;
        await SyncEntityCoreAsync(entity, ct);
    }

    /// <summary>
    /// Push all registered facts for every registered entity to WYRD.
    /// </summary>
    public async Task SyncAllEntitiesAsync(CancellationToken ct = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        WyrdEntity[] snapshot;
        lock (_entitiesLock)
            snapshot = [.. _entities.Values];

        foreach (var entity in snapshot)
            await SyncEntityCoreAsync(entity, ct);
    }

    // -------------------------------------------------------------------------
    // Static helpers
    // -------------------------------------------------------------------------

    /// <summary>
    /// Normalize a display name to a valid WYRD persona_id (snake_case, max 64 chars).
    /// </summary>
    public static string NormalizePersonaId(string name)
    {
        if (string.IsNullOrEmpty(name)) return string.Empty;
        var lower = name.ToLowerInvariant();
        var replaced = _invalidChars.Replace(lower, "_");
        var collapsed = _multiUnder.Replace(replaced, "_");
        return collapsed.Trim('_')[..Math.Min(collapsed.Trim('_').Length, 64)];
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    private async Task<WyrdQueryResult> QueryInternalAsync(
        string personaId, string query, CancellationToken ct)
    {
        try
        {
            var response = await _client.QueryAsync(
                personaId,
                string.IsNullOrEmpty(query) ? "What is the current world state?" : query,
                new QueryOptions { UseTurnLoop = false },
                ct);
            _isConnected = true;
            _lastError = string.Empty;
            return new WyrdQueryResult(true, personaId, response);
        }
        catch (Exception ex)
        {
            _isConnected = false;
            _lastError = ex.Message;
            return new WyrdQueryResult(false, personaId, string.Empty, ex.Message);
        }
    }

    private async Task SyncEntityCoreAsync(WyrdEntity entity, CancellationToken ct)
    {
        foreach (var (key, value) in entity.ToFacts())
        {
            try
            {
                await _client.PushFactAsync(entity.EntityId, key, value, ct: ct);
            }
            catch (Exception ex)
            {
                _lastError = ex.Message;
            }
        }
    }

    private async Task RunHealthCheckAsync()
    {
        try
        {
            var ok = await _client.HealthAsync();
            _completionQueue.Enqueue(() => _isConnected = ok);
        }
        catch
        {
            _completionQueue.Enqueue(() => _isConnected = false);
        }
    }

    // -------------------------------------------------------------------------
    // IDisposable
    // -------------------------------------------------------------------------

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _client.Dispose();
    }
}
