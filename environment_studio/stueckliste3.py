"""Beschriftete Explosionszeichnung v3 (zweifarbig) + Stueckliste. python stueckliste3.py <explosion_roh.png> <ausgabe-ordner>
Werte aus PrusaSlicer-Lauf (Bambu-aehnliches Profil, 2 Waende, 3 % Gyroid, 0,24 mm, organische Stuetzen; Farbwechsel/Purge nicht enthalten)."""
import sys, os, json, numpy as np
from PIL import Image, ImageDraw, ImageFont
roh, out = sys.argv[1:3]; os.makedirs(out, exist_ok=True); lab = json.load(open(roh + '.json'))
VIEWS = sys.argv[3:5] if len(sys.argv) > 4 else []     # optional: heck34-, front34-Rohbild (zusammengebaut)
FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
f = ImageFont.truetype(FB, 30); f2 = ImageFont.truetype(FR, 25); f3 = ImageFont.truetype(FR, 20)
TIRE = 95.3/(95.3+37.3)                          # Volumenanteil Reifen (schwarz) am Rad
ROWS = [  # (Nr, Name, Anzahl, Masse mm (Druckausrichtung), g/Stk, schwarz-Anteil, h/Stk, Ausrichtung, Teile in Zeichnung)
 ('1', 'Front + Kabine (ein Stück, Hohlraum mit 45°-Dach, 4 Pfosten)', 1, '168×198×247', 660.2, 1.0, 20.4, 'stehend auf der Trennfläche, Nase oben', ['Karosserie_1_Front_Kabine']),
 ('2', 'Heck-Fahrwerk (durchgehende Ladefläche, Rahmen, Stecker zur Kabine)', 1, '178×187×168', 300.5, 1.0, 10.9, 'wie im Auto (Räder unten)', ['Karosserie_2_Heck']),
 ('3', 'Aufbau: Motorrad, Käfig, Rohre', 1, '151×187×114', 250.9, 1.0, 13.4, 'wie im Auto, 4 Dübelpunkte unten', ['Karosserie_3_Aufbau']),
 ('4–7', 'Rad: Reifen schwarz + Felge weiß, EIN Teil', 4, '81×81×50', 40.9, TIRE, 2.0, 'liegend, Außenseite unten, Zapfen oben', ['Rad_VL', 'Rad_VR', 'Rad_HL', 'Rad_HR']),
 ('8–11', 'Dübel groß ⌀ 5,8 × 24 mm (weiß)', 4, '6×6×24', 0.86, 0.0, 0.14, 'stehend', ['Duebel_%d' % i for i in range(1, 5)]),
 ('12–15', 'Dübel klein ⌀ 3,0 × 13 mm (weiß)', 4, '3×3×13', 0.15, 0.0, 0.03, 'stehend', ['Pin_%d' % i for i in range(1, 5)]),
]
NUM = {}
for nr, nm, cnt, bb, g, bl, h, o, parts in ROWS:
    for i, p in enumerate(parts): NUM[p] = (nr if len(parts) == 1 else str(int(nr.split('–')[0]) + i))
def beschriften(path, labels, small=False):
    im = Image.open(path).convert('RGB'); a = np.asarray(im).astype(np.float32)/255
    a = np.clip((a - 0.50)/(0.96 - 0.50), 0, 1)**1.1; im = Image.fromarray((a*255).astype(np.uint8)); dr = ImageDraw.Draw(im)
    for p, (x, y) in labels.items():
        t = NUM[p]; r = (20 if small else 24) if len(t) < 3 else 30
        dr.ellipse([x-r, y-r, x+r, y+r], fill=(214, 40, 40), outline=(255, 255, 255), width=3)
        w = dr.textlength(t, font=f); dr.text((x-w/2, y-17), t, fill=(255, 255, 255), font=f)
    return im
