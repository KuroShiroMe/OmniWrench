"""Befunde (Fehler, Warnungen, Best Practice, Infos) für Zonen, Einträge, Server, Serververgleich und DHCP-Abgleich.

Reine Funktionen auf normalisierten Daten (dnsutil.Rec, Zonen-/Server-Dicts aus wmidns), damit ohne DNS-Server
testbar. Texte über tr() (Schlüssel chk.*). Gleiche Finding-Form wie im DHCP-Tool, damit die Oberflächen-
bausteine (ui_base) gleich funktionieren; scope_id ist hier der Zonenname.
"""

from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from . import dnsutil as du

ERROR, WARN, BP, INFO = "error", "warning", "bestpractice", "info"
LEVELS = (ERROR, WARN, BP, INFO)
LEVEL_ORDER = {ERROR: 0, WARN: 1, BP: 2, INFO: 3}

CATEGORIES = ("zone", "records", "cname", "targets", "ptr", "names", "aging", "security", "transfers", "server",
              "forwarders", "ns", "compare", "dhcp", "scan")

AREA_TARGETS = {"aging": "Field:Aging", "security": "Field:Update", "transfers": "Field:Transfers"}

# Typen, die neben einem CNAME stehen dürfen (DNSSEC)
CNAME_OK_WITH = {"CNAME", "RRSIG", "NSEC", "NSEC3", "KEY", "SIG"}


@dataclass
class Finding:
    level: str
    area: str
    text: str
    targets: list[str] = field(default_factory=list)
    obj: str = ""
    scope_id: str = ""          # Zone
    fix: str | None = None      # Aktions-ID (create_ptr, delete_rec, zone_settings, …)
    fix_arg: Any = None
    fix_label: str = ""
    server: str = ""

    def __post_init__(self):
        self.targets = [t for t in (self.targets or []) if t]
        if not self.targets and self.area in AREA_TARGETS:
            self.targets = [AREA_TARGETS[self.area]]


def worst(findings) -> str | None:
    best = None
    for f in findings:
        if f and (best is None or LEVEL_ORDER[f.level] < LEVEL_ORDER[best]):
            best = f.level
    return best


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (LEVEL_ORDER[f.level], CATEGORIES.index(f.area) if f.area in CATEGORIES else 99,
                                           f.scope_id, f.obj))


def rec_target(rec: du.Rec) -> str:
    return "Rec:" + rec.key


def index_by_target(findings: list[Finding]) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        for t in f.targets:
            out[t].append(f)
    return out


# --- Index über alle geladenen Zonen eines Servers ----------------------------------------------------

class Index:
    """Namen, Adressen und PTRs aller geladenen Zonen eines Servers (für zonenübergreifende Prüfungen)."""

    def __init__(self, zones: dict[str, dict], records: dict[str, list[du.Rec]]):
        self.zones = zones                         # alle Zonen des Servers (Name -> Zonen-Dict)
        self.loaded = set(records)                 # Zonen, deren Einträge geladen sind
        self.by_name: dict[str, list[du.Rec]] = defaultdict(list)
        self.by_ip: dict[str, list[du.Rec]] = defaultdict(list)
        self.ptr_by_ip: dict[str, list[du.Rec]] = defaultdict(list)
        for recs in records.values():
            for r in recs:
                self.by_name[r.name].append(r)
                if r.type in ("A", "AAAA"):
                    self.by_ip[r.ip()].append(r)
                elif r.type == "PTR":
                    ip = du.ip_from_ptr(r.name)
                    if ip:
                        self.ptr_by_ip[ip].append(r)

    def authoritative(self, name: str) -> str | None:
        """Zone dieses Servers, die für den Namen zuständig ist (Primär/Sekundär, keine Weiterleitung/Stub)."""
        z = du.best_zone(name, [n for n, zi in self.zones.items()
                                if zi.get("type") in (du.ZONE_PRIMARY, du.ZONE_SECONDARY)])
        return z

    def known(self, name: str) -> bool | None:
        """True/False wenn die zuständige Zone geladen ist, sonst None (unbekannt)."""
        z = self.authoritative(name)
        if z is None or z not in self.loaded:
            return None
        return bool(self.by_name.get(du.norm(name)))

    def addresses(self, name: str) -> list[str]:
        return [r.ip() for r in self.by_name.get(du.norm(name), []) if r.type in ("A", "AAAA")]

    def reverse_zone(self, ip: str) -> str | None:
        return du.best_zone(du.ptr_name(ip), [n for n, zi in self.zones.items() if du.is_reverse_zone(n)
                                             and zi.get("type") in (du.ZONE_PRIMARY, du.ZONE_SECONDARY)])


