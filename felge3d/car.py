# SPDX-License-Identifier: GPL-3.0-or-later
"""
Fahrzeug-Paket: Reifen, Bremse, Sattel, Ventil und Decals für vier Räder.

Geometrie (Reifenprofil, Bremsscheibe, Monobloc-Sattel, Decals) stammt aus dem Skript
"Automotive Wheel & Brake Studio" (v3.1). Die Felge selbst kommt aus dem Felgenfoto (Schritt 1).

Lokales Radsystem: Ursprung = Radmitte, Achse = X. s = +1/-1: Außenseite zeigt nach +X/-X.
Winkel beta wird von +Z Richtung +Y gemessen. Front des Fahrzeugs zeigt im lokalen Radsystem nach -Y.
Im Paket stehen die Räder um 90° um Z gedreht an einem Anker-Empty: Achse = Welt-Y, Radstand = Welt-X (Front = +X, links = +Y).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

RUB, RIM, BED, ROT, HAT, BLK, CAL, BOL, EMB, DEC_TOP, DEC_BOT, DEC_CAL, TPH, TRD, BRK, BRM, BRD, BRDM, PAD = range(19)
COLL_NAME = "Felge3D | Fahrzeug-Paket"
PREFIX = "Felge3D | "


# ---------------------------------------------------------------- Materialien
def get_mat(name, color, rough=0.4, metal=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1.0)
    m.roughness = rough
    m.metallic = metal
    m.use_nodes = True
    bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
    return m


def set_alpha_mode(m, transparent):
    """Alpha-Darstellung für Eevee, kompatibel mit Blender 3.6 bis 4.x."""
    if hasattr(m, "surface_render_method"):          # ab 4.2
        m.surface_render_method = 'DITHERED'
    if hasattr(m, "blend_method"):
        try:
            m.blend_method = 'HASHED' if transparent else 'OPAQUE'
        except TypeError:
            pass
    if hasattr(m, "shadow_method"):
        try:
            m.shadow_method = 'HASHED' if transparent else 'OPAQUE'
        except TypeError:
            pass


def decal_mat(name, filepath, fallback, rough, metal):
    """Material mit optionalem PNG (Farbe + Alpha). Gibt (Material, Bild oder None) zurück."""
    m = get_mat(name, fallback, rough, metal)
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    for n in [n for n in nt.nodes if n.type == 'TEX_IMAGE']:
        nt.nodes.remove(n)
    if bsdf:
        bsdf.inputs["Alpha"].default_value = 1.0
    img = None
    path = bpy.path.abspath(filepath) if filepath else ""
    if path and bsdf:
        try:
            img = bpy.data.images.load(path, check_existing=True)
            tex = nt.nodes.new('ShaderNodeTexImage')
            tex.image = img
            tex.extension = 'CLIP'
            tex.interpolation = 'Cubic'
            tex.location = (bsdf.location.x - 340, bsdf.location.y)
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        except RuntimeError as e:
            print("Felge3D: Bild für '%s' konnte nicht geladen werden:" % name, e)
            img = None
    set_alpha_mode(m, img is not None)
    return m, img


def photo_relief_mat(name, img, rough, contrast, bump, bump_dist, disp_scale, disp_mid, extension, height_img=None):
    """Foto als Farbe (mit Kontrast), als Bump (hell = hoch) und als Shader-Displacement (Cycles)."""
    m = get_mat(name, (.02, .02, .02), rough, 0.0)
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:                                             # Gummi glänzt kaum: sonst spiegelt der Himmel streifend (wirkt beige)
        _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.08)
    for n in [n for n in nt.nodes if n.type in ('TEX_IMAGE', 'BUMP', 'BRIGHTCONTRAST', 'RGBTOBW', 'DISPLACEMENT')]:
        nt.nodes.remove(n)
    if img is not None and bsdf:
        x0, y0 = bsdf.location.x, bsdf.location.y
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image, tex.extension, tex.interpolation = img, extension, 'Cubic'
        tex.location = (x0 - 900, y0)
        bc = nt.nodes.new('ShaderNodeBrightContrast')
        bc.inputs["Contrast"].default_value = contrast
        bc.location = (x0 - 650, y0 + 120)
        nt.links.new(tex.outputs["Color"], bc.inputs["Color"])
        nt.links.new(bc.outputs["Color"], bsdf.inputs["Base Color"])
        bw = nt.nodes.new('ShaderNodeRGBToBW')
        bw.location = (x0 - 650, y0 - 120)
        if height_img is not None:                       # eigene Höhenkarte (Non-Color), gleiche UV
            th = nt.nodes.new('ShaderNodeTexImage')
            th.image, th.extension, th.interpolation = height_img, extension, 'Cubic'
            th.location = (x0 - 900, y0 - 300)
            nt.links.new(th.outputs["Color"], bw.inputs["Color"])
        else:
            nt.links.new(tex.outputs["Color"], bw.inputs["Color"])
        bp = nt.nodes.new('ShaderNodeBump')
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = bump_dist
        bp.location = (x0 - 380, y0 - 120)
        nt.links.new(bw.outputs["Val"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if out:
            dp = nt.nodes.new('ShaderNodeDisplacement')
            dp.inputs["Scale"].default_value = disp_scale
            dp.inputs["Midlevel"].default_value = disp_mid
            dp.location = (x0 - 380, y0 - 330)
            nt.links.new(bw.outputs["Val"], dp.inputs["Height"])
            nt.links.new(dp.outputs["Displacement"], out.inputs["Displacement"])
            if hasattr(m, "displacement_method"):
                try:
                    m.displacement_method = 'BOTH'
                except TypeError:
                    pass
            if hasattr(m, "cycles") and hasattr(m.cycles, "displacement_method"):
                try:
                    m.cycles.displacement_method = 'BOTH'
                except TypeError:
                    pass
    return m


def _rubber(m):
    bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf:
        _set_input(bsdf, ("Specular IOR Level", "Specular"), 0.08)
    return m


def tire_photo_mat(img):
    """Reifenflanke: Beschriftung/Grafik steht hervor (hell = hoch)."""
    return photo_relief_mat(PREFIX + "Reifenfoto", img, .82, 0.35, 0.7, 0.0015, 0.0012, 0.25, 'EXTEND')


def tread_mat(img, height_img=None):
    """Lauffläche: tiefschwarzes Gummi, Profil aus der Höhenkarte (Rillen tief, Rippen hoch)."""
    return photo_relief_mat(PREFIX + "Reifenprofil", img, .94, 0.0, 2.2, 0.004, 0.0025, 0.5, 'REPEAT', height_img)


def _set_input(bsdf, names, value):
    for n in names:
        if n in bsdf.inputs:
            try:
                bsdf.inputs[n].default_value = value
            except (TypeError, ValueError):
                pass
            return True
    return False


def _photo_nodes(m, img, bump, bump_dist):
    """Foto als Basisfarbe + Bump (hell = hoch: dunkle Schlitze/Schrift liegen tiefer). Gibt (bsdf, nodes, Helligkeit) zurück."""
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    for n in [n for n in nt.nodes if n.type in ('TEX_IMAGE', 'BUMP', 'RGBTOBW', 'MAP_RANGE', 'TANGENT')]:
        nt.nodes.remove(n)
    if img is None or bsdf is None:
        return bsdf, None, None
    x0, y0 = bsdf.location.x, bsdf.location.y
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image, tex.extension, tex.interpolation = img, 'EXTEND', 'Cubic'
    tex.location = (x0 - 700, y0)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bw = nt.nodes.new('ShaderNodeRGBToBW')
    bw.location = (x0 - 460, y0 - 200)
    nt.links.new(tex.outputs["Color"], bw.inputs["Color"])
    bp = nt.nodes.new('ShaderNodeBump')
    bp.inputs["Strength"].default_value = bump
    bp.inputs["Distance"].default_value = bump_dist
    bp.location = (x0 - 240, y0 - 200)
    nt.links.new(bw.outputs["Val"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], bsdf.inputs["Normal"])
    return bsdf, tex, bw


def brake_photo_mat(name, img, tint=None):
    """
    Sattel: Klarlack (Coat); Schrift/Kratzer als leichter Bump. Ohne tint kommt die Farbe aus dem Foto, mit tint (sRGB-Werte 0..1,
    z. B. Weiß) bestimmt der Nutzer die Farbe: das Foto liefert nur noch die Helligkeitsstruktur (Schrift, Kanten, Schatten).
    """
    m = get_mat(name, (.4, .4, .4), .38, 0.0)
    for n in [n for n in m.node_tree.nodes if n.type in ('MATH', 'COMBINE_COLOR')]:       # Farbknoten eines früheren Baus entfernen
        m.node_tree.nodes.remove(n)
    bsdf, tex, bw = _photo_nodes(m, img, 0.35, 0.0015)
    if bsdf:
        _set_input(bsdf, ("Coat Weight", "Clearcoat"), 0.75)
        _set_input(bsdf, ("Coat Roughness", "Clearcoat Roughness"), 0.07)
        if tint is not None:
            lin = tuple(max(0.0, float(v)) ** 2.2 for v in tint)
            m.diffuse_color = (*lin, 1.0)
            nt = m.node_tree
            for l in list(bsdf.inputs["Base Color"].links):
                nt.links.remove(l)
            bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
            if bw is not None:                              # Helligkeit des Fotos (0.35..1) moduliert die gewählte Farbe
                x0, y0 = bsdf.location.x, bsdf.location.y
                mr = nt.nodes.new('ShaderNodeMapRange')
                mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.0, 0.7
                mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 0.35, 1.0
                mr.clamp = True
                mr.location = (x0 - 460, y0 + 60)
                nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
                comb = nt.nodes.new('ShaderNodeCombineColor')
                comb.location = (x0 - 240, y0 + 60)
                for i, ch in enumerate(("Red", "Green", "Blue")):
                    mul = nt.nodes.new('ShaderNodeMath')
                    mul.operation = 'MULTIPLY'
                    mul.location = (x0 - 330, y0 + 260 - 70 * i)
                    nt.links.new(mr.outputs["Result"], mul.inputs[0])
                    mul.inputs[1].default_value = lin[i]
                    nt.links.new(mul.outputs[0], comb.inputs[ch])
                nt.links.new(comb.outputs[0], bsdf.inputs["Base Color"])
    return m


def brake_disc_mat(name, img):
    """Scheibe: gebürsteter Stahl (Anisotropie entlang des Umfangs), Rauheit aus dem Foto, Schlitze als Bump."""
    m = get_mat(name, (.5, .5, .5), .38, 0.6)      # nicht voll metallisch: ohne HDRI wäre blanker Stahl fast schwarz
    bsdf, tex, bw = _photo_nodes(m, img, 0.5, 0.0012)
    if bsdf:
        nt = m.node_tree
        _set_input(bsdf, ("Anisotropic",), 0.55)
        tg = nt.nodes.new('ShaderNodeTangent')
        tg.direction_type, tg.axis = 'RADIAL', 'X'
        tg.location = (bsdf.location.x - 240, bsdf.location.y - 480)
        if "Tangent" in bsdf.inputs:
            nt.links.new(tg.outputs["Tangent"], bsdf.inputs["Tangent"])
        if bw is not None:
            mr = nt.nodes.new('ShaderNodeMapRange')
            mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.0, 1.0
            mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 0.62, 0.26
            mr.location = (bsdf.location.x - 460, bsdf.location.y - 420)
            nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    return m


def build_materials(c, tire_img=None, tread_img=None, tread_h=None, brake_imgs=None, cal_color=None):
    """cal_color: sRGB-Werte der Sattelfarbe (Einstellung „Sattelfarbe“); None = Farbe aus dem Foto."""
    """Materialliste in der Reihenfolge der Indizes RUB ... BRM, BRD, BRDM, PAD (siehe oben)."""
    top, top_img = decal_mat(PREFIX + "Decal Flanke oben", c.decal_sidewall_top, (.8, .8, .8), .55, 0)
    bot, bot_img = decal_mat(PREFIX + "Decal Flanke unten", c.decal_sidewall_bottom, (.8, .8, .8), .55, 0)
    cal, cal_img = decal_mat(PREFIX + "Decal Sattel", c.decal_caliper, (.05, .05, .05), .35, 0)
    imgs = {"top": top_img, "bottom": bot_img, "caliper": cal_img}
    mats = [
        _rubber(get_mat(PREFIX + "Gummi", (.018, .019, .021), .86)),
        get_mat(PREFIX + "Felge (unbenutzt)", (.5, .5, .5), .5, .5),
        get_mat(PREFIX + "Bett (unbenutzt)", (.3, .3, .3), .5, .6),
        get_mat(PREFIX + "Bremsscheibe Stahl", (.30, .31, .32), .28, .9),
        get_mat(PREFIX + "Bremstopf", (.55, .56, .57), .35, .8),
        get_mat(PREFIX + "Bohrung und Schlitz", (.02, .022, .024), .6, .3),
        get_mat(PREFIX + "Bremssattel", (.45, .6, .01), .3, .15),
        get_mat(PREFIX + "Schrauben", (.32, .33, .34), .22, .9),
        get_mat(PREFIX + "Emblem (unbenutzt)", (.5, .5, .52), .3, .7),
        top, bot, cal,
        tire_photo_mat(tire_img),
        tread_mat(tread_img, tread_h),
        brake_photo_mat(PREFIX + 'Bremse links', (brake_imgs or (None, None))[0], cal_color),
        brake_photo_mat(PREFIX + 'Bremse rechts', (brake_imgs or (None, None))[1], cal_color),
        brake_disc_mat(PREFIX + 'Bremsscheibe links', (brake_imgs or (None, None))[0]),
        brake_disc_mat(PREFIX + 'Bremsscheibe rechts', (brake_imgs or (None, None))[1]),
        get_mat(PREFIX + 'Bremsbelag', (.025, .025, .027), .92, 0.05),
    ]
    if cal_color:
        lin = tuple(max(0.0, v) ** 2.2 for v in cal_color)
        mats[CAL] = get_mat(PREFIX + 'Bremssattel', lin, .3, .15)
    return mats, imgs


# ---------------------------------------------------------------- bmesh-Helfer
def set_mat(faces, idx):
    for f in faces:
        f.material_index = idx
        f.smooth = True


def faces_of(verts):
    return {f for v in verts for f in v.link_faces}


def revolve(bm, prof, s, idx, seg=96, a0=0.0, a1=2 * math.pi, closed=False):
    full = abs((a1 - a0) - 2 * math.pi) < 1e-6
    rows = seg if full else seg + 1
    grid = []
    for j in range(rows):
        b = a0 + (a1 - a0) * j / seg
        sb, cb = math.sin(b), math.cos(b)
        grid.append([bm.verts.new((s * x, r * sb, r * cb)) for r, x in prof])
    n = len(prof)
    pairs = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed else [])
    faces = []
    for j in range(seg):
        jn = (j + 1) % rows
        for i, k in pairs:
            faces.append(bm.faces.new((grid[j][i], grid[j][k], grid[jn][k], grid[jn][i])))
    if closed and not full:
        faces.append(bm.faces.new(grid[0]))
        faces.append(bm.faces.new(list(reversed(grid[-1]))))
    set_mat(faces, idx)
    return faces


def cylinder(bm, s, x0, x1, radius, idx, center=(0.0, 0.0), seg=32):
    """Zylinder parallel zur Radachse zwischen x0 und x1 (lokal, Außenrichtung positiv)."""
    M = (Matrix.Translation((s * (x0 + x1) / 2.0, center[0], center[1]))
         @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                                radius1=radius, radius2=radius, depth=abs(x1 - x0), matrix=M)
    set_mat(faces_of(res['verts']), idx)


def cylinder_dir(bm, p0, p1, radius, idx, seg=16):
    """Zylinder zwischen zwei beliebigen Punkten."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    M = Matrix.Translation((p0 + p1) / 2.0) @ rot
    res = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg,
                                radius1=radius, radius2=radius, depth=d.length, matrix=M)
    set_mat(faces_of(res['verts']), idx)


