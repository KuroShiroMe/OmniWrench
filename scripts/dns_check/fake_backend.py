"""Fake-Backend für MS DNS Extended Management: DNS-Server im Speicher (ohne Windows/WMI).

Gleiche Schnittstelle wie tools/ms_dns_extended/backend.WmiBackend. Für Tests und Screenshots:

    from scripts.dns_check.fake_backend import FakeBackend
    MsDnsExtended.backend_factory = FakeBackend

`fail` = Methodenname (oder (Name, Bedingung(args))), der beim nächsten Aufruf einmal scheitert.
"""

from __future__ import annotations

import copy
import datetime as _dt
import threading

from tools.ms_dns_extended import dnsutil as du
from tools.ms_dns_extended.wmidns import HostError

NOW = du.now_utc().replace(minute=0, second=0, microsecond=0)


def _ago(days: float) -> _dt.datetime:
    return NOW - _dt.timedelta(days=days)


def _zone(name, server, ztype=du.ZONE_PRIMARY, ds=True, **kw) -> dict:
    z = {"name": name, "server": server, "type": ztype, "ds": ds, "reverse": du.is_reverse_zone(name), "auto": False,
         "aging": False, "norefresh_h": 168, "refresh_h": 168, "scavenge_after": None, "allow_update": du.UPDATE_SECURE,
         "paused": False, "shutdown": False, "secure_secondaries": du.XFER_NONE if ds else du.XFER_NS, "secondaries": [],
         "notify": du.NOTIFY_NS, "notify_servers": [], "masters": [], "local_masters": [],
         "data_file": "" if ds else f"{name}.dns", "forwarder_timeout": 0, "forwarder_slave": False, "use_wins": False}
    z.update(kw)
    return z


def _r(zone, node, rtype, ttl=3600, ts=None, **data) -> du.Rec:
    name = zone if node in ("", "@") else f"{node}.{zone}"
    rec = du.Rec(zone=zone, name=name, type=rtype, data=data, ttl=ttl, ts=ts)
    rec.text = du.text_representation(rec) if rtype in du.EDIT_TYPES else rec.text
    return rec


def _soa(zone, primary, serial=100) -> du.Rec:
    return du.Rec(zone=zone, name=zone, type="SOA", ttl=3600,
                  data={"primary": primary, "responsible": f"hostmaster.{zone}", "serial": serial, "refresh": 900,
                        "retry": 600, "expire": 86400, "minimum": 3600})


def _server(name, ds, **kw) -> dict:
    s = {"name": name, "wmi_name": name.upper(), "version": "10.0 (Build 20348)", "ds": ds,
         "server_addresses": [], "forwarders": ["9.9.9.9", "1.1.1.1"], "forwarding_timeout": 3, "is_slave": False,
         "no_recursion": False, "scavenging_hours": 168 if ds else 0, "default_aging": False,
         "default_norefresh_h": 168, "default_refresh_h": 168, "round_robin": True, "secure_responses": True,
         "bind_secondaries": False, "local_net_priority": True, "recursion_timeout": 8, "recursion_retry": 3,
         "max_cache_ttl": 86400, "event_log_level": 4, "disable_autoreverse": False, "edns_probes": True,
         "dnssec": True, "strict_file_parsing": False, "write_authority_ns": False, "listen_addresses": []}
    s.update(kw)
    return s


REV4 = "10.10.in-addr.arpa"
REV6 = "0.1.0.0.8.b.d.0.1.0.0.2.ip6.arpa"     # 2001:db8:10::/48
DOM = "corp.example"


