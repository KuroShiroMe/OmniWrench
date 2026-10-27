"""Sitzung und Fachlogik von MS DNS Extended Management: Server, Zonen, Einträge, Transaktionen, Konflikte.

Alle Methoden laufen im Hintergrund (runner.Job) und sprechen nur mit dem Backend (backend.WmiBackend oder
einem Test-Backend). Jede Änderung legt nach dem erfolgreichen Schreiben ihre Gegenoperation im laufenden
Tx-Journal ab; schlägt ein späterer Schritt fehl, wird alles zurückgenommen (Stef-Regel aus dem DHCP-Tool:
"nicht, dass Dinge gelöscht bleiben"). Nicht zurücknehmbar und deshalb immer letzter Schritt: Zone löschen,
Aufräumen starten, Cache leeren.
"""

from __future__ import annotations

import datetime as _dt
import ipaddress
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from . import adrepl
from . import checks as ck
from . import dnsutil as du
from . import eventlog
from .wmidns import HostError


class UserError(Exception):
    """Verständliche Meldung für den Benutzer (ohne Traceback); details = technische Zeilen für die Detailansicht."""

    def __init__(self, text: str = "", details: list[str] | None = None):
        super().__init__(text)
        self.details = list(details or [])


class TxError(UserError):
    def __init__(self, text: str, raw: str, undone: int, fails: list[str]):
        super().__init__(text)
        self.raw, self.undone, self.fails = raw, undone, fails


class ConflictError(UserError):
    """Ein betroffener Eintrag wurde seit dem Laden von anderen geändert."""

    def __init__(self, text: str, lines: list[str], who: list[str]):
        super().__init__(text)
        self.lines, self.who = lines, who


class Tx:
    def __init__(self, title: str):
        self.title = title
        self.undo: list[tuple[str, Callable]] = []


def short_list(items, n: int = 15) -> str:
    lst = [str(x) for x in items]
    out = "\n".join("• " + x for x in lst[:n])
    if len(lst) > n:
        out += f"\n• … (+{len(lst) - n})"
    return out


