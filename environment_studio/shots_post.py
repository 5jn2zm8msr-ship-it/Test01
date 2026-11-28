import sys, numpy as np
from PIL import Image, ImageDraw, ImageFont
src, dst, title = sys.argv[1:4]
a = np.asarray(Image.open(src).convert('RGB')).astype(np.float32)/255
a = np.clip((a - 0.50)/(0.96 - 0.50), 0, 1)**1.1
im = Image.fromarray((a*255).astype(np.uint8)); d = ImageDraw.Draw(im)
f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 34); f2 = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
t, sub = (title.split('|') + [''])[:2]
d.rounded_rectangle([28, 28, 28 + max(d.textlength(t, font=f), d.textlength(sub, font=f2)) + 36, 28 + (110 if sub else 70)], radius=14, fill=(20, 20, 24))
d.text((46, 38), t, fill=(255, 255, 255), font=f)
if sub: d.text((46, 84), sub, fill=(190, 190, 200), font=f2)
im.save(dst); print(dst)
