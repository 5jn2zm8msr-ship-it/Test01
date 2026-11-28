"""Slicen aller Teile in Druckausrichtung mit PrusaSlicer-CLI (Bambu-aehnliches Profil).
python slice_all.py <teile-ordner> <arbeitsordner> [nur_teil]"""
import sys, os, re, subprocess, json, numpy as np, trimesh
d, wd = sys.argv[1], sys.argv[2]; only = sys.argv[3] if len(sys.argv) > 3 else None
os.makedirs(wd, exist_ok=True)
CFG = """bed_shape = 0x0,256x0,256x256,0x256
max_print_height = 256
nozzle_diameter = 0.4
filament_diameter = 1.75
filament_density = 1.24
filament_type = PLA
temperature = 220
first_layer_temperature = 220
bed_temperature = 55
first_layer_bed_temperature = 55
layer_height = 0.2
first_layer_height = 0.2
perimeters = 3
top_solid_layers = 5
bottom_solid_layers = 5
fill_density = 15%
fill_pattern = gyroid
support_material = 1
support_material_auto = 1
support_material_style = organic
support_material_threshold = 40
support_material_buildplate_only = 0
support_material_contact_distance = 0.2
brim_width = 5
skirts = 1
perimeter_speed = 200
external_perimeter_speed = 150
infill_speed = 270
solid_infill_speed = 200
top_solid_infill_speed = 150
support_material_speed = 150
bridge_speed = 50
small_perimeter_speed = 60
travel_speed = 500
first_layer_speed = 50
max_volumetric_speed = 21
machine_limits_usage = emit_to_gcode
machine_max_acceleration_extruding = 10000
machine_max_acceleration_travel = 10000
machine_max_feedrate_x = 500
machine_max_feedrate_y = 500
default_acceleration = 10000
perimeter_acceleration = 5000
external_perimeter_acceleration = 5000
infill_acceleration = 10000
first_layer_acceleration = 500
gcode_flavor = marlin2
use_relative_e_distances = 1
layer_gcode = G92 E0
"""
open(os.path.join(wd, 'bambu_aehnlich.ini'), 'w').write(CFG)
def rot(axis, deg):
    return trimesh.transformations.rotation_matrix(np.radians(deg), axis)
def orient(name):
    X, Y = [1, 0, 0], [0, 1, 0]
    if name == 'Karosserie_vorn': return rot(Y, 90)
    if name == 'Karosserie_hinten': return rot(Y, -90)
    if name in ('Rad_VL', 'Rad_HL', 'Reserverad', 'Spiegel_L'): return rot(X, 90)
    if name in ('Rad_VR', 'Rad_HR', 'Spiegel_R'): return rot(X, -90)
    return np.eye(4)
res = {}
for f in sorted(os.listdir(d)):
    if not f.endswith('.stl'): continue
    n = f[:-4]
    if (only and n != only) or n in ('Duebel_2', 'Duebel_3', 'Duebel_4'): continue
    m = trimesh.load(os.path.join(d, f)); m.apply_transform(orient(n))
    c = m.bounds.mean(0); m.apply_translation([128 - c[0], 128 - c[1], -m.bounds[0][2]])
    stl = os.path.join(wd, n + '_druck.stl'); m.export(stl)
    out = os.path.join(wd, n + '.gcode')
    r = subprocess.run(['prusa-slicer', '--export-gcode', '--load', os.path.join(wd, 'bambu_aehnlich.ini'), '--dont-arrange', '-o', out, stl], capture_output=True, text=True)
    info = dict(bbox_druck=[round(v, 1) for v in (m.bounds[1]-m.bounds[0])], rc=r.returncode, log=(r.stdout+r.stderr)[-300:])
    if os.path.exists(out):
        t = open(out).read()
        g = lambda k: re.search(r'; %s = ([^\n]+)' % re.escape(k), t)
        for k, key in (('filament used [g]', 'gramm'), ('filament used [mm3]', 'mm3'), ('estimated printing time (normal mode)', 'zeit'), ('total filament cost', 'kosten')):
            mm = g(k); info[key] = mm.group(1) if mm else None
        info['gcode_mb'] = round(os.path.getsize(out)/1e6, 1)
    res[n] = info; print(n, json.dumps(info), flush=True)
json.dump(res, open(os.path.join(wd, 'slice_ergebnis.json'), 'w'), indent=1)