def box(bm, center, size, rot4, idx):
    M = Matrix.Translation(center) @ rot4 @ Matrix.Diagonal((*size, 1.0))
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=M)
    set_mat(faces_of(res['verts']), idx)


def arc_decal(bm, s, uv_lay, img, idx, radius, phi0, height, max_len, x_at,
              bottom=False, lift=0.0004, nu=48, nv=4):
    """Gebogenes Bild-Decal auf einem Kreisbogen (folgt der Flankenkontur)."""
    if img is None or img.size[0] == 0 or img.size[1] == 0:
        return
    aspect = img.size[0] / img.size[1]
    length = height * aspect
    if length > max_len:
        length, height = max_len, max_len / aspect
    rows = []
    for j in range(nv + 1):
        v = j / nv
        row = []
        for i in range(nu + 1):
            u = i / nu
            if bottom:
                rad = radius - (v - 0.5) * height
                phi = phi0 - (u - 0.5) * length / radius
            else:
                rad = radius + (v - 0.5) * height
                phi = phi0 + (u - 0.5) * length / radius
            row.append((bm.verts.new((s * (x_at(rad) + lift),
                                      s * rad * math.sin(phi), rad * math.cos(phi))), u, v))
        rows.append(row)
    faces = []
    for j in range(nv):
        for i in range(nu):
            q = (rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i])
            f = bm.faces.new([cc[0] for cc in q])
            for loop, cc in zip(f.loops, q):
                loop[uv_lay].uv = (cc[1], cc[2])
            faces.append(f)
    set_mat(faces, idx)


