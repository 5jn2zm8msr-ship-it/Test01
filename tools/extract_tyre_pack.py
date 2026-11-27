"""
Einzelne Reifen aus dem „[FREE] Sport Tire Pack“ von SDC PERFORMANCE (Sketchfab, CC BY 4.0) herauslösen und als kleine GLBs ablegen.
Quelle: https://sketchfab.com/3d-models/07ffafa14c0348738edff992999511f9 (Lizenz http://creativecommons.org/licenses/by/4.0/)

Je Reifen: Teile der Gruppe behalten (Elternobjekt-Name), Welttransformation in die Vertices backen, Mesh ausdünnen (Decimate, Ziel ca. 60 000 Flächen,
die Textur-UVs bleiben), Mitte in den Ursprung, GLB mit eingebetteter Textur. Die Achse wird beim Einbau automatisch erkannt (fbx.tire_fit).
Aufruf (Blender): /tmp/venv53/bin/python tools/extract_tyre_pack.py <pack.glb> <zielordner> [flächenziel]
"""
import os
import sys

import bpy
import numpy as np

GRUPPEN = {                                  # Dateiname -> Namen der Elternobjekte im Pack
    "pzero_sport.glb": ["<Wheel_0"],
    "pzero_trofeo_r.glb": ["Cylinder_1"],
    "advan_drift.glb": ["pneu ar-gauche 3_2"],
    "f1_slick.glb": ["Circle.004_3"],
}

src, dst = sys.argv[-3], sys.argv[-2]
ziel_flaechen = int(sys.argv[-1]) if sys.argv[-1].isdigit() else 60000
if sys.argv[-1].isdigit():
    src, dst = sys.argv[-3], sys.argv[-2]
else:
    src, dst = sys.argv[-2], sys.argv[-1]
os.makedirs(dst, exist_ok=True)

for fname, parents in GRUPPEN.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=src)
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is not None and o.parent.name in parents]
    total = sum(len(o.data.polygons) for o in meshes)
    ratio = min(1.0, ziel_flaechen / max(total, 1))
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for o in meshes:
        me = o.data.copy()
        me.transform(o.matrix_world)
        if o.matrix_world.determinant() < 0:
            me.flip_normals()
        new = bpy.data.objects.new(o.name, me)
        bpy.context.scene.collection.objects.link(new)
        if ratio < 0.999 and len(me.polygons) > 500:
            mod = new.modifiers.new("dec", "DECIMATE")
            mod.ratio = ratio
            mod.use_collapse_triangulate = True
            bpy.context.view_layer.update()
            ev = new.evaluated_get(bpy.context.evaluated_depsgraph_get())
            me2 = bpy.data.meshes.new_from_object(ev)
            new.modifiers.remove(mod)
            new.data = me2
        out.append(new)
    for o in list(bpy.data.objects):
        if o not in out:
            bpy.data.objects.remove(o)
    for i, o in enumerate(sorted(out, key=lambda o: -len(o.data.polygons))):          # Namen wie beim generierten Reifen: das größte Teil heißt „Reifen“
        o.name = "Reifen" if i == 0 else "Reifen %d" % (i + 1)
    allv = np.concatenate([np.array([v.co[:] for v in o.data.vertices]) for o in out])
    c = (allv.max(0) + allv.min(0)) / 2.0
    for o in out:
        for v in o.data.vertices:
            v.co.x -= c[0]
            v.co.y -= c[1]
            v.co.z -= c[2]
        o.data.update()
    bpy.ops.object.select_all(action="DESELECT")
    for o in out:
        o.select_set(True)
    bpy.context.view_layer.objects.active = out[0]
    path = os.path.join(dst, fname)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_image_format="AUTO", export_apply=False)
    print("exportiert:", path, "| Flächen vorher", total, "nachher", sum(len(o.data.polygons) for o in out), "| %.1f MB" % (os.path.getsize(path) / 1e6))
