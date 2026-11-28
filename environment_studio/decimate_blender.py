"""Reduziert ein STL mit Blender-Decimate (Collapse, behaelt Manifold). python decimate_blender.py <in.stl> <out.stl> <ziel_dreiecke>"""
import bpy, sys
src, out, target = sys.argv[1], sys.argv[2], int(sys.argv[3])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.stl_import(filepath=src); o = bpy.context.object
n0 = len(o.data.polygons); m = o.modifiers.new('d', 'DECIMATE'); m.ratio = min(1.0, target/n0); m.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier='d'); print('Dreiecke', n0, '->', len(o.data.polygons))
bpy.ops.wm.stl_export(filepath=out, export_selected_objects=True, ascii_format=False)
