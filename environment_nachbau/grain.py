"""Leichtes Filmkorn + minimale Vignette (wie im Foto) auf einen Render legen."""
import sys, numpy as np
from PIL import Image
a = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(np.float32) / 255
h, w, _ = a.shape; rng = np.random.default_rng(7)
g = rng.normal(0, 0.018, (h, w, 1)).astype(np.float32) + 0.5 * rng.normal(0, 0.012, (h, w, 3)).astype(np.float32)
yy, xx = np.mgrid[0:h, 0:w]; v = 1 - 0.10 * (((xx / w - .5) ** 2 + (yy / h - .5) ** 2) * 2)[..., None]
Image.fromarray((np.clip(a * v + g * (1 - 0.5 * a), 0, 1) * 255).astype(np.uint8)).save(sys.argv[2])
