"""DHCPv6-Abläufe von dhcpapi.py/service.py gegen die Fake-dhcpsapi (fake_dhcpsapi6.c) prüfen.

    gcc -shared -fPIC -o libfake.so fake_dhcpsapi.c fake_dhcpsapi6.c
    python3 test_api6.py ./libfake.so
"""
import ctypes
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.ms_dhcp_extended import checks as ck  # noqa: E402
from tools.ms_dhcp_extended import checks6 as ck6  # noqa: E402
from tools.ms_dhcp_extended import dhcpapi as A  # noqa: E402
from tools.ms_dhcp_extended import service as S  # noqa: E402
from tools.ms_dhcp_extended.backend import ApiBackend  # noqa: E402

lib = ctypes.CDLL(sys.argv[1] if len(sys.argv) > 1 else "./libfake.so")
A._lib = A.setup(lib)
b = ApiBackend()
svc = S.DhcpService(b, lambda k, d=None, **kw: f"{k}{kw}" if kw else k, lambda t, e=False: print("  LOG", "!" if e else "", t))
b.call("connect", {"server": "dhcp01", "primary": True}, lambda *_: None)
svc.server = "dhcp01"
P1, P2, NEW = "2001:db8:1::", "2001:db8:2::", "2001:db8:9::"
fails = []


def check(label, got, want):
    ok = got == want
    print(("OK  " if ok else "FEHLER"), label, "->", got if ok else f"{got!r} (erwartet {want!r})")
    if not ok:
        fails.append(label)


def ival(name):
    return ctypes.c_int.in_dll(lib, name)


# --- Lesen
svc.load_all()
check("scopes6", [s["id"] for s in svc.scopes6], [P1, P2])
s1 = svc.scope_row(P1)
check("scope felder", (s1["name"], s1["plen"], s1["state"], s1["lease_pref"], s1["lease_valid"], s1["rapid"], s1["unicast"]),
      ("Büro v6", 64, "Active", 8 * 86400, 12 * 86400, True, False))
check("scope2 inaktiv", svc.scope_row(P2)["state"], "InActive")
check("stats", (svc.scope_info6[P1]["stat"]["in_use"], svc.scope_info6[P1]["stat"]["pending"]), (2, 1))
check("ausschluss overview", svc.scope_info6[P1]["exclusions"], [("2001:db8:1::10", "2001:db8:1::20")])
check("defs6 ohne interne", sorted(k[1] for k in svc.defs6), [23, 24])
check("server-optionen6", svc.server_options6, {23: ["2001:db8::53"]})
d = svc.get_scope(P1)
check("optionen scope (ohne 0x20001)", [(o["id"], o["values"]) for o in d["options"]], [(24, ["firma.local"])])
check("reservierung", [(r["ip"], r["duid"], r["iaid"], r["name"], r["desc"]) for r in d["reservations"]],
      [("2001:db8:1::50", "00-01-00-01-2c-4f-11-22-00-15-5d-01-02-03", 0x0e00155d, "drucker", "Reserviert")])
check("leases", sorted((x["ip"], x["state"], x["type"], x["host"]) for x in d["leases"]),
      [("2001:db8:1::1234", "Active", "IANA", "pc02.firma.local"), ("2001:db8:1::50", "ActiveReservation", "IANA", "drucker")])
check("bindungen", svc.server_info6()["bindings"], [{"state": True, "alias": "Ethernet0", "ip": "2001:db8:1::1"}])

# --- Schreiben
svc.scope6_set(P1, Name="Büro neu", Preference=7, State="InActive")
r = svc.get_scope(P1)["scope"]
check("set name/pref/state", (r["name"], r["pref"], r["state"]), ("Büro neu", 7, "InActive"))
n0 = ctypes.c_uint32.in_dll(lib, "cfg_calls").value
svc.scope6_set(P1, PreferredLifetime=20 * 86400, ValidLifetime=30 * 86400)     # beide größer: erst gültig, dann bevorzugt
r = svc.get_scope(P1)["scope"]
check("lebensdauer vergrößern", (r["lease_pref"], r["lease_valid"], r["t1"], r["t2"]), (20 * 86400, 30 * 86400, 10 * 86400, 16 * 86400))
check("je feld ein aufruf", ctypes.c_uint32.in_dll(lib, "cfg_calls").value - n0, 2)
svc.scope6_set(P1, PreferredLifetime=3600, ValidLifetime=7200)                 # beide kleiner: erst bevorzugt
r = svc.get_scope(P1)["scope"]
check("lebensdauer verkleinern", (r["lease_pref"], r["lease_valid"]), (3600, 7200))
svc.scope6_set(P1, RapidCommit=False, Unicast=True)
r = svc.get_scope(P1)["scope"]
check("flags", (r["rapid"], r["unicast"]), (False, True))
try:
    svc.scope6_set(P1, PreferredLifetime=9000)
    check("bevorzugt >= gültig abgelehnt", "kein Fehler", "Fehler")
except S.UserError:
    check("bevorzugt >= gültig abgelehnt", "Fehler", "Fehler")

svc.excl6_add(P1, "2001:db8:1::100", "2001:db8:1::1ff")
check("ausschluss neu", sorted((x["start"], x["end"]) for x in svc.get_scope(P1)["exclusions"]),
      [("2001:db8:1::10", "2001:db8:1::20"), ("2001:db8:1::100", "2001:db8:1::1ff")])
svc.excl6_remove(P1, "2001:db8:1::10", "2001:db8:1::20")
check("ausschluss entfernt", [(x["start"], x["end"]) for x in svc.get_scope(P1)["exclusions"]], [("2001:db8:1::100", "2001:db8:1::1ff")])

