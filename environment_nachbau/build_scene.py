"""Rekonstruktion der Betonbox aus dem Referenzfoto (IMG_2730) in Blender (bpy, Cycles).

Aufruf: python build_scene.py <out.png> [Aufloesung] [Samples] [--param=wert ...]
Koordinaten: Kamera im Ursprung (Meter), Welt-Y = Richtung der linken Wand, Z oben.
Kamera aus den Fluchtpunkten des Fotos abgeleitet: 35 mm, Augenhoehe 1,6 m, Drehung 31,6 Grad, Horizont bei y=254/720.
Licht: zwei Sonnen mit Light-Linking (Boden/Decke/Auto vs. linke Wand), weil das Foto nicht
streng mit einer einzigen Sonne vereinbar ist (Bodenkeil: Sonne fast von hinten; Lichtflaeche links: Sonne von rechts hinten).
"""
import math, os, sys
import bpy
from mathutils import Vector, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1]
RES = int(sys.argv[2]) if len(sys.argv) > 2 else 540
SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 48
opt = dict(a.lstrip('-').split('=') for a in sys.argv[4:] if '=' in a)
F = lambda k, d: float(opt.get(k, d))

CAM_H, FOCAL, CAM_YAW = 1.6, 35.0, 31.6
HORIZON_PX = F('horizon', 254)
WALL_X, BACK_Y, WALL_H = -4.94, 9.06, 2.8
SLAB_EDGE_Y, SLAB_T = F('slab_y', 5.4), 0.45
CAR_LEN = F('car_len', 4.25)
CAR_X, CAR_Y = F('car_x', -3.55), F('car_y', 5.95)
CAR_YAW = F('car_yaw', 4.0)
SUN_A = Vector((F('ax', 0.10), F('ay', -0.75), F('az', -1.0)))    # Boden/Decke/Auto/Pfeiler/Rueckwand
SUN_W = Vector((F('wx', -0.40), F('wy', -0.85), F('wz', -1.0)))   # nur linke Wand
STR_A, STR_W = F('sunA', 34.0), F('sunW', 24.0)
SKY = F('sky', 0.85)
EXPO = F('expo', 2.5)
DIRT = F('dirt', 1.7)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ---------------------------------------------------------------- Node-Helfer
def mixc(nt, fac, a, b, blend='MIX'):
    m = nt.nodes.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.blend_type = blend
    if isinstance(fac, (int, float)): m.inputs[0].default_value = fac
    else: nt.links.new(fac, m.inputs[0])
    for idx, v in ((6, a), (7, b)):
        if isinstance(v, tuple): m.inputs[idx].default_value = v if len(v) == 4 else (*v, 1)
        else: nt.links.new(v, m.inputs[idx])
    return m.outputs[2]

def ramp(nt, fac, stops):
    r = nt.nodes.new('ShaderNodeValToRGB'); el = r.color_ramp.elements
    el[0].position, el[0].color = stops[0][0], (*stops[0][1], 1)
    el[1].position, el[1].color = stops[-1][0], (*stops[-1][1], 1)
    for pos, col in stops[1:-1]: e = el.new(pos); e.color = (*col, 1)
    nt.links.new(fac, r.inputs[0]); return r.outputs[0]

def noise(nt, vec, scale, detail=6, rough=0.55, dist=0.0):
    n = nt.nodes.new('ShaderNodeTexNoise'); n.noise_dimensions = '3D'
    n.inputs['Scale'].default_value = scale; n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = rough; n.inputs['Distortion'].default_value = dist
    nt.links.new(vec, n.inputs['Vector']); return n.outputs['Fac']

def mapping(nt, vec, scale):
    m = nt.nodes.new('ShaderNodeMapping')
    m.inputs['Scale'].default_value = scale if isinstance(scale, tuple) else (scale,) * 3
    nt.links.new(vec, m.inputs['Vector']); return m.outputs[0]

def gray(v): return (v, v, v)

_imgs = {}
def img(name, cs):
    if (name, cs) not in _imgs:
        im = bpy.data.images.load(os.path.join(HERE, 'textures', name)); im.colorspace_settings.name = cs; _imgs[(name, cs)] = im
    return _imgs[(name, cs)]

