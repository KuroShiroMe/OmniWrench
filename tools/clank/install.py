"""Installationsroutine von Clank – KI-Chat. Keine zusätzlichen Pakete; Git (Repositories) ist optional und wird nur
gemeldet."""

from __future__ import annotations

import shutil


def check(ctx):
    return []


def install(ctx):
    if shutil.which("git") is None:
        ctx.report(ctx.tr("install.no_git", "Git was not found. Local repositories and cloning need Git "
                                            "(git-scm.com); folders and online repositories work without it."))
    else:
        ctx.report(ctx.tr("install.ready", "Clank – AI chat installed."))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))
    if old_version.split(".")[:2] == ["1", "0"]:
        ctx.report(ctx.tr("install.split", "Images, music, video, group chat, documents, schedules, transcription, "
                                           "voice assistant and MCP are now separate AI tools in the store "
                                           "(category AI tools). Their settings are taken over when they open."))
