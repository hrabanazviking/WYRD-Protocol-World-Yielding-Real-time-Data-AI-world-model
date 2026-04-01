from __future__ import annotations

from datetime import UTC, datetime

from wyrdforge.models.bond import BondEdge, Hurt, Vow


class BondGraphService:
    def __init__(self) -> None:
        self.edges: dict[str, BondEdge] = {}
        self.vows: dict[str, Vow] = {}
        self.hurts: dict[str, Hurt] = {}

    def add_edge(self, edge: BondEdge) -> None:
        if edge.chronology.formed_at is None:
            edge.chronology.formed_at = datetime.now(UTC)
        self.edges[edge.bond_id] = edge

    def add_vow(self, vow: Vow) -> None:
        self.vows[vow.vow_id] = vow

    def add_hurt(self, hurt: Hurt) -> None:
        self.hurts[hurt.hurt_id] = hurt
        edge = self.edges[hurt.bond_id]
        edge.scars.unresolved_hurts.append(hurt.hurt_id)
        severity_shift = {"low": 0.1, "medium": 0.2, "high": 0.35, "mythic": 0.5}[hurt.severity]
        edge.scars.repair_debt = min(1.0, edge.scars.repair_debt + severity_shift)
        edge.vector.safety = max(0.0, edge.vector.safety - severity_shift / 2)
        edge.status = edge.status.__class__.REPAIRING
        edge.chronology.last_major_shift_at = datetime.now(UTC)

    def apply_event(self, bond_id: str, *, warmth_delta: float = 0.0, trust_delta: float = 0.0, devotion_delta: float = 0.0, source_record_id: str | None = None) -> BondEdge:
        edge = self.edges[bond_id]
        edge.vector.warmth = min(1.0, max(0.0, edge.vector.warmth + warmth_delta))
        edge.vector.trust = min(1.0, max(0.0, edge.vector.trust + trust_delta))
        edge.vector.devotion = min(1.0, max(0.0, edge.vector.devotion + devotion_delta))
        edge.chronology.last_contact_at = datetime.now(UTC)
        if source_record_id:
            edge.evidence.supporting_record_ids.append(source_record_id)
        if edge.vector.trust >= 0.55 and edge.vector.warmth >= 0.55:
            edge.status = edge.status.__class__.ACTIVE
        return edge

    def excerpt(self, bond_id: str) -> list[str]:
        edge = self.edges[bond_id]
        lines = [
            f"domain={edge.domain.value}",
            f"status={edge.status.value}",
            f"closeness_index={edge.closeness_index():.2f}",
            f"sacred_bond_index={edge.sacred_bond_index():.2f}",
            f"rupture_index={edge.rupture_index():.2f}",
            f"relational_mode={edge.active_modes.relational_mode}",
            f"emotional_weather={edge.active_modes.emotional_weather}",
        ]
        if edge.scars.unresolved_hurts:
            lines.append(f"unresolved_hurts={','.join(edge.scars.unresolved_hurts)}")
        related_vows = [v for v in self.vows.values() if v.bond_id == bond_id]
        if related_vows:
            lines.append("vows=" + " | ".join(f"{v.vow_kind}:{v.state.value}:{v.vow_text}" for v in related_vows))
        return lines
