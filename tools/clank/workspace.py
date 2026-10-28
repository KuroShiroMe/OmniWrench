"""Arbeitsbereich des KI-Studios: freigegebene Ordner, lokale Git-Repositories und entfernte Repositories.

Ein Eintrag (root) ist ein dict:
    {"id": "r-1a2b", "kind": "folder" | "git" | "remote", "name": "...", "path": "C:/...",   # folder/git
     "readonly": False,
     "remote": {"provider": "github" | "gitlab" | "azure", "url": "...", "branch": "main"}}   # nur remote

Gespeichert im Projekt (project["workspace"]) oder ohne Projekt in der Tool-Einstellung "workspace".
Alle Pfade des Assistenten sind relativ zu einem Eintrag ("<name>/unter/ordner/datei.txt"); Zugriffe außerhalb
der Einträge (.., absolute Pfade, Verknüpfungen nach draußen) werden abgelehnt.
"""

from __future__ import annotations

import difflib
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
             ".idea", ".vs", "dist", "build", ".tox", "_lib", ".gradle", "target", "bin", "obj"}
MAX_READ = 400_000          # Zeichen je Lesezugriff
MAX_LIST = 2_000            # Einträge je Auflistung
MAX_HITS = 300              # Suchtreffer
MAX_FILE_SEARCH = 2_000_000  # größere Dateien werden bei der Suche übersprungen
TEXT_SNIFF = 4096


class WorkspaceError(Exception):
    pass


def new_root(kind: str, name: str, path: str = "", remote: dict | None = None, readonly: bool = False) -> dict:
    root = {"id": "r-" + uuid.uuid4().hex[:6], "kind": kind, "name": name, "path": path, "readonly": readonly}
    if remote:
        root["remote"] = dict(remote)
    return root


def unique_name(roots: list[dict], name: str) -> str:
    base, n, have = name or "Ordner", 2, {r["name"].lower() for r in roots}
    out = base
    while out.lower() in have:
        out = f"{base} ({n})"
        n += 1
    return out


def is_git_dir(path: Path) -> bool:
    return (path / ".git").exists()


def git_available() -> bool:
    return shutil.which("git") is not None


