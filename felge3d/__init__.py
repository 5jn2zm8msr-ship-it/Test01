# SPDX-License-Identifier: GPL-3.0-or-later
"""
Felge3D – Blender-Add-on: Felgenfoto (Frontansicht) laden -> 3D-Felge in neuer Collection.

Bedienung: 3D-Viewport -> Seitenleiste (N) -> Reiter "Felge".
Läuft mit Blender 3.6 (Legacy-Add-on) und 4.2+ (Extension, siehe blender_manifest.toml).
"""

bl_info = {
    "name": "Rim Generator",
    "author": "Felge3D",
    "version": (0, 29, 2),
    "blender": (3, 5, 0),
    "location": "3D-Viewport > Seitenleiste (N) > 2D to 3D Rim / Package",
    "description": "Rim Generator: Felge aus Foto oder 3D-Datei -> 4 Räder mit Reifen und Bremsen",
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
    tire_data = importlib.reload(tire_data)
    brake_data = importlib.reload(brake_data)
    fbx = importlib.reload(fbx)
else:
    from . import ai, brake_data, car, core, fbx, tire_data, updater

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
    source: EnumProperty(name="Felge", default="GENERATED", items=[
        ("GENERATED", "Generierte Felge", "Die Felge aus dem Reiter ‚2D to 3D Rim‘ (Foto) verwenden"),
        ("COLLECTION", "Eigene Felge", "Eine beliebige Felge aus einer Collection der Szene wählen (z.B. importierte FBX)"),
    ])
    fbx_collection: PointerProperty(name="Collection", type=bpy.types.Collection,
                                    description="Collection mit der Felge (Meshes); Achse, Vorderseite und Größe werden erkannt")
    fbx_flip: BoolProperty(name="Felge umdrehen", default=False, update=lambda self, ctx: None,
                           description="Falls die Felge verkehrt herum sitzt (Vorderseite nach innen)")
    fbx_info: StringProperty(default="")
    use_fusion: BoolProperty(name="Erkennung per Fusion", default=True,
                             description="Mehrere Methoden (Helligkeit, Hintergrund, KI-Tiefe) je Speiche bewerten; die besten "
                                         "Segmente werden auf alle Speichen kopiert (behebt fehlende Speichen, Löcher, Negativ)")
    fusion_info: StringProperty(default="")
    warning: StringProperty(default="")
    check_text: StringProperty(default="")
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
    proc_size: IntProperty(name="Arbeitsauflösung", default=1536, min=256, max=3000,
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
    boss_height: FloatProperty(name="Versatz Mitte: Nabenbund (mm)", default=6.0, min=0, max=60,
                               update=_update_rebuild,
                               description="Erhabener Bund um den Zentralverschluss / die Nabe, als Versatz auf der Schnittkurve (0 = aus)")
    ring_step: FloatProperty(name="Versatz Außenring (mm)", default=0.0, min=-30, max=30,
                             update=_update_rebuild,
                             description="Stufe am Außenring gegenüber der Schnittkurve (+ = nach vorn, - = nach hinten). Die Kurve bleibt die Leitlinie")
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


def ai_depth(s, cx, cy, rx, ry, force=False):
    """KI-Tiefenkarte im Arbeitsbild – oder None, wenn KI aus/nicht installiert.
    force=True: auch wenn das KI-Relief aus ist (die Erkennung nutzt die Tiefe)."""
    if not ai.is_ready(s.ai_quality) or not (force or (s.ai_depth > 0 and s.use_ai)):
        return None
    key = (s.image.name, s.proc_size, s.ai_quality, round(cx, 1), round(cy, 1), round(rx, 1), round(ry, 1))
    if key not in _depth_cache:
        _depth_cache.clear()
        rgb = _rgb_cache[next(iter(_rgb_cache))]
        _depth_cache[key] = ai.depth_map(rgb, cx, cy, rx, ry, kind=s.ai_quality)
    return _depth_cache[key]


def symmetry_order(s, gray, cx, cy, rx, ry, depth=None):
    if s.sym_mode == "AUTO":
        n, _ = core.detect_symmetry_multi(gray, cx, cy, rx, ry, depth)
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


def compute_mask(s, gray, cx, cy, rx, ry, n=None, depth=None, hub_n=None):
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
            n = symmetry_order(s, gray, cx, cy, rx, ry, depth)
        rgb = _rgb_cache[next(iter(_rgb_cache))]
        mask, method, cand = core.segment_auto(rgb, cx, cy, rx, ry, n, s.clean, return_all=True)
        if s.use_fusion:
            if depth is not None:
                cand["D"] = core.depth_candidate(depth, cx, cy, rx, ry)
            if len(cand) >= 2:
                hn = hub_n if hub_n else n
                mask, rep = core.fuse_candidates(cand, cx, cy, rx, ry, n, hub_n=hn, split=0.33)
                z = rep["zones"].get("outer", {})
                best = z.get("best", [])
                method = "Fusion (" + "+".join(sorted(cand)) + ")"
                s["fusion_info"] = "Beste Segmente: " + ", ".join("%s%s" % (k, i) for k, i, _ in best) if best else ""
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


PROFILE_TREE = "Rim Generator | Schnittkurve"


def default_hub_x(s=None):
    """Ende der flachen Nabenanlage (Anteil von r_face) für die Standardkurve dieser Felge."""
    p = core.Params()
    if s is not None:
        for k in ("diameter", "wall", "flange", "hub_radius"):
            setattr(p, k, getattr(s, k))
    return float(core.hub_ratio(p))


def _set_default_profile(m, hub_x=None, q=2.0):
    """
    Standard-Schnittkurve, mathematisch exakt (core.default_depth): Nabe flach, dann 1 - u^q zum Rand.
    Sechs Punkte auf der exakten Funktion; der mittlere Punkt (u = 0,5) ist der „Schwerpunkt“-Handle.
    """
    if hub_x is None:
        hub_x = default_hub_x(None)
    m.use_clip = True
    m.clip_min_x, m.clip_max_x, m.clip_min_y, m.clip_max_y = 0.0, 1.0, 0.0, 1.0
    cur = m.curves[0]
    while len(cur.points) > 2:
        cur.points.remove(cur.points[-1])
    xs = [0.0, hub_x] + [hub_x + u * (1.0 - hub_x) for u in (0.25, 0.5, 0.75)] + [1.0]
    ys = [float(v) for v in core.default_depth(xs, hub_x, q)]
    cur.points[0].location = (xs[0], ys[0])
    cur.points[1].location = (xs[-1], ys[-1])
    for x, y in zip(xs[1:-1], ys[1:-1]):
        cur.points.new(x, y)
    for pt in cur.points:
        pt.handle_type = "AUTO"
        pt.select = False
    m.update()


def profile_node():
    """Knoten mit der editierbaren Schnittkurve (liegt in der .blend-Datei). Wird bei Bedarf angelegt."""
    ng = bpy.data.node_groups.get(PROFILE_TREE)
    if ng is None or "Kurve" not in ng.nodes:
        ng = bpy.data.node_groups.new(PROFILE_TREE, "ShaderNodeTree")
        ng.use_fake_user = True
        node = ng.nodes.new("ShaderNodeRGBCurve")
        node.name = "Kurve"
        _set_default_profile(node.mapping)
    return ng.nodes["Kurve"]


def profile_samples(n=65):
    """Tiefenanteil (0..1) der Schnittkurve bei r/r_face = 0..1."""
    m = profile_node().mapping
    m.update()
    cur = m.curves[0]
    return np.clip(np.array([m.evaluate(cur, i / (n - 1.0)) for i in range(n)], np.float32), 0.0, 1.0)


def make_params(s):
    p = core.Params()
    try:
        p.profile = profile_samples()
    except Exception:  # noqa: BLE001 – Kurve nicht verfügbar: Standardform
        p.profile = None
    for k in ("diameter", "width", "use_et", "et", "face_inset", "dish", "dish_power",
              "spoke_thickness", "hub_thickness", "hub_radius", "relief", "relief_width", "boss_height", "boss_radius", "ring_step", "min_hole", "bore", "ai_strength", "ai_depth", "relief_fade", "tone_step", "edge_round", "min_thick", "flange", "wall", "drop", "res_radial", "res_angular", "sections"):
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
    depth_pre = ai_depth(s, cx, cy, rx, ry, force=True) if s.use_fusion else None   # Tiefe hilft der Erkennung
    n = symmetry_order(s, gray, cx, cy, rx, ry, depth_pre)
    hub_n0 = hub_symmetry(s, gray, cx, cy, rx, ry, n)
    mask, thr = compute_mask(s, gray, cx, cy, rx, ry, n, depth_pre, hub_n0)
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
    depth = ai_depth(s, cx, cy, rx, ry)          # nur für das optionale KI-Relief
    hub_n = hub_n0
    res = core.build(mask, cx, cy, rx, ry, p, symmetry_n=n, depth=depth, hub_n=hub_n, gray=gray)
    s["tone_info"] = res.get("tone_info", "")
    chk = res.get("selfcheck") or {}
    s["check_text"] = "\n".join(chk.get("lines", []))
    if chk.get("warn"):
        s["warning"] = (s.get("warning", "") + ("; " if s.get("warning") else "") + "; ".join(chk["warn"]))
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
        try:                                    # neue Felge = neue, mathematisch exakte Standardkurve
            _set_default_profile(profile_node().mapping, default_hub_x(s))
        except Exception:  # noqa: BLE001
            pass
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
                  "relief", "edge_round", "boss_height", "boss_radius", "ring_step", "dish_power", "face_inset"):
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
            dp = ai_depth(s, cx, cy, rx, ry, force=True) if s.use_fusion else None
            nn = symmetry_order(s, gray, cx, cy, rx, ry, dp)
            mask, _ = compute_mask(s, gray, cx, cy, rx, ry, nn, dp, hub_symmetry(s, gray, cx, cy, rx, ry, nn))
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
    bl_label = "2D to 3D Rim"
    bl_idname = "FELGE3D_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        col = L.column(align=True)
        col.scale_y = 1.5
        col.operator("felge3d.import_image", icon="FILE_IMAGE")
        if s.image:
            L.label(text=s.image.name, icon="IMAGE_DATA")
        if s.warning:
            L.label(text="Erkennung unsicher – siehe ‚Erkennung & Prüfung‘", icon="ERROR")


class FELGE3D_PT_section(Panel):
    bl_label = "Schnitt: Tiefe und Bombierung"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_main"

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        L.label(text="X: Radius (links Mitte → rechts Rand), Y: Tiefe (oben = Nabenanlage)")
        L.label(text="Mittlerer Punkt = Schwerpunkt; Knick: Punkt anklicken → Knick")
        try:
            L.template_curve_mapping(profile_node(), "mapping", type="NONE")
        except Exception as e:  # noqa: BLE001
            L.label(text="Kurve nicht verfügbar: %s" % e, icon="ERROR")
        try:
            n_pts = len(profile_node().mapping.curves[0].points)
        except Exception:  # noqa: BLE001
            n_pts = 0
        row = L.row(align=True)
        row.operator("felge3d.curve_add", icon="ADD")
        row.operator("felge3d.curve_remove", icon="REMOVE")
        row.label(text="%d Punkte" % n_pts)
        row = L.row(align=True)
        op = row.operator("felge3d.curve_handle", text="Weich", icon="SMOOTHCURVE")
        op.kind = "AUTO"
        op = row.operator("felge3d.curve_handle", text="Knick", icon="SHARPCURVE")
        op.kind = "VECTOR"
        a = analysis_for(s)
        L.label(text="Tiefe in der Mitte: %.0f mm (%s)" % (abs(a["dish_mm"]), a["verdict"].capitalize()))
        col = L.column(align=True)
        col.scale_y = 1.4
        col.enabled = bool(s.image)
        col.operator("felge3d.refresh_profile", icon="FILE_REFRESH")
        L.operator("felge3d.reset_profile", icon="LOOP_BACK")


class FELGE3D_PT_shape(Panel):
    bl_label = "Felge: Maße & Form"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        col = L.column(align=True)
        col.prop(s, "diameter", slider=True)
        col.prop(s, "width")
        col.prop(s, "use_et")
        if s.use_et:
            col.prop(s, "et")
        else:
            col.prop(s, "dish", slider=True)
        L.prop(s, "tire_mode")
        a = analysis_for(s)
        L.label(text="Form: " + a["verdict"].capitalize() + " (%+.0f mm)" % a["dish_mm"])
        if a["warn"]:
            L.label(text=a["warn"], icon="ERROR")


class FELGE3D_PT_check(Panel):
    bl_label = "Erkennung & Prüfung"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        L = self.layout
        if s.warning:
            L.label(text="Erkennung unsicher:", icon="ERROR")
            L.label(text=s.warning)
            L.label(text="→ ‚Maske anzeigen‘ in ‚Erkennung‘")
        if s.collection:
            info = "%d Speichen" % s.detected_n if s.detected_n > 1 else "keine Symmetrie"
            L.label(text="Erkannt: " + info + (" · " + s.method_used if s.method_used else ""), icon="INFO")
        for ln in (s.check_text or "").split("\n"):
            if ln:
                L.label(text=ln)
        if not (s.warning or s.collection or s.check_text):
            L.label(text="Noch kein Felgenbild geladen.")


class FELGE3D_PT_look(Panel):
    bl_label = "Aussehen"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
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
        c.prop(s, "ring_step")
        L.operator("felge3d.reset_defaults", icon="LOOP_BACK")


class FELGE3D_PT_ai(Panel):
    bl_label = "KI-Relief (optional)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
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
    bl_label = "Form & Details"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
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
    bl_label = "Erkennung (Feinabstimmung)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
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
        L.prop(s, "use_fusion")
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
    """Eigenes Top-Level-Panel, immer sichtbar und unabhängig vom Hauptpanel (Update-Knopf darf nie fehlen)."""
    bl_label = "Update"
    bl_idname = "FELGE3D_PT_update"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"

    def draw(self, context):
        L = self.layout
        row = L.row(align=True)
        row.label(text="Version %d.%d.%d" % bl_info["version"], icon="INFO")
        row.operator("felge3d.check_update", text="Nach Update suchen", icon="URL")
        r = _update_state["remote"]
        if r and r > tuple(bl_info["version"]):
            col = L.column()
            col.scale_y = 1.3
            col.operator("felge3d.install_update", icon="IMPORT", text="Update %d.%d.%d installieren" % r)
        if _update_state["msg"]:
            L.label(text=_update_state["msg"])
        try:
            repo = get_prefs(context).repo
            L.label(text="Quelle: " + (repo or "nicht eingestellt"), icon="URL")
        except Exception:  # noqa: BLE001
            pass


class FELGE3D_PT_advanced(Panel):
    bl_label = "Erweitert"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
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
        self.layout.operator("felge3d.export_obj", icon="EXPORT")


# ============================================================ Schritt 2: Fahrzeug-Paket (4 Räder)
class Felge3DCar(PropertyGroup):
    """Maße vom Porsche 911 GT3 RS (992), Datenblatt MY P 08/2022 – alle Werte änderbar."""
    wheelbase: FloatProperty(name="Radstand (mm)", default=2457, min=1500, max=4000)
    front_track: FloatProperty(name="Spurweite vorn (mm)", default=1630, min=1200, max=2200)
    rear_track: FloatProperty(name="Spurweite hinten (mm)", default=1582, min=1200, max=2200)
    front_rim: IntProperty(name="Zoll vorn", default=20, min=16, max=24, description="Felgengröße vorn in Zoll")
    rear_rim: IntProperty(name="Zoll hinten", default=21, min=16, max=24, description="Felgengröße hinten in Zoll")
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
    tire_text_shift: FloatProperty(name="Beschriftung: Lage", default=0.0, min=-0.2, max=0.2,
                                   description="Verschiebt die Reifen-Beschriftung auf der Flanke: negativ = näher an die Felge, positiv = zum Reifenrand")
    tire_relief: FloatProperty(name="Schrift-Relief (mm)", default=1.2, min=0, max=4,
                               description="Wie weit die Beschriftung der Reifenflanke hervorsteht (Displacement). 0 = nur Bump")
    tread_relief: FloatProperty(name="Profil-Relief (mm)", default=2.5, min=0, max=6,
                                description="Tiefe des Laufflächenprofils (Displacement). 0 = nur Bump")
    tread_grooves: IntProperty(name="Zusätzliche Längsrillen", default=0, min=0, max=4,
                               description="Zusätzlich zum Profil aus dem Foto (Standard 0: Profil kommt aus der Textur)")
    decal_sidewall_top: StringProperty(name="Flanke oben (PNG)", subtype="FILE_PATH", default="")
    decal_sidewall_bottom: StringProperty(name="Flanke unten (PNG)", subtype="FILE_PATH", default="")
    decal_sidewall_scale: FloatProperty(name="Flanken-Decal Höhe", default=1.0, min=.2, max=1.2)
    decal_sidewall_arc: FloatProperty(name="Flanken-Decal max. Bogen (Grad)", default=110, min=10, max=170)

    caliper_angle: FloatProperty(name="Sattelposition (Grad)", default=45, min=-180, max=180,
                                 description="Sattel um die Achse gedreht: 0 = oben, 90 = Richtung Heck, -90 = Richtung Front")
    decal_caliper: StringProperty(name="Sattel (PNG)", subtype="FILE_PATH", default="")
    use_brakes: BoolProperty(name="Bremsen mit Sattel", default=True,
                             description="Bremsscheibe, Topf und Sattel (Mesh mit Foto-Textur) mit erzeugen")


def brake_textures():
    """Bremsenfoto (links/rechts) aus dem Code auspacken; gibt ((Bild links, Bild rechts), meta) zurück."""
    left = _unpack_image(brake_data.FRONT_B64, "bremse_links_v1.jpg")
    right = _unpack_image(brake_data.MIRROR_B64, "bremse_rechts_v1.jpg")
    return (left, right), dict(brake_data.META)


def tire_texture_file():
    """Eingebettete Reifentextur als JPG in den Add-on-Datenordner auspacken (einmalig)."""
    import base64
    path = os.path.join(ai.data_dir(), "reifen_michelin_pilot_sport_cup2.jpg")
    data = base64.b64decode("".join(tire_data.JPG_B64))
    if not (os.path.isfile(path) and os.path.getsize(path) == len(data)):
        with open(path, "wb") as f:
            f.write(data)
    return path


def _unpack_image(b64parts, filename, noncolor=False):
    import base64
    path = os.path.join(ai.data_dir(), filename)
    data = base64.b64decode("".join(b64parts))
    if not (os.path.isfile(path) and os.path.getsize(path) == len(data)):
        with open(path, "wb") as f:
            f.write(data)
    img = bpy.data.images.load(path, check_existing=True)
    if noncolor:
        try:
            img.colorspace_settings.name = "Non-Color"
        except TypeError:
            pass
    return img


def tread_texture():
    """Laufflächen-Kachel (Farbe, tiefschwarz) und Höhenkarte aus dem Code auspacken; gibt (Farbe, Höhe, meta) zurück."""
    col = _unpack_image(tire_data.TREAD_B64, "reifenprofil_farbe_v2.jpg")
    hgt = _unpack_image(tire_data.TREAD_H_B64, "reifenprofil_hoehe_v2.jpg", noncolor=True)
    return col, hgt, dict(tire_data.TREAD_META)


def tire_texture_params(c):
    """
    Feste Reifentextur (Michelin Pilot Sport Cup 2, im Code eingebettet). Mittelpunkt und Radien der
    Flanke sind vorgemessen (tire_data.META). Gibt (Bild, tex-dict) zurück.
    """
    j = tire_data.META
    img = bpy.data.images.load(tire_texture_file(), check_existing=True)
    W, H = j["width"], j["height"]
    o = j["outer"]
    R = o["a"] / W
    sh = c.tire_text_shift
    return img, dict(cx=o["cx"] / W, cy=1.0 - o["cy"] / H,          # Blender-UV: y von unten
                     r_in=R * (j.get("map_inner_ratio", 0.76) - sh), r_out=R * (j.get("map_outer_ratio", 1.05) - sh),
                     asp=o["b"] / o["a"], w_over_h=W / H, rot=c.tire_rotation, flip=c.tire_flip)


def _fbx_meshes(s):
    col = s.fbx_collection
    if not col or col.name not in bpy.data.collections:
        return []
    return [o for o in col.all_objects if o.type == "MESH" and len(o.data.vertices) > 0]


def build_car(context, s, c):
    use_fbx = s.source == "COLLECTION"
    if use_fbx:
        src_meshes = _fbx_meshes(s)
        if not src_meshes:
            raise RuntimeError("Eine Collection mit der Felge wählen (Picker) oder ‚3D-Felge importieren‘.")
    elif not s.image:
        raise RuntimeError("Im Reiter ‚2D to 3D Rim‘ zuerst ein Felgenbild laden – oder unter ‚Felge‘ eine eigene Collection wählen.")
    if context.object and context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass
    car.clear_old()
    col = bpy.data.collections.new(car.COLL_NAME)
    context.scene.collection.children.link(col)

    tire_img, tex = tire_texture_params(c)
    tread_img, tread_h, tread = tread_texture()
    bimgs, bmeta = brake_textures()
    mats, imgs = car.build_materials(c, tire_img, tread_img, tread_h, bimgs, bmeta["cal_color"])
    finfo = fbx.analyze(src_meshes, s.fbx_flip) if use_fbx else None

    axles = {}
    for front in (True, False):
        d = car.wheel_dims(c, front)
        x_m = max(-d["b"] * 0.5, min(d["et"], d["rim_out"] - 0.045))
        r_well = d["r_rim"] - 0.027
        if use_fbx:
            M_fit, scale = fbx.fit_matrix(finfo, d["r_rim"] + 0.017, d["rim_out"])
            parts = fbx.bake(src_meshes, M_fit, "FBX " + ("vorn" if front else "hinten"))
            back_fn = fbx.back_profile(parts, d["rim_out"], finfo["width"] * scale)
            base = lambda sgn: Matrix.Rotation(math.pi, 4, "Z") if sgn < 0 else Matrix.Identity(4)
            rim_parts = [(label, me) for label, me in parts]
        else:
            rim = make_rim_meshes(context, s, dict(diameter=float(d["rim_in"]), width=d["rim_width_in"],
                                                   et=d["et"] * 1000.0, use_et=True))
            half = d["rim_width_in"] * 0.0254 / 2.0
            back_fn = car.back_profile(rim["res"]["star_verts"], half)
            r_well = d["r_rim"] - (rim["p"].drop + rim["p"].wall) / 1000.0
            base = lambda sgn, half=half: Matrix.Translation((sgn * half, 0, 0)) @ car.rim_matrix(sgn)
            rim_parts = [("Felgenstern", rim["star_me"]), ("Felgenbett", rim["barrel_me"])]
        axles[front] = (d, rim_parts, base, back_fn, r_well, x_m)

    created = []
    for front in (True, False):
        d, rim_parts, base, back_fn, r_well, x_m = axles[front]
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

            m_rim = base(sgn)
            for label, me in rim_parts:
                ob = bpy.data.objects.new("%s %s" % (label, name), me)
                ob.matrix_basis = m_rim
                ob.parent = parent
                col.objects.link(ob)

            me_t = car.build_tire(c, d, sgn, mats, imgs, "Reifen " + name, tex, r_well, tread)
            ob = bpy.data.objects.new("Reifen " + name, me_t)
            ob.parent = parent
            col.objects.link(ob)
            car.add_relief(ob, tire_img, c.tire_relief, tread_h, c.tread_relief)
            if c.use_brakes:
                me_d, me_c, x_d = car.build_brake(c, d, sgn, mats, name, x_m, back_fn, r_well, bmeta)
                for label, me in (("Bremsscheibe", me_d), ("Bremssattel", me_c)):
                    bo = bpy.data.objects.new("%s %s" % (label, name), me)
                    bo.parent = parent
                    col.objects.link(bo)
                    if label == "Bremssattel":
                        mod = bo.modifiers.new("Kantenfasen", "BEVEL")
                        mod.width, mod.segments = 0.0035, 3
                        mod.limit_method, mod.angle_limit = "ANGLE", math.radians(50)
    for o in context.view_layer.objects:
        o.select_set(False)
    context.view_layer.objects.active = created[0]
    return col, ("4 Räder erzeugt (%s): vorn %g\"/%gJ ET%g, hinten %g\"/%gJ ET%g" % (
        "3D-Felge" if use_fbx else "Foto", c.front_rim, c.front_rim_width, c.front_et, c.rear_rim, c.rear_rim_width, c.rear_et))


class FELGE3D_OT_refresh_profile(Operator):
    """Felge mit der geänderten Schnittkurve neu aufbauen"""
    bl_idname = "felge3d.refresh_profile"
    bl_label = "Refresh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.felge3d
        if not s.image:
            self.report({"ERROR"}, "Erst ein Felgenbild laden.")
            return {"CANCELLED"}
        try:
            col, info = build_wheel(context, s, new_collection=not (s.collection and s.collection.name in bpy.data.collections))
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, "Felge mit neuer Schnittkurve aktualisiert.")
        return {"FINISHED"}


