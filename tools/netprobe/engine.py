"""Ablaufsteuerung: führt die gewählten Tests für alle Ziele parallel aus (asyncio in eigenem Thread)."""

from __future__ import annotations

import asyncio
import ipaddress
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from . import dnscheck, icmp, probes
from .localnet import VendorDB, mac_of
from .targets import Target, classify

# ------------------------------------------------------------ Tests und Kategorien
CATEGORIES = ("general", "route", "ports", "web", "services", "dns", "link")


@dataclass(frozen=True)
class TestDef:
    id: str
    category: str
    default: bool = True


TESTS = (
    TestDef("resolve", "general"), TestDef("reverse", "general"), TestDef("ping", "general"),
    TestDef("mtu", "general"), TestDef("mac", "general"), TestDef("netbios", "general"), TestDef("asn", "general"),
    TestDef("traceroute", "route"), TestDef("hops", "route"),
    TestDef("tcp", "ports"), TestDef("banner", "ports"),
    TestDef("http", "web"), TestDef("tls", "web"),
    TestDef("smb", "services"), TestDef("rdp", "services"), TestDef("ntp", "services"),
    TestDef("dnsserver", "services"),
    TestDef("dns", "dns"), TestDef("mail", "dns"), TestDef("dnssec", "dns"),
    # Leitungstest gegen eine Gegenstelle (braucht das linkagent-Mini-Tool/NetProbe drüben) – nie automatisch.
    TestDef("link", "link", default=False),
)
TEST_IDS = tuple(t.id for t in TESTS)

# Leitungstest-Optionen (eigener Abschnitt im Optionsdialog, Werte werden durch alle Profile getragen).
LINK_KEYS = ("link_port", "link_token", "link_seconds", "link_connections", "link_scan_ports",
             "link_latency", "link_download", "link_upload", "link_load", "link_portscan")

DEFAULT_OPTIONS = {
    "tests": {t.id: t.default for t in TESTS},
    # ping_timeout_ms bewusst großzügig (ping.exe wartet 4 s) + Aufwärm-Pings gegen ARP-/Routing-Verluste,
    # damit langsame erste Antworten nicht fälschlich als Paketverlust zählen.
    "ping_count": 10, "ping_interval_ms": 300, "ping_timeout_ms": 2000, "ping_warmup": 2,
    "port_profile": "standard", "custom_ports": "", "port_timeout_ms": 800,
    "max_hosts": 16, "max_sockets": 300, "only_alive": True,
    "max_hops": 30, "hop_pings": 4, "dns_timeout_ms": 4000, "oui_download": True,
    # Leitungstest gegen eine Gegenstelle (linkagent). Token leer = noch keines erzeugt.
    "link_port": 47600, "link_token": "", "link_seconds": 5, "link_connections": 8, "link_scan_ports": "",
    "link_latency": True, "link_download": True, "link_upload": True, "link_load": True, "link_portscan": True,
}

# Vorgefertigte Testprofile für das Dropdown neben „Starten“. "custom" nutzt die Einstellungen aus dem Dialog.
# "link" misst die Leitung zu einer Gegenstelle und braucht dort das linkagent-Mini-Tool (oder NetProbe).
TEMPLATE_IDS = ("overview", "standard", "deep", "link", "custom")

# Profile, die eine laufende Gegenstelle voraussetzen -> in der Oberfläche mit Hinweis (Ausrufezeichen).
TEMPLATES_NEED_AGENT = ("link",)


def template_options(template: str, custom: dict) -> dict:
    """Liefert die Optionen für ein Testprofil; `custom` sind die vom Nutzer gespeicherten Einstellungen."""
    if template == "custom":
        return dict(custom)
    if template == "overview":
        on = {"resolve", "reverse", "ping", "asn", "tcp", "banner", "http", "tls"}
        return {"tests": {t.id: (t.id in on) for t in TESTS},
                "port_profile": "quick", "ping_count": 5, "ping_warmup": 2, "only_alive": True}
    if template == "deep":
        return {"tests": {t.id: True for t in TESTS if t.id != "link"},
                "port_profile": "extended", "ping_count": 15, "ping_warmup": 3, "only_alive": False}
    if template == "link":
        # Fokus auf die Leitungsmessung: Name auflösen, kurzer Ping und der Leitungstest selbst.
        on = {"resolve", "reverse", "ping", "link"}
        opts = {"tests": {t.id: (t.id in on) for t in TESTS},
                "port_profile": "quick", "ping_count": 5, "ping_warmup": 2, "only_alive": False}
        for key in LINK_KEYS:                      # gespeicherte Leitungstest-Einstellungen übernehmen
            if key in custom:
                opts[key] = custom[key]
        return opts
    return {"tests": {t.id: t.default for t in TESTS}, "port_profile": "standard"}  # standard


