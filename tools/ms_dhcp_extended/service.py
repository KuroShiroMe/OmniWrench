"""DHCP-Zugriffe von MS DHCP Extended Management: Laden, Ändern, Failover, Replikation, Abgleich und Server-Scan.

Alle Methoden blockieren und laufen in Hintergrund-Threads der Oberfläche. Die eigentlichen Zugriffe
erledigt backend.py direkt aus Python (DHCP-API per RPC + netsh dhcp, kein PowerShell); hier liegt die Logik:

* Verbundener Server und Failover-Partner: DHCP Server Management API (dhcpsapi.dll), wie die DHCP-Konsole.
  Die Abfragen heißen intern weiter wie die DhcpServer-Cmdlets (dhcpapi.CMDLETS).
* Partner, der nur per netsh erreichbar ist: Failover-API + netsh dhcp - ohne Double Hop.
* Replikation: Scope lokal lesen, Partner per netsh dump lesen, Abweichungen per netsh angleichen.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Callable

from . import checks as ck
from . import dhcpapi as api
from . import ipcalc as ip
from . import netshdump as nd
from . import optcodec as oc
from .backend import HostError

FLAG_MCLT, FLAG_SAFE, FLAG_PCT, FLAG_MODE, FLAG_SECRET = 0x1, 0x2, 0x8, 0x10, 0x40
SAFE_OFF = 4294967295
FO_STATES = ["NO_STATE", "INIT", "STARTUP", "NORMAL", "COMMUNICATION_INT", "PARTNER_DOWN", "POTENTIAL_CONFLICT",
             "CONFLICT_DONE", "RESOLUTION_INT", "RECOVER", "RECOVER_WAIT", "RECOVER_DONE", "PAUSED", "SHUTDOWN"]
_RPC_CODES = (5, 53, 87, 1326, 1722, 1753, 0x4E25, 0x4E98, 0x4E9D, 0x4EA0, 0x4EA5)
_UNREACHABLE = re.compile(r"nicht erreichbar|unreachable|Zugriff|Access|WinRM|RPC|netsh dhcp|denied|verweigert", re.IGNORECASE)


class UserError(Exception):
    """Fehler mit fertigem, übersetztem Text für die Oberfläche."""


def ts(seconds) -> dict:
    """Zeitspanne für den Host (wird dort zu [TimeSpan])."""
    return {"__ts": int(seconds)}


# --- Normalisierung der Cmdlet-Ausgaben ------------------------------------------------------------

def _s(v) -> str:
    return "" if v is None else str(v)


def _b(v) -> bool:
    return bool(v) and str(v).lower() not in ("false", "0")


def _i(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def n_scope(r: dict) -> dict:
    lease = r.get("LeaseDuration")
    return {"id": _s(r.get("ScopeId")), "mask": _s(r.get("SubnetMask")), "name": _s(r.get("Name")),
            "desc": _s(r.get("Description")), "state": "Active" if _s(r.get("State")).lower() == "active" else "InActive",
            "start": _s(r.get("StartRange")), "end": _s(r.get("EndRange")),
            "lease": None if lease is None else min(_i(lease), ip.UNLIMITED), "superscope": _s(r.get("SuperscopeName"))}


def n_stats(r: dict) -> dict:
    try:
        pct = float(r.get("PercentageInUse") or 0)
    except (TypeError, ValueError):
        pct = 0.0
    return {"id": _s(r.get("ScopeId")), "in_use": _i(r.get("InUse")), "free": _i(r.get("Free")),
            "reserved": _i(r.get("Reserved")), "pct": pct}


def n_excl(r: dict) -> dict:
    return {"scope": _s(r.get("ScopeId")), "start": _s(r.get("StartRange")), "end": _s(r.get("EndRange"))}


def n_opt(r: dict) -> dict:
    vals = r.get("Value")
    if vals is None:
        vals = []
    elif not isinstance(vals, list):
        vals = [vals]
    return {"id": _i(r.get("OptionId")), "name": _s(r.get("Name")), "values": [_s(v) for v in vals],
            "vendor": _s(r.get("VendorClass")), "user": _s(r.get("UserClass"))}


def n_res(r: dict) -> dict:
    cid = _s(r.get("ClientId"))
    return {"ip": _s(r.get("IPAddress")), "cid": ip.format_client_id(cid) or cid, "name": _s(r.get("Name")),
            "desc": _s(r.get("Description")), "type": _s(r.get("Type")) or "Dhcp"}


def n_lease(r: dict) -> dict:
    cid = _s(r.get("ClientId"))
    return {"ip": _s(r.get("IPAddress")), "cid": ip.format_client_id(cid) or cid, "host": _s(r.get("HostName")),
            "state": _s(r.get("AddressState")), "expires": _s(r.get("LeaseExpiryTime")).replace("T", " ")}


def n_def(r: dict) -> dict:
    dv = r.get("DefaultValue")
    if dv is None:
        dv = []
    elif not isinstance(dv, list):
        dv = [dv]
    return {"id": _i(r.get("OptionId")), "name": _s(r.get("Name")), "type": _s(r.get("Type")),
            "multi": _b(r.get("MultiValued")), "vendor": _s(r.get("VendorClass")), "desc": _s(r.get("Description")),
            "default": [_s(v) for v in dv]}


def n_fo(r: dict) -> dict:
    sc = r.get("ScopeId") or []
    if not isinstance(sc, list):
        sc = [sc]
    return {"name": _s(r.get("Name")), "partner": _s(r.get("PartnerServer")), "mode": _s(r.get("Mode")),
            "role": _s(r.get("ServerRole")), "lb": r.get("LoadBalancePercent"), "reserve": r.get("ReservePercent"),
            "mclt": _i(r.get("MaxClientLeadTime")), "auto": _b(r.get("AutoStateTransition")),
            "interval": _i(r.get("StateSwitchInterval")), "state": _s(r.get("State")),
            "scopes": sorted((_s(x) for x in sc if x), key=ip.ip_sort_key), "auth": _b(r.get("EnableAuth"))}


def n_dns(r: dict) -> dict:
    return {"dyn": _s(r.get("DynamicUpdates")), "delete_on_expiry": _b(r.get("DeleteDnsRROnLeaseExpiry")),
            "older": _b(r.get("UpdateDnsRRForOlderClients")), "disable_ptr": _b(r.get("DisableDnsPtrRRUpdate")),
            "name_protection": _b(r.get("NameProtection"))}


def n_class(r: dict) -> dict:
    return {"name": _s(r.get("Name")), "desc": _s(r.get("Description")), "type": _s(r.get("Type")),
            "data": _s(r.get("Data"))}


def opt_label(o: dict) -> str:
    v = f" [{o['vendor']}]" if o.get("vendor") else ""
    u = f" <{o['user']}>" if o.get("user") else ""
    return f"{int(o['id']):03d}{v}{u}"


# ---------------------------------------------------------------------------------------------------

class DhcpService:
    def __init__(self, backend, tr: Callable, log: Callable[[str, bool], None] | None = None,
                 progress: Callable[[str, int, int], None] | None = None):
        self.backend = backend
        self.tr = tr
        self._log = log or (lambda text, error=False: None)
        self._progress = progress or (lambda text, i=0, n=0: None)
        self.cancel = threading.Event()
        self.reset()

    def reset(self) -> None:
        self.server: str | None = None
        self.user = ""
        self.protocol = ""
        self.partner_mode = "Lazy"          # Auto = beim Anmelden verbunden, Lazy = bei Bedarf, Off = nur Primärserver
        self.partner_via: dict[str, str] = {}   # Partner -> "Cim" | "Rpc"
        self.partner_fail: dict[str, str] = {}
        self.partner_user: dict[str, str] = {}
        self.netsh_ok: set[str] = set()
        self.netsh_fail: dict[str, str] = {}
        self.dump_cache: dict[str, tuple[float, dict]] = {}
        self.scopes: list[dict] = []
        self.scope_info: dict[str, dict] = {}
        self.defs: dict[tuple[str, int], dict] = {}
        self.server_options: dict[int, list[str]] = {}
        self.server_option_rows: list[dict] = []
        self.failovers: list[dict] = []
        self.scope_fo: dict[str, dict] = {}
        self.secrets: dict[str, tuple[str, str]] = {}   # nur im Speicher: "*" = Primärserver, sonst Partner (für die Prüfung)
        self.prefetch: dict[str, object] | None = None   # Ergebnisse von cim_many (schnelle Prüfung)
        self.rights: dict[str, str] = {}     # "*" = Primärserver, sonst Partner -> admin | read | unknown
        self.peer: dict[str, dict] = {}      # Sicht der Partner: Failover-Beziehungen, Scopes, Server-Optionen

    def log(self, text: str, error: bool = False) -> None:
        self._log(text, error)

    def progress(self, text: str, i: int = 0, n: int = 0) -> None:
        self._progress(text, i, n)

    # --- Host ---------------------------------------------------------------------------------------
    def host_text(self, msg: str) -> str:
        tr = self.tr
        m = re.match(r"^@RPC:(\w+):([^:]*):(\d+):(.*)$", msg, re.S)
        if m:
            what, server, code, systext = m.group(1), m.group(2), int(m.group(3)), m.group(4).strip()
            if code in _RPC_CODES:
                text = tr(f"rpc.code.{code}")
            elif 0x4E90 <= code <= 0x4EAF:
                text = tr("rpc.code.fo_conflict")
            else:
                text = systext
            if what in ("start", "start_logon", "logon"):
                return tr(f"rpc.{what}", text=text)
            return tr("rpc.fail", what=tr(f"rpc.op.{what}"), server=server, text=text, code=f"0x{code:X}")
        m = re.match(r"^@ERR:(\w+):(.*)$", msg, re.S)
        if m:
            parts = m.group(2).split("|")
            key = m.group(1)
            if key == "netsh_timeout":
                return tr("err.netsh_timeout", server=parts[0], sec=parts[1] if len(parts) > 1 else "?")
            return tr(f"err.{key}", value=parts[0])
        return msg

    def call(self, cmd: str, args: dict | None = None, on_progress=None):
        try:
            return self.backend.call(cmd, args or {}, on_progress)
        except HostError as e:
            raise UserError(self.host_text(str(e))) from None

    def _key(self, name: str, server: str | None, params: dict) -> str:
        return json.dumps([name, (server or self.server or "").lower(), params], sort_keys=True, default=str)

    def cim(self, name: str, server: str | None = None, **params) -> list[dict]:
        p = {k: v for k, v in params.items() if v is not None}
        if self.prefetch is not None:
            hit = self.prefetch.get(self._key(name, server, p))
            if isinstance(hit, UserError):
                raise hit
            if hit is not None:
                return list(hit)
        data = self.call("cim", {"server": server or self.server, "name": name, "params": p})
        return list((data or {}).get("items") or [])

    def cim_many(self, calls: list[tuple[str, str | None, dict]], threads: int = 8, on_result=None) -> dict[str, object]:
        """Viele Get-Cmdlets parallel (RunspacePool im Host). Ergebnis: Schlüssel -> Liste bzw. UserError."""
        out: dict[str, object] = {}
        req = []
        for name, server, params in calls:
            p = {k: v for k, v in params.items() if v is not None}
            req.append({"key": self._key(name, server, p), "name": name, "server": server or self.server, "params": p})

        def prog(msg):
            k = msg.get("key")
            if k is None:
                return
            v = UserError(self.host_text(str(msg["error"]))) if "error" in msg else list(msg.get("items") or [])
            out[k] = v
            if on_result:
                on_result(k, v)
        if req:
            self.call("cim_many", {"calls": req, "threads": threads}, prog)
        return out

    def hello(self) -> dict:
        return self.call("hello")

    def _conn_steps(self, server: str, partner: bool):
        """Fortschritt des Verbindungsaufbaus als ruhige Protokollzeilen (RPC, beim Partner ggf. weiter mit netsh)."""
        def on_step(msg):
            proto = str(msg.get("proto", ""))
            if msg.get("step") == "try":
                self.log(self.tr("log.conn_try", server=server, proto=proto))
            elif msg.get("step") == "fail" and partner:
                self.log(self.tr("log.conn_next", proto=proto, next="netsh"))
        return on_step

    # --- Verbindung ---------------------------------------------------------------------------------
    def connect(self, server: str, user: str = "", password: str = "") -> str:
        self.reset()
        data = self.call("connect", {"server": server, "user": user, "password": password, "primary": True},
                         self._conn_steps(server, False))
        self.server = server
        self.user = user
        self.secrets = {"*": (user, password)} if user else {}
        self.protocol = (data or {}).get("protocol", "")
        self.log(self.tr("log.connected", server=server, user=user or self.tr("ui.sso"), proto=self.protocol))
        self.check_access()
        return self.protocol

    # --- Rechte -------------------------------------------------------------------------------------
    def is_local(self, server: str | None) -> bool:
        return not server or server.lower() == (self.server or "").lower()

    def check_access(self, server: str | None = None) -> str:
        """Schreibrecht ermitteln (DHCP-Administratoren/Administratoren = admin, DHCP-Benutzer = read)."""
        key = "*" if self.is_local(server) else server
        try:
            r = str(self.call("access", {"server": server or self.server}))
        except UserError:
            r = "unknown"
        if r not in ("admin", "read"):
            r = "unknown"
        self.rights[key] = r
        if r == "read":
            self.log(self.tr("log.read_only", server=server or self.server), True)
        return r

    def can_write(self, server: str | None = None) -> bool:
        """Unbekannt zählt als erlaubt - dann lehnt notfalls der Server ab."""
        key = "*" if self.is_local(server) else server
        return self.rights.get(key, "unknown") != "read"

    def disconnect(self) -> None:
        if self.server:
            try:
                self.call("disconnect")
            except UserError:
                pass
            self.log(self.tr("log.disconnected", server=self.server))
        self.reset()

    def dhcp_in_dc(self) -> list[dict]:
        return list((self.call("dhcp_in_dc") or {}).get("items") or [])

    def resolve(self, name: str) -> str:
        return str(self.call("resolve", {"name": name}))

    # --- Partner ------------------------------------------------------------------------------------
    def partners(self) -> list[str]:
        return sorted({r["partner"] for r in self.failovers if r.get("partner")})

    def connect_partner(self, pn: str, user: str | None = None, password: str = "") -> str:
        """Meldet am Partner an: 1. CIM direkt, 2. RPC. Liefert "Cim"/"Rpc", sonst UserError mit beiden Fehlern."""
        args = {"server": pn, "reuse": True} if user is None else {"server": pn, "user": user, "password": password}
        if user:
            self.partner_user[pn] = user
            self.secrets[pn] = (user, password)
        else:
            self.partner_user.pop(pn, None)
            self.secrets.pop(pn, None)
        self.dump_cache = {k: v for k, v in self.dump_cache.items() if not k.startswith(pn + "|")}
        try:
            data = self.call("connect", args, self._conn_steps(pn, True))
            self.partner_via[pn] = "Cim"
            self.partner_fail.pop(pn, None)
            self.log(self.tr("log.partner_connected", partner=pn, proto=(data or {}).get("protocol", ""),
                             user=user or self.user or self.tr("ui.sso")))
            self.check_access(pn)
            try:
                self.test_netsh(pn)
            except UserError as e:
                self.log(self.tr("log.hint", text=str(e)), True)
            return "Cim"
        except UserError as e:
            wsman = str(e)
            self.partner_fail[pn] = self.tr("err.partner_winrm", partner=pn)
            self.partner_via.pop(pn, None)
            self.netsh_fail.pop(pn, None)
            self.netsh_ok.discard(pn)
            self.progress(self.tr("status.partner_rpc", partner=pn))
            if self.enable_rpc_partner(pn):
                return "Rpc"
            raise UserError(self.tr("err.partner_both", winrm=wsman, rpc=self.netsh_fail.get(pn, ""))) from None

    def enable_rpc_partner(self, pn: str) -> bool:
        if pn in self.netsh_fail:
            return False
        try:
            self.fo_api(pn, "enum")
            self.test_netsh(pn)
            self.partner_via[pn] = "Rpc"
            self.log(self.tr("log.conn_rpc_ok", server=pn))
            self.check_access(pn)
            return True
        except UserError as e:
            self.netsh_fail[pn] = str(e)
            self.log(self.tr("log.partner_rpc_failed", partner=pn, error=str(e)), True)
            return False

    def partner_state(self, pn: str) -> str:
        tr = self.tr
        who = f" ({self.partner_user[pn]})" if pn in self.partner_user else ""
        if self.partner_mode == "Off":
            return tr("conn.partner_off")
        ro = (" · " + tr("conn.read_only")) if self.rights.get(pn) == "read" else ""
        if self.partner_via.get(pn) == "Cim":
            return tr("conn.partner_cim") + who + ro
        if self.partner_via.get(pn) == "Rpc":
            return tr("conn.partner_rpc") + who + ro
        if pn in self.partner_fail:
            return tr("conn.partner_unreachable")
        return tr("conn.partner_lazy")

    def _ensure_partner(self, pn: str) -> str:
        if self.partner_mode == "Off":
            raise UserError(self.tr("err.partner_off", partner=pn, server=self.server))
        via = self.partner_via.get(pn)
        if via:
            return via
        if pn not in self.partner_fail:
            try:
                self.call("connect", {"server": pn, "reuse": True}, self._conn_steps(pn, True))
                self.partner_via[pn] = "Cim"
                self.log(self.tr("log.partner_connected", partner=pn, proto="", user=self.user or self.tr("ui.sso")))
                self.check_access(pn)
                return "Cim"
            except UserError as e:
                last = [x for x in str(e).splitlines() if x.strip()]
                self.partner_fail[pn] = self.tr("err.partner_winrm_detail", partner=pn, error=last[-1].strip() if last else "")
        if self.enable_rpc_partner(pn):
            return "Rpc"
        m = self.partner_fail.get(pn, "")
        if pn in self.netsh_fail:
            m += "\n" + self.tr("err.via_rpc", error=self.netsh_fail[pn])
        raise UserError(m.strip())

    def partner(self, pn: str, kind: str, **kw):
        """Einheitlicher, normalisierter Partnerzugriff (CIM oder netsh)."""
        via = self._ensure_partner(pn)
        if via == "Rpc":
            return self._partner_netsh(pn, kind, **kw)
        return self._partner_cim(pn, kind, **kw)

    def _partner_cim(self, pn: str, kind: str, scope: str | None = None, **kw):
        if kind == "version":
            self.cim("Get-DhcpServerVersion", pn)
            return True
        if kind == "scope":
            try:
                r = self.cim("Get-DhcpServerv4Scope", pn, ScopeId=scope)
            except UserError as e:
                if _UNREACHABLE.search(str(e)):
                    raise
                return None
            return n_scope(r[0]) if r else None
        if kind == "exclusions":
            return [n_excl(x) for x in self.cim("Get-DhcpServerv4ExclusionRange", pn, ScopeId=scope)]
        if kind == "reservations":
            return [n_res(x) for x in self.cim("Get-DhcpServerv4Reservation", pn, ScopeId=scope)]
        if kind == "options":
            return self.options(scope, pn)
        if kind == "scopes":
            return [n_scope(x) for x in self.cim("Get-DhcpServerv4Scope", pn)]
        if kind == "opt_remove":
            self.opt_remove(scope, kw["id"], kw.get("vendor", ""), kw.get("user", ""), pn)
            return True
        if kind == "defs":
            return self.list_defs(pn)
        if kind == "def_add":
            self.def_add(kw["d"], pn)
            return True
        if kind == "opt_set":
            self.opt_set(scope, kw["id"], kw["values"], kw.get("vendor", ""), kw.get("user", ""), pn)
            return True
        raise UserError(kind)

    def _partner_netsh(self, pn: str, kind: str, scope: str | None = None, **kw):
        if kind == "version":
            self.test_netsh(pn)
            return True
        if kind in ("scope", "exclusions", "reservations") or (kind == "options" and scope):
            d = self.netsh_parsed(pn, scope or "")
            s = d["scopes"].get(scope)
            if kind == "scope":
                return s if s and s.get("mask") else None
            if not s:
                return []
            return s[kind]
        if kind == "options":
            return self.netsh_parsed(pn, "")["options"]
        if kind == "scopes":
            return [dict(x) for x in self.netsh_parsed(pn, "")["scopes"].values() if x.get("mask")]
        if kind == "opt_remove":
            cmd = f"delete optionvalue {int(kw['id'])}{nd.class_args(kw.get('vendor', ''), kw.get('user', ''))}"
            self.netsh_write(pn, f"scope {scope} {cmd}" if scope else cmd)
            return True
        if kind == "defs":
            return self.netsh_parsed(pn, "")["defs"]
        if kind == "def_add":
            self.netsh_write(pn, nd.add_def_cmd(kw["d"]))
            return True
        if kind == "opt_set":
            cmd = nd.set_option_cmd(kw["id"], kw.get("vendor", ""), kw.get("user", ""), kw["values"],
                                    self.opt_def(kw["id"], kw.get("vendor", "")))
            self.netsh_write(pn, f"scope {scope} {cmd}" if scope else cmd)
            return True
        raise UserError(kind)

    # --- netsh --------------------------------------------------------------------------------------
    def netsh(self, server: str, lines: list[str], timeout: int = 0, on_result=None) -> list[dict]:
        def prog(msg):
            if on_result and isinstance(msg.get("result"), dict):
                on_result(int(msg.get("i", 0)), msg["result"])
        data = self.call("netsh", {"server": server, "lines": lines, "timeout": timeout}, prog if on_result else None)
        return list((data or {}).get("items") or [])

    def test_netsh(self, pn: str) -> None:
        if pn in self.netsh_ok:
            return
        r = (self.netsh(pn, ["show version"], 60) or [{}])[0]
        txt = "\n".join(r.get("out") or []).strip()
        if re.search(r"nicht gefunden|not found", txt, re.IGNORECASE) and "dhcp" in txt.lower():
            raise UserError(self.tr("err.no_netsh", text=txt))
        if int(r.get("code", -1)) != 0 or not re.search(r"\d+\.\d+", txt):
            raise UserError(self.tr("err.netsh_access", partner=pn, text=txt or "–"))
        self.netsh_ok.add(pn)

    def clear_dump(self, pn: str) -> None:
        self.dump_cache = {k: v for k, v in self.dump_cache.items() if not k.startswith(pn + "|")}

    def netsh_parsed(self, pn: str, scope_id: str = "") -> dict:
        key = f"{pn}|{scope_id}"
        c = self.dump_cache.get(key)
        if c and time.time() - c[0] < 30:
            return c[1]
        if scope_id:
            r = (self.netsh(pn, [f"scope {scope_id} dump"], 300) or [{}])[0]
            lines = list(r.get("out") or [])
            if not nd.has_dump_lines(lines):
                full = self.netsh_parsed(pn, "")
                data = {"scopes": {}, "options": full["options"], "defs": full["defs"], "classes": full["classes"],
                        "lines": full["lines"]}
                if scope_id in full["scopes"]:
                    data["scopes"][scope_id] = full["scopes"][scope_id]
                self.dump_cache[key] = (time.time(), data)
                return data
        else:
            r = (self.netsh(pn, ["dump"], 900) or [{}])[0]
            lines = list(r.get("out") or [])
            if not nd.has_dump_lines(lines):
                raise UserError(self.tr("err.dump_failed", partner=pn, text=" ".join(lines).strip() or "–"))
        data = nd.parse_dump(lines)
        data["lines"] = lines
        self.dump_cache[key] = (time.time(), data)
        return data

    def netsh_write(self, pn: str, cmd: str) -> None:
        r = (self.netsh(pn, [cmd]) or [{}])[0]
        self.clear_dump(pn)
        if not nd.is_ok(r):
            raise UserError(self.tr("err.netsh_says", partner=pn, text=nd.format_out(r)))

    # --- Laden --------------------------------------------------------------------------------------
    def opt_def(self, opt_id: int, vendor: str = "") -> dict | None:
        return self.defs.get((vendor or "", int(opt_id)))

    def list_defs(self, server: str | None = None) -> list[dict]:
        try:
            raw = self.cim("Get-DhcpServerv4OptionDefinition", server, All=True)
        except UserError:
            raw = self.cim("Get-DhcpServerv4OptionDefinition", server)
        return [n_def(x) for x in raw]

    def load_defs(self) -> None:
        try:
            self.defs = {(d["vendor"], d["id"]): d for d in self.list_defs()}
        except UserError as e:
            self.defs = {}
            self.log(self.tr("log.defs_failed", error=str(e)), True)

    def options(self, scope_id: str | None = None, server: str | None = None) -> list[dict]:
        p = {"ScopeId": scope_id} if scope_id else {}
        try:
            raw = self.cim("Get-DhcpServerv4OptionValue", server, All=True, **p)
        except UserError:
            raw = self.cim("Get-DhcpServerv4OptionValue", server, **p)
        return [n_opt(x) for x in raw]

    def load_server_options(self) -> list[dict]:
        try:
            opts = self.options()
        except UserError:
            opts = []
        self.server_options = {o["id"]: o["values"] for o in opts if not o["vendor"] and not o["user"]}
        self.server_option_rows = sorted(opts, key=lambda o: (o["vendor"], o["user"], o["id"]))
        return self.server_option_rows

    def load_failovers(self) -> None:
        self.failovers, self.scope_fo = [], {}
        try:
            self.failovers = sorted((n_fo(x) for x in self.cim("Get-DhcpServerv4Failover")), key=lambda r: r["name"].lower())
        except UserError as e:
            self.log(self.tr("log.fo_failed", error=str(e)), True)
        for r in self.failovers:
            for sid in r["scopes"]:
                self.scope_fo[sid] = r

    def load_overview(self) -> list[dict]:
        scopes = sorted((n_scope(x) for x in self.cim("Get-DhcpServerv4Scope")), key=lambda s: ip.ip_sort_key(s["id"]))
        stats: dict[str, dict] = {}
        try:
            for x in self.cim("Get-DhcpServerv4ScopeStatistics"):
                st = n_stats(x)
                stats[st["id"]] = st
        except UserError:
            pass
        excl = self.exclusions_by_scope(scopes)
        self.scopes = scopes
        self.scope_info = {}
        for s in scopes:
            rng = self.ranges_of(s, excl.get(s["id"], []))
            self.scope_info[s["id"]] = {"scope": s, "stat": stats.get(s["id"]), "exclusions": excl.get(s["id"], []),
                                        "ranges": rng, "usable": ip.range_size(rng)}
        return scopes

    def exclusions_by_scope(self, scopes: list[dict]) -> dict[str, list[tuple[int, int]]]:
        out: dict[str, list[tuple[int, int]]] = {}
        try:
            for x in self.cim("Get-DhcpServerv4ExclusionRange"):
                e = n_excl(x)
                if ip.is_ipv4(e["start"]) and ip.is_ipv4(e["end"]):
                    out.setdefault(e["scope"], []).append((ip.ip2int(e["start"]), ip.ip2int(e["end"])))
        except UserError:
            for s in scopes:
                try:
                    out[s["id"]] = [(ip.ip2int(e["start"]), ip.ip2int(e["end"]))
                                    for e in map(n_excl, self.cim("Get-DhcpServerv4ExclusionRange", ScopeId=s["id"]))]
                except UserError:
                    out[s["id"]] = []
        return out

    @staticmethod
    def ranges_of(s: dict, excl: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not (ip.is_ipv4(s.get("start")) and ip.is_ipv4(s.get("end"))):
            return []
        return ip.effective_ranges(ip.ip2int(s["start"]), ip.ip2int(s["end"]), excl)

    def load_all(self) -> None:
        self.load_defs()
        self.load_server_options()
        self.load_failovers()
        self.load_overview()

    def get_scope(self, sid: str, leases: bool = True) -> dict:
        s = self.cim("Get-DhcpServerv4Scope", ScopeId=sid)
        if not s:
            raise UserError(self.tr("err.scope_missing", id=sid))
        out = {"scope": n_scope(s[0]), "stat": None, "dns": None, "leases": []}
        try:
            st = self.cim("Get-DhcpServerv4ScopeStatistics", ScopeId=sid)
            out["stat"] = n_stats(st[0]) if st else None
        except UserError:
            pass
        out["exclusions"] = [n_excl(x) for x in self.cim("Get-DhcpServerv4ExclusionRange", ScopeId=sid)]
        out["options"] = self.options(sid)
        out["reservations"] = [n_res(x) for x in self.cim("Get-DhcpServerv4Reservation", ScopeId=sid)]
        if leases:
            try:
                out["leases"] = [n_lease(x) for x in self.cim("Get-DhcpServerv4Lease", ScopeId=sid)]
            except UserError as e:
                self.log(self.tr("log.leases_failed", id=sid, error=str(e)), True)
        try:
            d = self.cim("Get-DhcpServerv4DnsSetting", ScopeId=sid)
            out["dns"] = n_dns(d[0]) if d else None
        except UserError:
            pass
        info = self.scope_info.get(sid)
        if info is not None:
            ex = [(ip.ip2int(x["start"]), ip.ip2int(x["end"])) for x in out["exclusions"]]
            rng = self.ranges_of(out["scope"], ex)
            info.update({"scope": out["scope"], "exclusions": ex, "ranges": rng, "usable": ip.range_size(rng)})
            if out["stat"]:
                info["stat"] = out["stat"]
        return out

    def classes(self, server: str | None = None) -> list[dict]:
        return [n_class(x) for x in self.cim("Get-DhcpServerv4Class", server)]

    # --- Ändern -------------------------------------------------------------------------------------
    def scope_set(self, sid: str, **params) -> None:
        if "LeaseDuration" in params and params["LeaseDuration"] is not None:
            params["LeaseDuration"] = ts(params["LeaseDuration"])
        self.cim("Set-DhcpServerv4Scope", ScopeId=sid, **params)

    def scope_add(self, start: str, end: str, mask: str, name: str, desc: str, lease: int, active: bool) -> None:
        self.cim("Add-DhcpServerv4Scope", StartRange=start, EndRange=end, SubnetMask=mask, Name=name,
                 Description=desc or None, LeaseDuration=ts(lease), State="Active" if active else "InActive")

    def scope_remove(self, sid: str) -> None:
        self.cim("Remove-DhcpServerv4Scope", ScopeId=sid, Force=True)

    def excl_add(self, sid: str, start: str, end: str) -> None:
        self.cim("Add-DhcpServerv4ExclusionRange", ScopeId=sid, StartRange=start, EndRange=end)

    def excl_remove(self, sid: str, start: str, end: str) -> None:
        self.cim("Remove-DhcpServerv4ExclusionRange", ScopeId=sid, StartRange=start, EndRange=end)

    def opt_set(self, sid: str | None, opt_id: int, values: list[str], vendor: str = "", user: str = "",
                server: str | None = None) -> None:
        self.cim("Set-DhcpServerv4OptionValue", server, ScopeId=sid or None, OptionId=int(opt_id),
                 Value=[str(v) for v in values], VendorClass=vendor or None, UserClass=user or None, Force=True)

    def opt_remove(self, sid: str | None, opt_id: int, vendor: str = "", user: str = "", server: str | None = None) -> None:
        self.cim("Remove-DhcpServerv4OptionValue", server, ScopeId=sid or None, OptionId=int(opt_id), VendorClass=vendor or None,
                 UserClass=user or None)

    # --- Server-Optionen auf einem beliebigen Server der Failover-Gruppe ----------------------------------
    def srv_options(self, server: str | None) -> list[dict]:
        if self.is_local(server):
            return self.load_server_options()
        return sorted(self.partner(server, "options"), key=lambda o: (o.get("vendor") or "", o.get("user") or "", int(o["id"])))

    def srv_opt_set(self, server: str | None, opt_id: int, values: list[str], vendor: str = "", user: str = "") -> None:
        if self.is_local(server):
            self.opt_set(None, opt_id, values, vendor, user)
        else:
            self.partner(server, "opt_set", scope=None, id=int(opt_id), values=list(values), vendor=vendor, user=user)

    def srv_opt_remove(self, server: str | None, opt_id: int, vendor: str = "", user: str = "") -> None:
        if self.is_local(server):
            self.opt_remove(None, opt_id, vendor, user)
        else:
            self.partner(server, "opt_remove", scope=None, id=int(opt_id), vendor=vendor, user=user)

    def load_peer(self, pn: str) -> dict:
        """Sicht eines Partners: seine Failover-Beziehungen (auch zu dritten Servern), Scopes und Server-Optionen."""
        d: dict = {"fo": None, "scopes": None, "options": None, "errors": {}, "time": time.strftime("%H:%M:%S")}
        self.peer[pn] = d
        try:
            self._ensure_partner(pn)
        except UserError as e:
            d["errors"]["conn"] = str(e)
            return d
        try:
            d["fo"] = sorted((n_fo(api.fo_cmdlet_row(r)) for r in self.fo_api(pn, "enum")), key=lambda r: r["name"].lower())
        except UserError as e:
            d["errors"]["fo"] = str(e)
        try:
            d["scopes"] = sorted(self.partner(pn, "scopes"), key=lambda x: ip.ip_sort_key(x["id"]))
        except UserError as e:
            d["errors"]["scopes"] = str(e)
        try:
            d["options"] = self.srv_options(pn)
        except UserError as e:
            d["errors"]["options"] = str(e)
        return d

    def res_add(self, sid: str, r: dict) -> None:
        self.cim("Add-DhcpServerv4Reservation", ScopeId=sid, IPAddress=r["ip"], ClientId=r["cid"], Name=r.get("name") or None,
                 Description=r.get("desc") or None, Type=r.get("type") or "Dhcp")

    def res_set(self, r: dict) -> None:
        self.cim("Set-DhcpServerv4Reservation", IPAddress=r["ip"], ClientId=r["cid"], Name=r.get("name") or "",
                 Description=r.get("desc") or "", Type=r.get("type") or "Dhcp")

    def res_remove(self, sid: str, rip: str) -> None:
        self.cim("Remove-DhcpServerv4Reservation", ScopeId=sid, IPAddress=rip)

    def lease_remove(self, rip: str) -> None:
        self.cim("Remove-DhcpServerv4Lease", IPAddress=rip)

    def dns_set(self, sid: str, d: dict) -> None:
        self.cim("Set-DhcpServerv4DnsSetting", ScopeId=sid, DynamicUpdates=d["dyn"] or "OnClientRequest",
                 DeleteDnsRROnLeaseExpiry=bool(d["delete_on_expiry"]), UpdateDnsRRForOlderClients=bool(d["older"]),
                 DisableDnsPtrRRUpdate=bool(d["disable_ptr"]), NameProtection=bool(d["name_protection"]))

    def def_add(self, d: dict, server: str | None = None) -> None:
        dv = [str(x) for x in d.get("default") or [] if str(x)]
        self.cim("Add-DhcpServerv4OptionDefinition", server, OptionId=int(d["id"]), Name=d["name"], Type=d["type"],
                 MultiValued=bool(d.get("multi")), VendorClass=d.get("vendor") or None, Description=d.get("desc") or None,
                 DefaultValue=dv or None)

    def def_set(self, d: dict) -> None:
        dv = [str(x) for x in d.get("default") or [] if str(x)]
        self.cim("Set-DhcpServerv4OptionDefinition", OptionId=int(d["id"]), Name=d["name"], Description=d.get("desc") or "",
                 VendorClass=d.get("vendor") or None, DefaultValue=dv or None)

    def def_remove(self, opt_id: int, vendor: str = "") -> None:
        self.cim("Remove-DhcpServerv4OptionDefinition", OptionId=int(opt_id), VendorClass=vendor or None)

    # --- Replikation --------------------------------------------------------------------------------
    def local_scope_data(self, sid: str) -> dict:
        s = self.cim("Get-DhcpServerv4Scope", ScopeId=sid)
        if not s:
            raise UserError(self.tr("err.scope_missing", id=sid))
        return {"scope": n_scope(s[0]),
                "exclusions": [n_excl(x) for x in self.cim("Get-DhcpServerv4ExclusionRange", ScopeId=sid)],
                "options": self.options(sid),
                "reservations": [n_res(x) for x in self.cim("Get-DhcpServerv4Reservation", ScopeId=sid)]}

    def sync_classes(self, pn: str, names: list[str]) -> list[str]:
        need = sorted({n for n in names if n})
        if not need:
            return []
        errs = []
        have = {c["name"] for c in self.netsh_parsed(pn, "")["classes"]}
        try:
            local = {c["name"]: c for c in self.classes()}
        except UserError:
            local = {}
        for n in need:
            if n in have:
                continue
            c = local.get(n)
            if not c:
                errs.append(self.tr("err.class_unreadable", name=n, partner=pn))
                continue
            try:
                self.netsh_write(pn, nd.add_class_cmd(c))
                self.log(self.tr("log.class_created", name=n, partner=pn))
            except UserError as e:
                if not re.search(r"bereits|already exists", str(e), re.IGNORECASE):
                    errs.append(self.tr("err.class_failed", name=n, partner=pn, error=str(e)))
        return errs

    def copy_def_to_partner(self, d: dict, pn: str) -> bool:
        self.partner(pn, "version")
        existing = [x for x in self.partner(pn, "defs") if x["id"] == d["id"] and (x.get("vendor") or "") == (d.get("vendor") or "")]
        if existing:
            return False
        self.partner(pn, "def_add", d=d)
        self.log(self.tr("log.def_copied", tag=f"{d['id']:03d}", name=d["name"], partner=pn))
        return True

    def sync_defs_to_partner(self, pn: str, keys: list[tuple[str, int]]) -> list[str]:
        if self.partner_mode == "Off":
            return []
        errs, done = [], set()
        for vendor, oid in keys:
            if not vendor and oid in oc.STD_OPTION_IDS:
                continue        # Standardoptionen sind auf jedem Server definiert
            if (vendor, oid) in done:
                continue
            done.add((vendor, oid))
            d = self.opt_def(oid, vendor)
            if not d:
                continue
            try:
                self.copy_def_to_partner(d, pn)
            except UserError as e:
                errs.append(self.tr("err.def_partner", tag=f"{oid:03d}", partner=pn, error=str(e)))
                if pn in self.partner_fail or _UNREACHABLE.search(str(e)):
                    break
        return errs

    def sync_scope_to_partner(self, sid: str, pn: str) -> dict:
        tr = self.tr
        self.progress(tr("status.repl_local", id=sid))
        local = self.local_scope_data(sid)
        self.log(tr("log.repl_read_partner", id=sid, partner=pn))
        self.progress(tr("status.repl_partner", id=sid, partner=pn))
        self.clear_dump(pn)
        d = self.netsh_parsed(pn, sid)
        rem = d["scopes"].get(sid)
        if rem and not rem.get("mask"):
            rem = None
        if not rem:
            self.log(tr("log.repl_create", id=sid, partner=pn))
        errs: list[str] = []
        self.progress(tr("status.repl_defs", id=sid))
        names = [o.get("vendor") for o in local["options"]] + [o.get("user") for o in local["options"]]
        for e in self.sync_classes(pn, names):
            errs.append(e)
            self.log("  " + e, True)
        for e in self.sync_defs_to_partner(pn, [(o.get("vendor") or "", int(o["id"])) for o in local["options"]]):
            errs.append(e)
            self.log("  " + e, True)
        try:
            cmds = nd.sync_plan(sid, local, rem, self.opt_def)
        except nd.MaskMismatch as e:
            raise UserError(tr("err.mask_mismatch", id=e.scope_id, remote=e.remote, local=e.local)) from None
        if cmds:
            total = len(cmds)
            self.log(tr("log.repl_changes", n=total, partner=pn))
            self.progress(tr("status.repl_step", id=sid, i=0, n=total), 0, total)

            def on_result(i, res):
                ok = nd.is_ok(res)
                self.log(f"  [{i + 1}/{total}] {res.get('cmd')}  →  {nd.format_out(res)}", not ok)
                self.progress(tr("status.repl_step", id=sid, i=i + 1, n=total), i + 1, total)

            for res in self.netsh(pn, cmds, on_result=on_result):
                if not nd.is_ok(res):
                    errs.append(f"{res.get('cmd')}  →  {nd.format_out(res)}")
            self.clear_dump(pn)
        else:
            self.log(tr("log.repl_in_sync", id=sid, partner=pn))
        exists = True
        if not rem:
            chk = self.netsh_parsed(pn, sid)["scopes"].get(sid)
            exists = bool(chk and chk.get("mask"))
        return {"id": sid, "created": not rem and exists, "exists": exists, "changes": len(cmds), "errors": errs}

    def remove_partner_scopes(self, pn: str, ids: list[str]) -> list[str]:
        errs = []
        for sid in [x for x in ids if x]:
            try:
                self.netsh_write(pn, f"delete scope {sid} dhcpfullforce")
                self.log(self.tr("log.partner_scope_deleted", id=sid, partner=pn))
            except UserError as e:
                errs.append(self.tr("err.partner_scope_delete", id=sid, partner=pn, error=str(e)))
        return errs

    def replicate(self, ids: list[str]) -> list[str]:
        """Repliziert Scopes auf ihren Partner; liefert die fehlerfreien IDs, UserError bei Fehlern."""
        tr = self.tr
        ok, fail = [], []
        ids = [x for x in ids if x]
        for num, sid in enumerate(ids, 1):
            if len(ids) > 1:
                self.log(tr("log.repl_scope_n", i=num, n=len(ids), id=sid))
            rel = self.scope_fo.get(sid)
            if not rel:
                fail.append(f"{sid}: {tr('err.no_failover')}")
                continue
            pn = rel["partner"]
            self.progress(tr("status.replicating", id=sid, partner=pn))
            try:
                r = self.sync_scope_to_partner(sid, pn)
                self.log(tr("log.repl_done", id=sid, partner=pn, n=r["changes"], errors=len(r["errors"])))
                if r["errors"]:
                    fail += [f"{sid}: {e}" for e in r["errors"]]
                else:
                    ok.append(sid)
            except UserError as e:
                fail.append(f"{sid}: {e}")
        for f in fail:
            self.log(tr("log.repl_error", text=f), True)
        if fail:
            raise ReplicationError(tr("err.repl_incomplete", ok=len(ok), n=len(ids), list=short_list(fail, 10)), ok)
        return ok

    def replicate_relationship(self, name: str) -> list[str]:
        rel = next((r for r in self.failovers if r["name"] == name), None)
        if not rel:
            raise UserError(self.tr("err.fo_missing", name=name))
        ok = self.replicate(list(rel["scopes"]))
        self.log(self.tr("log.repl_rel_done", name=name, n=len(rel["scopes"])))
        return ok

    # --- Failover über die DHCP-API -----------------------------------------------------------------
    def fo_api(self, server: str, op: str, rel: dict | None = None, name: str | None = None, flags: int = 0):
        data = self.call("fo_api", {"server": server, "op": op, "rel": rel, "name": name, "flags": int(flags)})
        if op == "enum":
            return list((data or {}).get("items") or [])
        return data

    def fo_api_rel(self, server: str, name: str) -> dict:
        hit = [r for r in self.fo_api(server, "enum") if r.get("name") == name]
        if not hit:
            raise UserError(self.tr("err.fo_api_missing", name=name, server=server))
        return hit[0]

    def _pair_struct(self, spec: dict, local_primary: bool, lip: str, pip: str, server_type: int) -> dict:
        local = self.server
        r = {"name": spec["name"], "scopes": list(spec.get("scopes") or []), "mode": 1 if spec["mode"] == "HotStandby" else 0,
             "server_type": server_type, "mclt": max(1, int(spec["mclt"])),
             "safe_period": max(1, int(spec["interval"])) if spec.get("auto") else SAFE_OFF}
        if local_primary:
            r.update(primary_name=local, primary_ip=lip, secondary_name=spec["partner"], secondary_ip=pip)
        else:
            r.update(primary_name=spec["partner"], primary_ip=pip, secondary_name=local, secondary_ip=lip)
        # Lastverteilung: Anteil des Primärservers; Hot Standby: Reserve des Standby-Servers
        if spec["mode"] == "HotStandby":
            r["percentage"] = int(spec["reserve"])
        else:
            r["percentage"] = int(spec["lb"]) if local_primary else 100 - int(spec["lb"])
        if spec.get("secret"):
            r["secret"] = spec["secret"]
        return r

    def _add_pair(self, spec: dict, local_primary: bool, lip: str, pip: str) -> None:
        ptype = 1 if local_primary else 0
        self.fo_api(spec["partner"], "create", self._pair_struct(spec, local_primary, lip, pip, ptype))
        try:
            self.fo_api(self.server, "create", self._pair_struct(spec, local_primary, lip, pip, 1 - ptype))
        except UserError as e:
            try:
                self.fo_api(spec["partner"], "delete", name=spec["name"])
            except UserError as e2:
                self.log(self.tr("log.rollback_failed", server=spec["partner"], error=str(e2)), True)
            raise e

    def copy_scopes_to_partner(self, pn: str, ids: list[str]) -> dict:
        created, warn = [], []
        for sid in ids:
            self.progress(self.tr("status.copy_scope", id=sid, partner=pn))
            r = None
            try:
                r = self.sync_scope_to_partner(sid, pn)
            except UserError as e:
                warn.append(f"{sid}: {e}")
            if r and r["created"]:
                created.append(sid)
            if r:
                warn += [f"{sid}: {x}" for x in r["errors"]]
            if not r or not r["exists"]:
                for e in self.remove_partner_scopes(pn, created):
                    self.log(e, True)
                if not any(x.startswith(f"{sid}: ") for x in warn):
                    warn.append(f"{sid}: " + self.tr("err.partner_scope_missing", id=sid, partner=pn))
                raise UserError(self.tr("err.copy_scope_failed", id=sid, partner=pn, list=short_list(warn, 8)))
        return {"created": created, "warnings": warn}

    def new_relationship(self, spec: dict) -> list[str]:
        local, pn = self.server, spec["partner"]
        if not spec.get("scopes"):
            raise UserError(self.tr("err.fo_no_scopes"))
        self.test_netsh(pn)
        lip, pip = self.resolve(local), self.resolve(pn)
        local_primary = spec["mode"] != "HotStandby" or spec.get("role") == "Active"
        copy = self.copy_scopes_to_partner(pn, spec["scopes"])
        try:
            self._add_pair(spec, local_primary, lip, pip)
        except UserError as e:
            for x in self.remove_partner_scopes(pn, copy["created"]):
                self.log(x, True)
            raise UserError(self.tr("err.fo_create_failed", name=spec["name"], error=str(e))) from None
        self.log(self.tr("log.fo_created", name=spec["name"], partner=pn, server=local, scopes=", ".join(spec["scopes"])))
        # Kontrolle über die Sicht des Servers - Prozent- bzw. Rollenzuordnung bei Bedarf korrigieren
        self.load_failovers()
        rel = next((r for r in self.failovers if r["name"] == spec["name"]), None)
        if rel:
            if (spec["mode"] == "LoadBalance" and rel.get("lb") is not None and int(rel["lb"]) != int(spec["lb"])
                    and int(rel["lb"]) == 100 - int(spec["lb"])):
                self.log(self.tr("log.fo_lb_mirrored", got=rel["lb"], want=spec["lb"]), True)
                cur = self.fo_api_rel(local, spec["name"])
                fix = {"name": spec["name"], "percentage": 100 - int(cur.get("percentage") or 0)}
                for srv in (pn, local):
                    self.fo_api(srv, "set", fix, flags=FLAG_PCT)
                self.load_failovers()
            elif spec["mode"] == "HotStandby" and rel.get("role") and rel["role"] != spec.get("role"):
                self.log(self.tr("log.fo_role_swapped", got=rel["role"], want=spec.get("role")), True)
                for srv in (local, pn):
                    try:
                        self.fo_api(srv, "delete", name=spec["name"])
                    except UserError:
                        pass
                self._add_pair(spec, not local_primary, lip, pip)
                self.load_failovers()
        for w in copy["warnings"]:
            self.log(self.tr("log.transfer_warn", text=w), True)
        return copy["warnings"]

    def set_relationship(self, rel: dict, p: dict) -> None:
        """p: mode, lb, role, reserve, mclt, auto, interval, secret (wie spec)."""
        local, pn = self.server, rel["partner"]
        api = self.fo_api_rel(local, rel["name"])
        hs = p["mode"] == "HotStandby"
        s = {"name": rel["name"], "mode": 1 if hs else 0, "mclt": max(1, int(p["mclt"])),
             "safe_period": max(1, int(p["interval"])) if p.get("auto") else SAFE_OFF}
        if hs:
            cur_active = (rel.get("role") == "Active") if rel.get("mode") != "LoadBalance" and rel.get("role") else int(api.get("server_type", 0)) == 0
            if (p.get("role") == "Active") != cur_active:
                raise UserError(self.tr("err.fo_role_swap", role=self.tr("forole.Active" if cur_active else "forole.Standby")))
            s["percentage"] = int(p["reserve"])
        else:
            lb = int(p["lb"])
            inverted = int(api.get("server_type", 0)) != 0
            if rel.get("mode") == "LoadBalance" and rel.get("lb") is not None and int(rel["lb"]) != 50:
                if int(api.get("percentage", -1)) == int(rel["lb"]):
                    inverted = False
                elif int(api.get("percentage", -1)) == 100 - int(rel["lb"]):
                    inverted = True
            s["percentage"] = 100 - lb if inverted else lb
        flags = FLAG_MCLT | FLAG_SAFE | FLAG_PCT | FLAG_MODE
        self.fo_api(pn, "set", s, flags=flags)
        self.fo_api(local, "set", s, flags=flags)
        self.log(self.tr("log.fo_changed", name=rel["name"], partner=pn, server=local))
        if p.get("secret"):
            sec = {"name": rel["name"], "secret": p["secret"]}
            try:
                self.fo_api(pn, "set", sec, flags=FLAG_SECRET)
                self.fo_api(local, "set", sec, flags=FLAG_SECRET)
                self.log(self.tr("log.fo_secret", name=rel["name"]))
            except UserError as e:
                raise UserError(self.tr("err.fo_secret", error=str(e))) from None

    def remove_relationship(self, rel: dict) -> list[str]:
        local, pn = self.server, rel["partner"]
        self.fo_api(pn, "delete", name=rel["name"])
        self.fo_api(local, "delete", name=rel["name"])
        self.log(self.tr("log.fo_deleted", name=rel["name"], partner=pn, server=local))
        return self.remove_partner_scopes(pn, list(rel["scopes"]))

    def add_fo_scopes(self, rel: dict, ids: list[str]) -> list[str]:
        local, pn = self.server, rel["partner"]
        self.test_netsh(pn)
        copy = self.copy_scopes_to_partner(pn, ids)
        s = {"name": rel["name"], "scopes": list(ids)}
        try:
            self.fo_api(pn, "add_scopes", s)
        except UserError:
            for e in self.remove_partner_scopes(pn, copy["created"]):
                self.log(e, True)
            raise
        try:
            self.fo_api(local, "add_scopes", s)
        except UserError:
            try:
                self.fo_api(pn, "remove_scopes", s)
            except UserError as e2:
                self.log(self.tr("log.rollback_failed", server=pn, error=str(e2)), True)
            for e in self.remove_partner_scopes(pn, copy["created"]):
                self.log(e, True)
            raise
        self.log(self.tr("log.fo_scopes_added", name=rel["name"], ids=", ".join(ids)))
        for w in copy["warnings"]:
            self.log(self.tr("log.transfer_warn", text=w), True)
        return copy["warnings"]

    def remove_fo_scopes(self, rel: dict, ids: list[str]) -> list[str]:
        """Entfernt Scopes aus der Beziehung und löscht sie auf dem Partner; alle Scopes = Beziehung löschen."""
        local, pn = self.server, rel["partner"]
        if not [x for x in rel["scopes"] if x not in ids]:
            self.log(self.tr("log.fo_all_removed", name=rel["name"]))
            return self.remove_relationship(rel)
        s = {"name": rel["name"], "scopes": list(ids)}
        self.fo_api(pn, "remove_scopes", s)
        self.fo_api(local, "remove_scopes", s)
        self.log(self.tr("log.fo_scopes_removed", name=rel["name"], ids=", ".join(ids)))
        return self.remove_partner_scopes(pn, ids)

    def fo_raw_text(self, rel: dict) -> str:
        tr = self.tr
        out = [tr("raw.fo_title", name=rel["name"]), ""]
        api = {}
        for srv in (self.server, rel["partner"]):
            out.append(f"=== {srv} ===")
            try:
                a = self.fo_api_rel(srv, rel["name"])
                api[srv] = a
                out.append(self._fmt_api_rel(a))
            except UserError as e:
                out.append("  " + tr("raw.error", error=str(e)))
            out.append("")
        out.append(tr("raw.fo_cmdlet", server=self.server))
        out.append(f"  Mode: {rel.get('mode')}   Role: {rel.get('role')}   LoadBalance: {rel.get('lb')}   Reserve: {rel.get('reserve')}")
        out.append(f"  MCLT: {ck.format_duration(rel.get('mclt'))}   Auto: {rel.get('auto')} ({ck.format_duration(rel.get('interval'))})"
                   f"   State: {rel.get('state')}")
        out.append("")
        loc = api.get(self.server)
        if loc:
            out.append(tr("raw.eval"))
            if rel.get("mode") == "LoadBalance":
                lb = int(rel.get("lb") or 0)
                pct, st = int(loc.get("percentage", -1)), int(loc.get("server_type", -1))
                if pct == lb and st == 0:
                    m = tr("raw.lb_ok_primary")
                elif pct == 100 - lb and st == 1:
                    m = tr("raw.lb_ok_secondary")
                elif lb == 50:
                    m = tr("raw.lb_5050")
                else:
                    m = tr("raw.lb_bad")
                out.append("  " + tr("raw.lb", text=m))
            else:
                act = rel.get("role") == "Active"
                m = tr("raw.hs_ok") if act == (int(loc.get("server_type", -1)) == 0) else tr("raw.hs_bad")
                out.append("  " + tr("raw.hs", text=m))
            p = api.get(rel["partner"])
            if p:
                same = (p.get("primary_ip") == loc.get("primary_ip") and p.get("secondary_ip") == loc.get("secondary_ip")
                        and p.get("server_type") != loc.get("server_type") and p.get("percentage") == loc.get("percentage"))
                out.append("  " + tr("raw.partner_side", text=tr("raw.partner_ok") if same else tr("raw.partner_bad")))
        return "\n".join(out)

    def _fmt_api_rel(self, a: dict) -> str:
        tr = self.tr

        def st(n):
            n = int(n or 0)
            return FO_STATES[n] if 0 <= n < len(FO_STATES) else str(n)
        sp = int(a.get("safe_period") or 0)
        safe = tr("raw.off") if sp in (0, SAFE_OFF) else f"{sp} s"
        mode = int(a.get("mode") or 0)
        stype = int(a.get("server_type") or 0)
        scopes = a.get("scopes") or []
        return "\n".join([
            f"  Name             : {a.get('name')}",
            f"  {tr('raw.primary'):<17}: {a.get('primary_name')} ({a.get('primary_ip')})",
            f"  {tr('raw.secondary'):<17}: {a.get('secondary_name')} ({a.get('secondary_ip')})",
            f"  {tr('raw.mode'):<17}: {mode} ({'LoadBalance' if mode == 0 else 'HotStandby'})",
            f"  ServerType       : {stype} ({tr('raw.is_primary') if stype == 0 else tr('raw.is_secondary')})",
            f"  {tr('raw.state'):<17}: {st(a.get('state'))} / {st(a.get('prev_state'))}",
            f"  MCLT             : {a.get('mclt')} s",
            f"  SafePeriod       : {safe}",
            f"  {tr('raw.percentage'):<17}: {a.get('percentage')}",
            f"  Shared Secret    : {tr('raw.set') if a.get('secret') else '–'}",
            f"  Scopes ({len(scopes)}){' ' * max(1, 10 - len(str(len(scopes))))}: {', '.join(scopes)}",
        ])

    def partner_raw_text(self, sid: str) -> str:
        tr = self.tr
        rel = self.scope_fo.get(sid)
        if not rel:
            raise UserError(tr("err.no_failover"))
        pn = rel["partner"]
        self.dump_cache.pop(f"{pn}|{sid}", None)
        d = self.netsh_parsed(pn, sid)
        out = [tr("raw.partner_title", partner=pn, id=sid), ""] + nd.scope_lines(d.get("lines") or [], sid)
        s = d["scopes"].get(sid)
        if s:
            out += ["", tr("raw.parsed"), f"Name: {s['name']}", f"{tr('raw.mask')}: {s['mask']}",
                    f"{tr('raw.range')}: {s['start']} – {s['end']}", f"{tr('raw.state')}: {s['state']}",
                    f"Lease: {ck.format_lease(s['lease'], tr)}",
                    f"{tr('raw.exclusions')}: {', '.join(x['start'] + '-' + x['end'] for x in s['exclusions'])}",
                    tr("raw.options") + ":"]
            out += [f"  {opt_label(o)} = {', '.join(o['values'])}" for o in s["options"]]
            out.append(f"{tr('raw.reservations')}: {len(s['reservations'])}")
        return "\n".join(out)

    # --- Abgleich -----------------------------------------------------------------------------------
    def compare_scope(self, sid: str, rel: dict) -> list[dict]:
        """Zeilen {el, local, partner, result}: result = same | diff | missing | more."""
        tr = self.tr
        rows: list[dict] = []

        def add(el, a, b):
            a, b = str(a if a is not None else ""), str(b if b is not None else "")
            rows.append({"el": el, "local": a, "partner": b, "result": "same" if a == b else "diff"})
        pn = rel["partner"]
        self.partner(pn, "version")
        ls = n_scope(self.cim("Get-DhcpServerv4Scope", ScopeId=sid)[0])
        rs = self.partner(pn, "scope", scope=sid)
        if not rs:
            rows.append({"el": "Scope", "local": tr("cmp.present"), "partner": tr("cmp.absent"), "result": "missing"})
            return rows
        add(tr("cmp.name"), ls["name"], rs["name"])
        add(tr("cmp.mask"), ls["mask"], rs["mask"])
        add(tr("cmp.range"), f"{ls['start']} – {ls['end']}", f"{rs['start']} – {rs['end']}")
        add(tr("cmp.state"), tr("state." + ls["state"]), tr("state." + rs["state"]))
        add(tr("cmp.lease"), ck.format_lease(ls["lease"], tr), ck.format_lease(rs["lease"], tr))
        add(tr("cmp.desc"), ls["desc"], rs["desc"])

        def excl_text(lst):
            return ", ".join(f"{x['start']}-{x['end']}" for x in sorted(lst, key=lambda x: ip.ip_sort_key(x["start"])))
        add(tr("cmp.exclusions"), excl_text(map(n_excl, self.cim("Get-DhcpServerv4ExclusionRange", ScopeId=sid))),
            excl_text(self.partner(pn, "exclusions", scope=sid)))
        lo = {opt_label(o): oc.compare_form(o["values"], self.opt_def(o["id"], o["vendor"])) for o in self.options(sid)}
        ro = {opt_label(o): oc.compare_form(o["values"], self.opt_def(o["id"], o.get("vendor", "")))
              for o in self.partner(pn, "options", scope=sid)}
        for k in sorted(set(lo) | set(ro)):
            add(tr("cmp.option", opt=k), lo.get(k, "–"), ro.get(k, "–"))

        def res_map(lst):
            return {r["ip"]: f"{ip.format_client_id(r['cid']) or r['cid']} {r['name']}".strip() for r in lst}
        lr = res_map(n_res(x) for x in self.cim("Get-DhcpServerv4Reservation", ScopeId=sid))
        rr = res_map(self.partner(pn, "reservations", scope=sid))
        add(tr("cmp.res_count"), len(lr), len(rr))
        n = 0
        for k in sorted(set(lr) | set(rr), key=ip.ip_sort_key):
            a, b = lr.get(k, "–"), rr.get(k, "–")
            if a != b:
                add(tr("cmp.reservation", ip=k), a, b)
                n += 1
            if n >= 50:
                rows.append({"el": tr("cmp.reservations"), "local": "…", "partner": "…", "result": "more"})
                break
        return rows

    def compare_relationship(self, rel: dict, ids: list[str]) -> dict[str, tuple[str, str]]:
        """{scope: (zustand, details)} mit zustand = sync | missing | diff:<n> | error."""
        out = {}
        for i, sid in enumerate(ids, 1):
            if self.cancel.is_set():
                break
            self.progress(self.tr("status.comparing", id=sid, i=i, n=len(ids)), i, len(ids))
            try:
                rows = self.compare_scope(sid, rel)
                diff = [r for r in rows if r["result"] != "same"]
                if not diff:
                    out[sid] = ("sync", "")
                elif any(r["result"] == "missing" for r in diff):
                    out[sid] = ("missing", self.tr("cmp.missing_detail"))
                else:
                    out[sid] = (f"diff:{len(diff)}", ", ".join(r["el"] for r in diff[:8]))
            except UserError as e:
                out[sid] = ("error", str(e))
        return out

    # --- Server-Scan --------------------------------------------------------------------------------
    def server_info(self) -> dict:
        info: dict = {}

        def get(key, cmd, conv):
            try:
                r = self.cim(cmd)
                info[key] = conv(r[0] if r else {})
            except UserError as e:
                info[key + "_error"] = str(e)
        get("version", "Get-DhcpServerVersion", lambda r: {"major": _i(r.get("MajorVersion")), "minor": _i(r.get("MinorVersion"))})
        get("settings", "Get-DhcpServerSetting", lambda r: {
            "domain_joined": _b(r.get("IsDomainJoined")), "authorized": _b(r.get("IsAuthorized")),
            "nap": _b(r.get("NapEnabled")), "conflict_attempts": _i(r.get("ConflictDetectionAttempts")),
            "dynamic_bootp": _b(r.get("DynamicBootp"))})
        get("audit", "Get-DhcpServerAuditLog", lambda r: {"enabled": _b(r.get("Enable"))})
        get("database", "Get-DhcpServerDatabase", lambda r: {
            "logging": _b(r.get("LoggingEnabled")), "backup_interval": _i(r.get("BackupInterval")),
            "file": _s(r.get("FileName")), "backup_path": _s(r.get("BackupPath"))})
        try:
            d = self.cim("Get-DhcpServerv4DnsSetting")
            info["dns"] = n_dns(d[0]) if d else None
            if info["dns"] and info["dns"]["dyn"] != "Never":
                c = self.cim("Get-DhcpServerDnsCredential")
                info["dns_credential_user"] = _s((c[0] if c else {}).get("UserName"))
        except UserError:
            pass
        try:
            info["bindings"] = [{"state": _b(b.get("BindingState")), "alias": _s(b.get("InterfaceAlias")),
                                 "ip": _s(b.get("IPAddress"))} for b in self.cim("Get-DhcpServerv4Binding")]
        except UserError:
            pass
        try:
            sup: dict[str, int] = {}
            for x in self.cim("Get-DhcpServerv4Superscope"):
                name = _s(x.get("SuperscopeName"))
                if not name:
                    continue
                sc = x.get("ScopeId") or []
                sup[name] = sup.get(name, 0) + (len([y for y in sc if y]) if isinstance(sc, list) else 1)
            info["superscopes"] = sup
        except UserError:
            pass
        try:
            info["disabled_policies"] = [_s(x.get("Name")) for x in self.cim("Get-DhcpServerv4Policy") if not _b(x.get("Enabled"))]
        except UserError:
            pass
        try:
            fl = self.cim("Get-DhcpServerv4FilterList")
            fl = fl[0] if fl else {}
            f = {"allow": _b(fl.get("Allow")), "deny": _b(fl.get("Deny")), "allow_count": 0}
            if f["allow"]:
                try:
                    f["allow_count"] = len(self.cim("Get-DhcpServerv4Filter", List="Allow"))
                except UserError:
                    pass
            info["filters"] = f
        except UserError:
            pass
        return info

    def partner_check(self, pn: str) -> dict:
        pc = {"partner": pn, "primary_only": self.partner_mode == "Off"}
        try:
            self.partner(pn, "version")
        except UserError as e:
            pc["error"] = str(e)
            return pc
        try:
            def srv_opts(lst):
                return {o["id"]: oc.compare_form(o["values"], self.opt_def(o["id"], ""))
                        for o in lst if not o.get("vendor") and not o.get("user") and o["id"] not in (51, 81)}
            pc["local_options"] = srv_opts(self.options())
            pc["options"] = srv_opts(self.partner(pn, "options"))
        except UserError as e:
            pc["options_error"] = str(e)
        try:
            pc["defs"] = {(d.get("vendor") or "", d["id"]): d for d in self.partner(pn, "defs")}
        except UserError as e:
            pc["defs_error"] = str(e)
        return pc

    def scan_data(self, s: dict, stat: dict | None, excl: list[tuple[int, int]], with_leases: bool) -> dict:
        sid = s["id"]
        start, end = ip.ip2int(s["start"]), ip.ip2int(s["end"])
        rng = ip.effective_ranges(start, end, excl)
        try:
            opts = self.options(sid)
        except UserError:
            opts = []
        try:
            res = [n_res(x) for x in self.cim("Get-DhcpServerv4Reservation", ScopeId=sid)]
        except UserError:
            res = []
        dns = None
        try:
            d = self.cim("Get-DhcpServerv4DnsSetting", ScopeId=sid)
            dns = n_dns(d[0]) if d else None
        except UserError:
            pass
        leases = []
        if with_leases:
            try:
                leases = [n_lease(x) for x in self.cim("Get-DhcpServerv4Lease", ScopeId=sid)]
            except UserError:
                pass
        return {"id": sid, "model": ip.ScopeModel.from_scope(sid, s["mask"], rng), "name": s["name"], "lease": s["lease"],
                "state": s["state"], "start": start, "end": end, "res_start": start, "res_end": end, "exclusions": excl,
                "stat": stat, "dns": dns, "options": opts, "reservations": res, "leases": leases,
                "rel": self.scope_fo.get(sid), "unreplicated": False, "is_tab": False}

    def scan(self, with_leases: bool, compare_partners: bool) -> dict:
        tr = self.tr
        self.cancel.clear()
        started = time.time()
        self.progress(tr("scan.loading"))
        self.load_defs()
        self.load_server_options()
        self.load_failovers()
        self.load_overview()
        checker = ck.Checker(tr, self.defs, self.server_options, self.failovers)
        scan = {"time": time.strftime("%H:%M:%S"), "scopes": {}, "partial": False, "with_leases": with_leases}
        n = len(self.scopes)
        for i, s in enumerate(self.scopes, 1):
            if self.cancel.is_set():
                scan["partial"] = True
                break
            self.progress(tr("scan.scope", i=i, n=n, id=s["id"], name=s["name"]), i, n)
            info = self.scope_info.get(s["id"]) or {}
            try:
                data = self.scan_data(s, info.get("stat"), info.get("exclusions") or [], with_leases)
                f = ck.sort_findings(checker.scope_findings(data))
            except Exception as e:  # noqa: BLE001 - ein defekter Scope darf den Scan nicht abbrechen
                data = None
                f = [ck.Finding(ck.WARN, "scan", tr("chk.scan_scope_failed", error=str(e)), obj="Scan")]
                f[0].scope_id = s["id"]
            scan["scopes"][s["id"]] = {"scope": s, "findings": f, "data": data}
        self.progress(tr("scan.server"))
        info = self.server_info()
        pcs = [self.partner_check(pn) for pn in self.partners()] if compare_partners else []
        scan_scopes = {k: v["data"] for k, v in scan["scopes"].items() if v["data"]}
        scan["server"] = ck.sort_findings(checker.server_findings(info, self.scopes, scan_scopes, pcs))
        scan["seconds"] = int(time.time() - started)
        return scan


    # --- Schnelle Prüfung (eigener Host-Prozess, läuft parallel zur Bedienung) -----------------------
    def clone_for(self, backend, log=None, progress=None) -> "DhcpService":
        """Kopie des Verbindungszustands für einen zweiten Zugriff (die Prüfung blockiert so nichts)."""
        c = DhcpService(backend, self.tr, log or self._log, progress or self._progress)
        c.server, c.user, c.protocol = self.server, self.user, self.protocol
        c.partner_mode = self.partner_mode
        c.partner_via = {k: v for k, v in self.partner_via.items() if v == "Rpc"}   # CIM-Partner neu verbinden
        c.partner_fail = dict(self.partner_fail)
        c.partner_user = dict(self.partner_user)
        c.netsh_ok = set(self.netsh_ok)
        c.netsh_fail = dict(self.netsh_fail)
        c.secrets = dict(self.secrets)
        c.rights = dict(self.rights)
        return c

    def attach(self) -> None:
        """Meldet den zweiten Zugriff mit denselben Anmeldedaten am Server (und für die Partner) an."""
        user, pw = self.secrets.get("*", ("", ""))
        self.call("connect", {"server": self.server, "user": user, "password": pw, "primary": True})
        for pn, (u, p) in self.secrets.items():
            if pn != "*":
                self.call("set_cred", {"server": pn, "user": u, "password": p})

    def fast_scan(self, with_leases: bool, compare_partners: bool, on_scope=None, threads: int = 8) -> dict:
        """Wie scan(), aber alle Lesezugriffe gebündelt und parallel; Scopes werden sofort ausgewertet,
        sobald ihre Daten da sind (on_scope(id, eintrag, fertig, gesamt)). Abbruch liefert ein Teilergebnis."""
        tr = self.tr
        started = time.time()
        scan = {"time": time.strftime("%H:%M:%S"), "scopes": {}, "server": [], "partial": False, "with_leases": with_leases}
        self.prefetch = {}
        try:
            self.progress(tr("scan.loading"))
            srv = [("Get-DhcpServerv4OptionDefinition", {"All": True}), ("Get-DhcpServerv4OptionValue", {"All": True}),
                   ("Get-DhcpServerv4Failover", {}), ("Get-DhcpServerv4Scope", {}), ("Get-DhcpServerv4ScopeStatistics", {}),
                   ("Get-DhcpServerv4ExclusionRange", {}), ("Get-DhcpServerVersion", {}), ("Get-DhcpServerSetting", {}),
                   ("Get-DhcpServerAuditLog", {}), ("Get-DhcpServerDatabase", {}), ("Get-DhcpServerv4DnsSetting", {}),
                   ("Get-DhcpServerDnsCredential", {}), ("Get-DhcpServerv4Binding", {}), ("Get-DhcpServerv4Superscope", {}),
                   ("Get-DhcpServerv4Policy", {}), ("Get-DhcpServerv4FilterList", {}), ("Get-DhcpServerv4Filter", {"List": "Allow"})]
            self.prefetch.update(self.cim_many([(n, None, p) for n, p in srv], threads))
            self.load_defs()
            self.load_server_options()
            self.load_failovers()
            self.load_overview()
            checker = ck.Checker(tr, self.defs, self.server_options, self.failovers)
            scopes = {s["id"]: s for s in self.scopes}
            per = [("Get-DhcpServerv4OptionValue", {"All": True}), ("Get-DhcpServerv4Reservation", {}),
                   ("Get-DhcpServerv4DnsSetting", {})]
            if with_leases:
                per.append(("Get-DhcpServerv4Lease", {}))
            calls, need, owner = [], {}, {}
            for sid in scopes:
                need[sid] = set()
                for name, p in per:
                    pp = dict(p, ScopeId=sid)
                    k = self._key(name, None, pp)
                    calls.append((name, None, pp))
                    need[sid].add(k)
                    owner[k] = sid
            n = len(scopes)

            def evaluate(sid):
                s = scopes[sid]
                info = self.scope_info.get(sid) or {}
                try:
                    data = self.scan_data(s, info.get("stat"), info.get("exclusions") or [], with_leases)
                    f = ck.sort_findings(checker.scope_findings(data))
                except Exception as e:  # noqa: BLE001 - ein defekter Scope darf die Prüfung nicht abbrechen
                    data = None
                    f = [ck.Finding(ck.WARN, "scan", tr("chk.scan_scope_failed", error=str(e)), obj="Scan")]
                    f[0].scope_id = sid
                entry = {"scope": s, "findings": f, "data": data}
                scan["scopes"][sid] = entry
                done = len(scan["scopes"])
                self.progress(tr("scan.scope", i=done, n=n, id=sid, name=s["name"]), done, n)
                if on_scope:
                    on_scope(sid, entry, done, n)

            def on_result(k, v):
                self.prefetch[k] = v
                sid = owner.get(k)
                if sid is None or sid in scan["scopes"]:
                    return
                need[sid].discard(k)
                if not need[sid]:
                    evaluate(sid)
            self.progress(tr("scan.scopes_parallel", n=n, threads=threads), 0, n)
            try:
                self.cim_many(calls, threads, on_result)
            except UserError:
                if not self.cancel.is_set():
                    raise
            if self.cancel.is_set():
                scan["partial"] = True
            else:
                for sid in scopes:
                    if sid not in scan["scopes"]:
                        evaluate(sid)
                self.progress(tr("scan.server"))
                info = self.server_info()
                pcs = [self.partner_check(pn) for pn in self.partners()] if compare_partners else []
                scan_scopes = {k: v["data"] for k, v in scan["scopes"].items() if v["data"]}
                scan["server"] = ck.sort_findings(checker.server_findings(info, self.scopes, scan_scopes, pcs))
        except UserError:
            if not self.cancel.is_set():
                raise
            scan["partial"] = True
        finally:
            self.prefetch = None
        scan["seconds"] = int(time.time() - started)
        return scan


class ReplicationError(UserError):
    def __init__(self, text: str, ok: list[str]):
        super().__init__(text)
        self.ok = ok


def short_list(items: list[str], n: int) -> str:
    lst = [str(x) for x in items]
    out = "\n".join("• " + x for x in lst[:n])
    if len(lst) > n:
        out += f"\n• … (+{len(lst) - n})"
    return out
