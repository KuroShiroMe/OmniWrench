"""Wer hat am DHCP-Server etwas geändert? Ereignisprotokoll "DHCP-Server/Operational" über wevtapi.dll (RPC).

Der DHCP-Serverdienst schreibt Konfigurationsänderungen (Scope, Option, Reservierung, Ausschluss, Failover,
Richtlinie …) mit dem ausführenden Konto in dieses Protokoll – auch Änderungen aus der DHCP-Konsole oder
PowerShell. Gelesen wird wie in der Ereignisanzeige per Remote-Sitzung (EvtOpenSession), mit denselben
Anmeldedaten wie die DHCP-Verbindung. Nötig: Leserecht auf das Protokoll (z. B. Gruppe "Ereignisprotokollleser"
oder Administrator) und die Firewall-Regel "Remote-Ereignisprotokollverwaltung".
"""

from __future__ import annotations

import ctypes
import datetime as _dt
import re
import xml.etree.ElementTree as ET
from ctypes import Structure, byref, c_uint32, c_void_p, c_wchar_p

CHANNEL = "Microsoft-Windows-Dhcp-Server/Operational"
PUBLISHER = "Microsoft-Windows-DHCP-Server"
NS = "{http://schemas.microsoft.com/win/2004/08/events/event}"

ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259
EVT_RPC_LOGIN = 1
EVT_QUERY_CHANNEL_PATH = 0x1
EVT_QUERY_REVERSE = 0x200
EVT_RENDER_XML = 1
EVT_FORMAT_EVENT = 1


class _Login(Structure):
    _fields_ = [("Server", c_wchar_p), ("User", c_wchar_p), ("Domain", c_wchar_p), ("Password", c_wchar_p),
                ("Flags", c_uint32)]


def iso_utc(t: _dt.datetime) -> str:
    return t.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def xpath_since(since_utc: str) -> str:
    return f"*[System[TimeCreated[@SystemTime>='{since_utc}']]]"


def parse_event_xml(xml: str) -> dict:
    """Ereignis-XML -> {record, id, level, time (lokal, "JJJJ-MM-TT HH:MM:SS"), utc, sid, computer,
    data (Werte aus EventData), fields ([(Name, Wert)])}."""
    root = ET.fromstring(xml)
    sys_ = root.find(NS + "System")

    def f(tag):
        return sys_.find(NS + tag) if sys_ is not None else None
    tc = f("TimeCreated")
    utc = tc.get("SystemTime", "") if tc is not None else ""
    local = ""
    if utc:
        try:     # z. B. 2026-10-23T10:42:17.1234567Z
            t = _dt.datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt.timezone.utc)
            local = t.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            local = utc[:19].replace("T", " ")
    sec = f("Security")
    rec, eid = f("EventRecordID"), f("EventID")
    data, fields = [], []
    for parent in (root.find(NS + "EventData"), root.find(NS + "UserData")):
        if parent is not None:
            for el in parent.iter():
                if el is not parent and el.text and el.text.strip() and not list(el):
                    data.append(el.text.strip())
                    fields.append((el.get("Name") or el.tag.split("}")[-1], el.text.strip()))
    lvl, comp = f("Level"), f("Computer")
    return {"record": int(rec.text) if rec is not None and (rec.text or "").isdigit() else 0,
            "id": int(eid.text) if eid is not None and (eid.text or "").isdigit() else 0,
            "level": int(lvl.text) if lvl is not None and (lvl.text or "").isdigit() else 4,
            "utc": utc, "time": local, "sid": sec.get("UserID", "") if sec is not None else "",
            "computer": comp.text if comp is not None and comp.text else "", "data": data, "fields": fields}


