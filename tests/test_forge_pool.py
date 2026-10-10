"""Forge tests: BoundedThreadPool drain-on-shutdown (Helheim Hardening).

Covers the two-phase shutdown (drain the pending queue FIRST, bounded by
timeout, THEN send exit sentinels) and the tasks_completed / tasks_failed
counters.
"""
from __future__ import annotations

import threading
import time

from wyrdforge.hardening.pool import BoundedThreadPool


def test_shutdown_drains_all_queued_tasks_before_returning():
    pool = BoundedThreadPool(max_workers=2, max_queue=64)
    ran: list[int] = []
    lock = threading.Lock()

    def work(i):
        time.sleep(0.02)  # slow enough that the queue fills before drain
        with lock:
            ran.append(i)

    for i in range(30):
        assert pool.submit(work, i) is True

    pool.shutdown(wait=True, timeout=10.0)  # generous timeout per the slice

    assert sorted(ran) == list(range(30))  # every queued task ran
    assert pool.tasks_completed == 30
    assert pool.tasks_failed == 0


def test_counters_are_accurate():
    pool = BoundedThreadPool(max_workers=2, max_queue=64)

    def boom():
        raise RuntimeError("task exploded")

    for _ in range(5):
        assert pool.submit(lambda: None) is True
    for _ in range(2):
        assert pool.submit(boom) is True

    pool.shutdown(wait=True, timeout=10.0)

    assert pool.tasks_submitted == 7
    assert pool.tasks_completed == 5
    assert pool.tasks_failed == 2
    assert pool.tasks_dropped == 0


def test_failing_task_does_not_kill_the_pool():
    # Single worker: a failing task sits between two good ones. If the
    # worker died on the exception, the task after it would never run.
    pool = BoundedThreadPool(max_workers=1, max_queue=16)
    order: list[str] = []

    def boom():
        order.append("boom")
        raise RuntimeError("task exploded")

    assert pool.submit(lambda: order.append("first")) is True
    assert pool.submit(boom) is True
    assert pool.submit(lambda: order.append("last")) is True

    pool.shutdown(wait=True, timeout=10.0)

    assert order == ["first", "boom", "last"]  # worker survived the failure
    assert pool.tasks_completed == 2
    assert pool.tasks_failed == 1


def test_drain_happens_before_sentinels_when_queue_is_full():
    """The structural guarantee: even with a completely full queue, tasks
    submitted before shutdown() all run — the exit sentinels go behind
    them, never ahead of them."""
    pool = BoundedThreadPool(max_workers=1, max_queue=2)
    release = threading.Event()
    started = threading.Event()
    ran: list[str] = []

    def blocker():
        started.set()
        release.wait(timeout=10.0)

    assert pool.submit(blocker) is True  # pins the worker
    assert started.wait(timeout=5.0)  # worker is inside blocker; queue is empty
    assert pool.submit(lambda: ran.append("t1")) is True
    assert pool.submit(lambda: ran.append("t2")) is True  # queue now full

    finished = threading.Event()

    def do_shutdown():
        pool.shutdown(wait=True, timeout=10.0)
        finished.set()

    stopper = threading.Thread(target=do_shutdown)
    stopper.start()
    time.sleep(0.3)  # let shutdown enter its drain phase with a full queue
    release.set()  # free the worker; queued tasks must run before exit

    assert finished.wait(timeout=10.0)
    stopper.join(timeout=5.0)

    assert ran == ["t1", "t2"]
    assert pool.tasks_completed == 3
