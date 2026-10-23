"""Reine DNS-Hilfen ohne Serverzugriff: Namen, Reverse-Zonen (IPv4 und IPv6), Eintragsmodell, Werte prüfen.

Alles hier ist ohne Windows testbar. Ein Eintrag (Rec) ist ein normalisiertes Dict-ähnliches Objekt, wie es
backend.py aus WMI liefert und service.py/checks.py weiterverarbeiten.
"""

from __future__ import annotations

import datetime as _dt
import ipaddress
import re
from dataclasses import dataclass, field

# Eintragstypen, die das Tool bearbeiten kann (Reihenfolge = Auswahl im Dialog)
EDIT_TYPES = ("A", "AAAA", "CNAME", "PTR", "MX", "TXT", "SRV", "NS")
# Typen, die nur angezeigt werden (SOA über die Zoneneinstellungen, DNSSEC & Co. nur lesen)
TYPE_CODES = {1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 12: "PTR", 13: "HINFO", 15: "MX", 16: "TXT", 17: "RP",
              18: "AFSDB", 24: "SIG", 25: "KEY", 28: "AAAA", 33: "SRV", 35: "NAPTR", 39: "DNAME", 43: "DS",
              46: "RRSIG", 47: "NSEC", 48: "DNSKEY", 50: "NSEC3", 51: "NSEC3PARAM", 52: "TLSA", 65: "HTTPS",
              255: "ANY", 257: "CAA"}
# WMI-Klasse je Typ (MicrosoftDNS_<x>Type)
WMI_CLASSES = {"A": "AType", "AAAA": "AAAAType", "CNAME": "CNAMEType", "PTR": "PTRType", "MX": "MXType",
               "TXT": "TXTType", "SRV": "SRVType", "NS": "NSType", "SOA": "SOAType", "HINFO": "HINFOType",
               "AFSDB": "AFSDBType", "RP": "RPType", "DNAME": "DNAMEType", "KEY": "KEYType", "SIG": "SIGType",
               "WKS": "WKSType", "ATMA": "ATMAType", "WINS": "WINSType", "WINSR": "WINSRType", "MB": "MBType",
               "MD": "MDType", "MF": "MFType", "MG": "MGType", "MINFO": "MINFOType", "MR": "MRType",
               "NXT": "NXTType", "ISDN": "ISDNType", "X25": "X25Type", "RT": "RTType", "NULL": "NULLType"}

# Zonentypen (MicrosoftDNS_Zone.ZoneType) und die Werte für CreateZone
ZONE_CACHE, ZONE_PRIMARY, ZONE_SECONDARY, ZONE_STUB, ZONE_FORWARDER = 0, 1, 2, 3, 4
CREATE_TYPE = {ZONE_PRIMARY: 0, ZONE_SECONDARY: 1, ZONE_STUB: 2, ZONE_FORWARDER: 3}
ZONE_TYPE_KEYS = {ZONE_CACHE: "cache", ZONE_PRIMARY: "primary", ZONE_SECONDARY: "secondary", ZONE_STUB: "stub",
                  ZONE_FORWARDER: "forwarder"}
# AllowUpdate: 0 keine, 1 nicht sichere und sichere, 2 nur sichere
UPDATE_NONE, UPDATE_ANY, UPDATE_SECURE = 0, 1, 2
# SecureSecondaries: 0 an jeden Server, 1 nur an Namensserver, 2 nur an Liste, 3 keine Übertragung
XFER_ANY, XFER_NS, XFER_LIST, XFER_NONE = 0, 1, 2, 3
# Notify: 0 aus, 1 an Namensserver, 2 an Liste
NOTIFY_OFF, NOTIFY_NS, NOTIFY_LIST = 0, 1, 2

_EPOCH = _dt.datetime(1601, 1, 1, tzinfo=_dt.timezone.utc)
_LABEL = re.compile(r"^(?!-)[A-Za-z0-9_*-]{1,63}(?<!-)$|^\*$|^_[A-Za-z0-9-]{1,62}$")


