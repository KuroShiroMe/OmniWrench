"""Standard-Assistent je Funktion für alle KI-Tools (App-Einstellung "ai_defaults").

Werte sind Verbindungs-IDs oder Offline-Kennungen (__whisper__, __vosk__, __system__, __piper__). Die Tools
lesen den Wert als Vorauswahl und schreiben ihn bei jeder Auswahl zurück; die Seite „Funktionen“ in den
Einstellungen zeigt und ändert alle auf einmal.
"""

from __future__ import annotations

KEY = "ai_defaults"
FUNCTIONS = ("chat", "image", "music", "video", "docs", "group", "schedule", "ts_stt", "ts_summary", "va_stt",
             "va_tts")
KIND = {"chat": "chat", "image": "image", "music": "music", "video": "video", "docs": "chat", "group": "chat",
        "schedule": "chat", "ts_stt": "stt", "ts_summary": "chat", "va_stt": "stt", "va_tts": "tts"}
WHISPER, VOSK, SYSTEM_VOICE, PIPER = "__whisper__", "__vosk__", "__system__", "__piper__"
LOCAL = {"ts_stt": (WHISPER,), "va_stt": (WHISPER, VOSK), "va_tts": (SYSTEM_VOICE, PIPER)}


def get(settings, function: str) -> str:
    return str((settings.get(KEY) or {}).get(function) or "")


def set(settings, function: str, value: str) -> None:  # noqa: A001 - bewusst wie dict.set
    data = dict(settings.get(KEY) or {})
    if data.get(function) == value:
        return
    data[function] = value
    settings.set(KEY, data)


def candidates(store, function: str) -> list:
    """Verbindungen, die die Funktion können (ohne eingestellte)."""
    from . import media, speech
    kind = KIND.get(function, "chat")
    if kind == "chat":
        conns = store.chat_connections()
    elif kind == "stt":
        conns = speech.stt_connections(store)
    elif kind == "tts":
        conns = speech.tts_connections(store)
    else:
        conns = media.connections_for(store, kind)
    return [c for c in conns if not (c.info and c.info.removed)]
