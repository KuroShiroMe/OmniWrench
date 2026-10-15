"""Lädt die Icon-Bibliothek Lucide (ISC-Lizenz) nach omniwrench/resources/icons/lucide/.

    python scripts/update_icons.py            # neueste Version, die mindestens 14 Tage alt ist
    python scripts/update_icons.py 1.40.0     # bestimmte Version

Lucide: https://lucide.dev - frei, auch kommerziell nutzbar (ISC), Lizenztext liegt bei.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench.core import net  # noqa: E402

TARGET = ROOT / "omniwrench" / "resources" / "icons" / "lucide"


def pick_version(meta: dict) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    candidates = [
        (datetime.fromisoformat(t.replace("Z", "+00:00")), v)
        for v, t in meta["time"].items()
        if v not in ("created", "modified") and "-" not in v
    ]
    return max(c for c in candidates if c[0] <= cutoff)[1]


def main() -> None:
    meta = json.loads(net.get_bytes("https://registry.npmjs.org/lucide-static"))
    version = sys.argv[1] if len(sys.argv) > 1 else pick_version(meta)
    info = meta["versions"][version]
    print(f"Lucide {version} ({info.get('license')}) wird geladen …")
    data = net.get_bytes(info["dist"]["tarball"], timeout=120)

    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            if not member.isfile():
                continue
            if name.startswith("package/icons/") and name.endswith(".svg"):
                (TARGET / Path(name).name).write_bytes(tar.extractfile(member).read())
                count += 1
            elif name in ("package/LICENSE", "package/license"):
                (TARGET / "LICENSE").write_bytes(tar.extractfile(member).read())
    (TARGET / "VERSION").write_text(version + "\n", encoding="utf-8")
    print(f"{count} Icons nach {TARGET.relative_to(ROOT)} geschrieben.")


if __name__ == "__main__":
    main()
