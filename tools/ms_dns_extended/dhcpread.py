"""Nur lesender Zugriff auf einen Microsoft-DHCP-Server (dhcpsapi.dll, RPC) für den Abgleich DNS <-> DHCP.

Bewusst eigenständig: Das DNS-Tool braucht das DHCP-Tool nicht. Gelesen werden nur IPv4-Scopes, Leases und
Reservierungen (Strukturen wie im DHCP-Tool, dort gegen die Win32-Metadaten geprüft). Andere Anmeldedaten
gelten wie bei "runas /netonly" nur für den Netzwerkzugriff (LogonUser NEW_CREDENTIALS + Impersonation).
"""

from __future__ import annotations

import ctypes
import datetime as _dt
import os
import threading
from ctypes import POINTER, Structure, byref, c_int, c_ubyte, c_uint32, c_void_p, c_wchar_p

DWORD = c_uint32
BYTE = c_ubyte
LPWSTR = c_wchar_p
ERROR_MORE_DATA = 234
ERROR_NO_MORE_ITEMS = 259
ERROR_DHCP_SUBNET_NOT_PRESENT = 20005
MAX_PREF = 0xFFFFFFFF
EL_RESERVED = 2


class DATE_TIME(Structure):
    _fields_ = [("dwLowDateTime", DWORD), ("dwHighDateTime", DWORD)]


class DHCP_BINARY_DATA(Structure):
    _fields_ = [("DataLength", DWORD), ("Data", POINTER(BYTE))]


class DHCP_HOST_INFO(Structure):
    _fields_ = [("IpAddress", DWORD), ("NetBiosName", LPWSTR), ("HostName", LPWSTR)]


class DHCP_IP_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("Elements", POINTER(DWORD))]


class DHCP_IP_RESERVATION_V4(Structure):
    _fields_ = [("ReservedIpAddress", DWORD), ("ReservedForClient", POINTER(DHCP_BINARY_DATA)),
                ("bAllowedClientTypes", BYTE)]


class _ElementUnion(ctypes.Union):
    _fields_ = [("IpRange", c_void_p), ("SecondaryHost", c_void_p), ("ReservedIp", POINTER(DHCP_IP_RESERVATION_V4)),
                ("ExcludeIpRange", c_void_p), ("IpUsedCluster", c_void_p)]


class DHCP_SUBNET_ELEMENT_DATA_V5(Structure):
    _fields_ = [("ElementType", c_int), ("Element", _ElementUnion)]


class DHCP_SUBNET_ELEMENT_INFO_ARRAY_V5(Structure):
    _fields_ = [("NumElements", DWORD), ("Elements", POINTER(DHCP_SUBNET_ELEMENT_DATA_V5))]


class DHCP_CLIENT_INFO_V5(Structure):
    _fields_ = [("ClientIpAddress", DWORD), ("SubnetMask", DWORD), ("ClientHardwareAddress", DHCP_BINARY_DATA),
                ("ClientName", LPWSTR), ("ClientComment", LPWSTR), ("ClientLeaseExpires", DATE_TIME),
                ("OwnerHost", DHCP_HOST_INFO), ("bClientType", BYTE), ("AddressState", BYTE)]


class DHCP_CLIENT_INFO_ARRAY_V5(Structure):
    _fields_ = [("NumElements", DWORD), ("Clients", POINTER(POINTER(DHCP_CLIENT_INFO_V5)))]


_PROTOS = {
    "DhcpEnumSubnets": (LPWSTR, POINTER(DWORD), DWORD, POINTER(POINTER(DHCP_IP_ARRAY)), POINTER(DWORD), POINTER(DWORD)),
    "DhcpEnumSubnetElementsV5": (LPWSTR, DWORD, c_int, POINTER(DWORD), DWORD,
                                 POINTER(POINTER(DHCP_SUBNET_ELEMENT_INFO_ARRAY_V5)), POINTER(DWORD), POINTER(DWORD)),
    "DhcpEnumSubnetClientsV5": (LPWSTR, DWORD, POINTER(DWORD), DWORD, POINTER(POINTER(DHCP_CLIENT_INFO_ARRAY_V5)),
                                POINTER(DWORD), POINTER(DWORD)),
}

_lib = None
_lock = threading.Lock()


class DhcpReadError(Exception):
    def __init__(self, server: str, code: int, text: str = ""):
        self.server, self.code = server, int(code)
        super().__init__(f"@DHCP:{server}:{self.code}:{text}")


def _dll():
    global _lib
    with _lock:
        if _lib is None:
            if os.name != "nt":
                raise OSError("dhcpsapi.dll")
            lib = ctypes.WinDLL("dhcpsapi.dll")
            for name, args in _PROTOS.items():
                f = getattr(lib, name)
                f.argtypes = list(args)
                f.restype = DWORD
            lib.DhcpRpcFreeMemory.argtypes = [c_void_p]
            lib.DhcpRpcFreeMemory.restype = None
            _lib = lib
        return _lib


def available() -> bool:
    try:
        _dll()
        return True
    except OSError:
        return False


def n2ip(n: int) -> str:
    n = int(n) & 0xFFFFFFFF
    return f"{n >> 24 & 255}.{n >> 16 & 255}.{n >> 8 & 255}.{n & 255}"


def _error_text(code: int) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    flags = 0x1000 | 0x200
    src = None
    if code >= 20000:
        try:
            src = _dll()._handle
            flags |= 0x800
        except OSError:
            pass
    n = ctypes.windll.kernel32.FormatMessageW(flags, c_void_p(src) if src else None, code, 0, buf, len(buf), None)
    return buf.value[:n].strip() if n else ""


