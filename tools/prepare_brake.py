"""Bremsenfoto -> felge3d/brake_data.py (Texturen links/rechts, Sattelumriss). Aufruf: python3 tools/prepare_brake.py"""
import base64, textwrap
import cv2, numpy as np

im = cv2.imread("assets/bremse_foto.png")
cx, cy, Rx, Ry = 535.5, 814.5, 448.5, 450.0        # Scheibe im Foto (gemessen)
hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
m = ((hsv[..., 0] > 24) & (hsv[..., 0] < 48) & (hsv[..., 1] > 110) & (hsv[..., 2] > 90)).astype(np.uint8)
n, lab, st, _ = cv2.connectedComponentsWithStats(m)
mk = (lab == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA])).astype(np.uint8)
mk = cv2.morphologyEx(mk, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
c = max(cv2.findContours(mk, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea)
mfill = np.zeros_like(mk); cv2.drawContours(mfill, [c], -1, 1, -1)
mer = cv2.erode(mfill, np.ones((7, 7), np.uint8))
c2 = max(cv2.findContours(mer, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0], key=cv2.contourArea)
poly = [((p[0] - cx) / Rx, (cy - p[1]) / Ry) for p in cv2.approxPolyDP(c2, 2.2, True)[:, 0, :].astype(np.float32)]
rgbm = im[..., ::-1][mer > 0].mean(axis=0) / 255.0
V = hsv[..., 2]
dark = cv2.morphologyEx(((V < 85) & (mfill > 0)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) & cv2.erode(mfill, np.ones((41, 41), np.uint8))
ys, xs = np.nonzero(dark)
tx0, tx1, ty0, ty1 = int(np.percentile(xs, 1)) - 12, int(np.percentile(xs, 99)) + 12, int(np.percentile(ys, 1)) - 12, int(np.percentile(ys, 99)) + 12
hw, hh = 530, 471
x0, x1, y0, y1 = int(cx - hw), int(cx + hw), int(cy - hh), int(cy + hh)
front = im[y0:y1, x0:x1].copy(); mirror = front[:, ::-1].copy(); Wc = front.shape[1]
Mo = mer[y0:y1, x0:x1].astype(np.float32); Mm = Mo[:, ::-1]
px0, px1 = tx0 - x0, tx1 - x0; mx0, mx1 = Wc - px1, Wc - px0; ry0, ry1 = ty0 - y0, ty1 - y0
# Schrift unverspiegelt einsetzen - nur dort, wo Quelle UND Ziel Sattel sind (kein dunkles Rechteck)
alpha = cv2.GaussianBlur(Mo[ry0:ry1, px0:px1] * Mm[ry0:ry1, mx0:mx1], (0, 0), 2.5)
patch = front[ry0:ry1, px0:px1].astype(np.float32); reg = mirror[ry0:ry1, mx0:mx1].astype(np.float32)
mirror[ry0:ry1, mx0:mx1] = (patch * alpha[..., None] + reg * (1 - alpha[..., None])).astype(np.uint8)
sc = 1024.0 / max(front.shape[:2]); sz = (int(front.shape[1] * sc), int(front.shape[0] * sc))
fr = cv2.resize(front, sz, interpolation=cv2.INTER_AREA); mi = cv2.resize(mirror, sz, interpolation=cv2.INTER_AREA)
Wn, Hn = sz
jf = cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 88])[1]; jm = cv2.imencode(".jpg", mi, [cv2.IMWRITE_JPEG_QUALITY, 88])[1]
meta = dict(W=Wn, H=Hn, cx=(cx - x0) * sc / Wn, cy_up=1.0 - (cy - y0) * sc / Hn, Rx=Rx * sc / Wn, Ry=Ry * sc / Hn,
            hat_ratio=0.58, ring_in_ratio=0.62, cal_color=[float(v) for v in rgbm], cal_rmax=1.152, cal_rmin=0.684,
            caliper=[(round(float(a), 4), round(float(b), 4)) for a, b in poly])
enc = lambda d: "(\n" + "\n".join('    "%s"' % l for l in textwrap.wrap(base64.b64encode(d.tobytes()).decode(), 120)) + "\n)\n"
open("felge3d/brake_data.py", "w").write('# SPDX-License-Identifier: GPL-3.0-or-later\n"""Bremsen-Foto (Porsche, Monobloc-Sattel). FRONT = links, MIRROR = rechts (Schrift korrigiert). Erzeugt von tools/prepare_brake.py"""\n'
                                         + "META = %r\n" % (meta,) + "FRONT_B64 = " + enc(jf) + "MIRROR_B64 = " + enc(jm))
print("ok", Wn, Hn)
