# Gotchas (environment & framework traps)

## Machine / shell
- Windows 11, PowerShell 5.1 is the primary shell tool; Bash (Git Bash) also available.
- PS 5.1: `&&` not allowed; `Set-Content -Encoding utf8` may write BOM → JSON parse fails. Prefer Python or `[IO.File]::WriteAllText`.
- Inline `python -c "…"` with nested quotes breaks in PowerShell → write a script file in the scratchpad.
- `git commit -F -` with here-string didn't work → write message to a file and use `-F file`.
- `gh` installed but PATH not refreshed in tool shell → refresh PATH (see CLAUDE.md). `gh release create` prints a harmless "protocol error: received DATA after END_STREAM"; verify with `gh release view`.
- Corporate TLS inspection: Python 3.13+ strict X.509 rejects proxy root ("Missing Authority Key Identifier") → use truststore (net.py `_SSL`).
- Elevated PowerShell (UAC): don't use Start-Transcript for logs (file locked/owned by elevated proc) → collect output, WriteAllText, icacls grant user.
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

## Async credentials (2026-10-16)
- Dialogs only in GUI thread: provider auth prompt from a worker goes through workers.call_in_gui (blocking).
  Never hold a lock around get_secret() - GUI-thread resolve + worker waiting on GUI would deadlock.
- build_store.py on Linux (LF checkout) rebuilds UNCHANGED tool zips with different sha256 -> restore those zips
  + their index entries, commit only bumped tools.