im = beschriften(roh, lab); W, H = im.size
side = None
if VIEWS:
    ims = []
    for v in VIEWS: ims.append(beschriften(v, json.load(open(v + '.json')), True))
    side = Image.new('RGB', (ims[0].width, sum(i.height for i in ims))); yy = 0
    for i in ims: side.paste(i, (0, yy)); yy += i.height
    sd = ImageDraw.Draw(side); sd.text((20, 14), '3/4 hinten (zusammengebaut)', fill=(60, 60, 70), font=f2); sd.text((20, ims[0].height + 14), '3/4 vorn (zusammengebaut)', fill=(60, 60, 70), font=f2)
LW = 900; leg = Image.new('RGB', (LW, H), (250, 250, 251)); ld = ImageDraw.Draw(leg)
ld.text((24, 18), 'Explosionszeichnung 1:10 · 2 Filamentfarben', fill=(20, 20, 24), font=f)
ld.rectangle([24, 66, 54, 92], fill=(25, 25, 28)); ld.text((62, 64), 'schwarz', fill=(20, 20, 24), font=f2)
ld.rectangle([190, 66, 220, 92], fill=(255, 255, 255), outline=(120, 120, 130)); ld.text((228, 64), 'weiß', fill=(20, 20, 24), font=f2)
y = 120; tot_b = tot_w = tot_h = 0
for nr, nm, cnt, bb, g, bl, h, o, parts in ROWS:
    w = ld.textlength(nr, font=f2); bw = max(56, w+26); ld.rounded_rectangle([24, y, 24+bw, y+46], radius=23, fill=(214, 40, 40)); ld.text((24+bw/2-w/2, y+8), nr, fill=(255, 255, 255), font=f2)
    ld.text((24+max(56, ld.textlength(nr, font=f2)+26)+14, y-4), nm + (' ×%d' % cnt if cnt > 1 else ''), fill=(20, 20, 24), font=f2)
    gb, gw = g*bl*cnt, g*(1-bl)*cnt
    ld.text((124, y+28), '%s mm · %s · %.1f h/Stk' % (bb, ('%.0f g' % g if g >= 10 else '%.1f g' % g) + '/Stk', h), fill=(90, 90, 100), font=f3)
    ld.text((124, y+52), 'schwarz %.0f g · weiß %.0f g gesamt · %s' % (gb, gw, o), fill=(90, 90, 100), font=f3)
    tot_b += gb; tot_w += gw; tot_h += h*cnt; y += 112
ld.line([24, y+4, LW-24, y+4], fill=(190, 190, 195), width=2)
ld.text((24, y+16), 'Summe: schwarz %.0f g · weiß %.0f g · %.0f g PLA' % (tot_b, tot_w, tot_b+tot_w), fill=(20, 20, 24), font=f2)
ld.text((24, y+52), 'Druckzeit ≈ %.0f h (ohne Farbwechsel/Purge)' % tot_h, fill=(20, 20, 24), font=f2)
SW = side.width if side else 0
res = Image.new('RGB', (SW+W+LW, H)); 
if side: res.paste(side.resize((SW, H)), (0, 0))
res.paste(im, (SW, 0)); res.paste(leg, (SW+W, 0)); res.save(os.path.join(out, 'explosion_zweifarbig.png'))
md = ['| Nr | Teil | Anz. | Maße (mm) | schwarz g | weiß g | Zeit h | Ausrichtung |', '|---|---|---|---|---|---|---|---|']
for nr, nm, cnt, bb, g, bl, h, o, parts in ROWS:
    md.append('| %s | %s | %d | %s | %.0f | %.0f | %.1f | %s |' % (nr, nm, cnt, bb, g*bl*cnt, g*(1-bl)*cnt, h*cnt, o))
md.append('| | **Summe** | | | **%.0f** | **%.0f** | **%.0f** | |' % (tot_b, tot_w, tot_h))
open(os.path.join(out, 'stueckliste_v3.md'), 'w').write('\n'.join(md) + '\n'); print('\n'.join(md))
