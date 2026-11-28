# Environment-Nachbau (Betonbox mit weißem Lamborghini)

Rekonstruktion des Referenzfotos `IMG_2730` in Blender (bpy 5.3, Cycles, CPU). Alles per Skript, nichts per Hand.

## Schnellstart
```bash
./final.sh                      # 1080 px, 96 Samples -> ergebnis/ (render_final.png, vergleich.png, perspektive_kanten.png, messung_helligkeit.txt)
RES=720 SAMPLES=32 ./final.sh   # Vorschau
./final.sh --car_yaw=-15 --sunA=25   # Parameter überschreiben (--name=wert)
```
Voraussetzung: Python-venv mit `bpy`, `numpy`, `pillow` (`PY=/pfad/zu/python ./final.sh`).
Das Auto liegt unter `work2/car.glb` (Meshy, Task `01a21f80…`, nicht im Repo); `recolor_car.py work2/tex_0_base_color.png work2/tex_white.png` erzeugt daraus die weiße Textur.

## Quellen
- **Auto:** Meshy multi-image-to-3d `01a21f80-5baf-7266-a9e3-b4afe40a764e` (goldener Lamborghini), umgefärbt: Lack weiß, Scheiben schwarz (aus Textur), Felgen schwarz (aus der Geometrie: Radmaske).
- **Beton:** Poly Haven (CC0): `concrete_wall_004/006/007`, `concrete_floor_worn_001`, je 2K diffuse/normal/roughness (`textures/`). Stand der Abfrage: 28.11.2026 über die Poly-Haven-API.
- **Himmel:** prozedural (Cycles Sky, Multiple Scattering); kein HDRI nötig.

## Wie das Foto gelesen wurde
- **Kamera** aus den Fluchtpunkten: 35 mm (Kleinbild), Augenhöhe 1,6 m, 31,6° nach links gedreht, Horizont bei y=254 von 720 (Lens-Shift). Prüfung per Kanten-Overlay (`perspektive_kanten.png`, Foto blau, Render rot).
- **Raum:** linke Wand, Rückwand, Deckenplatte mit Vorderkante bei y=5,4 m, schmaler Pfeiler rechts (Seitenfläche Tiefe 3,4–4,0 m).
- **Licht:** Das Foto ist nicht mit *einer* Sonne vereinbar (Bodenkeil verlangt Licht fast von hinten, die helle Wandfläche links Licht von rechts hinten). Lösung: zwei weit entfernte Spots mit polygonaler Maske im Richtungsraum (Light-Nodes), kalibriert gegen eine echte Sonne. Die Masken geben dem Lichtkeil genau die schräge Foto-Geometrie. Das Himmelslicht bleibt unberührt.
- **Bounce:** unsichtbare Flächenlicht-Karte, nur für die Decke verlinkt (`ceilfill`), weil Cycles den überstrahlten Boden sonst zu schwach auf die Decke bounct.

## Messung
`measure.py` vergleicht die mittlere Helligkeit an 10 festen Regionen (Foto vs. Render); `edges.py` zeigt Perspektivversatz; `compare.py` baut das Vergleichsbild. `runden/` (lokal) enthält alle Zwischenstände mit Kritik-Runden.

## Bekannte Abweichungen (ehrlich)
- Das Auto im Foto ist ein weißer Keil mit Heckflügel; das Meshy-Modell ist eine andere Form (wie gewünscht ersetzt). Radlage und Proportionen weichen daher ab.
- Lichtkanten wirken im Render noch etwas weicher als im Foto (Fülllicht, Tone-Mapping).
- Pfeiler: heller Streifen rechts davon (Vorderfläche) nur angedeutet.
