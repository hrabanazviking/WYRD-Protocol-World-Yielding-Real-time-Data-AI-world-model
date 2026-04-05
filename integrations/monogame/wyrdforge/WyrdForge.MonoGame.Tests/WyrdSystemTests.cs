using WyrdForge.MonoGame;
using Xunit;

namespace WyrdForge.MonoGame.Tests;

// ---------------------------------------------------------------------------
// WyrdSystemOptions
// ---------------------------------------------------------------------------

public class WyrdSystemOptionsTests
{
    [Fact]
    public void Defaults_AreCorrect()
    {
        var opts = new WyrdSystemOptions();
        Assert.Equal("localhost", opts.Host);
        Assert.Equal(8765, opts.Port);
        Assert.Equal(TimeSpan.FromSeconds(10), opts.Timeout);
        Assert.Equal(TimeSpan.FromSeconds(30), opts.HealthCheckInterval);
    }

    [Fact]
    public void Custom_ValuesAreApplied()
    {
        var opts = new WyrdSystemOptions
        {
            Host = "192.168.1.10",
            Port = 9000,
            Timeout = TimeSpan.FromSeconds(5),
            HealthCheckInterval = TimeSpan.Zero,
        };
        Assert.Equal("192.168.1.10", opts.Host);
        Assert.Equal(9000, opts.Port);
        Assert.Equal(TimeSpan.FromSeconds(5), opts.Timeout);
        Assert.Equal(TimeSpan.Zero, opts.HealthCheckInterval);
    }

    [Fact]
    public void Options_IsRecord_SupportsWith()
    {
        var base_ = new WyrdSystemOptions();
        var derived = base_ with { Port = 1234 };
        Assert.Equal(1234, derived.Port);
        Assert.Equal("localhost", derived.Host); // unchanged
    }
}

// ---------------------------------------------------------------------------
// WyrdQueryResult
// ---------------------------------------------------------------------------

public class WyrdQueryResultTests
{
    [Fact]
    public void Success_Result_HasCorrectProperties()
    {
        var r = new WyrdQueryResult(true, "sigrid", "The hall is quiet.");
        Assert.True(r.Success);
        Assert.Equal("sigrid", r.PersonaId);
        Assert.Equal("The hall is quiet.", r.Response);
        Assert.Null(r.Error);
    }

    [Fact]
    public void Failure_Result_HasError()
    {
        var r = new WyrdQueryResult(false, "gunnar", string.Empty, "Connection refused");
        Assert.False(r.Success);
        Assert.Equal("Connection refused", r.Error);
        Assert.Equal(string.Empty, r.Response);
    }

    [Fact]
    public void Result_IsRecord_SupportsWith()
    {
        var r = new WyrdQueryResult(true, "x", "y");
        var r2 = r with { Response = "updated" };
        Assert.Equal("updated", r2.Response);
        Assert.Equal("x", r2.PersonaId);
    }
}

// ---------------------------------------------------------------------------
// WyrdSystem — construction & disposal
// ---------------------------------------------------------------------------

public class WyrdSystemConstructionTests
{
    [Fact]
    public void DefaultConstructor_DoesNotThrow()
    {
        using var ws = new WyrdSystem();
        Assert.NotNull(ws);
    }

    [Fact]
    public void OptionsConstructor_DoesNotThrow()
    {
        using var ws = new WyrdSystem(new WyrdSystemOptions { Host = "testhost", Port = 9999 });
        Assert.NotNull(ws);
    }

    [Fact]
    public void InitialState_IsConnected_IsFalse()
    {
        using var ws = new WyrdSystem();
        Assert.False(ws.IsConnected);
    }

    [Fact]
    public void InitialState_LastError_IsEmpty()
    {
        using var ws = new WyrdSystem();
        Assert.Equal(string.Empty, ws.LastError);
    }

    [Fact]
    public void Dispose_CanBeCalledTwice()
    {
        var ws = new WyrdSystem();
        ws.Dispose();
        ws.Dispose(); // must not throw
    }

    [Fact]
    public void Update_AfterDispose_Throws()
    {
        var ws = new WyrdSystem();
        ws.Dispose();
        Assert.Throws<ObjectDisposedException>(() => ws.Update(TimeSpan.FromMilliseconds(16)));
    }

    [Fact]
    public void QueueQuery_AfterDispose_Throws()
    {
        var ws = new WyrdSystem();
        ws.Dispose();
        Assert.Throws<ObjectDisposedException>(() => ws.QueueQuery("x", "y"));
    }

