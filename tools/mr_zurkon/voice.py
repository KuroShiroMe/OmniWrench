"""Mr. Zurkon – Sprachassistent: per Weckwort („Hey Zurkon“) oder Knopf sprechen, Antwort vorlesen lassen.

Weckwort: offline mit Vosk (kleines Sprachmodell je Sprache, ~40–50 MB, wird auf Wunsch geladen). Erst nach dem
Weckwort geht Audio an den gewählten Anbieter für Spracherkennung – oder bleibt mit „Whisper lokal“ (faster-whisper)
bzw. „Offline (Vosk)“ ganz auf dem Rechner. Die Frage läuft über einen eingebetteten Chat (gleiche Assistenten,
Funktionen und Bestätigungen wie die Chatleiste), die Antwort liest eine Systemstimme (QTextToSpeech, alle Engines), Piper (offline,
local_speech.py) oder ein Anbieter (omniwrench.ai.speech) vor. Die Sprache (va_lang) ist frei wählbar; danach richten
sich Weckwort-Modell, Erkennung und Stimmenliste.
Zustände: off -> wake -> command -> thinking -> speaking -> (followup) -> wake.
"""

from __future__ import annotations

import difflib
import html
import importlib.util
import json
import re
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from omniwrench.ai import audio
from omniwrench.ai import local_speech as ls
from omniwrench.core.i18n import tr as app_tr
from omniwrench.sdk import run_async
from omniwrench.ui.ai_kit import (
    DepsPage, Player, Section, install_with_progress, local_needs, setup_local, whisper_label,
)

VOSK_MODELS = ls.VOSK_MODELS
VOSK_URL = ls.VOSK_URL
OFFLINE = ls.VOSK
DEFAULT_NAME = "Zurkon"
SYSTEM_VOICE = "__system__"
WHISPER = ls.WHISPER
PIPER = ls.PIPER
LANGS = ("de", "en", "fr", "es", "it", "nl", "pl", "pt", "ru", "tr", "uk", "cs", "sk", "sv", "da", "no", "fi", "hu",
         "el", "ro", "ca", "ar", "zh", "ja", "ko", "hi")
FOLLOWUP_SECONDS = 8.0
COMMAND_TIMEOUT = 10.0


# ------------------------------------------------------------------ Weckwort
def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def matches(text: str, phrases: list[str], ratio: float = 0.72) -> bool:
    """Kommt eine der Wendungen (unscharf) im gehörten Text vor?"""
    words = normalize(text).split()
    for phrase in phrases:
        target = normalize(phrase)
        n = len(target.split())
        if not n:
            continue
        if f" {target} " in f" {' '.join(words)} ":
            return True
        for i in range(0, max(1, len(words) - n + 1)):
            if difflib.SequenceMatcher(None, " ".join(words[i:i + n]), target).ratio() >= ratio:
                return True
    return False


def wake_phrases(name: str, variants: str) -> list[str]:
    name = name.strip() or DEFAULT_NAME
    out = [f"hey {name}", f"hei {name}", f"he {name}"]
    out += [v.strip() for v in variants.split(",") if v.strip()]
    return out


def model_dir(data_dir: Path, lang: str) -> Path:
    return ls.vosk_model_dir(data_dir, lang)


def model_ready(data_dir: Path, lang: str) -> bool:
    return ls.vosk_ready(data_dir, lang)


def download_model(data_dir: Path, lang: str, progress) -> Path:
    return ls.vosk_download(data_dir, lang, progress)


class WakeDetector:
    """Erkennt die Wendungen in einem 16-kHz-Strom mit Vosk (ohne Grammatik, unscharfer Vergleich)."""

    def __init__(self, model_path: Path, phrases: list[str]):
        import vosk
        vosk.SetLogLevel(-1)
        self.vosk = vosk
        self.model = vosk.Model(str(model_path))
        self.rec = vosk.KaldiRecognizer(self.model, audio.RATE)
        self.phrases = phrases
        self.heard = ""

    @staticmethod
    def pcm(samples) -> bytes:
        import numpy as np
        return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()

    def feed(self, samples) -> str:
        """Gibt den gehörten Text zurück, wenn das Weckwort darin vorkommt, sonst ""."""
        if self.rec.AcceptWaveform(self.pcm(samples)):
            text = json.loads(self.rec.Result()).get("text", "")
        else:
            text = json.loads(self.rec.PartialResult()).get("partial", "")
        if text:
            self.heard = text
        if text and matches(text, self.phrases):
            self.rec.Reset()
            return text
        return ""

    def reset(self) -> None:
        self.rec.Reset()

    def transcribe(self, samples) -> str:
        """Ganzer Satz offline (für „Offline (Vosk)“)."""
        rec = self.vosk.KaldiRecognizer(self.model, audio.RATE)
        rec.AcceptWaveform(self.pcm(samples))
        return json.loads(rec.FinalResult()).get("text", "")


