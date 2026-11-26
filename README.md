# Rim Generator – Blender-Add-on

Aus einem Felgenfoto (Frontansicht) werden in Sekunden **vier Räder mit Reifen** in Blender.

## Installation (Blender 3.6, Intel-Mac)
1. ZIP über *Edit → Preferences → Add-ons → Install…* installieren, Haken bei **Rim Generator** setzen.
2. Blender mit Cmd+Q neu starten. Seitenleiste `N` → Reiter **Rim Generator**.
3. Optional: **KI-Tiefe einrichten** (einmalig, lokal, ~400 MB) – verbessert die Erkennung.

## Bedienung – zwei Reiter in der Seitenleiste (N)
**Reiter „2D to 3D Rim“** – Felge aus einem Foto
1. **Felgenbild laden & bauen** (JPG/PNG, möglichst gerade von vorn)
2. **Schnitt: Tiefe und Bombierung** – exakte Standardkurve; mittleren Punkt (Schwerpunkt) und weitere Punkte ziehen, +/− Punkt, Weich/Knick, dann **Refresh**. Versatz Mitte/Außenring unter *Aussehen* liegen als Offsets auf der Kurve

**Reiter „Package“** – vier Räder mit Reifen und Bremsen
1. Felge wählen: *Generierte Felge* (aus Reiter 1) oder *Eigene Felge* (Picker für eine beliebige Collection, z.B. importierte FBX) – eigene Felgen werden nicht verändert, nur gleichmäßig skaliert und in den Reifen gesetzt
2. Radstand, Spurweiten, **Zoll vorn/hinten** einstellen, **4 Räder erzeugen**
3. Bremse: echtes 3D (belüftete Scheibe, Sattel mit Brücke/Belägen/Schrauben), Foto als Textur; Regler **Sattelposition** (0° oben, 90° hinten, Standard 45°)

## Kompatibilität
Getestet (headless): Blender 4.5 LTS und **5.3** (Python 3.13); Ziel: ein ZIP für Blender 3.5 (Intel-Mac) bis 5.x (3.x bisher nicht getestet, kein bpy 3.x verfügbar), macOS, Windows, Linux.
KI-Tiefe: onnxruntime wird je nach Python-Version gewählt (3.13: 1.22; älter: 1.19.2 universal2).

## Bearbeitbare Geometrie statt KI-Mesh (nur Blender 5.3)
Im Reiter *2D to 3D Rim* wählst du **Ergebnis: Bearbeitbare Geometrie (SubD)** oder **KI-Mesh (Textur)**. Die bearbeitbare Variante entsteht direkt aus dem Foto:
grober Käfig (Musterspeiche = ein Sektor) + Subdivision Surface + Creases, instanziert auf die erkannte Speichenzahl. Käfigpunkte im Edit Mode ziehen,
Creases mit Shift+E setzen; Regler *Unterteilung* und *Kantenschärfe* im Panel.

## Parametrische Felge (nur Blender 5.3)
Zu jedem Bild entsteht in der Collection `Felge_01`, `Felge_02` … zusätzlich zum (ausgeblendeten) KI-Mesh eine saubere Quad-Felge (Geometry Nodes).
Im Panel *Parametrische Felge*: Konkavität-Slider, Kurven-Editor (Tiefe über dem Radius), Speichen/Nabe/Bett, Diamond Cut mit zwei Farben,
Diamond Cut = **Teller**: Bezier-Kurve „Teller-Kurve“ (3 Punkte, Maßstab 1:1, *Teller-Kurve bearbeiten*); die polierte Fläche liegt exakt auf der Drehfläche, schwarze Flächen „Rücksprung“ mm dahinter, Crease-Kante dazwischen,
*Aus KI-Mesh neu ableiten*, *Anwenden* (Modifier festschreiben). *Felgen vergleichen* schaltet zwischen den Collections um.
Die Musterspeiche (Pizzastück) liegt als Objekt in der Collection: *Muster zum Bearbeiten anwenden* → Edit Mode, alle Speichen und alle vier Räder folgen live.
*Als neue Variante speichern* kopiert alles nach `Felge_01_v2`. Optional: Mesh-Quelle *Cloud-API* (Key nur in den Preferences, kostenpflichtig): *Meshy* (Image to 3D nur Mesh, optional Multi-Image/Remesh, Modell einstellbar, Kosten und Guthaben im Panel; ohne echten Live-Test) und *Tripo* (Upload noch gesperrt); *Vergleich* erzeugt Lokal/Tripo/Meshy in getrennten Collections.

