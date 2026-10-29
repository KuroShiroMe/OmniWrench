"""Sprache offline und kostenlos: Whisper lokal (faster-whisper) zum Erkennen, Piper zum Vorlesen.

Beide laufen ganz auf dem Rechner. Pakete kommen auf Wunsch in den lib-Ordner des Tools (audio.install_packages),
Modelle und Stimmen in den Datenordner des Tools:
    whisper/   Modelle von Hugging Face (Systran/faster-whisper-*, ~75 MB bis 1,6 GB)
    piper/     Stimmen (<name>.onnx + .onnx.json, ~20–110 MB) aus rhasspy/piper-voices
Qt-frei; Audio als float32-Samples (16 kHz, mono) bzw. WAV-Bytes.
"""

from __future__ import annotations

import io
import json
import threading
import urllib.request
import wave
from pathlib import Path

WHISPER = "__whisper__"
PIPER = "__piper__"
WHISPER_PACKAGES = {"faster_whisper": "faster-whisper"}       # Import-Name -> pip-Name
PIPER_PACKAGES = {"piper": "piper-tts"}
WHISPER_MODELS = {"base": ("Systran/faster-whisper-base", 145), "small": ("Systran/faster-whisper-small", 480),
                  "medium": ("Systran/faster-whisper-medium", 1500),
                  "large-v3-turbo": ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", 1600)}
WHISPER_DEFAULT = "small"
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
PIPER_INDEX = PIPER_BASE + "voices.json"
# Falls die Liste nicht geladen werden kann: bekannte Stimmen je Sprache
PIPER_FALLBACK = {
    "de": ["de_DE-thorsten-medium", "de_DE-thorsten-high", "de_DE-thorsten_emotional-medium", "de_DE-kerstin-low",
           "de_DE-ramona-low", "de_DE-eva_k-x_low", "de_DE-karlsson-low", "de_DE-pavoque-low", "de_DE-mls-medium"],
    "en": ["en_US-amy-medium", "en_US-lessac-medium", "en_US-ryan-high", "en_GB-alba-medium"],
    "fr": ["fr_FR-siwis-medium"], "es": ["es_ES-davefx-medium"], "it": ["it_IT-paola-medium"],
    "nl": ["nl_NL-mls-medium"], "pl": ["pl_PL-gosia-medium"], "pt": ["pt_BR-faber-medium"],
    "ru": ["ru_RU-irina-medium"], "tr": ["tr_TR-fahrettin-medium"], "uk": ["uk_UA-ukrainian_tts-medium"],
}

_lock = threading.Lock()
_whisper: dict[str, object] = {}
_piper: dict[str, object] = {}


def _open(url: str, timeout: int = 60):
    from omniwrench.core.net import _SSL, USER_AGENT
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout,
                                  context=_SSL)


def _download(url: str, target: Path, progress) -> None:
    tmp = target.with_name(target.name + ".part")
    with _open(url) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = resp.read(1 << 16)
            if not block:
                break
            f.write(block)
            done += len(block)
            if progress:
                progress(f"{done * 100 // total} %" if total else f"{done // (1 << 20)} MB")
    tmp.replace(target)


# ------------------------------------------------------------------ Whisper
def whisper_dir(data_dir: Path) -> Path:
    return data_dir / "whisper"


def whisper_ready(data_dir: Path, model: str) -> bool:
    repo = WHISPER_MODELS.get(model, WHISPER_MODELS[WHISPER_DEFAULT])[0]
    snaps = whisper_dir(data_dir) / f"models--{repo.replace('/', '--')}" / "snapshots"
    return snaps.is_dir() and any(p.glob("*/model.bin") for p in [snaps])


def _whisper_model(data_dir: Path, model: str):
    model = model if model in WHISPER_MODELS else WHISPER_DEFAULT
    with _lock:
        if model not in _whisper:
            from faster_whisper import WhisperModel
            _whisper[model] = WhisperModel(WHISPER_MODELS[model][0], device="cpu", compute_type="int8",
                                           download_root=str(whisper_dir(data_dir)))
        return _whisper[model]


