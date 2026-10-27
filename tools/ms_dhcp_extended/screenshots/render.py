"""Screenshots für Store und Home (scripts/render_screenshots.py).

Statt dhcpsapi.dll liefert FakeBackend Beispieldaten (zwei Failover-Server, IPv4 und IPv6) in derselben
Form wie backend.ApiBackend. Schreibende Befehle werden angenommen und ignoriert.
"""

import ipaddress
import random

PRIMARY, PARTNER = "dhcp01.contoso.local", "dhcp02.contoso.local"
FO_NAME = "dhcp01-dhcp02"
DAY = 86400

# Scope-ID, Maske, Name, Beschreibung, Status, Lease (Tage), Belegung in %, Failover, Router fehlt
SCOPES = [
    ("10.20.1.0", "255.255.255.0", "HQ Clients 1st floor", "Building A", "Active", 8, 61, True, False),
    ("10.20.2.0", "255.255.255.0", "HQ Clients 2nd floor", "Building A", "Active", 8, 94, True, False),
    ("10.20.3.0", "255.255.255.0", "HQ VoIP", "Phones, option 43", "Active", 8, 47, True, False),
    ("10.20.4.0", "255.255.254.0", "HQ Wi-Fi guests", "Captive portal", "Active", 0.33, 72, True, False),
    ("10.20.6.0", "255.255.255.0", "HQ Printers", "", "Active", 30, 33, True, False),
    ("10.30.0.0", "255.255.254.0", "Branch Munich", "MPLS", "Active", 8, 58, True, False),
    ("10.31.0.0", "255.255.255.0", "Branch Hamburg", "MPLS", "Active", 8, 39, True, True),
    ("10.40.0.0", "255.255.252.0", "Lab", "Test network", "Active", 1, 12, False, False),
    ("172.16.10.0", "255.255.255.0", "Kiosk systems", "Decommissioned 2026", "InActive", 8, 0, False, False),
]
SCOPES6 = [
    ("2001:db8:20:1::", 64, "HQ Clients IPv6", "Building A", "Active", 412),
    ("2001:db8:20:3::", 64, "HQ VoIP IPv6", "", "Active", 186),
    ("2001:db8:30::", 64, "Branch Munich IPv6", "", "Active", 97),
]
HOSTS = ["NB-{:04d}", "PC-{:04d}", "SURFACE-{:03d}", "TC-{:04d}"]


def _scope_size(sid, mask):
    net = ipaddress.ip_network(f"{sid}/{mask}")
    return net, list(net.hosts())


def _range(sid, mask):
    net, hosts = _scope_size(sid, mask)
    return str(hosts[19]), str(hosts[-6])


