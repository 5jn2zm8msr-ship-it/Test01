# SPDX-License-Identifier: GPL-3.0-or-later
"""Oberfläche und Collection-Verwaltung für die parametrische Felge (Geometry Nodes, ab Blender 5.3)."""
import bpy
from bpy.types import Operator, Panel

from . import paramrim

PARAM_OK = bpy.app.version >= (5, 3, 0)
MOD_NAME = "Parametrische Felge"
ROLE_PARAM = "param"
AI_ROLES = ("star", "barrel", "body")


# ---------------------------------------------------------------- Collections
def next_rim_name():
    i = 1
    while True:
        name = "Felge_%02d" % i
        if name not in bpy.data.collections:
            return name
        i += 1


def rim_collections():
    return sorted((c for c in bpy.data.collections if c.get("felge3d_rim")), key=lambda c: c.name)


def param_object_of(col):
    if col is None or col.name not in bpy.data.collections:
        return None
    for ob in col.objects:
        if ob.get("felge3d_role") == ROLE_PARAM and ob.type == "MESH":
            return ob
    return None


def param_modifier(ob):
    if ob is None:
        return None
    return next((m for m in ob.modifiers if m.type == "NODES" and m.node_group is not None
                 and paramrim.CURVE_SECTION in m.node_group.nodes), None)


def hide_ai(col):
    """KI-Mesh bleibt erhalten, ist aber ausgeblendet (Viewport und Render)."""
    for ob in col.objects:
        if ob.get("felge3d_role") in AI_ROLES:
            try:
                ob.hide_set(True)
            except RuntimeError:
                pass
            ob.hide_render = True


def apply_detected(md, det, section_pts=None):
    """Erkannte Werte (paramdetect.detect) und die Tiefenkurve des KI-Meshes auf die parametrische Felge übertragen."""
    if det:
        for k, v in (("Speichen", det["n"]), ("Drehung (Grad)", det["drehung_deg"]), ("Biegung (Grad)", det["biegung_deg"]),
                     ("Speichenbreite (mm)", det["breite_mm"]), ("Nabenradius (mm)", min(max(det["hub_r_mm"], 40.0), 130.0))):
            try:
                paramrim.set_param(md, k, v)
            except (KeyError, TypeError, ValueError):
                pass
        paramrim.set_curve_points(paramrim.curve_node(md, paramrim.CURVE_WIDTH).mapping, det["width_pts"])
        paramrim.set_curve_points(paramrim.curve_node(md, paramrim.CURVE_SWEEP).mapping, det["sweep_pts"])
    if section_pts:
        paramrim.set_curve_points(paramrim.curve_node(md).mapping, section_pts)
    md.node_group.update_tag()


def ensure_param(context, s, col, root, defaults, detected=None, section_pts=None):
    """Parametrische Felge in der Collection anlegen (vorhandene bleibt mit den Werten des Nutzers erhalten)."""
    ob = param_object_of(col)
    if ob is None:
        d = dict(defaults)
        hub_x = d.pop("hub_x", 0.34)
        ob, md = paramrim.make_object("%s parametrisch" % col.name, col, None, hub_x=hub_x)
        ob["felge3d_role"] = ROLE_PARAM
        if root is not None:
            ob.parent = root
        for k, v in d.items():
            try:
                paramrim.set_param(md, k, v)
            except (KeyError, TypeError, ValueError):
                pass
        apply_detected(md, detected, section_pts)
    hide_ai(col)
    return ob


_ITEMS = [("NONE", "(keine)", "")]


def rim_items(self, context):
    global _ITEMS                                     # Referenz halten (Blender liest die Strings später)
    _ITEMS = [(c.name, c.name, "Felge umschalten") for c in rim_collections()] or [("NONE", "(keine)", "")]
    return _ITEMS


def switch_rim(context, s, name):
    """Nur die gewählte Felgen-Collection sichtbar; Bild und aktive Collection für Aktualisieren setzen."""
    target = bpy.data.collections.get(name)
    if target is None:
        return
    for c in rim_collections():
        c.hide_viewport = c is not target
        c.hide_render = c is not target
    s.collection = target
    img = bpy.data.images.get(target.get("felge3d_image", ""))
    if img is not None:
        s.image = img


