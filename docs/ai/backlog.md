# Backlog / next steps

Since 2026-10-17 open items are tracked as GitHub issues (#17–#38, labels). Keep this file and the issues in sync.

## Open / to verify with user
- [ ] KI-Integration (branch claude/project-thread-ie207t, Stef tests only the end product): stages 2-7 open
      (knowledge + KI-Zugriff + pseudonymization; tool functions + context menu; KI-Studio tool; images + group chat;
      music/video; transcription, voice agent, MCP, templates, scheduling). App locales: only en/de have the ai.* keys
      so far, other 21 locales get translated in one pass at the end. Wiki pages + landing page + TESTLISTE at the end.
- Landing page kuroshiro.me: live. Open: enforce HTTPS (Stef), re-render site/img screenshots after KuroShiro rename (PR #53).
  Impressum/legal page if the site counts as geschäftsmäßig (Stef to decide, needs a postal address).
**All open Windows tests live in `docs/TESTLISTE.md` (German, grouped by tool, created 2026-10-22).** Keep that file
as the single test list: add new test points there, tick/remove them when Stef reports results. Below only notes
that are not plain test steps.

- [ ] MS DHCP Extended Management (net.ms-dhcp-extended 1.3.0, Alpha removed 2026-10-22): backend (DHCP API via
      ctypes) only tested with a fake DLL. THREADS=8 may need tuning. Old net.scopekeeper installs must be removed by
      hand. Later ideas: replication via API instead of netsh (would drop RSAT), policies/filters editing.
- [ ] DHCP 1.5.0 IPv6/DHCPv6 + DNS-Abgleich: Windows check open (TESTLISTE 5, "1.5.0"). Verify on a real server:
      Get/SetClientInfoV6 for reservation names, hidden option ids, MIB stats, binding info. Ideas: v6 overview
      "free addresses" column stays empty (/64), maybe show leases in use; v6 DNS settings (option 39 / server flags).
- [ ] DHCP 1.4.2: event log loads in background thread - Windows check open (TESTLISTE 5, 1.4.1 tested OK by Stef).
- [ ] DHCP 1.4.1 event log page: classify() keywords are guesses from MS docs wording - tune with real
      message texts from Stef's test environment (German server). Per-scope "who" filter matches IPs in message text
      and EventData values.
      Ideas: compare DNS settings (option 81) and policies with the partner; "take value from partner" fix for
      single differences (replication always pushes this server's state).
- [ ] PowerShell -> Python inventory (2026-10-20, Stef wants PowerShell only where unavoidable): core/prerequisites
      (Windows capabilities/winget/PS modules, elevated - DISM API/`dism.exe` possible), core/certificates (cert store
      list/sign/decrypt via .NET - Python needs CryptoAPI/NCrypt via ctypes for smartcards), core/app_updater
      (portable update only, -EncodedCommand after exit - could be a .cmd + tar.exe; installed version uses setup.exe), ad_user_lookup (ActiveDirectory module - LDAP via
      ldap3/ctypes ADSI possible), omnivault PowerShellConnector + SecretManagement (by design PowerShell, stays).
- [ ] NetProbe weitere MX-Toolbox-Funktionen (nächster Schritt, von Stef gewünscht): DNSBL-Blacklist-Prüfung,
      SMTP-Open-Relay-Test. Ideas later: IPv6 port scan tuning, SNMP/mDNS/LLDP discovery, scheduled re-scan.
- [ ] Netwrix connector (#22, blocked): untested, needs Enterprise Pro. Open questions: password-auth field keys in
      DynamicFillableAuthentication.Fields, PsrContainer.Name vs. Info, SDK DLL in PowerShell 5.1 (default: pwsh 7).
- [ ] Alpha tags of Bitwarden/1Password/HashiCorp Vault connectors: remove per connector once Stef confirms (#19-#21).
- [ ] 0.5.x installs: update manually to 0.6.0 once (self-update would fetch the -win64 zip, see gotchas).
- [ ] Only Stef: CI checks as required in branch protection (#24); project settings in claude.ai still list
      `Steffi-Tech/OmniWrench` -> switch to `KuroShiroMe/OmniWrench`; delete merged `claude/*` branches (cloud
      sessions cannot delete branches) or enable "Automatically delete head branches".
- [ ] Vendor rename KuroShiro (2026-10-22): data-dir migration and setup move from C:\Program Files\DarkMatter only
      take effect with the next release (0.8.0); test per TESTLISTE. README screenshots: re-render when the UI changes
      (pattern in history.md, 2026-10-22).
- [x] Merged 2026-10-22: #45 categories one level + tags, #46 tool updates, #47 master password reset, #48 rename
      KuroShiroMe, #49 DHCP 1.2.0. UAC prerequisites (#10) tested OK 2026-10-16.

- [ ] MS DNS Extended Management 1.0.0 (net.ms-dns-extended): WMI backend (wmidns.py) only tested with a fake backend,
      all Windows tests open (TESTLISTE 9). Unsure until tested: AgeAllRecords NodeName format (FQDN with dot), WMI array
      assignment for forwarders/secondaries, audit log keywords in eventlog.classify (German server texts).
      Ideas: DHCPv6 leases in dhcpread (after PR #60), DNSSEC/policies/zone scopes read-only views, per-record aging via
      DNS RPC API (DnssrvUpdateRecord) instead of AgeAllRecords, virtualised record table for very large zones.
      1.1.0 replication (TESTLISTE 9a) untested on Windows: DsReplicaSyncAllW via ctypes, GetDistinguishedName out
      param name "Name", LastSuccessfulXfr units. Idea: repl column also in search results.

## Later (mentioned by user or proposed)
- More password-manager connectors (Bitwarden, 1Password, HashiCorp Vault done in 1.1.0): KeePassXC (browser protocol),
  Passbolt, Psono, Devolutions, Delinea, CyberArk, Pleasant, Azure Key Vault, Keeper.
- Connector folder structures (explicitly NOT now - search only).
- IconForge: more icon sources (combo "source" prepared), e.g. custom user folders, other free libraries.
- [ ] EXE build (scripts/build_exe.py) done, tested on Linux + CI; still to test on user's machine: start, login with
      smart card, tool install incl. pip (OmniVault/pykeepass), self-update from -win64.zip, UAC prerequisites.
- [ ] Code signing via SignPath Foundation (docs/EXE_SIGNIEREN.md): Stef applies at signpath.org (needs GitHub
      2FA, a released version), then sets SIGN_METHOD=signpath + SIGNPATH_* vars/secret. SignPath path untested
      until approval.
- Installers DONE 2026-10-22 (Inno Setup + .deb, 0.7.0). Later: sign setup.exe/uninstaller once signing exists,
  self-updater could verify signatures; rpm (Fedora/RHEL/openSUSE) and/or AppImage if Stef wants other distros;
  arm64 Linux build; Windows per-user install option (no UAC) if needed.
- [ ] Linux follow-ups: AD User Lookup via LDAP (ldap3) would make it Linux-capable; DHCP tool stays Windows-only
      (dhcpsapi.dll). Vault recovery on Linux uses a key file (no Secret Service/keyring integration yet).
- Move repo to a GitHub org "KuroShiro" if user creates one (then update GITHUB_REPO).
- Languages: it, nl, pl, pt, cs, sv, tr, uk + dialects swg/sxu/nds/gsw/ksh/wien DONE 2026-10-16 (app only).
  Still open: ja, zh-Hans (font/width tests); RTL (ar, he) needs layout work; tool locales for the new languages
  (optional, fallback works); German UI texts are long in some languages (pl, nl) -> check widths on Windows.
- [ ] Native-speaker review of fr/es/dialect translations STILL OPEN (incl. de_hes and ALL languages/dialects added
      2026-10-16: it nl pl pt cs sv tr uk, de_swg de_sxu de_nds de_gsw de_ksh de_wien - AI-written, unchecked). 2026-10-16: AI review done (main app locales
      only, see history); a real native speaker has NOT checked them. Open points: French typography (narrow
      no-break space before : ? ! and inside « », currently normal spaces), tool locales only exist in de/en
      (+ Subnet de_bad; OmniVault has all 8), new keys from connector/CI PRs need the same review.
- IconForge: more libraries (e.g. Azure/AWS architecture icons have special terms). Pack management done in 1.1.0
  (wizard: download, download again, remove). Idea: real sample icons in the banner before download (needs a CDN
  like jsDelivr; blocked in some networks, so not used yet).
- Categories (done 2026-10-17, #32): dialect translations of category names are the base-language text (no dialect
  flavour yet); native-speaker review together with #25.
  2026-10-20: reduced to one level + tags (all tools incl. MS DHCP Extended 1.2.1 since 2026-10-22).

## Wiki / template repo (2026-10-22)
- [ ] Stef: enable wiki (Settings › General › Features › Wikis) and create a first page by hand ("Home", any text),
      then run workflow "Wiki" once (Actions › Wiki › Run workflow). Afterwards it syncs on every push to main.
- [ ] Stef: create public repo `KuroShiroMe/OmniWrench-Tool-Template`, copy `templates/tool-repo/` content (incl.
      dotfiles), tick Settings › General › "Template repository", Actions workflow permissions "Read and write".
      Then test "Use this template" once.
- [ ] Optional: protect wiki from manual edits (Settings › Wikis › "Restrict editing to collaborators only").
- [ ] Rich screenshots for AD Benutzerabfrage (only empty search mask, needs a domain) and fresh DHCP overview/scope/
      draft images (current ones are 1.0.0 cropped; a fake backend via MsDhcpExtended.backend_factory would allow it).

## Store/Home 0.8.0 (2026-10-27)
- [x] Windows test by Stef OK (2026-10-27). [ ] Tag v0.8.0 by Stef (release notes + site links prepared).
- [ ] When a tool's UI changes: re-render its screenshots (`scripts/render_screenshots.py tools/<x>`), rebuild store.
- Idea: landing page could show each tool's main screenshot in the tool list (store/screenshots via raw URL).
- Idea: German screenshot set (`--lang de`) shown when the UI language is German (needs per-language files).
