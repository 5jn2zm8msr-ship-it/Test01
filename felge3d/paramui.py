# SPDX-License-Identifier: GPL-3.0-or-later
"""Oberfläche und Collection-Verwaltung für die parametrische Felge (Geometry Nodes, ab Blender 5.3)."""
import json

import bpy
from bpy.types import Operator, Panel

from . import paramrim

PARAM_OK = bpy.app.version >= (5, 3, 0)
ROLE_PARAM, ROLE_TEMPLATE, ROLE_TEMPLATE_BAKED = "param", "template", "template_baked"
KEEP_ROLES = (ROLE_PARAM, "param_applied", ROLE_TEMPLATE, ROLE_TEMPLATE_BAKED, paramrim.TELLER_ROLE)
AI_ROLES = ("star", "barrel", "body")
MOD_RIM, MOD_TEMPLATE = "Parametrische Felge", "Musterspeiche"


# ---------------------------------------------------------------- Collections / Objekte
def next_rim_name():
    i = 1
    while True:
        name = "Felge_%02d" % i
        if name not in bpy.data.collections:
            return name
        i += 1


def rim_collections():
    return sorted((c for c in bpy.data.collections if c.get("felge3d_rim")), key=lambda c: c.name)


def _object_with_role(col, roles):
    if col is None or col.name not in bpy.data.collections:
        return None
    for ob in col.objects:
        if ob.get("felge3d_role") in roles and ob.type == "MESH":
            return ob
    return None


def param_object_of(col):
    return _object_with_role(col, (ROLE_PARAM,))


def template_object_of(col):
    return _object_with_role(col, (ROLE_TEMPLATE, ROLE_TEMPLATE_BAKED))


def teller_object_of(col):
    if col is None or col.name not in bpy.data.collections:
        return None
    return next((ob for ob in col.objects if ob.get("felge3d_role") == paramrim.TELLER_ROLE and ob.type == "CURVE"), None)


def _nodes_modifier(ob, with_node):
    if ob is None:
        return None
    return next((m for m in ob.modifiers if m.type == "NODES" and m.node_group is not None and with_node in m.node_group.nodes), None)


def param_modifier(ob):
    return _nodes_modifier(ob, paramrim.CURVE_SECTION)


def template_modifier(tob):
    return _nodes_modifier(tob, paramrim.CURVE_WIDTH)


class Rim:
    """Felge + Muster als Einheit: Werte lesen/setzen, jeweils am richtigen Objekt."""

    def __init__(self, col):
        self.col = col
        self.ob = param_object_of(col)
        self.tob = template_object_of(col)
        self.md = param_modifier(self.ob)
        self.tmd = template_modifier(self.tob)
        self.cob = teller_object_of(col)

    @property
    def ok(self):
        return self.md is not None

    @property
    def baked(self):
        return self.tob is not None and self.tmd is None

    def _target(self, name):
        if name in paramrim.SLICE_ONLY:
            return self.tmd
        return self.md

    def get(self, name):
        md = self._target(name)
        if md is None:                                    # Muster fest: letzte Werte aus dem Merkzettel
            data = json.loads(self.tob.get("felge3d_slice_params", "{}")) if self.tob is not None else {}
            return data.get(name)
        return paramrim.get_param(md, name)

    def set(self, name, value):
        if name == "Speichen":
            for md in (self.md, self.tmd):
                if md is not None:
                    paramrim.set_param(md, name, value)
            return
        md = self._target(name)
        if md is not None:
            paramrim.set_param(md, name, value)


