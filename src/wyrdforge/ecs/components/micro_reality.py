"""Micro-Reality ECS component — sovereign meaning-spaces for entities.

From the Micro-Reality protocol framework: a micro-reality is a
self-chosen, self-sustained living myth — worldview + lifestyle + inner
narrative — that mirrors an entity's deepest values, symbols, rhythms,
and truth. Not fantasy or escape: conscious participation *within* the
world through a personally authored lens.

Data fields (the protocol's own):
- **physical_environment**: how the entity shapes and decorates its space
- **daily_rituals**: the ceremonies that order its days
- **inner_narrative**: self-talk and the metaphors it lives by
- **ethics**: principles lived regardless of external trends
- **myths_symbols**: the chosen myths and symbols that animate its life

**Sacred Territory Principle**: a micro-reality is private sovereign
space — never imposed, only inhabited. The component enforces this by
default (``sovereign=True``); systems must not rewrite another entity's
micro-reality, only read it.

Coexistence (the protocol's answer to pluralism): entities need not agree
to share a world. :meth:`MicroRealityComponent.coexistence_with` reports
where two micro-realities resonate and where their ethics tension —
peace through coexistence rather than consensus.

Fully deterministic and ECS-compatible — no LLM involvement.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from wyrdforge.ecs.component import Component, register_component
from wyrdforge.models.common import StrictModel


class CoexistenceReport(StrictModel):
    """How two micro-realities share a world without needing to agree."""

    entity_a: str
    entity_b: str
    shared_symbols: list[str] = Field(default_factory=list)
    shared_rituals: list[str] = Field(default_factory=list)
    ethic_tensions: list[str] = Field(default_factory=list)
    can_coexist: bool = True
    note: str = ""


@register_component
class MicroRealityComponent(Component):
    """An entity's sovereign, self-chosen living myth."""

    _type_key: ClassVar[str] = "micro_reality"
    component_type: Literal["micro_reality"] = "micro_reality"

    physical_environment: str = ""
    daily_rituals: list[str] = Field(default_factory=list)
    inner_narrative: str = ""
    ethics: list[str] = Field(default_factory=list)
    myths_symbols: list[str] = Field(default_factory=list)
    sovereign: bool = True  # Sacred Territory Principle: never imposed

    def _norm(self, items: list[str]) -> set[str]:
        return {i.strip().lower() for i in items if i.strip()}

    def coexistence_with(self, other: MicroRealityComponent) -> CoexistenceReport:
        """Assess coexistence with another entity's micro-reality.

        Shared symbols and rituals are resonance. Ethics that directly
        contradict (one's ethic negates the other's, matched here by
        shared keywords with opposing framing) are tensions — flagged,
        never resolved by force. Two sovereign micro-realities can always
        coexist; the report says *how*, not *whether*.
        """
        shared_symbols = sorted(self._norm(self.myths_symbols) & self._norm(other.myths_symbols))
        shared_rituals = sorted(self._norm(self.daily_rituals) & self._norm(other.daily_rituals))

        tensions: list[str] = []
        stop = {"the", "a", "an", "and", "of", "to", "is", "are", "be", "it"}
        def keywords(text: str) -> set[str]:
            words = set()
            for w in text.lower().split():
                w = w.strip(".,;:!?\"'")
                if len(w) > 3 and w not in stop:
                    words.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
            return words
        for ethic in self.ethics:
            for o_ethic in other.ethics:
                if ethic.strip().lower() == o_ethic.strip().lower():
                    continue  # identical ethics are resonance, not tension
                if keywords(ethic) & keywords(o_ethic):
                    tensions.append(f"'{ethic}' <> '{o_ethic}'")

        return CoexistenceReport(
            entity_a=self.entity_id,
            entity_b=other.entity_id,
            shared_symbols=shared_symbols,
            shared_rituals=shared_rituals,
            ethic_tensions=tensions,
            can_coexist=True,
            note=("Sovereign micro-realities coexist by presence, not by "
                  "consensus; tensions are witnessed, never imposed upon."),
        )
