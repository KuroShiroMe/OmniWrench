"""Installationsroutine von Clank – KI-Studio. Keine zusätzlichen Pakete; Git (Repositories) und ffmpeg
(Musik/Video) sind optional und werden nur gemeldet."""

from __future__ import annotations

import os
import shutil


def check(ctx):
    return []


def install(ctx):
    if shutil.which("git") is None:
        ctx.report(ctx.tr("install.no_git", "Git was not found. Local repositories and cloning need Git "
                                            "(git-scm.com); folders and online repositories work without it."))
    else:
        ctx.report(ctx.tr("install.ready", "Clank – KI-Studio installed."))
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    own = (ctx.settings.get("ffmpeg_path") or "").strip()
    if not (own and os.path.isfile(own)) and not (ctx.data_dir / "ffmpeg" / exe).is_file() and not shutil.which("ffmpeg"):
        ctx.report(ctx.tr("install.no_ffmpeg", "ffmpeg was not found. The music and video tabs offer to download "
                                               "it (Windows) or show the install command (Linux)."))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))
