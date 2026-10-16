# Gotchas (environment & framework traps)

## Machine / shell
- Windows 11, PowerShell 5.1 is the primary shell tool; Bash (Git Bash) also available.
- PS 5.1: `&&` not allowed; `Set-Content -Encoding utf8` may write BOM → JSON parse fails. Prefer Python or `[IO.File]::WriteAllText`.
- Inline `python -c "…"` with nested quotes breaks in PowerShell → write a script file in the scratchpad.
- `git commit -F -` with here-string didn't work → write message to a file and use `-F file`.
- `gh` installed but PATH not refreshed in tool shell → refresh PATH (see CLAUDE.md). `gh release create` prints a harmless "protocol error: received DATA after END_STREAM"; verify with `gh release view`.
- Corporate TLS inspection: Python 3.13+ strict X.509 rejects proxy root ("Missing Authority Key Identifier") → use truststore (net.py `_SSL`).
- Elevated PowerShell (UAC): don't use Start-Transcript for logs (file locked/owned by elevated proc). Current design:
  non-elevated parent creates the log file first (stays readable even if UAC runs under another admin account),
  elevated wrapper appends lines; parent tails it. A non-elevated process can't kill the elevated one (timeout = give up waiting).
- `Start-Process -Verb RunAs` from a hidden PowerShell: UAC prompt may only flash in the taskbar, cancel only as
  localized error text → use ShellExecuteExW with the main window hwnd (core/elevation.py).
- `-File` is subject to GPO execution policy (AllSigned) despite `-ExecutionPolicy Bypass`; `-EncodedCommand` is not
  → elevated wrapper uses -EncodedCommand (falls back to -File above ~30k chars).
- RSAT via Add-WindowsCapability fails on WSUS clients with 0x800f0954 unless GPO allows Windows Update for optional
  components → shown as hint (no automatic policy/registry change).
- Linux dev: pwsh 7 tarball from GitHub releases works for testing PowerShell wrappers (scratchpad).
- Intune device cert in CurrentUser\My is signing-only (CNG KeyUsage=Signing) → can't decrypt.

## Qt / PySide6 / QtAds
- QtAds sets its own stylesheet on CDockManager → apply our ads stylesheet on the manager (`dm.setStyleSheet(base + theme.ads_stylesheet())`).
- Padding on `ads--CDockWidgetTab QLabel` clips tab text → padding on the tab only.
- `#ToolCard QLabel {background: transparent}` outranks `#Badge` → use `QLabel#Badge`.
- `deleteLater()` isn't processed by manual processEvents loops in tests → hide widgets before deleteLater (clear_layout does).
- Offscreen platform has no fonts (boxes). For visual checks render with default platform + `setAttribute(WA_DontShowOnScreen)` + `grab().save()` (script pattern: scratchpad render.py; use `OMNIWRENCH_HOME` temp dir).
- QMenu.addAction(icon, text, shortcut, slot) overload unreliable → addAction(text, shortcut, slot) then setIcon.
- make_button(on_click=method) passes `checked` bool → methods with optional params must type-check (show_home uses isinstance tuple).
- ToolTile/FitLabel: FitLabel paints itself (custom widget), not QLabel.
- QListView IconMode shows only ONE text line (wordWrap ignored) -> IconForge uses a custom QStyledItemDelegate.
- ToolSettingsStore.update compares get(key) == value: mutating the SAME dict object and setting again is a no-op
  (always pass fresh dicts).
- Tool `check()` runs before `_lib` is on sys.path -> add ctx.tool_dir/"_lib" to sys.path inside check (PMM install.py).
- Bash heredocs containing many quotes break the Bash tool -> write a script file to the scratchpad and run it.

## Python
- Python 3.14 in venv `.venv`; packages: PySide6 6.11, PySide6-QtAds 5.1, cryptography 50 (Argon2id available), truststore.
- Netwrix Password Secure: no public REST API; only C#/JS SDK (PsrApi) from customer portal.
- `i18n.load_locales` is lru_cached per directory → `i18n.clear_cache()` after installs (tool_manager does).

## Round 8
- Adding an attribute to the SVG root that already exists (e.g. fill) creates invalid XML -> renders empty.
- Lineicons: root fill="none" + hard-coded path color -> recolor by replacing the single used color.
- Narrow QPushButton with "…" text shows "." -> use an icon (folder-open).
- Netwrix PsrApi: async methods return Task -> in PowerShell `.GetAwaiter().GetResult()`.

## Store build
- `build_store.py` rebuilds ALL packages; zips of unchanged tools get new hashes on another OS/checkout
  (line endings/mtimes). Keep only the bumped tool's zip + index entry; restore the others from git.

## Async credentials (2026-10-16)
- Dialogs only in GUI thread: provider auth prompt from a worker goes through workers.call_in_gui (blocking).
  Never hold a lock around get_secret() - GUI-thread resolve + worker waiting on GUI would deadlock.
- build_store.py on Linux (LF checkout) rebuilds UNCHANGED tool zips with different sha256 -> restore those zips
  + their index entries, commit only bumped tools.
## EXE build (PyInstaller)
- Frozen app has no `python -m pip` -> `OmniWrench.exe --pip …` (main.py). Windowed exe: sys.stdout is None -> devnull,
  errors via pip `--log` file. Packages without wheels can't build (no compiler/`-c` support) -> `--prefer-binary`.
- Tools are imported at runtime from %LOCALAPPDATA% -> PyInstaller can't see their imports; build_exe.py bundles whole
  stdlib (find_spec filter) + extra Qt modules. A new tool needing another PySide6 module -> add to QT_MODULES.
- Old clients (<= 0.5.0) take the FIRST zip asset starting with "omniwrench" -> upload source zip before -win64.zip.
- `.gitignore` ignores `*.spec`: build_exe.py passes all options on the command line (spec generated into build/exe).
- Linux test build needs libegl1/libgl1/libxkbcommon0/libfontconfig1 (Qt import) - only for smoke tests.
## Round 9
- QT_SCALE_FACTOR is read only when QApplication is created -> scaling needs a new process; child inherits env,
  so scaling.py marks its own value (OMNIWRENCH_SCALE_FACTOR) and drops it on the next start.
- Wrapped QLabel's minimum width = longest unbreakable word -> long ids (Rsat...~~~~0.0.1.0) widen side panels;
  breakable() inserts U+200B after . ~ / \ _ : @ (only for display text, not for copyable ids).
- A QScrollArea with horizontal scrollbar off clips content whose minimum width is too large (no shrink) -
  check minimumSizeHint of rows of buttons.
- QtAds wraps tool widgets in a scroll area: tools wider than their minimum get a horizontal scrollbar instead of shrinking.
- Linux renders: offscreen platform works with fontconfig fonts; screen size via
  QT_QPA_PLATFORM="offscreen:configfile=screen.json" ({"screens":[{"width":7680,"height":4320,"dpr":1,...}]}).
- build_store.py on Linux changes every zip (LF vs CRLF checkout) -> only commit zips of bumped tools.
