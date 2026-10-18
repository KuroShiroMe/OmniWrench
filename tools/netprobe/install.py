"""Installationsroutine von NetProbe.

dnspython (DNS-Prüfungen) installiert das Hauptprogramm aus tool.json -> requirements.
ICMP, TCP, TLS, SMB usw. nutzen nur die Standardbibliothek und laufen ohne Administratorrechte.
"""

from __future__ import annotations

import importlib
import sys


def check(ctx):
    lib = str(ctx.tool_dir / "_lib")  # pip installiert Tool-Pakete in den privaten _lib-Ordner
    if lib not in sys.path:
        sys.path.insert(0, lib)
    importlib.invalidate_caches()
    try:
        import dns.asyncresolver  # noqa: F401
    except ImportError:
        return ["dnspython"]
    return []


def install(ctx):
    ctx.report(ctx.tr("install.ready", "NetProbe installed."))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))


def uninstall(ctx):
    ctx.report(ctx.tr("install.removed", "NetProbe removed."))
