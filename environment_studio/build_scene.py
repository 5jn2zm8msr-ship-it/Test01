"""Defender-D130-Studio (Eevee): weisser Hohlkehlen-Hintergrund, Softboxen, 3 Kameras wie in den Referenzfotos.
Aufruf:  xvfb-run -a python build_scene.py <glb> <ausgabeordner> [skala 0.1-1] [shots, z. B. 10,8,6]
Einheiten: Meter. Auto auf 2,02 m Breite skaliert (wie meshy_cars), Boden z=0, Mitte auf X/Y=0.
"""
import bpy, sys, math, os, mathutils
from mathutils import Vector

GLB = sys.argv[sys.argv.index('--')+1] if '--' in sys.argv else sys.argv[1]
OUT = sys.argv[sys.argv.index('--')+2] if '--' in sys.argv else sys.argv[2]
rest = sys.argv[(sys.argv.index('--')+3 if '--' in sys.argv else 3):]
SCALE = float(rest[0]) if rest else 1.0
SHOTS = rest[1].split(',') if len(rest) > 1 else ['10', '8', '6']
SAMPLES = int(rest[2]) if len(rest) > 2 else 48
FRONT_SIGN = -1   # Meshy-README: Front nach -X (wird unten per Test geprueft/gedreht)
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ---------------- Auto -----------------
bpy.ops.import_scene.gltf(filepath=GLB)
car = [o for o in bpy.data.objects if o.type == 'MESH'][0]
car.name = 'Defender_D130'
bpy.context.view_layer.objects.active = car
d = car.dimensions
breite = min(d.x, d.y)
f = 2.02 / breite
car.scale = (f, f, f)
bpy.ops.object.transform_apply(scale=True)
bb = [car.matrix_world @ Vector(c) for c in car.bound_box]
mn = Vector((min(b[i] for b in bb) for i in range(3))); mx = Vector((max(b[i] for b in bb) for i in range(3)))
car.location = (-(mn.x+mx.x)/2, -(mn.y+mx.y)/2, -mn.z)
bpy.ops.object.transform_apply(location=True)
print('Auto m:', tuple(round(x, 3) for x in car.dimensions))
if os.environ.get('FLIP'):
    car.rotation_euler.z = math.pi; bpy.ops.object.transform_apply(rotation=True)

# ---------------- Eevee-Material -----------------
# Das glTF-Material (Basisfarbe, ORM, Normal) bleibt; Eevee-tauglich gemacht:
# kein Alpha-Blend, Rauheit im Mattbereich, leichter Clearcoat nur fuer die Felgen/Lack-Reflexe entfaellt (Lack ist matt).
mat = car.data.materials[0]
mat.blend_method = 'OPAQUE' if hasattr(mat, 'blend_method') else None
bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
bsdf.inputs['Specular IOR Level'].default_value = 0.25
mat.use_backface_culling = False
KARO = float(os.environ.get('KARO', '0.56'))   # Lack/Karosserie dunkler und neutraler (Referenz: fast Schwarz, matt)
for l in list(mat.node_tree.links):
    if l.to_node == bsdf and l.to_socket.name == 'Base Color':
        mxn = mat.node_tree.nodes.new('ShaderNodeMix'); mxn.data_type = 'RGBA'; mxn.blend_type = 'MULTIPLY'
        mxn.inputs['Factor'].default_value = 1.0; mxn.inputs['B'].default_value = (KARO, KARO, KARO*1.02, 1)
        mat.node_tree.links.new(l.from_socket, mxn.inputs['A']); mat.node_tree.links.new(mxn.outputs['Result'], bsdf.inputs['Base Color']); break
RAU_MIN = float(os.environ.get('RAU_MIN', '0.62'))
nt = mat.node_tree
for l in list(nt.links):
    if l.to_node == bsdf and l.to_socket.name == 'Roughness':
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['From Min'].default_value = 0; mr.inputs['From Max'].default_value = 1
        mr.inputs['To Min'].default_value = RAU_MIN; mr.inputs['To Max'].default_value = 1.0
        nt.links.new(l.from_socket, mr.inputs['Value']); nt.links.new(mr.outputs['Result'], bsdf.inputs['Roughness'])
        break

# ---------------- Studio -----------------
def mk_mat(name, col, rough, spec=0.3):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*col, 1); b.inputs['Roughness'].default_value = rough
    b.inputs['Specular IOR Level'].default_value = spec
    return m
