"""DNS-Prüfungen mit dnspython (asynchron)."""

from __future__ import annotations

import asyncio
import ipaddress
import secrets
import time

import dns.asyncquery
import dns.asyncresolver
import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.rdatatype
import dns.resolver
import dns.reversename

RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "CAA", "SRV")
SRV_NAMES = ("_ldap._tcp.dc._msdcs", "_kerberos._tcp", "_gc._tcp", "_autodiscover._tcp", "_sip._tls",
             "_sipfederationtls._tcp", "_xmpp-client._tcp", "_caldavs._tcp")
DKIM_SELECTORS = ("selector1", "selector2", "default", "google", "k1", "s1", "s2", "dkim", "mail")


def _resolver(timeout: float) -> dns.asyncresolver.Resolver:
    r = dns.asyncresolver.Resolver()
    r.lifetime = timeout
    r.timeout = min(2.0, timeout)
    return r


async def _query(r, name: str, rtype: str):
    """(rrset-Texte, ttl, fehlercode) - fehlercode: '' | 'nxdomain' | 'noanswer' | 'timeout' | 'error'."""
    try:
        ans = await r.resolve(name, rtype, raise_on_no_answer=True)
        return [rd.to_text() for rd in ans], ans.rrset.ttl, ""
    except dns.resolver.NXDOMAIN:
        return [], None, "nxdomain"
    except dns.resolver.NoAnswer:
        return [], None, "noanswer"
    except (dns.exception.Timeout, dns.resolver.LifetimeTimeout):
        return [], None, "timeout"
    except (dns.resolver.NoNameservers, dns.exception.DNSException):
        return [], None, "error"


async def reverse(ip: str, timeout: float = 3.0) -> dict:
    r = _resolver(timeout)
    names, ttl, err = await _query(r, dns.reversename.from_address(ip).to_text(), "PTR")
    result = {"ptr": [n.rstrip(".") for n in names], "ttl": ttl, "error": err, "forward_confirmed": None}
    if names:
        rtype = "AAAA" if ":" in ip else "A"
        fwd, _, _ = await _query(r, names[0], rtype)
        result["forward"] = fwd
        result["forward_confirmed"] = ipaddress.ip_address(ip).compressed in [
            ipaddress.ip_address(a).compressed for a in fwd]
    return result


async def resolve_name(name: str, timeout: float = 4.0) -> dict:
    r = _resolver(timeout)
    start = time.perf_counter()
    a, a_ttl, a_err = await _query(r, name, "A")
    ms = (time.perf_counter() - start) * 1000
    aaaa, aaaa_ttl, _ = await _query(r, name, "AAAA")
    cname, _, _ = await _query(r, name, "CNAME")
    return {"a": a, "aaaa": aaaa, "cname": [c.rstrip(".") for c in cname], "ttl": a_ttl or aaaa_ttl,
            "error": a_err if not (a or aaaa) else "", "time_ms": round(ms, 1),
            "resolvers": list(dns.resolver.get_default_resolver().nameservers)}


async def _zone_of(r, name: str) -> str:
    n = dns.name.from_text(name)
    while True:
        try:
            await r.resolve(n, "SOA")
            return n.to_text().rstrip(".")
        except dns.resolver.NoAnswer:
            pass
        except dns.exception.DNSException:
            pass
        if n == dns.name.root or len(n.labels) <= 2:
            return n.to_text().rstrip(".")
        n = n.parent()


async def _ns_check(zone: str, ns_name: str, r, timeout: float) -> dict:
    entry: dict = {"name": ns_name.rstrip("."), "ips": [], "serial": None, "aa": None, "time_ms": None, "error": ""}
    ips, _, err = await _query(r, ns_name, "A")
    entry["ips"] = ips
    if not ips:
        entry["error"] = err or "noaddress"
        return entry
    q = dns.message.make_query(zone, "SOA")
    q.flags &= ~dns.flags.RD
    start = time.perf_counter()
    try:
        resp = await dns.asyncquery.udp(q, ips[0], timeout=timeout)
        entry["time_ms"] = round((time.perf_counter() - start) * 1000, 1)
        entry["aa"] = bool(resp.flags & dns.flags.AA)
        for rrset in resp.answer:
            if rrset.rdtype == dns.rdatatype.SOA:
                entry["serial"] = rrset[0].serial
        rq = dns.message.make_query("example.com", "A")   # beantwortet der Server fremde Namen?
        rresp = await dns.asyncquery.udp(rq, ips[0], timeout=timeout)
        entry["recursive"] = bool(rresp.flags & dns.flags.RA) and bool(rresp.answer)
    except (dns.exception.DNSException, OSError) as exc:
        entry["error"] = type(exc).__name__
    return entry


def parse_spf(txt: str) -> dict:
    terms = txt.split()[1:]
    lookups = sum(1 for t in terms if t.lstrip("+-~?").split(":")[0].split("=")[0]
                  in ("include", "a", "mx", "ptr", "exists", "redirect"))
    final = next((t for t in reversed(terms) if t.lstrip("+-~?") == "all"), "")
    return {"record": txt, "lookups": lookups, "all": final, "ptr": any(t.lstrip("+-~?").startswith("ptr")
                                                                       for t in terms)}


def parse_tags(txt: str) -> dict:
    return {k.strip().lower(): v.strip() for k, _, v in (p.partition("=") for p in txt.split(";")) if k.strip()}