def dirty_concrete(name, A, B, scale, kind, tint=(1, 1, 1), bright=1.0, rough_mul=1.0, nor=0.7,
                   mottle=0.25, stain=0.35, streak=0.0, pits=0.4, ao_dirt=0.4, wet=0.0, brown=0.0, rough_min=0.6, fg_dark=0.0, desat=0.4, joints=0.0):
    """Beton mit Schmutz: zwei gemischte Poly-Haven-Texturen, Flecken, Laufspuren, Poren, Ecken-AO, nasse Stellen."""
    mt = bpy.data.materials.new(name); mt.use_nodes = True
    nt = mt.node_tree; nt.nodes.clear(); N = nt.nodes.new; L = nt.links.new
    d_ = DIRT
    cap = lambda v: min(v, 0.62)   # Flecken nie tiefschwarz
    tc = N('ShaderNodeTexCoord'); obj = tc.outputs['Object']
    def tex(prefix, n, cs, sc_):
        t = N('ShaderNodeTexImage'); t.image = img(f'{prefix}_{n}_2k.jpg', cs); t.projection = 'BOX'; t.projection_blend = 0.25
        L(mapping(nt, obj, sc_), t.inputs['Vector']); return t
    dA, rA, nA = tex(A, 'diff', 'sRGB', scale), tex(A, 'rough', 'Non-Color', scale), tex(A, 'nor_gl', 'Non-Color', scale)
    dB, rB = tex(B, 'diff', 'sRGB', scale * 0.43), tex(B, 'rough', 'Non-Color', scale * 0.43)
    ab = ramp(nt, noise(nt, obj, 0.3, 6), [(0.38, gray(0)), (0.62, gray(1))])           # Wechsel zwischen den Texturen
    col = mixc(nt, ab, dA.outputs['Color'], dB.outputs['Color'])
    hsv = N('ShaderNodeHueSaturation'); hsv.inputs['Saturation'].default_value = desat; L(col, hsv.inputs['Color']); col = hsv.outputs['Color']
    col = mixc(nt, 1.0, col, (*[c * bright for c in tint], 1), 'MULTIPLY')
    # mittelfrequente Wolken
    mot = ramp(nt, noise(nt, obj, 1.7, 8, 0.62), [(0.30, gray(1 - cap(mottle * d_))), (0.70, gray(1))])
    col = mixc(nt, 1.0, col, mot, 'MULTIPLY')
    # grosse Flecken (Feuchte, Verschmutzung)
    stain_m = ramp(nt, noise(nt, obj, 0.55, 10, 0.6, 0.4), [(0.42, gray(1 - cap(stain * d_))), (0.66, gray(1))])
    tone = (1.0, 1 - 0.05 * brown, 1 - 0.14 * brown)
    col = mixc(nt, 1.0, col, mixc(nt, 1.0, stain_m, tone, 'MULTIPLY'), 'MULTIPLY')
    # Laufspuren von oben nach unten (Regenwasser) - nur senkrechte Flaechen
    if streak > 0:
        sv = mapping(nt, obj, (2.6, 2.6, 0.16) if kind != 'floor' else (2.2, 0.18, 2.2))
        st = ramp(nt, noise(nt, sv, 1.0, 5, 0.7), [(0.48, gray(1 - cap(streak * d_))), (0.78, gray(1))])
        col = mixc(nt, 1.0, col, mixc(nt, 1.0, st, tone, 'MULTIPLY'), 'MULTIPLY')
    # Poren / Lunker
    if pits > 0:
        vr = N('ShaderNodeTexVoronoi'); vr.feature = 'F1'; vr.inputs['Scale'].default_value = 55
        L(obj, vr.inputs['Vector'])
        density = ramp(nt, noise(nt, obj, 2.2, 3), [(0.45, gray(0)), (0.62, gray(1))])
        dot = ramp(nt, vr.outputs['Distance'], [(0.0, gray(1 - cap(pits * d_))), (0.10, gray(1))])
        col = mixc(nt, density, col, mixc(nt, 1.0, col, dot, 'MULTIPLY'))
    if fg_dark > 0:   # Vordergrund (vor dem Lichtkeil) dunkler und fleckiger wie im Foto
        sy = nt.nodes.new('ShaderNodeSeparateXYZ'); L(obj, sy.inputs['Vector'])
        fgm = ramp(nt, sy.outputs['Y'], [(2.0, gray(1 - fg_dark)), (3.6, gray(1))])
        fgn = ramp(nt, noise(nt, obj, 0.9, 8, 0.6, 0.3), [(0.35, gray(0.55)), (0.65, gray(1))])
        col = mixc(nt, 1.0, col, mixc(nt, 1.0, fgm, fgn, 'MULTIPLY'), 'MULTIPLY')
    if joints > 0:   # Schalungsstoesse: waagerecht alle 1,2 m, senkrecht alle 2,4 m
        sx = N('ShaderNodeSeparateXYZ'); L(obj, sx.inputs['Vector'])
        def groove(coord, period, w):
            dv = N('ShaderNodeMath'); dv.operation = 'DIVIDE'; dv.inputs[1].default_value = period / 2; L(coord, dv.inputs[0])
            pp = N('ShaderNodeMath'); pp.operation = 'PINGPONG'; pp.inputs[1].default_value = 1.0; L(dv.outputs[0], pp.inputs[0])
            return ramp(nt, pp.outputs[0], [(0.0, gray(1 - cap(joints * d_))), (w, gray(1))])
        uu = N('ShaderNodeMath'); uu.operation = 'ADD'; L(sx.outputs['X'], uu.inputs[0]); L(sx.outputs['Y'], uu.inputs[1])
        brk = ramp(nt, noise(nt, obj, 0.45, 3), [(0.45, gray(0)), (0.58, gray(1))])      # Fugen nur stellenweise sichtbar
        col = mixc(nt, brk, col, mixc(nt, 1.0, col, groove(sx.outputs['Z'], 1.9, 0.012), 'MULTIPLY'))
        brk2 = ramp(nt, noise(nt, obj, 0.7, 3), [(0.55, gray(0)), (0.65, gray(1))])
        col = mixc(nt, brk2, col, mixc(nt, 1.0, col, groove(uu.outputs[0], 3.7, 0.006), 'MULTIPLY'))
    # Schmutz in Ecken / Fugen (Ambient Occlusion)
    ao = N('ShaderNodeAmbientOcclusion'); ao.inputs['Distance'].default_value = 0.9; ao.samples = 8
    aoc = ramp(nt, ao.outputs['AO'], [(0.0, (1 - ao_dirt * d_ * 0.8, 1 - ao_dirt * d_ * 0.85, 1 - ao_dirt * d_)), (0.7, gray(1))])
    col = mixc(nt, 1.0, col, aoc, 'MULTIPLY')
    # Rauheit: Textur A/B, nasse (dunkle) Flecken glaenzender
    rough = mixc(nt, ab, rA.outputs['Color'], rB.outputs['Color'])
    rf = nt.nodes.new('ShaderNodeSeparateColor'); L(rough, rf.inputs['Color'])
    rm = N('ShaderNodeMath'); rm.operation = 'MULTIPLY'; rm.inputs[1].default_value = rough_mul; L(rf.outputs['Red'], rm.inputs[0])
    if wet > 0:
        wetm = ramp(nt, noise(nt, obj, 0.8, 8, 0.6, 0.3), [(0.40, gray(1)), (0.58, gray(0))])   # 1 = nass
        wm = N('ShaderNodeMapRange'); wm.inputs['To Min'].default_value = 1.0; wm.inputs['To Max'].default_value = 1 - wet
        sw = nt.nodes.new('ShaderNodeSeparateColor'); L(wetm, sw.inputs['Color']); L(sw.outputs['Red'], wm.inputs['Value'])
        mul = N('ShaderNodeMath'); mul.operation = 'MULTIPLY'; L(rm.outputs[0], mul.inputs[0]); L(wm.outputs[0], mul.inputs[1]); rough_out = mul.outputs[0]
    else: rough_out = rm.outputs[0]
    rmin = N('ShaderNodeMath'); rmin.operation = 'MAXIMUM'; rmin.inputs[1].default_value = rough_min; L(rough_out, rmin.inputs[0])
    bsdf = N('ShaderNodeBsdfPrincipled'); outn = N('ShaderNodeOutputMaterial')
    L(col, bsdf.inputs['Base Color']); L(rmin.outputs[0], bsdf.inputs['Roughness'])
    nm = N('ShaderNodeNormalMap'); nm.inputs['Strength'].default_value = nor; L(nA.outputs['Color'], nm.inputs['Color'])
    L(nm.outputs['Normal'], bsdf.inputs['Normal']); bsdf.inputs['Specular IOR Level'].default_value = 0.25; bsdf.inputs['IOR'].default_value = F('conior', 1.1); L(bsdf.outputs[0], outn.inputs['Surface'])
    return mt

