"""Informationen über das Betriebssystem."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def is_windows_server() -> bool:
    """True unter Windows Server (auch Server Core). OmniWrench ist für Windows-Clients gedacht."""
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            value, _ = winreg.QueryValueEx(key, "InstallationType")
        return str(value).lower().startswith("server")
    except OSError:
        return False
