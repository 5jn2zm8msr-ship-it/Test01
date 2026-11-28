"""Druckfertiger STL (Bambu Lab, ein Stueck): wasserdicht, eine Huelle, flache Standflaeche.
python export_stl.py <glb> <ausgabe.stl> [laenge_mm=220] [voxel_mm=0.5]
Schritte: auf Druckgroesse skalieren -> Decimate -> Voxel-Remesh (verschmilzt alles zu EINER geschlossenen Huelle,
Tuben/Motorrad/Reifen werden mit dem Aufbau verbunden) -> Boden bei 1.2 mm abschneiden (flache Reifen-Aufstandsflaechen) -> STL in mm."""
import bpy, bmesh, sys, os
from mathutils import Vector
glb, out = sys.argv[1], sys.argv[2]
L_MM = float(sys.argv[3]) if len(sys.argv) > 3 else 220.0
VOX = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
CUT = 1.2
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
o = [x for x in bpy.data.objects if x.type == 'MESH'][0]
bpy.context.view_layer.objects.active = o; o.select_set(True)
o.data.materials.clear()
# 1 Einheit = 1 mm
d = o.dimensions; f = L_MM / max(d.x, d.y)
o.scale = (f, f, f); bpy.ops.object.transform_apply(scale=True)
bpy.context.scene.unit_settings.scale_length = 0.001
# Boden auf z=0, mittig
bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
o.location = (-(min(b.x for b in bb)+max(b.x for b in bb))/2, -(min(b.y for b in bb)+max(b.y for b in bb))/2, -min(b.z for b in bb))
bpy.ops.object.transform_apply(location=True)
print('Groesse mm:', tuple(round(v, 1) for v in o.dimensions), 'Dreiecke vorher:', len(o.data.polygons))
m = o.modifiers.new('dec', 'DECIMATE'); m.ratio = 0.12
bpy.ops.object.modifier_apply(modifier='dec'); print('nach Decimate:', len(o.data.polygons))
r = o.modifiers.new('vox', 'REMESH'); r.mode = 'VOXEL'; r.voxel_size = VOX; r.adaptivity = 0.0
bpy.ops.object.modifier_apply(modifier='vox'); print('nach Voxel-Remesh:', len(o.data.polygons))
# Boden flach schneiden
bm = bmesh.new(); bm.from_mesh(o.data)
geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(0, 0, CUT), plane_no=(0, 0, 1), clear_inner=True)
cut_edges = [e for e in res['geom_cut'] if isinstance(e, bmesh.types.BMEdge)]
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0) if False else None
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bm.to_mesh(o.data); bm.free()
# Deckel auf den Schnitt: Voxel-Remesh nochmal (schliesst die offene Unterseite sauber), dann Kontrolle
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.fill_holes(sides=0); bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.shade_flat()
bm = bmesh.new(); bm.from_mesh(o.data)
nonman = sum(1 for e in bm.edges if not e.is_manifold)
seen = set(); comps = 0
for v in bm.verts:
    if v.index in seen: continue
    comps += 1; stack = [v]
    while stack:
        x = stack.pop()
        if x.index in seen: continue
        seen.add(x.index); stack += [e.other_vert(x) for e in x.link_edges]
print('Nicht-Mannigfaltige Kanten:', nonman, '| getrennte Huellen:', comps, '| Dreiecke:', len(bm.faces), '| Volumen cm3:', round(bm.calc_volume()/1000, 1))
bm.free()
bpy.ops.wm.stl_export(filepath=out, export_selected_objects=True, ascii_format=False, apply_modifiers=True, global_scale=1.0)
print('STL:', out, round(os.path.getsize(out)/1e6, 1), 'MB')
