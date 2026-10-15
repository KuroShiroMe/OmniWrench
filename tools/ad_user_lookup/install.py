"""Installationsroutine der AD Benutzerabfrage.

Die RSAT-Funktion aus tool.json -> requirements.windows_capabilities installiert das
Hauptprogramm selbst (mit UAC-Abfrage). Hier wird nur geprüft, ob das Modul verfügbar ist.
"""


def check(ctx):
    res = ctx.run_powershell("if (Get-Module -ListAvailable -Name ActiveDirectory) { 'ok' } else { 'missing' }")
    if res.stdout.strip() != "ok":
        return [ctx.tr("install.missing")]
    return []


def install(ctx):
    ctx.report(ctx.tr("install.checking"))
    ctx.report(ctx.tr("install.not_found") if check(ctx) else ctx.tr("install.found"))


def uninstall(ctx):
    # RSAT bewusst NICHT entfernen - andere Tools/Programme nutzen es evtl. ebenfalls.
    ctx.report(ctx.tr("install.keep_rsat"))
