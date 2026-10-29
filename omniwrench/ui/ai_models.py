"""Modellauswahl für Chatleiste und Verbindungsdialog.

Zeigt die Modelle einer Verbindung mit Verfügbarkeit (Liste vom Anbieter, ai.models) und einer kurzen
Erklärung je Modell. Ein Name, den der Anbieter nicht meldet, lässt sich trotzdem eintippen.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)

from omniwrench.ai import adapters, models
from omniwrench.ai.connections import Connection, ConnectionStore
from omniwrench.ai.knowledge import WIKI_URL
from omniwrench.core.i18n import tr

from . import theme
from .widgets import label, make_button
from .workers import run_async

HELP_URL = f"{WIKI_URL}/KI-Anbieter#modelle-auswählen"


def tag_text(tags: list[str]) -> str:
    return " · ".join(tr(f"ai.model.tag.{t}") for t in tags)


def tooltip(choice: models.ModelChoice) -> str:
    lines = [choice.id]
    if choice.recommended:
        lines.append("★ " + tr("ai.model.recommended"))
    lines += [f"• {tr(f'ai.model.tag.{t}')}: {tr(f'ai.model.tip.{t}')}" for t in choice.tags]
    if choice.status == "missing":
        lines.append("⚠ " + tr("ai.model.missing"))
    elif choice.status == "unknown":
        lines.append(tr("ai.model.unknown"))
    return "\n".join(lines)


def fetch(store: ConnectionStore, conn: Connection, interactive: bool = False) -> list[str]:
    """Modelle beim Anbieter abfragen und merken (läuft im Hintergrund)."""
    try:
        found = adapters.for_connection(store, conn).list_models(interactive=interactive)
    except Exception as err:  # noqa: BLE001 - Anbieter ohne /models oder offline: Auswahl bleibt nutzbar
        models.store(store.settings, conn.id, None, error=str(err))
        raise
    models.store(store.settings, conn.id, found)
    return found


class ModelPicker(QDialog):
    """Modell wählen: Suche, Verfügbarkeit, Erklärung. Ergebnis in .selected."""

    def __init__(self, store: ConnectionStore, conn: Connection, current: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.conn = conn
        self.selected = current
        self.setWindowTitle(tr("ai.model.title", name=conn.name))
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ai.model.intro"), "Muted", wrap=True))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("ai.model.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._fill)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        self.list.currentItemChanged.connect(self._show)
        lay.addWidget(self.list, 1)
        self.info = label("", "Muted", wrap=True)
        self.info.setMinimumHeight(54)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.info)
        row = QHBoxLayout()
        self.others = QCheckBox(tr("ai.model.show_other"))
        self.others.toggled.connect(self._fill)
        row.addWidget(self.others)
        row.addStretch()
        self.status = label("", "Muted")
        row.addWidget(self.status)
        self.reload_btn = make_button("↻ " + tr("ai.model.reload"), on_click=self.reload)
        row.addWidget(self.reload_btn)
        row.addWidget(make_button("? " + tr("ai.model.help"),
                                  on_click=lambda: QDesktopServices.openUrl(QUrl(HELP_URL))))
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._fill()
        if models.is_stale(store.settings, conn.id):
            self.reload()

    def _choices(self) -> list[models.ModelChoice]:
        return models.choices(self.conn, models.cached_models(self.store.settings, self.conn.id))

    def _fill(self, *_):
        text = self.search.text().strip()
        needle = text.lower()
        danger, muted = QColor(theme.current["danger"]), QColor(theme.current["muted"])
        self.list.clear()
        choices = self._choices()
        if text and not any(c.id == text for c in choices):
            item = QListWidgetItem("✎ " + tr("ai.model.use_typed", model=text))
            item.setData(Qt.ItemDataRole.UserRole, text)
            self.list.addItem(item)
        current_row = -1
        for c in choices:
            if c.other and not self.others.isChecked():
                continue
            if needle and needle not in c.id.lower() and needle not in tag_text(c.tags).lower():
                continue
            mark = "★ " if c.recommended else ""
            sub = tag_text(c.tags)
            if c.status == "missing":
                sub = "⚠ " + tr("ai.model.missing") + (f" · {sub}" if sub else "")
            elif c.status == "unknown" and not sub:
                sub = tr("ai.model.unknown")
            item = QListWidgetItem(f"{mark}{c.id}" + (f"\n{sub}" if sub else ""))
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            item.setToolTip(tooltip(c))
            if c.status == "missing":
                item.setForeground(danger)
            elif c.other:
                item.setForeground(muted)
            self.list.addItem(item)
            if c.id == self.selected:
                current_row = self.list.count() - 1
        self.list.setCurrentRow(current_row if current_row >= 0 else 0)
        entry = models.cached(self.store.settings, self.conn.id)
        if entry and entry.get("models"):
            self.status.setText(tr("ai.model.count", count=len(entry["models"])))
        elif entry and entry.get("error"):
            self.status.setText("⚠ " + tr("ai.model.no_list"))
            self.status.setToolTip(entry["error"])
        else:
            self.status.setText("")

    def _show(self, item, _prev=None):
        if item is None:
            self.info.setText("")
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        choice = next((c for c in self._choices() if c.id == mid), None)
        self.info.setText(tooltip(choice) if choice else tr("ai.model.typed_hint"))

    def reload(self) -> None:
        self.reload_btn.setEnabled(False)
        self.status.setText(tr("ai.edit.loading_models"))

        def done(_found):
            self.reload_btn.setEnabled(True)
            self._fill()

        def failed(err: str):
            self.reload_btn.setEnabled(True)
            self._fill()
            self.status.setText("⚠ " + tr("ai.model.no_list"))
            self.status.setToolTip(err)

        run_async(lambda: fetch(self.store, self.conn, interactive=True), done, failed)

    def accept(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.selected = item.data(Qt.ItemDataRole.UserRole)
        super().accept()
