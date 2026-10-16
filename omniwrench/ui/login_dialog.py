"""Ersteinrichtung und Anmeldung (Masterpasswort und/oder Benutzerzertifikat)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget,
)

from omniwrench import APP_NAME, VENDOR, __version__
from omniwrench.core import certificates
from omniwrench.core.i18n import tr
from omniwrench.core.vault import Vault, VaultError

from . import theme
from .scaling import fit_min_width
from .widgets import label, make_button
from .workers import run_async

MIN_PASSWORD_LENGTH = 8


class CertificateCombo(QWidget):
    """Auswahl eines Benutzerzertifikats aus CurrentUser\\My (lädt im Hintergrund)."""

    def __init__(self, only_encryption: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.only_encryption = only_encryption
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(320)
        self.combo.addItem(tr("cert.loading"), "")
        lay.addWidget(self.combo, 1)
        self.reload_btn = make_button("↻", on_click=self.reload)
        self.reload_btn.setToolTip(tr("cert.reload"))
        self.reload_btn.setFixedWidth(36)
        lay.addWidget(self.reload_btn)
        self._pending_select = ""
        self.reload()

    def reload(self) -> None:
        self.combo.setEnabled(False)
        run_async(lambda: certificates.list_certificates(self.only_encryption), self._loaded, self._failed)

    def _loaded(self, certs) -> None:
        self.combo.clear()
        self.combo.setEnabled(True)
        if not certs:
            self.combo.addItem(tr("cert.none_found"), "")
            return
        self.combo.addItem(tr("cert.choose"), "")
        for c in certs:
            self.combo.addItem(c.display, c.thumbprint)
            self.combo.setItemData(self.combo.count() - 1, tr("cert.tooltip", subject=c.subject, issuer=c.issuer),
                                   Qt.ItemDataRole.ToolTipRole)
        if self._pending_select:
            self.set_thumbprint(self._pending_select)

    def _failed(self, error: str) -> None:
        self.combo.clear()
        self.combo.setEnabled(True)
        self.combo.addItem(tr("common.error_short", error=error[:80]), "")

    def thumbprint(self) -> str:
        return self.combo.currentData() or ""

    def set_thumbprint(self, thumbprint: str) -> None:
        self._pending_select = thumbprint or ""
        idx = self.combo.findData(self._pending_select)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)


class LoginDialog(QDialog):
    def __init__(self, vault: Vault, parent: QWidget | None = None, locked: bool = False):
        super().__init__(parent)
        self.vault = vault
        self.setup_mode = not vault.exists
        self.setWindowTitle(f"{APP_NAME} - " + tr("login.title_setup" if self.setup_mode else "login.title_unlock"))
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        fit_min_width(self, 500)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = QFrame()
        card.setObjectName("LoginCard")
        outer.addWidget(card)
        self.lay = QVBoxLayout(card)
        self.lay.setContentsMargins(28, 24, 28, 24)
        self.lay.setSpacing(10)

        self.lay.addWidget(label(APP_NAME, "PageTitle"))
        self.lay.addWidget(label(f"by {VENDOR}", "Muted"))
        if self.setup_mode:
            self.lay.addWidget(label(tr("login.setup_intro"), "PageSubtitle", wrap=True))
            self._build_setup()
        else:
            self.lay.addWidget(label(tr("login.locked" if locked else "login.please_login"), "PageSubtitle"))
            self._build_unlock()

        self.error = label("", "ErrorLabel", wrap=True)
        self.error.hide()
        self.lay.addWidget(self.error)
        self.lay.addWidget(label(tr("common.version", version=__version__), "Muted"),
                           alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------ Einrichtung
    def _build_setup(self) -> None:
        self.use_pw = QCheckBox(tr("login.use_password"))
        self.use_pw.setChecked(True)
        self.lay.addWidget(self.use_pw)
        self.pw1 = QLineEdit(placeholderText=tr("login.password_min", min=MIN_PASSWORD_LENGTH))
        self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2 = QLineEdit(placeholderText=tr("login.password_repeat"))
        self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.lay.addWidget(self.pw1)
        self.lay.addWidget(self.pw2)
        self.use_pw.toggled.connect(self.pw1.setEnabled)
        self.use_pw.toggled.connect(self.pw2.setEnabled)

        self.use_cert = QCheckBox(tr("login.use_cert"))
        self.lay.addWidget(self.use_cert)
        self.cert = CertificateCombo()
        self.cert.setEnabled(False)
        self.use_cert.toggled.connect(self.cert.setEnabled)
        self.lay.addWidget(self.cert)
        self.lay.addWidget(label(tr("login.both_hint"), "Muted", wrap=True))

        self.submit = make_button(tr("login.setup_button"), primary=True, on_click=self._do_setup)
        self.submit.setDefault(True)
        self.lay.addWidget(self.submit)

    def _do_setup(self) -> None:
        password = self.pw1.text() if self.use_pw.isChecked() else None
        thumb = self.cert.thumbprint() if self.use_cert.isChecked() else None
        if self.use_pw.isChecked():
            if len(password) < MIN_PASSWORD_LENGTH:
                return self._show_error(tr("login.err_short", min=MIN_PASSWORD_LENGTH))
            if password != self.pw2.text():
                return self._show_error(tr("login.err_mismatch"))
        if self.use_cert.isChecked() and not thumb:
            return self._show_error(tr("login.err_choose_cert"))
        if not password and not thumb:
            return self._show_error(tr("err.vault_need_method"))
        self._busy(True, tr("login.creating"))
        run_async(lambda: self.vault.create(password=password, cert_thumbprint=thumb),
                  lambda _: self.accept(), self._failed)

    # --------------------------------------------------------------- Anmelden
    def _build_unlock(self) -> None:
        self.pw1 = None
        if self.vault.has_unlocker("password"):
            self.pw1 = QLineEdit(placeholderText=tr("login.password"))
            self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
            self.pw1.returnPressed.connect(self._unlock_password)
            self.lay.addWidget(self.pw1)
            self.submit = make_button(tr("login.login_button"), primary=True, on_click=self._unlock_password)
            self.submit.setDefault(True)
            self.lay.addWidget(self.submit)
        self.cert_buttons = []
        certs = [u for u in self.vault.unlockers() if u["type"] == "certificate"]
        if certs and self.pw1:
            self.lay.addWidget(label(tr("login.or"), "Muted"), alignment=Qt.AlignmentFlag.AlignCenter)
        for u in certs:
            cn = u["subject"].split(",")[0].replace("CN=", "")
            btn = make_button("🔐  " + tr("login.with_cert", name=cn), primary=not self.pw1,
                              on_click=lambda _=False, t=u["thumbprint"]: self._unlock_cert(t))
            btn.setToolTip(tr("login.cert_tooltip", subject=u["subject"], thumb=u["thumbprint"],
                              date=u.get("not_after", "?")))
            self.cert_buttons.append(btn)
            self.lay.addWidget(btn)
        if self.pw1:
            self.pw1.setFocus()

    def _unlock_password(self) -> None:
        if not self.pw1.text():
            return
        pw = self.pw1.text()
        self._busy(True, tr("login.checking"))
        run_async(lambda: self.vault.unlock_with_password(pw), lambda _: self.accept(), self._failed)

    def _unlock_cert(self, thumbprint: str) -> None:
        self._busy(True, tr("login.cert_busy"))
        run_async(lambda: self.vault.unlock_with_certificate(thumbprint), lambda _: self.accept(), self._failed)

    # ---------------------------------------------------------------- Helfer
    def _busy(self, busy: bool, text: str = "") -> None:
        widgets = self.findChildren(QLineEdit) + self.findChildren(QCheckBox) + getattr(self, "cert_buttons", [])
        for w in widgets:
            w.setEnabled(not busy)
        if hasattr(self, "submit"):
            self.submit.setEnabled(not busy)
        if busy:
            self.error.setStyleSheet(f"color: {theme.current['muted']}")
            self.error.setText(text)
            self.error.show()

    def _failed(self, error: str) -> None:
        self._busy(False)
        if self.setup_mode:
            self.pw1.setEnabled(self.use_pw.isChecked())
            self.pw2.setEnabled(self.use_pw.isChecked())
        self._show_error(error)
        if self.pw1 is not None:
            self.pw1.selectAll()
            self.pw1.setFocus()

    def _show_error(self, text: str) -> None:
        self.error.setStyleSheet("")
        self.error.setText(text)
        self.error.show()


__all__ = ["LoginDialog", "CertificateCombo", "VaultError"]
