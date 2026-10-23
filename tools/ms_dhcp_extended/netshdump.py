"""netsh dhcp: Dump auswerten, Befehle bauen und den Abgleichplan für die Replikation berechnen.

Der Failover-Partner wird (wie von der DHCP-Konsole) per RPC direkt von diesem Rechner angesprochen.
Lesen über "netsh dhcp server \\\\x [scope y] dump", Schreiben über einzelne netsh-Befehle.
Die Dump-Syntax ist sprachunabhängig (Befehlszeilen), nur Erfolgsmeldungen sind lokalisiert.
"""

from __future__ import annotations

import re

from . import ipcalc as ip
from . import optcodec as oc

NETSH_TYPES = {"IPADDRESS": "IPv4Address", "STRING": "String", "BYTE": "Byte", "WORD": "Word", "DWORD": "DWord",
               "DWORDDWORD": "DWordDword", "BINARY": "BinaryData", "ENCAPSULATED": "EncapsulatedData",
               "IPV6ADDRESS": "IPv6Address"}
_TYPE_NAMES = {v: k for k, v in NETSH_TYPES.items()}
_TOKEN = re.compile(r'(\w+)="([^"]*)"|"([^"]*)"|(\S+)')
_OK = re.compile(r"erfolgreich|successfully|correctement|correttamente|correctamente|pomyślnie|úspěšně|sikeresen",
                 re.IGNORECASE)


def type_name(typ: str) -> str:
    return _TYPE_NAMES.get(typ, "STRING")


def split_tokens(line: str) -> list[tuple[str | None, str]]:
    out = []
    for m in _TOKEN.finditer(line):
        if m.group(1) is not None:
            out.append((m.group(1).lower(), m.group(2)))
        elif m.group(3) is not None:
            out.append((None, m.group(3)))
        else:
            t = m.group(4)
            km = re.match(r"^(vendor|user|comment)=(.*)$", t, re.IGNORECASE)
            out.append((km.group(1).lower(), km.group(2)) if km else (None, t))
    return out


def _new_scope(sid: str) -> dict:
    return {"id": sid, "mask": "", "name": "", "desc": "", "state": "Active", "start": "", "end": "", "lease": None,
            "exclusions": [], "options": [], "reservations": []}


def parse_dump(lines: list[str]) -> dict:
    """Ergebnis: {"scopes": {id: scope}, "options": [...], "defs": [...], "classes": [...]} (normalisiert)."""
    scopes: dict[str, dict] = {}
    opts, defs, classes = [], [], []
    for line in lines:
        if not re.match(r"^\s*Dhcp\s+Server\s", line, re.IGNORECASE):
            continue
        tk = split_tokens(line)
        if len(tk) < 5:
            continue
        i, sid = 3, None
        if tk[3][1].lower() == "scope" and len(tk) > 5:
            sid, i = tk[4][1], 5
        if len(tk) < i + 2:
            continue
        verb, obj = tk[i][1].lower(), tk[i + 1][1].lower()
        kw: dict[str, str] = {}
        pos: list[str] = []
        for k, v in tk[i + 2:]:
            if k:
                kw[k] = v
            else:
                pos.append(v)
        if sid and sid not in scopes:
            scopes[sid] = _new_scope(sid)
        sc = scopes.get(sid) if sid else None
        cmd = f"{verb} {obj}"
        if cmd == "add scope" and len(pos) >= 2:
            s = scopes.setdefault(pos[0], _new_scope(pos[0]))
            s["mask"] = pos[1]
            if len(pos) >= 3:
                s["name"] = pos[2]
            if len(pos) >= 4:
                s["desc"] = pos[3]
        elif cmd == "set state" and sc and pos:
            sc["state"] = "Active" if pos[0] in ("1", "3") else "InActive"
        elif cmd == "set name" and sc and pos:
            sc["name"] = pos[0]
        elif cmd == "set comment" and sc and pos:
            sc["desc"] = pos[0]
        elif cmd == "add iprange" and sc and len(pos) >= 2:
            sc["start"], sc["end"] = pos[0], pos[1]
        elif cmd == "add excluderange" and sc and len(pos) >= 2:
            sc["exclusions"].append({"start": pos[0], "end": pos[1]})
        elif cmd == "add reservedip" and sc and len(pos) >= 2:
            sc["reservations"].append({"ip": pos[0], "cid": ip.format_client_id(pos[1]) or pos[1],
                                       "name": pos[2] if len(pos) >= 3 else "", "desc": pos[3] if len(pos) >= 4 else "",
                                       "type": pos[4] if len(pos) >= 5 else "Dhcp"})
        elif cmd == "set optionvalue" and len(pos) >= 2:
            try:
                oid = int(pos[0])
            except ValueError:
                continue
            o = {"id": oid, "type": NETSH_TYPES.get(pos[1].upper(), pos[1]), "values": pos[2:],
                 "vendor": kw.get("vendor", ""), "user": kw.get("user", "")}
            if sc is not None:
                sc["options"].append(o)
                if oid == 51 and not o["vendor"] and o["values"]:
                    n = oc.to_number(o["values"][0])
                    if n is not None:
                        sc["lease"] = min(n, ip.UNLIMITED)
            else:
                opts.append(o)
        elif cmd == "add optiondef" and len(pos) >= 4:
            try:
                oid = int(pos[0])
            except ValueError:
                continue
            defs.append({"id": oid, "name": pos[1], "type": NETSH_TYPES.get(pos[2].upper(), pos[2]), "multi": pos[3] == "1",
                         "vendor": kw.get("vendor", ""), "desc": kw.get("comment", ""), "default": pos[4:]})
        elif cmd == "add class" and sc is None and pos:
            classes.append({"name": pos[0], "desc": pos[1] if len(pos) >= 2 else "", "vendor": len(pos) >= 4 and pos[3] == "1"})
    return {"scopes": scopes, "options": opts, "defs": defs, "classes": classes}


