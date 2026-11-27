"""
Blender-Test (5.3) für das Fahrzeug-Paket: Anker-Empty, Achse = Y, Radstand = X, Update-Button, eigener Reifen.
Aufruf: /tmp/venv53/bin/python tests/car/test_car_layout.py
"""
import math
import os
import shutil
import tempfile
import sys

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
from felge3d import car as carmod  # noqa: E402

bad = 0


def check(name, cond, info=""):
    global bad
    print("OK   " if cond else "FEHLT", name, info)
    bad += 0 if cond else 1


def tire_dims(obj_name):
    ob = bpy.data.objects[obj_name]
    n = len(ob.data.vertices)
    v = np.empty(n * 3)
    ob.data.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    return np.hypot(v[:, 1], v[:, 2]).max(), v[:, 0].max() - v[:, 0].min()


sc = bpy.context.scene
s, c = sc.felge3d, sc.felge3d_car
bpy.context.preferences.addons["felge3d"].preferences.show_local = True              # lokale Methoden (Entwickler) nur hier, ausdrücklich
s.method = "SUBD"                                            # lokale Methode nur hier, ausdrücklich gewählt
bpy.ops.felge3d.import_image(filepath=os.path.join(REPO, "tests", "diamond_cut", "neue_felgen", "porsche_gold_IMG_2695.jpg"))
r = bpy.ops.felge3d.car_generate()
check("Paket erzeugt", r == {"FINISHED"})
col = carmod.bpy.data.collections.get(carmod.COLL_NAME)
anchor = c.car_anchor
check("Anker-Empty gesetzt, Typ EMPTY", anchor is not None and anchor.type == "EMPTY")
check("Anker im Paket", anchor.name in col.objects)
dims_f = carmod.wheel_dims(c, True)
check("Anker Z = Vorderreifenradius (Boden bei 0)", abs(anchor.location.z - dims_f["R"]) < 1e-6, "%.4f" % anchor.location.z)
check("Standard-Spurweite: vorn 2,00 m, hinten 2,10 m", c.front_track == 2000 and c.rear_track == 2100, "%s / %s" % (c.front_track, c.rear_track))
names = {"Vorne links": (0.0, 1), "Vorne rechts": (0.0, -1), "Hinten links": (-c.wheelbase / 1000.0, 1), "Hinten rechts": (-c.wheelbase / 1000.0, -1)}
bpy.context.view_layer.update()
for n, (dx, sg) in names.items():
    ob = bpy.data.objects["Rad " + n]
    check("Rad %s hängt am Anker" % n, ob.parent is anchor)
    w = ob.matrix_world.translation
    half = (c.front_track if n.startswith("Vorne") else c.rear_track) / 2000.0
    check("Rad %s: X = Radstand, Y = Spur" % n, abs(w.x - (anchor.location.x + dx)) < 1e-4 and abs(w.y - sg * half) < 1e-4, "(%.3f %.3f %.3f)" % tuple(w))
    ax = ob.matrix_world.to_3x3() @ __import__("mathutils").Vector((1, 0, 0))
    check("Rad %s: Achse = Y" % n, abs(ax.y) > 0.999 and abs(ax.x) < 0.05, "(%.3f %.3f %.3f)" % tuple(ax))
bpy.context.view_layer.update()
check("Abstand der Radmitten in Y: vorn 2,000 m, hinten 2,100 m",
      abs((bpy.data.objects["Rad Vorne links"].matrix_world.translation.y - bpy.data.objects["Rad Vorne rechts"].matrix_world.translation.y) - 2.0) < 1e-4
      and abs((bpy.data.objects["Rad Hinten links"].matrix_world.translation.y - bpy.data.objects["Rad Hinten rechts"].matrix_world.translation.y) - 2.1) < 1e-4)
check("Radstand vorn/hinten in X",
      abs((bpy.data.objects["Rad Vorne links"].matrix_world.translation.x - bpy.data.objects["Rad Hinten links"].matrix_world.translation.x) - c.wheelbase / 1000.0) < 1e-4)
