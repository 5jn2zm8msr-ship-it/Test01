# SPDX-License-Identifier: GPL-3.0-or-later
"""
Selbst-Update von GitHub: prüft die Version im Repository und ersetzt die Add-on-Dateien.

Erwartete Repo-Struktur:  <repo>/felge3d/__init__.py  (+ core.py, updater.py, ...)
Öffentliches Repo: kein Token nötig. Privates Repo: Token mit Leserecht ("Contents: read").
"""
import io
import json
import os
import re
import ssl
import urllib.request
import zipfile

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
PKG = "felge3d"


def _ssl_context():
    ctx = ssl.create_default_context()
    try:  # macOS-Blender findet die System-Zertifikate nicht immer -> certifi, falls vorhanden
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001
        pass
    return ctx


def _get_once(url, token="", accept=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Felge3D-Updater"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return r.read()


def _get(url, token="", accept=None, timeout=20, tries=3):
    """Mit Wiederholung bei Zeitüberschreitung / 5xx (z.B. 504 Gateway Time-out)."""
    import time
    last = None
    for i in range(tries):
        try:
            return _get_once(url, token, accept, timeout)
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e)
            if any(c in msg for c in ("401", "403", "404")):
                raise
            time.sleep(1.5 * (i + 1))
    raise last


def _first_ok(urls, **kw):
    """Probiert mehrere Adressen nacheinander (API, dann direkte Download-Server)."""
    last = None
    for u, extra in urls:
        try:
            return _get(u, **dict(kw, **extra))
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def parse_version(text):
    m = re.search(r'"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)', text)
    return tuple(int(x) for x in m.groups()) if m else None


def remote_version(repo, branch="main", token=""):
    """Liest bl_info['version'] aus <repo>/felge3d/__init__.py auf GitHub."""
    import time
    urls = [
        # ?t=… umgeht den Zwischenspeicher von raw.githubusercontent.com (sonst bis 5 min alte Version)
        ("https://raw.githubusercontent.com/%s/%s/%s/__init__.py?t=%d" % (repo, branch, PKG, int(time.time())), {}),
        ("https://api.github.com/repos/%s/contents/%s/__init__.py?ref=%s" % (repo, PKG, branch),
         {"accept": "application/vnd.github.raw"}),
    ]
    if token:  # privates Repo: nur über die API mit Token
        urls = urls[1:]
    # Alle Quellen fragen und die höchste Version nehmen: das schnelle CDN (raw) kann nach einem Upload
    # einige Minuten die alte Datei liefern, die API ist aktuell, aber manchmal langsam.
    found, last = [], None
    for url, extra in urls:
        try:
            v = parse_version(_get(url, **dict({"token": token}, **extra)).decode("utf-8", "replace"))
            if v:
                found.append(v)
        except Exception as e:  # noqa: BLE001
            last = e
    if not found:
        raise last or RuntimeError("Version nicht lesbar")
    return max(found)


def install_latest(repo, branch="main", token=""):
    """Lädt das Repo als ZIP und ersetzt die .py/.toml-Dateien des Add-ons. Gibt Liste der Dateien zurück."""
    urls = [
        ("https://codeload.github.com/%s/zip/refs/heads/%s" % (repo, branch), {}),
        ("https://github.com/%s/archive/refs/heads/%s.zip" % (repo, branch), {}),
        ("https://api.github.com/repos/%s/zipball/%s" % (repo, branch), {}),
    ]
    if token:
        urls = urls[2:]
    data = _first_ok(urls, token=token, timeout=90)
    zf = zipfile.ZipFile(io.BytesIO(data))
    prefix = None
    for name in zf.namelist():
        parts = name.split("/")
        if len(parts) >= 3 and parts[-2] == PKG and parts[-1] == "__init__.py":
            prefix = "/".join(parts[:-1]) + "/"
            break
    if prefix is None:
        raise RuntimeError("Im Repository wurde kein Ordner '%s/' mit __init__.py gefunden." % PKG)
    written = []
    for name in zf.namelist():
        if not name.startswith(prefix) or name.endswith("/"):
            continue
        rel = name[len(prefix):]
        is_tex = rel.startswith("textures/") and rel.count("/") == 1 and rel.lower().endswith((".jpg", ".jpeg", ".png", ".json"))
        if not is_tex and ("/" in rel or not rel.endswith((".py", ".toml"))):
            continue
        os.makedirs(os.path.dirname(os.path.join(ADDON_DIR, rel)), exist_ok=True)
        tmp = os.path.join(ADDON_DIR, rel + ".tmp")
        with open(tmp, "wb") as f:
            f.write(zf.read(name))
        os.replace(tmp, os.path.join(ADDON_DIR, rel))
        written.append(rel)
    return written


def describe_error(e):
    msg = str(e)
    if "401" in msg or "403" in msg:
        return "Kein Zugriff (privates Repo? Token in den Add-on-Einstellungen eintragen)."
    if "404" in msg:
        return "Repository oder Branch nicht gefunden – Namen in den Add-on-Einstellungen prüfen."
    if "504" in msg or "502" in msg or "503" in msg or "timed out" in msg.lower():
        return "GitHub antwortet gerade nicht (Zeitüberschreitung) – bitte in ein paar Minuten erneut versuchen."
    if "CERTIFICATE" in msg.upper():
        return "SSL-Zertifikat konnte nicht geprüft werden (macOS: Blender-Python ohne Zertifikate)."
    return msg
