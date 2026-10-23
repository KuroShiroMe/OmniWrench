"""Transaktionen/Rücknahme ohne Windows prüfen: zustandsbehafteter Fake-Server, Fehler mitten im Ablauf.

    python3 scripts/dhcp_api_check/test_tx.py
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.ms_dhcp_extended import service as S  # noqa: E402
from tools.ms_dhcp_extended.backend import HostError  # noqa: E402
from tools.ms_dhcp_extended.runner import Job  # noqa: E402

SID = "10.1.0.0"


class FakeServer:
    """Ein DHCP-Server im Speicher; `fail` = Cmdlet-Name (oder (Name, Bedingung)), der einmal scheitern soll."""

    def __init__(self):
        self.scopes = {SID: {"ScopeId": SID, "SubnetMask": "255.255.255.0", "Name": "Büro", "Description": "",
                             "State": "Active", "StartRange": "10.1.0.10", "EndRange": "10.1.0.200", "LeaseDuration": 86400}}
        self.excl = {SID: [("10.1.0.10", "10.1.0.19"), ("10.1.0.250", "10.1.0.254")]}
        self.opts = {(SID, 3, "", ""): ["10.1.0.1"], (None, 6, "", ""): ["10.0.0.5"]}
        self.res = {SID: {"10.1.0.20": {"IPAddress": "10.1.0.20", "ClientId": "00-11-22-33-44-55", "Name": "drucker",
                                        "Description": "", "Type": "Dhcp"}}}
        self.fail = None
        self.calls = []

    def state(self):
        return copy.deepcopy((self.scopes, {k: sorted(v) for k, v in self.excl.items()}, self.opts, self.res))

    def call(self, cmd, args, _cb=None):
        assert cmd == "cim", cmd
        n, p = args["name"], dict(args["params"])
        self.calls.append(n)
        f = self.fail
        if f and (f == n or (isinstance(f, tuple) and f[0] == n and f[1](p))):
            self.fail = None
            raise HostError(f"Fake: {n} scheitert")
        sid = p.get("ScopeId")
        if n == "Get-DhcpServerv4Scope":
            return {"items": [dict(s) for k, s in self.scopes.items() if not sid or k == sid]}
        if n == "Set-DhcpServerv4Scope":
            s = self.scopes[sid]
            for k, v in p.items():
                s[k] = v["__ts"] if isinstance(v, dict) and "__ts" in v else v
            return {}
        if n == "Remove-DhcpServerv4Scope":
            del self.scopes[sid]
            self.excl.pop(sid, None)
            return {}
        if n == "Add-DhcpServerv4ExclusionRange":
            self.excl.setdefault(sid, []).append((p["StartRange"], p["EndRange"]))
            return {}
        if n == "Remove-DhcpServerv4ExclusionRange":
            self.excl[sid].remove((p["StartRange"], p["EndRange"]))
            return {}
        if n == "Get-DhcpServerv4OptionValue":
            return {"items": [{"OptionId": k[1], "Value": v, "VendorClass": k[2], "UserClass": k[3]}
                              for k, v in self.opts.items() if k[0] == sid]}
        key = (sid, int(p.get("OptionId", 0)), p.get("VendorClass") or "", p.get("UserClass") or "")
        if n == "Set-DhcpServerv4OptionValue":
            self.opts[key] = list(p["Value"])
            return {}
        if n == "Remove-DhcpServerv4OptionValue":
            if key not in self.opts:
                raise HostError("Option nicht vorhanden")
            del self.opts[key]
            return {}
        if n == "Get-DhcpServerv4Reservation":
            return {"items": [dict(r) for r in self.res.get(sid, {}).values()]}
        if n == "Add-DhcpServerv4Reservation":
            self.res.setdefault(sid, {})[p["IPAddress"]] = {k: p.get(k, "") for k in
                                                           ("IPAddress", "ClientId", "Name", "Description", "Type")}
            return {}
        if n == "Remove-DhcpServerv4Reservation":
            del self.res[sid][p["IPAddress"]]
            return {}
        raise AssertionError(n)


srv = FakeServer()
svc = S.DhcpService(srv, lambda k, d=None, **kw: f"{k}{kw}" if kw else k)
svc.server = "dhcp01"
svc.log = lambda text, err=False: print("   log:", text)
ok = True


def check(label, cond):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FEHL ") + label)


# 1) Pool verkleinern: Ausschluss außerhalb entfernen, dann Bereich setzen -> Bereich scheitert
before = srv.state()
srv.fail = "Set-DhcpServerv4Scope"


def save():
    svc.excl_remove(SID, "10.1.0.250", "10.1.0.254")
    svc.scope_set(SID, StartRange="10.1.0.20", EndRange="10.1.0.240")
try:
    svc.atomic("pool", save)
    check("Pool: Fehler erwartet", False)
except S.TxError as e:
    check(f"Pool: TxError, {e.undone} Schritt(e) zurück, keine Fehlschläge", e.undone == 1 and not e.fails)
check("Pool: Ausschluss wieder da, Stand unverändert", srv.state() == before)

# 2) Mehrere Optionen entfernen, die dritte scheitert -> die ersten beiden kommen zurück
srv.opts[(SID, 15, "", "")] = ["firma.de"]
srv.opts[(SID, 42, "", "")] = ["10.0.0.1"]
before = srv.state()
srv.fail = ("Remove-DhcpServerv4OptionValue", lambda p: p["OptionId"] == 42)


def rm_opts():
    for oid in (3, 15, 42):
        svc.opt_remove(SID, oid)
try:
    svc.atomic("opts", rm_opts)
except S.TxError as e:
    check(f"Optionen: {e.undone} zurück", e.undone == 2 and not e.fails)
check("Optionen: alle wieder da", srv.state() == before)

# 3) Reservierung überschreiben (entfernen + neu anlegen), Anlegen scheitert -> alte Reservierung zurück
before = srv.state()
srv.fail = "Add-DhcpServerv4Reservation"


def overwrite():
    svc.res_remove(SID, "10.1.0.20")
    svc.res_add(SID, {"ip": "10.1.0.20", "cid": "aa-bb-cc-dd-ee-ff", "name": "neu", "desc": "", "type": "Dhcp"})
try:
    svc.atomic("res", overwrite)
except S.TxError:
    pass
check("Reservierung: alte wieder da (inkl. Name)", srv.state() == before)

# 4) Verschachtelt: innere Transaktion gelingt, äußere scheitert danach -> auch die innere wird zurückgenommen
before = srv.state()
srv.fail = ("Set-DhcpServerv4OptionValue", lambda p: p["OptionId"] == 66)


def outer():
    svc.atomic("inner", lambda: svc.excl_add(SID, "10.1.0.100", "10.1.0.110"))
    svc.opt_set(SID, 66, ["tftp"])
try:
    svc.atomic("outer", outer)
except S.TxError as e:
    check(f"Verschachtelt: {e.undone} zurück", e.undone == 1)
check("Verschachtelt: Ausschluss der inneren Transaktion entfernt", srv.state() == before)
check("Kein offenes Journal mehr", svc._tx is None)

# 5) Rücknahme selbst scheitert -> Teilergebnis wird gemeldet
srv.fail = "Set-DhcpServerv4Scope"
calls = []


def two():
    svc.excl_add(SID, "10.1.0.120", "10.1.0.121")
    srv.fail = "Remove-DhcpServerv4ExclusionRange"      # die Gegenoperation scheitert
    raise S.UserError("Absicht")
try:
    svc.atomic("partial", two)
except S.TxError as e:
    check("Teil-Rücknahme gemeldet", len(e.fails) == 1 and "tx.partial" in str(e))
srv.excl[SID].remove(("10.1.0.120", "10.1.0.121"))

# 6) Ablauf der Oberfläche (Generator wie im Runner): Fehler im 2. Job -> Rücknahme-Job, TxError an den Aufrufer
from tools.ms_dhcp_extended.tool import MsDhcpExtended  # noqa: E402


class Ctl:
    tr = staticmethod(svc.tr)
    queue = []

    def __init__(self):
        self.svc = svc

    def _rollback_flow(self, tx):       # wie im Tool, nur ohne Meldungsfenster
        return (yield Job(lambda: svc.tx_rollback(tx), "rollback"))


ctl = Ctl()
before = srv.state()


def flow():
    yield Job(lambda: svc.excl_remove(SID, "10.1.0.10", "10.1.0.19"), "x")
    yield Job(lambda: svc.opt_remove(SID, 999), "y")       # gibt es nicht -> Fehler


def drive(gen):
    """Mini-Runner: Jobs synchron ausführen, Fehler per throw zurückgeben."""
    val, exc = None, None
    while True:
        try:
            job = gen.throw(exc) if exc else gen.send(val)
        except StopIteration as st:
            return st.value
        val, exc = None, None
        try:
            val = job.fn()
        except Exception as e:  # noqa: BLE001
            exc = e
try:
    drive(MsDhcpExtended.atomic(ctl, "ui", flow()))
    check("UI: Fehler erwartet", False)
except S.TxError as e:
    check("UI: TxError mit Rücknahme", e.undone == 1)
check("UI: Ausschluss wieder da", srv.state() == before)

# 7) UI-Ablauf abgebrochen (close) -> Rücknahme wird als eigener Ablauf eingereiht
g = MsDhcpExtended.atomic(ctl, "abbruch", flow())
job = g.send(None)
job.fn()
g.close()
check("Abbruch: Rücknahme eingereiht", len(ctl.queue) == 1 and svc._tx is None)
check("Abbruch: Ausschluss noch weg (bis Rücknahme läuft)", (("10.1.0.10", "10.1.0.19") not in srv.excl[SID]))
rb = ctl.queue.pop(0)
fails = rb.send(None).fn()
check("Abbruch: Rücknahme ohne Fehler", fails == [] and srv.state() == before)

print("\nALLES OK" if ok else "\nFEHLER")
sys.exit(0 if ok else 1)
