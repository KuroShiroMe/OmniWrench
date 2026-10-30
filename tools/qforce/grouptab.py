"""Reiter „Gruppenchat“: Teilnehmer, Thema, Optionen (gruppiert, einklappbar), Verlauf, Einwürfe."""

from __future__ import annotations

import html
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter,
    QStackedWidget, QTableWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from omniwrench.sdk import run_async

from . import group as gm
from omniwrench.ui.ai_kit import NoBotPage, Section  # noqa: F401 - Section für ältere Importe

COLORS = ("#8b5cf6", "#0ea5e9", "#f59e0b", "#10b981", "#ef4444", "#ec4899")


class _Bridge(QObject):
    turn = Signal(object)
    text = Signal(str, str)
    message = Signal(object)
    finished = Signal(str)
    failed = Signal(str)


def _md_html(text: str) -> str:
    doc = QTextDocument()
    doc.setMarkdown(text)
    out = doc.toHtml()
    start, end = out.find("<body"), out.rfind("</body>")
    if start < 0 or end < 0:
        return html.escape(text)
    return out[out.find(">", start) + 1:end]


class GroupTab(QWidget):
    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.services = studio.services
        self.store = gm.GroupStore(self.services.storage)
        tr = self.tr_ = studio.tr
        self.thread: dict | None = None
        self._stop: threading.Event | None = None
        self._pause: threading.Event | None = None
        self._paused = False
        self._queue: list[str] = []
        self._qlock = threading.Lock()
        self._live: dict | None = None
        self._decode = lambda t: t
        self.bridge = _Bridge()
        self.bridge.turn.connect(self._on_turn)
        self.bridge.text.connect(self._on_text)
        self.bridge.message.connect(self._on_message)
        self.bridge.finished.connect(self._on_finished)
        self.bridge.failed.connect(self._on_failed)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(150)
        self._render_timer.timeout.connect(self.render)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.stack.addWidget(NoBotPage(tr("grp.no_bot"), tr("ui.open_ai_options"), self.services.open_options))
        page = QWidget()
        self.stack.addWidget(page)
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split)

        # --- links: gespeicherte Gruppenchats
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        new_btn = QPushButton("＋ " + tr("grp.new"))
        new_btn.clicked.connect(self.new_group)
        sl.addWidget(new_btn)
        self.history = QListWidget()
        self.history.itemClicked.connect(lambda it: self.open_group(it.data(Qt.ItemDataRole.UserRole)))
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self._history_menu)
        sl.addWidget(self.history, 1)
        split.addWidget(side)

        # --- Mitte: Einrichtung oder Verlauf
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        self.setup = self._build_setup()
        cl.addWidget(self.setup, 1)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        cl.addWidget(self.view, 1)
        self.view.hide()
        bar = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(tr("grp.interject_hint"))
        self.input.returnPressed.connect(self.interject)
        bar.addWidget(self.input, 1)
        self.send_btn = QPushButton(tr("grp.interject"))
        self.send_btn.clicked.connect(self.interject)
        bar.addWidget(self.send_btn)
        self.start_btn = QPushButton("▶ " + tr("grp.start"))
        self.start_btn.clicked.connect(self._start_or_continue)
        bar.addWidget(self.start_btn)
        self.stop_btn = QPushButton("■ " + tr("grp.stop"))
        self.stop_btn.clicked.connect(self.stop)
        bar.addWidget(self.stop_btn)
        cl.addLayout(bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        cl.addWidget(self.status)
        split.addWidget(center)
        split.setSizes([220, 900])
        self._update_buttons()

    # --- Einrichtung ---------------------------------------------------------------------------------
    def _build_setup(self) -> QWidget:
        tr = self.tr_
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        intro = QLabel(tr("grp.intro"))
        intro.setWordWrap(True)
        intro.setEnabled(False)
        lay.addWidget(intro)

        # Teilnehmer
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("grp.col.name"), tr("grp.col.assistant"), tr("grp.col.role")])
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        head.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 220)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(120)
        pl.addWidget(self.table)
        row = QHBoxLayout()
        self.add_btn = QPushButton("＋ " + tr("grp.add"))
        self.add_btn.clicked.connect(lambda: self.add_participant())
        row.addWidget(self.add_btn)
        rm = QPushButton("－ " + tr("grp.remove"))
        rm.clicked.connect(self.remove_participant)
        row.addWidget(rm)
        row.addStretch()
        pl.addLayout(row)
        lay.addWidget(Section(tr("grp.sec.participants"), pw, True))

        # Thema
        self.topic = QPlainTextEdit()
        self.topic.setPlaceholderText(tr("grp.topic_hint"))
        self.topic.setMaximumHeight(110)
        lay.addWidget(Section(tr("grp.sec.topic"), self.topic, True))

        # Ablauf
        fw = QWidget()
        f = QFormLayout(fw)
        self.mode = QComboBox()
        for m in gm.MODES:
            self.mode.addItem(tr("grp.mode." + m), m)
        f.addRow(tr("grp.mode"), self.mode)
        self.order = QComboBox()
        for o in gm.ORDERS:
            self.order.addItem(tr("grp.order." + o), o)
        f.addRow(tr("grp.order"), self.order)
        self.detail = QComboBox()
        for d in ("short", "normal", "detailed"):
            self.detail.addItem(tr("grp.detail." + d), d)
        f.addRow(tr("grp.detail"), self.detail)
        self.summary = QCheckBox(tr("grp.summary"))
        f.addRow("", self.summary)
        lay.addWidget(Section(tr("grp.sec.flow"), fw))

        # Bremsen
        bw = QWidget()
        b = QFormLayout(bw)
        self.spins: dict[str, QSpinBox] = {}
        for key, suffix in (("rounds", ""), ("max_messages", ""), ("max_chars", ""), ("time_limit", " min"),
                            ("token_budget", "")):
            s = QSpinBox()
            lo, hi = gm.LIMITS[key]
            s.setRange(lo, hi)
            if key == "token_budget":
                s.setSingleStep(5000)
            elif key == "max_chars":
                s.setSingleStep(250)
            s.setSuffix(suffix)
            self.spins[key] = s
            b.addRow(tr("grp.opt." + key), s)
        self.checks: dict[str, QCheckBox] = {}
        for key in ("pause_each_round", "stop_on_agree", "stop_on_repeat"):
            c = QCheckBox(tr("grp.opt." + key))
            self.checks[key] = c
            b.addRow("", c)
        lay.addWidget(Section(tr("grp.sec.brakes"), bw))

        # Datenschutz
        priv = QLabel(tr("grp.privacy"))
        priv.setWordWrap(True)
        lay.addWidget(Section(tr("grp.sec.privacy"), priv))
        lay.addStretch()
        scroll.setWidget(host)
        self._load_options(self.studio.context.settings.get("group_options") or {})
        return scroll

    def _load_options(self, raw: dict) -> None:
        o = gm.options(raw)
        self.mode.setCurrentIndex(max(0, self.mode.findData(o["mode"])))
        self.order.setCurrentIndex(max(0, self.order.findData(o["order"])))
        self.detail.setCurrentIndex(max(0, self.detail.findData(o["detail"])))
        self.summary.setChecked(o["summary"])
        for k, s in self.spins.items():
            s.setValue(o[k])
        for k, c in self.checks.items():
            c.setChecked(o[k])

    def current_options(self) -> dict:
        o = {"mode": self.mode.currentData(), "order": self.order.currentData(), "detail": self.detail.currentData(),
             "summary": self.summary.isChecked()}
        o.update({k: s.value() for k, s in self.spins.items()})
        o.update({k: c.isChecked() for k, c in self.checks.items()})
        return gm.options(o)

    def _conn_combo(self, selected: str = "") -> QComboBox:
        box = QComboBox()
        for c in self.services.connections.chat_connections():
            if c.info is not None and c.info.removed:
                continue
            box.addItem(c.name, c.id)
        box.setCurrentIndex(max(0, box.findData(selected)))
        return box

    def add_participant(self, conn_id: str = "", name: str = "", role: str = "") -> None:
        if self.table.rowCount() >= gm.MAX_PARTICIPANTS:
            self.status.setText(self.tr_("grp.too_many", n=gm.MAX_PARTICIPANTS))
            return
        r = self.table.rowCount()
        self.table.insertRow(r)
        box = self._conn_combo(conn_id)
        if not conn_id and box.count():
            box.setCurrentIndex(r % box.count())
        self.table.setCellWidget(r, 1, box)
        name_edit = QLineEdit(name or self.tr_("grp.default_name", n=r + 1))
        self.table.setCellWidget(r, 0, name_edit)
        self.table.setCellWidget(r, 2, QLineEdit(role))

    def remove_participant(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            r = self.table.rowCount() - 1
        if r >= 0:
            self.table.removeRow(r)

    def participants(self) -> list[dict]:
        out = []
        for r in range(self.table.rowCount()):
            box = self.table.cellWidget(r, 1)
            name = self.table.cellWidget(r, 0).text().strip() or self.tr_("grp.default_name", n=r + 1)
            if box is not None and box.currentData():
                out.append(gm.new_participant(box.currentData(), name, self.table.cellWidget(r, 2).text().strip()))
        names = [p["name"] for p in out]
        for p in out:     # gleiche Namen unterscheidbar machen
            if names.count(p["name"]) > 1:
                p["name"] = f"{p['name']} ({p['id'][:3]})"
        return out

    # --- Verwaltung ----------------------------------------------------------------------------------
    def refresh(self) -> None:
        conns = [c for c in self.services.connections.chat_connections() if not (c.info and c.info.removed)]
        self.stack.setCurrentIndex(1 if conns else 0)
        if conns and self.table.rowCount() == 0 and self.thread is None:
            for i in range(min(2, len(conns))):
                self.add_participant(conns[i].id, conns[i].name)
        self.reload_history()

    def reload_history(self) -> None:
        self.history.clear()
        for t in self.store.list():
            when = time.strftime("%d.%m. %H:%M", time.localtime(t["updated"])) if t["updated"] else ""
            item = QListWidgetItem(("🔒 " if t.get("locked") else "") + f"{t['title']}\n{when}")
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self.history.addItem(item)
            if self.thread is not None and self.thread.get("id") == t["id"]:
                item.setSelected(True)

    def _history_menu(self, pos) -> None:
        item = self.history.itemAt(pos)
        if item is None:
            return
        gid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction(self.tr_("grp.reuse"), lambda: self.reuse(gid))
        menu.addAction(self.tr_("grp.reveal"), lambda: self._reveal(gid))
        menu.addAction(self.tr_("grp.delete"), lambda: self.delete(gid))
        menu.exec(self.history.viewport().mapToGlobal(pos))

    def _reveal(self, gid: str) -> None:
        d = self.store.base() / gid
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d if d.exists() else self.store.base())))

    def new_group(self) -> None:
        if self.running:
            return
        self.thread = None
        self._show_setup(True)
        self.topic.clear()
        self.status.setText("")
        self.render()
        self._update_buttons()

    def open_group(self, gid: str) -> None:
        if self.running:
            return
        t = self.store.load(gid)
        if not t:
            QMessageBox.warning(self, self.tr_("grp.title"), self.tr_("grp.unreadable"))
            return
        self.thread = t
        self._show_setup(False)
        self.render()
        self._update_buttons()

    def reuse(self, gid: str) -> None:
        """Teilnehmer, Thema und Optionen eines alten Gruppenchats für einen neuen übernehmen."""
        t = self.store.load(gid)
        if not t or self.running:
            return
        self.new_group()
        self.table.setRowCount(0)
        for p in t.get("participants", []):
            self.add_participant(p.get("connection", ""), p.get("name", ""), p.get("role", ""))
        self.topic.setPlainText(t.get("topic", ""))
        self._load_options(t.get("options") or {})

    def delete(self, gid: str) -> None:
        if QMessageBox.question(self, self.tr_("grp.delete"), self.tr_("grp.delete_q")) \
                != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(gid)
        if self.thread is not None and self.thread.get("id") == gid:
            self.new_group()
        self.reload_history()

    def _show_setup(self, on: bool) -> None:
        self.setup.setVisible(on)
        self.view.setVisible(not on)

    # --- Ablauf --------------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._stop is not None

    def _update_buttons(self) -> None:
        run = self.running
        self.start_btn.setText(("▶ " + self.tr_("grp.continue")) if self._paused else ("▶ " + self.tr_("grp.start")))
        self.start_btn.setEnabled(not run or self._paused)
        self.start_btn.setVisible(self.thread is None or self._paused)
        self.stop_btn.setEnabled(run)
        self.input.setEnabled(run)
        self.send_btn.setEnabled(run)

    def _start_or_continue(self) -> None:
        if self._paused and self._pause is not None:
            self._paused = False
            self._pause.set()
            self.status.setText("")
            self._update_buttons()
            return
        self.start()

    def start(self) -> bool:
        tr = self.tr_
        parts = self.participants()
        topic = self.topic.toPlainText().strip()
        if not parts:
            self.status.setText(tr("grp.need_participants"))
            return False
        if not topic:
            self.status.setText(tr("grp.need_topic"))
            return False
        opts = self.current_options()
        self.studio.context.settings.set("group_options", opts)
        self.thread = gm.new_thread(topic, parts, opts)
        self._show_setup(False)
        self._queue = []
        self._live = None
        self.render()
        self._run()
        return True

    def _run(self) -> None:
        from omniwrench.ai import access, adapters
        from omniwrench.ai.pseudo import Pseudonymizer
        thread = self.thread
        settings = self.services.settings
        tool_id = self.studio.context.manifest.id
        pseudo = Pseudonymizer(thread.setdefault("state", {}).setdefault("pseudo", {}), access.pseudo_kinds(settings),
                               enabled=access.pseudo_enabled(settings, tool_id))
        self._decode = pseudo.decode
        store = self.services.connections
        stop = self._stop = threading.Event()
        pause = self._pause = threading.Event()
        b = self.bridge

        def chat_fn(p, system, msgs, on_text, turn_stop):
            conn = store.get(p["connection"])
            if conn is None:
                raise RuntimeError(self.tr_("grp.missing_conn", name=p["name"]))
            state = thread["state"].setdefault("p_" + p["id"], {})
            return adapters.for_connection(store, conn).chat(
                system, msgs, [], lambda kind, data: on_text(data) if kind == "text" else None, turn_stop, state)

        def wait(round_no: int) -> bool:
            pause.clear()
            while not pause.wait(0.2):
                if stop.is_set():
                    return False
            return not stop.is_set()

        def pending() -> list[str]:
            with self._qlock:
                out, self._queue = self._queue, []
            return out

        hooks = gm.GroupHooks(on_turn=lambda p: b.turn.emit(dict(p)), on_text=b.text.emit,
                              on_message=lambda m: b.message.emit(dict(m)), pause=wait, pending_user=pending,
                              encode=pseudo.encode, decode=pseudo.decode)
        runner = gm.GroupRun(thread, chat_fn, hooks, stop)

        def task():
            from omniwrench.ai import chat
            try:
                reason = runner.run()
            except Exception as err:  # noqa: BLE001 - als Text anzeigen
                b.failed.emit(chat.error_text(err))
                return
            b.finished.emit(reason)

        self._update_buttons()
        run_async(task)

    def interject(self) -> None:
        text = self.input.text().strip()
        if not text or not self.running:
            return
        with self._qlock:
            self._queue.append(text)
        self.input.clear()
        self.status.setText(self.tr_("grp.queued"))

    def stop(self) -> None:
        if self._stop is None:
            return
        self._stop.set()
        if self._pause is not None:
            self._pause.set()
        self._finish(self.tr_("grp.end.stopped"))

    def _finish(self, text: str) -> None:
        self._stop = None
        self._pause = None
        self._paused = False
        if self._live is not None and self._live.get("content") and self.thread is not None:
            self.thread["messages"].append(dict(self._live, cut=True))
        self._live = None
        self.status.setText(text)
        self._save()
        self.render()
        self._update_buttons()

    def _save(self) -> None:
        if self.thread is not None and len(self.thread.get("messages", [])) > 1:
            try:
                self.store.save(self.thread, self.tr_("grp.you"))
            except OSError as e:
                self.status.setText("⚠ " + str(e))
            self.reload_history()

    # --- Signale -------------------------------------------------------------------------------------
    def _on_turn(self, p: dict) -> None:
        if not self.running:
            return
        self._live = {"role": "assistant", "content": "", "participant": p["id"], "name": p["name"],
                      "ts": int(time.time())}
        self.status.setText(self.tr_("grp.speaking", name=p["name"]))
        self.render()

    def _on_text(self, pid: str, delta: str) -> None:
        if not self.running or self._live is None:
            return
        self._live["raw"] = self._live.get("raw", "") + delta
        self._live["content"] = self._decode(self._live["raw"])
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _on_message(self, msg: dict) -> None:
        if not self.running:
            return
        if msg["role"] == "assistant":
            self._live = None
        if msg["role"] == "brake" and msg.get("content") == "pause":
            self._paused = True
            self.status.setText(self.tr_("grp.paused", n=msg.get("round", "")))
            self._update_buttons()
        self._save()
        self.render()
        self._update_counts()

    def _update_counts(self) -> None:
        t = self.thread or {}
        spoken = sum(1 for m in t.get("messages", []) if m["role"] == "assistant" and not m.get("summary"))
        tokens = sum(int(u.get("input", 0)) + int(u.get("output", 0)) for u in (t.get("usage") or {}).values())
        o = gm.options(t.get("options"))
        if not self._paused and self.running and self._live is None:
            self.status.setText(self.tr_("grp.counts", n=spoken, max=o["max_messages"], tokens=tokens))

    def _on_finished(self, reason: str) -> None:
        if not self.running:
            return
        self._finish(self.tr_("grp.end." + reason))

    def _on_failed(self, text: str) -> None:
        if not self.running:
            return
        if self.thread is not None:
            self.thread["messages"].append({"role": "error", "content": text, "ts": int(time.time())})
        self._finish("⚠ " + text)

    # --- Anzeige -------------------------------------------------------------------------------------
    def render(self) -> None:
        t = self.thread
        if t is None:
            self.view.setHtml(f"<p style='color:gray'>{html.escape(self.tr_('grp.intro'))}</p>")
            return
        colors = {p["id"]: COLORS[i % len(COLORS)] for i, p in enumerate(t.get("participants", []))}
        parts = [f"<h3>{html.escape(t.get('title', ''))}</h3>"]
        msgs = list(t.get("messages", []))
        if self._live is not None:
            msgs.append(dict(self._live, live=True))
        for m in msgs:
            role = m["role"]
            when = time.strftime("%H:%M", time.localtime(m.get("ts") or time.time()))
            if role == "user":
                parts.append(f"<p><b>{html.escape(self.tr_('grp.you'))}</b> "
                             f"<span style='color:gray'>{when}</span></p>{_md_html(m.get('content', ''))}")
            elif role == "assistant":
                color = colors.get(m.get("participant"), "#888")
                tags = []
                if m.get("summary"):
                    tags.append(self.tr_("grp.tag.summary"))
                if m.get("agree"):
                    tags.append("✓ " + self.tr_("grp.tag.agree"))
                if m.get("cut"):
                    tags.append("✂ " + self.tr_("grp.tag.cut"))
                if m.get("live"):
                    tags.append("…")
                tag = (" <span style='color:gray'>· " + " · ".join(html.escape(x) for x in tags) + "</span>") \
                    if tags else ""
                parts.append(f"<p><b style='color:{color}'>● {html.escape(m.get('name', ''))}</b> "
                             f"<span style='color:gray'>{when}</span>{tag}</p>{_md_html(m.get('content', ''))}")
            elif role == "brake":
                if m.get("content") == "pause":
                    text = self.tr_("grp.paused", n=m.get("round", ""))
                elif m.get("content") == "wait":
                    text = self.tr_("grp.wait", who=m.get("who", ""), seconds=m.get("seconds", ""))
                else:
                    text = self.tr_("grp.end." + m.get("content", ""), who=m.get("who", ""))
                parts.append(f"<p style='color:gray'><i>⏸ {html.escape(text)}</i></p>")
            elif role == "error":
                parts.append(f"<p style='color:#d33'>⚠ {html.escape(m.get('content', ''))}</p>")
        bar = self.view.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 30
        self.view.setHtml("<hr>".join(parts) if len(parts) < 2 else parts[0] + "".join(
            "<hr>" + p for p in parts[1:]))
        if at_end:
            bar.setValue(bar.maximum())

    def shutdown(self) -> None:
        if self.running:
            self.stop()
