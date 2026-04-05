using WyrdForge.Unity;
using Xunit;
using System.Collections.Generic;
using System.Text.Json;

namespace WyrdForge.Unity.Tests;

// ---------------------------------------------------------------------------
// WyrdUnityOptions
// ---------------------------------------------------------------------------

public class WyrdUnityOptionsTests
{
    [Fact]
    public void Defaults_AreCorrect()
    {
        var opts = new WyrdUnityOptions();
        Assert.Equal("localhost", opts.Host);
        Assert.Equal(8765, opts.Port);
        Assert.Equal(10, opts.TimeoutSeconds);
        Assert.True(opts.AutoRegisterNPCs);
        Assert.True(opts.SilentOnError);
    }

    [Fact]
    public void BaseUrl_IsCorrect()
    {
        var opts = new WyrdUnityOptions("sim.example.com", 9000);
        Assert.Equal("http://sim.example.com:9000", opts.BaseUrl());
    }

    [Fact]
    public void CustomOptions_Applied()
    {
        var opts = new WyrdUnityOptions("host", 1234, 5, false, false);
        Assert.Equal("host", opts.Host);
        Assert.Equal(1234, opts.Port);
        Assert.Equal(5, opts.TimeoutSeconds);
        Assert.False(opts.AutoRegisterNPCs);
        Assert.False(opts.SilentOnError);
    }
}

// ---------------------------------------------------------------------------
// WyrdEntityData.NormalizePersonaId
// ---------------------------------------------------------------------------

public class NormalizePersonaIdTests
{
    [Fact] public void Lowercases()
        => Assert.Equal("sigrid", WyrdEntityData.NormalizePersonaId("Sigrid"));

    [Fact] public void Replaces_Spaces()
        => Assert.Equal("sigrid_stormborn", WyrdEntityData.NormalizePersonaId("Sigrid Stormborn"));

    [Fact] public void Collapses_Multiple_Spaces()
        => Assert.Equal("a_b", WyrdEntityData.NormalizePersonaId("a  b"));

    [Fact] public void Strips_Leading_Underscores()
        => Assert.Equal("sigrid", WyrdEntityData.NormalizePersonaId("_Sigrid"));

    [Fact] public void Strips_Trailing_Underscores()
        => Assert.Equal("sigrid", WyrdEntityData.NormalizePersonaId("Sigrid_"));

    [Fact] public void Truncates_At_64()
        => Assert.Equal(64, WyrdEntityData.NormalizePersonaId(new string('a', 100)).Length);

    [Fact] public void Empty_Returns_Empty()
        => Assert.Equal(string.Empty, WyrdEntityData.NormalizePersonaId(string.Empty));

    [Fact] public void Preserves_Numbers()
        => Assert.Equal("npc_001", WyrdEntityData.NormalizePersonaId("npc_001"));

    [Fact] public void Replaces_Dots()
        => Assert.Equal("first_last", WyrdEntityData.NormalizePersonaId("First.Last"));

    [Fact] public void Already_Valid_Unchanged()
        => Assert.Equal("sigrid", WyrdEntityData.NormalizePersonaId("sigrid"));
}

// ---------------------------------------------------------------------------
// WyrdEntityData.EscapeJson
// ---------------------------------------------------------------------------

public class EscapeJsonTests
{
    [Fact] public void Escapes_DoubleQuote()
        => Assert.Equal("\\\"", WyrdEntityData.EscapeJson("\""));

    [Fact] public void Escapes_Backslash()
        => Assert.Equal("\\\\", WyrdEntityData.EscapeJson("\\"));

    [Fact] public void Escapes_Newline()
        => Assert.Equal("\\n", WyrdEntityData.EscapeJson("\n"));

    [Fact] public void Escapes_Tab()
        => Assert.Equal("\\t", WyrdEntityData.EscapeJson("\t"));

    [Fact] public void Empty_Returns_Empty()
        => Assert.Equal(string.Empty, WyrdEntityData.EscapeJson(string.Empty));

    [Fact] public void Null_Returns_Empty()
        => Assert.Equal(string.Empty, WyrdEntityData.EscapeJson(null));

    [Fact] public void Plain_String_Unchanged()
        => Assert.Equal("hello", WyrdEntityData.EscapeJson("hello"));
}

// ---------------------------------------------------------------------------
// WyrdEntityData.BuildQueryBody
// ---------------------------------------------------------------------------

public class BuildQueryBodyTests
{
    [Fact]
    public void Basic_ParsesCleanly()
    {
        var body   = WyrdEntityData.BuildQueryBody("sigrid", "Hello");
        var parsed = JsonDocument.Parse(body).RootElement;
        Assert.Equal("sigrid", parsed.GetProperty("persona_id").GetString());
        Assert.Equal("Hello",  parsed.GetProperty("user_input").GetString());
        Assert.False(parsed.GetProperty("use_turn_loop").GetBoolean());
    }

