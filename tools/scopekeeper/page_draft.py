"""Entwurf eines neuen Scopes - leer oder als Duplikat eines vorhandenen Scopes.

Beim Duplizieren werden Bereiche, Optionen und Einstellungen übernommen und Adressen auf das neue
Netz umgerechnet. Der Entwurf prüft laufend (Netz, Überschneidungen, Bereiche, Optionen) und lässt sich
erst anlegen, wenn keine Fehler mehr offen sind.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QScrollArea, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import checks as ck
from . import dialogs as dlg
from . import ipcalc as ip
from .editors import LeaseEdit, RangeEditor
from .runner import Job
from .service import UserError
from .ui_base import (
    MONO, ButtonBar, FindingsView, Markers, bold_label, confirm, hint_label, info, level_color, level_icon, level_name,
    short_list, tint, warn,
)

DEFAULT_LEASE = 8 * 86400


class OctetEdit(QLineEdit):
    """Ein Oktett; "." oder Leertaste springt ins nächste Feld."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setValidator(QIntValidator(0, 255, self))
        self.setMaxLength(3)
        self.setFixedWidth(52)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(MONO)
        self.next_edit: QLineEdit | None = None

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.text() in (".", ",", " ") and self.next_edit is not None:
            self.next_edit.setFocus()
            self.next_edit.selectAll()
            return
        super().keyPressEvent(e)
        if len(self.text()) == 3 and e.text().isdigit() and self.next_edit is not None:
            self.next_edit.setFocus()
            self.next_edit.selectAll()


