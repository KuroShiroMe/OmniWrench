"""Baut den Store: packt jedes Tool aus tools/ als ZIP und erzeugt store/index.json.

Aufruf:
    python scripts/build_store.py                     # relative Download-URLs (lokal & GitHub raw)
    python scripts/build_store.py --base-url URL      # absolute Download-URLs (z. B. GitHub Releases)

Danach den Ordner store/ ins GitHub-Repository committen. Als Repository-URL im
Programm dann eintragen:
    https://raw.githubusercontent.com/<owner>/<repo>/main/store/index.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from admintools.core.manifest import validate_package  # noqa: E402

EXCLUDE_DIRS = {"__pycache__", "_lib", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def build(tools_dir: Path, store_dir: Path, base_url: str | None) -> None:
    packages = store_dir / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    index = {"format": 1, "name": "Admin Tools Store",
             "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tools": []}

    for tool_dir in sorted(p for p in tools_dir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
        manifest = validate_package(tool_dir)
        zip_name = f"{manifest.id}-{manifest.version}.zip"
        zip_path = packages / zip_name
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(tool_dir.rglob("*")):
                rel = f.relative_to(tool_dir)
                if f.is_dir() or EXCLUDE_DIRS.intersection(rel.parts) or f.suffix in EXCLUDE_SUFFIXES:
                    continue
                zf.write(f, rel.as_posix())
        entry = dict(manifest.raw)
        if manifest.translations:  # übersetzte Namen/Beschreibungen/Kategorien aus locales/*.json
            entry["translations"] = manifest.translations
        entry["download_url"] = (base_url.rstrip("/") + "/" + zip_name) if base_url else f"packages/{zip_name}"
        entry["sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        entry["size"] = zip_path.stat().st_size
        index["tools"].append(entry)
        print(f"  {manifest.id} {manifest.version} -> {zip_path.relative_to(ROOT)}")

    (store_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"index.json mit {len(index['tools'])} Tool(s) geschrieben.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tools", type=Path, default=ROOT / "tools")
    ap.add_argument("--out", type=Path, default=ROOT / "store")
    ap.add_argument("--base-url", default=None)
    args = ap.parse_args()
    build(args.tools, args.out, args.base_url)
