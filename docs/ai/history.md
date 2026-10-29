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

## 2026-10-16 — more password connectors (thread "Passwort-Konnektoren", suggestion 5)
- OmniVault 1.1.0: connectors Bitwarden/Vaultwarden (bw CLI; API key or e-mail + master password), 1Password
  (op CLI; service account token or desktop app), HashiCorp Vault/OpenBao (HTTP API, KV v1/v2; token, userpass,
  LDAP, AppRole). All stage alpha. Python implementations in connectors.py (no PowerShell).
- Dialog: missing CLI -> winget install offer (Bitwarden.CLI, AgileBits.1Password.CLI).
- Tests: fake bw/op scripts + local fake Vault server (search, get, wrong credentials -> AuthenticationRequired,
  expired session/token -> re-login); dialog renders for all three types. Store: only omnivault zip rebuilt.
- Same PR, on request: OmniVault locales for fr, es, de_bad, de_by, en_sco, en_posh (all 51 keys) + fr/es for every
  label/description in connector_types.json (dialects fall back to de/en there via text()). Checked fr/es dialog renders.

## 2026-10-16 — real UAC install of prerequisites (thread "Echte UAC-Installation")
- New core/elevation.py: ShellExecuteExW "runas" (owner = main window via MainWindow.showEvent), detects UAC "No"
  (1223), is_admin() skips the prompt when already elevated. Same code path in source and EXE.
- run_ps_elevated rewritten: -EncodedCommand wrapper, user script base64-embedded (syntax errors land in the log),
  log file pre-created by the user, output streamed live (on_output), errors as stderr, full powershell.exe path.
- prerequisites: localized live progress per capability/feature, restart-needed notice, WSUS/FoD hint, clean
  "UAC declined" error. SDK run_powershell_elevated(on_output=). 12 new/changed keys in all 8 locales.
- Tested on Linux with pwsh 7.4 + mocked DISM cmdlets (install, present, restart, 0x800f0954, syntax error, exit code,
  umlauts, >30k script via -File, cancel). Windows API part untested here -> user test.