check("links = +Y, rechts = -Y", bpy.data.objects["Rad Vorne links"].matrix_world.translation.y > 0 > bpy.data.objects["Rad Vorne rechts"].matrix_world.translation.y)

# Seitenlage: die Felgenfläche (Außenseite) liegt außen, die Bremse innen davon; Sturz: Radoberkante nach innen (links = +Y, rechts = -Y)
import mathutils  # noqa: E402
dg = bpy.context.evaluated_depsgraph_get()


def world_pts(ob):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    n = len(me.vertices)
    v = np.empty(n * 3)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    M = np.array(ev.matrix_world)
    out = v @ M[:3, :3].T + M[:3, 3]
    ev.to_mesh_clear()
    return out


FACE5 = {}
def overlaps():
    """Überlappung Felge/Reifenflanke (mm) an allen vier Rädern."""
    bpy.context.view_layer.update()
    out = {}
    for n_, sg_ in (("Vorne links", 1), ("Vorne rechts", -1), ("Hinten links", 1), ("Hinten rechts", -1)):
        r_rim_ = carmod.wheel_dims(c, n_.startswith("Vorne"))["r_rim"]
        out[n_] = 1000 * felge3d.rim_tyre_overlap(bpy.context, bpy.data.objects["Rad " + n_], sg_, r_rim_)
    return out


ov = overlaps()
check("Felge steckt nicht in der Reifenflanke (generierter Reifen, Standard)", max(ov.values()) < 0.2, str({k: round(v, 2) for k, v in ov.items()}))
for n, sg in (("Vorne links", 1), ("Vorne rechts", -1), ("Hinten links", 1), ("Hinten rechts", -1)):
    w = bpy.data.objects["Rad " + n]
    rim_ob = next(o for o in w.children if o.name.startswith("Felge") and o.type == "MESH")
    face_out = (world_pts(rim_ob)[:, 1] * sg).max()
    FACE5[n] = face_out
    disc_c = (world_pts(bpy.data.objects["Bremsscheibe " + n])[:, 1] * sg).mean()
    check("Felgenfläche liegt außen, Bremse innen davon (%s)" % n, face_out - disc_c > 0.03, "Fläche %.3f / Scheibe %.3f" % (face_out, disc_c))
    up = w.matrix_world.to_3x3() @ mathutils.Vector((0, 0, 1))
    check("Sturz: Radoberkante nach innen (%s)" % n, up.y * sg < -0.01, "up.y=%.3f" % up.y)

# Bremse wächst proportional mit der Felgengröße (21 Zoll vorn / 22 Zoll hinten; Bezug 20/21)
d20, d21 = carmod.wheel_dims(c, True), None
check("Bremse: bei Standardgrößen unverändert (Faktor 1)", abs(d20["brake_k"] - c.front_rim / 20.0) < 1e-9 and abs(d20["disc_d"] - c.front_disc / 1000.0 * c.front_rim / 20.0) < 1e-9)
c.front_rim, c.rear_rim = 21, 22
df, dr_ = carmod.wheel_dims(c, True), carmod.wheel_dims(c, False)
check("Scheibe vorn 21 Zoll: Standard × 21/20", abs(df["disc_d"] - c.front_disc / 1000.0 * 21 / 20) < 1e-6, "%.4f" % df["disc_d"])
check("Scheibe hinten 22 Zoll: Standard × 22/21", abs(dr_["disc_d"] - c.rear_disc / 1000.0 * 22 / 21) < 1e-6, "%.4f" % dr_["disc_d"])
check("Scheibendicke wächst proportional", abs(df["disc_t"] - c.front_disc_thickness / 1000.0 * 21 / 20) < 1e-9)
bpy.ops.felge3d.car_update()
disc_v = bpy.data.objects["Bremsscheibe Vorne links"]
ev_ = disc_v.evaluated_get(bpy.context.evaluated_depsgraph_get())
n_ = len(disc_v.data.vertices); v_ = np.empty(n_ * 3); disc_v.data.vertices.foreach_get("co", v_); v_ = v_.reshape(-1, 3)
check("Bremsscheiben-Mesh vorn hat die neue Größe (Radius = Standard × 21/20 / 2)", abs(np.hypot(v_[:, 1], v_[:, 2]).max() - c.front_disc / 2000.0 * 21 / 20) < 0.004, "%.4f" % np.hypot(v_[:, 1], v_[:, 2]).max())
c.brake_scale = False
check("Bremse nicht proportional (aus): Scheibe wie eingestellt", abs(carmod.wheel_dims(c, True)["disc_d"] - c.front_disc / 1000.0) < 1e-9)
c.brake_scale = True
c.front_rim, c.rear_rim = 20, 21
bpy.ops.felge3d.car_update()

