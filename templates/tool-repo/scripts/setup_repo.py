"""Richtet ein neu aus der Vorlage erzeugtes Repository ein (läuft einmal per Workflow „Vorlage einrichten“).

    python scripts/setup_repo.py --owner meinefirma --repo dns-tools

- ersetzt die Platzhalter __OWNER__, __REPO__, __YEAR__ in README.md, LICENSE und docs/ und entfernt den
  Vorlagen-Hinweis aus der README
- legt das erste Tool an (ID <owner>.<repo>, Name = Repository-Name)
- entfernt die Markierung .github/template-setup.json (danach läuft der Workflow nicht mehr)

Den Store baut anschließend scripts/store.py build.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".github" / "template-setup.json"
sys.path.insert(0, str(ROOT / "scripts"))

from new_tool import create  # noqa: E402


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "tool"


def main(owner: str, repo: str) -> None:
    if not MARKER.is_file():
        print("Bereits eingerichtet.")
        return
    marker = json.loads(MARKER.read_text(encoding="utf-8"))
    if f"{owner}/{repo}".lower() == marker.get("template_repo", "").lower():
        print("Das ist das Vorlagen-Repository selbst - nichts zu tun.")
        return

    values = {"__OWNER__": owner, "__REPO__": repo, "__YEAR__": str(date.today().year)}
    files = [ROOT / "README.md", ROOT / "LICENSE", *(ROOT / "docs").glob("*.md")]
    for f in files:
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            text = re.sub(r"<!-- template:start -->.*?<!-- template:end -->\n+", "", text, flags=re.S)
            for key, value in values.items():
                text = text.replace(key, value)
            f.write_text(text, encoding="utf-8")

    name = re.sub(r"[-_]+", " ", repo).strip() or repo
    create(f"{slug(owner)}.{slug(repo)}", name, None, "other", owner, owner, repo)
    MARKER.unlink()
    print("Repository eingerichtet.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    main(args.owner, args.repo)
