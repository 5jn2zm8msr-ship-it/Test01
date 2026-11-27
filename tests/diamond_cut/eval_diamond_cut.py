# SPDX-License-Identifier: GPL-3.0-or-later
"""
Messung der Diamond-Cut-Zuordnung (blank / schwarz) gegen Ground-Truth-Masken.

Aufruf (Blender-Python, z. B. das bpy-Modul):
    python tests/diamond_cut/eval_diamond_cut.py [Fallname ...]

Je Fall in cases.json: Foto + Ground-Truth-Maske (PNG, Arbeitsauflösung, oben = y 0, weiß = blank).
Ausgabe: Tabelle je Bild (Flächengenauigkeit, Pixelgenauigkeit, IoU), außerdem tests/diamond_cut/ergebnis.md.
Ziel: >= 98 %.
"""
import json
import math
import os
import shutil
import sys

import bpy  # noqa: I001  (muss vor addon_utils kommen)
import addon_utils
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def install():
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


def load_gt(path, w, h):
    im = bpy.data.images.load(path)
    arr = np.array(im.pixels[:], np.float32).reshape(im.size[1], im.size[0], 4)[..., 0]      # bpy: unten = Zeile 0
    bpy.data.images.remove(im)
    if arr.shape != (h, w):
        raise RuntimeError("GT hat %s, Arbeitsbild %s" % (arr.shape, (h, w)))
    return arr > 0.5                                                                         # Orientierung wie das Arbeitsbild (unten = 0)


def raster(cage, cx, cy, rx, ry, R_out, H, W):
    """Käfigflächen aller N Sektoren ins Arbeitsbild: (Flächen-ID je Pixel, -1 = keine), (Label je Fläche und Sektor)."""
    r, f = np.asarray(cage["r"]), np.asarray(cage["f"])
    faces, dia = cage["faces"], np.asarray(cage["diamond"])
    pitch, ts, N = cage["pitch"], cage["theta_s"], int(cage["N"])
    nf = len(faces)
    fid = -np.ones((H, W), np.int32)
    for k in range(N):
        th = ts + (f + k) * pitch + (cage.get("copy_dtheta") or [0.0] * N)[k]
        rk = r * (1.0 + (cage.get("copy_eps") or [0.0] * N)[k])
        sh_ = (cage.get("copy_shift") or [[0.0, 0.0]] * N)[k]
        X, Y = cx + sh_[0] + rk / R_out * rx * np.sin(th), cy + sh_[1] + rk / R_out * ry * np.cos(th)
        for i, fc in enumerate(faces):
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
                fid[y0:y1 + 1, x0:x1 + 1][m] = k * nf + i
    return fid, np.tile(dia.astype(bool), N)