# Felge 5 mm nach außen (Standard)
# Felge 5 mm nach außen (Standard), Verschiebung wirkt in Achsrichtung nach außen; Sättel Richtung Fahrzeugmitte
check("Standard: Felge 5 mm nach außen", abs(c.rim_offset - 5.0) < 1e-9)
c.rim_auto_clear = False                                       # hier den reinen Versatz messen (die Automatik würde zusätzlich schieben)
bpy.ops.felge3d.car_update()
FACE5 = {n_: (world_pts(next(o for o in bpy.data.objects["Rad " + n_].children if o.name.startswith("Felge") and o.type == "MESH"))[:, 1] * sg_).max()
         for n_, sg_ in (("Vorne links", 1), ("Vorne rechts", -1), ("Hinten links", 1), ("Hinten rechts", -1))}
c.rim_offset = 0.0
bpy.ops.felge3d.car_update()
dg = bpy.context.evaluated_depsgraph_get()
for n, sg in (("Vorne links", 1), ("Vorne rechts", -1), ("Hinten links", 1), ("Hinten rechts", -1)):
    rim_ob = next(o for o in bpy.data.objects["Rad " + n].children if o.name.startswith("Felge") and o.type == "MESH")
    f0 = (world_pts(rim_ob)[:, 1] * sg).max()
    check("Felge liegt mit 5 mm Versatz 5 mm weiter außen (%s)" % n, abs((FACE5[n] - f0) - 0.005) < 0.0006, "%.2f mm" % (1000 * (FACE5[n] - f0)))
c.rim_offset = 5.0
c.rim_auto_clear = True
bpy.ops.felge3d.car_update()
check("Sattelwinkel Standard: vorn 90°, hinten −90° (Richtung Fahrzeugmitte)", c.front_caliper_angle == 90 and c.rear_caliper_angle == -90)
for n in ("Vorne links", "Vorne rechts", "Hinten links", "Hinten rechts"):
    w = bpy.data.objects["Rad " + n]
    cal = world_pts(bpy.data.objects["Bremssattel " + n])
    dx = cal[:, 0].mean() - w.matrix_world.translation.x
    want = -1 if n.startswith("Vorne") else 1             # vorn: Sattel hinter der Achse (−X), hinten: vor der Achse (+X) = Fahrzeugmitte
    check("Sattel zeigt zur Fahrzeugmitte (%s)" % n, dx * want > 0.04, "dx=%.3f m" % dx)

# erzeugter Anker folgt dem Reifenradius, solange Z nicht verstellt wurde (Boden bleibt bei 0)
c.front_rim = 19
bpy.ops.felge3d.car_update()
d19b = carmod.wheel_dims(c, True)
check("Anker-Z folgt der Zollgröße (Boden bei 0)", abs(anchor.location.z - d19b["R"]) < 1e-6, "%.4f / %.4f" % (anchor.location.z, d19b["R"]))
c.front_rim = 20
bpy.ops.felge3d.car_update()

