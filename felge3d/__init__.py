# SPDX-License-Identifier: GPL-3.0-or-later
"""
Felge3D – Blender-Add-on: Felgenfoto (Frontansicht) laden -> 3D-Felge in neuer Collection.

Bedienung: 3D-Viewport -> Seitenleiste (N) -> Reiter "Felge".
Läuft mit Blender 3.6 (Legacy-Add-on) und 4.2+ (Extension, siehe blender_manifest.toml).
"""

bl_info = {
    "name": "Felge3D",
    "author": "Felge3D",
    "version": (0, 2, 2),
    "blender": (3, 6, 0),
    "location": "3D-Viewport > Seitenleiste (N) > Felge",
    "description": "Erzeugt aus einem Frontfoto einer Felge ein 3D-Modell",
    "category": "Import-Export",
}

import math
import os

import bpy
import numpy as np
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty,
                       PointerProperty, StringProperty)
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ExportHelper, ImportHelper

# Beim Neu-Aktivieren/Update ohne Neustart lädt Blender Untermodule nicht neu -> selbst nachladen
if "core" in locals():
    import importlib
    core = importlib.reload(core)
    updater = importlib.reload(updater)
else:
    from . import core, updater

PREVIEW_NAME = "Felge3D_Vorschau"
MASK_NAME = "Felge3D_Maske"


# ============================================================ Einstellungen
def _update_rebuild(self, context):
    """Vorhandene Felge sofort mit dem neuen Wert neu bauen (gleiche Collection)."""
    if not (self.image and self.collection and self.collection.name in bpy.data.collections):
        return
    try:
        build_wheel(context, self, new_collection=False)
    except Exception as e:  # noqa: BLE001
        print("Felge3D: Neu bauen fehlgeschlagen:", e)