# --- Zone -------------------------------------------------------------------------------------------

def zone_settings_findings(z: dict, recs: list[du.Rec] | None, tr: Callable, server: dict | None = None) -> list[Finding]:
    out: list[Finding] = []
    name = z["name"]
    zt = z.get("type")

    def add(level, area, key, obj="", **kw):
        out.append(Finding(level, area, tr(f"chk.{key}", zone=name, **kw), obj=obj or name, scope_id=name,
                           server=z.get("server", "")))
    if z.get("shutdown"):
        add(ERROR, "zone", "zone_shutdown")
    if z.get("paused"):
        add(WARN, "zone", "zone_paused")
    if zt not in (du.ZONE_PRIMARY, du.ZONE_SECONDARY, du.ZONE_STUB, du.ZONE_FORWARDER):
        return out
    if zt in (du.ZONE_SECONDARY, du.ZONE_STUB, du.ZONE_FORWARDER) and not z.get("masters"):
        add(ERROR, "zone", "no_masters")
    if zt != du.ZONE_PRIMARY:
        return out
    upd = z.get("allow_update", 0)
    if upd == du.UPDATE_ANY:
        if z.get("ds"):
            add(WARN, "security", "insecure_updates_ad")
        else:
            add(BP, "security", "insecure_updates")
    sec = z.get("secure_secondaries", du.XFER_NONE)
    if sec == du.XFER_ANY:
        add(WARN, "transfers", "xfer_any")
    if sec == du.XFER_LIST and not z.get("secondaries"):
        add(WARN, "transfers", "xfer_list_empty")
    if z.get("notify") == du.NOTIFY_OFF and sec in (du.XFER_NS, du.XFER_LIST) and (z.get("secondaries") or not z.get("ds")):
        if z.get("secondaries"):
            add(BP, "transfers", "notify_off")
    if recs is None:
        return out
    dyn = [r for r in recs if r.dynamic]
    if (upd != du.UPDATE_NONE and not z.get("aging") and not du.is_reverse_zone(name) and z.get("ds")
            and not name.startswith("_msdcs.")):
        add(BP, "aging", "aging_off_dynamic" if dyn else "aging_off")
    elif dyn and not z.get("aging"):
        add(BP, "aging", "aging_off_dynamic")
    if z.get("aging") and server is not None and not server.get("scavenging_hours"):
        add(WARN, "aging", "aging_no_scavenging")
    if z.get("aging") and z.get("norefresh_h", 0) + z.get("refresh_h", 0) < 72:
        add(BP, "aging", "aging_short", hours=z.get("norefresh_h", 0) + z.get("refresh_h", 0))
    soa = next((r for r in recs if r.type == "SOA"), None)
    if soa is not None:
        d = soa.data
        if d.get("expire", 0) and d.get("refresh", 0) and d["expire"] <= d["refresh"]:
            add(BP, "zone", "soa_expire", obj="SOA")
        if d.get("retry", 0) and d.get("refresh", 0) and d["retry"] > d["refresh"]:
            add(BP, "zone", "soa_retry", obj="SOA")
        if d.get("minimum", 0) > 86400:
            add(BP, "zone", "soa_minimum", obj="SOA", ttl=du.fmt_ttl(d["minimum"]))
    elif recs:
        add(ERROR, "zone", "no_soa")
    if recs and not any(r.type == "NS" and r.name == name for r in recs):
        add(ERROR, "zone", "no_ns")
    if recs and all(r.type in ("SOA", "NS") for r in recs):
        add(INFO, "zone", "zone_empty")
    return out


