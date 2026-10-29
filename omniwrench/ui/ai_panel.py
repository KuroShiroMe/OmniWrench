"""Chatleiste des Hauptprogramms (andockbar, standardmäßig rechts).

Minimalistisch: Assistent wählen (auch mitten im Chat), Detailgrad, Projekt, Verlauf, neuer Chat.
Der Chat läuft im Hintergrund (ai.chat.run); Teiltexte kommen über Signale in die Oberfläche.
"""

from __future__ import annotations

import base64
import mimetypes
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QGuiApplication, QKeyEvent, QSyntaxHighlighter, QTextCharFormat,
)
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QScrollArea, QSizePolicy,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from omniwrench.ai import access, chat, functions, models
from omniwrench.ai.app_functions import register_app_functions
from omniwrench.ai.pseudo import Pseudonymizer
from omniwrench.ai.connections import Connection, ConnectionStore
from omniwrench.ai.http import AIError, Cancelled
from omniwrench.ai.storage import Storage
from omniwrench.core.i18n import tr

from . import theme
from .widgets import label, make_button
from .workers import call_in_gui, run_async

DETAIL_KEY = "ai_detail"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".log", ".json", ".xml", ".csv", ".ps1", ".py", ".ini", ".cfg", ".yaml", ".yml",
                 ".conf", ".html", ".css", ".js", ".sh", ".bat", ".cmd", ".reg", ".sql"}


def panel_stylesheet() -> str:
    c = theme.current
    return f"""
    #AIPanel {{ background: {c['bg']}; }}
    #AIChatArea, #AIChatHost {{ background: {c['bg']}; border: none; }}
    #AIUser {{ background: {c['selection']}; border-radius: 12px; }}
    #AIAssistant {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    #AIError {{ background: {c['surface']}; border: 1px solid {c['danger']}; border-radius: 10px; }}
    #AIMeta {{ color: {c['muted']}; font-size: 8.5pt; }}
    #AIChip {{ color: {c['muted']}; font-size: 8.5pt; background: {c['surface2']}; border-radius: 9px; padding: 2px 8px; }}
    #AIDivider {{ color: {c['muted']}; font-size: 8.5pt; }}
    #AIInputBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    #AIInputBox QPlainTextEdit {{ background: transparent; border: none; padding: 4px; }}
    #AIPanel QToolButton {{ border: none; border-radius: 6px; padding: 4px 6px; }}
    #AIPanel QToolButton:hover {{ background: {c['surface2']}; }}
    QToolButton#AISend {{ background: {c['accent']}; color: white; border-radius: 15px; font-weight: 600; }}
    QToolButton#AISend:hover {{ background: {c['accent_hover']}; }}
    QToolButton#AISend[stop="true"] {{ background: {c['danger']}; }}
    #AIEmpty {{ color: {c['muted']}; }}
    """


class _Bridge(QObject):
    text = Signal(str)
    tool = Signal(object)
    tool_done = Signal(object, str, bool)
    message = Signal(object)
    finished = Signal()
    failed = Signal(object)


class _Input(QPlainTextEdit):
    """Enter sendet, Umschalt+Enter fügt eine Zeile ein; wächst bis zu einer Höchsthöhe mit."""
    submit = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(tr("ai.panel.placeholder"))
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().contentsChanged.connect(self._grow)
        self._grow()

    def keyPressEvent(self, e: QKeyEvent):  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submit.emit()
            return
        super().keyPressEvent(e)

    def _grow(self) -> None:
        line = self.fontMetrics().lineSpacing()
        lines = max(1, min(int(self.document().size().height()), 8))
        self.setFixedHeight(int(lines * line + 16))


