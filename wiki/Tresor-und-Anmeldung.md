# Tresor und Anmeldung

> **Kurz:** Alle Passwörter, Tokens und Zugangsdaten liegen verschlüsselt in einem Tresor. Geöffnet wird er mit
> dem Masterpasswort oder einem Zertifikat (Smartcard). Ohne Anmeldung startet OmniWrench nicht.

**Gilt für:** Hauptprogramm ab Version 0.7.0 · Windows (Passwort und Zertifikat), Linux (Passwort)

## Inhalt
- [Anmeldemethoden](#anmeldemethoden)
- [Anmelden](#anmelden)
- [Sperren](#sperren)
- [Methoden ändern](#methoden-ändern)
- [Passwort vergessen](#passwort-vergessen)
- [Wie die Verschlüsselung funktioniert](#wie-die-verschlüsselung-funktioniert)
- [Häufige Fragen](#häufige-fragen)

## Anmeldemethoden

| Methode | Plattform | Hinweis |
|---|---|---|
| Masterpasswort | Windows, Linux | mindestens 8 Zeichen |
| Benutzerzertifikat | Windows | RSA-Zertifikat mit privatem Schlüssel aus `Cert:\CurrentUser\My`, z. B. Smartcard oder virtuelle Smartcard; PIN-Abfrage über Windows |

Beide Methoden lassen sich kombinieren; jede für sich öffnet den Tresor. Eingerichtet wird beim ersten Start
([Erste Schritte](Erste-Schritte)), geändert unter *Einstellungen › Sicherheit*.

Reine Signaturzertifikate (z. B. Intune-Gerätezertifikate) erscheinen nicht in der Auswahl, weil sie nicht
entschlüsseln können.

## Anmelden

![Anmeldung](images/hauptprogramm-anmeldung.png)

- Masterpasswort eingeben und **Anmelden**, oder
- **Mit Zertifikat anmelden: ‹Name›** wählen. Bei einer Smartcard fragt Windows nach der PIN.

Der Tooltip des Zertifikatknopfs zeigt Antragsteller, Fingerabdruck und Ablaufdatum.

## Sperren

- `Strg+L` oder *Datei › Sperren* sperrt sofort.
- *Einstellungen › Allgemein › Automatisch sperren nach* sperrt nach einer Zeit ohne Bedienung.

Beim Sperren verwirft OmniWrench alle Passwörter, die es für die Sitzung aus externen Passwortmanagern geholt hat.
Geöffnete Tabs bleiben bestehen; nach der Anmeldung geht es dort weiter.

## Methoden ändern

Unter *Einstellungen › Sicherheit*:
- **Masterpasswort setzen/ändern …**: legt ein neues Passwort fest. Der Tresor bleibt dabei erhalten.
- **Zertifikat hinzufügen …**: z. B. nach dem Tausch der Smartcard.
- Methode markieren und entfernen (mindestens eine muss bleiben).

## Passwort vergessen

Das Masterpasswort lässt sich nicht wiederherstellen. Auf der Anmeldung führt **Passwort vergessen?** zum
Zurücksetzen:

1. Neues Masterpasswort zweimal eingeben.
2. Den Haken **„Gespeicherte Passwörter unwiderruflich löschen“** setzen.
3. **Zurücksetzen**.

Was dabei passiert:

- **Alle gespeicherten Geheimnisse werden gelöscht:** Passwörter im Passwortmanager, Zugangsdaten der Tools,
  Anmeldedaten der Passwortmanager-Konnektoren, GitHub-Token, Zertifikat-Anmeldungen.
- **Alle Einträge bleiben erhalten** (Namen, Benutzernamen, Verknüpfungen, Konnektoren). Bei jedem fehlenden
  Passwort steht ein ❗. Der Zugang funktioniert wieder, sobald das Passwort neu eingetragen ist.
- Die alte Tresordatei bleibt als Sicherung `vault.before-reset-‹Zeitpunkt›.json` liegen.

Die Liste der Einträge wird beim Speichern zusätzlich ohne Passwörter abgelegt und an das Benutzerkonto gebunden
(unter Windows per DPAPI). Deshalb gelingt das Zurücksetzen mit Einträgen nur im selben Benutzerkonto. Ist diese
Kopie nicht lesbar, funktioniert das Zurücksetzen trotzdem, der Passwortmanager ist danach aber leer.

## Wie die Verschlüsselung funktioniert

- Die Daten im Tresor werden mit einem zufälligen Schlüssel mit **AES-256-GCM** verschlüsselt.
- Dieser Schlüssel wird für jede Anmeldemethode einzeln „eingepackt“:
  - Masterpasswort: Schlüsselableitung mit **Argon2id**, dann AES-GCM
  - Zertifikat: **RSA-OAEP** mit dem öffentlichen Schlüssel des Zertifikats; nur der private Schlüssel
    (z. B. auf der Smartcard) kann ihn wieder auspacken
- Es wird **kein Passwort-Hash** gespeichert. Ob ein Passwort stimmt, zeigt allein die erfolgreiche Entschlüsselung.
- Nach der Anmeldung liegt der Schlüssel nur im Arbeitsspeicher.

Die Tresordatei `vault.json` liegt im Benutzerprofil (siehe [Datenablage](Datenablage-und-Datenschutz)).

## Häufige Fragen

**Kann ich den Tresor auf einen anderen Rechner mitnehmen?**
Ja: den Datenordner kopieren und dort mit dem Masterpasswort öffnen. Zertifikat-Anmeldungen funktionieren,
wenn das Zertifikat dort ebenfalls vorhanden ist. „Passwort vergessen“ mit Einträgen geht nur im ursprünglichen
Benutzerkonto.

**Teilen sich Benutzer eines Rechners einen Tresor?**
Nein. Jeder Benutzer hat seinen eigenen Tresor im eigenen Profil.

**Was passiert, wenn die Smartcard verloren geht?**
Mit dem Masterpasswort anmelden (falls eingerichtet) und das neue Zertifikat hinzufügen. Ohne Passwort bleibt nur
[Passwort vergessen](#passwort-vergessen).

## Siehe auch
- [Passwortmanager](Passwortmanager)
- [Einstellungen › Sicherheit](Einstellungen#sicherheit)
