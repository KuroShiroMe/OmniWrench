"""Store dieses Repositorys prüfen und bauen.

    python scripts/store.py check            # alle Tools prüfen, nichts schreiben
    python scripts/store.py build            # geänderte Tools packen, store/index.json schreiben

Gebaut werden nur Tools, die neu sind oder deren Version sich geändert hat. Wurde ein Tool geändert,
ohne die Version in tool.json zu erhöhen, schlagen beide Befehle fehl: Installierte Clients würden die
Änderung sonst nie bekommen.

Benötigt den Quellcode von OmniWrench (für die Paketprüfung). Gesucht wird in dieser Reihenfolge:
--omniwrench PFAD, Umgebungsvariable OMNIWRENCH_SRC, ./.omniwrench, ../OmniWrench.
Im Workflow .github/workflows/store.yml wird er automatisch ausgecheckt.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
STORE = ROOT / "store"
EXCLUDE_DIRS = {"__pycache__", "_lib", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
# Feste Zeitstempel im ZIP: gleicher Inhalt ergibt dieselbe Prüfsumme
ZIP_DATE = (2020, 1, 1, 0, 0, 0)


def find_omniwrench(arg: str | None) -> Path:
    candidates = [arg, os.environ.get("OMNIWRENCH_SRC"), ROOT / ".omniwrench", ROOT.parent / "OmniWrench"]
    for c in candidates:
        if c and (Path(c) / "omniwrench" / "core" / "manifest.py").is_file():
            return Path(c).resolve()
    sys.exit("OmniWrench-Quellcode nicht gefunden. --omniwrench PFAD angeben oder OMNIWRENCH_SRC setzen "
             "(git clone https://github.com/KuroShiroMe/OmniWrench).")


def version_key(version: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[.+-]", version)[:3])


def normalized(data: bytes) -> bytes:
    return data if b"\0" in data else data.replace(b"\r\n", b"\n")


def tool_files(tool_dir: Path) -> dict[str, bytes]:
    files = {}
    for f in sorted(tool_dir.rglob("*")):
        rel = f.relative_to(tool_dir)
        if f.is_dir() or EXCLUDE_DIRS.intersection(rel.parts) or f.suffix in EXCLUDE_SUFFIXES:
            continue
        files[rel.as_posix()] = f.read_bytes()
    return files


def zip_files(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def same_content(a: dict[str, bytes], b: dict[str, bytes]) -> bool:
    return a.keys() == b.keys() and all(normalized(a[k]) == normalized(b[k]) for k in a)


def write_zip(path: Path, files: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            info = zipfile.ZipInfo(name, ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, normalized(data))


def run(mode: str, store_name: str | None, omniwrench: str | None) -> int:
    sys.path.insert(0, str(find_omniwrench(omniwrench)))
    from omniwrench.core.manifest import validate_package

    index_path = STORE / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    old = {e["id"]: e for e in index.get("tools", [])}
    name = store_name or index.get("name") or f"{ROOT.name} Store"

    problems: list[str] = []
    entries: list[dict] = []
    changed = name != index.get("name")
    seen: set[str] = set()

    tool_dirs = sorted(p for p in TOOLS.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))) \
        if TOOLS.is_dir() else []
    for tool_dir in tool_dirs:
        try:
            manifest = validate_package(tool_dir)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{tool_dir.name}: {exc}")
            continue
        if manifest.id in seen:
            problems.append(f"{tool_dir.name}: Tool-ID {manifest.id} kommt mehrfach vor")
            continue
        seen.add(manifest.id)
        files = tool_files(tool_dir)
        prev = old.get(manifest.id)
        prev_zip = STORE / prev["download_url"] if prev else None

        if prev and prev.get("version") == manifest.version and prev_zip and prev_zip.is_file():
            if same_content(files, zip_files(prev_zip)):
                entries.append(prev)
                print(f"  {manifest.id} {manifest.version}: unverändert")
            else:
                problems.append(f"{manifest.id}: geändert, aber Version {manifest.version} nicht erhöht (tool.json)")
            continue
        if prev and version_key(manifest.version) < version_key(prev.get("version", "0")):
            problems.append(f"{manifest.id}: Version {manifest.version} ist kleiner als im Store ({prev['version']})")
            continue

        zip_name = f"{manifest.id}-{manifest.version}.zip"
        print(f"  {manifest.id} {manifest.version}: wird gebaut -> store/packages/{zip_name}")
        changed = True
        if mode != "build":
            continue
        zip_path = STORE / "packages" / zip_name
        write_zip(zip_path, files)
        entry = dict(manifest.raw)
        icon_file = tool_dir / manifest.icon if manifest.icon else None
        if icon_file and icon_file.is_file():
            entry["icon_data"] = base64.b64encode(icon_file.read_bytes()).decode("ascii")
        if manifest.translations:
            entry["translations"] = manifest.translations
        entry["download_url"] = f"packages/{zip_name}"
        entry["sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        entry["size"] = zip_path.stat().st_size
        entries.append(entry)

    removed = set(old) - seen
    for tool_id in sorted(removed):
        print(f"  {tool_id}: entfernt")
        changed = True

    if problems:
        print("\nFehler:\n- " + "\n- ".join(problems))
        return 1
    if mode == "build" and changed:
        used = {e["download_url"] for e in entries}
        for z in (STORE / "packages").glob("*.zip") if (STORE / "packages").is_dir() else []:
            if f"packages/{z.name}" not in used:
                z.unlink()
        index = {"format": 1, "name": name,
                 "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tools": entries}
        STORE.mkdir(exist_ok=True)
        index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"store/index.json mit {len(entries)} Tool(s) geschrieben.")
    elif not changed:
        print("Store ist aktuell.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("check", "build"))
    ap.add_argument("--name", help="Anzeigename des Stores (Standard: bisheriger Name bzw. '<Repo> Store')")
    ap.add_argument("--omniwrench", help="Pfad zum OmniWrench-Quellcode")
    args = ap.parse_args()
    sys.exit(run(args.mode, args.name, args.omniwrench))
