"""Test des Meshy-Clients gegen einen lokalen Mock-Server (kein Netz, kein Key, kein Blender nötig).
Aufruf: python -I tests/meshy_cars/test_client.py"""
import base64, http.server, json, os, sys, tempfile, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "meshy_cars"))
import client  # noqa: E402

STATE = {"polls": 0, "body": None, "auth": None, "fail": False}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj=None, raw=None):
        b = raw if raw is not None else json.dumps(obj or {}).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_POST(self):
        STATE["auth"] = self.headers.get("Authorization")
        STATE["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._send(200, {"result": "task123"})
    def do_GET(self):
        if self.path.endswith("/model.glb"):
            return self._send(200, raw=b"glTF" + b"0" * 2000)
        STATE["polls"] += 1
        if STATE["fail"]:
            return self._send(200, {"status": "FAILED", "task_error": {"message": "kaputt"}})
        if STATE["polls"] < 3:
            return self._send(200, {"status": "IN_PROGRESS", "progress": 30 * STATE["polls"]})
        self._send(200, {"status": "SUCCEEDED", "progress": 100, "consumed_credits": 30,
                         "model_urls": {"glb": "http://127.0.0.1:%d/model.glb" % self.server.server_port}})


def main():
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % srv.server_port
    d = tempfile.mkdtemp()
    imgs = []
    for i in range(4):
        p = os.path.join(d, "car%d.png" % i); open(p, "wb").write(b"\x89PNG" + bytes([i]) * 50); imgs.append(p)
    opts = dict(ai_model="meshy-7.1")
    log = []
    glb, tid, cr = client.run_job("k", imgs, d, opts, lambda f, t: log.append(t), base_url=base, interval=0.01)
    b = STATE["body"]
    assert STATE["auth"] == "Bearer k" and tid == "task123" and cr == 30 and os.path.getsize(glb) > 1000
    assert len(b["image_urls"]) == 4 and b["image_urls"][0].startswith("data:image/png;base64,")
    assert base64.b64decode(b["image_urls"][1].split(",", 1)[1])[4] == 1          # Reihenfolge erhalten (Bild 2 an Stelle 2)
    for old in ("symmetry_mode", "ultra_mode", "hd_texture", "is_a_t_pose"):
        assert old not in b, old                                                   # veraltete Felder nie senden
    assert "topology" not in b and "target_polycount" not in b                     # ohne Remesh nicht senden
    assert b["ai_model"] == "meshy-7.1" and b["enable_pbr"] is True and log
    # Fehlerfälle
    for bad, msg in ((dict(ai_model="meshy-7"), "veraltet"), (dict(ai_model="meshy-6", geometry_resolution="2k"), "2k")):
        try: client.build_payload(imgs, **bad); raise SystemExit("kein Fehler: %s" % bad)
        except client.MeshyError as e: assert msg in str(e)
    try: client.build_payload([], ); raise SystemExit("leer akzeptiert")
    except client.MeshyError: pass
    try: client.build_payload(imgs + [imgs[0]]); raise SystemExit(">4 akzeptiert")
    except client.MeshyError: pass
    bad = os.path.join(d, "x.gif"); open(bad, "wb").write(b"GIF")
    try: client.image_to_data_uri(bad); raise SystemExit("gif akzeptiert")
    except client.MeshyError: pass
    assert "image_enhancement" not in client.build_payload(imgs, ai_model="meshy-6-lite")
    assert "should_remesh" not in b and "topology" not in b and "target_polycount" not in b     # kein Remesh: volles Detail
    STATE["fail"] = True
    try: client.run_job("k", imgs, d, opts, base_url=base, interval=0.01); raise SystemExit("FAILED nicht erkannt")
    except client.MeshyError as e: assert "kaputt" in str(e)
    print("OK: Meshy-Client-Tests bestanden")


main()
