# Rim Generator – Blender-Add-on

Aus einem Felgenfoto (Frontansicht) werden in Sekunden **vier Räder mit Reifen** in Blender.

## Installation (Blender 3.6, Intel-Mac)
1. ZIP über *Edit → Preferences → Add-ons → Install…* installieren, Haken bei **Rim Generator** setzen.
2. Blender mit Cmd+Q neu starten. Seitenleiste `N` → Reiter **Rim Generator**.
3. Optional: **KI-Tiefe einrichten** (einmalig, lokal, ~400 MB) – verbessert die Erkennung.

## Bedienung – zwei Reiter in der Seitenleiste (N)
**Reiter „2D to 3D Rim“** – Felge aus einem Foto
1. **Felgenbild laden & bauen** (JPG/PNG, möglichst gerade von vorn)
2. **Schnitt: Tiefe und Bombierung** – Kurve mit Handles ziehen, dann **Refresh** (die Felge baut sich neu)

**Reiter „Package“** – vier Räder mit Reifen und Bremsen
1. Felge wählen: *Generierte Felge* (aus Reiter 1) oder *Eigene Felge* (Picker für eine beliebige Collection, z.B. importierte FBX)
2. Radstand, Spurweiten, **Zoll vorn/hinten** einstellen, **4 Räder erzeugen**
3. Bremse: echtes 3D (belüftete Scheibe, Sattel mit Brücke/Belägen/Schrauben), Foto als Textur; Regler **Sattelposition** (0° oben, 90° hinten, Standard 45°)

## Kompatibilität
Getestet (headless): Blender 4.5 LTS und **5.3** (Python 3.13); Ziel: ein ZIP für Blender 3.5 (Intel-Mac) bis 5.x (3.x bisher nicht getestet, kein bpy 3.x verfügbar), macOS, Windows, Linux.
KI-Tiefe: onnxruntime wird je nach Python-Version gewählt (3.13: 1.22; älter: 1.19.2 universal2).

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
