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


def _get(url, token="", accept=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Felge3D-Updater"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
        return r.read()


def parse_version(text):
    m = re.search(r'"version"\s*:\s*\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)', text)
    return tuple(int(x) for x in m.groups()) if m else None


def remote_version(repo, branch="main", token=""):
    """Liest bl_info['version'] aus <repo>/felge3d/__init__.py auf GitHub."""
    url = "https://api.github.com/repos/%s/contents/%s/__init__.py?ref=%s" % (repo, PKG, branch)
    raw = _get(url, token, accept="application/vnd.github.raw")
    return parse_version(raw.decode("utf-8", "replace"))


def install_latest(repo, branch="main", token=""):
    """Lädt das Repo als ZIP und ersetzt die .py/.toml-Dateien des Add-ons. Gibt Liste der Dateien zurück."""
    url = "https://api.github.com/repos/%s/zipball/%s" % (repo, branch)
    data = _get(url, token, timeout=60)
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
        if "/" in rel or not rel.endswith((".py", ".toml")):
            continue
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
    if "CERTIFICATE" in msg.upper():
        return "SSL-Zertifikat konnte nicht geprüft werden (macOS: Blender-Python ohne Zertifikate)."
    return msg