def parse_scan_ports(text: str) -> list[int]:
    """Portliste für den Pfad-Portscan aus Freitext; leer = Standardauswahl aus linkagent."""
    from .linkagent import DEFAULT_SCAN_PORTS
    ports: set[int] = set()
    for part in (text or "").replace(";", ",").split(","):
        part = part.strip()
        if "-" in part:
            a, _, b = part.partition("-")
            if a.strip().isdigit() and b.strip().isdigit():
                ports.update(range(max(1, int(a)), min(65535, int(b)) + 1))
        elif part.isdigit() and 0 < int(part) < 65536:
            ports.add(int(part))
    return sorted(ports) or list(DEFAULT_SCAN_PORTS)

QUICK_PORTS = (21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 389, 443, 445, 587, 636, 993, 995, 1433, 3306, 3389,
               5900, 5985, 8080, 8443)
DISCOVERY_PORTS = (80, 443, 445, 22, 3389, 135)
WEB_PORTS = {80: False, 443: True, 8000: False, 8008: False, 8080: False, 8081: False, 8088: False, 8090: False,
             8443: True, 8888: False, 9443: True, 3000: False, 5000: False, 5001: True, 2083: True, 8006: True,
             9090: False, 10000: False, 16992: False, 16993: True, 5986: True, 8531: True}
TLS_PORTS = {443, 465, 636, 853, 990, 993, 995, 3269, 5061, 5671, 6443, 6514, 8443, 8883, 9443, 2376, 5986,
             8531, 5001, 2083, 8006, 16993, 3389}
BANNER_PORTS = {21, 22, 23, 25, 110, 143, 587, 2222, 3306, 5900, 1883, 119, 5222}


def port_list(options: dict, library_ports: list[int]) -> list[int]:
    profile = options.get("port_profile", "standard")
    if profile == "quick":
        return list(QUICK_PORTS)
    if profile == "extended":
        return sorted(set(range(1, 1025)) | set(library_ports))
    if profile == "full":
        return list(range(1, 65536))
    if profile == "custom":
        ports: set[int] = set()
        for part in options.get("custom_ports", "").replace(";", ",").split(","):
            part = part.strip()
            if "-" in part:
                a, _, b = part.partition("-")
                if a.strip().isdigit() and b.strip().isdigit():
                    ports.update(range(max(1, int(a)), min(65535, int(b)) + 1))
            elif part.isdigit() and 0 < int(part) < 65536:
                ports.add(int(part))
        return sorted(ports) or list(QUICK_PORTS)
    return sorted(set(library_ports))


# ------------------------------------------------------------ Ergebnis je Ziel
PENDING, RUNNING, DONE, NO_ANSWER, ERROR, STOPPED = "pending", "running", "done", "no_answer", "error", "stopped"


@dataclass
class TargetResult:
    target: Target
    ip: str = ""
    status: str = PENDING
    step: str = ""                                   # Test, der gerade läuft
    total: int = 0
    done: int = 0
    raw: dict = field(default_factory=dict)          # Test-ID -> Rohdaten
    errors: dict = field(default_factory=dict)
    started: float = 0.0
    finished: float = 0.0
    findings: list = field(default_factory=list)     # wird von findings.evaluate gefüllt

    @property
    def label(self) -> str:
        return self.target.label


def ping_stats(echos: list[icmp.Echo]) -> dict:
    rtts = [e.rtt_ms for e in echos if e.status == icmp.OK and e.rtt_ms is not None]
    sent = len(echos)
    result: dict = {"sent": sent, "received": len(rtts), "loss_pct": round(100 * (sent - len(rtts)) / sent, 1)
                    if sent else 100.0, "statuses": [e.status for e in echos], "rtts": rtts}
    if rtts:
        diffs = [abs(a - b) for a, b in zip(rtts, rtts[1:])]
        result.update(min=min(rtts), max=max(rtts), avg=round(statistics.fmean(rtts), 2),
                      median=round(statistics.median(rtts), 2),
                      stdev=round(statistics.pstdev(rtts), 2) if len(rtts) > 1 else 0.0,
                      jitter=round(statistics.fmean(diffs), 2) if diffs else 0.0)
        ttls = [e.ttl for e in echos if e.ttl]
        if ttls:
            ttl = max(set(ttls), key=ttls.count)
            initial = next((i for i in (32, 64, 128, 255) if ttl <= i), 255)
            result.update(ttl=ttl, initial_ttl=initial, hops=initial - ttl,
                          os_guess={32: "windows_old", 64: "unix", 128: "windows", 255: "network"}[initial])
    unreachable = next((e for e in echos if e.status == icmp.UNREACHABLE), None)
    if unreachable:
        result["unreachable_from"] = unreachable.from_ip
    return result


