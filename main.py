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


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["--pip"]:
        sys.exit(_run_pip(sys.argv[2:]))
    from omniwrench.app import main

    sys.exit(main())
