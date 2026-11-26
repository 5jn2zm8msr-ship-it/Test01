"""
Blender-Test (bpy-Modul): Add-on registriert mit Meshy-Einstellungen, Guthaben-Operator, Provider-Fabrik aus Preferences,
Job gegen Mock-Server und Import des GLB in eine eigene Collection („KI-Mesh | Meshy“, seitlich verschoben).
Aufruf: python3.11 tests/cloud/test_meshy_blender.py   (kein echter Aufruf, kein Key)
"""
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import HTTPServer

import bpy  # noqa: I001  (muss vor addon_utils kommen)
import addon_utils

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
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
from felge3d import cloud  # noqa: E402

sys.path.insert(0, HERE)
bad = 0


def check(name, cond, info=""):
    global bad
    print("OK   " if cond else "FEHLT", name, info)
    bad += 0 if cond else 1


# GLB zum Ausliefern erzeugen (Würfel)
bpy.ops.mesh.primitive_cube_add(size=0.5)
glb = os.path.join(tempfile.mkdtemp(), "cube.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
GLB = open(glb, "rb").read()
check("Test-GLB > 1000 Byte", len(GLB) > 1000, str(len(GLB)))

# Mock-Server aus dem Unit-Test wiederverwenden, aber mit echtem GLB
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("mock", os.path.join(HERE, "test_meshy_mock.py"))
src = open(os.path.join(HERE, "test_meshy_mock.py")).read().split("def run_case")[0]
ns = {"__file__": os.path.join(HERE, "test_meshy_mock.py")}
exec(compile(src, "mock", "exec"), ns)
ns["H"].do_GET_orig = ns["H"].do_GET
orig = ns["H"].do_GET


def do_GET(self):
    if self.path.startswith("/files/"):
        return self._send(200, raw=GLB)
    return orig(self)


ns["H"].do_GET = do_GET
srv = HTTPServer(("127.0.0.1", 0), ns["H"])
threading.Thread(target=srv.serve_forever, daemon=True).start()
cloud.MeshyProvider.BASE = "http://127.0.0.1:%d/openapi" % srv.server_port
cloud.MeshyProvider.POLL_S = 0.2

prefs = bpy.context.preferences.addons["felge3d"].preferences
sc = bpy.context.scene
s = sc.felge3d
check("Preferences: meshy_key + meshy_model(latest)", hasattr(prefs, "meshy_key") and prefs.meshy_model == "latest")
check("meshy_key maskiert (PASSWORD)", prefs.bl_rna.properties["meshy_key"].subtype == "PASSWORD")
check("Anbieter-Auswahl enthält MESHY", "MESHY" in [i.identifier for i in s.bl_rna.properties["cloud_provider"].enum_items])

s.cloud_provider = "MESHY"
check("ohne Key: cloud_key leer", felge3d.cloud_key() == "")
prefs.meshy_key = ns["FAKE_KEY"]
prefs.meshy_model = "meshy-6"
p = felge3d.make_provider(s)
check("Fabrik: Meshy mit Modell aus Preferences", isinstance(p, cloud.MeshyProvider) and p.options["ai_model"] == "meshy-6")
check("Kostentext (Standard mit Textur) = 30", "30 Credits" in felge3d.cost_text(p), felge3d.cost_text(p))
s.meshy_texture_mode = "MESH"
check("Kostentext nur Mesh = 20", "20 Credits" in felge3d.cost_text(felge3d.make_provider(s)), felge3d.cost_text(felge3d.make_provider(s)))
s.meshy_remesh = True
check("Kostentext nur Mesh mit Remesh = 25", "25 Credits" in felge3d.cost_text(felge3d.make_provider(s)))
s.meshy_remesh = False
s.meshy_texture_mode = "TEX"
prefs.meshy_model = ""
check("leeres Modell -> latest", felge3d.make_provider(s).options["ai_model"] == "latest")

r = bpy.ops.felge3d.cloud_balance()
check("Guthaben-Operator", r == {"FINISHED"} and "123" in s.get("cloud_balance", ""), s.get("cloud_balance", ""))

# Job (Hintergrundthread) -> GLB -> eigene Collection
img = os.path.join(tempfile.mkdtemp(), "a.jpg")
open(img, "wb").write(b"\xff\xd8\xff" + b"0" * 500)
job = cloud.Job(felge3d.make_provider(s), img, tempfile.mkdtemp())
job.start()
t0 = time.time()
while not job.done and time.time() - t0 < 60:
    time.sleep(0.2)
check("Job fertig ohne Fehler", job.done and not job.error and job.result and os.path.isfile(job.result), str(job.error))
col = felge3d._import_glb_collection(bpy.context, job.result, "KI-Mesh | Meshy", 2.4)
check("Collection „KI-Mesh | Meshy“ mit Mesh", col.name.startswith("KI-Mesh | Meshy") and any(o.type == "MESH" for o in col.objects))
roots = [o for o in col.objects if o.parent is None]
check("seitlich verschoben (x = 2.4)", roots and all(abs(o.location.x - 2.4) < 1e-6 for o in roots), str([o.location.x for o in roots]))
check("Collection in der Szene verlinkt", col.name in [c.name for c in sc.collection.children])
srv.shutdown()
print("\nFehlgeschlagen:", bad)
sys.exit(1 if bad else 0)
