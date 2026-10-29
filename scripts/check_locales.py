"""Prüft die Sprachdateien auf Vollständigkeit.

    python scripts/check_locales.py               # Hauptprogramm
    python scripts/check_locales.py tools/<tool>  # ein Tool

Hauptprogramm: Alle tr("…")-Schlüssel im Code müssen in en.json stehen. Für jede andere
Sprache werden fehlende Schlüssel aufgelistet (die greifen dann auf den Fallback zurück).
Tool: Vergleicht alle locales/*.json mit en.json und der config.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench.core.categories import translation_keys as category_keys  # noqa: E402
KEY_PATTERN = re.compile(r"""\btr\(\s*["']([a-z0-9_]+(?:\.[a-z0-9_]+)+)["']""")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def placeholders(text: str) -> set[str]:
    # {{Vorlagen-Platzhalter}} sind übersetzter Text, keine Format-Platzhalter
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    return set(re.findall(r"\{(\w+)\}", text))


def compare(locales_dir: Path, required: set[str]) -> int:
    problems = 0
    en = load(locales_dir / "en.json")
    missing_en = sorted(required - set(en))
    if missing_en:
        problems += len(missing_en)
        print(f"en.json: {len(missing_en)} fehlende Schlüssel:")
        for k in missing_en:
            print("   ", k)
    reference = (set(en) | required) - {"_meta"}
    for path in sorted(locales_dir.glob("*.json")):
        if path.stem == "en":
            continue
        data = load(path)
        missing = sorted(reference - set(data))
        extra = sorted(set(data) - reference - {"_meta"})
        wrong = [k for k in reference & set(data)
                 if k in en and isinstance(data[k], str) and placeholders(data[k]) != placeholders(en[k])]
        status = "OK" if not (missing or extra or wrong) else ""
        print(f"{path.name:16} {len(data) - 1:4} Texte  fehlend: {len(missing):3}  überzählig: {len(extra):3}  "
              f"Platzhalter falsch: {len(wrong):3}  {status}")
        for k in missing:
            print("      fehlt:", k)
        for k in extra:
            print("      überzählig:", k)
        for k in wrong:
            print(f"      Platzhalter: {k}  ({placeholders(en[k])} vs. {placeholders(data[k])})")
        problems += len(extra) + len(wrong)
    return problems


def app_keys() -> set[str]:
    keys: set[str] = set()
    for py in (ROOT / "omniwrench").rglob("*.py"):
        keys |= set(KEY_PATTERN.findall(py.read_text(encoding="utf-8")))
    # dynamisch zusammengesetzte Schlüssel
    keys |= {f"req.{k}" for k in ("python", "windows_capabilities", "windows_features", "powershell_modules", "winget")}
    keys |= {"install.installing", "install.updating", "login.title_unlock", "login.please_login"}
    keys |= category_keys()
    return keys


def tool_keys(tool_dir: Path) -> set[str]:
    keys: set[str] = set()
    for py in tool_dir.rglob("*.py"):
        keys |= set(KEY_PATTERN.findall(py.read_text(encoding="utf-8")))
    return keys


if __name__ == "__main__":
    if len(sys.argv) > 1:
        tool = Path(sys.argv[1])
        rc = compare(tool / "locales", tool_keys(tool))
    else:
        rc = compare(ROOT / "omniwrench" / "locales", app_keys())
    sys.exit(1 if rc else 0)
