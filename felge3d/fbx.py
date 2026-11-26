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
    """Punkte gleichmäßig auf der Oberfläche (flächengewichtet, unabhängig von der Netzdichte)."""
    rng = np.random.default_rng(1)
    parts, areas = [], []
    for o in objs:
        me = o.data
        M = np.array(o.matrix_world)
        n = len(me.vertices)
        co = np.empty(n * 3, np.float64)
        me.vertices.foreach_get("co", co)
        co = (co.reshape(-1, 3)) @ M[:3, :3].T + M[:3, 3]
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        if nt == 0:
            parts.append((co, None))
            areas.append(0.0)
            continue
        tri = np.empty(nt * 3, np.int32)
        me.loop_triangles.foreach_get("vertices", tri)
        tri = tri.reshape(-1, 3)
        a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
        ar = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
        parts.append((co, (tri, ar)))
        areas.append(float(ar.sum()))
    total = sum(areas)
    pts = []
    for (co, t), A in zip(parts, areas):
        if t is None or total <= 0 or A <= 0:
            pts.append(co[:: max(1, len(co) // 2000)])
            continue
        tri, ar = t
        k = max(100, int(max_pts * A / total))
        sel = rng.choice(len(tri), k, p=ar / ar.sum())
        u, v = rng.random(k), rng.random(k)
        f = u + v > 1.0
        u[f], v[f] = 1.0 - u[f], 1.0 - v[f]
        T = tri[sel]
        pts.append(co[T[:, 0]] + (co[T[:, 1]] - co[T[:, 0]]) * u[:, None] + (co[T[:, 2]] - co[T[:, 0]]) * v[:, None])
    return np.concatenate(pts)


def _pick_axis(P):
    """
    Achse der Felge: die Hauptachse, deren Querschnitt rund ist (die beiden anderen Streuungen sind fast gleich).
    Das gilt unabhängig davon, ob die Felge schmal oder sehr breit ist; bei Gleichstand gewinnt die kleinste Streuung.
    """
    c0 = P.mean(axis=0)
    w, V = np.linalg.eigh(np.cov((P - c0).T))
    best, best_score = 0, None
    for i in range(3):
        j, k = [m for m in range(3) if m != i]
        iso = abs(w[j] - w[k]) / max(w[j] + w[k], 1e-12)       # 0 = rund
        score = iso + 0.02 * (w[i] / max(w.max(), 1e-12))       # kleine Streuung bevorzugen
        if best_score is None or score < best_score:
            best, best_score = i, score
    return V[:, best], c0, float(best_score)


def analyze(objs, flip=False):
    """
    Findet Achse (runder Querschnitt), Mitte, Außenrichtung, Radius und Breite. Gibt dict mit R (3x3 Welt -> Rad),
    center, r_max, t_lip, width, ... zurück.
    Außenrichtung: Die Nabe (Mitte der Felge) liegt bei positiver Einpresstiefe auf der Außenseite der Bettmitte;
    also zeigt die Außenrichtung von der Mitte des Felgenbetts (zwischen den beiden Hörnern) zur Nabe.
    """
    P = collect_points(objs)
    axis, c0, roundness = _pick_axis(P)
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
    if hub.sum() < 50:
        hub = r < 0.4 * r_max
    if lip.any():
        bed_c = 0.5 * (float(np.percentile(t[lip], 1)) + float(np.percentile(t[lip], 99)))   # Mitte des Betts
    else:
        bed_c = 0.5 * float(t.min() + t.max())
    hub_t = float(t[hub].mean()) if hub.any() else float(t.mean())
    sign = 1.0 if hub_t >= bed_c else -1.0            # Nabe sitzt bei ET > 0 außen von der Bettmitte
    width_est = float(np.percentile(t, 99.95) - np.percentile(t, 0.05))
    conf = abs(hub_t - bed_c) / max(width_est, 1e-9)  # klein = Einpresstiefe nahe 0: Richtung unsicher
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
                dish=float(hub_t - bed_c) * sign, n_points=len(P), roundness=roundness, confidence=conf)


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


# ---------------------------------------------------------------- eigener Reifen
def tire_fit(objs, flip=False):
    """
    Achse, Mitte, Innen-/Außenradius und Breite eines Reifen-Meshs. Rückgabe: dict(R, center, t_mid, width, r_out, r_in).
    R = 3x3 (Welt -> Rad, Zeilen: Achse, Y, oben), t_mid = Mitte der Lauffläche entlang der Achse.
    """
    info = analyze(objs, flip)
    P = collect_points(objs)
    Q = (P - info["center"]) @ info["R"].T
    t = Q[:, 0]
    rho = np.hypot(Q[:, 1], Q[:, 2])
    lo, hi = float(np.percentile(t, 0.05)), float(np.percentile(t, 99.95))
    return dict(R=info["R"], center=info["center"], t_mid=0.5 * (lo + hi), width=hi - lo,
                r_out=float(np.percentile(rho, 99.95)), r_in=float(np.percentile(rho, 0.05)), n_points=int(len(P)))


def bake_tire(objs, tf, r_rim, R_out, width, sgn, name, rot_deg=0.0):
    """
    Reifen in Radkoordinaten backen und an die Zielgröße anpassen: der Radius wird linear zwischen Wulstsitz (r_in -> r_rim, Felgenradius)
    und Lauffläche (r_out -> R_out) abgebildet, die Breite auf `width`. sgn = -1: Rad um die Hochachse gedreht (Außenseite nach -X).
    Gibt Liste (label, mesh) zurück.
    """
    T = np.eye(4)
    T[:3, :3] = tf["R"]
    T[:3, 3] = -tf["R"] @ tf["center"] - np.array([tf["t_mid"], 0.0, 0.0])
    k = (R_out - r_rim) / max(tf["r_out"] - tf["r_in"], 1e-9)
    sx = width / max(tf["width"], 1e-9)
    th = np.radians(rot_deg)
    c_, s_ = np.cos(th), np.sin(th)
    out = []
    for i, o in enumerate(objs):
        me = o.data.copy()
        M = Matrix(T.tolist()) @ o.matrix_world
        me.transform(M)
        if M.determinant() < 0:
            me.flip_normals()
        n = len(me.vertices)
        co = np.empty(n * 3, np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        x, y, z = co[:, 0].copy(), co[:, 1].copy(), co[:, 2].copy()
        rho = np.hypot(y, z)
        new = r_rim + (rho - tf["r_in"]) * k
        f = np.where(rho > 1e-9, new / np.maximum(rho, 1e-9), 1.0)
        y, z = y * f, z * f
        y, z = y * c_ - z * s_, y * s_ + z * c_
        x = x * sx
        if sgn < 0:
            x, y = -x, -y
        co = np.stack([x, y, z], axis=1)
        me.vertices.foreach_set("co", co.ravel())
        me.name = "%s %d" % (name, i)
        me.update()
        out.append((o.name, me))
    return out
