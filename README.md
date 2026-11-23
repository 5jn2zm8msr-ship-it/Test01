# Felge3D – Blender-Add-on

Erzeugt aus einem Frontfoto einer Felge in Sekunden ein 3D-Modell in Blender
(neue Collection, geschlossener Körper, gewölbte Speichen, Foto als Textur).

## Installation (Blender 3.6)
1. Ordner `felge3d/` als ZIP packen (oder die ZIP aus dem Chat nehmen).
2. *Edit → Preferences → Add-ons → Install…* → ZIP wählen → Haken bei **Felge3D**.
3. 3D-Viewport → `N` → Reiter **Felge** → **Felgenbild laden & bauen**.

## Updates
Seitenpanel **Felge → Update** (oder Add-on-Einstellungen):
**Nach Update suchen** → **Update installieren** → Blender neu starten.
Das Add-on lädt dazu den Ordner `felge3d/` aus diesem Repository (Branch `main`).

## Aufbau
- `felge3d/core.py` – Rechenkern (nur numpy): Felge finden, Speichen erkennen, Symmetrie, Mesh bauen
- `felge3d/__init__.py` – Blender-Oberfläche, Operatoren
- `felge3d/updater.py` – Selbst-Update von GitHub