def profile_x(points, r):
    pts = sorted(points)
    if r <= pts[0][0]:
        return pts[0][1]
    for (r0, x0), (r1, x1) in zip(pts, pts[1:]):
        if r0 <= r <= r1:
            return x0 + (x1 - x0) * (r - r0) / max(1e-9, r1 - r0)
    return pts[-1][1]


# Asymmetrisches Profil: (Position relativ zur Laufflächenbreite, +0.5 = außen; Breitenfaktor)
TREAD_LAYOUT = {
    0: [],
    1: [(-0.05, 1.3)],
    2: [(-0.22, 1.2), (0.12, 1.0)],
    3: [(-0.30, 1.25), (-0.05, 1.3), (0.20, 0.9)],
    4: [(-0.34, 1.2), (-0.14, 1.3), (0.06, 1.1), (0.24, 0.8)],
}


def tire_side(r_rim, W, h, b, ft, fh, k):
    R = r_rim + h
    r_mid = min(max(r_rim + 0.5 * h, r_rim + fh * 1.7 + 0.002), R - k - 0.002)
    side = [(r_rim + fh * 0.55, b + ft * 0.5),
            (r_rim + fh * 1.15, b + ft + 0.004),     # Felgenschutzwulst
            (r_rim + fh * 1.6, b + ft + 0.002),
            (r_mid, W / 2.0)]
    for i in range(7):
        a = (math.pi / 2.0) * i / 6.0
        side.append((R - k + k * math.sin(a), W / 2.0 - k + k * math.cos(a)))
    return side


