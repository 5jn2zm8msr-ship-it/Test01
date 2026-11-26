# Experimente (nicht in der Matrix)

Rohzahlen: `experimente.json`. Blätter: `out/A1_<foto>_vergleich.png` (5. Spalte).

## A1 – Meshy-Silhouette als Maske für den SubD-Bau (25.11.2026)

Vorgehen: Meshy-Mesh (Referenz der Gruppe: gold) in der Foto-Kamera rendern, Silhouette über Maßstab/Verschiebung auf die Foto-Kanten legen
(gold: Treffer 34 % → 81 %, Maßstab 1,005, Verschiebung 3/16 px; graphit: Maßstab 1,0, keine Verschiebung, Treffer 63 % → 63 %), als `mask_image`
in die Pipeline geben, SubD neu bauen. Kanten ±3 px, Hilfswerte:

| Foto | Bau | Präzision | Recall | F1 | Speichen |
|---|---|---|---|---|---|
| gold | normal, N = 10 (Automatik) | 36 % | 24 % | 29 % | 10 |
| gold | **mit Meshy-Maske** (der Bau nimmt N = 10) | 33 % | 22 % | **26 %** | 10 |
| gold | normal, N = 5 erzwungen | 38 % | 44 % | 41 % | 5 |
| gold | mit Meshy-Maske, N = 5 erzwungen – greift nicht, der Maskenbau nimmt trotzdem N = 10 | 32 % | 22 % | 26 % | 10 |
| graphit | normal, N = 5 (Automatik) | 41 % | 80 % | 54 % | 5 |
| graphit | **mit Meshy-Maske** (der Bau nimmt N = 10) | 50 % | 25 % | **33 %** | 10 |

**Bewertung (korrigiert nach Reviewer-Hinweis):** Der faire Vergleich ist der bei gleichem N: gold N = 10 gegen N = 10 sind es nur 3 Punkte
(F1 29 % → 26 %), also kein Gewinn. Die größeren Abstände (26 % gegen 41 %, 33 % gegen 54 %) mischen den Effekt der Maske mit dem der Speichenzahl N,
weil der Maskenbau immer N = 10 wählt (Meshy macht die Fenster gleichmäßig) und die manuelle Symmetrie dort nicht greift. Ergebnis: **kein Gewinn → verworfen**.

## N = 5 statt Automatik bei gold

Mit `symmetrie: 5` in `fotos.json` (Symmetrie MANUAL, Ordnung 5): Recall 24 % → 44 %, F1 29 % → 41 %, „Zuordnung sicher“ 85 %, poliert 57 % statt 100 %.
Das Ergebnis sieht allerdings unruhig aus (Käfig 1093 Punkte, schlangenartige Kanten, Speichenflächen fehlen weiterhin). Ob N = 5 oder 10 gelten soll, ist offene
Frage an den Nutzer. Die Automatik (`pick_n`: größtes N nahe am Besten) wählt bei Y-Speichen 10.
