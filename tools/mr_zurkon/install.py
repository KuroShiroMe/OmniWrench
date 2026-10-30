"""Installationsroutine: Tonzugriff (numpy, soundcard) in den gemeinsamen KI-Paketordner; auf Wunsch Weckwort
(Vosk mit kleinem Sprachmodell der Programmsprache), Whisper lokal und Piper. Die Auswahl ist vorbelegt (Opt-out)
und lässt sich später im Tool nachholen."""

from __future__ import annotations


def check(ctx):
    return []


def _lang() -> str:
    from omniwrench.core.i18n import current_language
    return (current_language() or "en").split("_")[0].split("-")[0]


def install(ctx):
    from omniwrench.ai import audio
    from omniwrench.ai import local_speech as ls
    data, lang, model = audio.shared_dir(), _lang(), ls.WHISPER_DEFAULT
    chosen = ctx.choose(ctx.tr("install.choose_title", "Optional parts"),
                        ctx.tr("install.choose_text", "Which optional parts should be installed now?"), [
        ("wake", ctx.tr("install.opt_wake", "Wake word offline (Vosk, about 60 MB)"), True),
        ("whisper", ctx.tr("install.opt_whisper", "Whisper local: recognition completely offline (about {mb} MB)",
                           mb=ls.WHISPER_MODELS[model][1] + 150), True),
        ("piper", ctx.tr("install.opt_piper", "Piper: natural voices offline (about 80 MB)"), True),
    ])
    ctx.ai_packages(list(audio.PACKAGES))

    def step(text, fn) -> bool:
        if text:
            ctx.report(text)
        try:
            fn()
            return True
        except Exception as err:  # noqa: BLE001 - lässt sich im Tool nachholen
            ctx.report(ctx.tr("install.part_failed", "Not installed ({error}). The tool offers it again.", error=err))
            return False
    # Optionale Pakete einzeln: scheitert eines, bleibt der Rest (und das Tool) trotzdem installiert
    for part, pkgs in (("wake", ls.VOSK_PACKAGES), ("whisper", ls.WHISPER_PACKAGES), ("piper", ls.PIPER_PACKAGES)):
        if part in chosen and not step("", lambda p=pkgs: ctx.ai_packages(list(p))):
            chosen = [c for c in chosen if c != part]
    if "wake" in chosen and not ls.vosk_ready(data, lang):
        step(ctx.tr("install.loading_vosk", "Loading speech model for the wake word …"),
             lambda: ls.vosk_download(data, lang, ctx.report))
    if "whisper" in chosen and not ls.whisper_ready(data, model):
        step(ctx.tr("install.loading_whisper", "Loading Whisper model {model} …", model=model),
             lambda: ls.whisper_prepare(data, model))
    if "piper" in chosen:
        voices = ls.piper_voices(data, lang)
        if voices and not ls.piper_ready(data, voices[0][0]):
            step(ctx.tr("install.loading_piper", "Loading Piper voice {voice} …", voice=voices[0][0]),
                 lambda: ls.piper_download(data, voices[0][0], ctx.report))
    ctx.report(ctx.tr("install.ready", "Installed."))


def update(ctx, old_version):
    from omniwrench.ai import audio
    ctx.ai_packages(list(audio.PACKAGES))
    ctx.report(ctx.tr("install.update", "Update from {old}.", old=old_version))
