"""bpy-Test (ohne Netz/Credits): Registrierung, Import mit Task-ID, Remesh-Folgeimport (Vorgaenger wird ausgeblendet), Kostenanzeige.
Aufruf (pip install bpy): python -I tests/meshy_cars/check_remesh_flow_bpy.py -- <auto.glb>"""
import sys
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "..", ".."))
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
import meshy_cars
meshy_cars.register()
glb = sys.argv[sys.argv.index("--") + 1]
sc = bpy.context.scene
for op in ("generate", "remesh", "flip_front"):
    assert hasattr(bpy.ops.meshycars, op), op
coll1, _ = meshy_cars._import_glb(bpy.context, glb, "Meshy_Car", task_id="task-A")
r1 = meshy_cars.active_car_root(bpy.context)
assert r1["mc_task_id"] == "task-A" and r1["mc_glb"] == glb
coll2, _ = meshy_cars._import_glb(bpy.context, glb, "Meshy_Car", task_id="task-B", hide_root=r1)
r2 = meshy_cars.active_car_root(bpy.context)
assert r2 is not r1 and r2["mc_task_id"] == "task-B" and r2["mc_parent"] == r1.name
assert r1.hide_get() and all(o.hide_get() for o in r1.children_recursive), "Vorgaenger nicht ausgeblendet"
assert not r2.hide_get()
assert coll1.name != coll2.name
# Kostenanzeige
s = sc.meshycars
assert meshy_cars.credit_estimate(s) == (30, ""), meshy_cars.credit_estimate(s)
s.ai_model, s.tex_res = "meshy-6-lite", "4k"
cr, err = meshy_cars.credit_estimate(s)
assert cr is None and "2K" in err, (cr, err)
# Operator-Preflight ohne Bestaetigung -> bricht ab, ohne Netz
s.ai_model, s.tex_res = "meshy-7.1", "2k"
bpy.context.view_layer.objects.active = r2
try:
    bpy.ops.meshycars.remesh()
    raise SystemExit("Remesh ohne Bestaetigung lief los (haette Credits gekostet)!")
except RuntimeError as e:
    assert "bestätigen" in str(e) and "5 Credits" in str(e)
assert not s.busy
meshy_cars.unregister()
print("OK: bpy-Remesh-Ablauf bestanden")
