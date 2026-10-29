# Decisions & user preferences (binding)

## Product / branding
- Name: **OmniWrench** (Ratchet & Clank reference), vendor **KuroShiro** (Stef 2026-10-22; was DarkMatter, imaginary).
  Python package `omniwrench`. Domain kuroshiro.me (landing page). `LEGACY_VENDORS` in `omniwrench/__init__.py` lists old
  vendor names; DPAPI entropy in `core/dpapi.py` keeps "DarkMatter…" forever (else recovery data unreadable).
- GitHub: `KuroShiroMe/OmniWrench`, **public** (owner renamed from `Steffi-Tech` on 2026-10-22; GitHub redirects old URLs,
  app migrates stored update/store URLs in `core/settings.py`). No GitHub org (gh can't create orgs); could move later.
- Data dirs: `%APPDATA%\KuroShiro\OmniWrench` (settings, vault, tool_settings, layout), `%LOCALAPPDATA%\KuroShiro\OmniWrench` (tools, tool_data, logs). Override: `OMNIWRENCH_HOME`.
  Linux (2026-10-22): `$XDG_CONFIG_HOME/KuroShiro/OmniWrench` (config) + `$XDG_DATA_HOME/KuroShiro/OmniWrench` (local).
  Old locations (`DarkMatter` vendor dirs, Linux `~/AppData/...`) are moved at import of `core/paths.py` if the new dir
  is empty; if the move fails the old dir stays in use (no apparent data loss). Optional `portable-data/` folder next to the program
  = all data there (my addition for USB-stick use; default for portable stays the user profile).

## Platforms & installation (Stef 2026-10-22, CHANGED: before "Windows clients only")
- **Windows clients AND Linux** are supported platforms of the main program (Stef: "für Windows und Linux").
  Windows Server stays unsupported (notice on Home). macOS not planned.
- Tools declare `platforms`; Linux-capable: subnet calculator, IconForge, NetProbe, OmniVault (except SecretManagement
  + Netwrix connectors, filtered via connector_types "platforms"). Windows-only: AD User Lookup (RSAT/PowerShell),
  MS DHCP Extended Management (dhcpsapi.dll/RSAT). Store shows "Läuft nur unter …" without install button.
  Certificate/smart-card login only on Windows (Linux: master password only).
- Stef: release offers an installer AND a portable version ("Mobile Version" = portable) for Windows and Linux.
  Program files in the program folder, config/vaults/tools in the user profile.
- My choices: Windows = **Inno Setup 6** (single setup.exe, wizard + /VERYSILENT for Intune/SCCM, upgrades via
  fixed AppId, no signing requirement; MSI/WiX more complex, MSIX needs a signature). Per-machine install to
  `{autopf}\KuroShiro\OmniWrench` (UAC; setup moves installs from the old default `{autopf}\DarkMatter\OmniWrench`,
  custom dirs stay; mutex check covers `KuroShiro.OmniWrench` and old `DarkMatter.OmniWrench`), start menu, optional desktop icon (unchecked). Linux = **.deb**
  (/opt/omniwrench, /usr/bin/omniwrench, .desktop, apt resolves Qt system libs), built on Ubuntu 22.04 (glibc 2.35).
  No rpm/AppImage yet (offered as follow-up). Portable: Windows ZIP (name unchanged), Linux tar.gz.
- Uninstall keeps user data (vault!). Self-update follows the install kind (setup -> silent setup with UAC,
  deb -> pkexec apt-get, portable -> replace files, elevated copy if the folder is read-only).

## Tech
- Python + PySide6 + PySide6-QtAds (docking) — chosen by user over C#/WPF and PowerShell.
- Store = GitHub repo with `store/index.json` (+ zipped tool packages, sha256). Default repos: local dev store (if running from source) + official raw.githubusercontent URL.
- App updates via GitHub Releases (`vX.Y.Z`, asset `OmniWrench-X.Y.Z.zip`).
- TLS via `truststore` (Windows cert store) — corporate TLS inspection on user's machine.

## UI (user requests)
- Tabs on top; Home tab always open (not closable); Store tab openable; each tool opens in own tab; tabs dockable side-by-side/stacked/floating (QtAds).
- Left sidebar: installed tools tree by category. Double-click category → Home with category filter.
- Categories (Stef 2026-10-17, simplified 2026-10-20): service-oriented, "large IT department with many expert teams".
  11 fixed areas (workplace, identity, network, infrastructure, cloud, security, applications, operations,
  servicedesk, automation, documentation) + other; **only one level** (Stef 2026-10-20: "nur noch Hauptkategorien,
  alle Tools kriegen sinnvolle Tags"). Finer grouping via visible, clickable `tags` (language-neutral tech/product
  names, else English). Tools may still bring an own area. List + rules: core/categories.py,
  docs/TOOL_ENTWICKLUNG.md#kategorien / #tags.
- Store + Home identical (Stef 2026-10-27): lean card = icon + title next to it, screenshot carousel below (arrows/dots
  to click through), short `description` below, ONE button (Install/Open/Update/"Läuft nur unter …"). Single click →
  right DetailsPanel with ALL metadata (screenshots+captions, long description, versions, category, tags, platforms,
  author, id, requirements, source, homepage) + Install/Update/Open/Settings/Folder/Uninstall. Double click → open
  (installed). Right click → menu (Open, Settings, Update, Check, Repair, Folder, Uninstall), installed tools only.
- Home view modes (Stef 2026-10-27): "Vollansicht" (= Store cards, default), "Große Icons", "Kleine Icons",
  "Liste mit Details" (sortable columns). Switch = segmented buttons next to search, saved in setting `home_view`.
- Tool screenshots (Stef 2026-10-27: "die wirst du jedes mal rendern"): every tool has `screenshots` in tool.json,
  first = main shot, then one per function; rendered by Claude via `screenshots/render.py` + fake data whenever the
  UI changes. Claude's choice: 1280x800, dark theme, ENGLISH UI (store audience is international; `--lang de`
  possible if Stef prefers German). Not in the zip, published separately -> no version bump for new pictures.
