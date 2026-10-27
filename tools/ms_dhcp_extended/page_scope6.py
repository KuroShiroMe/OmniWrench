"""Scope-Tab für DHCPv6: Allgemein (Gültigkeitsdauern, Rapid Commit, Unicast), Optionen, Reservierungen
(DUID + IAID), Ausschlüsse, Leases und Befunde.

Gleiches Verhalten wie der IPv4-Tab (page_scope.ScopeTab): Prüfung bei jeder Eingabe, Konfliktprüfung vor dem
Schreiben, jede Aktion als Transaktion. Unterschiede: Präfix immer /64, kein Adresspool (der ganze Präfix wird
verteilt, Ausschlüsse nehmen Adressen heraus), kein Failover (gibt es unter Windows für DHCPv6 nicht).
"""

from __future__ import annotations

import datetime

from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QScrollArea, \
    QSpinBox, QVBoxLayout, QWidget

from omniwrench.ui import theme

from . import checks as ck
from . import checks6 as ck6
from . import dialogs as dlg
from . import eventlog
from . import ip6calc as ip6
from . import ipcalc as ip
from .editors import LeaseEdit, OptionsPanel
from .page_scope import ScopeTab, excl_key
from .runner import Job
from .service import UserError
from .ui_base import ButtonBar, Grid, ask3, confirm, help_icon, info, short_list, warn


def res6_key(r: dict) -> str:
    return r["ip"]


