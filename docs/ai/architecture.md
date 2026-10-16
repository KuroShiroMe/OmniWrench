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
  manifest.py                 ToolManifest (id,name,version,category,icon,icon_text,icon_data,entry,requirements,
                              translations…), SettingDef, validate_package, localized()/display_name/category_path
  tool_settings.py            ToolSettingsStore: JSON for normal, vault for secret/credential types; listeners
  tool_manager.py             ToolManager(QObject): refresh, create_instance, install_zip/dir (backup+rollback),
                              _install_prerequisites (check() first), uninstall, repair; module prefix omniwrench_tool_<id>
  prerequisites.py            pip (_lib), elevated capabilities/features (##OW markers -> localized progress,
                              restart notice, WSUS/FoD hint on 0x800f0954 etc.), PS modules, winget
  repository.py               load_catalog(repos), available_updates, install_from_catalog
  app_updater.py              GitHub releases check/download/apply (PS script replaces files after exit)
  net.py                      urllib + truststore SSL, github_token header
  i18n.py                     tr(), set_language, fallback_chain, tool_translator, resolve_tool_language
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
  store_page.py               StoreCard, StorePage (category tree, filters)
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
                              omnivault (sec.omnivault), iconforge (gfx.iconforge) - see below
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