def has_dump_lines(lines: list[str]) -> bool:
    return any(re.match(r"^\s*Dhcp\s+Server\s", x, re.IGNORECASE) for x in lines)


def is_ok(result: dict) -> bool:
    """Ein netsh-Befehl war erfolgreich (Exit-Code 0 und Erfolgsmeldung)."""
    return int(result.get("code", -1)) == 0 and bool(_OK.search("\n".join(result.get("out") or [])))


def format_out(result: dict) -> str:
    o = [x.strip() for x in result.get("out") or [] if not re.search(r"Bereichskontext|scope context", x, re.IGNORECASE)]
    return " ".join(o) if o else "–"


# --- Befehle bauen ---------------------------------------------------------------------------------

def q(text) -> str:
    return '"' + str(text or "").replace('"', "'") + '"'


def value_args(typ: str, values: list[str]) -> str:
    if typ in oc.BINARY_TYPES:
        b = oc.to_bytes([str(v) for v in values])
        return (b or b"").hex()
    return " ".join('"' + str(v).replace('"', "") + '"' for v in values)


def class_args(vendor: str = "", user: str = "") -> str:
    a = ""
    if user:
        a += " user=" + q(user)
    if vendor:
        a += " vendor=" + q(vendor)
    return a


def set_option_cmd(opt_id: int, vendor: str, user: str, values: list[str], opt_def: dict | None) -> str:
    typ = (opt_def or {}).get("type") or "String"
    if not vendor and opt_id in (51, 81):
        typ = "DWord"      # 81 = interne DNS-Einstellungen (DWORD-Bitmaske)
    return f"set optionvalue {int(opt_id)} {type_name(typ)}{class_args(vendor, user)} {value_args(typ, values)}"


def add_def_cmd(d: dict) -> str:
    a = f"add optiondef {int(d['id'])} {q(d['name'])} {type_name(d['type'])} {1 if d.get('multi') else 0}"
    if d.get("vendor"):
        a += " vendor=" + q(d["vendor"])
    if d.get("desc"):
        a += " comment=" + q(d["desc"])
    dv = [x for x in d.get("default") or [] if str(x)]
    if dv:
        a += " " + value_args(d["type"], dv)
    return a


def add_class_cmd(c: dict) -> str:
    hx = str(c.get("data") or "").encode("ascii", errors="replace").hex()
    return f"add class {q(c['name'])} {q(c.get('desc'))} {hx} {1 if c.get('type') == 'Vendor' else 0} b"


# --- Abgleich (Replikation) ------------------------------------------------------------------------

def _res_sig(r: dict) -> str:
    return "|".join((ip.mac_hex(r.get("cid")), str(r.get("name") or ""), str(r.get("desc") or ""),
                     str(r.get("type") or "").lower()))


def _opt_key(o: dict) -> str:
    return f"{int(o['id'])}|{o.get('vendor') or ''}|{o.get('user') or ''}"


class MaskMismatch(Exception):
    def __init__(self, scope_id: str, remote: str, local: str):
        super().__init__(scope_id, remote, local)
        self.scope_id, self.remote, self.local = scope_id, remote, local


