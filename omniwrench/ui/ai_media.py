"""Seite „Musik“ (Groovitron) und „Video“ (Vidcomic): erzeugen, abspielen und mit ffmpeg bearbeiten.

Gemeinsamer Code beider KI-Tools; die Texte kommen aus den Sprachdateien des jeweiligen Tools (host.tr).

Beide Seiten brauchen ffmpeg (Vorschaubilder, Kürzen, Umwandeln, Musik unterlegen) und sind ohne ffmpeg
ausgegraut – mit Knopf zum Herunterladen (Windows) bzw. dem Befehl für die Paketverwaltung (Linux).
"""

# i18n: tool-texts (Schlüssel stehen in den Sprachdateien von Groovitron und Vidcomic)

from __future__ import annotations

import mimetypes
import os
import threading
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSlider,
    QSpinBox, QSplitter, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from omniwrench.ai import audio
from omniwrench.ai import ffmpeg as ff

from .ai_kit import NoBotPage, output_device
from .workers import run_async

ICON = {"music": "♪", "video": "🎬"}


def _fmt(ms: int) -> str:
    s = max(0, ms) // 1000
    return f"{s // 60}:{s % 60:02d}"


class TrimDialog(QDialog):
    def __init__(self, tr, length: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("media.trim"))
        form = QFormLayout(self)
        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for s in (self.start, self.end):
            s.setRange(0, max(1.0, length or 3600))
            s.setDecimals(1)
            s.setSuffix(" s")
        self.end.setValue(length or 0)
        form.addRow(tr("media.trim_start"), self.start)
        form.addRow(tr("media.trim_end"), self.end)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        form.addRow(box)


class FFmpegPage(QWidget):
    """Ausgegraute Seite, solange ffmpeg fehlt."""
    changed = Signal()

    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        tr = tab.tr_
        lay = QVBoxLayout(self)
        lay.addStretch()
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.label)
        row = QHBoxLayout()
        row.addStretch()
        self.download = QPushButton("⬇ " + tr("ffmpeg.download"))
        self.download.clicked.connect(self._download)
        self.download.setVisible(os.name == "nt")
        row.addWidget(self.download)
        pick = QPushButton(tr("ffmpeg.pick"))
        pick.clicked.connect(self._pick)
        row.addWidget(pick)
        again = QPushButton(tr("ffmpeg.recheck"))
        again.clicked.connect(self.changed.emit)
        row.addWidget(again)
        row.addStretch()
        lay.addLayout(row)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status)
        lay.addStretch()
        text = tr("ffmpeg.missing", kind=tr("tool.name"))
        if os.name != "nt":
            text += "\n\n" + tr("ffmpeg.linux", cmd=ff.linux_hint())
        self.label.setText(text)

    def _download(self) -> None:
        tr = self.tab.tr_
        if QMessageBox.question(self, "ffmpeg", tr("ffmpeg.download_q", url=ff.WIN_URL)) \
                != QMessageBox.StandardButton.Yes:
            return
        self.download.setEnabled(False)
        self.status.setText(tr("ffmpeg.downloading", state=""))
        data_dir = audio.shared_dir()

        def done(path):
            self.download.setEnabled(True)
            self.status.setText(tr("ffmpeg.ready", path=path))
            self.changed.emit()

        def failed(text):
            self.download.setEnabled(True)
            self.status.setText("⚠ " + text.splitlines()[0])
        run_async(lambda progress: ff.download_windows(data_dir, progress), done, failed,
                  lambda s: self.status.setText(tr("ffmpeg.downloading", state=s)))

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tab.tr_("ffmpeg.pick"), "",
                                              "ffmpeg (ffmpeg.exe ffmpeg);;* (*)")
        if path:
            self.tab.studio.context.settings.set("ffmpeg_path", path)
            self.changed.emit()


