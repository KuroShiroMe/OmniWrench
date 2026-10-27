"""Befunde für DHCPv6 (Scopes, Optionen, Server) – Gegenstück zu checks.Checker für IPv4.

Reine Funktionen auf normalisierten Daten (service.n_scope6 usw.), Texte über tr() (Schlüssel chk.*).
DHCPv6 unter Windows: Präfix immer /64, kein Failover, Ausschlüsse statt Adresspool.
"""

from __future__ import annotations

import ipaddress

from . import ip6calc as ip6
from . import optcodec as oc
from .checks import BP, ERROR, INFO, WARN, Finding, format_lease, option_key

DAY = 86400


def opt_name(checker, opt_id: int, vendor: str = "") -> str:
    d = checker.defs6.get((vendor or "", int(opt_id)))
    return d["name"] if d else ""


def option_values(checker, opt_id: int, values: list[str], vendor: str = "", area: str = "options",
                  fix: str | None = None, fix_arg=None, fix_label: str = "") -> list[Finding]:
    """Prüfung einer einzelnen DHCPv6-Option (Scope- oder Server-Ebene)."""
    tr = checker.tr
    opt_id = int(opt_id)
    tag = f"{opt_id:05d}" if opt_id > 999 else f"{opt_id:03d}"
    vals = [str(v) for v in values or [] if str(v).strip()]
    h: list[Finding] = []

    def add(level, text):
        h.append(Finding(level, area, text, fix=fix, fix_arg=fix_arg, fix_label=fix_label))

    d = checker.defs6.get((vendor or "", opt_id))
    if not d:
        where = tr("chk.vendor_suffix", vendor=vendor) if vendor else ""
        h.append(Finding(ERROR, area, tr("chk.undefined", tag=tag, vendor=where), fix="new_def",
                         fix_arg={"id": opt_id, "vendor": vendor, "v6": True}, fix_label=tr("fix.new_def")))
        return h
    label = tr("chk.option_label", tag=tag, name=d["name"])
    if not vals:
        add(ERROR, tr("chk.no_value", label=label))
        return h
    if d["type"] not in oc.BINARY_TYPES:
        dups = sorted({v for v in vals if vals.count(v) > 1})
        if dups:
            add(WARN, tr("chk.dup_values", label=label, values=", ".join(dups)))
    for x in checker.typed_values(d["type"], vals, bool(d.get("multi")), label, area):
        x.fix, x.fix_arg, x.fix_label = fix, fix_arg, fix_label
        h.append(x)
    if vendor:
        return h
    if d["type"] == "IPv6Address":
        for v in vals:
            try:
                a = ipaddress.IPv6Address(v.strip())
            except ValueError:
                continue
            if a.is_unspecified:
                add(WARN, tr("chk.ip_zero", label=label))
            elif a.is_loopback:
                add(WARN, tr("chk.ip_loopback", label=label, value=v))
            elif a.is_multicast:
                add(WARN, tr("chk.ip_multicast", label=label, value=v))
            elif a.is_link_local and opt_id == 23:
                add(WARN, tr("chk.o6_link_local", label=label, value=v))
    if opt_id == 24:
        for v in vals:
            if any(c.isspace() for c in v.strip()) or not oc.is_hostname(v.strip().rstrip(".")):
                add(WARN, tr("chk.o15_invalid", label=label, value=v))
    return h


def _lifetimes(checker, data: dict, add) -> None:
    tr = checker.tr
    pref, valid = data.get("lease_pref"), data.get("lease_valid")
    obj_p, obj_v = tr("obj.lease_pref"), tr("obj.lease_valid")
    if valid is not None:
        if valid <= 0:
            add(ERROR, "lease", tr("chk.s_lease_zero"), "Field:LeaseValid", obj_v)
        elif valid >= 3650 * DAY:
            add(WARN, "lease", tr("chk.s_lease_unlimited"), "Field:LeaseValid", obj_v)
        elif valid > 30 * DAY:
            add(BP, "lease", tr("chk.s_lease_long", lease=format_lease(valid, tr)), "Field:LeaseValid", obj_v)
    if pref is not None:
        if pref <= 0:
            add(ERROR, "lease", tr("chk.s6_pref_zero"), "Field:LeasePref", obj_p)
        elif pref < 3600:
            add(BP, "lease", tr("chk.s_lease_short", lease=format_lease(pref, tr)), "Field:LeasePref", obj_p)
    if pref is not None and valid is not None and 0 < valid <= pref:
        add(ERROR, "lease", tr("chk.s6_pref_valid", pref=format_lease(pref, tr), valid=format_lease(valid, tr)),
            ["Field:LeasePref", "Field:LeaseValid"], obj_p)


