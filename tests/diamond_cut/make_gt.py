# SPDX-License-Identifier: GPL-3.0-or-later
"""
Ground-Truth-Entwurf für die Diamond-Cut-Messung aus Samen (Seeds) – ENTWURF, bitte prüfen und bei Bedarf in einem Bildeditor
nachmalen (weiß = blank, schwarz = nicht blank; gleiche Auflösung wie gt.png, Orientierung wie ein normales Bild).

Aufruf:  python tests/diamond_cut/make_gt.py volvo

Vorgehen: einige Punkte einer Speiche (weiß = blank, schwarz = Schwarzglanz, in Bildpixeln des Arbeitsbilds, oben = y 0) werden über die
Symmetrie (N Drehungen, Spiegelung) auf alle Speichen übertragen. Schwelle = Mitte der Proben; zusammenhängende helle Gebiete, die
einen weißen Samen enthalten (>= 60 px), bilden die Maske. Keine Pixel-Voting-Logik des Add-ons: unabhängig davon gebaut.
"""
import json
import math
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_diamond_cut as ev      # noqa: E402

CASES = {
    "volvo": dict(photo="volvo/photo.jpg", N=5, mirror=True,
                  white=[(517, 250), (510, 300), (506, 325), (480, 370), (494, 354),
                         (450, 418), (405, 425), (482, 435), (430, 478), (467, 480), (453, 386),      # Nabenfläche zwischen den Radschrauben
                         (450, 164)],                                                                  # polierter Außenring (Felgenhorn)
                  black=[(512, 366), (545, 330), (470, 300), (540, 250), (560, 380), (415, 412)]),
}


def main(name):
    cfg = CASES[name]
    ev.install()
    import felge3d
    bpy.ops.felge3d.import_image(filepath=os.path.join(ev.HERE, cfg["photo"]))
    s = bpy.context.scene.felge3d
    gray, cx, cy, rx, ry = felge3d.prepare(s)
    H, W = gray.shape
    g = np.asarray(gray, np.float64)[::-1]                    # Anzeige-Orientierung (oben = y 0)
    cyd = H - 1 - cy
    N = cfg["N"]

    def sym(pts):
        out = []
        for x, y in pts:
            for mir in ((False, True) if cfg["mirror"] else (False,)):
                xx = 2 * cx - x if mir else x
                for k in range(N):
                    a = 2 * math.pi * k / N
                    dx, dy = xx - cx, y - cyd
                    out.append((cx + dx * math.cos(a) - dy * math.sin(a), cyd + dx * math.sin(a) + dy * math.cos(a)))
        return out
    ws, bs = sym(cfg["white"]), sym(cfg["black"])
    val = lambda p: float(g[int(round(p[1])), int(round(p[0]))])          # noqa: E731
    wv, bv = np.array([val(p) for p in ws]), np.array([val(p) for p in bs])
    thr = 0.5 * (wv.mean() + bv.mean())

    def blur(a):
        a = (np.roll(a, 1, 0) + 2 * a + np.roll(a, -1, 0)) / 4
        return (np.roll(a, 1, 1) + 2 * a + np.roll(a, -1, 1)) / 4
    gb = blur(g)
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cyd) / ry) ** 2) * 0.271
    cand = (gb >= thr) & (rr > 0.045) & (rr < 0.287)             # Speichen, Nabenfläche und Außenring (bis 1,06 x Felgenradius); r < 45 mm ist die Kappe (Modell: Zylinder)
    lab = -np.ones((H, W), np.int32)
    comps = []
    for y in range(H):
        for x in range(W):
            if cand[y, x] and lab[y, x] < 0:
                st, cells = [(y, x)], []
                lab[y, x] = len(comps)
                while st:
                    a, b = st.pop()
                    cells.append((a, b))
                    for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        c, d = a + da, b + db
                        if 0 <= c < H and 0 <= d < W and cand[c, d] and lab[c, d] < 0:
                            lab[c, d] = len(comps)
                            st.append((c, d))
                comps.append(cells)
    keep = {lab[int(round(p[1])), int(round(p[0]))] for p in ws if lab[int(round(p[1])), int(round(p[0]))] >= 0}
    gt = np.zeros((H, W), bool)
    for ci in keep:
        if len(comps[ci]) >= 60:
            for a, b in comps[ci]:
                gt[a, b] = True
    ringpx = gt & (rr > 0.264)                              # Außenring: physisch überall poliert (Lippe), auch wo er im Foto dunkel spiegelt -> voller Kreisring
    if ringpx.sum() > 500:
        lo_r, hi_r = np.percentile(rr[ringpx], [3, 97])
        gt |= (rr >= lo_r) & (rr <= hi_r)
    im = bpy.data.images.new("gt", W, H, alpha=False)
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = gt[::-1, :, None]                         # bpy: unten = Zeile 0
    im.pixels.foreach_set(rgba.ravel())
    out = os.path.join(ev.HERE, name, "gt.png")
    im.filepath_raw = out
    im.file_format = "PNG"
    im.save()
    json.dump(dict(width=W, height=H, cx=cx, cy=cy, rx=rx, ry=ry, N=N, threshold=thr, white_mean=float(wv.mean()), black_mean=float(bv.mean()),
                   hinweis="Entwurf aus Samen, bitte prüfen"), open(os.path.join(ev.HERE, name, "gt_meta.json"), "w"), indent=1)
    print("GT geschrieben:", out, "blank-Anteil im Ring %.1f %%" % (100 * gt[(rr > 0.045) & (rr < 0.287)].mean()))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "volvo")