# Hohlkehle: Boden, hinten weit gerundet; Wand rund um das Auto weit weg -> keine Horizontlinie
import bmesh
me = bpy.data.meshes.new('Cyc'); cyc = bpy.data.objects.new('Studio_Cyc', me); sc.collection.objects.link(cyc)
bm = bmesh.new()
R_in = 22.0       # Boden bis hier eben
R_curve = 6.0
prof = [(R_in+R_curve*math.sin(a), R_curve-R_curve*math.cos(a)) for a in [i*math.pi/2/12 for i in range(13)]]
prof = [(0.0, 0.0)] + prof + [(R_in+R_curve, R_curve+80)]
N = 72
rings = []
for (r, z) in prof:
    rings.append([bm.verts.new((r*math.cos(2*math.pi*i/N), r*math.sin(2*math.pi*i/N), z)) for i in range(N)])
for k in range(len(rings)-1):
    for i in range(N):
        a, b = rings[k][i], rings[k][(i+1) % N]; c, dd = rings[k+1][(i+1) % N], rings[k+1][i]
        try: bm.faces.new((a, b, c, dd))
        except Exception: pass
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me); bm.free()
for p in me.polygons: p.use_smooth = True
cm = mk_mat('Studio_Weiss', (0.88, 0.88, 0.89), 0.6, 0.1)
cnt = cm.node_tree; cb = cnt.nodes['Principled BSDF']
tc = cnt.nodes.new('ShaderNodeTexCoord'); sx = cnt.nodes.new('ShaderNodeSeparateXYZ'); mr = cnt.nodes.new('ShaderNodeMapRange')
cnt.links.new(tc.outputs['Object'], sx.inputs['Vector'])
# "Hoehe" h = z + 0.5*max(0, r-5): Boden nahe am Auto ist schattenfaehig, weiter weg und an der Wand leuchtet die Hohlkehle gleichmaessig weiss
vx = cnt.nodes.new('ShaderNodeCombineXYZ'); cnt.links.new(sx.outputs['X'], vx.inputs['X']); cnt.links.new(sx.outputs['Y'], vx.inputs['Y'])
ln = cnt.nodes.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'; cnt.links.new(vx.outputs['Vector'], ln.inputs[0])
m1 = cnt.nodes.new('ShaderNodeMath'); m1.operation = 'SUBTRACT'; m1.inputs[1].default_value = 5.0; cnt.links.new(ln.outputs['Value'], m1.inputs[0])
m2 = cnt.nodes.new('ShaderNodeMath'); m2.operation = 'MAXIMUM'; m2.inputs[1].default_value = 0.0; cnt.links.new(m1.outputs['Value'], m2.inputs[0])
m3 = cnt.nodes.new('ShaderNodeMath'); m3.operation = 'MULTIPLY'; m3.inputs[1].default_value = 1.4; cnt.links.new(m2.outputs['Value'], m3.inputs[0])
m4 = cnt.nodes.new('ShaderNodeMath'); m4.operation = 'ADD'; cnt.links.new(m3.outputs['Value'], m4.inputs[0]); cnt.links.new(sx.outputs['Z'], m4.inputs[1])
mr.inputs['From Min'].default_value = 0.0; mr.inputs['From Max'].default_value = 5.0; mr.clamp = True
mr.inputs['To Min'].default_value = float(os.environ.get('EM_BODEN', '0.03')); mr.inputs['To Max'].default_value = float(os.environ.get('EM_WAND', '0.72'))
cnt.links.new(m4.outputs['Value'], mr.inputs['Value'])
nz = cnt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 1.6; nz.inputs['Detail'].default_value = 8; nz.inputs['Roughness'].default_value = 0.65
cnt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
nr = cnt.nodes.new('ShaderNodeMapRange'); nr.inputs['To Min'].default_value = 0.38; nr.inputs['To Max'].default_value = 0.78
cnt.links.new(nz.outputs['Fac'], nr.inputs['Value']); cnt.links.new(nr.outputs['Result'], cb.inputs['Roughness'])
nz2 = cnt.nodes.new('ShaderNodeTexNoise'); nz2.inputs['Scale'].default_value = 260; nz2.inputs['Detail'].default_value = 4
cnt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
bp = cnt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.08; bp.inputs['Distance'].default_value = 0.01
cnt.links.new(nz2.outputs['Fac'], bp.inputs['Height']); cnt.links.new(bp.outputs['Normal'], cb.inputs['Normal'])
cb.inputs['Emission Color'].default_value = (0.96, 0.96, 0.97, 1)
cnt.links.new(mr.outputs['Result'], cb.inputs['Emission Strength'])
cyc.data.materials.append(cm)
cyc.visible_camera = True