# Mitgelieferter Reifen (assets/reifen): einmal importiert, Textur bleibt, Größe passt sich an
c.tire_source = "COLLECTION"
c.tire_collection = None
c.tire_source = "BUNDLED"
check("mitgelieferte Reifen in der Liste", len(felge3d.assets.tyre_list()) >= 1 and c.tire_bundled == felge3d.assets.tyre_list()[0]["id"], c.tire_bundled)
r_ = bpy.ops.felge3d.car_update()
check("Update mit mitgeliefertem Reifen", r_ == {"FINISHED"})
dB = carmod.wheel_dims(c, True)
tb_ = [o.name for o in bpy.data.collections[carmod.COLL_NAME].all_objects if o.name == "Reifen Vorne links"]
check("mitgelieferter Reifen am Rad", len(tb_) == 1 and any(n_.type == "TEX_IMAGE" for n_ in bpy.data.objects[tb_[0]].data.materials[0].node_tree.nodes), str(tb_))
roB, wdB = tire_dims(tb_[0])
check("mitgelieferter Reifen: Radius und Breite = Reifenmaße", abs(roB - dB["R"]) < 0.004 and abs(wdB - dB["W"]) < 0.004, "%.3f/%.3f %.3f/%.3f" % (roB, dB["R"], wdB, dB["W"]))
vB = np.empty(len(bpy.data.objects[tb_[0]].data.vertices) * 3)
bpy.data.objects[tb_[0]].data.vertices.foreach_get("co", vB)
vB = vB.reshape(-1, 3)
check("mitgelieferter Reifen: Wulst sitzt auf dem Felgenradius", abs(np.hypot(vB[:, 1], vB[:, 2]).min() - dB["r_rim"]) < 0.004, "%.3f / %.3f" % (np.hypot(vB[:, 1], vB[:, 2]).min(), dB["r_rim"]))
mats_ = bpy.data.objects[tb_[0]].data.materials
check("mitgelieferter Reifen: Textur bleibt erhalten", len(mats_) >= 1 and any(n_.type == "TEX_IMAGE" and n_.image for n_ in mats_[0].node_tree.nodes))
te_ = felge3d.assets.tyre_entry("pzero_gt")
check("Credits: Autor, Quelle und Lizenz CC BY 4.0 vorhanden", te_["autor"] == "Iftekhar.Tushar" and te_["quelle_url"] == "https://skfb.ly/oNqAJ"
      and te_["lizenz"] == "CC BY 4.0" and te_["lizenz_url"].startswith("http://creativecommons.org/licenses/by/4.0"), str(te_.get("autor")))
check("Credits: Änderungen genannt, Zeilen für die Oberfläche", bool(te_.get("aenderungen")) and len(felge3d.assets.all_credits()) >= 4)
check("Standard-Drehung des Reifens (P ZERO oben): -90°", abs(te_["standard_drehung"] + 90.0) < 1e-9)
check("mitgelieferter Reifen: nur ein Import (Collection einmalig)", len([x for x in bpy.data.collections if x.name.startswith(felge3d.assets.PREFIX)]) == 1)
check("alle vier Räder mit dem mitgelieferten (texturierten) Reifen", all(any(n2.type == "TEX_IMAGE" for n2 in bpy.data.objects["Reifen " + n_].data.materials[0].node_tree.nodes)
      for n_ in ("Vorne links", "Vorne rechts", "Hinten links", "Hinten rechts")))
