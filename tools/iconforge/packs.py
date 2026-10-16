"""Symbol-Pakete: eingebautes Lucide + bei Bedarf geladene npm-Pakete (siehe icon_packs.json).

Ablage geladener Pakete:  <tool_data>/packs/<pack>/<variant>/<name>.svg
                          <tool_data>/packs/<pack>/index.json   (Version, Varianten, Metadaten)
Katalog (npm-Angaben):    <tool_data>/packs/catalog.json        (Version, Größe, Dateien, Datum je Paket)
"""

from __future__ import annotations

import io
import json
import random
import re
import shutil
import tarfile
import threading
import zlib
from colorsys import hls_to_rgb
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from omniwrench.core import icons, net

PACKS_FILE = Path(__file__).with_name("icon_packs.json")
LICENSES_FILE = Path(__file__).with_name("licenses.json")
MIN_AGE_DAYS = 14
CATALOG_TTL = timedelta(hours=24)
NPM = "https://registry.npmjs.org/"


@dataclass(frozen=True)
class IconRef:
    pack: str
    variant: str
    name: str


def load_definitions() -> dict[str, dict]:
    return json.loads(PACKS_FILE.read_text(encoding="utf-8"))["packs"]


def load_licenses() -> dict:
    return json.loads(LICENSES_FILE.read_text(encoding="utf-8"))


def _npm_url(package: str) -> str:
    return NPM + package.replace("/", "%2F")


def mature_version(meta: dict) -> str:
    """Neueste stabile Version, die mindestens MIN_AGE_DAYS alt ist (sonst die neueste)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_AGE_DAYS)
    candidates = [(datetime.fromisoformat(t.replace("Z", "+00:00")), v) for v, t in meta["time"].items()
                  if v in meta.get("versions", {}) and "-" not in v]
    mature = [c for c in candidates if c[0] <= cutoff] or candidates
    return max(mature)[1]


def pack_color(pack: str, spec: dict) -> str:
    """Akzentfarbe eines Pakets: aus icon_packs.json oder stabil aus der Paket-ID abgeleitet."""
    if spec.get("color"):
        return spec["color"]
    hue = zlib.crc32(pack.encode()) % 360
    r, g, b = hls_to_rgb(hue / 360, 0.46, 0.62)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


class PackStore:
    def __init__(self, data_dir: Path):
        self.root = data_dir / "packs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.defs = load_definitions()
        self._index: dict[str, dict] = {}
        self._catalog_file = self.root / "catalog.json"
        self._lock = threading.Lock()
        try:
            self._catalog: dict[str, dict] = json.loads(self._catalog_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._catalog = {}

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

    def downloadable(self) -> list[str]:
        """Pakete, die aus dem npm-Registry geladen werden können (alle außer den eingebauten)."""
        return sorted((p for p, d in self.defs.items() if not d.get("builtin")), key=lambda p: self.defs[p]["name"].lower())

    def disk_size(self, pack: str) -> int:
        folder = self.root / pack
        return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) if folder.exists() else 0

    # ------------------------------------------------------------ Katalog (npm-Angaben vor dem Laden)
    def catalog(self, pack: str) -> dict:
        """Zwischengespeicherte Angaben: {version, size, files, published, exact, fetched} oder {}."""
        return self._catalog.get(pack, {})

    def catalog_fresh(self, pack: str, exact: bool = False) -> bool:
        entry = self._catalog.get(pack)
        if not entry or (exact and not entry.get("exact")):
            return False
        fetched = datetime.fromisoformat(entry["fetched"])
        return datetime.now(timezone.utc) - fetched < CATALOG_TTL

    def _store_catalog(self, pack: str, entry: dict) -> dict:
        entry["fetched"] = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._catalog[pack] = entry
            try:
                self._catalog_file.write_text(json.dumps(self._catalog, separators=(",", ":")), encoding="utf-8")
            except OSError:
                pass
        return entry

    def fetch_summary(self, pack: str) -> dict:
        """Schnelle Angaben zur neuesten Version (wenige KB) - für die Auswahlliste."""
        if self.catalog_fresh(pack):
            return self.catalog(pack)
        info = json.loads(net.get_bytes(_npm_url(self.defs[pack]["package"]) + "/latest"))
        dist = info.get("dist", {})
        return self._store_catalog(pack, {"version": info.get("version", ""), "size": dist.get("unpackedSize", 0),
                                          "files": dist.get("fileCount", 0), "published": "", "exact": False})

    def fetch_release(self, pack: str) -> dict:
        """Genaue Angaben zu der Version, die geladen würde (siehe mature_version)."""
        if self.catalog_fresh(pack, exact=True):
            return self.catalog(pack)
        meta = json.loads(net.get_bytes(_npm_url(self.defs[pack]["package"])))
        version = mature_version(meta)
        dist = meta["versions"][version].get("dist", {})
        return self._store_catalog(pack, {"version": version, "size": dist.get("unpackedSize", 0),
                                          "files": dist.get("fileCount", 0),
                                          "published": meta["time"].get(version, ""), "exact": True})

    # ------------------------------------------------------------ Laden
    def download(self, pack: str, progress: Callable[[str], None] = lambda m: None) -> None:
        spec = self.defs[pack]
        package = spec["package"]
        progress(f"{spec['name']} …")
        meta = json.loads(net.get_bytes(_npm_url(package)))
        version = mature_version(meta)
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
                 "published": meta["time"].get(version, ""),
                 "variants": {v: sorted(n) for v, n in variants.items() if n},
                 "meta": meta_icons, "categories": categories}
        (tmp / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        shutil.rmtree(target, ignore_errors=True)
        tmp.rename(target)
        self._index.pop(pack, None)
        total = sum(len(n) for n in index["variants"].values())
        progress(f"{spec['name']} {version} ({total})")

    def samples(self, pack: str, count: int) -> list[bytes]:
        """Einige Symbole eines verfügbaren Pakets (stabil je Paket) - z. B. für das Vorschau-Banner."""
        if not self.is_available(pack):
            return []
        refs = self.items(pack, next(iter(self.index(pack)["variants"]), None))
        picked = random.Random(pack).sample(refs, min(count, len(refs)))
        out = []
        for ref in picked:
            try:
                out.append(self.svg(ref))
            except OSError:
                pass
        return out

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
