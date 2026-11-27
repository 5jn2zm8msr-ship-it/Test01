# Mitgelieferte Reifen – Credits und Lizenzen

## Pirelli P Zero (`pzero_gt.glb`)

„**car tyre game ready p zero**“ (https://skfb.ly/oNqAJ) von **Iftekhar.Tushar** steht unter der Lizenz
**Creative Commons Attribution 4.0 (CC BY 4.0)** – http://creativecommons.org/licenses/by/4.0/

**Änderungen gegenüber dem Original:** Aus dem Gesamtmodell (Rad mit Felge, Radschrauben, Bremsscheibe und Bremssattel;
Datei `Maserati_Granturismo_tyres_gltf.glb`, Teil `masaretti_tyer_parts00_low`) wurde nur der Reifen herausgelöst
(`tools/extract_tyre_asset.py`), als GLB neu exportiert und beim Bau an Radius, Breite und Wulstsitz angepasst und gedreht.

Die Rechte an den abgebildeten Marken (Pirelli, Maserati) liegen bei den jeweiligen Inhabern.

## Pirelli P Zero Sport, Pirelli P Zero Trofeo R, Yokohama Advan, Pirelli F1 (`pzero_sport.glb`, `pzero_trofeo_r.glb`, `advan_drift.glb`, `f1_slick.glb`)

„**[FREE] Sport Tire Pack - by SDC**“ (https://sketchfab.com/3d-models/free-sport-tire-pack-by-sdc-07ffafa14c0348738edff992999511f9) von **SDC PERFORMANCE**
steht unter der Lizenz **Creative Commons Attribution 4.0 (CC BY 4.0)** – http://creativecommons.org/licenses/by/4.0/

**Änderungen gegenüber dem Original:** Aus dem Pack mit vier Reifen wurde jeder Reifen einzeln herausgelöst, die Welttransformation gebacken, das Mesh auf ca. 60 000 Flächen
ausgedünnt (falls größer; Textur-UVs bleiben), neu als GLB exportiert (`tools/extract_tyre_pack.py`) und beim Bau an Radius, Breite und Wulstsitz angepasst und gedreht.
Standard im Add-on ist der Pirelli P Zero (Sport).

Die Rechte an den abgebildeten Marken (Pirelli, Yokohama) liegen bei den jeweiligen Inhabern.

Neue Reifen: GLB hier ablegen und in `reifen.json` eintragen (Felder `titel`, `autor`, `quelle_url`, `lizenz`, `lizenz_url`, `aenderungen`).
Dateien klein halten (GitHub: Warnung ab 50 MB, Grenze 100 MB; Git LFS funktioniert im ZIP-Download nicht).
