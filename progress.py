"""Flushed stderr status and a heartbeat while synchronous work is running."""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator

INTERVAL_SECONDS = 15


@contextmanager
def activity(label: str) -> Iterator[Callable[[str], None]]:
    """Announce work; yield a status updater; stop the ticker on every exit."""
    stopped = threading.Event()
    lock = threading.Lock()
    started = time.monotonic()
    current, since = label, started
    interval = INTERVAL_SECONDS
    errors = []

    def update(message: str) -> None:
        nonlocal current, since
        with lock:
            current, since = message, time.monotonic()
            print(f"  {current}...", file=sys.stderr, flush=True)

    def heartbeat() -> None:
        while not stopped.wait(interval):
            with lock:
                elapsed = time.monotonic() - since
                try:
                    print(f"  Still working: {current} ({elapsed:.0f}s elapsed)",
                          file=sys.stderr, flush=True)
                except OSError as exc:
                    errors.append(exc)
                    return

    update(label)
    worker = threading.Thread(target=heartbeat, name="review-progress", daemon=True)
    worker.start()
    try:
        yield update
    finally:
        stopped.set()
        worker.join()
    if errors:
        raise errors[0]
    print(f"  Done: {label} ({time.monotonic() - started:.0f}s elapsed)",
          file=sys.stderr, flush=True)
