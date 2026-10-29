"""Sprache: Transkription (Sprache -> Text, mit Sprechern) und Vorlesen (Text -> Sprache) über die Anbieter.

Katalog: media.speech.api (providers.json). Unterstützt:
    openai_audio       /audio/transcriptions (gpt-transcribe; gpt-4o-transcribe-diarize mit bekannten Sprechern,
                       abgekündigt 2027-02-26), /audio/speech (gpt-4o-mini-tts, abgekündigt 2027-01-06)
    elevenlabs_speech  /speech-to-text (scribe_v2, diarize), /text-to-speech/<stimme>
    deepgram           /listen (nova-3, diarize, utterances)
    assemblyai         /upload + /transcript (universal-3-pro, speaker_labels), Abfragen bis fertig
    gemini_audio       generateContent: Audio rein + Anweisung (Erkennung, Sprecher als „Speaker N:“),
                       *-tts-Modelle mit responseModalities AUDIO und einer der 30 Stimmen (PCM 24 kHz -> WAV)
openai_audio passt auch für Groq (whisper-large-v3-turbo) und Mistral (voxtral-mini-latest).
Vorlesen ohne Anbieter erledigt die Systemstimme (QTextToSpeech) in der Oberfläche.
Qt-frei; Audio immer als WAV-Bytes.
"""

from __future__ import annotations

import base64
import io
import json
import re
import secrets
import threading
import time
import urllib.parse
import wave
from dataclasses import dataclass

from omniwrench.core.i18n import tr

from . import http as aihttp
from .connections import Connection, ConnectionStore
from .http import AIError
from .media import ImageGen, _check, _raw, _raw_json, _wait, api_for

STT_APIS = ("openai_audio", "elevenlabs_speech", "deepgram", "assemblyai", "gemini_audio")
TTS_APIS = ("openai_audio", "elevenlabs_speech", "gemini_audio")
KNOWN_MAX = 4                        # OpenAI: höchstens 4 bekannte Sprecher je Anfrage
ELEVEN_VOICE = "JBFqnCBsd6RMkjVDRZzb"
OPENAI_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")
GEMINI_VOICES = ("Kore", "Puck", "Charon", "Zephyr", "Fenrir", "Leda", "Orus", "Aoede", "Callirrhoe", "Autonoe",
                 "Enceladus", "Iapetus", "Umbriel", "Algieba", "Despina", "Erinome", "Algenib", "Rasalgethi",
                 "Laomedeia", "Achernar", "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
                 "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat")


@dataclass
class Segment:
    text: str
    start: float = 0.0               # Sekunden ab Beginn des Abschnitts
    end: float = 0.0
    speaker: str = ""                # Kennung des Anbieters ("A", "0", "speaker_1") oder ein bekannter Name
    known: bool = False              # speaker ist ein Name aus den Sprecherprofilen