def _filetime(dt: DATE_TIME) -> str:
    ft = (int(dt.dwHighDateTime) << 32) | int(dt.dwLowDateTime)
    if ft == 0 or dt.dwHighDateTime >= 0x7FFFFFFF:
        return ""
    try:
        t = _dt.datetime(1601, 1, 1, tzinfo=_dt.timezone.utc) + _dt.timedelta(microseconds=ft // 10)
        return t.astimezone().strftime("%Y-%m-%d %H:%M")
    except (OverflowError, ValueError, OSError):
        return ""


def _mac(bd: DHCP_BINARY_DATA) -> str:
    if not bd.Data or not bd.DataLength:
        return ""
    return "-".join(f"{b:02x}" for b in bytes(bd.Data[:bd.DataLength]))


class _Impersonate:
    def __init__(self, user: str, domain: str | None, password: str):
        self.user, self.domain, self.password = user, domain, password
        self.tok = None

    def __enter__(self):
        if not self.user:
            return self
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        tok = c_void_p()
        if not adv.LogonUserW(c_wchar_p(self.user), c_wchar_p(self.domain), c_wchar_p(self.password), 9, 3, byref(tok)):
            err = ctypes.get_last_error()
            raise DhcpReadError("", err, ctypes.FormatError(err).strip())
        self.tok = tok
        if not adv.ImpersonateLoggedOnUser(tok):
            err = ctypes.get_last_error()
            ctypes.windll.kernel32.CloseHandle(tok)
            self.tok = None
            raise DhcpReadError("", err, ctypes.FormatError(err).strip())
        return self

    def __exit__(self, *exc):
        if self.tok:
            ctypes.WinDLL("advapi32").RevertToSelf()
            ctypes.windll.kernel32.CloseHandle(self.tok)
        return False


def split_user(user: str) -> tuple[str, str | None]:
    u = (user or "").strip()
    if not u:
        return "", None
    if "\\" in u:
        d, n = u.split("\\", 1)
        return n, d or None
    if "@" in u:
        return u, None
    return u, os.environ.get("USERDOMAIN") or None


def _enum(server: str, name: str, before: tuple, read) -> None:
    f = getattr(_dll(), name)
    buf_type = f.argtypes[len(before) + 3]._type_
    resume = DWORD(0)
    for _ in range(100000):
        buf = buf_type()
        nread, total = DWORD(0), DWORD(0)
        rc = int(f(server, *before, byref(resume), MAX_PREF, byref(buf), byref(nread), byref(total)))
        if rc == ERROR_NO_MORE_ITEMS:
            break
        if rc not in (0, ERROR_MORE_DATA):
            if rc == ERROR_DHCP_SUBNET_NOT_PRESENT:
                break
            raise DhcpReadError(server, rc, _error_text(rc))
        if buf:
            try:
                read(buf)
            finally:
                _dll().DhcpRpcFreeMemory(ctypes.cast(buf, c_void_p))
        if rc == 0:
            break


def leases(server: str, user: str = "", password: str = "") -> list[dict]:
    """Alle IPv4-Leases und Reservierungen: [{ip, name, mac, kind ("lease"|"reservation"), scope, expires, state}]."""
    u, d = split_user(user)
    out: list[dict] = []
    with _Impersonate(u, d, password):
        subnets: list[int] = []

        def read_subnets(buf):
            a = buf.contents
            subnets.extend(int(a.Elements[i]) for i in range(a.NumElements))
        _enum(server, "DhcpEnumSubnets", (), read_subnets)
        for sid in subnets:
            reserved: set[int] = set()
            res_mac: dict[int, str] = {}

            def read_res(buf):
                a = buf.contents
                for i in range(a.NumElements):
                    e = a.Elements[i]
                    if int(e.ElementType) == EL_RESERVED and e.Element.ReservedIp:
                        r = e.Element.ReservedIp.contents
                        reserved.add(int(r.ReservedIpAddress))
                        if r.ReservedForClient:
                            bd = r.ReservedForClient.contents
                            data = bytes(bd.Data[:bd.DataLength]) if bd.Data and bd.DataLength else b""
                            if len(data) > 6 and data[4:5] == b"\x01":
                                data = data[5:]
                            res_mac[int(r.ReservedIpAddress)] = "-".join(f"{b:02x}" for b in data)
            _enum(server, "DhcpEnumSubnetElementsV5", (sid, EL_RESERVED), read_res)
            seen: set[int] = set()

            def read_clients(buf):
                a = buf.contents
                for i in range(a.NumElements):
                    p = a.Clients[i]
                    if not p:
                        continue
                    c = p.contents
                    ipn = int(c.ClientIpAddress)
                    seen.add(ipn)
                    out.append({"ip": n2ip(ipn), "name": (c.ClientName or "").strip().rstrip(".").lower(),
                                "mac": _mac(c.ClientHardwareAddress), "scope": n2ip(sid), "mask": n2ip(c.SubnetMask),
                                "kind": "reservation" if ipn in reserved else "lease",
                                "expires": _filetime(c.ClientLeaseExpires), "state": int(c.AddressState) & 0x03})
            _enum(server, "DhcpEnumSubnetClientsV5", (sid,), read_clients)
            for ipn in reserved - seen:       # Reservierung ohne Client-Eintrag (noch nie vergeben)
                out.append({"ip": n2ip(ipn), "name": "", "mac": res_mac.get(ipn, ""), "scope": n2ip(sid),
                            "kind": "reservation", "expires": "", "state": 0})
    return out
