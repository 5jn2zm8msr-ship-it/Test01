# Debug-Ansicht für Schritte 1-3 (Felge finden, N/Phase, gemittelter Sektor). Aufruf mit Blender (headless):
#   blender -b --python tools/debug_sector.py        (Add-on "felge3d" muss installiert/aktiviert sein; IDX=Foto-Indizes, OUTDIR=Ausgabeordner)
# Schreibt je Foto debug_sektor_<name>_a.png (Foto+Kreis, entzerrt+Sektorgrenzen, Maske, Polar Foto/Maske) und _b.png
# (Median-Sektor, symmetrisiert, Silhouette, Rekonstruktion über dem Foto).
import os, shutil, bpy, addon_utils, numpy as np, time, json
def log(*a): print(*a, flush=True)
d = os.path.join(bpy.utils.user_resource('SCRIPTS', path="addons", create=True), "felge3d")
shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
for f in os.listdir("/home/user/test01/felge3d"):
    if f.endswith((".py", ".toml")): shutil.copy(os.path.join("/home/user/test01/felge3d", f), d)
bpy.ops.wm.read_factory_settings(use_empty=True); addon_utils.enable("felge3d", default_set=True)
import felge3d
from felge3d import paramui, paramrim
s = bpy.context.scene.felge3d
files = sorted(os.listdir("/home/user/test01/testfelgen"))

import numpy as np, math
from felge3d import core, sector
def put(img, y0, x0, tile):
    h, w = tile.shape[:2]; img[y0:y0 + h, x0:x0 + w] = tile
def rgbify(a, lo=None, hi=None):
    a = np.asarray(a, np.float32)
    lo = a.min() if lo is None else lo; hi = a.max() if hi is None else hi
    g = np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)
    return np.stack([g, g, g], -1)
def resize(a, h, w):
    X, Y = np.meshgrid((np.arange(w) + .5) / w * a.shape[1] - .5, (np.arange(h) + .5) / h * a.shape[0] - .5)
    if a.ndim == 2: return core.bilinear(a, X, Y)[..., None].repeat(3, -1)
    return np.stack([core.bilinear(a[..., c], X, Y) for c in range(3)], -1)
