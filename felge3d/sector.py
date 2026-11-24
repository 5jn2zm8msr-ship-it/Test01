# SPDX-License-Identifier: GPL-3.0-or-later
"""
Draufsicht aus dem FOTO (nur numpy):
  1. Felge im Foto finden: Mittelpunkt/Radius/Achsen verfeinern, Reifen und Hintergrund ausschließen (Periodizität der Speichen)
  2. Polar-Abwicklung, Speichenzahl N und Drehlage (Phase) per FFT/Autokorrelation
  3. Wiederholeinheit = ganzer Sektor (360°/N): alle N Sektoren übereinanderlegen, Median, Silhouette (Material/Luft)
Alle Bilder: y nach oben, Winkel theta im Uhrzeigersinn von +Y (wie core.sample_polar).
"""
import math

import numpy as np

from . import core


# ---------------------------------------------------------------- Polar
def polar_unwrap(img, cx, cy, rx, ry, r_max_norm=1.0, n_r=240, n_t=1080, r_min_norm=0.0):
    """Abwicklung: Zeilen = Radius (0..r_max_norm von rx/ry), Spalten = Winkel theta; Ellipse wird dabei zum Kreis entzerrt."""
    rn = np.linspace(r_min_norm, r_max_norm, n_r)
    th = np.arange(n_t) * (2 * math.pi / n_t)
    R, T = np.meshgrid(rn, th, indexing="ij")
    x = cx + R * rx * np.sin(T)
    y = cy + R * ry * np.cos(T)
    if img.ndim == 3:
        return np.stack([core.bilinear(img[..., c], x, y) for c in range(img.shape[2])], axis=-1)
    return core.bilinear(img, x, y)


def rectify(img, cx, cy, rx, ry, size=512, r_norm=1.0):
    """Quadratisches Bild, in dem die Felge ein Kreis (Radius size/2 / r_norm) ist (perspektivische Stauchung der Ellipse entzerrt)."""
    u = (np.arange(size) + 0.5) / size * 2 - 1
    U, V = np.meshgrid(u * r_norm, -u * r_norm)           # V: oben = +y
    x = cx + U * rx
    y = cy + V * ry
    if img.ndim == 3:
        return np.stack([core.bilinear(img[..., c], x, y) for c in range(img.shape[2])], axis=-1)
    return core.bilinear(img, x, y)


# ---------------------------------------------------------------- Schritt 1: Felge finden, Reifen ausschließen
def _ring_stats(P):
    n_t = P.shape[1]
    Pz = P - P.mean(axis=1, keepdims=True)
    C = np.fft.rfft(Pz, axis=1) / n_t
    pw = np.abs(C) ** 2
    total = pw[:, 1:].sum(axis=1) + 1e-12
    contrast = Pz.std(axis=1)
    return pw, total, contrast


def rot_scores(M, rows, kmin=3, kmax=24):
    """
    Drehsymmetrie-Score je N: Korrelation des Rings mit sich selbst bei Drehung um 360°/N MINUS der Korrelation bei 180°/N.
    Ein echtes N-zähliges Muster ist bei 360°/N deckungsgleich, bei der halben Schrittweite aber nicht; Teiler und Vielfache
    von N heben sich dadurch heraus (Score ~ 0), nur die Grundzahl bleibt hoch. rows: Indizes der Radien (mittlerer Bereich).
    """
    X = M[rows] - M[rows].mean(axis=1, keepdims=True)
    n_t = X.shape[1]
    den = float(np.sum(X * X)) + 1e-12

    def corr(shift):
        return float(np.sum(X * np.roll(X, -int(round(shift)), axis=1)) / den)
    return {N: corr(n_t / N) - corr(n_t / (2 * N)) for N in range(kmin, kmax + 1)}


def pick_n(scores, tol=0.85):
    """Größtes N mit Score nahe am Besten (bei Gleichstand ist die feinere Teilung die Wiederholeinheit)."""
    top = max(scores.values())
    ok = [N for N, v in scores.items() if v >= tol * top]
    return max(ok)


def periodicity_n(gray, cx, cy, rx, ry, r_lo=0.2, r_hi=0.98, kmin=3, kmax=24, n_r=160, n_t=720):
    """
    Speichenzahl aus der Periodizität über viele Ringe. Gibt (N, Scores, Ringradien, Anteil der Energie auf den Vielfachen
    von N je Ring, Kontrast je Ring (relativ), Polarbild) zurück.
    """
    rn = np.linspace(0.05, 1.15, n_r)
    P = polar_unwrap(gray, cx, cy, rx, ry, 1.15, n_r, n_t, 0.05)
    pw, total, contrast = _ring_stats(P)
    w = contrast / max(contrast.max(), 1e-9)
    sel = np.where((rn >= r_lo) & (rn <= r_hi) & (w >= 0.2))[0]
    if len(sel) < 5:
        sel = np.where((rn >= r_lo) & (rn <= r_hi))[0]
    sc = rot_scores(P, sel, kmin, kmax)
    N = pick_n(sc)
    ks = np.arange(N, pw.shape[1], N)
    q = pw[:, ks].sum(axis=1) / total
    return N, sc, rn, q, w, P


def find_rim(gray, cx, cy, rx, ry):
    """
    Verfeinert den Felgenkreis: Der Speichenbereich ist periodisch (N-zählig) und kontrastreich, der Reifen nicht. Aus dem Ort,
    an dem die Periodizität endet, und der stärksten radialen Kante dahinter folgt der Felgenhorn-Radius (Faktor auf rx/ry).
    Gibt dict(N, scale, q, rn, mean, contrast, window_end, lip, S) zurück.
    """
    N, S, rn, q, w, P = periodicity_n(gray, cx, cy, rx, ry)
    mean = P.mean(axis=1)
    k5 = np.ones(5) / 5.0
    qs = np.convolve(np.pad(q, 2, mode="edge"), k5, mode="valid")
    ws = np.convolve(np.pad(w, 2, mode="edge"), k5, mode="valid")
    ok = (qs >= 0.22) & (ws >= 0.22) & (rn >= 0.3)
    idx = np.where(ok)[0]
    window_end = float(rn[idx[-1]]) if len(idx) else 1.0
    dm = np.abs(np.gradient(np.convolve(np.pad(mean, 2, mode="edge"), k5, mode="valid")))
    lo = np.searchsorted(rn, window_end)
    hi = np.searchsorted(rn, min(window_end * 1.28, 1.14))
    lip = window_end * 1.03
    if hi > lo + 3:
        lip = float(rn[lo + int(np.argmax(dm[lo:hi]))])   # stärkste radiale Kante hinter den Fenstern = Felgenhorn gegen Reifen
    scale = float(np.clip(lip, 0.3, 1.15))
    return dict(N=N, scale=scale, q=q, rn=rn, mean=mean, contrast=w, window_end=window_end, lip=lip, S=S)


def refine_circle(gray, cx, cy, rx, ry):
    """
    Vorsichtige Übernahme von find_rim: Kleine Korrekturen (-8 % ... +8 %) immer; eine stärkere Verkleinerung nur, wenn hinter den
    Fenstern noch ein Ring bis zur Felgenkante liegt (Horn >= 1,12 x Fensterende) – sonst bleibt der Kreis (z. B. Netzfelgen).
    Gibt (rx, ry, info-dict mit 'scale', 'accepted', 'reason', 'N') zurück.
    """
    rim = find_rim(gray, cx, cy, rx, ry)
    sc = rim["scale"]
    ok, why = True, "ok"
    if sc < 0.92:
        if rim["lip"] < 1.12 * rim["window_end"]:
            ok, why = False, "Verkleinerung ohne Ring hinter den Fenstern"
        elif rim["N"] < 3 or rim["N"] > 12:
            ok, why = False, "Speichenzahl unplausibel"
    elif sc > 1.08:
        ok, why = False, "Vergrößerung zu stark"
    info = dict(scale=sc if ok else 1.0, accepted=ok, reason=why, N=rim["N"], window_end=rim["window_end"], lip=rim["lip"])
    return (rx * info["scale"], ry * info["scale"], info)


# ---------------------------------------------------------------- Schritt 2: N und Phase
def detect_n_phase(M, n_hint=0, kmin=3, kmax=24, r_lo=0.25, r_hi=0.95):
    """
    Speichenzahl N und Drehlage aus der polaren Material/Luft-Karte M (n_r x n_t, 0..1): Kammscore (Energie auf N, 2N, 3N ...)
    mit der Regel „größtes N nahe am Besten“, geprüft mit der Autokorrelation (Drehung um 360°/N muss die Karte decken).
    phase = Winkel theta (rad) des Maximums der N-zähligen Grundwelle, d. h. Mitte eines Materialbergs/einer Speiche.
    Gibt dict(N, phase, scores, sims) zurück.
    """
    n_r, n_t = M.shape
    rows = np.arange(int(r_lo * n_r), int(r_hi * n_r))
    sig = M[rows] - M[rows].mean(axis=1, keepdims=True)
    C = np.fft.rfft(sig, axis=1) / n_t
    scores = rot_scores(M, rows, kmin, kmax)
    N = pick_n(scores)
    sims = scores
    if n_hint and 3 <= n_hint <= 24 and n_hint != N and scores.get(n_hint, -1) >= 0.9 * scores[N]:
        N = n_hint
    coef = C.sum(axis=0)                                 # phasenrichtig über die Ringe summieren
    phase = float((-np.angle(coef[N])) / N) % (2 * math.pi / N)
    return dict(N=int(N), phase=phase, scores=scores, sims=sims)


# ---------------------------------------------------------------- Schritt 3: gemittelter Sektor
def sector_stack(Pm, N, theta0, width=360):
    """
    Stapel (N, n_r, width): Sektor k = [theta0 + k*2pi/N, theta0 + (k+1)*2pi/N), je `width` Spalten (Interpolation, zyklisch).
    """
    n_r, n_t = Pm.shape
    out = np.zeros((N, n_r, width), np.float32)
    frac = (np.arange(width) + 0.5) / width
    for k in range(N):
        th = theta0 + (k + frac) * (2 * math.pi / N)
        x = (th / (2 * math.pi) * n_t) % n_t
        i0 = np.floor(x).astype(int) % n_t
        i1 = (i0 + 1) % n_t
        f = (x - np.floor(x))[None, :]
        out[k] = Pm[:, i0] * (1 - f) + Pm[:, i1] * f
    return out


def median_sector(Pm, N, theta0, width=360):
    """Alle N Sektoren übereinander, Median (robust gegen fehlende Speichen, Reflexe, Artefakte)."""
    st = sector_stack(Pm, N, theta0, width)
    return np.median(st, axis=0), st


