"""Detail- und Uebersichtsbilder (4:3) der STL-Teile, Eevee, mattes Grau wie in der Explosionszeichnung.
python shots.py <teile-ordner> <shot> <ausgabe.png>   shot: rad_aufhaengung | duebel_kabine | duebel_heck | pins_aufbau | reifen | hero_front | hero_heck | explosion_detail"""
import bpy, sys, os, math
from mathutils import Vector
d, shot, out = sys.argv[sys.argv.index('--')+1:sys.argv.index('--')+4] if '--' in sys.argv else sys.argv[1:4]
W, H = 1600, 1200
bpy.ops.wm.read_factory_settings(use_empty=True); sc = bpy.context.scene
POST = [(-74.0, 83.0), (74.0, 83.0), (-64.0, 181.0), (64.0, 181.0)]
AUF = [(95.0, -10.0), (125.0, -10.0), (182.0, -24.0), (168.0, 55.0)]
XJ, ZC = 33.0, 78.0
BLACK, WHITE = 0.55, 0.95
def mat(o, g):
    m = bpy.data.materials.new('m'); m.use_nodes = True; b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (g, g, g*1.02, 1); b.inputs['Roughness'].default_value = 0.55; o.data.materials.append(m)
def part(name, g, loc=(0, 0, 0), rot=(0, 0, 0), limit=450000):
    bpy.ops.wm.stl_import(filepath=os.path.join(d, name + '.stl')); o = bpy.context.object
    if len(o.data.polygons) > limit:
        m = o.modifiers.new('d', 'DECIMATE'); m.ratio = limit/len(o.data.polygons); bpy.ops.object.modifier_apply(modifier='d')
    bpy.ops.object.shade_smooth(); mat(o, g); o.location = loc; o.rotation_euler = rot; return o
def cyl(r, depth, loc, rot, g=WHITE, v=32):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, rotation=rot, vertices=v); o = bpy.context.object; bpy.ops.object.shade_smooth(); mat(o, g); return o
def wheel(cx, left, off=0.0, limit=250000):
    z = math.pi if not left else 0
    a = part('Rad_Reifen_schwarz', BLACK, (cx, (off if not left else -off), 40.0), (0, 0, z), limit)
    b = part('Rad_Felge_weiss', WHITE, (cx, (off if not left else -off), 40.0), (0, 0, z), limit); return a, b
focus = None; lens = 50; cam = (0, -300, 150); tgt = (0, 0, 60); fstop = None
if shot == 'rad_aufhaengung':
    part('Karosserie_2_Heck', BLACK, limit=600000); wheel(116.0, True, 58.0, 300000); lens, cam, tgt, fstop = 60, (290, -150, 78), (116, -88, 42), 5.0
elif shot == 'duebel_kabine':
    part('Karosserie_1_Front_Kabine', BLACK, limit=500000)
    for i, (y, z) in enumerate(POST): cyl(2.9, 24, (XJ + (22 if i < 2 else 8), y, z), (0, math.pi/2, 0))
    lens, cam, tgt, fstop = 32, (XJ + 215, 25, 140), (0, 0, 125), 8.0
elif shot == 'duebel_heck':
    part('Karosserie_2_Heck', BLACK, limit=600000)
    for i, (y, z) in enumerate(POST): cyl(2.9, 24, (XJ - (4 if i % 2 == 0 else 14) + 1, y, z), (0, math.pi/2, 0))
    lens, cam, tgt, fstop = 38, (-95, -85, 160), (XJ, 0, 125), 6.0
elif shot == 'pins_aufbau':
    part('Karosserie_2_Heck', BLACK, limit=600000); part('Karosserie_3_Aufbau', BLACK, (0, 0, 42), limit=500000)
    for (x, y) in AUF: cyl(1.5, 13, (x, y, ZC - 0.5), (0, 0, 0), WHITE, 16)
    lens, cam, tgt, fstop = 45, (205, -175, 105), (140, -5, 86), 6.0
elif shot == 'reifen':
    wheel(0.0, True, 0.0, 500000); lens, cam, tgt, fstop = 85, (95, -255, 55), (0, -82, 5), 3.5
elif shot in ('hero_front', 'hero_heck', 'explosion_detail'):
    part('Karosserie_1_Front_Kabine', BLACK); part('Karosserie_2_Heck', BLACK); part('Karosserie_3_Aufbau', BLACK)
    for cx, left in ((-159.0, True), (-159.0, False), (116.0, True), (116.0, False)): wheel(cx, left, 0.0, 120000)
    if shot == 'hero_front': lens, cam, tgt = 52, (-590, -520, 300), (0, 0, 85)
    elif shot == 'hero_heck': lens, cam, tgt = 52, (590, 480, 300), (20, 0, 85)
    else: lens, cam, tgt = 70, (110, -330, 250), (150, -20, 85)
# Boden, Licht, Welt (wie Explosionszeichnung)
bpy.ops.mesh.primitive_plane_add(size=20000, location=(0, 0, -0.3)); fl = bpy.context.object
fm = bpy.data.materials.new('fl'); fm.use_nodes = True; fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.93, 0.93, 0.94, 1); fl.data.materials.append(fm)
w = bpy.data.worlds.new('w'); sc.world = w; w.use_nodes = True; w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.95, 0.95, 0.96, 1); w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.75
ld = bpy.data.lights.new('k', 'AREA'); ld.energy = 6e5 if not fstop else 3.5e5; ld.size = 600; lo = bpy.data.objects.new('k', ld); sc.collection.objects.link(lo)
lo.location = (cam[0]*0.6 - 100, cam[1]*0.8 - 200, 650); lo.rotation_euler = (math.radians(35), 0, math.radians(-25))
cd = bpy.data.cameras.new('c'); cd.lens = lens; cd.sensor_width = 36; cd.clip_start = 5; cd.clip_end = 100000
co = bpy.data.objects.new('c', cd); sc.collection.objects.link(co); sc.camera = co; co.location = cam
t = bpy.data.objects.new('t', None); sc.collection.objects.link(t); t.location = tgt
tr = co.constraints.new('TRACK_TO'); tr.target = t; tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
if fstop: cd.dof.use_dof = True; cd.dof.focus_object = t; cd.dof.aperture_fstop = fstop
sc.render.engine = 'BLENDER_EEVEE'; sc.eevee.taa_render_samples = 64
try: sc.eevee.use_raytracing = True
except Exception: pass
sc.view_settings.view_transform = 'Standard'
sc.render.resolution_x = W; sc.render.resolution_y = H; sc.render.filepath = out
bpy.ops.render.render(write_still=True); print('fertig', shot)