# --- Namen -------------------------------------------------------------------------------------------

def norm(name: str) -> str:
    """Kleinbuchstaben, ohne abschließenden Punkt."""
    return (name or "").strip().rstrip(".").lower()


def fqdn(node: str, zone: str) -> str:
    """Knotenname ("@", "host", "a.b" oder schon vollqualifiziert mit Punkt) -> voller Name ohne Punkt."""
    n = (node or "").strip()
    z = norm(zone)
    if n in ("", "@"):
        return z
    if n.endswith("."):
        return norm(n)
    n = norm(n)
    if n == z or n.endswith("." + z):
        return n
    return f"{n}.{z}" if z else n


def relative(name: str, zone: str) -> str:
    """Voller Name -> Name relativ zur Zone ("@" für den Zonenkopf)."""
    n, z = norm(name), norm(zone)
    if n == z:
        return "@"
    if z and n.endswith("." + z):
        return n[: -len(z) - 1]
    return n + "."


def in_zone(name: str, zone: str) -> bool:
    n, z = norm(name), norm(zone)
    return n == z or n.endswith("." + z)


def best_zone(name: str, zones) -> str | None:
    """Längste passende Zone für einen Namen (z. B. für PTR-Ziele oder CNAME-Ziele)."""
    n = norm(name)
    best = None
    for z in zones:
        zz = norm(z)
        if (n == zz or n.endswith("." + zz)) and (best is None or len(zz) > len(best)):
            best = zz
    return best


def valid_hostname(name: str, allow_wildcard: bool = True, allow_underscore: bool = True) -> bool:
    n = (name or "").strip().rstrip(".")
    if not n or len(n) > 253:
        return False
    labels = n.split(".")
    for i, lb in enumerate(labels):
        if lb == "*" and allow_wildcard and i == 0:
            continue
        if lb.startswith("_") and not allow_underscore:
            return False
        if not _LABEL.match(lb):
            return False
    return True


# --- Reverse-Zonen -----------------------------------------------------------------------------------

def is_reverse_zone(zone: str) -> bool:
    z = norm(zone)
    return z.endswith(".in-addr.arpa") or z.endswith(".ip6.arpa") or z in ("in-addr.arpa", "ip6.arpa")


def ptr_name(ip: str) -> str:
    """IP -> Name des PTR-Eintrags (4.3.2.1.in-addr.arpa bzw. Nibbles unter ip6.arpa)."""
    return norm(ipaddress.ip_address(ip.strip()).reverse_pointer)


def ip_from_ptr(name: str) -> str | None:
    """PTR-Name -> IP (nur vollständige Namen), sonst None."""
    n = norm(name)
    try:
        if n.endswith(".in-addr.arpa"):
            parts = n[: -len(".in-addr.arpa")].split(".")
            if len(parts) != 4:
                return None
            return str(ipaddress.IPv4Address(".".join(reversed(parts))))
        if n.endswith(".ip6.arpa"):
            nib = n[: -len(".ip6.arpa")].split(".")
            if len(nib) != 32 or not all(len(x) == 1 for x in nib):
                return None
            h = "".join(reversed(nib))
            return str(ipaddress.IPv6Address(":".join(h[i:i + 4] for i in range(0, 32, 4))))
    except ValueError:
        return None
    return None


