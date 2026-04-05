using WyrdForge.OpenSim;
using Xunit;

namespace WyrdForge.OpenSim.Tests;

// ---------------------------------------------------------------------------
// OpenSimBridgeOptions
// ---------------------------------------------------------------------------

public class OpenSimBridgeOptionsTests
{
    [Fact]
    public void Defaults_AreCorrect()
    {
        var opts = new OpenSimBridgeOptions();
        Assert.Equal("localhost", opts.Host);
        Assert.Equal(8765, opts.Port);
        Assert.Equal(10000, opts.TimeoutMs);
        Assert.True(opts.AutoSyncAvatars);
        Assert.True(opts.EnableChatCommands);
    }

    [Fact]
    public void Custom_ValuesApplied()
    {
        var opts = new OpenSimBridgeOptions("sim.example.com", 9999, 5000, false, false);
        Assert.Equal("sim.example.com", opts.Host);
        Assert.Equal(9999, opts.Port);
        Assert.False(opts.AutoSyncAvatars);
        Assert.False(opts.EnableChatCommands);
    }

    [Fact]
    public void Options_IsRecord_SupportsWith()
    {
        var base_ = new OpenSimBridgeOptions();
        var derived = base_ with { Port = 1234 };
        Assert.Equal(1234, derived.Port);
        Assert.Equal("localhost", derived.Host);
    }
}

// ---------------------------------------------------------------------------
// AvatarRecord
// ---------------------------------------------------------------------------

public class AvatarRecordTests
{
    [Fact]
    public void Properties_AreReadable()
    {
        var av = new AvatarRecord("uuid-001", "Sigrid Stormborn", "Midgard", "Norse Heathens");
        Assert.Equal("uuid-001", av.AgentId);
        Assert.Equal("Sigrid Stormborn", av.Name);
        Assert.Equal("Midgard", av.Region);
        Assert.Equal("Norse Heathens", av.Group);
    }

    [Fact]
    public void NullableFields_DefaultToNull()
    {
        var av = new AvatarRecord("id", "Name");
        Assert.Null(av.Region);
        Assert.Null(av.Group);
        Assert.Null(av.CustomFacts);
    }
}

// ---------------------------------------------------------------------------
// AvatarMapper.ToPersonaId
// ---------------------------------------------------------------------------

public class AvatarMapperToPersonaIdTests
{
    [Fact]
    public void Lowercases()
        => Assert.Equal("sigrid", AvatarMapper.ToPersonaId("Sigrid"));

    [Fact]
    public void Replaces_Spaces()
        => Assert.Equal("sigrid_stormborn", AvatarMapper.ToPersonaId("Sigrid Stormborn"));

    [Fact]
    public void Collapses_Multiple_Spaces()
        => Assert.Equal("a_b", AvatarMapper.ToPersonaId("a  b"));

    [Fact]
    public void Strips_Leading_Underscores()
        => Assert.Equal("sigrid", AvatarMapper.ToPersonaId("_Sigrid"));

    [Fact]
    public void Strips_Trailing_Underscores()
        => Assert.Equal("sigrid", AvatarMapper.ToPersonaId("Sigrid_"));

    [Fact]
    public void Truncates_At_64()
        => Assert.Equal(64, AvatarMapper.ToPersonaId(new string('a', 100)).Length);

    [Fact]
    public void Empty_Returns_Empty()
        => Assert.Equal(string.Empty, AvatarMapper.ToPersonaId(string.Empty));

    [Fact]
    public void Preserves_Numbers()
        => Assert.Equal("npc_001", AvatarMapper.ToPersonaId("npc_001"));

    [Fact]
    public void Replaces_Dots()
        => Assert.Equal("first_last", AvatarMapper.ToPersonaId("First.Last"));

    [Fact]
    public void Already_Valid_Unchanged()
        => Assert.Equal("sigrid", AvatarMapper.ToPersonaId("sigrid"));
}

// ---------------------------------------------------------------------------
// AvatarMapper.ToFacts
// ---------------------------------------------------------------------------

public class AvatarMapperToFactsTests
{
    [Fact]
    public void Includes_Name()
    {
        var av = new AvatarRecord("id", "Sigrid");
        var facts = AvatarMapper.ToFacts(av);
        Assert.Contains(facts, f => f.Key == "name" && f.Value == "Sigrid");
    }