class MediaTab(QWidget):
    def __init__(self, studio, kind: str):
        super().__init__()
        from omniwrench.ai import media
        self.media = media
        self.kind = kind
        self.studio = studio
        self.services = studio.services
        tr = self.tr_ = studio.tr
        self.refs: list[dict] = []
        self._stop: threading.Event | None = None
        self.ffmpeg = ""
        self.player = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.ff_page = FFmpegPage(self)
        self.ff_page.changed.connect(self.refresh)
        self.stack.addWidget(self.ff_page)
        self.stack.addWidget(NoBotPage(tr(f"{kind}.no_bot"), tr("ui.open_ai_options"), self.services.open_options))
        page = QWidget()
        self.stack.addWidget(page)
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split)

        # --- links: Auftrag
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.conn_box = QComboBox()
        self.conn_box.currentIndexChanged.connect(self._conn_changed)
        form.addRow(tr("img.connection"), self.conn_box)
        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        form.addRow(tr("img.model"), self.model_box)
        self.duration = QSpinBox()
        self.duration.setRange(0, 600 if kind == "music" else 60)
        self.duration.setSpecialValueText(tr("media.duration_auto"))
        self.duration.setSuffix(" s")
        self.duration.setValue(0 if kind == "music" else 5)
        form.addRow(tr("media.duration"), self.duration)
        if kind == "video":
            self.aspect = QComboBox()
            for a in media.VIDEO_ASPECTS:
                self.aspect.addItem(tr("img.aspect." + a.replace(":", "_")), a)
            form.addRow(tr("img.aspect"), self.aspect)
            self.resolution = QComboBox()
            for r in media.RESOLUTIONS:
                self.resolution.addItem(r, r)
            form.addRow(tr("media.resolution"), self.resolution)
        else:
            self.instrumental = QCheckBox(tr("music.instrumental"))
            form.addRow("", self.instrumental)
        fl.addLayout(form)
        fl.addWidget(QLabel(tr("img.prompt")))
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText(tr(f"{kind}.prompt_hint"))
        fl.addWidget(self.prompt, 2)
        if kind == "music":
            fl.addWidget(QLabel(tr("music.lyrics")))
            self.lyrics = QPlainTextEdit()
            self.lyrics.setPlaceholderText(tr("music.lyrics_hint"))
            fl.addWidget(self.lyrics, 2)
            self.instrumental.toggled.connect(lambda on: self.lyrics.setEnabled(not on))
        else:
            ref_row = QHBoxLayout()
            self.ref_btn = QPushButton("🖼 " + tr("video.start_image"))
            self.ref_btn.clicked.connect(self._pick_ref)
            ref_row.addWidget(self.ref_btn)
            self.ref_label = QLabel()
            ref_row.addWidget(self.ref_label, 1)
            clear = QToolButton(text="✕")
            clear.clicked.connect(lambda: self._set_ref(None))
            ref_row.addWidget(clear)
            fl.addLayout(ref_row)
        go_row = QHBoxLayout()
        self.go = QPushButton("✦ " + tr("img.generate"))
        self.go.clicked.connect(self._go_or_stop)
        go_row.addWidget(self.go)
        go_row.addStretch()
        fl.addLayout(go_row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        fl.addWidget(self.status)
        hint = QLabel(tr(f"{kind}.cost_hint"))
        hint.setWordWrap(True)
        hint.setEnabled(False)
        fl.addWidget(hint)
        split.addWidget(fw)

        # --- Mitte: Dateien
        self.files = QListWidget()
        self.files.setIconSize(QSize(96, 54) if kind == "video" else QSize(24, 24))
        self.files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._menu)
        self.files.currentItemChanged.connect(lambda cur, _p: self._select(cur))
        self.files.itemDoubleClicked.connect(lambda _it: self.toggle_play())
        split.addWidget(self.files)

        # --- rechts: Wiedergabe und Bearbeitung
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.setContentsMargins(0, 0, 0, 0)
        self.video_widget = None
        self._build_player(rl)
        ctl = QHBoxLayout()
        self.play_btn = QToolButton(text="▶")
        self.play_btn.clicked.connect(self.toggle_play)
        ctl.addWidget(self.play_btn)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player and self.player.setPosition(v))
        ctl.addWidget(self.slider, 1)
        self.time = QLabel("0:00")
        ctl.addWidget(self.time)
        rl.addLayout(ctl)
        self.meta = QLabel(tr("media.select"))
        self.meta.setWordWrap(True)
        self.meta.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(self.meta)
        edit = QHBoxLayout()
        self.edit_buttons = []
        actions = [("media.trim", self.trim)]
        if kind == "video":
            actions += [("video.add_music", self.add_music), ("video.to_gif", self.to_gif),
                        ("video.mute", self.mute), ("video.still", self.still)]
        else:
            actions += [("music.to_mp3", self.to_mp3)]
        for key, slot in actions:
            b = QPushButton(tr(key))
            b.clicked.connect(slot)
            edit.addWidget(b)
            self.edit_buttons.append(b)
        edit.addStretch()
        rl.addLayout(edit)
        split.addWidget(rw)
        split.setSizes([320, 360, 520])
        self._current: Path | None = None
        self._update_edit()

    # --- Wiedergabe ----------------------------------------------------------------------------------
    def _build_player(self, layout) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            if self.kind == "video":
                from PySide6.QtMultimediaWidgets import QVideoWidget
                self.video_widget = QVideoWidget()
                self.video_widget.setMinimumSize(320, 180)
                self.player.setVideoOutput(self.video_widget)
                layout.addWidget(self.video_widget, 1)
            else:
                art = QLabel("♪")
                art.setAlignment(Qt.AlignmentFlag.AlignCenter)
                art.setStyleSheet("font-size: 64pt; color: #8b5cf6;")
                layout.addWidget(art, 1)
            self.player.positionChanged.connect(self._position)
            self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
            self.player.playbackStateChanged.connect(self._state)
        except Exception:  # noqa: BLE001 - ohne QtMultimedia: extern öffnen
            self.player = None
            msg = QLabel(self.tr_("media.no_player"))
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(msg, 1)

    def _position(self, pos: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(int(pos))
        dur = self.player.duration() if self.player else 0
        self.time.setText(f"{_fmt(pos)} / {_fmt(dur)}")

    def _state(self, state) -> None:
        from PySide6.QtMultimedia import QMediaPlayer
        self.play_btn.setText("⏸" if state == QMediaPlayer.PlaybackState.PlayingState else "▶")

    def toggle_play(self) -> None:
        if self._current is None:
            return
        if self.player is None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._current)))
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.audio.setDevice(output_device(self.services.settings))   # aktuelles Standardgerät
            self.player.play()

    # --- Verbindungen ---------------------------------------------------------------------------------
    def refresh(self) -> None:
        ctx = self.studio.context
        self.ffmpeg = ff.find(ctx.settings, audio.shared_dir())
        conns = self.media.connections_for(self.services.connections, self.kind)
        if not self.ffmpeg:
            self.stack.setCurrentIndex(0)
            return
        keep = self.services.default(self.kind) or self.conn_box.currentData() or ""
        self.conn_box.blockSignals(True)
        self.conn_box.clear()
        for c in conns:
            self.conn_box.addItem(c.name, c.id)
        self.conn_box.setCurrentIndex(max(0, self.conn_box.findData(keep)))
        self.conn_box.blockSignals(False)
        self.stack.setCurrentIndex(2 if conns else 1)
        if conns:
            self._conn_changed()
        self.reload()

    def connection(self):
        cid = self.conn_box.currentData()
        return self.services.connections.get(cid) if cid else None

    def _conn_changed(self, *_):
        conn = self.connection()
        if conn is None:
            return
        settings = self.studio.context.settings
        self.services.set_default(self.kind, conn.id)
        last = (settings.get(f"{self.kind}_models") or {}).get(conn.id, "")
        self.model_box.clear()
        for m in self.media.models(conn, self.kind):
            self.model_box.addItem(m)
        if last:
            self.model_box.setCurrentText(last)

    def _pick_ref(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr_("video.start_image"), "",
                                              self.tr_("img.image_filter") + " (*.png *.jpg *.jpeg *.webp)")
        if path:
            self._set_ref(Path(path))

    def _set_ref(self, path: Path | None) -> None:
        self.refs = []
        if path is not None:
            try:
                self.refs = [{"name": path.name, "mime": mimetypes.guess_type(path.name)[0] or "image/png",
                              "data": path.read_bytes()}]
            except OSError as e:
                self.status.setText("⚠ " + str(e))
        self.ref_label.setText(path.name if path is not None and self.refs else "")

    # --- Erzeugen ------------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._stop is not None

    def _go_or_stop(self) -> None:
        if self.running:
            self.stop()
        else:
            self.generate()

    def generate(self) -> bool:
        conn = self.connection()
        prompt = self.prompt.toPlainText().strip()
        tr = self.tr_
        if conn is None or not prompt:
            self.status.setText(tr("img.need_prompt") if conn else tr(f"{self.kind}.no_bot"))
            return False
        media = self.media
        model = self.model_box.currentText().strip()
        settings = self.studio.context.settings
        models = dict(settings.get(f"{self.kind}_models") or {})
        models[conn.id] = model
        settings.set(f"{self.kind}_models", models)
        req = media.Request(prompt=prompt, model=model, duration=self.duration.value())
        meta = {"prompt": prompt, "model": model, "connection": conn.id, "connection_name": conn.name,
                "provider": conn.provider, "duration": req.duration}
        if self.kind == "music":
            req.instrumental = self.instrumental.isChecked()
            req.lyrics = "" if req.instrumental else self.lyrics.toPlainText().strip()
            meta.update(instrumental=req.instrumental, lyrics=req.lyrics)
        else:
            req.aspect = self.aspect.currentData()
            req.resolution = self.resolution.currentData()
            req.references = [{"mime": r["mime"], "data": r["data"]} for r in self.refs]
            meta.update(aspect=req.aspect, resolution=req.resolution,
                        start_image=self.refs[0]["name"] if self.refs else "")
        stop = self._stop = threading.Event()
        self.go.setText("■ " + tr("img.stop"))
        self.status.setText(tr(f"{self.kind}.working", name=conn.name))
        store, storage, ffmpeg, kind = self.services.connections, self.services.storage, self.ffmpeg, self.kind

        def task(progress):
            from omniwrench.ai import chat
            from omniwrench.ai.http import Cancelled
            try:
                items = media.generate(store, conn, kind, req, stop, progress)
                if stop.is_set():
                    return ("stopped", None)
                paths = []
                for m in items:
                    path = media.save(storage, kind, m, dict(meta))
                    if kind == "music" and path.suffix.lower() == ".wav":
                        try:   # MP3 ist überall abspielbar; WAV bleibt daneben liegen
                            mp3 = ff.to_mp3(ffmpeg, path, path.with_suffix(".mp3"))
                            mp3.with_suffix(".mp3.json").write_text(
                                path.with_suffix(".wav.json").read_text(encoding="utf-8"), encoding="utf-8")
                            path = mp3
                        except ff.FFmpegError:
                            pass
                    paths.append(str(path))
                return ("ok", paths)
            except Cancelled:
                return ("stopped", None)
            except Exception as err:  # noqa: BLE001 - als Text anzeigen
                return ("error", chat.error_text(err))

        run_async(task, lambda res: self._done(stop, res), lambda text: self._done(stop, ("error", text)),
                  lambda state: stop is self._stop and state and self.status.setText(tr("img.waiting", state=state)))
        return True

    def _done(self, stop, res) -> None:
        if stop is not self._stop:
            return
        self._stop = None
        self.go.setText("✦ " + self.tr_("img.generate"))
        kind, value = res
        if kind == "ok":
            self.status.setText(self.tr_("media.done", n=len(value)))
            self.reload(select=value[0] if value else "")
        elif kind == "stopped":
            self.status.setText(self.tr_("img.stopped"))
        else:
            self.status.setText("⚠ " + str(value))

    def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
            self._stop = None
            self.go.setText("✦ " + self.tr_("img.generate"))
            self.status.setText(self.tr_("img.stopped"))
        if self.player is not None:
            self.player.stop()

    # --- Dateien -------------------------------------------------------------------------------------
    def _poster(self, path: Path) -> QIcon:
        if self.kind != "video" or not self.ffmpeg:
            return QIcon()
        cache = path.with_name(path.name + ".poster.png")
        if not cache.exists():
            try:
                ff.poster(self.ffmpeg, path, cache)
            except ff.FFmpegError:
                return QIcon()
        return QIcon(QPixmap(str(cache)))

    def reload(self, select: str = "") -> None:
        self.files.clear()
        for path in self.media.list_files(self.services.storage, self.kind):
            meta = self.media.read_meta(path)
            title = meta.get("prompt") or path.stem
            title = (title[:60] + "…") if len(title) > 60 else title
            item = QListWidgetItem(self._poster(path), f"{ICON[self.kind]} {title}\n{path.name}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.files.addItem(item)
            if select and str(path) == select:
                self.files.setCurrentItem(item)

    def _path(self, item) -> Path | None:
        return Path(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _select(self, item) -> None:
        path = self._path(item)
        self._current = path
        self._update_edit()
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl.fromLocalFile(str(path)) if path else QUrl())
        if path is None:
            self.meta.setText(self.tr_("media.select"))
            return
        m = self.media.read_meta(path)
        lines = [x for x in (m.get("prompt"), " · ".join(str(v) for v in (
            m.get("connection_name"), m.get("model"), m.get("aspect"), m.get("resolution")) if v)) if x]
        if m.get("edit"):
            lines.append(self.tr_("media.edited", edit=m["edit"], source=m.get("source", "")))
        if m.get("lyrics"):
            lines.append(m["lyrics"][:600])
        lines.append(path.name)
        self.meta.setText("\n\n".join(lines))

    def _update_edit(self) -> None:
        for b in self.edit_buttons:
            b.setEnabled(self._current is not None and bool(self.ffmpeg))
        if self.kind == "music" and self._current is not None and self._current.suffix.lower() == ".mp3":
            self.edit_buttons[1].setEnabled(False)     # schon MP3

    def _menu(self, pos) -> None:
        path = self._path(self.files.itemAt(pos))
        if path is None:
            return
        tr = self.tr_
        menu = QMenu(self)
        menu.addAction(tr("img.open"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        menu.addAction(tr("img.reveal"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))))
        menu.addAction(tr("img.reuse"), lambda: self.reuse(path))
        menu.addSeparator()
        menu.addAction(tr("img.delete"), lambda: self.delete(path))
        menu.exec(self.files.viewport().mapToGlobal(pos))

    def reuse(self, path: Path) -> None:
        m = self.media.read_meta(path)
        self.prompt.setPlainText(m.get("prompt", ""))
        idx = self.conn_box.findData(m.get("connection", ""))
        if idx >= 0:
            self.conn_box.setCurrentIndex(idx)
        if m.get("model"):
            self.model_box.setCurrentText(m["model"])
        self.duration.setValue(int(m.get("duration") or 0))
        if self.kind == "music":
            self.instrumental.setChecked(bool(m.get("instrumental")))
            self.lyrics.setPlainText(m.get("lyrics", "") if not m.get("instrumental") else "")

    def delete(self, path: Path) -> None:
        if QMessageBox.question(self, self.tr_("img.delete"), self.tr_("media.delete_q", name=path.name)) \
                != QMessageBox.StandardButton.Yes:
            return
        if self.player is not None:
            self.player.setSource(QUrl())
        for f in (path, path.with_name(path.name + ".json"), path.with_name(path.name + ".poster.png")):
            try:
                f.unlink()
            except OSError:
                pass
        self._current = None
        self.reload()

    # --- Bearbeiten (ffmpeg) -------------------------------------------------------------------------
    def _edit(self, edit: str, suffix: str, fn, kind: str | None = None) -> None:
        """Bearbeitung im Hintergrund; Ergebnis als neue Datei mit Beschreibung neben dem Original."""
        src = self._current
        if src is None or not self.ffmpeg:
            return
        kind = kind or self.kind
        storage = self.services.storage
        meta = dict(self.media.read_meta(src))
        meta.update(edit=edit, source=src.name, kind=kind)
        stem = " ".join(str(meta.get("prompt") or src.stem).split()[:6]) + f"-{edit}"
        dst = storage.media_target(self.media.STORE_KIND[kind], stem, suffix)
        self.status.setText(self.tr_("media.editing"))

        def task():
            fn(src, dst)
            import json
            dst.with_name(dst.name + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                                         encoding="utf-8")
            return str(dst)

        def done(path):
            self.status.setText(self.tr_("media.edited_saved", name=Path(path).name))
            if kind == self.kind:
                self.reload(select=path)

        run_async(task, done, lambda text: self.status.setText("⚠ " + text.splitlines()[-1]))

    def _length(self) -> float:
        if self.player is not None and self.player.duration() > 0:
            return self.player.duration() / 1000
        return ff.duration(self.ffmpeg, self._current) if self._current else 0.0

    def trim(self) -> None:
        if self._current is None:
            return
        dlg = TrimDialog(self.tr_, self._length(), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        start, end = dlg.start.value(), dlg.end.value()
        self._edit("trim", self._current.suffix, lambda s, d: ff.trim(self.ffmpeg, s, d, start, end))

    def to_mp3(self) -> None:
        self._edit("mp3", ".mp3", lambda s, d: ff.to_mp3(self.ffmpeg, s, d))

    def to_gif(self) -> None:
        self._edit("gif", ".gif", lambda s, d: ff.to_gif(self.ffmpeg, s, d), kind="image")

    def mute(self) -> None:
        self._edit("mute", ".mp4", lambda s, d: ff.mute(self.ffmpeg, s, d))

    def still(self) -> None:
        at = (self.player.position() / 1000) if self.player is not None else 0.5
        self._edit("still", ".png", lambda s, d: ff._run(self.ffmpeg, ["-ss", f"{at:.2f}", "-i", str(s),
                                                                     "-frames:v", "1", str(d)], 60), kind="image")

    def add_music(self) -> None:
        tracks = self.media.list_files(self.services.storage, "music")
        tr = self.tr_
        names = [p.name for p in tracks] + [tr("video.other_file")]
        name, ok = QInputDialog.getItem(self, tr("video.add_music"), tr("video.pick_music"), names, 0, False)
        if not ok:
            return
        if name == names[-1]:
            path, _ = QFileDialog.getOpenFileName(self, tr("video.add_music"), "", "Audio (*.mp3 *.wav *.ogg *.flac *.m4a)")
            if not path:
                return
            audio = Path(path)
        else:
            audio = tracks[names.index(name)]
        self._edit("music", ".mp4", lambda s, d: ff.mux(self.ffmpeg, s, audio, d))
