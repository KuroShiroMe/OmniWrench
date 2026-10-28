# Architecture (where is what)

```
main.py                       -> omniwrench.app.main()
omniwrench/__init__.py        APP_NAME, VENDOR, __version__, GITHUB_REPO, OFFICIAL_STORE_URL
omniwrench/app.py             logging, language+Qt translator, theme, LoginDialog, credentials.init, MainWindow loop
                              (restartRequested -> rebuild window without re-login; setQuitOnLastWindowClosed(False))
omniwrench/sdk.py             PUBLIC API for tools: ToolBase, ToolContext, InstallContext, run_async, LANGUAGE_KEY,
                              pick_credential, CredentialField, PSResult, ps_quote
omniwrench/core/              (Qt-free except tool_manager QObject)
  paths.py                    dirs (Windows APPDATA/LOCALAPPDATA, Linux XDG; OMNIWRENCH_HOME or APP_DIR/portable-data
                              override), RESOURCES_DIR, APP_DIR, INSTALL_KIND (setup|deb|portable|source from
                              omniwrench-install.json next to the program), migrate_legacy_data (Linux ~/AppData ->
                              XDG), app_dir_writable
  vault.py                    Vault: create/unlock (password|cert)/lock, get/set keys "app:*", "tool:<id>:<key>";
                              reset(new_pw) from DPAPI recovery copy, is_lost()/lost_keys() ("app:lost_secrets")
  dpapi.py                    protect/unprotect via CryptProtectData (CurrentUser); off Windows "userkey" = AES-GCM with
                              LOCAL_DIR/recovery.key (0600); legacy "plain" still readable
  certificates.py             cert list/encrypt (Python) / decrypt (PowerShell .NET, smart card ok)
  powershell.py               run_ps (EncodedCommand, UTF-8, CLIXML cleanup), run_ps_elevated (UAC via elevation.py, live log tail, on_output;
                              wrapper: script base64-embedded, lines appended to log, errors prefixed ##ERROR)
  system.py                   PLATFORM ("windows"|"linux"|"macos"), supports_platform(platforms), platform_name,
                              is_windows_server() (registry InstallationType, cached)
  elevation.py                ShellExecuteExW runas (owner hwnd = main window, ERROR_CANCELLED 1223), is_admin/needs_uac
  categories.py               AREAS (ids, one level), LEGACY_AREAS, category_id(), category_path(manifest) -> [area] localized
  manifest.py                 ToolManifest (id,name,version,category,tags,icon,icon_text,icon_data,entry,requirements,
                              translations…), SettingDef, validate_package, localized()/display_name/category_path
  tool_settings.py            ToolSettingsStore: JSON for normal, vault for secret/credential types; listeners
  tool_manager.py             ToolManager(QObject): refresh, create_instance, install_zip/dir (backup+rollback),
                              _install_prerequisites (check() first), uninstall, repair; module prefix omniwrench_tool_<id>
  prerequisites.py            pip (_lib), elevated capabilities/features (##OW markers -> localized progress,
                              restart notice, WSUS/FoD hint on 0x800f0954 etc.), PS modules, winget
  repository.py               load_catalog(repos), available_updates, install_from_catalog, update_tools (batch,
                              continues on errors -> (updated, failed))
  app_updater.py              GitHub releases check/download/apply; asset by INSTALL_KIND (asset_suffix): setup ->
                              -win64-setup.exe run silently via UAC (/restart=1), deb -> sh + pkexec apt-get,
                              portable/source -> replace files after exit (PS -EncodedCommand on Windows, elevated
                              copy + non-elevated restarter if APP_DIR read-only; sh + tar/zipfile on Linux)
  net.py                      urllib + truststore SSL, github_token header
  i18n.py                     tr(), set_language, fallback_chain, tool_translator, resolve_tool_language,
                              language_tree (dialects indented under base language in dropdowns)
  icons.py                    Lucide library (names, svg), resolve(icon, icon_text, name, dir, data) -> IconSpec
  credentials.py              Credential, AuthField, AuthenticationRequired, CredentialProvider (search/get_secret/
                              auth_fields/set_auth/close), LocalProvider (vault "app:credentials"), CredentialManager
                              (register/unregister[_owner], search -> SearchResult(items, errors, auth_needed),
                              resolve(ref) w/ auth_handler retry + session cache, clear_session), normalize_value,
                              resolve_item, generate_password; init()/manager()
  settings.py                 AppSettings (DEFAULTS incl. repositories, language, theme, auto_lock_minutes,
                              auto_update_tools, close_update_window)
omniwrench/ui/
  main_window.py              QtAds dock manager; home/store docks; open_tool/close_tool/reload_tool_tabs;
                              tool menu; install/uninstall/check/repair; updates (startup dialog
                              _show_tool_update_prompt, update_all_tools, update_tools_in_background with
                              updating_in_background guard); lock; layout save/restore
  tool_views.py               shared by Home+Store: ToolItem (for_home/for_store, screenshots() local files else
                              catalog URLs), primary_action, Selectable mixin, ToolCard, DetailsPanel, side_width
  screenshots.py              ShotRef, async cached loader (CACHE_DIR/screenshots/<sha>.img), ScreenshotCarousel
                              (heightForWidth 16:10, arrows + dots), ScreenshotViewer dialog
  home_page.py                VIEWS full/large/small/list (setting home_view): ToolCard / ToolTile (FitLabel) /
                              SmallTile / ToolList(QTreeWidget); HomePage (filter, select_tool, splitter+details)
  store_page.py               StorePage: splitter [category tree | ToolCard grid (ColumnFlowLayout 280) |
                              DetailsPanel]; tree hidden while details open in narrow windows (_fit_tree)
  sidebar.py                  tree; CATEGORY_ROLE; double-click category -> host.show_home(category_filter=…)
  settings_dialogs.py         _Field/build_settings_form (schema -> widgets, translated via tool locale),
                              ToolSettingsDialog (+language combo), AppSettingsDialog (tabs incl. password manager)
  credentials.py              PasswordEdit, CredentialEditDialog, PasswordManagerWidget/Dialog, ProviderLoginDialog,
                              install_auth_handler, CredentialPickerDialog (async multi-provider), pick_credential,
                              CredentialField (multi-entry dropdown, settings binding, resolve(),
                              resolve_async()), resolve_async(item|ref, on_done) - background fetch
  login_dialog.py             setup/unlock, CertificateCombo
  icon_browser.py             Extras › icon library dialog (simple)
  widgets.py                  tool_icon (file/data/library/text), library_icon, FitLabel, FlowLayout, TaskDialog,
                              ResponsiveRow (wraps right part below), ColumnFlowLayout (n columns by width), breakable;
                              TaskDialog(auto_close=(settings, key)) = remembered "close when done" checkbox
  scaling.py                  ui_scale -> QT_SCALE_FACTOR (before QApplication), device_pixel_ratio, fit_to_screen,
                              fit_min_width, window_size, restart_application
  theme.py                    palettes + stylesheet; ads_stylesheet() must be set on CDockManager directly
  workers.py                  run_async (QThreadPool, signals), call_in_gui (BlockingQueuedConnection invoker)
omniwrench/locales/*.json     8 languages, ~280 keys
omniwrench/resources/icons/lucide/  SVGs + LICENSE + VERSION
tools/<tool>/                 subnet_calculator (net.subnet-calculator), ad_user_lookup (ms.ad-user-lookup),
                              omnivault (sec.omnivault), iconforge (gfx.iconforge), netprobe (net.netprobe), ms_dhcp_extended (net.ms-dhcp-extended) - see below
store/                        index.json + packages/*.zip (generated, committed)
scripts/                      build_store, build_release, build_exe (PyInstaller onedir), check_locales, check_store,
                              smoke_test, update_icons, sign_exe (Authenticode via signtool/osslsigncode, cert from env),
                              build_installer (Windows: ISCC -> -win64-setup.exe; Linux: dpkg-deb -> omniwrench_X_amd64.deb)
.github/workflows/ci.yml      every PR + push main: compileall, check_locales (app + each tool), check_store (Linux);
                              smoke_test.py on windows-latest and ubuntu-latest (offscreen; tools filtered by platforms)
.github/workflows/build.yml  every PR + push main + tags v*. Job windows: PyInstaller, `--pip --version`, EXE start
                              test, optional signing (vars.SIGN_METHOD), ZIP, Inno Setup (choco if missing),
                              silent install to Program Files + start + uninstall test. Job linux (ubuntu-22.04):
                              build, tar.gz, start test, .deb, apt install + start + remove test. Job release (tags):
                              downloads artifacts, build_release.py, gh release create (source zip first) + upload.
installer/windows/OmniWrench.iss  Inno Setup script (AppId fixed!, mutex wait via CheckForMutexes, [Run] restart
                              check {param:restart}), compiled only via scripts/build_installer.py (/D defines)
installer/linux/omniwrench.desktop  menu entry for the .deb
docs/TOOL_ENTWICKLUNG.md      German developer guide for tool authors (keep in sync!)
```

