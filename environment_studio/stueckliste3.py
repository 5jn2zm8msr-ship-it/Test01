"""Beschriftete Explosionszeichnung v3 (zweifarbig) + Stueckliste. python stueckliste3.py <explosion_roh.png> <ausgabe-ordner>
Werte aus PrusaSlicer-Lauf (Bambu-aehnliches Profil, 2 Waende, 5 % Gyroid, 0,24 mm, organische Stuetzen; Farbwechsel/Purge nicht enthalten)."""
import sys, os, json, numpy as np
from PIL import Image, ImageDraw, ImageFont
roh, out = sys.argv[1:3]; os.makedirs(out, exist_ok=True); lab = json.load(open(roh + '.json'))
FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
f = ImageFont.truetype(FB, 30); f2 = ImageFont.truetype(FR, 25); f3 = ImageFont.truetype(FR, 20)
TIRE = 100.0/(100.0+39.9)                          # Volumenanteil Reifen (schwarz) am Rad
RAD_G, RAD_H = 38.3, 1.6
ROWS = [  # (Nr-Label, Name, Anzahl, Masse mm (Druckausrichtung), g gesamt/Stk, schwarz-Anteil, h/Stk, Ausrichtung, Teile in Zeichnung)
 ('1', 'Karosserie Front (Motorraum, Keil, massiv)', 1, '167×197×174', 489.8, 1.0, 15.6, 'stehend auf der Trennfläche, Nase oben', ['Karosserie_1_Front']),
 ('2', 'Kabine (hohles Prisma 3 mm, Fenster zu, 4 Pfosten)', 1, '149×195×85', 203.2, 1.0, 5.8, 'stehend auf einem Ende, innen offen', ['Karosserie_2_Kabine']),
 ('3', 'Heck (Pritsche, Käfig, Motorrad, Stecker)', 1, '168×186×169', 436.6, 1.0, 18.3, 'stehend auf der Trennfläche', ['Karosserie_3_Heck']),
 ('4–7', 'Rad: Reifen schwarz + Felge weiß, EIN Teil', 4, '81×81×50', RAD_G, TIRE, RAD_H, 'liegend, Außenseite unten, Zapfen oben', ['Rad_VL', 'Rad_VR', 'Rad_HL', 'Rad_HR']),
 ('8–15', 'Dübel ⌀ 5,8 × 24 mm (weiß)', 8, '6×6×24', 0.86, 0.0, 0.14, 'stehend', ['Duebel_%d' % i for i in range(1, 9)]),
]
NUM = {}
for nr, nm, cnt, bb, g, bl, h, o, parts in ROWS:
    for i, p in enumerate(parts): NUM[p] = (nr if len(parts) == 1 else str(int(nr.split('–')[0]) + i))
im = Image.open(roh).convert('RGB'); a = np.asarray(im).astype(np.float32)/255
a = np.clip((a - 0.02)/(0.97 - 0.02), 0, 1); im = Image.fromarray((a*255).astype(np.uint8)); W, H = im.size
dr = ImageDraw.Draw(im)
for p, (x, y) in lab.items():
    t = NUM[p]; r = 24 if len(t) < 3 else 30
    dr.ellipse([x-r, y-r, x+r, y+r], fill=(214, 40, 40), outline=(255, 255, 255), width=3)
    w = dr.textlength(t, font=f); dr.text((x-w/2, y-17), t, fill=(255, 255, 255), font=f)
LW = 900; leg = Image.new('RGB', (LW, H), (250, 250, 251)); ld = ImageDraw.Draw(leg)
ld.text((24, 18), 'Explosionszeichnung 1:10 · 2 Filamentfarben', fill=(20, 20, 24), font=f)
ld.rectangle([24, 66, 54, 92], fill=(25, 25, 28)); ld.text((62, 64), 'schwarz', fill=(20, 20, 24), font=f2)
ld.rectangle([190, 66, 220, 92], fill=(255, 255, 255), outline=(120, 120, 130)); ld.text((228, 64), 'weiß', fill=(20, 20, 24), font=f2)
y = 120; tot_b = tot_w = tot_h = 0
for nr, nm, cnt, bb, g, bl, h, o, parts in ROWS:
    ld.ellipse([24, y, 80, y+46], fill=(214, 40, 40)); w = ld.textlength(nr, font=f2); ld.text((52-w/2, y+8), nr, fill=(255, 255, 255), font=f2)
    ld.text((96, y-4), nm + (' ×%d' % cnt if cnt > 1 else ''), fill=(20, 20, 24), font=f2)
    gb, gw = g*bl*cnt, g*(1-bl)*cnt
    ld.text((96, y+28), '%s mm · %s · %.1f h/Stk' % (bb, ('%.0f g' % g if g >= 10 else '%.1f g' % g) + '/Stk', h), fill=(90, 90, 100), font=f3)
    ld.text((96, y+52), 'schwarz %.0f g · weiß %.0f g gesamt · %s' % (gb, gw, o), fill=(90, 90, 100), font=f3)
    tot_b += gb; tot_w += gw; tot_h += h*cnt; y += 112
ld.line([24, y+4, LW-24, y+4], fill=(190, 190, 195), width=2)
ld.text((24, y+16), 'Summe: schwarz %.0f g · weiß %.0f g · %.0f g PLA' % (tot_b, tot_w, tot_b+tot_w), fill=(20, 20, 24), font=f2)
ld.text((24, y+52), 'Druckzeit ≈ %.0f h (ohne Farbwechsel/Purge)' % tot_h, fill=(20, 20, 24), font=f2)
res = Image.new('RGB', (W+LW, H)); res.paste(im, (0, 0)); res.paste(leg, (W, 0)); res.save(os.path.join(out, 'explosion_zweifarbig.png'))
md = ['| Nr | Teil | Anz. | Maße (mm) | schwarz g | weiß g | Zeit h | Ausrichtung |', '|---|---|---|---|---|---|---|---|']
for nr, nm, cnt, bb, g, bl, h, o, parts in ROWS:
    md.append('| %s | %s | %d | %s | %.0f | %.0f | %.1f | %s |' % (nr, nm, cnt, bb, g*bl*cnt, g*(1-bl)*cnt, h*cnt, o))
md.append('| | **Summe** | | | **%.0f** | **%.0f** | **%.0f** | |' % (tot_b, tot_w, tot_h))
open(os.path.join(out, 'stueckliste_v3.md'), 'w').write('\n'.join(md) + '\n'); print('\n'.join(md))