ovb = overlaps()
check("Felge steckt nicht in der Reifenflanke (mitgelieferter Reifen)", max(ovb.values()) < 0.2, str({k: round(v, 2) for k, v in ovb.items()}))
c.rim_auto_clear = False
c.rim_offset = -20.0                                           # absichtlich zu weit innen: Überlappung muss messbar sein
bpy.ops.felge3d.car_update()
ovn = overlaps()
check("Messung erkennt Überlappung, wenn die Felge zu weit innen sitzt", max(ovn.values()) > 5.0, str({k: round(v, 1) for k, v in ovn.items()}))
c.rim_auto_clear = True
bpy.ops.felge3d.car_update()
ova = overlaps()
check("Automatik schiebt die Felge frei, auch bei −20 mm Versatz", max(ova.values()) < 0.2, str({k: round(v, 2) for k, v in ova.items()}))
check("Automatischer Versatz steht am Rad-Empty", "Felge automatisch nach außen (mm)" in bpy.data.objects["Rad Vorne links"].keys())
c.rim_offset = 5.0
c.tire_source = "GENERATED"
bpy.ops.felge3d.car_update()

# Eigene Bremse (Collection/Import): auf Scheibengröße skaliert, Scheibenebene wie die mitgelieferte, rechts gespiegelt
def local_pts(ob):
    n_ = len(ob.data.vertices)
    v_ = np.empty(n_ * 3)
    ob.data.vertices.foreach_get("co", v_)
    return v_.reshape(-1, 3)


c.brake_source = "GENERATED"
bpy.ops.felge3d.car_update()
gen = {}
for n_ in ("Vorne links", "Vorne rechts", "Hinten links"):
    v_ = local_pts(bpy.data.objects["Bremsscheibe " + n_])
    rho_ = np.hypot(v_[:, 1], v_[:, 2])
    ring_ = (rho_ > 0.75 * rho_.max()) & (rho_ < 0.93 * rho_.max())
    gen[n_] = (rho_.max(), float(0.5 * (v_[ring_, 0].min() + v_[ring_, 0].max())))
bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=0.02, vertices=64)          # Scheibe (Achse Z) – später gedreht
disc_ = bpy.context.active_object
bpy.ops.mesh.primitive_cylinder_add(radius=0.11, depth=0.02, vertices=64)          # innerer Ring der Reibfläche (Punkte im Ring-Bereich)
dsc2_ = bpy.context.active_object
bpy.ops.mesh.primitive_cube_add(size=0.05, location=(0.12, 0.0, 0.0))             # „Sattel“ seitlich der Scheibe
cal_ = bpy.context.active_object
cal_.scale = (1.0, 1.4, 1.2)
for o_ in (disc_, dsc2_, cal_):
    o_.select_set(True)
bpy.context.view_layer.objects.active = disc_
bpy.ops.object.join()
brk_ = bpy.context.active_object
brk_.name = "Bremse_test"
brk_.rotation_euler = (math.pi / 2, 0.0, 0.3)                                      # Achse beliebig
glb_b = os.path.join(tempfile.mkdtemp(), "bremse.glb")
bpy.ops.export_scene.gltf(filepath=glb_b, export_format="GLB", use_selection=True)
bpy.data.objects.remove(brk_)
check("import_brake importiert und wählt die Collection", bpy.ops.felge3d.import_brake(filepath=glb_b) == {"FINISHED"} and c.brake_source == "COLLECTION"
      and c.brake_collection.hide_render and "Scheibe Ø" in c.brake_info, c.brake_info)
check("Bremsen-Quelle verborgen (Viewport und Rendering)", c.brake_collection.hide_viewport and c.brake_collection.hide_render)
check("Update mit eigener Bremse", bpy.ops.felge3d.car_update() == {"FINISHED"})
for n_ in ("Vorne links", "Vorne rechts", "Hinten links"):
    ob_ = next((o for o in bpy.data.objects if o.name.startswith("Bremse_test") and o.name.endswith(n_)), None)
    check("eigene Bremse am Rad (%s)" % n_, ob_ is not None and ob_.get("felge3d_part") == "brake")
    v_ = local_pts(ob_)
    rho_ = np.hypot(v_[:, 1], v_[:, 2])
    r95 = float(np.percentile(rho_, 95))
    ring_ = (rho_ > 0.6 * r95) & (rho_ < 0.95 * r95)
    xr_ = float(0.5 * (np.percentile(v_[ring_, 0], 2) + np.percentile(v_[ring_, 0], 98)))
    check("eigene Bremse %s: Scheibenradius = Scheibengröße (±8 %%)" % n_, abs(r95 - gen[n_][0]) / gen[n_][0] < 0.08, "%.3f / %.3f" % (r95, gen[n_][0]))
    check("eigene Bremse %s: Scheibenebene wie die mitgelieferte (±4 mm), Seite stimmt" % n_, abs(xr_ - gen[n_][1]) < 0.004, "%.4f / %.4f" % (xr_, gen[n_][1]))
