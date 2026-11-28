"""Explosionsdarstellung der STL-Teile (grau, nummeriert). python explosion.py <teile-ordner> <ausgabe.png> [breite]
Rendert mit Eevee (Teile fuer die Darstellung reduziert), schreibt <ausgabe>.json mit den Bildpositionen der Nummern."""
import bpy, sys, os, json, math
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
d, out = sys.argv[1], sys.argv[2]; W = int(sys.argv[3]) if len(sys.argv) > 3 else 1800; H = int(W*0.62)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
import math
ORDER = ['Karosserie_1_Front', 'Karosserie_2_Kabine', 'Karosserie_3_Heck', 'Rad_VL', 'Rad_VR', 'Rad_HL', 'Rad_HR'] + ['Duebel_%d' % i for i in range(1, 9)]
POST = [(-74.0, 83.0), (74.0, 83.0), (-64.0, 181.0), (64.0, 181.0)]
WH = {'Rad_VL': (-159.0, -1), 'Rad_VR': (-159.0, 1), 'Rad_HL': (116.0, -1), 'Rad_HR': (116.0, 1)}
OFF = {'Karosserie_1_Front': (-70, 0, 0), 'Karosserie_2_Kabine': (0, 0, 0), 'Karosserie_3_Heck': (70, 0, 0)}
objs = {}
def load(path, name):
    bpy.ops.wm.stl_import(filepath=path); o = bpy.context.object
    if len(o.data.polygons) > 60000:
        m = o.modifiers.new('d', 'DECIMATE'); m.ratio = 60000 / len(o.data.polygons); bpy.ops.object.modifier_apply(modifier='d')
    bpy.ops.object.shade_smooth(); o.name = name; return o
def mat(o, g, name):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (g, g, g*1.02, 1); b.inputs['Roughness'].default_value = 0.55; o.data.materials.append(m)
for n, g in (('Karosserie_1_Front', 0.62), ('Karosserie_2_Kabine', 0.78), ('Karosserie_3_Heck', 0.55)):
    o = load(os.path.join(d, n + '.stl'), n); o.location = OFF[n]; mat(o, g, n); objs[n] = o
import math
for n, (cx, sg) in WH.items():
    parts = []
    for f, g in (('Rad_Reifen_schwarz', 0.38), ('Rad_Felge_weiss', 0.92)):
        o = load(os.path.join(d, f + '.stl'), n + '_' + f); mat(o, g, n + f)
        if sg > 0: o.rotation_euler = (0, 0, math.pi)
        o.location = (cx + (0 if sg < 0 else 0), (-75 if sg < 0 else 75), 40.0 - 5.0); parts.append(o)
    objs[n] = parts[0]
for i in range(8):
    X = -40.0 if i < 4 else 45.0; y, z = POST[i % 4]
    bpy.ops.mesh.primitive_cylinder_add(radius=2.9, depth=24, location=(X, y, z), rotation=(0, math.pi/2, 0), vertices=24); o = bpy.context.object
    o.name = 'Duebel_%d' % (i+1); mat(o, 0.95, o.name); objs[o.name] = o
# Boden-Schatten
bpy.ops.mesh.primitive_plane_add(size=40000, location=(0, 0, -0.5)); fl = bpy.context.object
fm = bpy.data.materials.new('fl'); fm.use_nodes = True; fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.93, 0.93, 0.94, 1); fl.data.materials.append(fm)
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.95, 0.95, 0.96, 1); w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.75
ld = bpy.data.lights.new('k', 'AREA'); ld.energy = 6e5; ld.size = 600; lo = bpy.data.objects.new('k', ld); sc.collection.objects.link(lo); lo.location = (-250, -350, 600); lo.rotation_euler = (math.radians(40), 0, math.radians(-35))
cd = bpy.data.cameras.new('c'); cd.lens = 80; cd.sensor_width = 36; cd.clip_start = 10; cd.clip_end = 100000
co = bpy.data.objects.new('c', cd); sc.collection.objects.link(co); sc.camera = co
co.location = (-640, -1000, 1000); tg = bpy.data.objects.new('t', None); sc.collection.objects.link(tg); tg.location = (0, 0, 70)
tr = co.constraints.new('TRACK_TO'); tr.target = tg; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
sc.render.engine = 'BLENDER_EEVEE'; sc.eevee.taa_render_samples = 48
try: sc.eevee.use_raytracing = True
except Exception: pass
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = W; sc.render.resolution_y = H; sc.render.filepath = out
bpy.context.view_layer.update()
lab = {}
for name, o in objs.items():
    c = o.matrix_world @ (sum((Vector(v) for v in o.bound_box), Vector()) / 8)
    q = world_to_camera_view(sc, co, c); lab[name] = [q.x*W, (1-q.y)*H]
json.dump(lab, open(out + '.json', 'w'))
bpy.ops.render.render(write_still=True); print('fertig')
