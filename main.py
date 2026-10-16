"""Startpunkt von OmniWrench."""

import sys


def _run_pip(args: list[str]) -> int:
    """Nur EXE-Build: "OmniWrench.exe --pip install …" ersetzt "python -m pip" (sdk.InstallContext.pip_install)."""
    import os

    if sys.stdout is None:  # Fensterprogramm ohne Konsole
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = sys.stdout
    from pip._internal.cli.main import main as pip_main

    return pip_main(args)


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and sys.argv[1:2] == ["--pip"]:
        sys.exit(_run_pip(sys.argv[2:]))
    from omniwrench.app import main

    sys.exit(main())
