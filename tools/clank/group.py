"""Gruppenchat: mehrere Assistenten besprechen ein Thema der Reihe nach – mit Bremsen.

Ohne Qt, damit der Ablauf testbar bleibt; die Oberfläche steht in grouptab.py.

Bremsen (alle in den Optionen einstellbar): Runden, Nachrichten insgesamt, Länge je Beitrag (Hinweis an den
Assistenten und hartes Abschneiden), Zeitlimit, Token-Budget, Pause nach jeder Runde, Ende bei Einigkeit
(alle Teilnehmer einer Runde setzen [DONE]), Ende bei Wiederholung. Funktionsaufrufe gibt es im Gruppenchat
nicht. Gespeichert wird unter <Chats>/groups/<id>/thread.(json|owai) (+ .md), verschlüsselt wie Chats.

Thread: {"format": 1, "kind": "group", "id", "title", "created", "updated", "topic",
         "participants": [{"id", "connection", "name", "role"}], "options": {...},
         "messages": [{"role": "user"|"assistant"|"brake"|"error", "content", "ts", "participant", "name", ...}],
         "usage": {}, "state": {"pseudo": {...}}}
"""

from __future__ import annotations

import difflib
import random
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

DONE_MARK = "[DONE]"
MODES = ("discussion", "brainstorm", "debate", "review")
ORDERS = ("fixed", "random")
DEFAULTS: dict[str, Any] = {
    "mode": "discussion", "order": "fixed", "detail": "normal", "rounds": 3, "max_messages": 12,
    "max_chars": 1500, "time_limit": 10, "token_budget": 40000, "pause_each_round": False,
    "stop_on_agree": True, "stop_on_repeat": True, "summary": True,
}
LIMITS = {"rounds": (1, 30), "max_messages": (1, 200), "max_chars": (200, 20000), "time_limit": (1, 240),
          "token_budget": (1000, 2_000_000)}
MAX_PARTICIPANTS = 6
REPEAT_RATIO = 0.9
REPEAT_MIN = 60

_MODE_TEXT = {
    "discussion": "Discuss the topic with the other participants. Build on what they said, point out "
                  "disagreements and work towards a useful result.",
    "brainstorm": "Brainstorm: contribute new ideas, avoid repeating ideas already mentioned, briefly build on "
                  "good ideas of others.",
    "debate": "Debate: argue clearly for your assigned position, answer the strongest argument of the others "
              "and stay factual.",
    "review": "Review: examine the material critically, name concrete problems and improvements, and say "
              "where you agree with the other reviewers.",
}
_DETAIL = {"short": "Keep each contribution very short.", "normal": "Keep each contribution focused.",
           "detailed": "Contributions may be detailed where it helps."}


def options(raw: dict | None) -> dict:
    """Optionen mit Standardwerten und Grenzen."""
    out = dict(DEFAULTS)
    for k, v in (raw or {}).items():
        if k not in DEFAULTS:
            continue
        if isinstance(DEFAULTS[k], bool):
            out[k] = bool(v)
        elif isinstance(DEFAULTS[k], int):
            try:
                lo, hi = LIMITS.get(k, (0, 10**9))
                out[k] = max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                pass
        elif k == "mode" and v in MODES or k == "order" and v in ORDERS or k == "detail" and v in (
                "short", "normal", "detailed"):
            out[k] = v
    return out


def new_thread(topic: str, participants: list[dict], opts: dict) -> dict:
    now = int(time.time())
    title = " ".join(topic.split())
    return {"format": 1, "kind": "group", "id": time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2),
            "title": (title[:57] + "…") if len(title) > 60 else title, "created": now, "updated": now,
            "topic": topic, "participants": [dict(p) for p in participants], "options": options(opts),
            "messages": [{"role": "user", "content": topic, "ts": now}], "usage": {}, "state": {}}


def new_participant(conn_id: str, name: str, role: str = "") -> dict:
    return {"id": secrets.token_hex(3), "connection": conn_id, "name": name, "role": role}


