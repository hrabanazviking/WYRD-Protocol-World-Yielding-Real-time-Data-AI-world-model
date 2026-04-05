"""wyrd_pygame_loop.py — Event loop hooks for WYRD pygame integration.

Wraps :class:`WyrdPygameClient` with named semantic hooks that map naturally
onto pygame game-loop events.

Usage::

    import pygame
    from wyrd_pygame_client import WyrdPygameClient
    from wyrd_pygame_loop import WyrdPygameLoop

    client = WyrdPygameClient()
    wyrd = WyrdPygameLoop(client)

    # In your game loop:
    while running:
        for event in pygame.event.get():
            ...

        # When player talks to an NPC:
        context = wyrd.on_npc_interact("guard_captain", player_message)
        npc_dialogue_box.set_text(context)

        # When player moves to a new area:
        wyrd.on_scene_change("dark_forest")

        # When an NPC moves:
        wyrd.on_npc_move("goblin_scout", "cave_entrance")
"""
from __future__ import annotations

from wyrd_pygame_client import WyrdPygameClient
from wyrd_pygame_helpers import normalize_persona_id


class WyrdPygameLoop:
    """Event loop integration helper for pygame games.

    All push operations (scene change, NPC move) are fire-and-forget and
    will not block the pygame render loop.  Query operations (NPC interact)
    are blocking — call from a thread or coroutine if latency is a concern.

    Args:
        client: A configured :class:`WyrdPygameClient` instance.
    """

    def __init__(self, client: WyrdPygameClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def on_npc_interact(self, entity_id: str, player_input: str) -> str:
        """Called when the player interacts with an NPC.

        Queries WYRD for world-grounded context and returns the response
        string.  The game can use this as NPC dialogue, a GM narrator note,
        or a system prompt injection.

        Args:
            entity_id:    The NPC's entity identifier.
            player_input: What the player said or asked.

        Returns:
            WYRD's context/response string, or the client's fallback if
            the server is unreachable.
        """
        pid = normalize_persona_id(entity_id)
        return self._client.query(pid, player_input)

    def on_scene_change(self, location_id: str, description: str = "") -> None:
        """Called when the player enters a new scene or location.

        Pushes an observation event to WYRD (fire-and-forget).

        Args:
            location_id:  The new location's identifier.
            description:  Optional human-readable description of the scene.
        """
        title = f"Scene change: {location_id}"
        summary = description or f"The scene changed to {location_id}."
        self._client.push_observation(title, summary)

    def on_npc_move(self, entity_id: str, new_location: str) -> None:
        """Called when an NPC moves to a different location.

        Pushes a fact update to WYRD (fire-and-forget).

        Args:
            entity_id:    The NPC's entity identifier.
            new_location: The location ID the NPC moved to.
        """
        pid = normalize_persona_id(entity_id)
        self._client.push_fact(pid, "location", new_location)

    def on_npc_status_change(self, entity_id: str, new_status: str) -> None:
        """Called when an NPC's status changes (hurt, dead, fleeing, etc.).

        Pushes a fact update to WYRD (fire-and-forget).

        Args:
            entity_id:  The NPC's entity identifier.
            new_status: The new status string.
        """
        pid = normalize_persona_id(entity_id)
        self._client.push_fact(pid, "status", new_status)

    def on_game_event(self, title: str, summary: str) -> None:
        """Push any named game event into WYRD memory (fire-and-forget).

        Use for plot moments, combat outcomes, dialogue decisions, etc.

        Args:
            title:   Short event label (e.g. ``"Boss defeated"``).
            summary: Full description of what happened.
        """
        self._client.push_observation(title, summary)

    # ------------------------------------------------------------------
    # Accessor
    # ------------------------------------------------------------------

    @property
    def client(self) -> WyrdPygameClient:
        """The underlying :class:`WyrdPygameClient`."""
        return self._client