class MessageWidget(QFrame):
    """Eine Nachricht: Benutzer rechts, Assistent links mit Kopfzeile, Funktions-Chips und Aktionen."""

    def __init__(self, msg: dict, panel: "AIPanel"):
        super().__init__()
        self.msg = msg
        self.panel = panel
        role = msg["role"]
        self.setObjectName({"user": "AIUser", "assistant": "AIAssistant", "error": "AIError"}.get(role, ""))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)
        if role == "assistant":
            when = time.strftime("%H:%M", time.localtime(msg.get("ts") or time.time()))
            model = f" · {msg['model']}" if msg.get("model") else ""
            lay.addWidget(label(f"✦ {msg.get('connection_name', '')}{model} · {when}", "AIMeta"))
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.body.setOpenExternalLinks(True)
        self.body.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if role == "error":
            self.body.setTextFormat(Qt.TextFormat.RichText)
            self.body.setOpenExternalLinks(False)
            self.body.linkActivated.connect(lambda _l: panel.open_options())
            text = f"⚠ {msg.get('content', '')}"
            if msg.get("options_link"):
                text += f"<br><a href='options'>{tr('ai.panel.open_options')}</a>"
            self.body.setText(text)
        else:
            self.body.setTextFormat(Qt.TextFormat.MarkdownText if role == "assistant" else Qt.TextFormat.PlainText)
            self.body.setText(msg.get("content", ""))
        self._chip_ids: set = set()
        self.chips = QHBoxLayout()
        self.chips.setSpacing(4)
        lay.addLayout(self.chips)   # Funktions-Chips über dem Text: erst nachschlagen, dann antworten
        lay.addWidget(self.body)
        for img in msg.get("images") or []:
            lay.addWidget(label("🖼 " + img.get("name", tr("ai.panel.image")), "AIMeta"))
        for call in msg.get("tool_calls") or []:
            self.add_chip(call)
        if role == "assistant":
            row = QHBoxLayout()
            row.setSpacing(2)
            copy = QToolButton(text="⧉")
            copy.setToolTip(tr("ai.panel.copy"))
            copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.msg.get("content", "")))
            row.addWidget(copy)
            row.addStretch()
            self.actions = QWidget()
            self.actions.setLayout(row)
            row.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self.actions)
            self.actions.setVisible(bool(msg.get("content")))
            self.body.setVisible(bool(msg.get("content")))
        self._buffer = msg.get("content", "") if role == "assistant" else ""
        self._new_round = False
        self._raw = self._buffer
        self.decoder = lambda text: text

    def add_chip(self, call: dict) -> None:
        if call.get("id") and call["id"] in self._chip_ids:
            return
        self._chip_ids.add(call.get("id"))
        if self.chips.count():
            self.chips.takeAt(self.chips.count() - 1)   # Stretch ans Ende verschieben
        chip = label("⚙ " + tr("ai.panel.function", name=call.get("name", "")), "AIChip")
        chip.setToolTip(str(call.get("arguments") or ""))
        self.chips.addWidget(chip)
        self.chips.addStretch()

    def append(self, delta: str) -> None:
        """Gestreamter Text. Text einer neuen Runde (nach Funktionsaufrufen) kommt als neuer Absatz.

        Der Rohtext kann Platzhalter der Verfremdung enthalten (auch über Teilstücke verteilt),
        angezeigt wird immer die vollständig zurückübersetzte Fassung.
        """
        if self._new_round and self._raw:
            self._raw += "\n\n"
        self._new_round = False
        self._raw += delta
        try:
            self._buffer = self.decoder(self._raw)
        except RuntimeError:   # Zuordnung wurde gerade im Hintergrund erweitert
            self._buffer = self._raw
        self.body.setText(self._buffer)
        self.body.setVisible(True)

    def end_round(self, msg: dict) -> None:
        """Eine Runde ist fertig: Funktions-Chips ergänzen; bei Funktionsaufrufen folgt eine weitere Runde."""
        for call in msg.get("tool_calls") or []:
            self.add_chip(call)
        self._new_round = True
        self.msg = {**msg, "content": self._buffer}
        self.body.setVisible(bool(self._buffer))
        if hasattr(self, "actions"):
            self.actions.setVisible(bool(self._buffer) and not msg.get("tool_calls"))

    def add_round(self, msg: dict) -> None:
        """Gespeicherte Folge-Nachricht (Verlauf öffnen) in diese Blase übernehmen."""
        if msg.get("content"):
            self._new_round = True
            self.append(msg["content"])
        self.end_round(msg)