class Felge3DSettings(PropertyGroup):
    image: PointerProperty(name="Bild", type=bpy.types.Image)
    mask_image: PointerProperty(
        name="Eigene Maske", type=bpy.types.Image,
        description="Optional: Schwarz/Weiß-Bild (weiß = Material) statt automatischer Erkennung")
    collection: PointerProperty(name="Collection", type=bpy.types.Collection)

    # --- Lage der Felge im Bild
    auto_detect: BoolProperty(name="Felge automatisch finden", default=True,
                              description="Mittelpunkt und Radius beim Laden automatisch suchen")
    center_x: FloatProperty(name="Mitte X", default=0.5, min=0, max=1, precision=3,
                            description="Mittelpunkt, Anteil der Bildbreite")
    center_y: FloatProperty(name="Mitte Y", default=0.5, min=0, max=1, precision=3,
                            description="Mittelpunkt, Anteil der Bildhöhe (von unten)")
    radius: FloatProperty(name="Radius", default=0.49, min=0.05, max=1, precision=3,
                          description="Außenradius des Felgenhorns, Anteil der Bildbreite")
    aspect: FloatProperty(name="Stauchung", default=1.0, min=0.7, max=1.4, precision=3,
                          description="Höhe/Breite der Felgenkontur (gleicht leichte Perspektive aus)")

    # --- Erkennung
    seg_mode: EnumProperty(name="Erkennung", default="AUTO", items=[
        ("AUTO", "Automatisch", "Otsu-Schwellwert, Material = was am Felgenrand dominiert"),
        ("BRIGHT", "Hell = Material", ""),
        ("DARK", "Dunkel = Material", ""),
        ("BAND", "Grauband = Lücke", "Mittlere Grauwerte sind Lücke (z.B. Wand hinter schwarz/silbernen Speichen)"),
    ])
    auto_threshold: BoolProperty(name="Schwellwert automatisch", default=True)
    threshold: FloatProperty(name="Schwellwert", default=0.5, min=0, max=1, precision=3)
    threshold_hi: FloatProperty(name="Obere Grenze", default=0.7, min=0, max=1, precision=3)
    invert: BoolProperty(name="Invertieren", default=False, description="Material und Lücken vertauschen")
    clean: IntProperty(name="Glätten", default=2, min=0, max=10,
                       description="Entfernt kleine Störungen in der Maske (Pixel)")
    proc_size: IntProperty(name="Arbeitsauflösung", default=768, min=256, max=2048,
                           description="Bild wird für die Analyse auf diese Größe verkleinert")

    sym_mode: EnumProperty(name="Symmetrie", default="AUTO", items=[
        ("AUTO", "Automatisch", "Speichenanzahl erkennen und alle Speichen angleichen"),
        ("MANUAL", "Manuell", "Ordnung selbst vorgeben"),
        ("OFF", "Aus", "Maske unverändert verwenden"),
    ])
    sym_n: IntProperty(name="Ordnung", default=5, min=2, max=36)
    detected_n: IntProperty(name="Erkannt", default=0)

    # --- Maße
    diameter: IntProperty(name="Felgengröße (Zoll)", default=20, min=19, max=24,
                          subtype="NONE", update=_update_rebuild,
                          description="Durchmesser der Felge in Zoll (19–24)")
    width: FloatProperty(name="Breite (Zoll, J)", default=8.0, min=4, max=14)
    use_et: BoolProperty(name="Konkavität aus ET", default=True,
                         description="Konkavität aus der Einpresstiefe berechnen")
    et: FloatProperty(name="ET (mm)", default=45.0, min=-50, max=120)
    dish: FloatProperty(name="Konkavität (mm)", default=35.0, min=0, max=150)
    dish_power: FloatProperty(name="Wölbungsform", default=1.5, min=0.5, max=4,
                              description="1 = gerader Kegel, größer = runder")
    face_inset: FloatProperty(name="Stern-Rücksprung (mm)", default=12.0, min=0, max=60,
                              description="Wie weit der Stern außen hinter dem Felgenhorn liegt")
    spoke_thickness: FloatProperty(name="Speichendicke Rand (mm)", default=22.0, min=4, max=80,
                                   update=_update_rebuild)
    hub_thickness: FloatProperty(name="Nabendicke (mm)", default=40.0, min=10, max=120,
                                 update=_update_rebuild,
                                 description="Materialstärke an der Nabe (Speichen werden zur Mitte hin dicker)")
    hub_radius: FloatProperty(name="Nabenfläche Radius (mm)", default=85.0, min=30, max=150,
                              update=_update_rebuild,
                              description="Radius der flachen Nabenanlagefläche")
    relief: FloatProperty(name="Speichen-Wölbung (mm)", default=10.0, min=0, max=40,
                          update=_update_rebuild,
                          description="Wie stark die Speichen zur Mitte hin gewölbt sind (0 = flach)")
    relief_width: FloatProperty(name="Rundungsbreite (mm)", default=30.0, min=2, max=80,
                                update=_update_rebuild,
                                description="Über welche Breite die Speichenkante rund abfällt")
    one_body: BoolProperty(name="Ein Körper (fräsfertig)", default=True,
                           description="Stern und Felgenbett per Boolean zu einem geschlossenen Mesh vereinen")
    flange: FloatProperty(name="Hornhöhe (mm)", default=17.0, min=5, max=30)
    wall: FloatProperty(name="Wandstärke (mm)", default=5.0, min=2, max=15)
    drop: FloatProperty(name="Tiefbett (mm)", default=22.0, min=5, max=50)

    # --- Aussehen
    photo_texture: BoolProperty(name="Foto als Textur", default=True,
                                description="Das Felgenfoto von vorn auf die Felge projizieren (Farben, Logo, Glanz wie im Bild)")

    # --- Qualität
    res_radial: IntProperty(name="Ringe", default=160, min=40, max=600)
    res_angular: IntProperty(name="Segmente Stern", default=720, min=120, max=3600)
    sections: IntProperty(name="Segmente Bett", default=128, min=32, max=512)


