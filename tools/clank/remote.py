"""Entfernte Repositories (nur lesen): GitHub, GitLab (auch selbst betrieben) und Azure DevOps.

Zugriff über die REST-APIs mit optionalem Token (persönliches Zugriffstoken, im Tresor des Tools). Schreiben
geht über einen lokalen Klon (git clone, Token nur als HTTP-Kopfzeile, nie in der Klon-URL).
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import urllib.parse
from pathlib import Path

from omniwrench.ai.http import AIError, request

from .workspace import WorkspaceError, _flags, git_available

PROVIDERS = ("github", "gitlab", "azure")
MAX_TREE = 20_000
MAX_FILE = 400_000


def parse_url(url: str) -> dict:
    """Repository-URL -> {"provider", "host", "owner", "repo", "project", "url"}; WorkspaceError bei Unbekanntem."""
    u = urllib.parse.urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        raise WorkspaceError("URL must start with https://")
    host = u.netloc.lower()
    parts = [p for p in u.path.split("/") if p]
    if parts and parts[-1].endswith(".git"):
        parts[-1] = parts[-1][:-4]
    if host in ("github.com", "www.github.com"):
        if len(parts) < 2:
            raise WorkspaceError("GitHub URL: https://github.com/<owner>/<repo>")
        return {"provider": "github", "host": "github.com", "owner": parts[0], "repo": parts[1],
                "url": f"https://github.com/{parts[0]}/{parts[1]}"}
    if host == "dev.azure.com" or host.endswith(".visualstudio.com"):
        # https://dev.azure.com/<org>/<project>/_git/<repo>  |  https://<org>.visualstudio.com/<project>/_git/<repo>
        if "_git" not in parts:
            raise WorkspaceError("Azure DevOps URL: https://dev.azure.com/<org>/<project>/_git/<repo>")
        i = parts.index("_git")
        org = parts[0] if host == "dev.azure.com" else host.split(".")[0]
        project = parts[i - 1] if i >= 1 else ""
        repo = parts[i + 1] if len(parts) > i + 1 else project
        return {"provider": "azure", "host": "dev.azure.com", "owner": org, "project": project, "repo": repo,
                "url": f"https://dev.azure.com/{org}/{project}/_git/{repo}"}
    # alles andere: GitLab (gitlab.com oder eigene Instanz); Pfad = Gruppe(n)/Projekt
    if "-" in parts:
        parts = parts[:parts.index("-")]
    if len(parts) < 2:
        raise WorkspaceError("GitLab URL: https://<host>/<group>/<project>")
    return {"provider": "gitlab", "host": host, "owner": "/".join(parts[:-1]), "repo": parts[-1],
            "url": f"{u.scheme}://{host}/{'/'.join(parts)}"}


def token_key(info: dict) -> str:
    return f"token:{info['provider']}:{info['host']}"


class Remote:
    def __init__(self, info: dict, token: str = "", branch: str = ""):
        self.info = info
        self.token = token
        self.branch = branch
        self._tree: list[dict] | None = None

    # --- HTTP --------------------------------------------------------------------------------------
    def _headers(self, raw: bool = False) -> dict:
        p, h = self.info["provider"], {}
        if p == "github":
            h["Accept"] = "application/vnd.github.raw+json" if raw else "application/vnd.github+json"
            h["X-GitHub-Api-Version"] = "2022-11-28"
            if self.token:
                h["Authorization"] = f"Bearer {self.token}"
        elif p == "gitlab" and self.token:
            h["PRIVATE-TOKEN"] = self.token
        elif p == "azure" and self.token:
            h["Authorization"] = "Basic " + base64.b64encode(f":{self.token}".encode()).decode()
        return h

    def _get(self, url: str, raw: bool = False):
        try:
            with request("GET", url, self._headers(raw), timeout=60) as resp:
                data = resp.read()
        except AIError as e:
            if e.kind == "auth" or e.status in (401, 403, 404):
                raise WorkspaceError(f"Access denied or not found ({e.status}). Check URL and token.") from None
            raise WorkspaceError(str(e)) from None
        if raw:
            return data
        return json.loads(data or b"{}")

    def _api(self) -> str:
        i = self.info
        if i["provider"] == "github":
            return f"https://api.github.com/repos/{i['owner']}/{i['repo']}"
        if i["provider"] == "gitlab":
            pid = urllib.parse.quote(f"{i['owner']}/{i['repo']}", safe="")
            return f"https://{i['host']}/api/v4/projects/{pid}"
        return (f"https://dev.azure.com/{urllib.parse.quote(i['owner'])}/{urllib.parse.quote(i['project'])}"
                f"/_apis/git/repositories/{urllib.parse.quote(i['repo'])}")

    # --- Lesen -------------------------------------------------------------------------------------
    def default_branch(self) -> str:
        if self.branch:
            return self.branch
        p = self.info["provider"]
        if p == "azure":
            data = self._get(self._api() + "?api-version=7.1")
            self.branch = (data.get("defaultBranch") or "refs/heads/main").replace("refs/heads/", "")
        else:
            self.branch = self._get(self._api()).get("default_branch") or "main"
        return self.branch

    def tree(self) -> list[dict]:
        """Alle Einträge [{"path", "type": "file"|"dir", "size"}] (zwischengespeichert)."""
        if self._tree is not None:
            return self._tree
        p, ref, out = self.info["provider"], urllib.parse.quote(self.default_branch(), safe=""), []
        if p == "github":
            data = self._get(f"{self._api()}/git/trees/{ref}?recursive=1")
            for e in data.get("tree", []):
                out.append({"path": e["path"], "type": "dir" if e.get("type") == "tree" else "file",
                            "size": e.get("size")})
        elif p == "gitlab":
            page = 1
            while len(out) < MAX_TREE:
                data = self._get(f"{self._api()}/repository/tree?recursive=true&per_page=100&page={page}&ref={ref}")
                if not data:
                    break
                for e in data:
                    out.append({"path": e["path"], "type": "dir" if e.get("type") == "tree" else "file"})
                if len(data) < 100:
                    break
                page += 1
        else:
            data = self._get(f"{self._api()}/items?recursionLevel=Full&versionDescriptor.version={ref}"
                             f"&api-version=7.1")
            for e in data.get("value", []):
                path = e.get("path", "").lstrip("/")
                if path:
                    out.append({"path": path, "type": "dir" if e.get("isFolder") else "file",
                                "size": e.get("size")})
        self._tree = out[:MAX_TREE]
        return self._tree

    def list_dir(self, sub: str = "", depth: int = 1) -> list[dict]:
        sub = sub.strip("/")
        base_depth = sub.count("/") + 1 if sub else 0
        out = []
        for e in self.tree():
            path = e["path"]
            if sub and not path.startswith(sub + "/"):
                continue
            if path.count("/") - base_depth < max(1, depth) and path.count("/") >= base_depth:
                out.append(e)
        return out[:2000]

    def read(self, sub: str) -> tuple[str, bool]:
        p, ref, sub = self.info["provider"], self.default_branch(), sub.strip("/")
        if p == "github":
            data = self._get(f"{self._api()}/contents/{urllib.parse.quote(sub)}?ref={urllib.parse.quote(ref)}",
                             raw=True)
        elif p == "gitlab":
            data = self._get(f"{self._api()}/repository/files/{urllib.parse.quote(sub, safe='')}/raw"
                             f"?ref={urllib.parse.quote(ref)}", raw=True)
        else:
            data = self._get(f"{self._api()}/items?path={urllib.parse.quote('/' + sub)}"
                             f"&versionDescriptor.version={urllib.parse.quote(ref)}&$format=octetStream"
                             f"&api-version=7.1", raw=True)
        if b"\0" in data[:4096]:
            return ("(binary file)", False)
        text = data.decode("utf-8", errors="replace")
        return (text[:MAX_FILE], len(text) > MAX_FILE)

    def search_paths(self, query: str) -> list[str]:
        q = query.lower()
        return [e["path"] for e in self.tree() if e["type"] == "file" and q in e["path"].lower()][:300]


def clone(info: dict, token: str, target: Path, branch: str = "") -> None:
    """git clone; das Token geht nur als HTTP-Kopfzeile mit (nicht in .git/config)."""
    if not git_available():
        raise WorkspaceError("Git is not installed (git.exe not found in PATH).")
    if target.exists() and any(target.iterdir()):
        raise WorkspaceError(f"Target folder is not empty: {target}")
    url = info["url"] + ("" if info["provider"] == "azure" else ".git")
    args = ["git"]
    if token:
        if info["provider"] == "azure":
            auth = "Basic " + base64.b64encode(f":{token}".encode()).decode()
        elif info["provider"] == "gitlab":
            auth = "Basic " + base64.b64encode(f"oauth2:{token}".encode()).decode()
        else:
            auth = "Basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()
        args += ["-c", f"http.extraHeader=Authorization: {auth}"]
    args += ["clone", "--progress"] + (["--branch", branch] if branch else []) + [url, str(target)]
    p = subprocess.run(args, capture_output=True, timeout=1800, creationflags=_flags(), stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        msg = p.stderr.decode("utf-8", errors="replace").strip()
        raise WorkspaceError(re.sub(r"Authorization: \S+ \S+", "Authorization: ***", msg)[-2000:])
