# Felgen-Add-on (felge3d) – Regeln für Änderungen

Quelle dieser Regeln: Vorgaben des Nutzers aus dem bisherigen Verlauf (Entwurf, bitte korrigieren, wenn etwas nicht stimmt).

## Modellier-Regeln (Ergebnis „bearbeitbar / SubD“)
- Käfig des Mustersektors (Pizzastück) aus Quads und wenigen Polygonen, grob: ca. 300–600 Punkte je Sektor als Richtwert (Zeilenabstand ~18 mm); Subdivision Stufe 2 verfeinert.
- Linien des Käfigs laufen entlang der Speiche, parallel zur Außenkontur, nicht radial ins Zentrum (Ausnahme: Nabe).
- Alle scharfen Außenkanten und die Grenze blank/schwarz sind Creases (1,0). Materialgrenzen kommen nur aus Geometriekanten.
- Keine Zacken im Rand, keine Haarlinien-Kanten (< 0,9 mm), keine offenen Kanten bei Stufe 2 (Ziel 0).
- Diamond Cut liegt auf dem Teller (Drehfläche z = f(r), Bézier-Kurve mit 3 Punkten); schwarze Flächen liegen um „Rücksprung“ dahinter.
- Nabe geschlossen: Kappe, Zentralverschluss oder Schrauben mit Mittelkappe; Spiegelungen im Foto sind keine Löcher.
- Optik technisch/gefräst (scharfe Kanten), nicht organisch rund.

## Messung / Freigabe
- `python tests/diamond_cut/eval_diamond_cut.py` (Ziel: Flächengenauigkeit ≥ 98 %); IoU und Ring-IoU dürfen nicht schlechter werden.
- Regression über die Testfelgen (`testfelgen/`): Speichenzahl, Drehlage, „Zuordnung sicher“, offene Kanten, Käfiggröße.
- Ein Schritt gilt als erledigt, wenn kein Messwert schlechter ist als zuvor (Subagent `reviewer`).
- Bilder (Renderings, Abgleich) mit schwarzer Backplate; nicht beschnittene Speichen zeigen.

## Meshy-Credits (Vorgabe des Nutzers, 25.11.2026)
- Sparsam nutzen: mehrere Fotos derselben Felge brauchen nur EIN Meshy-Mesh (Gruppe in `tests/abgleich/fotos.json`, `meshy_aus` = Referenzfoto).
- Vor JEDEM Meshy-Aufruf den Nutzer fragen (Anzahl Aufrufe, geschätzte Credits, Guthaben nennen); ohne ausdrückliche Zusage nichts senden. Das Skript `tests/abgleich/meshy_erzeugen.py` läuft ohne `MESHY_FREIGABE` nur als Trockenlauf.
- Gleiche Bilder + gleiche Einstellungen kommen aus dem Cache (`MeshyProvider`, Option `cache_dir`), nie doppelt bezahlen.
- Key nie ausgeben oder speichern: nur über den Proxy bzw. die Preferences.