def reset_teller(rim):
    """Teller-Kurve auf den Ausgangsverlauf zurücksetzen: Schnittkurve (Schüssel) + Höhe der polierten Fläche aus dem Foto, 3 Punkte."""
    import numpy as np
    if rim.cob is None or rim.md is None:
        return
    td = json.loads(rim.tob.get("felge3d_tdata", "{}")) if rim.tob is not None else {}
    hh = np.asarray(td.get("teller_h") or [(0.0, 0.0), (1.0, 0.0)], np.float64)
    g = lambda n: float(paramrim.get_param(rim.md, n))  # noqa: E731
    r_face = g("Durchmesser (Zoll)") * 0.0127 - g("Wandstärke (mm)") * 0.001 + 0.001
    z_rim, dish = -g("Front-Einzug (mm)") * 0.001, g("Schüsseltiefe (mm)") * 0.001 * g("Konkavität")
    mp = paramrim.curve_node(rim.md).mapping
    cm = mp.curves[0]

    def z(u):
        return z_rim - dish * mp.evaluate(cm, min(max(u, 0.0), 1.0)) + float(np.interp(u, hh[:, 0], hh[:, 1]))

    um, d = 0.62, 0.03
    slope = (z(um + d) - z(um - d)) / (2 * d * r_face)
    paramrim.set_teller_points(rim.cob, [(0.0, z(0.0)), (um * r_face, z(um)), (r_face, z(1.0))], slope)
    rim.ob.update_tag()


def hide_ai(col):
    """KI-Mesh bleibt erhalten, ist aber ausgeblendet (Viewport und Render)."""
    for ob in col.objects:
        if ob.get("felge3d_role") in AI_ROLES:
            try:
                ob.hide_set(True)
            except RuntimeError:
                pass
            ob.hide_render = True


def apply_detected(rim, det, section_pts=None):
    """Erkannte Werte (paramdetect.detect: Speichenzahl, Drehung, Kantenkurven, Nabe) und die Tiefenkurve des KI-Meshes übertragen."""
    if det:
        for k, v in (("Speichen", det["n"]), ("Drehung (Grad)", det["drehung_deg"]),
                     ("Nabenradius (mm)", min(max(det["hub_r_mm"], 40.0), 130.0))):
            try:
                rim.set(k, v)
            except (KeyError, TypeError, ValueError):
                pass
        if rim.tmd is not None:
            paramrim.set_curve_points(paramrim.curve_node(rim.tmd, paramrim.CURVE_EDGE_L).mapping, det["edge_l"])
            paramrim.set_curve_points(paramrim.curve_node(rim.tmd, paramrim.CURVE_EDGE_R).mapping, det["edge_r"])
            if det.get("seam"):
                paramrim.set_curve_points(paramrim.curve_node(rim.tmd, paramrim.CURVE_SEAM).mapping, det["seam"])
    if section_pts and rim.md is not None:
        paramrim.set_curve_points(paramrim.curve_node(rim.md).mapping, section_pts)
    for ob in (rim.ob, rim.tob):
        if ob is not None:
            ob.update_tag()


def ensure_param(context, s, col, root, defaults, detected=None, section_pts=None, tdata=None):
    """Felge + Musterspeiche in der Collection anlegen (vorhandene bleiben mit den Werten des Nutzers erhalten)."""
    ob = param_object_of(col)
    if ob is None:
        d = dict(defaults)
        hub_x = d.pop("hub_x", 0.34)
        ob, tob, md = paramrim.make_object("%s parametrisch" % col.name, col, None, hub_x=hub_x, tdata=tdata)
        ob["felge3d_role"] = ROLE_PARAM
        tob["felge3d_role"] = ROLE_TEMPLATE if tdata is None else ROLE_TEMPLATE_BAKED
        if tdata is not None:                              # Datenfeld für „neu erzeugen“ merken
            tob["felge3d_tdata"] = json.dumps({k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in tdata.items()})
        if root is not None:
            ob.parent = root
            tob.parent = root
            c0 = teller_object_of(col)
            if c0 is not None:
                c0.parent = root
        rim = Rim(col)
        for k, v in d.items():
            try:
                rim.set(k, v)
            except (KeyError, TypeError, ValueError):
                pass
        for k, v in (("Referenz-Durchmesser (Zoll)", d.get("Durchmesser (Zoll)")), ("Referenz-Wandstärke (mm)", d.get("Wandstärke (mm)"))):
            if v is not None:                              # Muster wird für diese Größe gebaut
                if rim.tmd is not None:
                    paramrim.set_param(rim.tmd, k, float(v))
                paramrim.set_param(rim.md, k, float(v))
        if tdata is None or "crease_top" not in tdata:      # alte Gitter-Muster sind schwer: ohne Unterteilung
            paramrim.set_param(rim.md, "Unterteilung", 0)
        apply_detected(rim, detected, section_pts)
        reset_teller(rim)
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


