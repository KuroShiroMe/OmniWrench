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
              "ideogram", "minimax_image")
SUPPORTED = {"image": IMAGE_APIS, "music": (), "video": ()}
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
        "audio/mpeg": ".mp3", "audio/wav": ".wav", "video/mp4": ".mp4"}


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
              kind: str = "image") -> dict:
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