# Kontaktschatten: weiche dunkle Ellipse unter dem Auto + engere unter den Reifen (zusaetzlich zu den Lichtschatten)
def schatten(name, sx_, sy_, dichte, z):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, z)); o = bpy.context.object; o.name = name
    o.scale = (sx_*2, sy_*2, 1); bpy.ops.object.transform_apply(scale=True)
    m = bpy.data.materials.new(name); m.use_nodes = True; n = m.node_tree; n.nodes.clear()
    tcx = n.nodes.new('ShaderNodeTexCoord'); mp = n.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1/sx_, 1/sy_, 1)
    gr = n.nodes.new('ShaderNodeTexGradient'); gr.gradient_type = 'SPHERICAL'
    cr = n.nodes.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].position = 0.0; cr.color_ramp.elements[1].position = 0.85
    cr.color_ramp.elements[0].color = (0, 0, 0, 1); cr.color_ramp.elements[1].color = (1, 1, 1, 1)
    cr.color_ramp.interpolation = 'LINEAR'
    pw = n.nodes.new('ShaderNodeMath'); pw.operation = 'POWER'; pw.inputs[1].default_value = 1.7
    mu = n.nodes.new('ShaderNodeMath'); mu.operation = 'MULTIPLY'; mu.inputs[1].default_value = dichte
    tr_ = n.nodes.new('ShaderNodeBsdfTransparent'); bk = n.nodes.new('ShaderNodeBsdfDiffuse'); bk.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1)
    mx = n.nodes.new('ShaderNodeMixShader'); out = n.nodes.new('ShaderNodeOutputMaterial')
    n.links.new(tcx.outputs['Object'], mp.inputs['Vector']); n.links.new(mp.outputs['Vector'], gr.inputs['Vector'])
    n.links.new(gr.outputs['Fac'], cr.inputs['Fac']); n.links.new(cr.outputs['Color'], pw.inputs[0]); n.links.new(pw.outputs['Value'], mu.inputs[0])
    n.links.new(mu.outputs['Value'], mx.inputs['Fac']); n.links.new(tr_.outputs['BSDF'], mx.inputs[1]); n.links.new(bk.outputs['BSDF'], mx.inputs[2])
    n.links.new(mx.outputs['Shader'], out.inputs['Surface'])
    try: m.surface_render_method = 'BLENDED'
    except Exception: m.blend_method = 'BLEND'
    m.use_backface_culling = False
    o.data.materials.append(m); o.visible_shadow = False
    return o
