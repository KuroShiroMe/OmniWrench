"""Reiter „Mitschrift“: Live-Transkription von Mikrofon und Systemton mit Sprechererkennung und Zusammenfassung.

Ablauf: Einwilligungsdialog (Pflicht, jedes Mal) -> Aufnahme (audio.Recorder) zerlegt in Sprachabschnitte ->
ein Hintergrund-Thread schickt jeden Abschnitt an den gewählten Anbieter (omniwrench.ai.speech) und ordnet die
Sätze Sprechern zu (speakers.SessionSpeakers) -> Anzeige und Speichern (Ablage "transcripts", verschlüsselt wie
Chats). Am Ende optional Zusammenfassung über einen Chat-Assistenten (verfremdet, ohne Funktionen).
Audio wird nicht gespeichert; nur die Stimmprobe eines Sprecherprofils, wenn es jemand anlegt.
"""

from __future__ import annotations

import html
import queue
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QProgressBar, QPushButton, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from omniwrench.sdk import run_async

from . import audio
from . import speakers as spk
from .documents import ask_once
from .grouptab import Section
from .images import NoBotPage

COLORS = ("#8b5cf6", "#22c55e", "#f59e0b", "#06b6d4", "#ef4444", "#ec4899", "#84cc16", "#3b82f6")
KEEP_AUDIO = 300                    # so viele Abschnitte bleiben für „Stimme als Profil speichern“ im Speicher


class DepsPage(QWidget):
    """Ausgegraute Seite, solange Python-Pakete fehlen; installiert sie auf Knopfdruck."""
    changed = Signal()

    def __init__(self, studio, packages: tuple[str, ...], text: str):
        super().__init__()
        self.studio = studio
        self.packages = packages
        tr = studio.tr
        lay = QVBoxLayout(self)
        lay.addStretch()
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.label)
        row = QHBoxLayout()
        row.addStretch()
        self.button = QPushButton("⬇ " + tr("deps.install"))
        self.button.clicked.connect(self.install)
        row.addWidget(self.button)
        row.addStretch()
        lay.addLayout(row)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch()

    def install(self) -> None:
        tr = self.studio.tr
        need = audio.missing(self.packages)
        if not need:
            self.changed.emit()
            return
        self.button.setEnabled(False)
        self.status.setText(tr("deps.installing", packages=", ".join(need)))
        tool_dir = self.studio.context.tool_dir

        def done(error):
            self.button.setEnabled(True)
            if error:
                self.status.setText("⚠ " + error)
            else:
                self.status.setText(tr("deps.done"))
                self.changed.emit()

        def failed(text):
            self.button.setEnabled(True)
            self.status.setText("⚠ " + text.splitlines()[0])
        run_async(lambda: audio.install_packages(tool_dir, need), done, failed)


