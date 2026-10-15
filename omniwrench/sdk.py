"""Öffentliche Schnittstelle für Tool-Entwickler.

Ein Tool importiert ausschließlich aus diesem Modul (und PySide6):

    from omniwrench.sdk import ToolBase

    class Tool(ToolBase):
        def create_widget(self, parent):
            ...

Siehe docs/TOOL_ENTWICKLUNG.md für die vollständige Beschreibung.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from omniwrench import __version__ as APP_VERSION  # noqa: F401 - Re-Export für Tools
from omniwrench.core.i18n import tool_translator, tr
from omniwrench.core.powershell import PSResult, ps_quote, run_ps, run_ps_elevated, run_ps_json

# Reservierter Einstellungsschlüssel für die Sprachwahl eines Tools ("auto" oder Sprachcode)
LANGUAGE_KEY = "_language"

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

    from omniwrench.core.manifest import ToolManifest
    from omniwrench.core.tool_settings import ToolSettingsStore
    from omniwrench.core.vault import Vault

__all__ = [
    "APP_VERSION", "ToolBase", "ToolContext", "InstallContext", "PSResult", "ps_quote", "run_async", "LANGUAGE_KEY",
]


def run_async(fn, on_done=None, on_error=None, on_progress=None) -> None:
    """Führt fn in einem Hintergrund-Thread aus; die Callbacks laufen wieder im GUI-Thread.

    Ist on_progress gesetzt, erhält fn als einziges Argument eine progress(str)-Funktion.
    """
    from omniwrench.ui.workers import run_async as _run_async
    _run_async(fn, on_done, on_error, on_progress)


class SecretStore:
    """Freier Zugriff eines Tools auf seinen eigenen Bereich im Tresor."""

    def __init__(self, tool_id: str, vault: "Vault"):
        self._prefix = f"tool:{tool_id}:_"
        self._vault = vault

    def get(self, key: str, default: Any = None) -> Any:
        return self._vault.get(self._prefix + key, default)

    def set(self, key: str, value: Any) -> None:
        self._vault.set(self._prefix + key, value)

    def delete(self, key: str) -> None:
        self._vault.delete(self._prefix + key)


class _ContextBase:
    def __init__(self, manifest: "ToolManifest", tool_dir: Path, data_dir: Path,
                 settings: "ToolSettingsStore", vault: "Vault"):
        self.manifest = manifest
        self.tool_id = manifest.id
        self.tool_dir = tool_dir
        self.data_dir = data_dir
        self.settings = settings
        self.secrets = SecretStore(manifest.id, vault)
        self.log = logging.getLogger(f"tool.{manifest.id}")
        self.translator = tool_translator(tool_dir, settings.get(LANGUAGE_KEY))

    # Mehrsprachigkeit
    @property
    def language(self) -> str:
        """Aktive Sprache des Tools (z. B. "de", "en", "de_bad")."""
        return self.translator.language

    def tr(self, key: str, default: str | None = None, **kwargs) -> str:
        """Übersetzt einen Text aus <tool>/locales/<sprache>.json (Fallback: en.json, dann default/key)."""
        return self.translator.tr(key, default, **kwargs)

    # PowerShell-Helfer
    def run_powershell(self, script: str, stdin: str | None = None, timeout: float | None = 300) -> PSResult:
        return run_ps(script, stdin=stdin, timeout=timeout)

    def run_powershell_json(self, script: str, stdin: str | None = None, timeout: float | None = 300):
        return run_ps_json(script, stdin=stdin, timeout=timeout)

    def run_powershell_elevated(self, script: str, timeout: float | None = 3600) -> PSResult:
        return run_ps_elevated(script, timeout=timeout)

    def get_credential(self, key: str) -> tuple[str, str] | None:
        """Liefert (Benutzer, Passwort) einer Einstellung vom Typ "credential"."""
        value = self.settings.get(key)
        if not value or not value.get("username"):
            return None
        return value.get("username", ""), value.get("password", "")


class ToolContext(_ContextBase):
    """Wird jeder Tool-Instanz beim Start übergeben."""

    def __init__(self, *args, notify: Callable[[str], None] | None = None,
                 open_settings: Callable[[], None] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._notify = notify
        self._open_settings = open_settings

    def notify(self, message: str) -> None:
        """Zeigt eine Meldung in der Statusleiste des Hauptprogramms."""
        if self._notify:
            self._notify(f"{self.manifest.display_name}: {message}")

    def open_settings(self) -> None:
        """Öffnet den Einstellungsdialog dieses Tools."""
        if self._open_settings:
            self._open_settings()


class InstallContext(_ContextBase):
    """Wird an die Funktionen in install.py übergeben."""

    def __init__(self, *args, progress: Callable[[str], None] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._progress = progress

    def report(self, message: str) -> None:
        """Schreibt eine Zeile in das Installationsprotokoll."""
        self.log.info(message)
        if self._progress:
            self._progress(message)

    def pip_install(self, *packages: str) -> None:
        """Installiert Python-Pakete in den privaten lib-Ordner des Tools."""
        if not packages:
            return
        target = self.tool_dir / "_lib"
        self.report(tr("prog.pip_install", packages=", ".join(packages)))
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade",
             "--target", str(target), *packages],
            capture_output=True, text=True,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        if proc.returncode != 0:
            raise RuntimeError(tr("err.pip") + "\n" + proc.stderr[-2000:])


class ToolBase:
    """Basisklasse für alle Tools.

    Pro geöffnetem Tab wird eine eigene Instanz erzeugt.
    """

    def __init__(self, context: ToolContext):
        self.context = context

    def create_widget(self, parent: "QWidget | None" = None) -> "QWidget":
        """Erzeugt die Oberfläche des Tools (wird im Tab angezeigt)."""
        raise NotImplementedError

    def on_settings_changed(self, changed_keys: set[str]) -> None:
        """Wird aufgerufen, wenn der Benutzer Einstellungen des Tools geändert hat.

        Bei einem Sprachwechsel baut das Hauptprogramm den Tab automatisch mit einer
        neuen Instanz neu auf - dafür ist hier nichts zu tun.
        """

    def can_close(self) -> bool:
        """Rückgabe False verhindert das Schließen des Tabs (z. B. ungespeicherte Änderungen)."""
        return True

    def shutdown(self) -> None:
        """Aufräumen beim Schließen des Tabs (Threads stoppen, Verbindungen trennen ...)."""
