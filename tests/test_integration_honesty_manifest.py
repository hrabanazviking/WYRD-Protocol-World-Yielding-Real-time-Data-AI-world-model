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
