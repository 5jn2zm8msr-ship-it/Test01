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
    solid = r > r_hub_solid + 0.02
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
    zone[r < r_hub_solid + 0.02] = 0.0
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


def cage_mesh(Fv, r_fine, Rc, Cc, r_a, r_face, iso=0.5):
    """
    Grobes Marching-Squares-Netz (Käfig) auf dem Sektor: Ecken-Zustände aus dem feinen Feld, Randpunkte per Bisektion exakt auf die
    feine Kontur gesetzt (keine Treppenstufen). Gibt (r, f, faces, seam, flags) zurück; faces = Polygone (meist Quads).
    """
    at = _fine_sampler(Fv, r_fine)
    rc = np.linspace(r_a, r_face, Rc)
    fc = np.linspace(0.0, 1.0, Cc)
    R, Fg = np.meshgrid(rc, fc, indexing="ij")
    val = at(R, Fg)
    inside = val >= iso
    pts = {}                                             # Randpunkte: (i, j, kind) -> Index
    rr, ff = list(R.reshape(-1)), list(Fg.reshape(-1))
    n_corner = Rc * Cc

    def edge_pt(i, j, kind):
        key = (i, j, kind)
        v = pts.get(key)
        if v is not None:
            return v
        if kind == 0:                                    # radiale Kante (i,j)-(i+1,j)
            a, b = (rc[i], fc[j]), (rc[i + 1], fc[j])
        else:                                            # Winkelkante (i,j)-(i,j+1)
            a, b = (rc[i], fc[j]), (rc[i], fc[j + 1])
        va, vb = float(val[i, j]), float(val[i + 1, j] if kind == 0 else val[i, j + 1])
        lo, hi = 0.0, 1.0
        for _ in range(12):
            mid = 0.5 * (lo + hi)
            rm, fm = a[0] + mid * (b[0] - a[0]), a[1] + mid * (b[1] - a[1])
            vm = float(at(rm, fm))
            if (vm >= iso) == (va >= iso):
                lo = mid
            else:
                hi = mid
        t = 0.5 * (lo + hi)
        rr.append(a[0] + t * (b[0] - a[0]))
        ff.append(a[1] + t * (b[1] - a[1]))
        pts[key] = n_corner + len(pts)
        return pts[key]
    faces = []
    for i in range(Rc - 1):
        for j in range(Cc - 1):
            ins = [inside[i, j], inside[i, j + 1], inside[i + 1, j + 1], inside[i + 1, j]]
            c = sum(ins)
            if c == 0:
                continue
            if c == 4:
                faces.append([i * Cc + j, i * Cc + j + 1, (i + 1) * Cc + j + 1, (i + 1) * Cc + j])
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
            if len(poly) >= 3:
                faces.append(poly)
    r_all, f_all = np.array(rr), np.array(ff)
    used = np.zeros(len(r_all), bool)
    for f in faces:
        used[f] = True
    remap = -np.ones(len(r_all), np.int64)
    remap[used] = np.arange(used.sum())
    faces = [remap[f].tolist() for f in faces]
    r, f = r_all[used], f_all[used]
    seam = (f < 1e-9) | (f > 1 - 1e-9)
    return r, f, faces, seam


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


