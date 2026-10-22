# OmniWrench.exe signieren

Eine signierte EXE zeigt in Windows den Herausgeber statt „Unbekannter Herausgeber“ an und wird von
Virenscannern seltener fälschlich beanstandet. SmartScreen warnt bei einem neuen Zertifikat trotzdem
zunächst weiter: die Reputation baut sich erst über Downloads auf, auch bei EV-Zertifikaten (seit 2024
gibt es dafür keinen Sofort-Vorteil mehr).

Signiert wird nur `OmniWrench.exe`. Die mitgelieferten DLLs (Python, Qt) behalten ihre eigenen Signaturen
bzw. bleiben unsigniert; für SmartScreen zählt die gestartete EXE.

## Möglichkeiten

| Weg | Kosten | Herausgeber in der Signatur | Automatisch in GitHub | Voraussetzung |
|---|---|---|---|---|
| **SignPath Foundation** | kostenlos | „SignPath Foundation“ | ja (`SIGN_METHOD=signpath`) | Open-Source-Lizenz (OSI) im Repository, Antrag bei SignPath, Build in GitHub Actions |
| **Certum Open Source Code Signing** | ca. 49 € | „Open Source Developer, *Name*“ | nein, lokal (`SIGN_CERT_SHA1`) | Open-Source-Projekt, Ausweisprüfung; Schlüssel in der SimplySign-Cloud (Freigabe per Handy-App) |
| **Azure Artifact Signing** (früher Trusted Signing) | ca. 10 $/Monat | Firmenname | ja (`SIGN_METHOD=azure`) | in der EU nur für eingetragene Organisationen, Privatpersonen nur USA/Kanada |
| **OV-Zertifikat** einer Zertifizierungsstelle | ca. 200–500 €/Jahr | Name/Firma | nur mit Cloud-HSM-Anbindung | Schlüssel liegt seit 2023 immer auf Token oder Cloud-HSM, PFX-Export gibt es nicht mehr |
| **Firmen-PKI** (AD CS, Vorlage Codesignatur) | vorhanden | Firma | lokal (`SIGN_CERT_SHA1`) | nur für Rechner, denen das Zertifikat per GPO/Intune als vertrauenswürdiger Herausgeber verteilt wird |

**Gewählt (16.10.2026): SignPath Foundation.** Das Repository steht dafür unter der MIT-Lizenz, die README
enthält den Abschnitt „Code signing policy“.

## SignPath Foundation beantragen

### Vorher erledigen

1. **Zwei-Faktor-Anmeldung** bei GitHub einschalten (*Settings › Password and authentication*). Pflicht bei
   SignPath, später auch für das SignPath-Konto.
2. **Diesen PR mergen**, damit Lizenz und „Code signing policy“ auf `main` sichtbar sind. Das
   Antragsteam prüft die Links unten.
3. **Release 0.6.0 veröffentlichen** (`v0.6.0` ist noch nicht getaggt): `git tag v0.6.0` und
   `git push origin v0.6.0`, der Workflow **Build** erstellt das Release. SignPath signiert nur bereits
   veröffentlichte Versionen, und das Formular fragt nach der Download-Seite.

### Antragsformular: Werte zum Kopieren

