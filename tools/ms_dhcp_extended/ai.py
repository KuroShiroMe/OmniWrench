"""KI-Assistent: Funktionen dieses Tools für den Assistenten des Hauptprogramms (ab OmniWrench 0.9.0).

Lesende Funktionen nehmen zwischengespeicherte Daten (Übersicht, Prüfung) aus dem GUI-Thread oder
laufen als eigener Ablauf über den Runner des Tools, damit sie sich nicht mit Bedienaktionen überschneiden.
Änderungen (Reservierung anlegen/entfernen) bestätigt das Hauptprogramm vorher; sie laufen als
Transaktion und werden wie in der Oberfläche auf den Failover-Partner repliziert.
"""

from __future__ import annotations

import threading

from . import checks as ck
from . import ip6calc as ip6
from . import ipcalc as ip
from .runner import Job
from .service import UserError, n_lease, n_res

MAX_ROWS = 500
WAIT_SECONDS = 600


def _rows(items: list, limit: int = MAX_ROWS) -> dict:
    return {"total": len(items), "items": items[:limit], "truncated": len(items) > limit}


def _finding(f: ck.Finding) -> dict:
    return {"level": f.level, "area": f.area, "scope": f.scope_id, "object": f.obj, "text": f.text}


class DhcpAI:
    def __init__(self, tool):
        self.tool = tool
        ctx = tool.context
        self.ctx = ctx
        add = getattr(ctx, "ai_function", None)
        if add is None:     # älteres Hauptprogramm ohne KI
            return
        from omniwrench.sdk import AI_CHANGE, AI_DESCRIBE, AI_OVERVIEW, AI_READ
        sid = {"scope_id": {"type": "string", "description": "Scope ID, e.g. 10.0.0.0 (IPv4) or a DHCPv6 prefix"}}
        add("dhcp_status", "Microsoft DHCP tool: connection state (server, protocol, rights, failover partners).",
            self.status, level=AI_DESCRIBE)
        add("dhcp_overview", "List all DHCP scopes of the connected server with state, utilisation, failover "
            "relationship and number of findings per severity.", self.overview, level=AI_OVERVIEW)
        add("dhcp_findings", "Findings of the last server check (errors, warnings, best practice). Optionally "
            "filtered by scope or severity.", self.findings, level=AI_READ,
            parameters={"type": "object", "properties": {
                **sid, "level": {"type": "string", "enum": [ck.ERROR, ck.WARN, ck.BP, ck.INFO]}}})
        add("dhcp_scope", "Details of one scope: settings, statistics, exclusions, options, reservations, leases "
            "and DNS settings (read live from the server).", self.scope, level=AI_READ,
            parameters={"type": "object", "properties": {
                **sid, "leases": {"type": "boolean", "description": "Include leases (default true)"}},
                "required": ["scope_id"]})
        add("dhcp_find_client", "Search leases and reservations of all IPv4 scopes by IP address, MAC/client ID "
            "or host name (substring).", self.find_client, level=AI_READ,
            parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
        add("dhcp_failover", "Failover relationships with mode, partner, state and scopes.", self.failover,
            level=AI_READ)
        add("dhcp_server_options", "Server-wide DHCP options (IPv4 and IPv6).", self.server_options, level=AI_READ)
        res = {"type": "object", "properties": {
            **sid, "ip": {"type": "string"},
            "client_id": {"type": "string", "description": "MAC address / client ID"},
            "name": {"type": "string"}, "description": {"type": "string"}},
            "required": ["scope_id", "ip", "client_id"]}
        tr = tool.tr
        add("dhcp_add_reservation", "Add an IPv4 reservation to a scope (asks the user first; replicated to "
            "the failover partner like in the tool).", self.res_add, parameters=res, level=AI_CHANGE,
            summary=lambda a: tr("ai.fn.res_add", ip=a.get("ip", ""), mac=a.get("client_id", ""),
                                 scope=a.get("scope_id", ""), server=self.tool.svc.server or ""))
        add("dhcp_remove_reservation", "Remove an IPv4 reservation (asks the user first).", self.res_remove,
            parameters={"type": "object", "properties": {**sid, "ip": {"type": "string"}},
                        "required": ["scope_id", "ip"]}, level=AI_CHANGE,
            summary=lambda a: tr("ai.fn.res_remove", ip=a.get("ip", ""), scope=a.get("scope_id", ""),
                                 server=self.tool.svc.server or ""))

    # --- Hilfen -------------------------------------------------------------------------------------
    def _connected(self, call) -> bool:
        return bool(call.in_gui(lambda: self.tool.svc.server and self.tool.stack.currentIndex() == 1))

    def _need(self, call) -> None:
        if not self._connected(call):
            raise UserError("Not connected to a DHCP server. Ask the user to log in in the DHCP tool first.")

    def _flow(self, call, flow_fn):
        """Ablauf im Runner des Tools ausführen (nach laufenden Bedienaktionen) und auf das Ergebnis warten."""
        done = threading.Event()
        box: dict = {}

        def wrapper():
            try:
                box["value"] = yield from flow_fn()
            except Exception as e:  # noqa: BLE001 - Fehler an den Assistenten zurückgeben
                box["error"] = e
            finally:
                done.set()

        call.in_gui(lambda: self.tool.run(wrapper()))
        waited = 0.0
        while not done.wait(0.25):
            waited += 0.25
            if call.stop.is_set() or waited > WAIT_SECONDS:
                raise UserError("Cancelled.")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def _job(self, call, fn, status: str = ""):
        def flow():
            return (yield Job(fn, status or self.tool.tr("status.loading")))
        return self._flow(call, flow)

    # --- Lesen --------------------------------------------------------------------------------------
    def status(self, args, call):
        def read():
            t, svc = self.tool, self.tool.svc
            if not svc.server or t.stack.currentIndex() != 1:
                return {"connected": False}
            return {"connected": True, "server": svc.server, "user": svc.user or "(current Windows account)",
                    "protocol": svc.protocol, "can_write": svc.can_write(None),
                    "partners": {pn: svc.partner_state(pn) for pn in svc.partners()},
                    "ipv4_scopes": len(svc.scopes), "ipv6_scopes": len(svc.scopes6),
                    "check_done": bool(t.scan)}
        return call.in_gui(read)

    def overview(self, args, call):
        self._need(call)

        def read():
            svc, scan = self.tool.svc, self.tool.scan or {}
            out = []
            for info in list(svc.scope_info.values()) + list(svc.scope_info6.values()):
                s, st = info["scope"], info.get("stat") or {}
                found = (scan.get("scopes", {}).get(s["id"]) or {}).get("findings") or []
                counts: dict[str, int] = {}
                for f in found:
                    counts[f.level] = counts.get(f.level, 0) + 1
                fo = svc.scope_fo.get(s["id"])
                out.append({"id": s["id"], "name": s.get("name", ""), "state": s.get("state", ""),
                            "range": f"{s.get('start', '')} - {s.get('end', '')}".strip(" -"),
                            "in_use": st.get("in_use"), "free": st.get("free"), "percent": st.get("pct"),
                            "failover": fo["name"] if fo else "", "findings": counts})
            return {"server": svc.server, "check_done": bool(scan), **_rows(out)}
        return call.in_gui(read)

    def findings(self, args, call):
        self._need(call)

        def read():
            scan = self.tool.scan
            if not scan:
                return {"check_done": False, "hint": "No server check yet. The user can start it on the page 'Check'."}
            items = list(scan.get("server") or [])
            for sid, entry in (scan.get("scopes") or {}).items():
                items += entry.get("findings") or []
            want_sid, want_lvl = (args.get("scope_id") or "").strip(), (args.get("level") or "").strip()
            items = [f for f in ck.sort_findings(items) if (not want_sid or f.scope_id == want_sid)
                     and (not want_lvl or f.level == want_lvl)]
            return {"check_done": True, "partial": bool(scan.get("partial")), **_rows([_finding(f) for f in items])}
        return call.in_gui(read)

    def scope(self, args, call):
        self._need(call)
        sid = (args.get("scope_id") or "").strip()
        if not sid:
            raise UserError("scope_id missing")
        leases = args.get("leases", True) is not False
        data = self._job(call, lambda: self.tool.svc.get_scope(sid, leases),
                         self.tool.tr("status.loading_scope", id=sid))
        out = {k: v for k, v in data.items() if k != "leases"}
        if leases:
            out["leases"] = _rows(data.get("leases") or [])
        scan = call.in_gui(lambda: self.tool.scan) or {}
        found = (scan.get("scopes", {}).get(sid) or {}).get("findings") or []
        out["findings"] = [_finding(f) for f in found]
        return out

    def find_client(self, args, call):
        self._need(call)
        q = (args.get("query") or "").strip().lower()
        if len(q) < 2:
            raise UserError("query too short")
        qn = q.replace("-", "").replace(":", "").replace(".", "")
        svc = self.tool.svc
        ids = call.in_gui(lambda: [s["id"] for s in svc.scopes])

        def match(row: dict) -> bool:
            for key in ("ip", "cid", "host", "name"):
                v = str(row.get(key) or "").lower()
                if not v:
                    continue
                if q in v or (key == "cid" and len(qn) >= 4 and qn in v.replace("-", "").replace(":", "")):
                    return True
            return False

        def search():
            hits = []
            for sid in ids:
                if call.stop.is_set() or svc.cancel.is_set():
                    break
                for kind, cmd in (("reservation", "Get-DhcpServerv4Reservation"), ("lease", "Get-DhcpServerv4Lease")):
                    try:
                        rows = svc.cim(cmd, ScopeId=sid)
                    except UserError:
                        continue
                    for r in map(n_res if kind == "reservation" else n_lease, rows):
                        if match(r):
                            hits.append({"type": kind, "scope": sid, **r})
            return hits
        hits = self._job(call, search, self.tool.tr("status.loading"))
        return _rows(hits, 200)

    def failover(self, args, call):
        self._need(call)
        return call.in_gui(lambda: [{k: v for k, v in r.items() if not k.startswith("_")}
                                    for r in self.tool.svc.failovers])

    def server_options(self, args, call):
        self._need(call)

        def read():
            svc = self.tool.svc
            return {"ipv4": svc.server_option_rows, "ipv6": svc.server_option_rows6}
        return call.in_gui(read)

    # --- Ändern -------------------------------------------------------------------------------------
    def _write_check(self, call, sid: str) -> None:
        self._need(call)
        svc = self.tool.svc
        if not call.in_gui(lambda: svc.can_write(None)):
            raise UserError("Read-only access (DHCP Users): changes are not possible with this login.")
        if ip6.is_v6_scope(sid):
            raise UserError("Only IPv4 reservations are supported here; use the DHCP tool for DHCPv6.")
        if not call.in_gui(lambda: sid in svc.scope_info):
            raise UserError(f"Scope {sid} not found on {svc.server}.")

    def _after(self, sid: str):
        t = self.tool
        tab = t.scope_tab(sid)
        if tab is not None:
            yield from tab.load_flow(leases=False)
        yield from t.after_change(sid, tab)
        yield from t.refresh_overview_rows()

    def res_add(self, args, call):
        sid = (args.get("scope_id") or "").strip()
        self._write_check(call, sid)
        svc, tr = self.tool.svc, self.tool.tr
        rip = (args.get("ip") or "").strip()
        cid = ip.format_client_id(args.get("client_id") or "") or (args.get("client_id") or "").strip()
        scope = svc.scope_info[sid]["scope"]
        if not ip.is_ipv4(rip) or not ip.in_subnet(rip, sid, scope["mask"]):
            raise UserError(f"{rip} is not an address of scope {sid}/{scope['mask']}.")
        if not cid:
            raise UserError("client_id missing")
        r = {"ip": rip, "cid": cid, "name": args.get("name") or "", "desc": args.get("description") or "",
             "type": "Dhcp"}

        def flow():
            yield Job(lambda: svc.atomic(tr("tx.res_add", ip=rip), lambda: svc.res_add(sid, r)), tr("status.saving"))
            svc.log(tr("log.res_saved", ip=rip, mac=cid, id=sid))
            yield from self._after(sid)
            return {"ok": True, "scope": sid, "reservation": r}
        return self._flow(call, flow)

    def res_remove(self, args, call):
        sid = (args.get("scope_id") or "").strip()
        self._write_check(call, sid)
        svc, tr = self.tool.svc, self.tool.tr
        rip = (args.get("ip") or "").strip()

        def flow():
            yield Job(lambda: svc.atomic(tr("tx.res_remove", id=sid), lambda: svc.res_remove(sid, rip)),
                      tr("status.saving"))
            svc.log(tr("log.res_removed", ip=rip, id=sid))
            yield from self._after(sid)
            return {"ok": True, "scope": sid, "removed": rip}
        return self._flow(call, flow)
