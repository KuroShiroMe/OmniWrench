"""Befunde: aus den Rohdaten eines Ziels Fehler, Warnungen, Hinweise und bestätigte Punkte ableiten.

Jeder Befund hat eine Stufe (error/warn/info/ok), einen Übersetzungsschlüssel (fx.<id>.title/.detail)
und optionale Platzhalter. Die Oberfläche übersetzt und zeigt sie als Liste.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ERROR, WARN, INFO, OK = "error", "warn", "info", "ok"
ORDER = {ERROR: 0, WARN: 1, INFO: 2, OK: 3}


@dataclass
class Finding:
    id: str
    level: str
    category: str = "general"          # Tab, zu dem der Befund gehört
    params: dict = field(default_factory=dict)
    port: int | None = None


def _add(out, id, level, category="general", port=None, **params):
    out.append(Finding(id, level, category, params, port))


def evaluate(res) -> list[Finding]:
    out: list[Finding] = []
    raw = res.raw
    _reachability(out, res)
    _latency(out, raw.get("ping", {}))
    _route(out, raw.get("traceroute", {}))
    _ports(out, res)
    _tls(out, res)
    _http(out, raw.get("http", {}))
    _smb(out, raw.get("smb", {}))
    _rdp(out, raw.get("rdp", {}))
    _ntp(out, raw.get("ntp", {}))
    _dnsserver(out, raw.get("dnsserver", {}))
    _reverse(out, raw.get("reverse", {}), res)
    _dns(out, raw.get("dns", {}))
    out.sort(key=lambda f: (ORDER[f.level], f.category, f.port or 0, f.id))
    return out


def _reachability(out, res):
    ping = res.raw.get("ping", {})
    if res.status == "no_answer":
        _add(out, "host_silent", WARN)
        return
    if ping.get("received") == 0 and not ping.get("unavailable"):
        if res.raw.get("tcp", {}).get("open"):
            _add(out, "icmp_filtered", INFO)
        elif "unreachable_from" in ping:
            _add(out, "host_unreachable", ERROR, router=ping["unreachable_from"])
        else:
            _add(out, "no_icmp", WARN)
    elif ping.get("received") and ping.get("loss_pct", 0) == 0:
        _add(out, "host_up", OK)
    addr = res.raw.get("address", {})
    if addr.get("class") in ("private", "link_local", "loopback", "cgnat", "reserved"):
        _add(out, f"addr_{addr['class']}", INFO)


def _latency(out, ping):
    if not ping.get("received"):
        return
    loss = ping.get("loss_pct", 0)
    if 0 < loss < 100:
        _add(out, "packet_loss", ERROR if loss >= 20 else WARN, loss=loss,
             sent=ping["sent"], recv=ping["received"])
    avg, jitter = ping.get("avg"), ping.get("jitter", 0)
    if avg is not None:
        if avg >= 200:
            _add(out, "latency_high", WARN, avg=avg)
        if jitter >= 30:
            _add(out, "jitter_high", WARN, jitter=jitter)


def _route(out, tr):
    if not tr or tr.get("unavailable"):
        return
    hops = tr.get("hops", [])
    if not tr.get("reached") and hops:
        last = next((h["ip"] for h in reversed(hops) if h.get("ip")), "")
        _add(out, "route_incomplete", WARN, category="route", hops=len(hops), last=last)
    stars = sum(1 for h in hops if not h.get("ip"))
    if stars >= 3:
        _add(out, "route_silent_hops", INFO, category="route", count=stars)
    for h in hops:
        rtts = h.get("rtts") or []
        if len(rtts) >= 2 and max(rtts) - min(rtts) > 100:
            _add(out, "route_unstable_hop", INFO, category="route", ttl=h["ttl"], ip=h.get("ip", "?"))
            break


def _ports(out, res):
    tcp = res.raw.get("tcp", {})
    open_ports = tcp.get("open", {})
    if not open_ports:
        return
    from .portinfo import PORT_META
    cleartext, admin, legacy, db, ics = [], [], [], [], []
    for port in open_ports:
        meta = PORT_META.get(f"{port}/tcp", {})
        flags = meta.get("flags", [])
        name = meta.get("name", "")
        if "cleartext" in flags:
            cleartext.append((port, name))
        if "admin" in flags:
            admin.append((port, name))
        if "legacy" in flags:
            legacy.append((port, name))
        if "database" in flags:
            db.append((port, name))
        if "ics" in flags:
            ics.append((port, name))
    for port, name in cleartext:
        _add(out, "port_cleartext", WARN, category="ports", port=port, name=name)
    for port, name in legacy:
        _add(out, "port_legacy", WARN, category="ports", port=port, name=name)
    for port, name in ics:
        _add(out, "port_ics", WARN, category="ports", port=port, name=name)
    for port, name in db:
        _add(out, "port_database", INFO, category="ports", port=port, name=name)
    for port, name in admin:
        _add(out, "port_admin", INFO, category="ports", port=port, name=name)
    if 23 in open_ports:
        _add(out, "telnet_open", ERROR, category="ports", port=23)
    if 445 in open_ports or 139 in open_ports:
        _add(out, "smb_exposed", INFO, category="ports", port=445)
    many = len(open_ports)
    if many >= 15:
        _add(out, "many_ports", INFO, category="ports", count=many)


def _tls(out, res):
    for port, data in res.raw.get("tls", {}).items():
        if data.get("error"):
            continue
        cert = data.get("cert", {})
        days = cert.get("days_left")
        if days is not None:
            if days < 0:
                _add(out, "cert_expired", ERROR, category="web", port=port, days=-days)
            elif days <= 14:
                _add(out, "cert_expiring", ERROR, category="web", port=port, days=days)
            elif days <= 30:
                _add(out, "cert_expiring_soon", WARN, category="web", port=port, days=days)
        if cert.get("not_yet_valid"):
            _add(out, "cert_not_yet_valid", ERROR, category="web", port=port)
        if cert.get("self_signed"):
            _add(out, "cert_self_signed", WARN, category="web", port=port)
        if data.get("trusted") is False and not cert.get("self_signed"):
            _add(out, "cert_untrusted", WARN, category="web", port=port,
                 reason=data.get("verify_error", ""))
        sni = res.target.name
        if sni and cert.get("san") and not _host_ok(sni, cert["san"]):
            _add(out, "cert_name_mismatch", WARN, category="web", port=port, host=sni)
        if cert.get("key") == "RSA" and cert.get("key_bits", 4096) < 2048:
            _add(out, "cert_weak_key", WARN, category="web", port=port, bits=cert["key_bits"])
        if cert.get("signature") in ("md5", "sha1"):
            _add(out, "cert_weak_signature", WARN, category="web", port=port, algo=cert["signature"])
        versions = data.get("versions", {})
        for proto in ("TLSv1", "TLSv1.1"):
            if versions.get(proto) is True:
                _add(out, "tls_old_version", WARN, category="web", port=port, version=proto)
        if versions.get("TLSv1.2") is False and versions.get("TLSv1.3") is False:
            _add(out, "tls_no_modern", WARN, category="web", port=port)
        if versions.get("TLSv1.3") is True:
            _add(out, "tls_13_ok", OK, category="web", port=port)
        if data.get("cipher_bits") and data["cipher_bits"] < 128:
            _add(out, "tls_weak_cipher", WARN, category="web", port=port, cipher=data.get("cipher", ""))


def _host_ok(host, names):
    from . import probes
    return probes.name_matches(host, names)


def _http(out, pages):
    for port, page in pages.items():
        if page.get("error"):
            continue
        if port == 80 and page.get("status") in (301, 302, 307, 308) and page.get("location", "").startswith("https"):
            _add(out, "http_redirect_https", OK, category="web", port=port)
        elif port == 80 and page.get("status", 0) < 300:
            _add(out, "http_no_https_redirect", INFO, category="web", port=port)
        missing = page.get("missing_security_headers", [])
        if page.get("tls") and "strict-transport-security" in missing:
            _add(out, "http_no_hsts", INFO, category="web", port=port)
        if page.get("status", 0) >= 500:
            _add(out, "http_server_error", WARN, category="web", port=port, status=page["status"])
        server = page.get("headers", {}).get("server", "")
        if server:
            _add(out, "http_server_banner", INFO, category="web", port=port, server=server)
        for cookie in page.get("set_cookie", []):
            low = cookie.lower()
            if page.get("tls") and "secure" not in low:
                _add(out, "cookie_insecure", INFO, category="web", port=port)
                break


def _smb(out, smb):
    if smb.get("closed") or smb.get("error"):
        return
    if smb.get("smb1"):
        _add(out, "smb1_enabled", ERROR, category="services")
    if smb.get("signing_required") is False:
        _add(out, "smb_signing_off", WARN, category="services")
    if smb.get("dialect"):
        _add(out, "smb_dialect", INFO, category="services", dialect=smb["dialect"])
    skew = smb.get("clock_skew_s")
    if skew is not None and abs(skew) > 120:
        _add(out, "clock_skew", WARN, category="services", seconds=abs(skew))


def _rdp(out, rdp):
    if rdp.get("closed") or rdp.get("error"):
        return
    if rdp.get("nla_required") is False:
        _add(out, "rdp_no_nla", WARN, category="services")
    if rdp.get("classic_rdp_allowed"):
        _add(out, "rdp_classic", WARN, category="services")
    if rdp.get("selected"):
        _add(out, "rdp_security", INFO, category="services", security=rdp["selected"])


def _ntp(out, ntp):
    if not ntp.get("answer"):
        return
    offset = ntp.get("offset_ms")
    if offset is not None and abs(offset) > 1000:
        _add(out, "ntp_offset", WARN, category="services", offset=round(offset))
    _add(out, "ntp_stratum", INFO, category="services", stratum=ntp.get("stratum"), ref=ntp.get("refid", ""))


def _dnsserver(out, dns):
    if not dns.get("answer"):
        return
    if dns.get("recursion_available") and dns.get("resolved_external"):
        _add(out, "open_resolver", WARN, category="services")
    else:
        _add(out, "dns_service", INFO, category="services")


def _reverse(out, rev, res):
    if not rev or rev.get("error"):
        if res.raw.get("address", {}).get("class") == "public":
            _add(out, "no_ptr", INFO, ptr=True)
        return
    if rev.get("forward_confirmed") is False:
        _add(out, "ptr_mismatch", INFO, name=(rev.get("ptr") or [""])[0])
    elif rev.get("ptr"):
        _add(out, "ptr_ok", OK, name=rev["ptr"][0])


def _dns(out, dns):
    if not dns:
        return
    records = dns.get("records", {})
    if not records.get("A", {}).get("values") and not records.get("AAAA", {}).get("values"):
        _add(out, "dns_no_address", WARN, category="dns")
    # Namensserver
    ns = dns.get("ns", [])
    serials = {n["serial"] for n in ns if n.get("serial") is not None}
    if len(serials) > 1:
        _add(out, "ns_serial_mismatch", WARN, category="dns", count=len(serials))
    if ns and len(ns) < 2:
        _add(out, "ns_single", WARN, category="dns")
    for n in ns:
        if n.get("recursive"):
            _add(out, "ns_recursive", WARN, category="dns", server=n["name"])
    if dns.get("cname_target_missing"):
        _add(out, "cname_dangling", ERROR, category="dns")
    # DNSSEC
    sec = dns.get("dnssec", {})
    if sec.get("ds") and sec.get("dnskey"):
        _add(out, "dnssec_on", OK, category="dns")
    elif sec.get("dnskey") and not sec.get("ds"):
        _add(out, "dnssec_unsigned_parent", INFO, category="dns")
    # Mail
    mail = dns.get("mail", {})
    if mail:
        _mail(out, mail)
    if dns.get("wildcard"):
        _add(out, "dns_wildcard", INFO, category="dns")


def _mail(out, mail):
    if not mail.get("mx"):
        _add(out, "mail_no_mx", INFO, category="dns")
        return
    if mail.get("spf_count", 0) == 0:
        _add(out, "mail_no_spf", WARN, category="dns")
    elif mail.get("spf_count", 0) > 1:
        _add(out, "mail_multi_spf", ERROR, category="dns")
    else:
        spf = mail.get("spf", {})
        if spf.get("all") in ("+all", "?all"):
            _add(out, "mail_spf_weak", WARN, category="dns", mechanism=spf["all"])
        if spf.get("lookups", 0) > 10:
            _add(out, "mail_spf_lookups", WARN, category="dns", count=spf["lookups"])
        if spf.get("all") in ("-all", "~all"):
            _add(out, "mail_spf_ok", OK, category="dns")
    dmarc = mail.get("dmarc")
    if not dmarc:
        _add(out, "mail_no_dmarc", WARN, category="dns")
    else:
        policy = dmarc.get("p", "none")
        if policy == "none":
            _add(out, "mail_dmarc_none", INFO, category="dns")
        else:
            _add(out, "mail_dmarc_ok", OK, category="dns", policy=policy)
    if not mail.get("dkim_selectors"):
        _add(out, "mail_no_dkim", INFO, category="dns")
    for mx in mail["mx"]:
        if mx.get("fcrdns") is False:
            _add(out, "mail_mx_no_ptr", INFO, category="dns", host=mx.get("host", ""))
            break
