"""KI-Assistent: Funktionen dieses Tools für den Assistenten des Hauptprogramms (ab OmniWrench 0.9.0).

Lesende Funktionen nehmen zwischengespeicherte Daten (Zonen, Prüfung) aus dem GUI-Thread oder laufen
als eigener Ablauf über den Runner des Tools, damit sie sich nicht mit Bedienaktionen überschneiden.
Änderungen (Eintrag anlegen/löschen) bestätigt das Hauptprogramm vorher; sie laufen wie in der
Oberfläche über write_flow (Konfliktprüfung, Transaktion, Replikationsbeobachtung).
"""

from __future__ import annotations

import threading

from . import checks as ck
from . import dnsutil as du
from .runner import Job
from .service import UserError

MAX_ROWS = 500
WAIT_SECONDS = 600
WRITE_TYPES = ("A", "AAAA", "CNAME", "PTR", "TXT", "MX", "SRV")


def _rows(items: list, limit: int = MAX_ROWS) -> dict:
    return {"total": len(items), "items": items[:limit], "truncated": len(items) > limit}


def _finding(f: ck.Finding) -> dict:
    return {"level": f.level, "area": f.area, "server": f.server, "zone": f.scope_id, "object": f.obj,
            "text": f.text}


def _rec(r: du.Rec) -> dict:
    return {"name": r.name, "zone": r.zone, "type": r.type, "value": r.value, "ttl": r.ttl,
            "dynamic": r.dynamic, "timestamp": du.fmt_local(r.ts) if r.ts else ""}


