"""Bausteine für die KI-Tools (Pixelizer, Kreeli, Mr. Zurkon …): Hinweisseiten, einklappbare Abschnitte,
Paketinstallation mit Fortschritt, Offline-Sprache (Whisper lokal, Piper) und Audioausgabe auf dem aktuellen
Standardgerät. Texte kommen aus den Sprachdateien des Hauptprogramms (ai.kit.*).
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from omniwrench.ai import audio
from omniwrench.ai import local_speech as ls
from omniwrench.core.i18n import tr
from omniwrench.sdk import ToolBase

from .workers import run_async

WHISPER = ls.WHISPER
PIPER = ls.PIPER
TOOL_NAME = "tool.name"                          # Schlüssel in den Sprachdateien jedes Tools
OUTPUT_KEY = "ai_audio_output"                   # App-Einstellung: Ausgabegerät (leer = Windows-Standard)


# ------------------------------------------------------------------ Seiten und Abschnitte
class NoBotPage(QWidget):
    """Ausgegraute Seite mit Hinweis und Knopf zu den Optionen (kein passender Assistent verbunden)."""

    def __init__(self, text: str, button: str, on_click, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.addStretch()
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setEnabled(False)
        lay.addWidget(self.label)
        row = QHBoxLayout()
        row.addStretch()
        self.button = QPushButton(button)
        self.button.clicked.connect(on_click)
        row.addWidget(self.button)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()


class Section(QWidget):
    """Einklappbarer Abschnitt mit Überschrift."""

    def __init__(self, title: str, content: QWidget, expanded: bool = False):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.head = QToolButton(text=title)
        self.head.setCheckable(True)
        self.head.setChecked(expanded)
        self.head.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.head.setStyleSheet("QToolButton { border: none; font-weight: 600; }")
        self.head.toggled.connect(self._toggle)
        lay.addWidget(self.head)
        self.content = content
        lay.addWidget(content)
        self._toggle(expanded)

    def _toggle(self, on: bool) -> None:
        self.head.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.content.setVisible(on)


# ------------------------------------------------------------------ Auswahl bei der Installation
def choose_options(parent, title: str, text: str, options: list[tuple[str, str, bool]]) -> list[str] | None:
    """Dialog für InstallContext.choose: optionale Teile an-/abwählen (Opt-out). None = Vorgabe übernehmen."""
    from PySide6.QtWidgets import QCheckBox
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(520)
    lay = QVBoxLayout(dlg)
    head = QLabel(text)
    head.setWordWrap(True)
    lay.addWidget(head)
    boxes = []
    for oid, label, on in options:
        box = QCheckBox(label)
        box.setChecked(bool(on))
        lay.addWidget(box)
        boxes.append((oid, box))
    note = QLabel(tr("ai.kit.choose_later"))
    note.setWordWrap(True)
    note.setEnabled(False)
    lay.addWidget(note)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    buttons.accepted.connect(dlg.accept)
    lay.addWidget(buttons)
    dlg.exec()
    return [oid for oid, box in boxes if box.isChecked()]


# ------------------------------------------------------------------ Installation mit Fortschritt
_PERCENT = re.compile(r"(\d{1,3})\s*%")


class ProgressDialog(QDialog):
    """Fenster mit Fortschrittsbalken für Installationen und Downloads.

    work(progress) läuft im Hintergrund; progress(text) aktualisiert die Zeile, „NN %“ im Text stellt den Balken
    (sonst läuft er als Lauflicht). Ergebnis in .result / .error; exec() endet, wenn die Arbeit fertig ist.
    """

    def __init__(self, title: str, work: Callable, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.result = None
        self.error = ""
        lay = QVBoxLayout(self)
        self.text = QLabel(tr("ai.kit.starting"))
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        lay.addWidget(self.bar)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setEnabled(False)
        lay.addWidget(self.detail)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.rejected.connect(self.reject)
        self.buttons.setEnabled(False)
        lay.addWidget(self.buttons)
        self._work = work

    def _progress(self, text: str) -> None:
        m = _PERCENT.search(text or "")
        if m:
            self.bar.setRange(0, 100)
            self.bar.setValue(min(100, int(m.group(1))))
        else:
            self.bar.setRange(0, 0)
        self.text.setText(text)

    def exec(self) -> int:
        def done(result):
            self.result = result
            self.bar.setRange(0, 100)
            self.bar.setValue(100)
            self.text.setText("✓ " + tr("ai.kit.done"))
            self.accept()

        def failed(err: str):
            self.error = err.strip().splitlines()[-1] if err.strip() else "?"
            self.bar.setRange(0, 100)
            self.bar.setValue(0)
            self.text.setText("⚠ " + self.error)
            self.detail.setText(err[-600:])
            self.buttons.setEnabled(True)
        run_async(self._work, done, failed, self._progress)
        return super().exec()

    def reject(self) -> None:
        if self.buttons.isEnabled():               # während der Arbeit nicht schließbar
            super().reject()


def install_with_progress(parent, title: str, packages: list[str], extra: Callable | None = None) -> bool:
    """Pakete (und optional weitere Schritte extra(progress)) mit Fortschrittsfenster installieren."""
    need = audio.missing(tuple(packages))

    def work(progress):
        if need:
            progress(tr("ai.kit.installing", packages=", ".join(audio.PIP_NAMES.get(p, p) for p in need)))
            err = audio.install_packages(need, lambda line: progress(tr("ai.kit.pip", line=line)))
            if err:
                raise RuntimeError(err)
        if extra is not None:
            extra(progress)
        return True
    if not need and extra is None:
        return True
    dlg = ProgressDialog(title, work, parent)
    dlg.exec()
    return dlg.result is True


class DepsPage(QWidget):
    """Seite, solange Python-Pakete fehlen; installiert sie auf Knopfdruck mit Fortschrittsfenster."""
    changed = Signal()

    def __init__(self, packages: tuple[str, ...], text: str, parent=None):
        super().__init__(parent)
        self.packages = packages
        lay = QVBoxLayout(self)
        lay.addStretch()
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label)
        row = QHBoxLayout()
        row.addStretch()
        self.button = QPushButton("⬇ " + tr("ai.kit.install"))
        self.button.clicked.connect(self.install)
        row.addWidget(self.button)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()

    def install(self) -> None:
        if install_with_progress(self, tr("ai.kit.install"), list(self.packages)):
            self.changed.emit()


# ------------------------------------------------------------------ Offline-Sprache
def whisper_label(name: str) -> str:
    mb = ls.WHISPER_MODELS.get(name, ls.WHISPER_MODELS[ls.WHISPER_DEFAULT])[1]
    return tr(f"ai.kit.whisper_{name.replace('-', '_')}", mb=mb)


def local_needs(whisper_model: str = "", piper_voice: str = "") -> list[str]:
    """Was für Whisper lokal / Piper noch fehlt (Pakete, Modell, Stimme) – lesbar für den Hinweis."""
    data = audio.shared_dir()
    need = []
    if whisper_model:
        if audio.missing(("faster_whisper",)):
            need.append("faster-whisper")
        if not ls.whisper_ready(data, whisper_model):
            need.append(tr("ai.kit.need_whisper", model=whisper_model,
                           mb=ls.WHISPER_MODELS.get(whisper_model, ls.WHISPER_MODELS[ls.WHISPER_DEFAULT])[1]))
    if piper_voice:
        if audio.missing(("piper",)):
            need.append("piper-tts")
        if not ls.piper_ready(data, piper_voice):
            need.append(tr("ai.kit.need_piper", voice=piper_voice))
    return need


def setup_local(parent, whisper_model: str = "", piper_voice: str = "") -> bool:
    """Whisper lokal / Piper einrichten (nach Rückfrage, mit Fortschritt). True = bereit."""
    need = local_needs(whisper_model, piper_voice)
    if not need:
        return True
    if QMessageBox.question(parent, tr("ai.kit.local_setup"), tr("ai.kit.local_q", what="\n• ".join([""] + need))) \
            != QMessageBox.StandardButton.Yes:
        return False
    data = audio.shared_dir()
    packages = (["faster_whisper"] if whisper_model else []) + (["piper"] if piper_voice else [])

    def extra(progress):
        if whisper_model and not ls.whisper_ready(data, whisper_model):
            progress(tr("ai.kit.loading_whisper", model=whisper_model))
            ls.whisper_prepare(data, whisper_model)
        if piper_voice and not ls.piper_ready(data, piper_voice):
            ls.piper_download(data, piper_voice, lambda st: progress(tr("ai.kit.downloading", what=piper_voice,
                                                                        state=st)))
    return install_with_progress(parent, tr("ai.kit.local_setup"), packages, extra)


class LocalWhisper:
    """Platzhalter-Verbindung für „Whisper lokal“ (nichts verlässt den Rechner)."""

    def __init__(self, name: str = ""):
        self.id = WHISPER
        self.name = name or tr("ai.kit.whisper")
        self.info = None


# ------------------------------------------------------------------ Chat-Helfer
def ask_once(services, tool_id: str, conn, system: str, text: str, on_text, stop: threading.Event):
    """Eine Frage ohne Funktionen. Gibt (Antwort, decode) zurück; on_text bekommt verfremdeten Teiltext."""
    from omniwrench.ai import access, adapters
    from omniwrench.ai.pseudo import Pseudonymizer
    pseudo = Pseudonymizer({}, access.pseudo_kinds(services.settings),
                           enabled=access.pseudo_enabled(services.settings, tool_id))
    adapter = adapters.for_connection(services.connections, conn)
    result = adapter.chat(system, [{"role": "user", "content": pseudo.encode(text)}], [],
                          lambda kind, data: on_text(data, pseudo.decode) if kind == "text" else None, stop, {})
    return pseudo.decode(result.get("text") or ""), pseudo.decode


def safe_name(title: str) -> str:
    name = re.sub(r"[^\w\-. ]+", "_", title).strip(" ._")[:80]
    return name or time.strftime("Dokument %Y-%m-%d %H%M")


# ------------------------------------------------------------------ Audioausgabe
def audio_outputs() -> list[tuple[str, str]]:
    """[(ID, Name)] der Ausgabegeräte; ID als Text (QAudioDevice.id)."""
    try:
        from PySide6.QtMultimedia import QMediaDevices
    except ImportError:
        return []
    return [(bytes(d.id()).decode("utf-8", "replace"), d.description()) for d in QMediaDevices.audioOutputs()]


def output_device(settings):
    """Gewähltes Gerät oder das aktuelle Standardgerät des Systems – bei jeder Ausgabe neu ermittelt, damit ein
    Wechsel (z. B. auf Kopfhörer) ohne Neustart gilt."""
    from PySide6.QtMultimedia import QMediaDevices
    want = (settings.get(OUTPUT_KEY) or "") if settings is not None else ""
    if want:
        for d in QMediaDevices.audioOutputs():
            if bytes(d.id()).decode("utf-8", "replace") == want:
                return d
    return QMediaDevices.defaultAudioOutput()


class Player(QObject):
    """Spielt eine Audiodatei auf dem gewünschten Gerät; finished kommt am Ende, bei Fehler oder stop()."""
    finished = Signal()

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._player = None
        self._out = None

    def play(self, path: Path) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            self.finished.emit()
            return
        self.stop(emit=False)
        self._player = QMediaPlayer(self)
        self._out = QAudioOutput(output_device(self.settings), self)
        self._player.setAudioOutput(self._out)
        self._player.mediaStatusChanged.connect(
            lambda st: self._end() if st in (QMediaPlayer.MediaStatus.EndOfMedia,
                                             QMediaPlayer.MediaStatus.InvalidMedia) else None)
        self._player.errorOccurred.connect(lambda *_: self._end())
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

    @property
    def active(self) -> bool:
        return self._player is not None

    def _end(self) -> None:
        if self._player is not None:
            self.stop()

    def stop(self, emit: bool = True) -> None:
        if self._player is None:
            return
        p, self._player = self._player, None
        p.stop()
        p.deleteLater()
        if self._out is not None:
            self._out.deleteLater()
            self._out = None
        if emit:
            self.finished.emit()


# ------------------------------------------------------------------ Tool-Gerüst
class ToolPage(QWidget):
    """Hülle für die Hauptseite eines KI-Tools: ruft refresh() der Seite beim Anzeigen auf (Verbindungen und
    Standard-Assistenten können sich in den Einstellungen geändert haben)."""

    def __init__(self, page: QWidget, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(page)
        self.page = page

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if hasattr(self.page, "refresh"):
            self.page.refresh()


def build_tool(tool, make_page, parent=None) -> QWidget:
    """create_widget der KI-Tools: setzt tool.tr / tool.services und baut die Seite; ohne KI-Dienste (zu altes
    Hauptprogramm) nur ein Hinweis. make_page(tool) -> QWidget."""
    ctx = tool.context
    tool.tr = ctx.tr
    get = getattr(ctx, "ai_services", None)
    tool.services = get() if get else None
    if tool.services is None:
        msg = QLabel(tr("ai.kit.needs_app"))
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return msg
    tool.page = make_page(tool)
    tool.root = ToolPage(tool.page, parent)
    return tool.root


class AITool(ToolBase):
    """Basis der KI-Tools: make_page() baut die Seite (self.tr, self.services und self.context sind gesetzt).
    Schließen fragt nach, solange die Seite arbeitet (page.running); beim Beenden page.stop() / page.shutdown()."""

    CLANK_KEYS: tuple[str, ...] = ()            # Einstellungen aus Clank ≤ 1.0.2 übernehmen (Name oder Präfix*)
    CLANK_DEFAULTS: dict[str, str] = {}          # alte Clank-Einstellung -> Funktion in ai_defaults

    def make_page(self) -> QWidget:
        raise NotImplementedError

    def create_widget(self, parent=None) -> QWidget:
        self._take_over_clank()
        return build_tool(self, lambda t: t.make_page(), parent)

    def _take_over_clank(self) -> None:
        """Einmalig: Werte aus den Einstellungen des alten Clank-Studios übernehmen (Zeitpläne, Optionen …)."""
        s = self.context.settings
        if not (self.CLANK_KEYS or self.CLANK_DEFAULTS) or s.get("clank_imported"):
            return
        from omniwrench.ai import defaults
        from omniwrench.core.jsonio import read_json
        from omniwrench.core.paths import TOOL_SETTINGS_DIR
        old = read_json(TOOL_SETTINGS_DIR / "ai.clank.json", default={}) or {}
        take = {}
        for key, value in old.items():
            if any(key == k or (k.endswith("*") and key.startswith(k[:-1])) for k in self.CLANK_KEYS):
                take[key] = value
        get = getattr(self.context, "ai_services", None)
        services = get() if get else None
        app = services.settings if services is not None else None
        for key, function in self.CLANK_DEFAULTS.items():
            if old.get(key) and app is not None and not defaults.get(app, function):
                defaults.set(app, function, old[key])
        take["clank_imported"] = True
        s.update(take)
        self.take_over_clank(old)

    def take_over_clank(self, old: dict) -> None:
        """Für Tools mit Geheimnissen im Tresor: diese aus dem Bereich von Clank übernehmen (old = alte Werte)."""

    def clank_secret(self, key: str):
        from omniwrench.sdk import SecretStore
        return SecretStore("ai.clank", self.context.secrets._vault).get(key)

    def can_close(self) -> bool:
        page = getattr(self, "page", None)
        if page is not None and getattr(page, "running", False):
            return QMessageBox.question(self.root, self.tr(TOOL_NAME), tr("ai.kit.close_running")) \
                == QMessageBox.StandardButton.Yes
        return True

    def shutdown(self) -> None:
        page = getattr(self, "page", None)
        if page is None:
            return
        if getattr(page, "running", False) and hasattr(page, "stop"):
            page.stop()
        if hasattr(page, "shutdown"):
            page.shutdown()
