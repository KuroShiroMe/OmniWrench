"""Schutz kleiner Datenmengen an das Windows-Benutzerkonto (DPAPI, CurrentUser).

Wird für die Wiederherstellungsdaten des Tresors verwendet: Diese enthalten keine
Passwörter, sollen aber trotzdem nicht im Klartext auf der Platte liegen. Entschlüsseln
kann sie nur dasselbe Windows-Konto - ohne Masterpasswort.

Außerhalb von Windows (Entwicklung, CI) gibt es kein DPAPI; dort werden die Daten nur
Base64-kodiert ("plain"). OmniWrench selbst läuft nur unter Windows.
"""

from __future__ import annotations

import base64
import sys

ENTROPY = b"DarkMatter.OmniWrench.vault-recovery"


def _protect_windows(data: bytes, unprotect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw: bytes) -> tuple[Blob, ctypes.Array]:
        buf = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    src, _src_buf = blob(data)
    ent, _ent_buf = blob(ENTROPY)
    out = Blob()
    ui_forbidden = 0x01
    func = crypt32.CryptUnprotectData if unprotect else crypt32.CryptProtectData
    if unprotect:
        ok = func(ctypes.byref(src), None, ctypes.byref(ent), None, None, ui_forbidden, ctypes.byref(out))
    else:
        ok = func(ctypes.byref(src), "OmniWrench", ctypes.byref(ent), None, None, ui_forbidden, ctypes.byref(out))
    if not ok:
        raise OSError(ctypes.GetLastError(), "DPAPI")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> dict:
    """Verpackt Daten; Ergebnis ist JSON-tauglich ({"scheme", "data"})."""
    if sys.platform == "win32":
        return {"scheme": "dpapi", "data": base64.b64encode(_protect_windows(data, False)).decode("ascii")}
    return {"scheme": "plain", "data": base64.b64encode(data).decode("ascii")}


def unprotect(box: dict) -> bytes:
    raw = base64.b64decode(box["data"])
    if box.get("scheme") == "dpapi":
        return _protect_windows(raw, True)
    if box.get("scheme") == "plain":
        return raw
    raise ValueError(f"unknown scheme {box.get('scheme')!r}")
