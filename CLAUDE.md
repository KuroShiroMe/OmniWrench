# CLAUDE.md – OmniWrench (DarkMatter)

Modular admin toolbox for Windows clients and Linux (since 0.7.0). Python 3.14 + PySide6 + QtAds. Repo: github.com/KuroShiroMe/OmniWrench (public).
User = "KuroShiroMe" (GitHub, formerly Steffi-Tech until 2026-10-22) (sysadmin, writes German, wants German replies). Vendor brand: DarkMatter. Product: OmniWrench.

## Read this first (AI memory)
Detailed project memory lives in `docs/ai/`. Read selectively — do NOT load everything:

| Need | File |
|---|---|
| What the user wants / decided / prefers (binding!) | `docs/ai/decisions.md` |
| How the code is built, where things are | `docs/ai/architecture.md` |
| What was asked & done, in order | `docs/ai/history.md` |
| Open tasks, next steps, ideas | `docs/ai/backlog.md` |
| Open Windows tests for Stef (German) | `docs/TESTLISTE.md` |
| Environment traps & fixes (PowerShell, TLS, Qt …) | `docs/ai/gotchas.md` |
| claude.ai project setup + per-component chat starters | `docs/ai/claude-project/` |

Rules for yourself:
1. Before a feature: read `decisions.md` + the relevant part of `architecture.md`.
2. Before running shell commands / publishing: read `gotchas.md`.
3. After finishing work: append to `history.md`, update `backlog.md`, add new decisions/gotchas. Keep the files terse (bullet style, English is fine; user-facing text stays German).

## Quick commands
```powershell
.\.venv\Scripts\python main.py                      # run app
.\.venv\Scripts\python scripts\check_locales.py     # all languages complete? (23 app locales)
.\.venv\Scripts\python scripts\build_store.py       # rebuild store/ after tool changes (bump tool version!)
.\.venv\Scripts\python scripts\check_store.py       # store/ matches tools/? (CI checks this)
.\.venv\Scripts\python scripts\smoke_test.py        # start test as in CI (temp home, all languages/tools)
.\.venv\Scripts\python scripts\build_release.py     # dist\OmniWrench-X.Y.Z.zip from HEAD
.\.venv\Scripts\python scripts\build_exe.py --zip   # dist\OmniWrench\OmniWrench.exe + -win64.zip (docs/EXE_BUILD.md)
.\.venv\Scripts\python scripts\build_exe.py --sign --zip  # same, signed if SIGN_CERT_SHA1/SIGN_PFX_* set (docs/EXE_SIGNIEREN.md)
.\.venv\Scripts\python scripts\build_installer.py   # after build_exe: Windows -win64-setup.exe (Inno Setup 6), Linux .deb
git tag vX.Y.Z; git push origin vX.Y.Z               # CI (Build) creates the GitHub release: setup, zip, deb, tar.gz, source
```
`gh` needs PATH refresh in PowerShell: `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`

## Conventions
- Every user-visible string via `tr("key")` (app) or `self.context.tr("key")` (tools); add keys to ALL app locale files (`omniwrench/locales/*.json`, 23 incl. dialects), then run check_locales. Missing keys only fall back (dialect → base → en), they do not fail CI.
- Tool packages: `tools/<name>/` with tool.json, config.json, install.py, tool.py, locales/. Bump version → rebuild store → commit store/.
- Commit messages German, end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Bump `omniwrench/__init__.py` version for app releases.
- Landing page kuroshiro.me (`site/`, deployed by `.github/workflows/pages.yml`): at the end of EVERY task check whether
  something belongs on it and add it (Stef 2026-10-22). Tool list is generated from store/index.json by
  `scripts/build_site.py` (run it after store changes); new main features, platforms, screenshots, install info → edit `site/index.html`.
- Verify UI visually: render with real fonts + `WA_DontShowOnScreen` and `grab()` (see gotchas).
