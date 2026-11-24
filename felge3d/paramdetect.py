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


def _centers(row, dth):
    """Mittenwinkel (rad) und Länge (rad) der Läufe."""
    return [(((s + 0.5 * l) * dth) % (2 * math.pi), l * dth) for s, l in _runs(row)]


def detect(F, radii, r_face, n_sym=0, ring_m=0.012):
    """
    Gibt dict: n, drehung_deg, biegung_deg, breite_mm, hub_r_mm, width_pts, sweep_pts, info (Text), twin (bool) zurück.
    """
    F = np.asarray(F) >= 0.5
    n_r, n_t = F.shape
    dth = 2 * math.pi / n_t
    radii = np.asarray(radii, np.float64)
    frac = F.mean(axis=1)
    run_n = np.array([len(_runs(F[i])) for i in range(n_r)])
    # --- Speichenzahl: häufigster Wert (>= 3) der Läufe auf Radien mit offenen Fenstern (frac < 0.9)
    wide = np.where((frac < 0.9) & (run_n >= 3))[0]
    if len(wide) < 4:
        return None
    vals, cnts = np.unique(run_n[wide], return_counts=True)
    n_run = int(vals[np.argmax(cnts)])
    twin = False
    if 3 <= n_sym <= 24:
        n = n_sym
        twin = bool(n_run == 2 * n_sym)
    else:
        n = n_run
    need = 2 * n if twin else n
    # --- Nabe/Ring: Fenster zwischen den Speichen sind offen (>= n Läufe) – kleine Löcher in der Nabe zählen nicht
    open_idx = np.where(run_n >= max(3, need - max(1, need // 4)))[0]
    if len(open_idx) < 4:
        return None
    r_hub = float(radii[open_idx[0]])
    r_ring_in = float(min(radii[open_idx[-1]], r_face - ring_m))
    if r_ring_in <= r_hub + 0.02:
        return None
    lo, hi = r_hub + 0.15 * (r_ring_in - r_hub), r_hub + 0.85 * (r_ring_in - r_hub)
    cand = [i for i in range(n_r) if lo <= radii[i] <= hi]
    # --- Bezugsradius mit genau n Läufen (sonst der mit der besten Übereinstimmung)
    best_i, best_d = None, 1e9
    for i in cand:
        c = len(_runs(F[i]))
        d = abs(c - (2 * n if twin else n))
        if d < best_d or (d == best_d and best_i is not None and abs(radii[i] - 0.5 * (lo + hi)) < abs(radii[best_i] - 0.5 * (lo + hi))):
            best_i, best_d = i, d
    i_ref = best_i
    ref_runs = _centers(F[i_ref], dth)
    if twin:                                           # Doppelspeichen: Paare zusammenfassen -> mittlere Position/Breite
        ref_runs.sort()
        merged = []
        for k in range(0, len(ref_runs) - 1, 2):
            a, b = ref_runs[k], ref_runs[k + 1]
            merged.append((((a[0] + b[0]) / 2), abs(_wrap(b[0] - a[0])) + (a[1] + b[1]) / 2))
        ref_runs = merged
    if len(ref_runs) < 3:
        return None
    # --- Verfolgen jeder Speiche nach innen und außen über i_ref
    ks = np.linspace(r_hub, r_ring_in, 28)
    ri = [int(np.argmin(np.abs(radii - r))) for r in ks]
    W = np.full((len(ref_runs), len(ks)), np.nan)
    PSI = np.full_like(W, np.nan)
    sector = math.pi / max(len(ref_runs), 1)
    j_ref = int(np.argmin(np.abs(ks - radii[i_ref])))
    for s, (c0, w0) in enumerate(ref_runs):
        for direction in (-1, 1):
            c_prev = c0
            rng = range(j_ref, -1, -1) if direction < 0 else range(j_ref, len(ks))
            for j in rng:
                cs = _centers(F[ri[j]], dth)
                if not cs:
                    break
                pick = min(cs, key=lambda t: abs(_wrap(t[0] - c_prev)))
                if abs(_wrap(pick[0] - c_prev)) > 0.7 * sector:
                    break
                W[s, j] = pick[1] * radii[ri[j]]       # Bogenlänge ~ Breite (m)
                PSI[s, j] = _wrap(pick[0] - c0)
                c_prev = pick[0]
    med_w = np.nanmedian(W, axis=0)
    med_p = np.nanmedian(PSI, axis=0)
    ok = ~np.isnan(med_w)
    if ok.sum() < 6:
        return None
    # --- sauberste Speiche = geringste Abweichung vom Median (vollständige Verfolgung bevorzugt)
    score = []
    for s in range(len(ref_runs)):
        valid = ~np.isnan(W[s]) & ok
        if valid.sum() < 0.6 * ok.sum():
            score.append(1e9)
            continue
        dw = np.abs(W[s][valid] - med_w[valid]).mean() / max(np.nanmax(med_w), 1e-6)
        dp = np.abs(PSI[s][valid] - med_p[valid]).mean()
        score.append(dw + 2.0 * dp + 0.5 * (1 - valid.sum() / ok.sum()))
    k_best = int(np.argmin(score))
    w = np.where(np.isnan(W[k_best]), med_w, W[k_best])
    psi = np.where(np.isnan(PSI[k_best]), med_p, PSI[k_best])
    # Lücken (nicht verfolgt) halten: Rand-Werte fortsetzen
    idx = np.arange(len(ks))
    good = ~np.isnan(w)
    w = np.interp(idx, idx[good], w[good])
    good = ~np.isnan(psi)
    psi = np.interp(idx, idx[good], psi[good])
    # --- Umrechnen auf die Parameter des Node-Baums (t = 0..1 von r0 = 0.8 r_hub bis r1 = r_face - ring/2)
    r0, r1 = 0.8 * r_hub, r_face - 0.5 * ring_m
    t_k = np.clip((ks - r0) / (r1 - r0), 0.0, 1.0)
    tg = np.linspace(0.0, 1.0, 8)
    pitch = 2 * math.pi * ks / n                          # Speichen können nie breiter als der Teilungsabstand sein
    w = np.minimum(w, 0.9 * pitch)
    # Glätten: Nabenübergang (innere 15 %) ignorieren, Breite und Biegung linear fitten (kein Wackeln)
    use = np.arange(len(ks)) >= int(0.15 * len(ks))
    tw = t_k[use]
    cw = np.polyfit(tw, w[use], 1) if use.sum() > 4 else np.array([0.0, float(np.median(w))])
    wg = np.polyval(cw, tg)
    wmax = float(np.clip(np.percentile(wg, 90), 0.02, 0.15))
    wg = np.clip(wg, 0.12 * wmax, wmax)
    cp = np.polyfit(tw, psi[use], 1) if use.sum() > 4 else np.array([0.0, float(np.median(psi))])
    pg = np.polyval(cp, tg)
    p0 = float(pg[0])
    c0 = ref_runs[k_best][0]
    d_psi = -(pg - p0)                                  # Änderung von phi (= pi/2 - theta) relativ zum Start
    total = float(d_psi[-1])
    if abs(total) < math.radians(12.0):                 # praktisch gerade Speiche
        p0 = float(np.polyval(cp, 0.5))
        total = 0.0
        sweep = [(float(t), float(t)) for t in tg]
    else:
        total = float(np.clip(total, -math.radians(60.0), math.radians(60.0)))
        sweep = [(float(t), float(t)) for t in tg]       # lineare Verdrehung zum Rand
    width_pts = [(float(t), float(v / wmax)) for t, v in zip(tg, wg)]
    drehung = math.degrees(_wrap(math.pi / 2 - (c0 + p0)))
    info = "%d Speichen%s · Breite max %.0f mm · Biegung %.0f° · Nabe bis %.0f mm" % (
        n, " (Doppelspeichen → je Paar eine Speiche)" if twin else "", wmax * 1000.0, math.degrees(total), r_hub * 1000.0)
    return dict(n=int(n), drehung_deg=float(drehung), biegung_deg=float(np.clip(math.degrees(total), -90.0, 90.0)),
                breite_mm=wmax * 1000.0, hub_r_mm=r_hub * 1000.0, width_pts=width_pts, sweep_pts=sweep, twin=twin, info=info)
