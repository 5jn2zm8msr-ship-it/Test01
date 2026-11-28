"""Slicen der vereinfachten Teile (PrusaSlicer-CLI, Bambu-aehnliches Profil), mit Varianten der Ausrichtung.
python slice_v2.py <teile-ordner> <arbeitsordner> [name,name,...]   Umgebungsvariablen: INFILL (Standard 10%), WALLS (2), LAYER (0.2), SUPPORT_STYLE, SUPPORT_THR"""
import sys, os, re, subprocess, json, numpy as np, trimesh
d, wd = sys.argv[1], sys.argv[2]; sel = sys.argv[3].split(',') if len(sys.argv) > 3 else None
os.makedirs(wd, exist_ok=True)
src = open(os.path.join(os.path.dirname(__file__), 'slice_all.py')).read()
CFG = src[src.index('CFG = """')+9: src.index('"""\nopen') if '"""\nopen' in src else src.index('"""\nif os.environ')]
CFG = re.sub(r'perimeters = \d+', 'perimeters = ' + os.environ.get('WALLS', '2'), CFG)
CFG = re.sub(r'fill_density = [\d%]+', 'fill_density = ' + os.environ.get('INFILL', '10%'), CFG)
CFG = re.sub(r'(?m)^layer_height = [\d.]+', 'layer_height = ' + os.environ.get('LAYER', '0.2'), CFG)
CFG = CFG.replace('top_solid_layers = 5', 'top_solid_layers = 4').replace('bottom_solid_layers = 5', 'bottom_solid_layers = 4')
CFG = CFG.replace('support_material_style = organic', 'support_material_style = ' + os.environ.get('SUPPORT_STYLE', 'organic')).replace('support_material_threshold = 40', 'support_material_threshold = ' + os.environ.get('SUPPORT_THR', '40'))
if os.environ.get('NOSUPPORT'): CFG = CFG.replace('support_material = 1', 'support_material = 0')
ini = os.path.join(wd, 'profil.ini'); open(ini, 'w').write(CFG)
R = lambda ax, deg: trimesh.transformations.rotation_matrix(np.radians(deg), ax)
X, Y = [1, 0, 0], [0, 1, 0]
JOBS = {  # name: (dateien, Ausrichtung)
 'Front_stehend': (['Karosserie_1_Front'], R(Y, 90)),
 'Kabine_stehend': (['Karosserie_2_Kabine'], R(Y, -90)),
 'Heck_stehend': (['Karosserie_3_Heck'], R(Y, -90)),
 'Front_Nase_unten': (['Karosserie_1_Front'], R(Y, -90)),
 'Heck_Schnittflaeche_unten_gedreht': (['Karosserie_3_Heck'], R(Y, 90)),
 'Front_liegend_seite': (['Karosserie_1_Front'], R(X, 90)),
 'Heck_liegend_seite': (['Karosserie_3_Heck'], R(X, 90)),
 'FrontKabine_stehend': (['Karosserie_1_Front_Kabine'], R(Y, 90)),
 'Heck4_natuerlich': (['Karosserie_2_Heck'], np.eye(4)),
 'Heck4_stehend': (['Karosserie_2_Heck'], R(Y, -90)),
 'Aufbau_natuerlich': (['Karosserie_3_Aufbau'], np.eye(4)),
 'Duebel_klein': (['Duebel_klein'], R(Y, -90)),
 'Rad_zweifarbig': (['Rad_Reifen_schwarz', 'Rad_Felge_weiss'], R(X, 90)),
 'Duebel': (['Duebel'], R(Y, -90)),
}
res = {}
for job, (files, T) in JOBS.items():
    if sel and job not in sel: continue
    ms = [trimesh.load(os.path.join(d, f + '.stl')) for f in files]; M = trimesh.util.concatenate(ms); M.apply_transform(T)
    c = M.bounds.mean(0); off = [128 - c[0], 128 - c[1], -M.bounds[0][2]]
    fl = []
    for m in ms:
        m = m.copy(); m.apply_transform(T); m.apply_translation(off); fl.append(m)
    allm = trimesh.util.concatenate(fl); stl = os.path.join(wd, job + '_druck.stl'); allm.export(stl)
    for m, f in zip(fl, files): m.export(os.path.join(wd, job + '__' + f + '_druck.stl'))
    out = os.path.join(wd, job + '.gcode')
    r = subprocess.run(['prusa-slicer', '--export-gcode', '--load', ini, '--dont-arrange', '-o', out, stl], capture_output=True, text=True)
    info = dict(bbox_druck=[round(float(v), 1) for v in (allm.bounds[1]-allm.bounds[0])], rc=r.returncode, warn=sorted(set(re.findall(r'(Thin fragile part|Loose extrusions|Low bed adhesion|Floating object parts|Crossing perimeters|Potentially lost branch)', r.stdout + r.stderr))))
    if os.path.exists(out):
        t = open(out).read()
        for k, key in (('filament used [g]', 'gramm'), ('estimated printing time (normal mode)', 'zeit')):
            mm = re.search(r'; %s = ([^\n]+)' % re.escape(k), t); info[key] = mm.group(1) if mm else None
        info['gcode_mb'] = round(os.path.getsize(out)/1e6, 1)
    res[job] = info; print(job, json.dumps(info), flush=True)
json.dump(res, open(os.path.join(wd, 'ergebnis.json'), 'w'), indent=1)
