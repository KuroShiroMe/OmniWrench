"""Installationsroutine: Tonzugriff (numpy, soundcard) in den gemeinsamen KI-Paketordner, auf Wunsch Whisper lokal
(Erkennung ganz offline). Die Auswahl ist vorbelegt (Opt-out) und lässt sich später im Tool nachholen."""

from __future__ import annotations


def check(ctx):
    return []


def install(ctx):
    from omniwrench.ai import audio
    from omniwrench.ai import local_speech as ls
    model = ls.WHISPER_DEFAULT
    chosen = ctx.choose(ctx.tr("install.choose_title", "Optional parts"),
                        ctx.tr("install.choose_text", "Which optional parts should be installed now?"),
                        [("whisper", ctx.tr("install.opt_whisper", "Whisper local: recognition completely offline "
                                                                   "(about {mb} MB)", mb=ls.WHISPER_MODELS[model][1] + 150),
                          True)])
    ctx.ai_packages(list(audio.PACKAGES))
    if "whisper" in chosen and not ls.whisper_ready(audio.shared_dir(), model):
        try:
            ctx.ai_packages(list(ls.WHISPER_PACKAGES))
            ctx.report(ctx.tr("install.loading_whisper", "Loading Whisper model {model} …", model=model))
            ls.whisper_prepare(audio.shared_dir(), model)
        except Exception as err:  # noqa: BLE001 - lässt sich im Tool nachholen
            ctx.report(ctx.tr("install.part_failed", "Not installed ({error}). The tool offers it again.", error=err))
    ctx.report(ctx.tr("install.ready", "Installed."))


def update(ctx, old_version):
    from omniwrench.ai import audio
    ctx.ai_packages(list(audio.PACKAGES))
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))
