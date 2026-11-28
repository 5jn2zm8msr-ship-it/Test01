"""bpy-Test (ohne Netz/Credits): Registrierung, Import mit Task-ID, Folgeimport blendet Vorgänger aus, Retexture ohne Bestätigung wird verweigert.
Aufruf (pip install bpy): python -I tests/meshy_cars/check_retexture_flow_bpy.py -- <auto.glb>"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
import meshy_cars
meshy_cars.register()
glb = sys.argv[sys.argv.index("--") + 1]
def has_op(name):      # hasattr(bpy.ops.x, ...) ist immer True (lazy) -> über das RNA-Objekt prüfen
    try:
        getattr(bpy.ops.meshycars, name).get_rna_type()
        return True
    except (KeyError, RuntimeError):
        return False
for op in ("generate", "retexture", "flip_front"):
    assert has_op(op), op
assert not has_op("remesh") and not has_op("to_quads") and not has_op("nonsense"), "Quads/Remesh müssen weg sein"
s = bpy.context.scene.meshycars
assert s.retex_prompt == meshy_cars.RETEX_DEFAULT and "no sketch strokes" in s.retex_prompt
c1, _ = meshy_cars._import_glb(bpy.context, glb, "A", task_id="task-A")
r1 = meshy_cars.active_car_root(bpy.context)
assert r1["mc_task_id"] == "task-A" and r1["mc_glb"] == glb
c2, _ = meshy_cars._import_glb(bpy.context, glb, "B", task_id="task-B", hide_root=r1)
r2 = meshy_cars.active_car_root(bpy.context)
assert r2["mc_task_id"] == "task-B" and r2["mc_parent"] == r1.name and r1.hide_get() and not r2.hide_get()
bpy.context.view_layer.objects.active = r2
try:
    bpy.ops.meshycars.retexture()
    raise SystemExit("Retexture ohne Bestätigung lief los (hätte Credits gekostet)!")
except RuntimeError as e:
    assert "bestätigen" in str(e) and "10 Credits" in str(e)
assert not s.busy
meshy_cars.unregister()
print("OK: bpy-Retexture-Ablauf bestanden")