class FELGE3D_OT_reset_profile(Operator):
    """Schnittkurve auf die Standardform zurücksetzen"""
    bl_idname = "felge3d.reset_profile"
    bl_label = "Kurve zurücksetzen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _set_default_profile(profile_node().mapping, default_hub_x(context.scene.felge3d))
        return {"FINISHED"}


def _profile_curve():
    m = profile_node().mapping
    return m, m.curves[0]


class FELGE3D_OT_curve_add(Operator):
    """Zusätzlichen Punkt (Handle) in die Schnittkurve setzen: in der größten Lücke, auf der aktuellen Kurve"""
    bl_idname = "felge3d.curve_add"
    bl_label = "+ Punkt"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        m, cur = _profile_curve()
        xs = sorted(p.location[0] for p in cur.points)
        if len(cur.points) >= 16:
            self.report({"WARNING"}, "Maximal 16 Punkte.")
            return {"CANCELLED"}
        gap = max(range(len(xs) - 1), key=lambda i: xs[i + 1] - xs[i])
        x = 0.5 * (xs[gap] + xs[gap + 1])
        y = float(m.evaluate(cur, x))
        for pt in cur.points:
            pt.select = False
        new = cur.points.new(x, y)
        new.handle_type = "AUTO"
        new.select = True
        m.update()
        return {"FINISHED"}