def evaluate(case):
    import felge3d
    from felge3d import core, paramui
    bpy.context.preferences.addons["felge3d"].preferences.show_local = True              # lokale Methoden (Entwickler) nur hier, ausdrücklich
    bpy.context.scene.felge3d.method = "SUBD"                  # lokale Methode ausdrücklich (Standard ist Meshy)
    bpy.ops.felge3d.import_image(filepath=os.path.join(HERE, case["photo"]))
    s = bpy.context.scene.felge3d
    col = s.collection
    tob = next(o for o in col.objects if o.get("felge3d_role") == "template_baked")
    cage = json.loads(tob["felge3d_tdata"])
    n_deep = cage.get("n_deep", 0)
    gray, cx, cy, rx, ry = felge3d.prepare(s)
    H, W = gray.shape
    _R, _W, _fl, _wl, R_out, _rf, _d = core.dimensions(felge3d.make_params(s))
    gt = load_gt(os.path.join(HERE, case["gt"]), W, H)
    fid, lab = raster(cage, cx, cy, rx, ry, R_out, H, W)
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) * R_out
    region = (fid >= 0) & (rr > case.get("r_min", 0.045)) & (rr < case.get("r_max", 0.264))          # Käfigflächen: Nabe und Speichen
    pred = np.zeros((H, W), bool)
    pred[fid >= 0] = lab[fid[fid >= 0]]
    if os.environ.get("DC_DEBUG"):                          # Fehlerbild: rot = zu viel blank, blau = fehlt, Region abgedunkelt
        rgb = np.array(bpy.data.images[s.image.name].pixels[:], np.float32)           # Originalgröße; Arbeitsbild für das Fehlerbild
        rgb = np.asarray(felge3d._rgb_cache[next(iter(felge3d._rgb_cache))], np.float32)
        if rgb.max() <= 1.5:
            rgb = rgb * 255.0
        ov = rgb[..., :3].copy()
        ov[~region] *= 0.35
        ov[region & pred & ~gt] = (255, 40, 40)
        ov[region & ~pred & gt] = (40, 120, 255)
        im = bpy.data.images.new("fehler", W, H, alpha=False)
        rgba = np.ones((H, W, 4), np.float32)
        rgba[..., :3] = ov / 255.0
        im.pixels.foreach_set(rgba.ravel())
        im.filepath_raw = os.path.join(HERE, "fehler_%s.png" % case["name"])
        im.file_format = "PNG"
        im.save()
    # Außenring (Felgenhorn): liegt außerhalb des Käfigs; blank, wenn „Horn poliert“ gesetzt ist und das Foto dort hell ist
    ring_zone = (rr > cage.get("r_cage_out", 0.264) + 0.002) & (rr < 1.06 * R_out)
    horn = bool(cage.get("horn_polished", False))
    ring_pred = ring_zone & horn & (rr >= R_out - _wl - 0.002) & (rr <= R_out + 0.001)                 # Horn-Lippe im Modell (Stirnfläche, Breite = Wandstärke)
    rtp, rfp, rfn = int(np.sum(ring_pred & gt & ring_zone)), int(np.sum(ring_pred & ~gt)), int(np.sum(~ring_pred & gt & ring_zone))
    ring_iou = rtp / max(rtp + rfp + rfn, 1)
    if os.environ.get("DC_DEBUG"):
        gr = rr[gt & ring_zone]
        print("DEBUG Ring: GT-Pixel %d (r %.4f–%.4f, Median %.4f) | Modell-Horn-Pixel %d (r %.4f–%.4f) | Treffer %d | R_out %.4f r_cage_out %.4f" % (len(gr), gr.min() if len(gr) else 0, gr.max() if len(gr) else 0, np.median(gr) if len(gr) else 0, int(ring_pred.sum()), R_out - _wl - 0.002, R_out + 0.001, rtp, R_out, cage.get('r_cage_out', 0)))
    P, G = pred[region], gt[region]
    tp, fp, fn = int(np.sum(P & G)), int(np.sum(P & ~G)), int(np.sum(~P & G))
    pix_acc = float(np.mean(P == G))
    iou = tp / max(tp + fp + fn, 1)
    ids = fid[region]
    n_all = int(fid.max()) + 1
    cnt = np.bincount(ids, minlength=n_all).astype(np.float64)
    gsum = np.bincount(ids, weights=G.astype(np.float64), minlength=n_all)
    present = cnt > 0
    gmaj = (gsum[present] / cnt[present]) >= 0.5
    face_correct = (lab[:n_all][present] == gmaj)
    face_acc_area = float(np.sum(cnt[present][face_correct]) / np.sum(cnt[present]))           # flächengewichtet (Pixel)
    face_acc_n = float(np.mean(face_correct))
    return dict(name=case["name"], N=int(cage["N"]), faces=int(len(cage["faces"])), pix_acc=pix_acc, iou=iou, face_acc_area=face_acc_area,
                face_acc_n=face_acc_n, ring_iou=ring_iou, ring_pixels=int(np.sum(gt & ring_zone)), n_deep=n_deep, conf_min=float(np.min(cage["face_conf"])) if cage.get("face_conf") else None, precision=tp / max(tp + fp, 1), recall=tp / max(tp + fn, 1), pixels=int(region.sum()))


def main():
    cases = json.load(open(os.path.join(HERE, "cases.json")))
    sel = set(sys.argv[1:])
    install()
    if os.environ.get("DC_NO_DEPTH"):
        from felge3d import sector
        sector.USE_DEPTH_RULE = False
    rows = [evaluate(c) for c in cases if not sel or c["name"] in sel]
    hdr = "| Bild | Sektoren | Flächen/Sektor | Flächengenauigkeit (Fläche) | Flächengenauigkeit (Anzahl) | Pixelgenauigkeit | IoU blank | Präzision | Recall | Ring-IoU (Felgenhorn) | durch Tiefe entfernt | Ziel Flächengenauigkeit ≥ 98 % |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
    lines = [hdr]
    for r in rows:
        ok = "✓" if r["face_acc_area"] >= 0.98 else "✗"
        lines.append("| %s | %d | %d | %.1f %% | %.1f %% | %.1f %% | %.1f %% | %.1f %% | %.1f %% | %.1f %% | %d | %s |" % (
            r["name"], r["N"], r["faces"], 100 * r["face_acc_area"], 100 * r["face_acc_n"], 100 * r["pix_acc"], 100 * r["iou"],
            100 * r["precision"], 100 * r["recall"], 100 * r["ring_iou"], r["n_deep"], ok))
    out = "\n".join(lines)
    print(out)
    with open(os.path.join(HERE, "ergebnis.md"), "w", encoding="utf-8") as fh:
        fh.write("# Diamond-Cut-Messung\n\nGround Truth: siehe README.md (Entwurf, bitte prüfen).\n\n" + out + "\n")


if __name__ == "__main__":
    main()
