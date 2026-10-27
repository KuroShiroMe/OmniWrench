"""Screenshots für Store und Home (scripts/render_screenshots.py).

Die echte Engine läuft, nur die Netzwerkzugriffe (ICMP, TCP, HTTP, TLS, SMB, RDP, NTP, NetBIOS, DNS)
liefern Beispieldaten: ein Windows-Anwendungsserver und ein kleines Netz mit Drucker und Switch.
"""

import asyncio
import datetime as dt
import random

from PySide6.QtWidgets import QTabWidget

HOSTS = {
    "10.20.1.15": {"name": "srv-app01", "ports": [80, 135, 139, 443, 445, 1433, 3389, 5985, 8080], "windows": True},
    "10.20.5.1": {"name": "sw-core-05", "ports": [22, 80, 443], "windows": False},
    "10.20.5.4": {"name": "prn-hq-2og", "ports": [80, 443, 515, 631, 9100], "windows": False},
    "10.20.5.9": {"name": "ap-hq-2og", "ports": [22, 443], "windows": False},
    "10.20.5.12": {"name": "nas-backup", "ports": [22, 139, 443, 445, 5000, 5001], "windows": False},
}
PATH = ["10.20.0.1", "10.0.0.2"]  # Router vor den Zielnetzen
rnd = random.Random(7)


def _echo_factory(icmp):
    def available():
        return True

    def echo(ip, ttl=128, timeout_ms=1000, size=32, df=False):
        if ip in PATH:
            return icmp.Echo(icmp.OK, round(rnd.uniform(0.4, 1.4), 2), 255, ip)
        if ip not in HOSTS:
            return icmp.Echo(icmp.TIMEOUT)
        if ttl <= len(PATH):
            return icmp.Echo(icmp.TTL_EXPIRED, round(rnd.uniform(0.5, 1.6) * ttl, 2), 255, PATH[ttl - 1])
        base = 128 if HOSTS[ip]["windows"] else 64
        return icmp.Echo(icmp.OK, round(rnd.uniform(1.1, 2.9), 2), base - len(PATH), ip)
    return available, echo


async def tcp_connect(ip, port, timeout):
    await asyncio.sleep(0)
    if ip not in HOSTS:
        return "filtered", None
    if port in HOSTS[ip]["ports"]:
        return "open", round(rnd.uniform(0.6, 2.2), 2)
    return "closed", 0.5


async def banner(ip, port, timeout=2.0):
    return {22: "SSH-2.0-OpenSSH_9.6", 9100: ""}.get(port, "")


async def http_probe(ip, port, host, tls, timeout=5.0, path="/"):
    name = HOSTS[ip]["name"]
    pages = {
        80: (301, "Moved Permanently", "", f"https://{name}.contoso.local/"),
        443: (200, "OK", "Contoso Intranet – Sign in", ""),
        8080: (200, "OK", "Reporting Services", ""),
        5000: (200, "OK", "DiskStation", ""), 5001: (200, "OK", "DiskStation", ""),
        631: (200, "OK", "CUPS – Printer Status", ""),
    }
    status, reason, title, location = pages.get(port, (200, "OK", f"{name} – Web interface", ""))
    headers = {"server": "Microsoft-IIS/10.0" if HOSTS[ip]["windows"] else "nginx", "content-type": "text/html"}
    if tls and port == 443 and HOSTS[ip]["windows"]:
        headers["strict-transport-security"] = "max-age=31536000"
    missing = [h for h in ("strict-transport-security", "content-security-policy", "x-content-type-options",
                           "x-frame-options", "referrer-policy", "permissions-policy")
               if h not in headers and not (h == "strict-transport-security" and not tls)]
    return {"port": port, "tls": tls, "host": host, "time_ms": round(rnd.uniform(8, 40), 1), "http_version": "1.1",
            "status": status, "reason": reason, "headers": headers, "set_cookie": [], "title": title,
            "location": location, "missing_security_headers": missing}


async def tls_probe(ip, port, sni, timeout=4.0, versions=True):
    name = HOSTS[ip]["name"]
    now = dt.datetime.now(dt.timezone.utc)
    days = 21 if port == 443 else 290
    cert = {"subject": f"CN={name}.contoso.local", "issuer": "CN=Contoso Issuing CA 01,DC=contoso,DC=local",
            "self_signed": False, "san": [f"{name}.contoso.local", name],
            "not_before": (now - dt.timedelta(days=344)).isoformat(),
            "not_after": (now + dt.timedelta(days=days)).isoformat(), "days_left": days, "not_yet_valid": False,
            "key": "RSA", "key_bits": 2048, "signature": "sha256", "serial": "6C00000A4F7E2B91D3C51E2A000000000A4F",
            "sha256": ":".join(f"{rnd.randrange(256):02X}" for _ in range(32))}
    if port == 3389:
        cert.update(subject=f"CN={name}.contoso.local", issuer=f"CN={name}.contoso.local", self_signed=True)
    return {"port": port, "sni": sni or "", "version": "TLSv1.2", "cipher": "ECDHE-RSA-AES256-GCM-SHA384",
            "cipher_bits": 256, "cert": cert, "trusted": port != 3389,
            "verify_error": "self-signed certificate" if port == 3389 else "",
            "versions": {"TLSv1": port == 443, "TLSv1.1": False, "TLSv1.2": True, "TLSv1.3": False}}


