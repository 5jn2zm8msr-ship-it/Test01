# SPDX-License-Identifier: GPL-3.0-or-later
"""
Parameter der parametrischen Felge aus dem (bereinigten) Polarfeld des KI-Meshes ableiten – nur Maße/Proportionen,
nicht die Geometrie. F[i, j] = 1 (Material) bei Radius radii[i] (m) und Winkel theta_j = j * 2pi / n_t
(theta zählt im Uhrzeigersinn von +Y; x = r sin(theta), y = r cos(theta)).
"""
import math

import numpy as np


def _runs(row):
    """Zyklische Läufe von True in einem 1D-Bool-Array: Liste (Start, Länge)."""
    n = len(row)
    if row.all() or not row.any():
        return []
    start = int(np.argmin(row))                       # ein False-Index als Anker
    rolled = np.roll(row, -start)
    out, i = [], 0
    while i < n:
        if rolled[i]:
            j = i
            while j < n and rolled[j]:
                j += 1
            out.append(((i + start) % n, j - i))
            i = j
        else:
            i += 1
    return out


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def _material_at(Frow, theta, n_t):
    """Material (0..1) einer Polarzeile bei beliebigen Winkeln theta (rad), zyklisch interpoliert."""
    x = (np.asarray(theta) / (2 * math.pi) * n_t) % n_t
    i0 = np.floor(x).astype(int) % n_t
    i1 = (i0 + 1) % n_t
    f = x - np.floor(x)
    return Frow[i0] * (1 - f) + Frow[i1] * f


def _rdp(xs, ys, tol, max_pts):
    """Ramer-Douglas-Peucker: wenige Stützpunkte, die die Kurve auf tol genau treffen."""
    keep = [0, len(xs) - 1]

    def rec(a, b):
        if b <= a + 1:
            return
        xa, ya, xb, yb = xs[a], ys[a], xs[b], ys[b]
        t = (xs[a + 1:b] - xa) / max(xb - xa, 1e-12)
        err = np.abs(ys[a + 1:b] - (ya + t * (yb - ya)))
        k = int(np.argmax(err))
        if err[k] > tol:
            m = a + 1 + k
            keep.append(m)
            rec(a, m)
            rec(m, b)
    rec(0, len(xs) - 1)
    keep = sorted(set(keep))
    while len(keep) > max_pts:                         # zu viele: kleinsten Beitrag entfernen
        errs = []
        for q in range(1, len(keep) - 1):
            a_, m_, b_ = keep[q - 1], keep[q], keep[q + 1]
            t = (xs[m_] - xs[a_]) / max(xs[b_] - xs[a_], 1e-12)
            errs.append(abs(ys[m_] - (ys[a_] + t * (ys[b_] - ys[a_]))))
        keep.pop(1 + int(np.argmin(errs)))
    return [(float(xs[i]), float(ys[i])) for i in keep]


def default_edges(n, r_face, r_hub, ring, width, bend_deg=0.0, rows=96, r_a=0.012, L=0.03):
    """Standard-Kanten (ohne Foto): runde Fensterenden, gerade Speiche der Breite `width` (m). Gibt (links, rechts) Stützpunkte."""
    half = math.pi / n
    rho = np.linspace(0.0, 1.0, rows)
    r = r_a + (r_face - r_a) * rho
    x1 = np.clip((r - r_hub) / L, 0, 1)
    x2 = np.clip((r - (r_face - ring - L)) / L, 0, 1)
    b = np.sqrt(np.maximum(1 - (1 - x1) ** 2, 0)) * np.sqrt(np.maximum(1 - x2 ** 2, 0))
    hw = np.minimum(0.5 * width / np.maximum(r, 1e-6), 0.92 * half)
    A = half + (hw - half) * b
    t = np.clip((r - 0.8 * r_hub) / (r_face - 0.5 * ring - 0.8 * r_hub), 0, 1)
    c = b * math.radians(bend_deg) * t
    c = np.clip(c, -(0.96 * half - A).clip(min=0), (0.96 * half - A).clip(min=0))
    fL = np.clip((c - A) / (2 * half) + 0.5, 0, 1)
    fR = np.clip((c + A) / (2 * half) + 0.5, 0, 1)
    return _rdp(rho, fL, 0.004, 24), _rdp(rho, fR, 0.004, 24)


