"""Befunde (Fehler, Warnungen, Best Practice, Infos) für Scopes, Optionen, Entwürfe und den Server.

Alle Prüfungen sind reine Funktionen auf normalisierten Daten (siehe service.py) und damit ohne
DHCP-Server testbar. Texte kommen über tr() aus den Sprachdateien (Schlüssel chk.*).
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any, Callable

from . import ipcalc as ip
from . import optcodec as oc

ERROR, WARN, BP, INFO = "error", "warning", "bestpractice", "info"
LEVELS = (ERROR, WARN, BP, INFO)
LEVEL_ORDER = {ERROR: 0, WARN: 1, BP: 2, INFO: 3}

CATEGORIES = ("net", "ranges", "general", "lease", "usage", "exclusions", "options", "reservations", "leases",
              "failover", "dns", "server", "server_options", "defs", "security", "database", "bindings", "scopes",
              "superscopes", "policies", "filter", "partner", "scan")

# Ein Befund ohne eigenes Ziel markiert das Feld bzw. die Seite seines Bereichs
AREA_TARGETS = {"net": "Field:Net", "ranges": "Ranges", "options": "Options", "failover": "Failover",
                "reservations": "Reservations", "exclusions": "Exclusions", "leases": "Leases",
                "usage": "Field:Stats", "lease": "Field:Lease"}


@dataclass
class Finding:
    level: str
    area: str
    text: str
    targets: list[str] = field(default_factory=list)
    obj: str = ""
    scope_id: str = ""
    fix: str | None = None      # Aktions-ID, ausgeführt vom Tab (z. B. "merge_ranges")
    fix_arg: Any = None
    fix_label: str = ""

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
    return sorted(findings, key=lambda f: (LEVEL_ORDER[f.level], CATEGORIES.index(f.area) if f.area in CATEGORIES else 99))


def option_key(opt_id, vendor="", user="") -> str:
    return f"Option:{int(opt_id)}|{vendor or ''}|{user or ''}"


def format_lease(seconds: int | None, tr: Callable) -> str:
    if seconds is None:
        return ""
    s = int(seconds)
    if s >= 3650 * 86400:
        return tr("lease.unlimited")
    d, rest = divmod(s, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    parts = []
    if d:
        parts.append(tr("lease.d", n=d))
    if h:
        parts.append(tr("lease.h", n=h))
    if m:
        parts.append(tr("lease.m", n=m))
    return " ".join(parts) if parts else tr("lease.m", n=0)


def format_duration(seconds: int | None) -> str:
    """hh:mm:ss (bei mehr als einem Tag d.hh:mm:ss) für MCLT und Intervalle."""
    s = int(seconds or 0)
    d, rest = divmod(s, 86400)
    h, rest = divmod(rest, 3600)
    m, sec = divmod(rest, 60)
    return (f"{d}." if d else "") + f"{h:02d}:{m:02d}:{sec:02d}"


def parse_duration(text: str) -> int | None:
    """hh:mm:ss oder d.hh:mm:ss -> Sekunden."""
    t = (text or "").strip()
    days = 0
    if "." in t.split(":")[0]:
        dpart, t = t.split(".", 1)
        if not dpart.isdigit():
            return None
        days = int(dpart)
    parts = t.split(":")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    while len(parts) < 3:
        parts.append("0")
    h, m, s = (int(p) for p in parts)
    if m > 59 or s > 59:
        return None
    return days * 86400 + h * 3600 + m * 60 + s


FO_STATE_KEYS = {"Normal", "CommunicationInterrupted", "PartnerDown", "PotentialConflict", "ConflictDone",
                 "ResolutionInterrupted", "Recover", "RecoverWait", "RecoverDone", "Init", "Startup", "Paused",
                 "Shutdown"}


def fo_state(state: str, tr: Callable) -> str:
    return tr("fostate." + state) if state in FO_STATE_KEYS else (state or "")


def fo_mode(rel: dict | None, tr: Callable) -> str:
    if not rel:
        return ""
    if rel.get("mode") == "LoadBalance":
        return tr("fomode.lb", pct=rel.get("lb") if rel.get("lb") is not None else 50)
    return tr("fomode.hs", role=tr("forole." + (rel.get("role") or "Active")), pct=rel.get("reserve") or 0)


class Checker:
    """Prüfungen mit dem Wissensstand des verbundenen Servers (Optionsdefinitionen, Server-Optionen, Failover)."""

    def __init__(self, tr: Callable, defs: dict | None = None, server_options: dict | None = None,
                 failovers: list | None = None):
        self.tr = tr
        self.defs = defs or {}                       # (vendor, id) -> Definition
        self.server_options = server_options or {}   # id -> [werte] (ohne Klassen)
        self.failovers = failovers or []

    def opt_def(self, opt_id: int, vendor: str = "") -> dict | None:
        return self.defs.get((vendor or "", int(opt_id)))

    def opt_name(self, opt_id: int, vendor: str = "") -> str:
        d = self.opt_def(opt_id, vendor)
        return d["name"] if d else ""

    # ----------------------------------------------------------------------------------------------
    def typed_values(self, typ: str, values: list[str], multi: bool, label: str, area: str = "options") -> list[Finding]:
        tr = self.tr
        h: list[Finding] = []
        if not multi and len(values) > 1 and typ not in oc.BINARY_TYPES:
            h.append(Finding(ERROR, area, tr("chk.single_value", label=label, n=len(values))))
        if typ in oc.NUMERIC_MAX:
            mx = oc.NUMERIC_MAX[typ]
            for v in values:
                n = oc.to_number(v)
                if n is None or n > mx:
                    h.append(Finding(ERROR, area, tr("chk.bad_number", label=label, value=v, type=typ, max=mx)))
        elif typ == "IPv4Address":
            for v in values:
                if not ip.is_ipv4(v):
                    h.append(Finding(ERROR, area, tr("chk.bad_ipv4", label=label, value=v)))
                    continue
                n = ip.ip2int(v)
                o1 = n >> 24
                if n == 0:
                    h.append(Finding(WARN, area, tr("chk.ip_zero", label=label)))
                elif n == ip.FULL32:
                    h.append(Finding(WARN, area, tr("chk.ip_broadcast", label=label)))
                elif o1 == 127:
                    h.append(Finding(WARN, area, tr("chk.ip_loopback", label=label, value=v)))
                elif 224 <= o1 <= 239:
                    h.append(Finding(WARN, area, tr("chk.ip_multicast", label=label, value=v)))
                elif v.startswith("169.254."):
                    h.append(Finding(WARN, area, tr("chk.ip_apipa", label=label, value=v)))
        elif typ == "IPv6Address":
            for v in values:
                try:
                    ok = isinstance(ipaddress.ip_address(v.strip()), ipaddress.IPv6Address)
                except ValueError:
                    ok = False
                if not ok:
                    h.append(Finding(ERROR, area, tr("chk.bad_ipv6", label=label, value=v)))
        elif typ == "String":
            for v in values:
                if len(v.encode("utf-8")) > 255:
                    h.append(Finding(ERROR, area, tr("chk.string_long", label=label)))
                if v != v.strip():
                    h.append(Finding(WARN, area, tr("chk.string_spaces", label=label)))
        elif typ in oc.BINARY_TYPES:
            if oc.to_bytes(values) is None:
                h.append(Finding(ERROR, area, tr("chk.bad_hex", label=label)))
        return h

    # ----------------------------------------------------------------------------------------------
    def option_values(self, opt_id: int, values: list[str], vendor: str = "", scope: ip.ScopeModel | None = None,
                      area: str = "options", fix: str | None = None, fix_arg=None, fix_label: str = "") -> list[Finding]:
        """Prüfung einer einzelnen Option; scope = Scope-Modell oder None (Server-Ebene)."""
        tr = self.tr
        opt_id = int(opt_id)
        tag = f"{opt_id:03d}"
        vals = [str(v) for v in values or [] if str(v).strip()]
        h: list[Finding] = []

        def add(level, text):
            h.append(Finding(level, area, text, fix=fix, fix_arg=fix_arg, fix_label=fix_label))

        if opt_id in (51, 81) and not vendor:
            return h
        d = self.opt_def(opt_id, vendor)
        if not d:
            where = tr("chk.vendor_suffix", vendor=vendor) if vendor else ""
            h.append(Finding(ERROR, area, tr("chk.undefined", tag=tag, vendor=where), fix="new_def",
                             fix_arg={"id": opt_id, "vendor": vendor}, fix_label=tr("fix.new_def")))
            return h
        label = tr("chk.option_label", tag=tag, name=d["name"])
        if not vals:
            add(ERROR, tr("chk.no_value", label=label))
            return h
        if d["type"] not in oc.BINARY_TYPES:
            dups = sorted({v for v in vals if vals.count(v) > 1})
            if dups:
                add(WARN, tr("chk.dup_values", label=label, values=", ".join(dups)))
        for x in self.typed_values(d["type"], vals, bool(d.get("multi")), label, area):
            x.fix, x.fix_arg, x.fix_label = fix, fix_arg, fix_label
            h.append(x)

        # Adressen, die im Scope-Netz liegen müssen bzw. nicht im Verteilbereich liegen sollten
        if scope and d["type"] == "IPv4Address" and not vendor and opt_id not in (1, 28):
            for v in (x for x in vals if ip.is_ipv4(x)):
                n = ip.ip2int(v)
                if n in (scope.net, scope.bc):
                    add(WARN, tr("chk.net_or_bc", label=label, value=v))
                    continue
                if opt_id in (3, 6, 42, 44, 150) and scope.contains(n) and scope.ranges and ip.in_ranges(n, scope.ranges):
                    add(WARN, tr("chk.in_pool", label=label, value=v))
        if vendor:
            return h

        first = vals[0]
        if opt_id == 1:
            add(BP, tr("chk.o1_auto", label=label))
            if scope and ip.is_ipv4(first) and ip.ip2int(first) != scope.mask:
                add(WARN, tr("chk.o1_mismatch", label=label, value=first, mask=ip.int2ip(scope.mask)))
        elif opt_id == 3 and scope:
            for v in (x for x in vals if ip.is_ipv4(x)):
                if not scope.contains(ip.ip2int(v)):
                    add(WARN, tr("chk.o3_outside", label=label, value=v, net=ip.fmt_net(scope.net, scope.prefix)))
        elif opt_id == 12:
            add(WARN, tr("chk.o12", label=label))
        elif opt_id == 15:
            if any(c.isspace() for c in first):
                add(ERROR, tr("chk.o15_space", label=label, value=first))
            elif not oc.is_hostname(first):
                add(WARN, tr("chk.o15_invalid", label=label, value=first))
            elif first.endswith("."):
                add(INFO, tr("chk.o15_dot", label=label))
            elif "." not in first:
                add(INFO, tr("chk.o15_single", label=label, value=first))
        elif opt_id == 28:
            if scope and ip.is_ipv4(first) and ip.ip2int(first) != scope.bc:
                add(WARN, tr("chk.o28", label=label, value=first, bc=ip.int2ip(scope.bc)))
        elif opt_id == 33:
            if len(vals) % 2:
                add(ERROR, tr("chk.o33_pairs", label=label))
            if any(vals[i] == "0.0.0.0" for i in range(0, len(vals), 2)):
                add(WARN, tr("chk.o33_default", label=label))
        elif opt_id == 46:
            n = oc.to_number(first)
            if n not in (1, 2, 4, 8):
                add(ERROR, tr("chk.o46", label=label))
        elif opt_id == 50:
            add(WARN, tr("chk.o50", label=label))
        elif opt_id == 54:
            add(WARN, tr("chk.o54", label=label))
        elif opt_id == 60:
            if first != first.strip():
                add(WARN, tr("chk.o60", label=label))
        elif opt_id == 66:
            if any(c.isspace() for c in first):
                add(ERROR, tr("chk.o66_space", label=label, value=first))
            elif not ip.is_ipv4(first) and not oc.is_hostname(first):
                add(WARN, tr("chk.o66_invalid", label=label, value=first))
        elif opt_id == 67:
            if any(c.isspace() for c in first):
                add(WARN, tr("chk.o67_space", label=label))
            if "\\" in first:
                add(INFO, tr("chk.o67_backslash", label=label))
        elif opt_id in (121, 249):
            b = oc.to_bytes(vals)
            if b is not None:
                try:
                    oc.classless_routes(b)
                except oc.DecodeError as e:
                    add(ERROR, tr("chk.routes_bad", label=label, error=tr(e.key, **e.params)))
        elif opt_id == 43:
            b = oc.to_bytes(vals)
            if b:
                text, err = self.option43(b)
                if err:
                    add(WARN, f"{label}: {err}")
                elif text:
                    add(INFO, f"{label}: {text}")
        elif opt_id == 119:
            b = oc.to_bytes(vals)
            if b:
                try:
                    add(INFO, tr("chk.o119_list", label=label, names=", ".join(oc.dns_search_list(b))))
                except oc.DecodeError as e:
                    add(WARN, tr("chk.o119_bad", label=label, error=tr(e.key, **e.params)))
        elif opt_id == 125:
            b = oc.to_bytes(vals)
            if b:
                ents = oc.vi_enterprises(b)
                if ents is None:
                    add(WARN, tr("chk.o125_bad", label=label))
                else:
                    add(INFO, tr("chk.o125", label=label, ents=", ".join(map(str, ents))))
        elif opt_id == 252:
            if not first.startswith(("http://", "https://")):
                add(ERROR, tr("chk.o252_scheme", label=label))
            elif not first.lower().endswith((".dat", ".pac")):
                add(INFO, tr("chk.o252_ext", label=label))
        return h

    def option43(self, data: bytes) -> tuple[str | None, str | None]:
        """Option 43: Cisco WLC (0xF1/0xF3), UniFi (Suboption 1), Text (z. B. Aruba), sonst generische Suboptionen."""
        tr = self.tr
        try:
            items = oc.tlv_items(data)
            err = None
        except oc.DecodeError as e:
            items, err = [], tr(e.key, **e.params)
        if err or not items:
            if oc.printable(data):
                return tr("chk.o43_text", text=data.decode("ascii")), None
            return None, tr("chk.o43_unreadable", error=err or "")
        parts, warn = [], []
        for code, d in items:
            if code == 241:
                if len(d) % 4:
                    warn.append(tr("chk.o43_f1_len", n=len(d)))
                else:
                    parts.append(tr("chk.o43_f1", ips=oc.ip_bytes(d)))
            elif code == 243:
                if len(d) < 5:
                    warn.append(tr("chk.o43_f3_short"))
                else:
                    mode = {1: "Meraki", 2: "Catalyst"}.get(d[-1], tr("chk.o43_mode", n=d[-1]))
                    parts.append(tr("chk.o43_f3", ips=oc.ip_bytes(d[:-1]), mode=mode))
            elif code == 1:
                parts.append(tr("chk.o43_s1_ip", ip=oc.ip_bytes(d)) if len(d) == 4 else tr("chk.o43_s1", n=len(d)))
            else:
                txt = f" '{d.decode('ascii')}'" if d and oc.printable(d) else ""
                parts.append(tr("chk.o43_sub", code=code, n=len(d), text=txt))
        return tr("chk.o43_found", parts="; ".join(parts)), (" ".join(warn) if warn else None)

    # ----------------------------------------------------------------------------------------------
    def option_set(self, options: list[dict], scope: ip.ScopeModel | None, lease: int | None,
                   area: str = "options") -> list[Finding]:
        """Prüfungen über mehrere Optionen hinweg. options: [{"id", "values", "vendor"}] ohne Benutzerklassen."""
        tr = self.tr
        h: list[Finding] = []
        ids = {int(o["id"]): list(o["values"]) for o in options if not o.get("vendor")}
        if scope:
            if 3 not in ids:
                if 3 in self.server_options:
                    h.append(Finding(INFO, area, tr("chk.set_router_server")))
                else:
                    h.append(Finding(WARN, area, tr("chk.set_no_router")))
            if 6 not in ids and 6 not in self.server_options:
                h.append(Finding(WARN, area, tr("chk.set_no_dns")))
            if 15 not in ids and 15 not in self.server_options:
                h.append(Finding(BP, area, tr("chk.set_no_domain")))
        for rid in (121, 249):
            if rid in ids:
                b = oc.to_bytes(ids[rid])
                routes = []
                if b is not None:
                    try:
                        routes = oc.classless_routes(b)
                    except oc.DecodeError:
                        routes = []
                if routes and not any(r[1] == 0 for r in routes):
                    h.append(Finding(WARN, area, tr("chk.set_routes_default", tag=f"{rid:03d}")))
        t1 = oc.to_number(ids[58][0]) if ids.get(58) else None
        t2 = oc.to_number(ids[59][0]) if ids.get(59) else None
        if t1 is not None and t2 is not None and t1 >= t2:
            h.append(Finding(WARN, area, tr("chk.set_t1_t2", t1=t1, t2=t2)))
        if lease and lease > 0:
            if t1 is not None and t1 >= lease:
                h.append(Finding(WARN, area, tr("chk.set_t1_lease", t1=t1, lease=lease)))
            if t2 is not None and t2 >= lease:
                h.append(Finding(WARN, area, tr("chk.set_t2_lease", t2=t2, lease=lease)))
        if (66 in ids) != (67 in ids):
            h.append(Finding(INFO, area, tr("chk.set_pxe")))
        return h

    # ----------------------------------------------------------------------------------------------
    def ranges(self, items: list[tuple[int, str, str]], model: ip.ScopeModel | None,
               area: str = "ranges") -> tuple[list[Finding], dict[int, int], int]:
        """Adressbereiche aus der Bereichsliste. items: [(zeile, start, ende)].

        Ergebnis: (befunde, {zeile: anzahl adressen}, summe)
        """
        tr = self.tr
        h: list[Finding] = []
        counts: dict[int, int] = {}
        total = 0
        if not items:
            h.append(Finding(ERROR, area, tr("chk.r_none"), ["Ranges"], tr("obj.ranges"), fix="whole_net",
                             fix_label=tr("fix.whole_net")))
        valid = []
        for i, (row, stext, etext) in enumerate(items, 1):
            tg = [f"Range:{row}", "Ranges"]
            obj = tr("obj.range", n=i)
            if not ip.is_ipv4(stext) or not ip.is_ipv4(etext):
                bad = stext if not ip.is_ipv4(stext) else etext
                h.append(Finding(ERROR, area, tr("chk.r_bad_ip", n=i, value=bad), tg, obj))
                continue
            s, e = ip.ip2int(stext), ip.ip2int(etext)
            if s > e:
                h.append(Finding(ERROR, area, tr("chk.r_swapped", n=i, start=stext, end=etext), tg, obj,
                                 fix="swap_range", fix_arg=row, fix_label=tr("fix.swap")))
                s, e = e, s
            if model:
                first, last = ip.int2ip(model.net + 1), ip.int2ip(model.bc - 1)
                if not model.contains(s) or not model.contains(e):
                    h.append(Finding(ERROR, area, tr("chk.r_outside", n=i, start=stext, end=etext,
                                                     net=ip.fmt_net(model.net, model.prefix), first=first, last=last),
                                     tg, obj, fix="clip_ranges", fix_label=tr("fix.clip")))
                elif s == model.net or e == model.bc:
                    h.append(Finding(ERROR, area, tr("chk.r_netbc", n=i, first=first, last=last), tg, obj,
                                     fix="clip_ranges", fix_label=tr("fix.clip")))
            valid.append((s, e, i, row))
            counts[row] = e - s + 1
            total += e - s + 1
        valid.sort()
        for k in range(1, len(valid)):
            a, b = valid[k - 1], valid[k]
            if b[0] <= a[1]:
                h.append(Finding(ERROR, area, tr("chk.r_overlap", a=a[2], b=b[2]), [f"Range:{b[3]}", f"Range:{a[3]}", "Ranges"],
                                 tr("obj.ranges_pair", a=a[2], b=b[2]), fix="merge_ranges", fix_label=tr("fix.merge")))
            elif b[0] == a[1] + 1:
                h.append(Finding(INFO, area, tr("chk.r_adjacent", a=a[2], b=b[2]), ["Ranges"],
                                 tr("obj.ranges_pair", a=a[2], b=b[2]), fix="merge_ranges", fix_label=tr("fix.merge")))
        return h, counts, total

    # ----------------------------------------------------------------------------------------------
    def scope_findings(self, data: dict) -> list[Finding]:
        """Prüft einen Scope anhand eines Daten-Dicts (aus dem Scope-Tab oder aus dem Server-Scan).

        Schlüssel: id, model, name, lease, state, start, end, res_start, res_end, exclusions [(s,e)], stat,
        dns, options [{"id","values","vendor","user"}], reservations [{"ip","cid","name","type"}],
        leases [{"ip","state","host"}], rel, unreplicated, is_tab
        """
        tr = self.tr
        h: list[Finding] = []
        m: ip.ScopeModel | None = data.get("model")
        tab = bool(data.get("is_tab"))

        def add(level, area, text, target=None, obj="", fix=None, farg=None, flabel=""):
            targets = target if isinstance(target, list) else ([target] if target else [])
            h.append(Finding(level, area, text, targets, obj, fix=fix, fix_arg=farg, fix_label=flabel))

        # --- Allgemein / Lease
        if "name" in data and not data.get("name"):
            add(ERROR, "general", tr("chk.s_no_name"), "Field:Name", tr("obj.name"))
        lease = data.get("lease")
        if lease is not None:
            if lease <= 0:
                add(ERROR, "lease", tr("chk.s_lease_zero"), "Field:Lease", tr("obj.lease"))
            elif lease >= 3650 * 86400:
                add(WARN, "lease", tr("chk.s_lease_unlimited"), "Field:Lease", tr("obj.lease"))
            elif lease > 30 * 86400:
                add(BP, "lease", tr("chk.s_lease_long", lease=format_lease(lease, tr)), "Field:Lease", tr("obj.lease"))
            elif lease < 3600:
                add(BP, "lease", tr("chk.s_lease_short", lease=format_lease(lease, tr)), "Field:Lease", tr("obj.lease"))
        active = data.get("state") == "Active"
        if data.get("state") and not active:
            add(INFO, "general", tr("chk.s_inactive"), "Field:State", tr("obj.state"))

        # --- Auslastung
        st = data.get("stat")
        if st and active:
            pct = float(st.get("pct") or 0)
            if int(st.get("free") or 0) == 0 and int(st.get("in_use") or 0) > 0:
                add(ERROR, "usage", tr("chk.s_full", in_use=st["in_use"]), "Field:Stats", tr("obj.usage"))
            elif pct >= 95:
                add(ERROR, "usage", tr("chk.s_95", pct=f"{pct:.1f}", free=st.get("free")), "Field:Stats", tr("obj.usage"))
            elif pct >= 85:
                add(WARN, "usage", tr("chk.s_85", pct=f"{pct:.1f}", free=st.get("free")), "Field:Stats", tr("obj.usage"))
            elif int(st.get("in_use") or 0) == 0:
                add(INFO, "usage", tr("chk.s_unused"), "Field:Stats", tr("obj.usage"))

        # --- Ausschlussbereiche (Serverstand)
        excl = sorted(data.get("exclusions") or [])
        if data.get("start") is not None and excl:
            for x in excl:
                key = f"Excl:{ip.int2ip(x[0])}-{ip.int2ip(x[1])}"
                if x[1] < data["start"] or x[0] > data["end"]:
                    add(WARN, "exclusions", tr("chk.x_outside", range=ip.fmt_range(x)), key,
                        tr("obj.exclusion", range=ip.fmt_range(x)))
            for k in range(1, len(excl)):
                if excl[k][0] <= excl[k - 1][1]:
                    add(WARN, "exclusions", tr("chk.x_overlap", a=ip.fmt_range(excl[k - 1]), b=ip.fmt_range(excl[k])),
                        f"Excl:{ip.int2ip(excl[k][0])}-{ip.int2ip(excl[k][1])}", tr("obj.exclusions"))
            if not tab and m and not m.ranges:
                add(ERROR, "ranges", tr("chk.x_all"), "Ranges", tr("obj.ranges"))

        # --- Optionen
        opts = [o for o in data.get("options") or [] if o]
        routers: list[str] = []
        for o in opts:
            oid = int(o["id"])
            vendor, user = o.get("vendor") or "", o.get("user") or ""
            key = option_key(oid, vendor, user)
            obj = tr("obj.option", tag=f"{oid:03d}", name=self.opt_name(oid, vendor))
            if oid == 3 and not vendor and not user:
                routers = [str(v) for v in o["values"]]
            fx = fa = None
            fl = ""
            if tab:
                fx, fa, fl = "edit_option", {"id": oid, "vendor": vendor, "user": user}, tr("fix.edit_option")
            for x in self.option_values(oid, o["values"], vendor, m, fix=fx, fix_arg=fa, fix_label=fl):
                x.targets, x.obj = [key], obj
                h.append(x)
            if (oid not in (51, 81) and not vendor and not user and oid in self.server_options
                    and ",".join(map(str, o["values"])) == ",".join(map(str, self.server_options[oid]))):
                add(INFO, "options", tr("chk.o_redundant", obj=obj), key, obj, fx, fa, fl)
        opt_set = [{"id": int(o["id"]), "values": o["values"], "vendor": o.get("vendor") or ""}
                   for o in opts if not o.get("user")]
        for x in self.option_set(opt_set, m, lease):
            x.targets = ["Options"]
            if tab:
                x.fix, x.fix_arg, x.fix_label = "select_page", "Options", tr("fix.show_options")
            h.append(x)

        # --- Reservierungen
        by_mac: dict[str, list[str]] = {}
        for r in data.get("reservations") or []:
            rip = str(r.get("ip") or "")
            key, obj = f"Res:{rip}", tr("obj.reservation", ip=rip)
            mac = ip.mac_hex(r.get("cid"))
            if mac:
                by_mac.setdefault(mac, []).append(rip)
            if not ip.is_ipv4(rip):
                continue
            n = ip.ip2int(rip)
            if m and not m.contains(n):
                add(ERROR, "reservations", tr("chk.res_outside_net", obj=obj), key, obj)
            elif data.get("res_start") is not None and not data["res_start"] <= n <= data["res_end"]:
                add(WARN, "reservations", tr("chk.res_outside_range", obj=obj, start=ip.int2ip(data["res_start"]),
                                             end=ip.int2ip(data["res_end"])), key, obj)
            if m and n in (m.net, m.bc):
                add(ERROR, "reservations", tr("chk.res_netbc", obj=obj), key, obj)
            if rip in routers:
                add(ERROR, "reservations", tr("chk.res_router", obj=obj), key, obj)
            if not r.get("name"):
                add(BP, "reservations", tr("chk.res_no_name", obj=obj), key, obj)
            if r.get("type") and str(r["type"]).lower() != "dhcp":
                add(INFO, "reservations", tr("chk.res_bootp", obj=obj, type=r["type"]), key, obj)
        for mac, ips in by_mac.items():
            if len(ips) > 1:
                add(WARN, "reservations", tr("chk.res_dup_mac", mac=ip.format_client_id(mac) or mac, ips=", ".join(ips)),
                    [f"Res:{x}" for x in ips], tr("obj.mac", mac=ip.format_client_id(mac) or mac))

        # --- Leases
        leases = data.get("leases") or []
        if leases:
            declined = [x for x in leases if "declined" in str(x.get("state", "")).lower()]
            if declined:
                add(WARN, "leases", tr("chk.l_declined", n=len(declined), ips=", ".join(x["ip"] for x in declined[:6])),
                    "Leases", tr("obj.leases"))
            for x in leases:
                if x.get("ip") in routers and str(x.get("state", "")).lower().startswith("active"):
                    add(ERROR, "leases", tr("chk.l_router", ip=x["ip"], host=x.get("host") or ""), "Leases", tr("obj.leases"))

        # --- Failover
        rel = data.get("rel")
        if not rel:
            if self.failovers:
                add(WARN, "failover", tr("chk.fo_none"), "Failover", tr("obj.failover"),
                    "add_to_fo" if tab else None, None, tr("fix.add_to_fo"))
        else:
            if rel.get("state") != "Normal":
                add(ERROR, "failover", tr("chk.fo_state", name=rel["name"], partner=rel["partner"],
                                          state=fo_state(rel.get("state", ""), tr)), "Failover",
                    tr("obj.relationship", name=rel["name"]))
            if data.get("unreplicated"):
                add(WARN, "failover", tr("chk.fo_unreplicated", partner=rel["partner"]), "Failover", tr("obj.replication"),
                    "replicate" if tab else None, None, tr("fix.replicate"))

        # --- DNS
        d = data.get("dns")
        if d:
            if d.get("dyn") == "Never":
                add(INFO, "dns", tr("chk.dns_off"), None, "DNS")
            else:
                if not d.get("delete_on_expiry"):
                    add(BP, "dns", tr("chk.dns_no_delete"), None, "DNS")
                if not d.get("name_protection"):
                    add(BP, "dns", tr("chk.dns_no_protection"), None, "DNS")
        for x in h:
            x.scope_id = str(data.get("id") or "")
        return h

    # ----------------------------------------------------------------------------------------------
    def partner_scope(self, scope: dict, data: dict, remote: dict | None, partner: str) -> list[Finding]:
        """Abweichungen eines Failover-Scopes zum Partner (jedes Element einzeln).

        scope: Scope-Zeile des Servers (n_scope), data: Scan-Daten (options, reservations, exclusions [(s,e)], lease),
        remote: Stand auf dem Partner (netsh-Dump bzw. Cmdlets, normalisiert) oder None = Scope fehlt dort.
        """
        tr = self.tr
        h: list[Finding] = []
        sid = scope.get("id") or data.get("id") or ""
        obj = tr("obj.partner", name=partner)

        def add(level, text, targets):
            f = Finding(level, "partner", text, list(targets) + ["Failover"], obj)
            f.scope_id = sid
            h.append(f)

        if not remote:
            add(ERROR, tr("chk.p_missing", partner=partner), [])
            return h
        if remote.get("mask") and remote["mask"] != scope.get("mask"):
            add(ERROR, tr("chk.p_mask", partner=partner, a=scope.get("mask"), b=remote["mask"]), [])
        for key, field_, target in (("name", "cmp.name", "Field:Name"), ("desc", "cmp.desc", "Field:Name"),
                                    ("state", "cmp.state", "Field:State")):
            a, b = str(scope.get(key) or ""), str(remote.get(key) or "")
            if a != b:
                if key == "state":
                    a, b = tr(f"state.{a}"), tr(f"state.{b}") if b else "–"
                add(WARN, tr("chk.p_field", field=tr(field_), partner=partner, a=a or "–", b=b or "–"), [target])
        a = f"{scope.get('start')} – {scope.get('end')}"
        b = f"{remote.get('start') or '?'} – {remote.get('end') or '?'}"
        if (scope.get("start"), scope.get("end")) != (remote.get("start"), remote.get("end")):
            add(ERROR, tr("chk.p_range", partner=partner, a=a, b=b), ["Ranges"])
        la, lb = data.get("lease"), remote.get("lease")
        if la is not None and lb is not None and int(la) != int(lb):
            add(WARN, tr("chk.p_field", field=tr("cmp.lease"), partner=partner, a=format_lease(la, tr), b=format_lease(lb, tr)),
                ["Field:Lease"])
        # Ausschlüsse
        lx = {(int(x[0]), int(x[1])) for x in data.get("exclusions") or []}
        rx = set()
        for x in remote.get("exclusions") or []:
            if ip.is_ipv4(x.get("start")) and ip.is_ipv4(x.get("end")):
                rx.add((ip.ip2int(x["start"]), ip.ip2int(x["end"])))
        only_l, only_r = sorted(lx - rx), sorted(rx - lx)
        if only_l:
            add(WARN, tr("chk.p_excl_local", partner=partner, list=", ".join(ip.fmt_range(x) for x in only_l)),
                [f"Excl:{ip.int2ip(x[0])}-{ip.int2ip(x[1])}" for x in only_l] + ["Exclusions"])
        if only_r:
            add(WARN, tr("chk.p_excl_partner", partner=partner, list=", ".join(ip.fmt_range(x) for x in only_r)),
                ["Exclusions"])
        # Optionen (alle Klassen; 51 = Lease-Dauer oben, 81 = DNS-Einstellung)
        def opts(lst):
            out = {}
            for o in lst or []:
                oid = int(o["id"])
                if oid in (51, 81) and not o.get("vendor") and not o.get("user"):
                    continue
                out[option_key(oid, o.get("vendor"), o.get("user"))] = (
                    oid, o.get("vendor") or "", oc.compare_form(o.get("values") or [], self.opt_def(oid, o.get("vendor") or "")))
            return out
        lo, ro = opts(data.get("options")), opts(remote.get("options"))
        for k in sorted(set(lo) | set(ro)):
            a, b = lo.get(k), ro.get(k)
            if a and b and a[2] == b[2]:
                continue
            oid, vendor = (a or b)[0], (a or b)[1]
            tag = f"{oid:03d} {self.opt_name(oid, vendor)}".strip()
            if not b:
                text = tr("chk.p_opt_missing", tag=tag, partner=partner, a=a[2])
            elif not a:
                text = tr("chk.p_opt_only", tag=tag, partner=partner, b=b[2])
            else:
                text = tr("chk.p_opt", tag=tag, partner=partner, a=a[2], b=b[2])
            add(WARN, text, [k, "Options"])
        # Reservierungen (Client-ID, Name, Typ)
        def res(lst):
            return {r["ip"]: ((ip.format_client_id(r.get("cid")) or r.get("cid") or "").lower(), r.get("name") or "")
                    for r in lst or [] if r.get("ip")}
        lr, rr = res(data.get("reservations")), res(remote.get("reservations"))
        miss = sorted((k for k in lr if k not in rr), key=ip.ip_sort_key)
        extra = sorted((k for k in rr if k not in lr), key=ip.ip_sort_key)
        diff = sorted((k for k in lr if k in rr and lr[k] != rr[k]), key=ip.ip_sort_key)

        def lst(ids):
            return ", ".join(ids[:10]) + (f" … (+{len(ids) - 10})" if len(ids) > 10 else "")
        if miss:
            add(WARN, tr("chk.p_res_missing", n=len(miss), partner=partner, list=lst(miss)),
                [f"Res:{k}" for k in miss[:50]] + ["Reservations"])
        if extra:
            add(WARN, tr("chk.p_res_only", n=len(extra), partner=partner, list=lst(extra)), ["Reservations"])
        if diff:
            add(WARN, tr("chk.p_res_diff", n=len(diff), partner=partner, list=lst(diff)),
                [f"Res:{k}" for k in diff[:50]] + ["Reservations"])
        return h

    # ----------------------------------------------------------------------------------------------
    def server_findings(self, info: dict, scopes: list[dict], scan_scopes: dict, partner_checks: list[dict]) -> list[Finding]:
        """Serverweite und scopeübergreifende Befunde.

        info: Ergebnis von service.server_info(); scopes: Scope-Liste; scan_scopes: id -> Scan-Daten (für
        Reservierungen); partner_checks: [{"partner", "error"?, "options": {id: wert}, "local_options", "defs": {...}}]
        """
        tr = self.tr
        h: list[Finding] = []

        def add(level, area, text, obj, sid=""):
            f = Finding(level, area, text, [f"Srv:{area}"], obj)
            f.scope_id = sid
            h.append(f)

        v = info.get("version")
        if isinstance(v, dict):
            mj, mn = int(v.get("major") or 0), int(v.get("minor") or 0)
            if mj < 6 or (mj == 6 and mn < 3):
                add(BP, "server", tr("chk.srv_version", ver=f"{mj}.{mn}"), tr("obj.version"))
        elif info.get("version_error"):
            add(INFO, "scan", tr("chk.scan_unreadable", what=tr("obj.version"), error=info["version_error"]), tr("obj.version"))

        st = info.get("settings")
        if isinstance(st, dict):
            if st.get("domain_joined") and not st.get("authorized"):
                add(ERROR, "server", tr("chk.srv_unauthorized"), tr("obj.authorization"))
            if st.get("nap"):
                add(BP, "server", tr("chk.srv_nap"), "NAP")
            cd = int(st.get("conflict_attempts") or 0)
            if cd > 2:
                add(WARN, "server", tr("chk.srv_conflict_high", n=cd), tr("obj.conflict"))
            elif cd > 0:
                add(INFO, "server", tr("chk.srv_conflict", n=cd), tr("obj.conflict"))
            if st.get("dynamic_bootp"):
                add(INFO, "server", tr("chk.srv_bootp"), "BOOTP")
        elif info.get("settings_error"):
            add(INFO, "scan", tr("chk.scan_unreadable", what=tr("obj.settings"), error=info["settings_error"]), tr("obj.settings"))

        a = info.get("audit")
        if isinstance(a, dict):
            if not a.get("enabled"):
                add(BP, "security", tr("chk.srv_audit"), tr("obj.audit"))
        elif info.get("audit_error"):
            add(INFO, "scan", tr("chk.scan_unreadable", what=tr("obj.audit"), error=info["audit_error"]), tr("obj.audit"))

        db = info.get("database")
        if isinstance(db, dict):
            if not db.get("logging"):
                add(WARN, "database", tr("chk.srv_db_logging"), tr("obj.database"))
            if int(db.get("backup_interval") or 0) > 1440:
                add(WARN, "database", tr("chk.srv_db_interval", n=int(db["backup_interval"])), tr("obj.backup"))
            r1, r2 = _drive(db.get("file")), _drive(db.get("backup_path"))
            if r1 and r1 == r2:
                add(BP, "database", tr("chk.srv_db_same_drive", drive=r1), tr("obj.backup"))
        elif info.get("database_error"):
            add(INFO, "scan", tr("chk.scan_unreadable", what=tr("obj.database"), error=info["database_error"]), tr("obj.database"))

        dns = info.get("dns")
        if isinstance(dns, dict):
            if dns.get("dyn") == "Never":
                add(INFO, "dns", tr("chk.srv_dns_off"), tr("obj.dns_server"))
            else:
                if not dns.get("delete_on_expiry"):
                    add(BP, "dns", tr("chk.srv_dns_no_delete"), tr("obj.dns_server"))
                if not dns.get("name_protection"):
                    add(BP, "dns", tr("chk.srv_dns_no_protection"), tr("obj.dns_server"))
                if info.get("dns_credential_user") == "":
                    add(BP, "security", tr("chk.srv_dns_cred"), tr("obj.dns_credential"))

        b = info.get("bindings")
        if isinstance(b, list) and b:
            on = [x for x in b if x.get("state")]
            if not on:
                add(ERROR, "bindings", tr("chk.srv_no_binding"), tr("obj.bindings"))
            elif len(on) > 1:
                add(INFO, "bindings", tr("chk.srv_bindings", n=len(on),
                                         list=", ".join(f"{x.get('alias')} ({x.get('ip')})" for x in on)), tr("obj.bindings"))

        # Server-Optionen
        for oid in sorted(self.server_options):
            for x in self.option_values(oid, self.server_options[oid], "", None, area="server_options"):
                x.targets, x.obj = ["Srv:server_options"], tr("obj.server_option", tag=f"{oid:03d}")
                h.append(x)
        if 3 in self.server_options:
            add(WARN, "server_options", tr("chk.srv_o3"), tr("obj.server_option", tag="003"))

        # Failover
        all_ids = [s["id"] for s in scopes]
        in_fo = {sid for r in self.failovers for sid in r.get("scopes") or []}
        for r in self.failovers:
            o = tr("obj.relationship", name=r["name"])
            if r.get("state") != "Normal":
                add(ERROR, "failover", tr("chk.srv_fo_state", obj=o, partner=r["partner"], state=fo_state(r.get("state", ""), tr)), o)
            if not r.get("auth"):
                add(BP, "security", tr("chk.srv_fo_auth", obj=o), o)
            if not r.get("auto"):
                add(BP, "failover", tr("chk.srv_fo_auto", obj=o), o)
            if r.get("mclt"):
                mc = int(r["mclt"])
                if mc < 15 * 60 or mc > 24 * 3600:
                    add(INFO, "failover", tr("chk.srv_fo_mclt", obj=o, mclt=format_duration(mc)), o)
            if r.get("mode") == "LoadBalance":
                if r.get("lb") is not None and int(r["lb"]) != 50:
                    add(INFO, "failover", tr("chk.srv_fo_lb", obj=o, a=r["lb"], b=100 - int(r["lb"])), o)
            elif r.get("reserve") is not None and int(r["reserve"]) == 0:
                add(WARN, "failover", tr("chk.srv_fo_reserve", obj=o), o)
        if self.failovers:
            nf = [x for x in all_ids if x not in in_fo]
            if nf:
                more = " …" if len(nf) > 12 else ""
                add(WARN, "failover", tr("chk.srv_fo_missing", n=len(nf), total=len(all_ids), list=", ".join(nf[:12]) + more),
                    tr("obj.scopes_without_fo"))

        # Abgleich mit den Failover-Partnern
        for pc in partner_checks:
            pn = pc["partner"]
            if pc.get("error"):
                add(INFO if pc.get("primary_only") else WARN, "failover", tr("chk.srv_partner_err", partner=pn, error=pc["error"]),
                    tr("obj.partner", name=pn))
                continue
            if pc.get("options_error"):
                add(INFO, "scan", tr("chk.srv_partner_opts_err", partner=pn, error=pc["options_error"]), tr("obj.partner", name=pn))
            else:
                lo, ro = pc.get("local_options") or {}, pc.get("options") or {}
                for k in sorted(set(lo) | set(ro)):
                    va, vb = lo.get(k, "–"), ro.get(k, "–")
                    if va != vb:
                        key = "chk.srv_partner_opt_only" if k not in lo else "chk.srv_partner_opt_missing" if k not in ro \
                            else "chk.srv_partner_opt"
                        add(WARN, "server_options", tr(key, tag=f"{k:03d}", partner=pn, a=va, b=vb),
                            tr("obj.server_option", tag=f"{k:03d}"))
            if pc.get("defs_error"):
                add(INFO, "scan", tr("chk.srv_partner_defs_err", partner=pn, error=pc["defs_error"]), tr("obj.partner", name=pn))
            else:
                rd = pc.get("defs") or {}
                for key, d in self.defs.items():
                    if key not in rd:
                        vend = f" [{d['vendor']}]" if d.get("vendor") else ""
                        add(WARN, "defs", tr("chk.srv_def_missing", tag=f"{d['id']:03d}", name=d["name"], vendor=vend, partner=pn),
                            tr("obj.definition", tag=f"{d['id']:03d}"))
                    elif d.get("type") and rd[key].get("type") and d["type"] != rd[key]["type"]:
                        add(WARN, "defs", tr("chk.p_def_type", tag=f"{d['id']:03d}", name=d["name"], partner=pn,
                                             a=d["type"], b=rd[key]["type"]), tr("obj.definition", tag=f"{d['id']:03d}"))
                for key, d in rd.items():
                    if key not in self.defs:
                        add(INFO, "defs", tr("chk.srv_def_only_partner", tag=f"{d['id']:03d}", name=d["name"], partner=pn),
                            tr("obj.definition", tag=f"{d['id']:03d}"))
            # Benutzer-/Herstellerklassen
            if pc.get("classes_error"):
                add(INFO, "scan", tr("chk.p_classes_err", partner=pn, error=pc["classes_error"]), tr("obj.partner", name=pn))
            elif pc.get("classes") is not None and pc.get("local_classes") is not None:
                lc, rc = pc["local_classes"], pc["classes"]
                for n in sorted(lc - rc):
                    add(WARN, "partner", tr("chk.p_class_missing", name=n, partner=pn), tr("obj.partner", name=pn))
                for n in sorted(rc - lc):
                    add(INFO, "partner", tr("chk.p_class_only", name=n, partner=pn), tr("obj.partner", name=pn))
            # Failover-Beziehungen aus Sicht des Partners
            if pc.get("scopes_error"):
                add(INFO, "scan", tr("chk.p_scopes_err", partner=pn, error=pc["scopes_error"]), tr("obj.partner", name=pn))
            if pc.get("fo_error"):
                add(INFO, "scan", tr("chk.p_fo_err", partner=pn, error=pc["fo_error"]), tr("obj.partner", name=pn))
            elif pc.get("fo") is not None:
                theirs = {r["name"]: r for r in pc["fo"]}
                for r in self.failovers:
                    if (r.get("partner") or "").lower() != pn.lower():
                        continue
                    o = tr("obj.relationship", name=r["name"])
                    p = theirs.get(r["name"])
                    if not p:
                        add(ERROR, "partner", tr("chk.p_rel_missing", name=r["name"], partner=pn), o)
                        continue
                    if p.get("mode") != r.get("mode"):
                        add(ERROR, "partner", tr("chk.p_rel_field", name=r["name"], partner=pn, field=tr("fo.f.mode"),
                                                 a=fo_mode(r, tr), b=fo_mode(p, tr)), o)
                    elif r.get("mode") == "LoadBalance" and r.get("lb") is not None and p.get("lb") is not None \
                            and int(r["lb"]) + int(p["lb"]) != 100:
                        add(WARN, "partner", tr("chk.p_rel_lb", name=r["name"], partner=pn, a=r["lb"], b=p["lb"]), o)
                    elif r.get("mode") != "LoadBalance" and r.get("reserve") is not None and p.get("reserve") is not None \
                            and int(r["reserve"]) != int(p["reserve"]):
                        add(WARN, "partner", tr("chk.p_rel_field", name=r["name"], partner=pn, field=tr("p.reserve"),
                                                 a=f"{r['reserve']} %", b=f"{p['reserve']} %"), o)
                    if r.get("mclt") is not None and p.get("mclt") is not None and int(r["mclt"]) != int(p["mclt"]):
                        add(WARN, "partner", tr("chk.p_rel_field", name=r["name"], partner=pn, field="MCLT",
                                                 a=format_duration(r["mclt"]), b=format_duration(p["mclt"])), o)
                    if bool(r.get("auth")) != bool(p.get("auth")):
                        add(WARN, "partner", tr("chk.p_rel_field", name=r["name"], partner=pn, field=tr("p.auth"),
                                                 a=tr("p.on" if r.get("auth") else "p.off"),
                                                 b=tr("p.on" if p.get("auth") else "p.off")), o)
                    ls, rs = set(r.get("scopes") or []), set(p.get("scopes") or [])
                    only_l = sorted(ls - rs, key=ip.ip_sort_key)
                    only_r = sorted(rs - ls, key=ip.ip_sort_key)
                    if only_l:
                        add(ERROR, "partner", tr("chk.p_rel_scopes_local", name=r["name"], partner=pn, list=", ".join(only_l)),
                            o, only_l[0])
                    if only_r:
                        add(WARN, "partner", tr("chk.p_rel_scopes_partner", name=r["name"], partner=pn, list=", ".join(only_r)), o)

        # Scope-übergreifend
        names: dict[str, list[str]] = {}
        for s in scopes:
            if s.get("name"):
                names.setdefault(s["name"], []).append(s["id"])
        for n, ids in names.items():
            if len(ids) > 1:
                add(BP, "scopes", tr("chk.srv_dup_name", name=n, ids=", ".join(ids)), tr("obj.name_q", name=n), ids[0])
        nets = []
        for s in scopes:
            sm = ip.ip2int(s["mask"])
            b1 = ip.ip2int(s["id"]) & sm
            nets.append((s["id"], b1, b1 | (ip.FULL32 ^ sm)))
        for i in range(len(nets)):
            for j in range(i + 1, len(nets)):
                if nets[i][1] <= nets[j][2] and nets[j][1] <= nets[i][2]:
                    add(ERROR, "scopes", tr("chk.srv_overlap", a=nets[i][0], b=nets[j][0]), tr("obj.overlap"), nets[i][0])
        macs: dict[str, list[tuple[str, str]]] = {}
        for sid, entry in scan_scopes.items():
            for r in (entry or {}).get("reservations") or []:
                mac = ip.mac_hex(r.get("cid"))
                if mac:
                    macs.setdefault(mac, []).append((sid, r.get("ip", "")))
        for mac, lst in macs.items():
            sids = sorted({x[0] for x in lst}, key=ip.ip_sort_key)
            if len(sids) > 1:
                fm = ip.format_client_id(mac) or mac
                add(WARN, "reservations", tr("chk.srv_mac_multi", mac=fm, list=", ".join(f"{a} ({b})" for a, b in lst)),
                    tr("obj.mac", mac=fm), sids[0])
        inactive = [s["id"] for s in scopes if s.get("state") != "Active"]
        if inactive:
            more = " …" if len(inactive) > 12 else ""
            add(INFO, "scopes", tr("chk.srv_inactive", n=len(inactive), list=", ".join(inactive[:12]) + more), tr("obj.inactive"))
        for sname, count in (info.get("superscopes") or {}).items():
            if count <= 1:
                add(INFO, "superscopes", tr("chk.srv_superscope", name=sname, n=count), tr("obj.superscope", name=sname))
        for pname in info.get("disabled_policies") or []:
            add(INFO, "policies", tr("chk.srv_policy", name=pname), tr("obj.policy", name=pname))
        fl = info.get("filters")
        if isinstance(fl, dict):
            if fl.get("allow"):
                n = int(fl.get("allow_count") or 0)
                if n == 0:
                    add(ERROR, "filter", tr("chk.srv_allow_empty"), tr("obj.allow_filter"))
                else:
                    add(INFO, "filter", tr("chk.srv_allow", n=n), tr("obj.allow_filter"))
            if fl.get("deny"):
                add(INFO, "filter", tr("chk.srv_deny"), tr("obj.deny_filter"))
        return h


def _drive(path) -> str:
    p = str(path or "")
    if len(p) >= 2 and p[1] == ":":
        return p[:2].upper() + "\\"
    if p.startswith("\\\\"):
        parts = p.split("\\")
        return "\\\\" + "\\".join(parts[2:4]) if len(parts) >= 4 else ""
    return ""
