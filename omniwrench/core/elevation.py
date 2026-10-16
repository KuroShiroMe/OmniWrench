"""UAC-Erhöhung unter Windows (ShellExecuteExW mit Verb "runas").

Direkt über die Windows-API statt über "Start-Process -Verb RunAs":
* die UAC-Abfrage gehört zum Hauptfenster (erscheint im Vordergrund statt nur in der Taskleiste),
* "Nein" in der UAC-Abfrage ist eindeutig erkennbar (ERROR_CANCELLED),
* funktioniert identisch aus dem Quellcode und aus der EXE.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

ERROR_CANCELLED = 1223  # Benutzer hat die UAC-Abfrage abgelehnt

_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SEE_MASK_NOASYNC = 0x00000100
_SEE_MASK_FLAG_NO_UI = 0x00000400
_SW_HIDE = 0
_WAIT_OBJECT_0 = 0

_owner_hwnd = 0


class ElevationCancelled(Exception):
    """Die UAC-Abfrage wurde abgelehnt."""


def set_owner_window(hwnd: int) -> None:
    """Fenster, dem die UAC-Abfrage zugeordnet wird (Hauptfenster; wird von der Oberfläche gesetzt)."""
    global _owner_hwnd
    _owner_hwnd = int(hwnd or 0)


def is_admin() -> bool:
    """True, wenn der Prozess bereits Administratorrechte hat (dann entfällt die UAC-Abfrage)."""
    if os.name != "nt":
        return hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def needs_uac() -> bool:
    """True, wenn für Administratorrechte eine UAC-Abfrage nötig ist (nur Windows ohne Adminrechte)."""
    return os.name == "nt" and not is_admin()


if os.name == "nt":
    class _ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfo)]
    _shell32.ShellExecuteExW.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


class ElevatedProcess:
    """Handle eines erhöhten Prozesses; poll() wie bei subprocess.Popen."""

    def __init__(self, handle) -> None:
        self._handle = handle
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        if not self._handle:
            self.returncode = 0
            return 0
        if _kernel32.WaitForSingleObject(self._handle, 0) != _WAIT_OBJECT_0:
            return None
        code = wintypes.DWORD()
        _kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code))
        _kernel32.CloseHandle(self._handle)
        self._handle = None
        # Exitcodes sind DWORD; negative PowerShell-Exitcodes wieder vorzeichenbehaftet machen
        value = code.value
        self.returncode = value - (1 << 32) if value >= (1 << 31) else value
        return self.returncode


def start_elevated(executable: str, parameters: str, hidden: bool = True) -> ElevatedProcess:
    """Startet ein Programm mit Administratorrechten (UAC-Abfrage).

    Löst ElevationCancelled aus, wenn die Abfrage abgelehnt wird, sonst OSError.
    """
    if os.name != "nt":
        raise OSError("UAC elevation is only available on Windows")
    info = _ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS | _SEE_MASK_NOASYNC | _SEE_MASK_FLAG_NO_UI
    info.hwnd = _owner_hwnd or None
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = parameters
    info.nShow = _SW_HIDE if hidden else 1
    if not _shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == ERROR_CANCELLED:
            raise ElevationCancelled()
        raise ctypes.WinError(error)
    return ElevatedProcess(info.hProcess)
