"""Wiederverwendbare Eingabebausteine: Lease-Dauer, Bereichsliste und Optionsliste (Scope, Server, Entwurf)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QLabel, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from . import checks as ck
from . import ipcalc as ip
from .ui_base import MONO, ButtonBar, Grid, help_icon, level_color, tint


class LeaseEdit(QWidget):
    """Lease-Dauer als Tage/Stunden/Minuten, wahlweise unbegrenzt."""

    changed = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.d, self.h, self.m = QSpinBox(), QSpinBox(), QSpinBox()
        for box, mx, key in ((self.d, 999, "lease.unit_d"), (self.h, 23, "lease.unit_h"), (self.m, 59, "lease.unit_m")):
            box.setRange(0, mx)
            box.valueChanged.connect(lambda _v: self.changed.emit())
            lay.addWidget(box)
            lay.addWidget(QLabel(tr(key)))
        self.unlimited = QCheckBox(tr("lease.unlimited"))
        self.unlimited.toggled.connect(self._toggle)
        lay.addWidget(self.unlimited)
        lay.addStretch(1)

    def _toggle(self, on: bool) -> None:
        for b in (self.d, self.h, self.m):
            b.setEnabled(not on)
        self.changed.emit()

    def set_value(self, seconds: int | None) -> None:
        self.blockSignals(True)
        unl = ip.lease_is_unlimited(seconds)
        self.unlimited.setChecked(unl)
        d, h, m = (8, 0, 0) if unl or seconds is None else ip.lease_parts(seconds)
        self.d.setValue(d)
        self.h.setValue(h)
        self.m.setValue(m)
        self.blockSignals(False)

    def value(self) -> int:
        if self.unlimited.isChecked():
            return ip.UNLIMITED
        return self.d.value() * 86400 + self.h.value() * 3600 + self.m.value() * 60


class RangeEditor(QWidget):
    """Liste der Verteilbereiche (Start/Ende). Aus den Bereichen ergeben sich Scope-Grenzen und Ausschlüsse."""

    changed = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.model: ip.ScopeModel | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("rng.col.start"), tr("rng.col.end"), tr("rng.col.count")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setMinimumHeight(130)
        self.table.itemChanged.connect(self._item_changed)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        self.bar = ButtonBar([("Add", tr("rng.add")), ("Remove", tr("rng.remove")), ("WholeNet", tr("rng.whole_net")),
                              ("Merge", tr("rng.merge"))])
        self.bar.action.connect(self._action)
        row.addWidget(self.bar, 1)
        self.sum = QLabel("")
        row.addWidget(self.sum)
        row.addWidget(help_icon(tr("rng.note")))
        lay.addLayout(row)
        self._updating = False
        self.confirm_whole = None   # Rückfrage vor "Ganzes Netz" bei mehreren Bereichen

    # ----------------------------------------------------------------------------------------------
    def _item_changed(self, it: QTableWidgetItem) -> None:
        if self._updating or it.column() == 2:
            return
        self.changed.emit()

    def _action(self, aid: str) -> None:
        if aid == "Add":
            self.add_row("", "")
            self.table.setCurrentCell(self.table.rowCount() - 1, 0)
            self.table.editItem(self.table.item(self.table.rowCount() - 1, 0))
        elif aid == "Remove":
            rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
            for r in rows:
                self.table.removeRow(r)
            if rows:
                self.changed.emit()
        elif aid == "WholeNet":
            if self.table.rowCount() > 1 and self.confirm_whole and not self.confirm_whole():
                return
            self.whole_net()
        elif aid == "Merge":
            self.merge()

    def add_row(self, start: str, end: str, emit: bool = True) -> None:
        self._updating = True
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate((start, end)):
            it = QTableWidgetItem(v)
            it.setFont(MONO)
            self.table.setItem(r, c, it)
        cnt = QTableWidgetItem("")
        cnt.setFlags(cnt.flags() & ~Qt.ItemFlag.ItemIsEditable)
        cnt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(r, 2, cnt)
        self._updating = False
        if emit:
            self.changed.emit()

    def set_ranges(self, ranges: list[tuple[int, int]]) -> None:
        self._updating = True
        self.table.setRowCount(0)
        self._updating = False
        for s, e in ranges:
            self.add_row(ip.int2ip(s), ip.int2ip(e), emit=False)

    def items(self) -> list[tuple[int, str, str]]:
        out = []
        for r in range(self.table.rowCount()):
            s = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            e = (self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip()
            if s or e:
                out.append((r, s, e))
        return out

    def valid_ranges(self) -> list[tuple[int, int]]:
        out = []
        for _r, s, e in self.items():
            if ip.is_ipv4(s) and ip.is_ipv4(e):
                a, b = sorted((ip.ip2int(s), ip.ip2int(e)))
                out.append((a, b))
        return sorted(out)

    def merged(self) -> list[tuple[int, int]]:
        return ip.merge_ranges(self.valid_ranges())

    # ----------------------------------------------------------------------------------------------
    def whole_net(self) -> None:
        if not self.model or self.model.hosts < 1:
            return
        self.set_ranges([(self.model.net + 1, self.model.bc - 1)])
        self.changed.emit()

    def merge(self) -> None:
        m = self.merged()
        if m:
            self.set_ranges(m)
            self.changed.emit()

    def swap(self, row: int) -> None:
        if 0 <= row < self.table.rowCount():
            a, b = self.table.item(row, 0).text(), self.table.item(row, 1).text()
            self._updating = True
            self.table.item(row, 0).setText(b)
            self.table.item(row, 1).setText(a)
            self._updating = False
            self.changed.emit()

    def clip(self) -> None:
        """Bereiche auf die nutzbaren Adressen des Netzes kürzen (ohne Netz- und Broadcastadresse)."""
        if not self.model:
            return
        lo, hi = self.model.net + 1, self.model.bc - 1
        out = []
        for s, e in self.valid_ranges():
            s, e = max(s, lo), min(e, hi)
            if s <= e:
                out.append((s, e))
        self.set_ranges(out)
        self.changed.emit()

    def show_result(self, counts: dict[int, int], total: int, index: dict[str, list[ck.Finding]], flt) -> None:
        """Adressanzahl je Zeile, Summe und Zeilenfarbe nach Befunden."""
        self._updating = True
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 2)
            if it is not None:
                it.setText(str(counts[r]) if r in counts else "")
            fs = [f for f in index.get(f"Range:{r}", []) if flt.marker(f)]
            lvl = ck.worst(fs)
            tip = "\n".join(f.text for f in fs)
            for c in range(3):
                cell = self.table.item(r, c)
                if cell is not None:
                    cell.setBackground(QBrush(tint(level_color(lvl), 60)) if lvl else QBrush())
                    cell.setToolTip(tip)
        self._updating = False
        self.sum.setText(self.tr("rng.sum", n=total))


# --- Optionsliste --------------------------------------------------------------------------------------

def option_rows(options: list[dict], defs: dict) -> list[dict]:
    rows = []
    for o in options:
        d = defs.get((o.get("vendor") or "", int(o["id"])))
        rows.append({"id": int(o["id"]), "name": (d or {}).get("name") or o.get("name") or "", "value": ", ".join(o["values"]),
                     "values": list(o["values"]), "vendor": o.get("vendor") or "", "user": o.get("user") or "",
                     "type": (d or {}).get("type", "")})
    return rows


def opt_row_key(r: dict) -> str:
    return ck.option_key(r["id"], r.get("vendor"), r.get("user"))


class OptionsPanel(QWidget):
    """Optionswerte eines Scopes oder des Servers mit Schaltflächen; Aktionen gehen als Signal an den Besitzer."""

    action = Signal(str)

    def __init__(self, tr, server_level: bool = False, parent=None):
        super().__init__(parent)
        self.tr = tr
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        acts = [("Add", tr("opt.add"), "Ins"), ("Edit", tr("opt.edit"), "F2"), ("Remove", tr("opt.remove"), "Del"), "-",
                ("Copy", tr("ui.copy"), "Ctrl+C"), ("Paste", tr("ui.paste"), "Ctrl+V"), ("CopyCell", tr("ui.copy_cell"), "")]
        if server_level:
            acts += ["-", ("ToPartner", tr("opt.to_partner"), "")]
        self.grid = Grid([("id", tr("opt.col.id"), "opt"), ("name", tr("opt.col.name"), "text"),
                          ("value", tr("opt.col.value"), "text"), ("vendor", tr("opt.col.vendor"), "text"),
                          ("user", tr("opt.col.user"), "text")], key_fn=opt_row_key, actions=acts, default_action="Edit",
                         stretch="value")
        self.grid.action.connect(self.action.emit)
        lay.addWidget(self.grid, 1)
        btns = [("Add", tr("opt.add")), ("Edit", tr("opt.edit")), ("Remove", tr("opt.remove")), ("Copy", tr("ui.copy")),
                ("Paste", tr("ui.paste"))]
        if server_level:
            btns.append(("ToPartner", tr("opt.to_partner")))
        self.bar = ButtonBar(btns)
        self.bar.action.connect(self.action.emit)
        self.bar.add_widget(help_icon(tr("opt.server_note") if server_level else tr("opt.scope_note")))
        lay.addWidget(self.bar)

    def set_options(self, options: list[dict], defs: dict) -> None:
        self.grid.set_rows(option_rows(options, defs))
        self.grid.setColumnWidth(0, 70)
        self.grid.setColumnWidth(1, 220)

    def mark(self, index: dict[str, list[ck.Finding]], flt) -> None:
        for r in self.grid.rows:
            k = opt_row_key(r)
            fs = [f for f in index.get(k, []) if flt.marker(f)]
            lvl = ck.worst(fs)
            self.grid.style_row(k, tint(level_color(lvl), 60) if lvl else None, None, False,
                                "\n".join(f.text for f in fs) if fs else "")


def muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.current['muted']};")
    return lbl


def color_text(text: str, color: str) -> str:
    return f"<span style='color:{QColor(color).name()}'>{text}</span>"
