"""
Blender-Test (5.3): drei Methoden (Lokale KI / Geometry Nodes / Meshy) hinter einer Auswahl, Meshy-Felge aus einem GLB (ohne API-Aufruf),
Quelle für das Paket. Aufruf: /tmp/venv53/bin/python tests/methods/test_methods.py
"""
import math
import os
import shutil
import sys
import tempfile

import bpy  # noqa: I001
import addon_utils
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = os.path.join(bpy.utils.user_resource("SCRIPTS", path="addons", create=True), "felge3d")
shutil.rmtree(d, ignore_errors=True)
os.makedirs(d)
for f in os.listdir(os.path.join(REPO, "felge3d")):
    if f.endswith((".py", ".toml")):
        shutil.copy(os.path.join(REPO, "felge3d", f), d)
if os.path.isdir(os.path.join(REPO, "felge3d", "assets")):                       # mitgelieferte Objekte (assets/) mitkopieren
    shutil.copytree(os.path.join(REPO, "felge3d", "assets"), os.path.join(d, "assets"))
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("felge3d", default_set=True)
import felge3d  # noqa: E402
from felge3d import paramui  # noqa: E402

bad = 0


def check(name, cond, info=""):
    global bad
    print("OK   " if cond else "FEHLT", name, info)
    bad += 0 if cond else 1


sc = bpy.context.scene
s, c = sc.felge3d, sc.felge3d_car
photo = os.path.join(REPO, "tests", "diamond_cut", "neue_felgen", "porsche_gold_IMG_2695.jpg")
check("Standard-Methode = Meshy (lokale Methoden nur auf ausdrücklichen Wunsch)", s.method == "MESHY" and s.cloud_provider == "MESHY" and s.mesh_source == "CLOUD")
items = [i.identifier for i in s.bl_rna.properties["method"].enum_items]
check("drei Methoden zur Auswahl", items == ["AI", "SUBD", "MESHY"], str(items))

# 1) Geometry Nodes (ausdrücklich gewählt)
s.method = "SUBD"
bpy.ops.felge3d.import_image(filepath=photo)
rims = paramui.rim_collections()
check("Geometry Nodes: Collection mit Methode SUBD", len(rims) == 1 and rims[0]["felge3d_method"] == "SUBD" and paramui.param_object_of(rims[0]) is not None)
subd = rims[0]

# 2) Lokale KI: eigene Collection, SubD bleibt
s.method = "AI"
check("Methode AI setzt KI-Mesh-Modus", s.result_mode == "KI")
check("Felge erstellen (AI)", bpy.ops.felge3d.create_rim() == {"FINISHED"})
rims = paramui.rim_collections()
ai = [r for r in rims if r["felge3d_method"] == "AI"]
check("Lokale KI: zweite Collection, SubD unverändert vorhanden", len(rims) == 2 and len(ai) == 1 and subd.name in bpy.data.collections)
check("KI-Collection enthält Stern/Bett", any(o.get("felge3d_role") in ("star", "barrel", "body") for o in ai[0].objects))

# 3) zurück auf Geometry Nodes: bestehende Collection wird aktualisiert, keine dritte
s.method = "SUBD"
check("Methode SUBD setzt EDIT", s.result_mode == "EDIT")
check("Felge erstellen (SUBD)", bpy.ops.felge3d.create_rim() == {"FINISHED"})
check("keine dritte Collection (gleiches Bild, gleiche Methode)", len(paramui.rim_collections()) == 2)

# 3b) Meshy: Auswahl Mit Textur / Nur Mesh mit Credits in Klammern
tex_items = {i[0]: i[1] for i in felge3d.meshy_texture_items(s, bpy.context)}      # dynamische Auswahl: Items-Funktion der Eigenschaft
check("Meshy-Auswahl: Mit Textur / Nur Mesh", set(tex_items) == {"TEX", "MESH"}, str(tex_items))
check("Credits in Klammern (Textur 30, nur Mesh 20)", "(30 Credits)" in tex_items["TEX"] and "(20 Credits)" in tex_items["MESH"], str(tex_items))
check("Standard = mit Textur", s.meshy_texture_mode == "TEX" and felge3d.make_provider(s, "MESHY").options["texture"] is True)
s.meshy_texture_mode = "MESH"
check("Nur Mesh: Option aus, Kosten 20", felge3d.make_provider(s, "MESHY").options["texture"] is False and felge3d.make_provider(s, "MESHY").estimate_credits() == 20)
s.meshy_remesh = True
tex_items = {i[0]: i[1] for i in felge3d.meshy_texture_items(s, bpy.context)}      # dynamische Auswahl: Items-Funktion der Eigenschaft
check("Remesh wird in den Credits berücksichtigt (35 / 25)", "(35 Credits)" in tex_items["TEX"] and "(25 Credits)" in tex_items["MESH"], str(tex_items))
s.meshy_remesh = False
s.meshy_texture_mode = "TEX"

