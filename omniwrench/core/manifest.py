"""Tool-Paketformat.

Jedes Tool ist ein Ordner (bzw. ZIP) mit mindestens diesen Dateien:

    tool.json    Metadaten  (Anzeigename, Beschreibung, Kategoriepfad, Version, Voraussetzungen ...)
    config.json  Einstellungen (Schema + Standardwerte der tool-spezifischen Einstellungen)
    install.py   Installationsroutine (check / install / uninstall)
    <entry>.py   Python-Modul mit der Tool-Klasse (siehe omniwrench.sdk.ToolBase)

Details: docs/TOOL_ENTWICKLUNG.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .i18n import app_chain, load_locales, tr
from .jsonio import read_json

METADATA_FILE = "tool.json"
CONFIG_FILE = "config.json"
INSTALL_FILE = "install.py"
LOCALES_DIR = "locales"

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")

SETTING_TYPES = {
    "string", "text", "int", "float", "bool", "choice",
    "path_file", "path_dir", "secret", "credential", "certificate",
}


class ManifestError(Exception):
    pass


@dataclass
class Requirements:
    python: list[str] = field(default_factory=list)              # pip-Pakete, z. B. "ldap3>=2.9"
    windows_capabilities: list[str] = field(default_factory=list)  # z. B. "Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0"
    windows_features: list[str] = field(default_factory=list)      # Server-Features / optionale Features
    powershell_modules: list[str] = field(default_factory=list)    # PSGallery-Module
    winget: list[str] = field(default_factory=list)                # winget-Paket-IDs

    @classmethod
    def from_dict(cls, data: dict | None) -> "Requirements":
        data = data or {}
        return cls(**{k: list(data.get(k, [])) for k in cls.__dataclass_fields__})

    def is_empty(self) -> bool:
        return not any(getattr(self, k) for k in self.__dataclass_fields__)

    def summary(self) -> list[str]:
        return [f"{tr('req.' + k)}: {item}" for k in self.__dataclass_fields__ for item in getattr(self, k)]


@dataclass
class ToolManifest:
    id: str
    name: str
    version: str
    description: str = ""
    long_description: str = ""
    author: str = ""
    category: str = ""                   # Pfad mit "/", z. B. "Network/IP Tools" (übersetzbar)
    icon: str = ""                       # Bilddatei im Tool-Ordner ODER Name aus der Bibliothek (siehe core/icons.py)
    icon_text: str = ""                  # eigenes Kürzel für das generierte Symbol (max. 4 Zeichen)
    icon_data: str = ""                  # nur im Store: eingebettete Bilddatei (Base64), von build_store.py erzeugt
    color: str = ""                      # Akzentfarbe für die Kachel, z. B. "#3b82f6"
    entry: str = "tool:Tool"             # "<modul>:<Klasse>"
    min_app_version: str = "0.0.0"
    platforms: list[str] = field(default_factory=lambda: ["windows"])
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    single_instance: bool = False        # nur ein Tab gleichzeitig erlaubt
    requirements: Requirements = field(default_factory=Requirements)
    # Übersetzungen der Anzeigetexte: {"de": {"name": …, "description": …, "category": …}, …}
    # Installiert: aus locales/*.json ("tool.name", …), im Store: aus index.json
    translations: dict = field(default_factory=dict)
    # Nur im Store-Katalog vorhanden:
    download_url: str = ""
    sha256: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    def localized(self, field_name: str, chain: list[str] | None = None) -> str:
        """Übersetzter Anzeigetext (name, description, long_description, category)."""
        if chain is None:
            chain = app_chain()
        for code in chain:
            text = self.translations.get(code, {}).get(field_name)
            if text:
                return text
        return getattr(self, field_name)

    @property
    def display_name(self) -> str:
        return self.localized("name")

    @property
    def display_description(self) -> str:
        return self.localized("description")

    @property
    def display_long_description(self) -> str:
        return self.localized("long_description") or self.display_description

    @property
    def category_path(self) -> list[str]:
        """Kategoriepfad in der Sprache des Hauptprogramms."""
        return _split_category(self.localized("category"))

    @classmethod
    def from_dict(cls, data: dict) -> "ToolManifest":
        missing = [k for k in ("id", "name", "version") if not data.get(k)]
        if missing:
            raise ManifestError(tr("err.manifest_fields", fields=", ".join(missing)))
        if not ID_PATTERN.match(data["id"]):
            raise ManifestError(tr("err.manifest_bad_id", id=data["id"]))
        kwargs: dict[str, Any] = {}
        for name in cls.__dataclass_fields__:
            if name in ("requirements", "raw"):
                continue
            if name in data:
                kwargs[name] = data[name]
        return cls(**kwargs, requirements=Requirements.from_dict(data.get("requirements")), raw=data)

    @classmethod
    def load(cls, tool_dir: Path) -> "ToolManifest":
        data = read_json(tool_dir / METADATA_FILE)
        if data is None:
            raise ManifestError(tr("err.manifest_missing", file=METADATA_FILE, path=tool_dir))
        manifest = cls.from_dict(data)
        manifest.translations = read_tool_translations(tool_dir)
        return manifest


TRANSLATABLE_FIELDS = ("name", "description", "long_description", "category")


def read_tool_translations(tool_dir: Path) -> dict[str, dict[str, str]]:
    """Liest "tool.name", "tool.description" … aus <tool>/locales/*.json."""
    result: dict[str, dict[str, str]] = {}
    for code, table in load_locales(tool_dir / LOCALES_DIR).items():
        entry = {f: table[f"tool.{f}"] for f in TRANSLATABLE_FIELDS if isinstance(table.get(f"tool.{f}"), str)}
        if entry:
            result[code] = entry
    return result


def _split_category(category: str) -> list[str]:
    return [p.strip() for p in category.split("/") if p.strip()] or [tr("category.other")]


@dataclass
class SettingDef:
    key: str
    type: str
    label: str
    default: Any = None
    description: str = ""
    group: str = ""                      # leer = "Allgemein" (übersetzt)
    options: list = field(default_factory=list)  # für "choice": ["a", "b"] oder [{"value":..., "label":...}]
    min: float | None = None
    max: float | None = None
    placeholder: str = ""
    required: bool = False

    @property
    def is_secret(self) -> bool:
        return self.type in ("secret", "credential")


def load_settings_schema(tool_dir: Path) -> list[SettingDef]:
    data = read_json(tool_dir / CONFIG_FILE, default={}) or {}
    result = []
    for item in data.get("settings", []):
        if item.get("type") not in SETTING_TYPES:
            raise ManifestError(tr("err.setting_type", type=item.get("type"), path=tool_dir / CONFIG_FILE))
        fields = SettingDef.__dataclass_fields__
        result.append(SettingDef(**{k: v for k, v in item.items() if k in fields}))
    return result


def validate_package(tool_dir: Path) -> ToolManifest:
    """Prüft einen entpackten Tool-Ordner auf Vollständigkeit."""
    manifest = ToolManifest.load(tool_dir)
    for required in (CONFIG_FILE, INSTALL_FILE):
        if not (tool_dir / required).exists():
            raise ManifestError(tr("err.package_file_missing", file=required, id=manifest.id))
    module = manifest.entry.split(":", 1)[0]
    if not (tool_dir / f"{module.replace('.', '/')}.py").exists() and not (tool_dir / module).is_dir():
        raise ManifestError(tr("err.package_entry_missing", module=module, id=manifest.id))
    load_settings_schema(tool_dir)
    return manifest
