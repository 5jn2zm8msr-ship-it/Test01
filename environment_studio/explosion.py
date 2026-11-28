"""Explosionsdarstellung der STL-Teile (grau, nummeriert). python explosion.py <teile-ordner> <ausgabe.png> [breite]
Rendert mit Eevee (Teile fuer die Darstellung reduziert), schreibt <ausgabe>.json mit den Bildpositionen der Nummern."""
import bpy, sys, os, json, math
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
d, out = sys.argv[1], sys.argv[2]; W = int(sys.argv[3]) if len(sys.argv) > 3 else 1800; H = int(W*0.62)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
ORDER = ['Karosserie_vorn', 'Karosserie_hinten', 'Rad_VL', 'Rad_VR', 'Rad_HL', 'Rad_HR', 'Spiegel_L', 'Spiegel_R', 'Reserverad', 'Duebel_1', 'Duebel_2', 'Duebel_3', 'Duebel_4']
BOSS = [(-71.0, 78.0), (71.0, 78.0), (-66.0, 182.0), (66.0, 182.0)]
OFF = {'Karosserie_vorn': (-70, 0, 0), 'Karosserie_hinten': (70, 0, 0), 'Rad_VL': (0, -75, -5), 'Rad_VR': (0, 75, -5), 'Rad_HL': (0, -75, -5), 'Rad_HR': (0, 75, -5),
       'Spiegel_L': (-5, -45, 45), 'Spiegel_R': (-5, 45, 45), 'Reserverad': (0, -70, 0)}
GREY = [0.62, 0.55, 0.78, 0.70, 0.78, 0.70, 0.9, 0.9, 0.82, 0.95, 0.95, 0.95, 0.95]
objs = {}
for i, name in enumerate(ORDER):
    p = os.path.join(d, name + '.stl')
    if name.startswith('Duebel'):
        y, z = BOSS[int(name[-1])-1]
        bpy.ops.mesh.primitive_cylinder_add(radius=2.9, depth=24, location=(-8, y, z), rotation=(0, math.pi/2, 0), vertices=24); o = bpy.context.object
    else:
        bpy.ops.wm.stl_import(filepath=p); o = bpy.context.object
        if len(o.data.polygons) > 60000:
            m = o.modifiers.new('d', 'DECIMATE'); m.ratio = 60000 / len(o.data.polygons); bpy.ops.object.modifier_apply(modifier='d')
        bpy.ops.object.shade_smooth()
        o.location = OFF.get(name, (0, 0, 0))
    o.name = name; objs[name] = o
    mat = bpy.data.materials.new(name); mat.use_nodes = True; b = mat.node_tree.nodes['Principled BSDF']
    g = GREY[i]; b.inputs['Base Color'].default_value = (g, g, g*1.02, 1); b.inputs['Roughness'].default_value = 0.55
    o.data.materials.append(mat)
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
