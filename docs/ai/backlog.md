# Backlog / next steps

Since 2026-10-17 open items are tracked as GitHub issues (#17–#38, labels). Keep this file and the issues in sync.

## Open / to verify with user
**All open Windows tests live in `docs/TESTLISTE.md` (German, grouped by tool, created 2026-10-22).** Keep that file
as the single test list: add new test points there, tick/remove them when Stef reports results. Below only notes
that are not plain test steps.

- [ ] MS DHCP Extended Management (net.ms-dhcp-extended 1.2.1, Alpha removed 2026-10-22): backend (DHCP API via
      ctypes) only tested with a fake DLL. THREADS=8 may need tuning. Old net.scopekeeper installs must be removed by
      hand. Later ideas: replication via API instead of netsh (would drop RSAT), IPv6 scopes, policies/filters editing.
- [ ] PowerShell -> Python inventory (2026-10-20, Stef wants PowerShell only where unavoidable): core/prerequisites
      (Windows capabilities/winget/PS modules, elevated - DISM API/`dism.exe` possible), core/certificates (cert store
      list/sign/decrypt via .NET - Python needs CryptoAPI/NCrypt via ctypes for smartcards), core/app_updater
      (apply_update.ps1 after exit - could be a .cmd + tar.exe), ad_user_lookup (ActiveDirectory module - LDAP via
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
- [x] Merged 2026-10-22: #45 categories one level + tags, #46 tool updates, #47 master password reset, #48 rename
      KuroShiroMe, #49 DHCP 1.2.0. UAC prerequisites (#10) tested OK 2026-10-16.

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
- Optional later: installer (Inno Setup/MSIX, sign it too), self-updater could verify the Authenticode signature of a downloaded -win64.zip's exe.
- Move repo to a GitHub org "DarkMatter" if user creates one (then update GITHUB_REPO).
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