def scope_findings(checker, data: dict) -> list[Finding]:
    """Prüft einen DHCPv6-Scope.

    Schlüssel: id (Präfix), plen, name, state, lease_pref, lease_valid, stat, exclusions [(start, end)],
    options [{"id","values","vendor","user"}], reservations [{"ip","duid","iaid","name"}], leases [{"ip","state","host"}],
    is_tab
    """
    tr = checker.tr
    h: list[Finding] = []
    sid = str(data.get("id") or "")
    plen = int(data.get("plen") or ip6.PREFIX)
    tab = bool(data.get("is_tab"))

    def add(level, area, text, target=None, obj="", fix=None, farg=None, flabel=""):
        targets = target if isinstance(target, list) else ([target] if target else [])
        h.append(Finding(level, area, text, targets, obj, fix=fix, fix_arg=farg, fix_label=flabel))

    # --- Allgemein / Gültigkeitsdauern
    if "name" in data and not data.get("name"):
        add(ERROR, "general", tr("chk.s_no_name"), "Field:Name", tr("obj.name"))
    _lifetimes(checker, data, add)
    active = data.get("state") == "Active"
    if data.get("state") and not active:
        add(INFO, "general", tr("chk.s_inactive"), "Field:State", tr("obj.state"))

    # --- Auslastung (ein /64 läuft praktisch nie voll; nur ungenutzte Scopes melden)
    st = data.get("stat")
    if st and active and int(st.get("in_use") or 0) == 0:
        add(INFO, "usage", tr("chk.s_unused"), "Field:Stats", tr("obj.usage"))

    # --- Ausschlussbereiche
    excl = sorted((tuple(x) for x in data.get("exclusions") or []), key=lambda x: (ip6.sort_key(x[0]), ip6.sort_key(x[1])))
    for x in excl:
        key = f"Excl:{x[0]}-{x[1]}"
        obj = tr("obj.exclusion", range=ip6.fmt_range(x))
        if not (ip6.is_ipv6(x[0]) and ip6.is_ipv6(x[1])):
            continue
        if not (ip6.in_prefix(x[0], sid, plen) and ip6.in_prefix(x[1], sid, plen)):
            add(WARN, "exclusions", tr("chk.x_outside", range=ip6.fmt_range(x)), key, obj)
        elif ip6.to_int(x[0]) > ip6.to_int(x[1]):
            add(ERROR, "exclusions", tr("chk.x6_reversed", range=ip6.fmt_range(x)), key, obj)
    for k in range(1, len(excl)):
        if ip6.overlaps(excl[k - 1], excl[k]):
            add(WARN, "exclusions", tr("chk.x_overlap", a=ip6.fmt_range(excl[k - 1]), b=ip6.fmt_range(excl[k])),
                f"Excl:{excl[k][0]}-{excl[k][1]}", tr("obj.exclusions"))

    # --- Optionen
    opts = [o for o in data.get("options") or [] if o]
    for o in opts:
        oid = int(o["id"])
        vendor, user = o.get("vendor") or "", o.get("user") or ""
        key = option_key(oid, vendor, user)
        obj = tr("obj.option", tag=f"{oid:03d}", name=opt_name(checker, oid, vendor))
        fx = fa = None
        fl = ""
        if tab:
            fx, fa, fl = "edit_option", {"id": oid, "vendor": vendor, "user": user}, tr("fix.edit_option")
        for x in option_values(checker, oid, o["values"], vendor, fix=fx, fix_arg=fa, fix_label=fl):
            x.targets, x.obj = [key], obj
            h.append(x)
        if (not vendor and not user and oid in checker.server_options6
                and ",".join(map(str, o["values"])) == ",".join(map(str, checker.server_options6[oid]))):
            add(INFO, "options", tr("chk.o_redundant", obj=obj), key, obj, fx, fa, fl)
    have = {int(o["id"]) for o in opts if not o.get("vendor") and not o.get("user")} | set(checker.server_options6)
    if 23 not in have and active:
        add(BP, "options", tr("chk.o6_no_dns"), "Options", tr("obj.options"),
            "select_page" if tab else None, "Options", tr("fix.show_options"))

    # --- Reservierungen
    by_client: dict[tuple[str, int], list[str]] = {}
    for r in data.get("reservations") or []:
        rip = str(r.get("ip") or "")
        key, obj = f"Res:{rip}", tr("obj.reservation", ip=rip)
        if r.get("duid"):
            by_client.setdefault((str(r["duid"]).lower(), int(r.get("iaid") or 0)), []).append(rip)
        if not ip6.is_ipv6(rip):
            continue
        if not ip6.in_prefix(rip, sid, plen):
            add(ERROR, "reservations", tr("chk.res_outside_net", obj=obj), key, obj)
        elif ip6.host_part(rip, plen) == 0:
            add(ERROR, "reservations", tr("chk.res6_anycast", obj=obj), key, obj)
        if any(ip6.to_int(a) <= ip6.to_int(rip) <= ip6.to_int(b) for a, b in excl
               if ip6.is_ipv6(a) and ip6.is_ipv6(b)):
            add(INFO, "reservations", tr("chk.res6_excluded", obj=obj), key, obj)
        if not r.get("name"):
            add(BP, "reservations", tr("chk.res_no_name", obj=obj), key, obj)
    for (duid, iaid), ips in by_client.items():
        if len(ips) > 1:
            add(WARN, "reservations", tr("chk.res6_dup_duid", duid=duid, iaid=iaid, ips=", ".join(ips)),
                [f"Res:{x}" for x in ips], tr("obj.duid", duid=duid))

    # --- Leases
    leases = data.get("leases") or []
    declined = [x for x in leases if "declined" in str(x.get("state", "")).lower()]
    if declined:
        add(WARN, "leases", tr("chk.l_declined", n=len(declined), ips=", ".join(x["ip"] for x in declined[:6])),
            "Leases", tr("obj.leases"))
    for x in h:
        x.scope_id = sid
    return h


