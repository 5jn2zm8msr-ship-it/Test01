# SPDX-License-Identifier: GPL-3.0-or-later
"""
Meshy Cars (Car Meshi) – Blender-Add-on: 1-4 Autofotos (erstes = Vorderansicht) -> Meshy Multi-Image-to-3D -> texturiertes Mesh in Blender.
Bedienung: 3D-Viewport -> Seitenleiste (N) -> Reiter "Meshy Cars". Der API-Key steht nur in den Add-on-Preferences.
"""
bl_info = {
    "name": "Meshy Cars",
    "author": "Felge3D",
    "version": (0, 1, 0),
    "blender": (3, 5, 0),
    "location": "3D-Viewport > Seitenleiste (N) > Meshy Cars",
    "description": "Auto aus 4 Bildern via Meshy (Multi-Image-to-3D) als texturiertes Mesh importieren",
    "category": "Import-Export",
}

import os
import tempfile
import threading

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel, PropertyGroup

if "client" in locals():
    import importlib
    client = importlib.reload(client)
else:
    from . import client

_JOB = {"thread": None, "cancel": None, "state": None}      # nur ein Job gleichzeitig


def api_key(context=None):
    try:
        k = bpy.context.preferences.addons[__package__].preferences.api_key
    except Exception:  # noqa: BLE001
        k = ""
    return k or os.environ.get("MESHY_API_KEY", "")


