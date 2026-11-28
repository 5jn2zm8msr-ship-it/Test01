#!/bin/bash
# Nur Bild 2 (Ecken-Kamera, Auto wie im Foto, Waldwand) neu rendern
cd "$(dirname "$0")"; mkdir -p ergebnis_ansichten
PY=${PY:-/tmp/claude-0/-home-user-Test01/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/scratchpad/venv/bin/python}; R=${RES:-1080}; N=${SAMPLES:-96}
$PY build_scene.py ergebnis_ansichten/bild2_roh.png $R $N --view=ecke --wald=1 --carshifty=-1.0 "$@" 2>&1 | grep -E "DONE|rror|Traceback|AUTO|KAMERA"
$PY grain.py ergebnis_ansichten/bild2_roh.png ergebnis_ansichten/bild2_ecke_wald.png
rm -f ergebnis_ansichten/bild2_roh.png
echo FERTIG
