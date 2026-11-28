"""Nachbearbeitung eines Renders: Schwarzpunkt anheben (wie im Foto, dort 2. Perzentil = 34/255), leichtes Filmkorn, minimale Vignette.
Aufruf: python grain.py <in.png> <out.png> [lift]      lift = Anteil des Wertebereichs (Standard 0.05 oder Umgebungsvariable GRADE_LIFT)"""
import os, sys, numpy as np
from PIL import Image
LIFT = float(sys.argv[3]) if len(sys.argv) > 3 else float(os.environ.get('GRADE_LIFT', '0.05'))
a = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(np.float32) / 255
h, w, _ = a.shape; rng = np.random.default_rng(7)
a = LIFT + (1.0 - LIFT) * a                                                   # Schwarzpunkt anheben (linear in Anzeigewerten)
g = rng.normal(0, 0.018, (h, w, 1)).astype(np.float32) + 0.5 * rng.normal(0, 0.012, (h, w, 3)).astype(np.float32)
yy, xx = np.mgrid[0:h, 0:w]; v = 1 - 0.10 * (((xx / w - .5) ** 2 + (yy / h - .5) ** 2) * 2)[..., None]
Image.fromarray((np.clip(a * v + g * (1 - 0.5 * a), 0, 1) * 255).astype(np.uint8)).save(sys.argv[2])
