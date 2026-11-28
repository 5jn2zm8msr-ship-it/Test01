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

# ---- Kamera: laengere Brennweite (weniger Weitwinkel-Eindruck); Raum wird daraus aus Foto-Pixeln neu berechnet
FOCAL = F('focal', 50.0); FPX = 720.0 * FOCAL / 36.0                  # Brennweite (Kleinbild) -> Pixel bei 720 px Bildbreite
CAM_H = 1.6; HORIZON_PX = F('horizon', 243.0)                         # Horizont aus den Linien der linken Wand (Fluchtpunkt bei y=243)
CAM_YAW = math.degrees(math.atan((F('vp1x', 795.0) - 360.0) / FPX))   # Kamera so gedreht, dass die linke Wand parallel zur Welt-Y-Achse liegt
_ya = math.radians(CAM_YAW)
CAM_A = (-math.sin(_ya), math.cos(_ya)); CAM_R = (math.cos(_ya), math.sin(_ya))     # Blickrichtung / rechts (Welt, xy)
def ray(u, v): return (CAM_A[0] * FPX + CAM_R[0] * (u - 360.0), CAM_A[1] * FPX + CAM_R[1] * (u - 360.0), HORIZON_PX - v)
def at_height(u, v, h):                                               # Foto-Pixel -> Weltpunkt in der Hoehe h
    d = ray(u, v); t = (h - CAM_H) / d[2]; return (t * d[0], t * d[1], h)
def on_plane_x(u, v, x0):                                             # Foto-Pixel -> Weltpunkt auf der Ebene x = x0
    d = ray(u, v); t = x0 / d[0]; return (x0, t * d[1], CAM_H + t * d[2])