def circle(img, cx, cy, rx, ry, col):
    for t in np.linspace(0, 2 * math.pi, 1500):
        x, y = int(round(cx + rx * math.sin(t))), int(round(cy + ry * math.cos(t)))
        if 0 <= x < img.shape[1] and 0 <= y < img.shape[0]: img[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = col
def vlines(img, xs, col):
    for x in xs:
        x = int(x)
        if 0 <= x < img.shape[1]: img[:, x] = col
def save(path, arr):
    im = bpy.data.images.new("dbg", arr.shape[1], arr.shape[0], alpha=False); a = np.concatenate([np.clip(arr[::-1], 0, 1), np.ones(arr.shape[:2] + (1,), np.float32)], -1)
    im.pixels[:] = a.ravel().tolist(); im.filepath_raw = path; im.file_format = "PNG"; im.save(); bpy.data.images.remove(im)
OUT = os.environ.get("OUTDIR", "/home/user/felge3d/")
names = {5: "porsche", 0: "audi", 4: "volvo"}
for k in [int(x) for x in os.environ.get("IDX", "5,0,4").split(",")]:
    bpy.ops.felge3d.import_image(filepath="" + os.environ.get("TESTFELGEN", "/home/user/test01/testfelgen") + "/" + files[k])
    gray, cx, cy, rx, ry = felge3d.prepare(s); rgb = felge3d._rgb_cache[next(iter(felge3d._rgb_cache))]; H, W = gray.shape
    # ---- Schritt 1
    rim = sector.find_rim(gray, cx, cy, rx, ry); nrx, nry = rim["scale"] * rx, rim["scale"] * ry
    print("RESULT %s Schritt 1: alter Kreis rx=%.0f | Periodizität N=%d | Fensterende bei %.2f, Horn bei %.2f -> neuer Radius %.0f px (%+.0f%%)" % (names.get(k, k), rx, rim["N"], rim["window_end"], rim["lip"], nrx, (rim["scale"] - 1) * 100))
    # Maske (bestehende Segmentierung) mit dem neuen Kreis
    depth_pre = felge3d.ai_depth(s, cx, cy, nrx, nry, force=True)
    print("RESULT %s KI-Tiefe: %s" % (names.get(k, k), "ja" if depth_pre is not None else "nicht verfügbar"))
    hub_n = felge3d.hub_symmetry(s, gray, cx, cy, nrx, nry, rim["N"])
    mask, thr = felge3d.compute_mask(s, gray, cx, cy, nrx, nry, rim["N"], depth_pre, hub_n)
    Pm = sector.polar_unwrap(mask, cx, cy, nrx, nry, 1.0, 240, 1080)
    Pg = sector.polar_unwrap(gray, cx, cy, nrx, nry, 1.0, 240, 1080)
    # ---- Schritt 2
    nph = sector.detect_n_phase(Pm, n_hint=rim["N"]); N, phase = nph["N"], nph["phase"]
    top3 = sorted(nph["scores"], key=nph["scores"].get, reverse=True)[:4]
    print("RESULT %s Schritt 2: N=%d Phase=%.1f° | beste k (FFT+Autokorr): %s | Rotations-Score N: %.2f" % (names.get(k, k), N, math.degrees(phase), [(kk, round(nph["scores"][kk], 2)) for kk in top3], nph["sims"][N]))
    # ---- Schritt 3
    theta0 = phase - math.pi / N
    med, st = sector.median_sector(Pm, N, theta0, 360)
    sym, sh = sector.mirror_symmetry(med)
    med_s = sector.symmetrize(med, sh) if sym > 0.88 else med
    sil = sector.silhouette(med_s)
    rec = sector.reconstruct(sil, N, theta0, 512)
    ref = sector.rectify(mask, cx, cy, nrx, nry, 512)
    iou = float((rec * (ref > .5)).sum() / max(np.maximum(rec, ref > .5).sum(), 1))
    spread = float(np.mean(np.abs(st - med[None])))
    print("RESULT %s Schritt 3: Median über %d Sektoren | Streuung zwischen Sektoren %.3f | Spiegelsymmetrie %.2f (Achse %+d Spalten, %s) | Rekonstruktion IoU zur Maske %.2f" % (names.get(k, k), N, spread, sym, sh, "angewandt" if sym > 0.88 else "nicht angewandt", iou))
    # ---- Debug-Bild
    T = 330; canvas = np.full((T * 3 + 20, T * 3 + 20, 3), 0.1, np.float32)
    ph = resize(rgb, T, T) if rgb.shape[0] == H else resize(rgb, T, T)
    big = rgb.copy(); circle(big, cx, cy, rx, ry, (1, 0, 0)); circle(big, cx, cy, nrx, nry, (0, 1, 0)); put(canvas, 0, 0, resize(big, T, T))                 # a) Foto + alter (rot) / neuer (grün) Kreis
    rr = sector.rectify(rgb, cx, cy, nrx, nry, 512); bounds = [(theta0 + j * 2 * math.pi / N) for j in range(N)]
    for b in bounds:
        for t in np.linspace(0, 1, 400): x = int(256 + math.sin(b) * 256 * t); y = int(256 - math.cos(b) * 256 * t); rr[max(0, y - 1):y + 1, max(0, x - 1):x + 1] = (1, 1, 0)
    put(canvas, 0, T + 10, resize(rr, T, T))                                                                    # b) entzerrt + Sektorgrenzen
    put(canvas, 0, 2 * T + 20, resize(np.stack([ref] * 3, -1), T, T))                                        # c) Maske entzerrt
    pg = rgbify(Pg, np.percentile(Pg, 1), np.percentile(Pg, 99)); pm = np.stack([Pm] * 3, -1)
    xs = [(b % (2 * math.pi)) / (2 * math.pi) * 1080 for b in bounds]
    pgr, pmr = resize(pg, T, 3 * T // 1 if False else T), None
    wide = np.zeros((T, 3 * T, 3), np.float32); wide[:] = resize(pg, T, 3 * T); vlines(wide, [x / 1080 * 3 * T for x in xs], (1, 1, 0)); canvas[T + 10:2 * T + 10, 0:3 * T] = wide   # d) Polar (Foto)
    wide2 = resize(pm, T, 3 * T); vlines(wide2, [x / 1080 * 3 * T for x in xs], (1, 1, 0)); canvas[2 * T + 20:3 * T + 20, 0:3 * T] = wide2                              # e) Polar (Maske)
    save(OUT + "debug_sektor_%s_a.png" % names.get(k, k), canvas)
    # zweites Bild: Sektoren, Median, Silhouette, Rekonstruktion
    row = np.full((T + 10, 4 * T + 30, 3), 0.1, np.float32)
    put(row, 0, 0, resize(np.stack([med] * 3, -1), T, T)); put(row, 0, T + 10, resize(np.stack([med_s] * 3, -1), T, T)); put(row, 0, 2 * T + 20, resize(np.stack([sil] * 3, -1), T, T))
    ov = sector.rectify(rgb, cx, cy, nrx, nry, 512) * 0.55; edge = (rec - np.roll(rec, 1, 0) != 0) | (rec - np.roll(rec, 1, 1) != 0); ov[edge] = (0, 1, 0); put(row, 0, 3 * T + 30, resize(ov, T, T))
    save(OUT + "debug_sektor_%s_b.png" % names.get(k, k), row)
print("RESULT fertig")
