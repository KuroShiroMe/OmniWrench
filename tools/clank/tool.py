"""Clank – KI-Studio: Chats mit Projekten, Arbeitsbereich aus Ordnern und Repositories, Dateiansicht.

Nutzt die KI-Dienste des Hauptprogramms (ToolContext.ai_services, ab OmniWrench 0.9.0): dieselben
Verbindungen, dieselbe Datenablage und dasselbe Chat-Widget wie die Chatleiste. Projekte und Chats sind
die der Datenablage (gemeinsam mit der Chatleiste); der Arbeitsbereich gehört zum Projekt (project["workspace"])
oder ohne Projekt zur Tool-Einstellung "workspace". Die Funktionen für Assistenten stehen in ai.py.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QInputDialog, QLabel, QMenu, QMessageBox, QSplitter, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from omniwrench.sdk import ToolBase, run_async

from . import remote as rm
from . import workspace as wsm
from .ai import StudioAI
from .chats import ChatList
from .explorer import WorkspacePanel
from .grouptab import GroupTab
from .documents import DocumentsTab
from .images import ImagesTab
from .schedule import ScheduleTab
from .screenshot import Screenshot
from .templates import TemplatesPanel
from .transcript import TranscriptTab
from .voice import VoiceTab
from .mcptab import MCPTab
from .mediatab import MediaTab
from .viewer import FileViewer

MAX_VIEW = 400_000


class Clank(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        ctx = self.context
        tr = self.tr = ctx.tr
        self.root = QWidget(parent)
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(8, 8, 8, 8)
        get = getattr(ctx, "ai_services", None)
        self.services = get() if get else None
        if self.services is None:
            msg = QLabel(tr("ui.needs_app"))
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(msg)
            return self.root
        self.storage = self.services.storage
        self.project: dict | None = None
        self.roots: list[dict] = [dict(r) for r in ctx.settings.get("workspace") or [] if isinstance(r, dict)]
        self._remotes: dict[str, rm.Remote] = {}

        self.modes = QTabWidget()
        self.modes.setDocumentMode(True)
        lay.addWidget(self.modes, 1)
        self.modes.addTab(self._build_chat(), "💬 " + tr("mode.chat"))
        self.images = ImagesTab(self)
        self.images.to_chat.connect(self.image_to_chat)
        self.modes.addTab(self.images, "🖼 " + tr("mode.images"))
        self.music = MediaTab(self, "music")
        self.modes.addTab(self.music, "🎵 " + tr("mode.music"))
        self.video = MediaTab(self, "video")
        self.modes.addTab(self.video, "🎬 " + tr("mode.video"))
        self.group = GroupTab(self)
        self.modes.addTab(self.group, "👥 " + tr("mode.group"))
        self.docs = DocumentsTab(self)
        self.modes.addTab(self.docs, "📄 " + tr("mode.docs"))
        self.plans = ScheduleTab(self)
        self.modes.addTab(self.plans, "⏰ " + tr("mode.plans"))
        self.transcript = TranscriptTab(self)
        self.modes.addTab(self.transcript, "📝 " + tr("mode.transcript"))
        self.voice = VoiceTab(self)
        self.modes.addTab(self.voice, "🗣 " + tr("mode.voice"))
        self.mcp = MCPTab(self)
        self.modes.addTab(self.mcp, "🔌 " + tr("mode.mcp"))
        shot = QToolButton(text="📷 " + tr("shot.button"))
        shot.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        shot_menu = QMenu(shot)
        shot_menu.addAction(tr("shot.region"), lambda: self.screenshot(True))
        shot_menu.addAction(tr("shot.full"), lambda: self.screenshot(False))
        shot.setMenu(shot_menu)
        self.modes.setCornerWidget(shot, Qt.Corner.TopRightCorner)
        self.modes.currentChanged.connect(self._mode_changed)

        self.ai = StudioAI(self)
        self._level_timer = QTimer(self.root)
        self._level_timer.timeout.connect(self._update_level)
        self._level_timer.start(4000)
        last = ctx.settings.get("last_project") or ""
        self.set_project(last if self.storage.load_project(last) else "") if last else self.set_project("")
        return self.root

    def _build_chat(self) -> QWidget:
        tr = self.tr
        split = QSplitter(Qt.Orientation.Horizontal)
        side = QTabWidget()
        side.setUsesScrollButtons(False)
        side.tabBar().setExpanding(True)
        side.setMinimumWidth(240)
        self.chats = ChatList(tr, self.storage)
        side.addTab(self.chats, tr("side.chats"))
        self.ws_panel = WorkspacePanel(self)
        side.addTab(self.ws_panel, tr("side.workspace"))
        self.templates = TemplatesPanel(tr, self.context.settings)
        side.addTab(self.templates, tr("side.templates"))
        self.side = side
        split.addWidget(side)
        self.panel = self.services.chat_widget(system_extra=self._system_extra)
        split.addWidget(self.panel)
        self.viewer = FileViewer(tr)
        self.viewer.hide()
        split.addWidget(self.viewer)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        split.setSizes([260, 640, 480])
        self.split = split

        c = self.chats
        c.open_thread.connect(self.open_thread)
        c.new_chat.connect(self.new_chat)
        c.new_project.connect(self.new_project)
        c.select_project.connect(self.set_project)
        c.edit_project.connect(self.edit_project)
        c.delete_project.connect(self.delete_project)
        c.rename_thread.connect(self.rename_thread)
        c.delete_thread.connect(self.delete_thread)
        c.reveal.connect(self.reveal_chat)
        self.panel.threadSaved.connect(lambda tid, pid: self.chats.mark(tid, pid))
        self.templates.use.connect(self.use_template)
        w = self.ws_panel
        w.open_file.connect(lambda rel: self.show_file(rel))
        w.changed.connect(self.save_roots)
        w.open_access.connect(self.context.open_settings)
        v = self.viewer
        v.closed.connect(self.viewer.hide)
        v.attach.connect(lambda: self.attach_file(self.viewer.path))
        v.show_diff.connect(lambda: self.show_diff(self.viewer.path))
        v.reveal.connect(lambda: self.reveal(self.viewer.path))
        return split

    def _mode_changed(self, idx: int) -> None:
        w = self.modes.widget(idx)
        if hasattr(w, "refresh"):
            w.refresh()

    def use_template(self, text: str) -> None:
        self.modes.setCurrentIndex(0)
        self.panel.input.setPlainText(text)
        self.panel.focus_input()

    def screenshot(self, region: bool) -> None:
        def done(path, error):
            if error:
                self.notify(error)
            elif path is not None:
                self.image_to_chat(str(path))
        Screenshot(self.root.window(), self.storage, self.tr).take(region, done)

    def image_to_chat(self, path: str) -> None:
        self.panel.add_attachment(Path(path))
        self.modes.setCurrentIndex(0)
        self.panel.focus_input()

    # --- Projekte und Chats --------------------------------------------------------------------------
    def set_project(self, pid: str) -> None:
        project = self.storage.load_project(pid) if pid else None
        if pid and project is None:
            QMessageBox.warning(self.root, self.tr("chats.project"), self.tr("chats.unreadable"))
            pid = ""
        self.project = project
        self.context.settings.set("last_project", pid)
        if project is not None:
            self.roots = [dict(r) for r in project.get("workspace") or [] if isinstance(r, dict)]
        else:
            self.roots = [dict(r) for r in self.context.settings.get("workspace") or [] if isinstance(r, dict)]
        self._remotes = {}
        self.panel.set_project(project)
        self.chats.mark("", pid)
        self.ws_panel.set_scope(self.tr("ws.scope_project", name=project.get("name", "")) if project
                                else self.tr("ws.scope_general"))
        self.ws_panel.reload()
        self._update_level()

    def open_thread(self, tid: str, pid: str) -> None:
        if (self.project or {}).get("id", "") != pid:
            self.set_project(pid)
        self.panel.open_thread(tid, pid)
        self.chats.mark(tid, pid)

    def new_chat(self, pid: str) -> None:
        if (self.project or {}).get("id", "") != pid:
            self.set_project(pid)
        self.panel.new_chat()
        self.chats.mark("", pid)

    def new_project(self) -> None:
        from omniwrench.ui.ai_panel import ProjectDialog
        dlg = ProjectDialog(None, self.root)
        if dlg.exec():
            project = dict(dlg.project, workspace=[])
            self.storage.save_project(project)
            self.set_project(project["id"])

    def edit_project(self, pid: str) -> None:
        from omniwrench.ui.ai_panel import ProjectDialog
        project = self.storage.load_project(pid)
        if not project:
            return
        dlg = ProjectDialog(project, self.root)
        if dlg.exec():
            self.storage.save_project(dlg.project)
            if (self.project or {}).get("id") == pid:
                self.project = dlg.project
                self.panel.set_project(self.project)
            self.chats.reload()

    def delete_project(self, pid: str) -> None:
        project = self.storage.load_project(pid) or {"name": pid}
        if QMessageBox.question(self.root, self.tr("chats.delete_project"),
                                self.tr("chats.delete_project_q", name=project.get("name", pid))) \
                != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_project(pid)
        if (self.project or {}).get("id") == pid:
            self.set_project("")
        self.chats.reload()

    def rename_thread(self, tid: str, pid: str) -> None:
        from omniwrench.ai import chat
        thread = self.storage.load_thread(tid, pid)
        if not thread:
            return
        name, ok = QInputDialog.getText(self.root, self.tr("chats.rename"), self.tr("chats.title"),
                                        text=thread.get("title", ""))
        if ok and name.strip():
            thread["title"] = name.strip()
            self.storage.save_thread(thread, chat.thread_markdown(thread))
            if self.panel.thread and self.panel.thread.get("id") == tid:
                self.panel.thread["title"] = thread["title"]
            self.chats.reload()

    def delete_thread(self, tid: str, pid: str) -> None:
        if QMessageBox.question(self.root, self.tr("chats.delete"), self.tr("chats.delete_q")) \
                != QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_thread(tid, pid)
        if self.panel.thread and self.panel.thread.get("id") == tid:
            self.panel.new_chat()
        self.chats.mark("", pid)

    def reveal_chat(self, tid: str, pid: str) -> None:
        path = self.storage.thread_dir(tid, pid) if tid else self.storage.project_dir(pid)
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # --- Arbeitsbereich ------------------------------------------------------------------------------
    def save_roots(self) -> None:
        if self.project is not None:
            self.project["workspace"] = [dict(r) for r in self.roots]
            self.storage.save_project(self.project)
        else:
            self.context.settings.set("workspace", [dict(r) for r in self.roots])
        self._remotes = {k: v for k, v in self._remotes.items() if any(r["id"] == k for r in self.roots)}
        self.ws_panel.reload()
        self._update_level()

    def _update_level(self) -> None:
        if self.services is not None:
            self.ws_panel.update_level(self.services.level(self.context.manifest.id))

    def token_for(self, info: dict) -> str:
        return self.context.secrets.get(rm.token_key(info)) or ""

    def save_token(self, info: dict, token: str) -> None:
        self.context.secrets.set(rm.token_key(info), token)

    def remote_for(self, root: dict) -> rm.Remote:
        r = self._remotes.get(root["id"])
        if r is None:
            info = dict(root.get("remote") or {})
            r = rm.Remote(info, self.token_for(info), info.get("branch", ""))
            self._remotes[root["id"]] = r
        return r

    def clone_dir(self) -> str:
        d = self.context.settings.get("clone_dir") or ""
        return d or str(Path.home() / "OmniWrench-Repos")

    def notify(self, text: str) -> None:
        self.context.notify(text)

    def _system_extra(self) -> str:
        parts = ["You are running inside the KI-Studio tool (\"Clank\") of OmniWrench."]
        if self.roots:
            lines = []
            for r in self.roots:
                where = (r.get("remote") or {}).get("url", "") if r["kind"] == "remote" else r["kind"]
                lines.append(f"- {r['name']} ({where}{', read-only' if r.get('readonly') else ''})")
            parts.append("The user shared this workspace (use the studio_* functions; paths are relative, "
                         "starting with the entry name):\n" + "\n".join(lines))
            parts.append("Before changing files, read them first. When you propose a change, use "
                         "studio_write_file with the complete new content; for shell commands use studio_run_command "
                         "with a short explanation. The user confirms both.")
        else:
            parts.append("The workspace is empty; the user can add folders or repositories on the tab "
                         f"'{self.tr('side.workspace')}' in KI-Studio.")
        voice = getattr(self, "voice", None)
        if voice is not None and voice.system_hint():
            parts.append(voice.system_hint())
        return "\n\n".join(parts)

    # --- Dateiansicht --------------------------------------------------------------------------------
    def _workspace(self) -> wsm.Workspace:
        return wsm.Workspace(self.roots)

    def show_file(self, rel: str, quiet: bool = False) -> None:
        if quiet and not self.viewer.isVisible():
            return
        ws = self._workspace()
        try:
            root, sub = ws.split(rel)
        except wsm.WorkspaceError as e:
            self.notify(str(e))
            return
        if root["kind"] == "remote":
            self.viewer.show_text(rel, self.tr("ws.loading"))
            self.viewer.show()

            def done(res):
                text, cut = res
                self.viewer.show_text(rel, text, self.tr("viewer.truncated") if cut else "")

            def failed(text):
                self.viewer.show_text(rel, "", "⚠ " + text.splitlines()[0])
            run_async(lambda: self.remote_for(root).read(sub), done, failed)
            return
        try:
            out = ws.read(rel)
        except (wsm.WorkspaceError, OSError) as e:
            self.viewer.show_text(rel, "", "⚠ " + str(e))
            self.viewer.show()
            return
        if out.get("binary"):
            self.viewer.show_text(rel, "", self.tr("viewer.binary", size=out.get("size", 0)))
        else:
            info = self.tr("viewer.lines", n=out["lines"]) + (" · " + self.tr("viewer.truncated")
                                                               if out["truncated"] else "")
            self.viewer.show_text(rel, out["content"], info, git=root["kind"] == "git")
        self.viewer.show()

    def show_diff(self, rel: str) -> None:
        try:
            text = wsm.git_diff(self._workspace(), rel) or self.tr("viewer.no_changes")
        except wsm.WorkspaceError as e:
            text = str(e)
        self.viewer.show_text(rel, text, "", ext="diff")
        self.viewer.show()

    def file_changed(self, rel: str) -> None:
        self.notify(self.tr("ws.file_written", path=rel))
        if self.viewer.isVisible() and self.viewer.path == rel:
            self.show_file(rel)

    def command_ran(self, command: str, result: dict) -> None:
        text = f"> {command}\n\n{result.get('output', '')}"
        if result.get("errors"):
            text += f"\n--- stderr ---\n{result['errors']}"
        code = result.get("exit_code")
        info = self.tr("viewer.exit_code", code="–" if code is None else code)
        self.viewer.show_text(self.tr("viewer.command"), text, info, ext="ps1" if os.name == "nt" else "sh")
        self.viewer.show()

    def attach_file(self, rel: str) -> None:
        ws = self._workspace()
        try:
            root, sub = ws.split(rel)
            if root["kind"] == "remote":
                text = self.remote_for(root).read(sub)[0]
            else:
                text = ws.read(rel).get("content", "")
        except (wsm.WorkspaceError, OSError) as e:
            self.notify(str(e))
            return
        self.panel.add_text_attachment(rel, text[:100_000])
        self.panel.focus_input()

    def reveal(self, rel: str) -> None:
        try:
            _root, path = self._workspace().resolve(rel)
        except wsm.WorkspaceError as e:
            self.notify(str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))

    # --- Lebenszyklus --------------------------------------------------------------------------------
    def can_close(self) -> bool:
        panel = getattr(self, "panel", None)
        busy = panel is not None and panel._running
        busy = busy or any(getattr(getattr(self, n, None), "running", False)
                           for n in ("images", "music", "video", "group", "docs", "transcript"))
        if busy:
            return QMessageBox.question(self.root, self.tr("tool.name"), self.tr("ui.close_running")) \
                == QMessageBox.StandardButton.Yes
        return True

    def shutdown(self) -> None:
        panel = getattr(self, "panel", None)
        if panel is not None and panel._running:
            panel.stop()
        for name in ("images", "music", "video", "group"):
            tab = getattr(self, name, None)
            if tab is not None and tab.running:
                tab.stop()
        for name in ("docs", "plans", "transcript", "voice", "mcp"):
            tab = getattr(self, name, None)
            if tab is not None:
                tab.shutdown()
        timer = getattr(self, "_level_timer", None)
        if timer is not None:
            timer.stop()
