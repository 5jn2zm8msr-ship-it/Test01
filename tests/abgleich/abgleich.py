# SPDX-License-Identifier: GPL-3.0-or-later
"""
Bildabgleich (Version 2): Foto <-> Nachbauten, mit Kamera in der Perspektive des Fotos.

Aufruf (Blender 5.3):  /tmp/venv53/bin/python tests/abgleich/abgleich.py <foto-schluessel> [...]
Umgebung: SAMPLES (48), MAXPX (1100), LABEL (Versionsbezeichnung in der Matrix), OUT (Ausgabeordner), KEEP_RATINGS=1 (Noten übernehmen).
Achtung: überschreibt das Add-on „felge3d“ im Blender-Benutzerordner dieser Blender-Installation (nur Testumgebung verwenden).

Ausgabe je Foto (OUT = tests/abgleich/out/):  <key>_vergleich.png
  Zeile 1: 1 Foto | 2 Mesh lokal (KI-Mesh) | 3 SubD lokal | 4 Meshy (nur Mesh, Referenz der Gruppe) | 5 SubD mit Meshy-Maske (cfg "maske_aus_meshy")
  Zeile 2: Überlagerung SubD/Foto | Kanten (rot Foto, cyan Nachbau, gelb deckungsgleich) | Nabe 3x (oben Foto, unten SubD)
und ein Eintrag mit Automesswerten in bewertung.json. Die Messwerte sind Hilfen, KEINE Note: Noten vergeben Reviewer und Nutzer am Bild.

Kamera: Rad im Ursprung (Achse = Y, Vorderseite nach -Y). Die optische Achse geht durch die Mitte der vorderen Felgenkante
(Ellipsenmitte im Foto), Abstand aus Brennweite und Felgenradius; bei Schrägansicht wird das Rad um die Hochachse gedreht (yaw).
Licht: neutrales Studio (Verlaufshimmel, Kamerastrahlen sehen schwarz). Die Grundfarben kommen aus dem Foto (bereits beleuchtet),
darum sind Farbabstände nur Richtwerte.
"""
import json
import math
import os
import shutil
import sys
import time

import bpy  # noqa: I001
import addon_utils
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.environ.get("OUT", os.path.join(HERE, "out"))
SAMPLES = int(os.environ.get("SAMPLES", "48"))
MAXPX = int(os.environ.get("MAXPX", "1100"))