class DnsService:
    def __init__(self, backend, tr: Callable, log: Callable[[str, bool], None] | None = None,
                 progress: Callable[[str, int, int], None] | None = None):
        self.backend = backend
        self.tr = tr
        self._log = log or (lambda t, e=False: None)
        self._progress = progress or (lambda t, i=0, n=0: None)
        self.cancel = threading.Event()
        self.scan_cancel = threading.Event()     # eigene Abbruchmarke der Hintergrundprüfung
        self.reset()

    def reset(self) -> None:
        self.primary = ""
        self.user = ""
        self.secrets: dict[str, str] = {}             # Passwörter nur im Speicher (Server -> Passwort)
        self.users: dict[str, str] = {}
        self.servers: dict[str, dict] = {}            # Server -> Info (wmidns.server_from_props)
        self.zones: dict[str, dict[str, dict]] = {}   # Server -> Zone -> Zonen-Dict
        self.cache: dict[tuple[str, str], dict] = {}  # (Server, Zone) -> {recs, loaded, serial}
        self.errors: dict[str, str] = {}              # Server -> letzter Ladefehler
        self.dhcp_server = ""
        self.dhcp_user = ""
        self.dhcp_secret = ""
        self._tx: Tx | None = None
        self.events_error: dict[str, str] = {}
        self.repl: dict[tuple[str, str], dict] = {}  # (Server, Zone) -> letzter Replikationsstand (repl_status)

    # --- Protokoll ----------------------------------------------------------------------------------
    def log(self, text: str, is_error: bool = False) -> None:
        self._log(text, is_error)

    def progress(self, text: str, i: int = 0, n: int = 0) -> None:
        self._progress(text, i, n)

    def host_text(self, msg: str) -> str:
        tr = self.tr
        m = re.match(r"^@WMI:(\w+):([^:]*):([0-9A-Fa-f]+):(.*)$", msg, re.S)
        if m:
            what, server, code, text = m.group(1), m.group(2), m.group(3), m.group(4).strip()
            return tr("wmi.fail", what=tr(f"wmi.op.{what}"), server=server, text=text or "–", code="0x" + code.upper())
        m = re.match(r"^@ERR:(\w+):(.*)$", msg, re.S)
        if m:
            key, parts = m.group(1), m.group(2).split("|")
            return tr(f"err.{key}", value=parts[0], code=parts[1] if len(parts) > 1 else "",
                      text=parts[2] if len(parts) > 2 else "")
        m = re.match(r"^@RPC:(\w+):([^:]*):(\d+):(.*)$", msg, re.S)
        if m:
            return tr("err.events", server=m.group(2), text=m.group(4).strip() or m.group(3))
        m = re.match(r"^@DHCP:([^:]*):(\d+):(.*)$", msg, re.S)
        if m:
            return tr("err.dhcp", server=m.group(1) or self.dhcp_server, text=m.group(3).strip() or m.group(2))
        return msg

    def _b(self, fn: str, *args, **kw):
        try:
            return getattr(self.backend, fn)(*args, **kw)
        except HostError as e:
            target = args[0] if args and isinstance(args[0], str) else ""
            raise UserError(self.host_text(str(e)),
                            [f"backend: {fn}({target})", f"raw: {e}"] + list(getattr(e, "details", []))) from None

    # --- Anmeldung ----------------------------------------------------------------------------------
    def hello(self) -> dict:
        return self.backend.hello()

    def connect(self, server: str, user: str = "", password: str = "") -> dict:
        server = du.norm(server)
        self.log(self.tr("log.connecting", server=server))
        info = self._b("connect", server, user, password)
        if info.get("creds_ignored"):
            self.log(self.tr("log.local_creds"))
        if not self.primary:
            self.primary = server
            self.user = user
        self.users[server] = user
        self.secrets[server] = password
        self.servers[server] = info
        self.log(self.tr("log.connected", server=server, version=info.get("version") or "?",
                         role=self.tr("srv.role_dc") if info.get("ds") else self.tr("srv.role_member")))
        return info

    def add_server(self, server: str, user: str | None = None, password: str | None = None) -> dict:
        """Weiteren Server in die Sitzung (gleiche Anmeldedaten, wenn nichts angegeben)."""
        if user is None:
            user, password = self.user, self.secrets.get(self.primary, "")
        info = self.connect(server, user, password or "")
        self.load_zones(du.norm(server))
        return info

    def remove_server(self, server: str) -> None:
        server = du.norm(server)
        self.backend.disconnect(server)
        for d in (self.servers, self.zones, self.users, self.secrets, self.errors):
            d.pop(server, None)
        for k in [k for k in self.cache if k[0] == server]:
            self.cache.pop(k, None)

    def logout(self) -> None:
        try:
            self.backend.disconnect()
        finally:
            self.reset()

    def credentials_for(self, server: str) -> tuple[str, str]:
        s = du.norm(server)
        return self.users.get(s, self.user), self.secrets.get(s, self.secrets.get(self.primary, ""))

    # --- Laden --------------------------------------------------------------------------------------
    def load_zones(self, server: str) -> dict[str, dict]:
        zs = self._b("zones", server)
        self.zones[server] = {z["name"]: z for z in sorted(zs, key=lambda z: (z["reverse"], z["name"]))}
        return self.zones[server]

    def load_all(self) -> None:
        for s in list(self.servers):
            try:
                self.servers[s] = {**self.servers[s], **self._b("info", s)}
                self.load_zones(s)
                self.errors.pop(s, None)
            except UserError as e:
                self.errors[s] = str(e)
                if s == self.primary:
                    raise
                self.log(str(e), True)

    def refresh_info(self, server: str) -> dict:
        self.servers[server] = {**self.servers.get(server, {}), **self._b("info", server)}
        return self.servers[server]

    def load_zone(self, server: str, zone: str) -> list[du.Rec]:
        recs = self._b("records", server, zone)
        soa = next((r for r in recs if r.type == "SOA"), None)
        self.cache[(server, zone)] = {"recs": recs, "loaded": du.now_utc(),
                                      "serial": soa.data.get("serial") if soa else None}
        return recs

    def records(self, server: str, zone: str) -> list[du.Rec] | None:
        c = self.cache.get((server, zone))
        return c["recs"] if c else None

    def related_zones(self, server: str, zone: str, recs: list[du.Rec]) -> list[str]:
        """Zonen, die für die Prüfung einer Zone mitgeladen werden: Reverse-Zonen der Adressen bzw. die
        Forward-Zonen der PTR-Ziele."""
        zones = self.zones.get(server, {})
        need: set[str] = set()
        if du.is_reverse_zone(zone):
            for r in recs:
                if r.type == "PTR":
                    z = du.best_zone(r.target(), [n for n in zones if not du.is_reverse_zone(n)])
                    if z:
                        need.add(z)
        else:
            for n, zi in zones.items():
                if du.is_reverse_zone(n) and zi.get("type") in (du.ZONE_PRIMARY, du.ZONE_SECONDARY):
                    need.add(n)
            for r in recs:
                t = r.target()
                if t and r.type in ("CNAME", "MX", "SRV", "NS"):
                    z = du.best_zone(t, [n for n in zones if not du.is_reverse_zone(n)])
                    if z:
                        need.add(z)
        need.discard(zone)
        return sorted(n for n in need if (server, n) not in self.cache
                      and zones.get(n, {}).get("type") in (du.ZONE_PRIMARY, du.ZONE_SECONDARY))

    def load_many(self, server: str, zones: list[str], threads: int = 4,
                  on_done: Callable[[str, object], None] | None = None,
                  cancel: threading.Event | None = None) -> dict[str, object]:
        """Mehrere Zonen parallel laden (Ergebnis: Zone -> Liste oder UserError)."""
        out: dict[str, object] = {}
        if not zones:
            return out

        cancel = cancel or self.cancel

        def one(z):
            if cancel.is_set():
                return z, UserError(self.tr("status.cancelled"))
            try:
                return z, self.load_zone(server, z)
            except UserError as e:
                return z, e
        with ThreadPoolExecutor(max_workers=max(1, min(threads, len(zones))), thread_name_prefix="dns") as ex:
            for z, res in ex.map(one, zones):
                out[z] = res
                if on_done:
                    on_done(z, res)
        return out

    def index(self, server: str) -> ck.Index:
        recs = {z: c["recs"] for (s, z), c in self.cache.items() if s == server}
        return ck.Index(self.zones.get(server, {}), recs)

    # --- Prüfung ------------------------------------------------------------------------------------
    def zone_findings(self, server: str, zone: str, idx: ck.Index | None = None) -> list[ck.Finding]:
        z = self.zones.get(server, {}).get(zone)
        if z is None:
            return []
        recs = self.records(server, zone)
        srv = self.servers.get(server)
        out = ck.zone_settings_findings(z, recs, self.tr, srv)
        if recs is not None:
            out += ck.record_findings(z, recs, idx or self.index(server), self.tr, server=srv)
        return ck.sort_findings(out)

    def scan(self, server: str, probe_ns: bool, on_zone: Callable[[str, list[ck.Finding]], None] | None = None,
             dhcp: bool = False, progress: Callable[[str, int, int], None] | None = None) -> dict:
        """Ganzen Server prüfen: alle Zonen laden, Einträge, Server, Namensserver, Vergleich, DHCP."""
        tr = self.tr
        prog = progress or self.progress
        self.scan_cancel.clear()
        zones = self.zones.get(server) or self.load_zones(server)
        names = [n for n, z in zones.items() if z["type"] in (du.ZONE_PRIMARY, du.ZONE_SECONDARY) and not z.get("auto")]
        todo = [n for n in names if (server, n) not in self.cache]
        done = [0]

        def loaded(z, res):
            done[0] += 1
            prog(tr("status.scan_zone", zone=z, i=done[0], n=len(todo)), done[0], len(todo))
            if isinstance(res, UserError):
                self.log(tr("log.zone_failed", zone=z, error=str(res)), True)
        self.load_many(server, todo, on_done=loaded, cancel=self.scan_cancel)
        if self.scan_cancel.is_set():
            return {"partial": True, "findings": [], "server": server}
        idx = self.index(server)
        findings: list[ck.Finding] = ck.server_findings(self.servers.get(server, {}), list(zones.values()), tr)
        for n, z in zones.items():
            fs = self.zone_findings(server, n, idx)
            findings += fs
            if on_zone:
                on_zone(n, fs)
        if probe_ns and not self.scan_cancel.is_set():
            findings += self.probe_findings(server, idx, prog)
        if len(self.servers) > 1 and not self.scan_cancel.is_set():
            findings += self.compare(probe=probe_ns)["findings"]
        if dhcp and self.dhcp_server and not self.scan_cancel.is_set():
            try:
                findings += self.dhcp_compare(server)["findings"]
            except UserError as e:
                self.log(str(e), True)
        return {"partial": self.scan_cancel.is_set(), "findings": ck.sort_findings(findings), "server": server,
                "zones": len(zones), "records": sum(len(self.cache[(server, n)]["recs"]) for n in zones
                                                    if (server, n) in self.cache)}

    def probe_findings(self, server: str, idx: ck.Index, progress: Callable | None = None) -> list[ck.Finding]:
        """Namensserver jeder Primärzone und die Weiterleitungen direkt abfragen (dnspython, UDP 53)."""
        tr = self.tr
        out: list[ck.Finding] = []
        zones = self.zones.get(server, {})
        jobs = []
        for n, z in zones.items():
            if z["type"] != du.ZONE_PRIMARY or z.get("auto"):
                continue
            recs = self.records(server, n) or []
            for r in recs:
                if r.type == "NS" and r.name == n:
                    jobs.append((n, r.target()))
        addr_cache: dict[str, list[str]] = {}

        def addr(host):
            if host not in addr_cache:
                a = idx.addresses(host) or self.backend.resolve(host)
                addr_cache[host] = a
            return addr_cache[host]

        def one(job):
            zone, ns = job
            ips = addr(ns)
            if not ips:
                return zone, ns, {"ok": False, "error": tr("chk.ns_unresolved")}
            return zone, ns, self.backend.probe(ips[0], zone, "SOA")
        per_zone: dict[str, dict[str, dict]] = {}
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="dnsprobe") as ex:
            for i, (zone, ns, res) in enumerate(ex.map(one, jobs)):
                per_zone.setdefault(zone, {})[ns] = res
                if self.scan_cancel.is_set():
                    break
                (progress or self.progress)(tr("status.probe", zone=zone, ns=ns), i + 1, len(jobs))
        for zone, res in per_zone.items():
            out += ck.ns_findings(zone, res, tr, server)
        fwd = self.servers.get(server, {}).get("forwarders") or []
        if fwd:
            res = {ip: self.backend.probe(ip, "microsoft.com", "A") for ip in fwd}
            out += ck.forwarder_findings(server, res, tr)
        return out

    def compare(self, probe: bool = False) -> dict:
        """Vergleich aller Server der Sitzung (Einstellungen, AD-Zonen, Seriennummern)."""
        serials: dict[tuple[str, str], int | None] = {}
        if probe:
            for s, info in self.servers.items():
                ip = (info.get("server_addresses") or [None])[0] or s
                for zn, z in self.zones.get(s, {}).items():
                    if z.get("ds") and z["type"] == du.ZONE_PRIMARY and not z.get("auto"):
                        serials[(s, zn)] = self.backend.probe(ip, zn, "SOA").get("serial")
        else:
            for (s, zn), c in self.cache.items():
                if self.zones.get(s, {}).get(zn, {}).get("ds"):
                    serials[(s, zn)] = c.get("serial")
        return {"findings": ck.compare_findings(self.servers, self.zones, self.tr, serials), "serials": serials}

    def dhcp_compare(self, server: str) -> dict:
        if not self.dhcp_server:
            raise UserError(self.tr("err.no_dhcp_server"))
        leases = self._b("dhcp_leases", self.dhcp_server, self.dhcp_user, self.dhcp_secret)
        self.log(self.tr("log.dhcp_loaded", server=self.dhcp_server, n=len(leases)))
        return {"leases": leases, "findings": ck.dhcp_findings(leases, self.index(server), self.tr, server)}

    def discover_servers(self) -> list[str]:
        """Weitere DNS-Server: Namensserver der Zonen und (in Domänen) alle DCs aus _ldap._tcp.dc._msdcs."""
        found: set[str] = set()
        for s, zones in self.zones.items():
            for zn, z in zones.items():
                recs = self.records(s, zn) or []
                for r in recs:
                    if r.type == "NS" and r.name == zn:
                        found.add(r.target())
            for zn, z in zones.items():
                if z.get("ds") and not du.is_reverse_zone(zn) and not zn.startswith("_msdcs"):
                    found.update(self.backend.srv_lookup(f"_ldap._tcp.dc._msdcs.{zn}"))
        have = set(self.servers)
        short = {h.split(".")[0] for h in have}
        return sorted(h for h in found if h and h not in have and h.split(".")[0] not in short)

    # --- Suche --------------------------------------------------------------------------------------
    def search(self, text: str, types: set[str] | None = None, server: str | None = None) -> list[du.Rec]:
        """Suche in allen geladenen Zonen: Name (Teilwort), IP, Netz (CIDR) oder Ziel."""
        q = text.strip().lower()
        net = None
        if "/" in q:
            try:
                net = ipaddress.ip_network(q, strict=False)
            except ValueError:
                net = None
        ip = du.parse_ip(q) if not net else None
        out = []
        for (s, zn), c in self.cache.items():
            if server and s != server:
                continue
            for r in c["recs"]:
                if types and r.type not in types:
                    continue
                if not q:
                    out.append(r)
                    continue
                rip = r.ip() or (du.ip_from_ptr(r.name) if r.type == "PTR" else "")
                if net is not None:
                    if rip:
                        try:
                            if ipaddress.ip_address(rip) in net:
                                out.append(r)
                        except ValueError:
                            pass
                    continue
                if ip:
                    if rip == ip:
                        out.append(r)
                    continue
                if q in r.name or q in r.value.lower():
                    out.append(r)
        return out

    # --- Transaktionen ------------------------------------------------------------------------------
    def tx_begin(self, title: str) -> tuple[Tx, Tx | None]:
        outer = self._tx
        self._tx = Tx(title)
        return self._tx, outer

    def tx_commit(self, tx: Tx, outer: Tx | None) -> None:
        self._tx = outer
        if outer is not None:
            outer.undo += tx.undo

    def _undo(self, label: str, fn: Callable) -> None:
        if self._tx is not None:
            self._tx.undo.append((label, fn))

    def tx_rollback(self, tx: Tx) -> list[str]:
        tr = self.tr
        self._tx = None
        fails: list[str] = []
        if not tx.undo:
            return fails
        self.log(tr("log.tx_rollback", title=tx.title, n=len(tx.undo)), True)
        for label, fn in reversed(tx.undo):
            try:
                fn()
                self.log("  ↶ " + label)
            except Exception as e:  # noqa: BLE001 - jeder Schritt wird versucht
                text = self.host_text(str(e)) if isinstance(e, HostError) else str(e)
                fails.append(f"{label}: {text}")
                self.log("  ✗ " + tr("log.tx_undo_failed", step=label, error=text), True)
        self.log(tr("log.tx_rollback_done" if not fails else "log.tx_rollback_partial", n=len(fails)), bool(fails))
        return fails

    def tx_fail(self, e: Exception, tx: Tx, outer: Tx | None) -> TxError:
        raw = e.raw if isinstance(e, TxError) else str(e) if isinstance(e, UserError) else f"{type(e).__name__}: {e}"
        done = e.undone if isinstance(e, TxError) else 0
        fails = (e.fails if isinstance(e, TxError) else []) + self.tx_rollback(tx)
        self._tx = outer
        n = done + len(tx.undo)
        if not n:
            text = raw
        elif fails:
            text = self.tr("tx.partial", error=raw, n=len(fails), list=short_list(fails, 10))
        else:
            text = self.tr("tx.rolled_back", error=raw, n=n)
        err = TxError(text, raw, n, fails)
        err.details = [f"transaction: {tx.title}"] + list(getattr(e, "details", [])) + \
            ([f"rollback failed: {f}" for f in fails] if fails else [])
        return err

    def tx_message_cancel(self, tx: Tx, fails: list[str]) -> str:
        if fails:
            return self.tr("tx.cancel_partial", n=len(fails), list=short_list(fails, 10))
        return self.tr("tx.cancel_done", n=len(tx.undo))

    def atomic(self, title: str, fn: Callable):
        tx, outer = self.tx_begin(title)
        try:
            res = fn()
        except Exception as e:  # noqa: BLE001 - jeder Fehler löst die Rücknahme aus
            raise self.tx_fail(e, tx, outer) from None
        self.tx_commit(tx, outer)
        return res

    # --- Einträge ändern ----------------------------------------------------------------------------
    def _label(self, rec: du.Rec) -> str:
        return f"{rec.name} {rec.type} {rec.value}"

    def _raw_create(self, server: str, rec: du.Rec) -> None:
        self.backend.create_record(server, rec)

    def _raw_delete(self, server: str, rec: du.Rec) -> None:
        self.backend.delete_record(server, rec)

    def create_record(self, server: str, rec: du.Rec) -> None:
        tr = self.tr
        self._b("create_record", server, rec)
        self.log(tr("log.created", rec=self._label(rec), zone=rec.zone))
        self._undo(tr("undo.delete", rec=self._label(rec)), lambda: self._raw_delete(server, rec))
        self._cache_add(server, rec)

    def delete_record(self, server: str, rec: du.Rec) -> None:
        tr = self.tr
        self._b("delete_record", server, rec)
        self.log(tr("log.deleted", rec=self._label(rec), zone=rec.zone))
        self._undo(tr("undo.create", rec=self._label(rec)), lambda: self._raw_create(server, rec))
        self._cache_remove(server, rec)

    def replace_record(self, server: str, old: du.Rec, new: du.Rec) -> None:
        """Ändern = alten Eintrag löschen, neuen anlegen (WMI kennt kein typunabhängiges Ändern). Als
        Transaktion: Scheitert das Anlegen, kommt der alte Eintrag zurück."""
        self.atomic(self.tr("tx.edit", rec=self._label(old)), lambda: (
            self.delete_record(server, old), self.create_record(server, new)))

    def _cache_add(self, server: str, rec: du.Rec) -> None:
        c = self.cache.get((server, rec.zone))
        if c is not None and not any(r.key == rec.key for r in c["recs"]):
            c["recs"].append(rec)

    def _cache_remove(self, server: str, rec: du.Rec) -> None:
        c = self.cache.get((server, rec.zone))
        if c is not None:
            c["recs"] = [r for r in c["recs"] if r.key != rec.key]

    def ptr_for(self, server: str, rec: du.Rec) -> du.Rec | None:
        """Passender PTR-Eintrag zu einem A/AAAA-Eintrag (None, wenn keine Reverse-Zone vorhanden ist)."""
        ip = rec.ip()
        if not ip:
            return None
        zones = [n for n, z in self.zones.get(server, {}).items()
                 if du.is_reverse_zone(n) and z["type"] == du.ZONE_PRIMARY]
        pn = du.ptr_name(ip)
        rz = du.best_zone(pn, zones)
        if not rz:
            return None
        return du.Rec(zone=rz, name=pn, type="PTR", data={"host": rec.name}, ttl=rec.ttl, ts=rec.ts)

    def existing_ptrs(self, server: str, ip: str) -> list[du.Rec]:
        pn = du.ptr_name(ip)
        out = []
        for (s, zn), c in self.cache.items():
            if s == server and du.is_reverse_zone(zn):
                out += [r for r in c["recs"] if r.type == "PTR" and r.name == pn]
        return out

    # --- Zonen und Server ändern --------------------------------------------------------------------
    def set_zone(self, server: str, zone: str, values: dict) -> None:
        tr = self.tr
        old = self.zones[server][zone]
        prev = {k: old.get(k) for k in values}
        if prev == values:
            return
        self._b("set_zone", server, zone, values)
        self.log(tr("log.zone_set", zone=zone, values=", ".join(f"{k}={v}" for k, v in values.items())))
        self._undo(tr("undo.zone_set", zone=zone), lambda: self.backend.set_zone(server, zone, prev))
        old.update(values)

    def set_transfers(self, server: str, zone: str, secure: int, secondaries: list[str], notify: int,
                      notify_servers: list[str]) -> None:
        tr = self.tr
        z = self.zones[server][zone]
        prev = (z["secure_secondaries"], list(z["secondaries"]), z["notify"], list(z["notify_servers"]))
        new = (int(secure), list(secondaries), int(notify), list(notify_servers))
        if prev == new:
            return
        self._b("set_transfers", server, zone, *new)
        self.log(tr("log.transfers_set", zone=zone))
        self._undo(tr("undo.transfers", zone=zone), lambda: self.backend.set_transfers(server, zone, *prev))
        z.update({"secure_secondaries": new[0], "secondaries": new[1], "notify": new[2], "notify_servers": new[3]})

    def set_server(self, server: str, values: dict) -> None:
        tr = self.tr
        info = self.servers[server]
        prev = {k: info.get(k) for k in values}
        if prev == values:
            return
        self._b("set_server", server, values)
        self.log(tr("log.server_set", server=server, values=", ".join(values)))
        self._undo(tr("undo.server_set", server=server), lambda: self.backend.set_server(server, prev))
        info.update(values)

    def create_zone(self, server: str, name: str, ztype: int, ds: bool, data_file: str = "",
                    masters: list[str] | None = None, admin: str = "") -> None:
        tr = self.tr
        name = du.norm(name)
        self._b("create_zone", server, name, ztype, ds, data_file, masters or [], admin)
        self.log(tr("log.zone_created", zone=name, server=server))
        self._undo(tr("undo.zone_delete", zone=name), lambda: self.backend.delete_zone(server, name))
        self.load_zones(server)

    def delete_zone(self, server: str, zone: str) -> None:
        """Endgültig (nicht zurücknehmbar): immer der letzte Schritt einer Aktion."""
        self._b("delete_zone", server, zone)
        self.log(self.tr("log.zone_deleted", zone=zone, server=server))
        self.zones.get(server, {}).pop(zone, None)
        self.cache.pop((server, zone), None)

    def zone_action(self, server: str, zone: str, action: str) -> None:
        self._b("zone_action", server, zone, action)
        self.log(self.tr("log.zone_action", zone=zone, action=self.tr(f"zact.{action}")))

    def start_scavenging(self, server: str) -> None:
        self._b("start_scavenging", server)
        self.log(self.tr("log.scavenging", server=server))

    def clear_cache(self, server: str) -> None:
        self._b("clear_cache", server)
        self.log(self.tr("log.cache_cleared", server=server))

    def age_node(self, server: str, zone: str, node: str) -> None:
        self._b("age_node", server, zone, node)

    # --- Replikation --------------------------------------------------------------------------------
    def repl_peers(self, server: str, zone: str) -> list[str]:
        """Weitere verbundene Server, die dieselbe Zone mit Einträgen halten (primär/sekundär; nicht Stub/Weiterleitung).
        AD-integrierte Zonen zählen nur mit AD-integrierten Gegenstücken (gleiche Partition), dateibasierte mit allen."""
        z = self.zones.get(server, {}).get(zone)
        if z is None:
            return []
        out = []
        for s in self.servers:
            if s == server or s in self.errors:
                continue
            pz = self.zones.get(s, {}).get(zone)
            if pz is None or pz["type"] not in (du.ZONE_PRIMARY, du.ZONE_SECONDARY):
                continue
            if z.get("ds") and pz["type"] == du.ZONE_PRIMARY and not pz.get("ds"):
                continue
            out.append(s)
        return out

    def _unconnected_secondaries(self, server: str, zone: str) -> list[str]:
        """Eingetragene sekundäre Server / Benachrichtigungsziele (Adressen), die nicht in der Sitzung sind."""
        z = self.zones.get(server, {}).get(zone) or {}
        if z.get("ds") or z.get("type") != du.ZONE_PRIMARY:
            return []
        known = set()
        for s, info in self.servers.items():
            known.update(info.get("server_addresses") or [])
        return [ip for ip in dict.fromkeys((z.get("secondaries") or []) + (z.get("notify_servers") or []))
                if ip not in known]

    def repl_status(self, server: str, zone: str) -> dict:
        """Stand der Zone auf allen weiteren verbundenen Servern: deren Einträge (Schlüssel), Seriennummer,
        letzte Übertragung; nicht verbundene sekundäre Server nur per SOA-Abfrage (ohne Anmeldung)."""
        z = self.zones.get(server, {}).get(zone) or {}
        own = self.cache.get((server, zone)) or {}
        peers: dict[str, dict] = {}
        for p in self.repl_peers(server, zone):
            entry: dict = {"ok": False, "error": "", "keys": set(), "serial": None}
            try:
                pz = self._b("zone", p, zone)
                self.zones.setdefault(p, {})[zone] = pz
                recs = self.load_zone(p, zone)
                entry.update(ok=True, keys={r.key for r in recs if r.type != "SOA"},
                             serial=(self.cache.get((p, zone)) or {}).get("serial"), type=pz["type"], ds=pz.get("ds"),
                             last_xfr=pz.get("last_xfr"), last_soa=pz.get("last_soa_check"))
            except UserError as e:
                entry["error"] = str(e)
            peers[p] = entry
        others = []
        for ip in self._unconnected_secondaries(server, zone):
            r = self.backend.probe(ip, zone, "SOA")
            others.append({"ip": ip, "ok": bool(r.get("ok")) and r.get("serial") is not None, "serial": r.get("serial"),
                           "error": r.get("error") or r.get("rcode") or ""})
        serial = own.get("serial")
        if not z.get("ds"):
            try:    # nur zur Anzeige; der Zwischenspeicher behält seine Seriennummer (Konfliktprüfung)
                serial = self.zone_serial(server, zone)
            except UserError:
                pass
        st = {"server": server, "zone": zone, "time": du.now_utc(), "ds": bool(z.get("ds")),
              "serial": serial, "own": {r.key for r in own.get("recs", []) if r.type != "SOA"},
              "peers": peers, "others": others}
        self.repl[(server, zone)] = st
        return st

    @staticmethod
    def repl_of(st: dict | None, key: str) -> dict | None:
        """Für einen Eintrag: {have: [Server], missing: [Server], unknown: [Server]} (eigener Server zählt mit)."""
        if not st or not st["peers"]:
            return None
        have, missing, unknown = [st["server"]], [], []
        for p, e in st["peers"].items():
            if not e["ok"]:
                unknown.append(p)
            elif key in e["keys"]:
                have.append(p)
            else:
                missing.append(p)
        return {"have": have, "missing": missing, "unknown": unknown}

    @staticmethod
    def repl_diff(st: dict | None) -> dict:
        """Zonenweit: Einträge, die auf mindestens einem Partner fehlen, und solche, die nur auf Partnern stehen."""
        if not st:
            return {"missing": {}, "extra": {}}
        missing, extra = {}, {}
        for p, e in st["peers"].items():
            if e["ok"]:
                missing[p] = st["own"] - e["keys"]
                extra[p] = e["keys"] - st["own"]
        return {"missing": missing, "extra": extra}

    def repl_pending(self, st: dict, present: set[str], absent: set[str]) -> list[str]:
        """Partner, auf denen eine eigene Änderung noch nicht angekommen ist (neue fehlen / gelöschte noch da)."""
        out = []
        for p, e in st["peers"].items():
            if e["ok"] and ((present - e["keys"]) or (absent & e["keys"])):
                out.append(p)
        return out

    def replicate(self, server: str, zone: str) -> dict:
        """Replikation der Zone anstoßen. AD-integriert: AD-Replikation der Partition von server an alle Partner,
        danach UpdateFromDS auf den Partnern (sonst lesen sie AD erst nach bis zu 180 s). Dateibasiert:
        ForceRefresh (SOA prüfen, bei neuerer Seriennummer übertragen) auf den sekundären Servern.
        Fehlt ein Recht, geht es mit dem Rest weiter; die Meldung nennt das fehlende Recht.
        Ergebnis {done: [Zeilen], warnings: [Texte], details: [Zeilen], denied: bool}."""
        tr = self.tr
        z = self.zones.get(server, {}).get(zone)
        if z is None:
            z = self._b("zone", server, zone)
        peers = self.repl_peers(server, zone)
        done, warns, details, denied = [], [], [f"zone: {zone} @ {server}", f"peers: {', '.join(peers) or '-'}"], False
        if z.get("ds"):
            nc = ""
            try:
                dn = self._b("zone_dn", server, zone)
                nc = adrepl.partition_of(dn)
                details.append(f"zone DN: {dn}")
                if not nc:
                    raise UserError(tr("err.no_partition", value=dn))
                details.append(f"partition: {nc}")
                self.progress(tr("status.ad_sync", part=adrepl.partition_label(nc)))
                try:
                    synced = self.backend.ad_sync(server, nc)
                except HostError as e:
                    details += [f"raw: {e}"] + list(e.details)
                    if str(e).startswith("@ERR:repl_denied:"):
                        denied = True
                        raise UserError(tr("repl.denied", server=server, part=adrepl.partition_label(nc),
                                           user=self.users.get(server) or self.user or tr("repl.current_user"))) from None
                    raise UserError(self.host_text(str(e))) from None
                done.append(tr("repl.ad_done", server=server, part=adrepl.partition_label(nc), n=len(synced)))
                details += [f"synced: {x}" for x in synced]
            except UserError as e:
                warns.append(str(e))
                details += e.details
            for p in peers:
                if not (self.zones.get(p, {}).get(zone) or {}).get("ds"):
                    continue
                try:
                    self._b("zone_action", p, zone, "from_ds")
                    done.append(tr("repl.from_ds", server=p))
                except UserError as e:
                    warns.append(str(e))
                    details += e.details
        else:
            targets = [p for p in peers if self.zones[p][zone]["type"] == du.ZONE_SECONDARY]
            if z["type"] in (du.ZONE_SECONDARY, du.ZONE_STUB):
                targets.insert(0, server)
            for p in targets:
                try:
                    self._b("zone_action", p, zone, "refresh")
                    done.append(tr("repl.refresh", server=p))
                except UserError as e:
                    warns.append(str(e))
                    details += e.details
            if not targets:
                warns.append(tr("repl.no_secondaries", zone=zone))
            other = self._unconnected_secondaries(server, zone)
            if other:
                warns.append(tr("repl.unconnected", list=", ".join(other)))
        for line in done:
            self.log(line)
        for w in warns:
            self.log(w, True)
        if not done:
            raise UserError("\n\n".join(warns) or tr("repl.nothing"), details)
        return {"done": done, "warnings": warns, "details": details, "denied": denied}

    # --- Änderungen anderer -------------------------------------------------------------------------
    def zone_serial(self, server: str, zone: str) -> int | None:
        soa = self._b("soa", server, zone)
        return soa.data.get("serial") if soa else None

    def zone_changed(self, server: str, zone: str) -> bool:
        c = self.cache.get((server, zone))
        if c is None or c.get("serial") is None:
            return False
        return self.zone_serial(server, zone) != c["serial"]

    def guard(self, server: str, zone: str, touched: list[du.Rec], new: list[du.Rec] | None = None) -> list[str]:
        """Vor dem Schreiben: Hat jemand die Zone seit dem Laden geändert? Liefert die Konfliktzeilen
        (leer = alles in Ordnung). Lädt die Zone dabei neu, wenn sie sich geändert hat."""
        tr = self.tr
        c = self.cache.get((server, zone))
        if c is None:
            return []
        if not self.zone_changed(server, zone):
            return []
        old_keys = {r.key: r for r in c["recs"]}
        fresh = self.load_zone(server, zone)
        fresh_keys = {r.key: r for r in fresh}
        lines = []
        for r in touched:
            cur = fresh_keys.get(r.key)
            if cur is None:
                lines.append(tr("conflict.gone", rec=self._label(r)))
            elif cur.ttl != r.ttl or cur.dynamic != r.dynamic:
                lines.append(tr("conflict.changed", rec=self._label(r)))
        for r in new or []:
            if r.key in fresh_keys and r.key not in old_keys:
                lines.append(tr("conflict.exists", rec=self._label(r)))
        return lines

    def diff_zone(self, before: list[du.Rec], after: list[du.Rec]) -> list[str]:
        a, b = {r.key: r for r in before}, {r.key: r for r in after}
        tr = self.tr
        lines = [tr("diff.added", rec=self._label(b[k])) for k in b if k not in a and b[k].type != "SOA"]
        lines += [tr("diff.removed", rec=self._label(a[k])) for k in a if k not in b and a[k].type != "SOA"]
        lines += [tr("diff.changed", rec=self._label(b[k])) for k in b if k in a and not b[k].same_content(a[k])
                  and b[k].type != "SOA"]
        return lines

    def change_events(self, server: str, since_utc: str, zone: str | None = None, max_n: int = 300) -> list[dict]:
        """Ereignisse aus dem Audit-Protokoll, mit Lesehilfe; unlesbares Protokoll -> [] und ein Logeintrag."""
        try:
            evs = self.backend.events(server, since_utc, max_n)
        except HostError as e:
            text = self.host_text(str(e))
            if self.events_error.get(server) != text:
                self.events_error[server] = text
                self.log(self.tr("log.events_error", server=server, error=text))
            return []
        except Exception as e:  # noqa: BLE001 - Protokoll ist Zusatzinformation, nie Abbruchgrund
            self.log(self.tr("log.events_error", server=server, error=str(e)))
            return []
        self.events_error.pop(server, None)
        zones = list(self.zones.get(server, {}))
        out = []
        for ev in evs:
            ev = dict(ev)
            ev.update(eventlog.classify(ev, zones))
            if zone and ev.get("zone") and ev["zone"] != zone:
                continue
            out.append(ev)
        return out

    def who_changed(self, server: str, zone: str, since: _dt.datetime) -> list[str]:
        evs = self.change_events(server, eventlog.iso_utc(since), zone, 50)
        return [f"{e.get('time', '')} {e.get('user') or '?'}: {e.get('obj') or e.get('text', '')[:80]}" for e in evs[:8]]

    # --- Massenänderungen ---------------------------------------------------------------------------
    def bulk_ttl(self, server: str, recs: list[du.Rec], ttl: int) -> int:
        n = 0
        for r in recs:
            if r.ttl == ttl or r.type == "SOA":
                continue
            new = du.Rec(zone=r.zone, name=r.name, type=r.type, data=dict(r.data), ttl=ttl, ts=r.ts, text=r.text)
            self.delete_record(server, r)
            self.create_record(server, new)
            n += 1
        return n

    def bulk_static(self, server: str, recs: list[du.Rec]) -> int:
        n = 0
        for r in recs:
            if not r.dynamic:
                continue
            new = du.Rec(zone=r.zone, name=r.name, type=r.type, data=dict(r.data), ttl=r.ttl, ts=None, text=r.text)
            self.delete_record(server, r)
            self.create_record(server, new)
            n += 1
        return n

    def bulk_delete(self, server: str, recs: list[du.Rec]) -> int:
        for r in recs:
            self.delete_record(server, r)
        return len(recs)
