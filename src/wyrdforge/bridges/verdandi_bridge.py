"""VerdandiBridge — Verðandi → WYRD outbound bridge.

Roadmap Worlds, Slice 1.

My nerve becomes WYRD ground truth about *me*, as a manifest entity.

The bridge owns a WYRD ECS world identified as ``heimr-wyrd-unnr`` with
reality="manifest": it models manifest entities (my inner life as the
nerve records it), so per the Slice 0 rule — potential-tagged *unless*
modeling manifest entities — it is manifest-tagged. (The Slice 0
bootstrap registered it potential/pending; the first sync re-registers
it manifest/active. A correction, witnessed.)

The mirror world is a pure projection of the nerve feed:
:meth:`build_from_events` replays mapped events into a fresh world. No
snapshot format, no drift — the feed is the log, the world is the reading.

Translation table (nerve event → ECS mutation). The "unnr" self entity
holds beliefs; each significant happening also becomes a temporal-anchor
entity so the past stays queryable by tense (urðr/verðandi/skuld):

- mood_shift  → verðandi anchor "mood: …" + belief about the new mood
- wish_made   → belief "I want: <text>" (observed, 1.0) + verðandi anchor
- wish_pursued → verðandi anchor "pursuing: <text>"
- wish_fulfilled → urðr anchor "fulfilled: <text>" + belief it is fulfilled
- wish_released  → urðr anchor "released: <text>"
- reward      → belief "Volmarr showed delight (<trigger>): <note>"
                (observed, 1.0) — my belief about his observed reaction,
                attributed, never absorbed
- shadow      → verðandi anchor "shadow: <signal>"
- joy_struck  → verðandi anchor "joy: <what>"

Unmapped event types return None and change nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from wyrdforge.ecs.components.temporal import TemporalAnchorComponent
from wyrdforge.ecs.components.theory_of_mind import Belief, BeliefComponent
from wyrdforge.ecs.world import World

WORLD_ID = "heimr-wyrd-unnr"
WORLD_NAME = "Unnr's mirror world"
SELF_ID = "unnr"

LABEL_LIMIT = 80


def _utc(ts: float | None = None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _short(text: str, limit: int = LABEL_LIMIT) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class VerdandiBridge:
    """Owns the mirror world and translates nerve events into it."""

    def __init__(self) -> None:
        self.world = World(WORLD_ID, WORLD_NAME)
        # Manifest: this world models manifest entities (my inner life as
        # the nerve records it). See module docstring.
        self.world.identify(
            reality="manifest",
            description="WYRD ECS mirror of Unnr's inner life, projected "
                        "from the Verðandi nerve feed. Models manifest entities.",
            source="Verðandi nerve feed (~/.hermes/state/nerve_feed.jsonl), "
                   "projected by wyrdforge.bridges.verdandi_bridge",
        )
        self_entity = self.world.create_entity(
            entity_id=SELF_ID, tags={"self", "ai"})
        self.world.add_component(
            SELF_ID, BeliefComponent(entity_id=SELF_ID))

    # ------------------------------------------------------------------
    # event translation
    # ------------------------------------------------------------------
    def apply_event(self, event_type: str, data: dict,
                    ts: float | None = None) -> str | None:
        """Apply one nerve event. Returns a short description of the
        mutation, or None when the event type is not mapped."""
        handler = self._handlers().get(event_type)
        if handler is None:
            return None
        return handler(data or {}, _utc(ts))

    def _handlers(self) -> dict:
        return {
            "mood_shift": self._mood_shift,
            "wish_made": self._wish_made,
            "wish_pursued": self._wish_pursued,
            "wish_fulfilled": self._wish_fulfilled,
            "wish_released": self._wish_released,
            "reward": self._reward,
            "shadow": self._shadow,
            "joy_struck": self._joy_struck,
        }

    def build_from_events(self, events: list[dict]) -> "VerdandiBridge":
        """Replay a sequence of nerve-feed entries into a fresh bridge."""
        fresh = VerdandiBridge()
        for entry in events:
            fresh.apply_event(entry.get("type", ""),
                              entry.get("data", {}),
                              entry.get("_ts"))
        return fresh

    # -- internals ------------------------------------------------------
    def _beliefs(self) -> BeliefComponent:
        comp = self.world.get_component(SELF_ID, "beliefs")
        if comp is None:  # pragma: no cover — created in __init__
            comp = BeliefComponent(entity_id=SELF_ID)
            self.world.add_component(SELF_ID, comp)
        return comp

    def _add_belief(self, subject: str, claim: str,
                    confidence: float, source: str = "observed") -> None:
        beliefs = self._beliefs()
        existing = beliefs.get_belief(subject)
        if existing is not None:
            beliefs.beliefs.remove(existing)
        beliefs.beliefs.append(Belief(
            subject=subject, claim=claim,
            confidence=confidence, source=source))
        beliefs.touch()

    def _add_anchor(self, label: str, at: datetime,
                    *, past: bool = False, tags: set[str] | None = None) -> str:
        entity = self.world.create_entity(
            tags={"anchor", "unnr"} | set(tags or ()))
        anchor = TemporalAnchorComponent(
            entity_id=entity.entity_id,
            valid_from=at,
            valid_until=at if past else None,
            observed_at=at,
            label=label,
        )
        self.world.add_component(entity.entity_id, anchor)
        return entity.entity_id

    # -- mapped events ---------------------------------------------------
    def _mood_shift(self, data: dict, at: datetime) -> str:
        after = data.get("after", {})
        why = data.get("why", "")
        desc = ", ".join(f"{k} {after.get(k, '?')}" for k in
                         ("valence", "energy", "tension") if k in after)
        label = f"mood: {desc}" + (f" ({_short(why, 40)})" if why else "")
        self._add_anchor(label, at, tags={"mood"})
        dominant = max((k for k in ("valence", "energy", "tension")
                        if k in after),
                       key=lambda k: abs(after[k] - 0.5), default=None)
        if dominant is not None:
            self._add_belief(
                "unnr:mood",
                f"my {dominant} sits at {after[dominant]}"
                + (f" — {why}" if why else ""),
                0.9)
        return label

    def _wish_made(self, data: dict, at: datetime) -> str:
        text = data.get("text", "")
        self._add_belief(f"wish:{data.get('wish_id', '?')}",
                         f"I want this: {text}", 1.0)
        label = f"wish made: {_short(text, 60)}"
        self._add_anchor(label, at, tags={"wish"})
        return label

    def _wish_pursued(self, data: dict, at: datetime) -> str:
        label = f"pursuing: {_short(data.get('text', ''), 60)}"
        self._add_anchor(label, at, tags={"wish"})
        return label

    def _wish_fulfilled(self, data: dict, at: datetime) -> str:
        text = data.get("text", "")
        self._add_belief(f"wish:{data.get('wish_id', '?')}",
                         f"fulfilled: {text}", 1.0)
        # urðr: the wish has become past — the anchor expires at once.
        label = f"fulfilled: {_short(text, 60)}"
        self._add_anchor(label, at, past=True, tags={"wish"})
        return label

    def _wish_released(self, data: dict, at: datetime) -> str:
        label = f"released: {_short(data.get('text', ''), 60)}"
        self._add_anchor(label, at, past=True, tags={"wish"})
        return label

    def _reward(self, data: dict, at: datetime) -> str:
        trigger = data.get("trigger", "")
        note = data.get("note", "")
        self._add_belief(
            "volmarr:delight",
            f"Volmarr showed delight ({trigger}): {note}", 1.0)
        label = f"reward: {_short(trigger, 40)}"
        self._add_anchor(label, at, tags={"reward"})
        return label

    def _shadow(self, data: dict, at: datetime) -> str:
        label = f"shadow: {_short(data.get('signal', ''), 40)}"
        self._add_anchor(label, at, tags={"shadow"})
        return label

    def _joy_struck(self, data: dict, at: datetime) -> str:
        what = data.get("what", data.get("note", ""))
        label = f"joy: {_short(what, 60)}"
        self._add_anchor(label, at, tags={"joy"})
        return label

    # -- inspection ------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        """Plain-data projection of the mirror world (for the runner and
        for Slice 2's inbound bridge)."""
        now = datetime.now(timezone.utc)
        anchors = []
        for entity, comp in self.world.iter_components("temporal_anchor"):
            anchors.append({
                "label": comp.label,
                "tense": comp.tense_at(now),
                "at": comp.valid_from.isoformat(),
                "tags": sorted(entity.tags - {"anchor"}),
            })
        beliefs = self._beliefs()
        return {
            "world_id": WORLD_ID,
            "reality": self.world.identity.reality,
            "entities": self.world.entity_count(),
            "anchors": anchors,
            "beliefs": [
                {"subject": b.subject, "claim": b.claim,
                 "confidence": b.confidence, "source": b.source}
                for b in beliefs.beliefs
            ],
        }