    [Fact]
    public void Empty_Input_Defaults()
    {
        var body   = WyrdEntityData.BuildQueryBody("sigrid", "");
        var parsed = JsonDocument.Parse(body).RootElement;
        Assert.Equal("What is the current world state?",
                     parsed.GetProperty("user_input").GetString());
    }

    [Fact]
    public void Whitespace_Input_Defaults()
    {
        var body   = WyrdEntityData.BuildQueryBody("sigrid", "   ");
        var parsed = JsonDocument.Parse(body).RootElement;
        Assert.Contains("world state", parsed.GetProperty("user_input").GetString());
    }

    [Fact]
    public void Special_Chars_In_Input()
    {
        var body   = WyrdEntityData.BuildQueryBody("sigrid", "Say \"hello\"");
        var parsed = JsonDocument.Parse(body).RootElement;
        Assert.Equal("Say \"hello\"", parsed.GetProperty("user_input").GetString());
    }
}

// ---------------------------------------------------------------------------
// WyrdEntityData.BuildObservationBody
// ---------------------------------------------------------------------------

public class BuildObservationBodyTests
{
    [Fact]
    public void Basic()
    {
        var body   = WyrdEntityData.BuildObservationBody("NPC spawned", "Sigrid appeared.");
        var parsed = JsonDocument.Parse(body).RootElement;
        Assert.Equal("observation", parsed.GetProperty("event_type").GetString());
        Assert.Equal("NPC spawned", parsed.GetProperty("payload").GetProperty("title").GetString());
        Assert.Equal("Sigrid appeared.", parsed.GetProperty("payload").GetProperty("summary").GetString());
    }

    [Fact]
    public void Valid_Json() => JsonDocument.Parse(
        WyrdEntityData.BuildObservationBody("T", "S"));
}

// ---------------------------------------------------------------------------
// WyrdEntityData.BuildFactBody
// ---------------------------------------------------------------------------

public class BuildFactBodyTests
{
    [Fact]
    public void Basic()
    {
        var body   = WyrdEntityData.BuildFactBody("sigrid", "scene", "Valhalla");
        var parsed = JsonDocument.Parse(body).RootElement;
        Assert.Equal("fact",     parsed.GetProperty("event_type").GetString());
        Assert.Equal("sigrid",   parsed.GetProperty("payload").GetProperty("subject_id").GetString());
        Assert.Equal("scene",    parsed.GetProperty("payload").GetProperty("key").GetString());
        Assert.Equal("Valhalla", parsed.GetProperty("payload").GetProperty("value").GetString());
    }

    [Fact]
    public void Valid_Json() => JsonDocument.Parse(
        WyrdEntityData.BuildFactBody("a", "b", "c"));
}

// ---------------------------------------------------------------------------
// WyrdEntityData.ParseResponse
// ---------------------------------------------------------------------------

public class ParseResponseTests
{
    [Fact]
    public void Extracts_Response()
    {
        var r = WyrdEntityData.ParseResponse("{\"response\":\"The hall is quiet.\"}");
        Assert.Equal("The hall is quiet.", r);
    }

    [Fact]
    public void Empty_Returns_Fallback()
        => Assert.Equal("The spirits whisper nothing of note.",
                        WyrdEntityData.ParseResponse(string.Empty));

    [Fact]
    public void Missing_Key_Returns_Fallback()
        => Assert.Equal("The spirits whisper nothing of note.",
                        WyrdEntityData.ParseResponse("{\"status\":\"ok\"}"));

    [Fact]
    public void Empty_Value_Returns_Fallback()
        => Assert.Equal("The spirits whisper nothing of note.",
                        WyrdEntityData.ParseResponse("{\"response\":\"\"}"));
}

// ---------------------------------------------------------------------------
// WyrdEntityData.ToFacts
// ---------------------------------------------------------------------------

public class ToFactsTests
{
    [Fact]
    public void Includes_Name()
    {
        var e = new WyrdEntityData("id", "Sigrid");
        Assert.Contains(e.ToFacts(), f => f.Key == "name" && f.Value == "Sigrid");
    }

    [Fact]
    public void Includes_EntityId()
    {
        var e = new WyrdEntityData("uuid-001", "X");
        Assert.Contains(e.ToFacts(), f => f.Key == "entity_id" && f.Value == "uuid-001");
    }

    [Fact]
    public void Includes_SceneName_WhenSet()
    {
        var e = new WyrdEntityData("id", "X", sceneName: "Midgard");
        Assert.Contains(e.ToFacts(), f => f.Key == "scene" && f.Value == "Midgard");
    }

