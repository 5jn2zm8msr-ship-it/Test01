# Meshy Cars (Car Meshi)

Blender-Add-on: 1–4 Autofotos → Meshy **Multi-Image-to-3D** → texturiertes Mesh (GLB) in der Collection `Meshy_Car_01`, `_02` …

## Installation
`meshy_cars/` als ZIP über *Edit → Preferences → Add-ons → Install…* installieren. Meshy-API-Key in den Add-on-Preferences eintragen
(oder Umgebungsvariable `MESHY_API_KEY`). Der Key liegt nie in der .blend. Multi-Image-to-3D braucht einen Meshy-Bezahl-Plan.

## Bedienung
Seitenleiste `N` → Reiter **Meshy Cars**: Bilder wählen (erstes = Vorderansicht, dann Seite, Hinten, Schräg), Kostenhaken setzen,
**Auto bei Meshy erzeugen**. Fortschritt im Panel, `ESC` bricht ab (wartende Tasks werden gelöscht, Credits erstattet).

## API-Stand (docs.meshy.ai, gelesen 27.11.2026)
- Standardmodell `meshy-7.1`; `latest` löst auf 7.1 auf.
- **Veraltet, wird nicht gesendet:** `meshy-7` (endet 31.12.2026, danach HTTP 400), `meshy-5`/`meshy-4` (eingestellt), `ultra_mode`, `hd_texture`, `symmetry_mode`, `is_a_t_pose`.
- Credit-Preise: Pricing-Seite nicht selbst geprüft – vor Nutzung im Meshy-Dashboard nachsehen.

## Test
`python -I tests/meshy_cars/test_client.py` (Mock-Server, ohne Netz/Blender). Die Blender-Oberfläche ist hier **nicht** in Blender getestet.
