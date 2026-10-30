"""Orvus – Zeitpläne: Fragen an den Assistenten zu festen Zeiten (einmalig, täglich, wöchentlich, alle N Stunden).

Zeitpläne liegen in der Tool-Einstellung "schedules" und laufen, solange Orvus geöffnet ist (Prüfung alle 30 s);
verpasste Läufe holt Orvus beim nächsten Öffnen nach, wenn „nachholen“ gesetzt ist. Jeder Lauf wird ein neuer
Chat (im gewählten Projekt). Funktionen der Stufe 4 (Änderungen) werden bei geplanten Läufen nie ausgeführt –
niemand kann bestätigen. Die Logik oben ist Qt-frei (testbar).
"""

from __future__ import annotations

import datetime as dt
import secrets
import threading
import time

KINDS = ("once", "daily", "weekly", "interval")
CHECK_MS = 30_000


def _hm(text: str) -> tuple[int, int]:
    try:
        h, m = (int(x) for x in str(text or "08:00").split(":")[:2])
        return max(0, min(23, h)), max(0, min(59, m))
    except ValueError:
        return 8, 0


def next_run(job: dict, after: dt.datetime) -> float | None:
    """Nächster Zeitpunkt (Unix-Zeit) strikt nach after, None = kein weiterer Lauf."""
    kind = job.get("kind", "daily")
    h, m = _hm(job.get("time"))
    if kind == "once":
        try:
            day = dt.date.fromisoformat(job.get("date") or "")
        except ValueError:
            return None
        when = dt.datetime.combine(day, dt.time(h, m))
        return when.timestamp() if when > after else None
    if kind == "interval":
        hours = max(1, int(job.get("hours") or 1))
        last = job.get("last_run")
        base = dt.datetime.fromtimestamp(last) if last else after
        when = base + dt.timedelta(hours=hours) if last else after + dt.timedelta(minutes=1)
        while when <= after:
            when += dt.timedelta(hours=hours)
        return when.timestamp()
    days = sorted({int(d) for d in job.get("weekdays") or []} & set(range(7))) if kind == "weekly" else list(range(7))
    if not days:
        return None
    for add in range(0, 8):
        day = after.date() + dt.timedelta(days=add)
        if day.weekday() not in days:
            continue
        when = dt.datetime.combine(day, dt.time(h, m))
        if when > after:
            return when.timestamp()
    return None


def new_job(name: str, prompt: str, kind: str = "daily", time_: str = "08:00") -> dict:
    return {"id": secrets.token_hex(4), "name": name, "prompt": prompt, "connection": "", "project": "",
            "kind": kind, "time": time_, "date": dt.date.today().isoformat(), "weekdays": [0], "hours": 4,
            "enabled": True, "catch_up": True, "last_run": 0, "next_run": None, "last_status": "",
            "last_thread": ""}


def plan(job: dict, now: float, opened: bool = False) -> dict:
    """Setzt next_run. Beim Öffnen gilt ein verpasster Lauf nur mit catch_up als fällig."""
    job = dict(job)
    if not job.get("enabled"):
        job["next_run"] = None
        return job
    nxt = job.get("next_run")
    if nxt and nxt <= now and opened and not job.get("catch_up", True):
        nxt = None
    if not nxt:
        nxt = next_run(job, dt.datetime.fromtimestamp(now))
    job["next_run"] = nxt
    return job


def due(jobs: list[dict], now: float) -> list[dict]:
    return [j for j in jobs if j.get("enabled") and j.get("next_run") and j["next_run"] <= now]


def after_run(job: dict, now: float, status: str, thread_id: str = "") -> dict:
    job = dict(job, last_run=now, last_status=status, last_thread=thread_id or job.get("last_thread", ""))
    if job.get("kind") == "once":
        job["enabled"] = False
        job["next_run"] = None
    else:
        job["next_run"] = next_run(job, dt.datetime.fromtimestamp(now))
    return job