def markdown(thread: dict, you: str = "You") -> str:
    out = [f"# {thread.get('title', '')}", ""]
    for p in thread.get("participants", []):
        out.append(f"- **{p['name']}**" + (f": {p['role']}" if p.get("role") else ""))
    out.append("")
    for m in thread.get("messages", []):
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(m.get("ts", 0))) if m.get("ts") else ""
        if m["role"] == "user":
            out += [f"## {you} · {when}", "", m.get("content", ""), ""]
        elif m["role"] == "assistant":
            out += [f"## {m.get('name', '')} · {when}", "", m.get("content", ""), ""]
        else:
            out += [f"> {m.get('content', '')}", ""]
    return "\n".join(out)


# ------------------------------------------------------------------ Ablage
class GroupStore:
    def __init__(self, storage):
        self.storage = storage

    def base(self) -> Path:
        return self.storage.path("chats") / "groups"

    def doc(self, gid: str) -> Path:
        return self.base() / gid / "thread"

    def save(self, thread: dict, you: str = "You") -> None:
        thread["updated"] = int(time.time())
        self.storage.write_doc(self.doc(thread["id"]), thread, markdown(thread, you))

    def load(self, gid: str) -> dict | None:
        try:
            return self.storage.read_doc(self.doc(gid))
        except Exception:
            return None

    def delete(self, gid: str) -> None:
        import shutil
        shutil.rmtree(self.base() / gid, ignore_errors=True)

    def list(self) -> list[dict]:
        out = []
        base = self.base()
        if not base.is_dir():
            return out
        for d in base.iterdir():
            if not d.is_dir() or not self.storage.doc_exists(d / "thread"):
                continue
            try:
                t = self.storage.read_doc(d / "thread") or {}
            except Exception:
                t = {"title": d.name, "updated": int(d.stat().st_mtime), "locked": True}
            out.append({"id": t.get("id") or d.name, "title": t.get("title") or d.name,
                        "updated": t.get("updated") or 0, "locked": t.get("locked", False)})
        out.sort(key=lambda t: t["updated"], reverse=True)
        return out


# ------------------------------------------------------------------ Ablauf
class Stopped(Exception):
    pass


@dataclass
class GroupHooks:
    """Rückrufe (laufen im Hintergrund-Thread)."""
    on_turn: Callable[[dict], None] = lambda participant: None
    on_text: Callable[[str, str], None] = lambda pid, delta: None
    on_message: Callable[[dict], None] = lambda msg: None
    pause: Callable[[int], bool] = lambda round_no: True          # False = beenden
    pending_user: Callable[[], list[str]] = lambda: []            # Einwürfe des Benutzers
    encode: Callable[[str], str] = lambda t: t
    decode: Callable[[str], str] = lambda t: t
    clock: Callable[[], float] = time.monotonic


def system_for(thread: dict, me: dict, opts: dict, summary: bool = False) -> str:
    others = [p for p in thread["participants"] if p["id"] != me["id"]]
    lines = [
        f"You are \"{me['name']}\", one of {len(thread['participants'])} AI participants in a moderated group "
        "chat inside OmniWrench (admin toolbox). The user is the moderator.",
        "Other participants: " + (", ".join(f"{p['name']}" + (f" ({p['role']})" if p.get("role") else "")
                                             for p in others) or "none") + ".",
        "Messages of others reach you as \"[Name]: text\". Write only your own contribution, without a name "
        "prefix, in the user's language, formally and neutrally.",
    ]
    if me.get("role"):
        lines.append(f"Your role: {me['role']}")
    if summary:
        lines.append("The discussion is over. Summarize the result for the moderator: agreed points, open "
                     "disagreements and recommended next steps. Be concise.")
    else:
        lines.append(_MODE_TEXT.get(opts["mode"], _MODE_TEXT["discussion"]))
        lines.append(_DETAIL.get(opts["detail"], "") + f" Never exceed {opts['max_chars']} characters.")
        if opts["stop_on_agree"]:
            lines.append(f"If you think the group has reached a good result and nothing important is left, end "
                         f"your contribution with {DONE_MARK}.")
    lines.append("Values like IP-1, HOST-2 or DOMAIN-1 are placeholders for hidden real data; use them as they are.")
    return "\n".join(lines)


