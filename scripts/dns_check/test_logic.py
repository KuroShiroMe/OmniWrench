"""MS DNS Extended Management ohne Windows prüfen: Namen/Reverse/IPv6, Befunde, Transaktionen, Konflikte.

    python scripts/dns_check/test_logic.py
"""
import copy
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.dns_check.fake_backend import FakeBackend, REV4, REV6, DOM  # noqa: E402
from tools.ms_dns_extended import checks as ck  # noqa: E402
from tools.ms_dns_extended import dnsutil as du  # noqa: E402
from tools.ms_dns_extended import eventlog  # noqa: E402
from tools.ms_dns_extended import service as S  # noqa: E402

LOC = json.loads((ROOT / "tools/ms_dns_extended/locales/de.json").read_text(encoding="utf-8"))
MISSING: set[str] = set()


def tr(key, *a, **kw):
    t = LOC.get(key)
    if t is None:
        MISSING.add(key)
        return key
    return t.format(**kw)


DC1 = "dc01.corp.example"
OK = 0


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def svc_new(fb=None):
    fb = fb or FakeBackend()
    svc = S.DnsService(fb, tr)
    svc.connect(DC1)
    svc.load_all()
    for z in (DOM, REV4, REV6):
        svc.load_zone(DC1, z)
    return svc, fb


def server_state(fb, zone):
    return sorted(r.key + f"|{r.ttl}|{r.dynamic}" for r in fb.data[DC1]["recs"][zone])


# --- dnsutil -----------------------------------------------------------------------------------------
def test_names():
    check(du.ptr_name("10.10.20.42") == "42.20.10.10.in-addr.arpa", "ptr v4")
    p6 = du.ptr_name("2001:db8:10::77")
    check(p6.endswith(".ip6.arpa") and len(p6.split(".")) == 34, "ptr v6 nibbles")
    check(du.ip_from_ptr(p6) == "2001:db8:10::77", "ip_from_ptr v6")
    check(du.ip_from_ptr("42.20.10.10.in-addr.arpa") == "10.10.20.42", "ip_from_ptr v4")
    check(du.ip_from_ptr("20.10.10.in-addr.arpa") is None, "partial ptr")
    check(du.reverse_zone_for("192.168.10.0/24") == "10.168.192.in-addr.arpa", "rev /24")
    check(du.reverse_zone_for("10.0.0.0/8") == "10.in-addr.arpa", "rev /8")
    check(du.reverse_zone_for("172.16.0.0/16") == "16.172.in-addr.arpa", "rev /16")
    check(du.reverse_zone_for("2001:db8:10::/48") == REV6, "rev v6 /48")
    check(du.reverse_zone_network(REV6) == "2001:db8:10::/48", "net from v6 zone")
    check(du.reverse_zone_network("10.10.in-addr.arpa") == "10.10.0.0/16", "net from v4 zone")
    check(du.best_zone(du.ptr_name("2001:db8:10:20::77"), [REV6, REV4]) == REV6, "best zone v6")
    check(du.best_zone("a.b.corp.example", [DOM, "b.corp.example"]) == "b.corp.example", "best zone longest")
    check(du.relative(DOM, DOM) == "@" and du.relative("pc1." + DOM, DOM) == "pc1", "relative")
    for good in ("pc-01", "_ldap._tcp", "*", "a" * 63):
        check(du.valid_hostname(good) or good.startswith("_") or good == "*", f"valid {good}")
    check(not du.valid_hostname("bad name"), "space invalid")
    check(du.parse_ttl("1h") == 3600 and du.parse_ttl("30m") == 1800 and du.parse_ttl("1d") == 86400, "parse ttl")
    try:
        du.parse_ttl("x")
        check(False, "parse ttl invalid")
    except ValueError:
        pass
    for sec in (0, 59, 3600, 86400, 90061, 604800):
        check(du.parse_ttl(du.fmt_ttl(sec)) == sec, f"ttl round trip {sec}")
    ts = du.ts_from_hours(3_500_000)
    check(du.hours_from_ts(ts) == 3_500_000, "timestamp round trip")
    check(du.ts_from_hours(0) is None, "static")