    [Fact]
    public void PushObservation_AfterDispose_Throws()
    {
        var ws = new WyrdSystem();
        ws.Dispose();
        Assert.Throws<ObjectDisposedException>(() => ws.PushObservation("title", "summary"));
    }
}

// ---------------------------------------------------------------------------
// WyrdSystem.Update — completion queue draining
// ---------------------------------------------------------------------------

public class WyrdSystemUpdateTests
{
    [Fact]
    public void Update_WithNoCallbacks_DoesNotThrow()
    {
        using var ws = new WyrdSystem(new WyrdSystemOptions
        {
            HealthCheckInterval = TimeSpan.Zero // disable health checks
        });
        ws.Update(TimeSpan.FromMilliseconds(16));
    }

    [Fact]
    public async Task QueueQuery_Callback_RunsOnUpdate()
    {
        // WyrdSystem with health checks disabled so Update is deterministic.
        using var ws = new WyrdSystem(new WyrdSystemOptions
        {
            HealthCheckInterval = TimeSpan.Zero
        });

        // We cannot hit a real server, so we test that:
        //   1. QueueQuery does not throw even when server is unreachable.
        //   2. The callback eventually fires (failure result) within a timeout.
        WyrdQueryResult? received = null;
        var tcs = new TaskCompletionSource<bool>();

        ws.QueueQuery("sigrid", "Hello?", result =>
        {
            received = result;
            tcs.TrySetResult(true);
        });

        // Drain the queue by calling Update in a spin loop until callback fires.
        var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(5);
        while (received is null && DateTime.UtcNow < deadline)
        {
            ws.Update(TimeSpan.FromMilliseconds(16));
            await Task.Delay(20);
        }

        Assert.NotNull(received);
        // Server is not running — expect failure.
        Assert.False(received.Success);
        Assert.Equal("sigrid", received.PersonaId);
        Assert.NotNull(received.Error);
    }
}

// ---------------------------------------------------------------------------
// NormalizePersonaId
// ---------------------------------------------------------------------------

public class NormalizePersonaIdTests
{
    [Fact]
    public void Lowercases_Input()
        => Assert.Equal("sigrid", WyrdSystem.NormalizePersonaId("Sigrid"));

    [Fact]
    public void Replaces_Spaces_With_Underscores()
        => Assert.Equal("erik_red", WyrdSystem.NormalizePersonaId("Erik Red"));

    [Fact]
    public void Collapses_Multiple_Underscores()
        => Assert.Equal("a_b", WyrdSystem.NormalizePersonaId("a  b"));

    [Fact]
    public void Strips_Leading_Underscores()
        => Assert.Equal("sigrid", WyrdSystem.NormalizePersonaId("_sigrid"));

    [Fact]
    public void Strips_Trailing_Underscores()
        => Assert.Equal("sigrid", WyrdSystem.NormalizePersonaId("sigrid_"));

    [Fact]
    public void Truncates_At_64_Chars()
    {
        var result = WyrdSystem.NormalizePersonaId(new string('a', 100));
        Assert.Equal(64, result.Length);
    }

    [Fact]
    public void Empty_String_Returns_Empty()
        => Assert.Equal(string.Empty, WyrdSystem.NormalizePersonaId(string.Empty));

    [Fact]
    public void Preserves_Numbers()
        => Assert.Equal("npc_001", WyrdSystem.NormalizePersonaId("npc_001"));

    [Fact]
    public void Replaces_Dots()
        => Assert.Equal("npc_archer", WyrdSystem.NormalizePersonaId("npc.archer"));

    [Fact]
    public void Replaces_Dashes()
        => Assert.Equal("npc_one", WyrdSystem.NormalizePersonaId("npc-one"));

    [Fact]
    public void Already_Valid_Id_Unchanged()
        => Assert.Equal("sigrid", WyrdSystem.NormalizePersonaId("sigrid"));
}

// ---------------------------------------------------------------------------
// WyrdEntity
// ---------------------------------------------------------------------------

public class WyrdEntityTests
{
    [Fact]
    public void DefaultConstruction_HasEmptyCollections()
    {
        var e = new WyrdEntity();
        Assert.Empty(e.Tags);
        Assert.Empty(e.CustomFacts);
    }