# 3c) Meshy: bis zu 3 Bilder (Hauptbild + 2 weitere), auch mit nur einem
tmpd = tempfile.mkdtemp()
def mkimg(name):
    im = bpy.data.images.new(name, 64, 64)
    im.filepath_raw = os.path.join(tmpd, name + ".png")
    im.file_format = "PNG"
    im.save()
    return bpy.data.images.load(im.filepath_raw)
check("ohne weitere Bilder: Image to 3D (keine Zusatzbilder)", "extra_images" not in felge3d.make_provider(s, "MESHY").options and felge3d.meshy_extra_images(s) == [])
s.meshy_image2 = mkimg("ansicht2")
check("ein Zusatzbild: 2 Bilder insgesamt", len(felge3d.make_provider(s, "MESHY").options["extra_images"]) == 1)
s.meshy_image3 = mkimg("ansicht3")
ex = felge3d.make_provider(s, "MESHY").options["extra_images"]
check("zwei Zusatzbilder: 3 Bilder insgesamt, feste Reihenfolge", len(ex) == 2 and ex[0].endswith("ansicht2.png") and ex[1].endswith("ansicht3.png"), str(ex))
check("Kosten mit 3 Bildern unverändert (Textur 30)", felge3d.make_provider(s, "MESHY").estimate_credits() == 30)
s.meshy_image2 = None
check("nur Ansicht 3 gesetzt: trotzdem 2 Bilder", len(felge3d.meshy_extra_images(s)) == 1)
img_mem = bpy.data.images.new("imspeicher", 8, 8)                       # nur im Speicher, keine Datei
s.meshy_image2 = img_mem
check("Zusatzbild ohne Datei wird abgelehnt (Meldung)", felge3d.meshy_extra_problem(s) is not None and "Datei" in felge3d.meshy_extra_problem(s))
s.meshy_image2 = None
s.meshy_image3 = None
check("zurück auf ein Bild", felge3d.meshy_extra_images(s) == [] and felge3d.meshy_extra_problem(s) is None)

# 3d) Plus-Knopf: zusätzliche Bildfelder öffnen sich schrittweise (1 → 2 → 3), mit einem Bild funktioniert alles
check("Start: nur ein Bildfeld (Hauptbild)", s.meshy_views == 1)
bpy.ops.felge3d.meshy_view_add()
check("Plus: zweites Feld öffnet sich", s.meshy_views == 2)
bpy.ops.felge3d.meshy_view_add()
check("Plus: drittes Feld öffnet sich", s.meshy_views == 3)
bpy.ops.felge3d.meshy_view_add()
check("Plus: nicht mehr als 3 Bilder", s.meshy_views == 3)
s.meshy_image3 = mkimg("v3")
s.meshy_image2 = mkimg("v2")
check("3 Bilder gesetzt: 2 Zusatzbilder", len(felge3d.meshy_extra_images(s)) == 2)
bpy.ops.felge3d.meshy_view_remove()
check("Minus: drittes Feld schließt und das Bild wird entfernt", s.meshy_views == 2 and s.meshy_image3 is None and len(felge3d.meshy_extra_images(s)) == 1)
bpy.ops.felge3d.meshy_view_remove()
check("Minus: zweites Feld schließt, zurück auf ein Bild", s.meshy_views == 1 and s.meshy_image2 is None and felge3d.meshy_extra_images(s) == [])
bpy.ops.felge3d.meshy_view_remove()
check("Minus bei einem Bild ändert nichts", s.meshy_views == 1 and felge3d.make_provider(s, "MESHY").estimate_credits() == 30)

# 4) Meshy: Einstellungen, kein Bau beim Bildladen (kostenpflichtig)
s.method = "MESHY"
check("Methode MESHY setzt Anbieter Meshy", s.cloud_provider == "MESHY" and s.mesh_source == "CLOUD")
n_before = len(paramui.rim_collections())
bpy.ops.felge3d.import_image(filepath=photo)
check("Bild laden baut bei Meshy NICHT (erst ‚Felge erstellen‘)", len(paramui.rim_collections()) == n_before)

# 5) Meshy-GLB (synthetisch: Fass + Scheibe + Speichen, Achse beliebig) -> sichtbare Felge
bpy.ops.mesh.primitive_torus_add(major_radius=0.25, minor_radius=0.04, major_segments=64, minor_segments=12)
barrel = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(radius=0.22, depth=0.02, vertices=48, location=(0, 0, 0.05))
disc = bpy.context.active_object
for o in (barrel, disc):
    o.select_set(True)
