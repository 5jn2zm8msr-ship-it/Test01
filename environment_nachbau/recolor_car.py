"""Meshy-Basisfarbtextur (blauer Lack) -> weisser Lack. Dunkle Teile (Glas, Reifen, Schatten) bleiben."""
import sys
import numpy as np
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
rgb = np.asarray(im).astype(np.float32) / 255.0
hsv = np.asarray(im.convert("HSV")).astype(np.float32) / 255.0
h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
# "Lackmaske": gesaettigtes Blau mit genug Helligkeit
paint = np.clip((s - 0.35) / 0.25, 0, 1) * np.clip((v - 0.22) / 0.2, 0, 1)
paint = np.asarray(Image.fromarray((paint * 255).astype(np.uint8)).filter(__import__("PIL.ImageFilter", fromlist=["x"]).GaussianBlur(1.2))).astype(np.float32) / 255.0
white = np.clip(0.80 + 0.35 * (v - 0.55), 0.62, 0.95)[..., None] * np.ones((1, 1, 3), np.float32)
grey = rgb.mean(axis=2, keepdims=True)
rest = grey + (rgb - grey) * 0.35   # Blaustich der dunklen Teile entfernen
out = rest * (1 - paint[..., None]) + white * paint[..., None]
Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(dst)
print("paint coverage", float(paint.mean()))
