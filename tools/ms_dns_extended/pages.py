"""Feste Seiten des Hauptbereichs: Übersicht (Zonen), Server, Suche, Vergleich, Prüfung, Ereignisprotokoll."""

from __future__ import annotations

import datetime as _dt
import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from . import checks as ck
from . import dnsutil as du
from . import eventlog
from .runner import Job
from .ui_base import (
    ButtonBar, FindingsView, Grid, bold_label, confirm, finding_tip, help_icon, hint_label, info, level_color,
    level_name, short_list, warn,
)


def _server_combo(ctl, on_change) -> QComboBox:
    cb = QComboBox()
    cb.setMinimumContentsLength(18)
    cb.currentIndexChanged.connect(lambda _i: on_change())
    return cb


def _fill_servers(cb: QComboBox, servers: list[str], keep: str | None = None) -> None:
    cur = keep or cb.currentData()
    cb.blockSignals(True)
    cb.clear()
    for s in servers:
        cb.addItem(s, s)
    i = cb.findData(cur)
    cb.setCurrentIndex(i if i >= 0 else 0)
    cb.blockSignals(False)


class Tile(QFrame):
    def __init__(self, title: str, color: str):
        super().__init__()
        c = theme.current
        self.setObjectName("dnstile")
        self.setStyleSheet(f"QFrame#dnstile {{ border:1px solid {c['border']}; border-left:4px solid {color};"
                           f" border-radius:6px; background:{c['surface']}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(0)
        t = QLabel(title)
        t.setStyleSheet(f"color:{c['muted']};")
        self.value = QLabel("–")
        f = self.value.font()
        f.setPointSizeF(f.pointSizeF() * 1.7)
        f.setBold(True)
        self.value.setFont(f)
        self.value.setStyleSheet(f"color:{color};")
        lay.addWidget(t)
        lay.addWidget(self.value)


# --- Übersicht ---------------------------------------------------------------------------------------

class OverviewPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("ov.server")))
        self.server = _server_combo(ctl, self.refresh)
        top.addWidget(self.server)
        self.srv_bar = ButtonBar([("AddServer", tr("ov.add_server")), ("RemoveServer", tr("ov.remove_server"))])
        self.srv_bar.action.connect(self._action)
        top.addWidget(self.srv_bar)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("ov.filter"))
        self.filter.setClearButtonEnabled(True)
        top.addWidget(self.filter, 1)
        self.count = QLabel("")
        self.count.setStyleSheet(f"color:{theme.current['muted']};")
        top.addWidget(self.count)
        lay.addLayout(top)
        self.srv_line = QLabel("")
        self.srv_line.setTextFormat(Qt.TextFormat.RichText)
        self.srv_line.setWordWrap(True)
        lay.addWidget(self.srv_line)
        acts = [("Open", tr("ov.open"), ""), ("Reload", tr("ui.refresh"), "F5"), "-", ("NewZone", tr("ov.new_zone"), ""),
                ("DeleteZone", tr("ov.delete_zone"), "Del"), "-", ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.grid = Grid([("name", tr("ov.col.name"), "text"), ("type_t", tr("ov.col.type"), "text"),
                          ("store_t", tr("ov.col.store"), "text"), ("upd_t", tr("ov.col.updates"), "text"),
                          ("aging_t", tr("ov.col.aging"), "text"), ("xfer_t", tr("ov.col.xfer"), "text"),
                          ("n", tr("ov.col.records"), "int"), ("find", tr("ov.col.findings"), "text"),
                          ("state_t", tr("ov.col.state"), "text")],
                         key_fn=lambda r: r["name"], actions=acts, default_action="Open", stretch="find")
        self.grid.enable_layout(ctl.settings, "overview_columns", labels=(tr("ui.columns"), tr("ui.columns_reset")))
        self.grid.action.connect(self._action)
        self.filter.textChanged.connect(lambda t: (self.grid.apply_filter(t), self._count()))
        lay.addWidget(self.grid, 1)
        self.bar = ButtonBar([("Reload", tr("ui.refresh")), ("Open", tr("ov.open")), ("NewZone", tr("ov.new_zone")),
                              ("DeleteZone", tr("ov.delete_zone"))], primary=("NewZone",))
        self.bar.action.connect(self._action)
        lay.addWidget(self.bar)

    def current_server(self) -> str:
        return self.server.currentData() or self.ctl.svc.primary

    def _count(self) -> None:
        self.count.setText(self.tr("ov.count", shown=len(self.grid.visible_rows()), total=len(self.grid.rows)))

    def refresh(self) -> None:
        tr, svc = self.tr, self.ctl.svc
        _fill_servers(self.server, list(svc.servers))
        srv = self.current_server()
        info_ = svc.servers.get(srv, {})
        err = svc.errors.get(srv)
        role = tr("srv.role_dc") if info_.get("ds") else tr("srv.role_member")
        line = tr("ov.server_line", server=html.escape(srv), version=info_.get("version") or "?", role=role,
                  n=len(svc.zones.get(srv, {})))
        if err:
            line += f"<br><span style='color:{theme.current['danger']}'>{html.escape(err)}</span>"
        self.srv_line.setText(line)
        scan = self.ctl.scan_result(srv)
        per_zone: dict[str, list[ck.Finding]] = {}
        for f in (scan or {}).get("findings", []):
            if f.scope_id:
                per_zone.setdefault(f.scope_id, []).append(f)
        rows = []
        for name, z in svc.zones.get(srv, {}).items():
            recs = svc.records(srv, name)
            fs = per_zone.get(name, [])
            cnt = {lv: sum(1 for f in fs if f.level == lv) for lv in (ck.ERROR, ck.WARN)}
            st = [tr("zg.paused")] if z.get("paused") else []
            if z.get("shutdown"):
                st.append(tr("zg.shutdown"))
            rows.append({"name": name, "type_t": tr(f"ztype.{du.ZONE_TYPE_KEYS.get(z['type'], 'primary')}")
                         + (" ↺" if z.get("reverse") else ""),
                         "store_t": tr("ov.ad") if z.get("ds") else tr("ov.file"),
                         "upd_t": tr(f"upd.short.{z.get('allow_update', 0)}") if z["type"] == du.ZONE_PRIMARY else "",
                         "aging_t": (tr("ov.aging_on", h=z.get("norefresh_h", 0) + z.get("refresh_h", 0))
                                     if z.get("aging") else tr("ov.aging_off")) if z["type"] == du.ZONE_PRIMARY else "",
                         "xfer_t": tr(f"xfer.short.{z.get('secure_secondaries', 3)}") if z["type"] in (
                             du.ZONE_PRIMARY, du.ZONE_SECONDARY) else "",
                         "n": len(recs) if recs is not None else None,
                         "find": " · ".join(f"{level_name(tr, lv, cnt[lv] != 1)} {cnt[lv]}" for lv in cnt if cnt[lv]),
                         "state_t": ", ".join(st) or tr("zg.running"), "_z": z, "_find": fs})
        self.grid.set_rows(rows)
        c = theme.current
        for r in rows:
            lvl = ck.worst([f for f in r["_find"] if f.level in (ck.ERROR, ck.WARN)])
            if lvl:
                self.grid.style_cell(r["name"], "find", fore=level_color(lvl), bold=lvl == ck.ERROR)
            if r["_z"].get("paused") or r["_z"].get("shutdown"):
                self.grid.style_cell(r["name"], "state_t", fore=c["danger"], bold=True)
            if r["_z"].get("auto"):
                self.grid.style_row(r["name"], fore=c["muted"])
        self.grid.set_tooltips(lambda r: (r["name"] + ("\n\n" + finding_tip(tr, [f for f in r["_find"] if f.level != ck.INFO], 8)
                                                       if r["_find"] else "")))
        self.grid.autosize(320)
        self.grid.apply_filter(self.filter.text())
        self._count()
        self.srv_bar.set_visible("RemoveServer", srv != svc.primary)

    def _action(self, a: str) -> None:
        srv = self.current_server()
        r = self.grid.current()
        if a == "Open" and r:
            self.ctl.open_zone(srv, r["name"])
        elif a == "Reload":
            self.ctl.run(self.ctl.reload_server_flow(srv))
        elif a == "NewZone":
            self.ctl.run(self.ctl.new_zone_flow(srv))
        elif a == "DeleteZone" and r:
            self.ctl.run(self.ctl.delete_zone_flow(srv, r["name"]))
        elif a == "AddServer":
            self.ctl.run(self.ctl.add_server_flow())
        elif a == "RemoveServer":
            self.ctl.remove_server(srv)


# --- Server ------------------------------------------------------------------------------------------

class ServerPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr("ov.server")))
        self.server = _server_combo(ctl, self.refresh)
        top.addWidget(self.server)
        self.head = QLabel("")
        self.head.setStyleSheet(f"color:{theme.current['muted']};")
        top.addWidget(self.head, 1)
        outer.addLayout(top)
        split = QSplitter(Qt.Orientation.Vertical)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        g1 = QGroupBox(tr("srv.forwarding"))
        f1 = QFormLayout(g1)
        self.fwd = QLineEdit()
        self.fwd.setPlaceholderText(tr("zg.ip_list_ph"))
        f1.addRow(tr("srv.forwarders"), self.fwd)
        self.fwd_timeout = QSpinBox()
        self.fwd_timeout.setRange(1, 15)
        self.fwd_timeout.setSuffix(" s")
        self.fwd_timeout.setMaximumWidth(120)
        f1.addRow(tr("srv.forwarding_timeout"), self.fwd_timeout)
        self.recursion = QCheckBox(tr("srv.recursion"))
        f1.addRow("", self.recursion)
        self.is_slave = QCheckBox(tr("srv.is_slave"))
        f1.addRow("", self.is_slave)
        lay.addWidget(g1)
        g2 = QGroupBox(tr("srv.aging"))
        f2 = QFormLayout(g2)
        self.scav = QSpinBox()
        self.scav.setRange(0, 8760)
        self.scav.setSuffix(" h")
        self.scav.setSpecialValueText(tr("srv.scav_off"))
        self.scav.setMaximumWidth(160)
        row = QHBoxLayout()
        row.addWidget(self.scav)
        row.addWidget(help_icon(tr("srv.scav_hint")))
        row.addStretch(1)
        f2.addRow(tr("srv.scavenging"), row)
        self.def_aging = QCheckBox(tr("srv.default_aging"))
        f2.addRow("", self.def_aging)
        self.def_norefresh = QSpinBox()
        self.def_refresh = QSpinBox()
        for sp in (self.def_norefresh, self.def_refresh):
            sp.setRange(1, 8760 * 4)
            sp.setSuffix(" h")
            sp.setMaximumWidth(140)
        f2.addRow(tr("zg.norefresh"), self.def_norefresh)
        f2.addRow(tr("zg.refresh"), self.def_refresh)
        lay.addWidget(g2)
        g3 = QGroupBox(tr("srv.advanced"))
        f3 = QFormLayout(g3)
        self.flags: dict[str, QCheckBox] = {}
        for key in ("secure_responses", "round_robin", "local_net_priority", "bind_secondaries", "disable_autoreverse",
                    "edns_probes"):
            cb = QCheckBox(tr(f"srv.{key}"))
            self.flags[key] = cb
            f3.addRow("", cb)
        self.addresses = QLabel("")
        self.addresses.setWordWrap(True)
        self.addresses.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f3.addRow(tr("srv.addresses"), self.addresses)
        lay.addWidget(g3)
        self.bar = ButtonBar([("Apply", tr("zg.apply")), ("Revert", tr("zg.revert")), ("TestFwd", tr("srv.test_fwd")),
                              ("Scavenge", tr("srv.scavenge_now")), ("ClearCache", tr("srv.clear_cache")),
                              ("Reload", tr("ui.refresh"))], primary=("Apply",))
        self.bar.action.connect(self._action)
        lay.addWidget(self.bar)
        lay.addStretch(1)
        scroll.setWidget(body)
        split.addWidget(scroll)
        self.find_view = FindingsView(tr, ctl.flt)
        self.find_view.empty_text = tr("srv.no_findings")
        split.addWidget(self.find_view)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        outer.addWidget(split, 1)
        self.fwd_results: dict[str, list[ck.Finding]] = {}
        self.def_aging.toggled.connect(lambda on: (self.def_norefresh.setEnabled(on), self.def_refresh.setEnabled(on)))

    def current_server(self) -> str:
        return self.server.currentData() or self.ctl.svc.primary

    def refresh(self) -> None:
        tr, svc = self.tr, self.ctl.svc
        _fill_servers(self.server, list(svc.servers))
        s = svc.servers.get(self.current_server(), {})
        self.head.setText(tr("srv.head", version=s.get("version") or "?",
                             role=tr("srv.role_dc") if s.get("ds") else tr("srv.role_member")))
        self.fwd.setText(", ".join(s.get("forwarders") or []))
        self.fwd_timeout.setValue(int(s.get("forwarding_timeout") or 3))
        self.recursion.setChecked(not s.get("no_recursion"))
        self.is_slave.setChecked(bool(s.get("is_slave")))
        self.scav.setValue(int(s.get("scavenging_hours") or 0))
        self.def_aging.setChecked(bool(s.get("default_aging")))
        self.def_norefresh.setValue(int(s.get("default_norefresh_h") or 168))
        self.def_refresh.setValue(int(s.get("default_refresh_h") or 168))
        self.def_norefresh.setEnabled(self.def_aging.isChecked())
        self.def_refresh.setEnabled(self.def_aging.isChecked())
        for key, cb in self.flags.items():
            cb.setChecked(bool(s.get(key)))
        listen = s.get("listen_addresses") or []
        self.addresses.setText(tr("srv.addresses_text", all=", ".join(s.get("server_addresses") or []) or "–",
                                  listen=", ".join(listen) if listen else tr("srv.listen_all")))
        self._findings()

    def _findings(self) -> None:
        svc = self.ctl.svc
        srv = self.current_server()
        fs = ck.server_findings(svc.servers.get(srv, {}), list(svc.zones.get(srv, {}).values()), self.tr)
        self.find_view.set_findings(ck.sort_findings(fs + self.fwd_results.get(srv, [])))

    def values(self) -> dict | None:
        ips = []
        for x in self.fwd.text().replace(";", ",").replace(" ", ",").split(","):
            if x.strip():
                ip = du.parse_ip(x)
                if not ip:
                    return None
                ips.append(ip)
        v = {"forwarders": ips, "forwarding_timeout": self.fwd_timeout.value(),
             "no_recursion": not self.recursion.isChecked(), "is_slave": self.is_slave.isChecked(),
             "scavenging_hours": self.scav.value(), "default_aging": self.def_aging.isChecked()}
        if self.def_aging.isChecked():
            v["default_norefresh_h"] = self.def_norefresh.value()
            v["default_refresh_h"] = self.def_refresh.value()
        for key, cb in self.flags.items():
            v[key] = cb.isChecked()
        return v

    def _action(self, a: str) -> None:
        tr, svc = self.tr, self.ctl.svc
        srv = self.current_server()
        if a == "Revert":
            self.refresh()
        elif a == "Reload":
            self.ctl.run(self.ctl.reload_server_flow(srv))
        elif a == "Apply":
            v = self.values()
            if v is None:
                warn(self, tr("zg.apply"), tr("val.ip_list"))
                return
            cur = svc.servers.get(srv, {})
            changed = {k: x for k, x in v.items() if cur.get(k) != x}
            if not changed:
                info(self, tr("zg.apply"), tr("zg.nothing"))
                return
            if changed.get("no_recursion") and not confirm(self, tr("zg.apply"), tr("srv.recursion_off_q")):
                return
            self.ctl.run(self._apply_flow(srv, changed))
        elif a == "TestFwd":
            ips = (self.values() or {}).get("forwarders") or svc.servers.get(srv, {}).get("forwarders") or []
            if not ips:
                info(self, tr("srv.test_fwd"), tr("srv.no_fwd"))
                return
            self.ctl.run(self._test_flow(srv, ips))
        elif a == "Scavenge":
            if confirm(self, tr("srv.scavenge_now"), tr("srv.scavenge_q", server=srv)):
                self.ctl.run(self.ctl.simple_flow(lambda: svc.start_scavenging(srv), tr("srv.scavenge_now")))
        elif a == "ClearCache":
            if confirm(self, tr("srv.clear_cache"), tr("srv.clear_cache_q", server=srv)):
                self.ctl.run(self.ctl.simple_flow(lambda: svc.clear_cache(srv), tr("srv.clear_cache")))

    def _apply_flow(self, srv: str, changed: dict):
        tr, svc = self.tr, self.ctl.svc
        yield from self.ctl.atomic(tr("tx.server_settings", server=srv),
                                   self.ctl.job_flow(lambda: svc.set_server(srv, changed), tr("status.saving")))
        yield Job(lambda: svc.refresh_info(srv), tr("status.loading"))
        self.ctl.refresh_pages()

    def _test_flow(self, srv: str, ips: list[str]):
        tr, svc = self.tr, self.ctl.svc
        res = yield Job(lambda: {ip: svc.backend.probe(ip, "microsoft.com", "A") for ip in ips}, tr("srv.testing"))
        self.fwd_results[srv] = ck.forwarder_findings(srv, res, tr)
        lines = [f"{ip}: " + (tr("srv.fwd_ok", ms=r.get("ms")) if r.get("ok") else tr("srv.fwd_fail", error=r.get("error", "")))
                 for ip, r in res.items()]
        self._findings()
        info(self, tr("srv.test_fwd"), "\n".join(lines))


