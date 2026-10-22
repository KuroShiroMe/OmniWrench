"""Ablaufsteuerung: Abläufe sind Generatoren, die Hintergrundaufgaben (Job) liefern.

    def flow(self):
        data = yield Job(lambda: svc.get_scope(sid), tr("status.loading"))
        if not confirm(...):            # Dialoge laufen zwischen den Jobs im GUI-Thread
            return
        yield Job(lambda: svc.scope_set(sid, Name=name))

Das Ergebnis eines Jobs kommt per send() zurück, eine Ausnahme per throw() - so bleiben try/except im
Ablauf lesbar wie bei synchronem Code. Es läuft immer nur ein Ablauf; währenddessen ist die Oberfläche
gesperrt (Dialoge ausgenommen).
"""

from __future__ import annotations

import logging
import traceback
from typing import Callable

from PySide6.QtCore import QObject, Signal

from omniwrench.sdk import run_async

from .service import UserError

log = logging.getLogger(__name__)


class Job:
    def __init__(self, fn: Callable, status: str = "", cancellable: bool = False):
        self.fn = fn
        self.status = status
        self.cancellable = cancellable


class Runner(QObject):
    busy_changed = Signal(bool, bool)     # (beschäftigt, abbrechbar)
    status = Signal(str)
    failed = Signal(str)                  # Fehlertext eines unbehandelten Fehlers

    def __init__(self):
        super().__init__()
        self.gen = None
        self.on_finish: Callable[[], None] | None = None

    @property
    def active(self) -> bool:
        return self.gen is not None

    def start(self, gen, on_finish: Callable[[], None] | None = None) -> bool:
        if gen is None:
            return False
        if self.gen is not None:
            gen.close()
            self.status.emit("busy")
            return False
        self.gen = gen
        self.on_finish = on_finish
        self._step(False, None)
        return True

    def _step(self, is_error: bool, value) -> None:
        gen = self.gen
        try:
            job = gen.throw(value) if is_error else gen.send(value)
        except StopIteration:
            self._end()
            return
        except UserError as e:
            self._end()
            self.failed.emit(str(e))
            return
        except Exception as e:  # noqa: BLE001 - Programmfehler sichtbar machen statt still abzubrechen
            log.exception("DHCP-Ablauf")
            self._end()
            self.failed.emit(f"{e}\n\n{traceback.format_exc(limit=6)}")
            return
        if not isinstance(job, Job):
            # Generator lieferte etwas anderes: unmittelbar zurückgeben (erlaubt "yield" ohne Job)
            self._step(False, job)
            return
        if job.status:
            self.status.emit(job.status)
        self.busy_changed.emit(True, job.cancellable)

        def work():
            try:
                return (True, job.fn())
            except Exception as e:  # noqa: BLE001 - Ausnahme samt Typ an den Ablauf zurückgeben
                return (False, e)

        def done(res):
            self.busy_changed.emit(False, False)
            ok, val = res
            if self.gen is gen:
                self._step(not ok, val)

        def error(text: str):
            self.busy_changed.emit(False, False)
            if self.gen is gen:
                self._step(True, RuntimeError(text))

        run_async(work, done, error)

    def _end(self) -> None:
        self.gen = None
        self.busy_changed.emit(False, False)
        cb, self.on_finish = self.on_finish, None
        if cb:
            cb()

    def abort(self) -> None:
        if self.gen is not None:
            try:
                self.gen.close()
            except Exception:  # noqa: BLE001
                pass
            self._end()
