"""Baut den Store: packt jedes Tool aus tools/ als ZIP und erzeugt store/index.json.

Aufruf:
    python scripts/build_store.py                     # relative Download-URLs (lokal & GitHub raw)
    python scripts/build_store.py --base-url URL      # absolute Download-URLs (z. B. GitHub Releases)

Screenshots (tool.json "screenshots", Ordner screenshots/ im Tool) kommen nicht ins ZIP, sondern
nach store/screenshots/<id>/; index.json verweist mit "url" + "sha256" darauf. So lädt das
Programm sie nur bei Bedarf, und neue Screenshots brauchen keine neue Tool-Version.

Danach den Ordner store/ ins GitHub-Repository committen. Als Repository-URL im
Programm dann eintragen:
    https://raw.githubusercontent.com/<owner>/<repo>/main/store/index.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench.core.manifest import SCREENSHOTS_DIR, validate_package  # noqa: E402

EXCLUDE_DIRS = {"__pycache__", "_lib", ".git", SCREENSHOTS_DIR}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def build(tools_dir: Path, store_dir: Path, base_url: str | None) -> None:
    packages = store_dir / "packages"
    packages.mkdir(parents=True, exist_ok=True)
    index = {"format": 1, "name": "OmniWrench Store",
             "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tools": []}

    shots_root = store_dir / SCREENSHOTS_DIR
    if shots_root.is_dir():  # Screenshots immer frisch aus tools/ übernehmen (entfernte fallen weg)
        shutil.rmtree(shots_root)

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
        icon_file = tool_dir / manifest.icon if manifest.icon else None
        if icon_file and icon_file.is_file():  # eigene Bilddatei: für die Store-Ansicht einbetten
            entry["icon_data"] = base64.b64encode(icon_file.read_bytes()).decode("ascii")
        if manifest.translations:  # übersetzte Namen/Beschreibungen/Kategorien aus locales/*.json
            entry["translations"] = manifest.translations
        if manifest.screenshots:
            entry["screenshots"] = publish_screenshots(tool_dir, manifest, store_dir, base_url)
        entry["download_url"] = (base_url.rstrip("/") + "/" + zip_name) if base_url else f"packages/{zip_name}"
        entry["sha256"] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        entry["size"] = zip_path.stat().st_size
        index["tools"].append(entry)
        print(f"  {manifest.id} {manifest.version} -> {zip_path.relative_to(ROOT)}")

    (store_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"index.json mit {len(index['tools'])} Tool(s) geschrieben.")
    publish_ai_providers(store_dir)


def publish_ai_providers(store_dir: Path) -> None:
    """Anbieterliste der KI-Assistenten in den Store kopieren (Programme laden sie von dort nach)."""
    source = ROOT / "omniwrench" / "resources" / "ai" / "providers.json"
    if source.is_file():
        target = store_dir / "ai" / "providers.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(f"KI-Anbieterliste -> {target.relative_to(ROOT)}")


def publish_screenshots(tool_dir: Path, manifest, store_dir: Path, base_url: str | None) -> list[dict]:
    """Kopiert die Screenshots eines Tools nach store/screenshots/<id>/ und ergänzt url + sha256."""
    result = []
    for shot in manifest.screenshot_list:
        src = tool_dir / shot["file"]
        if not src.is_file():
            raise SystemExit(f"{manifest.id}: Screenshot fehlt: {src} (scripts/render_screenshots.py)")
        rel = f"{SCREENSHOTS_DIR}/{manifest.id}/{src.name}"
        target = store_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        data = target.read_bytes()
        result.append({**shot, "url": (base_url.rstrip("/") + "/" + rel) if base_url else rel,
                       "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tools", type=Path, default=ROOT / "tools")
    ap.add_argument("--out", type=Path, default=ROOT / "store")
    ap.add_argument("--base-url", default=None)
    args = ap.parse_args()
    build(args.tools, args.out, args.base_url)
