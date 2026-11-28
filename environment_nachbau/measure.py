"""Mittlere Helligkeit (0-255) und RGB an festen Bildregionen: Foto vs. Render (720-px-Koordinaten)."""
import sys, numpy as np
from PIL import Image
REF='/root/.claude/uploads/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/c2a87a4f-image.jpg'
R={'Decke':(300,20,500,80),'Wand links schattig':(20,150,120,250),'Wand links sonnig':(190,290,280,380),
 'Rueckwand':(420,200,520,300),'Boden sonnig':(10,470,100,495),'Boden vorn schattig':(200,600,450,700),
 'Pfeiler':(650,200,690,400),'Keil rechts':(470,450,540,480),'Himmel':(450,100,600,130),'Auto Motorhaube':(230,390,330,420)}
def stats(p):
    a=np.asarray(Image.open(p).convert('RGB').resize((720,720))).astype(float)
    return {k:a[y0:y1,x0:x1].reshape(-1,3).mean(0) for k,(x0,y0,x1,y1) in R.items()}
a=stats(REF); b=stats(sys.argv[1])
print(f"{'Region':22s} {'Foto L':>7s} {'Render L':>8s}   Foto RGB        Render RGB")
for k in R:
    la,lb=a[k].mean(),b[k].mean()
    print(f"{k:22s} {la:7.0f} {lb:8.0f}   {a[k].round().astype(int)}  {b[k].round().astype(int)}")
