"""
Test der Meshy-Anbindung gegen einen lokalen Mock-Server (kein echter Aufruf, kein Key, keine Credits).
Prüft die Regeln aus der Meshy-Doku: Endpunkte/Felder, nur Mesh (should_texture=false), ai_model aus den Einstellungen,
Polling mit Retry-After, FAILED/Modellfehler/401/402, KEIN automatisches Erneut-Senden bei 5xx, Remesh, Multi-Image, Guthaben.
Aufruf: python3 -I tests/cloud/test_meshy_mock.py
"""
import importlib.util
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("cloud", os.path.join(ROOT, "felge3d", "cloud.py"))
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)

FAKE_KEY = "msy_TESTKEY_nicht_echt"
STATE = {}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None, headers=None):
        body = raw if raw is not None else json.dumps(obj or {}).encode()
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        if self.headers.get("Authorization") != "Bearer " + FAKE_KEY:
            self._send(401, {"message": "Unauthorized"})
            return False
        return True

    def do_GET(self):
        if self.path.startswith("/files/"):
            return self._send(200, raw=b"glTF" + b"\0" * 2000)
        if not self._auth():
            return
        if self.path == "/openapi/v1/balance":
            return self._send(200, {"balance": 123})
        tid = self.path.rsplit("/", 1)[-1]
        STATE.setdefault("polls", {}).setdefault(tid, 0)
        STATE["polls"][tid] += 1
        mode = STATE.get("mode", "ok")
        if mode in ("poll429", "pollreset") and STATE.setdefault("flaky", 0) < 2:
            STATE["flaky"] += 1
            if mode == "pollreset":
                self.connection.close()
                return
            return self._send(429, {"message": "Too Many Requests"}, headers={"Retry-After": "1"})
        if mode == "remesh_fail" and self.path.startswith("/openapi/v1/remesh"):
            return self._send(200, {"id": tid, "status": "FAILED", "task_error": {"message": "remesh kaputt"}})
        if mode == "failed":
            return self._send(200, {"id": tid, "status": "FAILED", "progress": 0, "task_error": {"message": "Bild unbrauchbar"}})
        if STATE["polls"][tid] < 2:
            return self._send(200, {"id": tid, "status": "IN_PROGRESS", "progress": 40}, headers={"Retry-After": "1"})
        base = "http://127.0.0.1:%d/files/%s.glb" % (self.server.server_port, tid)
        self._send(200, {"id": tid, "status": "SUCCEEDED", "progress": 100, "model_urls": {"glb": base}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n) or b"{}")
        if not self._auth():
            return
        STATE.setdefault("posts", []).append((self.path, payload))
        mode = STATE.get("mode", "ok")
        if mode == "model_gone":
            return self._send(400, {"message": "ai_model meshy-5 is retired"})
        if mode == "nocredit":
            return self._send(402, {"message": "Insufficient credits"})
        if mode == "500":
            return self._send(500, {"message": "boom"})
        self._send(200, {"result": "task%d" % len(STATE["posts"])})


def run_case(mode, options, image, extra=None):
    STATE.clear()
    STATE["mode"] = mode
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cloud.MeshyProvider.BASE = "http://127.0.0.1:%d/openapi" % srv.server_port
    opts = dict(options)
    if extra:
        opts["extra_images"] = extra
    p = cloud.MeshyProvider(FAKE_KEY, opts)
    out = tempfile.mkdtemp()
    try:
        res = p.generate(image, out, lambda *a: None, threading.Event())
        err = None
    except cloud.CloudError as e:
        res, err = None, e
    srv.shutdown()
    return p, res, err


def check(name, cond, info=""):
    print(("OK   " if cond else "FEHLT"), name, info)
    if not cond:
        check.failed += 1


check.failed = 0
img = os.path.join(tempfile.mkdtemp(), "a.jpg")
open(img, "wb").write(b"\xff\xd8\xff" + b"0" * 500)
img2 = os.path.join(os.path.dirname(img), "b.png")
open(img2, "wb").write(b"\x89PNG" + b"0" * 500)

# 1) Standardfall
p, res, err = run_case("ok", {"ai_model": "latest"}, img)
path, pl = STATE["posts"][0]
check("Erfolg: GLB geladen", res and os.path.getsize(res) > 1000 and err is None, str(err or ""))
check("Endpunkt /v1/image-to-3d", path == "/openapi/v1/image-to-3d", path)
check("nur Mesh: should_texture=false", pl.get("should_texture") is False)
check("ai_model aus Einstellung (latest)", pl.get("ai_model") == "latest")
check("target_formats=[glb]", pl.get("target_formats") == ["glb"])
check("Bild als Data-URI", pl.get("image_url", "").startswith("data:image/jpeg;base64,"))
check("genau 1 POST (kein Erneut-Senden)", len(STATE["posts"]) == 1)
check("Polling mehrfach (Retry-After beachtet)", max(STATE["polls"].values()) >= 2)
check("Kosten-Schätzung latest = 20", p.estimate_credits() == 20)

# 2) anderes Modell wird nicht überschrieben
p, res, err = run_case("ok", {"ai_model": "meshy-6"}, img)
check("ai_model aus Einstellung (meshy-6)", STATE["posts"][0][1]["ai_model"] == "meshy-6")

# 3) Remesh
p, res, err = run_case("ok", {"ai_model": "latest", "remesh": True, "polycount": 12345, "topology": "quad"}, img)
paths = [x[0] for x in STATE["posts"]]
check("Remesh: zweiter Aufruf /v1/remesh", paths == ["/openapi/v1/image-to-3d", "/openapi/v1/remesh"], str(paths))
check("Remesh: input_task_id + Polycount", STATE["posts"][1][1].get("input_task_id") == "task1" and STATE["posts"][1][1].get("target_polycount") == 12345)
check("Kosten mit Remesh = 25", p.estimate_credits() == 25)

