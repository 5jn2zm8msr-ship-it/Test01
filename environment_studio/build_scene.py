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
KARO = float(os.environ.get('KARO', '1.0'))   # Lack dunkler
KONT = float(os.environ.get('KONT', '0.3'))   # Kontrast der Basisfarbe (Textur war zu flau)
METALL = float(os.environ.get('METALL', '0.25'))  # metallischer Lack/Teile; Weiss (Felgen) bleibt unmetallisch
nt = mat.node_tree
for l in list(nt.links):
    if l.to_node == bsdf and l.to_socket.name == 'Base Color':
        src = l.from_socket
        hs = nt.nodes.new('ShaderNodeHueSaturation'); hs.inputs['Saturation'].default_value = float(os.environ.get('SAT', '0.5'))  # Textur-Blaustich raus
        nt.links.new(src, hs.inputs['Color'])
        bc = nt.nodes.new('ShaderNodeBrightContrast'); bc.inputs['Contrast'].default_value = KONT; bc.inputs['Bright'].default_value = float(os.environ.get('HELL', '0.05'))
        nt.links.new(hs.outputs['Color'], bc.inputs['Color'])
        mxn = nt.nodes.new('ShaderNodeMix'); mxn.data_type = 'RGBA'; mxn.blend_type = 'MULTIPLY'
        mxn.inputs['Factor'].default_value = 1.0
        lum0 = nt.nodes.new('ShaderNodeRGBToBW'); nt.links.new(src, lum0.inputs['Color'])
        dk = nt.nodes.new('ShaderNodeValToRGB'); nt.links.new(lum0.outputs['Val'], dk.inputs['Fac'])
        FEN = float(os.environ.get('FENDER', '0.80'))   # Kotfluegel/graue Teile 20 % dunkler, Felgen-Weiss bleibt
        cr_ = dk.color_ramp; cr_.interpolation = 'LINEAR'
        cr_.elements[0].position = 0.0; cr_.elements[0].color = (KARO, KARO, KARO*1.02, 1)
        e1 = cr_.elements.new(0.22); e1.color = (FEN, FEN, FEN, 1)
        e2 = cr_.elements.new(0.55); e2.color = (FEN, FEN, FEN, 1)
        cr_.elements[-1].position = 0.80; cr_.elements[-1].color = (1, 1, 1, 1)
        nt.links.new(dk.outputs['Color'], mxn.inputs['B'])
        nt.links.new(bc.outputs['Color'], mxn.inputs['A']); nt.links.new(mxn.outputs['Result'], bsdf.inputs['Base Color'])
        # Metallic nach Helligkeit: dunkle Flaechen metallisch, helle (weisse Felgen) nicht
        lum = nt.nodes.new('ShaderNodeRGBToBW'); nt.links.new(src, lum.inputs['Color'])
        mm = nt.nodes.new('ShaderNodeMapRange'); mm.clamp = True
        mm.inputs['From Min'].default_value = 0.22; mm.inputs['From Max'].default_value = 0.55
        mm.inputs['To Min'].default_value = METALL; mm.inputs['To Max'].default_value = 0.0
        nt.links.new(lum.outputs['Val'], mm.inputs['Value'])
        for ll in list(nt.links):
            if ll.to_node == bsdf and ll.to_socket.name == 'Metallic': nt.links.remove(ll)
        nt.links.new(mm.outputs['Result'], bsdf.inputs['Metallic'])
        break

# ---- Windschutzscheibe (Positionsmaske), Dirt ----
def mathn(op, a=None, b=None, clamp=False):
    n_ = nt.nodes.new('ShaderNodeMath'); n_.operation = op; n_.use_clamp = clamp
    if a is not None: n_.inputs[0].default_value = a
    if b is not None: n_.inputs[1].default_value = b
    return n_
tcm = nt.nodes.new('ShaderNodeTexCoord'); spm = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tcm.outputs['Object'], spm.inputs['Vector'])
def cmp_(op, sock, v):
    n_ = mathn(op, None, v); nt.links.new(sock, n_.inputs[0]); return n_.outputs[0]
absy = mathn('ABSOLUTE'); nt.links.new(spm.outputs['Y'], absy.inputs[0])
WS = [float(v) for v in os.environ.get('WS', '-1.30,-0.60,0.72,1.22,1.62').split(',')]   # x0,x1,|y|max,z0,z1
conds = [cmp_('GREATER_THAN', spm.outputs['X'], WS[0]), cmp_('LESS_THAN', spm.outputs['X'], WS[1]), cmp_('LESS_THAN', absy.outputs[0], WS[2]),
         cmp_('GREATER_THAN', spm.outputs['Z'], WS[3]), cmp_('LESS_THAN', spm.outputs['Z'], WS[4])]
