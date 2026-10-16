"""Mehrsprachigkeit.

Sprachdateien sind flache JSON-Dateien "<code>.json" mit Schlüssel -> Text:

    {
      "_meta": {"name": "German", "native": "Deutsch", "fallback": "en"},
      "home.title": "Meine Tools",
      "home.subtitle": "{count} Tool(s) installiert"
    }

* Platzhalter in {geschweiften Klammern} werden mit str.format ersetzt.
* "_meta.fallback" legt fest, welche Sprache für fehlende Schlüssel einspringt
  (z. B. Badisch -> Deutsch -> Englisch). Englisch ist immer die letzte Stufe.

Hauptprogramm:  omniwrench/locales/<code>.json
Tools:          <tool>/locales/<code>.json   (siehe docs/TOOL_ENTWICKLUNG.md)
"""

from __future__ import annotations

import json
import locale
import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

APP_LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"
DEFAULT_LANGUAGE = "en"
AUTO = "auto"


@dataclass(frozen=True)
class LanguageInfo:
    code: str
    name: str        # englischer Name
    native: str      # Name in der Sprache selbst
    fallback: str


def _read(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        log.warning("Sprachdatei %s ungültig: %s", path, exc)
        return {}


@lru_cache(maxsize=64)
def _load_dir(directory: str) -> dict[str, dict]:
    d = Path(directory)
    if not d.is_dir():
        return {}
    return {p.stem: _read(p) for p in sorted(d.glob("*.json"))}


def clear_cache() -> None:
    _load_dir.cache_clear()


def load_locales(directory: Path) -> dict[str, dict]:
    return _load_dir(str(directory))


def _sort_name(text: str) -> str:
    """Sortierschlüssel ohne Akzente ("Čeština" steht bei C, nicht hinter Z)."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()


def language_infos(directory: Path = APP_LOCALES_DIR) -> list[LanguageInfo]:
    result = []
    for code, data in load_locales(directory).items():
        meta = data.get("_meta", {})
        result.append(LanguageInfo(code, meta.get("name", code), meta.get("native", code),
                                   meta.get("fallback", DEFAULT_LANGUAGE)))
    return sorted(result, key=lambda i: (i.code != DEFAULT_LANGUAGE, _sort_name(i.native)))


def base_language(code: str) -> str:
    """Basissprache eines Dialekts ("de_bad" -> "de"); bei Hauptsprachen der Code selbst."""
    return code.split("_", 1)[0]


def language_tree(codes=None, directory: Path = APP_LOCALES_DIR) -> list[tuple[LanguageInfo, int]]:
    """Sprachen für Auswahllisten: jede Hauptsprache, darunter ihre Dialekte (Ebene 1).

    codes: nur diese Sprachcodes (z. B. die eines Tools); Namen kommen aus den Sprachdateien
    des Hauptprogramms. Ein Dialekt ohne vorhandene Basissprache steht auf Ebene 0.
    """
    infos = {i.code: i for i in language_infos(directory)}
    wanted = list(infos) if codes is None else list(dict.fromkeys(codes))
    items = [infos.get(c) or LanguageInfo(c, c, c, DEFAULT_LANGUAGE) for c in wanted]
    order = {i.code: n for n, i in enumerate(language_infos(directory))}
    key = lambda i: (order.get(i.code, len(order)), _sort_name(i.native))
    present = {i.code for i in items}
    top = sorted((i for i in items if base_language(i.code) == i.code or base_language(i.code) not in present),
                 key=key)
    result: list[tuple[LanguageInfo, int]] = []
    for parent in top:
        result.append((parent, 0))
        if base_language(parent.code) != parent.code:
            continue
        children = [i for i in items if i.code != parent.code and base_language(i.code) == parent.code]
        result.extend((child, 1) for child in sorted(children, key=lambda i: _sort_name(i.native)))
    return result


def fallback_chain(code: str, locales: dict[str, dict]) -> list[str]:
    """[code, fallback, fallback-des-fallbacks, …, "en"] - ohne Duplikate und Zyklen."""
    chain: list[str] = []
    current = code
    while current and current not in chain:
        chain.append(current)
        current = locales.get(current, {}).get("_meta", {}).get("fallback", DEFAULT_LANGUAGE)
    if DEFAULT_LANGUAGE not in chain:
        chain.append(DEFAULT_LANGUAGE)
    return chain


class Translator:
    def __init__(self, language: str, tables: list[dict]):
        self.language = language
        self._tables = tables

    def tr(self, key: str, default: str | None = None, **kwargs) -> str:
        for table in self._tables:
            text = table.get(key)
            if isinstance(text, str):
                break
        else:
            text = default if default is not None else key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                return text
        return text

    def has(self, key: str) -> bool:
        return any(key in t for t in self._tables)


def make_translator(language: str, directory: Path) -> Translator:
    locales = load_locales(directory)
    chain = fallback_chain(language, locales)
    return Translator(language, [locales[c] for c in chain if c in locales])


# ------------------------------------------------------------ Hauptprogramm
_app = Translator(DEFAULT_LANGUAGE, [])


def system_language() -> str:
    """Bestmögliche Sprache passend zur Windows-Anzeigesprache."""
    available = load_locales(APP_LOCALES_DIR)
    try:
        sys_code = (locale.getlocale()[0] or "").lower()
    except ValueError:
        sys_code = ""
    # "German_Germany" / "de_DE" -> "de"
    names = {
        "german": "de", "english": "en", "french": "fr", "spanish": "es",
        "italian": "it", "dutch": "nl", "polish": "pl", "portuguese": "pt",
        "czech": "cs", "swedish": "sv", "turkish": "tr", "ukrainian": "uk",
    }
    base = names.get(sys_code.split("_")[0], sys_code.split("_")[0][:2])
    return base if base in available else DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    global _app
    available = load_locales(APP_LOCALES_DIR)
    if not code or code not in available:
        code = system_language()
    _app = make_translator(code, APP_LOCALES_DIR)
    log.info("Sprache: %s", code)


def current_language() -> str:
    return _app.language


def tr(key: str, default: str | None = None, **kwargs) -> str:
    """Übersetzt einen Text des Hauptprogramms."""
    return _app.tr(key, default, **kwargs)


def app_chain() -> list[str]:
    return fallback_chain(_app.language, load_locales(APP_LOCALES_DIR))


# --------------------------------------------------------------------- Tools
def resolve_tool_language(available: set[str], setting: str | None) -> str:
    """Sprache für ein Tool bestimmen.

    1. explizit gewählte Sprache (falls vorhanden)
    2. "auto": Sprache des Hauptprogramms - bei Dialekten auch deren Basissprache
       (Badisch -> Deutsch), sofern das Tool sie mitbringt
    3. sonst Englisch
    """
    if setting and setting != AUTO and setting in available:
        return setting
    for code in app_chain():
        if code == DEFAULT_LANGUAGE:
            break
        if code in available:
            return code
    return DEFAULT_LANGUAGE


def tool_translator(tool_dir: Path, setting: str | None) -> Translator:
    """Übersetzer für ein Tool. Fehlende Schlüssel folgen der Fallback-Kette
    (z. B. Badisch -> Deutsch -> Englisch), soweit das Tool diese Sprachen mitbringt."""
    locales = load_locales(tool_dir / "locales")
    language = resolve_tool_language(set(locales), setting)
    app_locales = load_locales(APP_LOCALES_DIR)
    # Fallback-Angabe aus der Tool-Datei, sonst die des Hauptprogramms
    meta = {code: (locales[code] if "fallback" in locales.get(code, {}).get("_meta", {}) else app_locales.get(code, {}))
            for code in set(locales) | set(app_locales)}
    chain = fallback_chain(language, meta)
    return Translator(language, [locales[c] for c in chain if c in locales])


def native_name(code: str) -> str:
    for info in language_infos():
        if info.code == code:
            return info.native
    return code