def schatten_wolke(z=0.004):
    """Breites, wolkig-fleckiges Schattenfeld unter dem Auto wie im Referenzfoto (Frontansicht):
    grau-blau, seitlich ueber die Reifen hinaus, vor dem Stossfaenger weich auslaufend, mit rauchiger Noise-Struktur."""
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, z)); o = bpy.context.object; o.name = 'Schattenfeld'
    o.scale = (14, 7, 1); bpy.ops.object.transform_apply(scale=True)
    m = bpy.data.materials.new('Schattenfeld'); m.use_nodes = True; n = m.node_tree; n.nodes.clear()
    L = lambda a, b, c, d: n.links.new(a.outputs[b] if isinstance(b, str) else a.outputs[b], c.inputs[d])
    tcx = n.nodes.new('ShaderNodeTexCoord'); sp = n.nodes.new('ShaderNodeSeparateXYZ'); L(tcx, 'Object', sp, 'Vector')
    def smooth(src_sock_node, src, a, b, name):
        r = n.nodes.new('ShaderNodeMapRange'); r.interpolation_type = 'SMOOTHSTEP'; r.clamp = True
        r.inputs['From Min'].default_value = a; r.inputs['From Max'].default_value = b
        n.links.new(src_sock_node.outputs[src], r.inputs['Value']); return r
    # Laenge: Front liegt bei -X (FRONT_SIGN), Schatten reicht ~1.1 m ueber die Front hinaus, hinten kuerzer
    fx = smooth(sp, 'X', -3.0, -2.0, 'fx')
    fr = smooth(sp, 'X', 3.4, 1.6, 'fr')
    ab = n.nodes.new('ShaderNodeMath'); ab.operation = 'ABSOLUTE'; L(sp, 'Y', ab, 0)
    fy = smooth(ab, 'Value', 1.8, 1.0, 'fy')
    m1 = n.nodes.new('ShaderNodeMath'); m1.operation = 'MULTIPLY'; L(fx, 'Result', m1, 0); L(fr, 'Result', m1, 1)
    m2 = n.nodes.new('ShaderNodeMath'); m2.operation = 'MULTIPLY'; L(m1, 'Value', m2, 0); L(fy, 'Result', m2, 1)
    # rauchige Struktur: verzerrtes Noise, grosse Wolken + feines Detail
    nz = n.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 0.9; nz.inputs['Detail'].default_value = 9
    nz.inputs['Roughness'].default_value = 0.62; nz.inputs['Distortion'].default_value = 1.4
    L(tcx, 'Object', nz, 'Vector')
    nr = n.nodes.new('ShaderNodeMapRange'); nr.inputs['From Min'].default_value = 0.30; nr.inputs['From Max'].default_value = 0.70
    nr.inputs['To Min'].default_value = 0.35; nr.inputs['To Max'].default_value = 1.15; nr.clamp = True
    L(nz, 'Fac', nr, 'Value')
    m3 = n.nodes.new('ShaderNodeMath'); m3.operation = 'MULTIPLY'; L(m2, 'Value', m3, 0); L(nr, 'Result', m3, 1)
    m4 = n.nodes.new('ShaderNodeMath'); m4.operation = 'MULTIPLY'; m4.inputs[1].default_value = float(os.environ.get('SCH', '0.50')); m4.use_clamp = True; L(m3, 'Value', m4, 0)
    tr_ = n.nodes.new('ShaderNodeBsdfTransparent'); bk = n.nodes.new('ShaderNodeBsdfDiffuse'); bk.inputs['Color'].default_value = (0.012, 0.022, 0.035, 1)
    mx = n.nodes.new('ShaderNodeMixShader'); out = n.nodes.new('ShaderNodeOutputMaterial')
    L(m4, 'Value', mx, 0); L(tr_, 'BSDF', mx, 1); L(bk, 'BSDF', mx, 2); L(mx, 'Shader', out, 'Surface')
    try: m.surface_render_method = 'BLENDED'
    except Exception: m.blend_method = 'BLEND'
    o.data.materials.append(m); o.visible_shadow = False
    return o
schatten_wolke()
schatten('Kontaktschatten_Reifen', 2.3, 1.15, float(os.environ.get('SCH2', '0.55')), 0.006)

# Welt: sehr helles, leicht kuehles Grau (Streulicht der weissen Hohlkehle)
w = bpy.data.worlds.new('Studio'); sc.world = w; w.use_nodes = True
bgn = w.node_tree.nodes['Background']
bgn.inputs['Color'].default_value = (0.82, 0.83, 0.85, 1); bgn.inputs['Strength'].default_value = float(os.environ.get('WORLD', '0.13'))

LK = float(os.environ.get('LK', '0.045'))
def area(name, loc, target, size, power, color=(1, 1, 1), shape='RECTANGLE', size_y=None, spread=1.0):
    ld = bpy.data.lights.new(name, 'AREA'); ld.shape = shape; ld.size = size
    if size_y: ld.size_y = size_y
    ld.energy = power; ld.color = color; ld.spread = spread
    o = bpy.data.objects.new(name, ld); sc.collection.objects.link(o); o.location = loc
    tr = o.constraints.new('TRACK_TO'); tr.track_axis = 'TRACK_NEGATIVE_Z'; tr.up_axis = 'UP_Y'
    tgt = bpy.data.objects.get('Ziel') or bpy.data.objects.new('Ziel', None)
    if tgt.name not in sc.collection.objects: sc.collection.objects.link(tgt)
    tgt.location = target; tr.target = tgt
    return o
car_coll = bpy.data.collections.new('Auto'); sc.collection.children.link(car_coll)
for c_ in list(car.users_collection): c_.objects.unlink(car)
car_coll.objects.link(car)
def nur_auto(o):
    try: o.light_linking.receiver_collection = car_coll
    except Exception as e: print('Light-Linking nicht moeglich:', e)
