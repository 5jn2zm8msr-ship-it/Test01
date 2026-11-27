# SPDX-License-Identifier: GPL-3.0-or-later
"""Radstand-Skalierung (reine Mathematik, ohne bpy -> testbar). 1 Blender-Einheit = 1 m."""
import math

WHEELBASE_RATIO = 0.60     # grobe Schätzung: Radstand ~ 60 % der Fahrzeuglänge (Pkw typisch 0,57-0,63) -> nur Startwert!


def estimate_wheelbase_m(dim_x, dim_y):
    """Schätzt den Radstand (m) aus der längeren horizontalen Ausdehnung der Bounding-Box."""
    return WHEELBASE_RATIO * max(dim_x, dim_y)


def distance(a, b):
    return math.dist(a, b)


def scale_factor(target_mm, base_m):
    """Gleichmäßiger Skalierfaktor, damit der Radstand base_m (im Modell) zu target_mm wird."""
    if base_m <= 0:
        raise ValueError("Basis-Radstand muss > 0 sein.")
    if target_mm <= 0:
        raise ValueError("Ziel-Radstand muss > 0 sein.")
    return (target_mm / 1000.0) / base_m
