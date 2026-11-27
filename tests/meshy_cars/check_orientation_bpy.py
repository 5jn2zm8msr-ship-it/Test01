"""Prueft Ausrichtung/Zentrierung/Breite eines Meshy-GLB im echten bpy und macht schnelle Workbench-Screenshots (ohne Rendering).
Aufruf (pip install bpy): python -I tests/meshy_cars/check_orientation_bpy.py -- <Ausgabeordner> <auto.glb>
Erwartet: Zentrum XY = (0,0), Boden z = 0, Breite(Y) = 2020 mm, Laenge entlang X, Front (niedrig/schmal) bei -X."""
import sys, math, glob, time
sys.path.insert(0, "/home/user/Test01")
import bpy, numpy as np
from mathutils import Vector
SP = sys.argv[sys.argv.index("--") + 1]
glb = sys.argv[sys.argv.index("--") + 2]
bpy.ops.wm.read_factory_settings(use_empty=True)
import meshy_cars
meshy_cars.register()
sc = bpy.context.scene
coll, n = meshy_cars._import_glb(bpy.context, glb, "Meshy_Car")
bpy.context.view_layer.update()
meshes = [o for o in coll.all_objects if o.type == "MESH"]
# --- Ausrichtung am echten Mesh nachmessen (Weltkoordinaten, mm)
V = np.vstack([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in meshes]) * 1000
lo, hi = V.min(0), V.max(0)
print("Bounding-Box mm: X %.0f..%.0f  Y %.0f..%.0f  Z %.0f..%.0f" % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
print("Zentrum XY: (%.1f, %.1f)  Boden z=%.2f  Laenge(X)=%.0f  Breite(Y)=%.0f" % ((lo[0]+hi[0])/2, (lo[1]+hi[1])/2, lo[2], hi[0]-lo[0], hi[1]-lo[1]))
L = hi[0] - lo[0]
front = V[V[:, 0] < lo[0] + 0.2 * L]; rear = V[V[:, 0] > hi[0] - 0.2 * L]
print("Hoehe max z: vorderes Fuenftel(-X) %.0f mm | hinteres Fuenftel(+X) %.0f mm" % (front[:, 2].max(), rear[:, 2].max()))
print("Querbreite: vorn %.0f mm | hinten %.0f mm" % (np.ptp(front[:, 1]), np.ptp(rear[:, 1])))
# --- Buehne (kein Rendering: Workbench, Textur, keine Samples)
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"; sh.color_type = "TEXTURE"; sh.show_shadows = False; sh.show_cavity = False; sh.show_object_outline = False
sc.display.render_aa = "OFF"
sc.render.resolution_x, sc.render.resolution_y = 1400, 800
w = bpy.data.worlds.new("W"); sc.world = w; w.color = (0.12, 0.12, 0.14)
bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, -0.002))
cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); sc.collection.objects.link(cam); cam.data.lens = 42
tg = bpy.data.objects.new("T", None); tg.location = (0, 0, 0.55); sc.collection.objects.link(tg)
t = cam.constraints.new("TRACK_TO"); t.target, t.track_axis, t.up_axis = tg, "TRACK_NEGATIVE_Z", "UP_Y"
sc.camera = cam
views = {"front_von_minus_x": (-1, 0), "seite_von_minus_y": (0, -1), "schraeg_front_links": (-0.8, -0.6), "oben": None}
for k, v in views.items():
    t0 = time.time()
    if v is None:
        cam.location = (0, 0.001, 8.5); cam.data.lens = 35
    else:
        cam.data.lens = 42; cam.location = (v[0] * 7.2, v[1] * 7.2, 1.7)
    sc.render.filepath = SP + "/shot_%s.png" % k
    bpy.ops.render.render(write_still=True)
    print("Screenshot %-20s %.1f s" % (k, time.time() - t0))