class DnsAI:
    def __init__(self, tool):
        self.tool = tool
        add = getattr(tool.context, "ai_function", None)
        if add is None:     # älteres Hauptprogramm ohne KI
            return
        from omniwrench.sdk import AI_CHANGE, AI_DESCRIBE, AI_OVERVIEW, AI_READ
        srv = {"server": {"type": "string", "description": "DNS server (default: the primary server)"}}
        zone = {"zone": {"type": "string", "description": "Zone name, e.g. contoso.local"}}
        add("dns_status", "Microsoft DNS tool: connection state (servers, user, number of zones).", self.status,
            level=AI_DESCRIBE)
        add("dns_overview", "List the zones of a connected DNS server with type, AD integration, dynamic updates, "
            "aging and number of findings per severity.", self.overview, level=AI_OVERVIEW,
            parameters={"type": "object", "properties": srv})
        add("dns_findings", "Findings of the last server check (errors, warnings, best practice), optionally "
            "filtered by zone or severity.", self.findings, level=AI_READ,
            parameters={"type": "object", "properties": {
                **srv, **zone, "level": {"type": "string", "enum": [ck.ERROR, ck.WARN, ck.BP, ck.INFO]}}})
        add("dns_records", "Records of one zone (loaded live if needed), optionally filtered by record type or "
            "name substring.", self.records, level=AI_READ,
            parameters={"type": "object", "properties": {
                **srv, **zone, "type": {"type": "string"}, "name": {"type": "string"}}, "required": ["zone"]})
        add("dns_search", "Search all zones of a server by name (substring), IP address or network (CIDR).",
            self.search, level=AI_READ,
            parameters={"type": "object", "properties": {**srv, "query": {"type": "string"}},
                        "required": ["query"]})
        add("dns_server_settings", "Settings of a DNS server (forwarders, recursion, scavenging, aging …).",
            self.server_settings, level=AI_READ, parameters={"type": "object", "properties": srv})
        tr = tool.tr
        rec = {"type": "object", "properties": {
            **srv, **zone,
            "name": {"type": "string", "description": "Record name relative to the zone ('@' for the zone itself)"},
            "type": {"type": "string", "enum": list(WRITE_TYPES)},
            "value": {"type": "string", "description": "A/AAAA: IP; CNAME/PTR: host; TXT: text; "
                      "MX: 'preference host'; SRV: 'priority weight port host'"},
            "ttl": {"type": "integer", "description": "Seconds (default 3600)"},
            "create_ptr": {"type": "boolean", "description": "A/AAAA: also create the PTR record"}},
            "required": ["zone", "name", "type", "value"]}
        add("dns_add_record", "Create a static DNS record (asks the user first).", self.add_record,
            parameters=rec, level=AI_CHANGE,
            summary=lambda a: tr("ai.fn.rec_add", rec=f"{a.get('name', '')} {a.get('type', '')} {a.get('value', '')}",
                                 zone=a.get("zone", ""), server=self._server(a)))
        add("dns_delete_record", "Delete a DNS record (asks the user first). Identify it by name, type and value.",
            self.delete_record, parameters=rec, level=AI_CHANGE,
            summary=lambda a: tr("ai.fn.rec_delete",
                                 rec=f"{a.get('name', '')} {a.get('type', '')} {a.get('value', '')}",
                                 zone=a.get("zone", ""), server=self._server(a)))

    # --- Hilfen -------------------------------------------------------------------------------------
    def _server(self, args: dict) -> str:
        s = du.norm(str(args.get("server") or ""))
        return s or self.tool.svc.primary

    def _need(self, call, args: dict | None = None) -> str:
        t = self.tool
        ok = call.in_gui(lambda: bool(t.svc.primary) and t.stack.currentIndex() == 1)
        if not ok:
            raise UserError("Not connected to a DNS server. Ask the user to log in in the DNS tool first.")
        server = self._server(args or {})
        if server not in call.in_gui(lambda: list(t.svc.servers)):
            raise UserError(f"Server {server} is not connected in the DNS tool.")
        return server

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

    def _zone_recs(self, call, server: str, zone: str) -> list[du.Rec]:
        svc = self.tool.svc
        zone = du.norm(zone)
        if zone not in call.in_gui(lambda: list(svc.zones.get(server, {}))):
            raise UserError(f"Zone {zone} not found on {server}.")
        recs = call.in_gui(lambda: svc.records(server, zone))
        if recs is None:
            recs = self._job(call, lambda: svc.load_zone(server, zone))
            call.in_gui(lambda: self.tool.zone_changed(server, zone))
        return list(recs)

    # --- Lesen --------------------------------------------------------------------------------------
    def status(self, args, call):
        def read():
            t, svc = self.tool, self.tool.svc
            if not svc.primary or t.stack.currentIndex() != 1:
                return {"connected": False}
            return {"connected": True, "primary": svc.primary, "user": svc.user or "(current Windows account)",
                    "servers": {s: {"zones": len(svc.zones.get(s, {})), "version": i.get("version", ""),
                                    "error": svc.errors.get(s, "")} for s, i in svc.servers.items()},
                    "dhcp_server": svc.dhcp_server, "checked_servers": list(t.scans)}
        return call.in_gui(read)

    def overview(self, args, call):
        server = self._need(call, args)

        def read():
            svc, scan = self.tool.svc, self.tool.scans.get(server) or {}
            counts: dict[str, dict[str, int]] = {}
            for f in scan.get("findings") or []:
                c = counts.setdefault(f.scope_id, {})
                c[f.level] = c.get(f.level, 0) + 1
            out = []
            for name, z in svc.zones.get(server, {}).items():
                cached = svc.records(server, name)
                out.append({"zone": name, "type": du.ZONE_TYPE_KEYS.get(z["type"], str(z["type"])),
                            "ad_integrated": z.get("ds"), "reverse": z.get("reverse"),
                            "dynamic_updates": z.get("allow_update"), "aging": z.get("aging"),
                            "paused": z.get("paused"), "records": len(cached) if cached is not None else None,
                            "findings": counts.get(name, {})})
            return {"server": server, "check_done": bool(scan), "server_findings": counts.get("", {}), **_rows(out)}
        return call.in_gui(read)

    def findings(self, args, call):
        server = self._need(call, args)

        def read():
            scan = self.tool.scans.get(server)
            if not scan:
                return {"check_done": False, "hint": "No check for this server yet. The user can start it on the "
                                                     "page 'Check'."}
            zone, lvl = du.norm(str(args.get("zone") or "")), (args.get("level") or "").strip()
            items = [f for f in scan.get("findings") or [] if (not zone or f.scope_id == zone)
                     and (not lvl or f.level == lvl)]
            return {"check_done": True, "time": scan.get("time", ""), "partial": bool(scan.get("partial")),
                    **_rows([_finding(f) for f in items])}
        return call.in_gui(read)

    def records(self, args, call):
        server = self._need(call, args)
        recs = self._zone_recs(call, server, str(args.get("zone") or ""))
        rtype = str(args.get("type") or "").upper()
        name = str(args.get("name") or "").lower()
        recs = [r for r in recs if (not rtype or r.type == rtype) and (not name or name in r.name)]
        return _rows([_rec(r) for r in recs])

    def search(self, args, call):
        server = self._need(call, args)
        svc = self.tool.svc
        q = str(args.get("query") or "").strip()
        if not q:
            raise UserError("query missing")

        def work():
            zones = [n for n, z in svc.zones.get(server, {}).items()
                     if z["type"] in (du.ZONE_PRIMARY, du.ZONE_SECONDARY) and not z.get("auto")]
            svc.load_many(server, [z for z in zones if (server, z) not in svc.cache])
            return svc.search(q, server=server)
        hits = self._job(call, work, self.tool.tr("status.loading"))
        return _rows([_rec(r) for r in hits], 200)

    def server_settings(self, args, call):
        server = self._need(call, args)
        return call.in_gui(lambda: dict(self.tool.svc.servers.get(server) or {}))

    # --- Ändern -------------------------------------------------------------------------------------
    def _parse(self, call, args: dict) -> tuple[str, du.Rec]:
        server = self._need(call, args)
        svc, tr = self.tool.svc, self.tool.tr
        zone = du.norm(str(args.get("zone") or ""))
        z = call.in_gui(lambda: svc.zones.get(server, {}).get(zone))
        if not z:
            raise UserError(f"Zone {zone} not found on {server}.")
        if z["type"] != du.ZONE_PRIMARY:
            raise UserError(f"Zone {zone} is not a primary zone; records can only be changed there.")
        rtype = str(args.get("type") or "").upper()
        if rtype not in WRITE_TYPES:
            raise UserError(f"Record type {rtype} is not supported here.")
        node = str(args.get("name") or "").strip()
        name = zone if node in ("", "@") else du.fqdn(node, zone)
        value = str(args.get("value") or "").strip()
        parts = value.split()
        if rtype in ("A", "AAAA"):
            data = {"ip": value}
        elif rtype in ("CNAME", "PTR"):
            data = {"host": value}
        elif rtype == "TXT":
            data = {"text": du.txt_unquote(value)}
        elif rtype == "MX" and len(parts) == 2:
            data = {"pref": parts[0], "host": parts[1]}
        elif rtype == "SRV" and len(parts) == 4:
            data = {"priority": parts[0], "weight": parts[1], "port": parts[2], "host": parts[3]}
        else:
            raise UserError(f"Value for {rtype} has the wrong format.")
        err = du.validate_data(rtype, data, tr)
        if err:
            raise UserError(err)
        try:
            ttl = int(args.get("ttl") or 3600)
        except (TypeError, ValueError):
            ttl = 3600
        return server, du.Rec(zone=zone, name=du.norm(name), type=rtype, data=du.clean_data(rtype, data), ttl=ttl)

    def add_record(self, args, call):
        server, new = self._parse(call, args)
        t, svc, tr = self.tool, self.tool.svc, self.tool.tr
        recs = self._zone_recs(call, server, new.zone)
        if any(r.key == new.key for r in recs):
            raise UserError(f"The record {new.name} {new.type} {new.value} already exists.")
        ptr = None
        if args.get("create_ptr") and new.type in ("A", "AAAA"):
            ptr = call.in_gui(lambda: svc.ptr_for(server, new))
            if ptr is not None and any(p.key == ptr.key for p in call.in_gui(lambda: svc.existing_ptrs(server, new.ip()))):
                ptr = None

        def write():
            svc.create_record(server, new)
            if ptr is not None:
                svc.create_record(server, ptr)

        def flow():
            yield from t.write_flow(server, new.zone, [], [new] + ([ptr] if ptr else []),
                                    tr("tx.create", rec=f"{new.name} {new.type}"), write,
                                    extra_zones=[ptr.zone] if ptr else [])
            if not any(r.key == new.key for r in svc.records(server, new.zone) or []):
                return {"ok": False, "info": "Not created (cancelled by the user or conflict with other changes)."}
            return {"ok": True, "created": _rec(new), "ptr": _rec(ptr) if ptr else None}
        return self._flow(call, flow)

    def delete_record(self, args, call):
        server, want = self._parse(call, args)
        t, svc, tr = self.tool, self.tool.svc, self.tool.tr
        recs = self._zone_recs(call, server, want.zone)
        found = [r for r in recs if r.key == want.key]
        if not found:
            raise UserError(f"No record {want.name} {want.type} {want.value} in zone {want.zone}.")

        def write():
            for r in found:
                svc.delete_record(server, r)

        def flow():
            yield from t.write_flow(server, want.zone, found, [], tr("tx.delete", n=len(found)), write)
            if any(r.key == want.key for r in svc.records(server, want.zone) or []):
                return {"ok": False, "info": "Not deleted (cancelled by the user or conflict with other changes)."}
            return {"ok": True, "deleted": [_rec(r) for r in found]}
        return self._flow(call, flow)
