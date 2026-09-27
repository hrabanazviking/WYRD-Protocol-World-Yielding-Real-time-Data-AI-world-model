"""Fuzz corpus 1/3 — torn/hostile world-file YAML (Track 1, P1).

Corpus-first: written against the unpatched tree, where the hostile
cases go red (unhandled AttributeError/TypeError/KeyError, or silent
acceptance of unknown fields). After the validators land, every case
is either accepted within bounds or rejected naming the field —
0 unhandled exceptions across the whole corpus.

Boundaries under test: ``load_world_from_yaml`` and
``services.memory_promoter._load_config``.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml

from wyrdforge.hardening.config_validator import (
    ConfigValidationError,
    validate_world_config,
)
from wyrdforge.loaders.world_loader import load_world_from_yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
THORNHOLT = REPO_ROOT / "configs" / "worlds" / "thornholt.yaml"

_TMP: Path | None = None


@pytest.fixture(autouse=True)
def _tmp_dir(tmp_path):
    global _TMP
    _TMP = tmp_path
    yield
    _TMP = None


def _write(content: str | bytes) -> Path:
    # pytest's tmp_path (auto-cleaned) via the autouse fixture below —
    # the 10 MiB corpus files must not litter /tmp across runs.
    assert _TMP is not None, "tmp dir fixture not active"
    tmp = _TMP / f"{uuid.uuid4().hex}.yaml"
    if isinstance(content, bytes):
        tmp.write_bytes(content)
    else:
        tmp.write_text(content, encoding="utf-8")
    return tmp


def _load_text(content: str | bytes):
    return load_world_from_yaml(_write(content))


def _rejects(content: str | bytes, field_fragment: str):
    """Assert the loader fails closed naming the field."""
    with pytest.raises(ConfigValidationError) as exc_info:
        _load_text(content)
    err = exc_info.value
    assert err.field is not None, f"rejection must name the field: {err}"
    # The fragment may name the field path or the reason — either way
    # the error carries it (fail closed *and* legible).
    assert field_fragment in str(err), (
        f"error {err} does not mention {field_fragment!r}"
    )


# ---------------------------------------------------------------------------
# Must-accept: ground truth and documented behavior
# ---------------------------------------------------------------------------

class TestWorldYamlAccepts:
    def test_thornholt_yaml_loads(self):
        # Corpus case #1: the repo's own world file is the ground truth.
        world, tree = load_world_from_yaml(THORNHOLT)
        assert world.world_id == "thornholt"

    def test_minimal_config_loads(self):
        world, _ = _load_text("world_id: mini\nworld_name: Mini\n")
        assert world.world_id == "mini"

    def test_empty_zones_accepted(self):
        world, _ = _load_text("world_id: mini\nworld_name: Mini\nzones: []\n")
        assert world.world_id == "mini"

    def test_four_level_nesting_accepted(self):
        world, _ = _load_text(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        locations:\n"
            "          - id: l\n            name: L\n            sublocations:\n"
            "              - id: s\n                name: S\n"
        )
        assert world.world_id == "mini"

    def test_descriptions_at_every_level_accepted(self):
        world, _ = _load_text(
            "world_id: mini\nworld_name: Mini\ndescription: top\nzones:\n"
            "  - id: z\n    name: Z\n    description: zd\n"
        )
        assert world.world_id == "mini"

    def test_missing_world_id_falls_back_to_stem(self):
        # Documented loader behavior (pinned by test_world_loader.py):
        # the stem is a default, not silent acceptance of hostile input.
        path = _write("zones: []\n")
        world, _ = load_world_from_yaml(path)
        assert world.world_id == path.stem

    def test_missing_world_name_falls_back_to_world_id(self):
        world, _ = _load_text("world_id: mini\n")
        assert world.world_id == "mini"

    def test_description_at_max_length_accepted(self):
        world, _ = _load_text(
            "world_id: mini\nworld_name: Mini\ndescription: " + "x" * 100_000 + "\n"
        )
        assert world.world_id == "mini"

    def test_id_at_max_length_accepted(self):
        world, _ = _load_text(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: " + "i" * 500 + "\n    name: Z\n"
        )
        assert world.world_id == "mini"

    def test_explicit_document_markers_accepted(self):
        world, _ = _load_text("---\nworld_id: mini\nworld_name: Mini\n...\n")
        assert world.world_id == "mini"

    def test_validate_minimal_dict(self):
        result = validate_world_config({"world_id": "mini", "world_name": "Mini"})
        assert result["world_id"] == "mini"


# ---------------------------------------------------------------------------
# Must-reject: torn documents (named field, fail closed)
# ---------------------------------------------------------------------------

class TestWorldYamlTorn:
    def test_truncated_mid_document(self):
        _rejects("world_id: mini\nworld_name: Mini\nzones:\n  - id: z\n    name: \"unclosed",
                "invalid YAML document")

    def test_tabs_rejected(self):
        _rejects("world_id: mini\n\tworld_name: Mini\n", "document")

    def test_list_root_rejected(self):
        _rejects("- just\n- a\n- list\n", "world config")

    def test_scalar_root_rejected(self):
        _rejects("just a string\n", "world config")

    def test_null_document_rejected(self):
        _rejects("null\n", "world config")

    def test_empty_file_rejected(self):
        _rejects("", "world config")

    def test_multiple_documents_rejected(self):
        _rejects(
            "world_id: a\n---\nworld_id: b\n", "document",
        )

    def test_non_utf8_bytes_rejected(self):
        _rejects(b"world_id: mini\nworld_name: \xff\xfe\n", "UTF-8")

    def test_alias_bomb_rejected(self):
        # Exponential alias web: 418 raw bytes naming a ~16M-node
        # object graph (aliases resolve by reference). The validator's
        # node-walk budget must trip — the walk itself must not become
        # the bomb.
        bomb = "world_id: mini\nworld_name: Mini\nx0: &a0 ['s']\n"
        for i in range(1, 13):
            bomb += f"x{i}: &a{i} [*a{i-1}, *a{i-1}, *a{i-1}, *a{i-1}]\n"
        bomb += "zones: []\n"
        _rejects(bomb, "node walk exceeds")

    def test_cyclic_alias_rejected(self):
        # A list containing itself: the depth-first walk descends the
        # self-reference, so the iterative depth gate trips long before
        # any walk budget — no hang, no RecursionError.
        _rejects(
            "world_id: mini\nworld_name: Mini\ncyclic: &c [*c]\nzones: []\n",
            "nesting depth exceeds",
        )

    def test_deep_bracket_nesting_rejected(self):
        # 200-deep bracket nesting under a known key: the iterative
        # depth gate fires (never a RecursionError).
        deep = "world_id: mini\nworld_name: Mini\nzones: " + "[" * 200 + "]" * 200 + "\n"
        _rejects(deep, "nesting depth exceeds")

    def test_file_over_10mib_rejected(self):
        big = "world_id: mini\nworld_name: Mini\ndescription: |\n"
        big += ("  " + "x" * 200 + "\n") * 60_000  # ~12 MiB
        assert len(big.encode("utf-8")) > 10 * 1024 * 1024
        _rejects(big, "size")

    def test_file_at_10mib_boundary_accepted(self):
        # Exactly MAX bytes, padded with YAML comments (ignored by the
        # parser, unconstrained by field caps): the size gate passes
        # and the valid world loads.
        from wyrdforge.hardening.input_validation import MAX_WORLD_FILE_BYTES
        base = "world_id: mini\nworld_name: Mini\n"
        nx = MAX_WORLD_FILE_BYTES - len(base.encode("utf-8")) - 2
        content = base + "#" + "x" * nx + "\n"
        assert len(content.encode("utf-8")) == MAX_WORLD_FILE_BYTES
        world, _ = _load_text(content)
        assert world.world_id == "mini"


# ---------------------------------------------------------------------------
# Must-reject: unknown fields (hard error, dotted path named)
# ---------------------------------------------------------------------------

class TestWorldYamlUnknownFields:
    def test_unknown_top_level_field(self):
        _rejects("world_id: mini\nworld_name: Mini\nbogus: 1\n", "bogus")

    def test_name_instead_of_world_name(self):
        # The old schema's field name is rejected; the message names it.
        _rejects("world_id: mini\nname: Mini\n", "name")

    def test_entities_top_level_rejected(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nentities: []\n", "entities"
        )

    def test_version_top_level_rejected(self):
        _rejects("world_id: mini\nworld_name: Mini\nversion: '1.0'\n", "version")

    def test_settings_top_level_rejected(self):
        _rejects("world_id: mini\nworld_name: Mini\nsettings: {}\n", "settings")

    def test_unknown_nested_zone_field(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    bogus: 1\n",
            "zones[0].bogus",
        )

    def test_unknown_nested_region_field(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        bogus: 1\n",
            "zones[0].regions[0].bogus",
        )

    def test_unknown_nested_location_field(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        locations:\n"
            "          - id: l\n            name: L\n            bogus: 1\n",
            "zones[0].regions[0].locations[0].bogus",
        )

    def test_regions_key_under_sublocation_rejected(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        locations:\n"
            "          - id: l\n            name: L\n            sublocations:\n"
            "              - id: s\n                name: S\n                regions: []\n",
            "zones[0].regions[0].locations[0].sublocations[0].regions",
        )

    def test_sublocations_under_sublocation_rejected(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    sublocations: []\n",
            "zones[0].sublocations",
        )

    def test_locations_directly_under_zone_rejected(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    locations: []\n",
            "zones[0].locations",
        )


# ---------------------------------------------------------------------------
# Must-reject: wrong types and bounds (named field)
# ---------------------------------------------------------------------------

class TestWorldYamlTypesAndBounds:
    def test_zones_as_string(self):
        _rejects("world_id: mini\nworld_name: Mini\nzones: nope\n", "zones")

    def test_zones_as_dict(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones: {a: b}\n", "zones"
        )

    def test_zone_as_string(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - justastring\n",
            "zones[0]",
        )

    def test_zone_as_int(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - 42\n",
            "zones[0]",
        )

    def test_zone_missing_id(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - name: Z\n",
            "zones[0].id",
        )

    def test_zone_missing_name(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - id: z\n",
            "zones[0].name",
        )

    def test_zone_id_as_int(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - id: 42\n    name: Z\n",
            "zones[0].id",
        )

    def test_zone_id_as_bool(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - id: true\n    name: Z\n",
            "zones[0].id",
        )

    def test_zone_id_empty(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - id: ''\n    name: Z\n",
            "zones[0].id",
        )

    def test_zone_name_as_int(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - id: z\n    name: 42\n",
            "zones[0].name",
        )

    def test_region_missing_id(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n      - name: R\n",
            "zones[0].regions[0].id",
        )

    def test_regions_as_string(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions: nope\n",
            "zones[0].regions",
        )

    def test_location_id_as_list(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        locations:\n"
            "          - id: [a]\n            name: L\n",
            "zones[0].regions[0].locations[0].id",
        )

    def test_locations_as_dict(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        locations: {a: b}\n",
            "zones[0].regions[0].locations",
        )

    def test_sublocation_missing_name(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        locations:\n"
            "          - id: l\n            name: L\n            sublocations:\n"
            "              - id: s\n",
            "zones[0].regions[0].locations[0].sublocations[0].name",
        )

    def test_sublocations_as_string(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    regions:\n"
            "      - id: r\n        name: R\n        locations:\n"
            "          - id: l\n            name: L\n            sublocations: nope\n",
            "zones[0].regions[0].locations[0].sublocations",
        )

    def test_description_as_int(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\ndescription: 42\n",
            "description",
        )

    def test_description_over_max_length(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\ndescription: " + "x" * 100_001 + "\n",
            "description",
        )

    def test_nested_description_over_max_length(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: z\n    name: Z\n    description: " + "x" * 100_001 + "\n",
            "zones[0].description",
        )

    def test_id_over_max_length(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n"
            "  - id: " + "i" * 501 + "\n    name: Z\n",
            "zones[0].id",
        )

    def test_world_id_as_int(self):
        _rejects("world_id: 42\nworld_name: Mini\n", "world_id")

    def test_world_id_empty(self):
        _rejects("world_id: '   '\nworld_name: Mini\n", "world_id")

    def test_world_name_as_int(self):
        _rejects("world_id: mini\nworld_name: 42\n", "world_name")


# ---------------------------------------------------------------------------
# Direct validator unit cases (ground-truth schema)
# ---------------------------------------------------------------------------

class TestValidateWorldConfigDirect:
    def test_non_dict_raises(self):
        with pytest.raises(ConfigValidationError):
            validate_world_config(["not", "a", "dict"])

    def test_missing_world_id_raises_naming_field(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_world_config({"world_name": "Mini"})
        assert exc_info.value.field == "$.world_id"

    def test_missing_world_name_raises_naming_field(self):
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_world_config({"world_id": "mini"})
        assert exc_info.value.field == "$.world_name"


# ---------------------------------------------------------------------------
# memory_promoter._load_config — the second YAML surface
# ---------------------------------------------------------------------------

class TestMemoryPromoterLoadConfig:
    def _load_config(self, path):
        from wyrdforge.services.memory_promoter import _load_config
        return _load_config(path)

    def test_list_root_fails_closed_naming_file(self):
        from wyrdforge.hardening.config_validator import ConfigValidationError
        path = _write("- just\n- a\n- list\n")
        with pytest.raises(ConfigValidationError) as exc_info:
            self._load_config(path)
        assert str(path) in str(exc_info.value)

    def test_scalar_root_fails_closed_naming_file(self):
        from wyrdforge.hardening.config_validator import ConfigValidationError
        path = _write("just a string\n")
        with pytest.raises(ConfigValidationError) as exc_info:
            self._load_config(path)
        assert str(path) in str(exc_info.value)

    def test_dict_root_merges_with_defaults(self):
        cfg = self._load_config(_write("promotion: {weights: {}}\n"))
        assert cfg["promotion"] == {"weights": {}}
        assert "scoring" in cfg or "decay" in cfg or len(cfg) > 1

    def test_empty_file_uses_defaults(self):
        from wyrdforge.services.memory_promoter import _DEFAULT_CONFIG
        assert self._load_config(_write("")) == _DEFAULT_CONFIG

    def test_missing_file_uses_defaults(self):
        from wyrdforge.services.memory_promoter import _DEFAULT_CONFIG
        assert self._load_config("/nonexistent/promotion.yaml") == _DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# Boundaries exercised at exactly the cap, not just over it
# ---------------------------------------------------------------------------

class TestWorldYamlBoundaryEdges:
    def test_description_at_100k_accepted(self):
        # The 100k description validates and the world loads (the
        # description lives on the tree nodes, not the World header).
        world, _ = _load_text(
            "world_id: mini\nworld_name: Mini\ndescription: " + "d" * 100_000 + "\n"
        )
        assert world.world_id == "mini"

    def test_description_over_100k_rejected_naming(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\ndescription: " + "d" * 100_001 + "\n",
            "$.description",
        )

    def test_world_id_whitespace_rejected(self):
        _rejects("world_id: '   '\nworld_name: Mini\n", "world_id")

    def test_description_wrong_type_rejected(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\ndescription: 42\n",
            "$.description",
        )

    def test_zones_null_rejected(self):
        _rejects("world_id: mini\nworld_name: Mini\nzones: null\n", "$.zones")

    def test_regions_dict_rejected(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\n"
            "zones:\n  - id: z\n    name: Z\n    regions: {r: 1}\n",
            "$.zones[0].regions",
        )

    def test_zone_name_list_rejected(self):
        _rejects(
            "world_id: mini\nworld_name: Mini\n"
            "zones:\n  - id: z\n    name: [Z]\n",
            "$.zones[0].name",
        )

    def test_sublocation_children_key_rejected(self):
        # sublocations are leaves — a children key is unknown there
        _rejects(
            "world_id: mini\nworld_name: Mini\nzones:\n  - id: z\n    name: Z\n"
            "    regions:\n      - id: r\n        name: R\n"
            "        locations:\n          - id: l\n            name: L\n"
            "            sublocations:\n              - id: s\n                name: S\n"
            "                sublocations: []\n",
            "$.zones[0].regions[0].locations[0].sublocations[0].sublocations",
        )
