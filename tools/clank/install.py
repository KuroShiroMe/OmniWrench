"""Installationsroutine von Clank – KI-Studio. Keine zusätzlichen Pakete; Git ist optional (Repositories)."""

from __future__ import annotations

import shutil


def check(ctx):
    return []


def install(ctx):
    if shutil.which("git") is None:
        ctx.report(ctx.tr("install.no_git", "Git was not found. Local repositories and cloning need Git "
                                            "(git-scm.com); folders and online repositories work without it."))
    else:
        ctx.report(ctx.tr("install.ready", "Clank – KI-Studio installed."))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))
