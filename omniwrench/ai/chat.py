"""Ein Chatverlauf: Systemanweisung, Detailgrad, Funktionsaufrufe, Speichern.

Thread (thread.json):
    {"format": 1, "id", "title", "created", "updated", "project", "connection", "connection_name",
     "detail", "messages": [ {role, content, ts, connection_name, model, tool_calls, ...} ],
     "usage": {"<verbindung>": {"input", "output"}}, "state": {...}}
"""

from __future__ import annotations

import json
import logging
import platform
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from omniwrench import APP_NAME, VENDOR, __version__
from omniwrench.core.i18n import current_language, tr

from . import adapters, functions
from .connections import Connection, ConnectionStore
from .http import AIError, Cancelled

DETAILS = ("short", "normal", "detailed")
MAX_ROUNDS = 12
CONTEXT_CHARS = 200_000

_DETAIL_TEXT = {
    "short": "Answer as briefly as possible: a few sentences or a short list, no introduction.",
    "normal": "Answer clearly and to the point, with enough detail to act on.",
    "detailed": "Answer thoroughly: explain background, steps and alternatives where useful.",
}


def new_thread(conn: Connection | None, detail: str = "normal", project: str = "") -> dict:
    from .storage import Storage
    now = int(time.time())
    return {"format": 1, "id": Storage.new_id(), "title": "", "created": now, "updated": now,
            "project": project, "connection": conn.id if conn else "",
            "connection_name": conn.name if conn else "", "detail": detail, "messages": [],
            "usage": {}, "state": {}}


def make_title(text: str) -> str:
    line = " ".join(text.strip().split())
    return (line[:57] + "…") if len(line) > 60 else line


def thread_markdown(thread: dict) -> str:
    """Lesbare Fassung eines Chats (wird neben thread.json abgelegt)."""
    out = [f"# {thread.get('title') or tr('ai.chat.untitled')}", ""]
    for m in thread.get("messages", []):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(m.get("ts", 0))) if m.get("ts") else ""
        if m["role"] == "user":
            out += [f"## {tr('ai.chat.you')} · {when}", "", m.get("content", ""), ""]
        elif m["role"] == "assistant":
            who = m.get("connection_name") or tr("ai.chat.assistant")
            model = f" ({m['model']})" if m.get("model") else ""
            if m.get("content"):
                out += [f"## {who}{model} · {when}", "", m["content"], ""]
            for c in m.get("tool_calls") or []:
                out += [f"> ⚙ `{c['name']}` {json.dumps(c.get('arguments') or {}, ensure_ascii=False)}", ""]
        elif m["role"] == "error":
            out += [f"> ⚠ {m.get('content', '')}", ""]
    return "\n".join(out)


def system_prompt(detail: str, project: dict | None = None, extra: str = "") -> str:
    lang = current_language() or "en"
    parts = [
        f"You are the assistant built into {APP_NAME} {__version__} by {VENDOR}, a modular admin toolbox "
        f"for Windows clients and Linux. Users are system administrators.",
        f"Today is {time.strftime('%Y-%m-%d')}. The computer runs {platform.system()} {platform.release()}.",
        f"Reply in the user's language (program language: {lang}). Address the user formally and neutrally.",
        _DETAIL_TEXT.get(detail, _DETAIL_TEXT["normal"]),
        "Use the provided functions to look up facts about the program, its tools, the documentation "
        "and the connected systems instead of guessing. If a tool that would help is not installed or "
        "not connected, say so and explain how to install or connect it.",
        "Values like IP-1, HOST-2 or DOMAIN-1 are placeholders for real data that the program hides "
        "from you; use them as they are, the program translates them back for the user.",
    ]
    if project:
        parts.append(f"Project \"{project.get('name', '')}\":\n{project.get('instructions', '')}".strip())
    if extra:
        parts.append(extra)
    return "\n\n".join(p for p in parts if p)


def _trim(messages: list[dict]) -> list[dict]:
    """Älteste Nachrichten weglassen, bis der Verlauf ins Budget passt; Bilder nur in der letzten."""
    out, total = [], 0
    for i, m in enumerate(reversed(messages)):
        size = len(m.get("content") or "") + len(json.dumps(m.get("tool_calls") or []))
        if total + size > CONTEXT_CHARS and out:
            break
        total += size
        if i > 0 and m.get("images"):
            m = {k: v for k, v in m.items() if k != "images"}
        out.append(m)
    out.reverse()
    while out and out[0]["role"] == "tool":   # Antwort ohne zugehörigen Aufruf vermeiden
        out.pop(0)
    return out


def api_messages(thread: dict) -> list[dict]:
    keep = ("role", "content", "images", "tool_calls", "tool_call_id", "name")
    msgs = [{k: v for k, v in m.items() if k in keep} for m in thread.get("messages", [])
            if m["role"] in ("user", "assistant", "tool")]
    return _trim(msgs)