## Key mechanisms
- EXE build: PyInstaller onedir; data in _internal/omniwrench/{resources,locales} (found via __file__), APP_DIR = exe
  folder (docs/ copied there). Whole stdlib + omniwrench + extra Qt modules bundled for runtime-loaded tools.
  Frozen pip: main.py handles `OmniWrench.exe --pip …` before importing Qt; sdk.pip_install uses it (+ --log file).
  Updater picks `-win64.zip` when frozen, the other zip when run from source (app_updater._pick_asset).
- Tool loading: package `omniwrench_tool_<id>` via importlib with submodule_search_locations; `_lib` added to sys.path.
- Settings value of type credential: `{"items": [...], "selected": i}`; items hold `ref` ("<provider>:<id>") or manual
  username/password. get_credential resolves the selected item (session cache for external providers).
  get_credential_async / CredentialField.resolve_async: instant for cache/local, else run_async. resolve() is
  thread-safe: auth_handler = call_in_gui(ask_provider_login); clear_session bumps _session so in-flight fetches
  are not cached.
- Tool hooks: manifest.hooks {"startup": "module:func"} -> ToolManager.run_hooks("startup") (app.py after login) and
  run_hook after install; providers registered via ctx.register_credential_provider are released on update/uninstall.
- PMM connector config: tool setting "connectors" (non-secret), vault ctx.secrets "conn:<id>" (secret fields, only if
  save_auth), otherwise module-level _session_auth (memory).
