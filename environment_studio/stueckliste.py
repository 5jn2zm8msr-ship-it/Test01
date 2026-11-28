"""Stueckliste + beschriftete Explosionszeichnung. python stueckliste.py <teile-ordner> <pruefung.json> <explosion_roh.png> <ausgabe-ordner>"""
import sys, os, json, numpy as np
from PIL import Image, ImageDraw, ImageFont
d, pj, roh, out = sys.argv[1:5]; os.makedirs(out, exist_ok=True)
info = json.load(open(os.path.join(d, 'teile.json'))); pr = json.load(open(pj)); lab = json.load(open(roh + '.json'))
ORDER = ['Karosserie_vorn', 'Karosserie_hinten', 'Rad_VL', 'Rad_VR', 'Rad_HL', 'Rad_HR', 'Spiegel_L', 'Spiegel_R', 'Reserverad', 'Duebel_1', 'Duebel_2', 'Duebel_3', 'Duebel_4']
NAMES = {'Karosserie_vorn': 'Karosserie vorn', 'Karosserie_hinten': 'Karosserie hinten (Pritsche/Kabine)', 'Rad_VL': 'Rad vorn links', 'Rad_VR': 'Rad vorn rechts',
         'Rad_HL': 'Rad hinten links', 'Rad_HR': 'Rad hinten rechts', 'Spiegel_L': 'Spiegel links', 'Spiegel_R': 'Spiegel rechts', 'Reserverad': 'Reserverad (Tür)',
         'Duebel_1': 'Dübel 1', 'Duebel_2': 'Dübel 2', 'Duebel_3': 'Dübel 3', 'Duebel_4': 'Dübel 4'}
ORIENT = {'Karosserie_vorn': 'stehend auf der Trennfläche (Front oben)', 'Karosserie_hinten': 'stehend auf der Trennfläche (Heck oben)',
          'Rad_': 'liegend, Außenseite unten, Zapfen oben', 'Spiegel': 'liegend', 'Reserverad': 'liegend', 'Duebel': 'liegend'}
orient = lambda n: next(v for k, v in ORIENT.items() if n.startswith(k))
D1 = pr['Duebel_1']; rows = []; tot = dict(g=0, h=0, cm3=0)
for n in ORDER:
    p = pr.get(n) or D1; i = info.get(n) or info['Duebel_1']
    k = i['vol_cm3'] / p['volumen_cm3']                     # Raster -> exakte Mesh-Volumen
    g = p['gramm'] * k; h = p['zeit_h'] * k + (0.02 if n.startswith('Duebel') else 0)
    rows.append((n, NAMES[n], i['bbox_mm'], i['vol_cm3'], g, h, p['duenn_prozent'], orient(n)))
    tot['g'] += g; tot['h'] += h; tot['cm3'] += i['vol_cm3']
# Explosionsbild beschriften
im = Image.open(roh).convert('RGB'); a = np.asarray(im).astype(np.float32)/255
a = np.clip((a - 0.50)/(0.96 - 0.50), 0, 1)**1.1                 # Kontrast
im = Image.fromarray((a*255).astype(np.uint8)); W, H = im.size
dr = ImageDraw.Draw(im)
try: f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30); f2 = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 26)
except Exception: f = f2 = ImageFont.load_default()
for i, n in enumerate(ORDER):
    x, y = lab[n]; r = 22
    dr.ellipse([x-r, y-r, x+r, y+r], fill=(20, 20, 24), outline=(255, 255, 255), width=3)
    t = str(i+1); w = dr.textlength(t, font=f); dr.text((x-w/2, y-17), t, fill=(255, 255, 255), font=f)
leg = Image.new('RGB', (760, H), (250, 250, 251)); ld = ImageDraw.Draw(leg)
ld.text((24, 20), 'Explosionszeichnung 1:10 – %d Teile' % len(ORDER), fill=(20, 20, 24), font=f)
for i, (n, nm, bb, v, g, h, th, o) in enumerate(rows):
    yy = 80 + i*58
    ld.ellipse([24, yy, 68, yy+44], fill=(20, 20, 24)); t = str(i+1); w = ld.textlength(t, font=f); ld.text((46-w/2, yy+5), t, fill=(255, 255, 255), font=f)
    ld.text((84, yy-2), nm, fill=(20, 20, 24), font=f2); ld.text((84, yy+26), '%d×%d×%d mm · %s g · %.1f h' % (bb[0], bb[1], bb[2], ('%.1f' % g if g < 10 else '%.0f' % g), h), fill=(90, 90, 100), font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20))
ld.text((24, H-60), 'Summe: %.0f g PLA · %.0f h (ohne Stützen)' % (tot['g'], tot['h']), fill=(20, 20, 24), font=f2)
res = Image.new('RGB', (W + leg.width, H)); res.paste(im, (0, 0)); res.paste(leg, (W, 0)); res.save(os.path.join(out, 'explosion_teile.png'))
# Markdown
md = ['| Nr | Teil | Maße (mm) | Volumen cm³ | Filament g | Zeit h | Druckausrichtung |', '|---|---|---|---|---|---|---|']
for i, (n, nm, bb, v, g, h, th, o) in enumerate(rows):
    md.append('| %d | %s | %.0f × %.0f × %.0f | %.1f | %s | %.1f | %s |' % (i+1, nm, bb[0], bb[1], bb[2], v, ('%.1f' % g if g < 10 else '%.0f' % g), h, o))
md.append('| | **Summe** | | **%.0f** | **%.0f** | **%.0f** | |' % (tot['cm3'], tot['g'], tot['h']))
open(os.path.join(out, 'stueckliste.md'), 'w').write('\n'.join(md) + '\n'); print('\n'.join(md)); print(tot)
