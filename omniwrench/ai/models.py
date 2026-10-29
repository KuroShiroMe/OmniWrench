"""Modelle einer Verbindung: abfragen, zwischenspeichern, erklären.

Der Katalog (providers.json "models") nennt empfohlene Modelle, die aber veralten. Deshalb fragt die
Chatleiste die Liste beim Anbieter ab (GET /models) und merkt sie sich in den Einstellungen
("ai_model_cache", je Verbindung, MAX_AGE). Daraus entsteht die Auswahl im Chat:

* status "ok"       vom Anbieter gemeldet
* status "missing"  steht im Katalog/war eingestellt, meldet der Anbieter aber nicht (mehr)
* status "unknown"  Liste nicht abrufbar (z. B. Anbieter ohne /models), nichts bekannt

Erklärungen sind kurze Merkmale (tags), aus dem Modellnamen abgeleitet oder im Katalog gesetzt
("model_tags": {"<modell>": ["top", …]}); Texte unter ai.model.tag.<tag>.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .connections import Connection

CACHE_KEY = "ai_model_cache"
MAX_AGE = 12 * 3600

TAGS = ("top", "balanced", "fast", "light", "reasoning", "code", "vision", "free", "preview")

# Modelle, die nicht chatten (Einbettungen, Sprache, Bilder …): im Chat unter „Weitere Modelle“
_NOT_CHAT = re.compile(r"embed|tts|whisper|transcri|dall-e|imagen|image|veo|lyria|moderation|rerank|audio|"
                       r"realtime|speech|aqa|ocr|sora|music|video|guard|clip|stable-diffusion|flux")

_RULES: tuple[tuple[str, re.Pattern], ...] = (
    ("top", re.compile(r"(^|[-_.])(pro|opus|ultra|max|large|astra|argon|fable)([-_.]|$)")),
    ("balanced", re.compile(r"(^|[-_.])(sonnet|medium|plus|sol)([-_.]|$)")),
    ("fast", re.compile(r"flash|turbo|(^|[-_.])(fast|instant|terra)([-_.]|$)")),
    ("light", re.compile(r"(^|[-_.])(lite|nano|haiku|mini|small|tiny|luna|[1-9]b|1[0-4]b)([-_.]|$)")),
    ("reasoning", re.compile(r"reason|think|(^|[-_/])(o\d|r1|qwq)([-_.]|$)")),
    ("code", re.compile(r"code|coder|codestral|devstral")),
    ("vision", re.compile(r"vision|(^|[-_.])vl([-_.]|$)|pixtral")),
    ("preview", re.compile(r"preview|(^|[-_.])exp(erimental)?([-_.]|$)|beta")),
)


def is_chat_model(model_id: str) -> bool:
    return not _NOT_CHAT.search(model_id.lower())


def tags(model_id: str, conn: Connection | None = None) -> list[str]:
    """Merkmale eines Modells (Reihenfolge wie TAGS)."""
    info = conn.info if conn else None
    explicit = (getattr(info, "model_tags", None) or {}).get(model_id) if info else None
    if explicit is not None:
        return [t for t in TAGS if t in explicit]
    name = model_id.lower().rsplit("/", 1)[-1]
    found = {tag for tag, rx in _RULES if rx.search(name.split(":")[0])}
    if name.endswith(":free"):
        found.add("free")
    if "light" in found and "top" in found:   # z. B. "pro-mini": das kleinere Merkmal gewinnt
        found.discard("top")
    return [t for t in TAGS if t in found]


@dataclass
class ModelChoice:
    id: str
    status: str = "unknown"                  # ok | missing | unknown
    tags: list[str] = field(default_factory=list)
    recommended: bool = False                # erstes verfügbares Katalogmodell
    other: bool = False                      # kein Chatmodell (Einbettung, Bild …)


# ------------------------------------------------------------------ Cache
def cached(settings, conn_id: str) -> dict | None:
    """{"ts", "models": [...], "error"} oder None."""
    entry = (settings.get(CACHE_KEY) or {}).get(conn_id)
    return entry if isinstance(entry, dict) else None


def cached_models(settings, conn_id: str) -> list[str] | None:
    """Vom Anbieter gemeldete Modelle, None wenn unbekannt (nie abgefragt, Fehler oder leer)."""
    entry = cached(settings, conn_id)
    models = entry.get("models") if entry else None
    return list(models) if models else None


def is_stale(settings, conn_id: str, max_age: int = MAX_AGE) -> bool:
    entry = cached(settings, conn_id)
    return not entry or time.time() - float(entry.get("ts", 0)) > max_age


def store(settings, conn_id: str, models: list[str] | None, error: str = "") -> None:
    data = dict(settings.get(CACHE_KEY) or {})
    data[conn_id] = {"ts": int(time.time()), "models": sorted(set(models or [])), "error": error}
    settings.set(CACHE_KEY, data)


def forget(settings, conn_id: str) -> None:
    data = dict(settings.get(CACHE_KEY) or {})
    if data.pop(conn_id, None) is not None:
        settings.set(CACHE_KEY, data)


# --------------------------------------------------------------- Auswahl
def choices(conn: Connection, available: list[str] | None) -> list[ModelChoice]:
    """Auswahlliste für den Chat: Katalog-Reihenfolge zuerst, dann der Rest des Anbieters."""
    info = conn.info
    catalog = list(dict.fromkeys((info.models if info else []) + list(conn.models)))
    out: list[ModelChoice] = []
    seen: set[str] = set()

    def add(mid: str, status: str, other: bool = False) -> None:
        if mid and mid not in seen:
            seen.add(mid)
            out.append(ModelChoice(mid, status, tags(mid, conn), other=other))

    if available is None:
        for m in catalog + [conn.model]:
            add(m, "unknown")
    else:
        have = set(available)
        for m in catalog:
            if m in have:
                add(m, "ok")
        for m in sorted(have, key=str.lower):
            if is_chat_model(m):
                add(m, "ok")
        for m in sorted(have, key=str.lower):
            add(m, "ok", other=True)
        for m in catalog + [conn.model]:
            add(m, "missing")
    first = next((c for c in out if c.id in catalog and c.status != "missing"), None)
    if first:
        first.recommended = True
    return out


def best(conn: Connection, available: list[str] | None) -> str:
    """Bestes Modell, wenn das eingestellte fehlt: erstes verfügbares Katalogmodell, sonst erstes Chatmodell."""
    if available is None or conn.model in (available or []):
        return conn.model
    for c in choices(conn, available):
        if c.status == "ok" and not c.other:
            return c.id
    return conn.model


_MODEL_ERROR = re.compile(r"model[^\n]{0,80}(not[ _]found|does not exist|not supported|unknown|invalid|"
                          r"not available|no access|deprecated|decommissioned)|model_not_found|unknown model",
                          re.IGNORECASE)


def is_model_error(err: Exception) -> bool:
    """Meldet der Anbieter, dass es das eingestellte Modell nicht (mehr) gibt?"""
    status = getattr(err, "status", 0)
    code = str(getattr(err, "code", "") or "")
    if code in ("model_not_found", "invalid_model"):
        return True
    return status in (400, 404) and bool(_MODEL_ERROR.search(str(err)))
