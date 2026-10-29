"""Phase E1 — integration test-honesty manifest pinning tests.

Roadmap §1.3 found the mirror-test problem: for many integrations the
"tests" re-implemented the shipped logic in Python (or inlined JS
copies) and tested the copy, so drift was undetectable and test counts
were quoted as evidence the integrations work. E1 shipped
``integrations/honesty-manifest.json`` classifying every integration
and SDK, plus honest harnesses that execute the shipped code where a
toolchain exists here.

These tests pin the manifest itself, so it cannot silently rot:

(a) the manifest parses and carries the expected schema marker;
(b) every directory under ``integrations/`` is classified, and every
    classified integration exists on disk;
(c) every entry's shipped paths exist;
(d) ``honest-executed`` entries name a harness FILE that exists, and
    other entries' harness values (when present) start with a path
    that exists;
(e) classifications are drawn only from the manifest's own vocabulary;
(f) the mirror/logic test files named by the roadmap §1.3 finding
    carry the MIRROR / LOGIC label in their own headers.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO / "integrations" / "honesty-manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_parses_with_schema_marker():
    m = _manifest()
    assert m["manifest"] == "wyrd-integration-test-honesty/1"
    assert set(m["classifications"]) == {
        "honest-executed",
        "genuine-suite-elsewhere",
        "experimental-host-untested",
    }
    assert "reproduction" in m  # exact invocations recorded durably (E1)


def test_every_integration_dir_is_classified():
    m = _manifest()
    dirs = {
        p.name
        for p in (REPO / "integrations").iterdir()
        if p.is_dir()
    }
    assert dirs == set(m["integrations"])
    for name in m["sdks"]:
        top = name.split("/")[0]
        assert (REPO / top).is_dir()


def test_shipped_paths_exist():
    m = _manifest()
    for section in ("integrations", "sdks"):
        for name, entry in m[section].items():
            assert entry["shipped"], name
            for rel in entry["shipped"]:
                assert (REPO / rel).is_file(), f"{name}: missing shipped {rel}"


def test_harness_paths_exist():
    m = _manifest()
    for section in ("integrations", "sdks"):
        for name, entry in m[section].items():
            harness = entry["honest_harness"]
            if entry["classification"] == "honest-executed":
                assert harness, f"{name}: honest-executed without a harness"
                assert (REPO / harness).is_file(), (
                    f"{name}: honest harness is not a file: {harness}"
                )
            elif harness:
                # Genuine-suite entries name a test project/dir, sometimes
                # followed by a parenthetical description.
                first_token = harness.split(" (")[0]
                assert (REPO / first_token).exists(), (
                    f"{name}: harness path missing: {first_token}"
                )


def test_classifications_use_the_manifest_vocabulary():
    m = _manifest()
    allowed = set(m["classifications"])
    for section in ("integrations", "sdks"):
        for name, entry in m[section].items():
            assert entry["classification"] in allowed, name


def test_mirror_files_carry_their_label():
    m = _manifest()
    labelled = [
        "integrations/cryengine/wyrdforge/tests/test_wyrdforge.py",
        "integrations/defold/wyrdforge/tests/test_wyrdforge.py",
        "integrations/minecraft/wyrdforge/tests/test_wyrdforge.py",
        "integrations/o3de/wyrdforge/tests/test_wyrdforge.py",
        "integrations/roblox/wyrdforge/tests/test_wyrdforge.py",
        "integrations/unreal/wyrdforge/tests/test_wyrdforge.py",
        "integrations/gamemaker/wyrdforge/tests/test_gml_logic.py",
        "integrations/godot/wyrdforge/tests/test_godot_logic.py",
        "sdk/gdscript/tests/test_gdscript_logic.py",
        "integrations/construct3/wyrdforge/tests/wyrdforge.test.js",
        "integrations/dndbeyond/wyrdforge/tests/wyrdforge.test.js",
        "integrations/foundry/wyrdforge/tests/wyrdforge.test.js",
        "integrations/owlbear/wyrdforge/tests/wyrdforge.test.js",
        "integrations/roll20/wyrdforge/tests/wyrdforge.test.js",
        "integrations/rpgmaker/wyrdforge/tests/wyrdforge.test.js",
        "integrations/sillytavern/wyrdforge/tests/wyrdforge.test.js",
    ]
    for rel in labelled:
        head = (REPO / rel).read_text(encoding="utf-8")[:1200]
        assert "MIRROR / LOGIC TESTS" in head, f"{rel} lost its E1 label"
    # The experimental entries are exactly the ones with no honest harness.
    for name, entry in m["integrations"].items():
        if entry["classification"] == "experimental-host-untested":
            assert entry["honest_harness"] is None, name


# ---------------------------------------------------------------------------
# E3 host-truth pins (roadmap §9 E3): the Unity host layer is real, the
# OpenSim region module implements IRegionModuleBase in an isolated
# deployment project, and CryEngine/O3De carry their STUB labels in every
# surface that names them. These pins keep that truth from rotting back
# into overstatement.
# ---------------------------------------------------------------------------

UNITY_PKG = REPO / "integrations" / "unity" / "wyrdforge"
OPENSIM_PKG = REPO / "integrations" / "opensim" / "wyrdforge"
CRY_PKG = REPO / "integrations" / "cryengine" / "wyrdforge"
O3DE_PKG = REPO / "integrations" / "o3de" / "wyrdforge"


def test_e3_unity_host_layer_is_real():
    # Genuine MonoBehaviours wrapping the plain-C# client.
    manager_behaviour = (
        UNITY_PKG / "Runtime" / "WyrdManagerBehaviour.cs"
    ).read_text(encoding="utf-8")
    assert "class WyrdManagerBehaviour : MonoBehaviour" in manager_behaviour
    assert "using UnityEngine;" in manager_behaviour
    npc_behaviour = (
        UNITY_PKG / "Runtime" / "WyrdNPCBehaviour.cs"
    ).read_text(encoding="utf-8")
    assert "class WyrdNPCBehaviour : MonoBehaviour" in npc_behaviour
    # The xUnit suite's Compile-Includes still name files that exist.
    tests_csproj = (
        UNITY_PKG / "WyrdForge.Unity.Tests" / "WyrdForge.Unity.Tests.csproj"
    ).read_text(encoding="utf-8")
    for name in ("WyrdUnityOptions.cs", "WyrdEntityData.cs",
                 "WyrdManager.cs", "WyrdNPC.cs"):
        assert name in tests_csproj
        assert (UNITY_PKG / "Runtime" / name).is_file()


def test_e3_unity_asmdefs_and_editor_inspector():
    runtime_asmdef = json.loads(
        (UNITY_PKG / "Runtime" / "WyrdForge.Runtime.asmdef").read_text(
            encoding="utf-8"))
    assert runtime_asmdef["name"] == "WyrdForge.Runtime"
    assert runtime_asmdef["noEngineReferences"] is False
    editor_asmdef = json.loads(
        (UNITY_PKG / "Editor" / "WyrdForge.Editor.asmdef").read_text(
            encoding="utf-8"))
    assert editor_asmdef["includePlatforms"] == ["Editor"]
    assert "WyrdForge.Runtime" in editor_asmdef["references"]
    inspector = (
        UNITY_PKG / "Editor" / "WyrdManagerBehaviourEditor.cs"
    ).read_text(encoding="utf-8")
    assert "CustomEditor(typeof(WyrdManagerBehaviour))" in inspector
    assert "HealthCheckAsync" in inspector  # an action the API supports
    # The package docs state the .meta position honestly.
    readme = (UNITY_PKG / "README.md").read_text(encoding="utf-8")
    assert ".meta" in readme and "generates" in readme


def test_e3_opensim_region_module_implements_iregionmodulebase():
    host = (
        OPENSIM_PKG / "WyrdForge.OpenSim.RegionModule"
        / "WyrdForgeRegionModuleHost.cs"
    ).read_text(encoding="utf-8")
    assert "INonSharedRegionModule" in host
    for member in ("Initialise", "Close()", "AddRegion(Scene",
                   "RemoveRegion(Scene", "RegionLoaded(Scene",
                   "ReplaceableInterface"):
        assert member in host, f"host missing IRegionModuleBase member {member}"
    assert "OnMakeRootAgent" in host and "OnChatFromClient" in host
    # The deployment project exists and references the core project...
    deploy_csproj = (
        OPENSIM_PKG / "WyrdForge.OpenSim.RegionModule"
        / "WyrdForge.OpenSim.RegionModule.csproj"
    ).read_text(encoding="utf-8")
    assert "WyrdForge.OpenSim.csproj" in deploy_csproj
    assert "OpenSim.Framework" in deploy_csproj
    # ...while the core project stays host-free (its xUnit suite's
    # ProjectReference must keep making sense).
    core_csproj = (
        OPENSIM_PKG / "WyrdForge.OpenSim" / "WyrdForge.OpenSim.csproj"
    ).read_text(encoding="utf-8")
    assert "<Reference" not in core_csproj  # no framework references at all
    assert "WyrdForge.Client.csproj" in core_csproj
    tests_csproj = (
        OPENSIM_PKG / "WyrdForge.OpenSim.Tests"
        / "WyrdForge.OpenSim.Tests.csproj"
    ).read_text(encoding="utf-8")
    assert "WyrdForge.OpenSim.csproj" in tests_csproj


def test_e3_cryengine_and_o3de_stubs_labelled_everywhere():
    # Source-file headers.
    cry_plugin = (
        CRY_PKG / "Code" / "WyrdPlugin" / "WyrdPlugin.cpp"
    ).read_text(encoding="utf-8")
    assert "STUB" in cry_plugin
    o3de_component = (
        O3DE_PKG / "Code" / "Source" / "WyrdSystemComponent.h"
    ).read_text(encoding="utf-8")
    assert "STUB" in o3de_component
    # Plugin/gem descriptor surfaces.
    cry_json = json.loads(
        (CRY_PKG / "WyrdForgePlugin.json").read_text(encoding="utf-8"))
    assert "STUB" in cry_json["Description"]
    gem_json = json.loads((O3DE_PKG / "gem.json").read_text(encoding="utf-8"))
    assert "STUB" in gem_json["Summary"]
    # Per-integration docs.
    assert "STUB" in (CRY_PKG / "TESTING.md").read_text(encoding="utf-8")
    assert "STUB" in (O3DE_PKG / "TESTING.md").read_text(encoding="utf-8")
    # The integrations overview.
    overview = (
        REPO / "docs" / "integrations" / "overview.md"
    ).read_text(encoding="utf-8")
    assert "PARTIAL STUB" in overview  # CryEngine row
    assert "STUB" in overview          # O3DE row
    # The manifest itself states the stub status in both scopes.
    m = _manifest()
    assert "STUB" in m["integrations"]["cryengine"]["scope"]
    assert "STUB" in m["integrations"]["o3de"]["scope"]


def test_e3_implemented_host_free_logic_exists():
    # CryEngine client core + O3DE helpers core are real shipped sources,
    # and the manifest's reproduction section names their harnesses.
    assert (CRY_PKG / "Code" / "WyrdPlugin" / "WyrdClientCore.cpp").is_file()
    assert (O3DE_PKG / "Code" / "Source" / "WyrdHelpersCore.cpp").is_file()
    assert (O3DE_PKG / "Code" / "Source" / "WyrdHelpers.cpp").is_file()
    m = _manifest()
    assert "cryengine_core_harness" in m["reproduction"]
    assert "o3de_honest_harness" in m["reproduction"]
    unity_scope = m["integrations"]["unity"]["scope"]
    assert "MonoBehaviour" in unity_scope and "NOT been compiled" in unity_scope
    opensim_scope = m["integrations"]["opensim"]["scope"]
    assert "IRegionModuleBase" in opensim_scope
    assert "NOT been compiled" in opensim_scope