# ---------------------------------------------------------------- Größen für die vier Räder (geteilte Node-Group)
def _rim_inputs(src_md):
    return {nm: paramrim.get_param(src_md, nm) for nm in paramrim.socket_ids(src_md.node_group)}


def attach_modifiers(ob, src_md, cfg):
    """Rad-Objekt mit derselben Node-Group wie die Felge (live gekoppelt), eigene Zoll-/Breiten-/Tiefenwerte."""
    md = ob.modifiers.new(MOD_RIM, "NODES")
    md.node_group = src_md.node_group
    vals = _rim_inputs(src_md)
    vals.update(cfg)
    for nm, v in vals.items():
        paramrim.set_param(md, nm, v)
    if any(m.type == "BEVEL" for m in src_md.id_data.modifiers):      # nur Felgen ohne Käfig/Subdivision brauchen Bevel
        paramrim.add_finish_modifiers(ob)
    return md


def param_rim_mesh(context, src_ob, cfg, name):
    """Auswertung der Felge in der Größe einer Achse (für Hinterkante/Radhaus); Node-Group und Felge bleiben unverändert."""
    src_md = param_modifier(src_ob)
    ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    context.scene.collection.objects.link(ob)
    try:
        attach_modifiers(ob, src_md, cfg)
        context.view_layer.update()
        dg = context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
        me.name = name
    finally:
        context.scene.collection.objects.unlink(ob)
        old = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(old)
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


# ---------------------------------------------------------------- Varianten
def make_variant(context, s):
    """Kopiert die aktive Felgen-Collection (Muster inkl. Handarbeit, Kurven, Materialien) nach <Name>_v2 …; das Original bleibt."""
    src = s.collection
    if src is None:
        raise RuntimeError("Keine Felgen-Collection aktiv.")
    base = src.get("felge3d_variant_of") or src.name
    i = 2
    while "%s_v%d" % (base, i) in bpy.data.collections:
        i += 1
    new = bpy.data.collections.new("%s_v%d" % (base, i))
    context.scene.collection.children.link(new)
    for k in ("felge3d_image", "felge3d_detect", "felge3d_detect_info"):
        if k in src:
            new[k] = src[k]
    new["felge3d_rim"] = True
    new["felge3d_variant_of"] = base
    mapping = {}
    for ob in src.objects:
        cp = ob.copy()
        if ob.data is not None:
            cp.data = ob.data.copy()
        new.objects.link(cp)
        mapping[ob] = cp
    for ob, cp in mapping.items():
        cp.parent = mapping.get(ob.parent, ob.parent)
        cp.matrix_parent_inverse = ob.matrix_parent_inverse.copy()
    rim_ob, tmpl_ob = mapping.get(param_object_of(src)), mapping.get(template_object_of(src))
    tel_ob = mapping.get(teller_object_of(src))
    # Node-Groups und Materialien eigenständig kopieren, Muster-Verweis auf die Kopie umlenken
    tag = " " + new.name
    mats = {}
    for ob in (rim_ob, tmpl_ob):
        if ob is None:
            continue
        for md in ob.modifiers:
            if md.type == "NODES" and md.node_group is not None:
                ng = md.node_group.copy()
                ng.name = md.node_group.name + tag
                md.node_group = ng
                for n in ng.nodes:
                    if n.bl_idname == "GeometryNodeObjectInfo":
                        tgt = tel_ob if n.name == paramrim.TELLER_NODE else tmpl_ob
                        if tgt is not None:
                            n.inputs["Object"].default_value = tgt
                    if n.bl_idname == "GeometryNodeSetMaterial":
                        m0 = n.inputs["Material"].default_value
                        if m0 is not None:
                            if m0 not in mats:
                                mats[m0] = m0.copy()
                                mats[m0].name = m0.name + tag
                            n.inputs["Material"].default_value = mats[m0]
    for ob in new.objects:
        if ob.get("felge3d_role") in AI_ROLES:
            ob.hide_render = True
    return new


