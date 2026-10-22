"""Dekodieren und Normalisieren von DHCP-Optionswerten (ohne Oberfläche, ohne Übersetzungen)."""

from __future__ import annotations

import re

OPTION_TYPES = ["IPv4Address", "String", "Byte", "Word", "DWord", "DWordDword", "BinaryData", "EncapsulatedData",
                "IPv6Address"]
NUMERIC_MAX = {"Byte": 255, "Word": 65535, "DWord": 4294967295, "DWordDword": 18446744073709551615}
BINARY_TYPES = ("BinaryData", "EncapsulatedData")
# Standardoptionen, die auf jedem Microsoft-DHCP-Server definiert sind
STD_OPTION_IDS = set(range(1, 78)) | {81, 121, 249}

_HOSTNAME = re.compile(
    r"^(?=.{1,253}\.?$)[A-Za-z0-9_]([A-Za-z0-9_\-]{0,61}[A-Za-z0-9_])?(\.[A-Za-z0-9_]([A-Za-z0-9_\-]{0,61}[A-Za-z0-9_])?)*\.?$")


class DecodeError(ValueError):
    """Fehler beim Dekodieren; args[0] = Schlüssel für die Übersetzung, args[1] = Platzhalter."""

    def __init__(self, key: str, **params):
        super().__init__(key, params)
        self.key = key
        self.params = params


def to_number(text) -> int | None:
    t = str(text).strip()
    m = re.fullmatch(r"0x([0-9a-fA-F]+)", t)
    if m:
        return int(m.group(1), 16)
    if re.fullmatch(r"\d+", t):
        return int(t)
    return None


def to_bytes(values: list[str]) -> bytes | None:
    """Hex-Werte (0x0A1B, 0A 1B, 0a:1b, …) zu Bytes; None bei ungültiger Eingabe."""
    out = bytearray()
    for v in values:
        h = re.sub(r"[\s:\-,]", "", re.sub(r"^0x", "", str(v).strip()))
        if not re.fullmatch(r"[0-9a-fA-F]*", h):
            return None
        if len(h) % 2:
            h = "0" + h
        out += bytes.fromhex(h)
    return bytes(out)


def is_hostname(name: str) -> bool:
    return bool(_HOSTNAME.match(name or ""))


def classless_routes(data: bytes) -> list[tuple[str, int, str]]:
    """RFC 3442: [(ziel, präfix, gateway)]."""
    out = []
    i = 0
    while i < len(data):
        w = data[i]
        if w > 32:
            raise DecodeError("dec.route_prefix", width=w, pos=i)
        sig = (w + 7) // 8
        if i + 1 + sig + 4 > len(data):
            raise DecodeError("dec.route_incomplete")
        dst = list(data[i + 1:i + 1 + sig]) + [0] * (4 - sig)
        gw = data[i + 1 + sig:i + 5 + sig]
        out.append((".".join(map(str, dst)), w, ".".join(map(str, gw))))
        i += 1 + sig + 4
    return out


def tlv_items(data: bytes) -> list[tuple[int, bytes]]:
    """Suboptionen (Code, Länge, Daten); 0 = Füllbyte, 255 = Ende."""
    out = []
    i = 0
    while i < len(data):
        c = data[i]
        if c == 0:
            i += 1
            continue
        if c == 255:
            break
        if i + 1 >= len(data):
            raise DecodeError("dec.tlv_nolen", code=c)
        ln = data[i + 1]
        if i + 2 + ln > len(data):
            raise DecodeError("dec.tlv_short", code=c, length=ln, rest=len(data) - i - 2)
        out.append((c, bytes(data[i + 2:i + 2 + ln])))
        i += 2 + ln
    return out


def printable(data: bytes) -> bool:
    return all(32 <= b <= 126 for b in data)


def ip_bytes(data: bytes) -> str:
    return ", ".join(".".join(map(str, data[k:k + 4])) for k in range(0, len(data) - 3, 4))


def dns_search_list(data: bytes) -> list[str]:
    """RFC 1035-Labels (RFC 3397), Kompressionszeiger werden nicht aufgelöst."""
    names = []
    labels: list[str] = []
    i = 0
    while i < len(data):
        ln = data[i]
        if ln == 0:
            if labels:
                names.append(".".join(labels))
            labels = []
            i += 1
            continue
        if ln >= 192:
            if i + 1 >= len(data):
                raise DecodeError("dec.dns_pointer")
            labels.append("…")
            names.append(".".join(labels))
            labels = []
            i += 2
            continue
        if ln > 63:
            raise DecodeError("dec.dns_label", length=ln)
        if i + 1 + ln > len(data):
            raise DecodeError("dec.dns_long")
        labels.append(data[i + 1:i + 1 + ln].decode("ascii", errors="replace"))
        i += 1 + ln
    if labels:
        raise DecodeError("dec.dns_unterminated")
    return names


def vi_enterprises(data: bytes) -> list[int] | None:
    """RFC 3925 (Option 125): Enterprise-Nummern; None bei falschem Aufbau."""
    ents = []
    i = 0
    while i < len(data):
        if i + 5 > len(data):
            return None
        ent = int.from_bytes(data[i:i + 4], "big")
        ln = data[i + 4]
        if i + 5 + ln > len(data):
            return None
        ents.append(ent)
        i += 5 + ln
    return ents


def split_option_text(text: str, opt_def: dict | None) -> list[str]:
    """Text aus einer Tabellenzelle in Werte zerlegen (String-Optionen mit nur einem Wert bleiben ganz)."""
    if opt_def and opt_def.get("type") == "String" and not opt_def.get("multi"):
        t = (text or "").strip()
        return [t] if t else []
    return [p.strip() for p in re.split(r"[,;\r\n]", text or "") if p.strip()]


def compare_form(values: list, opt_def: dict | None) -> str:
    """Vergleichbare Darstellung (Binär als Hex, Zahlen dezimal) - für den Abgleich mit netsh-Daten."""
    vals = [str(v) for v in values or []]
    t = (opt_def or {}).get("type")
    if t in BINARY_TYPES:
        b = to_bytes(vals)
        if b is not None:
            return b.hex().upper()
    if t in NUMERIC_MAX:
        return ", ".join(str(n) if (n := to_number(v)) is not None else v for v in vals)
    return ", ".join(vals)
