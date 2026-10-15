"""Einstellungsdialoge: tool-spezifisch (aus config.json generiert) und Hauptprogramm."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from omniwrench.core import i18n, net
from omniwrench.core.i18n import AUTO, Translator, tr
from omniwrench.core.manifest import SettingDef
from omniwrench.core.settings import AppSettings
from omniwrench.core.tool_manager import InstalledTool
from omniwrench.core.vault import Vault
from omniwrench.sdk import LANGUAGE_KEY

from .credentials import CredentialField, PasswordManagerWidget
from .login_dialog import MIN_PASSWORD_LENGTH, CertificateCombo
from .widgets import label, make_button, tool_icon
from .workers import run_async


# ====================================================================== Felder
class _Field:
    """Verbindet eine SettingDef mit ihrem Eingabe-Widget.

    Texte werden über den Übersetzer des Tools geholt:
        settings.<key>.label / .description / .placeholder / .option.<wert>
    Fehlt ein Schlüssel, wird der Text aus config.json verwendet.
    """

    def __init__(self, sdef: SettingDef, value: Any, t: Translator):
        self.sdef = sdef
        self.t = t
        self.widget = self._build(sdef, value)

    def text(self, attr: str) -> str:
        return self.t.tr(f"settings.{self.sdef.key}.{attr}", getattr(self.sdef, attr) or "")

    def _password_edit(self, value: str, placeholder: str = "") -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(value or "")
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText(placeholder or self.text("placeholder") or tr("settings.secret_placeholder"))
        eye = make_button("👁")
        eye.setCheckable(True)
        eye.setFixedWidth(36)
        eye.setToolTip(tr("settings.show_password"))
        eye.toggled.connect(lambda on: edit.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        lay.addWidget(edit, 1)
        lay.addWidget(eye)
        box.edit = edit
        return box

    def _path_edit(self, value: str, directory: bool) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(value or "")
        edit.setPlaceholderText(self.text("placeholder"))

        def browse():
            if directory:
                path = QFileDialog.getExistingDirectory(box, self.text("label"), edit.text())
            else:
                path, _ = QFileDialog.getOpenFileName(box, self.text("label"), edit.text())
            if path:
                edit.setText(path)

        lay.addWidget(edit, 1)
        btn = make_button("…", on_click=browse)
        btn.setToolTip(tr("settings.browse"))
        lay.addWidget(btn)
        box.edit = edit
        return box

    def _build(self, s: SettingDef, value: Any) -> QWidget:
        t = s.type
        if t == "string":
            w = QLineEdit("" if value is None else str(value))
            w.setPlaceholderText(self.text("placeholder"))
        elif t == "text":
            w = QPlainTextEdit("" if value is None else str(value))
            w.setFixedHeight(90)
        elif t == "int":
            w = QSpinBox()
            w.setRange(int(s.min if s.min is not None else -2_000_000_000), int(s.max if s.max is not None else 2_000_000_000))
            w.setValue(int(value or 0))
        elif t == "float":
            w = QDoubleSpinBox()
            w.setDecimals(3)
            w.setRange(s.min if s.min is not None else -1e12, s.max if s.max is not None else 1e12)
            w.setValue(float(value or 0))
        elif t == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
        elif t == "choice":
            w = QComboBox()
            for opt in s.options:
                val, lbl = (opt["value"], opt.get("label", str(opt["value"]))) if isinstance(opt, dict) else (opt, str(opt))
                w.addItem(self.t.tr(f"settings.{s.key}.option.{val}", lbl), val)
            idx = w.findData(value)
            w.setCurrentIndex(max(idx, 0))
        elif t in ("path_file", "path_dir"):
            w = self._path_edit(value, directory=(t == "path_dir"))
        elif t == "secret":
            w = self._password_edit(value)
        elif t == "credential":
            w = CredentialField(value or {})
        elif t == "certificate":
            w = CertificateCombo(only_encryption=False)
            w.set_thumbprint(value or "")
        else:
            w = QLineEdit(str(value))
        if self.text("description"):
            w.setToolTip(self.text("description"))
        return w

    def value(self) -> Any:
        t, w = self.sdef.type, self.widget
        if t == "string":
            return w.text()
        if t == "text":
            return w.toPlainText()
        if t in ("int", "float"):
            return w.value()
        if t == "bool":
            return w.isChecked()
        if t == "choice":
            return w.currentData()
        if t in ("path_file", "path_dir", "secret"):
            return w.edit.text()
        if t == "credential":
            return w.value()
        if t == "certificate":
            return w.thumbprint()
        return w.text()

    def is_empty(self) -> bool:
        v = self.value()
        if self.sdef.type == "credential":
            return not v["username"]
        return v in ("", None)


def build_settings_form(schema: list[SettingDef], values: dict[str, Any],
                        t: Translator) -> tuple[QWidget, list[_Field]]:
    """Erzeugt aus einem Einstellungsschema ein Formular (bei mehreren Gruppen mit Tabs)."""
    groups: dict[str, list[SettingDef]] = {}
    for s in schema:
        groups.setdefault(s.group or "", []).append(s)
    fields: list[_Field] = []

    def group_title(name: str) -> str:
        return t.tr(f"settings.group.{name}", name) if name else tr("settings.group_general")

    def make_page(defs: list[SettingDef]) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(10)
        for s in defs:
            f = _Field(s, values.get(s.key), t)
            fields.append(f)
            form.addRow(f.text("label") + (" *" if s.required else ""), f.widget)
            if f.text("description"):
                form.addRow("", label(f.text("description"), "Muted", wrap=True))
        return page

    if len(groups) <= 1:
        return make_page(schema), fields
    tabs = QTabWidget()
    for name, defs in groups.items():
        tabs.addTab(make_page(defs), group_title(name))
    return tabs, fields


class ToolSettingsDialog(QDialog):
    def __init__(self, tool: InstalledTool, parent: QWidget | None = None):
        super().__init__(parent)
        self.tool = tool
        self.language_changed = False
        m = tool.manifest
        self.setWindowTitle(tr("settings.tool_title", name=m.display_name))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)

        head = QHBoxLayout()
        icon = label("")
        icon.setPixmap(tool_icon(m, tool.path, 40).pixmap(40, 40))
        head.addWidget(icon)
        title = QVBoxLayout()
        title.addWidget(label(m.display_name, "CardTitle"))
        title.addWidget(label(f"{tr('common.version', version=m.version)} · {' › '.join(m.category_path)}",
                              "CardMeta"))
        head.addLayout(title, 1)
        lay.addLayout(head)

        # --- Sprache des Tools
        lang_row = QFormLayout()
        self.language = QComboBox()
        available = sorted(i18n.load_locales(tool.path / "locales"))
        current = tool.settings.get(LANGUAGE_KEY) or AUTO
        auto_lang = i18n.resolve_tool_language(set(available), AUTO)
        self.language.addItem(tr("settings.language_auto", language=i18n.native_name(auto_lang)), AUTO)
        for code in available:
            self.language.addItem(i18n.native_name(code), code)
        self.language.setCurrentIndex(max(self.language.findData(current), 0))
        self.language.setToolTip(tr("settings.tool_language_hint"))
        lang_row.addRow(tr("settings.tool_language"), self.language)
        if not available:
            self.language.setEnabled(False)
        lay.addLayout(lang_row)

        translator = i18n.tool_translator(tool.path, current)
        if not tool.schema:
            lay.addWidget(label(tr("settings.no_settings"), "Muted"))
            self.fields = []
        else:
            form, self.fields = build_settings_form(tool.schema, tool.settings.all(), translator)
            lay.addWidget(form, 1)
            if any(f.sdef.is_secret for f in self.fields):
                lay.addWidget(label("🔒 " + tr("settings.secrets_hint"), "Muted"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _save(self) -> None:
        missing = [f.text("label") for f in self.fields if f.sdef.required and f.is_empty()]
        if missing:
            QMessageBox.warning(self, tr("settings.required_title"),
                                tr("settings.required_text") + "\n- " + "\n- ".join(missing))
            return
        values = {f.sdef.key: f.value() for f in self.fields}
        new_lang = self.language.currentData()
        self.language_changed = new_lang != (self.tool.settings.get(LANGUAGE_KEY) or AUTO)
        values[LANGUAGE_KEY] = new_lang
        self.tool.settings.update(values)
        self.accept()


# ============================================================ Hauptprogramm
class AppSettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, vault: Vault, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        self.vault = vault
        self.language_changed = False
        self.setWindowTitle(tr("appsettings.title"))
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), tr("appsettings.tab_general"))
        tabs.addTab(self._repo_tab(), tr("appsettings.tab_repos"))
        tabs.addTab(self._update_tab(), tr("appsettings.tab_updates"))
        tabs.addTab(self._security_tab(), tr("appsettings.tab_security"))
        pwm = QWidget()
        pwm_lay = QVBoxLayout(pwm)
        pwm_lay.addWidget(PasswordManagerWidget(pwm))
        tabs.addTab(pwm, tr("pwm.title"))
        self.tabs = tabs
        lay.addWidget(tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # ----- Allgemein
    def _general_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.language = QComboBox()
        for info in i18n.language_infos():
            text = info.native if info.native == info.name else f"{info.native}  ({info.name})"
            self.language.addItem(text, info.code)
        self.language.setCurrentIndex(max(self.language.findData(i18n.current_language()), 0))
        form.addRow(tr("appsettings.language"), self.language)
        form.addRow("", label(tr("appsettings.language_hint"), "Muted", wrap=True))
        self.theme = QComboBox()
        self.theme.addItem(tr("appsettings.theme_dark"), "dark")
        self.theme.addItem(tr("appsettings.theme_light"), "light")
        self.theme.setCurrentIndex(max(self.theme.findData(self.settings.get("theme")), 0))
        form.addRow(tr("appsettings.theme"), self.theme)
        self.restore_layout = QCheckBox(tr("appsettings.restore_layout"))
        self.restore_layout.setChecked(self.settings.get("restore_layout", True))
        form.addRow("", self.restore_layout)
        self.auto_lock = QSpinBox()
        self.auto_lock.setRange(0, 600)
        self.auto_lock.setSuffix(" " + tr("appsettings.minutes"))
        self.auto_lock.setSpecialValueText(tr("appsettings.disabled"))
        self.auto_lock.setValue(int(self.settings.get("auto_lock_minutes", 0)))
        form.addRow(tr("appsettings.auto_lock"), self.auto_lock)
        return page

    # ----- Repositories
    def _repo_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(label(tr("appsettings.repos_hint"), "Muted", wrap=True))
        self.repo_table = QTableWidget(0, 3)
        self.repo_table.setHorizontalHeaderLabels([tr("appsettings.repo_active"), tr("appsettings.repo_name"), "URL"])
        self.repo_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.repo_table.verticalHeader().hide()
        for repo in self.settings.get("repositories", []):
            self._add_repo_row(repo)
        lay.addWidget(self.repo_table, 1)
        row = QHBoxLayout()
        row.addWidget(make_button(tr("common.add"),
                                  on_click=lambda: self._add_repo_row({"name": "", "url": "", "enabled": True})))
        row.addWidget(make_button(tr("common.remove"),
                                  on_click=lambda: self.repo_table.removeRow(self.repo_table.currentRow())))
        row.addStretch()
        lay.addLayout(row)
        return page

    def _add_repo_row(self, repo: dict) -> None:
        r = self.repo_table.rowCount()
        self.repo_table.insertRow(r)
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        chk.setCheckState(Qt.CheckState.Checked if repo.get("enabled", True) else Qt.CheckState.Unchecked)
        self.repo_table.setItem(r, 0, chk)
        self.repo_table.setItem(r, 1, QTableWidgetItem(repo.get("name", "")))
        self.repo_table.setItem(r, 2, QTableWidgetItem(repo.get("url", "")))

    # ----- Updates
    def _update_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.update_repo = QLineEdit(self.settings.get("app_update_repo", ""))
        self.update_repo.setPlaceholderText("owner/repository")
        form.addRow(tr("appsettings.update_repo"), self.update_repo)
        self.check_start = QCheckBox(tr("appsettings.check_on_start"))
        self.check_start.setChecked(self.settings.get("check_updates_on_start", True))
        form.addRow("", self.check_start)
        self.prerelease = QCheckBox(tr("appsettings.prereleases"))
        self.prerelease.setChecked(self.settings.get("include_prereleases", False))
        form.addRow("", self.prerelease)
        self.token = QLineEdit(self.vault.get("app:github_token", "") or "")
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText(tr("appsettings.token_placeholder"))
        form.addRow(tr("appsettings.token"), self.token)
        return page

    # ----- Sicherheit
    def _security_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.addWidget(label(tr("appsettings.unlock_methods"), "CardTitle"))
        self.unlocker_list = QListWidget()
        lay.addWidget(self.unlocker_list, 1)
        row = QHBoxLayout()
        row.addWidget(make_button(tr("appsettings.set_password"), on_click=self._change_password))
        row.addWidget(make_button(tr("appsettings.add_cert"), on_click=self._add_certificate))
        row.addWidget(make_button(tr("common.remove"), danger=True, on_click=self._remove_unlocker))
        row.addStretch()
        lay.addLayout(row)
        self._refresh_unlockers()
        return page

    def _refresh_unlockers(self) -> None:
        self.unlocker_list.clear()
        for u in self.vault.unlockers():
            if u["type"] == "password":
                text = "🔑  " + tr("appsettings.method_password")
            else:
                text = "🔐  " + tr("appsettings.method_cert", subject=u["subject"], date=u.get("not_after", "?"))
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, u)
            self.unlocker_list.addItem(item)

    def _change_password(self) -> None:
        title = tr("appsettings.method_password")
        pw, ok = QInputDialog.getText(self, title, tr("appsettings.new_password", min=MIN_PASSWORD_LENGTH),
                                      QLineEdit.EchoMode.Password)
        if not ok:
            return
        if len(pw) < MIN_PASSWORD_LENGTH:
            QMessageBox.warning(self, title, tr("login.err_short", min=MIN_PASSWORD_LENGTH))
            return
        pw2, ok = QInputDialog.getText(self, title, tr("login.password_repeat"), QLineEdit.EchoMode.Password)
        if not ok or pw != pw2:
            QMessageBox.warning(self, title, tr("login.err_mismatch"))
            return
        self.vault.change_password(pw)
        self._refresh_unlockers()
        QMessageBox.information(self, title, tr("appsettings.password_saved"))

    def _add_certificate(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("appsettings.add_cert_title"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(label(tr("appsettings.add_cert_text"), wrap=True))
        combo = CertificateCombo()
        lay.addWidget(combo)
        status = label("", "Muted", wrap=True)
        lay.addWidget(status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(buttons)
        buttons.rejected.connect(dlg.reject)

        def accept():
            thumb = combo.thumbprint()
            if not thumb:
                return
            buttons.setEnabled(False)
            status.setText(tr("login.cert_busy"))
            run_async(lambda: self.vault.add_certificate(thumb), lambda _: dlg.accept(),
                      lambda err: (status.setText(tr("common.error_short", error=err)), buttons.setEnabled(True)))

        buttons.accepted.connect(accept)
        if dlg.exec():
            self._refresh_unlockers()

    def _remove_unlocker(self) -> None:
        item = self.unlocker_list.currentItem()
        if not item:
            return
        u = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, tr("common.remove"), tr("appsettings.remove_method_confirm")) \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            self.vault.remove_unlocker(u["type"], u.get("thumbprint"))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("common.remove"), str(exc))
        self._refresh_unlockers()

    # ----- Speichern
    def _save(self) -> None:
        repos = []
        for r in range(self.repo_table.rowCount()):
            url = (self.repo_table.item(r, 2).text() if self.repo_table.item(r, 2) else "").strip()
            if not url:
                continue
            repos.append({
                "enabled": self.repo_table.item(r, 0).checkState() == Qt.CheckState.Checked,
                "name": (self.repo_table.item(r, 1).text() if self.repo_table.item(r, 1) else "").strip() or url,
                "url": url,
            })
        s = self.settings
        new_lang = self.language.currentData()
        self.language_changed = new_lang != i18n.current_language()
        s.set("language", new_lang, save=False)
        s.set("repositories", repos, save=False)
        s.set("theme", self.theme.currentData(), save=False)
        s.set("restore_layout", self.restore_layout.isChecked(), save=False)
        s.set("auto_lock_minutes", self.auto_lock.value(), save=False)
        s.set("app_update_repo", self.update_repo.text().strip(), save=False)
        s.set("check_updates_on_start", self.check_start.isChecked(), save=False)
        s.set("include_prereleases", self.prerelease.isChecked(), save=False)
        s.save()
        token = self.token.text().strip()
        if token != (self.vault.get("app:github_token", "") or ""):
            self.vault.set("app:github_token", token or None)
        net.github_token = token or None
        self.accept()
