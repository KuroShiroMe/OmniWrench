"""Tab einer Zone: Einträge, Allgemein (Zoneneinstellungen, SOA, Übertragungen), Befunde, Aufräum-Vorschau."""

from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from . import checks as ck
from . import dialogs as dlg
from . import dnsutil as du
from .runner import Job
from .ui_base import (
    ButtonBar, FindingsView, Grid, bold_label, confirm, finding_tip, help_icon, hint_label, info, level_color,
    level_icon, short_list, tint, warn,
)


class ZoneTab(QWidget):
    changed = Signal()

    def __init__(self, ctl, server: str, zone: str, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.svc = ctl.svc
        tr = self.tr = ctl.tr
        self.server = server
        self.zone = zone
        self.findings: list[ck.Finding] = []
        self.preview: list[dict] = []
        self.alive: dict[str, bool | None] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        self.title = bold_label(zone)
        f = self.title.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        self.title.setFont(f)
        head.addWidget(self.title)
        self.meta = QLabel("")
        self.meta.setStyleSheet(f"color:{theme.current['muted']};")
        head.addWidget(self.meta, 1)
        lay.addLayout(head)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_records(), tr("zt.records"))
        # eigener Scrollbereich: sonst bestimmt die hohe Seite die Mindesthöhe des ganzen Zonen-Tabs, und die
        # Knöpfe unter der Eintragsliste rutschen aus dem sichtbaren Bereich (Dock scrollt dann den ganzen Tab)
        general = QScrollArea()
        general.setWidgetResizable(True)
        general.setFrameShape(QFrame.Shape.NoFrame)
        general.setWidget(self._build_general())
        self.tabs.addTab(general, tr("zt.general"))
        self.find_view = FindingsView(tr, ctl.flt)
        self.find_view.activated.connect(self._finding)
        self.tabs.addTab(self.find_view, tr("zt.findings"))
        self.tabs.addTab(self._build_scavenge(), tr("zt.scavenge"))
        lay.addWidget(self.tabs, 1)

    # --- Aufbau -------------------------------------------------------------------------------------
    def _build_records(self) -> QWidget:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("zt.filter"))
        self.filter.setClearButtonEnabled(True)
        top.addWidget(self.filter, 1)
        self.type_filter = QComboBox()
        self.type_filter.addItem(tr("zt.all_types"), "")
        top.addWidget(self.type_filter)
        self.only_find = QCheckBox(tr("zt.only_findings"))
        top.addWidget(self.only_find)
        self.count = QLabel("")
        self.count.setStyleSheet(f"color:{theme.current['muted']};")
        top.addWidget(self.count)
        lay.addLayout(top)
        # Replikation: Stand auf den weiteren verbundenen Servern (nur sichtbar, wenn es welche gibt)
        self.repl_row = QWidget()
        rr = QHBoxLayout(self.repl_row)
        rr.setContentsMargins(0, 0, 0, 0)
        self.repl_lbl = hint_label("")
        self.repl_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rr.addWidget(self.repl_lbl, 1)
        self.repl_bar = ButtonBar([("ReplCheck", tr("zr.check")), ("Repl", tr("zr.trigger"))])
        self.repl_bar.buttons["ReplCheck"].setToolTip(tr("zr.check_tip"))
        self.repl_bar.buttons["Repl"].setToolTip(tr("zr.trigger_tip"))
        self.repl_bar.action.connect(self._action)
        rr.addWidget(self.repl_bar, 0, Qt.AlignmentFlag.AlignTop)
        self.repl_row.setVisible(False)
        lay.addWidget(self.repl_row)
        acts = [("Edit", tr("zt.edit"), ""), ("New", tr("zt.new"), "Ins"), "-", ("Ttl", tr("zt.ttl"), ""),
                ("Static", tr("zt.static"), ""), ("Ptr", tr("zt.ptr"), ""), "-", ("Delete", tr("zt.delete"), "Del"), "-",
                ("CopyRows", tr("zt.copy_rows"), "Ctrl+Shift+C"), ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.grid = Grid([("node", tr("zt.col.name"), "text"), ("type", tr("zt.col.type"), "text"),
                          ("value", tr("zt.col.value"), "text"), ("ttl_t", tr("zt.col.ttl"), "text"),
                          ("ts_t", tr("zt.col.ts"), "text"), ("age", tr("zt.col.age"), "int"),
                          ("repl", tr("zt.col.repl"), "text"), ("find", tr("zt.col.findings"), "text")],
                         key_fn=lambda r: r["key"], actions=acts, default_action="Edit", stretch="value")
        self.grid.enable_layout(self.ctl.settings, "zone_columns", labels=(tr("ui.columns"), tr("ui.columns_reset")))
        self.grid.action.connect(self._action)
        lay.addWidget(self.grid, 1)
        self.bar = ButtonBar([("Reload", tr("ui.refresh")), ("New", tr("zt.new")), ("Edit", tr("zt.edit")),
                              ("Delete", tr("zt.delete")), ("Ttl", tr("zt.ttl")), ("Static", tr("zt.static")),
                              ("Ptr", tr("zt.ptr"))], primary=("New",))
        self.bar.action.connect(self._action)
        lay.addWidget(self.bar)
        self.filter.textChanged.connect(lambda t: (self.grid.apply_filter(t, ["node", "type", "value", "name"]), self._count()))
        self.type_filter.currentIndexChanged.connect(lambda _i: self.fill())
        self.only_find.toggled.connect(lambda _on: self.fill())
        return w

    def _build_general(self) -> QWidget:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        info_box = QGroupBox(tr("zg.info"))
        fi = QFormLayout(info_box)
        self.g_type = QLabel("")
        self.g_store = QLabel("")
        self.g_state = QLabel("")
        self.g_masters = QLabel("")
        self.g_masters.setWordWrap(True)
        self.g_xfr = QLabel("")
        for lbl, wid in ((tr("zg.type"), self.g_type), (tr("zg.store"), self.g_store), (tr("zg.state"), self.g_state),
                         (tr("zg.masters"), self.g_masters), (tr("zg.last_xfr"), self.g_xfr)):
            wid.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            fi.addRow(lbl, wid)
        lay.addWidget(info_box)
        soa_box = QGroupBox(tr("zg.soa"))
        fs = QFormLayout(soa_box)
        self.g_soa = {}
        for key in ("serial", "primary", "responsible", "refresh", "retry", "expire", "minimum"):
            lbl = QLabel("")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.g_soa[key] = lbl
            fs.addRow(tr(f"zg.soa.{key}"), lbl)
        lay.addWidget(soa_box)
        set_box = QGroupBox(tr("zg.settings"))
        fz = QFormLayout(set_box)
        self.g_update = QComboBox()
        for v in (du.UPDATE_SECURE, du.UPDATE_ANY, du.UPDATE_NONE):
            self.g_update.addItem(tr(f"upd.{v}"), v)
        fz.addRow(tr("zg.updates"), self._with_marker(self.g_update, "Field:Update"))
        self.g_aging = QCheckBox(tr("zg.aging"))
        fz.addRow("", self._with_marker(self.g_aging, "Field:Aging"))
        self.g_norefresh = QSpinBox()
        self.g_refresh = QSpinBox()
        for sp in (self.g_norefresh, self.g_refresh):
            sp.setRange(1, 8760 * 4)
            sp.setSuffix(" h")
            sp.setMaximumWidth(140)
        fz.addRow(tr("zg.norefresh"), self._hint_row(self.g_norefresh, tr("zg.norefresh_hint")))
        fz.addRow(tr("zg.refresh"), self._hint_row(self.g_refresh, tr("zg.refresh_hint")))
        self.g_scav_after = QLabel("")
        fz.addRow(tr("zg.scavenge_after"), self.g_scav_after)
        lay.addWidget(set_box)
        xf_box = QGroupBox(tr("zg.transfers"))
        fx = QFormLayout(xf_box)
        self.g_xfer = QComboBox()
        for v in (du.XFER_NONE, du.XFER_NS, du.XFER_LIST, du.XFER_ANY):
            self.g_xfer.addItem(tr(f"xfer.{v}"), v)
        fx.addRow(tr("zg.xfer"), self._with_marker(self.g_xfer, "Field:Transfers"))
        self.g_secondaries = QLineEdit()
        self.g_secondaries.setPlaceholderText(tr("zg.ip_list_ph"))
        fx.addRow(tr("zg.secondaries"), self.g_secondaries)
        self.g_notify = QComboBox()
        for v in (du.NOTIFY_NS, du.NOTIFY_LIST, du.NOTIFY_OFF):
            self.g_notify.addItem(tr(f"notify.{v}"), v)
        fx.addRow(tr("zg.notify"), self.g_notify)
        self.g_notify_list = QLineEdit()
        self.g_notify_list.setPlaceholderText(tr("zg.ip_list_ph"))
        fx.addRow(tr("zg.notify_list"), self.g_notify_list)
        lay.addWidget(xf_box)
        self.g_bar = ButtonBar([("Apply", tr("zg.apply")), ("Revert", tr("zg.revert")), ("Pause", tr("zact.pause")),
                                ("Resume", tr("zact.resume")), ("ReloadZone", tr("zact.reload")),
                                ("Transfer", tr("zact.refresh")), ("FromDs", tr("zact.from_ds")),
                                ("WriteBack", tr("zact.write_back")), ("DeleteZone", tr("zg.delete_zone"))],
                               primary=("Apply",))
        self.g_bar.action.connect(self._g_action)
        lay.addWidget(self.g_bar)
        lay.addStretch(1)
        self.g_aging.toggled.connect(self._aging_toggled)
        self.g_xfer.currentIndexChanged.connect(lambda _i: self._xfer_toggled())
        self.g_notify.currentIndexChanged.connect(lambda _i: self._xfer_toggled())
        return w

    def _with_marker(self, w: QWidget, key: str) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w)
        m = self.ctl.markers_for(self).add(key, w)
        if m is not None:
            h.addWidget(m)
        h.addStretch(1)
        return box

    def _hint_row(self, w: QWidget, hint: str) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w)
        h.addWidget(help_icon(hint))
        h.addStretch(1)
        return box

    def _build_scavenge(self) -> QWidget:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        self.sc_info = hint_label("")
        lay.addWidget(self.sc_info)
        self.sc_grid = Grid([("node", tr("zt.col.name"), "text"), ("type", tr("zt.col.type"), "text"),
                             ("value", tr("zt.col.value"), "text"), ("ts_t", tr("zt.col.ts"), "text"),
                             ("age", tr("zt.col.age"), "int"), ("due_t", tr("sc.col.due"), "text"),
                             ("alive_t", tr("sc.col.alive"), "text"), ("dhcp_t", tr("sc.col.dhcp"), "text")],
                            key_fn=lambda r: r["key"],
                            actions=[("ScDelete", tr("sc.delete"), "Del"), ("ScStatic", tr("zt.static"), ""), "-",
                                     ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")], stretch="value")
        self.sc_grid.action.connect(self._sc_action)
        lay.addWidget(self.sc_grid, 1)
        self.sc_bar = ButtonBar([("ScPing", tr("sc.ping")), ("ScDelete", tr("sc.delete")),
                                 ("ScStatic", tr("zt.static"))])
        self.sc_bar.action.connect(self._sc_action)
        lay.addWidget(self.sc_bar)
        return w

    # --- Daten --------------------------------------------------------------------------------------
    @property
    def z(self) -> dict:
        return self.svc.zones.get(self.server, {}).get(self.zone) or {"name": self.zone, "type": -1}

    def recs(self) -> list[du.Rec]:
        return self.svc.records(self.server, self.zone) or []

    def writable(self) -> bool:
        return self.z.get("type") == du.ZONE_PRIMARY

    def set_data(self) -> None:
        """Nach dem Laden/Neuladen: alles neu aufbauen."""
        tr = self.tr
        z = self.z
        recs = self.recs()
        c = self.svc.cache.get((self.server, self.zone)) or {}
        types = sorted({r.type for r in recs})
        cur = self.type_filter.currentData()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem(tr("zt.all_types"), "")
        for t in types:
            self.type_filter.addItem(f"{t} ({sum(1 for r in recs if r.type == t)})", t)
        self.type_filter.setCurrentIndex(max(0, self.type_filter.findData(cur)))
        self.type_filter.blockSignals(False)
        loaded = c.get("loaded")
        self.meta.setText(tr("zt.meta", type=tr(f"ztype.{du.ZONE_TYPE_KEYS.get(z.get('type'), 'primary')}"),
                             server=self.server, n=len(recs), serial=c.get("serial") or "–",
                             time=du.fmt_local(loaded) if loaded else "–")
                          + ("  ·  " + tr("zt.ad") if z.get("ds") else ""))
        self.recheck()
        self.fill_general()
        self.apply_rights()
        self._repl_ui()
        if (self.server, self.zone) not in self.svc.repl:
            self.ctl.repl_check(self.server, self.zone)

    def recheck(self) -> None:
        self.findings = self.svc.zone_findings(self.server, self.zone)
        self.find_view.set_findings(self.findings)
        self.preview = ck.scavenge_preview(self.z, self.recs(), self.svc.servers.get(self.server))
        self.ctl.markers_for(self).update(ck.index_by_target(self.findings))
        n_bad = sum(1 for f in self.findings if f.level in (ck.ERROR, ck.WARN))
        self.tabs.setTabText(2, self.tr("zt.findings_n", n=len(self.findings)) if self.findings else self.tr("zt.findings"))
        self.tabs.setTabIcon(2, level_icon(ck.worst(self.findings)) if n_bad else level_icon(None))
        self.tabs.setTabText(3, self.tr("zt.scavenge_n", n=len(self.preview)) if self.preview else self.tr("zt.scavenge"))
        self.fill()
        self.fill_scavenge()

    # --- Replikation ----------------------------------------------------------------------------------
    def _repl_ui(self) -> None:
        svc = self.svc
        peers = svc.repl_peers(self.server, self.zone)
        others = svc._unconnected_secondaries(self.server, self.zone)
        self.repl_row.setVisible(bool(peers or others))
        self.repl_bar.set_visible("Repl", bool(peers))
        self.grid.setColumnHidden(self._col("repl"), not peers or self._repl_hidden_by_user())
        self.repl_lbl.setText(self._repl_text(svc.repl.get((self.server, self.zone))))

    def _col(self, key: str) -> int:
        return next(i for i, c in enumerate(self.grid.cols) if c[0] == key)

    def _repl_hidden_by_user(self) -> bool:
        saved = self.ctl.settings.get("zone_columns") or {}
        return isinstance(saved, dict) and "repl" in (saved.get("hidden") or [])

    def repl_busy(self, on: bool) -> None:
        self.repl_bar.buttons["ReplCheck"].setEnabled(not on)
        if on:
            self.repl_lbl.setText(self.tr("zr.checking"))

    def set_repl(self, st: dict | None) -> None:
        self.repl_bar.buttons["ReplCheck"].setEnabled(True)
        self._repl_ui()
        self.fill()

    def _repl_text(self, st: dict | None) -> str:
        tr = self.tr
        if st is None:
            return tr("zr.unknown")
        diff = self.svc.repl_diff(st)
        parts = []
        for p, e in st["peers"].items():
            short = p.split(".")[0]
            if not e["ok"]:
                parts.append(tr("zr.peer_err", server=short, error=(e["error"].splitlines() or ["?"])[0][:160]))
                continue
            miss, extra = len(diff["missing"].get(p, ())), len(diff["extra"].get(p, ()))
            diffs = ([tr("zr.peer_missing", n=miss)] if miss else []) + ([tr("zr.peer_extra", n=extra)] if extra else [])
            line = f"{short}: " + ", ".join(diffs) if diffs else tr("zr.peer_ok", server=short)
            if not st["ds"]:
                line += ", " + tr("zr.serial", serial=e.get("serial") or "–")
                if e.get("type") == du.ZONE_SECONDARY:
                    line += ", " + tr("zr.last_xfr", time=du.fmt_local(e.get("last_xfr")) or tr("zr.never"))
            parts.append(line)
        for o in st["others"]:
            parts.append(tr("zr.other", ip=o["ip"], serial=o["serial"]) if o["ok"]
                         else tr("zr.other_err", ip=o["ip"], error=o["error"] or "?"))
        head = tr("zr.head_ad") if st["ds"] else tr("zr.head_file", serial=st.get("serial") or "–")
        return f"{head} ({du.fmt_local(st['time'])}): " + "  ·  ".join(parts)

    def _repl_cell(self, r: du.Rec) -> tuple[str, dict | None]:
        if r.type == "SOA":
            return "", None
        x = self.svc.repl_of(self.svc.repl.get((self.server, self.zone)), r.key)
        if x is None:
            return "", None
        n = len(x["have"]) + len(x["missing"])
        text = f"{len(x['have'])}/{n}" + (" ?" if x["unknown"] else "")
        return ("✓ " + text if not x["missing"] else text), x

    def _repl_tip(self, x: dict | None) -> str:
        if not x:
            return ""
        tr = self.tr
        short = lambda lst: ", ".join(s.split(".")[0] for s in lst)  # noqa: E731
        out = [tr("zr.tip_have", list=short(x["have"]))]
        if x["missing"]:
            out.append(tr("zr.tip_missing", list=short(x["missing"])))
        if x["unknown"]:
            out.append(tr("zr.tip_unknown", list=short(x["unknown"])))
        return "\n".join(out)

    def _row(self, r: du.Rec, fidx: dict, now: _dt.datetime) -> dict:
        fs = fidx.get(ck.rec_target(r), [])
        repl_t, repl = self._repl_cell(r)
        ip = du.ip_from_ptr(r.name) if r.type == "PTR" else None
        # Reverse-Zonen: Adresse statt Nibble-/Oktett-Name anzeigen (voller Name steht im Tooltip)
        return {"key": r.key, "node": ip or r.node, "name": r.name, "type": r.type, "value": r.value,
                "ttl_t": du.fmt_ttl(r.ttl), "ts_t": du.fmt_local(r.ts) if r.ts else self.tr("zt.static_t"),
                "age": (now - r.ts).days if r.ts else None,
                "find": "; ".join(f.text for f in fs[:2]) + (" …" if len(fs) > 2 else ""), "_rec": r, "_find": fs,
                "repl": repl_t, "_repl": repl}

    def fill(self) -> None:
        recs = self.recs()
        t = self.type_filter.currentData()
        fidx = ck.index_by_target(self.findings)
        now = du.now_utc()
        rows = []
        def order(x: du.Rec):
            ip = du.ip_from_ptr(x.name) if x.type == "PTR" else None
            return (x.name != self.zone, du.ip_sort_key(ip) if ip else (), x.node.lower(), x.type)
        for r in sorted(recs, key=order):
            if t and r.type != t:
                continue
            row = self._row(r, fidx, now)
            if self.only_find.isChecked() and not row["_find"]:
                continue
            rows.append(row)
        self.grid.set_rows(rows)
        c = theme.current
        for row in rows:
            lvl = ck.worst([f for f in row["_find"] if self.ctl.flt.marker(f)])
            if lvl:
                self.grid.style_row(row["key"], back=tint(level_color(lvl), 40))
                self.grid.style_cell(row["key"], "find", fore=level_color(lvl), back=tint(level_color(lvl), 40),
                                     bold=lvl == ck.ERROR)
            if row["_rec"].type == "SOA":
                self.grid.style_row(row["key"], fore=c["muted"])
            if row["_repl"] and row["_repl"]["missing"]:
                self.grid.style_cell(row["key"], "repl", fore=c["warning"], bold=True)
        self.grid.set_tooltips(lambda r: (r["name"] + "\n" + r["_rec"].text + (
            "\n\n" + finding_tip(self.tr, r["_find"]) if r["_find"] else "") + (
            "\n\n" + self._repl_tip(r["_repl"]) if r["_repl"] else "")).strip())
        self.grid.autosize(320)
        self.grid.apply_filter(self.filter.text(), ["node", "type", "value", "name"])
        self._count()

    def _count(self) -> None:
        self.count.setText(self.tr("zt.count", shown=len(self.grid.visible_rows()), total=len(self.recs())))

    def fill_general(self) -> None:
        tr = self.tr
        z = self.z
        self.g_type.setText(tr(f"ztype.{du.ZONE_TYPE_KEYS.get(z.get('type'), 'primary')}")
                            + ("  ·  " + tr("zg.reverse_net", net=du.reverse_zone_network(self.zone))
                               if du.is_reverse_zone(self.zone) and du.reverse_zone_network(self.zone) else ""))
        self.g_store.setText(tr("zg.store_ad") if z.get("ds") else tr("zg.store_file", file=z.get("data_file") or "–"))
        st = [tr("zg.paused")] if z.get("paused") else []
        if z.get("shutdown"):
            st.append(tr("zg.shutdown"))
        self.g_state.setText(", ".join(st) or tr("zg.running"))
        self.g_masters.setText(", ".join(z.get("masters") or []) or "–")
        if z.get("type") in (du.ZONE_SECONDARY, du.ZONE_STUB):
            self.g_xfr.setText(tr("zg.last_xfr_v", xfr=du.fmt_local(z.get("last_xfr")) or tr("zr.never"),
                                  soa=du.fmt_local(z.get("last_soa_check")) or tr("zr.never")))
        else:
            self.g_xfr.setText("–")
        soa = next((r for r in self.recs() if r.type == "SOA"), None)
        d = soa.data if soa else {}
        for key, lbl in self.g_soa.items():
            v = d.get(key)
            lbl.setText("–" if v in (None, "") else du.fmt_ttl(v) if key in ("refresh", "retry", "expire", "minimum")
                        else str(v))
        self._loading = True
        self.g_update.setCurrentIndex(max(0, self.g_update.findData(z.get("allow_update", 0))))
        self.g_aging.setChecked(bool(z.get("aging")))
        self.g_norefresh.setValue(int(z.get("norefresh_h") or 168))
        self.g_refresh.setValue(int(z.get("refresh_h") or 168))
        sa = z.get("scavenge_after")
        self.g_scav_after.setText(du.fmt_local(sa) if sa and z.get("aging") else "–")
        self.g_xfer.setCurrentIndex(max(0, self.g_xfer.findData(z.get("secure_secondaries", du.XFER_NONE))))
        self.g_secondaries.setText(", ".join(z.get("secondaries") or []))
        self.g_notify.setCurrentIndex(max(0, self.g_notify.findData(z.get("notify", du.NOTIFY_OFF))))
        self.g_notify_list.setText(", ".join(z.get("notify_servers") or []))
        self._loading = False
        self._aging_toggled(self.g_aging.isChecked())
        self._xfer_toggled()

    def _aging_toggled(self, on: bool) -> None:
        self.g_norefresh.setEnabled(on and self.writable())
        self.g_refresh.setEnabled(on and self.writable())

    def _xfer_toggled(self) -> None:
        self.g_secondaries.setEnabled(self.g_xfer.currentData() == du.XFER_LIST and self.can_transfer())
        self.g_notify_list.setEnabled(self.g_notify.currentData() == du.NOTIFY_LIST and self.can_transfer())

    def can_transfer(self) -> bool:
        return self.z.get("type") in (du.ZONE_PRIMARY, du.ZONE_SECONDARY)

    def apply_rights(self) -> None:
        """Nur Primärzonen sind beschreibbar; Sekundär/Stub/Weiterleitung zeigen nur an."""
        rw = self.writable()
        zt = self.z.get("type")
        for aid in ("New", "Edit", "Delete", "Ttl", "Static", "Ptr"):
            self.bar.set_visible(aid, rw)
            self.grid.set_action_visible(aid, rw)
        self.sc_bar.set_visible("ScDelete", rw)
        self.sc_bar.set_visible("ScStatic", rw)
        for wdg in (self.g_update, self.g_aging):
            wdg.setEnabled(rw)
        for wdg in (self.g_xfer, self.g_notify):
            wdg.setEnabled(self.can_transfer())
        self._aging_toggled(self.g_aging.isChecked())
        self._xfer_toggled()
        self.g_bar.set_visible("Apply", rw or self.can_transfer())
        self.g_bar.set_visible("Revert", rw or self.can_transfer())
        self.g_bar.set_visible("Pause", not self.z.get("paused") and zt in (du.ZONE_PRIMARY, du.ZONE_SECONDARY, du.ZONE_STUB))
        self.g_bar.set_visible("Resume", bool(self.z.get("paused")))
        self.g_bar.set_visible("Transfer", zt in (du.ZONE_SECONDARY, du.ZONE_STUB))
        self.g_bar.set_visible("FromDs", bool(self.z.get("ds")))
        self.g_bar.set_visible("WriteBack", not self.z.get("ds") and zt == du.ZONE_PRIMARY)

    def fill_scavenge(self) -> None:
        tr = self.tr
        z = self.z
        leases = self.ctl.dhcp_by_ip()
        rows = []
        for p in self.preview:
            r = p["rec"]
            alive = self.alive.get(r.ip())
            lease = leases.get(r.ip()) if leases is not None else None
            rows.append({"key": r.key, "node": r.node, "type": r.type, "value": r.value, "ts_t": du.fmt_local(r.ts),
                         "age": p["age_days"], "due_t": tr("sc.now") if p["now"] else du.fmt_local(p["due"]),
                         "alive_t": "" if alive is None else tr("sc.alive_yes") if alive else tr("sc.alive_no"),
                         "dhcp_t": "" if leases is None else tr(f"sc.dhcp_{lease['kind']}") if lease else tr("sc.dhcp_none"),
                         "_rec": r, "_alive": alive, "_lease": lease})
        self.sc_grid.set_rows(rows)
        c = theme.current
        for row in rows:
            if row["_alive"]:
                self.sc_grid.style_cell(row["key"], "alive_t", fore=c["warning"], bold=True)
            if row["_lease"]:
                self.sc_grid.style_cell(row["key"], "dhcp_t", fore=c["warning"], bold=True)
        self.sc_grid.autosize(320)
        srv = self.svc.servers.get(self.server, {})
        if not z.get("aging"):
            text = tr("sc.aging_off")
        elif not srv.get("scavenging_hours"):
            text = tr("sc.server_off", n=len(self.preview))
        else:
            text = tr("sc.info", n=len(self.preview), hours=srv.get("scavenging_hours"),
                      span=int(z.get("norefresh_h", 0)) + int(z.get("refresh_h", 0)))
        self.sc_info.setText(text + "  " + tr("sc.hint"))

    # --- Befunde ------------------------------------------------------------------------------------
    def show_findings(self) -> None:
        self.tabs.setCurrentIndex(2)

    def select_key(self, key: str) -> None:
        self.tabs.setCurrentIndex(0)
        if not self.grid.select_key(key):
            self.type_filter.setCurrentIndex(0)
            self.filter.clear()
            self.grid.select_key(key)

    def marker_clicked(self, key: str) -> None:
        self.find_view.set_target(key, key.split(":", 1)[-1])
        self.tabs.setCurrentIndex(2)

    def _finding(self, f: ck.Finding, mode: str) -> None:
        if mode in ("Default", "Fix") and f.fix:
            self.ctl.run(self.fix_flow(f))
            return
        for t in f.targets:
            if t.startswith("Rec:"):
                self.select_key(t[4:])
                return
            if t.startswith("Field:"):
                self.tabs.setCurrentIndex(1)
                return
            if t == "Page:Scavenge":
                self.tabs.setCurrentIndex(3)
                return
            if t.startswith("Page:"):
                self.ctl.show_page(t[5:].lower())
                return

    def fix_flow(self, f: ck.Finding):
        tr = self.tr
        rec: du.Rec = f.fix_arg
        if f.fix == "create_ptr":
            ptr = self.svc.ptr_for(self.server, rec)
            if ptr is None:
                warn(self, tr("zt.ptr"), tr("rec.ptr_no_zone"))
                return
            if not confirm(self, tr("fix.create_ptr"), tr("fix.create_ptr_q", ip=rec.ip(), name=rec.name, zone=ptr.zone)):
                return
            yield from self.ctl.write_flow(self.server, ptr.zone, [], [ptr], tr("fix.create_ptr"),
                                           lambda: self.svc.create_record(self.server, ptr))
        elif f.fix == "delete_rec":
            if not confirm(self, tr("fix.delete_rec"), tr("fix.delete_rec_q", rec=f"{rec.name} {rec.type} {rec.value}",
                                                          reason=f.text)):
                return
            yield from self.ctl.write_flow(self.server, rec.zone, [rec], [], tr("fix.delete_rec"),
                                           lambda: self.svc.delete_record(self.server, rec))

    # --- Aktionen Einträge --------------------------------------------------------------------------
    def _selected(self) -> list[du.Rec]:
        return [r["_rec"] for r in self.grid.selected_rows()]

    def _action(self, a: str) -> None:
        tr = self.tr
        if a == "Reload":
            self.ctl.run(self.ctl.reload_zone_flow(self.server, self.zone))
            return
        if a == "ReplCheck":
            self.ctl.repl_check(self.server, self.zone)
            return
        if a == "Repl":
            self.ctl.run(self.ctl.replicate_flow(self.server, self.zone))
            return
        if a == "CopyRows":
            QApplication.clipboard().setText(self.grid.rows_as_text())
            return
        if not self.writable() and a in ("New", "Edit", "Delete", "Ttl", "Static", "Ptr"):
            if a == "Edit":
                cur = self.grid.current()
                if cur:
                    info(self, tr("zt.readonly_title"), cur["_rec"].text or cur["value"])
            return
        sel = [r for r in self._selected() if r.type != "SOA"]
        if a == "New":
            self.ctl.run(self.edit_flow(None))
        elif a == "Edit":
            cur = self.grid.current()
            if cur and cur["_rec"].type == "SOA":
                self.tabs.setCurrentIndex(1)
            elif cur:
                if cur["_rec"].type not in du.EDIT_TYPES:
                    info(self, tr("zt.readonly_title"), tr("zt.type_readonly", type=cur["_rec"].type) + "\n\n" + cur["_rec"].text)
                    return
                self.ctl.run(self.edit_flow(cur["_rec"]))
        elif a == "Delete" and sel:
            self.ctl.run(self.delete_flow(sel))
        elif a == "Ttl" and sel:
            ttl = dlg.ttl_dialog(self, tr, sel[0].ttl)
            if ttl is not None:
                self.ctl.run(self.ctl.write_flow(self.server, self.zone, sel, [], tr("bulk.ttl_title"),
                                                 lambda: self.svc.bulk_ttl(self.server, [r for r in sel if r.type in du.EDIT_TYPES], ttl)))
        elif a == "Static" and sel:
            dyn = [r for r in sel if r.dynamic and r.type in du.EDIT_TYPES]
            if dyn and confirm(self, tr("zt.static"), tr("bulk.static_q", n=len(dyn), list=short_list(
                    [f"{r.node} {r.type} {r.value}" for r in dyn], 10))):
                self.ctl.run(self.ctl.write_flow(self.server, self.zone, dyn, [], tr("zt.static"),
                                                 lambda: self.svc.bulk_static(self.server, dyn)))
        elif a == "Ptr" and sel:
            self.ctl.run(self.ptr_flow(sel))

    def _reverse_ok(self, ip: str) -> bool:
        return self.svc.ptr_for(self.server, du.Rec(zone=self.zone, name="x", type="AAAA" if ":" in ip else "A",
                                                    data={"ip": ip})) is not None

    def edit_flow(self, old: du.Rec | None):
        tr = self.tr
        res = dlg.RecordDialog.ask(self, tr, self.zone, old, reverse_ok=self._reverse_ok,
                                   rtype=self.type_filter.currentData() or None)
        if not res:
            return
        new, opts = res
        if old is not None and new.same_content(old) and not opts.get("ptr"):
            return
        if old is None and any(r.key == new.key for r in self.recs()):
            warn(self, tr("rec.new_title", zone=self.zone), tr("rec.exists", rec=f"{new.name} {new.type} {new.value}"))
            return
        svc, server = self.svc, self.server
        touched = [old] if old else []
        ptr_new = svc.ptr_for(server, new) if opts.get("ptr") else None
        ptr_old: list[du.Rec] = []
        if ptr_new is not None:
            # PTRs, die durch den neuen ersetzt werden: alter Name/alte Adresse
            names = {new.name} | ({old.name} if old else set())
            ips = {new.ip()} | ({old.ip()} if old and old.ip() else set())
            for ip in ips:
                ptr_old += [p for p in svc.existing_ptrs(server, ip) if p.target() in names and p.key != ptr_new.key]
            have_ptr = any(p.key == ptr_new.key for p in svc.existing_ptrs(server, new.ip()))
        else:
            have_ptr = True

        def write():
            if old is not None:
                svc.delete_record(server, old)
            svc.create_record(server, new)
            for p in ptr_old:
                svc.delete_record(server, p)
            if not have_ptr:
                svc.create_record(server, ptr_new)
        zones = sorted({p.zone for p in ptr_old} | ({ptr_new.zone} if ptr_new is not None else set()))
        title = tr("tx.edit", rec=f"{old.name} {old.type}") if old else tr("tx.create", rec=f"{new.name} {new.type}")
        yield from self.ctl.write_flow(server, self.zone, touched + ptr_old, [new], title, write, extra_zones=zones)

    def delete_flow(self, recs: list[du.Rec]):
        tr = self.tr
        svc, server = self.svc, self.server
        ptrs = []
        for r in recs:
            if r.type in ("A", "AAAA"):
                ptrs += [p for p in svc.existing_ptrs(server, r.ip()) if p.target() == r.name
                         and p.key not in {x.key for x in recs}]
        lines = [f"{r.node} {r.type} {r.value}" for r in recs]
        text = tr("del.records_q", n=len(recs), list=short_list(lines, 12))
        box = None
        if ptrs:
            text += "\n\n" + tr("del.with_ptr_hint", n=len(ptrs))
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(QMessageBox.Icon.Question, tr("zt.delete"), text,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        cb = None
        if ptrs:
            cb = QCheckBox(tr("del.with_ptr", n=len(ptrs)), box)
            cb.setChecked(True)
            box.setCheckBox(cb)
        ok = box.exec() == QMessageBox.StandardButton.Yes
        with_ptr = bool(cb and cb.isChecked())
        box.deleteLater()
        if not ok:
            return
        todo = recs + (ptrs if with_ptr else [])

        def write():
            for r in todo:
                svc.delete_record(server, r)
        yield from self.ctl.write_flow(server, self.zone, todo, [], tr("tx.delete", n=len(todo)), write)

    def ptr_flow(self, recs: list[du.Rec]):
        tr = self.tr
        svc, server = self.svc, self.server
        todo, skip = [], []
        for r in recs:
            if r.type not in ("A", "AAAA"):
                continue
            p = svc.ptr_for(server, r)
            if p is None:
                skip.append(f"{r.node} {r.ip()}: {tr('rec.ptr_no_zone')}")
                continue
            if any(x.target() == r.name for x in svc.existing_ptrs(server, r.ip())):
                continue
            todo.append(p)
        if not todo:
            info(self, tr("zt.ptr"), tr("ptr.nothing") + ("\n\n" + short_list(skip) if skip else ""))
            return
        if not confirm(self, tr("zt.ptr"), tr("ptr.q", n=len(todo), list=short_list(
                [f"{du.ip_from_ptr(p.name)} → {p.target()}" for p in todo], 12))
                + ("\n\n" + tr("ptr.skipped", list=short_list(skip, 5)) if skip else "")):
            return
        zones = sorted({p.zone for p in todo})

        def write():
            for p in todo:
                svc.create_record(server, p)
        yield from self.ctl.write_flow(server, zones[0], [], todo, tr("zt.ptr"), write, extra_zones=zones[1:])

    # --- Aufräum-Vorschau ---------------------------------------------------------------------------
    def _sc_selected(self) -> list[du.Rec]:
        return [r["_rec"] for r in self.sc_grid.selected_rows()]

    def _sc_action(self, a: str) -> None:
        tr = self.tr
        if a == "ScPing":
            ips = [p["rec"].ip() for p in self.preview if p["rec"].ip()]
            if ips:
                self.ctl.ping_many(ips, self._ping_done)
            return
        sel = self._sc_selected()
        if not sel or not self.writable():
            return
        if a == "ScDelete":
            self.ctl.run(self.delete_flow(sel))
        elif a == "ScStatic":
            if confirm(self, tr("zt.static"), tr("bulk.static_q", n=len(sel), list=short_list(
                    [f"{r.node} {r.type} {r.value}" for r in sel], 10))):
                self.ctl.run(self.ctl.write_flow(self.server, self.zone, sel, [], tr("zt.static"),
                                                 lambda: self.svc.bulk_static(self.server, sel)))

    def _ping_done(self, res: dict[str, bool]) -> None:
        self.alive.update(res)
        self.fill_scavenge()

    def _g_action(self, a: str) -> None:
        tr = self.tr
        if a == "Revert":
            self.fill_general()
        elif a == "Apply":
            self.ctl.run(self.apply_flow())
        elif a in ("Pause", "Resume", "ReloadZone", "Transfer", "FromDs", "WriteBack"):
            act = {"Pause": "pause", "Resume": "resume", "ReloadZone": "reload", "Transfer": "refresh",
                   "FromDs": "from_ds", "WriteBack": "write_back"}[a]
            if act == "pause" and not confirm(self, tr("zact.pause"), tr("zact.pause_q", zone=self.zone)):
                return
            self.ctl.run(self.ctl.zone_action_flow(self.server, self.zone, act))
        elif a == "DeleteZone":
            self.ctl.run(self.ctl.delete_zone_flow(self.server, self.zone))

    def _ips(self, text: str) -> list[str] | None:
        out = []
        for x in text.replace(";", ",").replace(" ", ",").split(","):
            if x.strip():
                ip = du.parse_ip(x)
                if not ip:
                    return None
                out.append(ip)
        return out

    def apply_flow(self):
        tr = self.tr
        z = self.z
        values = {}
        if self.writable():
            values = {"allow_update": self.g_update.currentData(), "aging": self.g_aging.isChecked()}
            if self.g_aging.isChecked():
                values["norefresh_h"] = self.g_norefresh.value()
                values["refresh_h"] = self.g_refresh.value()
            values = {k: v for k, v in values.items() if z.get(k) != v}
        sec, notif = self._ips(self.g_secondaries.text()), self._ips(self.g_notify_list.text())
        if sec is None or notif is None:
            warn(self, tr("zg.apply"), tr("val.ip_list"))
            return
        xfer = (self.g_xfer.currentData(), sec, self.g_notify.currentData(), notif)
        xfer_changed = self.can_transfer() and xfer != (z.get("secure_secondaries"), z.get("secondaries"), z.get("notify"),
                                                         z.get("notify_servers"))
        if not values and not xfer_changed:
            info(self, tr("zg.apply"), tr("zg.nothing"))
            return
        if values.get("allow_update") == du.UPDATE_ANY and z.get("ds"):
            if not confirm(self, tr("zg.apply"), tr("zg.insecure_q")):
                return
        if xfer[0] == du.XFER_ANY and not confirm(self, tr("zg.apply"), tr("zg.xfer_any_q")):
            return
        svc, server, zone = self.svc, self.server, self.zone

        def write():
            if values:
                svc.set_zone(server, zone, values)
            if xfer_changed:
                svc.set_transfers(server, zone, *xfer)
        yield from self.ctl.atomic(tr("tx.zone_settings", zone=zone), self.ctl.job_flow(write, tr("status.saving")))
        yield Job(lambda: svc.load_zones(server), tr("status.loading"))
        self.ctl.zone_changed(server, zone)