Formular: [signpath.org/apply](https://signpath.org/apply). Die Fragen sind englisch, daher auch die
Antworten. Die Feldnamen können leicht abweichen; die Reihenfolge entspricht dem Formular, wie andere
Projekte es dokumentiert haben. Name und E-Mail-Adresse für Rückfragen selbst eintragen.

**Project name**
```text
OmniWrench
```

**Repository URL**
```text
https://github.com/KuroShiroMe/OmniWrench
```

**Homepage URL**
```text
https://github.com/KuroShiroMe/OmniWrench
```

**Download URL**
```text
https://github.com/KuroShiroMe/OmniWrench/releases
```

**Privacy policy URL**
```text
https://github.com/KuroShiroMe/OmniWrench#datenschutz
```

**Code signing policy URL** (falls gefragt)
```text
https://github.com/KuroShiroMe/OmniWrench#code-signing-policy
```

**License**
```text
MIT
```

**Tagline / short description**
```text
Modular, open-source admin toolbox for Windows: install admin tools from a built-in store and run them in dockable tabs.
```

**Description**
```text
OmniWrench is a modular toolbox for Windows system administrators, written in Python with PySide6 (Qt).
Tools such as an IPv4/IPv6 subnet calculator, an Active Directory user lookup, a password manager
(OmniVault) and an icon browser (IconForge) are installed from a built-in store that is a plain GitHub
repository, including their prerequisites (RSAT, PowerShell modules, winget and Python packages) after
asking the user. Credentials are stored locally in an encrypted vault (Argon2id/AES-GCM or smart card).
The Windows build is a PyInstaller program folder (OmniWrench.exe plus libraries) published as a ZIP on
GitHub Releases. It is built from source by GitHub Actions; we want to sign OmniWrench.exe so that
administrators can verify the publisher and to reduce antivirus false positives.
The program does not send telemetry. It only contacts GitHub for the tool store and update checks
(can be disabled) and the systems the user configures in a tool.
```

**Reputation**
```text
Public on GitHub since October 2026 and actively developed (several releases, the latest 0.6.0).
All releases are built from source by GitHub Actions on windows-latest; every pull request runs locale
checks, a Windows start test and the EXE build. Developed by a Windows system administrator for daily
administration work; documentation (German) in the repository: README, docs/EXE_BUILD.md,
docs/TOOL_ENTWICKLUNG.md.
```

**Maintainer type**
```text
Individual
```

**Build system**
```text
GitHub Actions
```

**Workflow / build configuration** (falls gefragt)
```text
https://github.com/KuroShiroMe/OmniWrench/blob/main/.github/workflows/build.yml
```

**Artifacts to sign** (falls gefragt)
```text
OmniWrench.exe inside the program folder that is published as OmniWrench-X.Y.Z-win64.zip
```

Bestätigungs-Häkchen (OSI-Lizenz, keine Schadsoftware, Code signing policy, Zwei-Faktor-Anmeldung usw.)
stimmen alle, sobald die Schritte unter *Vorher erledigen* erledigt sind.

Hinweis: Das Projekt ist noch jung. Die Foundation achtet auf Bekanntheit und Pflege; neue Sterne, Downloads
oder Beiträge (z. B. in Foren) vor dem Antrag oder bei Rückfragen nachtragen.

### Nach der Zusage: Werte in SignPath

| Einstellung | Wert |
|---|---|
| Project slug | `omniwrench` |
| Trusted build system | GitHub.com, Repository `KuroShiroMe/OmniWrench` |
| Signing policy slug | `release-signing` |
| Approval | manuell, Approver `KuroShiroMe` |
| Artifact configuration slug | `omniwrench-exe` (als Standard des Projekts markieren) |

Artefakt-Konfiguration zum Einfügen:

```xml
<?xml version="1.0" encoding="utf-8"?>
<artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
  <zip-file>
    <pe-file path="OmniWrench.exe" product-name="OmniWrench">
      <authenticode-sign />
    </pe-file>
  </zip-file>
</artifact-configuration>
```

Dann einen CI-Benutzer (z. B. `github-actions`) mit der Rolle *Submitter* für die Richtlinie
`release-signing` anlegen und dessen API-Token erzeugen.

### Nach der Zusage: Werte in GitHub

*Settings › Secrets and variables › Actions*:

| Typ | Name | Wert |
|---|---|---|
| Secret | `SIGNPATH_API_TOKEN` | API-Token des CI-Benutzers |
| Variable | `SIGNPATH_ORGANIZATION_ID` | Organisations-ID aus SignPath (*Settings*, GUID) |
| Variable | `SIGNPATH_PROJECT_SLUG` | `omniwrench` |
| Variable | `SIGNPATH_POLICY_SLUG` | `release-signing` |
| Variable | `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | `omniwrench-exe` |
| Variable | `SIGN_METHOD` | `signpath` |

Ab dann: Tag `vX.Y.Z` pushen → Workflow **Build** reicht die EXE bei SignPath ein → Freigabe in
SignPath → der Workflow lädt die signierte EXE und packt das ZIP. Der Workflow wartet bis zu 10 Minuten auf
die Freigabe, sonst den Lauf danach neu starten. Bis dahin bleibt `SIGN_METHOD` leer und die EXE unsigniert.

## Lokal signieren

```powershell
# Zertifikat aus dem Speicher (Smartcard, USB-Token, SimplySign Desktop, Firmen-PKI)
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Format-List Subject, Thumbprint
$env:SIGN_CERT_SHA1 = '<Fingerabdruck>'
.\.venv\Scripts\python scripts\build_exe.py --sign --zip

# oder eine vorhandene EXE nachträglich
.\.venv\Scripts\python scripts\sign_exe.py
Get-AuthenticodeSignature dist\OmniWrench\OmniWrench.exe | Format-List Status, SignerCertificate
```

`signtool.exe` gehört zum Windows SDK (Installation über den Visual Studio Installer oder
`winget install Microsoft.WindowsSDK.10.0.26100`). Alternativ `SIGN_PFX_PATH` + `SIGN_PFX_PASSWORD` für eine
PFX-Datei. Weitere Variablen stehen oben in `scripts/sign_exe.py`. Ohne Zertifikat baut `--sign` einfach
unsigniert weiter.

## In GitHub signieren

Der Workflow **Build** signiert nur bei Tags `v*` und bei manuellen Läufen (*Actions › Build ›
Run workflow*); Builds für Pull Requests und `main` bleiben unsigniert. Welcher Weg genutzt wird, steht in
der Repository-Variablen `SIGN_METHOD`. Ist sie leer, bleibt die EXE unsigniert und der Build läuft
normal durch.

Einrichtung unter *Settings › Secrets and variables › Actions*. Zugangsdaten immer als **Secret**,
Namen und Adressen als **Variable**:

**SignPath** (`SIGN_METHOD` = `signpath`): siehe *Nach der Zusage* oben.

**Azure Artifact Signing** (`SIGN_METHOD` = `azure`)
- Secrets `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` (App-Registrierung mit der Rolle
  *Artifact Signing Certificate Profile Signer* bzw. *Trusted Signing Certificate Profile Signer*)
- Variablen `AZURE_SIGNING_ENDPOINT` (z. B. `https://weu.codesigning.azure.net/`), `AZURE_SIGNING_ACCOUNT`,
  `AZURE_CERTIFICATE_PROFILE`

**PFX-Zertifikat** (`SIGN_METHOD` = `certificate`)
- Secrets `SIGN_PFX_BASE64` (`[Convert]::ToBase64String([IO.File]::ReadAllBytes('cert.pfx'))`) und
  `SIGN_PFX_PASSWORD`, optional Variable `SIGN_TIMESTAMP_URL`
- Nur für exportierbare Zertifikate, also Test- oder Firmen-PKI-Zertifikate; gekaufte OV/EV-Zertifikate
  lassen sich nicht mehr als PFX exportieren.

Der Schritt *Signatur prüfen* zeigt Status und Herausgeber im Log und bricht ab, wenn trotz `SIGN_METHOD`
keine Signatur vorhanden ist. Danach wird das ZIP aus dem signierten Programmordner gepackt.
