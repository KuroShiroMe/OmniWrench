# History (chronological, terse)

## 2026-10-15 — session 1 (one long chat)
1. Initial concept: admin toolbox with app-store, categories (network, MS server), auto prerequisites (RSAT), update check for app+tools via GitHub, tabs (Home always open, Store), tools open in dockable/floatable tabs, sidebar, per-tool settings (right-click), master password or user cert, encrypted secrets.
   - Asked user: tech (→ Python/PySide6), store (→ GitHub repo + index.json), auth (→ both).
   - Built base (v0.1.0): core, UI, vault, store, sample tools Subnet calculator + AD user lookup, docs.
   - Found: only cert on machine is signing-only Intune cert → filtered; CLIXML stderr cleanup.
2. i18n: language files folder, app setting + per-tool setting with auto/English fallback; de/en/fr/es + Badisch, Bayrisch, Scots, Posh English. Git repo initialized. (v0.2.0)
3. Rebrand to OmniWrench / DarkMatter; package rename; gh login by user; repo created public; releases v0.2.0, v0.2.1 (truststore TLS fix — corporate proxy).
4. User feedback: tab text clipped (fixed: no padding on QtAds tab label); Home simplified to icon+name tiles with right details panel; AD tool install failed with PermissionError on elevated run.log (fixed: no Start-Transcript, WriteAllText + icacls; plus check() pre-check skips UAC when RSAT present). Release v0.2.2.
5. Lucide icon library + icon_text; FitLabel dynamic tile text; Home category filter + sidebar double-click; built-in password manager with CredentialField + ref linking; master-password explanation; list of password managers with APIs (SecretManagement, KeePass/KeePassXC, Bitwarden, 1Password, Passbolt, Psono, Devolutions, Delinea, CyberArk, Netwrix, Pleasant, HashiCorp Vault/Azure KV, Keeper; LastPass/Dashlane/Proton Pass weak). Release v0.3.0.
6. User requested (a) tool "OmniVault" (connectors SecretManagement, KeePass, Netwrix Password Secure; JSON connector definitions; search only; session-only secret cache; multi-credential dropdown; auth-failure → re-login popup with save), (b) tool "IconForge" (grid, search, filter, details panel, save-as with scaling and file types), (c) this AI documentation.

## 2026-10-16 — session 1 continued (after usage-limit pause)
7. Built (v0.4.0):
   - Core: credentials.py rewritten — providers with search()/get_secret(), AuthenticationRequired + auth_handler
     (UI popup ProviderLoginDialog instead of error), session cache (memory only, cleared on lock),
     register/unregister by owner tool; credential values = {"items":[{name,username,ref}|{name,username,password}],
     "selected": i} (old format auto-converted by normalize_value).
   - Tool hooks: tool.json "hooks": {"startup": "module:func"}; ToolManager.run_hooks after login, run_hook after install,
     _release_tool before update/uninstall.
   - UI: CredentialPickerDialog searches all providers async (local instant); CredentialField = dropdown + key/plus/trash,
     bindable to settings (settings=, key=), resolve().
   - Tool "OmniVault" (sec.omnivault 1.0.0): connector_types.json (secretmanagement,
     keepass, netwrix), connectors.py (PowerShellConnector generic from JSON scripts, KeePassConnector via pykeepass),
     UI (sources list, search, connector dialog with test + PS module install offer).
   - Tool "IconForge" (gfx.iconforge 1.0.0): model/proxy grid with custom delegate, categories/tags from
     resources/icons/lucide/meta.json (update_icons.py builds it from lucide repo tarball), details panel,
     style (color, stroke, background square/circle), export SVG/PNG/ICO(multi-size)/PDF(vector)/JPG, copy image.
   - AD tool 1.3.0: credential dropdown in its UI.
   - Netwrix: public docs say API only via C#/JS SDK (PsrApi, from customer portal), no REST/PS module -> connector
     is a PowerShell template loading the SDK DLLs; method names UNVERIFIED ("verified": false). Asked user for SDK docs/DLL.
   - SecretManagement not installed on dev machine -> not live-tested (dialog offers Install-Module).
   - Tested: KeePass end-to-end (auth popup flow, wrong pw retry, session cache, no secrets on disk), all export formats.

