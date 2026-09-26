"""World identity — the WYRD-side counterpart of Verðandi's World Registry.

Roadmap Worlds, Slice 0 (two-project slice).

Every WYRD ECS world can declare who it is in the registry of worlds: its
heimr-* id, its kind, and — the load-bearing part — its reality tag
(manifest or potential, per the MTOM Level 101 rules in mtom.py).

The handshake is a shared schema, not a shared dependency:
``WorldIdentity.registry_entry()`` emits exactly the dict that Verðandi's
``WorldRegistry.register()`` accepts. A world with no identity refuses to
emit an entry — identity is declared, never assumed.
"""
from __future__ import annotations

from dataclasses import dataclass

MANIFEST = "manifest"
POTENTIAL = "potential"
REALITIES = {MANIFEST, POTENTIAL}

# WYRD worlds always register as kind "wyrd" — the kind is the project's
# word in the shared schema.
KIND = "wyrd"


class UnidentifiedWorldError(ValueError):
    """A WYRD world was asked for its registry entry before identify()."""


@dataclass
class WorldIdentity:
    world_id: str
    kind: str = KIND
    reality: str = POTENTIAL
    description: str = ""
    source: str = "WYRD Protocol ECS world"

    def __post_init__(self) -> None:
        if not self.world_id or not self.world_id.strip():
            raise ValueError("world_id is required")
        if self.kind != KIND:
            raise ValueError(
                f"a WYRD world's kind is always {KIND!r}, got {self.kind!r}")
        if self.reality not in REALITIES:
            raise ValueError(
                f"unknown reality {self.reality!r}. Known: manifest, potential")
        if not self.source or not self.source.strip():
            raise ValueError("source is required — every world names its ground")

    def registry_entry(self) -> dict:
        """The exact dict Verðandi's WorldRegistry.register() accepts."""
        return {
            "world_id": self.world_id,
            "kind": self.kind,
            "reality": self.reality,
            "source": self.source,
            "description": self.description,
            "status": "active",
        }

    def assert_manifest(self) -> "WorldIdentity":
        """Refuse to treat this world's contents as manifest ground truth
        unless the world is tagged manifest. The WYRD-side half of the
        zero-bleed firewall."""
        if self.reality != MANIFEST:
            raise UnidentifiedWorldError(
                f"world {self.world_id!r} is tagged {self.reality!r} — "
                f"its contents cannot be read as manifest ground truth.")
        return self
