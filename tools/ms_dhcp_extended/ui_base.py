"""Gemeinsame Oberflächenbausteine von MS DHCP Extended Management: Tabellen, Schaltflächenleisten, Befundliste, Markierungen
und Dialoge. Farben kommen aus dem App-Theme, damit hell und dunkel funktionieren."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QToolButton, QToolTip, QVBoxLayout, QWidget,
)

from omniwrench.ui import theme
import html

from omniwrench.ui.widgets import FlowLayout, library_icon, make_button

from . import checks as ck
from . import ipcalc as ip

SORT_ROLE = Qt.ItemDataRole.UserRole + 1
MONO = QFont("Consolas", 10)


def level_color(level: str | None) -> str:
    c = theme.current
    return {ck.ERROR: c["danger"], ck.WARN: c["warning"], ck.BP: "#6d6af0", ck.INFO: c["muted"]}.get(level or "", c["success"])


def tint(color: str, alpha: int = 46) -> QColor:
    q = QColor(color)
    q.setAlpha(alpha)
    return q


_icon_cache: dict[tuple[str, str], QIcon] = {}


def level_icon(level: str | None, size: int = 12) -> QIcon:
    color = level_color(level)
    key = (color, str(size))
    if key not in _icon_cache:
        pm = QPixmap(size * 2, size * 2)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, size * 2 - 4, size * 2 - 4)
        p.end()
        pm.setDevicePixelRatio(2)
        _icon_cache[key] = QIcon(pm)
    return _icon_cache[key]


def level_name(tr, level: str, plural: bool = False) -> str:
    return tr(f"level.{level}{'_pl' if plural else ''}")


# --- Meldungen ---------------------------------------------------------------------------------------

def _box(parent, icon, title, text, buttons, default=None) -> QMessageBox.StandardButton:
    box = QMessageBox(icon, title, text, buttons, parent)
    if default is not None:
        box.setDefaultButton(default)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return box.exec()


def info(parent, title: str, text: str) -> None:
    _box(parent, QMessageBox.Icon.Information, title, text, QMessageBox.StandardButton.Ok)


def warn(parent, title: str, text: str) -> None:
    _box(parent, QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok)


def error(parent, title: str, text: str) -> None:
    _box(parent, QMessageBox.Icon.Critical, title, text, QMessageBox.StandardButton.Ok)


def confirm(parent, title: str, text: str) -> bool:
    b = QMessageBox.StandardButton
    return _box(parent, QMessageBox.Icon.Question, title, text, b.Yes | b.No, b.No) == b.Yes


def choose(parent, title: str, text: str, buttons: list[tuple[str, str]], default: str | None = None,
           icon=QMessageBox.Icon.Warning) -> str:
    """Meldung mit eigenen Knöpfen [(Schlüssel, Beschriftung)]; liefert den Schlüssel (Schließen = letzter Knopf)."""
    box = QMessageBox(icon, title, text, QMessageBox.StandardButton.NoButton, parent)
    box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    btns = {}
    for i, (key, label) in enumerate(buttons):
        role = QMessageBox.ButtonRole.RejectRole if i == len(buttons) - 1 else QMessageBox.ButtonRole.AcceptRole
        btns[box.addButton(label, role)] = key
        if key == default:
            box.setDefaultButton(list(btns)[-1])
    box.setEscapeButton(list(btns)[-1])
    box.exec()
    return btns.get(box.clickedButton(), buttons[-1][0])


def ask3(parent, title: str, text: str) -> str:
    b = QMessageBox.StandardButton
    r = _box(parent, QMessageBox.Icon.Question, title, text, b.Yes | b.No | b.Cancel, b.Yes)
    return "yes" if r == b.Yes else "no" if r == b.No else "cancel"


def text_dialog(parent, title: str, text: str, close_label: str) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.resize(980, 640)
    lay = QVBoxLayout(dlg)
    ed = QPlainTextEdit(text)
    ed.setReadOnly(True)
    ed.setFont(MONO)
    ed.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    lay.addWidget(ed)
    bb = QDialogButtonBox()
    bb.addButton(close_label, QDialogButtonBox.ButtonRole.RejectRole)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    dlg.exec()


def short_list(items, n: int = 15) -> str:
    lst = [str(x) for x in items]
    out = "\n".join("• " + x for x in lst[:n])
    if len(lst) > n:
        out += f"\n• … (+{len(lst) - n})"
    return out


# --- Formular-Dialog (wie ein universeller Eingabedialog) ----------------------------------------------

class FormDialog(QDialog):
    """fields: [{"key","label","type"(text|password|combo|multiline|number|check|checklist),"value","items",
    "editable","readonly","min","max"}]. validate(values) -> Fehlertext oder None."""

    def __init__(self, parent, title: str, fields: list[dict], tr, hint: str = "", validate=None, width: int = 560,
                 ok_label: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self._validate = validate
        self._fields = fields
        self.widgets: dict[str, QWidget] = {}
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for f in fields:
            t = f.get("type", "text")
            v = f.get("value")
            if t == "combo":
                w = QComboBox()
                w.setEditable(bool(f.get("editable")))
                for it in f.get("items") or []:
                    if isinstance(it, tuple):
                        w.addItem(it[1], it[0])
                    else:
                        w.addItem(str(it), it)
                if v is not None:
                    idx = w.findData(v)
                    if idx < 0:
                        idx = w.findText(str(v))
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                    elif w.isEditable():
                        w.setEditText(str(v))
            elif t == "multiline":
                w = QPlainTextEdit(str(v or ""))
                w.setFont(MONO)
                w.setMinimumHeight(110)
            elif t == "number":
                w = QSpinBox()
                w.setRange(int(f.get("min", 0)), int(f.get("max", 999999)))
                w.setValue(int(v or 0))
            elif t == "check":
                w = QCheckBox(f["label"])
                w.setChecked(bool(v))
            elif t == "checklist":
                w = QListWidget()
                w.setMinimumHeight(170)
                for it in f.get("items") or []:
                    key, text = it if isinstance(it, tuple) else (it, it)
                    li = QListWidgetItem(text)
                    li.setData(Qt.ItemDataRole.UserRole, key)
                    li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    li.setCheckState(Qt.CheckState.Checked if key in (v or []) else Qt.CheckState.Unchecked)
                    w.addItem(li)
            else:
                w = QLineEdit(str(v or ""))
                if t == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)
            if f.get("readonly"):
                w.setEnabled(False)
            self.widgets[f["key"]] = w
            if t == "check":
                form.addRow("", w)
            else:
                form.addRow(f["label"], w)
        lay.addLayout(form)
        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet(f"color:{theme.current['danger']};")
        self.err.hide()
        lay.addWidget(self.err)
        bb = QDialogButtonBox()
        okb = bb.addButton(ok_label or tr("ui.ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        okb.setDefault(True)
        bb.addButton(tr("ui.cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        row = QHBoxLayout()
        if hint:
            row.addWidget(help_icon(hint))     # Hinweis als Fragezeichen neben den Schaltflächen
        row.addWidget(bb, 1)
        lay.addLayout(row)
        self.result_values: dict | None = None

    def values(self) -> dict:
        out = {}
        for f in self._fields:
            w = self.widgets[f["key"]]
            t = f.get("type", "text")
            if t == "combo":
                d = w.currentData()
                out[f["key"]] = w.currentText().strip() if w.isEditable() and w.currentText() != w.itemText(w.currentIndex()) else (
                    d if d is not None else w.currentText().strip())
            elif t == "multiline":
                out[f["key"]] = w.toPlainText()
            elif t == "number":
                out[f["key"]] = w.value()
            elif t == "check":
                out[f["key"]] = w.isChecked()
            elif t == "checklist":
                out[f["key"]] = [w.item(i).data(Qt.ItemDataRole.UserRole) for i in range(w.count())
                                 if w.item(i).checkState() == Qt.CheckState.Checked]
            else:
                out[f["key"]] = w.text().strip() if t != "password" else w.text()
        return out

    def _accept(self) -> None:
        v = self.values()
        if self._validate:
            msg = self._validate(v)
            if msg:
                self.err.setText(msg)
                self.err.show()
                return
        self.result_values = v
        self.accept()

    @classmethod
    def ask(cls, parent, title, fields, tr, hint="", validate=None, width=560, ok_label=None) -> dict | None:
        dlg = cls(parent, title, fields, tr, hint, validate, width, ok_label)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_values
        return None


# --- Tabellen ------------------------------------------------------------------------------------------

class _Item(QTableWidgetItem):
    def __lt__(self, other):  # noqa: D105
        a, b = self.data(SORT_ROLE), other.data(SORT_ROLE)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        return super().__lt__(other)


def sort_key(kind: str, value):
    if value is None or value == "":
        return -1 if kind in ("int", "float") else ""
    if kind == "ip":     # als Hex-Text: IPv6-Schlüssel passen nicht in Qts 64-Bit-Zahlen
        return f"{max(0, ip.ip_sort_key(str(value))):033x}"
    if kind in ("int", "float"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return -1
    return str(value).lower()


def fmt_cell(kind: str, value) -> str:
    if value is None:
        return ""
    if kind == "float" and isinstance(value, (int, float)):
        return f"{value:.1f}"
    if kind == "opt" and isinstance(value, int):
        return f"{value:03d}"
    if isinstance(value, bool):
        return "✓" if value else ""
    return str(value)


_ask_context = None     # ToolContext mit add_ask_action (KI, ab OmniWrench 0.9.0)


def set_ask_hook(context) -> None:
    """Kontextmenüs der Tabellen bekommen „Assistent fragen …“, wenn das Hauptprogramm es anbietet."""
    global _ask_context
    _ask_context = context if hasattr(context, "add_ask_action") else None


def add_ask_action(menu, text_fn) -> None:
    if _ask_context is not None:
        menu.addSeparator()
        _ask_context.add_ask_action(menu, text_fn)


class Grid(QTableWidget):
    """Tabelle aus Zeilen-Dicts. cols: [(key, titel, art)], art = text|ip|int|float|opt."""

    action = Signal(str)

    def __init__(self, cols: list[tuple[str, str, str]], key_fn: Callable[[dict], str] | None = None,
                 actions: list | None = None, default_action: str | None = None, multi: bool = True,
                 stretch: str | None = None, sortable: bool = True, parent=None):
        super().__init__(parent)
        self.cols = cols
        self.sortable = sortable
        self.key_fn = key_fn or (lambda r: str(id(r)))
        self.rows: list[dict] = []
        self.tooltip_fn: Callable[[dict], str] | None = None
        self.default_action = default_action
        self._actions: list = actions or []
        self._last_cell: tuple[int, int] | None = None
        self.setColumnCount(len(cols))
        self.setHorizontalHeaderLabels([c[1] for c in cols])
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multi
                              else QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setSortingEnabled(sortable)
        self.setWordWrap(False)
        if stretch:
            for i, c in enumerate(cols):
                if c[0] == stretch:
                    self.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.cellDoubleClicked.connect(lambda *_: self.default_action and self.action.emit(self.default_action))
        self.cellPressed.connect(lambda r, c: setattr(self, "_last_cell", (r, c)))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self._qactions: dict[str, QAction] = {}
        for spec in self._actions:
            if spec == "-":
                continue
            aid, label, sc = spec
            a = QAction(label, self)
            if sc:
                a.setShortcut(QKeySequence(sc))
                a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                self.addAction(a)
            a.triggered.connect(lambda _=False, x=aid: self._trigger(x))
            self._qactions[aid] = a

    def _trigger(self, aid: str) -> None:
        if aid == "CopyCell":
            self.copy_cell()
            return
        self.action.emit(aid)

    def _menu(self, pos) -> None:
        idx = self.indexAt(pos)
        if idx.isValid():
            self._last_cell = (idx.row(), idx.column())
            if not self.item(idx.row(), 0) or not self.item(idx.row(), 0).isSelected():
                self.selectRow(idx.row())
        m = QMenu(self)
        for spec in self._actions:
            if spec == "-":
                m.addSeparator()
            else:
                m.addAction(self._qactions[spec[0]])
        if self.selected_rows():
            add_ask_action(m, self.selection_text)
        if not m.isEmpty():
            m.exec(self.viewport().mapToGlobal(pos))

    def selection_text(self, limit: int = 200) -> str:
        """Markierte Zeilen als Text (sichtbare Spalten „Titel: Wert“), z. B. für den Assistenten."""
        vis = [(k, t, kind) for i, (k, t, kind) in enumerate(self.cols) if not self.isColumnHidden(i)]
        rows = self.selected_rows()
        lines = ["; ".join(f"{t}: {fmt_cell(kind, r.get(k))}" for k, t, kind in vis if r.get(k) not in (None, ""))
                 for r in rows[:limit]]
        if len(rows) > limit:
            lines.append(f"… (+{len(rows) - limit})")
        return "\n".join(lines)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.default_action and self.state() != QAbstractItemView.State.EditingState:
            self.action.emit(self.default_action)
            return
        super().keyPressEvent(e)

    # ----------------------------------------------------------------------------------------------
    def set_rows(self, rows: list[dict]) -> None:
        sel = {self.key_fn(r) for r in self.selected_rows()}
        self.setSortingEnabled(False)
        self.clearContents()
        self.rows = list(rows)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, (key, _t, kind) in enumerate(self.cols):
                val = row.get(key)
                it = _Item(fmt_cell(kind, val))
                it.setData(SORT_ROLE, sort_key(kind, val))
                it.setData(Qt.ItemDataRole.UserRole, r)
                if kind in ("ip", "opt") or key in ("cid",):
                    it.setFont(MONO)
                if kind in ("int", "float"):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.setItem(r, c, it)
        self.setSortingEnabled(self.sortable)
        if sel:
            self.select_keys(sel)

    def row_at(self, visual_row: int) -> dict | None:
        it = self.item(visual_row, 0)
        if it is None:
            return None
        i = it.data(Qt.ItemDataRole.UserRole)
        return self.rows[i] if i is not None and 0 <= i < len(self.rows) else None

    def selected_rows(self) -> list[dict]:
        vis = sorted({i.row() for i in self.selectedIndexes()})
        out = []
        for v in vis:
            if self.isRowHidden(v):
                continue
            r = self.row_at(v)
            if r is not None:
                out.append(r)
        return out

    def current(self) -> dict | None:
        s = self.selected_rows()
        return s[0] if s else None

    def visible_rows(self) -> list[dict]:
        return [r for v in range(self.rowCount()) if not self.isRowHidden(v) and (r := self.row_at(v)) is not None]

    def _visual_of_key(self, key: str) -> int:
        for v in range(self.rowCount()):
            r = self.row_at(v)
            if r is not None and self.key_fn(r) == key:
                return v
        return -1

    def select_keys(self, keys) -> None:
        self.clearSelection()
        first = None
        mode = self.selectionMode()
        self.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for k in keys:
            v = self._visual_of_key(k)
            if v >= 0:
                self.selectRow(v)
                first = v if first is None else first
        self.setSelectionMode(mode)
        if first is not None:
            self.scrollToItem(self.item(first, 0))

    def select_key(self, key: str) -> bool:
        v = self._visual_of_key(key)
        if v < 0:
            return False
        self.clearSelection()
        self.selectRow(v)
        self.setCurrentCell(v, 0)
        self.scrollToItem(self.item(v, 0))
        return True

    def style_row(self, key: str, back: QColor | None = None, fore: str | None = None, bold: bool = False,
                  tooltip: str | None = None, col_keys: list[str] | None = None) -> None:
        v = self._visual_of_key(key)
        if v < 0:
            return
        for c, col in enumerate(self.cols):
            if col_keys and col[0] not in col_keys:
                continue
            it = self.item(v, c)
            if it is None:
                continue
            it.setBackground(QBrush(back) if back is not None else QBrush())
            it.setForeground(QBrush(QColor(fore)) if fore else QBrush())
            f = it.font()
            f.setBold(bold)
            it.setFont(f)
            if tooltip is not None:
                it.setToolTip(tooltip)

    def style_cell(self, key: str, col_key: str, fore: str | None = None, back: QColor | None = None,
                   bold: bool = False) -> None:
        v = self._visual_of_key(key)
        if v < 0:
            return
        for c, col in enumerate(self.cols):
            if col[0] == col_key:
                it = self.item(v, c)
                if it is None:
                    return
                it.setForeground(QBrush(QColor(fore)) if fore else QBrush())
                it.setBackground(QBrush(back) if back is not None else QBrush())
                f = it.font()
                f.setBold(bold)
                it.setFont(f)

    def set_tooltips(self, fn: Callable[[dict], str]) -> None:
        for v in range(self.rowCount()):
            r = self.row_at(v)
            if r is None:
                continue
            t = fn(r)
            for c in range(self.columnCount()):
                it = self.item(v, c)
                if it is not None:
                    it.setToolTip(t)

    def apply_filter(self, text: str, fields: list[str] | None = None) -> None:
        q = (text or "").strip().lower()
        for v in range(self.rowCount()):
            r = self.row_at(v)
            if r is None:
                continue
            if not q:
                self.setRowHidden(v, False)
                continue
            hay = " ".join(str(r.get(k) or "") for k in (fields or [c[0] for c in self.cols])).lower()
            self.setRowHidden(v, q not in hay)

    def rows_as_text(self, rows: list[dict] | None = None) -> str:
        rows = self.selected_rows() if rows is None else rows
        lines = ["\t".join(c[1] for c in self.cols)]
        for r in rows:
            lines.append("\t".join(fmt_cell(c[2], r.get(c[0])) for c in self.cols))
        return "\r\n".join(lines)

    def copy_cell(self) -> str:
        rc = self._last_cell or ((self.currentRow(), self.currentColumn()) if self.currentRow() >= 0 else None)
        if not rc:
            return ""
        it = self.item(*rc)
        t = it.text() if it else ""
        if t:
            QApplication.clipboard().setText(t)
        return t

    def autosize(self, max_width: int = 360) -> None:
        self.resizeColumnsToContents()
        for c in range(self.columnCount() - 1):
            if self.columnWidth(c) > max_width:
                self.setColumnWidth(c, max_width)
            elif self.columnWidth(c) < 60:
                self.setColumnWidth(c, 60)

    # --- Aktionen ein-/ausblenden (Rechte, Sperren) ---------------------------------------------------
    def set_action_visible(self, aid: str, on: bool) -> None:
        a = self._qactions.get(aid)
        if a is not None:
            a.setVisible(on)
            a.setEnabled(on)

    def has_action(self, aid: str) -> bool:
        a = self._qactions.get(aid)
        return a is not None and a.isEnabled()

    # --- Spalten frei anordnen und ein-/ausblenden (gespeichert in den Tool-Einstellungen) -------------
    def enable_layout(self, settings, key: str, hidden: tuple[str, ...] = (), labels: tuple[str, str] = ("", "")) -> None:
        """Spalten per Ziehen verschiebbar; Rechtsklick auf den Kopf blendet Spalten ein/aus.
        Reihenfolge der cols = Standard. labels = (Menütitel "Spalten", "Standardanordnung")."""
        self._layout = (settings, key, tuple(hidden), labels)
        h = self.horizontalHeader()
        h.setSectionsMovable(True)
        h.setFirstSectionMovable(True)
        h.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        h.customContextMenuRequested.connect(self._header_menu)
        self._restore_layout()
        h.sectionMoved.connect(lambda *_: self._save_layout())

    def _restore_layout(self) -> None:
        settings, key, hidden, _l = self._layout
        saved = settings.get(key) or {}
        keys = [c[0] for c in self.cols]
        order = [k for k in (saved.get("order") or []) if k in keys]
        order += [k for k in keys if k not in order]
        h = self.horizontalHeader()
        h.blockSignals(True)
        for vis, k in enumerate(order):
            h.moveSection(h.visualIndex(keys.index(k)), vis)
        h.blockSignals(False)
        hide = set(saved["hidden"]) if isinstance(saved.get("hidden"), list) else set(hidden)
        for i, k in enumerate(keys):
            self.setColumnHidden(i, k in hide)

    def _save_layout(self) -> None:
        settings, key, _h, _l = self._layout
        h = self.horizontalHeader()
        keys = [c[0] for c in self.cols]
        order = [keys[h.logicalIndex(v)] for v in range(len(keys))]
        settings.set(key, {"order": order, "hidden": [k for i, k in enumerate(keys) if self.isColumnHidden(i)]})

    def _header_menu(self, pos) -> None:
        settings, key, _h, (title, reset) = self._layout
        m = QMenu(self)
        if title:
            m.addSection(title)
        h = self.horizontalHeader()
        for v in range(len(self.cols)):
            i = h.logicalIndex(v)
            a = m.addAction(self.cols[i][1])
            a.setCheckable(True)
            a.setChecked(not self.isColumnHidden(i))
            a.toggled.connect(lambda on, i=i: (self.setColumnHidden(i, not on), self._save_layout()))
        m.addSeparator()
        m.addAction(reset, lambda: (settings.set(key, None), self._restore_layout()))
        m.exec(h.viewport().mapToGlobal(pos))


class ButtonBar(QWidget):
    """Schaltflächen nebeneinander (umbrechend); actions: [(id, text)] oder "|" als Abstand."""

    action = Signal(str)

    def __init__(self, actions: list, parent=None, primary: tuple[str, ...] = ()):
        super().__init__(parent)
        self.flow = FlowLayout(self, spacing=6)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.buttons: dict[str, QPushButton] = {}
        self._order: list[QWidget] = []
        for spec in actions:
            aid, text = spec
            b = make_button(text, primary=aid in primary, on_click=lambda _=False, x=aid: self.action.emit(x))
            self.buttons[aid] = b
            self._order.append(b)
            self.flow.addWidget(b)

    def add_widget(self, w: QWidget) -> None:
        self._order.append(w)
        self.flow.addWidget(w)

    def set_visible(self, aid: str, on: bool) -> None:
        """Schaltfläche ein-/ausblenden; ausgeblendete kommen aus dem FlowLayout (es zählt sonst ihre Breite mit)."""
        b = self.buttons.get(aid)
        if b is None or b.isHidden() != on:
            return
        b.setVisible(on)
        for w in self._order:
            self.flow.removeWidget(w)
        for w in self._order:
            if not w.isHidden():
                self.flow.addWidget(w)
        self.updateGeometry()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.LayoutRequest:
            self.updateGeometry()      # Schaltflächen wurden breiter (Stil) -> übergeordnetes Layout neu rechnen
        return super().event(e)

    def sizeHint(self) -> QSize:  # noqa: N802 - bevorzugt einzeilig (FlowLayout meldet nur die breiteste Schaltfläche)
        items = [self.flow.itemAt(i) for i in range(self.flow.count())]
        hints = [it.sizeHint() for it in items if it.widget() is None or not it.widget().isHidden()]
        if not hints:
            return QSize(0, 0)
        # +1: FlowLayout bricht schon um, wenn die Zeile rect.right() (= Breite - 1) erreicht
        return QSize(sum(h.width() for h in hints) + 6 * (len(hints) - 1) + 1, max(h.height() for h in hints))


# --- Befundfilter (gemeinsam für alle Ansichten) -----------------------------------------------------

class FilterState(QObject):
    changed = Signal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        saved = settings.get("filter_levels") or {}
        self.levels = {lv: bool(saved.get(lv, True)) for lv in ck.LEVELS}
        self.hidden: set[str] = set(settings.get("hidden_categories") or [])

    def save(self) -> None:
        self.settings.set("filter_levels", dict(self.levels))
        self.settings.set("hidden_categories", sorted(self.hidden))
        self.changed.emit()

    def visible(self, f: ck.Finding, search: str = "", target: str | None = None, ignore_level: bool = False,
                tr=None) -> bool:
        if not ignore_level and not self.levels.get(f.level, True):
            return False
        if f.area in self.hidden:
            return False
        if target and target not in f.targets:
            return False
        if search:
            hay = f"{tr(f'level.{f.level}') if tr else f.level} {tr(f'cat.{f.area}') if tr else f.area} {f.obj} {f.scope_id} {f.text}"
            if search.lower() not in hay.lower():
                return False
        return True

    def marker(self, f: ck.Finding) -> bool:
        """Für Markierungen: ohne Infos; Fehler immer, sonst nur, wenn nicht ausgefiltert."""
        if f.level == ck.INFO:
            return False
        return f.level == ck.ERROR or self.visible(f)


class FindingsView(QWidget):
    """Befundliste mit Filterleiste (Stufen, Kategorien, Suche) und optionalem Zielfilter."""

    activated = Signal(object, str)   # (Finding, "Default" | "Fix" | "Goto")

    def __init__(self, tr, flt: FilterState, show_scope: bool = False, scope_mode: bool = False, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.flt = flt
        self.show_scope = show_scope
        self.scope_mode = scope_mode      # Server-Prüfung: Aktion = Scope öffnen
        self.findings: list[ck.Finding] = []
        self.search = ""
        self.target: str | None = None
        self.target_label = ""
        self.empty_text = tr("find.none")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.toolbar = FindingsToolbar(tr, flt, self)
        self.toolbar.search_changed.connect(self._search)
        self.toolbar.clear_target.connect(self.clear_target)
        lay.addWidget(self.toolbar)
        cols = [tr("find.col.level"), tr("find.col.category")]
        if show_scope:
            cols.append(tr("find.col.scope"))
        cols += [tr("find.col.object"), tr("find.col.text"), tr("find.col.action")]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.text_col = len(cols) - 2
        h.setSectionResizeMode(self.text_col, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(1, 130)
        if show_scope:
            self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(self.text_col - 1, 170)
        self.table.setColumnWidth(self.text_col + 1, 190)
        # Zeilenhöhen nach jeder Breitenänderung neu (beim ersten Füllen ist die Seite oft noch schmal/verborgen)
        self._rows_timer = QTimer(self)
        self._rows_timer.setSingleShot(True)
        self._rows_timer.setInterval(50)
        self._rows_timer.timeout.connect(self.table.resizeRowsToContents)
        h.sectionResized.connect(lambda *_: self._rows_timer.start())
        self.table.cellDoubleClicked.connect(lambda r, _c: self._act(r, "Default"))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        copy = QAction(self.table)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        copy.triggered.connect(lambda: self.copy(False))
        self.table.addAction(copy)
        lay.addWidget(self.table, 1)
        flt.changed.connect(self.refresh)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.table.currentRow() >= 0:
            self._act(self.table.currentRow(), "Default")
            return
        super().keyPressEvent(e)

    def set_findings(self, findings: list[ck.Finding]) -> None:
        self.findings = [f for f in findings if f]
        self.refresh()

    def set_target(self, key: str | None, label: str = "") -> None:
        self.target = key
        self.target_label = label
        self.refresh()

    def clear_target(self) -> None:
        self.set_target(None)

    def _search(self, text: str) -> None:
        self.search = text
        self.refresh()

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for f in self.findings:
            if self.flt.visible(f, self.search, self.target, True, self.tr):
                c[f.level] = c.get(f.level, 0) + 1
        return c

    def refresh(self) -> None:
        tr = self.tr
        self.toolbar.sync(self.counts(), self.findings)
        shown = [f for f in self.findings if self.flt.visible(f, self.search, self.target, False, tr)]
        t = self.table
        t.setRowCount(0)
        t.setRowCount(max(1, len(shown)))
        for r, f in enumerate(shown):
            if self.scope_mode:
                act = tr("find.act_scope") if f.scope_id else ""
            elif f.fix:
                act = "→ " + f.fix_label
            elif f.targets:
                act = tr("find.act_goto")
            else:
                act = ""
            vals = [level_name(tr, f.level), tr(f"cat.{f.area}")]
            if self.show_scope:
                vals.append(f.scope_id)
            vals += [f.obj, f.text, act]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v or ""))
                it.setData(Qt.ItemDataRole.UserRole, r)
                it.setBackground(QBrush(tint(level_color(f.level), 34)))
                if c == 0:
                    it.setIcon(level_icon(f.level))
                    fo = it.font()
                    fo.setBold(True)
                    it.setFont(fo)
                if c == len(vals) - 1 and v:
                    it.setForeground(QBrush(QColor(theme.current["accent"])))
                t.setItem(r, c, it)
        self._shown = shown
        if not shown:
            txt = tr("find.none_filtered") if self.findings else self.empty_text
            it = QTableWidgetItem(tr("find.ok"))
            it.setIcon(level_icon(None))
            t.setItem(0, 0, it)
            t.setItem(0, self.text_col, QTableWidgetItem(txt))
        t.resizeRowsToContents()
        self.toolbar.set_count(tr("find.count", shown=len(shown), total=len(self.findings)))
        self.toolbar.set_target(self.target_label if self.target else "")

    def _act(self, row: int, mode: str) -> None:
        shown = getattr(self, "_shown", [])
        if 0 <= row < len(shown):
            self.activated.emit(shown[row], mode)

    def _menu(self, pos) -> None:
        tr = self.tr
        m = QMenu(self)
        row = self.table.indexAt(pos).row()
        if not self.scope_mode:
            m.addAction(tr("find.menu.fix"), lambda: self._act(row, "Fix"))
        m.addAction(tr("find.menu.goto"), lambda: self._act(row, "Goto"))
        m.addSeparator()
        m.addAction(tr("find.menu.copy"), lambda: self.copy(False))
        m.addAction(tr("find.menu.copy_all"), lambda: self.copy(True))
        add_ask_action(m, lambda: self.copy(False, to_clipboard=False))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def copy(self, all_rows: bool, to_clipboard: bool = True) -> str:
        shown = getattr(self, "_shown", [])
        rows = range(len(shown)) if all_rows else sorted({i.row() for i in self.table.selectedIndexes()})
        lines = []
        for r in rows:
            if 0 <= r < len(shown):
                f = shown[r]
                parts = [level_name(self.tr, f.level), self.tr(f"cat.{f.area}")]
                if self.show_scope:
                    parts.append(f.scope_id)
                parts += [f.obj, f.text]
                lines.append("\t".join(parts))
        if lines and to_clipboard:
            QApplication.clipboard().setText("\r\n".join(lines))
        return "\n".join(lines)


class FindingsToolbar(QWidget):
    search_changed = Signal(str)
    clear_target = Signal()
    only_with = Signal(bool)

    def __init__(self, tr, flt: FilterState, parent=None, scope_list: bool = False):
        super().__init__(parent)
        self.tr = tr
        self.flt = flt
        self._all: list[ck.Finding] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(QLabel(tr("find.show")))
        self.level_btns: dict[str, QToolButton] = {}
        for lv in ck.LEVELS:
            b = QToolButton()
            b.setCheckable(True)
            b.setChecked(flt.levels.get(lv, True))
            b.setIcon(level_icon(lv))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setToolTip(tr("find.toggle_level", level=level_name(tr, lv, True)))
            b.toggled.connect(lambda on, x=lv: self._level(x, on))
            self.level_btns[lv] = b
            lay.addWidget(b)
        self.cat_btn = QToolButton()
        self.cat_btn.setText(tr("find.categories"))
        self.cat_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.cat_menu = QMenu(self.cat_btn)
        self.cat_menu.aboutToShow.connect(self._fill_categories)
        self.cat_btn.setMenu(self.cat_menu)
        lay.addWidget(self.cat_btn)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("find.search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(self.search_changed.emit)
        lay.addWidget(self.search)
        self.only = None
        if scope_list:
            self.only = QCheckBox(tr("find.only_with"))
            self.only.toggled.connect(self.only_with.emit)
            lay.addWidget(self.only)
        self.target_lbl = QLabel("")
        self.target_lbl.setStyleSheet(f"color:{level_color(ck.BP)}; font-weight:600;")
        self.target_lbl.hide()
        self.clear_btn = QToolButton()
        self.clear_btn.setText(tr("find.clear_target"))
        self.clear_btn.clicked.connect(lambda _=False: self.clear_target.emit())
        self.clear_btn.hide()
        lay.addWidget(self.target_lbl)
        lay.addWidget(self.clear_btn)
        lay.addStretch(1)
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet(f"color:{theme.current['muted']};")
        lay.addWidget(self.count_lbl)
        self._syncing = False

    def _level(self, lv: str, on: bool) -> None:
        if self._syncing:
            return
        self.flt.levels[lv] = on
        self.flt.save()

    def _fill_categories(self) -> None:
        tr = self.tr
        self.cat_menu.clear()
        cnt: dict[str, int] = {}
        for f in self._all:
            cnt[f.area] = cnt.get(f.area, 0) + 1
        self.cat_menu.addAction(tr("find.cat_all"), lambda: self._set_cats(set()))
        self.cat_menu.addAction(tr("find.cat_none"), lambda: self._set_cats(set(ck.CATEGORIES) | set(cnt)))
        self.cat_menu.addSeparator()
        for c in list(ck.CATEGORIES) + sorted(k for k in cnt if k not in ck.CATEGORIES):
            a = self.cat_menu.addAction(f"{tr('cat.' + c)}  ({cnt.get(c, 0)})")
            a.setCheckable(True)
            a.setChecked(c not in self.flt.hidden)
            a.toggled.connect(lambda on, x=c: self._cat(x, on))

    def _set_cats(self, hidden: set[str]) -> None:
        self.flt.hidden = set(hidden)
        self.flt.save()

    def _cat(self, c: str, on: bool) -> None:
        if on:
            self.flt.hidden.discard(c)
        else:
            self.flt.hidden.add(c)
        self.flt.save()

    def sync(self, counts: dict[str, int], all_findings: list[ck.Finding]) -> None:
        self._all = all_findings
        self._syncing = True
        try:
            for lv, b in self.level_btns.items():
                want = self.flt.levels.get(lv, True)
                if b.isChecked() != want:
                    b.setChecked(want)
                b.setText(f"{level_name(self.tr, lv, True)} ({counts.get(lv, 0)})")
        finally:
            self._syncing = False
        n = len(self.flt.hidden)
        self.cat_btn.setText(self.tr("find.categories_hidden", n=n) if n else self.tr("find.categories"))

    def set_count(self, text: str) -> None:
        self.count_lbl.setText(text)

    def set_target(self, label: str) -> None:
        self.target_lbl.setText(self.tr("find.filtered_to", name=label) if label else "")
        self.target_lbl.setVisible(bool(label))
        self.clear_btn.setVisible(bool(label))


# --- Markierungen an Feldern -------------------------------------------------------------------------

class MarkerButton(QToolButton):
    def __init__(self, key: str, on_click: Callable[[str], None], parent=None):
        super().__init__(parent)
        self.key = key
        self.setText("?")
        self.setFixedSize(QSize(20, 20))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda: on_click(self.key))
        self.hide()

    def set_level(self, level: str | None, tip: str) -> None:
        if not level:
            self.hide()
            return
        self.setStyleSheet(f"QToolButton {{ background:{level_color(level)}; color:white; border:none; border-radius:10px;"
                           f" font-weight:700; }}")
        self.setToolTip(tip)
        self.show()


class Markers:
    """Feld-Markierungen: farbiger Rahmen + "?"-Knopf, Tooltip mit den Befunden."""

    def __init__(self, tr, flt: FilterState, on_click: Callable[[str], None]):
        self.tr = tr
        self.flt = flt
        self.on_click = on_click
        self.items: dict[str, tuple[QWidget | None, MarkerButton | None, bool]] = {}

    def add(self, key: str, widget: QWidget | None, color: bool = True, icon: bool = True) -> MarkerButton | None:
        btn = MarkerButton(key, self.on_click) if icon else None
        self.items[key] = (widget, btn, color)
        return btn

    def update(self, index: dict[str, list[ck.Finding]]) -> None:
        for key, (w, btn, color) in self.items.items():
            fs = [f for f in index.get(key, []) if self.flt.marker(f)]
            lvl = ck.worst(fs)
            tip = "\n".join(f"[{level_name(self.tr, f.level)}] {f.text}" for f in fs)
            if btn is not None:
                btn.set_level(lvl, tip)
            if w is not None and color:
                if lvl:
                    w.setStyleSheet(f"border: 2px solid {level_color(lvl)}; border-radius: 4px;")
                    w.setToolTip(tip)
                else:
                    w.setStyleSheet("")
                    w.setToolTip("")


def finding_tip(tr, findings: list[ck.Finding], limit: int = 12) -> str:
    lines = [f"[{level_name(tr, f.level)}] {f.text}" for f in findings[:limit]]
    if len(findings) > limit:
        lines.append(tr("find.more", n=len(findings) - limit))
    return "\n".join(lines)


class HelpIcon(QLabel):
    """Kleines Fragezeichen statt langer Hinweistexte: Text als Tooltip (Mauszeiger darüber oder Klick)."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setPixmap(library_icon("circle-help", 16, theme.current["muted"]).pixmap(16, 16))
        self.setFixedSize(QSize(20, 20))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.set_text(text)

    def set_text(self, text: str) -> None:
        body = "<br>".join(html.escape(x) for x in text.split("\n"))
        self.setToolTip(f"<p style='max-width:420px'>{body}</p>" if text else "")

    def mousePressEvent(self, e) -> None:  # noqa: N802
        QToolTip.showText(e.globalPosition().toPoint(), self.toolTip(), self)


def help_icon(text: str) -> HelpIcon:
    return HelpIcon(text)


def hint_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{theme.current['muted']};")
    return lbl


def bold_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setBold(True)
    lbl.setFont(f)
    return lbl