def demo_data() -> dict:
    """Zwei Domänencontroller (AD-Zonen) und ein eigenständiger Server außerhalb der Domäne."""
    data = {}
    for srv, ip, ip6 in (("dc01.corp.example", "10.10.0.10", "2001:db8:10::10"),
                         ("dc02.corp.example", "10.10.0.11", "2001:db8:10::11")):
        info = _server(srv, True, server_addresses=[ip, ip6])
        if srv.startswith("dc02"):
            info.update(scavenging_hours=0, forwarders=["9.9.9.9"], secure_responses=False)
        zones = {
            DOM: _zone(DOM, srv, aging=True, norefresh_h=168, refresh_h=168),
            f"_msdcs.{DOM}": _zone(f"_msdcs.{DOM}", srv),
            REV4: _zone(REV4, srv, aging=True),
            REV6: _zone(REV6, srv),
            "partner.example": _zone("partner.example", srv, du.ZONE_FORWARDER, masters=["192.0.2.53"]),
            "trustanchors": _zone("trustanchors", srv, auto=True),
        }
        if srv.startswith("dc01"):
            zones["legacy.example"] = _zone("legacy.example", srv, ds=False, allow_update=du.UPDATE_ANY,
                                            secure_secondaries=du.XFER_ANY)
        z = DOM
        recs = [
            _soa(z, "dc01.corp.example", 4711),
            _r(z, "", "NS", host="dc01.corp.example"), _r(z, "", "NS", host="dc02.corp.example"),
            _r(z, "", "A", ttl=600, ip="10.10.0.10"), _r(z, "", "A", ttl=600, ip="10.10.0.11"),
            _r(z, "dc01", "A", ip="10.10.0.10"), _r(z, "dc02", "A", ip="10.10.0.11"),
            _r(z, "dc01", "AAAA", ip="2001:db8:10::10"), _r(z, "dc02", "AAAA", ip="2001:db8:10::11"),
            _r(z, "mail", "A", ip="10.10.0.25"), _r(z, "", "MX", pref=10, host="mail.corp.example"),
            _r(z, "", "TXT", text="v=spf1 mx -all"),
            _r(z, "www", "CNAME", host="web01.corp.example"), _r(z, "web01", "A", ip="10.10.1.80"),
            _r(z, "web01", "AAAA", ip="2001:db8:10:1::80"),
            _r(z, "intranet", "CNAME", host="www.corp.example"),            # Kette
            _r(z, "old-app", "CNAME", host="app-gone.corp.example"),        # Ziel fehlt
            _r(z, "printer_3og", "A", ip="10.10.2.30"),                    # Unterstrich
            _r(z, "_ldap._tcp", "SRV", ttl=600, priority=0, weight=100, port=389, host="dc01.corp.example"),
            _r(z, "_ldap._tcp", "SRV", ttl=600, priority=0, weight=100, port=389, host="dc02.corp.example"),
            _r(z, "_kerberos._tcp", "SRV", ttl=600, priority=0, weight=100, port=88, host="dc01.corp.example"),
            _r(z, "pc-0142", "A", ttl=1200, ts=_ago(2), ip="10.10.20.42"),
            _r(z, "pc-0143", "A", ttl=1200, ts=_ago(20), ip="10.10.20.43"),   # veraltet
            _r(z, "pc-0199", "A", ttl=1200, ts=_ago(40), ip="10.10.20.42"),   # gleiche IP wie pc-0142, älter
            _r(z, "nb-anna", "A", ttl=1200, ts=_ago(1), ip="10.10.20.77"),
            _r(z, "nb-anna", "AAAA", ttl=1200, ts=_ago(1), ip="2001:db8:10:20::77"),
            _r(z, "nas", "A", ip="10.10.3.5"),                              # ohne PTR
            _r(z, "test", "A", ttl=0, ip="10.10.9.9"),
        ]
        rev4 = [
            _soa(REV4, "dc01.corp.example", 320), _r(REV4, "", "NS", host="dc01.corp.example"),
            _r(REV4, "", "NS", host="dc02.corp.example"),
            _r(REV4, "10.0", "PTR", host="dc01.corp.example"), _r(REV4, "11.0", "PTR", host="dc02.corp.example"),
            _r(REV4, "25.0", "PTR", host="mail.corp.example"), _r(REV4, "80.1", "PTR", host="web01.corp.example"),
            _r(REV4, "42.20", "PTR", ttl=1200, ts=_ago(2), host="pc-0142.corp.example"),
            _r(REV4, "43.20", "PTR", ttl=1200, ts=_ago(20), host="pc-0143.corp.example"),
            _r(REV4, "77.20", "PTR", ttl=1200, ts=_ago(1), host="nb-anna.corp.example"),
            _r(REV4, "50.20", "PTR", ttl=1200, ts=_ago(60), host="pc-0050.corp.example"),   # Ziel fehlt
            _r(REV4, "30.2", "PTR", host="printer_3og.corp.example"),
            _r(REV4, "9.9", "PTR", host="dc01.corp.example"),                               # falscher Name
        ]
        rev6 = [_soa(REV6, "dc01.corp.example", 12), _r(REV6, "", "NS", host="dc01.corp.example"),
                _r(REV6, "", "NS", host="dc02.corp.example"),
                du.Rec(REV6, du.ptr_name("2001:db8:10::10"), "PTR", {"host": "dc01.corp.example"}),
                du.Rec(REV6, du.ptr_name("2001:db8:10::11"), "PTR", {"host": "dc02.corp.example"})]
        msdcs = [_soa(f"_msdcs.{DOM}", "dc01.corp.example", 90), _r(f"_msdcs.{DOM}", "", "NS", host="dc01.corp.example"),
                 _r(f"_msdcs.{DOM}", "_ldap._tcp.dc", "SRV", ttl=600, priority=0, weight=100, port=389,
                    host="dc01.corp.example")]
        legacy = [_soa("legacy.example", "dc01.corp.example", 7), _r("legacy.example", "", "NS", host="dc01.corp.example"),
                  _r("legacy.example", "ftp", "A", ip="10.10.5.21")]
        rr = {DOM: recs, REV4: rev4, REV6: rev6, f"_msdcs.{DOM}": msdcs, "legacy.example": legacy,
              "partner.example": [], "trustanchors": []}
        if srv.startswith("dc02"):
            rr = copy.deepcopy(rr)
            rr[DOM][0].data["serial"] = 4710
            rr.pop("legacy.example", None)
        data[srv] = {"info": info, "zones": zones, "recs": rr}
    # eigenständiger Server in der DMZ (keine Domäne, dateibasierte Zonen, IPv6-Reverse-Zone)
    srv = "dmz-dns01"
    info = _server(srv, False, server_addresses=["192.0.2.10", "2001:db8:ff::10"], forwarders=["9.9.9.9"])
    z = "shop.example"
    zones = {z: _zone(z, srv, ds=False, allow_update=du.UPDATE_NONE, secure_secondaries=du.XFER_LIST,
                      secondaries=["192.0.2.11"], notify=du.NOTIFY_LIST, notify_servers=["192.0.2.11"]),
             "2.0.192.in-addr.arpa": _zone("2.0.192.in-addr.arpa", srv, ds=False, allow_update=du.UPDATE_NONE),
             "f.f.0.0.8.b.d.0.1.0.0.2.ip6.arpa": _zone("f.f.0.0.8.b.d.0.1.0.0.2.ip6.arpa", srv, ds=False,
                                                     allow_update=du.UPDATE_NONE)}
    recs = {z: [_soa(z, "dmz-dns01.shop.example", 2026102301), _r(z, "", "NS", host="dmz-dns01.shop.example"),
                _r(z, "dmz-dns01", "A", ip="192.0.2.10"), _r(z, "dmz-dns01", "AAAA", ip="2001:db8:ff::10"),
                _r(z, "", "A", ip="192.0.2.80"), _r(z, "", "AAAA", ip="2001:db8:ff::80"),
                _r(z, "www", "CNAME", host="shop.example"), _r(z, "", "MX", pref=10, host="mx.mailhost.example"),
                _r(z, "", "TXT", text="v=spf1 include:mailhost.example -all")],
            "2.0.192.in-addr.arpa": [_soa("2.0.192.in-addr.arpa", "dmz-dns01.shop.example", 5),
                                     _r("2.0.192.in-addr.arpa", "", "NS", host="dmz-dns01.shop.example"),
                                     _r("2.0.192.in-addr.arpa", "10", "PTR", host="dmz-dns01.shop.example")],
            "f.f.0.0.8.b.d.0.1.0.0.2.ip6.arpa": [
                _soa("f.f.0.0.8.b.d.0.1.0.0.2.ip6.arpa", "dmz-dns01.shop.example", 3),
                _r("f.f.0.0.8.b.d.0.1.0.0.2.ip6.arpa", "", "NS", host="dmz-dns01.shop.example"),
                du.Rec("f.f.0.0.8.b.d.0.1.0.0.2.ip6.arpa", du.ptr_name("2001:db8:ff::10"), "PTR",
                       {"host": "dmz-dns01.shop.example"})]}
    data[srv] = {"info": info, "zones": zones, "recs": recs}
    return data


