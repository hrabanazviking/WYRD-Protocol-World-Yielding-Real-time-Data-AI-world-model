"""PythonRPGBridge — direct in-process adapter for Python RPG engines.

Wraps the full WYRD stack (PassiveOracle + CharacterContext + TurnLoop) behind
a minimal ``query(persona_id, user_input)`` call so that any Python RPG
script can drop WYRD in without caring about the internal plumbing.

Typical usage::

    from wyrdforge.bridges.python_rpg import PythonRPGBridge, BridgeConfig

    bridge = PythonRPGBridge.from_config(
        BridgeConfig(
            world_id="my_world",
            db_path="wyrd.db",
            ollama_model="llama3",
        )
    )
    reply = bridge.query("sigrid", "What do the runes say?")
    print(reply)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from wyrdforge.bridges.base import BifrostBridge
from wyrdforge.ecs.world import World
from wyrdforge.ecs.yggdrasil import YggdrasilTree
from wyrdforge.llm.ollama_connector import OllamaConnector
from wyrdforge.models.micro_rag import QueryMode
from wyrdforge.models.persona import PersonaMode
from wyrdforge.oracle.passive_oracle import PassiveOracle
from wyrdforge.persistence.memory_store import PersistentMemoryStore
from wyrdforge.runtime.character_context import CharacterContext, CharacterContextResult
from wyrdforge.runtime.turn_loop import TurnLoop
from wyrdforge.services.bond_graph_service import BondGraphService
from wyrdforge.services.contradiction_detector import ContradictionDetector
from wyrdforge.services.writeback_engine import WritebackEngine


@dataclass
class BridgeConfig:
    """Configuration for PythonRPGBridge.

    Attributes:
        world_id:       Logical ID for the World instance.
        db_path:        SQLite path for PersistentMemoryStore.
        ollama_model:   Model name used by OllamaConnector.
        ollama_host:    Ollama server host.
        ollama_port:    Ollama server port.
        ollama_timeout: HTTP timeout seconds.
        default_location_id: Default location injected into every query.
        history_limit:  Max turns kept in TurnLoop conversation history.
        rag_candidates: Max RAG candidates per family.
        rag_budget:     MicroRAG token budget.
        use_bond_service: Whether to enable BondGraphService.
    """

    world_id: str = "wyrd_world"
    db_path: str = "wyrd.db"
    ollama_model: str = "llama3"
    ollama_host: str = "localhost"
    ollama_port: int = 11434
    ollama_timeout: int = 60
    default_location_id: str | None = None
    history_limit: int = 10
    rag_candidates: int = 20
    rag_budget: int = 900
    use_bond_service: bool = True
    extra_world_kwargs: dict[str, Any] = field(default_factory=dict)


class PythonRPGBridge(BifrostBridge):
    """In-process WYRD bridge for Python RPG engines.

    Owns a complete WYRD service stack.  The caller may inject a pre-built
    ``World`` and ``YggdrasilTree`` (for engine-managed worlds) or rely on
    the minimal blank world created by :meth:`from_config`.

    Args:
        world:          ECS World instance.
        yggdrasil:      Yggdrasil spatial tree.
        memory_store:   PersistentMemoryStore.
        connector:      OllamaConnector (may be None if no LLM is needed).
        bond_service:   Optional BondGraphService.
        config:         BridgeConfig (used for optional defaults).
    """

    def __init__(
        self,
        world: World,
        yggdrasil: YggdrasilTree,
        memory_store: PersistentMemoryStore,
        connector: OllamaConnector | None,
        *,
        bond_service: BondGraphService | None = None,
        config: BridgeConfig | None = None,
    ) -> None:
        self._world = world
        self._tree = yggdrasil
        self._store = memory_store
        self._connector = connector
        self._bond_service = bond_service
        self._config = config or BridgeConfig()

        self._oracle = PassiveOracle(world, memory_store, yggdrasil=yggdrasil)
        self._engine = WritebackEngine(memory_store)
        self._detector = ContradictionDetector(memory_store)
        self._char_ctx = CharacterContext(
            self._oracle,
            memory_store,
            bond_service=bond_service,
            max_rag_candidates=self._config.rag_candidates,
            rag_packet_budget=self._config.rag_budget,
        )

        # Per-persona TurnLoops lazily created on first query
        self._turn_loops: dict[str, TurnLoop] = {}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: BridgeConfig) -> "PythonRPGBridge":
        """Build a bridge from a BridgeConfig with a blank World.

        Use this when the RPG engine doesn't manage an existing ECS World.
        Entities and locations can be added post-construction via
        ``bridge.world`` and ``bridge.yggdrasil``.

        Args:
            config: BridgeConfig with connection and behaviour settings.

        Returns:
            A fully initialised PythonRPGBridge.
        """
        world = World(config.world_id, config.world_id.replace("_", " ").title())
        tree = YggdrasilTree(world)
        store = PersistentMemoryStore(config.db_path)
        connector = OllamaConnector(
            host=config.ollama_host,
            port=config.ollama_port,
            model=config.ollama_model,
            timeout=config.ollama_timeout,
        )
        bond_service = BondGraphService() if config.use_bond_service else None
        return cls(world, tree, store, connector, bond_service=bond_service, config=config)

    # ------------------------------------------------------------------
    # BifrostBridge implementation
    # ------------------------------------------------------------------

    def query(
        self,
        persona_id: str,
        user_input: str,
        *,
        location_id: str | None = None,
        bond_id: str | None = None,
        query_mode: QueryMode = QueryMode.COMPANION_CONTINUITY,
        persona_mode: PersonaMode = PersonaMode.COMPANION,
        focus_entity_ids: list[str] | None = None,
        use_turn_loop: bool = True,
    ) -> str:
        """Query a character and return their response.

        When ``use_turn_loop=True`` (default) the full TurnLoop is used,
        meaning the exchange is written to memory and conversation history
        is maintained per persona.  Set ``use_turn_loop=False`` to get a
        pure :class:`CharacterContextResult` render without LLM generation
        (useful for testing or when Ollama is unavailable).

        Args:
            persona_id:        Active character/persona ID.
            user_input:        Player text.
            location_id:       Override location (falls back to config default).
            bond_id:           Bond edge ID for relationship context.
            query_mode:        MicroRAG scoring mode.
            persona_mode:      PersonaCompiler compilation mode.
            focus_entity_ids:  Entities to focus context on (defaults to [persona_id]).
            use_turn_loop:     Use TurnLoop (LLM + memory write) vs context-only.

        Returns:
            Character response string.
        """
        loc = location_id or self._config.default_location_id
        entities = focus_entity_ids if focus_entity_ids is not None else [persona_id]

        if not use_turn_loop or self._connector is None:
            result: CharacterContextResult = self._char_ctx.build(
                persona_id=persona_id,
                user_id="player",
                query=user_input,
                mode=query_mode,
                persona_mode=persona_mode,
                focus_entity_ids=entities,
                location_id=loc,
                bond_id=bond_id,
            )
            return result.formatted_for_llm

        loop = self._get_or_create_loop(persona_id, loc)
        turn = loop.execute_turn(user_input, location_id=loc)
        return turn.assistant_response

    def push_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Write an engine event as a memory observation.

        Supported event types:
        - ``"observation"`` — ``payload`` must have ``title`` and ``summary`` keys.
        - ``"fact"`` — ``payload`` must have ``subject_id``, ``key``, ``value``,
          and optionally ``confidence`` and ``domain``.

        Args:
            event_type: ``"observation"`` or ``"fact"``.
            payload:    Data dict matching the event type.
        """
        if event_type == "observation":
            self._engine.write_observation(
                title=payload.get("title", "Engine event"),
                summary=payload.get("summary", ""),
            )
        elif event_type == "fact":
            self._engine.write_canonical_fact(
                fact_subject_id=payload["subject_id"],
                fact_key=payload["key"],
                fact_value=payload["value"],
                confidence=float(payload.get("confidence", 0.85)),
                domain=payload.get("domain", ""),
            )

    def clear_history(self, persona_id: str) -> None:
        """Clear conversation history for a persona.

        Args:
            persona_id: Persona whose history to clear.
        """
        if persona_id in self._turn_loops:
            self._turn_loops[persona_id].clear_history()

    def teardown(self) -> None:
        """No persistent resources to release."""

    # ------------------------------------------------------------------
    # Accessors (for engine-managed world building)
    # ------------------------------------------------------------------

    @property
    def world(self) -> World:
        """The underlying ECS World."""
        return self._world

    @property
    def yggdrasil(self) -> YggdrasilTree:
        """The Yggdrasil spatial hierarchy."""
        return self._tree

    @property
    def oracle(self) -> PassiveOracle:
        """The PassiveOracle (read-only world queries)."""
        return self._oracle

    @property
    def writeback(self) -> WritebackEngine:
        """The WritebackEngine (write facts/observations)."""
        return self._engine

    @property
    def bond_service(self) -> BondGraphService | None:
        """The BondGraphService if enabled."""
        return self._bond_service

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_loop(self, persona_id: str, location_id: str | None) -> TurnLoop:
        if persona_id not in self._turn_loops:
            assert self._connector is not None
            self._turn_loops[persona_id] = TurnLoop(
                self._oracle,
                self._engine,
                self._detector,
                self._connector,
                focus_entity_id=persona_id,
                location_id=location_id,
                persona_name=persona_id,
                history_limit=self._config.history_limit,
            )
        return self._turn_loops[persona_id]