class FELGE3D_OT_curve_remove(Operator):
    """Ausgewählten Punkt der Schnittkurve entfernen (ohne Auswahl: der innere Punkt mit dem kleinsten Einfluss)"""
    bl_idname = "felge3d.curve_remove"
    bl_label = "− Punkt"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        m, cur = _profile_curve()
        if len(cur.points) <= 2:
            self.report({"WARNING"}, "Mindestens 2 Punkte (Anfang und Ende).")
            return {"CANCELLED"}
        pts = sorted(cur.points, key=lambda p: p.location[0])
        inner = pts[1:-1]
        sel = [p for p in inner if p.select]
        if sel:
            target = sel[0]
        elif inner:
            # den Punkt wählen, dessen Entfernen die Kurve am wenigsten ändert (Abstand zur Linie der Nachbarn)
            def dev(i):
                a, b, c = pts[i - 1].location, pts[i].location, pts[i + 1].location
                t = (b[0] - a[0]) / max(1e-9, c[0] - a[0])
                return abs(b[1] - (a[1] + t * (c[1] - a[1])))
            target = pts[min(range(1, len(pts) - 1), key=dev)]
        else:
            self.report({"WARNING"}, "Nur noch Anfang und Ende.")
            return {"CANCELLED"}
        cur.points.remove(target)
        m.update()
        return {"FINISHED"}


