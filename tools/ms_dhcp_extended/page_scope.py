"""Scope-Tab: Allgemein und Adresspool, Optionen, Reservierungen, Ausschlüsse, Leases, Failover und Befunde.

Befunde werden bei jeder Eingabe neu berechnet und markieren Felder, Zeilen und Unterseiten. Ein Klick
auf einen Befund springt zum Objekt oder führt die vorgeschlagene Korrektur aus.
"""

from __future__ import annotations

import datetime
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from . import checks as ck
from . import dialogs as dlg
from . import eventlog
from . import ipcalc as ip
from .editors import LeaseEdit, OptionsPanel, PoolEditor, opt_row_key
from .runner import Job
from .service import ReplicationError, UserError
from .ui_base import (
    ButtonBar, FindingsView, Grid, Markers, ask3, bold_label, choose, confirm, finding_tip, help_icon, info, level_color,
    level_icon, level_name, short_list, text_dialog, tint, warn,
)

PAGES = ("General", "Options", "Reservations", "Exclusions", "Leases", "Failover", "Findings")


def excl_key(r: dict) -> str:
    return f"{r['start']}-{r['end']}"


class ScopeTab(QWidget):
    def __init__(self, ctl, sid: str, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.tr = tr = ctl.tr
        self.svc = ctl.svc
        self.sid = sid
        self.data: dict | None = None
        self.model: ip.ScopeModel | None = None
        self.unreplicated = False
        self.findings: list[ck.Finding] = []
        self.index: dict[str, list[ck.Finding]] = {}
        self.dock = None
        self._loading = False
        self.base: dict | None = None        # Konfiguration beim Laden (für „wurde auf dem Server geändert?“)
        self.loaded_utc = ""                 # Zeitpunkt des Ladens (UTC, für das Ereignisprotokoll)
        self.remote_data: dict | None = None  # neuerer Stand vom Server, solange eigene Eingaben offen sind

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        self.title = bold_label(sid)
        f = self.title.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        self.title.setFont(f)
        head.addWidget(self.title)
        self.summary = QLabel("")
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.linkActivated.connect(lambda _l: self.show_findings(None))
        head.addWidget(self.summary)
        head.addStretch(1)
        self.head_bar = ButtonBar([("Refresh", tr("ui.refresh")), ("Paste", tr("ui.paste")),
                                   ("Duplicate", tr("scope.duplicate")), ("Replicate", tr("scope.replicate")),
                                   ("Close", tr("ui.close"))])
        self.head_bar.action.connect(self._head_action)
        head.addWidget(self.head_bar)
        root.addLayout(head)
        self.banner = QFrame()
        self.banner.setObjectName("remotebanner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(10, 6, 6, 6)
        self.banner_text = QLabel("")
        self.banner_text.setWordWrap(True)
        self.banner_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bl.addWidget(self.banner_text, 1)
        self.banner_bar = ButtonBar([("Reload", tr("conf.btn_reload")), ("Hide", tr("conf.btn_hide"))])
        self.banner_bar.action.connect(self._banner_action)
        bl.addWidget(self.banner_bar)
        self.banner.hide()
        root.addWidget(self.banner)

        self.markers = Markers(tr, ctl.flt, self.show_findings)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)
        self._build_general()
        self._build_options()
        self._build_reservations()
        self._build_exclusions()
        self._build_leases()
        self._build_failover()
        self.fview = FindingsView(tr, ctl.flt)
        self.fview.activated.connect(self.on_finding)
        self.tabs.addTab(self.fview, tr("scope.page.findings"))
        ctl.flt.changed.connect(self._refresh_marks)
        self.apply_rights()

    def apply_rights(self) -> None:
        """Ohne Schreibrecht (nur „DHCP-Benutzer“) ist der Scope nur lesbar; Partnerfunktionen brauchen dort Schreibrecht."""
        rw = self.svc.can_write(None)
        rel = self.rel()
        prw = rw and (rel is None or self.svc.can_write(rel["partner"]))
        for aid in ("Paste", "Duplicate"):
            self.head_bar.set_visible(aid, rw)
        self.head_bar.set_visible("Replicate", prw)
        self.save_bar.setVisible(rw)
        self.f_name.setReadOnly(not rw)
        self.f_desc.setReadOnly(not rw)
        self.f_lease.setEnabled(rw)
        self.f_state.setEnabled(rw)
        self.pool.bar.setVisible(rw)
        self.pool.set_editable(rw)
        self.opts.apply_rights(rw, False)
        for grid, bar, ids in ((self.res_grid, self.res_bar, ("Add", "Edit", "Remove", "Paste")),
                               (self.ex_grid, self.ex_bar, ("Add", "Remove", "Paste")),
                               (self.ls_grid, self.ls_bar, ("ToReservation", "Remove"))):
            for aid in ids:
                bar.set_visible(aid, rw)
                grid.set_action_visible(aid, rw)
        for aid in ("FoAdd", "FoRemove", "FoReplicate", "FoReplicateRel"):
            self.fo_bar.set_visible(aid, prw)

    # --- Aufbau ------------------------------------------------------------------------------------
    def _build_general(self) -> None:
        tr = self.tr
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        lay = QVBoxLayout(page)
        box = QGroupBox(tr("scope.general"))
        grid = QGridLayout(box)
        self.f_id = QLineEdit()
        self.f_id.setReadOnly(True)
        self.f_mask = QLineEdit()
        self.f_mask.setReadOnly(True)
        self.f_name = QLineEdit()
        self.f_desc = QLineEdit()
        self.f_lease = LeaseEdit(tr)
        self.f_state = QComboBox()
        self.f_state.addItem(tr("state.Active"), "Active")
        self.f_state.addItem(tr("state.InActive"), "InActive")
        self.f_stats = QLabel("")
        self.f_dns = QLabel("")
        self.f_dns.setWordWrap(True)
        rows = [(tr("scope.f.id"), self.f_id, None), (tr("scope.f.mask"), self.f_mask, None),
                (tr("scope.f.name"), self.f_name, "Field:Name"), (tr("scope.f.desc"), self.f_desc, None),
                (tr("scope.f.lease"), self.f_lease, "Field:Lease"), (tr("scope.f.state"), self.f_state, "Field:State"),
                (tr("scope.f.stats"), self.f_stats, "Field:Stats"), (tr("scope.f.dns"), self.f_dns, None)]
        for r, (label, w, key) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            grid.addWidget(w, r, 1)
            if key:
                btn = self.markers.add(key, w if key != "Field:Stats" else None)
                grid.addWidget(btn, r, 2)
        grid.setColumnStretch(1, 1)
        lay.addWidget(box)
        self.f_name.textChanged.connect(self._edited)
        self.f_desc.textChanged.connect(self._edited)
        self.f_lease.changed.connect(self._edited)
        self.f_state.currentIndexChanged.connect(self._edited)

        rbox = QGroupBox(tr("scope.pool"))
        rl = QHBoxLayout(rbox)
        self.pool = PoolEditor(tr)
        self.pool.changed.connect(self._edited)
        rl.addWidget(self.pool, 1)
        rl.addWidget(help_icon(tr("scope.pool_hint")))
        rl.addWidget(self.markers.add("Ranges", None))
        lay.addWidget(rbox)
        bar = QHBoxLayout()
        self.save_bar = ButtonBar([("Save", tr("ui.save")), ("Discard", tr("ui.discard"))], primary=("Save",))
        self.save_bar.action.connect(lambda a: self.ctl.run(self.save_flow()) if a == "Save" else self.discard())
        bar.addWidget(self.save_bar)
        self.dirty_lbl = QLabel("")
        self.dirty_lbl.setStyleSheet(f"color:{theme.current['warning']}; font-weight:600;")
        bar.addWidget(self.dirty_lbl, 1)
        lay.addLayout(bar)
        lay.addStretch(1)
        self.tabs.addTab(scroll, tr("scope.page.general"))

    def _build_options(self) -> None:
        self.opts = OptionsPanel(self.tr)
        self.opts.action.connect(self._opt_action)
        self.tabs.addTab(self.opts, self.tr("scope.page.options"))

    def _build_reservations(self) -> None:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        acts = [("Add", tr("res.add"), "Ins"), ("Edit", tr("res.edit"), "F2"), ("Remove", tr("res.remove"), "Del"), "-",
                ("Copy", tr("ui.copy"), "Ctrl+C"), ("Paste", tr("ui.paste"), "Ctrl+V"), ("CopyCell", tr("ui.copy_cell"), "")]
        self.res_grid = Grid([("ip", tr("res.col.ip"), "ip"), ("cid", tr("res.col.mac"), "text"),
                              ("name", tr("res.col.name"), "text"), ("desc", tr("res.col.desc"), "text"),
                              ("type", tr("res.col.type"), "text")], key_fn=lambda r: r["ip"], actions=acts,
                             default_action="Edit", stretch="desc")
        self.res_grid.action.connect(self._res_action)
        self.res_filter = QLineEdit()
        self.res_filter.setPlaceholderText(tr("ui.filter"))
        self.res_filter.setClearButtonEnabled(True)
        self.res_filter.textChanged.connect(self.res_grid.apply_filter)
        lay.addWidget(self.res_filter)
        lay.addWidget(self.res_grid, 1)
        bar = self.res_bar = ButtonBar([("Add", tr("res.add")), ("Edit", tr("res.edit")), ("Remove", tr("res.remove")),
                                        ("Copy", tr("ui.copy")), ("Paste", tr("ui.paste"))])
        bar.action.connect(self._res_action)
        lay.addWidget(bar)
        self.tabs.addTab(w, tr("scope.page.reservations"))

    def _build_exclusions(self) -> None:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        acts = [("Add", tr("excl.add"), "Ins"), ("Remove", tr("excl.remove"), "Del"), "-",
                ("Copy", tr("ui.copy"), "Ctrl+C"), ("Paste", tr("ui.paste"), "Ctrl+V")]
        self.ex_grid = Grid([("start", tr("excl.col.start"), "ip"), ("end", tr("excl.col.end"), "ip"),
                             ("count", tr("excl.col.count"), "int")], key_fn=excl_key, actions=acts, stretch="count")
        self.ex_grid.action.connect(self._ex_action)
        lay.addWidget(self.ex_grid, 1)
        bar = self.ex_bar = ButtonBar([("Add", tr("excl.add")), ("Remove", tr("excl.remove")), ("Copy", tr("ui.copy")),
                                       ("Paste", tr("ui.paste"))])
        bar.action.connect(self._ex_action)
        bar.add_widget(help_icon(tr("excl.note")))
        lay.addWidget(bar)
        self.tabs.addTab(w, tr("scope.page.exclusions"))

    def _build_leases(self) -> None:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        acts = [("ToReservation", tr("lease.to_res"), ""), ("Remove", tr("lease.remove"), "Del"), "-",
                ("CopyRes", tr("lease.copy_res"), "Ctrl+C"), ("CopyCell", tr("ui.copy_cell"), "")]
        self.ls_grid = Grid([("ip", tr("lease.col.ip"), "ip"), ("cid", tr("lease.col.mac"), "text"),
                             ("host", tr("lease.col.host"), "text"), ("state", tr("lease.col.state"), "text"),
                             ("expires", tr("lease.col.expires"), "text")], key_fn=lambda r: r["ip"], actions=acts,
                            stretch="host")
        self.ls_grid.action.connect(self._lease_action)
        self.ls_filter = QLineEdit()
        self.ls_filter.setPlaceholderText(tr("ui.filter"))
        self.ls_filter.setClearButtonEnabled(True)
        self.ls_filter.textChanged.connect(self.ls_grid.apply_filter)
        lay.addWidget(self.ls_filter)
        lay.addWidget(self.ls_grid, 1)
        bar = self.ls_bar = ButtonBar([("Refresh", tr("ui.refresh")), ("ToReservation", tr("lease.to_res")),
                                       ("Remove", tr("lease.remove")), ("CopyRes", tr("lease.copy_res"))])
        bar.action.connect(self._lease_action)
        lay.addWidget(bar)
        self.tabs.addTab(w, tr("scope.page.leases"))

    def _build_failover(self) -> None:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.fo_labels: dict[str, QLabel] = {}
        for key in ("rel", "partner", "mode", "state", "mclt", "auth", "hint"):
            lbl = QLabel("")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.fo_labels[key] = lbl
            form.addRow(tr(f"scope.fo.{key}"), lbl)
        lay.addLayout(form)
        self.fo_bar = ButtonBar([("FoAdd", tr("scope.fo.add")), ("FoRemove", tr("scope.fo.remove")),
                                 ("FoReplicate", tr("scope.fo.replicate")), ("FoReplicateRel", tr("scope.fo.replicate_rel")),
                                 ("FoCompare", tr("scope.fo.compare")), ("FoRaw", tr("scope.fo.raw"))])
        self.fo_bar.action.connect(self._fo_action)
        lay.addWidget(self.fo_bar)
        self.cmp_grid = Grid([("el", tr("cmp.col.element"), "text"), ("local", tr("cmp.col.local"), "text"),
                              ("partner", tr("cmp.col.partner"), "text"), ("result", tr("cmp.col.result"), "text")],
                             key_fn=lambda r: r["el"], actions=[("CopyCell", tr("ui.copy_cell"), "Ctrl+C")], stretch="partner")
        self.cmp_grid.setSortingEnabled(False)
        lay.addWidget(self.cmp_grid, 1)
        self.tabs.addTab(w, tr("scope.page.failover"))

    # --- Daten ---------------------------------------------------------------------------------------
    def load_flow(self, leases: bool = True):
        data = yield Job(lambda: self.svc.get_scope(self.sid, leases), self.tr("status.loading_scope", id=self.sid))
        if not leases and self.data:
            data["leases"] = self.data.get("leases") or []
        self.set_data(data, keep_edits=self.is_dirty())

    def set_data(self, data: dict, keep_edits: bool = False) -> None:
        tr = self.tr
        # eigene Eingaben merken (nur die tatsächlich geänderten Felder), alles andere kommt neu vom Server
        mine = self.general_changes() if keep_edits else {}
        pool_mine = keep_edits and self.data is not None and self.pool_changed()
        pool_val = self.pool.pool() if pool_mine else None
        self.data = data
        self.base = self.svc.config_of(data)
        self.loaded_utc = eventlog.iso_utc(datetime.datetime.now() - datetime.timedelta(minutes=2))  # Uhren-Toleranz
        self.remote_data = None
        self.banner.hide()
        s = data["scope"]
        self.model = ip.ScopeModel.from_scope(s["id"], s["mask"])
        self.pool.model = self.model
        self._loading = True
        self.f_id.setText(s["id"])
        self.f_mask.setText(f"{s['mask']}  (/{ip.prefix_len(s['mask'])})")
        self.f_name.setText(mine.get("Name", s["name"]))
        self.f_desc.setText(mine.get("Description", s["desc"]))
        self.f_lease.set_value(mine.get("LeaseDuration", s["lease"]))
        self.f_state.setCurrentIndex(0 if mine.get("State", s["state"]) == "Active" else 1)
        if not pool_mine:
            self.pool.set_pool(*self.server_pool())
        elif pool_val is not None:
            self.pool.set_pool(*pool_val)
        st = data.get("stat")
        self.f_stats.setText(tr("scope.stats", in_use=st["in_use"], pct=f"{st['pct']:.1f}", free=st["free"],
                                reserved=st["reserved"]) if st else "–")
        d = data.get("dns")
        self.f_dns.setText(self._dns_text(d) if d else "–")
        self._loading = False
        self.opts.set_options(data["options"], self.svc.defs)
        self.res_grid.set_rows(data["reservations"])
        self.res_grid.apply_filter(self.res_filter.text())
        exs = []
        for x in data["exclusions"]:
            if ip.is_ipv4(x["start"]) and ip.is_ipv4(x["end"]):
                exs.append({"start": x["start"], "end": x["end"], "count": ip.ip2int(x["end"]) - ip.ip2int(x["start"]) + 1})
        self.ex_grid.set_rows(exs)
        self.ls_grid.set_rows(data.get("leases") or [])
        self.ls_grid.apply_filter(self.ls_filter.text())
        for g in (self.res_grid, self.ls_grid, self.ex_grid):
            g.autosize()
        self._fill_failover()
        self.apply_rights()
        self.recheck()

    def _dns_text(self, d: dict) -> str:
        tr = self.tr
        parts = [tr("dns.dyn." + (d.get("dyn") or "OnClientRequest"))]
        if d.get("delete_on_expiry"):
            parts.append(tr("dns.delete_on_expiry"))
        if d.get("older"):
            parts.append(tr("dns.older"))
        if d.get("name_protection"):
            parts.append(tr("dns.name_protection"))
        return ", ".join(parts)

    def server_pool(self) -> tuple[int | None, int | None]:
        s = (self.data or {}).get("scope") or {}
        return (ip.ip2int(s["start"]) if ip.is_ipv4(s.get("start")) else None,
                ip.ip2int(s["end"]) if ip.is_ipv4(s.get("end")) else None)

    def exclusion_list(self) -> list[tuple[int, int]]:
        return [(ip.ip2int(x["start"]), ip.ip2int(x["end"])) for x in (self.data or {}).get("exclusions") or []
                if ip.is_ipv4(x["start"]) and ip.is_ipv4(x["end"])]

    def pool_changed(self) -> bool:
        p = self.pool.pool()
        if p is None:
            return bool(self.pool.items()) or self.server_pool() != (None, None)
        return p != self.server_pool()

    def rel(self) -> dict | None:
        return self.svc.scope_fo.get(self.sid)

    def is_dirty(self) -> bool:
        if not self.data:
            return False
        return bool(self.general_changes()) or self.pool_changed()

    def general_changes(self) -> dict:
        if not self.data:
            return {}
        s = self.data["scope"]
        ch = {}
        if self.f_name.text().strip() != s["name"]:
            ch["Name"] = self.f_name.text().strip()
        if self.f_desc.text().strip() != s["desc"]:
            ch["Description"] = self.f_desc.text().strip()
        if s["lease"] is None or self.f_lease.value() != min(int(s["lease"]), ip.UNLIMITED):
            if not (ip.lease_is_unlimited(s["lease"]) and self.f_lease.unlimited.isChecked()):
                ch["LeaseDuration"] = self.f_lease.value()
        if self.f_state.currentData() != s["state"]:
            ch["State"] = self.f_state.currentData()
        return ch

    def _edited(self) -> None:
        if not self._loading:
            self.recheck()

    # --- Befunde -------------------------------------------------------------------------------------
    def recheck(self) -> None:
        if not self.data:
            return
        tr = self.tr
        checker = self.ctl.checker()
        p = self.pool.pool()
        excl = self.exclusion_list()
        valid = ip.effective_ranges(p[0], p[1], excl) if p else []
        model = ip.ScopeModel(self.model.net, self.model.prefix, valid)
        start, end = self.server_pool()
        data = {"id": self.sid, "model": model, "name": self.f_name.text().strip(), "lease": self.f_lease.value(),
                "state": self.f_state.currentData(), "start": start, "end": end,
                "res_start": p[0] if p else start, "res_end": p[1] if p else end, "exclusions": excl,
                "stat": self.data.get("stat"), "dns": self.data.get("dns"), "options": self.data["options"],
                "reservations": self.data["reservations"], "leases": self.data.get("leases") or [], "rel": self.rel(),
                "unreplicated": self.unreplicated, "is_tab": True}
        fs = checker.scope_findings(data)
        rf, counts, total = checker.ranges(self.pool.items(), self.model)
        if p:
            total = ip.range_size(valid)
        if p and self.pool_changed():
            for x in excl:
                if x[1] < p[0] or x[0] > p[1]:
                    rf.append(ck.Finding(ck.WARN, "ranges", tr("chk.x_outside_pool", range=ip.fmt_range(x)),
                                         [f"Excl:{ip.int2ip(x[0])}-{ip.int2ip(x[1])}", "Ranges"], tr("obj.exclusions")))
        for f in rf:
            f.scope_id = self.sid
        fs += rf
        # Abweichungen zum Failover-Partner aus der letzten Prüfung (Replikation gleicht sie an)
        if self.rel():
            fs += [replace(f, targets=list(f.targets), fix="replicate", fix_label=tr("fix.replicate"))
                   for f in self.svc.partner_diffs.get(self.sid) or []]
        dirty = self.is_dirty()
        if dirty:
            fs.append(ck.Finding(ck.INFO, "general", tr("chk.unsaved"), ["Field:Name", "Ranges"], tr("obj.general"),
                                 self.sid, fix="save_general", fix_label=tr("fix.save")))
        self.findings = ck.sort_findings(fs)
        self.index = {}
        for f in self.findings:
            for t in f.targets:
                self.index.setdefault(t, []).append(f)
        self.pool.show_result(counts, total, self.index, self.ctl.flt)
        self.save_bar.buttons["Save"].setEnabled(dirty)
        self.save_bar.buttons["Discard"].setEnabled(dirty)
        self.dirty_lbl.setText(tr("scope.unsaved") if dirty else "")
        self.fview.set_findings(self.findings)
        self._refresh_marks()

    def _refresh_marks(self) -> None:
        tr = self.tr
        flt = self.ctl.flt
        self.markers.update(self.index)
        self.opts.mark(self.index, flt)
        for grid, prefix, keyf in ((self.res_grid, "Res:", lambda r: r["ip"]), (self.ex_grid, "Excl:", excl_key)):
            for r in grid.rows:
                k = keyf(r)
                fs = [f for f in self.index.get(prefix + k, []) if flt.marker(f)]
                lvl = ck.worst(fs)
                grid.style_row(k, tint(level_color(lvl), 60) if lvl else None, None, False, finding_tip(tr, fs) if fs else "")
        # Unterseiten: Symbol nach schwerstem Befund
        page_targets = {
            0: lambda t: t.startswith(("Field:", "Range")),
            1: lambda t: t.startswith("Option"),
            2: lambda t: t.startswith("Res"),
            3: lambda t: t.startswith("Excl"),
            4: lambda t: t == "Leases",
            5: lambda t: t == "Failover",
        }
        for page, pred in page_targets.items():
            fs = [f for f in self.findings if flt.marker(f) and any(pred(t) for t in f.targets)]
            lvl = ck.worst(fs)
            self.tabs.setTabIcon(page, level_icon(lvl) if lvl else level_icon(None, 1))
        cnt = {}
        for f in self.findings:
            if flt.visible(f, ignore_level=True):
                cnt[f.level] = cnt.get(f.level, 0) + 1
        parts = [f"{level_name(tr, lv, cnt[lv] != 1)}: {cnt[lv]}" for lv in ck.LEVELS if cnt.get(lv) and lv != ck.INFO]
        n = sum(v for k, v in cnt.items() if k != ck.INFO)
        lvl = ck.worst([f for f in self.findings if f.level != ck.INFO and flt.visible(f, ignore_level=True)])
        color = level_color(lvl)
        txt = " · ".join(parts) if parts else tr("scope.no_findings")
        self.summary.setText(f"&nbsp;&nbsp;<a href='f' style='color:{color}; text-decoration:none'>● {txt}</a>")
        self.tabs.setTabText(6, tr("scope.page.findings") + (f" ({n})" if n else ""))
        s = (self.data or {}).get("scope") or {}
        title = f"{self.sid}/{self.model.prefix if self.model else ''}  {s.get('name', '')}"
        if self.unreplicated:
            title += "  " + tr("scope.unreplicated_badge")
        self.title.setText(title)
        self.ctl.update_tab(self, lvl)

    def show_findings(self, key: str | None) -> None:
        if key:
            label = self.index.get(key, [ck.Finding(ck.INFO, "", "", obj=key)])[0].obj or key
            self.fview.set_target(key, label)
        else:
            self.fview.clear_target()
        self.tabs.setCurrentIndex(6)

    def select_page(self, name: str) -> None:
        if name in PAGES:
            self.tabs.setCurrentIndex(PAGES.index(name))

    def goto(self, target: str) -> None:
        if target.startswith("Field:") or target.startswith("Range"):
            self.select_page("General")
            w = {"Field:Name": self.f_name, "Field:Lease": self.f_lease.d, "Field:State": self.f_state}.get(target)
            if w:
                w.setFocus()
            if target.startswith("Range"):
                self.pool.start.setFocus()
        elif target.startswith("Option"):
            self.select_page("Options")
            if ":" in target:
                self.opts.grid.select_key(target)
        elif target.startswith("Res"):
            self.select_page("Reservations")
            if ":" in target:
                self.res_grid.select_key(target.split(":", 1)[1])
        elif target.startswith("Excl"):
            self.select_page("Exclusions")
            if ":" in target:
                self.ex_grid.select_key(target.split(":", 1)[1])
        elif target in ("Leases", "Failover"):
            self.select_page(target)
        else:
            self.select_page("Findings")

    def on_finding(self, f: ck.Finding, mode: str) -> None:
        if mode != "Goto" and f.fix:
            self.apply_fix(f)
        elif f.targets:
            self.goto(f.targets[0])

    def apply_fix(self, f: ck.Finding) -> None:
        fx = f.fix
        if fx == "whole_net":
            self.select_page("General")
            self.pool.whole_net()
        elif fx == "swap_range":
            self.select_page("General")
            self.pool.swap()
        elif fx == "clip_ranges":
            self.select_page("General")
            self.pool.clip()
        elif fx == "edit_option":
            a = f.fix_arg or {}
            self.select_page("Options")
            key = ck.option_key(a.get("id"), a.get("vendor"), a.get("user"))
            row = next((r for r in self.opts.grid.rows if opt_row_key(r) == key), None)
            if row:
                self.opts.grid.select_key(key)
                self.ctl.run(self.option_flow(row))
        elif fx == "select_page":
            self.select_page(str(f.fix_arg))
        elif fx == "add_to_fo":
            self.ctl.run(self.fo_add_flow())
        elif fx == "replicate":
            self.ctl.run(self.replicate_flow())
        elif fx == "new_def":
            self.ctl.run(self._new_def_flow(f.fix_arg or {}))
        elif fx == "save_general":
            self.ctl.run(self.save_flow())
        elif f.targets:
            self.goto(f.targets[0])

    def _new_def_flow(self, arg: dict):
        vals = []
        for o in (self.data or {}).get("options") or []:
            if o["id"] == arg.get("id") and (o.get("vendor") or "") == (arg.get("vendor") or ""):
                vals = o["values"]
        yield from self.ctl.new_definition_flow({"id": arg.get("id"), "vendor": arg.get("vendor") or "",
                                                 "type": dlg.guess_type(vals)})
        self.recheck()

    # --- Kopf -------------------------------------------------------------------------------------------
    def _head_action(self, a: str) -> None:
        if a == "Refresh":
            if self.is_dirty() and not confirm(self, self.tr("ui.refresh"), self.tr("scope.confirm_discard")):
                return
            self.ctl.run(self._reload_all())
        elif a == "Paste":
            self.ctl.run(self.paste_flow(None))
        elif a == "Duplicate":
            self.ctl.open_draft(self.sid)
        elif a == "Replicate":
            self.ctl.run(self.replicate_flow())
        elif a == "Close":
            self.ctl.close_tab(self)

    def _reload_all(self):
        self._loading = True
        data = yield Job(lambda: self.svc.get_scope(self.sid, True), self.tr("status.loading_scope", id=self.sid))
        self.set_data(data, keep_edits=False)

    def can_close(self) -> bool:
        return not self.is_dirty() or confirm(self, self.tr("ui.close"), self.tr("scope.confirm_close"))

    def discard(self) -> None:
        if self.data:
            self.set_data(self.data, keep_edits=False)

    def set_unreplicated(self, value: bool) -> None:
        self.unreplicated = value
        self.recheck()

    # --- Änderungen anderer --------------------------------------------------------------------------------
    def _fresh(self, data: dict) -> dict:
        data["leases"] = (self.data or {}).get("leases") or []
        return data

    def _who(self, events: list[dict]) -> str:
        if events:
            return "\n\n" + self.tr("conf.who", list=self.svc.event_lines(events))
        return "\n\n" + self.tr("conf.who_unknown") if self.svc.events_error else ""

    def guard(self):
        """Vor dem Schreiben: Hat jemand anderes den Scope seit dem Laden geändert? Liefert True = schreiben."""
        tr, svc, sid = self.tr, self.svc, self.sid
        if self.base is None:
            return True
        fresh = yield Job(lambda: svc.get_scope(sid, False), tr("status.conflict_check", id=sid))
        diffs = svc.diff_config(self.base, svc.config_of(fresh))
        if not diffs:
            return True
        mask = self.data["scope"]["mask"]
        events = yield Job(lambda: svc.change_events(self.loaded_utc, sid, mask), tr("status.conflict_check", id=sid))
        svc.log(tr("log.conflict", id=sid, n=len(diffs)), True)
        ans = choose(self, tr("conf.title"), tr("conf.conflict", id=sid, list=short_list(diffs, 12)) + self._who(events),
                     [("reload", tr("conf.btn_reload_keep")), ("overwrite", tr("conf.btn_overwrite")),
                      ("cancel", tr("ui.cancel"))], "reload")
        if ans == "reload":
            self.set_data(self._fresh(fresh), keep_edits=True)
            svc.log(tr("log.remote_reloaded", id=sid, list="; ".join(diffs[:6])))
        return ans == "overwrite"

    def apply_remote(self, fresh: dict, events: list[dict]) -> list[str]:
        """Ergebnis der Hintergrundprüfung: ohne eigene Eingaben neu laden, sonst Hinweis zeigen."""
        tr = self.tr
        if self.base is None:
            return []
        if fresh.get("stat"):
            self.data["stat"] = st = fresh["stat"]
            self.f_stats.setText(tr("scope.stats", in_use=st["in_use"], pct=f"{st['pct']:.1f}", free=st["free"],
                                    reserved=st["reserved"]))
        diffs = self.svc.diff_config(self.base, self.svc.config_of(fresh))
        if not diffs:
            return []
        who = self._who([ev for ev in events if self._mine(ev)])
        if self.is_dirty():
            self.remote_data = self._fresh(fresh)
            self._show_banner(tr("conf.banner_dirty", list=short_list(diffs, 6)) + who, True)
        else:
            self.set_data(self._fresh(fresh))
            self._show_banner(tr("conf.banner_reloaded", list=short_list(diffs, 6)) + who, False)
        return diffs

    def _mine(self, ev: dict) -> bool:
        return bool(self.svc.change_events_match(ev, self.sid, self.data["scope"]["mask"]))

    def _show_banner(self, text: str, reload_btn: bool) -> None:
        c = theme.current
        self.banner.setStyleSheet(f"QFrame#remotebanner {{ border:1px solid {c['warning']}; border-left:4px solid {c['warning']};"
                                  f" border-radius:6px; background:{c['surface']}; }}")
        self.banner_text.setText(text.strip())
        self.banner_bar.set_visible("Reload", reload_btn)
        self.banner.show()

    def _banner_action(self, a: str) -> None:
        if a == "Reload" and self.remote_data is not None:
            data = self.remote_data
            self.set_data(data, keep_edits=True)
            self.svc.log(self.tr("log.remote_reloaded", id=self.sid, list=""))
        elif a == "Hide":
            self.banner.hide()

    # --- Speichern ------------------------------------------------------------------------------------
    def save_flow(self):
        tr, svc, sid = self.tr, self.svc, self.sid
        errs = [f for f in self.findings if f.level == ck.ERROR and f.area in ("general", "ranges", "lease")]
        if errs:
            warn(self, tr("ui.save"), tr("scope.save_blocked", list=short_list([f.text for f in errs], 10)))
            return
        ch = self.general_changes()
        pool_changed = self.pool_changed()
        if not ch and not pool_changed:
            return
        if pool_changed:
            p = self.pool.pool()
            old_s, old_e = self.server_pool()
            # Ausschlüsse außerhalb des neuen Pools lässt Windows nicht stehen - vorher entfernen
            drop = [x for x in self.data["exclusions"] if ip.is_ipv4(x["start"]) and ip.is_ipv4(x["end"])
                    and (ip.ip2int(x["end"]) < p[0] or ip.ip2int(x["start"]) > p[1])]
            text = tr("scope.confirm_pool", old_start=ip.int2ip(old_s) if old_s is not None else "–",
                      old_end=ip.int2ip(old_e) if old_e is not None else "–", start=ip.int2ip(p[0]), end=ip.int2ip(p[1]))
            if drop:
                text += "\n\n" + tr("scope.confirm_pool_drop", list=short_list([f"{x['start']} – {x['end']}" for x in drop], 10))
            if self.rel():
                text += "\n\n" + tr("scope.confirm_pool_fo", partner=self.rel()["partner"])
            if not confirm(self, tr("ui.save"), text):
                return
            ch["StartRange"] = ip.int2ip(p[0])
            ch["EndRange"] = ip.int2ip(p[1])

        else:
            drop = []

        if not (yield from self.guard()):
            return

        def work():
            # Transaktion: schlägt ein Schritt fehl, kommen entfernte Ausschlüsse und alte Werte zurück
            for x in drop:
                svc.excl_remove(sid, x["start"], x["end"])
            svc.scope_set(sid, **ch)
        yield Job(lambda: svc.atomic(tr("tx.scope_save", id=sid), work), tr("status.saving"))
        svc.log(tr("log.scope_saved", id=sid, fields=", ".join(ch)))
        yield from self.load_flow(leases=False)
        self.set_data(self.data, keep_edits=False)
        yield from self.ctl.after_change(sid, self)
        yield from self.ctl.refresh_overview_rows()

    # --- Optionen --------------------------------------------------------------------------------------
    def _opt_action(self, a: str) -> None:
        g = self.opts.grid
        if a == "Add":
            self.ctl.run(self.option_flow(None))
        elif a == "Edit" and g.current():
            self.ctl.run(self.option_flow(g.current()))
        elif a == "Remove" and g.selected_rows():
            self.ctl.run(self.opt_remove_flow(g.selected_rows()))
        elif a == "Copy" and g.selected_rows():
            rows = g.selected_rows()
            self.ctl.clip_set("Options", [{"id": r["id"], "values": r["values"], "vendor": r["vendor"], "user": r["user"]}
                                          for r in rows], self.sid, self.data["scope"]["mask"], g.rows_as_text(rows))
        elif a == "Paste":
            self.ctl.run(self.paste_flow("Options"))

    def option_flow(self, row: dict | None):
        tr, svc = self.tr, self.svc
        vendors, users = yield from self.ctl.load_classes()
        p = self.pool.pool()
        model = ip.ScopeModel(self.model.net, self.model.prefix,
                              ip.effective_ranges(p[0], p[1], self.exclusion_list()) if p else [])
        res = dlg.option_dialog(self, tr, self.ctl.checker(), svc.defs, row, model, vendors, users)
        if not res:
            return
        if res["undefined"] and not confirm(self, tr("opt.title_add"), tr("opt.confirm_new_def", tag=f"{res['id']:03d}")):
            return
        if not (yield from self.guard()):
            return

        def write():
            # neue Definition und Option gehören zusammen: scheitert die Option, verschwindet auch die Definition
            if res["undefined"]:
                ok = yield from self.ctl.new_definition_flow({"id": res["id"], "vendor": res["vendor"],
                                                              "type": dlg.guess_type(res["values"])})
                if not ok:
                    return False
            yield Job(lambda: svc.opt_set(self.sid, res["id"], res["values"], res["vendor"], res["user"]), tr("status.saving"))
            return True
        if not (yield from self.ctl.atomic(tr("tx.opt_set", tag=f"{res['id']:03d}", id=self.sid), write())):
            return
        svc.log(tr("log.opt_set", tag=f"{res['id']:03d}", id=self.sid, values=", ".join(res["values"])))
        yield from self._after_detail_change()

    def opt_remove_flow(self, rows: list[dict]):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("opt.remove"), tr("opt.confirm_remove", list=short_list([f"{r['id']:03d} {r['name']}" for r in rows]))):
            return
        if not (yield from self.guard()):
            return

        def write():
            for r in rows:
                yield Job(lambda r=r: svc.opt_remove(self.sid, r["id"], r["vendor"], r["user"]), tr("status.saving"))
        yield from self.ctl.atomic(tr("tx.opt_remove", id=self.sid), write())
        for r in rows:
            svc.log(tr("log.opt_removed", tag=f"{r['id']:03d}", id=self.sid))
        yield from self._after_detail_change()

    def _after_detail_change(self):
        yield from self.load_flow(leases=False)
        yield from self.ctl.after_change(self.sid, self)
        yield from self.ctl.refresh_overview_rows()

    # --- Reservierungen ---------------------------------------------------------------------------------
    def _res_action(self, a: str) -> None:
        g = self.res_grid
        if a == "Add":
            self.ctl.run(self.res_flow(None))
        elif a == "Edit" and g.current():
            self.ctl.run(self.res_flow(g.current()))
        elif a == "Remove" and g.selected_rows():
            self.ctl.run(self.res_remove_flow(g.selected_rows()))
        elif a == "Copy" and g.selected_rows():
            rows = g.selected_rows()
            self.ctl.clip_set("Reservations", [dict(r) for r in rows], self.sid, self.data["scope"]["mask"], g.rows_as_text(rows))
        elif a == "Paste":
            self.ctl.run(self.paste_flow("Reservations"))

    def res_flow(self, row: dict | None, preset: dict | None = None):
        tr, svc = self.tr, self.svc
        r = dlg.reservation_dialog(self, tr, self.model, row) if preset is None else preset
        if not r:
            return
        if not (yield from self.guard()):
            return
        if row:
            yield Job(lambda: svc.atomic(tr("tx.res_set", ip=r["ip"]), lambda: svc.res_set(r, self.sid)), tr("status.saving"))
        else:
            if any(x["ip"] == r["ip"] for x in self.data["reservations"]):
                warn(self, tr("res.title_add"), tr("res.err_exists", ip=r["ip"]))
                return
            yield Job(lambda: svc.res_add(self.sid, r), tr("status.saving"))
        svc.log(tr("log.res_saved", ip=r["ip"], mac=r["cid"], id=self.sid))
        yield from self._after_detail_change()

    def res_remove_flow(self, rows: list[dict]):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("res.remove"), tr("res.confirm_remove", list=short_list([f"{r['ip']}  {r['name']}" for r in rows]))):
            return
        if not (yield from self.guard()):
            return

        def write():
            for r in rows:
                yield Job(lambda r=r: svc.res_remove(self.sid, r["ip"]), tr("status.saving"))
        yield from self.ctl.atomic(tr("tx.res_remove", id=self.sid), write())
        for r in rows:
            svc.log(tr("log.res_removed", ip=r["ip"], id=self.sid))
        yield from self._after_detail_change()

    # --- Ausschlüsse ------------------------------------------------------------------------------------
    def _ex_action(self, a: str) -> None:
        g = self.ex_grid
        if a == "Add":
            self.ctl.run(self.ex_add_flow())
        elif a == "Remove" and g.selected_rows():
            self.ctl.run(self.ex_remove_flow(g.selected_rows()))
        elif a == "Copy" and g.selected_rows():
            rows = g.selected_rows()
            self.ctl.clip_set("Exclusions", [{"start": r["start"], "end": r["end"]} for r in rows], self.sid,
                              self.data["scope"]["mask"], g.rows_as_text(rows))
        elif a == "Paste":
            self.ctl.run(self.paste_flow("Exclusions"))

    def ex_add_flow(self):
        tr, svc = self.tr, self.svc
        r = dlg.exclusion_dialog(self, tr, self.model)
        if not r:
            return
        if self.is_dirty() and not confirm(self, tr("excl.title"), tr("scope.confirm_discard")):
            return
        if not (yield from self.guard()):
            return
        yield Job(lambda: svc.excl_add(self.sid, r[0], r[1]), tr("status.saving"))
        svc.log(tr("log.excl_added", range=f"{r[0]}-{r[1]}", id=self.sid))
        yield from self.load_flow(leases=False)
        self.set_data(self.data, keep_edits=False)
        yield from self.ctl.after_change(self.sid, self)
        yield from self.ctl.refresh_overview_rows()

    def ex_remove_flow(self, rows: list[dict]):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("excl.remove"), tr("excl.confirm_remove", list=short_list([excl_key(r) for r in rows]))):
            return
        if not (yield from self.guard()):
            return

        def write():
            for r in rows:
                yield Job(lambda r=r: svc.excl_remove(self.sid, r["start"], r["end"]), tr("status.saving"))
        yield from self.ctl.atomic(tr("tx.excl_remove", id=self.sid), write())
        for r in rows:
            svc.log(tr("log.excl_removed", range=excl_key(r), id=self.sid))
        yield from self.load_flow(leases=False)
        self.set_data(self.data, keep_edits=False)
        yield from self.ctl.after_change(self.sid, self)
        yield from self.ctl.refresh_overview_rows()

    # --- Leases -----------------------------------------------------------------------------------------
    def _lease_res(self, r: dict) -> dict:
        return {"ip": r["ip"], "cid": r["cid"], "name": r.get("host") or r["ip"], "desc": self.tr("lease.from_lease"),
                "type": "Dhcp"}

    def _lease_action(self, a: str) -> None:
        g = self.ls_grid
        tr = self.tr
        if a == "Refresh":
            self.ctl.run(self.load_flow(leases=True))
        elif a == "ToReservation" and g.current():
            r = g.current()
            if not ip.format_client_id(r.get("cid")):
                warn(self, tr("lease.to_res"), tr("lease.no_mac", ip=r["ip"]))
                return
            pre = self._lease_res(r)
            if confirm(self, tr("lease.to_res"), tr("lease.confirm_res", ip=r["ip"], mac=r["cid"], name=pre["name"])):
                self.ctl.run(self.res_flow(None, pre))
        elif a == "Remove" and g.selected_rows():
            rows = g.selected_rows()
            if confirm(self, tr("lease.remove"), tr("lease.confirm_remove", list=short_list([f"{r['ip']}  {r['host']}" for r in rows]))):
                self.ctl.run(self._lease_remove_flow(rows))
        elif a == "CopyRes" and g.selected_rows():
            rows = [r for r in g.selected_rows() if ip.format_client_id(r.get("cid"))]
            if rows:
                self.ctl.clip_set("Reservations", [self._lease_res(r) for r in rows], self.sid, self.data["scope"]["mask"],
                                  g.rows_as_text(rows))

    def _lease_remove_flow(self, rows):
        tr, svc = self.tr, self.svc
        for r in rows:
            yield Job(lambda r=r: svc.lease_remove(r["ip"]), tr("status.saving"))
            svc.log(tr("log.lease_removed", ip=r["ip"], id=self.sid))
        yield from self.load_flow(leases=True)

    # --- Einfügen ---------------------------------------------------------------------------------------
    def paste_flow(self, want: str | None):
        tr, svc, sid = self.tr, self.svc, self.sid
        clip = self.ctl.clip_get()
        if not clip or not clip.get("Items"):
            info(self, tr("ui.paste"), tr("clip.empty"))
            return
        kind = clip["Kind"]
        if want and kind != want:
            info(self, tr("ui.paste"), tr("clip.wrong_kind", have=tr("clip.kind." + kind), want=tr("clip.kind." + want)))
            return
        items = clip["Items"]
        conv = None
        src_id, src_mask = clip.get("SourceScopeId"), clip.get("SourceMask")
        if src_id and src_mask and ip.is_ipv4(src_id) and ip.is_ipv4(src_mask) and (
                (ip.ip2int(src_id) & ip.ip2int(src_mask)) != self.model.net or ip.ip2int(src_mask) != self.model.mask):
            ans = ask3(self, tr("ui.paste"), tr("clip.adapt", src=f"{src_id}/{ip.prefix_len(src_mask)}",
                                                   dst=ip.fmt_net(self.model.net, self.model.prefix)))
            if ans == "cancel":
                return
            if ans == "yes":
                sn, sm = ip.ip2int(src_id) & ip.ip2int(src_mask), ip.ip2int(src_mask)

                def _conv(values):
                    return ip.convert_values(values, sn, sm, self.model.net, self.model.mask)
                conv = _conv
        skipped, steps = [], []      # steps: (Bezeichnung, Funktion) - alles oder nichts
        if kind == "Options":
            have = {(o["id"], o.get("vendor") or "", o.get("user") or "") for o in self.data["options"]}
            over = [it for it in items if (int(it["id"]), it.get("vendor") or "", it.get("user") or "") in have]
            if over and not confirm(self, tr("ui.paste"), tr("clip.overwrite_opts", list=short_list([f"{int(i['id']):03d}" for i in over]))):
                return
            for it in items:
                vals = conv(it["values"]) if conv else list(it["values"])
                steps.append((f"{int(it['id']):03d}", lambda it=it, vals=vals: svc.opt_set(
                    sid, int(it["id"]), vals, it.get("vendor") or "", it.get("user") or "")))
        elif kind == "Reservations":
            have = {r["ip"] for r in self.data["reservations"]}
            todo = []
            for it in items:
                rip = conv([it["ip"]])[0] if conv else it["ip"]
                if not ip.is_ipv4(rip) or not self.model.contains(ip.ip2int(rip)) or ip.ip2int(rip) in (self.model.net, self.model.bc):
                    skipped.append(rip)
                    continue
                todo.append(dict(it, ip=rip))
            over = [t["ip"] for t in todo if t["ip"] in have]
            if over and not confirm(self, tr("ui.paste"), tr("clip.overwrite_res", list=short_list(over))):
                return
            for t in todo:
                if t["ip"] in have:     # überschreiben = entfernen + neu anlegen (wird bei Fehler zurückgenommen)
                    steps.append((t["ip"], lambda t=t: svc.res_remove(sid, t["ip"])))
                steps.append((t["ip"], lambda t=t: svc.res_add(sid, t)))
        elif kind == "Exclusions":
            for it in items:
                s, e = (conv([it["start"], it["end"]]) if conv else [it["start"], it["end"]])
                if not (ip.is_ipv4(s) and ip.is_ipv4(e)) or not (self.model.contains(ip.ip2int(s)) and self.model.contains(ip.ip2int(e))):
                    skipped.append(f"{s}-{e}")
                    continue
                steps.append((f"{s}-{e}", lambda s=s, e=e: svc.excl_add(sid, s, e)))

        if not (yield from self.guard()):
            return

        def write():
            for label, fn in steps:
                try:
                    yield Job(fn, tr("status.saving"))
                except UserError as ex:
                    raise UserError(f"{label}: {ex}") from None
        yield from self.ctl.atomic(tr("tx.paste", kind=tr("clip.kind." + kind), id=sid), write())
        done = len({label for label, _fn in steps})
        svc.log(tr("log.pasted", n=done, kind=tr("clip.kind." + kind), id=sid))
        if skipped:
            warn(self, tr("ui.paste"), tr("clip.result", n=done) + "\n\n" + tr("clip.skipped", list=short_list(skipped, 10)))
        if done:
            if kind == "Exclusions":
                yield from self.load_flow(leases=False)
                self.set_data(self.data, keep_edits=False)
                yield from self.ctl.after_change(sid, self)
                yield from self.ctl.refresh_overview_rows()
            else:
                yield from self._after_detail_change()

    # --- Failover ---------------------------------------------------------------------------------------
    def _fill_failover(self) -> None:
        tr = self.tr
        rel = self.rel()
        L = self.fo_labels
        has = rel is not None
        for k in ("FoRemove", "FoReplicate", "FoReplicateRel", "FoCompare", "FoRaw"):
            self.fo_bar.buttons[k].setEnabled(has)
        self.fo_bar.buttons["FoAdd"].setEnabled(not has and bool(self.svc.failovers))
        self.head_bar.buttons["Replicate"].setEnabled(has)
        if not has:
            for k in L:
                L[k].setText("–")
            L["hint"].setText(tr("scope.fo.none_hint") if self.svc.failovers else tr("scope.fo.no_rel_hint"))
            return
        L["rel"].setText(rel["name"])
        L["partner"].setText(f"{rel['partner']}  ({self.svc.partner_state(rel['partner'])})")
        L["mode"].setText(ck.fo_mode(rel, tr))
        ok = rel.get("state") == "Normal"
        L["state"].setText(f"<span style='color:{theme.current['success' if ok else 'danger']}'>"
                           f"{ck.fo_state(rel.get('state', ''), tr)}</span>")
        L["mclt"].setText(tr("scope.fo.mclt_val", mclt=ck.format_duration(rel.get("mclt")),
                             auto=ck.format_duration(rel.get("interval")) if rel.get("auto") else tr("ui.off")))
        L["auth"].setText(tr("ui.on") if rel.get("auth") else tr("ui.off"))
        L["hint"].setText(tr("scope.fo.hint_unrepl") if self.unreplicated else tr("scope.fo.hint_ok"))

    def _fo_action(self, a: str) -> None:
        if a == "FoAdd":
            self.ctl.run(self.fo_add_flow())
        elif a == "FoRemove":
            self.ctl.run(self.fo_remove_flow())
        elif a == "FoReplicate":
            self.ctl.run(self.replicate_flow())
        elif a == "FoReplicateRel":
            rel = self.rel()
            if rel:
                self.ctl.run(self.ctl.replicate_rel_flow(rel))
        elif a == "FoCompare":
            self.ctl.run(self.compare_flow())
        elif a == "FoRaw":
            self.ctl.run(self.raw_flow())

    def fo_add_flow(self):
        tr, svc = self.tr, self.svc
        if self.rel():
            return
        sel = dlg.select_relationship(self, tr, svc.failovers)
        if not sel:
            if not svc.failovers:
                info(self, tr("scope.fo.add"), tr("scope.fo.no_rel_hint"))
            return
        name, _repl = sel
        rel = next(r for r in svc.failovers if r["name"] == name)
        warns = yield Job(lambda: svc.add_fo_scopes(rel, [self.sid]), tr("status.fo_add", id=self.sid, name=name))
        yield Job(svc.load_failovers, tr("status.loading"))
        if warns:
            warn(self, tr("scope.fo.add"), tr("scope.fo.add_warn", list=short_list(warns, 10)))
        self.unreplicated = False
        self._fill_failover()
        self.recheck()
        yield from self.ctl.refresh_overview_rows()

    def fo_remove_flow(self):
        tr, svc = self.tr, self.svc
        rel = self.rel()
        if not rel:
            return
        last = len(rel["scopes"]) <= 1
        if not confirm(self, tr("scope.fo.remove"), tr("scope.fo.confirm_remove_last" if last else "scope.fo.confirm_remove",
                                                      id=self.sid, name=rel["name"], partner=rel["partner"])):
            return
        errs = yield Job(lambda: svc.remove_fo_scopes(rel, [self.sid]), tr("status.fo_remove", id=self.sid))
        yield Job(svc.load_failovers, tr("status.loading"))
        if errs:
            warn(self, tr("scope.fo.remove"), short_list(errs, 10))
        self.unreplicated = False
        self._fill_failover()
        self.recheck()
        yield from self.ctl.refresh_overview_rows()

    def replicate_flow(self):
        tr, svc = self.tr, self.svc
        rel = self.rel()
        if not rel:
            info(self, tr("scope.replicate"), tr("err.no_failover"))
            return
        if self.is_dirty() and not confirm(self, tr("scope.replicate"), tr("scope.confirm_repl_dirty")):
            return
        try:
            yield Job(lambda: svc.replicate([self.sid]), tr("status.replicating", id=self.sid, partner=rel["partner"]))
            self.set_unreplicated(False)
            self.ctl.notify(tr("log.repl_ok", id=self.sid, partner=rel["partner"]))
        except ReplicationError as e:
            self.set_unreplicated(True)
            warn(self, tr("scope.replicate"), str(e))
        self._fill_failover()

    def compare_flow(self):
        tr, svc = self.tr, self.svc
        rel = self.rel()
        if not rel:
            return
        rows = yield Job(lambda: svc.compare_scope(self.sid, rel), tr("status.comparing_one", id=self.sid, partner=rel["partner"]))
        shown = []
        for r in rows:
            shown.append(dict(r, result=tr("cmp.res." + r["result"])))
        self.cmp_grid.set_rows(shown)
        for r, orig in zip(shown, rows):
            color = theme.current["success"] if orig["result"] == "same" else theme.current["danger"]
            self.cmp_grid.style_cell(r["el"], "result", fore=color, bold=orig["result"] != "same")
        self.cmp_grid.autosize(420)
        diff = [r for r in rows if r["result"] != "same"]
        self.fo_labels["hint"].setText(tr("cmp.summary_diff", n=len(diff)) if diff else tr("cmp.summary_same"))
        if not diff and self.unreplicated:
            self.set_unreplicated(False)

    def raw_flow(self):
        tr, svc = self.tr, self.svc
        text = yield Job(lambda: svc.partner_raw_text(self.sid), tr("status.loading"))
        text_dialog(self, tr("scope.fo.raw"), text, tr("ui.close"))

