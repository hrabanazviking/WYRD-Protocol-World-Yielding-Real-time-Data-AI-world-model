"""wyrd_pygame_client.py — HTTP client for the WYRD pygame bridge.

Uses only stdlib (urllib.request + threading) — no extra pip installs needed
beyond what a pygame project already has.

Usage::

    from wyrd_pygame_client import WyrdPygameClient

    client = WyrdPygameClient()          # connects to localhost:8765
    response = client.query("sigrid", "What do you know about the army?")
    client.push_observation("Army spotted", "300 warriors at the north gate.")
    client.sync_entity("goblin_king", name="Goblin King", location="cave", status="hostile")
    alive = client.health_check()
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

from wyrd_pygame_helpers import (
    build_fact_body,
    build_observation_body,
    build_query_body,
    normalize_persona_id,
    parse_response,
    to_facts,
    WyrdFact,
)


class WyrdPygameClient:
    """Thin HTTP client wrapping WyrdHTTPServer for pygame games.

    All push operations (observation, fact, entity sync) run in daemon
    threads so they never block the pygame render loop.

    Args:
        host:              WyrdHTTPServer hostname (default ``"localhost"``).
        port:              WyrdHTTPServer port (default ``8765``).
        timeout:           HTTP timeout in seconds (default ``10``).
        silent_on_error:   If ``True``, HTTP / connection errors are silently
                           swallowed and the fallback response is returned
                           instead of raising (default ``True``).
        fallback_response: String returned by :meth:`query` when the server
                           is unreachable and *silent_on_error* is ``True``.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        timeout: int = 10,
        silent_on_error: bool = True,
        fallback_response: str = "The spirits whisper nothing of note.",
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.silent_on_error = silent_on_error
        self.fallback_response = fallback_response

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def query(self, persona_id: str, user_input: str) -> str:
        """Query WyrdHTTPServer for character context.  Blocking call.

        Args:
            persona_id: Character identifier (will be normalized automatically).
            user_input: The question or player message.

        Returns:
            The response string from WYRD, or *fallback_response* on error.
        """
        pid = normalize_persona_id(persona_id) if persona_id else persona_id
        body = build_query_body(pid, user_input)
        try:
            raw = self._post("/query", body)
            result = parse_response(raw)
            return result if result else self.fallback_response
        except Exception:
            if self.silent_on_error:
                return self.fallback_response
            raise

    def push_observation(self, title: str, summary: str) -> None:
        """Push an observation event.  Fire-and-forget (non-blocking).

        Args:
            title:   Short label for the event.
            summary: Full description of what happened.
        """
        body = build_observation_body(title, summary)
        self._fire_and_forget("/event", body)

    def push_fact(self, subject_id: str, key: str, value: str) -> None:
        """Push a canonical fact.  Fire-and-forget (non-blocking).

        Args:
            subject_id: Entity whose fact is being set.
            key:        Fact key (e.g. ``"location"``, ``"status"``).
            value:      Fact value.
        """
        body = build_fact_body(subject_id, key, value)
        self._fire_and_forget("/event", body)

    def sync_entity(
        self,
        entity_id: str,
        *,
        name: str = "",
        location: str = "",
        status: str = "",
        faction: str = "",
    ) -> None:
        """Sync an entity's state into WYRD as canonical facts.

        Each non-empty field is pushed as a separate fact (fire-and-forget).

        Args:
            entity_id: Entity identifier (will be normalized).
            name:      Display name.
            location:  Current location ID.
            status:    Current status string.
            faction:   Faction or group.
        """
        pid = normalize_persona_id(entity_id)
        fields = {
            "name": name,
            "location": location,
            "status": status,
            "faction": faction,
        }
        for key, value in fields.items():
            if value:
                self.push_fact(pid, key, value)

    def get_facts(self, subject_id: str) -> list[WyrdFact]:
        """Fetch canonical facts for a subject.  Blocking call.

        Args:
            subject_id: Entity whose facts to retrieve.

        Returns:
            List of :class:`~wyrd_pygame_helpers.WyrdFact` objects,
            or ``[]`` on error when *silent_on_error* is ``True``.
        """
        url = f"{self.base_url}/facts?subject_id={urllib.request.quote(subject_id)}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return to_facts(raw)
        except Exception:
            if self.silent_on_error:
                return []
            raise

    def health_check(self) -> bool:
        """Check whether WyrdHTTPServer is reachable.

        Returns:
            ``True`` if the server responds with status 200, ``False`` otherwise.
        """
        try:
            url = f"{self.base_url}/health"
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post(self, path: str, body: str) -> str:
        """Send a blocking HTTP POST and return the response body."""
        url = f"{self.base_url}{path}"
        data = body.encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _fire_and_forget(self, path: str, body: str) -> None:
        """Send an HTTP POST in a daemon thread (non-blocking)."""
        def _send() -> None:
            try:
                self._post(path, body)
            except Exception:
                pass  # silent — push operations are best-effort

        t = threading.Thread(target=_send, daemon=True)
        t.start()
