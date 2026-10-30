"""Hilfen für die KI-Tests: KI-Tools in das Temp-Home legen und im Hauptfenster öffnen."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def install(manager, *names: str) -> dict[str, str]:
    """tools/<name> nach TOOLS_DIR kopieren; gibt {name: Tool-ID} zurück."""
    from omniwrench.core import paths
    from omniwrench.core.manifest import ToolManifest
    ids = {}
    for name in names:
        source = ROOT / "tools" / name
        manifest = ToolManifest.load(source)
        target = paths.TOOLS_DIR / manifest.id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.png"))
        ids[name] = manifest.id
    manager.refresh()
    return ids


def open_tool(win, tool_id: str, pump):
    """Tool öffnen (oder das offene nehmen) und die Instanz zurückgeben."""
    win.open_tool(tool_id)
    pump(0.4)
    return next(o for o in win.open_tools.values() if o.tool_id == tool_id).instance


def close_tool(win, tool_id: str, pump) -> None:
    for name, o in list(win.open_tools.items()):
        if o.tool_id == tool_id:
            win.close_tool(name)
    pump(0.2)
