"""ICMP-Echo ohne Administratorrechte.

Windows: IcmpSendEcho aus iphlpapi.dll (wie ping.exe/tracert.exe, keine Rohsockets nötig).
Andere Systeme (nur Entwicklung): ping-Befehl von iputils.
Blockierende Aufrufe - die Engine führt sie in einem Thread-Pool aus.
"""

from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

OK, TTL_EXPIRED, TIMEOUT, UNREACHABLE, TOO_BIG, ERROR = "ok", "ttl_expired", "timeout", "unreachable", "too_big", "error"


@dataclass
class Echo:
    status: str
    rtt_ms: float | None = None
    ttl: int | None = None          # TTL der Antwort
    from_ip: str | None = None      # antwortende Adresse (bei TTL abgelaufen: der Router)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _IPOptions(ctypes.Structure):
        _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                    ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]

    class _EchoReply(ctypes.Structure):
        _fields_ = [("Address", wintypes.ULONG), ("Status", wintypes.ULONG), ("RoundTripTime", wintypes.ULONG),
                    ("DataSize", wintypes.USHORT), ("Reserved", wintypes.USHORT), ("Data", ctypes.c_void_p),
                    ("Options", _IPOptions)]

    _iphlp = ctypes.WinDLL("iphlpapi.dll", use_last_error=True)
    _iphlp.IcmpCreateFile.restype = wintypes.HANDLE
    _iphlp.IcmpCloseHandle.argtypes = [wintypes.HANDLE]
    _iphlp.IcmpSendEcho.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.WORD,
                                     ctypes.POINTER(_IPOptions), ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    _iphlp.IcmpSendEcho.restype = wintypes.DWORD
    _STATUS = {0: OK, 11013: TTL_EXPIRED, 11014: TTL_EXPIRED, 11010: TIMEOUT, 11002: UNREACHABLE,
               11003: UNREACHABLE, 11004: UNREACHABLE, 11005: UNREACHABLE, 11009: TOO_BIG}

    def available() -> bool:
        return True

    def echo(ip: str, ttl: int = 128, timeout_ms: int = 1000, size: int = 32, df: bool = False) -> Echo:
        addr = ipaddress.ip_address(ip)
        if addr.version != 4:
            return Echo(ERROR)
        handle = _iphlp.IcmpCreateFile()
        try:
            payload = (b"OmniWrench" * (size // 10 + 1))[:size]
            opts = _IPOptions(Ttl=ttl, Tos=0, Flags=0x02 if df else 0, OptionsSize=0, OptionsData=None)
            buf = ctypes.create_string_buffer(ctypes.sizeof(_EchoReply) + size + 64)
            dest = int.from_bytes(addr.packed, "little")
            start = time.perf_counter()
            count = _iphlp.IcmpSendEcho(handle, dest, payload, len(payload), ctypes.byref(opts),
                                        buf, len(buf), timeout_ms)
            measured = (time.perf_counter() - start) * 1000
            reply = _EchoReply.from_buffer(buf)
            if count == 0:
                err = ctypes.get_last_error()
                return Echo(_STATUS.get(err, TIMEOUT if err == 11010 else ERROR))
            frm = str(ipaddress.IPv4Address(reply.Address.to_bytes(4, "little")))
            status = _STATUS.get(reply.Status, ERROR)
            rtt = float(reply.RoundTripTime) if reply.RoundTripTime else min(measured, 1.0)
            return Echo(status, rtt, reply.Options.Ttl or None, frm)
        finally:
            _iphlp.IcmpCloseHandle(handle)
else:
    _PING = shutil.which("ping")
    _TIME = re.compile(r"time[=<]([\d.]+)")
    _TTL = re.compile(r"ttl=(\d+)", re.I)
    _FROM = re.compile(r"From ([\d.]+).*(Time to live exceeded|Frag needed|Unreachable)", re.I)

    def available() -> bool:
        return _PING is not None

    def echo(ip: str, ttl: int = 128, timeout_ms: int = 1000, size: int = 32, df: bool = False) -> Echo:
        if _PING is None:
            return Echo(ERROR)
        cmd = [_PING, "-n", "-c", "1", "-W", str(max(1, round(timeout_ms / 1000))), "-t", str(ttl), "-s", str(size)]
        if df:
            cmd += ["-M", "do"]
        try:
            out = subprocess.run(cmd + [ip], capture_output=True, text=True, timeout=timeout_ms / 1000 + 3).stdout
        except (OSError, subprocess.TimeoutExpired):
            return Echo(TIMEOUT)
        if m := _FROM.search(out):
            kind = m.group(2).lower()
            status = TTL_EXPIRED if "time" in kind else TOO_BIG if "frag" in kind else UNREACHABLE
            return Echo(status, None, None, m.group(1))
        if t := _TIME.search(out):
            ttl_m = _TTL.search(out)
            return Echo(OK, float(t.group(1)), int(ttl_m.group(1)) if ttl_m else None, ip)
        return Echo(TIMEOUT)