def build_cage(F, radii, photo, N, theta_s, r_ref_face, relief_mm=4.0, relief_width_mm=40.0, boss_mm=6.0, boss_r_mm=75.0,
               spoke_t_mm=14.0, hub_t_mm=24.0, hub_r_mm=85.0, r_a=0.012, r_hub_solid=0.045, crease_top=0.7):
    """
    Bearbeitbarer Käfig des Pizzastücks für Subdivision Surface (ohne KI-Mesh): grobes Netz entlang der Silhouette (Fenster,
    Löcher), Rücken/Bund aus dem Abstand zum Rand, Dicke aus Nabe/Speiche, Zweifarbigkeit (weich) aus dem Foto.
    Auflösung steigt automatisch, bis die Käfigfläche die feine Silhouette auf 3 % trifft (dünne Speichen).
    """
    from . import core
    pitch = 2 * math.pi / N
    r_fine = r_a + (r_ref_face - r_a) * np.linspace(0.0, 1.0, 161)
    Fv, sym = sector_field(F, radii, N, theta_s, r_fine, 145)
    Fv[r_fine < r_hub_solid, :] = 1.0
    fine_area = float(np.sum((Fv[:-1, :-1] >= 0.5) * r_fine[:-1, None] * (r_fine[1] - r_fine[0]) * (pitch / 144.0)))
    best = None
    for Rc, Cc in ((36, 20), (48, 26), (64, 34), (84, 44), (110, 58)):
        r, f, faces, seam = cage_mesh(Fv, r_fine, Rc, Cc, r_a, r_ref_face)
        r, f, faces, seam = drop_small(r, f, faces, seam, pitch)
        err = abs(_poly_area(r, f, faces, pitch) - fine_area) / max(fine_area, 1e-9)
        best = (r, f, faces, seam, err, Rc, Cc)
        if err < 0.03:
            break
    r, f, faces, seam, err, Rc, Cc = best
    n = len(r)
    # --- Höhen: Rücken (Abstand zum Rand), Nabenbund, Dicke
    d = _boundary_distance(r, f, faces, seam, pitch)
    nb = [set() for _ in range(n)]
    for fc in faces:
        for a in fc:
            nb[a].update(fc)
    dmed = d.copy()
    for _ in range(6):                                   # lokale halbe Breite ~ größter Randabstand in der Nähe
        dmed = np.array([max(dmed[a], max(dmed[b] for b in nb[a])) for a in range(n)])
    dmax = np.minimum(np.maximum(dmed, 1e-4), relief_width_mm / 1000.0)
    t = np.clip(d / dmax, 0.0, 1.0)
    top = relief_mm / 1000.0 * (1.0 - (1.0 - t) ** 2.2)
    u = np.clip((boss_r_mm / 1000.0 - r) / 0.015, 0.0, 1.0)
    top = top + boss_mm / 1000.0 * u * u * (3 - 2 * u)
    s_of = np.clip((r_ref_face - r) / (r_ref_face - hub_r_mm / 1000.0), 0.0, 1.0)
    thick = (spoke_t_mm + (hub_t_mm - spoke_t_mm) * s_of) / 1000.0
    for arr in (top, thick):                              # Nahtpaare gleich (Verschweißen)
        idx = np.where(seam)[0]
        key = np.round(r[idx] * 1e6).astype(np.int64)
        for kv in np.unique(key):
            g = idx[key == kv]
            if len(g) > 1:
                arr[g] = arr[g].mean()
    # --- Zweifarbigkeit (weich) aus dem Foto, Median über alle N Sektoren
    theta = theta_s + f * pitch
    vals = np.zeros((N, n))
    gray = np.asarray(photo["gray"], np.float64)
    for k in range(N):
        tt = theta + k * pitch
        vals[k] = core.bilinear(gray, photo["cx"] + r / photo["R_out"] * photo["rx"] * np.sin(tt),
                                photo["cy"] + r / photo["R_out"] * photo["ry"] * np.cos(tt))
    br = np.median(vals, axis=0)
    solid = r > r_hub_solid + 0.02
    lo, hi = (np.percentile(br[solid], 5), np.percentile(br[solid], 95)) if solid.sum() > 30 else (0.0, 1.0)
    nrm = np.clip((br - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    thr, var = _otsu(nrm[solid]) if solid.sum() > 30 else (0.5, 0.0)
    cls = nrm > thr
    bright_raw = float(np.mean(br[solid & cls])) if (solid & cls).any() else 0.0
    dark_raw = float(np.mean(br[solid & ~cls])) if (solid & ~cls).any() else 0.0
    bimodal = bool(var > 0.03 and bright_raw >= 0.5 and bright_raw - dark_raw >= 0.22)
    if bimodal:
        zone = np.clip((nrm - thr) * 4.0 + 0.5, 0.0, 1.0)
        zone = core.smooth_on_mesh(zone, faces, n, 4)
    else:
        zone = np.full(n, 1.0 if (solid.any() and float(np.mean(br[solid])) > 0.55) else 0.0)
    zone[r < r_hub_solid + 0.02] = 0.0
    half = 0.5 * pitch
    phi0 = math.pi / 2 - (theta_s + half)
    return dict(r=r, f=f, faces=faces, seam=seam, top=top, bot=-thick, zone=zone, N=int(N), pitch=pitch, theta_s=theta_s,
                crease_top=crease_top, drehung_deg=math.degrees((phi0 + math.pi) % (2 * math.pi) - math.pi), sym=sym,
                bimodal=bimodal, polished=float(np.mean(zone[solid] > 0.5)) if solid.any() else 0.0, area_err=err, cells=(Rc, Cc))
