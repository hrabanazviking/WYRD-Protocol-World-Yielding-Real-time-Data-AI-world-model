"""test_phase19_load.py — 19D: Concurrency and stability mini load test.

Spins up a live WyrdHTTPServer and fires 50 concurrent POST /query requests
using a thread pool.  Success criteria:
  - All 50 requests complete (no dropped connections, no hangs)
  - All 50 return HTTP 200
  - All 50 contain a "response" key
  - p99 latency < 2 s

Also tests:
  - Mixed endpoint load: /query + /world + /facts + /event concurrently
  - Event endpoint survives burst (no dropped events, no server crash)
  - Server remains responsive (health check passes) after load
"""
from __future__ import annotations

import json
import socket
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import NamedTuple
from unittest.mock import MagicMock

import pytest

from wyrdforge.bridges.http_api import WyrdHTTPServer


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_mock_bridge():
    bridge = MagicMock()
    bridge.query.return_value = "Skål, warrior."
    packet = MagicMock()
    packet.model_dump_json.return_value = json.dumps({
        "world_name": "load_test_world",
        "entities": [],
        "zones": [],
    })
    bridge.oracle.build_context_packet.return_value = packet
    fact = MagicMock()
    fact.model_dump_json.return_value = json.dumps({"subject_id": "s", "key": "k", "value": "v"})
    bridge.oracle.get_facts.return_value = [fact]
    bridge.push_event.return_value = None
    return bridge


class _LiveServer:
    def __init__(self):
        self.port = _find_free_port()
        self.bridge = _make_mock_bridge()
        self.server = WyrdHTTPServer(self.bridge, host="127.0.0.1", port=self.port)

    def __enter__(self):
        self.server.start_background()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.05)
        return self

    def __exit__(self, *_):
        self.server.shutdown()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class Result(NamedTuple):
    status: int
    body: dict
    elapsed: float


def _post(base: str, path: str, body: dict) -> Result:
    url = base + path
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            elapsed = time.monotonic() - t0
            return Result(resp.status, json.loads(resp.read()), elapsed)
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - t0
        return Result(e.code, json.loads(e.read()), elapsed)


def _get(base: str, path: str) -> Result:
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            elapsed = time.monotonic() - t0
            return Result(resp.status, json.loads(resp.read()), elapsed)
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - t0
        return Result(e.code, json.loads(e.read()), elapsed)


# ===========================================================================
# 50 concurrent /query requests
# ===========================================================================

class TestConcurrentQuery:
    N = 50

    def test_all_complete(self):
        with _LiveServer() as srv:
            with ThreadPoolExecutor(max_workers=self.N) as pool:
                futures = [
                    pool.submit(_post, srv.base, "/query",
                                {"persona_id": "sigrid", "user_input": f"Query {i}"})
                    for i in range(self.N)
                ]
                results = [f.result() for f in as_completed(futures)]
        assert len(results) == self.N

    def test_all_return_200(self):
        with _LiveServer() as srv:
            with ThreadPoolExecutor(max_workers=self.N) as pool:
                futures = [
                    pool.submit(_post, srv.base, "/query",
                                {"persona_id": "sigrid", "user_input": f"Query {i}"})
                    for i in range(self.N)
                ]
                results = [f.result() for f in as_completed(futures)]
        failures = [r for r in results if r.status != 200]
        assert failures == [], f"{len(failures)} non-200 responses"

    def test_all_have_response_key(self):
        with _LiveServer() as srv:
            with ThreadPoolExecutor(max_workers=self.N) as pool:
                futures = [
                    pool.submit(_post, srv.base, "/query",
                                {"persona_id": "sigrid", "user_input": f"Query {i}"})
                    for i in range(self.N)
                ]
                results = [f.result() for f in as_completed(futures)]
        missing = [r for r in results if "response" not in r.body]
        assert missing == []

    def test_p99_under_2_seconds(self):
        with _LiveServer() as srv:
            with ThreadPoolExecutor(max_workers=self.N) as pool:
                futures = [
                    pool.submit(_post, srv.base, "/query",
                                {"persona_id": "sigrid", "user_input": f"Query {i}"})
                    for i in range(self.N)
                ]
                results = [f.result() for f in as_completed(futures)]
        latencies = sorted(r.elapsed for r in results)
        p99_idx = max(0, int(len(latencies) * 0.99) - 1)
        p99 = latencies[p99_idx]
        assert p99 < 2.0, f"p99 latency {p99:.3f}s exceeds 2s threshold"


# ===========================================================================
# Mixed endpoint concurrent load
# ===========================================================================

class TestMixedEndpointLoad:
    """Fire 50 requests spread across all endpoints simultaneously."""

    def _make_tasks(self, base: str) -> list:
        tasks = []
        n = 12  # per endpoint (total ~50)
        for i in range(n):
            tasks.append((_post, (base, "/query", {"persona_id": "sigrid", "user_input": f"Q{i}"})))
        for i in range(n):
            tasks.append((_get, (base, "/world")))
        for i in range(n):
            tasks.append((_get, (base, f"/facts?entity_id=sigrid")))
        for i in range(n):
            tasks.append((_post, (base, "/event", {"event_type": "observation",
                                                    "payload": {"title": f"T{i}", "summary": "S"}})))
        tasks.append((_get, (base, "/health")))
        tasks.append((_get, (base, "/health")))
        return tasks

    def test_no_errors_under_mixed_load(self):
        with _LiveServer() as srv:
            tasks = self._make_tasks(srv.base)
            with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
                futures = [pool.submit(fn, *args) for fn, args in tasks]
                results = [f.result() for f in as_completed(futures)]
        error_responses = [r for r in results if r.status >= 500]
        assert error_responses == [], f"{len(error_responses)} 5xx responses"

    def test_all_mixed_complete_under_5_seconds(self):
        with _LiveServer() as srv:
            tasks = self._make_tasks(srv.base)
            t0 = time.monotonic()
            with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
                futures = [pool.submit(fn, *args) for fn, args in tasks]
                results = [f.result() for f in as_completed(futures)]
            total = time.monotonic() - t0
        assert total < 5.0, f"Mixed load took {total:.2f}s > 5s"
        assert len(results) == len(tasks)


# ===========================================================================
# Event burst
# ===========================================================================

class TestEventBurst:
    """Rapid sequential event pushes must not crash the server."""

    N = 100

    def test_burst_events_all_succeed(self):
        with _LiveServer() as srv:
            results = []
            for i in range(self.N):
                r = _post(srv.base, "/event", {
                    "event_type": "observation",
                    "payload": {"title": f"Event {i}", "summary": "Burst test"},
                })
                results.append(r)
        assert all(r.status == 200 for r in results), (
            f"{sum(1 for r in results if r.status != 200)} non-200 events"
        )

    def test_server_healthy_after_burst(self):
        with _LiveServer() as srv:
            for i in range(self.N):
                _post(srv.base, "/event", {
                    "event_type": "observation",
                    "payload": {"title": f"E{i}", "summary": "burst"},
                })
            r = _get(srv.base, "/health")
        assert r.status == 200
        assert r.body.get("status") == "ok"
