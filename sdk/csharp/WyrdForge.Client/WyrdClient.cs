// WyrdClient — async C# HTTP client for the WYRD Protocol WyrdHTTPServer.
//
// Usage:
//   using var client = new WyrdClient("localhost", 8765);
//   string reply = await client.QueryAsync("sigrid", "What do the runes say?");

using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Web;

namespace WyrdForge.Client;

/// <summary>
/// Options for configuring a <see cref="WyrdClient"/>.
/// </summary>
public record WyrdClientOptions
{
    /// <summary>Hostname of the WyrdHTTPServer. Default: "localhost"</summary>
    public string Host { get; init; } = "localhost";

    /// <summary>Port of the WyrdHTTPServer. Default: 8765</summary>
    public int Port { get; init; } = 8765;

    /// <summary>HTTP request timeout. Default: 10 seconds</summary>
    public TimeSpan Timeout { get; init; } = TimeSpan.FromSeconds(10);
}

/// <summary>
/// Options controlling a single <see cref="WyrdClient.QueryAsync"/> call.
/// </summary>
public record QueryOptions
{
    /// <summary>Override location for world context.</summary>
    public string? LocationId { get; init; }

    /// <summary>Bond edge ID for relationship context.</summary>
    public string? BondId { get; init; }

    /// <summary>
    /// When true (default), uses the full TurnLoop — writes to memory and
    /// maintains conversation history. Set false for context-only output
    /// without LLM generation.
    /// </summary>
    public bool UseTurnLoop { get; init; } = true;
}

/// <summary>
/// Async HTTP client for the WYRD Protocol WyrdHTTPServer.
/// Implements <see cref="IDisposable"/> — use with <c>using</c> or dispose explicitly.
/// </summary>
public sealed class WyrdClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _baseUrl;
    private static readonly JsonSerializerOptions _json = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    };

    /// <summary>Create a WyrdClient with explicit host and port.</summary>
    public WyrdClient(string host = "localhost", int port = 8765,
        TimeSpan? timeout = null)
    {
        _baseUrl = $"http://{host}:{port}";
        _http = new HttpClient { Timeout = timeout ?? TimeSpan.FromSeconds(10) };
    }

    /// <summary>Create a WyrdClient from a <see cref="WyrdClientOptions"/> record.</summary>
    public WyrdClient(WyrdClientOptions options)
        : this(options.Host, options.Port, options.Timeout) { }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /// <summary>
    /// Query a character and return their response string.
    /// </summary>
    /// <param name="personaId">ID of the active character/persona.</param>
    /// <param name="userInput">Player or user message text.</param>
    /// <param name="options">Optional overrides.</param>
    /// <param name="ct">Cancellation token.</param>
    public async Task<string> QueryAsync(
        string personaId,
        string userInput,
        QueryOptions? options = null,
        CancellationToken ct = default)
    {
        options ??= new QueryOptions();
        var body = new Dictionary<string, object?>
        {
            ["persona_id"] = personaId,
            ["user_input"] = userInput,
            ["use_turn_loop"] = options.UseTurnLoop,
        };
        if (options.LocationId is not null) body["location_id"] = options.LocationId;
        if (options.BondId is not null) body["bond_id"] = options.BondId;

        var result = await PostAsync<Dictionary<string, string>>("/query", body, ct);
        return result["response"];
    }

    /// <summary>
    /// Fetch the current <see cref="WorldContextPacket"/> from the server.
    /// </summary>
    public async Task<WorldContextPacket> GetWorldAsync(CancellationToken ct = default)
        => await GetAsync<WorldContextPacket>("/world", ct);

    /// <summary>
    /// Fetch canonical facts for a specific entity.
    /// </summary>
    /// <param name="entityId">Entity to query facts for.</param>
    public async Task<List<FactRecord>> GetFactsAsync(
        string entityId, CancellationToken ct = default)
    {
        var encoded = Uri.EscapeDataString(entityId);
        var result = await GetAsync<Dictionary<string, List<FactRecord>>>(
            $"/facts?entity_id={encoded}", ct);
        return result.TryGetValue("facts", out var facts) ? facts : [];
    }

    /// <summary>
    /// Push an observation event to the WYRD server.
    /// </summary>
    public async Task<bool> PushObservationAsync(
        string title, string summary, CancellationToken ct = default)
    {
        var body = new Dictionary<string, object>
        {
            ["event_type"] = "observation",
            ["payload"] = new ObservationEvent(title, summary),
        };
        var result = await PostAsync<Dictionary<string, bool>>("/event", body, ct);
        return result.TryGetValue("ok", out var ok) && ok;
    }

    /// <summary>
    /// Push a canonical fact event to the WYRD server.
    /// </summary>
    public async Task<bool> PushFactAsync(
        string subjectId, string key, string value,
        double? confidence = null, string? domain = null,
        CancellationToken ct = default)
    {
        var body = new Dictionary<string, object>
        {
            ["event_type"] = "fact",
            ["payload"] = new FactEvent(subjectId, key, value, confidence, domain),
        };
        var result = await PostAsync<Dictionary<string, bool>>("/event", body, ct);
        return result.TryGetValue("ok", out var ok) && ok;
    }

    /// <summary>
    /// Check whether the WYRD server is reachable and healthy.
    /// Returns false on any network or API error.
    /// </summary>
    public async Task<bool> HealthAsync(CancellationToken ct = default)
    {
        try
        {
            var result = await GetAsync<Dictionary<string, string>>("/health", ct);
            return result.TryGetValue("status", out var s) && s == "ok";
        }
        catch
        {
            return false;
        }
    }

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    private async Task<T> GetAsync<T>(string path, CancellationToken ct)
    {
        HttpResponseMessage response;
        try
        {
            response = await _http.GetAsync($"{_baseUrl}{path}", ct);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            throw new WyrdConnectionException(
                $"WYRD server unreachable at {_baseUrl}{path}", ex);
        }
        return await ParseResponseAsync<T>(response, path);
    }

    private async Task<T> PostAsync<T>(string path, object body, CancellationToken ct)
    {
        var json = JsonSerializer.Serialize(body, _json);
        var content = new StringContent(json, Encoding.UTF8, "application/json");
        HttpResponseMessage response;
        try
        {
            response = await _http.PostAsync($"{_baseUrl}{path}", content, ct);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
        {
            throw new WyrdConnectionException(
                $"WYRD server unreachable at {_baseUrl}{path}", ex);
        }
        return await ParseResponseAsync<T>(response, path);
    }

    private static async Task<T> ParseResponseAsync<T>(
        HttpResponseMessage response, string path)
    {
        var raw = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
        {
            string message;
            try
            {
                var err = JsonSerializer.Deserialize<Dictionary<string, string>>(raw, _json);
                message = err?.TryGetValue("error", out var e) == true ? e : raw;
            }
            catch
            {
                message = raw;
            }
            throw new WyrdApiException(message, (int)response.StatusCode, raw);
        }
        return JsonSerializer.Deserialize<T>(raw, _json)
            ?? throw new WyrdApiException(
                $"WYRD server returned null body from {path}",
                (int)response.StatusCode);
    }

    public void Dispose() => _http.Dispose();
}
