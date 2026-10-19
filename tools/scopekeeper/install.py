"""Installationsroutine von ScopeKeeper.

Die RSAT-Funktion aus tool.json -> requirements.windows_capabilities installiert das Hauptprogramm
selbst (mit UAC-Abfrage). Hier wird nur geprüft, ob das PowerShell-Modul DhcpServer verfügbar ist.
"""


def check(ctx):
    res = ctx.run_powershell("if (Get-Module -ListAvailable -Name DhcpServer) { 'ok' } else { 'missing' }")
    if res.stdout.strip() != "ok":
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
