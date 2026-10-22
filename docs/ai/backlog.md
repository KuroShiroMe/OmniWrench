# Backlog / next steps

Since 2026-10-17 open items are tracked as GitHub issues (#17–#38, labels). Keep this file and the issues in sync.

## Open / to verify with user
- [ ] MS DHCP Extended Management (net.ms-dhcp-extended 1.2.0, Alpha tag removed 2026-10-22; was net.scopekeeper): Stef tests on Windows against
      real DHCP servers. Backend is new (DHCP API via ctypes, no PowerShell) - only tested with a fake DLL on Linux.
      Check: login SSO/vault/manual (runas-netonly creds), overview/stats, scope tab (ranges, options incl. binary/
      vendor, reservations names/types/MAC format, leases states/expiry, DNS settings = option 81), save/range change,
      new/duplicate scope, failover create/edit/remove (role/LB mirroring), replication via netsh, server check speed,
      cancel, auto check after login. 1.1.0: rights probe (DHCP Users account -> read-only UI; untested on real
      servers), partner scopes/options view, per-option transfer, failover rows per server. THREADS=8 may need tuning. Old net.scopekeeper installs must be removed by hand.
      Later ideas: replication via API instead of netsh (would drop RSAT), IPv6 scopes, policies/filters editing.
- [ ] PowerShell -> Python inventory (2026-10-20, Stef wants PowerShell only where unavoidable): core/prerequisites
      (Windows capabilities/winget/PS modules, elevated - DISM API/`dism.exe` possible), core/certificates (cert store
      list/sign/decrypt via .NET - Python needs CryptoAPI/NCrypt via ctypes for smartcards), core/app_updater
      (apply_update.ps1 after exit - could be a .cmd + tar.exe), ad_user_lookup (ActiveDirectory module - LDAP via
      ldap3/ctypes ADSI possible), omnivault PowerShellConnector + SecretManagement (by design PowerShell, stays).
- [ ] NetProbe (net.netprobe 1.1.0): Verify on Windows: IcmpSendEcho ping incl. new warm-up + 2 s timeout (Stef saw
      loss that CMD didn't – likely the old 1 s timeout), persistent list + expandable network groups (x/y hosts),
      re-test-in-place, context menu/buttons (repeat/delete/PDF export), test-template dropdown, Steckbrief/Konnektivität
      tabs, DNS best-practice findings (CAA/MTA-STS/TLS-RPT), PDF export (QPdfWriter). DNS checks need real DNS
      (sandbox proxy only answers A/AAAA). Ideas later: IPv6 port scan tuning, SNMP/mDNS/LLDP discovery, scheduled re-scan.
- [x] NetProbe Leitungstest/Remote-Agent (net.netprobe 1.2.0, eigener PR 2026-10-19): echte Latenz, Durchsatz,
      Lasttest, Pfad-Portscan via Mini-Tool `linkagent.py` (stdlib-only, Win+Linux) ODER NetProbe↔NetProbe.
      Export-Button + „Als Gegenstelle dienen“ im Optionsfenster, ❗ beim Profil „Leitungstest“. Token-Pflicht (Last nur
      gegen einwilligende Gegenstelle). Auf Windows zu prüfen: Server-Bind auf 0.0.0.0, Firewall-Freigabe für den Port,
      echte Durchsatz-/Latenzwerte über eine reale Strecke zwischen zwei Rechnern.
- [ ] NetProbe weitere MX-Toolbox-Funktionen (nächster Schritt, von Stef gewünscht): DNSBL-Blacklist-Prüfung,
      SMTP-Open-Relay-Test.
- [ ] 0.6.0 released (tag v0.6.0, release built by CI); user still tests on Windows (source + EXE).
      0.5.x installs: update manually to 0.6.0 once (self-update would fetch the -win64 zip, see gotchas).
- [ ] Netwrix connector: scripts now follow the official PsrApi docs; still untested against a real server.
      Marked `stage: alpha` (OmniVault 1.0.1) - user has no Enterprise Pro licence to test; remove the tag once
      someone with Netwrix Enterprise Pro confirms it works.
      Open questions: password-auth field keys in DynamicFillableAuthentication.Fields, PsrContainer.Name vs. Info for
      display name, whether SDK DLL loads in PowerShell 5.1 (default: pwsh 7).
- [ ] Bitwarden, 1Password, HashiCorp Vault connectors (OmniVault 1.1.0, stage alpha): only tested against fake
      bw/op CLIs and a fake Vault HTTP server on Linux. To verify live: bw login/unlock with Vaultwarden + bitwarden.com,
      op with service account and desktop app (does `item get --format json` return concealed values without
      --reveal on current op versions?), Vault token/userpass/LDAP/AppRole, winget install path detection.
      Remove alpha tag per connector once confirmed.
- [ ] SecretManagement connector: live test (module not installed on dev machine).
- [ ] KeePass connector: user will test in next round (no KeePass installed yet; pykeepass needs no KeePass).
- [x] UAC prerequisites (ShellExecuteExW, PR #10) merged; Stef tested on Windows 2026-10-16: OK.
      Windows Server: not a target (Stef 2026-10-16); Home shows a notice that functions are limited.
- [ ] Scaling restart (QProcess.startDetached) only tested on Linux renders - verify on Windows (source + EXE).
- [ ] IconForge 1.1.1 (narrow header, PR): user check on Windows at small window width / 150-200 % scaling.

- [ ] CI (ci.yml + build-exe.yml on every PR): mark checks as required in GitHub branch protection for main
      (Settings > Branches) - only the user can do that.

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
