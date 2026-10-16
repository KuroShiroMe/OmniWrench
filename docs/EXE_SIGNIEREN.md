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

Voraussetzungen der [SignPath Foundation](https://signpath.org/terms), die OmniWrench schon erfüllt:
OSI-Lizenz (MIT), nur eigener Quellcode plus freie Bibliotheken, aktiv gepflegt, automatischer Build aus
dem Repository (GitHub Actions), Produktname und Version in der EXE (`version_info.txt`), Abschnitt
„Code signing policy“ mit Rollen und Datenschutzhinweis in der README.

Noch zu tun:
1. **Zwei-Faktor-Anmeldung** bei GitHub einschalten (Pflicht für alle Beteiligten, auch später bei SignPath).
2. **Release veröffentlichen**, das signiert werden soll: SignPath signiert nur bereits veröffentlichte
   Versionen, d. h. erst Tag/Release `vX.Y.Z`, dann signierter Build.
3. **Antrag stellen** über das Formular auf [signpath.org](https://signpath.org) (Projekt-URL, Lizenz,
   Download-Seite = GitHub Releases, Link auf die Code signing policy in der README).
4. Nach der Zusage in SignPath: GitHub-Repository als Quelle verbinden (GitHub-App *SignPath*), Projekt
   `omniwrench` mit Signierrichtlinie `release-signing` und der Artefakt-Konfiguration unten anlegen,
   CI-Benutzer mit API-Token (Rolle *Submitter*) erstellen.
5. In GitHub die Variablen und das Secret aus dem Abschnitt **SignPath** unten eintragen und
   `SIGN_METHOD` = `signpath` setzen.
6. Ab dann: Tag `vX.Y.Z` pushen → Workflow **EXE-Build** reicht die EXE bei SignPath ein → die Freigabe
   erfolgt dort manuell (Approver) → der Workflow lädt die signierte EXE und packt das ZIP.

Jede Signierung muss in SignPath von Hand freigegeben werden. Der Workflow wartet darauf bis zu
10 Minuten; danach den Lauf nach der Freigabe neu starten.

Bis zur Zusage bleibt `SIGN_METHOD` leer, die EXE wird unsigniert gebaut.

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

Der Workflow **EXE-Build** signiert nur bei Tags `v*` und bei manuellen Läufen (*Actions › EXE-Build ›
Run workflow*); Builds für Pull Requests und `main` bleiben unsigniert. Welcher Weg genutzt wird, steht in
der Repository-Variablen `SIGN_METHOD`. Ist sie leer, bleibt die EXE unsigniert und der Build läuft
normal durch.

Einrichtung unter *Settings › Secrets and variables › Actions*. Zugangsdaten immer als **Secret**,
Namen und Adressen als **Variable**:

**SignPath** (`SIGN_METHOD` = `signpath`)
- Secret `SIGNPATH_API_TOKEN` (Token eines CI-Benutzers in SignPath, Rolle *Submitter*)
- Variablen `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_POLICY_SLUG`
  (z. B. `release-signing`), optional `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG`
- In SignPath das Repository als vertrauenswürdiges GitHub-Projekt verbinden und als Artefakt-Konfiguration
  den Programmordner angeben (das GitHub-Artefakt ist ein ZIP mit dem Inhalt von `dist\OmniWrench`):

  ```xml
  <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
    <zip-file>
      <pe-file path="OmniWrench.exe">
        <authenticode-sign />
      </pe-file>
    </zip-file>
  </artifact-configuration>
  ```

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