# ---------------------------------------------------------------- Operatoren
def _current(context):
    s = context.scene.felge3d
    return s, Rim(s.collection)


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
        for old in (param_object_of(col), template_object_of(col)):
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
        s, rim = _current(context)
        if not rim.ok:
            return {"CANCELLED"}
        for md in (rim.md, rim.tmd):
            if md is not None:
                md.node_group.update_tag()
        for ob in (rim.ob, rim.tob):
            if ob is not None:
                ob.update_tag()
        context.view_layer.update()
        return {"FINISHED"}


class FELGE3D_OT_param_apply(Operator):
    """Felge festschreiben (Node-Baum, Bevel, Weighted Normal): normales Mesh zum Nacharbeiten"""
    bl_idname = "felge3d.param_apply"
    bl_label = "Felge anwenden"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s, rim = _current(context)
        if not rim.ok:
            self.report({"ERROR"}, "Keine parametrische Felge in der aktuellen Collection.")
            return {"CANCELLED"}
        paramrim.apply_all(context, rim.ob)
        rim.ob["felge3d_role"] = "param_applied"          # nicht mehr parametrisch: wird nicht mehr überschrieben
        self.report({"INFO"}, "Angewendet: normales Mesh, Nachbearbeitung möglich.")
        return {"FINISHED"}


class FELGE3D_OT_template_bake(Operator):
    """Musterspeiche (Pizzastück) zum Bearbeiten festschreiben: danach im Edit Mode ändern, die Felge folgt live"""
    bl_idname = "felge3d.template_bake"
    bl_label = "Muster zum Bearbeiten anwenden"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s, rim = _current(context)
        if rim.tob is None or rim.tmd is None:
            self.report({"WARNING"}, "Das Muster ist schon ein festes Mesh.")
            return {"CANCELLED"}
        vals = {nm: paramrim.get_param(rim.tmd, nm) for nm in paramrim.socket_ids(rim.tmd.node_group)}
        rim.tob["felge3d_slice_params"] = json.dumps(vals)
        rim.tob["felge3d_slice_group"] = rim.tmd.node_group.name
        rim.tmd.node_group.use_fake_user = True
        dg = context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(rim.tob.evaluated_get(dg), depsgraph=dg)
        old = rim.tob.data
        rim.tob.modifiers.clear()
        rim.tob.data = me
        me.name = rim.tob.name
        if old.users == 0:
            bpy.data.meshes.remove(old)
        rim.tob["felge3d_role"] = ROLE_TEMPLATE_BAKED
        rim.tob.display_type = "SOLID"
        for o in context.view_layer.objects:
            o.select_set(False)
        rim.tob.select_set(True)
        context.view_layer.objects.active = rim.tob
        self.report({"INFO"}, "Muster ist jetzt ein Mesh: Tab = Edit Mode. Nahtpunkte (±180°/Speichen) nicht verschieben.")
        return {"FINISHED"}