## 2026-10-16 — session 1, round 8 (v0.5.0)
8. User feedback/requests:
   - Rename "Password Manager Manager" -> user proposed "OmniKey"; I flagged conflict with HID OMNIKEY smart-card
     readers -> user chose **OmniVault** (id sec.omnivault, tools/omnivault). Icon Store -> **IconForge**
     (id gfx.iconforge, tools/iconforge), chosen from 10 suggestions.
   - Netwrix: user provided API docs URL; I read the PsrApi reference and rewrote the connector scripts
     (LoginWithApiKey or StartNewAuthentication flow; GetContainerList + PsrListFilterGroupContent;
     GetContainer + DecryptContainerItem). Connector has shell choice pwsh/powershell and auth_mode choice.
   - Connector dialog: single "Add connector" button, manager type chosen inside the dialog, fields rebuild
     dynamically; JSON supports choice fields and show_if. "Test connection" no longer saves (values_override).
   - Text review: removed chat-like phrasing / du-forms from de/en/fr/es UI texts (dialects stay playful).
   - IconForge: removed "name for tool.json" field (doc hint instead); 26 icon libraries (Lucide built-in, others
     downloaded from npm on selection, newest version >= 14 days); licenses.json + per-icon permission checklist
     (green check / red cross); brand variants add "trademark" cross. Coloring handles currentColor, single hard-coded
     color, no color; background handles any viewBox.
   - "Make this chat a project + chats per component": not possible from Claude Code (no API for claude.ai
     projects/chats) -> created docs/ai/claude-project/ (setup guide, project instructions, GitHub knowledge sync,
     chat starter prompts for main app + each tool).
   - Tested: all 26 packs downloaded (~118k icons, ~4.5 min), 1217-icon render sample OK; UI screenshots;
     KeePass flow + regressions OK.