c.brake_own_scale = 1.2
bpy.ops.felge3d.car_update()
ob_ = next(o for o in bpy.data.objects if o.name.startswith("Bremse_test") and o.name.endswith("Vorne links"))
v_ = local_pts(ob_)
check("Größe ×1,2 wirkt", np.percentile(np.hypot(v_[:, 1], v_[:, 2]), 95) > 1.15 * gen["Vorne links"][0] * 0.95)
c.brake_own_scale = 1.0
c.brake_source = "GENERATED"
bpy.ops.felge3d.car_update()
check("zurück auf die mitgelieferte Bremse", any(o.name == "Bremsscheibe Vorne links" for o in bpy.data.objects) and not any(o.name.startswith("Bremse_test") for o in bpy.data.objects if o.parent))
r_ = bpy.ops.felge3d.car_reset()
check("Maße zurücksetzen lässt die Bremsenauswahl stehen", c.brake_collection is not None)

# Rad-Empties können nicht Anker sein
try:
    c.car_anchor = bpy.data.objects["Rad Vorne rechts"]
    rejected = c.car_anchor is not anchor
except TypeError:
    rejected = True
if rejected or c.car_anchor is not anchor:
    c.car_anchor = anchor
try:
    c.car_anchor = bpy.data.objects["Rad Vorne rechts"]
    r_bad = bpy.ops.felge3d.car_update()
except Exception:
    r_bad = {"CANCELLED"}
check("Rad-Empty als Anker wird abgelehnt", r_bad != {"FINISHED"} or c.car_anchor is not bpy.data.objects["Rad Vorne rechts"])
c.car_anchor = anchor

# Anker verschieben: alle vier Räder bewegen sich mit
before = {n: bpy.data.objects["Rad " + n].matrix_world.translation.copy() for n in names}
anchor.location = (anchor.location.x + 1.5, anchor.location.y + 0.2, anchor.location.z + 0.3)
bpy.context.view_layer.update()
ok = all(((bpy.data.objects["Rad " + n].matrix_world.translation - before[n]) - __import__("mathutils").Vector((1.5, 0.2, 0.3))).length < 1e-5 for n in names)
check("Anker verschieben bewegt alle 4 Räder", ok)
moved = tuple(anchor.location)

# Update-Feld: geänderte Parameter -> Hinweis, Update erhält die Lage des Ankers
check("nicht veraltet nach dem Bau", not felge3d.car_is_stale(s, c))
c.front_rim = 19
check("veraltet nach Änderung der Zollgröße", felge3d.car_is_stale(s, c))
r = bpy.ops.felge3d.car_update()
check("Update ausgeführt", r == {"FINISHED"})
check("nach Update nicht mehr veraltet", not felge3d.car_is_stale(s, c))
check("Anker bleibt derselbe Empty und an derselben Stelle", c.car_anchor is anchor and tuple(anchor.location) == moved, str(tuple(anchor.location)))
check("nur ein Anker im Paket", sum(1 for o in bpy.data.collections[carmod.COLL_NAME].all_objects if o.get("felge3d_role") == "car_anchor") == 1)



d19 = carmod.wheel_dims(c, True)
ro, wd = tire_dims("Reifen Vorne links")
check("generierter Reifen: Radius passt zu 19 Zoll", abs(ro - d19["R"]) < 0.004, "%.3f / %.3f" % (ro, d19["R"]))

