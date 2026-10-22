# Vorlagen

| Ordner | Inhalt |
|---|---|
| [`tool-repo/`](tool-repo) | Inhalt des Vorlagen-Repositorys **KuroShiroMe/OmniWrench-Tool-Template** für eigene Tool-Repositories |

## tool-repo → OmniWrench-Tool-Template

Der Ordner ist die Quelle des GitHub-Vorlagen-Repositorys. Einrichten (einmalig, durch die Repo-Besitzerin):

1. Auf GitHub ein öffentliches Repository `OmniWrench-Tool-Template` anlegen (ohne README).
2. Den **Inhalt** von `templates/tool-repo/` (inkl. `.github/`, `.gitignore`, `.gitattributes`) hineinkopieren und pushen:
   ```bash
   cp -r templates/tool-repo/. ../OmniWrench-Tool-Template/
   cd ../OmniWrench-Tool-Template && git add -A && git commit -m "Vorlage" && git push
   ```
3. *Settings › General* → Haken **Template repository** setzen.

Danach erscheint auf der Repo-Seite **Use this template**. Ein daraus erzeugtes Repository richtet sich mit dem
Workflow „Vorlage einrichten“ selbst ein (Platzhalter, erstes Tool, Store).

Änderungen an der Vorlage hier pflegen und ins Vorlagen-Repository übernehmen (Schritt 2).
Beschreibung für Nutzer: [Wiki › Vorlagen-Repository](https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung-Vorlagen-Repository).
