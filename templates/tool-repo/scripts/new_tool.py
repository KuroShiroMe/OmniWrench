"""Legt ein neues Tool aus der Vorlage an.

    python scripts/new_tool.py --id meinefirma.dns-cleanup --name "DNS Cleanup"
    python scripts/new_tool.py --id meinefirma.dns-cleanup --name "DNS Cleanup" --category network --author "Meine Firma"

Erzeugt tools/<ordner>/ aus template/tool/ und die Doku-Seite docs/Tool-<Name>.md aus template/Tool-Seite.md.
Der Ordnername ergibt sich aus dem letzten Teil der ID (dns-cleanup -> dns_cleanup), wenn --folder fehlt.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
AREAS = ("workplace", "identity", "network", "infrastructure", "cloud", "security", "applications",
         "operations", "servicedesk", "automation", "documentation", "other")
TEXT_SUFFIXES = {".json", ".py", ".md", ".txt", ".ps1"}


def git_remote() -> tuple[str, str] | None:
    """(owner, repo) aus dem GitHub-Remote 'origin', falls vorhanden."""
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    return (m.group(1), m.group(2)) if m else None


def page_name(name: str) -> str:
    return "Tool-" + re.sub(r"[^\w]+", "-", name, flags=re.UNICODE).strip("-")


def create(tool_id: str, name: str, folder: str | None, category: str, author: str | None,
           owner: str | None = None, repo: str | None = None) -> Path:
    if not ID_PATTERN.match(tool_id):
        sys.exit(f"Ungültige ID '{tool_id}': nur a-z, 0-9, Punkt, Bindestrich, Unterstrich.")
    if category not in AREAS:
        print(f"Hinweis: '{category}' ist kein fester Bereich ({', '.join(AREAS)}). "
              "Für einen eigenen Bereich 'category_area' in tool.json ergänzen.")
    folder = folder or tool_id.rsplit(".", 1)[-1].replace("-", "_")
    target = ROOT / "tools" / folder
    if target.exists():
        sys.exit(f"{target.relative_to(ROOT)} gibt es bereits.")
    remote = (owner, repo) if owner and repo else git_remote()
    page = page_name(name)
    homepage = f"https://github.com/{remote[0]}/{remote[1]}/blob/main/docs/{page}.md" if remote else ""
    values = {
        "__TOOL_ID__": tool_id,
        "__TOOL_NAME__": name,
        "__TOOL_FOLDER__": folder,
        "__AUTHOR__": author or (remote[0] if remote else ""),
        "__HOMEPAGE__": homepage,
        "__CATEGORY__": category,
        "__OWNER__": remote[0] if remote else "<owner>",
        "__REPO__": remote[1] if remote else "<repo>",
    }

    shutil.copytree(TEMPLATE / "tool", target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    page_file = docs / f"{page}.md"
    if not page_file.exists():
        shutil.copy(TEMPLATE / "Tool-Seite.md", page_file)
    for f in [*target.rglob("*"), page_file]:
        if f.is_file() and f.suffix in TEXT_SUFFIXES:
            text = f.read_text(encoding="utf-8")
            for key, value in values.items():
                text = text.replace(key, value)
            f.write_text(text, encoding="utf-8")
    print(f"Angelegt: tools/{folder}/ und docs/{page}.md")
    return target


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="eindeutige Tool-ID, z. B. meinefirma.dns-cleanup")
    ap.add_argument("--name", required=True, help="Anzeigename, z. B. \"DNS Cleanup\"")
    ap.add_argument("--folder", help="Ordnername unter tools/ (Standard aus der ID)")
    ap.add_argument("--category", default="other", help="Bereich, z. B. network (Standard: other)")
    ap.add_argument("--author", help="Autor (Standard: GitHub-Besitzer des Repositorys)")
    args = ap.parse_args()
    create(args.id, args.name, args.folder, args.category, args.author)