def describe(job: dict, tr) -> str:
    kind = job.get("kind", "daily")
    t = job.get("time", "08:00")
    if kind == "once":
        return tr("plan.desc.once", date=job.get("date", ""), time=t)
    if kind == "interval":
        return tr("plan.desc.interval", n=job.get("hours", 1))
    if kind == "weekly":
        days = ", ".join(tr(f"plan.day.{d}") for d in sorted(job.get("weekdays") or []))
        return tr("plan.desc.weekly", days=days, time=t)
    return tr("plan.desc.daily", time=t)


# ------------------------------------------------------------------ Ausführung (Hintergrund)
def run_job(services, tool_id: str, job: dict, project: dict | None, window, stop: threading.Event) -> dict:
    """Führt einen Zeitplan als neuen Chat aus und speichert ihn. Gibt den Thread zurück."""
    from omniwrench.ai import access, chat, functions
    from omniwrench.ai.pseudo import Pseudonymizer
    from omniwrench.ui.workers import call_in_gui
    store, settings = services.connections, services.settings
    from omniwrench.ai import defaults
    conn = store.get(job.get("connection") or "") or store.get(defaults.get(settings, "schedule")) or store.primary()
    if conn is None:
        raise RuntimeError("no assistant")
    thread = chat.new_thread(conn, "normal", (project or {}).get("id", ""))
    thread["title"] = f"⏰ {job.get('name', '')} · {time.strftime('%d.%m. %H:%M')}"
    thread["scheduled"] = job.get("id", "")
    thread["messages"].append({"role": "user", "content": job.get("prompt", ""), "ts": int(time.time())})
    pstate = thread["state"].setdefault("pseudo", {})
    kinds = access.pseudo_kinds(settings)
    pseudo = Pseudonymizer(pstate, kinds, enabled=access.pseudo_enabled(settings, "app"))

    def encode_result(source, value):
        p = Pseudonymizer(pstate, kinds, enabled=access.pseudo_enabled(settings, source))
        return functions.format_result(p.encode_value(value))

    def in_gui(fn):
        out = []
        call_in_gui(lambda: out.append(fn()))
        return out[0] if out else None

    extra = ("This question was started automatically by a schedule in Orvus; nobody is watching. Changes "
             "(functions that need confirmation) are declined automatically, so only read and report.")
    hooks = chat.RunHooks(confirm=lambda fn, args: False,
                          level_for=lambda source: access.level(settings, source, conn.id),
                          encode=pseudo.encode, decode=pseudo.decode, encode_result=encode_result,
                          call_context=functions.CallContext(window=window, connection=conn, in_gui=in_gui,
                                                             stop=stop))
    system = chat.system_prompt("normal", project, extra)
    try:
        chat.run(store, conn, thread, system, hooks, stop)
    finally:
        services.storage.save_thread(thread, chat.thread_markdown(thread))
    return thread


# ------------------------------------------------------------------ Oberfläche
from PySide6.QtCore import QDate, Qt, QTime, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTimeEdit,
    QVBoxLayout, QWidget,
)

from omniwrench.sdk import run_async  # noqa: E402