def rim_switched(self, context):
    if self.active_rim not in ("", "NONE"):
        switch_rim(context, self, self.active_rim)


def param_rim_mesh(context, src_ob, diameter_in, width_in, dish_mm, name):
    """
    Mesh der parametrischen Felge in anderer Größe (für die vier Räder): Node-Baum kopieren, Zoll/Breite/Tiefe setzen,
    auswerten (inkl. Bevel/Weighted Normal) und als normales Mesh zurückgeben. Die Felge des Nutzers bleibt unverändert.
    """
    src_md = param_modifier(src_ob)
    ng = src_md.node_group.copy()
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    context.scene.collection.objects.link(ob)
    try:
        md = ob.modifiers.new("GN", "NODES")
        md.node_group = ng
        paramrim.add_finish_modifiers(ob)
        for nm in paramrim.socket_ids(src_md.node_group):
            paramrim.set_param(md, nm, paramrim.get_param(src_md, nm))
        paramrim.set_param(md, "Durchmesser (Zoll)", float(diameter_in))
        paramrim.set_param(md, "Breite J (Zoll)", float(width_in))
        paramrim.set_param(md, "Schüsseltiefe (mm)", float(dish_mm))
        context.view_layer.update()
        dg = context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
        me.name = name
    finally:
        context.scene.collection.objects.unlink(ob)
        old = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(old)
        bpy.data.node_groups.remove(ng)
    return me