def _build():
    rnd = random.Random(42)
    data = {"scopes": [], "stats": [], "excl": [], "res": [], "leases": [], "opts": {}, "dns": {}}
    for sid, mask, name, desc, state, days, pct, _fo, no_router in SCOPES:
        start, end = _range(sid, mask)
        data["scopes"].append({"ScopeId": sid, "SubnetMask": mask, "Name": name, "Description": desc, "State": state,
                               "StartRange": start, "EndRange": end, "LeaseDuration": int(days * DAY),
                               "SuperscopeName": "", "Type": "Dhcp"})
        size = int(ipaddress.ip_address(end)) - int(ipaddress.ip_address(start)) + 1 - 10
        in_use = round(size * pct / 100)
        data["stats"].append({"ScopeId": sid, "InUse": in_use, "Free": size - in_use, "Pending": 0, "Reserved": 3,
                              "PercentageInUse": round(100 * in_use / size, 2)})
        base = int(ipaddress.ip_address(start))
        data["excl"].append({"ScopeId": sid, "StartRange": str(ipaddress.ip_address(base + 200 if size > 220 else base + 100)),
                             "EndRange": str(ipaddress.ip_address(base + 209 if size > 220 else base + 109))})
        for i, (rname, rdesc) in enumerate((("prn-" + name.split()[-1].lower()[:6], "Printer"),
                                            ("ap-" + name.split()[0].lower() + "-01", "Access point"),
                                            ("cam-entrance", "Camera"))):
            data["res"].append({"ScopeId": sid, "IPAddress": str(ipaddress.ip_address(base + 150 + i)),
                                "ClientId": "00-1b-a9-%02x-%02x-%02x" % (rnd.randrange(256), rnd.randrange(256), i),
                                "Name": rname, "Description": rdesc, "Type": "Both"})
        for i in range(min(in_use, 60)):
            host = rnd.choice(HOSTS).format(rnd.randrange(1, 4000))
            data["leases"].append({
                "ScopeId": sid, "IPAddress": str(ipaddress.ip_address(base + i)),
                "ClientId": "-".join(f"{rnd.randrange(256):02x}" for _ in range(6)),
                "HostName": f"{host.lower()}.contoso.local", "Description": "",
                "AddressState": "Active", "LeaseExpiryTime": f"2026-11-0{1 + i % 8}T{8 + i % 10:02d}:{i % 60:02d}:00",
                "ClientType": "Dhcp"})
        router = str(ipaddress.ip_address(int(ipaddress.ip_address(sid)) + 1))
        data["opts"][sid] = ([] if no_router else [{"OptionId": 3, "Name": "Router", "Value": [router],
                                                    "Type": "IPv4Address", "VendorClass": "", "UserClass": ""}])
        if "VoIP" in name:
            data["opts"][sid].append({"OptionId": 42, "Name": "NTP Servers", "Value": ["10.20.0.10"],
                                      "Type": "IPv4Address", "VendorClass": "", "UserClass": ""})
        if "guests" in name:
            data["opts"][sid].append({"OptionId": 6, "Name": "DNS Servers", "Value": ["9.9.9.9", "149.112.112.112"],
                                      "Type": "IPv4Address", "VendorClass": "", "UserClass": ""})
    data["server_opts"] = [
        {"OptionId": 6, "Name": "DNS Servers", "Value": ["10.20.0.10", "10.20.0.11"], "Type": "IPv4Address",
         "VendorClass": "", "UserClass": ""},
        {"OptionId": 15, "Name": "DNS Domain Name", "Value": ["contoso.local"], "Type": "String",
         "VendorClass": "", "UserClass": ""},
        {"OptionId": 42, "Name": "NTP Servers", "Value": ["10.20.0.10"], "Type": "IPv4Address",
         "VendorClass": "", "UserClass": ""},
        {"OptionId": 119, "Name": "DNS Search List", "Value": ["contoso.local", "corp.contoso.local"],
         "Type": "String", "VendorClass": "", "UserClass": ""},
    ]
    data["defs"] = [
        {"OptionId": i, "Name": n, "Description": d, "Type": t, "MultiValued": m, "VendorClass": "",
         "UserClass": "", "DefaultValue": [dv]}
        for i, n, d, t, m, dv in (
            (3, "Router", "Array of router addresses ordered by preference", "IPv4Address", True, "0.0.0.0"),
            (6, "DNS Servers", "Array of DNS servers, by preference", "IPv4Address", True, "0.0.0.0"),
            (15, "DNS Domain Name", "Domain name for client resolutions", "String", False, ""),
            (42, "NTP Servers", "Addresses of Network Time Protocol servers", "IPv4Address", True, "0.0.0.0"),
            (43, "Vendor Specific Info", "Embedded vendor-specific options", "BinaryData", False, ""),
            (66, "Boot Server Host Name", "TFTP boot server host name", "String", False, ""),
            (67, "Bootfile Name", "Bootfile Name", "String", False, ""),
            (119, "DNS Search List", "Domain search list for name resolution", "String", True, ""),
            (252, "WPAD", "Web proxy auto-discovery", "String", False, ""))]
    data["scopes6"], data["stats6"], data["res6"], data["leases6"] = [], [], [], []
    for prefix, length, name, desc, state, used in SCOPES6:
        data["scopes6"].append({"Prefix": prefix, "PrefixLength": length, "Name": name, "Description": desc,
                                "Preference": 0, "State": state, "PreferredLifetime": 8 * DAY,
                                "ValidLifetime": 12 * DAY, "T1": 4 * DAY, "T2": 6 * DAY, "RapidCommit": False,
                                "Unicast": False})
        data["stats6"].append({"Prefix": prefix, "AddressesInUse": used, "AddressesFree": 2 ** 64 - used,
                               "PendingAdvertises": 0, "PercentageInUse": 0.0})
        for i in range(min(used, 25)):
            data["leases6"].append({
                "Prefix": prefix, "IPAddress": f"{prefix}{rnd.randrange(0x1000, 0xffff):x}:{rnd.randrange(0x10, 0xff):x}",
                "ClientDuid": "00-01-00-01-" + "-".join(f"{rnd.randrange(256):02x}" for _ in range(10)),
                "Iaid": rnd.randrange(10 ** 8, 10 ** 9), "HostName": f"nb-{rnd.randrange(1, 4000):04d}.contoso.local",
                "Description": "", "AddressState": "Active", "AddressType": "IANA",
                "LeaseExpiryTime": "2026-11-04T09:00:00"})
    return data


