# SPDX-License-Identifier: GPL-3.0-or-later
"""
Meshy-Cars: Meshy-API-Client (nur Standardbibliothek, ohne bpy -> separat testbar).

Stand der API: docs.meshy.ai/en/api/multi-image-to-3d und /changelog, gelesen am 2026-11-27.
  POST   /openapi/v1/multi-image-to-3d            -> {"result": "<task_id>"}
  GET    /openapi/v1/multi-image-to-3d/{id}       -> Task (status PENDING|IN_PROGRESS|SUCCEEDED|FAILED|CANCELED, progress, model_urls.glb)
  DELETE /openapi/v1/multi-image-to-3d/{id}       -> 200 (409, wenn IN_PROGRESS)
  Auth: Authorization: Bearer <Key>. 1-4 Bilder (jpg/jpeg/png/webp, <= 20 MB, >= 32 px), erstes Bild = Vorderansicht.
VERALTET (nicht mehr senden): ai_model "meshy-7" (endet 31.12.2026, danach HTTP 400), "meshy-5"/"meshy-4" (eingestellt),
  ultra_mode (-> geometry_resolution), hd_texture (-> texture_resolution), symmetry_mode (ohne Wirkung), is_a_t_pose.
"""
import base64
import json
import mimetypes
import os
import ssl
import time
import urllib.error
import urllib.request

BASE_URL = "https://api.meshy.ai"
ENDPOINT = "/openapi/v1/multi-image-to-3d"
MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
AI_MODELS = ("latest", "meshy-7.1", "meshy-6", "meshy-6-lite")      # "meshy-7" bewusst nicht mehr dabei
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELED")


class MeshyError(Exception):
    """Fehler mit lesbarer Meldung für den Nutzer."""


def _ssl_context():
    return ssl.create_default_context()


