"""Metaphysical fate/thread components — Phase D4 (roadmap §3.5 / §9-D4).

This module is the reconciliation of the Phase 7 plan with the code
that actually shipped. The plan (``WYRD_Phased_Implementation_Plan.md``
§7.1) promised a ``metaphysical.py`` holding ``HamingjaComponent``,
``WyrdThreadComponent``, and ``SpiritualChargeComponent``. What
shipped instead was a runic layer under different names and shapes
(``ecs/components/runic.py`` + ``services/runic_engine.py``):

- ``HamingjaComponent`` — shipped, in ``runic.py``: ``score`` in
  [-1.0, 1.0] (negative IS the plan's ``curse_active``, positive the
  blessing; the plan's [0, 1] score + two flags folded into one signed
  value), ``peak``, ``drift_rate``, ``last_event_id``. The plan's
  ``lineage_sources`` shipped on the sibling component below.
- ``AncestralResonanceComponent`` — not named in the plan, but it is
  where the plan's lineage half landed: ``lineage_ids`` are the
  plan's ``lineage_sources``, with a resonance ``score`` and inherited
  ``memory_fragments``.
- ``SpiritualChargeComponent`` — shipped as ``RunicChargeComponent``:
  instead of one signed ``charge_level`` the shipped shape keeps a
  per-rune charge map in [0.0, 1.0] (``charges``), because runic work
  is always *of a named rune*; ``total_charge()`` is the aggregate
  the plan's single level approximated, and invocation through
  ``RunicEngine.invoke_rune`` is the plan's ritual source.
- ``RunicBindingComponent`` (plan) — never shipped as a component;
  rune invocations are recorded as charges, not as persistent binding
  entities. Recorded here honestly: bindings remain unshipped.

The one promised piece that had NO shipped equivalent was the fate
thread itself — and a thread is not a garnish on an engine named
WYRD. D4 therefore ships it here, in the plan's own file and under
the plan's own name, composed ON the runic foundation rather than
beside or instead of it:

- A thread is an ENTITY (the D1 engagement/effect precedent: the
  World stores one component per type per entity, and a fate
  connection is a thing with its own lifecycle, not a field on one
  of its endpoints). The thread entity carries
  :class:`WyrdThreadComponent`; its two endpoints are ordinary
  entities, which may — independently — carry the runic components.
- The plan's per-entity sketch (``connected_entities`` on the
  subject) and the research sketch (a thread between exactly two
  entities, ``research_data/20_wyrd_protocol_ecs_worldmodel.md``)
  are reconciled as: the component lives on the thread entity and
  names exactly two ``endpoint_ids``; "the threads of an entity"
  is a query over thread entities, answered by the Oracle.
- Composition with the runic layer is by REFERENCE and by REPORT,
  never by duplication: a thread may name the ``rune_name`` it was
  woven under, and Oracle thread answers carry each endpoint's
  current hamingja (read live from ``HamingjaComponent``) beside the
  thread's own state — the thread layer does not copy, cache, or
  re-derive runic state.
- **Convergence is derived, never stored** (the D1 range-band
  doctrine): a thread's fate pressure is
  ``strength * wyrd_charge`` computed at query time, and a
  *convergence* is that pressure at or above a caller threshold
  between co-located endpoints (the Phase 7 plan's
  ``WyrdThreadSystem`` sketch: "high wyrd_charge between co-located
  entities"). Nothing stores a convergence flag that could disagree
  with the thread or the locations it was derived from.

Persistence: the component persists generically through
``WorldStore`` like B3's ``PositionComponent`` and D1's combat
components — no schema change, no migration.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Literal

from pydantic import Field, model_validator

from wyrdforge.ecs.component import Component, register_component


def _now() -> datetime:
    return datetime.now(timezone.utc)


#: Default per-tick strength decay for a woven thread (the research
#: sketch's 0.01/day shape, carried as a per-tick rate here because
#: WYRD's engines tick, they do not count days).
DEFAULT_THREAD_DECAY_RATE = 0.01

ThreadStatus = Literal["woven", "severed", "fulfilled"]

#: Lifecycle: a woven thread may be severed (cut before its fate
#: played out) or fulfilled (its prophesied/basis event came to
#: pass). Both are terminal — a new connection between the same
#: endpoints is a NEW thread entity, never a resurrection.
_THREAD_TRANSITIONS: dict[str, frozenset[str]] = {
    "woven": frozenset({"severed", "fulfilled"}),
    "severed": frozenset(),
    "fulfilled": frozenset(),
}


@register_component
class WyrdThreadComponent(Component):
    """One fate thread between two entities, as its own entity.

    The component lives on the thread entity (whose entity_id IS
    the thread id). Endpoints are referenced, never embedded.

    Attributes:
        endpoint_ids:     Exactly two distinct entity ids the thread
                          connects, in weaving order.
        kind:             Free-form thread kind: oath / love /
                          conflict / grief / shared_memory / … (the
                          research sketch's thread_type vocabulary).
        strength:         0.0 (barely a whisper) .. 1.0 (iron fate).
        wyrd_charge:      Accumulated fate energy in [0.0, 1.0] —
                          the plan's field of the same name.
        decay_rate:       Strength lost per ThreadEngine tick.
        prophesied_event: The event this thread is said to lead to,
                          or None when no prophecy is attached.
        description:      What this thread represents, in words.
        rune_name:        The rune the thread was woven under, if
                          any — a reference INTO the runic layer
                          (charges themselves stay on the endpoints'
                          RunicChargeComponents).
        basis_event_ids:  Event/record ids the weaving rests on.
        status:           woven / severed / fulfilled (see the
                          transition table; both ends are terminal).
        woven_at:         World-time the thread was woven.
        closed_at:        World-time it was severed/fulfilled, or
                          None while woven.
    """

    _type_key: ClassVar[str] = "wyrd_thread"
    component_type: Literal["wyrd_thread"] = "wyrd_thread"

    endpoint_ids: list[str] = Field(default_factory=list)
    kind: str = ""
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    wyrd_charge: float = Field(default=0.0, ge=0.0, le=1.0)
    decay_rate: float = Field(default=DEFAULT_THREAD_DECAY_RATE, ge=0.0, le=1.0)
    prophesied_event: str | None = None
    description: str = ""
    rune_name: str | None = None
    basis_event_ids: list[str] = Field(default_factory=list)
    status: ThreadStatus = "woven"
    woven_at: datetime = Field(default_factory=_now)
    closed_at: datetime | None = None

    @model_validator(mode="after")
    def _endpoints_are_a_pair(self) -> "WyrdThreadComponent":
        if len(self.endpoint_ids) != 2 or self.endpoint_ids[0] == self.endpoint_ids[1]:
            raise ValueError(
                "a wyrd thread connects exactly two distinct endpoints, "
                f"got {self.endpoint_ids!r}"
            )
        return self

    # -- endpoints ------------------------------------------------------

    @property
    def is_live(self) -> bool:
        return self.status == "woven"

    def involves(self, entity_id: str) -> bool:
        return entity_id in self.endpoint_ids

    def other_endpoint(self, entity_id: str) -> str | None:
        """The endpoint that is not ``entity_id``, or None."""
        if self.endpoint_ids[0] == entity_id:
            return self.endpoint_ids[1]
        if self.endpoint_ids[1] == entity_id:
            return self.endpoint_ids[0]
        return None

    # -- derived fate pressure (never stored) ----------------------------

    @property
    def convergence_score(self) -> float:
        """Fate pressure: strength × wyrd_charge, in [0.0, 1.0].

        Derived at read time from the thread's own two fields, so
        it can never disagree with them. A severed/fulfilled thread
        still reports the pressure it had — history is history —
        but convergence QUERIES only consider live threads.
        """
        return self.strength * self.wyrd_charge

    def is_convergence(self, threshold: float) -> bool:
        """True when this LIVE thread's pressure meets ``threshold``."""
        return self.is_live and self.convergence_score >= threshold

    # -- lifecycle --------------------------------------------------------

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in _THREAD_TRANSITIONS[self.status]

    def transition_to(self, new_status: ThreadStatus, *, at: datetime | None = None) -> None:
        """Move along the lifecycle; invalid moves raise ValueError."""
        if new_status == self.status:
            return
        if not self.can_transition_to(new_status):
            raise ValueError(
                f"wyrd thread cannot move {self.status} -> {new_status}; "
                f"allowed: {sorted(_THREAD_TRANSITIONS[self.status]) or 'none (terminal)'}"
            )
        self.status = new_status
        self.closed_at = at if at is not None else _now()
        self.touch()

    def sever(self, *, at: datetime | None = None) -> None:
        """Cut the thread. Terminal: severing a closed thread raises,
        so the act (and its event) can happen exactly once."""
        if not self.is_live:
            raise ValueError(f"cannot sever a {self.status} thread — it is already closed")
        self.transition_to("severed", at=at)

    def fulfill(self, *, at: datetime | None = None) -> None:
        """Mark the thread's fate fulfilled. Terminal, exactly once,
        like :meth:`sever`."""
        if not self.is_live:
            raise ValueError(f"cannot fulfill a {self.status} thread — it is already closed")
        self.transition_to("fulfilled", at=at)


def wyrd_thread_id(entity_a: str, entity_b: str, kind: str) -> str:
    """A readable deterministic thread-entity id for a weaving.

    Callers may pass their own id to ``ThreadEngine.weave`` instead;
    this helper exists so tests and demos get stable names of the
    D2 body-fact shape (``body-fact:<entity>:<channel>``).
    """
    return f"wyrd-thread:{entity_a}:{entity_b}:{kind}"
