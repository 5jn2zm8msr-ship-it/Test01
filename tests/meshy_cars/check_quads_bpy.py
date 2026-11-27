"""bpy-Test (ohne Netz/Credits): Dreiecke -> Quads am echten Meshy-GLB. Erwartet: >= 85 % Quads, UVs/Material erhalten, Maße unverändert.
Aufruf (pip install bpy): python -I tests/meshy_cars/check_quads_bpy.py -- <quad_remesh_auto.glb>"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import bpy
from mathutils import Vector
bpy.ops.wm.read_factory_settings(use_empty=True)
import meshy_cars
meshy_cars.register()
glb = sys.argv[sys.argv.index("--") + 1]

def dims(coll):
    ms = [o for o in coll.all_objects if o.type == "MESH"]
    pts = [o.matrix_world @ v.co for o in ms for v in o.data.vertices]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return (hi - lo) * 1000, (lo + hi) / 2 * 1000

c0, _ = meshy_cars._import_glb(bpy.context, glb, "A", to_quads=False)
c1, _ = meshy_cars._import_glb(bpy.context, glb, "B", to_quads=True)
bpy.context.view_layer.update()
m0 = [o for o in c0.all_objects if o.type == "MESH"][0]; m1 = [o for o in c1.all_objects if o.type == "MESH"][0]
f0, f1 = len(m0.data.polygons), len(m1.data.polygons)
q1 = sum(1 for p in m1.data.polygons if len(p.vertices) == 4)
print("Dreiecke-Import: %d Flächen | Quad-Import: %d Flächen, %d Quads (%.1f %%)" % (f0, f1, q1, 100 * q1 / f1))
assert f0 == sum(1 for p in m0.data.polygons if len(p.vertices) == 3), "Ausgangsmesh sollte reine Dreiecke sein"
assert q1 / f1 >= 0.85, "Quad-Anteil zu niedrig"
assert [u.name for u in m1.data.uv_layers] == [u.name for u in m0.data.uv_layers] and len(m1.material_slots) == len(m0.material_slots)
d0, ctr0 = dims(c0); d1, ctr1 = dims(c1)
print("Maße mm (Dreiecke): %s | (Quads): %s" % (tuple(round(v) for v in d0), tuple(round(v) for v in d1)))
assert all(abs(a - b) < 0.5 for a, b in zip(d0, d1)) and all(abs(a - b) < 0.5 for a, b in zip(ctr0, ctr1)), "Form/Lage verändert"
# Operator auf bestehendem Auto
bpy.context.view_layer.objects.active = meshy_cars.find_car_root(m0)
bpy.ops.meshycars.to_quads()
q0 = sum(1 for p in m0.data.polygons if len(p.vertices) == 4)
assert abs(q0 - q1) <= 1, (q0, q1)
meshy_cars.unregister()
print("OK: Quad-Rückgewinnung bestanden")
