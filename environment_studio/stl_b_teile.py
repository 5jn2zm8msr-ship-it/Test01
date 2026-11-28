"""Stufe B: Huelle (1:10, mm) in druckbare Teile zerlegen, Zapfen/Bohrungen mit Spiel, Pruefung.
python stl_b_teile.py <solid_full.stl> <ausgabeordner>
Teile: 4 Raeder (Zapfen), Koerper vorn/hinten (Trennung x=-8, 4 Duebel-Bosse), 2 Spiegel, Reserverad, 4 lose Duebel."""
import sys, os, json, numpy as np, trimesh, manifold3d as mf
src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
SP = 0.2            # Spiel je Seite (mm) fuer Steckverbindungen
SEG = 64
def to_man(m): return mf.Manifold(mf.Mesh(np.asarray(m.vertices, np.float32), np.asarray(m.faces, np.uint32)))
def to_tm(M):
    r = M.to_mesh(); return trimesh.Trimesh(np.asarray(r.vert_properties)[:, :3].astype(np.float64), np.asarray(r.tri_verts), process=False)
def cyl_x(x0, x1, y, z, r):   # Zylinder entlang x
    c = mf.Manifold.cylinder(abs(x1-x0), r, r, SEG).rotate([0, 90, 0]); return c.translate([min(x0, x1), y, z])
def cyl_y(y0, y1, x, z, r):   # Zylinder entlang y
    c = mf.Manifold.cylinder(abs(y1-y0), r, r, SEG).rotate([-90, 0, 0]); return c.translate([x, min(y0, y1), z])
def cyl_z(z0, z1, x, y, r):
    c = mf.Manifold.cylinder(abs(z1-z0), r, r, SEG); return c.translate([x, y, min(z0, z1)])
def box(x0, x1, y0, y1, z0, z1): return mf.Manifold.cube([x1-x0, y1-y0, z1-z0]).translate([x0, y0, z0])
def U(*a):
    r = a[0]
    for b in a[1:]: r = r + b
    return r

S0 = trimesh.load(src); S0.merge_vertices()
S = to_man(S0); print('Huelle V=%.1f cm3' % (S.volume()/1000))
info = {}
# ---------------- Raeder ----------------
WHEELS = {'Rad_VL': (-159.0, -1), 'Rad_VR': (-159.0, 1), 'Rad_HL': (116.0, -1), 'Rad_HR': (116.0, 1)}
CZ, RW, Y_CUT = 40.0, 41.0, 62.4
PIN_D, HOLE_D = 6.0, 6.0 + 2*SP
wheel_cuts, parts = [], {}
for name, (cx, sg) in WHEELS.items():
    y0, y1 = (Y_CUT, 104.0) if sg > 0 else (-104.0, -Y_CUT)
    cyl = cyl_y(y0, y1, cx, CZ, RW); wheel_cuts.append(cyl)
    w = S ^ cyl                      # Schnitt
    # Nabe innen: Aufnahme (Boss) + Zapfen Richtung Karosserie
    yb_in, yb_out = (63.5, 81.0) if sg > 0 else (-81.0, -63.5)
    boss = cyl_y(yb_in, yb_out, cx, CZ, 6.0)
    ypin = (50.8, 64.0) if sg > 0 else (-64.0, -50.8)
    pin = cyl_y(ypin[0], ypin[1], cx, CZ, PIN_D/2)
    parts[name] = U(w, boss, pin)
# ---------------- Spiegel / Reserverad ----------------
MIRR = {'Spiegel_L': -1, 'Spiegel_R': 1}
mir_cuts = []
for name, sg in MIRR.items():
    ya, yb = (86.0, 100.0) if sg > 0 else (-100.0, -86.0)
    bx = box(-109, -98.5, ya, yb, 123, 151); mir_cuts.append(bx)
    head = S ^ bx
    y_in = sg*78.8; y_hd = sg*91.5
    arm = cyl_y(min(y_in, y_hd), max(y_in, y_hd), -104.0, 133.0, 1.75)
    post = cyl_z(122.0, 133.0, -104.0, y_in, 1.5)
    parts[name] = U(head, arm, post)
