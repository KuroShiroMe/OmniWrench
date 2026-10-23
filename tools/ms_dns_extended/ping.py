"""Erreichbarkeit per ICMP (IcmpSendEcho / Icmp6SendEcho2 aus iphlpapi.dll), ohne Administratorrechte.

Nur für die Aufräum-Vorschau: "Lebt das Gerät hinter einem veralteten Eintrag noch?" Ein Gerät mit
Firewall antwortet evtl. nicht – das Ergebnis ist ein Hinweis, kein Beweis.
"""

from __future__ import annotations

import ctypes
import ipaddress
import os
import socket
from concurrent.futures import ThreadPoolExecutor
from ctypes import byref, c_ubyte, c_uint16, c_uint32, c_void_p

_DATA = b"OmniWrench"


class _SockAddrIn6(ctypes.Structure):
    _fields_ = [("sin6_family", c_uint16), ("sin6_port", c_uint16), ("sin6_flowinfo", c_uint32),
                ("sin6_addr", c_ubyte * 16), ("sin6_scope_id", c_uint32)]


def _ping4(ip: str, timeout_ms: int) -> bool:
    ctypes.windll.iphlpapi.IcmpCreateFile.restype = c_void_p
    h = ctypes.windll.iphlpapi.IcmpCreateFile()
    if not h or h == c_void_p(-1).value:
        return False
    try:
        addr = int.from_bytes(socket.inet_aton(ip), "little")
        buf = ctypes.create_string_buffer(256)
        fn = ctypes.windll.iphlpapi.IcmpSendEcho
        fn.argtypes = [c_void_p, c_uint32, c_void_p, c_uint16, c_void_p, c_void_p, c_uint32, c_uint32]
        fn.restype = c_uint32
        n = fn(h, addr, _DATA, len(_DATA), None, buf, len(buf), timeout_ms)
        if not n:
            return False
        status = int.from_bytes(buf.raw[4:8], "little")     # ICMP_ECHO_REPLY.Status
        return status == 0
    finally:
        ctypes.windll.iphlpapi.IcmpCloseHandle(c_void_p(h))


def _ping6(ip: str, timeout_ms: int) -> bool:
    lib = ctypes.windll.iphlpapi
    lib.Icmp6CreateFile.restype = c_void_p
    h = lib.Icmp6CreateFile()
    if not h or h == c_void_p(-1).value:
        return False
    try:
        src = _SockAddrIn6()
        src.sin6_family = socket.AF_INET6
        dst = _SockAddrIn6()
        dst.sin6_family = socket.AF_INET6
        a = ipaddress.IPv6Address(ip.split("%")[0])
        for i, b in enumerate(a.packed):
            dst.sin6_addr[i] = b
        buf = ctypes.create_string_buffer(512)
        fn = lib.Icmp6SendEcho2
        fn.argtypes = [c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_void_p, c_uint16, c_void_p,
                       c_void_p, c_uint32, c_uint32]
        fn.restype = c_uint32
        n = fn(c_void_p(h), None, None, None, byref(src), byref(dst), _DATA, len(_DATA), None, buf, len(buf), timeout_ms)
        return bool(n)      # Anzahl Echo-Antworten (Fehler wie "nicht erreichbar" liefern 0)
    finally:
        lib.IcmpCloseHandle(c_void_p(h))


def ping(ip: str, timeout_ms: int = 800) -> bool | None:
    """True = Antwort, False = keine Antwort, None = nicht prüfbar (kein Windows / ungültige Adresse)."""
    if os.name != "nt":
        return None
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return None
    try:
        return _ping6(str(a), timeout_ms) if a.version == 6 else _ping4(str(a), timeout_ms)
    except OSError:
        return None


def ping_many(ips: list[str], timeout_ms: int = 800, threads: int = 32) -> dict[str, bool | None]:
    uniq = list(dict.fromkeys(ips))
    if not uniq:
        return {}
    with ThreadPoolExecutor(max_workers=min(threads, len(uniq)), thread_name_prefix="ping") as ex:
        return dict(zip(uniq, ex.map(lambda x: ping(x, timeout_ms), uniq)))
