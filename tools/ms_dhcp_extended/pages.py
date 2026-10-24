"""Feste Seiten des Hauptbereichs: Übersicht, Server-Optionen, Failover, Optionsdefinitionen und Prüfung.

Übersicht, Server-Optionen und Definitionen zeigen die oben gewählte Adressfamilie (ctl.family 4/6);
Failover gibt es nur für IPv4, die Prüfung umfasst immer beide Familien.
"""

from __future__ import annotations

import html

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSplitter,
    QStackedWidget, QToolTip, QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from . import checks as ck
from . import checks6 as ck6
from . import dialogs as dlg
from . import ip6calc as ip6
from . import ipcalc as ip
from . import optcodec as oc
from .editors import OptionsPanel, opt_row_key, option_rows
from .runner import Job
from .service import UserError
from .ui_base import (
    ButtonBar, FindingsToolbar, FindingsView, Grid, bold_label, choose, confirm, finding_tip, help_icon, hint_label, info,
    level_color, level_name, short_list, text_dialog, tint, warn,
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
        # Reihenfolge = Standardanordnung; die Spalten lassen sich verschieben und über den Spaltenkopf ein-/ausblenden
        self.grid = Grid([("name", tr("ov.col.name"), "text"), ("desc", tr("ov.col.desc"), "text"),
                          ("id", tr("ov.col.id"), "ip"), ("prefix", tr("ov.col.prefix"), "int"),
                          ("state_t", tr("ov.col.state"), "text"), ("free", tr("ov.col.free"), "int"),
                          ("pct", tr("ov.col.pct"), "float"), ("lease_t", tr("ov.col.lease"), "text"),
                          ("find", tr("ov.col.findings"), "text"), ("fo", tr("ov.col.failover"), "text"),
                          ("usable", tr("ov.col.usable"), "int"), ("ranges", tr("ov.col.ranges"), "text")],
                         key_fn=lambda r: r["id"], actions=acts, default_action="Edit")
        self.grid.enable_layout(ctl.settings, "overview_columns", hidden=("usable", "ranges"),
                                labels=(tr("ui.columns"), tr("ui.columns_reset")))
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
        if self.ctl.family == 6:
            return self._set_rows(self._rows6(svc, scan))
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
                         "usable": inf.get("usable", 0), "free": st["free"] if st else None,
                         "state": s["state"], "state_t": tr("state." + s["state"]),
                         "fo": f"{rel['name']} ({ck.fo_state(rel.get('state', ''), tr)})" if rel else "–",
                         "lease_t": ck.format_lease(s["lease"], tr), "pct": st["pct"] if st else None, "desc": s["desc"],
                         "find": find if scan else "", "_find": fs, "_rel": rel, "_inf": inf, "_stat": st})
        self._set_rows(rows)

    def _rows6(self, svc, scan: dict | None) -> list[dict]:
        tr = self.tr
        rows = []
        for s in svc.scopes6:
            inf = svc.scope_info6.get(s["id"]) or {}
            st = inf.get("stat")
            fs = ((scan or {}).get("scopes", {}).get(s["id"]) or {}).get("findings") or []
            cnt = {lv: sum(1 for f in fs if f.level == lv) for lv in (ck.ERROR, ck.WARN)}
            find = " · ".join(f"{level_name(tr, lv, cnt[lv] != 1)} {cnt[lv]}" for lv in cnt if cnt[lv])
            ex = inf.get("exclusions") or []
            rows.append({"id": s["id"], "prefix": s["plen"], "name": s["name"], "ranges": tr("ov.excl_n", n=len(ex)) if ex else "",
                         "usable": None, "free": None, "state": s["state"], "state_t": tr("state." + s["state"]),
                         "fo": tr("ov.no_fo6"), "lease_t": ck.format_lease(s["lease_valid"], tr), "pct": None,
                         "desc": s["desc"], "find": find if scan else "", "_find": fs, "_rel": None, "_inf": inf, "_stat": st,
                         "_v6": True})
        return rows

    def _set_rows(self, rows: list[dict]) -> None:
        self.grid.set_rows(rows)
        c = theme.current
        for r in rows:
            k = r["id"]
            if r["state"] != "Active":
                self.grid.style_cell(k, "state_t", fore=c["muted"])
            rel = r["_rel"]
            if r.get("_v6"):
                self.grid.style_cell(k, "fo", fore=c["muted"])
            else:
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

    def apply_rights(self, rw: bool) -> None:
        for aid in ("New", "Duplicate", "Activate", "Deactivate", "Remove"):
            self.bar.set_visible(aid, rw)
            self.grid.set_action_visible(aid, rw)

    def _tip(self, r: dict) -> str:
        tr = self.tr
        inf = r["_inf"]
        lines = [f"{r['id']}/{r['prefix']}  {r['name']}"]
        if r.get("_v6"):
            ex = inf.get("exclusions") or []
            if ex:
                lines.append(tr("ov.tip.exclusions", list=", ".join(ip6.fmt_range(x) for x in ex[:6]) + (" …" if len(ex) > 6 else "")))
            if r["_stat"]:
                lines.append(tr("scope6.stats", in_use=r["_stat"]["in_use"], pending=r["_stat"].get("pending", 0)))
            if r["_find"]:
                lines += ["", finding_tip(tr, [f for f in r["_find"] if f.level != ck.INFO], 8)]
            return "\n".join(lines)
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

SKIP_SYNC = (51, 81)      # Lease-Dauer und interne DNS-Einstellungen dürfen je Server abweichen


