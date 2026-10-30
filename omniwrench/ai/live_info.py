"""Alltagswissen für die Assistenten ohne Konto: Wetter (Open-Meteo) und Nachrichten (Google-News-RSS).

Beide Dienste brauchen keinen Schlüssel. Qt-frei; die Ergebnisse gehen als Funktionsergebnis an den Assistenten und
zusätzlich an angemeldete Zuhörer (z. B. die Anzeige von Mr. Zurkon), siehe add_listener().
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any, Callable

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NEWS_URL = "https://news.google.com/rss"

# WMO-Wettercodes (Open-Meteo) -> (Symbol, Art für die Anzeige, Text de, Text en)
WMO = {
    0: ("☀️", "clear", "klar", "clear sky"), 1: ("🌤️", "clear", "überwiegend klar", "mainly clear"),
    2: ("⛅", "cloudy", "teils bewölkt", "partly cloudy"), 3: ("☁️", "cloudy", "bedeckt", "overcast"),
    45: ("🌫️", "fog", "Nebel", "fog"), 48: ("🌫️", "fog", "Reifnebel", "rime fog"),
    51: ("🌦️", "rain", "leichter Nieselregen", "light drizzle"), 53: ("🌦️", "rain", "Nieselregen", "drizzle"),
    55: ("🌧️", "rain", "starker Nieselregen", "dense drizzle"),
    56: ("🌧️", "rain", "gefrierender Nieselregen", "freezing drizzle"),
    57: ("🌧️", "rain", "gefrierender Nieselregen", "freezing drizzle"),
    61: ("🌦️", "rain", "leichter Regen", "light rain"), 63: ("🌧️", "rain", "Regen", "rain"),
    65: ("🌧️", "rain", "starker Regen", "heavy rain"), 66: ("🌧️", "rain", "gefrierender Regen", "freezing rain"),
    67: ("🌧️", "rain", "gefrierender Regen", "freezing rain"),
    71: ("🌨️", "snow", "leichter Schneefall", "light snow"), 73: ("🌨️", "snow", "Schneefall", "snow"),
    75: ("❄️", "snow", "starker Schneefall", "heavy snow"), 77: ("🌨️", "snow", "Schneegriesel", "snow grains"),
    80: ("🌦️", "rain", "Regenschauer", "rain showers"), 81: ("🌧️", "rain", "Regenschauer", "rain showers"),
    82: ("⛈️", "storm", "heftige Regenschauer", "violent rain showers"),
    85: ("🌨️", "snow", "Schneeschauer", "snow showers"), 86: ("❄️", "snow", "starke Schneeschauer", "heavy snow showers"),
    95: ("⛈️", "storm", "Gewitter", "thunderstorm"), 96: ("⛈️", "storm", "Gewitter mit Hagel", "thunderstorm with hail"),
    99: ("⛈️", "storm", "Gewitter mit Hagel", "thunderstorm with hail"),
}

_listeners: list[Callable[[str, dict], None]] = []
_lock = threading.Lock()


def add_listener(fn: Callable[[str, dict], None]) -> None:
    """fn(kind, data) nach jedem erfolgreichen Abruf ("weather" / "news"); läuft im Hintergrund-Thread."""
    with _lock:
        if fn not in _listeners:
            _listeners.append(fn)


def remove_listener(fn) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)


def _notify(kind: str, data: dict) -> None:
    with _lock:
        listeners = list(_listeners)
    for fn in listeners:
        try:
            fn(kind, data)
        except Exception:  # noqa: BLE001 - eine defekte Anzeige darf die Antwort nicht verhindern
            pass


def _get(url: str, params: dict, timeout: int = 15) -> bytes:
    from omniwrench.core.net import _SSL, USER_AGENT
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as resp:
        return resp.read()


def describe(code: int, lang: str) -> tuple[str, str, str]:
    """WMO-Code -> (Symbol, Art, Text in der Sprache; Deutsch für de, sonst Englisch)."""
    icon, kind, de, en = WMO.get(int(code), ("🌡️", "cloudy", "unbekannt", "unknown"))
    return icon, kind, de if lang == "de" else en


def geocode(place: str, lang: str = "de") -> dict | None:
    data = json.loads(_get(GEO_URL, {"name": place, "count": 1, "language": lang or "en", "format": "json"}))
    hits = data.get("results") or []
    if not hits:
        return None
    h = hits[0]
    return {"name": h.get("name", place), "country": h.get("country", ""), "region": h.get("admin1", ""),
            "latitude": h["latitude"], "longitude": h["longitude"], "timezone": h.get("timezone", "auto")}


def weather(place: str, days: int = 3, lang: str = "de") -> dict:
    """Aktuelles Wetter und Vorhersage (bis 7 Tage) für einen Ort."""
    loc = geocode(place, lang)
    if loc is None:
        return {"error": f"Place '{place}' not found."}
    days = max(1, min(7, int(days or 3)))
    data = json.loads(_get(FORECAST_URL, {
        "latitude": loc["latitude"], "longitude": loc["longitude"], "timezone": loc["timezone"] or "auto",
        "forecast_days": days,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                 "precipitation_sum,sunrise,sunset"}))
    cur = data.get("current") or {}
    icon, kind, text = describe(cur.get("weather_code", 0), lang)
    out = {"place": loc["name"], "region": loc["region"], "country": loc["country"],
           "current": {"temperature": cur.get("temperature_2m"), "feels_like": cur.get("apparent_temperature"),
                       "humidity": cur.get("relative_humidity_2m"), "wind_kmh": cur.get("wind_speed_10m"),
                       "condition": text, "icon": icon, "kind": kind, "is_day": bool(cur.get("is_day", 1)),
                       "time": cur.get("time", "")},
           "days": [], "source": "Open-Meteo.com"}
    d = data.get("daily") or {}
    for i, date in enumerate(d.get("time") or []):
        di, dk, dt = describe((d.get("weather_code") or [0])[i], lang)
        out["days"].append({"date": date, "condition": dt, "icon": di, "kind": dk,
                            "max": (d.get("temperature_2m_max") or [None])[i],
                            "min": (d.get("temperature_2m_min") or [None])[i],
                            "rain_chance": (d.get("precipitation_probability_max") or [None])[i],
                            "rain_mm": (d.get("precipitation_sum") or [None])[i]})
    _notify("weather", out)
    return out


def _region(lang: str) -> tuple[str, str]:
    """Sprache -> (hl, gl) für Google News."""
    country = {"de": "DE", "en": "US", "fr": "FR", "es": "ES", "it": "IT", "nl": "NL", "pl": "PL", "pt": "BR",
               "ru": "RU", "tr": "TR", "uk": "UA", "cs": "CZ", "sv": "SE", "da": "DK", "fi": "FI", "hu": "HU",
               "ja": "JP", "ko": "KR", "zh": "CN"}.get(lang, "US")
    return (lang if lang in ("de", "fr", "es", "it", "nl", "pl", "ru", "tr", "uk", "cs", "sv", "da", "fi", "hu",
                             "ja", "ko") else {"pt": "pt-BR", "zh": "zh-CN"}.get(lang, "en-US")), country


def news(topic: str = "", lang: str = "de", limit: int = 8) -> dict:
    """Aktuelle Schlagzeilen (Google News), optional zu einem Thema."""
    hl, gl = _region(lang)
    params = {"hl": hl, "gl": gl, "ceid": f"{gl}:{hl.split('-')[0]}"}
    url = NEWS_URL
    if topic.strip():
        url += "/search"
        params["q"] = topic.strip()
    root = ET.fromstring(_get(url, params))
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        source = (it.findtext("source") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        when = ""
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone().strftime("%d.%m. %H:%M")
        except (TypeError, ValueError):
            pass
        items.append({"title": title, "source": source, "time": when, "link": (it.findtext("link") or "").strip()})
        if len(items) >= max(1, min(20, int(limit or 8))):
            break
    out = {"topic": topic.strip(), "items": items, "source": "Google News"}
    _notify("news", out)
    return out


def register_functions() -> None:
    """Wetter und Nachrichten als Funktionen des Hauptprogramms (Stufe „Beschreibung“: keine Programmdaten)."""
    from omniwrench.core.i18n import current_language

    from .functions import LEVEL_DESCRIBE, Function, register

    def lang() -> str:
        return (current_language() or "en").split("_")[0].split("-")[0]

    def get_weather(args: dict, ctx) -> Any:
        place = str(args.get("place", "")).strip()
        if not place:
            return {"error": "No place given. Ask the user for the place."}
        return weather(place, int(args.get("days") or 3), lang())

    def get_news(args: dict, ctx) -> Any:
        return news(str(args.get("topic", "")), lang(), int(args.get("limit") or 8))

    obj = lambda props, req=None: {"type": "object", "properties": props, "required": req or []}  # noqa: E731
    register(Function("get_weather", "Current weather and forecast (up to 7 days) for a place, from Open-Meteo. "
                      "Use it whenever the user asks about the weather.", get_weather,
                      obj({"place": {"type": "string", "description": "City or place, e.g. 'Munich'"},
                           "days": {"type": "integer", "description": "Forecast days 1-7 (default 3)"}}, ["place"]),
                      source="app", level=LEVEL_DESCRIBE))
    register(Function("get_news", "Current news headlines (Google News), optionally about a topic. Use it whenever "
                      "the user asks for news or current events.", get_news,
                      obj({"topic": {"type": "string", "description": "Optional topic or search words"},
                           "limit": {"type": "integer", "description": "Number of headlines (default 8)"}}),
                      source="app", level=LEVEL_DESCRIBE))
