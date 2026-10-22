# Layout und Skalierung

> **Kurz:** OmniWrench läuft von kleinen Fenstern (ca. 1000 px) bis zu maximierten 8K-Monitoren, mit
> zusätzlicher Skalierung von 75 bis 300 %. Tools nutzen Layouts statt fester Größen und rechnen nichts selbst um.

**Gilt für:** OmniWrench ab Version 0.6.0

## Regeln

- Alle Größen im Code sind logische Pixel bzw. Punkt (pt). Sie wachsen mit der Skalierung automatisch mit;
  nichts selbst umrechnen.
- Layouts (`QVBoxLayout`, `QHBoxLayout`, `QGridLayout`, `QFormLayout`, `QSplitter`) statt fester Breiten.
  Mindestbreiten einer Zeile sollten zusammen unter etwa 700 px bleiben.
- Was breiter wird (viele Knöpfe, Bereiche nebeneinander), bei schmalem Fenster umbrechen oder untereinander
  anordnen. Beispiel: `_layout_filter` im
  [Subnetzrechner](https://github.com/KuroShiroMe/OmniWrench/blob/main/tools/subnet_calculator/tool.py), der den
  Splitter unter 900 px senkrecht stellt.
- Breiten für Eingabefelder besser in Zeichen (Schriftmetrik) als in Pixeln angeben.
- Selbst gezeichnete Bilder (`QPixmap`, `QImage`) in `logische Größe × sdk.device_pixel_ratio()` rendern und
  `pixmap.setDevicePixelRatio(...)` setzen, sonst werden sie bei 200–300 % unscharf.
- Dialoge mit `sdk.fit_to_screen(dialog, breite, höhe)` statt `resize()` öffnen, damit sie auch auf kleine
  Bildschirme mit hoher Skalierung passen.
- Farben nicht fest verdrahten: OmniWrench hat ein dunkles und ein helles Farbschema. Palette-Farben
  (`palette().color(...)`) oder neutrale Akzentfarben verwenden.

## Eigene Dock-Bereiche

Ein Tool darf in seinem Tab ein eigenes Qt Advanced Docking System anlegen (`PySide6QtAds.CDockManager`), z. B.
um Ergebnisse nebeneinander anzuordnen (NetProbe, MS DHCP Extended Management). Das stört das Docking des
Hauptfensters nicht.

## Testen

Das Tool bei 1000 × 640 und maximiert auf einem großen Monitor öffnen, dazu unter
*Einstellungen › Anzeige › Skalierung* 75 % und 200 % ausprobieren; außerdem beide Farbschemata.

## Siehe auch
- [Tool-Klasse und SDK](Entwicklung-Tool-Klasse-und-SDK)