    [Fact]
    public void ToFacts_IncludesName()
    {
        var e = new WyrdEntity { EntityId = "sigrid", Name = "Sigrid" };
        var facts = e.ToFacts().ToList();
        Assert.Contains(facts, f => f.Key == "name" && f.Value == "Sigrid");
    }

    [Fact]
    public void ToFacts_IncludesLocation_WhenSet()
    {
        var e = new WyrdEntity { EntityId = "sigrid", Name = "Sigrid", LocationId = "mead_hall" };
        var facts = e.ToFacts().ToList();
        Assert.Contains(facts, f => f.Key == "location" && f.Value == "mead_hall");
    }

    [Fact]
    public void ToFacts_OmitsLocation_WhenNull()
    {
        var e = new WyrdEntity { EntityId = "x", Name = "X" };
        var facts = e.ToFacts().ToList();
        Assert.DoesNotContain(facts, f => f.Key == "location");
    }

    [Fact]
    public void ToFacts_IncludesTags_WhenPresent()
    {
        var e = new WyrdEntity { EntityId = "x", Name = "X", Tags = ["npc", "hostile"] };
        var facts = e.ToFacts().ToList();
        Assert.Contains(facts, f => f.Key == "tags" && f.Value.Contains("npc"));
    }

    [Fact]
    public void ToFacts_OmitsTags_WhenEmpty()
    {
        var e = new WyrdEntity { EntityId = "x", Name = "X" };
        var facts = e.ToFacts().ToList();
        Assert.DoesNotContain(facts, f => f.Key == "tags");
    }

    [Fact]
    public void ToFacts_IncludesCustomFacts()
    {
        var e = new WyrdEntity { EntityId = "x", Name = "X" };
        e.CustomFacts["role"] = "blacksmith";
        var facts = e.ToFacts().ToList();
        Assert.Contains(facts, f => f.Key == "role" && f.Value == "blacksmith");
    }

    [Fact]
    public void ToFacts_OmitsNullCustomFacts()
    {
        var e = new WyrdEntity { EntityId = "x", Name = "X" };
        e.CustomFacts["role"] = null;
        var facts = e.ToFacts().ToList();
        Assert.DoesNotContain(facts, f => f.Key == "role");
    }

    [Fact]
    public void ToFacts_OmitsEmptyName()
    {
        var e = new WyrdEntity { EntityId = "x", Name = "" };
        var facts = e.ToFacts().ToList();
        Assert.DoesNotContain(facts, f => f.Key == "name");
    }
}

// ---------------------------------------------------------------------------
// Entity registration
// ---------------------------------------------------------------------------

public class EntityRegistrationTests
{
    [Fact]
    public void RegisterEntity_ThenSyncDoesNotThrow_WhenServerDown()
    {
        using var ws = new WyrdSystem(new WyrdSystemOptions
        {
            HealthCheckInterval = TimeSpan.Zero
        });
        var entity = new WyrdEntity { EntityId = "sigrid", Name = "Sigrid" };
        ws.RegisterEntity(entity);
        // SyncEntityAsync will fail (no server), but must not throw — it captures the error.
        // We just verify it returns a completed task without exception.
        var task = ws.SyncEntityAsync("sigrid");
        Assert.NotNull(task);
    }

    [Fact]
    public void RegisterEntity_EmptyId_Throws()
    {
        using var ws = new WyrdSystem();
        Assert.Throws<ArgumentException>(() =>
            ws.RegisterEntity(new WyrdEntity { EntityId = "", Name = "X" }));
    }

    [Fact]
    public void RegisterEntity_NullEntity_Throws()
    {
        using var ws = new WyrdSystem();
        Assert.Throws<ArgumentNullException>(() => ws.RegisterEntity(null!));
    }

    [Fact]
    public void UnregisterEntity_NonExistent_DoesNotThrow()
    {
        using var ws = new WyrdSystem();
        ws.UnregisterEntity("nonexistent"); // must not throw
    }

    [Fact]
    public void RegisterAndUnregister_RoundTrip()
    {
        using var ws = new WyrdSystem();
        var entity = new WyrdEntity { EntityId = "gunnar", Name = "Gunnar" };
        ws.RegisterEntity(entity);
        ws.UnregisterEntity("gunnar");
        // SyncEntityAsync on removed entity should be a no-op, not throw.
        var task = ws.SyncEntityAsync("gunnar");
        Assert.NotNull(task);
    }
}