def densify(points, step=0.005):
    out = [points[0]]
    for (r0, x0), (r1, x1) in zip(points, points[1:]):
        n = max(1, int(math.ceil(math.hypot(r1 - r0, x1 - x0) / step)))
        for i in range(1, n + 1):
            t = i / n
            out.append((r0 + (r1 - r0) * t, x0 + (x1 - x0) * t))
    return out


def tire_profile(r_rim, W, h, b, ft, fh, k, grooves):
    R = r_rim + h
    side = tire_side(r_rim, W, h, b, ft, fh, k)
    tw = W - 2.0 * k
    gd = min(0.007, 0.1 * h)
    tread = []
    for pos, wf in sorted(TREAD_LAYOUT[max(0, min(4, grooves))], key=lambda g: -g[0]):
        xg, gw = pos * tw, W * 0.018 * wf
        tread += [(R, xg + gw), (R - gd, xg + gw * 0.6), (R - gd, xg - gw * 0.6), (R, xg - gw)]
    return densify(side + tread + [(r, -x) for r, x in reversed(side)], 0.005)


def apply_smoothing(me, angle):
    if hasattr(me, "use_auto_smooth"):          # bis Blender 4.0
        me.use_auto_smooth = True
        me.auto_smooth_angle = angle
    elif hasattr(me, "set_sharp_from_angle"):   # ab Blender 4.1
        me.set_sharp_from_angle(angle=angle)


# ---------------------------------------------------------------- Maße
def pick(c, front, name):
    return getattr(c, ("front_" if front else "rear_") + name)


def wheel_dims(c, front):
    """Alle Maße eines Rads (Meter). rim_width_in = Felgenbreite inkl. Hornstärke für die Foto-Felge."""
    rim_in = pick(c, front, "rim")
    j_in = pick(c, front, "rim_width")
    W = pick(c, front, "width") / 1000.0
    asp = pick(c, front, "aspect") / 100.0
    r_rim = rim_in * 0.0254 / 2.0
    h = W * asp
    R = r_rim + h
    ft = min(0.012, W * 0.04)
    fh = min(0.0175, h * 0.3)
    b = min(j_in * 0.0254 / 2.0, W / 2.0 - ft - 0.006)
    k = min(0.3 * h, 0.09 * W)
    rim_out = b + ft * 0.5                       # Vorderkante des Felgenhorns (axial)
    return dict(rim_in=rim_in, j_in=j_in, et=pick(c, front, "et") / 1000.0, W=W, h=h, R=R, r_rim=r_rim,
                ft=ft, fh=fh, b=b, k=k, rim_out=rim_out, rim_width_in=2.0 * rim_out / 0.0254,
                disc_d=pick(c, front, "disc") / 1000.0, disc_t=pick(c, front, "disc_thickness") / 1000.0)


def back_profile(star_verts, half_width, n_front=None):
    """
    Rückseite des Felgensterns: kleinste axiale Lage x je Radius (in m), aus den Mesh-Vertices.
    Gibt f(r) -> x (axial, Außenseite positiv) zurück; Radien ohne Material werden überbrückt.
    """
    v = np.asarray(star_verts)
    nv = len(v) // 2
    back = v[nv:]                                # zweite Hälfte = Rückseite
    r = np.hypot(back[:, 0], back[:, 1])
    x = back[:, 2] + half_width                  # Felgenmitte = 0
    bins = np.arange(0.0, r.max() + 0.003, 0.003)
    idx = np.digitize(r, bins)
    rs, xs = [], []
    for i in np.unique(idx):
        m = idx == i
        rs.append(r[m].mean())
        xs.append(x[m].min())
    rs, xs = np.array(rs), np.array(xs)
    order = np.argsort(rs)
    rs, xs = rs[order], xs[order]

    def f(rr):
        return float(np.interp(rr, rs, xs))
    f.rear_min = float(xs.min())
    return f


