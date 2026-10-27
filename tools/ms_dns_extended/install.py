"""Installationsroutine von MS DNS Extended Management.

pywin32 (WMI über DCOM) und dnspython (Abfragen an Namensserver) installiert das Hauptprogramm aus
tool.json -> requirements in den privaten _lib-Ordner. Kein RSAT und kein PowerShell nötig.
"""

from __future__ import annotations

import importlib
import os
import sys


def check(ctx):
    if os.name != "nt":
        return [ctx.tr("install.windows_only")]
    lib = ctx.tool_dir / "_lib"  # pip installiert Tool-Pakete in den privaten _lib-Ordner
    # pip --target wertet die .pth-Datei von pywin32 nicht aus -> Pfade selbst setzen (wie wmidns.load)
    for p in (lib, lib / "win32", lib / "win32" / "lib", lib / "pywin32_system32"):
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    dll_dir = lib / "pywin32_system32"
    if dll_dir.is_dir():
        try:
            os.add_dll_directory(str(dll_dir))
        except (OSError, AttributeError):
            pass
    importlib.invalidate_caches()
    missing = []
    try:
        import dns.resolver  # noqa: F401
    except ImportError:
        missing.append("dnspython")
    try:
        import pythoncom  # noqa: F401
        import win32com.client  # noqa: F401
    except (ImportError, OSError):
        missing.append("pywin32")
    return missing


def install(ctx):
    ctx.report(ctx.tr("install.checking"))
    missing = check(ctx)
    ctx.report(ctx.tr("install.missing", items=", ".join(missing)) if missing else ctx.tr("install.ready"))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", old=old_version))


def uninstall(ctx):
    ctx.report(ctx.tr("install.removed"))
