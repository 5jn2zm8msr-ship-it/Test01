#!/bin/bash
# Alle drei Bilder in Folge (je ~9 min): Originalansicht, Bild 1 (Auto 180 Grad), Bild 2 (Ecke + Wald)
cd "$(dirname "$0")"
./final.sh "$@"
./final_ansichten.sh "$@"
echo ALLES_FERTIG
