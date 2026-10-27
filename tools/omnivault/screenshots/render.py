"""Screenshots für Store und Home (scripts/render_screenshots.py) - Beispieleinträge, keine echten Manager."""

from omniwrench.core import credentials
from omniwrench.core.credentials import Credential, SearchResult

LOCAL = [
    ("Domain admin (tier 0)", "CONTOSO\\adm-t0-jbauer"), ("DHCP service account", "CONTOSO\\svc-dhcp"),
    ("SQL server sa", "sa"), ("Firewall HQ", "admin"), ("vCenter", "administrator@vsphere.local"),
    ("Switch stack core", "netadmin"), ("Backup repository", "CONTOSO\\svc-backup"),
    ("Intune enrollment", "enroll@contoso.example"),
]
CONNECTORS = [("keepass", "KeePass – IT team"), ("bitwarden", "Vaultwarden"),
              ("hashicorp_vault", "HashiCorp Vault – Production")]
FOUND = [
    ("SQL server sa", "sa", "OmniWrench"), ("SQL reporting service", "CONTOSO\\svc-sqlrs", "KeePass – IT team"),
    ("SQL cluster admin", "CONTOSO\\adm-sql", "KeePass – IT team"),
    ("secret/db/sql-prod-01", "dbadmin", "HashiCorp Vault – Production"),
    ("secret/db/sql-prod-02", "dbadmin", "HashiCorp Vault – Production"),
    ("SQL Server Management (Azure)", "sqladmin@contoso.example", "Vaultwarden"),
]


def render(shot):
    local = credentials.manager().local
    for name, user in LOCAL:
        local.add(name, user, "example-password")
    connectors = shot.module("connectors")
    tool, _ = shot.create()
    for type_id, name in CONNECTORS:
        tool.store.save(connectors.ConnectorConfig(f"demo{type_id[:6]}", type_id, name))
    tool._fill_sources()
    shot.wait(0.3)
    shot.save("manager")

    tool.sources.setCurrentRow(0)  # alle Quellen durchsuchen
    tool.query.blockSignals(True)
    tool.query.setText("sql")
    tool.query.blockSignals(False)
    tool._generation += 1  # laufende Suche verwerfen, Beispielergebnis zeigen
    shot.wait(0.3)
    tool._generation += 1
    items = [Credential(f"x{i}", n, u, source=src) for i, (n, u, src) in enumerate(FOUND)]
    tool._show(SearchResult(items, {}, []))
    tool.table.selectRow(3)
    shot.save("search")

    dialog = shot.module("tool").ConnectorDialog(tool, None)
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData("hashicorp_vault"))
    dialog.name.setText("HashiCorp Vault – Production")
    for key, value in (("address", "https://vault.contoso.example:8200"), ("mount", "secret"), ("path", "db")):
        widget = dialog.inputs[key].widget if key in dialog.inputs else None
        if hasattr(widget, "setText"):
            widget.setText(value)
    shot.save_dialog("connector", dialog)