def wav_bytes(samples, rate: int = 16000) -> bytes:
    """float32-Samples (-1..1, mono) -> 16-bit-WAV."""
    import numpy as np
    pcm = (np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def stt_connections(store: ConnectionStore) -> list[Connection]:
    return [c for c in store.list() if api_for(c, "speech") in STT_APIS]


def tts_connections(store: ConnectionStore) -> list[Connection]:
    return [c for c in store.list() if api_for(c, "speech") in TTS_APIS and tts_models(c)]


def _models(conn: Connection) -> list[str]:
    info = conn.info
    return list((((info.media if info else {}) or {}).get("speech") or {}).get("models") or [])


def stt_models(conn: Connection) -> list[str]:
    api = api_for(conn, "speech")
    ms = _models(conn)
    if api in ("openai_audio", "gemini_audio"):
        return [m for m in ms if "tts" not in m]
    if api == "elevenlabs_speech":
        return [m for m in ms if m.startswith("scribe")]
    return ms


def tts_models(conn: Connection) -> list[str]:
    api = api_for(conn, "speech")
    ms = _models(conn)
    if api in ("openai_audio", "gemini_audio"):
        return [m for m in ms if "tts" in m]
    if api == "elevenlabs_speech":
        return [m for m in ms if m.startswith("eleven_")]
    return []


def voices(conn: Connection) -> list[str]:
    """Stimmen zum Auswählen (ElevenLabs: Stimm-ID eintragen, daher leer)."""
    api = api_for(conn, "speech")
    if api == "gemini_audio":
        return list(GEMINI_VOICES)
    if api == "openai_audio" and tts_models(conn):
        return list(OPENAI_VOICES)
    return []


def pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def parse_speakers(text: str) -> list[Segment]:
    """„Speaker 1: …“-Zeilen (Gemini-Erkennung) in Abschnitte je Sprecher."""
    out: list[Segment] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\**\s*(?:speaker|sprecher)\s*(\w+)\s*\**\s*:\s*(.*)$", line, re.I)
        if m:
            out.append(Segment(m.group(2).strip(), speaker=m.group(1)))
        elif out:
            out[-1].text = (out[-1].text + " " + line).strip()
        else:
            out.append(Segment(line))
    return [seg for seg in out if seg.text]

def knows_speakers(conn: Connection, model: str) -> bool:
    """Kann der Anbieter Sprecher anhand von Stimmproben benennen?"""
    return api_for(conn, "speech") == "openai_audio" and "diarize" in (model or "")


def _multipart(pairs: list[tuple[str, str]], files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    """multipart/form-data mit wiederholbaren Feldern (languages[], known_speaker_names[] …)."""
    boundary = "----OmniWrench" + secrets.token_hex(12)
    out = bytearray()
    for name, value in pairs:
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
    for name, filename, mime, data in files:
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _group_words(words: list[dict], key: str = "speaker_id") -> list[Segment]:
    """Wörter (ElevenLabs: word/spacing) zu Abschnitten je Sprecher zusammenfassen."""
    out: list[Segment] = []
    for w in words:
        kind = w.get("type", "word")
        if kind == "spacing":
            if out:
                out[-1].text += " "
            continue
        if kind != "word":
            continue
        spk = str(w.get(key) if w.get(key) is not None else "")
        if out and out[-1].speaker == spk:
            out[-1].text += w.get("text", "")
            out[-1].end = float(w.get("end") or out[-1].end)
        else:
            out.append(Segment(w.get("text", ""), float(w.get("start") or 0), float(w.get("end") or 0), spk))
    for seg in out:
        seg.text = " ".join(seg.text.split())
    return [seg for seg in out if seg.text]


class Speech(ImageGen):
    """Transkription und Vorlesen für eine Verbindung."""

    # --------------------------------------------------------------------------- Sprache -> Text
    def transcribe(self, wav: bytes, model: str = "", languages: list[str] | None = None,
                   known: list[tuple[str, bytes]] | None = None, diarize: bool = True) -> list[Segment]:
        api = api_for(self.conn, "speech")
        if api not in STT_APIS:
            raise AIError(f"Transcription is not supported by {self.conn.name}", "request")
        _check(self.stop)
        model = model or (stt_models(self.conn) or [""])[0]
        return getattr(self, f"_stt_{api}")(wav, model, [x for x in (languages or []) if x], known or [], diarize)

    def _stt_openai_audio(self, wav, model, languages, known, diarize) -> list[Segment]:
        pairs = [("model", model or "gpt-transcribe")]
        if "diarize" in model:
            pairs += [("response_format", "diarized_json"), ("chunking_strategy", "auto")]
            for name, ref in known[:KNOWN_MAX]:
                pairs.append(("known_speaker_names[]", name))
                pairs.append(("known_speaker_references[]",
                              "data:audio/wav;base64," + base64.b64encode(ref).decode("ascii")))
            if languages:
                pairs.append(("language", languages[0]))
        elif model == "gpt-transcribe":
            pairs += [("languages[]", lang) for lang in languages]
        else:                                    # whisper (Groq), voxtral (Mistral): Standard-JSON
            if languages:
                pairs.append(("language", languages[0]))
        body, ctype = _multipart(pairs, [("file", "audio.wav", "audio/wav", wav)])
        data = _raw_json(self.url("/audio/transcriptions"), self.headers(), body, ctype, timeout=300)
        names = {n for n, _ in known[:KNOWN_MAX]}
        if data.get("segments"):
            return [Segment((s.get("text") or "").strip(), float(s.get("start") or 0), float(s.get("end") or 0),
                            str(s.get("speaker") or ""), str(s.get("speaker") or "") in names)
                    for s in data["segments"] if (s.get("text") or "").strip()]
        text = (data.get("text") or "").strip()
        return [Segment(text)] if text else []

    def _stt_elevenlabs_speech(self, wav, model, languages, known, diarize) -> list[Segment]:
        pairs = [("model_id", model or "scribe_v2"), ("diarize", "true" if diarize else "false"),
                 ("timestamps_granularity", "word"), ("tag_audio_events", "false")]
        if languages:
            pairs.append(("language_code", languages[0]))
        body, ctype = _multipart(pairs, [("file", "audio.wav", "audio/wav", wav)])
        data = _raw_json(self.url("/speech-to-text"), self.headers(), body, ctype, timeout=300)
        segs = _group_words(data.get("words") or [])
        if not segs and (data.get("text") or "").strip():
            segs = [Segment(data["text"].strip())]
        return segs

    def _stt_deepgram(self, wav, model, languages, known, diarize) -> list[Segment]:
        q = {"model": model or "nova-3", "smart_format": "true", "punctuate": "true", "utterances": "true",
             "language": languages[0] if languages else "multi"}
        if diarize:
            q.update(diarize="true", diarize_model="latest")
        with _raw("POST", self.url("/listen?" + urllib.parse.urlencode(q)), self.headers(), wav, "audio/wav") as r:
            data = json.loads(r.read() or b"{}")
        res = data.get("results") or {}
        utts = res.get("utterances") or []
        if utts:
            return [Segment((u.get("transcript") or "").strip(), float(u.get("start") or 0),
                            float(u.get("end") or 0), str(u.get("speaker", "")))
                    for u in utts if (u.get("transcript") or "").strip()]
        try:
            text = res["channels"][0]["alternatives"][0]["transcript"].strip()
        except (KeyError, IndexError, AttributeError):
            text = ""
        return [Segment(text)] if text else []

    def _stt_assemblyai(self, wav, model, languages, known, diarize) -> list[Segment]:
        up = _raw_json(self.url("/upload"), self.headers(), wav, "application/octet-stream", timeout=300)
        models = [model] if model else ["universal-3-pro"]
        if "universal-2" not in models:
            models.append("universal-2")
        body: dict = {"audio_url": up.get("upload_url"), "speech_models": models, "speaker_labels": bool(diarize)}
        if languages:
            body["language_code"] = languages[0]
        else:
            body["language_detection"] = True
        job = aihttp.json_request("POST", self.url("/transcript"), self.headers(), body, timeout=120)
        tid = job.get("id")
        deadline = time.time() + 600
        while True:
            data = aihttp.json_request("GET", self.url(f"/transcript/{tid}"), self.headers(), timeout=60)
            status = data.get("status")
            if status == "completed":
                break
            if status == "error":
                raise AIError(data.get("error") or "AssemblyAI error", "server")
            if time.time() > deadline:
                raise AIError("AssemblyAI: timeout", "server")
            _wait(self.stop, 1.5)
        utts = data.get("utterances") or []
        if utts:
            return [Segment((u.get("text") or "").strip(), float(u.get("start") or 0) / 1000,
                            float(u.get("end") or 0) / 1000, str(u.get("speaker") or ""))
                    for u in utts if (u.get("text") or "").strip()]
        text = (data.get("text") or "").strip()
        return [Segment(text)] if text else []

    def _gemini(self) -> tuple[str, dict]:
        base = self.conn.url
        if base.endswith("/openai"):
            base = base[: -len("/openai")]
        return base, {"x-goog-api-key": self.store.api_key(self.conn)}

    def _stt_gemini_audio(self, wav, model, languages, known, diarize) -> list[Segment]:
        base, headers = self._gemini()
        prompt = ("Transcribe this audio verbatim in the language that is spoken. Output only the transcript, "
                  "no comments, no timestamps.")
        if languages:
            prompt += f" Expected language: {', '.join(languages)}."
        if diarize:
            prompt += (" If more than one person speaks, start a new line at each change of speaker with "
                       "'Speaker 1:', 'Speaker 2:' and so on.")
        body = {"contents": [{"role": "user", "parts": [
                    {"text": prompt}, {"inline_data": {"mime_type": "audio/wav",
                                                       "data": base64.b64encode(wav).decode("ascii")}}]}],
                "generationConfig": {"temperature": 0}}
        url = f"{base}/models/{urllib.parse.quote(model or 'gemini-3.8-flash', safe='-._')}:generateContent"
        data = aihttp.json_request("POST", url, headers, body, timeout=300)
        text = "".join(part.get("text", "") for cand in data.get("candidates") or []
                       for part in (cand.get("content") or {}).get("parts") or [] if not part.get("thought"))
        return parse_speakers(text) if diarize else ([Segment(text.strip())] if text.strip() else [])

    # --------------------------------------------------------------------------- Text -> Sprache
    def synthesize(self, text: str, model: str = "", voice: str = "") -> tuple[bytes, str]:
        api = api_for(self.conn, "speech")
        model = model or (tts_models(self.conn) or [""])[0]
        if api == "openai_audio":
            body = {"model": model or "gpt-4o-mini-tts", "input": text[:4000],
                    "voice": voice if voice in OPENAI_VOICES else "alloy", "response_format": "mp3"}
            with aihttp.request("POST", self.url("/audio/speech"), dict(self.headers(), Accept="audio/mpeg"), body,
                                timeout=120) as r:
                return r.read(), "audio/mpeg"
        if api == "elevenlabs_speech":
            body = {"text": text[:5000], "model_id": model or "eleven_v4_turbo"}
            path = f"/text-to-speech/{urllib.parse.quote(voice or ELEVEN_VOICE)}?output_format=mp3_44100_128"
            with aihttp.request("POST", self.url(path), dict(self.headers(), Accept="audio/mpeg"), body,
                                timeout=120) as r:
                return r.read(), "audio/mpeg"
        if api == "gemini_audio":
            base, headers = self._gemini()
            body = {"contents": [{"parts": [{"text": text[:4000]}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice if voice in GEMINI_VOICES else "Kore"}}}}}
            url = f"{base}/models/{urllib.parse.quote(model or 'gemini-3.8-flash-tts', safe='-._')}:generateContent"
            data = aihttp.json_request("POST", url, headers, body, timeout=180)
            for cand in data.get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        raw = base64.b64decode(inline["data"])
                        if raw[:4] == b"RIFF":
                            return raw, "audio/wav"
                        mime = inline.get("mimeType") or inline.get("mime_type") or ""
                        rate = re.search(r"rate=(\d+)", mime)
                        return pcm_to_wav(raw, int(rate.group(1)) if rate else 24000), "audio/wav"
            raise AIError("Gemini: no audio in the answer", "server")
        raise AIError(f"Speech output is not supported by {self.conn.name}", "request")


def transcribe(store: ConnectionStore, conn: Connection, wav: bytes, model: str = "",
               languages: list[str] | None = None, known: list[tuple[str, bytes]] | None = None,
               diarize: bool = True, stop: threading.Event | None = None) -> list[Segment]:
    return Speech(store, conn, stop).transcribe(wav, model, languages, known, diarize)


def synthesize(store: ConnectionStore, conn: Connection, text: str, model: str = "", voice: str = "",
               stop: threading.Event | None = None) -> tuple[bytes, str]:
    return Speech(store, conn, stop).synthesize(text, model, voice)


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def transcript_markdown(t: dict) -> str:
    """Lesbare Fassung einer Mitschrift (neben transcript.json, wenn nicht verschlüsselt)."""
    names = {sid: s.get("name", sid) for sid, s in (t.get("speakers") or {}).items()}
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(t.get("created") or 0))
    out = [f"# {t.get('title') or tr('ai.transcript.untitled')}", "", f"{when} · {clock(t.get('duration') or 0)}", ""]
    consent = t.get("consent") or {}
    if consent.get("at"):
        out += [f"> {tr('ai.transcript.consent_note', time=time.strftime('%Y-%m-%d %H:%M', time.localtime(consent['at'])))}",
                ""]
    if t.get("summary"):
        out += [f"## {tr('ai.transcript.summary')}", "", t["summary"], ""]
    out += [f"## {tr('ai.transcript.transcript')}", ""]
    for seg in t.get("segments") or []:
        out.append(f"**[{clock(seg.get('t') or 0)}] {names.get(seg.get('speaker'), seg.get('speaker') or '?')}:** "
                   f"{seg.get('text', '')}")
        out.append("")
    return "\n".join(out)
