using WyrdForge.FGU;
using Xunit;

namespace WyrdForge.FGU.Tests;

// ---------------------------------------------------------------------------
// ChatCommandParser tests
// ---------------------------------------------------------------------------

public class ChatCommandParserTests
{
    [Fact]
    public void Parse_NonCommand_ReturnsNone()
    {
        var r = ChatCommandParser.Parse("Hello everyone");
        Assert.Equal(ChatCommandType.None, r.Type);
    }

    [Fact]
    public void Parse_Health_ReturnsHealth()
    {
        var r = ChatCommandParser.Parse("/wyrd-health");
        Assert.Equal(ChatCommandType.Health, r.Type);
    }

    [Fact]
    public void Parse_Health_CaseInsensitive()
    {
        var r = ChatCommandParser.Parse("/WYRD-HEALTH");
        Assert.Equal(ChatCommandType.Health, r.Type);
    }

    [Fact]
    public void Parse_Sync_ExtractsPersonaId()
    {
        var r = ChatCommandParser.Parse("/wyrd-sync Sigrid Stormborn");
        Assert.Equal(ChatCommandType.Sync, r.Type);
        Assert.Equal("Sigrid Stormborn", r.PersonaId);
    }

    [Fact]
    public void Parse_Sync_NoName()
    {
        var r = ChatCommandParser.Parse("/wyrd-sync");
        Assert.Equal(ChatCommandType.Sync, r.Type);
        Assert.Equal(string.Empty, r.PersonaId);
    }

    [Fact]
    public void Parse_Query_PersonaOnly()
    {
        var r = ChatCommandParser.Parse("/wyrd sigrid");
        Assert.Equal(ChatCommandType.Query, r.Type);
        Assert.Equal("sigrid", r.PersonaId);
        Assert.Equal(string.Empty, r.Query);
    }

    [Fact]
    public void Parse_Query_PersonaAndQuery()
    {
        var r = ChatCommandParser.Parse("/wyrd sigrid What is happening?");
        Assert.Equal("sigrid", r.PersonaId);
        Assert.Equal("What is happening?", r.Query);
    }

    [Fact]
    public void Parse_Query_MultiwordQuery()
    {
        var r = ChatCommandParser.Parse("/wyrd astrid Tell me about the storm");
        Assert.Equal("Tell me about the storm", r.Query);
    }

    [Fact]
    public void Parse_Null_ReturnsNone()
    {
        var r = ChatCommandParser.Parse(null);
        Assert.Equal(ChatCommandType.None, r.Type);
    }

    [Fact]
    public void Parse_Empty_ReturnsNone()
    {
        var r = ChatCommandParser.Parse(string.Empty);
        Assert.Equal(ChatCommandType.None, r.Type);
    }

    [Fact]
    public void Parse_TrimsWhitespace()
    {
        var r = ChatCommandParser.Parse("  /wyrd gunnar  Hello  ");
        Assert.Equal("gunnar", r.PersonaId);
        Assert.Equal("Hello", r.Query);
    }
}

// ---------------------------------------------------------------------------
// NPCMapper tests
// ---------------------------------------------------------------------------

public class NPCMapperTests
{
    [Fact]
    public void ToPersonaId_Lowercases()
    {
        Assert.Equal("sigrid", NPCMapper.ToPersonaId("Sigrid"));
    }

    [Fact]
    public void ToPersonaId_ReplacesSpaces()
    {
        Assert.Equal("erik_red", NPCMapper.ToPersonaId("Erik Red"));
    }

    [Fact]
    public void ToPersonaId_CollapsesDuplicateUnderscores()
    {
        Assert.Equal("a_b", NPCMapper.ToPersonaId("a  b"));
    }

    [Fact]
    public void ToPersonaId_TruncatesAt64()
    {
        var long64 = NPCMapper.ToPersonaId(new string('a', 100));
        Assert.Equal(64, long64.Length);
    }

    [Fact]
    public void ToPersonaId_Empty_ReturnsEmpty()
    {
        Assert.Equal(string.Empty, NPCMapper.ToPersonaId(string.Empty));
    }

    [Fact]
    public void ToFacts_IncludesName()
    {
        var npc = new NPCRecord("x", "Sigrid", null, null, null, null);
        var facts = NPCMapper.ToFacts(npc);
        Assert.Contains(facts, f => f.Key == "name" && f.Value == "Sigrid");
    }

    [Fact]
    public void ToFacts_IncludesRaceAndClass()
    {
        var npc = new NPCRecord("x", "Gunnar", "Human", "Warrior", null, null);
        var facts = NPCMapper.ToFacts(npc);
        Assert.Contains(facts, f => f.Key == "race");
        Assert.Contains(facts, f => f.Key == "class");
    }

    [Fact]
    public void ToFacts_OmitsNullFields()
    {
        var npc = new NPCRecord("x", "X", null, null, null, null);
        var facts = NPCMapper.ToFacts(npc);
        Assert.DoesNotContain(facts, f => f.Key == "race");
    }

    [Fact]
    public void ToFacts_IncludesLocation()
    {
        var npc = new NPCRecord("x", "Astrid", null, null, null, "hall");
        var facts = NPCMapper.ToFacts(npc);
        Assert.Contains(facts, f => f.Key == "location" && f.Value == "hall");
    }
}

public class FGUWyrdBridgeConstructionTests
{
    [Fact]
    public void Constructor_DefaultOptions_DoesNotThrow()
    {
        using var b = new FGUWyrdBridge();
        Assert.NotNull(b);
    }

    [Fact]
    public void Constructor_CustomOptions_DoesNotThrow()
    {
        using var b = new FGUWyrdBridge(new FGUBridgeOptions("myhost", 9999, 5000));
        Assert.NotNull(b);
    }
}

public class NPCRecordTests
{
    [Fact]
    public void NPCRecord_Properties_AreReadable()
    {
        var npc = new NPCRecord("id1", "Sigrid", "Elf", "Ranger", "A tall ranger.", "forest");
        Assert.Equal("id1", npc.Id);
        Assert.Equal("Sigrid", npc.Name);
        Assert.Equal("Elf", npc.Race);
        Assert.Equal("Ranger", npc.Class);
        Assert.Equal("A tall ranger.", npc.Description);
        Assert.Equal("forest", npc.Location);
    }
}

public class FGUContextResultTests
{
    [Fact]
    public void FGUContextResult_Success_Properties()
    {
        var r = new FGUContextResult(true, "sigrid", "Some context.");
        Assert.True(r.Success);
        Assert.Equal("sigrid", r.PersonaId);
        Assert.Equal("Some context.", r.ContextText);
        Assert.Null(r.ErrorMessage);
    }

    [Fact]
    public void FGUContextResult_Failure_HasError()
    {
        var r = new FGUContextResult(false, "x", string.Empty, "Connection refused");
        Assert.False(r.Success);
        Assert.Equal("Connection refused", r.ErrorMessage);
    }
}

public class FGUSyncResultTests
{
    [Fact]
    public void FGUSyncResult_Success()
    {
        var r = new FGUSyncResult(true, "sigrid");
        Assert.True(r.Success);
        Assert.Null(r.ErrorMessage);
    }

    [Fact]
    public void FGUSyncResult_Failure_HasError()
    {
        var r = new FGUSyncResult(false, "x", "Server down");
        Assert.False(r.Success);
        Assert.Equal("Server down", r.ErrorMessage);
    }
}
