# SPDX-License-Identifier: GPL-3.0-or-later
"""
Rechenkern von Felge3D – nur numpy, kein bpy. Damit auch ohne Blender testbar.

Koordinaten: Bilder liegen wie in Blender vor (Zeile 0 = unten, y nach oben).
Winkel theta = 0 zeigt nach oben (+y), läuft im Uhrzeigersinn.
Geometrie in Metern, Radachse = Z, Felgenfront zeigt nach +Z.
"""
import math
import numpy as np

INCH = 0.0254


# ============================================================ Bildverarbeitung
def rgba_to_gray(rgba):
    return (rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114).astype(np.float32)


def downscale(a, max_size):
    """Blockmittel-Verkleinerung, bis die längere Seite <= max_size ist."""
    h, w = a.shape
    f = max(1, int(math.ceil(max(h, w) / float(max_size))))
    if f == 1:
        return a.astype(np.float32)
    h2, w2 = h // f, w // f
    return a[:h2 * f, :w2 * f].reshape(h2, f, w2, f).mean(axis=(1, 3)).astype(np.float32)


def _box1d(a, r, axis):
    if r < 1:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def blur(a, r, passes=2):
    out = a.astype(np.float32)
    for _ in range(passes):
        out = _box1d(_box1d(out, r, 0), r, 1)
    return out


def otsu(values, bins=256):
    hist, edges = np.histogram(values, bins=bins, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centers)
    mu0 = m0 / np.maximum(w0, 1)
    mu1 = (m0[-1] - m0) / np.maximum(w1, 1)
    between = w0 * w1 * (mu0 - mu1) ** 2
    return float(centers[int(np.argmax(between))])