def test_text_repr():
    cases = [
        (du.Rec(DOM, "pc1." + DOM, "A", {"ip": "10.1.1.1"}, 1200), "pc1.corp.example", "A", "10.1.1.1"),
        (du.Rec(DOM, "pc1." + DOM, "AAAA", {"ip": "2001:db8::1"}, 1200), "pc1.corp.example", "AAAA", "2001:db8::1"),
        (du.Rec(DOM, "www." + DOM, "CNAME", {"host": "web." + DOM}), "www.corp.example", "CNAME", "web.corp.example."),
        (du.Rec(DOM, DOM, "MX", {"pref": 10, "host": "mail." + DOM}), "corp.example", "MX", "10 mail.corp.example."),
        (du.Rec(DOM, "_ldap._tcp." + DOM, "SRV", {"priority": 0, "weight": 100, "port": 389, "host": "dc." + DOM}),
         "_ldap._tcp.corp.example", "SRV", "0 100 389 dc.corp.example."),
        (du.Rec(DOM, DOM, "TXT", {"text": 'v=spf1 -all "zitiert"' + "x" * 300}), "corp.example", "TXT", '"v=spf1 -all \\"zitiert\\"'),
    ]
    for rec, owner, t, frag in cases:
        txt = du.text_representation(rec)
        check(txt.split()[0].rstrip(".") == owner and f" IN {t} " in txt and frag in txt, f"text repr {txt}")
    txt = du.text_representation(cases[-1][0])
    check(du.txt_unquote(txt.split(" IN TXT ", 1)[1]) == cases[-1][0].data["text"], "txt round trip")
    check(txt.count('" "') == 1, "TXT in 255er-Stücke geteilt")


def test_validate():
    check(du.validate_data("A", {"ip": "10.1.1.1"}, tr) is None, "A ok")
    check(du.validate_data("A", {"ip": "2001:db8::1"}, tr) == tr("val.ipv4"), "A v6 rejected")
    check(du.validate_data("AAAA", {"ip": "10.1.1.1"}, tr) == tr("val.ipv6"), "AAAA v4 rejected")
    check(du.validate_data("MX", {"pref": "x", "host": "m." + DOM}, tr) is not None, "MX pref number")
    check(du.validate_data("SRV", {"priority": 0, "weight": 0, "port": 70000, "host": "a." + DOM}, tr) is not None,
          "SRV port range")
    check(du.validate_data("CNAME", {"host": "bad host"}, tr) == tr("val.host"), "CNAME host")