class FELGE3D_OT_template_regen(Operator):
    """Muster neu aus den Parametern erzeugen (verwirft Handarbeit am Muster)"""
    bl_idname = "felge3d.template_regen"
    bl_label = "Muster neu erzeugen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s, rim = _current(context)
        if rim.tob is None or rim.tmd is not None:
            return {"CANCELLED"}
        raw = rim.tob.get("felge3d_tdata")
        if raw:                                           # Muster aus dem KI-Mesh neu aufbauen
            import numpy as np
            td = {k: (np.asarray(v) if isinstance(v, list) and k != "faces" else v) for k, v in json.loads(raw).items()}
            old = rim.tob.data
            build = (paramrim.template_mesh_from_cage if "crease_top" in td else paramrim.template_mesh_from_sector if "faces" in td
                     else paramrim.template_mesh_from_data)
            rim.tob.data = build(rim.tob.name, td)
            if old.users == 0:
                bpy.data.meshes.remove(old)
            rim.tob.update_tag()
            return {"FINISHED"}
        ng = bpy.data.node_groups.get(rim.tob.get("felge3d_slice_group", ""))
        if ng is None:
            self.report({"ERROR"}, "Die Parameter des Musters sind nicht mehr vorhanden.")
            return {"CANCELLED"}
        old = rim.tob.data
        rim.tob.data = bpy.data.meshes.new(rim.tob.name)
        if old.users == 0:
            bpy.data.meshes.remove(old)
        md = rim.tob.modifiers.new(MOD_TEMPLATE, "NODES")
        md.node_group = ng
        for nm, v in json.loads(rim.tob.get("felge3d_slice_params", "{}")).items():
            try:
                paramrim.set_param(md, nm, v)
            except (KeyError, TypeError, ValueError):
                pass
        rim.tob["felge3d_role"] = ROLE_TEMPLATE
        rim.tob.display_type = "WIRE"
        return {"FINISHED"}


class FELGE3D_OT_param_variant(Operator):
    """Als neue Variante speichern: kopiert Felge, Muster (inkl. Handarbeit), Kurven und Materialien in eine neue Collection"""
    bl_idname = "felge3d.param_variant"
    bl_label = "Als neue Variante speichern"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.felge3d
        try:
            new = make_variant(context, s)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        s.active_rim = new.name
        self.report({"INFO"}, "Variante gespeichert: %s (Original unverändert)" % new.name)
        return {"FINISHED"}


class FELGE3D_OT_param_redetect(Operator):
    """Speichenzahl, -form und Nabe erneut aus dem KI-Mesh ableiten (setzt die Werte der Felge zurück)"""
    bl_idname = "felge3d.param_redetect"
    bl_label = "Aus KI-Mesh neu ableiten"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        from . import build_param_defaults, profile_node
        s, rim = _current(context)
        if not rim.ok:
            return {"CANCELLED"}
        if rim.baked:
            self.report({"WARNING"}, "Das Muster ist ein festes Mesh: erst ‚Muster neu erzeugen‘.")
            return {"CANCELLED"}
        raw = s.collection.get("felge3d_detect")
        det = json.loads(raw) if raw else None
        for k, v in build_param_defaults(s, det["n"] if det else None).items():
            if k != "hub_x":
                try:
                    rim.set(k, v)
                except (KeyError, TypeError, ValueError):
                    pass
        pts = sorted((p.location[0], p.location[1]) for p in profile_node().mapping.curves[0].points)
        apply_detected(rim, det, pts)
        return {"FINISHED"}


class FELGE3D_OT_param_reset_curve(Operator):
    """Schnittkurve auf die exakte Standardform zurücksetzen"""
    bl_idname = "felge3d.param_reset_curve"
    bl_label = "Kurve zurücksetzen"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s, rim = _current(context)
        if not rim.ok:
            return {"CANCELLED"}
        from . import default_hub_x
        paramrim.set_curve_points(paramrim.curve_node(rim.md).mapping, paramrim.default_section_points(default_hub_x(s)))
        rim.md.node_group.update_tag()
        rim.ob.update_tag()
        return {"FINISHED"}


