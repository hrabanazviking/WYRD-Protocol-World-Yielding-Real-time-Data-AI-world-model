// Tests for WyrdClient — Phase 8B C# SDK.
// All tests use a MockHttpHandler; no real server required.

using System.Net;
using System.Text;
using System.Text.Json;
using WyrdForge.Client;
using Xunit;

namespace WyrdForge.Client.Tests;


// ---------------------------------------------------------------------------
// In-process test server using HttpListener
// ---------------------------------------------------------------------------

internal sealed class FakeWyrdServer : IDisposable
{
    private readonly HttpListener _listener;
    private readonly Thread _thread;
    public readonly int Port;
    private volatile bool _running = true;

    // Configurable responses
    public HttpStatusCode HealthStatus { get; set; } = HttpStatusCode.OK;
    public object HealthBody { get; set; } = new { status = "ok" };
    public object QueryBody { get; set; } = new { response = "Mock response." };
    public object WorldBody { get; set; } = new
    {
        query_timestamp = "2026-04-02T12:00:00Z",
        world_id = "test_world",
        focus_entities = Array.Empty<object>(),
        location_context = (object?)null,
        present_entities = Array.Empty<object>(),
        canonical_facts = new { },
        active_policies = Array.Empty<object>(),
        recent_observations = Array.Empty<object>(),
        open_contradiction_count = 0,
        formatted_for_llm = "=== WORLD STATE ===",
    };
    public object FactsBody { get; set; } = new { facts = Array.Empty<object>() };
    public object EventBody { get; set; } = new { ok = true };
    public string? LastRequestBody { get; private set; }

    public FakeWyrdServer()
    {
        Port = GetFreePort();
        _listener = new HttpListener();
        _listener.Prefixes.Add($"http://localhost:{Port}/");
        _listener.Start();
        _thread = new Thread(Serve) { IsBackground = true };
        _thread.Start();
    }

    private void Serve()
    {
        while (_running)
        {
            HttpListenerContext ctx;
            try { ctx = _listener.GetContext(); }
            catch { break; }

            var req = ctx.Request;
            var resp = ctx.Response;

            if (req.HasEntityBody)
                using (var sr = new System.IO.StreamReader(req.InputStream))
                    LastRequestBody = sr.ReadToEnd();

            object responseObj = req.Url!.LocalPath switch
            {
                "/health" => HealthBody,
                "/query" => QueryBody,
                "/world" => WorldBody,
                "/facts" => FactsBody,
                "/event" => EventBody,
                _ => new { error = "Not found" },
            };

            int statusCode = req.Url.LocalPath switch
            {
                "/health" => (int)HealthStatus,
                _ => 200,
            };

            var body = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(responseObj));
            resp.StatusCode = statusCode;
            resp.ContentType = "application/json; charset=utf-8";
            resp.ContentLength64 = body.Length;
            resp.OutputStream.Write(body);
            resp.Close();
        }
    }

    private static int GetFreePort()
    {
        var listener = new System.Net.Sockets.TcpListener(
            System.Net.IPAddress.Loopback, 0);
        listener.Start();
        int port = ((System.Net.IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();
        return port;
    }

    public void Dispose()
    {
        _running = false;
        _listener.Stop();
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

public class WyrdClientConstructionTests
{
    [Fact]
    public void DefaultConstructor_Succeeds()
    {
        using var client = new WyrdClient();
        Assert.NotNull(client);
    }

    [Fact]
    public void OptionsConstructor_Succeeds()
    {
        using var client = new WyrdClient(new WyrdClientOptions
        {
            Host = "127.0.0.1",
            Port = 9999,
            Timeout = TimeSpan.FromSeconds(5),
        });
        Assert.NotNull(client);
    }
}

public class WyrdClientHealthTests
{
    [Fact]
    public async Task Health_ReturnsTrue_WhenServerRespondsOk()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        Assert.True(await client.HealthAsync());
    }

    [Fact]
    public async Task Health_ReturnsFalse_WhenServerUnreachable()
    {
        using var client = new WyrdClient("localhost", 1); // port 1 — nothing there
        Assert.False(await client.HealthAsync());
    }

    [Fact]
    public async Task Health_ReturnsFalse_WhenStatusNotOk()
    {
        using var server = new FakeWyrdServer { HealthBody = new { status = "degraded" } };
        using var client = new WyrdClient("localhost", server.Port);
        Assert.False(await client.HealthAsync());
    }
}

public class WyrdClientQueryTests
{
    [Fact]
    public async Task Query_ReturnsResponseString()
    {
        using var server = new FakeWyrdServer
        {
            QueryBody = new { response = "The runes speak of change." }
        };
        using var client = new WyrdClient("localhost", server.Port);
        var reply = await client.QueryAsync("sigrid", "What do you see?");
        Assert.Equal("The runes speak of change.", reply);
    }

    [Fact]
    public async Task Query_SendsPersonaIdAndUserInput()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        await client.QueryAsync("sigrid", "Hello");
        Assert.NotNull(server.LastRequestBody);
        Assert.Contains("sigrid", server.LastRequestBody);
        Assert.Contains("Hello", server.LastRequestBody);
    }

    [Fact]
    public async Task Query_SendsUseTurnLoopTrue_ByDefault()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        await client.QueryAsync("sigrid", "Hello");
        Assert.Contains("use_turn_loop", server.LastRequestBody!);
        Assert.Contains("true", server.LastRequestBody!);
    }

    [Fact]
    public async Task Query_SendsUseTurnLoopFalse_WhenSpecified()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        await client.QueryAsync("sigrid", "Hello", new QueryOptions { UseTurnLoop = false });
        Assert.Contains("false", server.LastRequestBody!);
    }

    [Fact]
    public async Task Query_ThrowsWyrdConnectionException_WhenUnreachable()
    {
        using var client = new WyrdClient("localhost", 1);
        await Assert.ThrowsAsync<WyrdConnectionException>(
            () => client.QueryAsync("sigrid", "Hi"));
    }
}

