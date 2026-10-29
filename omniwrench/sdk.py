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
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from omniwrench import __version__ as APP_VERSION  # noqa: F401 - Re-Export für Tools
from omniwrench.core import credentials
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
    "pick_credential", "CredentialField", "Credential", "CredentialProvider", "AuthField",
    "AuthenticationRequired", "device_pixel_ratio", "fit_to_screen",
]

# Für Tools, die eigene Passwortmanager-Anbieter bereitstellen
Credential = credentials.Credential
CredentialProvider = credentials.CredentialProvider
AuthField = credentials.AuthField
AuthenticationRequired = credentials.AuthenticationRequired


def pick_credential(parent=None) -> tuple[str, str] | None:
    """Öffnet den Auswahldialog des Passwortmanagers und liefert (Benutzer, Passwort) oder None.

    Durchsucht alle verbundenen Manager. Das Passwort wird erst nach der Auswahl abgerufen.
    """
    from omniwrench.ui.credentials import pick_credential as _pick
    cred = _pick(parent)
    if cred is None:
        return None
    full = credentials.manager().resolve(cred.ref)
    return (full.username, full.password) if full else None


def CredentialField(value: dict | None = None, parent=None, settings=None, key: str = ""):  # noqa: N802
    """Fertiges Feld für Zugangsdaten: Auswahlliste gespeicherter Einträge + Buttons
    "Aus Passwortmanager" / "Manuell" / "Entfernen".

    Mit settings + key bindet sich das Feld an eine Tool-Einstellung (Typ "credential") und
    speichert Änderungen selbst:

        self.login = CredentialField(settings=self.context.settings, key="credential")
        ...
        user, password = self.login.resolve()     # Abruf erst hier (einmal pro Sitzung)
        self.login.resolve_async(self._start)     # dasselbe ohne die Oberfläche zu blockieren
    """
    from omniwrench.ui.credentials import CredentialField as _Field
    return _Field(value, parent, settings=settings, key=key)


def run_async(fn, on_done=None, on_error=None, on_progress=None) -> None:
    """Führt fn in einem Hintergrund-Thread aus; die Callbacks laufen wieder im GUI-Thread.

    Ist on_progress gesetzt, erhält fn als einziges Argument eine progress(str)-Funktion.
    """
    from omniwrench.ui.workers import run_async as _run_async
    _run_async(fn, on_done, on_error, on_progress)


def device_pixel_ratio() -> float:
    """Pixelverhältnis des schärfsten Bildschirms (Windows-Skalierung x OmniWrench-Skalierung).

    Selbst gezeichnete Bilder in logische Größe x diesem Wert rendern und
    pixmap.setDevicePixelRatio(...) setzen - dann bleiben sie von 1k bis 8k scharf.
    """
    from omniwrench.ui.scaling import device_pixel_ratio as _ratio
    return _ratio()


def fit_to_screen(widget, width: int, height: int) -> None:
    """Wie widget.resize(width, height), aber höchstens so groß wie der freie Bildschirmbereich."""
    from omniwrench.ui.scaling import fit_to_screen as _fit
    _fit(widget, width, height)


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

    def is_lost(self, key: str) -> bool:
        """True, wenn der Wert beim Zurücksetzen des Masterpassworts verworfen und noch nicht neu gesetzt wurde."""
        return self._vault.is_lost(self._prefix + key)


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

    # Passwortmanager-Anbieter
    def register_credential_provider(self, provider: "credentials.CredentialProvider") -> None:
        """Stellt einen weiteren Passwortmanager im Auswahldialog bereit (wird beim
        Deinstallieren des Tools automatisch entfernt)."""
        credentials.manager().register(provider, owner=self.tool_id)

    def unregister_credential_provider(self, provider_id: str) -> None:
        credentials.manager().unregister(provider_id)

    # PowerShell-Helfer
    def run_powershell(self, script: str, stdin: str | None = None, timeout: float | None = 300,
                       shell: str = "powershell") -> PSResult:
        """shell="pwsh" nutzt PowerShell 7 statt Windows PowerShell 5.1."""
        return run_ps(script, stdin=stdin, timeout=timeout, shell=shell)

    def run_powershell_json(self, script: str, stdin: str | None = None, timeout: float | None = 300):
        return run_ps_json(script, stdin=stdin, timeout=timeout)

    def run_powershell_elevated(self, script: str, timeout: float | None = 3600,
                                on_output: Callable[[str], None] | None = None) -> PSResult:
        """Mit Administratorrechten (UAC-Abfrage, entfällt bei bereits erhöhtem Programm).
        on_output erhält jede Ausgabezeile sofort; returncode 1223 = UAC-Abfrage abgelehnt."""
        return run_ps_elevated(script, timeout=timeout, on_output=on_output)

    def get_credential(self, key: str) -> tuple[str, str] | None:
        """(Benutzer, Passwort) des in einer "credential"-Einstellung ausgewählten Eintrags.

        Verweise auf Passwortmanager werden erst hier abgerufen (einmal pro Sitzung, nur im
        Speicher). Braucht ein Manager neue Zugangsdaten, fragt das Programm selbst nach.
        """
        value = credentials.normalize_value(self.settings.get(key))
        if not value["items"]:
            return None
        return credentials.resolve_item(value["items"][value["selected"]])

    def get_credential_async(self, key: str, on_done, on_error=None) -> None:
        """Wie get_credential(), blockiert aber die Oberfläche nicht: externe Manager werden im
        Hintergrund abgefragt, danach läuft on_done((benutzer, passwort) | None) im GUI-Thread.
        """
        from omniwrench.ui.credentials import resolve_async
        value = credentials.normalize_value(self.settings.get(key))
        resolve_async(value["items"][value["selected"]] if value["items"] else None, on_done, on_error)

    def get_credentials(self, key: str) -> list[dict]:
        """Alle in einer "credential"-Einstellung hinterlegten Einträge (ohne Passwörter abzurufen)."""
        return credentials.normalize_value(self.settings.get(key))["items"]


