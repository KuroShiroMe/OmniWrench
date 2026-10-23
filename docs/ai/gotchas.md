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
- `ToolBase` ist KEIN QObject -> ein `Signal(...)` direkt als Klassenattribut einer ToolBase-Unterklasse wirft beim `connect` `'Signal' object has no attribute 'connect'`. Für Hintergrund->GUI entweder `run_async` oder eine eigene `class _Bridge(QObject)` mit den Signals (NetProbe). smoke_test fängt das ab.

- FlowLayout (widgets.py) wraps as soon as a row reaches rect.right() (= width-1) and its sizeHint is only the widest
  item -> in an HBox a button row wraps vertically. DHCP tool ButtonBar overrides sizeHint (one row + 1 px) and calls
  updateGeometry on LayoutRequest (button widths change after styling).
- `spinbox.valueChanged.connect(self.changed.emit)` with `changed = Signal()` -> "changed() only accepts 0 argument(s)"
  at runtime; wrap in a lambda. Same for clicked(bool) -> Signal().
- QTableWidget: styling items (setBackground/setToolTip) fires itemChanged -> keep blockSignals until styling is done,
  otherwise itemChanged -> refill -> endless recursion.
- smoke_test patches only the static QMessageBox helpers; `QMessageBox(...).exec()` instances block a headless test
  (patch QMessageBox.exec in render/flow scripts).
- PowerShell: unary comma only for function RETURN values (`return , $arr`). Inside a hashtable literal
  `@{ items = , $arr }` nests the array -> JSON `[[...]]` (DHCP tool 1.0.0 bug, old PowerShell host: "'list' object has no attribute
  'get'"). Test host.ps1 output shapes with real pwsh (Linux tarball works, stub the DhcpServer cmdlets), not only
  with a Python fake backend.
- dhcpsapi via ctypes: IPs are host-order DWORDs; client arrays are arrays of POINTERS (DHCP_CLIENT_INFO_ARRAY_V5);
  option data type lives only in the element OptionType (definition type = DefaultValue element type); the DNS
  credential function is DhcpServerQueryDnsRegCredentials (not ...Get...). Verify new structs against windows-sys
  metadata (raw.githubusercontent.com/microsoft/windows-rs/0.52.0/crates/libs/sys/src/Windows/Win32/NetworkManagement/
  Dhcp/mod.rs) - mingw's dhcpsapi.h lacks most V5/failover structs.
## Python
- `context.tr(key, default=None, **kw)`: never use `key=` or `default=` as placeholder names (TypeError "multiple values").
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
- QSplitter shrinks the stretch child first: give a QListView grid a minimum width of one cell (+ scrollbar + frame),
  otherwise it collapses below one column while the side panel keeps its width.
## EXE signing
- `secrets.*` can't be used in step `if:` -> build.yml decides via repo variable SIGN_METHOD (vars.* works).
- Since 06/2023 OV/EV private keys live on HSM/token/cloud only -> no PFX secret for bought certs; PFX path is for
  test/company-PKI certs. Certum SimplySign needs a phone code per session -> local signing, not CI.
- Cloud sandbox: plain-HTTP timestamp servers unreachable and osslsigncode segfaults on that ->
  SIGN_TIMESTAMP_URL=none for local tests only.

## Release assets
- GitHub lists release assets sorted by NAME: `OmniWrench-X.Y.Z-win64.zip` comes before `OmniWrench-X.Y.Z.zip`
  ("-" < "."), upload order/re-upload doesn't change it. App <=0.5.x takes the first omniwrench*.zip -> would get
  the EXE package. 0.6.0+ uses _pick_asset (by suffix), so only the 0.5.x -> 0.6.0 jump is affected.
  User decision: no rename; 0.5.x installs are updated manually once.

## Qt dialogs/layouts (DHCP tool 1.1.0)
- QMessageBox.setCheckBox: the QCheckBox must have the box as parent, else Python frees it while Qt still owns it
  -> segfault after the dialog. Then box.deleteLater().
- App FlowLayout counts hidden widgets in its width -> a bar with hidden buttons wraps. ButtonBar.set_visible removes
  all widgets and re-adds only visible ones.
- QTableWidget.resizeRowsToContents on a hidden/narrow page wraps text into huge rows -> redo it on
  header sectionResized (debounced, FindingsView).
- build_store.py rebuilds ALL tool ZIPs and they are not byte-identical (timestamps) -> after a merge, restore the ZIPs
  and index entries of tools whose version did not change, otherwise check_store/CI report sha256 mismatches or the
  diff churns. Two branches bumping the same tool to the same version -> bump once more after merging.
- Cloud sessions can push to other `claude/*` branches but cannot delete remote branches (git push --delete is denied,
  GitHub MCP has no delete-branch tool) -> Stef deletes them or enables auto-delete of head branches.

## Installers / Linux (2026-10-22)
- Inno Setup: .iss must be UTF-8 **with BOM** (umlauts in [CustomMessages]); unprefixed custom messages apply to all
  languages, `de.` overrides. Optional languages via `#if FileExists(CompilerPath + "Languages\X.isl")`.
- Never change the Inno `AppId` (upgrades/uninstall entry depend on it) or the release file names (updater
  asset_suffix and 0.6.0 clients pick by name).
- Linux PyInstaller binary needs glibc >= build system -> build on ubuntu-22.04 (PySide6 wheels need 2.34).
- `pkill -f <path>` in the Bash tool also kills the tool's own shell when the path appears in the command text.
- Testing a "wait for PID" helper with a child process as stand-in: reap it (zombie keeps `kill -0` true).
- Linux tar.gz instead of zip for the portable build (zipfile drops the executable bit).
- `set -e` in bash ignores `! cmd` -> use `if cmd; then exit 1; fi` in workflow checks.
- README screenshots on Linux: install Windows-only tools by patching `ToolManager._load_installer` (stub module) and
  `_install_prerequisites` (system=False) plus `system.supports_platform`; grab() with offscreen + screen.json.
- Vendor name is part of data paths, setup dir and mutex: never change VENDOR without LEGACY_VENDORS + setup mutex list;
  the DPAPI entropy string must never change.
## DHCP API
- Never remove the IP range of a failover scope (DhcpRemoveSubnetElementV5 -> 20132 ERROR_DHCP_FO_RANGE_PART_OF_REL).
  DhcpAddSubnetElementV5 / `netsh scope x add iprange` modify the existing range, but only if the new range contains
  or lies inside the old one (else 20023) -> shift via the union. Codes 0x4E90-0x4EAF are not all failover errors
  (0x4E90 = policy range conflict).
- DHCP tool transactions: record an undo step only after the write succeeded, otherwise a failed write produces a
  failing inverse ("partial rollback" false alarm). Inside `ctl.atomic` flows, do not catch UserError per item to
  continue - raise, so the whole action is undone. Lambdas in except blocks must bind the exception (`exc=e`).
- DHCP tool background polling: use `Job(..., quiet=True)`; a normal Job disables the main area for every step
  (focus loss while typing). Never poll while a modal dialog is open or the runner is busy.
