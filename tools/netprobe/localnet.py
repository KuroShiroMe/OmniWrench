"""Lokales Netz: MAC-Adresse per ARP und Hersteller (IEEE-OUI-Liste, wird bei Bedarf geladen)."""

from __future__ import annotations

import ipaddress
import re
import sys
import threading
import time
from pathlib import Path

OUI_URL = "https://standards-oui.ieee.org/oui/oui.txt"
OUI_MAX_AGE = 90 * 86400

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _iphlp = ctypes.WinDLL("iphlpapi.dll")
    _iphlp.SendARP.argtypes = [wintypes.ULONG, wintypes.ULONG, ctypes.c_void_p, ctypes.POINTER(wintypes.ULONG)]

    def mac_of(ip: str) -> str:
        addr = ipaddress.ip_address(ip)
        if addr.version != 4:
            return ""
        buf = (ctypes.c_ubyte * 8)()
        size = wintypes.ULONG(6)
        if _iphlp.SendARP(int.from_bytes(addr.packed, "little"), 0, buf, ctypes.byref(size)) != 0:
            return ""
        return "-".join(f"{b:02X}" for b in bytes(buf)[:size.value])
else:
    def mac_of(ip: str) -> str:
        try:
            for line in Path("/proc/net/arp").read_text().splitlines()[1:]:
                parts = line.split()
                if parts and parts[0] == ip and parts[3] != "00:00:00:00:00:00":
                    return parts[3].upper().replace(":", "-")
        except OSError:
            pass
        return ""


class VendorDB:
    """MAC-Präfix -> Hersteller. Lädt oui.txt einmalig in den Datenordner des Tools."""

    def __init__(self, data_dir: Path, allow_download: bool):
        self.path = data_dir / "oui.txt"
        self.allow_download = allow_download
        self._map: dict[str, str] | None = None
        self._lock = threading.Lock()

    def _load(self) -> dict[str, str]:
        fresh = self.path.exists() and time.time() - self.path.stat().st_mtime < OUI_MAX_AGE
        if not fresh and self.allow_download:
            try:
                from omniwrench.core import net
                self.path.parent.mkdir(parents=True, exist_ok=True)
                data = net.get_bytes(OUI_URL, timeout=30)
                if b"(hex)" in data:
                    self.path.write_bytes(data)
            except Exception:  # noqa: BLE001 - ohne Liste nur ohne Herstellernamen
                pass
        result: dict[str, str] = {}
        if self.path.exists():
            pattern = re.compile(r"^([0-9A-F]{2}-[0-9A-F]{2}-[0-9A-F]{2})\s+\(hex\)\s+(.+)$")
            for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
                if m := pattern.match(line.strip()):
                    result[m.group(1)] = m.group(2).strip()
        return result

    def lookup(self, mac: str) -> str:
        if not mac:
            return ""
        with self._lock:
            if self._map is None:
                self._map = self._load()
        first = int(mac[:2], 16)
        if first & 0x02:
            return "local"   # lokal verwaltete (zufällige) MAC-Adresse
        return self._map.get(mac[:8].upper(), "")