class MESHYCARS_Prefs(AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(name="Meshy API-Key", subtype="PASSWORD",
                            description="Nur hier gespeichert, nie in der .blend. Alternativ Umgebungsvariable MESHY_API_KEY")

    def draw(self, context):
        self.layout.prop(self, "api_key")
        self.layout.label(text="Key erstellen: meshy.ai -> Settings -> API. Multi-Image-to-3D braucht einen Bezahl-Plan.")


class MeshyCarsSettings(PropertyGroup):
    img_front: StringProperty(name="Vorne (Hauptbild)", subtype="FILE_PATH", description="Erstes Bild = Vorderansicht (bei meshy-7.1/latest)")
    img_2: StringProperty(name="Seite", subtype="FILE_PATH")
    img_3: StringProperty(name="Hinten", subtype="FILE_PATH")
    img_4: StringProperty(name="Weitere Seite / Schräg", subtype="FILE_PATH")
    ai_model: EnumProperty(name="Modell", default="meshy-7.1", items=[
        ("meshy-7.1", "Meshy 7.1 (aktuell)", "Neuestes Modell (Stand 18.09.2026)"),
        ("latest", "latest", "Löst auf das jeweils neueste Modell auf (derzeit 7.1)"),
        ("meshy-6", "Meshy 6", "Älter, noch verfügbar"),
        ("meshy-6-lite", "Meshy 6 Lite", "Schnell/günstig, ohne Bildverbesserung")])
    geometry: EnumProperty(name="Geometrie", default="standard", items=[
        ("standard", "Standard", ""), ("2k", "Ultra 2k", "Mehr Detail, +5 Credits (nur 7.1/latest)")])
    pbr: BoolProperty(name="PBR-Maps (Metall, Rauheit, Normal)", default=True)
    tex_res: EnumProperty(name="Textur", default="2k", items=[("2k", "2K", ""), ("4k", "4K", ""), ("8k", "8K", "")])
    prompt: StringProperty(name="Textur-Hinweis", description="Optional, max. 800 Zeichen (z.B. 'Lack metallic, Chromteile')")
    enhance: BoolProperty(name="Bildverbesserung", default=True, description="Aus = Aussehen der Bilder exakt halten")
    remesh: BoolProperty(name="Remesh (Quads)", default=False)
    polycount: IntProperty(name="Polygone", default=30000, min=100, max=300000)
    auto_size: BoolProperty(name="Echte Größe schätzen", default=False)
    confirm: BoolProperty(name="Ich weiß: kostenpflichtig (Credits)", default=False)
    # Fortschritt (vom Timer gesetzt)
    progress: FloatProperty(default=0.0, min=0.0, max=1.0)
    status: StringProperty(default="")
    busy: BoolProperty(default=False)


def _options(s):
    return dict(ai_model=s.ai_model, geometry_resolution=s.geometry, should_texture=True, enable_pbr=s.pbr,
                texture_resolution=s.tex_res, texture_prompt=s.prompt, should_remesh=s.remesh,
                topology="quad", target_polycount=s.polycount, image_enhancement=s.enhance, auto_size=s.auto_size)


def _worker(key, paths, out_dir, opts, state, cancel):
    def prog(f, txt):
        state["progress"], state["status"] = f, txt
    try:
        glb, tid, credits = client.run_job(key, paths, out_dir, opts, prog, cancel.is_set)
        state.update(done=True, glb=glb, task_id=tid, credits=credits)
    except Exception as e:  # noqa: BLE001
        state.update(done=True, error=str(e))


def _import_glb(context, glb, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    new = [o for o in bpy.data.objects if o not in before]
    n = 1
    while "Meshy_Car_%02d" % n in bpy.data.collections:
        n += 1
    coll = bpy.data.collections.new("Meshy_Car_%02d" % n)
    context.scene.collection.children.link(coll)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    meshes = [o for o in new if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    if meshes:
        context.view_layer.objects.active = meshes[0]
    return coll, len(meshes)


class MESHYCARS_OT_generate(Operator):
    bl_idname = "meshycars.generate"
    bl_label = "Auto bei Meshy erzeugen"
    bl_description = "Schickt die Bilder an Meshy (kostenpflichtig) und importiert das texturierte Mesh"
    _timer = None

    @classmethod
    def poll(cls, context):
        return not context.scene.meshycars.busy

    def execute(self, context):
        s = context.scene.meshycars
        paths = [bpy.path.abspath(p) for p in (s.img_front, s.img_2, s.img_3, s.img_4) if p]
        if not s.img_front:
            self.report({"ERROR"}, "Vorderansicht (Hauptbild) fehlt.")
            return {"CANCELLED"}
        if not s.confirm:
            self.report({"ERROR"}, "Bitte erst bestätigen, dass die Erzeugung Credits kostet.")
            return {"CANCELLED"}
        key = api_key()
        if not key:
            self.report({"ERROR"}, "Kein Meshy-API-Key in den Add-on-Preferences.")
            return {"CANCELLED"}
        try:
            client.build_payload(paths, **_options(s))        # Eingaben vorab prüfen (Format, Größe), noch vor dem Thread
        except client.MeshyError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        state, cancel = {}, threading.Event()
        out = os.path.join(tempfile.gettempdir(), "meshy_cars")
        th = threading.Thread(target=_worker, args=(key, paths, out, _options(s), state, cancel), daemon=True)
        _JOB.update(thread=th, cancel=cancel, state=state)
        s.busy, s.progress, s.status = True, 0.0, "Starte …"
        s.confirm = False
        th.start()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        s = context.scene.meshycars
        st = _JOB["state"] or {}
        if event.type == "ESC" and not st.get("done"):
            _JOB["cancel"].set()
            s.status = "Abbruch angefordert …"
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        s.progress, s.status = st.get("progress", s.progress), st.get("status", s.status)
        for a in context.screen.areas:
            a.tag_redraw()
        if not st.get("done"):
            return {"RUNNING_MODAL"}
        context.window_manager.event_timer_remove(self._timer)
        s.busy = False
        if st.get("error"):
            s.status = st["error"]
            self.report({"ERROR"}, st["error"])
            return {"CANCELLED"}
        try:
            coll, n = _import_glb(context, st["glb"], "Meshy_Car")
        except Exception as e:  # noqa: BLE001
            s.status = "Import fehlgeschlagen: %s (GLB: %s)" % (e, st["glb"])
            self.report({"ERROR"}, s.status)
            return {"CANCELLED"}
        s.progress, s.status = 1.0, "Fertig: %d Mesh-Objekt(e) in %s (Credits: %s)" % (n, coll.name, st.get("credits"))
        self.report({"INFO"}, s.status)
        return {"FINISHED"}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)


class MESHYCARS_PT_main(Panel):
    bl_label = "Meshy Cars"
    bl_idname = "MESHYCARS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Meshy Cars"

    def draw(self, context):
        L, s = self.layout, context.scene.meshycars
        b = L.box()
        b.label(text="Bilder (1–4, JPG/PNG/WebP, ≤ 20 MB)")
        for p in ("img_front", "img_2", "img_3", "img_4"):
            b.prop(s, p)
        L.prop(s, "ai_model")
        L.prop(s, "geometry")
        L.prop(s, "pbr")
        L.prop(s, "tex_res")
        L.prop(s, "prompt")
        L.prop(s, "enhance")
        r = L.row()
        r.prop(s, "remesh")
        r.prop(s, "auto_size")
        if s.remesh:
            L.prop(s, "polycount")
        L.separator()
        L.prop(s, "confirm")
        r = L.row()
        r.scale_y = 1.5
        r.operator("meshycars.generate", icon="AUTO")
        if s.busy:
            L.prop(s, "progress", text="Fortschritt", slider=True)
            L.label(text="ESC bricht ab")
        if s.status:
            L.label(text=s.status)
        if not api_key():
            L.label(text="API-Key fehlt (Preferences)", icon="ERROR")


_CLASSES = (MESHYCARS_Prefs, MeshyCarsSettings, MESHYCARS_OT_generate, MESHYCARS_PT_main)


def register():
    for c in _CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.meshycars = PointerProperty(type=MeshyCarsSettings)


def unregister():
    del bpy.types.Scene.meshycars
    for c in reversed(_CLASSES):
        bpy.utils.unregister_class(c)
