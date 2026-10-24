"""Optionale Prüfung „DNS-Eintrag passt?“ für Reservierungen und Leases (IPv4 und IPv6).

Nutzt nur den Resolver des Systems (socket), keine weitere Abhängigkeit und kein DNS-Tool:
Name vorwärts auflösen (A/AAAA) und Adresse rückwärts (PTR). Befunde, wenn der Name nicht auflöst,
auf eine andere Adresse zeigt oder der PTR fehlt bzw. auf einen anderen Namen zeigt.
"""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, wait

from . import optcodec as oc
from .checks import BP, INFO, WARN, Finding

THREADS = 16
TIMEOUT = 60        # Sekunden für alle Abfragen zusammen


def _forward(name: str, v6: bool) -> set[str] | None:
    """Adressen des Namens (None = löst nicht auf)."""
    try:
        infos = socket.getaddrinfo(name, None, socket.AF_INET6 if v6 else socket.AF_INET, socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return None
    return {str(ipaddress.ip_address(i[4][0].split("%")[0])) for i in infos}


def _reverse(addr: str) -> str | None:
    try:
        return socket.gethostbyaddr(addr)[0]
    except (OSError, UnicodeError):
        return None


def _same_name(a: str, b: str) -> bool:
    """Kurzname oder FQDN: gleich, wenn der kürzere ein Präfix (bis zum Punkt) des längeren ist."""
    a, b = a.lower().rstrip("."), b.lower().rstrip(".")
    if a == b:
        return True
    s, lng = (a, b) if len(a) < len(b) else (b, a)
    return "." not in s and lng.startswith(s + ".")


def candidates(scan_scopes: dict) -> list[tuple[str, str, str, str]]:
    """(Scope, Adresse, Name, Art) für Reservierungen mit Namen und aktive Leases mit Hostnamen."""
    out, seen = [], set()
    for sid, data in scan_scopes.items():
        if not data:
            continue
        for r in data.get("reservations") or []:
            name = str(r.get("name") or "").strip()
            if r.get("ip") and name and oc.is_hostname(name.rstrip(".")):
                out.append((sid, r["ip"], name, "res"))
                seen.add(r["ip"])
        for x in data.get("leases") or []:
            name = str(x.get("host") or "").strip()
            state = str(x.get("state") or "").lower()
            if (x.get("ip") and x["ip"] not in seen and name and state.startswith("active")
                    and oc.is_hostname(name.rstrip("."))):
                out.append((sid, x["ip"], name, "lease"))
    return out


def check_one(addr: str, name: str) -> tuple[str, str] | None:
    """(Schlüssel, Detail) oder None, wenn alles passt."""
    v6 = ":" in addr
    norm = str(ipaddress.ip_address(addr))
    fwd = _forward(name, v6)
    if fwd is None:
        return "chk.dns_no_name", ""
    if norm not in fwd:
        return "chk.dns_other_ip", ", ".join(sorted(fwd)[:4])
    ptr = _reverse(norm)
    if ptr is None:
        return "chk.dns_no_ptr", ""
    if not _same_name(ptr, name):
        return "chk.dns_other_ptr", ptr
    return None


LEVELS = {"chk.dns_no_name": WARN, "chk.dns_other_ip": WARN, "chk.dns_no_ptr": BP, "chk.dns_other_ptr": WARN}


def findings(scan_scopes: dict, tr, cancel=None) -> dict[str, list[Finding]]:
    """Scope-ID -> DNS-Befunde. Läuft parallel; was bis TIMEOUT nicht fertig ist, wird als Info gemeldet."""
    items = candidates(scan_scopes)
    out: dict[str, list[Finding]] = {}
    if not items:
        return out
    pool = ThreadPoolExecutor(THREADS, thread_name_prefix="DhcpExt-DNS")
    futs = {pool.submit(check_one, a, n): (sid, a, n, kind) for sid, a, n, kind in items}
    done, pending = wait(futs, TIMEOUT)
    pool.shutdown(wait=False, cancel_futures=True)
    for f in done:
        sid, a, n, kind = futs[f]
        try:
            res = f.result()
        except Exception:  # noqa: BLE001 - eine kaputte Antwort darf die Prüfung nicht abbrechen
            res = None
        if not res:
            continue
        key, detail = res
        target, obj = (f"Res:{a}", tr("obj.reservation", ip=a)) if kind == "res" else ("Leases", tr("obj.leases"))
        fd = Finding(LEVELS[key], "dns", tr(key, name=n, ip=a, detail=detail), [target], obj)
        fd.scope_id = sid
        out.setdefault(sid, []).append(fd)
    if pending and not (cancel and cancel.is_set()):
        sid = futs[next(iter(pending))][0]
        fd = Finding(INFO, "dns", tr("chk.dns_timeout", n=len(pending)), [], "DNS")
        fd.scope_id = sid
        out.setdefault(sid, []).append(fd)
    return out
