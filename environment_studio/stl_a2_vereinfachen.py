"""Stufe A2: Huelle vereinfachen (Closing/Opening im Voxelraster, Marching Cubes, glaetten, reduzieren).
python stl_a2_vereinfachen.py <solid_full.stl> <ausgabe.stl> [pitch=0.6] [close_mm=1.6] [open_mm=0.9] [min_vol_mm3=300]"""
import sys, numpy as np, trimesh, time
from scipy import ndimage as ndi
from skimage import measure
from PIL import Image, ImageDraw
src, out = sys.argv[1], sys.argv[2]
P = float(sys.argv[3]) if len(sys.argv) > 3 else 0.6
RC = float(sys.argv[4]) if len(sys.argv) > 4 else 1.6
RO = float(sys.argv[5]) if len(sys.argv) > 5 else 0.9
MINV = float(sys.argv[6]) if len(sys.argv) > 6 else 300.0
CAB = (-92.0, 62.0, 78.0, 73.0, 192.0)      # x0,x1,|y|,z0,z1
HOOD = (-215.0, -92.0, 84.0)               # x0,x1,|y|
t0 = time.time()
m = trimesh.load(src); m.merge_vertices(); print('geladen', len(m.faces), round(time.time()-t0), flush=True)
lo = m.bounds[0] - 3; hi = m.bounds[1] + 3
shape = np.ceil((hi - lo)/P).astype(int)
occ = np.zeros(tuple(shape), bool)
for k in range(shape[2]):
    z = lo[2] + (k + 0.5)*P
    sec = m.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])
    if sec is None: continue
    img = np.zeros((shape[1], shape[0]), bool)
    loops = [pl for pl in sec.discrete if len(pl) > 3]
    loops.sort(key=lambda pl: -np.ptp(pl[:, 0])*np.ptp(pl[:, 1]))
    for pl in loops:
        t = Image.new('1', (shape[0], shape[1]), 0)
        ImageDraw.Draw(t).polygon([(float((p[0]-lo[0])/P), float((p[1]-lo[1])/P)) for p in pl], fill=1); img ^= np.array(t, bool)
    occ[:, :, k] = img.T
    if k % 50 == 0: print('Schicht', k, shape[2], round(time.time()-t0), flush=True)
print('Raster', occ.shape, 'Volumen cm3', occ.sum()*P**3/1000, flush=True)
def dil(a, r): d = ndi.distance_transform_edt(~a, sampling=P); return d <= r
def ero(a, r): d = ndi.distance_transform_edt(a, sampling=P); return d > r
occ = ero(dil(occ, RC), RC); print('Closing', round(time.time()-t0), flush=True)
occ = dil(ero(occ, RO), RO); print('Opening', round(time.time()-t0), 'Vol cm3', occ.sum()*P**3/1000, flush=True)
# Fuellen: Kabine (Seitenscheiben geschlossen, innen massiv) und Motorraum unter der Haube -> keine geschlossenen Hohlraeume (Stuetzen innen unmoeglich)
X = lambda x: int(round((x - lo[0])/P)); Y = lambda y: int(round((y - lo[1])/P)); Z = lambda z: int(round((z - lo[2])/P))
if not __import__('os').environ.get('NOFILL'):
    occ[X(CAB[0]):X(CAB[1]), Y(-CAB[2]):Y(CAB[2]), Z(CAB[3]):Z(CAB[4])] = True              # Kabine als Block
    zone = occ[X(HOOD[0]):X(HOOD[1]), Y(-HOOD[2]):Y(HOOD[2]), :]                         # Motorraum: je (x,y) von der tiefsten bis zur hoechsten Stelle fuellen
    zi = np.arange(occ.shape[2])[None, None, :]
    has = zone.any(2, keepdims=True); zmin = np.where(zone, zi, 10**6).min(2, keepdims=True); zmax = np.where(zone, zi, -1).max(2, keepdims=True)
    zone |= has & (zi >= zmin) & (zi <= zmax)
    print('gefuellt, Vol cm3', occ.sum()*P**3/1000, flush=True)
lab, n = ndi.label(occ); sz = ndi.sum(occ, lab, range(1, n+1))*P**3
keep = np.isin(lab, [i+1 for i, v in enumerate(sz) if v >= MINV]); print('Komponenten', n, 'behalten', int((sz >= MINV).sum()), flush=True)
vol = ndi.gaussian_filter(keep.astype(np.float32), 0.8)
vol = np.pad(vol, 1)
verts, faces, _, _ = measure.marching_cubes(vol, 0.5, spacing=(P, P, P))
verts += lo - P; mm = trimesh.Trimesh(verts, faces, process=True); trimesh.repair.fix_normals(mm); print('MC watertight', mm.is_watertight, 'Vol', round(mm.volume/1000, 1), flush=True)
print('MC', len(mm.faces), round(time.time()-t0), flush=True)
mm.export(out)
print('exportiert', out, len(mm.faces), flush=True)
