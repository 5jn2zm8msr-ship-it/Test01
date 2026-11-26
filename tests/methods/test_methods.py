"""
Blender-Test (5.3): drei Methoden (Lokale KI / Geometry Nodes / Meshy) hinter einer Auswahl, Meshy-Felge aus einem GLB (ohne API-Aufruf),
Quelle für das Paket. Aufruf: /tmp/venv53/bin/python tests/methods/test_methods.py
"""
import math
import os
import shutil
import sys
import tempfile

import bpy  # noqa: I001
import addon_utils
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = os.path.join(bpy.utils.user_resource("SCRIPTS", path="addons", create=True), "felge3d")
shutil.rmtree(d, ignore_errors=True)
os.makedirs(d)
for f in os.listdir(os.path.join(REPO, "felge3d")):
    if f.endswith((".py", ".toml")):
        shutil.copy(os.path.join(REPO, "felge3d", f), d)
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("felge3d", default_set=True)
import felge3d  # noqa: E402
from felge3d import paramui  # noqa: E402

bad = 0


def check(name, cond, info=""):
    global bad
    print("OK   " if cond else "FEHLT", name, info)
    bad += 0 if cond else 1


sc = bpy.context.scene
s, c = sc.felge3d, sc.felge3d_car
photo = os.path.join(REPO, "tests", "diamond_cut", "neue_felgen", "porsche_gold_IMG_2695.jpg")
check("Standard-Methode = Geometry Nodes", s.method == "SUBD" and s.result_mode == "EDIT")
items = [i.identifier for i in s.bl_rna.properties["method"].enum_items]
check("drei Methoden zur Auswahl", items == ["AI", "SUBD", "MESHY"], str(items))

# 1) Geometry Nodes (Standard)
bpy.ops.felge3d.import_image(filepath=photo)
rims = paramui.rim_collections()
check("Geometry Nodes: Collection mit Methode SUBD", len(rims) == 1 and rims[0]["felge3d_method"] == "SUBD" and paramui.param_object_of(rims[0]) is not None)
subd = rims[0]

# 2) Lokale KI: eigene Collection, SubD bleibt
s.method = "AI"
check("Methode AI setzt KI-Mesh-Modus", s.result_mode == "KI")
check("Felge erstellen (AI)", bpy.ops.felge3d.create_rim() == {"FINISHED"})
rims = paramui.rim_collections()
ai = [r for r in rims if r["felge3d_method"] == "AI"]
check("Lokale KI: zweite Collection, SubD unverändert vorhanden", len(rims) == 2 and len(ai) == 1 and subd.name in bpy.data.collections)
check("KI-Collection enthält Stern/Bett", any(o.get("felge3d_role") in ("star", "barrel", "body") for o in ai[0].objects))

# 3) zurück auf Geometry Nodes: bestehende Collection wird aktualisiert, keine dritte
s.method = "SUBD"
check("Methode SUBD setzt EDIT", s.result_mode == "EDIT")
check("Felge erstellen (SUBD)", bpy.ops.felge3d.create_rim() == {"FINISHED"})
check("keine dritte Collection (gleiches Bild, gleiche Methode)", len(paramui.rim_collections()) == 2)

# 4) Meshy: Einstellungen, kein Bau beim Bildladen (kostenpflichtig)
s.method = "MESHY"
check("Methode MESHY setzt Anbieter Meshy", s.cloud_provider == "MESHY" and s.mesh_source == "CLOUD")
n_before = len(paramui.rim_collections())
bpy.ops.felge3d.import_image(filepath=photo)
check("Bild laden baut bei Meshy NICHT (erst ‚Felge erstellen‘)", len(paramui.rim_collections()) == n_before)

# 5) Meshy-GLB (synthetisch: Fass + Scheibe + Speichen, Achse beliebig) -> sichtbare Felge
bpy.ops.mesh.primitive_torus_add(major_radius=0.25, minor_radius=0.04, major_segments=64, minor_segments=12)
barrel = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=0.02, vertices=48, location=(0, 0, 0.05))
disc = bpy.context.active_object
for o in (barrel, disc):
    o.select_set(True)
bpy.context.view_layer.objects.active = barrel
bpy.ops.object.join()
rimob = bpy.context.active_object
rimob.rotation_euler = (math.radians(90), 0, math.radians(30))          # Achse nicht in Z
glb = os.path.join(tempfile.mkdtemp(), "meshy_test.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
col = felge3d.make_meshy_rim(bpy.context, s, glb)
check("Meshy-Felge: neue Felgen-Collection mit Methode MESHY", col["felge3d_method"] == "MESHY" and col in paramui.rim_collections())
check("Meshy-Felge: Mesh-Objekt mit Rolle meshy", any(o.get("felge3d_role") == "meshy" and o.type == "MESH" for o in col.objects))
check("Meshy-Quelle verborgen gespeichert", s.meshy_source is not None and s.meshy_source.hide_viewport)
bpy.context.view_layer.update()
mob = next(o for o in col.objects if o.get("felge3d_role") == "meshy")
v = np.empty(len(mob.data.vertices) * 3)
mob.data.vertices.foreach_get("co", v)
v = v.reshape(-1, 3)
M = np.array(mob.matrix_world)
w = v @ M[:3, :3].T + M[:3, 3]
from felge3d import core  # noqa: E402
R_out = core.dimensions(felge3d.make_params(s))[4]
# Rad steht: Achse = Welt-Y; Außenradius in der XZ-Ebene
ro = np.hypot(w[:, 0], w[:, 2]).max()
check("Meshy-Felge: Außenradius = Felgenradius", abs(ro - R_out) / R_out < 0.03, "%.3f / %.3f" % (ro, R_out))
check("Meshy-Felge: Achse = Welt-Y (Ausdehnung in Y klein)", (w[:, 1].max() - w[:, 1].min()) < 0.5 * 2 * ro)
check("sichtbar (aktive Felge)", not col.hide_viewport and s.collection == col)

# 6) Paket aus der Meshy-Felge
check("Methode MESHY: Paket nutzt Meshy-Quelle", felge3d._source_collection(s) is s.meshy_source and bool(felge3d._fbx_meshes(s)))
r = bpy.ops.felge3d.car_generate()
check("Paket aus Meshy-Felge erzeugt", r == {"FINISHED"})
wheels = [o for o in bpy.data.objects if o.name.startswith("Rad ") and o.type == "EMPTY"]
rim_children = {w.name: [k.name for k in w.children if k.type == "MESH" and not k.name.startswith(("Reifen", "Bremse"))] for w in wheels}
check("4 Räder, an jedem eine Felge aus dem Meshy-Mesh", len(wheels) == 4 and all(len(v) >= 1 for v in rim_children.values()), str(rim_children))
check("Methodenwechsel -> Update-Hinweis", (setattr(s, "method", "SUBD") or True) and felge3d.car_is_stale(s, c))
print("\nFehlgeschlagen:", bad)
sys.exit(1 if bad else 0)
