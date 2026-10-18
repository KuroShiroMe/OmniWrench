"""Protokoll-Abfragen ohne Anmeldung: TCP-Verbindung, Banner, HTTP, TLS, SMB, RDP, NTP, DNS, NetBIOS.

Alle Abfragen sind lesend und entsprechen dem, was ein normaler Client beim Verbindungsaufbau
sendet (Verhandlung der Protokollversion). Es werden keine Zugangsdaten ausprobiert.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import errno
import os
import re
import socket
import ssl
import struct
import time

USER_AGENT = "OmniWrench-NetProbe/1.0"


# ------------------------------------------------------------------ TCP
async def tcp_connect(ip: str, port: int, timeout: float) -> tuple[str, float | None]:
    """('open' | 'closed' | 'filtered', Verbindungszeit in ms)."""
    start = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
    except asyncio.TimeoutError:
        return "filtered", None
    except ConnectionRefusedError:
        return "closed", (time.perf_counter() - start) * 1000
    except OSError as exc:
        if exc.errno in (errno.ECONNREFUSED, 10061):
            return "closed", (time.perf_counter() - start) * 1000
        return "filtered", None
    ms = (time.perf_counter() - start) * 1000
    writer.close()
    try:
        await asyncio.wait_for(writer.wait_closed(), 1)
    except (OSError, asyncio.TimeoutError):
        pass
    return "open", ms


async def banner(ip: str, port: int, timeout: float = 2.0) -> str:
    """Begrüßungstext von Diensten, die zuerst senden (SSH, FTP, SMTP, POP3, IMAP, MySQL ...)."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
    except (OSError, asyncio.TimeoutError):
        return ""
    try:
        data = await asyncio.wait_for(reader.read(512), timeout)
    except (OSError, asyncio.TimeoutError):
        data = b""
    finally:
        writer.close()
    return _printable(data)


def _printable(data: bytes) -> str:
    text = data.decode("utf-8", "replace")
    text = "".join(ch if ch.isprintable() or ch in "\r\n\t" else "·" for ch in text)
    return text.strip()[:400]


