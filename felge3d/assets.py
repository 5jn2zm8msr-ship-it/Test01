# SPDX-License-Identifier: GPL-3.0-or-later
"""
Mitgelieferte 3D-Objekte (derzeit Reifen): liegen als GLB unter felge3d/assets/reifen/ im Add-on, Liste in reifen.json.
Beim ersten Gebrauch wird der Reifen einmal in eine verborgene Collection importiert und danach wiederverwendet
(Mesh und Material nicht doppelt laden).

CREDITS (Namensnennung nach CC BY 4.0, Pflicht bei Weitergabe):
  Mitgelieferter Reifen „car tyre game ready p zero“ (https://skfb.ly/oNqAJ) von Iftekhar.Tushar,
  Lizenz Creative Commons Attribution 4.0 (http://creativecommons.org/licenses/by/4.0/).
  Änderungen: nur der Reifen aus dem Gesamtmodell herausgelöst, neu exportiert, beim Bau an Größe und Drehung angepasst.
  Mitgelieferte Reifen „[FREE] Sport Tire Pack - by SDC“ (https://sketchfab.com/3d-models/free-sport-tire-pack-by-sdc-07ffafa14c0348738edff992999511f9)
  von SDC PERFORMANCE (Pirelli P Zero Sport, Pirelli P Zero Trofeo R, Yokohama Advan Drift, Pirelli F1 Slick), Lizenz CC BY 4.0
  (http://creativecommons.org/licenses/by/4.0/). Änderungen: je Reifen herausgelöst, Mesh auf ca. 60 000 Flächen ausgedünnt, neu exportiert,
  beim Bau an Größe und Drehung angepasst (tools/extract_tyre_pack.py).
  Alle Angaben stehen auch in assets/reifen/reifen.json und assets/reifen/QUELLE.md und in den Add-on-Preferences.
"""
import json
import os

import bpy

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "reifen")
INDEX = os.path.join(DIR, "reifen.json")
PREFIX = "Rim Generator | Reifen (mitgeliefert) "


def tyre_list():
    """Liste der mitgelieferten Reifen: [{id, name, datei, ...}] (leer, wenn der Ordner fehlt)."""
    try:
        with open(INDEX, encoding="utf-8") as f:
            items = json.load(f).get("reifen", [])
    except (OSError, ValueError):
        return []
    return [t for t in items if os.path.isfile(os.path.join(DIR, t.get("datei", "")))]


def tyre_entry(tid):
    return next((t for t in tyre_list() if t["id"] == tid), None)


def ensure_tyre(tid):
    """Hidden-Collection mit dem Reifen (einmal importiert). Gibt (Collection, Meshes) zurück; wirft RuntimeError."""
    from . import fbx
    t = tyre_entry(tid)
    if t is None:
        raise RuntimeError("Mitgelieferter Reifen ‚%s‘ nicht gefunden (Ordner assets/reifen fehlt oder Update unvollständig)." % tid)
    col = bpy.data.collections.get(PREFIX + tid)
    if col is not None:
        meshes = [o for o in col.all_objects if o.type == "MESH" and len(o.data.vertices) > 0]
        if meshes:
            return col, meshes
        bpy.data.collections.remove(col)
    new, meshes = fbx.import_file(os.path.join(DIR, t["datei"]))
    col = bpy.data.collections.new(PREFIX + tid)
    bpy.context.scene.collection.children.link(col)
    for o in new:
        for oc in list(o.users_collection):
            oc.objects.unlink(o)
        col.objects.link(o)
    col.hide_viewport = True
    col.hide_render = True
    col["felge3d_asset"] = tid
    return col, meshes


def credit_lines(t):
    """Namensnennung (CC BY): Titel, Autor, Quelle, Lizenz, Änderungen – als Textzeilen für die Oberfläche."""
    if not t:
        return []
    return ["„%s“ von %s" % (t.get("titel", t.get("name", "")), t.get("autor", "?")),
            "Lizenz: %s (%s)" % (t.get("lizenz", "?"), t.get("lizenz_url", "")),
            "Quelle: %s" % t.get("quelle_url", ""),
            "Änderungen: %s" % t.get("aenderungen", "keine")]


def all_credits():
    """Credits aller mitgelieferten Objekte (für die Preferences)."""
    out = []
    for t in tyre_list():
        out += credit_lines(t) + [""]
    return out