def box(name, x0, x1, y0, y1, z0, z1, mat, bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(); o = bpy.context.object; o.name = name
    o.scale = ((x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2); o.location = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    bpy.ops.object.transform_apply(scale=True); o.data.materials.append(mat)
    if bevel:
        b = o.modifiers.new('Fase', 'BEVEL'); b.width = bevel; b.segments = 2; b.limit_method = 'ANGLE'
    return o

# ---------------------------------------------------------------- Materialien
wall = dirty_concrete('Wand', 'concrete_wall_007', 'concrete_wall_006', 0.33, 'wall', tint=(0.84, 0.84, 0.86), bright=F('wallb', 2.7),
                      nor=0.55, mottle=0.30, stain=0.40, streak=0.30, pits=0.6, ao_dirt=0.45, brown=0.0, joints=0.28)
slab = dirty_concrete('Decke', 'concrete_wall_006', 'concrete_wall_007', 0.30, 'ceiling', tint=(0.9, 0.9, 0.9), bright=F('slabb', 2.7),
                      nor=0.6, mottle=0.30, stain=0.45, streak=0.25, pits=0.5, ao_dirt=0.4, brown=0.1)
dark = dirty_concrete('Pfeiler', 'concrete_wall_006', 'concrete_wall_007', 0.4, 'pillar', tint=(0.80, 0.78, 0.75), bright=F('pilb', 0.26),
                      nor=0.8, mottle=0.3, stain=0.35, streak=0.35, pits=0.5, ao_dirt=0.4)
floor = dirty_concrete('Boden', 'concrete_floor_worn_001', 'concrete_wall_006', 0.22, 'floor', tint=(0.84, 0.84, 0.82), bright=F('floorb', 2.4),
                       rough_mul=0.9, nor=0.7, mottle=0.4, stain=0.6, streak=0.62, pits=0.5, ao_dirt=0.5, wet=0.45, rough_min=0.5, desat=0.55, fg_dark=F('fgd', 0.04))

# ---------------------------------------------------------------- Raum
o_floor = box('Boden', -9, 9, -9, BACK_Y + 0.5, -0.5, 0, floor, bevel=0)
o_wall = box('Wand_links', WALL_X - 0.6, WALL_X, -9, BACK_Y + 0.5, 0, WALL_H + 0.5, wall)
o_back = box('Wand_hinten', WALL_X - 0.6, 6, BACK_Y, BACK_Y + 0.6, 0, WALL_H, wall)
o_slab = box('Decke', WALL_X - 0.6, 9, -9, SLAB_EDGE_Y, WALL_H, WALL_H + SLAB_T, slab, bevel=0.02)
ya = math.radians(CAM_YAW); a = Vector((-math.sin(ya), math.cos(ya), 0)); r = Vector((math.cos(ya), math.sin(ya), 0))
bpy.ops.mesh.primitive_cube_add(); pil = bpy.context.object; pil.name = 'Pfeiler'
pil.scale = (1.0, 0.3, F('pil_h', 2.55) / 2); bpy.ops.object.transform_apply(scale=True); pil.data.materials.append(dark)
pil.location = r * (F('pil_lat', 1.6) + 1.0) + a * F('pil_z', 3.7) + Vector((0, 0, F('pil_h', 2.55) / 2)); pil.rotation_euler = Euler((0, 0, ya))
b = pil.modifiers.new('Fase', 'BEVEL'); b.width = 0.02; b.segments = 2; b.limit_method = 'ANGLE'
o_back2 = box('Wand_rechts_hinten', 5.5, 6.0, 0, BACK_Y + 0.6, 0, WALL_H, wall)
room = [o_floor, o_back, o_slab, pil, o_back2]

# ---------------------------------------------------------------- Auto (Meshy multi-image-to-3d 01a21f80, goldener Lamborghini -> weiss)
import numpy as np
CAR_DIR = os.path.join(HERE, opt.get('cardir', 'work2'))
bpy.ops.import_scene.gltf(filepath=os.path.join(CAR_DIR, 'car.glb'))
car = [o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('Mesh_0')][0]
# Radmaske aus der Geometrie (lokale Koordinaten, aus den Speichen-Vertices vermessen): Felgen + Reifen -> schwarz
me = car.data; nv = len(me.vertices); co = np.zeros(nv * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
rim = np.zeros(nv, np.float32)
for cx in (-0.552, 0.62):
    d = np.hypot(co[:, 0] - cx, co[:, 2] - (-0.085))
    rim[(d < F('rimr', 0.153)) & (np.abs(co[:, 1]) > 0.20)] = 1.0
att = me.attributes.new('rimmask', 'FLOAT', 'POINT'); att.data.foreach_set('value', rim)
print('Radvertices', int(rim.sum()))
s_ = CAR_LEN / car.dimensions.x
car.scale = (s_, s_, s_); bpy.context.view_layer.objects.active = car; car.select_set(True)
bpy.ops.object.transform_apply(scale=True)
bb = [car.matrix_world @ Vector(c) for c in car.bound_box]
mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
ctr = (mn + mx) / 2
car.location = (-ctr.x, -ctr.y, -mn.z); bpy.ops.object.transform_apply(location=True)
car.rotation_mode = 'XYZ'
car.rotation_euler = (0, 0, math.radians(90 + 180 * int(F('flip', 0)) + CAR_YAW))   # Nase zur Kamera
car.location = (CAR_X, CAR_Y, 0)

cm = bpy.data.materials.new('Lack_weiss_verschmutzt'); cm.use_nodes = True
nt = cm.node_tree; src = car.data.materials[0].node_tree; L = nt.links.new
bsdf = nt.nodes['Principled BSDF']
def tn(im, cs):
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = im; im.colorspace_settings.name = cs; return t
base = bpy.data.images.load(os.path.join(CAR_DIR, 'tex_white.png')); base.colorspace_settings.name = 'sRGB'
tb = tn(base, 'sRGB')
mr_node = [n for n in src.nodes if n.type == 'TEX_IMAGE' and n.outputs['Color'].links and n.outputs['Color'].links[0].to_node.type == 'SEPARATE_COLOR'][0]
nm_node = [n for n in src.nodes if n.type == 'TEX_IMAGE' and n.outputs['Color'].links and n.outputs['Color'].links[0].to_node.type == 'NORMAL_MAP'][0]
tm = tn(mr_node.image, 'Non-Color'); sp = nt.nodes.new('ShaderNodeSeparateColor'); L(tm.outputs['Color'], sp.inputs['Color'])
# Masken: Rad (Geometrie) und Glas/dunkler Lack (Textur sehr dunkel, nicht Rad)
at = nt.nodes.new('ShaderNodeAttribute'); at.attribute_name = 'rimmask'; at.attribute_type = 'GEOMETRY'
rimm = ramp(nt, at.outputs['Fac'], [(0.35, gray(0)), (0.65, gray(1))])
rimf = nt.nodes.new('ShaderNodeSeparateColor'); L(rimm, rimf.inputs['Color']); rimv = rimf.outputs['Red']
bw = nt.nodes.new('ShaderNodeRGBToBW'); L(tb.outputs['Color'], bw.inputs['Color'])
glassm = ramp(nt, bw.outputs['Val'], [(0.035, gray(1)), (0.11, gray(0))])      # dunkel -> 1
glassf = nt.nodes.new('ShaderNodeSeparateColor'); L(glassm, glassf.inputs['Color'])
# Schmutz: Ecken-AO, Strassenschmutz unten (Weltkoordinate z), Staubspeckles
geo = nt.nodes.new('ShaderNodeNewGeometry'); sz = nt.nodes.new('ShaderNodeSeparateXYZ'); L(geo.outputs['Position'], sz.inputs['Vector'])
low = ramp(nt, sz.outputs['Z'], [(0.0, (0.34, 0.31, 0.27)), (0.14, (0.62, 0.59, 0.54)), (0.30, (0.88, 0.86, 0.82)), (0.55, gray(1))])
low = mixc(nt, DIRT, gray(1), low)
ao = nt.nodes.new('ShaderNodeAmbientOcclusion'); ao.inputs['Distance'].default_value = 0.14; ao.samples = 8
aoc = ramp(nt, ao.outputs['AO'], [(0.0, (0.30, 0.28, 0.25)), (0.6, gray(1))]); aoc = mixc(nt, DIRT, gray(1), aoc)
dust = ramp(nt, noise(nt, geo.outputs['Position'], 22, 6, 0.6), [(0.35, (0.74, 0.72, 0.68)), (0.68, gray(1))]); dust = mixc(nt, DIRT, gray(1), dust)
col = mixc(nt, 1.0, tb.outputs['Color'], (F('carb', 0.63), F('carb', 0.63) * 0.985, F('carb', 0.63) * 0.94), 'MULTIPLY'); col = mixc(nt, 1.0, col, low, 'MULTIPLY')
col = mixc(nt, 1.0, col, aoc, 'MULTIPLY'); col = mixc(nt, 1.0, col, dust, 'MULTIPLY')
col = mixc(nt, rimv, col, (0.012, 0.012, 0.014))                                   # schwarze Felgen
L(col, bsdf.inputs['Base Color'])
def mixf(fac, a, b):
    m = nt.nodes.new('ShaderNodeMix'); m.data_type = 'FLOAT'
    L(fac, m.inputs[0])
    for idx, v in ((2, a), (3, b)):
        if isinstance(v, (int, float)): m.inputs[idx].default_value = v
        else: L(v, m.inputs[idx])
    return m.outputs[0]
rough = nt.nodes.new('ShaderNodeMapRange'); rough.inputs['To Min'].default_value = 0.14; rough.inputs['To Max'].default_value = 0.42
L(sp.outputs['Green'], rough.inputs['Value'])
dirt_r = nt.nodes.new('ShaderNodeSeparateColor'); L(low, dirt_r.inputs['Color'])
rm = nt.nodes.new('ShaderNodeMath'); rm.operation = 'SUBTRACT'; rm.inputs[0].default_value = 1.0; L(dirt_r.outputs['Red'], rm.inputs[1])
rs = nt.nodes.new('ShaderNodeMath'); rs.operation = 'MULTIPLY_ADD'; rs.inputs[1].default_value = 0.6; L(rm.outputs[0], rs.inputs[0]); L(rough.outputs['Result'], rs.inputs[2])
rn = ramp(nt, noise(nt, geo.outputs['Position'], 60, 4, 0.6), [(0.3, gray(0)), (0.7, gray(1))]); rnf = nt.nodes.new('ShaderNodeSeparateColor'); L(rn, rnf.inputs['Color'])
rv = nt.nodes.new('ShaderNodeMath'); rv.operation = 'MULTIPLY_ADD'; rv.inputs[1].default_value = 0.10; L(rnf.outputs['Red'], rv.inputs[0]); L(rs.outputs[0], rv.inputs[2])   # Lack-Orangenhaut
r1 = mixf(glassf.outputs['Red'], rv.outputs[0], 0.05)           # Scheiben: Klarglanz-Schwarz
r2 = mixf(rimv, r1, F('rimrough', 0.42))                                        # Felgen: seidenmatt-glaenzend
L(r2, bsdf.inputs['Roughness'])
met = nt.nodes.new('ShaderNodeMath'); met.operation = 'MULTIPLY'; met.inputs[1].default_value = 0.25
L(sp.outputs['Blue'], met.inputs[0]); L(mixf(rimv, met.outputs[0], F('rimmet', 0.12)), bsdf.inputs['Metallic'])
tnor = tn(nm_node.image, 'Non-Color'); nn = nt.nodes.new('ShaderNodeNormalMap'); nn.inputs['Strength'].default_value = 0.5
L(tnor.outputs['Color'], nn.inputs['Color']); L(nn.outputs['Normal'], bsdf.inputs['Normal'])
L(mixf(glassf.outputs['Red'], 0.7, 0.0), bsdf.inputs['Coat Weight']); bsdf.inputs['Coat Roughness'].default_value = 0.08
L(mixf(glassf.outputs['Red'], 0.5, F('glassspec', 0.0)), bsdf.inputs['Specular IOR Level'])
car.data.materials.clear(); car.data.materials.append(cm)
for p_ in car.data.polygons: p_.use_smooth = True

# Kontaktschatten: weicher dunkler Fleck unter/vor dem Auto (im Foto fast schwarz unter der Front)
bpy.ops.mesh.primitive_plane_add(size=2); cs = bpy.context.object; cs.name = 'Kontaktschatten'
cs.scale = (CAR_LEN * 0.5 * 1.08, CAR_LEN * 0.497 * 0.5 * 1.18, 1); cs.rotation_euler = (0, 0, math.radians(90 + CAR_YAW))
cs.location = car.location + Vector((0, 0, 0.004)) + (Vector((math.cos(math.radians(CAR_YAW)), math.sin(math.radians(CAR_YAW)), 0)) * 0.0)
cmat = bpy.data.materials.new('Kontakt'); cmat.use_nodes = True; cn = cmat.node_tree; cn.nodes.clear()
tcn = cn.nodes.new('ShaderNodeTexCoord'); mpn = cn.nodes.new('ShaderNodeMapping'); mpn.inputs['Location'].default_value = (-0.5, -0.5, 0)
grn = cn.nodes.new('ShaderNodeTexGradient'); grn.gradient_type = 'SPHERICAL'
cn.links.new(tcn.outputs['Generated'], mpn.inputs['Vector']); cn.links.new(mpn.outputs[0], grn.inputs['Vector'])
cr = cn.nodes.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].position = 0.5; cr.color_ramp.elements[0].color = (0, 0, 0, 1); cr.color_ramp.elements[1].position = 1.0; cr.color_ramp.elements[1].color = (F('contact', 0.32),) * 3 + (1,)
cn.links.new(grn.outputs['Fac'], cr.inputs['Fac'])
pbn = cn.nodes.new('ShaderNodeBsdfPrincipled'); pbn.inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1); pbn.inputs['Roughness'].default_value = 1.0
sepn = cn.nodes.new('ShaderNodeSeparateColor'); cn.links.new(cr.outputs[0], sepn.inputs['Color']); cn.links.new(sepn.outputs['Red'], pbn.inputs['Alpha'])
ocn = cn.nodes.new('ShaderNodeOutputMaterial'); cn.links.new(pbn.outputs[0], ocn.inputs['Surface'])
cs.data.materials.append(cmat); cs.visible_shadow = False; cs.visible_glossy = False

# ---------------------------------------------------------------- Licht (zwei Sonnen, Light-Linking)
def sun(name, d, strength, receivers):
    o = bpy.data.objects.new(name, bpy.data.lights.new(name, 'SUN')); sc.collection.objects.link(o)
    o.data.energy = strength; o.data.angle = math.radians(0.6); o.data.color = (1.0, 0.97, 0.92)
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    c = bpy.data.collections.new(name + '_Empfaenger'); sc.collection.children.link(c)
    for ob in receivers: c.objects.link(ob)
    o.light_linking.receiver_collection = c
    return o
SPOT_R = 300.0
def masked_spot(name, d, strength, poly, receivers, blockers, eps=None):
    eps = F('maskeps', 0.00005) if eps is None else eps
    """Weit entfernter Spot, der wie eine Sonne wirkt (Staerke kalibriert), mit polygonaler Lichtmaske.
    poly: Weltpunkte, die die beleuchtete Flaeche umreissen (konvex). Die Maske liegt im Richtungsraum des Lichts,
    d.h. sie wirkt wie eine unsichtbare Blende und blockiert das Himmelslicht NICHT."""
    d = d.normalized(); L_ = -d * SPOT_R
    o = bpy.data.objects.new(name, bpy.data.lights.new(name, 'SPOT')); sc.collection.objects.link(o)
    ld = o.data; ld.spot_size = math.radians(10); ld.spot_blend = 0.0
    ld.shadow_soft_size = F('sunr', 0.07); ld.color = (1.0, 0.97, 0.92)
    ld.energy = 2.828e5 * strength * (SPOT_R / 150.0) ** 2
    o.location = L_; q = d.to_track_quat('-Z', 'Y'); o.rotation_euler = q.to_euler(); Rm = q.to_matrix()
    ab = []
    for P in poly:
        v = Rm.transposed() @ (Vector(P) - L_); ab.append((v.x / -v.z, v.y / -v.z))
    area = sum(ab[i][0] * ab[(i + 1) % len(ab)][1] - ab[(i + 1) % len(ab)][0] * ab[i][1] for i in range(len(ab)))
    if area < 0: ab.reverse()
    ld.use_nodes = True; nt_ = ld.node_tree; nt_.nodes.clear(); N_ = nt_.nodes.new; L2 = nt_.links.new
    em = N_('ShaderNodeEmission'); outn = N_('ShaderNodeOutputLight'); tc_ = N_('ShaderNodeTexCoord'); sp_ = N_('ShaderNodeSeparateXYZ')
    L2(tc_.outputs['Normal'], sp_.inputs['Vector'])
    def mth(op, a=None, b=None):
        m = N_('ShaderNodeMath'); m.operation = op
        for i, v in enumerate((a, b)):
            if v is None: continue
            if isinstance(v, (int, float)): m.inputs[i].default_value = v
            else: L2(v, m.inputs[i])
        return m.outputs[0]
    negz = mth('MULTIPLY', sp_.outputs['Z'], -1.0)
    A_ = mth('DIVIDE', sp_.outputs['X'], negz); B_ = mth('DIVIDE', sp_.outputs['Y'], negz)
    mask = None
    for i in range(len(ab)):
        (a0, b0), (a1, b1) = ab[i], ab[(i + 1) % len(ab)]
        ex, ey = a1 - a0, b1 - b0; ln = math.hypot(ex, ey); nx, ny, c = -ey / ln, ex / ln, (ey * a0 - ex * b0) / ln
        val = mth('ADD', mth('ADD', mth('MULTIPLY', A_, nx), mth('MULTIPLY', B_, ny)), c)
        mr = N_('ShaderNodeMapRange'); mr.inputs['From Min'].default_value = -eps; mr.inputs['From Max'].default_value = eps
        L2(val, mr.inputs['Value']); e_ = mr.outputs['Result']
        mask = e_ if mask is None else mth('MULTIPLY', mask, e_)
    L2(mask, em.inputs['Strength']); L2(em.outputs[0], outn.inputs['Surface'])
    c_ = bpy.data.collections.new(name + '_Empfaenger'); sc.collection.children.link(c_)
    for ob in receivers: c_.objects.link(ob)
    o.light_linking.receiver_collection = c_
    b_ = bpy.data.collections.new(name + '_Blocker'); sc.collection.children.link(b_)
    for ob in blockers: b_.objects.link(ob)
    o.light_linking.blocker_collection = b_
    return o
if int(F('spotmask', 1)):
    # Lichtkeil auf dem Boden: Polygon aus den Foto-Messpunkten (Unterkante schraeg, rechte Kante schraeg), siehe README
    ky = F('wedge_y', 0.0)
    floor_poly = [(-5.5, 2.53 + ky, 0), (-1.60, 3.73 + ky, 0), (-2.54, 11.0, 0), (-5.5, 11.0, 0)]
    masked_spot('Sonne_Boden', SUN_A, STR_A, floor_poly, [o_floor, o_back, o_slab, pil, o_back2, car, cs], [car, pil])
    # Lichtflaeche auf der linken Wand: Halbebene, Diagonale (y - z/1.036 > 2.82) wie im Foto
    wall_poly = [(WALL_X, 2.82, 0), (WALL_X, 7.65, 5.0), (WALL_X, 13.0, 5.0), (WALL_X, 13.0, 0)]
    masked_spot('Sonne_Wand', SUN_W, STR_W, wall_poly, [o_wall], [car, pil])
else:
    sun('Sonne_Boden', SUN_A, STR_A, room + [car])
    sun('Sonne_Wand', SUN_W, STR_W, [o_wall])
# Bounce-Karte: unsichtbare Flaeche ueber dem hellen Lichtkeil, nur fuer die Decke verlinkt (ersetzt den fehlenden Bounce vom stark ueberstrahlten Boden)
bl = bpy.data.objects.new('Bounce_Decke', bpy.data.lights.new('Bounce_Decke', 'AREA')); sc.collection.objects.link(bl)
bl.data.shape = 'RECTANGLE'; bl.data.size = 6.0; bl.data.size_y = 5.0; bl.data.energy = F('ceilfill', 170.0); bl.data.color = (1.0, 0.95, 0.89)
bl.data.use_shadow = False; bl.location = (F('bx', -2.0), F('by', 7.0), 0.4); bl.rotation_euler = (0, 0, 0)   # leuchtet nach unten -> drehen
bl.rotation_euler = (math.pi, 0, 0)   # Flaeche zeigt nach oben (Area-Licht strahlt entlang -Z; gedreht -> +Z)
bcol = bpy.data.collections.new('Bounce_Empfaenger'); sc.collection.children.link(bcol); bcol.objects.link(o_slab)
bl.light_linking.receiver_collection = bcol
w = bpy.data.worlds.new('Himmel'); sc.world = w; w.use_nodes = True
sky = w.node_tree.nodes.new('ShaderNodeTexSky'); sky.sky_type = 'MULTIPLE_SCATTERING'
sky.sun_disc = False; sky.air_density = 1.0; sky.aerosol_density = 2.0; sky.altitude = 0
sd = -SUN_A.normalized(); sky.sun_elevation = math.asin(sd.z); sky.sun_rotation = -math.atan2(sd.x, sd.y)
bg = w.node_tree.nodes['Background']; bg.inputs['Strength'].default_value = SKY
lp = w.node_tree.nodes.new('ShaderNodeLightPath'); cm_ = w.node_tree.nodes.new('ShaderNodeMath'); cm_.operation = 'MULTIPLY_ADD'
cm_.inputs[1].default_value = -F('camsky', 0.915) * SKY; cm_.inputs[2].default_value = SKY
w.node_tree.links.new(lp.outputs['Is Camera Ray'], cm_.inputs[0]); w.node_tree.links.new(cm_.outputs[0], bg.inputs['Strength'])
hs = w.node_tree.nodes.new('ShaderNodeHueSaturation'); hs.inputs['Saturation'].default_value = F('skysat', 0.5)
w.node_tree.links.new(sky.outputs['Color'], hs.inputs['Color']); w.node_tree.links.new(hs.outputs['Color'], bg.inputs['Color'])
sm_ = w.node_tree.nodes.new('ShaderNodeMath'); sm_.operation = 'MULTIPLY_ADD'; sm_.inputs[1].default_value = F('camsat', 0.55); sm_.inputs[2].default_value = F('skysat', 0.5)
w.node_tree.links.new(lp.outputs['Is Camera Ray'], sm_.inputs[0]); w.node_tree.links.new(sm_.outputs[0], hs.inputs['Saturation'])

# ---------------------------------------------------------------- Kamera
cam = bpy.data.objects.new('Kamera', bpy.data.cameras.new('Kamera')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = FOCAL; cam.data.sensor_width = 36; cam.data.sensor_fit = 'HORIZONTAL'
cam.data.shift_y = -(360 - HORIZON_PX) / 720.0
cam.location = (0, 0, CAM_H); cam.rotation_euler = (math.radians(90), 0, math.radians(CAM_YAW))

# ---------------------------------------------------------------- Render
cy = sc.cycles
sc.render.engine = 'CYCLES'; cy.device = 'CPU'; cy.samples = SAMPLES; cy.use_denoising = True
cy.max_bounces = 14; cy.diffuse_bounces = 10; cy.glossy_bounces = 6; cy.transmission_bounces = 4
cy.sample_clamp_indirect = 0; cy.sample_clamp_direct = 0; cy.caustics_reflective = False; cy.caustics_refractive = False
sc.render.resolution_x = sc.render.resolution_y = RES; sc.render.resolution_percentage = 100
sc.view_settings.view_transform = opt.get('tm', 'AgX'); sc.view_settings.exposure = EXPO; sc.view_settings.look = 'None'
sc.render.filepath = out; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print('DONE', out)