class FELGE3D_OT_teller_edit(Operator):
    bl_idname = "felge3d.teller_edit"
    bl_label = "Teller-Kurve bearbeiten"
    bl_description = "Wählt die Teller-Kurve (3 Bezier-Punkte, echte Maße) und öffnet den Edit Mode; der Teller folgt live"

    def execute(self, context):
        s, rim = _current(context)
        if rim.cob is None:
            self.report({"WARNING"}, "Keine Teller-Kurve in dieser Felge.")
            return {"CANCELLED"}
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in context.view_layer.objects:
            o.select_set(False)
        rim.cob.hide_set(False)
        rim.cob.select_set(True)
        context.view_layer.objects.active = rim.cob
        bpy.ops.object.mode_set(mode="EDIT")
        return {"FINISHED"}


class FELGE3D_OT_teller_reset(Operator):
    bl_idname = "felge3d.teller_reset"
    bl_label = "Teller zurücksetzen"
    bl_description = "Teller-Kurve auf den Ausgangsverlauf (aus Foto und Schnittkurve) zurücksetzen"

    def execute(self, context):
        s, rim = _current(context)
        if rim.cob is None:
            return {"CANCELLED"}
        if context.object is not None and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        reset_teller(rim)
        return {"FINISHED"}


# ---------------------------------------------------------------- Panels
GROUPS = [
    ("Form", ("Durchmesser (Zoll)", "Breite J (Zoll)")),
    ("Speichen", ("Speichen", "Drehung (Grad)", "Wölbung (mm)", "Dicke Speiche (mm)")),
    ("Nabe", ("Zentralverschluss", "Radschrauben", "Lochkreis (mm)", "Nabenradius (mm)", "Dicke Nabe (mm)", "Nabenbund Höhe (mm)", "Nabenbund Radius (mm)")),
    ("Tiefe", ("Konkavität", "Schüsseltiefe (mm)", "Front-Einzug (mm)")),
    ("Felgenbett", ("Flansch (mm)", "Wandstärke (mm)", "Tiefbett (mm)", "Auflösung")),
    ("Unterteilung", ("Unterteilung", "Kantenschärfe")),
    ("Material", ("Diamond Cut", "Diamond-Cut Rand (%)")),
    ("Teller (Diamond Cut)", ("Rücksprung (mm)", "Horn poliert", "Teller anzeigen")),
]


def _draw_param(layout, md, name, enabled=True):
    if md is None:
        return
    ident = paramrim.socket_ids(md.node_group).get(name)
    if ident is None:
        return
    st = paramrim._input_struct(md, ident)
    row = layout.row()
    row.enabled = enabled
    if st is not None:
        row.prop(st, "value", text=name)
    else:
        row.prop(md, '["%s"]' % ident, text=name)


def _material_of(md, node_name):
    """Das zur Felge gehörende Material mit dem Farbknoten (je Felge eigene Materialien)."""
    suffix = " " + md.node_group.name
    base = paramrim.MATERIAL_FRONT if node_name == paramrim.FRONT_COLOR_NODE else paramrim.MATERIAL_BODY
    for nm in (base + suffix, base + " " + md.id_data.name):
        mat = bpy.data.materials.get(nm)
        if mat is not None and mat.node_tree and node_name in mat.node_tree.nodes:
            return mat
    return None


