# Backlog / next steps

## Open / to verify with user
- [ ] Netwrix connector: verify/adjust PowerShell scripts in tools/password_manager_manager/connector_types.json
      against user's PsrApi SDK (need SDK docs or DLL path). Login/search/decrypt method names are guesses.
- [ ] SecretManagement connector: live test (module not installed on dev machine).
- [ ] Real UAC run of elevated prerequisite install (only simulated so far).

## Later (mentioned by user or proposed)
- More password-manager connectors: Bitwarden/Vaultwarden, KeePassXC (browser protocol), 1Password, Passbolt, Psono,
  Devolutions, Delinea, CyberArk, Pleasant, HashiCorp Vault, Azure Key Vault, Keeper.
- Connector folder structures (explicitly NOT now - search only).
- Icon Store: more icon sources (combo "source" prepared), e.g. custom user folders, other free libraries.
- Remote credential resolve runs in UI thread (PowerShell can take 1-3 s) -> could be made async.
- EXE build (PyInstaller) - self-updater assumes a packed program folder.
- Move repo to a GitHub org "DarkMatter" if user creates one (then update GITHUB_REPO).
- Native-speaker review of fr/es/dialect translations.
