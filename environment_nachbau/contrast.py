"""Kontrast-Vergleich Foto vs. Render (beide auf 720 px): Helligkeits-Perzentile, Textur-Kontrast je Region, Saettigung.
Aufruf: python contrast.py <render.png> [render2.png ...]"""
import sys, numpy as np
from PIL import Image, ImageFilter
REF = '/root/.claude/uploads/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/c2a87a4f-image.jpg'
REG = {'Decke': (300, 20, 500, 80), 'Wand links schattig': (20, 150, 120, 250), 'Wand links sonnig': (190, 290, 280, 380),
       'Rueckwand': (420, 200, 520, 300), 'Boden vorn': (200, 600, 450, 700), 'Pfeiler': (650, 200, 690, 400)}
def load(p): return np.asarray(Image.open(p).convert('RGB').resize((720, 720), Image.LANCZOS)).astype(float)
def lum(a): return a @ np.array([0.2126, 0.7152, 0.0722])
def hp(a):   # Textur-Kontrast: Standardabweichung des Hochpass (Original - Unschaerfe 4 px), relativ zur mittleren Helligkeit
    g = Image.fromarray(a.astype(np.uint8)).convert('L'); b = g.filter(ImageFilter.GaussianBlur(4))
    return np.asarray(g).astype(float) - np.asarray(b).astype(float)
def sat(a):
    mx, mn = a.max(2), a.min(2); return ((mx - mn) / np.maximum(mx, 1)).mean()
def report(name, a):
    L = lum(a); p = np.percentile(L, [2, 10, 25, 50, 75, 90, 98])
    print(f'{name:14s} Perzentile 2/10/25/50/75/90/98: ' + ' '.join(f'{v:5.0f}' for v in p) + f'   Spreizung 10-90: {p[5]-p[1]:4.0f}   Anteil >245: {100*(L>245).mean():4.1f}%  <20: {100*(L<20).mean():4.1f}%  Saettigung {sat(a):.3f}')
    return a
ref = load(REF); rs = [(p.split('/')[-1], load(p)) for p in sys.argv[1:]]
report('Foto', ref)
for n, a in rs: report(n[:14], a)
print('\nTextur-Kontrast (Std. Hochpass, 8-bit-Stufen) je Region:')
print(f"{'Region':22s} {'Foto':>6s} " + ' '.join(f'{n[:10]:>10s}' for n, _ in rs))
for k, (x0, y0, x1, y1) in REG.items():
    f = hp(ref)[y0:y1, x0:x1].std(); print(f'{k:22s} {f:6.2f} ' + ' '.join(f'{hp(a)[y0:y1, x0:x1].std():10.2f}' for _, a in rs))
print('\nGrossflaechiger Kontrast je Region (Std. der Helligkeit, 8 px Unschaerfe):')
def lo(a):
    g = Image.fromarray(a.astype(np.uint8)).convert('L').filter(ImageFilter.GaussianBlur(8)); return np.asarray(g).astype(float)
for k, (x0, y0, x1, y1) in REG.items():
    f = lo(ref)[y0:y1, x0:x1].std(); print(f'{k:22s} {f:6.2f} ' + ' '.join(f'{lo(a)[y0:y1, x0:x1].std():10.2f}' for _, a in rs))
