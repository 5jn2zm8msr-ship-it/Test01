"""Nachbearbeitung: Farbgrading (leichter Blaustich), Glow, Vignette, Filmkorn, Imperfektionen.
python post.py <ordner> [shots]   liest roh_<k>.png, schreibt final_<k>.png (+ .jpg)"""
import sys, numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, shift as nd_shift, zoom

def srgb2lin(x): return np.where(x <= 0.04045, x/12.92, ((x+0.055)/1.055)**2.4)
def lin2srgb(x): x = np.clip(x, 0, 1); return np.where(x <= 0.0031308, x*12.92, 1.055*x**(1/2.4)-0.055)

# je Bild: Belichtung, Vignette (Ecken), Bodenabdunklung unten, Blaustich-Staerke
SHOT = {'10': dict(expo=1.06, vig=0.12, bottom=0.00, cool=1.0),
        '8':  dict(expo=0.92, vig=0.14, bottom=0.00, cool=1.2),
        '6':  dict(expo=1.04, vig=0.14, bottom=0.55, cool=1.0)}

def grade(a, p, rng):
    H, W = a.shape[:2]
    lin = srgb2lin(a) * p['expo']
    # Glow/Halation: helle Flaechen streuen leicht ueber die dunklen Kanten
    hi = np.clip(lin - 0.72, 0, None)
    glow = np.stack([gaussian_filter(hi[..., c], 9 * W/1179) for c in range(3)], -1)
    lin = lin + glow * np.array([0.55, 0.42, 0.40]) * 0.5
    # chromatische Aberration (R/B nach aussen, ~1 px an den Raendern)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W/2, H/2
    out = lin.copy()
    for c, k in ((0, 1.0012), (2, 0.9988)):
        from scipy.ndimage import map_coordinates
        out[..., c] = map_coordinates(lin[..., c], [cy + (yy-cy)*k, cx + (xx-cx)*k], order=1, mode='nearest')
    lin = out
    # Vignette + Bodenabdunklung (Licht faellt zu den Raendern/vor der Kamera ab)
    r = np.sqrt(((xx-cx)/cx)**2 + ((yy-cy)/cy)**2) / np.sqrt(2)
    v = 1 - p['vig'] * r**2.2 - p['bottom'] * np.clip((yy/H - 0.72) / 0.28, 0, 1)**1.6
    lin = lin * v[..., None]
    # Farbgrading: kuehler Stich, Schatten staerker blau (Lift), Lichter nur leicht
    c = p['cool']
    lum = lin.mean(-1, keepdims=True)
    lin = lin * np.array([1 - 0.020*c, 1 - 0.006*c, 1 + 0.028*c])
    lin = lin + (1 - np.clip(lum*3, 0, 1)) * np.array([0.0015, 0.0030, 0.0065]) * c
    s = lin2srgb(lin)
    # sanfte S-Kurve (Kontrast), Weiss bleibt unter 1
    s = s + 0.24 * (s - 0.5) * (1 - np.abs(2*s - 1))
    # Mikro-Weichheit (Objektiv) + Korn
    s = np.stack([gaussian_filter(s[..., ch], 0.55 * W/1179) for ch in range(3)], -1)
    # Imperfektionen: grossflaechige Fleckigkeit (Boden/Wand), feiner Staub
    low = gaussian_filter(rng.standard_normal((H//8+1, W//8+1)), 6).astype(np.float32); low = np.asarray(Image.fromarray(low/low.std()).resize((W, H), Image.BILINEAR))
    s = s * (1 + 0.006 * low[..., None])
    dust = (rng.random((H, W)) > 0.99965).astype(np.float32); dust = gaussian_filter(dust, 0.9) * 6
    s = s - 0.05 * np.clip(dust, 0, 1)[..., None] * (s.mean(-1, keepdims=True) > 0.6)
    # Filmkorn: mehr in Schatten/Mitten, leichte Farbkomponente, minimal weichgezeichnet
    lum = s.mean(-1, keepdims=True)
    g1 = gaussian_filter(rng.standard_normal((H, W)), 0.6); g1 /= g1.std()
    gc = np.stack([gaussian_filter(rng.standard_normal((H, W)), 0.7) for _ in range(3)], -1); gc /= gc.std()
    amp = 0.0075 + 0.0055 * (1 - lum)
    s = s + amp * g1[..., None] + 0.35 * amp * gc
    return np.clip(s, 0, 1)

if __name__ == '__main__':
    d = sys.argv[1]; shots = sys.argv[2].split(',') if len(sys.argv) > 2 else ['10', '8', '6']
    for k in shots:
        a = np.asarray(Image.open(f'{d}/roh_{k}.png').convert('RGB')).astype(np.float32) / (65535 if Image.open(f'{d}/roh_{k}.png').mode.startswith('I') else 255)
        im = Image.open(f'{d}/roh_{k}.png')
        arr = np.asarray(im)
        a = arr[..., :3].astype(np.float32) / (65535.0 if arr.dtype == np.uint16 else 255.0)
        o = grade(a, SHOT[k], np.random.default_rng(int(k) * 7))
        Image.fromarray((o * 255 + 0.5).astype(np.uint8)).save(f'{d}/final_{k}.png')
        Image.fromarray((o * 255 + 0.5).astype(np.uint8)).save(f'{d}/final_{k}.jpg', quality=93)
        print('post', k)