- Stef tested UAC install on Windows: OK. Follow-up: Windows Server is not a target -> core/system.is_windows_server()
  (registry InstallationType) + notice label on Home (QLabel#Notice, key home.server_notice, 8 locales).

## 2026-10-16 — AI translation review fr/es/dialects (thread "Übersetzungen prüfen", suggestion 7)
- Reviewed all 300 keys of fr, es, de_bad, de_by, en_sco, en_posh against de/en. Only existing keys changed
  (open PRs #7-#10 + connector PR also touch locales). No native-speaker check - stays open in backlog.
- fr: log FILE not folder (app.unexpected_error), "Prérequis manquants", "est absent de" instead of "manque dans",
  full terms (nom d'utilisateur, gestionnaire de mots de passe d'OmniWrench), pick_button wording.
- es: archivo de registro, "Faltan requisitos", copia de seguridad, nombre de usuario, Obtener del gestor.
  Formal "usted" imperatives confirmed consistent (Seleccione, Introduzca, Consulte).
- de_bad: scale keys used a different spelling (ë, nooch, vun, het, selber) -> aligned with rest of file;
  "gönn" -> "gehn". de_by: typo "Ofmeidn", "söiba"/"no amoi" aligned to "sejba"/"nomoi", "Grichtt", "auswürfln".
- en_posh "programme" consistently; en_sco "Copy user name". check_locales OK.
- Follow-up (same thread): merged main (UAC, CI, signing). Reviewed the 12 new UAC/server keys too (fr "p. ex.",
  de_bad/en_sco spelling aligned). Added Hessian `de_hes` (all keys, fallback de). Language dropdowns in app and tool
  settings now indent dialects under the main language (i18n.language_tree, LANGUAGE_INDENT = 2 em spaces).
  Gave Stef a list of further sensible languages (backlog).
- Follow-up 2 (Stef: "Nehmen wir alle sinnvollen und die Dialekte"): added 8 languages (it, nl, pl, pt-BR as `pt`, cs, sv,
  tr, uk) and 6 German dialects (de_swg, de_sxu, de_nds, de_gsw, de_ksh, de_wien), all 312 keys, AI-written.
  system_language() maps Windows names (italian, dutch, …). Language list sorts accent-insensitive (Čeština at C).
  Smoke test: 23 languages OK. Tool locales unchanged (fallback).

## 2026-10-17 — Backlog as GitHub issues, service-oriented categories (thread "Backlog, Board, Kategorien")
- Open backlog items as issues #17–#32, new proposals #33–#38 (labels test/windows/konnektor/alpha/blockiert/
  nur-stef/übersetzung/idee/zurückgestellt/vorschlag/neues-tool/prio-*). No Projects API access from the cloud ->
  Stef creates the GitHub Project board herself (auto-add workflow `is:issue`).
- Categories: tool.json `category` = area/sub IDs (core/categories.py); app translates 11 areas + 42 subs
  (`category.area.*`, `category.sub.*`, all 23 locales; dialects use base-language text). Own sub/area via
  `subcategory`/`category_area` (+ tool locales). Legacy free-text paths mapped via LEGACY_AREAS.
  `tool.category` in tool locales kept as written-out path for 0.6.x apps. Sidebar search includes tags,
  category node tooltip shows full name. Tools bumped: AD 1.3.2, IconForge 1.1.2, OmniVault 1.1.1, Subnet 1.2.2.


## 2026-10-18 — NetProbe network test tool (thread "Netzwerker-Tools: ultimatives Test-Tool")
- First networking tool. Input IP/DNS/CIDR/range -> target list; networks scanned (limit 4096). Battery of tests
  toggleable per category in an options dialog (OptionsDialog: tristate per category, port profile, ping count,
  timeouts, max hosts/sockets/hops, only_alive, OUI download).
- Engine async in a thread, results marshalled to the GUI via Qt signals. Tests "auf Steroiden": ping with
  loss/jitter/TTL/OS guess (IcmpSendEcho on Windows, `ping` on Linux – no raw sockets), parallel traceroute with
  per-hop PTR/ASN/class/ping, port scan explained from a 136-port library (portlib.json, flags + de/en + usage list),
  HTTP/TLS incl. unknown open ports (finds web UIs on odd ports), SMB/RDP/NTP/DNS-server, full DNS for names
  (records, NS serials, SPF/DKIM/DMARC/MTA-STS/TLS-RPT, DNSSEC, wildcard, AD SRV). "Befunde" tab = ~60 best-practice
  findings (findings.py), target list shows ⚠n.
- UI: left target list with live status/progress, right an OWN nested QtAds CDockManager (verified it does not touch
  the main window docking). Click a target -> dockable tab with only the categories that ran; tabs arrangeable side by
  side inside the tool. render.Renderer builds the per-category widgets.
- requirements.python dnspython>=2.6 (pip on install). category network/diagnostics, icon radar, min_app_version 0.6.0.
- Checks green: compileall, check_locales (app 23 + tool de/en 339 keys), check_store, smoke_test. Store: netprobe
  1.0.0 zip + index entry (other tools' zips restored, only net.netprobe entry merged – Linux-zip-hash gotcha).

## 2026-10-19 — NetProbe v2: Feedback-Runde (thread "Netzwerker-Tools: ultimatives Test-Tool")
Stef hat 1.0.0 getestet und eine Liste Verbesserungen gewünscht (net.netprobe 1.1.0):
- Zielliste bleibt dauerhaft: neue Tests werden angehängt statt die Liste zu löschen. Netze/Bereiche erscheinen als
  aufklappbare Gruppe mit Fortschritt „x/y Hosts“. Ein erneuter Test eines schon vorhandenen Ziels aktualisiert den
  Eintrag in place (res_for_addr/item_for_addr nach Adresse, mehrere Engines parallel möglich).
- Kontextmenü + Buttons: Wiederholen, Löschen, Export (PDF), Alle löschen. targets.parse taggt jetzt die Herkunft
  (Target.group = ursprüngliche Netz-/Bereichsangabe) fürs Gruppieren.
- Ping-Fix (Stef sah Paketverlust, CMD nicht): Default-Timeout 1000→2000 ms (ping.exe wartet 4 s – langsame Antworten
  wurden fälschlich als Verlust gezählt) + Aufwärm-Pings (ping_warmup=2, nicht gezählt, gegen ARP/Routing-Erstverlust).
  Timeout/Intervall/Warmup/DNS-Timeout jetzt im Optionsdialog einstellbar.
- Testprofile als Dropdown neben „Starten“: overview/standard/deep/custom (engine.template_options).
- Tabs umgebaut: erster Tab „Steckbrief“ (Identität + Befunde-Ampel oben + offene-Ports-Zeile), Verbindungs-/Qualität
  jetzt eigener Tab „Konnektivität“ (Ping, MTU, Routen-Kurzüberblick). Wichtiges oben, scrollbar.
- Mehr DNS-Best-Practice-Befunde: CAA fehlt, MTA-STS, TLS-RPT (Daten kamen schon aus dnscheck).
- PDF-Export je Ziel/Auswahl über QPdfWriter+QTextDocument (keine Zusatzbibliothek), tools/netprobe/pdfreport.py.
- OFFEN (eigener Folge-Schritt): Leitungstest/Remote-Agent (echte Latenz, Durchsatz, Lasttest, Portscan durch die
  Strecke) via Mini-Tool/Script auf der Gegenstelle oder NetProbe↔NetProbe; Export-Button im Optionsfenster mit
  Ausrufezeichen-Hinweis bei Profilen, die das Mini-Tool brauchen. Außerdem weitere MX-Toolbox-Funktionen (Blacklists).

## 2026-10-19 — NetProbe v1.2: Leitungstest/Remote-Agent (eigener PR nach v1.1)
Stefs gewünschter Folge-PR: echte Leitungsqualität zu einer Gegenstelle messen.
- Neues eigenständiges Mini-Tool `tools/netprobe/linkagent.py` – NUR Standardbibliothek, läuft Windows+Linux
  (Python 3.8+). Enthält Server (`LinkServer`) + Client (`LinkClient`) + CLI (`serve`/`probe`). NetProbe importiert
  denselben Client; das exportierte Skript ist dieselbe Datei. Protokoll: längengerahmtes JSON (MAGIC+Länge) über TCP,
  Token-Pflicht im Hello. Messungen: echte (anwendungsnahe) Latenz per Echo, Durchsatz je Richtung (source/sink),
  Lasttest mit K parallelen Verbindungen (ThreadPoolExecutor), Pfad-Portscan (Server bindet eine Portauswahl, Client
  prüft, was die Strecke durchlässt). Sicherheit: Last entsteht NUR gegen eine Gegenstelle, die das Tool mit demselben
  Token bewusst startet (nicht gegen beliebige Fremdrechner richtbar); Dauer/Parallelität/Portanzahl/Idle begrenzt.
- Engine: Kategorie/Test "link" (default aus), Profil `template.link` ("Leitungstest (Gegenstelle)"), LINK_KEYS werden
  durch alle Profile getragen. `_link_test` läuft blockierend im Executor, Phasen aktualisieren res.step
  (link_latency/download/upload/load/portscan). parse_scan_ports() für die Pfad-Ports.
- Oberfläche: Optionsdialog hat einen eigenen Abschnitt „Leitungstest“ (Port, Token+„Neu“, Dauer, Lasttest-
  Verbindungen, Pfad-Ports, Messungs-Checkboxen) mit **Mini-Tool-Export** (QFileDialog, zeigt den Startbefehl) und
  **„Als Gegenstelle dienen“** (startet/stoppt den eingebauten LinkServer; Lebenszyklus liegt im Tool via _LinkControl,
  damit er den Dialog überlebt). Beim Profil „Leitungstest“ steht ein ❗ neben dem Dropdown mit Hinweis (Mini-Tool drüben
  starten). Ergebnis-Tab „Leitungstest“ (render.link_widget): Gegenstelle, Latenz+Sparkline, Durchsatz-Balken je
  Richtung, Lasttest, Pfad-Portscan; früh einsortiert. Befunde link_ok/link_loss/link_unreachable/link_path_blocked.
  PDF-Report um den Leitungstest-Abschnitt ergänzt.
- +62 Lokalisierungsschlüssel de/en (cat.link, test.link_*, template.link, link.*, fx.link_*). tool.json 1.1.0→1.2.0,
  neue Tags (leitungstest, throughput, lasttest, iperf …), Beschreibungen erweitert.
- Geprüft: compileall, check_locales (App 23), Tool-de⊆en + Platzhalter-Parität, Offscreen-Render (Haupttool, Options-
  Leitungsabschnitt, Ergebnis-Tab), Ende-zu-Ende über die echte Engine gegen einen lokalen LinkServer (Handshake,
  Latenz, Durchsatz, Lasttest 3 Verb., Portscan 32 Ports, Befund link_ok), standalone-CLI serve+probe, PDF, check_store.
- OFFEN bleibt: weitere MX-Toolbox-Funktionen (DNSBL-Blacklists, SMTP-Open-Relay). Windows-Realtest: Server-Bind auf
  0.0.0.0, Firewall-Freigabe, echte Durchsatz-/Latenzwerte über eine reale Strecke.

## 2026-10-20 — Masterpasswort zurücksetzen (verlorenes Passwort)
Stef: Passwort zurücksetzen können, wenn es verloren geht; dabei nur Passwörter löschen (auch Vault-Konnektoren),
alle Einträge bleiben mit ❗ beim Passwort und funktionieren erst nach Neusetzen.
- core/dpapi.py (neu), Vault.recovery + reset() + Verlustliste, Credential.missing, is_missing(), SecretStore.is_lost,
  ToolSettingsStore.is_lost. Login: Link „Passwort vergessen?“ -> ResetDialog (neues Passwort, Bestätigungs-Haken).
- ❗-Markierung: Passwortmanager-Liste, Auswahl, credential-Felder (neuer ✎-Knopf zum Nachtragen), geheime
  Tool-Einstellungen, GitHub-Token, OmniVault-Konnektorliste (OmniVault 1.1.1 -> 1.1.2; nach Merge mit #45/#46 1.1.3).
- 12 neue App-Schlüssel in allen 23 Sprachen. Geprüft: Reset-Ablauf per Skript (Linux, Schema "plain"), Renders,
  smoke_test, check_locales, check_store. DPAPI selbst nur unter Windows prüfbar.

## 2026-10-20 — NetProbe 1.2.1: Mini-Tool als eigenständige .exe (ohne Python)
Stef: das exportierte Leitungstest-Mini-Tool soll auf der Gegenstelle ohne Python startbar sein.
- Neues scripts/build_linkagent.py: baut tools/netprobe/linkagent.py mit PyInstaller als Einzeldatei
  (dist/linkagent.exe bzw. dist/linkagent, nur stdlib, ~8 MB, Windows-Versionsinfo). Auf Linux gebaut und
  getestet (serve+probe laufen ohne Python).
- build_exe.py baut das Mini-Tool mit und legt linkagent.exe in den Programmordner (APP_DIR) neben
  OmniWrench.exe; landet damit automatisch im -win64-Zip und beim Selbst-Update. --sign signiert es mit.
- build-exe.yml: Schritt „Mini-Tool (linkagent) prüfen“ (--help), und beim Tag-Release wird linkagent.exe
  zusätzlich als eigenständiges Asset hochgeladen.
- Export im Optionsdialog jetzt zwei Knöpfe: „Mini-Tool (.exe)“ (kopiert die gebaute Datei, über
  _LinkControl.agent_binary() aus APP_DIR bzw. APP_DIR/dist gefunden; deaktiviert mit Hinweis, wenn aus dem
  Quellcode keine Binärdatei vorliegt) und „Als Skript (.py)“ (wie bisher). Neue Texte link.export_exe/
  export_script/export_exe_missing/export_no_binary/export_done_exe.
- tool.json 1.2.0 → 1.2.1, Store neu gebaut. Geprüft: compileall, check_locales, de⊆en-Parität, Linux-Build +
  serve/probe des Binaries, Offscreen-Render des Export-Bereichs (beide Knöpfe, .exe-Knopf aktiv), check_store.
  Windows-.exe-Build selbst läuft in CI (hier nur Linux-Binary gebaut).

## 2026-10-22 – GitHub-Name Steffi-Tech → KuroShiroMe
Stef hat den GitHub-Namen geändert. Alle Verweise auf `Steffi-Tech/OmniWrench` umgestellt: `omniwrench/__init__.py`
(GITHUB_REPO → Update-Quelle und offizieller Store), build-exe.yml, sign_exe.py, README (inkl. Code-signing-Rollen),
LICENSE (Copyright war der GitHub-Name), CLAUDE.md, decisions.md, EXE_SIGNIEREN.md, claude-project/README.md.
- Neu: `core/settings.py` schreibt in gespeicherten Einstellungen `app_update_repo` und Store-URLs mit dem alten
  Namen beim Laden auf den neuen um (alte Installationen hängen sonst an der GitHub-Weiterleitung).
- Geprüft: grep ohne Rest-Treffer (außer Historie), Migration per Python-Test.

## 2026-10-20 Tool-Updates: Startmeldung, Alle aktualisieren, Auto-Update (Thread „Tool-Updates“)
- Stef: Meldung beim Start bei Tool-Updates (alle aktualisieren oder verschieben), Haken „Dieses Fenster nach Abschluss
  schließen“ in Update-Fenstern (gemerkt), „Alle aktualisieren“ in Store und Optionen, Option für automatische
  Hintergrund-Updates. (Kategorien/Tags und Passwort-Zurücksetzen laufen in eigenen Threads.)
- Gebaut: repository.update_tools, MainWindow._show_tool_update_prompt/update_all_tools/update_tools_in_background,
  TaskDialog auto_close, Store-Button, Optionen › Updates (Auto-Update, Fenster-Haken, „Alle aktualisieren (n)“),
  Settings auto_update_tools/close_update_window, 20 neue Schlüssel in allen 23 Sprachen, README-Datenschutz ergänzt.
- Geprüft (Linux offscreen): Testskript mit Fake-Store (2 Tools hochversioniert): Startmeldung, Alle aktualisieren
  inkl. geöffnetem Tool, Haken gemerkt + Einzel-Update schließt sich selbst, Auto-Update ohne Meldung; smoke_test
  (23 Sprachen), check_locales, check_store. Windows-Test durch Stef offen.

## 2026-10-20 Kategorien nur noch eine Ebene + Tags (Stef)
- Stef: "Kategorien nur noch auf die Hauptkategorien reduzieren, alle Tools kriegen sinnvolle Tags". Weicht von der
  2-Ebenen-Entscheidung vom 2026-10-17 ab -> decisions.md angepasst.
- core/categories.py: AREAS nur noch IDs, SUBCATEGORIES/category.sub.* entfernt (43 Schlüssel x 23 Sprachen),
  category_id() statt category_ids(); "bereich/unterkategorie" und Freitext-Pfade werden auf den Bereich reduziert
  (Rückwärtskompatibel, z. B. ScopeKeeper PR #43). manifest: Feld `subcategory` entfernt (unbekannte Felder werden ignoriert).
- Tags sichtbar: Details auf Home (Zeile "Tags") und Store-Karte ("Tags: …"), Klick sucht danach (widgets.tag_links).
  Neue Schlüssel details.tags, store.tags in allen 23 App-Sprachen.
- Alle 5 Tools: category = Bereich, neu kuratierte Tags (sprachneutral/Englisch), tool.category in Tool-Sprachdateien
  nur noch Bereich, Patch-Version +1 (NetProbe nach Merge mit main 1.2.2), Store neu gebaut (alte ZIPs entfernt).
- TOOL_ENTWICKLUNG.md: Kategorien-Abschnitt auf eine Ebene, neuer Abschnitt "Tags".
- Geprüft: check_locales, check_store, smoke_test (Linux offscreen), Render Home-Details/Suche/Store.
- 2026-10-22 nach Merge mit main (#49): MS DHCP Extended ebenfalls auf Bereich `network` + kuratierte Tags, 1.2.1.

## 2026-10-19 — ScopeKeeper: DHCP-Verwaltung neu gebaut (thread "DHCP Management Tool")
Stef gab DhcpScopeManager.ps1 v2.3.1 (WinForms) und wollte das komplette Konzept neu als OmniWrench-Tool, keine Kopie.
- Neues Tool net.scopekeeper 1.0.0 (Alpha): Anmeldung (SSO/Tresor/manuell, Server-MRU, „Aus AD laden“), Übersicht,
  Scope-Tabs mit Live-Befunden + Korrekturen, Entwurf/Duplikat mit Netzumrechnung, Server-Optionen, Failover-Seite
  (anlegen/ändern/Scopes/Vergleich/Rohdaten/löschen), Definitionen, serverweite Prüfung, Zwischenablage, Replikation
  auf den Partner (netsh, auch ohne WinRM), Protokoll. 947 Texte de/en.
- Mit Fake-Backend durchgespielt (Login, Replikation, Vergleich, Speichern, Entwurf anlegen inkl. Failover, Status,
  Löschen); dabei behoben: Endlosschleife in der Optionstabelle des Entwurfs, Signal-Argumentfehler LeaseEdit,
  tr(key=) Konflikt beim Vergleich, Knopfzeilen umbrachen senkrecht, „&“ im Tab-Titel, leere Fehlerliste beim
  Übertragen. Screenshots in /mnt/project-files/scopekeeper/.
- Checks grün: compileall, pyflakes, check_locales, check_store (nur scopekeeper-zip + Index-Eintrag), smoke_test.
- 2026-10-20 Stef-Test: „Aus AD laden“ und Login scheiterten mit "'list' object has no attribute 'get'". Ursache:
  `items = , $x` in Hashtables von host.ps1 verschachtelte alle Listen. Behoben in 1.0.1, mit echtem pwsh + Stub-Cmdlets
  nachgestellt und geprüft.
- 2026-10-20 Stef-Wunsch (1.1.0): Umbenennung in „MS DHCP Extended Management“; Prüfung parallel (RunspacePool
  cim_many, 8 Threads, zweiter PowerShell-Prozess, UI bleibt bedienbar, abbrechbar, Scope-Ergebnisse laufen live ein);
  Opt-out „Server direkt nach der Anmeldung prüfen“; Ladeansicht beim Anmelden (bei Fehler zurück); Verbindungsaufbau
  als Schritte statt Fehlermeldung; Hinweistexte -> ?-Icons. Mit Fake-Backend + pwsh-Stubs getestet (10 Abfragen à
  300 ms in 0,7 s).
- 2026-10-20 Stef: interne Kennung auch ändern (neues Tool net.ms-dhcp-extended, Ordner ms_dhcp_extended) und
  „möglichst alles in Python“. DHCP-Zugriff komplett neu über dhcpsapi.dll (ctypes, backend.py/dhcpapi.py),
  PowerShell-Host (host.ps1/pshost.py) entfernt, netsh direkt aus Python. Strukturen gegen Win32-Metadaten geprüft,
  Abläufe mit Fake-DLL unter Linux getestet. Inventar der übrigen PowerShell-Nutzung in backlog.md.

- 2026-10-22 Stef tested 1.0.0 and asked for 6 changes -> 1.1.0: movable overview columns (new default order), failover
  view with one row per server + all scopes of the selected server (split detection), check page with distribution
  bars/top scopes and segmented switch, server options per failover server with sync state + per-option transfer +
  opt-out partner checkbox, definitions behind expert mode + unlock, rights detection (read-only hides edits).
  Fixed on the way: QMessageBox checkbox segfault, FlowLayout wrapping with hidden buttons. Fake-DLL/fake-backend tests.
- 2026-10-22 Stef (after 1.1.0 merge) -> 1.2.0: check column "Höchster Befund" (was "Bewertung"), failover list as
  expandable relationship rows (▸/▾, double-click, arrow keys) with both servers below, server options show only the
  selected server's own options (missing ones stay as findings; "Anzeigen" jumps to the server that has it), Alpha
  tag/note removed at Stef's request. Fixed: findings list row heights computed while page hidden (giant rows).

## 2026-10-22 Aufräumen + Testliste (Stef: "alle Threads abschließen, Repo aufräumen, Testliste für main")
- Merged in order after #49 (DHCP 1.2.0): #45 -> #46 -> #47 -> #48, each with main merged in (conflicts only in docs/ai/*,
  store/index.json): kept both sides in docs; store conflicts solved by rebuilding only the affected tool.
  MS DHCP Extended -> category `network` + curated tags, 1.2.1 (on #45). OmniVault 1.1.2 was bumped by #45 and #47
  independently -> 1.1.3 (on #47). Other tools' ZIPs restored from the branch (build_store ZIPs are not byte-stable).
- New docs/TESTLISTE.md: all open Windows tests (threads, issues #17-#23, backlog) grouped by tool; backlog points to it.
- Branch deletion is blocked from the cloud session (git push --delete denied, no MCP tool) -> left to Stef.

## 2026-10-22 Installationsprogramme + Linux, Release 0.7.0 (thread "Installer und portable Version")
- Stef: full installer + portable version for Windows AND Linux in the release, program files in the program folder,
  config/vaults in the user profile; merge everything and release. decisions.md platform rule changed visibly.
- Installers: Inno Setup (installer/windows/OmniWrench.iss) + .deb (scripts/build_installer.py). Marker
  omniwrench-install.json -> paths.INSTALL_KIND. Linux paths = XDG + migration from ~/AppData; Windows paths unchanged.
- Updater: per install kind (setup via UAC, deb via pkexec, portable replaces files; read-only portable folder on
  Windows -> elevated copy + non-elevated restart). PowerShell now via -EncodedCommand (GPO AllSigned safe).
  App creates mutex DarkMatter.OmniWrench (setup waits for it, max 60 s silent).
- Linux support: platforms check generic (core/system.py), store marks Windows-only tools, cert login hidden,
  DPAPI replacement "userkey". Tools 4x patch bump with platforms windows+linux (subnet 1.2.4, IconForge 1.1.4,
  NetProbe 1.2.3, OmniVault 1.1.4; OmniVault hides SecretManagement/Netwrix connectors off Windows).
- CI: build.yml (was build-exe.yml) with windows/linux/release jobs incl. real install/uninstall tests; ci.yml got a
  Linux smoke test. README: install guide, data locations, honest "unsigned" section (SignPath claim removed).
- Tested locally (Linux container): PyInstaller build, .deb install/start/apt remove, XDG migration, portable tar.gz
  self-update incl. restart, deb update script (fake pkexec), smoke test. Windows parts only via CI.
- Version 0.7.0, release notes .github/release-notes/v0.7.0.md. Tag v0.7.0 must be pushed by Stef.

## 2026-10-22 Hersteller KuroShiro + neues README (thread "KuroShiro und neues README")
- Stef: vendor "DarkMatter" -> "KuroShiro" everywhere (GitHub user had to be KuroShiroMe; domain kuroshiro.me points
  to the repo for now, landing page in a parallel thread). Wiki + tool template in thread "Wiki und Tool-Vorlage".
- VENDOR/APP_MUTEX -> KuroShiro, LEGACY_VENDORS=("DarkMatter",). core/paths.py moves old data dirs at import
  (os.rename, shutil.move only across file systems; on failure the old dir stays in use). Settings rename stored
  "DarkMatter Store" -> "KuroShiro Store". DPAPI entropy deliberately unchanged.
- Setup: publisher KuroShiro, default dir {autopf}\KuroShiro\OmniWrench; installs in the old default dir are moved
  (InitializeWizard swaps DirEdit, ssPostInstall DelTree old dir); mutex check covers old + new name. CI install test
  path updated. Upgrade path itself untested (Windows) -> TESTLISTE.
- All 6 tools patch-bumped: author KuroShiro + "homepage" = wiki page (Tool-<Name>). LICENSE holder KuroShiro.
- README rewritten for end users: description of the main program with screenshots (.github/readme/*.png, rendered
  offscreen on Linux with a patched ToolManager so Windows tools install), installation, data locations, wiki link.
  Dev sections (start from source, structure, publishing, signing) removed -> wiki/CLAUDE.md/docs.

## 2026-10-22 Landing Page kuroshiro.me
- Stef: brand renamed DarkMatter -> KuroShiro (separate thread), domain kuroshiro.me should get a landing page.
- Built static page in `site/` (index.html, style.css, script.js, img/): hero + 6 feature cards, store tool list,
  2 screenshots, download cards (Windows setup/zip, Linux deb/tar.gz). script.js swaps links to latest release via
  GitHub API, falls back to hard-coded v0.7.0 links. Screenshots rendered from the real app (offscreen, de, dark).
- Deploy: `.github/workflows/pages.yml` (Actions Pages, on push to main touching site/). Domain set in repo settings.
- PR #52 merged, Stef set Strato DNS (only ONE A record possible: 185.199.108.153) + custom domain; site live.
- Follow-up: tool list as collapsible categories with wiki links, generated by scripts/build_site.py; landing-page
  rule added to CLAUDE.md.

## 2026-10-22 GitHub Wiki + tool template repo
- Stef wants GitHub Wiki for everything, standardized pages + template, developer area, "template function" for
  own repositories, docs/ only internal with README pointing to the wiki.
- Wrote `wiki/` (33 pages + images): Home, Installation, Erste-Schritte, Bedienung, Store-und-Tools, Einstellungen,
  Tresor-und-Anmeldung, Passwortmanager, Sprachen, Datenablage-und-Datenschutz, Fehlerbehebung, Tools + 6 tool pages,
  2 templates, 11 Entwicklung-* pages, _Sidebar, _Footer. Screenshots in wiki/images (rendered from the KuroShiro
  branch; DHCP images partly reused from project files, old WinRM header cropped away).
- `templates/tool-repo/` (template repo content, tested locally: setup, build, check, version guard, new_tool).
- `.github/workflows/wiki.yml`, `docs/README.md`, help menu entries (menu.wiki in all 23 locales), build_exe no
  longer copies docs/TOOL_ENTWICKLUNG.md.

## 2026-10-23 DHCP: pool of failover scopes (0x4EA4) + partner comparison (net.ms-dhcp-extended 1.3.0)
- Stef: changing the range of a failover scope failed with 0x4EA4. Cause: `set_range` removed the range element and
  re-added it; Windows forbids deleting the range of a failover scope (ERROR_DHCP_FO_RANGE_PART_OF_REL 20132).
  The old generic 0x4E90-0x4EAF -> "Failover-Konflikt" text hid this. Also: the save flow had already removed all
  exclusions before the failing call (lost on the server).
- Fix: `DhcpAddSubnetElementV5` modifies an existing range in place (MS-DHCPM 3.2.4.38: new range must contain or lie
  inside the old one); shifted pools go via the union in two steps, rollback to the old range. netsh `sync_plan` does
  the same for the partner and deletes stale exclusions before the range change. Own texts for 20023, 20112-20116,
  20127, 20129, 20131, 20132; unknown failover codes show the system text.
- Stef (same thread): back to the classic DHCP console model - one pool (start/end) + exclusions; the range list
  that turned gaps into exclusions is removed (`PoolEditor` replaces `RangeEditor`, draft duplicates pool + exclusions).
- Stef: new checks for all differences between the servers. Scan with "Mit Partnern abgleichen" now compares per
  failover scope (missing, mask, name, desc, state, pool, lease, exclusions both ways, options all classes,
  reservations), per relationship (missing, mode, LB sum, reserve, MCLT, auth, scope lists) and server classes +
  definition types. Category `partner`; scope findings also in the scope tab (fix "replicate", from
  `svc.partner_diffs`, set by `set_scan`, cleared on successful replication).
- Tested: fake DLL (S1 = failover scope, rejects range removal with 20132, enforces containment), pure checker tests,
  offscreen renders of scope tab and draft. Windows tests in TESTLISTE section 5.
- Stef: "Warte was? Gelöscht?!" - audit of all delete paths (pool save removed exclusions, reservation change via
  remove+add, paste overwrite, scope delete incl. failover/partner, fo remove/delete/role swap, replication deletes on
  the partner, server option removal on partners, partial draft creation). Built the transaction journal (see
  architecture "Transactions"): all UI write flows wrapped, manual rollbacks in failover code replaced, paste/draft/
  partner copies now raise instead of collecting errors. Tested with test_tx.py (rollback, nested, partial, UI flow,
  cancel) + test_api.py. Windows tests added to TESTLISTE 5 ("Automatische Rücknahme").
- PR #56 merged on Stef's request (Stef now has a DHCP test environment).
- Stef: detect changes by others / auto-refresh / who changed it. Built 1.4.0: conflict check before writes,
  auto-refresh (quiet background jobs, banner in scope tab), event log reader (wevtapi via ctypes) for "who".
  Tested on Linux only: test_conflict.py, test_tx.py, offscreen renders of banner + guard + poll_flow stub.
- PR #57 merged. Stef: own tab for the event log with reading aids, version 1.4.1, message with wiki link if the
  right is missing, wiki setup guide; merge directly. Built page_events.py + classify + wiki section
  "Ereignisprotokoll einrichten" (Event Log Readers S-1-5-32-573, firewall RemoteEventLogSvc*, wevtutil, test).
- PR #58 merged, Stef tested 1.4.1 OK. Stef: load the event log in its own thread so the GUI does not block,
  as 1.4.2, merge, then close the thread. Built EventsPage.load() via run_async (not the Runner).

- 2026-10-23 Stef (via DNS thread): make the DHCP tool fully IPv6/DHCPv6-capable with the same scope as IPv4
  (scopes, options, reservations, leases, check, transactions, conflict detection, event log). Built 1.5.0:
  dhcpapi V6 layer, service v6 methods with undo, checks6, page_scope6 (ScopeTab6), IPv4/IPv6 switch, v6 server
  options/definitions, v6 scope dialog (new/duplicate). Agreed with the DNS thread: optional "DNS-Abgleich" in the
  check (dnscheck.py, socket resolver only, no dependency on the DNS tool). Tested on Linux: test_api6.py (fake
  fake_dhcpsapi6.c, 36 checks), test_api/test_tx/test_conflict unchanged, offscreen UI flows + screenshots.
## 2026-10-23 MS DNS Extended Management (net.ms-dns-extended 1.0.0)
- Stef: "Equivalent zum DHCP-Tool für DNS?" -> concept doc (Claude Doc). Decisions: name OK, editing from the start (no
  read-only phase), every kind of MS DNS (DCs + standalone/non-domain servers), IPv6 right away, both tools fully
  independent but cooperate where useful, pywin32 OK, separate thread makes the DHCP tool IPv6-capable.
- Built tools/ms_dns_extended: WMI root\MicrosoftDNS via pywin32 (DCOM, per-thread connection), records A/AAAA/CNAME/
  PTR/MX/TXT/SRV/NS with PTR sync (in-addr.arpa + ip6.arpa nibbles), zones (create incl. IPv6 reverse, settings,
  transfers, actions, delete), server settings, scavenging preview with ICMP ping, checks + NS/forwarder probes
  (dnspython), multi-server compare (SOA serials), search, read-only DHCP lease comparison (own dhcpread.py),
  audit event log page, conflict check via SOA serial, auto-refresh, transactions with rollback.
- The DHCP-IPv6 thread added the reverse direction (DNS check in the DHCP tool, PR #60) without importing the DNS tool.
- Tested on Linux only: scripts/dns_check/test_logic.py (88 checks, fake backend), offscreen renders, UI flows
  (create with PTR, edit, rollback, conflict, delete with PTR). Windows tests: TESTLISTE section 9.
- 2026-10-27: PR #61 merged on Stef's request. Stef's test environment (EXE): DNS tool install failed with WinError 32
  on the pip log file -> sdk.pip_install leaked the mkstemp handle; now closed + unlink best-effort. Affects every
  pip install from the EXE build (app fix, ships with the next app release).

## 2026-10-27 Store/Home lean cards + screenshots + Home view modes (app 0.8.0)
- Stef: Store much leaner (icon, title, screenshot, short description, one button), click through screenshots,
  single click -> right panel with all metadata + install/update, same for Home; Home gets views list/small/large/full.
- Built ui/tool_views.py (shared card + DetailsPanel), ui/screenshots.py (carousel, cache, viewer), rewrote
  home_page.py (4 views) and store_page.py; theme styles; 14 new app locale keys in all 23 locales.
- Screenshots: tool.json field, scripts/render_screenshots.py, render.py + PNGs for all 7 tools (English, dark);
  build_store/check_store/repository support; tool versions bumped (ad 1.3.5, iconforge 1.1.6, dhcp 1.5.1,
  netprobe 1.2.5, omnivault 1.1.6, subnet 1.2.6, dns 1.0.1) because locales/tool.json changed.
- Narrow windows: card area min 320/360 px, Store hides the category tree while details are open (<~1000 px).
- Wiki (Bedienung, Store-und-Tools, Paketformat#screenshots, Vorlagen-Repository, Schnellstart, Testen), README
  images, landing page images/texts, release notes v0.8.0, tool template (store.py, screenshots.py, example shot).
- Tested on Linux: smoke_test, check_locales, check_store, offscreen renders 1600x1000 dark + 1100x720 light,
  template flow (new_tool -> screenshots.py -> store.py build/check).
- 2026-10-27: After #62 Stef's EXE install of the DNS tool failed with "Unable to locate finder for
  'pip._vendor.distlib'" (nt-only distlib path). Reproduced with a frozen test build on Linux, fixed in main._run_pip
  (register distlib ResourceFinder), Windows Build CI installs dnspython + pywin32 via the EXE. App 0.8.1 prepared
  (v0.8.0 already tagged): version, release notes, site download links.
- 2026-10-27: Stef (first real test against a DC): login failed "Lesen … fehlgeschlagen: Unbekannter Fehler
  (0x80004005)". Cause: wmidns._query used list() on a forward-only SWbemObjectSet (len() -> Count -> E_FAIL).
  Fixed in DNS tool 1.0.2 + regression test (test_logic, 90 checks).
- 2026-10-27: Stef: login OK with 1.0.2, but creating a record failed "Allgemeiner Fehler (0x80041001)". DNS tool 1.0.3:
  PropertyData path + fallbacks (wmidns.create_record), test_logic 95 checks. Real cause still to be confirmed on the DC.
- 2026-10-27: Stef: error popup needs a "Detailansicht" with all attempts and exact messages. HostError/UserError/TxError
  carry `details` (call, HRESULT, excepinfo, scode, SWbemLastError props, create attempts; no passwords), Runner.failed
  is Signal(str, str), ui_base.error shows a "Detailansicht" button -> text dialog with "Alles kopieren". Part of 1.0.3.
- 2026-10-27: Stef: zone tab buttons only visible after scrolling down. Cause: "Allgemein" page (min height ~800 px)
  set the zone tab's minimum height inside the dock scroll area. Wrapped it in a QScrollArea, DNS tool 1.0.4.
  Also answered: replication is done by Windows (AD replication for AD-integrated zones, zone transfer otherwise).
- 2026-10-27: Stef: replication indicator + manual trigger ("beides"), cover missing right; asked about standalone DNS
  (answered: file zones, zone transfer). DNS tool 1.1.0: column "Repliziert", status line per peer, re-check after own
  writes (log), "Replikation anstoßen" (AD: DsReplicaSyncAll push of the zone's partition + UpdateFromDS on peers;
  file: ForceRefresh on secondaries), denied right -> warning with Detailansicht. Fake backend: ad_sync/zone_dn/
  refresh copy; tests 134 checks. Wiki section "Replikation zwischen Servern", TESTLISTE 9a.
- 2026-10-27: Stef's DC test of 1.1.0: record creation works; "Replikation anstoßen" failed with 0x80041002 reading
  GetDistinguishedName out param "Name". 1.1.1 reads ReturnValue (or any DN-like out property) and falls back to the
  default partition guessed from the domain (DomainDnsZones / ForestDnsZones for _msdcs.*).
- 2026-10-27: Stef: error popup on closing the DNS tool (QPushButton already deleted). Cause: replication re-check timer
  fired after shutdown and touched the deleted zone tab. 1.1.2: `_closed` flag (repl_check/tick/poll/ping/log/
  progress/busy) and timers bound to self.root; reproduced offscreen with shiboken6.delete(root) before/after.
- 2026-10-28: Stef (via KI feasibility doc, answer A3): favourites list in the DHCP and DNS tool for servers and
  connection settings, later also AI settings per server. Built server favourites (DHCP 1.6.0, DNS 1.2.0): shared
  favorites.py copy, login row "Favorit", save/overwrite/manage, no passwords (credential reference only), DHCP keeps
  IPv4/IPv6 view, DNS further servers + DHCP server for the comparison. "ai" section agreed with the KI thread.
  Tests: scripts/fav_check (39 checks), dns_check/test_logic, smoke_test, check_locales, check_store. Wiki sections
  "Favoriten" + new login images, TESTLISTE 11. Landing page checked: tool list is generated, nothing else to add.
- 2026-10-28: KI-Integration planned with Stef (feasibility doc, mockups, provider research, question tables A1-A15,
  B1-B12, answers in decisions.md). Stef: implement all stages automatically, she tests the end product.
  Etappe 1 (branch claude/project-thread-ie207t): omniwrench/ai/ (providers catalog 63 entries, connections + vault
  secrets, browser sign-in ChatGPT/OpenRouter/Entra/custom OAuth, adapters OpenAI Chat/Responses/Anthropic/Graph
  Copilot, chat loop with function calls, local storage 3 modes + AES-GCM encryption), settings tabs KI-Assistenten /
  KI-Datenablage, dockable chat panel with bot switch, detail level, projects, history. Tested against a local fake
  server (all 3 protocols incl. tool calls), smoke test extended.
- 2026-10-28: Etappe 2: wiki knowledge (FTS5), app functions, KI-Zugriff page for app + every tool (inheritance, exceptions), pseudonymization (on for everything), confirmation dialog with remember; scripts/test_ai.py in CI.
- 2026-10-28: Etappe 3: tool SDK for AI (ToolContext.ai_function/ai_set_access/ask_assistant/add_ask_action), "Assistent
  fragen …" dialog + mode setting, AI functions in DHCP 1.7.0, DNS 1.3.0, NetProbe 1.3.0, IconForge 1.2.0, AD lookup
  1.4.0, AI level/pseudonymization per server favourite on the DHCP/DNS login page, context menus in tool tables.
  Tests: scripts/ai_check/test_tool_ai.py (47 checks), fav_check adjusted, smoke test asks via context dialog.

- 2026-10-28: Etappe 4: new tool "Clank – KI-Studio" (ai.clank 1.0.0): chat with projects/threads, workspace explorer
  for local folders + GitHub/GitLab/Azure DevOps repos (browse via API, clone with token header), file viewer with
  highlighting, AI functions for list/read/search/git/write/run command (diff resp. command + explanation in the
  confirmation). App version 0.9.0 (min_app of Clank). R&C name list docs/ai/rc-names.md. Test test_studio.py (36).
- 2026-10-28: Etappe 5: Clank tabs "Bilder" (ai/media.py with 9 image API kinds, gallery, reference images, to chat)
  and "Gruppenchat" (2-6 assistants, modes, brakes, interjections, summary, saved encrypted). Provider check: Gemini
  image models now gemini-nano-banana-2.1 (GA 2026-10-06, replaces deprecated gemini-3.1-flash-image), OpenAI
  gpt-image-1-mini/1.5/chatgpt-image-latest shut down 2026-12-01 (not in catalog). Test test_media_group.py (68).
- 2026-10-28: Etappe 6: Clank tabs "Musik" and "Video" (7 music + 8 video API kinds, playback, ffmpeg edits: trim,
  MP3, GIF, add music, mute, still; ffmpeg download for Windows, greyed tabs without ffmpeg). Provider check: Veo 3.1
  preview shut down 2026-10-22 -> Gemini Omni Flash (gemini-omni-1.1-flash, Interactions API); xAI grok-imagine-video
  1.5 + 1.5-lite; Lyria 3.5 GA. Test test_music_video.py (71 checks).
- 2026-10-28: Etappe 7a: Clank templates (8 built-in, own with {{placeholders}}), tab "Dokumente" (write/revise with
  AI, export HTML/PDF/ODT, new storage type documents), screenshot (region/full screen to chat), tab "Planung"
  (scheduled prompts while Clank is open). Test test_extras.py (40 checks).
- 2026-10-28: Etappe 7b: MCP. Spec check: current MCP revision is 2026-07-28 (stateless, server/discover, per-request
  _meta, new HTTP headers) -> client speaks it plus legacy initialize; Clank tab "MCP" (connect stdio/HTTP servers,
  tools for assistants) and OmniWrench as MCP server (localhost HTTP + token, stdio bridge `--mcp-stdio`). Test
  test_mcp.py (72 checks).
- 2026-10-29: Etappe 7c: Clank tabs "Mitschrift" (live transcription of mic + system audio, consent dialog, speaker
  recognition with named encrypted profiles, summary) and "Sprachassistent" (wake word "Hey <name>" offline via
  Vosk, push-to-talk, answers read aloud). Provider check: OpenAI gpt-transcribe/gpt-live-transcribe new,
  whisper-1/gpt-4o(-mini)-transcribe(-diarize) shut down 2027-02-26, TTS tts-1/gpt-4o-mini-tts snapshots
  2027-01-06 (successor realtime only); ElevenLabs eleven_v4/_turbo new, scribe_v1 deprecated; AssemblyAI
  speech_models universal-3-pro/universal-2 (speech_model, best, nano deprecated); Deepgram diarize_model v2.
  EXE build now bundles QtMultimedia/QtMultimediaWidgets/QtTextToSpeech (were missing for Clank media tabs).
  Test test_speech.py (69 checks).
- 2026-10-29: KI-Integration final stage: 273 ai.* app keys translated into the 21 other locales (real languages by
  hand, dialects via word maps, pt = pt-BR), Clank screenshots (screenshots/render.py with MainWindow + fake
  OpenAI-compatible server: chat, images, group, mcp), Clank description incl. MCP/transcript/voice, voice log
  without Markdown, code hint translatable (va.code). UI wording "Optionen" -> "Einstellungen" in de/en (menu is
  Extras > Einstellungen). Wiki: KI-Assistenten, KI-Zugriff-und-Verfremdung, Tool-Clank-KI-Studio (new), AI sections
  + version rows in DHCP 1.7.0/DNS 1.3.0/NetProbe 1.3.0/IconForge 1.2.0/AD 1.4.0 pages, Einstellungen (3 AI tabs),
  Datenablage, SDK page (ai_function & co.), Home/Sidebar/Tools. Landing page: 3 AI feature cards + Clank image.
  TESTLISTE section 12. Provider check: no new changes since Etappe 7c (same day).
- 2026-10-29: Stef not happy with the dropdown: wants a collapsible list left of the login with folders, favourite
  button at the address field, manual creation, and a password per favourite (several customers, different
  passwords, no separate selection). Rebuilt: FavoritesPanel (folders, search, DnD, context menu, collapse), star at
  the server field, FavoriteDialog with login mode "stored" (password encrypted in the vault via context.secrets).
  Also fixed: DHCP _mode_changed had lost user/password enabling in the first favourites commit. Tests 59 checks.
- 2026-10-29: Stef pulled the branch but still saw the old favourites: the tools run from the installed copy, and the
  rework kept version 1.6.0/1.2.0, so the dev store offered no update. Bumped to DHCP 1.6.1 / DNS 1.2.1. Lesson in gotchas.
- 2026-10-29: Merged reworked server favourites (#70: FavoritesPanel with folders, password per favourite) into the KI
  branch; AIAccessRow re-added to favorites.py, overwrite() keeps "ai". DHCP 1.7.1 / DNS 1.3.1 (above #70's 1.6.1/1.2.1,
  unreleased 1.7.0/1.3.0 zips removed). Linux: QT_AUDIO_BACKEND=pulseaudio when no PipeWire daemon (CI segfault).
- 2026-10-29: Clank 1.0.1: ProfileNotice (Art. 9 DSGVO, responsibility with the user) before recording with speaker
  profiles; hidden "always" option after 10 opt-in toggles in 6 s (Stef). test_speech 78 checks.
- 2026-10-29: Stef's ChatGPT sign-in failed (invalid_authorize_request, ext_agent_host_id): host id now urn:uuid:<uuid>
  (old values migrated), callback port 1455 preferred, registration without issued client_id rejected, id_token_hint
  on re-auth. test_ai covers the flow against a fake token endpoint.
- 2026-10-29: "Voraussetzung" row in the add-assistant dialog (Provider.requirement(auth), catalog field "requires",
  defaults by auth/category; ai.req.* in 23 locales). Sign in with ChatGPT needs Plus/Pro (OpenAI SIWC quickstart;
  Go not listed). Wiki KI-Assistenten: requirement table + free tiers note.