def whisper_prepare(data_dir: Path, model: str) -> None:
    """Modell laden (beim ersten Mal von Hugging Face herunterladen)."""
    _whisper_model(data_dir, model)


def whisper_transcribe(data_dir: Path, samples, model: str = "", language: str = "") -> list[tuple[str, float, float]]:
    """float32-Samples (16 kHz) -> [(Text, Start, Ende)]."""
    import numpy as np
    m = _whisper_model(data_dir, model)
    segs, _info = m.transcribe(np.asarray(samples, dtype="float32"), language=language or None, vad_filter=True,
                               beam_size=5)
    return [(s.text.strip(), float(s.start), float(s.end)) for s in segs if s.text.strip()]


def wav_samples(wav: bytes):
    """16-bit-WAV (mono, 16 kHz) -> float32-Samples."""
    import numpy as np
    with wave.open(io.BytesIO(wav)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768.0
        if w.getnchannels() > 1:
            data = data.reshape(-1, w.getnchannels()).mean(axis=1)
    return data


# ------------------------------------------------------------------ Piper
def piper_dir(data_dir: Path) -> Path:
    return data_dir / "piper"


def piper_ready(data_dir: Path, voice: str) -> bool:
    d = piper_dir(data_dir)
    return (d / f"{voice}.onnx").is_file() and (d / f"{voice}.onnx.json").is_file()


def installed_voices(data_dir: Path) -> list[str]:
    d = piper_dir(data_dir)
    return sorted(p.name[:-5] for p in d.glob("*.onnx") if (d / f"{p.name}.json").is_file()) if d.is_dir() else []


def piper_voices(data_dir: Path, lang: str) -> list[tuple[str, int]]:
    """Stimmen der Sprache: [(Name, MB)] – aus voices.json (zwischengespeichert), sonst die bekannte Liste."""
    cache = piper_dir(data_dir) / "voices.json"
    index: dict = {}
    try:
        if not cache.is_file():
            cache.parent.mkdir(parents=True, exist_ok=True)
            with _open(PIPER_INDEX, timeout=20) as resp:
                cache.write_bytes(resp.read())
        index = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}
    out = []
    for key, v in index.items():
        if ((v.get("language") or {}).get("family") or "") != lang:
            continue
        size = sum(f.get("size_bytes", 0) for name, f in (v.get("files") or {}).items() if name.endswith(".onnx"))
        out.append((key, size // 1_000_000))
    if not out:
        out = [(name, 0) for name in PIPER_FALLBACK.get(lang, PIPER_FALLBACK["en"])]
    have = set(installed_voices(data_dir))
    out.sort(key=lambda x: (x[0] not in have, "medium" not in x[0], x[0]))
    return out


def piper_url(voice: str, ext: str) -> str:
    """de_DE-thorsten-medium -> de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx"""
    code, name, quality = voice.split("-", 2)
    return f"{PIPER_BASE}{code.split('_')[0]}/{code}/{name}/{quality}/{voice}{ext}"


def piper_download(data_dir: Path, voice: str, progress=None) -> None:
    d = piper_dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    _download(piper_url(voice, ".onnx.json"), d / f"{voice}.onnx.json", None)
    _download(piper_url(voice, ".onnx"), d / f"{voice}.onnx", progress)


def piper_synthesize(data_dir: Path, voice: str, text: str) -> bytes:
    """Text -> WAV-Bytes."""
    with _lock:
        if voice not in _piper:
            from piper import PiperVoice
            _piper[voice] = PiperVoice.load(str(piper_dir(data_dir) / f"{voice}.onnx"))
        pv = _piper[voice]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        if hasattr(pv, "synthesize_wav"):
            pv.synthesize_wav(text, w)
        else:                                       # piper-tts < 1.3
            pv.synthesize(text, w)
    return buf.getvalue()