# --- Lesehilfe: Bereich, Aktion, Scope und Objekt aus dem Meldungstext (deutsch oder englisch) ---------------
# Reihenfolge zählt: spezielle Begriffe vor allgemeinen ("Reservierung im Bereich" ist eine Reservierung).
AREAS = (("failover", ("failover",)), ("policy", ("policy", "richtlinie")), ("filter", ("filter",)),
         ("reservation", ("reservation", "reservierung")), ("exclusion", ("exclusion", "ausschluss", "exclude")),
         ("optiondef", ("option definition", "optionsdefinition", "optiondefinition")),
         ("option", ("option",)), ("class", ("class", "klasse")), ("superscope", ("superscope", "bereichsgruppe")),
         ("scope", ("scope", "bereich")), ("server", ("server", "audit", "datenbank", "database", "binding", "bindung")))
ACTIONS = (("delete", ("delet", "remov", "gelöscht", "entfernt")),
           ("create", ("creat", "added", "add ", "hinzugef", "erstellt", "angelegt")),
           ("change", ("modif", "chang", "updat", "geändert", "aktualisiert", "festgelegt", "configured", "konfiguriert",
                       "activat", "deactivat", "aktiviert", "deaktiviert", "enabled", "disabled")))
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_OPT = re.compile(r"option(?:s)?(?:[- ]?(?:id|nummer|number|wert|value|definition))?\s*[:#]?\s*(\d{1,3})\b", re.I)


def _ip2int(a: str) -> int | None:
    p = a.split(".")
    if len(p) != 4 or not all(x.isdigit() and int(x) < 256 for x in p):
        return None
    return (int(p[0]) << 24) | (int(p[1]) << 16) | (int(p[2]) << 8) | int(p[3])


def classify(ev: dict, scopes: list[tuple[str, str]] | None = None) -> dict:
    """Lesehilfe zu einem Ereignis: area, action, scope (Scope-ID), obj (Adresse/Option) – leer, wenn unklar.
    scopes = [(Scope-ID, Maske)] des Servers, um Adressen einem Scope zuzuordnen."""
    text = " ".join([ev.get("text") or ""] + [f"{k} {v}" for k, v in ev.get("fields") or []])
    low = text.lower()
    area = next((a for a, keys in AREAS if any(k in low for k in keys)), "other")
    action = next((a for a, keys in ACTIONS if any(k in low for k in keys)), "other")
    nets = []
    for sid, mask in scopes or []:
        n, m = _ip2int(sid), _ip2int(mask)
        if n is not None and m is not None:
            nets.append((sid, n, m))
    scope, objs = "", []
    for a in dict.fromkeys(_IP.findall(text)):
        v = _ip2int(a)
        if v is None:
            continue
        hit = next((sid for sid, n, m in nets if v & m == n), "")
        if a in (sid for sid, _n, _m in nets):
            scope = scope or a
        else:
            scope = scope or hit
            objs.append(a)
    if area in ("option", "optiondef"):
        m = _OPT.search(text)
        if m:
            objs.insert(0, f"{int(m.group(1)):03d}")
    return {"area": area, "action": action, "scope": scope, "obj": ", ".join(objs[:3])}


