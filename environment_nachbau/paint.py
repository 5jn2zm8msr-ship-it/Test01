"""Lackfarbe im Auto-Bereich messen: mittlerer Farbton/Saettigung der Karosserie-Pixel. Aufruf: python paint.py <render.png> [x0 y0 x1 y1]"""
import sys, numpy as np, colorsys
from PIL import Image
im = np.asarray(Image.open(sys.argv[1]).convert('RGB').resize((720, 720))).astype(float) / 255
x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6]) if len(sys.argv) >= 6 else (130, 300, 560, 470)
box = im[y0:y1, x0:x1]; hsv = np.array([colorsys.rgb_to_hsv(*p) for p in box.reshape(-1, 3)]).reshape(box.shape)
sel = (hsv[..., 1] > 0.30) & (hsv[..., 2] > 0.35); m = box[sel].mean(0); h, s, v = colorsys.rgb_to_hsv(*m)
print(f'Lack: {int(sel.sum()):6d} Pixel  RGB {(m*255).round().astype(int)}  Farbton {h*360:5.1f} Grad (Original-Gold 37.4)  Saettigung {s:.2f} (Original ~0.66)  Helligkeit {v:.2f}')
