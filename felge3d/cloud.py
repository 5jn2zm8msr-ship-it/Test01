# SPDX-License-Identifier: GPL-3.0-or-later
"""
Optionale Cloud-Erzeugung des 3D-Meshes (Provider-Klassen, damit weitere Anbieter ergänzt werden können).

Sicherheit: Der API-Key steht NUR in den Add-on-Preferences (maskiert), nie im Code, in der .blend oder im Repo.
Der Aufruf läuft in einem Hintergrund-Thread; Blender friert nicht ein. Die Generierung ist kostenpflichtig (Credits beim Anbieter).

Stand der Tripo-Anbindung (v3, Quelle: developers.tripo3d.com über Suchergebnisse, die Doku-Seiten selbst waren nicht erreichbar):
  Auth:    Authorization: Bearer <Key>
  Erzeugen: POST  <BASE>/generation/image-to-model        (Eingabe: Feld "input")
  Status:   GET   <BASE>/tasks/{task_id}                  (status: success | failed | cancelled | …; output.model_url)
  NICHT geprüft: der Bild-Upload (POST <BASE>/files/upload-credentials) und die Fehlercodes – siehe TripoProvider._upload.
"""
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request


class CloudError(Exception):
    """Fehler mit lesbarer Meldung für den Nutzer (status/body: HTTP-Status und Antworttext, falls vorhanden)."""

    def __init__(self, message, status=None, body="", retry_after=None):
        super().__init__(message)
        self.status, self.body, self.retry_after = status, body, retry_after