class FakeBackend:
    def __init__(self, data: dict | None = None):
        self.data = data or demo_data()
        self.connected: dict[str, tuple[str, str]] = {}
        self.fail = None
        self.calls: list[str] = []
        self.lock = threading.Lock()
        def ev(delta, user, eid, text, fields, rec):
            t = NOW - delta
            return {"record": rec, "id": eid, "level": 4, "utc": t.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "time": t.astimezone().strftime("%Y-%m-%d %H:%M:%S"), "user": user, "text": text,
                    "fields": fields, "data": [v for _k, v in fields]}
        self.events_list = [
            ev(_dt.timedelta(minutes=12), "CORP\\admin.meier", 515,
               "A resource record of type A, name pc-0142.corp.example and RDATA 10.10.20.42 was created in scope "
               "Default of zone corp.example.", [("Zone", "corp.example"), ("NAME", "pc-0142.corp.example"),
                                                 ("Type", "1")], 9003),
            ev(_dt.timedelta(hours=3), "CORP\\admin.schulz", 516,
               "A resource record of type CNAME, name old.corp.example was deleted from zone corp.example.",
               [("Zone", "corp.example"), ("NAME", "old.corp.example"), ("Type", "5")], 9002),
            ev(_dt.timedelta(days=1), "CORP\\admin.meier", 541,
               "The setting Forwarders on scope . has been set to 9.9.9.9 1.1.1.1.", [], 9001),
        ]

    # --- Hilfen -------------------------------------------------------------------------------------
    def _hit(self, name: str, *args):
        self.calls.append(name)
        f = self.fail
        if f and (f == name or (isinstance(f, tuple) and f[0] == name and f[1](args))):
            self.fail = None
            raise HostError(f"@WMI:write:fake:80041001:Fake: {name} scheitert")

    def _s(self, server: str) -> dict:
        s = du.norm(server)
        if s not in self.connected:
            raise HostError(f"@ERR:not_connected:{server}")
        return self.data[s]

    def _bump(self, server: str, zone: str) -> None:
        for r in self._s(server)["recs"].get(zone, []):
            if r.type == "SOA":
                r.data["serial"] += 1

    # --- Verwaltung -----------------------------------------------------------------------------------
    def hello(self) -> dict:
        return {"wmi": True, "error": "", "dnspython": True, "dhcp": True, "user": "CORP\\admin.meier",
                "computer": "ADMIN-PC"}

    def kill(self): pass

    def reset_cancel(self): pass

    def close(self):
        self.connected.clear()

    def connect(self, server, user="", password=""):
        s = du.norm(server)
        self._hit("connect", s)
        if s not in self.data:
            raise HostError(f"@ERR:unreachable:{server}|800706BA|")
        self.connected[s] = (user, password)
        return dict(self.data[s]["info"], local=False, creds_ignored=False)

    def disconnect(self, server=None):
        if server:
            self.connected.pop(du.norm(server), None)
        else:
            self.connected.clear()

    def info(self, server):
        return dict(copy.deepcopy(self._s(server)["info"]), local=False)

    def set_server(self, server, values):
        self._hit("set_server", values)
        self._s(server)["info"].update(copy.deepcopy(values))

    def start_scavenging(self, server):
        self._hit("start_scavenging")

    def clear_cache(self, server):
        self._hit("clear_cache")

    def zones(self, server):
        return [dict(z) for z in copy.deepcopy(list(self._s(server)["zones"].values()))]

    def zone(self, server, zone):
        z = self._s(server)["zones"].get(du.norm(zone))
        if z is None:
            raise HostError(f"@ERR:zone_missing:{zone}")
        return copy.deepcopy(z)

    def set_zone(self, server, zone, values):
        self._hit("set_zone", zone, values)
        self._s(server)["zones"][zone].update(values)

    def set_transfers(self, server, zone, secure, secondaries, notify, notify_servers):
        self._hit("set_transfers", zone)
        self._s(server)["zones"][zone].update(secure_secondaries=secure, secondaries=list(secondaries), notify=notify,
                                              notify_servers=list(notify_servers))

    def zone_action(self, server, zone, action):
        self._hit("zone_action", zone, action)
        z = self._s(server)["zones"][zone]
        if action in ("pause", "resume"):
            z["paused"] = action == "pause"

    def create_zone(self, server, name, ztype, ds, data_file="", masters=None, admin=""):
        self._hit("create_zone", name)
        s = self._s(server)
        name = du.norm(name)
        if name in s["zones"]:
            raise HostError(f"@WMI:create_zone:{server}:80041019:Zone exists")
        s["zones"][name] = _zone(name, du.norm(server), ztype, ds, masters=list(masters or []),
                                 data_file=data_file if not ds else "")
        recs = []
        if ztype == du.ZONE_PRIMARY:
            recs = [_soa(name, du.norm(server), 1), _r(name, "", "NS", host=du.norm(server))]
        s["recs"][name] = recs

    def delete_zone(self, server, zone):
        self._hit("delete_zone", zone)
        s = self._s(server)
        s["zones"].pop(zone, None)
        s["recs"].pop(zone, None)

    # --- Einträge -------------------------------------------------------------------------------------
    def records(self, server, zone):
        self._hit("records", zone)
        s = self._s(server)
        if zone not in s["zones"]:
            raise HostError(f"@ERR:zone_missing:{zone}")
        return copy.deepcopy(s["recs"].get(zone, []))

    def soa(self, server, zone):
        s = self._s(server)
        return copy.deepcopy(next((r for r in s["recs"].get(zone, []) if r.type == "SOA"), None))

    def exists(self, server, rec):
        return any(r.key == rec.key for r in self._s(server)["recs"].get(rec.zone, []))

    def create_record(self, server, rec):
        self._hit("create_record", rec)
        s = self._s(server)
        if rec.zone not in s["zones"]:
            raise HostError(f"@ERR:zone_missing:{rec.zone}")
        lst = s["recs"].setdefault(rec.zone, [])
        if any(r.key == rec.key for r in lst):
            raise HostError(f"@WMI:create:{server}:80041019:Record exists")
        new = copy.deepcopy(rec)
        new.text = du.text_representation(new)
        if new.ts is not None:
            new.ts = NOW
        lst.append(new)
        self._bump(server, rec.zone)

    def delete_record(self, server, rec):
        self._hit("delete_record", rec)
        lst = self._s(server)["recs"].get(rec.zone, [])
        for i, r in enumerate(lst):
            if r.key == rec.key:
                del lst[i]
                self._bump(server, rec.zone)
                return
        raise HostError(f"@ERR:record_missing:{rec.name} {rec.type} {rec.value}")

    def age_node(self, server, zone, node):
        self._hit("age_node", zone, node)
        for r in self._s(server)["recs"].get(zone, []):
            if r.node == node and r.type not in ("SOA", "NS"):
                r.ts = NOW
        self._bump(server, zone)

    # --- Ereignisse, DHCP, Abfragen -------------------------------------------------------------------
    def events(self, server, since_utc, max_n=300):
        return copy.deepcopy(self.events_list)

    def dhcp_leases(self, server, user="", password=""):
        return [
            {"ip": "10.10.20.42", "name": "pc-0142.corp.example", "mac": "00-11-22-33-44-42", "scope": "10.10.20.0",
             "mask": "255.255.255.0", "kind": "lease", "expires": None, "state": 1},
            {"ip": "10.10.20.77", "name": "nb-anna.corp.example", "mac": "00-11-22-33-44-77", "scope": "10.10.20.0",
             "mask": "255.255.255.0", "kind": "lease", "expires": None, "state": 1},
            {"ip": "10.10.20.88", "name": "pc-0188.corp.example", "mac": "00-11-22-33-44-88", "scope": "10.10.20.0",
             "mask": "255.255.255.0", "kind": "lease", "expires": None, "state": 1},
            {"ip": "10.10.20.90", "name": "nb-tom.corp.example", "mac": "00-11-22-33-44-90", "scope": "10.10.20.0",
             "mask": "255.255.255.0", "kind": "reservation", "expires": None, "state": 1},
        ]

    def resolve(self, name):
        n = du.norm(name)
        for d in self.data.values():
            for zone, recs in d["recs"].items():
                ips = [r.ip() for r in recs if r.name == n and r.type in ("A", "AAAA")]
                if ips:
                    return ips
        return []

    def probe(self, server_ip, qname, rtype="SOA", timeout=2.0):
        for name, d in self.data.items():
            if server_ip in d["info"]["server_addresses"]:
                z = d["recs"].get(du.norm(qname))
                if z is None:
                    return {"ok": True, "rcode": "REFUSED", "answers": [], "serial": None, "ms": 3, "aa": False}
                soa = next((r for r in z if r.type == "SOA"), None)
                return {"ok": True, "rcode": "NOERROR", "answers": [], "serial": soa.data["serial"] if soa else None,
                        "ms": 4, "aa": True}
        if server_ip == "1.1.1.1":
            return {"ok": False, "error": "Timeout", "ms": 2000}
        return {"ok": True, "rcode": "NOERROR", "answers": ["93.184.215.14"], "serial": None, "ms": 21, "aa": False}

    def srv_lookup(self, name, timeout=3.0):
        return ["dc01.corp.example", "dc02.corp.example"]
