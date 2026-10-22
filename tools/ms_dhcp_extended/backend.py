"""Zugriffsschicht ohne PowerShell: DHCP-API (dhcpapi.py) und netsh dhcp, direkt aus Python.

Gleiche Schnittstelle wie früher der PowerShell-Host: call(cmd, args, on_progress) mit den Befehlen hello,
connect, set_cred, disconnect, cim, cim_many, dhcp_in_dc, resolve, fo_api, netsh. "cim" nimmt weiter
Cmdlet-Namen entgegen (dhcpapi.CMDLETS bildet sie auf API-Aufrufe ab), damit service.py und das
Test-Backend unverändert bleiben. Fehler kommen als HostError mit "@RPC:…"- bzw. "@ERR:…"-Text, den
DhcpService.host_text übersetzt.

Alle Methoden sind threadsicher; cim_many arbeitet mit einem Thread-Pool (ctypes gibt das GIL während der
RPC-Aufrufe frei). kill() bricht laufende Sammelabfragen ab.
"""

from __future__ import annotations

import ctypes
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from . import dhcpapi as api


class HostError(Exception):
    """Fehlermeldung des Zugriffs (Text ggf. mit @RPC:/@ERR:-Präfix)."""


class HostDied(HostError):
    """Zugriff abgebrochen."""


def _err(e: Exception) -> HostError:
    if isinstance(e, HostError):
        return e
    if isinstance(e, api.RpcError):
        return HostError(str(e))
    if isinstance(e, (ValueError, KeyError, TypeError)):
        return HostError(f"@ERR:bad_value:{e}")
    return HostError(str(e) or type(e).__name__)


class ApiBackend:
    def __init__(self):
        self._lock = threading.Lock()
        self._apis: dict[str, api.DhcpApi] = {}
        self._idents: dict[str, api.Identity] = {}     # Server -> Anmeldung ("*" = Primärserver)
        self._cancel = threading.Event()

    # --- Verwaltung -----------------------------------------------------------------------------------
    def close(self) -> None:
        self._cancel.set()
        with self._lock:
            for i in self._idents.values():
                i.close()
            self._idents.clear()
            self._apis.clear()

    def kill(self) -> None:
        self._cancel.set()

    def _ident(self, server: str | None) -> api.Identity | None:
        with self._lock:
            return self._idents.get(server or "") or self._idents.get("*")

    def _api(self, server: str | None) -> api.DhcpApi:
        if not server:
            raise HostError("@ERR:not_connected:–")
        with self._lock:
            a = self._apis.get(server.lower())
        if a is None:
            raise HostError(f"@ERR:not_connected:{server}")
        return a

    def _set_ident(self, key: str, user: str, password: str) -> None:
        with self._lock:
            old = self._idents.pop(key, None)
            if old:
                old.close()
            if user:
                self._idents[key] = api.Identity(user, password)

    # --- Befehle --------------------------------------------------------------------------------------
    def call(self, cmd: str, args: dict | None = None, on_progress=None):
        args = args or {}
        fn = getattr(self, "_cmd_" + str(cmd), None)
        if fn is None:
            raise HostError(f"@ERR:bad_cmd:{cmd}")
        try:
            return fn(args, on_progress)
        except Exception as e:  # noqa: BLE001 - alles als HostError an service.py
            raise _err(e) from None

    def _cmd_hello(self, a, prog):
        return {"dhcp": api.available(), "user": f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}",
                "computer": os.environ.get("COMPUTERNAME", "")}

    def _cmd_connect(self, a, prog):
        server = str(a["server"]).strip()
        if a.get("reuse"):
            ident = self._ident(server)
        else:
            key = "*" if a.get("primary") else server
            self._set_ident(key, str(a.get("user") or ""), str(a.get("password") or ""))
            ident = self._ident(server) if not a.get("primary") else self._ident("*")
        if prog:
            prog({"step": "try", "proto": "RPC"})
        dhcp = api.DhcpApi(server, ident)
        try:
            dhcp.version()
        except Exception as e:
            if prog:
                prog({"step": "fail", "proto": "RPC", "error": str(e)})
            raise
        with self._lock:
            self._apis[server.lower()] = dhcp
        return {"protocol": "RPC"}

    def _cmd_set_cred(self, a, prog):
        server = str(a["server"])
        self._set_ident(server, str(a.get("user") or ""), str(a.get("password") or ""))
        with self._lock:
            d = self._apis.get(server.lower())
            if d is not None:
                d.ident = self._idents.get(server) or self._idents.get("*")
        return True

    def _cmd_disconnect(self, a, prog):
        server = a.get("server")
        with self._lock:
            if server:
                self._apis.pop(str(server).lower(), None)
            else:
                self._apis.clear()
                for i in self._idents.values():
                    i.close()
                self._idents.clear()
        return True

    def _run_cmdlet(self, name: str, server: str | None, params: dict) -> list[dict]:
        f = api.CMDLETS.get(name)
        if f is None:
            raise HostError(f"@ERR:bad_cmdlet:{name}")
        res = f(self._api(server), dict(params or {}))
        return list(res) if isinstance(res, list) else []

    def _cmd_cim(self, a, prog):
        return {"items": self._run_cmdlet(str(a["name"]), a.get("server"), a.get("params") or {})}

    def _cmd_cim_many(self, a, prog):
        calls = list(a.get("calls") or [])
        for c in calls:
            if not str(c.get("name", "")).startswith("Get-"):
                raise HostError(f"@ERR:bad_cmdlet:{c.get('name')}")
        threads = max(1, min(16, int(a.get("threads") or 8)))
        self._cancel.clear()

        def one(c):
            if self._cancel.is_set():
                raise HostDied("cancelled")
            return self._run_cmdlet(str(c["name"]), c.get("server"), c.get("params") or {})
        with ThreadPoolExecutor(max_workers=threads, thread_name_prefix="dhcp") as ex:
            futs = {ex.submit(one, c): c for c in calls}
            pending = set(futs)
            while pending:
                done, pending = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                if self._cancel.is_set():
                    for f in pending:
                        f.cancel()
                    raise HostDied("cancelled")
                for f in done:
                    key = futs[f]["key"]
                    try:
                        msg = {"key": key, "items": f.result()}
                    except Exception as e:  # noqa: BLE001
                        msg = {"key": key, "error": str(_err(e))}
                    if prog:
                        prog(msg)
        return {"count": len(calls)}

    def _cmd_dhcp_in_dc(self, a, prog):
        return {"items": api.dhcp_in_dc()}

    def _cmd_resolve(self, a, prog):
        n = str(a["name"]).strip()
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", n):
            return n
        try:
            infos = socket.getaddrinfo(n, None, socket.AF_INET)
        except OSError:
            raise HostError(f"@ERR:resolve:{n}") from None
        if not infos:
            raise HostError(f"@ERR:resolve:{n}")
        return infos[0][4][0]

    def _cmd_fo_api(self, a, prog):
        server = str(a["server"])
        dhcp = api.DhcpApi(server, self._ident(server))       # Partner auch ohne vorheriges connect erreichbar
        return dhcp.fo_call(str(a.get("op")), a.get("rel"), a.get("name"), int(a.get("flags") or 0))

    def _cmd_access(self, a, prog):
        server = str(a["server"])
        return api.DhcpApi(server, self._ident(server)).access()

    def _cmd_netsh(self, a, prog):
        server = str(a["server"])
        lines = [str(x) for x in a.get("lines") or []]
        return {"items": run_netsh(server, lines, self._ident(server), int(a.get("timeout") or 0), prog)}