def is_text(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(TEXT_SNIFF)
    except OSError:
        return False
    if b"\0" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            chunk.decode("cp1252")
            return True
        except UnicodeDecodeError:
            return False


def read_text(path: Path, limit: int = MAX_READ) -> tuple[str, bool]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return (text[:limit], len(text) > limit)


class Workspace:
    def __init__(self, roots: list[dict] | None = None):
        self.roots: list[dict] = [dict(r) for r in roots or [] if isinstance(r, dict) and r.get("name")]

    # --- Einträge ---------------------------------------------------------------------------------
    def local_roots(self) -> list[dict]:
        return [r for r in self.roots if r.get("kind") in ("folder", "git")]

    def root(self, name: str) -> dict:
        for r in self.roots:
            if r["name"].lower() == (name or "").lower():
                return r
        raise WorkspaceError(f"Unknown workspace entry '{name}'. Known: {', '.join(r['name'] for r in self.roots)}")

    def split(self, rel: str) -> tuple[dict, str]:
        """"Name/unter/pfad" -> (root, "unter/pfad"). Ohne Namen: einziger Eintrag."""
        rel = (rel or "").replace("\\", "/").strip().strip("/")
        if not self.roots:
            raise WorkspaceError("The workspace is empty. Ask the user to add a folder or repository in KI-Studio.")
        head, _, rest = rel.partition("/")
        for r in self.roots:
            if r["name"].lower() == head.lower():
                return r, rest
        if len(self.roots) == 1:
            return self.roots[0], rel
        return self.root(head), rest

    def resolve(self, rel: str) -> tuple[dict, Path]:
        """Lokaler Pfad innerhalb eines Eintrags; Ausbruchsversuche -> WorkspaceError."""
        root, sub = self.split(rel)
        if root.get("kind") == "remote":
            raise WorkspaceError("remote")
        base = Path(root["path"]).resolve()
        if not base.is_dir():
            raise WorkspaceError(f"Folder of '{root['name']}' not found: {base}")
        if sub and (Path(sub).is_absolute() or re.match(r"^[A-Za-z]:", sub)):
            raise WorkspaceError("Absolute paths are not allowed; use paths relative to the workspace.")
        target = (base / sub).resolve() if sub else base
        if target != base and base not in target.parents:
            raise WorkspaceError("Path is outside the workspace.")
        return root, target

    def rel(self, root: dict, path: Path) -> str:
        base = Path(root["path"]).resolve()
        sub = path.resolve().relative_to(base).as_posix() if path.resolve() != base else ""
        return f"{root['name']}/{sub}".rstrip("/")

    # --- Lesen -------------------------------------------------------------------------------------
    def list_dir(self, rel: str = "", depth: int = 1, pattern: str = "") -> dict:
        root, path = self.resolve(rel)
        if not path.is_dir():
            raise WorkspaceError(f"Not a folder: {rel}")
        depth = max(1, min(int(depth or 1), 6))
        out: list[dict] = []
        truncated = False

        def walk(p: Path, level: int) -> None:
            nonlocal truncated
            try:
                entries = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError:
                return
            for e in entries:
                if len(out) >= MAX_LIST:
                    truncated = True
                    return
                if e.is_dir():
                    if e.name in SKIP_DIRS:
                        continue
                    out.append({"path": self.rel(root, e), "type": "dir"})
                    if level < depth:
                        walk(e, level + 1)
                elif not pattern or fnmatch.fnmatch(e.name.lower(), pattern.lower()):
                    try:
                        size = e.stat().st_size
                    except OSError:
                        size = None
                    out.append({"path": self.rel(root, e), "type": "file", "size": size})
        walk(path, 1)
        return {"items": out, "truncated": truncated}

    def read(self, rel: str, start: int = 1, lines: int = 0) -> dict:
        root, path = self.resolve(rel)
        if not path.is_file():
            raise WorkspaceError(f"Not a file: {rel}")
        if not is_text(path):
            return {"path": self.rel(root, path), "binary": True, "size": path.stat().st_size}
        text, cut = read_text(path)
        all_lines = text.splitlines()
        start = max(1, int(start or 1))
        chunk = all_lines[start - 1:start - 1 + int(lines)] if lines else all_lines[start - 1:]
        return {"path": self.rel(root, path), "first_line": start, "lines": len(all_lines),
                "content": "\n".join(chunk), "truncated": cut}

    def search(self, query: str, rel: str = "", pattern: str = "", regex: bool = False) -> dict:
        if not query:
            raise WorkspaceError("query missing")
        try:
            rx = re.compile(query if regex else re.escape(query), re.IGNORECASE)
        except re.error as e:
            raise WorkspaceError(f"Invalid regular expression: {e}") from None
        roots = [self.resolve(rel)] if rel else [(r, Path(r["path"])) for r in self.local_roots()]
        hits: list[dict] = []
        for root, base in roots:
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fn in filenames:
                    if pattern and not fnmatch.fnmatch(fn.lower(), pattern.lower()):
                        continue
                    p = Path(dirpath) / fn
                    try:
                        if p.stat().st_size > MAX_FILE_SEARCH or not is_text(p):
                            continue
                        text, _ = read_text(p, MAX_FILE_SEARCH)
                    except OSError:
                        continue
                    if rx.search(fn):
                        hits.append({"path": self.rel(root, p), "line": 0, "text": "(file name)"})
                    for no, line in enumerate(text.splitlines(), 1):
                        if rx.search(line):
                            hits.append({"path": self.rel(root, p), "line": no, "text": line.strip()[:240]})
                            if len(hits) >= MAX_HITS:
                                return {"items": hits, "truncated": True}
        return {"items": hits, "truncated": False}

    # --- Schreiben ---------------------------------------------------------------------------------
    def check_writable(self, rel: str) -> tuple[dict, Path]:
        root, path = self.resolve(rel)
        if root.get("readonly"):
            raise WorkspaceError(f"'{root['name']}' is read-only in KI-Studio.")
        if path.is_dir():
            raise WorkspaceError(f"Is a folder: {rel}")
        return root, path

    def diff(self, rel: str, content: str) -> str:
        root, path = self.check_writable(rel)
        old = read_text(path)[0] if path.is_file() else ""
        name = self.rel(root, path)
        lines = difflib.unified_diff(old.splitlines(), content.splitlines(), f"a/{name}", f"b/{name}", lineterm="")
        return "\n".join(lines)

    def write(self, rel: str, content: str) -> dict:
        root, path = self.check_writable(rel)
        existed = path.is_file()
        newline = "\n"
        if existed:
            raw = path.read_bytes()
            if b"\r\n" in raw:
                newline = "\r\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = content.replace("\r\n", "\n")
        with path.open("w", encoding="utf-8", newline=newline) as f:
            f.write(text)
        return {"path": self.rel(root, path), "created": not existed, "bytes": path.stat().st_size}


# --- Git ----------------------------------------------------------------------------------------------
def _flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def git(path: Path, *args: str, timeout: int = 60) -> str:
    if not git_available():
        raise WorkspaceError("Git is not installed (git.exe not found in PATH).")
    try:
        p = subprocess.run(["git", "-C", str(path), "-c", "core.quotepath=false", *args], capture_output=True,
                           timeout=timeout, creationflags=_flags())
    except subprocess.TimeoutExpired:
        raise WorkspaceError("git timed out") from None
    out = p.stdout.decode("utf-8", errors="replace")
    if p.returncode != 0:
        raise WorkspaceError((p.stderr.decode("utf-8", errors="replace") or out).strip()[:2000])
    return out


def git_root(ws: Workspace, rel: str) -> tuple[dict, Path]:
    root, path = ws.resolve(rel)
    base = Path(root["path"])
    if not is_git_dir(base):
        raise WorkspaceError(f"'{root['name']}' is not a Git repository.")
    return root, path


def git_status(ws: Workspace, rel: str) -> dict:
    root, path = git_root(ws, rel)
    base = Path(root["path"])
    branch = git(base, "rev-parse", "--abbrev-ref", "HEAD").strip()
    lines = git(base, "status", "--porcelain=v1", "--branch").splitlines()
    files = [{"state": ln[:2].strip(), "path": ln[3:]} for ln in lines if not ln.startswith("##")]
    head = next((ln[3:] for ln in lines if ln.startswith("##")), "")
    return {"repository": root["name"], "branch": branch, "tracking": head, "changes": files[:500],
            "truncated": len(files) > 500}


def git_log(ws: Workspace, rel: str, n: int = 20) -> list[dict]:
    root, path = git_root(ws, rel)
    n = max(1, min(int(n or 20), 200))
    sep = "\x1f"
    out = git(Path(root["path"]), "log", f"-n{n}", f"--pretty=format:%h{sep}%an{sep}%ad{sep}%s", "--date=short",
              "--", str(path))
    return [dict(zip(("commit", "author", "date", "subject"), ln.split(sep))) for ln in out.splitlines() if ln]


def git_diff(ws: Workspace, rel: str, staged: bool = False, commit: str = "") -> str:
    root, path = git_root(ws, rel)
    args = ["show", "--stat", "--patch", commit] if commit else ["diff"] + (["--cached"] if staged else [])
    out = git(Path(root["path"]), *args, "--", str(path))
    return out[:MAX_READ]


# --- Befehle ------------------------------------------------------------------------------------------
def default_shell() -> str:
    return "powershell" if sys.platform == "win32" else "bash"


def run_command(command: str, cwd: Path, shell: str = "", timeout: int = 120) -> dict:
    shell = shell or default_shell()
    if shell == "powershell":
        exe = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        argv = [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    elif shell == "cmd":
        argv = ["cmd.exe", "/d", "/c", command]
    else:
        argv = [shutil.which("bash") or "/bin/sh", "-c", command]
    try:
        p = subprocess.run(argv, cwd=str(cwd), capture_output=True, timeout=max(5, min(int(timeout), 900)),
                           creationflags=_flags(), stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", errors="replace")
        return {"exit_code": None, "timeout": True, "output": out[-30000:]}
    except OSError as e:
        raise WorkspaceError(str(e)) from None

    def dec(b: bytes) -> str:
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return b.decode("cp850" if sys.platform == "win32" else "latin-1", errors="replace")
    out, err = dec(p.stdout), dec(p.stderr)
    return {"exit_code": p.returncode, "output": out[-30000:], "errors": err[-10000:]}
