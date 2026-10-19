"""IPv4-Hilfsfunktionen für ScopeKeeper (intern als int).

Bereiche sind Tupel (start, end) als int. Ein Scope-Modell beschreibt Netz, Präfix, Maske, Broadcast
und die Verteilbereiche (Scope-Bereich minus Ausschlüsse).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FULL32 = 0xFFFFFFFF
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def is_ipv4(text) -> bool:
    if not text or not isinstance(text, str):
        return False
    t = text.strip()
    return bool(_IPV4.match(t)) and all(int(o) <= 255 for o in t.split("."))


def ip2int(ip: str) -> int:
    a, b, c, d = (int(o) for o in ip.strip().split("."))
    return (a << 24) | (b << 16) | (c << 8) | d


def int2ip(n: int) -> str:
    if n < 0 or n > FULL32:
        return "?"
    return f"{(n >> 24) & 255}.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def mask_from_prefix(prefix: int) -> int:
    if prefix <= 0:
        return 0
    return (FULL32 << (32 - prefix)) & FULL32


def prefix_len(mask: str | int) -> int:
    n = ip2int(mask) if isinstance(mask, str) else mask
    return bin(n & FULL32).count("1")


def is_mask(mask: str) -> bool:
    if not is_ipv4(mask):
        return False
    m = ip2int(mask)
    if m == 0:
        return False
    inv = FULL32 ^ m
    return ((inv + 1) & inv) == 0


def in_subnet(ip: str, net: str, mask: str) -> bool:
    if not (is_ipv4(ip) and is_ipv4(net) and is_ipv4(mask)):
        return False
    m = ip2int(mask)
    return (ip2int(ip) & m) == (ip2int(net) & m)


def network_of(ip: str, mask: str) -> int:
    return ip2int(ip) & ip2int(mask)


def broadcast_of(ip: str, mask: str) -> int:
    m = ip2int(mask)
    return (ip2int(ip) & m) | (FULL32 ^ m)


def fmt_net(net: int, prefix: int) -> str:
    return f"{int2ip(net)}/{prefix}"


def fmt_range(r: tuple[int, int]) -> str:
    return f"{int2ip(r[0])} – {int2ip(r[1])}"


def aligned_prefix(n: int) -> int:
    """Kleinstes Präfix (größtes Netz), für das n eine gültige Netzadresse ist."""
    if n == 0:
        return 0
    tz = 0
    while ((n >> tz) & 1) == 0 and tz < 32:
        tz += 1
    return 32 - tz


def network_suggestions(n: int, prefix: int) -> list[tuple[int, int, str]]:
    """Vorschläge für eine Adresse mit gesetzten Host-Bits: (netz, präfix, art) mit art below/above/mask."""
    m = mask_from_prefix(prefix)
    size = 1 << (32 - prefix)
    lower = n & m
    out = [(lower, prefix, "below")]
    if lower + size <= FULL32:
        out.append((lower + size, prefix, "above"))
    ap = aligned_prefix(n)
    if prefix < ap <= 30:
        out.append((n, ap, "mask"))
    return out


def convert_ip_num(ip: int, src_net: int, src_mask: int, dst_net: int, dst_mask: int) -> int | None:
    """Rechnet eine Adresse aus dem Quellnetz ins Zielnetz um (Host-Anteil bleibt erhalten).

    Adressen außerhalb des Quellnetzes bleiben unverändert; None, wenn der Host-Anteil nicht ins Zielnetz passt.
    """
    if (ip & src_mask) != (src_net & src_mask):
        return ip
    host = ip & (FULL32 ^ src_mask)
    if host & dst_mask:
        return None
    return (dst_net & dst_mask) | host


def convert_ip(ip: str, src_net: str, src_mask: str, dst_net: str, dst_mask: str) -> str | None:
    if not in_subnet(ip, src_net, src_mask):
        return ip
    n = convert_ip_num(ip2int(ip), ip2int(src_net), ip2int(src_mask), ip2int(dst_net), ip2int(dst_mask))
    return None if n is None else int2ip(n)


def convert_values(values: list[str], src_net: int, src_mask: int, dst_net: int, dst_mask: int) -> list[str]:
    out = []
    for v in values:
        if is_ipv4(v):
            n = convert_ip_num(ip2int(v), src_net, src_mask, dst_net, dst_mask)
            out.append(int2ip(n) if n is not None else v)
        else:
            out.append(v)
    return out


def format_client_id(text: str | None) -> str | None:
    """MAC/Client-ID in beliebiger Schreibweise -> 00-11-22-33-44-55; None bei ungültiger Eingabe."""
    if not text or not str(text).strip():
        return None
    hx = re.sub(r"[\s:\-.]", "", str(text)).lower()
    if not re.fullmatch(r"[0-9a-f]+", hx) or len(hx) % 2:
        return None
    return "-".join(hx[i:i + 2] for i in range(0, len(hx), 2))


def mac_hex(cid: str | None) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", str(cid or "")).lower()


def ip_sort_key(ip: str):
    return ip2int(ip) if is_ipv4(ip) else -1


# --- Bereiche --------------------------------------------------------------------------------------

def effective_ranges(start: int, end: int, exclusions: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Verteilbereiche = Scope-Bereich minus Ausschlussbereiche."""
    out = []
    cur = start
    for s, e in sorted(exclusions):
        if e < cur:
            continue
        if s > end:
            break
        if s > cur:
            out.append((cur, min(s - 1, end)))
        cur = max(cur, e + 1)
    if cur <= end:
        out.append((cur, end))
    return out


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[list[int]] = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def range_gaps(merged: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [(merged[i - 1][1] + 1, merged[i][0] - 1) for i in range(1, len(merged))]


def range_signature(ranges: list[tuple[int, int]]) -> str:
    return ";".join(f"{s}-{e}" for s, e in ranges)


def in_ranges(n: int, ranges: list[tuple[int, int]]) -> bool:
    return any(s <= n <= e for s, e in ranges)


def range_size(ranges: list[tuple[int, int]]) -> int:
    return sum(e - s + 1 for s, e in ranges)


@dataclass
class ScopeModel:
    net: int
    prefix: int
    ranges: list[tuple[int, int]] = field(default_factory=list)

    @property
    def mask(self) -> int:
        return mask_from_prefix(self.prefix)

    @property
    def bc(self) -> int:
        return self.net | (FULL32 ^ self.mask)

    @property
    def hosts(self) -> int:
        return max(0, self.bc - self.net - 1)

    def contains(self, n: int) -> bool:
        return (n & self.mask) == self.net

    @classmethod
    def from_scope(cls, scope_id: str, mask: str, ranges=None) -> "ScopeModel":
        return cls(ip2int(scope_id) & ip2int(mask), prefix_len(mask), list(ranges or []))


def find_conflicts(net: int, prefix: int, scopes: list[dict]) -> list[dict]:
    """Überschneidungen eines Netzes mit vorhandenen Scopes. CIDR-Netze sind disjunkt oder ineinander enthalten.

    Ergebnis: [{"kind": identical|contains|contained_by|overlap, "id", "prefix", "name"}]
    """
    m = mask_from_prefix(prefix)
    a1 = net & m
    a2 = a1 | (FULL32 ^ m)
    out = []
    for s in scopes:
        sm = ip2int(s["mask"])
        b1 = ip2int(s["id"]) & sm
        b2 = b1 | (FULL32 ^ sm)
        if a1 <= b2 and b1 <= a2:
            if a1 == b1 and a2 == b2:
                kind = "identical"
            elif a1 <= b1 and a2 >= b2:
                kind = "contains"
            elif b1 <= a1 and b2 >= a2:
                kind = "contained_by"
            else:
                kind = "overlap"
            out.append({"kind": kind, "id": s["id"], "prefix": prefix_len(sm), "name": s.get("name", "")})
    return out


# --- Lease-Dauer -----------------------------------------------------------------------------------

UNLIMITED = 4294967295


def lease_parts(seconds: int | None) -> tuple[int, int, int]:
    """(Tage, Stunden, Minuten) für die Eingabefelder."""
    s = int(seconds or 0)
    if s >= UNLIMITED:
        return 999, 0, 0
    return s // 86400, (s % 86400) // 3600, (s % 3600) // 60


def lease_is_unlimited(seconds: int | None) -> bool:
    return seconds is not None and int(seconds) >= 3650 * 86400