class FELGE3D_OT_curve_handle(Operator):
    """Ausgewählte Punkte: weicher Verlauf (Auto) oder scharfer Knick (Vektor)"""
    bl_idname = "felge3d.curve_handle"
    bl_label = "Handle-Typ"
    bl_options = {"REGISTER", "UNDO"}
    kind: EnumProperty(items=[("AUTO", "Weich", ""), ("VECTOR", "Knick", "")], default="AUTO")

    def execute(self, context):
        m, cur = _profile_curve()
        n = 0
        for pt in cur.points:
            if pt.select:
                pt.handle_type = self.kind
                n += 1
        if not n:
            self.report({"INFO"}, "Erst einen Punkt in der Kurve anklicken.")
        m.update()
        return {"FINISHED"}


class FELGE3D_OT_import_fbx(Operator, ImportHelper):
    """3D-Felge (FBX, OBJ oder glTF) laden: Achse, Vorderseite und Größe werden automatisch erkannt"""
    bl_idname = "felge3d.import_fbx"
    bl_label = "3D-Datei importieren…"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: StringProperty(default="*.fbx;*.obj;*.glb;*.gltf", options={"HIDDEN"})

    def execute(self, context):
        s = context.scene.felge3d
        try:
            new, meshes = fbx.import_file(self.filepath)
        except Exception as e:  # noqa: BLE001
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        old = s.fbx_collection
        if old and old.name in bpy.data.collections:
            for o in list(old.all_objects):
                bpy.data.objects.remove(o)
            bpy.data.collections.remove(old)
        col = bpy.data.collections.new("Rim Generator | 3D-Felge (Quelle)")
        context.scene.collection.children.link(col)
        for o in new:
            for oc in list(o.users_collection):
                oc.objects.unlink(o)
            col.objects.link(o)
        col.hide_viewport = True                      # Quelle ausblenden, die Räder entstehen separat
        s.fbx_collection = col
        s.source = "COLLECTION"
        info = fbx.analyze(meshes, s.fbx_flip)
        warn = " · Richtung unsicher: bei Bedarf ‚Umdrehen‘" if info["confidence"] < 0.06 else ""
        s["fbx_info"] = "%d Teile · Breite/Ø = %.2f · Außen erkannt (Nabe %+.0f %% der Breite außerhalb der Bettmitte)%s" % (
            len(meshes), info["width"] / (2.0 * info["r_max"]), 100.0 * info["dish"] / max(info["width"], 1e-9), warn)
        self.report({"INFO"}, "3D-Felge geladen: " + s.fbx_info)
        return {"FINISHED"}


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
        self.report({"WARNING"} if "fehlt" in info else {"INFO"}, info)
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


