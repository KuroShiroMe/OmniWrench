# Installation

> **Kurz:** Unter [Releases](https://github.com/KuroShiroMe/OmniWrench/releases/latest) das passende Paket
> laden. Windows: `…-win64-setup.exe` ausführen. Linux: `sudo apt install ./omniwrench_…_amd64.deb`.
> Python muss nicht installiert sein.

**Gilt für:** Hauptprogramm ab Version 0.7.0 · Windows 10/11 (64 Bit), Linux x86_64

## Inhalt
- [Systemanforderungen](#systemanforderungen)
- [Welches Paket?](#welches-paket)
- [Windows: Installationsprogramm](#windows-installationsprogramm)
- [Windows: Stille Installation (Intune, SCCM …)](#windows-stille-installation)
- [Windows: Portable Version](#windows-portable-version)
- [Linux: Debian-Paket](#linux-debian-paket)
- [Linux: Portable Version](#linux-portable-version)
- [Updates](#updates)
- [Deinstallation](#deinstallation)
- [Aus dem Quellcode starten](#aus-dem-quellcode-starten)
- [Probleme bei der Installation](#probleme-bei-der-installation)

## Systemanforderungen

| | Windows | Linux |
|---|---|---|
| System | Windows 10 oder 11, 64 Bit (Clients) | x86_64 mit glibc 2.35 oder neuer (z. B. Ubuntu 22.04+, Debian 12+, Linux Mint 21+) |
| Rechte | Installationsprogramm: Administrator (UAC); portabel: keine | .deb: `sudo`; portabel: keine |
| Speicher | ca. 300 MB plus installierte Tools | ca. 300 MB plus installierte Tools |
| Netzwerk | Zugriff auf `github.com`, `raw.githubusercontent.com`, `api.github.com` für Store und Updates | wie Windows |

**Windows Server** wird nicht unterstützt. OmniWrench startet dort, zeigt aber auf der Startseite einen Hinweis;
einige Funktionen (z. B. die automatische Installation von RSAT) sind eingeschränkt.

Unter **Linux** laufen nur Tools, die Linux unterstützen. Der Store kennzeichnet die übrigen mit
„Läuft nur unter Windows“ (siehe [Tools](Tools)). Die Anmeldung per Zertifikat/Smartcard gibt es nur unter
Windows; unter Linux dient das Masterpasswort.

## Welches Paket?

Alle Pakete liegen unter [Releases](https://github.com/KuroShiroMe/OmniWrench/releases/latest).
`X.Y.Z` steht für die Versionsnummer.

| System | Installationsprogramm (empfohlen) | Portable Version (ohne Installation) |
|---|---|---|
| Windows 10/11 | `OmniWrench-X.Y.Z-win64-setup.exe` | `OmniWrench-X.Y.Z-win64.zip` |
| Linux | `omniwrench_X.Y.Z_amd64.deb` (Debian, Ubuntu, Mint …) | `OmniWrench-X.Y.Z-linux-x86_64.tar.gz` |

Daneben gibt es `OmniWrench-X.Y.Z.zip` (Quellcode) und `linkagent.exe` (Mini-Tool für den Leitungstest von
[NetProbe](Tool-NetProbe), nicht für OmniWrench selbst nötig).

**Installationsprogramm oder portabel?**
- Das **Installationsprogramm** legt OmniWrench in den Programmordner, erstellt Startmenü-Einträge, erscheint
  in der Softwareverwaltung und aktualisiert sich über denselben Weg. Für den normalen Arbeitsplatz die richtige Wahl.
- Die **portable Version** läuft aus einem beliebigen Ordner ohne Installation und ohne Adminrechte, z. B. von
  einem USB-Stick oder auf Rechnern, auf denen nichts installiert werden darf.

In beiden Fällen liegen Einstellungen, Tresor und Tools im Benutzerprofil (siehe
[Datenablage](Datenablage-und-Datenschutz)). Wer alles auf dem Stick haben möchte, legt neben dem Programm
einen Ordner `portable-data` an.

## Windows: Installationsprogramm

1. `OmniWrench-X.Y.Z-win64-setup.exe` herunterladen und starten.
2. Die Abfrage der Benutzerkontensteuerung (UAC) bestätigen.
3. Dem Assistenten folgen. Optional lässt sich eine Desktop-Verknüpfung anlegen (standardmäßig aus).
4. Am Ende OmniWrench starten und den [Tresor einrichten](Erste-Schritte).

Ergebnis:
- Programmordner `C:\Program Files\KuroShiro\OmniWrench` (bis Version 0.7.x: `…\DarkMatter\OmniWrench`; das Setup
  zieht eine alte Installation beim Update automatisch um)
- Eintrag im Startmenü, optional auf dem Desktop
- Deinstallation über *Einstellungen › Apps › Installierte Apps*

**SmartScreen-Warnung:** Die Programmdateien sind derzeit nicht signiert. Windows SmartScreen kann deshalb beim
ersten Start warnen. Über *Weitere Informationen › Trotzdem ausführen* geht es weiter. Alle Pakete werden
automatisch und nachvollziehbar mit GitHub Actions aus diesem Repository gebaut.

Läuft OmniWrench während der Installation, wartet das Setup, bis es beendet wurde (bei stiller Installation
höchstens 60 Sekunden).

## Windows: Stille Installation

Für Softwareverteilung (Intune, SCCM/ConfigMgr, PDQ, Skripte):

```bat
OmniWrench-X.Y.Z-win64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

| Parameter | Wirkung |
|---|---|
| `/VERYSILENT` | keine Fenster |
| `/SUPPRESSMSGBOXES` | keine Rückfragen |
| `/NORESTART` | nie neu starten |
| `/TASKS="desktopicon"` | zusätzlich Desktop-Verknüpfung anlegen |
| `/LOG="C:\Temp\omniwrench-setup.log"` | Installationsprotokoll schreiben |

Stille Deinstallation:

```bat
"C:\Program Files\KuroShiro\OmniWrench\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

Für Intune als Win32-App (`.intunewin`): Installationsbefehl wie oben, Deinstallationsbefehl wie oben,
Erkennungsregel z. B. Datei `C:\Program Files\KuroShiro\OmniWrench\OmniWrench.exe` vorhanden.
Installiert wird für das Gerät (alle Benutzer); jeder Benutzer richtet beim ersten Start seinen eigenen Tresor ein.

Ein Update wird genauso installiert wie die Erstinstallation; die Daten der Benutzer bleiben unberührt.

## Windows: Portable Version

1. `OmniWrench-X.Y.Z-win64.zip` herunterladen.
2. Entpacken, z. B. nach `C:\Tools` oder auf einen USB-Stick. Es entsteht der Ordner `OmniWrench`.
3. `OmniWrench\OmniWrench.exe` starten.

Keine Adminrechte nötig. Die portable Version aktualisiert sich selbst, indem sie ihre Dateien ersetzt. Liegt sie
in einem schreibgeschützten Ordner, fragt sie dafür nach Administratorrechten.

## Linux: Debian-Paket

```bash
sudo apt install ./omniwrench_X.Y.Z_amd64.deb
```

- installiert nach `/opt/omniwrench`, mit dem Befehl `omniwrench` und einem Eintrag im Anwendungsmenü
- `apt` installiert die nötigen Qt-Systembibliotheken automatisch mit
- Entfernen: `sudo apt remove omniwrench`

Andere Distributionen (Fedora, openSUSE, Arch …) nutzen die portable Version. Ein rpm-Paket gibt es bei Bedarf.

## Linux: Portable Version

```bash
tar -xzf OmniWrench-X.Y.Z-linux-x86_64.tar.gz
./OmniWrench/OmniWrench
```

Benötigt die Qt-Systembibliotheken. Unter Debian/Ubuntu:

```bash
sudo apt install libegl1 libxkbcommon-x11-0 libxcb-cursor0
```

Unter Fedora entsprechend `libglvnd-egl libxkbcommon-x11 xcb-util-cursor`.

## Updates

OmniWrench prüft beim Start, ob es eine neue Version gibt (abschaltbar unter
*Extras › Einstellungen › Updates*), und von Hand über *Extras › Nach Updates suchen*. Ein Fenster zeigt die
Versionshinweise mit den Knöpfen **Jetzt installieren**, **Release-Seite öffnen** und **Später**.

„Jetzt installieren“ lädt automatisch das passende Paket:

| Installationsart | Ablauf |
|---|---|
| Windows-Setup | lädt das neue Setup und führt es still aus (eine UAC-Abfrage), danach startet OmniWrench neu |
| Linux-.deb | lädt das Paket und installiert es mit `pkexec apt-get` (Passwortabfrage) |
| Portabel (Windows/Linux) | lädt das Archiv, ersetzt nach dem Beenden die Programmdateien und startet neu |

Einstellungen, Tresor und installierte Tools bleiben bei Updates erhalten. Wie Tools aktualisiert werden,
steht unter [Store und Tools](Store-und-Tools#updates).

**Vorabversionen** (Beta) erscheinen nur, wenn unter *Einstellungen › Updates* „Vorabversionen berücksichtigen“
eingeschaltet ist.

## Deinstallation

| Installationsart | Deinstallation |
|---|---|
| Windows-Setup | *Einstellungen › Apps* oder still mit `unins000.exe` (siehe oben) |
| Windows portabel | Ordner löschen |
| Linux-.deb | `sudo apt remove omniwrench` |
| Linux portabel | Ordner löschen |

Die Deinstallation lässt die **Benutzerdaten bewusst stehen** (Tresor, Einstellungen, Tools), damit nichts
verloren geht. Wer OmniWrench restlos entfernen will, löscht zusätzlich die Ordner aus
[Datenablage](Datenablage-und-Datenschutz#wo-liegen-die-daten).

## Aus dem Quellcode starten

Für Entwicklung und Tests. Voraussetzung: Python 3.14.

```powershell
git clone https://github.com/KuroShiroMe/OmniWrench.git
cd OmniWrench
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt     # Linux: .venv/bin/pip
.\.venv\Scripts\python main.py
```

Aus dem Quellcode zeigt der Store zusätzlich den lokal gebauten Store im Ordner `store/`.
Mehr dazu im [Entwicklerbereich](Entwicklung).

## Probleme bei der Installation

| Problem | Lösung |
|---|---|
| SmartScreen blockiert den Start | *Weitere Informationen › Trotzdem ausführen* (Programm ist nicht signiert) |
| Setup meldet, dass OmniWrench noch läuft | OmniWrench beenden (auch im Infobereich prüfen) und erneut versuchen |
| Linux: `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"` | Qt-Systembibliotheken nachinstallieren (siehe [Portable Version](#linux-portable-version)) |
| Linux: Update meldet „pkexec fehlt“ | Paket von Hand installieren: `sudo apt install ./omniwrench_X.Y.Z_amd64.deb` |
| Update meldet „Programmordner schreibgeschützt“ | Paket von der Release-Seite laden und von Hand entpacken bzw. installieren |
| Firmen-Proxy mit TLS-Prüfung | OmniWrench nutzt den Windows-Zertifikatspeicher; das Proxy-Zertifikat muss dort vertrauenswürdig sein |

Weitere Hilfe: [Fehlerbehebung](Fehlerbehebung).

## Siehe auch
- [Erste Schritte](Erste-Schritte)
- [Datenablage und Datenschutz](Datenablage-und-Datenschutz)
- [Store und Tools](Store-und-Tools)
