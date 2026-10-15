"""Installation der deklarativen Voraussetzungen aus tool.json -> "requirements".

Python-Pakete und winget/PSGallery werden ohne Adminrechte installiert,
Windows-Funktionen (z. B. RSAT) und Features gesammelt in EINER
Administrator-Sitzung (eine UAC-Abfrage).
"""

from __future__ import annotations

from typing import Callable

from .i18n import tr
from .manifest import Requirements
from .powershell import ps_quote, run_ps, run_ps_elevated

Progress = Callable[[str], None]


def _elevated_script(req: Requirements) -> str:
    lines: list[str] = []
    for cap in req.windows_capabilities:
        q = ps_quote(cap)
        lines.append(
            f"$c = Get-WindowsCapability -Online -Name {q}\n"
            f"if ($c.State -ne 'Installed') {{ Write-Output ('Installing capability ' + {q}); "
            f"Add-WindowsCapability -Online -Name {q} | Out-Null }} "
            f"else {{ Write-Output ('Already installed: ' + {q}) }}"
        )
    for feat in req.windows_features:
        q = ps_quote(feat)
        # Windows Server: Install-WindowsFeature, Client: optionale Features
        lines.append(
            "if (Get-Command Install-WindowsFeature -ErrorAction SilentlyContinue) {\n"
            f"  $f = Get-WindowsFeature -Name {q}\n"
            f"  if (-not $f.Installed) {{ Write-Output ('Installing feature ' + {q}); "
            f"Install-WindowsFeature -Name {q} -IncludeManagementTools | Out-Null }}\n"
            "} else {\n"
            f"  $f = Get-WindowsOptionalFeature -Online -FeatureName {q}\n"
            f"  if ($f.State -ne 'Enabled') {{ Write-Output ('Enabling feature ' + {q}); "
            f"Enable-WindowsOptionalFeature -Online -FeatureName {q} -All -NoRestart | Out-Null }}\n"
            "}"
        )
    return "\n".join(lines)


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
        progress(tr("prog.windows_features"))
        res = run_ps_elevated(_elevated_script(req))
        for line in res.stdout.splitlines():
            if line.strip() and not line.startswith("*"):
                progress("  " + line.strip())
        if not res.ok:
            raise RuntimeError(tr("err.windows_features") + "\n" + (res.stderr or res.stdout)[-2000:])

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
