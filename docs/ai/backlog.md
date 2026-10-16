# Backlog / next steps

## Open / to verify with user
- [ ] Netwrix connector: scripts now follow the official PsrApi docs; still untested against a real server.
      Marked `stage: alpha` (OmniVault 1.0.1) - user has no Enterprise Pro licence to test; remove the tag once
      someone with Netwrix Enterprise Pro confirms it works.
      Open questions: password-auth field keys in DynamicFillableAuthentication.Fields, PsrContainer.Name vs. Info for
      display name, whether SDK DLL loads in PowerShell 5.1 (default: pwsh 7).
- [ ] SecretManagement connector: live test (module not installed on dev machine).
- [ ] KeePass connector: user will test in next round (no KeePass installed yet; pykeepass needs no KeePass).
- [ ] Real UAC run of elevated prerequisite install (only simulated so far).

## Later (mentioned by user or proposed)
- More password-manager connectors: Bitwarden/Vaultwarden, KeePassXC (browser protocol), 1Password, Passbolt, Psono,
  Devolutions, Delinea, CyberArk, Pleasant, HashiCorp Vault, Azure Key Vault, Keeper.
- Connector folder structures (explicitly NOT now - search only).
- IconForge: more icon sources (combo "source" prepared), e.g. custom user folders, other free libraries.
- EXE build (PyInstaller) - self-updater assumes a packed program folder.
- Move repo to a GitHub org "DarkMatter" if user creates one (then update GITHUB_REPO).
- Native-speaker review of fr/es/dialect translations.
- IconForge: pack management (remove/refresh downloaded libraries), more libraries (e.g. Azure/AWS architecture icons have special terms).
