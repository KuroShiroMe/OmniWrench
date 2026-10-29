"""HTTP für die KI-Anbieter: JSON-Anfragen und Server-Sent-Events (Streaming)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

from omniwrench.core.net import _SSL, USER_AGENT


_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class AIError(Exception):
    """Fehler mit Art ("auth", "limit", "quota", "network", "server", "request", "removed")."""

    def __init__(self, message: str, kind: str = "request", status: int = 0, code: str = ""):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.code = code


class Cancelled(Exception):
    pass


def _error_from_http(err: urllib.error.HTTPError) -> AIError:
    try:
        body = err.read().decode("utf-8", "replace")
    except Exception:
        body = ""
    message, code = body[:500], ""
    try:
        data = json.loads(body)
        e = data.get("error", data) if isinstance(data, dict) else {}
        if isinstance(e, dict):
            message = e.get("message") or message
            code = str(e.get("code") or e.get("type") or "")
        elif isinstance(e, str):              # OAuth: {"error": "invalid_grant", "error_description": "…"}
            code = e
            message = f"{e}: {data['error_description']}" if data.get("error_description") else e
    except ValueError:
        pass
    status = err.code
    if code in ("subscription_sharing_usage_limit_exceeded", "subscription_sharing_usage_unavailable"):
        kind = "limit"
    elif status in (401, 403):
        kind = "auth"
    elif status == 429:
        kind = "quota" if "quota" in (code + message).lower() else "limit"
    elif status >= 500:
        kind = "server"
    else:
        kind = "request"
    return AIError(message or f"HTTP {status}", kind, status, code)


def request(method: str, url: str, headers: dict | None = None, body: Any = None,
            form: dict | None = None, timeout: float = 60) -> urllib.request.addinfourl:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    try:
        if url.startswith("https:"):
            return urllib.request.urlopen(req, timeout=timeout, context=_SSL)
        if host in ("localhost", "::1") or host.startswith("127."):
            # Lokale Server (Ollama, LM Studio …) nie über einen Proxy ansprechen
            return _LOCAL_OPENER.open(req, timeout=timeout)
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as err:
        raise _error_from_http(err) from None
    except (urllib.error.URLError, OSError) as err:
        reason = getattr(err, "reason", err)
        raise AIError(str(reason), "network") from None


def json_request(method: str, url: str, headers: dict | None = None, body: Any = None,
                 form: dict | None = None, timeout: float = 60) -> Any:
    with request(method, url, headers, body, form, timeout) as resp:
        raw = resp.read()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        raise AIError(raw[:300].decode("utf-8", "replace"), "server") from None


def sse(url: str, headers: dict, body: Any, stop: threading.Event | None = None,
        timeout: float = 300) -> Iterator[tuple[str, Any]]:
    """Liefert (event, daten) je Server-Sent-Event. Daten sind JSON oder Text ("[DONE]")."""
    h = dict(headers)
    h["Accept"] = "text/event-stream"
    resp = request("POST", url, h, body, timeout=timeout)
    with resp:
        event, data = "", []
        for raw in resp:
            if stop is not None and stop.is_set():
                raise Cancelled()
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                if data:
                    text = "\n".join(data)
                    try:
                        payload = json.loads(text)
                    except ValueError:
                        payload = text
                    yield event, payload
                event, data = "", []
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event = value
            elif field == "data":
                data.append(value)
        if data:
            text = "\n".join(data)
            try:
                yield event, json.loads(text)
            except ValueError:
                yield event, text
