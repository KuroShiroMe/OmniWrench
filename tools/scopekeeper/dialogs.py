"""Eingabedialoge von ScopeKeeper (Option, Reservierung, Ausschluss, Failover, Definition, Anmeldung)."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QMessageBox

from . import checks as ck
from . import ipcalc as ip
from . import optcodec as oc
from .ui_base import FormDialog, confirm


def _opt_id(v) -> int | None:
    m = re.match(r"\s*(\d+)", str(v if v is not None else ""))
    return int(m.group(1)) if m else None


def option_dialog(parent, tr, checker: ck.Checker, defs: dict, opt: dict | None = None, model: ip.ScopeModel | None = None,
                  vendors: list[str] = (), users: list[str] = (), title: str = "") -> dict | None:
    """Option anlegen/bearbeiten. Ergebnis: {"id", "values", "vendor", "user", "undefined"}."""
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
    state: dict = {}

    def validate(v: dict) -> str | None:
        oid = _opt_id(v["id"])
        if oid is None or not 1 <= oid <= 254:
            return tr("opt.err_id")
        if oid == 51 and not v["vendor"]:
            return tr("opt.err_51")
        d = defs.get((v["vendor"] or "", oid))
        vals = oc.split_option_text(v["values"], d)
        if not vals:
            return tr("opt.err_empty")
        if not d:
            state.update(id=oid, values=vals, undefined=True)
            return None
        fs = [f for f in checker.option_values(oid, vals, v["vendor"] or "", model) if f.fix != "new_def"]
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
            "undefined": state.get("undefined", False)}


def guess_type(values: list[str]) -> str:
    if values and all(ip.is_ipv4(v) for v in values):
        return "IPv4Address"
    if values and all(oc.to_number(v) is not None for v in values):
        mx = max(oc.to_number(v) for v in values)
        return "Byte" if mx <= 255 else "Word" if mx <= 65535 else "DWord"
    return "String"


def definition_dialog(parent, tr, d: dict | None = None, vendors: list[str] = (), with_partner: bool = False,
                      preset: dict | None = None) -> dict | None:
    edit = d is not None
    base = d or preset or {}
    fields = [
        {"key": "id", "label": tr("def.f.id"), "type": "number", "min": 1, "max": 255, "value": base.get("id", 224),
         "readonly": edit},
        {"key": "name", "label": tr("def.f.name"), "value": base.get("name", "")},
        {"key": "type", "label": tr("def.f.type"), "type": "combo", "items": oc.OPTION_TYPES[:-1],
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

    res = FormDialog.ask(parent, tr("def.title_edit") if edit else tr("def.title_add"), fields, tr, validate=validate)
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