async def smb_probe(ip, timeout=4.0):
    now = dt.datetime.now(dt.timezone.utc)
    return {"dialect": "3.1.1", "signing_required": False, "signing_enabled": True, "encryption_cap": True,
            "server_time": now.isoformat(timespec="seconds"), "clock_skew_s": 1, "smb1": False}


async def rdp_probe(ip, timeout=4.0):
    return {"selected": "CredSSP (NLA)", "classic_rdp_allowed": False, "nla_required": True}


async def ntp_probe(ip, timeout=2.0):
    return {"answer": False}


async def dns_server_probe(ip, timeout=2.0):
    return {"answer": False}


async def netbios_probe(ip, timeout=2.0):
    if not HOSTS.get(ip, {}).get("windows"):
        return {"answer": False}
    name = HOSTS[ip]["name"].upper()
    return {"answer": True, "computer": name, "domain": "CONTOSO", "mac": "00-15-5D-14-02-0F",
            "names": [{"name": name, "suffix": 0, "group": False}, {"name": "CONTOSO", "suffix": 0, "group": True},
                      {"name": name, "suffix": 32, "group": False}]}


async def reverse(ip, timeout=3.0):
    name = HOSTS[ip]["name"] if ip in HOSTS else {"10.20.0.1": "gw-hq", "10.0.0.2": "core-rtr-01"}.get(ip)
    if not name:
        return {"ptr": [], "ttl": None, "error": "nxdomain", "forward_confirmed": None}
    fqdn = f"{name}.contoso.local"
    return {"ptr": [fqdn], "ttl": 1200, "error": "", "forward_confirmed": True, "forward": [ip]}


async def asn_lookup(ip, timeout=3.0):
    return {}


def _patch(shot):
    engine = shot.module("engine")
    icmp, probes, dnscheck, localnet = (shot.module(n) for n in ("icmp", "probes", "dnscheck", "localnet"))
    icmp.available, icmp.echo = _echo_factory(icmp)
    for fn in (tcp_connect, banner, http_probe, tls_probe, smb_probe, rdp_probe, ntp_probe, dns_server_probe,
               netbios_probe):
        setattr(probes, fn.__name__, fn)
    dnscheck.reverse, dnscheck.asn_lookup = reverse, asn_lookup
    engine.mac_of = lambda ip: {"10.20.1.15": "00-15-5D-14-02-0F", "10.20.5.4": "00-1B-A9-3C-77-10"}.get(ip, "")
    vendors = {"00-15-5D": "Microsoft Corporation (Hyper-V)", "00-1B-A9": "Brother Industries"}
    localnet.VendorDB.lookup = lambda self, mac: vendors.get((mac or "")[:8], "")


def _select_tab(tool, title_start):
    for tabs in tool.dm.findChildren(QTabWidget):
        if not tabs.isVisible():
            continue
        for i in range(tabs.count()):
            if tabs.tabText(i).replace("&&", "&").startswith(title_start):
                tabs.setCurrentIndex(i)
                return


def render(shot):
    _patch(shot)
    shot.settings.set("options", {"oui_download": False})
    tool, _ = shot.create()
    tool.template.setCurrentIndex(tool.template.findData("standard"))
    tool.input.setText("10.20.1.15, 10.20.5.0/28")
    tool._start()
    shot.wait_until(lambda: not any(e.running for e in tool.engines), 60, "NetProbe-Engine")
    shot.wait(0.5)
    tool.list.expandAll()
    item = tool.item_for_addr["10.20.1.15"]
    tool.list.setCurrentItem(item)
    tool._open_result(item)
    shot.wait(0.4)
    tr = tool.context.tr
    _select_tab(tool, tr("cat.general"))
    shot.save("overview")
    _select_tab(tool, tr("cat.ports"))
    shot.save("ports")
    _select_tab(tool, tr("cat.web"))
    shot.save("web")
    _select_tab(tool, tr("cat.findings"))
    shot.save("findings")
