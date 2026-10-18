"""Hilfsfunktion: Pixelverhältnis, falls das Hauptprogramm es bereitstellt (sonst 1.0)."""

from __future__ import annotations


def ratio() -> float:
    try:
        from omniwrench.sdk import device_pixel_ratio
        return device_pixel_ratio()
    except Exception:  # noqa: BLE001
        return 1.0