def messages_for(thread: dict, me: dict, encode: Callable[[str], str], summary: bool = False) -> list[dict]:
    """Verlauf aus Sicht eines Teilnehmers: eigene Beiträge = assistant, alles andere = user."""
    out: list[dict] = []

    def add(role: str, text: str) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})

    for m in thread["messages"]:
        if m["role"] == "user":
            add("user", "[Moderator]: " + encode(m.get("content", "")))
        elif m["role"] == "assistant" and m.get("content"):
            if m.get("participant") == me["id"]:
                add("assistant", encode(m["content"]))
            else:
                add("user", f"[{m.get('name', '?')}]: " + encode(m["content"]))
    if out and out[0]["role"] == "assistant":
        out.insert(0, {"role": "user", "content": "[Moderator]: " + encode(thread.get("topic", ""))})
    if not out or out[-1]["role"] == "assistant":
        add("user", "[Moderator]: Please write your summary." if summary else "[Moderator]: Please continue.")
    return out


RATE_RETRIES = 3
RATE_WAIT_MAX = 90.0


def rate_wait(err: str) -> tuple[float, int] | None:
    """Minuten-/Anfragelimit (429) mit Wartezeit? -> (Sekunden, Limit je Minute oder 0); None = echter Fehler.
    Kein Warten bei aufgebrauchtem Guthaben oder Funktion nicht im Tarif („limit: 0“)."""
    low = err.lower()
    if "limit: 0," in low or any(w in low for w in ("credit", "balance")):
        return None
    if not any(w in low for w in ("429", "rate limit", "rate-limit", "quota", "too many requests", "per minute",
                                  "resource_exhausted", "retry in")):
        return None
    if "per day" in low or "perday" in low or "daily" in low:
        return None
    m = re.search(r"retry in ([\d.]+)\s*s", low) or re.search(r"retry[- ]after[\"': ]+([\d.]+)", low)
    seconds = float(m.group(1)) + 1 if m else 20.0
    if seconds > RATE_WAIT_MAX:
        return None
    lim = re.search(r"limit: (\d+)", low)
    per_minute = int(lim.group(1)) if lim and "minute" in low else 0
    return seconds, per_minute


def _similar(a: str, b: str) -> bool:
    """Fast gleicher Beitrag wie der vorige desselben Teilnehmers (kurze Antworten zählen nicht)."""
    return min(len(a), len(b)) >= REPEAT_MIN and difflib.SequenceMatcher(None, a[:4000], b[:4000]).ratio() >= REPEAT_RATIO


