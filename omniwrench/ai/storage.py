"""Lokale Ablage der KI-Daten in lesbaren Formaten.

Ablagemodi ("ai_storage_mode"):
    documents  Eigene Dateien: Dokumente/Bilder/Musik/Videos, jeweils Unterordner "OmniWrench"
    central    ein Ordner ("ai_storage_root") mit Unterordnern je Datenart
    per_type   je Datenart ein eigener Ordner ("ai_storage_paths"), Vorgabe wie "central"

Chats:     <chats>/<thread-id>/thread.json + thread.md
Projekte:  <projects>/<projekt-id>/project.json, files/, threads/<thread-id>/…
Medien:    Datei + gleichnamige .json mit Prompt, Anbieter und Modell

Verschlüsselung ("ai_encrypt", Standard an) gilt für Chats, Projekte und Transkripte, nie für
Medien. Statt *.json liegt dann *.owai daneben: b"OWAI1" + Nonce + AES-256-GCM, Schlüssel im
Tresor ("app:ai:data_key"). Eine Markdown-Fassung wird dann nicht geschrieben.
"""

from __future__ import annotations

import base64
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from omniwrench.core.jsonio import read_json, write_json
from omniwrench.core.paths import LOCAL_DIR

MODE_KEY = "ai_storage_mode"
ROOT_KEY = "ai_storage_root"
PATHS_KEY = "ai_storage_paths"
ENCRYPT_KEY = "ai_encrypt"
DATA_KEY = "app:ai:data_key"
MAGIC = b"OWAI1"

MODES = ("documents", "central", "per_type")
TYPES = ("chats", "projects", "documents", "images", "music", "videos", "transcripts")
ENCRYPTABLE = ("chats", "projects", "transcripts")
FORMATS = {"chats": "JSON + Markdown", "projects": "JSON + Markdown", "documents": "Markdown, HTML, PDF, ODT", "images": "PNG/WebP + JSON",
           "music": "MP3/WAV + JSON", "videos": "MP4 + JSON", "transcripts": "JSON + Markdown"}
SUBDIRS = {"chats": "Chats", "projects": "Projects", "documents": "Documents", "images": "Images", "music": "Music",
           "videos": "Videos", "transcripts": "Transcripts"}
INDEX_DIR = LOCAL_DIR / "ai-index"

_FOLDER_IDS = {   # Windows Known Folder IDs
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
    "music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
    "videos": "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}",
}
_XDG = {"documents": "XDG_DOCUMENTS_DIR", "pictures": "XDG_PICTURES_DIR", "music": "XDG_MUSIC_DIR",
        "videos": "XDG_VIDEOS_DIR"}
_FALLBACK = {"documents": "Documents", "pictures": "Pictures", "music": "Music", "videos": "Videos"}
_TYPE_FOLDER = {"chats": "documents", "projects": "documents", "transcripts": "documents", "documents": "documents",
                "images": "pictures", "music": "music", "videos": "videos"}


def _windows_folder(kind: str) -> Path | None:
    try:
        import ctypes
        from ctypes import wintypes
        import uuid as _uuid

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        u = _uuid.UUID(_FOLDER_IDS[kind])
        guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
            return None
        path = Path(out.value)
        ctypes.windll.ole32.CoTaskMemFree(out)
        return path
    except Exception:
        return None


def _xdg_folder(kind: str) -> Path | None:
    cfg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "user-dirs.dirs"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            m = re.match(rf'\s*{_XDG[kind]}="(.*)"', line)
            if m:
                return Path(m.group(1).replace("$HOME", str(Path.home())))
    except OSError:
        pass
    return None


def user_folder(kind: str) -> Path:
    """Persönlicher Ordner (documents, pictures, music, videos) des Benutzers."""
    path = _windows_folder(kind) if sys.platform == "win32" else _xdg_folder(kind)
    return path or Path.home() / _FALLBACK[kind]


