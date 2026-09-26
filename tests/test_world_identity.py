"""Tests for world_identity.py + World.identify() (Roadmap Worlds, Slice 0).

The WYRD-side half of the two-project handshake: a WYRD world's identity
emits exactly the dict Verðandi's WorldRegistry.register() accepts, and the
reality tag is enforced on both sides of the bridge.
"""
import pytest

from wyrdforge.ecs.components.world_identity import (
    MANIFEST, POTENTIAL, UnidentifiedWorldError, WorldIdentity,
)
from wyrdforge.ecs.world import World


def test_identify_tags_world():
    world = World("heimr-wyrd-unnr", "Unnr's mirror world")
    identity = world.identify(reality="potential",
                              description="models the AI as a manifest entity")
    assert identity.world_id == "heimr-wyrd-unnr"
    assert identity.kind == "wyrd"
    assert identity.reality == "potential"


def test_registry_entry_matches_handshake_schema():
    world = World("heimr-wyrd-unnr")
    world.identify(reality="potential", description="d", source="s")
    entry = world.registry_entry()
    assert entry == {
        "world_id": "heimr-wyrd-unnr",
        "kind": "wyrd",
        "reality": "potential",
        "source": "s",
        "description": "d",
        "status": "active",
    }


def test_registry_entry_requires_identify():
    world = World("heimr-wyrd-unnr")
    with pytest.raises(UnidentifiedWorldError, match="call identify"):
        world.registry_entry()


def test_invalid_reality_rejected():
    world = World("heimr-wyrd-unnr")
    with pytest.raises(ValueError, match="unknown reality"):
        world.identify(reality="liminal")


def test_kind_is_always_wyrd():
    with pytest.raises(ValueError, match="always 'wyrd'"):
        WorldIdentity(world_id="x", kind="ttrpg")


def test_assert_manifest_passes_for_manifest_world():
    identity = WorldIdentity(world_id="heimr-wyrd-unnr", reality=MANIFEST)
    assert identity.assert_manifest() is identity


def test_assert_manifest_raises_for_potential_world():
    identity = WorldIdentity(world_id="heimr-wyrd-unnr", reality=POTENTIAL)
    with pytest.raises(UnidentifiedWorldError, match="cannot be read as manifest"):
        identity.assert_manifest()


def test_identify_is_idempotent():
    world = World("heimr-wyrd-unnr")
    first = world.identify(reality="potential")
    second = world.identify(reality="manifest", description="now modeling manifest")
    assert second.reality == "manifest"
    assert world.registry_entry()["reality"] == "manifest"
    assert first is not second