class FELGE3D_PT_car_axle(Panel):
    bl_label = "Achsen: Felge und Reifen"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Package"
    bl_parent_id = "FELGE3D_PT_pkg"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        c = context.scene.felge3d_car
        for title, pre in (("Vorderachse", "front_"), ("Hinterachse", "rear_")):
            box = self.layout.box()
            box.label(text=title)
            col = box.column(align=True)
            for prop in ("rim", "rim_width", "et", "width", "aspect", "camber", "disc", "disc_thickness"):
                col.prop(c, pre + prop)
        self.layout.prop(c, "use_brakes")
        self.layout.operator("felge3d.car_reset", icon="LOOP_BACK")


class FELGE3D_PT_car_extra(Panel):
    bl_label = "Reifen: Profil, Textur, Decals"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Package"
    bl_parent_id = "FELGE3D_PT_pkg"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        c = context.scene.felge3d_car
        L = self.layout
        row = L.row(align=True)
        row.prop(c, "tire_rotation")
        row.prop(c, "tire_flip", text="", icon="MOD_MIRROR")
        L.prop(c, "tire_text_shift")
        L.prop(c, "tire_relief")
        L.prop(c, "tread_relief")
        L.prop(c, "tread_grooves")
        for prop in ("decal_sidewall_top", "decal_sidewall_bottom", "decal_sidewall_scale", "decal_sidewall_arc"):
            L.prop(c, prop)