# --- Befunde -----------------------------------------------------------------------------------------
def test_findings():
    svc, fb = svc_new()
    res = svc.scan(DC1, True)
    texts = {f.text for f in res["findings"]}
    keys = {(f.area, f.level) for f in res["findings"]}

    def has(key, **kw):
        check(tr(key, **kw) in texts, f"Befund fehlt: {tr(key, **kw)}")
    has("chk.cname_dangling", zone=DOM, name="old-app." + DOM, target="app-gone." + DOM)
    has("chk.cname_chain", zone=DOM, name="intranet." + DOM, target="www." + DOM)
    has("chk.a_no_ptr", zone=DOM, name="nas." + DOM, ip="10.10.3.5")
    has("chk.a_no_ptr", zone=DOM, name="nb-anna." + DOM, ip="2001:db8:10:20::77")
    has("chk.ptr_target_missing", zone=REV4, ip="10.10.20.50", target="pc-0050." + DOM)
    has("chk.ptr_stale", zone=REV4, ip="10.10.9.9", target=DC1, have="10.10.0.10")
    has("chk.dup_ip_dynamic", zone=DOM, name="pc-0199." + DOM, ip="10.10.20.42", other="pc-0142." + DOM)
    has("chk.underscore", zone=DOM, name="printer_3og." + DOM)
    has("chk.ttl_zero", zone=DOM, name="test." + DOM)
    has("chk.xfer_any", zone="legacy.example")
    has("chk.forwarder_down", server=DC1, ip="1.1.1.1", error="Timeout")
    has("chk.ns_serial", zone=DOM, serial=4711, behind="dc02.corp.example (4710)")
    check(not any("dc01.corp.example (10.10.0.10)" in t for t in texts), "kein PTR-Befund für dc01 (PTR vorhanden)")
    check(("ptr", "warning") in keys, "PTR-Kategorie")
    # Aufräum-Vorschau: pc-0143 (20 Tage) und pc-0199 (40 Tage) bei 7+7 Tagen
    z = svc.zones[DC1][DOM]
    prev = ck.scavenge_preview(z, svc.records(DC1, DOM), svc.servers[DC1])
    names = {p["rec"].name for p in prev}
    check({"pc-0143." + DOM, "pc-0199." + DOM} <= names and "pc-0142." + DOM not in names, f"scavenge {names}")
    # DHCP-Abgleich
    svc.dhcp_server = "dhcp01"
    d = svc.dhcp_compare(DC1)
    dtexts = {f.text for f in d["findings"]}
    check(tr("chk.lease_no_dns", name="pc-0188." + DOM, ip="10.10.20.88") in dtexts, "lease ohne DNS")
    check(tr("chk.dns_no_lease", name="pc-0143." + DOM, ip="10.10.20.43") in dtexts, "DNS ohne Lease")
    check(not any("pc-0142" in t for t in dtexts), "pc-0142 passt")
    # Vergleich mit dc02
    svc.add_server("dc02.corp.example")
    cmp = svc.compare(probe=True)
    ctexts = [f.text for f in cmp["findings"]]
    check(any(tr("srv.forwarders") in t for t in ctexts), "Weiterleitungen unterscheiden sich")
    check(any("legacy" in t for t in ctexts) is False, "dateibasierte Zone nicht als fehlende AD-Zone")
    check(any(tr("chk.serial_diff", zone_name=DOM, values="").split(":")[0] in t for t in ctexts), "Seriennummern")


# --- Transaktionen -----------------------------------------------------------------------------------
def test_tx_create_with_ptr_rollback():
    svc, fb = svc_new()
    before4, beforeD = server_state(fb, REV4), server_state(fb, DOM)
    a = du.Rec(DOM, "neu." + DOM, "A", {"ip": "10.10.30.5"}, 1200)
    ptr = svc.ptr_for(DC1, a)
    check(ptr is not None and ptr.zone == REV4 and ptr.name == "5.30.10.10.in-addr.arpa", "ptr_for v4")
    fb.fail = ("create_record", lambda args: args[0].type == "PTR")
    try:
        svc.atomic("t", lambda: (svc.create_record(DC1, a), svc.create_record(DC1, ptr)))
        check(False, "Fehler erwartet")
    except S.TxError as e:
        check(e.undone == 1 and not e.fails, f"eine Rücknahme {e.undone} {e.fails}")
    check(server_state(fb, DOM) == beforeD and server_state(fb, REV4) == before4, "Server unverändert")


def test_tx_ptr_v6():
    svc, fb = svc_new()
    a = du.Rec(DOM, "v6host." + DOM, "AAAA", {"ip": "2001:db8:10:30::5"}, 1200)
    ptr = svc.ptr_for(DC1, a)
    check(ptr is not None and ptr.zone == REV6, "ptr_for v6")
    svc.atomic("t", lambda: (svc.create_record(DC1, a), svc.create_record(DC1, ptr)))
    check(any(r.name == ptr.name and r.type == "PTR" for r in fb.data[DC1]["recs"][REV6]), "v6-PTR angelegt")
    check(any(r.key == ptr.key for r in svc.records(DC1, REV6)), "Zwischenspeicher aktualisiert")


