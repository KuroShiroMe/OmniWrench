"""Hintergrundausführung, damit die Oberfläche bei Downloads/Installationen nicht einfriert."""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

log = logging.getLogger(__name__)
_active: set["_Task"] = set()


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], with_progress: bool):
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.with_progress = with_progress
        self.signals = _Signals()

    def run(self) -> None:
        try:
            result = self.fn(self.signals.progress.emit) if self.with_progress else self.fn()
        except Exception as exc:  # noqa: BLE001
            log.error("Hintergrundaufgabe fehlgeschlagen:\n%s", traceback.format_exc())
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.signals.done.emit(result)


def run_async(fn: Callable[..., Any], on_done: Callable[[Any], None] | None = None,
              on_error: Callable[[str], None] | None = None,
              on_progress: Callable[[str], None] | None = None) -> None:
    """Führt fn in einem Thread aus. Ist on_progress gesetzt, erhält fn eine progress(str)-Funktion."""
    task = _Task(fn, with_progress=on_progress is not None)
    _active.add(task)

    def finish(*_):
        _active.discard(task)

    if on_done:
        task.signals.done.connect(on_done)
    if on_error:
        task.signals.failed.connect(on_error)
    if on_progress:
        task.signals.progress.connect(on_progress)
    task.signals.done.connect(finish)
    task.signals.failed.connect(finish)
    QThreadPool.globalInstance().start(task)