def norm_radius(shape, cx, cy, rx, ry):
    """Normierter Radius jedes Pixels (1 = Felgenhorn außen). Ellipse erlaubt leichte Perspektive."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)


def segment(gray, cx, cy, rx, ry, mode="AUTO", auto_threshold=True,
            thr=0.5, thr_hi=0.7, invert=False, clean=2):
    """
    Liefert (maske 0/1 float32, benutzter Schwellwert).
    mode: AUTO   – Otsu, Material = Klasse, die am Felgenrand dominiert
          BRIGHT – hell = Material
          DARK   – dunkel = Material
          BAND   – Grauwerte zwischen thr und thr_hi sind Lücke (z.B. grauer Hintergrund
                   hinter schwarz/silbernen Speichen)
    """
    rn = norm_radius(gray.shape, cx, cy, rx, ry)
    inside = rn < 1.0
    g = blur(gray, 1, passes=1)
    if auto_threshold and mode != "BAND":
        thr = otsu(g[inside]) if inside.any() else 0.5

    if mode == "BAND":
        mat = (g < thr) | (g > thr_hi)
    else:
        bright = g > thr
        if mode == "BRIGHT":
            mat = bright
        elif mode == "DARK":
            mat = ~bright
        else:
            ring = (rn > 0.94) & (rn < 0.99)   # Felgenhorn = immer Material
            mat = bright if (bright[ring].mean() if ring.any() else 1) > 0.5 else ~bright
    if invert:
        mat = ~mat
    m = (mat & inside).astype(np.float32)
    if clean > 0:
        # Öffnen (Störpunkte weg) und Schließen (kleine Löcher zu) über Box-Filter
        m = (blur((blur(m, clean, 1) > 0.999).astype(np.float32), clean, 1) > 0.001).astype(np.float32)
        m = (blur((blur(m, clean, 1) > 0.001).astype(np.float32), clean, 1) > 0.999).astype(np.float32)
        m *= inside
    return m, float(thr)


def downscale_rgb(rgb, max_size):
    h, w = rgb.shape[:2]
    f = max(1, int(math.ceil(max(h, w) / float(max_size))))
    if f == 1:
        return rgb[..., :3].astype(np.float32)
    h2, w2 = h // f, w // f
    return rgb[:h2 * f, :w2 * f, :3].reshape(h2, f, w2, f, 3).mean(axis=(1, 3)).astype(np.float32)


def _sample_rgb(rgb, X, Y):
    return np.stack([bilinear(rgb[..., c], X, Y) for c in range(3)], -1)


def segment_auto(rgb, cx, cy, rx, ry, n, clean=2):
    """
    Automatische Erkennung ohne Einstellungen. Zwei Kandidaten:
      A) Helligkeit (Otsu; Material = was am Felgenhorn dominiert)
      B) Abstand zum Hintergrund: jedes Pixel wird mit dem Hintergrund direkt AUSSERHALB
         der Felge in derselben Richtung verglichen. Ähnlich = Lücke (man sieht durch).
         Funktioniert auch bei zweifarbigen Felgen (schwarz + silber).
    Gewählt wird der Kandidat, bei dem Material sich stärker vom Hintergrund unterscheidet
    und über die N Speichen gleich aussieht (Konsistenz).
    """
    g = rgba_to_gray(rgb)
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = (xx - cx) / rx, (yy - cy) / ry
    rn = np.hypot(u, v)
    th = np.arctan2(u, v)
    inside = rn < 1.0

    # Hintergrund je Richtung (Median über einen Ring außerhalb der Felge)
    nb = 720
    ang = np.linspace(-np.pi, np.pi, nb, endpoint=False)
    ref = np.median(np.stack([_sample_rgb(rgb, cx + rr * rx * np.sin(ang), cy + rr * ry * np.cos(ang))
                              for rr in np.linspace(1.06, 1.25, 12)]), axis=0)
    ref = np.stack([blur(np.tile(ref[:, c], 3)[None, :], 3, 2)[0, nb:2 * nb] for c in range(3)], -1)
    idx = ((th + np.pi) / (2 * np.pi) * nb).astype(np.int64) % nb
    bgd = np.abs(rgb - ref[idx]).sum(-1)

    # Konsistenz über die N Speichen
    if n > 1:
        S = np.stack([_sample_rgb(rgb, cx + rn * rx * np.sin(th + 2 * np.pi * k / n),
                                  cy + rn * ry * np.cos(th + 2 * np.pi * k / n)) for k in range(n)])
        med = np.median(S, axis=0)
        mad = np.median(np.abs(S - med).sum(-1), axis=0)
    else:
        mad = np.zeros_like(g)

    gg = blur(g, 1, 1)
    thr = otsu(gg[inside]) if inside.any() else 0.5
    br = gg > thr
    ring = (rn > 0.94) & (rn < 0.99)
    A = br if br[ring].mean() > 0.5 else ~br
    bgs = blur(bgd, 1, 1)
    tb = otsu(np.clip(bgs[inside] / 1.5, 0, 1)) * 1.5
    B = bgs > tb
    if n > 1:
        # was in allen N Speichen gleich aussieht und nicht exakt wie der Hintergrund ist, ist Material
        mads = blur(mad, 2, 2)
        tm = otsu(np.clip(mads[inside] / 0.6, 0, 1)) * 0.6
        B = B | ((mads < 0.6 * tm) & (bgs > 0.35 * tb))

    band = (rn < 0.97) & (rn > 0.15)

    def score(M):
        gap, mat = band & ~M, band & M
        if gap.sum() < 50 or mat.sum() < 50:
            return -9.0
        return (bgd[mat].mean() - bgd[gap].mean()) + (mad[gap].mean() - mad[mat].mean())

    hub = (rn > 0.12) & (rn < 0.30)

    def plausible(M):
        # Nabe (um die Mitte) ist bei echten Felgen überwiegend Material
        return M[hub].mean() >= 0.55

    sa = score(A) + (0 if plausible(A) else -10)
    sb = score(B) + (0 if plausible(B) else -10)
    M, method = (B, "Hintergrund") if sb >= sa else (A, "Helligkeit")
    m = (M & inside).astype(np.float32)
    if clean > 0:
        m = (blur((blur(m, clean, 1) > 0.999).astype(np.float32), clean, 1) > 0.001).astype(np.float32)
        m = (blur((blur(m, clean, 1) > 0.001).astype(np.float32), clean, 1) > 0.999).astype(np.float32)
        m *= inside
    return m, method


def fill_background(rgb, valid, iters=12, radius=4):
    """
    Füllt alle ungültigen Pixel (Hintergrund, Kantensaum) mit der Farbe des benachbarten
    gültigen Materials – damit die Fototextur an den Kanten nie Hintergrund (z.B. weiß) zeigt.
    """
    out = rgb[..., :3].astype(np.float32).copy()
    w = valid.astype(np.float32)
    for _ in range(iters):
        if w.min() >= 1.0:
            break
        den = blur(w, radius, 1)
        num = np.stack([blur(out[..., c] * w, radius, 1) for c in range(3)], -1)
        fill = (w < 1.0) & (den > 1e-3)
        out[fill] = num[fill] / den[fill][:, None]
        w = np.where(fill, 1.0, w)
    return out


# ============================================================ Polarraster
def bilinear(img, x, y):
    h, w = img.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    a = img[y0, x0]
    b = img[y0, x0 + 1]
    c = img[y0 + 1, x0]
    d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def sample_polar(mask, cx, cy, rx, ry, rn_values, n_t):
    """Feld F[i, j] = Maske bei normiertem Radius rn_values[i] und Winkel j*2pi/n_t."""
    th = np.arange(n_t) * (2 * np.pi / n_t)
    R, T = np.meshgrid(rn_values, th, indexing="ij")
    x = cx + R * rx * np.sin(T)
    y = cy + R * ry * np.cos(T)
    return bilinear(mask, x, y).astype(np.float32)


def detect_symmetry(mask, cx, cy, rx, ry, n_max=24, min_iou=0.80):
    """Größte Ordnung N (3..n_max), unter deren Drehung die Maske gleich bleibt; 1 = keine."""
    n_t = 5040  # durch fast alle üblichen Speichenzahlen teilbar
    rn = np.linspace(0.25, 0.85, 40)
    F = sample_polar(mask, cx, cy, rx, ry, rn, n_t) > 0.5
    best, scores = 1, {}
    for n in range(3, n_max + 1):
        s = int(round(n_t / n))
        G = np.roll(F, s, axis=1)
        iou = (F & G).sum() / max(1, (F | G).sum())
        scores[n] = float(iou)
        if iou >= min_iou:
            best = n
    return best, scores


def detect_symmetry_gray(gray, cx, cy, rx, ry, n_max=24, rel=0.8, min_corr=0.3, band=(0.3, 0.85)):
    """
    Speichenordnung über die Korrelation des GRAUBILDS mit sich selbst, gedreht um 360/N.
    Robuster als die Maske, weil Schattierungen an den Speichen mitgemessen werden.
    Gibt das größte N zurück, dessen Korrelation >= rel * bestes ist (10 statt 5 bei 10 Speichen).
    """
    n_t = 5040
    F = sample_polar(gray, cx, cy, rx, ry, np.linspace(band[0], band[1], 40), n_t)
    F = F - F.mean(axis=1, keepdims=True)
    den = (F * F).sum()
    corr = {}
    for n in range(3, n_max + 1):
        G = np.roll(F, int(round(n_t / n)), axis=1)
        corr[n] = float((F * G).sum() / max(den, 1e-9))
    best = max(corr.values())
    if best < min_corr:
        return 1, corr
    return max(n for n, c in corr.items() if c >= rel * best), corr


def detect_hub_symmetry(gray, cx, cy, rx, ry, n_spoke):
    """
    Symmetrie der Nabe (Radschrauben) – oft anders als die Speichen (z.B. 10 Speichen, 5 Schrauben).
    Muss ein Teiler der Speichenordnung sein oder wird separat erkannt.
    """
    n, corr = detect_symmetry_gray(gray, cx, cy, rx, ry, n_max=12, band=(0.12, 0.30), rel=0.85)
    return n


def symmetrize_zones(F, radii, split_r, n_hub, n_spoke):
    """Innen (r < split_r) mit Nabensymmetrie, außen mit Speichensymmetrie angleichen."""
    out = F.copy()
    inner = radii < split_r
    if n_spoke > 1:
        out[~inner] = symmetrize_polar(F[~inner], n_spoke)
    if n_hub > 1:
        out[inner] = symmetrize_polar(F[inner], n_hub)
    return out


def symmetrize_polar(F, n):
    n_r, n_t = F.shape
    if n <= 1 or n_t % n:
        return F
    return np.tile(F.reshape(n_r, n, n_t // n).mean(axis=1), (1, n))


# ============================================================ Felgenstern-Mesh
def star_mesh(F, radii, iso=0.5):
    """
    Gefülltes Marching-Squares auf dem Polarraster F (n_r x n_t, in theta zyklisch).
    radii: Radien der Rasterzeilen in Metern.
    Gibt (verts (N,3) mit z=0, faces: Liste von Index-Listen, CCW von +Z gesehen) zurück.
    """
    n_r, n_t = F.shape
    dth = 2 * np.pi / n_t
    inside = F >= iso

    rows, cols, kinds, ts = [], [], [], []  # Kanten-Punkte: (i, j, art, t)
    edge_id = {}
    n_corner = n_r * n_t

    def corner(i, j):
        return i * n_t + (j % n_t)

    def edge_pt(i, j, kind, fa, fb):
        # kind 0: radiale Kante (i,j)-(i+1,j); kind 1: Winkelkante (i,j)-(i,j+1)
        key = (i, j % n_t, kind)
        v = edge_id.get(key)
        if v is None:
            v = n_corner + len(rows)
            edge_id[key] = v
            rows.append(i)
            cols.append(j % n_t)
            kinds.append(kind)
            ts.append((iso - fa) / (fb - fa) if fb != fa else 0.5)
        return v

    I, J = np.meshgrid(np.arange(n_r - 1), np.arange(n_t), indexing="ij")
    Jn = (J + 1) % n_t
    # CCW (theta läuft im Uhrzeigersinn): (i,j) -> (i,j+1) -> (i+1,j+1) -> (i+1,j)
    c_in = np.stack([inside[I, J], inside[I, Jn], inside[I + 1, Jn], inside[I + 1, J]], axis=-1)
    cnt = c_in.sum(axis=-1)

    faces = []
    full = np.argwhere(cnt == 4)
    if len(full):
        i, j = full[:, 0], full[:, 1]
        jn = (j + 1) % n_t
        quad = np.stack([i * n_t + j, i * n_t + jn, (i + 1) * n_t + jn, (i + 1) * n_t + j], axis=1)
        faces.extend(quad.tolist())

    for i, j in np.argwhere((cnt > 0) & (cnt < 4)):
        i, j = int(i), int(j)
        cs = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
        # Kanten zwischen aufeinanderfolgenden Ecken: (Basis-i, Basis-j, Art)
        es = [(i, j, 1), (i, j + 1, 0), (i + 1, j, 1), (i, j, 0)]
        vals = [F[a, b % n_t] for a, b in cs]
        ins = [v >= iso for v in vals]
        poly = []
        for k in range(4):
            k2 = (k + 1) % 4
            if ins[k]:
                poly.append(corner(*cs[k]))
            if ins[k] != ins[k2]:
                ei, ej, kind = es[k]
                # t immer von der Basisecke (ei,ej) aus messen
                fa = F[ei, ej % n_t]
                fb = F[ei + 1, ej % n_t] if kind == 0 else F[ei, (ej + 1) % n_t]
                poly.append(edge_pt(ei, ej, kind, fa, fb))
        if len(poly) >= 3:
            faces.append(poly)

    # Vertex-Positionen
    th = np.arange(n_t) * dth
    rr, tt = np.meshgrid(radii, th, indexing="ij")
    corner_xy = np.stack([rr * np.sin(tt), rr * np.cos(tt)], axis=-1).reshape(-1, 2)
    if rows:
        ri = np.array(rows)
        ci = np.array(cols)
        kd = np.array(kinds)
        t = np.clip(np.array(ts), 0.0, 1.0)
        r_e = np.where(kd == 0, radii[ri] + t * (radii[np.minimum(ri + 1, n_r - 1)] - radii[ri]), radii[ri])
        th_e = np.where(kd == 1, (ci + t) * dth, ci * dth)
        edge_xy = np.stack([r_e * np.sin(th_e), r_e * np.cos(th_e)], axis=-1)
        all_xy = np.vstack([corner_xy, edge_xy])
    else:
        all_xy = corner_xy

    # Unbenutzte Vertices entfernen
    used = np.zeros(len(all_xy), bool)
    for f in faces:
        used[f] = True
    remap = -np.ones(len(all_xy), np.int64)
    remap[used] = np.arange(used.sum())
    faces = [remap[f].tolist() for f in faces]
    verts = np.zeros((int(used.sum()), 3))
    verts[:, :2] = all_xy[used]
    return verts, faces


def boundary_edges(faces):
    """Kanten, die nur zu einer Fläche gehören (Außen- und Lochkonturen)."""
    count = {}
    for f in faces:
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            key = (a, b) if a < b else (b, a)
            count[key] = count.get(key, 0) + 1
    return [k for k, c in count.items() if c == 1]


def boundary_edges_directed(faces):
    """Randkanten in Umlaufrichtung ihrer Fläche (a -> b)."""
    count = {}
    directed = []
    for f in faces:
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            key = (a, b) if a < b else (b, a)
            count[key] = count.get(key, 0) + 1
            directed.append((a, b))
    return [(a, b) for a, b in directed if count[(a, b) if a < b else (b, a)] == 1]


def _components(B):
    """Zusammenhangskomponenten (4er-Nachbarschaft) auf dem Polarraster, zyklisch in theta."""
    n_r, n_t = B.shape
    lab = -np.ones(B.shape, np.int64)
    comps = []
    for i0, j0 in zip(*np.nonzero(B)):
        if lab[i0, j0] >= 0:
            continue
        cid = len(comps)
        stack = [(i0, j0)]
        lab[i0, j0] = cid
        cells = []
        while stack:
            i, j = stack.pop()
            cells.append((i, j))
            for a, b in ((i + 1, j), (i - 1, j), (i, (j + 1) % n_t), (i, (j - 1) % n_t)):
                if 0 <= a < n_r and B[a, b] and lab[a, b] < 0:
                    lab[a, b] = cid
                    stack.append((a, b))
        comps.append(cells)
    return comps


def _is_thin(ii, jj, shape, radii, half_mm=1.6):
    """Erodiert die Lücke um half_mm in Millimetern (radial und tangential); bleibt <10 % übrig -> dünn."""
    n_r, n_t = shape
    i0, i1 = ii.min(), ii.max() + 1
    m = np.zeros((i1 - i0, n_t), bool)
    m[ii - i0, jj] = True
    dr = max(float(np.mean(np.diff(radii))) * 1000.0, 1e-3)
    kr = max(1, int(round(half_mm / dr)))
    e = m.copy()
    for k in range(1, kr + 1):                          # radial
        up = np.zeros_like(m)
        dn = np.zeros_like(m)
        up[:-k] = m[k:]
        dn[k:] = m[:-k]
        e &= up & dn
    dth = 2 * np.pi / n_t
    for row in range(e.shape[0]):                       # tangential, je Radius andere Zellbreite
        r_mm = max(radii[i0 + row] * 1000.0, 1.0)
        kt = max(1, int(round(half_mm / (r_mm * dth))))
        if kt >= n_t // 2:
            continue
        mr = m[row]
        acc = mr.copy()
        for k in range(1, kt + 1):
            acc &= np.roll(mr, k) & np.roll(mr, -k)
        e[row] &= acc
    return e.sum() < 0.1 * len(ii)


def polar_close(F, radii, half_mm=1.6):
    """Morphologisches Schließen auf dem Polarraster in Millimetern (radial + tangential)."""
    n_r, n_t = F.shape
    M = F >= 0.5
    dr = max(float(np.mean(np.diff(radii))) * 1000.0, 1e-3)
    kr = max(1, int(round(half_mm / dr)))
    dth = 2 * np.pi / n_t
    kts = [min(n_t // 4, max(1, int(round(half_mm / (max(r * 1000.0, 1.0) * dth))))) for r in radii]

    def morph(B, grow):
        out = B.copy()
        for k in range(1, kr + 1):                        # radial
            up = np.zeros_like(B)
            dn = np.zeros_like(B)
            up[:-k] = B[k:]
            dn[k:] = B[:-k]
            if grow:
                out |= up | dn
            else:
                up[-k:] = True
                dn[:k] = True
                out &= up & dn
        res = out.copy()
        for i, kt in enumerate(kts):                      # tangential
            row = out[i]
            acc = row.copy()
            for k in range(1, kt + 1):
                if grow:
                    acc |= np.roll(row, k) | np.roll(row, -k)
                else:
                    acc &= np.roll(row, k) & np.roll(row, -k)
            res[i] = acc
        return res

    closed = morph(morph(M, True), False)
    out = F.copy()
    out[closed & ~M] = 1.0
    return out


def clean_polar(F, radii, min_hole_mm2=60.0, rel_spot=0.07, lug_zone=0.45):
    """
    - Material, das nicht mit dem Außenring verbunden ist, entfernen (würde lose herumfliegen)
    - Lücken kleiner als min_hole_mm2 füllen (Spiegelungen/Störungen), Mittelbohrung bleibt
    """
    n_r, n_t = F.shape
    dr = np.gradient(radii)
    cell_mm2 = (radii[:, None] * (2 * np.pi / n_t) * dr[:, None]) * 1e6
    M = F >= 0.5
    out = F.copy()
    for cells in _components(M):
        ii = np.array([c[0] for c in cells])
        if ii.max() < n_r - 1:                  # berührt den Außenring nicht -> lose
            out[ii, [c[1] for c in cells]] = 0.0
    M = out >= 0.5
    holes = []
    for cells in _components(~M):
        ii = np.array([c[0] for c in cells])
        jj = np.array([c[1] for c in cells])
        if ii.min() == 0:                       # Mittelbohrung
            continue
        holes.append((ii, jj, cell_mm2[ii, 0].sum(), radii[ii].mean() / radii[-1]))
    biggest = max([h[2] for h in holes], default=0.0)
    hole_mask = out < 0.5
    for ii, jj, area, r_mean in holes:
        # dünne Schlitze (z.B. Fugen zwischen Rahmen und Einsatz): schmaler als ~3 mm -> füllen
        if _is_thin(ii, jj, F.shape, radii, half_mm=1.6):
            out[ii, jj] = 1.0
            continue
        # kleine Störungen immer füllen; außerhalb der Radschrauben-Zone auch Flecken
        # (z.B. Spiegelungen auf silbernen Einsätzen), die viel kleiner als ein Fenster sind
        if area < min_hole_mm2 or (r_mean > lug_zone and area < rel_spot * biggest):
            out[ii, jj] = 1.0
    return out


def _dilate_max(D, steps):
    out = D.copy()
    for k in range(steps):
        p = np.pad(out, 1, mode="edge")
        m = np.maximum.reduce([out, p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
        if k % 2:
            m = np.maximum.reduce([m, p[:-2, :-2], p[:-2, 2:], p[2:, :-2], p[2:, 2:]])
        out = m
    return out


def _erode(m, square):
    p = np.pad(m, 1, mode="edge")
    out = m & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    if square:
        out &= p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:]
    return out


def edge_distance_fn(F, radii, r_face, max_mm, grid_mm=1.0):
    """
    Abstand (mm) jedes Punktes zur nächsten Fenster-/Lochkante, aus dem Polarfeld F.
    Gibt eine Funktion xy(N,2 in m) -> Abstand in mm zurück.
    """
    n_r, n_t = F.shape
    g = grid_mm / 1000.0
    N = int(np.ceil(2 * r_face / g)) + 3
    ax = (np.arange(N) - (N - 1) / 2.0) * g
    X, Y = np.meshgrid(ax, ax)
    R = np.hypot(X, Y)
    TH = np.mod(np.arctan2(X, Y), 2 * np.pi)
    fi = np.interp(R, radii, np.arange(n_r))
    fj = TH / (2 * np.pi / n_t)
    i0 = np.clip(np.floor(fi).astype(int), 0, n_r - 2)
    j0 = np.floor(fj).astype(int) % n_t
    ti, tj = np.clip(fi - i0, 0, 1), fj - np.floor(fj)
    j1 = (j0 + 1) % n_t
    val = ((F[i0, j0] * (1 - tj) + F[i0, j1] * tj) * (1 - ti)
           + (F[i0 + 1, j0] * (1 - tj) + F[i0 + 1, j1] * tj) * ti)
    M = (val >= 0.5) | (R >= r_face)          # außerhalb = Felgenbett (keine Rundung zum Bett hin)
    M &= R >= radii[0]                         # Mittelbohrung ist eine Kante
    D = np.zeros(M.shape, np.float32)
    cur = M.copy()
    steps = int(np.ceil(max_mm / grid_mm)) + 2
    for k in range(steps):                     # abwechselnd Kreuz/Quadrat ~ Achteck-Abstand
        D += cur
        cur = _erode(cur, k % 2 == 1)
        if not cur.any():
            break
    D = D * grid_mm
    # lokale halbe Speichenbreite = größter Abstand in der Umgebung (Grat der Speiche)
    W = _dilate_max(D, steps)
    T = blur(np.clip(D / np.maximum(W, grid_mm), 0.0, 1.0), 1, 2)

    def at(xy):
        px = xy[:, 0] / g + (N - 1) / 2.0
        py = xy[:, 1] / g + (N - 1) / 2.0
        return bilinear(T, px, py)
    return at


def smooth_on_mesh(values, faces, n_verts, iters=6, lam=0.6):
    """
    Laplace-Glättung von Werten auf den Mesh-Vertices (über die Kanten der Flächen).
    Randpunkte (an Fenstern) mitteln dabei auch mit den Punkten innerhalb der Speiche –
    das entfernt die Sägezähne, die durch Hintergrundwerte an der Kante entstehen.
    """
    if iters <= 0 or not faces:
        return values
    a_list, b_list = [], []
    for f in faces:
        k = len(f)
        for i in range(k):
            a_list.append(f[i])
            b_list.append(f[(i + 1) % k])
    a = np.array(a_list + b_list)
    b = np.array(b_list + a_list)
    deg = np.bincount(a, minlength=n_verts).astype(np.float64)
    deg[deg == 0] = 1
    v = values.astype(np.float64).copy()
    for _ in range(iters):
        avg = np.bincount(a, weights=v[b], minlength=n_verts) / deg
        v += lam * (avg - v)
    return v


def _boundary_neighbors(bnd, n_verts):
    """Für jeden Randpunkt seine zwei Nachbarn entlang der Kante (Vorgänger, Nachfolger)."""
    prev = -np.ones(n_verts, np.int64)
    nxt = -np.ones(n_verts, np.int64)
    for a, b in bnd:
        nxt[a] = b
        prev[b] = a
    on = (prev >= 0) & (nxt >= 0)
    return prev, nxt, on


def _smooth_along_boundary(vals, prev, nxt, on, iters, lam=0.5, mu=None):
    """1D-Glättung entlang der Kanten-Linie (Taubin: ohne Schrumpfen, wenn mu gesetzt)."""
    v = vals.astype(np.float64).copy()
    idx = np.nonzero(on)[0]
    p, q = prev[idx], nxt[idx]
    for k in range(iters):
        f = lam if (mu is None or k % 2 == 0) else mu
        avg = 0.5 * (v[p] + v[q])
        v[idx] = v[idx] + f * (avg - v[idx])
    return v


def _near_boundary(faces, n_verts, bnd, rings=3):
    """Maske: Vertices bis zu 'rings' Kanten von der Fensterkante entfernt."""
    m = np.zeros(n_verts, bool)
    for a, b in bnd:
        m[a] = m[b] = True
    a_list, b_list = [], []
    for f in faces:
        k = len(f)
        for i in range(k):
            a_list.append(f[i])
            b_list.append(f[(i + 1) % k])
    A = np.array(a_list + b_list)
    B = np.array(b_list + a_list)
    for _ in range(rings):
        grow = np.zeros(n_verts, bool)
        grow[A[m[B]]] = True
        m |= grow
    return m


def star_solid(F, radii, z_front_fn, thick_fn, front_offset_fn=None, front_override_fn=None,
               min_thick=0.006, smooth_iters=10, edge_iters=100):
    """
    Geschlossener Felgenstern: Vorderfläche (Wölbung), Rückfläche, Seitenwände
    exakt parallel zur Radachse (3-Achs-fräsbar von vorn).
    """
    fv, ff = star_mesh(F, radii)
    if not ff:
        return fv, ff, [], []
    bnd = boundary_edges_directed(ff)
    prev, nxt, on = _boundary_neighbors(bnd, len(fv))
    if edge_iters > 0:
        # Kontur der Fenster in der Ebene glätten (Rasterstufen weg, Taubin = kein Schrumpfen)
        for c in (0, 1):
            fv[:, c] = _smooth_along_boundary(fv[:, c], prev, nxt, on, 40, 0.5, -0.53)
    r = np.hypot(fv[:, 0], fv[:, 1])
    zb = z_front_fn(r) - thick_fn(r)
    zf = z_front_fn(r) + (front_offset_fn(fv[:, :2]) if front_offset_fn else 0.0)
    if front_override_fn is not None:
        z0 = zf.copy()
        zf = front_override_fn(fv[:, :2], zf)
        off = smooth_on_mesh(zf - z0, ff, len(fv), smooth_iters)      # allgemeine Glättung
        if edge_iters > 0:
            # verstärkt an den Kanten: erst entlang der Kantenlinie, dann im Randstreifen
            off = _smooth_along_boundary(off, prev, nxt, on, edge_iters, 0.5)
            band = _near_boundary(ff, len(fv), bnd, rings=3)
            off_band = smooth_on_mesh(off, ff, len(fv), edge_iters // 2)
            off = np.where(band, off_band, off)
        zf = z0 + off
        zb = np.minimum(zb, zf - thick_fn(r))    # Rückseite folgt der KI-Vorderseite
    zf = np.maximum(zf, zb + min_thick)          # Mindestwandstärke
    n = len(fv)
    verts = np.vstack([np.column_stack([fv[:, :2], zf]), np.column_stack([fv[:, :2], zb])])
    faces = list(ff)
    faces += [[v + n for v in f[::-1]] for f in ff]
    faces += [[a, a + n, b + n, b] for a, b in bnd]
    sharp = []
    for a, b in bnd:
        for x, y in ((a, b), (a + n, b + n)):
            sharp.append((x, y) if x < y else (y, x))
    kinds = [0] * len(ff) + [1] * len(ff) + [2] * len(bnd)   # 0 vorn, 1 hinten, 2 Taschenwand
    return verts, faces, sharp, kinds


def rim_fade(r, r_face, fade, ring=0.0):
    """1 innen, läuft zum Felgenrand weich auf 0 aus (Speichen treffen das Bett auf Randhöhe)."""
    u = np.clip((r_face - ring - r) / max(fade, 1e-6), 0.0, 1.0)
    return u * u * (3 - 2 * u)


def ai_front_fn(depth, cx, cy, rx, ry, R_out, n, strength=1.0, edge_t=None, hub_n=None, split_r=0.0,
                relief_mm=15.0, detail_scale_px=None, r_face=None, fade=None):
    """
    Relief aus der KI-Tiefe als ZUSATZ zur Grundform (Konkavität):
    Von vorn fotografiert kann die KI die großflächige Tiefe (Schüssel) kaum erkennen –
    die liefert die Grundform. Aus der KI kommen nur die Details: Hochpass der Tiefe
    (gewölbte Speichen, Kanten, Stufen glanzgedreht/schwarz, Nabe).
    """
    base = np.nan_to_num(depth, nan=float(np.nanmin(depth)))
    fine = blur(base, 1, 2)                                    # Pixelrauschen weg, Kanten bleiben
    big = max(4, int(round((detail_scale_px or 0.10 * rx))))
    coarse = blur(base, big, 3)                                # großflächige (unzuverlässige) Tiefe
    hp = fine - coarse                                         # nur Details

    def _sample_n(field, xy, nn):
        vals = []
        for k in range(max(1, nn)):
            a = 2 * np.pi * k / max(1, nn)
            ca, sa = np.cos(a), np.sin(a)
            x = xy[:, 0] * ca - xy[:, 1] * sa
            y = xy[:, 0] * sa + xy[:, 1] * ca
            vals.append(bilinear(field, cx + x / R_out * rx, cy + y / R_out * ry))
        V = np.stack(vals)
        if len(vals) >= 4:                                     # robuster Mittelwert (Ausreißer weg)
            V.sort(axis=0)
            q = max(1, len(vals) // 4)
            return V[q:-q].mean(axis=0)
        return np.median(V, axis=0)

    def sample(xy):
        outer = _sample_n(hp, xy, n)
        if hub_n is None or hub_n == n:
            return outer
        inner = _sample_n(hp, xy, hub_n)
        return np.where(np.hypot(xy[:, 0], xy[:, 1]) < split_r, inner, outer)

    def f(xy, z_base):
        d = sample(xy)
        t = edge_t(xy) if edge_t is not None else np.ones(len(xy))
        sel = t > 0.3
        if sel.sum() < 100:
            return z_base
        scale = np.percentile(np.abs(d[sel]), 97)
        if scale < 1e-9:
            return z_base
        rel = np.clip(d / scale, -1.2, 1.0)                    # -1..1 = tief..hoch
        w = 1.0
        if r_face is not None:
            w = rim_fade(np.hypot(xy[:, 0], xy[:, 1]), r_face, fade or 0.30 * r_face)
        return z_base + strength * w * rel * relief_mm / 1000.0
    return f


def tone_step_fn(gray, mask, cx, cy, rx, ry, R_out, n, hub_n=None, split_r=0.0, bevel_px=1.0):
    """
    Feine Kante der glanzgedrehten Fläche direkt aus dem Foto (schärfer als die KI):
    Ist die Felge deutlich zweifarbig (z.B. silber glanzgedreht + schwarz), wird die helle
    Fläche zur erhabenen Stufe. Gibt (f(xy)->0..1, info) zurück; None, wenn einfarbig.
    """
    g = blur(gray, 1, 1)
    sel = (mask > 0.5) & (norm_radius(gray.shape, cx, cy, rx, ry) < 0.92)
    vals = g[sel]
    if vals.size < 500:
        return None, "zu wenig Material"
    thr = otsu(vals)
    lo, hi = vals[vals <= thr], vals[vals > thr]
    if lo.size < 0.08 * vals.size or hi.size < 0.08 * vals.size:
        return None, "einfarbig"
    sep = (hi.mean() - lo.mean()) / (vals.std() + 1e-6)
    if hi.mean() - lo.mean() < 0.30 or sep < 1.6:
        return None, "einfarbig (Kontrast %.2f)" % (hi.mean() - lo.mean())
    w = max(0.02, 0.15 * (hi.mean() - lo.mean()))
    soft = np.clip((g - thr) / w * 0.5 + 0.5, 0.0, 1.0)      # weiche Stufe (Fase ~ 1 px)
    if bevel_px > 0:
        soft = blur(soft, int(round(bevel_px)), 1)

    def _sample_n(xy, nn):
        vals = []
        for k in range(max(1, nn)):
            a = 2 * np.pi * k / max(1, nn)
            ca, sa = np.cos(a), np.sin(a)
            x = xy[:, 0] * ca - xy[:, 1] * sa
            y = xy[:, 0] * sa + xy[:, 1] * ca
            vals.append(bilinear(soft, cx + x / R_out * rx, cy + y / R_out * ry))
        return np.median(np.stack(vals), axis=0)              # über alle Speichen -> sauber

    def f(xy):
        outer = _sample_n(xy, n)
        if hub_n is None or hub_n == n:
            return outer
        inner = _sample_n(xy, hub_n)
        return np.where(np.hypot(xy[:, 0], xy[:, 1]) < split_r, inner, outer)
    return f, "zweifarbig (Kontrast %.2f)" % (hi.mean() - lo.mean())


def apply_dish(verts, z_front, dish, power, r_face):
    r = np.hypot(verts[:, 0], verts[:, 1])
    s = np.clip(1.0 - r / r_face, 0.0, 1.0)
    out = verts.copy()
    out[:, 2] = z_front - dish * s ** power
    return out


# ============================================================ Felgenbett
def barrel_profile(R, W, wall, flange, drop):
    """Geschlossener Querschnitt (r, z), Front bei z=0, Rückseite bei z=-W."""
    outer = [
        (R + flange, 0.0),
        (R + flange, -0.006),
        (R + 0.002, -0.014),
        (R, -0.020),
        (R, -0.18 * W),
        (R - drop, -0.30 * W),
        (R - drop, -0.62 * W),
        (R, -0.74 * W),
        (R, -W + 0.020),
        (R + 0.002, -W + 0.014),
        (R + flange, -W + 0.006),
        (R + flange, -W),
    ]
    inner = [(r - wall, z) for r, z in outer]
    return np.array(outer + inner[::-1])


def revolve(profile, sections):
    """Profil (r, z) um Z drehen. Gibt (verts, faces) zurück, Normalen nach außen."""
    P = len(profile)
    phi = np.arange(sections) * (2 * np.pi / sections)
    r, z = profile[:, 0], profile[:, 1]
    verts = np.zeros((sections * P, 3))
    verts[:, 0] = (np.sin(phi)[:, None] * r[None, :]).ravel()
    verts[:, 1] = (np.cos(phi)[:, None] * r[None, :]).ravel()
    verts[:, 2] = np.tile(z, sections)
    k = np.arange(sections)[:, None]
    p = np.arange(P)[None, :]
    k2 = (k + 1) % sections
    p2 = (p + 1) % P
    faces = np.stack([k * P + p, k * P + p2, k2 * P + p2, k2 * P + p], axis=-1).reshape(-1, 4)
    if signed_volume(verts, faces) < 0:
        faces = faces[:, ::-1]
    return verts, faces.tolist()


def signed_volume(verts, faces):
    f = np.asarray(faces)
    tri = np.concatenate([f[:, [0, 1, 2]], f[:, [0, 2, 3]]]) if f.shape[1] == 4 else f
    a, b, c = verts[tri[:, 0]], verts[tri[:, 1]], verts[tri[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


# ============================================================ Gesamt-Pipeline
class Params:
    """Alle Maße in den Einheiten der Oberfläche (Zoll / mm)."""
    diameter = 18.0       # Zoll
    width = 8.0           # Zoll
    use_et = False
    et = 45.0             # mm
    face_inset = 12.0     # mm
    dish = 60.0           # mm
    dish_power = 1.5
    spoke_thickness = 22.0  # mm, Dicke am Felgenrand
    hub_thickness = 40.0  # mm, Dicke an der Nabe
    hub_radius = 85.0     # mm, flache Nabenanlagefläche
    relief = 10.0         # mm, Wölbung der Speichen (0 = flach)
    relief_width = 40.0   # mm, max. halbe Breite, über die gewölbt wird
    boss_height = 12.0    # mm, Nabenbund um den Zentralverschluss
    boss_radius = 75.0    # mm
    boss_slope = 15.0     # mm, Breite der Flanke
    min_hole = 60.0       # mm², kleinere Lücken werden gefüllt
    bore = 0.0            # mm, Mittelbohrung (0 = wie im Bild: Deckel/Logo bleiben)
    hub_zone = 0.33       # Anteil des Radius, in dem die Nabensymmetrie gilt
    ai_strength = 1.0     # 0 = nur Formmodell, 1 = Vorderfläche aus KI-Tiefe
    ai_depth = 25.0       # mm, Stärke des KI-Reliefs (Details auf der Grundform)
    relief_fade = 0.35    # Anteil des Radius, über den das Relief zum Rand auf 0 ausläuft
    tone_step = 4.0       # mm, Stufe der glanzgedrehten Fläche (nur bei zweifarbigen Felgen)
    min_thick = 6.0       # mm, Mindestwandstärke
    flange = 17.0         # mm
    wall = 5.0            # mm
    drop = 22.0           # mm
    ring = 12.0           # mm, Außenring des Sterns
    res_radial = 240
    res_angular = 1080
    sections = 128


def dimensions(p):
    R = p.diameter * INCH / 2.0
    W = p.width * INCH
    flange = p.flange / 1000.0
    wall = p.wall / 1000.0
    R_out = R + flange
    r_face = R - wall + 0.002
    dish = p.dish
    if p.use_et:
        # Nabenanlagefläche (Rückseite der Nabe) liegt ET mm vor der Felgenmitte
        hub_back = -W / 2 * 1000.0 + p.et
        dish = -p.face_inset - (hub_back + p.hub_thickness)   # negativ = konvex
    return R, W, flange, wall, R_out, r_face, dish


def build(mask, cx, cy, rx, ry, p, symmetry_n=1, depth=None, hub_n=None, gray=None):
    """
    mask: Materialmaske (Bildpixel, y nach oben), cx..ry in Pixeln (Felgenhorn außen).
    Gibt dict mit star_verts, star_faces, star_sharp, barrel_verts, barrel_faces, dish.
    """
    R, W, flange, wall, R_out, r_face, dish = dimensions(p)

    if hub_n is None:
        hub_n = symmetry_n
    n_t = int(p.res_angular)
    lcm = int(np.lcm(max(1, symmetry_n), max(1, hub_n)))
    if lcm > 1:
        n_t = max(lcm, int(round(n_t / lcm)) * lcm)
    n_r = int(p.res_radial)
    radii = np.linspace(r_face / n_r * 0.5, r_face, n_r)
    # Spalten schmaler als ~6 mm schließen (Fugen zwischen Rahmen und Einsatz, Spiegelkanten)
    px_per_mm = rx / (R_out * 1000.0)
    k = max(1, int(round(3.0 * px_per_mm)))
    mclosed = (blur((blur(mask, k, 1) > 0.02).astype(np.float32), k, 1) > 0.98).astype(np.float32)
    mask = np.maximum(mask, mclosed)
    F = sample_polar(blur(mask, 1, 1), cx, cy, rx, ry, radii / R_out, n_t)
    split_r = p.hub_zone * R_out
    F = symmetrize_zones(F, radii, split_r, hub_n, symmetry_n)
    F[radii > r_face - p.ring / 1000.0, :] = 1.0   # Außenring verbindet Stern mit Bett
    if p.bore > 0:                                  # saubere Mittelbohrung (Deckel/Logo sind nicht Teil der Felge)
        F[radii < p.bore / 2000.0, :] = 0.0
    F = polar_close(F, radii, 3.0)                  # Spalten < ~6 mm nach dem Angleichen schließen
    F = clean_polar(F, radii, p.min_hole)

    r_hub = min(p.hub_radius / 1000.0, r_face * 0.8)
    z_rim = -p.face_inset / 1000.0

    def s_of(r):  # 1 an der Nabe (flach), 0 am Rand
        return np.clip((r_face - r) / (r_face - r_hub), 0.0, 1.0)

    def z_front(r):
        return z_rim - dish / 1000.0 * s_of(r) ** p.dish_power

    def thick(r):
        return (p.spoke_thickness + (p.hub_thickness - p.spoke_thickness) * s_of(r)) / 1000.0

    offset = None
    dist = None
    use_ai = depth is not None and p.ai_strength > 0
    if (p.relief > 0 and p.relief_width > 0) or use_ai:
        dist = edge_distance_fn(F, radii, r_face, max(p.relief_width, 10.0))
    # Mit KI kommt die Form allein aus der KI-Tiefe (keine künstliche Wölbung / kein Nabenbund)
    if p.relief > 0 and p.relief_width > 0 and not use_ai:

        def offset(xy):
            t = np.clip(dist(xy), 0.0, 1.0)           # 0 = Kante, 1 = Speichenmitte
            off = p.relief / 1000.0 * np.sqrt(1.0 - (1.0 - t) ** 2)   # Viertelkreis-Rundung
            if p.boss_height > 0:
                r = np.hypot(xy[:, 0], xy[:, 1]) * 1000.0
                u = np.clip((p.boss_radius - r) / max(p.boss_slope, 0.1), 0.0, 1.0)
                off = off + p.boss_height / 1000.0 * u * u * (3 - 2 * u)   # weicher Bund
            return off
    elif p.boss_height > 0 and not use_ai:
        def offset(xy):
            r = np.hypot(xy[:, 0], xy[:, 1]) * 1000.0
            u = np.clip((p.boss_radius - r) / max(p.boss_slope, 0.1), 0.0, 1.0)
            return p.boss_height / 1000.0 * u * u * (3 - 2 * u)

    override = None
    if depth is not None and p.ai_strength > 0:
        override = ai_front_fn(depth, cx, cy, rx, ry, R_out, symmetry_n, p.ai_strength, dist,
                               hub_n=hub_n, split_r=split_r, relief_mm=p.ai_depth,
                               r_face=r_face, fade=p.relief_fade * r_face)
    # feine Kante glanzgedreht/schwarz aus dem Foto
    tone_info = "aus"
    if gray is not None and p.tone_step > 0:
        step, tone_info = tone_step_fn(gray, mask, cx, cy, rx, ry, R_out, symmetry_n, hub_n, split_r)
        if step is not None:
            base_override = override

            def override(xy, z, _b=base_override, _s=step):
                z2 = _b(xy, z) if _b is not None else z
                w = rim_fade(np.hypot(xy[:, 0], xy[:, 1]), r_face, 0.02, p.ring / 1000.0)
                return z2 + w * p.tone_step / 1000.0 * (_s(xy) - 1.0)   # dunkle Fläche liegt tiefer
    sv, sf, sharp, kinds = star_solid(F, radii, z_front, thick, offset, override, p.min_thick / 1000.0)
    bv, bf = revolve(barrel_profile(R, W, wall, flange, p.drop / 1000.0), int(p.sections))
    return dict(star_verts=sv, star_faces=sf, star_sharp=sharp, star_kinds=kinds,
                barrel_verts=bv, barrel_faces=bf, dish=dish, tone_info=tone_info,
                hub_back=(z_rim - dish / 1000.0 - p.hub_thickness / 1000.0) * 1000.0)


# ============================================================ Felge im Bild finden
def find_wheel(gray, work=256):
    """
    Sucht die Felgenkontur (Ellipse mit fast gleichen Achsen) über den Bildgradienten.
    Gibt (cx, cy, rx, ry) in Pixeln des übergebenen Bildes zurück.
    """
    h, w = gray.shape
    small = downscale(gray, work)
    f = h / float(small.shape[0])
    gy, gx = np.gradient(blur(small, 1, 2))
    G = np.hypot(gx, gy)
    sh, sw = G.shape
    m = min(sh, sw)
    ang = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    sa, ca = np.sin(ang), np.cos(ang)

    def score(cx, cy, rx, ry):
        x = cx + rx[:, None] * sa[None, :]
        y = cy + ry[:, None] * ca[None, :]
        ok = (x >= 0) & (x < sw - 1) & (y >= 0) & (y < sh - 1)
        v = bilinear(G, x, y) * ok
        # Kontrast über den ganzen Umfang: Mittel minus Streuung bestraft Teilbögen
        return v.mean(axis=1) - 0.5 * v.std(axis=1)

    radii = np.arange(int(m * 0.25), int(m * 0.505))
    # bester Score je Radius (über alle Mittelpunkte)
    best_r = np.full(len(radii), -1.0)
    best_c = np.zeros((len(radii), 2))
    for cy in np.arange(sh * 0.38, sh * 0.62, 2.0):
        for cx in np.arange(sw * 0.38, sw * 0.62, 2.0):
            sc = score(cx, cy, radii, radii)
            upd = sc > best_r
            best_r[upd] = sc[upd]
            best_c[upd] = (cx, cy)
    # Felgen haben mehrere konzentrische Kanten (Horn innen/außen, Bett).
    # Die Außenkontur ist die GRÖSSTE deutliche Kante -> größter Radius mit gutem Score.
    strong = np.where(best_r >= 0.40 * best_r.max())[0]
    # lokales Maximum in der Nähe des größten starken Radius
    k = int(strong.max())
    lo = max(0, k - 4)
    k = lo + int(np.argmax(best_r[lo:k + 1]))
    best = (float(best_r[k]), best_c[k][0], best_c[k][1], float(radii[k]), float(radii[k]))
    # Feinsuche inkl. leichter Perspektive (Ellipse)
    _, cx0, cy0, r0, _ = best
    best = (-1.0,) + best[1:]
    for cy in np.arange(cy0 - 2, cy0 + 2.01, 0.5):
        for cx in np.arange(cx0 - 2, cx0 + 2.01, 0.5):
            for asp in np.linspace(0.85, 1.15, 13):
                rr = np.arange(r0 - 2, r0 + 2.01, 0.5)
                rx = rr / np.sqrt(asp)
                ry = rr * np.sqrt(asp)
                s = score(cx, cy, rx, ry)
                k = int(np.argmax(s))
                if s[k] > best[0]:
                    best = (float(s[k]), cx, cy, float(rx[k]), float(ry[k]))
    _, cx, cy, rx, ry = best
    return cx * f, cy * f, rx * f, ry * f
