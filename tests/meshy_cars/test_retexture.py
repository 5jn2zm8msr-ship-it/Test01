"""Test Retexture gegen lokalen Mock-Server (kein Netz, keine Credits). Aufruf: python -I tests/meshy_cars/test_retexture.py"""
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
        if self.path != "/openapi/v1/retexture":
            return self._send(404, {})
        if "input_task_id" in body and S["reject_task_id"]:
            return self._send(400, {"message": "Invalid input task: not a supported type"})
        self._send(200, {"result": "rt1"})
    def do_GET(self):
        if self.path.endswith("/t.glb"):
            return self._send(200, raw=b"glTF" + b"1" * 3000)
        assert self.path == "/openapi/v1/retexture/rt1", self.path      # Poll am Retexture-Endpunkt
        S["polls"] += 1
        if S["polls"] < 2:
            return self._send(200, {"status": "IN_PROGRESS", "progress": 50})
        self._send(200, {"status": "SUCCEEDED", "progress": 100, "consumed_credits": 10,
                         "model_urls": {"glb": "http://127.0.0.1:%d/t.glb" % self.server.server_port}})


assert client.retexture_credits("2k") == 10 and client.retexture_credits("4k") == 10 and client.retexture_credits("8k") == 15
p = client.build_retexture_payload("glossy paint", input_task_id="abc")
assert p == {"text_style_prompt": "glossy paint", "enable_original_uv": True, "enable_pbr": True, "texture_resolution": "2k",
             "target_formats": ["glb"], "input_task_id": "abc"}, p
assert "ai_model" not in p and "hd_texture" not in p and "remove_lighting" not in p            # nichts Unnötiges/Veraltetes
assert len(client.build_retexture_payload("x" * 2000, input_task_id="a")["text_style_prompt"]) == 800
for bad in (dict(prompt="  ", input_task_id="a"), dict(prompt="x"), dict(prompt="x", input_task_id="a", texture_resolution="16k")):
    try: client.build_retexture_payload(**bad); raise SystemExit("kein Fehler: %s" % bad)
    except client.MeshyError: pass

srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % srv.server_port
d = tempfile.mkdtemp(); glb = os.path.join(d, "car.glb"); open(glb, "wb").write(b"glTF" + b"2" * 5000)
out, tid, cr, way = client.run_retexture("k", "task-multi", glb, d, dict(prompt="glossy paint"), base_url=base, interval=0.01)
assert way == "model_url" and tid == "rt1" and cr == 10 and os.path.getsize(out) > 1000
assert len(S["posts"]) == 2 and "input_task_id" in S["posts"][0][1] and "model_url" in S["posts"][1][1]   # erst Task-ID, dann Rückfall
assert base64.b64decode(S["posts"][1][1]["model_url"].split(",", 1)[1]) == open(glb, "rb").read()
S.update(posts=[], reject_task_id=False, polls=0)
_, _, _, way = client.run_retexture("k", "task-multi", glb, d, dict(prompt="p"), base_url=base, interval=0.01)
assert way == "input_task_id" and len(S["posts"]) == 1
class H401(H):
    def do_POST(self): self._send(401, {"message": "bad key"})
srv2 = http.server.HTTPServer(("127.0.0.1", 0), H401); threading.Thread(target=srv2.serve_forever, daemon=True).start()
try: client.run_retexture("k", "t", glb, d, dict(prompt="p"), base_url="http://127.0.0.1:%d" % srv2.server_port); raise SystemExit("401 nicht erkannt")
except client.MeshyError as ex: assert ex.code == 401
print("OK: Retexture-Tests bestanden")
