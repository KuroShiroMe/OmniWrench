"""Funktionen von Clank für Assistenten: Arbeitsbereich lesen, Dateien ändern, Git, Befehle.

Pfade sind immer relativ zum Arbeitsbereich ("<Eintrag>/unter/datei"). Lesen ab Stufe 3, Dateien schreiben und
Befehle ausführen ab Stufe 4 mit Bestätigung: das Fenster zeigt den Befehl bzw. die Änderung (Diff) und die
kurze Erklärung des Assistenten.
"""

from __future__ import annotations

from pathlib import Path

from . import workspace as wsm
from .workspace import WorkspaceError

DIFF_PREVIEW = 6000


class StudioAI:
    def __init__(self, tool):
        self.tool = tool
        ctx = tool.context
        add = getattr(ctx, "ai_function", None)
        if add is None:
            return
        from omniwrench.sdk import AI_CHANGE, AI_OVERVIEW, AI_READ
        tr = ctx.tr
        path = {"path": {"type": "string", "description": "Path relative to the workspace: '<entry>/sub/file'. "
                                                            "Empty = all entries."}}
        add("studio_workspace", "Clank: folders and repositories the user shared in the current workspace "
            "(name, kind, read-only, Git branch, remote URL).", self.workspace, level=AI_OVERVIEW)
        add("studio_list", "Clank: list files and folders of the workspace.", self.list, level=AI_READ,
            parameters={"type": "object", "properties": {
                **path, "depth": {"type": "integer", "description": "1-6, default 1"},
                "pattern": {"type": "string", "description": "File name filter like *.ps1"}}})
        add("studio_read", "Clank: read a text file of the workspace (optionally a line range).", self.read,
            level=AI_READ, parameters={"type": "object", "properties": {
                **path, "start_line": {"type": "integer"}, "lines": {"type": "integer"}}, "required": ["path"]})
        add("studio_search", "Clank: search text in the workspace files (case-insensitive; remote repositories: "
            "file names only).", self.search, level=AI_READ,
            parameters={"type": "object", "properties": {
                "query": {"type": "string"}, **path, "pattern": {"type": "string"},
                "regex": {"type": "boolean"}}, "required": ["query"]})
        add("studio_git", "Clank: Git information of a local repository in the workspace: status, log, diff "
            "(working tree or staged) or show (one commit).", self.git, level=AI_READ,
            parameters={"type": "object", "properties": {
                "action": {"type": "string", "enum": ["status", "log", "diff", "show"]}, **path,
                "commit": {"type": "string"}, "staged": {"type": "boolean"}, "count": {"type": "integer"}},
                "required": ["action"]})
        add("studio_write_file", "Clank: create or overwrite a text file in the workspace with the complete new "
            "content. The user sees the diff and confirms first. Give a short explanation.", self.write,
            level=AI_CHANGE, parameters={"type": "object", "properties": {
                **path, "content": {"type": "string"},
                "explanation": {"type": "string", "description": "One or two sentences: what and why"}},
                "required": ["path", "content", "explanation"]},
            summary=lambda a: self._write_summary(a, tr))
        add("studio_run_command", "Clank: run a shell command in a local workspace folder (PowerShell on "
            "Windows, bash on Linux unless 'shell' says otherwise). The user sees the command with your "
            "explanation and confirms first. Prefer read-only commands; never run destructive commands without "
            "the user asking for it.", self.run, level=AI_CHANGE,
            parameters={"type": "object", "properties": {
                "command": {"type": "string"},
                "explanation": {"type": "string", "description": "Short explanation of what the command does"},
                "folder": {"type": "string", "description": "Working folder relative to the workspace"},
                "shell": {"type": "string", "enum": ["powershell", "cmd", "bash"]}},
                "required": ["command", "explanation"]},
            summary=lambda a: {"text": tr("ai.confirm.command", folder=a.get("folder") or self._first_name()),
                               "code": a.get("command", ""), "explanation": a.get("explanation", "")})

    # --- Hilfen -------------------------------------------------------------------------------------
    def _ws(self, call) -> wsm.Workspace:
        return wsm.Workspace(call.in_gui(lambda: [dict(r) for r in self.tool.roots]))

    def _first_name(self) -> str:
        roots = self.tool.roots
        return roots[0]["name"] if roots else "?"

    def _remote(self, root: dict):
        return self.tool.remote_for(root)

    # --- Lesen --------------------------------------------------------------------------------------
    def workspace(self, args, call):
        out = []
        for r in self._ws(call).roots:
            e = {"name": r["name"], "kind": r["kind"], "read_only": bool(r.get("readonly"))}
            if r["kind"] == "remote":
                e["url"] = (r.get("remote") or {}).get("url", "")
            elif r["kind"] == "git":
                try:
                    e["branch"] = wsm.git(Path(r["path"]), "rev-parse", "--abbrev-ref", "HEAD").strip()
                except WorkspaceError:
                    pass
            out.append(e)
        return {"entries": out, "hint": "" if out else "Empty workspace. The user can add folders in Clank."}

    def list(self, args, call):
        ws = self._ws(call)
        rel = args.get("path") or ""
        if not rel and len(ws.roots) > 1:
            return {"entries": [r["name"] for r in ws.roots], "hint": "Pass one of these names as path."}
        root, sub = ws.split(rel)
        if root["kind"] == "remote":
            items = self._remote(root).list_dir(sub, int(args.get("depth") or 1))
            return {"items": [{"path": f"{root['name']}/{e['path']}", "type": e["type"]} for e in items]}
        return ws.list_dir(rel, args.get("depth") or 1, args.get("pattern") or "")

    def read(self, args, call):
        ws = self._ws(call)
        root, sub = ws.split(args.get("path") or "")
        if root["kind"] == "remote":
            text, cut = self._remote(root).read(sub)
            lines = text.splitlines()
            start = max(1, int(args.get("start_line") or 1))
            n = int(args.get("lines") or 0)
            chunk = lines[start - 1:start - 1 + n] if n else lines[start - 1:]
            return {"path": f"{root['name']}/{sub}", "lines": len(lines), "first_line": start,
                    "content": "\n".join(chunk), "truncated": cut}
        out = ws.read(args.get("path") or "", args.get("start_line") or 1, args.get("lines") or 0)
        call.in_gui(lambda: self.tool.show_file(out["path"], quiet=True))
        return out

    def search(self, args, call):
        ws = self._ws(call)
        rel = args.get("path") or ""
        if rel:
            root, _sub = ws.split(rel)
            if root["kind"] == "remote":
                return {"files": [f"{root['name']}/{p}" for p in self._remote(root).search_paths(args["query"])]}
        out = ws.search(args.get("query") or "", rel, args.get("pattern") or "", bool(args.get("regex")))
        if not rel:
            for r in ws.roots:
                if r["kind"] == "remote":
                    out.setdefault("remote_files", []).extend(
                        f"{r['name']}/{p}" for p in self._remote(r).search_paths(args["query"])[:50])
        return out

    def git(self, args, call):
        ws = self._ws(call)
        rel, action = args.get("path") or "", args.get("action") or "status"
        if action == "status":
            return wsm.git_status(ws, rel)
        if action == "log":
            return wsm.git_log(ws, rel, args.get("count") or 20)
        if action == "show":
            if not args.get("commit"):
                raise WorkspaceError("commit missing")
            return wsm.git_diff(ws, rel, commit=str(args["commit"]))
        return wsm.git_diff(ws, rel, staged=bool(args.get("staged"))) or "(no changes)"

    # --- Ändern -------------------------------------------------------------------------------------
    def _write_summary(self, a: dict, tr) -> dict:
        path = a.get("path", "")
        try:
            diff = wsm.Workspace([dict(r) for r in self.tool.roots]).diff(path, a.get("content", ""))
        except WorkspaceError as e:
            diff = f"({e})"
        if len(diff) > DIFF_PREVIEW:
            diff = diff[:DIFF_PREVIEW] + "\n…"
        return {"text": tr("ai.confirm.write", path=path), "code": diff or tr("ai.confirm.no_change"),
                "explanation": a.get("explanation", "")}

    def write(self, args, call):
        ws = self._ws(call)
        out = ws.write(args.get("path") or "", args.get("content") or "")
        call.in_gui(lambda: self.tool.file_changed(out["path"]))
        return out

    def run(self, args, call):
        ws = self._ws(call)
        folder = args.get("folder") or ""
        if not ws.local_roots():
            raise WorkspaceError("No local folder in the workspace to run commands in.")
        if folder:
            _root, cwd = ws.resolve(folder)
        else:
            cwd = Path(ws.local_roots()[0]["path"])
        if not cwd.is_dir():
            raise WorkspaceError(f"Not a folder: {folder}")
        settings = self.tool.context.settings
        shell = args.get("shell") or settings.get("shell") or ""
        shell = "" if shell == "auto" else shell
        result = wsm.run_command(args.get("command") or "", cwd, shell, int(settings.get("command_timeout") or 120))
        call.in_gui(lambda: self.tool.command_ran(args.get("command") or "", result))
        return result
