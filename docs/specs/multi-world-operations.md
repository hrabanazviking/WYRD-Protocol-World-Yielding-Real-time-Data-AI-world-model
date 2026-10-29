# Multi-World Operations — Serving, Cross-World Queries, Zero-Bleed

*Phase D5 of the WYRD advancement roadmap (§3.4 / §9 D5). The WYRD-side
operations half of world identity (`docs/specs/world-registry.md` is the
identity half).*

## What this is

Before D5, world *identity* was designed (registry, `heimr-*` ids,
manifest/potential realities) but world *operations* were not: bridges
bound one world per process instance, there was no cross-world query
surface, no concurrent multi-world serving story, and no isolation test
suite proving two live worlds in one process cannot bleed.

D5 ships `wyrdforge.services.multi_world.MultiWorldHost`:

- **Concurrent multi-world serving in one process.** The host holds
  several fully-composed world stacks — each world keeps its own
  `World`, stores, `PassiveOracle`, and `EventBus`, composed exactly as
  before D5 — and serves each world's Oracle concurrently. The host
  registry is lock-guarded; queries snapshot it and then run without
  holding the host lock, so different worlds serve in parallel and each
  query keeps its Phase B1 guarantee (one consistent snapshot under that
  world's own lock).

- **A registry-mediated, read-only cross-world query surface.**
  Registration is mediated by the identity layer: a world must have
  called `World.identify()` first (identity is declared, never assumed),
  and the host keys it by its registry entry's `world_id`. Cross-world
  queries dispatch only to the allowlisted read-only Oracle methods in
  `READ_ONLY_ORACLE_QUERIES`; any other name is refused with
  `CrossWorldWriteRefused` before any attribute is touched. The host
  exposes no method that mutates a hosted world's contents — a
  cross-world write is absent by construction. Every answer is a
  `CrossWorldResult` carrying the answering `world_id` and its declared
  `reality` tag; answers from different worlds are never merged into one
  unattributed list.

- **Zero-bleed isolation between worlds in one process.** The MTOM
  zero-bleed firewall keeps realities apart within a world; D5 extends
  the doctrine to worlds within a process. Registration refuses sharing
  that would bleed: the same World/Oracle/store instance under two
  worlds, two distinct stores opened on the same database file, or the
  same EventBus wired into two worlds. The component-type registry is
  the one process-global state, and it is shared *vocabulary* (type
  name → component class definitions), not data: component instances
  live inside one world's own dicts and cannot cross. With
  `as_manifest=True`, a cross-world query raises `ZeroBleedError`
  before any world is queried if any target world is tagged
  `potential`.

## Usage

```python
from wyrdforge.ecs.world import World
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.services.multi_world import MultiWorldHost

hall = World("heimr-samtal-hall", "The Hall")
hall.identify(reality="manifest", description="Samtal main hall")
garden = World("heimr-samtal-garden", "The Garden")
garden.identify(reality="manifest", description="Samtal garden room")

host = MultiWorldHost()
host.register(hall, memory_store=PersistentMemoryStore("hall.db"))
host.register(garden, memory_store=PersistentMemoryStore("garden.db"))

# Read-only, registry-mediated, world-attributed:
for result in host.what_is_across("yrsa"):
    print(result.world_id, result.reality, result.value)
```

## This is not federation

Multi-world operations here means several worlds in **one process**
operated by **one owner** — Samtal's many rooms in one server process,
one agent present in several regions through one host process. Nothing
here opens a socket, speaks to another server, or lets worlds owned by
different operators communicate. Federation between separate servers is
out of scope and is not built.