    [Fact]
    public void Omits_SceneName_WhenNull()
    {
        var e = new WyrdEntityData("id", "X");
        Assert.DoesNotContain(e.ToFacts(), f => f.Key == "scene");
    }

    [Fact]
    public void Includes_Role_WhenSet()
    {
        var e = new WyrdEntityData("id", "X", role: "seer");
        Assert.Contains(e.ToFacts(), f => f.Key == "role" && f.Value == "seer");
    }

    [Fact]
    public void Includes_CustomFacts()
    {
        var e = new WyrdEntityData("id", "X",
            customFacts: new Dictionary<string, string> { ["clan"] = "ravens" });
        Assert.Contains(e.ToFacts(), f => f.Key == "clan" && f.Value == "ravens");
    }
}

// ---------------------------------------------------------------------------
// WyrdManager
// ---------------------------------------------------------------------------

public class WyrdManagerTests
{
    [Fact]
    public void DefaultConstruction_DoesNotThrow()
    {
        var m = new WyrdManager(new WyrdUnityOptions());
        Assert.NotNull(m);
    }

    [Fact]
    public void RegisterEntity_IncrementsCount()
    {
        var m = new WyrdManager(new WyrdUnityOptions());
        m.RegisterEntity(new WyrdEntityData("sigrid", "Sigrid"));
        Assert.Equal(1, m.EntityCount);
    }

    [Fact]
    public void GetEntity_ReturnsRegistered()
    {
        var m = new WyrdManager(new WyrdUnityOptions());
        m.RegisterEntity(new WyrdEntityData("sigrid", "Sigrid"));
        Assert.NotNull(m.GetEntity("sigrid"));
    }

    [Fact]
    public void GetEntity_Unknown_ReturnsNull()
    {
        var m = new WyrdManager(new WyrdUnityOptions());
        Assert.Null(m.GetEntity("unknown"));
    }

    [Fact]
    public void RegisterEntity_EmptyEntityId_UsesNormalizedName()
    {
        var m = new WyrdManager(new WyrdUnityOptions());
        m.RegisterEntity(new WyrdEntityData("", "Sigrid Stormborn"));
        Assert.NotNull(m.GetEntity("sigrid_stormborn"));
    }

    [Fact]
    public void RegisterEntity_NullEntity_Throws()
    {
        var m = new WyrdManager(new WyrdUnityOptions());
        Assert.Throws<System.ArgumentNullException>(() => m.RegisterEntity(null));
    }

    [Fact]
    public void RegisterEntity_EmptyIdAndName_Throws()
    {
        var m = new WyrdManager(new WyrdUnityOptions());
        Assert.Throws<System.ArgumentException>(
            () => m.RegisterEntity(new WyrdEntityData("", "")));
    }

    [Fact]
    public async System.Threading.Tasks.Task QueryAsync_WhenServerDown_ReturnsFailureOrFallback()
    {
        var opts = new WyrdUnityOptions("localhost", 19999, 1) { SilentOnError = false };
        var m    = new WyrdManager(opts);
        var r    = await m.QueryAsync("sigrid", "Hello?");
        Assert.False(r.Success);
    }

    [Fact]
    public async System.Threading.Tasks.Task QueryAsync_SilentMode_ReturnsFallback()
    {
        var opts = new WyrdUnityOptions("localhost", 19999, 1) { SilentOnError = true };
        var m    = new WyrdManager(opts);
        var r    = await m.QueryAsync("sigrid", "Hello?");
        Assert.True(r.Success);
        Assert.Equal(opts.FallbackResponse, r.Response);
    }
}

// ---------------------------------------------------------------------------
// WyrdNPC
// ---------------------------------------------------------------------------

public class WyrdNPCTests
{
    [Fact]
    public void PersonaId_FromEntityId()
    {
        var npc = new WyrdNPC(new WyrdEntityData("sigrid_npc", "Sigrid"));
        Assert.Equal("sigrid_npc", npc.PersonaId);
    }

    [Fact]
    public void PersonaId_FallsBackToNormalizedName()
    {
        var npc = new WyrdNPC(new WyrdEntityData("", "Sigrid Stormborn"));
        Assert.Equal("sigrid_stormborn", npc.PersonaId);
    }

    [Fact]
    public void Register_AddsToManager()
    {
        var mgr = new WyrdManager(new WyrdUnityOptions());
        var npc = new WyrdNPC(new WyrdEntityData("sigrid_npc", "Sigrid"));
        npc.Register(mgr);
        Assert.NotNull(mgr.GetEntity("sigrid_npc"));
    }

    [Fact]
    public void Construction_NullData_Throws()
        => Assert.Throws<System.ArgumentNullException>(() => new WyrdNPC(null));
}