class FELGE3D_PT_pkg(Panel):
    bl_label = "Package"
    bl_idname = "FELGE3D_PT_pkg"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Package"

    def draw(self, context):
        s = context.scene.felge3d
        c = context.scene.felge3d_car
        L = self.layout
        box = L.box()
        box.label(text="Felge", icon="MESH_TORUS")
        box.prop(s, "source", expand=True)
        if s.source == "COLLECTION":
            box.prop(s, "fbx_collection", text="")
            box.operator("felge3d.import_fbx", icon="IMPORT")
            if s.fbx_info and s.fbx_collection:
                box.label(text=s.fbx_info, icon="INFO")
            ready = bool(_fbx_meshes(s))
        else:
            box.label(text=(s.image.name if s.image else "Noch kein Felgenbild (Reiter ‚2D to 3D Rim‘)"),
                      icon="IMAGE_DATA")
            ready = bool(s.image)
        row = L.row()
        row.scale_y = 1.7
        row.enabled = ready
        row.operator("felge3d.car_generate", icon="AUTO")
        col = L.column(align=True)
        col.prop(c, "wheelbase")
        col.prop(c, "front_track")
        col.prop(c, "rear_track")
        col = L.column(align=True)
        col.prop(c, "front_rim", slider=True)
        col.prop(c, "rear_rim", slider=True)


