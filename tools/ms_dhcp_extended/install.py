"""Installationsroutine von MS DHCP Extended Management.

Die RSAT-Funktion aus tool.json -> requirements.windows_capabilities installiert das Hauptprogramm
selbst (mit UAC-Abfrage; nötig für netsh dhcp). Hier wird nur geprüft, ob die DHCP-Schnittstelle von
Windows (dhcpsapi.dll) geladen werden kann - ohne PowerShell.
"""


import ctypes
import os


def check(ctx):
    if os.name != "nt":
        return [ctx.tr("install.missing")]
    try:
        ctypes.WinDLL("dhcpsapi.dll")
    except OSError:
        return [ctx.tr("install.missing")]
    return []


def install(ctx):
    ctx.report(ctx.tr("install.checking"))
    ctx.report(ctx.tr("install.not_found") if check(ctx) else ctx.tr("install.found"))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", old=old_version))


def uninstall(ctx):
    # RSAT bewusst NICHT entfernen - andere Tools/Programme nutzen es evtl. ebenfalls.
    ctx.report(ctx.tr("install.keep_rsat"))