def test_replace_rollback():
    svc, fb = svc_new()
    old = next(r for r in svc.records(DC1, DOM) if r.name == "nas." + DOM)
    new = copy.deepcopy(old)
    new.data["ip"] = "10.10.3.6"
    before = server_state(fb, DOM)
    fb.fail = ("create_record", lambda args: args[0].data.get("ip") == "10.10.3.6")
    try:
        svc.replace_record(DC1, old, new)
        check(False, "Fehler erwartet")
    except S.TxError:
        pass
    check(server_state(fb, DOM) == before, "alter Eintrag wiederhergestellt")


def test_bulk_ttl_rollback_partial():
    svc, fb = svc_new()
    recs = [r for r in svc.records(DC1, DOM) if r.type == "A" and not r.dynamic][:4]
    before = server_state(fb, DOM)
    fb.fail = ("create_record", lambda args: args[0].name == recs[2].name and args[0].ttl == 60)
    try:
        svc.atomic("ttl", lambda: svc.bulk_ttl(DC1, recs, 60))
        check(False, "Fehler erwartet")
    except S.TxError as e:
        check(e.undone == 5 and not e.fails, f"5 Schritte zurück ({e.undone})")
    check(server_state(fb, DOM) == before, "TTL-Änderungen zurückgenommen")


def test_zone_settings_and_create():
    svc, fb = svc_new()
    z = DOM
    fb.fail = "set_transfers"
    try:
        svc.atomic("z", lambda: (svc.set_zone(DC1, z, {"aging": False, "allow_update": du.UPDATE_ANY}),
                                 svc.set_transfers(DC1, z, du.XFER_ANY, [], du.NOTIFY_OFF, [])))
        check(False, "Fehler erwartet")
    except S.TxError:
        pass
    zs = fb.data[DC1]["zones"][z]
    check(zs["aging"] is True and zs["allow_update"] == du.UPDATE_SECURE, "Zoneneinstellung zurück")
    # Neue IPv6-Reverse-Zone, danach scheitert ein Eintrag -> Zone wird wieder gelöscht
    name = du.reverse_zone_for("2001:db8:99::/48")
    fb.fail = "create_record"
    try:
        svc.atomic("nz", lambda: (svc.create_zone(DC1, name, du.ZONE_PRIMARY, True),
                                  svc.create_record(DC1, du.Rec(name, du.ptr_name("2001:db8:99::1"), "PTR",
                                                                {"host": "x." + DOM}))))
        check(False, "Fehler erwartet")
    except S.TxError:
        pass
    check(name not in fb.data[DC1]["zones"], "neue Zone zurückgenommen")


def test_conflict():
    svc, fb = svc_new()
    rec = next(r for r in svc.records(DC1, DOM) if r.name == "nas." + DOM)
    check(svc.guard(DC1, DOM, [rec]) == [], "kein Konflikt")
    # jemand anderes löscht nas und legt neu.corp.example an
    fb.delete_record(DC1, rec)
    other = du.Rec(DOM, "neu." + DOM, "A", {"ip": "10.10.30.9"}, 1200)
    fb.create_record(DC1, other)
    lines = svc.guard(DC1, DOM, [rec], [other])
    check(tr("conflict.gone", rec=svc._label(rec)) in lines and tr("conflict.exists", rec=svc._label(other)) in lines,
          f"Konflikte {lines}")
    check(not svc.zone_changed(DC1, DOM), "nach guard neu geladen")
    before = [r for r in svc.records(DC1, DOM)]
    fb.create_record(DC1, du.Rec(DOM, "x." + DOM, "A", {"ip": "10.10.30.10"}, 1200))
    diff = svc.diff_zone(before, fb.records(DC1, DOM))
    check(diff == [tr("diff.added", rec="x.corp.example A 10.10.30.10")], f"diff {diff}")


def test_events():
    svc, fb = svc_new()
    evs = svc.change_events(DC1, "2000-01-01T00:00:00Z")
    check(evs[0]["area"] == "record" and evs[0]["action"] == "create" and evs[0]["zone"] == DOM, f"classify {evs[0]}")
    check(evs[2]["area"] == "server", "server event")
    who = svc.who_changed(DC1, DOM, du.now_utc() - _dt.timedelta(days=2))
    check(any("admin.meier" in w for w in who), "wer")
    check(eventlog.CHANNEL == "Microsoft-Windows-DNSServer/Audit", "Kanal")


