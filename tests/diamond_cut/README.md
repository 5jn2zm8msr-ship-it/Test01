# Diamond-Cut-Messung

Misst, wie genau das Add-on die Käfigflächen in **blank (Diamond Cut)** und **schwarz** einteilt, gegen eine Ground-Truth-Maske.

```bash
python tests/diamond_cut/eval_diamond_cut.py            # alle Fälle aus cases.json, schreibt ergebnis.md
DC_DEBUG=1 python tests/diamond_cut/eval_diamond_cut.py # zusätzlich fehler_<name>.png (rot = zu viel blank, blau = fehlt)
DC_NO_DEPTH=1 python ...                                # ohne Tiefen-Regel (Standard: aus)
```

(Python = das `bpy`-Modul / Blender-Python mit numpy.)

## Kennzahlen
- **Flächengenauigkeit (Fläche)**: je Käfigfläche und Sektor entscheidet die Mehrheit der Ground-Truth-Pixel das Soll-Label; Anteil der richtig
  beschrifteten Fläche (pixelgewichtet). **Das ist die Zielgröße (≥ 98 %).**
- Flächengenauigkeit (Anzahl): dasselbe, aber jede Fläche zählt gleich.
- Pixelgenauigkeit / IoU blank / Präzision / Recall: Pixelvergleich im Speichenbereich (nur Käfigflächen, 55–262 mm Radius).
  Die Kontur der Käfigflächen ist grob (Kanten laufen entlang des Käfigs), daher liegt der IoU bei dünnen Speichen deutlich unter der Flächengenauigkeit.

## Ground Truth
`volvo/gt.png` ist ein **Entwurf**, kein von Hand gezeichnetes Original: `make_gt.py` überträgt einige weiße und schwarze Proben einer Speiche per Symmetrie
auf alle Speichen, legt die Schwelle in die Mitte der Proben und nimmt die zusammenhängenden hellen Gebiete mit weißem Samen (≥ 60 px). Unabhängig von
der Abstimmungslogik des Add-ons gebaut, aber nicht unabhängig von der Helligkeit. **Bitte prüfen und bei Bedarf in einem Bildeditor nachmalen**
(weiß = blank, schwarz = nicht blank, gleiche Größe und Orientierung wie die Datei). Die Kanten sind auf ±1–2 Pixel genau.
Neue Fälle: Foto nach `<name>/photo.jpg`, Maske nach `<name>/gt.png` (Arbeitsauflösung des Add-ons), Eintrag in `cases.json`.