    [Fact]
    public void Includes_AgentId()
    {
        var av = new AvatarRecord("uuid-abc", "X");
        var facts = AvatarMapper.ToFacts(av);
        Assert.Contains(facts, f => f.Key == "agent_id" && f.Value == "uuid-abc");
    }

    [Fact]
    public void Includes_Region_WhenSet()
    {
        var av = new AvatarRecord("id", "X", Region: "Midgard");
        var facts = AvatarMapper.ToFacts(av);
        Assert.Contains(facts, f => f.Key == "region" && f.Value == "Midgard");
    }

    [Fact]
    public void Omits_Region_WhenNull()
    {
        var av = new AvatarRecord("id", "X");
        var facts = AvatarMapper.ToFacts(av);
        Assert.DoesNotContain(facts, f => f.Key == "region");
    }

    [Fact]
    public void Includes_Group_WhenSet()
    {
        var av = new AvatarRecord("id", "X", Group: "Norse Heathens");
        var facts = AvatarMapper.ToFacts(av);
        Assert.Contains(facts, f => f.Key == "group" && f.Value == "Norse Heathens");
    }

    [Fact]
    public void Includes_CustomFacts()
    {
        var av = new AvatarRecord("id", "X", CustomFacts: new() { ["role"] = "seer" });
        var facts = AvatarMapper.ToFacts(av);
        Assert.Contains(facts, f => f.Key == "role" && f.Value == "seer");
    }

    [Fact]
    public void Omits_Null_CustomFact_Values()
    {
        var av = new AvatarRecord("id", "X", CustomFacts: new() { ["role"] = null! });
        var facts = AvatarMapper.ToFacts(av);
        Assert.DoesNotContain(facts, f => f.Key == "role");
    }
}

// ---------------------------------------------------------------------------
// ChatCommandParser
// ---------------------------------------------------------------------------

public class ChatCommandParserTests
{
    [Fact]
    public void NonCommand_ReturnsNone()
    {
        var r = ChatCommandParser.Parse("Hello everyone");
        Assert.Equal(ChatCommandType.None, r.Type);
    }

    [Fact]
    public void Health_Command()
    {
        var r = ChatCommandParser.Parse("/wyrd-health");
        Assert.Equal(ChatCommandType.Health, r.Type);
    }

    [Fact]
    public void Health_CaseInsensitive()
    {
        var r = ChatCommandParser.Parse("/WYRD-HEALTH");
        Assert.Equal(ChatCommandType.Health, r.Type);
    }

    [Fact]
    public void Sync_ExtractsName()
    {
        var r = ChatCommandParser.Parse("/wyrd-sync Sigrid Stormborn");
        Assert.Equal(ChatCommandType.Sync, r.Type);
        Assert.Equal("Sigrid Stormborn", r.PersonaId);
    }

    [Fact]
    public void Sync_NoName_EmptyPersonaId()
    {
        var r = ChatCommandParser.Parse("/wyrd-sync");
        Assert.Equal(ChatCommandType.Sync, r.Type);
        Assert.Equal(string.Empty, r.PersonaId);
    }

    [Fact]
    public void Query_PersonaOnly()
    {
        var r = ChatCommandParser.Parse("/wyrd sigrid");
        Assert.Equal(ChatCommandType.Query, r.Type);
        Assert.Equal("sigrid", r.PersonaId);
        Assert.Equal(string.Empty, r.Query);
    }

    [Fact]
    public void Query_PersonaAndQuery()
    {
        var r = ChatCommandParser.Parse("/wyrd sigrid What do the runes say?");
        Assert.Equal("sigrid", r.PersonaId);
        Assert.Equal("What do the runes say?", r.Query);
    }

    [Fact]
    public void Query_MultiwordQuery()
    {
        var r = ChatCommandParser.Parse("/wyrd gunnar Tell me about the hall");
        Assert.Equal("gunnar", r.PersonaId);
        Assert.Equal("Tell me about the hall", r.Query);
    }

    [Fact]
    public void Null_ReturnsNone()
    {
        var r = ChatCommandParser.Parse(null);
        Assert.Equal(ChatCommandType.None, r.Type);
    }

