# SPDX-License-Identifier: GPL-3.0-or-later
"""
3D-Felge (FBX o.ä.) -> Rim Generator: Achse, Vorderseite, Durchmesser und Breite automatisch erkennen und die
Felge so in Radkoordinaten bringen (Achse = X nach außen, Z oben, Mitte im Ursprung), wie die Foto-Felge.
"""
import numpy as np

import bpy
from mathutils import Matrix


def import_file(filepath):
    """FBX importieren; gibt die neuen Mesh-Objekte zurück. Wirft RuntimeError mit klarer Meldung."""
    import addon_utils
    low = filepath.lower()
    before = set(bpy.data.objects)
    try:
        if low.endswith(".fbx"):
            try:
                addon_utils.enable("io_scene_fbx", default_set=False)
            except Exception:  # noqa: BLE001
                pass
            bpy.ops.import_scene.fbx(filepath=filepath)
        elif low.endswith(".obj"):
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=filepath)
            else:
                bpy.ops.import_scene.obj(filepath=filepath)
        elif low.endswith((".glb", ".gltf")):
            bpy.ops.import_scene.gltf(filepath=filepath)
        else:
            raise RuntimeError("Dateityp nicht unterstützt (FBX, OBJ oder glTF).")
    except AttributeError as e:
        raise RuntimeError("Import-Add-on für diese Datei ist nicht aktiviert: %s" % e)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH" and len(o.data.vertices) > 0]
    if not meshes:
        raise RuntimeError("In der Datei wurde kein Mesh gefunden.")
    return new, meshes


def collect_points(objs, max_pts=300000):
    pts = []
    for o in objs:
        me = o.data
        n = len(me.vertices)
        co = np.empty(n * 3, np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        M = np.array(o.matrix_world)
        pts.append(co @ M[:3, :3].T + M[:3, 3])
    P = np.concatenate(pts)
    if len(P) > max_pts:
        P = P[np.random.default_rng(1).choice(len(P), max_pts, replace=False)]
    return P


def analyze(objs, flip=False):
    """
    Findet Achse (kleinste Streuung), Mitte, Außenrichtung (Felgenhorn liegt bei konkaven Felgen vor der Nabe),
    Radius und Breite. Gibt dict mit R (3x3 Welt -> Rad), center, r_max, t_lip, width, ... zurück.
    """
    P = collect_points(objs)
    c0 = P.mean(axis=0)
    cov = np.cov((P - c0).T)
    w, V = np.linalg.eigh(cov)
    axis = V[:, 0]                                    # kleinste Streuung = Felgenachse
    # Hochachse: Welt-Z senkrecht zur Achse (oder X, falls die Achse fast vertikal ist)
    up = np.array([0.0, 0.0, 1.0])
    if abs(axis @ up) > 0.95:
        up = np.array([1.0, 0.0, 0.0])
    u = up - (up @ axis) * axis
    u /= np.linalg.norm(u)
    # Mitte in der Ebene
    a = (P - c0) @ u
    b = (P - c0) @ np.cross(u, axis)
    c = c0 + u * (a.min() + a.max()) / 2.0 + np.cross(u, axis) * (b.min() + b.max()) / 2.0
    Q = P - c
    t = Q @ axis
    ay, az = Q @ np.cross(u, axis), Q @ u
    r = np.hypot(ay, az)
    r_max = float(np.percentile(r, 99.95))
    lip = r > 0.9 * r_max
    hub = r < 0.25 * r_max
    lip_t = float(t[lip].mean()) if lip.any() else float(t.max())
    hub_t = float(t[hub].mean()) if hub.any() else float(t.mean())
    sign = 1.0 if lip_t >= hub_t else -1.0            # Außenrichtung: Horn liegt vor der Nabe
    if flip:
        sign = -sign
    axis = axis * sign
    t = t * sign
    # Rad-Koordinatensystem: X = Achse, Z = oben (u), Y = u × Achse
    Y = np.cross(u, axis)
    R = np.array([axis, Y, u])                        # Zeilen: x', y', z'
    t_lip = float(np.percentile(t[lip], 98)) if lip.any() else float(t.max())
    width = float(t_lip - np.percentile(t, 0.05))
    return dict(R=R, center=c, r_max=r_max, t_lip=t_lip, width=width, axis=axis, sign=sign,
                dish=float(lip_t - hub_t) * sign, n_points=len(P))


def fit_matrix(info, r_target, x_lip):
    """4x4: Welt -> Radkoordinaten (Felgenhorn bei x = x_lip, größter Radius = r_target)."""
    s = r_target / info["r_max"]
    R = info["R"] * s
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = -R @ info["center"] + np.array([x_lip - s * info["t_lip"], 0.0, 0.0])
    return M, s


def bake(meshes, M_fit, name):
    """Mesh-Kopien in Radkoordinaten (Objekt- und Anpassungs-Matrix eingebacken). Gibt Liste (label, mesh) zurück."""
    out = []
    for i, o in enumerate(meshes):
        me = o.data.copy()
        M = Matrix(M_fit.tolist()) @ o.matrix_world
        me.transform(M)
        if M.determinant() < 0:
            me.flip_normals()
        me.name = "%s %d" % (name, i)
        me.update()
        out.append((o.name, me))
    return out


def back_profile(parts, x_lip, width_s, bin_mm=3.0):
    """
    Rückseite der Speichen/Nabe: kleinste axiale Lage x je Radius (nur vordere ~55 % der Breite, damit das
    hintere Felgenbett nicht mitzählt). Gibt f(r) -> x zurück.
    """
    xs, rs = [], []
    for _, me in parts:
        n = len(me.vertices)
        co = np.empty(n * 3, np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        xs.append(co[:, 0])
        rs.append(np.hypot(co[:, 1], co[:, 2]))
    x, r = np.concatenate(xs), np.concatenate(rs)
    keep = x >= x_lip - 0.55 * width_s
    x, r = x[keep], r[keep]
    bins = np.arange(0.0, r.max() + 0.003, bin_mm / 1000.0)
    idx = np.digitize(r, bins)
    rr, xx = [], []
    for i in np.unique(idx):
        m = idx == i
        rr.append(r[m].mean())
        xx.append(x[m].min())
    o = np.argsort(rr)
    rr, xx = np.array(rr)[o], np.array(xx)[o]

    def f(radius):
        return float(np.interp(radius, rr, xx))
    return f
