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
# Breite als fester Bezug (Standard 2020 mm)
assert sizing.car_dims(1.8, 4.5) == (4.5, 1.8) and sizing.car_dims(4.5, 1.8) == (4.5, 1.8)   # Achsenlage egal
f = sizing.width_scale(2020, 1.8)
assert abs(1.8 * f - 2.02) < 1e-12                       # Breite = 2,02 m
assert abs(4.5 * f - 5.05) < 1e-9                      # Länge folgt proportional
assert abs(sizing.estimate_wheelbase_m(4.5 * f, 0) - 0.6 * 4.5 * f) < 1e-12   # Radstand ergibt sich
for bad in ((0, 1.8), (2020, 0)):
    try: sizing.width_scale(*bad); raise SystemExit("kein Fehler: %s" % (bad,))
    except ValueError: pass
print("OK: Groessen-Tests bestanden")
