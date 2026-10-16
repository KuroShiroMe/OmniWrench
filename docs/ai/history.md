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

## 2026-10-16 — EXE build (thread "EXE-Build mit PyInstaller")
- Asked (via project chat, "die ersten beiden" from backlog): EXE build with PyInstaller incl. tools/store/locales.
- Done: scripts/build_exe.py (onedir, icon from app.svg, Windows version info, docs next to exe, --zip, --console);
  main.py `--pip` mode + sdk.pip_install frozen path; app_updater picks -win64 asset when frozen;
  .github/workflows/build-exe.yml (windows-latest, Python 3.14, artifact); docs/EXE_BUILD.md; README/CLAUDE.md.
- Tested (Linux build, Python 3.13): app starts offscreen; frozen pip installed pykeepass; smoke exe installed and
  opened IconForge, OmniVault, Subnet calculator (AD lookup needs RSAT/pwsh -> Windows only).