class _DiffHighlighter(QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:  # noqa: N802
        c = theme.current
        color = (c.get("success", "#10b981") if text.startswith("+") and not text.startswith("+++") else
                 c.get("danger", "#ef4444") if text.startswith("-") and not text.startswith("---") else
                 c.get("accent", "#3b82f6") if text.startswith("@@") else None)
        if color:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            self.setFormat(0, len(text), f)


class ConfirmDialog(QDialog):
    """Rückfrage vor einer Änderung durch den Assistenten, mit „für diese Sitzung merken“.

    text: Satz („Reservierung … anlegen?“) oder dict {"text", "code", "explanation"} für Befehle:
    der Befehl erscheint in Festbreitenschrift, darunter die kurze Erklärung des Assistenten.
    """

    def __init__(self, title: str, text, parent=None):
        from PySide6.QtWidgets import QCheckBox
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        info = text if isinstance(text, dict) else {"text": str(text)}
        lay = QVBoxLayout(self)
        lay.addWidget(label("✦ " + tr("ai.panel.confirm_intro"), "Muted", wrap=True))
        body = label(info.get("text", ""), "CardTitle", wrap=True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(body)
        if info.get("code"):
            code = QPlainTextEdit(info["code"])
            code.setReadOnly(True)
            code.setObjectName("AICode")
            font = code.font()
            font.setFamilies(["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"])
            code.setFont(font)
            if info["code"].startswith(("--- ", "diff ")):
                self._hl = _DiffHighlighter(code.document())
                self._hl.rehighlight()
            lines = min(max(info["code"].count("\n") + 1, 2), 14)
            code.setFixedHeight(int(lines * code.fontMetrics().lineSpacing() + 18))
            lay.addWidget(code)
        if info.get("explanation"):
            lay.addWidget(label(tr("ai.panel.confirm_explanation"), "Muted"))
            lay.addWidget(label(info["explanation"], "", wrap=True))
        self.remember = QCheckBox(tr("ai.panel.remember_session"))
        lay.addWidget(self.remember)
        buttons = QDialogButtonBox()
        buttons.addButton(tr("ai.panel.allow"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(tr("ai.panel.deny"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


ASK_MODE_KEY = "ai_ask_mode"
ASK_MODES = ("primary", "active", "ask")
MAX_CONTEXT_CHARS = 60000


class AskDialog(QDialog):
    """„Assistent fragen …“ aus einem Kontextmenü: Frage eingeben, mitgeschickten Inhalt ansehen,
    im Modus „nachfragen“ zusätzlich den Assistenten wählen."""

    def __init__(self, title: str, context: str, connections: list[Connection], selected: str,
                 choose: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("✦ " + tr("ai.ask.title"))
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ai.ask.about", title=title) if title else tr("ai.ask.intro"), "CardTitle",
                            wrap=True))
        self.question = QPlainTextEdit()
        self.question.setPlaceholderText(tr("ai.ask.placeholder"))
        self.question.setFixedHeight(80)
        lay.addWidget(self.question)
        self.bot = QComboBox()
        for c in connections:
            info = c.info
            self.bot.addItem(c.name + ("" if info and not info.removed else " ⚠"), c.id)
        self.bot.setCurrentIndex(max(self.bot.findData(selected), 0))
        if choose:
            form = QFormLayout()
            form.addRow(tr("ai.ask.assistant"), self.bot)
            lay.addLayout(form)
        lay.addWidget(label(tr("ai.ask.context"), "Muted"))
        preview = QPlainTextEdit(context)
        preview.setReadOnly(True)
        lay.addWidget(preview, 1)
        lay.addWidget(label(tr("ai.ask.notice"), "Muted", wrap=True))
        buttons = QDialogButtonBox()
        buttons.addButton("✦ " + tr("ai.ask.send"), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(tr("common.cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.question.setFocus()

    def text(self) -> str:
        return self.question.toPlainText().strip() or tr("ai.ask.default_question")


class ProjectDialog(QDialog):
    def __init__(self, project: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ai.project.title_edit") if project else tr("ai.project.title_new"))
        self.resize(520, 380)
        self.project = dict(project or {})
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(self.project.get("name", ""))
        form.addRow(tr("ai.project.name"), self.name)
        lay.addLayout(form)
        lay.addWidget(label(tr("ai.project.instructions"), "", wrap=True))
        self.instructions = QPlainTextEdit(self.project.get("instructions", ""))
        self.instructions.setPlaceholderText(tr("ai.project.instructions_placeholder"))
        lay.addWidget(self.instructions, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _ok(self) -> None:
        if not self.name.text().strip():
            self.name.setFocus()
            return
        self.project["name"] = self.name.text().strip()
        self.project["instructions"] = self.instructions.toPlainText().strip()
        self.accept()


class AIPanel(QWidget):
    """Chat mit einem Assistenten. embedded=True: eingebettet in ein Tool (Clank, Mr. Zurkon), ohne eigenen Verlauf und
    Projektauswahl - das Tool steuert Projekt und Chat über set_project()/open_thread()/new_chat()."""

    PAGE_EMPTY, PAGE_CHAT, PAGE_HISTORY = range(3)
    threadSaved = Signal(str, str)      # (Chat-ID, Projekt-ID) nach dem Speichern

    def __init__(self, window, embedded: bool = False, system_extra=None):
        super().__init__()
        self.window = window
        self.embedded = embedded
        self.system_extra = system_extra      # Funktion -> zusätzlicher Systemtext (z. B. Arbeitsbereich)
        self.settings = window.settings
        self.store = ConnectionStore(window.settings, window.vault)
        self.storage = Storage(window.settings, window.vault)
        self.thread: dict | None = None
        self.project: dict | None = None
        self.attachments: list[dict] = []
        self._stop = threading.Event()
        self._running = False
        self._live: MessageWidget | None = None
        self._remembered: dict[str, bool] = {}     # Bestätigungen „für diese Sitzung merken“
        if hasattr(window, "manager"):
            register_app_functions(window)
        self.setObjectName("AIPanel")
        self.setStyleSheet(panel_stylesheet())
        self.setMinimumWidth(300)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.bot = QComboBox()
        self.bot.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.bot.setMinimumContentsLength(10)
        self.bot.setToolTip(tr("ai.panel.bot_tip"))
        self.bot.activated.connect(self._bot_changed)
        top.addWidget(self.bot, 1)
        self.model_btn = QToolButton()
        self.model_btn.setObjectName("AIModel")
        self.model_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.model_btn.clicked.connect(self.choose_model)
        top.addWidget(self.model_btn)
        self._fetching: set[str] = set()
        self.new_btn = self._tool_button("＋", tr("ai.panel.new_chat"), self.new_chat)
        self.hist_btn = self._tool_button("🕘", tr("ai.panel.history"), self.toggle_history)
        self.hist_btn.setCheckable(True)
        self.more_btn = self._tool_button("⋯", tr("ai.panel.more"), None)
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_menu = QMenu(self)
        self.more_menu.aboutToShow.connect(self._fill_more_menu)
        self.more_btn.setMenu(self.more_menu)
        for b in (self.new_btn, self.hist_btn, self.more_btn):
            top.addWidget(b)
        lay.addLayout(top)

        second = QHBoxLayout()
        self.project_combo = QComboBox()
        self.project_combo.setToolTip(tr("ai.panel.project_tip"))
        self.project_combo.activated.connect(self._project_changed)
        second.addWidget(self.project_combo, 1)
        seg = QFrame()
        self.detail_bar = seg
        seg.setObjectName("Segmented")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(2, 2, 2, 2)
        sl.setSpacing(2)
        self.detail_group = QButtonGroup(self)
        current = self.settings.get(DETAIL_KEY, "normal")
        for d in chat.DETAILS:
            b = QToolButton(text=tr(f"ai.detail.{d}"))
            b.setCheckable(True)
            b.setChecked(d == current)
            b.setToolTip(tr("ai.panel.detail_tip"))
            b.setProperty("detail", d)
            self.detail_group.addButton(b)
            sl.addWidget(b)
        self.detail_group.buttonClicked.connect(self._detail_changed)
        second.addWidget(seg)
        lay.addLayout(second)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._empty_page())
        self.stack.addWidget(self._chat_page())
        self.stack.addWidget(self._history_page())
        lay.addWidget(self.stack, 1)

        self.bridge = _Bridge()
        self.bridge.text.connect(self._on_text)
        self.bridge.tool.connect(self._on_tool)
        self.bridge.message.connect(self._on_message)
        self.bridge.finished.connect(self._on_finished)
        self.bridge.failed.connect(self._on_failed)
        self.refresh()

    # ============================================================== Aufbau
    def _tool_button(self, text: str, tip: str, slot) -> QToolButton:
        b = QToolButton(text=text)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if slot:
            b.clicked.connect(slot)
        return b

    def _empty_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addStretch()
        icon = label("✦", "AIEmpty")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 28pt;")
        lay.addWidget(icon)
        title = label(tr("ai.panel.empty_title"), "CardTitleLarge", wrap=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        text = label(tr("ai.panel.empty_text"), "AIEmpty", wrap=True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(text)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(make_button(tr("ai.panel.open_options"), primary=True, on_click=self.open_options))
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return page

    def _chat_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("AIChatArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget()
        host.setObjectName("AIChatHost")
        self.msg_lay = QVBoxLayout(host)
        self.msg_lay.setContentsMargins(2, 2, 6, 2)
        self.msg_lay.setSpacing(8)
        self.msg_lay.addStretch()
        self.scroll.setWidget(host)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._autoscroll)
        lay.addWidget(self.scroll, 1)

        self.welcome = label("", "AIEmpty", wrap=True)
        self.welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_lay.insertWidget(0, self.welcome)

        self.attach_row = QHBoxLayout()
        self.attach_row.setSpacing(4)
        lay.addLayout(self.attach_row)

        box = QFrame()
        box.setObjectName("AIInputBox")
        bl = QHBoxLayout(box)
        bl.setContentsMargins(6, 4, 6, 4)
        self.attach_btn = self._tool_button("📎", tr("ai.panel.attach"), self.attach)
        bl.addWidget(self.attach_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self.input = _Input()
        self.input.submit.connect(self.send)
        bl.addWidget(self.input, 1)
        self.send_btn = QToolButton(text="➤")
        self.send_btn.setObjectName("AISend")
        self.send_btn.setFixedSize(QSize(30, 30))
        self.send_btn.setToolTip(tr("ai.panel.send"))
        self.send_btn.clicked.connect(self._send_or_stop)
        bl.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addWidget(box)
        self.status = label("", "AIMeta", wrap=True)
        lay.addWidget(self.status)
        return page

    def _history_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        self.hist_search = QLineEdit(placeholderText="🔍  " + tr("ai.panel.search_history"))
        self.hist_search.setClearButtonEnabled(True)
        self.hist_search.textChanged.connect(self._fill_history)
        lay.addWidget(self.hist_search)
        self.hist_list = QListWidget()
        self.hist_list.itemClicked.connect(self._history_open)
        self.hist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.hist_list.customContextMenuRequested.connect(self._history_menu)
        lay.addWidget(self.hist_list, 1)
        return page

    # ========================================================== Zustand
    def refresh(self) -> None:
        """Assistenten- und Projektliste neu laden (z. B. nach den Einstellungen)."""
        self.setStyleSheet(panel_stylesheet())
        conns = self.store.chat_connections()
        current = self.bot.currentData() or (self.thread or {}).get("connection") or self.store.primary_id()
        self.bot.clear()
        primary = self.store.primary_id()
        for c in conns:
            info = c.info
            text = ("★ " if c.id == primary else "") + c.name
            self.bot.addItem(text, c.id)
            if info is None or info.removed:
                self.bot.setItemData(self.bot.count() - 1, QBrush(QColor(theme.current["danger"])),
                                     Qt.ItemDataRole.ForegroundRole)
                self.bot.setItemData(self.bot.count() - 1, tr("ai.status.removed"), Qt.ItemDataRole.ToolTipRole)
        idx = self.bot.findData(current)
        self.bot.setCurrentIndex(idx if idx >= 0 else 0)
        self._fill_projects()
        has = bool(conns)
        for w in (self.bot, self.model_btn, self.new_btn, self.hist_btn, self.more_btn, self.project_combo,
                  self.detail_bar):
            w.setVisible(has)
        if self.embedded:
            self.hist_btn.setVisible(False)
            self.project_combo.setVisible(False)
        if not has:
            self.stack.setCurrentIndex(self.PAGE_EMPTY)
        elif self.stack.currentIndex() == self.PAGE_EMPTY:
            self.stack.setCurrentIndex(self.PAGE_CHAT)
        self._update_welcome()
        self._update_attach()
        self._update_model()

    def _fill_projects(self) -> None:
        self.project_combo.clear()
        self.project_combo.addItem(tr("ai.panel.no_project"), "")
        for p in self.storage.list_projects():
            self.project_combo.addItem("📁 " + (p.get("name") or p["id"]), p["id"])
        self.project_combo.addItem("＋ " + tr("ai.panel.new_project"), "__new__")
        pid = (self.project or {}).get("id", "")
        self.project_combo.setCurrentIndex(max(self.project_combo.findData(pid), 0))

    def connection(self) -> Connection | None:
        cid = self.bot.currentData()
        return self.store.get(cid) if cid else None

    def _detail(self) -> str:
        b = self.detail_group.checkedButton()
        return b.property("detail") if b else "normal"

    def _update_welcome(self) -> None:
        conn = self.connection()
        self.welcome.setText(tr("ai.panel.welcome", name=conn.name) if conn else "")
        self.welcome.setVisible(not (self.thread and self.thread.get("messages")))

    def _update_attach(self) -> None:
        conn = self.connection()
        self.attach_btn.setEnabled(bool(conn))

    # =========================================================== Aktionen
    def open_options(self) -> None:
        self.window.open_app_settings(initial_tab="ai")

    def focus_input(self) -> None:
        if self.stack.currentIndex() == self.PAGE_HISTORY:
            self.stack.setCurrentIndex(self.PAGE_CHAT)
            self.hist_btn.setChecked(False)
        self.input.setFocus()

    def new_chat(self) -> None:
        if self._running:
            self.stop()
        self.thread = None
        self.attachments = []
        self._render_attachments()
        self._clear_messages()
        self.hist_btn.setChecked(False)
        if self.stack.currentIndex() != self.PAGE_EMPTY:
            self.stack.setCurrentIndex(self.PAGE_CHAT)
        self._update_welcome()
        self.status.setText("")
        self.input.setFocus()

    def toggle_history(self) -> None:
        if self.stack.currentIndex() == self.PAGE_HISTORY:
            self.stack.setCurrentIndex(self.PAGE_CHAT)
            self.hist_btn.setChecked(False)
        else:
            self._fill_history()
            self.stack.setCurrentIndex(self.PAGE_HISTORY)
            self.hist_btn.setChecked(True)
            self.hist_search.setFocus()

    def _fill_history(self) -> None:
        self.hist_list.clear()
        needle = self.hist_search.text().strip().lower()
        for t in self.storage.list_threads((self.project or {}).get("id", "")):
            title = t.get("title") or tr("ai.chat.untitled")
            if needle and needle not in title.lower():
                continue
            when = time.strftime("%d.%m.%Y %H:%M", time.localtime(t.get("updated") or 0))
            who = t.get("connection_name") or ""
            item = QListWidgetItem(f"{'🔒 ' if t.get('locked') else ''}{title}\n{when}  ·  {who}")
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self.hist_list.addItem(item)
        if not self.hist_list.count():
            item = QListWidgetItem(tr("ai.panel.no_history"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.hist_list.addItem(item)

    def _history_open(self, item: QListWidgetItem) -> None:
        tid = item.data(Qt.ItemDataRole.UserRole)
        if tid:
            self.open_thread(tid, (self.project or {}).get("id", ""))

    def open_thread(self, thread_id: str, project: str = "") -> None:
        thread = self.storage.load_thread(thread_id, project)
        if not thread:
            QMessageBox.warning(self, tr("ai.panel.history"), tr("ai.panel.thread_unreadable"))
            return
        if self._running:
            self.stop()
        self.thread = thread
        idx = self.bot.findData(thread.get("connection"))
        if idx >= 0:
            self.bot.setCurrentIndex(idx)
        for b in self.detail_group.buttons():
            b.setChecked(b.property("detail") == thread.get("detail", "normal"))
        self._clear_messages()
        for m in thread.get("messages", []):
            self._add_message_widget(m)
        self.stack.setCurrentIndex(self.PAGE_CHAT)
        self.hist_btn.setChecked(False)
        self._update_welcome()

    def _history_menu(self, pos) -> None:
        item = self.hist_list.itemAt(pos)
        tid = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not tid:
            return
        menu = QMenu(self)
        menu.addAction(tr("ai.panel.rename"), lambda: self._rename_thread(tid))
        menu.addAction(tr("ai.panel.open_folder"), lambda: self._open_folder(
            self.storage.thread_dir(tid, (self.project or {}).get("id", ""))))
        menu.addSeparator()
        menu.addAction(tr("ai.panel.delete"), lambda: self._delete_thread(tid))
        menu.exec(self.hist_list.mapToGlobal(pos))

    def _rename_thread(self, tid: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        project = (self.project or {}).get("id", "")
        thread = self.storage.load_thread(tid, project)
        if not thread:
            return
        name, ok = QInputDialog.getText(self, tr("ai.panel.rename"), tr("ai.panel.chat_title"), text=thread.get("title", ""))
        if ok and name.strip():
            thread["title"] = name.strip()
            self.storage.save_thread(thread, chat.thread_markdown(thread))
            if self.thread and self.thread["id"] == tid:
                self.thread["title"] = thread["title"]
            self._fill_history()

    def _delete_thread(self, tid: str) -> None:
        if QMessageBox.question(self, tr("ai.panel.delete"), tr("ai.panel.delete_confirm")) \
                != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_thread(tid, (self.project or {}).get("id", ""))
        if self.thread and self.thread["id"] == tid:
            self.new_chat()
            self.stack.setCurrentIndex(self.PAGE_HISTORY)
        self._fill_history()

    def _open_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _fill_more_menu(self) -> None:
        m = self.more_menu
        m.clear()
        m.addAction(tr("ai.panel.new_chat"), self.new_chat)
        if self.project:
            m.addAction(tr("ai.panel.edit_project"), self._edit_project)
            m.addAction(tr("ai.panel.open_project_folder"),
                        lambda: self._open_folder(self.storage.project_dir(self.project["id"])))
        if self.thread and self.thread.get("messages"):
            m.addAction(tr("ai.panel.open_folder"), lambda: self._open_folder(
                self.storage.thread_dir(self.thread["id"], self.thread.get("project", ""))))
        m.addAction(tr("ai.panel.open_data_folder"), lambda: self._open_folder(self.storage.path("chats")))
        m.addSeparator()
        m.addAction(tr("ai.panel.options"), self.open_options)

    # ------------------------------------------------------------ Projekte
    def _project_changed(self, idx: int) -> None:
        pid = self.project_combo.itemData(idx)
        if pid == "__new__":
            dlg = ProjectDialog(None, self)
            if dlg.exec():
                self.storage.save_project(dlg.project)
                self.project = dlg.project
            self._fill_projects()
        else:
            self.project = self.storage.load_project(pid) if pid else None
            if pid and self.project is None:
                QMessageBox.warning(self, tr("ai.panel.project_tip"), tr("ai.panel.thread_unreadable"))
                self._fill_projects()
        if not self.thread or self.thread.get("project", "") != (self.project or {}).get("id", ""):
            self.new_chat()
        if self.stack.currentIndex() == self.PAGE_HISTORY:
            self._fill_history()

    def set_project(self, project: dict | None) -> None:
        """Projekt von außen setzen (eingebettet); ein Chat eines anderen Projekts wird geschlossen."""
        self.project = project
        self._fill_projects()
        if not self.thread or self.thread.get("project", "") != (project or {}).get("id", ""):
            self.new_chat()

    def _edit_project(self) -> None:
        if not self.project:
            return
        dlg = ProjectDialog(self.project, self)
        if dlg.exec():
            self.project = dlg.project
            self.storage.save_project(self.project)
            self._fill_projects()

    # ------------------------------------------------------------ Einstellungen
    def _detail_changed(self, _btn) -> None:
        d = self._detail()
        self.settings.set(DETAIL_KEY, d)
        if self.thread is not None:
            self.thread["detail"] = d

    def _bot_changed(self, _idx: int) -> None:
        conn = self.connection()
        if not conn:
            return
        info = conn.info
        if info is not None and info.removed:
            self.status.setText("⚠ " + tr("ai.error.removed",
                                          note=tr(f"ai.note.{info.status_note}") if info.status_note else ""))
        else:
            self.status.setText("")
        if self.thread and self.thread.get("messages") and self.thread.get("connection") != conn.id:
            msg = {"role": "switch", "content": conn.name, "ts": int(time.time())}
            self.thread["messages"].append(msg)
            self._add_message_widget(msg)
        if self.thread is not None:
            self.thread["connection"] = conn.id
            self.thread["connection_name"] = conn.name
        self._update_welcome()
        self._update_attach()
        self._update_model()

    # ------------------------------------------------------------- Modell
    def _update_model(self, fetch: bool = True) -> None:
        """Modellknopf beschriften; veraltete Modellliste im Hintergrund neu abfragen."""
        conn = self.connection()
        if conn is None:
            return
        no_models = conn.api == "graph_copilot"
        self.model_btn.setVisible(not no_models)
        if no_models:
            return
        available = models.cached_models(self.settings, conn.id)
        missing = available is not None and conn.model not in available
        text = conn.model or tr("ai.model.none")
        short = text if len(text) <= 22 else text[:21] + "…"
        self.model_btn.setText(("🔞 " if conn.nsfw_allowed else "") + ("⚠ " if missing else "") + short + " ▾")
        choice = next((c for c in models.choices(conn, available) if c.id == conn.model), None)
        tip = [tr("ai.model.button_tip")]
        if choice:
            from .ai_models import tooltip
            tip.append(tooltip(choice))
        if conn.nsfw_allowed:
            tip.append("🔞 " + tr("ai.nsfw.active"))
        self.model_btn.setToolTip("\n\n".join(tip))
        self.model_btn.setStyleSheet(f"color: {theme.current['danger']};" if missing else "")
        if fetch and conn.id not in self._fetching and models.is_stale(self.settings, conn.id):
            self._fetch_models(conn)

    def _fetch_models(self, conn: Connection) -> None:
        from .ai_models import fetch
        self._fetching.add(conn.id)

        def done(found):
            self._fetching.discard(conn.id)
            current = self.store.get(conn.id)
            if current is None:
                return
            best = models.best(current, found or None)
            ours = not current.model or current.model in (current.info.models if current.info else [])
            if best and best != current.model and ours:
                # Vorgabe aus dem Katalog gibt es nicht (mehr): bestes verfügbares nehmen und Bescheid sagen.
                # Selbst eingetragene Namen (z. B. Azure-Bereitstellungen) bleiben, der Knopf zeigt nur ⚠.
                old = current.model
                current.model = best
                self.store.save(current)
                if self.connection() and self.connection().id == current.id:
                    self.status.setText(tr("ai.model.switched", old=old or "–", new=best))
            if self.connection() and self.connection().id == conn.id:
                self._update_model(fetch=False)

        def failed(_err):
            self._fetching.discard(conn.id)
            if self.connection() and self.connection().id == conn.id:
                self._update_model(fetch=False)

        run_async(lambda: fetch(self.store, conn), done, failed)

    def choose_model(self) -> None:
        conn = self.connection()
        if conn is None:
            return
        from .ai_models import ModelPicker
        dlg = ModelPicker(self.store, conn, conn.model, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.selected:
            self._update_model(fetch=False)
            return
        current = self.store.get(conn.id) or conn
        if dlg.selected != current.model:
            current.model = dlg.selected
            self.store.save(current)
            self.status.setText(tr("ai.model.changed", model=dlg.selected))
        self._update_model(fetch=False)

    # ------------------------------------------------------------ Anhänge
    def attach(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("ai.panel.attach"), "",
                                                tr("ai.panel.attach_filter") + " (*.*)")
        for f in files:
            self.add_attachment(Path(f))

    def add_attachment(self, path: Path) -> None:
        mime = mimetypes.guess_type(path.name)[0] or ""
        try:
            if mime.startswith("image/"):
                data = path.read_bytes()
                if len(data) > MAX_IMAGE_BYTES:
                    raise ValueError(tr("ai.panel.too_large"))
                conn = self.connection()
                if conn and conn.info and not conn.has("vision"):
                    self.status.setText(tr("ai.panel.no_vision", name=conn.name))
                self.attachments.append({"kind": "image", "name": path.name, "mime": mime,
                                         "data": base64.b64encode(data).decode()})
            elif path.suffix.lower() in TEXT_SUFFIXES or mime.startswith("text/"):
                text = path.read_text(encoding="utf-8", errors="replace")[:100_000]
                self.attachments.append({"kind": "text", "name": path.name, "text": text})
            else:
                raise ValueError(tr("ai.panel.unsupported_file"))
        except (OSError, ValueError) as err:
            QMessageBox.warning(self, tr("ai.panel.attach"), f"{path.name}: {err}")
            return
        self._render_attachments()

    def add_text_attachment(self, name: str, text: str) -> None:
        self.attachments.append({"kind": "text", "name": name, "text": text})
        self._render_attachments()

    def _render_attachments(self) -> None:
        while self.attach_row.count():
            w = self.attach_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, a in enumerate(self.attachments):
            b = QToolButton(text=("🖼 " if a["kind"] == "image" else "📄 ") + a["name"] + "  ✕")
            b.setObjectName("AIChip")
            b.setToolTip(tr("ai.panel.remove_attachment"))
            b.clicked.connect(lambda _=False, idx=i: self._remove_attachment(idx))
            self.attach_row.addWidget(b)
        if self.attachments:
            self.attach_row.addStretch()

    def _remove_attachment(self, idx: int) -> None:
        if 0 <= idx < len(self.attachments):
            del self.attachments[idx]
        self._render_attachments()

    # ============================================================ Chatten
    def ask(self, text: str, attachments: list[dict] | None = None, connection_id: str = "",
            new: bool = True) -> None:
        """Von außen (Kontextmenü …): neuen Chat mit Text und Anhängen beginnen und abschicken."""
        if connection_id:
            idx = self.bot.findData(connection_id)
            if idx >= 0:
                self.bot.setCurrentIndex(idx)
                self._bot_changed(idx)
        if new:
            self.new_chat()
        self.attachments = list(attachments or [])
        self._render_attachments()
        self.input.setPlainText(text)
        self.send()

    def ask_about(self, context: str, title: str = "", source: str = "") -> bool:
        """Kontextmenü „Assistent fragen …“. Wählt den Assistenten nach Einstellung ai_ask_mode."""
        self.refresh()
        conns = self.store.chat_connections()
        if not conns:
            return False
        mode = self.settings.get(ASK_MODE_KEY, "primary")
        if mode == "active" and self.connection() is not None:
            selected = self.connection().id
        else:
            selected = self.store.primary_id() or conns[0].id
        if len(context) > MAX_CONTEXT_CHARS:
            context = context[:MAX_CONTEXT_CHARS] + "\n… " + tr("ai.ask.truncated")
        dlg = AskDialog(title, context, conns, selected, mode == "ask", self.window)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return True
        head = tr("ai.ask.context_head", title=title) if title else tr("ai.ask.context_head_plain")
        text = f"{dlg.text()}\n\n--- {head} ---\n{context}"
        self.ask(text, connection_id=dlg.bot.currentData() or "")
        return True

    def _send_or_stop(self) -> None:
        if self._running:
            self.stop()
        else:
            self.send()

    def send(self) -> None:
        if self._running:
            return
        text = self.input.toPlainText().strip()
        if not text and not self.attachments:
            return
        conn = self.connection()
        if conn is None:
            self.stack.setCurrentIndex(self.PAGE_EMPTY)
            return
        if self.thread is None:
            self.thread = chat.new_thread(conn, self._detail(), (self.project or {}).get("id", ""))
        texts = [f"--- {a['name']} ---\n{a['text']}" for a in self.attachments if a["kind"] == "text"]
        content = "\n\n".join([text] + texts) if texts else text
        msg = {"role": "user", "content": content, "ts": int(time.time())}
        images = [{"mime": a["mime"], "data": a["data"], "name": a["name"]}
                  for a in self.attachments if a["kind"] == "image"]
        if images:
            msg["images"] = images
        if not self.thread.get("title"):
            self.thread["title"] = chat.make_title(text or self.attachments[0]["name"])
        self.thread["messages"].append(msg)
        self.thread["connection"] = conn.id
        self.thread["connection_name"] = conn.name
        self.thread["detail"] = self._detail()
        self._add_message_widget(msg)
        self.input.clear()
        self.attachments = []
        self._render_attachments()
        self._save_thread()
        self._start(conn)

    def _start(self, conn: Connection) -> None:
        self._running = True
        self._stop = threading.Event()
        self._set_running(True)
        self.status.setText(tr("ai.panel.thinking", name=conn.name))
        thread = self.thread
        # Der Hintergrund arbeitet auf einer Kopie; übernommen wird sie erst am Ende (Stopp verwirft sie)
        work = dict(thread, messages=list(thread["messages"]), usage=dict(thread.get("usage") or {}),
                    state=dict(thread.get("state") or {}))
        self._work = (thread, work)
        extra = ""
        if self.system_extra is not None:
            try:
                extra = self.system_extra() or ""
            except Exception:  # noqa: BLE001 - Zusatztext ist optional
                extra = ""
        system = chat.system_prompt(thread.get("detail", "normal"), self.project, extra)
        b = self.bridge
        settings = self.settings
        pstate = work["state"].setdefault("pseudo", {})
        kinds = access.pseudo_kinds(settings)
        chat_pseudo = Pseudonymizer(pstate, kinds, enabled=access.pseudo_enabled(settings, "app"))

        def encode_result(source: str, value) -> str:
            p = Pseudonymizer(pstate, kinds, enabled=access.pseudo_enabled(settings, source))
            return functions.format_result(p.encode_value(value))

        self._decoder = chat_pseudo.decode
        hooks = chat.RunHooks(
            on_text=b.text.emit, on_tool=b.tool.emit, on_tool_done=b.tool_done.emit,
            on_message=lambda m: b.message.emit(dict(m)),
            confirm=self._confirm_in_gui, level_for=lambda source: access.level(settings, source, conn.id),
            encode=chat_pseudo.encode, decode=chat_pseudo.decode, encode_result=encode_result,
            call_context=functions.CallContext(window=self.window, connection=conn,
                                               in_gui=lambda fn: self._in_gui(fn), stop=self._stop))
        stop = self._stop

        def task():
            try:
                chat.run(self.store, conn, work, system, hooks, stop)
            except Cancelled:
                pass
            except Exception as err:  # noqa: BLE001
                b.failed.emit(err)
                return
            b.finished.emit()

        run_async(task)

    def _in_gui(self, fn):
        result = []
        call_in_gui(lambda: result.append(fn()))
        return result[0] if result else None

    def _confirm_in_gui(self, fn: functions.Function, args: dict) -> bool:
        try:
            text = fn.summary(args) if fn.summary else f"{fn.name}\n{args}"
        except Exception:  # noqa: BLE001 - Zusammenfassung ist nur Anzeige
            text = f"{fn.name}\n{args}"
        # Befehle merken sich die Antwort je Befehlstext, alles andere je Funktion
        key = fn.name + ("\0" + text["code"] if isinstance(text, dict) and text.get("code") else "")
        if key in self._remembered:
            return self._remembered[key]

        def ask():
            dlg = ConfirmDialog(tr("ai.panel.confirm_title"), text, self)
            ok = dlg.exec() == QDialog.DialogCode.Accepted
            if dlg.remember.isChecked():
                self._remembered[key] = ok
            return ok
        return bool(self._in_gui(ask))

    def stop(self) -> None:
        self._stop.set()
        self._work = (None, None)
        self._running = False
        self._set_running(False)
        self.status.setText(tr("ai.panel.stopped"))
        if self._live is not None:
            self._live.end_round({**self._live.msg, "tool_calls": []})
            if self._live._buffer and self.thread is not None:
                conn = self.connection()
                self.thread["messages"].append({"role": "assistant", "content": self._live._buffer,
                                                "ts": int(time.time()), "stopped": True,
                                                "connection": conn.id if conn else "",
                                                "connection_name": conn.name if conn else ""})
            self._live = None
        self._save_thread()

    def _set_running(self, running: bool) -> None:
        self.send_btn.setText("■" if running else "➤")
        self.send_btn.setToolTip(tr("ai.panel.stop") if running else tr("ai.panel.send"))
        self.send_btn.setProperty("stop", running)
        self.send_btn.style().unpolish(self.send_btn)
        self.send_btn.style().polish(self.send_btn)

    # ---------------------------------------------------------- Signale
    def _ensure_live(self) -> MessageWidget:
        if self._live is None:
            conn = self.connection()
            self._live = self._add_message_widget({"role": "assistant", "content": "", "ts": int(time.time()),
                                                   "connection_name": conn.name if conn else "",
                                                   "model": conn.model if conn else ""})
            self._live.decoder = self._decoder
        return self._live

    def _on_text(self, delta: str) -> None:
        if not self._running:
            return
        self._ensure_live().append(delta)
        self.status.setText("")

    def _on_tool(self, call: dict) -> None:
        if not self._running:
            return
        self._ensure_live()
        self.status.setText(tr("ai.panel.running_function", name=call.get("name", "")))

    def _on_message(self, msg: dict) -> None:
        if not self._running:
            return
        self._ensure_live().end_round(msg)
        if msg.get("tool_calls"):
            self.status.setText(tr("ai.panel.running_function", name=msg["tool_calls"][0].get("name", "")))
        else:
            self._live = None

    def _merge_work(self) -> None:
        thread, work = getattr(self, "_work", (None, None))
        self._work = (None, None)
        if thread is not None and thread is self.thread:
            for key in ("messages", "usage", "state"):
                thread[key] = work[key]

    def _on_finished(self) -> None:
        if not self._running:
            return
        self._merge_work()
        self._running = False
        self._set_running(False)
        self.status.setText("")
        self._live = None
        self._save_thread()

    def _on_failed(self, err: Exception) -> None:
        if not self._running:
            return
        self._merge_work()
        self._running = False
        self._set_running(False)
        self.status.setText("")
        if self._live is not None and not self._live._buffer:
            self._live.deleteLater()
        self._live = None
        msg = {"role": "error", "content": chat.error_text(err), "ts": int(time.time())}
        if isinstance(err, AIError) and err.kind in ("auth", "removed"):
            msg["options_link"] = True
        conn = self.connection()
        if conn is not None and models.is_model_error(err):
            models.forget(self.settings, conn.id)      # Liste neu abfragen, Knopf zeigt dann ⚠
            self._update_model()
        if self.thread is not None:
            self.thread["messages"].append(msg)
        self._add_message_widget(msg)
        self._save_thread()

    # ---------------------------------------------------------- Anzeige
    def _clear_messages(self) -> None:
        self._live = None
        self._last_widget = None
        while self.msg_lay.count() > 2:   # Begrüßung + Stretch bleiben
            w = self.msg_lay.takeAt(1).widget()
            if w:
                w.deleteLater()

    def _add_message_widget(self, msg: dict) -> MessageWidget | None:
        role = msg["role"]
        if role == "tool":
            return None
        last = getattr(self, "_last_widget", None)
        if role == "assistant" and last is not None and last.msg.get("tool_calls"):
            last.add_round(msg)   # Folge-Runde nach Funktionsaufrufen in derselben Blase
            return last
        if role == "switch":
            w = label(tr("ai.panel.switched", name=msg.get("content", "")), "AIDivider")
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.msg_lay.insertWidget(self.msg_lay.count() - 1, w)
            self._last_widget = None
            return None
        widget = MessageWidget(msg, self)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        if role == "user":
            rl.addStretch(1)
            rl.addWidget(widget, 6)
        else:
            rl.addWidget(widget, 1)
        self.msg_lay.insertWidget(self.msg_lay.count() - 1, row)
        self._last_widget = widget
        self._update_welcome()
        self._stick = True
        return widget

    def _autoscroll(self, _min: int, maximum: int) -> None:
        bar = self.scroll.verticalScrollBar()
        if getattr(self, "_stick", True) or bar.value() >= bar.maximum() - 80:
            bar.setValue(maximum)
        self._stick = False

    def _save_thread(self) -> None:
        if self.thread and self.thread.get("messages"):
            try:
                self.storage.save_thread(self.thread, chat.thread_markdown(self.thread))
            except OSError as err:
                self.status.setText("⚠ " + tr("ai.panel.save_failed", error=str(err)))
                return
            self.threadSaved.emit(self.thread["id"], self.thread.get("project", ""))
