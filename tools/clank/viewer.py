"""Dateiansicht des KI-Studios: Text mit einfacher Hervorhebung (Schlüsselwörter, Texte, Kommentare, Diff)."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget

from omniwrench.ui import theme

KEYWORDS = {
    "py": "and as assert async await break class continue def del elif else except False finally for from global if "
          "import in is lambda None nonlocal not or pass raise return True try while with yield",
    "ps1": "begin break catch class continue data do dynamicparam else elseif end exit filter finally for foreach "
           "function if in param process return switch throw trap try until using var while",
    "js": "async await break case catch class const continue default delete do else export extends false finally for "
          "function if import in instanceof let new null return super switch this throw true try typeof var void "
          "while with yield",
    "sh": "case do done elif else esac fi for function if in local return then until while export",
    "cs": "abstract async await base bool break case catch class const continue default do else enum false finally "
          "for foreach if int interface internal namespace new null override private protected public readonly "
          "return static string switch this throw true try using var void while",
}
ALIASES = {"psm1": "ps1", "psd1": "ps1", "ts": "js", "tsx": "js", "jsx": "js", "mjs": "js", "bash": "sh", "zsh": "sh"}
HASH_COMMENT = {"py", "ps1", "sh", "yaml", "yml", "toml", "ini", "conf", "cfg", "rb", "r"}


def mono_font() -> QFont:
    f = QFont()
    f.setFamilies(["Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono", "monospace"])
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


class Highlighter(QSyntaxHighlighter):
    def __init__(self, doc, ext: str):
        super().__init__(doc)
        self.set_language(ext)

    def set_language(self, ext: str) -> None:
        ext = ALIASES.get(ext, ext)
        self.ext = ext
        c = theme.current

        def fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            f.setFontItalic(italic)
            return f
        self.rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        if ext == "diff":
            self.rules = [(re.compile(r"^\+.*$"), fmt(c.get("success", "#10b981"))),
                          (re.compile(r"^-.*$"), fmt(c.get("danger", "#ef4444"))),
                          (re.compile(r"^@@.*$"), fmt(c.get("accent", "#3b82f6"), bold=True)),
                          (re.compile(r"^(diff|index|\+\+\+|---|commit|Author|Date).*$"), fmt(c["muted"], bold=True))]
        else:
            words = KEYWORDS.get(ext, "")
            if words:
                flags = re.IGNORECASE if ext == "ps1" else 0
                self.rules.append((re.compile(r"\b(" + "|".join(words.split()) + r")\b", flags),
                                   fmt(c.get("accent", "#3b82f6"), bold=True)))
            if ext == "ps1":
                self.rules.append((re.compile(r"\$[\w:]+"), fmt("#c084fc")))
            self.rules.append((re.compile(r"\b\d+(\.\d+)?\b"), fmt("#f59e0b")))
            self.rules.append((re.compile(r"\"(\\.|[^\"\\])*\"|'(\\.|[^'\\])*'"), fmt("#10b981")))
            if ext in ("json",):
                self.rules.append((re.compile(r"\"(\\.|[^\"\\])*\"(?=\s*:)"), fmt("#60a5fa")))
            comment = r"#.*$" if ext in HASH_COMMENT else r"//.*$" if ext in ("js", "cs", "java", "c", "cpp", "go",
                                                                                 "rs", "kt", "swift") else ""
            if comment:
                self.rules.append((re.compile(comment), fmt(c["muted"], italic=True)))
            if ext in ("md",):
                self.rules.append((re.compile(r"^#+ .*$"), fmt(c.get("accent", "#3b82f6"), bold=True)))
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for rx, f in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)


class FileViewer(QWidget):
    """Kopfzeile (Pfad + Aktionen) und schreibgeschützter Text."""
    attach = Signal()
    closed = Signal()
    show_diff = Signal()
    reveal = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.path = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        head = QHBoxLayout()
        self.title = QLabel("")
        self.title.setObjectName("CardTitle")
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        head.addWidget(self.title, 1)
        self.buttons = {}
        for key, sig, text in (("attach", self.attach, "📎"), ("diff", self.show_diff, "±"),
                               ("reveal", self.reveal, "📂"), ("close", self.closed, "✕")):
            b = QToolButton(text=text)
            b.setToolTip(tr(f"viewer.{key}"))
            b.clicked.connect(sig.emit)
            head.addWidget(b)
            self.buttons[key] = b
        lay.addLayout(head)
        self.info = QLabel("")
        self.info.setObjectName("Muted")
        lay.addWidget(self.info)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setFont(mono_font())
        lay.addWidget(self.text, 1)
        self.hl = Highlighter(self.text.document(), "")

    def show_text(self, path: str, text: str, info: str = "", ext: str = "", git: bool = False) -> None:
        self.path = path
        self.title.setText(path.rsplit("/", 1)[-1] if ext != "diff" else self.tr("viewer.diff_title", path=path))
        self.title.setToolTip(path)
        self.info.setText(info)
        self.info.setVisible(bool(info))
        self.hl.set_language(ext or path.rsplit(".", 1)[-1].lower() if "." in path else ext)
        self.text.setPlainText(text)
        self.buttons["diff"].setVisible(git and ext != "diff")
        self.buttons["attach"].setVisible(bool(text))
