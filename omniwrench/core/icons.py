"""Symbole für Tools.

In der tool.json bestimmen zwei Felder das Symbol:

    "icon":      Bilddatei im Tool-Ordner ("icon.png", "assets/logo.svg")
                 ODER Name aus der eingebauten Bibliothek Lucide ("server", "lucide:network")
    "icon_text": eigenes Kürzel für das generierte Symbol (z. B. "AD"), max. 4 Zeichen

Ohne beides werden die Anfangsbuchstaben des Namens verwendet.
Übersicht aller Bibliotheks-Symbole: Hilfe › Symbol-Bibliothek bzw. https://lucide.dev/icons
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .paths import RESOURCES_DIR

LIBRARY_DIR = RESOURCES_DIR / "icons" / "lucide"
LIBRARY_PREFIX = "lucide:"
IMAGE_SUFFIXES = {".png", ".svg", ".ico", ".jpg", ".jpeg", ".bmp", ".webp"}
MAX_TEXT = 4


@dataclass(frozen=True)
class IconSpec:
    kind: str           # "file" | "library" | "data" | "text"
    value: str          # Pfad, Bibliotheksname, Base64-Daten oder Text


@lru_cache(maxsize=1)
def library_names() -> tuple[str, ...]:
    if not LIBRARY_DIR.is_dir():
        return ()
    return tuple(sorted(p.stem for p in LIBRARY_DIR.glob("*.svg")))


def library_path(name: str) -> Path | None:
    name = name.removeprefix(LIBRARY_PREFIX).strip().lower()
    path = LIBRARY_DIR / f"{name}.svg"
    return path if name and path.exists() else None


@lru_cache(maxsize=512)
def library_svg(name: str) -> bytes | None:
    path = library_path(name)
    return path.read_bytes() if path else None


@lru_cache(maxsize=1)
def library_meta() -> dict:
    """Schlagwörter/Kategorien der Bibliothek (meta.json, erzeugt von scripts/update_icons.py)."""
    path = LIBRARY_DIR / "meta.json"
    if not path.exists():
        return {"categories": {}, "icons": {}, "version": "", "license": "ISC", "source": "https://lucide.dev"}
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def library_info(name: str) -> dict:
    """{"tags": [...], "categories": [...]} eines Bibliotheks-Symbols."""
    return library_meta()["icons"].get(name, {"tags": [], "categories": []})


def library_categories() -> dict[str, str]:
    """Kategorie-ID -> Anzeigename."""
    return {k: v.get("title", k) for k, v in library_meta()["categories"].items()}


def library_version() -> str:
    path = LIBRARY_DIR / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else library_meta().get("version", "")


def initials(name: str) -> str:
    words = [w for w in name.replace("-", " ").replace("_", " ").split() if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "?").upper()


def resolve(icon: str, icon_text: str, display_name: str, tool_dir: Path | None = None,
            icon_data: str = "") -> IconSpec:
    """Ermittelt, welches Symbol angezeigt wird (Reihenfolge: Datei, Store-Daten, Bibliothek, Kürzel, Initialen)."""
    icon = (icon or "").strip()
    if icon:
        is_file_ref = Path(icon).suffix.lower() in IMAGE_SUFFIXES
        if is_file_ref and tool_dir is not None and (tool_dir / icon).is_file():
            return IconSpec("file", str(tool_dir / icon))
        if is_file_ref and icon_data:
            return IconSpec("data", icon_data)
        if not is_file_ref and library_path(icon):
            return IconSpec("library", icon.removeprefix(LIBRARY_PREFIX).lower())
    if icon_text.strip():
        return IconSpec("text", icon_text.strip()[:MAX_TEXT])
    return IconSpec("text", initials(display_name))
