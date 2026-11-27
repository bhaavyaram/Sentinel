"""A tiny background worker: runs one function every N seconds on its own thread."""

import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)


class PeriodicWorker:
    def __init__(self, name: str, interval_s: float, task: Callable[[], None]) -> None:
        self._name = name
        self._interval_s = interval_s
        self._task = task
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._task()
            except Exception:  # a failing task must never kill the worker
                log.exception("worker %s: task failed", self._name)
            self._stop.wait(self._interval_s)