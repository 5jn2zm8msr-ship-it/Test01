"""Stufe A: Meshy-GLB -> wasserdichte, geschlossene Huelle im Massstab 1:10 (1 Einheit = 1 mm), als STL.
python stl_a_hulle.py <glb> <ausgabe.stl> [voxel_mm=0.6] [decimate=0.12]"""
import bpy, sys, os
from mathutils import Vector
glb, out = sys.argv[1], sys.argv[2]
VOX = float(sys.argv[3]) if len(sys.argv) > 3 else 0.6
DEC = float(sys.argv[4]) if len(sys.argv) > 4 else 0.12
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
o = [x for x in bpy.data.objects if x.type == 'MESH'][0]
bpy.context.view_layer.objects.active = o; o.select_set(True)
o.data.materials.clear()
d = o.dimensions
f = 202.0 / min(d.x, d.y)              # 1:10 -> Breite 2,02 m = 202 mm (wie meshy_cars/Szene)
o.scale = (f, f, f); bpy.ops.object.transform_apply(scale=True)
bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
o.location = (-(min(b.x for b in bb)+max(b.x for b in bb))/2, -(min(b.y for b in bb)+max(b.y for b in bb))/2, -min(b.z for b in bb))
bpy.ops.object.transform_apply(location=True)
print('Groesse mm:', tuple(round(v, 1) for v in o.dimensions), 'Dreiecke:', len(o.data.polygons))
m = o.modifiers.new('dec', 'DECIMATE'); m.ratio = DEC; bpy.ops.object.modifier_apply(modifier='dec'); print('Decimate:', len(o.data.polygons))
r = o.modifiers.new('vox', 'REMESH'); r.mode = 'VOXEL'; r.voxel_size = VOX; r.adaptivity = 0.0
bpy.ops.object.modifier_apply(modifier='vox'); print('Voxel-Remesh:', len(o.data.polygons))
m = o.modifiers.new('dec2', 'DECIMATE'); m.decimate_type = 'COLLAPSE'; m.ratio = 0.5; m.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier='dec2'); print('nach 2. Decimate:', len(o.data.polygons))
bpy.ops.wm.stl_export(filepath=out, export_selected_objects=True, ascii_format=False, apply_modifiers=True)
print('STL', out, round(os.path.getsize(out)/1e6, 1), 'MB')