class JobDialog(QDialog):
    def __init__(self, tab, job: dict):
        super().__init__(tab)
        tr = tab.tr_
        self.job = dict(job)
        self.setWindowTitle(tr("plan.edit"))
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(job.get("name", ""))
        form.addRow(tr("plan.name"), self.name)
        self.conn = QComboBox()
        self.conn.addItem(tr("plan.primary"), "")
        for c in tab.services.connections.chat_connections():
            self.conn.addItem(c.name, c.id)
        self.conn.setCurrentIndex(max(0, self.conn.findData(job.get("connection", ""))))
        form.addRow(tr("plan.assistant"), self.conn)
        self.project = QComboBox()
        self.project.addItem(tr("plan.no_project"), "")
        for p in tab.services.storage.list_projects():
            if not p.get("locked"):
                self.project.addItem(p.get("name", p["id"]), p["id"])
        self.project.setCurrentIndex(max(0, self.project.findData(job.get("project", ""))))
        form.addRow(tr("plan.project"), self.project)
        self.kind = QComboBox()
        for k in KINDS:
            self.kind.addItem(tr("plan.kind." + k), k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(job.get("kind", "daily"))))
        form.addRow(tr("plan.kind"), self.kind)
        self.date = QDateEdit(QDate.fromString(job.get("date") or "", "yyyy-MM-dd"))
        if not self.date.date().isValid():
            self.date.setDate(QDate.currentDate())
        self.date.setCalendarPopup(True)
        form.addRow(tr("plan.date"), self.date)
        h, m = _hm(job.get("time"))
        self.time = QTimeEdit(QTime(h, m))
        form.addRow(tr("plan.time"), self.time)
        days = QWidget()
        dl = QHBoxLayout(days)
        dl.setContentsMargins(0, 0, 0, 0)
        self.days = []
        for d in range(7):
            c = QCheckBox(tr(f"plan.day.{d}"))
            c.setChecked(d in (job.get("weekdays") or []))
            dl.addWidget(c)
            self.days.append(c)
        form.addRow(tr("plan.weekdays"), days)
        self.days_row = days
        self.hours = QSpinBox()
        self.hours.setRange(1, 168)
        self.hours.setValue(int(job.get("hours") or 4))
        self.hours.setSuffix(" h")
        form.addRow(tr("plan.hours"), self.hours)
        self.catch_up = QCheckBox(tr("plan.catch_up"))
        self.catch_up.setChecked(job.get("catch_up", True))
        form.addRow("", self.catch_up)
        self.enabled = QCheckBox(tr("plan.enabled"))
        self.enabled.setChecked(job.get("enabled", True))
        form.addRow("", self.enabled)
        lay.addLayout(form)
        lay.addWidget(QLabel(tr("plan.prompt")))
        self.prompt = QPlainTextEdit(job.get("prompt", ""))
        self.prompt.setPlaceholderText(tr("plan.prompt_hint"))
        lay.addWidget(self.prompt, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._ok)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._form = form
        self._kind_changed()

    def _kind_changed(self, *_):
        k = self.kind.currentData()
        for w, show in ((self.date, k == "once"), (self.time, k != "interval"), (self.days_row, k == "weekly"),
                        (self.hours, k == "interval")):
            w.setVisible(show)
            label = self._form.labelForField(w)
            if label is not None:
                label.setVisible(show)

    def _ok(self) -> None:
        if not self.name.text().strip() or not self.prompt.toPlainText().strip():
            return
        self.job.update(name=self.name.text().strip(), prompt=self.prompt.toPlainText().strip(),
                        connection=self.conn.currentData(), project=self.project.currentData(),
                        kind=self.kind.currentData(), date=self.date.date().toString("yyyy-MM-dd"),
                        time=self.time.time().toString("HH:mm"), hours=self.hours.value(),
                        weekdays=[d for d, c in enumerate(self.days) if c.isChecked()],
                        catch_up=self.catch_up.isChecked(), enabled=self.enabled.isChecked(), next_run=None)
        self.accept()