def mirror_symmetry(S):
    """Spiegelsymmetrie des Sektors (Spalten umdrehen): (Ähnlichkeit 0..1, beste Achsenverschiebung in Spalten)."""
    n_r, w = S.shape
    best, best_sh = -1.0, 0
    for sh in range(-w // 8, w // 8 + 1, 2):
        a = np.roll(S, sh, axis=1)
        b = a[:, ::-1]
        sc = 1.0 - float(np.mean(np.abs(a - b)))
        if sc > best:
            best, best_sh = sc, sh
    return best, best_sh


def symmetrize(S, shift):
    a = np.roll(S, shift, axis=1)
    m = 0.5 * (a + a[:, ::-1])
    return np.roll(m, -shift, axis=1)


def silhouette(S, thr=0.5):
    """Material/Luft-Silhouette des gemittelten Sektors (Binärbild, kleine Inseln/Löcher entfernt)."""
    B = (S >= thr).astype(np.float32)
    k = np.ones(3) / 3.0
    for _ in range(1):                                  # 3x3-Mehrheitsfilter
        pad = np.pad(B, 1, mode="edge")
        acc = sum(pad[i:i + B.shape[0], j:j + B.shape[1]] for i in range(3) for j in range(3)) / 9.0
        B = (acc >= 0.5).astype(np.float32)
    return B


# ---------------------------------------------------------------- Rekonstruktion / Abgleich
def reconstruct(sil, N, theta0, size=512, r_norm=1.0):
    """Silhouette (n_r x width) N-mal in ein quadratisches Bild setzen (Kreis, y oben) -> Maske."""
    n_r, w = sil.shape
    u = (np.arange(size) + 0.5) / size * 2 - 1
    U, V = np.meshgrid(u * r_norm, -u * r_norm)
    r = np.hypot(U, V)
    th = np.arctan2(U, V) % (2 * math.pi)                 # von +Y im Uhrzeigersinn
    rel = ((th - theta0) % (2 * math.pi / N)) / (2 * math.pi / N)
    ri = np.clip((r / r_norm * (n_r - 1)).round().astype(int), 0, n_r - 1)
    ci = np.clip((rel * w).astype(int), 0, w - 1)
    out = sil[ri, ci] * (r <= r_norm)
    return out.astype(np.float32)


# ---------------------------------------------------------------- Schritt 4: Sektor-Mesh (Fenster, Löcher/Aussparungen)
def sector_field(F, radii, N, theta0, r_rows, cols):
    """
    Weiches Material-Feld des gemittelten Sektors auf dem Vertex-Gitter (len(r_rows) x cols), Spalten von theta0 bis theta0 + 360°/N
    INKLUSIVE beider Nähte. Median über alle N Sektoren; erste und letzte Spalte sind identisch (Nähte passen zum Nachbarn).
    """
    n_r, n_t = F.shape
    frac = np.linspace(0.0, 1.0, cols)
    st = np.zeros((N, n_r, cols), np.float32)
    for k in range(N):
        th = theta0 + (k + frac) * (2 * math.pi / N)
        x = (th / (2 * math.pi) * n_t) % n_t
        i0 = np.floor(x).astype(int) % n_t
        i1 = (i0 + 1) % n_t
        f = (x - np.floor(x))[None, :]
        st[k] = F[:, i0] * (1 - f) + F[:, i1] * f
    med = np.median(st, axis=0)
    # radial auf die Zeilenradien umrechnen
    out = np.zeros((len(r_rows), cols), np.float32)
    for j in range(cols):
        out[:, j] = np.interp(r_rows, radii, med[:, j])
    cyc = out[:, :-1]
    for _ in range(2):                                     # Rasterrauschen: 1-2-1 in beiden Richtungen (Spalten zyklisch)
        cyc = 0.25 * np.roll(cyc, 1, axis=1) + 0.5 * cyc + 0.25 * np.roll(cyc, -1, axis=1)
        up = np.concatenate([cyc[:1], cyc[:-1]], axis=0)
        dn = np.concatenate([cyc[1:], cyc[-1:]], axis=0)
        cyc = 0.25 * up + 0.5 * cyc + 0.25 * dn
    sym, sh = mirror_symmetry(cyc)
    if sym > 0.88:                                          # spiegelsymmetrisches Design: Achse suchen und mitteln
        cyc = symmetrize(cyc, sh)
    out = np.concatenate([cyc, cyc[:, :1]], axis=1)         # Naht links == Naht rechts
    return out, float(sym)


def sector_mesh(Fv, r_rows, iso=0.5):
    """
    Gefülltes Marching-Squares auf dem NICHT zyklischen Sektorgitter Fv (rows x cols). Fenster und Löcher in den Speichen
    ergeben sich von selbst. Gibt (r, f, faces, seam) zurück: Radius, Anteil über der Sektorbreite (0..1), Flächen (Index-
    Listen, CCW), seam = Vertex liegt auf einer Naht (f = 0 oder 1).
    """
    n_r, C = Fv.shape
    inside = Fv >= iso
    rows_, cols_, kinds, ts = [], [], [], []
    edge_id = {}
    n_corner = n_r * C

    def corner(i, j):
        return i * C + j

    def edge_pt(i, j, kind, fa, fb):
        key = (i, j, kind)
        v = edge_id.get(key)
        if v is None:
            v = n_corner + len(rows_)
            edge_id[key] = v
            rows_.append(i)
            cols_.append(j)
            kinds.append(kind)
            ts.append((iso - fa) / (fb - fa) if fb != fa else 0.5)
        return v

    faces = []
    for i in range(n_r - 1):
        for j in range(C - 1):
            ins = [inside[i, j], inside[i, j + 1], inside[i + 1, j + 1], inside[i + 1, j]]
            cnt = sum(ins)
            if cnt == 0:
                continue
            if cnt == 4:
                faces.append([corner(i, j), corner(i, j + 1), corner(i + 1, j + 1), corner(i + 1, j)])
                continue
            cs = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
            es = [(i, j, 1), (i, j + 1, 0), (i + 1, j, 1), (i, j, 0)]
            poly = []
            for k in range(4):
                k2 = (k + 1) % 4
                if ins[k]:
                    poly.append(corner(*cs[k]))
                if ins[k] != ins[k2]:
                    ei, ej, kind = es[k]
                    fa = Fv[ei, ej]
                    fb = Fv[ei + 1, ej] if kind == 0 else Fv[ei, ej + 1]
                    poly.append(edge_pt(ei, ej, kind, fa, fb))
            if len(poly) >= 3:
                faces.append(poly)
    # Vertexwerte (r, f)
    cr = np.repeat(r_rows[:, None], C, axis=1).reshape(-1)
    cf = np.tile(np.linspace(0.0, 1.0, C)[None, :], (n_r, 1)).reshape(-1)
    if rows_:
        ri, ci, kd, t = np.array(rows_), np.array(cols_), np.array(kinds), np.clip(np.array(ts), 0, 1)
        er = np.where(kd == 0, r_rows[ri] + t * (r_rows[np.minimum(ri + 1, n_r - 1)] - r_rows[ri]), r_rows[ri])
        ef = np.where(kd == 1, (ci + t) / (C - 1), ci / (C - 1))
        r_all, f_all = np.concatenate([cr, er]), np.concatenate([cf, ef])
    else:
        r_all, f_all = cr, cf
    used = np.zeros(len(r_all), bool)
    for f in faces:
        used[f] = True
    remap = -np.ones(len(r_all), np.int64)
    remap[used] = np.arange(used.sum())
    faces = [remap[f].tolist() for f in faces]
    r, f = r_all[used], f_all[used]
    seam = (f < 1e-9) | (f > 1 - 1e-9)
    return r, f, faces, seam


def _components(faces, n_verts):
    parent = list(range(n_verts))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for f in faces:
        for v in f[1:]:
            ra, rb = find(f[0]), find(v)
            if ra != rb:
                parent[ra] = rb
    return [find(f[0]) for f in faces]


def drop_small(r, f, faces, seam, pitch, min_area_mm2=25.0):
    """Winzige Inseln (Rauschen) entfernen; Inseln an der Naht bleiben."""
    x = r * np.cos(f * pitch)
    y = r * np.sin(f * pitch)
    comp = _components(faces, len(r))
    area = {}
    touches = {}
    for fc, c in zip(faces, comp):
        pts = np.stack([x[fc], y[fc]], 1)
        a = 0.5 * abs(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1]))
        area[c] = area.get(c, 0.0) + a
        touches[c] = touches.get(c, False) or bool(seam[fc].any())
    keep = [fc for fc, c in zip(faces, comp) if area[c] * 1e6 >= min_area_mm2 or touches[c]]
    used = np.zeros(len(r), bool)
    for fc in keep:
        used[fc] = True
    remap = -np.ones(len(r), np.int64)
    remap[used] = np.arange(used.sum())
    return r[used], f[used], [remap[fc].tolist() for fc in keep], seam[used]


def smooth_boundary(r, f, faces, seam, pitch, iters=40):
    """Fenster-/Lochkonturen glätten (Taubin, schrumpft nicht); Nahtpunkte bleiben exakt stehen (sie müssen zum Nachbarn passen)."""
    from . import core
    n = len(r)
    x, y = r * np.cos(f * pitch), r * np.sin(f * pitch)
    bnd = core.boundary_edges_directed(faces)
    prev, nxt, on = core._boundary_neighbors(bnd, n)
    x2 = core._smooth_along_boundary(x, prev, nxt, on, iters, 0.5, -0.53)
    y2 = core._smooth_along_boundary(y, prev, nxt, on, iters, 0.5, -0.53)
    x2[seam], y2[seam] = x[seam], y[seam]
    r2 = np.hypot(x2, y2)
    f2 = np.arctan2(y2, x2) / pitch
    f2[seam] = f[seam]
    return r2, f2


