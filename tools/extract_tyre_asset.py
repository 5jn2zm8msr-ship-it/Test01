"""
Reifen aus einem Fahrzeug-Rad-Modell (GLB) herauslösen: nur das Reifen-Mesh behalten (Felge, Radschrauben, Bremsscheibe, Bremssattel
werden verworfen) und als eigenständige GLB mit eingebetteter Textur exportieren.
Aufruf (Blender): /tmp/venv53/bin/python tools/extract_tyre_asset.py <quelle.glb> <ziel.glb> [teilname]
Das Teil mit dem größten Außenradius ist der Reifen (Standard); mit teilname kann man es erzwingen.
"""
import sys

import bpy
import numpy as np

src, dst = sys.argv[-3] if len(sys.argv) >= 4 and sys.argv[-3].endswith(".glb") else sys.argv[-2], sys.argv[-1]
if len(sys.argv) >= 4 and not sys.argv[-1].endswith(".glb"):
    src, dst, name = sys.argv[-3], sys.argv[-2], sys.argv[-1]
else:
    name = None
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]


def outer_radius(o):
    n = len(o.data.vertices)
    v = np.empty(n * 3)
    o.data.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    M = np.array(o.matrix_world)
    w = v @ M[:3, :3].T + M[:3, 3]
    c = (w.max(0) + w.min(0)) / 2
    # Achse = Richtung mit der kleinsten Ausdehnung unter den Bounding-Box-Seiten, die zwei ähnlichen Achsen sind radial
    ext = w.max(0) - w.min(0)
    return float(max(ext)), o


if name:
    tyre = next(o for o in meshes if o.name == name)
else:
    tyre = max((outer_radius(o) for o in meshes), key=lambda t: t[0])[1]
print("Reifen:", tyre.name, len(tyre.data.vertices), "Vertices")
for o in meshes:
    if o is not tyre:
        bpy.data.objects.remove(o)
bpy.ops.object.select_all(action="DESELECT")
tyre.select_set(True)
bpy.context.view_layer.objects.active = tyre
tyre.name = "Reifen"
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", use_selection=True, export_image_format="AUTO", export_apply=False)
print("exportiert:", dst)
