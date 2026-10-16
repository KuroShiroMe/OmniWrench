# Decisions & user preferences (binding)

## Product / branding
- Name: **OmniWrench** (Ratchet & Clank reference), vendor **DarkMatter** (imaginary). Python package `omniwrench`.
- GitHub: `Steffi-Tech/OmniWrench`, **public**. No GitHub org (gh can't create orgs); could move later.
- Data dirs: `%APPDATA%\DarkMatter\OmniWrench` (settings, vault, tool_settings, layout), `%LOCALAPPDATA%\DarkMatter\OmniWrench` (tools, tool_data, logs). Override: `OMNIWRENCH_HOME`.

## Tech
- Python + PySide6 + PySide6-QtAds (docking) — chosen by user over C#/WPF and PowerShell.
- Store = GitHub repo with `store/index.json` (+ zipped tool packages, sha256). Default repos: local dev store (if running from source) + official raw.githubusercontent URL.
- App updates via GitHub Releases (`vX.Y.Z`, asset `OmniWrench-X.Y.Z.zip`).
- TLS via `truststore` (Windows cert store) — corporate TLS inspection on user's machine.

## UI (user requests)
- Tabs on top; Home tab always open (not closable); Store tab openable; each tool opens in own tab; tabs dockable side-by-side/stacked/floating (QtAds).
- Left sidebar: installed tools tree by category. Double-click category → Home with category filter.
- Home: compact tiles (icon + name only). Single click → right details panel (metadata, actions). Double click → open. Right click → menu (Open, Settings, Update, Check, Repair, Folder, Uninstall).
- Tile names: shrink font first (down to 8.5pt), then wrap (spaces/after hyphens) into 2 lines, then elide.
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

## i18n
- Languages: de, en, fr, es + fun: de_bad (Badisch), de_by (Bayrisch), en_sco (Scots), en_posh (Posh English). Files flat JSON with `_meta.fallback`.
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
- Local dev store not shipped with the EXE. No installer yet. Code signing: see "EXE signing" below.

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
- Stef chose (2026-10-16): **SignPath Foundation** + repo licence **MIT** (LICENSE, copyright "Steffi-Tech").
  README has the required "Code signing policy" section (roles: Steffi-Tech = author/reviewer/approver,
  privacy statement). Keep it accurate: new automatic network access must be listed there (SignPath terms).
  Alternatives rejected for now: Certum OSS, company PKI, OV, Azure (EU orgs only).
