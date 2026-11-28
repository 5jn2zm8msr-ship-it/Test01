# Defender D130 – STL 1:10 für Bambu Lab

Pipeline (alle Skripte in diesem Ordner, Reihenfolge):

| Stufe | Skript | Zweck |
|---|---|---|
| A | `stl_a_hulle.py` | Meshy-GLB → 1:10 (Breite 202 mm, Länge 427,5 mm, Höhe 194 mm), Decimate + Voxel-Remesh 0,6 mm → eine wasserdichte Hülle |
| B | `stl_b_teile.py` | Zerlegung in 13 Teile (Manifold-Booleans), Zapfen/Bohrungen mit 0,2 mm Spiel je Seite |
| C | `stl_c_pruefung.py` | Schicht-für-Schicht-Raster (0,4 mm): Dünnstellen < 0,8 mm, Filament, Zeit |
| – | `explosion.py`, `stueckliste.py` | Explosionszeichnung (grau, nummeriert) und Stückliste |

## Teile (Stand v5, siehe `ergebnis/stueckliste_v3.md`, `ergebnis/explosion_zweifarbig.png`)
- **Front + Kabine** (ein Stück, 168 × 198 × 247 mm): Motorraum und Keil unter der Scheibe massiv, Kabine hohl (3 mm Wand, Seitenfenster geschlossen) mit 45°-Dach, 4 Pfosten für die Dübel zum Heck.
- **Heck-Fahrwerk** (Boden, Rahmen, Stecker zur Kabine) und **Aufbau** (Motorrad, Käfig, Rohre) mit 4 kleinen Dübeln.
- **Rad** (4×, zweifarbig: Reifen schwarz, Felge weiß, ein Teil): Zapfen ⌀ 6,0 mm in ⌀ 6,4-mm-Bohrung (frei drehend, nicht gesichert).
- 4 große Dübel ⌀ 5,8 × 24 mm und 4 kleine ⌀ 3,0 × 13 mm.
- Motorraum bewusst nicht hohl: bei 3 % Infill kosten die zusätzlichen Wände des Hohlraums mehr, als der gesparte Infill bringt.

## Skripte der letzten Stufen
`stl_a2_vereinfachen.py` (Hülle, Kabinen-Hohlraum), `stl_b4_teile.py` (Aufteilung, Bohrungen, Räder aus der Original-Hülle), `slice_v2.py` (Slicing-Varianten), `gcode_viz.py` + `doku_stuetzen.py` (Stützen-Doku), `explosion.py` + `stueckliste3.py` (Zeichnung, Stückliste).

## Grenzen (ehrlich)
- Mit PrusaSlicer gesliced (Bambu-ähnliches Profil), nicht mit Bambu Studio; Werte ±30 %. Farbwechsel/Purge nicht enthalten.
- Der Aufbau (Motorrad) besteht zu rund 43 % aus Stützmaterial, das Heck-Fahrwerk zu rund 30 %.
- Front + Kabine steht 247 mm hoch (Bambu-Studio-Standard 250 mm).
