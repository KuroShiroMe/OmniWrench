"""AD-Replikation einer Verzeichnispartition anstoßen (ntdsapi.dll über ctypes, ohne PowerShell/repadmin).

Entspricht `repadmin /syncall <dc> <partition> /P /e /d`: Der DC, auf dem geändert wurde, schiebt seine
Änderungen an alle Replikationspartner (auch über Standortgrenzen). Nötig ist das erweiterte Recht
„Replikation synchronisieren“ (DS-Replication-Synchronize) auf der Partition; Domänen-Admins haben es für
DomainDnsZones, für ForestDnsZones standardmäßig nur Organisations-Admins (oder per Delegation).

Fehler: AdReplError(code, text, details). code 5/8453 = Recht fehlt (siehe DENIED).
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

DS_REPSYNCALL_ID_SERVERS_BY_DN = 0x4
DS_REPSYNCALL_PUSH_CHANGES_OUTWARD = 0x20
DS_REPSYNCALL_CROSS_SITE_BOUNDARIES = 0x40
FLAGS = DS_REPSYNCALL_ID_SERVERS_BY_DN | DS_REPSYNCALL_PUSH_CHANGES_OUTWARD | DS_REPSYNCALL_CROSS_SITE_BOUNDARIES

ERROR_ACCESS_DENIED = 5
ERROR_DS_DRA_ACCESS_DENIED = 8453
DENIED = {ERROR_ACCESS_DENIED, ERROR_DS_DRA_ACCESS_DENIED}

EV_ERROR, EV_STARTED, EV_COMPLETED, EV_FINISHED = 0, 1, 2, 3
ERR_KIND = {0: "contacting server", 1: "replicating", 2: "server unreachable"}


class AdReplError(Exception):
    def __init__(self, code: int, text: str, details: list[str] | None = None):
        super().__init__(text)
        self.code = code
        self.details = list(details or [])

    @property
    def denied(self) -> bool:
        return self.code in DENIED


class _ErrInfo(ctypes.Structure):
    _fields_ = [("pszSvrId", wintypes.LPWSTR), ("error", ctypes.c_int), ("dwWin32Err", wintypes.DWORD),
                ("pszSrcId", wintypes.LPWSTR)]


class _Sync(ctypes.Structure):
    _fields_ = [("pszSrcId", wintypes.LPWSTR), ("pszDstId", wintypes.LPWSTR), ("pszNC", wintypes.LPWSTR),
                ("pguidSrc", ctypes.c_void_p), ("pguidDst", ctypes.c_void_p)]


class _Update(ctypes.Structure):
    _fields_ = [("event", ctypes.c_int), ("pErrInfo", ctypes.POINTER(_ErrInfo)), ("pSync", ctypes.POINTER(_Sync))]


def available() -> bool:
    return sys.platform == "win32"


def server_name(dn: str | None) -> str:
    """'CN=NTDS Settings,CN=DC02,CN=Servers,…' -> 'DC02' (sonst der Text selbst)."""
    if not dn:
        return "?"
    parts = [p.strip() for p in dn.split(",")]
    if len(parts) > 1 and parts[0].upper() == "CN=NTDS SETTINGS" and parts[1].upper().startswith("CN="):
        return parts[1][3:]
    return dn


def win_text(code: int) -> str:
    try:
        return ctypes.FormatError(code).strip()   # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return ""


def _api():
    dll = ctypes.WinDLL("ntdsapi.dll")   # type: ignore[attr-defined]
    cb_type = ctypes.WINFUNCTYPE(wintypes.BOOL, ctypes.c_void_p, ctypes.POINTER(_Update))  # type: ignore[attr-defined]
    dll.DsMakePasswordCredentialsW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                               ctypes.POINTER(ctypes.c_void_p)]
    dll.DsMakePasswordCredentialsW.restype = wintypes.DWORD
    dll.DsFreePasswordCredentials.argtypes = [ctypes.c_void_p]
    dll.DsFreePasswordCredentials.restype = None
    dll.DsBindWithCredW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(wintypes.HANDLE)]
    dll.DsBindWithCredW.restype = wintypes.DWORD
    dll.DsUnBindW.argtypes = [ctypes.POINTER(wintypes.HANDLE)]
    dll.DsUnBindW.restype = wintypes.DWORD
    dll.DsReplicaSyncAllW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.ULONG, cb_type, ctypes.c_void_p,
                                      ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_ErrInfo)))]
    dll.DsReplicaSyncAllW.restype = wintypes.DWORD
    return dll, cb_type


def split_user(user: str) -> tuple[str | None, str | None]:
    if not user:
        return None, None
    if "\\" in user:
        d, u = user.split("\\", 1)
        return u, d
    if "@" in user:
        u, d = user.split("@", 1)
        return u, d
    return user, None


def sync_all(dc: str, nc: str, user: str = "", password: str = "") -> list[str]:
    """Änderungen von dc für die Partition nc an alle Partner schieben. Liefert die Zeilen „Quelle → Ziel“
    der erfolgreichen Abgleiche; Fehler -> AdReplError (alle Teilfehler in details, nie das Passwort)."""
    if not available():
        raise AdReplError(0, "@ERR:no_ntdsapi:")
    dll, cb_type = _api()
    kernel32 = ctypes.WinDLL("kernel32")   # type: ignore[attr-defined]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    details = [f"call: DsReplicaSyncAllW(DC={dc!r}, NC={nc!r}, flags=0x{FLAGS:X})",
               f"user: {user or '(current)'}, password: {'***' if password else '(empty)'}"]
    auth = ctypes.c_void_p()
    if user:
        u, d = split_user(user)
        rc = dll.DsMakePasswordCredentialsW(u, d, password or "", ctypes.byref(auth))
        if rc:
            raise AdReplError(rc, f"@ERR:ad_sync:{dc}|{rc}|{win_text(rc)}", details + [f"DsMakePasswordCredentialsW: {rc}"])
    h = wintypes.HANDLE()
    try:
        rc = dll.DsBindWithCredW(dc, None, auth if user else None, ctypes.byref(h))
        if rc:
            raise AdReplError(rc, f"@ERR:{'repl_denied' if rc in DENIED else 'ad_sync'}:{dc}|{rc}|{win_text(rc)}",
                              details + [f"DsBindWithCredW: {rc} {win_text(rc)}"])
        done: list[str] = []
        events: list[str] = []

        def cb(_data, upd):
            try:
                u = upd.contents
                if u.event == EV_COMPLETED and u.pSync:
                    s = u.pSync.contents
                    done.append(f"{server_name(s.pszSrcId)} → {server_name(s.pszDstId)}")
                elif u.event == EV_ERROR and u.pErrInfo:
                    e = u.pErrInfo.contents
                    events.append(f"error: {server_name(e.pszSrcId)} → {server_name(e.pszSvrId)}: "
                                  f"{ERR_KIND.get(e.error, e.error)}, {e.dwWin32Err} {win_text(e.dwWin32Err)}")
            except Exception:  # noqa: BLE001 - Rückruf darf nie werfen
                pass
            return True

        callback = cb_type(cb)
        errs = ctypes.POINTER(ctypes.POINTER(_ErrInfo))()
        rc = dll.DsReplicaSyncAllW(h, nc, FLAGS, callback, None, ctypes.byref(errs))
        codes: list[int] = []
        if errs:
            i = 0
            while errs[i]:
                e = errs[i].contents
                codes.append(int(e.dwWin32Err))
                details.append(f"errinfo: {server_name(e.pszSrcId)} → {server_name(e.pszSvrId)}: "
                               f"{ERR_KIND.get(e.error, e.error)}, {e.dwWin32Err} {win_text(e.dwWin32Err)}")
                i += 1
            kernel32.LocalFree(ctypes.cast(errs, ctypes.c_void_p))
        details += events + [f"synced: {x}" for x in done]
        if rc or codes:
            code = next((c for c in codes if c in DENIED), rc or (codes[0] if codes else 0))
            key = "repl_denied" if code in DENIED else "ad_sync"
            raise AdReplError(code, f"@ERR:{key}:{dc}|{code}|{win_text(code)}", details)
        return done
    finally:
        if h:
            dll.DsUnBindW(ctypes.byref(h))
        if user and auth:
            dll.DsFreePasswordCredentials(auth)


def partition_of(zone_dn: str) -> str:
    """DN der Zone -> DN der Partition, in der sie liegt.

    'DC=corp.example,CN=MicrosoftDNS,DC=DomainDnsZones,DC=corp,DC=example' -> 'DC=DomainDnsZones,DC=corp,DC=example'
    'DC=x,CN=MicrosoftDNS,CN=System,DC=corp,DC=example' (Windows-2000-Modus) -> 'DC=corp,DC=example'"""
    parts = [p.strip() for p in zone_dn.split(",")]
    for i, p in enumerate(parts):
        if p.upper() == "CN=MICROSOFTDNS":
            rest = parts[i + 1:]
            if rest and rest[0].upper() == "CN=SYSTEM":
                rest = rest[1:]
            return ",".join(rest)
    return ""


def guess_partition(zone: str, server_fqdn: str) -> str:
    """Partition ohne DN der Zone schätzen: _msdcs.<Gesamtstruktur> liegt in ForestDnsZones der Gesamtstruktur,
    alles andere in DomainDnsZones der Domäne des Servers (Standard beim Anlegen über die DNS-Konsole)."""
    z = zone.strip(".").lower()
    if z.startswith("_msdcs."):
        dom, part = z[len("_msdcs."):], "ForestDnsZones"
    else:
        dom, part = server_fqdn.strip(".").lower().partition(".")[2], "DomainDnsZones"
    if not dom:
        return ""
    return f"DC={part}," + ",".join(f"DC={x}" for x in dom.split("."))


def partition_label(nc: str) -> str:
    first = nc.split(",", 1)[0].upper()
    if first == "DC=DOMAINDNSZONES":
        return "DomainDnsZones"
    if first == "DC=FORESTDNSZONES":
        return "ForestDnsZones"
    return nc