# ============================================================ Hilfsfunktionen
def image_to_gray(img):
    """Blender-Bild -> Graustufen-numpy-Array (Zeile 0 = unten), Werte 0..1."""
    w, h = img.size
    if w == 0 or h == 0:
        raise RuntimeError("Bild '%s' konnte nicht gelesen werden." % img.name)
    ch = img.channels
    buf = np.empty(w * h * ch, dtype=np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(h, w, ch)
    if ch >= 3:
        return core.rgba_to_gray(buf)
    return buf[..., 0].copy()


def prepare(s):
    """Bild laden, verkleinern, Felgenlage in Arbeits-Pixeln bestimmen."""
    if not s.image:
        raise RuntimeError("Kein Bild geladen.")
    gray_full = image_to_gray(s.image)
    gray = core.downscale(gray_full, s.proc_size)
    h, w = gray.shape
    cx = s.center_x * w
    cy = s.center_y * h
    rx = s.radius * w
    ry = rx * s.aspect
    return gray, cx, cy, rx, ry


def compute_mask(s, gray, cx, cy, rx, ry):
    if s.mask_image:
        m = image_to_gray(s.mask_image)
        if m.shape != gray.shape:
            # auf Arbeitsauflösung bringen (nächster Nachbar)
            yi = (np.arange(gray.shape[0]) * m.shape[0] / gray.shape[0]).astype(int)
            xi = (np.arange(gray.shape[1]) * m.shape[1] / gray.shape[1]).astype(int)
            m = m[yi][:, xi]
        return (m > 0.5).astype(np.float32), None
    return core.segment(gray, cx, cy, rx, ry, s.seg_mode, s.auto_threshold,
                        s.threshold, s.threshold_hi, s.invert, s.clean)


def make_params(s):
    p = core.Params()
    for k in ("diameter", "width", "use_et", "et", "face_inset", "dish", "dish_power",
              "spoke_thickness", "hub_thickness", "hub_radius", "relief", "relief_width", "flange", "wall", "drop", "res_radial", "res_angular", "sections"):
        setattr(p, k, getattr(s, k))
    return p


def get_material(name, color, metallic, roughness):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Metallic"].default_value = metallic
            bsdf.inputs["Roughness"].default_value = roughness
        mat.diffuse_color = color
    return mat


def set_smooth(me, angle_deg, sharp_edges=None):
    """Glatt schattieren mit Kantenwinkel – kompatibel mit Blender 3.6 und 4.1+."""
    n = len(me.polygons)
    me.polygons.foreach_set("use_smooth", np.ones(n, dtype=bool))
    angle = math.radians(angle_deg)
    if hasattr(me, "use_auto_smooth"):           # Blender < 4.1
        me.use_auto_smooth = True
        me.auto_smooth_angle = angle
    elif hasattr(me, "set_sharp_from_angle"):    # Blender 4.1+
        me.set_sharp_from_angle(angle=angle)
    if sharp_edges:
        ev = np.empty(len(me.edges) * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ev)
        ev = ev.reshape(-1, 2)
        ev.sort(axis=1)
        want = set(sharp_edges)
        flags = np.array([(int(a), int(b)) in want for a, b in ev], dtype=bool)
        if flags.any():
            cur = np.empty(len(me.edges), dtype=bool)
            me.edges.foreach_get("use_edge_sharp", cur)
            me.edges.foreach_set("use_edge_sharp", cur | flags)
    me.update()


def project_photo_uv(me, s, R_out):
    """Planare UV-Projektion von vorn: jeder Punkt bekommt die Bildstelle, an der er im Foto liegt."""
    w, h = s.image.size
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    u = s.center_x + co[:, 0] / R_out * s.radius
    v = s.center_y + co[:, 1] / R_out * s.radius * s.aspect * (w / float(h))
    vi = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", vi)
    uv = me.uv_layers.new(name="Foto")
    uv.data.foreach_set("uv", np.stack([u[vi], v[vi]], axis=1).astype(np.float32).ravel())


def mean_color(img, mask):
    """Mittlere Farbe der Felge (Material-Pixel) für die nicht-fotografierten Flächen."""
    w, h = img.size
    ch = img.channels
    buf = np.empty(w * h * ch, dtype=np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(h, w, ch)
    yi = (np.arange(mask.shape[0]) * h / mask.shape[0]).astype(int)
    xi = (np.arange(mask.shape[1]) * w / mask.shape[1]).astype(int)
    rgb = buf[yi][:, xi, :3]
    sel = mask > 0.5
    col = rgb[sel].mean(axis=0) if sel.any() else np.array([0.5, 0.5, 0.5])
    return (float(col[0]), float(col[1]), float(col[2]), 1.0)


def get_photo_material(img):
    name = "Felge3D_Foto_" + img.name
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.extension = "EXTEND"
        tex.location = (-400, 300)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Metallic"].default_value = 0.5
        bsdf.inputs["Roughness"].default_value = 0.35
    return mat


def new_mesh(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(verts).tolist(), [], faces)
    me.update()
    return me


def replace_mesh(ob, me):
    old = ob.data
    ob.data = me
    if old and old.users == 0:
        bpy.data.meshes.remove(old)


def union_meshes(a_me, b_me):
    """Boolean-Vereinigung zweier Meshes (Exact-Solver) ohne Operator-Kontext."""
    a = bpy.data.objects.new("_felge3d_a", a_me)
    b = bpy.data.objects.new("_felge3d_b", b_me)
    scn = bpy.context.scene
    scn.collection.objects.link(a)
    scn.collection.objects.link(b)
    try:
        mod = a.modifiers.new("Union", "BOOLEAN")
        mod.operation = "UNION"
        mod.solver = "EXACT"
        mod.object = b
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        me = bpy.data.meshes.new_from_object(a.evaluated_get(dg))
        me.name = "Felge"
    finally:
        bpy.data.objects.remove(a)
        bpy.data.objects.remove(b)
    return me


def unique_collection_name(base):
    name, i = base, 2
    while name in bpy.data.collections:
        name = "%s.%d" % (base, i)
        i += 1
    return name


def build_wheel(context, s, new_collection=True):
    """Komplette Pipeline. Gibt (collection, info-text) zurück."""
    gray, cx, cy, rx, ry = prepare(s)
    mask, thr = compute_mask(s, gray, cx, cy, rx, ry)
    if thr is not None and s.auto_threshold:
        s["threshold"] = thr          # anzeigen, ohne Update-Callback auszulösen

    n = 1
    if s.sym_mode == "AUTO":
        n, _ = core.detect_symmetry_gray(gray, cx, cy, rx, ry)
    elif s.sym_mode == "MANUAL":
        n = s.sym_n
    s["detected_n"] = n

    p = make_params(s)
    res = core.build(mask, cx, cy, rx, ry, p, symmetry_n=n)
    if not res["star_faces"]:
        raise RuntimeError("Keine Speichen erkannt – Erkennung/Schwellwert prüfen (Maske anzeigen).")

    img_name = os.path.splitext(s.image.name)[0]
    star_me = new_mesh("Felgenstern", res["star_verts"], res["star_faces"])
    set_smooth(star_me, 30, res["star_sharp"])
    barrel_me = new_mesh("Felgenbett", res["barrel_verts"], res["barrel_faces"])
    set_smooth(barrel_me, 35)
    if s.photo_texture:
        R_out = core.dimensions(p)[4]
        photo = get_photo_material(s.image)
        plain = get_material("Felge3D_Grund_" + s.image.name, mean_color(s.image, mask), 0.6, 0.4)
        for me in (star_me, barrel_me):
            project_photo_uv(me, s, R_out)
            me.materials.append(photo)
            me.materials.append(plain)
            # Foto nur auf Flächen, die nach vorn zeigen – Wände/Bett einfarbig (keine Schlieren)
            nrm = np.empty(len(me.polygons) * 3, dtype=np.float32)
            me.polygons.foreach_get("normal", nrm)
            me.polygons.foreach_set("material_index", (nrm[2::3] < 0.35).astype(np.int32))
    else:
        star_me.materials.append(get_material("Felge3D_Stern", (0.05, 0.05, 0.055, 1), 0.6, 0.45))
        barrel_me.materials.append(get_material("Felge3D_Bett", (0.7, 0.7, 0.72, 1), 1.0, 0.25))

    meshes = [("star", "Felgenstern", star_me), ("barrel", "Felgenbett", barrel_me)]
    if s.one_body:
        meshes = [("body", "Felge", union_meshes(barrel_me, star_me))]

    col = s.collection if (not new_collection and s.collection
                           and s.collection.name in bpy.data.collections) else None
    if col is None:
        col = bpy.data.collections.new(unique_collection_name("Felge " + img_name))
        context.scene.collection.children.link(col)
        s.collection = col
    # alte Objekte der Collection entfernen (Empty bleibt)
    root = None
    for ob in list(col.objects):
        if ob.get("felge3d_role") == "root":
            root = ob
        else:
            me = ob.data
            bpy.data.objects.remove(ob)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
    if root is None:
        root = bpy.data.objects.new("Felge_Achse", None)
        root.empty_display_type = "CIRCLE"
        root.empty_display_size = 0.3
        root.rotation_euler = (math.pi / 2, 0, 0)   # Felge steht, Front zeigt nach -Y
        root["felge3d_role"] = "root"
        col.objects.link(root)
    for role, name, me in meshes:
        ob = bpy.data.objects.new(name, me)
        ob["felge3d_role"] = role
        ob.parent = root
        col.objects.link(ob)
    for _, _, me in (("star", "", star_me), ("barrel", "", barrel_me)):
        if me.users == 0:
            bpy.data.meshes.remove(me)

    nf = sum(len(ob.data.polygons) for ob in col.objects if ob.type == "MESH")
    info = "Felge erzeugt: %d-fach symmetrisch, Konkavität %.0f mm, Nabenanlage bei %.1f mm, %d Flächen" % (
        n, res["dish"], res["hub_back"], nf)
    return col, info


def show_in_image_editor(context, img):
    for area in context.screen.areas if context.screen else []:
        if area.type == "IMAGE_EDITOR":
            area.spaces.active.image = img
            return True
    return False


# ============================================================ Operatoren
class FELGE3D_OT_import_image(Operator, ImportHelper):
    """Felgenfoto (Frontansicht) laden und sofort als 3D-Felge in einer neuen Collection erzeugen"""
    bl_idname = "felge3d.import_image"
    bl_label = "Felgenbild laden & bauen"
    bl_options = {"REGISTER", "UNDO"}

    filter_glob: StringProperty(default="*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.tif;*.tiff", options={"HIDDEN"})

    def execute(self, context):
        s = context.scene.felge3d
        try:
            img = bpy.data.images.load(self.filepath, check_existing=True)
        except RuntimeError as e:
            self.report({"ERROR"}, "Bild nicht lesbar: %s" % e)
            return {"CANCELLED"}
        s.image = img
        s.mask_image = None
        if s.auto_detect:
            bpy.ops.felge3d.detect()
        try:
            col, info = build_wheel(context, s, new_collection=True)
        except Exception as e:  # noqa: BLE001 – Fehler dem Nutzer anzeigen
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, info)
        return {"FINISHED"}


class FELGE3D_OT_rebuild(Operator):
    """Felge mit den aktuellen Einstellungen neu berechnen"""
    bl_idname = "felge3d.rebuild"
    bl_label = "Neu bauen"
    bl_options = {"REGISTER", "UNDO"}

    new_collection: BoolProperty(name="Neue Collection", default=False)

    def execute(self, context):
        s = context.scene.felge3d
        try:
            col, info = build_wheel(context, s, new_collection=self.new_collection)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, info)
        return {"FINISHED"}


