"""Installationsroutine des Icon Store - keine Voraussetzungen, die Symbole liefert OmniWrench mit."""


def check(ctx):
    return []


def install(ctx):
    ctx.report(ctx.tr("install.ready", "Icon Store is ready."))
