"""Vergleichsbild: Referenzfoto | Render | 50/50-Ueberblendung, alles 720 px."""
import sys
from PIL import Image, ImageDraw
ref = Image.open('/root/.claude/uploads/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/c2a87a4f-image.jpg').convert('RGB').resize((720, 720))
rend = Image.open(sys.argv[1]).convert('RGB').resize((720, 720))
mix = Image.blend(ref, rend, 0.5)
sheet = Image.new('RGB', (720 * 3 + 40, 720 + 40), 'black'); d = ImageDraw.Draw(sheet)
for i, (im, t) in enumerate(((ref, 'Referenzfoto'), (rend, 'Nachbau (Render)'), (mix, 'Ueberblendung 50/50'))):
    sheet.paste(im, (i * 740, 40)); d.text((i * 740 + 8, 12), t, fill='white')
sheet.save(sys.argv[2])