class FELGE3D_OT_detect(Operator):
    """Felgenkontur im Bild automatisch suchen"""
    bl_idname = "felge3d.detect"
    bl_label = "Felge im Bild finden"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.felge3d
        if not s.image:
            self.report({"ERROR"}, "Kein Bild geladen.")
            return {"CANCELLED"}
        gray = core.downscale(image_to_gray(s.image), s.proc_size)
        h, w = gray.shape
        cx, cy, rx, ry = core.find_wheel(gray)
        s.center_x, s.center_y = cx / w, cy / h
        s.radius = rx / w
        s.aspect = ry / rx
        return {"FINISHED"}


class FELGE3D_OT_preview(Operator):
    """Erkannte Maske und Felgenkontur als Bild anzeigen (Bildeditor)"""
    bl_idname = "felge3d.preview"
    bl_label = "Maske anzeigen"

    def execute(self, context):
        s = context.scene.felge3d
        try:
            gray, cx, cy, rx, ry = prepare(s)
            mask, _ = compute_mask(s, gray, cx, cy, rx, ry)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        h, w = gray.shape
        rn = core.norm_radius(gray.shape, cx, cy, rx, ry)
        rgb = np.repeat(gray[..., None] * 0.6, 3, axis=2)
        rgb[mask > 0.5] = rgb[mask > 0.5] * 0.4 + np.array([0.1, 0.6, 0.1])
        rgb[np.abs(rn - 1.0) < 2.0 / rx] = (1, 0, 0)
        rgba = np.concatenate([rgb, np.ones((h, w, 1))], axis=2).astype(np.float32)
        img = bpy.data.images.get(PREVIEW_NAME)
        if img is None or tuple(img.size) != (w, h):
            if img:
                bpy.data.images.remove(img)
            img = bpy.data.images.new(PREVIEW_NAME, w, h)
        img.pixels.foreach_set(rgba.ravel())
        img.update()
        if not show_in_image_editor(context, img):
            self.report({"INFO"}, "Vorschau-Bild '%s' erstellt – im Bildeditor öffnen." % PREVIEW_NAME)
        return {"FINISHED"}


