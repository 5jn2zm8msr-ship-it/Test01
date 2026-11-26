# SPDX-License-Identifier: GPL-3.0-or-later
"""
Meshy-Mesh (Image to 3D, nur Mesh, ai_model "latest") je Foto erzeugen und in out/meshy/<key>.glb ablegen.
Kostet Credits (mit Textur ca. 30, nur Mesh 20 je Foto). Existiert die GLB schon, wird NICHT erneut gesendet. Ein Fehler beim Senden wird nie automatisch wiederholt.
Key: kommt nicht aus dem Repo. In der Cloud-Sitzung setzt der Proxy ihn ein (Platzhalter "proxy-injected"); lokal: Umgebungsvariable MESHY_API_KEY.
REGELN (Nutzervorgabe): 1) Meshy sparsam nutzen: Fotos derselben Felge (Feld "gruppe" in fotos.json) brauchen nur EIN Mesh ("meshy_aus" = Referenzfoto).
2) Vor JEDEM Lauf den Nutzer fragen; ohne seine ausdrückliche Zusage in dieser Sitzung wird nicht gestartet. Die Zusage wird mit
   MESHY_FREIGABE="ja: <Datum/Anlass>" übergeben; ohne diese Variable bricht das Skript ab und zeigt nur die Kosten (Trockenlauf).
Aufruf: python3 -I tests/abgleich/meshy_erzeugen.py <foto-schluessel> ...   (Fotos aus fotos.json; bei "zuschnitt" wird out/<key>_zuschnitt.png genutzt)
"""
import importlib.util
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location("cloud", os.path.join(REPO, "felge3d", "cloud.py"))
cloud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud)


def main(keys):
    fotos = json.load(open(os.path.join(HERE, "fotos.json"), encoding="utf-8"))
    outdir = os.path.join(HERE, "out", "meshy")
    os.makedirs(outdir, exist_ok=True)
    prov = cloud.MeshyProvider(os.environ.get("MESHY_API_KEY", "proxy-injected"),
                               {"ai_model": "latest", "texture": os.environ.get("MESHY_TEXTUR", "1") != "0",        # Standard: MIT Textur (+10 Credits)
                                "cache_dir": os.path.join(HERE, "out", "meshy_cache")})
    # gleiche Felge -> nur das Referenzfoto der Gruppe erzeugen
    plan = []
    for k in keys:
        ref = fotos[k].get("meshy_aus", k)
        if ref not in plan and not os.path.isfile(os.path.join(outdir, ref + ".glb")) and not os.path.isfile(os.path.join(outdir, ref + ".task.txt")):
            plan.append(ref)
    cost = 0
    for ref in plan:                                                    # Kosten je Aufruf (Multi-Image und Textur berücksichtigt)
        prov.options["extra_images"] = [x for x in fotos[ref].get("meshy_extra", [])]
        cost += prov.estimate_credits() or 0
    prov.options["extra_images"] = []
    print("Geplant: %d Meshy-Aufruf(e) %s, ca. %d Credits (Fotos derselben Gruppe teilen sich ein Mesh)" % (len(plan), plan, cost))
    print("Guthaben:", prov.balance())
    if not os.environ.get("MESHY_FREIGABE"):
        print("KEINE Freigabe (MESHY_FREIGABE fehlt): Trockenlauf, es wird nichts gesendet. Erst den Nutzer fragen.")
        return
    keys = plan
    for k in keys:
        dest = os.path.join(outdir, k + ".glb")
        if os.path.isfile(os.path.join(outdir, k + ".task.txt")):
            print(k, "Task schon angelegt (siehe .task.txt) – nicht erneut senden")
            continue
        if os.path.isfile(dest):
            print(k, "schon vorhanden:", dest)
            continue
        cfg = fotos[k]
        img = os.path.join(HERE, "out", k + "_zuschnitt.png") if cfg.get("zuschnitt") else os.path.normpath(os.path.join(HERE, cfg["foto"]))
        if os.path.getsize(img) > 20 * 1024 * 1024 or img.endswith(".png") and os.path.getsize(img) > 8 * 1024 * 1024:
            print(k, "Bild zu groß für Data-URI-Upload:", img)
            continue
        t0 = time.time()
        last = [""]

        def prog(p, text):
            if text != last[0]:
                print("  %s %3d %% %s (%.0f s)" % (k, p * 100, text, time.time() - t0), flush=True)
                last[0] = text
        extra = [os.path.normpath(os.path.join(HERE, x)) for x in cfg.get("meshy_extra", [])]      # Multi-Image: weitere Ansichten derselben Felge
        prov.options["extra_images"] = extra
        try:
            glb = prov.generate(img, outdir, prog, threading.Event())
        except cloud.CloudError as e:
            print(k, "FEHLER:", e, "| Task-ID:", getattr(prov, "last_task_id", None))
            if getattr(prov, "last_task_id", None):                 # Task ist bezahlt: ID merken, nicht neu senden
                open(os.path.join(outdir, k + ".task.txt"), "w").write(prov.last_task_id)
            continue
        os.replace(glb, dest)
        print(k, "->", dest)
    print("Guthaben nachher:", prov.balance())


if __name__ == "__main__":
    main(sys.argv[1:])
