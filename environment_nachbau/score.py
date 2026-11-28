"""Verteilungs-Abstand Render vs. Foto: Perzentile (2..98), Anteil ausgebrannt/abgesoffen, Gesamtnote (kleiner = naeher am Foto).
Aufruf: python score.py <render.png> [label]"""
import sys, numpy as np
from PIL import Image
REF = '/root/.claude/uploads/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/c2a87a4f-image.jpg'
P = [2, 10, 25, 50, 75, 90, 98]
def L(p): a = np.asarray(Image.open(p).convert('RGB').resize((720, 720), Image.LANCZOS)).astype(float); return a @ np.array([0.2126, 0.7152, 0.0722])
import os; LIFT = float(os.environ.get('LIFT', '0')); f = L(REF); r = LIFT * 255 + (1 - LIFT) * L(sys.argv[1]); pf = np.percentile(f, P); pr = np.percentile(r, P)
d = np.abs(pf - pr).mean(); clip = 100 * (r > 245).mean()
print(f"{(sys.argv[2] if len(sys.argv)>2 else sys.argv[1]):34s} " + ' '.join(f'{v:4.0f}' for v in pr) + f" | Abstand {d:5.1f}  ausgebr. {clip:4.1f}%  abgesoffen {100*(r<20).mean():4.1f}%  Mittel {r.mean():4.0f} (Foto {f.mean():.0f})")
if len(sys.argv) > 2 and sys.argv[2] == 'FOTO': pass
