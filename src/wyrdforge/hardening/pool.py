"""pool.py — Bounded daemon-thread pool for fire-and-forget push operations.

All WYRD bridge fire-and-forget operations (push_observation, push_fact, sync_entity)
spawn daemon threads.  Under sustained load this can accumulate thousands of threads.
:class:`BoundedThreadPool` caps the live thread count, queuing excess tasks until
a slot is free.

Usage::

    from wyrdforge.hardening.pool import BoundedThreadPool

    pool = BoundedThreadPool(max_workers=16)

    pool.submit(lambda: post_json_to_wyrd(url, body))  # your own HTTP
    pool.submit(my_push_function, arg1, arg2)          # call — `requests`
                                                      # is NOT a wyrdforge
                                                      # dependency

    # Graceful drain (waits up to timeout seconds for queued tasks)
    pool.shutdown(wait=True, timeout=5.0)
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_SENTINEL = object()  # signals a worker to exit


class BoundedThreadPool:
    """A fixed-size daemon-thread pool with a bounded task queue.

    Tasks submitted when the queue is full are dropped with a warning (they
    are fire-and-forget; dropping is safer than blocking the game loop).

    Args:
        max_workers:  Maximum number of concurrent worker threads (default 16).
        max_queue:    Maximum number of pending tasks (default 256).
        name_prefix:  Thread name prefix for debugging (default ``"wyrd-pool"``).
    """

    def __init__(
        self,
        max_workers: int = 16,
        max_queue: int = 256,
        name_prefix: str = "wyrd-pool",
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if max_queue < 1:
            raise ValueError("max_queue must be >= 1")

        self._max_workers = max_workers
        self._name_prefix = name_prefix
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._lock = threading.Lock()
        self._workers: list[threading.Thread] = []
        self._shutdown = False
        self._tasks_submitted = 0
        self._tasks_dropped = 0
        self._tasks_completed = 0
        self._tasks_failed = 0

        for i in range(max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"{name_prefix}-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, fn: Callable, *args, **kwargs) -> bool:
        """Schedule *fn(*args, **kwargs)* for execution.

        Returns:
            ``True`` if the task was queued, ``False`` if the queue was full
            and the task was dropped.
        """
        if self._shutdown:
            return False
        task = (fn, args, kwargs)
        try:
            self._queue.put_nowait(task)
            with self._lock:
                self._tasks_submitted += 1
            return True
        except queue.Full:
            with self._lock:
                self._tasks_dropped += 1
            logger.warning(
                "BoundedThreadPool: queue full (%d tasks waiting) — task dropped",
                self._queue.qsize(),
            )
            return False

    def shutdown(self, *, wait: bool = True, timeout: float = 5.0) -> None:
        """Stop accepting new tasks and optionally drain before stopping workers.

        Why the ordering matters: the old code sent the exit sentinels
        first. If the queue was full at that moment the sentinel puts were
        silently dropped, and workers blocked in ``get()`` would wake up,
        see the shutdown flag, and exit while real tasks were still
        queued — fire-and-forget work silently abandoned. Now shutdown is
        two phases:

        1. **Drain** (``wait=True`` only): wait — bounded by *timeout* —
           for every queued task to be picked up and finished. Workers keep
           running normally during this phase; no sentinel is in the queue.
        2. **Stop**: one sentinel per worker, appended behind any remaining
           tasks (FIFO), so no worker exits while real work is still ahead
           of its sentinel. Workers are then joined, bounded by the
           remaining *timeout* budget.

        Args:
            wait:    If True, drain the pending queue (up to *timeout*
                     seconds) before stopping workers.
            timeout: Total seconds budget for the whole shutdown (drain +
                     worker join). A stuck task cannot hang shutdown forever;
                     it is logged and shutdown moves on.
        """
        self._shutdown = True
        deadline: float | None = None
        if wait:
            deadline = time.monotonic() + max(0.0, timeout)
            self._drain_queue(deadline, timeout)
        # Phase 2 — stop. Sentinels go to the TAIL of the FIFO queue, behind
        # any task still pending, so a worker can only see its sentinel
        # after all real work ahead of it has run.
        for _ in self._workers:
            try:
                if deadline is not None:
                    remaining = max(0.0, deadline - time.monotonic())
                    self._queue.put(_SENTINEL, timeout=remaining)
                else:
                    self._queue.put_nowait(_SENTINEL)
            except queue.Full:
                # Extremely unlikely after a drain (or acceptable when not
                # waiting): a worker with no sentinel still exits via the
                # get()-timeout + shutdown-flag path in _worker_loop.
                logger.warning(
                    "BoundedThreadPool: could not deliver shutdown sentinel"
                )
        if wait and deadline is not None:
            for t in self._workers:
                remaining = max(0.0, deadline - time.monotonic())
                t.join(timeout=remaining)

    @property
    def max_workers(self) -> int:
        """Maximum number of concurrent worker threads."""
        return self._max_workers

    @property
    def queue_size(self) -> int:
        """Current number of tasks waiting in the queue."""
        return self._queue.qsize()

    @property
    def tasks_submitted(self) -> int:
        """Total tasks successfully queued since creation."""
        with self._lock:
            return self._tasks_submitted

    @property
    def tasks_dropped(self) -> int:
        """Total tasks dropped because the queue was full."""
        with self._lock:
            return self._tasks_dropped

    @property
    def tasks_completed(self) -> int:
        """Total tasks that ran to completion without raising."""
        with self._lock:
            return self._tasks_completed

    @property
    def tasks_failed(self) -> int:
        """Total tasks that raised an exception (logged, pool unaffected)."""
        with self._lock:
            return self._tasks_failed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _drain_queue(self, deadline: float, timeout: float) -> None:
        """Phase 1 of shutdown: wait for queued work to finish, bounded.

        Waits until ``unfinished_tasks`` reaches zero — i.e. every queued
        task has been picked up *and* finished (workers call
        ``task_done()`` in a ``finally``). Bounded by *deadline* so a
        wedged task is logged and abandoned by shutdown (the daemon
        workers still finish it afterwards), never a hang.
        """
        while self._queue.unfinished_tasks > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "BoundedThreadPool: shutdown timeout (%.1fs) expired "
                    "with %d task(s) still unfinished",
                    timeout,
                    self._queue.unfinished_tasks,
                )
                return
            time.sleep(min(0.02, remaining))

    def _worker_loop(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                if self._shutdown:
                    return
                continue

            if item is _SENTINEL:
                # Balance the put() so unfinished_tasks stays honest for
                # the drain phase (and for a second shutdown() call).
                self._queue.task_done()
                return

            fn, args, kwargs = item
            try:
                fn(*args, **kwargs)
            except Exception:
                # A failing task must not kill the worker: count it, log
                # it, and keep the loop draining.
                with self._lock:
                    self._tasks_failed += 1
                logger.exception("BoundedThreadPool: unhandled exception in task")
            else:
                with self._lock:
                    self._tasks_completed += 1
            finally:
                self._queue.task_done()