def record_findings(z: dict, recs: list[du.Rec], idx: Index, tr: Callable, now: _dt.datetime | None = None,
                    server: dict | None = None) -> list[Finding]:
    """Prüfungen der Einträge einer Zone (mit Blick auf die anderen geladenen Zonen über idx)."""
    out: list[Finding] = []
    zone = z["name"]
    now = now or du.now_utc()
    reverse = du.is_reverse_zone(zone)

    def add(level, area, key, rec: du.Rec | None = None, fix=None, fix_arg=None, fix_label="", extra_targets=(), **kw):
        targets = ([rec_target(rec)] if rec else []) + list(extra_targets)
        obj = f"{rec.node} {rec.type}" if rec else ""
        out.append(Finding(level, area, tr(f"chk.{key}", zone=zone, **kw), targets=targets, obj=obj, scope_id=zone,
                           fix=fix, fix_arg=fix_arg, fix_label=tr(f"fix.{fix}") if fix and not fix_label else fix_label,
                           server=z.get("server", "")))
    by_node: dict[str, list[du.Rec]] = defaultdict(list)
    for r in recs:
        by_node[r.name].append(r)
    for name, rs in by_node.items():
        types = {r.type for r in rs}
        if "CNAME" in types:
            others = [r for r in rs if r.type not in CNAME_OK_WITH]
            if others:
                c = next(r for r in rs if r.type == "CNAME")
                add(ERROR, "cname", "cname_conflict", c, name=name, types=", ".join(sorted({r.type for r in others})))
            if len([r for r in rs if r.type == "CNAME"]) > 1:
                add(ERROR, "cname", "cname_multiple", next(r for r in rs if r.type == "CNAME"), name=name)
    aging_on = bool(z.get("aging"))
    span_h = int(z.get("norefresh_h", 0)) + int(z.get("refresh_h", 0))
    stale_cut = now - _dt.timedelta(hours=span_h or 168)
    stale_count = 0
    for r in recs:
        if r.type == "CNAME":
            tgt = r.target()
            known = idx.known(tgt)
            if known is False:
                add(ERROR, "cname", "cname_dangling", r, name=r.name, target=tgt, fix="delete_rec", fix_arg=r)
            elif known:
                nxt = [x for x in idx.by_name.get(tgt, []) if x.type == "CNAME"]
                if nxt:
                    add(BP, "cname", "cname_chain", r, name=r.name, target=tgt)
            if r.name == zone:
                add(ERROR, "cname", "cname_apex", r)
        elif r.type in ("MX", "NS", "SRV"):
            tgt = r.target()
            if not tgt or tgt == ".":
                continue
            tg = idx.by_name.get(tgt, [])
            if any(x.type == "CNAME" for x in tg):
                add(ERROR, "targets", "target_is_cname", r, name=r.name, rtype=r.type, target=tgt)
            elif idx.known(tgt) is False:
                add(ERROR if r.type in ("NS", "MX") else WARN, "targets", "target_missing", r, name=r.name,
                    rtype=r.type, target=tgt)
            elif idx.known(tgt) and not idx.addresses(tgt):
                add(WARN, "targets", "target_no_address", r, name=r.name, rtype=r.type, target=tgt)
        elif r.type in ("A", "AAAA") and not reverse:
            ip = r.ip()
            if r.type == "A" and "_" in r.node and not r.node.startswith("_"):
                add(BP, "names", "underscore", r, name=r.name)
            rz = idx.reverse_zone(ip)
            ptrs = idx.ptr_by_ip.get(ip, [])
            if rz and rz in idx.loaded and not ptrs and r.name != zone and not r.node.startswith("*"):
                add(WARN, "ptr", "a_no_ptr", r, name=r.name, ip=ip, fix="create_ptr", fix_arg=r)
            if r.dynamic and r.ts and r.ts < stale_cut:
                stale_count += 1
                if not aging_on:
                    add(INFO, "aging", "stale_record", r, name=r.name, days=(now - r.ts).days)
        elif r.type == "PTR":
            ip = du.ip_from_ptr(r.name)
            tgt = r.target()
            if ip is None:
                if reverse:
                    add(BP, "ptr", "ptr_partial", r, name=r.name)
                continue
            known = idx.known(tgt)
            if known is False:
                add(WARN, "ptr", "ptr_target_missing", r, ip=ip, target=tgt, fix="delete_rec", fix_arg=r)
            elif known and ip not in idx.addresses(tgt):
                fam = ":" in ip
                have = ", ".join(a for a in idx.addresses(tgt) if (":" in a) == fam) or "–"
                add(WARN, "ptr", "ptr_stale", r, ip=ip, target=tgt, have=have, fix="delete_rec", fix_arg=r)
            if len(idx.ptr_by_ip.get(ip, [])) > 1 and r is idx.ptr_by_ip[ip][0]:
                add(BP, "ptr", "ptr_multiple", r, ip=ip, n=len(idx.ptr_by_ip[ip]),
                    names=", ".join(x.target() for x in idx.ptr_by_ip[ip][:4]))
        if r.ttl == 0 and r.type != "SOA":
            add(BP, "records", "ttl_zero", r, name=r.name)
        if r.node.startswith("*") and r.type not in ("SOA", "NS"):
            add(INFO, "records", "wildcard", r, name=r.name)
    # gleiche Adresse auf mehreren dynamischen Namen: ältere sind meist veraltet
    if not reverse:
        seen: dict[str, list[du.Rec]] = defaultdict(list)
        for r in recs:
            if r.type in ("A", "AAAA") and r.dynamic:
                seen[r.ip()].append(r)
        for ip, rs in seen.items():
            names = {r.name for r in rs}
            if len(names) > 1:
                newest = max(rs, key=lambda x: x.ts)
                for r in rs:
                    if r.name != newest.name:
                        add(WARN, "records", "dup_ip_dynamic", r, name=r.name, ip=ip, other=newest.name,
                            fix="delete_rec", fix_arg=r)
    if aging_on and stale_count:
        out.append(Finding(INFO, "aging", tr("chk.stale_summary", zone=zone, n=stale_count), obj=zone, scope_id=zone,
                           targets=["Page:Scavenge"], server=z.get("server", "")))
    return out


