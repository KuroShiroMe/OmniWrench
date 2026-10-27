"""Wer hat am DNS-Server etwas geändert? Ereignisprotokoll "DNS-Server/Audit" über wevtapi.dll (RPC).

Der DNS-Serverdienst (ab Windows Server 2012 R2) schreibt jede Änderung an Zonen, Einträgen und Einstellungen mit
dem ausführenden Konto in den Kanal "Microsoft-Windows-DNSServer/Audit" – auch Änderungen aus der DNS-Konsole,
PowerShell, dnscmd oder dynamische Updates der Clients. Gelesen wird wie in der Ereignisanzeige per
Remote-Sitzung (EvtOpenSession) mit denselben Anmeldedaten wie die DNS-Verbindung. Nötig: Leserecht auf das
Protokoll (z. B. Gruppe "Ereignisprotokollleser" oder Administrator) und die Firewall-Regel
"Remote-Ereignisprotokollverwaltung".

Aufbau wie im DHCP-Tool (eigene Kopie, damit beide Tools unabhängig bleiben).
"""

from __future__ import annotations

import ctypes
import datetime as _dt
import re
import xml.etree.ElementTree as ET
from ctypes import Structure, byref, c_uint32, c_void_p, c_wchar_p

CHANNEL = "Microsoft-Windows-DNSServer/Audit"
PUBLISHER = "Microsoft-Windows-DNSServer"
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


# --- Lesehilfe: Bereich, Aktion, Zone und Eintrag ---------------------------------------------------------
# Ereignis-IDs des Audit-Kanals (Microsoft: "DNS logging and diagnostics"). Unbekannte IDs werden über
# Schlüsselwörter im Meldungstext eingeordnet (deutsch oder englisch).
EVENT_IDS = {
    513: ("zone", "delete"), 514: ("zone", "change"), 515: ("record", "create"), 516: ("record", "delete"),
    517: ("record", "delete"), 518: ("record", "delete"), 519: ("record", "create"), 520: ("record", "delete"),
    521: ("record", "scavenge"), 522: ("zone", "delete"), 523: ("record", "scavenge"), 525: ("dnssec", "change"),
    526: ("dnssec", "change"), 527: ("dnssec", "change"), 528: ("dnssec", "change"), 529: ("dnssec", "change"),
    530: ("dnssec", "change"), 531: ("dnssec", "change"), 532: ("dnssec", "change"), 533: ("dnssec", "change"),
    534: ("dnssec", "change"), 535: ("dnssec", "change"), 536: ("cache", "delete"), 537: ("server", "change"),
    540: ("server", "change"), 541: ("server", "change"), 542: ("server", "create"), 543: ("server", "delete"),
    544: ("dnssec", "create"), 545: ("dnssec", "delete"), 546: ("dnssec", "change"), 547: ("server", "change"),
    548: ("server", "change"), 549: ("server", "change"), 550: ("server", "change"), 551: ("server", "change"),
    552: ("server", "change"), 553: ("zone", "change"), 554: ("server", "change"), 555: ("server", "change"),
    556: ("server", "change"), 557: ("server", "change"), 558: ("zone", "change"), 559: ("zone", "change"),
    561: ("zone", "change"), 562: ("zone", "change"), 563: ("zone", "change"), 564: ("zone", "change"),
    565: ("zone", "change"), 566: ("zone", "change"), 567: ("policy", "change"), 568: ("policy", "create"),
    569: ("policy", "delete"), 570: ("policy", "change"), 571: ("policy", "change"), 572: ("policy", "change"),
    573: ("policy", "create"), 574: ("policy", "delete"), 575: ("zone", "change"), 576: ("zone", "change"),
    577: ("zone", "create"), 578: ("zone", "delete"), 579: ("record", "create"), 580: ("record", "delete"),
    581: ("record", "change"), 582: ("record", "change"),
}
AREAS = (("dnssec", ("dnssec", "signing", "signier", "key ", "schlüssel", "trust", "vertrauens")),
         ("policy", ("policy", "richtlinie")), ("cache", ("cache",)),
         ("record", ("record", "eintrag", "resource", "ressource", "rrset", "node", "knoten")),
         ("zone", ("zone",)),
         ("server", ("server", "forwarder", "weiterleitung", "root hint", "stammhinweis", "setting", "einstellung")))
ACTIONS = (("scavenge", ("scaveng", "aufräum", "veraltet")),
           ("delete", ("delet", "remov", "gelöscht", "entfernt", "purg")),
           ("create", ("creat", "added", "add ", "hinzugef", "erstellt", "angelegt")),
           ("change", ("modif", "chang", "updat", "geändert", "aktualisiert", "festgelegt", "configured", "konfiguriert",
                       "reset", "zurückgesetzt", "pause", "resum", "reload")))
TYPE_NAMES = {1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 12: "PTR", 15: "MX", 16: "TXT", 28: "AAAA", 33: "SRV",
              43: "DS", 46: "RRSIG", 47: "NSEC", 48: "DNSKEY", 50: "NSEC3", 51: "NSEC3PARAM", 257: "CAA"}
_FIELD_ZONE = ("zone", "zonename")
_FIELD_NAME = ("name", "nodename", "fqdn", "ownername")
_FIELD_TYPE = ("type", "rrtype", "recordtype")


def _field(ev: dict, names) -> str:
    for k, v in ev.get("fields") or []:
        if str(k).lower() in names and str(v).strip():
            return str(v).strip()
    return ""


def classify(ev: dict, zones: list[str] | None = None) -> dict:
    """Lesehilfe zu einem Ereignis: area, action, zone, obj ("name (Typ)") – leer, wenn unklar."""
    known = EVENT_IDS.get(int(ev.get("id") or 0))
    text = " ".join([ev.get("text") or ""] + [f"{k} {v}" for k, v in ev.get("fields") or []])
    low = text.lower()
    if known:
        area, action = known
    else:
        area = next((a for a, keys in AREAS if any(k in low for k in keys)), "other")
        action = next((a for a, keys in ACTIONS if any(k in low for k in keys)), "other")
    zone = _field(ev, _FIELD_ZONE).rstrip(".").lower()
    if not zone and zones:
        hits = [z for z in zones if z and re.search(r"(?<![\w-])" + re.escape(z) + r"(?![\w-])", low)]
        zone = max(hits, key=len) if hits else ""
    name = _field(ev, _FIELD_NAME).rstrip(".").lower()
    rtype = _field(ev, _FIELD_TYPE)
    if rtype.isdigit():
        rtype = TYPE_NAMES.get(int(rtype), rtype)
    obj = name
    if obj and rtype:
        obj = f"{name} ({rtype})"
    return {"area": area, "action": action, "zone": zone, "obj": obj, "name": name, "rtype": rtype}


class EventReader:
    """Liest die neuesten Ereignisse eines Kanals auf einem Server (nur Windows)."""

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
              max_n: int = 200, channel: str = CHANNEL, publisher: str = PUBLISHER) -> list[dict]:
        user, domain, pw = login
        lg = _Login(server, user, domain, pw, 0)
        sess = self.w.EvtOpenSession(EVT_RPC_LOGIN, ctypes.addressof(lg), 0, 0)
        if not sess:
            raise self._fail("events", server)
        try:
            q = self.w.EvtQuery(sess, channel, xpath_since(since_utc), EVT_QUERY_CHANNEL_PATH | EVT_QUERY_REVERSE)
            if not q:
                raise self._fail("events", server)
            meta = self.w.EvtOpenPublisherMetadata(sess, publisher, None, 0, 0)
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
