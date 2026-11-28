# Meshy Cars (Car Meshi)

Blender-Add-on: 1–4 Autofotos → Meshy **Multi-Image-to-3D** → texturiertes Mesh (GLB) in der Collection `Meshy_Car_01`, `_02` …

## Installation
`meshy_cars/` als ZIP über *Edit → Preferences → Add-ons → Install…* installieren. Meshy-API-Key in den Add-on-Preferences eintragen
(oder Umgebungsvariable `MESHY_API_KEY`). Der Key liegt nie in der .blend. Multi-Image-to-3D braucht einen Meshy-Bezahl-Plan.

## Bedienung
Seitenleiste `N` → Reiter **Meshy Cars**: Bilder wählen (erstes = Vorderansicht, dann Seite, Hinten, Schräg), Kostenhaken setzen,
**Auto bei Meshy erzeugen**. Fortschritt im Panel, `ESC` bricht ab (wartende Tasks werden gelöscht, Credits erstattet).

## Größe: feste Breite
Jedes importierte Auto wird gleichmäßig auf eine feste **Breite** skaliert (Standard **2020 mm**, Feld *Breite (mm)* im Panel; ändern skaliert live).
Breite = kürzere horizontale Seite der Bounding-Box (Spiegel zählen mit, falls im Mesh vorhanden). Die **Länge** ergibt sich proportional,
der **Radstand** wird als Schätzung (≈ 60 % der Länge) angezeigt. Jedes Auto hängt an einem Wurzel-Empty `Meshy_Car_NN` am Boden-Mittelpunkt.

## Ausrichtung beim Import
Das Auto sitzt **zentriert auf dem Weltursprung** (Mitte der Bounding-Box auf X/Y = 0, Räder/Unterkante auf z = 0), **Z oben**, Länge entlang **X**,
Achsen/Breite entlang **Y**, **Front nach −X**. Liegt die Länge nach dem Import entlang Y, wird um −90° um Z gedreht. Welche Seite „vorn“ ist, kann
Meshy nicht garantieren – zeigt die Front nach +X, im Panel **Front/Heck tauschen (180°)** drücken. Prüfung: `tests/meshy_cars/check_orientation_bpy.py` (braucht `pip install bpy`) – macht je Lauf Workbench-Screenshots ohne Rendering, immer **mit Textur und grau (Form)**; Ergebnisse in `testbilder/ergebnis/`.

## Kosten (Preisseite docs.meshy.ai/en/api/pricing, 27.11.2026; das Panel rechnet vorab mit)
| Leistung | meshy-7.1 / latest | meshy-6 | meshy-6-lite |
|---|---|---|---|
| Multi-Image, nur Mesh | 20 | 20 | 5 |
| + Textur 2K / 4K | +10 / +10 | +10 / +10 | +10 / nicht unterstützt |
| + Textur 8K | +15 | +15 | nicht unterstützt |
| + Ultra-Geometrie 2k | +5 | nicht unterstützt | nicht unterstützt |

Prüfung: 7.1 + 2K-Textur kostete real **30 Credits** (Preisseite: 30).

## Textur neu (Retexture)
Skizzen als Eingabe führen dazu, dass Meshy die **Schraffur der Zeichnung in die Textur backt** (Test: graues Flickwerk statt Lack). Abhilfe ohne neue Form:
Box *Textur neu* am gewählten Auto → Beschreibung (*Look*, Standard: glänzender graphit-metallic Lack, schwarze Scheiben, Carbon/Chrom, „no sketch strokes“) → Bestätigung → Knopf.
Meshy-Retexture (`enable_original_uv`, Form bleibt) kostet **10 Credits** (2K/4K, 8K: 15). Das neue Auto wird importiert, das alte ausgeblendet.
Meshys Doku nennt Multi-Image-Tasks nicht als Quelle: lehnt Meshy die Task-ID ab (HTTP 400), geht das lokale GLB als `model_url` hoch (max. 100 MB).
Tests: `test_retexture.py` (Mock), `check_retexture_flow_bpy.py` (bpy). Live noch nicht getestet.

## Bewusst weggelassen: Remesh/Quads (0.5–0.7)
Remesh (auch mit Quads) wurde ausprobiert und wieder entfernt: Das Modell wird dabei von ~1,1 Mio. auf ~61.000 Dreiecke reduziert, die Textur wird neu gebacken,
und das Ergebnis war sichtbar schlechter als der Lauf ohne Remesh. Standard ist jetzt immer der Lauf **ohne Remesh** (volles Detail). Der Code steht weiter in der
Git-Historie (Commit `378a914`, Version 0.7.0). Vergleichsbilder des Remesh-Laufs: `testbilder2/ergebnis/`.

## API-Stand (docs.meshy.ai, gelesen 27.11.2026)
- Standardmodell `meshy-7.1`; `latest` löst auf 7.1 auf.
- **Veraltet, wird nicht gesendet:** `meshy-7` (endet 31.12.2026, danach HTTP 400), `meshy-5`/`meshy-4` (eingestellt), `ultra_mode`, `hd_texture`, `symmetry_mode`, `is_a_t_pose`.
- Credit-Preise: Pricing-Seite nicht selbst geprüft – vor Nutzung im Meshy-Dashboard nachsehen.

## Test
`python -I tests/meshy_cars/test_client.py` `test_sizing.py`, `test_prices.py` und `test_retexture.py` (Mock-Server, ohne Netz/Blender). Die Blender-Oberfläche ist hier **nicht** in Blender getestet.