_VOICE_CACHE: dict[str, list[tuple[str, str, str]]] = {}


def ready_tts(engine: str = "", parent=None):
    """QTextToSpeech der Engine oder None, wenn sie sich nicht laden lässt.

    Stimmen nie mit allVoices(None) abfragen: PySide reicht None als leere QLocale-Referenz durch, unter Windows ist
    das eine Zugriffsverletzung (Absturz). Stattdessen availableLocales() + setLocale() + availableVoices()."""
    from PySide6.QtTextToSpeech import QTextToSpeech
    tts = QTextToSpeech(engine, parent) if engine else QTextToSpeech(parent)
    if tts.state() == QTextToSpeech.State.Error:
        tts.deleteLater()
        return None
    return tts


def system_voices(lang: str) -> list[tuple[str, str, str]]:
    """Installierte Systemstimmen der Sprache über alle Engines: [(Engine, Name, Gebiet)].
    Windows: „winrt“ (OneCore, auch neuere natürliche Stimmen, soweit Windows sie freigibt) und „sapi“."""
    try:
        from PySide6.QtCore import QLocale
        from PySide6.QtTextToSpeech import QTextToSpeech
    except ImportError:
        return []
    if lang in _VOICE_CACHE:
        return list(_VOICE_CACHE[lang])
    out, seen = [], set()
    engines = [e for e in QTextToSpeech.availableEngines() if e != "mock"]
    for engine in engines or [""]:
        try:
            tts = ready_tts(engine)
            if tts is None:
                continue
            found = []
            for loc in tts.availableLocales():
                if loc.name().split("_")[0] == lang:
                    tts.setLocale(loc)
                    found += list(tts.availableVoices())
        except Exception:  # noqa: BLE001 - Engine ohne Stimmen / nicht ladbar
            continue
        for v in found:
            loc = v.locale()
            if loc.name().split("_")[0] != lang or (engine, v.name()) in seen:
                continue
            seen.add((engine, v.name()))
            out.append((engine if len(engines) > 1 else "", v.name(),
                        QLocale.territoryToString(loc.territory())))
        tts.deleteLater()
    out.sort(key=lambda x: (x[0] != (engines[0] if engines else ""), x[1]))
    _VOICE_CACHE[lang] = out
    return list(out)