class FELGE3D_OT_mask_to_image(Operator):
    """Aktuelle Maske als bemalbares Bild anlegen (weiß = Material) und als eigene Maske verwenden"""
    bl_idname = "felge3d.mask_to_image"
    bl_label = "Maske zum Bemalen anlegen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.felge3d
        try:
            gray, cx, cy, rx, ry = prepare(s)
            s.mask_image = None
            mask, _ = compute_mask(s, gray, cx, cy, rx, ry)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        h, w = mask.shape
        img = bpy.data.images.get(MASK_NAME)
        if img is None or tuple(img.size) != (w, h):
            if img:
                bpy.data.images.remove(img)
            img = bpy.data.images.new(MASK_NAME, w, h)
        rgba = np.repeat(mask[..., None], 4, axis=2)
        rgba[..., 3] = 1
        img.pixels.foreach_set(rgba.astype(np.float32).ravel())
        img.update()
        s.mask_image = img
        show_in_image_editor(context, img)
        self.report({"INFO"}, "Maske '%s' angelegt – im Bildeditor (Paint-Modus) bearbeiten, dann 'Neu bauen'." % MASK_NAME)
        return {"FINISHED"}


class FELGE3D_OT_export_obj(Operator, ExportHelper):
    """Aktuelle Felge als OBJ exportieren"""
    bl_idname = "felge3d.export_obj"
    bl_label = "Als OBJ exportieren"
    filename_ext = ".obj"
    filter_glob: StringProperty(default="*.obj", options={"HIDDEN"})

    def execute(self, context):
        s = context.scene.felge3d
        col = s.collection
        if not col:
            self.report({"ERROR"}, "Noch keine Felge erzeugt.")
            return {"CANCELLED"}
        for ob in context.view_layer.objects:
            ob.select_set(False)
        meshes = [ob for ob in col.objects if ob.type == "MESH"]
        for ob in meshes:
            ob.select_set(True)
        context.view_layer.objects.active = meshes[0]
        bpy.ops.wm.obj_export(filepath=self.filepath, export_selected_objects=True,
                              apply_modifiers=True, export_materials=True)
        self.report({"INFO"}, "Exportiert: %s" % self.filepath)
        return {"FINISHED"}