class ScopeTab6(ScopeTab):
    PAGES = ("General", "Options", "Reservations", "Exclusions", "Leases", "Findings")
    PAGE_TARGETS = {k: v for k, v in ScopeTab.PAGE_TARGETS.items() if k != "Failover"}

    def __init__(self, ctl, sid: str, parent=None):
        super().__init__(ctl, sid, parent)
        self.plen = ip6.PREFIX

    def rel(self) -> dict | None:
        return None     # kein Failover für DHCPv6

    def apply_rights(self) -> None:
        rw = self.svc.can_write(None)
        for aid in ("Paste", "Duplicate"):
            self.head_bar.set_visible(aid, rw)
        self.head_bar.set_visible("Replicate", False)
        self.save_bar.setVisible(rw)
        for w in (self.f_name, self.f_desc):
            w.setReadOnly(not rw)
        for w in (self.f_pref, self.f_state, self.f_lease_pref, self.f_lease_valid, self.f_rapid, self.f_unicast):
            w.setEnabled(rw)
        self.opts.apply_rights(rw, False)
        for grid, bar, ids in ((self.res_grid, self.res_bar, ("Add", "Edit", "Remove", "Paste")),
                               (self.ex_grid, self.ex_bar, ("Add", "Remove", "Paste")),
                               (self.ls_grid, self.ls_bar, ("ToReservation", "Remove"))):
            for aid in ids:
                bar.set_visible(aid, rw)
                grid.set_action_visible(aid, rw)

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
        self.f_name = QLineEdit()
        self.f_desc = QLineEdit()
        self.f_pref = QSpinBox()
        self.f_pref.setRange(0, 255)
        self.f_pref.setMaximumWidth(90)
        self.f_pref.setToolTip(tr("scope6.preference_tip"))
        self.f_state = QComboBox()
        self.f_state.addItem(tr("state.Active"), "Active")
        self.f_state.addItem(tr("state.InActive"), "InActive")
        self.f_lease_pref = LeaseEdit(tr)
        self.f_lease_valid = LeaseEdit(tr)
        self.f_rapid = QCheckBox(tr("scope6.rapid"))
        self.f_rapid.setToolTip(tr("scope6.rapid_tip"))
        self.f_unicast = QCheckBox(tr("scope6.unicast"))
        self.f_unicast.setToolTip(tr("scope6.unicast_tip"))
        flags = QWidget()
        fl = QHBoxLayout(flags)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.f_rapid)
        fl.addWidget(self.f_unicast)
        fl.addStretch(1)
        self.f_stats = QLabel("")
        rows = [(tr("scope6.f.prefix"), self.f_id, None), (tr("scope.f.name"), self.f_name, "Field:Name"),
                (tr("scope.f.desc"), self.f_desc, None), (tr("scope6.f.preference"), self.f_pref, None),
                (tr("scope6.f.lease_pref"), self.f_lease_pref, "Field:LeasePref"),
                (tr("scope6.f.lease_valid"), self.f_lease_valid, "Field:LeaseValid"),
                (tr("scope.f.state"), self.f_state, "Field:State"), (tr("scope6.f.flags"), flags, None),
                (tr("scope.f.stats"), self.f_stats, "Field:Stats")]
        for r, (label, w, key) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            grid.addWidget(w, r, 1)
            if key:
                grid.addWidget(self.markers.add(key, w if key != "Field:Stats" else None), r, 2)
        grid.addWidget(help_icon(tr("scope6.lifetime_hint")), 4, 3)
        grid.setColumnStretch(1, 1)
        lay.addWidget(box)
        for sig in (self.f_name.textChanged, self.f_desc.textChanged, self.f_pref.valueChanged, self.f_lease_pref.changed,
                    self.f_lease_valid.changed, self.f_state.currentIndexChanged, self.f_rapid.toggled,
                    self.f_unicast.toggled):
            sig.connect(self._edited)
        hint = QLabel(tr("scope6.no_pool_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.current['muted']};")
        lay.addWidget(hint)
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
        self.res_grid = Grid([("ip", tr("res.col.ip"), "ip"), ("duid", tr("res6.col.duid"), "text"),
                              ("iaid", tr("res6.col.iaid"), "int"), ("name", tr("res.col.name"), "text"),
                              ("desc", tr("res.col.desc"), "text")], key_fn=res6_key, actions=acts,
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
        bar.add_widget(help_icon(tr("res6.hint")))
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
        bar.add_widget(help_icon(tr("excl6.note")))
        lay.addWidget(bar)
        self.tabs.addTab(w, tr("scope.page.exclusions"))

    def _build_leases(self) -> None:
        tr = self.tr
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        acts = [("ToReservation", tr("lease.to_res"), ""), ("Remove", tr("lease.remove"), "Del"), "-",
                ("CopyRes", tr("lease.copy_res"), "Ctrl+C"), ("CopyCell", tr("ui.copy_cell"), "")]
        self.ls_grid = Grid([("ip", tr("lease.col.ip"), "ip"), ("duid", tr("res6.col.duid"), "text"),
                             ("iaid", tr("res6.col.iaid"), "int"), ("host", tr("lease.col.host"), "text"),
                             ("state", tr("lease.col.state"), "text"), ("type", tr("lease6.col.type"), "text"),
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
        pass

    def _fill_failover(self) -> None:
        pass

    # --- Daten ---------------------------------------------------------------------------------------
    def set_data(self, data: dict, keep_edits: bool = False) -> None:
        mine = self.general_changes() if keep_edits else {}
        self.data = data
        self.base = self.svc.config_of(data)
        self.loaded_utc = eventlog.iso_utc(datetime.datetime.now() - datetime.timedelta(minutes=2))
        self.remote_data = None
        self.banner.hide()
        s = data["scope"]
        self.plen = int(s.get("plen") or ip6.PREFIX)
        self._loading = True
        self.f_id.setText(ip6.fmt_net(s["id"], self.plen))
        self.f_name.setText(mine.get("Name", s["name"]))
        self.f_desc.setText(mine.get("Description", s["desc"]))
        self.f_pref.setValue(int(mine.get("Preference", s.get("pref") or 0)))
        self.f_lease_pref.set_value(mine.get("PreferredLifetime", s.get("lease_pref")))
        self.f_lease_valid.set_value(mine.get("ValidLifetime", s.get("lease_valid")))
        self.f_state.setCurrentIndex(0 if mine.get("State", s["state"]) == "Active" else 1)
        self.f_rapid.setChecked(bool(mine.get("RapidCommit", s.get("rapid"))))
        self.f_unicast.setChecked(bool(mine.get("Unicast", s.get("unicast"))))
        self.f_stats.setText(self._stats_text(data.get("stat")))
        self._loading = False
        self.opts.set_options(data["options"], self.svc.defs6)
        self.res_grid.set_rows(data["reservations"])
        self.res_grid.apply_filter(self.res_filter.text())
        exs = [{"start": x["start"], "end": x["end"], "count": ip6.range_size(x["start"], x["end"])}
               for x in data["exclusions"] if ip6.is_ipv6(x["start"]) and ip6.is_ipv6(x["end"])]
        self.ex_grid.set_rows(exs)
        self.ls_grid.set_rows(data.get("leases") or [])
        self.ls_grid.apply_filter(self.ls_filter.text())
        for g in (self.res_grid, self.ls_grid, self.ex_grid):
            g.autosize()
        self.apply_rights()
        self.recheck()

    def _stats_text(self, st: dict | None) -> str:
        if not st:
            return "–"
        return self.tr("scope6.stats", in_use=st["in_use"], pending=st.get("pending", 0))

    def clip_mask(self) -> str:
        return str(self.plen)

    def exclusion_pairs(self) -> list[tuple[str, str]]:
        return [(x["start"], x["end"]) for x in (self.data or {}).get("exclusions") or []]

    def pool_changed(self) -> bool:
        return False

    def general_changes(self) -> dict:
        if not self.data:
            return {}
        s = self.data["scope"]
        ch = {}
        if self.f_name.text().strip() != s["name"]:
            ch["Name"] = self.f_name.text().strip()
        if self.f_desc.text().strip() != s["desc"]:
            ch["Description"] = self.f_desc.text().strip()
        if self.f_pref.value() != int(s.get("pref") or 0):
            ch["Preference"] = self.f_pref.value()
        for key, w, cur in (("PreferredLifetime", self.f_lease_pref, s.get("lease_pref")),
                            ("ValidLifetime", self.f_lease_valid, s.get("lease_valid"))):
            if cur is None or w.value() != min(int(cur), ip.UNLIMITED):
                if not (cur is not None and int(cur) >= ip.UNLIMITED and w.unlimited.isChecked()):
                    ch[key] = w.value()
        if self.f_state.currentData() != s["state"]:
            ch["State"] = self.f_state.currentData()
        if self.f_rapid.isChecked() != bool(s.get("rapid")):
            ch["RapidCommit"] = self.f_rapid.isChecked()
        if self.f_unicast.isChecked() != bool(s.get("unicast")):
            ch["Unicast"] = self.f_unicast.isChecked()
        return ch

    # --- Befunde -------------------------------------------------------------------------------------
    def recheck(self) -> None:
        if not self.data:
            return
        tr = self.tr
        data = {"id": self.sid, "plen": self.plen, "name": self.f_name.text().strip(), "state": self.f_state.currentData(),
                "lease_pref": self.f_lease_pref.value(), "lease_valid": self.f_lease_valid.value(),
                "stat": self.data.get("stat"), "exclusions": self.exclusion_pairs(), "options": self.data["options"],
                "reservations": self.data["reservations"], "leases": self.data.get("leases") or [], "is_tab": True}
        fs = ck6.scope_findings(self.ctl.checker(), data)
        dirty = self.is_dirty()
        if dirty:
            fs.append(ck.Finding(ck.INFO, "general", tr("chk.unsaved"), ["Field:Name"], tr("obj.general"),
                                 self.sid, fix="save_general", fix_label=tr("fix.save")))
        self.findings = ck.sort_findings(fs)
        self.index = {}
        for f in self.findings:
            for t in f.targets:
                self.index.setdefault(t, []).append(f)
        self.save_bar.buttons["Save"].setEnabled(dirty)
        self.save_bar.buttons["Discard"].setEnabled(dirty)
        self.dirty_lbl.setText(tr("scope.unsaved") if dirty else "")
        self.fview.set_findings(self.findings)
        self._refresh_marks()

    def title_text(self) -> str:
        s = (self.data or {}).get("scope") or {}
        return f"{ip6.fmt_net(self.sid, self.plen)}  {s.get('name', '')}"

    def goto(self, target: str) -> None:
        if target.startswith("Field:"):
            self.select_page("General")
            w = {"Field:Name": self.f_name, "Field:LeasePref": self.f_lease_pref.d, "Field:LeaseValid": self.f_lease_valid.d,
                 "Field:State": self.f_state}.get(target)
            if w:
                w.setFocus()
        else:
            super().goto(target)

    def apply_fix(self, f: ck.Finding) -> None:
        if f.fix in ("edit_option", "select_page", "new_def", "save_general"):
            super().apply_fix(f)
        elif f.targets:
            self.goto(f.targets[0])

    def _new_def_flow(self, arg: dict):
        vals = []
        for o in (self.data or {}).get("options") or []:
            if o["id"] == arg.get("id") and (o.get("vendor") or "") == (arg.get("vendor") or ""):
                vals = o["values"]
        yield from self.ctl.new_definition_flow({"id": arg.get("id"), "vendor": arg.get("vendor") or "",
                                                 "type": dlg.guess_type(vals), "v6": True})
        self.recheck()

    # --- Speichern ------------------------------------------------------------------------------------
    def save_flow(self):
        tr, svc, sid = self.tr, self.svc, self.sid
        errs = [f for f in self.findings if f.level == ck.ERROR and f.area in ("general", "lease")]
        if errs:
            warn(self, tr("ui.save"), tr("scope.save_blocked", list=short_list([f.text for f in errs], 10)))
            return
        ch = self.general_changes()
        if not ch:
            return
        if not (yield from self.guard()):
            return
        yield Job(lambda: svc.atomic(tr("tx.scope_save", id=sid), lambda: svc.scope6_set(sid, **ch)), tr("status.saving"))
        svc.log(tr("log.scope_saved", id=sid, fields=", ".join(ch)))
        yield from self.load_flow(leases=False)
        self.set_data(self.data, keep_edits=False)
        yield from self.ctl.refresh_overview_rows()

    # --- Optionen --------------------------------------------------------------------------------------
    def option_flow(self, row: dict | None):
        tr, svc = self.tr, self.svc
        vendors, users = yield from self.ctl.load_classes(v6=True)
        res = dlg.option_dialog(self, tr, self.ctl.checker(), svc.defs6, row, None, vendors, users, v6=True)
        if not res:
            return
        if res["undefined"] and not confirm(self, tr("opt.title_add"), tr("opt.confirm_new_def", tag=f"{res['id']:03d}")):
            return
        if not (yield from self.guard()):
            return

        def write():
            if res["undefined"]:
                ok = yield from self.ctl.new_definition_flow({"id": res["id"], "vendor": res["vendor"],
                                                              "type": dlg.guess_type(res["values"]), "v6": True})
                if not ok:
                    return False
            yield Job(lambda: svc.opt_set(self.sid, res["id"], res["values"], res["vendor"], res["user"]), tr("status.saving"))
            return True
        if not (yield from self.ctl.atomic(tr("tx.opt_set", tag=f"{res['id']:03d}", id=self.sid), write())):
            return
        svc.log(tr("log.opt_set", tag=f"{res['id']:03d}", id=self.sid, values=", ".join(res["values"])))
        yield from self._after_detail_change()

    # --- Reservierungen ---------------------------------------------------------------------------------
    def res_flow(self, row: dict | None, preset: dict | None = None):
        tr, svc = self.tr, self.svc
        r = dlg.reservation6_dialog(self, tr, self.sid, self.plen, row) if preset is None else preset
        if not r:
            return
        if not (yield from self.guard()):
            return
        if row:
            yield Job(lambda: svc.atomic(tr("tx.res_set", ip=r["ip"]), lambda: svc.res6_set(self.sid, r)), tr("status.saving"))
        else:
            if any(x["ip"] == r["ip"] for x in self.data["reservations"]):
                warn(self, tr("res.title_add"), tr("res.err_exists", ip=r["ip"]))
                return
            yield Job(lambda: svc.atomic(tr("tx.res_add", ip=r["ip"]), lambda: svc.res6_add(self.sid, r)), tr("status.saving"))
        svc.log(tr("log.res6_saved", ip=r["ip"], duid=r["duid"], iaid=r["iaid"], id=self.sid))
        yield from self._after_detail_change()

    def res_remove_flow(self, rows: list[dict]):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("res.remove"), tr("res.confirm_remove", list=short_list([f"{r['ip']}  {r['name']}" for r in rows]))):
            return
        if not (yield from self.guard()):
            return

        def write():
            for r in rows:
                yield Job(lambda r=r: svc.res6_remove(self.sid, r["ip"]), tr("status.saving"))
        yield from self.ctl.atomic(tr("tx.res_remove", id=self.sid), write())
        for r in rows:
            svc.log(tr("log.res_removed", ip=r["ip"], id=self.sid))
        yield from self._after_detail_change()

    # --- Ausschlüsse ------------------------------------------------------------------------------------
    def ex_add_flow(self):
        tr, svc = self.tr, self.svc
        r = dlg.exclusion6_dialog(self, tr, self.sid, self.plen)
        if not r:
            return
        if self.is_dirty() and not confirm(self, tr("excl.title"), tr("scope.confirm_discard")):
            return
        if not (yield from self.guard()):
            return
        yield Job(lambda: svc.excl6_add(self.sid, r[0], r[1]), tr("status.saving"))
        svc.log(tr("log.excl_added", range=f"{r[0]}-{r[1]}", id=self.sid))
        yield from self._after_excl_change()

    def ex_remove_flow(self, rows: list[dict]):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("excl.remove"), tr("excl.confirm_remove", list=short_list([excl_key(r) for r in rows]))):
            return
        if not (yield from self.guard()):
            return

        def write():
            for r in rows:
                yield Job(lambda r=r: svc.excl6_remove(self.sid, r["start"], r["end"]), tr("status.saving"))
        yield from self.ctl.atomic(tr("tx.excl_remove", id=self.sid), write())
        for r in rows:
            svc.log(tr("log.excl_removed", range=excl_key(r), id=self.sid))
        yield from self._after_excl_change()

    def _after_excl_change(self):
        yield from self.load_flow(leases=False)
        self.set_data(self.data, keep_edits=False)
        yield from self.ctl.refresh_overview_rows()

    # --- Leases -----------------------------------------------------------------------------------------
    def _lease_res(self, r: dict) -> dict:
        return {"ip": r["ip"], "duid": r["duid"], "iaid": int(r.get("iaid") or 0), "name": r.get("host") or "",
                "desc": self.tr("lease.from_lease")}

    def _lease_action(self, a: str) -> None:
        g = self.ls_grid
        tr = self.tr
        if a == "Refresh":
            self.ctl.run(self.load_flow(leases=True))
        elif a == "ToReservation" and g.current():
            r = g.current()
            if not ip6.format_duid(r.get("duid")):
                warn(self, tr("lease.to_res"), tr("lease6.no_duid", ip=r["ip"]))
                return
            pre = self._lease_res(r)
            if confirm(self, tr("lease.to_res"), tr("lease6.confirm_res", ip=r["ip"], duid=r["duid"], iaid=pre["iaid"],
                                                    name=pre["name"] or "–")):
                self.ctl.run(self.res_flow(None, pre))
        elif a == "Remove" and g.selected_rows():
            rows = g.selected_rows()
            if confirm(self, tr("lease.remove"), tr("lease.confirm_remove", list=short_list([f"{r['ip']}  {r['host']}" for r in rows]))):
                self.ctl.run(self._lease_remove_flow(rows))
        elif a == "CopyRes" and g.selected_rows():
            rows = [r for r in g.selected_rows() if ip6.format_duid(r.get("duid"))]
            if rows:
                self.ctl.clip_set("Reservations", [self._lease_res(r) for r in rows], self.sid, self.clip_mask(),
                                  g.rows_as_text(rows))

    def _lease_remove_flow(self, rows):
        tr, svc = self.tr, self.svc
        for r in rows:
            yield Job(lambda r=r: svc.lease6_remove(r["ip"]), tr("status.saving"))
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
        src_id = str(clip.get("SourceScopeId") or "")
        if clip.get("Family") != 6:
            info(self, tr("ui.paste"), tr("clip.wrong_family"))
            return
        items = clip["Items"]
        conv = None
        if ip6.is_v6_scope(src_id) and ip6.prefix_of(src_id, self.plen) != ip6.prefix_of(sid, self.plen):
            ans = ask3(self, tr("ui.paste"), tr("clip.adapt", src=ip6.fmt_net(src_id, self.plen), dst=ip6.fmt_net(sid, self.plen)))
            if ans == "cancel":
                return
            if ans == "yes":
                def _conv(values):
                    return ip6.convert_values(values, src_id, sid, self.plen)
                conv = _conv
        skipped, steps = [], []
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
                if not ip6.is_ipv6(rip) or not ip6.in_prefix(rip, sid, self.plen) or not it.get("duid"):
                    skipped.append(rip)
                    continue
                todo.append(dict(it, ip=ip6.norm(rip)))
            over = [t["ip"] for t in todo if t["ip"] in have]
            if over and not confirm(self, tr("ui.paste"), tr("clip.overwrite_res", list=short_list(over))):
                return
            for t in todo:
                if t["ip"] in have:
                    steps.append((t["ip"], lambda t=t: svc.res6_remove(sid, t["ip"])))
                steps.append((t["ip"], lambda t=t: svc.res6_add(sid, t)))
        elif kind == "Exclusions":
            for it in items:
                s, e = (conv([it["start"], it["end"]]) if conv else [it["start"], it["end"]])
                if not (ip6.in_prefix(s, sid, self.plen) and ip6.in_prefix(e, sid, self.plen)):
                    skipped.append(f"{s}-{e}")
                    continue
                steps.append((f"{s}-{e}", lambda s=s, e=e: svc.excl6_add(sid, s, e)))

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
            yield from self._after_excl_change() if kind == "Exclusions" else self._after_detail_change()
