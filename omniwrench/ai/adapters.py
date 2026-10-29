"""Protokolle der Anbieter.

Einheitliches Nachrichtenformat (wie in den gespeicherten Chats):
    {"role": "user", "content": "...", "images": [{"mime": "image/png", "data": "<base64>"}]}
    {"role": "assistant", "content": "...", "tool_calls": [{"id", "name", "arguments": {...}}]}
    {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}

Ein Adapter schickt den Verlauf ab und meldet über on_event:
    ("text", "<Teiltext>")      ("tool_call", {"id", "name", "arguments"})
und gibt am Ende {"text", "tool_calls", "usage": {"input", "output"}} zurück.
"""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any, Callable

from . import http as aihttp
from . import oauth, providers
from .connections import Connection, ConnectionStore
from .http import AIError

EventFn = Callable[[str, Any], None]

# Anbieter, die Inhalte für Erwachsene erzeugen können, bekommen diese Regel, solange der Schalter aus ist
SAFE_RULE = ("Keep all content suitable for a workplace: no sexual, pornographic or otherwise explicit "
             "content, even if asked.")


def _args(text: str) -> dict:
    try:
        value = json.loads(text) if text else {}
        return value if isinstance(value, dict) else {"value": value}
    except ValueError:
        return {"_raw": text}


class Adapter:
    supports_tools = True

    def __init__(self, store: ConnectionStore, conn: Connection):
        self.store = store
        self.conn = conn
        self.info = conn.info

    # ------------------------------------------------------------ Anmeldung
    def headers(self, interactive: bool = True) -> dict:
        auth = self.conn.auth
        if auth == providers.AUTH_NONE:
            return {}
        if auth in (providers.AUTH_CHATGPT, providers.AUTH_ENTRA, providers.AUTH_CUSTOM):
            return {"Authorization": "Bearer " + oauth.access_token(self.store, self.conn)}
        key = self.store.api_key(self.conn, interactive=interactive)
        header = (self.info.key_header if self.info else "") or "Authorization"
        prefix = (self.info.key_prefix if self.info else "") or ("Bearer " if header == "Authorization" else "")
        return {header: prefix + key}

    def rules(self, system: str) -> str:
        """Systemanweisung plus Inhaltsregel (NSFW-Schalter der Verbindung)."""
        if self.conn.nsfw_capable and not self.conn.nsfw:
            return f"{system}\n\n{SAFE_RULE}" if system else SAFE_RULE
        return system

    def url(self, path: str) -> str:
        base = self.conn.url
        if not base:
            raise AIError("no base url", "request", code="no_url")
        return base + path

    # -------------------------------------------------------------- Abläufe
    def list_models(self, interactive: bool = True) -> list[str]:
        url = (self.info.models_url if self.info else "") or self.url("/models")
        data = aihttp.json_request("GET", url, self.headers(interactive), timeout=20)
        items = data.get("data", data.get("models", [])) if isinstance(data, dict) else data
        out = []
        for item in items or []:
            mid = item.get("id") or item.get("name") if isinstance(item, dict) else item
            if mid:
                mid = str(mid)
                # Gemini meldet "models/<name>", erwartet beim Chat aber nur den Namen
                out.append(mid[len("models/"):] if mid.startswith("models/") else mid)
        return sorted(set(out))

    def test(self) -> str:
        """Prüft die Verbindung. Gibt eine kurze Info zurück (z. B. Anzahl Modelle)."""
        try:
            models = self.list_models()
            return str(len(models))
        except AIError as err:
            if err.kind != "request" or err.status not in (404, 405):
                raise
        self.chat("", [{"role": "user", "content": "ping"}], [], lambda *_: None, threading.Event())
        return ""

    def chat(self, system: str, messages: list[dict], tools: list[dict], on_event: EventFn,
             stop: threading.Event, state: dict | None = None) -> dict:
        raise NotImplementedError


