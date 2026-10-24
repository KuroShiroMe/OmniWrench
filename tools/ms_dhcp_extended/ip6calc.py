"""IPv6-Hilfsfunktionen für MS DHCP Extended Management (DHCPv6-Scopes, intern als int).

Ein DHCPv6-Scope ist bei Windows immer ein /64-Präfix; seine ID ist die Präfixadresse („2001:db8:1::“).
Adressen werden in der kurzen Schreibweise geführt (ipaddress.IPv6Address.compressed), damit Vergleiche
zwischen Server, Oberfläche und Zwischenablage stimmen.
"""

from __future__ import annotations

import ipaddress
import re

PREFIX = 64
FULL128 = (1 << 128) - 1


def is_ipv6(text) -> bool:
    if not text or not isinstance(text, str) or ":" not in text:
        return False
    try:
        ipaddress.IPv6Address(text.strip())
        return True
    except ValueError:
        return False


def is_v6_scope(sid) -> bool:
    """DHCPv6-Scope-IDs enthalten einen Doppelpunkt, IPv4-Scope-IDs nie."""
    return isinstance(sid, str) and ":" in sid


def norm(text: str) -> str:
    """Kurze Schreibweise; ungültige Eingaben bleiben unverändert."""
    try:
        return ipaddress.IPv6Address(str(text).strip()).compressed
    except ValueError:
        return str(text)


def to_int(text: str) -> int:
    return int(ipaddress.IPv6Address(str(text).strip().split("/")[0]))


def to_str(n: int) -> str:
    return ipaddress.IPv6Address(int(n) & FULL128).compressed


def net_of(text: str, plen: int = PREFIX) -> int:
    m = (FULL128 << (128 - plen)) & FULL128
    return to_int(text) & m


def prefix_of(text: str, plen: int = PREFIX) -> str:
    return to_str(net_of(text, plen))


def in_prefix(addr: str, prefix: str, plen: int = PREFIX) -> bool:
    if not (is_ipv6(addr) and is_ipv6(prefix)):
        return False
    return net_of(addr, plen) == net_of(prefix, plen)


def host_part(addr: str, plen: int = PREFIX) -> int:
    return to_int(addr) & (FULL128 >> plen)


def fmt_net(prefix: str, plen: int = PREFIX) -> str:
    return f"{norm(prefix)}/{plen}"


def fmt_range(r: tuple[str, str]) -> str:
    return f"{norm(r[0])} – {norm(r[1])}"


def parse_prefix(text: str) -> tuple[str, int] | None:
    """„2001:db8:1::/64“ oder „2001:db8:1::“ -> (Präfixadresse, Länge); None bei ungültiger Eingabe."""
    t = (text or "").strip()
    if not t:
        return None
    try:
        n = ipaddress.IPv6Network(t if "/" in t else f"{t}/{PREFIX}", strict=False)
    except ValueError:
        return None
    return n.network_address.compressed, n.prefixlen


def has_host_bits(text: str, plen: int = PREFIX) -> bool:
    t = (text or "").strip().split("/")[0]
    return is_ipv6(t) and host_part(t, plen) != 0


def convert(addr: str, src_prefix: str, dst_prefix: str, plen: int = PREFIX) -> str:
    """Adresse aus dem Quellpräfix ins Zielpräfix umrechnen (Interface-Teil bleibt); fremde Adressen unverändert."""
    if not in_prefix(addr, src_prefix, plen):
        return addr
    return to_str(net_of(dst_prefix, plen) | host_part(addr, plen))


def convert_values(values: list[str], src_prefix: str, dst_prefix: str, plen: int = PREFIX) -> list[str]:
    return [convert(v, src_prefix, dst_prefix, plen) if is_ipv6(v) else v for v in values]


def range_size(start: str, end: str) -> int:
    return to_int(end) - to_int(start) + 1


def overlaps(a: tuple[str, str], b: tuple[str, str]) -> bool:
    return to_int(a[0]) <= to_int(b[1]) and to_int(b[0]) <= to_int(a[1])


def format_duid(text: str | None) -> str | None:
    """DUID in beliebiger Schreibweise -> 00-01-00-01-…; None bei ungültiger Eingabe (2 bis 130 Byte, RFC 8415)."""
    if not text or not str(text).strip():
        return None
    hx = re.sub(r"[\s:\-.]", "", str(text)).lower()
    if hx.startswith("0x"):
        hx = hx[2:]
    if not re.fullmatch(r"[0-9a-f]+", hx) or len(hx) % 2 or not 4 <= len(hx) <= 260:
        return None
    return "-".join(hx[i:i + 2] for i in range(0, len(hx), 2))


def duid_kind(duid: str | None) -> str:
    """DUID-Art nach RFC 8415: LLT, EN, LL, UUID oder ''."""
    hx = re.sub(r"[^0-9a-fA-F]", "", str(duid or ""))
    if len(hx) < 4:
        return ""
    return {1: "LLT", 2: "EN", 3: "LL", 4: "UUID"}.get(int(hx[:4], 16), "")


def duid_mac(duid: str | None) -> str:
    """MAC-Adresse aus einer DUID-LLT/-LL (Hardwaretyp 1 = Ethernet), sonst ''."""
    hx = re.sub(r"[^0-9a-fA-F]", "", str(duid or "")).lower()
    kind = duid_kind(hx)
    if kind == "LLT" and len(hx) == 28 and hx[4:8] == "0001":
        mac = hx[16:]
    elif kind == "LL" and len(hx) == 20 and hx[4:8] == "0001":
        mac = hx[8:]
    else:
        return ""
    return "-".join(mac[i:i + 2] for i in range(0, 12, 2))


def sort_key(text: str) -> int:
    """Sortierschlüssel nach dem IPv4-Bereich (ipcalc.ip_sort_key gibt IPv4 0 … 2^32-1)."""
    return (1 << 32) + to_int(text) if is_ipv6(text) else -1
