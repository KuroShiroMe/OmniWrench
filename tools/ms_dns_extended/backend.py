"""Zugriffsschicht des Tools: WMI je DNS-Server, Ereignisprotokoll, DHCP-Leases (nur lesen) und DNS-Abfragen.

service.DnsService spricht nur mit dieser Schnittstelle. Für Tests und Screenshots ersetzt ein Fake-Backend mit
denselben Methoden diese Klasse (MsDnsExtended.backend_factory, siehe scripts/dns_check/fake_backend.py).

Alle Methoden sind threadsicher und dürfen aus Hintergrund-Threads aufgerufen werden.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

from . import dhcpread
from . import dnsutil as du
from . import eventlog
from .wmidns import HostError, WmiServer, is_local, load


def _ensure_lib() -> None:
    lib = Path(__file__).resolve().parent / "_lib"
    if lib.is_dir() and str(lib) not in sys.path:
        sys.path.insert(0, str(lib))


def _dns():
    _ensure_lib()
    try:
        import dns.message  # noqa: PLC0415
        import dns.query  # noqa: PLC0415
        import dns.rcode  # noqa: PLC0415
        import dns.rdatatype  # noqa: PLC0415
        import dns.resolver  # noqa: PLC0415
    except ImportError:
        return None
    return dns


class WmiBackend:
    def __init__(self):
        self._lock = threading.Lock()
        self._servers: dict[str, WmiServer] = {}
        self._creds: dict[str, tuple[str, str]] = {}
        self._events: eventlog.EventReader | None = None
        self._cancel = threading.Event()

    # --- Verwaltung -----------------------------------------------------------------------------------
    def hello(self) -> dict:
        ok, err = True, ""
        try:
            load()
        except HostError as e:
            ok, err = False, str(e)
        dom = os.environ.get("USERDOMAIN", "")
        return {"wmi": ok, "error": err, "dnspython": _dns() is not None, "dhcp": dhcpread.available(),
                "user": f"{dom}\\{os.environ.get('USERNAME', '')}" if dom else os.environ.get("USERNAME", ""),
                "computer": os.environ.get("COMPUTERNAME", "")}

    def kill(self) -> None:
        self._cancel.set()

    def reset_cancel(self) -> None:
        self._cancel.clear()

    def close(self) -> None:
        with self._lock:
            for s in self._servers.values():
                s.close()
            self._servers.clear()
            self._creds.clear()

    def _srv(self, server: str) -> WmiServer:
        with self._lock:
            s = self._servers.get(du.norm(server))
        if s is None:
            raise HostError(f"@ERR:not_connected:{server}")
        return s

    def connect(self, server: str, user: str = "", password: str = "") -> dict:
        s = WmiServer(server, user, password)
        info = s.info()
        info["local"] = s.local
        info["creds_ignored"] = bool(s.local and user)
        with self._lock:
            old = self._servers.pop(du.norm(server), None)
            if old:
                old.close()
            self._servers[du.norm(server)] = s
            self._creds[du.norm(server)] = (s.user, s._password)
        return info

    def disconnect(self, server: str | None = None) -> None:
        with self._lock:
            if server:
                s = self._servers.pop(du.norm(server), None)
                self._creds.pop(du.norm(server), None)
                if s:
                    s.close()
            else:
                for s in self._servers.values():
                    s.close()
                self._servers.clear()
                self._creds.clear()

    # --- Server und Zonen -----------------------------------------------------------------------------
    def info(self, server: str) -> dict:
        s = self._srv(server)
        out = s.info()
        out["local"] = s.local
        return out

    def set_server(self, server: str, values: dict) -> None:
        self._srv(server).set_server(values)

    def start_scavenging(self, server: str) -> None:
        self._srv(server).start_scavenging()

    def clear_cache(self, server: str) -> None:
        self._srv(server).clear_cache()

    def zones(self, server: str) -> list[dict]:
        return self._srv(server).zones()

    def zone(self, server: str, zone: str) -> dict:
        return self._srv(server).zone(zone)

    def set_zone(self, server: str, zone: str, values: dict) -> None:
        self._srv(server).set_zone(zone, values)

    def set_transfers(self, server: str, zone: str, secure: int, secondaries: list[str], notify: int,
                      notify_servers: list[str]) -> None:
        self._srv(server).set_transfers(zone, secure, secondaries, notify, notify_servers)

    def zone_action(self, server: str, zone: str, action: str) -> None:
        self._srv(server).zone_action(zone, action)

    def create_zone(self, server: str, name: str, ztype: int, ds: bool, data_file: str = "",
                    masters: list[str] | None = None, admin: str = "") -> None:
        self._srv(server).create_zone(name, ztype, ds, data_file, masters, admin)

    def delete_zone(self, server: str, zone: str) -> None:
        self._srv(server).delete_zone(zone)

    # --- Einträge -------------------------------------------------------------------------------------
    def records(self, server: str, zone: str) -> list[du.Rec]:
        return self._srv(server).records(zone)

    def soa(self, server: str, zone: str) -> du.Rec | None:
        return self._srv(server).soa(zone)

    def exists(self, server: str, rec: du.Rec) -> bool:
        return self._srv(server).exists(rec)

    def create_record(self, server: str, rec: du.Rec) -> None:
        self._srv(server).create_record(rec)

    def delete_record(self, server: str, rec: du.Rec) -> None:
        self._srv(server).delete_record(rec)

    def age_node(self, server: str, zone: str, node: str) -> None:
        self._srv(server).age_node(zone, node)

    # --- Ereignisprotokoll ----------------------------------------------------------------------------
    def events(self, server: str, since_utc: str, max_n: int = 300) -> list[dict]:
        with self._lock:
            if self._events is None:
                self._events = eventlog.EventReader()
            reader = self._events
            user, pw = self._creds.get(du.norm(server), ("", ""))
        if user:
            u, d = dhcpread.split_user(user)
            login = (u, d, pw)
        else:
            login = (None, None, None)
        target = "localhost" if is_local(server) else server
        try:
            return reader.query(target, login, since_utc, max_n)
        except RuntimeError as e:
            raise HostError(str(e)) from None

    # --- DHCP (nur lesen) -----------------------------------------------------------------------------
    def dhcp_leases(self, server: str, user: str = "", password: str = "") -> list[dict]:
        try:
            return dhcpread.leases(server, user, password)
        except dhcpread.DhcpReadError as e:
            raise HostError(str(e)) from None
        except OSError as e:
            raise HostError(f"@ERR:no_dhcpapi:{e}") from None

    # --- DNS-Abfragen (dnspython, ohne Anmeldung) -----------------------------------------------------
    def resolve(self, name: str) -> list[str]:
        try:
            infos = socket.getaddrinfo(name, None)
        except OSError:
            return []
        return list(dict.fromkeys(i[4][0] for i in infos))

    def probe(self, server_ip: str, qname: str, rtype: str = "SOA", timeout: float = 2.0) -> dict:
        """Eine Frage direkt an einen Server: {ok, rcode, answers[str], serial, ms, error, aa}."""
        dns = _dns()
        if dns is None:
            return {"ok": False, "error": "dnspython"}
        t0 = time.monotonic()
        try:
            q = dns.message.make_query(qname, rtype)
            r = dns.query.udp(q, server_ip, timeout=timeout)
            if r.flags & 0x0200:      # abgeschnitten -> TCP
                r = dns.query.tcp(q, server_ip, timeout=timeout)
        except Exception as e:  # noqa: BLE001 - Zeitüberschreitung, nicht erreichbar …
            return {"ok": False, "error": type(e).__name__, "ms": int((time.monotonic() - t0) * 1000)}
        ms = int((time.monotonic() - t0) * 1000)
        answers, serial = [], None
        for rrset in r.answer:
            for rd in rrset:
                answers.append(rd.to_text())
                if rtype == "SOA" and hasattr(rd, "serial"):
                    serial = int(rd.serial)
        return {"ok": True, "rcode": dns.rcode.to_text(r.rcode()), "answers": answers, "serial": serial, "ms": ms,
                "aa": bool(r.flags & 0x0400)}

    def srv_lookup(self, name: str, timeout: float = 3.0) -> list[str]:
        """SRV-Ziele (z. B. _ldap._tcp.dc._msdcs.<domäne>) über den System-Resolver."""
        dns = _dns()
        if dns is None:
            return []
        try:
            ans = dns.resolver.resolve(name, "SRV", lifetime=timeout)
        except Exception:  # noqa: BLE001
            return []
        return sorted({du.norm(str(r.target)) for r in ans})
