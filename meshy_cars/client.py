# SPDX-License-Identifier: GPL-3.0-or-later
"""
Meshy-Cars: Meshy-API-Client (nur Standardbibliothek, ohne bpy -> separat testbar).

Stand der API: docs.meshy.ai/en/api/multi-image-to-3d und /changelog, gelesen am 2026-11-27.
  POST   /openapi/v1/multi-image-to-3d            -> {"result": "<task_id>"}
  GET    /openapi/v1/multi-image-to-3d/{id}       -> Task (status PENDING|IN_PROGRESS|SUCCEEDED|FAILED|CANCELED, progress, model_urls.glb)
  DELETE /openapi/v1/multi-image-to-3d/{id}       -> 200 (409, wenn IN_PROGRESS)
  Auth: Authorization: Bearer <Key>. 1-4 Bilder (jpg/jpeg/png/webp, <= 20 MB, >= 32 px), erstes Bild = Vorderansicht.
  Retexture (docs.meshy.ai/en/api/retexture, 28.11.2026): POST /openapi/v1/retexture {input_task_id | model_url, text_style_prompt (max. 800), enable_original_uv,
    enable_pbr, texture_resolution}; Preis 10 Credits (2K/4K), 15 (8K). Multi-Image-Tasks sind als input_task_id weder erlaubt noch ausgeschlossen -> Rueckfall auf model_url.
  Preise (docs.meshy.ai/en/api/pricing, 27.11.2026): Multi-Image mesh 20 (7.1/6) bzw. 5 (6-lite), Textur 2K/4K +10, 8K +15
  (6-lite: nur 2K, +10), Ultra-Geometrie 2k +5 (nur 7.1/latest). VERALTET (nicht mehr senden): ai_model "meshy-7" (endet 31.12.2026, danach HTTP 400), "meshy-5"/"meshy-4" (eingestellt),
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
BALANCE_ENDPOINT = "/openapi/v1/balance"        # kostenlos (docs.meshy.ai/en/api/balance)
RETEXTURE_ENDPOINT = "/openapi/v1/retexture"
MAX_DATA_URI_BYTES = 100 * 1024 * 1024        # model_url als Data-URI: max. 100 MB
MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
AI_MODELS = ("latest", "meshy-7.1", "meshy-6", "meshy-6-lite")      # "meshy-7" bewusst nicht mehr dabei
TERMINAL = ("SUCCEEDED", "FAILED", "CANCELED")


class MeshyError(Exception):
    """Fehler mit lesbarer Meldung für den Nutzer. code = HTTP-Status (falls vom Server)."""
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


def estimate_credits(ai_model="meshy-7.1", geometry_resolution="standard", should_texture=True, texture_resolution="2k"):
    """Credits eines Multi-Image-Tasks nach der Preisseite (Standard-Texturmodell). Wirft MeshyError bei nicht unterstuetzter Kombination."""
    lite = ai_model == "meshy-6-lite"
    c = 5 if lite else 20
    if should_texture:
        if lite and texture_resolution != "2k":
            raise MeshyError("meshy-6-lite unterstützt nur 2K-Texturen (Preisseite: 4K/8K 'Not supported').")
        c += {"2k": 10, "4k": 10, "8k": 15}[texture_resolution]
    if geometry_resolution == "2k":
        if lite or ai_model == "meshy-6":
            raise MeshyError("Geometrie '2k' (Ultra) braucht meshy-7.1 oder latest.")
        c += 5
    return c


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
                  enable_pbr=True, texture_resolution="2k", texture_prompt="", image_enhancement=True, auto_size=False,
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
    estimate_credits(ai_model, geometry_resolution, should_texture, texture_resolution)     # wirft bei ungueltiger Kombination
    p = {
        "image_urls": [image_to_data_uri(x) for x in paths],
        "ai_model": ai_model,
        "geometry_resolution": geometry_resolution,
        "should_texture": bool(should_texture),
        "target_formats": list(target_formats),
        "auto_size": bool(auto_size),
        "moderation": bool(moderation),
    }
    if should_texture:
        p["enable_pbr"] = bool(enable_pbr)
        p["texture_resolution"] = texture_resolution
        if texture_prompt.strip():
            p["texture_prompt"] = texture_prompt.strip()[:800]
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
            raise MeshyError(self._explain(e.code, body), e.code)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise MeshyError("Keine Verbindung / Zeitüberschreitung: %s" % getattr(e, "reason", e))

    @staticmethod
    def _explain(code, body):
        if code == 401:
            return "API-Key ungültig (HTTP 401). Key in den Preferences prüfen."
        if code == 402:
            return "Kein Guthaben bzw. kein bezahlter Plan (HTTP 402) – die Meshy-API braucht einen Bezahl-Plan mit vorab gekauften API-Credits."
        if code == 403:
            return "Von der Moderation blockiert oder keine Berechtigung (HTTP 403): %s" % body
        if code == 429:
            return "Zu viele Anfragen (HTTP 429). Später erneut versuchen."
        if code == 409:
            return "Task läuft bereits (HTTP 409) und lässt sich nicht löschen."
        return "Meshy-Fehler HTTP %d: %s" % (code, body)

    def balance(self):
        """Guthaben (kostenlos): {'balance', 'monthly_credits', 'permanent_credits', 'monthly_resets_at' (ms oder None)}."""
        return self._call("GET", BALANCE_ENDPOINT)

    def create(self, payload, endpoint=ENDPOINT):
        r = self._call("POST", endpoint, payload)
        tid = r.get("result")
        if not tid:
            raise MeshyError("Meshy lieferte keine Task-ID: %s" % r)
        return tid

    def get(self, task_id, endpoint=ENDPOINT):
        return self._call("GET", "%s/%s" % (endpoint, task_id))

    def delete(self, task_id, endpoint=ENDPOINT):
        return self._call("DELETE", "%s/%s" % (endpoint, task_id))

    def wait(self, task_id, progress=None, cancelled=None, interval=4.0, max_seconds=1800, endpoint=ENDPOINT, label="Meshy erzeugt das Auto"):
        """Pollt bis SUCCEEDED. progress(0..1, Text); cancelled() -> bool. Liefert das Task-Objekt."""
        t0 = time.time()
        while True:
            if cancelled and cancelled():
                try:
                    self.delete(task_id, endpoint)
                except MeshyError:
                    pass
                raise MeshyError("Abgebrochen.")
            t = self.get(task_id, endpoint)
            st = t.get("status")
            if progress:
                txt = {"PENDING": "wartet in der Warteschlange", "IN_PROGRESS": label}.get(st, st or "?")
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


def balance_text(info):
    """Kurztext für die Anzeige, z.B. '830 Credits (monatlich 830, dauerhaft 0)'."""
    if not isinstance(info, dict) or "balance" not in info:
        return "Guthaben unbekannt"
    return "%s Credits (monatlich %s, dauerhaft %s)" % (info.get("balance"), info.get("monthly_credits", "?"), info.get("permanent_credits", "?"))


def safe_balance(key, base_url=BASE_URL):
    """Guthaben-Text; Fehler werden zu einem Hinweistext (die Abfrage darf einen fertigen Lauf nie scheitern lassen)."""
    try:
        return balance_text(MeshyClient(key, base_url).balance())
    except MeshyError as e:
        return "Guthaben nicht abrufbar (%s)" % e


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



def retexture_credits(texture_resolution="2k"):
    """Credits eines Retexture-Tasks (Preisseite 28.11.2026: 2K/4K = 10, 8K = 15)."""
    return 15 if texture_resolution == "8k" else 10


def build_retexture_payload(prompt, input_task_id=None, glb_path=None, texture_resolution="2k", enable_pbr=True):
    """Retexture-Body: Form bleibt (enable_original_uv). Kein ai_model (Doku nennt meshy-7.1 hier nicht; Standard 'latest'), keine veralteten Felder."""
    if not prompt.strip():
        raise MeshyError("Textur-Beschreibung fehlt (z.B. 'glossy graphite metallic car paint').")
    if texture_resolution not in ("2k", "4k", "8k"):
        raise MeshyError("Textur-Auflösung muss 2k, 4k oder 8k sein.")
    p = {"text_style_prompt": prompt.strip()[:800], "enable_original_uv": True, "enable_pbr": bool(enable_pbr),
         "texture_resolution": texture_resolution, "target_formats": ["glb"]}
    if input_task_id:
        p["input_task_id"] = input_task_id
    elif glb_path:
        if not os.path.isfile(glb_path):
            raise MeshyError("GLB nicht gefunden: %s" % glb_path)
        if os.path.getsize(glb_path) > MAX_DATA_URI_BYTES:
            raise MeshyError("GLB größer als 100 MB – als Data-URI nicht sendbar.")
        with open(glb_path, "rb") as f:
            p["model_url"] = "data:application/octet-stream;base64," + base64.b64encode(f.read()).decode("ascii")
    else:
        raise MeshyError("Retexture braucht input_task_id oder eine GLB-Datei.")
    return p


def run_retexture(key, input_task_id, glb_path, out_dir, options, progress=None, cancelled=None, base_url=BASE_URL, interval=4.0):
    """Neue Textur fuer ein fertiges Auto. Erst mit input_task_id; lehnt Meshy ab (HTTP 400), Rueckfall auf die lokale GLB als model_url.
    Liefert (glb_pfad, task_id, credits, benutzter_weg)."""
    client = MeshyClient(key, base_url)
    way = "input_task_id"
    if progress:
        progress(0.01, "Retexture wird gestartet …")
    try:
        if not input_task_id:
            raise MeshyError("keine Task-ID", 400)
        tid = client.create(build_retexture_payload(input_task_id=input_task_id, **options), RETEXTURE_ENDPOINT)
    except MeshyError as e:
        if e.code != 400 or not glb_path:
            raise
        way = "model_url"
        if progress:
            progress(0.02, "Task-ID abgelehnt – lade lokale GLB hoch …")
        tid = client.create(build_retexture_payload(glb_path=glb_path, **options), RETEXTURE_ENDPOINT)
    task = client.wait(tid, progress, cancelled, interval, endpoint=RETEXTURE_ENDPOINT, label="Meshy texturiert neu")
    url = (task.get("model_urls") or {}).get("glb")
    if not url:
        raise MeshyError("Retexture fertig, aber ohne GLB-Link.")
    os.makedirs(out_dir, exist_ok=True)
    if progress:
        progress(0.97, "Lade GLB …")
    return download(url, os.path.join(out_dir, "meshy_car_retex_%s.glb" % tid)), tid, task.get("consumed_credits"), way