def reverse_zone_for(network: str) -> str:
    """Netz ("10.20.0.0/16", "192.168.1", "2001:db8:1::/48") -> Name der Reverse-Zone.

    IPv4 auf Oktettgrenzen (/8, /16, /24), IPv6 auf Nibble-Grenzen (Vielfache von 4)."""
    s = network.strip()
    if ":" not in s and "/" not in s:
        parts = [p for p in s.split(".") if p != ""]
        if not 1 <= len(parts) <= 3 or not all(p.isdigit() and int(p) < 256 for p in parts):
            raise ValueError(network)
        return ".".join(reversed(parts)) + ".in-addr.arpa"
    net = ipaddress.ip_network(s, strict=False)
    if net.version == 4:
        if net.prefixlen not in (8, 16, 24):
            raise ValueError(network)
        octs = str(net.network_address).split(".")[: net.prefixlen // 8]
        return ".".join(reversed(octs)) + ".in-addr.arpa"
    if net.prefixlen % 4 or not 4 <= net.prefixlen <= 124:
        raise ValueError(network)
    h = net.network_address.exploded.replace(":", "")[: net.prefixlen // 4]
    return ".".join(reversed(h)) + ".ip6.arpa"


def reverse_zone_network(zone: str) -> str:
    """Name einer Reverse-Zone -> Netz in CIDR-Schreibweise ("" wenn keine Reverse-Zone)."""
    z = norm(zone)
    try:
        if z.endswith(".in-addr.arpa"):
            parts = list(reversed(z[: -len(".in-addr.arpa")].split(".")))
            if not 1 <= len(parts) <= 4 or not all(p.isdigit() for p in parts):
                return ""
            full = parts + ["0"] * (4 - len(parts))
            return str(ipaddress.IPv4Network(f"{'.'.join(full)}/{8 * len(parts)}"))
        if z.endswith(".ip6.arpa"):
            nib = list(reversed(z[: -len(".ip6.arpa")].split(".")))
            if not nib or len(nib) > 32 or not all(len(x) == 1 for x in nib):
                return ""
            h = "".join(nib) + "0" * (32 - len(nib))
            addr = ipaddress.IPv6Address(":".join(h[i:i + 4] for i in range(0, 32, 4)))
            return str(ipaddress.IPv6Network(f"{addr}/{4 * len(nib)}"))
    except ValueError:
        return ""
    return ""


def ip_in_network(ip: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def parse_ip(text: str) -> str | None:
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


def ip_sort_key(value: str):
    try:
        a = ipaddress.ip_address(str(value).split()[0])
        return (a.version, int(a))
    except (ValueError, IndexError):
        return (9, str(value).lower())


# --- Zeitstempel -------------------------------------------------------------------------------------

def ts_from_hours(hours) -> _dt.datetime | None:
    """WMI-Timestamp (Stunden seit 1601-01-01 UTC, 0 = statisch) -> datetime (UTC) oder None."""
    try:
        h = int(hours or 0)
    except (TypeError, ValueError):
        return None
    if h <= 0:
        return None
    return _EPOCH + _dt.timedelta(hours=h)


def hours_from_ts(t: _dt.datetime | None) -> int:
    if t is None:
        return 0
    return int((t - _EPOCH).total_seconds() // 3600)


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def fmt_local(t: _dt.datetime | None) -> str:
    return t.astimezone().strftime("%Y-%m-%d %H:%M") if t else ""


def fmt_ttl(seconds: int | None) -> str:
    """3600 -> "1:00:00", 86400 -> "1d 0:00:00" (wie die DNS-Konsole, nur kompakter)."""
    if seconds is None:
        return ""
    s = int(seconds)
    d, rest = divmod(s, 86400)
    h, rest = divmod(rest, 3600)
    m, sec = divmod(rest, 60)
    core = f"{h}:{m:02d}:{sec:02d}"
    return f"{d}d {core}" if d else core


def parse_ttl(text: str) -> int:
    """"3600", "1h", "1d 2:00:00", "0:05:00", "2d", "30m" -> Sekunden. ValueError bei Unsinn."""
    t = (text or "").strip().lower()
    if not t:
        raise ValueError(text)
    if t.isdigit():
        return int(t)
    total = 0
    m = re.fullmatch(r"(?:(\d+)\s*d)?\s*(?:(\d+):(\d{1,2}):(\d{1,2}))?", t)
    if m and any(m.groups()):
        d, h, mi, s = (int(x) if x else 0 for x in m.groups())
        return d * 86400 + h * 3600 + mi * 60 + s
    for num, unit in re.findall(r"(\d+)\s*([wdhms])", t):
        total += int(num) * {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    if total or re.fullmatch(r"(\d+\s*[wdhms]\s*)+", t):
        return total
    raise ValueError(text)


# --- Eintragsmodell ----------------------------------------------------------------------------------

@dataclass
class Rec:
    zone: str                    # Zonenname (klein, ohne Punkt)
    name: str                    # voller Name (klein, ohne Punkt)
    type: str                    # "A", "AAAA", …
    data: dict = field(default_factory=dict)      # typabhängige Felder, siehe DATA_FIELDS
    ttl: int = 3600
    ts: _dt.datetime | None = None                # None = statisch
    text: str = ""               # Textdarstellung des Servers (für Löschen/Wiederherstellen)

    @property
    def node(self) -> str:
        return relative(self.name, self.zone)

    @property
    def dynamic(self) -> bool:
        return self.ts is not None

    @property
    def value(self) -> str:
        return format_value(self.type, self.data, self.text)

    @property
    def key(self) -> str:
        """Identität eines Eintrags: Name + Typ + Wert (TTL und Zeitstempel zählen nicht)."""
        return f"{self.name}|{self.type}|{value_key(self.type, self.data, self.text)}"

    def same_content(self, other: "Rec") -> bool:
        return self.key == other.key and self.ttl == other.ttl and self.dynamic == other.dynamic

    def target(self) -> str:
        """Ziel-Name bei CNAME/PTR/MX/NS/SRV, sonst ""."""
        d = self.data
        return norm(d.get("host") or "") if self.type in ("CNAME", "PTR", "MX", "NS", "SRV") else ""

    def ip(self) -> str:
        return self.data.get("ip", "") if self.type in ("A", "AAAA") else ""

    def to_dict(self) -> dict:
        return {"zone": self.zone, "name": self.name, "type": self.type, "data": dict(self.data), "ttl": self.ttl,
                "ts": self.ts.isoformat() if self.ts else None, "text": self.text}

    @classmethod
    def from_dict(cls, d: dict) -> "Rec":
        ts = d.get("ts")
        return cls(zone=norm(d.get("zone", "")), name=norm(d.get("name", "")), type=str(d.get("type", "")).upper(),
                   data=dict(d.get("data") or {}), ttl=int(d.get("ttl") or 0),
                   ts=_dt.datetime.fromisoformat(ts) if ts else None, text=d.get("text", ""))


# Felder je Typ (Schlüssel in Rec.data): für Dialoge, Prüfung und Textdarstellung
DATA_FIELDS = {
    "A": ("ip",), "AAAA": ("ip",), "CNAME": ("host",), "PTR": ("host",), "NS": ("host",),
    "MX": ("pref", "host"), "SRV": ("priority", "weight", "port", "host"), "TXT": ("text",),
}


def format_value(rtype: str, d: dict, fallback: str = "") -> str:
    t = rtype.upper()
    if t in ("A", "AAAA"):
        return d.get("ip", "")
    if t in ("CNAME", "PTR", "NS"):
        return norm(d.get("host", "")) + "."
    if t == "MX":
        return f"[{d.get('pref', 10)}] {norm(d.get('host', ''))}."
    if t == "SRV":
        return f"[{d.get('priority', 0)}] [{d.get('weight', 0)}] [{d.get('port', 0)}] {norm(d.get('host', ''))}."
    if t == "TXT":
        return d.get("text", "")
    if t == "SOA":
        return (f"[{d.get('serial', 0)}] {norm(d.get('primary', ''))}., {norm(d.get('responsible', ''))}.")
    if "raw" in d:
        return str(d["raw"])
    return _rdata_from_text(fallback)


def value_key(rtype: str, d: dict, fallback: str = "") -> str:
    t = rtype.upper()
    if t in ("A", "AAAA"):
        return parse_ip(d.get("ip", "")) or d.get("ip", "")
    if t == "SOA":
        return "soa"
    return format_value(t, d, fallback).lower()


def _rdata_from_text(text: str) -> str:
    """"host.zone IN TYPE daten" -> "daten" (für Typen ohne eigene Felder)."""
    m = re.match(r"^\S+\s+(?:\d+\s+)?IN\s+\S+\s+(.*)$", (text or "").strip(), re.I)
    return m.group(1) if m else (text or "")


def text_representation(rec: Rec, include_ttl: bool = True) -> str:
    """Textdarstellung für MicrosoftDNS_ResourceRecord.CreateInstanceFromTextRepresentation."""
    t = rec.type.upper()
    d = rec.data
    owner = rec.name
    ttl = f" {int(rec.ttl)}" if include_ttl and rec.ttl is not None else ""
    if t in ("A", "AAAA"):
        rdata = d["ip"]
    elif t in ("CNAME", "PTR", "NS"):
        rdata = norm(d["host"]) + "."
    elif t == "MX":
        rdata = f"{int(d.get('pref', 10))} {norm(d['host'])}."
    elif t == "SRV":
        rdata = f"{int(d.get('priority', 0))} {int(d.get('weight', 0))} {int(d.get('port', 0))} {norm(d['host'])}."
    elif t == "TXT":
        rdata = txt_quote(d.get("text", ""))
    elif rec.text:
        return rec.text           # unbekannter Typ: Text des Servers unverändert verwenden
    else:
        raise ValueError(t)
    return f"{owner}{ttl} IN {t} {rdata}"


def txt_quote(text: str) -> str:
    """TXT-Daten in Anführungszeichen; lange Texte in 255-Zeichen-Stücke teilen."""
    s = text if isinstance(text, str) else str(text)
    if s.startswith('"') and s.endswith('"') and len(s) > 1:
        return s
    chunks = [s[i:i + 255] for i in range(0, len(s), 255)] or [""]
    return " ".join('"' + c.replace("\\", "\\\\").replace('"', '\\"') + '"' for c in chunks)


def txt_unquote(text: str) -> str:
    s = (text or "").strip()
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', s)
    if not parts:
        return s
    return "".join(p.replace('\\"', '"').replace("\\\\", "\\") for p in parts)


def validate_data(rtype: str, d: dict, tr) -> str | None:
    """Fehlertext oder None. tr(key, **kw) liefert die Meldungstexte (val.*)."""
    t = rtype.upper()
    if t == "A":
        try:
            ipaddress.IPv4Address(str(d.get("ip", "")).strip())
        except ValueError:
            return tr("val.ipv4")
    elif t == "AAAA":
        try:
            ipaddress.IPv6Address(str(d.get("ip", "")).strip())
        except ValueError:
            return tr("val.ipv6")
    elif t in ("CNAME", "PTR", "NS", "MX", "SRV"):
        if not valid_hostname(str(d.get("host", "")), allow_wildcard=False):
            return tr("val.host")
        for k, hi in (("pref", 65535), ("priority", 65535), ("weight", 65535), ("port", 65535)):
            if k in DATA_FIELDS[t]:
                try:
                    v = int(d.get(k, 0))
                except (TypeError, ValueError):
                    return tr("val.number", field=k)
                if not 0 <= v <= hi:
                    return tr("val.number", field=k)
    elif t == "TXT":
        if not str(d.get("text", "")):
            return tr("val.txt")
    return None


def clean_data(rtype: str, d: dict) -> dict:
    """Werte normalisieren (IP-Schreibweise, Namen klein ohne Punkt, Zahlen als int)."""
    t = rtype.upper()
    out = dict(d)
    if t in ("A", "AAAA") and "ip" in out:
        out["ip"] = parse_ip(str(out["ip"])) or str(out["ip"]).strip()
    if "host" in out:
        out["host"] = norm(str(out["host"]))
    for k in ("pref", "priority", "weight", "port"):
        if k in out:
            out[k] = int(out[k])
    return out


def node_key(name: str) -> str:
    return norm(name)


def split_records(recs, rtype: str) -> list:
    return [r for r in recs if r.type == rtype]
