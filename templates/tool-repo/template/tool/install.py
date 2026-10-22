"""Installationsroutine. Alle Funktionen sind optional.

Voraussetzungen aus tool.json (requirements) installiert OmniWrench bereits VOR install().
"""


def check(ctx):
    """Liefert eine Liste fehlender Voraussetzungen ([] = alles vorhanden, keine UAC-Abfrage)."""
    return []


def install(ctx):
    ctx.report(ctx.tr("install.ready", "Installed."))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Updated from {old}.", old=old_version))


def uninstall(ctx):
    pass