# ------------------------------------------------------------ OpenAI Chat
class OpenAIChat(Adapter):
    """Chat Completions mit SSE, deckt die meisten Anbieter und lokalen Server ab."""

    @staticmethod
    def convert(system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}] if system else []
        for m in messages:
            role = m["role"]
            if role == "user":
                if m.get("images"):
                    parts = [{"type": "text", "text": m.get("content", "")}]
                    for img in m["images"]:
                        parts.append({"type": "image_url",
                                      "image_url": {"url": f"data:{img['mime']};base64,{img['data']}"}})
                    out.append({"role": "user", "content": parts})
                else:
                    out.append({"role": "user", "content": m.get("content", "")})
            elif role == "assistant":
                msg: dict = {"role": "assistant", "content": m.get("content") or None}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                          "function": {"name": c["name"],
                                                       "arguments": json.dumps(c.get("arguments") or {})}}
                                         for c in m["tool_calls"]]
                elif msg["content"] is None:
                    msg["content"] = ""
                out.append(msg)
            elif role == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m.get("content", "")})
        return out

    def chat(self, system, messages, tools, on_event, stop, state=None):
        system = self.rules(system)
        body: dict = {"model": self.conn.model, "messages": self.convert(system, messages), "stream": True,
                      "stream_options": {"include_usage": True}}
        if tools and self.supports_tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        text, calls, usage = [], {}, {}
        for _event, data in aihttp.sse(self.url("/chat/completions"), self.headers(), body, stop):
            if data == "[DONE]" or not isinstance(data, dict):
                continue
            if data.get("error"):
                e = data["error"]
                raise AIError(e.get("message", str(e)) if isinstance(e, dict) else str(e), "server")
            if data.get("usage"):
                u = data["usage"]
                usage = {"input": u.get("prompt_tokens", 0), "output": u.get("completion_tokens", 0)}
            for choice in data.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    text.append(delta["content"])
                    on_event("text", delta["content"])
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["args"] += fn.get("arguments") or ""
        tool_calls = []
        for _, slot in sorted(calls.items()):
            call = {"id": slot["id"] or "call_" + uuid.uuid4().hex[:10], "name": slot["name"],
                    "arguments": _args(slot["args"])}
            tool_calls.append(call)
            on_event("tool_call", call)
        return {"text": "".join(text), "tool_calls": tool_calls, "usage": usage}


# ------------------------------------------------------- OpenAI Responses
class OpenAIResponses(Adapter):
    """Responses-API (OpenAI und "Sign in with ChatGPT")."""

    @staticmethod
    def convert(messages: list[dict]) -> list[dict]:
        items: list[dict] = []
        for m in messages:
            role = m["role"]
            if role == "user":
                parts = [{"type": "input_text", "text": m.get("content", "")}]
                for img in m.get("images") or []:
                    parts.append({"type": "input_image", "image_url": f"data:{img['mime']};base64,{img['data']}"})
                items.append({"role": "user", "content": parts})
            elif role == "assistant":
                if m.get("content"):
                    items.append({"role": "assistant", "content": [{"type": "output_text", "text": m["content"]}]})
                for c in m.get("tool_calls") or []:
                    items.append({"type": "function_call", "call_id": c["id"], "name": c["name"],
                                  "arguments": json.dumps(c.get("arguments") or {})})
            elif role == "tool":
                items.append({"type": "function_call_output", "call_id": m["tool_call_id"],
                              "output": m.get("content", "")})
        return items

    def chat(self, system, messages, tools, on_event, stop, state=None):
        system = self.rules(system)
        body: dict = {"model": self.conn.model, "input": self.convert(messages), "stream": True, "store": False}
        if system:
            body["instructions"] = system
        if tools:
            body["tools"] = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                              "parameters": t.get("parameters", {"type": "object", "properties": {}})}
                             for t in tools]
        text, tool_calls, usage, completed = [], [], {}, False
        for event, data in aihttp.sse(self.url("/responses"), self.headers(), body, stop):
            if not isinstance(data, dict):
                continue
            kind = data.get("type") or event
            if kind == "response.output_text.delta":
                text.append(data.get("delta", ""))
                on_event("text", data.get("delta", ""))
            elif kind == "response.output_item.done":
                item = data.get("item") or {}
                if item.get("type") == "function_call":
                    call = {"id": item.get("call_id") or item.get("id"), "name": item.get("name", ""),
                            "arguments": _args(item.get("arguments", ""))}
                    tool_calls.append(call)
                    on_event("tool_call", call)
            elif kind == "response.completed":
                completed = True
                u = (data.get("response") or {}).get("usage") or {}
                usage = {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0)}
            elif kind in ("response.failed", "error", "response.incomplete"):
                err = (data.get("response") or {}).get("error") or data.get("error") or data
                code = str(err.get("code", "")) if isinstance(err, dict) else ""
                msg = err.get("message", kind) if isinstance(err, dict) else str(err)
                limit = code.startswith("subscription_sharing_usage")
                raise AIError(msg, "limit" if limit else "server", code=code)
        if not completed:
            raise AIError("stream ended early", "network", code="incomplete")
        return {"text": "".join(text), "tool_calls": tool_calls, "usage": usage}


