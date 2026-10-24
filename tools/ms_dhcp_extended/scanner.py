"""Serverprüfung im Hintergrund: eigener Thread mit eigenem Zugriff, damit die Bedienung währenddessen frei bleibt.

Der Prüf-Zugriff meldet sich mit denselben Anmeldedaten an wie der Hauptzugriff (DhcpService.clone_for/attach)
und liest alle Daten gebündelt und parallel (cim_many, Thread-Pool). Jeder Scope wird ausgewertet, sobald
seine Daten da sind; die Ergebnisse kommen als Qt-Signale in den GUI-Thread. Abbrechen stoppt die
Sammelabfragen sofort, die nächste Prüfung meldet sich neu an.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from .service import UserError

THREADS = 8


class Scanner(QObject):
    progress = Signal(str, int, int)
    scope_done = Signal(str, object, int, int)
    finished = Signal(object)       # Prüfergebnis (dict), bei Abbruch mit partial=True
    failed = Signal(str)
    running_changed = Signal(bool)

    def __init__(self, backend_factory, main_svc_getter, log, parent=None):
        super().__init__(parent)
        self._factory = backend_factory
        self._main = main_svc_getter
        self._log = log
        self._host = None
        self._attached = False
        self._svc = None
        self._lock = threading.Lock()
        self.running = False

    def start(self, with_leases: bool, with_partner: bool, with_dns: bool = False) -> bool:
        main = self._main()
        if self.running or not main.server:
            return False
        self.running = True
        self.running_changed.emit(True)
        threading.Thread(target=self._run, args=(main, with_leases, with_partner, with_dns), daemon=True,
                         name="DhcpExt-Pruefung").start()
        return True

    def _run(self, main, with_leases: bool, with_partner: bool, with_dns: bool) -> None:
        try:
            with self._lock:
                if self._host is None:
                    self._host = self._factory()
                    self._attached = False
                svc = main.clone_for(self._host, log=lambda t, e=False: e and self._log(t, e),
                                     progress=lambda t, i=0, n=0: self.progress.emit(t, i, n))
                self._svc = svc
            if not self._attached:
                svc.attach()
                self._attached = True
            scan = svc.fast_scan(with_leases, with_partner,
                                 on_scope=lambda sid, entry, i, n: self.scope_done.emit(sid, entry, i, n), threads=THREADS,
                                 check_dns=with_dns)
            if scan.get("partial"):
                self._drop_host()
            self.finished.emit(scan)
        except UserError as e:
            self._drop_host()
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001 - Fehler gehören in die Oberfläche, nicht in den Thread
            self._drop_host()
            self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            self._svc = None
            self.running = False
            self.running_changed.emit(False)

    def cancel(self) -> None:
        svc = self._svc
        if svc is not None:
            svc.cancel.set()
        host = self._host
        if host is not None and hasattr(host, "kill"):
            host.kill()

    def _drop_host(self) -> None:
        host, self._host, self._attached = self._host, None, False
        if host is not None:
            try:
                host.close()
            except Exception:  # noqa: BLE001
                pass

    def reset(self) -> None:
        """Abmelden/Schließen: laufende Prüfung abbrechen, Prüf-Host beenden."""
        self.cancel()
        self._drop_host()