@dataclass
class RunHooks:
    """Rückrufe des Chat-Ablaufs (laufen im Hintergrund-Thread)."""
    on_text: Callable[[str], None] = lambda t: None               # Teiltext, noch nicht zurückübersetzt
    on_tool: Callable[[dict], None] = lambda c: None              # Aufruf angekündigt
    on_tool_done: Callable[[dict, str, bool], None] = lambda c, r, ok: None
    on_message: Callable[[dict], None] = lambda m: None           # Nachricht fertig im Verlauf
    confirm: Callable[[functions.Function, dict], bool] = lambda f, a: False
    level_for: Callable[[str], int] = lambda source: functions.LEVEL_DESCRIBE
    encode: Callable[[str], str] = lambda t: t                    # Verfremdung zum Assistenten hin
    decode: Callable[[str], str] = lambda t: t                    # Rückübersetzung
    # Funktionsergebnis -> Text für den Assistenten (Verfremdung je nach Einstellung der Quelle)
    encode_result: Callable[[str, Any], str] = lambda source, value: functions.format_result(value)
    call_context: functions.CallContext = field(default_factory=functions.CallContext)


def run(store: ConnectionStore, conn: Connection, thread: dict, system: str, hooks: RunHooks,
        stop: threading.Event) -> None:
    """Schickt den Verlauf (letzte Nachricht = Benutzer) ab und führt Funktionsaufrufe aus.

    Ergänzt thread["messages"] laufend. Fehler werden als Nachricht {"role": "error"} abgelegt
    und zusätzlich geworfen.
    """
    adapter = adapters.for_connection(store, conn)
    tools = functions.available(hooks.level_for) if adapter.supports_tools else []
    schemas = [f.schema() for f in tools]
    allowed = {f.name for f in tools}
    state = thread.setdefault("state", {})
    for _round in range(MAX_ROUNDS):
        msgs = api_messages(thread)
        enc = []
        for m in msgs:
            m = dict(m)
            # Funktionsergebnisse wurden beim Ausführen schon passend aufbereitet
            if m.get("content") and m["role"] != "tool":
                m["content"] = hooks.encode(m["content"])
            enc.append(m)
        result = adapter.chat(system, enc, schemas,
                              lambda kind, data: hooks.on_text(data) if kind == "text" else None,
                              stop, state)
        usage = thread.setdefault("usage", {}).setdefault(conn.id, {"input": 0, "output": 0})
        for k in ("input", "output"):
            usage[k] = usage.get(k, 0) + int((result.get("usage") or {}).get(k, 0) or 0)
        msg = {"role": "assistant", "content": hooks.decode(result.get("text", "")), "ts": int(time.time()),
               "connection": conn.id, "connection_name": conn.name, "model": conn.model}
        calls = result.get("tool_calls") or []
        if calls:
            msg["tool_calls"] = calls
        thread["messages"].append(msg)
        hooks.on_message(msg)
        if not calls:
            return
        for call in calls:
            if stop.is_set():
                raise Cancelled()
            hooks.on_tool(call)
            content, ok = _execute(call, allowed, hooks)
            tool_msg = {"role": "tool", "tool_call_id": call["id"], "name": call["name"], "content": content,
                        "ts": int(time.time())}
            thread["messages"].append(tool_msg)
            hooks.on_tool_done(call, content, ok)
    thread["messages"].append({"role": "error", "content": tr("ai.error.too_many_rounds"), "ts": int(time.time())})


def _execute(call: dict, allowed: set[str], hooks: RunHooks) -> tuple[str, bool]:
    fn = functions.get(call["name"])
    if fn is None or fn.name not in allowed:
        return f"Function {call['name']} is not available.", False
    # Platzhalter in den Argumenten zurückübersetzen, damit die Funktion echte Werte bekommt
    args = json.loads(hooks.decode(json.dumps(call.get("arguments") or {}, ensure_ascii=False)))
    if fn.confirm or fn.level >= functions.LEVEL_CHANGE:
        if not hooks.confirm(fn, args):
            return "The user declined this action.", False
    ctx = hooks.call_context
    ctx.level = hooks.level_for(fn.source)
    try:
        value = fn.handler(args, ctx)
    except Exception as err:  # noqa: BLE001 - Fehler geht als Text an den Assistenten
        logging.getLogger(__name__).info("Funktion %s fehlgeschlagen: %s", fn.name, err)
        return f"Error: {err}", False
    return hooks.encode_result(fn.source, value), True


def error_text(err: Exception) -> str:
    """Verständliche Meldung für die Oberfläche."""
    if isinstance(err, AIError):
        if err.kind == "removed":
            return tr("ai.error.removed", note=tr(f"ai.note.{err.code}") if err.code else "")
        if err.code == "missing_key":
            return tr("ai.error.missing_key")
        if err.code == "signed_out":
            return tr("ai.error.signed_out")
        if err.code.startswith("subscription_sharing_usage"):
            return tr("ai.error.chatgpt_limit")
        from . import models
        if models.is_model_error(err):
            return tr("ai.error.model_missing", detail=str(err))
        key = {"auth": "ai.error.auth", "limit": "ai.error.limit", "quota": "ai.error.quota",
               "network": "ai.error.network", "server": "ai.error.server"}.get(err.kind, "ai.error.request")
        return tr(key, detail=str(err))
    return tr("ai.error.request", detail=str(err) or err.__class__.__name__)