class Engine:
    def __init__(self, options: dict, library_ports: list[int], vendors: VendorDB,
                 on_update: Callable[[TargetResult], None], on_finished: Callable[[], None]):
        self.options = DEFAULT_OPTIONS | options
        self.tests = DEFAULT_OPTIONS["tests"] | options.get("tests", {})
        self.ports = port_list(self.options, library_ports)
        self.vendors = vendors
        self.on_update = on_update
        self.on_finished = on_finished
        self.results: list[TargetResult] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main: asyncio.Task | None = None
        self._stopping = False
        self._thread: threading.Thread | None = None

    # -------------------------------------------------------------- Steuerung
    def start(self, targets: list[Target]) -> list[TargetResult]:
        self.results = [TargetResult(t) for t in targets]
        self._thread = threading.Thread(target=self._run, name="netprobe", daemon=True)
        self._thread.start()
        return self.results

    def stop(self) -> None:
        self._stopping = True
        if self._loop and self._main:
            self._loop.call_soon_threadsafe(self._main.cancel)

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        pool = ThreadPoolExecutor(max_workers=64, thread_name_prefix="netprobe-icmp")
        loop.set_default_executor(pool)
        try:
            self._main = loop.create_task(self._all())
            loop.run_until_complete(self._main)
        except asyncio.CancelledError:
            pass
        finally:
            for r in self.results:
                if r.status in (PENDING, RUNNING):
                    r.status = STOPPED
                    self.on_update(r)
            pool.shutdown(wait=False, cancel_futures=True)
            loop.close()
            self.on_finished()

    async def _all(self) -> None:
        self.sockets = asyncio.Semaphore(int(self.options["max_sockets"]))
        hosts = asyncio.Semaphore(int(self.options["max_hosts"]))

        async def one(res: TargetResult):
            async with hosts:
                if self._stopping:
                    return
                try:
                    await self._target(res)
                except asyncio.CancelledError:
                    res.status = STOPPED
                    raise
                except Exception as exc:  # noqa: BLE001 - ein Ziel darf die anderen nicht abbrechen
                    res.status = ERROR
                    res.errors["engine"] = f"{type(exc).__name__}: {exc}"
                finally:
                    res.finished = time.time()
                    from .findings import evaluate
                    res.findings = evaluate(res)
                    self.on_update(res)

        await asyncio.gather(*(one(r) for r in self.results))

    # -------------------------------------------------------------- je Ziel
    def _on(self, test: str) -> bool:
        return bool(self.tests.get(test))

    async def _step(self, res: TargetResult, test: str, coro) -> None:
        res.step = test
        self.on_update(res)
        try:
            res.raw[test] = await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            res.errors[test] = f"{type(exc).__name__}: {exc}"
        res.done += 1
        self.on_update(res)

    async def _tcp(self, ip: str, port: int, timeout: float):
        async with self.sockets:
            return await probes.tcp_connect(ip, port, timeout)

    async def _target(self, res: TargetResult) -> None:
        o = self.options
        t = res.target
        res.status = RUNNING
        res.started = time.time()
        dns_timeout = o["dns_timeout_ms"] / 1000
        name_tests = [x for x in ("dns", "mail", "dnssec") if self._on(x)] if t.name else []
        planned = [x for x in TEST_IDS if self._on(x) and x not in ("dns", "mail", "dnssec")]
        res.total = len(planned) + (1 if name_tests else 0)
        self.on_update(res)

        # 1. Name auflösen
        if t.name:
            data = await dnscheck.resolve_name(t.name, dns_timeout)
            res.raw["resolve"] = data
            addrs = data["a"] + data["aaaa"]
            res.ip = addrs[0] if addrs else ""
        else:
            res.ip = t.address
            if self._on("resolve"):
                res.raw["resolve"] = {"input_ip": True}
        if self._on("resolve"):
            res.done += 1
        if res.ip:
            res.raw["address"] = {"ip": res.ip, "version": ipaddress.ip_address(res.ip).version,
                                  "class": classify(res.ip)}
        dns_task = None
        if name_tests:
            dns_task = asyncio.create_task(self._step(res, "dns", dnscheck.domain_checks(
                t.name, dns_timeout, {"mail": self._on("mail")})))
        if not res.ip:
            res.status = ERROR
            res.errors.setdefault("resolve", res.raw.get("resolve", {}).get("error") or "noaddress")
            if dns_task:
                await dns_task
            res.done = res.total
            return
        ip = res.ip

        # 2. Netzscan: erst prüfen, ob überhaupt etwas antwortet
        if t.from_network and o["only_alive"] and not await self._alive(ip):
            res.status = NO_ANSWER
            res.done = res.total
            if dns_task:
                await dns_task
            return

        tasks = []
        if self._on("ping"):
            tasks.append(self._step(res, "ping", self._ping(ip)))
        if self._on("reverse"):
            tasks.append(self._step(res, "reverse", dnscheck.reverse(ip, dns_timeout)))
        if self._on("mac"):
            tasks.append(self._step(res, "mac", self._mac(ip)))
        if self._on("netbios"):
            tasks.append(self._step(res, "netbios", probes.netbios_probe(ip)))
        if self._on("asn"):
            tasks.append(self._step(res, "asn", dnscheck.asn_lookup(ip, dns_timeout)))
        if self._on("ntp"):
            tasks.append(self._step(res, "ntp", probes.ntp_probe(ip)))
        if self._on("dnsserver"):
            tasks.append(self._step(res, "dnsserver", probes.dns_server_probe(ip)))
        if self._on("traceroute"):
            tasks.append(self._route(res, ip))
        if self._on("link"):
            tasks.append(self._link_test(res, ip))
        tasks.append(self._ports_and_services(res, ip))
        if dns_task:
            tasks.append(dns_task)
        await asyncio.gather(*tasks)
        if self._on("mtu"):
            await self._step(res, "mtu", self._mtu(ip, res.raw.get("ping", {})))
        res.step = ""
        res.status = DONE

    async def _alive(self, ip: str) -> bool:
        loop = asyncio.get_running_loop()
        if icmp.available():
            echo = await loop.run_in_executor(None, icmp.echo, ip, 128, 800)
            if echo.status == icmp.OK:
                return True
        checks = await asyncio.gather(*(self._tcp(ip, p, 0.8) for p in DISCOVERY_PORTS))
        return any(state in ("open", "closed") for state, _ in checks)

    # -------------------------------------------------------------- Ping, MTU, MAC
    async def _ping(self, ip: str) -> dict:
        if not icmp.available():
            return {"unavailable": True}
        loop = asyncio.get_running_loop()
        o = self.options
        timeout = int(o["ping_timeout_ms"])
        interval = o["ping_interval_ms"] / 1000
        warmup = int(o.get("ping_warmup", 0))
        # Aufwärm-Pings: ARP-Auflösung und erste Routing-Entscheidung passieren hier, nicht in der Statistik.
        for _ in range(warmup):
            await loop.run_in_executor(None, icmp.echo, ip, 128, timeout)
            await asyncio.sleep(min(0.2, interval))
        echos = []
        for i in range(int(o["ping_count"])):
            echos.append(await loop.run_in_executor(None, icmp.echo, ip, 128, timeout))
            if i < o["ping_count"] - 1:
                await asyncio.sleep(interval)
        stats = ping_stats(echos)
        stats["warmup"] = warmup
        stats["timeout_ms"] = timeout
        return stats

    # -------------------------------------------------------------- Leitungstest (Gegenstelle)
    async def _link_test(self, res: TargetResult, ip: str) -> None:
        """Vermisst die Leitung zu einer Gegenstelle (linkagent). Blockierende Socket-Arbeit im Executor."""
        from . import linkagent
        o = self.options
        loop = asyncio.get_running_loop()
        out: dict = {"server_ip": ip, "server_port": int(o["link_port"])}
        res.raw["link"] = out
        token = str(o.get("link_token", "")).strip()
        if not token:
            out["error"] = "no_token"
            res.done += 1
            self.on_update(res)
            return
        client = linkagent.LinkClient(ip, int(o["link_port"]), token)
        res.step = "link"
        self.on_update(res)
        try:
            out["server"] = await loop.run_in_executor(None, client.handshake)
        except Exception as exc:  # noqa: BLE001 - Verbindungs-/Auth-Fehler als Ergebnis zeigen
            out["error"] = f"{type(exc).__name__}: {exc}"
            res.done += 1
            self.on_update(res)
            return

        seconds = int(o["link_seconds"])
        conns = int(o["link_connections"])

        async def phase(name: str, fn) -> object:
            res.step = "link_" + name
            self.on_update(res)
            try:
                return await loop.run_in_executor(None, fn)
            except Exception as exc:  # noqa: BLE001
                out.setdefault("errors", {})[name] = f"{type(exc).__name__}: {exc}"
                return None

        if o.get("link_latency", True):
            r = await phase("latency", lambda: client.latency(count=max(10, min(100, seconds * 5)), interval=0.05))
            if r:
                out["latency"] = r
        if o.get("link_download", True):
            r = await phase("download", lambda: client.throughput(seconds, True, False))
            if r:
                out.update(r)
        if o.get("link_upload", True):
            r = await phase("upload", lambda: client.throughput(seconds, False, True))
            if r:
                out.update(r)
        if o.get("link_load", True):
            r = await phase("load", lambda: client.loadtest(conns, seconds))
            if r:
                out["load"] = r
        if o.get("link_portscan", True):
            ports = parse_scan_ports(str(o.get("link_scan_ports", "")))
            r = await phase("portscan", lambda: client.path_scan(ports))
            if r:
                out["portscan"] = r
        res.step = ""
        res.done += 1
        self.on_update(res)

    async def _mtu(self, ip: str, ping: dict) -> dict:
        if not icmp.available() or not ping.get("received") or ":" in ip:
            return {"skipped": True}
        loop = asyncio.get_running_loop()

        async def fits(size: int) -> str:
            e = await loop.run_in_executor(None, icmp.echo, ip, 128, 1500, size, True)
            return e.status
        if await fits(1472) == icmp.OK:
            return {"mtu": 1500, "payload": 1472}
        low, high, blocked = 548, 1471, False
        if await fits(low) != icmp.OK:
            return {"mtu": None}
        while low < high:
            mid = (low + high + 1) // 2
            status = await fits(mid)
            if status == icmp.OK:
                low = mid
            else:
                blocked = blocked or status == icmp.TIMEOUT
                high = mid - 1
        return {"mtu": low + 28, "payload": low, "silent_drop": blocked}

    async def _mac(self, ip: str) -> dict:
        addr = ipaddress.ip_address(ip)
        if addr.version != 4 or not (addr.is_private or addr.is_link_local):
            return {"skipped": True}
        loop = asyncio.get_running_loop()
        mac = await loop.run_in_executor(None, mac_of, ip)
        vendor = await loop.run_in_executor(None, self.vendors.lookup, mac) if mac else ""
        return {"mac": mac, "vendor": vendor}

    # -------------------------------------------------------------- Route
    async def _route(self, res: TargetResult, ip: str) -> None:
        await self._step(res, "traceroute", self._traceroute(ip))
        if self._on("hops"):
            await self._step(res, "hops", self._hop_analysis(res.raw.get("traceroute", {})))

    async def _traceroute(self, ip: str) -> dict:
        if not icmp.available() or ":" in ip:
            return {"unavailable": True}
        loop = asyncio.get_running_loop()
        max_hops = int(self.options["max_hops"])

        async def hop(ttl: int) -> dict:
            echos = []
            for _ in range(3):
                echos.append(await loop.run_in_executor(None, icmp.echo, ip, ttl, 1500))
            responder = next((e.from_ip for e in echos if e.from_ip), "")
            rtts = [e.rtt_ms for e in echos if e.rtt_ms is not None and e.status in (icmp.OK, icmp.TTL_EXPIRED)]
            return {"ttl": ttl, "ip": responder, "rtts": rtts, "reached": any(e.status == icmp.OK for e in echos),
                    "statuses": [e.status for e in echos]}

        # Alle Sprungweiten gleichzeitig senden (wie pathping, aber parallel), danach am Ziel abschneiden
        hops = await asyncio.gather(*(hop(ttl) for ttl in range(1, max_hops + 1)))
        result = []
        for h in hops:
            result.append(h)
            if h["reached"] or h["ip"] == ip:
                break
        reached = bool(result) and (result[-1]["reached"] or result[-1]["ip"] == ip)
        return {"hops": result, "reached": reached, "max_hops": max_hops}

    async def _hop_analysis(self, route: dict) -> dict:
        hops = [h for h in route.get("hops", []) if h.get("ip")]
        loop = asyncio.get_running_loop()
        count = int(self.options["hop_pings"])

        async def analyse(h: dict) -> tuple[str, dict]:
            hip = h["ip"]
            echos = []
            for _ in range(count):
                echos.append(await loop.run_in_executor(None, icmp.echo, hip, 128, 1000))
            rev, asn = await asyncio.gather(dnscheck.reverse(hip, 2.5), dnscheck.asn_lookup(hip, 2.5))
            return hip, {"ptr": rev.get("ptr", []), "asn": asn, "class": classify(hip), "ping": ping_stats(echos)}

        unique = {h["ip"]: h for h in hops}
        pairs = await asyncio.gather(*(analyse(h) for h in unique.values()))
        return dict(pairs)

    # -------------------------------------------------------------- Ports und Dienste
    async def _ports_and_services(self, res: TargetResult, ip: str) -> None:
        timeout = self.options["port_timeout_ms"] / 1000
        open_ports: list[int] = []
        if self._on("tcp"):
            async def scan() -> dict:
                ports = self.ports
                states = await asyncio.gather(*(self._tcp(ip, p, timeout) for p in ports))
                rows = {p: {"state": s, "ms": round(ms, 1) if ms else None} for p, (s, ms) in zip(ports, states)}
                closed = sum(1 for r in rows.values() if r["state"] == "closed")
                filtered = sum(1 for r in rows.values() if r["state"] == "filtered")
                return {"scanned": len(ports), "open": {p: r for p, r in rows.items() if r["state"] == "open"},
                        "closed": closed, "filtered": filtered, "profile": self.options["port_profile"]}
            await self._step(res, "tcp", scan())
            open_ports = sorted(res.raw.get("tcp", {}).get("open", {}))

        async def is_open(port: int) -> bool:
            if self._on("tcp"):
                return port in open_ports
            state, _ = await self._tcp(ip, port, timeout)
            return state == "open"

        host = res.target.name or ip
        jobs = []
        if self._on("banner"):
            async def banners() -> dict:
                ports = [p for p in open_ports if p in BANNER_PORTS or p not in WEB_PORTS | dict.fromkeys(TLS_PORTS)]
                texts = await asyncio.gather(*(probes.banner(ip, p) for p in ports[:64]))
                return {p: b for p, b in zip(ports, texts) if b}
            jobs.append(self._step(res, "banner", banners()))
        from .portinfo import PORT_META
        unknown_open = [p for p in open_ports if f"{p}/tcp" not in PORT_META]
        if self._on("http"):
            async def http() -> dict:
                # bekannte Web-Ports + unbekannte offene Ports (oft Weboberflächen auf ungewöhnlichen Ports)
                candidates = ([p for p in open_ports if p in WEB_PORTS] + unknown_open) if open_ports else [80, 443]
                if not self._on("tcp"):
                    candidates = [p for p in candidates if await is_open(p)]
                pages = await asyncio.gather(*(probes.http_probe(ip, p, host, WEB_PORTS.get(p, False))
                                              for p in candidates[:24]))
                return {p: page for p, page in zip(candidates, pages)}
            jobs.append(self._step(res, "http", http()))
        if self._on("tls"):
            async def tls() -> dict:
                candidates = ([p for p in open_ports if p in TLS_PORTS] + unknown_open) if open_ports else [443]
                if not self._on("tcp"):
                    candidates = [p for p in candidates if await is_open(p)]
                sni = res.target.name or None
                found = await asyncio.gather(*(probes.tls_probe(ip, p, sni) for p in candidates[:16]))
                return {p: f for p, f in zip(candidates, found)}
            jobs.append(self._step(res, "tls", tls()))
        if self._on("smb"):
            async def smb() -> dict:
                return await probes.smb_probe(ip) if await is_open(445) else {"closed": True}
            jobs.append(self._step(res, "smb", smb()))
        if self._on("rdp"):
            async def rdp() -> dict:
                return await probes.rdp_probe(ip) if await is_open(3389) else {"closed": True}
            jobs.append(self._step(res, "rdp", rdp()))
        await asyncio.gather(*jobs)
