"""Installation der deklarativen Voraussetzungen aus tool.json -> "requirements".

Python-Pakete und winget/PSGallery werden ohne Adminrechte installiert,
Windows-Funktionen (z. B. RSAT) und Features gesammelt in EINER
Administrator-Sitzung (eine UAC-Abfrage).
"""

from __future__ import annotations

from typing import Callable

from . import elevation
from .i18n import tr
from .manifest import Requirements
from .powershell import MARKER_PREFIX, ps_quote, run_ps, run_ps_elevated

Progress = Callable[[str], None]


# Fortschrittsmeldungen der Admin-Sitzung: "##OW <art>|<name>" -> übersetzter Text
_MARKERS: dict[str, Callable[[str], str]] = {
    "cap_install": lambda name: tr("prog.elev_cap_install", name=name),
    "cap_present": lambda name: tr("prog.elev_cap_present", name=name),
    "feat_install": lambda name: tr("prog.elev_feat_install", name=name),
    "feat_present": lambda name: tr("prog.elev_feat_present", name=name),
    "done": lambda name: tr("prog.elev_done", name=name),
}

# Typische Fehler, wenn Windows-Funktionen nicht aus Windows Update geladen werden dürfen (WSUS)
_SOURCE_ERRORS = ("0x800f0954", "0x800f081f", "0x8024402c", "0x80240438")


def _marker(kind: str, q: str) -> str:
    return f"Write-Output ('{MARKER_PREFIX}{kind}|' + {q})"


def _restart_check() -> str:
    return f"if ([string]$r.RestartNeeded -in 'True','Yes') {{ Write-Output '{MARKER_PREFIX}restart|' }}"


def _elevated_script(req: Requirements) -> str:
    lines: list[str] = []
    for cap in req.windows_capabilities:
        q = ps_quote(cap)
        lines.append(
            f"$c = Get-WindowsCapability -Online -Name {q}\n"
            f"if ($c.State -ne 'Installed') {{\n"
            f"  {_marker('cap_install', q)}\n"
            f"  $r = Add-WindowsCapability -Online -Name {q}\n"
            f"  {_restart_check()}\n"
            f"  {_marker('done', q)}\n"
            f"}} else {{ {_marker('cap_present', q)} }}"
        )
    for feat in req.windows_features:
        q = ps_quote(feat)
        # Windows Server: Install-WindowsFeature, Client: optionale Features
        lines.append(
            "if (Get-Command Install-WindowsFeature -ErrorAction SilentlyContinue) {\n"
            f"  $f = Get-WindowsFeature -Name {q}\n"
            f"  if (-not $f.Installed) {{\n"
            f"    {_marker('feat_install', q)}\n"
            f"    $r = Install-WindowsFeature -Name {q} -IncludeManagementTools\n"
            f"    {_restart_check()}\n"
            f"    {_marker('done', q)}\n"
            f"  }} else {{ {_marker('feat_present', q)} }}\n"
            "} else {\n"
            f"  $f = Get-WindowsOptionalFeature -Online -FeatureName {q}\n"
            f"  if ($f.State -ne 'Enabled') {{\n"
            f"    {_marker('feat_install', q)}\n"
            f"    $r = Enable-WindowsOptionalFeature -Online -FeatureName {q} -All -NoRestart\n"
            f"    {_restart_check()}\n"
            f"    {_marker('done', q)}\n"
            f"  }} else {{ {_marker('feat_present', q)} }}\n"
            "}"
        )
    return "\n".join(lines)


def _install_elevated(req: Requirements, progress: Progress) -> None:
    """Windows-Funktionen und Features in einer Admin-Sitzung (eine UAC-Abfrage)."""
    progress(tr("prog.windows_features"))
    progress(tr("prog.uac_prompt") if elevation.needs_uac() else tr("prog.already_admin"))
    restart = False

    def on_output(line: str) -> None:
        nonlocal restart
        if not line.startswith(MARKER_PREFIX):
            progress("  " + line)
            return
        kind, _, name = line[len(MARKER_PREFIX):].partition("|")
        if kind == "restart":
            restart = True
        elif kind in _MARKERS:
            progress("  " + _MARKERS[kind](name))

    res = run_ps_elevated(_elevated_script(req), on_output=on_output)
    if res.returncode == elevation.ERROR_CANCELLED:
        raise RuntimeError(tr("err.elevated_cancelled"))
    if not res.ok:
        detail = (res.stderr or res.stdout)[-2000:]
        message = tr("err.windows_features") + "\n" + detail
        if any(code in detail.lower() for code in _SOURCE_ERRORS):
            message += "\n\n" + tr("err.feature_source_hint")
        raise RuntimeError(message)
    if restart:
        progress(tr("prog.restart_required"))


def install_requirements(req: Requirements, pip_install: Callable[..., None], progress: Progress,
                         system: bool = True) -> None:
    """Installiert die Voraussetzungen. system=False überspringt Windows-Funktionen,
    PowerShell-Module und winget (wenn check() des Tools sie bereits als erfüllt meldet)."""
    if req.is_empty():
        return

    if req.python:
        pip_install(*req.python)

    if not system:
        return

    if req.windows_capabilities or req.windows_features:
        _install_elevated(req, progress)

    for module in req.powershell_modules:
        q = ps_quote(module)
        progress(tr("prog.check_ps_module", name=module))
        res = run_ps(
            f"if (-not (Get-Module -ListAvailable -Name {q})) {{"
            f" Install-Module -Name {q} -Scope CurrentUser -Force -AllowClobber; 'installed' }} else {{ 'present' }}",
            timeout=900,
        )
        if not res.ok:
            raise RuntimeError(tr("err.ps_module", name=module) + "\n" + res.stderr)
        progress(f"  {module}: {res.stdout}")

    for pkg in req.winget:
        q = ps_quote(pkg)
        progress(tr("prog.check_winget", name=pkg))
        res = run_ps(
            f"winget list --id {q} -e --accept-source-agreements | Out-Null\n"
            f"if ($LASTEXITCODE -ne 0) {{ winget install --id {q} -e --silent "
            "--accept-package-agreements --accept-source-agreements; exit $LASTEXITCODE } else { 'present' }",
            timeout=1800,
        )
        if not res.ok:
            raise RuntimeError(tr("err.winget", name=pkg) + "\n" + res.stdout[-1500:])
        progress(f"  {pkg}: OK")
