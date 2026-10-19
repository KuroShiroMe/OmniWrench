"""Feste Seiten des Hauptbereichs: Übersicht, Server-Optionen, Failover, Optionsdefinitionen und Prüfung."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from . import checks as ck
from . import dialogs as dlg
from . import ipcalc as ip
from .editors import OptionsPanel, opt_row_key
from .runner import Job
from .ui_base import (
    ButtonBar, FindingsToolbar, FindingsView, Grid, bold_label, confirm, finding_tip, hint_label, info, level_color,
    level_icon, level_name, short_list, text_dialog, tint, warn,
)


# --- Übersicht ---------------------------------------------------------------------------------------

class OverviewPage(QWidget):
    action = Signal(str)

    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("ov.filter"))
        self.filter.setClearButtonEnabled(True)
        top.addWidget(self.filter, 1)
        self.count = QLabel("")
        self.count.setStyleSheet(f"color:{theme.current['muted']};")
        top.addWidget(self.count)
        lay.addLayout(top)
        acts = [("Edit", tr("ov.open"), ""), ("Duplicate", tr("ov.duplicate"), "Ctrl+D"), "-",
                ("Activate", tr("ov.activate"), ""), ("Deactivate", tr("ov.deactivate"), ""), "-",
                ("Remove", tr("ov.remove"), "Del"), "-", ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.grid = Grid([("id", tr("ov.col.id"), "ip"), ("prefix", tr("ov.col.prefix"), "int"),
                          ("name", tr("ov.col.name"), "text"), ("ranges", tr("ov.col.ranges"), "text"),
                          ("usable", tr("ov.col.usable"), "int"), ("state_t", tr("ov.col.state"), "text"),
                          ("fo", tr("ov.col.failover"), "text"), ("lease_t", tr("ov.col.lease"), "text"),
                          ("pct", tr("ov.col.pct"), "float"), ("desc", tr("ov.col.desc"), "text"),
                          ("find", tr("ov.col.findings"), "text")],
                         key_fn=lambda r: r["id"], actions=acts, default_action="Edit", stretch="desc")
        self.grid.action.connect(self.action.emit)
        self.filter.textChanged.connect(lambda t: (self.grid.apply_filter(t), self._count()))
        lay.addWidget(self.grid, 1)
        self.bar = ButtonBar([("Refresh", tr("ui.refresh")), ("Edit", tr("ov.open")), ("New", tr("ov.new")),
                              ("Duplicate", tr("ov.duplicate")), ("Activate", tr("ov.activate")),
                              ("Deactivate", tr("ov.deactivate")), ("Remove", tr("ov.remove"))], primary=("New",))
        self.bar.action.connect(self.action.emit)
        lay.addWidget(self.bar)

    def _count(self) -> None:
        self.count.setText(self.tr("ov.count", shown=len(self.grid.visible_rows()), total=len(self.grid.rows)))

    def set_data(self, svc, scan: dict | None) -> None:
        tr = self.tr
        rows = []
        for s in svc.scopes:
            inf = svc.scope_info.get(s["id"]) or {}
            st = inf.get("stat")
            rel = svc.scope_fo.get(s["id"])
            fs = ((scan or {}).get("scopes", {}).get(s["id"]) or {}).get("findings") or []
            cnt = {lv: sum(1 for f in fs if f.level == lv) for lv in (ck.ERROR, ck.WARN)}
            find = " · ".join(f"{level_name(tr, lv, cnt[lv] != 1)} {cnt[lv]}" for lv in cnt if cnt[lv])
            rows.append({"id": s["id"], "prefix": ip.prefix_len(s["mask"]), "name": s["name"],
                         "ranges": ", ".join(ip.fmt_range(r) for r in (inf.get("ranges") or [])[:3])
                         + (" …" if len(inf.get("ranges") or []) > 3 else ""),
                         "usable": inf.get("usable", 0), "state": s["state"], "state_t": tr("state." + s["state"]),
                         "fo": f"{rel['name']} ({ck.fo_state(rel.get('state', ''), tr)})" if rel else "–",
                         "lease_t": ck.format_lease(s["lease"], tr), "pct": st["pct"] if st else None, "desc": s["desc"],
                         "find": find if scan else "", "_find": fs, "_rel": rel, "_inf": inf, "_stat": st})
        self.grid.set_rows(rows)
        c = theme.current
        for r in rows:
            k = r["id"]
            if r["state"] != "Active":
                self.grid.style_cell(k, "state_t", fore=c["muted"])
            rel = r["_rel"]
            self.grid.style_cell(k, "fo", fore=c["warning"] if not rel else c["success"] if rel.get("state") == "Normal" else c["danger"],
                                 bold=bool(rel) and rel.get("state") != "Normal")
            if r["pct"] is not None and r["pct"] >= 90:
                self.grid.style_cell(k, "pct", fore=c["danger"], bold=True)
            lvl = ck.worst([f for f in r["_find"] if f.level in (ck.ERROR, ck.WARN)])
            if lvl:
                self.grid.style_cell(k, "find", fore=level_color(lvl), bold=lvl == ck.ERROR)
        self.grid.set_tooltips(self._tip)
        self.grid.autosize(300)
        self.grid.apply_filter(self.filter.text())
        self._count()

    def _tip(self, r: dict) -> str:
        tr = self.tr
        inf = r["_inf"]
        lines = [f"{r['id']}/{r['prefix']}  {r['name']}"]
        lines.append(tr("ov.tip.ranges", list=", ".join(ip.fmt_range(x) for x in inf.get("ranges") or []) or "–"))
        ex = inf.get("exclusions") or []
        if ex:
            lines.append(tr("ov.tip.exclusions", list=", ".join(ip.fmt_range(x) for x in ex[:8]) + (" …" if len(ex) > 8 else "")))
        if r["_rel"]:
            lines.append(tr("ov.tip.failover", name=r["_rel"]["name"], partner=r["_rel"]["partner"], mode=ck.fo_mode(r["_rel"], tr)))
        st = r["_stat"]
        if st:
            lines.append(tr("scope.stats", in_use=st["in_use"], pct=f"{st['pct']:.1f}", free=st["free"], reserved=st["reserved"]))
        if r["_find"]:
            lines.append("")
            lines.append(finding_tip(tr, [f for f in r["_find"] if f.level != ck.INFO], 8))
        return "\n".join(lines)


# --- Server-Optionen ------------------------------------------------------------------------------------

class ServerOptionsPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.svc = ctl.svc
        self.options: list[dict] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        sp = QSplitter(Qt.Orientation.Vertical)
        self.panel = OptionsPanel(tr, server_level=True)
        self.panel.action.connect(self._action)
        sp.addWidget(self.panel)
        self.fview = FindingsView(tr, ctl.flt)
        self.fview.empty_text = tr("srvopt.no_findings")
        self.fview.activated.connect(self._finding)
        sp.addWidget(self.fview)
        sp.setSizes([400, 200])
        lay.addWidget(sp, 1)

    def set_options(self, options: list[dict]) -> None:
        self.options = options
        self.panel.set_options(options, self.svc.defs)
        checker = self.ctl.checker()
        fs = []
        for o in options:
            key = ck.option_key(o["id"], o["vendor"], o["user"])
            for f in checker.option_values(o["id"], o["values"], o["vendor"], None, area="server_options"):
                f.targets = [key]
                f.obj = self.tr("obj.server_option", tag=f"{o['id']:03d}")
                fs.append(f)
        if any(o["id"] == 3 and not o["vendor"] and not o["user"] for o in options):
            fs.append(ck.Finding(ck.WARN, "server_options", self.tr("chk.srv_o3"), [ck.option_key(3)],
                                 self.tr("obj.server_option", tag="003")))
        self.findings = ck.sort_findings(fs)
        idx: dict[str, list[ck.Finding]] = {}
        for f in self.findings:
            for t in f.targets:
                idx.setdefault(t, []).append(f)
        self.panel.mark(idx, self.ctl.flt)
        self.fview.set_findings(self.findings)

    def _finding(self, f, _mode) -> None:
        if f.targets:
            self.panel.grid.select_key(f.targets[0])
            if f.fix == "new_def":
                self.ctl.run(self._reload_after(self.ctl.new_definition_flow({"id": f.fix_arg["id"], "vendor": f.fix_arg["vendor"]})))

    def load_flow(self):
        opts = yield Job(self.svc.load_server_options, self.tr("status.loading"))
        self.set_options(opts)

    def _reload_after(self, gen):
        yield from gen
        yield from self.load_flow()

    def _action(self, a: str) -> None:
        g = self.panel.grid
        if a == "Add":
            self.ctl.run(self.option_flow(None))
        elif a == "Edit" and g.current():
            self.ctl.run(self.option_flow(g.current()))
        elif a == "Remove" and g.selected_rows():
            self.ctl.run(self.remove_flow(g.selected_rows()))
        elif a == "Copy" and g.selected_rows():
            rows = g.selected_rows()
            self.ctl.clip_set("Options", [{"id": r["id"], "values": r["values"], "vendor": r["vendor"], "user": r["user"]}
                                          for r in rows], "", "", g.rows_as_text(rows))
        elif a == "Paste":
            self.ctl.run(self.paste_flow())
        elif a == "ToPartner" and g.selected_rows():
            self.ctl.run(self.to_partner_flow(g.selected_rows()))

    def option_flow(self, row):
        tr, svc = self.tr, self.svc
        vendors, users = yield from self.ctl.load_classes()
        res = dlg.option_dialog(self, tr, self.ctl.checker(), svc.defs, row, None, vendors, users,
                                title=tr("srvopt.title_edit") if row else tr("srvopt.title_add"))
        if not res:
            return
        if res["undefined"]:
            if not confirm(self, tr("opt.title_add"), tr("opt.confirm_new_def", tag=f"{res['id']:03d}")):
                return
            ok = yield from self.ctl.new_definition_flow({"id": res["id"], "vendor": res["vendor"], "type": dlg.guess_type(res["values"])})
            if not ok:
                return
        yield Job(lambda: svc.opt_set(None, res["id"], res["values"], res["vendor"], res["user"]), tr("status.saving"))
        svc.log(tr("log.srvopt_set", tag=f"{res['id']:03d}", values=", ".join(res["values"])))
        svc.log(tr("log.srvopt_no_repl"))
        yield from self.load_flow()

    def remove_flow(self, rows):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("opt.remove"), tr("srvopt.confirm_remove", list=short_list([f"{r['id']:03d} {r['name']}" for r in rows]))):
            return
        for r in rows:
            yield Job(lambda r=r: svc.opt_remove(None, r["id"], r["vendor"], r["user"]), tr("status.saving"))
            svc.log(tr("log.srvopt_removed", tag=f"{r['id']:03d}"))
        yield from self.load_flow()

    def paste_flow(self):
        tr, svc = self.tr, self.svc
        clip = self.ctl.clip_get()
        if not clip or clip.get("Kind") != "Options" or not clip.get("Items"):
            info(self, tr("ui.paste"), tr("clip.no_options"))
            return
        have = {opt_row_key(r) for r in self.panel.grid.rows}
        over = [it for it in clip["Items"] if ck.option_key(it["id"], it.get("vendor"), it.get("user")) in have]
        if over and not confirm(self, tr("ui.paste"), tr("clip.overwrite_opts", list=short_list([f"{int(i['id']):03d}" for i in over]))):
            return
        for it in clip["Items"]:
            yield Job(lambda it=it: svc.opt_set(None, int(it["id"]), list(it["values"]), it.get("vendor") or "", it.get("user") or ""),
                      tr("status.saving"))
        svc.log(tr("log.pasted", n=len(clip["Items"]), kind=tr("clip.kind.Options"), id=tr("srvopt.server")))
        yield from self.load_flow()

    def to_partner_flow(self, rows):
        tr, svc = self.tr, self.svc
        partners = svc.partners()
        if not partners:
            info(self, tr("opt.to_partner"), tr("srvopt.no_partner"))
            return
        if not confirm(self, tr("opt.to_partner"), tr("srvopt.confirm_partner", partners=", ".join(partners),
                                                     list=short_list([f"{r['id']:03d} {r['name']}" for r in rows]))):
            return
        errs = []

        def work():
            for pn in partners:
                errs.extend(svc.sync_defs_to_partner(pn, [(r["vendor"], r["id"]) for r in rows]))
                for r in rows:
                    try:
                        svc.partner(pn, "opt_set", scope=None, id=r["id"], values=r["values"], vendor=r["vendor"], user=r["user"])
                        svc.log(tr("log.srvopt_partner", tag=f"{r['id']:03d}", partner=pn))
                    except Exception as e:  # noqa: BLE001 - je Option weitermachen
                        errs.append(f"{pn} {r['id']:03d}: {e}")
        yield Job(work, tr("status.to_partner"))
        if errs:
            warn(self, tr("opt.to_partner"), short_list(errs, 12))
        else:
            self.ctl.notify(tr("srvopt.partner_done", n=len(rows)))


# --- Failover --------------------------------------------------------------------------------------------

class FailoverPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.svc = ctl.svc
        self.compare: dict[str, dict[str, tuple[str, str]]] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        sp = QSplitter(Qt.Orientation.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(bold_label(tr("fo.relationships")))
        acts = [("Edit", tr("fo.edit"), "F2"), ("AddScopes", tr("fo.add_scopes"), ""), ("Replicate", tr("fo.replicate"), ""),
                ("Compare", tr("fo.compare"), ""), ("ApiRaw", tr("fo.raw"), ""), "-", ("Remove", tr("fo.remove"), "Del"),
                "-", ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.rel_grid = Grid([("name", tr("fo.col.name"), "text"), ("partner", tr("fo.col.partner"), "text"),
                              ("mode_t", tr("fo.col.mode"), "text"), ("role_t", tr("fo.col.role"), "text"),
                              ("state_t", tr("fo.col.state"), "text"), ("lb", tr("fo.col.lb"), "int"),
                              ("reserve", tr("fo.col.reserve"), "int"), ("mclt_t", tr("fo.col.mclt"), "text"),
                              ("auto_t", tr("fo.col.auto"), "text"), ("count", tr("fo.col.scopes"), "int"),
                              ("auth_t", tr("fo.col.auth"), "text")], key_fn=lambda r: r["name"], actions=acts,
                             default_action="Edit", multi=False, stretch="partner")
        self.rel_grid.action.connect(self._rel_action)
        self.rel_grid.itemSelectionChanged.connect(self._fill_scopes)
        tl.addWidget(self.rel_grid, 1)
        self.rel_bar = ButtonBar([("Refresh", tr("ui.refresh")), ("New", tr("fo.new")), ("Edit", tr("fo.edit")),
                                  ("AddScopes", tr("fo.add_scopes")), ("Replicate", tr("fo.replicate")),
                                  ("Compare", tr("fo.compare")), ("ApiRaw", tr("fo.raw")), ("Remove", tr("fo.remove"))],
                                 primary=("New",))
        self.rel_bar.action.connect(self._rel_action)
        tl.addWidget(self.rel_bar)
        self.info = hint_label("")
        tl.addWidget(self.info)
        sp.addWidget(top)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        self.sc_title = bold_label(tr("fo.scopes"))
        bl.addWidget(self.sc_title)
        sacts = [("Open", tr("fo.sc_open"), ""), ("Replicate", tr("fo.sc_replicate"), ""), ("Compare", tr("fo.sc_compare"), ""),
                 "-", ("Remove", tr("fo.sc_remove"), "Del")]
        self.sc_grid = Grid([("id", tr("ov.col.id"), "ip"), ("name", tr("ov.col.name"), "text"),
                             ("state_t", tr("fo.col.local_state"), "text"), ("sync_t", tr("fo.col.sync"), "text"),
                             ("detail", tr("fo.col.detail"), "text")], key_fn=lambda r: r["id"], actions=sacts,
                            default_action="Open", stretch="detail")
        self.sc_grid.action.connect(self._sc_action)
        bl.addWidget(self.sc_grid, 1)
        sb = ButtonBar([("Open", tr("fo.sc_open")), ("Replicate", tr("fo.sc_replicate")), ("Compare", tr("fo.sc_compare")),
                        ("Remove", tr("fo.sc_remove"))])
        sb.action.connect(self._sc_action)
        bl.addWidget(sb)
        sp.addWidget(bottom)
        sp.setSizes([300, 300])
        lay.addWidget(sp, 1)

    def refresh(self) -> None:
        tr = self.tr
        rows = []
        for r in self.svc.failovers:
            lb = r["mode"] == "LoadBalance"
            rows.append(dict(r, mode_t=tr("fo.mode_lb") if lb else tr("fo.mode_hs"),
                             role_t="–" if lb else tr("forole." + (r.get("role") or "Active")),
                             state_t=ck.fo_state(r.get("state", ""), tr), lb=r.get("lb") if lb else None,
                             reserve=None if lb else r.get("reserve"), mclt_t=ck.format_duration(r.get("mclt")),
                             auto_t=ck.format_duration(r.get("interval")) if r.get("auto") else tr("ui.off"),
                             count=len(r["scopes"]), auth_t=tr("ui.on") if r.get("auth") else tr("ui.off")))
        self.rel_grid.set_rows(rows)
        c = theme.current
        for r in rows:
            self.rel_grid.style_cell(r["name"], "state_t", fore=c["success"] if r.get("state") == "Normal" else c["danger"],
                                     bold=r.get("state") != "Normal")
        self.rel_grid.autosize(260)
        if rows and not self.rel_grid.selected_rows():
            self.rel_grid.selectRow(0)
        no_fo = [s["id"] for s in self.svc.scopes if s["id"] not in self.svc.scope_fo]
        parts = [tr("fo.info_count", n=len(rows), m=len(self.svc.scopes) - len(no_fo), total=len(self.svc.scopes))]
        for pn in self.svc.partners():
            parts.append(f"{pn}: {self.svc.partner_state(pn)}")
        self.info.setText(" · ".join(parts))
        self._fill_scopes()

    def current_rel(self) -> dict | None:
        r = self.rel_grid.current()
        return next((x for x in self.svc.failovers if x["name"] == r["name"]), None) if r else None

    def _fill_scopes(self) -> None:
        tr = self.tr
        rel = self.current_rel()
        if not rel:
            self.sc_grid.set_rows([])
            self.sc_title.setText(tr("fo.scopes"))
            return
        self.sc_title.setText(tr("fo.scopes_of", name=rel["name"], partner=rel["partner"]))
        cmp = self.compare.get(rel["name"], {})
        rows = []
        by_id = {s["id"]: s for s in self.svc.scopes}
        for sid in rel["scopes"]:
            s = by_id.get(sid) or {}
            st, detail = cmp.get(sid, ("", ""))
            if st.startswith("diff:"):
                sync_t = tr("fo.sync.diff", n=st.split(":")[1])
            else:
                sync_t = tr("fo.sync." + st) if st else "–"
            rows.append({"id": sid, "name": s.get("name", ""), "state_t": tr("state." + s["state"]) if s else tr("fo.sc_missing"),
                         "sync": st, "sync_t": sync_t, "detail": detail})
        self.sc_grid.set_rows(rows)
        c = theme.current
        for r in rows:
            if r["sync"]:
                col = c["success"] if r["sync"] == "sync" else c["danger"]
                self.sc_grid.style_cell(r["id"], "sync_t", fore=col, bold=r["sync"] != "sync")
        self.sc_grid.autosize(260)

    # --- Abläufe --------------------------------------------------------------------------------------
    def _reload(self):
        yield Job(self.svc.load_failovers, self.tr("status.loading"))
        self.refresh()
        yield from self.ctl.refresh_overview_rows()

    def _rel_action(self, a: str) -> None:
        rel = self.current_rel()
        if a == "Refresh":
            self.ctl.run(self._reload())
        elif a == "New":
            self.ctl.run(self.new_flow())
        elif not rel:
            return
        elif a == "Edit":
            self.ctl.run(self.edit_flow(rel))
        elif a == "AddScopes":
            self.ctl.run(self.add_scopes_flow(rel))
        elif a == "Replicate":
            self.ctl.run(self.ctl.replicate_rel_flow(rel))
        elif a == "Compare":
            self.ctl.run(self.compare_flow(rel, list(rel["scopes"])))
        elif a == "ApiRaw":
            self.ctl.run(self.raw_flow(rel))
        elif a == "Remove":
            self.ctl.run(self.remove_flow(rel))

    def _sc_action(self, a: str) -> None:
        rel = self.current_rel()
        ids = [r["id"] for r in self.sc_grid.selected_rows()]
        if not rel or not ids:
            return
        if a == "Open":
            for sid in ids:
                self.ctl.open_scope(sid)
        elif a == "Replicate":
            self.ctl.run(self.ctl.replicate_ids_flow(ids))
        elif a == "Compare":
            self.ctl.run(self.compare_flow(rel, ids))
        elif a == "Remove":
            self.ctl.run(self.remove_scopes_flow(rel, ids))

    def _free_scopes(self) -> list[tuple[str, str]]:
        return [(s["id"], f"{s['id']}/{ip.prefix_len(s['mask'])}  {s['name']}") for s in self.svc.scopes
                if s["id"] not in self.svc.scope_fo]

    def new_flow(self):
        tr, svc = self.tr, self.svc
        free = self._free_scopes()
        if not free:
            info(self, tr("fo.new"), tr("fo.no_free_scopes"))
            return
        spec = dlg.failover_dialog(self, tr, self.ctl.known_servers(), svc.server, None, free)
        if not spec:
            return
        if any(r["name"].lower() == spec["name"].lower() for r in svc.failovers):
            warn(self, tr("fo.new"), tr("fo.err_exists", name=spec["name"]))
            return
        if not confirm(self, tr("fo.new"), tr("fo.confirm_new", name=spec["name"], partner=spec["partner"],
                                             mode=ck.fo_mode(spec, tr), n=len(spec["scopes"]))):
            return
        warns = yield Job(lambda: svc.new_relationship(spec), tr("status.fo_create", name=spec["name"]))
        self.ctl.remember_server(spec["partner"])
        if warns:
            warn(self, tr("fo.new"), tr("scope.fo.add_warn", list=short_list(warns, 10)))
        yield from self._reload()
        self.rel_grid.select_key(spec["name"])

    def edit_flow(self, rel):
        tr, svc = self.tr, self.svc
        p = dlg.failover_dialog(self, tr, self.ctl.known_servers(), svc.server, rel)
        if not p:
            return
        yield Job(lambda: svc.set_relationship(rel, p), tr("status.fo_change", name=rel["name"]))
        yield from self._reload()

    def add_scopes_flow(self, rel):
        tr, svc = self.tr, self.svc
        free = self._free_scopes()
        if not free:
            info(self, tr("fo.add_scopes"), tr("fo.no_free_scopes"))
            return
        res = dlg.checklist_dialog(self, tr, tr("fo.add_scopes"), tr("fo.add_scopes_hint", name=rel["name"], partner=rel["partner"]),
                                   free)
        if not res:
            return
        ids = res[0]
        warns = yield Job(lambda: svc.add_fo_scopes(rel, ids), tr("status.fo_add", id=", ".join(ids), name=rel["name"]))
        if warns:
            warn(self, tr("fo.add_scopes"), tr("scope.fo.add_warn", list=short_list(warns, 10)))
        yield from self._reload()

    def compare_flow(self, rel, ids):
        tr, svc = self.tr, self.svc
        svc.cancel.clear()
        res = yield Job(lambda: svc.compare_relationship(rel, ids), tr("status.comparing_rel", name=rel["name"]), cancellable=True)
        self.compare.setdefault(rel["name"], {}).update(res)
        self._fill_scopes()
        bad = [k for k, v in res.items() if v[0] != "sync"]
        svc.log(tr("log.compare_done", name=rel["name"], n=len(res), bad=len(bad)), bool(bad))
        for sid, v in res.items():
            tab = self.ctl.scope_tab(sid)
            if tab is not None and v[0] == "sync" and tab.unreplicated:
                tab.set_unreplicated(False)

    def raw_flow(self, rel):
        text = yield Job(lambda: self.svc.fo_raw_text(rel), self.tr("status.loading"))
        text_dialog(self, self.tr("fo.raw"), text, self.tr("ui.close"))

    def remove_flow(self, rel):
        tr, svc = self.tr, self.svc
        if not dlg.confirm_typed(self, tr, tr("fo.remove"), tr("fo.confirm_remove", name=rel["name"], partner=rel["partner"],
                                                                 n=len(rel["scopes"])), rel["name"]):
            return
        errs = yield Job(lambda: svc.remove_relationship(rel), tr("status.fo_remove_rel", name=rel["name"]))
        if errs:
            warn(self, tr("fo.remove"), short_list(errs, 10))
        self.compare.pop(rel["name"], None)
        yield from self._reload()

    def remove_scopes_flow(self, rel, ids):
        tr, svc = self.tr, self.svc
        all_ids = not [x for x in rel["scopes"] if x not in ids]
        text = tr("fo.confirm_remove_scopes_all" if all_ids else "fo.confirm_remove_scopes", name=rel["name"],
                  partner=rel["partner"], list=short_list(ids))
        if not confirm(self, tr("fo.sc_remove"), text):
            return
        errs = yield Job(lambda: svc.remove_fo_scopes(rel, ids), tr("status.fo_remove", id=", ".join(ids)))
        if errs:
            warn(self, tr("fo.sc_remove"), short_list(errs, 10))
        yield from self._reload()


# --- Optionsdefinitionen ------------------------------------------------------------------------------

class DefsPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.svc = ctl.svc
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("ui.filter"))
        self.filter.setClearButtonEnabled(True)
        lay.addWidget(self.filter)
        acts = [("Edit", tr("def.edit"), "F2"), ("ToPartner", tr("def.to_partner"), ""), "-", ("Remove", tr("def.remove"), "Del"),
                "-", ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.grid = Grid([("id", tr("def.col.id"), "opt"), ("name", tr("def.col.name"), "text"), ("type", tr("def.col.type"), "text"),
                          ("multi", tr("def.col.multi"), "text"), ("vendor", tr("def.col.vendor"), "text"),
                          ("desc", tr("def.col.desc"), "text"), ("default_t", tr("def.col.default"), "text")],
                         key_fn=lambda r: f"{r['vendor']}|{r['id']}", actions=acts, default_action="Edit", stretch="desc")
        self.grid.action.connect(self._action)
        self.filter.textChanged.connect(self.grid.apply_filter)
        lay.addWidget(self.grid, 1)
        bar = ButtonBar([("Refresh", tr("ui.refresh")), ("New", tr("def.new")), ("Edit", tr("def.edit")),
                         ("Remove", tr("def.remove")), ("ToPartner", tr("def.to_partner"))], primary=("New",))
        bar.action.connect(self._action)
        lay.addWidget(bar)
        lay.addWidget(hint_label(tr("def.note")))

    def refresh(self) -> None:
        rows = [dict(d, default_t=", ".join(d["default"])) for d in sorted(self.svc.defs.values(), key=lambda d: (d["vendor"], d["id"]))]
        self.grid.set_rows(rows)
        self.grid.autosize(320)
        self.grid.apply_filter(self.filter.text())

    def _action(self, a: str) -> None:
        cur = self.grid.current()
        if a == "Refresh":
            self.ctl.run(self._reload())
        elif a == "New":
            self.ctl.run(self.ctl.new_definition_flow({}))
        elif a == "Edit" and cur:
            self.ctl.run(self.edit_flow(cur))
        elif a == "Remove" and cur:
            self.ctl.run(self.remove_flow(cur))
        elif a == "ToPartner" and self.grid.selected_rows():
            self.ctl.run(self.to_partner_flow(self.grid.selected_rows()))

    def _reload(self):
        yield Job(self.svc.load_defs, self.tr("status.loading"))
        self.refresh()

    def edit_flow(self, d):
        tr, svc = self.tr, self.svc
        res = dlg.definition_dialog(self, tr, d)
        if not res:
            return
        res.update(id=d["id"], vendor=d["vendor"], type=d["type"], multi=d["multi"])
        yield Job(lambda: svc.def_set(res), tr("status.saving"))
        svc.log(tr("log.def_changed", tag=f"{d['id']:03d}", name=res["name"]))
        yield from self._reload()

    def remove_flow(self, d):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("def.remove"), tr("def.confirm_remove", tag=f"{d['id']:03d}", name=d["name"])):
            return
        yield Job(lambda: svc.def_remove(d["id"], d["vendor"]), tr("status.saving"))
        svc.log(tr("log.def_removed", tag=f"{d['id']:03d}", name=d["name"]))
        yield from self._reload()

    def to_partner_flow(self, rows):
        tr, svc = self.tr, self.svc
        partners = svc.partners()
        if not partners:
            info(self, tr("def.to_partner"), tr("srvopt.no_partner"))
            return
        out = []

        def work():
            for pn in partners:
                for d in rows:
                    try:
                        out.append(tr("def.copied" if svc.copy_def_to_partner(d, pn) else "def.exists",
                                      tag=f"{d['id']:03d}", partner=pn))
                    except Exception as e:  # noqa: BLE001
                        out.append(tr("err.def_partner", tag=f"{d['id']:03d}", partner=pn, error=str(e)))
        yield Job(work, tr("status.to_partner"))
        info(self, tr("def.to_partner"), short_list(out, 20))


# --- Prüfung ------------------------------------------------------------------------------------------

class Tile(QFrame):
    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        self.setStyleSheet(f"QFrame#tile {{ border:1px solid {theme.current['border']}; border-left:4px solid {color};"
                           f" border-radius:6px; background:{theme.current['surface']}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.value = QLabel("–")
        f = self.value.font()
        f.setPointSizeF(f.pointSizeF() * 1.8)
        f.setBold(True)
        self.value.setFont(f)
        self.value.setStyleSheet(f"color:{color};")
        lay.addWidget(self.value)
        t = QLabel(title)
        t.setStyleSheet(f"color:{theme.current['muted']};")
        lay.addWidget(t)


class CheckPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.svc = ctl.svc
        self.scan: dict | None = None
        self.only = False
        self.search = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.bar = ButtonBar([("Scan", tr("chk.scan"))], primary=("Scan",))
        self.bar.action.connect(lambda _a: self.ctl.run(self.scan_flow()))
        top.addWidget(self.bar)
        self.with_leases = QCheckBox(tr("chk.with_leases"))
        self.with_leases.setToolTip(tr("chk.with_leases_tip"))
        self.with_partner = QCheckBox(tr("chk.with_partner"))
        self.with_partner.setChecked(True)
        top.addWidget(self.with_leases)
        top.addWidget(self.with_partner)
        self.state = QLabel(tr("chk.not_run"))
        self.state.setStyleSheet(f"color:{theme.current['muted']};")
        top.addWidget(self.state, 1)
        lay.addLayout(top)
        tiles = QGridLayout()
        self.tiles: dict[str, Tile] = {}
        for i, lv in enumerate(ck.LEVELS):
            t = Tile(level_name(tr, lv, True), level_color(lv))
            self.tiles[lv] = t
            tiles.addWidget(t, 0, i)
        self.t_scopes = Tile(tr("chk.tile_scopes"), theme.current["accent"])
        tiles.addWidget(self.t_scopes, 0, 4)
        lay.addLayout(tiles)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.srv_view = FindingsView(tr, ctl.flt, show_scope=True, scope_mode=True)
        self.srv_view.empty_text = tr("chk.server_none")
        self.srv_view.activated.connect(lambda f, _m: f.scope_id and self.ctl.open_scope(f.scope_id))
        self.tabs.addTab(self.srv_view, tr("chk.tab_server"))
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        self.sc_bar = FindingsToolbar(tr, ctl.flt, scope_list=True)
        self.sc_bar.search_changed.connect(self._search)
        self.sc_bar.only_with.connect(self._only)
        wl.addWidget(self.sc_bar)
        self.sc_grid = Grid([("id", tr("ov.col.id"), "ip"), ("name", tr("ov.col.name"), "text"),
                             ("state_t", tr("ov.col.state"), "text"), ("rating", tr("chk.col.rating"), "text"),
                             ("e", level_name(tr, ck.ERROR, True), "int"), ("w", level_name(tr, ck.WARN, True), "int"),
                             ("b", level_name(tr, ck.BP, True), "int"), ("i", level_name(tr, ck.INFO, True), "int"),
                             ("top", tr("chk.col.top"), "text")], key_fn=lambda r: r["id"],
                            actions=[("Open", tr("ov.open"), ""), ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")],
                            default_action="Open", stretch="top")
        self.sc_grid.action.connect(self._sc_action)
        wl.addWidget(self.sc_grid, 1)
        self.tabs.addTab(w, tr("chk.tab_scopes"))
        lay.addWidget(self.tabs, 1)
        ctl.flt.changed.connect(self.refresh)

    def _search(self, t: str) -> None:
        self.search = t
        self.refresh()

    def _only(self, on: bool) -> None:
        self.only = on
        self.refresh()

    def _sc_action(self, a: str) -> None:
        r = self.sc_grid.current()
        if a == "Open" and r:
            self.ctl.open_scope(r["id"], show_findings=True)

    def scan_flow(self):
        tr, svc = self.tr, self.svc
        wl, wp = self.with_leases.isChecked(), self.with_partner.isChecked()
        self.state.setText(tr("chk.running"))
        try:
            scan = yield Job(lambda: svc.scan(wl, wp), tr("scan.loading"), cancellable=True)
        except Exception:
            self.state.setText(tr("chk.failed"))
            raise
        self.ctl.set_scan(scan)
        svc.log(tr("log.scan_done", n=len(scan["scopes"]), sec=scan["seconds"]))

    def set_scan(self, scan: dict | None) -> None:
        self.scan = scan
        self.refresh()

    def refresh(self) -> None:
        tr = self.tr
        scan = self.scan
        flt = self.ctl.flt
        if not scan:
            return
        self.state.setText(tr("chk.state_partial" if scan.get("partial") else "chk.state", time=scan["time"], sec=scan["seconds"],
                              n=len(scan["scopes"])) + ("  " + tr("chk.state_leases") if scan.get("with_leases") else ""))
        allf = list(scan["server"])
        for v in scan["scopes"].values():
            allf += v["findings"]
        for lv, t in self.tiles.items():
            t.value.setText(str(sum(1 for f in allf if f.level == lv and flt.visible(f, ignore_level=True))))
        clean = sum(1 for v in scan["scopes"].values()
                    if not [f for f in v["findings"] if f.level in (ck.ERROR, ck.WARN)])
        self.t_scopes.value.setText(f"{clean}/{len(scan['scopes'])}")
        self.srv_view.set_findings(scan["server"])
        rows = []
        for sid, v in scan["scopes"].items():
            fs = [f for f in v["findings"] if flt.visible(f, self.search, None, True, tr)]
            shown = [f for f in fs if flt.levels.get(f.level, True)]
            if self.only and not [f for f in shown if f.level != ck.INFO]:
                continue
            c = {lv: sum(1 for f in fs if f.level == lv) for lv in ck.LEVELS}
            lvl = ck.worst([f for f in fs if f.level != ck.INFO])
            top = next((f.text for f in shown if f.level != ck.INFO), "")
            rows.append({"id": sid, "name": v["scope"]["name"], "state_t": tr("state." + v["scope"]["state"]),
                         "rating": tr("chk.rating." + (lvl or "ok")), "e": c[ck.ERROR], "w": c[ck.WARN], "b": c[ck.BP],
                         "i": c[ck.INFO], "top": top, "_lvl": lvl})
        self.sc_grid.set_rows(rows)
        for r in rows:
            self.sc_grid.style_cell(r["id"], "rating", fore=level_color(r["_lvl"]), bold=r["_lvl"] == ck.ERROR)
            if r["_lvl"]:
                self.sc_grid.style_cell(r["id"], "id", back=tint(level_color(r["_lvl"]), 40))
        self.sc_grid.autosize(260)
        cnt = {lv: sum(1 for v in scan["scopes"].values() for f in v["findings"] if f.level == lv) for lv in ck.LEVELS}
        self.sc_bar.sync(cnt, [f for v in scan["scopes"].values() for f in v["findings"]])
        self.sc_bar.set_count(tr("chk.scopes_count", shown=len(rows), total=len(scan["scopes"])))
        n_srv = sum(1 for f in scan["server"] if f.level in (ck.ERROR, ck.WARN))
        self.tabs.setTabText(0, tr("chk.tab_server") + (f" ({n_srv})" if n_srv else ""))
        self.tabs.setTabIcon(0, level_icon(ck.worst([f for f in scan["server"] if f.level != ck.INFO]) or None))

