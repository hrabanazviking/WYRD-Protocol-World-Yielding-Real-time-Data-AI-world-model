"""pool.py — Bounded daemon-thread pool for fire-and-forget push operations.

All WYRD bridge fire-and-forget operations (push_observation, push_fact, sync_entity)
spawn daemon threads.  Under sustained load this can accumulate thousands of threads.
:class:`BoundedThreadPool` caps the live thread count, queuing excess tasks until
a slot is free.

Usage::

    from wyrdforge.hardening.pool import BoundedThreadPool

    pool = BoundedThreadPool(max_workers=16)

    pool.submit(lambda: requests.post(url, json=body))
    pool.submit(my_push_function, arg1, arg2)

    # Graceful drain (waits up to timeout seconds for queued tasks)
    pool.shutdown(wait=True, timeout=5.0)
"""
from __future__ import annotations

import logging
import queue
import threading
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
        """Stop accepting new tasks and optionally wait for queued tasks to finish.

        Args:
            wait:    If True, wait up to *timeout* seconds for workers to drain.
            timeout: Maximum seconds to wait per worker thread.
        """
        self._shutdown = True
        for _ in self._workers:
            try:
                self._queue.put_nowait(_SENTINEL)
            except queue.Full:
                pass
        if wait:
            for t in self._workers:
                t.join(timeout=timeout)

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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                if self._shutdown:
                    return
                continue

            if item is _SENTINEL:
                return

            fn, args, kwargs = item
            try:
                fn(*args, **kwargs)
            except Exception:
                logger.exception("BoundedThreadPool: unhandled exception in task")
            finally:
                self._queue.task_done()