sp_box = box(-14, 30, -96, -83.4, 68, 128)
spare = S ^ sp_box
sp_pins = [cyl_y(-85.0, -78.5, 8.0, z, 2.0) for z in (88.0, 108.0)]
parts['Reserverad'] = U(spare, *sp_pins)
# ---------------- Koerper ----------------
B = S
for c in wheel_cuts + mir_cuts + [sp_box]: B = B - c
# Loecher: Radzapfen, Spiegelpfosten, Reserverad
holes = []
for name, (cx, sg) in WHEELS.items():
    yh = (48.5, 61.5) if sg > 0 else (-61.5, -48.5)
    holes.append(cyl_y(yh[0], yh[1], cx, CZ, HOLE_D/2))
for name, sg in MIRR.items(): holes.append(cyl_z(122.0, 128.5, -104.0, sg*78.8, 1.5+SP))
for z in (88.0, 108.0): holes.append(cyl_y(-84.0, -77.5, 8.0, z, 2.0+SP))
# Duebel-Bosse + Trennung
XC, GAP, BL = -8.0, 0.15, 15.0
BOSS = [(-71.0, 78.0), (71.0, 78.0), (-66.0, 182.0), (66.0, 182.0)]
DOW_D = 5.8
bosses = [cyl_x(XC-BL, XC+BL, y, z, 5.5) for (y, z) in BOSS]
B = U(B, *bosses)
dh = [cyl_x(XC-GAP-13.0, XC-GAP+0.01, y, z, (DOW_D+2*SP)/2) for (y, z) in BOSS] + [cyl_x(XC+GAP-0.01, XC+GAP+13.0, y, z, (DOW_D+2*SP)/2) for (y, z) in BOSS]
diag = []
for h in holes + dh:
    inside = (B ^ h).volume(); diag.append(round(inside / h.volume(), 2)); B = B - h
print('Bohrungen: Anteil im Material (1.0 = komplett im Massiv, <1 = ragt in Hohlraum):', diag)
info['_bohrungen_anteil'] = diag
F = B ^ box(-300, XC-GAP, -150, 150, -5, 300)
R = B ^ box(XC+GAP, 300, -150, 150, -5, 300)
parts['Karosserie_vorn'] = F; parts['Karosserie_hinten'] = R
# lose Duebel
for i in range(4): parts['Duebel_%d' % (i+1)] = cyl_z(0, 24.0, 0, 0, DOW_D/2)
# ---------------- Pruefung/Export ----------------
tot = 0
for name, M in parts.items():
    t = to_tm(M)
    comps = t.split(only_watertight=False)
    comps = sorted(comps, key=lambda c: -abs(c.volume))
    keep = [c for c in comps if abs(c.volume) > 100.0]       # >100 mm3
    if name.startswith('Karosserie'): keep = keep[:1]            # lose Einzelteile im Hohlraum (z. B. Sitzreste) verwerfen
    dropped = [round(abs(c.volume), 1) for c in comps if abs(c.volume) <= 100.0] + ([round(abs(c.volume), 1) for c in comps if name.startswith('Karosserie') and c not in keep and abs(c.volume) > 100.0])
    t = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]
    info[name] = dict(faces=len(t.faces), vol_cm3=round(abs(t.volume)/1000, 2), area_cm2=round(t.area/100, 1),
                      bbox_mm=[round(v, 1) for v in (t.bounds[1]-t.bounds[0])], watertight=bool(t.is_watertight),
                      huellen=len(keep), kleinteile_verworfen=len(dropped), grosse_huellen_vol_mm3=[round(abs(c.volume)) for c in keep[:6]])
    t.export(os.path.join(out, name + '.stl'))
    print(name, {k: (float(v) if isinstance(v, np.floating) else v) for k, v in info[name].items()}); tot += abs(t.volume)
    if len(keep) > 1: print('   Huellen-Schwerpunkte', [(round(abs(c.volume)), [round(v) for v in c.centroid]) for c in keep[:6]])
json.dump(info, open(os.path.join(out, 'teile.json'), 'w'), indent=1, default=float)
print('Summe Volumen cm3: %.1f' % (tot/1000))
