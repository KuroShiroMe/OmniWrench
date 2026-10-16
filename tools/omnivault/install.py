"""Installationsroutine des OmniVault.

pykeepass (für KeePass-Konnektoren) installiert das Hauptprogramm aus tool.json -> requirements.
Das PowerShell-Modul für SecretManagement wird erst beim Anlegen eines solchen Konnektors benötigt.
"""


def check(ctx):
    import importlib
    import sys
    lib = str(ctx.tool_dir / "_lib")  # pip installiert Tool-Pakete in den privaten _lib-Ordner
    if lib not in sys.path:
        sys.path.insert(0, lib)
    importlib.invalidate_caches()
    try:
        import pykeepass  # noqa: F401
    except ImportError:
        return ["pykeepass"]
    return []


def install(ctx):
    ctx.report(ctx.tr("install.ready", "OmniVault installed."))


def uninstall(ctx):
    ctx.report(ctx.tr("install.removed", "Connectors removed. Built-in credentials are kept in OmniWrench."))