# Eigener Reifen: Torus mit beliebiger Achse (hier X statt Z), anderer Größe
bpy.ops.mesh.primitive_torus_add(major_radius=0.33, minor_radius=0.10, major_segments=64, minor_segments=24)
tor = bpy.context.active_object
tor.rotation_euler = (0.0, math.pi / 2, 0.0)                 # Achse jetzt in X
tor.scale = (1.0, 1.0, 1.1)
tcol = bpy.data.collections.new("Testreifen")
sc.collection.children.link(tcol)
for oc in list(tor.users_collection):
    oc.objects.unlink(tor)
tcol.objects.link(tor)
bpy.context.view_layer.update()
c.tire_collection = tcol
c.tire_source = "COLLECTION"
r = bpy.ops.felge3d.car_update()
check("Update mit eigenem Reifen", r == {"FINISHED"})
bpy.context.view_layer.update()
tn = [o.name for o in bpy.data.collections[carmod.COLL_NAME].all_objects if o.name.startswith(tor.name) and "Vorne links" in o.name]
check("eigener Reifen am Rad vorhanden", len(tn) == 1, str(tn))
for nm_, dd in (("Vorne links", d19), ("Vorne rechts", d19), ("Hinten links", carmod.wheel_dims(c, False)), ("Hinten rechts", carmod.wheel_dims(c, False))):
    t_ = [o.name for o in bpy.data.collections[carmod.COLL_NAME].all_objects if o.name.startswith(tor.name) and nm_ in o.name]
    ro_, wd_ = tire_dims(t_[0]) if t_ else (0, 0)
    check("eigener Reifen %s: Radius und Breite" % nm_, abs(ro_ - dd["R"]) < 0.004 and abs(wd_ - dd["W"]) < 0.004, "%.3f/%.3f %.3f/%.3f" % (ro_, dd["R"], wd_, dd["W"]))
ro, wd = tire_dims(tn[0])
check("eigener Reifen: Außenradius = Reifenradius (19 Zoll vorn)", abs(ro - d19["R"]) < 0.004, "%.3f / %.3f" % (ro, d19["R"]))
check("eigener Reifen: Breite = Reifenbreite", abs(wd - d19["W"]) < 0.004, "%.3f / %.3f" % (wd, d19["W"]))
v = np.empty(len(bpy.data.objects[tn[0]].data.vertices) * 3)
bpy.data.objects[tn[0]].data.vertices.foreach_get("co", v)
v = v.reshape(-1, 3)
check("eigener Reifen: Wulst sitzt auf dem Felgenradius", abs(np.hypot(v[:, 1], v[:, 2]).min() - d19["r_rim"]) < 0.004, "%.3f / %.3f" % (np.hypot(v[:, 1], v[:, 2]).min(), d19["r_rim"]))
check("eigener Reifen: Mitte in der Radmitte", abs((v[:, 0].max() + v[:, 0].min()) / 2) < 0.004)
c.front_rim = 21
check("Zollgröße geändert -> veraltet (eigener Reifen)", felge3d.car_is_stale(s, c))
bpy.ops.felge3d.car_update()
d21 = carmod.wheel_dims(c, True)
ro, wd = tire_dims([o.name for o in bpy.data.collections[carmod.COLL_NAME].all_objects if o.name.startswith(tor.name) and "Vorne links" in o.name][0])
check("eigener Reifen passt sich an 21 Zoll an", abs(ro - d21["R"]) < 0.004, "%.3f / %.3f" % (ro, d21["R"]))
check("Anker nach zweitem Update unverändert", tuple(anchor.location) == moved)
r = bpy.ops.felge3d.car_reset()
check("Maße zurücksetzen lässt Auswahl (Anker, Reifenquelle) stehen", c.car_anchor is anchor and c.tire_source == "COLLECTION")
# Operator import_tire (GLB aus der Szene exportieren und laden)
import tempfile
glb_t = os.path.join(tempfile.mkdtemp(), "reifen.glb")
bpy.ops.mesh.primitive_torus_add(major_radius=0.3, minor_radius=0.12, major_segments=48, minor_segments=16)
bpy.context.active_object.rotation_euler = (math.pi / 2, 0, 0)
bpy.ops.export_scene.gltf(filepath=glb_t, export_format="GLB", use_selection=True)
bpy.data.objects.remove(bpy.context.active_object)
check("Reifen-Quelle auch im Rendering verborgen", c.tire_collection is not None and c.tire_collection.hide_render) if bpy.ops.felge3d.import_tire(filepath=glb_t) == {"FINISHED"} else None
check("import_tire importiert und wählt die Collection", bpy.ops.felge3d.import_tire(filepath=glb_t) == {"FINISHED"} and c.tire_collection is not None
      and c.tire_collection.name.startswith("Rim Generator | 3D-Reifen") and "Ø außen" in c.tire_info, c.tire_info)