def scavenge_preview(z: dict, recs: list[du.Rec], server: dict | None, now: _dt.datetime | None = None) -> list[dict]:
    """Welche Einträge würde das nächste Aufräumen löschen? [{rec, age_days, due (datetime)}] (älteste zuerst).

    Ein dynamischer Eintrag ist veraltet, wenn Zeitstempel + Nicht-Aktualisierung + Aktualisierung vorbei ist
    und die Zone frühestens ab "scavenge_after" aufgeräumt werden darf."""
    now = now or du.now_utc()
    span = _dt.timedelta(hours=int(z.get("norefresh_h", 0)) + int(z.get("refresh_h", 0)))
    out = []
    for r in recs:
        if not r.dynamic or r.type in ("SOA", "NS"):
            continue
        due = r.ts + span
        after = z.get("scavenge_after")
        if after and due < after:
            due = after
        if due <= now + _dt.timedelta(days=7):
            out.append({"rec": r, "age_days": (now - r.ts).days, "due": due, "now": due <= now})
    return sorted(out, key=lambda x: x["due"])


# --- Server -----------------------------------------------------------------------------------------

def server_findings(s: dict, zones: list[dict], tr: Callable) -> list[Finding]:
    out: list[Finding] = []
    name = s.get("name", "")

    def add(level, area, key, obj="", **kw):
        out.append(Finding(level, area, tr(f"chk.{key}", server=name, **kw), obj=obj or name, server=name,
                           targets=["Page:Server"]))
    prim = [z for z in zones if z.get("type") == du.ZONE_PRIMARY and not z.get("auto")]
    if any(z.get("aging") for z in prim) and not s.get("scavenging_hours"):
        add(WARN, "aging", "scavenging_off")
    if not s.get("secure_responses"):
        add(BP, "security", "cache_pollution")
    if not s.get("no_recursion") and not s.get("forwarders") and s.get("ds"):
        add(INFO, "forwarders", "no_forwarders")
    if s.get("forwarders") and len(s["forwarders"]) == 1:
        add(BP, "forwarders", "one_forwarder")
    if s.get("ds") and prim and not any(du.is_reverse_zone(z["name"]) for z in zones):
        add(BP, "zone", "no_reverse_zones")
    if s.get("scavenging_hours") and s["scavenging_hours"] < 24:
        add(BP, "aging", "scavenging_often", hours=s["scavenging_hours"])
    return out