def test_search():
    svc, fb = svc_new()
    check({r.name for r in svc.search("10.10.20.42")} >= {"pc-0142." + DOM, "pc-0199." + DOM}, "Suche IP")
    check(any(r.type == "AAAA" for r in svc.search("2001:db8:10::/48")), "Suche v6-Netz")
    check(any(r.name == "nb-anna." + DOM for r in svc.search("anna")), "Suche Name")


def test_host_text():
    svc, fb = svc_new()
    t = svc.host_text("@ERR:access:dc09|80070005|Zugriff verweigert")
    check("dc09" in t and "0x80070005" not in t and "80070005" in t, t)
    t = svc.host_text("@WMI:create:dc01:80041001:Generic failure")
    check(tr("wmi.op.create") in t and "0x80041001" in t, t)
    try:
        svc.connect("unbekannt")
        check(False, "Fehler erwartet")
    except S.UserError as e:
        check("unbekannt" in str(e), str(e))


def test_wmi_query_forward_only():
    """ExecQuery mit wbemFlagForwardOnly kennt kein Count: list() würde vorab len() fragen und scheitern."""
    from tools.ms_dns_extended import wmidns

    class ForwardOnlySet:   # verhält sich wie CDispatch um SWbemObjectSet (Count -> E_FAIL)
        def __init__(self, items):
            self.items = items

        def __len__(self):
            raise RuntimeError("Count bei wbemFlagForwardOnly nicht verfügbar (0x80004005)")

        def __getitem__(self, i):
            return self.items[i]

    class Svc:
        def ExecQuery(self, wql, lang, flags):
            check(flags == wmidns.WBEM_FLAGS, "Abfrage-Flags")
            return ForwardOnlySet(["a", "b"])

    w = wmidns.WmiServer("dc01")
    w._svc = lambda: Svc()
    check(w._query("SELECT * FROM MicrosoftDNS_Zone") == ["a", "b"], "Abfrage ohne Count")


def test_wmi_create_fallback():
    """Eintrag anlegen: erst PropertyData, bei 0x80041001 weiter zur Textdarstellung bzw. zum eingegebenen Namen."""
    from tools.ms_dns_extended import wmidns

    w = wmidns.WmiServer("dc01")
    w.wmi_name = "dc01.corp.example"
    calls = []

    def call(target, method, params=None, op="write", cls=None):
        calls.append((target, method, params["DnsServerName"]))
        if len(calls) < fail_until:
            raise wmidns.HostError("@WMI:create:dc01:80041001:Allgemeiner Fehler")

    w._call = call
    w.exists = lambda rec: False
    rec = du.Rec(zone=DOM, name="neu." + DOM, type="A", data={"ip": "10.10.9.9"}, ttl=3600)
    fail_until = 2
    w.create_record(rec)
    check(calls[0][:2] == ("MicrosoftDNS_AType", "CreateInstanceFromPropertyData"), "zuerst PropertyData")
    check(calls[1][2] == "dc01" and len(calls) == 2, "danach eingegebener Servername")
    calls.clear()
    fail_until = 99
    try:
        w.create_record(rec)
        check(False, "Fehler erwartet")
    except wmidns.HostError as e:
        check("80041001" in str(e), str(e))
    check([c[1] for c in calls].count("CreateInstanceFromTextRepresentation") == 2 and len(calls) == 4,
          "alle Wege versucht")
    calls.clear()
    fail_until = 99
    w.exists = lambda rec: True        # Server meldet Fehler, hat den Eintrag aber angelegt
    w.create_record(rec)
    check(len(calls) == 1, "kein zweiter Versuch, wenn der Eintrag existiert")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok ", t.__name__)
    if MISSING:
        print("FEHLENDE SPRACHSCHLÜSSEL:", sorted(MISSING))
        sys.exit(1)
    print(f"{OK} Prüfungen bestanden")
