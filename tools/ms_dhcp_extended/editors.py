"""Wiederverwendbare Eingabebausteine: Lease-Dauer, Adresspool und Optionsliste (Scope, Server, Entwurf)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

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


class PoolEditor(QWidget):
    """Adresspool des Scopes wie in der DHCP-Konsole: eine Start- und eine Endadresse. Ausschlüsse werden
    getrennt auf der Seite „Ausschlüsse“ gepflegt (keine Umrechnung von Bereichen in Ausschlüsse)."""

    changed = Signal()

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.model: ip.ScopeModel | None = None
        self.confirm_whole = None   # nicht mehr nötig, bleibt für Aufrufer kompatibel
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.start, self.end = QLineEdit(), QLineEdit()
        for lbl, w in ((tr("pool.start"), self.start), (tr("pool.end"), self.end)):
            w.setFont(MONO)
            w.setPlaceholderText("0.0.0.0")
            w.setMaximumWidth(170)
            w.textChanged.connect(self._edited)
            lay.addWidget(QLabel(lbl))
            lay.addWidget(w)
        self.bar = ButtonBar([("WholeNet", tr("rng.whole_net"))])
        self.bar.action.connect(lambda _a: self.whole_net())
        lay.addWidget(self.bar)
        self.sum = QLabel("")
        lay.addWidget(self.sum, 1)
        self._updating = False

    def _edited(self, _t: str = "") -> None:
        if not self._updating:
            self.changed.emit()

    def set_editable(self, on: bool) -> None:
        self.start.setReadOnly(not on)
        self.end.setReadOnly(not on)

    def set_pool(self, start: int | None, end: int | None) -> None:
        self._updating = True
        self.start.setText(ip.int2ip(start) if start is not None else "")
        self.end.setText(ip.int2ip(end) if end is not None else "")
        self._updating = False

    def set_ranges(self, ranges: list[tuple[int, int]]) -> None:
        """Ältere Aufrufer: Pool = erste bis letzte Adresse."""
        self.set_pool(ranges[0][0] if ranges else None, ranges[-1][1] if ranges else None)

    def texts(self) -> tuple[str, str]:
        return self.start.text().strip(), self.end.text().strip()

    def items(self) -> list[tuple[int, str, str]]:
        s, e = self.texts()
        return [(0, s, e)] if s or e else []

    def pool(self) -> tuple[int, int] | None:
        s, e = self.texts()
        if ip.is_ipv4(s) and ip.is_ipv4(e):
            a, b = ip.ip2int(s), ip.ip2int(e)
            return (a, b) if a <= b else (b, a)
        return None

    def merged(self) -> list[tuple[int, int]]:
        p = self.pool()
        return [p] if p else []

    # ----------------------------------------------------------------------------------------------
    def whole_net(self) -> None:
        if not self.model or self.model.hosts < 1:
            return
        self.set_pool(self.model.net + 1, self.model.bc - 1)
        self.changed.emit()

    def swap(self, _row: int = 0) -> None:
        s, e = self.texts()
        self._updating = True
        self.start.setText(e)
        self.end.setText(s)
        self._updating = False
        self.changed.emit()

    def clip(self) -> None:
        """Pool auf die nutzbaren Adressen des Netzes kürzen (ohne Netz- und Broadcastadresse)."""
        p = self.pool()
        if not self.model or not p:
            return
        s, e = max(p[0], self.model.net + 1), min(p[1], self.model.bc - 1)
        if s <= e:
            self.set_pool(s, e)
            self.changed.emit()

    def merge(self) -> None:
        pass

    def show_result(self, counts: dict[int, int], total: int, index: dict[str, list[ck.Finding]], flt) -> None:
        """Adressanzahl und Feldfarbe nach Befunden."""
        fs = [f for f in index.get("Range:0", []) + index.get("Ranges", []) if flt.marker(f)]
        lvl = ck.worst(fs)
        css = f"background:{tint(level_color(lvl), 60).name(QColor.NameFormat.HexArgb)};" if lvl else ""
        tip = "\n".join(dict.fromkeys(f.text for f in fs))
        for w in (self.start, self.end):
            w.setStyleSheet(css)
            w.setToolTip(tip)
        self.sum.setText(self.tr("pool.sum", n=total) if total else "")


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
    """Optionswerte eines Scopes oder des Servers mit Schaltflächen; Aktionen gehen als Signal an den Besitzer.
    Auf Serverebene zusätzlich die Spalte „Abgleich“ (Stand gegenüber dem Failover-Partner) und „Auf Partner
    übertragen“ – bewusst nur für einen einzelnen Optionswert."""

    action = Signal(str)

    def __init__(self, tr, server_level: bool = False, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.server_level = server_level
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        acts = [("Add", tr("opt.add"), "Ins"), ("Edit", tr("opt.edit"), "F2"), ("Remove", tr("opt.remove"), "Del"), "-",
                ("Copy", tr("ui.copy"), "Ctrl+C"), ("Paste", tr("ui.paste"), "Ctrl+V"), ("CopyCell", tr("ui.copy_cell"), "")]
        if server_level:
            acts += ["-", ("ToPartner", tr("opt.to_partner_one"), "")]
        cols = [("id", tr("opt.col.id"), "opt"), ("name", tr("opt.col.name"), "text"), ("value", tr("opt.col.value"), "text"),
                ("vendor", tr("opt.col.vendor"), "text"), ("user", tr("opt.col.user"), "text")]
        if server_level:
            cols.append(("sync_t", tr("opt.col.sync"), "text"))
        self.grid = Grid(cols, key_fn=opt_row_key, actions=acts, default_action="Edit", stretch="value")
        self.grid.action.connect(self.action.emit)
        lay.addWidget(self.grid, 1)
        btns = [("Add", tr("opt.add")), ("Edit", tr("opt.edit")), ("Remove", tr("opt.remove")), ("Copy", tr("ui.copy")),
                ("Paste", tr("ui.paste"))]
        if server_level:
            btns.append(("ToPartner", tr("opt.to_partner_one")))
        self.bar = ButtonBar(btns)
        self.bar.action.connect(self.action.emit)
        self.bar.add_widget(help_icon(tr("opt.server_note") if server_level else tr("opt.scope_note")))
        lay.addWidget(self.bar)
        if server_level:
            self.grid.itemSelectionChanged.connect(self._sel_changed)
            self._sel_changed()

    def _sel_changed(self) -> None:
        rows = self.grid.selected_rows()
        one = len(rows) == 1 and not rows[0].get("ghost")
        self.bar.buttons["ToPartner"].setEnabled(one and self.grid.has_action("ToPartner"))

    def set_options(self, options: list[dict], defs: dict) -> None:
        self.set_rows(option_rows(options, defs))

    def set_rows(self, rows: list[dict]) -> None:
        self.grid.set_rows(rows)
        self.grid.setColumnWidth(0, 70)
        self.grid.setColumnWidth(1, 220)
        for c in (3, 4):
            self.grid.resizeColumnToContents(c)
        if self.server_level:
            c = theme.current
            for r in rows:
                k = opt_row_key(r)
                col = {"sync": c["success"], "diff": c["danger"], "missing": c["warning"], "ghost": c["warning"]}.get(r.get("sync"))
                if col:
                    self.grid.style_cell(k, "sync_t", fore=col, bold=r.get("sync") != "sync")
                if r.get("ghost"):
                    for ck_ in ("id", "name", "value", "vendor", "user"):
                        self.grid.style_cell(k, ck_, fore=c["muted"])
            self._sel_changed()

    def mark(self, index: dict[str, list[ck.Finding]], flt) -> None:
        for r in self.grid.rows:
            k = opt_row_key(r)
            fs = [f for f in index.get(k, []) if flt.marker(f)]
            lvl = ck.worst(fs)
            self.grid.style_row(k, tint(level_color(lvl), 60) if lvl else None,
                                theme.current["muted"] if r.get("ghost") else None, False,
                                "\n".join(f.text for f in fs) if fs else "",
                                col_keys=["id", "name", "value", "vendor", "user"])

    def apply_rights(self, rw: bool, to_partner: bool) -> None:
        for aid in ("Add", "Edit", "Remove", "Paste"):
            self.bar.set_visible(aid, rw)
            self.grid.set_action_visible(aid, rw)
        if self.server_level:
            self.bar.set_visible("ToPartner", to_partner)
            self.grid.set_action_visible("ToPartner", to_partner)
            self._sel_changed()


def muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.current['muted']};")
    return lbl


def color_text(text: str, color: str) -> str:
    return f"<span style='color:{QColor(color).name()}'>{text}</span>"