class ServerOptionsPage(QWidget):
    """Oben die Server der Failover-Gruppe (verbundener Server + Partner), darunter die Server-Optionen des
    gewählten Servers mit Abgleichstatus gegenüber dem Gegenüber und den Befunden dazu."""

    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.svc = ctl.svc
        self.current: str | None = None
        self.findings: list[ck.Finding] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        sp = QSplitter(Qt.Orientation.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        th = QHBoxLayout()
        th.addWidget(bold_label(tr("srvopt.servers")))
        th.addWidget(help_icon(tr("srvopt.servers_hint")))
        th.addStretch(1)
        self.srv_bar = ButtonBar([("Refresh", tr("ui.refresh"))])
        self.srv_bar.action.connect(lambda _a: self.ctl.run(self.reload_flow(all_servers=True)))
        th.addWidget(self.srv_bar)
        tl.addLayout(th)
        self.srv_grid = Grid([("server", tr("srvopt.col.server"), "text"), ("role_t", tr("srvopt.col.role"), "text"),
                              ("conn", tr("srvopt.col.conn"), "text"), ("count", tr("srvopt.col.count"), "int"),
                              ("diff", tr("srvopt.col.diff"), "int")], key_fn=lambda r: r["server"].lower(),
                             actions=[("CopyCell", tr("ui.copy_cell"), "Ctrl+C")], multi=False, stretch="conn")
        self.srv_grid.itemSelectionChanged.connect(self._server_changed)
        tl.addWidget(self.srv_grid, 1)
        sp.addWidget(top)
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(0, 0, 0, 0)
        self.opt_title = bold_label(tr("srvopt.server"))
        ml.addWidget(self.opt_title)
        self.panel = OptionsPanel(tr, server_level=True)
        self.panel.action.connect(self._action)
        ml.addWidget(self.panel, 1)
        sp.addWidget(mid)
        self.fview = FindingsView(tr, ctl.flt)
        self.fview.empty_text = tr("srvopt.no_findings")
        self.fview.activated.connect(self._finding)
        sp.addWidget(self.fview)
        sp.setSizes([140, 380, 180])
        lay.addWidget(sp, 1)

    # --- Daten ----------------------------------------------------------------------------------------
    @property
    def v6(self) -> bool:
        """DHCPv6-Ansicht: nur der verbundene Server (für DHCPv6 gibt es kein Failover und keine Partner)."""
        return self.ctl.family == 6

    def servers(self) -> list[str]:
        out = [self.svc.server] if self.svc.server else []
        if self.svc.partner_mode != "Off" and not self.v6:
            out += self.svc.partners()
        return out

    def options_of(self, server: str) -> list[dict] | None:
        if self.svc.is_local(server):
            return list(self.svc.server_option_rows6 if self.v6 else self.svc.server_option_rows)
        return None if self.v6 else (self.svc.peer.get(server) or {}).get("options")

    def targets(self, server: str | None) -> list[str]:
        """Gegenüber eines Servers: für den verbundenen Server alle Partner, für einen Partner der verbundene Server."""
        if self.svc.partner_mode == "Off" or not server or self.v6:
            return []
        return self.svc.partners() if self.svc.is_local(server) else [self.svc.server]

    def _form(self, o: dict) -> str:
        return oc.compare_form(o["values"], self.svc.opt_def(int(o["id"]), o.get("vendor") or "", self.v6))

    def compare(self, server: str) -> dict[str, list[tuple[str, str, dict | None]]]:
        """Je Option: [(Gegenüber, same|diff|missing|only, Option des Gegenübers)] – nur geladene Gegenüber."""
        mine = {opt_row_key(o): o for o in self.options_of(server) or []}
        out: dict[str, list] = {}
        for other in self.targets(server):
            theirs_l = self.options_of(other)
            if theirs_l is None:
                continue
            theirs = {opt_row_key(o): o for o in theirs_l}
            for k in set(mine) | set(theirs):
                o = mine.get(k) or theirs.get(k)
                if not o.get("vendor") and not o.get("user") and int(o["id"]) in SKIP_SYNC:
                    continue
                a, b = mine.get(k), theirs.get(k)
                st = "only" if a is None else "missing" if b is None else "same" if self._form(a) == self._form(b) else "diff"
                out.setdefault(k, []).append((other, st, b))
        return out

    def set_options(self, options: list[dict]) -> None:
        """Vom Hauptfenster nach dem Laden des verbundenen Servers."""
        self.refresh()

    def refresh(self) -> None:
        tr = self.tr
        rows = []
        for srv in self.servers():
            opts = self.options_of(srv)
            local = self.svc.is_local(srv)
            err = "" if local else (self.svc.peer.get(srv) or {}).get("errors", {}).get("options", "")
            diff = sum(1 for lst in self.compare(srv).values() if any(st != "same" for _o, st, _b in lst)) if opts is not None else None
            conn = tr("srvopt.connected") if local else self.svc.partner_state(srv)
            if not self.svc.can_write(srv):
                conn += "" if not local else " · " + tr("conn.read_only")
            if opts is None:
                conn += " · " + (tr("srvopt.load_error", error=err) if err else tr("srvopt.not_loaded"))
            rows.append({"server": srv, "role_t": tr("srvopt.role_local") if local else tr("srvopt.role_partner"),
                         "conn": conn, "count": len(opts) if opts is not None else None, "diff": diff})
        self.srv_grid.set_rows(rows)
        c = theme.current
        for r in rows:
            if r["diff"]:
                self.srv_grid.style_cell(r["server"].lower(), "diff", fore=c["danger"], bold=True)
        self.srv_grid.autosize(320)
        if self.current is None or not self.srv_grid.select_key(self.current.lower()):
            if rows:
                self.srv_grid.select_key(rows[0]["server"].lower())
        self._fill()

    def _server_changed(self) -> None:
        r = self.srv_grid.current()
        if not r or (self.current and r["server"].lower() == self.current.lower()):
            return
        self.current = r["server"]
        if self.options_of(self.current) is None and not self.svc.is_local(self.current):
            self.ctl.run(self.reload_flow(server=self.current))
        else:
            self._fill()

    def _fill(self) -> None:
        tr = self.tr
        srv = self.current or self.svc.server
        if not srv:
            return
        opts = self.options_of(srv)
        self.opt_title.setText(tr("srvopt.options_of", server=srv) + (" – DHCPv6" if self.v6 else ""))
        cmp = self.compare(srv)
        rows = option_rows(opts or [], self.svc.defs_of(self.v6))
        # nur die Optionen dieses Servers; was nur auf dem Gegenüber existiert, steht dort als „Fehlt auf …“
        for r in rows:
            lst = cmp.get(opt_row_key(r))
            if not self.targets(srv):
                r["sync"], r["sync_t"] = "", ""
            elif lst is None:
                skip = not r["vendor"] and not r["user"] and r["id"] in SKIP_SYNC
                r["sync"], r["sync_t"] = "", tr("srvopt.sync.skip") if skip else tr("srvopt.sync.unknown")
            else:
                bad = [(o, st) for o, st, _b in lst if st != "same"]
                if not bad:
                    r["sync"], r["sync_t"] = "sync", tr("srvopt.sync.same")
                elif any(st == "diff" for _o, st in bad):
                    r["sync"], r["sync_t"] = "diff", tr("srvopt.sync.diff", server=", ".join(o for o, st in bad if st == "diff"))
                else:
                    r["sync"], r["sync_t"] = "missing", tr("srvopt.sync.missing", server=", ".join(o for o, _st in bad))
        self.panel.set_rows(rows)
        self._findings(srv, opts or [], cmp)
        self.apply_rights()

    def _findings(self, srv: str, opts: list[dict], cmp: dict) -> None:
        tr = self.tr
        checker = self.ctl.checker()
        fs = []
        for o in opts:
            key = ck.option_key(o["id"], o["vendor"], o["user"])
            found = ck6.option_values(checker, o["id"], o["values"], o["vendor"], area="server_options") if self.v6 else \
                checker.option_values(o["id"], o["values"], o["vendor"], None, area="server_options")
            for f in found:
                f.targets = [key]
                f.obj = tr("obj.server_option6" if self.v6 else "obj.server_option", tag=f"{o['id']:03d}")
                fs.append(f)
        if not self.v6 and any(o["id"] == 3 and not o["vendor"] and not o["user"] for o in opts):
            fs.append(ck.Finding(ck.WARN, "server_options", tr("chk.srv_o3"), [ck.option_key(3)],
                                 tr("obj.server_option", tag="003")))
        mine = {opt_row_key(o): o for o in opts}
        self._only_on: dict[str, str] = {}      # Option fehlt hier -> „Anzeigen“ springt zum Server, der sie hat
        for k, lst in cmp.items():
            for other, st, b in lst:
                if st == "same":
                    continue
                o = mine.get(k) or b
                tag = f"{int(o['id']):03d}"
                a_t = ", ".join(mine[k]["values"]) if k in mine else "–"
                b_t = ", ".join(b["values"]) if b else "–"
                key = {"diff": "chk.srv_partner_opt", "missing": "chk.srv_partner_opt_missing"}.get(st, "chk.srv_partner_opt_only")
                if st == "only":
                    self._only_on.setdefault(k, other)
                fs.append(ck.Finding(ck.WARN, "server_options", tr(key, tag=tag, partner=other, a=a_t, b=b_t),
                                     [k], tr("obj.server_option", tag=tag)))
        self.findings = ck.sort_findings(fs)
        idx: dict[str, list[ck.Finding]] = {}
        for f in self.findings:
            for t in f.targets:
                idx.setdefault(t, []).append(f)
        self.panel.mark(idx, self.ctl.flt)
        self.fview.set_findings(self.findings)

    def apply_rights(self) -> None:
        srv = self.current or self.svc.server
        rw = self.svc.can_write(srv)
        tp = any(self.svc.can_write(t) for t in self.targets(srv))
        self.panel.apply_rights(rw, tp)

    # --- Abläufe --------------------------------------------------------------------------------------
    def _finding(self, f, _mode) -> None:
        if f.targets:
            k = f.targets[0]
            other = getattr(self, "_only_on", {}).get(k)
            if other and not self.panel.grid.select_key(k):
                self.srv_grid.select_key(other)
                self.panel.grid.select_key(k)
                return
            if f.fix == "new_def":
                self.ctl.run(self._after(self.ctl.new_definition_flow({"id": f.fix_arg["id"], "vendor": f.fix_arg["vendor"],
                                                                       "v6": self.v6}), [self.svc.server]))

    def load_flow(self):
        yield from self.reload_flow(server=self.svc.server)

    def reload_flow(self, server: str | None = None, all_servers: bool = False, servers: list[str] | None = None):
        tr, svc = self.tr, self.svc
        lst = self.servers() if all_servers else (servers or [server or svc.server])
        for srv in lst:
            if svc.is_local(srv):
                yield Job(svc.load_server_options6 if self.v6 else svc.load_server_options, tr("status.loading"))
            else:
                def work(srv=srv):
                    d = svc.peer.setdefault(srv, {"fo": None, "scopes": None, "options": None, "errors": {}})
                    try:
                        d["options"] = svc.srv_options(srv)
                        d["errors"].pop("options", None)
                    except Exception as e:  # noqa: BLE001 - Fehler wird in der Serverliste angezeigt
                        d["errors"]["options"] = str(e)
                yield Job(work, tr("status.peer_options", partner=srv))
        self.refresh()

    def _after(self, gen, servers):
        yield from gen
        yield from self.reload_flow(servers=servers)

    def _action(self, a: str) -> None:
        g = self.panel.grid
        srv = self.current or self.svc.server
        if a == "Add":
            self.ctl.run(self.option_flow(srv, None))
        elif a == "Edit" and g.current():
            self.ctl.run(self.option_flow(srv, g.current()))
        elif a == "Remove" and [r for r in g.selected_rows() if not r.get("ghost")]:
            self.ctl.run(self.remove_flow(srv, [r for r in g.selected_rows() if not r.get("ghost")]))
        elif a == "Copy" and g.selected_rows():
            rows = [r for r in g.selected_rows() if not r.get("ghost")]
            self.ctl.clip_set("Options", [{"id": r["id"], "values": r["values"], "vendor": r["vendor"], "user": r["user"]}
                                          for r in rows], "", "", g.rows_as_text(rows))
        elif a == "Paste":
            self.ctl.run(self.paste_flow(srv))
        elif a == "ToPartner":
            rows = g.selected_rows()
            if len(rows) == 1 and not rows[0].get("ghost"):
                self.ctl.run(self.to_partner_flow(srv, rows[0]))

    def _guard(self, servers: list[str]):
        """Vor dem Schreiben: Hat jemand anderes die Server-Optionen seit dem Laden geändert? True = schreiben."""
        tr, svc = self.tr, self.svc

        def conf(rows):
            return svc.config_of({"options": rows or []})
        diffs = []
        for srv in servers:
            before = self.options_of(srv)
            if before is None:
                continue
            fresh = yield Job(lambda srv=srv: svc.srv_options(srv, self.v6), tr("status.conflict_check", id=srv))
            diffs += [f"{srv}: {d}" for d in svc.diff_config(conf(before), conf(fresh))]
        if not diffs:
            return True
        svc.log(tr("log.conflict", id=", ".join(servers), n=len(diffs)), True)
        ans = choose(self, tr("conf.title"), tr("conf.conflict_srv", list=short_list(diffs, 12)),
                     [("reload", tr("conf.btn_reload")), ("overwrite", tr("conf.btn_overwrite")), ("cancel", tr("ui.cancel"))],
                     "reload")
        if ans == "reload":
            yield from self.reload_flow(servers=servers)
        return ans == "overwrite"

    def _write_targets(self, srv: str) -> list[str]:
        return [t for t in self.targets(srv) if self.svc.can_write(t)]

    def option_flow(self, srv: str, row):
        tr, svc, v6 = self.tr, self.svc, self.v6
        vendors, users = yield from self.ctl.load_classes(v6)
        targets = self._write_targets(srv)
        edit = row is not None and not row.get("ghost")
        title = tr("srvopt.title_edit", server=srv) if edit else tr("srvopt.title_add", server=srv)
        res = dlg.option_dialog(self, tr, self.ctl.checker(), svc.defs_of(v6), row, None, vendors, users,
                                title=title + (" – DHCPv6" if v6 else ""),
                                partner_check=tr("opt.f.to_partner", partners=", ".join(targets)) if targets else "", v6=v6)
        if not res:
            return
        if res["undefined"] and not confirm(self, tr("opt.title_add"), tr("opt.confirm_new_def", tag=f"{res['id']:03d}")):
            return
        tag = f"{res['id']:03d}"
        done = [srv] + (targets if res.get("partner") else [])
        if not (yield from self._guard(done)):
            return

        def write():
            # Definition, Option und Partner-Kopie als Einheit: scheitert ein Teil, wird alles zurückgenommen
            if res["undefined"]:
                ok = yield from self.ctl.new_definition_flow({"id": res["id"], "vendor": res["vendor"],
                                                              "type": dlg.guess_type(res["values"]), "v6": v6})
                if not ok:
                    return False
            yield Job(lambda: svc.srv_opt_set(srv, res["id"], res["values"], res["vendor"], res["user"], v6), tr("status.saving"))
            if res.get("partner") and targets:
                yield from self._copy([dict(res)], srv, targets)
            return True
        try:
            if not (yield from self.ctl.atomic(tr("tx.srvopt_set", tag=tag, server=srv), write())):
                return
        finally:
            yield from self.reload_flow(servers=done)
        svc.log(tr("log.srvopt_set_on", tag=tag, server=srv, values=", ".join(res["values"])))

    def _copy(self, opts: list[dict], src: str, targets: list[str]):
        """Optionen von src auf die Ziele schreiben (bei Quelle = verbundener Server vorher eigene Definitionen).
        Bricht beim ersten Fehler ab - in einer Transaktion wird dann alles Geschriebene zurückgenommen."""
        tr, svc = self.tr, self.svc

        def work():
            for t in targets:
                if svc.is_local(src):
                    errs = svc.sync_defs_to_partner(t, [(o["vendor"], int(o["id"])) for o in opts])
                    if errs:
                        raise UserError("; ".join(errs))
                for o in opts:
                    try:
                        svc.srv_opt_set(t, int(o["id"]), o["values"], o["vendor"], o["user"])
                    except UserError as e:
                        raise UserError(f"{t} {int(o['id']):03d}: {e}") from None
                    svc.log(tr("log.srvopt_partner", tag=f"{int(o['id']):03d}", partner=t))
        yield Job(work, tr("status.to_partner"))

    def remove_flow(self, srv: str, rows):
        tr, svc = self.tr, self.svc
        cmp = self.compare(srv)
        targets = self._write_targets(srv)
        also = [t for t in targets if any(o == t and st != "only" and b is not None
                                          for r in rows for o, st, b in cmp.get(opt_row_key(r), []))]
        ok, on_partner = dlg.confirm_check(self, tr("opt.remove"), tr("srvopt.confirm_remove", server=srv,
                                           list=short_list([f"{r['id']:03d} {r['name']}" for r in rows])),
                                           tr("srvopt.remove_partner", partners=", ".join(also)) if also else "")
        if not ok:
            return
        if not (yield from self._guard([srv] + (also if on_partner else []))):
            return

        def write():
            # lokal und (falls gewählt) beim Partner: alles oder nichts
            for r in rows:
                yield Job(lambda r=r: svc.srv_opt_remove(srv, r["id"], r["vendor"], r["user"], self.v6), tr("status.saving"))
                svc.log(tr("log.srvopt_removed_on", tag=f"{r['id']:03d}", server=srv))
            if on_partner:
                def work():
                    for t in also:
                        have = {opt_row_key(o) for o in self.options_of(t) or []}
                        for r in rows:
                            if opt_row_key(r) not in have:
                                continue
                            try:
                                svc.srv_opt_remove(t, r["id"], r["vendor"], r["user"])
                            except UserError as e:
                                raise UserError(f"{t} {r['id']:03d}: {e}") from None
                            svc.log(tr("log.srvopt_removed_on", tag=f"{r['id']:03d}", server=t))
                yield Job(work, tr("status.to_partner"))
        try:
            yield from self.ctl.atomic(tr("tx.srvopt_remove", server=srv), write())
        finally:
            yield from self.reload_flow(servers=[srv] + (also if on_partner else []))

    def paste_flow(self, srv: str):
        tr, svc = self.tr, self.svc
        clip = self.ctl.clip_get()
        if not clip or clip.get("Kind") != "Options" or not clip.get("Items"):
            info(self, tr("ui.paste"), tr("clip.no_options"))
            return
        if (clip.get("Family") or 4) != self.ctl.family:
            info(self, tr("ui.paste"), tr("clip.wrong_family"))
            return
        have = {opt_row_key(r) for r in self.panel.grid.rows if not r.get("ghost")}
        over = [it for it in clip["Items"] if ck.option_key(it["id"], it.get("vendor"), it.get("user")) in have]
        if over and not confirm(self, tr("ui.paste"), tr("clip.overwrite_opts", list=short_list([f"{int(i['id']):03d}" for i in over]))):
            return
        if not (yield from self._guard([srv])):
            return

        def write():
            for it in clip["Items"]:
                yield Job(lambda it=it: svc.srv_opt_set(srv, int(it["id"]), list(it["values"]), it.get("vendor") or "",
                                                        it.get("user") or "", self.v6), tr("status.saving"))
        try:
            yield from self.ctl.atomic(tr("tx.paste", kind=tr("clip.kind.Options"), id=srv), write())
        finally:
            yield from self.reload_flow(servers=[srv])
        svc.log(tr("log.pasted", n=len(clip["Items"]), kind=tr("clip.kind.Options"), id=srv))

    def to_partner_flow(self, srv: str, row):
        tr = self.tr
        targets = self._write_targets(srv)
        if not targets:
            info(self, tr("opt.to_partner"), tr("srvopt.no_partner"))
            return
        if not confirm(self, tr("opt.to_partner"), tr("srvopt.confirm_partner", partners=", ".join(targets),
                                                     list=f"{row['id']:03d} {row['name']} = {row['value']}")):
            return
        if not (yield from self._guard(targets)):
            return
        try:
            yield from self.ctl.atomic(tr("tx.srvopt_partner", tag=f"{row['id']:03d}"), self._copy([row], srv, targets))
        finally:
            yield from self.reload_flow(servers=targets)
        self.ctl.notify(tr("srvopt.partner_done_one", tag=f"{row['id']:03d}", partners=", ".join(targets)))


# --- Failover --------------------------------------------------------------------------------------------

class FailoverPage(QWidget):
    """Eine Failover-Beziehung besteht immer aus genau zwei Servern. Oben steht je Beziehung eine aufklappbare
    Zeile, darunter ihre beiden Server (jeweils aus ihrer eigenen Sicht); unten alle Scopes des gewählten
    Servers – auch die, die in keiner oder einer anderen Beziehung sind."""

    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.svc = ctl.svc
        self.compare: dict[str, dict[str, tuple[str, str]]] = {}
        self._cur_key: str | None = None
        self._open: set[str] = set()      # aufgeklappte Beziehungen (Name klein)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        sp = QSplitter(Qt.Orientation.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        th = QHBoxLayout()
        th.addWidget(bold_label(tr("fo.relationships")))
        th.addWidget(help_icon(tr("fo.concept")))
        th.addStretch(1)
        tl.addLayout(th)
        acts = [("Edit", tr("fo.edit"), "F2"), ("AddScopes", tr("fo.add_scopes"), ""), ("Replicate", tr("fo.replicate"), ""),
                ("Compare", tr("fo.compare"), ""), ("ApiRaw", tr("fo.raw"), ""), ("LoadPeer", tr("fo.load_peer"), ""), "-",
                ("Remove", tr("fo.remove"), "Del"), "-", ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.rel_grid = Grid([("name", tr("fo.col.name"), "text"), ("server", tr("fo.col.server"), "text"),
                              ("partner", tr("fo.col.partner"), "text"), ("mode_t", tr("fo.col.mode"), "text"),
                              ("role_t", tr("fo.col.role"), "text"), ("state_t", tr("fo.col.state"), "text"),
                              ("share", tr("fo.col.share"), "text"), ("mclt_t", tr("fo.col.mclt"), "text"),
                              ("auto_t", tr("fo.col.auto"), "text"), ("count", tr("fo.col.scopes"), "int"),
                              ("auth_t", tr("fo.col.auth"), "text")], key_fn=lambda r: r["key"], actions=acts,
                             multi=False, sortable=False)
        self.rel_grid.setAlternatingRowColors(False)
        self.rel_grid.cellClicked.connect(self._cell_clicked)
        self.rel_grid.cellDoubleClicked.connect(self._cell_double)
        self.rel_grid.installEventFilter(self)
        self.rel_grid.enable_layout(ctl.settings, "failover_tree_columns", labels=(tr("ui.columns"), tr("ui.columns_reset")))
        self.rel_grid.action.connect(self._rel_action)
        self.rel_grid.itemSelectionChanged.connect(self._row_changed)
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
        bh = QHBoxLayout()
        self.sc_title = bold_label(tr("fo.scopes"))
        bh.addWidget(self.sc_title)
        self.sc_sum = QLabel("")
        self.sc_sum.setStyleSheet(f"color:{theme.current['muted']};")
        bh.addWidget(self.sc_sum, 1)
        bl.addLayout(bh)
        sacts = [("Open", tr("fo.sc_open"), ""), ("Replicate", tr("fo.sc_replicate"), ""), ("Compare", tr("fo.sc_compare"), ""),
                 ("AddToRel", tr("fo.sc_add"), ""), "-", ("Remove", tr("fo.sc_remove"), "Del"), "-",
                 ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.sc_grid = Grid([("id", tr("ov.col.id"), "ip"), ("name", tr("ov.col.name"), "text"),
                             ("state_t", tr("ov.col.state"), "text"), ("member_t", tr("fo.col.member"), "text"),
                             ("other_t", tr("fo.col.on_other", server="–"), "text"), ("sync_t", tr("fo.col.sync"), "text"),
                             ("detail", tr("fo.col.detail"), "text")], key_fn=lambda r: r["id"], actions=sacts,
                            default_action="Open", stretch="detail")
        self.sc_grid.action.connect(self._sc_action)
        bl.addWidget(self.sc_grid, 1)
        self.sc_bar = ButtonBar([("Open", tr("fo.sc_open")), ("Replicate", tr("fo.sc_replicate")), ("Compare", tr("fo.sc_compare")),
                                 ("AddToRel", tr("fo.sc_add")), ("Remove", tr("fo.sc_remove"))])
        self.sc_bar.action.connect(self._sc_action)
        bl.addWidget(self.sc_bar)
        sp.addWidget(bottom)
        sp.setSizes([300, 320])
        lay.addWidget(sp, 1)

    # --- Daten ----------------------------------------------------------------------------------------
    def peer_rel(self, rel: dict) -> tuple[dict | None, bool]:
        """Die Beziehung aus Sicht des Partners: (Daten, Partnersicht geladen)."""
        fo = (self.svc.peer.get(rel["partner"]) or {}).get("fo")
        if fo is None:
            return None, False
        return next((x for x in fo if x["name"].lower() == rel["name"].lower()), None), True

    def _mismatch(self, a: dict, b: dict) -> list[str]:
        """Abweichungen zwischen den Sichten der beiden Server (gleiche Beziehung muss spiegelbildlich sein)."""
        tr = self.tr
        out = []
        if a.get("mode") != b.get("mode"):
            out.append(tr("fo.mm.mode"))
        elif a.get("mode") == "LoadBalance":
            if a.get("lb") is not None and b.get("lb") is not None and int(a["lb"]) + int(b["lb"]) != 100:
                out.append(tr("fo.mm.lb", a=a["lb"], b=b["lb"]))
        elif a.get("role") and a.get("role") == b.get("role"):
            out.append(tr("fo.mm.role", role=tr("forole." + a["role"])))
        if int(a.get("mclt") or 0) != int(b.get("mclt") or 0):
            out.append(tr("fo.mm.mclt"))
        sa, sb = set(a.get("scopes") or []), set(b.get("scopes") or [])
        if sa != sb:
            out.append(tr("fo.mm.scopes", a=len(sa - sb), b=len(sb - sa)))
        return out

    def _row(self, rel: dict, server: str, data: dict | None, view: str, mm: list[str]) -> dict:
        tr = self.tr
        d = data or {}
        lb = d.get("mode") == "LoadBalance"
        local = view == "local"
        if data is None:
            state_t = tr("fo.peer_missing") if view == "missing" else tr("fo.peer_not_loaded")
        else:
            state_t = ck.fo_state(d.get("state", ""), tr)
        if not d:
            share = role_t = mode_t = mclt_t = auto_t = auth_t = "–"
            count = None
        else:
            mode_t = tr("fo.mode_lb") if lb else tr("fo.mode_hs")
            role_t = "–" if lb else tr("forole." + (d.get("role") or "Active"))
            share = (f"{d.get('lb')} %" if d.get("lb") is not None else "–") if lb else tr("fo.share_reserve", pct=d.get("reserve"))
            mclt_t = ck.format_duration(d.get("mclt"))
            auto_t = ck.format_duration(d.get("interval")) if d.get("auto") else tr("ui.off")
            auth_t = tr("ui.on") if d.get("auth") else tr("ui.off")
            count = len(d.get("scopes") or [])
        partner = rel["partner"] if local else (d.get("partner") or self.svc.server)
        return {"key": f"{rel['name']}|{server.lower()}", "server": "      " + server, "_srv": server, "partner": partner, "name": "",
                "mode_t": mode_t, "role_t": role_t, "state_t": state_t, "share": share, "mclt_t": mclt_t, "auto_t": auto_t,
                "count": count, "auth_t": auth_t, "_rel": rel, "_data": data, "_view": view, "_mm": mm,
                "_state": d.get("state", "")}

    def _rel_row(self, rel: dict, prel: dict | None, mm: list[str]) -> dict:
        """Kopfzeile einer Beziehung: Werte, die für beide Server gelten (bei Abweichung beide Sichten)."""
        tr = self.tr
        r = self._row(rel, self.svc.server, rel, "rel", mm)
        is_open = rel["name"].lower() in self._open
        r.update(key=f"{rel['name']}|*", name=("▾ " if is_open else "▸ ") + rel["name"],
                 server=f"{self.svc.server} ↔ {rel['partner']}", partner="", role_t="")
        if rel.get("mode") == "LoadBalance":
            if prel and prel.get("lb") is not None:
                r["share"] = f"{rel.get('lb')} / {prel.get('lb')} %"
        if prel and prel.get("state") and prel.get("state") != rel.get("state"):
            r["state_t"] = f"{ck.fo_state(rel.get('state', ''), tr)} / {ck.fo_state(prel['state'], tr)}"
            r["_state"] = "mixed"
        return r

    def refresh(self) -> None:
        tr = self.tr
        svc = self.svc
        rows = []
        for rel in svc.failovers:
            prel, loaded = self.peer_rel(rel)
            mm = self._mismatch(rel, prel) if prel else []
            rows.append(self._rel_row(rel, prel, mm))
            rows.append(self._row(rel, svc.server, rel, "local", mm))
            rows.append(self._row(rel, rel["partner"], prel, "peer" if prel else "missing" if loaded else "assumed", mm))
        self.rel_grid.set_rows(rows)
        c = theme.current
        for i, r in enumerate(rows):
            k = r["key"]
            head = r["_view"] == "rel"
            back = tint(c["muted"], 30) if head else None
            if head:
                self.rel_grid.style_row(k, back=back, bold=True)
            elif r["_data"] is None:
                self.rel_grid.style_cell(k, "state_t", fore=c["danger"] if r["_view"] == "missing" else c["muted"])
            if r["_data"] is not None:
                ok = r["_state"] == "Normal"
                self.rel_grid.style_cell(k, "state_t", fore=c["success"] if ok else c["danger"], bold=head or not ok, back=back)
            if r["_mm"]:
                self.rel_grid.style_cell(k, "name" if head else "server", fore=c["danger"], bold=True, back=back)
        self.rel_grid.set_tooltips(self._tip)
        self.rel_grid.autosize(300)       # vor dem Zuklappen, sonst zählen die Serverzeilen nicht mit
        self._apply_open()
        if rows and (self._cur_key is None or not self._select(self._cur_key)):
            self.rel_grid.selectRow(0)
        no_fo = [s["id"] for s in svc.scopes if s["id"] not in svc.scope_fo]
        parts = [tr("fo.info_count", n=len(svc.failovers), m=len(svc.scopes) - len(no_fo), total=len(svc.scopes))]
        for pn in svc.partners():
            parts.append(f"{pn}: {svc.partner_state(pn)}")
        self.info.setText(" · ".join(parts))
        self._fill_scopes()
        self.apply_rights()

    # --- Auf-/Zuklappen -------------------------------------------------------------------------------
    def _apply_open(self) -> None:
        for v in range(self.rel_grid.rowCount()):
            r = self.rel_grid.row_at(v)
            if r is not None and r["_view"] != "rel":
                self.rel_grid.setRowHidden(v, r["_rel"]["name"].lower() not in self._open)

    def _select(self, key: str) -> bool:
        """Zeile wählen; ein Server einer zugeklappten Beziehung klappt sie auf."""
        name = key.rsplit("|", 1)[0].lower()
        if not key.endswith("|*") and name not in self._open:
            self._open.add(name)
            self._set_head_text(name)
            self._apply_open()
        return self.rel_grid.select_key(key)

    def _set_head_text(self, name: str) -> None:
        for v in range(self.rel_grid.rowCount()):
            r = self.rel_grid.row_at(v)
            if r is not None and r["_view"] == "rel" and r["_rel"]["name"].lower() == name:
                r["name"] = ("▾ " if name in self._open else "▸ ") + r["_rel"]["name"]
                col = next(i for i, x in enumerate(self.rel_grid.cols) if x[0] == "name")
                it = self.rel_grid.item(v, col)
                if it is not None:
                    it.setText(r["name"])

    def toggle(self, r: dict | None = None, on: bool | None = None) -> None:
        r = r or self.current_row()
        if not r:
            return
        name = r["_rel"]["name"].lower()
        on = (name not in self._open) if on is None else on
        if on == (name in self._open):
            return
        if on:
            self._open.add(name)
        else:
            self._open.discard(name)
        self._set_head_text(name)
        self._apply_open()
        if not on and r["_view"] != "rel":
            self.rel_grid.select_key(f"{r['_rel']['name']}|*")

    def _cell_clicked(self, v: int, col: int) -> None:
        r = self.rel_grid.row_at(v)
        if r is None or r["_view"] != "rel" or self.rel_grid.cols[col][0] != "name":
            return
        rect = self.rel_grid.visualItemRect(self.rel_grid.item(v, col))
        x = self.rel_grid.viewport().mapFromGlobal(QCursor.pos()).x()
        if x - rect.left() < 24:
            self.toggle(r)

    def _cell_double(self, v: int, _col: int) -> None:
        r = self.rel_grid.row_at(v)
        if r is None:
            return
        if r["_view"] == "rel":
            self.toggle(r)
        else:
            self._rel_action("Edit")

    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        if obj is self.rel_grid and e.type() == QEvent.Type.KeyPress:
            r = self.current_row()
            k = e.key()
            if r and k in (Qt.Key.Key_Right, Qt.Key.Key_Plus):
                self.toggle(r, True)
                return True
            if r and k in (Qt.Key.Key_Left, Qt.Key.Key_Minus):
                self.toggle(r, False)
                return True
            if r and k in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if r["_view"] == "rel":
                    self.toggle(r)
                else:
                    self._rel_action("Edit")
                return True
        return super().eventFilter(obj, e)

    def _tip(self, r: dict) -> str:
        tr = self.tr
        if r["_view"] == "rel":
            lines = [tr("fo.tip_rel", name=r["_rel"]["name"])]
            if r["_mm"]:
                lines += ["", tr("fo.tip_mismatch")] + ["• " + x for x in r["_mm"]]
            return "\n".join(lines)
        lines = [tr("fo.tip_view", server=r["_srv"], name=r["_rel"]["name"])]
        if r["_view"] == "assumed":
            lines.append(tr("fo.tip_not_loaded"))
        elif r["_view"] == "missing":
            lines.append(tr("fo.tip_missing", server=r["_srv"]))
        if r["_mm"]:
            lines.append("")
            lines.append(tr("fo.tip_mismatch"))
            lines += ["• " + x for x in r["_mm"]]
        return "\n".join(lines)

    def current_row(self) -> dict | None:
        return self.rel_grid.current()

    def current_rel(self) -> dict | None:
        r = self.rel_grid.current()
        return next((x for x in self.svc.failovers if x["name"] == r["_rel"]["name"]), None) if r else None

    def _row_changed(self) -> None:
        r = self.current_row()
        self._cur_key = r["key"] if r else None
        self._fill_scopes()
        pn = None if not r or r["_view"] == "local" else r["_rel"]["partner"] if r["_view"] == "rel" else r["_srv"]
        if pn and self.svc.partner_mode != "Off" and pn not in self.svc.peer:
            self.ctl.run(self.ctl.load_peer_flow([pn]))

    def _fill_scopes(self) -> None:
        tr, svc = self.tr, self.svc
        r = self.current_row()
        c = theme.current
        if not r:
            self.sc_grid.set_rows([])
            self.sc_title.setText(tr("fo.scopes"))
            self.sc_sum.setText("")
            return
        rel, srv = r["_rel"], r["_srv"]
        local = r["_view"] in ("local", "rel")
        srv = svc.server if local else srv
        other = rel["partner"] if local else svc.server
        self.sc_grid.horizontalHeaderItem(4).setText(tr("fo.col.on_other", server=other))
        self.sc_title.setText(tr("fo.scopes_on", server=srv))
        peer = svc.peer.get(rel["partner"]) or {}
        if local:
            scopes = list(svc.scopes)
            memb = {sid: (x["name"], x["partner"]) for x in svc.failovers for sid in x["scopes"]}
            in_rel = set(rel["scopes"])
            other_ids = {s["id"] for s in peer["scopes"]} if peer.get("scopes") is not None else None
        else:
            if peer.get("scopes") is None:
                self.sc_grid.set_rows([])
                err = (peer.get("errors") or {}).get("scopes") or (peer.get("errors") or {}).get("conn")
                self.sc_sum.setText(tr("fo.peer_error", error=err) if err else tr("fo.peer_loading"))
                return
            scopes = list(peer["scopes"])
            memb = {sid: (x["name"], x["partner"]) for x in peer.get("fo") or [] for sid in x["scopes"]}
            in_rel = set((r["_data"] or rel)["scopes"])
            other_ids = {s["id"] for s in svc.scopes}
        # Sicht des Gegenübers auf dieselbe Beziehung (None = nicht geladen)
        prel, _loaded = self.peer_rel(rel)
        other_rel = (set(prel["scopes"]) if prel else None) if local else set(rel["scopes"])
        cmp = self.compare.get(rel["name"], {})
        rows = []
        have = set()
        for s in scopes:
            sid = s["id"]
            have.add(sid)
            m = memb.get(sid)
            if sid in in_rel:
                member, mk = tr("fo.member.this"), "this"
            elif m:
                member, mk = tr("fo.member.other", name=m[0], partner=m[1]), "other"
            else:
                member, mk = tr("fo.member.none"), "none"
            if other_ids is None:
                other_t, ok_other = "–", None
            else:
                ok_other = sid in other_ids
                other_t = tr("fo.on_other.yes") if ok_other else tr("fo.on_other.no")
            st, detail = cmp.get(sid, ("", "")) if mk == "this" else ("", "")
            split = other_rel is not None and (sid in in_rel) != (sid in other_rel)
            if split:
                detail = tr("fo.rel_only_here" if sid in in_rel else "fo.rel_only_other", server=other)
            rows.append({"id": sid, "_split": split, "name": s.get("name", ""), "state_t": tr("state." + (s.get("state") or "Active")),
                         "member_t": member, "_mk": mk, "other_t": other_t, "_other": ok_other, "sync": st,
                         "sync_t": self._sync_text(st), "detail": detail})
        for sid in sorted(in_rel - have, key=ip.ip_sort_key):
            rows.append({"id": sid, "name": "", "state_t": tr("fo.sc_missing"), "member_t": tr("fo.member.this"), "_mk": "gone",
                         "other_t": "", "_other": None, "sync": "", "sync_t": "", "detail": tr("fo.sc_missing_detail", server=srv)})
        self.sc_grid.set_rows(rows)
        for x in rows:
            k = x["id"]
            if x.get("_split"):
                self.sc_grid.style_cell(k, "member_t", fore=c["danger"], bold=True)
                self.sc_grid.style_cell(k, "detail", fore=c["danger"])
            elif x["_mk"] == "this":
                self.sc_grid.style_cell(k, "member_t", fore=c["success"])
            elif x["_mk"] == "none":
                self.sc_grid.style_cell(k, "member_t", fore=c["warning"], bold=True)
            elif x["_mk"] == "other":
                self.sc_grid.style_cell(k, "member_t", fore=c["muted"])
            else:
                self.sc_grid.style_row(k, back=tint(c["danger"], 40))
            if x["_other"] is False:
                self.sc_grid.style_cell(k, "other_t", fore=c["danger"] if x["_mk"] == "this" else c["warning"], bold=x["_mk"] == "this")
            if x["sync"]:
                self.sc_grid.style_cell(k, "sync_t", fore=c["success"] if x["sync"] == "sync" else c["danger"], bold=x["sync"] != "sync")
        self.sc_grid.autosize(260)
        n_this = sum(1 for x in rows if x["_mk"] in ("this", "gone"))
        n_none = sum(1 for x in rows if x["_mk"] == "none")
        n_other = sum(1 for x in rows if x["_mk"] == "other")
        self.sc_sum.setText(tr("fo.sc_summary", n=len(have), this=n_this, none=n_none, other=n_other))

    def _sync_text(self, st: str) -> str:
        if st.startswith("diff:"):
            return self.tr("fo.sync.diff", n=st.split(":")[1])
        return self.tr("fo.sync." + st) if st else "–"

    def apply_rights(self) -> None:
        rel = self.current_rel()
        rw_local = self.svc.can_write(None)
        rw = rw_local and (rel is None or self.svc.can_write(rel["partner"]))
        for aid in ("Edit", "AddScopes", "Replicate", "Remove"):
            self.rel_bar.set_visible(aid, rw)
            self.rel_grid.set_action_visible(aid, rw)
        self.rel_bar.set_visible("New", rw_local)
        for aid in ("Replicate", "AddToRel", "Remove"):
            self.sc_bar.set_visible(aid, rw)
            self.sc_grid.set_action_visible(aid, rw)

    # --- Abläufe --------------------------------------------------------------------------------------
    def _reload(self, peers: bool = False):
        yield Job(self.svc.load_failovers, self.tr("status.loading"))
        if peers:
            yield from self.ctl.load_peer_flow(self.svc.partners(), refresh=False)
        else:
            for pn in self.svc.partners():
                self.svc.peer.pop(pn, None)
        self.refresh()
        yield from self.ctl.refresh_overview_rows()

    def _rel_action(self, a: str) -> None:
        rel = self.current_rel()
        if a == "Refresh":
            self.ctl.run(self._reload(peers=True))
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
        elif a == "LoadPeer":
            self.ctl.run(self.ctl.load_peer_flow([rel["partner"]]))
        elif a == "Remove":
            self.ctl.run(self.remove_flow(rel))

    def _sc_action(self, a: str) -> None:
        rel = self.current_rel()
        sel = self.sc_grid.selected_rows()
        if not rel or not sel:
            return
        mine = {s["id"] for s in self.svc.scopes}
        in_rel = [r["id"] for r in sel if r["id"] in rel["scopes"] and r["id"] in mine]
        if a == "Open":
            for sid in [r["id"] for r in sel if r["id"] in mine][:10]:
                self.ctl.open_scope(sid)
        elif a == "Replicate" and in_rel:
            self.ctl.run(self.ctl.replicate_ids_flow(in_rel))
        elif a == "Compare" and in_rel:
            self.ctl.run(self.compare_flow(rel, in_rel))
        elif a == "AddToRel":
            free = [r["id"] for r in sel if r["id"] in mine and r["id"] not in self.svc.scope_fo]
            if not free:
                info(self, self.tr("fo.sc_add"), self.tr("fo.sc_add_none"))
                return
            self.ctl.run(self.add_ids_flow(rel, free))
        elif a == "Remove" and in_rel:
            self.ctl.run(self.remove_scopes_flow(rel, in_rel))

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
        self._cur_key = f"{spec['name']}|*"
        yield from self._reload()

    def edit_flow(self, rel):
        tr, svc = self.tr, self.svc
        p = dlg.failover_dialog(self, tr, self.ctl.known_servers(), svc.server, rel)
        if not p:
            return
        yield Job(lambda: svc.set_relationship(rel, p), tr("status.fo_change", name=rel["name"]))
        yield from self._reload()

    def add_ids_flow(self, rel, ids):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("fo.sc_add"), tr("fo.confirm_add_ids", name=rel["name"], partner=rel["partner"], list=short_list(ids))):
            return
        warns = yield Job(lambda: svc.add_fo_scopes(rel, ids), tr("status.fo_add", id=", ".join(ids), name=rel["name"]))
        if warns:
            warn(self, tr("fo.sc_add"), tr("scope.fo.add_warn", list=short_list(warns, 10)))
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
        self._select(self._cur_key or f"{rel['name']}|*")
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
        self.unlocked = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.lock_box = QFrame()
        self.lock_box.setObjectName("lockbox")
        c = theme.current
        self.lock_box.setStyleSheet(f"QFrame#lockbox {{ border:1px solid {c['warning']}; border-radius:6px;"
                                    f" background:{tint(c['warning'], 30).name(QColor.NameFormat.HexArgb)}; }}")
        lb = QHBoxLayout(self.lock_box)
        lb.setContentsMargins(12, 8, 12, 8)
        self.lock_text = QLabel("")
        self.lock_text.setWordWrap(True)
        lb.addWidget(self.lock_text, 1)
        self.lock_btn = QPushButton("")
        self.lock_btn.clicked.connect(self._toggle_lock)
        lb.addWidget(self.lock_btn)
        lay.addWidget(self.lock_box)
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
        self.bar = ButtonBar([("Refresh", tr("ui.refresh")), ("New", tr("def.new")), ("Edit", tr("def.edit")),
                              ("Remove", tr("def.remove")), ("ToPartner", tr("def.to_partner"))])
        self.bar.action.connect(self._action)
        self.bar.add_widget(help_icon(tr("def.note")))
        lay.addWidget(self.bar)
        self.apply_rights()

    WRITE = ("New", "Edit", "Remove", "ToPartner")

    def _toggle_lock(self) -> None:
        if self.unlocked:
            self.unlocked = False
        elif confirm(self, self.tr("def.unlock"), self.tr("def.unlock_confirm")):
            self.unlocked = True
        self.apply_rights()

    def lock(self) -> None:
        self.unlocked = False
        self.apply_rights()

    def apply_rights(self) -> None:
        """Bearbeiten erst nach „Entsperren“ und nur mit Schreibrecht; ohne Recht bleibt die Liste nur lesbar."""
        tr = self.tr
        rw = self.svc.can_write(None)
        on = rw and self.unlocked
        for aid in self.WRITE:
            self.bar.buttons[aid].setEnabled(on)
            self.grid.set_action_visible(aid, on)
        self.bar.buttons["ToPartner"].setEnabled(on and not self.v6 and any(self.svc.can_write(pn) for pn in self.svc.partners()))
        self.grid.set_action_visible("ToPartner", on and not self.v6)
        self.lock_btn.setVisible(rw)
        self.lock_btn.setText(tr("def.lock") if self.unlocked else tr("def.unlock"))
        self.lock_text.setText(tr("def.read_only") if not rw else tr("def.unlocked_text") if self.unlocked else tr("def.locked_text"))
        self.grid.default_action = "Edit" if on else None

    @property
    def v6(self) -> bool:
        return self.ctl.family == 6

    def refresh(self) -> None:
        defs = self.svc.defs_of(self.v6)
        rows = [dict(d, default_t=", ".join(d["default"])) for d in sorted(defs.values(), key=lambda d: (d["vendor"], d["id"]))]
        self.grid.set_rows(rows)
        self.grid.autosize(320)
        self.grid.apply_filter(self.filter.text())

    def _action(self, a: str) -> None:
        cur = self.grid.current()
        if a == "Refresh":
            self.ctl.run(self._reload())
        elif a in self.WRITE and not (self.unlocked and self.svc.can_write(None)):
            return
        elif a == "New":
            self.ctl.run(self.ctl.new_definition_flow({"v6": self.v6}))
        elif a == "Edit" and cur:
            self.ctl.run(self.edit_flow(cur))
        elif a == "Remove" and cur:
            self.ctl.run(self.remove_flow(cur))
        elif a == "ToPartner" and self.grid.selected_rows() and not self.v6:
            self.ctl.run(self.to_partner_flow(self.grid.selected_rows()))

    def _reload(self):
        yield Job(self.svc.load_defs, self.tr("status.loading"))
        self.refresh()

    def edit_flow(self, d):
        tr, svc = self.tr, self.svc
        v6 = self.v6
        res = dlg.definition_dialog(self, tr, d, v6=v6)
        if not res:
            return
        res.update(id=d["id"], vendor=d["vendor"], type=d["type"], multi=d["multi"])
        yield Job(lambda: svc.def_set(res, v6), tr("status.saving"))
        svc.log(tr("log.def_changed", tag=f"{d['id']:03d}", name=res["name"]))
        yield from self._reload()

    def remove_flow(self, d):
        tr, svc = self.tr, self.svc
        if not confirm(self, tr("def.remove"), tr("def.confirm_remove", tag=f"{d['id']:03d}", name=d["name"])):
            return
        v6 = self.v6
        yield Job(lambda: svc.def_remove(d["id"], d["vendor"], v6), tr("status.saving"))
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
            # alle oder keine: scheitert eine Kopie, werden die schon kopierten Definitionen wieder entfernt
            for pn in partners:
                for d in rows:
                    try:
                        out.append(tr("def.copied" if svc.copy_def_to_partner(d, pn) else "def.exists",
                                      tag=f"{d['id']:03d}", partner=pn))
                    except UserError as e:
                        raise UserError(tr("err.def_partner", tag=f"{d['id']:03d}", partner=pn, error=str(e))) from None
        yield Job(lambda: svc.atomic(tr("tx.def_partner"), work), tr("status.to_partner"))
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
        lay.setSpacing(2)
        self.value = QLabel("–")
        self.value.setStyleSheet(f"color:{color}; font-size:24px; font-weight:700;")
        lay.addWidget(self.value)
        t = QLabel(title)
        t.setStyleSheet(f"color:{theme.current['muted']};")
        lay.addWidget(t)
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{theme.current['muted']}; font-size:11px;")
        lay.addWidget(self.sub)


class DistBars(QWidget):
    """Gestapelte Balken: Befunde je Kategorie, aufgeteilt nach Stufe."""

    MAX_ROWS = 8
    ROW_H = 20

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.rows: list[tuple[str, dict[str, int]]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(self.ROW_H * 2)

    def set_data(self, rows: list[tuple[str, dict[str, int]]]) -> None:
        rows = sorted(rows, key=lambda r: tuple(-r[1].get(lv, 0) for lv in ck.LEVELS))
        if len(rows) > self.MAX_ROWS:
            rest: dict[str, int] = {}
            for _n, c in rows[self.MAX_ROWS - 1:]:
                for lv, v in c.items():
                    rest[lv] = rest.get(lv, 0) + v
            rows = rows[:self.MAX_ROWS - 1] + [(self.tr("chk.dist_other", n=len(rows) - self.MAX_ROWS + 1), rest)]
        self.rows = rows
        self.setMinimumHeight(max(2, len(rows)) * self.ROW_H + 4)
        self.update()

    def _row_at(self, y: float) -> int:
        i = int((y - 2) // self.ROW_H)
        return i if 0 <= i < len(self.rows) else -1

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        i = self._row_at(e.position().y())
        if i < 0:
            QToolTip.hideText()
            return
        name, c = self.rows[i]
        parts = [f"{level_name(self.tr, lv, c[lv] != 1)}: {c[lv]}" for lv in ck.LEVELS if c.get(lv)]
        QToolTip.showText(e.globalPosition().toPoint(), f"{name}\n" + "\n".join(parts), self)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fm = p.fontMetrics()
        if not self.rows:
            p.setPen(QColor(theme.current["muted"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.tr("chk.dist_none"))
            return
        label_w = min(max(fm.horizontalAdvance(n) for n, _c in self.rows) + 10, self.width() // 3)
        num_w = fm.horizontalAdvance("0000") + 6
        bar_w = max(20, self.width() - label_w - num_w - 4)
        mx = max(sum(c.values()) for _n, c in self.rows) or 1
        for i, (name, c) in enumerate(self.rows):
            y = 2 + i * self.ROW_H
            p.setPen(QColor(theme.current["text"]))
            p.drawText(0, y, label_w - 6, self.ROW_H, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       fm.elidedText(name, Qt.TextElideMode.ElideRight, label_w - 6))
            x = float(label_w)
            for lv in ck.LEVELS:
                n = c.get(lv, 0)
                if not n:
                    continue
                w = max(2.0, bar_w * n / mx)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(level_color(lv)))
                p.drawRoundedRect(QRectF(x, y + 4, w - 1, self.ROW_H - 8), 2, 2)
                x += w
            p.setPen(QColor(theme.current["muted"]))
            p.drawText(int(x) + 6, y, num_w, self.ROW_H, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       str(sum(c.values())))
        p.end()


def _box(title: str, w: QWidget, extra: QWidget | None = None) -> QFrame:
    f = QFrame()
    f.setObjectName("chkbox")
    f.setStyleSheet(f"QFrame#chkbox {{ border:1px solid {theme.current['border']}; border-radius:6px;"
                    f" background:{theme.current['surface']}; }}")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 8, 12, 8)
    h = QHBoxLayout()
    h.addWidget(bold_label(title))
    h.addStretch(1)
    if extra is not None:
        h.addWidget(extra)
    lay.addLayout(h)
    lay.addWidget(w, 1)
    return f


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
        self.bar.action.connect(lambda _a: self.ctl.start_scan())
        top.addWidget(self.bar)
        self.cancel_btn = QPushButton(tr("ui.cancel"))
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        top.addWidget(self.cancel_btn)
        self.with_leases = QCheckBox(tr("chk.with_leases"))
        self.with_leases.setToolTip(tr("chk.with_leases_tip"))
        self.with_partner = QCheckBox(tr("chk.with_partner"))
        self.with_partner.setChecked(True)
        self.with_dns = QCheckBox(tr("chk.with_dns"))
        self.with_dns.setToolTip(tr("chk.with_dns_tip"))
        self.with_dns.setChecked(bool(ctl.settings.get("check_dns", False)))
        self.with_dns.toggled.connect(lambda on: ctl.settings.set("check_dns", on))
        top.addWidget(self.with_leases)
        top.addWidget(self.with_partner)
        top.addWidget(self.with_dns)
        self.state = QLabel(tr("chk.not_run"))
        self.state.setStyleSheet(f"color:{theme.current['muted']};")
        top.addWidget(self.state, 1)
        self.pbar = QProgressBar()
        self.pbar.setMaximumWidth(260)
        self.pbar.setMaximumHeight(14)
        self.pbar.setTextVisible(False)
        self.pbar.hide()
        top.addWidget(self.pbar)
        lay.addLayout(top)
        self._pending = QTimer(self)        # Zwischenstände gebündelt anzeigen (nicht nach jedem Scope neu zeichnen)
        self._pending.setSingleShot(True)
        self._pending.setInterval(300)
        self._pending.timeout.connect(self.refresh)
        tiles = QGridLayout()
        self.tiles: dict[str, Tile] = {}
        for i, lv in enumerate(ck.LEVELS):
            t = Tile(level_name(tr, lv, True), level_color(lv))
            self.tiles[lv] = t
            tiles.addWidget(t, 0, i)
        self.t_scopes = Tile(tr("chk.tile_scopes"), theme.current["accent"])
        tiles.addWidget(self.t_scopes, 0, 4)
        lay.addLayout(tiles)
        dist = QHBoxLayout()
        self.dist = DistBars(tr)
        legend = QLabel("  ".join(f"<span style='color:{level_color(lv)}'>■</span> {html.escape(level_name(tr, lv, True))}"
                                  for lv in ck.LEVELS))
        legend.setStyleSheet(f"color:{theme.current['muted']}; font-size:11px;")
        dist.addWidget(_box(tr("chk.dist_title"), self.dist, legend), 3)
        self.top_scopes = QLabel("")
        self.top_scopes.setTextFormat(Qt.TextFormat.RichText)
        self.top_scopes.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.top_scopes.setWordWrap(True)
        self.top_scopes.linkActivated.connect(lambda sid: self.ctl.open_scope(sid, show_findings=True))
        dist.addWidget(_box(tr("chk.top_title"), self.top_scopes), 2)
        lay.addLayout(dist)

        # Umschalter Server-/Scope-Befunde: große Segmentschaltfläche statt unauffälliger Tabs
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.seg_group = QButtonGroup(self)
        self.seg_btns: list[QPushButton] = []
        c = theme.current
        for i, key in enumerate(("chk.tab_server", "chk.tab_scopes")):
            b = QPushButton(tr(key))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            f = b.font()
            f.setPointSizeF(f.pointSizeF() * 1.1)
            f.setBold(True)
            b.setFont(f)
            rad = "border-top-left-radius:6px; border-bottom-left-radius:6px;" if i == 0 else \
                "border-top-right-radius:6px; border-bottom-right-radius:6px; border-left:none;"
            b.setStyleSheet(f"QPushButton {{ padding:7px 22px; border:1px solid {c['border']}; border-radius:0; {rad}"
                            f" background:{c['surface']}; color:{c['text']}; }}"
                            f" QPushButton:checked {{ background:{c['accent']}; border-color:{c['accent']}; color:white; }}"
                            f" QPushButton:hover:!checked {{ background:{tint(c['accent'], 40).name(QColor.NameFormat.HexArgb)}; }}")
            self.seg_group.addButton(b, i)
            self.seg_btns.append(b)
            seg.addWidget(b)
        seg.addStretch(1)
        lay.addLayout(seg)
        self.stack = QStackedWidget()
        self.seg_group.idClicked.connect(self.stack.setCurrentIndex)
        self.srv_view = FindingsView(tr, ctl.flt, show_scope=True, scope_mode=True)
        self.srv_view.empty_text = tr("chk.server_none")
        self.srv_view.activated.connect(lambda f, _m: f.scope_id and self.ctl.open_scope(f.scope_id))
        self.stack.addWidget(self.srv_view)
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
        self.stack.addWidget(w)
        self.seg_btns[0].setChecked(True)
        lay.addWidget(self.stack, 1)
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

    # --- Prüfung im Hintergrund (Scanner-Signale) -------------------------------------------------------
    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.state.setText(self.tr("status.cancelling"))
        self.ctl.scanner.cancel()

    def scan_started(self) -> None:
        self.bar.buttons["Scan"].setEnabled(False)
        self.with_leases.setEnabled(False)
        self.with_partner.setEnabled(False)
        self.with_dns.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.show()
        self.pbar.setRange(0, 0)
        self.pbar.show()
        self.state.setText(self.tr("chk.running"))
        self.live = {"time": "", "scopes": {}, "server": [], "partial": True, "seconds": 0, "running": True,
                     "with_leases": self.with_leases.isChecked()}

    def scan_progress(self, text: str, i: int, n: int) -> None:
        if text:
            self.state.setText(text)
        if n:
            self.pbar.setRange(0, n)
            self.pbar.setValue(i)

    def scope_done(self, sid: str, entry: dict, i: int, n: int) -> None:
        live = getattr(self, "live", None)
        if live is None:
            return
        live["scopes"][sid] = entry
        if self.scan is None or self.scan.get("running"):
            self.scan = live
            if not self._pending.isActive():
                self._pending.start()

    def scan_stopped(self) -> None:
        self.bar.buttons["Scan"].setEnabled(True)
        self.with_leases.setEnabled(True)
        self.with_partner.setEnabled(True)
        self.with_dns.setEnabled(True)
        self.cancel_btn.hide()
        self.pbar.hide()
        self.live = None

    def scan_failed(self, text: str) -> None:
        self.state.setText(self.tr("chk.failed") + " " + text.splitlines()[0] if text else self.tr("chk.failed"))
        if self.scan is not None and self.scan.get("running"):
            self.scan = None

    def set_scan(self, scan: dict | None) -> None:
        self._pending.stop()
        self.scan = scan
        self.refresh()

    def refresh(self) -> None:
        tr = self.tr
        scan = self.scan
        flt = self.ctl.flt
        if not scan:
            return
        if not scan.get("running"):
            self.state.setText(tr("chk.state_partial" if scan.get("partial") else "chk.state", time=scan["time"],
                                  sec=scan["seconds"], n=len(scan["scopes"]))
                               + ("  " + tr("chk.state_leases") if scan.get("with_leases") else "")
                               + ("  " + tr("chk.state_dns") if scan.get("with_dns") else ""))
        allf = list(scan["server"])
        for v in scan["scopes"].values():
            allf += v["findings"]
        vis = [f for f in allf if flt.visible(f, ignore_level=True)]
        srv_vis = [f for f in scan["server"] if flt.visible(f, ignore_level=True)]
        for lv, t in self.tiles.items():
            n_srv = sum(1 for f in srv_vis if f.level == lv)
            per = [sum(1 for f in v["findings"] if f.level == lv and flt.visible(f, ignore_level=True))
                   for v in scan["scopes"].values()]
            t.value.setText(str(n_srv + sum(per)))
            t.sub.setText(tr("chk.tile_split", server=n_srv, scopes=sum(per), affected=sum(1 for x in per if x)))
        clean = sum(1 for v in scan["scopes"].values()
                    if not [f for f in v["findings"] if f.level in (ck.ERROR, ck.WARN)])
        self.t_scopes.value.setText(f"{clean}/{len(scan['scopes'])}")
        self.t_scopes.sub.setText(tr("chk.tile_scopes_sub", n=len(scan["scopes"]) - clean))
        cats: dict[str, dict[str, int]] = {}
        for f in vis:
            c = cats.setdefault(f.area, {})
            c[f.level] = c.get(f.level, 0) + 1
        self.dist.set_data([(tr("cat." + k), v) for k, v in cats.items()])
        worst = []
        for sid, v in scan["scopes"].items():
            fs = [f for f in v["findings"] if flt.visible(f, ignore_level=True)]
            e, w_ = sum(1 for f in fs if f.level == ck.ERROR), sum(1 for f in fs if f.level == ck.WARN)
            if e or w_:
                worst.append((e, w_, sid, v["scope"]["name"]))
        worst.sort(key=lambda x: (-x[0], -x[1], ip.ip_sort_key(x[2])))
        acc = theme.current["accent"]
        lines = []
        for e, w_, sid, name in worst[:7]:
            cnt = " · ".join(f"<span style='color:{level_color(lv)}'>{html.escape(level_name(tr, lv, n != 1))} {n}</span>"
                             for lv, n in ((ck.ERROR, e), (ck.WARN, w_)) if n)
            lines.append(f"<a href='{html.escape(sid)}' style='color:{acc}; text-decoration:none'><b>{html.escape(sid)}</b></a>"
                         f" {html.escape(name)} – {cnt}")
        if len(worst) > 7:
            lines.append(f"<span style='color:{theme.current['muted']}'>{html.escape(tr('chk.top_more', n=len(worst) - 7))}</span>")
        self.top_scopes.setText("<br>".join(lines) if lines else
                                f"<span style='color:{theme.current['muted']}'>{html.escape(tr('chk.top_none'))}</span>")
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
        n_srv = sum(1 for f in srv_vis if f.level in (ck.ERROR, ck.WARN))
        n_sc = sum(1 for v in scan["scopes"].values() for f in v["findings"]
                   if f.level in (ck.ERROR, ck.WARN) and flt.visible(f, ignore_level=True))
        self.seg_btns[0].setText(tr("chk.tab_server") + (f"  ({n_srv})" if n_srv else ""))
        self.seg_btns[1].setText(tr("chk.tab_scopes") + (f"  ({n_sc})" if n_sc else ""))

