# DHCP-API-Prüfung (Entwicklung, läuft unter Linux)

Prüft `tools/ms_dhcp_extended/dhcpapi.py` ohne Windows:

1. Strukturen und Signaturen gegen die offiziellen Win32-Metadaten:
   ```
   curl -o dhcp_sys.rs https://raw.githubusercontent.com/microsoft/windows-rs/0.52.0/crates/libs/sys/src/Windows/Win32/NetworkManagement/Dhcp/mod.rs
   python3 verify_api.py dhcp_sys.rs     # erwartet: nur DHCP_ATTRIB (anonyme Union) als Namensabweichung
   ```
2. Abläufe gegen eine Fake-dhcpsapi (gleiche Layouts, Testdaten):
   ```
   gcc -shared -fPIC -o libfake.so fake_dhcpsapi.c
   python3 test_api.py ./libfake.so
   python3 test_tx.py                    # Transaktionen: Fehler mitten im Ablauf, Rücknahme, Abbruch
   ```
