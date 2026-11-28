# Environment-Nachbau (Betonbox mit weißem Lamborghini)

Rekonstruktion des Referenzfotos `IMG_2730` in Blender (bpy 5.3, Cycles, CPU). Alles per Skript, nichts per Hand.

## Schnellstart
```bash
./final.sh                      # 1080 px, 96 Samples -> ergebnis/ (render_final.png, vergleich.png, perspektive_kanten.png, messung_helligkeit.txt)
RES=720 SAMPLES=32 ./final.sh   # Vorschau
./final.sh --car_yaw=-15 --sunA=25   # Parameter überschreiben (--name=wert)
```
Voraussetzung: Python-venv mit `bpy`, `numpy`, `pillow` (`PY=/pfad/zu/python ./final.sh`).
Das Auto liegt unter `work2/car.glb` (Meshy, Task `01a21f80…`, nicht im Repo). Standard ist das originale Goldgelb (`--carpaint=gold`); `--carpaint=white` nutzt die mit `recolor_car.py work2/tex_0_base_color.png work2/tex_white.png` erzeugte weiße Textur.

## Anker am Vorderreifen (neues Auto laden)
Im Szenenbaum gibt es den Empty **`Anker_Vorderrad`** genau dort, wo der Vorderreifen auf dem Boden steht (Welt, Drehung = Fahrtrichtung). Das Auto hängt daran; sein eigener Empty **`Auto_Vorderrad_Kontakt`** markiert den Aufstandspunkt seines Vorderreifens. Beim Laden eines anderen Autos sitzt dessen Vorderrad wieder auf dem Anker.
```bash
# neues Auto: Ordner mit car.glb (+ tex_0_base_color.png) angeben, Radlage des Modells in lokalen Koordinaten
./final.sh --cardir=work3 --wfx=-0.55 --wrx=0.62 --wz=-0.085 --rimr=0.153
```
`--wfx/--wrx` = Längsposition von Vorder-/Hinterrad, `--wz` = Radmittelpunkt-Höhe, `--rimr` = Radradius des Modells. Der Löser stellt das Auto dann automatisch so, dass sein Vorderreifen auf (437 | 478) im Foto liegt (`--pfx/--pfy`); der Hinterreifen (`--prx/--pry`) wird schwächer gewichtet.

## Quellen
- **Auto:** Meshy multi-image-to-3d `01a21f80-5baf-7266-a9e3-b4afe40a764e` (goldener Lamborghini). Lack goldgelb (Originaltextur, Farbton auf 37° korrigiert), Scheiben schwarz (aus Textur), Felgen schwarz und metallisch (aus der Geometrie: Radmaske). Breite 2050 mm (nur Y skaliert), 5 mm im Boden.
- **Beton:** Poly Haven (CC0): `concrete_wall_004/006/007`, `concrete_floor_worn_001`, je 2K diffuse/normal/roughness (`textures/`). Stand der Abfrage: 28.11.2026 über die Poly-Haven-API.
- **Himmel:** prozedural (Cycles Sky, Multiple Scattering); kein HDRI nötig.

## Wie das Foto gelesen wurde
- **Kamera:** 70 mm (Kleinbild), Augenhöhe 1,6 m, Horizont y=243 von 720, nach links gedreht (ergibt sich aus der Wandrichtung). Der Raum wird nicht von Hand gesetzt, sondern aus Foto-Pixeln per Strahl-Ebenen-Schnitt berechnet: linke Wand (Fuß/Oberkante), Ecke, Rückwand (Keil, Oberkante steigt wie im Foto), Deckenvorderkante, Pfeiler (zwei frontale Platten). Bei längerer Brennweite stehen die Wände dadurch nicht mehr rechtwinklig. Prüfung ohne Rendern: `--check=1` gibt die Abweichung jedes Linienpunkts in Pixeln aus (≤ 3 px, Ausnahme Pfeiler-Oberkante), zusätzlich `perspektive_kanten.png` (Foto blau, Render rot).
- **Licht:** Das Foto ist nicht mit *einer* Sonne vereinbar (Bodenkeil verlangt Licht fast von hinten, die helle Wandfläche links Licht von rechts hinten). Lösung: zwei weit entfernte Spots mit polygonaler Maske im Richtungsraum (Light-Nodes), kalibriert gegen eine echte Sonne. Die Masken geben dem Lichtkeil genau die schräge Foto-Geometrie. Das Himmelslicht bleibt unberührt.
- **Bounce:** unsichtbare Flächenlicht-Karte, nur für die Decke verlinkt (`ceilfill`), weil Cycles den überstrahlten Boden sonst zu schwach auf die Decke bounct.

## Messung
`measure.py` vergleicht die mittlere Helligkeit an 10 festen Regionen (Foto vs. Render); `edges.py` zeigt Perspektivversatz; `compare.py` baut das Vergleichsbild. `runden/` (lokal) enthält alle Zwischenstände mit Kritik-Runden.

## Bekannte Abweichungen (ehrlich)
- Das Auto im Foto ist ein weißer Keil mit Heckflügel; das Meshy-Modell ist eine andere Form (wie gewünscht ersetzt). Radlage und Proportionen weichen daher ab.
- Lichtkanten wirken im Render noch etwas weicher als im Foto (Fülllicht, Tone-Mapping).
- Pfeiler: Im Foto stehen die Pfeilerkanten leicht schief (6–10 px über die Höhe), eine waagerechte Kamera kann das nicht abbilden.
- Hinterreifen: Wegen des anderen Radstands liegt er bei 70 mm ca. 20 px unter dem Foto-Punkt; der Vorderreifen trifft exakt.