r_ = bpy.ops.felge3d.car_update()
check("Update mit importiertem Reifen", r_ == {"FINISHED"})

# Eigener (vom Nutzer gewählter) Empty als Anker
bpy.ops.object.empty_add(type="PLAIN_AXES", location=(5.0, 1.0, 0.4))
mine = bpy.context.active_object
mine.name = "MeinEmpty"
c.car_anchor = mine
bpy.ops.felge3d.car_update()
bpy.context.view_layer.update()
check("gewählter Empty ist der Anker", bpy.data.objects["Rad Vorne links"].parent is mine)
check("Vorderachse sitzt auf dem gewählten Empty (X, Z)", abs(bpy.data.objects["Rad Vorne links"].matrix_world.translation.x - 5.0) < 1e-4
      and abs(bpy.data.objects["Rad Vorne links"].matrix_world.translation.z - 0.4) < 1e-4)
mine.location.x += 2.0
bpy.context.view_layer.update()
check("gewählten Empty verschieben bewegt die Räder", abs(bpy.data.objects["Rad Hinten rechts"].matrix_world.translation.x - (7.0 - c.wheelbase / 1000.0)) < 1e-4)
bpy.ops.felge3d.car_update()
check("gewählter Empty bleibt nach Update erhalten", "MeinEmpty" in bpy.data.objects and abs(mine.location.x - 7.0) < 1e-6)
# Sattelfarbe: Standard weiß, änderbar, Update-Hinweis
check("Sattelfarbe Standard = weiß", tuple(c.caliper_color) == (1.0, 1.0, 1.0))
mat = bpy.data.materials["Felge3D | Bremse links"]
bs = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
comb = [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeCombineColor"]
check("Sattel-Material nutzt die Farbe (Foto nur als Helligkeit)", len(comb) == 1 and bs.inputs["Base Color"].is_linked)
muls = [n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "MULTIPLY"]
check("Sattelfarbe weiß in allen Kanälen (linear 1,0)", len(muls) == 3 and all(abs(n.inputs[1].default_value - 1.0) < 1e-6 for n in muls))
c.caliper_color = (0.8, 0.1, 0.1)
check("Farbänderung -> Update-Hinweis", felge3d.car_is_stale(s, c))
bpy.ops.felge3d.car_update()
mat = bpy.data.materials["Felge3D | Bremse links"]
muls = sorted(n.inputs[1].default_value for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeMath" and n.operation == "MULTIPLY")
check("Sattel rot nach Update (R hoch, G/B niedrig)", len(muls) == 3 and muls[-1] > 0.5 and muls[0] < 0.05, str([round(v, 3) for v in muls]))
check("Bremse-Startwerte 7 % kleiner als die Datenblattwerte (408/380 mm)", abs(c.front_disc - 408 * 0.93) < 1 and abs(c.rear_disc - 380 * 0.93) < 1, "%s / %s" % (c.front_disc, c.rear_disc))
print("\nFehlgeschlagen:", bad)
sys.exit(1 if bad else 0)