## Updates
Panel **Rim Generator · Update** (ganz unten) → *Nach Update suchen* → installieren → Blender neu starten.
Quelle: dieses Repository, Ordner `felge3d/` (Modulname bleibt `felge3d`).

## Aufbau
- `felge3d/core.py` – Rechenkern (nur numpy): Felge finden, Speichen erkennen (Fusion mehrerer Methoden), Symmetrie mit Selbstprüfung, Mesh
- `felge3d/__init__.py` – Oberfläche, Operatoren
- `felge3d/car.py` – Reifen, Aufstellung der 4 Räder (Geometrie aus „Automotive Wheel & Brake Studio“)
- `felge3d/tire_data.py` – eingebettete Reifentexturen (Michelin Pilot Sport Cup 2 + Profil)
- `felge3d/ai.py`, `updater.py` – lokale KI-Tiefe, Selbst-Update
- `testfelgen/` – 20 Testfotos; `assets/` – Quellbilder (Reifen, Profil, Bremse)

Siehe **ROADMAP.md** für den Stand und die nächsten Schritte.


## Fahrzeug-Paket (4 Räder) – Anker-Empty, Achse Y, Radstand X, eigener Reifen (ab 0.44.0)
- **Ausrichtung:** Radstand immer in **X** (Front = +X), Achsen immer in **Y** (links = +Y), Boden bei Z = 0.
- **Fahrzeug-Empty:** Reiter *Package* → „Fahrzeug-Empty (Mitte Vorderachse)“. Der Picker wählt einen beliebigen Empty (leer lassen = es wird einer angelegt, Radmitte auf Höhe des Vorderreifenradius). Seine **X- und Z-Lage** bestimmt die Vorderachse; die Felder X/Z stehen direkt im Panel. Alle vier Räder hängen am Empty: **Verschieben bewegt das ganze Paket**.
- **Eigener Reifen:** Box „Reifen“ → *Eigener Reifen*: Collection wählen oder *3D-Reifen importieren…* (FBX/OBJ/glTF). Achse, Mitte, Außen- und Wulstradius und Breite werden erkannt; beim Bau wird der Reifen an Zoll, Reifenbreite und Querschnitt angepasst (Wulst sitzt auf dem Felgenradius). *Reifen umdrehen* und *Reifen drehen (Grad)* für Beschriftung/Ventil.
- **Aktualisieren:** Ändert man Zoll, Reifen, Spur, Quellen u. Ä., erscheint „Parameter geändert – bitte aktualisieren“; **Aktualisieren** baut das Paket neu, **die Lage des Empties bleibt erhalten**.
- Test: `/tmp/venv53/bin/python tests/car/test_car_layout.py` (Blender 5.3), Sichtprüfung: `tests/car/render_car.py`.

## Drei Methoden, eine Auswahl (ab 0.45.0)
Reiter *2D to 3D Rim*: **1 Bild** laden, **2 Methode** wählen, **Felge erstellen**.
- **Lokale KI:** KI-Mesh mit Foto-Textur, lokal und kostenlos (gut als Vorlage, schlecht bearbeitbar).
- **Geometry Nodes:** erkennt Formen und Materialien (blank/schwarz, Diamond Cut) und baut eine bearbeitbare SubD-Felge (Blender 5.3).
- **Meshy:** Mesh von Meshy (Cloud). Auswahl **Mit Textur (30 Credits) / Nur Mesh (20 Credits)** direkt unter der Methode; die Zahlen werden aus Modell, Remesh und Preisliste berechnet. Vor jedem Aufruf zeigt der Dialog Kosten und verlangt eine Bestätigung; dasselbe Bild mit gleichen Einstellungen kommt aus dem Cache (keine Credits). Ergebnis: sichtbare Felgen-Collection in Rad-Größe (neutrales Metall, noch ohne Farbe/Textur) und Quelle für die vier Räder.
Jede Methode legt eine eigene Collection an (`Felge_01 …`); zwischen ihnen schaltet der Felgen-Umschalter um. Das Paket (Reiter *Package*) nutzt die Felge der gewählten Methode.