# --- Suche -------------------------------------------------------------------------------------------

class SearchPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText(tr("se.ph"))
        self.query.setClearButtonEnabled(True)
        self.query.returnPressed.connect(self.run)
        top.addWidget(self.query, 1)
        self.type = QComboBox()
        self.type.addItem(tr("zt.all_types"), "")
        for t in du.EDIT_TYPES + ("SOA",):
            self.type.addItem(t, t)
        top.addWidget(self.type)
        self.server = _server_combo(ctl, lambda: None)
        top.addWidget(self.server)
        self.bar = ButtonBar([("Search", tr("se.search")), ("LoadAll", tr("se.load_all"))], primary=("Search",))
        self.bar.action.connect(self._action)
        top.addWidget(self.bar)
        lay.addLayout(top)
        self.state = hint_label(tr("se.hint"))
        lay.addWidget(self.state)
        acts = [("Open", tr("se.open"), ""), "-", ("Delete", tr("zt.delete"), "Del"), "-",
                ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.grid = Grid([("zone", tr("se.col.zone"), "text"), ("node", tr("zt.col.name"), "text"),
                          ("type", tr("zt.col.type"), "text"), ("value", tr("zt.col.value"), "text"),
                          ("ttl_t", tr("zt.col.ttl"), "text"), ("ts_t", tr("zt.col.ts"), "text")],
                         key_fn=lambda r: r["zone"] + "|" + r["key"], actions=acts, default_action="Open", stretch="value")
        self.grid.action.connect(self._action)
        lay.addWidget(self.grid, 1)

    def refresh(self) -> None:
        _fill_servers(self.server, list(self.ctl.svc.servers))

    def _action(self, a: str) -> None:
        srv = self.server.currentData() or self.ctl.svc.primary
        if a == "Search":
            self.run()
        elif a == "LoadAll":
            self.ctl.run(self.ctl.load_all_zones_flow(srv, then=self.run))
        elif a == "Open":
            r = self.grid.current()
            if r:
                self.ctl.open_zone(srv, r["zone"], select_key=r["key"])
        elif a == "Delete":
            recs = [r["_rec"] for r in self.grid.selected_rows() if r["_rec"].type != "SOA"]
            zones = self.ctl.svc.zones.get(srv, {})
            recs = [r for r in recs if zones.get(r.zone, {}).get("type") == du.ZONE_PRIMARY]
            if recs:
                self.ctl.run(self.ctl.delete_records_flow(srv, recs, after=self.run))

    def run(self) -> None:
        tr, svc = self.tr, self.ctl.svc
        srv = self.server.currentData() or svc.primary
        t = self.type.currentData()
        res = svc.search(self.query.text(), {t} if t else None, srv)
        loaded = sum(1 for (s, _z) in svc.cache if s == srv)
        total = len(svc.zones.get(srv, {}))
        self.state.setText(tr("se.state", n=len(res), loaded=loaded, total=total))
        rows = [{"zone": r.zone, "key": r.key, "node": r.node, "type": r.type, "value": r.value,
                 "ttl_t": du.fmt_ttl(r.ttl), "ts_t": du.fmt_local(r.ts) if r.ts else tr("zt.static_t"), "_rec": r}
                for r in res[:5000]]
        self.grid.set_rows(rows)
        self.grid.autosize(320)


# --- Vergleich ---------------------------------------------------------------------------------------

COMPARE_KEYS = ("version", "ds", "forwarders", "forwarding_timeout", "no_recursion", "is_slave", "scavenging_hours",
                "default_aging", "default_norefresh_h", "default_refresh_h", "secure_responses", "round_robin",
                "local_net_priority", "bind_secondaries", "edns_probes")


class ComparePage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.result: dict | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.bar = ButtonBar([("Compare", tr("cmp.run")), ("AddServer", tr("ov.add_server")),
                              ("Discover", tr("cmp.discover"))], primary=("Compare",))
        self.bar.action.connect(self._action)
        top.addWidget(self.bar)
        self.probe = QCheckBox(tr("cmp.probe"))
        self.probe.setChecked(True)
        self.probe.setToolTip(tr("cmp.probe_tip"))
        top.addWidget(self.probe)
        self.state = hint_label(tr("cmp.hint"))
        top.addWidget(self.state, 1)
        lay.addLayout(top)
        split = QSplitter(Qt.Orientation.Vertical)
        self.settings_grid = Grid([("key_t", tr("cmp.col.setting"), "text")], key_fn=lambda r: r["key"], sortable=False)
        split.addWidget(self.settings_grid)
        self.zone_grid = Grid([("zone", tr("se.col.zone"), "text")], key_fn=lambda r: r["zone"])
        split.addWidget(self.zone_grid)
        self.find_view = FindingsView(tr, ctl.flt, show_scope=True, scope_mode=True)
        self.find_view.empty_text = tr("cmp.none")
        split.addWidget(self.find_view)
        lay.addWidget(split, 1)

    def _action(self, a: str) -> None:
        if a == "Compare":
            self.ctl.run(self.compare_flow())
        elif a == "AddServer":
            self.ctl.run(self.ctl.add_server_flow())
        elif a == "Discover":
            self.ctl.run(self.ctl.discover_flow())

    def compare_flow(self):
        tr, svc = self.tr, self.ctl.svc
        if len(svc.servers) < 2:
            info(self, tr("cmp.title"), tr("cmp.need_two"))
            return
        probe = self.probe.isChecked()
        self.result = yield Job(lambda: svc.compare(probe), tr("cmp.running"))
        self.refresh()

    def refresh(self) -> None:
        tr, svc = self.tr, self.ctl.svc
        servers = list(svc.servers)
        cols = [("key_t", tr("cmp.col.setting"), "text")] + [(f"s{i}", s, "text") for i, s in enumerate(servers)]
        self._regrid(self.settings_grid, cols)
        rows = []
        diff_keys = set()
        for key in COMPARE_KEYS:
            vals = [svc.servers[s].get(key) for s in servers]
            norm = [repr(sorted(v)) if isinstance(v, list) else repr(v) for v in vals]
            row = {"key": key, "key_t": tr(f"srv.{key}")}
            for i, v in enumerate(vals):
                row[f"s{i}"] = ck.fmt_value(v, tr) if v is not None else "–"
            if len(set(norm)) > 1:
                diff_keys.add(key)
            rows.append(row)
        self.settings_grid.set_rows(rows)
        for k in diff_keys:
            self.settings_grid.style_row(k, fore=theme.current["warning"], bold=True)
        self.settings_grid.autosize(300)
        zcols = [("zone", tr("se.col.zone"), "text")] + [(f"s{i}", s, "text") for i, s in enumerate(servers)]
        self._regrid(self.zone_grid, zcols)
        serials = (self.result or {}).get("serials") or {}
        names = sorted({z for s in servers for z in svc.zones.get(s, {})}, key=lambda n: (du.is_reverse_zone(n), n))
        zrows = []
        for n in names:
            row = {"zone": n}
            for i, s in enumerate(servers):
                z = svc.zones.get(s, {}).get(n)
                if z is None:
                    row[f"s{i}"] = "–"
                    continue
                ser = serials.get((s, n))
                kind = tr(f"ztype.short.{du.ZONE_TYPE_KEYS.get(z['type'], 'primary')}") + (" AD" if z.get("ds") else "")
                row[f"s{i}"] = kind + (f" · {ser}" if ser is not None else "")
            zrows.append(row)
        self.zone_grid.set_rows(zrows)
        for row in zrows:
            if any(row.get(f"s{i}") == "–" for i in range(len(servers))):
                self.zone_grid.style_row(row["zone"], fore=theme.current["warning"])
        self.zone_grid.autosize(300)
        fs = (self.result or {}).get("findings")
        if fs is None:
            fs = ck.compare_findings(svc.servers, svc.zones, tr)
        self.find_view.set_findings(ck.sort_findings(fs))
        self.state.setText(tr("cmp.state", n=len(servers)) if len(servers) > 1 else tr("cmp.hint"))

    @staticmethod
    def _regrid(grid: Grid, cols) -> None:
        grid.cols = cols
        grid.setColumnCount(len(cols))
        grid.setHorizontalHeaderLabels([c[1] for c in cols])


# --- Prüfung -----------------------------------------------------------------------------------------

class CheckPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.bar = ButtonBar([("Scan", tr("chk.scan")), ("Dhcp", tr("chk.dhcp_server"))], primary=("Scan",))
        self.bar.action.connect(self._action)
        top.addWidget(self.bar)
        self.cancel_btn = QPushButton(tr("ui.cancel"))
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        top.addWidget(self.cancel_btn)
        self.probe = QCheckBox(tr("chk.probe_ns"))
        self.probe.setChecked(bool(ctl.settings.get("probe_ns", True)))
        self.probe.setToolTip(tr("chk.probe_ns_tip"))
        self.probe.toggled.connect(lambda on: ctl.settings.set("probe_ns", on))
        top.addWidget(self.probe)
        self.with_dhcp = QCheckBox(tr("chk.with_dhcp"))
        self.with_dhcp.setToolTip(tr("chk.with_dhcp_tip"))
        top.addWidget(self.with_dhcp)
        self.state = hint_label(tr("chk.not_run"))
        top.addWidget(self.state, 1)
        self.pbar = QProgressBar()
        self.pbar.setMaximumWidth(240)
        self.pbar.setMaximumHeight(14)
        self.pbar.setTextVisible(False)
        self.pbar.hide()
        top.addWidget(self.pbar)
        lay.addLayout(top)
        tiles = QGridLayout()
        self.tiles: dict[str, Tile] = {}
        for i, lv in enumerate(ck.LEVELS):
            t = Tile(level_name(tr, lv, True), level_color(lv))
            self.tiles[lv] = t
            tiles.addWidget(t, 0, i)
        self.t_zones = Tile(tr("chk.tile_zones"), theme.current["accent"])
        tiles.addWidget(self.t_zones, 0, 4)
        lay.addLayout(tiles)
        self.view = FindingsView(tr, ctl.flt, show_scope=True, scope_mode=True)
        self.view.empty_text = tr("chk.none")
        self.view.activated.connect(self._activated)
        lay.addWidget(self.view, 1)
        self.with_dhcp.setEnabled(False)

    def refresh_dhcp(self) -> None:
        svc = self.ctl.svc
        self.with_dhcp.setEnabled(bool(svc.dhcp_server))
        self.with_dhcp.setText(self.tr("chk.with_dhcp_srv", server=svc.dhcp_server) if svc.dhcp_server
                               else self.tr("chk.with_dhcp"))
        if svc.dhcp_server and not self.with_dhcp.property("set"):
            self.with_dhcp.setChecked(True)
            self.with_dhcp.setProperty("set", True)

    def _action(self, a: str) -> None:
        if a == "Scan":
            self.ctl.start_scan()
        elif a == "Dhcp":
            self.ctl.run(self.ctl.dhcp_setup_flow())

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.state.setText(self.tr("status.cancelling"))
        self.ctl.svc.scan_cancel.set()

    def scan_started(self) -> None:
        self.bar.buttons["Scan"].setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.show()
        self.pbar.setRange(0, 0)
        self.pbar.show()
        self.state.setText(self.tr("chk.running"))

    def scan_progress(self, text: str, i: int, n: int) -> None:
        if text:
            self.state.setText(text)
        if n:
            self.pbar.setRange(0, n)
            self.pbar.setValue(i)

    def scan_stopped(self, text: str = "") -> None:
        self.bar.buttons["Scan"].setEnabled(True)
        self.cancel_btn.hide()
        self.pbar.hide()
        if text:
            self.state.setText(text)

    def set_scan(self, scan: dict | None) -> None:
        tr = self.tr
        if not scan:
            return
        fs = scan.get("findings") or []
        for lv, t in self.tiles.items():
            t.value.setText(str(sum(1 for f in fs if f.level == lv)))
        self.t_zones.value.setText(str(scan.get("zones", 0)))
        self.state.setText(tr("chk.state_partial" if scan.get("partial") else "chk.state", time=scan.get("time", ""),
                              sec=scan.get("seconds", 0), zones=scan.get("zones", 0), records=scan.get("records", 0),
                              server=scan.get("server", "")))
        self.view.set_findings(fs)

    def _activated(self, f: ck.Finding, mode: str) -> None:
        srv = f.server or self.ctl.svc.primary
        if f.scope_id and f.scope_id in self.ctl.svc.zones.get(srv, {}):
            key = next((t[4:] for t in f.targets if t.startswith("Rec:")), None)
            self.ctl.open_zone(srv, f.scope_id, select_key=key, show_findings=key is None)
        elif any(t.startswith("Page:") for t in f.targets):
            self.ctl.show_page(next(t for t in f.targets if t.startswith("Page:"))[5:].lower())


# --- Ereignisprotokoll -------------------------------------------------------------------------------

PERIODS = ((1, "ev.p1h"), (24, "ev.p24h"), (24 * 7, "ev.p7d"), (24 * 30, "ev.p30d"))


class EventsPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self._gen = 0
        self.loaded = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.server = _server_combo(ctl, self.reload)
        top.addWidget(self.server)
        self.period = QComboBox()
        for h, key in PERIODS:
            self.period.addItem(tr(key), h)
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(lambda _i: self.reload())
        top.addWidget(self.period)
        self.zone = QComboBox()
        self.zone.currentIndexChanged.connect(lambda _i: self._fill())
        top.addWidget(self.zone)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("ev.filter"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda _t: self._fill())
        top.addWidget(self.filter, 1)
        self.bar = ButtonBar([("Reload", tr("ui.refresh"))])
        self.bar.action.connect(lambda _a: self.reload())
        top.addWidget(self.bar)
        lay.addLayout(top)
        self.state = QLabel(tr("ev.hint"))
        self.state.setWordWrap(True)
        self.state.setOpenExternalLinks(True)
        self.state.setTextFormat(Qt.TextFormat.RichText)
        self.state.setStyleSheet(f"color:{theme.current['muted']};")
        lay.addWidget(self.state)
        self.grid = Grid([("time", tr("ev.col.time"), "text"), ("user", tr("ev.col.user"), "text"),
                          ("area_t", tr("ev.col.area"), "text"), ("action_t", tr("ev.col.action"), "text"),
                          ("zone", tr("se.col.zone"), "text"), ("obj", tr("ev.col.obj"), "text"),
                          ("text", tr("ev.col.text"), "text"), ("id", tr("ev.col.id"), "int")],
                         key_fn=lambda r: str(r["record"]), actions=[("OpenZone", tr("ev.open_zone"), ""),
                                                                     ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")],
                         default_action="OpenZone", stretch="text")
        self.grid.enable_layout(ctl.settings, "events_columns", labels=(tr("ui.columns"), tr("ui.columns_reset")))
        self.grid.action.connect(self._action)
        lay.addWidget(self.grid, 1)
        self.events: list[dict] = []

    def on_shown(self) -> None:
        if not self.loaded:
            self.reload()

    def set_zone(self, zone: str) -> None:
        i = self.zone.findData(zone)
        if i >= 0:
            self.zone.setCurrentIndex(i)

    def refresh(self) -> None:
        _fill_servers(self.server, list(self.ctl.svc.servers))
        self._fill_zones()

    def _fill_zones(self) -> None:
        cur = self.zone.currentData()
        self.zone.blockSignals(True)
        self.zone.clear()
        self.zone.addItem(self.tr("ev.all_zones"), "")
        for z in self.ctl.svc.zones.get(self.server.currentData() or self.ctl.svc.primary, {}):
            self.zone.addItem(z, z)
        i = self.zone.findData(cur)
        self.zone.setCurrentIndex(i if i >= 0 else 0)
        self.zone.blockSignals(False)

    def reload(self) -> None:
        """Lesen im eigenen Thread (kein Runner: der würde den Hauptbereich sperren)."""
        from omniwrench.sdk import run_async
        svc = self.ctl.svc
        srv = self.server.currentData() or svc.primary
        if not srv:
            return
        self._fill_zones()
        self._gen += 1
        gen = self._gen
        hours = self.period.currentData() or 24
        since = eventlog.iso_utc(_dt.datetime.now() - _dt.timedelta(hours=hours))
        self.state.setText(self.tr("ev.loading", server=srv))
        self.loaded = True

        def done(evs):
            if gen != self._gen:
                return
            self.events = evs
            err = svc.events_error.get(srv)
            if err:
                self.state.setText(self.tr("ev.error", error=html.escape(err), url=self.ctl.wiki_url("Ereignisprotokoll-einrichten")))
            else:
                self.state.setText(self.tr("ev.state", n=len(evs), server=srv))
            self._fill()

        def failed(text):
            if gen == self._gen:
                self.state.setText(html.escape(text.splitlines()[0] if text else ""))
        run_async(lambda: svc.change_events(srv, since, None, 2000), done, failed)

    def _fill(self) -> None:
        tr = self.tr
        z = self.zone.currentData()
        q = self.filter.text().strip().lower()
        rows = []
        for e in self.events:
            if z and e.get("zone") != z:
                continue
            row = {"record": e.get("record", 0), "time": e.get("time", ""), "user": e.get("user", ""),
                   "area_t": tr(f"ev.area.{e.get('area', 'other')}"), "action_t": tr(f"ev.action.{e.get('action', 'other')}"),
                   "zone": e.get("zone", ""), "obj": e.get("obj", ""), "text": e.get("text", ""), "id": e.get("id", 0)}
            if q and q not in " ".join(str(v) for v in row.values()).lower():
                continue
            rows.append(row)
        self.grid.set_rows(rows)
        self.grid.autosize(260)

    def _action(self, a: str) -> None:
        r = self.grid.current()
        if a == "OpenZone" and r and r.get("zone"):
            srv = self.server.currentData() or self.ctl.svc.primary
            if r["zone"] in self.ctl.svc.zones.get(srv, {}):
                self.ctl.open_zone(srv, r["zone"])
