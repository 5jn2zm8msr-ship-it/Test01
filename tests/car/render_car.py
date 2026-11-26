"""Sichtprüfung des Pakets (Blender 5.3): Rendering in 3/4-Ansicht und Seitenansicht auf schwarzer Backplate.
Aufruf: /tmp/venv53/bin/python tests/car/render_car.py <ausgabeordner>   (nutzt tests/abgleich/abgleich.py für Szene/Licht)"""
import math
import os
import sys

import bpy  # noqa: I001
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "abgleich"))
import abgleich as ab  # noqa: E402

OUT = sys.argv[-1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
ab.install_addon()
sc = bpy.context.scene
bpy.ops.felge3d.import_image(filepath=os.path.join(ab.REPO, "tests", "diamond_cut", "neue_felgen", "porsche_gold_IMG_2695.jpg"))
bpy.ops.felge3d.car_generate()
sc.felge3d.collection.hide_render = True
sc.felge3d.collection.hide_viewport = True
ab.setup_world(sc)
sc.render.engine = "CYCLES"
sc.cycles.samples = int(os.environ.get("SAMPLES", "32"))
sc.cycles.device = "CPU"
sc.render.resolution_x, sc.render.resolution_y = 1400, 800
sc.render.film_transparent = False
sc.view_settings.view_transform = "Standard"
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -0.002))
gm = bpy.data.materials.new("Boden")
gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.01, 0.01, 0.012, 1)
bpy.context.active_object.data.materials.append(gm)
cam = bpy.data.objects.new("K", bpy.data.cameras.new("K"))
sc.collection.objects.link(cam)
sc.camera = cam
mid = Vector((-1.2285, 0.0, 0.35))
for name, loc, lens in (("dreiviertel", Vector((2.6, -4.3, 1.4)), 38), ("seite", Vector((-1.2285, -6.5, 0.6)), 45)):
    cam.location = loc
    cam.data.lens = lens
    cam.rotation_euler = (mid - loc).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, "paket_%s.png" % name)
    bpy.ops.render.render(write_still=True)
    print("gerendert:", sc.render.filepath)