def _set_material_of(rim):
    for n in rim.md.node_group.nodes:
        if n.bl_idname == "GeometryNodeSetMaterial" and n.inputs["Material"].default_value is not None:
            yield n.inputs["Material"].default_value


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
        rim = Rim(s.collection)
        if not rim.ok:
            L.operator("felge3d.param_build", icon="MESH_GRID")
            return
        c = L.column(align=True)
        _draw_param(c, rim.md, "Konkavität")
        L.label(text="Kurve: x = Radius (Nabe → Horn), y = Tiefe")
        try:
            L.template_curve_mapping(paramrim.curve_node(rim.md), "mapping", type="NONE")
        except Exception as e:  # noqa: BLE001
            L.label(text="Kurve nicht verfügbar: %s" % e, icon="ERROR")
        row = L.row(align=True)
        row.operator("felge3d.param_reset_curve", icon="LOOP_BACK")
        row.operator("felge3d.param_refresh", icon="FILE_REFRESH")
        row = L.row(align=True)
        row.operator("felge3d.teller_edit", icon="CURVE_BEZCURVE")
        row.operator("felge3d.teller_reset", icon="LOOP_BACK", text="")
        for title, names in GROUPS:
            box = L.box()
            box.label(text=title)
            col = box.column(align=True)
            for nm in names:
                if nm == "Konkavität":
                    continue
                if nm in paramrim.SLICE_ONLY:
                    _draw_param(col, rim.tmd, nm, enabled=not rim.baked)
                elif nm == "Speichen":
                    _draw_param(col, rim.md, nm, enabled=not rim.baked)
                else:
                    _draw_param(col, rim.md, nm)
            if title == "Material":
                for node_name, label in ((paramrim.FRONT_COLOR_NODE, "Frontfläche (Diamond Cut)"), (paramrim.BODY_COLOR_NODE, "Grundfarbe")):
                    mat = _material_of(rim.md, node_name)
                    if mat is not None:
                        col.prop(mat.node_tree.nodes[node_name].outputs[0], "default_value", text=label)
        info = s.collection.get("felge3d_detect_info") if s.collection else None
        if info:
            L.label(text="Erkannt: " + info, icon="VIEWZOOM")
        row = L.row(align=True)
        row.operator("felge3d.param_redetect", icon="FILE_REFRESH")
        row.operator("felge3d.param_build", text="Standardwerte", icon="LOOP_BACK")
        L.operator("felge3d.param_apply", icon="CHECKMARK")


class FELGE3D_PT_param_template(Panel):
    bl_label = "Musterspeiche bearbeiten"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_param"

    @classmethod
    def poll(cls, context):
        return PARAM_OK and Rim(context.scene.felge3d.collection).ok

    def draw(self, context):
        L = self.layout
        rim = Rim(context.scene.felge3d.collection)
        L.label(text="Pizzastück: Nabenkeil + Speiche + Ringkeil", icon="MESH_GRID")
        if rim.tob is not None:
            L.label(text="Objekt: " + rim.tob.name)
        if rim.baked:
            L.label(text="Fest: Edit Mode bearbeiten, Felge folgt live", icon="EDITMODE_HLT")
            L.operator("felge3d.template_regen", icon="LOOP_BACK")
        else:
            L.operator("felge3d.template_bake", icon="MODIFIER")
        L.separator()
        L.operator("felge3d.param_variant", icon="DUPLICATE")


class FELGE3D_PT_param_curves(Panel):
    bl_label = "Speichenform (Kurven)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "2D to 3D Rim"
    bl_parent_id = "FELGE3D_PT_param"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return PARAM_OK and Rim(context.scene.felge3d.collection).tmd is not None

    def draw(self, context):
        L = self.layout
        rim = Rim(context.scene.felge3d.collection)
        if rim.tmd is None:
            return
        for title, node in (("Linke Speichenkante (Nabe → Rand, Anteil der Keilbreite)", paramrim.CURVE_EDGE_L), ("Rechte Speichenkante", paramrim.CURVE_EDGE_R), ("Nahtverlauf (nicht verändern)", paramrim.CURVE_SEAM)):
            L.label(text=title)
            L.template_curve_mapping(paramrim.curve_node(rim.tmd, node), "mapping", type="NONE")


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


classes = (FELGE3D_OT_param_build, FELGE3D_OT_param_refresh, FELGE3D_OT_param_apply, FELGE3D_OT_template_bake,
           FELGE3D_OT_template_regen, FELGE3D_OT_param_variant, FELGE3D_OT_param_redetect, FELGE3D_OT_param_reset_curve, FELGE3D_OT_teller_edit, FELGE3D_OT_teller_reset,
           FELGE3D_OT_rim_show, FELGE3D_PT_param, FELGE3D_PT_param_template, FELGE3D_PT_param_curves, FELGE3D_PT_rims)