class ProfileNotice(QDialog):
    """Deutlicher Hinweis, bevor Sprecherprofile (biometrische Daten) dauerhaft gespeichert werden."""

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ts.pnotice.title"))
        self.setMinimumWidth(600)
        lay = QVBoxLayout(self)
        head = QLabel("⚠ " + tr("ts.pnotice.head"))
        head.setStyleSheet("font-size: 18px; font-weight: 800; color: #ef4444;")
        head.setWordWrap(True)
        lay.addWidget(head)
        body = QLabel(tr("ts.pnotice.body"))
        body.setWordWrap(True)
        body.setStyleSheet("font-weight: 600;")
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(body)
        self.ok_box = QCheckBox(tr("ts.pnotice.accept"))
        lay.addWidget(self.ok_box)
        box = QDialogButtonBox()
        self.ok = box.addButton(tr("ts.pnotice.ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        box.addButton(QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.ok.setEnabled(False)
        self.ok_box.toggled.connect(self.ok.setEnabled)


class ConsentDialog(QDialog):
    """Pflichthinweis vor jeder Aufnahme.

    Sprecherprofile: Beim Start mit angehaktem Opt-in erscheint zusätzlich ProfileNotice. Wer das Opt-in
    zehnmal kurz hintereinander umschaltet, bekommt den Haken „immer aktiv“ (Einstellung ts_profiles_always):
    dann ist das Opt-in vorbelegt und ProfileNotice entfällt. Die Einwilligung zur Aufnahme selbst bleibt.
    """

    TOGGLES = 10          # so oft umschalten …
    WINDOW = 6.0          # … innerhalb dieser Sekunden

    def __init__(self, tr, provider: str, profiles_possible: bool, settings=None, parent=None):
        super().__init__(parent)
        self.tr_ = tr
        self.settings = settings
        self._clicks: list[float] = []
        self.setWindowTitle(tr("ts.consent.title"))
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        head = QLabel("⚠ " + tr("ts.consent.head"))
        head.setStyleSheet("font-size: 17px; font-weight: 700; color: #f59e0b;")
        head.setWordWrap(True)
        lay.addWidget(head)
        body = QLabel(tr("ts.consent.body", provider=provider))
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(body)
        self.agree = QCheckBox(tr("ts.consent.agree"))
        self.agree.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.agree)
        self.profiles = QCheckBox(tr("ts.consent.profiles"))
        self.profiles.setEnabled(profiles_possible)
        self.profiles.clicked.connect(self._profiles_clicked)
        lay.addWidget(self.profiles)
        always = bool(settings and settings.get("ts_profiles_always")) and profiles_possible
        self.always = QCheckBox(tr("ts.consent.profiles_always"))
        self.always.setChecked(always)
        self.always.setVisible(always)
        self.always.toggled.connect(self._always_toggled)
        lay.addWidget(self.always)
        self.profiles.setChecked(always)
        row = QHBoxLayout()
        copy = QPushButton(tr("ts.consent.copy"))
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(tr("ts.consent.notice")))
        row.addWidget(copy)
        row.addStretch()
        lay.addLayout(row)
        box = QDialogButtonBox()
        self.start = box.addButton("● " + tr("ts.start"), QDialogButtonBox.ButtonRole.AcceptRole)
        box.addButton(QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.start.setEnabled(False)
        self.agree.toggled.connect(self.start.setEnabled)

    def _profiles_clicked(self, _checked: bool) -> None:
        now = time.monotonic()
        self._clicks = [t for t in self._clicks if now - t <= self.WINDOW] + [now]
        if len(self._clicks) >= self.TOGGLES and self.settings is not None:
            self.always.setVisible(True)

    def _always_toggled(self, on: bool) -> None:
        if self.settings is not None:
            self.settings.set("ts_profiles_always", on)
        if on:
            self.profiles.setChecked(True)

    def accept(self) -> None:
        if self.profiles.isChecked() and not self.always.isChecked():
            if ProfileNotice(self.tr_, self).exec() != QDialog.DialogCode.Accepted:
                self.profiles.setChecked(False)
                return
        super().accept()


class ProfilesDialog(QDialog):
    def __init__(self, tr, store: spk.ProfileStore, parent=None):
        super().__init__(parent)
        self.tr_ = tr
        self.store = store
        self.setWindowTitle(tr("ts.profiles.title"))
        self.resize(560, 400)
        lay = QVBoxLayout(self)
        hint = QLabel(tr("ts.profiles.hint"))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("ts.col.name"), tr("ts.profiles.count"), tr("ts.profiles.sample")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, slot in ((tr("ts.rename"), self.rename), (tr("ts.profiles.delete"), self.delete)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        close = QPushButton(tr("ts.close"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self.render()

    def render(self) -> None:
        profiles = self.store.load()
        self.table.setRowCount(len(profiles))
        for r, p in enumerate(profiles):
            it = QTableWidgetItem(p.get("name", ""))
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            self.table.setItem(r, 0, it)
            self.table.setItem(r, 1, QTableWidgetItem(str(p.get("count") or 0)))
            self.table.setItem(r, 2, QTableWidgetItem("✓" if p.get("sample") else "–"))

    def _current(self) -> tuple[str, str]:
        r = self.table.currentRow()
        if r < 0:
            return "", ""
        it = self.table.item(r, 0)
        return it.data(Qt.ItemDataRole.UserRole), it.text()

    def rename(self) -> None:
        pid, name = self._current()
        if not pid:
            return
        new, ok = QInputDialog.getText(self, self.tr_("ts.rename"), self.tr_("ts.col.name"), text=name)
        if ok and new.strip():
            self.store.rename(pid, new.strip())
            self.render()

    def delete(self) -> None:
        pid, name = self._current()
        if pid and QMessageBox.question(self, self.tr_("ts.profiles.delete"),
                                        self.tr_("ts.profiles.delete_q", name=name)) == QMessageBox.StandardButton.Yes:
            self.store.delete(pid)
            self.render()


class _Bridge(QObject):
    segments = Signal(object)          # Liste neuer Abschnitte
    error = Signal(str)
    idle = Signal()
    source_error = Signal(str, str)


class TranscriptTab(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.services = studio.services
        self.tr_ = tr = studio.tr
        self.settings = studio.context.settings
        self.profiles = spk.ProfileStore(self.services.storage)
        self.data: dict | None = None        # aktuelle Mitschrift
        self.recorder: audio.Recorder | None = None
        self.session: spk.SessionSpeakers | None = None
        self.queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.audio_cache: dict[int, object] = {}
        self.lock = threading.Lock()                    # Sprecherliste: Worker und Oberfläche
        self.bridge = _Bridge()
        self.bridge.segments.connect(self._add_segments)
        self.bridge.error.connect(lambda t: self.status.setText("⚠ " + t))
        self.bridge.idle.connect(self._worker_idle)
        self.bridge.source_error.connect(self._source_error)
        self._summarizing = False
        self._sum_stop = threading.Event()
        self.make_sources = self._make_sources          # Tests ersetzen das durch Fake-Quellen

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.deps = DepsPage(studio, audio.PACKAGES, tr("ts.deps"))
        self.deps.changed.connect(self.refresh)
        self.stack.addWidget(self.deps)
        self.nobot = NoBotPage(tr("ts.nobot"), tr("ui.open_ai_options"), self.services.open_options)
        self.stack.addWidget(self.nobot)
        self.stack.addWidget(self._main())
        lay.addWidget(self.stack)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._tick)

    # --- Aufbau -------------------------------------------------------------------------------------
    def _main(self) -> QWidget:
        tr = self.tr_
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel(tr("ts.history")))
        self.history = QListWidget()
        self.history.itemClicked.connect(lambda it: self.open(it.data(Qt.ItemDataRole.UserRole)))
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self._history_menu)
        ll.addWidget(self.history, 1)
        prof = QPushButton("👤 " + tr("ts.profiles.title"))
        prof.clicked.connect(lambda: ProfilesDialog(tr, self.profiles, self).exec())
        ll.addWidget(prof)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        setup = QWidget()
        form = QFormLayout(setup)
        src = QHBoxLayout()
        self.use_mic = QCheckBox(tr("ts.src.mic"))
        self.use_mic.setChecked(self.settings.get("ts_mic", True))
        src.addWidget(self.use_mic)
        self.mic_dev = QComboBox()
        src.addWidget(self.mic_dev, 1)
        self.use_sys = QCheckBox(tr("ts.src.system"))
        self.use_sys.setChecked(self.settings.get("ts_system", True))
        src.addWidget(self.use_sys)
        self.sys_dev = QComboBox()
        src.addWidget(self.sys_dev, 1)
        form.addRow(tr("ts.sources"), src)
        prov = QHBoxLayout()
        self.conn = QComboBox()
        self.conn.currentIndexChanged.connect(self._fill_models)
        prov.addWidget(self.conn, 2)
        self.model = QComboBox()
        prov.addWidget(self.model, 1)
        form.addRow(tr("ts.provider"), prov)
        self.langs = QLineEdit(self.settings.get("ts_languages") or "")
        self.langs.setPlaceholderText(tr("ts.languages_hint"))
        form.addRow(tr("ts.languages"), self.langs)
        me = QHBoxLayout()
        self.own = QLineEdit(self.settings.get("ts_own_name") or tr("ts.me"))
        me.addWidget(self.own, 1)
        self.multi_mic = QCheckBox(tr("ts.multi_mic"))
        self.multi_mic.setChecked(bool(self.settings.get("ts_multi_mic")))
        me.addWidget(self.multi_mic)
        form.addRow(tr("ts.own_name"), me)
        rec = QHBoxLayout()
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.5, 0.99)
        self.threshold.setSingleStep(0.01)
        self.threshold.setValue(float(self.settings.get("ts_threshold") or spk.THRESHOLD))
        self.threshold.setToolTip(tr("ts.threshold_tip"))
        rec.addWidget(self.threshold)
        self.auto_sum = QCheckBox(tr("ts.auto_summary"))
        self.auto_sum.setChecked(self.settings.get("ts_auto_summary", True))
        rec.addWidget(self.auto_sum)
        rec.addStretch()
        form.addRow(tr("ts.threshold"), rec)
        self.setup = Section(tr("ts.setup"), setup, True)
        rl.addWidget(self.setup)

        ctl = QHBoxLayout()
        self.start_btn = QPushButton("● " + tr("ts.start"))
        self.start_btn.setStyleSheet("QPushButton { font-weight: 700; }")
        self.start_btn.clicked.connect(self.toggle)
        ctl.addWidget(self.start_btn)
        self.pause_btn = QPushButton("⏸ " + tr("ts.pause"))
        self.pause_btn.setCheckable(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.toggled.connect(self._pause)
        ctl.addWidget(self.pause_btn)
        self.elapsed = QLabel("00:00:00")
        ctl.addWidget(self.elapsed)
        self.levels: dict[str, QProgressBar] = {}
        for kind in ("mic", "system"):
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(True)
            bar.setFormat(tr(f"ts.src.{kind}"))
            bar.setMaximumWidth(160)
            bar.setMaximumHeight(16)
            self.levels[kind] = bar
            ctl.addWidget(bar)
        ctl.addStretch()
        rl.addLayout(ctl)
        self.banner = QLabel("●  " + tr("ts.recording_banner"))
        self.banner.setStyleSheet("background: #b91c1c; color: white; font-weight: 700; padding: 6px; "
                                  "border-radius: 4px;")
        self.banner.setWordWrap(True)
        self.banner.hide()
        rl.addWidget(self.banner)

        self.views = QTabWidget()
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.views.addTab(self.text, tr("ts.view.transcript"))
        self.summary = QTextBrowser()
        self.views.addTab(self.summary, tr("ts.view.summary"))
        sp = QWidget()
        sl = QVBoxLayout(sp)
        self.spk_table = QTableWidget(0, 3)
        self.spk_table.setHorizontalHeaderLabels([tr("ts.col.name"), tr("ts.col.profile"), tr("ts.col.parts")])
        self.spk_table.verticalHeader().hide()
        self.spk_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.spk_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.spk_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.spk_table.doubleClicked.connect(lambda *_: self.rename_speaker())
        sl.addWidget(self.spk_table, 1)
        row = QHBoxLayout()
        for text, slot in ((tr("ts.rename"), self.rename_speaker), (tr("ts.save_profile"), self.save_profile),
                           (tr("ts.merge"), self.merge_speaker)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        sl.addLayout(row)
        self.views.addTab(sp, tr("ts.view.speakers"))
        rl.addWidget(self.views, 1)

        bottom = QHBoxLayout()
        self.title = QLineEdit()
        self.title.setPlaceholderText(tr("ts.title"))
        self.title.editingFinished.connect(self._title_changed)
        bottom.addWidget(self.title, 2)
        self.sum_conn = QComboBox()
        bottom.addWidget(self.sum_conn, 1)
        self.sum_btn = QPushButton("✦ " + tr("ts.summarize"))
        self.sum_btn.clicked.connect(self.summarize)
        bottom.addWidget(self.sum_btn)
        chat = QPushButton(tr("ts.to_chat"))
        chat.clicked.connect(self.to_chat)
        bottom.addWidget(chat)
        exp = QPushButton(tr("ts.export"))
        exp.clicked.connect(self.export)
        bottom.addWidget(exp)
        rl.addLayout(bottom)
        self.status = QLabel()
        self.status.setWordWrap(True)
        rl.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([220, 980])
        return split

    # --- Zustand ------------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.recorder is not None or (self.worker is not None and self.worker.is_alive()) or self._summarizing

    def refresh(self) -> None:
        from omniwrench.ai import speech
        if audio.missing():
            self.stack.setCurrentIndex(0)
            return
        conns = [c for c in speech.stt_connections(self.services.connections) if not (c.info and c.info.removed)]
        if not conns:
            self.stack.setCurrentIndex(1)
            return
        self.stack.setCurrentIndex(2)
        if self.recorder is not None:
            return
        keep = self.conn.currentData() or self.settings.get("ts_connection") or ""
        self.conn.blockSignals(True)
        self.conn.clear()
        for c in conns:
            self.conn.addItem(c.name, c.id)
        self.conn.setCurrentIndex(max(0, self.conn.findData(keep)))
        self.conn.blockSignals(False)
        self._fill_models()
        chats = [c for c in self.services.connections.chat_connections() if not (c.info and c.info.removed)]
        keep = self.sum_conn.currentData() or self.settings.get("ts_summary_connection") or \
            self.services.connections.primary_id()
        self.sum_conn.clear()
        for c in chats:
            self.sum_conn.addItem(c.name, c.id)
        self.sum_conn.setCurrentIndex(max(0, self.sum_conn.findData(keep)))
        self._fill_devices()
        self.reload()

    def _fill_models(self, *_):
        from omniwrench.ai import speech
        conn = self.services.connections.get(self.conn.currentData() or "")
        self.model.clear()
        if conn is None:
            return
        for m in speech.stt_models(conn):
            self.model.addItem(m, m)
        keep = self.settings.get("ts_model") or ""
        idx = self.model.findData(keep)
        if idx >= 0:
            self.model.setCurrentIndex(idx)

    def _fill_devices(self) -> None:
        tr = self.tr_
        try:
            devs = audio.devices()
        except Exception:  # noqa: BLE001 - kein Audiosystem
            devs = {"mic": [], "system": []}
        for kind, box in (("mic", self.mic_dev), ("system", self.sys_dev)):
            keep = box.currentData() or self.settings.get(f"ts_{kind}_device") or ""
            box.clear()
            box.addItem(tr("ts.default_device"), "")
            for did, name in devs.get(kind, []):
                box.addItem(name, did)
            box.setCurrentIndex(max(0, box.findData(keep)))

    def reload(self) -> None:
        self.history.clear()
        for t in self.services.storage.list_transcripts():
            when = time.strftime("%d.%m. %H:%M", time.localtime(t.get("created") or t.get("updated") or 0))
            item = QListWidgetItem(("🔒 " if t.get("locked") else "") + f"{t.get('title') or '…'}\n{when}")
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self.history.addItem(item)

    def _save_settings(self) -> None:
        s = self.settings
        s.set("ts_mic", self.use_mic.isChecked())
        s.set("ts_system", self.use_sys.isChecked())
        s.set("ts_mic_device", self.mic_dev.currentData() or "")
        s.set("ts_system_device", self.sys_dev.currentData() or "")
        s.set("ts_connection", self.conn.currentData() or "")
        s.set("ts_model", self.model.currentData() or "")
        s.set("ts_languages", self.langs.text().strip())
        s.set("ts_own_name", self.own.text().strip())
        s.set("ts_multi_mic", self.multi_mic.isChecked())
        s.set("ts_threshold", round(self.threshold.value(), 2))
        s.set("ts_auto_summary", self.auto_sum.isChecked())

    # --- Aufnahme -----------------------------------------------------------------------------------
    def toggle(self) -> None:
        if self.recorder is not None:
            self.stop()
        else:
            self.start()

    def _make_sources(self) -> list:
        out = []
        if self.use_mic.isChecked():
            out.append(audio.Source("mic", self.mic_dev.currentData() or ""))
        if self.use_sys.isChecked():
            out.append(audio.Source("system", self.sys_dev.currentData() or ""))
        return out

    def start(self) -> None:
        from omniwrench.ai import speech
        tr = self.tr_
        if self.recorder is not None or (self.worker is not None and self.worker.is_alive()):
            return
        conn = self.services.connections.get(self.conn.currentData() or "")
        if conn is None:
            return
        if not (self.use_mic.isChecked() or self.use_sys.isChecked()):
            self.status.setText("⚠ " + tr("ts.no_source"))
            return
        dlg = ConsentDialog(tr, conn.name, True, self.settings, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.agree.isChecked():
            return
        self._save_settings()
        use_profiles = dlg.profiles.isChecked()
        now = time.time()
        model = self.model.currentData() or ""
        self.data = {"format": 1, "id": self.services.storage.new_id(), "created": int(now), "updated": int(now),
                     "title": tr("ts.default_title", date=time.strftime("%d.%m.%Y %H:%M")),
                     "consent": {"at": int(now), "profiles": use_profiles},
                     "sources": [s for s, on in (("mic", self.use_mic.isChecked()),
                                                 ("system", self.use_sys.isChecked())) if on],
                     "connection": conn.id, "connection_name": conn.name, "model": model,
                     "languages": self._languages(), "speakers": {}, "segments": [], "summary": "",
                     "duration": 0}
        self.title.setText(self.data["title"])
        profiles = self.profiles.load() if use_profiles else []
        self.session = spk.SessionSpeakers(profiles, tr("ts.speaker_n"), self.threshold.value(),
                                           self.data["speakers"])
        self.audio_cache = {}
        self.text.clear()
        self.summary.clear()
        self._render_speakers()
        self.stop_event = threading.Event()
        self.queue = queue.Queue()
        job = {"store": self.services.connections, "conn": conn, "model": model,
               "languages": self.data["languages"], "profiles": use_profiles,
               "known": spk.ProfileStore.samples(profiles) if use_profiles and speech.knows_speakers(conn, model)
               else [], "own": self.own.text().strip() or tr("ts.me"), "multi_mic": self.multi_mic.isChecked()}
        self.worker = threading.Thread(target=self._work, args=(job,), name="transcribe", daemon=True)
        self.worker.start()
        self.recorder = audio.Recorder(self.make_sources(), lambda kind, s, t: self.queue.put((kind, s, t)),
                                       lambda kind, text: self.bridge.source_error.emit(kind, text))
        self.recorder.start()
        active = {src.kind for src in self.recorder.sources}
        for kind, bar in self.levels.items():
            bar.setVisible(kind in active)
        self.setup.head.setChecked(False)
        self.setup.setEnabled(False)
        self.start_btn.setText("■ " + tr("ts.stop"))
        self.pause_btn.setEnabled(True)
        self.banner.show()
        self.status.setText(tr("ts.listening"))
        self.timer.start()
        self.services.storage.save_transcript(self.data)

    def _languages(self) -> list[str]:
        return [x.strip().lower() for x in self.langs.text().replace(";", ",").split(",") if x.strip()]

    def _pause(self, on: bool) -> None:
        if self.recorder is not None:
            self.recorder.paused = on
            self.banner.setText(("⏸  " + self.tr_("ts.paused_banner")) if on else ("●  " +
                                                                                  self.tr_("ts.recording_banner")))

    def stop(self) -> None:
        if self.recorder is None:
            return
        rec, self.recorder = self.recorder, None
        rec.stop()
        if self.data is not None:
            self.data["duration"] = int(time.time() - rec.started)
        self.queue.put(None)                       # Ende: Worker arbeitet die Warteschlange ab und meldet idle
        self.timer.stop()
        self.banner.hide()
        self.pause_btn.setChecked(False)
        self.pause_btn.setEnabled(False)
        self.start_btn.setText("● " + self.tr_("ts.start"))
        self.start_btn.setEnabled(False)
        self.status.setText(self.tr_("ts.finishing"))
        for bar in self.levels.values():
            bar.setValue(0)

    def _source_error(self, kind: str, text: str) -> None:
        self.status.setText("⚠ " + self.tr_("ts.source_error", source=self.tr_(f"ts.src.{kind}"), error=text))

    def _tick(self) -> None:
        rec = self.recorder
        if rec is None:
            return
        self.elapsed.setText(_clock(time.time() - rec.started))
        for kind, level in rec.levels().items():
            if kind in self.levels:
                self.levels[kind].setValue(min(100, int(level * 400)))

    # --- Hintergrund: Abschnitt -> Text -> Sprecher -------------------------------------------------
    def _work(self, job: dict) -> None:
        from omniwrench.ai import speech
        from omniwrench.ai.chat import error_text
        counter = 0
        last = {"mic": "", "system": ""}
        while True:
            item = self.queue.get()
            if item is None or self.stop_event.is_set():
                break
            kind, samples, t0 = item
            counter += 1
            try:
                segs = speech.transcribe(job["store"], job["conn"], speech.wav_bytes(samples), job["model"],
                                         job["languages"], job["known"], True, self.stop_event)
            except Exception as err:  # noqa: BLE001 - weiter aufnehmen, Fehler anzeigen
                self.bridge.error.emit(error_text(err))
                continue
            out = []
            labels: dict[str, str] = {}
            dur = len(samples) / audio.RATE
            for seg in segs:
                a = max(0.0, min(seg.start, dur))
                b = max(a, min(seg.end or dur, dur))
                piece = samples[int(a * audio.RATE):int(b * audio.RATE)] if b - a >= 0.5 else samples
                with self.lock:
                    if seg.known:
                        sid = self.session.by_name(seg.speaker)
                    elif kind == "mic" and not job["multi_mic"]:
                        sid = self.session.by_name(job["own"])
                    elif seg.speaker and seg.speaker in labels:
                        sid = labels[seg.speaker]
                    else:
                        # Stimmmerkmale nur im Speicher zum Unterscheiden; gespeichert wird nichts davon
                        sid = self.session.assign(spk.embedding(piece), last[kind])
                        if seg.speaker:
                            labels[seg.speaker] = sid
                last[kind] = sid
                idx = counter * 1000 + len(out)
                if len(piece) <= audio.RATE * 30:
                    self.audio_cache[idx] = piece
                out.append({"t": round(t0 + a, 1), "end": round(t0 + b, 1), "source": kind, "speaker": sid,
                            "text": seg.text, "audio": idx})
            while len(self.audio_cache) > KEEP_AUDIO:
                self.audio_cache.pop(next(iter(self.audio_cache)))
            if out:
                self.bridge.segments.emit(out)
        self.bridge.idle.emit()

    def _add_segments(self, segs: list[dict]) -> None:
        if self.data is None:
            return
        self.data["segments"].extend(segs)
        self.data["segments"].sort(key=lambda s: s["t"])
        self._render_text()
        self._render_speakers()
        if len(self.data["segments"]) % 5 == 0:
            self._save()

    def _worker_idle(self) -> None:
        self.worker = None
        self.start_btn.setEnabled(True)
        self.status.setText(self.tr_("ts.saved"))
        self._save()
        self.reload()
        if self.auto_sum.isChecked() and self.data and self.data["segments"] and self.sum_conn.currentData():
            self.summarize()

    # --- Darstellung --------------------------------------------------------------------------------
    def _color(self, sid: str) -> str:
        with self.lock:
            keys = list((self.data or {}).get("speakers", {}).keys())
        return COLORS[keys.index(sid) % len(COLORS)] if sid in keys else "#9ca3af"

    def _render_text(self) -> None:
        if self.data is None:
            self.text.clear()
            return
        with self.lock:
            names = {sid: s["name"] for sid, s in self.data["speakers"].items()}
        parts = []
        prev = None
        for seg in self.data["segments"]:
            sid = seg.get("speaker")
            head = ""
            if sid != prev:
                head = (f"<div style='margin-top:8px'><span style='color:{self._color(sid)};font-weight:700'>"
                        f"{html.escape(names.get(sid, sid or '?'))}</span> "
                        f"<span style='color:#9ca3af'>{_clock(seg.get('t') or 0)}</span></div>")
            parts.append(head + f"<div>{html.escape(seg.get('text', ''))}</div>")
            prev = sid
        bar = self.text.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        self.text.setHtml("".join(parts))
        if at_end:
            bar.setValue(bar.maximum())

    def _render_speakers(self) -> None:
        with self.lock:
            speakers = dict((self.data or {}).get("speakers") or {})
        counts: dict[str, int] = {}
        for seg in (self.data or {}).get("segments") or []:
            counts[seg.get("speaker")] = counts.get(seg.get("speaker"), 0) + 1
        profiles = {p["id"]: p["name"] for p in self.profiles.load()} if speakers else {}
        self.spk_table.setRowCount(len(speakers))
        for r, (sid, s) in enumerate(speakers.items()):
            it = QTableWidgetItem("● " + s.get("name", sid))
            it.setForeground(QColor(self._color(sid)))
            it.setData(Qt.ItemDataRole.UserRole, sid)
            self.spk_table.setItem(r, 0, it)
            self.spk_table.setItem(r, 1, QTableWidgetItem(profiles.get(s.get("profile"), "–")))
            self.spk_table.setItem(r, 2, QTableWidgetItem(str(counts.get(sid, 0))))

    def _selected_speaker(self) -> str:
        r = self.spk_table.currentRow()
        return self.spk_table.item(r, 0).data(Qt.ItemDataRole.UserRole) if r >= 0 else ""

    # --- Sprecher -----------------------------------------------------------------------------------
    def rename_speaker(self) -> None:
        sid = self._selected_speaker()
        if not sid or self.data is None:
            return
        cur = self.data["speakers"][sid]["name"]
        new, ok = QInputDialog.getText(self, self.tr_("ts.rename"), self.tr_("ts.col.name"), text=cur)
        if ok and new.strip():
            self.data["speakers"][sid]["name"] = new.strip()
            self._render_text()
            self._render_speakers()
            self._save()

    def save_profile(self) -> None:
        """Stimme dieses Sprechers als dauerhaftes Profil speichern (Merkmale + bis zu 10 s Probe)."""
        tr = self.tr_
        sid = self._selected_speaker()
        if not sid or self.data is None:
            return
        if not (self.data.get("consent") or {}).get("profiles"):
            QMessageBox.information(self, tr("ts.profiles.title"), tr("ts.profiles.no_consent"))
            return
        s = self.data["speakers"][sid]
        pieces = [self.audio_cache[seg["audio"]] for seg in self.data["segments"]
                  if seg.get("speaker") == sid and seg.get("audio") in self.audio_cache]
        if not pieces:
            QMessageBox.information(self, tr("ts.profiles.title"), tr("ts.profiles.no_audio"))
            return
        import numpy as np
        from omniwrench.ai.speech import wav_bytes
        joined = np.concatenate(pieces)
        sample = joined[:int(spk.SAMPLE_MAX * audio.RATE)]
        if len(sample) < 2 * audio.RATE:
            QMessageBox.information(self, tr("ts.profiles.title"), tr("ts.profiles.too_short"))
            return
        name, ok = QInputDialog.getText(self, tr("ts.save_profile"), tr("ts.col.name"), text=s["name"])
        if not ok or not name.strip():
            return
        prof = self.profiles.upsert(name.strip(), spk.embedding(joined) or s.get("embedding"), wav_bytes(sample),
                                    s.get("profile") or "")
        s.update(name=prof["name"], profile=prof["id"])
        self._render_text()
        self._render_speakers()
        self._save()
        self.status.setText(tr("ts.profiles.saved", name=prof["name"]))

    def merge_speaker(self) -> None:
        """Zwei Sprecher zusammenlegen (Erkennung hat eine Person doppelt angelegt)."""
        tr = self.tr_
        sid = self._selected_speaker()
        if not sid or self.data is None:
            return
        others = [(k, v["name"]) for k, v in self.data["speakers"].items() if k != sid]
        if not others:
            return
        names = [n for _, n in others]
        choice, ok = QInputDialog.getItem(self, tr("ts.merge"), tr("ts.merge_into",
                                                                  name=self.data["speakers"][sid]["name"]),
                                          names, 0, False)
        if not ok:
            return
        target = others[names.index(choice)][0]
        for seg in self.data["segments"]:
            if seg.get("speaker") == sid:
                seg["speaker"] = target
        with self.lock:
            self.data["speakers"].pop(sid, None)
        self._render_text()
        self._render_speakers()
        self._save()

    # --- Speichern / Laden --------------------------------------------------------------------------
    def _title_changed(self) -> None:
        if self.data is not None and self.title.text().strip() and self.title.text().strip() != self.data["title"]:
            self.data["title"] = self.title.text().strip()
            self._save()
            self.reload()

    def _stored(self) -> dict:
        """Mitschrift ohne Audio-Verweise und ohne Stimmmerkmale (die bleiben nur im Speicher)."""
        with self.lock:
            speakers = {sid: {k: v for k, v in s.items() if k != "embedding"}
                        for sid, s in self.data["speakers"].items()}
        return dict(self.data, speakers=speakers,
                    segments=[{k: v for k, v in s.items() if k != "audio"} for s in self.data["segments"]])

    def _save(self) -> None:
        if self.data is None:
            return
        data = self._stored()
        try:
            self.services.storage.save_transcript(data)
        except Exception as err:  # noqa: BLE001 - Tresor gesperrt o. Ä.
            self.status.setText("⚠ " + str(err))

    def open(self, tid: str) -> None:
        if self.running:
            return
        data = self.services.storage.load_transcript(tid)
        if not data:
            self.status.setText("⚠ " + self.tr_("ts.locked"))
            return
        self.data = data
        self.audio_cache = {}
        self.title.setText(data.get("title", ""))
        self.summary.setMarkdown(data.get("summary") or "")
        self._render_text()
        self._render_speakers()
        self.status.setText("")

    def _history_menu(self, pos) -> None:
        item = self.history.itemAt(pos)
        if item is None or self.running:
            return
        tid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction(self.tr_("ts.delete"), lambda: self.delete(tid))
        menu.exec(self.history.viewport().mapToGlobal(pos))

    def delete(self, tid: str) -> None:
        if QMessageBox.question(self, self.tr_("ts.delete"), self.tr_("ts.delete_q")) \
                != QMessageBox.StandardButton.Yes:
            return
        self.services.storage.delete_transcript(tid)
        if self.data and self.data.get("id") == tid:
            self.data = None
            self.text.clear()
            self.summary.clear()
            self._render_speakers()
        self.reload()

    def plain_text(self) -> str:
        if not self.data:
            return ""
        names = {sid: s["name"] for sid, s in self.data["speakers"].items()}
        return "\n".join(f"[{_clock(s.get('t') or 0)}] {names.get(s.get('speaker'), '?')}: {s.get('text', '')}"
                         for s in self.data["segments"])

    def to_chat(self) -> None:
        if not self.data or not self.data["segments"]:
            return
        text = self.plain_text()
        if self.data.get("summary"):
            text = f"{self.tr_('ts.view.summary')}:\n{self.data['summary']}\n\n{text}"
        self.studio.panel.add_text_attachment((self.data.get("title") or "Mitschrift") + ".txt", text[:100_000])
        self.studio.modes.setCurrentIndex(0)
        self.studio.panel.focus_input()

    def export(self) -> None:
        if not self.data:
            return
        from omniwrench.ai.speech import transcript_markdown
        from .documents import safe_name
        path, _ = QFileDialog.getSaveFileName(self, self.tr_("ts.export"), safe_name(self.data["title"]) + ".md",
                                              "Markdown (*.md)")
        if path:
            data = self._stored()
            with open(path, "w", encoding="utf-8") as f:
                f.write(transcript_markdown(data))
            self.status.setText(self.tr_("ts.exported", name=path))

    # --- Zusammenfassung ----------------------------------------------------------------------------
    def summarize(self) -> None:
        tr = self.tr_
        if self._summarizing or not self.data or not self.data["segments"]:
            return
        conn = self.services.connections.get(self.sum_conn.currentData() or "")
        if conn is None:
            return
        self.settings.set("ts_summary_connection", conn.id)
        from omniwrench.core.i18n import current_language
        system = ("You summarize a meeting transcript for system administrators. Write in the language with code "
                  f"'{current_language() or 'en'}', formal and neutral. Use Markdown with these sections: Summary "
                  "(3-6 sentences), Decisions, Action items (who, what, until when if mentioned), Open questions. "
                  "Only use facts from the transcript; if a section is empty, write '–'. Speaker names are as given.")
        text = self.plain_text()
        self._summarizing = True
        self._sum_stop = threading.Event()
        self.sum_btn.setEnabled(False)
        self.status.setText(tr("ts.summarizing", name=conn.name))
        self.views.setCurrentWidget(self.summary)
        self.summary.clear()
        buf: list[str] = []
        stop = self._sum_stop

        def task():
            answer, _decode = ask_once(self.services, self.studio.context.manifest.id, conn, system, text,
                                       lambda d, dec: buf.append(d), stop)
            return answer

        def done(answer):
            self._summarizing = False
            self.sum_btn.setEnabled(True)
            if self.data is None:
                return
            self.data["summary"] = answer
            self.data["summary_connection"] = conn.name
            self.summary.setMarkdown(answer)
            self.status.setText(tr("ts.summary_done"))
            self._save()

        def failed(err):
            self._summarizing = False
            self.sum_btn.setEnabled(True)
            self.status.setText("⚠ " + err.splitlines()[0])
        run_async(task, done, failed)

    def shutdown(self) -> None:
        self.stop()
        self._sum_stop.set()
        self.stop_event.set()
        self.queue.put(None)
        self._save()


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