# ============================================================ Update von GitHub
_update_state = {"remote": None, "msg": ""}


def get_prefs(context):
    return context.preferences.addons[__package__].preferences


class Felge3DPreferences(AddonPreferences):
    bl_idname = __package__

    repo: StringProperty(name="GitHub-Repository", default="5jn2zm8msr-ship-it/test01",
                         description="Form: besitzer/repo, z.B. maxmuster/felge3d")
    branch: StringProperty(name="Branch", default="main")
    token: StringProperty(name="Token (nur privates Repo)", default="", subtype="PASSWORD",
                          description="GitHub Fine-grained Token mit Leserecht 'Contents' – bei öffentlichem Repo leer lassen")

    def draw(self, context):
        L = self.layout
        L.prop(self, "repo")
        L.prop(self, "branch")
        L.prop(self, "token")
        draw_update_box(L)


def draw_update_box(layout):
    box = layout.box()
    box.label(text="Version %d.%d.%d" % bl_info["version"], icon="INFO")
    row = box.row(align=True)
    row.operator("felge3d.check_update", icon="URL")
    r = _update_state["remote"]
    if r and r > tuple(bl_info["version"]):
        row.operator("felge3d.install_update", icon="IMPORT", text="Update %d.%d.%d installieren" % r)
    if _update_state["msg"]:
        box.label(text=_update_state["msg"])