# --- netsh dhcp ------------------------------------------------------------------------------------

def _oem_encoding() -> str:
    try:
        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except (AttributeError, OSError):
        return "cp850"


def _decode(b: bytes) -> str:
    if not b:
        return ""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode(_oem_encoding(), errors="replace")


def _segment(text: str, i: int, cmd: str) -> dict | None:
    m = re.search(rf"##BEGIN{i}##\r?\n(?P<o>[\s\S]*?)##RC{i}=(?P<c>-?\d+)", text)
    if not m:
        return None
    return {"cmd": cmd, "code": int(m.group("c")), "out": [x for x in re.split(r"\r?\n", m.group("o")) if x.strip()]}


def _read(path: str, complete: bool) -> str:
    try:
        with open(path, "rb") as f:
            b = f.read()
    except OSError:
        return ""
    if not complete:
        n = b.rfind(b"\n")
        if n < 0:
            return ""
        b = b[:n + 1]
    return _decode(b)


class _STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_uint32), ("lpReserved", ctypes.c_wchar_p), ("lpDesktop", ctypes.c_wchar_p),
                ("lpTitle", ctypes.c_wchar_p), ("dwX", ctypes.c_uint32), ("dwY", ctypes.c_uint32),
                ("dwXSize", ctypes.c_uint32), ("dwYSize", ctypes.c_uint32), ("dwXCountChars", ctypes.c_uint32),
                ("dwYCountChars", ctypes.c_uint32), ("dwFillAttribute", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("wShowWindow", ctypes.c_uint16), ("cbReserved2", ctypes.c_uint16), ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", ctypes.c_void_p), ("hStdOutput", ctypes.c_void_p), ("hStdError", ctypes.c_void_p)]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", ctypes.c_void_p), ("hThread", ctypes.c_void_p), ("dwProcessId", ctypes.c_uint32),
                ("dwThreadId", ctypes.c_uint32)]


