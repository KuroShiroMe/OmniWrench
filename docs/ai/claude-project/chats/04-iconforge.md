# Chat: IconForge

**Tool:** `gfx.iconforge` – Ordner `tools/iconforge/` (früher „Icon Store“)
Symbole aus 26 freien Bibliotheken: Lucide eingebaut (`omniwrench/resources/icons/lucide`, inkl. meta.json),
alle anderen werden bei Auswahl aus dem npm-Registry geladen (`icon_packs.json`, `packs.py`, Ablage im
Tool-Datenordner). Lizenz je Symbol mit Checkliste aus `licenses.json`. Export (SVG/PNG/ICO/PDF/JPG) in `export.py`.

**Getestet:** alle 26 Bibliotheken geladen (~118.000 Symbole), Stichproben-Rendering ohne Ausfälle.

## Start-Prompt

```text
In diesem Chat geht es um das Tool "IconForge" (tools/iconforge/) von OmniWrench.
Lies CLAUDE.md, docs/ai/decisions.md (Abschnitt Icon Store/IconForge), tools/iconforge/icon_packs.json und
tools/iconforge/licenses.json. Beschreibe kurz, wie Pakete geladen und Lizenzen angezeigt werden.
Warte dann auf meine Aufgabe.
```