def build_sector_template(res, N, theta0, r_ref_face, cols=73, rows=128, r_a=0.012, r_hub_solid=0.045):
    """
    Musterobjekt-Daten: Sektor-Mesh aus der Silhouette (mehrere Fenster, Löcher in Speichen) + Höhen/Dicke aus dem KI-Mesh +
    Zweifarbigkeit aus dem Foto. Alle N Sektoren sind identisch (Median); Nähte stimmen Punkt für Punkt.
    Gibt dict(r, f, faces, seam, top, bot, zone, N, drehung_deg, ...) zurück.
    """
    F, radii = res["polar_F"], res["polar_r"]
    pitch = 2 * math.pi / N
    r_rows = r_a + (r_ref_face - r_a) * np.linspace(0.0, 1.0, rows)
    Fv, sym = sector_field(F, radii, N, theta0, r_rows, cols)
    Fv[r_rows < r_hub_solid, :] = 1.0                     # Nabenmitte (Schrauben-/Schlitzmuster) bleibt voll
    r, f, faces, seam = sector_mesh(Fv, r_rows)
    r, f, faces, seam = drop_small(r, f, faces, seam, pitch)
    r, f = smooth_boundary(r, f, faces, seam, pitch)
    n = len(r)
    theta = theta0 + f * pitch
    xy = np.stack([r * np.sin(theta), r * np.cos(theta)], axis=-1)       # Koordinaten des KI-Meshes
    top = np.asarray(res["detail_fn"](xy), np.float64).reshape(-1)
    thick = np.asarray(res["thick_fn"](r), np.float64).reshape(-1)
    # Relief glätten (Rasterrauschen); Nahtpunkte paarweise gleich, damit die Kopien verschweißen
    from . import core
    top = core.smooth_on_mesh(top, faces, n, 6)
    for arr in (top, thick):
        idx = np.where(seam)[0]
        key = np.round(r[idx] * 1e6).astype(np.int64)
        for kv in np.unique(key):
            g = idx[key == kv]
            if len(g) > 1:
                arr[g] = arr[g].mean()
    # Zweifarbigkeit aus dem Foto: Helligkeit je Vertex, Median über alle N Sektoren (robust gegen Reflexe)
    ph = res["photo"]
    gray = np.asarray(ph["gray"], np.float64)
    vals = np.zeros((N, n))
    for k in range(N):
        t = theta + k * pitch
        x = ph["cx"] + r / ph["R_out"] * ph["rx"] * np.sin(t)
        y = ph["cy"] + r / ph["R_out"] * ph["ry"] * np.cos(t)
        vals[k] = core.bilinear(gray, x, y)
    br = np.median(vals, axis=0)
    solid = r > r_hub_solid + 0.008
    lo, hi = (np.percentile(br[solid], 5), np.percentile(br[solid], 95)) if solid.sum() > 50 else (0.0, 1.0)
    nrm = np.clip((br - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    thr, var = _otsu(nrm[solid]) if solid.sum() > 50 else (0.5, 0.0)
    cls = nrm > thr
    bright_raw = float(np.mean(br[solid & cls])) if (solid & cls).any() else 0.0
    dark_raw = float(np.mean(br[solid & ~cls])) if (solid & ~cls).any() else 0.0
    # zweifarbig nur, wenn die helle Klasse wirklich hell ist und sich deutlich abhebt (sonst sind es nur Glanzlichter auf dunkler Felge)
    bimodal = bool(var > 0.03 and bright_raw >= 0.5 and bright_raw - dark_raw >= 0.22)
    if bimodal:
        zone = nrm.astype(np.float64)
        zone = np.clip((zone - thr) * 4.0 + 0.5, 0.0, 1.0)            # weiche Zone, Rand bei thr
        for _ in range(6):                                            # Kontur beruhigen (Laplace-Glättung auf dem Mesh)
            zone = core.smooth_on_mesh(zone, faces, n, 3)
        zone = (zone > 0.5).astype(np.float64)
    else:
        zone = np.full(n, 1.0 if (solid.any() and float(np.mean(br[solid])) > 0.55) else 0.0)
    zone[r < r_hub_solid + 0.008] = 0.0
    half = 0.5 * pitch
    phi0 = math.pi / 2 - (theta0 + half)
    return dict(r=r, f=f, faces=faces, seam=seam, top=top, bot=-thick, zone=zone, N=int(N), pitch=pitch,
                drehung_deg=math.degrees((phi0 + math.pi) % (2 * math.pi) - math.pi), sym=sym, bimodal=bool(bimodal),
                polished=float(zone[solid].mean()) if solid.any() else 0.0)


def _otsu(vals, bins=64):
    h, e = np.histogram(vals, bins=bins, range=(0.0, 1.0))
    h = h.astype(np.float64)
    tot = h.sum()
    if tot <= 0:
        return 0.5, 0.0
    c = 0.5 * (e[1:] + e[:-1])
    w0 = np.cumsum(h)
    w1 = tot - w0
    m0 = np.cumsum(h * c) / np.maximum(w0, 1)
    m1 = (np.sum(h * c) - np.cumsum(h * c)) / np.maximum(w1, 1)
    var = w0 * w1 * (m0 - m1) ** 2 / tot ** 2
    k = int(np.argmax(var))
    return float(c[k]), float(var[k])


# ---------------------------------------------------------------- Bearbeitbarer Käfig (Subdivision Surface)
def polar_field(mask, cx, cy, rx, ry, R_out, r_face, n_r=240, n_t=1080):
    """Polarfeld der Material-Maske (Zeilen = Radius in Metern bis r_face, Spalten = Winkel) – ohne KI-Mesh."""
    radii = np.linspace(r_face / n_r * 0.5, r_face, n_r)
    F = core.sample_polar(core.blur(mask, max(1, int(round(rx / 250.0))), 1), cx, cy, rx, ry, radii / R_out, n_t)
    return F, radii


def choose_seam(F, radii, N, r_face):
    """
    Winkel (theta) der Nahtlinie, die in den offenen Zeilen möglichst mitten durch die Fenster läuft (über alle N Kopien gemittelt).
    So liegt die Naht im Luftbereich und schneidet keine Speiche (außer an Verzweigungen, dort passt das Feld trotzdem).
    """
    n_r, n_t = F.shape
    pitch = 2 * math.pi / N
    frac = (F >= 0.5).mean(axis=1)
    sel = np.where((radii >= 0.3 * r_face) & (radii <= 0.93 * r_face) & (frac < 0.9))[0]
    if len(sel) < 4:
        return 0.0
    cand = np.linspace(0.0, pitch, 180, endpoint=False)
    score = np.zeros(len(cand))
    for ci, s0 in enumerate(cand):
        m = np.zeros(len(sel))
        for k in range(N):
            th = s0 + k * pitch
            x = (th / (2 * math.pi) * n_t) % n_t
            i0 = int(x) % n_t
            i1 = (i0 + 1) % n_t
            f = x - int(x)
            m += F[sel, i0] * (1 - f) + F[sel, i1] * f
        m /= N
        score[ci] = -float(np.sum(m * m))
    ker = np.ones(9) / 9.0                              # Mitte des besten Bereichs (maximaler Abstand zu den Speichen)
    sm = np.convolve(np.pad(score, 4, mode="wrap"), ker, mode="valid")
    return float(cand[int(np.argmax(sm))])


def _fine_sampler(Fv, r_rows):
    n_r, C = Fv.shape
    r0, r1 = r_rows[0], r_rows[-1]

    def at(r, f):
        y = np.clip((np.asarray(r) - r0) / (r1 - r0) * (n_r - 1), 0, n_r - 1 - 1e-9)
        x = np.clip(np.asarray(f) * (C - 1), 0, C - 1 - 1e-9)
        i, j = np.floor(y).astype(int), np.floor(x).astype(int)
        fy, fx = y - i, x - j
        return (Fv[i, j] * (1 - fy) * (1 - fx) + Fv[i + 1, j] * fy * (1 - fx)
                + Fv[i, j + 1] * (1 - fy) * fx + Fv[i + 1, j + 1] * fy * fx)
    return at


def cage_mesh(Fv, r_fine, Rc, Cc, r_a, r_face, iso=0.5, Zv=None, pitch=None, min_area_mm2=25.0, snap=0.10, rows=None):
    """
    Grobes Marching-Squares-Netz (Käfig) auf dem Sektor: Ecken-Zustände aus dem feinen Feld, Randpunkte per Bisektion exakt auf die
    feine Kontur gesetzt (keine Treppenstufen). Optional Zv (feines Zonenfeld, z. B. polierte Fläche): volle Zellen werden entlang
    der Zonenkontur geteilt, die Teilungskanten (Chords) liegen exakt auf der Kontur und bekommen später einen Crease.
    Gibt dict(r, f, faces, seam, diamond, zvert, chords) zurück (diamond: 1 = Fläche in der Zone).
    """
    at = _fine_sampler(Fv, r_fine)
    atz = _fine_sampler(Zv, r_fine) if Zv is not None else None
    rc = np.linspace(r_a, r_face, Rc) if rows is None else np.asarray(rows, np.float64)
    Rc = len(rc)
    fc = np.linspace(0.0, 1.0, Cc)
    R, Fg = np.meshgrid(rc, fc, indexing="ij")
    val = at(R, Fg)
    inside = val >= iso
    zval = atz(R, Fg) if atz is not None else np.zeros_like(val)
    zin = (zval >= 0.5) & inside
    pts = {}
    rr, ff = list(R.reshape(-1)), list(Fg.reshape(-1))
    n_corner = Rc * Cc

    def bisect(sampler, a, b, va, thr=iso):
        lo, hi = 0.0, 1.0
        for _ in range(12):
            mid = 0.5 * (lo + hi)
            vm = float(sampler(a[0] + mid * (b[0] - a[0]), a[1] + mid * (b[1] - a[1])))
            if (vm >= thr) == (va >= thr):
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def edge_pt(i, j, kind):
        key = (i, j, kind)
        v = pts.get(key)
        if v is not None:
            return v
        a = (rc[i], fc[j])
        b = (rc[i + 1], fc[j]) if kind == 0 else (rc[i], fc[j + 1])
        va = float(val[i, j])
        t = bisect(at, a, b, va)
        if t < snap or t > 1 - snap:                       # Punkt nahe einer Ecke: auf die Ecke setzen (keine Haarlinien-Flächen)
            ci, cj = (i, j) if t < snap else ((i + 1, j) if kind == 0 else (i, j + 1))
            pts[key] = ci * Cc + cj
            return pts[key]
        rr.append(a[0] + t * (b[0] - a[0]))
        ff.append(a[1] + t * (b[1] - a[1]))
        pts[key] = len(rr) - 1
        return pts[key]

    # ---- Phase 1: Silhouette
    faces, tags = [], []
    for i in range(Rc - 1):
        for j in range(Cc - 1):
            ins = [inside[i, j], inside[i, j + 1], inside[i + 1, j + 1], inside[i + 1, j]]
            c = sum(ins)
            if c == 0:
                continue
            if c == 4:
                faces.append([i * Cc + j, i * Cc + j + 1, (i + 1) * Cc + j + 1, (i + 1) * Cc + j])
                tags.append((i, j))
                continue
            cs = [(i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j)]
            es = [(i, j, 1), (i, j + 1, 0), (i + 1, j, 1), (i, j, 0)]
            poly = []
            for k in range(4):
                k2 = (k + 1) % 4
                if ins[k]:
                    poly.append(cs[k][0] * Cc + cs[k][1])
                if ins[k] != ins[k2]:
                    poly.append(edge_pt(*es[k]))
            poly = [v for k, v in enumerate(poly) if v != poly[k - 1]]       # Doppelpunkte (Ecken-Einrastung) entfernen
            if len(poly) >= 3 and len(set(poly)) == len(poly):
                faces.append(poly)
                tags.append(None)
    # kleine Inseln (Rauschen) entfernen; Nahtinseln bleiben
    if pitch is not None:
        r_all, f_all = np.array(rr), np.array(ff)
        x, y = r_all * np.cos(f_all * pitch), r_all * np.sin(f_all * pitch)
        seam_all = (f_all < 1e-9) | (f_all > 1 - 1e-9)
        comp = _components(faces, len(r_all))
        area, touch = {}, {}
        for fc_, c_ in zip(faces, comp):
            px, py = x[fc_], y[fc_]
            area[c_] = area.get(c_, 0.0) + 0.5 * abs(np.sum(px * np.roll(py, -1) - np.roll(px, -1) * py))
            touch[c_] = touch.get(c_, False) or bool(seam_all[fc_].any())
        keep = [k for k, c_ in enumerate(comp) if area[c_] * 1e6 >= min_area_mm2 or touch[c_]]
        faces = [faces[k] for k in keep]
        tags = [tags[k] for k in keep]
    # ---- Phase 2: Zone (polierte Fläche) in jedem Polygon (auch von der Silhouette angeschnittene Zellen) entlang der Zonenkontur teilen
    diamond = []
    zvert = {}
    chords = []
    zpts = {}
    zs_cache = {}

    def zs(idx):
        v = zs_cache.get(idx)
        if v is None:
            v = float(atz(rr[idx], ff[idx]))
            zs_cache[idx] = v
        return v

    def zcross(ia, ib):
        key = (min(ia, ib), max(ia, ib))
        v = zpts.get(key)
        if v is not None:
            return v
        pa, pb = (rr[ia], ff[ia]), (rr[ib], ff[ib])
        t = bisect(atz, pa, pb, zs(ia), 0.5)
        if t < 0.03 or t > 0.97:
            idx = ia if t < 0.03 else ib
        else:
            rr.append(pa[0] + t * (pb[0] - pa[0]))
            ff.append(pa[1] + t * (pb[1] - pa[1]))
            idx = len(rr) - 1
        zpts[key] = idx
        zvert[idx] = True
        return idx
    out_faces = []
    for fc_, tag in zip(faces, tags):
        if atz is None:
            out_faces.append(fc_)
            diamond.append(0)
            continue
        st = [zs(v) >= 0.5 for v in fc_]
        for v, sv in zip(fc_, st):
            if sv:
                zvert[v] = True
        c = sum(st)
        if c == 0:
            out_faces.append(fc_)
            diamond.append(0)
        elif c == len(fc_):
            out_faces.append(fc_)
            diamond.append(1)
        else:
            items = []
            ncross = 0
            for k in range(len(fc_)):
                k2 = (k + 1) % len(fc_)
                items.append(("v", fc_[k], st[k]))
                if st[k] != st[k2]:
                    items.append(("c", zcross(fc_[k], fc_[k2]), None))
                    ncross += 1
            if ncross != 2:                                     # Sattel/Mehrfachschnitt: nicht teilen, Mehrheit entscheidet
                out_faces.append(fc_)
                diamond.append(1 if 2 * c >= len(fc_) else 0)
                continue
            inp = [it[1] for it in items if it[0] == "c" or it[2]]
            outp = [it[1] for it in items if it[0] == "c" or not it[2]]
            cr = [it[1] for it in items if it[0] == "c"]
            inp = [v for k, v in enumerate(inp) if v != inp[k - 1]]
            outp = [v for k, v in enumerate(outp) if v != outp[k - 1]]
            if cr[0] == cr[1] or len(inp) < 3 or len(outp) < 3:
                out_faces.append(fc_)
                diamond.append(1 if 2 * c >= len(fc_) else 0)
                continue
            out_faces.append(inp)
            diamond.append(1)
            out_faces.append(outp)
            diamond.append(0)
            chords.append((cr[0], cr[1]))
    faces = out_faces
    r_all, f_all = np.array(rr), np.array(ff)
    used = np.zeros(len(r_all), bool)
    for fc_ in faces:
        used[fc_] = True
    remap = -np.ones(len(r_all), np.int64)
    remap[used] = np.arange(used.sum())
    faces = [remap[fc_].tolist() for fc_ in faces]
    r, f = r_all[used], f_all[used]
    zv = np.zeros(len(r_all), bool)
    for k in zvert:
        zv[k] = True
    zv = zv[used]
    chords = [(int(remap[a_]), int(remap[b_])) for a_, b_ in chords if remap[a_] >= 0 and remap[b_] >= 0]
    seam = (f < 1e-9) | (f > 1 - 1e-9)
    return dict(r=r, f=f, faces=faces, seam=seam, diamond=np.array(diamond, np.int8), zvert=zv, chords=chords)


def _poly_area(r, f, faces, pitch):
    x, y = r * np.cos(f * pitch), r * np.sin(f * pitch)
    a = 0.0
    for fc in faces:
        px, py = x[fc], y[fc]
        a += 0.5 * abs(np.sum(px * np.roll(py, -1) - np.roll(px, -1) * py))
    return a


def _boundary_distance(r, f, faces, seam, pitch):
    """Abstand jedes Vertex zur nächsten Randkante (ohne Nahtkanten); die Nachbar-Kopien (±Teilung) zählen mit."""
    from . import core
    x, y = r * np.cos(f * pitch), r * np.sin(f * pitch)
    segs = []
    for a, b in core.boundary_edges(faces):
        if seam[a] and seam[b] and abs(f[a] - f[b]) < 1e-9:
            continue
        segs.append((x[a], y[a], x[b], y[b]))
    if not segs:
        return np.full(len(r), 1.0)
    S = np.array(segs)
    out = []
    for sh in (-pitch, 0.0, pitch):                       # Kopien: Drehung um ±Teilung
        c, s_ = math.cos(sh), math.sin(sh)
        out.append(np.stack([S[:, 0] * c - S[:, 1] * s_, S[:, 0] * s_ + S[:, 1] * c, S[:, 2] * c - S[:, 3] * s_, S[:, 2] * s_ + S[:, 3] * c], 1))
    S = np.concatenate(out)
    d = np.full(len(r), 1e9)
    for k0 in range(0, len(S), 200):
        s = S[k0:k0 + 200]
        ax, ay, bx, by = s[:, 0][None], s[:, 1][None], s[:, 2][None], s[:, 3][None]
        px, py = x[:, None], y[:, None]
        abx, aby = bx - ax, by - ay
        t = np.clip(((px - ax) * abx + (py - ay) * aby) / np.maximum(abx ** 2 + aby ** 2, 1e-12), 0, 1)
        dd = np.hypot(px - (ax + t * abx), py - (ay + t * aby))
        d = np.minimum(d, dd.min(axis=1))
    return d


def fill_reflections(F, radii, photo, r_face, max_rel_area=0.35, weak_min=0.25, bright_min=0.40, debug=None):
    """
    Spiegelungen in polierten Flächen sind keine Löcher: Ein „Luft“-Bereich im Polarfeld ist ein echtes Fenster/Loch, wenn seine Kontur
    im Foto überall eine Kante hat (Steg, Schatten, Felgeninnenseite). Hat er auf einem Teil der Kontur keine Kante (die polierte Fläche
    geht nahtlos weiter), ist er eine Spiegelung und wird zu Material. Nur kleine Bereiche (< max_rel_area des größten Fensters) und
    solche, die nicht bis zum Felgenrand reichen und an eine helle (polierte) Fläche grenzen, kommen infrage (schwarz auf schwarz bleibt Loch). Rückgabe (F neu, Anzahl gefüllter Bereiche).
    """
    from . import core
    n_r, n_t = F.shape
    air = F < 0.5
    lab = -np.ones(F.shape, np.int32)
    comps = []
    for i in range(n_r):
        for j in range(n_t):
            if air[i, j] and lab[i, j] < 0:
                k = len(comps)
                st, cells = [(i, j)], []
                lab[i, j] = k
                while st:
                    a, b = st.pop()
                    cells.append((a, b))
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        c, d = a + da, (b + db) % n_t
                        if 0 <= c < n_r and air[c, d] and lab[c, d] < 0:
                            lab[c, d] = k
                            st.append((c, d))
                comps.append(np.array(cells))
    if len(comps) < 2:
        return F, 0
    dr = float(radii[1] - radii[0])
    area = [float(np.sum(radii[c[:, 0]]) * dr * 2 * math.pi / n_t) for c in comps]
    big = max(area)
    Rg, Tg = np.meshgrid(radii, np.arange(n_t) * 2 * math.pi / n_t, indexing="ij")
    G = core.bilinear(np.asarray(photo["gray"], np.float64), photo["cx"] + Rg / photo["R_out"] * photo["rx"] * np.sin(Tg),
                      photo["cy"] + Rg / photo["R_out"] * photo["ry"] * np.cos(Tg))
    for _ in range(3):
        G = (np.roll(G, 1, 1) + 2 * G + np.roll(G, -1, 1)) / 4
        B = np.pad(G, ((1, 1), (0, 0)), mode="edge")
        G = (B[:-2] + 2 * B[1:-1] + B[2:]) / 4
    gt = (np.roll(G, -2, 1) - np.roll(G, 2, 1)) / (4 * (2 * math.pi / n_t) * Rg + 1e-9)
    gr = np.zeros_like(G)
    gr[1:-1] = (G[2:] - G[:-2]) / (2 * dr)
    grad = np.hypot(gt, gr)
    near = np.max(np.stack([np.roll(np.roll(grad, a, 0), b, 1) for a in (-2, -1, 0, 1, 2) for b in (-2, -1, 0, 1, 2)]), 0)
    out = F.copy()
    filled = 0
    for k, c in enumerate(comps):
        if len(c) < 20 or area[k] > max_rel_area * big or radii[c[:, 0]].max() > 0.9 * r_face:
            continue
        M = np.zeros(F.shape, bool)
        M[c[:, 0], c[:, 1]] = True
        bd = M & ~(np.roll(M, 1, 0) & np.roll(M, -1, 0) & np.roll(M, 1, 1) & np.roll(M, -1, 1))
        if bd.sum() < 10:
            continue
        weak = float(np.mean(near[bd] < 30.0))
        ring = np.zeros(F.shape, bool)
        for a in (-2, -1, 0, 1, 2):
            for b in (-2, -1, 0, 1, 2):
                ring |= np.roll(np.roll(bd, a, 0), b, 1)
        ring &= ~M & (F >= 0.5)
        bright = float(np.percentile(G[ring], 75)) if ring.any() else 0.0           # grenzt an helle (polierte) Fläche?
        if debug is not None:
            debug.append((k, len(c), round(area[k] * 1e4, 1), round(weak, 2), round(bright, 2)))
        if weak > weak_min and bright > bright_min:
            out[M] = 1.0
            filled += 1
    return out, filled


def _erode_material(M, r_fine, pitch, margin_m):
    """Material-Maske (rows x cols, Spalten = Sektorwinkel mit doppelter Naht) um margin_m schrumpfen (Bogenlänge/Radius getrennt)."""
    n_r, C = M.shape
    cyc = M[:, :-1].astype(np.int32)
    Cc = cyc.shape[1]
    out = np.zeros_like(cyc)
    for i in range(n_r):
        a = max(r_fine[i] * pitch / Cc, 1e-6)
        k = int(min(math.ceil(margin_m / a), Cc // 2 - 1))
        ext = np.concatenate([cyc[i, -k:], cyc[i], cyc[i, :k]]) if k > 0 else cyc[i]
        out[i] = (np.convolve(ext, np.ones(2 * k + 1, np.int32), mode="valid") == 2 * k + 1).astype(np.int32)
    kr = int(math.ceil(margin_m / max(r_fine[1] - r_fine[0], 1e-6)))
    pad = np.pad(out, ((kr, kr), (0, 0)), mode="edge")
    cs = np.cumsum(np.pad(pad, ((1, 0), (0, 0))), axis=0)
    win = cs[2 * kr + 1:] - cs[:-(2 * kr + 1)]
    out = (win == 2 * kr + 1).astype(np.float32)
    return np.concatenate([out, out[:, :1]], axis=1)


def _blur_cyc(A, passes=2):
    c = A[:, :-1].astype(np.float32)
    for _ in range(passes):
        c = 0.25 * np.roll(c, 1, axis=1) + 0.5 * c + 0.25 * np.roll(c, -1, axis=1)
        up = np.concatenate([c[:1], c[:-1]], axis=0)
        dn = np.concatenate([c[1:], c[-1:]], axis=0)
        c = 0.25 * up + 0.5 * c + 0.25 * dn
    return np.concatenate([c, c[:, :1]], axis=1)


def zone_field(Fv, r_fine, photo, N, theta_s, pitch, border_m, r_hub_solid=0.045, thr=0.0, open_m=0.0035):
    """
    Polierte Fläche (Blau) = einfaches Graustufen-Mapping: jeder Punkt des Fotos, dessen Helligkeit (relativ zur Felge: 0 = dunkelste, 1 = hellste Stelle) >= thr ist, ist hell/poliert.
    Über die N Speichen wird das 70. Perzentil genommen (Licht und Spiegelungen sind je Speiche verschieden), leicht entrauscht.
    Rückgabe (Zv, info); Zv = None, wenn (fast) nichts oder (fast) alles hell ist.
    """
    from . import core
    n_r, C = Fv.shape
    frac = np.linspace(0.0, 1.0, C)
    R, Fg = np.meshgrid(r_fine, frac, indexing="ij")
    gray = np.asarray(photo["gray"], np.float64)
    vals = np.zeros((N,) + R.shape)
    for k in range(N):
        th = theta_s + (Fg + k) * pitch
        vals[k] = core.bilinear(gray, photo["cx"] + R / photo["R_out"] * photo["rx"] * np.sin(th),
                                photo["cy"] + R / photo["R_out"] * photo["ry"] * np.cos(th))
    br = np.percentile(vals, 70, axis=0)                               # nur für Schwelle/Kennwerte (Licht ist je Speiche verschieden); die Entscheidung fällt per Abstimmung
    mat = (Fv >= 0.5)
    solid = mat & (R > r_hub_solid + 0.008)
    if solid.sum() < 100:
        return None, dict(bimodal=False, bright=0.0)
    lo, hi = float(np.percentile(br[solid], 10)), float(np.percentile(br[solid], 95))
    if hi < 0.45 or hi - lo < 0.25:                                    # keine helle Fläche im Foto (schwarz/matt/einfarbig): kein Diamond Cut
        return None, dict(bimodal=False, bright=float(np.mean(br[solid])), share=0.0)
    nrm = np.clip((br - lo) / (hi - lo), 0.0, 1.0)                     # Graustufen relativ zur Felge: 0 % = dunkelste, 100 % = hellste Stelle
    if thr <= 0:                                                       # 0 = automatisch: Schwelle zwischen den zwei Helligkeitsgruppen (Otsu)
        thr = 0.7 * float(_otsu(nrm[solid])[0])                      # bewusst großzügig: alles, was nicht schwarz ist, ist Diamond Cut (Schwarz/Weiß-Bild)
    votes = sum((np.clip((vals[k] - lo) / (hi - lo), 0.0, 1.0) >= thr).astype(np.int32) for k in range(N))
    for need in ((max(N - 1, 1), max((N + 1) // 2, 1)) if N > 2 else (N,)):   # blank nur, wenn in >= N-1 Sektoren blank (Reflexionen sind nicht symmetrisch);
        cls = _blur_cyc((votes >= need).astype(np.float32), 2) >= 0.5          # Rückfall auf die Mehrheit, wenn die strenge Regel (fast) nichts übrig lässt
        ero = _erode_material(cls.astype(np.float32), r_fine, pitch, open_m)   # Öffnen: Glanzkanten dünner als 2 x open_m sind keine Fläche
        cls = (1.0 - _erode_material(1.0 - ero, r_fine, pitch, open_m)) >= 0.5
        if float(np.mean(cls[solid])) >= 0.10:
            break
    share = float(np.mean(cls[solid]))
    b_raw = float(np.mean(br[solid & cls])) if (solid & cls).any() else 0.0
    d_raw = float(np.mean(br[solid & ~cls])) if (solid & ~cls).any() else 0.0
    if b_raw < 0.5 or b_raw - d_raw < 0.25:                            # die „helle“ Fläche ist nur ein Glanzlicht (satinschwarz), kein Metall
        return None, dict(bimodal=False, bright=float(np.mean(br[solid])), share=share)
    if share < 0.10 or share > 0.92:                                   # nichts oder fast alles hell: keine Zweifarbigkeit
        return None, dict(bimodal=False, bright=float(np.mean(br[solid])), share=share)
    B = _blur_cyc(cls.astype(np.float32), 2)                          # ruhige Kontur
    E = _blur_cyc(_erode_material(mat, r_fine, pitch, border_m), 1)
    Z = np.minimum(B, E)
    Z[R < r_hub_solid + 0.008] = 0.0
    # Außenrand (Felgenhorn): ist der Ring außerhalb des Käfigs hell (>= thr), wird er mit poliert
    ang = np.linspace(0.0, 2 * math.pi, 360, endpoint=False)
    rr_ = np.linspace(r_fine[-1] + 0.004, photo["R_out"] + 0.02, 18)
    RG, TG = np.meshgrid(rr_, ang, indexing="ij")
    ring = core.bilinear(gray, photo["cx"] + RG / photo["R_out"] * photo["rx"] * np.sin(TG),
                         photo["cy"] + RG / photo["R_out"] * photo["ry"] * np.cos(TG))
    ring_b = float(np.max(np.median(ring, axis=1)))
    bgr = np.linspace(1.10, 1.18, 3) * photo["R_out"]                          # Hintergrund knapp außerhalb: ist der „Ring“ so hell wie er, ist er Hintergrund
    BG, TB = np.meshgrid(bgr, ang, indexing="ij")
    bg_b = float(np.median(core.bilinear(gray, photo["cx"] + BG / photo["R_out"] * photo["rx"] * np.sin(TB),
                                         photo["cy"] + BG / photo["R_out"] * photo["ry"] * np.cos(TB))))
    return Z.astype(np.float32), dict(bimodal=True, bright=b_raw, dark=d_raw, ring=ring_b, horn=bool((ring_b - lo) / (hi - lo) >= thr and ring_b - bg_b >= 0.12), bg=bg_b, share=share, thr=thr, lo=lo, hi=hi, need=need, gray_thr=float(lo + thr * (hi - lo)),
                                      raw=(cls & mat & (R > r_hub_solid + 0.008)))


_DEBUG_BAND = False


def _zone_band(Zf, at_, bt_, ea, eb, r_fine, pitch, raw, min_border):
    """
    Polierte Fläche = Band zwischen zwei GERADEN Kanten, die an die helle Fläche im Foto angepasst sind (Ausgleichsgerade je Kante),
    mit geradem Ende bei konstantem Radius; die Kanten laufen ungeändert bis zum Rand durch. Zf: Foto-Klassifikation (Winkel f).
    Rückgabe (Feld in (r, s), dict(iou, r0, r1)); IoU = Überdeckung mit der hellen Fläche im Foto.
    """
    n_r, C = Zf.shape
    f = np.linspace(0.0, 1.0, C)
    s_ = np.linspace(0.0, 1.0, C)
    ds = s_[1] - s_[0]
    win = (at_ > 0) & (bt_ < 1)
    lo_f, hi_f = np.full(n_r, np.nan), np.full(n_r, np.nan)
    for i in range(n_r):
        idx = np.flatnonzero(Zf[i] >= 0.5)
        if len(idx) and win[i]:
            lo_f[i], hi_f[i] = f[idx[0]], f[idx[-1]]
    ok = ~np.isnan(lo_f)
    if ok.sum() < 8:
        return None, dict(iou=0.0)
    rr = r_fine
    wid = hi_f - lo_f
    good = ok & (wid >= 0.7 * np.nanmedian(wid[ok]))
    gi = np.flatnonzero(good)
    i0 = int(gi[0])
    i1 = int(np.flatnonzero(win)[-1])
    use = [i for i in gi if i <= i1]
    u_lo, u_hi = lo_f * rr * pitch, hi_f * rr * pitch                   # Bogenlänge quer zur Speiche (m)
    fits = []
    for u in (u_lo, u_hi):
        sel = np.array(use)
        for _ in range(3):                                              # Ausreißer (Spiegelungen, Enden) ausschließen
            p_ = np.polyfit(rr[sel], u[sel], 1)
            res = np.abs(np.polyval(p_, rr[sel]) - u[sel])
            keep = res <= max(3.0 * np.median(res), 0.0015)
            if keep.sum() < 6:
                break
            sel = sel[keep]
        fits.append(p_)
    f_lo, f_hi = np.full(n_r, np.nan), np.full(n_r, np.nan)
    for i in range(i0, n_r):
        lo_, hi_ = np.polyval(fits[0], rr[i]) / (rr[i] * pitch), np.polyval(fits[1], rr[i]) / (rr[i] * pitch)
        if win[i]:                                                       # nie in die Außenkontur hinein
            off = min_border / (rr[i] * pitch)
            lo_, hi_ = max(lo_, at_[i] + off), min(hi_, bt_[i] - off)
        f_lo[i], f_hi[i] = lo_, hi_
    out = np.zeros_like(Zf)
    for i in range(i0, n_r):
        if f_hi[i] <= f_lo[i]:
            continue
        w_ = max(eb[i] - ea[i], 1e-6)
        s_lo, s_hi = min(max((f_lo[i] - ea[i]) / w_, 0.0), 1.0), min(max((f_hi[i] - ea[i]) / w_, 0.0), 1.0)
        if s_hi > s_lo + ds:
            out[i] = np.clip(0.5 + np.minimum(s_ - s_lo, s_hi - s_) / (2.0 * ds), 0.0, 1.0)
    band = np.zeros((n_r, C), bool)
    for i in range(i0, i1 + 1):
        band[i] = (f >= f_lo[i]) & (f <= f_hi[i])
    ref = (raw > 0.5) & (np.arange(n_r)[:, None] >= i0) & (np.arange(n_r)[:, None] <= i1)
    iou = float(np.sum(band & ref)) / max(float(np.sum(band | ref)), 1.0)
    return out, dict(iou=iou, r0=float(rr[i0]), r1=float(rr[i1]), d=min_border)


def overlay_array(rgb, cage, cx, cy, rx, ry, R_out, gray=None):
    """Foto mit Käfig-Abgleich: Blau = Diamond-Cut-Flächen, Cyan = Grenze poliert/schwarz (Crease), Orange = Außenkontur, für alle N Speichen."""
    H, W = rgb.shape[:2]
    ov = np.asarray(rgb, np.float32).copy()
    r, f = np.asarray(cage["r"]), np.asarray(cage["f"])
    faces, dia = cage["faces"], np.asarray(cage["diamond"])
    chords = {tuple(sorted(c)) for c in cage["chords"]}
    pitch, ts, N = cage["pitch"], cage["theta_s"], int(cage["N"])
    seam = (f < 1e-9) | (f > 1 - 1e-9)
    cnt = {}
    for fc in faces:
        for q in range(len(fc)):
            e = tuple(sorted((fc[q], fc[(q + 1) % len(fc)])))
            cnt[e] = cnt.get(e, 0) + 1
    blue = np.array([40.0, 110.0, 255.0])
    if gray is not None and cage.get("horn_polished"):                      # Felgenhorn (Ring außerhalb des Käfigs) als poliert gewertet: hellblau
        yy, xx = np.mgrid[0:H, 0:W]
        rad = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) * R_out
        ring = (rad > cage["r_cage_out"] + 0.002) & (rad < R_out * 1.05) & (np.asarray(gray) >= cage["gray_thr"])
        ov[ring] = 0.5 * ov[ring] + 0.5 * np.array([120.0, 190.0, 255.0])
    for k in range(N):
        th = ts + (f + k) * pitch + (cage.get("copy_dtheta") or [0.0] * N)[k]
        rk = r * (1.0 + (cage.get("copy_eps") or [0.0] * N)[k])
        X, Y = cx + rk / R_out * rx * np.sin(th), cy + rk / R_out * ry * np.cos(th)
        for fc, d in zip(faces, dia):
            if not d:
                continue
            for q in range(1, len(fc) - 1):
                a, b, c = fc[0], fc[q], fc[q + 1]
                x0, x1 = int(max(min(X[a], X[b], X[c]), 0)), int(min(max(X[a], X[b], X[c]) + 1, W - 1))
                y0, y1 = int(max(min(Y[a], Y[b], Y[c]), 0)), int(min(max(Y[a], Y[b], Y[c]) + 1, H - 1))
                if x1 < x0 or y1 < y0:
                    continue
                gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
                den = (Y[b] - Y[c]) * (X[a] - X[c]) + (X[c] - X[b]) * (Y[a] - Y[c])
                if abs(den) < 1e-9:
                    continue
                l1 = ((Y[b] - Y[c]) * (gx - X[c]) + (X[c] - X[b]) * (gy - Y[c])) / den
                l2 = ((Y[c] - Y[a]) * (gx - X[c]) + (X[a] - X[c]) * (gy - Y[c])) / den
                m = (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
                ov[y0:y1 + 1, x0:x1 + 1][m] = 0.55 * ov[y0:y1 + 1, x0:x1 + 1][m] + 0.45 * blue
        for e, c_ in cnt.items():
            a, b = e
            if e in chords:
                col = (0.0, 230.0, 230.0)
            elif c_ == 1 and not (seam[a] and seam[b]):
                col = (255.0, 140.0, 0.0)
            else:
                continue
            n = int(max(abs(X[a] - X[b]), abs(Y[a] - Y[b])) * 1.5) + 2
            t = np.linspace(0, 1, n)
            xs = np.clip((X[a] + (X[b] - X[a]) * t).astype(int), 0, W - 1)
            ys = np.clip((Y[a] + (Y[b] - Y[a]) * t).astype(int), 0, H - 1)
            ov[ys, xs] = col
    return ov


_BARY = {}
USE_DEPTH_RULE = False       # Teller-Regel über die KI-Tiefenkarte (nur wirksam, wenn die Tiefenkarte vorliegt)


def _bary_points(n):
    """Schwerpunkte der n*n Teildreiecke eines Dreiecks (Baryzentrisch u, v)."""
    v = _BARY.get(n)
    if v is None:
        pts = []
        for i in range(n):
            for j in range(n - i):
                pts.append(((i + 1 / 3) / n, (j + 1 / 3) / n))
                if j < n - i - 1:
                    pts.append(((i + 2 / 3) / n, (j + 2 / 3) / n))
        v = np.array(pts)
        _BARY[n] = v
    return v


def classify_faces(r, f, faces, photo, N, theta_s, pitch, lo, hi, thr, depth=None, need=None):
    """
    Klassifikation je Käfigfläche statt je Pixel: Foto-Punkte (~1 mm Raster) in jeder Fläche, in jedem der N Sektoren; je Sektor
    Mehrheitsentscheid (>= 50 % hell), Fläche = blank nur, wenn in >= N-1 Sektoren blank (nicht symmetrische Reflexionen fallen heraus).
    Physikalische Regel: mit Tiefenkarte werden Flächen, die deutlich tiefer als die blanken Flächen liegen, nie blank.
    Rückgabe dict(label (0/1), conf (0..1), votes, deep (bool je Fläche, wegen Tiefe entfernt)).
    """
    from . import core
    nf = len(faces)
    x, y = r * np.cos(f * pitch), r * np.sin(f * pitch)
    P_r, P_f, own = [], [], []
    for i, fc in enumerate(faces):
        for q in range(1, len(fc) - 1):
            a, b, c = fc[0], fc[q], fc[q + 1]
            area = 0.5 * abs((x[b] - x[a]) * (y[c] - y[a]) - (x[c] - x[a]) * (y[b] - y[a]))
            n = int(min(max(math.ceil(math.sqrt(area * 1e6) / 1.0), 1), 14))
            uv = _bary_points(n)
            w0 = 1.0 - uv[:, 0] - uv[:, 1]
            P_r.append(w0 * r[a] + uv[:, 0] * r[b] + uv[:, 1] * r[c])
            P_f.append(w0 * f[a] + uv[:, 0] * f[b] + uv[:, 1] * f[c])
            own.append(np.full(len(uv), i, np.int32))
    P_r, P_f, own = np.concatenate(P_r), np.concatenate(P_f), np.concatenate(own)
    cnt = np.maximum(np.bincount(own, minlength=nf).astype(np.float64), 1.0)
    gray = np.asarray(photo["gray"], np.float64)
    dep = np.asarray(depth, np.float64) if depth is not None else None

    def sample(k, dth, eps=0.0):
        th = theta_s + (P_f + k) * pitch + dth
        rr_ = P_r * (1.0 + eps)
        px = photo["cx"] + rr_ / photo["R_out"] * photo["rx"] * np.sin(th)
        py = photo["cy"] + rr_ / photo["R_out"] * photo["ry"] * np.cos(th)
        g = core.bilinear(gray, px, py)
        return np.clip((g - lo) / (hi - lo), 0.0, 1.0), px, py

    def fractions(dth, eps):
        fr = np.zeros((N, nf))
        for k in range(N):
            nn, _, _ = sample(k, dth[k], eps[k])
            fr[k] = np.bincount(own, weights=(nn >= thr).astype(np.float64), minlength=nf) / cnt
        return fr
    dtheta, eps_k = np.zeros(N), np.zeros(N)
    frac = fractions(dtheta, eps_k)
    if N > 1:                                                           # Registrierung je Sektor: Foto ist nie perfekt N-fach symmetrisch
        cand = np.radians(np.arange(-1.6, 1.61, 0.1))
        cand_e = np.arange(-0.015, 0.0151, 0.0025)
        for _ in range(2):
            lab_ = ((frac >= 0.5).sum(axis=0) >= (max(N - 1, 1) if need is None else need))
            wb = lab_[own]
            if wb.all() or (~wb).all():
                break
            for k in range(N):
                for _pass in range(2):                                  # Drehung und Radius abwechselnd (Koordinatenabstieg)
                    best, bd = -9.0, dtheta[k]
                    for dth in cand:
                        nn, _, _ = sample(k, dth, eps_k[k])
                        sc = float(np.mean(nn[wb]) - np.mean(nn[~wb]))
                        if sc > best + 1e-9:
                            best, bd = sc, dth
                    dtheta[k] = bd
                    best, be = -9.0, eps_k[k]
                    for e in cand_e:
                        nn, _, _ = sample(k, dtheta[k], e)
                        sc = float(np.mean(nn[wb]) - np.mean(nn[~wb]))
                        if sc > best + 1e-9:
                            best, be = sc, e
                    eps_k[k] = be
            frac = fractions(dtheta, eps_k)
    dsum = np.zeros(nf)
    if dep is not None:
        for k in range(N):
            _, px, py = sample(k, dtheta[k], eps_k[k])
            dsum += np.bincount(own, weights=core.bilinear(dep, px, py), minlength=nf) / cnt
    votes = (frac >= 0.5).sum(axis=0)
    need = max(N - 1, 1) if need is None else need
    label = (votes >= need)
    agree = np.maximum(votes, N - votes) / float(N)
    conf = np.mean(np.abs(2 * frac - 1.0), axis=0) * agree
    deep = np.zeros(nf, bool)
    if depth is not None and USE_DEPTH_RULE and label.sum() >= 5:       # Teller-Regel: blank nur auf der obersten Ebene
        dface = dsum / N
        ref = dface[label]
        top = float(np.median(ref))
        mad = float(np.median(np.abs(ref - top)))
        tol = max(4.0 * mad, 0.02)
        deep = label & (dface < top - tol)
        label = label & ~deep
    return dict(label=label.astype(np.int8), conf=conf, votes=votes.astype(np.int32), deep=deep, dtheta=dtheta, eps=eps_k)


def _conf_share(r, f, faces, conf, pitch, lim=0.6):
    """Flächenanteil der Käfigflächen mit sicherer Zuordnung (Konfidenz >= lim)."""
    x, y = r * np.cos(f * pitch), r * np.sin(f * pitch)
    area = np.array([0.5 * abs(np.sum(x[fc] * np.roll(y[fc], -1) - np.roll(x[fc], -1) * y[fc])) for fc in faces])
    return float(np.sum(area[np.asarray(conf) >= lim]) / max(np.sum(area), 1e-12))


def zone_iou(r, f, faces, diamond, r_fine, raw):
    """Abgleich Blau (Diamond-Cut-Flächen des Käfigs) gegen Weiß (helle Fläche im Foto) im Sektor-Raster: Überdeckung IoU."""
    n_r, C = raw.shape
    r0, r1 = r_fine[0], r_fine[-1]
    X = np.asarray(f) * (C - 1)
    Y = (np.asarray(r) - r0) / (r1 - r0) * (n_r - 1)
    M = np.zeros((n_r, C), bool)
    for fc, d in zip(faces, diamond):
        if not d:
            continue
        for k in range(1, len(fc) - 1):
            a, b, c = fc[0], fc[k], fc[k + 1]
            x0, x1 = int(max(min(X[a], X[b], X[c]), 0)), int(min(max(X[a], X[b], X[c]) + 1, C - 1))
            y0, y1 = int(max(min(Y[a], Y[b], Y[c]), 0)), int(min(max(Y[a], Y[b], Y[c]) + 1, n_r - 1))
            if x1 < x0 or y1 < y0:
                continue
            gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
            den = (Y[b] - Y[c]) * (X[a] - X[c]) + (X[c] - X[b]) * (Y[a] - Y[c])
            if abs(den) < 1e-12:
                continue
            l1 = ((Y[b] - Y[c]) * (gx - X[c]) + (X[c] - X[b]) * (gy - Y[c])) / den
            l2 = ((Y[c] - Y[a]) * (gx - X[c]) + (X[a] - X[c]) * (gy - Y[c])) / den
            M[y0:y1 + 1, x0:x1 + 1] |= (l1 >= -0.02) & (l2 >= -0.02) & (l1 + l2 <= 1.02)
    ref = np.asarray(raw) > 0.5
    return float(np.sum(M & ref)) / max(float(np.sum(M | ref)), 1.0)


def _collapse_short(r, f, faces, diamond, zvert, chords, pitch, tol=0.0052, r_min=0.075, micro=0.0009):
    """Kurze Kanten am Rand (Zacken, Doppellinien) zusammenziehen; Naht und Zonenpunkte bleiben, Nabe bleibt unberührt."""
    n = len(r)
    seam = (f < 1e-9) | (f > 1 - 1e-9)
    parent = list(range(n))
    rr, ff = r.copy(), f.copy()

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for _ in range(3):
        cnt = {}
        for fc in faces:
            for k in range(len(fc)):
                e = tuple(sorted((fc[k], fc[(k + 1) % len(fc)])))
                cnt[e] = cnt.get(e, 0) + 1
        bverts = set()
        for e, c_ in cnt.items():
            if c_ == 1:
                bverts.update(e)
        x, y = rr * np.cos(ff * pitch), rr * np.sin(ff * pitch)
        cand = []
        for (a, b), c_ in cnt.items():
            if seam[a] or seam[b]:
                continue
            L = math.hypot(x[a] - x[b], y[a] - y[b])
            if L < micro:                                          # Haarlinien-Kanten (< Verschweißabstand) überall zusammenziehen
                cand.append((L, a, b))
            elif (a in bverts or b in bverts) and rr[a] > r_min and rr[b] > r_min and bool(zvert[a]) == bool(zvert[b]) and L < tol:
                cand.append((L, a, b))
        if not cand:
            break
        used = set()
        for L, a, b in sorted(cand):
            if a in used or b in used:
                continue
            used.update((a, b))
            parent[b] = a
            rr[a], ff[a] = 0.5 * (rr[a] + rr[b]), 0.5 * (ff[a] + ff[b])
            zvert[a] = bool(zvert[a]) or bool(zvert[b])
        new_faces, new_dia = [], []
        seen = set()
        for fc, dflag in zip(faces, diamond):
            q = [root(v) for v in fc]
            q = [v for k, v in enumerate(q) if v != q[k - 1]]
            if len(q) < 3 or len(set(q)) < len(q):
                continue
            key = tuple(sorted(q))
            if key in seen:
                continue
            seen.add(key)
            new_faces.append(q)
            new_dia.append(dflag)
        faces, diamond = new_faces, new_dia
        chords = [(root(a), root(b)) for a, b in chords]
        chords = [(a, b) for a, b in chords if a != b]
    used = np.zeros(n, bool)
    for fc in faces:
        used[fc] = True
    remap = -np.ones(n, np.int64)
    remap[used] = np.arange(used.sum())
    faces = [remap[fc].tolist() for fc in faces]
    chords = [(int(remap[a]), int(remap[b])) for a, b in chords if remap[a] >= 0 and remap[b] >= 0]
    return rr[used], ff[used], faces, np.array(diamond, np.int8), np.asarray(zvert)[used], chords


def _envelope(Fv, r_fine, ramp_m=0.010):
    """
    Je Zeile: Anfang a und Ende b des Materials (Winkelanteil f, Nahtfenster ausgenommen). Nahtzeilen mit Material: a=0, b=1.
    An den Fenster-Enden (Spitze zur Nabe, Bogen zum Felgenring) geht das Speichengitter über `ramp_m` weich ins normale Gitter über.
    Rückgabe a_eff, b_eff, has, exact (exact: Gitterrand liegt genau auf der Silhouette).
    """
    n_r, C = Fv.shape
    f = np.linspace(0.0, 1.0, C)
    a, b = np.zeros(n_r), np.ones(n_r)
    has = np.ones(n_r, bool)
    for i in range(n_r):
        row = Fv[i] >= 0.5
        if row[0] and row[-1]:
            continue
        idx = np.flatnonzero(row)
        if len(idx) == 0:
            a[i], b[i], has[i] = 0.49, 0.51, False
            continue
        j0, j1 = idx[0], idx[-1]
        a[i] = f[j0 - 1] + (0.5 - Fv[i, j0 - 1]) / max(Fv[i, j0] - Fv[i, j0 - 1], 1e-6) * (f[1] - f[0]) if j0 > 0 else 0.0
        b[i] = f[j1] + (Fv[i, j1] - 0.5) / max(Fv[i, j1] - Fv[i, j1 + 1], 1e-6) * (f[1] - f[0]) if j1 < C - 1 else 1.0
    a = np.where(a < 0.004, 0.0, a)
    b = np.where(b > 0.996, 1.0, b)
    one = (a > 0) != (b < 1)                            # nur einseitig geschnitten: Zeile voll lassen, damit die Naht (f = 0 und 1) zusammenpasst
    a, b = np.where(one, 0.0, a), np.where(one, 1.0, b)
    b = np.maximum(b, a + 0.02)
    pos = (a > 0) | (b < 1)
    a_true, b_true = a.copy(), b.copy()
    a_eff, b_eff = a.copy(), b.copy()
    i = 0
    while i < n_r:
        if not pos[i]:
            i += 1
            continue
        j = i
        while j < n_r and pos[j]:
            j += 1
        L = min(ramp_m, 0.4 * (r_fine[j - 1] - r_fine[i])) if ramp_m > 0 else 1e-9
        for k in range(i, j):
            u1 = min(max((r_fine[k] - r_fine[i]) / max(L, 1e-6), 0.0), 1.0)
            u2 = min(max((r_fine[j - 1] - r_fine[k]) / max(L, 1e-6), 0.0), 1.0)
            w = (u1 * u1 * (3 - 2 * u1)) * (u2 * u2 * (3 - 2 * u2))
            a_eff[k], b_eff[k] = a[k] * w, 1.0 - (1.0 - b[k]) * w
        i = j
    exact = has & (a_eff >= a - 1e-9) & (b_eff <= b + 1e-9)
    return a_eff, b_eff, has, exact, a_true, b_true


def _warp(Fv, r_fine, a, b):
    """Feld in (r, s): s = 0..1 läuft über das Material von a(r) bis b(r); Spokenkanten werden zu Gitterlinien."""
    n_r, C = Fv.shape
    s = np.linspace(0.0, 1.0, C)
    fm = a[:, None] + (b - a)[:, None] * s[None, :]
    R = np.repeat(r_fine[:, None], C, axis=1)
    return _fine_sampler(Fv, r_fine)(R, fm), fm


def _band_zone(Zs, ea, eb, passes=24):
    """Polierte Fläche je Zeile als ein Band [lo, hi] in s, entlang r geglättet (Kontur parallel zur Speichenkante)."""
    n_r, C = Zs.shape
    s = np.linspace(0.0, 1.0, C)
    ds = s[1] - s[0]
    lo, hi = np.full(n_r, np.nan), np.full(n_r, np.nan)
    raw = np.zeros(n_r, bool)
    for i in range(n_r):
        idx = np.flatnonzero(Zs[i] >= 0.5)
        if len(idx) == 0:
            continue
        lo[i], hi[i] = s[idx[0]] - 0.5 * ds, s[idx[-1]] + 0.5 * ds
    wid = hi - lo
    ok = ~np.isnan(wid)
    if ok.any():
        full = ok & (wid >= 0.7 * np.nanmedian(wid[ok]))              # abgerundete Enden weglassen -> Ende bleibt gerade (konstanter Radius)
        lo[~full], hi[~full] = np.nan, np.nan
    for arr in (lo, hi):
        for _ in range(passes):
            v = np.where(np.isnan(arr), 0.0, arr)
            w = (~np.isnan(arr)).astype(float)
            k = np.array([1.0, 2.0, 1.0])
            num, den = np.convolve(v, k, "same"), np.convolve(w, k, "same")
            new = np.where((den > 0) & (w > 0), num / np.maximum(den, 1e-9), np.nan)
            arr[:] = new
    valid = np.flatnonzero(~np.isnan(lo))
    if len(valid):                                                       # die polierte Fläche läuft nach außen bis zum Rand weiter
        last = valid[-1]
        f_lo, f_hi = ea[last] + lo[last] * (eb[last] - ea[last]), ea[last] + hi[last] * (eb[last] - ea[last])      # gleicher Winkelbereich
        for i in range(last + 1, n_r):
            w_ = max(eb[i] - ea[i], 1e-6)
            lo[i], hi[i] = min(max((f_lo - ea[i]) / w_, 0.0), 1.0), min(max((f_hi - ea[i]) / w_, 0.0), 1.0)
    out = np.zeros_like(Zs)
    for i in range(n_r):
        if raw[i]:
            out[i] = Zs[i]
        elif not np.isnan(lo[i]):
            out[i] = np.clip(0.5 + np.minimum(s - lo[i], hi[i] - s) / (2.0 * ds), 0.0, 1.0)
    return out


CAGE_EXT = 0.013          # Käfig reicht über den Innenrand des Felgenbetts hinaus (Speichenspitzen bis zum Horn, wie im Foto)


def build_cage(F, radii, photo, N, theta_s, r_ref_face, relief_mm=4.0, relief_width_mm=40.0, boss_mm=6.0, boss_r_mm=75.0,
               spoke_t_mm=14.0, hub_t_mm=24.0, hub_r_mm=85.0, r_a=0.012, r_hub_solid=0.045, crease_top=1.0,
               border_mm=6.0, max_area_err=0.05, zone_target=0.93, diamond_thr=0.0):
    """
    Bearbeitbarer Käfig des Pizzastücks für Subdivision Surface (ohne KI-Mesh): grobes Netz entlang der Silhouette (Fenster, Löcher),
    Rücken/Bund aus dem Randabstand, Dicke aus Nabe/Speiche. Die Diamond-Cut-Fläche (Zweifarbigkeit aus dem Foto) ist eine eigene
    Fläche des Käfigs: eine Kantenschleife (Crease 1) grenzt sie ab, ihre Punkte werden per Geometry Nodes auf den Teller (Drehfläche z = f(r)) gelegt – so kann der Fräser bei drehender Felge gleichmäßig abtragen.
    """
    from . import core
    pitch = 2 * math.pi / N
    r_out = r_ref_face + CAGE_EXT                                           # äußerer Käfigrand
    r_fine = r_a + (r_out - r_a) * np.linspace(0.0, 1.0, 161)
    Fv, sym = sector_field(F, radii, N, theta_s, r_fine, 145)
    Fv[r_fine < r_hub_solid, :] = 1.0
    fine_area = float(np.sum((Fv[:-1, :-1] >= 0.5) * r_fine[:-1, None] * (r_fine[1] - r_fine[0]) * (pitch / 144.0)))
    # Gitter entlang der Speiche: s läuft von der linken zur rechten Silhouettenkante, die Linien des Käfigs folgen der Außenkontur
    ea, eb, has, exact, at_, bt_ = _envelope(Fv, r_fine)
    Fs, _fm = _warp(Fv, r_fine, ea, eb)
    Fs[:, 0] = np.where(exact, 1.0, Fs[:, 0])
    Fs[:, -1] = np.where(exact, 1.0, Fs[:, -1])

    def true_f(r_, s_):
        a_, b_ = np.interp(r_, r_fine, ea), np.interp(r_, r_fine, eb)
        a_ = np.where(a_ < 0.004, 0.0, a_)                       # Naht exakt bei f = 0 / 1 (Verschweißen)
        b_ = np.where(b_ > 0.996, 1.0, b_)
        return a_ + (b_ - a_) * s_
    # Zeilenradien: gleichmäßig grob, an Fensterspitze und Fensterende (Übergang zum Ring) feiner
    pos = (ea > 1e-6) | (eb < 1 - 1e-6)
    spans, i = [], 0
    while i < len(pos):
        if pos[i]:
            j = i
            while j < len(pos) and pos[j]:
                j += 1
            spans.append((r_fine[i], r_fine[j - 1]))
            i = j
        else:
            i += 1

    def row_radii(Rc):
        rr_ = list(np.linspace(r_a, r_out, Rc))
        for r0, r1 in spans:
            for lo_, hi_ in ((r0 - 0.008, r0 + 0.040), (r1 - 0.040, r1 + 0.010)):
                rr_ += list(np.arange(max(lo_, r_a), min(hi_, r_out), 0.0055))
        rr_ = sorted(set(round(v, 5) for v in rr_ + [r_out]))
        out_ = [rr_[0]]
        for v in rr_[1:]:
            if v - out_[-1] > 0.0028:
                out_.append(v)
        out_[-1] = r_out
        return np.array(out_)
    best = None
    for Rc, Cc in ((14, 9), (18, 11), (24, 14), (32, 18), (48, 26), (64, 34), (84, 44)):
        rows = row_radii(Rc)
        m = cage_mesh(Fs, r_fine, Rc, Cc, r_a, r_out, pitch=pitch, rows=rows)
        err = abs(_poly_area(m["r"], true_f(m["r"], m["f"]), m["faces"], pitch) - fine_area) / max(fine_area, 1e-9)
        best = (Rc, Cc, err)
        if err < max_area_err:
            break
    Rc, Cc, err = best
    spoke_w = float(np.median((eb - ea)[r_fine > 0.09]))
    cell = 0.5 * (r_out + r_a) * pitch * max(spoke_w, 0.2) / (Cc - 1)        # Zellbreite quer zur Speiche (m)
    margin = max(border_mm / 1000.0, 1.2 * cell)                         # Zone liegt in vollen Zellen (Rahmen um die polierte Fläche)
    Zv, zinfo = zone_field(Fv, r_fine, photo, N, theta_s, pitch, 0.0, thr=diamond_thr)       # Blau = helle Fläche im Foto (1:1, keine Erosion)
    if _DEBUG_BAND and Zv is not None:
        for i in range(0, len(r_fine), 8):
            print('ZDBG r=%.0f mat=%.2f raw=%.2f Z=%.2f' % (1000 * r_fine[i], np.mean(Fv[i] >= 0.5), np.mean(zinfo['raw'][i]), np.mean(Zv[i] >= 0.5)))
    if Zv is not None:
        Zv, _ = _warp(Zv, r_fine, ea, eb)
    ladder = [(R_, C_) for R_, C_ in ((14, 9), (18, 11), (24, 14), (32, 18), (48, 26)) if C_ >= Cc]
    z_iou = None
    for Rc, Cc in ladder:                                                # feiner werden, bis Blau das Weiß im Foto abdeckt (schmale Streifen)
        m = cage_mesh(Fs, r_fine, Rc, Cc, r_a, r_out, Zv=Zv, pitch=pitch, rows=row_radii(Rc))
        r, faces = m["r"], m["faces"]
        f = true_f(r, m["f"])
        f[np.abs(f) < 1e-9] = 0.0
        r, f, faces, m["diamond"], m["zvert"], m["chords"] = _collapse_short(r, f, faces, m["diamond"], m["zvert"], m["chords"], pitch)
        if Zv is None:
            break
        fc_res = classify_faces(r, f, faces, photo, N, theta_s, pitch, zinfo["lo"], zinfo["hi"], zinfo["thr"], photo.get("depth"), zinfo.get("need"))
        m["diamond"] = fc_res["label"]
        zv_ = np.zeros(len(r), bool)                                     # Teller-Punkte: Ecken blanker Flächen
        for fc_, d_ in zip(faces, fc_res["label"]):
            if d_:
                zv_[fc_] = True
        m["zvert"] = zv_
        z_iou = zone_iou(r, f, faces, m["diamond"], r_fine, zinfo["raw"])
        if z_iou >= zone_target:
            break
    seam = (f < 1e-9) | (f > 1 - 1e-9)
    diamond, zvert, chords = m["diamond"], m["zvert"], m["chords"]
    n = len(r)
    # --- Höhen: Rücken (Abstand zum Rand), Nabenbund, Dicke
    d = _boundary_distance(r, f, faces, seam, pitch)
    nb = [set() for _ in range(n)]
    for fc in faces:
        for a in fc:
            nb[a].update(fc)
    dmed = d.copy()
    for _ in range(6):
        dmed = np.array([max(dmed[a], max(dmed[b] for b in nb[a])) for a in range(n)])
    dmax = np.minimum(np.maximum(dmed, 1e-4), relief_width_mm / 1000.0)
    t = np.clip(d / dmax, 0.0, 1.0)
    top = relief_mm / 1000.0 * (1.0 - (1.0 - t) ** 2.2)
    u = np.clip((boss_r_mm / 1000.0 - r) / 0.015, 0.0, 1.0)
    top = top + boss_mm / 1000.0 * u * u * (3 - 2 * u)
    # Diamond-Cut-Fläche: die Höhe kommt später aus dem Teller (Drehfläche, Geometry Nodes); hier nur die Standard-Tellerkontur
    teller_h = [(0.0, 0.0), (1.0, 0.0)]
    if True:
        u = r / r_ref_face
        edges_u = np.linspace(0.3, 1.0, 8)
        pts = []
        base = zvert if (Zv is not None and zvert.sum() > 10) else np.ones(len(r), bool)       # sonst: ganze Oberseite
        for a_, b_ in zip(edges_u[:-1], edges_u[1:]):
            sel = base & (u >= a_) & (u < b_)
            if sel.sum() >= 3:
                pts.append((float(0.5 * (a_ + b_)), float(np.median(top[sel]))))
        if len(pts) >= 2:
            teller_h = [(0.0, pts[0][1])] + pts + [(1.0, pts[-1][1])]
    s_of = np.clip((r_ref_face - r) / (r_ref_face - hub_r_mm / 1000.0), 0.0, 1.0)
    thick = (spoke_t_mm + (hub_t_mm - spoke_t_mm) * s_of) / 1000.0
    for arr in (top, thick):                              # Nahtpaare gleich (Verschweißen)
        idx = np.where(seam)[0]
        key = np.round(r[idx] * 1e6).astype(np.int64)
        for kv in np.unique(key):
            g = idx[key == kv]
            if len(g) > 1:
                arr[g] = arr[g].mean()
    half = 0.5 * pitch
    phi0 = math.pi / 2 - (theta_s + half)
    bright_all = (not zinfo["bimodal"]) and zinfo.get("bright", 0.0) > 0.55
    return dict(r=r, f=f, faces=faces, seam=seam, top=top, bot=-thick, zone=np.zeros(n), diamond=diamond if Zv is not None else
                (np.ones(len(faces), np.int8) if bright_all else np.zeros(len(faces), np.int8)), chords=chords,
                N=int(N), pitch=pitch, theta_s=theta_s, crease_top=crease_top, drehung_deg=math.degrees((phi0 + math.pi) % (2 * math.pi) - math.pi),
                sym=sym, horn_polished=bool(zinfo.get("horn", False)), gray_thr=float(zinfo.get("gray_thr", 0.0)), r_cage_out=float(r_out), bimodal=bool(zinfo["bimodal"]), zone_iou=float(z_iou) if z_iou is not None else None, conf_share=(_conf_share(r, f, faces, fc_res["conf"], pitch) if Zv is not None else None), face_conf=(fc_res["conf"] if Zv is not None else None), face_votes=(fc_res["votes"] if Zv is not None else None), n_deep=(int(fc_res["deep"].sum()) if Zv is not None else 0), copy_dtheta=([float(v) for v in fc_res["dtheta"]] if Zv is not None else None), copy_eps=([float(v) for v in fc_res["eps"]] if Zv is not None else None), polished=float(np.mean(diamond)) if Zv is not None else float(bright_all),
                area_err=err, cells=(Rc, Cc), zvert=zvert.astype(np.int8), teller_h=teller_h,
                has_zone=bool(Zv is not None and zvert.sum() > 10))
