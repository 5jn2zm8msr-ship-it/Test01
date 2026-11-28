#!/bin/bash
# Qualitaets-Render + Korn + Vergleichsbild + Kanten-Overlay + Messung (alles in ergebnis/)
cd "$(dirname "$0")"; mkdir -p ergebnis
PY=${PY:-/tmp/claude-0/-home-user-Test01/c07fdc5c-1ff2-54c4-b0e5-bd212c8d6483/scratchpad/venv/bin/python}
$PY build_scene.py ergebnis/render_roh.png ${RES:-1080} ${SAMPLES:-96} "$@" 2>&1 | grep -E "DONE|rror|Traceback|AUTOMASSE"
$PY grain.py ergebnis/render_roh.png ergebnis/render_final.png
$PY compare.py ergebnis/render_final.png ergebnis/vergleich.png
$PY edges.py ergebnis/render_roh.png ergebnis/perspektive_kanten.png
$PY measure.py ergebnis/render_roh.png > ergebnis/messung_helligkeit.txt
echo FERTIG