# grosse Deckensoftbox (weich, Hauptlicht), seitliche Streifenboxen fuer Kantenlicht, Aufhellung vorn
area('Softbox_Decke', (-1.5, 1.0, 7.5), (0, 0, 0.8), 9.0, 12000*LK, (1.0, 0.99, 0.98), size_y=7.0)
area('Streifen_links', (-7.5, -6.0, 3.2), (0, 0, 0.9), 1.8, 5000*LK, (0.97, 0.99, 1.0), size_y=6.0)
area('Streifen_rechts', (7.0, 6.5, 3.5), (0, 0, 0.9), 1.8, 4000*LK, (0.97, 0.99, 1.0), size_y=6.0)
area('Aufheller_vorn', (-9.0, 4.0, 1.5), (0, 0, 0.8), 6.0, 2200*LK, (0.96, 0.98, 1.0), size_y=3.0)
# Nur fuers Auto (Light-Linking): weiche Formgebung, Streiflicht auf Kanten, Glanz auf Hauben-/Seitenflaechen
LA = float(os.environ.get('LA', '0.085'))
nur_auto(area('Auto_Deckenbox', (-1.0, 0.5, 6.0), (0, 0, 0.9), 7.0, 12000*LA, (1.0, 0.99, 0.98), size_y=5.0))
nur_auto(area('Auto_Kante_links', (-6.5, -5.5, 2.4), (0, 0, 1.0), 1.5, 5000*LA, (0.96, 0.98, 1.0), size_y=4.0))
nur_auto(area('Auto_Kante_rechts', (6.5, 6.0, 2.6), (0, 0, 1.0), 1.5, 4500*LA, (0.96, 0.98, 1.0), size_y=4.0))
nur_auto(area('Auto_Front', (-8.0, 1.0, 1.2), (0, 0, 0.9), 5.0, 3500*LA, (0.97, 0.98, 1.0), size_y=3.0))
nur_auto(area('Auto_Heck', (8.0, -1.0, 1.4), (0, 0, 0.9), 5.0, 3000*LA, (0.97, 0.98, 1.0), size_y=3.0))

# ---------------- Kameras -----------------
# Auto: Laenge entlang X. Auto-Front = FRONT_SIGN*X.
L = car.dimensions.x; B = car.dimensions.y; H = car.dimensions.z
fs = FRONT_SIGN if not os.environ.get('FLIP') else -FRONT_SIGN
def cam(name, loc, target, focal, shift=(0, 0)):
    cd = bpy.data.cameras.new(name); cd.lens = focal; cd.sensor_width = 36; cd.sensor_fit = 'HORIZONTAL'
    cd.shift_x, cd.shift_y = shift
    cd.clip_end = 200
    o = bpy.data.objects.new(name, cd); sc.collection.objects.link(o); o.location = loc
    t = bpy.data.objects.new(name+'_Ziel', None); sc.collection.objects.link(t); t.location = target
    c = o.constraints.new('TRACK_TO'); c.target = t; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
    return o
# Auto faehrt im Bild nach links, wir sehen die +Y-Seite? -> Seite wird per Spiegel-Test festgelegt (SIDE)
side = float(os.environ.get('SIDE', '-1'))
CAMS = {
  # 10/10: schraeg von vorn, Augenhoehe etwas ueber der Haube, Auto fuellt das Bild
  '10': cam('Kamera_10_front_schraeg', (fs*8.9, side*8.2, 1.45), (0.0, 0, 1.0), 85),
  # 8/10: schraeg von hinten, etwas niedriger, weitwinkliger
  '8':  cam('Kamera_8_heck_schraeg', (-fs*7.4, side*6.8, 1.15), (0.1, 0, 0.95), 75),
  # 6/10: frontal, niedrig (Mitte Kuehlergrill), Tele
  '6':  cam('Kamera_6_front', (fs*8.1, 0, 0.95), (0, 0, 1.12), 100),
}

# ---------------- Render (Eevee) -----------------
sc.render.engine = 'BLENDER_EEVEE'
ee = sc.eevee
ee.taa_render_samples = SAMPLES
for k, v in dict(use_raytracing=True, use_shadows=True, use_volumetric_shadows=False, shadow_ray_count=2, shadow_step_count=6,
                 use_shadow_jitter_viewport=False, fast_gi_method='GLOBAL_ILLUMINATION').items():
    try: setattr(ee, k, v)
    except Exception as e: print('Eevee-Option fehlt:', k, e)
try:
    ee.ray_tracing_options.resolution_scale = '1'
    ee.ray_tracing_options.use_denoise = True
except Exception as e: print(e)
sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
sc.view_settings.exposure = float(os.environ.get('EXPO', '0'))
sc.render.resolution_x = int(1179*SCALE); sc.render.resolution_y = int(1472*SCALE); sc.render.resolution_percentage = 100
sc.render.film_transparent = False
sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_depth = '16'

if os.environ.get('SAVE_BLEND'):
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'defender_studio.blend'))
for k in SHOTS:
    sc.camera = CAMS[k]
    sc.render.filepath = os.path.join(OUT, f'roh_{k}.png')
    bpy.ops.render.render(write_still=True)
    print('fertig', k)