class FELGE3D_OT_check_update(Operator):
    """Auf GitHub nach einer neueren Version suchen"""
    bl_idname = "felge3d.check_update"
    bl_label = "Nach Update suchen"

    def execute(self, context):
        p = get_prefs(context)
        if not p.repo:
            _update_state["msg"] = "Repository in den Add-on-Einstellungen eintragen."
            self.report({"ERROR"}, _update_state["msg"])
            return {"CANCELLED"}
        try:
            r = updater.remote_version(p.repo, p.branch, p.token)
        except Exception as e:  # noqa: BLE001
            _update_state["msg"] = updater.describe_error(e)
            self.report({"ERROR"}, _update_state["msg"])
            return {"CANCELLED"}
        _update_state["remote"] = r
        cur = tuple(bl_info["version"])
        if r and r > cur:
            _update_state["msg"] = "Neue Version %d.%d.%d verfügbar." % r
        else:
            _update_state["msg"] = "Aktuell (%d.%d.%d)." % cur
        self.report({"INFO"}, _update_state["msg"])
        return {"FINISHED"}


class FELGE3D_OT_install_update(Operator):
    """Neueste Version von GitHub herunterladen und installieren"""
    bl_idname = "felge3d.install_update"
    bl_label = "Update installieren"

    def execute(self, context):
        p = get_prefs(context)
        try:
            files = updater.install_latest(p.repo, p.branch, p.token)
        except Exception as e:  # noqa: BLE001
            _update_state["msg"] = updater.describe_error(e)
            self.report({"ERROR"}, _update_state["msg"])
            return {"CANCELLED"}
        _update_state["msg"] = "Installiert (%s) – bitte Blender neu starten." % ", ".join(files)
        _update_state["remote"] = None
        self.report({"INFO"}, _update_state["msg"])
        return {"FINISHED"}