async def domain_checks(name: str, timeout: float = 4.0, options: dict | None = None) -> dict:
    """Umfassende Prüfung eines Namens bzw. seiner Zone."""
    options = options or {}
    r = _resolver(timeout)
    zone = await _zone_of(r, name)
    result: dict = {"name": name, "zone": zone, "records": {}}

    async def rec(rtype, qname=name):
        values, ttl, err = await _query(r, qname, rtype)
        return rtype, {"values": [v.strip('"') if rtype != "TXT" else v for v in values], "ttl": ttl, "error": err}

    for rtype, data in await asyncio.gather(*(rec(t) for t in RECORD_TYPES if t != "SRV")):
        result["records"][rtype] = data
    zone_soa = result["records"]["SOA"] if zone == name else (await rec("SOA", zone))[1]
    result["soa"] = zone_soa
    if zone_soa.get("values"):
        parts = zone_soa["values"][0].split()
        if len(parts) >= 7:
            result["soa_fields"] = dict(zip(("mname", "rname", "serial", "refresh", "retry", "expire", "minimum"),
                                            parts))

    # Namensserver der Zone und deren Übereinstimmung
    ns_values, _, _ = await _query(r, zone, "NS")
    result["ns"] = list(await asyncio.gather(*(_ns_check(zone, ns, r, timeout) for ns in ns_values)))

    # CNAME-Ziel vorhanden?
    cname = result["records"]["CNAME"]["values"]
    if cname:
        _, _, err = await _query(r, cname[0], "A")
        _, _, err6 = await _query(r, cname[0], "AAAA")
        result["cname_target_missing"] = err == "nxdomain" and err6 == "nxdomain"

    # Mail: MX, SPF, DMARC, MTA-STS, TLS-RPT, DKIM
    if options.get("mail", True):
        mail: dict = {"mx": []}
        for mx in result["records"]["MX"]["values"]:
            pref, _, host = mx.partition(" ")
            host = host.rstrip(".")
            ips, _, _ = await _query(r, host, "A") if host else ([], None, "")
            entry = {"preference": int(pref) if pref.isdigit() else pref, "host": host, "ips": ips}
            if ips:
                rev = await reverse(ips[0], timeout)
                entry["ptr"] = rev["ptr"]
                entry["fcrdns"] = rev["forward_confirmed"]
            mail["mx"].append(entry)
        txts = [t.strip('"').replace('" "', "") for t in result["records"]["TXT"]["values"]]
        spf = [t for t in txts if t.lower().startswith("v=spf1")]
        mail["spf_count"] = len(spf)
        if spf:
            mail["spf"] = parse_spf(spf[0])
        dmarc, _, _ = await _query(r, f"_dmarc.{zone}", "TXT")
        dmarc = [t.strip('"').replace('" "', "") for t in dmarc if "v=dmarc1" in t.lower()]
        if dmarc:
            mail["dmarc"] = parse_tags(dmarc[0]) | {"record": dmarc[0]}
        mta, _, _ = await _query(r, f"_mta-sts.{zone}", "TXT")
        mail["mta_sts"] = bool(mta)
        tlsrpt, _, _ = await _query(r, f"_smtp._tls.{zone}", "TXT")
        mail["tls_rpt"] = bool(tlsrpt)
        dkim = await asyncio.gather(*(_query(r, f"{s}._domainkey.{zone}", "TXT") for s in DKIM_SELECTORS))
        mail["dkim_selectors"] = [s for s, (v, _, _) in zip(DKIM_SELECTORS, dkim) if v]
        result["mail"] = mail

    # Dienste (SRV), u. a. Active Directory
    srv = await asyncio.gather(*(_query(r, f"{s}.{zone}", "SRV") for s in SRV_NAMES))
    result["srv"] = {s: v for s, (v, _, _) in zip(SRV_NAMES, srv) if v}

    # DNSSEC
    dnskey, _, _ = await _query(r, zone, "DNSKEY")
    ds, _, _ = await _query(r, zone, "DS")
    validated = None
    try:
        q = dns.message.make_query(name, "A", want_dnssec=True)
        q.flags |= dns.flags.AD
        resp = await dns.asyncquery.udp(q, r.nameservers[0], timeout=timeout)
        validated = bool(resp.flags & dns.flags.AD)
    except (dns.exception.DNSException, OSError, IndexError):
        pass
    result["dnssec"] = {"dnskey": len(dnskey), "ds": len(ds), "validated": validated}

    # Wildcard-Eintrag?
    probe = f"omniwrench-{secrets.token_hex(4)}.{zone}"
    wild, _, _ = await _query(r, probe, "A")
    result["wildcard"] = wild
    # IPv6 und Rückwärtsauflösung der Adressen
    result["ptr"] = {}
    for ip in (result["records"]["A"]["values"] + result["records"]["AAAA"]["values"])[:6]:
        result["ptr"][ip] = await reverse(ip, timeout)
    return result


async def asn_lookup(ip: str, timeout: float = 3.0) -> dict:
    """Netzbetreiber über den DNS-Dienst von Team Cymru (origin.asn.cymru.com)."""
    addr = ipaddress.ip_address(ip)
    if not addr.is_global:
        return {}
    if addr.version == 4:
        qname = ".".join(reversed(ip.split("."))) + ".origin.asn.cymru.com"
    else:
        nibbles = addr.exploded.replace(":", "")
        qname = ".".join(reversed(nibbles)) + ".origin6.asn.cymru.com"
    r = _resolver(timeout)
    txt, _, _ = await _query(r, qname, "TXT")
    if not txt:
        return {}
    parts = [p.strip() for p in txt[0].strip('"').split("|")]
    result = {"asn": parts[0].split()[0] if parts else "", "prefix": parts[1] if len(parts) > 1 else "",
              "country": parts[2] if len(parts) > 2 else "", "registry": parts[3] if len(parts) > 3 else ""}
    if result["asn"]:
        desc, _, _ = await _query(r, f"AS{result['asn']}.asn.cymru.com", "TXT")
        if desc:
            result["owner"] = desc[0].strip('"').split("|")[-1].strip()
    return result