## 2026-10-16 — project thread: Netwrix alpha + store titles
- Netwrix connector tagged alpha (user can't test, no Enterprise Pro): `connector_types.json` gets optional
  `stage` (alpha|beta) -> dialog type list shows "Name (Alpha)", description gets bold hint line
  (keys `stage.*` in omnivault de/en). OmniVault 1.0.0 -> 1.0.1, store rebuilt (only omnivault package changed).
- Store: tool names on store cards bigger (new object name `StoreCardTitle`, 14pt; shared `CardTitle` unchanged).
- Verified both with offscreen render (Linux, real fonts).

## 2026-10-16 — async credential resolve (v0.5.1, backlog item)
- Core: CredentialManager.is_instant(ref); resolve() safe in worker threads; clear_session() discards in-flight results.
- UI: workers.call_in_gui; install_auth_handler marshals ProviderLoginDialog to GUI thread; resolve_async();
  CredentialField.resolve_async(). SDK: ToolContext.get_credential_async(). Dev doc updated.
- Tools: AD User Lookup 1.3.1 (search resolves credential in background), OmniVault 1.0.1 (copy password in
  background); both min_app_version 0.5.1. App version 0.5.1. No new UI strings.
- Tested offscreen with fake slow provider: event loop keeps ticking, auth prompt runs in GUI thread, cache/local
  instant, clear_session during fetch not cached, provider error -> on_error.
## 2026-10-16 — EXE build (thread "EXE-Build mit PyInstaller")
- Asked (via project chat, "die ersten beiden" from backlog): EXE build with PyInstaller incl. tools/store/locales.
- Done: scripts/build_exe.py (onedir, icon from app.svg, Windows version info, docs next to exe, --zip, --console);
  main.py `--pip` mode + sdk.pip_install frozen path; app_updater picks -win64 asset when frozen;
  .github/workflows/build-exe.yml (windows-latest, Python 3.14, artifact); docs/EXE_BUILD.md; README/CLAUDE.md.
- Tested (Linux build, Python 3.13): app starts offscreen; frozen pip installed pykeepass; smoke exe installed and
  opened IconForge, OmniVault, Subnet calculator (AD lookup needs RSAT/pwsh -> Windows only).

## 2026-10-16 — round 9 (claude.ai project thread, IconForge 1.1.0)
9. User: IconForge library dropdown showed undownloaded packs; selecting one did nothing until the download finished.
   - Pack dropdown now lists only available packs (Lucide + downloaded). Download button (Lucide "download") next to
     it opens `PackWizard` (wizard.py): dropdown "Name · Größe · Herausgeber" (✔ = downloaded), generated hero
     banner (gradient in pack colour + icon pattern; real icons once downloaded, Lucide placeholders before),
     title, meta (publisher, version, unpacked size, files, published date, styles, licence, status, source link,
     npm link), buttons Download / Download again / Remove.
   - npm data: /latest for all packs (dropdown sizes, parallel), full doc for the selected pack (exact version that
     download() would pick); cached 24 h in packs/catalog.json.
   - Right panel reordered: Export (format, sizes, copy/save) on top, then preview, appearance, info, licence.
   - Widths in characters (font metrics) instead of px for top bar/panel (scales with font/scaling setting).
   - Verified via xvfb screenshots (dark/light, 1400 and 1000 px wide) and real feather download.

## 2026-10-16 — round 9: responsive UI + scaling (thread "Responsive+Skalierung", Claude Code cloud session)
9. User: whole UI must look as good maximized on 8k as small on 1k; add "Skalierung" option to display settings.
   - New settings tab "Anzeige" (theme moved there from "Allgemein", + scaling combo 75-300 %, restore layout).
   - Scaling = `ui_scale` setting -> QT_SCALE_FACTOR set before QApplication (ui/scaling.py); multiplies with
     Windows scaling. Needs a new process -> dialog offers immediate restart (re-login), else applies next start.
   - Icons (tool_icon/library_icon) rendered at real device pixel ratio instead of fixed 2x -> sharp at 300 %+.
   - Responsive: ResponsiveRow (header/buttons wrap below when narrow) for Home/Store headers, details-panel
     buttons, store cards, password manager buttons; Store cards in ColumnFlowLayout (1-6 columns by width);
     details panel width 28 % (300-560); main window start size relative to screen; dialogs fit_to_screen /
     fit_min_width; long requirement ids get zero-width break points (breakable()).
   - Subnet calculator 1.2.1: splitter switches to vertical below 900 px, table columns size to contents.
   - SDK: device_pixel_ratio(), fit_to_screen() for tools.
   - Tested by offscreen renders: 760x560, 1000x640, 1280x720 (100 %) and 2560x1400 logical at 200/300 % (= 8k px).

## 2026-10-16 — merge of PRs #1-#5 + version 0.6.0 (thread "PRs zusammenführen und 0.6.0")
- Integration branch claude/merge-0-6-0-i4gq40, merged in order: #1 Netwrix alpha/store titles, #2 async credentials,
  #3 PyInstaller EXE, #4 IconForge wizard, #5 responsive/scaling. PR branches not rewritten.
- Conflicts: docs/ai/* (kept both sides), ui/credentials.py imports (scaling + call_in_gui), store/index.json +
  omnivault zip (both PRs bumped OmniVault to 1.0.1 -> one combined 1.0.1, never released before).
- App 0.6.0 (0.5.1 from #2 never released). Tools: AD User Lookup 1.3.1, IconForge 1.1.0, OmniVault 1.0.1,
  Subnet calculator 1.2.1; store fully rebuilt (all 4 tools changed). check_locales OK.
- Smoke test (Linux offscreen): tools install, main window 900/1400/3840 px, IconForge/OmniVault/Subnet open.

## 2026-10-16 — GitHub Actions CI for every PR (thread "GitHub-Prüfungen für PRs", proposal 3)
- New `.github/workflows/ci.yml`: Linux job (compileall, check_locales app + all tools, check_store) and Windows job
  (`scripts/smoke_test.py`). `build-exe.yml` now runs on every PR/push main (no paths filter) + starts the EXE.
- `scripts/check_store.py`: store/index.json matches tools/ (version, zip exists, sha256/size, zip content == tool dir,
  CRLF/LF ignored) -> catches "tool changed but version not bumped / store not rebuilt".
- `scripts/smoke_test.py`: temp OMNIWRENCH_HOME, creates vault, installs store tools without system requirements
  (AD User Lookup only validated: RSAT), opens main window in all 8 languages, store tab, all tools, 3 widths;
  any QMessageBox / ERROR log / uncaught exception fails. Runs locally too (`--visible` for real windows).

## 2026-10-16 — EXE signing prepared (thread "EXE signieren", Claude Code cloud session)
- Branch claude/exe-signing-0i9n5y stacked on PR #8 (CI) because both change build-exe.yml.
- scripts/sign_exe.py: signtool (Windows SDK, auto-found) or osslsigncode (non-Windows, PFX only); cert from env
  (SIGN_CERT_SHA1 / SIGN_PFX_BASE64 / SIGN_PFX_PATH + SIGN_PFX_PASSWORD, SIGN_TIMESTAMP_URL); retries 3x; masks password.
- build_exe.py: --sign (signs if configured, else notice) and --no-build (sign/zip existing folder, used by CI).
- build-exe.yml: build -> tests -> optional signing (Azure artifact-signing-action@v2 / SignPath submit action@v2 /
  PFX via sign_exe.py) -> Get-AuthenticodeSignature check -> zip -> upload.
- docs/EXE_SIGNIEREN.md: options table + recommendation + setup per method. Tested on Linux with a self-signed PFX
  (osslsigncode verify ok); Windows/CI signing paths untested without credentials.
- Stef picked "SignPath + MIT" on the decision card -> LICENSE (MIT), README "Lizenz" + "Code signing policy"
  (SignPath credit line, roles, privacy statement incl. GitHub store/update check), LICENSE shipped next to the EXE,
  EXE_SIGNIEREN.md with SignPath application steps.
- Stef asked for copy-paste values: EXE_SIGNIEREN.md now has every SignPath form answer (English) in code blocks,
  SignPath/GitHub settings after approval (slugs omniwrench / release-signing / omniwrench-exe); README privacy
  statement got its own heading (#datenschutz) for the privacy URL.
- v0.6.0 released by CI (tag pushed by user). Assets came out win64-first -> workflow now uploads source zip first,
  win64 separately; user asked to re-upload the win64 asset of v0.6.0 so the source zip is first.
- Re-upload didn't help: assets are sorted by name. User chose: keep names, update 0.5.x installs manually once.
