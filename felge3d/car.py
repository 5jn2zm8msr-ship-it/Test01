# SPDX-License-Identifier: GPL-3.0-or-later
"""
Fahrzeug-Paket: Reifen, Bremse, Sattel, Ventil und Decals für vier Räder.

Geometrie (Reifenprofil, Bremsscheibe, Monobloc-Sattel, Decals) stammt aus dem Skript
"Automotive Wheel & Brake Studio" (v3.1). Die Felge selbst kommt aus dem Felgenfoto (Schritt 1).

Lokales Radsystem: Ursprung = Radmitte, Achse = X. s = +1/-1: Außenseite zeigt nach +X/-X.
Winkel beta wird von +Z Richtung +Y gemessen. Front des Fahrzeugs zeigt nach -Y.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

RUB, RIM, BED, ROT, HAT, BLK, CAL, BOL, EMB, DEC_TOP, DEC_BOT, DEC_CAL, TPH = range(13)
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


def tire_photo_mat(img):
    """Reifenfoto auf der Flanke: Gummi, matt, Farbe aus dem Foto."""
    m = get_mat(PREFIX + "Reifenfoto", (.02, .02, .02), .85, 0.0)
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    for n in [n for n in nt.nodes if n.type == 'TEX_IMAGE']:
        nt.nodes.remove(n)
    if img is not None and bsdf:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = img
        tex.extension = 'EXTEND'
        tex.location = (bsdf.location.x - 340, bsdf.location.y)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def build_materials(c, tire_img=None):
    """Materialliste in der Reihenfolge RUB, RIM, BED, ROT, HAT, BLK, CAL, BOL, EMB, DEC_TOP, DEC_BOT, DEC_CAL, TPH."""
    top, top_img = decal_mat(PREFIX + "Decal Flanke oben", c.decal_sidewall_top, (.8, .8, .8), .55, 0)
    bot, bot_img = decal_mat(PREFIX + "Decal Flanke unten", c.decal_sidewall_bottom, (.8, .8, .8), .55, 0)
    cal, cal_img = decal_mat(PREFIX + "Decal Sattel", c.decal_caliper, (.05, .05, .05), .35, 0)
    imgs = {"top": top_img, "bottom": bot_img, "caliper": cal_img}
    mats = [
        get_mat(PREFIX + "Gummi", (.018, .019, .021), .86),
        get_mat(PREFIX + "Felge (unbenutzt)", (.5, .5, .5), .5, .5),
        get_mat(PREFIX + "Bett (unbenutzt)", (.3, .3, .3), .5, .6),
        get_mat(PREFIX + "Bremsscheibe Stahl", (.30, .31, .32), .28, .9),
        get_mat(PREFIX + "Bremstopf", (.55, .56, .57), .35, .8),
        get_mat(PREFIX + "Bohrung und Schlitz", (.02, .022, .024), .6, .3),
        get_mat(PREFIX + "Bremssattel", tuple(c.caliper_color), .25, .1),
        get_mat(PREFIX + "Schrauben", (.32, .33, .34), .22, .9),
        get_mat(PREFIX + "Emblem (unbenutzt)", (.5, .5, .52), .3, .7),
        top, bot, cal,
        tire_photo_mat(tire_img),
    ]
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


def tire_profile(r_rim, W, h, b, ft, fh, k, grooves):
    R = r_rim + h
    side = tire_side(r_rim, W, h, b, ft, fh, k)
    tw = W - 2.0 * k
    gd = min(0.007, 0.1 * h)
    tread = []
    for pos, wf in sorted(TREAD_LAYOUT[max(0, min(4, grooves))], key=lambda g: -g[0]):
        xg, gw = pos * tw, W * 0.018 * wf
        tread += [(R, xg + gw), (R - gd, xg + gw * 0.6), (R - gd, xg - gw * 0.6), (R, xg - gw)]
    return side + tread + [(r, -x) for r, x in reversed(side)]


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
def build_tire(c, dims, s, mats, imgs, name, tex=None, r_well=None):
    """
    Reifenmesh. tex: dict(cx, cy, r_in, r_out, asp, w_over_h, rot, flip) für das Reifenfoto auf den
    Flanken (Mitte/Radien normiert auf Bildbreite), oder None.
    """
    d = dims
    bm = bmesh.new()
    uv_lay = bm.loops.layers.uv.verify()
    tire_faces = revolve(bm, tire_profile(d["r_rim"], d["W"], d["h"], d["b"], d["ft"], d["fh"], d["k"],
                                          c.tread_grooves), s, RUB, seg=128)
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
                t = max(-0.15, min(1.05, (rho - r0) / (r1 - r0)))
                rn = tex["r_in"] + t * (tex["r_out"] - tex["r_in"])       # Bildradius, normiert auf Breite
                loop[uv_lay].uv = (tex["cx"] + da * rn, tex["cy"] + db * rn * tex["asp"] * tex["w_over_h"])

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    apply_smoothing(me, math.radians(35))
    me.update()
    return me


# ---------------------------------------------------------------- Bremse
def build_brake(c, dims, s, mats, imgs, name, x_m, back_fn, r_well):
    d = dims
    t, disc_d = d["disc_t"], d["disc_d"]
    bm = bmesh.new()
    uv_lay = bm.loops.layers.uv.verify()
    dr = min(disc_d / 2.0, r_well - 0.024)
    r_in = dr * 0.56
    cw = t / 2.0 + 0.024
    r_c0, r_c1 = dr * 0.60, min(dr + 0.018, r_well - 0.006)

    # Platz hinter den Speichen: Bremse sitzt hinter dem rückwärtigsten Punkt des Sterns
    rear = min(back_fn(r_c0), back_fn(r_c1), back_fn(0.5 * (r_c0 + r_c1)))
    x_d = min(x_m - 0.045, rear - cw - 0.004)

    # Reibring, Trennfuge, Topf mit Verbindungsstiften
    revolve(bm, [(r_in, x_d - t / 2), (dr, x_d - t / 2), (dr, x_d + t / 2), (r_in, x_d + t / 2)],
            s, ROT, seg=128, closed=True)
    revolve(bm, [(r_in - 0.006, x_d - t * .3), (r_in, x_d - t * .3),
                 (r_in, x_d + t * .3), (r_in - 0.006, x_d + t * .3)], s, BLK, closed=True)
    cylinder(bm, s, x_d - t * .3, x_m, r_in - 0.006, HAT, seg=96)
    for i in range(12):
        a = 2 * math.pi * i / 12
        cylinder(bm, s, x_d + t / 2, x_d + t / 2 + 0.003, 0.0045, BOL,
                 center=((r_in - 0.002) * math.sin(a), (r_in - 0.002) * math.cos(a)), seg=10)

    if c.disc_style == "GELOCHT":
        hr = min(0.0045, (dr - r_in) * 0.06)
        for ring_i, fr in enumerate((0.3, 0.55, 0.8)):
            rr = r_in + (dr - r_in) * fr
            for i in range(18):
                a = 2 * math.pi * i / 18 + ring_i * 2 * math.pi / 54
                cylinder(bm, s, x_d - t / 2 - 0.0004, x_d + t / 2 + 0.0004, hr, BLK,
                         center=(rr * math.sin(a), rr * math.cos(a)), seg=10)
    elif c.disc_style == "GESCHLITZT":
        rm, L = r_in + (dr - r_in) * 0.62, (dr - r_in) * 0.42
        for side in (-1, 1):
            xc = s * (x_d + side * (t / 2 + 0.0002))
            for i in range(10):
                a = 2 * math.pi * i / 10
                box(bm, (xc, rm * math.sin(a), rm * math.cos(a)), (0.0006, L, 0.0028),
                    Matrix.Rotation(math.pi / 2 - (a + 0.55), 4, 'X'), BLK)

    # Monobloc-Sattel: Körper, erhabene Deckplatte, Schrauben, Entlüfter
    alpha = math.radians(c.caliper_angle)
    half = math.radians(36)
    revolve(bm, [(r_c0, x_d - cw), (r_c1, x_d - cw), (r_c1, x_d + cw), (r_c0, x_d + cw)],
            s, CAL, seg=32, a0=alpha - half, a1=alpha + half, closed=True)
    pr0, pr1 = r_c0 + 0.006, r_c1 - 0.006
    revolve(bm, [(pr0, x_d + cw - 0.001), (pr1, x_d + cw - 0.001),
                 (pr1, x_d + cw + 0.003), (pr0, x_d + cw + 0.003)],
            s, CAL, seg=24, a0=alpha - half * 0.72, a1=alpha + half * 0.72, closed=True)
    rc = (r_c0 + r_c1) / 2.0
    for sign in (-1, 1):
        a = s * (alpha + sign * half * 0.86)
        cylinder(bm, s, x_d + cw, x_d + cw + 0.005, 0.0075, BOL,
                 center=(rc * math.sin(a), rc * math.cos(a)), seg=12)
    a = s * (alpha - half * 0.92)
    cylinder(bm, s, x_d + cw, x_d + cw + 0.01, 0.0028, BOL,
             center=((r_c1 - 0.006) * math.sin(a), (r_c1 - 0.006) * math.cos(a)), seg=8)
    x_plate = x_d + cw + 0.003
    arc_decal(bm, s, uv_lay, imgs.get("caliper"), DEC_CAL, rc, s * alpha,
              (pr1 - pr0) * c.decal_caliper_scale, rc * 2 * half * 0.6 * c.decal_caliper_scale,
              lambda r: x_plate, lift=0.0003, nu=24, nv=1)

    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    apply_smoothing(me, math.radians(35))
    me.update()
    return me, x_d


def clear_old():
    old = bpy.data.collections.get(COLL_NAME)
    if not old:
        return
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