public class WyrdClientGetWorldTests
{
    [Fact]
    public async Task GetWorld_ReturnsWorldContextPacket()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        var world = await client.GetWorldAsync();
        Assert.Equal("test_world", world.WorldId);
    }

    [Fact]
    public async Task GetWorld_PacketHasFormattedForLlm()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        var world = await client.GetWorldAsync();
        Assert.NotNull(world.FormattedForLlm);
        Assert.NotEmpty(world.FormattedForLlm);
    }

    [Fact]
    public async Task GetWorld_ThrowsWyrdConnectionException_WhenUnreachable()
    {
        using var client = new WyrdClient("localhost", 1);
        await Assert.ThrowsAsync<WyrdConnectionException>(
            () => client.GetWorldAsync());
    }
}

public class WyrdClientGetFactsTests
{
    private static readonly object MockFactsBody = new
    {
        facts = new[]
        {
            new
            {
                record_id = "rec-001",
                record_type = "canonical_fact",
                content = new
                {
                    title = "sigrid.role = völva",
                    structured_payload = new
                    {
                        fact_subject_id = "sigrid",
                        fact_key = "role",
                        fact_value = "völva",
                        value_type = "string",
                        domain = "identity",
                    }
                }
            }
        }
    };

    [Fact]
    public async Task GetFacts_ReturnsListOfFactRecord()
    {
        using var server = new FakeWyrdServer { FactsBody = MockFactsBody };
        using var client = new WyrdClient("localhost", server.Port);
        var facts = await client.GetFactsAsync("sigrid");
        Assert.Single(facts);
    }

    [Fact]
    public async Task GetFacts_FactHasCorrectValue()
    {
        using var server = new FakeWyrdServer { FactsBody = MockFactsBody };
        using var client = new WyrdClient("localhost", server.Port);
        var facts = await client.GetFactsAsync("sigrid");
        Assert.Equal("völva", facts[0].Content.StructuredPayload.FactValue);
    }

    [Fact]
    public async Task GetFacts_ReturnsEmptyList_ForUnknownEntity()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        var facts = await client.GetFactsAsync("nobody");
        Assert.Empty(facts);
    }
}

public class WyrdClientPushEventTests
{
    [Fact]
    public async Task PushObservation_ReturnsTrue()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        var ok = await client.PushObservationAsync("Storm", "A storm arrived.");
        Assert.True(ok);
    }

    [Fact]
    public async Task PushObservation_SendsCorrectEventType()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        await client.PushObservationAsync("Storm", "A storm arrived.");
        Assert.Contains("observation", server.LastRequestBody!);
    }

    [Fact]
    public async Task PushFact_ReturnsTrue()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        var ok = await client.PushFactAsync("gunnar", "weapon", "axe");
        Assert.True(ok);
    }

    [Fact]
    public async Task PushFact_SendsSubjectIdAndKey()
    {
        using var server = new FakeWyrdServer();
        using var client = new WyrdClient("localhost", server.Port);
        await client.PushFactAsync("gunnar", "weapon", "axe");
        Assert.Contains("gunnar", server.LastRequestBody!);
        Assert.Contains("weapon", server.LastRequestBody!);
    }

    [Fact]
    public async Task PushObservation_ThrowsConnectionException_WhenUnreachable()
    {
        using var client = new WyrdClient("localhost", 1);
        await Assert.ThrowsAsync<WyrdConnectionException>(
            () => client.PushObservationAsync("x", "y"));
    }
}

public class WyrdClientExceptionTests
{
    [Fact]
    public void WyrdConnectionException_HasMessage()
    {
        var ex = new WyrdConnectionException("test message");
        Assert.Equal("test message", ex.Message);
    }

    [Fact]
    public void WyrdApiException_HasStatusCode()
    {
        var ex = new WyrdApiException("bad input", 400);
        Assert.Equal(400, ex.StatusCode);
    }

    [Fact]
    public void WyrdApiException_HasBody()
    {
        var ex = new WyrdApiException("bad input", 400, "{\"error\":\"bad\"}");
        Assert.NotNull(ex.Body);
        Assert.Contains("bad", ex.Body);
    }
}
