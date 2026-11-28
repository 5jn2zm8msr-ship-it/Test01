"""Poly-Haven-Waldpanorama (CC0, equirectangular .hdr) -> graded PNG fuer den Waldhintergrund.
Aufruf: python wald_png.py <in.hdr> <out.png>   (Tonemapping, leichter Dunst am Horizont, kuehler/entsaettigter Ton -> nordischer Eindruck)"""
import sys, math, bpy, numpy as np
from PIL import Image
im = bpy.data.images.load(sys.argv[1]); w, h = im.size
a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1, :, :3]            # oben zuerst
import os; g = float(np.median(a.mean(2))); a = a * (float(os.environ.get('WALD_MEDIAN', '0.16')) / max(g, 1e-4)); a = a / (1 + 0.6 * a); a = np.clip(a, 0, 1); a = np.clip(0.5 + (a - 0.5) * 1.18, 0, 1)   # Belichtung + weiche Schulter
lum = a.mean(2, keepdims=True); a = lum + (a - lum) * 1.0                           # etwas entsaettigt
a = a * np.array([0.96, 1.0, 1.06], np.float32)                                     # leicht kuehl
v = (np.arange(h)[:, None] + 0.5) / h; haze = np.exp(-((v - 0.475) / 0.045) ** 2)[:, :, None] * float(os.environ.get('WALD_HAZE', '0.0'))   # Dunst um den Horizont (Standard: keiner)
sky = np.array([0.80, 0.86, 0.93], np.float32); a = a * (1 - haze) + sky * haze
a = np.clip(a, 0, 1) ** (1 / 2.2)
Image.fromarray((a * 255).astype(np.uint8)).save(sys.argv[2], optimize=True)
print('PNG', sys.argv[2], w, 'x', h)

# --- Modus "wand": perspektivisch korrekter Ausschnitt (rectilinear) fuer die Waldwand ---------------------------
# Aufruf: python wald_png.py <in.hdr> <panorama.png> wand <wand.png> [azimut_deg] [elevation_deg] [hfov] [vfov]
if len(sys.argv) > 3 and sys.argv[3] == 'wand':
    az, el, hf, vf = (float(x) for x in (sys.argv[5:9] + [None] * 4)[:4]) if len(sys.argv) >= 9 else (
        float(sys.argv[5]) if len(sys.argv) > 5 else 160.0, float(sys.argv[6]) if len(sys.argv) > 6 else 12.0, 72.0, 31.0)
    pano = np.asarray(Image.open(sys.argv[2]).convert('RGB')).astype(np.float32) / 255.0; H, W, _ = pano.shape
    ow = 2400; oh = int(round(ow * math.tan(math.radians(vf / 2)) / math.tan(math.radians(hf / 2)))) if False else int(round(ow * (2 * math.tan(math.radians(vf / 2))) / (2 * math.tan(math.radians(hf / 2)))))
    xs = (np.arange(ow) + 0.5) / ow * 2 - 1; ys = 1 - (np.arange(oh) + 0.5) / oh * 2           # Bildebene (-1..1)
    tx = xs[None, :] * math.tan(math.radians(hf / 2)); ty = ys[:, None] * math.tan(math.radians(vf / 2))
    dx = np.broadcast_to(tx, (oh, ow)); dz = np.broadcast_to(ty, (oh, ow)); dy = np.ones((oh, ow), np.float32)   # Blickrichtung nach vorn (+y), x rechts, z oben
    ce, se = math.cos(math.radians(el)), math.sin(math.radians(el))                          # um die x-Achse kippen (Elevation)
    y1 = dy * ce - dz * se; z1 = dy * se + dz * ce; x1 = dx
    lon = np.arctan2(x1, y1) + math.radians(az); lat = np.arctan2(z1, np.hypot(x1, y1))
    u = ((lon / (2 * math.pi)) % 1.0) * W; v = (0.5 - lat / math.pi) * H
    u = u - 0.5; v = v - 0.5; iu = np.floor(u).astype(int); iv = np.floor(v).astype(int); fu = (u - iu)[..., None]; fv = (v - iv)[..., None]
    iu0 = iu % W; iu1 = (iu + 1) % W; iv0 = np.clip(iv, 0, H - 1); iv1 = np.clip(iv + 1, 0, H - 1)
    out = (pano[iv0, iu0] * (1 - fu) + pano[iv0, iu1] * fu) * (1 - fv) + (pano[iv1, iu0] * (1 - fu) + pano[iv1, iu1] * fu) * fv      # bilinear
    Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(sys.argv[4], optimize=True)
    print('PNG Wand', sys.argv[4], ow, 'x', oh, 'Azimut', az, 'Elevation', el)