# 4) Multi-Image
p, res, err = run_case("ok", {"ai_model": "latest"}, img, extra=[img2])
path, pl = STATE["posts"][0]
check("Multi-Image: Endpunkt + 2 Bilder", path == "/openapi/v1/multi-image-to-3d" and len(pl.get("image_urls", [])) == 2, path)
check("Multi-Image: Front zuerst", pl["image_urls"][0].startswith("data:image/jpeg"))
check("Multi-Image: nur Mesh", pl.get("should_texture") is False)

# 5) Fehlerfälle
p, res, err = run_case("model_gone", {"ai_model": "meshy-5"}, img)
check("abgeschaltetes Modell: klare Meldung", err and "meshy-5" in str(err) and "Preferences" in str(err), str(err))
p, res, err = run_case("nocredit", {}, img)
check("402: Meldung Guthaben", err and "Guthaben" in str(err), str(err))
p, res, err = run_case("500", {}, img)
check("5xx: Hinweis + KEIN Erneut-Senden", err and len(STATE["posts"]) == 1 and "trotzdem" in str(err), str(err))
p, res, err = run_case("failed", {}, img)
check("FAILED: Meldung mit Grund", err and "Bild unbrauchbar" in str(err), str(err))
p, res, err = run_case("ok", {"ai_model": "meshy-8"}, img, extra=[img2])
check("unbekanntes Modell + Multi-Image wird gesendet (API entscheidet)", STATE.get("posts") and STATE["posts"][0][1]["ai_model"] == "meshy-8" and res, str(err))
check("unbekanntes Modell: keine Kostenangabe", cloud.MeshyProvider("x", {"ai_model": "meshy-8"}).estimate_credits() is None)
p, res, err = run_case("ok", {"ai_model": "meshy-7"}, img, extra=[img2])
check("meshy-7 (gilt bis 31.12.2026) wird gesendet", STATE.get("posts") and res, str(err))
check("meshy-7: Kosten 20", cloud.MeshyProvider("x", {"ai_model": "meshy-7"}).estimate_credits() == 20)
bad = os.path.join(os.path.dirname(img), "c.bmp")
open(bad, "wb").write(b"BM" + b"0" * 100)
p, res, err = run_case("ok", {}, bad)
check("falsches Bildformat abgewiesen, ohne POST", err and not STATE.get("posts"), str(err))

# 5b) Polling übersteht 429 und Verbindungsabbruch; Task-ID im Endfehler; Remesh-Fehler behält das erste GLB
cloud.MeshyProvider.POLL_S = 0.2
p, res, err = run_case("poll429", {}, img)
check("Polling: 429 wird wiederholt (Retry-After), Ergebnis kommt", res and not err and STATE["flaky"] == 2 and len(STATE["posts"]) == 1, str(err))
p, res, err = run_case("pollreset", {}, img)
check("Polling: Verbindungsabbruch wird wiederholt, kein 2. POST", res and not err and len(STATE["posts"]) == 1, str(err))
p, res, err = run_case("remesh_fail", {"remesh": True}, img)
check("Remesh-Fehler: erstes GLB bleibt erhalten + Warnung", res and not err and "Remesh fehlgeschlagen" in getattr(p, "warning", ""), str(err))
saved = cloud.MeshyProvider.MAX_POLL_FAILS
cloud.MeshyProvider.MAX_POLL_FAILS = 1
p, res, err = run_case("poll429", {}, img)
cloud.MeshyProvider.MAX_POLL_FAILS = saved
check("Endgültiger Polling-Fehler nennt die Task-ID", err and "task1" in str(err), str(err))

# 5c) Cache: dasselbe Bild + gleiche Einstellungen -> KEIN zweiter Aufruf (keine Credits)
cdir = tempfile.mkdtemp()
p, res1, err = run_case("ok", {"ai_model": "latest", "cache_dir": cdir}, img)
n1 = len(STATE["posts"])
p, res2, err = run_case("ok", {"ai_model": "latest", "cache_dir": cdir}, img)
check("Cache: erster Lauf sendet, zweiter Lauf nicht", n1 == 1 and not STATE.get("posts") and res2 and not err, str(err))
p, res3, err = run_case("ok", {"ai_model": "meshy-6", "cache_dir": cdir}, img)
check("Cache: anderes Modell = neuer Aufruf", len(STATE.get("posts", [])) == 1 and res3, str(err))

# 6) Guthaben + falscher Key
STATE.clear()
srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
cloud.MeshyProvider.BASE = "http://127.0.0.1:%d/openapi" % srv.server_port
check("Guthaben-Abfrage", cloud.MeshyProvider(FAKE_KEY).balance() == 123)
try:
    cloud.MeshyProvider("falsch").balance()
    check("falscher Key -> Fehler", False)
except cloud.CloudError as e:
    check("falscher Key -> klare Meldung", e.status == 401 and "Preferences" in str(e), str(e))
srv.shutdown()

# 7) Key nie im Repo
bad_hits = []
for dp, dn, fn in os.walk(ROOT):
    if ".git" in dp.split(os.sep):
        continue
    for f in fn:
        if f.endswith((".py", ".md", ".json", ".txt")) and "msy_" in open(os.path.join(dp, f), errors="ignore").read().replace("msy_TESTKEY_nicht_echt", ""):
            if os.path.join(dp, f) != os.path.abspath(__file__):
                bad_hits.append(os.path.join(dp, f))
check("kein „msy_“-Key im Repo", not [h for h in bad_hits if not h.endswith(("cloud.py", "__init__.py"))], str(bad_hits))

print("\nFehlgeschlagen:", check.failed)
sys.exit(1 if check.failed else 0)
