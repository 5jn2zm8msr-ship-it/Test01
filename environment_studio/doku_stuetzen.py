"""Dokublatt Stuetzen/Bruecken aus den G-Code-Auswertungen. python doku_stuetzen.py <viz-ordner> <ausgabe.png>"""
import sys, json
from PIL import Image, ImageDraw, ImageFont
d, out = sys.argv[1:3]
FB = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; FR = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
f = ImageFont.truetype(FB, 34); f2 = ImageFont.truetype(FR, 24); f3 = ImageFont.truetype(FR, 21)
S = {n: json.load(open(f'{d}/{n}_stats.json')) for n in ('front6', 'heck6', 'aufbau6', 'rad6')}
NAMES = {'front6': 'Front + Kabine', 'heck6': 'Heck-Fahrwerk', 'aufbau6': 'Aufbau (Motorrad)', 'rad6': 'Rad (1 Stück)'}
def share(n, k): return S[n]['typen'].get(k, {}).get('prozent', 0.0)
W = 2800; pad = 40
a = Image.open(f'{d}/aufbau6_schnitt.png').convert('RGB'); b = Image.open(f'{d}/front6_schichten.png').convert('RGB')
a.thumbnail((W-2*pad, 1300)); b.thumbnail((W-2*pad, 800))
tab_h = 330
H = pad + 60 + a.height + pad + 60 + b.height + pad + 60 + tab_h + pad
im = Image.new('RGB', (W, H), (16, 17, 20)); dr = ImageDraw.Draw(im); y = pad
dr.text((pad, y), 'Seitenschnitt durch den gesliceten Druck: Aufbau mit Motorrad (Schnittebene y = 128 mm)', fill=(235, 235, 240), font=f); y += 60
im.paste(a, ((W-a.width)//2, y)); y += a.height + pad
dr.text((pad, y), 'Schichtansichten Front + Kabine (25 %, 55 %, 85 % der Bauhöhe): rote Inseln = Stützen, blau = Gyroid-Infill, violett = Brücken', fill=(235, 235, 240), font=f); y += 60
im.paste(b, ((W-b.width)//2, y)); y += b.height + pad
dr.text((pad, y), 'Materialanteile nach Strukturtyp (Volumen, PrusaSlicer-Lauf, 2 Wände, 3 % Gyroid, 0,24 mm, organische Stützen)', fill=(235, 235, 240), font=f); y += 70
cols = ['Teil', 'Wände', 'Infill', 'Vollfläche/Deckel', 'Brücken', 'Stützen (+ Kontaktschicht)', 'Gesamt cm³']; xs = [pad, 330, 560, 790, 1130, 1380, 1900]
for c, x in zip(cols, xs): dr.text((x, y), c, fill=(150, 160, 175), font=f3)
y += 40
for n in ('front6', 'heck6', 'aufbau6', 'rad6'):
    row = [NAMES[n], '%.0f %%' % (share(n, 'Perimeter') + share(n, 'External perimeter') + share(n, 'Overhang perimeter')), '%.0f %%' % share(n, 'Internal infill'),
           '%.0f %%' % (share(n, 'Solid infill') + share(n, 'Top solid infill')), '%.1f %%' % share(n, 'Bridge infill'),
           '%.1f %%' % (share(n, 'Support material') + share(n, 'Support material interface')), '%.0f' % S[n]['gesamt_cm3']]
    for c, x in zip(row, xs): dr.text((x, y), c, fill=(235, 235, 240) if x != xs[5] else (255, 120, 100), font=f2)
    y += 44
im.save(out); print(im.size)