# ---------------------------------------------------------------- Reifen
def build_tire(c, dims, s, mats, imgs, name, tex=None, r_well=None, tread=None):
    """
    Reifenmesh. tex: dict(cx, cy, r_in, r_out, asp, w_over_h, rot, flip) für das Reifenfoto auf den
    Flanken (Mitte/Radien normiert auf Bildbreite), oder None.
    """
    d = dims
    bm = bmesh.new()
    uv_lay = bm.loops.layers.uv.verify()
    tire_faces = revolve(bm, tire_profile(d["r_rim"], d["W"], d["h"], d["b"], d["ft"], d["fh"], d["k"],
                                          c.tread_grooves), s, RUB, seg=384)
    # Ventil (im Felgenbett)
    if r_well is not None:
        vb = math.pi + 0.5 * (2 * math.pi / 7.0)
        dv = Vector((0.0, math.sin(vb), math.cos(vb)))
        ax = s * (d["b"] - 0.02)
        cylinder_dir(bm, Vector((ax, 0, 0)) + dv * (r_well - 0.022), Vector((ax, 0, 0)) + dv * r_well,
                     0.004, BOL, seg=12)
    # Reifenflanken-Decals
    side = tire_side(d["r_rim"], d["W"], d["h"], d["b"], d["ft"], d["fh"], d["k"])
    band_lo, band_hi = d["r_rim"] + d["fh"] * 1.8, d["R"] - d["k"] * 0.6
    rt = (band_lo + band_hi) / 2.0
    hgt = (band_hi - band_lo) * 0.85 * c.decal_sidewall_scale
    max_len = rt * math.radians(c.decal_sidewall_arc)
    flank = lambda r: profile_x(side, r)
    arc_decal(bm, s, uv_lay, imgs.get("top"), DEC_TOP, rt, 0.0, hgt, max_len, flank)
    arc_decal(bm, s, uv_lay, imgs.get("bottom"), DEC_BOT, rt, math.pi, hgt, max_len, flank, bottom=True)

    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    flank_verts, tread_verts = set(), set()

    # Reifenfoto auf die Flanken (Flächen, die zur Achse zeigen), Lauffläche bleibt Gummi.
    # Radial angepasst: Bildring [r_in .. r_out] (Wulst .. Reifenkante) <-> Mesh [Felgenhorn .. Reifenkante],
    # damit dasselbe Foto auf jede Reifengröße passt.
    if tex is not None:
        th = math.radians(tex.get("rot", 0.0))
        ct, st = math.cos(th), math.sin(th)
        r0, r1 = d["r_rim"] + d["fh"] * 0.5, d["R"]
        for f in tire_faces:
            if not f.is_valid or abs(f.normal.x) < 0.3:
                continue
            f.material_index = TPH
            flank_verts.update(v.index for v in f.verts)
            for loop in f.loops:
                co = loop.vert.co
                a, bb = s * co.y, co.z                    # Bild-Rechts / Bild-Oben (von außen gesehen)
                rho = math.hypot(a, bb)
                if rho < 1e-9:
                    continue
                if tex.get("flip"):
                    a = -a
                da, db = a / rho, bb / rho
                da, db = da * ct - db * st, da * st + db * ct
                t = max(0.0, min(1.0, (rho - r0) / (r1 - r0)))
                rn = tex["r_in"] + t * (tex["r_out"] - tex["r_in"])       # Bildradius, normiert auf Breite
                loop[uv_lay].uv = (tex["cx"] + da * rn, tex["cy"] + db * rn * tex["asp"] * tex["w_over_h"])

    # Laufflächenprofil: u quer über die Breite, v rund um den Umfang (ganzzahlige Wiederholungen -> nahtlos)
    if tread is not None:
        Rt = d["R"]
        pitch = tread["aspect"] * d["W"]                          # Kachellänge in m (proportional zur Reifenbreite)
        reps = max(1, int(round(2 * math.pi * Rt / pitch)))
        for f in bm.faces:
            if not f.is_valid or f.material_index != RUB:
                continue
            f.material_index = TRD
            cs = sum((v.co for v in f.verts), Vector()) / len(f.verts)
            phi_c = math.atan2(cs.y, cs.z)
            tread_verts.update(v.index for v in f.verts)
            for loop in f.loops:
                co = loop.vert.co
                u = (s * co.x + d["W"] / 2.0) / d["W"]
                dphi = (math.atan2(co.y, co.z) - phi_c + math.pi) % (2 * math.pi) - math.pi
                loop[uv_lay].uv = (u, reps * (phi_c + dphi) / (2 * math.pi))

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    apply_smoothing(me, math.radians(35))
    me.update()
    only_flank = flank_verts - tread_verts                  # gemeinsame Randpunkte bleiben unverschoben (keine Naht)
    me["flank_verts"] = sorted(only_flank)
    me["tread_verts"] = sorted(tread_verts - flank_verts)           # für die Vertexgruppe (Displacement nur auf der Flanke)
    me["uv_name"] = me.uv_layers[0].name if me.uv_layers else ""
    return me


def _displace(obj, name, group, verts, tex_img, tex_name, strength_mm, mid, uv_name):
    vg = obj.vertex_groups.new(name=group)
    vg.add(verts, 1.0, 'REPLACE')
    tx = bpy.data.textures.get(PREFIX + tex_name) or bpy.data.textures.new(PREFIX + tex_name, 'IMAGE')
    tx.image = tex_img
    tx.extension = 'REPEAT' if tex_name == "Profilrelief" else 'EXTEND'
    dis = obj.modifiers.new(name, 'DISPLACE')
    dis.texture, dis.texture_coords = tx, 'UV'
    if uv_name:
        dis.uv_layer = uv_name
    dis.vertex_group, dis.direction = group, 'NORMAL'
    dis.mid_level, dis.strength = mid, strength_mm / 1000.0


def add_relief(obj, flank_img, flank_mm, tread_img=None, tread_mm=0.0, level=1):
    """Displacement: Subdivision (einfach) + je ein Displace-Modifier für Flanke (Schrift) und Lauffläche (Profil)."""
    me = obj.data
    fv, tv = list(me.get("flank_verts", [])), list(me.get("tread_verts", []))
    uv_name = me.get("uv_name", "")
    do_f = flank_img is not None and fv and flank_mm > 0
    do_t = tread_img is not None and tv and tread_mm > 0
    if not (do_f or do_t):
        return
    sub = obj.modifiers.new("Reifen-Unterteilung", 'SUBSURF')
    sub.subdivision_type = 'SIMPLE'
    sub.levels, sub.render_levels = level, level + 1
    if do_f:
        _displace(obj, "Reifen-Relief", "Flanke", fv, flank_img, "Reifenrelief", flank_mm, 0.25, uv_name)
    if do_t:
        _displace(obj, "Profil-Relief", "Lauffläche", tv, tread_img, "Profilrelief", tread_mm, 0.5, uv_name)