class GroupRun:
    """Führt den Gruppenchat aus. chat_fn(participant, system, messages, on_text, stop) -> {"text", "usage"}."""

    def __init__(self, thread: dict, chat_fn: Callable[..., dict], hooks: GroupHooks, stop: threading.Event):
        self.thread = thread
        self.chat_fn = chat_fn
        self.hooks = hooks
        self.stop = stop
        self.opts = options(thread.get("options"))
        self.start = hooks.clock()
        self.spoken = 0
        self.gap: dict[str, float] = {}           # Verbindung -> Mindestabstand (s), gelernt aus Minutenlimits
        self.last_call: dict[str, float] = {}

    # Bremsen ------------------------------------------------------------------------------------------
    def tokens(self) -> int:
        return sum(int(u.get("input", 0)) + int(u.get("output", 0)) for u in (self.thread.get("usage") or {}).values())

    def brake(self) -> str:
        o = self.opts
        if self.spoken >= o["max_messages"]:
            return "max_messages"
        if self.hooks.clock() - self.start >= o["time_limit"] * 60:
            return "time_limit"
        if self.tokens() >= o["token_budget"]:
            return "token_budget"
        return ""

    def _note(self, reason: str, **extra) -> None:
        msg = {"role": "brake", "content": reason, "ts": int(time.time()), **extra}
        self.thread["messages"].append(msg)
        self.hooks.on_message(msg)

    def _take_user(self) -> None:
        for text in self.hooks.pending_user():
            msg = {"role": "user", "content": text, "ts": int(time.time())}
            self.thread["messages"].append(msg)
            self.hooks.on_message(msg)

    # Ablauf -------------------------------------------------------------------------------------------
    def run(self) -> str:
        """Gibt den Grund des Endes zurück (rounds, max_messages, agree, repeat, stopped, …)."""
        parts = [p for p in self.thread["participants"]]
        if not parts:
            return "no_participants"
        o = self.opts
        reason = "rounds"
        try:
            for rnd in range(1, o["rounds"] + 1):
                order = list(parts)
                if o["order"] == "random":
                    random.shuffle(order)
                agreed = 0
                for p in order:
                    self._take_user()
                    why = self.brake()
                    if why:
                        raise _Brake(why)
                    msg = self.turn(p)
                    if msg.get("agree"):
                        agreed += 1
                    if o["stop_on_repeat"] and msg.get("repeat"):
                        raise _Brake("repeat", msg.get("name", ""))
                if o["stop_on_agree"] and agreed == len(order):
                    reason = "agree"
                    break
                if rnd < o["rounds"] and o["pause_each_round"]:
                    self._note("pause", round=rnd)
                    if not self.hooks.pause(rnd):
                        reason = "stopped"
                        break
                    self._take_user()
        except _Brake as b:
            reason = b.reason
            if reason != "stopped":
                self._note(reason, who=b.who)
        except Stopped:
            return "stopped"
        if reason in ("agree", "rounds"):
            self._note(reason)
        if self.stop.is_set():
            return "stopped"
        if o["summary"] and reason != "stopped" and parts:
            try:
                self.turn(parts[0], summary=True)
            except Stopped:
                return "stopped"
        return reason

    def turn(self, p: dict, summary: bool = False) -> dict:
        if self.stop.is_set():
            raise Stopped()
        self.hooks.on_turn(p)
        o = self.opts
        system = system_for(self.thread, p, o, summary)
        msgs = messages_for(self.thread, p, self.hooks.encode, summary)
        turn_stop = threading.Event()
        buf: list[str] = []
        limit = int(o["max_chars"] * 1.2) if not summary else max(4000, o["max_chars"] * 2)
        cut = False

        def on_text(delta: str) -> None:
            nonlocal cut
            if self.stop.is_set():
                turn_stop.set()
                return
            buf.append(delta)
            self.hooks.on_text(p["id"], delta)
            if sum(len(x) for x in buf) > limit:
                cut = True
                turn_stop.set()

        result = self._call(p, system, msgs, on_text, turn_stop, buf, lambda: cut)
        usage = self.thread.setdefault("usage", {}).setdefault(p["connection"], {"input": 0, "output": 0})
        for k in ("input", "output"):
            usage[k] = usage.get(k, 0) + int((result.get("usage") or {}).get(k, 0) or 0)
        text = self.hooks.decode(result.get("text") or "".join(buf)).strip()
        if cut:
            text = text[:limit].rstrip() + " …"
        agree = DONE_MARK in text
        text = text.replace(DONE_MARK, "").strip()
        prev = next((m.get("content", "") for m in reversed(self.thread["messages"])
                     if m["role"] == "assistant" and m.get("participant") == p["id"]), "")
        msg = {"role": "assistant", "content": text, "ts": int(time.time()), "participant": p["id"],
               "name": p["name"], "connection": p["connection"]}
        if summary:
            msg["summary"] = True
        if agree:
            msg["agree"] = True
        if cut:
            msg["cut"] = True
        if not summary and _similar(text, prev):
            msg["repeat"] = True
        self.thread["messages"].append(msg)
        if not summary:
            self.spoken += 1
        self.hooks.on_message(msg)
        return msg


    def _wait(self, seconds: float) -> None:
        if seconds > 0 and self.stop.wait(seconds):
            raise Stopped()

    def _call(self, p, system, msgs, on_text, turn_stop, buf, was_cut) -> dict:
        """Ein Beitrag. Bei Minutenlimits warten und wiederholen; danach Abstand für diese Verbindung halten."""
        conn = p.get("connection", "")
        for attempt in range(RATE_RETRIES + 1):
            gap = self.gap.get(conn, 0.0)
            if gap and conn in self.last_call:
                self._wait(self.last_call[conn] + gap - time.monotonic())
            self.last_call[conn] = time.monotonic()
            try:
                return self.chat_fn(p, system, msgs, on_text, turn_stop) or {}
            except Exception as err:
                if self.stop.is_set():
                    raise Stopped() from None
                if was_cut():
                    return {"text": "".join(buf)}
                hit = None if buf or attempt == RATE_RETRIES else rate_wait(str(err))
                if hit is None:
                    raise
                seconds, per_minute = hit
                if per_minute:
                    self.gap[conn] = max(self.gap.get(conn, 0.0), 60.0 / per_minute + 0.5)
                self._note("wait", who=p.get("name", ""), seconds=int(round(seconds)))
                self._wait(seconds)
        return {}


class _Brake(Exception):
    def __init__(self, reason: str, who: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.who = who
