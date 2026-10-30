"""Bilder (später Musik und Video) über die Medien-Schnittstellen der Anbieter.

Welche Schnittstelle ein Anbieter hat, steht im Katalog unter media.<art>.api (providers.json).
generate_image() liefert Medien als Bytes; save() legt sie mit einer JSON-Beschreibung in der
Datenablage ab (Bilder werden nie verschlüsselt, damit andere Programme sie öffnen können).

Unterstützte Bild-Schnittstellen:
    openai_images   POST /images/generations (Referenzbilder: /images/edits) – OpenAI, xAI, Azure, Recraft, LocalAI
    chatgpt_image   Responses-API mit Werkzeug image_generation (Anmeldung mit ChatGPT)
    gemini_image    generateContent mit responseModalities IMAGE
    bfl             Black Forest Labs: Auftrag + polling_url
    fal             fal.ai Warteschlange: Auftrag + status_url/response_url
    replicate       Vorhersage mit "Prefer: wait", sonst Abfragen
    stability_image Stability AI stable-image/generate/<modell> (Multipart, Antwort = Bild)
    ideogram        Ideogram 3.0 generate (Multipart)
    minimax_image   MiniMax image_generation (base64)
    comfyui         lokales ComfyUI (auch Musik und Video), Workflows in ai/comfyui.py
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import http as aihttp
from . import providers
from .adapters import Adapter
from .connections import Connection, ConnectionStore
from .http import AIError, Cancelled

KINDS = ("image", "music", "video")
IMAGE_APIS = ("openai_images", "chatgpt_image", "gemini_image", "bfl", "fal", "replicate", "stability_image",
              "ideogram", "minimax_image", "comfyui")
MUSIC_APIS = ("gemini_lyria", "elevenlabs_music", "minimax_music", "stability_audio", "mureka", "fal", "replicate",
              "comfyui")
VIDEO_APIS = ("gemini_omni", "xai_video", "minimax_video", "runway", "luma", "seedance", "fal", "replicate",
              "comfyui")
SUPPORTED = {"image": IMAGE_APIS, "music": MUSIC_APIS, "video": VIDEO_APIS}
VIDEO_ASPECTS = ("16:9", "9:16", "1:1")
RESOLUTIONS = ("720p", "1080p", "480p")
_RUNWAY_RATIO = {"16:9": "1280:720", "9:16": "720:1280", "1:1": "960:960"}
ASPECTS = ("1:1", "16:9", "9:16", "4:3", "3:4")
REFERENCE_APIS = ("openai_images", "chatgpt_image", "gemini_image", "bfl", "fal", "replicate")
STORE_KIND = {"image": "images", "music": "music", "video": "videos"}
POLL_TIMEOUT = {"image": 300, "music": 600, "video": 1800}

# Seitenverhältnis -> Pixel (OpenAI kennt nur quadratisch, quer und hoch)
_OPENAI_SIZE = {"1:1": "1024x1024", "16:9": "1536x1024", "4:3": "1536x1024", "9:16": "1024x1536",
                "3:4": "1024x1536"}
_PIXELS = {"1:1": (1024, 1024), "16:9": (1344, 768), "9:16": (768, 1344), "4:3": (1152, 896), "3:4": (896, 1152)}
_FAL_SIZE = {"1:1": "square_hd", "16:9": "landscape_16_9", "9:16": "portrait_16_9", "4:3": "landscape_4_3",
             "3:4": "portrait_4_3"}
_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
        "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/flac": ".flac", "video/mp4": ".mp4",
        "video/webm": ".webm"}


@dataclass
class Media:
    data: bytes
    mime: str = "image/png"
    meta: dict = field(default_factory=dict)

    @property
    def ext(self) -> str:
        return _EXT.get(self.mime, ".bin")


@dataclass
class Request:
    prompt: str
    model: str = ""
    aspect: str = "1:1"
    count: int = 1
    references: list[dict] = field(default_factory=list)   # [{"mime", "data": bytes}]
    negative: str = ""
    duration: int = 0              # Sekunden (Musik/Video), 0 = Vorgabe des Anbieters
    lyrics: str = ""               # Musik: eigener Liedtext
    instrumental: bool = False     # Musik: ohne Gesang
    resolution: str = ""           # Video: 480p/720p/1080p


# ------------------------------------------------------------------ Katalog
def api_for(conn: Connection, kind: str) -> str:
    """Schnittstelle einer Verbindung für eine Medienart ("" = keine)."""
    info = conn.info
    if info is None or info.removed:
        return ""
    if kind == "image" and conn.auth == providers.AUTH_CHATGPT:
        return "chatgpt_image"
    return str(((info.media or {}).get(kind) or {}).get("api") or "")


def supports(conn: Connection, kind: str) -> bool:
    return api_for(conn, kind) in SUPPORTED.get(kind, ())


def models(conn: Connection, kind: str) -> list[str]:
    info = conn.info
    if kind == "image" and conn.auth == providers.AUTH_CHATGPT:
        return ["gpt-5.5"] if not conn.model else [conn.model]
    return list((((info.media if info else {}) or {}).get(kind) or {}).get("models") or [])


def connections_for(store: ConnectionStore, kind: str) -> list[Connection]:
    return [c for c in store.list() if supports(c, kind)]


def accepts_references(conn: Connection) -> bool:
    return api_for(conn, "image") in REFERENCE_APIS


# ------------------------------------------------------------------ Hilfen
def _check(stop: threading.Event | None) -> None:
    if stop is not None and stop.is_set():
        raise Cancelled()


def _wait(stop: threading.Event | None, seconds: float) -> None:
    if stop is None:
        time.sleep(seconds)
    elif stop.wait(seconds):
        raise Cancelled()


def _download(url: str, headers: dict | None = None, timeout: float = 120) -> Media:
    if url.startswith("data:"):
        head, _, data = url.partition(",")
        return Media(base64.b64decode(data), head[5:].split(";")[0] or "image/png")
    with aihttp.request("GET", url, headers or {}, timeout=timeout) as resp:
        mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
        data = resp.read()
    if not mime or mime in ("application/octet-stream", "binary/octet-stream"):
        mime = _sniff(data)
    return Media(data, mime)


def _sniff(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"ID3" or data[:2] == b"\xff\xfb":
        return "audio/mpeg"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    return "image/png"


def _mime_for(name: str, data: bytes) -> str:
    ext = Path(name).suffix.lower()
    return {".mp3": "audio/mpeg", ".flac": "audio/flac", ".wav": "audio/wav", ".mp4": "video/mp4",
            ".webm": "video/webm", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(ext) \
        or _sniff(data)


def _b64(item: dict) -> str:
    return base64.b64encode(item["data"]).decode("ascii")


def _data_url(item: dict) -> str:
    return f"data:{item.get('mime', 'image/png')};base64,{_b64(item)}"


def _multipart(fields: dict, files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    """(Inhalt, Content-Type) für multipart/form-data. files: (feld, dateiname, mime, daten)."""
    boundary = "----OmniWrench" + secrets.token_hex(12)
    out = bytearray()
    for name, value in fields.items():
        if value is None or value == "":
            continue
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
    for name, filename, mime, data in files:
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {mime}\r\n\r\n").encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def _raw(method: str, url: str, headers: dict, data: bytes, content_type: str, timeout: float = 300):
    """Anfrage mit fertigem Inhalt (Multipart); gibt die offene Antwort zurück."""
    import urllib.request
    h = {"User-Agent": aihttp.USER_AGENT, "Accept": "application/json", "Content-Type": content_type}
    h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        if url.startswith("https:"):
            return urllib.request.urlopen(req, timeout=timeout, context=aihttp._SSL)
        return aihttp._LOCAL_OPENER.open(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        raise aihttp._error_from_http(err) from None
    except (urllib.error.URLError, OSError) as err:
        raise AIError(str(getattr(err, "reason", err)), "network") from None


def _raw_json(url: str, headers: dict, data: bytes, content_type: str, timeout: float = 300) -> dict:
    with _raw("POST", url, headers, data, content_type, timeout) as resp:
        body = resp.read()
    try:
        return json.loads(body) if body else {}
    except ValueError:
        raise AIError(body[:300].decode("utf-8", "replace"), "server") from None


# ------------------------------------------------------------------ Bilder
class ImageGen:
    def __init__(self, store: ConnectionStore, conn: Connection, stop: threading.Event | None = None,
                 progress: Callable[[str], None] | None = None):
        self.store = store
        self.conn = conn
        self.stop = stop
        self.progress = progress or (lambda text: None)
        self.base = Adapter(store, conn)

    def headers(self) -> dict:
        return self.base.headers()

    def url(self, path: str) -> str:
        return self.base.url(path)

    def run(self, req: Request) -> list[Media]:
        api = api_for(self.conn, "image")
        fn = getattr(self, "_" + api, None)
        if fn is None or api not in IMAGE_APIS:
            raise AIError(f"no image api for {self.conn.provider}", "request", code="no_media")
        req.count = max(1, min(int(req.count or 1), 4))
        req.model = req.model or (models(self.conn, "image") or [""])[0]
        out = fn(req)
        if not out:
            raise AIError("no image in the answer", "server", code="no_result")
        for m in out:
            m.meta.setdefault("model", req.model)
        return out

    # --- ComfyUI (lokal, kostenlos) -------------------------------------------------------------------
    def _comfy(self, kind: str, model: str, workflow: dict) -> list[Media]:
        from . import comfyui
        comfyui.check_ready(self.conn.url, kind, model)
        files = comfyui.run(self.conn.url, workflow, self.stop, self.progress, POLL_TIMEOUT.get(kind, 1800))
        return [Media(data, _mime_for(name, data)) for data, name in files]

    def _comfyui(self, req: Request) -> list[Media]:
        from . import comfyui
        return self._comfy("image", req.model, comfyui.image_workflow(req.model, req.prompt, req.negative,
                                                                       req.aspect, req.count))

    # --- OpenAI-kompatibel ---------------------------------------------------------------------------
    def _openai_images(self, req: Request) -> list[Media]:
        sized = self.conn.provider in ("openai", "azure_openai", "localai", "recraft")
        if req.references:
            fields = {"model": req.model, "prompt": req.prompt, "n": req.count,
                      "size": _OPENAI_SIZE.get(req.aspect) if sized else None}
            files = [("image[]", f"ref{i}{_EXT.get(r.get('mime'), '.png')}", r.get("mime", "image/png"), r["data"])
                     for i, r in enumerate(req.references)]
            body, ctype = _multipart(fields, files)
            data = _raw_json(self.url("/images/edits"), self.headers(), body, ctype)
        else:
            payload: dict = {"model": req.model, "prompt": req.prompt, "n": req.count}
            if sized:
                payload["size"] = _OPENAI_SIZE.get(req.aspect, "1024x1024")
            elif self.conn.provider == "xai":
                payload["aspect_ratio"] = req.aspect
            data = aihttp.json_request("POST", self.url("/images/generations"), self.headers(), payload,
                                       timeout=300)
        out = []
        for item in data.get("data") or []:
            _check(self.stop)
            if item.get("b64_json"):
                raw = base64.b64decode(item["b64_json"])
                m = Media(raw, _sniff(raw))
            elif item.get("url"):
                m = _download(item["url"])
            else:
                continue
            if item.get("revised_prompt"):
                m.meta["revised_prompt"] = item["revised_prompt"]
            out.append(m)
        return out

    def _chatgpt_image(self, req: Request) -> list[Media]:
        out = []
        for _ in range(req.count):
            parts: list[dict] = [{"type": "input_text", "text": req.prompt}]
            for r in req.references:
                parts.append({"type": "input_image", "image_url": _data_url(r)})
            size = _OPENAI_SIZE.get(req.aspect, "1024x1024")
            body = {"model": self.conn.model or req.model, "input": [{"role": "user", "content": parts}],
                    "tools": [{"type": "image_generation", "size": size}],
                    "tool_choice": {"type": "image_generation"}, "stream": True, "store": False,
                    "instructions": "Create the requested image."}
            for event, data in aihttp.sse(self.url("/responses"), self.headers(), body, self.stop):
                if not isinstance(data, dict):
                    continue
                kind = data.get("type") or event
                if kind == "response.output_item.done":
                    item = data.get("item") or {}
                    if item.get("type") == "image_generation_call" and item.get("result"):
                        raw = base64.b64decode(item["result"])
                        m = Media(raw, _sniff(raw))
                        if item.get("revised_prompt"):
                            m.meta["revised_prompt"] = item["revised_prompt"]
                        out.append(m)
                elif kind in ("response.failed", "error"):
                    err = (data.get("response") or {}).get("error") or data.get("error") or data
                    msg = err.get("message", kind) if isinstance(err, dict) else str(err)
                    code = str(err.get("code", "")) if isinstance(err, dict) else ""
                    raise AIError(msg, "limit" if code.startswith("subscription_sharing_usage") else "server",
                                  code=code)
        return out

    # --- Google Gemini -------------------------------------------------------------------------------
    def _gemini_image(self, req: Request) -> list[Media]:
        base = self.conn.url
        if base.endswith("/openai"):
            base = base[: -len("/openai")]
        key = self.store.api_key(self.conn)
        parts: list[dict] = [{"text": req.prompt}]
        for r in req.references:
            parts.append({"inline_data": {"mime_type": r.get("mime", "image/png"), "data": _b64(r)}})
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": req.aspect}}}
        url = f"{base}/models/{urllib.parse.quote(req.model, safe='-._')}:generateContent"
        out = []
        for _ in range(req.count):
            _check(self.stop)
            data = aihttp.json_request("POST", url, {"x-goog-api-key": key}, body, timeout=300)
            for cand in data.get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        out.append(Media(base64.b64decode(inline["data"]),
                                         inline.get("mimeType") or inline.get("mime_type") or "image/png"))
            if not out and (data.get("promptFeedback") or {}).get("blockReason"):
                raise AIError(data["promptFeedback"]["blockReason"], "request", code="blocked")
        return out

    # --- Black Forest Labs ---------------------------------------------------------------------------
    def _bfl(self, req: Request) -> list[Media]:
        w, h = _PIXELS.get(req.aspect, (1024, 1024))
        out = []
        for _ in range(req.count):
            payload: dict = {"prompt": req.prompt, "width": w, "height": h, "output_format": "png"}
            if "kontext" in req.model:
                payload = {"prompt": req.prompt, "aspect_ratio": req.aspect, "output_format": "png"}
            for i, r in enumerate(req.references[:4]):
                payload["input_image" if i == 0 else f"input_image_{i + 1}"] = _b64(r)
            job = aihttp.json_request("POST", self.url("/" + req.model), self.headers(), payload, timeout=60)
            poll = job.get("polling_url") or self.url(f"/get_result?id={job.get('id', '')}")
            result = self._poll(lambda: aihttp.json_request("GET", poll, self.headers(), timeout=60),
                                lambda d: str(d.get("status", "")), ("Ready",),
                                ("Error", "Failed", "Content Moderated", "Request Moderated", "Task not found"))
            sample = (result.get("result") or {}).get("sample")
            if sample:
                out.append(_download(sample))
        return out

    # --- fal.ai --------------------------------------------------------------------------------------
    def _fal(self, req: Request) -> list[Media]:
        payload: dict = {"prompt": req.prompt, "num_images": req.count, "image_size": _FAL_SIZE.get(req.aspect),
                         "aspect_ratio": req.aspect}
        if req.negative:
            payload["negative_prompt"] = req.negative
        if req.references:
            payload["image_urls"] = [_data_url(r) for r in req.references]
        result = self._fal_queue(req.model, payload)
        items = result.get("images") or ([result["image"]] if isinstance(result.get("image"), dict) else [])
        return [_download(i["url"]) for i in items if isinstance(i, dict) and i.get("url")]

    def _fal_queue(self, model: str, payload: dict) -> dict:
        job = aihttp.json_request("POST", self.url("/" + model.strip("/")), self.headers(), payload, timeout=60)
        status_url = job.get("status_url") or self.url(f"/{model}/requests/{job.get('request_id', '')}/status")
        response_url = job.get("response_url") or self.url(f"/{model}/requests/{job.get('request_id', '')}")
        self._poll(lambda: aihttp.json_request("GET", status_url, self.headers(), timeout=60),
                   lambda d: str(d.get("status", "")), ("COMPLETED",), ("FAILED", "ERROR"))
        return aihttp.json_request("GET", response_url, self.headers(), timeout=120)

    # --- Replicate -----------------------------------------------------------------------------------
    def _replicate(self, req: Request) -> list[Media]:
        inp: dict = {"prompt": req.prompt, "aspect_ratio": req.aspect, "num_outputs": req.count,
                     "output_format": "png"}
        if req.negative:
            inp["negative_prompt"] = req.negative
        if req.references:
            inp["input_images"] = [_data_url(r) for r in req.references]
            inp["image"] = _data_url(req.references[0])
        result = self._replicate_run(req.model, inp)
        output = result.get("output")
        urls = output if isinstance(output, list) else [output]
        return [_download(u) for u in urls if isinstance(u, str) and u]

    def _replicate_run(self, model: str, inp: dict) -> dict:
        h = dict(self.headers(), Prefer="wait=60")
        pred = aihttp.json_request("POST", self.url(f"/models/{model}/predictions"), h, {"input": inp},
                                   timeout=120)
        if pred.get("status") == "succeeded":
            return pred
        get = (pred.get("urls") or {}).get("get") or self.url(f"/predictions/{pred.get('id', '')}")
        return self._poll(lambda: aihttp.json_request("GET", get, self.headers(), timeout=60),
                          lambda d: str(d.get("status", "")), ("succeeded",), ("failed", "canceled"))

    # --- Stability AI --------------------------------------------------------------------------------
    def _stability_image(self, req: Request) -> list[Media]:
        model = req.model or "core"
        path, extra = (model, {}) if model in ("ultra", "core") else ("sd3", {"model": model})
        out = []
        for _ in range(req.count):
            _check(self.stop)
            fields = {"prompt": req.prompt, "aspect_ratio": req.aspect, "output_format": "png",
                      "negative_prompt": req.negative, **extra}
            body, ctype = _multipart(fields, [])
            h = dict(self.headers(), Accept="image/*")
            with _raw("POST", self.url(f"/stable-image/generate/{path}"), h, body, ctype) as resp:
                data = resp.read()
                mime = (resp.headers.get("Content-Type") or "image/png").split(";")[0]
            out.append(Media(data, mime if mime.startswith("image/") else _sniff(data)))
        return out

    # --- Ideogram ------------------------------------------------------------------------------------
    def _ideogram(self, req: Request) -> list[Media]:
        speed = "TURBO" if "TURBO" in req.model.upper() else "DEFAULT"
        fields = {"prompt": req.prompt, "aspect_ratio": req.aspect.replace(":", "x"), "rendering_speed": speed,
                  "num_images": req.count, "negative_prompt": req.negative}
        body, ctype = _multipart(fields, [])
        data = _raw_json(self.url("/ideogram-v3/generate"), self.headers(), body, ctype)
        return [_download(i["url"]) for i in data.get("data") or [] if i.get("url")]

    # --- MiniMax -------------------------------------------------------------------------------------
    def _minimax_image(self, req: Request) -> list[Media]:
        payload = {"model": req.model or "image-01", "prompt": req.prompt, "aspect_ratio": req.aspect,
                   "n": req.count, "response_format": "base64"}
        data = aihttp.json_request("POST", self.url("/image_generation"), self.headers(), payload, timeout=300)
        status = data.get("base_resp") or {}
        if status.get("status_code") not in (None, 0):
            raise AIError(status.get("status_msg") or "error", "request", code=str(status.get("status_code")))
        raws = [base64.b64decode(b) for b in (data.get("data") or {}).get("image_base64") or []]
        return [Media(r, _sniff(r)) for r in raws]

    # --- Abfragen ------------------------------------------------------------------------------------
    def _poll(self, get: Callable[[], dict], status: Callable[[dict], str], done: tuple, failed: tuple,
              kind: str = "") -> dict:
        kind = kind or getattr(self, "kind", "image")
        start = time.monotonic()
        delay = 1.5
        while True:
            _check(self.stop)
            data = get()
            state = status(data)
            if state in done:
                return data
            if state in failed:
                detail = data.get("error") or data.get("detail") or state
                raise AIError(str(detail)[:300], "request", code="failed")
            self.progress(state)
            if time.monotonic() - start > POLL_TIMEOUT.get(kind, 300):
                raise AIError("timeout", "network", code="timeout")
            _wait(self.stop, delay)
            delay = min(delay * 1.5, 8)


class MediaGen(ImageGen):
    """Musik und Video. Methoden _music_<api> bzw. _video_<api> liefern Media-Listen."""

    def generate(self, kind: str, req: Request) -> list[Media]:
        if kind == "image":
            return self.run(req)
        self.kind = kind
        api = api_for(self.conn, kind)
        fn = getattr(self, f"_{kind}_{api}", None)
        if fn is None or api not in SUPPORTED.get(kind, ()):
            raise AIError(f"no {kind} api for {self.conn.provider}", "request", code="no_media")
        req.model = req.model or (models(self.conn, kind) or [""])[0]
        out = fn(req)
        if not out:
            raise AIError(f"no {kind} in the answer", "server", code="no_result")
        for m in out:
            m.meta.setdefault("model", req.model)
        return out

    def _music_text(self, req: Request) -> str:
        text = req.prompt
        if req.instrumental:
            text += "\nInstrumental only, no vocals."
        if req.duration:
            text += f"\nLength: about {req.duration} seconds."
        if req.lyrics and not req.instrumental:
            text += "\n\nLyrics:\n" + req.lyrics
        return text

    # --- ComfyUI --------------------------------------------------------------------------------------
    def _music_comfyui(self, req: Request) -> list[Media]:
        from . import comfyui
        out = self._comfy("music", req.model, comfyui.music_workflow(req.prompt, req.lyrics, req.duration or 60,
                                                                      req.instrumental))
        for m in out:
            if req.lyrics and not req.instrumental:
                m.meta["lyrics"] = req.lyrics
        return out

    def _video_comfyui(self, req: Request) -> list[Media]:
        from . import comfyui
        return self._comfy("video", req.model, comfyui.video_workflow(req.prompt, req.negative, req.aspect,
                                                                      req.duration or 5))

    # --- Musik ---------------------------------------------------------------------------------------
    def _music_gemini_lyria(self, req: Request) -> list[Media]:
        base = self.conn.url
        if base.endswith("/openai"):
            base = base[: -len("/openai")]
        key = self.store.api_key(self.conn)
        parts: list[dict] = [{"text": self._music_text(req)}]
        for r in req.references:
            parts.append({"inline_data": {"mime_type": r.get("mime", "image/png"), "data": _b64(r)}})
        url = f"{base}/models/{urllib.parse.quote(req.model, safe='-._')}:generateContent"
        data = aihttp.json_request("POST", url, {"x-goog-api-key": key}, {"contents": [{"parts": parts}]},
                                   timeout=600)
        out, lyrics = [], []
        for cand in data.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    raw = base64.b64decode(inline["data"])
                    out.append(Media(raw, inline.get("mimeType") or inline.get("mime_type") or _sniff(raw)))
                elif part.get("text"):
                    lyrics.append(part["text"])
        for m in out:
            if lyrics:
                m.meta["lyrics"] = "\n".join(lyrics)
        return out

    def _music_elevenlabs_music(self, req: Request) -> list[Media]:
        body: dict = {"prompt": req.prompt, "model_id": req.model or "music_v1"}
        if req.duration:
            body["music_length_ms"] = max(3000, min(600_000, req.duration * 1000))
        if req.instrumental:
            body["force_instrumental"] = True
        elif req.lyrics:
            body["prompt"] = self._music_text(Request(req.prompt, lyrics=req.lyrics))
        h = dict(self.headers(), Accept="audio/mpeg")
        with aihttp.request("POST", self.url("/music?output_format=mp3_44100_128"), h, body, timeout=600) as resp:
            data = resp.read()
        return [Media(data, "audio/mpeg")]

    def _music_minimax_music(self, req: Request) -> list[Media]:
        body: dict = {"model": req.model, "prompt": req.prompt,
                      "audio_setting": {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"}}
        if req.lyrics and not req.instrumental:
            body["lyrics"] = req.lyrics
        else:
            body["is_instrumental"] = True
        data = aihttp.json_request("POST", self.url("/music_generation"), self.headers(), body, timeout=600)
        status = data.get("base_resp") or {}
        if status.get("status_code") not in (None, 0):
            raise AIError(status.get("status_msg") or "error", "request", code=str(status.get("status_code")))
        audio = (data.get("data") or {}).get("audio") or ""
        if audio.startswith("http"):
            return [_download(audio)]
        return [Media(bytes.fromhex(audio), "audio/mpeg")] if audio else []

    def _music_stability_audio(self, req: Request) -> list[Media]:
        fields = {"prompt": self._music_text(Request(req.prompt, instrumental=req.instrumental)),
                  "duration": req.duration or None, "output_format": "mp3", "model": req.model}
        body, ctype = _multipart(fields, [])
        h = dict(self.headers(), Accept="audio/*")
        with _raw("POST", self.url("/audio/stable-audio-2/text-to-audio"), h, body, ctype, 600) as resp:
            data = resp.read()
        return [Media(data, "audio/mpeg")]

    def _music_mureka(self, req: Request) -> list[Media]:
        kind = "instrumental" if req.instrumental or not req.lyrics else "song"
        body: dict = {"model": req.model or "auto", "prompt": req.prompt}
        if kind == "song":
            body["lyrics"] = req.lyrics
        job = aihttp.json_request("POST", self.url(f"/{kind}/generate"), self.headers(), body, timeout=60)
        result = self._poll(lambda: aihttp.json_request("GET", self.url(f"/{kind}/query/{job.get('id', '')}"),
                                                        self.headers(), timeout=60),
                            lambda d: str(d.get("status", "")), ("succeeded",),
                            ("failed", "cancelled", "timeouted"))
        return [_download(c["url"]) for c in result.get("choices") or [] if c.get("url")]

    def _music_fal(self, req: Request) -> list[Media]:
        payload: dict = {"prompt": self._music_text(req)}
        if req.duration:
            payload["duration"] = req.duration
            payload["music_length_ms"] = req.duration * 1000
        if req.lyrics and not req.instrumental:
            payload["lyrics"] = req.lyrics
        return self._fal_files(self._fal_queue(req.model, payload), ("audio", "audio_file", "audio_url"))

    def _music_replicate(self, req: Request) -> list[Media]:
        inp: dict = {"prompt": self._music_text(req)}
        if req.duration:
            inp["duration"] = req.duration
        if req.lyrics and not req.instrumental:
            inp["lyrics"] = req.lyrics
        return self._replicate_files(self._replicate_run(req.model, inp))

    # --- Video ---------------------------------------------------------------------------------------
    def _video_gemini_omni(self, req: Request) -> list[Media]:
        base = self.conn.url
        if base.endswith("/openai"):
            base = base[: -len("/openai")]
        key = {"x-goog-api-key": self.store.api_key(self.conn)}
        content: list | str = req.prompt
        if req.references:
            content = [{"type": "text", "text": req.prompt}] + [
                {"type": "image", "mime_type": r.get("mime", "image/png"), "data": _b64(r)} for r in req.references]
        fmt = {"type": "video", "delivery": "uri", "aspect_ratio": req.aspect if req.aspect in ("16:9", "9:16")
               else "16:9", "resolution": req.resolution or "720p"}
        data = aihttp.json_request("POST", base + "/interactions", key,
                                   {"model": req.model, "input": content, "response_format": fmt}, timeout=900)
        out = []
        for item in _find_items(data, "video"):
            if item.get("data"):
                out.append(Media(base64.b64decode(item["data"]), item.get("mime_type") or "video/mp4"))
            elif item.get("uri"):
                file_id = item["uri"].rstrip("/").rsplit("/", 1)[-1].split(":")[0]
                self._poll(lambda: aihttp.json_request("GET", f"{base}/files/{file_id}", key, timeout=60),
                           lambda d: str(d.get("state", "")), ("ACTIVE",), ("FAILED",))
                out.append(_download(f"{base}/files/{file_id}:download?alt=media", key, timeout=600))
        return out

    def _video_xai_video(self, req: Request) -> list[Media]:
        body: dict = {"model": req.model, "prompt": req.prompt, "aspect_ratio": req.aspect}
        if req.duration:
            body["duration"] = max(1, min(15, req.duration))
        if req.resolution:
            body["resolution"] = req.resolution
        if req.references:
            body["image"] = {"url": _data_url(req.references[0])}
        job = aihttp.json_request("POST", self.url("/videos/generations"), self.headers(), body, timeout=60)
        rid = job.get("request_id") or job.get("id", "")
        result = self._poll(lambda: aihttp.json_request("GET", self.url(f"/videos/{rid}"), self.headers(), timeout=60),
                            lambda d: str(d.get("status", "")), ("done",), ("failed", "expired"))
        url = (result.get("video") or {}).get("url")
        return [_download(url, timeout=600)] if url else []

    def _video_minimax_video(self, req: Request) -> list[Media]:
        body: dict = {"model": req.model, "prompt": req.prompt}
        if req.duration:
            body["duration"] = 10 if req.duration > 6 else 6
        if req.resolution:
            body["resolution"] = {"480p": "512P", "720p": "768P", "1080p": "1080P"}.get(req.resolution, "768P")
        if req.references:
            body["first_frame_image"] = _data_url(req.references[0])
        job = aihttp.json_request("POST", self.url("/video_generation"), self.headers(), body, timeout=60)
        status = job.get("base_resp") or {}
        if status.get("status_code") not in (None, 0):
            raise AIError(status.get("status_msg") or "error", "request", code=str(status.get("status_code")))
        tid = job.get("task_id", "")
        result = self._poll(lambda: aihttp.json_request("GET", self.url(f"/query/video_generation?task_id={tid}"),
                                                        self.headers(), timeout=60),
                            lambda d: str(d.get("status", "")), ("Success",), ("Fail", "Failed"))
        info = aihttp.json_request("GET", self.url(f"/files/retrieve?file_id={result.get('file_id', '')}"),
                                   self.headers(), timeout=60)
        url = (info.get("file") or {}).get("download_url")
        return [_download(url, timeout=600)] if url else []

    def _video_runway(self, req: Request) -> list[Media]:
        h = dict(self.headers(), **{"X-Runway-Version": "2024-11-06"})
        body: dict = {"model": req.model, "promptText": req.prompt,
                      "ratio": _RUNWAY_RATIO.get(req.aspect, "1280:720"), "duration": req.duration or 5}
        path = "/text_to_video"
        if req.references:
            path = "/image_to_video"
            body["promptImage"] = _data_url(req.references[0])
        job = aihttp.json_request("POST", self.url(path), h, body, timeout=60)
        result = self._poll(lambda: aihttp.json_request("GET", self.url(f"/tasks/{job.get('id', '')}"), h, timeout=60),
                            lambda d: str(d.get("status", "")), ("SUCCEEDED",), ("FAILED", "CANCELLED"))
        return [_download(u, timeout=600) for u in result.get("output") or [] if isinstance(u, str)]

    def _video_luma(self, req: Request) -> list[Media]:
        body: dict = {"prompt": req.prompt, "model": req.model, "aspect_ratio": req.aspect}
        if req.duration:
            body["duration"] = f"{9 if req.duration > 6 else 5}s"
        if req.resolution:
            body["resolution"] = req.resolution
        if req.references:
            body["keyframes"] = {"frame0": {"type": "image", "url": _data_url(req.references[0])}}
        job = aihttp.json_request("POST", self.url("/generations"), self.headers(), body, timeout=60)
        result = self._poll(lambda: aihttp.json_request("GET", self.url(f"/generations/{job.get('id', '')}"),
                                                        self.headers(), timeout=60),
                            lambda d: str(d.get("state", "")), ("completed",), ("failed",))
        url = (result.get("assets") or {}).get("video")
        return [_download(url, timeout=600)] if url else []

    def _video_seedance(self, req: Request) -> list[Media]:
        text = f"{req.prompt} --ratio {req.aspect}"
        if req.duration:
            text += f" --duration {req.duration}"
        if req.resolution:
            text += f" --resolution {req.resolution}"
        content: list[dict] = [{"type": "text", "text": text}]
        for r in req.references[:1]:
            content.append({"type": "image_url", "image_url": {"url": _data_url(r)}})
        job = aihttp.json_request("POST", self.url("/contents/generations/tasks"), self.headers(),
                                  {"model": req.model, "content": content}, timeout=60)
        result = self._poll(lambda: aihttp.json_request("GET", self.url(f"/contents/generations/tasks/{job.get('id', '')}"),
                                                        self.headers(), timeout=60),
                            lambda d: str(d.get("status", "")), ("succeeded",), ("failed", "cancelled"))
        url = (result.get("content") or {}).get("video_url")
        return [_download(url, timeout=600)] if url else []

    def _video_fal(self, req: Request) -> list[Media]:
        payload: dict = {"prompt": req.prompt, "aspect_ratio": req.aspect}
        if req.duration:
            payload["duration"] = str(req.duration)
        if req.resolution:
            payload["resolution"] = req.resolution
        if req.negative:
            payload["negative_prompt"] = req.negative
        if req.references:
            payload["image_url"] = _data_url(req.references[0])
        return self._fal_files(self._fal_queue(req.model, payload), ("video", "video_url"))

    def _video_replicate(self, req: Request) -> list[Media]:
        inp: dict = {"prompt": req.prompt, "aspect_ratio": req.aspect}
        if req.duration:
            inp["duration"] = req.duration
        if req.resolution:
            inp["resolution"] = req.resolution
        if req.references:
            inp["image"] = _data_url(req.references[0])
            inp["start_image"] = inp["image"]
        return self._replicate_files(self._replicate_run(req.model, inp))

    # --- gemeinsame Auswertung -------------------------------------------------------------------------
    @staticmethod
    def _fal_files(result: dict, keys: tuple[str, ...]) -> list[Media]:
        for key in keys:
            value = result.get(key)
            if isinstance(value, dict) and value.get("url"):
                return [_download(value["url"], timeout=600)]
            if isinstance(value, str) and value.startswith("http"):
                return [_download(value, timeout=600)]
            if isinstance(value, list):
                return [_download(v["url"] if isinstance(v, dict) else v, timeout=600) for v in value if v]
        return []

    @staticmethod
    def _replicate_files(result: dict) -> list[Media]:
        output = result.get("output")
        urls = output if isinstance(output, list) else [output]
        return [_download(u, timeout=600) for u in urls if isinstance(u, str) and u.startswith(("http", "data:"))]


def _find_items(data, kind: str) -> list[dict]:
    """Alle Inhalte {"type": kind, ...} in einer verschachtelten Antwort (Interactions-API)."""
    out: list[dict] = []
    if isinstance(data, dict):
        if data.get("type") == kind and (data.get("data") or data.get("uri")):
            out.append(data)
        for v in data.values():
            out += _find_items(v, kind)
    elif isinstance(data, list):
        for v in data:
            out += _find_items(v, kind)
    return out


def generate(store: ConnectionStore, conn: Connection, kind: str, req: Request,
             stop: threading.Event | None = None, progress: Callable[[str], None] | None = None) -> list[Media]:
    return MediaGen(store, conn, stop, progress).generate(kind, req)


def generate_image(store: ConnectionStore, conn: Connection, req: Request, stop: threading.Event | None = None,
                   progress: Callable[[str], None] | None = None) -> list[Media]:
    return ImageGen(store, conn, stop, progress).run(req)


# ------------------------------------------------------------------ Ablage
def save(storage, kind: str, media: Media, meta: dict) -> Path:
    """Speichert die Datei plus <name>.json (Prompt, Modell, Verbindung, Zeit) in der Datenablage."""
    stem = " ".join(str(meta.get("prompt") or kind).split()[:6])
    path = storage.media_target(STORE_KIND.get(kind, kind), stem, media.ext)
    n = 1
    while path.exists():
        path = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    path.write_bytes(media.data)
    info = {"format": 1, "kind": kind, "file": path.name, "created": int(time.time()), **meta, **media.meta}
    path.with_suffix(path.suffix + ".json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                                        encoding="utf-8")
    return path


def read_meta(path: Path) -> dict:
    try:
        return json.loads(path.with_suffix(path.suffix + ".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def list_files(storage, kind: str, limit: int = 300) -> list[Path]:
    """Neueste Medien einer Art aus der Datenablage (nur Dateien mit passender Endung)."""
    base = storage.path(STORE_KIND.get(kind, kind))
    if not base.is_dir():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"} if kind == "image" else \
        ({".mp3", ".wav", ".ogg", ".flac"} if kind == "music" else {".mp4", ".webm", ".mov"})
    files = [p for p in base.rglob("*") if p.suffix.lower() in exts and p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]