WALL_H = F('wall_h', 2.67); SLAB_T = 0.45
WALL_X = at_height(0, 487, 0.0)[0]                                    # linke Wand: Fusspunkt am linken Bildrand
_c = at_height(402, 363.6, 0.0); CORNER = (WALL_X, _c[1]); BACK_Y = CORNER[1]   # Ecke (Wandfuss)
_rp = at_height(645, 369.5, 0.0)                                      # Rueckwandfuss rechts
BACK_ANG = math.atan2(_rp[1] - CORNER[1], _rp[0] - CORNER[0])         # Rueckwand-Richtung (nicht rechtwinklig zur linken Wand!)
_s1 = at_height(225, 126, WALL_H); _s2 = at_height(647, 83, WALL_H)   # Deckenvorderkante (zwei Foto-Punkte)
_dc = CORNER[0] * CAM_A[0] + CORNER[1] * CAM_A[1]; _dr = _rp[0] * CAM_A[0] + _rp[1] * CAM_A[1]         # Tiefen entlang der Blickachse
BACK_H0 = CAM_H + (HORIZON_PX - 163.0) * _dc / FPX; BACK_H1 = CAM_H + (HORIZON_PX - 147.0) * _dr / FPX    # Hoehe an der Ecke / am rechten Ende
BACK_SLOPE = (BACK_H1 - BACK_H0) / math.hypot(_rp[0] - CORNER[0], _rp[1] - CORNER[1])                       # Oberkante steigt im Foto nach rechts
SLAB_ANG = math.atan2(_s2[1] - _s1[1], _s2[0] - _s1[0]); SLAB_MID = ((_s1[0] + _s2[0]) / 2, (_s1[1] + _s2[1]) / 2)
SLAB_YA, SLAB_YB = SLAB_MID[1] - 1.8, SLAB_MID[1]
_G1 = at_height(0, 505, 0.0); FG_YA, FG_YB = _G1[1] - 1.7, _G1[1] - 0.2
_pf = at_height(640, 555, 0.0)                                        # Pfeiler: ferne Kante (Fusspunkt)
PIL_LAT = _pf[0] * CAM_R[0] + _pf[1] * CAM_R[1]; PIL_D = _pf[0] * CAM_A[0] + _pf[1] * CAM_A[1]      # seitlicher Abstand / Tiefe der frontalen Flaeche
PIL_LAT2 = (689.0 - 360.0) * PIL_D / FPX                              # rechte Kante der dunklen Flaeche bei x=689
PIL_H = CAM_H + (HORIZON_PX - 47.0) * PIL_D / FPX                     # Oberkante bei y=47
CAR_LEN = F('car_len', 4.25)
CAR_X, CAR_Y = F('car_x', -3.55), F('car_y', 5.95)
CAR_YAW = F('car_yaw', 4.0)
SUN_A = Vector((F('ax', -0.30), F('ay', -0.75), F('az', -1.0)))    # Boden/Decke/Auto/Pfeiler/Rueckwand
SUN_W = Vector((F('wx', -0.60), F('wy', -0.685), F('wz', -1.0)))   # nur linke Wand
STR_A, STR_W = F('sunA', 42.0), F('sunW', 30.0)
SKY = F('sky', 0.6)
EXPO = F('expo', 2.0)
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
                   mottle=0.25, stain=0.35, streak=0.0, pits=0.4, ao_dirt=0.4, wet=0.0, brown=0.0, rough_min=0.6, fg_dark=0.0, desat=0.4, joints=0.0, edge=0.0, bug=0.0):
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
        fgm = ramp(nt, sy.outputs['Y'], [(FG_YA, gray(1 - fg_dark)), (FG_YB, gray(1))])
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
    bug_h = None
    if edge > 0:   # Raender dunkel vom Regen, am Fuss vermoost/verschmutzt
        gp = N('ShaderNodeNewGeometry'); wz = N('ShaderNodeSeparateXYZ'); L(gp.outputs['Position'], wz.inputs['Vector'])
        ragged = ramp(nt, noise(nt, obj, 2.6, 6, 0.6, 0.3), [(0.30, gray(0.15)), (0.70, gray(1))])
        if kind in ('wall', 'pillar'):
            band = ramp(nt, wz.outputs['Z'], [(WALL_H - 0.9, gray(1)), (WALL_H, (1 - cap(edge * d_), 1 - cap(edge * d_) * 0.92, 1 - cap(edge * d_) * 1.0))])
            col = mixc(nt, 1.0, col, mixc(nt, ragged, gray(1), band), 'MULTIPLY')
            moss = ramp(nt, wz.outputs['Z'], [(0.0, (0.52, 0.58, 0.40)), (0.22, (0.80, 0.85, 0.70)), (0.6, gray(1))])
            col = mixc(nt, 1.0, col, mixc(nt, ragged, gray(1), moss), 'MULTIPLY')
        if kind == 'ceiling':
            wy_ = N('ShaderNodeSeparateXYZ'); L(gp.outputs['Position'], wy_.inputs['Vector'])
            band = ramp(nt, wy_.outputs['Y'], [(SLAB_YA, gray(1)), (SLAB_YB, (1 - cap(edge * d_), 1 - cap(edge * d_) * 0.92, 1 - cap(edge * d_) * 0.9))])
            col = mixc(nt, 1.0, col, mixc(nt, ragged, gray(1), band), 'MULTIPLY')
    if bug > 0:    # Lufteinschluesse (Lunker): unregelmaessig verteilt, verschieden gross, dunkel, leicht vertieft
        holes = None
        for scale_, thr_, rmax_ in ((7.0, 0.72, 0.24), (16.0, 0.60, 0.20), (40.0, 0.50, 0.15)):
            vr2 = N('ShaderNodeTexVoronoi'); vr2.feature = 'F1'; vr2.inputs['Scale'].default_value = scale_; L(obj, vr2.inputs['Vector'])
            rc = N('ShaderNodeSeparateColor'); L(vr2.outputs['Color'], rc.inputs['Color'])
            sub = N('ShaderNodeMath'); sub.operation = 'SUBTRACT'; sub.inputs[1].default_value = thr_; L(rc.outputs['Red'], sub.inputs[0])
            rad = N('ShaderNodeMath'); rad.operation = 'MULTIPLY'; rad.inputs[1].default_value = rmax_ / (1 - thr_); L(sub.outputs[0], rad.inputs[0])
            radp = N('ShaderNodeMath'); radp.operation = 'MAXIMUM'; radp.inputs[1].default_value = 0.0; L(rad.outputs[0], radp.inputs[0])
            dif = N('ShaderNodeMath'); dif.operation = 'SUBTRACT'; L(radp.outputs[0], dif.inputs[0]); L(vr2.outputs['Distance'], dif.inputs[1])
            ins = N('ShaderNodeMapRange'); ins.inputs['From Min'].default_value = -0.012; ins.inputs['From Max'].default_value = 0.012; L(dif.outputs[0], ins.inputs['Value'])
            holes = ins.outputs['Result'] if holes is None else (lambda a_, b_: (lambda m_: (L(a_, m_.inputs[0]), L(b_, m_.inputs[1]), m_.outputs[0])[2])(N('ShaderNodeMath')))(holes, ins.outputs['Result'])
            if holes is not ins.outputs['Result']: pass
        hm = N('ShaderNodeMath'); hm.operation = 'MINIMUM'; hm.inputs[1].default_value = 1.0; L(holes, hm.inputs[0]); holes = hm.outputs[0]
        dark_h = ramp(nt, holes, [(0.0, gray(1)), (1.0, gray(1 - cap(bug * d_)))])
        col = mixc(nt, 1.0, col, dark_h, 'MULTIPLY'); bug_h = holes
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
    if bug_h is not None:
        inv = N('ShaderNodeMath'); inv.operation = 'SUBTRACT'; inv.inputs[0].default_value = 1.0; L(bug_h, inv.inputs[1])
        bp = N('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.9; bp.inputs['Distance'].default_value = 0.01
        L(inv.outputs[0], bp.inputs['Height']); L(nm.outputs['Normal'], bp.inputs['Normal']); L(bp.outputs['Normal'], bsdf.inputs['Normal'])
    else: L(nm.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Specular IOR Level'].default_value = 0.25; bsdf.inputs['IOR'].default_value = F('conior', 1.1); L(bsdf.outputs[0], outn.inputs['Surface'])
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
                      nor=0.55, mottle=0.30, stain=0.40, streak=0.45, pits=0.4, ao_dirt=0.6, brown=0.0, joints=0.28, edge=F('edge', 0.9), bug=F('bug', 0.7))
slab = dirty_concrete('Decke', 'concrete_wall_006', 'concrete_wall_007', 0.30, 'ceiling', tint=(0.9, 0.9, 0.9), bright=F('slabb', 2.7),
                      nor=0.6, mottle=0.30, stain=0.45, streak=0.25, pits=0.5, ao_dirt=0.5, brown=0.1, edge=F('edge', 0.9), bug=F('bug', 0.6))
dark = dirty_concrete('Pfeiler', 'concrete_wall_006', 'concrete_wall_007', 0.4, 'pillar', tint=(0.80, 0.78, 0.75), bright=F('pilb', 0.57),
                      nor=0.8, mottle=0.3, stain=0.35, streak=0.35, pits=0.5, ao_dirt=0.5, edge=F('edge', 0.9) * 0.6, bug=F('bug', 0.6))
floor = dirty_concrete('Boden', 'concrete_floor_worn_001', 'concrete_wall_006', 0.22, 'floor', tint=(0.84, 0.84, 0.82), bright=F('floorb', 1.7),
                       rough_mul=0.9, nor=0.7, mottle=0.4, stain=0.6, streak=0.62, pits=0.5, ao_dirt=0.5, wet=0.45, rough_min=0.5, desat=0.55, bug=F('bug', 0.25), fg_dark=F('fgd', 0.15))

# ---------------------------------------------------------------- Raum
def rbox(name, cx, cy, sx, sy, z0, z1, ang, mat, bevel=0.015):
    """Quader um die Z-Achse gedreht (lokal x = Laengsrichtung, lokal y = Tiefe)."""
    bpy.ops.mesh.primitive_cube_add(); o = bpy.context.object; o.name = name
    o.scale = (sx / 2, sy / 2, (z1 - z0) / 2); o.location = (cx, cy, (z0 + z1) / 2); o.rotation_euler = (0, 0, ang)
    bpy.ops.object.transform_apply(scale=True); o.data.materials.append(mat)
    if bevel:
        bm_ = o.modifiers.new('Fase', 'BEVEL'); bm_.width = bevel; bm_.segments = 2; bm_.limit_method = 'ANGLE'
    return o
o_floor = box('Boden', -14, 14, -16, 16, -0.5, 0, floor, bevel=0)
o_wall = box('Wand_links', WALL_X - 0.6, WALL_X, -9, BACK_Y + 0.6, 0, WALL_H, wall)
wall_b = dirty_concrete('Wand_hinten', 'concrete_wall_007', 'concrete_wall_006', 0.33, 'wall', tint=(0.84, 0.84, 0.86), bright=F('wallb', 2.7) * F('backdim', 0.76),
                        nor=0.55, mottle=0.30, stain=0.40, streak=0.45, pits=0.4, ao_dirt=0.6, brown=0.0, joints=0.28, edge=F('edge', 0.9), bug=F('bug', 0.7))
_bn = (-math.sin(BACK_ANG), math.cos(BACK_ANG)); _bd = (math.cos(BACK_ANG), math.sin(BACK_ANG))
def wedge_wall(name, p0, dvec, nvec, L, thick, h0, slope, mat, s0=-0.3):
    """Rueckwand als Keil: Oberkante steigt linear (wie im Foto), Fuss gerade."""
    import bmesh
    me_ = bpy.data.meshes.new(name); V = []
    for z_mode in (0, 1):
        for s_, off in ((s0, 0.0), (s0 + L, 0.0), (s0 + L, thick), (s0, thick)):
            V.append((p0[0] + dvec[0] * s_ + nvec[0] * off, p0[1] + dvec[1] * s_ + nvec[1] * off, (h0 + slope * max(s_, 0.0)) if z_mode else 0.0))
    me_.from_pydata(V, [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]); me_.update()
    bm_ = bmesh.new(); bm_.from_mesh(me_); bmesh.ops.recalc_face_normals(bm_, faces=bm_.faces); bm_.to_mesh(me_); bm_.free()
    o = bpy.data.objects.new(name, me_); sc.collection.objects.link(o); o.data.materials.append(mat); return o
o_back = wedge_wall('Wand_hinten', CORNER, _bd, _bn, 10.0, 0.6, BACK_H0, BACK_SLOPE, wall_b)
_sn = (-math.sin(SLAB_ANG), math.cos(SLAB_ANG)); _SD = 14.0
o_slab = rbox('Decke', SLAB_MID[0] - _sn[0] * _SD / 2, SLAB_MID[1] - _sn[1] * _SD / 2, 26.0, _SD, WALL_H, WALL_H + SLAB_T, SLAB_ANG, slab, bevel=0.02)
def _cam_xy(lat, dep): return (CAM_R[0] * lat + CAM_A[0] * dep, CAM_R[1] * lat + CAM_A[1] * dep)
_pa = _cam_xy((PIL_LAT + PIL_LAT2) / 2, PIL_D + 0.025); _pb = _cam_xy((PIL_LAT2 + 3.4) / 2, PIL_D + 0.025)
pil = rbox('Pfeiler', _pa[0], _pa[1], PIL_LAT2 - PIL_LAT, 0.05, 0, PIL_H, _ya, dark, bevel=0.0)          # dunkle frontale Flaeche (x 640-689)
wall_p = dirty_concrete('Pfeiler_hell', 'concrete_wall_006', 'concrete_wall_007', 0.4, 'pillar', tint=(0.82, 0.82, 0.82), bright=F('pilb2', 1.5),
                        nor=0.7, mottle=0.3, stain=0.3, streak=0.35, pits=0.4, ao_dirt=0.4, edge=0.0, bug=F('bug', 0.6))
pilB = rbox('Pfeiler_hell', _pb[0], _pb[1], 3.4 - PIL_LAT2, 0.05, 0, WALL_H, _ya, wall_p, bevel=0.0)    # hellere Flaeche rechts davon (x>689)
room = [o_floor, o_back, o_slab, pil, pilB]

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
car.scale = (1.0, F('car_w', 2.05) / car.dimensions.y, 1.0)   # nur Breite (lokal Y) auf 2050 mm, Laenge/Hoehe unveraendert
bpy.ops.object.transform_apply(scale=True)
print('AUTOMASSE L x B x H [m]: %.3f x %.3f x %.3f' % (car.dimensions.x, car.dimensions.y, car.dimensions.z))
bb = [car.matrix_world @ Vector(c) for c in car.bound_box]
mn = Vector((min(v.x for v in bb), min(v.y for v in bb), min(v.z for v in bb)))
mx = Vector((max(v.x for v in bb), max(v.y for v in bb), max(v.z for v in bb)))
ctr = (mn + mx) / 2
car.location = (-ctr.x, -ctr.y, -mn.z); bpy.ops.object.transform_apply(location=True)
car.rotation_mode = 'XYZ'
car.rotation_euler = (0, 0, math.radians(90 + 180 * int(F('flip', 0)) + CAR_YAW))   # Nase zur Kamera
car.location = (CAR_X, CAR_Y, -0.005)

cm = bpy.data.materials.new('Lack_weiss_verschmutzt'); cm.use_nodes = True
nt = cm.node_tree; src = car.data.materials[0].node_tree; L = nt.links.new
bsdf = nt.nodes['Principled BSDF']
def tn(im, cs):
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = im; im.colorspace_settings.name = cs; return t
GOLD = opt.get('carpaint', 'gold') == 'gold'
base = bpy.data.images.load(os.path.join(CAR_DIR, 'tex_0_base_color.png' if GOLD else 'tex_white.png')); base.colorspace_settings.name = 'sRGB'
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
hsc = nt.nodes.new('ShaderNodeHueSaturation'); hsc.inputs['Saturation'].default_value = F('carsat', 3.2) if GOLD else 1.0; L(tb.outputs['Color'], hsc.inputs['Color'])
col = mixc(nt, 1.0, hsc.outputs['Color'], ((F('carbg', 0.27),) * 3 if GOLD else (F('carb', 0.63), F('carb', 0.63) * 0.985, F('carb', 0.63) * 0.94)), 'MULTIPLY'); col = mixc(nt, 1.0, col, low, 'MULTIPLY')
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
r2 = mixf(rimv, r1, F('rimrough', 0.2))                                        # Felgen: seidenmatt-glaenzend
L(r2, bsdf.inputs['Roughness'])
met = nt.nodes.new('ShaderNodeMath'); met.operation = 'MULTIPLY'; met.inputs[1].default_value = F('carmet', 0.15) if GOLD else 0.25
L(sp.outputs['Blue'], met.inputs[0]); L(mixf(rimv, met.outputs[0], F('rimmet', 0.9)), bsdf.inputs['Metallic'])
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
    G1 = at_height(0, 505, 0.0); G2 = at_height(470, 552, 0.0); G3 = at_height(590, 395, 0.0)     # Keil: Unterkante (G1-G2), rechte Kante (G2-G3)
    e1 = (G2[0] - G1[0], G2[1] - G1[1]); e2 = (G3[0] - G2[0], G3[1] - G2[1]); xl = WALL_X - 1.0; yfar = BACK_Y + 3.0
    P1 = (xl, G1[1] + e1[1] * (xl - G1[0]) / e1[0] + ky, 0.0); P3 = (G2[0] + e2[0] * (yfar - G2[1]) / e2[1], yfar, 0.0)
    floor_poly = [P1, (G2[0], G2[1] + ky, 0.0), P3, (xl, yfar, 0.0)]
    masked_spot('Sonne_Boden', SUN_A, STR_A, floor_poly, [o_floor, o_back, o_slab, pil, pilB, car, cs], [car, pil, pilB, o_back])
    # Lichtflaeche auf der linken Wand: Halbebene durch zwei Foto-Punkte der Schattendiagonale
    W1 = on_plane_x(225, 127, WALL_X); W2 = on_plane_x(0, 430, WALL_X); dv = (W1[1] - W2[1], W1[2] - W2[2])
    plow = (WALL_X, W2[1] + dv[0] * (-W2[2] / dv[1]), 0.0); phigh = (WALL_X, W1[1] + dv[0] * ((6.0 - W1[2]) / dv[1]), 6.0)
    wall_poly = [plow, phigh, (WALL_X, yfar, 6.0), (WALL_X, yfar, 0.0)]
    masked_spot('Sonne_Wand', SUN_W, STR_W, wall_poly, [o_wall], [car, pil, pilB, o_back])
else:
    sun('Sonne_Boden', SUN_A, STR_A, room + [car])
    sun('Sonne_Wand', SUN_W, STR_W, [o_wall])
# Bounce-Karte: unsichtbare Flaeche ueber dem hellen Lichtkeil, nur fuer die Decke verlinkt (ersetzt den fehlenden Bounce vom stark ueberstrahlten Boden)
bl = bpy.data.objects.new('Bounce_Decke', bpy.data.lights.new('Bounce_Decke', 'AREA')); sc.collection.objects.link(bl)
bl.data.shape = 'RECTANGLE'; bl.data.size = 7.0; bl.data.size_y = 6.0; bl.data.energy = F('ceilfill', 130.0); bl.data.color = (1.0, 0.95, 0.89)
bl.data.use_shadow = False; bl.location = (F('bx', WALL_X + 2.0), F('by', 6.2), 0.4); bl.rotation_euler = (0, 0, 0)   # leuchtet nach unten -> drehen
bl.rotation_euler = (math.pi, 0, 0)   # Flaeche zeigt nach oben (Area-Licht strahlt entlang -Z; gedreht -> +Z)
bcol = bpy.data.collections.new('Bounce_Empfaenger'); sc.collection.children.link(bcol); bcol.objects.link(o_slab)
bl.light_linking.receiver_collection = bcol
w = bpy.data.worlds.new('Himmel'); sc.world = w; w.use_nodes = True
sky = w.node_tree.nodes.new('ShaderNodeTexSky'); sky.sky_type = 'MULTIPLE_SCATTERING'
sky.sun_disc = False; sky.air_density = 1.0; sky.aerosol_density = 2.0; sky.altitude = 0
sd = -SUN_A.normalized(); sky.sun_elevation = math.asin(sd.z); sky.sun_rotation = -math.atan2(sd.x, sd.y)
bg = w.node_tree.nodes['Background']; bg.inputs['Strength'].default_value = SKY
lp = w.node_tree.nodes.new('ShaderNodeLightPath'); cm_ = w.node_tree.nodes.new('ShaderNodeMath'); cm_.operation = 'MULTIPLY_ADD'
cm_.inputs[1].default_value = -F('camsky', 0.975) * SKY; cm_.inputs[2].default_value = SKY
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

# ---------------------------------------------------------------- Auto auf Foto-Reifenpunkte einpassen
sc.render.resolution_x = sc.render.resolution_y = RES; sc.render.resolution_percentage = 100   # vor der Projektion setzen (quadratisch)
if int(F('match', 1)):
    from bpy_extras.object_utils import world_to_camera_view
    PF = np.array([F('pfx', 437.0), F('pfy', 478.0)])     # Vorderreifen unten (Foto, 720-px-Koordinaten) - harte Vorgabe
    PR = np.array([F('prx', 533.0), F('pry', 408.0)])     # Hinterreifen unten - schwaecher gewichtet (anderer Radstand)
    WF, WR = 1.0, F('wr', 0.3)
    cv = np.zeros(len(car.data.vertices) * 3, np.float32); car.data.vertices.foreach_get('co', cv); cv = cv.reshape(-1, 3)
    rimv = cv[rim > 0.5]
    def wheel_pt(front):
        sel = rimv[(rimv[:, 0] < 0) == front]; sel = sel[sel[:, 1] < 0]          # sichtbare Seite: lokal y < 0 (flip=0)
        low = sel[sel[:, 2] < sel[:, 2].min() + 0.012]                           # tiefster Reifenpunkt (unterste 1,2 cm)
        return np.array([low[:, 0].mean(), sel[:, 1].min(), 0.0])                # dessen Laengsposition, aeussere Reifenflanke, Boden
    cf_, cr_ = wheel_pt(True), wheel_pt(False)
    cam_obj = sc.camera; bpy.context.view_layer.update()
    def wpt(pl, X, Y, yaw):
        th = math.radians(90 + 180 * int(F('flip', 0)) + yaw)
        return Vector((math.cos(th) * pl[0] - math.sin(th) * pl[1] + X, math.sin(th) * pl[0] + math.cos(th) * pl[1] + Y, -0.005))
    def pix(w_):
        v = world_to_camera_view(sc, cam_obj, w_); return np.array([v.x * 720.0, (1 - v.y) * 720.0])
    def resid(p):
        return np.concatenate([WF * (pix(wpt(cf_, *p)) - PF), WR * (pix(wpt(cr_, *p)) - PR)])
    _gf = at_height(PF[0], PF[1], 0.0); _gr = at_height(PR[0], PR[1], 0.0)
    _th = math.atan2(-(_gf[1] - _gr[1]), -(_gf[0] - _gr[0])); _y0 = math.degrees(_th) - 90 - 180 * int(F('flip', 0))
    _X0 = _gf[0] - (math.cos(_th) * cf_[0] - math.sin(_th) * cf_[1]); _Y0 = _gf[1] - (math.sin(_th) * cf_[0] + math.cos(_th) * cf_[1])
    p = np.array([_X0, _Y0, _y0], float)
    for _ in range(40):
        r0 = resid(p); J = np.zeros((4, 3))
        for k, e in enumerate((1e-3, 1e-3, 1e-2)):
            q = p.copy(); q[k] += e; J[:, k] = (resid(q) - r0) / e
        dp = np.linalg.lstsq(J, -r0, rcond=None)[0]; p = p + 0.7 * dp
    print('EINPASSUNG X=%.3f Y=%.3f Yaw=%.2f | Vorderreifen soll %s ist %s | Hinterreifen soll %s ist %s' % (
        p[0], p[1], p[2], PF.round(1), pix(wpt(cf_, *p)).round(1), PR.round(1), pix(wpt(cr_, *p)).round(1)))
    CAR_X, CAR_Y, CAR_YAW = p
    car.rotation_euler = (0, 0, math.radians(90 + 180 * int(F('flip', 0)) + CAR_YAW)); car.location = (CAR_X, CAR_Y, -0.005)
    cs.location = car.location + Vector((0, 0, 0.009)); cs.rotation_euler = (0, 0, car.rotation_euler.z)

# ---------------------------------------------------------------- Linienpruefung (ohne Rendern): --check=1
if int(F('check', 0)):
    from bpy_extras.object_utils import world_to_camera_view
    sc.render.resolution_x = sc.render.resolution_y = 720; bpy.context.view_layer.update()
    def pxl(P):
        v = world_to_camera_view(sc, sc.camera, Vector(P)); return np.array([v.x * 720.0, (1 - v.y) * 720.0])
    _w0 = at_height(0, 487, 0.0)
    _pn = _cam_xy(PIL_LAT2, PIL_D) + (0.0,)
    pts = [('linke Wand Fuss links', (WALL_X, _w0[1], 0.0), (0, 487)), ('linke Wand Oberkante links', (WALL_X, _w0[1], WALL_H), (0, 80)),
           ('Ecke unten', (CORNER[0], CORNER[1], 0.0), (402, 363.6)), ('Ecke oben', (CORNER[0], CORNER[1], BACK_H0), (402, 163)),
           ('Rueckwand Fuss rechts', (_rp[0], _rp[1], 0.0), (645, 369.5)), ('Rueckwand Oberkante rechts', (_rp[0], _rp[1], BACK_H1), (645, 147)),
           ('Decke links (Wand/Kante)', (_s1[0], _s1[1], WALL_H), (225, 126)), ('Decke rechts', (_s2[0], _s2[1], WALL_H), (647, 83)),
           ('Pfeiler fern unten', (_pf[0], _pf[1], 0.0), (640, 555)), ('Pfeiler fern oben', (_pf[0], _pf[1], PIL_H), (650, 47)),
           ('Pfeiler nah unten', _pn, (689, 558)), ('Pfeiler nah oben', (_pn[0], _pn[1], PIL_H), (695, 47))]
    print('LINIENPRUEFUNG  Brennweite %.0f mm  Kameradrehung %.2f Grad  Horizont y=%.0f  WALL_X=%.3f  Ecke y=%.3f  Rueckwand-Winkel %.1f Grad  Deckenkante-Winkel %.1f Grad  Wandhoehe %.2f  Pfeiler h=%.2f' % (
        FOCAL, CAM_YAW, HORIZON_PX, WALL_X, BACK_Y, math.degrees(BACK_ANG), math.degrees(SLAB_ANG), WALL_H, PIL_H))
    for nm_, w3, ph in pts:
        q = pxl(w3); print('  %-28s Render (%6.1f|%6.1f)  Foto (%5.1f|%5.1f)  Abweichung %+5.1f / %+5.1f px' % (nm_, q[0], q[1], ph[0], ph[1], q[0] - ph[0], q[1] - ph[1]))
    q = at_height(150, 441, 0.0); print('  Wandfusslinie-Test (150|441): Abstand zur Wandebene %+.3f m (0 = parallel zur Wand)' % (q[0] - WALL_X))
    q = on_plane_x(150, 110.7, WALL_X); print('  Wandoberkante-Test (150|111): Hoehe %.3f m, Soll %.3f m' % (q[2], WALL_H))
    import sys as _s; _s.exit(0)

# ---------------------------------------------------------------- Render
cy = sc.cycles
sc.render.engine = 'CYCLES'; cy.device = 'CPU'; cy.samples = SAMPLES; cy.use_denoising = True
cy.max_bounces = 14; cy.diffuse_bounces = 10; cy.glossy_bounces = 6; cy.transmission_bounces = 4
cy.sample_clamp_indirect = 0; cy.sample_clamp_direct = 0; cy.caustics_reflective = False; cy.caustics_refractive = False
sc.render.resolution_x = sc.render.resolution_y = RES; sc.render.resolution_percentage = 100
sc.view_settings.view_transform = opt.get('tm', 'Standard'); sc.view_settings.exposure = EXPO; sc.view_settings.look = opt.get('look', 'None')
sc.render.filepath = out; sc.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
print('DONE', out)
