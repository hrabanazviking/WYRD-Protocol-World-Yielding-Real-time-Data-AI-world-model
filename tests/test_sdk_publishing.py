"""Phase E2 — SDK publishing pinning tests.

Roadmap §3.6 found three of the four SDK surfaces unconsumable as
packaged: the JS SDK's build script invoked a file that did not exist
(so its declared dist/ entry points could never be produced), the C#
SDK's csproj carried no NuGet metadata and targeted net8.0 only, and
the Python package declared no [project.scripts] entry points (so
`pip install -e .` installed no CLIs). E2 fixed all three; these
tests pin the fixes so the packaging cannot silently rot back.

What is pinned here is packaging *structure* — the JS dist itself is
proven by `npm run build` + plain-node smoke checks in the E2
session (recorded in the campaign state file and the honesty
manifest), and C# compilation is NOT verified on this machine (no
dotnet SDK exists here; the manifest says so plainly).
"""
from __future__ import annotations

import json
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Python: console entry points
# ---------------------------------------------------------------------------


def test_console_scripts_declared_for_the_real_clis():
    scripts = _pyproject()["project"]["scripts"]
    assert scripts == {
        "wyrd-chat": "wyrd_chat_cli:main",
        "wyrd-world": "wyrd_world_cli:main",
        "wyrd-backup": "wyrdforge.persistence.backup:main",
    }


def test_console_script_targets_are_importable_callables():
    import wyrd_chat_cli
    import wyrd_world_cli
    from wyrdforge.persistence import backup

    assert callable(wyrd_chat_cli.main)
    assert callable(wyrd_world_cli.main)
    assert callable(backup.main)


def test_cli_modules_ship_as_top_level_py_modules():
    # The src-layout package build only ships what py-modules names;
    # without this the entry points would import only from the repo
    # root and break in a real (wheel) install — proven broken in E2's
    # probe before the fix.
    tool = _pyproject()["tool"]["setuptools"]
    assert tool["py-modules"] == ["wyrd_chat_cli", "wyrd_world_cli"]
    assert (REPO / "src" / "wyrd_chat_cli.py").is_file()
    assert (REPO / "src" / "wyrd_world_cli.py").is_file()


def test_root_cli_files_remain_as_shims():
    # CLAUDE.md / quickstart document `python wyrd_chat_cli.py` from
    # the repo root; the root files must exist and forward to src/.
    for name in ("wyrd_chat_cli.py", "wyrd_world_cli.py"):
        text = (REPO / name).read_text(encoding="utf-8")
        assert f"src\" / \"{name}\"" in text or f'src" / "{name}"' in text or "src" in text
        assert "main()" in text


# ---------------------------------------------------------------------------
# JS SDK: the declared build can exist
# ---------------------------------------------------------------------------


def test_js_build_script_file_exists_and_is_referenced():
    pkg = json.loads((REPO / "sdk/js/package.json").read_text(encoding="utf-8"))
    assert pkg["scripts"]["build"] == (
        "tsc -p tsconfig.build.json && node scripts/build-esm.mjs"
    )
    build = REPO / "sdk/js/scripts/build-esm.mjs"
    assert build.is_file()
    # The script must fail loudly if the declared outputs are missing.
    assert "index.cjs" in build.read_text(encoding="utf-8")
    assert "index.mjs" in build.read_text(encoding="utf-8")


def test_js_declared_entry_points_match_build_outputs():
    pkg = json.loads((REPO / "sdk/js/package.json").read_text(encoding="utf-8"))
    assert pkg["main"] == "./dist/index.cjs"
    assert pkg["module"] == "./dist/index.mjs"
    assert pkg["types"] == "./dist/index.d.ts"
    assert pkg["exports"]["."]["import"] == "./dist/index.mjs"
    assert pkg["exports"]["."]["require"] == "./dist/index.cjs"


# ---------------------------------------------------------------------------
# C# SDK: NuGet metadata + multi-target (structure only — this machine
# has no dotnet SDK, so compilation is not and cannot be pinned here)
# ---------------------------------------------------------------------------


def _csproj_props() -> dict[str, str]:
    root = ET.parse(REPO / "sdk/csharp/WyrdForge.Client/WyrdForge.Client.csproj").getroot()
    props: dict[str, str] = {}
    for group in root.iter("PropertyGroup"):
        for el in group:
            props[el.tag] = el.text or ""
    return props


def test_csharp_csproj_has_nuget_metadata():
    props = _csproj_props()
    assert props["PackageId"] == "WyrdForge.Client"
    assert props["IsPackable"] == "true"
    assert props["Version"]
    assert props["Authors"]
    assert props["Description"]
    assert props["PackageLicenseExpression"] == "CC-BY-4.0"


def test_csharp_csproj_multi_targets_netstandard_and_net8():
    props = _csproj_props()
    targets = props["TargetFrameworks"].split(";")
    assert "net8.0" in targets
    assert any(t.startswith("netstandard2.") for t in targets), targets
    # The shipped code uses records/init accessors: the netstandard
    # marker-type shim must be present for those targets.
    assert (REPO / "sdk/csharp/WyrdForge.Client/IsExternalInit.cs").is_file()