bpy.context.view_layer.objects.active = barrel
bpy.ops.object.join()
rimob = bpy.context.active_object
rimob.rotation_euler = (math.radians(90), 0, math.radians(30))          # Achse nicht in Z
glb = os.path.join(tempfile.mkdtemp(), "meshy_test.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
col = felge3d.make_meshy_rim(bpy.context, s, glb)
check("Meshy-Felge: neue Felgen-Collection mit Methode MESHY", col["felge3d_method"] == "MESHY" and col in paramui.rim_collections())
check("Meshy-Felge: Mesh-Objekt mit Rolle meshy", any(o.get("felge3d_role") == "meshy" and o.type == "MESH" for o in col.objects))
check("Meshy-Quelle verborgen (Viewport UND Rendering)", s.meshy_source is not None and s.meshy_source.hide_viewport and s.meshy_source.hide_render)
bpy.context.view_layer.update()
mob = next(o for o in col.objects if o.get("felge3d_role") == "meshy")
v = np.empty(len(mob.data.vertices) * 3)
mob.data.vertices.foreach_get("co", v)
v = v.reshape(-1, 3)
M = np.array(mob.matrix_world)
w = v @ M[:3, :3].T + M[:3, 3]
from felge3d import core  # noqa: E402
R_out = core.dimensions(felge3d.make_params(s))[4]
# Rad steht: Achse = Welt-Y; Außenradius in der XZ-Ebene
ro = np.hypot(w[:, 0], w[:, 2]).max()
check("Meshy-Felge: Außenradius = Felgenradius", abs(ro - R_out) / R_out < 0.03, "%.3f / %.3f" % (ro, R_out))
check("Meshy-Felge: Achse = Welt-Y (Ausdehnung in Y klein)", (w[:, 1].max() - w[:, 1].min()) < 0.5 * 2 * ro)
check("sichtbar (aktive Felge)", not col.hide_viewport and s.collection == col)
# Farbe aus dem Foto (Frontprojektion)
mats_ = [m_ for o_ in col.objects if o_.type == "MESH" for m_ in o_.data.materials]
imgs_ = [n_.image for m_ in mats_ for n_ in m_.node_tree.nodes if n_.type == "TEX_IMAGE"]
check("Farbe aus dem Foto: Material mit Foto-Projektion (Standard an)", len(mats_) >= 1 and all(m_.name.endswith(" Foto") for m_ in mats_) and s.image in imgs_, str([m_.name for m_ in mats_]))
check("Foto-Projektion: Mischknoten und Helligkeit vorhanden", any(n_.bl_idname in ("ShaderNodeMix", "ShaderNodeMixRGB") for n_ in mats_[0].node_tree.nodes)
      and any(n_.bl_idname == "ShaderNodeHueSaturation" for n_ in mats_[0].node_tree.nodes))
s.meshy_photo_color = False
col_np = felge3d.make_meshy_rim(bpy.context, s, glb)
mats_np = [m_ for o_ in col_np.objects if o_.type == "MESH" for m_ in o_.data.materials]
check("Foto-Projektion aus: Material bleibt unverändert", all(not m_.name.endswith(" Foto") for m_ in mats_np))
s.meshy_photo_color = True

# 6) Paket aus der Meshy-Felge
check("Methode MESHY: Paket nutzt Meshy-Quelle", felge3d._source_collection(s) is s.meshy_source and bool(felge3d._fbx_meshes(s)))
r = bpy.ops.felge3d.car_generate()
check("Paket aus Meshy-Felge erzeugt", r == {"FINISHED"})
wheels = [o for o in bpy.data.objects if o.name.startswith("Rad ") and o.type == "EMPTY"]
rim_children = {w.name: [k.name for k in w.children if k.type == "MESH" and not k.name.startswith(("Reifen", "Bremse"))] for w in wheels}
check("4 Räder, an jedem eine Felge aus dem Meshy-Mesh", len(wheels) == 4 and all(len(v) >= 1 for v in rim_children.values()), str(rim_children))
def _ov(front, sg, nm):
    return 1000 * felge3d.rim_tyre_overlap(bpy.context, bpy.data.objects[nm], sg, felge3d.car.wheel_dims(c, front)["r_rim"])
bpy.context.view_layer.update()
ovm = [_ov(f_, sg_, "Rad %s %s" % ("Vorne" if f_ else "Hinten", sd_)) for f_ in (True, False) for sg_, sd_ in ((1, "links"), (-1, "rechts"))]
check("Meshy-Felge steckt nicht im Reifen (alle vier Räder)", max(ovm) < 0.2, str([round(x, 2) for x in ovm]))
rim_mats = [m_.name for o_ in bpy.data.objects if o_.name.startswith("Felge Meshy ") or (o_.parent and o_.parent.name.startswith("Rad ") and o_.get("felge3d_part") == "rim") for m_ in o_.data.materials]
check("Paket: Felgen der vier Räder mit Foto-Projektion", len(rim_mats) >= 4 and all(" Foto" in n_ for n_ in rim_mats), str(rim_mats[:4]))
check("Methodenwechsel -> Update-Hinweis", (setattr(s, "method", "SUBD") or True) and felge3d.car_is_stale(s, c))
print("\nFehlgeschlagen:", bad)
sys.exit(1 if bad else 0)
