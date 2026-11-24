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
    """Fehler mit lesbarer Meldung für den Nutzer."""


def _ssl_context():
    try:
        from . import updater
        return updater._ssl_context()
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def http_json(method, url, key, payload=None, timeout=60):
    """JSON-Aufruf mit Bearer-Key; übersetzt Fehler in CloudError (ungültiger Key, kein Guthaben, Limit, Timeout)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "RimGenerator"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        low = body.lower()
        if e.code in (401, 403) or "invalid" in low and "key" in low:
            raise CloudError("API-Key ungültig oder ohne Berechtigung (HTTP %d). Key in den Add-on-Preferences prüfen." % e.code)
        if e.code == 402 or "credit" in low or "balance" in low:
            raise CloudError("Kein Guthaben beim Anbieter (HTTP %d). Bitte Credits aufladen." % e.code)
        if e.code == 429:
            raise CloudError("Zu viele Anfragen (Limit erreicht). Später erneut versuchen.")
        raise CloudError("Anbieter-Fehler HTTP %d: %s" % (e.code, body or e.reason))
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

    def __init__(self, api_key):
        self.api_key = api_key

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


PROVIDERS = {"TRIPO": TripoProvider}


class Job:
    """Hintergrund-Job: Status für die Oberfläche (Blender-Hauptthread liest nur)."""

    def __init__(self, provider, image_path, out_dir):
        self.provider, self.image_path, self.out_dir = provider, image_path, out_dir
        self.cancel = threading.Event()
        self.progress, self.text = 0.0, "Start"
        self.result, self.error, self.done = None, None, False
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()

    def _on_progress(self, p, text):
        self.progress, self.text = min(max(p, 0.0), 1.0), text

    def _run(self):
        try:
            self.result = self.provider.generate(self.image_path, self.out_dir, self._on_progress, self.cancel)
        except CloudError as e:
            self.error = str(e)
        except Exception as e:  # noqa: BLE001
            self.error = "Unerwarteter Fehler: %s" % e
        self.done = True