- Tile names (large icons): shrink font first (down to 8.5pt), then wrap (spaces/after hyphens) into 2 lines, then elide.
- Home has "Filter" button (categories) + filter chip.
- Dark theme default; light available.

## Tool package format (user spec)
- Each tool must have: config/settings file (config.json), install routine (install.py), metadata file (tool.json incl. display data, description, category path).
- Requirements (RSAT etc.) auto-installed. `check()` runs first; if nothing missing → skip system requirements (no UAC).
- Per-tool settings dialog generated from config.json (paths, credentials, certificates …).
- Icons: `icon` = image file in tool dir OR Lucide library name; `icon_text` = custom short text; else initials.
- Icon library: Lucide (ISC, free commercial). Bundled offline in `omniwrench/resources/icons/lucide`.

## Security
- Master password and/or user certificate (smart card). Envelope encryption: random DEK, wrapped by Argon2id(password) AES-GCM and/or RSA-OAEP(cert). User asked for "hash compare"; explained current design is equivalent/better (no hash stored, verify by AEAD decrypt, DEK kept in session). User accepted ("wir machen das so").
- Signing-only certs (Intune device certs) are filtered out.
- Built-in password manager in main app (local provider in vault). Credential picker = simple full-text search.
- Lost master password (Stef 2026-10-20): "Passwort vergessen?" on the login resets the vault. Reset = ALL stored
  secrets gone (incl. password-manager connector credentials, GitHub token, cert unlockers); every entry stays, its
  password marked with ❗ and the entry simply doesn't work until a new password is set. Only passwords are deleted.
  My choices: entries survive via a secret-free recovery copy in vault.json, protected with DPAPI (CurrentUser, so only
  the same Windows account can reset with data); without readable copy the reset still works but the manager is empty.
  Old vault file kept as `vault.before-reset-<ts>.json`. Reset asks for a new password + "delete permanently" checkbox.

