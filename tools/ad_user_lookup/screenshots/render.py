"""Screenshots für Store und Home (scripts/render_screenshots.py) - Beispieldaten statt Active Directory."""

from PySide6.QtCore import Qt

GROUPS = ["Domain Users", "GG_Sales_Munich", "GG_VPN_Users", "GG_M365_E3", "GG_Printers_HQ"]
USERS = [
    ("j.becker", "Julia Becker", True, False, "2026-10-27 07:58", "Sales", "Account Manager"),
    ("j.berger", "Jonas Berger", True, True, "2026-10-24 16:12", "Finance", "Controller"),
    ("j.bauer", "Jana Bauer", True, False, "2026-10-26 18:40", "IT", "System Administrator"),
    ("j.brandt", "Jan Brandt", False, False, "2026-06-30 11:05", "Logistics", "Dispatcher"),
    ("j.baumann", "Johanna Baumann", True, False, "2026-10-27 08:11", "HR", "HR Business Partner"),
    ("j.busch", "Jakob Busch", True, False, "2026-10-25 09:47", "Sales", "Inside Sales"),
    ("j.beck", "Jessica Beck", True, False, "2026-10-27 06:55", "Marketing", "Content Manager"),
]


def _users():
    result = []
    for sam, name, enabled, locked, last, dept, title in USERS:
        result.append({
            "SamAccountName": sam, "Name": name, "Enabled": enabled, "LockedOut": locked, "LastLogonDate": last,
            "mail": f"{sam.replace('.', '.')}@contoso.example", "Department": dept, "Title": title,
            "DistinguishedName": f"CN={name},OU={dept},OU=Users,OU=HQ,DC=contoso,DC=example",
            "whenCreated": "2023-04-03", "PasswordLastSet": "2026-09-14 08:02",
            "MemberOf": GROUPS[:3] + [f"GG_{dept}"],
        })
    return result


def render(shot):
    tool, _ = shot.create()
    tool.query.setText("j.b")
    tool._show_results(_users())
    tool.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    _select(tool, "j.becker")
    shot.save("search")

    _select(tool, "j.berger")  # gesperrtes Konto
    shot.save("details")


def _select(tool, sam):
    for row in range(tool.table.rowCount()):
        if tool.table.item(row, 0).text() == sam:
            tool.table.selectRow(row)