def image_to_data_uri(path):
    """Prüft Format/Größe und liefert data:image/...;base64,... (die API nimmt öffentliche URLs oder Data-URIs)."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in ALLOWED_EXT:
        raise MeshyError("Bildformat nicht erlaubt (%s): nur JPG, PNG oder WebP – %s" % (ext or "ohne Endung", os.path.basename(path)))
    if not os.path.isfile(path):
        raise MeshyError("Bild nicht gefunden: %s" % path)
    size = os.path.getsize(path)
    if size > MAX_IMAGE_BYTES:
        raise MeshyError("Bild zu groß (%.1f MB, max. 20 MB): %s" % (size / 1048576, os.path.basename(path)))
    with open(path, "rb") as f:
        raw = f.read()
    return "data:%s;base64,%s" % (ALLOWED_EXT[ext], base64.b64encode(raw).decode("ascii"))


def build_payload(image_paths, ai_model="meshy-7.1", geometry_resolution="standard", should_texture=True,
                  enable_pbr=True, texture_resolution="2k", texture_prompt="", should_remesh=False,
                  topology="quad", target_polycount=30000, image_enhancement=True, auto_size=False,
                  target_formats=("glb",), moderation=False):
    """Request-Body. Reihenfolge der Bilder: erstes = Vorderansicht. Keine veralteten Felder."""
    paths = [p for p in image_paths if p]
    if not 1 <= len(paths) <= 4:
        raise MeshyError("1 bis 4 Bilder nötig (erstes = Vorderansicht).")
    if ai_model == "meshy-7":
        raise MeshyError("Modell 'meshy-7' ist veraltet (endet am 31.12.2026) – bitte 'meshy-7.1' verwenden.")
    if ai_model not in AI_MODELS:
        raise MeshyError("Unbekanntes Modell: %s" % ai_model)
    if geometry_resolution == "2k" and ai_model in ("meshy-6", "meshy-6-lite"):
        raise MeshyError("Geometrie '2k' (Ultra) braucht meshy-7.1 oder latest.")
    p = {
        "image_urls": [image_to_data_uri(x) for x in paths],
        "ai_model": ai_model,
        "geometry_resolution": geometry_resolution,
        "should_texture": bool(should_texture),
        "should_remesh": bool(should_remesh),
        "target_formats": list(target_formats),
        "auto_size": bool(auto_size),
        "moderation": bool(moderation),
    }
    if should_texture:
        p["enable_pbr"] = bool(enable_pbr)
        p["texture_resolution"] = texture_resolution
        if texture_prompt.strip():
            p["texture_prompt"] = texture_prompt.strip()[:800]
    if should_remesh:                              # topology/target_polycount wirken nur mit Remesh
        p["topology"] = topology
        p["target_polycount"] = int(max(100, min(300000, target_polycount)))
    if ai_model != "meshy-6-lite":                 # image_enhancement mit meshy-6-lite -> HTTP 400
        p["image_enhancement"] = bool(image_enhancement)
    return p


class MeshyClient:
    def __init__(self, key, base_url=BASE_URL, timeout=120):
        if not key:
            raise MeshyError("Kein Meshy-API-Key. Key in den Add-on-Preferences eintragen (oder Umgebungsvariable MESHY_API_KEY).")
        self.key, self.base, self.timeout = key, base_url.rstrip("/"), timeout

    def _call(self, method, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self.key, "Content-Type": "application/json", "User-Agent": "MeshyCars"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=_ssl_context()) as r:
                body = r.read().decode("utf-8") or "{}"
                return json.loads(body)
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")[:400]
            except Exception:  # noqa: BLE001
                body = ""
            raise MeshyError(self._explain(e.code, body))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise MeshyError("Keine Verbindung / Zeitüberschreitung: %s" % getattr(e, "reason", e))

    @staticmethod
    def _explain(code, body):
        if code == 401:
            return "API-Key ungültig (HTTP 401). Key in den Preferences prüfen."
        if code == 402:
            return "Kein Guthaben bzw. kein bezahlter Plan (HTTP 402) – Multi-Image-to-3D braucht einen Bezahl-Plan mit Credits."
        if code == 403:
            return "Von der Moderation blockiert oder keine Berechtigung (HTTP 403): %s" % body
        if code == 429:
            return "Zu viele Anfragen (HTTP 429). Später erneut versuchen."
        if code == 409:
            return "Task läuft bereits (HTTP 409) und lässt sich nicht löschen."
        return "Meshy-Fehler HTTP %d: %s" % (code, body)

    def create(self, payload):
        r = self._call("POST", ENDPOINT, payload)
        tid = r.get("result")
        if not tid:
            raise MeshyError("Meshy lieferte keine Task-ID: %s" % r)
        return tid

    def get(self, task_id):
        return self._call("GET", "%s/%s" % (ENDPOINT, task_id))

    def delete(self, task_id):
        return self._call("DELETE", "%s/%s" % (ENDPOINT, task_id))

    def wait(self, task_id, progress=None, cancelled=None, interval=4.0, max_seconds=1800):
        """Pollt bis SUCCEEDED. progress(0..1, Text); cancelled() -> bool. Liefert das Task-Objekt."""
        t0 = time.time()
        while True:
            if cancelled and cancelled():
                try:
                    self.delete(task_id)
                except MeshyError:
                    pass
                raise MeshyError("Abgebrochen.")
            t = self.get(task_id)
            st = t.get("status")
            if progress:
                txt = {"PENDING": "wartet in der Warteschlange", "IN_PROGRESS": "Meshy erzeugt das Auto"}.get(st, st or "?")
                progress(min(0.95, (t.get("progress") or 0) / 100.0), "%s (%s %%)" % (txt, t.get("progress", 0)))
            if st == "SUCCEEDED":
                return t
            if st in ("FAILED", "CANCELED"):
                err = (t.get("task_error") or {}).get("message") or st
                raise MeshyError("Meshy-Task %s: %s" % (st, err))
            if time.time() - t0 > max_seconds:
                raise MeshyError("Zeitüberschreitung (>%d min). Task-ID %s im Meshy-Dashboard prüfen." % (max_seconds // 60, task_id))
            time.sleep(interval)


def download(url, dest, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "MeshyCars"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise MeshyError("Download fehlgeschlagen (Links laufen ab): %s" % getattr(e, "reason", e))
    if os.path.getsize(dest) < 1000:
        raise MeshyError("Heruntergeladene Datei zu klein – kein gültiges Modell.")
    return dest


def run_job(key, image_paths, out_dir, options, progress=None, cancelled=None, base_url=BASE_URL, interval=4.0):
    """Komplett-Ablauf (läuft im Hintergrund-Thread): Task anlegen, warten, GLB laden. Liefert (glb_pfad, task_id, credits)."""
    client = MeshyClient(key, base_url)
    payload = build_payload(image_paths, **options)
    if progress:
        progress(0.01, "Bilder werden zu Meshy hochgeladen …")
    tid = client.create(payload)
    task = client.wait(tid, progress, cancelled, interval)
    url = (task.get("model_urls") or {}).get("glb")
    if not url:
        raise MeshyError("Task fertig, aber ohne GLB-Link (target_formats prüfen).")
    os.makedirs(out_dir, exist_ok=True)
    if progress:
        progress(0.97, "Lade GLB …")
    glb = download(url, os.path.join(out_dir, "meshy_car_%s.glb" % tid))
    return glb, tid, task.get("consumed_credits")