# ---------------------------------------------------------------- Bremse
def _face(bm, verts, want, axis='x'):
    """Fläche anlegen und so drehen, dass die Normale in Richtung 'want' (Vorzeichen) zeigt."""
    f = bm.faces.new(verts)
    f.normal_update()
    comp = f.normal.x if axis == 'x' else f.normal.dot(Vector((0.0, want[0], want[1])))
    if (comp * (want if axis == 'x' else 1.0)) < 0:
        f.normal_flip()
    f.smooth = True
    return f


def _ray_radii(poly, phi):
    """Größter Abstand vom Ursprung, in dem der Strahl (Winkel phi) die Polygonkante schneidet (None = kein Treffer)."""
    ux, uy = math.cos(phi), math.sin(phi)
    best = None
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        den = -ux * ey + ex * uy
        if abs(den) < 1e-12:
            continue
        t = (-x1 * ey + ex * y1) / den
        k = (ux * y1 - uy * x1) / den
        if t > 0 and -1e-9 <= k <= 1 + 1e-9:
            best = t if best is None else max(best, t)
    return best


def _polar_prism(bm, s, phis, r_in, r_out, x0, x1, mat):
    """Geschlossener Ringsektor-Körper (Winkel phi von +Y nach +Z; r_in/r_out je Winkel; axial x0..x1)."""
    K = len(phis)

    def v(r, p, x):
        return bm.verts.new((s * x, r * math.cos(p), r * math.sin(p)))
    A0 = [v(r_in[k], phis[k], x0) for k in range(K)]
    A1 = [v(r_in[k], phis[k], x1) for k in range(K)]
    B0 = [v(r_out[k], phis[k], x0) for k in range(K)]
    B1 = [v(r_out[k], phis[k], x1) for k in range(K)]
    faces = []
    for k in range(K - 1):
        for quad in ((A1[k], A1[k + 1], B1[k + 1], B1[k]), (A0[k], A0[k + 1], B0[k + 1], B0[k]),
                     (B0[k], B0[k + 1], B1[k + 1], B1[k]), (A0[k], A0[k + 1], A1[k + 1], A1[k])):
            faces.append(bm.faces.new(quad))
    faces.append(bm.faces.new((A0[0], A1[0], B1[0], B0[0])))
    faces.append(bm.faces.new((A0[-1], A1[-1], B1[-1], B0[-1])))
    for f in faces:
        f.material_index = mat
        f.smooth = True
    return faces


def _brake_vanes(bm, s, r0, r1, xa, xb, n, sweep, width, mat):
    """Gebogene Lüftungsstege zwischen den beiden Reibringen (xa..xb), von r0 nach r1."""
    K = 6
    for iv in range(n):
        a0 = 2 * math.pi * iv / n
        side = {-1: [], 1: []}
        for sg in (-1, 1):
            for k in range(K + 1):
                u = k / K
                r = r0 + (r1 - r0) * u
                a = a0 + sweep * u + sg * (width / 2.0) / r
                side[sg].append((bm.verts.new((s * xa, r * math.sin(a), r * math.cos(a))),
                                 bm.verts.new((s * xb, r * math.sin(a), r * math.cos(a)))))
        faces = []
        for sg in (-1, 1):
            for k in range(K):
                p, q = side[sg][k], side[sg][k + 1]
                f = bm.faces.new((p[0], q[0], q[1], p[1]))
                o = side[-sg][k]
                tang = Vector((0.0, (p[0].co.y - o[0].co.y), (p[0].co.z - o[0].co.z)))
                f.normal_update()
                if f.normal.dot(tang) < 0:
                    f.normal_flip()
                faces.append(f)
        cap = bm.faces.new((side[-1][K][0], side[1][K][0], side[1][K][1], side[-1][K][1]))
        cap.normal_update()
        rad = Vector((0.0, cap.calc_center_median().y, cap.calc_center_median().z))
        if cap.normal.dot(rad) < 0:
            cap.normal_flip()
        faces.append(cap)
        for f in faces:
            f.material_index = mat
            f.smooth = True


