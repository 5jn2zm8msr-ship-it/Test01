# Defender D130 – STL 1:10 für Bambu Lab

Pipeline (alle Skripte in diesem Ordner, Reihenfolge):

| Stufe | Skript | Zweck |
|---|---|---|
| A | `stl_a_hulle.py` | Meshy-GLB → 1:10 (Breite 202 mm, Länge 427,5 mm, Höhe 194 mm), Decimate + Voxel-Remesh 0,6 mm → eine wasserdichte Hülle |
| B | `stl_b_teile.py` | Zerlegung in 13 Teile (Manifold-Booleans), Zapfen/Bohrungen mit 0,2 mm Spiel je Seite |
| C | `stl_c_pruefung.py` | Schicht-für-Schicht-Raster (0,4 mm): Dünnstellen < 0,8 mm, Filament, Zeit |
| – | `explosion.py`, `stueckliste.py` | Explosionszeichnung (grau, nummeriert) und Stückliste |

## Teile (siehe `ergebnis/stueckliste.md`, `ergebnis/explosion_teile.png`)
- 2 Karosseriehälften, getrennt bei x = −8 mm (Spalt 0,3 mm), verbunden mit 4 losen Dübeln ⌀ 5,8 × 24 mm in Bohrungen ⌀ 6,4 mm (Bosse an den Innenwänden/Dach der Kabine).
- 4 Räder, liegend gedruckt (Außenseite unten, Zapfen ⌀ 6,0 oben); Bohrung in der Achse ⌀ 6,4 mm → Räder drehen frei.
- 2 Spiegel (Arm + Pfosten ⌀ 3,0 mm in ⌀ 3,4-mm-Bohrung in der Karosseriewand), 1 Reserverad (2 Zapfen ⌀ 4,0 mm).
- Alle Teile passen auf ein 256 × 256 × 256 mm Druckbett (X1/P1/A1); die hintere Hälfte ist 222 mm lang und steht auf der Trennfläche.

## Grenzen (ehrlich)
- Mit Bambu Studio nicht geslict (hier nicht verfügbar); Filament/Zeit sind Schätzungen (Annahmen im Kopf von `stl_c_pruefung.py`, ±30 %), Stützmaterial ist nicht enthalten.
- Das Meshy-Mesh ist keine Konstruktion: Wände sind teils nur ca. 2,5 mm (Kabine), Details unter ca. 0,6 mm (Wischer, Antenne) sind durch das Voxel-Remesh weg oder dünn.
- Die Spiegel- und Reserveradbohrungen liegen zu 83–91 % im Material (Rest ragt in Hohlraum): Zapfen halten, sind aber mit Kleber sicherer.
- Lose Einzelteile im Hohlraum der hinteren Hälfte (z. B. 0,5 cm³) wurden verworfen.