def detect(F, radii, r_face, n_sym=0, ring_m=0.012, rows=96, r_a=0.012):
    """
    Leitet das „Pizzastück“ aus dem Polarfeld ab. Ergebnis (dict):
      n, drehung_deg (Mitte des Stücks), edge_l / edge_r (Stützpunkte (rho, f): Speichenkanten über dem Radius; f = Anteil der
      Keilbreite von links nach rechts, 0/1 = ganze Breite = Nabe bzw. Ring), hub_r_mm, ring_mm, wmax_mm, twin, info.
    Der Keil wird so gelegt, dass seine Nähte durch die Fenster laufen (auch bei gebogenen Speichen).
    """
    F = np.asarray(F, np.float64)
    n_r, n_t = F.shape
    dth = 2 * math.pi / n_t
    radii = np.asarray(radii, np.float64)
    frac = (F >= 0.5).mean(axis=1)
    run_n = np.array([len(_runs(F[i] >= 0.5)) for i in range(n_r)])
    wide = np.where((frac < 0.9) & (run_n >= 3))[0]
    if len(wide) < 4:
        detect.why = 'wide'
        return None
    vals, cnts = np.unique(run_n[wide], return_counts=True)
    n_run = int(vals[np.argmax(cnts)])
    twin = False
    if 3 <= n_sym <= 24:
        n = n_sym
        twin = bool(n_run == 2 * n_sym)
    else:
        n = n_run
    if not 3 <= n <= 24:
        detect.why = 'n=%d' % n
        return None
    need = 2 * n if twin else n
    open_idx = np.where(run_n >= max(3, need - max(1, need // 4)))[0]
    if len(open_idx) < 4:
        detect.why = 'open_idx n=%d need=%d' % (n, need)
        return None
    r_open0, r_open1 = float(radii[open_idx[0]]), float(radii[open_idx[-1]])
    pitch = 2 * math.pi / n
    # --- Naht so legen, dass sie in den offenen Zeilen durch ein Fenster läuft (größter Abstand zum Material)
    ro = [i for i in range(n_r) if r_open0 + 0.1 * (r_open1 - r_open0) <= radii[i] <= r_open1 - 0.1 * (r_open1 - r_open0)]
    cand = np.linspace(0.0, pitch, 90, endpoint=False)
    best_s, best_score = 0.0, -1.0
    probe = np.linspace(-0.5 * pitch, 0.5 * pitch, 41)
    for sc in cand:
        score = 1e9
        for i in ro[::2]:
            m = _material_at(F[i], sc + probe, n_t) >= 0.5
            if m[20]:                                   # Naht im Material
                score = -1.0
                break
            idx = np.where(m)[0]
            dmin = np.min(np.abs(idx - 20)) if len(idx) else 20
            score = min(score, float(dmin))
        if score > best_score:
            best_s, best_score = float(sc), score
    s0 = best_s
    # --- Nahtpfad: pro Zeile durch die Mitte des Fensters (Fenster sind nicht immer mittig zur Speiche)
    r_rows = r_a + (r_face - r_a) * np.linspace(0.0, 1.0, rows)
    half = 0.5 * pitch
    seam = np.full(rows, np.nan)

    def row_seam(i_row, prev):
        i = int(np.argmin(np.abs(radii - r_rows[i_row])))
        m = F[i] >= 0.5
        gaps = _runs(~m)
        if not gaps:
            return None
        lens = np.array([g[1] for g in gaps], np.float64)
        best = None
        for (g0, gl) in gaps:
            if gl < 0.25 * lens.max():
                continue
            cg = ((g0 + 0.5 * gl) * dth) % (2 * math.pi)
            d = ((cg - prev + half) % pitch) - half     # Abstand modulo Teilung, in [-half, half)
            if best is None or abs(d) < abs(best[0]):
                best = (d, prev + d)
        return best[1] if best else None

    mid = int(np.argmin(np.abs(r_rows - 0.5 * (r_open0 + r_open1))))
    prev = s0                                           # Startnaht (Mitte eines Fensters)
    seam[mid] = prev
    for rng_ in (range(mid + 1, rows), range(mid - 1, -1, -1)):
        cur = seam[mid]
        for i_row in rng_:
            v = row_seam(i_row, cur)
            if v is not None and r_open0 - 0.01 <= r_rows[i_row] <= r_open1 + 0.01:
                cur = v
                seam[i_row] = v
            else:
                seam[i_row] = np.nan
    # Lücken (Nabe/Ring ohne Fenster): letzten gültigen Wert halten; glätten
    good = ~np.isnan(seam)
    idxs = np.arange(rows)
    seam = np.interp(idxs, idxs[good], seam[good])
    k5 = np.ones(5) / 5.0
    seam = np.convolve(np.pad(seam, 2, mode="edge"), k5, mode="valid")
    seam_ref = float(seam[0])                          # Naht in der Nabe
    # --- Zeilen: Materialhülle im Keil [Naht(r), Naht(r) + Teilung]
    M = 360
    fL_t = np.zeros(rows)
    fR_t = np.ones(rows)
    for k, r in enumerate(r_rows):
        i = int(np.argmin(np.abs(radii - r)))
        th = seam[k] + (np.arange(M) + 0.5) / M * pitch
        m = _material_at(F[i], th, n_t) >= 0.5
        if m.all() or r < 0.045:                        # Nabenmitte (Schrauben-/Schlitzmuster) bleibt voll
            fL_t[k], fR_t[k] = 0.0, 1.0
        elif not m.any():
            fL_t[k], fR_t[k] = 0.49, 0.51
        else:
            idx = np.where(m)[0]
            fL_t[k], fR_t[k] = idx[0] / M, (idx[-1] + 1) / M
    # Naht relativ zum Keil der Nabe: phi = pi/2 - theta, also c = -(seam - seam_ref)
    cfrac = np.clip(0.5 - (seam - seam_ref) / pitch, 0.0, 1.0)
    # theta (im Uhrzeigersinn) -> phi (gegen den Uhrzeigersinn): f_phi_links = 1 - f_theta_rechts
    fL = 1.0 - fR_t
    fR = 1.0 - fL_t
    k3 = np.ones(3) / 3.0                               # Pixelrauschen glätten (Rand unverändert)
    for arr in (fL, fR):
        sm = np.convolve(np.pad(arr, 1, mode="edge"), k3, mode="valid")
        arr[1:-1] = sm[1:-1]
    rho = np.linspace(0.0, 1.0, rows)
    w = fR - fL
    open_rows = np.where(w < 0.97)[0]
    if len(open_rows) < 4:
        detect.why = 'open_rows'
        return None
    hub_r = float(r_rows[open_rows[0]])
    ring_in = float(r_rows[open_rows[-1]])
    phi0 = math.pi / 2 - seam_ref - 0.5 * pitch
    drehung = math.degrees((phi0 + math.pi) % (2 * math.pi) - math.pi)
    wmax = float(np.percentile(w[open_rows], 90) * pitch * float(np.mean(r_rows[open_rows])))
    info = "%d Speichen%s · Kanten aus der Maske (%d Stützpunkte) · Nabe bis %.0f mm · Ring ab %.0f mm" % (
        n, " (Doppelspeichen → je Paar eine Speiche)" if twin else "", 0, hub_r * 1000.0, ring_in * 1000.0)
    el, er = _rdp(rho, fL, 0.004, 28), _rdp(rho, fR, 0.004, 28)
    es = _rdp(rho, cfrac, 0.004, 20)
    info = info.replace("(0 Stützpunkte)", "(%d+%d Stützpunkte)" % (len(el), len(er)))
    return dict(n=int(n), drehung_deg=float(drehung), edge_l=el, edge_r=er, seam=es, hub_r_mm=hub_r * 1000.0,
                ring_mm=max(6.0, (r_face - ring_in) * 1000.0), wmax_mm=wmax * 1000.0, twin=twin, info=info)


detect.why = ''