class DraftTab(QWidget):
    def __init__(self, ctl, source_sid: str | None = None, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.tr = tr = ctl.tr
        self.svc = ctl.svc
        self.source_sid = source_sid
        self.src: dict | None = None
        self.src_model: ip.ScopeModel | None = None
        self.opt_rows: list[dict] = []
        self.pending_rel: dict | None = None
        self.ranges_touched = False
        self.findings: list[ck.Finding] = []
        self.index: dict[str, list[ck.Finding]] = {}
        self.dock = None
        self._busy = False
        self._last_net: tuple[int, int] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        head = QHBoxLayout()
        self.title = bold_label(tr("draft.title_dup", id=source_sid) if source_sid else tr("draft.title_new"))
        f = self.title.font()
        f.setPointSizeF(f.pointSizeF() * 1.25)
        self.title.setFont(f)
        head.addWidget(self.title)
        self.summary = QLabel("")
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.linkActivated.connect(lambda _l: self.tabs.setCurrentIndex(2))
        head.addWidget(self.summary)
        head.addStretch(1)
        self.head_bar = ButtonBar([("Create", tr("draft.create")), ("Rescan", tr("draft.rescan")),
                                   ("Paste", tr("draft.paste_opts")), ("Close", tr("ui.close"))], primary=("Create",))
        self.head_bar.action.connect(self._head_action)
        head.addWidget(self.head_bar)
        root.addLayout(head)
        self.markers = Markers(tr, ctl.flt, self._marker_clicked)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)
        self._build_main()
        self._build_options()
        self.fview = FindingsView(tr, ctl.flt)
        self.fview.activated.connect(self._on_finding)
        self.tabs.addTab(self.fview, tr("scope.page.findings"))
        ctl.flt.changed.connect(self._refresh_marks)

    # --- Aufbau ------------------------------------------------------------------------------------
    def _build_main(self) -> None:
        tr = self.tr
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        lay = QVBoxLayout(page)

        nbox = QGroupBox(tr("draft.net"))
        ng = QGridLayout(nbox)
        row = QHBoxLayout()
        self.octets: list[OctetEdit] = []
        self.fixed: list[QCheckBox] = []
        oct_grid = QGridLayout()
        for i in range(4):
            e = OctetEdit()
            e.textChanged.connect(self._net_changed)
            self.octets.append(e)
            oct_grid.addWidget(e, 0, i * 2)
            if i < 3:
                oct_grid.addWidget(QLabel("."), 0, i * 2 + 1)
            c = QCheckBox(tr("draft.fixed"))
            c.setToolTip(tr("draft.fixed_tip"))
            c.toggled.connect(lambda on, x=e: x.setReadOnly(on))
            c.setVisible(bool(self.source_sid))
            self.fixed.append(c)
            oct_grid.addWidget(c, 1, i * 2)
        for i in range(3):
            self.octets[i].next_edit = self.octets[i + 1]
        row.addLayout(oct_grid)
        row.addWidget(QLabel("/"))
        self.prefix = QComboBox()
        for p in range(8, 31):
            self.prefix.addItem(f"/{p}   {ip.int2ip(ip.mask_from_prefix(p))}", p)
        self.prefix.setCurrentIndex(24 - 8)
        self.prefix.currentIndexChanged.connect(self._net_changed)
        row.addWidget(self.prefix)
        row.addWidget(self.markers.add("Field:Net", None))
        row.addStretch(1)
        ng.addLayout(row, 0, 0, 1, 2)
        self.net_lbl = QLabel("")
        self.net_lbl.setFont(MONO)
        ng.addWidget(self.net_lbl, 1, 0, 1, 2)
        lay.addWidget(nbox)

        gbox = QGroupBox(tr("scope.general"))
        gg = QGridLayout(gbox)
        self.f_name = QLineEdit()
        self.f_desc = QLineEdit()
        self.f_lease = LeaseEdit(tr)
        self.f_lease.set_value(DEFAULT_LEASE)
        self.f_active = QCheckBox(tr("draft.activate"))
        self.f_active.setChecked(True)
        self.f_dns = QCheckBox(tr("draft.copy_dns"))
        self.f_dns.setChecked(True)
        self.f_dns.setVisible(bool(self.source_sid))
        for r, (label, w, key) in enumerate([(tr("scope.f.name"), self.f_name, "Field:Name"),
                                              (tr("scope.f.desc"), self.f_desc, None),
                                              (tr("scope.f.lease"), self.f_lease, "Field:Lease")]):
            gg.addWidget(QLabel(label), r, 0)
            gg.addWidget(w, r, 1)
            if key:
                gg.addWidget(self.markers.add(key, w), r, 2)
        gg.addWidget(self.f_active, 3, 1)
        gg.addWidget(self.f_dns, 4, 1)
        gg.setColumnStretch(1, 1)
        lay.addWidget(gbox)
        for w in (self.f_name, self.f_desc):
            w.textChanged.connect(self.recheck)
        self.f_lease.changed.connect(self.recheck)

        rbox = QGroupBox(tr("scope.ranges"))
        rl = QVBoxLayout(rbox)
        rh = QHBoxLayout()
        rh.addWidget(hint_label(tr("draft.ranges_hint")), 1)
        rh.addWidget(self.markers.add("Ranges", None))
        rl.addLayout(rh)
        self.ranges = RangeEditor(tr)
        self.ranges.confirm_whole = lambda: confirm(self, tr("rng.whole_net"), tr("rng.confirm_whole"))
        self.ranges.changed.connect(self._ranges_edited)
        rl.addWidget(self.ranges)
        lay.addWidget(rbox)

        fbox = QGroupBox(tr("draft.failover"))
        fl = QGridLayout(fbox)
        self.fo_on = QCheckBox(tr("draft.fo_on"))
        self.fo_on.toggled.connect(self._fo_changed)
        self.fo_combo = QComboBox()
        self.fo_combo.currentIndexChanged.connect(self._fo_changed)
        self.fo_new = ButtonBar([("NewRel", tr("draft.fo_new"))])
        self.fo_new.action.connect(lambda _a: self._new_relationship())
        self.fo_repl = QCheckBox(tr("draft.fo_replicate"))
        self.fo_repl.setChecked(True)
        self.fo_lbl = hint_label("")
        fl.addWidget(self.fo_on, 0, 0)
        fl.addWidget(self.fo_combo, 0, 1)
        fl.addWidget(self.fo_new, 0, 2)
        fl.addWidget(self.markers.add("Failover", None), 0, 3)
        fl.addWidget(self.fo_repl, 1, 1, 1, 2)
        fl.addWidget(self.fo_lbl, 2, 0, 1, 4)
        fl.setColumnStretch(1, 1)
        lay.addWidget(fbox)
        lay.addStretch(1)
        self.tabs.addTab(scroll, tr("draft.page.main").replace("&", "&&"))

    def _build_options(self) -> None:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        cols = [tr("draft.col.take"), tr("opt.col.id"), tr("opt.col.name"), tr("draft.col.src"), tr("draft.col.new"),
                tr("draft.col.adapt"), tr("opt.col.vendor"), tr("opt.col.user")]
        self.otable = QTableWidget(0, len(cols))
        self.otable.setHorizontalHeaderLabels(cols)
        self.otable.verticalHeader().setVisible(False)
        self.otable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.otable.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        h = self.otable.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for c, wdt in enumerate((80, 60, 190, 220, 220, 90, 110)):
            self.otable.setColumnWidth(c, wdt)
        self.otable.itemChanged.connect(self._opt_item_changed)
        lay.addWidget(self.otable, 1)
        bar = ButtonBar([("Add", tr("opt.add")), ("Remove", tr("opt.remove")), ("All", tr("draft.all")),
                         ("None", tr("draft.none")), ("AdaptAll", tr("draft.adapt_all")), ("AdaptNone", tr("draft.adapt_none")),
                         ("Paste", tr("ui.paste")), ("NewDef", tr("def.new"))])
        bar.action.connect(self._opt_action)
        lay.addWidget(bar)
        lay.addWidget(hint_label(tr("draft.opt_note")))
        self.tabs.addTab(w, tr("scope.page.options"))

    # --- Laden ---------------------------------------------------------------------------------------
    def init_flow(self):
        """Bei Duplikat: Quelle laden und übernehmen; sonst Vorgaben setzen."""
        tr, svc = self.tr, self.svc
        self._fill_rels()
        if self.source_sid:
            src = yield Job(lambda: svc.get_scope(self.source_sid, False), tr("status.loading_scope", id=self.source_sid))
            self.src = src
            s = src["scope"]
            self.src_model = ip.ScopeModel.from_scope(s["id"], s["mask"])
            self._busy = True
            self.set_address(self.src_model.net, self.src_model.prefix)
            self.f_name.setText(tr("draft.copy_name", name=s["name"]))
            self.f_desc.setText(s["desc"])
            self.f_lease.set_value(s["lease"])
            self.f_active.setChecked(s["state"] == "Active")
            ex = [(ip.ip2int(x["start"]), ip.ip2int(x["end"])) for x in src["exclusions"]
                  if ip.is_ipv4(x["start"]) and ip.is_ipv4(x["end"])]
            self.src_ranges = svc.ranges_of(s, ex)
            self.ranges.set_ranges(self.src_ranges)
            self.ranges_touched = True
            self.opt_rows = [{"id": o["id"], "name": (svc.opt_def(o["id"], o["vendor"]) or {}).get("name", o.get("name", "")),
                              "vendor": o["vendor"], "user": o["user"], "src": list(o["values"]), "manual": None, "take": True,
                              "adapt": True, "src_net": self.src_model.net, "src_mask": self.src_model.mask}
                             for o in src["options"] if not (o["id"] in (51, 81) and not o["vendor"])]
            rel = svc.scope_fo.get(self.source_sid)
            if rel:
                i = self.fo_combo.findData(rel["name"])
                if i >= 0:
                    self.fo_combo.setCurrentIndex(i)
                self.fo_on.setChecked(True)
            self._busy = False
            self._fill_options()
        else:
            self._busy = True
            self.prefix.setCurrentIndex(24 - 8)
            self._busy = False
        self._net_changed()

    def _fill_rels(self) -> None:
        self.fo_combo.blockSignals(True)
        self.fo_combo.clear()
        for r in self.svc.failovers:
            self.fo_combo.addItem(f"{r['name']}  →  {r['partner']}", r["name"])
        if self.pending_rel:
            self.fo_combo.addItem(self.tr("draft.fo_pending", name=self.pending_rel["name"], partner=self.pending_rel["partner"]),
                                  "__new__")
            self.fo_combo.setCurrentIndex(self.fo_combo.count() - 1)
        self.fo_combo.blockSignals(False)
        has = self.fo_combo.count() > 0
        self.fo_on.setEnabled(has)
        if not has:
            self.fo_on.setChecked(False)

    # --- Netz ----------------------------------------------------------------------------------------
    def address(self) -> int | None:
        parts = [e.text().strip() for e in self.octets]
        if not all(p.isdigit() and int(p) <= 255 for p in parts):
            return None
        return ip.ip2int(".".join(parts))

    def prefix_value(self) -> int:
        return int(self.prefix.currentData())

    def set_address(self, n: int, prefix: int) -> None:
        busy = self._busy
        self._busy = True
        for e, part in zip(self.octets, ip.int2ip(n).split(".")):
            e.setText(part)
        self.prefix.setCurrentIndex(prefix - 8)
        self._busy = busy

    def net_model(self) -> ip.ScopeModel | None:
        n = self.address()
        if n is None:
            return None
        p = self.prefix_value()
        return ip.ScopeModel(n & ip.mask_from_prefix(p), p)

    def _net_changed(self) -> None:
        if self._busy:
            return
        m = self.net_model()
        self.ranges.model = m
        if m:
            self.net_lbl.setText(self.tr("draft.net_info", net=ip.fmt_net(m.net, m.prefix), mask=ip.int2ip(m.mask),
                                         first=ip.int2ip(m.net + 1), last=ip.int2ip(m.bc - 1), bc=ip.int2ip(m.bc), hosts=m.hosts))
            key = (m.net, m.prefix)
            if key != self._last_net:
                old = self._last_net
                self._last_net = key
                self._move_ranges(old, m)
            self._fill_options()
        else:
            self.net_lbl.setText(self.tr("draft.net_invalid"))
        self.recheck()

    def _move_ranges(self, old: tuple[int, int] | None, m: ip.ScopeModel) -> None:
        """Bereiche dem neuen Netz folgen lassen (Duplikat: aus der Quelle umgerechnet)."""
        if self.src_model is not None:
            out = []
            for s, e in getattr(self, "src_ranges", []):
                a = ip.convert_ip_num(s, self.src_model.net, self.src_model.mask, m.net, m.mask)
                b = ip.convert_ip_num(e, self.src_model.net, self.src_model.mask, m.net, m.mask)
                if a is not None and b is not None and m.contains(a) and m.contains(b):
                    out.append((a, b))
            if not out and m.hosts > 0:
                out = [(m.net + 1, m.bc - 1)]
            self.ranges.set_ranges(out)
        elif not self.ranges_touched or old is None:
            if m.hosts > 0:
                self.ranges.set_ranges([(m.net + 1, m.bc - 1)])
            self.ranges_touched = False

    def _ranges_edited(self) -> None:
        self.ranges_touched = True
        self.recheck()

    # --- Failover ------------------------------------------------------------------------------------
    def _fo_changed(self, *_a) -> None:
        tr = self.tr
        on = self.fo_on.isChecked()
        self.fo_combo.setEnabled(on)
        self.fo_repl.setEnabled(on)
        rel = self.selected_rel()
        if not on:
            self.fo_lbl.setText(tr("draft.fo_off"))
        elif self.fo_combo.currentData() == "__new__":
            self.fo_lbl.setText(tr("draft.fo_pending_hint", name=self.pending_rel["name"], partner=self.pending_rel["partner"]))
        elif rel:
            self.fo_lbl.setText(tr("draft.fo_existing", name=rel["name"], partner=rel["partner"], mode=ck.fo_mode(rel, tr)))
        self.recheck()

    def selected_rel(self) -> dict | None:
        if not self.fo_on.isChecked():
            return None
        d = self.fo_combo.currentData()
        if d == "__new__" and self.pending_rel:
            return {"name": self.pending_rel["name"], "partner": self.pending_rel["partner"], "state": "Normal",
                    "mode": self.pending_rel["mode"], "lb": self.pending_rel["lb"], "role": self.pending_rel["role"],
                    "reserve": self.pending_rel["reserve"]}
        return next((r for r in self.svc.failovers if r["name"] == d), None)

    def _new_relationship(self) -> None:
        spec = dlg.failover_dialog(self, self.tr, self.ctl.known_servers(), self.svc.server, None, None)
        if not spec:
            return
        if any(r["name"].lower() == spec["name"].lower() for r in self.svc.failovers):
            warn(self, self.tr("fo.title_new"), self.tr("fo.err_exists", name=spec["name"]))
            return
        self.pending_rel = spec
        self._fill_rels()
        self.fo_on.setChecked(True)
        self._fo_changed()

    # --- Optionen ------------------------------------------------------------------------------------
    def new_values(self, r: dict) -> list[str]:
        if r["manual"] is not None:
            return list(r["manual"])
        m = self.net_model()
        if r["adapt"] and m is not None and r.get("src_net") is not None:
            return ip.convert_values(r["src"], r["src_net"], r["src_mask"], m.net, m.mask)
        return list(r["src"])

    def _fill_options(self) -> None:
        t = self.otable
        t.blockSignals(True)
        t.setRowCount(len(self.opt_rows))
        for i, r in enumerate(self.opt_rows):
            take = QTableWidgetItem("")
            take.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            take.setCheckState(Qt.CheckState.Checked if r["take"] else Qt.CheckState.Unchecked)
            t.setItem(i, 0, take)
            vals = [f"{r['id']:03d}", r["name"], ", ".join(r["src"]), ", ".join(self.new_values(r))]
            for c, v in enumerate(vals, 1):
                it = QTableWidgetItem(v)
                if c != 4:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c in (1, 3, 4):
                    it.setFont(MONO)
                t.setItem(i, c, it)
            adapt = QTableWidgetItem("")
            adapt.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            adapt.setCheckState(Qt.CheckState.Checked if r["adapt"] and r["manual"] is None else Qt.CheckState.Unchecked)
            t.setItem(i, 5, adapt)
            for c, v in ((6, r["vendor"]), (7, r["user"])):
                it = QTableWidgetItem(v)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                t.setItem(i, c, it)
        self._mark_options()
        t.blockSignals(False)

    def _opt_item_changed(self, it: QTableWidgetItem) -> None:
        i, c = it.row(), it.column()
        if not 0 <= i < len(self.opt_rows):
            return
        r = self.opt_rows[i]
        if c == 0:
            r["take"] = it.checkState() == Qt.CheckState.Checked
        elif c == 5:
            r["adapt"] = it.checkState() == Qt.CheckState.Checked
            if r["adapt"]:
                r["manual"] = None
        elif c == 4:
            from . import optcodec as oc
            vals = oc.split_option_text(it.text(), self.svc.opt_def(r["id"], r["vendor"]))
            if vals != self.new_values(r):
                r["manual"] = vals
        else:
            return
        self._fill_options()
        self.recheck()

    def _selected_opt_rows(self) -> list[int]:
        return sorted({i.row() for i in self.otable.selectedIndexes()})

    def _opt_action(self, a: str) -> None:
        if a == "Add":
            self.ctl.run(self._opt_add_flow())
        elif a == "Remove":
            for i in reversed(self._selected_opt_rows()):
                del self.opt_rows[i]
        elif a in ("All", "None"):
            for r in self.opt_rows:
                r["take"] = a == "All"
        elif a in ("AdaptAll", "AdaptNone"):
            for r in self.opt_rows:
                r["adapt"] = a == "AdaptAll"
                if r["adapt"]:
                    r["manual"] = None
        elif a == "Paste":
            self._paste_options()
        elif a == "NewDef":
            self.ctl.run(self._new_def_flow({}))
            return
        self._fill_options()
        self.recheck()

    def _opt_add_flow(self):
        tr, svc = self.tr, self.svc
        vendors, users = yield from self.ctl.load_classes()
        res = dlg.option_dialog(self, tr, self.ctl.checker(), svc.defs, None, self.net_model(), vendors, users)
        if not res:
            return
        if res["undefined"]:
            if not confirm(self, tr("opt.title_add"), tr("opt.confirm_new_def", tag=f"{res['id']:03d}")):
                return
            ok = yield from self.ctl.new_definition_flow({"id": res["id"], "vendor": res["vendor"],
                                                          "type": dlg.guess_type(res["values"])})
            if not ok:
                return
        self.opt_rows = [r for r in self.opt_rows if (r["id"], r["vendor"], r["user"]) != (res["id"], res["vendor"], res["user"])]
        self.opt_rows.append({"id": res["id"], "name": (svc.opt_def(res["id"], res["vendor"]) or {}).get("name", ""),
                              "vendor": res["vendor"], "user": res["user"], "src": [], "manual": list(res["values"]),
                              "take": True, "adapt": False, "src_net": None, "src_mask": None})
        self.opt_rows.sort(key=lambda r: (r["vendor"], r["user"], r["id"]))
        self._fill_options()
        self.recheck()

    def _new_def_flow(self, preset: dict):
        yield from self.ctl.new_definition_flow(preset)
        for r in self.opt_rows:
            r["name"] = (self.svc.opt_def(r["id"], r["vendor"]) or {}).get("name", r["name"])
        self._fill_options()
        self.recheck()

    def _paste_options(self) -> None:
        tr = self.tr
        clip = self.ctl.clip_get()
        if not clip or clip.get("Kind") != "Options" or not clip.get("Items"):
            info(self, tr("ui.paste"), tr("clip.no_options"))
            return
        sn = sm = None
        if ip.is_ipv4(clip.get("SourceScopeId") or "") and ip.is_ipv4(clip.get("SourceMask") or ""):
            sm = ip.ip2int(clip["SourceMask"])
            sn = ip.ip2int(clip["SourceScopeId"]) & sm
        keys = {(int(it["id"]), it.get("vendor") or "", it.get("user") or "") for it in clip["Items"]}
        self.opt_rows = [r for r in self.opt_rows if (r["id"], r["vendor"], r["user"]) not in keys]
        for it in clip["Items"]:
            oid = int(it["id"])
            self.opt_rows.append({"id": oid, "name": (self.svc.opt_def(oid, it.get("vendor") or "") or {}).get("name", ""),
                                  "vendor": it.get("vendor") or "", "user": it.get("user") or "", "src": list(it["values"]),
                                  "manual": None, "take": True, "adapt": sn is not None, "src_net": sn, "src_mask": sm})
        self.opt_rows.sort(key=lambda r: (r["vendor"], r["user"], r["id"]))

    def taken_options(self) -> list[dict]:
        return [{"id": r["id"], "values": self.new_values(r), "vendor": r["vendor"], "user": r["user"]}
                for r in self.opt_rows if r["take"]]

    # --- Befunde -------------------------------------------------------------------------------------
    def recheck(self, *_a) -> None:
        if self._busy:
            return
        tr, svc = self.tr, self.svc
        checker = self.ctl.checker()
        fs: list[ck.Finding] = []
        n = self.address()
        p = self.prefix_value()
        m = self.net_model()

        def add(level, area, text, target, obj, fix=None, farg=None, flabel=""):
            fs.append(ck.Finding(level, area, text, [target] if target else [], obj, fix=fix, fix_arg=farg, fix_label=flabel))

        if m is None:
            add(ck.ERROR, "net", tr("chk.d_bad_ip"), "Field:Net", tr("obj.net"))
        else:
            if n != m.net:
                add(ck.WARN, "net", tr("chk.d_host_bits", ip=ip.int2ip(n), net=ip.fmt_net(m.net, p)), "Field:Net", tr("obj.net"))
                for net, pre, kind in ip.network_suggestions(n, p):
                    add(ck.INFO, "net", tr(f"chk.d_suggest_{kind}", net=ip.fmt_net(net, pre)), "Field:Net", tr("obj.net"),
                        "apply_network", (net, pre), tr("fix.apply_network", net=ip.fmt_net(net, pre)))
            if p < 16:
                add(ck.WARN, "net", tr("chk.d_prefix_large", prefix=p, hosts=m.hosts), "Field:Net", tr("obj.net"))
            for c in ip.find_conflicts(m.net, p, svc.scopes):
                add(ck.ERROR, "net", tr(f"chk.d_conflict_{c['kind']}", id=c["id"], prefix=c["prefix"], name=c["name"]),
                    "Field:Net", tr("obj.net"))
            if self.src_model and self.src_model.prefix != p:
                add(ck.INFO, "net", tr("chk.d_mask_changed", old=self.src_model.prefix, new=p), "Field:Net", tr("obj.net"))
        merged = self.ranges.merged()
        start = merged[0][0] if merged else None
        end = merged[-1][1] if merged else None
        opts = self.taken_options()
        if m is not None:
            model = ip.ScopeModel(m.net, m.prefix, merged)
            data = {"id": ip.int2ip(m.net), "model": model, "name": self.f_name.text().strip(), "lease": self.f_lease.value(),
                    "state": "Active", "start": start, "end": end, "res_start": start, "res_end": end, "exclusions": [],
                    "stat": None, "dns": None, "options": opts, "reservations": [], "leases": [], "rel": self.selected_rel(),
                    "unreplicated": False, "is_tab": False}
            for f in checker.scope_findings(data):
                if f.area == "failover" and not self.svc.failovers:
                    continue
                fs.append(f)
            rf, counts, total = checker.ranges(self.ranges.items(), m)
            fs += rf
            # Adressen aus dem Quellnetz, die nicht angepasst werden
            for r in self.opt_rows:
                if not r["take"] or r["adapt"] or r["manual"] is not None or r.get("src_net") is None:
                    continue
                foreign = [v for v in r["src"] if ip.is_ipv4(v) and (ip.ip2int(v) & r["src_mask"]) == r["src_net"]
                           and not m.contains(ip.ip2int(v))]
                if foreign:
                    k = ck.option_key(r["id"], r["vendor"], r["user"])
                    add(ck.WARN, "options", tr("chk.d_foreign_ip", tag=f"{r['id']:03d}", values=", ".join(foreign)), k,
                        tr("obj.option", tag=f"{r['id']:03d}", name=r["name"]), "adapt_option", k, tr("fix.adapt"))
        else:
            counts, total = {}, 0
        for f in fs:
            f.scope_id = ip.fmt_net(m.net, p) if m else ""
        self.findings = ck.sort_findings(fs)
        self.index = {}
        for f in self.findings:
            for t in f.targets:
                self.index.setdefault(t, []).append(f)
        self.ranges.show_result(counts, total, self.index, self.ctl.flt)
        self.fview.set_findings(self.findings)
        self._refresh_marks()

    def _mark_options(self) -> None:
        flt = self.ctl.flt
        for i, r in enumerate(self.opt_rows):
            k = ck.option_key(r["id"], r["vendor"], r["user"])
            fs = [f for f in self.index.get(k, []) if flt.marker(f)] if r["take"] else []
            lvl = ck.worst(fs)
            tip = "\n".join(f.text for f in fs)
            for c in range(self.otable.columnCount()):
                it = self.otable.item(i, c)
                if it is not None:
                    it.setBackground(QBrush(tint(level_color(lvl), 60)) if lvl else QBrush())
                    it.setToolTip(tip)
                    if not r["take"]:
                        it.setForeground(QBrush(QColor("#888888")))

    def _refresh_marks(self) -> None:
        tr = self.tr
        flt = self.ctl.flt
        self.markers.update(self.index)
        self.otable.blockSignals(True)
        self._mark_options()
        self.otable.blockSignals(False)
        for page, pred in ((0, lambda t: t.startswith(("Field:", "Range", "Failover"))), (1, lambda t: t.startswith("Option"))):
            fs = [f for f in self.findings if flt.marker(f) and any(pred(t) for t in f.targets)]
            lvl = ck.worst(fs)
            self.tabs.setTabIcon(page, level_icon(lvl) if lvl else level_icon(None, 1))
        errors = [f for f in self.findings if f.level == ck.ERROR]
        cnt = {}
        for f in self.findings:
            if f.level != ck.INFO and flt.visible(f, ignore_level=True):
                cnt[f.level] = cnt.get(f.level, 0) + 1
        parts = [f"{level_name(tr, lv, cnt[lv] != 1)}: {cnt[lv]}" for lv in ck.LEVELS if cnt.get(lv)]
        lvl = ck.worst(errors) or ck.worst([f for f in self.findings if f.level != ck.INFO])
        txt = " · ".join(parts) if parts else tr("draft.ready")
        self.summary.setText(f"&nbsp;&nbsp;<a href='f' style='color:{level_color(lvl)}; text-decoration:none'>● {txt}</a>")
        self.tabs.setTabText(2, tr("scope.page.findings") + (f" ({sum(cnt.values())})" if cnt else ""))
        btn = self.head_bar.buttons["Create"]
        btn.setEnabled(not errors)
        btn.setToolTip(tr("draft.create_blocked", n=len(errors)) if errors else "")
        self.ctl.update_tab(self, lvl)

    def _marker_clicked(self, key: str) -> None:
        label = self.index.get(key, [ck.Finding(ck.INFO, "", "", obj=key)])[0].obj or key
        self.fview.set_target(key, label)
        self.tabs.setCurrentIndex(2)

    def _on_finding(self, f: ck.Finding, mode: str) -> None:
        if mode != "Goto" and f.fix:
            if f.fix == "apply_network":
                net, pre = f.fix_arg
                self.set_address(net, pre)
                self._net_changed()
                self.tabs.setCurrentIndex(0)
            elif f.fix == "adapt_option":
                for r in self.opt_rows:
                    if ck.option_key(r["id"], r["vendor"], r["user"]) == f.fix_arg:
                        r["adapt"], r["manual"] = True, None
                self._fill_options()
                self.recheck()
                self.tabs.setCurrentIndex(1)
            elif f.fix in ("swap_range", "clip_ranges", "merge_ranges", "whole_net"):
                self.tabs.setCurrentIndex(0)
                {"swap_range": lambda: self.ranges.swap(int(f.fix_arg)), "clip_ranges": self.ranges.clip,
                 "merge_ranges": self.ranges.merge, "whole_net": lambda: self.ranges._action("WholeNet")}[f.fix]()
            elif f.fix == "new_def":
                self.ctl.run(self._new_def_flow({"id": (f.fix_arg or {}).get("id"), "vendor": (f.fix_arg or {}).get("vendor", "")}))
            return
        t = f.targets[0] if f.targets else ""
        if t.startswith("Option"):
            self.tabs.setCurrentIndex(1)
        elif t:
            self.tabs.setCurrentIndex(0)
            if t == "Field:Name":
                self.f_name.setFocus()
            elif t == "Field:Net":
                self.octets[0].setFocus()

    # --- Kopf ------------------------------------------------------------------------------------------
    def _head_action(self, a: str) -> None:
        if a == "Create":
            self.ctl.run(self.create_flow())
        elif a == "Rescan":
            self.ctl.run(self.rescan_flow())
        elif a == "Paste":
            self._paste_options()
            self._fill_options()
            self.recheck()
            self.tabs.setCurrentIndex(1)
        elif a == "Close":
            self.ctl.close_tab(self)

    def can_close(self) -> bool:
        return confirm(self, self.tr("ui.close"), self.tr("draft.confirm_close"))

    def rescan_flow(self):
        yield Job(self.svc.load_overview, self.tr("status.loading"))
        yield Job(self.svc.load_failovers, self.tr("status.loading"))
        self._fill_rels()
        self._fo_changed()
        self.recheck()

    def create_flow(self):
        tr, svc = self.tr, self.svc
        yield from self.rescan_flow()
        errors = [f for f in self.findings if f.level == ck.ERROR]
        if errors:
            warn(self, tr("draft.create"), tr("draft.has_errors", list=short_list([f.text for f in errors], 10)))
            return
        m = self.net_model()
        merged = self.ranges.merged()
        gaps = ip.range_gaps(merged)
        sid = ip.int2ip(m.net)
        opts = self.taken_options()
        rel = self.selected_rel()
        pending = self.fo_on.isChecked() and self.fo_combo.currentData() == "__new__"
        lines = [tr("draft.sum.net", net=ip.fmt_net(m.net, m.prefix), mask=ip.int2ip(m.mask)),
                 tr("draft.sum.name", name=self.f_name.text().strip()),
                 tr("draft.sum.range", start=ip.int2ip(merged[0][0]), end=ip.int2ip(merged[-1][1]), n=ip.range_size(merged)),
                 tr("draft.sum.gaps", n=len(gaps)), tr("draft.sum.options", n=len(opts)),
                 tr("draft.sum.lease", lease=ck.format_lease(self.f_lease.value(), tr)),
                 tr("draft.sum.state", state=tr("state.Active" if self.f_active.isChecked() else "state.InActive"))]
        if rel:
            lines.append(tr("draft.sum.fo_new" if pending else "draft.sum.fo", name=rel["name"], partner=rel["partner"]))
        if not confirm(self, tr("draft.create"), tr("draft.confirm_create", lines="\n".join("• " + x for x in lines))):
            return
        name, desc, lease, active = self.f_name.text().strip(), self.f_desc.text().strip(), self.f_lease.value(), self.f_active.isChecked()
        yield Job(lambda: svc.scope_add(ip.int2ip(merged[0][0]), ip.int2ip(merged[-1][1]), ip.int2ip(m.mask), name, desc,
                                        lease, active), tr("status.creating", id=sid))
        svc.log(tr("log.scope_created", id=sid, prefix=m.prefix, name=name))
        problems: list[str] = []
        dns = (self.src or {}).get("dns") if self.source_sid and self.f_dns.isChecked() else None

        def details():
            errs = []
            for g in gaps:
                try:
                    svc.excl_add(sid, ip.int2ip(g[0]), ip.int2ip(g[1]))
                except UserError as e:
                    errs.append(f"{ip.fmt_range(g)}: {e}")
            for o in opts:
                try:
                    svc.opt_set(sid, o["id"], o["values"], o["vendor"], o["user"])
                except UserError as e:
                    errs.append(f"{o['id']:03d}: {e}")
            if dns:
                try:
                    svc.dns_set(sid, dns)
                except UserError as e:
                    errs.append(f"DNS: {e}")
            return errs
        problems += yield Job(details, tr("status.creating_details", id=sid))
        if rel:
            try:
                if pending:
                    spec = dict(self.pending_rel, scopes=[sid])
                    w = yield Job(lambda: svc.new_relationship(spec), tr("status.fo_create", name=spec["name"]))
                else:
                    real = next(r for r in svc.failovers if r["name"] == rel["name"])
                    w = yield Job(lambda: svc.add_fo_scopes(real, [sid]), tr("status.fo_add", id=sid, name=real["name"]))
                problems += w or []
                yield Job(svc.load_failovers, tr("status.loading"))
                if self.fo_repl.isChecked():
                    try:
                        yield Job(lambda: svc.replicate([sid]), tr("status.replicating", id=sid, partner=rel["partner"]))
                    except UserError as e:
                        problems.append(str(e))
            except UserError as e:
                problems.append(tr("draft.fo_failed", error=str(e)))
        if problems:
            warn(self, tr("draft.create"), tr("draft.created_with_problems", id=sid, list=short_list(problems, 12)))
        yield from self.ctl.refresh_overview_rows()
        self.ctl.close_tab(self, force=True)
        self.ctl.open_scope(sid)
