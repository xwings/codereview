"""Flushed stderr status and a heartbeat while synchronous work is running."""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Iterator

INTERVAL_SECONDS = 15


def emit(message: str, *, model: str = "-", agent: str = "Host", phase: str = "prepare") -> None:
    """Write one timestamped status or detailed exchange to stderr."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{model}] [{agent}] [{phase}] {message}", file=sys.stderr, flush=True)


@contextmanager
def activity(label: str, *, model: str = "-", agent: str = "Host",
             phase: str = "prepare") -> Iterator[Callable[..., None]]:
    """Announce work; yield a status updater; stop the ticker on every exit."""
    stopped = threading.Event()
    lock = threading.Lock()
    started = time.monotonic()
    current, since = label, started
    context = {"model": model, "agent": agent, "phase": phase}
    interval = INTERVAL_SECONDS
    errors = []

    def update(message: str, *, model: str | None = None, agent: str | None = None,
               phase: str | None = None) -> None:
        nonlocal current, since
        with lock:
            current, since = message, time.monotonic()
            context.update({key: value for key, value in
                            (("model", model), ("agent", agent), ("phase", phase)) if value is not None})
            emit(f"{current}...", **context)

    def heartbeat() -> None:
        while not stopped.wait(interval):
            with lock:
                now = time.monotonic()
                elapsed, total = now - since, now - started
                try:
                    emit(f"Still working: {current} ({elapsed:.0f}s elapsed; {total:.0f}s total)", **context)
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
    emit(f"Done: {label} ({time.monotonic() - started:.0f}s elapsed)", **context)