# Zugriffsstufen für KI-Funktionen (Seite „KI-Zugriff“): Mindeststufe, ab der eine Funktion angeboten wird
AI_DESCRIBE, AI_OVERVIEW, AI_READ, AI_CHANGE = 1, 2, 3, 4


class ToolContext(_ContextBase):
    """Wird jeder Tool-Instanz beim Start übergeben."""

    def __init__(self, *args, notify: Callable[[str], None] | None = None,
                 open_settings: Callable[[], None] | None = None,
                 ask_assistant: Callable[..., None] | None = None, ai_services: Callable[[], Any] | None = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._notify = notify
        self._open_settings = open_settings
        self._ask_assistant = ask_assistant
        self._ai_services = ai_services

    # ------------------------------------------------------------ KI-Assistent (seit 0.9.0)
    def ai_function(self, name: str, description: str, handler: Callable[[dict, Any], Any],
                    parameters: dict | None = None, level: int = AI_READ, confirm: bool = False,
                    summary: Callable[[dict], str] | None = None) -> None:
        """Stellt dem Assistenten eine Funktion dieses Tools bereit (gilt, solange der Tab offen ist).

        name/description auf Englisch (für das Sprachmodell), parameters als JSON-Schema.
        handler(args, call) läuft im Hintergrund; call.in_gui(fn) führt fn im GUI-Thread aus,
        call.level ist die wirksame Zugriffsstufe. Rückgabe: Text oder JSON-fähige Daten.
        level: Mindeststufe (AI_DESCRIBE … AI_CHANGE). Ab AI_CHANGE fragt das Programm vor dem
        Ausführen nach; summary(args) liefert dafür den Text (in der Sprache des Benutzers).
        Werte unter Schlüsseln wie host/server/user werden bei aktiver Verfremdung ersetzt.
        """
        from omniwrench.ai import functions
        functions.register(functions.Function(
            name=name, description=description, handler=handler,
            parameters=parameters or {"type": "object", "properties": {}}, source=self.manifest.id,
            level=level, confirm=confirm or level >= AI_CHANGE, summary=summary, owner=self))

    def ai_remove_functions(self) -> None:
        """Entfernt alle Funktionen dieser Tool-Instanz (passiert beim Schließen des Tabs automatisch)."""
        from omniwrench.ai import functions
        functions.unregister_owner(self)

    def ai_set_access(self, level: int | None = None, pseudo: bool | None = None) -> None:
        """Vorübergehende KI-Zugriffsstufe/Verfremdung dieses Tools, z. B. aus dem gewählten Server-Favoriten.
        None für beides = wieder die Einstellung des Tools verwenden."""
        from omniwrench.ai import access
        access.set_runtime(self.manifest.id, level, pseudo)

    def ai_level(self) -> int:
        """Wirksame Zugriffsstufe dieses Tools (ohne Ausnahmen je Assistent)."""
        from omniwrench.ai import access
        from omniwrench.core.settings import AppSettings
        return access.level(AppSettings(), self.manifest.id)

    def ai_services(self):
        """KI-Dienste des Hauptprogramms (Verbindungen, Datenablage, Chat-Widget) für KI-Tools; None ohne Hauptfenster.
        Siehe omniwrench.ui.ai_services.AIServices."""
        return self._ai_services() if self._ai_services else None

    def ask_assistant(self, context: str, title: str = "") -> None:
        """Öffnet „Assistent fragen …“ mit einem Element des Tools als Kontext (Text, z. B. ein Lease)."""
        if self._ask_assistant:
            self._ask_assistant(context, title or self.manifest.display_name, self.manifest.id)

    def add_ask_action(self, menu, context: "str | Callable[[], str]", title: str = ""):
        """Fügt einem Kontextmenü den Eintrag „Assistent fragen …“ hinzu. context: Text oder Funktion."""
        if not self._ask_assistant:
            return None
        act = menu.addAction("✦ " + tr("ai.ask.action"))
        act.triggered.connect(lambda: self.ask_assistant(context() if callable(context) else context, title))
        return act

    def notify(self, message: str) -> None:
        """Zeigt eine Meldung in der Statusleiste des Hauptprogramms."""
        if self._notify:
            self._notify(f"{self.manifest.display_name}: {message}")

    def open_settings(self) -> None:
        """Öffnet den Einstellungsdialog dieses Tools."""
        if self._open_settings:
            self._open_settings()


_install_chooser: "Callable[[str, str, list], list[str] | None] | None" = None


def set_install_chooser(fn) -> None:
    """Hauptfenster: Dialog für InstallContext.choose (wird aus dem Installations-Thread aufgerufen)."""
    global _install_chooser
    _install_chooser = fn


class InstallContext(_ContextBase):
    """Wird an die Funktionen in install.py übergeben."""

    def __init__(self, *args, progress: Callable[[str], None] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._progress = progress

    def choose(self, title: str, text: str, options: list[tuple[str, str, bool]]) -> list[str]:
        """Fragt bei der Installation, welche optionalen Teile installiert werden sollen (Opt-out: vorbelegt ist,
        was in options True hat). options: [(ID, Anzeigetext, vorbelegt)]. Liefert die gewählten IDs; ohne
        Oberfläche (Tests, Kommandozeile) die vorbelegten."""
        defaults = [oid for oid, _label, on in options if on]
        if _install_chooser is None or not options:
            return defaults
        try:
            chosen = _install_chooser(title, text, options)
        except Exception:  # noqa: BLE001 - im Zweifel die Vorgabe
            return defaults
        return defaults if chosen is None else list(chosen)

    def ai_packages(self, packages: list[str]) -> None:
        """Installiert Zusatzpakete der KI-Tools in den gemeinsamen Paketordner (mit Fortschritt im Protokoll)."""
        from omniwrench.ai import audio
        need = audio.missing(tuple(packages))
        if not need:
            return
        self.report(tr("prog.pip_install", packages=", ".join(audio.PIP_NAMES.get(p, p) for p in need)))
        err = audio.install_packages(need, self.report)
        if err:
            raise RuntimeError(tr("err.pip") + "\n" + err)

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
        args = ["install", "--disable-pip-version-check", "--upgrade", "--target", str(target), *packages]
        log_file = None
        if getattr(sys, "frozen", False):
            # EXE-Build: pip ist eingebaut (main.py --pip); Fensterprogramm hat evtl. keine Ausgabe -> Logdatei
            fd, name = tempfile.mkstemp(prefix="omniwrench_pip_", suffix=".log")
            os.close(fd)  # offener Handle sperrt die Datei unter Windows (WinError 32 beim Löschen)
            log_file = Path(name)
            cmd = [sys.executable, "--pip", *args, "--prefer-binary", "--log", str(log_file)]
        else:
            cmd = [sys.executable, "-m", "pip", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              creationflags=0x08000000 if sys.platform == "win32" else 0)
        details = proc.stderr or ""
        if log_file:
            if not details.strip() and log_file.exists():
                details = log_file.read_text(encoding="utf-8", errors="replace")
            try:
                log_file.unlink(missing_ok=True)
            except OSError:
                self.log.debug("pip-Logdatei nicht löschbar: %s", log_file)
        if proc.returncode != 0:
            raise RuntimeError(tr("err.pip") + "\n" + details[-2000:])


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