def server_findings(checker, info: dict, scopes: list[dict], scan_scopes: dict) -> list[Finding]:
    """Serverweite DHCPv6-Befunde. info: service.server_info6(); scopes: n_scope6-Liste; scan_scopes: id -> Scan-Daten."""
    tr = checker.tr
    h: list[Finding] = []

    def add(level, area, text, obj, sid=""):
        f = Finding(level, area, text, [f"Srv:{area}"], obj)
        f.scope_id = sid
        h.append(f)

    if info.get("error"):
        add(INFO, "scan", tr("chk.scan_unreadable", what="DHCPv6", error=info["error"]), "DHCPv6")
        return h
    b = info.get("bindings")
    if isinstance(b, list) and b and scopes:
        if not any(x.get("state") for x in b):
            add(ERROR, "bindings", tr("chk.srv6_no_binding"), tr("obj.bindings6"))
    st = info.get("settings")
    if isinstance(st, dict) and st.get("stateless") and int(st.get("purge") or 0) == 0:
        add(INFO, "server", tr("chk.srv6_stateless_purge"), tr("obj.stateless"))
    for oid in sorted(checker.server_options6):
        for x in option_values(checker, oid, checker.server_options6[oid], "", area="server_options"):
            x.targets, x.obj = ["Srv:server_options"], tr("obj.server_option6", tag=f"{oid:03d}")
            h.append(x)

    names: dict[str, list[str]] = {}
    for s in scopes:
        if s.get("name"):
            names.setdefault(s["name"], []).append(s["id"])
    for n, ids in names.items():
        if len(ids) > 1:
            add(BP, "scopes", tr("chk.srv_dup_name", name=n, ids=", ".join(ids)), tr("obj.name_q", name=n), ids[0])
    clients: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for sid, entry in scan_scopes.items():
        for r in (entry or {}).get("reservations") or []:
            if r.get("duid"):
                clients.setdefault((str(r["duid"]).lower(), int(r.get("iaid") or 0)), []).append((sid, r.get("ip", "")))
    for (duid, iaid), lst in clients.items():
        sids = sorted({x[0] for x in lst}, key=ip6.sort_key)
        if len(sids) > 1:
            add(WARN, "reservations", tr("chk.srv6_duid_multi", duid=duid, iaid=iaid,
                                         list=", ".join(f"{a} ({b})" for a, b in lst)), tr("obj.duid", duid=duid), sids[0])
    inactive = [s["id"] for s in scopes if s.get("state") != "Active"]
    if inactive:
        more = " …" if len(inactive) > 12 else ""
        add(INFO, "scopes", tr("chk.srv_inactive", n=len(inactive), list=", ".join(inactive[:12]) + more), tr("obj.inactive"))
    return h
