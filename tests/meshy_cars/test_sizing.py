"""Test der Radstand-Mathematik. Aufruf: python -I tests/meshy_cars/test_sizing.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "meshy_cars"))
import sizing  # noqa: E402

assert abs(sizing.scale_factor(2450, 2.45) - 1.0) < 1e-12
assert abs(sizing.scale_factor(3000, 2.5) - 1.2) < 1e-12              # größerer Radstand -> größeres Auto
assert abs(sizing.scale_factor(1250, 2.5) - 0.5) < 1e-12
assert abs(sizing.estimate_wheelbase_m(4.5, 1.8) - 2.7) < 1e-9 and abs(sizing.estimate_wheelbase_m(1.8, 4.5) - 2.7) < 1e-9
assert abs(sizing.distance((0, 0, 0), (3, 4, 0)) - 5) < 1e-12
for bad in ((0, 2.5), (2450, 0), (-1, 2.5)):
    try: sizing.scale_factor(*bad); raise SystemExit("kein Fehler: %s" % (bad,))
    except ValueError: pass
# Proportionalität: zweimal skalieren == einmal direkt
f1 = sizing.scale_factor(2800, 2.5); f2 = sizing.scale_factor(2450, 2.5 * f1)
assert abs(f1 * f2 - sizing.scale_factor(2450, 2.5)) < 1e-12
print("OK: Radstand-Tests bestanden")