def compare_findings(servers: dict[str, dict], zones: dict[str, dict[str, dict]], tr: Callable,
                     serials: dict[tuple[str, str], int | None] | None = None) -> list[Finding]:
    """Unterschiede zwischen den Servern der Sitzung (Servereinstellungen, AD-Zonen, Seriennummern)."""
    out: list[Finding] = []
    names = sorted(servers)
    if len(names) < 2:
        return out

    def add(level, key, obj, zone="", **kw):
        out.append(Finding(level, "compare", tr(f"chk.{key}", **kw), obj=obj, scope_id=zone, targets=["Page:Compare"]))
    for key in ("forwarders", "no_recursion", "secure_responses", "default_aging", "forwarding_timeout",
                "round_robin"):
        vals = {n: servers[n].get(key) for n in names}
        norm = {n: (sorted(v) if isinstance(v, list) else v) for n, v in vals.items()}
        if len({repr(v) for v in norm.values()}) > 1:
            add(WARN if key in ("forwarders", "no_recursion") else BP, "srv_diff", tr(f"srv.{key}"),
                setting=tr(f"srv.{key}"), values="; ".join(f"{n}: {fmt_value(vals[n], tr)}" for n in names))
    scav = [n for n in names if servers[n].get("scavenging_hours")]
    ds_servers = [n for n in names if servers[n].get("ds")]
    if len([n for n in scav if n in ds_servers]) > 1:
        add(BP, "scav_multiple", ", ".join(scav), servers=", ".join(scav))
    # AD-integrierte Zonen sollten auf allen DCs (gleicher Replikationsbereich) vorhanden sein
    ds_zones: dict[str, set[str]] = defaultdict(set)
    for n in ds_servers:
        for zn, zi in zones.get(n, {}).items():
            if zi.get("ds") and not zi.get("auto"):
                ds_zones[zn].add(n)
    for zn, have in sorted(ds_zones.items()):
        missing = [n for n in ds_servers if n not in have]
        if missing and len(have) >= 1 and not zn.startswith("_msdcs") and zn != "trustanchors":
            add(INFO, "zone_not_everywhere", zn, zone=zn, zone_name=zn, servers=", ".join(missing))
        settings = {n: (zones[n][zn].get("aging"), zones[n][zn].get("allow_update")) for n in have}
        if len(set(settings.values())) > 1:
            add(WARN, "zone_settings_diff", zn, zone=zn, zone_name=zn)
    if serials:
        by_zone: dict[str, dict[str, int | None]] = defaultdict(dict)
        for (srv, zn), ser in serials.items():
            by_zone[zn][srv] = ser
        for zn, per in sorted(by_zone.items()):
            vals = {v for v in per.values() if v is not None}
            if len(vals) > 1:
                add(WARN, "serial_diff", zn, zone=zn, zone_name=zn,
                    values="; ".join(f"{n}: {per[n] if per[n] is not None else '–'}" for n in sorted(per)))
    return out


def fmt_value(v, tr) -> str:
    if isinstance(v, bool):
        return tr("ui.yes") if v else tr("ui.no")
    if isinstance(v, list):
        return ", ".join(v) or "–"
    return str(v)


def ns_findings(zone: str, results: dict[str, dict], tr: Callable, server: str = "") -> list[Finding]:
    """Antworten der Namensserver einer Zone (SOA-Abfrage je NS): Erreichbarkeit, autoritativ, Seriennummer."""
    out: list[Finding] = []
    serials = {ns: r.get("serial") for ns, r in results.items() if r.get("ok") and r.get("serial") is not None}
    for ns, r in sorted(results.items()):
        if not r.get("ok"):
            out.append(Finding(WARN, "ns", tr("chk.ns_no_answer", zone=zone, ns=ns, error=r.get("error", "")), obj=ns,
                               scope_id=zone, server=server))
        elif r.get("rcode") not in ("NOERROR", None):
            out.append(Finding(ERROR, "ns", tr("chk.ns_rcode", zone=zone, ns=ns, rcode=r.get("rcode")), obj=ns,
                               scope_id=zone, server=server))
        elif not r.get("aa"):
            out.append(Finding(ERROR, "ns", tr("chk.ns_lame", zone=zone, ns=ns), obj=ns, scope_id=zone, server=server))
    if len(set(serials.values())) > 1:
        top = max(serials.values())
        behind = [f"{ns} ({s})" for ns, s in sorted(serials.items()) if s != top]
        out.append(Finding(WARN, "ns", tr("chk.ns_serial", zone=zone, serial=top, behind=", ".join(behind)), obj=zone,
                           scope_id=zone, server=server))
    return out


