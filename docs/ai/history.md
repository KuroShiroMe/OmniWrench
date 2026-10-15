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
6. NOW: user requested (a) tool "Password Manager Manager" (connectors SecretManagement, KeePass, Netwrix Password Secure; JSON connector definitions; search only; session-only secret cache; multi-credential dropdown; auth-failure → re-login popup with save), (b) tool "Icon Store" (grid, search, filter, details panel, save-as with scaling and file types), (c) this AI documentation.