def _ssl_context():
    try:
        from . import updater
        return updater._ssl_context()
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def http_json(method, url, key, payload=None, timeout=60, with_headers=False):
    """JSON-Aufruf mit Bearer-Key; übersetzt Fehler in CloudError (ungültiger Key, kein Guthaben, Limit, Timeout)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "RimGenerator"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
            data = json.loads(r.read().decode("utf-8") or "{}")
            return (data, dict(r.headers.items())) if with_headers else data
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        low = body.lower()
        try:
            ra = float(e.headers.get("Retry-After")) if e.headers and e.headers.get("Retry-After") else None
        except (TypeError, ValueError):
            ra = None
        if e.code in (401, 403) or "invalid" in low and "key" in low:
            raise CloudError("API-Key ungültig oder ohne Berechtigung (HTTP %d). Key in den Add-on-Preferences prüfen." % e.code, e.code, body)
        if e.code == 402 or "credit" in low or "balance" in low:
            raise CloudError("Kein Guthaben beim Anbieter (HTTP %d). Bitte Credits aufladen." % e.code, e.code, body)
        if e.code == 429:
            raise CloudError("Zu viele Anfragen (Limit erreicht). Später erneut versuchen.", e.code, body, ra)
        raise CloudError("Anbieter-Fehler HTTP %d: %s" % (e.code, body or e.reason), e.code, body)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CloudError("Keine Verbindung / Zeitüberschreitung: %s" % getattr(e, "reason", e))


def download(url, dest, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "RimGenerator"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r, open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise CloudError("Download des Modells fehlgeschlagen (die Links laufen nach kurzer Zeit ab): %s" % getattr(e, "reason", e))
    if os.path.getsize(dest) < 1000:
        raise CloudError("Heruntergeladene Datei ist zu klein – kein gültiges Modell.")
    return dest


class Provider:
    """Basisklasse: generate() liefert den Pfad einer GLB-Datei. progress(0..1, Text); cancel = threading.Event."""
    key = "BASE"
    label = "Anbieter"
    cost_note = "Die Generierung ist kostenpflichtig (Credits des Anbieters)."

    def __init__(self, api_key, options=None):
        self.api_key = api_key
        self.options = dict(options or {})          # anbieterspezifische Einstellungen (nie den Key hier ablegen)

    def estimate_credits(self):
        """Geschätzte Kosten je Aufruf in Credits (None = unbekannt), nach der Preistabelle des Anbieters."""
        return None

    def balance(self):
        """Guthaben in Credits (None = nicht abfragbar)."""
        return None

    def generate(self, image_path, out_dir, progress, cancel):
        raise NotImplementedError


class TripoProvider(Provider):
    key = "TRIPO"
    label = "Tripo"
    BASE = "https://openapi.tripo3d.com/v3"
    POLL_S = 4.0
    TIMEOUT_S = 600.0
    cost_note = "Tripo berechnet Credits von deinem Konto pro Generierung (aktuelle Preise: Tripo-Preisseite)."

    def _upload(self, image_path):
        """
        Bild hochladen und die Eingabe-Kennung für das Feld "input" liefern.
        Laut Changelog gibt es dafür POST /v3/files/upload-credentials; Ablauf und Felder konnten wegen gesperrtem Zugriff auf die
        Doku NICHT geprüft werden – bewusst nicht aus dem Gedächtnis geraten (Kosten!). Sobald die Doku vorliegt, nur hier ergänzen.
        """
        raise CloudError("Der Bild-Upload für Tripo ist noch nicht gegen die offizielle Doku geprüft und deshalb gesperrt.")

    def generate(self, image_path, out_dir, progress, cancel):
        progress(0.02, "Bild hochladen")
        ref = self._upload(image_path)
        progress(0.10, "Auftrag senden")
        res = http_json("POST", self.BASE + "/generation/image-to-model", self.api_key, {"input": ref})
        task_id = (res.get("data") or res).get("task_id") or res.get("id")
        if not task_id:
            raise CloudError("Antwort ohne Task-ID: %s" % json.dumps(res)[:200])
        t0 = time.time()
        while True:
            if cancel.is_set():
                raise CloudError("Abgebrochen.")
            if time.time() - t0 > self.TIMEOUT_S:
                raise CloudError("Zeitüberschreitung: Der Anbieter hat nach %d s kein Ergebnis geliefert (Task %s)." % (self.TIMEOUT_S, task_id))
            st = http_json("GET", "%s/tasks/%s" % (self.BASE, task_id), self.api_key)
            d = st.get("data") or st
            status = str(d.get("status", "")).lower()
            progress(0.10 + 0.8 * float(d.get("progress", 0) or 0) / 100.0, "Tripo: %s" % status)
            if status in ("success", "succeeded"):
                url = ((d.get("output") or {}).get("model_url")) or (d.get("output") or {}).get("model")
                if not url:
                    raise CloudError("Fertig, aber ohne Modell-Link in der Antwort.")
                progress(0.92, "Modell laden")
                return download(url, os.path.join(out_dir, "cloud_%s.glb" % task_id))
            if status in ("failed", "cancelled", "canceled", "banned", "expired", "unknown"):
                raise CloudError("Der Anbieter meldet: %s." % status)
            time.sleep(self.POLL_S)


class MeshyProvider(Provider):
    """
    Meshy (https://docs.meshy.ai, Stand der Doku: llms-full.txt vom 25.11.2026).
    Image to 3D (Standard, nur Mesh ohne Textur: should_texture=false), optional Multi-Image to 3D (Front + weitere Ansichten) und
    optional Remesh. Auth: „Authorization: Bearer msy_…“. Alle Zeitstempel der API sind Millisekunden.
    Regeln aus der Doku, die hier befolgt werden: Create bei Timeout/5xx NIE automatisch erneut senden (kein Idempotenz-Schlüssel, Task kann
    existieren); Polling mit Retry-After (sonst 5 s); mindestens 60 Minuten ab created_at warten; Dateien sofort laden (Links signiert,
    Assets max. 3 Tage); nur FAILED heißt gescheitert (Credits werden erstattet).
    """
    key = "MESHY"
    label = "Meshy"
    BASE = "https://api.meshy.ai/openapi"
    POLL_S = 5.0
    TIMEOUT_S = 3600.0
    # Credits für „nur Mesh“ je ai_model (Preistabelle „API pricing → 3D generation“); Remesh: 5; Ultra-Geometrie: +5
    # NUR für die Kostenanzeige (Doku-Stand 25.11.2026). Ein Modell, das hier fehlt, wird trotzdem gesendet; die API antwortet bei
    # einem ungültigen Modell mit 400 und _model_error übersetzt das. „meshy-7“ ist veraltet (Abschaltung 31.12.2026), gilt aber noch.
    MESH_CREDITS = {"latest": 20, "meshy-7.1": 20, "meshy-7": 20, "meshy-6": 20, "meshy-6-lite": 5, "meshy-t2": 5, "meshy-t2.5": 5}
    MULTI_MODELS = ("latest", "meshy-7.1", "meshy-6", "meshy-6-lite", "meshy-7")   # Multi-Image to 3D laut Doku; nur für die Kostenanzeige
    REMESH_CREDITS = 5
    SMART = ("meshy-t2", "meshy-t2.5")              # Smart-Topology-Modelle brauchen model_type "smart-topology" (nur Image to 3D)
    cost_note = "Meshy berechnet Credits von deinem Konto pro Generierung (Mesh ohne Textur: je nach Modell 5–20 Credits, Remesh +5)."

    def _opt(self, name, default=None):
        v = self.options.get(name)
        return default if v in (None, "") else v

    def _multi(self):
        return bool(self.options.get("extra_images"))

    def estimate_credits(self):
        model = str(self._opt("ai_model", "latest"))
        base = self.MESH_CREDITS.get(model)
        if base is None or (self._multi() and model not in self.MULTI_MODELS):
            return None
        return base + (self.REMESH_CREDITS if self._opt("remesh") else 0)

    def _call(self, method, path, payload=None, timeout=60, with_headers=False):
        return http_json(method, self.BASE + path, self.api_key, payload, timeout=timeout, with_headers=with_headers)

    def balance(self):
        """GET /v1/balance (kostenlos) -> Feld `balance`."""
        d = self._call("GET", "/v1/balance")
        return int(d.get("balance", 0))

    @staticmethod
    def _data_uri(path):
        ext = os.path.splitext(path)[1].lower()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(ext)
        if mime is None:
            raise CloudError("Meshy nimmt nur JPG, PNG oder WebP (Datei: %s)." % os.path.basename(path))
        if os.path.getsize(path) > 20 * 1024 * 1024:
            raise CloudError("Das Bild ist größer als 20 MB (Grenze von Meshy).")
        import base64
        with open(path, "rb") as fh:
            return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode("ascii"))

    def _model_error(self, e, model, create_path=""):
        """400 wegen unbekanntem/abgeschaltetem Modell: klare Meldung (Doku: abgeschaltete Modelle liefern 400)."""
        text = (e.body or str(e)).lower()
        if create_path != "/v1/remesh" and e.status == 400 and ("model" in text or "retired" in text or "deprecated" in text):
            return CloudError("Meshy akzeptiert das Modell „%s“ nicht (mehr): %s. In den Add-on-Preferences ein anderes Modell eintragen "
                              "(z. B. „latest“; aktuelle Liste: docs.meshy.ai/api/models)." % (model, (e.body or str(e))[:200]), e.status, e.body)
        return e

    def _create(self, path, payload, model):
        try:
            res = self._call("POST", path, payload, timeout=120)
        except CloudError as e:
            if e.status is None:                                   # Timeout/Verbindung: Task kann trotzdem existieren -> NICHT erneut senden
                raise CloudError("Keine sichere Antwort von Meshy (%s). Der Auftrag kann trotzdem angelegt und berechnet sein – bitte im "
                                 "Meshy-Konto (Tasks) nachsehen und nicht automatisch erneut senden." % e)
            if e.status >= 500:
                raise CloudError("Meshy-Serverfehler (HTTP %d). Der Auftrag kann trotzdem angelegt sein – im Meshy-Konto nachsehen, "
                                 "bevor du erneut startest." % e.status, e.status, e.body)
            raise self._model_error(e, model, path)
        tid = res.get("result")
        if not tid:
            raise CloudError("Antwort ohne Task-ID: %s" % json.dumps(res)[:200])
        return str(tid)

    MAX_POLL_FAILS = 8

    @staticmethod
    def _sleep(seconds, cancel):
        end = time.time() + seconds
        while time.time() < end and not cancel.is_set():
            time.sleep(min(0.25, max(0.0, end - time.time())))

    def _wait(self, path, tid, progress, cancel, label, p0, p1):
        t0 = time.time()
        fails = 0
        while True:
            if cancel.is_set():
                raise CloudError("Abgebrochen (der bereits gestartete Meshy-Auftrag läuft weiter und ist berechnet).")
            if time.time() - t0 > self.TIMEOUT_S:
                raise CloudError("Nach %d Minuten kein Ergebnis (Task %s). Er läuft beim Anbieter weiter – im Meshy-Konto nachsehen." % (self.TIMEOUT_S // 60, tid))
            try:
                d, hdr = self._call("GET", "%s/%s" % (path, tid), with_headers=True)
                fails = 0
            except CloudError as e:
                # 429 und Verbindungsfehler: der Task läuft (und ist berechnet) weiter -> warten und erneut fragen, nicht aufgeben
                if e.status not in (None, 429) and not (e.status and e.status >= 500) or fails >= self.MAX_POLL_FAILS:
                    raise CloudError("%s (Task-ID %s: läuft ggf. weiter und ist berechnet – im Meshy-Konto unter Tasks nachsehen)" % (e, tid), e.status, e.body)
                fails += 1
                self._sleep(e.retry_after or min(self.POLL_S * (2 ** fails), 60.0), cancel)
                continue
            st = str(d.get("status", "")).upper()
            progress(p0 + (p1 - p0) * float(d.get("progress", 0) or 0) / 100.0, "%s: %s" % (label, st.lower()))
            if st == "SUCCEEDED":
                return d
            if st in ("FAILED", "CANCELED"):
                te = d.get("task_error") or {}
                raise CloudError("Meshy meldet %s: %s%s (Credits werden erstattet)." % (
                    st, te.get("message", "kein Grund angegeben"), (" [%s]" % te["code"]) if te.get("code") else ""))
            wait = self.POLL_S
            try:
                wait = max(1.0, float(hdr.get("Retry-After", hdr.get("retry-after", wait))))
            except (TypeError, ValueError):
                pass
            self._sleep(wait, cancel)

    def generate(self, image_path, out_dir, progress, cancel):
        model = str(self._opt("ai_model", "latest"))
        extra = [p for p in (self.options.get("extra_images") or []) if p]
        progress(0.02, "Bild vorbereiten")
        main_uri = self._data_uri(image_path)
        if extra:                                                  # Multi-Image to 3D: erstes Bild = Vorderansicht, 1–4 Bilder
            uris = [main_uri] + [self._data_uri(p) for p in extra][:3]
            path, payload = "/v1/multi-image-to-3d", {"image_urls": uris, "ai_model": model}
        else:
            path, payload = "/v1/image-to-3d", {"image_url": main_uri, "ai_model": model}
            if model in self.SMART:
                payload["model_type"] = "smart-topology"
        payload.update(should_texture=False, target_formats=["glb"])                # nur Mesh, eigene Materialien
        progress(0.08, "Auftrag senden")
        tid = self._create(path, payload, model)
        remesh = bool(self._opt("remesh"))
        d = self._wait(path, tid, progress, cancel, "Meshy", 0.10, 0.60 if remesh else 0.90)
        url = (d.get("model_urls") or {}).get("glb")
        if remesh:
            rp = {"input_task_id": tid, "target_formats": ["glb"], "topology": str(self._opt("topology", "quad")),
                  "target_polycount": int(self._opt("polycount", 30000))}
            progress(0.62, "Remesh senden")
            try:
                rid = self._create("/v1/remesh", rp, model)
                d = self._wait("/v1/remesh", rid, progress, cancel, "Remesh", 0.64, 0.90)
                url = (d.get("model_urls") or {}).get("glb") or url
            except CloudError as e:
                if cancel.is_set():
                    raise
                progress(0.9, "Remesh fehlgeschlagen – nutze das unbearbeitete Mesh")
                self.warning = "Remesh fehlgeschlagen (%s); das erste (bezahlte) Mesh wurde übernommen." % e
        if not url:
            raise CloudError("Fertig, aber ohne GLB-Link in der Antwort (Feld model_urls.glb fehlt).")
        progress(0.92, "Modell laden")
        return download(url, os.path.join(out_dir, "meshy_%s.glb" % tid))


PROVIDERS = {"TRIPO": TripoProvider, "MESHY": MeshyProvider}


class Job:
    """Hintergrund-Job: Status für die Oberfläche (Blender-Hauptthread liest nur)."""

    def __init__(self, provider, image_path, out_dir):
        self.provider, self.image_path, self.out_dir = provider, image_path, out_dir
        self.cancel = threading.Event()
        self.progress, self.text = 0.0, "Start"
        self.result, self.error, self.done, self.warning = None, None, False, ""
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()

    def _on_progress(self, p, text):
        self.progress, self.text = min(max(p, 0.0), 1.0), text

    def _run(self):
        try:
            self.result = self.provider.generate(self.image_path, self.out_dir, self._on_progress, self.cancel)
            self.warning = getattr(self.provider, "warning", "")
        except CloudError as e:
            self.error = str(e)
        except Exception as e:  # noqa: BLE001
            self.error = "Unerwarteter Fehler: %s" % e
        self.done = True
