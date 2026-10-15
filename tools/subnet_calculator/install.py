"""Installationsroutine des Subnetzrechners.

Alle Funktionen sind optional. Deklarative Voraussetzungen (tool.json -> requirements)
werden bereits VOR install() vom Hauptprogramm installiert.
"""


def check(ctx):
    """Liefert eine Liste fehlender Voraussetzungen (leer = alles OK)."""
    return []


def install(ctx):
    ctx.report(ctx.tr("install.nothing", "No additional components required."))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Update from {old} - no migration required.", old=old_version))


def uninstall(ctx):
    ctx.report(ctx.tr("install.uninstall", "Nothing to remove."))
