"""Startpunkt von OmniWrench."""

import sys


def _run_pip(args: list[str]) -> int:
    """Nur EXE-Build: "OmniWrench.exe --pip install …" ersetzt "python -m pip" (sdk.InstallContext.pip_install)."""
    import os

    if sys.stdout is None:  # Fensterprogramm ohne Konsole
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = sys.stdout
    _register_distlib_finder()
    from pip._internal.cli.main import main as pip_main

    return pip_main(args)


def _register_distlib_finder() -> None:
    """distlib (in pip) kennt den Modul-Loader von PyInstaller nicht und bricht unter Windows beim Laden der
    Starter-EXEs ab ("Unable to locate finder for 'pip._vendor.distlib'"). Die Dateien liegen dank
    --collect-data pip normal im Programmordner, also reicht der dateibasierte ResourceFinder."""
    from pip._vendor.distlib import resources

    loader = getattr(resources, "__loader__", None)
    if loader is not None and type(loader) not in resources._finder_registry:
        resources.register_finder(loader, resources.ResourceFinder)


def _run_mcp_stdio() -> int:
    """"OmniWrench --mcp-stdio": MCP über stdin/stdout an den laufenden Server in Gadgetron weiterleiten."""
    import os

    from omniwrench.ai.mcp_server import stdio_bridge

    # Fensterprogramm (EXE): sys.stdin/stdout fehlen, die Pipes des aufrufenden Programms gibt es trotzdem
    stdin = sys.stdin.buffer if sys.stdin is not None else os.fdopen(0, "rb")
    stdout = sys.stdout.buffer if sys.stdout is not None else os.fdopen(1, "wb")
    return stdio_bridge(stdin, stdout)


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["--pip"]:
        sys.exit(_run_pip(sys.argv[2:]))
    if sys.argv[1:2] == ["--mcp-stdio"]:
        sys.exit(_run_mcp_stdio())
    from omniwrench.app import main

    sys.exit(main())