mask = conds[0]
for c_ in conds[1:]:
    mm_ = mathn('MULTIPLY'); nt.links.new(mask, mm_.inputs[0]); nt.links.new(c_, mm_.inputs[1]); mask = mm_.outputs[0]
def mixc(fac_sock, a_sock_or_val, b_val, dtype='RGBA'):
    n_ = nt.nodes.new('ShaderNodeMix'); n_.data_type = dtype
    nt.links.new(fac_sock, n_.inputs['Factor'])
    ia = n_.inputs['A']; ib = n_.inputs['B']
    if hasattr(a_sock_or_val, 'node'): nt.links.new(a_sock_or_val, ia)
    else: ia.default_value = a_sock_or_val
    ib.default_value = b_val
    return n_
# Dirt: grober + feiner Noise, unten (Schweller/Reifen) staerker, Staubfarbe, leicht rauer
nz1 = nt.nodes.new('ShaderNodeTexNoise'); nz1.inputs['Scale'].default_value = 9.0; nz1.inputs['Detail'].default_value = 12; nz1.inputs['Roughness'].default_value = 0.7
nz2 = nt.nodes.new('ShaderNodeTexNoise'); nz2.inputs['Scale'].default_value = 90.0; nz2.inputs['Detail'].default_value = 6
nt.links.new(tcm.outputs['Object'], nz1.inputs['Vector']); nt.links.new(tcm.outputs['Object'], nz2.inputs['Vector'])
r1 = nt.nodes.new('ShaderNodeMapRange'); r1.inputs['From Min'].default_value = 0.42; r1.inputs['From Max'].default_value = 0.68; nt.links.new(nz1.outputs['Fac'], r1.inputs['Value'])
r2 = nt.nodes.new('ShaderNodeMapRange'); r2.inputs['From Min'].default_value = 0.50; r2.inputs['From Max'].default_value = 0.75; r2.inputs['To Max'].default_value = 0.5; nt.links.new(nz2.outputs['Fac'], r2.inputs['Value'])
hz = nt.nodes.new('ShaderNodeMapRange'); hz.inputs['From Min'].default_value = 1.4; hz.inputs['From Max'].default_value = 0.15; nt.links.new(spm.outputs['Z'], hz.inputs['Value'])
d1 = mathn('MULTIPLY'); nt.links.new(r1.outputs[0], d1.inputs[0]); nt.links.new(hz.outputs[0], d1.inputs[1])
d2 = mathn('ADD'); nt.links.new(d1.outputs[0], d2.inputs[0]); nt.links.new(r2.outputs[0], d2.inputs[1])
DIRT = float(os.environ.get('DIRT', '0.42'))
d3 = mathn('MULTIPLY', None, DIRT, True); nt.links.new(d2.outputs[0], d3.inputs[0])
inv = mathn('SUBTRACT', 1.0, None); nt.links.new(mask, inv.inputs[1])
dirtf = mathn('MULTIPLY', None, None, True); nt.links.new(d3.outputs[0], dirtf.inputs[0]); nt.links.new(inv.outputs[0], dirtf.inputs[1])
bclink = next(l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Base Color')
base_src = bclink.from_socket
m_dirt = mixc(dirtf.outputs[0], base_src, (0.16, 0.135, 0.11, 1)); nt.links.new(base_src, m_dirt.inputs['A'])
m_glass = mixc(mask, m_dirt.outputs['Result'], (0.012, 0.014, 0.018, 1)); nt.links.new(m_dirt.outputs['Result'], m_glass.inputs['A'])
nt.links.new(m_glass.outputs['Result'], bsdf.inputs['Base Color'])
# Normal-Map in der Scheibe nahezu aus (weniger Noise)
for n_ in nt.nodes:
    if n_.type == 'NORMAL_MAP':
        sm = mathn('SUBTRACT', 1.0, None); mk = mathn('MULTIPLY', None, 0.92); nt.links.new(mask, mk.inputs[0]); nt.links.new(mk.outputs[0], sm.inputs[1])
        nt.links.new(sm.outputs[0], n_.inputs['Strength'])
GLASS_R = float(os.environ.get('GLASS_R', '0.07')); GLASS_M = float(os.environ.get('GLASS_M', '0.9'))

RAU_MIN = float(os.environ.get('RAU_MIN', '0.30'))
for l in list(nt.links):
    if l.to_node == bsdf and l.to_socket.name == 'Roughness':
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['From Min'].default_value = 0; mr.inputs['From Max'].default_value = 1
        mr.inputs['To Min'].default_value = RAU_MIN; mr.inputs['To Max'].default_value = 1.0
        nt.links.new(l.from_socket, mr.inputs['Value']); nt.links.new(mr.outputs['Result'], bsdf.inputs['Roughness'])
        break
# Scheibe: glatt + metallisch, Dirt: rauer
rl = next(l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Roughness')
r_dirt = mixc(dirtf.outputs[0], rl.from_socket, 0.92, 'FLOAT'); nt.links.new(rl.from_socket, r_dirt.inputs['A'])
r_gl = mixc(mask, r_dirt.outputs['Result'], GLASS_R, 'FLOAT'); nt.links.new(r_dirt.outputs['Result'], r_gl.inputs['A'])
nt.links.new(r_gl.outputs['Result'], bsdf.inputs['Roughness'])
ml = next((l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Metallic'), None)
m_gl = mixc(mask, ml.from_socket if ml else bsdf.inputs['Metallic'].default_value, GLASS_M, 'FLOAT')
if ml: nt.links.new(ml.from_socket, m_gl.inputs['A'])
nt.links.new(m_gl.outputs['Result'], bsdf.inputs['Metallic'])
if os.environ.get('DEBUGMASK'):
    bsdf.inputs['Emission Color'].default_value = (1, 0, 0, 1); nt.links.new(mask, bsdf.inputs['Emission Strength'])

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
mr.inputs['To Min'].default_value = float(os.environ.get('EM_BODEN', '0.03')); mr.inputs['To Max'].default_value = float(os.environ.get('EM_WAND', '0.6'))
cnt.links.new(m4.outputs['Value'], mr.inputs['Value'])
nz = cnt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 1.6; nz.inputs['Detail'].default_value = 8; nz.inputs['Roughness'].default_value = 0.65
cnt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
nr = cnt.nodes.new('ShaderNodeMapRange'); nr.inputs['To Min'].default_value = float(os.environ.get('BO_R0', '0.16')); nr.inputs['To Max'].default_value = float(os.environ.get('BO_R1', '0.48'))
cnt.links.new(nz.outputs['Fac'], nr.inputs['Value']); cnt.links.new(nr.outputs['Result'], cb.inputs['Roughness'])
cb.inputs['Metallic'].default_value = float(os.environ.get('BO_M', '0.15')); cb.inputs['Specular IOR Level'].default_value = 0.8
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
bgn.inputs['Color'].default_value = (0.82, 0.83, 0.85, 1); bgn.inputs['Strength'].default_value = float(os.environ.get('WORLD', '0.22'))

LK = float(os.environ.get('LK', '0.02'))
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
area('Softbox_Decke', (-1.5, 1.0, 7.5), (0, 0, 0.8), 5.5, 12000*LK, (1.0, 0.99, 0.98), size_y=4.5)
# Hauptlicht seitlich/hoch, klein -> klarere Schlagschatten-Konturen auf dem Boden
area('Key_Schlagschatten', (float(os.environ.get('KX', '5.5')), float(os.environ.get('KY', '5.0')), 6.5), (0, 0, 0.4), 2.6, float(os.environ.get('KP', '55000'))*LK, (1.0, 0.98, 0.96), size_y=2.6)
area('Streifen_links', (-7.5, -6.0, 3.2), (0, 0, 0.9), 1.8, 5000*LK, (0.97, 0.99, 1.0), size_y=6.0)
area('Streifen_rechts', (7.0, 6.5, 3.5), (0, 0, 0.9), 1.8, 4000*LK, (0.97, 0.99, 1.0), size_y=6.0)
area('Aufheller_vorn', (-9.0, 4.0, 1.5), (0, 0, 0.8), 6.0, 2200*LK, (0.96, 0.98, 1.0), size_y=3.0)
# Nur fuers Auto (Light-Linking): weiche Formgebung, Streiflicht auf Kanten, Glanz auf Hauben-/Seitenflaechen
LA = float(os.environ.get('LA', '0.12'))
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