class EventReader:
    """Liest die neuesten DHCP-Konfigurationsereignisse eines Servers (nur Windows)."""

    def __init__(self):
        self.w = ctypes.WinDLL("wevtapi.dll", use_last_error=True)
        self.adv = ctypes.WinDLL("advapi32", use_last_error=True)
        w = self.w
        for name, res, args in (
                ("EvtOpenSession", c_void_p, [c_uint32, c_void_p, c_uint32, c_uint32]),
                ("EvtQuery", c_void_p, [c_void_p, c_wchar_p, c_wchar_p, c_uint32]),
                ("EvtNext", ctypes.c_int, [c_void_p, c_uint32, ctypes.POINTER(c_void_p), c_uint32, c_uint32,
                                           ctypes.POINTER(c_uint32)]),
                ("EvtRender", ctypes.c_int, [c_void_p, c_void_p, c_uint32, c_uint32, c_void_p, ctypes.POINTER(c_uint32),
                                             ctypes.POINTER(c_uint32)]),
                ("EvtOpenPublisherMetadata", c_void_p, [c_void_p, c_wchar_p, c_wchar_p, c_uint32, c_uint32]),
                ("EvtFormatMessage", ctypes.c_int, [c_void_p, c_void_p, c_uint32, c_uint32, c_void_p, c_uint32, c_uint32,
                                                    c_void_p, ctypes.POINTER(c_uint32)]),
                ("EvtClose", ctypes.c_int, [c_void_p])):
            fn = getattr(w, name)
            fn.restype, fn.argtypes = res, args
        self._names: dict[tuple[str, str], str] = {}

    def _fail(self, what: str, server: str) -> RuntimeError:
        err = ctypes.get_last_error()
        return RuntimeError(f"@RPC:{what}:{server}:{err}:{ctypes.FormatError(err).strip() if err else ''}")

    def _render(self, h) -> str:
        used, props = c_uint32(0), c_uint32(0)
        self.w.EvtRender(None, h, EVT_RENDER_XML, 0, None, byref(used), byref(props))
        if ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER:
            return ""
        buf = ctypes.create_string_buffer(used.value + 2)
        if not self.w.EvtRender(None, h, EVT_RENDER_XML, used.value, buf, byref(used), byref(props)):
            return ""
        return ctypes.wstring_at(buf)

    def _message(self, meta, h) -> str:
        if not meta:
            return ""
        used = c_uint32(0)
        self.w.EvtFormatMessage(meta, h, 0, 0, None, EVT_FORMAT_EVENT, 0, None, byref(used))
        if ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER or not used.value:
            return ""
        buf = ctypes.create_unicode_buffer(used.value + 1)
        if not self.w.EvtFormatMessage(meta, h, 0, 0, None, EVT_FORMAT_EVENT, used.value, buf, byref(used)):
            return ""
        return " ".join(buf.value.split())

    def _account(self, server: str, sid: str) -> str:
        """SID -> DOMÄNE\\Benutzer (auf dem Server aufgelöst, gemerkt)."""
        if not sid:
            return ""
        key = (server.lower(), sid)
        if key in self._names:
            return self._names[key]
        name = sid
        psid = c_void_p()
        if self.adv.ConvertStringSidToSidW(c_wchar_p(sid), byref(psid)):
            n, d, use = c_uint32(256), c_uint32(256), c_uint32(0)
            nb, db = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
            if self.adv.LookupAccountSidW(c_wchar_p(server), psid, nb, byref(n), db, byref(d), byref(use)):
                name = f"{db.value}\\{nb.value}" if db.value else nb.value
            ctypes.windll.kernel32.LocalFree(psid)
        self._names[key] = name
        return name

    def query(self, server: str, login: tuple[str | None, str | None, str | None], since_utc: str,
              max_n: int = 200) -> list[dict]:
        user, domain, pw = login
        lg = _Login(server, user, domain, pw, 0)
        sess = self.w.EvtOpenSession(EVT_RPC_LOGIN, ctypes.addressof(lg), 0, 0)
        if not sess:
            raise self._fail("events", server)
        try:
            q = self.w.EvtQuery(sess, CHANNEL, xpath_since(since_utc), EVT_QUERY_CHANNEL_PATH | EVT_QUERY_REVERSE)
            if not q:
                raise self._fail("events", server)
            meta = self.w.EvtOpenPublisherMetadata(sess, PUBLISHER, None, 0, 0)
            out: list[dict] = []
            try:
                arr = (c_void_p * 32)()
                got = c_uint32(0)
                while len(out) < max_n:
                    if not self.w.EvtNext(q, 32, arr, 5000, 0, byref(got)):
                        if ctypes.get_last_error() == ERROR_NO_MORE_ITEMS:
                            break
                        raise self._fail("events", server)
                    for i in range(got.value):
                        h = arr[i]
                        try:
                            xml = self._render(h)
                            if xml:
                                ev = parse_event_xml(xml)
                                ev["text"] = self._message(meta, h) or " | ".join(ev["data"])
                                ev["user"] = self._account(server, ev["sid"])
                                out.append(ev)
                        finally:
                            self.w.EvtClose(h)
            finally:
                if meta:
                    self.w.EvtClose(meta)
                self.w.EvtClose(q)
            return out
        finally:
            self.w.EvtClose(sess)