def forwarder_findings(server: str, results: dict[str, dict], tr: Callable) -> list[Finding]:
    out = []
    for ip, r in sorted(results.items()):
        if not r.get("ok"):
            out.append(Finding(WARN, "forwarders", tr("chk.forwarder_down", server=server, ip=ip,
                                                    error=r.get("error", "")), obj=ip, server=server,
                               targets=["Page:Server"]))
        elif r.get("ms", 0) > 500:
            out.append(Finding(BP, "forwarders", tr("chk.forwarder_slow", server=server, ip=ip, ms=r["ms"]), obj=ip,
                               server=server, targets=["Page:Server"]))
    return out


# --- DHCP-Abgleich ----------------------------------------------------------------------------------

def dhcp_findings(leases: list[dict], idx: Index, tr: Callable, server: str = "") -> list[Finding]:
    """Leases/Reservierungen eines DHCP-Servers gegen die geladenen Zonen."""
    out: list[Finding] = []
    lease_ips = {x["ip"]: x for x in leases if x.get("state") == 1 or x.get("kind") == "reservation"}
    scopes = sorted({x["scope"] for x in leases if x.get("scope")})
    for x in leases:
        if x.get("state") != 1 or not x.get("name"):
            continue
        name = x["name"]
        if "." not in name:
            continue        # Kurzname ohne Domäne: zuständige Zone unbekannt
        known = idx.known(name)
        if known is None:
            continue
        addrs = idx.addresses(name)
        zone = idx.authoritative(name) or ""
        if not addrs:
            out.append(Finding(WARN, "dhcp", tr("chk.lease_no_dns", name=name, ip=x["ip"]), obj=name, scope_id=zone,
                               server=server))
        elif x["ip"] not in addrs and ":" not in x["ip"]:
            v4 = [a for a in addrs if ":" not in a]
            if v4:
                out.append(Finding(WARN, "dhcp", tr("chk.lease_mismatch", name=name, ip=x["ip"], have=", ".join(v4)),
                                   obj=name, scope_id=zone, server=server,
                                   targets=[rec_target(r) for r in idx.by_name.get(name, []) if r.type == "A"]))
    # dynamische A-Einträge in DHCP-Netzen ohne Lease/Reservierung -> wahrscheinlich veraltet
    nets = []
    for sid in scopes:
        mask = next((x.get("mask") for x in leases if x.get("scope") == sid and x.get("mask")), None)
        nets.append((sid, mask))
    for ip, recs in idx.by_ip.items():
        if ":" in ip or ip in lease_ips:
            continue
        if not any(_in_scope(ip, sid, mask, leases) for sid, mask in nets):
            continue
        for r in recs:
            if r.dynamic:
                out.append(Finding(WARN, "dhcp", tr("chk.dns_no_lease", name=r.name, ip=ip), targets=[rec_target(r)],
                                   obj=f"{r.node} {r.type}", scope_id=r.zone, server=server, fix="delete_rec",
                                   fix_arg=r, fix_label=tr("fix.delete_rec")))
    return out


def _in_scope(ip: str, sid: str, mask, leases) -> bool:
    """Liegt ip im Scope sid? Ohne Maske: /24 um die Scope-ID (DHCP liefert sie hier nicht mit)."""
    import ipaddress
    try:
        a = ipaddress.IPv4Address(ip)
        if mask:
            return ipaddress.IPv4Network(f"{sid}/{mask}", strict=False).__contains__(a)
        return a in ipaddress.IPv4Network(f"{sid}/24", strict=False)
    except ValueError:
        return False