class FELGE3D_PT_pkg_opts(Panel):
    bl_label = "Optionen"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Package"
    bl_parent_id = "FELGE3D_PT_pkg"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.felge3d
        c = context.scene.felge3d_car
        L = self.layout
        L.prop(c, "use_brakes")
        if c.use_brakes:
            L.prop(c, "caliper_angle", slider=True)
        if s.source == "COLLECTION":
            L.prop(s, "fbx_flip")


class FELGE3D_PT_update_pkg(Panel):
    bl_label = "Update"
    bl_idname = "FELGE3D_PT_update_pkg"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Package"

    def draw(self, context):
        FELGE3D_PT_update.draw(self, context)


classes = (
    Felge3DPreferences,
    Felge3DSettings,
    Felge3DCar,
    FELGE3D_OT_car_generate,
    FELGE3D_OT_import_fbx,
    FELGE3D_OT_refresh_profile,
    FELGE3D_OT_reset_profile,
    FELGE3D_OT_curve_add,
    FELGE3D_OT_curve_remove,
    FELGE3D_OT_curve_handle,
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
    # Reiter 1: 2D to 3D Rim
    FELGE3D_PT_main,
    FELGE3D_PT_section,
    FELGE3D_PT_shape,
    FELGE3D_PT_check,
    FELGE3D_PT_look,
    FELGE3D_PT_ai,
    FELGE3D_PT_dims,
    FELGE3D_PT_detect,
    FELGE3D_PT_advanced,
    FELGE3D_PT_update,
    # Reiter 2: Package
    FELGE3D_PT_pkg,
    FELGE3D_PT_pkg_opts,
    FELGE3D_PT_car_axle,
    FELGE3D_PT_car_extra,
    FELGE3D_PT_update_pkg,
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
