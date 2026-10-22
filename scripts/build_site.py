"""Füllt die Tool-Liste der Landing Page (site/index.html) aus dem Store-Katalog.

    python scripts/build_site.py           # schreibt site/index.html neu
    python scripts/build_site.py --check   # Exitcode 1, wenn site/index.html nicht aktuell ist

Die Tools werden nach Service-Bereichen gruppiert (alphabetisch und mit deutschen Namen wie im Store).
Jeder Eintrag verlinkt auf die Wiki-Seite des Tools ("homepage" in tool.json, sonst Tool-<Name>).
Läuft auch im Pages-Workflow vor dem Veröffentlichen, neue Tools erscheinen also automatisch.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench.core.categories import AREAS, OTHER  # noqa: E402

SITE = ROOT / "site" / "index.html"
INDEX = ROOT / "store" / "index.json"
LOCALE = ROOT / "omniwrench" / "locales" / "de.json"
WIKI = "https://github.com/KuroShiroMe/OmniWrench/wiki"
START, END = "<!-- TOOLS:START -->", "<!-- TOOLS:END -->"
PLATFORMS = {"windows": "Windows", "linux": "Linux"}


def wiki_link(entry: dict, name: str) -> str:
    homepage = entry.get("homepage") or ""
    if homepage.startswith(WIKI):
        return homepage
    return f"{WIKI}/Tool-" + re.sub(r"\s+", "-", name.strip())


def render() -> str:
    tools = json.loads(INDEX.read_text(encoding="utf-8"))["tools"]
    labels = json.loads(LOCALE.read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = {}
    for entry in tools:
        area = (entry.get("category") or OTHER).split("/")[0].strip().lower()
        groups.setdefault(area if area in AREAS else OTHER, []).append(entry)

    def label(area: str) -> str:
        return labels.get(f"category.area.{area}" if area != OTHER else "category.other", area)

    lines = [START]
    # Alphabetisch wie im Store, "Sonstiges" zuletzt
    for area in sorted(groups, key=lambda a: (a == OTHER, label(a).lower())):
        entries = groups[area]
        lines.append('        <details class="cat">')
        lines.append(f'          <summary><span>{html.escape(label(area))}</span>'
                     f'<small>{len(entries)} Tool{"s" if len(entries) != 1 else ""}</small></summary>')
        lines.append('          <ul>')
        rows = []
        for entry in entries:
            de = (entry.get("translations") or {}).get("de") or {}
            name = de.get("name") or entry["name"]
            desc = de.get("description") or entry.get("description") or ""
            platforms = " · ".join(PLATFORMS.get(p, p) for p in entry.get("platforms") or ["windows"])
            rows.append((name.lower(), f'            <li><a href="{html.escape(wiki_link(entry, name))}">'
                                       f'<b>{html.escape(name)}</b><span>{html.escape(desc)}</span>'
                                       f'<em>{html.escape(platforms)}</em></a></li>'))
        lines += [row for _, row in sorted(rows)]
        lines.append('          </ul>')
        lines.append('        </details>')
    lines.append(f"        {END}")
    return "\n".join(lines)


def main() -> int:
    page = SITE.read_text(encoding="utf-8")
    start, end = page.index(START), page.index(END) + len(END)
    new = page[:start] + render() + page[end:]
    if "--check" in sys.argv:
        if new != page:
            print("site/index.html ist nicht aktuell: python scripts/build_site.py ausführen", file=sys.stderr)
            return 1
        return 0
    SITE.write_text(new, encoding="utf-8", newline="\n")
    print("site/index.html aktualisiert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
