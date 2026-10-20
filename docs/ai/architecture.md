# Architecture (where is what)

```
main.py                       -> omniwrench.app.main()
omniwrench/__init__.py        APP_NAME, VENDOR, __version__, GITHUB_REPO, OFFICIAL_STORE_URL
omniwrench/app.py             logging, language+Qt translator, theme, LoginDialog, credentials.init, MainWindow loop
                              (restartRequested -> rebuild window without re-login; setQuitOnLastWindowClosed(False))
omniwrench/sdk.py             PUBLIC API for tools: ToolBase, ToolContext, InstallContext, run_async, LANGUAGE_KEY,
                              pick_credential, CredentialField, PSResult, ps_quote
omniwrench/core/              (Qt-free except tool_manager QObject)
  paths.py                    dirs (VENDOR/APP_ID), RESOURCES_DIR, APP_DIR
  vault.py                    Vault: create/unlock (password|cert)/lock, get/set keys "app:*", "tool:<id>:<key>"
  certificates.py             cert list/encrypt (Python) / decrypt (PowerShell .NET, smart card ok)
  powershell.py               run_ps (EncodedCommand, UTF-8, CLIXML cleanup), run_ps_elevated (UAC via elevation.py, live log tail, on_output;
                              wrapper: script base64-embedded, lines appended to log, errors prefixed ##ERROR)
  system.py                   is_windows_server() (registry InstallationType, cached)
  elevation.py                ShellExecuteExW runas (owner hwnd = main window, ERROR_CANCELLED 1223), is_admin/needs_uac
  categories.py               AREAS (ids, one level), LEGACY_AREAS, category_id(), category_path(manifest) -> [area] localized
  manifest.py                 ToolManifest (id,name,version,category,tags,icon,icon_text,icon_data,entry,requirements,
                              translations…), SettingDef, validate_package, localized()/display_name/category_path
  tool_settings.py            ToolSettingsStore: JSON for normal, vault for secret/credential types; listeners
  tool_manager.py             ToolManager(QObject): refresh, create_instance, install_zip/dir (backup+rollback),
                              _install_prerequisites (check() first), uninstall, repair; module prefix omniwrench_tool_<id>
  prerequisites.py            pip (_lib), elevated capabilities/features (##OW markers -> localized progress,
                              restart notice, WSUS/FoD hint on 0x800f0954 etc.), PS modules, winget
  repository.py               load_catalog(repos), available_updates, install_from_catalog
  app_updater.py              GitHub releases check/download/apply (PS script replaces files after exit)
  net.py                      urllib + truststore SSL, github_token header
  i18n.py                     tr(), set_language, fallback_chain, tool_translator, resolve_tool_language,
                              language_tree (dialects indented under base language in dropdowns)
  icons.py                    Lucide library (names, svg), resolve(icon, icon_text, name, dir, data) -> IconSpec
  credentials.py              Credential, AuthField, AuthenticationRequired, CredentialProvider (search/get_secret/
                              auth_fields/set_auth/close), LocalProvider (vault "app:credentials"), CredentialManager
                              (register/unregister[_owner], search -> SearchResult(items, errors, auth_needed),
                              resolve(ref) w/ auth_handler retry + session cache, clear_session), normalize_value,
                              resolve_item, generate_password; init()/manager()
  settings.py                 AppSettings (DEFAULTS incl. repositories, language, theme, auto_lock_minutes)
omniwrench/ui/
  main_window.py              QtAds dock manager; home/store docks; open_tool/close_tool/reload_tool_tabs;
                              tool menu; install/uninstall/check/repair; updates; lock; layout save/restore
  home_page.py                ToolTile (FitLabel), DetailsPanel, HomePage (filter, select_tool)
  store_page.py               StoreCard (clickable tags -> search), StorePage (category tree, filters)
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
                              ResponsiveRow (wraps right part below), ColumnFlowLayout (n columns by width), breakable
  scaling.py                  ui_scale -> QT_SCALE_FACTOR (before QApplication), device_pixel_ratio, fit_to_screen,
                              fit_min_width, window_size, restart_application
  theme.py                    palettes + stylesheet; ads_stylesheet() must be set on CDockManager directly
  workers.py                  run_async (QThreadPool, signals), call_in_gui (BlockingQueuedConnection invoker)
omniwrench/locales/*.json     8 languages, ~280 keys
omniwrench/resources/icons/lucide/  SVGs + LICENSE + VERSION
tools/<tool>/                 subnet_calculator (net.subnet-calculator), ad_user_lookup (ms.ad-user-lookup),
                              omnivault (sec.omnivault), iconforge (gfx.iconforge), netprobe (net.netprobe) - see below
store/                        index.json + packages/*.zip (generated, committed)
scripts/                      build_store, build_release, build_exe (PyInstaller onedir), check_locales, check_store,
                              smoke_test, update_icons, sign_exe (Authenticode via signtool/osslsigncode, cert from env)
.github/workflows/ci.yml      every PR + push main: compileall, check_locales (app + each tool), check_store (Linux);
                              smoke_test.py on windows-latest (offscreen)
.github/workflows/build-exe.yml  every PR + push main + tags v*: PyInstaller build, `--pip --version`, EXE start test
                              (process must survive 20 s, no ERROR in log), optional signing on tags/manual runs
                              (vars.SIGN_METHOD: azure|signpath|certificate, docs/EXE_SIGNIEREN.md), signature check,
                              zip, artifact OmniWrench-X.Y.Z-win64.zip
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
