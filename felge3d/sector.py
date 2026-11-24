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