class ScheduleTab(QWidget):
    COLS = ("name", "when", "next", "last", "status")
    _owner = None        # nur ein geöffnetes Clank führt Zeitpläne aus (mehrere Tabs möglich)

    def __init__(self, studio):
        super().__init__()
        self.studio = studio
        self.services = studio.services
        self.settings = studio.context.settings
        tr = self.tr_ = studio.tr
        self._stop = threading.Event()
        self._busy = ""
        self._closed = False
        lay = QVBoxLayout(self)
        info = QLabel(tr("plan.info"))
        info.setWordWrap(True)
        info.setEnabled(False)
        lay.addWidget(info)
        row = QHBoxLayout()
        for key, slot in (("plan.new", self.new), ("plan.edit", self.edit), ("plan.delete", self.delete),
                          ("plan.run_now", self.run_now), ("plan.open", self.open_result)):
            b = QPushButton(tr(key))
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([tr("plan.col." + c) for c in self.COLS])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(lambda _it: self.edit())
        lay.addWidget(self.table, 1)
        self.status = QLabel()
        lay.addWidget(self.status)
        now = time.time()
        self.save_jobs([plan(j, now, opened=True) for j in self.jobs()])
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(CHECK_MS)
        QTimer.singleShot(2000, self.tick)

    # --- Daten ---------------------------------------------------------------------------------------
    def jobs(self) -> list[dict]:
        return [dict(j) for j in self.settings.get("schedules") or [] if isinstance(j, dict) and j.get("id")]

    def save_jobs(self, jobs: list[dict]) -> None:
        self.settings.set("schedules", jobs)
        self.render()

    def _update(self, job: dict) -> None:
        self.save_jobs([job if j["id"] == job["id"] else j for j in self.jobs()])

    def render(self) -> None:
        tr = self.tr_
        jobs = self.jobs()
        sel = self.selected_id()
        self.table.setRowCount(len(jobs))
        fmt = lambda ts: time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts else "–"  # noqa: E731
        for r, j in enumerate(jobs):
            status = j.get("last_status") or ""
            if self._busy == j["id"]:
                status = tr("plan.running")
            elif status == "ok":
                status = "✓ " + tr("plan.ok")
            elif status:
                status = "⚠ " + status
            vals = (("" if j.get("enabled") else "⏸ ") + j.get("name", ""), describe(j, tr),
                    fmt(j.get("next_run")), fmt(j.get("last_run")), status)
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setData(Qt.ItemDataRole.UserRole, j["id"])
                self.table.setItem(r, c, item)
            if j["id"] == sel:
                self.table.selectRow(r)

    def selected_id(self) -> str:
        items = self.table.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else ""

    def selected(self) -> dict | None:
        sid = self.selected_id()
        return next((j for j in self.jobs() if j["id"] == sid), None)

    # --- Bearbeiten ----------------------------------------------------------------------------------
    def new(self) -> None:
        job = new_job("", "")
        dlg = JobDialog(self, job)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.save_jobs(self.jobs() + [plan(dlg.job, time.time())])

    def edit(self) -> None:
        job = self.selected()
        if job is None:
            return
        dlg = JobDialog(self, job)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._update(plan(dlg.job, time.time()))

    def delete(self) -> None:
        job = self.selected()
        if job is None:
            return
        if QMessageBox.question(self, self.tr_("plan.delete"), self.tr_("plan.delete_q", name=job["name"])) \
                == QMessageBox.StandardButton.Yes:
            self.save_jobs([j for j in self.jobs() if j["id"] != job["id"]])

    def run_now(self) -> None:
        job = self.selected()
        if job is not None:
            self.start(job)

    def open_result(self) -> None:
        job = self.selected()
        if job is None or not job.get("last_thread"):
            return
        self.services.open_thread(job["last_thread"], job.get("project", ""))

    # --- Ausführen -----------------------------------------------------------------------------------
    def tick(self) -> None:
        if self._closed:
            return
        if ScheduleTab._owner is None:
            ScheduleTab._owner = self
        if self._busy or ScheduleTab._owner is not self:
            return
        jobs = due(self.jobs(), time.time())
        if jobs:
            self.start(jobs[0])

    def start(self, job: dict) -> bool:
        if self._busy:
            self.status.setText(self.tr_("plan.busy"))
            return False
        self._busy = job["id"]
        self.render()
        project = self.services.storage.load_project(job["project"]) if job.get("project") else None
        services, tool_id = self.services, self.studio.context.manifest.id
        window, stop = self.services.window, self._stop

        def task():
            from omniwrench.ai import chat
            try:
                thread = run_job(services, tool_id, job, project, window, stop)
                errors = [m for m in thread["messages"] if m["role"] == "error"]
                return ("ok" if not errors else errors[-1]["content"][:120], thread["id"])
            except Exception as err:  # noqa: BLE001 - Status in der Liste
                return (chat.error_text(err)[:160], "")

        run_async(task, lambda res: self._done(job["id"], *res),
                  lambda text: self._done(job["id"], text.splitlines()[0][:160], ""))
        return True

    def _done(self, job_id: str, status: str, thread_id: str) -> None:
        self._busy = ""
        job = next((j for j in self.jobs() if j["id"] == job_id), None)
        if job is None:
            self.render()
            return
        job = after_run(job, time.time(), status, thread_id)
        self._update(job)
        self.studio.context.notify(self.tr_("plan.notify_ok" if status == "ok" else "plan.notify_error",
                                                name=job["name"], status=status))

    def shutdown(self) -> None:
        self._closed = True
        self.timer.stop()
        self._stop.set()
        if ScheduleTab._owner is self:
            ScheduleTab._owner = None