def back_profile_of(me, half_width, r_inner):
    """Rückseite des Sterns: kleinste axiale Lage x je Radius (Felgenmitte = 0), ohne das Felgenbett (r >= r_inner)."""
    import numpy as np
    n = len(me.vertices)
    co = np.empty(n * 3, np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    r = np.hypot(co[:, 0], co[:, 1])
    keep = r < r_inner
    r, x = r[keep], co[keep, 2] + half_width
    bins = np.arange(0.0, r.max() + 0.003, 0.003)
    idx = np.digitize(r, bins)
    rs, xs = [], []
    for i in np.unique(idx):
        m = idx == i
        rs.append(r[m].mean())
        xs.append(x[m].min())
    o = np.argsort(rs)
    rs, xs = np.array(rs)[o], np.array(xs)[o]

    def f(rr):
        return float(np.interp(rr, rs, xs))
    f.rear_min = float(xs.min())
    return f


# ---------------------------------------------------------------- Operatoren
def _current(context):
    s = context.scene.felge3d
    ob = param_object_of(s.collection)
    return s, ob, param_modifier(ob)


class FELGE3D_OT_param_build(Operator):
    """Parametrische Felge (Geometry Nodes) mit Standardwerten in der aktuellen Collection erzeugen"""
    bl_idname = "felge3d.param_build"
    bl_label = "Parametrische Felge erzeugen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from . import build_param_defaults
        s = context.scene.felge3d
        col = s.collection
        if col is None or col.name not in bpy.data.collections:
            col = bpy.data.collections.new(next_rim_name())
            col["felge3d_rim"] = True
            context.scene.collection.children.link(col)
            s.collection = col
        old = param_object_of(col)
        if old is not None:
            me = old.data
            bpy.data.objects.remove(old)
            if me and me.users == 0:
                bpy.data.meshes.remove(me)
        root = next((o for o in col.objects if o.get("felge3d_role") == "root"), None)
        ensure_param(context, s, col, root, build_param_defaults(s))
        s.active_rim = col.name
        return {"FINISHED"}


class FELGE3D_OT_param_refresh(Operator):
    """Felge neu berechnen (falls die Anzeige einmal nicht live nachzieht)"""
    bl_idname = "felge3d.param_refresh"
    bl_label = "Refresh"

    def execute(self, context):
        s, ob, md = _current(context)
        if ob is None:
            return {"CANCELLED"}
        md.node_group.update_tag()
        ob.update_tag()
        context.view_layer.update()
        return {"FINISHED"}


class FELGE3D_OT_param_apply(Operator):
    """Modifier-Stack festschreiben (Node-Baum, Bevel, Weighted Normal): normales Mesh zum Nacharbeiten"""
    bl_idname = "felge3d.param_apply"
    bl_label = "Anwenden"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s, ob, md = _current(context)
        if ob is None:
            self.report({"ERROR"}, "Keine parametrische Felge in der aktuellen Collection.")
            return {"CANCELLED"}
        paramrim.apply_all(context, ob)
        ob["felge3d_role"] = "param_applied"          # nicht mehr parametrisch: wird nicht mehr überschrieben
        self.report({"INFO"}, "Angewendet: normales Mesh, Nachbearbeitung möglich.")
        return {"FINISHED"}


class FELGE3D_OT_param_redetect(Operator):
    """Speichenzahl, -form und Nabe erneut aus dem KI-Mesh ableiten (setzt die Werte der Felge zurück)"""
    bl_idname = "felge3d.param_redetect"
    bl_label = "Aus KI-Mesh neu ableiten"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        import json
        from . import build_param_defaults, profile_node
        s, ob, md = _current(context)
        if md is None:
            return {"CANCELLED"}
        raw = s.collection.get("felge3d_detect")
        det = json.loads(raw) if raw else None
        for k, v in build_param_defaults(s, det["n"] if det else None).items():
            if k != "hub_x":
                try:
                    paramrim.set_param(md, k, v)
                except (KeyError, TypeError, ValueError):
                    pass
        pts = sorted((p.location[0], p.location[1]) for p in profile_node().mapping.curves[0].points)
        apply_detected(md, det, pts)
        ob.update_tag()
        return {"FINISHED"}


class FELGE3D_OT_param_reset_curve(Operator):
    """Schnittkurve auf die exakte Standardform zurücksetzen"""
    bl_idname = "felge3d.param_reset_curve"
    bl_label = "Kurve zurücksetzen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s, ob, md = _current(context)
        if md is None:
            return {"CANCELLED"}
        from . import default_hub_x
        paramrim.set_curve_points(paramrim.curve_node(md).mapping, paramrim.default_section_points(default_hub_x(s)))
        md.node_group.update_tag()
        ob.update_tag()
        return {"FINISHED"}


# ---------------------------------------------------------------- Panels
GROUPS = [
    ("Form", ("Durchmesser (Zoll)", "Breite J (Zoll)")),
    ("Speichen", ("Speichen", "Drehung (Grad)", "Speichenbreite (mm)", "Biegung (Grad)", "Wölbung (mm)", "Dicke Speiche (mm)")),
    ("Nabe", ("Zentralverschluss", "Radschrauben", "Lochkreis (mm)", "Nabenradius (mm)", "Dicke Nabe (mm)")),
    ("Tiefe", ("Konkavität", "Schüsseltiefe (mm)", "Front-Einzug (mm)", "Ring (mm)")),
    ("Felgenbett", ("Flansch (mm)", "Wandstärke (mm)", "Tiefbett (mm)", "Auflösung")),
    ("Material", ("Diamond Cut",)),
]


def _draw_param(layout, md, name):
    ident = paramrim.socket_ids(md.node_group).get(name)
    if ident is None:
        return
    st = paramrim._input_struct(md, ident)
    if st is not None:
        layout.prop(st, "value", text=name)
    else:
        layout.prop(md, '["%s"]' % ident, text=name)


def _material_of(md, node_name):
    """Das zur Felge gehörende Material mit dem Farbknoten (je Felge eigene Materialien)."""
    suffix = " " + md.node_group.name
    base = paramrim.MATERIAL_FRONT if node_name == paramrim.FRONT_COLOR_NODE else paramrim.MATERIAL_BODY
    mat = bpy.data.materials.get(base + suffix)
    return mat if mat is not None and mat.node_tree and node_name in mat.node_tree.nodes else None


class FELGE3D_PT_param(Panel):
    bl_label = "Parametrische Felge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_main"

    def draw(self, context):
        L = self.layout
        s = context.scene.felge3d
        if not PARAM_OK:
            L.label(text="Benötigt Blender 5.3 oder neuer", icon="INFO")
            return
        ob = param_object_of(s.collection)
        md = param_modifier(ob)
        if md is None:
            L.operator("felge3d.param_build", icon="MESH_GRID")
            return
        c = L.column(align=True)
        _draw_param(c, md, "Konkavität")
        L.label(text="Kurve: x = Radius (Nabe → Horn), y = Tiefe")
        try:
            L.template_curve_mapping(paramrim.curve_node(md), "mapping", type="NONE")
        except Exception as e:  # noqa: BLE001
            L.label(text="Kurve nicht verfügbar: %s" % e, icon="ERROR")
        row = L.row(align=True)
        row.operator("felge3d.param_reset_curve", icon="LOOP_BACK")
        row.operator("felge3d.param_refresh", icon="FILE_REFRESH")
        for title, names in GROUPS:
            box = L.box()
            box.label(text=title)
            col = box.column(align=True)
            for nm in names:
                if nm != "Konkavität":
                    _draw_param(col, md, nm)
            if title == "Material":
                for node_name, label in ((paramrim.FRONT_COLOR_NODE, "Frontfläche (Diamond Cut)"), (paramrim.BODY_COLOR_NODE, "Grundfarbe")):
                    mat = _material_of(md, node_name)
                    if mat is not None:
                        col.prop(mat.node_tree.nodes[node_name].outputs[0], "default_value", text=label)
        info = s.collection.get("felge3d_detect_info") if s.collection else None
        if info:
            L.label(text="Erkannt: " + info, icon="VIEWZOOM")
        row = L.row(align=True)
        row.operator("felge3d.param_redetect", icon="FILE_REFRESH")
        row.operator("felge3d.param_build", text="Standardwerte", icon="LOOP_BACK")
        L.operator("felge3d.param_apply", icon="CHECKMARK")


class FELGE3D_PT_param_curves(Panel):
    bl_label = "Speichenform (Kurven)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_param"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return PARAM_OK and param_modifier(param_object_of(context.scene.felge3d.collection)) is not None

    def draw(self, context):
        L = self.layout
        md = param_modifier(param_object_of(context.scene.felge3d.collection))
        if md is None:
            return
        for title, node in (("Speichenbreite (Nabe → Rand)", paramrim.CURVE_WIDTH), ("Speichenbiegung (Nabe → Rand)", paramrim.CURVE_SWEEP)):
            L.label(text=title)
            L.template_curve_mapping(paramrim.curve_node(md, node), "mapping", type="NONE")


class FELGE3D_PT_rims(Panel):
    bl_label = "Felgen vergleichen"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_main"

    @classmethod
    def poll(cls, context):
        return len(rim_collections()) > 0

    def draw(self, context):
        L = self.layout
        s = context.scene.felge3d
        L.prop(s, "active_rim", text="")
        for c in rim_collections():
            row = L.row(align=True)
            op = row.operator("felge3d.rim_show", text=c.name, depress=(s.collection == c), icon="HIDE_OFF" if not c.hide_viewport else "HIDE_ON")
            op.name = c.name


class FELGE3D_OT_rim_show(Operator):
    """Diese Felge anzeigen, die anderen ausblenden"""
    bl_idname = "felge3d.rim_show"
    bl_label = "Felge anzeigen"
    name: bpy.props.StringProperty()

    def execute(self, context):
        s = context.scene.felge3d
        s.active_rim = self.name                      # der Update-Callback schaltet um
        return {"FINISHED"}


classes = (FELGE3D_OT_param_build, FELGE3D_OT_param_refresh, FELGE3D_OT_param_apply, FELGE3D_OT_param_redetect,
           FELGE3D_OT_param_reset_curve,
           FELGE3D_OT_rim_show, FELGE3D_PT_param, FELGE3D_PT_param_curves, FELGE3D_PT_rims)
