# Eigenes Tool-Repository

> **Kurz:** Ein Tool-Repository enthält die Quellen der Tools (`tools/`), ihre Doku (`docs/`) und den daraus
> gebauten Store (`store/index.json` + ZIP-Pakete). OmniWrench liest nur `store/index.json`. Am einfachsten
> entsteht es aus der [Vorlage](Entwicklung-Vorlagen-Repository).

**Gilt für:** OmniWrench ab Version 0.7.0

## Inhalt
- [Aufbau](#aufbau)
- [Der Store: index.json](#der-store-indexjson)
- [Store bauen](#store-bauen)
- [Versionen und Updates](#versionen-und-updates)
- [Hosting-Varianten](#hosting-varianten)
- [Mehrere Tools, mehrere Repositories](#mehrere-tools-mehrere-repositories)

## Aufbau

```
mein-repo/
├── tools/
│   ├── dns_cleanup/          ein Ordner je Tool (Paketformat)
│   └── gpo_report/
├── docs/
│   ├── Tool-DNS-Cleanup.md   Doku je Tool nach der Vorlage für Tool-Seiten
│   └── Tool-GPO-Report.md
├── store/                    automatisch gebaut, nicht von Hand ändern
│   ├── index.json
│   └── packages/
│       ├── contoso.dns-cleanup-1.2.0.zip
│       └── contoso.gpo-report-0.3.1.zip
├── scripts/                  store.py, new_tool.py (aus der Vorlage)
├── .github/workflows/        Store-Workflow (aus der Vorlage)
├── README.md                 Store-URL und Tool-Liste
└── LICENSE
```

Eine eigene Lizenz ist wichtig, wenn andere die Tools nutzen sollen; die Vorlage bringt MIT mit.

## Der Store: index.json

```json
{
  "format": 1,
  "name": "Contoso Store",
  "generated": "2026-10-22T12:00:00+00:00",
  "tools": [
    {
      "id": "contoso.dns-cleanup",
      "name": "DNS Cleanup",
      "version": "1.2.0",
      "...": "alle Felder aus tool.json",
      "translations": {"de": {"name": "DNS-Bereinigung", "description": "…"}},
      "download_url": "packages/contoso.dns-cleanup-1.2.0.zip",
      "sha256": "…",
      "size": 12345
    }
  ]
}
```

- `download_url` ist relativ zur `index.json` oder absolut (z. B. ein Release-Asset).
- OmniWrench prüft nach dem Download die SHA-256-Prüfsumme.
- `translations` kommen aus den `tool.*`-Schlüsseln der Sprachdateien, damit der Store Namen und Beschreibungen
  übersetzt anzeigt, bevor das Tool installiert ist.
- Eigene Bilddateien als Symbol werden als `icon_data` eingebettet.

## Store bauen

Mit der Vorlage: `python scripts/store.py build` (lokal) bzw. automatisch per Workflow bei jedem Push auf `main`.
Das Skript

- prüft jedes Tool (Pflichtdateien, `tool.json`, `config.json`, Einstiegsmodul),
- packt nur Tools, die neu sind oder eine neue Version haben (unveränderte Pakete behalten ihre Prüfsumme),
- bricht ab, wenn ein Tool geändert wurde, ohne die Version zu erhöhen, oder wenn eine Version kleiner wird,
- entfernt Pakete gelöschter Tools und alter Versionen.

`python scripts/store.py check` macht dieselben Prüfungen, ohne zu schreiben.

Ohne Vorlage geht es auch mit dem Skript aus OmniWrench:
`python <OmniWrench>/scripts/build_store.py --tools tools --out store` (baut immer alle Pakete neu).

## Versionen und Updates

- Clients vergleichen die installierte Version mit der im Store. Nur eine **höhere** Version gilt als Update.
- Ablauf: Code ändern → `version` erhöhen → pushen → Store wird gebaut → Clients melden das Update beim
  nächsten Start (oder installieren es automatisch, wenn eingestellt).
- Neue Voraussetzungen (z. B. ein weiteres RSAT-Paket) verhindern ein automatisches Hintergrund-Update; der
  Benutzer bestätigt sie beim Aktualisieren.
- Ein Tool zurückziehen: Ordner löschen und pushen. Installierte Kopien bleiben, bekommen aber keine Updates mehr.

## Hosting-Varianten

| Variante | Store-URL | Hinweis |
|---|---|---|
| Öffentliches GitHub-Repository | `https://raw.githubusercontent.com/<besitzer>/<repo>/main/store/index.json` | Standard, kein Token nötig |
| Privates GitHub-Repository | wie oben | jeder Client braucht ein GitHub-Token mit Lesezugriff |
| Dateifreigabe im Firmennetz | `\\server\freigabe\omniwrench-store\index.json` | Ordner `store/` dorthin kopieren; ohne Internet |
| Webserver / Intranet | `https://intranet.contoso.local/omniwrench/index.json` | Ordner `store/` veröffentlichen; Zertifikat muss im Windows-Zertifikatspeicher vertrauenswürdig sein |

Die Pakete werden relativ zur `index.json` gesucht; der Ordner `store/` muss also vollständig mitkopiert werden.

## Mehrere Tools, mehrere Repositories

- Ein Repository kann beliebig viele Tools enthalten.
- Kommt dieselbe Tool-ID in mehreren Repositories vor, nimmt OmniWrench die höchste Version. IDs daher mit
  eigenem Präfix versehen (`contoso.…`), nie die IDs fremder Tools verwenden.
- Bereiche und Tags sind repository-übergreifend; eigene Bereiche nur, wenn kein fester passt.

## Siehe auch
- [Vorlagen-Repository](Entwicklung-Vorlagen-Repository)
- [Repository einbinden](Entwicklung-Repository-einbinden)
- [Testen und veröffentlichen](Entwicklung-Testen-und-Veroeffentlichen)
