"""Reiter „MCP“: fremde MCP-Server anbinden (Client) und OmniWrench selbst als MCP-Server anbieten.

Client: Werkzeuge der verbundenen Server werden als Funktionen dieses Tools registriert (Quelle ai.clank), gelten
also mit der KI-Zugriffsstufe des KI-Studios: lesende Werkzeuge (nur bei „Server vertrauen“ erkennbar) ab Stufe 3,
alle anderen ab Stufe 4 mit Bestätigung. Sie stehen im KI-Studio und in der Chatleiste bereit, solange das
KI-Studio offen ist.
Server: omniwrench/ai/mcp_server.py, läuft solange das KI-Studio offen ist (nur eine Instanz, wie Zeitpläne).
"""

from __future__ import annotations

import json
import sys
import threading
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QStackedWidget,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from omniwrench.ai import mcp
from omniwrench.ai import mcp_server as mcps
from omniwrench.sdk import run_async

SERVERS_KEY = "mcp_servers"
LOG_MAX = 50


def _lines_to_dict(text: str, sep: str) -> dict:
    out = {}
    for line in text.splitlines():
        if sep in line:
            k, _, v = line.partition(sep)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


def bridge_command() -> tuple[str, list[str]]:
    """Befehl, mit dem ein stdio-Client die Brücke startet."""
    from omniwrench.core.paths import APP_DIR
    if getattr(sys, "frozen", False):
        return sys.executable, ["--mcp-stdio"]
    return sys.executable, [str(APP_DIR / "main.py"), "--mcp-stdio"]


def client_config(kind: str, url: str, token: str) -> str:
    if kind == "stdio":
        cmd, args = bridge_command()
        data = {"mcpServers": {"omniwrench": {"command": cmd, "args": args}}}
    elif kind == "vscode":
        data = {"servers": {"omniwrench": {"type": "http", "url": url,
                                           "headers": {"Authorization": f"Bearer {token}"}}}}
    else:
        data = {"mcpServers": {"omniwrench": {"type": "http", "url": url,
                                              "headers": {"Authorization": f"Bearer {token}"}}}}
    return json.dumps(data, indent=2, ensure_ascii=False)


class ServerDialog(QDialog):
    def __init__(self, tr, server: dict, token: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("mcp.edit") if server.get("name") else tr("mcp.add"))
        self.resize(600, 520)
        self.server = dict(server)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(server.get("name", ""))
        form.addRow(tr("mcp.name"), self.name)
        self.kind = QComboBox()
        self.kind.addItem(tr("mcp.kind.stdio"), "stdio")
        self.kind.addItem(tr("mcp.kind.http"), "http")
        self.kind.setCurrentIndex(max(self.kind.findData(server.get("transport", "stdio")), 0))
        form.addRow(tr("mcp.kind"), self.kind)
        lay.addLayout(form)

        self.stack = QStackedWidget()
        page = QWidget()
        f = QFormLayout(page)
        f.setContentsMargins(0, 0, 0, 0)
        self.command = QLineEdit(server.get("command", ""))
        self.command.setPlaceholderText("npx")
        f.addRow(tr("mcp.command"), self.command)
        self.args = QLineEdit(" ".join(f'"{a}"' if " " in a else a for a in server.get("args") or []))
        self.args.setPlaceholderText("-y @modelcontextprotocol/server-filesystem C:\\Daten")
        f.addRow(tr("mcp.args"), self.args)
        self.cwd = QLineEdit(server.get("cwd", ""))
        f.addRow(tr("mcp.cwd"), self.cwd)
        self.env = QPlainTextEdit("\n".join(f"{k}={v}" for k, v in (server.get("env") or {}).items()))
        self.env.setPlaceholderText("NAME=Wert")
        self.env.setFixedHeight(70)
        f.addRow(tr("mcp.env"), self.env)
        warn = QLabel("⚠ " + tr("mcp.stdio_warning"))
        warn.setWordWrap(True)
        f.addRow(warn)
        self.stack.addWidget(page)

        page = QWidget()
        f = QFormLayout(page)
        f.setContentsMargins(0, 0, 0, 0)
        self.url = QLineEdit(server.get("url", ""))
        self.url.setPlaceholderText("https://example.com/mcp")
        f.addRow(tr("mcp.url"), self.url)
        self.token = QLineEdit(token)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText(tr("mcp.token_hint"))
        f.addRow(tr("mcp.token"), self.token)
        self.headers = QPlainTextEdit("\n".join(f"{k}: {v}" for k, v in (server.get("headers") or {}).items()))
        self.headers.setPlaceholderText("X-Api-Key: …")
        self.headers.setFixedHeight(70)
        f.addRow(tr("mcp.headers"), self.headers)
        self.stack.addWidget(page)
        lay.addWidget(self.stack)
        self.kind.currentIndexChanged.connect(lambda: self.stack.setCurrentIndex(self.kind.currentIndex()))
        self.stack.setCurrentIndex(self.kind.currentIndex())

        self.trusted = QCheckBox(tr("mcp.trusted"))
        self.trusted.setChecked(bool(server.get("trusted")))
        self.trusted.setToolTip(tr("mcp.trusted_tip"))
        lay.addWidget(self.trusted)
        self.enabled = QCheckBox(tr("mcp.enabled"))
        self.enabled.setChecked(server.get("enabled", True))
        lay.addWidget(self.enabled)
        lay.addStretch()
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def _ok(self) -> None:
        http = self.kind.currentData() == "http"
        if not self.name.text().strip() or (http and not self.url.text().strip()) \
                or (not http and not self.command.text().strip()):
            return
        self.accept()

    def result_server(self) -> dict:
        s = dict(self.server)
        s.update(name=self.name.text().strip(), transport=self.kind.currentData(),
                 command=self.command.text().strip(), args=mcp.split_args(self.args.text()),
                 cwd=self.cwd.text().strip(), env=_lines_to_dict(self.env.toPlainText(), "="),
                 url=self.url.text().strip(), headers=_lines_to_dict(self.headers.toPlainText(), ":"),
                 trusted=self.trusted.isChecked(), enabled=self.enabled.isChecked())
        return s