class _Proc:
    """Unsichtbarer Prozess; mit Anmeldedaten wie "runas /netonly" (CreateProcessWithLogonW, LOGON_NETCREDENTIALS_ONLY)."""

    def __init__(self, cmdline: str, ident: api.Identity | None):
        self._popen = None
        self._h = None
        sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
        if ident is None or ident.empty:
            self._popen = subprocess.Popen(cmdline, cwd=sysdir, creationflags=0x08000000,     # CREATE_NO_WINDOW
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        user, domain, pw = ident.parts()
        si = _STARTUPINFO()
        si.cb = ctypes.sizeof(si)
        si.dwFlags = 1          # STARTF_USESHOWWINDOW
        si.wShowWindow = 0      # SW_HIDE
        pi = _PROCESS_INFORMATION()
        buf = ctypes.create_unicode_buffer(cmdline)
        adv = ctypes.WinDLL("advapi32", use_last_error=True)
        ok = adv.CreateProcessWithLogonW(ctypes.c_wchar_p(user), ctypes.c_wchar_p(domain), ctypes.c_wchar_p(pw), 2, None,
                                         buf, 0x10, None, ctypes.c_wchar_p(sysdir), ctypes.byref(si), ctypes.byref(pi))
        if not ok:
            err = ctypes.get_last_error()
            raise HostError(f"@RPC:start_logon::{err}:{ctypes.FormatError(err).strip()}")
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(pi.hThread))
        self._h = pi.hProcess

    def running(self, wait_ms: int) -> bool:
        if self._popen is not None:
            try:
                self._popen.wait(wait_ms / 1000)
                return False
            except subprocess.TimeoutExpired:
                return True
        return ctypes.windll.kernel32.WaitForSingleObject(ctypes.c_void_p(self._h), wait_ms) == 0x102

    def kill(self) -> None:
        if self._popen is not None:
            self._popen.kill()
        elif self._h:
            ctypes.windll.kernel32.TerminateProcess(ctypes.c_void_p(self._h), 1)

    def close(self) -> None:
        if self._h:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self._h))
            self._h = None


def run_netsh(server: str, lines: list[str], ident: api.Identity | None, timeout: int = 0, prog=None) -> list[dict]:
    """netsh-dhcp-Befehle gegen einen Server: eine unsichtbare Stapeldatei, ein netsh-Aufruf pro Zeile.
    Jeder fertige Befehl wird sofort als Fortschritt {"i", "n", "result"} gemeldet."""
    if not lines:
        return []
    if timeout <= 0:
        timeout = 120 + 3 * len(lines)
    enc = _oem_encoding()
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    netsh = os.path.join(sysroot, "System32", "netsh.exe")
    tmp = tempfile.gettempdir()
    tag = uuid.uuid4().hex
    bat = os.path.join(tmp, f"owdhcp_{tag}.cmd")
    out = os.path.join(tmp, f"owdhcp_{tag}.txt")
    rows = ["@echo off"]
    for i, line in enumerate(lines):
        rows.append(f'echo ##BEGIN{i}##>>"{out}"')
        rows.append(f'"{netsh}" dhcp server \\\\{server} {line.replace("%", "%%")} >>"{out}" 2>&1')
        rows.append(f'echo ##RC{i}=%errorlevel%##>>"{out}"')
    with open(bat, "w", encoding=enc, errors="replace", newline="\r\n") as f:
        f.write("\n".join(rows) + "\n")
    results: list[dict] = []
    nxt = 0

    def emit(seg):
        results.append(seg)
        if prog:
            prog({"i": len(results) - 1, "n": len(lines), "result": seg})
    try:
        proc = _Proc(f'"{os.path.join(sysroot, "System32", "cmd.exe")}" /d /c "{bat}"', ident)
        try:
            started = time.monotonic()
            while proc.running(300):
                if time.monotonic() - started > timeout:
                    proc.kill()
                    raise HostError(f"@ERR:netsh_timeout:{server}|{timeout}")
                live = _read(out, False)
                while nxt < len(lines):
                    seg = _segment(live, nxt, lines[nxt])
                    if not seg:
                        break
                    emit(seg)
                    nxt += 1
        finally:
            proc.close()
        txt = _read(out, True)
    finally:
        for p in (bat, out):
            try:
                os.remove(p)
            except OSError:
                pass
    for k in range(nxt, len(lines)):
        emit(_segment(txt, k, lines[k]) or {"cmd": lines[k], "code": -1, "out": []})
    return results