def log(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ Farbe / Bild-Hilfen
def to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def to_lin(x):
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def lab(rgb_lin):
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = rgb_lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def delta_e(a_lin, b_lin):
    return float(np.linalg.norm(lab(np.asarray(a_lin)) - lab(np.asarray(b_lin))))


def lum(rgb_lin):
    return 0.2126 * rgb_lin[..., 0] + 0.7152 * rgb_lin[..., 1] + 0.0722 * rgb_lin[..., 2]


def resample(a, h, w):
    yy = (np.arange(h) * a.shape[0] / h).astype(int)
    xx = (np.arange(w) * a.shape[1] / w).astype(int)
    return a[yy][:, xx]


def load_photo(path):
    """Bild als linear-sRGB (y von oben). Blender liefert bei 8-Bit-Bildern die gespeicherten sRGB-Werte."""
    im = bpy.data.images.load(path, check_existing=True)
    w, h = im.size
    ch = im.channels
    buf = np.empty(w * h * ch, np.float32)
    im.pixels.foreach_get(buf)
    buf = buf.reshape(h, w, ch)[::-1]
    rgb = buf[..., :3]
    if ch == 4:
        a = buf[..., 3:4]
        rgb = rgb * a + (1 - a)
    return to_lin(rgb).astype(np.float32)


def save_png(arr_srgb, path):
    h, w = arr_srgb.shape[:2]
    im = bpy.data.images.new("tmp_" + os.path.basename(path), w, h, alpha=True)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = np.clip(arr_srgb, 0, 1)
    im.pixels.foreach_set(rgba[::-1].ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def dilate(m, n=1):
    m = m.copy()
    for _ in range(n):
        p = np.pad(m, 1)
        m = (p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:])
    return m


def erode(m, n=1):
    return ~dilate(~m, n)


def outline(m):
    return m & ~erode(m, 1)


def edge_mask(gray, keep, region=None):
    """Stärkste Gradienten (Anteil keep). Mit region: Schwelle NUR aus dem Bereich (z. B. Radring), damit Hintergrund/Reifen sie nicht bestimmen."""
    gy, gx = np.gradient(gray)
    g = np.hypot(gx, gy)
    ref = g[region] if region is not None and region.any() else g
    m = g >= np.quantile(ref, 1.0 - keep)
    return m & region if region is not None else m


def dewarp(img, cx, cy, asp, half):
    """Schräges Foto entzerren: x um den Ellipsenmittelpunkt mit asp = a/b strecken; Quadrat 2*half."""
    S = int(2 * half)
    u = (np.arange(S) - half) * asp + cx
    v = np.arange(S) - half + cy
    xi = np.clip(np.round(u).astype(int), 0, img.shape[1] - 1)
    yi = np.clip(np.round(v).astype(int), 0, img.shape[0] - 1)
    out = img[yi][:, xi].copy()
    out[(v < 0) | (v > img.shape[0] - 1), :] = 0
    out[:, (u < 0) | (u > img.shape[1] - 1)] = 0
    return out


# ------------------------------------------------------------------ Szene
def install_addon():
    d = os.path.join(bpy.utils.user_resource("SCRIPTS", path="addons", create=True), "felge3d")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for f in os.listdir(os.path.join(REPO, "felge3d")):
        if f.endswith((".py", ".toml")):
            shutil.copy(os.path.join(REPO, "felge3d", f), d)
    if os.path.isdir(os.path.join(REPO, "felge3d", "assets")):                       # mitgelieferte Objekte (assets/) mitkopieren
        shutil.copytree(os.path.join(REPO, "felge3d", "assets"), os.path.join(d, "assets"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("felge3d", default_set=True)


def setup_world(sc):
    """Neutrales Studio: Verlaufshimmel (unten dunkler, oben hell, grau, ohne Farbstich) + weiche Sonne; Kamerastrahlen sehen schwarz."""
    w = bpy.data.worlds.new("W")
    w.use_nodes = True
    sc.world = w
    nt = w.node_tree
    for n in list(nt.nodes):
        if n.name != "World Output":
            nt.nodes.remove(n)
    out = nt.nodes["World Output"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -1.0, 1.0
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 0.10, 1.0
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    bg = nt.nodes.new("ShaderNodeBackground")
    comb = nt.nodes.new("ShaderNodeCombineColor")
    for nm in ("Red", "Green", "Blue"):
        nt.links.new(mr.outputs["Result"], comb.inputs[nm])
    nt.links.new(comb.outputs[0], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    black = nt.nodes.new("ShaderNodeBackground")
    black.inputs["Color"].default_value = (0, 0, 0, 1)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg.outputs[0], mix.inputs[1])
    nt.links.new(black.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    sun = bpy.data.objects.new("Sonne", bpy.data.lights.new("Sonne", "SUN"))
    sc.collection.objects.link(sun)
    sun.data.energy = 2.2
    sun.rotation_euler = (math.radians(55), 0, math.radians(25))
    sun.data.angle = math.radians(8.0)


def lip_z(col):
    """Lage der vorderen Felgenkante (größtes z im Rad-Koordinatensystem der Collection), Rad-Mitte = Ursprung."""
    root = next(o for o in col.objects if o.get("felge3d_role") == "root")
    dg = bpy.context.evaluated_depsgraph_get()
    inv = root.matrix_world.inverted()
    zs = []
    for o in col.all_objects:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        n = len(me.vertices)
        if n:
            v = np.empty(n * 3, np.float32)
            me.vertices.foreach_get("co", v)
            v = v.reshape(n, 3)
            M = np.array(inv @ ev.matrix_world)
            zs.append((v @ M[:3, :3].T + M[:3, 3])[:, 2])
        ev.to_mesh_clear()
    return float(np.percentile(np.concatenate(zs), 99.9)) if zs else 0.0


def make_camera(sc, cfg, w, h, cx, cy, rx, R_out, anchor):
    """Optische Achse durch den Ankerpunkt (Mitte der vorderen Felgenkante), Verschiebung bringt ihn auf (cx, cy)."""
    f = float(cfg.get("brennweite_mm", 135.0))
    cam_d = bpy.data.cameras.new("Kamera Foto")
    cam_d.lens = f
    cam_d.sensor_width = 36.0
    cam_d.sensor_fit = "AUTO"
    pix = 36.0 / max(w, h)                                   # Sensor-mm je Bildpixel
    dist = f * R_out / (rx * pix)                            # m (f, pix in mm; R_out in m)
    cam_d.clip_start, cam_d.clip_end = 0.1, dist * 4
    cam_d.shift_x = -(cx - w / 2.0) / max(w, h)
    cam_d.shift_y = (cy - h / 2.0) / max(w, h)
    cam = bpy.data.objects.new("Kamera Foto", cam_d)
    sc.collection.objects.link(cam)
    cam.location = (anchor.x, anchor.y - dist, anchor.z)
    cam.rotation_euler = (math.pi / 2, 0.0, 0.0)             # blickt entlang +Y, oben = +Z
    sc.camera = cam
    return cam, dist


def set_zone_colors(rim, body_rgb, front_rgb, fin):
    from felge3d import paramrim, paramui
    mb = paramui._material_of(rim.md, paramrim.BODY_COLOR_NODE)
    mf = paramui._material_of(rim.md, paramrim.FRONT_COLOR_NODE)
    mb.node_tree.nodes[paramrim.BODY_COLOR_NODE].outputs[0].default_value = (*body_rgb, 1.0)
    mf.node_tree.nodes[paramrim.FRONT_COLOR_NODE].outputs[0].default_value = (*front_rgb, 1.0)
    mb.diffuse_color = (*body_rgb, 1.0)
    mf.diffuse_color = (*front_rgb, 1.0)
    for mat, key in ((mb, "lack"), (mf, "blank")):
        b = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
        for name, val in (fin.get(key) or {}).items():
            if name in b.inputs:
                b.inputs[name].default_value = val
    return mb, mf


def render_to_array(sc, path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    buf = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(buf)
    arr = buf.reshape(h, w, 4)[::-1].copy()
    bpy.data.images.remove(im)
    arr[..., :3] = to_lin(arr[..., :3])
    return arr


def id_pass(sc, mb, mf, res_path):
    """Workbench, flach, ohne Kantenglättung: rot = blanke Fläche (Front-Material), blau = Grundfarbe/Lack."""
    keep = (sc.render.engine, sc.render.film_transparent)
    old = (tuple(mb.diffuse_color), tuple(mf.diffuse_color))
    mb.diffuse_color, mf.diffuse_color = (0, 0, 1, 1), (1, 0, 0, 1)
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "FLAT"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.render_aa = "OFF"
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    a = render_to_array(sc, res_path)
    sc.render.engine, sc.render.film_transparent = keep
    mb.diffuse_color, mf.diffuse_color = old
    a = np.clip(a, 0, 1)
    alpha = a[..., 3] > 0.5
    return alpha, alpha & (a[..., 0] > a[..., 2] + 0.15), alpha & (a[..., 2] > a[..., 0] + 0.15)


def show_only(cols, which):
    for c in cols:
        c.hide_render = c is not which
        c.hide_viewport = c is not which


def clay_material():
    m = bpy.data.materials.new("Meshy Ton")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.55, 0.55, 0.56, 1)
    b.inputs["Roughness"].default_value = 0.45
    return m


def import_meshy(sc, glb, R_target, lipz, piv, rim_ratio):
    """Meshy-GLB laden, auf Rad-Größe bringen (Mitte in der Bildebene, vordere Fläche auf die Felgenkante) und an die Drehung hängen."""
    from felge3d import fbx
    new, meshes = fbx.import_file(glb)
    col = bpy.data.collections.new("Meshy")
    sc.collection.children.link(col)
    for o in new:
        for oc in list(o.users_collection):
            oc.objects.unlink(o)
        col.objects.link(o)
    bpy.context.view_layer.update()
    P = np.asarray(fbx.collect_points(meshes), np.float64)
    # glTF -> Blender: Vorderseite zeigt nach -Y, oben = +Z (Meshy liefert die Ansicht des Eingabebildes)
    c = np.array([(P[:, 0].min() + P[:, 0].max()) / 2, P[:, 1].min(), (P[:, 2].min() + P[:, 2].max()) / 2])
    r_out = np.percentile(np.hypot(P[:, 0] - c[0], P[:, 2] - c[2]), 99.5)
    s = R_target / max(r_out * rim_ratio, 1e-9)
    holder = bpy.data.objects.new("Meshy Halter", None)
    col.objects.link(holder)
    holder.parent = piv
    holder.scale = (s, s, s)
    holder.location = (-c[0] * s, -lipz - c[1] * s, -c[2] * s)
    clay = clay_material()
    for o in new:
        if o.parent is None:
            o.parent = holder
        if o.type == "MESH":
            has_tex = any(m_ and m_.use_nodes and any(n_.type == "TEX_IMAGE" and n_.image for n_ in m_.node_tree.nodes) for m_ in o.data.materials)
            if not has_tex:                                  # nur Mesh: Ton-Material; mit Meshy-Textur bleibt das Meshy-Material
                o.data.materials.clear()
                o.data.materials.append(clay)
    return col, dict(r_out=float(r_out), ausdehnung_y=float(P[:, 1].max() - P[:, 1].min()), punkte=int(len(P)))


def align_meshy_mask(m0, photo, cx, cy, rx):
    """
    Silhouette des Meshy-Meshs (Rendering m0) auf das Foto legen: Maßstab und Verschiebung so, dass die Umrisse (Rand, Fenster, Nabe)
    auf Foto-Kanten liegen. Grobsuche (Gitter) + Feinsuche, bewertet nur an den Umrisspunkten (schnell).
    Gibt (Maske als bool-Array im Bildraster, dict mit Maßstab/Verschiebung/Trefferquote) zurück.
    """
    h, w = m0.shape
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - cx, yy - cy)
    sp = to_srgb(lum(photo))
    ge = dilate(edge_mask(sp, 0.08, (rr > 0.12 * rx) & (rr < 1.03 * rx)), 2)
    oy, ox = np.nonzero(outline(m0) & (rr > 0.12 * rx) & (rr < 1.15 * rx))
    if len(ox) < 50:
        return m0, dict(skala=1.0, dx=0, dy=0, treffer=0.0, treffer_vorher=0.0)

    def score(sc, dx, dy):
        x = np.round(cx + sc * (ox - cx) + dx).astype(int)
        y = np.round(cy + sc * (oy - cy) + dy).astype(int)
        ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        return float(ge[y[ok], x[ok]].mean()) if ok.any() else 0.0
    base = score(1.0, 0, 0)
    best = (base, 1.0, 0, 0)
    for sc in np.arange(0.90, 1.101, 0.02):
        for dx in range(-16, 17, 4):
            for dy in range(-16, 17, 4):
                v = score(sc, dx, dy)
                if v > best[0]:
                    best = (v, sc, dx, dy)
    v0, sc0, dx0, dy0 = best
    for sc in np.arange(sc0 - 0.02, sc0 + 0.0201, 0.005):
        for dx in range(dx0 - 4, dx0 + 5, 1):
            for dy in range(dy0 - 4, dy0 + 5, 1):
                v = score(sc, dx, dy)
                if v > best[0]:
                    best = (v, sc, dx, dy)
    v, sc, dx, dy = best
    sx = np.clip(np.round(cx + (xx - cx - dx) / sc).astype(int), 0, w - 1)
    sy = np.clip(np.round(cy + (yy - cy - dy) / sc).astype(int), 0, h - 1)
    m = m0[sy, sx]
    return m, dict(skala=float(sc), dx=int(dx), dy=int(dy), treffer=float(v), treffer_vorher=float(base))


# ------------------------------------------------------------------ Messwerte
def radial_profile(g, cx, cy, r_max, step=1.0):
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - cx, yy - cy)
    n = int(r_max / step)
    idx = np.minimum((r / step).astype(int), n)
    sums = np.bincount(idx.ravel(), g.ravel(), n + 1)[:n]
    cnt = np.maximum(np.bincount(idx.ravel(), minlength=n + 1)[:n], 1)
    return sums / cnt


def cap_radius(profile, lo, hi):
    """Kappen-/Verschlussrand: äußerster starker Helligkeitssprung (>= 60 % des stärksten) im Bereich [lo, hi] (px)."""
    d = np.abs(np.gradient(np.convolve(profile, np.ones(3) / 3, "same")))
    i0, i1 = int(lo), min(int(hi), len(d))
    seg = d[i0:i1]
    strong = np.nonzero(seg >= 0.6 * seg.max())[0]
    return float(i0 + strong.max())


def dark_cap_radius(g, cx, cy, rx):
    """Schwarzes Verschlussmodul im Foto: größter Radius (<= 0,22 R), auf dem noch > 50 % der Pixel dunkel sind (dunkel = < 25 % der Ringhelligkeit)."""
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - cx, yy - cy)
    ring = g[(r > 0.22 * rx) & (r < 0.30 * rx)]
    thr = 0.25 * float(np.median(ring)) if ring.size else 0.1
    n = int(0.22 * rx)
    dark = (g < thr)
    idx = np.minimum(r.astype(int), n)
    frac = np.bincount(idx.ravel(), dark.ravel().astype(float), n + 1)[:n] / np.maximum(np.bincount(idx.ravel(), minlength=n + 1)[:n], 1)
    ok = np.nonzero(frac > 0.5)[0]
    return float(ok.max()) if ok.size else float("nan")


def crest_stats(rgb_srgb, cx, cy, r):
    """Wappenfarben (Gold-Gelb und Rot, Farbton 0–70° bzw. 340–360°, gesättigt) im Zentrum: Anzahl, Schwerpunkt-Versatz, Ausdehnung."""
    h, w = rgb_srgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    mx, mn = rgb_srgb.max(-1), rgb_srgb.min(-1)
    d = np.maximum(mx - mn, 1e-6)
    sat = (mx - mn) / np.maximum(mx, 1e-4)
    rch, gch, bch = rgb_srgb[..., 0], rgb_srgb[..., 1], rgb_srgb[..., 2]
    hue = np.where(mx == rch, ((gch - bch) / d) % 6, np.where(mx == gch, (bch - rch) / d + 2, (rch - gch) / d + 4)) * 60.0
    warm = (hue <= 70) | (hue >= 340)
    m = (np.hypot(xx - cx, yy - cy) < r) & (sat > 0.45) & (mx > 0.25) & warm
    if m.sum() < 5:
        return dict(n=int(m.sum()), cx=None, cy=None, ausdehnung=None)
    return dict(n=int(m.sum()), cx=float(xx[m].mean() - cx), cy=float(yy[m].mean() - cy),
                ausdehnung=float(max(np.percentile(xx[m], 95) - np.percentile(xx[m], 5), np.percentile(yy[m], 95) - np.percentile(yy[m], 5))))


def measure(photo, rend_srgb, rend_lin, alpha, red, blue, cx, cy, rx, N_model, N_exp, mm_per_px):
    h, w = photo.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - cx, yy - cy)
    sp, sr = to_srgb(lum(photo)), to_srgb(lum(rend_lin))
    out = {}
    # --- Kanten: Präzision (Nachbau-Umriss liegt auf Foto-Kante) und Recall (Foto-Kanten im Rad werden vom Nachbau getroffen)
    band = (rr > 0.12 * rx) & (rr < 0.985 * rx)
    ge = edge_mask(sp, 0.06, band)
    ren_e = (outline(alpha) | outline(red) | outline(blue)) & band
    ol = outline(alpha) & band
    prec = float((ol & dilate(ge, 3)).sum() / max(ol.sum(), 1))
    rec = float((ge & dilate(ren_e, 3)).sum() / max(ge.sum(), 1))
    out["genauigkeit"] = dict(praezision=prec, recall=rec, f1=2 * prec * rec / max(prec + rec, 1e-9), speichen_modell=N_model, speichen_soll=N_exp)
    # --- Farben (Rendering-Material, 2 px vom Rand entfernt)
    core = erode(alpha, 2) & (rr > 0.20 * rx) & (rr < 0.95 * rx)
    cols = {}
    for nm, zone in (("blank", red), ("lack", blue)):
        z = core & erode(zone, 1)
        if z.sum() > 200:
            cp, cr = np.median(photo[z], 0), np.median(rend_lin[z][:, :3], 0)
            cols[nm] = dict(de=delta_e(cp, cr), foto=[float(v) for v in to_srgb(cp)], modell=[float(v) for v in to_srgb(cr)],
                            hell95_foto=float(np.quantile(sp[z], 0.95)), hell95_modell=float(np.quantile(sr[z], 0.95)),
                            anteil=float(z.sum() / max(core.sum(), 1)))
    out["speichenfarbe"] = cols
    # --- Zentrum / Verschluss
    pp, pr = radial_profile(sp, cx, cy, 0.30 * rx), radial_profile(sr, cx, cy, 0.30 * rx)
    k = min(len(pp), len(pr))
    corr = float(np.corrcoef(pp[:k], pr[:k])[0, 1]) if k > 4 else 0.0
    rcp, rcr = dark_cap_radius(sp, cx, cy, rx), cap_radius(pr, 0.06 * rx, 0.22 * rx)
    if not (rcp == rcp):                                     # nan: keine dunkle Kappe gefunden -> Gradientenverfahren
        rcp = cap_radius(pp, 0.06 * rx, 0.22 * rx)
    out["zentrum"] = dict(profil_korrelation=corr, kappe_foto_mm=rcp * mm_per_px, kappe_modell_mm=rcr * mm_per_px, verhaeltnis=rcr / max(rcp, 1e-6))
    out["wappen"] = dict(foto=crest_stats(to_srgb(photo), cx, cy, 0.8 * rcp), modell=crest_stats(rend_srgb, cx, cy, 0.8 * rcp))
    return out


def fmt_auto(m):
    g, c, z, wp = m["genauigkeit"], m["speichenfarbe"], m["zentrum"], m["wappen"]
    a = {}
    a["genauigkeit"] = "Kanten ±3 px: Präzision %.0f %%, Recall %.0f %% (F1 %.0f %%) · Speichen %s (Soll %s)" % (
        100 * g["praezision"], 100 * g["recall"], 100 * g["f1"], g["speichen_modell"], g["speichen_soll"])
    a["speichenform"] = "Recall der Foto-Kanten im Rad: %.0f %% (Anteil der Speichen-/Fensterkanten, die der Nachbau trifft)" % (100 * g["recall"])
    parts = []
    for nm in ("blank", "lack"):
        if nm in c:
            parts.append("%s ΔE %.0f (Glanzlicht 95 %%: Foto %.2f / Modell %.2f, Flächenanteil %.0f %%)" % (
                nm, c[nm]["de"], c[nm]["hell95_foto"], c[nm]["hell95_modell"], 100 * c[nm]["anteil"]))
    a["speichenfarbe"] = " · ".join(parts) or "–"
    a["zentrum"] = "Profil-Korrelation %.2f (Helligkeit über dem Radius, r < 0,3 R)" % z["profil_korrelation"]
    a["verschluss"] = "Kappen-/Verschlussradius (grober Hilfswert, ±30 %%) Foto %.0f mm, Modell %.0f mm (×%.2f)" % (z["kappe_foto_mm"], z["kappe_modell_mm"], z["verhaeltnis"])
    f, mo = wp["foto"], wp["modell"]
    a["wappen"] = "Wappenfarben Foto: %d Pixel (Ø %s px) · Modell: %d Pixel%s" % (
        f["n"], "–" if f["ausdehnung"] is None else "%.0f" % f["ausdehnung"], mo["n"], " (kein Wappen im Modell)" if mo["n"] < 0.2 * max(f["n"], 1) else "")
    return a


# ------------------------------------------------------------------ Hauptablauf
def run(key, cfg):
    t0 = time.time()
    photo_path = os.path.normpath(os.path.join(HERE, cfg["foto"]))
    install_addon()
    import felge3d
    from felge3d import core, paramui, paramrim
    sc = bpy.context.scene
    s = sc.felge3d
    s.result_mode = "EDIT"
    os.makedirs(OUT, exist_ok=True)
    if cfg.get("zuschnitt"):
        src = load_photo(photo_path)
        H0, W0 = src.shape[:2]
        x0, y0, x1, y1 = cfg["zuschnitt"]
        photo_path = os.path.join(OUT, key + "_zuschnitt.png")
        save_png(to_srgb(src[int(y0 * H0):int(y1 * H0), int(x0 * W0):int(x1 * W0)]), photo_path)
    sch = cfg.get("schraeg")
    build_path = photo_path
    if sch:
        full = load_photo(photo_path)
        ecx, ecy, ea, eb = sch["ellipse"]
        half = int(1.15 * eb)
        build_path = os.path.join(OUT, key + "_entzerrt.png")
        save_png(to_srgb(dewarp(full, ecx, ecy, ea / eb, half)), build_path)
        cfg = dict(cfg, kreis=[0.5, 0.5, eb / (2.0 * half)])
    if cfg.get("symmetrie"):                                  # Symmetrieordnung von Hand (z. B. 5 bei Y-Speichen mit zwei Fenstersorten)
        s.sym_mode, s.sym_n = "MANUAL", int(cfg["symmetrie"])
    if cfg.get("kreis"):
        s.auto_detect = False
        s.center_x, s.center_y, s.radius, s.aspect = cfg["kreis"][0], cfg["kreis"][1], cfg["kreis"][2], 1.0
    bpy.ops.felge3d.import_image(filepath=build_path)
    col_subd = s.collection
    det = json.loads(col_subd.get("felge3d_detect", "{}"))
    info = col_subd.get("felge3d_detect_info", "")
    log("Bau SubD", key, "%.1f s" % (time.time() - t0), "|", info)

    photo_full = load_photo(photo_path)
    H0, W0 = photo_full.shape[:2]
    k = min(1.0, MAXPX / max(H0, W0))
    h, w = int(round(H0 * k)), int(round(W0 * k))
    photo = resample(photo_full, h, w)
    cx, cy, rx = s.center_x * w, s.center_y * h, s.radius * w
    asp = 1.0
    if sch:
        cx, cy, rx, asp = sch["ellipse"][0] * k, sch["ellipse"][1] * k, sch["ellipse"][3] * k, sch["ellipse"][2] / sch["ellipse"][3]
    R, Wd, flange, wall, R_out, r_face, dish = core.dimensions(felge3d.make_params(s))
    mm_per_px = R_out * 1000.0 / rx

    setup_world(sc)
    lipz = lip_z(col_subd)
    piv = bpy.data.objects.new("Foto-Drehung", None)
    sc.collection.objects.link(piv)
    piv.rotation_euler = (math.radians(sch.get("pitch_deg", 0.0)) if sch else 0.0, 0.0, math.radians(sch["yaw_deg"]) if sch else 0.0)
    root_subd = next(o for o in col_subd.objects if o.get("felge3d_role") == "root")
    root_subd.parent = piv
    bpy.context.view_layer.update()
    anchor = root_subd.matrix_world @ Vector((0.0, 0.0, lipz))
    cam, dist = make_camera(sc, cfg, w, h, cx, cy, rx, R_out, anchor)
    log("Kreis: Mitte (%.0f, %.0f) px, Radius %.0f px · R_out %.1f mm · Kante z=%.1f mm · Abstand %.2f m" % (cx, cy, rx, R_out * 1000, lipz * 1000, dist))
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_adaptive_sampling = True
    try:
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:  # noqa: BLE001
        pass
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.exposure = float(cfg.get("belichtung", 0.0))

    rim = paramui.Rim(col_subd)
    mb = paramui._material_of(rim.md, paramrim.BODY_COLOR_NODE)
    mf = paramui._material_of(rim.md, paramrim.FRONT_COLOR_NODE)
    alpha, red, blue = id_pass(sc, mb, mf, os.path.join(OUT, key + "_id.png"))
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot((xx - cx) / asp, yy - cy)
    core_ = erode(alpha, 3) & (rr > 0.2 * rx) & (rr < 0.95 * rx)

    def med(zone):
        z = core_ & erode(zone, 2)
        return np.median(photo[z], 0) if z.sum() > 200 else None
    bc, fc = med(blue), med(red)
    body_rgb = tuple(float(v) for v in (bc if bc is not None else (0.012, 0.012, 0.014)))
    front_rgb = tuple(float(v) for v in (fc if fc is not None else (0.8, 0.81, 0.83)))
    set_zone_colors(rim, body_rgb, front_rgb, cfg.get("oberflaeche", {}))

    # --- Spalte 3: SubD lokal
    all_cols = [col_subd]
    t1 = time.time()
    arr = render_to_array(sc, os.path.join(OUT, key + "_render.png"))
    a = np.clip(arr[..., 3:4], 0, 1)
    subd_lin = arr[..., :3] * a
    subd_srgb = to_srgb(subd_lin)
    log("Render SubD %.0f s" % (time.time() - t1))

    # --- Spalte 2: Mesh lokal (KI-Mesh mit Foto-Textur)
    ki_srgb = np.zeros((h, w, 3), np.float32)
    try:
        s.result_mode, s.use_param = "KI", False
        col_ki, _ = felge3d.build_wheel(bpy.context, s, new_collection=True)
        root_ki = next(o for o in col_ki.objects if o.get("felge3d_role") == "root")
        root_ki.parent = piv
        all_cols.append(col_ki)
        show_only(all_cols, col_ki)
        bpy.context.view_layer.update()
        arr = render_to_array(sc, os.path.join(OUT, key + "_render_ki.png"))
        ki_srgb = to_srgb(arr[..., :3] * np.clip(arr[..., 3:4], 0, 1))
        log("Render KI-Mesh lokal ok")
    except Exception as e:  # noqa: BLE001
        log("KI-Mesh lokal fehlgeschlagen:", e)
    finally:
        s.result_mode, s.use_param = "EDIT", True

    # --- Spalte 4: Meshy
    mz_srgb = np.zeros((h, w, 3), np.float32)
    mz_alpha = None
    meshy_info = None
    glb = os.path.join(HERE, "out", "meshy", cfg.get("meshy_aus", key) + ".glb")      # gleiche Felge = EIN Meshy-Mesh (Gruppe)
    if os.path.isfile(glb):
        try:
            col_mz, meshy_info = import_meshy(sc, glb, R_out, lipz, piv, float(cfg.get("meshy_felge_zu_modell", 1.0)))
            all_cols.append(col_mz)
            show_only(all_cols, col_mz)
            bpy.context.view_layer.update()
            arr = render_to_array(sc, os.path.join(OUT, key + "_render_meshy.png"))
            mz_alpha = np.clip(arr[..., 3], 0, 1)
            mz_srgb = to_srgb(arr[..., :3] * np.clip(arr[..., 3:4], 0, 1))
            log("Render Meshy ok", meshy_info)
        except Exception as e:  # noqa: BLE001
            log("Meshy-Render fehlgeschlagen:", e)
    else:
        log("kein Meshy-Mesh vorhanden:", glb)

    # --- Spalte 5 (A1): SubD mit der an das Foto angelegten Meshy-Silhouette als Maske (nur Frontalfotos)
    mm_srgb = np.zeros((h, w, 3), np.float32)
    mm_m = None
    mm_fit = None
    if cfg.get("maske_aus_meshy") and mz_alpha is not None and not sch:
        try:
            mask_b, mm_fit = align_meshy_mask(mz_alpha > 0.5, photo, cx, cy, rx)
            log("Meshy-Maske angelegt:", mm_fit)
            mpath = os.path.join(OUT, key + "_meshy_maske.png")
            save_png(np.repeat(mask_b[..., None].astype(np.float32), 3, axis=2), mpath)
            s.mask_image = bpy.data.images.load(mpath, check_existing=True)
            s.result_mode, s.use_param = "EDIT", True
            col_mm, _ = felge3d.build_wheel(bpy.context, s, new_collection=True)
            info_mm = col_mm.get("felge3d_detect_info", "")
            log("Bau SubD mit Meshy-Maske:", info_mm)
            root_mm = next(o for o in col_mm.objects if o.get("felge3d_role") == "root")
            root_mm.parent = piv
            all_cols.append(col_mm)
            rim_mm = paramui.Rim(col_mm)
            mb2, mf2 = set_zone_colors(rim_mm, body_rgb, front_rgb, cfg.get("oberflaeche", {}))
            show_only(all_cols, col_mm)
            bpy.context.view_layer.update()
            alpha2, red2, blue2 = id_pass(sc, mb2, mf2, os.path.join(OUT, key + "_id_mm.png"))
            arr = render_to_array(sc, os.path.join(OUT, key + "_render_mm.png"))
            mm_lin = arr[..., :3] * np.clip(arr[..., 3:4], 0, 1)
            mm_srgb = to_srgb(mm_lin)
            det_mm = json.loads(col_mm.get("felge3d_detect", "{}"))
            mm_m = measure(photo, mm_srgb, mm_lin, alpha2, red2, blue2, cx, cy, rx, det_mm.get("n"), cfg.get("speichen"), mm_per_px)
            mm_fit["info"] = info_mm
        except Exception as e:  # noqa: BLE001
            log("SubD mit Meshy-Maske fehlgeschlagen:", e)
        finally:
            s.mask_image = None

    if sch:                                                   # Schrägbild: Messwerte nicht belastbar (Tiefe, Perspektive) -> n/a, nur Sichtprüfung
        m = {}
        auto = {k_["id"]: "n/a (Schrägbild: Messung nicht belastbar, bitte am Bild bewerten)" for k_ in json.load(open(os.path.join(HERE, "kriterien.json")))["kriterien"]}
        auto["genauigkeit"] += " · Speichen im Modell: %s (Soll %s)" % (det.get("n"), cfg.get("speichen"))
    else:
        m = measure(photo, subd_srgb, subd_lin, alpha, red, blue, cx, cy, rx, det.get("n"), cfg.get("speichen"), mm_per_px)
        auto = fmt_auto(m)

    # --- Blatt
    ps = to_srgb(photo)
    blend = 0.5 * ps + 0.5 * subd_srgb
    inside = (rr < 1.03 * rx)
    ge = edge_mask(to_srgb(lum(photo)), 0.06, inside & (rr > 0.12 * rx))
    edges = np.zeros((h, w, 3), np.float32)
    edges[ge] = (1.0, 0.25, 0.25)
    ol_ = dilate(outline(alpha) | outline(red) | outline(blue), 1)
    edges[ol_] = (0.0, 1.0, 1.0)
    edges[ol_ & dilate(ge, 1)] = (1.0, 1.0, 0.2)
    rad = int(0.26 * rx)
    x0, x1, y0, y1 = int(cx) - rad, int(cx) + rad, int(cy) - rad, int(cy) + rad

    def zoom(img):
        hh_, ww_ = img.shape[:2]
        c = img[max(y0, 0):min(y1, hh_), max(x0, 0):min(x1, ww_)]
        return resample(c, h // 2, h // 2) if c.shape[0] and c.shape[1] else np.zeros((h // 2, h // 2, 3), np.float32)
    if sch:
        hf_ = int(1.15 * rx)
        x0, x1, y0, y1 = hf_ - rad, hf_ + rad, hf_ - rad, hf_ + rad
        hub = np.concatenate([zoom(dewarp(ps, cx, cy, asp, hf_)), zoom(dewarp(subd_srgb, cx, cy, asp, hf_))], axis=0)
        hf_h, hf_w = 2 * hf_, 2 * hf_
        h_, w_ = h, w
    else:
        hub = np.concatenate([zoom(ps), zoom(subd_srgb)], axis=0)
    hub = resample(hub, h, int(hub.shape[1] * h / hub.shape[0]))
    row1 = np.concatenate([ps, ki_srgb, subd_srgb, mz_srgb] + ([mm_srgb] if mm_m is not None else []), axis=1)
    row2 = np.concatenate([blend, edges, hub], axis=1)
    W = max(row1.shape[1], row2.shape[1])
    pad = lambda r_: np.pad(r_, ((0, 0), (0, W - r_.shape[1]), (0, 0)))   # noqa: E731
    sheet = np.concatenate([pad(row1), pad(row2)], axis=0)
    png = os.path.join(OUT, key + "_vergleich.png")
    save_png(sheet, png)
    log("Blatt:", png, sheet.shape)

    label = os.environ.get("LABEL") or "%d.%d.%d" % tuple(felge3d.bl_info["version"])
    bj = os.path.join(HERE, "bewertung.json")
    rows = json.load(open(bj, encoding="utf-8")) if os.path.isfile(bj) else {}
    ek = "%s [%s]" % (key, label)
    krit = json.load(open(os.path.join(HERE, "kriterien.json")))["kriterien"]
    old = rows.get(ek, {}).get("bewertung") if os.environ.get("KEEP_RATINGS") == "1" else None
    rows[ek] = dict(version=label, bild=os.path.relpath(png, HERE).replace(os.sep, "/"), info=info, auto=auto,
                    messung=json.loads(json.dumps(m, default=float)), meshy=meshy_info,
                    meshy_maske=dict(fit=mm_fit, messung=json.loads(json.dumps(mm_m, default=float)) if mm_m else None,
                                     auto=fmt_auto(mm_m) if mm_m else None),
                    bewertung=old or {k_["id"]: dict(reviewer=None, nutzer=None, kommentar="") for k_ in krit},
                    kamera=dict(brennweite_mm=cfg.get("brennweite_mm", 135.0), abstand_m=dist, kreis_px=[cx, cy, rx], bild_px=[w, h],
                                yaw_deg=sch["yaw_deg"] if sch else 0.0))
    json.dump(rows, open(bj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k_, v_ in auto.items():
        log("  %-14s %s" % (k_, v_))
    log("fertig %s in %.0f s" % (key, time.time() - t0))


if __name__ == "__main__":
    fotos = json.load(open(os.path.join(HERE, "fotos.json"), encoding="utf-8"))
    for kk in (sys.argv[1:] or list(fotos)):
        run(kk, fotos[kk])