def speakable(text: str, limit: int, code_hint: str = "(Code)") -> str:
    """Antwort zum Vorlesen: ohne Markdown, Code nur als Hinweis, gekürzt."""
    t = re.sub(r"```.*?```", f" {code_hint} ", text, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
    t = re.sub(r"[*_|>]{1,3}", "", t)
    t = " ".join(t.split())
    if len(t) > limit:
        cut = t[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = (cut[:end + 1] if end > limit // 2 else cut) + " …"
    return t


# ------------------------------------------------------------------ Steuerung
class _Bridge(QObject):
    woke = Signal(str)
    command = Signal(object)            # Samples des gesprochenen Satzes
    heard = Signal(str)
    level = Signal(float)
    error = Signal(str)


class VoiceTab(QWidget):
    STATES = ("off", "wake", "command", "thinking", "speaking", "followup")

    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.services = studio.services
        self.tr_ = tr = studio.tr
        self.settings = studio.context.settings
        self.state = "off"
        self.detector: WakeDetector | None = None
        self.mic: tuple[threading.Event, threading.Thread] | None = None
        self.chunker: audio.Chunker | None = None
        self._lock = threading.Lock()
        self._state_since = time.time()
        self._first_turn = True
        self._asking = False
        self._tts = None
        self._player = None
        self._stop = threading.Event()
        self.make_source = lambda: audio.Source("mic", self.settings.get("va_mic_device") or "")
        self.bridge = _Bridge()
        self.bridge.woke.connect(self._woke)
        self.bridge.command.connect(self._command_audio)
        self.bridge.heard.connect(lambda t: self.heard.setText(tr("va.heard", text=t)))
        self.bridge.error.connect(self._error)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.deps = DepsPage(audio.PACKAGES, tr("va.deps"))
        self.deps.changed.connect(self.refresh)
        self.stack.addWidget(self.deps)
        self.stack.addWidget(self._main())
        # Gespräch im eingebetteten Chat (gleiche Assistenten, Funktionen und Bestätigungen wie die Chatleiste)
        self.panel = getattr(studio, "panel", None)
        if self.panel is None:
            self.panel = self.services.chat_widget(system_extra=self.system_hint)
            split = QSplitter(Qt.Orientation.Horizontal)
            split.addWidget(self.stack)
            split.addWidget(self.panel)
            split.setStretchFactor(0, 3)
            split.setStretchFactor(1, 2)
            split.setSizes([620, 420])
            lay.addWidget(split)
        else:
            lay.addWidget(self.stack)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._watchdog)
        self.panel.bridge.finished.connect(self._answer_done)
        self.panel.bridge.failed.connect(lambda err: self._answer_done(failed=True))

    def _main(self) -> QWidget:
        tr = self.tr_
        w = QWidget()
        lay = QVBoxLayout(w)
        self.big = QLabel()
        self.big.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.big.setStyleSheet("font-size: 22px; font-weight: 700; padding: 12px;")
        lay.addWidget(self.big)
        row = QHBoxLayout()
        row.addStretch()
        self.on_btn = QPushButton(tr("va.on"))
        self.on_btn.setCheckable(True)
        self.on_btn.toggled.connect(self.switch)
        row.addWidget(self.on_btn)
        self.ptt = QPushButton("🎙 " + tr("va.talk"))
        self.ptt.setToolTip(tr("va.talk_tip"))
        self.ptt.clicked.connect(self.talk)
        row.addWidget(self.ptt)
        self.hush = QPushButton("⏹ " + tr("va.hush"))
        self.hush.clicked.connect(self.hush_now)
        row.addWidget(self.hush)
        row.addStretch()
        lay.addLayout(row)
        self.heard = QLabel()
        self.heard.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.heard.setEnabled(False)
        lay.addWidget(self.heard)

        setup = QWidget()
        form = QFormLayout(setup)
        wake = QHBoxLayout()
        self.name = QLineEdit(self.settings.get("va_name") or DEFAULT_NAME)
        self.name.setMaximumWidth(160)
        wake.addWidget(QLabel(tr("va.hey")))
        wake.addWidget(self.name)
        self.variants = QLineEdit(self.settings.get("va_variants") or "")
        self.variants.setPlaceholderText(tr("va.variants_hint"))
        wake.addWidget(self.variants, 1)
        form.addRow(tr("va.wake"), wake)
        self.engine_row = QWidget()
        eng = QHBoxLayout(self.engine_row)
        eng.setContentsMargins(0, 0, 0, 0)
        self.engine = QLabel()
        self.engine.setWordWrap(True)
        eng.addWidget(self.engine, 1)
        self.setup_btn = QPushButton(tr("va.setup_wake"))
        self.setup_btn.clicked.connect(self.setup_wake)
        eng.addWidget(self.setup_btn)
        form.addRow(tr("va.engine"), self.engine_row)
        self.form = form
        self.lang_box = QComboBox()
        self.lang_box.setToolTip(tr("va.lang_tip"))
        from PySide6.QtCore import QLocale
        self.lang_box.addItem(tr("va.lang_app", lang=QLocale(self._app_lang()).nativeLanguageName() or
                                 self._app_lang()), "")
        for code in LANGS:
            name = QLocale(code).nativeLanguageName() or code
            self.lang_box.addItem(f"{name[:1].upper()}{name[1:]} ({code})", code)
        self.lang_box.setCurrentIndex(max(0, self.lang_box.findData(self.settings.get("va_lang") or "")))
        self.lang_box.currentIndexChanged.connect(self._lang_changed)
        lang_row = QHBoxLayout()
        lang_row.addWidget(self.lang_box)
        lang_row.addStretch()
        form.addRow(tr("va.lang"), lang_row)
        rec = QHBoxLayout()
        self.stt = QComboBox()
        self.stt.currentIndexChanged.connect(self._fill_stt_models)
        self.stt.activated.connect(lambda *_: self.services.set_default("va_stt", self.stt.currentData() or ""))
        rec.addWidget(self.stt, 2)
        self.stt_model = QComboBox()
        self.stt_model.setToolTip(tr("va.whisper_model_tip"))
        self.stt_model.currentIndexChanged.connect(lambda *_: self._update_local())
        rec.addWidget(self.stt_model, 1)
        form.addRow(tr("va.stt"), rec)
        out = QHBoxLayout()
        self.tts = QComboBox()
        self.tts.currentIndexChanged.connect(self._fill_tts_models)
        self.tts.activated.connect(lambda *_: self.services.set_default("va_tts", self.tts.currentData() or ""))
        out.addWidget(self.tts, 2)
        self.tts_model = QComboBox()
        out.addWidget(self.tts_model, 1)
        self.voice = QComboBox()
        self.voice.setEditable(True)
        self.voice.setMinimumContentsLength(14)
        self.voice.currentIndexChanged.connect(lambda *_: self._update_local())
        out.addWidget(self.voice, 2)
        form.addRow(tr("va.tts"), out)
        local = QHBoxLayout()
        self.local_info = QLabel()
        self.local_info.setWordWrap(True)
        local.addWidget(self.local_info, 1)
        self.local_btn = QPushButton("⬇ " + tr("va.local_setup"))
        self.local_btn.clicked.connect(self.setup_local)
        local.addWidget(self.local_btn)
        self.test_btn = QPushButton("🔊 " + tr("va.test_voice"))
        self.test_btn.clicked.connect(lambda: self.speak(tr("va.test_text"), test=True))
        local.addWidget(self.test_btn)
        form.addRow("", local)
        more = QHBoxLayout()
        self.followup = QCheckBox(tr("va.followup"))
        self.followup.setChecked(self.settings.get("va_followup", True))
        more.addWidget(self.followup)
        more.addWidget(QLabel(tr("va.limit")))
        self.limit = QSpinBox()
        self.limit.setRange(100, 4000)
        self.limit.setSingleStep(100)
        self.limit.setValue(int(self.settings.get("va_limit") or 600))
        more.addWidget(self.limit)
        more.addStretch()
        form.addRow(tr("va.more"), more)
        self.setup = Section(tr("va.setup"), setup, True)
        lay.addWidget(self.setup)
        note = QLabel("🔒 " + tr("va.privacy"))
        note.setWordWrap(True)
        note.setEnabled(False)
        lay.addWidget(note)
        self.log = QTextBrowser()
        lay.addWidget(self.log, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self._show_state()
        return w

    # --- Einrichtung --------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.state != "off"

    def _app_lang(self) -> str:
        from omniwrench.core.i18n import current_language
        return (current_language() or "en").split("_")[0].split("-")[0]

    def _lang(self) -> str:
        """Sprache des Assistenten: frei gewählt oder die Programmsprache."""
        box = getattr(self, "lang_box", None)
        return (box.currentData() if box is not None else self.settings.get("va_lang")) or self._app_lang()

    def _lang_changed(self, *_):
        self.settings.set("va_lang", self.lang_box.currentData() or "")
        self._fill_voices()
        self._update_engine()

    def wake_available(self) -> bool:
        return not audio.missing(("vosk",)) and model_ready(audio.shared_dir(), self._lang())

    def refresh(self) -> None:
        from omniwrench.ai import speech
        if audio.missing():
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        if self.state != "off":
            return
        store = self.services.connections
        keep = self.services.default("va_stt") or self.stt.currentData()
        self.stt.clear()
        for c in speech.stt_connections(store):
            if not (c.info and c.info.removed):
                self.stt.addItem(c.name, c.id)
        self.stt.addItem("💻 " + app_tr("ai.kit.whisper"), WHISPER)
        self.stt.addItem("💻 " + app_tr("ai.kit.vosk"), OFFLINE)
        self.stt.blockSignals(True)
        self.stt.setCurrentIndex(max(0, self.stt.findData(keep)))
        self.stt.blockSignals(False)
        self._fill_stt_models()
        keep = self.services.default("va_tts") or self.tts.currentData() or SYSTEM_VOICE
        self.tts.blockSignals(True)
        self.tts.clear()
        self.tts.addItem("💻 " + app_tr("ai.kit.system_voice"), SYSTEM_VOICE)
        self.tts.addItem("💻 " + app_tr("ai.kit.piper"), PIPER)
        for c in speech.tts_connections(store):
            if not (c.info and c.info.removed):
                self.tts.addItem(c.name, c.id)
        self.tts.setCurrentIndex(max(0, self.tts.findData(keep)))
        self.tts.blockSignals(False)
        self._fill_tts_models()
        self._update_engine()

    def _fill_stt_models(self, *_):
        from omniwrench.ai import speech
        target = self.stt.currentData() or ""
        self.stt_model.blockSignals(True)
        self.stt_model.clear()
        if target == WHISPER:
            for name in ls.WHISPER_MODELS:
                self.stt_model.addItem(whisper_label(name), name)
            keep = self.settings.get("va_whisper_model") or ls.WHISPER_DEFAULT
        else:
            conn = self.services.connections.get(target)
            for m in speech.stt_models(conn) if conn else []:
                self.stt_model.addItem(m, m)
            keep = (self.settings.get("va_stt_models") or {}).get(target, "")
        self.stt_model.setCurrentIndex(max(0, self.stt_model.findData(keep)))
        self.stt_model.setVisible(self.stt_model.count() > 1)
        self.stt_model.blockSignals(False)
        self._update_local()

    def _fill_tts_models(self, *_):
        from omniwrench.ai import speech
        self.tts_model.clear()
        conn = self.services.connections.get(self.tts.currentData() or "")
        self.tts_model.setVisible(conn is not None)
        if conn is not None:
            for m in speech.tts_models(conn):
                self.tts_model.addItem(m, m)
            idx = self.tts_model.findData(self.settings.get("va_tts_model") or "")
            if idx >= 0:
                self.tts_model.setCurrentIndex(idx)
        self._fill_voices()

    def _voice_key(self) -> str:
        return self.tts.currentData() or SYSTEM_VOICE

    def _fill_voices(self) -> None:
        """Stimmen passend zur gewählten Sprache (Systemstimmen, Piper) bzw. die des Anbieters."""
        from omniwrench.ai import speech
        tr = self.tr_
        target = self._voice_key()
        lang = self._lang()
        prev = getattr(self, "_voice_target", None)
        if prev is not None and (self.voice.count() or self.voice.currentText()):
            self.settings.set("va_voices", dict(self.settings.get("va_voices") or {}, **{prev: self._voice_value()}))
        self._voice_target = target
        saved = (self.settings.get("va_voices") or {}).get(target)
        if saved is None and target not in (SYSTEM_VOICE, PIPER):
            saved = self.settings.get("va_voice") or ""          # bis 1.0.1 eine Stimme für alle
        self.voice.blockSignals(True)
        self.voice.clear()
        self.voice.setEditable(target not in (SYSTEM_VOICE, PIPER))
        if self.voice.isEditable():
            self.voice.lineEdit().setPlaceholderText(tr("va.voice_hint"))
        if target == SYSTEM_VOICE:
            self.voice.addItem(tr("va.voice_default"), "")
            for engine, name, loc in system_voices(lang):
                label = f"{name} · {loc}" + (f" ({engine})" if engine else "")
                self.voice.addItem(label, f"{engine}|{name}")
        elif target == PIPER:
            have = set(ls.installed_voices(audio.shared_dir()))
            for name, mb in ls.piper_voices(audio.shared_dir(), lang):
                mark = "✓ " if name in have else "⬇ "
                self.voice.addItem(mark + name + (f" · {mb} MB" if mb and name not in have else ""), name)
        else:
            conn = self.services.connections.get(target)
            for v in speech.voices(conn) if conn else []:
                self.voice.addItem(v, v)
        idx = self.voice.findData(saved) if saved else -1
        if idx >= 0:
            self.voice.setCurrentIndex(idx)
        elif saved and self.voice.isEditable():
            self.voice.setEditText(saved)
        elif target == PIPER and self.voice.count():
            self.voice.setCurrentIndex(0)
        self.voice.blockSignals(False)
        self._update_local()

    def _voice_value(self) -> str:
        if self.voice.isEditable():
            text = self.voice.currentText().strip()
            data = self.voice.currentData()
            return data if data and self.voice.itemText(self.voice.currentIndex()) == text else text
        return self.voice.currentData() or ""

    def _update_local(self) -> None:
        """Hinweis und Einrichten-Knopf für Whisper lokal / Piper."""
        if not hasattr(self, "local_btn"):
            return
        need = self._local_needs()
        tr = self.tr_
        self.local_btn.setVisible(bool(need))
        self.local_info.setText(tr("va.local_needs", what=", ".join(need)) if need else "")
        self.local_info.setVisible(bool(need))

    def _local_needs(self) -> list[str]:
        whisper = (self.stt_model.currentData() or ls.WHISPER_DEFAULT) if self.stt.currentData() == WHISPER else ""
        piper = (self.voice.currentData() or "") if self._voice_key() == PIPER else ""
        return local_needs(whisper, piper)

    def setup_local(self) -> None:
        """Whisper lokal / Piper einrichten (Rückfrage, Pakete, Modell bzw. Stimme)."""
        whisper = (self.stt_model.currentData() or ls.WHISPER_DEFAULT) if self.stt.currentData() == WHISPER else ""
        piper = (self.voice.currentData() or "") if self._voice_key() == PIPER else ""

        if setup_local(self, whisper, piper):
            self.status.setText(self.tr_("va.setup_done"))
        self._fill_voices()

    def _update_engine(self) -> None:
        tr = self.tr_
        ready = self.wake_available()
        self.engine.setText("" if ready else tr("va.engine_missing"))
        self.name.setToolTip(tr("va.engine_ready", model=model_dir(audio.shared_dir(), self._lang()).name)
                             if ready else "")
        self.form.setRowVisible(self.engine_row, not ready)      # eingerichtet: kein Hinweis mehr

    def setup_wake(self) -> None:
        """vosk installieren und das kleine Sprachmodell der Programmsprache laden (nach Rückfrage)."""
        tr = self.tr_
        lang = self._lang()
        name = VOSK_MODELS.get(lang, VOSK_MODELS["en"])
        if QMessageBox.question(self, tr("va.setup_wake"), tr("va.setup_q", model=name,
                                                              url=VOSK_URL.format(name=name))) \
                != QMessageBox.StandardButton.Yes:
            return
        data_dir = audio.shared_dir()

        def extra(progress):
            if not model_ready(data_dir, lang):
                download_model(data_dir, lang, lambda st: progress(tr("va.downloading", state=st)))
        if install_with_progress(self, tr("va.setup_wake"), ["vosk"], extra):
            self.status.setText(tr("va.setup_done"))
        self._update_engine()

    def _save_settings(self) -> None:
        s = self.settings
        s.set("va_name", self.name.text().strip() or DEFAULT_NAME)
        s.set("va_variants", self.variants.text().strip())
        self.services.set_default("va_stt", self.stt.currentData() or "")
        self.services.set_default("va_tts", self.tts.currentData() or SYSTEM_VOICE)
        s.set("va_tts_model", self.tts_model.currentData() or "")
        s.set("va_lang", self.lang_box.currentData() or "")
        stt = self.stt.currentData() or ""
        if stt == WHISPER:
            s.set("va_whisper_model", self.stt_model.currentData() or ls.WHISPER_DEFAULT)
        elif self.stt_model.currentData():
            s.set("va_stt_models", dict(s.get("va_stt_models") or {}, **{stt: self.stt_model.currentData()}))
        s.set("va_voices", dict(s.get("va_voices") or {}, **{self._voice_key(): self._voice_value()}))
        s.set("va_followup", self.followup.isChecked())
        s.set("va_limit", self.limit.value())

    # --- Zustände -----------------------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        with self._lock:
            self.state = state
            self._state_since = time.time()
            if state in ("command", "followup"):
                self.chunker = audio.Chunker(lambda s, t: self.bridge.command.emit(s), min_speech=0.4,
                                             silence_end=1.0, max_chunk=30.0)
            elif state == "wake" and self.detector is not None:
                self.detector.reset()
        self._show_state()

    def _show_state(self) -> None:
        tr = self.tr_
        name = self.name.text().strip() or DEFAULT_NAME if hasattr(self, "name") else DEFAULT_NAME
        text = {"off": "💤 " + tr("va.state.off"), "wake": "👂 " + tr("va.state.wake", name=name),
                "command": "🎙 " + tr("va.state.command"), "thinking": "🤔 " + tr("va.state.thinking"),
                "speaking": "🔊 " + tr("va.state.speaking"), "followup": "🎙 " + tr("va.state.followup")}
        self.big.setText(text.get(self.state, self.state))
        if hasattr(self, "on_btn"):
            self.on_btn.setText(tr("va.off") if self.on_btn.isChecked() else tr("va.on"))

    def _feed(self, samples) -> None:
        """Audio-Thread: je nach Zustand ans Weckwort oder an die Satzaufnahme."""
        with self._lock:
            state, det, chunker = self.state, self.detector, self.chunker
        if state == "wake" and det is not None:
            heard = det.feed(samples)
            if heard:
                self.bridge.woke.emit(heard)
            elif det.heard:
                self.bridge.heard.emit(det.heard)
        elif state in ("command", "followup") and chunker is not None:
            chunker.feed(samples)

    def _start_mic(self) -> None:
        if self.mic is not None:
            return
        stop, src = threading.Event(), self.make_source()

        def loop():
            try:
                src.run(self._feed, stop)
            except Exception as err:  # noqa: BLE001 - kein Mikrofon, Treiber, Rechte …
                self.bridge.error.emit(str(err) or err.__class__.__name__)
        t = threading.Thread(target=loop, name="voice-mic", daemon=True)
        t.start()
        self.mic = (stop, t)
        self.timer.start()

    def _stop_mic(self) -> None:
        if self.mic is not None:
            self.mic[0].set()
            self.mic = None
        self.timer.stop()

    def switch(self, on: bool) -> None:
        tr = self.tr_
        if not on:
            self.off()
            return
        self._save_settings()
        if not self.wake_available():
            self.on_btn.setChecked(False)
            self.status.setText(tr("va.need_wake"))
            return
        try:
            self.detector = WakeDetector(model_dir(audio.shared_dir(), self._lang()),
                                         wake_phrases(self.name.text(), self.variants.text()))
        except Exception as err:  # noqa: BLE001
            self.on_btn.setChecked(False)
            self.status.setText("⚠ " + str(err))
            return
        self._first_turn = True
        self._start_mic()
        self._set_state("wake")
        self.setup.head.setChecked(False)
        self.status.setText("")

    def off(self) -> None:
        self._stop.set()
        self.hush_now()
        self._stop_mic()
        self.detector = None
        self._set_state("off")
        if self.on_btn.isChecked():
            self.on_btn.blockSignals(True)
            self.on_btn.setChecked(False)
            self.on_btn.blockSignals(False)
            self._show_state()

    def talk(self) -> None:
        """Knopf „Sprechen“: ohne Weckwort direkt zuhören (funktioniert auch ohne Vosk)."""
        if self.state in ("thinking",):
            return
        self._save_settings()
        if self.state == "speaking":
            self.hush_now()
        self._start_mic()
        self._set_state("command")

    def _woke(self, heard: str) -> None:
        if self.state != "wake":
            return
        from PySide6.QtWidgets import QApplication
        QApplication.beep()
        self.log.append(f"<span style='color:#9ca3af'>„{html.escape(heard)}“</span>")
        self._set_state("command")

    def _watchdog(self) -> None:
        """Zeitlimits: kein Satz nach dem Weckwort / keine Folgefrage -> wieder auf das Weckwort warten."""
        waited = time.time() - self._state_since
        if self.state == "command" and waited > COMMAND_TIMEOUT and (self.chunker is None or
                                                                     self.chunker.speech == 0):
            self._back_to_wait()
        elif self.state == "followup" and waited > FOLLOWUP_SECONDS and (self.chunker is None or
                                                                         self.chunker.speech == 0):
            self._back_to_wait()

    def _back_to_wait(self) -> None:
        if self.on_btn.isChecked() and self.detector is not None:
            self._set_state("wake")
        else:
            self._stop_mic()
            self._set_state("off")

    # --- Satz -> Text -> Chat -----------------------------------------------------------------------
    def _command_audio(self, samples) -> None:
        if self.state not in ("command", "followup"):
            return
        self._set_state("thinking")
        stt = self.stt.currentData() or OFFLINE
        model = self.stt_model.currentData() or ""
        store = self.services.connections
        langs = [self._lang()]
        det = self.detector
        data_dir = audio.shared_dir()
        if stt == WHISPER and self._local_needs():
            self._error(self.tr_("va.local_missing"))
            return

        def work():
            from omniwrench.ai import speech
            if stt == WHISPER:
                return " ".join(t for t, _a, _b in ls.whisper_transcribe(data_dir, samples, model, langs[0])).strip()
            if stt == OFFLINE:
                if det is None:
                    raise RuntimeError(self.tr_("va.need_wake"))
                return det.transcribe(samples)
            conn = store.get(stt)
            segs = speech.transcribe(store, conn, speech.wav_bytes(samples), model, langs, None, False)
            return " ".join(s.text for s in segs).strip()

        def done(text):
            if self.state != "thinking":
                return
            if not text:
                self._back_to_wait()
                return
            self.log.append(f"<b>{self.tr_('va.you')}:</b> {html.escape(text)}")
            self.ask(text)

        def failed(err):
            self._error(err.splitlines()[0])
        run_async(work, done, failed)

    def system_hint(self) -> str:
        if not self._asking:
            return ""
        return ("The user is talking to you by voice and your answer will be read aloud. Answer briefly in plain "
                "spoken sentences, without Markdown, tables, lists or code unless the user asks for them. If details "
                "are needed, give the short answer and say that the details are in the chat.")

    def ask(self, text: str) -> None:
        panel = self.panel
        if panel._running:
            self._error(self.tr_("va.busy"))
            return
        self._asking = True
        panel.ask(text, new=self._first_turn)
        self._first_turn = False
        if not panel._running:              # kein Assistent verbunden o. Ä.
            self._asking = False
            self._error(self.tr_("va.no_bot"))

    def _answer_done(self, failed: bool = False) -> None:
        if not self._asking:
            return
        self._asking = False
        panel = self.panel
        text = ""
        if not failed:
            msgs = (panel.thread or {}).get("messages") or []
            text = next((m.get("content", "") for m in reversed(msgs) if m["role"] == "assistant"
                         and m.get("content")), "")
        if not text:
            text = self.tr_("va.failed")
        self.log.append(f"<b>{self.tr_('va.bot')}:</b> {html.escape(speakable(text, 2000, self.tr_('va.code')))}")
        self.speak(speakable(text, self.limit.value(), self.tr_("va.code")))

    # --- Vorlesen -----------------------------------------------------------------------------------
    def speak(self, text: str, test: bool = False) -> None:
        if test:
            if self.state != "off":
                return
            self._save_settings()
        self._set_state("speaking")
        target = self.tts.currentData() or SYSTEM_VOICE
        voice = self._voice_value()
        if target == SYSTEM_VOICE:
            self._speak_system(text, voice)
            return
        if target == PIPER and self._local_needs():
            self.status.setText("⚠ " + self.tr_("va.local_missing"))
            self._speak_system(text, "")
            return
        store = self.services.connections
        model = self.tts_model.currentData() or ""
        data_dir = audio.shared_dir()

        def work():
            if target == PIPER:
                return ls.piper_synthesize(data_dir, voice, text), "audio/wav"
            from omniwrench.ai import speech
            return speech.synthesize(store, store.get(target), text, model, voice)

        def done(result):
            data, mime = result
            if self.state != "speaking":
                return
            ext = ".wav" if "wav" in (mime or "") else ".mp3"
            path = Path(tempfile.gettempdir()) / f"omniwrench_voice_{int(time.time() * 1000)}{ext}"
            path.write_bytes(data)
            self._play(path)

        def failed(err):
            self.status.setText("⚠ " + err.splitlines()[0])
            self._speak_system(text)
        run_async(work, done, failed)

    def _speak_system(self, text: str, voice: str = "") -> None:
        if importlib.util.find_spec("PySide6.QtTextToSpeech") is None:
            self._spoken()
            return
        engine, _, name = voice.partition("|")
        if self._tts is not None:                  # je Ansage neu: so gilt das aktuelle Standard-Ausgabegerät
            self._tts.stateChanged.disconnect(self._tts_state)
            self._tts.stop()
            self._tts.deleteLater()
        self._tts = ready_tts(engine, self)
        if self._tts is None:
            self._spoken()
            return
        self._tts.stateChanged.connect(self._tts_state)
        from PySide6.QtCore import QLocale
        self._tts.setLocale(QLocale(self._lang()))
        if name:
            match = next((v for v in self._tts.availableVoices() if v.name() == name), None)
            if match is not None:
                self._tts.setVoice(match)
        self._tts_started = False
        self._tts.say(text)
        QTimer.singleShot(max(4000, len(text) * 120), self._tts_timeout)

    def _tts_state(self, state) -> None:
        from PySide6.QtTextToSpeech import QTextToSpeech
        if state == QTextToSpeech.State.Speaking:
            self._tts_started = True
        elif state in (QTextToSpeech.State.Ready, QTextToSpeech.State.Error) and self.state == "speaking":
            self._spoken()

    def _tts_timeout(self) -> None:
        """Manche Systeme melden das Ende nie (oder es gibt keine Stimme) – dann nach Schätzung weiter."""
        if self.state == "speaking" and self._player is None:
            self._spoken()

    def _play(self, path: Path) -> None:
        """Auf dem gewählten bzw. aktuellen Standardgerät abspielen (Einstellungen › KI-Funktionen)."""
        self._player = Player(self.services.settings, self)
        self._player.finished.connect(self._spoken)
        self._player.play(path)

    def _spoken(self) -> None:
        if self.state != "speaking":
            return
        if self._player is not None:
            player, self._player = self._player, None
            player.stop(emit=False)
            player.deleteLater()
        if self.followup.isChecked() and self.mic is not None:
            self._set_state("followup")
        else:
            self._back_to_wait()

    def hush_now(self) -> None:
        if self._tts is not None:
            self._tts.stop()
        if self._player is not None:
            self._player.stop()
        if self.state == "speaking":
            self._spoken()

    def _error(self, text: str) -> None:
        self.status.setText("⚠ " + text)
        self._asking = False
        if self.state in ("thinking", "speaking", "command", "followup"):
            self._back_to_wait()

    def shutdown(self) -> None:
        self.off()
