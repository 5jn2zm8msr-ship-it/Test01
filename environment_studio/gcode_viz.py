"""Auswertung/Visualisierung von PrusaSlicer-G-Code: Volumen je Strukturtyp, Seitenschnitt (y = Mitte), Schichtansichten.
python gcode_viz.py <datei.gcode> <ausgabeprefix> <hoehe_mm> [schnitt_y=128]"""
import sys, re, json, numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
path, pre, H = sys.argv[1], sys.argv[2], float(sys.argv[3]); CY = float(sys.argv[4]) if len(sys.argv) > 4 else 128.0
COL = {'Perimeter': '#9aa0a6', 'External perimeter': '#5f6368', 'Overhang perimeter': '#e8710a', 'Internal infill': '#4285f4', 'Solid infill': '#8ab4f8', 'Top solid infill': '#aecbfa',
       'Bridge infill': '#a142f4', 'Support material': '#ea4335', 'Support material interface': '#fbbc04', 'Gap fill': '#34a853', 'Skirt/Brim': '#cccccc', 'Ironing': '#cccccc'}
NAME = {'Perimeter': 'Wand innen', 'External perimeter': 'Wand außen', 'Overhang perimeter': 'Überhang-Wand', 'Internal infill': 'Infill (Gyroid)', 'Solid infill': 'Vollfläche',
        'Top solid infill': 'Deckfläche', 'Bridge infill': 'Brücke', 'Support material': 'Stütze', 'Support material interface': 'Stütz-Kontaktschicht', 'Gap fill': 'Lückenfüllung', 'Skirt/Brim': 'Brim'}
vol = {}; pts = {}; layers = {}                 # Schnittpunkte je Typ; Schichten (z -> Segmente je Typ)
TARGET = [round(H*f, 1) for f in (0.25, 0.55, 0.85)]
typ = None; x = y = z = 0.0; r = 0.875**2*np.pi   # mm2 Filamentquerschnitt
pending = {}
for line in open(path, errors='ignore'):
    if line.startswith(';TYPE:'): typ = line[6:].strip(); continue
    if not line.startswith('G1'): continue
    nx, ny, nz, e = x, y, z, 0.0
    for tok in line.split(';')[0].split()[1:]:
        c = tok[0]
        if c == 'X': nx = float(tok[1:])
        elif c == 'Y': ny = float(tok[1:])
        elif c == 'Z': nz = float(tok[1:])
        elif c == 'E': e = float(tok[1:])
    if e > 0 and typ and (nx != x or ny != y):
        vol[typ] = vol.get(typ, 0.0) + e*r
        if (y - CY)*(ny - CY) < 0:
            t = (CY - y)/(ny - y); pts.setdefault(typ, []).append((x + t*(nx - x), z))
        for T in TARGET:
            if abs(z - T) < 0.13: layers.setdefault(T, {}).setdefault(typ, []).append(((x, y), (nx, ny)))
    x, y, z = nx, ny, nz
tot = sum(vol.values()); stats = {k: dict(cm3=round(v/1000, 2), prozent=round(100*v/tot, 1)) for k, v in sorted(vol.items(), key=lambda kv: -kv[1])}
json.dump(dict(gesamt_cm3=round(tot/1000, 1), typen=stats), open(pre + '_stats.json', 'w'), indent=1, ensure_ascii=False); print(json.dumps(stats, ensure_ascii=False)[:600])
# Seitenschnitt
allp = np.array([p for v in pts.values() for p in v]); xr = np.ptp(allp[:, 0]) + 10; zr = np.ptp(allp[:, 1]) + 10
fig, ax = plt.subplots(figsize=(11, max(3.0, min(11*zr/xr, 12)) + 0.8), dpi=170); ax.set_facecolor('#101114'); fig.patch.set_facecolor('#101114')
order = ['Skirt/Brim', 'Internal infill', 'Solid infill', 'Top solid infill', 'Perimeter', 'External perimeter', 'Gap fill', 'Support material', 'Support material interface', 'Bridge infill', 'Overhang perimeter']
for t in order:
    if t in pts:
        a = np.array(pts[t]); ax.scatter(a[:, 0], a[:, 1], s=max(1.5, 3600/xr), c=COL.get(t, '#fff'), marker='s', linewidths=0, label=NAME.get(t, t))
ax.set_aspect('equal'); ax.tick_params(colors='#aaa'); [sp.set_color('#444') for sp in ax.spines.values()]
ax.set_xlabel('x (mm), Bett', color='#bbb'); ax.set_ylabel('z (mm), Bauhöhe', color='#bbb'); ax.set_title('Seitenschnitt durch den G-Code (y = %.0f mm)' % CY, color='#eee')
lg = ax.legend(markerscale=1.0, facecolor='#1b1c20', edgecolor='#444', labelcolor='#ddd', fontsize=9, loc='upper left', bbox_to_anchor=(1.0, 1.0)); fig.savefig(pre + '_schnitt.png', facecolor=fig.get_facecolor(), bbox_inches='tight'); plt.close(fig)
# Schichtansichten
fig, axs = plt.subplots(1, len(layers), figsize=(5.4*len(layers), 5.6), dpi=170); fig.patch.set_facecolor('#101114')
axs = np.atleast_1d(axs)
for ax, T in zip(axs, sorted(layers)):
    ax.set_facecolor('#101114')
    for t in order:
        if t in layers[T]: ax.add_collection(LineCollection(layers[T][t], colors=COL.get(t, '#fff'), linewidths=0.35))
    ax.autoscale(); ax.set_aspect('equal'); ax.set_title('Schicht bei z = %.1f mm' % T, color='#eee', fontsize=11); ax.tick_params(colors='#888', labelsize=7)
    [sp.set_color('#444') for sp in ax.spines.values()]
fig.tight_layout(); fig.savefig(pre + '_schichten.png', facecolor=fig.get_facecolor()); plt.close(fig)
