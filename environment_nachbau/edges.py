"""Kanten des Renders (rot) und des Fotos (cyan) auf Grau uebereinander -> Perspektivpruefung."""
import sys, numpy as np
from PIL import Image, ImageFilter
REF='/root/.claude/uploads/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/c2a87a4f-image.jpg'
def edge(p, blur):
    im=Image.open(p).convert('L').resize((720,720)).filter(ImageFilter.GaussianBlur(blur))
    a=np.asarray(im).astype(float); gx=np.abs(np.diff(a,axis=1,prepend=a[:,:1])); gy=np.abs(np.diff(a,axis=0,prepend=a[:1]))
    e=np.hypot(gx,gy); return np.clip(e/np.percentile(e,99.3),0,1)
er=edge(sys.argv[1],2.0); ef=edge(REF,2.0)
out=np.full((720,720,3),255.,np.float32)
out[...,0]-=ef*255*0.9; out[...,1]-=ef*255*0.25         # Foto: cyan-ish (rot raus)
out[...,1]-=er*255*0.9; out[...,2]-=er*255*0.9          # Render: rot
Image.fromarray(np.clip(out,0,255).astype(np.uint8)).save(sys.argv[2])
