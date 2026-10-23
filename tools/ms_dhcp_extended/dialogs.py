"""Eingabedialoge von MS DHCP Extended Management (Option, Reservierung, Ausschluss, Failover, Definition, Anmeldung,
DHCPv6-Scope)."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QCheckBox, QMessageBox

from . import checks as ck
from . import checks6 as ck6
from . import ip6calc as ip6
from . import ipcalc as ip
from . import optcodec as oc
from .ui_base import FormDialog, confirm


def _opt_id(v) -> int | None:
    m = re.match(r"\s*(\d+)", str(v if v is not None else ""))
    return int(m.group(1)) if m else None


def option_dialog(parent, tr, checker: ck.Checker, defs: dict, opt: dict | None = None, model: ip.ScopeModel | None = None,
                  vendors: list[str] = (), users: list[str] = (), title: str = "", partner_check: str = "",
                  v6: bool = False) -> dict | None:
    """Option anlegen/bearbeiten. Ergebnis: {"id", "values", "vendor", "user", "undefined", "partner"}.
    partner_check: Beschriftung des Hakens „Auf Partner übertragen“ (Opt-out, vorausgewählt); leer = kein Haken.
    v6: DHCPv6-Option (Code 1–65535, Prüfung nach checks6)."""
    std = sorted((d for (v, _i), d in defs.items() if not v), key=lambda d: d["id"])
    items = [(d["id"], f"{d['id']:03d} – {d['name']}") for d in std]
    edit = opt is not None
    vend_items = [("", tr("opt.no_class"))] + [(v, v) for v in vendors]
    user_items = [("", tr("opt.no_class"))] + [(u, u) for u in users]
    fields = [
        {"key": "id", "label": tr("opt.f.id"), "type": "combo", "items": items, "editable": True,
         "value": opt["id"] if edit else None, "readonly": edit},
        {"key": "vendor", "label": tr("opt.f.vendor"), "type": "combo", "items": vend_items,
         "value": (opt or {}).get("vendor", ""), "readonly": edit},
        {"key": "user", "label": tr("opt.f.user"), "type": "combo", "items": user_items,
         "value": (opt or {}).get("user", ""), "readonly": edit},
        {"key": "values", "label": tr("opt.f.values"), "type": "multiline", "value": "\n".join((opt or {}).get("values") or [])},
    ]
    if partner_check:
        fields.append({"key": "partner", "label": partner_check, "type": "check", "value": True})
    state: dict = {}

    def validate(v: dict) -> str | None:
        oid = _opt_id(v["id"])
        if oid is None or not 1 <= oid <= (65535 if v6 else 254):
            return tr("opt.err_id6" if v6 else "opt.err_id")
        if oid == 51 and not v["vendor"] and not v6:
            return tr("opt.err_51")
        d = defs.get((v["vendor"] or "", oid))
        vals = oc.split_option_text(v["values"], d)
        if not vals:
            return tr("opt.err_empty")
        if not d:
            state.update(id=oid, values=vals, undefined=True)
            return None
        fs = ck6.option_values(checker, oid, vals, v["vendor"] or "") if v6 else \
            checker.option_values(oid, vals, v["vendor"] or "", model)
        fs = [f for f in fs if f.fix != "new_def"]
        errs = [f.text for f in fs if f.level == ck.ERROR]
        if errs:
            return "\n".join(errs)
        warns = [f.text for f in fs if f.level == ck.WARN]
        if warns and not confirm(parent, tr("opt.title_check"), tr("opt.confirm_warn", list="\n".join("• " + w for w in warns))):
            return tr("opt.err_cancelled")
        state.update(id=oid, values=vals, undefined=False)
        return None

    res = FormDialog.ask(parent, title or (tr("opt.title_edit") if edit else tr("opt.title_add")), fields, tr,
                         hint=tr("opt.hint"), validate=validate, width=620)
    if res is None:
        return None
    return {"id": state["id"], "values": state["values"], "vendor": res["vendor"] or "", "user": res["user"] or "",
            "undefined": state.get("undefined", False), "partner": bool(res.get("partner"))}


def confirm_check(parent, title: str, text: str, check_label: str = "", checked: bool = True) -> tuple[bool, bool]:
    """Ja/Nein-Rückfrage mit optionalem Haken (z. B. „Auch auf dem Partner entfernen“). Ergebnis: (ja, Haken)."""
    b = QMessageBox.StandardButton
    box = QMessageBox(QMessageBox.Icon.Question, title, text, b.Yes | b.No, parent)
    box.setDefaultButton(b.No)
    cb = None
    if check_label:
        cb = QCheckBox(check_label, box)     # Elternteil box: sonst gibt Python den Haken frei, solange box ihn noch hält
        cb.setChecked(checked)
        box.setCheckBox(cb)
    ok = box.exec() == b.Yes
    on = bool(ok and cb is not None and cb.isChecked())
    box.deleteLater()
    return ok, on


def guess_type(values: list[str]) -> str:
    if values and all(ip.is_ipv4(v) for v in values):
        return "IPv4Address"
    if values and all(ip6.is_ipv6(v) for v in values):
        return "IPv6Address"
    if values and all(oc.to_number(v) is not None for v in values):
        mx = max(oc.to_number(v) for v in values)
        return "Byte" if mx <= 255 else "Word" if mx <= 65535 else "DWord"
    return "String"


def definition_dialog(parent, tr, d: dict | None = None, vendors: list[str] = (), with_partner: bool = False,
                      preset: dict | None = None, v6: bool = False) -> dict | None:
    edit = d is not None
    base = d or preset or {}
    fields = [
        {"key": "id", "label": tr("def.f.id"), "type": "number", "min": 1, "max": 65535 if v6 else 255,
         "value": base.get("id", 224), "readonly": edit},
        {"key": "name", "label": tr("def.f.name"), "value": base.get("name", "")},
        {"key": "type", "label": tr("def.f.type"), "type": "combo", "items": oc.OPTION_TYPES if v6 else oc.OPTION_TYPES[:-1],
         "value": base.get("type", "String"), "readonly": edit},
        {"key": "multi", "label": tr("def.f.multi"), "type": "check", "value": base.get("multi", False), "readonly": edit},
        {"key": "vendor", "label": tr("def.f.vendor"), "type": "combo",
         "items": [("", tr("opt.no_class"))] + [(v, v) for v in vendors], "value": base.get("vendor", ""), "readonly": edit},
        {"key": "desc", "label": tr("def.f.desc"), "value": base.get("desc", "")},
        {"key": "default", "label": tr("def.f.default"), "type": "multiline", "value": "\n".join(base.get("default") or [])},
    ]
    if with_partner:
        fields.append({"key": "partner", "label": tr("def.f.partner"), "type": "check", "value": True})

    def validate(v):
        if not v["name"].strip():
            return tr("def.err_name")
        return None

    title = tr("def.title_edit") if edit else tr("def.title_add")
    res = FormDialog.ask(parent, title + (" (DHCPv6)" if v6 else ""), fields, tr, validate=validate)
    if res is None:
        return None
    res["default"] = [x.strip() for x in res["default"].splitlines() if x.strip()]
    res["id"] = int(res["id"])
    res["vendor"] = res["vendor"] or ""
    return res


def reservation_dialog(parent, tr, model: ip.ScopeModel, r: dict | None = None) -> dict | None:
    edit = r is not None
    pre = ""
    if not edit and model.prefix >= 24:
        pre = ".".join(ip.int2ip(model.net).split(".")[:3]) + "."
    fields = [
        {"key": "ip", "label": tr("res.f.ip"), "value": r["ip"] if edit else pre, "readonly": edit},
        {"key": "cid", "label": tr("res.f.mac"), "value": (r or {}).get("cid", "")},
        {"key": "name", "label": tr("res.f.name"), "value": (r or {}).get("name", "")},
        {"key": "desc", "label": tr("res.f.desc"), "value": (r or {}).get("desc", "")},
        {"key": "type", "label": tr("res.f.type"), "type": "combo",
         "items": [("Dhcp", "DHCP"), ("Bootp", "BOOTP"), ("Both", tr("res.type_both"))], "value": (r or {}).get("type", "Dhcp")},
    ]

    def validate(v):
        if not ip.is_ipv4(v["ip"]):
            return tr("res.err_ip")
        n = ip.ip2int(v["ip"])
        if not model.contains(n):
            return tr("res.err_outside", net=ip.fmt_net(model.net, model.prefix))
        if n in (model.net, model.bc):
            return tr("res.err_netbc")
        if not ip.format_client_id(v["cid"]):
            return tr("res.err_mac")
        return None

    res = FormDialog.ask(parent, tr("res.title_edit") if edit else tr("res.title_add"), fields, tr, validate=validate)
    if res:
        res["cid"] = ip.format_client_id(res["cid"])
    return res


def exclusion_dialog(parent, tr, model: ip.ScopeModel) -> tuple[str, str] | None:
    pre = ".".join(ip.int2ip(model.net).split(".")[:3]) + "." if model.prefix >= 24 else ""
    fields = [{"key": "start", "label": tr("excl.f.start"), "value": pre},
              {"key": "end", "label": tr("excl.f.end"), "value": pre}]

    def validate(v):
        for k in ("start", "end"):
            if not ip.is_ipv4(v[k]):
                return tr("excl.err_ip", value=v[k])
            if not model.contains(ip.ip2int(v[k])):
                return tr("excl.err_outside", value=v[k], net=ip.fmt_net(model.net, model.prefix))
        if ip.ip2int(v["start"]) > ip.ip2int(v["end"]):
            return tr("excl.err_order")
        return None

    res = FormDialog.ask(parent, tr("excl.title"), fields, tr, validate=validate)
    return (res["start"], res["end"]) if res else None


# --- DHCPv6 -------------------------------------------------------------------------------------------

def reservation6_dialog(parent, tr, prefix: str, plen: int, r: dict | None = None) -> dict | None:
    """DHCPv6-Reservierung: Adresse + DUID + IAID (der Client wird über DUID und IAID erkannt, nicht über die MAC)."""
    edit = r is not None
    fields = [
        {"key": "ip", "label": tr("res.f.ip"), "value": r["ip"] if edit else prefix, "readonly": edit},
        {"key": "duid", "label": tr("res6.f.duid"), "value": (r or {}).get("duid", "")},
        {"key": "iaid", "label": tr("res6.f.iaid"), "value": str((r or {}).get("iaid", "") or "")},
        {"key": "name", "label": tr("res.f.name"), "value": (r or {}).get("name", "")},
        {"key": "desc", "label": tr("res.f.desc"), "value": (r or {}).get("desc", "")},
    ]

    def validate(v):
        if not ip6.is_ipv6(v["ip"]):
            return tr("res6.err_ip")
        if not ip6.in_prefix(v["ip"], prefix, plen):
            return tr("res.err_outside", net=ip6.fmt_net(prefix, plen))
        if ip6.host_part(v["ip"], plen) == 0:
            return tr("res6.err_anycast")
        if not ip6.format_duid(v["duid"]):
            return tr("res6.err_duid")
        t = v["iaid"].strip()
        n = int(t, 16) if t.lower().startswith("0x") and len(t) > 2 else int(t) if t.isdigit() else -1
        if not 0 <= n <= 0xFFFFFFFF:
            return tr("res6.err_iaid")
        return None

    res = FormDialog.ask(parent, tr("res.title_edit") if edit else tr("res.title_add"), fields, tr,
                         hint=tr("res6.hint"), validate=validate)
    if res:
        t = res["iaid"].strip()
        res["iaid"] = int(t, 16) if t.lower().startswith("0x") else int(t)
        res["ip"] = ip6.norm(res["ip"])
        res["duid"] = ip6.format_duid(res["duid"])
    return res


def exclusion6_dialog(parent, tr, prefix: str, plen: int) -> tuple[str, str] | None:
    fields = [{"key": "start", "label": tr("excl.f.start"), "value": prefix},
              {"key": "end", "label": tr("excl.f.end"), "value": prefix}]

    def validate(v):
        for k in ("start", "end"):
            if not ip6.is_ipv6(v[k]):
                return tr("excl.err_ip", value=v[k])
            if not ip6.in_prefix(v[k], prefix, plen):
                return tr("excl.err_outside", value=v[k], net=ip6.fmt_net(prefix, plen))
        if ip6.to_int(v["start"]) > ip6.to_int(v["end"]):
            return tr("excl.err_order")
        return None

    res = FormDialog.ask(parent, tr("excl.title"), fields, tr, validate=validate)
    return (ip6.norm(res["start"]), ip6.norm(res["end"])) if res else None


def scope6_dialog(parent, tr, existing: set[str], source: dict | None = None) -> dict | None:
    """Neuer DHCPv6-Scope (bzw. Kopie von source = n_scope6-Zeile). Ergebnis: prefix, name, desc, pref, lease_pref,
    lease_valid, active, copy_options, copy_exclusions."""
    s = source or {}
    fields = [
        {"key": "prefix", "label": tr("scope6.f.prefix"), "value": "", "readonly": False},
        {"key": "name", "label": tr("scope.f.name"), "value": (s.get("name") + " " + tr("scope6.copy_suffix")) if s else ""},
        {"key": "desc", "label": tr("scope.f.desc"), "value": s.get("desc", "")},
        {"key": "pref", "label": tr("scope6.f.preference"), "type": "number", "min": 0, "max": 255, "value": s.get("pref", 0)},
        {"key": "lease_pref", "label": tr("scope6.f.lease_pref"), "value": ck.format_duration(s.get("lease_pref") or 8 * 86400)},
        {"key": "lease_valid", "label": tr("scope6.f.lease_valid"),
         "value": ck.format_duration(s.get("lease_valid") or 12 * 86400)},
        {"key": "active", "label": tr("scope6.f.active"), "type": "check", "value": False},
    ]
    if s:
        fields += [{"key": "copy_options", "label": tr("scope6.copy_options"), "type": "check", "value": True},
                   {"key": "copy_exclusions", "label": tr("scope6.copy_exclusions"), "type": "check", "value": True}]

    def validate(v):
        p = ip6.parse_prefix(v["prefix"])
        if not p:
            return tr("scope6.err_prefix")
        if p[1] != ip6.PREFIX:
            return tr("scope6.err_plen")
        if ip6.prefix_of(p[0]) in existing:
            return tr("scope6.err_exists", prefix=ip6.prefix_of(p[0]))
        if not v["name"].strip():
            return tr("def.err_name")
        a, b = ck.parse_duration(v["lease_pref"]), ck.parse_duration(v["lease_valid"])
        if not a or not b:
            return tr("scope6.err_lifetime")
        if a >= b:
            return tr("scope6.err_pref_valid")
        return None

    res = FormDialog.ask(parent, tr("scope6.title_dup", id=s["id"]) if s else tr("scope6.title_new"), fields, tr,
                         hint=tr("scope6.hint"), validate=validate)
    if not res:
        return None
    p = ip6.parse_prefix(res["prefix"])
    res.update(prefix=ip6.prefix_of(p[0]), name=res["name"].strip(), desc=res["desc"].strip(), pref=int(res["pref"]),
               lease_pref=ck.parse_duration(res["lease_pref"]), lease_valid=ck.parse_duration(res["lease_valid"]))
    return res


def failover_dialog(parent, tr, servers: list[str], local: str, rel: dict | None = None,
                    scope_items: list[tuple[str, str]] | None = None, preset_scopes: list[str] = ()) -> dict | None:
    """Neue Beziehung (rel=None) oder Beziehung ändern. scope_items=None: keine Scope-Auswahl (Entwurf)."""
    edit = rel is not None
    r = rel or {}
    fields = [
        {"key": "name", "label": tr("fo.f.name"), "value": r.get("name", ""), "readonly": edit},
        {"key": "partner", "label": tr("fo.f.partner"), "type": "combo", "editable": True,
         "items": [s for s in servers if s.lower() != (local or "").lower()], "value": r.get("partner", ""), "readonly": edit},
        {"key": "mode", "label": tr("fo.f.mode"), "type": "combo",
         "items": [("LoadBalance", tr("fo.mode_lb")), ("HotStandby", tr("fo.mode_hs"))], "value": r.get("mode") or "LoadBalance"},
        {"key": "lb", "label": tr("fo.f.lb"), "type": "number", "min": 0, "max": 100,
         "value": r.get("lb") if r.get("lb") is not None else 50},
        {"key": "role", "label": tr("fo.f.role"), "type": "combo",
         "items": [("Active", tr("forole.Active")), ("Standby", tr("forole.Standby"))], "value": r.get("role") or "Active"},
        {"key": "reserve", "label": tr("fo.f.reserve"), "type": "number", "min": 0, "max": 100,
         "value": r.get("reserve") if r.get("reserve") is not None else 5},
        {"key": "mclt", "label": tr("fo.f.mclt"), "value": ck.format_duration(r.get("mclt") or 3600)},
        {"key": "auto", "label": tr("fo.f.auto"), "type": "check", "value": r.get("auto", False)},
        {"key": "interval", "label": tr("fo.f.interval"), "value": ck.format_duration(r.get("interval") or 3600)},
        {"key": "secret", "label": tr("fo.f.secret"), "type": "password", "value": ""},
    ]
    if not edit and scope_items is not None:
        fields.append({"key": "scopes", "label": tr("fo.f.scopes"), "type": "checklist", "items": scope_items,
                       "value": list(preset_scopes)})

    def validate(v):
        if not v["name"].strip():
            return tr("fo.err_name")
        p = str(v["partner"] or "").strip()
        if not p:
            return tr("fo.err_partner")
        if p.lower() == (local or "").lower():
            return tr("fo.err_partner_self")
        if ck.parse_duration(v["mclt"]) is None:
            return tr("fo.err_duration", field=tr("fo.f.mclt"))
        if v["auto"] and ck.parse_duration(v["interval"]) is None:
            return tr("fo.err_duration", field=tr("fo.f.interval"))
        if not edit and scope_items is not None and not v.get("scopes"):
            return tr("fo.err_scopes")
        return None

    hint = tr("fo.hint_edit") if edit else tr("fo.hint_new")
    res = FormDialog.ask(parent, tr("fo.title_edit") if edit else tr("fo.title_new"), fields, tr, hint=hint,
                         validate=validate, width=600)
    if res is None:
        return None
    res["partner"] = str(res["partner"]).strip()
    res["name"] = res["name"].strip()
    res["mclt"] = ck.parse_duration(res["mclt"])
    res["interval"] = ck.parse_duration(res["interval"]) or 3600
    res.setdefault("scopes", [])
    return res


def select_relationship(parent, tr, rels: list[dict], replicate: bool = True) -> tuple[str, bool] | None:
    if not rels:
        return None
    fields = [{"key": "name", "label": tr("fo.f.relationship"), "type": "combo",
               "items": [(r["name"], f"{r['name']}  →  {r['partner']}  ({ck.fo_mode(r, tr)})") for r in rels]},
              {"key": "replicate", "label": tr("fo.f.replicate_now"), "type": "check", "value": replicate}]
    res = FormDialog.ask(parent, tr("fo.title_select"), fields, tr, hint=tr("fo.hint_select"))
    return (res["name"], res["replicate"]) if res else None


def confirm_typed(parent, tr, title: str, text: str, word: str) -> bool:
    fields = [{"key": "word", "label": tr("ui.type_to_confirm", word=word), "value": ""}]
    res = FormDialog.ask(parent, title, fields, tr, hint=text,
                         validate=lambda v: None if v["word"].strip() == word else tr("ui.type_mismatch", word=word),
                         ok_label=tr("ui.delete"))
    return res is not None


def credentials_dialog(parent, tr, server: str, user: str = "") -> tuple[str, str] | None:
    fields = [{"key": "user", "label": tr("login.user"), "value": user},
              {"key": "password", "label": tr("login.password"), "type": "password"}]
    res = FormDialog.ask(parent, tr("login.cred_title", server=server), fields, tr, hint=tr("login.cred_hint"),
                         validate=lambda v: None if v["user"] else tr("login.err_user"))
    return (res["user"], res["password"]) if res else None


def partner_login_dialog(parent, tr, partner: str, error: str) -> str:
    """Partner nicht erreichbar: retry | other | primary | cancel."""
    box = QMessageBox(QMessageBox.Icon.Warning, tr("partner.title"), tr("partner.text", partner=partner), parent=parent)
    box.setInformativeText(tr("partner.info"))
    box.setDetailedText(error)
    b_retry = box.addButton(tr("partner.retry"), QMessageBox.ButtonRole.AcceptRole)
    b_other = box.addButton(tr("partner.other"), QMessageBox.ButtonRole.ActionRole)
    b_prim = box.addButton(tr("partner.primary"), QMessageBox.ButtonRole.DestructiveRole)
    b_cancel = box.addButton(tr("partner.later"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(b_other)
    box.exec()
    c = box.clickedButton()
    return {b_retry: "retry", b_other: "other", b_prim: "primary", b_cancel: "cancel"}.get(c, "cancel")


def checklist_dialog(parent, tr, title: str, hint: str, items: list[tuple[str, str]], checked=(), extra_check: str = "",
                     extra_value: bool = True) -> tuple[list[str], bool] | None:
    fields = [{"key": "items", "label": "", "type": "checklist", "items": items, "value": list(checked)}]
    if extra_check:
        fields.append({"key": "extra", "label": extra_check, "type": "check", "value": extra_value})
    res = FormDialog.ask(parent, title, fields, tr, hint=hint,
                         validate=lambda v: None if v["items"] else tr("ui.select_one"))
    return (res["items"], bool(res.get("extra"))) if res else None