DATA = _build()
FAILOVER = {"Name": FO_NAME, "Mode": "LoadBalance", "ServerRole": "", "LoadBalancePercent": 50,
            "ReservePercent": None, "MaxClientLeadTime": 3600, "AutoStateTransition": False, "StateSwitchInterval": 0,
            "State": "Normal", "ScopeId": [s[0] for s in SCOPES if s[7]], "EnableAuth": True}


def _by(items, key, value):
    return [x for x in items if value is None or str(x.get(key)) == str(value)]


class FakeBackend:
    """Gleiche Schnittstelle wie backend.ApiBackend.call()."""

    def close(self):
        pass

    def kill(self):
        pass

    def call(self, cmd, args=None, on_progress=None):
        a = args or {}
        if cmd == "hello":
            return {"dhcp": True, "user": "CONTOSO\\j.bauer", "computer": "ADM-WS07"}
        if cmd == "connect":
            if on_progress:
                on_progress({"step": "try", "proto": "RPC"})
            return {"protocol": "RPC"}
        if cmd in ("set_cred", "disconnect"):
            return True
        if cmd == "access":
            return "admin"
        if cmd == "resolve":
            return "10.20.0.21"
        if cmd == "dhcp_in_dc":
            return {"items": [{"name": PRIMARY, "ip": "10.20.0.21"}, {"name": PARTNER, "ip": "10.20.0.22"}]}
        if cmd == "events":
            return {"items": []}
        if cmd == "netsh":
            return {"items": [{"out": ["Server version 10.0"], "code": 0} for _ in a.get("lines") or [""]]}
        if cmd == "fo_api":
            if a.get("op") == "enum":
                return {"items": [{"name": FO_NAME, "primary_ip": "10.20.0.21", "secondary_ip": "10.20.0.22",
                                   "primary_name": PRIMARY, "secondary_name": PARTNER, "mode": 0, "server_type": 0,
                                   "state": 3, "prev_state": 0, "mclt": 3600, "safe_period": 4294967295,
                                   "percentage": 50, "secret": True, "scopes": FAILOVER["ScopeId"]}]}
            return {}
        if cmd == "cim":
            return {"items": self.cmdlet(str(a["name"]), a.get("server") or PRIMARY, a.get("params") or {})}
        if cmd == "cim_many":
            for c in a.get("calls") or []:
                if on_progress:
                    on_progress({"key": c["key"], "items": self.cmdlet(c["name"], c.get("server") or PRIMARY,
                                                                       c.get("params") or {})})
            return {"count": len(a.get("calls") or [])}
        return {}

    def cmdlet(self, name, server, p):
        if not name.startswith("Get-"):
            return []
        sid, prefix = p.get("ScopeId"), p.get("Prefix")
        partner = server.lower().startswith("dhcp02")
        d = DATA
        if name == "Get-DhcpServerVersion":
            return [{"MajorVersion": 10, "MinorVersion": 0}]
        if name == "Get-DhcpServerv4Scope":
            return _by(d["scopes"], "ScopeId", sid)
        if name == "Get-DhcpServerv4ScopeStatistics":
            return _by(d["stats"], "ScopeId", sid)
        if name == "Get-DhcpServerv4ExclusionRange":
            return _by(d["excl"], "ScopeId", sid)
        if name == "Get-DhcpServerv4Reservation":
            res = _by(d["res"], "ScopeId", sid)
            # Unterschied auf dem Partner: eine Reservierung fehlt dort (zeigt der Abgleich)
            return [r for r in res if not (partner and r["Name"] == "cam-entrance" and r["ScopeId"] == "10.20.3.0")]
        if name == "Get-DhcpServerv4Lease":
            return _by(d["leases"], "ScopeId", sid)
        if name == "Get-DhcpServerv4OptionValue":
            return list(d["opts"].get(sid, [])) if sid else list(d["server_opts"])
        if name == "Get-DhcpServerv4OptionDefinition":
            return list(d["defs"])
        if name == "Get-DhcpServerv4DnsSetting":
            return [{"DynamicUpdates": "Always", "DeleteDnsRROnLeaseExpiry": True, "UpdateDnsRRForOlderClients": True,
                     "DisableDnsPtrRRUpdate": False, "NameProtection": sid != "10.20.4.0"}]
        if name == "Get-DhcpServerv4Failover":
            other = PRIMARY if partner else PARTNER
            return [dict(FAILOVER, PartnerServer=other)]
        if name == "Get-DhcpServerSetting":
            return [{"IsDomainJoined": True, "IsAuthorized": True, "NapEnabled": False,
                     "ConflictDetectionAttempts": 1, "DynamicBootp": False}]
        if name == "Get-DhcpServerAuditLog":
            return [{"Enable": True}]
        if name == "Get-DhcpServerDatabase":
            return [{"LoggingEnabled": True, "BackupInterval": 60, "FileName": "C:\\Windows\\system32\\dhcp\\dhcp.mdb",
                     "BackupPath": "C:\\Windows\\system32\\dhcp\\backup"}]
        if name == "Get-DhcpServerDnsCredential":
            return [{"UserName": "svc-dhcp-dns", "DomainName": "CONTOSO"}]
        if name == "Get-DhcpServerv6Scope":
            return _by(d["scopes6"], "Prefix", prefix)
        if name == "Get-DhcpServerv6ScopeStatistics":
            return _by(d["stats6"], "Prefix", prefix)
        if name == "Get-DhcpServerv6Lease":
            return _by(d["leases6"], "Prefix", prefix)
        if name == "Get-DhcpServerv6OptionValue":
            return [] if prefix else [
                {"OptionId": 23, "Name": "DNS Recursive Name Server IPV6 Address List",
                 "Value": ["2001:db8:20::53", "2001:db8:20::54"], "Type": "IPv6Address", "VendorClass": "",
                 "UserClass": ""},
                {"OptionId": 24, "Name": "Domain Search List", "Value": ["contoso.local"], "Type": "String",
                 "VendorClass": "", "UserClass": ""}]
        if name == "Get-DhcpServerv6OptionDefinition":
            return [{"OptionId": 23, "Name": "DNS Recursive Name Server IPV6 Address List", "Description": "",
                     "Type": "IPv6Address", "MultiValued": True, "VendorClass": "", "UserClass": "",
                     "DefaultValue": [""]},
                    {"OptionId": 24, "Name": "Domain Search List", "Description": "", "Type": "String",
                     "MultiValued": True, "VendorClass": "", "UserClass": "", "DefaultValue": [""]}]
        if name == "Get-DhcpServerv6Setting":
            return [{"PreferredLifetime": 8 * DAY, "ValidLifetime": 12 * DAY, "RapidCommit": False, "Unicast": False,
                     "AuditLog": True, "StatelessEnabled": True, "StatelessPurgeInterval": 0}]
        if name == "Get-DhcpServerv6Binding":
            return [{"BindingState": True, "InterfaceAlias": "Ethernet0", "IPAddress": "2001:db8:20::21"}]
        if name == "Get-DhcpServerv4Binding":
            return [{"BindingState": True, "InterfaceAlias": "Ethernet0", "IPAddress": "10.20.0.21",
                     "SubnetMask": "255.255.255.0"}]
        return []