def default_root() -> Path:
    return user_folder("documents") / "OmniWrench" / "AI"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class Storage:
    def __init__(self, settings, vault):
        self.settings = settings
        self.vault = vault
        self._key: bytes | None = None

    # ----------------------------------------------------------------- Orte
    @property
    def mode(self) -> str:
        mode = self.settings.get(MODE_KEY, "documents")
        return mode if mode in MODES else "documents"

    @property
    def root(self) -> Path:
        return Path(self.settings.get(ROOT_KEY) or default_root())

    def default_path(self, kind: str, mode: str | None = None) -> Path:
        mode = mode or self.mode
        if mode == "documents":
            base = user_folder(_TYPE_FOLDER[kind]) / "OmniWrench"
            return base / SUBDIRS[kind] if _TYPE_FOLDER[kind] == "documents" else base
        return self.root / SUBDIRS[kind]

    def path(self, kind: str) -> Path:
        if self.mode == "per_type":
            custom = (self.settings.get(PATHS_KEY) or {}).get(kind)
            if custom:
                return Path(custom)
        return self.default_path(kind)

    def ensure(self, kind: str) -> Path:
        p = self.path(kind)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def all_paths(self) -> dict[str, Path]:
        return {k: self.path(k) for k in TYPES}

    # ------------------------------------------------------- Verschlüsselung
    @property
    def encrypt(self) -> bool:
        return bool(self.settings.get(ENCRYPT_KEY, True))

    def _data_key(self) -> bytes:
        if self._key is None:
            stored = self.vault.get(DATA_KEY)
            if not stored:
                stored = _b64(AESGCM.generate_key(256))
                self.vault.set(DATA_KEY, stored)
            self._key = base64.b64decode(stored)
        return self._key

    def seal(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        return MAGIC + nonce + AESGCM(self._data_key()).encrypt(nonce, data, MAGIC)

    def unseal(self, blob: bytes) -> bytes:
        if not blob.startswith(MAGIC):
            raise ValueError("not an OmniWrench AI file")
        nonce = blob[len(MAGIC):len(MAGIC) + 12]
        return AESGCM(self._data_key()).decrypt(nonce, blob[len(MAGIC) + 12:], MAGIC)

    def write_doc(self, base: Path, data: Any, markdown: str | None = None, encrypt: bool | None = None) -> None:
        """Schreibt <base>.json (+ .md) oder verschlüsselt <base>.owai; entfernt die jeweils andere Form."""
        import json
        encrypt = self.encrypt if encrypt is None else encrypt
        base.parent.mkdir(parents=True, exist_ok=True)
        js, enc, md = base.with_suffix(".json"), base.with_suffix(".owai"), base.with_suffix(".md")
        if encrypt:
            tmp = enc.with_suffix(".owai.tmp")
            tmp.write_bytes(self.seal(json.dumps(data, ensure_ascii=False).encode("utf-8")))
            os.replace(tmp, enc)
            for p in (js, md):
                p.unlink(missing_ok=True)
        else:
            write_json(js, data)
            if markdown is not None:
                md.write_text(markdown, encoding="utf-8")
            enc.unlink(missing_ok=True)

    def read_doc(self, base: Path) -> Any:
        import json
        enc = base.with_suffix(".owai")
        if enc.exists():
            return json.loads(self.unseal(enc.read_bytes()))
        return read_json(base.with_suffix(".json"), default=None)

    @staticmethod
    def doc_exists(base: Path) -> bool:
        return base.with_suffix(".owai").exists() or base.with_suffix(".json").exists()

    # ---------------------------------------------------------- Chats
    @staticmethod
    def new_id() -> str:
        return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)

    def thread_dir(self, thread_id: str, project: str = "") -> Path:
        if project:
            return self.path("projects") / project / "threads" / thread_id
        return self.path("chats") / thread_id

    def save_thread(self, thread: dict, markdown: str | None = None) -> None:
        thread["updated"] = int(time.time())
        self.write_doc(self.thread_dir(thread["id"], thread.get("project", "")) / "thread", thread, markdown)

    def load_thread(self, thread_id: str, project: str = "") -> dict | None:
        try:
            return self.read_doc(self.thread_dir(thread_id, project) / "thread")
        except Exception:
            return None

    def delete_thread(self, thread_id: str, project: str = "") -> None:
        shutil.rmtree(self.thread_dir(thread_id, project), ignore_errors=True)

    def _thread_dirs(self, project: str = "") -> Iterator[Path]:
        base = self.path("projects") / project / "threads" if project else self.path("chats")
        if base.is_dir():
            for d in base.iterdir():
                if d.is_dir() and self.doc_exists(d / "thread"):
                    yield d

    def list_threads(self, project: str = "") -> list[dict]:
        """Kopfdaten (id, title, updated, project, connection_name) aller Chats, neueste zuerst."""
        out = []
        for d in self._thread_dirs(project):
            try:
                t = self.read_doc(d / "thread") or {}
            except Exception:
                t = {"id": d.name, "title": d.name, "updated": int(d.stat().st_mtime), "locked": True}
            out.append({k: t.get(k) for k in ("id", "title", "updated", "project", "connection_name", "locked")}
                       | {"id": t.get("id") or d.name})
        out.sort(key=lambda t: t.get("updated") or 0, reverse=True)
        return out

    # -------------------------------------------------------- Projekte
    def project_dir(self, project_id: str) -> Path:
        return self.path("projects") / project_id

    def list_projects(self) -> list[dict]:
        base = self.path("projects")
        out = []
        if base.is_dir():
            for d in base.iterdir():
                if d.is_dir() and self.doc_exists(d / "project"):
                    try:
                        p = self.read_doc(d / "project") or {}
                    except Exception:
                        p = {"name": d.name, "locked": True}
                    p.setdefault("id", d.name)
                    out.append(p)
        out.sort(key=lambda p: str(p.get("name", "")).lower())
        return out

    def load_project(self, project_id: str) -> dict | None:
        try:
            return self.read_doc(self.project_dir(project_id) / "project")
        except Exception:
            return None

    def save_project(self, project: dict) -> None:
        project.setdefault("id", self.new_id())
        project.setdefault("created", int(time.time()))
        project["updated"] = int(time.time())
        md = f"# {project.get('name', '')}\n\n{project.get('instructions', '')}\n"
        self.write_doc(self.project_dir(project["id"]) / "project", project, md)
        (self.project_dir(project["id"]) / "files").mkdir(exist_ok=True)

    def delete_project(self, project_id: str) -> None:
        shutil.rmtree(self.project_dir(project_id), ignore_errors=True)

    # ---------------------------------------------------------- Umbauten
    def convert_all(self, encrypt: bool) -> int:
        """Schreibt alle Chats/Projekte im gewünschten Format neu (nach Umschalten der Verschlüsselung)."""
        from .chat import thread_markdown
        count = 0
        for project in [""] + [p["id"] for p in self.list_projects() if not p.get("locked")]:
            if project:
                base = self.project_dir(project) / "project"
                data = self.read_doc(base)
                if data:
                    md = f"# {data.get('name', '')}\n\n{data.get('instructions', '')}\n"
                    self.write_doc(base, data, md, encrypt=encrypt)
            for d in list(self._thread_dirs(project)):
                try:
                    data = self.read_doc(d / "thread")
                except Exception:
                    continue
                if data:
                    self.write_doc(d / "thread", data, thread_markdown(data), encrypt=encrypt)
                    count += 1
        return count

    @staticmethod
    def move_tree(src: Path, dst: Path) -> int:
        """Verschiebt den Inhalt von src nach dst (bestehende Einträge in dst bleiben). Anzahl Einträge."""
        if not src.is_dir() or src.resolve() == dst.resolve():
            return 0
        dst.mkdir(parents=True, exist_ok=True)
        moved = 0
        for item in list(src.iterdir()):
            target = dst / item.name
            if target.exists():
                continue
            shutil.move(str(item), str(target))
            moved += 1
        try:
            src.rmdir()
        except OSError:
            pass
        return moved

    def media_target(self, kind: str, stem: str, suffix: str) -> Path:
        folder = self.ensure(kind) / time.strftime("%Y-%m")
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w\-. ]+", "_", stem).strip()[:60] or kind
        path = folder / f"{time.strftime('%Y%m%d-%H%M%S')}-{safe}{suffix}"
        return path
