"""Prüft, ob store/ zu tools/ passt (für CI und vor dem Commit).

    python scripts/check_store.py

Für jedes Tool in tools/ muss store/index.json einen Eintrag mit derselben Version haben,
das ZIP muss existieren, sha256 und Größe müssen stimmen und der Inhalt des ZIPs muss den
Dateien im Tool-Ordner entsprechen. Wurde ein Tool geändert, ohne die Version zu erhöhen und
den Store neu zu bauen (scripts/build_store.py), schlägt die Prüfung fehl.
Zeilenenden (CRLF/LF) werden beim Inhaltsvergleich ignoriert.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench.core.manifest import validate_package  # noqa: E402
from scripts.build_store import EXCLUDE_DIRS, EXCLUDE_SUFFIXES  # noqa: E402


def normalized(data: bytes) -> bytes:
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def tool_files(tool_dir: Path) -> dict[str, bytes]:
    files = {}
    for f in sorted(tool_dir.rglob("*")):
        rel = f.relative_to(tool_dir)
        if f.is_dir() or EXCLUDE_DIRS.intersection(rel.parts) or f.suffix in EXCLUDE_SUFFIXES:
            continue
        files[rel.as_posix()] = normalized(f.read_bytes())
    return files


def check(tools_dir: Path, store_dir: Path) -> list[str]:
    problems: list[str] = []
    index = json.loads((store_dir / "index.json").read_text(encoding="utf-8"))
    entries = {e["id"]: e for e in index.get("tools", [])}
    seen: set[str] = set()

    for tool_dir in sorted(p for p in tools_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        manifest = validate_package(tool_dir)
        seen.add(manifest.id)
        label = f"{manifest.id} ({tool_dir.name})"
        entry = entries.get(manifest.id)
        if not entry:
            problems.append(f"{label}: fehlt in store/index.json")
            continue
        if entry.get("version") != manifest.version:
            problems.append(f"{label}: tool.json {manifest.version}, Store {entry.get('version')}")
            continue
        zip_path = store_dir / entry.get("download_url", "")
        if not zip_path.is_file():
            problems.append(f"{label}: ZIP fehlt ({entry.get('download_url')})")
            continue
        data = zip_path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            problems.append(f"{label}: sha256 in index.json passt nicht zum ZIP")
        if len(data) != entry.get("size"):
            problems.append(f"{label}: Größe in index.json passt nicht zum ZIP")
        with zipfile.ZipFile(zip_path) as zf:
            packed = {n: normalized(zf.read(n)) for n in zf.namelist() if not n.endswith("/")}
        local = tool_files(tool_dir)
        changed = sorted(n for n in packed.keys() & local.keys() if packed[n] != local[n])
        only_local = sorted(local.keys() - packed.keys())
        only_zip = sorted(packed.keys() - local.keys())
        if changed or only_local or only_zip:
            problems.append(f"{label}: Tool geändert, aber Version nicht erhöht bzw. Store nicht neu gebaut")
            problems += [f"    geändert: {n}" for n in changed]
            problems += [f"    neu: {n}" for n in only_local]
            problems += [f"    entfernt: {n}" for n in only_zip]

    for tool_id in sorted(entries.keys() - seen):
        problems.append(f"{tool_id}: steht in store/index.json, aber nicht in tools/")
    return problems


if __name__ == "__main__":
    found = check(ROOT / "tools", ROOT / "store")
    for line in found:
        print(line)
    print("Store OK" if not found else f"{sum(not p.startswith(' ') for p in found)} Problem(e)")
    sys.exit(1 if found else 0)
