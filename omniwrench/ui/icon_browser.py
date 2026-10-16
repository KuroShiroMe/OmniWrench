"""Übersicht der eingebauten Symbol-Bibliothek (Lucide) - für Tool-Entwickler.

Klick auf ein Symbol kopiert dessen Namen, der dann in tool.json unter "icon" eingetragen wird.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from omniwrench.core import icons
from omniwrench.core.i18n import tr

from .scaling import fit_to_screen
from .widgets import label, library_icon

BATCH = 300  # Symbole werden stückweise geladen, damit der Dialog sofort erscheint


class IconBrowserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("icons.title"))
        fit_to_screen(self, 820, 600)
        lay = QVBoxLayout(self)
        version = (icons.LIBRARY_DIR / "VERSION").read_text().strip() if (icons.LIBRARY_DIR / "VERSION").exists() else "?"
        lay.addWidget(label(tr("icons.hint", count=len(icons.library_names()), version=version), "Muted", wrap=True))
        self.search = QLineEdit(placeholderText="🔍  " + tr("icons.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setIconSize(QSize(32, 32))
        self.list.setGridSize(QSize(110, 78))
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setUniformItemSizes(True)
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._copy)
        lay.addWidget(self.list, 1)
        self.status = label("", "Muted")
        lay.addWidget(self.status)
        self._names = list(icons.library_names())
        self._pos = 0
        QTimer.singleShot(0, self._load_batch)
        self.search.setFocus()

    def _load_batch(self) -> None:
        for name in self._names[self._pos:self._pos + BATCH]:
            item = QListWidgetItem(library_icon(name, 32), name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.list.addItem(item)
        self._pos += BATCH
        self._filter()
        if self._pos < len(self._names):
            QTimer.singleShot(0, self._load_batch)

    def _filter(self) -> None:
        q = self.search.text().strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(q) and q not in item.text())

    def _copy(self, item: QListWidgetItem) -> None:
        QApplication.clipboard().setText(item.text())
        self.status.setText(tr("icons.copied", name=item.text()))
