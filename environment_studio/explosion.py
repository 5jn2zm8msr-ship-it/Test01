"""Explosionsdarstellung der STL-Teile (grau, nummeriert). python explosion.py <teile-ordner> <ausgabe.png> [breite]
Rendert mit Eevee (Teile fuer die Darstellung reduziert), schreibt <ausgabe>.json mit den Bildpositionen der Nummern."""
import bpy, sys, os, json, math
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
d, out = sys.argv[1], sys.argv[2]; W = int(sys.argv[3]) if len(sys.argv) > 3 else 1800; H = int(W*0.62)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
import math
ORDER = ['Karosserie_1_Front_Kabine', 'Karosserie_2_Heck', 'Karosserie_3_Aufbau', 'Rad_VL', 'Rad_VR', 'Rad_HL', 'Rad_HR'] + ['Duebel_%d' % i for i in range(1, 5)] + ['Pin_%d' % i for i in range(1, 5)]
POST = [(-74.0, 83.0), (74.0, 83.0), (-64.0, 181.0), (64.0, 181.0)]
AUF = [(95.0, -10.0), (125.0, -10.0), (182.0, -24.0), (168.0, 55.0)]
XJ, ZC = 33.0, 78.0
WH = {'Rad_VL': (-159.0, -1), 'Rad_VR': (-159.0, 1), 'Rad_HL': (116.0, -1), 'Rad_HR': (116.0, 1)}
OFF = {'Karosserie_1_Front_Kabine': (-45, 0, 0), 'Karosserie_2_Heck': (45, 0, 0), 'Karosserie_3_Aufbau': (45, 0, 95)}
VIEW = os.environ.get('VIEW', 'explosion')       # explosion | front34 | heck34
ASM = VIEW != 'explosion'
if ASM: OFF = {k: (0, 0, 0) for k in OFF}
SCHWARZ = float(os.environ.get('SCHWARZ', '0.10'))     # mattes Schwarzgrau
objs = {}
def load(path, name):
    bpy.ops.wm.stl_import(filepath=path); o = bpy.context.object
    if len(o.data.polygons) > 90000:
        m = o.modifiers.new('d', 'DECIMATE'); m.ratio = 90000 / len(o.data.polygons); bpy.ops.object.modifier_apply(modifier='d')
    bpy.ops.object.shade_smooth(); o.name = name; return o
def mat(o, g, name):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (g, g, g*1.02, 1); b.inputs['Roughness'].default_value = 1.0
    b.inputs['Specular IOR Level'].default_value = 0.0; o.data.materials.append(m)
for n in ('Karosserie_1_Front_Kabine', 'Karosserie_2_Heck', 'Karosserie_3_Aufbau'):
    o = load(os.path.join(d, n + '.stl'), n); o.location = OFF[n]; mat(o, SCHWARZ, n); objs[n] = o
for n, (cx, sg) in WH.items():
    parts = []
    for f, g in (('Rad_Reifen_schwarz', SCHWARZ), ('Rad_Felge_weiss', 0.85)):
        o = load(os.path.join(d, f + '.stl'), n + '_' + f); mat(o, g, n + f)
        if sg > 0: o.rotation_euler = (0, 0, math.pi)
        o.location = (cx, (0 if ASM else (-75 if sg < 0 else 75)), 40.0 if ASM else 35.0); parts.append(o)
    objs[n] = parts[0]
if not ASM:
    for i in range(4):
        y, z = POST[i]
        bpy.ops.mesh.primitive_cylinder_add(radius=2.9, depth=24, location=(XJ, y, z), rotation=(0, math.pi/2, 0), vertices=24); o = bpy.context.object
        o.name = 'Duebel_%d' % (i+1); mat(o, 0.85, o.name); objs[o.name] = o
        x, y2 = AUF[i]
        bpy.ops.mesh.primitive_cylinder_add(radius=1.5, depth=13, location=(x + 45, y2, ZC + 95 - 6), vertices=16); o = bpy.context.object
        o.name = 'Pin_%d' % (i+1); mat(o, 0.85, o.name); objs[o.name] = o
# Boden-Schatten
bpy.ops.mesh.primitive_plane_add(size=40000, location=(0, 0, -0.5)); fl = bpy.context.object
fm = bpy.data.materials.new('fl'); fm.use_nodes = True; fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.93, 0.93, 0.94, 1); fl.data.materials.append(fm)
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.95, 0.95, 0.96, 1); w.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
ld = bpy.data.lights.new('k', 'AREA'); ld.energy = 9e5; ld.size = 600; lo = bpy.data.objects.new('k', ld); sc.collection.objects.link(lo); lo.location = (-250, -350, 600); lo.rotation_euler = (math.radians(40), 0, math.radians(-35))
cd = bpy.data.cameras.new('c'); cd.lens = 70 if not ASM else 62; cd.sensor_width = 36; cd.clip_start = 10; cd.clip_end = 100000
co = bpy.data.objects.new('c', cd); sc.collection.objects.link(co); sc.camera = co
co.location = {'explosion': (-420, -720, 1500), 'front34': (-640, -560, 330), 'heck34': (640, 560, 330)}[VIEW]; tg = bpy.data.objects.new('t', None); sc.collection.objects.link(tg); tg.location = (0, 0, 70 if not ASM else 85)
tr = co.constraints.new('TRACK_TO'); tr.target = tg; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
sc.render.engine = 'BLENDER_EEVEE'; sc.eevee.taa_render_samples = 48
try: sc.eevee.use_raytracing = True
except Exception: pass
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = W; sc.render.resolution_y = H; sc.render.filepath = out
bpy.context.view_layer.update()
lab = {}
dg = bpy.context.evaluated_depsgraph_get()
for name, o in objs.items():
    c = o.matrix_world @ (sum((Vector(v) for v in o.bound_box), Vector()) / 8)
    q = world_to_camera_view(sc, co, c)
    if ASM:
        dr_ = (c - co.location).normalized(); ok, loc, nrm, idx, hit, mw = sc.ray_cast(dg, co.location, dr_)
        base = name.split('_')[0] + '_' + name.split('_')[1] if name.startswith('Rad') else name
        if name != 'Karosserie_2_Kabine' and not (ok and hit is not None and (hit.name == name or hit.name.startswith(name + '_'))): continue
    lab[name] = [q.x*W, (1-q.y)*H]
json.dump(lab, open(out + '.json', 'w'))
bpy.ops.render.render(write_still=True); print('fertig')