def render(shot):
    tool_mod = shot.module("tool")
    tool_mod.MsDhcpExtended.backend_factory = FakeBackend
    shot.settings.set("auto_scan", True)
    shot.settings.set("auto_partner", True)
    shot.settings.set("auto_refresh", 0)
    tool, _ = shot.create()
    tool.server.setCurrentText(PRIMARY)
    tool._login_clicked()
    shot.wait_until(lambda: tool.stack.currentIndex() == 1 and not tool.runner.active, 60, "Anmeldung")
    shot.wait_until(lambda: tool.scan is not None, 120, "Prüfung")
    shot.wait(0.5)
    split = tool.log_view.parentWidget().parentWidget()  # Protokoll klein halten
    split.setSizes([700, 90])
    tool.fixed_docks[0].setAsCurrentTab()
    shot.save("overview")

    tool.open_scope("10.20.2.0")
    shot.wait_until(lambda: not tool.runner.active, 30, "Scope")
    shot.wait(0.5)
    shot.save("scope")

    tool.fixed_docks[2].setAsCurrentTab()
    shot.wait(0.4)
    shot.save("failover")

    tool.fixed_docks[1].setAsCurrentTab()
    shot.wait(0.4)
    shot.save("server_options")

    tool.fixed_docks[4].setAsCurrentTab()
    shot.wait(0.4)
    shot.save("check")

    tool.set_family(6)
    shot.wait_until(lambda: not tool.runner.active, 30, "IPv6")
    tool.fixed_docks[0].setAsCurrentTab()
    shot.wait(0.5)
    shot.save("ipv6")
