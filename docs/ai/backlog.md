# Backlog / next steps

## Open / to verify with user
- [ ] 0.6.0 on main (PRs #1-#5 merged); user tests on Windows (source + EXE). Release tag/GitHub release only after OK.
- [ ] Netwrix connector: scripts now follow the official PsrApi docs; still untested against a real server.
      Marked `stage: alpha` (OmniVault 1.0.1) - user has no Enterprise Pro licence to test; remove the tag once
      someone with Netwrix Enterprise Pro confirms it works.
      Open questions: password-auth field keys in DynamicFillableAuthentication.Fields, PsrContainer.Name vs. Info for
      display name, whether SDK DLL loads in PowerShell 5.1 (default: pwsh 7).
- [ ] SecretManagement connector: live test (module not installed on dev machine).
- [ ] KeePass connector: user will test in next round (no KeePass installed yet; pykeepass needs no KeePass).
- [ ] UAC prerequisites rebuilt on ShellExecuteExW (branch claude/real-uac-install-axo2h0); tested on Linux with pwsh +
      mocked cmdlets only. User to test on Windows (source + EXE): RSAT install via AD User Lookup, UAC "No",
      already-admin start, WSUS hint. Windows Server: RSAT capabilities don't exist there (would need features) - open.
- [ ] Scaling restart (QProcess.startDetached) only tested on Linux renders - verify on Windows (source + EXE).
- [ ] IconForge: toolbar min widths (search 240 + pack 230 + variant 110 + category 180) force a horizontal
      scrollbar below ~1100 px dock width; preview/grid render at fixed 2x -> use sdk.device_pixel_ratio().
      Left to the IconForge rework thread.

## Later (mentioned by user or proposed)
- More password-manager connectors: Bitwarden/Vaultwarden, KeePassXC (browser protocol), 1Password, Passbolt, Psono,
  Devolutions, Delinea, CyberArk, Pleasant, HashiCorp Vault, Azure Key Vault, Keeper.
- Connector folder structures (explicitly NOT now - search only).
- IconForge: more icon sources (combo "source" prepared), e.g. custom user folders, other free libraries.
- [ ] EXE build (scripts/build_exe.py) done, tested on Linux + CI; still to test on user's machine: start, login with
      smart card, tool install incl. pip (OmniVault/pykeepass), self-update from -win64.zip, UAC prerequisites.
- Optional later: code signing of OmniWrench.exe (SmartScreen), installer (Inno Setup/MSIX), auto-upload of the
  CI zip to the GitHub release.
- Move repo to a GitHub org "DarkMatter" if user creates one (then update GITHUB_REPO).
- Native-speaker review of fr/es/dialect translations.
- IconForge: more libraries (e.g. Azure/AWS architecture icons have special terms). Pack management done in 1.1.0
  (wizard: download, download again, remove). Idea: real sample icons in the banner before download (needs a CDN
  like jsDelivr; blocked in some networks, so not used yet).
