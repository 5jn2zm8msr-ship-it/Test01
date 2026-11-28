"""Test Preisrechner (Preisseite 27.11.2026). Aufruf: python -I tests/meshy_cars/test_prices.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "meshy_cars"))
import client  # noqa: E402

# ---- Preisrechner (Preisseite 27.11.2026)
e = client.estimate_credits
assert e("meshy-7.1", "standard", True, "2k") == 30           # = tatsaechlich abgebuchter Testlauf
assert e("latest", "standard", False) == 20 and e("meshy-6", "standard", True, "4k") == 30
assert e("meshy-7.1", "standard", True, "8k") == 35 and e("meshy-7.1", "2k", True, "2k") == 35
assert e("meshy-6-lite", "standard", False) == 5 and e("meshy-6-lite", "standard", True, "2k") == 15
for bad in (("meshy-6-lite", "standard", True, "4k"), ("meshy-6", "2k", True, "2k"), ("meshy-6-lite", "2k", False, "2k")):
    try: e(*bad); raise SystemExit("kein Fehler: %s" % (bad,))
    except client.MeshyError: pass

print("OK: Preis-Tests bestanden")
