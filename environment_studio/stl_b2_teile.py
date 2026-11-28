"""Stufe B2 (vereinfacht, wenig Stuetzmaterial): 3 Karosserieteile auf ebenen Trennflaechen + 1 Rad (4x, zweifarbig) + Duebel.
python stl_b2_teile.py <solid_simple.stl> <ausgabeordner>
Teile: Karosserie_1_Front (x < -100), Karosserie_2_Kabine (-100..45), Karosserie_3_Heck (> 45), Rad_Reifen (schwarz), Rad_Felge (weiss, mit Zapfen), Duebel."""
import sys, os, json, numpy as np, trimesh, manifold3d as mf
src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
SP = 0.2; SEG = 64
def to_man(m): return mf.Manifold(mf.Mesh(np.asarray(m.vertices, np.float32), np.asarray(m.faces, np.uint32)))
def to_tm(M):
    r = M.to_mesh(); return trimesh.Trimesh(np.asarray(r.vert_properties)[:, :3].astype(np.float64), np.asarray(r.tri_verts), process=False)
def cyl_x(x0, x1, y, z, r): return mf.Manifold.cylinder(abs(x1-x0), r, r, SEG).rotate([0, 90, 0]).translate([min(x0, x1), y, z])
def cyl_y(y0, y1, x, z, r): return mf.Manifold.cylinder(abs(y1-y0), r, r, SEG).rotate([-90, 0, 0]).translate([x, min(y0, y1), z])
def box(x0, x1, y0, y1, z0, z1): return mf.Manifold.cube([x1-x0, y1-y0, z1-z0]).translate([x0, y0, z0])
def U(*a):
    r = a[0]
    for b in a[1:]: r = r + b
    return r
S0 = trimesh.load(src); S0.merge_vertices(); S = to_man(S0); print('Huelle V=%.1f cm3' % (S.volume()/1000))
CZ, RW, Y_CUT = 40.0, 41.0, 62.4
WHEELS = {'VL': (-159.0, -1), 'VR': (-159.0, 1), 'HL': (116.0, -1), 'HR': (116.0, 1)}
PIN_D, HOLE_D = 6.0, 6.0 + 2*SP; R_RIM = 24.0
cuts = []
for k, (cx, sg) in WHEELS.items():
    y0, y1 = (Y_CUT, 104.0) if sg > 0 else (-104.0, -Y_CUT); cuts.append(cyl_y(y0, y1, cx, CZ, RW))
# ---- ein Rad (hinten links als Vorlage), Zapfen Richtung +y (wird fuer rechts gedreht) ----
cx = 116.0
wheel = S ^ cyl_y(-104.0, -Y_CUT, cx, CZ, RW)
boss = cyl_y(-81.0, -63.5, cx, CZ, 6.0); pin = cyl_y(-64.0, -50.8, cx, CZ, PIN_D/2)
rim = (wheel ^ cyl_y(-104.0, -Y_CUT, cx, CZ, R_RIM)) + boss + pin
tire = wheel - cyl_y(-104.0, -Y_CUT, cx, CZ, R_RIM)
# in Wurzelposition (Radmitte im Ursprung, Zapfen nach +y) bringen
def centre(M): return M.translate([-cx, 0, -CZ])
parts = {'Rad_Reifen_schwarz': centre(tire), 'Rad_Felge_weiss': centre(rim)}
# ---- Karosserie ----
B = S
for c in cuts: B = B - c
holes = []
for k, (cx_, sg) in WHEELS.items():
    yh = (48.5, 61.5) if sg > 0 else (-61.5, -48.5); holes.append(cyl_y(yh[0], yh[1], cx_, CZ, HOLE_D/2))
X1, X2, GAP, DEPTH = -100.0, 45.0, 0.15, 13.0
DOW_D = 5.8; DPOS = {X1: [(-50, 70), (50, 70), (-50, 115), (50, 115)], X2: [(-50, 105), (50, 105), (-50, 160), (50, 160)]}
dh = []
for X, pts in DPOS.items():
    for (y, z) in pts:
        dh.append(cyl_x(X-GAP-DEPTH, X-GAP+0.01, y, z, (DOW_D+2*SP)/2)); dh.append(cyl_x(X+GAP-0.01, X+GAP+DEPTH, y, z, (DOW_D+2*SP)/2))
diag = []
for h in holes + dh:
    diag.append(round((B ^ h).volume() / h.volume(), 2)); B = B - h
print('Bohrungen im Material (1.0 = ganz massiv):', diag)
BIG = 400
parts['Karosserie_1_Front'] = B ^ box(-BIG, X1-GAP, -BIG, BIG, -5, BIG)
parts['Karosserie_2_Kabine'] = B ^ box(X1+GAP, X2-GAP, -BIG, BIG, -5, BIG)
parts['Karosserie_3_Heck'] = B ^ box(X2+GAP, BIG, -BIG, BIG, -5, BIG)
parts['Duebel'] = cyl_x(0, 24.0, 0, 0, DOW_D/2)
info = {'_bohrungen_anteil': diag}
for name, M in parts.items():
    t = to_tm(M); comps = sorted(t.split(only_watertight=False), key=lambda c: -abs(c.volume))
    keep = [c for c in comps if abs(c.volume) > 100.0]
    if name.startswith('Karosserie'): keep = keep[:1]
    t = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]
    info[name] = dict(faces=len(t.faces), vol_cm3=round(abs(t.volume)/1000, 2), area_cm2=round(t.area/100, 1), bbox_mm=[round(float(v), 1) for v in (t.bounds[1]-t.bounds[0])],
                      watertight=bool(t.is_watertight), huellen=len(keep), verworfen=len(comps)-len(keep))
    t.export(os.path.join(out, name + '.stl')); print(name, info[name])
json.dump(info, open(os.path.join(out, 'teile.json'), 'w'), indent=1, default=float)
