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
6. User requested (a) tool "Password Manager Manager" (connectors SecretManagement, KeePass, Netwrix Password Secure; JSON connector definitions; search only; session-only secret cache; multi-credential dropdown; auth-failure → re-login popup with save), (b) tool "Icon Store" (grid, search, filter, details panel, save-as with scaling and file types), (c) this AI documentation.

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
   - Tool "Password Manager Manager" (sec.password-manager-manager 1.0.0): connector_types.json (secretmanagement,
     keepass, netwrix), connectors.py (PowerShellConnector generic from JSON scripts, KeePassConnector via pykeepass),
     UI (sources list, search, connector dialog with test + PS module install offer).
   - Tool "Icon Store" (gfx.icon-store 1.0.0): model/proxy grid with custom delegate, categories/tags from
     resources/icons/lucide/meta.json (update_icons.py builds it from lucide repo tarball), details panel,
     style (color, stroke, background square/circle), export SVG/PNG/ICO(multi-size)/PDF(vector)/JPG, copy image.
   - AD tool 1.3.0: credential dropdown in its UI.
   - Netwrix: public docs say API only via C#/JS SDK (PsrApi, from customer portal), no REST/PS module -> connector
     is a PowerShell template loading the SDK DLLs; method names UNVERIFIED ("verified": false). Asked user for SDK docs/DLL.
   - SecretManagement not installed on dev machine -> not live-tested (dialog offers Install-Module).
   - Tested: KeePass end-to-end (auth popup flow, wrong pw retry, session cache, no secrets on disk), all export formats.