svc.opt_set(P1, 23, ["2001:db8::1", "2001:db8::2"])
svc.opt_set(None, 24, ["firma.local", "corp.local"], v6=True)
check("option scope", [(o["id"], o["values"]) for o in svc.options(P1) if o["id"] == 23], [(23, ["2001:db8::1", "2001:db8::2"])])
check("option server", [(o["id"], o["values"]) for o in svc.options(v6=True) if o["id"] == 24], [(24, ["firma.local", "corp.local"])])
svc.opt_remove(P1, 24)
check("option entfernt", [o["id"] for o in svc.options(P1)], [23])

# Reservierung: ohne Client-Eintrag lässt sich der Name nicht setzen (Hinweis im Protokoll)
svc.res6_add(P1, {"ip": "2001:db8:1::60", "duid": "00-03-00-01-00-15-5d-aa-bb-cc", "iaid": 5, "name": "neu", "desc": ""})
check("reservierung neu", [(r["ip"], r["duid"], r["iaid"]) for r in svc.get_scope(P1)["reservations"] if r["ip"].endswith("::60")],
      [("2001:db8:1::60", "00-03-00-01-00-15-5d-aa-bb-cc", 5)])
svc.res6_set(P1, {"ip": "2001:db8:1::50", "duid": "00-01-00-01-2c-4f-11-22-00-15-5d-01-02-03", "iaid": 0x0e00155d,
                  "name": "drucker-eg", "desc": "neu"})
check("reservierung name", [(r["name"], r["desc"]) for r in svc.get_scope(P1)["reservations"] if r["ip"].endswith("::50")],
      [("drucker-eg", "neu")])
svc.res6_set(P1, {"ip": "2001:db8:1::60", "duid": "00-03-00-01-00-15-5d-aa-bb-dd", "iaid": 6, "name": "", "desc": ""})
check("reservierung duid/iaid", [(r["duid"], r["iaid"]) for r in svc.get_scope(P1)["reservations"] if r["ip"].endswith("::60")],
      [("00-03-00-01-00-15-5d-aa-bb-dd", 6)])
svc.res6_remove(P1, "2001:db8:1::60")
check("reservierung entfernt", [r["ip"] for r in svc.get_scope(P1)["reservations"]], ["2001:db8:1::50"])
svc.lease6_remove("2001:db8:1::1234")
check("lease entfernt", [x["ip"] for x in svc.get_scope(P1)["leases"]], ["2001:db8:1::50"])

sid = svc.scope6_add("2001:db8:9:0:1::/64", "Neu", "", 3, 3600, 7200, False)
check("scope neu (präfix normalisiert)", sid, NEW)
r = svc.get_scope(NEW)["scope"]
check("scope neu felder", (r["name"], r["pref"], r["state"], r["lease_pref"], r["lease_valid"]), ("Neu", 3, "InActive", 3600, 7200))
svc.def_add({"id": 1000, "name": "Eigene", "type": "IPv6Address", "multi": True, "vendor": "", "desc": "", "default": []}, v6=True)
svc.load_defs()
check("definition neu", svc.opt_def(1000, "", True)["type"], "IPv6Address")
svc.def_remove(1000, "", True)
svc.load_defs()
check("definition entfernt", svc.opt_def(1000, "", True), None)

# --- Transaktion: Scope + Ausschluss + Option + Aktivieren, der Ausschluss scheitert -> alles zurück
svc.load_overview()
before = [s["id"] for s in svc.scopes6]
w = ctypes.c_int.in_dll(lib, "w6_calls").value
ctypes.c_int.in_dll(lib, "w6_fail_at").value = w + 4


def work():
    s = svc.scope6_add("2001:db8:a::", "Tx", "", 0, 3600, 7200, False)
    svc.excl6_add(s, "2001:db8:a::1", "2001:db8:a::9")
    svc.opt_set(s, 23, ["2001:db8::53"])
    svc.scope6_set(s, State="Active")


try:
    svc.atomic("test", work)
    check("tx fehler", "kein Fehler", "Fehler")
except S.UserError as e:
    check("tx fehler", type(e).__name__, "TxError")
ctypes.c_int.in_dll(lib, "w6_fail_at").value = 0
svc.load_overview()
check("tx zurückgenommen", [s["id"] for s in svc.scopes6], before)

# --- Konfliktprüfung
a = svc.config_of(svc.get_scope(P1, False))
svc.scope6_set(P1, ValidLifetime=9000, Name="Fremd")
diffs = svc.diff_config(a, svc.config_of(svc.get_scope(P1, False)))
check("konflikt erkannt", len(diffs), 2)
print("   ", diffs)

# --- Prüfung: Scan mit beiden Familien
scan = svc.scan(True, False)
check("scan enthält v6", sorted(k for k in scan["scopes"] if ":" in k), [P1, P2, NEW])
fs = [f.text for f in scan["scopes"][P1]["findings"]]
print("    Befunde", P1, fs)
srv = [f.text for f in scan["server"] if "srv6" in f.text or "DHCPv6" in f.text]
print("    Server v6", srv)
chk = svc.checker()
f6 = ck6.scope_findings(chk, {"id": P1, "plen": 64, "name": "x", "state": "Active", "lease_pref": 7200, "lease_valid": 3600})
check("prüfung bevorzugt > gültig", [f.level for f in f6 if "s6_pref_valid" in f.text], [ck.ERROR])
print("\nFEHLER:", fails if fails else "keine")
sys.exit(1 if fails else 0)
