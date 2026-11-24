# Rim Generator – Stand & nächste Schritte

## Stand (Version 0.28.1)
Läuft: Foto → 3D-Felge → 4 Räder (GT3-RS-Maße) mit Reifen (Michelin-Flanke mit Relief, Profil), Update-Knopf,
lokale KI-Tiefe, Selbstprüfung der Speichen, Erkennung per Fusion (Helligkeit + Hintergrund + KI-Tiefe).

Offen/unsicher: Felgenerkennung bei Fotos mit Reifen oder Schrägansicht (Felgenkreis wird falsch gesetzt, dann
stimmt die Speichenzahl nicht); sehr feine Speichen/Netzfelgen (BBS); Fusion nicht an allen 20 Testfotos
gleich gut (3, 6, 8, 10 schwach).

## Erledigt (0.25–0.27)
- Aufteilung in zwei Reiter (2D to 3D Rim | Package); Package nimmt die generierte Felge oder per Picker eine Collection
- Schnittkurve mit Handles (Tiefe/Bombierung des Tellers) + Refresh
- Bremsen 0.28: echtes 3D – innenbelüftete Scheibe (2 Reibringe + 36 gebogene Stege), Topf mit Schulter, Sattel aus Außenplatte
  (Umriss aus dem Foto) + Innenplatte + Brücke + 2 Bremsbeläge + 2 Torx-Schrauben + Entlüfter; Foto nur als Textur,
  Sattel um die Achse drehbar (Regler *Sattelposition*, Standard 45° = oben-hinten), Schrift rechts korrigiert.
  Materialien: Scheibe gebürsteter Stahl (Anisotropie, Rauheit/Bump aus dem Foto), Sattel Klarlack (Coat) + Bump
- Zoll-Regler vorn/hinten im Hauptpanel
- Zweiter Weg: 3D-Felge (FBX/OBJ/glTF) laden -> Achse/Vorderseite/Größe automatisch, auf die 4 Räder übertragen
  (Quelle umschalten: Foto | 3D-Datei im Hauptpanel)

- 0.28.1: Schnittkurve mit Buttons + Punkt / − Punkt / Weich / Knick; Blender 5.3 getestet, ONNX-Auswahl für Python 3.13

## Nächste Schritte
0. Bremse: Schlitze der Scheibe sind nur Bump aus dem Foto (keine echte Geometrie); Scheibe nutzt die linke Fotohälfte
   gespiegelt (Sattel im Foto verdeckt rechts). Kein freies 3D-Referenzmodell erreichbar -> Aufbau aus Kenntnis der Bauteile.
1. FBX-Weg verfeinern: Nabe/ET der 3D-Felge an die Einpresstiefe anpassen, Breite an die Felgenbreite (J) koppeln,
   mehrere Teile/Materialien prüfen, echte Kunden-FBX testen.
2. **Felgenerkennung weiter verbessern**: Ellipse (Perspektive) statt Kreis, Reifen im Foto, Netzfelgen,
   mehr Testfotos; Kontrolle mit `testfelgen/` (Fusion ist drin, an 3, 6, 8, 10 noch schwach).
3. Alle Maße als Regler (Radstand, Spurweiten, Zoll vorn/hinten sind da; Reifenbreite/Querschnitt/ET liegen unter *Achsen*).
4. Reifen: Beschriftung/Profil feinjustieren (Regler `Beschriftung: Lage`, `Profil-Relief`).