**Sattelfarbe:** Reiter *Package* → Optionen → *Sattelfarbe* (Standard Weiß statt Grün); Schrift und Kanten aus dem Foto bleiben als Helligkeitsstruktur sichtbar. Zum Anwenden *Aktualisieren*.
Tests: `tests/methods/test_methods.py`, `tests/car/test_car_layout.py` (Blender 5.3).

## Mitgelieferter Reifen (ab 0.46.0)
Reiter *Package* → Box „Reifen“ → **Mitgelieferter Reifen** (Liste). Der Reifen liegt als GLB im Add-on (`felge3d/assets/reifen/`, Liste in `reifen.json`) und wird beim ersten Gebrauch einmal importiert. Er passt sich wie der „Eigene Reifen“ an Zoll, Breite und Querschnitt an (Wulstsitz = Felgenradius), behält Profil und Flankentextur und steht standardmäßig so gedreht, dass „P ZERO“ oben steht (wie beim Porsche 992; Feinkorrektur mit *Reifen drehen*). Mitgeliefert: *Pirelli P Zero (GT, 20 Zoll, Game-Ready)* – nur der Reifen, Felge/Schrauben/Bremse wurden herausgelöst (`tools/extract_tyre_asset.py`).
Neue Reifen: GLB nach `felge3d/assets/reifen/` legen und in `reifen.json` eintragen; der Update-Knopf kopiert jetzt auch `assets/` (GLB/JSON/MD/Bilder).
**Credits (CC BY 4.0):** „car tyre game ready p zero“ (https://skfb.ly/oNqAJ) von Iftekhar.Tushar, Lizenz http://creativecommons.org/licenses/by/4.0/ – Änderungen: nur der Reifen herausgelöst, neu exportiert, angepasst. Die Namensnennung steht im Code (`__init__.py`, `assets.py`), in `assets/reifen/reifen.json` und `QUELLE.md`, in den Add-on-Preferences und im Reifen-Bereich des Panels.

## Felge/Reifen-Versatz und Sattelstellung (ab 0.47.0)
- **Felge nach außen (mm):** Reiter *Package → Optionen*, Standard **5 mm**: Die Felge sitzt in Achsrichtung (Y) so weit außen, dass der Reifen sie nicht abschneidet; die Bremse berücksichtigt den Versatz.
- **Sattel vorn / hinten (Grad):** Standard **vorn 90°** (von der linken Fahrzeugseite gesehen auf 3 Uhr, Richtung Heck) und **hinten −90°** (9 Uhr, Richtung Front), also immer zur Fahrzeugmitte, wie beim Porsche. 0° = oben.

## Bremse wächst mit der Felge (ab 0.48.0)
Reiter *Package → Optionen → Bremse wächst mit der Felge* (Standard an): Scheibe, Topf, Sattel und Scheibendicke werden proportional zur Felgengröße skaliert; Bezug sind die Datenblattwerte (20 Zoll vorn, 21 Zoll hinten). Beispiel 21 Zoll vorn: Scheibe 408 mm × 21/20 = 428 mm; 22 Zoll hinten: 380 mm × 22/21 = 398 mm. Aus: Scheibengröße genau wie eingestellt.

## Meshy mit 1 bis 3 Bildern (ab 0.49.0)
Methode *Meshy*: Das oben geladene Bild ist das Hauptbild (Vorderansicht). Mit dem kleinen **+** neben „Bilder für Meshy“ öffnet sich ein zweites Bildfeld, mit nochmal **+** ein drittes (insgesamt höchstens 3); das **−** schließt das letzte Feld wieder. Mit nur einem Bild funktioniert alles wie bisher (Image to 3D); mit 2–3 Bildern nutzt das Add-on Multi-Image to 3D – ein Aufruf, gleicher Preis (mit Textur 30 Credits). Bilder müssen als Datei vorliegen; der Bestätigungsdialog nennt die Bildanzahl.