class ToolsDialog(QDialog):
    """Werkzeuge eines Servers ein-/ausschalten."""

    def __init__(self, tr, server: dict, tools: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("mcp.tools_title", name=server.get("name", "")))
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        hint = QLabel(tr("mcp.tools_hint"))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.table = QTableWidget(len(tools), 3)
        self.table.setHorizontalHeaderLabels([tr("mcp.col.tool"), tr("mcp.col.kind"), tr("mcp.col.desc")])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        off = set(server.get("disabled_tools") or [])
        trusted = bool(server.get("trusted"))
        for row, t in enumerate(tools):
            item = QTableWidgetItem(t.get("title") or t["name"])
            item.setData(Qt.ItemDataRole.UserRole, t["name"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked if t["name"] in off else Qt.CheckState.Checked)
            self.table.setItem(row, 0, item)
            ro = mcp.is_read_only(t, trusted)
            self.table.setItem(row, 1, QTableWidgetItem(tr("mcp.read") if ro else tr("mcp.change")))
            desc = QTableWidgetItem((t.get("description") or "").split("\n")[0][:200])
            desc.setToolTip(t.get("description") or "")
            self.table.setItem(row, 2, desc)
        self.table.resizeColumnsToContents()
        lay.addWidget(self.table, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def disabled(self) -> list[str]:
        out = []
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if it.checkState() != Qt.CheckState.Checked:
                out.append(it.data(Qt.ItemDataRole.UserRole))
        return out


class MCPTab(QWidget):
    _owner = None                          # nur ein KI-Studio betreibt den Server
    _called = Signal(str, bool)
    _state = Signal(str)                   # Server-ID, deren Status sich geändert hat

    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.tr_ = tr = studio.tr
        self.ctx = studio.context
        self.settings = self.ctx.settings
        self.clients: dict[str, mcp.Client] = {}
        self.status: dict[str, dict] = {}
        self.registered: dict[str, list[str]] = {}
        self.server: mcps.Server | None = None
        self._closed = False
        self._lock = threading.Lock()

        lay = QVBoxLayout(self)
        intro = QLabel(tr("mcp.intro"))
        intro.setWordWrap(True)
        lay.addWidget(intro)

        # --- Client ---------------------------------------------------------------------------------
        box = QGroupBox(tr("mcp.client_title"))
        bl = QVBoxLayout(box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr("mcp.col.name"), tr("mcp.col.kind"), tr("mcp.col.status")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        bl.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, slot in (("＋ " + tr("mcp.add"), self.add), (tr("mcp.edit"), self.edit),
                           (tr("mcp.tools"), self.show_tools), (tr("mcp.reconnect"), self.reconnect),
                           (tr("mcp.remove"), self.remove)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        bl.addLayout(row)
        hint = QLabel(tr("mcp.client_hint"))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        bl.addWidget(hint)
        lay.addWidget(box, 3)

        # --- Server ---------------------------------------------------------------------------------
        box = QGroupBox(tr("mcp.server_title"))
        sl = QVBoxLayout(box)
        row = QHBoxLayout()
        self.on = QCheckBox(tr("mcp.server_on"))
        self.on.setChecked(bool(self.settings.get("mcp_server_on")))
        self.on.toggled.connect(self._toggle_server)
        row.addWidget(self.on)
        row.addWidget(QLabel(tr("mcp.port")))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(self.settings.get("mcp_server_port") or mcps.DEFAULT_PORT))
        self.port.valueChanged.connect(lambda v: self.settings.set("mcp_server_port", int(v)))
        row.addWidget(self.port)
        row.addStretch()
        self.copy_btn = QToolButton(text="⧉ " + tr("mcp.copy_config"))
        self.copy_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.copy_btn)
        menu.addAction(tr("mcp.cfg.stdio"), lambda: self._copy_config("stdio"))
        menu.addAction(tr("mcp.cfg.vscode"), lambda: self._copy_config("vscode"))
        menu.addAction(tr("mcp.cfg.http"), lambda: self._copy_config("http"))
        menu.addSeparator()
        menu.addAction(tr("mcp.cfg.token"), self._copy_token)
        menu.addAction(tr("mcp.cfg.new_token"), self._new_token)
        self.copy_btn.setMenu(menu)
        row.addWidget(self.copy_btn)
        sl.addLayout(row)
        self.server_status = QLabel()
        self.server_status.setWordWrap(True)
        self.server_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        sl.addWidget(self.server_status)
        self.log = QListWidget()
        self.log.setMaximumHeight(110)
        sl.addWidget(self.log)
        hint = QLabel(tr("mcp.server_hint"))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        sl.addWidget(hint)
        lay.addWidget(box, 2)

        self._called.connect(self._log_call)
        self._state.connect(lambda _sid: self.render())
        self.render()
        self._update_server_status()
        for s in self.servers():
            if s.get("enabled", True):
                self.connect_server(s)
        if self.on.isChecked():
            self._toggle_server(True)

    # --- Einstellungen ----------------------------------------------------------------------------
    def servers(self) -> list[dict]:
        return [dict(s) for s in self.settings.get(SERVERS_KEY) or [] if isinstance(s, dict) and s.get("id")]

    def save_servers(self, servers: list[dict]) -> None:
        self.settings.set(SERVERS_KEY, servers)

    def _token(self, sid: str) -> str:
        try:
            return self.ctx.secrets.get(mcp.secret_key(sid)) or ""
        except Exception:  # noqa: BLE001 - Tresor gesperrt
            return ""

    def selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        sid = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((s for s in self.servers() if s["id"] == sid), None)

    def render(self) -> None:
        tr = self.tr_
        servers = self.servers()
        current = (self.selected() or {}).get("id")
        self.table.setRowCount(len(servers))
        for row, s in enumerate(servers):
            name = QTableWidgetItem(s.get("name", ""))
            name.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(tr(f"mcp.kind.{s.get('transport', 'stdio')}")))
            st = self.status.get(s["id"]) or {}
            state = st.get("state") or ("off" if not s.get("enabled", True) else "idle")
            if state == "ok":
                text = "● " + tr("mcp.state.ok", count=len(self.registered.get(s["id"], [])),
                                 version=st.get("version", ""))
            elif state == "error":
                text = "⚠ " + tr("mcp.state.error", error=st.get("error", ""))
            else:
                text = tr(f"mcp.state.{state}")
            item = QTableWidgetItem(text)
            item.setToolTip(st.get("error") or st.get("instructions") or "")
            self.table.setItem(row, 2, item)
            if s["id"] == current:
                self.table.selectRow(row)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(1)

    # --- Client -----------------------------------------------------------------------------------
    def connect_server(self, server: dict) -> None:
        sid = server["id"]
        self.disconnect_server(sid)
        if not server.get("enabled", True):
            self.render()
            return
        self.status[sid] = {"state": "connecting"}
        self.render()
        token = self._token(sid)

        def work():
            client = mcp.Client(server, token)
            client.connect()
            try:
                tools = client.tools()
            except Exception:
                client.close()
                raise
            return client, tools

        def done(result):
            client, tools = result
            if self._closed or not any(s["id"] == sid for s in self.servers()):
                client.close()
                return
            with self._lock:
                self.clients[sid] = client
            self.status[sid] = {"state": "ok", "tools": tools, "version": client.version,
                                "instructions": client.instructions}
            self._register(server, client, tools)
            self.render()

        def failed(err):
            self.status[sid] = {"state": "error", "error": str(err)}
            self.render()
        run_async(work, done, failed)

    def disconnect_server(self, sid: str) -> None:
        from omniwrench.ai import functions
        for name in self.registered.pop(sid, []):
            functions.unregister(name)
        with self._lock:
            client = self.clients.pop(sid, None)
        self.status.pop(sid, None)
        if client is not None:
            threading.Thread(target=client.close, daemon=True).start()

    def _register(self, server: dict, client: mcp.Client, tools: list[dict]) -> None:
        from omniwrench.sdk import AI_CHANGE, AI_READ
        add = getattr(self.ctx, "ai_function", None)
        if add is None:
            return
        tr = self.tr_
        off = set(server.get("disabled_tools") or [])
        names = []
        for t in tools:
            if t["name"] in off:
                continue
            fname = mcp.function_name(server, t["name"])
            if fname in names:
                continue
            ro = mcp.is_read_only(t, bool(server.get("trusted")))
            desc = f"[MCP server '{server.get('name', '')}'] {t.get('description') or t.get('title') or t['name']}"
            tool_name = t["name"]

            def handler(args, call, _tool=tool_name):
                return mcp.result_text(client.call_tool(_tool, args, stop=call.stop))

            def summary(args, _t=t):
                return {"text": tr("mcp.confirm_call", tool=_t.get("title") or _t["name"],
                                   server=server.get("name", "")),
                        "code": json.dumps(args, ensure_ascii=False, indent=1),
                        "explanation": (_t.get("description") or "")[:400]}
            add(fname, desc[:1024], handler, parameters=mcp.clean_schema(t.get("inputSchema")),
                level=AI_READ if ro else AI_CHANGE, summary=None if ro else summary)
            names.append(fname)
        self.registered[server["id"]] = names

    def add(self) -> None:
        dlg = ServerDialog(self.tr_, mcp.new_server(""), "", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        s = dlg.result_server()
        self._save_token(s["id"], dlg.token.text().strip())
        self.save_servers(self.servers() + [s])
        self.connect_server(s)

    def edit(self) -> None:
        cur = self.selected()
        if cur is None:
            return
        dlg = ServerDialog(self.tr_, cur, self._token(cur["id"]), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        s = dlg.result_server()
        self._save_token(s["id"], dlg.token.text().strip())
        self.save_servers([s if x["id"] == s["id"] else x for x in self.servers()])
        self.connect_server(s)

    def _save_token(self, sid: str, token: str) -> None:
        try:
            self.ctx.secrets.set(mcp.secret_key(sid), token)
        except Exception as err:  # noqa: BLE001 - Tresor gesperrt
            if token:
                QMessageBox.warning(self, self.tr_("mcp.title"), self.tr_("mcp.vault_locked", error=str(err)))

    def remove(self) -> None:
        cur = self.selected()
        if cur is None:
            return
        if QMessageBox.question(self, self.tr_("mcp.remove"), self.tr_("mcp.remove_q", name=cur["name"])) \
                != QMessageBox.StandardButton.Yes:
            return
        self.disconnect_server(cur["id"])
        self._save_token(cur["id"], "")
        self.save_servers([x for x in self.servers() if x["id"] != cur["id"]])
        self.render()

    def reconnect(self) -> None:
        cur = self.selected()
        if cur is not None:
            self.connect_server(cur)

    def show_tools(self) -> None:
        cur = self.selected()
        if cur is None:
            return
        tools = (self.status.get(cur["id"]) or {}).get("tools")
        if not tools:
            QMessageBox.information(self, self.tr_("mcp.title"), self.tr_("mcp.no_tools"))
            return
        dlg = ToolsDialog(self.tr_, cur, tools, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cur["disabled_tools"] = dlg.disabled()
        self.save_servers([cur if x["id"] == cur["id"] else x for x in self.servers()])
        from omniwrench.ai import functions
        for name in self.registered.pop(cur["id"], []):
            functions.unregister(name)
        client = self.clients.get(cur["id"])
        if client is not None:
            self._register(cur, client, tools)
        self.render()

    def _menu(self, pos) -> None:
        if self.table.itemAt(pos) is None:
            return
        tr = self.tr_
        menu = QMenu(self)
        menu.addAction(tr("mcp.edit"), self.edit)
        menu.addAction(tr("mcp.tools"), self.show_tools)
        menu.addAction(tr("mcp.reconnect"), self.reconnect)
        menu.addSeparator()
        menu.addAction(tr("mcp.remove"), self.remove)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # --- Server -----------------------------------------------------------------------------------
    def _server_token(self) -> str:
        token = ""
        try:
            token = self.ctx.secrets.get("mcp_server_token") or ""
        except Exception:  # noqa: BLE001
            pass
        if not token:
            token = mcps.new_token()
            try:
                self.ctx.secrets.set("mcp_server_token", token)
            except Exception:  # noqa: BLE001 - dann nur für diese Sitzung
                pass
        return token

    def _confirm(self, fn, args) -> bool:
        from omniwrench.ui.ai_panel import ConfirmDialog
        from omniwrench.ui.workers import call_in_gui
        tr = self.tr_
        try:
            text = fn.summary(args) if fn.summary else f"{fn.name}\n{args}"
        except Exception:  # noqa: BLE001
            text = f"{fn.name}\n{args}"
        out = []

        def ask():
            info = text if isinstance(text, dict) else {"text": str(text)}
            info = {**info, "text": tr("mcp.server_confirm") + "\n\n" + info.get("text", "")}
            dlg = ConfirmDialog(tr("mcp.server_confirm_title"), info, self)
            dlg.remember.hide()
            out.append(dlg.exec() == QDialog.DialogCode.Accepted)
        call_in_gui(ask)
        return bool(out and out[0])

    def _in_gui(self, fn):
        from omniwrench.ui.workers import call_in_gui
        out = []
        call_in_gui(lambda: out.append(fn()))
        return out[0] if out else None

    def _toggle_server(self, on: bool) -> None:
        self.settings.set("mcp_server_on", bool(on))
        if not on:
            self.stop_server()
            self._update_server_status()
            return
        if MCPTab._owner is not None and MCPTab._owner is not self:
            self._update_server_status(self.tr_("mcp.server_other"))
            return
        host = mcps.FunctionHost(self.studio.services.settings, confirm=self._confirm, in_gui=self._in_gui, window=self.window(),
                                 on_call=lambda name, ok: self._called.emit(name, ok))
        self.server = mcps.Server(host, self.port.value(), self._server_token())
        try:
            self.server.start()
        except OSError as err:
            self.server = None
            self._update_server_status(self.tr_("mcp.server_failed", error=str(err)))
            return
        MCPTab._owner = self
        self.port.setEnabled(False)
        self._update_server_status()

    def stop_server(self) -> None:
        if self.server is not None:
            self.server.stop()
            self.server = None
        if MCPTab._owner is self:
            MCPTab._owner = None
        self.port.setEnabled(True)

    def _update_server_status(self, error: str = "") -> None:
        tr = self.tr_
        if error:
            self.server_status.setText("⚠ " + error)
        elif self.server is not None and self.server.running:
            n = len(self.server.core.host.functions())
            self.server_status.setText("● " + tr("mcp.server_running", url=self.server.url, count=n))
        else:
            self.server_status.setText(tr("mcp.server_off"))
        self.copy_btn.setEnabled(self.server is not None)

    def _copy_config(self, kind: str) -> None:
        if self.server is None:
            return
        QGuiApplication.clipboard().setText(client_config(kind, self.server.url, self.server.token))
        self.ctx.notify(self.tr_("mcp.copied"))

    def _copy_token(self) -> None:
        if self.server is not None:
            QGuiApplication.clipboard().setText(self.server.token)
            self.ctx.notify(self.tr_("mcp.copied"))

    def _new_token(self) -> None:
        if QMessageBox.question(self, self.tr_("mcp.title"), self.tr_("mcp.new_token_q")) \
                != QMessageBox.StandardButton.Yes:
            return
        token = mcps.new_token()
        try:
            self.ctx.secrets.set("mcp_server_token", token)
        except Exception:  # noqa: BLE001
            pass
        if self.server is not None:
            self.server.token = token
            mcps.write_info(self.server.port, token)

    def _log_call(self, name: str, ok: bool) -> None:
        self.log.insertItem(0, f"{time.strftime('%H:%M:%S')}  {'✓' if ok else '✗'}  {name}")
        while self.log.count() > LOG_MAX:
            self.log.takeItem(self.log.count() - 1)
        self._update_server_status()

    def shutdown(self) -> None:
        self._closed = True
        self.stop_server()
        for sid in list(self.clients):
            self.disconnect_server(sid)
