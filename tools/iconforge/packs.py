"""Symbol-Pakete: eingebautes Lucide + bei Bedarf geladene npm-Pakete (siehe icon_packs.json).

Ablage geladener Pakete:  <tool_data>/packs/<pack>/<variant>/<name>.svg
                          <tool_data>/packs/<pack>/index.json   (Version, Varianten, Metadaten)
"""

from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from omniwrench.core import icons, net

PACKS_FILE = Path(__file__).with_name("icon_packs.json")
LICENSES_FILE = Path(__file__).with_name("licenses.json")
MIN_AGE_DAYS = 14


@dataclass(frozen=True)
class IconRef:
    pack: str
    variant: str
    name: str


def load_definitions() -> dict[str, dict]:
    return json.loads(PACKS_FILE.read_text(encoding="utf-8"))["packs"]


def load_licenses() -> dict:
    return json.loads(LICENSES_FILE.read_text(encoding="utf-8"))


class PackStore:
    def __init__(self, data_dir: Path):
        self.root = data_dir / "packs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.defs = load_definitions()
        self._index: dict[str, dict] = {}

    # ------------------------------------------------------------ Status
    def is_available(self, pack: str) -> bool:
        return self.defs[pack].get("builtin") or (self.root / pack / "index.json").exists()

    def index(self, pack: str) -> dict:
        """{"version", "license", "variants": {variant: [names]}, "meta": {name: {tags, categories}}}"""
        if pack not in self._index:
            if self.defs[pack].get("builtin"):
                meta = icons.library_meta()
                self._index[pack] = {"version": icons.library_version(), "variants": {"default": list(icons.library_names())},
                                     "meta": meta["icons"], "categories": {k: v.get("title", k) for k, v in meta["categories"].items()}}
            else:
                self._index[pack] = json.loads((self.root / pack / "index.json").read_text(encoding="utf-8"))
        return self._index[pack]

    def items(self, pack: str, variant: str | None = None) -> list[IconRef]:
        idx = self.index(pack)
        variants = [variant] if variant else list(idx["variants"])
        return [IconRef(pack, v, n) for v in variants for n in idx["variants"].get(v, [])]

    def info(self, ref: IconRef) -> dict:
        return self.index(ref.pack).get("meta", {}).get(ref.name, {"tags": [], "categories": []})

    def category_title(self, pack: str, cid: str) -> str:
        return self.index(pack).get("categories", {}).get(cid, cid)

    def svg(self, ref: IconRef) -> bytes:
        if self.defs[ref.pack].get("builtin"):
            return icons.library_svg(ref.name)
        return (self.root / ref.pack / ref.variant / f"{ref.name}.svg").read_bytes()

    def license_key(self, pack: str) -> str:
        return self.defs[pack]["license"]

    def is_brand(self, ref: IconRef) -> bool:
        brands = self.defs[ref.pack].get("brands_variant")
        return bool(brands) and ref.variant == brands

    # ------------------------------------------------------------ Laden
    def download(self, pack: str, progress: Callable[[str], None] = lambda m: None) -> None:
        spec = self.defs[pack]
        package = spec["package"]
        progress(f"{spec['name']} …")
        meta = json.loads(net.get_bytes(f"https://registry.npmjs.org/{package.replace('/', '%2F')}"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_AGE_DAYS)
        candidates = [(datetime.fromisoformat(t.replace("Z", "+00:00")), v) for v, t in meta["time"].items()
                      if v in meta.get("versions", {}) and "-" not in v]
        mature = [c for c in candidates if c[0] <= cutoff] or candidates
        version = max(mature)[1]
        info = meta["versions"][version]
        progress(f"{spec['name']} {version} …")
        data = net.get_bytes(info["dist"]["tarball"], timeout=600)

        target = self.root / pack
        tmp = self.root / f".{pack}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        variants: dict[str, set[str]] = {v: set() for v in spec["variants"]}
        meta_icons: dict[str, dict] = {}
        categories: dict[str, str] = {}
        meta_raw = None
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                rel = PurePosixPath(member.name)
                rel = PurePosixPath(*rel.parts[1:])  # "package/" entfernen
                if spec.get("meta") and str(rel) == spec["meta"]["file"]:
                    meta_raw = json.loads(tar.extractfile(member).read())
                    continue
                if rel.suffix.lower() != ".svg":
                    continue
                for vid, v in spec["variants"].items():
                    base = PurePosixPath(v["dir"])
                    try:
                        sub = rel.relative_to(base)
                    except ValueError:
                        continue
                    if len(sub.parts) > 1 and not spec.get("recursive"):
                        continue
                    stem = rel.stem
                    if v.get("include") and not re.search(v["include"], stem):
                        continue
                    name = re.sub(v["strip"], "", stem) if v.get("strip") else stem
                    name = name.lower()
                    out = tmp / vid / f"{name}.svg"
                    if out.exists():
                        continue
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(tar.extractfile(member).read())
                    variants[vid].add(name)
                    if spec.get("categories_from_subdirs") and len(sub.parts) > 1:
                        cat = sub.parts[0]
                        categories[cat.lower()] = cat.replace("-", " ").title()
                        entry = meta_icons.setdefault(name, {"tags": [], "categories": []})
                        if cat.lower() not in entry["categories"]:
                            entry["categories"].append(cat.lower())
        if meta_raw is not None:
            parse_meta(spec["meta"]["format"], meta_raw, meta_icons, categories)
        index = {"version": version, "license": spec["license"], "package": package,
                 "variants": {v: sorted(n) for v, n in variants.items() if n},
                 "meta": meta_icons, "categories": categories}
        (tmp / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)
        self._index.pop(pack, None)
        total = sum(len(n) for n in index["variants"].values())
        progress(f"{spec['name']} {version} ({total})")

    def remove(self, pack: str) -> None:
        shutil.rmtree(self.root / pack, ignore_errors=True)
        self._index.pop(pack, None)


def _add(meta: dict, name: str, tags=(), cats=()) -> None:
    entry = meta.setdefault(name.lower(), {"tags": [], "categories": []})
    entry["tags"] += [t for t in tags if t and t not in entry["tags"]]
    entry["categories"] += [c for c in cats if c and c not in entry["categories"]]


def parse_meta(fmt: str, raw, meta: dict, categories: dict) -> None:
    """Schlagwörter/Kategorien aus den Paket-Metadaten übernehmen."""
    if fmt == "tabler":
        for name, info in raw.items():
            cat = (info.get("category") or "").strip()
            cid = cat.lower()
            if cat:
                categories[cid] = cat
            _add(meta, name, [str(t) for t in info.get("tags", [])], [cid] if cat else [])
    elif fmt == "mdi":
        for info in raw:
            cats = []
            for tag in info.get("tags", []):
                cid = tag.lower()
                categories[cid] = tag
                cats.append(cid)
            _add(meta, info["name"], info.get("aliases", []), cats)
    elif fmt == "octicons":
        for name, info in raw.items():
            _add(meta, name, info.get("keywords", []))
    elif fmt == "fontawesome":
        for name, info in raw.items():
            _add(meta, name, [str(t) for t in info.get("search", {}).get("terms", [])] + [info.get("label", "")])
    elif fmt == "simpleicons":
        for info in raw:
            aliases = info.get("aliases", {})
            extra = aliases.get("aka", []) if isinstance(aliases, dict) else []
            _add(meta, info.get("slug") or re.sub(r"[^a-z0-9]", "", info["title"].lower()), [info["title"], *extra])
