"""Installationsroutine: keine Zusatzpakete. Braucht nur die KI-Assistenten des Hauptprogramms."""

from __future__ import annotations


def check(ctx):
    return []


def install(ctx):
    ctx.report(ctx.tr("install.ready", "Installed. Assistants are managed under Settings > AI assistants."))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))
