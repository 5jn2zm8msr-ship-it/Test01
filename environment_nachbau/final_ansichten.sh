#!/bin/bash
# Zwei Ansichten in ergebnis_ansichten/:
#   bild1_auto180.png      Originalkamera (70 mm), Auto um 180 Grad gedreht (Heck zur Kamera)
#   bild2_ecke_wald.png   Kamera hinten in der Ecke (70 mm, 1,50 m), Auto 3/4-Heck, Waldbild statt Kamerawand
cd "$(dirname "$0")"; mkdir -p ergebnis_ansichten
PY=${PY:-/tmp/claude-0/-home-user-Test01/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/scratchpad/venv/bin/python}; R=${RES:-1080}; N=${SAMPLES:-96}
$PY build_scene.py ergebnis_ansichten/bild1_roh.png $R $N --carrot=180 "$@" 2>&1 | grep -E "DONE|rror|Traceback|AUTO"
$PY grain.py ergebnis_ansichten/bild1_roh.png ergebnis_ansichten/bild1_auto180.png
$PY build_scene.py ergebnis_ansichten/bild2_roh.png $R $N --view=ecke --wald=1 --carrot=35 --carshiftx=0.9 --carshifty=-2.5 "$@" 2>&1 | grep -E "DONE|rror|Traceback|AUTO|KAMERA"
$PY grain.py ergebnis_ansichten/bild2_roh.png ergebnis_ansichten/bild2_ecke_wald.png
rm -f ergebnis_ansichten/bild1_roh.png ergebnis_ansichten/bild2_roh.png
echo FERTIG