# ------------------------------------------------------------------ TLS
def _insecure_ctx(minimum=None, maximum=None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("ALL:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    if minimum:
        ctx.minimum_version = minimum
    if maximum:
        ctx.maximum_version = maximum
    return ctx


def _verify_ctx() -> ssl.SSLContext:
    try:
        import truststore  # Windows-Zertifikatsspeicher (Firmen-Proxys, eigene CA)
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


async def _handshake(ip: str, port: int, ctx: ssl.SSLContext, sni: str | None, timeout: float):
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(ip, port, ssl=ctx, server_hostname=sni or None), timeout)
    obj = writer.get_extra_info("ssl_object")
    info = (obj.version(), obj.cipher(), obj.getpeercert(binary_form=True))
    writer.close()
    return info


def parse_cert(der: bytes) -> dict:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, rsa
    cert = x509.load_der_x509_certificate(der)
    key = cert.public_key()
    if isinstance(key, rsa.RSAPublicKey):
        key_desc, key_bits = "RSA", key.key_size
    elif isinstance(key, ec.EllipticCurvePublicKey):
        key_desc, key_bits = f"EC {key.curve.name}", key.curve.key_size
    elif isinstance(key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
        key_desc, key_bits = type(key).__name__.replace("PublicKey", ""), 256
    elif isinstance(key, dsa.DSAPublicKey):
        key_desc, key_bits = "DSA", key.key_size
    else:
        key_desc, key_bits = "?", 0
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        names = san.get_values_for_type(x509.DNSName) + [str(i) for i in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        names = []
    not_after = cert.not_valid_after_utc
    not_before = cert.not_valid_before_utc
    sig = cert.signature_hash_algorithm.name if cert.signature_hash_algorithm else "?"
    return {
        "subject": cert.subject.rfc4514_string(), "issuer": cert.issuer.rfc4514_string(),
        "self_signed": cert.subject == cert.issuer, "san": names,
        "not_before": not_before.isoformat(), "not_after": not_after.isoformat(),
        "days_left": (not_after - dt.datetime.now(dt.timezone.utc)).days,
        "not_yet_valid": not_before > dt.datetime.now(dt.timezone.utc),
        "key": key_desc, "key_bits": key_bits, "signature": sig, "serial": format(cert.serial_number, "X"),
        "sha256": cert.fingerprint(hashes.SHA256()).hex(":").upper(),
    }


def name_matches(host: str, names: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for n in names:
        n = n.lower().rstrip(".")
        if n == host or (n.startswith("*.") and host.count(".") == n.count(".") and host.endswith(n[1:])):
            return True
    return False


async def tls_probe(ip: str, port: int, sni: str | None, timeout: float = 4.0, versions: bool = True) -> dict:
    result: dict = {"port": port, "sni": sni or ""}
    try:
        version, cipher, der = await _handshake(ip, port, _insecure_ctx(), sni, timeout)
    except (OSError, asyncio.TimeoutError, ssl.SSLError) as exc:
        result["error"] = str(exc) or type(exc).__name__
        return result
    result.update(version=version, cipher=cipher[0] if cipher else "", cipher_bits=cipher[2] if cipher else 0)
    try:
        result["cert"] = parse_cert(der)
    except Exception as exc:  # noqa: BLE001 - beschädigte Zertifikate trotzdem melden
        result["cert_error"] = str(exc)
    # Vertrauenskette prüfen (Windows-Zertifikatsspeicher)
    ctx = _verify_ctx()
    ctx.check_hostname = bool(sni)
    try:
        await _handshake(ip, port, ctx, sni, timeout)
        result["trusted"] = True
    except ssl.SSLCertVerificationError as exc:
        result["trusted"] = False
        result["verify_error"] = exc.verify_message or str(exc)
    except (OSError, asyncio.TimeoutError, ssl.SSLError) as exc:
        result["trusted"] = None
        result["verify_error"] = str(exc)
    if versions:
        supported = {}
        for name, ver in (("TLSv1", ssl.TLSVersion.TLSv1), ("TLSv1.1", ssl.TLSVersion.TLSv1_1),
                          ("TLSv1.2", ssl.TLSVersion.TLSv1_2), ("TLSv1.3", ssl.TLSVersion.TLSv1_3)):
            try:
                ctx = _insecure_ctx(ver, ver)
            except (ValueError, ssl.SSLError):
                supported[name] = None   # lokal nicht prüfbar
                continue
            try:
                await _handshake(ip, port, ctx, sni, timeout)
                supported[name] = True
            except ssl.SSLError as exc:
                # Der eigene TLS-Stack verweigert alte Versionen -> unbekannt statt "nicht unterstützt"
                supported[name] = None if "NO_PROTOCOLS_AVAILABLE" in str(exc).upper() else False
            except (OSError, asyncio.TimeoutError):
                supported[name] = False
        result["versions"] = supported
    return result


# ------------------------------------------------------------------ HTTP
SECURITY_HEADERS = ("strict-transport-security", "content-security-policy", "x-content-type-options",
                    "x-frame-options", "referrer-policy", "permissions-policy")


async def http_probe(ip: str, port: int, host: str, tls: bool, timeout: float = 5.0, path: str = "/") -> dict:
    result: dict = {"port": port, "tls": tls, "host": host}
    ctx = _insecure_ctx() if tls else None
    start = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port, ssl=ctx, server_hostname=(host if tls else None)), timeout)
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {USER_AGENT}\r\nAccept: */*\r\n"
               f"Connection: close\r\n\r\n")
        writer.write(req.encode())
        await writer.drain()
        data = b""
        while len(data) < 65536:
            chunk = await asyncio.wait_for(reader.read(8192), timeout)
            if not chunk:
                break
            data += chunk
            if b"</title>" in data.lower() and b"\r\n\r\n" in data:
                break
        writer.close()
    except (OSError, asyncio.TimeoutError, ssl.SSLError) as exc:
        result["error"] = str(exc) or type(exc).__name__
        return result
    result["time_ms"] = round((time.perf_counter() - start) * 1000, 1)
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1", "replace").split("\r\n")
    m = re.match(r"HTTP/(\d\.\d|\d)\s+(\d{3})\s*(.*)", lines[0] if lines else "")
    if not m:
        result["error"] = "no HTTP response"
        result["raw"] = _printable(data[:200])
        return result
    headers: dict[str, list[str]] = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        headers.setdefault(k.strip().lower(), []).append(v.strip())
    result.update(http_version=m.group(1), status=int(m.group(2)), reason=m.group(3),
                  headers={k: ", ".join(v) for k, v in headers.items()}, set_cookie=headers.get("set-cookie", []))
    t = re.search(rb"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    if t:
        result["title"] = re.sub(r"\s+", " ", t.group(1).decode("utf-8", "replace")).strip()[:200]
    result["location"] = headers.get("location", [""])[0]
    result["missing_security_headers"] = [h for h in SECURITY_HEADERS if h not in headers
                                          and not (h == "strict-transport-security" and not tls)]
    return result


# ------------------------------------------------------------------ SMB
def _smb2_negotiate() -> bytes:
    dialects = [0x0202, 0x0210, 0x0300, 0x0302, 0x0311]
    hdr = b"\xfeSMB" + struct.pack("<HHIHHIIQIIQ16s", 64, 0, 0, 0, 1, 0, 0, 0, 0xFEFF, 0, 0, b"\0" * 16)
    ctx_offset = 64 + 36 + len(dialects) * 2
    pad = (8 - ctx_offset % 8) % 8
    ctx_offset += pad
    # Preauth-Integrity- und Verschlüsselungs-Kontext (für SMB 3.1.1 vorgeschrieben)
    preauth = struct.pack("<HHI", 1, 38, 0) + struct.pack("<HHH", 1, 32, 1) + os.urandom(32)
    preauth += b"\0" * ((8 - len(preauth) % 8) % 8)
    enc = struct.pack("<HHI", 2, 6, 0) + struct.pack("<HHH", 2, 2, 1)
    body = struct.pack("<HHHHI16sIHH", 36, len(dialects), 1, 0, 0x7F, os.urandom(16), ctx_offset, 2, 0)
    body += b"".join(struct.pack("<H", d) for d in dialects) + b"\0" * pad + preauth + enc
    msg = hdr + body
    return struct.pack(">I", len(msg)) + msg


def _smb1_negotiate() -> bytes:
    dialects = b"\x02NT LM 0.12\x00"
    hdr = b"\xffSMB" + bytes([0x72]) + b"\0" * 4 + b"\x18" + struct.pack("<H", 0xC853) + b"\0" * 12 \
        + struct.pack("<HHHH", 0, 0xFEFF, 0, 0)
    msg = hdr + b"\x00" + struct.pack("<H", len(dialects)) + dialects
    return struct.pack(">I", len(msg)) + msg


async def _exchange(ip: str, port: int, payload: bytes, timeout: float, size: int = 4096) -> bytes:
    reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
    try:
        writer.write(payload)
        await writer.drain()
        return await asyncio.wait_for(reader.read(size), timeout)
    finally:
        writer.close()


SMB_DIALECTS = {0x0202: "2.0.2", 0x0210: "2.1", 0x0300: "3.0", 0x0302: "3.0.2", 0x0311: "3.1.1"}


async def smb_probe(ip: str, timeout: float = 4.0) -> dict:
    result: dict = {}
    try:
        data = await _exchange(ip, 445, _smb2_negotiate(), timeout)
        if data[4:8] == b"\xfeSMB" and len(data) >= 4 + 64 + 8:
            body = data[4 + 64:]
            sec_mode, dialect = struct.unpack_from("<HH", body, 2)
            result["dialect"] = SMB_DIALECTS.get(dialect, hex(dialect))
            result["signing_required"] = bool(sec_mode & 0x02)
            result["signing_enabled"] = bool(sec_mode & 0x01)
            caps = struct.unpack_from("<I", body, 24)[0] if len(body) >= 28 else 0
            result["encryption_cap"] = bool(caps & 0x40) or dialect == 0x0311
            if len(body) >= 48:
                systime = struct.unpack_from("<Q", body, 40)[0]
                if systime:
                    t = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(microseconds=systime // 10)
                    result["server_time"] = t.isoformat(timespec="seconds")
                    result["clock_skew_s"] = round((t - dt.datetime.now(dt.timezone.utc)).total_seconds())
        else:
            result["error"] = "no SMB2 response"
    except (OSError, asyncio.TimeoutError) as exc:
        result["error"] = str(exc) or type(exc).__name__
    try:
        data = await _exchange(ip, 445, _smb1_negotiate(), timeout)
        result["smb1"] = data[4:8] == b"\xffSMB" and data[9:13] == b"\0\0\0\0"
    except (OSError, asyncio.TimeoutError):
        result["smb1"] = False
    return result


# ------------------------------------------------------------------ RDP
async def _rdp_request(ip: str, protocols: int, timeout: float) -> tuple[str, int]:
    neg = struct.pack("<BBHI", 1, 0, 8, protocols)
    x224 = bytes([6 + len(neg), 0xE0, 0, 0, 0, 0, 0]) + neg
    tpkt = struct.pack(">BBH", 3, 0, 4 + len(x224)) + x224
    data = await _exchange(ip, 3389, tpkt, timeout, 64)
    if len(data) >= 19 and data[11] == 2:
        return "ok", struct.unpack_from("<I", data, 15)[0]
    if len(data) >= 19 and data[11] == 3:
        return "failure", struct.unpack_from("<I", data, 15)[0]
    return ("ok", 0) if len(data) >= 11 else ("none", 0)


async def rdp_probe(ip: str, timeout: float = 4.0) -> dict:
    result: dict = {}
    try:
        kind, value = await _rdp_request(ip, 0x0B, timeout)      # TLS | CredSSP | CredSSP-EX
        result["selected"] = {0: "RDP", 1: "TLS", 2: "CredSSP (NLA)", 8: "RDSTLS"}.get(value, hex(value)) \
            if kind == "ok" else ""
        kind0, value0 = await _rdp_request(ip, 0x00, timeout)    # nur klassische RDP-Sicherheit
        result["classic_rdp_allowed"] = kind0 == "ok" and value0 == 0
        kind1, value1 = await _rdp_request(ip, 0x01, timeout)    # TLS ohne NLA
        result["nla_required"] = kind1 == "failure" and value1 == 5  # HYBRID_REQUIRED_BY_SERVER
    except (OSError, asyncio.TimeoutError) as exc:
        result["error"] = str(exc) or type(exc).__name__
    return result


# ------------------------------------------------------------------ UDP
class _UDP(asyncio.DatagramProtocol):
    def __init__(self):
        self.future = asyncio.get_running_loop().create_future()

    def datagram_received(self, data, addr):
        if not self.future.done():
            self.future.set_result(data)

    def error_received(self, exc):
        if not self.future.done():
            self.future.set_exception(exc)


async def udp_query(ip: str, port: int, payload: bytes, timeout: float = 2.0) -> bytes | None:
    loop = asyncio.get_running_loop()
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    transport, proto = await loop.create_datagram_endpoint(_UDP, remote_addr=(ip, port), family=family)
    try:
        transport.sendto(payload)
        return await asyncio.wait_for(proto.future, timeout)
    except (asyncio.TimeoutError, OSError):
        return None
    finally:
        transport.close()


NTP_EPOCH = 2208988800


async def ntp_probe(ip: str, timeout: float = 2.0) -> dict:
    t1 = time.time()
    data = await udp_query(ip, 123, b"\x23" + b"\0" * 47, timeout)
    t4 = time.time()
    if not data or len(data) < 48:
        return {"answer": False}
    stratum = data[1]
    refid = data[12:16]
    t2 = struct.unpack("!I", data[32:36])[0] - NTP_EPOCH + struct.unpack("!I", data[36:40])[0] / 2**32
    t3 = struct.unpack("!I", data[40:44])[0] - NTP_EPOCH + struct.unpack("!I", data[44:48])[0] / 2**32
    offset = ((t2 - t1) + (t3 - t4)) / 2
    ref = refid.decode("ascii", "replace").strip("\0") if stratum <= 1 else socket.inet_ntoa(refid)
    return {"answer": True, "stratum": stratum, "offset_ms": round(offset * 1000, 1),
            "delay_ms": round(((t4 - t1) - (t3 - t2)) * 1000, 1), "refid": ref, "leap": data[0] >> 6,
            "version": (data[0] >> 3) & 7}


def _dns_query(name: str, qtype: int = 1, rd: bool = True) -> tuple[int, bytes]:
    qid = int.from_bytes(os.urandom(2), "big")
    flags = 0x0100 if rd else 0
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    return qid, struct.pack(">HHHHHH", qid, flags, 1, 0, 0, 0) + q + struct.pack(">HH", qtype, 1)


async def dns_server_probe(ip: str, timeout: float = 2.0) -> dict:
    """Beantwortet das Ziel DNS-Anfragen? Löst es fremde Namen rekursiv auf (offener Resolver)?"""
    qid, pkt = _dns_query("www.microsoft.com")
    start = time.perf_counter()
    data = await udp_query(ip, 53, pkt, timeout)
    if not data or len(data) < 12:
        return {"answer": False}
    ms = (time.perf_counter() - start) * 1000
    _, flags, _, ancount, _, _ = struct.unpack(">HHHHHH", data[:12])
    rcode = flags & 0x0F
    return {"answer": True, "time_ms": round(ms, 1), "recursion_available": bool(flags & 0x0080),
            "resolved_external": rcode == 0 and ancount > 0, "rcode": rcode,
            "authoritative": bool(flags & 0x0400)}


async def netbios_probe(ip: str, timeout: float = 2.0) -> dict:
    """NetBIOS-Knotenstatus: Rechnername, Arbeitsgruppe/Domäne, MAC-Adresse."""
    name = b"\x20" + b"CK" + b"A" * 30 + b"\x00"
    pkt = os.urandom(2) + b"\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00" + name + b"\x00\x21\x00\x01"
    data = await udp_query(ip, 137, pkt, timeout)
    if not data or len(data) < 57:
        return {"answer": False}
    count = data[56]
    names, pos = [], 57
    for _ in range(count):
        if pos + 18 > len(data):
            break
        raw = data[pos:pos + 15].decode("ascii", "replace").rstrip()
        suffix = data[pos + 15]
        group = bool(data[pos + 16] & 0x80)
        names.append({"name": raw, "suffix": suffix, "group": group})
        pos += 18
    mac = data[pos:pos + 6].hex("-").upper() if pos + 6 <= len(data) else ""
    computer = next((n["name"] for n in names if n["suffix"] == 0 and not n["group"]), "")
    domain = next((n["name"] for n in names if n["suffix"] == 0 and n["group"]), "")
    return {"answer": True, "computer": computer, "domain": domain, "names": names,
            "mac": mac if mac and mac != "00-00-00-00-00-00" else ""}
