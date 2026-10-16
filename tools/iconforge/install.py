"""Installationsroutine von IconForge. Lucide ist eingebaut, weitere Bibliotheken werden bei Bedarf geladen."""


def check(ctx):
    return []


def install(ctx):
    ctx.report(ctx.tr("install.ready", "IconForge installed."))