- PMM runtime state (Bitwarden BW_SESSION, Vault login token) in module-level _session_state[conn_id] via
  ConnectorProvider.state; cleared by on_auth_changed/close/delete; connection test uses an instance-local dict.
- PMM implementations (connector_types.json "implementation"): powershell, keepass, bitwarden (bw CLI, own
  BITWARDENCLI_APPDATA_DIR = <tool_data>/bitwarden/<conn_id>), onepassword (op CLI, OP_SERVICE_ACCOUNT_TOKEN or
  desktop app --account; ids "vaultId|itemId"), hashicorp_vault (urllib + net._SSL, KV v1/v2, BFS LIST below base
  path, max 300 LIST calls; ids = secret path). CliConnector base: find_program (cli_path, PATH, winget Links/Packages),
  NODE_EXTRA_CA_CERTS from optional ca_file. requirements.program {name, command, winget, url} -> dialog
  _ensure_program offers `winget install --id … --exact`. show_if accepts a list of values.
- Tool language: reserved setting key `_language`; change -> MainWindow.reload_tool_tabs (new instance).
- Layout persistence: layout.json (geometry, QtAds state, open tool dock names `tool:<id>:<n>`).
- Store index entries = tool.json + download_url + sha256 + translations (+ icon_data for custom image icons).
- powershell.run_ps(..., shell="powershell"|"pwsh"); ToolContext.run_powershell(..., shell=...).
- IconForge pack cache: <tool_data>/gfx.iconforge/packs/<pack>/<variant>/<name>.svg + index.json
  {version, license, variants{v:[names]}, meta{name:{tags,categories}}, categories{id:title}}.
- IconForge npm catalog: packs/catalog.json {pack: {version, size, files, published, exact, fetched}} (24 h TTL);
  PackStore.fetch_summary (/latest, for the wizard dropdown) / fetch_release (full doc, mature version).
  wizard.py: HeroBanner (painted, font-relative height) + PackWizard (signals packDownloaded/packRemoved).

## NetProbe (net.netprobe) – network test tool
- Input (IP / DNS name / CIDR / range a-b, comma/space separated) -> `targets.parse` -> list[Target]; single IP = one
  entry, networks/ranges expand (limit 4096). `classify(ip)` labels private/cgnat/loopback/… for display.
- `engine.Engine` runs asyncio in its own thread; per target a `TargetResult` (status PENDING/RUNNING/DONE/NO_ANSWER/
  ERROR/STOPPED, raw dict per test, findings). Callbacks `on_update`/`on_finished` are marshalled to the GUI via Qt
  signals in tool.py (never touch widgets from the worker thread). `options["tests"][id]` toggles each test;
  CATEGORIES general/route/ports/web/services/dns map test ids -> result tabs.
- Tests ("auf Steroiden"): ping = IcmpSendEcho (Windows, iphlpapi via ctypes) / `ping` subprocess (Linux), no raw
  sockets/admin; `ping_stats` -> loss/avg/jitter/TTL/hop guess/OS guess. Traceroute increments TTL, each hop re-probed
  in parallel (PTR, ASN via Team Cymru, class, ping). Port scan from profile quick/standard/extended/full/custom;
  open ports explained from `portinfo.PORT_META` (portlib.json, 136 ports, flags cleartext/admin/legacy/database/
  windows/ics + de/en description + usage list). HTTP/TLS probed on known web/TLS ports AND unknown open ports
  (discovers web UIs on unusual ports); cert chain via truststore (Windows store). SMB2 negotiate, RDP NLA, NTP,
  DNS-server (open resolver). For names: full DNS (`dnscheck`): A/AAAA/CNAME/MX/NS/TXT/SOA/CAA, NS serial compare,
  SPF/DKIM/DMARC/MTA-STS/TLS-RPT, DNSSEC, wildcard, AD SRV.
- `findings.evaluate(res)` -> ~60 Finding(level ERROR/WARN/INFO/OK) covering reachability/latency/route/ports/TLS/
  HTTP/SMB/RDP/NTP/DNS/mail best practices; shown in the "Befunde" tab and summarised in the target list (⚠n).
