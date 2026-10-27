"""Zugriff auf Microsoft-DNS-Server über WMI (Namespace root\\MicrosoftDNS), direkt aus Python mit pywin32.

Kein PowerShell, kein WinRM: WMI läuft über DCOM/RPC wie die Computerverwaltung. Funktioniert mit jedem
Windows-DNS-Server (Domänencontroller, Mitgliedsserver oder Server ohne Domäne). Andere Anmeldedaten gehen
direkt an SWbemLocator.ConnectServer; für den eigenen Computer erlaubt WMI keine anderen Anmeldedaten.

COM-Objekte werden je Thread angelegt (eigene Verbindung pro Thread und Server): Die Aufrufe kommen aus
wechselnden Hintergrund-Threads, so gibt es keine Apartment-Probleme.

Fehler kommen als HostError mit "@WMI:op:server:hresult:text" bzw. "@ERR:key:arg"; service.host_text übersetzt.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path

from . import dnsutil as du

NAMESPACE = "root\\MicrosoftDNS"
WBEM_FLAGS = 0x30           # wbemFlagReturnImmediately | wbemFlagForwardOnly
IMPERSONATE, PKT_PRIVACY = 3, 6

# Bekannte HRESULTs -> Schlüssel für verständliche Meldungen
HRESULTS = {
    0x80041003: "access", 0x80070005: "access", 0x8007052E: "logon", 0x80070569: "logon",
    0x800706BA: "unreachable", 0x800706BF: "unreachable", 0x80070776: "unreachable", 0x800706B5: "unreachable",
    0x8004100E: "no_dns", 0x80041010: "no_dns", 0x80041002: "not_found", 0x80041064: "local_creds",
    0x80041008: "bad_value", 0x8004101E: "access", 0x80041017: "bad_value", 0x80070422: "no_dns",
}


# Parameter von CreateInstanceFromPropertyData je Typ (Namen laut MicrosoftDNS_<Typ>Type)
PROPERTY_DATA = {
    "A": lambda d: {"IPAddress": d["ip"]},
    "AAAA": lambda d: {"IPv6Address": d["ip"]},
    "CNAME": lambda d: {"PrimaryName": du.norm(d["host"]) + "."},
    "PTR": lambda d: {"PTRDomainName": du.norm(d["host"]) + "."},
    "NS": lambda d: {"NSHost": du.norm(d["host"]) + "."},
    "MX": lambda d: {"Preference": int(d.get("pref", 10)), "MailExchange": du.norm(d["host"]) + "."},
    "SRV": lambda d: {"Priority": int(d.get("priority", 0)), "Weight": int(d.get("weight", 0)),
                      "Port": int(d.get("port", 0)), "DomainName": du.norm(d["host"]) + "."},
    "TXT": lambda d: {"DescriptiveText": d.get("text", "")},
}


class HostError(Exception):
    """Fehlermeldung des Zugriffs (Text mit @WMI:/@ERR:-Präfix). details = technische Zeilen für die
    Detailansicht (Aufruf, HRESULT, excepinfo, SWbemLastError, Versuche); nie Passwörter."""

    def __init__(self, msg: str = "", details: list[str] | None = None):
        super().__init__(msg)
        self.details = list(details or [])


# --- pywin32 laden (liegt beim installierten Tool im privaten _lib-Ordner) -----------------------------

_loaded = None
_load_lock = threading.Lock()


def _lib_paths() -> list[Path]:
    lib = Path(__file__).resolve().parent / "_lib"
    return [lib, lib / "win32", lib / "win32" / "lib", lib / "pywin32_system32"]


def load():
    """(pythoncom, win32com.client.dynamic, pywintypes) oder HostError, wenn pywin32 fehlt/nicht lädt."""
    global _loaded
    with _load_lock:
        if _loaded is not None:
            return _loaded
        if os.name != "nt":
            raise HostError("@ERR:windows_only:")
        # pip --target wertet die .pth-Datei von pywin32 nicht aus -> Pfade und DLL-Ordner selbst setzen
        for p in _lib_paths():
            if p.is_dir() and str(p) not in sys.path:
                sys.path.append(str(p))
        dll_dir = _lib_paths()[-1]
        if dll_dir.is_dir():
            os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(str(dll_dir))
            except (OSError, AttributeError):
                pass
        try:
            import pythoncom  # noqa: PLC0415
            import pywintypes  # noqa: PLC0415
            from win32com.client import dynamic  # noqa: PLC0415
        except ImportError as e:
            raise HostError(f"@ERR:no_pywin32:{e}") from None
        _loaded = (pythoncom, dynamic, pywintypes)
        return _loaded


def available() -> bool:
    try:
        load()
        return True
    except HostError:
        return False


def is_local(server: str) -> bool:
    s = du.norm(server)
    if s in ("", ".", "localhost", "127.0.0.1", "::1"):
        return True
    me = du.norm(os.environ.get("COMPUTERNAME", ""))
    if me and (s == me or s.split(".")[0] == me):
        return True
    try:
        return s == du.norm(socket.getfqdn())
    except OSError:
        return False


# --- Werte -------------------------------------------------------------------------------------------

def _wql(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("'", "\\'")


def _arr(v) -> list:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [x for x in v if x is not None]
    return [v]


def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _str(v) -> str:
    return "" if v is None else str(v)


def _ip_list(v) -> list[str]:
    out = []
    for x in _arr(v):
        s = str(x).strip()
        if s:
            out.append(du.parse_ip(s) or s)
    return out


def version_text(v) -> str:
    n = _int(v)
    return f"{n & 0xFF}.{(n >> 8) & 0xFF}.{(n >> 16) & 0xFFFF}" if n else ""


def zone_from_props(p: dict, server: str) -> dict:
    zt = _int(p.get("ZoneType"), -1)
    return {
        "name": du.norm(_str(p.get("Name"))), "server": server, "type": zt,
        "ds": bool(p.get("DsIntegrated")), "reverse": bool(p.get("Reverse")), "auto": bool(p.get("AutoCreated")),
        "aging": bool(p.get("Aging")), "norefresh_h": _int(p.get("NoRefreshInterval")),
        "refresh_h": _int(p.get("RefreshInterval")), "scavenge_after": du.ts_from_hours(p.get("AvailForScavengeTime")),
        "allow_update": _int(p.get("AllowUpdate")), "paused": bool(p.get("Paused")), "shutdown": bool(p.get("Shutdown")),
        "secure_secondaries": _int(p.get("SecureSecondaries"), du.XFER_NONE),
        "secondaries": _ip_list(p.get("SecondaryServers")), "notify": _int(p.get("Notify")),
        "notify_servers": _ip_list(p.get("NotifyServers")), "masters": _ip_list(p.get("MasterServers")),
        "local_masters": _ip_list(p.get("LocalMasterServers")), "data_file": _str(p.get("DataFile")),
        "forwarder_timeout": _int(p.get("ForwarderTimeout")), "forwarder_slave": bool(p.get("ForwarderSlave")),
        "use_wins": bool(p.get("UseWins")),
    }


SERVER_PROPS = {
    # Schlüssel im Tool: (WMI-Eigenschaft, Art)
    "forwarders": ("Forwarders", "ips"), "forwarding_timeout": ("ForwardingTimeout", "int"),
    "is_slave": ("IsSlave", "bool"), "no_recursion": ("NoRecursion", "bool"),
    "scavenging_hours": ("ScavengingInterval", "int"), "default_aging": ("DefaultAgingState", "bool"),
    "default_norefresh_h": ("DefaultNoRefreshInterval", "int"), "default_refresh_h": ("DefaultRefreshInterval", "int"),
    "round_robin": ("RoundRobin", "bool"), "secure_responses": ("SecureResponses", "bool"),
    "bind_secondaries": ("BindSecondaries", "bool"), "local_net_priority": ("LocalNetPriority", "bool"),
    "recursion_timeout": ("RecursionTimeout", "int"), "recursion_retry": ("RecursionRetry", "int"),
    "max_cache_ttl": ("MaxCacheTTL", "int"), "event_log_level": ("EventLogLevel", "int"),
    "disable_autoreverse": ("DisableAutoReverseZones", "bool"), "edns_probes": ("EnableEDnsProbes", "bool"),
    "dnssec": ("EnableDnsSec", "bool"), "strict_file_parsing": ("StrictFileParsing", "bool"),
    "write_authority_ns": ("WriteAuthorityNS", "bool"), "listen_addresses": ("ListenAddresses", "ips"),
}


def server_from_props(p: dict) -> dict:
    out = {"name": du.norm(_str(p.get("Name"))), "wmi_name": _str(p.get("Name")),
           "version": version_text(p.get("Version")), "ds": bool(p.get("DsAvailable")),
           "server_addresses": _ip_list(p.get("ServerAddresses"))}
    for key, (prop, kind) in SERVER_PROPS.items():
        v = p.get(prop)
        out[key] = _ip_list(v) if kind == "ips" else bool(v) if kind == "bool" else _int(v)
    return out


def rec_from_props(cls: str, p: dict) -> du.Rec | None:
    """WMI-Eintrag (Klasse MicrosoftDNS_<x>Type) -> Rec."""
    zone = du.norm(_str(p.get("ContainerName")))
    owner = du.norm(_str(p.get("OwnerName")))
    if not zone or zone.startswith(".."):
        return None
    t = cls.replace("MicrosoftDNS_", "").replace("Type", "").upper()
    text = _str(p.get("TextRepresentation"))
    if t not in du.WMI_CLASSES and text:
        parts = text.split()
        if len(parts) >= 3:      # "owner [ttl] IN TYPE …"
            t = next((parts[i + 1].upper() for i, x in enumerate(parts[:-1]) if x.upper() == "IN"), t)
    d: dict = {}
    if t == "A":
        d = {"ip": _str(p.get("IPAddress"))}
    elif t == "AAAA":
        d = {"ip": du.parse_ip(_str(p.get("IPv6Address"))) or _str(p.get("IPv6Address"))}
    elif t == "CNAME":
        d = {"host": du.norm(_str(p.get("PrimaryName")))}
    elif t == "PTR":
        d = {"host": du.norm(_str(p.get("PTRDomainName")))}
    elif t == "NS":
        d = {"host": du.norm(_str(p.get("NSHost")))}
    elif t == "MX":
        d = {"pref": _int(p.get("Preference")), "host": du.norm(_str(p.get("MailExchange")))}
    elif t == "SRV":
        d = {"priority": _int(p.get("Priority")), "weight": _int(p.get("Weight")), "port": _int(p.get("Port")),
             "host": du.norm(_str(p.get("SRVDomainName")))}
    elif t == "TXT":
        d = {"text": du.txt_unquote(_str(p.get("DescriptiveText")))}
    elif t == "SOA":
        d = {"primary": du.norm(_str(p.get("PrimaryServer"))), "responsible": du.norm(_str(p.get("ResponsibleParty"))),
             "serial": _int(p.get("SerialNumber")), "refresh": _int(p.get("RefreshInterval")),
             "retry": _int(p.get("RetryDelay")), "expire": _int(p.get("ExpireLimit")),
             "minimum": _int(p.get("MinimumTTL"))}
    else:
        d = {"raw": _str(p.get("RecordData")) or du._rdata_from_text(text)}
    return du.Rec(zone=zone, name=owner, type=t, data=d, ttl=_int(p.get("TTL")),
                  ts=du.ts_from_hours(p.get("Timestamp")), text=text)


# --- Verbindung --------------------------------------------------------------------------------------

class WmiServer:
    """Ein DNS-Server mit festen Anmeldedaten. Methoden sind threadsicher (Verbindung je Thread)."""

    def __init__(self, server: str, user: str = "", password: str = ""):
        self.server = server.strip()
        self.local = is_local(self.server)
        self.user = "" if self.local else (user or "")
        self._password = "" if self.local else (password or "")
        self._tls = threading.local()
        self.wmi_name = ""          # Name, den der DNS-Dienst selbst meldet (für DnsServerName)

    # --- Grundlagen ---------------------------------------------------------------------------------
    def _svc(self):
        pythoncom, dynamic, _pt = load()
        if not getattr(self._tls, "init", False):
            try:
                pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            except Exception:  # noqa: BLE001 - Thread hat COM schon anders initialisiert: so verwenden
                pass
            self._tls.init = True
        svc = getattr(self._tls, "svc", None)
        if svc is None:
            loc = dynamic.Dispatch("WbemScripting.SWbemLocator")
            loc.Security_.ImpersonationLevel = IMPERSONATE
            loc.Security_.AuthenticationLevel = PKT_PRIVACY
            target = "." if self.local else self.server
            try:
                # leere Zeichenfolgen = aktuelles Konto (wie in VBScript); None würde als VT_NULL übergeben
                svc = loc.ConnectServer(target, NAMESPACE, self.user or "", self._password or "")
            except Exception as e:  # noqa: BLE001
                call = (f"SWbemLocator.ConnectServer({target!r}, {NAMESPACE!r}, user={self.user or '(current account)'!r}, "
                        f"password={'***' if self._password else '(empty)'})")
                raise self._error("connect", e, call) from None
            self._tls.svc = svc
        return svc

    def _error(self, op: str, e: Exception, call: str = "") -> HostError:
        if isinstance(e, HostError):
            return e
        hr, text = 0, str(e)
        details = [f"server: {self.server} (WMI-Name: {self.wmi_name or '?'})", f"operation: {op}"]
        if call:
            details.append(f"call: {call}")
        details.append(f"exception: {type(e).__module__}.{type(e).__name__}: {e!r}")
        args = getattr(e, "args", ())
        if args and isinstance(args[0], int):
            hr = args[0] & 0xFFFFFFFF
            text = str(args[1]) if len(args) > 1 else text
            details.append(f"hresult: 0x{hr:08X} {text}")
            exc = args[2] if len(args) > 2 else None
            if exc and isinstance(exc, tuple):
                details.append("excepinfo: " + ", ".join(
                    f"{k}={v!r}" for k, v in zip(("wcode", "source", "description", "helpfile", "helpcontext", "scode"),
                                                 exc)))
                if len(exc) > 5 and isinstance(exc[5], int) and exc[5]:
                    hr = exc[5] & 0xFFFFFFFF
                    details.append(f"scode: 0x{hr:08X}")
                if len(exc) > 2 and exc[2]:
                    text = str(exc[2])
            if len(args) > 3 and args[3] is not None:
                details.append(f"argerror: {args[3]!r}")
        last = self._last_error_props()
        if last:
            details.append("SWbemLastError: " + ", ".join(f"{k}={v!r}" for k, v in last.items()))
        detail = next((str(last[k]) for k in ("Description", "StatusCode", "ErrorCode") if last.get(k) not in (None, "", 0)), "")
        if detail:
            text = f"{text} ({detail})" if text and detail not in text else detail
        key = HRESULTS.get(hr)
        if key:
            return HostError(f"@ERR:{key}:{self.server}|{hr:08X}|{text.strip()}", details)
        return HostError(f"@WMI:{op}:{self.server}:{hr:08X}:{' '.join(text.split())}", details)

    def _last_error_props(self) -> dict:
        """Alle Eigenschaften des letzten WMI-Fehlerobjekts (SWbemLastError), falls vorhanden."""
        out: dict = {}
        try:
            _pc, dynamic, _pt = load()
            le = dynamic.Dispatch("WbemScripting.SWbemLastError")
            for p in le.Properties_:
                try:
                    v = p.Value
                except Exception:  # noqa: BLE001
                    continue
                if v not in (None, ""):
                    out[p.Name] = v
        except Exception:  # noqa: BLE001 - kein Fehlerobjekt
            return {}
        return out

    @staticmethod
    def _props(obj) -> dict:
        out = {}
        for p in obj.Properties_:
            try:
                out[p.Name] = p.Value
            except Exception:  # noqa: BLE001 - nicht lesbare Eigenschaft überspringen
                continue
        return out

    def _query(self, wql: str, op: str = "read") -> list:
        try:
            # nicht list(): das fragt vorab Count ab, und das gibt es bei wbemFlagForwardOnly nicht (E_FAIL)
            return [o for o in self._svc().ExecQuery(wql, "WQL", WBEM_FLAGS)]
        except HostError:
            raise
        except Exception as e:  # noqa: BLE001
            raise self._error(op, e, f"ExecQuery({wql!r}, flags=0x{WBEM_FLAGS:X})") from None

    def _call(self, target, method: str, params: dict | None = None, op: str = "write", cls: str | None = None):
        """Methode an einem Objekt (target = SWbemObject) oder statisch an einer Klasse (target = Klassenname)."""
        svc = self._svc()
        try:
            klass = svc.Get(cls or (target if isinstance(target, str) else target.Path_.Class))
            inp = None
            if params:
                inp = klass.Methods_(method).InParameters.SpawnInstance_()
                for k, v in params.items():
                    if v is None:
                        continue
                    inp.Properties_.Item(k).Value = list(v) if isinstance(v, (list, tuple)) else v
            if isinstance(target, str):
                # SWbemServices.ExecMethod (ohne Unterstrich) für statische Methoden einer Klasse
                return svc.ExecMethod(target, method, inp) if inp is not None else svc.ExecMethod(target, method)
            return target.ExecMethod_(method, inp) if inp is not None else target.ExecMethod_(method)
        except HostError:
            raise
        except Exception as e:  # noqa: BLE001
            where = target if isinstance(target, str) else f"{cls or '?'} (Instanz)"
            raise self._error(op, e, f"{where}.{method}({params!r})") from None

    def close(self) -> None:
        self._tls = threading.local()

    # --- Server -------------------------------------------------------------------------------------
    def _server_obj(self):
        objs = self._query("SELECT * FROM MicrosoftDNS_Server")
        if not objs:
            raise HostError(f"@ERR:no_dns:{self.server}")
        return objs[0]

    def info(self) -> dict:
        p = self._props(self._server_obj())
        out = server_from_props(p)
        self.wmi_name = out["wmi_name"] or self.server
        return out

    def set_server(self, values: dict) -> None:
        obj = self._server_obj()
        try:
            for key, v in values.items():
                prop, kind = SERVER_PROPS[key]
                obj.Properties_.Item(prop).Value = list(v) if kind == "ips" else bool(v) if kind == "bool" else int(v)
            obj.Put_()
        except HostError:
            raise
        except Exception as e:  # noqa: BLE001
            raise self._error("server", e) from None

    def start_scavenging(self) -> None:
        self._call(self._server_obj(), "StartScavenging", op="scavenge")

    def clear_cache(self) -> None:
        objs = self._query("SELECT * FROM MicrosoftDNS_Cache")
        if objs:
            self._call(objs[0], "ClearCache", op="cache")

    # --- Zonen --------------------------------------------------------------------------------------
    def zones(self) -> list[dict]:
        out = []
        for o in self._query("SELECT * FROM MicrosoftDNS_Zone"):
            z = zone_from_props(self._props(o), self.server)
            if z["name"] and not z["name"].startswith(".."):
                out.append(z)
        return out

    def _zone_obj(self, zone: str):
        objs = self._query(f"SELECT * FROM MicrosoftDNS_Zone WHERE Name='{_wql(zone)}'")
        if not objs:
            raise HostError(f"@ERR:zone_missing:{zone}")
        return objs[0]

    def zone(self, zone: str) -> dict:
        return zone_from_props(self._props(self._zone_obj(zone)), self.server)

    def set_zone(self, zone: str, values: dict) -> None:
        """Beschreibbare Eigenschaften (AllowUpdate, Aging, NoRefreshInterval, RefreshInterval) setzen."""
        names = {"allow_update": ("AllowUpdate", int), "aging": ("Aging", bool),
                 "norefresh_h": ("NoRefreshInterval", int), "refresh_h": ("RefreshInterval", int)}
        obj = self._zone_obj(zone)
        try:
            for key, v in values.items():
                prop, conv = names[key]
                obj.Properties_.Item(prop).Value = conv(v)
            obj.Put_()
        except HostError:
            raise
        except Exception as e:  # noqa: BLE001
            raise self._error("zone", e) from None

    def set_transfers(self, zone: str, secure: int, secondaries: list[str], notify: int, notify_servers: list[str]) -> None:
        self._call(self._zone_obj(zone), "ResetSecondaries",
                   {"SecondaryServers": list(secondaries), "SecureSecondaries": int(secure),
                    "NotifyServers": list(notify_servers), "Notify": int(notify)}, op="zone")

    def zone_action(self, zone: str, action: str) -> None:
        method = {"reload": "ReloadZone", "refresh": "ForceRefresh", "from_ds": "UpdateFromDS",
                  "write_back": "WriteBackZone", "pause": "PauseZone", "resume": "ResumeZone"}[action]
        self._call(self._zone_obj(zone), method, op="zone")

    def age_node(self, zone: str, node: str) -> None:
        """Zeitstempel aller Einträge eines Knotens auf jetzt setzen (macht sie dynamisch/veraltbar).

        node = voller Name; wie bei dnscmd /AgeAllRecords mit abschließendem Punkt (sonst relativ zur Zone).
        Achtung: WMI kann nur alle Einträge des Namens gemeinsam altern lassen, nicht einen einzelnen."""
        self._call(self._zone_obj(zone), "AgeAllRecords",
                   {"NodeName": du.norm(node) + ".", "ApplyToSubtree": False}, op="age")

    def create_zone(self, name: str, ztype: int, ds: bool, data_file: str = "", masters: list[str] | None = None,
                    admin: str = "") -> None:
        params = {"ZoneName": name, "ZoneType": du.CREATE_TYPE[ztype], "DsIntegrated": bool(ds)}
        if data_file and not ds:
            params["DataFileName"] = data_file
        if masters:
            params["IpAddr"] = list(masters)
        if admin:
            params["AdminEmailName"] = admin
        self._call("MicrosoftDNS_Zone", "CreateZone", params, op="create_zone")

    def delete_zone(self, zone: str) -> None:
        obj = self._zone_obj(zone)
        try:
            obj.Delete_()
        except Exception as e:  # noqa: BLE001
            raise self._error("delete_zone", e) from None

    # --- Einträge -----------------------------------------------------------------------------------
    def records(self, zone: str) -> list[du.Rec]:
        out = []
        for o in self._query(f"SELECT * FROM MicrosoftDNS_ResourceRecord WHERE ContainerName='{_wql(zone)}'"):
            try:
                cls = o.Path_.Class
            except Exception:  # noqa: BLE001
                cls = ""
            r = rec_from_props(cls, self._props(o))
            if r is not None:
                out.append(r)
        return out

    def soa(self, zone: str) -> du.Rec | None:
        for o in self._query(f"SELECT * FROM MicrosoftDNS_SOAType WHERE ContainerName='{_wql(zone)}'"):
            r = rec_from_props("MicrosoftDNS_SOAType", self._props(o))
            if r is not None:
                return r
        return None

    def _find(self, rec: du.Rec):
        cls = du.WMI_CLASSES.get(rec.type)
        base = f"MicrosoftDNS_{cls}" if cls else "MicrosoftDNS_ResourceRecord"
        wql = (f"SELECT * FROM {base} WHERE ContainerName='{_wql(rec.zone)}' AND OwnerName='{_wql(rec.name)}'")
        for o in self._query(wql):
            try:
                c = o.Path_.Class
            except Exception:  # noqa: BLE001
                c = base
            r = rec_from_props(c, self._props(o))
            if r is not None and r.key == rec.key:
                return o
        return None

    def exists(self, rec: du.Rec) -> bool:
        return self._find(rec) is not None

    def create_record(self, rec: du.Rec) -> None:
        """Bekannte Typen über CreateInstanceFromPropertyData der Typklasse, sonst über die Textdarstellung.
        Meldet ein Weg "Allgemeiner Fehler" (0x80041001), folgt der nächste (auch mit dem Servernamen wie
        eingegeben statt dem vom Dienst gemeldeten); vorher wird geprüft, ob der Eintrag doch angelegt wurde."""
        if not self.wmi_name:
            self.info()
        names = [self.wmi_name] + ([self.server] if du.norm(self.server) != du.norm(self.wmi_name) else [])
        ways = [(n, self._create_props) for n in names if rec.type in PROPERTY_DATA] + \
               [(n, self._create_text) for n in names]
        first: HostError | None = None
        tried: list[str] = []
        for n, (dns_name, way) in enumerate(ways, 1):
            label = f"#{n} {'CreateInstanceFromPropertyData' if way == self._create_props else 'CreateInstanceFromTextRepresentation'}" \
                    f" DnsServerName={dns_name!r}"
            try:
                way(rec, dns_name)
                break
            except HostError as e:
                tried += [f"{label}: {e}"] + ["    " + d for d in e.details]
                if ":80041001:" not in str(e):
                    raise HostError(str(e), tried) from None
                first = first or e
                if self.exists(rec):
                    break
        else:
            raise HostError(str(first), [f"record: {du.text_representation(rec)}"] + tried)
        if rec.dynamic:
            self.age_node(rec.zone, rec.name)

    def _create_text(self, rec: du.Rec, dns_name: str) -> None:
        self._call("MicrosoftDNS_ResourceRecord", "CreateInstanceFromTextRepresentation",
                   {"DnsServerName": dns_name, "ContainerName": rec.zone,
                    "TextRepresentation": du.text_representation(rec)}, op="create")

    def _create_props(self, rec: du.Rec, dns_name: str) -> None:
        cls = f"MicrosoftDNS_{du.WMI_CLASSES[rec.type]}"
        params = {"DnsServerName": dns_name, "ContainerName": rec.zone, "OwnerName": rec.name, "RecordClass": 1}
        if rec.ttl is not None:
            params["TTL"] = int(rec.ttl)
        params.update(PROPERTY_DATA[rec.type](rec.data))
        self._call(cls, "CreateInstanceFromPropertyData", params, op="create")

    def delete_record(self, rec: du.Rec) -> None:
        o = self._find(rec)
        if o is None:
            raise HostError(f"@ERR:record_missing:{rec.name} {rec.type} {rec.value}")
        try:
            o.Delete_()
        except Exception as e:  # noqa: BLE001
            raise self._error("delete", e) from None
