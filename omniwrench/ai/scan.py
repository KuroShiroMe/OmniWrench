"""Fähigkeiten einer Verbindung prüfen: was geht, mit welchen Modellen, wie viel Volumen ist noch da.

Was ein Anbieter verrät, ist sehr unterschiedlich:
* Modellliste (fast alle) -> welche Funktionen (Chat, Bilder, Musik, Video, Sprache) mit welchen Modellen möglich sind.
* Limits aus Antwort-Headern (x-ratelimit-*, anthropic-ratelimit-*; z. B. OpenAI, Groq, Anthropic, Mistral).
* Guthaben nur bei einigen (OpenRouter, DeepSeek, Moonshot, SiliconFlow). Google, OpenAI und Anthropic zeigen
  Verbrauch und Restguthaben nur auf ihrer Webseite (catalog "usage_url").
* Ob eine Funktion im Tarif enthalten ist (z. B. Gemini-Bilder nur mit Abrechnung), zeigt erst ein Versuch;
  der Katalog nennt dafür media.<art>.requires.

Ergebnis in den Einstellungen "ai_scan" {conn_id: {...}}, damit Clank es ohne neue Abfrage zeigen kann.
"""

from __future__ import annotations

import time

from . import http as aihttp
from . import media, models, speech
from .connections import Connection, ConnectionStore

SETTINGS_KEY = "ai_scan"
KINDS = ("chat", "image", "music", "video", "stt", "tts")

# Merkmale im Modellnamen je Medienart (für "steht in der Modellliste des Kontos")
_HINTS = {"image": ("image", "imagen", "dall", "flux", "banana", "seedream", "recraft", "ideogram"),
          "music": ("lyria", "music", "audio", "song"),
          "video": ("veo", "video", "omni", "sora", "kling", "hailuo", "seedance", "gen4", "ray")}


def _balance(store: ConnectionStore, conn: Connection, headers: dict) -> dict:
    """Guthaben/Verbrauch bei Anbietern, die es per Schnittstelle melden. {} = nicht verfügbar."""
    pid = conn.provider
    base = conn.url
    if pid == "openrouter":
        d = (aihttp.json_request("GET", "https://openrouter.ai/api/v1/key", headers, timeout=20) or {}).get("data") or {}
        out = {"usage": d.get("usage"), "limit": d.get("limit"), "remaining": d.get("limit_remaining"),
               "currency": "USD", "free_tier": d.get("is_free_tier")}
        try:
            c = (aihttp.json_request("GET", "https://openrouter.ai/api/v1/credits", headers, timeout=20)
                 or {}).get("data") or {}
            if c.get("total_credits") is not None:
                out["balance"] = round(float(c["total_credits"]) - float(c.get("total_usage") or 0), 4)
        except aihttp.AIError:
            pass
        return {k: v for k, v in out.items() if v is not None}
    if pid == "deepseek":
        d = aihttp.json_request("GET", "https://api.deepseek.com/user/balance", headers, timeout=20) or {}
        info = (d.get("balance_infos") or [{}])[0]
        return {"balance": info.get("total_balance"), "currency": info.get("currency", "")}
    if pid == "moonshot":
        d = (aihttp.json_request("GET", base + "/users/me/balance", headers, timeout=20) or {}).get("data") or {}
        return {"balance": d.get("available_balance"), "currency": "CNY" if ".cn" in base else "USD"}
    if pid == "siliconflow":
        d = (aihttp.json_request("GET", base + "/user/info", headers, timeout=20) or {}).get("data") or {}
        return {"balance": d.get("totalBalance") or d.get("balance"), "currency": "USD"}
    return {}


def parse_limits(raw: dict) -> dict:
    """Header-Limits vereinheitlichen: requests/tokens jeweils remaining/limit, reset."""
    out: dict = {}
    for key, value in raw.items():
        if key == "ts":
            continue
        k = key.replace("anthropic-ratelimit-", "").replace("x-ratelimit-", "").replace("ratelimit-", "")
        for what in ("requests", "tokens"):
            if what in k:
                if "remaining" in k:
                    out.setdefault(what, {})["remaining"] = value
                elif "limit" in k:
                    out.setdefault(what, {})["limit"] = value
                elif "reset" in k:
                    out.setdefault(what, {})["reset"] = value
    return out


def _kind_status(available: list[str] | None, catalog_models: list[str], kind: str) -> str:
    if available is None:
        return "unknown"
    have = set(available)
    if any(m in have for m in catalog_models):
        return "ok"
    hints = _HINTS.get(kind, ())
    if hints and any(any(h in m.lower() for h in hints) for m in available):
        return "ok"
    # Medienschnittstellen ohne eigene Modelleinträge in /models (z. B. Runway, BFL): nicht ableitbar
    return "unknown" if not hints or not any(available) else "missing"


def scan(store: ConnectionStore, conn: Connection) -> dict:
    """Prüft eine Verbindung (läuft im Hintergrund) und merkt sich das Ergebnis."""
    from . import adapters
    info = conn.info
    result: dict = {"ts": int(time.time()), "kinds": {}, "account": {}, "limits": {}, "errors": [],
                    "usage_url": getattr(info, "usage_url", "") if info else ""}
    available: list[str] | None = None
    headers: dict = {}
    if info is not None and info.can_chat:
        try:
            ad = adapters.for_connection(store, conn)
            headers = ad.headers()
            available = ad.list_models(interactive=True) or None
            models.store(store.settings, conn.id, available)
        except Exception as err:  # noqa: BLE001 - Ergebnis zeigt den Fehler
            result["errors"].append(str(err))
    result["models"] = len(available) if available is not None else None
    kinds = result["kinds"]
    if info is not None and info.can_chat:
        chat_models = [m for m in (available or []) if models.is_chat_model(m)]
        if available is not None:
            status = "ok" if chat_models else "missing"
        else:
            status = "error" if result["errors"] else "unknown"
        kinds["chat"] = {"status": status, "models": chat_models[:50] if available is not None else list(info.models),
                         "requires": info.requirement(conn.auth)}
    for kind in ("image", "music", "video"):
        if media.supports(conn, kind):
            cat = media.models(conn, kind)
            spec = ((info.media or {}).get(kind) or {}) if info else {}
            kinds[kind] = {"status": _kind_status(available, cat, kind), "models": cat,
                           "requires": spec.get("requires") or (info.requirement(conn.auth) if info else "")}
    if media.api_for(conn, "speech") in speech.STT_APIS:
        kinds["stt"] = {"status": "unknown", "models": speech.stt_models(conn), "requires": ""}
    if media.api_for(conn, "speech") in speech.TTS_APIS and speech.tts_models(conn):
        kinds["tts"] = {"status": "unknown", "models": speech.tts_models(conn), "requires": ""}
    if headers:
        try:
            result["account"] = {k: v for k, v in _balance(store, conn, headers).items() if v is not None}
        except Exception as err:  # noqa: BLE001
            result["errors"].append(str(err))
    result["limits"] = parse_limits(aihttp.limits_for(conn.url)) if conn.url else {}
    data = dict(store.settings.get(SETTINGS_KEY) or {})
    data[conn.id] = result
    store.settings.set(SETTINGS_KEY, data)
    return result


def last(settings, conn_id: str) -> dict | None:
    entry = (settings.get(SETTINGS_KEY) or {}).get(conn_id)
    return entry if isinstance(entry, dict) else None