# --------------------------------------------------------------- Anthropic
class Anthropic(Adapter):
    VERSION = "2023-06-01"

    def headers(self, interactive: bool = True) -> dict:
        h = {"anthropic-version": self.VERSION}
        if self.conn.auth in (providers.AUTH_CUSTOM,):
            h["Authorization"] = "Bearer " + oauth.access_token(self.store, self.conn)
        elif self.conn.auth != providers.AUTH_NONE:
            h["x-api-key"] = self.store.api_key(self.conn, interactive=interactive)
        return h

    @staticmethod
    def convert(messages: list[dict]) -> list[dict]:
        out: list[dict] = []

        def add(role: str, block: dict) -> None:
            if out and out[-1]["role"] == role:
                out[-1]["content"].append(block)
            else:
                out.append({"role": role, "content": [block]})

        for m in messages:
            role = m["role"]
            if role == "user":
                for img in m.get("images") or []:
                    add("user", {"type": "image", "source": {"type": "base64", "media_type": img["mime"],
                                                             "data": img["data"]}})
                add("user", {"type": "text", "text": m.get("content") or " "})
            elif role == "assistant":
                if m.get("content"):
                    add("assistant", {"type": "text", "text": m["content"]})
                for c in m.get("tool_calls") or []:
                    add("assistant", {"type": "tool_use", "id": c["id"], "name": c["name"],
                                      "input": c.get("arguments") or {}})
            elif role == "tool":
                add("user", {"type": "tool_result", "tool_use_id": m["tool_call_id"],
                             "content": m.get("content", "")})
        return out

    def chat(self, system, messages, tools, on_event, stop, state=None):
        system = self.rules(system)
        body: dict = {"model": self.conn.model, "max_tokens": 8192, "messages": self.convert(messages),
                      "stream": True}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["name"], "description": t.get("description", ""),
                              "input_schema": t.get("parameters", {"type": "object", "properties": {}})}
                             for t in tools]
        text, blocks, usage = [], {}, {"input": 0, "output": 0}
        for event, data in aihttp.sse(self.url("/messages"), self.headers(), body, stop):
            if not isinstance(data, dict):
                continue
            kind = data.get("type") or event
            if kind == "message_start":
                u = (data.get("message") or {}).get("usage") or {}
                usage["input"] = u.get("input_tokens", 0)
            elif kind == "content_block_start":
                block = data.get("content_block") or {}
                if block.get("type") == "tool_use":
                    blocks[data.get("index", 0)] = {"id": block.get("id"), "name": block.get("name"), "json": ""}
            elif kind == "content_block_delta":
                delta = data.get("delta") or {}
                if delta.get("type") == "text_delta":
                    text.append(delta.get("text", ""))
                    on_event("text", delta.get("text", ""))
                elif delta.get("type") == "input_json_delta" and data.get("index", 0) in blocks:
                    blocks[data["index"]]["json"] += delta.get("partial_json", "")
            elif kind == "message_delta":
                usage["output"] = ((data.get("usage") or {}).get("output_tokens", usage["output"]))
            elif kind == "error":
                err = data.get("error") or {}
                etype = err.get("type", "")
                raise AIError(err.get("message", "error"), "limit" if etype == "rate_limit_error" else "server",
                              code=etype)
        tool_calls = []
        for _, b in sorted(blocks.items()):
            call = {"id": b["id"], "name": b["name"], "arguments": _args(b["json"])}
            tool_calls.append(call)
            on_event("tool_call", call)
        return {"text": "".join(text), "tool_calls": tool_calls, "usage": usage}


# ------------------------------------------------------ Microsoft 365 Copilot
class GraphCopilot(Adapter):
    """Microsoft 365 Copilot Chat API (Vorschau): nur Text, keine Funktionsaufrufe."""

    supports_tools = False

    def list_models(self, interactive: bool = True) -> list[str]:
        return []

    def test(self) -> str:
        aihttp.json_request("POST", self.url("/copilot/conversations"), self.headers(), body={})
        return ""

    def chat(self, system, messages, tools, on_event, stop, state=None):
        system = self.rules(system)
        state = state if state is not None else {}
        headers = self.headers()
        conv = state.get("copilot_conversation")
        prompt = messages[-1].get("content", "") if messages else ""
        if not conv:
            conv = aihttp.json_request("POST", self.url("/copilot/conversations"), headers, body={}).get("id")
            state["copilot_conversation"] = conv
            # Neue Unterhaltung: bisherigen Verlauf und Anweisungen als Kontext voranstellen
            history = "\n".join(f"{m['role']}: {m.get('content', '')}" for m in messages[:-1]
                                if m["role"] in ("user", "assistant") and m.get("content"))
            prefix = "\n\n".join(x for x in (system, history) if x)
            if prefix:
                prompt = f"{prefix}\n\nuser: {prompt}"
        if stop.is_set():
            raise aihttp.Cancelled()
        data = aihttp.json_request("POST", self.url(f"/copilot/conversations/{conv}/chat"), headers,
                                   body={"message": {"text": prompt}, "locationHint": {"timeZone": "UTC"}},
                                   timeout=180)
        reply = ""
        for msg in reversed(data.get("messages") or []):
            if msg.get("text") and msg.get("text") != prompt:
                reply = msg["text"]
                break
        on_event("text", reply)
        return {"text": reply, "tool_calls": [], "usage": {}}


ADAPTERS = {"openai": OpenAIChat, "openai_responses": OpenAIResponses, "anthropic": Anthropic,
            "graph_copilot": GraphCopilot}


def for_connection(store: ConnectionStore, conn: Connection) -> Adapter:
    info = conn.info
    if info and info.removed:
        raise AIError(info.status_note or "removed", "removed", code=info.status_note)
    cls = ADAPTERS.get(conn.api)
    if cls is None:
        raise AIError(f"no chat api {conn.api}", "request", code="no_chat")
    return cls(store, conn)
