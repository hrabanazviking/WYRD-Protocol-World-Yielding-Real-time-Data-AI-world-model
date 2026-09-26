# World Identity & the Registry Handshake

*Roadmap Worlds, Slice 0 — the WYRD-side half of a two-project slice.*

## What this is

Every WYRD ECS world can declare its identity in the registry of worlds:

- `world_id` — its `heimr-*` name (e.g. `heimr-wyrd-unnr`)
- `kind` — always `"wyrd"` for WYRD worlds (the project's word in the
  shared schema)
- `reality` — `manifest` or `potential`, per the MTOM Level 101 rules
  (`mtom.py`). A world modeling imagined or hypothetical entities is
  `potential`; a world modeling manifest entities may be `manifest`.
  The tag is declared by whoever identifies the world — never assumed.

## Usage

```python
from wyrdforge.ecs.world import World

world = World("heimr-wyrd-unnr", "Unnr's mirror world")
world.identify(
    reality="potential",
    description="WYRD ECS world modeling the AI as a manifest entity",
)

# The handshake dict — exactly what Verðandi's WorldRegistry.register()
# accepts. Raises UnidentifiedWorldError until identify() is called.
entry = world.registry_entry()
```

## The firewall, WYRD-side

`WorldIdentity.assert_manifest()` refuses to let a `potential` world's
contents be treated as manifest ground truth. The Verðandi-side
counterpart is `WorldRegistry.assert_no_bleed(world_id, as_manifest=True)`.
Both halves were verified against each other live in Slice 0: a WYRD
world's entry registers directly into a Verðandi registry, and the
firewall raises on both sides.

## Design notes

- The handshake is a shared **schema**, not a shared dependency — neither
  project imports the other.
- `identify()` is idempotent; re-identifying updates the identity.
- Additive only: existing `World` construction is unchanged; `identity`
  starts as `None`.
