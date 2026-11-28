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
CAB_X0, CAB_X1, PLUG_X1, CABZ0, SHELL = -40.0, 33.0, 62.5, 73.0, 3.0    # Kabine hohl von -40 bis 33 (Dach als 45-Grad-Walm), massiver Stecker 33..62,5
STRAIGHT = 18.0                                                          # gerader Hohlraum ab Trennflaeche x=33, danach 45 Grad
HOOD = (-215.0, -40.0, 84.0)               # Motorraum/Keil massiv x0,x1,|y|
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
# Fuellen: Kabine (Seitenscheiben geschlossen) und Motorraum unter der Haube -> keine geschlossenen Hohlraeume (Stuetzen innen unmoeglich)
X = lambda x: int(round((x - lo[0])/P)); Y = lambda y: int(round((y - lo[1])/P)); Z = lambda z: int(round((z - lo[2])/P))
if not __import__('os').environ.get('NOFILL'):
    # Kabine x in [CAB_X0, CAB_X1]: Silhouette (Projektion entlang x) -> hohles Prisma, 3 mm Wand, Fenster geschlossen, Innenleben entfernt
    y0, y1, z0, z1 = Y(-84), Y(84), Z(CABZ0), Z(192)
    proj = occ[X(CAB_X0):X(PLUG_X1), y0:y1, z0:z1].any(0)
    proj = ndi.binary_closing(proj, iterations=int(round(2.0/P))); sil = ndi.binary_fill_holes(proj)
    inner = ndi.distance_transform_edt(sil, sampling=P) > SHELL
    shell2 = sil & ~inner
    ys, zs = np.where(sil); print('Silhouette y %.1f..%.1f z %.1f..%.1f' % (lo[1]+(y0+ys.min())*P, lo[1]+(y0+ys.max())*P, lo[2]+(z0+zs.min())*P, lo[2]+(z0+zs.max())*P), flush=True)
    for zz in (81, 120, 176):
        row = np.where(sil[:, Z(zz)-z0])[0]; print('  z=%d: y %.1f..%.1f' % (zz, lo[1]+(y0+row.min())*P, lo[1]+(y0+row.max())*P), flush=True)
    ax0, ax1, ax2 = X(CAB_X0), X(CAB_X1), X(PLUG_X1)
    blk = occ[ax0:ax2, y0:y1, z0:z1]
    blk &= ~sil[None]                                   # alles innerhalb der Silhouette raus
    edt_in = ndi.distance_transform_edt(sil, sampling=P) - SHELL        # Abstand zur Aussenhaut minus Wandstaerke
    for k in range(ax1 - ax0):                          # x von -40 (vorn) bis 33 (Trennflaeche)
        xk = CAB_X0 + k*P; d = max(0.0, (CAB_X1 - xk) - STRAIGHT)       # 45 Grad: Hohlraum schrumpft ab 18 mm Hoehe ueber der Trennflaeche
        blk[k] |= sil & ~(edt_in > d)                   # fest = Silhouette ohne Hohlraum
    blk[ax1-ax0:] |= sil[None]                          # massiver Stecker hinter der Trennflaeche bis zur Rueckwand
    occ[ax0:ax2, y0:y1, z0:z1] = blk
    # Motorraum + Windschutzscheiben-Keil vorn: je (x,y) von tiefster bis hoechster Stelle fuellen
    zone = occ[X(HOOD[0]):X(HOOD[1]), Y(-HOOD[2]):Y(HOOD[2]), :]
    zi = np.arange(occ.shape[2])[None, None, :]
    has = zone.any(2, keepdims=True); zmin = np.where(zone, zi, 10**6).min(2, keepdims=True); zmax = np.where(zone, zi, -1).max(2, keepdims=True)
    zone |= has & (zi >= zmin) & (zi <= zmax)
    print('gefuellt, Vol cm3', occ.sum()*P**3/1000, flush=True)
lab, n = ndi.label(occ); sz = ndi.sum(occ, lab, range(1, n+1))*P**3
keep = np.isin(lab, [i+1 for i, v in enumerate(sz) if v >= MINV]); print('Komponenten', n, 'behalten', int((sz >= MINV).sum()), flush=True)
vol = ndi.gaussian_filter(keep.astype(np.float32), float(__import__('os').environ.get('GAUSS', '0.8')))
vol = np.pad(vol, 1)
verts, faces, _, _ = measure.marching_cubes(vol, 0.5, spacing=(P, P, P))
verts += lo - P; mm = trimesh.Trimesh(verts, faces, process=True); trimesh.repair.fix_normals(mm); print('MC watertight', mm.is_watertight, 'Vol', round(mm.volume/1000, 1), flush=True)
print('MC', len(mm.faces), round(time.time()-t0), flush=True)
mm.export(out)
print('exportiert', out, len(mm.faces), flush=True)
