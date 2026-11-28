"""Stufe C: Wandstaerken (min. 0,8 mm), Filament und Druckzeit (Schaetzung) je Teil.
python stl_c_pruefung.py <teile-ordner> <ausgabe.json>
Annahmen: PLA 1,24 g/cm3, 0,4-mm-Duese, 0,2 mm Schicht, 3 Waende (1,2 mm), 15 % Infill, 5 Deck-/Bodenschichten (1,0 mm),
mittlerer Volumenfluss 10 mm3/s inkl. Beschleunigung/Bewegung, +12 % Rand/Brim/Skirt; Stuetzmaterial NICHT enthalten."""
import sys, os, json, numpy as np, trimesh
from scipy import ndimage as ndi
d, outj = sys.argv[1], sys.argv[2]
PITCH = 0.4; WALL = 1.2; INFILL = 0.15; SKIN = 1.0; RHO = 1.24; FLOW = 10.0
AXIS = {'Rad_': 1, 'Spiegel': 1, 'Reserverad': 1, 'Karosserie': 0, 'Duebel': 2}     # Druckrichtung (Hochachse beim Drucken)

from PIL import Image, ImageDraw
def layers(m, ax, pitch):
    """Schicht-fuer-Schicht-Raster (wie ein Slicer): bool-Array [schicht, u, v]."""
    normal = [0, 0, 0]; normal[ax] = 1
    lo, hi = m.bounds[0][ax], m.bounds[1][ax]
    hs = np.arange(lo + pitch/2, hi, pitch)
    other = [a for a in range(3) if a != ax]
    mn = m.bounds[0][other] - pitch; mx = m.bounds[1][other] + pitch
    shape = np.ceil((mx - mn)/pitch).astype(int)
    out = np.zeros((len(hs), shape[0], shape[1]), bool)
    for i, h in enumerate(hs):
        o = [0, 0, 0]; o[ax] = h
        sec = m.section(plane_origin=o, plane_normal=normal)
        if sec is None: continue
        img = np.zeros((shape[1], shape[0]), bool)
        loops = [pl for pl in sec.discrete if len(pl) > 3]
        loops.sort(key=lambda pl: -np.ptp(pl[:, other[0]])*np.ptp(pl[:, other[1]]))
        for pl in loops:
            pts = [(float((p[other[0]]-mn[0])/pitch), float((p[other[1]]-mn[1])/pitch)) for p in pl]
            t = Image.new('1', (shape[0], shape[1]), 0); ImageDraw.Draw(t).polygon(pts, fill=1)
            img ^= np.array(t, bool)
        out[i] = img.T
    return out
res = {}
for f in sorted(os.listdir(d)):
    if not f.endswith('.stl'): continue
    name = f[:-4]
    if name.startswith('Duebel') and name != 'Duebel_1': res[name] = None; continue
    m = trimesh.load(os.path.join(d, f)); m.merge_vertices()
    ax = next(v for k, v in AXIS.items() if name.startswith(k))
    occ = layers(m, ax, PITCH)          # Achse 0 = Druckrichtung (Schichten)
    ax = 0
    vv = PITCH**3; V = occ.sum()*vv
    din = np.empty(occ.shape, np.float64); ndi.distance_transform_edt(occ, sampling=PITCH, distances=din)
    shell = occ & (din <= WALL)
    # Deck/Boden (Druckachse): Voxel innerhalb SKIN von Luft in Achsrichtung
    air = ~occ; k = int(round(SKIN/PITCH)); st = [1, 1, 1]
    def shift_or(a, ax, k):
        r = np.zeros_like(a)
        for s_ in range(1, k+1):
            r |= np.roll(a, s_, ax); r |= np.roll(a, -s_, ax)
        return r
    skin = occ & shift_or(air, ax, k)
    solid = shell | skin
    inner = occ & ~solid
    fil = solid.sum()*vv + INFILL*inner.sum()*vv
    # dünne Bereiche: Opening mit r=0,4 mm (Material, das keine Kugel von 0,8 mm Durchmesser aufnimmt)
    core = din > 0.4; del din
    dd = np.empty(occ.shape, np.float64); ndi.distance_transform_edt(~core, sampling=PITCH, distances=dd); opened = dd <= 0.4; del dd
    thin = occ & ~opened
    lab, n = ndi.label(thin)
    sizes = ndi.sum(thin, lab, range(1, n+1))*vv if n else np.array([])
    thin_vol = float(thin.sum()*vv)
    res[name] = dict(volumen_cm3=V/1000, filament_cm3=fil/1000, gramm=fil/1000*RHO, zeit_h=fil/FLOW*1.12/3600,
                     duenn_mm3=thin_vol, duenn_prozent=100*thin_vol/V, duenn_cluster_ueber_1mm3=int((sizes > 1.0).sum()),
                     shell_prozent=100*shell.sum()*vv/V)
    print(name, {k: round(v, 2) for k, v in res[name].items()}, flush=True)
    del occ, shell, skin, solid, inner, core, opened, thin, lab
d1 = res.get('Duebel_1')
for k in list(res):
    if res[k] is None: res[k] = None
json.dump(res, open(outj, 'w'), indent=1, default=float)