# ============================================================ Oberfläche
class FELGE3D_PT_main(Panel):
    bl_label = "Felge3D"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"

    def draw(self, context):
        s = context.scene.felge3d
        col = self.layout.column(align=True)
        col.scale_y = 1.4
        col.operator("felge3d.import_image", icon="FILE_IMAGE")
        row = self.layout.row(align=True)
        row.operator("felge3d.rebuild", icon="FILE_REFRESH")
        row.operator("felge3d.rebuild", text="", icon="ADD").new_collection = True
        self.layout.prop(s, "image")
        if s.collection:
            self.layout.label(text="Collection: " + s.collection.name, icon="OUTLINER_COLLECTION")
        self.layout.operator("felge3d.export_obj", icon="EXPORT")


class FELGE3D_PT_dims(Panel):
    bl_label = "Maße"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"

    def draw(self, context):
        s = context.scene.felge3d
        c = self.layout.column(align=True)
        c.prop(s, "diameter", slider=True)
        c.prop(s, "width")
        c = self.layout.column(align=True)
        c.prop(s, "use_et")
        if s.use_et:
            c.prop(s, "et")
        else:
            c.prop(s, "dish")
        c.prop(s, "dish_power")
        c.prop(s, "face_inset")
        c.prop(s, "spoke_thickness")
        c.prop(s, "hub_thickness")
        c.prop(s, "hub_radius")
        c = self.layout.column(align=True)
        c.prop(s, "relief")
        c.prop(s, "relief_width")
        self.layout.prop(s, "one_body")
        self.layout.prop(s, "photo_texture")


class FELGE3D_PT_detect(Panel):
    bl_label = "Erkennung"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        L.prop(s, "auto_detect")
        c = L.column(align=True)
        c.prop(s, "center_x")
        c.prop(s, "center_y")
        c.prop(s, "radius")
        c.prop(s, "aspect")
        L.operator("felge3d.detect", icon="VIEWZOOM")
        L.separator()
        L.prop(s, "seg_mode")
        if s.seg_mode == "BAND":
            c = L.column(align=True)
            c.prop(s, "threshold", text="Lücke von")
            c.prop(s, "threshold_hi", text="Lücke bis")
        else:
            L.prop(s, "auto_threshold")
            sub = L.row()
            sub.enabled = not s.auto_threshold
            sub.prop(s, "threshold")
        row = L.row()
        row.prop(s, "invert")
        row.prop(s, "clean")
        row = L.row(align=True)
        row.prop(s, "sym_mode", text="")
        if s.sym_mode == "MANUAL":
            row.prop(s, "sym_n")
        elif s.sym_mode == "AUTO" and s.detected_n:
            row.label(text="%d-fach" % s.detected_n if s.detected_n > 1 else "keine")
        L.separator()
        row = L.row(align=True)
        row.operator("felge3d.preview", icon="HIDE_OFF")
        row.operator("felge3d.mask_to_image", icon="BRUSH_DATA")
        L.prop(s, "mask_image")


class FELGE3D_PT_update(Panel):
    bl_label = "Update"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        draw_update_box(self.layout)


class FELGE3D_PT_advanced(Panel):
    bl_label = "Erweitert"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        c = self.layout.column(align=True)
        for k in ("flange", "wall", "drop"):
            c.prop(s, k)
        c = self.layout.column(align=True)
        for k in ("res_radial", "res_angular", "sections", "proc_size"):
            c.prop(s, k)


classes = (
    Felge3DPreferences,
    Felge3DSettings,
    FELGE3D_OT_check_update,
    FELGE3D_OT_install_update,
    FELGE3D_OT_import_image,
    FELGE3D_OT_rebuild,
    FELGE3D_OT_detect,
    FELGE3D_OT_preview,
    FELGE3D_OT_mask_to_image,
    FELGE3D_OT_export_obj,
    FELGE3D_PT_main,
    FELGE3D_PT_dims,
    FELGE3D_PT_detect,
    FELGE3D_PT_advanced,
    FELGE3D_PT_update,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.felge3d = PointerProperty(type=Felge3DSettings)


def unregister():
    del bpy.types.Scene.felge3d
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