def sync_plan(scope_id: str, local: dict, remote: dict | None, opt_def) -> list[str]:
    """netsh-Befehle, die den Partner-Scope (remote aus dem Dump, None = fehlt) an den lokalen Stand angleichen.

    local: {"scope": {...}, "exclusions": [...], "options": [...], "reservations": [...]} (normalisiert)
    opt_def(id, vendor) -> Definition oder None. Überträgt Name, Beschreibung, Bereich, Ausschlüsse, Lease,
    Optionen (alle Klassen), Reservierungen und zuletzt den Status. Option 81 wird nie gelöscht.
    """
    cmds: list[str] = []
    s = local["scope"]
    sc = f"scope {scope_id}"
    l_name = str(s.get("name") or "").replace('"', "'")
    l_desc = str(s.get("desc") or "").replace('"', "'")
    l_state = "Active" if s.get("state") == "Active" else "InActive"
    l_range = f"{s['start']} {s['end']}"
    if not remote:
        cmds.append(f"add scope {scope_id} {s['mask']} {q(l_name)} {q(l_desc)}")
        cmds.append(f"{sc} add iprange {l_range}")
    else:
        if remote.get("mask") and remote["mask"] != s["mask"]:
            raise MaskMismatch(scope_id, remote["mask"], s["mask"])
        if str(remote.get("name") or "") != l_name:
            cmds.append(f"{sc} set name {q(l_name)}")
        if str(remote.get("desc") or "") != l_desc:
            cmds.append(f"{sc} set comment {q(l_desc)}")
    # Ausschlüsse: erst überzählige entfernen (vor der Bereichsänderung), dann fehlende anlegen
    lx = {f"{x['start']} {x['end']}" for x in local.get("exclusions") or []}
    rx = {f"{x['start']} {x['end']}" for x in (remote or {}).get("exclusions") or []}
    for k in sorted(rx - lx):
        cmds.append(f"{sc} delete excluderange {k}")
    if remote and f"{remote.get('start')} {remote.get('end')}" != l_range:
        # "add iprange" passt den vorhandenen Bereich an (Failover-Scopes erlauben kein Löschen). Der neue Bereich
        # muss den alten enthalten oder darin liegen - bei Verschiebung erst auf die Vereinigung erweitern.
        try:
            ls, le, rs, re_ = (ip.ip2int(s["start"]), ip.ip2int(s["end"]), ip.ip2int(remote["start"]), ip.ip2int(remote["end"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            ls = None
        if ls is not None and not (rs <= ls and le <= re_) and not (ls <= rs and re_ <= le):
            cmds.append(f"{sc} add iprange {ip.int2ip(min(ls, rs))} {ip.int2ip(max(le, re_))}")
        cmds.append(f"{sc} add iprange {l_range}")
    for k in sorted(lx - rx):
        cmds.append(f"{sc} add excluderange {k}")
    # Lease-Dauer (Option 51)
    l_sec = s.get("lease")
    r_sec = (remote or {}).get("lease")
    if l_sec is not None and l_sec != r_sec:
        cmds.append(f'{sc} set optionvalue 51 DWORD "{int(l_sec)}"')
    # Optionen (alle Hersteller-/Benutzerklassen, ohne 51)
    lo = {_opt_key(o): o for o in local.get("options") or [] if int(o["id"]) != 51}
    ro = {_opt_key(o): o for o in (remote or {}).get("options") or [] if int(o["id"]) != 51}
    for k, o in ro.items():
        if k in lo or int(o["id"]) == 81:
            continue
        cmds.append(f"{sc} delete optionvalue {int(o['id'])}{class_args(o.get('vendor', ''), o.get('user', ''))}")
    for k, o in lo.items():
        d = opt_def(int(o["id"]), o.get("vendor") or "")
        vals = [str(v) for v in o.get("values") or []]
        if k in ro and oc.compare_form(vals, d) == oc.compare_form(ro[k].get("values"), d):
            continue
        cmds.append(f"{sc} " + set_option_cmd(int(o["id"]), o.get("vendor") or "", o.get("user") or "", vals, d))
    # Reservierungen: geänderte werden gelöscht und neu angelegt
    lr = {str(x["ip"]): x for x in local.get("reservations") or []}
    rr = {str(x["ip"]): x for x in (remote or {}).get("reservations") or []}
    for k, x in rr.items():
        if k in lr and _res_sig(lr[k]) == _res_sig(x):
            continue
        cmds.append(f"{sc} delete reservedip {k} {ip.mac_hex(x.get('cid'))}")
    for k, x in lr.items():
        if k in rr and _res_sig(x) == _res_sig(rr[k]):
            continue
        typ = str(x.get("type") or "").upper()
        if typ not in ("DHCP", "BOOTP", "BOTH"):
            typ = "DHCP"
        cmds.append(f'{sc} add reservedip {k} {ip.mac_hex(x.get("cid"))} {q(x.get("name"))} {q(x.get("desc"))} "{typ}"')
    # Status zuletzt (erst aktivieren, wenn alles da ist)
    if str((remote or {}).get("state") or "") != l_state:
        cmds.append(f"{sc} set state {1 if l_state == 'Active' else 0}")
    return cmds


def scope_lines(lines: list[str], scope_id: str) -> list[str]:
    """Die Dump-Zeilen, die einen Scope betreffen (für die Rohdatenansicht)."""
    e = re.escape(scope_id)
    rx = re.compile(r"Scope\s+" + e + r"\b|add scope " + e + r"\b", re.IGNORECASE)
    return [x for x in lines if rx.search(x)]
