"""Änderungen anderer erkennen: Ereignis-XML, Konfigurationsvergleich, Filter auf einen Scope.

    python3 scripts/dhcp_api_check/test_conflict.py
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.ms_dhcp_extended import eventlog as E  # noqa: E402
from tools.ms_dhcp_extended import service as S  # noqa: E402

ok = True


def check(label, cond):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FEHL ") + label)


XML = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>
<Provider Name='Microsoft-Windows-DHCP-Server' Guid='{6D64F02C-A125-4DAC-9A01-F0555B41CA84}'/>
<EventID>20102</EventID><Version>0</Version><Level>4</Level><TimeCreated SystemTime='2026-10-23T10:42:17.1234567Z'/>
<EventRecordID>4711</EventRecordID><Channel>Microsoft-Windows-Dhcp-Server/Operational</Channel>
<Computer>rz-dhcp01.mediclin.wan</Computer><Security UserID='S-1-5-21-1-2-3-1105'/></System>
<EventData><Data Name='ScopeName'>Büro</Data><Data Name='ScopeId'>10.1.0.0</Data><Data Name='Empty'></Data></EventData></Event>"""
ev = E.parse_event_xml(XML)
check(f"XML: {ev['id']} #{ev['record']} {ev['sid']} {ev['time']} {ev['data']}",
      ev["id"] == 20102 and ev["record"] == 4711 and ev["sid"].endswith("1105") and ev["utc"].startswith("2026-10-23T10:42")
      and ev["time"][:10] == "2026-10-23" and ev["data"] == ["Büro", "10.1.0.0"])
check("XPath", E.xpath_since("2026-10-23T10:00:00.000Z") == "*[System[TimeCreated[@SystemTime>='2026-10-23T10:00:00.000Z']]]")

tr = lambda k, **kw: f"{k}{kw}" if kw else k  # noqa: E731
svc = S.DhcpService(None, tr)
svc.server = "dhcp01"
logs = []
svc.log = lambda t, e=False: logs.append(t)
base = {"scope": {"id": "10.1.0.0", "mask": "255.255.255.0", "name": "Büro", "desc": "", "state": "Active",
                  "start": "10.1.0.10", "end": "10.1.0.200", "lease": 86400},
        "stat": {"in_use": 1}, "exclusions": [{"start": "10.1.0.50", "end": "10.1.0.60"}],
        "options": [{"id": 3, "values": ["10.1.0.1"], "vendor": "", "user": ""}],
        "reservations": [{"ip": "10.1.0.20", "cid": "00-11", "name": "drucker", "desc": "", "type": "Dhcp"}],
        "dns": {"dyn": "Always"}, "leases": [{"ip": "10.1.0.99"}]}
same = copy.deepcopy(base)
same["stat"] = {"in_use": 42}
same["leases"] = []
check("Leases/Statistik zählen nicht als Änderung", svc.diff_config(svc.config_of(base), svc.config_of(same)) == [])
new = copy.deepcopy(base)
new["scope"]["end"] = "10.1.0.220"
new["exclusions"] = [{"start": "10.1.0.70", "end": "10.1.0.80"}]
new["options"] = [{"id": 3, "values": ["10.1.0.254"], "vendor": "", "user": ""},
                  {"id": 1, "values": ["1"], "vendor": "MSFT", "user": ""}]
new["reservations"][0]["cid"] = "00-22"
new["dns"] = {"dyn": "Never"}
d = svc.diff_config(svc.config_of(base), svc.config_of(new))
for line in d:
    print("   ", line)
check("alle Unterschiede erkannt (Pool, 2 Ausschlüsse, 2 Optionen, Reservierung, DNS)", len(d) == 7)
check("Herstelleroption mit Klasse", any("001 [MSFT]" in x for x in d))

EVENTS = [
    {"record": 3, "text": "Reservierung 10.1.0.21 im Bereich hinzugefügt", "user": "A", "time": "2026-10-23 11:00:00"},
    {"record": 2, "text": "Bereich 10.1.0.0 geändert", "user": "B", "time": "2026-10-23 10:59:00"},
    {"record": 1, "text": "Bereich 10.9.0.0 geändert", "user": "C", "time": "2026-10-23 10:58:00"},
    {"record": 0, "text": "Serveroption 6 geändert", "user": "D", "time": "2026-10-23 10:57:00"}]
svc.backend = type("B", (), {"call": staticmethod(lambda cmd, args=None, prog=None: {"items": EVENTS})})()
check("alle Ereignisse", len(svc.change_events("x")) == 4)
check("nur dieser Scope (Scope-ID und Adressen darin)",
      [e["record"] for e in svc.change_events("x", "10.1.0.0", "255.255.255.0")] == [3, 2])


def boom(cmd, args=None, prog=None):
    raise S.HostError("@RPC:events:dhcp01:5:Zugriff verweigert")
svc.backend = type("B", (), {"call": staticmethod(boom)})()
r1, r2 = svc.change_events("x"), svc.change_events("x")
check("Protokoll nicht lesbar: leer, nur einmal gemeldet", r1 == [] and r2 == [] and len(logs) == 1 and svc.events_error)
print("   ", logs[0])
try:
    svc.events("dhcp01", "x")
except S.EventLogError as e:
    check(f"EventLogError mit Code {e.code}", e.code == 5)

# Lesehilfe
sc = [("10.1.0.0", "255.255.255.0"), ("10.2.0.0", "255.255.0.0")]
for text, want in (("Reservierung 10.1.0.21 wurde im Bereich 10.1.0.0 hinzugefügt.", ("reservation", "create", "10.1.0.0", "10.1.0.21")),
                   ("Scope 10.2.0.0 was deleted.", ("scope", "delete", "10.2.0.0", "")),
                   ("The option value for option 6 was modified in scope 10.1.0.0", ("option", "change", "10.1.0.0", "006")),
                   ("Failover relationship a-b was modified", ("failover", "change", "", "")),
                   ("Optionsdefinition 250 wurde erstellt", ("optiondef", "create", "", "250")),
                   ("Reservation 10.2.5.7 removed", ("reservation", "delete", "10.2.0.0", "10.2.5.7"))):
    c = E.classify({"text": text}, sc)
    check(f"Lesehilfe: {text} -> {c}", (c["area"], c["action"], c["scope"], c["obj"]) == want)
c = E.classify({"text": "", "fields": [("ScopeId", "10.1.0.0"), ("ReservedIP", "10.1.0.9"), ("Op", "deleted reservation")]}, sc)
check(f"Lesehilfe aus Ereignisdaten: {c}", c["area"] == "reservation" and c["scope"] == "10.1.0.0" and c["obj"] == "10.1.0.9")
check(f"Feldnamen: {ev['fields']}", ev["fields"][:2] == [("ScopeName", "Büro"), ("ScopeId", "10.1.0.0")] and ev["level"] == 4)

print("\nALLES OK" if ok else "\nFEHLER")
sys.exit(0 if ok else 1)