## i18n
- Languages: de, en, fr, es + fun: de_bad (Badisch), de_by (Bayrisch), de_hes (Hessisch, added 2026-10-16 on Stef's request), en_sco (Scots), en_posh (Posh English). Files flat JSON with `_meta.fallback`.
- 2026-10-16 Stef: "alle sinnvollen und die Dialekte" -> added it, nl, pl, pt (Brazilian, code `pt`), cs, sv, tr, uk
  (fallback en) and de_swg, de_sxu, de_nds, de_gsw, de_ksh, de_wien (fallback de). 23 app locales. Not chosen: ja, zh, RTL.
  Tool locales are NOT required for every language (fallback). Language lists sort accent-insensitive (_sort_name).
- Language dropdowns (app + tool settings) list dialects indented under their main language (Stef 2026-10-16).
  Dialect code convention `<base>_<suffix>`; i18n.language_tree() groups by the part before "_".
- App language in settings; change rebuilds UI without re-login.
- Tools: own `locales/`; per-tool language setting ("auto" or fixed). Auto = app language if tool has it, else dialect base language (my addition, user informed), else English.

## OmniVault (decided 2026-10-15, built 2026-10-16 v1.0.0)
- Separate tool "OmniVault": contains own manager + connectors to external managers.
- First connectors: Microsoft SecretManagement, KeePass, Netwrix Password Secure (user has Netwrix to test).
- Connector type definitions in a JSON (fields needed for API). Only simple search for now (no folder trees).
- Access credentials for each connector configured in the connector's settings.
- Picker stays simple (full-text); when tool installed, picker searches all connected managers too.
- Credentials referenced by tools: fetched once per session from manager, kept in memory only (never cached on disk).
- Credential field supports MULTIPLE saved credentials → name dropdown; list persisted (refs only), secrets fetched at login time.
- If manager auth fails (changed password): NO error message — show popup asking for connector credentials, with "save" option, then retry.

## IconForge (decided 2026-10-15, built 2026-10-16 v1.0.0)
- Tool "IconForge": browse icons (start with bundled Lucide), search + filter, cool grid, click → right metadata panel, show name usable in tool.json, "Save as" with scaling options and multiple file types (for Visio etc.).
- Implementation choices (mine): connector secrets saved only if "save login data" is checked, else asked once per
  session; connector dialog offers Install-Module for missing PS modules; IconForge export formats SVG/PNG/ICO/PDF/JPG
  (EMF not supported by Qt); "copy image" for pasting into Visio.

## EXE build (2026-10-16, my choices)
- PyInstaller **onedir** (not onefile): faster start, fewer AV false positives, self-updater can overwrite files.
- Release ships two assets: `OmniWrench-X.Y.Z.zip` (source) + `OmniWrench-X.Y.Z-win64.zip` (EXE); upload source first.
  (2026-10-16) GitHub sorts assets by name, so -win64 is listed first anyway; user chose to keep the names and
  update 0.5.x installs manually once instead of renaming the source zip.
- Local dev store not shipped with the EXE. Installers since 0.7.0 (see "Platforms & installation"). Code signing: see "EXE signing" below.

## Round 8 decisions (2026-10-16)
- Tool names: **OmniVault** (not OmniKey: HID OMNIKEY trademark conflict, user agreed), **IconForge**.
- UI text style: neutral program language — no "du", no chatty explanations; imperative/impersonal like normal software.
  Dialect locales may stay playful. Developer docs (TOOL_ENTWICKLUNG.md) may address the reader informally.
- Connector dialog: one "Add connector" button; type selection inside the dialog; fields from JSON update live.
- IconForge: no "tool.json name" field; dev doc says: library icon names = names shown in IconForge (Lucide).
- IconForge libraries: only Lucide bundled offline; all others downloaded on demand when selected.
- Every icon shows licence + checklist (licenses.json, permission_order); disclaimer "no legal guarantee".
- Project/chats: maintained as docs/ai/claude-project/ (user sets up claude.ai project; files stay on GitHub).

## Password connectors 2 (2026-10-16, my choices)
- Bitwarden/1Password via their official CLIs (bw, op) - no own crypto/API re-implementation; HashiCorp Vault via
  plain HTTP API (no extra Python package). All three stage alpha until tested live.
- Bitwarden: per-connector CLI data dir so it never touches the user's own bw login; session key only in memory.
- Vault search = path names only (no reading every secret); user name shown after selection.

## Round 9 decisions (2026-10-16)
- IconForge: library dropdown shows ONLY downloaded libraries; a download button next to it opens a wizard
  (dropdown with name, size, publisher; preview = generated hero banner, title, meta info, source link).
- IconForge right panel: export controls (sizes, format, save/copy) at the top, everything else below.
- (mine) Wizard also offers "Download again" and "Remove" for downloaded libraries; publisher stored statically
  in icon_packs.json (npm author fields are inconsistent).

- Display settings live in their own tab "Anzeige" (theme, scaling, restore layout); language/auto-lock stay in "Allgemein".
- Scaling (my choice): uniform QT_SCALE_FACTOR on top of Windows scaling, choices 75-300 %, effective after restart
  (Qt can't change it at runtime); restart offered immediately. Chosen over manual font/px scaling because it also
  scales tools, QtAds and Qt-internal metrics consistently.
- Responsive rule for all UI: no fixed widths that sum above ~700 px in one row; rows that may overflow use
  ResponsiveRow; card lists use ColumnFlowLayout; self-drawn pixmaps use device_pixel_ratio().

## CI (2026-10-16, my choices)
- Checks run on every PR and push to main; EXE build too (no paths filter) because tools/app changes can break it.
- Smoke test never installs system prerequisites (RSAT, features, PS modules, winget) on runners - only validates.
- Store consistency is enforced: a changed tool without version bump + rebuilt store fails CI.

## EXE signing (2026-10-16, my choices; certificate choice is Stef's, open)
- Only OmniWrench.exe is signed (bundled DLLs keep their own signatures). SHA-256 + RFC 3161 timestamp.
- Secrets never in repo/chat: local signing via env (SIGN_CERT_SHA1 or SIGN_PFX_*), CI via GitHub secrets/variables.
- CI signs only on tags v* and manual runs; method chosen by repo variable SIGN_METHOD (azure|signpath|certificate);
  empty -> unsigned build, no failure. PR/main builds stay unsigned.
- Stef chose (2026-10-16): **SignPath Foundation** + repo licence **MIT** (LICENSE, copyright "KuroShiroMe", formerly "Steffi-Tech").
  2026-10-17 SignPath application REJECTED -> signing on hold. 2026-10-22: README "Code signing policy" replaced by
  "Signierung" (honest: unsigned) + "Datenschutz" (keep it accurate when adding automatic network access).
  Alternatives rejected for now: Certum OSS, company PKI, OV, Azure (EU orgs only).

## UAC prerequisites (2026-10-16, my choices)
- Elevation via ShellExecuteExW (not Start-Process -Verb RunAs); already-elevated app runs without prompt.
- WSUS/Features-on-Demand errors: only a hint text; OmniWrench never changes policies/registry on its own.
- Restart needed: notice in the install log only, no automatic restart.
- Stef (2026-10-16): OmniWrench targets Windows clients, **not Windows Server** (Linux added 2026-10-22, see above). On Server only a notice on Home
  ("functions limited"); no Server-specific prerequisite handling.
- Translation style (2026-10-16, my choice, consistent with existing files): fr infinitive/impersonal + "Veuillez" for
  requests; es formal "usted" imperatives (Seleccione, Introduzca); dialects keep their own consistent spelling per
  file (de_bad: noch/vu/sälwer/hät, de_by: nomoi/sejba/omeidn) and may stay playful/informal.

## Tool updates (Stef 2026-10-20; details my choices)
- Startup: if tool updates exist -> non-blocking dialog listing "Name: old → new" with "Alle aktualisieren" / "Später"
  (Später = status-bar button stays). Shown only when the startup check runs (check_updates_on_start or auto update).
- "Alle aktualisieren": button in Store header (only visible with updates, shows count) and in Settings › Updates;
  one TaskDialog for all tools, one failing tool does not stop the others; open tools are closed after one question,
  tools refusing to close are skipped.
- Install/update windows (store install/update, update all, app update) show checkbox "Dieses Fenster nach Abschluss
  schließen"; setting `close_update_window` is saved immediately when toggled, also in Settings › Updates.
  Window closes itself only on success; on errors it stays open.
- Setting `auto_update_tools` (default off): at startup updates install silently in the background (status bar + log
  only). Skipped and still offered: tools open in a tab, and updates whose requirements changed (may need UAC; should
  not appear unannounced). If everything was skipped, the normal startup dialog appears instead. Opening/updating/
  uninstalling a tool while it is updated in the background is refused with a status message.

## MS DHCP Extended Management, formerly ScopeKeeper (2026-10-19, rebuilt from Stef's DhcpScopeManager.ps1, my choices)
- Stef wanted the full concept rebuilt as OmniWrench tool, not a copy. Name ScopeKeeper, id net.scopekeeper, category
  network/ip_dns_dhcp, IPv4 only (like the script). Tag "alpha" + Alpha note in the description until Stef tested it (removed 2026-10-22, 1.2.0).
- Requirement RSAT DHCP tools (windows_capabilities Rsat.DHCP.Tools); uninstall keeps RSAT.
- Defaults: connect failover partners at login = on, auto replication = on (both switchable in settings/main page).
- Partner fallback chain kept from the script: CIM/WinRM -> RPC (failover API + netsh dump/commands).
- Server options are never replicated automatically; deleting scopes needs the typed word (ov.delete_word).
- Passwords never on a command line or in logs (only in memory; passed to LogonUser/CreateProcessWithLogonW).
- 2026-10-20 (Stef): display name "MS DHCP Extended Management" (tool.json name + tool.name). Same day (Stef): internal id
  changed too -> net.ms-dhcp-extended (new tool, must be installed fresh; no migration from net.scopekeeper). Check runs in the background, never freezes the UI; login checkbox "Server direkt nach
  der Anmeldung prüfen" (setting auto_scan, default on). Login shows a loading view, on failure back to the login form.
  Connection steps are logged calmly ("Verbinde … per RPC …"), never styled as errors.
  Long hint labels replaced by "?" help icons with tooltip (ui_base.help_icon).
- Scan backend gets the login password in memory (DhcpService.secrets) to log in a second time; never written to
  disk/settings, cleared on reset/logout.
- 2026-10-20 (Stef, binding for all work): "möglichst alles in Python, PowerShell nur wenn unbedingt nötig".
  DHCP tool therefore uses dhcpsapi.dll via ctypes (no WinRM/CIM/DhcpServer module); RSAT stays only for netsh dhcp
  (replication). Other PowerShell uses in the app: see backlog (inventory 2026-10-20).
- 2026-10-22 (Stef): overview columns freely movable, default order Name, Beschreibung, Scope ID, Präfix, Status,
  Freie Adressen, Belegt %, Lease-Dauer, Befunde, Failover (my reading of "Verteilbar (Freie Adressen)": free count;
  "Verteilbar" + "Bereiche" kept as hidden optional columns). Failover: every server of a relationship as own row,
  click shows all scopes of that server. Check page: distribution shown, no level dot on the tabs, prominent
  segmented switch. Server options: list of all failover servers, sync state per option, opt-out checkbox
  "Auf Partner übertragen" on add/edit, transfer only per option (no "all" button). Definitions: BOTH expert mode
  setting (dock hidden otherwise, default off) and unlock button with expert warning (my choice: Stef offered either).
  Rights: UI adapts to read-only (DHCP Users) - write controls hidden, not just disabled.
- 2026-10-22 (Stef, 1.2.0): failover list = expandable relationship row, children = the two servers (collapsed by
  default). Server options list only the selected server's options (no rows for options that exist only on the
  partner). Alpha note removed although the rights probe is still untested on real servers (Stef's call).
- 2026-10-23 (Stef, 1.3.0): scope address range like the classic DHCP console - one pool (start/end) plus
  exclusions; the range list that converted gaps into exclusions is removed completely. Scan must find every
  difference between failover servers (my scope of "all": scope fields, pool, lease, exclusions, options all
  classes, reservations, relationship settings and scope lists, classes, definition types; not leases or policies).
- 2026-10-23 (Stef, after the 0x4EA4 incident: "nicht, dass Dinge gelöscht bleiben"): every user action in the DHCP
  tool is a transaction - on error or cancel everything it changed (server and partner) is undone automatically.
  Paste and draft creation are all-or-nothing (no "partially done" results). Final, not undoable, therefore always
  the last step: lease delete, scope delete, definition delete. Multi-scope replication is atomic per scope.
- 2026-10-23 (Stef, 1.4.0): detect changes made by others. Conflict check before every scope/server-option write
  (reload keeping own edits / save anyway / cancel), auto-refresh with selectable interval (default 5 min, combo in
  the top bar + tool setting), "who" from the DHCP server's Operational event log. Stef said "kannst das dann auch
  gleich mergen" -> merged without waiting for Windows tests.

## Landing page (2026-10-22)
- kuroshiro.me = static landing page from `site/` in the OmniWrench repo, deployed via GitHub Pages (Actions,
  `.github/workflows/pages.yml`). My choice: no extra repo (cloud can't create repos, downloads/screenshots stay in sync
  with the product). Can move to a `KuroShiroMe.github.io` user-site repo later if KuroShiro gets more products.
- Page language German, dark design in app colors, no tracking, no external fonts/scripts except the GitHub API call.
- Tool list on the page (Stef 2026-10-22): collapsible service areas like in the store (alphabetical, German names),
  click on a tool opens its wiki page (`homepage` from tool.json, else `wiki/Tool-<German name>`). Generated from
  store/index.json by `scripts/build_site.py` (also runs in the Pages workflow, so new tools appear automatically).
- Rule (Stef 2026-10-22): every thread checks whether its work adds something relevant for the landing page and adds it.

## Wiki and developer docs (2026-10-22)
- Stef: GitHub Wiki for all user/developer docs. Home page presents the main program, sub pages per area
  (Installation, Einstellungen, Tresor, Passwortmanager, Store, Datenablage, Fehlerbehebung …), one detailed page per
  tool (all functions), developer area (build tools, own repository, template repo, integrate repositories).
- Standardized structure: `wiki/Vorlage-Tool-Seite.md` (tool pages: Kurz, Steckbrief, Inhalt, Wofür, Installation,
  Erste Schritte, Funktionen im Detail, Einstellungen, Sicherheit, Grenzen, Fehlerbehebung, Versionen, Siehe auch)
  and `wiki/Vorlage-Bereichsseite.md`. Every future tool MUST get a full page in the same PR (Stef's rule).
- Wiki source lives in the repo (`wiki/`), synced by workflow (my choice: reviewable via PR, cloud can't push to the
  wiki repo directly). Page names: `Tool-<display name, spaces as hyphens>` (matches landing page fallback).
- `docs/` only for Stef + Claude; third-party developer docs only in the wiki.
- Template repo: GitHub "Template repository" `KuroShiroMe/OmniWrench-Tool-Template`, content from
  `templates/tool-repo/`. Self-setup workflow on first push (placeholders, first tool, store), store workflow with
  version guard (changed tool without version bump fails). Template keeps `.github/workflows/setup.yml` after setup
  (GITHUB_TOKEN may not modify workflows), only the marker `.github/template-setup.json` is deleted.
- Help menu: "Online-Hilfe (Wiki)" (F1) opens the wiki, "Tool-Entwicklung" opens wiki/Entwicklung; docs/ no longer
  shipped next to the EXE.
- DHCP tool IPv6 (1.5.0, Stef 2026-10-23: "beide Tools eigenständig, Zusammenarbeit wo sinnvoll"):
  one tool for both families, segmented IPv4|IPv6 switch (setting "family") instead of a second tool. Overview,
  server options and definitions follow the switch; check and event log always cover both. v6 scopes are created via
  a dialog (no draft tab: no pool, no failover). Clipboard carries "Family"; cross-family paste is rejected.
- DHCP <-> DNS tool cooperation: the DHCP tool only checks DNS via the system resolver (dnscheck.py, optional
  "DNS-Abgleich"); it never imports the DNS tool. The DNS tool does not touch tools/ms_dhcp_extended.

## MS DNS Extended Management (2026-10-23)
- Stef: name "MS DNS Extended Management", id net.ms-dns-extended; editing in the first version; support every kind of
  MS DNS server incl. servers outside a domain; IPv6 from the start; DNS and DHCP tool must work fully independently
  (no imports between tools), cooperation only where it helps (DNS tool reads DHCP leases itself, DHCP tool checks DNS
  via the system resolver); pywin32 is allowed as a dependency.
- My choices: WMI (root\MicrosoftDNS) instead of PowerShell/dnscmd (Python-only rule, no RSAT); editing = delete +
  create as one transaction; zone delete, scavenge now, clear cache are final and need confirmation; local server
  always uses the logged-on account (WMI forbids local credentials).
- DNS tool error popups (Stef 2026-10-27): every failure offers "Detailansicht" with the technical trail (all attempts,
  exact WMI messages) for troubleshooting; never include passwords.
- DNS tool replication (Stef 2026-10-27): per-record "Repliziert" indicator + manual trigger, both. Missing replication
  right must be handled with a clear message (who lacks which right on which partition), remaining steps still run.
  Standalone DNS (no AD) is covered via zone transfer status/trigger.

## Server favourites (2026-10-28, reworked 2026-10-29)
- Stef (KI feasibility doc, A3): DHCP and DNS tool get a favourites list storing servers + connection settings;
  AI settings per server will live there too (section "ai", KI thread). Every tool gets an AI setting inherited from
  the main program, login tools get a dropdown at login (KI thread's job).
- Stef 2026-10-29: no dropdown; collapsible list LEFT of the login window with folders, manual creation in the list,
  favourite (star) button at the address field; a password can be linked per favourite (customers with different
  passwords, no separate favourite + password selection).
- My choices: favourite password lives encrypted in the vault (context.secrets "fav:<id>"), never in settings; other
  login modes: current user, password-manager reference, user only. Click fills the form, double click logs in.
  One identical favorites.py per tool (tools stay independent); DHCP favourite restores the IPv4/IPv6 view, DNS
  favourite can add further servers and the DHCP server for the comparison; manual server edit deselects; last
  favourite, panel state and collapsed folders are remembered; deleting a folder moves its content up.
## AI assistants (KI-Integration, 2026-10-28, Stef's answers A1-A15 / B1-B12 in the planning doc)
- Everything local and readable (JSON/Markdown/PNG/MP3/MP4). Storage dropdown with 3 modes: "Eigene Dateien"
  (Documents/Pictures/Music/Videos + OmniWrench subfolder), "Zentraler Speicherort" (one folder, subfolders per type),
  "Je Typ" (folder per type). Encryption of chats/projects/transcripts ON by default with notice that other programs
  can't read them; media never encrypted.
- Any number of connections, also several accounts of one provider; one primary assistant (★). Browser sign-in where
  officially possible (Sign in with ChatGPT, OpenRouter OAuth, Entra for M365 Copilot, custom OAuth), else API key
  (vault or password manager reference). NO Claude subscription OAuth (forbidden since 02/2026, legal/GitHub risk) -
  custom OAuth instead. No unofficial Grok OAuth. Stef tests only with Claude (API key) + ChatGPT subscription, no
  extra costs. M365 Copilot: no alpha tag, experiences via wiki (Stef has no license).
- Provider list via the store mechanism (store/ai/providers.json, built from omniwrench/resources/ai/providers.json).
  Providers are never deleted: status "removed" -> red in lists + notice when used. **Rule: every time I build
  something for OmniWrench, check providers for additions/removals/changed conditions and update providers.json.**
- KI-Zugriff page for main program AND every tool without exception; tools inherit the main program level unless
  changed; levels Nichts..Ändern mit Bestätigung; main default level 1 (Beschreibung); per-assistant exceptions.
  Tools that log in (DHCP/DNS) get an AI level dropdown at login (favorites "ai" section: {"level": null|int,
  "pseudo": null|bool}, null = inherit). Pseudonymization ON for everything by default.
- Chat panel: dockable (right), minimal (bot dropdown switchable mid-chat, detail Kurz/Normal/Ausführlich, history,
  projects). No bot -> message with "Optionen öffnen". Context menu "Assistent fragen …" with setting: always primary /
  active / always ask (picker).
- Tool (KI-Studio): Ratchet & Clank name -> **Clank – KI-Studio** (ai.clank, chosen 2026-10-28); R&C name list for
  future tools in docs/ai/rc-names.md. Greyed tabs with hint + button
  when no capable bot. Repos: Git, GitHub, GitLab, Azure DevOps. Commands: window with command + short explanation,
  confirmation with "remember answer" (per session). ffmpeg asked at install; music/video tabs greyed until present.
  Group chat with brakes, many options grouped and collapsible. Extras: templates, documents, screenshot, scheduling,
  MCP client/server (server last), live transcription tab (system audio + mic, summary, speaker recognition with
  named long-term profiles, prominent consent notice at start), live voice agent with wake word ("Hey <name>").
- MCP (my choices 2026-10-28, stage 7b): client + server live in Clank (run only while Clank is open, like
  schedules). Server only on 127.0.0.1 with mandatory token, same access levels/pseudonymization/confirmation as
  built-in assistants (exception key "mcp-server"); never re-exports foreign MCP tools. Client: tool annotations only
  trusted when the user ticks "Server vertrauen", otherwise every MCP tool = level 4 with confirmation.
- Speech (my choices 2026-10-29, stage 7c): no audio is stored, only text; voice features only in memory unless a
  speaker profile is saved (opt-in in the consent dialog, profiles always encrypted). Consent dialog on EVERY
  recording start + red banner. Wake word only offline (Vosk) - never stream all mic audio to a cloud provider;
  without Vosk only push-to-talk. Default voice = system voice (free, offline). numpy/soundcard/vosk installed on
  demand into the tool's _lib, not at tool install.
- Speaker profiles (Stef 2026-10-29): opt-in stays; starting with profiles shows ProfileNotice (bold, Art. 9 DSGVO,
  user is responsible, confirm checkbox). Hidden by Stef's wish: toggling the opt-in 10x within 6 s reveals "always use
  profiles without notice" (setting ts_profiles_always) - not in wiki/UI help. Recording consent dialog always stays.
  Stef asked to make it "less obvious in the code"; I kept it plain + commented (public repo, privacy-relevant code
  should stay reviewable).
- Work pacing (Stef): no real 80 % usage limit possible -> work in packages, commit+push, pause ~5 h between packages.
