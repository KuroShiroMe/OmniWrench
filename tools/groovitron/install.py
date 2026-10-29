"""Installationsroutine: ffmpeg (Vorschau, Kürzen, Umwandeln) wird gesucht und unter Windows auf Wunsch
heruntergeladen – in den gemeinsamen KI-Ordner, damit Groovitron und Vidcomic dieselbe Kopie nutzen."""

from __future__ import annotations

import os


def check(ctx):
    return []


def install(ctx):
    from omniwrench.ai import audio
    from omniwrench.ai import ffmpeg as ff
    if ff.find(ctx.settings, audio.shared_dir()):
        ctx.report(ctx.tr("install.ready", "Installed."))
        return
    if os.name != "nt":
        ctx.report(ctx.tr("install.no_ffmpeg_linux", "ffmpeg was not found. Install it with the package manager:\n{cmd}",
                          cmd=ff.linux_hint()))
        return
    chosen = ctx.choose(ctx.tr("install.choose_title", "Optional parts"),
                        ctx.tr("install.choose_text", "Which optional parts should be installed now?"),
                        [("ffmpeg", ctx.tr("install.opt_ffmpeg", "Download ffmpeg (about 100 MB, needed for playback "
                                                                 "previews and editing)"), True)])
    if "ffmpeg" not in chosen:
        ctx.report(ctx.tr("install.later", "Can be installed later in the tool."))
        return
    try:
        path = ff.download_windows(audio.shared_dir(), ctx.report)
        ctx.report(ctx.tr("install.ffmpeg_ready", "ffmpeg ready: {path}", path=path))
    except Exception as err:  # noqa: BLE001 - Tool bleibt nutzbar, Download geht später im Tool
        ctx.report(ctx.tr("install.ffmpeg_failed", "ffmpeg could not be downloaded ({error}). The tool offers it "
                                                   "again.", error=err))


def update(ctx, old_version):
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))