- UI (tool.py): top input row, left QTreeWidget target list with live status/progress, right an own nested
  `ads.CDockManager` (does NOT interfere with the main window's dock manager). Click a target -> a CDockWidget tab
  with a QTabWidget of only the categories that actually ran; tabs are dockable side by side inside the tool.
  `render.Renderer(tr, lang)` builds every category widget; `category_order(res)` decides which tabs exist (web only
  when a port returned usable HTTP/TLS). `&` in tab titles doubled so it is not read as a mnemonic.
- requirements.python ["dnspython>=2.6"] (pip-installed on install, like OmniVault/pykeepass). OUI vendor DB cached in
  <tool_data>/net.netprobe (localnet.VendorDB, optional download).
- v1.1: persistent target list in tool.py keyed by address (res_for_addr/item_for_addr/dock_for_addr); networks are an
  expandable parent (group_items, "x/y hosts" via list.hosts); re-testing a target reuses its entry and re-points the
  open dock; several Engine instances can run at once (self.engines). Stale updates guarded by `res_for_addr[addr] is res`.
  Test profiles (engine.template_options: overview/standard/deep/custom) via a dropdown next to Start. Ping has warm-up
  pings (ping_warmup, discarded) + a generous default timeout (2 s) so slow replies aren't miscounted as loss.
  Tabs: "profile" (Steckbrief: identity + findings strip + open-ports line) and "connectivity" (ping/MTU/route summary)
  replace the old "general" tab. PDF export via pdfreport.py (QPdfWriter + QTextDocument from HTML, no extra dependency).
  TODO (own PR): line test / remote agent (true latency, throughput, load, path port scan) + more MX-Toolbox checks.

## Vault reset (lost master password, 2026-10-20)
- Every Vault._save() also writes `recovery` = dpapi.protect(json({key: redact(key, value)})). redact(): app:credentials
  entries and credential-field items ({"items": [...]}) without "password" (+ "missing": true if one was set); refs kept;
  app:lost_secrets kept; every other key -> None (fully secret). Vaults without `recovery` get one on next unlock.
- Vault.reset(): backup file, new DEK + password unlocker only, data = non-None skeleton values, None keys go into
  "app:lost_secrets". Vault.set(key, value) removes key from that list; delete_prefix() too.
- Markers: Credential.missing (LocalProvider; resolve() returns None while missing, update() with a password clears it),
  credentials.is_missing(item) (manual item or local ref), resolve_item() -> None. UI: ui/credentials.missing_icon()
  (Lucide circle-alert, warning colour) in manager list, picker, CredentialField (+ new ✎ edit button for manual items
  and local refs); secret settings fields and GitHub token show ❗ + placeholder (ToolSettingsStore.is_lost,
  build_settings_form(lost=...)); OmniVault source list via ctx.secrets.is_lost("conn:<id>") (SDK SecretStore.is_lost).
- Login: LoginDialog link "Passwort vergessen?" -> ResetDialog (login_dialog.py).

## MS DHCP Extended Management (net.ms-dhcp-extended, folder tools/ms_dhcp_extended, class MsDhcpExtended) – Microsoft DHCP manager
  (Alpha until 1.2.0, rebuilt from Stef's DhcpScopeManager.ps1 v2.3.1; was net.scopekeeper/ScopeKeeper until 2026-10-20)
- Layers: `ipcalc` (IPv4 math, ScopeModel, range/exclusion conversion, address translation between networks),
  `optcodec` (option value parse/format/compare per definition type, STD_OPTION_IDS), `checks` (Checker -> Finding
  level error/warning/bestpractice/info + category + obj + targets["Field:Name", "Range:n", "Option:003", ...] + fix id;
  scope_findings/server_findings/draft), `netshdump` (parse `netsh dhcp server \\x dump`, build netsh commands,
  `sync_plan` = replication diff), `service.DhcpService` (all server access, normalises cmdlet output n_scope/n_opt/...,
  partner handling, replication, failover, scan), UI modules (tool, pages, page_scope, page_draft, editors, dialogs,
  ui_base, runner).
- Backend (no PowerShell since 2026-10-20): `backend.ApiBackend.call(cmd, args, on_progress)` with hello, connect,
  set_cred, disconnect, cim, cim_many, dhcp_in_dc, resolve, fo_api, netsh. `dhcpapi.py` = ctypes on dhcpsapi.dll
  (DHCP Server Management API over RPC, like the MMC); `dhcpapi.CMDLETS` maps the old cmdlet names to API calls and
  returns cmdlet-shaped dicts (ScopeId, StartRange, LeaseDuration in s …) so service.py normalisers stay unchanged.
  Alt. creds = LogonUser(NEW_CREDENTIALS) + ImpersonateLoggedOnUser per call/thread (runas /netonly). Lease time =
  option 51 (DWord), DNS settings = option 81 bit flags (DNS_FLAG_*), reservation names = client records
  (DhcpGetClientInfoV4/SetClientInfoV4); reservation UID may carry subnet(LE)+0x01 prefix -> stripped. netsh: Python
  writes a .cmd batch with ##BEGIN/##RC markers, runs it hidden (CreateProcessWithLogonW netcredentials-only if creds),
  polls the output file. Errors `@ERR:key:..` / `@RPC:op:server:code:text` -> `DhcpService.host_text`.
- Struct layouts verified against the official Win32 metadata (windows-sys 0.52 Dhcp/mod.rs) with
  scripts/dhcp_api_check/verify_api.py; logic tested on Linux with a fake dhcpsapi (fake_dhcpsapi.c, same layouts)
  via test_api.py (`dhcpapi.setup(ctypes.CDLL(...))`). Re-run both after touching dhcpapi.py.
- Partner access: DHCP API first (partner_via "Cim" = API, label "verbunden"), else netsh path ("Rpc"). `partner_mode` Auto (login checks all partners, dialog
  retry/other creds/primary only) / Lazy / Off. Replication always reads the partner via netsh dump and writes netsh
  commands (works without WinRM); custom classes/definitions are created on the partner first. Server options are
  never auto-replicated ("Copy to partner" button).
- Flow runner: UI actions are generators yielding `runner.Job(fn, status, cancellable)`; `Runner` runs fn via
  run_async, sends the result back (or throws), shows status/progress/cancel. One flow at a time, `MsDhcpExtended.run`
  queues. UserError -> error box, others -> box with traceback.
- UI: login page -> main page with own QtAds CDockManager: fixed docks Übersicht/Server-Optionen/Failover/Definitionen/
  Prüfung + one closable dock per scope (`ScopeTab`: Allgemein+Adresspool, Optionen, Reservierungen, Ausschlüsse, Leases,
  Failover, Befunde) or draft (`DraftTab`: new/duplicate with octet edits, conversion of pool/exclusions/options).
  Pool = `editors.PoolEditor` (start/end like the DHCP console, since 1.3.0; exclusions only on their own page).
  `dhcpapi.set_range` changes the pool in place via DhcpAddSubnetElementV5 (never removes it: failover scopes
  reject that with 20132); shifted pools go via the union. Findings are
  recomputed on every edit (`recheck`), mark fields (Markers "?" buttons, row tints, tab icons); double-click applies
  the fix. Clipboard MIME application/x-omniwrench-ms-dhcp-extended+json for options/reservations/exclusions with network
  conversion.
- Test hook: `MsDhcpExtended.backend_factory` replaces ApiBackend (fake backend for screenshots/flow tests; not in repo).
- Fast scan: `scanner.Scanner` (QObject, own thread, own ApiBackend) -> `DhcpService.clone_for(backend)` + `attach()`
  (re-login with in-memory secrets, partners via set_cred) -> `fast_scan`: phase 1 = one `cim_many` with all
  server-level Gets, phase 2 = per-scope Gets (options, reservations, DNS, opt. leases) in parallel; results land in
  `svc.prefetch` (key = json [name, server, params]) so the normal `cim()`/load/check code is reused unchanged.
  `cim_many` = ThreadPoolExecutor (1..16, THREADS=8), only Get-*, each result streamed as progress {key, items|error};
  DhcpApi itself parallelises per-subnet work of "all scopes" queries. Each scope is evaluated once its keys are in
  -> `scope_done` signal -> CheckPage refresh coalesced by a 300 ms timer. Cancel = `ApiBackend.kill()` (stops
  waiting, pending calls cancelled); partial result has partial=True.
- Partner comparison (scan option "Mit Partnern abgleichen"): `partner_check(pn)` reads partner options, defs,
  classes, its failover relationships (fo_api enum) and the failover scopes (`partner_scopes`: netsh full dump for
  "Rpc" partners, else API per scope). `apply_partner_diffs` adds `Checker.partner_scope` findings (category
  `partner`) to the scope entries and stores them in scan["partner_diffs"] -> `set_scan` copies them to
  `svc.partner_diffs`, `ScopeTab.recheck` shows them with fix "replicate"; `replicate` clears a scope on success.
  Relationship/class/definition-type differences are server findings (`server_findings`).
- Transactions (1.3.0): `svc._tx` = open `Tx` (title, undo list of (label, fn)). Every write primitive reads the old
  state while a tx is open and records its inverse AFTER the write succeeded (`_undo_after`; failover scope lists
  and partner-scope syncs record before, Windows may apply them partially). `svc.atomic(title, fn)` for one Job,
  `ctl.atomic(title, gen)` (tool.py) for flows over several Jobs: on exception it yields a rollback Job
  (`tx_fail` -> TxError with text tx.rolled_back / tx.partial), on GeneratorExit (cancel) it queues `_rollback_flow`.
  Nested tx: success merges undo into the outer one, failure rolls back only its own steps and re-raises.
  Wrap only the write part of a flow - reloads/after_change replication stay outside. Partner inverses: netsh
  (`_netsh_undo`, `_undo_partner_scope` = sync_plan back to the dump snapshot or `delete scope`), fo_api (`_fo_undo`,
  deleted relationship comes back without shared secret). Test: scripts/dhcp_api_check/test_tx.py (stateful fake).
- DHCPv6 (1.5.0): `dhcpapi._V6` mixin (DhcpEnumSubnetsV6 … DhcpServerSetConfigV6, DHCP_IPV6_ADDRESS = High/Low
  QWORD big-endian halves, `ip6()`/`ip6s()`), cmdlet names Get-DhcpServerv6* in CMDLETS. Service: `scopes6`,
  `scope_info6`, `server_options6`, `defs6` (keyed (vendor, id), internal ids >= V6_INTERNAL_MIN hidden),
  `get_scope6`, `scope6_set/add/remove`, `excl6_*`, `res6_*` (DUID+IAID; name/desc via client record),
  `lease6_remove`, opt/def/srv functions take `v6=`. All record undo like v4. `checks6` = scope/server findings
  (Checker gets defs6/server_options6). UI: `page_scope6.ScopeTab6(ScopeTab)` (PAGES/PAGE_TARGETS class attrs,
  no Failover page), `dialogs.scope6_dialog/reservation6_dialog/exclusion6_dialog`, `tool.set_family`,
  `tool.new_scope6_flow`, pages.ServerOptionsPage/DefsPage `v6` property follows `ctl.family`. `ip6calc` = v6 math
  (prefix, convert_values for duplicate/paste). Scan: `scan_list/scan_scope/scan_finish` cover both families;
  `dnscheck.findings` (ThreadPoolExecutor 16, getaddrinfo + gethostbyaddr) when scan option with_dns.
  Tests: scripts/dhcp_api_check/fake_dhcpsapi6.c + test_api6.py.
- Changes by others (1.4.0): `svc.config_of(data)` = comparable scope config (no leases/stats), `diff_config` ->
  readable lines. ScopeTab keeps `base`/`loaded_utc` (set in `set_data`; keep_edits keeps only fields the user
  actually changed). `ScopeTab.guard()` before writes, `ServerOptionsPage._guard(servers)` likewise, both use
  `ui_base.choose`. Auto-refresh: `refresh_timer` -> `_poll_tick` (only if runner idle, no queue, no modal) ->
  `poll_flow` with `Job(quiet=True)` (Runner then skips busy/status, UI stays usable; user flows queue behind it),
  `ScopeTab.apply_remote` reloads or shows the banner. "Who": `eventlog.EventReader` (wevtapi EvtOpenSession with
  the connection's credentials, channel Microsoft-Windows-Dhcp-Server/Operational, EvtFormatMessage, SID ->
  LookupAccountSid on the server), backend cmd `events`, `svc.change_events(since, sid, mask)` filters by IPs in
  the message text; unreadable log -> [] and one log line (`events_error`). Tests: test_conflict.py.
- Event log page (1.4.1, `page_events.py`, fixed dock index 5, loads on first show via visibilityChanged):
  `svc.events(server, since, max)` raises `EventLogError(code)` (5 access, 1722/1753 RPC, 15007 channel) ->
  warning box with wiki link `#ereignisprotokoll-einrichten`. `eventlog.classify(ev, scopes)` = reading aid
  (area/action keywords de+en, scope by IP containment, option number via regex, also EventData fields);
  hint text per area (`evt.hint.*`). poll_flow pushes new events via `events_page.add_events`.
  1.4.2: `EventsPage.load()` bypasses the Runner (own `run_async` thread, fetch + classify `_rows(items, ctx)` in the
  worker on a snapshot `_context()`), so the UI stays usable; `_gen` counter drops stale results (reset/reload),
  `add_events` during loading is buffered in `_pending`.
- Login view: stack index 0 form, 1 main, 2 loading card (title, busy bar, last 8 log lines); `_failed` jumps 2 -> 0.
- 1.1.0 (2026-10-22): Rights: `DhcpApi.access()` = no-op write probe DhcpServerSetConfigV4(FieldsToSet=0): rc 0 admin,
  5 read (DHCP Users), else unknown (treated as writable). `svc.rights` per server ("*" = primary), `svc.can_write(s)`;
  every page has `apply_rights()` (hide write buttons/actions, read-only editors); `MsDhcpExtended.apply_rights()` after
  refresh. Partner view: `svc.load_peer(pn)` -> `svc.peer[pn]` {fo, scopes, options, errors} (API or netsh dump),
  `ctl.load_peer_flow`. FailoverPage: expandable head row per relationship (key "rel|*", `_open` set, rows hidden via setRowHidden) + one row per server (key "rel|server", real name in `_srv`), lower grid = ALL scopes of
  the selected server with membership. ServerOptionsPage: server grid (primary + partners), `compare()` gives sync
  state per option, only own options (1.2.0, no ghost rows), `_only_on` lets a finding jump to the server that has the option, transfer per option only. CheckPage: `DistBars`
  (stacked bars per category) + top scopes + segmented buttons/QStackedWidget instead of tabs. DefsPage: lock banner,
  writes only after unlock; dock shown only with setting expert_mode. Grid.enable_layout(settings,key) = movable/
  hideable columns stored {"order","hidden"}; overview + failover use it.

## MS DNS Extended Management (net.ms-dns-extended, folder tools/ms_dns_extended, class MsDnsExtended)
- Same UI architecture as the DHCP tool (copied, not imported: ui_base, runner, eventlog): generator flows + Runner,
  FindingsView/markers, QtAds docks (pages overview/server/search/compare/check/events + one tab per zone).
- Layers: `dnsutil` (names, reverse v4/v6, TTL/timestamp, Rec dataclass, text representation, validation),
  `wmidns` (WmiServer over root\MicrosoftDNS, errors as @ERR/@WMI strings), `backend.WmiBackend` (servers, creds,
  event log, DHCP read, dnspython probes), `dhcpread` (dhcpsapi leases/reservations, read-only), `checks`, `service.
  DnsService` (session, cache {(server, zone): recs, loaded, serial}, Tx undo journal, guard/diff, bulk ops), UI
  (`tool`, `pages`, `page_zone`, `dialogs`), `ping` (ICMP v4/v6).
- Conflict check: SOA serial of each touched zone before writing (`guard`); after a write only the new serial is
  stored, after a failure/cancel the zones are reloaded (`_after_write_flow`).
- Tests: scripts/dns_check/fake_backend.py (2 DCs + DMZ server) and test_logic.py; `MsDnsExtended.backend_factory`
  replaces the WMI backend for renders.
- Replication (1.1.0): `service.repl_peers/repl_status/repl_of/repl_diff/repl_pending/replicate`, state in
  `svc.repl[(server, zone)]` (peer record keys, serials, last xfr, unconnected secondaries via SOA probe).
  `tool.repl_check` (run_async, no runner), `repl_watch` (QTimer re-checks after own writes, REPL_DELAYS),
  `replicate_flow`. AD trigger: `adrepl.sync_all` = ntdsapi DsBindWithCredW + DsReplicaSyncAllW (push, cross-site,
  ids by DN) on the partition from `MicrosoftDNS_Zone.GetDistinguishedName` (`adrepl.partition_of`), then
  UpdateFromDS on peers; file zones: ForceRefresh on connected secondaries. `MsDnsExtended.show_error(..., warning)` =
  popup with Detailansicht.

## Server favourites (DHCP 1.6.0, DNS 1.2.0, 2026-10-28)
- `tools/ms_dhcp_extended/favorites.py` == `tools/ms_dns_extended/favorites.py` (identical copy, no imports between
  tools; test checks equality). FavoriteStore(settings) on the undeclared tool setting "favorites":
  {"version":1,"last":id,"items":[{id,name,server,note,login:{mode sso|vault|manual,user,cred:{ref}|{name,username}},
  options:{tool-specific},ai:{}}]}. save() merges (unknown keys + sections like "ai" survive; "login" is replaced),
  always deep copies (ToolSettingsStore compares values). section()/set_section() for other features.
- FavoritesBar (row "Favorit" on the login card): combo + ☆ (save new / overwrite selected) + "Verwalten …"
  (ManageDialog: edit, up/down, delete). Signal applied(fav) -> tool.fav_apply fills the form; tool.fav_capture
  reads it. Manual edit of the server -> selection "Kein Favorit". restore() at build selects the last one.
- Credentials: only cred_key (ref or name+username) -> match_cred finds the item in the CredentialField list and sets
  cred_field.combo; missing -> login_status hint. Passwords never in favourites.
- DHCP options: auto_partner, auto_scan, family (applied via set_family after login when the favourite's server equals
  the typed one, `_login_fav`). DNS options: auto_discover, auto_scan + extra_fields servers (list) and dhcp_server,
  edited only in the favourite dialog; fav_login_flow connects them (connect_servers_flow, shared with discovery) and
  sets svc.dhcp_server/user/secret from the login.
- KI integration (thread "KI-Integration", branch claude/project-thread-ie207t) uses "ai": {"level": null|int,
  "pseudo": null|bool} (null = inherit) via section()/applied.
- Test: scripts/fav_check/test_favorites.py (store + both tools offscreen with the screenshot fake backends).

## Wiki and template (2026-10-22)
```
wiki/                         GitHub-Wiki source (German), *.md + images/; mirrored by .github/workflows/wiki.yml
  Tool-<Name>.md              one page per tool (template: Vorlage-Tool-Seite.md)
  Entwicklung-*.md            developer area (package format, SDK, i18n, layout, own repo, template, testing)
templates/tool-repo/          content of the template repo KuroShiroMe/OmniWrench-Tool-Template
  .github/workflows/setup.yml   one-time self setup (scripts/setup_repo.py, marker .github/template-setup.json)
  .github/workflows/store.yml   checks (compileall, check_locales, store.py check) + builds/commits store/ on main
  scripts/store.py              incremental store build with version guard (uses OmniWrench's manifest validation)
  scripts/new_tool.py           new tool from template/tool + docs page from template/Tool-Seite.md
docs/README.md                internal docs index, points to the wiki
```
- Help menu: `WIKI_URL` in ui/main_window.py (from GITHUB_REPO), `menu.wiki` (F1) and `menu.dev_docs` open the wiki.

## Screenshots (since 0.8.0)
- tool.json `screenshots: [{file, caption}]`; manifest.screenshot_list, screenshot_caption() (tool locale key
  `tool.screenshot.<stem>` -> translations `screenshot.<stem>`).
- scripts/render_screenshots.py: temp OMNIWRENCH_HOME, offscreen 3840x2160 screen, copies tool to TOOLS_DIR,
  imports `screenshots.render` via manager._import_module, calls render(shot) (Shot API: create/module/settings/
  wait/wait_until/save/save_dialog/source). Fakes per tool live in screenshots/render.py (DNS uses
  scripts/dns_check/fake_backend.py, aliases tools.ms_dns_extended.* to the loaded modules).
- build_store.py: zip excludes screenshots/, copies them to store/screenshots/<id>/, index entry gets url/sha256/size.
  check_store.check_screenshots verifies. repository.load_catalog resolves urls; install_from_catalog ->
  fetch_screenshots() copies them into the installed tool (offline Home).
- Template repo: scripts/screenshots.py (wrapper for OmniWrench's render_screenshots.py), store.py handles
  screenshots the same way; example tool ships screenshots/render.py + main.png.

## AI assistants (omniwrench/ai/, since 0.9.0)
- `providers.py` catalog from resources/ai/providers.json (63 providers, categories, auth kinds, capabilities, media
  APIs). Newer copy from `<repo>/ai/providers.json` (store) cached in CACHE_DIR/ai, newest "updated" wins, entries
  of the bundled file missing in the newer one are kept. build_store copies it to store/ai/, check_store verifies.
- `connections.py` settings "ai_connections" (no secrets) + vault "app:ai:conn:<id>" ({api_key} or OAuth tokens,
  ChatGPT issued client_id, account). key_ref = password manager reference. "ai_primary" = primary id.
- `oauth.py` loopback http.server on 127.0.0.1 + PKCE: ChatGPT (dynamic client, ext_agent_host_id = settings
  "ai_host_id", /auth/callback), OpenRouter (key exchange), Entra (default client Microsoft Graph CLI tools, tenant
  organizations, redirect http://localhost:<port>/), custom OAuth (client secret in vault). access_token() refreshes.
- `http.py` urllib + truststore SSL, SSE parser, AIError(kind auth/limit/quota/network/server/request/removed);
  localhost/127.x bypass proxies.
- `adapters.py` OpenAIChat (chat/completions, most providers), OpenAIResponses (OpenAI + ChatGPT sign-in, store
  false), Anthropic (messages), GraphCopilot (beta copilot/conversations, no tools, conversation id in thread state).
  Unified message format: user {content, images[{mime,data}]}, assistant {content, tool_calls[{id,name,arguments}]},
  tool {tool_call_id, name, content}.
- `chat.py` run(): loop up to 12 rounds with function calls, RunHooks (on_text/on_tool/on_message/confirm/level_for/
  encode/decode for pseudonymization), system prompt with detail level + project instructions, trimming 200k chars.
- `functions.py` registry Function(name, description, handler(args, ctx), parameters, source app|tool id, level 1-4,
  confirm). available(level_for) filters by access level.
- `storage.py` modes documents/central/per_type, Windows known folders via SHGetKnownFolderPath, XDG user-dirs.
  Docs written as <base>.json (+.md) or encrypted <base>.owai (b"OWAI1"+nonce+AES-GCM, key vault "app:ai:data_key").
  Chats <chats>/<id>/thread.*, projects <projects>/<pid>/project.* + files/ + threads/<id>/. convert_all() on toggle.
- UI: `ui/ai_panel.py` AIPanel in CDockWidget "ai-assistant" (right area, hidden by default; menu bar corner button
  "✦ Assistent", View menu, Ctrl+Shift+A). Background run works on a copy of the thread, merged on finish (stop
  discards). Rounds after function calls continue in the same bubble. `ui/ai_settings.py` tabs "KI-Assistenten"
  (AIConnectionsPage, changes apply at once) and "KI-Datenablage" (AIStoragePage, saved with the dialog) in
  AppSettingsDialog (initial_tab="ai"). ConnectionDialog: ProviderPicker (categories, search, capability/auth/region
  filters, removed red) -> form per auth kind, load models, test.
- Smoke test: fake OpenAI server, empty-state check per language, real chat round trip in "de".
- Etappe 2: `knowledge.py` wiki/*.md (APP_DIR/wiki or _MEIPASS/wiki, build_exe add-data) split at headings into
  SQLite FTS5 (LOCAL_DIR/ai-index/knowledge.db, rebuilt on fingerprint change; word-count fallback).
  `app_functions.py` registers source "app": program_info, list_installed_tools, list_store_tools,
  search_documentation, read_documentation_page (level 1), list_open_tabs (2), open_tool/install_tool (4, confirm).
  `access.py` settings "ai_access" (level, pseudo, pseudo_kinds, exceptions per connection) and "ai_access_tools"
  {tool_id: {level|null, pseudo|null, exceptions}}; level(): tool exception > runtime (set_runtime from favorites) >
  tool level > app exception > app level. `pseudo.py` Pseudonymizer(state=thread.state.pseudo): IPv4 (NETn.x keeps
  /24), IPv6, MAC, email, FQDN (HOST-n.DOMAIN-m), DOMAIN\user; skips masks/loopback/public domains/file names;
  encode_value() maps dict keys host*/server*/user* too; known values replaced in free text; rev map for exact decode.
  Tool results are encoded at execution per tool pseudo setting (RunHooks.encode_result) and not re-encoded.
  Streamed text is decoded on the whole raw buffer (placeholders split across chunks). UI: AIAccessPage (app tab
  "KI-Zugriff" + tab in every ToolSettingsDialog), ConfirmDialog with "remember for this session".
- `scripts/test_ai.py` (CI): fake server for all 3 protocols, pseudonymization, access, storage, wiki search.
