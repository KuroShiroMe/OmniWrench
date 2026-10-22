"""Informationen über das Betriebssystem."""

from __future__ import annotations

import os
import sys
from functools import lru_cache

# Kennung des Betriebssystems wie in tool.json "platforms" ("windows", "linux", "macos")
PLATFORM = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
PLATFORM_NAMES = {"windows": "Windows", "linux": "Linux", "macos": "macOS"}


def platform_name(platform_id: str) -> str:
    return PLATFORM_NAMES.get(platform_id.lower(), platform_id)


def supports_platform(platforms: list[str]) -> bool:
    """True, wenn ein Tool mit dieser "platforms"-Liste auf dem aktuellen Betriebssystem läuft."""
    return PLATFORM in [p.lower() for p in platforms]


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