def build_brake(c, d, s, mats, name, x_m, back_fn, r_well, bmeta, caliper_deg=None):
    """
    Bremse als echtes 3D-Mesh, das Bremsenfoto liegt als Textur auf den passenden Flächen:
      Scheibe: innenbelüftet (zwei Reibringe + 36 gebogene Stege), Topf mit Übergang, Nabenkappe;
      Sattel: Außenplatte (Umriss aus dem Foto), Innenplatte, Brücke über dem Scheibenrand, zwei Bremsbeläge,
              zwei Torx-Schrauben und Entlüfter/Leitung (Positionen aus dem Foto).
    Die Schlitze der Scheibe kommen als Bump aus dem Foto. Der Sattel wird um die Achse auf caliper_deg gedreht
    (0 = oben, 90 = Richtung Heck, -90 = Richtung Front; Standard: vorn 90, hinten -90 = beide Richtung Fahrzeugmitte); die Textur bleibt an der Geometrie.
    Rechte Seite (s<0): Geometrie gespiegelt, Textur gespiegelt mit korrigierter Schrift.
    Gibt (Scheibenmesh, Sattelmesh, x_d) zurück.
    """
    t = d["disc_t"]
    dr = min(d["disc_d"] / 2.0, r_well - 0.024)
    r_in, r_hat = bmeta["ring_in_ratio"] * dr, bmeta["hat_ratio"] * dr
    cw = t / 2.0 + 0.024
    cs = min(1.0, (r_well - 0.006) / (bmeta["cal_rmax"] * dr))
    r_c0, r_c1 = bmeta["cal_rmin"] * dr * cs, bmeta["cal_rmax"] * dr * cs
    rear = min(back_fn(r) for r in np.linspace(r_c0, r_c1, 6))
    x_d = min(x_m - 0.045, rear - cw - 0.016)      # 12 mm Luft für Schraubenköpfe/Entlüfter hinter den Speichen
    mirror = s < 0
    PH, PHD = (BRM, BRDM) if mirror else (BRK, BRD)
    seg = 160
    tp = 0.26 * t                                           # Dicke eines Reibrings
    xo_out, xo_in = x_d + t / 2.0, x_d + t / 2.0 - tp
    xi_out, xi_in = x_d - t / 2.0, x_d - t / 2.0 + tp
    angs = [2 * math.pi * i / seg for i in range(seg)]

    def uv_of(dxr, dzr):
        return (bmeta["cx"] + (-dxr if mirror else dxr) * bmeta["Rx"], bmeta["cy_up"] + dzr * bmeta["Ry"])

    def vert(bm, x, y, z):
        return bm.verts.new((s * x, y, z))

    # ================= Scheibe + Topf
    bm = bmesh.new()
    uv_lay = bm.loops.layers.uv.verify()

    def annulus(r0, r1, x, mat, want, photo=False):
        A = [vert(bm, x, r0 * math.sin(a), r0 * math.cos(a)) for a in angs]
        B = [vert(bm, x, r1 * math.sin(a), r1 * math.cos(a)) for a in angs]
        for i in range(seg):
            j = (i + 1) % seg
            f = _face(bm, [A[i], A[j], B[j], B[i]], want * s)
            f.material_index = mat
            if photo:                                       # Reibring: linke Fotohälfte gespiegelt (Sattelbereich frei)
                for loop in f.loops:
                    co = loop.vert.co
                    loop[uv_lay].uv = uv_of(-abs(co.y) / dr, co.z / dr)

    def band(r, xa, xb, mat, outward):
        A = [vert(bm, xa, r * math.sin(a), r * math.cos(a)) for a in angs]
        B = [vert(bm, xb, r * math.sin(a), r * math.cos(a)) for a in angs]
        for i in range(seg):
            j = (i + 1) % seg
            f = bm.faces.new([A[i], A[j], B[j], B[i]])
            f.normal_update()
            radial = Vector((0.0, A[i].co.y + A[j].co.y, A[i].co.z + A[j].co.z))
            if (f.normal.dot(radial) > 0) != outward:
                f.normal_flip()
            f.material_index = mat
            f.smooth = True

    def revolve_o(prof, idx, want):
        faces = revolve(bm, prof, s, idx, seg=seg)
        f0 = faces[0]
        f0.normal_update()
        cen = f0.calc_center_median()
        rad = Vector((0.0, cen.y, cen.z)).normalized()
        if f0.normal.dot(rad * want[0] + Vector((s, 0.0, 0.0)) * want[1]) < 0:
            for f in faces:
                f.normal_flip()

    # Reibringe (Foto außen und innen), Innenflächen zu den Stegen, Kanten
    annulus(r_in, dr, xo_out, PHD, +1, True)
    annulus(r_in, dr, xo_in, ROT, -1)
    band(dr, xo_in, xo_out, ROT, True)
    annulus(r_in, dr, xi_out, PHD, -1, True)
    annulus(r_in, dr, xi_in, ROT, +1)
    band(dr, xi_out, xi_in, ROT, True)
    band(r_in, xi_out, xo_out, ROT, False)
    _brake_vanes(bm, s, r_in + 0.004, dr, xi_in, xo_in, 36, math.radians(26), 0.0075, ROT)

    # Topf: Schulter (dunkel) vom Reibring zur Topfwand, Wand, Deckel (Foto), Nabenkappe; Rückseite als Kegel
    k_top = x_m - 0.004
    shoulder = []
    for i in range(6):
        u = i / 5.0
        shoulder.append((r_in + (r_hat - r_in) * u, xo_out + (k_top - xo_out) * (1.0 - (1.0 - u) ** 2)))
    revolve_o(shoulder, BLK, (1.0, 1.0))
    revolve_o([(r_hat, k_top), (r_hat, x_m)], HAT, (1.0, 0.0))
    revolve_o([(r_in, xi_out), (r_hat, k_top)], HAT, (-1.0, -1.0))
    ctr = vert(bm, x_m, 0.0, 0.0)
    rim_v = [vert(bm, x_m, r_hat * math.sin(a), r_hat * math.cos(a)) for a in angs]
    for i in range(seg):
        f = _face(bm, [ctr, rim_v[i], rim_v[(i + 1) % seg]], +1 * s)
        f.material_index = PHD
        for loop in f.loops:
            co = loop.vert.co
            loop[uv_lay].uv = uv_of(co.y / dr, co.z / dr)
    cylinder(bm, s, x_m, x_m + 0.010, 0.17 * r_hat, BOL, seg=24)       # Nabenkappe / Mutter
    bm.normal_update()
    me_d = bpy.data.meshes.new("Bremsscheibe " + name)
    bm.to_mesh(me_d)
    bm.free()
    for m in mats:
        me_d.materials.append(m)
    apply_smoothing(me_d, math.radians(40))
    me_d.update()

    # ================= Sattel
    bm = bmesh.new()
    uv_lay = bm.loops.layers.uv.verify()
    pts = bmeta["caliper"]
    u_m = dr * cs                                           # Foto-Einheit -> Meter
    yz = [(dx * u_m, dy * u_m) for dx, dy in pts]           # +Y = Heck (Foto rechts), z = oben
    x_front, x_back = x_d + cw, x_d - cw
    gap = 0.006                                             # Luft zwischen Platte und Scheibe (Belag sitzt dazwischen)

    def plate(xa, xb, photo_front):
        """Platte mit Fotoumriss zwischen xa (außen) und xb (innen)."""
        n = len(yz)
        F = [vert(bm, xa, y, z) for y, z in yz]
        B = [vert(bm, xb, y, z) for y, z in yz]
        fs = [bm.faces.new(F), bm.faces.new(B)]
        for i in range(n):
            fs.append(bm.faces.new([F[i], F[(i + 1) % n], B[(i + 1) % n], B[i]]))
        fs[0].material_index = PH if photo_front else CAL
        for f in fs[1:]:
            f.material_index = CAL
        for f in fs:
            f.smooth = True

    plate(x_front, xo_out + gap, True)                      # Außenplatte (Foto)
    plate(xi_out - gap, x_back, False)                      # Innenplatte
    # Brücke über dem Scheibenrand: folgt dem äußeren Umriss, füllt den Spalt zwischen den Platten
    ph = [math.atan2(y, x) for x, y in pts]
    phis = list(np.linspace(min(ph) + 0.01, max(ph) - 0.01, 28))
    r_b0 = dr + 0.008
    r_o, ok = [], []
    for p in phis:
        ro = _ray_radii(yz, p)
        ok.append(ro is not None and ro > r_b0 + 0.012)
        r_o.append(max((ro or 0.0) - 0.0015, r_b0 + 0.004))
    # zusammenhängenden Bereich mit Treffern nehmen
    idx_ok = [i for i, v in enumerate(ok) if v]
    if len(idx_ok) >= 2:
        i0, i1 = idx_ok[0], idx_ok[-1]
        _polar_prism(bm, s, phis[i0:i1 + 1], [r_b0] * (i1 - i0 + 1), r_o[i0:i1 + 1],
                     xi_out - gap - 0.003, xo_out + gap + 0.003, CAL)
    # Bremsbeläge (zwischen Platte und Scheibe)
    pc = float(np.mean(ph))
    pad_phis = list(np.linspace(pc - 0.50, pc + 0.50, 7))
    pad_in, pad_out = 0.74 * dr, 0.965 * dr
    _polar_prism(bm, s, pad_phis, [pad_in] * 7, [pad_out] * 7, xo_out + 0.0008, xo_out + gap - 0.0008, PAD)
    _polar_prism(bm, s, pad_phis, [pad_in] * 7, [pad_out] * 7, xi_out - gap + 0.0008, xi_out - 0.0008, PAD)
    # Schrauben (Positionen aus dem Foto) und Entlüfter / Leitung
    for bx, by in ((0.623, 0.548), (0.712, -0.426)):
        cylinder(bm, s, x_front - 0.001, x_front + 0.006, 0.055 * u_m, BOL, center=(bx * u_m, by * u_m), seg=24)
    for bx, by, hl in ((0.668, 0.821, 0.016), (0.790, -0.700, 0.012)):
        y0, z0 = bx * u_m, by * u_m
        rad = Vector((0.0, y0, z0)).normalized()
        hl = max(0.004, min(hl, r_well - 0.004 - math.hypot(y0, z0)))      # nicht in die Felge ragen
        cylinder(bm, s, x_front - 0.001, x_front + 0.010, 0.013, BOL, center=(y0, z0), seg=12)
        p0 = Vector((s * (x_front + 0.010), y0, z0))
        cylinder_dir(bm, p0, p0 + rad * hl, 0.0085, BLK, seg=12)
    bm.normal_update()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:                                       # Foto-UV (vor dem Drehen): Position -> Fotokoordinate
        if f.material_index == PH:
            f.normal_update()
            if abs(f.normal.x) > 0.9 and f.normal.x * s > 0:
                for loop in f.loops:
                    co = loop.vert.co
                    loop[uv_lay].uv = uv_of(co.y / u_m, co.z / u_m)
    # Schraubenköpfe: Deckel zeigt das Foto (Torx-Kopf), sonst Metall
    for f in bm.faces:
        if f.material_index == BOL:
            f.normal_update()
            cen = f.calc_center_median()
            if f.normal.x * s > 0.9 and abs(cen.x * s - (x_front + 0.006)) < 1e-5:
                f.material_index = PH
                for loop in f.loops:
                    co = loop.vert.co
                    loop[uv_lay].uv = uv_of(co.y / u_m, co.z / u_m)
    delta = math.radians(90.0 - (c.front_caliper_angle if caliper_deg is None else caliper_deg))
    if abs(delta) > 1e-6:
        bmesh.ops.rotate(bm, cent=(0.0, 0.0, 0.0), matrix=Matrix.Rotation(delta, 3, 'X'), verts=bm.verts)
    r_max = max(math.hypot(v.co.y, v.co.z) for v in bm.verts)
    bm.normal_update()
    me_c = bpy.data.meshes.new("Bremssattel " + name)
    bm.to_mesh(me_c)
    bm.free()
    for m in mats:
        me_c.materials.append(m)
    apply_smoothing(me_c, math.radians(35))
    me_c.update()
    me_c["r_max"] = r_max
    return me_d, me_c, x_d


def clear_old(keep=()):
    """Altes Paket entfernen; Objekte in `keep` (z. B. der Anker-Empty mit der vom Nutzer eingestellten Lage) bleiben erhalten."""
    old = bpy.data.collections.get(COLL_NAME)
    if not old:
        return
    for o in keep:
        if o is not None and o.name in old.objects:
            old.objects.unlink(o)
    meshes = {o.data for o in old.all_objects if o.type == 'MESH'}
    for o in list(old.all_objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for me in meshes:
        if me.users == 0:
            bpy.data.meshes.remove(me)
    bpy.data.collections.remove(old)


# Rotation der Felge (Foto-Frame: z = Achse, x = rechts, y = oben) in das Radsystem (X = Achse nach außen)
def rim_matrix(s):
    if s > 0:
        return Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    return Matrix(((0, 0, -1, 0), (-1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
