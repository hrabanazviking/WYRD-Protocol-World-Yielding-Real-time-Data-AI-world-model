"""MultiWorldHost — multi-world operations (Phase D5, roadmap §3.4 / §9).

World *identity* existed before D5 (``World.identify()`` /
``World.registry_entry()``, ``docs/specs/world-registry.md``): a world
can declare its ``heimr-*`` id and its reality tag. World *operations*
did not: bridges bound one world per process instance, there was no
cross-world query surface, no concurrent multi-world serving story,
and no test suite proving two live worlds in one process cannot bleed.

This module is the operations half, built only from machinery that
already exists per world — each hosted world keeps its OWN
``World`` + stores + ``PassiveOracle`` + ``EventBus`` exactly as they
are composed today. The host adds three things:

1. **Concurrent multi-world serving in one process.** A
   :class:`MultiWorldHost` holds several fully-composed world stacks
   and serves each one's Oracle concurrently. The host's own
   registry is guarded by one re-entrant lock; queries snapshot the
   registry under that lock and then run each Oracle query WITHOUT
   holding it, so worlds are served in parallel and every Oracle
   keeps its Phase B1 guarantees (each query runs under its own
   world's lock, on a consistent snapshot of that world).

2. **A registry-mediated, READ-ONLY cross-world query surface.**
   Registration is mediated by the identity layer: a world must have
   declared its identity via ``World.identify()`` before it can be
   hosted (identity is declared, never assumed — the world-registry
   doctrine), and the host keys the world by the ``world_id`` in its
   registry entry. Cross-world queries dispatch ONLY to an allowlist
   of read-only ``PassiveOracle`` methods
   (:data:`READ_ONLY_ORACLE_QUERIES`); any other name — a World
   mutator, a store write, a private helper — is refused with
   :class:`CrossWorldWriteRefused` before any attribute is touched.
   The host exposes no method that mutates a hosted world's
   contents, so a cross-world write is absent by construction, not
   merely checked at runtime. Every answer is returned as a
   :class:`CrossWorldResult` carrying the ``world_id`` AND the
   ``reality`` tag of the world it came from; answers from different
   worlds are NEVER merged into one unattributed list.

3. **Zero-bleed isolation, enforced at registration.** The MTOM
   zero-bleed firewall (``ecs/components/mtom.py``) keeps realities
   apart *within* a world; D5 extends that doctrine to worlds within
   a process. Registration refuses any sharing that would bleed:

   * the same ``World`` instance, Oracle instance, or memory-store
     instance under two worlds;
   * two distinct memory stores opened on the SAME database file
     (disk-level bleed — the stores would share one truth on disk
     while pretending to be two worlds);
   * the same ``EventBus`` instance wired into two worlds (bus
     traffic is world traffic; two worlds on one bus would hear
     each other).

   The one piece of process-global state the inspection found —
   the component-type registry in ``ecs/component.py`` — is shared
   *vocabulary*, not bleed: it maps type names to component CLASSES
   (definitions), while every component INSTANCE lives inside one
   world's own dicts. Two worlds may both carry a ``name``
   component; the values cannot cross. All other per-world state
   (World indexes, Yggdrasil trees, stores, bond services, buses,
   TurnLoops) is instance state with no module-level singleton —
   verified by the isolation suite in
   ``tests/test_multi_world_operations.py``, which exercises
   entities, components, memories, bonds, events, and fate threads
   across two live worlds, including under concurrent load.

   The reality firewall applies across worlds too: a cross-world
   query run with ``as_manifest=True`` raises
   :class:`~wyrdforge.ecs.components.mtom.ZeroBleedError` before any
   world is queried if ANY target world is tagged ``potential`` —
   a potential world's contents can never be read as manifest
   ground truth by laundering them through a multi-world query.

Scope law — this is NOT federation. Multi-world operations here
means several worlds in ONE process operated by ONE owner (Samtal's
many rooms in one server process; one agent present in several
regions through one host process). Nothing in this module opens a
socket, speaks to another server, or lets worlds owned by different
operators communicate. Federation between separate servers is out
of scope by the owner's standing ruling and is not built here.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from wyrdforge.ecs.components.mtom import ZeroBleedError
from wyrdforge.ecs.components.world_identity import UnidentifiedWorldError
from wyrdforge.ecs.world import World
from wyrdforge.models.common import StrictModel
from wyrdforge.oracle.passive_oracle import PassiveOracle

#: The ONLY Oracle methods the cross-world surface will dispatch to.
#: Every entry is a read-only PassiveOracle query (the Oracle is
#: read-only by construction — it never mutates world state and never
#: writes memory records). Anything not listed here is refused as a
#: cross-world write attempt, including names that exist on World,
#: on the stores, or on the host itself.
READ_ONLY_ORACLE_QUERIES = frozenset({
    "where_is",
    "who_is_here",
    "what_is",
    "get_fact",
    "get_facts",
    "get_relations",
    "get_nearby",
    "get_position",
    "within_radius",
    "within_radius_of_point",
    "nearest",
    "nearest_to_point",
    "distance_between",
    "get_engagement",
    "threats_to",
    "threats_perceived_by",
    "combatants_within",
    "range_band_between",
    "get_sensation",
    "get_sensations",
    "get_reported_sensations",
    "recent_observations",
    "recall_by_salience",
    "get_wyrd_threads",
    "get_thread_between",
    "get_convergences",
    "search_facts",
    "build_context_packet",
})


class CrossWorldWriteRefused(ValueError):
    """A cross-world query named a non-read-only operation.

    The cross-world surface is read-only by construction: the only
    dispatchable names are :data:`READ_ONLY_ORACLE_QUERIES`. Naming
    anything else — a World mutator, a store write, a private
    method — raises this before any attribute is touched, so the
    refusal can never itself mutate a world.
    """


class WorldSharingError(ValueError):
    """Registration would share state between two hosted worlds.

    Sharing a World / Oracle / store instance, a store database
    file, or an EventBus between two worlds in one process is the
    bleed the zero-bleed doctrine forbids, so it is refused at
    registration time, before the second world is hosted.
    """


class UnregisteredWorldError(KeyError):
    """A query or lookup named a world_id the host does not serve."""


class CrossWorldResult(StrictModel):
    """One world's answer to a cross-world query, world-attributed.

    ``value`` is exactly what that world's own Oracle returned
    (a result model, a list of them, a record, or None) — carried
    verbatim, never merged with another world's answer. ``reality``
    is the answering world's declared MTOM reality tag, so a
    ``potential`` world's answer can never pose as manifest truth.
    """

    world_id: str
    reality: str
    query: str
    value: Any = None


class WorldServingSummary(StrictModel):
    """One hosted world as the host reports it (operator surface)."""

    world_id: str
    world_name: str
    kind: str
    reality: str
    description: str
    entity_count: int


@dataclass
class _HostedWorld:
    world: World
    oracle: PassiveOracle
    reality: str


class MultiWorldHost:
    """Serve several identified worlds concurrently in one process.

    Operator surface (register / unregister / look up a world's own
    stack) plus the read-only cross-world query surface. The host
    itself holds no world content: every entity, component, memory,
    bond, and event lives inside exactly one hosted world's own
    stack, exactly as composed before D5.

    Thread-safety: the registry dict is guarded by one RLock.
    Registration and unregistration are atomic; queries snapshot
    their target entries under the lock and release it before any
    Oracle call, so a slow query never blocks another world's
    serving and concurrent queries to DIFFERENT worlds proceed in
    parallel (queries to the same world serialise on that world's
    own B1 lock, inside its Oracle).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._worlds: dict[str, _HostedWorld] = {}

    # ------------------------------------------------------------------
    # Operator surface: registration (registry-mediated)
    # ------------------------------------------------------------------

    def register(
        self,
        world: World,
        oracle: PassiveOracle | None = None,
        *,
        memory_store: Any | None = None,
        yggdrasil: Any | None = None,
        bond_service: Any | None = None,
    ) -> str:
        """Host ``world`` and return its registered ``world_id``.

        The world must already carry a declared identity
        (``world.identify(...)``) — the registry entry IS the
        mediation: the host keys the world by the entry's
        ``world_id`` and tags every cross-world answer with the
        entry's ``reality``. An unidentified world is refused with
        :class:`UnidentifiedWorldError`.

        Pass a pre-built ``oracle`` for the world, OR a
        ``memory_store`` (plus optional ``yggdrasil`` /
        ``bond_service``) and the host composes the Oracle exactly
        as existing bridges do. Passing neither raises ValueError.

        Zero-bleed registration guards (see module docstring):
        duplicate ``world_id``, a shared World / Oracle / store
        instance, a shared store database file, or a shared
        EventBus all raise :class:`WorldSharingError` and host
        nothing.
        """
        entry = world.registry_entry()  # raises UnidentifiedWorldError
        world_id = entry["world_id"]
        if oracle is None:
            if memory_store is None:
                raise ValueError(
                    "register() requires a pre-built oracle= or a "
                    "memory_store= to compose one from"
                )
            oracle = PassiveOracle(
                world, memory_store, yggdrasil=yggdrasil,
                bond_service=bond_service,
            )
        elif not isinstance(oracle, PassiveOracle):
            raise TypeError(
                f"oracle must be a PassiveOracle, got {type(oracle).__name__}"
            )

        store = getattr(oracle, "_store", None)
        store_path = getattr(store, "_db_path", None)
        world_bus = getattr(world, "_bus", None)
        store_bus = getattr(store, "_bus", None)

        with self._lock:
            if world_id in self._worlds:
                raise WorldSharingError(
                    f"world_id {world_id!r} is already hosted — two "
                    "worlds under one id would make every cross-world "
                    "answer ambiguous"
                )
            for other_id, hosted in self._worlds.items():
                other_store = getattr(hosted.oracle, "_store", None)
                if hosted.world is world:
                    raise WorldSharingError(
                        f"this World instance is already hosted as {other_id!r}"
                    )
                if hosted.oracle is oracle:
                    raise WorldSharingError(
                        f"this Oracle instance already serves {other_id!r}"
                    )
                if store is not None and other_store is store:
                    raise WorldSharingError(
                        f"this memory store already serves {other_id!r} — "
                        "one store cannot be two worlds' memory"
                    )
                other_path = getattr(other_store, "_db_path", None)
                if (
                    store_path is not None
                    and other_path is not None
                    and str(store_path) == str(other_path)
                ):
                    raise WorldSharingError(
                        f"memory store file {store_path} already serves "
                        f"{other_id!r} — two stores on one file are one "
                        "memory on disk, whatever the objects pretend"
                    )
                for bus, other_bus, what in (
                    (world_bus, getattr(hosted.world, "_bus", None), "world bus"),
                    (store_bus, getattr(other_store, "_bus", None), "store bus"),
                ):
                    if bus is not None and other_bus is bus:
                        raise WorldSharingError(
                            f"this {what} already serves {other_id!r} — "
                            "two worlds on one EventBus would hear each "
                            "other's events"
                        )
            self._worlds[world_id] = _HostedWorld(
                world=world, oracle=oracle, reality=str(entry["reality"]),
            )
        return world_id

    def unregister(self, world_id: str) -> None:
        """Stop hosting a world. Raises if it was never hosted."""
        with self._lock:
            if self._worlds.pop(world_id, None) is None:
                raise UnregisteredWorldError(
                    f"world {world_id!r} is not hosted by this host"
                )

    def world_ids(self) -> list[str]:
        """The hosted world_ids, sorted (deterministic)."""
        with self._lock:
            return sorted(self._worlds)

    def registry_entries(self) -> list[dict]:
        """Every hosted world's registry entry, sorted by world_id.

        This is the mediation layer made visible: the same handshake
        dicts ``World.registry_entry()`` emits, one per hosted world.
        """
        with self._lock:
            hosted = [self._worlds[k] for k in sorted(self._worlds)]
        return [h.world.registry_entry() for h in hosted]

    def describe_worlds(self) -> list[WorldServingSummary]:
        """Operator summary of every hosted world, sorted by id."""
        with self._lock:
            hosted = [(k, self._worlds[k]) for k in sorted(self._worlds)]
        summaries: list[WorldServingSummary] = []
        for world_id, h in hosted:
            entry = h.world.registry_entry()
            summaries.append(WorldServingSummary(
                world_id=world_id,
                world_name=h.world.world_name,
                kind=str(entry["kind"]),
                reality=h.reality,
                description=str(entry["description"]),
                entity_count=h.world.entity_count(),
            ))
        return summaries

    def world(self, world_id: str) -> World:
        """The hosted world's own World (operator access).

        This hands the OPERATOR — the one owner of this process —
        the world stack they themselves registered, e.g. to wire a
        bridge to it. It is not part of the cross-world query
        surface: holding this reference is holding that one world,
        and nothing here reaches any other hosted world.
        """
        return self._hosted(world_id).world

    def oracle(self, world_id: str) -> PassiveOracle:
        """The hosted world's own read-only Oracle (operator access)."""
        return self._hosted(world_id).oracle

    def _hosted(self, world_id: str) -> _HostedWorld:
        with self._lock:
            hosted = self._worlds.get(world_id)
        if hosted is None:
            raise UnregisteredWorldError(
                f"world {world_id!r} is not hosted by this host"
            )
        return hosted

    def _targets(
        self, world_ids: list[str] | None
    ) -> list[tuple[str, _HostedWorld]]:
        with self._lock:
            if world_ids is None:
                keys = sorted(self._worlds)
            else:
                keys = list(world_ids)
                for key in keys:
                    if key not in self._worlds:
                        raise UnregisteredWorldError(
                            f"world {key!r} is not hosted by this host"
                        )
            return [(k, self._worlds[k]) for k in keys]

    # ------------------------------------------------------------------
    # Cross-world query surface (READ-ONLY, registry-mediated)
    # ------------------------------------------------------------------

    def query_across(
        self,
        query: str,
        *args: Any,
        world_ids: list[str] | None = None,
        as_manifest: bool = False,
        **kwargs: Any,
    ) -> list[CrossWorldResult]:
        """Run one read-only Oracle query across hosted worlds.

        ``query`` must name a method in
        :data:`READ_ONLY_ORACLE_QUERIES`; anything else raises
        :class:`CrossWorldWriteRefused` before any world is touched.
        Each target world's own Oracle runs the query (under that
        world's B1 lock, as always) and the answers come back as one
        :class:`CrossWorldResult` per world, in ``world_ids`` order
        (sorted order when ``world_ids`` is None) — attributed,
        reality-tagged, never merged.

        ``as_manifest=True`` applies the MTOM zero-bleed firewall
        across worlds: if ANY target world is tagged ``potential``,
        :class:`ZeroBleedError` is raised before ANY world is
        queried — no partial manifest answer can leak a potential
        world's contents.
        """
        if query not in READ_ONLY_ORACLE_QUERIES:
            raise CrossWorldWriteRefused(
                f"{query!r} is not a read-only Oracle query — the "
                "cross-world surface dispatches only to "
                "READ_ONLY_ORACLE_QUERIES and can never write across worlds"
            )
        targets = self._targets(world_ids)
        if as_manifest:
            for world_id, hosted in targets:
                if hosted.reality != "manifest":
                    raise ZeroBleedError(
                        f"Zero-bleed violation in cross-world query "
                        f"{query!r}: world {world_id!r} is tagged "
                        f"{hosted.reality!r} — its contents cannot be "
                        "read as manifest ground truth. Query it "
                        "without as_manifest (its answers stay "
                        "reality-tagged) or target manifest worlds only."
                    )
        results: list[CrossWorldResult] = []
        for world_id, hosted in targets:
            value = getattr(hosted.oracle, query)(*args, **kwargs)
            results.append(CrossWorldResult(
                world_id=world_id, reality=hosted.reality,
                query=query, value=value,
            ))
        return results

    # Typed wrappers — the common cross-world questions, each a thin
    # named face on query_across (same refusal + firewall semantics).

    def what_is_across(
        self, entity_id: str, *, world_ids: list[str] | None = None,
        as_manifest: bool = False,
    ) -> list[CrossWorldResult]:
        """``what_is`` in every target world where the entity exists.

        Worlds where the entity does not exist contribute NO result
        — absence in a world is not an answer from it. The same
        entity_id in two worlds yields two attributed results with
        each world's own snapshot; neither overwrites the other.
        """
        results = self.query_across(
            "what_is", entity_id, world_ids=world_ids,
            as_manifest=as_manifest,
        )
        return [r for r in results if r.value is not None]

    def where_is_across(
        self, entity_id: str, *, world_ids: list[str] | None = None,
        as_manifest: bool = False,
    ) -> list[CrossWorldResult]:
        """``where_is`` in every target world where the entity exists."""
        results = self.query_across(
            "where_is", entity_id, world_ids=world_ids,
            as_manifest=as_manifest,
        )
        return [r for r in results if r.value is not None]

    def get_facts_across(
        self, subject_id: str, *, world_ids: list[str] | None = None,
        as_manifest: bool = False,
    ) -> list[CrossWorldResult]:
        """Canonical facts about a subject, one result per world.

        Every target world contributes a result (its list may be
        empty) so a caller can see WHICH worlds were asked — a
        world's empty memory is its own fact, never filled from
        another world's.
        """
        return self.query_across(
            "get_facts", subject_id, world_ids=world_ids,
            as_manifest=as_manifest,
        )

    def search_facts_across(
        self, query: str, *, limit: int = 5,
        world_ids: list[str] | None = None, as_manifest: bool = False,
    ) -> list[CrossWorldResult]:
        """FTS fact search in every target world, per-world results."""
        return self.query_across(
            "search_facts", query, limit=limit, world_ids=world_ids,
            as_manifest=as_manifest,
        )

    def recent_observations_across(
        self, place_id: str | None = None, kind: Any | None = None,
        *, limit: int = 10, world_ids: list[str] | None = None,
        as_manifest: bool = False,
    ) -> list[CrossWorldResult]:
        """Filtered recent observations, one result per world."""
        return self.query_across(
            "recent_observations", place_id, kind, limit=limit,
            world_ids=world_ids, as_manifest=as_manifest,
        )


__all__ = [
    "READ_ONLY_ORACLE_QUERIES",
    "CrossWorldResult",
    "CrossWorldWriteRefused",
    "MultiWorldHost",
    "UnregisteredWorldError",
    "WorldServingSummary",
    "WorldSharingError",
    "ZeroBleedError",
]
