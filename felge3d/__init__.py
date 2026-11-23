# SPDX-License-Identifier: GPL-3.0-or-later
"""
Felge3D – Blender-Add-on: Felgenfoto (Frontansicht) laden -> 3D-Felge in neuer Collection.

Bedienung: 3D-Viewport -> Seitenleiste (N) -> Reiter "Felge".
Läuft mit Blender 3.6 (Legacy-Add-on) und 4.2+ (Extension, siehe blender_manifest.toml).
"""

bl_info = {
    "name": "Felge3D",
    "author": "Felge3D",
    "version": (0, 19, 1),
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
from mathutils import Matrix

# Beim Neu-Aktivieren/Update ohne Neustart lädt Blender Untermodule nicht neu -> selbst nachladen
if "core" in locals():
    import importlib
    core = importlib.reload(core)
    updater = importlib.reload(updater)
    ai = importlib.reload(ai)
    car = importlib.reload(car)
else:
    from . import ai, car, core, updater

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
    tire_mode: EnumProperty(name="Reifen im Foto", default="AUTO", items=[
        ("AUTO", "Automatisch", "Reifen erkennen und Felgenhorn wählen"),
        ("YES", "Ja – Reifen sichtbar", "Äußeren Kreis (Reifen) überspringen und das Felgenhorn davor nehmen"),
        ("NO", "Nein – nur Felge", "Äußersten deutlichen Kreis als Felge nehmen"),
    ])
    warning: StringProperty(default="")
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
        ("AUTO", "Automatisch", "Wählt selbst: Hintergrund-Vergleich (auch zweifarbige Felgen) oder Helligkeit"),
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
    method_used: StringProperty(name="Methode", default="")
    ai_used: BoolProperty(name="KI verwendet", default=False)

    # --- Maße
    diameter: IntProperty(name="Felgengröße (Zoll)", default=20, min=19, max=24,
                          subtype="NONE", update=_update_rebuild,
                          description="Durchmesser der Felge in Zoll (19–24)")
    width: FloatProperty(name="Breite (Zoll, J)", default=8.5, min=4, max=14, update=_update_rebuild,
                         description="Felgenbreite in Zoll (J-Wert aus dem Datenblatt, z.B. 8,5J)")
    use_et: BoolProperty(name="Form aus Breite + ET", default=True, update=_update_rebuild,
                         description="Konkav/konvex und Schüsseltiefe aus Breite (J) und Einpresstiefe (ET) berechnen "
                                     "– physikalisch eindeutig. Aus = Schüssel von Hand")
    et: FloatProperty(name="ET (mm)", default=40.0, min=-50, max=120, update=_update_rebuild,
                      description="Einpresstiefe aus dem Datenblatt (z.B. ET44)")
    dish: FloatProperty(name="Schüssel (mm)", default=40.0, min=-80, max=150, update=_update_rebuild,
                        description="Von Hand: Mitte liegt so viel tiefer als der Rand. Positiv = konkav, negativ = konvex")
    dish_power: FloatProperty(name="Wölbungsform", default=1.5, min=0.5, max=4,
                              description="1 = gerader Kegel, größer = runder")
    face_inset: FloatProperty(name="Stern-Rücksprung (mm)", default=12.0, min=0, max=60,
                              description="Wie weit der Stern außen hinter dem Felgenhorn liegt")
    spoke_thickness: FloatProperty(name="Speichendicke Rand (mm)", default=14.0, min=4, max=80,
                                   update=_update_rebuild)
    hub_thickness: FloatProperty(name="Nabendicke (mm)", default=24.0, min=10, max=120,
                                 update=_update_rebuild,
                                 description="Materialstärke an der Nabe (Speichen werden zur Mitte hin dicker)")
    hub_radius: FloatProperty(name="Nabenfläche Radius (mm)", default=85.0, min=30, max=150,
                              update=_update_rebuild,
                              description="Radius der flachen Nabenanlagefläche")
    relief: FloatProperty(name="Speichenrücken (mm)", default=4.0, min=0, max=20,
                          update=_update_rebuild,
                          description="Sanfte Wölbung der Speichenoberfläche (0 = flach)")
    relief_width: FloatProperty(name="Max. Rundungsbreite (mm)", default=40.0, min=2, max=120,
                                update=_update_rebuild,
                                description="Schmale Speichen werden über ihre ganze Breite gewölbt, breite Flächen höchstens über diese Breite")
    edge_round: FloatProperty(name="Kantenverrundung (mm)", default=2.5, min=0, max=8, update=_update_rebuild,
                              description="Verrundet alle Fensterkanten (fängt Glanzlichter wie echtes Material)")
    boss_height: FloatProperty(name="Nabenbund Höhe (mm)", default=6.0, min=0, max=60,
                               update=_update_rebuild,
                               description="Erhabener Bund um den Zentralverschluss / die Nabe (0 = aus)")
    boss_radius: FloatProperty(name="Nabenbund Radius (mm)", default=75.0, min=20, max=200,
                               update=_update_rebuild)
    bore: FloatProperty(name="Mittelbohrung (mm)", default=0.0, min=0, max=200, update=_update_rebuild,
                        description="0 = Zentrum wie im Foto (Deckel/Logo). >0 schneidet ein rundes Loch")
    min_hole: FloatProperty(name="Kleine Löcher füllen (mm²)", default=60.0, min=0, max=2000,
                            update=_update_rebuild,
                            description="Lücken kleiner als diese Fläche gelten als Störung (Spiegelung) und werden gefüllt")
    use_ai: BoolProperty(name="KI-Relief", default=True, update=_update_rebuild,
                         description="Optional: feine Details (Speichenform, Kanten) aus der KI-Tiefe zusätzlich einrechnen")
    ai_quality: EnumProperty(name="KI-Qualität", default="HIGH", update=_update_rebuild, items=[
        ("HIGH", "Hoch (DA3 Large)", "Depth Anything 3 Mono-Large – saubere Flächen, ~5–20 s pro Bild"),
        ("FAST", "Schnell (DA2 Small)", "Depth Anything V2 Small – unter 1 s, etwas rauschiger"),
    ])
    ai_depth: FloatProperty(name="KI-Relief (mm)", default=0.0, min=0, max=60, update=_update_rebuild,
                            description="Stärke der KI-Details. 0 = aus (saubere, glatte Form – empfohlen)")
    relief_fade: FloatProperty(name="Relief-Auslauf zum Rand", default=0.35, min=0.05, max=1.0,
                               update=_update_rebuild, subtype="FACTOR",
                               description="Über welchen Anteil des Radius das Relief zum Felgenrand auf 0 ausläuft")
    tone_step: FloatProperty(name="Stufe glanzgedreht (mm)", default=0.0, min=0, max=15, update=_update_rebuild,
                             description="Optional: glanzgedrehte Fläche steht gegenüber dem dunklen Bereich vor "
                                         "(nur bei zweifarbigen Felgen, 0 = aus)")
    tone_info: StringProperty(default="")
    pocket_color: bpy.props.FloatVectorProperty(name="Taschen-Farbe", subtype="COLOR", size=3,
                                                default=(0.015, 0.015, 0.017), min=0, max=1,
                                                update=_update_rebuild,
                                                description="Farbe der Fensterwände in der Tiefe")
    ai_strength: FloatProperty(name="KI-Anteil", default=1.0, min=0, max=1.5, update=_update_rebuild,
                               description="0 = nur Formmodell, 1 = Vorderfläche komplett aus KI-Tiefe")
    min_thick: FloatProperty(name="Mindestwandstärke (mm)", default=6.0, min=2, max=30, update=_update_rebuild)
    one_body: BoolProperty(name="Ein Körper (Boolean)", default=False,
                           description="Stern und Felgenbett per Boolean zu einem geschlossenen Mesh vereinen")
    flange: FloatProperty(name="Hornhöhe (mm)", default=17.0, min=5, max=30)
    wall: FloatProperty(name="Wandstärke (mm)", default=5.0, min=2, max=15)
    drop: FloatProperty(name="Tiefbett (mm)", default=22.0, min=5, max=50)

    # --- Aussehen
    photo_texture: BoolProperty(name="Foto als Textur", default=True,
                                description="Das Felgenfoto von vorn auf die Felge projizieren (Farben, Logo, Glanz wie im Bild)")

    # --- Qualität
    res_radial: IntProperty(name="Ringe", default=240, min=40, max=600, update=_update_rebuild)
    res_angular: IntProperty(name="Segmente Stern", default=1080, min=120, max=3600, update=_update_rebuild)
    sections: IntProperty(name="Segmente Bett", default=128, min=32, max=512)


# ============================================================ Hilfsfunktionen
def image_to_gray(img):
    """Blender-Bild -> Graustufen-numpy-Array (Zeile 0 = unten), Werte 0..1."""
    w, h = img.size
    if w == 0 or h == 0:
        raise RuntimeError("Bild '%s' konnte nicht gelesen werden (Format %s nicht unterstützt – bitte als JPG/PNG speichern)."
                           % (img.name, os.path.splitext(img.filepath)[1].upper() or "?"))
    ch = img.channels
    buf = np.empty(w * h * ch, dtype=np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(h, w, ch)
    if ch >= 3:
        return core.rgba_to_gray(buf)
    return buf[..., 0].copy()


def image_to_rgb(img, max_size):
    """Blender-Bild -> verkleinertes RGB-Array (Zeile 0 = unten)."""
    w, h = img.size
    if w == 0 or h == 0:
        raise RuntimeError("Bild '%s' konnte nicht gelesen werden." % img.name)
    ch = img.channels
    buf = np.empty(w * h * ch, dtype=np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(h, w, ch)
    if ch < 3:
        buf = np.repeat(buf[..., :1], 3, axis=2)
    if ch == 4:
        a = buf[..., 3:4]
        if (a < 0.98).mean() > 0.02:                 # transparenter Hintergrund (PNG) -> auf Weiß setzen
            buf = np.concatenate([buf[..., :3] * a + (1.0 - a), np.ones_like(a)], axis=2)
    return core.downscale_rgb(buf, max_size)


_rgb_cache = {}


def prepare(s):
    """Bild laden, verkleinern, Felgenlage in Arbeits-Pixeln bestimmen."""
    if not s.image:
        raise RuntimeError("Kein Bild geladen.")
    key = (s.image.name, s.proc_size, tuple(s.image.size))
    if key not in _rgb_cache:
        _rgb_cache.clear()
        _rgb_cache[key] = image_to_rgb(s.image, s.proc_size)
    rgb = _rgb_cache[key]
    gray = core.rgba_to_gray(rgb)
    h, w = gray.shape
    cx = s.center_x * w
    cy = s.center_y * h
    rx = s.radius * w
    ry = rx * s.aspect
    return gray, cx, cy, rx, ry


_depth_cache = {}


def ai_depth(s, cx, cy, rx, ry):
    """KI-Tiefenkarte im Arbeitsbild – oder None, wenn KI aus/nicht installiert."""
    if s.ai_depth <= 0 or not s.use_ai or not ai.is_ready(s.ai_quality):
        return None
    key = (s.image.name, s.proc_size, s.ai_quality, round(cx, 1), round(cy, 1), round(rx, 1), round(ry, 1))
    if key not in _depth_cache:
        _depth_cache.clear()
        rgb = _rgb_cache[next(iter(_rgb_cache))]
        _depth_cache[key] = ai.depth_map(rgb, cx, cy, rx, ry, kind=s.ai_quality)
    return _depth_cache[key]


def symmetry_order(s, gray, cx, cy, rx, ry):
    if s.sym_mode == "AUTO":
        n, _ = core.detect_symmetry_gray(gray, cx, cy, rx, ry)
    elif s.sym_mode == "MANUAL":
        n = s.sym_n
    else:
        n = 1
    s["detected_n"] = n
    return n


def hub_symmetry(s, gray, cx, cy, rx, ry, n):
    if s.sym_mode == "OFF":
        return 1
    if s.sym_mode == "MANUAL":
        return n
    return core.detect_hub_symmetry(gray, cx, cy, rx, ry, n)


def compute_mask(s, gray, cx, cy, rx, ry, n=None):
    if s.mask_image:
        m = image_to_gray(s.mask_image)
        if m.shape != gray.shape:
            # auf Arbeitsauflösung bringen (nächster Nachbar)
            yi = (np.arange(gray.shape[0]) * m.shape[0] / gray.shape[0]).astype(int)
            xi = (np.arange(gray.shape[1]) * m.shape[1] / gray.shape[1]).astype(int)
            m = m[yi][:, xi]
        return (m > 0.5).astype(np.float32), None
    if s.seg_mode == "AUTO":
        if n is None:
            n = symmetry_order(s, gray, cx, cy, rx, ry)
        rgb = _rgb_cache[next(iter(_rgb_cache))]
        mask, method = core.segment_auto(rgb, cx, cy, rx, ry, n, s.clean)
        s["method_used"] = method
        return mask, None
    return core.segment(gray, cx, cy, rx, ry, s.seg_mode, s.auto_threshold,
                        s.threshold, s.threshold_hi, s.invert, s.clean)


def analysis_for(s):
    """Aktuelle Formanalyse (live, unabhängig vom Bauen) aus den Einstellungen."""
    p = make_params(s)
    if s.use_et:
        a = core.shape_analysis(p)
        a["mode"] = "Felgendaten (J/ET)"
    else:
        d = s.dish
        v = "KONKAV" if d > 6 else ("KONVEX" if d < -6 else "FLACH")
        a = dict(verdict=v, dish_mm=d, hub_back_mm=None, warn="", mode="von Hand",
                 text="%s - Schüssel %+.0f mm (von Hand)" % (v, d))
    return a


def make_params(s):
    p = core.Params()
    for k in ("diameter", "width", "use_et", "et", "face_inset", "dish", "dish_power",
              "spoke_thickness", "hub_thickness", "hub_radius", "relief", "relief_width", "boss_height", "boss_radius", "min_hole", "bore", "ai_strength", "ai_depth", "relief_fade", "tone_step", "edge_round", "min_thick", "flange", "wall", "drop", "res_radial", "res_angular", "sections"):
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


def clean_texture(img, mask, closed_mask=None):
    """
    Bereinigte Fototextur: Hintergrund und ein schmaler Kantensaum werden mit der Farbe des
    angrenzenden Felgenmaterials gefüllt (keine weißen Nähte an Speichenkanten / Löchern).
    """
    w, h = img.size
    ch = img.channels
    buf = np.empty(w * h * ch, dtype=np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(h, w, ch)
    rgb = buf[..., :3] if ch >= 3 else np.repeat(buf[..., :1], 3, axis=2)
    # Maske (Arbeitsauflösung) auf volle Bildgröße, dann um einen Saum verkleinern
    yi = np.minimum((np.arange(h) * mask.shape[0] / h).astype(int), mask.shape[0] - 1)
    xi = np.minimum((np.arange(w) * mask.shape[1] / w).astype(int), mask.shape[1] - 1)
    valid = mask[yi][:, xi] > 0.5
    k = max(3, int(round(w / 150.0)))                      # Saum ~0,7 % der Bildbreite (Kantenreflexe weg)
    valid = core.blur(valid.astype(np.float32), k, 1) > 0.999
    # Arbeitsauflösung für das Füllen (schnell), dann nur ungültige Pixel ersetzen
    f = max(1, int(np.ceil(max(w, h) / 1024.0)))
    small = rgb[::f, ::f]
    vs = valid[::f, ::f]
    filled_small = core.fill_background(small, vs, iters=16, radius=3)
    up = filled_small[np.minimum(np.arange(h) // f, filled_small.shape[0] - 1)][:, np.minimum(np.arange(w) // f, filled_small.shape[1] - 1)]
    out = np.where(valid[..., None], rgb, up)
    name = "Felge3D_Textur_" + img.name
    tex = bpy.data.images.get(name)
    if tex is None or tuple(tex.size) != (w, h):
        if tex:
            bpy.data.images.remove(tex)
        tex = bpy.data.images.new(name, w, h)
    rgba = np.concatenate([out, np.ones((h, w, 1), np.float32)], axis=2)
    tex.pixels.foreach_set(rgba.astype(np.float32).ravel())
    tex.update()
    try:
        tex.pack()                                         # mit der .blend-Datei speichern
    except Exception:  # noqa: BLE001
        pass
    return tex


def get_photo_material(img, tex_img=None):
    """
    Fotomaterial mit zweifarbiger Steuerung: Helle (polierte/gedrehte) Flächen werden metallisch
    und glänzend, dunkler Lack matter und weniger metallisch – direkt aus der Helligkeit der Textur.
    """
    name = "Felge3D_Foto_" + img.name
    mat = bpy.data.materials.get(name)
    if mat is not None and mat.get("felge3d_pbr") != 2:
        bpy.data.materials.remove(mat)           # alte Version ohne Metall-Steuerung neu aufbauen
        mat = None
    if mat is not None and tex_img is not None:
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE":
                node.image = tex_img
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat["felge3d_pbr"] = 2
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = tex_img or img
        tex.extension = "EXTEND"
        tex.location = (-700, 300)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        bw.location = (-450, 80)
        nt.links.new(tex.outputs["Color"], bw.inputs["Color"])

        def remap(label, y, lo, hi, out_name):
            mr = nt.nodes.new("ShaderNodeMapRange")
            mr.label = label
            mr.location = (-230, y)
            mr.inputs["From Min"].default_value = 0.22
            mr.inputs["From Max"].default_value = 0.62
            mr.inputs["To Min"].default_value = lo
            mr.inputs["To Max"].default_value = hi
            nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"], bsdf.inputs[out_name])

        remap("Metall (hell = poliert)", 120, 0.08, 0.92, "Metallic")
        remap("Rauheit (hell = glänzend)", -120, 0.50, 0.24, "Roughness")
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


def make_rim_meshes(context, s, overrides=None):
    """
    Foto -> Felgenmeshes (Stern + Bett, mit Materialien und Foto-UV), noch ohne Objekte/Collection.
    overrides: Maße überschreiben, z.B. dict(diameter=20.0, width=10.0, et=45.0, use_et=True) (für das Fahrzeug-Paket).
    Gibt dict(star_me, barrel_me, res, n, depth, p, mask) zurück.
    """
    gray, cx, cy, rx, ry = prepare(s)
    n = symmetry_order(s, gray, cx, cy, rx, ry)
    mask, thr = compute_mask(s, gray, cx, cy, rx, ry, n)
    if thr is not None and s.auto_threshold:
        s["threshold"] = thr          # anzeigen, ohne Update-Callback auszulösen

    # Plausibilität: Nabe muss Material sein, Materialanteil im üblichen Bereich, Symmetrie erkannt
    rn = core.norm_radius(mask.shape, cx, cy, rx, ry)
    frac = float(mask[rn < 0.97].mean()) if (rn < 0.97).any() else 0.0
    hubfrac = float(mask[(rn > 0.12) & (rn < 0.30)].mean())
    warn = []
    if hubfrac < 0.5:
        warn.append("Nabe nicht als Material erkannt")
    if frac < 0.20 or frac > 0.88:
        warn.append("Materialanteil %.0f %% ungewöhnlich" % (frac * 100))
    if n <= 1 and s.sym_mode == "AUTO":
        warn.append("keine Speichenordnung erkannt")
    if rx > 0.5 * mask.shape[1] * 1.02 or rx < 0.28 * mask.shape[1]:
        warn.append("Felgenkreis unplausibel (Reifen im Foto?)")
    s["warning"] = "; ".join(warn)
    p = make_params(s)
    for k_, v_ in (overrides or {}).items():
        setattr(p, k_, v_)
    depth = ai_depth(s, cx, cy, rx, ry)
    hub_n = hub_symmetry(s, gray, cx, cy, rx, ry, n)
    res = core.build(mask, cx, cy, rx, ry, p, symmetry_n=n, depth=depth, hub_n=hub_n, gray=gray)
    s["tone_info"] = res.get("tone_info", "")
    if not res["star_faces"]:
        raise RuntimeError("Keine Speichen erkannt – Erkennung/Schwellwert prüfen (Maske anzeigen).")

    star_me = new_mesh("Felgenstern", res["star_verts"], res["star_faces"])
    set_smooth(star_me, 50, res["star_sharp"])
    barrel_me = new_mesh("Felgenbett", res["barrel_verts"], res["barrel_faces"])
    set_smooth(barrel_me, 35)
    pocket = get_material("Felge3D_Taschen", s.pocket_color[:] + (1.0,) if len(s.pocket_color) == 3
                          else tuple(s.pocket_color), 0.3, 0.6)
    pocket.diffuse_color = tuple(s.pocket_color) + (1.0,)
    bsdf = pocket.node_tree.nodes.get("Principled BSDF") if pocket.use_nodes else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = tuple(s.pocket_color) + (1.0,)
    kinds = np.array(res.get("star_kinds") or [0] * len(star_me.polygons), dtype=np.int32)
    if s.photo_texture:
        R_out = core.dimensions(p)[4]
        try:
            tex_img = clean_texture(s.image, mask)
        except Exception as e:  # noqa: BLE001
            print("Felge3D: Textur-Bereinigung fehlgeschlagen:", e)
            tex_img = None
        photo = get_photo_material(s.image, tex_img)
        plain = get_material("Felge3D_Grund_" + s.image.name, mean_color(s.image, mask), 0.6, 0.4)
        for me in (star_me, barrel_me):
            project_photo_uv(me, s, R_out)
            me.materials.append(photo)    # 0: Foto (Vorderseite)
            me.materials.append(plain)    # 1: Grundfarbe
            me.materials.append(pocket)   # 2: Taschen (dunkel)
        # Stern: fest nach Flächenart – vorn Foto, Taschenwände + Rückseite dunkel
        idx = np.where(kinds == 0, 0, 2).astype(np.int32)
        star_me.polygons.foreach_set("material_index", idx[:len(star_me.polygons)])
        # Felgenbett: nach vorn zeigende Flächen Foto, Rest Grundfarbe
        nrm = np.empty(len(barrel_me.polygons) * 3, dtype=np.float32)
        barrel_me.polygons.foreach_get("normal", nrm)
        barrel_me.polygons.foreach_set("material_index", (nrm[2::3] < 0.35).astype(np.int32))
    else:
        star_me.materials.append(get_material("Felge3D_Stern", (0.05, 0.05, 0.055, 1), 0.6, 0.45))
        barrel_me.materials.append(get_material("Felge3D_Bett", (0.7, 0.7, 0.72, 1), 1.0, 0.25))

    return dict(star_me=star_me, barrel_me=barrel_me, res=res, n=n, depth=depth, p=p, mask=mask)


def build_wheel(context, s, new_collection=True):
    """Komplette Pipeline für ein einzelnes Rad. Gibt (collection, info-text) zurück."""
    rim = make_rim_meshes(context, s)
    star_me, barrel_me, res, n, depth = rim["star_me"], rim["barrel_me"], rim["res"], rim["n"], rim["depth"]
    img_name = os.path.splitext(s.image.name)[0]
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
    s["ai_used"] = depth is not None
    info = "Felge erzeugt: %s · %d-fach symmetrisch · %d Flächen%s" % (
        res["analysis"]["text"] if s.use_et else "Schüssel %+.0f mm" % res["dish"], n, nf,
        " · mit KI-Relief" if depth is not None else "")
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


class FELGE3D_OT_reset_defaults(Operator):
    """Konkavität, Relief und Kante auf die Standardwerte zurücksetzen und neu bauen"""
    bl_idname = "felge3d.reset_defaults"
    bl_label = "Standardwerte"

    def execute(self, context):
        s = context.scene.felge3d
        for k in ("width", "et", "use_et", "dish", "ai_depth", "tone_step", "spoke_thickness", "hub_thickness",
                  "relief", "edge_round", "boss_height", "boss_radius", "dish_power", "face_inset"):
            s.property_unset(k)
        if s.image and s.collection:
            bpy.ops.felge3d.rebuild()
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
        cx, cy, rx, ry = core.find_wheel(gray, tire={'AUTO': None, 'YES': True, 'NO': False}[s.tire_mode])
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



class FELGE3D_OT_install_ai(Operator):
    """KI-Tiefe einmalig einrichten: ONNX Runtime (~50 MB) und das gewählte Modell (Hoch ~350 MB, Schnell ~27 MB). Läuft danach komplett lokal"""
    bl_idname = "felge3d.install_ai"
    bl_label = "KI-Tiefe einrichten (einmalig)"

    def execute(self, context):
        try:
            if not ai.runtime_available() or not ai.supports("HIGH"):
                self.report({"INFO"}, "Installiere ONNX Runtime …")
                ver = ai.install_runtime()
                if not ai.runtime_available():
                    raise RuntimeError("ONNX Runtime %s installiert – bitte Blender neu starten "
                                       "und 'KI-Tiefe einrichten' erneut klicken." % ver)
            s0 = context.scene.felge3d
            if s0.ai_quality == "HIGH" and not ai.supports("HIGH"):
                s0["ai_quality"] = 1   # FAST – ältere Laufzeit kann das große Modell nicht
                self.report({"WARNING"}, "Nur ältere ONNX Runtime möglich – nutze das schnelle Modell.")
            kind = s0.ai_quality
            if not os.path.isfile(ai.model_path(kind)):
                wm = context.window_manager
                wm.progress_begin(0, 100)
                try:
                    ai.download_model(kind, progress=lambda f: wm.progress_update(int(f * 100)))
                finally:
                    wm.progress_end()
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, "KI-Einrichtung fehlgeschlagen: %s" % updater.describe_error(e))
            return {"CANCELLED"}
        self.report({"INFO"}, "KI-Tiefe ist bereit.")
        s = context.scene.felge3d
        if s.image and s.collection:
            bpy.ops.felge3d.rebuild()
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
        _update_state["msg"] = "Installiert – jetzt Blender komplett beenden (Cmd+Q) und neu starten."
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
        L = self.layout
        col = L.column(align=True)
        col.scale_y = 1.4
        col.operator("felge3d.import_image", icon="FILE_IMAGE")

        box = L.box()
        box.label(text="Felgendaten (Datenblatt)", icon="PREFERENCES")
        box.prop(s, "diameter", slider=True)
        box.prop(s, "width")
        box.prop(s, "use_et")
        if s.use_et:
            box.prop(s, "et")
        else:
            box.prop(s, "dish", slider=True)
        box.prop(s, "tire_mode")

        # --- klare Formanalyse
        a = analysis_for(s)
        box = L.box()
        icon = {"KONKAV": "TRIA_DOWN", "KONVEX": "TRIA_UP", "FLACH": "REMOVE"}[a["verdict"]]
        row = box.row()
        row.label(text="Form: " + a["verdict"], icon=icon)
        if a["hub_back_mm"] is not None:
            box.label(text="Nabenanlage %.0f mm hinter dem Horn" % a["hub_back_mm"])
        txt = {"KONKAV": "Mitte liegt %.0f mm tiefer als der Rand" % abs(a["dish_mm"]),
               "KONVEX": "Mitte steht %.0f mm vor dem Rand" % abs(a["dish_mm"]),
               "FLACH": "Mitte und Rand etwa auf einer Ebene"}[a["verdict"]]
        box.label(text=txt)
        if a["warn"]:
            box.label(text=a["warn"], icon="ERROR")

        if s.warning:
            wb = L.box()
            wb.label(text="Erkennung unsicher:", icon="ERROR")
            wb.label(text=s.warning)
            wb.label(text="→ Erkennung prüfen: ‚Maske anzeigen‘")
        if s.collection:
            info = "%d Speichen" % s.detected_n if s.detected_n > 1 else "keine Symmetrie"
            L.label(text="Erkannt: " + info + (" · " + s.method_used if s.method_used else ""), icon="INFO")
            L.operator("felge3d.export_obj", icon="EXPORT")


class FELGE3D_PT_look(Panel):
    bl_label = "Aussehen"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        L.prop(s, "photo_texture")
        L.prop(s, "pocket_color")
        c = L.column(align=True)
        c.prop(s, "relief")
        c.prop(s, "edge_round")
        c.prop(s, "boss_height")
        c.prop(s, "boss_radius")
        L.operator("felge3d.reset_defaults", icon="LOOP_BACK")


class FELGE3D_PT_ai(Panel):
    bl_label = "KI-Relief (optional)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        L.label(text="Standard aus: saubere, glatte Form.")
        row = L.row(align=True)
        if ai.is_ready(s.ai_quality):
            row.prop(s, "use_ai")
        else:
            row.operator("felge3d.install_ai", icon="IMPORT")
        row.prop(s, "ai_quality", text="")
        c = L.column(align=True)
        c.prop(s, "ai_depth", slider=True)
        c.prop(s, "ai_strength")
        c.prop(s, "relief_fade")
        L.prop(s, "tone_step", slider=True)
        if s.tone_info:
            L.label(text="Zweifarbigkeit: " + s.tone_info, icon="MOD_BEVEL")


class FELGE3D_PT_dims(Panel):
    bl_label = "Feinabstimmung: Maße & Form"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        row = self.layout.row(align=True)
        row.operator("felge3d.rebuild", icon="FILE_REFRESH")
        row.operator("felge3d.rebuild", text="", icon="ADD").new_collection = True
        c = self.layout.column(align=True)
        c.prop(s, "dish_power")
        c.prop(s, "face_inset")
        c.prop(s, "spoke_thickness")
        c.prop(s, "hub_thickness")
        c.prop(s, "hub_radius")
        c.prop(s, "relief_width")
        c.prop(s, "bore")
        self.layout.prop(s, "one_body")


class FELGE3D_PT_detect(Panel):
    bl_label = "Feinabstimmung: Erkennung"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        L.prop(s, "auto_detect")
        c = L.column(align=True)
        c.prop(s, "center_x")
        c.prop(s, "center_y")
        c.prop(s, "radius")
        c.prop(s, "aspect")
        L.prop(s, "tire_mode")
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
        L.prop(s, "min_hole")
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


# ============================================================ Schritt 2: Fahrzeug-Paket (4 Räder)
class Felge3DCar(PropertyGroup):
    """Maße vom Porsche 911 GT3 RS (992), Datenblatt MY P 08/2022 – alle Werte änderbar."""
    wheelbase: FloatProperty(name="Radstand (mm)", default=2457, min=1500, max=4000)
    front_track: FloatProperty(name="Spurweite vorn (mm)", default=1630, min=1200, max=2200)
    rear_track: FloatProperty(name="Spurweite hinten (mm)", default=1582, min=1200, max=2200)
    front_rim: FloatProperty(name="Felge vorn (Zoll)", default=20, min=14, max=24)
    rear_rim: FloatProperty(name="Felge hinten (Zoll)", default=21, min=14, max=24)
    front_rim_width: FloatProperty(name="Felgenbreite vorn (J)", default=10.0, min=5, max=14)
    rear_rim_width: FloatProperty(name="Felgenbreite hinten (J)", default=13.0, min=5, max=14)
    front_et: FloatProperty(name="Einpresstiefe vorn (ET mm)", default=45, min=-20, max=80)
    rear_et: FloatProperty(name="Einpresstiefe hinten (ET mm)", default=31, min=-20, max=80)
    front_width: IntProperty(name="Reifenbreite vorn (mm)", default=275, min=145, max=405)
    rear_width: IntProperty(name="Reifenbreite hinten (mm)", default=335, min=145, max=405)
    front_aspect: IntProperty(name="Querschnitt vorn (%)", default=35, min=20, max=85)
    rear_aspect: IntProperty(name="Querschnitt hinten (%)", default=30, min=20, max=85)
    front_camber: FloatProperty(name="Sturz vorn (Grad)", default=-1.5, min=-12, max=12)
    rear_camber: FloatProperty(name="Sturz hinten (Grad)", default=-1.5, min=-12, max=12)
    front_disc: FloatProperty(name="Scheibe vorn (mm)", default=408, min=250, max=450)
    rear_disc: FloatProperty(name="Scheibe hinten (mm)", default=380, min=240, max=450)
    front_disc_thickness: FloatProperty(name="Scheibendicke vorn (mm)", default=36, min=18, max=48)
    rear_disc_thickness: FloatProperty(name="Scheibendicke hinten (mm)", default=30, min=18, max=48)

    tire_rotation: FloatProperty(name="Reifentextur drehen (Grad)", default=0, min=-180, max=180,
                                 description="Dreht die Reifentextur auf der Flanke (Beschriftung oben/unten)")
    tire_flip: BoolProperty(name="Reifentextur spiegeln", default=False)
    tread_grooves: IntProperty(name="Längsrillen", default=3, min=0, max=4)
    decal_sidewall_top: StringProperty(name="Flanke oben (PNG)", subtype="FILE_PATH", default="")
    decal_sidewall_bottom: StringProperty(name="Flanke unten (PNG)", subtype="FILE_PATH", default="")
    decal_sidewall_scale: FloatProperty(name="Flanken-Decal Höhe", default=1.0, min=.2, max=1.2)
    decal_sidewall_arc: FloatProperty(name="Flanken-Decal max. Bogen (Grad)", default=110, min=10, max=170)

    disc_style: EnumProperty(name="Scheibentyp", default="GESCHLITZT", items=[
        ("GESCHLITZT", "Geschlitzt", ""), ("GELOCHT", "Gelocht", ""), ("GLATT", "Glatt", "")])
    caliper_angle: FloatProperty(name="Sattelposition (Grad)", default=90, min=-180, max=180,
                                 description="0 = oben, 90 = Richtung Heck, -90 = Richtung Front")
    caliper_color: bpy.props.FloatVectorProperty(name="Sattelfarbe", subtype="COLOR", size=3, min=0, max=1,
                                                 default=(.55, .78, .02))
    decal_caliper: StringProperty(name="Sattel (PNG)", subtype="FILE_PATH", default="")
    decal_caliper_scale: FloatProperty(name="Sattel-Decal Größe", default=.7, min=.2, max=1.0)
    use_bevel: BoolProperty(name="Kantenfasen (Bevel)", default=True)


TIRE_TEXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "textures", "reifen.jpg")


def tire_texture_params(c):
    """
    Feste Reifentextur (im Add-on gebündelt) laden und vermessen: Mittelpunkt, Außenkante der Flanke
    und Innenkante (Wulst, heller Innenraum) werden aus dem Bild bestimmt.
    Gibt (Bild, tex-dict) zurück, oder (None, None) falls die Datei fehlt.
    """
    if not os.path.isfile(TIRE_TEXTURE):
        return None, None
    img = bpy.data.images.load(TIRE_TEXTURE, check_existing=True)
    gray = core.downscale(image_to_gray(img), 768)
    h, w = gray.shape
    cx, cy, rx, ry = core.find_wheel(gray, tire=False)      # äußerster Kreis = Reifenkante
    # Radialprofil der Helligkeit (Mittel über alle Winkel): innen weiß (Loch), dann Reifen, außen weiß
    ang = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    rr = np.linspace(0.05, 1.10, 220) * rx
    xs = cx + rr[:, None] * np.sin(ang)[None, :]
    ys = cy + rr[:, None] * np.cos(ang)[None, :] * (ry / rx)
    ok = (xs >= 0) & (xs < w - 1) & (ys >= 0) & (ys < h - 1)
    prof = np.where(ok, core.bilinear(gray, np.clip(xs, 0, w - 1.01), np.clip(ys, 0, h - 1.01)), np.nan)
    prof = np.nanmedian(prof, axis=1)
    dark = np.nonzero(prof < 0.55)[0]
    r_in = rr[dark[0]] if dark.size else 0.62 * rx           # Wulst: erster dunkler Radius von innen
    r_out = rx
    return img, dict(cx=cx / w, cy=cy / h, r_in=r_in / w, r_out=r_out / w, asp=ry / rx, w_over_h=w / h,
                     rot=c.tire_rotation, flip=c.tire_flip)


def build_car(context, s, c):
    if not s.image:
        raise RuntimeError("Zuerst im Bereich ‚Felge3D‘ ein Felgenbild laden (Schritt 1).")
    if context.object and context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    car.clear_old()
    col = bpy.data.collections.new(car.COLL_NAME)
    context.scene.collection.children.link(col)

    tire_img, tex = tire_texture_params(c)
    mats, imgs = car.build_materials(c, tire_img)

    axles = {}
    for front in (True, False):
        d = car.wheel_dims(c, front)
        rim = make_rim_meshes(context, s, dict(diameter=float(d["rim_in"]), width=d["rim_width_in"],
                                               et=d["et"] * 1000.0, use_et=True))
        half = d["rim_width_in"] * 0.0254 / 2.0
        back_fn = car.back_profile(rim["res"]["star_verts"], half)
        r_well = d["r_rim"] - (rim["p"].drop + rim["p"].wall) / 1000.0
        x_m = max(-d["b"] * 0.5, min(d["et"], d["rim_out"] - 0.045))
        axles[front] = (d, rim, half, back_fn, r_well, x_m)

    created = []
    for front in (True, False):
        d, rim, half, back_fn, r_well, x_m = axles[front]
        axle = "Vorne" if front else "Hinten"
        y = (-1 if front else 1) * c.wheelbase / 2000.0
        half_track = (c.front_track if front else c.rear_track) / 2000.0
        camber = math.radians(c.front_camber if front else c.rear_camber)
        for sgn, side in ((1, "links"), (-1, "rechts")):
            name = "%s %s" % (axle, side)
            parent = bpy.data.objects.new("Rad " + name, None)
            parent.empty_display_type = "PLAIN_AXES"
            parent.empty_display_size = 0.2
            parent.location = (sgn * half_track, y, d["R"])
            parent.rotation_euler = (0.0, sgn * camber, 0.0)     # negativer Sturz: oben nach innen
            col.objects.link(parent)
            parent["Achse"], parent["Seite"] = axle, side
            parent["Rad"] = "%sJ x %s ET%s" % (("%g" % d["j_in"]), ("%g" % d["rim_in"]), ("%g" % (d["et"] * 1000)))
            parent["Reifen"] = "%d/%d ZR%s" % (round(d["W"] * 1000), round(d["h"] / d["W"] * 100), ("%g" % d["rim_in"]))
            parent["Sturz Grad"] = math.degrees(camber)
            created.append(parent)

            m_rim = Matrix.Translation((sgn * half, 0, 0)) @ car.rim_matrix(sgn)
            for label, me in (("Felgenstern", rim["star_me"]), ("Felgenbett", rim["barrel_me"])):
                ob = bpy.data.objects.new("%s %s" % (label, name), me)
                ob.matrix_basis = m_rim
                ob.parent = parent
                col.objects.link(ob)

            me_t = car.build_tire(c, d, sgn, mats, imgs, "Reifen " + name, tex, r_well)
            ob = bpy.data.objects.new("Reifen " + name, me_t)
            ob.parent = parent
            col.objects.link(ob)
            # Bremsscheibe und Sattel: Code liegt in car.build_brake bereit, kommt später dazu
    for o in context.view_layer.objects:
        o.select_set(False)
    context.view_layer.objects.active = created[0]
    return col, ("4 Räder erzeugt: vorn %g×%gJ ET%g, hinten %g×%gJ ET%g%s" % (
        c.front_rim, c.front_rim_width, c.front_et, c.rear_rim, c.rear_rim_width, c.rear_et,
        " · Reifentextur gemappt" if tex else " · Reifentextur fehlt (textures/reifen.jpg)"))


class FELGE3D_OT_car_generate(Operator):
    """Aus dem Felgenbild ein Paket mit 4 Rädern (Felge, Reifen, Bremse) nach Radstand/Spurweite erzeugen"""
    bl_idname = "felge3d.car_generate"
    bl_label = "4 Räder erzeugen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            col, info = build_car(context, context.scene.felge3d, context.scene.felge3d_car)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, info)
        return {"FINISHED"}


class FELGE3D_OT_car_reset(Operator):
    """Alle Fahrzeugmaße auf die Werte des 911 GT3 RS (992) zurücksetzen"""
    bl_idname = "felge3d.car_reset"
    bl_label = "GT3-RS-Maße"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        c = context.scene.felge3d_car
        for k in c.bl_rna.properties.keys():
            if k != "rna_type":
                c.property_unset(k)
        return {"FINISHED"}


class FELGE3D_PT_car(Panel):
    bl_label = "Schritt 2: Fahrzeug-Paket"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"

    def draw(self, context):
        s = context.scene.felge3d
        c = context.scene.felge3d_car
        L = self.layout
        if not s.image:
            L.label(text="Erst oben ein Felgenbild laden", icon="INFO")
        col = L.column(align=True)
        col.scale_y = 1.5
        col.operator("felge3d.car_generate", icon="AUTO")
        box = L.box()
        box.label(text="Fahrzeug (GT3 RS)", icon="AUTO")
        col = box.column(align=True)
        col.prop(c, "wheelbase")
        col.prop(c, "front_track")
        col.prop(c, "rear_track")
        if not os.path.isfile(TIRE_TEXTURE):
            L.label(text="Reifentextur fehlt (textures/reifen.jpg)", icon="ERROR")
        L.operator("felge3d.car_reset", icon="LOOP_BACK")


class FELGE3D_PT_car_axle(Panel):
    bl_label = "Achsen: Felge und Reifen"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_car"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        c = context.scene.felge3d_car
        for title, pre in (("Vorderachse", "front_"), ("Hinterachse", "rear_")):
            box = self.layout.box()
            box.label(text=title)
            col = box.column(align=True)
            for prop in ("rim", "rim_width", "et", "width", "aspect", "camber"):
                col.prop(c, pre + prop)


class FELGE3D_PT_car_extra(Panel):
    bl_label = "Reifen: Profil, Textur, Decals"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Felge"
    bl_parent_id = "FELGE3D_PT_car"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        c = context.scene.felge3d_car
        L = self.layout
        row = L.row(align=True)
        row.prop(c, "tire_rotation")
        row.prop(c, "tire_flip", text="", icon="MOD_MIRROR")
        L.prop(c, "tread_grooves")
        for prop in ("decal_sidewall_top", "decal_sidewall_bottom", "decal_sidewall_scale", "decal_sidewall_arc"):
            L.prop(c, prop)



classes = (
    Felge3DPreferences,
    Felge3DSettings,
    Felge3DCar,
    FELGE3D_OT_car_generate,
    FELGE3D_OT_car_reset,
    FELGE3D_OT_check_update,
    FELGE3D_OT_install_ai,
    FELGE3D_OT_install_update,
    FELGE3D_OT_import_image,
    FELGE3D_OT_rebuild,
    FELGE3D_OT_reset_defaults,
    FELGE3D_OT_detect,
    FELGE3D_OT_preview,
    FELGE3D_OT_mask_to_image,
    FELGE3D_OT_export_obj,
    FELGE3D_PT_main,
    FELGE3D_PT_look,
    FELGE3D_PT_ai,
    FELGE3D_PT_dims,
    FELGE3D_PT_detect,
    FELGE3D_PT_advanced,
    FELGE3D_PT_update,
    FELGE3D_PT_car,
    FELGE3D_PT_car_axle,
    FELGE3D_PT_car_extra,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.felge3d = PointerProperty(type=Felge3DSettings)
    bpy.types.Scene.felge3d_car = PointerProperty(type=Felge3DCar)


def unregister():
    del bpy.types.Scene.felge3d_car
    del bpy.types.Scene.felge3d
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
