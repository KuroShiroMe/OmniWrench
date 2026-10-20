"""NetProbe Leitungstest – eigenständiges, plattformübergreifendes Mini-Tool (Server + Client).

Diese Datei hat KEINE Abhängigkeiten außer der Python-Standardbibliothek und läuft unter Windows
und Linux (Python 3.8+). Sie dient zwei Zwecken:

* als **Gegenstellen-Server** auf der entfernten Maschine (``python linkagent.py serve``). NetProbe (oder
  ein zweites linkagent) verbindet sich dann, um die Leitung zu vermessen.
* als **Client-Bibliothek**, die NetProbe importiert (:class:`LinkClient`), um die Messungen auszuführen.

Gemessen werden: echte (anwendungsnahe) Latenz über TCP, Durchsatz je Richtung, ein Lasttest mit mehreren
parallelen Verbindungen und ein Pfad-Portscan (welche Ports lässt die Infrastruktur dazwischen durch).

Sicherheit: Der Server verlangt ein gemeinsames Token. Last entsteht ausschließlich gegenüber einer
Gegenstelle, die dieses Mini-Tool mit demselben Token bewusst gestartet hat – das Tool kann also nicht gegen
beliebige fremde Rechner gerichtet werden. Dauer, Datenmenge, Parallelität und Portanzahl sind begrenzt.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import socket
import struct
import threading
import time

PROTOCOL = 1
DEFAULT_PORT = 47600
MAGIC = b"NPLT"                       # erkennt fremde/zufällige Verbindungen früh
CHUNK = 256 * 1024                    # Sendepuffer für den Durchsatz
MAX_SECONDS = 60                      # Obergrenze je Messrichtung
MAX_PARALLEL = 64                     # Obergrenze Lasttest-Verbindungen
MAX_SCAN_PORTS = 256                  # Obergrenze Pfad-Portscan
IDLE_TIMEOUT = 300                    # Server beendet sich nach so vielen Sekunden ohne Verbindung

# Repräsentative Portauswahl für den Pfad-Portscan (was die Strecke durchlässt).
DEFAULT_SCAN_PORTS = (20, 21, 22, 23, 25, 53, 80, 110, 123, 143, 389, 443, 445, 465, 587, 636, 993, 995,
                      1194, 1433, 1521, 1723, 3128, 3306, 3389, 5060, 5432, 5900, 5985, 5986, 8080, 8443)


# ------------------------------------------------------------ Rahmen (Länge + JSON / Rohdaten)
def _send_json(sock: socket.socket, obj: dict) -> None:
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    sock.sendall(MAGIC + struct.pack("!I", len(data)) + data)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed")
        buf.extend(chunk)
    return bytes(buf)


def _recv_json(sock: socket.socket) -> dict:
    if _recv_exact(sock, len(MAGIC)) != MAGIC:
        raise ConnectionError("bad magic")
    (length,) = struct.unpack("!I", _recv_exact(sock, 4))
    if length > 1 << 20:
        raise ConnectionError("frame too large")
    return json.loads(_recv_exact(sock, length).decode("utf-8"))


def _clamp(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


# ============================================================ SERVER
class LinkServer:
    """Gegenstellen-Server: nimmt authentifizierte Verbindungen an und beantwortet die Messungen."""

    def __init__(self, token: str, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 idle_timeout: float = IDLE_TIMEOUT, log=None):
        self.token = token
        self.host = host
        self.port = port
        self.idle_timeout = idle_timeout
        self.log = log or (lambda msg: None)
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_activity = time.time()

    # -------------------------------------------------- Lebenszyklus
    def start(self) -> int:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(MAX_PARALLEL + 8)
        srv.settimeout(1.0)
        self._sock = srv
        self.port = srv.getsockname()[1]
        self._stop.clear()
        self._last_activity = time.time()
        self._thread = threading.Thread(target=self._accept_loop, name="linkagent-srv", daemon=True)
        self._thread.start()
        self.log("serve: %s:%d" % (self.host, self.port))
        return self.port

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._sock = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def serve_forever(self) -> None:
        """Blockierend (für die Standalone-CLI)."""
        self.start()
        try:
            while self.running and not self._stop.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.log("stop (keyboard)")
        finally:
            self.stop()

    # -------------------------------------------------- Annahme
    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                if self.idle_timeout and time.time() - self._last_activity > self.idle_timeout:
                    self.log("idle timeout – beende")
                    self._stop.set()
                continue
            except OSError:
                break
            self._last_activity = time.time()
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()

    def _handle(self, conn: socket.socket, addr) -> None:
        try:
            conn.settimeout(10.0)
            hello = _recv_json(conn)
            if hello.get("token") != self.token or hello.get("op") != "hello":
                _send_json(conn, {"ok": False, "error": "unauthorized"})
                return
            _send_json(conn, {"ok": True, "server": "netprobe-linkagent", "v": PROTOCOL,
                              "os": platform.platform(terse=True), "host": socket.gethostname(),
                              "caps": ["latency", "throughput", "load", "portscan"]})
            while not self._stop.is_set():
                conn.settimeout(30.0)
                try:
                    msg = _recv_json(conn)
                except (ConnectionError, socket.timeout, OSError):
                    return
                self._last_activity = time.time()
                if not self._dispatch(conn, msg):
                    return
        except (ConnectionError, OSError, ValueError):
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _dispatch(self, conn: socket.socket, msg: dict) -> bool:
        op = msg.get("op")
        if op == "echo":
            _send_json(conn, {"op": "echo", "seq": msg.get("seq"), "ts": msg.get("ts")})
            return True
        if op == "source":                       # Download aus Sicht des Clients: wir senden
            self._source(conn, _clamp(msg.get("seconds"), 1, MAX_SECONDS, 5))
            return False
        if op == "sink":                          # Upload aus Sicht des Clients: wir empfangen
            self._sink(conn, _clamp(msg.get("seconds"), 1, MAX_SECONDS, 5))
            return False
        if op == "listen":
            self._listen(conn, msg.get("ports") or [])
            return False
        _send_json(conn, {"ok": False, "error": "unknown op"})
        return False

    def _source(self, conn: socket.socket, seconds: int) -> None:
        payload = os.urandom(CHUNK)
        conn.settimeout(seconds + 10)
        end = time.monotonic() + seconds
        sent = 0
        try:
            while time.monotonic() < end:
                conn.sendall(payload)
                sent += len(payload)
        except (OSError, ConnectionError):
            pass
        try:
            conn.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    def _sink(self, conn: socket.socket, seconds: int) -> None:
        conn.settimeout(seconds + 10)
        start = time.monotonic()
        received = 0
        try:
            while True:
                data = conn.recv(CHUNK)
                if not data:
                    break
                received += len(data)
                if time.monotonic() - start > seconds + 5:
                    break
        except (OSError, ConnectionError):
            pass
        try:
            _send_json(conn, {"op": "sink", "bytes": received, "seconds": round(time.monotonic() - start, 3)})
        except OSError:
            pass

    def _listen(self, conn: socket.socket, ports) -> None:
        """Bindet eine Portauswahl, damit der Client prüfen kann, was die Strecke durchlässt."""
        wanted = []
        for p in ports[:MAX_SCAN_PORTS]:
            try:
                p = int(p)
            except (TypeError, ValueError):
                continue
            if 1 <= p <= 65535:
                wanted.append(p)
        bound: list[int] = []
        failed: dict[str, str] = {}
        listeners: list[socket.socket] = []
        for p in wanted:
            try:
                ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                ls.bind((self.host, p))
                ls.listen(16)
                listeners.append(ls)
                bound.append(p)
            except OSError as exc:
                failed[str(p)] = exc.strerror or str(exc)
        try:
            _send_json(conn, {"op": "listen", "bound": bound, "failed": failed})
            conn.settimeout(MAX_SECONDS)
            try:
                _recv_json(conn)                  # wartet auf "unlisten" oder Verbindungsende
            except (ConnectionError, socket.timeout, OSError):
                pass
        finally:
            for ls in listeners:
                try:
                    ls.close()
                except OSError:
                    pass


# ============================================================ CLIENT
def _stats(rtts: list[float]) -> dict:
    import statistics
    if not rtts:
        return {}
    diffs = [abs(a - b) for a, b in zip(rtts, rtts[1:])]
    return {"min": round(min(rtts), 3), "max": round(max(rtts), 3),
            "avg": round(statistics.fmean(rtts), 3), "median": round(statistics.median(rtts), 3),
            "stdev": round(statistics.pstdev(rtts), 3) if len(rtts) > 1 else 0.0,
            "jitter": round(statistics.fmean(diffs), 3) if diffs else 0.0}


class LinkClient:
    """Führt die Leitungsmessungen gegen eine Gegenstelle aus (blockierend, mit Threads für die Last)."""

    def __init__(self, host: str, port: int, token: str, timeout: float = 8.0):
        self.host = host
        self.port = port
        self.token = token
        self.timeout = timeout
        self.hello: dict = {}

    def _connect(self) -> socket.socket:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _send_json(sock, {"op": "hello", "token": self.token, "client": "NetProbe", "v": PROTOCOL})
        reply = _recv_json(sock)
        if not reply.get("ok"):
            sock.close()
            raise PermissionError(reply.get("error", "refused"))
        self.hello = reply
        return sock

    def handshake(self) -> dict:
        sock = self._connect()
        sock.close()
        return self.hello

    # -------------------------------------------------- Latenz
    def latency(self, count: int = 20, interval: float = 0.05, progress=None) -> dict:
        sock = self._connect()
        rtts: list[float] = []
        lost = 0
        try:
            for i in range(count):
                t0 = time.perf_counter()
                _send_json(sock, {"op": "echo", "seq": i, "ts": t0})
                try:
                    sock.settimeout(self.timeout)
                    reply = _recv_json(sock)
                    if reply.get("seq") == i:
                        rtts.append((time.perf_counter() - t0) * 1000.0)
                    else:
                        lost += 1
                except (socket.timeout, ConnectionError):
                    lost += 1
                if progress:
                    progress(i + 1, count)
                if i < count - 1:
                    time.sleep(interval)
        finally:
            sock.close()
        out = {"sent": count, "received": len(rtts), "lost": lost,
               "loss_pct": round(100 * lost / count, 1) if count else 0.0, "rtts": [round(r, 3) for r in rtts]}
        out.update(_stats(rtts))
        return out

    # -------------------------------------------------- Durchsatz
    def _download(self, seconds: int) -> dict:
        sock = self._connect()
        received = 0
        try:
            _send_json(sock, {"op": "source", "seconds": seconds})
            sock.settimeout(seconds + 12)
            start = time.monotonic()
            while True:
                data = sock.recv(CHUNK)
                if not data:
                    break
                received += len(data)
            elapsed = time.monotonic() - start
        finally:
            sock.close()
        return {"bytes": received, "seconds": round(elapsed, 3),
                "mbps": round(received * 8 / elapsed / 1e6, 2) if elapsed > 0 else 0.0}

    def _upload(self, seconds: int) -> dict:
        sock = self._connect()
        payload = os.urandom(CHUNK)
        sent = 0
        try:
            _send_json(sock, {"op": "sink", "seconds": seconds})
            sock.settimeout(seconds + 12)
            start = time.monotonic()
            end = start + seconds
            while time.monotonic() < end:
                sock.sendall(payload)
                sent += len(payload)
            sock.shutdown(socket.SHUT_WR)
            elapsed = time.monotonic() - start
            try:
                _recv_json(sock)
            except (ConnectionError, socket.timeout, OSError):
                pass
        finally:
            sock.close()
        return {"bytes": sent, "seconds": round(elapsed, 3),
                "mbps": round(sent * 8 / elapsed / 1e6, 2) if elapsed > 0 else 0.0}

    def throughput(self, seconds: int = 5, download: bool = True, upload: bool = True) -> dict:
        out: dict = {}
        if download:
            out["download"] = self._download(seconds)
        if upload:
            out["upload"] = self._upload(seconds)
        return out

    # -------------------------------------------------- Lasttest (parallele Verbindungen)
    def loadtest(self, connections: int = 8, seconds: int = 5) -> dict:
        from concurrent.futures import ThreadPoolExecutor
        connections = max(1, min(MAX_PARALLEL, int(connections)))
        results: list[dict] = []
        errors = 0

        def worker(_i: int) -> dict:
            t0 = time.perf_counter()
            r = self._download(seconds)
            r["setup_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
            return r

        with ThreadPoolExecutor(max_workers=connections) as pool:
            for fut in [pool.submit(worker, i) for i in range(connections)]:
                try:
                    results.append(fut.result())
                except Exception:  # noqa: BLE001 – eine fehlgeschlagene Verbindung bricht den Lasttest nicht ab
                    errors += 1
        total_mbps = round(sum(r["mbps"] for r in results), 2)
        return {"connections": connections, "ok": len(results), "errors": errors,
                "mbps_total": total_mbps,
                "mbps_per_conn": round(total_mbps / len(results), 2) if results else 0.0}

    # -------------------------------------------------- Pfad-Portscan
    def path_scan(self, ports=DEFAULT_SCAN_PORTS, connect_timeout: float = 2.0) -> dict:
        ports = [int(p) for p in ports][:MAX_SCAN_PORTS]
        ctrl = self._connect()
        try:
            _send_json(ctrl, {"op": "listen", "ports": ports})
            ctrl.settimeout(self.timeout + 5)
            reply = _recv_json(ctrl)
            bound = reply.get("bound", [])
            states = {"open": [], "filtered": [], "closed": []}
            for p in bound:
                states[self._probe_port(p, connect_timeout)].append(p)
            return {"requested": ports, "bound": bound, "bind_failed": reply.get("failed", {}),
                    "open": states["open"], "filtered": states["filtered"], "closed": states["closed"]}
        finally:
            try:
                _send_json(ctrl, {"op": "unlisten"})
            except OSError:
                pass
            ctrl.close()

    def _probe_port(self, port: int, timeout: float) -> str:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((self.host, port))
            return "open"
        except socket.timeout:
            return "filtered"
        except OSError:
            return "closed"
        finally:
            sock.close()


# ============================================================ Standalone-CLI
def new_token() -> str:
    return secrets.token_hex(8)


def _cli(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="linkagent",
        description="NetProbe Leitungstest – Gegenstelle. Starten Sie den Server auf der entfernten Maschine "
                    "und tragen Sie IP, Port und Token in NetProbe ein.")
    sub = parser.add_subparsers(dest="mode")

    srv = sub.add_parser("serve", help="Als Gegenstelle lauschen (Standard)")
    srv.add_argument("--port", type=int, default=DEFAULT_PORT)
    srv.add_argument("--host", default="0.0.0.0", help="Bind-Adresse (Standard: alle Schnittstellen)")
    srv.add_argument("--token", default=os.environ.get("LINKAGENT_TOKEN", ""),
                     help="Gemeinsames Token; ohne Angabe wird eines erzeugt und angezeigt")
    srv.add_argument("--idle-timeout", type=float, default=IDLE_TIMEOUT,
                     help="Beendet den Server nach so vielen Sekunden ohne Verbindung (0 = nie)")

    pr = sub.add_parser("probe", help="Selbst eine Gegenstelle messen (Diagnose)")
    pr.add_argument("host")
    pr.add_argument("--port", type=int, default=DEFAULT_PORT)
    pr.add_argument("--token", required=True)
    pr.add_argument("--seconds", type=int, default=5)

    args = parser.parse_args(argv)
    mode = args.mode or "serve"

    if mode == "serve":
        token = args.token or new_token()
        print("NetProbe Leitungstest – Gegenstelle")
        print("  Port:  %d" % args.port)
        print("  Token: %s" % token)
        print("  (In NetProbe als Ziel die IP dieses Rechners eintragen, Port und Token in den Optionen.)")
        print("  Zum Beenden Strg+C.")
        LinkServer(token, host=args.host, port=args.port, idle_timeout=args.idle_timeout,
                   log=lambda m: print("  [%s] %s" % (time.strftime("%H:%M:%S"), m))).serve_forever()
        return 0

    client = LinkClient(args.host, args.port, args.token)
    print("Handshake:", client.handshake())
    print("Latenz:", client.latency())
    print("Durchsatz:", client.throughput(args.seconds))
    print("Pfad-Portscan:", client.path_scan())
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