    [Fact]
    public void Empty_ReturnsNone()
    {
        var r = ChatCommandParser.Parse(string.Empty);
        Assert.Equal(ChatCommandType.None, r.Type);
    }

    [Fact]
    public void Trims_Whitespace()
    {
        var r = ChatCommandParser.Parse("  /wyrd astrid  Storm?  ");
        Assert.Equal("astrid", r.PersonaId);
        Assert.Equal("Storm?", r.Query);
    }
}

// ---------------------------------------------------------------------------
// WyrdContextResult / WyrdSyncResult
// ---------------------------------------------------------------------------

public class ResultTypeTests
{
    [Fact]
    public void ContextResult_Success()
    {
        var r = new WyrdContextResult(true, "sigrid", "The hall is quiet.");
        Assert.True(r.Success);
        Assert.Equal("sigrid", r.PersonaId);
        Assert.Equal("The hall is quiet.", r.ContextText);
        Assert.Null(r.ErrorMessage);
    }

    [Fact]
    public void ContextResult_Failure()
    {
        var r = new WyrdContextResult(false, "x", string.Empty, "Connection refused");
        Assert.False(r.Success);
        Assert.Equal("Connection refused", r.ErrorMessage);
    }

    [Fact]
    public void SyncResult_Success()
    {
        var r = new WyrdSyncResult(true, "sigrid");
        Assert.True(r.Success);
        Assert.Null(r.ErrorMessage);
    }

    [Fact]
    public void SyncResult_Failure()
    {
        var r = new WyrdSyncResult(false, "x", "Server down");
        Assert.False(r.Success);
        Assert.Equal("Server down", r.ErrorMessage);
    }
}

// ---------------------------------------------------------------------------
// WyrdForgeRegionModule — construction
// ---------------------------------------------------------------------------

public class WyrdForgeRegionModuleTests
{
    [Fact]
    public void DefaultConstruction_DoesNotThrow()
    {
        using var m = new WyrdForgeRegionModule();
        Assert.NotNull(m);
    }

    [Fact]
    public void CustomOptions_DoesNotThrow()
    {
        using var m = new WyrdForgeRegionModule(
            new OpenSimBridgeOptions("testhost", 9000, 3000));
        Assert.NotNull(m);
    }

    [Fact]
    public void Name_IsWyrdForge()
    {
        using var m = new WyrdForgeRegionModule();
        Assert.Equal("WyrdForge", m.Name);
    }

    [Fact]
    public void Dispose_CanBeCalledTwice()
    {
        var m = new WyrdForgeRegionModule();
        m.Dispose();
        m.Dispose(); // must not throw
    }

    [Fact]
    public async Task QueryContextAsync_WhenServerDown_ReturnsFailure()
    {
        using var m = new WyrdForgeRegionModule(
            new OpenSimBridgeOptions("localhost", 19999, 1000));
        var result = await m.QueryContextAsync("sigrid", "Hello?");
        Assert.False(result.Success);
        Assert.NotNull(result.ErrorMessage);
    }

    [Fact]
    public async Task SyncAvatarAsync_EmptyName_ReturnsFailure()
    {
        using var m = new WyrdForgeRegionModule();
        var av = new AvatarRecord("id", "");
        var result = await m.SyncAvatarAsync(av);
        Assert.False(result.Success);
    }

    [Fact]
    public async Task DispatchChatCommand_NonCommand_ReturnsNull()
    {
        using var m = new WyrdForgeRegionModule();
        var reply = await m.DispatchChatCommandAsync("Hello everyone");
        Assert.Null(reply);
    }

    [Fact]
    public async Task DispatchChatCommand_QueryNoPersonaId_ReturnUsage()
    {
        using var m = new WyrdForgeRegionModule();
        var reply = await m.DispatchChatCommandAsync("/wyrd");
        Assert.NotNull(reply);
        Assert.Contains("Usage", reply, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task DispatchChatCommand_SyncNoName_ReturnsUsage()
    {
        using var m = new WyrdForgeRegionModule();
        var reply = await m.DispatchChatCommandAsync("/wyrd-sync");
        Assert.NotNull(reply);
        Assert.Contains("Usage", reply, StringComparison.OrdinalIgnoreCase);
    }
}
