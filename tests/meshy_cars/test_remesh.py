"""Test Remesh + Preisrechner gegen lokalen Mock-Server (kein Netz, keine Credits).
Aufruf: python -I tests/meshy_cars/test_remesh.py"""
import base64, http.server, json, os, sys, tempfile, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "meshy_cars"))
import client  # noqa: E402

S = {"posts": [], "reject_task_id": True, "polls": 0}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj=None, raw=None):
        b = raw if raw is not None else json.dumps(obj or {}).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        S["posts"].append((self.path, body))
        if self.path != "/openapi/v1/remesh":
            return self._send(404, {})
        if "input_task_id" in body and S["reject_task_id"]:
            return self._send(400, {"message": "invalid input task: model does not support remesh"})
        self._send(200, {"result": "rm1"})
    def do_GET(self):
        if self.path.endswith("/m.glb"):
            return self._send(200, raw=b"glTF" + b"1" * 3000)
        assert self.path == "/openapi/v1/remesh/rm1", self.path          # Poll muss am Remesh-Endpunkt laufen, nicht am Multi-Image-Endpunkt
        S["polls"] += 1
        if S["polls"] < 2:
            return self._send(200, {"status": "IN_PROGRESS", "progress": 40})
        self._send(200, {"status": "SUCCEEDED", "progress": 100, "consumed_credits": 5,
                         "model_urls": {"glb": "http://127.0.0.1:%d/m.glb" % self.server.server_port}})


# ---- Preisrechner (Preisseite 27.11.2026)
e = client.estimate_credits
assert e("meshy-7.1", "standard", True, "2k") == 30           # = tatsaechlich abgebuchter Testlauf
assert e("latest", "standard", False) == 20 and e("meshy-6", "standard", True, "4k") == 30
assert e("meshy-7.1", "standard", True, "8k") == 35 and e("meshy-7.1", "2k", True, "2k") == 35
assert e("meshy-6-lite", "standard", False) == 5 and e("meshy-6-lite", "standard", True, "2k") == 15
for bad in (("meshy-6-lite", "standard", True, "4k"), ("meshy-6", "2k", True, "2k"), ("meshy-6-lite", "2k", False, "2k")):
    try: e(*bad); raise SystemExit("kein Fehler: %s" % (bad,))
    except client.MeshyError: pass
assert client.REMESH_CREDITS == 5

# ---- Payload
p = client.build_remesh_payload(input_task_id="abc", topology="quad", target_polycount=999999)
assert p == {"topology": "quad", "target_polycount": 300000, "target_formats": ["glb"], "input_task_id": "abc"}, p
for old in ("resize_height", "resize_longest_side", "auto_size", "origin_at", "convert_format_only"):
    assert old not in p, old
assert client.build_remesh_payload(input_task_id="abc", target_polycount=5)["target_polycount"] == 100
for bad in (dict(topology="hex", input_task_id="a"), dict()):
    try: client.build_remesh_payload(**bad); raise SystemExit("kein Fehler: %s" % bad)
    except client.MeshyError: pass

# ---- Ablauf mit Rueckfall
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % srv.server_port
d = tempfile.mkdtemp(); glb = os.path.join(d, "car.glb"); open(glb, "wb").write(b"glTF" + b"2" * 5000)
log = []
out, tid, cr, way = client.run_remesh("k", "task-multi", glb, d, dict(topology="quad", target_polycount=20000),
                                      lambda f, t: log.append(t), base_url=base, interval=0.01)
assert way == "model_url" and tid == "rm1" and cr == 5 and os.path.getsize(out) > 1000
assert len(S["posts"]) == 2 and "input_task_id" in S["posts"][0][1] and "model_url" in S["posts"][1][1]    # erst Task-ID, dann Rueckfall
mu = S["posts"][1][1]["model_url"]
assert mu.startswith("data:application/octet-stream;base64,") and base64.b64decode(mu.split(",", 1)[1]) == open(glb, "rb").read()
assert any("Topologie" in t for t in log)
# Direktweg (Meshy akzeptiert die Task-ID)
S.update(posts=[], reject_task_id=False, polls=0)
_, _, _, way = client.run_remesh("k", "task-multi", glb, d, dict(topology="triangle", target_polycount=1000), base_url=base, interval=0.01)
assert way == "input_task_id" and len(S["posts"]) == 1
# Anderer Fehler (401) -> KEIN Rueckfall, sondern Fehler
S.update(posts=[], polls=0)
class H401(H):
    def do_POST(self): self._send(401, {"message": "bad key"})
srv2 = http.server.HTTPServer(("127.0.0.1", 0), H401); threading.Thread(target=srv2.serve_forever, daemon=True).start()
try: client.run_remesh("k", "t", glb, d, {}, base_url="http://127.0.0.1:%d" % srv2.server_port); raise SystemExit("401 nicht erkannt")
except client.MeshyError as ex: assert ex.code == 401 and "ungültig" in str(ex)
print("OK: Remesh- und Preis-Tests bestanden")
