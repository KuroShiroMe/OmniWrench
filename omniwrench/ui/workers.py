"""Hintergrundausführung, damit die Oberfläche bei Downloads/Installationen nicht einfriert.

* run_async()   - fn in einem Thread, Callbacks wieder im GUI-Thread
* call_in_gui() - aus einem Thread heraus etwas im GUI-Thread ausführen (z. B. Rückfrage-Dialog) und warten
"""

from __future__ import annotations

import logging
import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication, QObject, QRunnable, Qt, QThread, QThreadPool, Signal

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


class _GuiInvoker(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run, Qt.ConnectionType.BlockingQueuedConnection)

    def _run(self, job: Callable[[], None]) -> None:
        job()


_invoker: _GuiInvoker | None = None
_invoker_lock = threading.Lock()


def _get_invoker(app: QCoreApplication) -> _GuiInvoker:
    global _invoker
    with _invoker_lock:
        if _invoker is None:
            _invoker = _GuiInvoker()
            _invoker.moveToThread(app.thread())
        return _invoker


def call_in_gui(fn: Callable[[], Any]) -> Any:
    """Führt fn im GUI-Thread aus und liefert das Ergebnis; im GUI-Thread selbst direkt.

    Gedacht für Hintergrundaufgaben, die kurz etwas fragen müssen (Dialoge gehen nur im GUI-Thread).
    """
    app = QCoreApplication.instance()
    if app is None or QThread.currentThread() is app.thread():
        return fn()
    box: dict[str, Any] = {}

    def job() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 - im aufrufenden Thread erneut auslösen
            box["error"] = exc

    _get_invoker(app).call.emit(job)
    if "error" in box:
        raise box["error"]
    return box.get("result")
