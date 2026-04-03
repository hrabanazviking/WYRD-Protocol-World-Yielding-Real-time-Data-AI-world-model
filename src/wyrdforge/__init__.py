"""Wyrdforge — World-Yielding Real-time Data AI world model substrate."""

__version__ = "1.0.0"

from .models.memory import MemoryRecord, ObservationRecord, CanonicalFactRecord
from .models.bond import BondEdge, Vow, Hurt
from .models.persona import PersonaPacket
from .models.micro_rag import MicroContextPacket
from .models.evals import EvalCase, EvalResult

__all__ = [
    "__version__",
    "MemoryRecord",
    "ObservationRecord",
    "CanonicalFactRecord",
    "BondEdge",
    "Vow",
    "Hurt",
    "PersonaPacket",
    "MicroContextPacket",
    "EvalCase",
    "EvalResult",
]
