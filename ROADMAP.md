# Rim Generator – Stand & nächste Schritte

## Stand (Version 0.26.0)
Läuft: Foto → 3D-Felge → 4 Räder (GT3-RS-Maße) mit Reifen (Michelin-Flanke mit Relief, Profil), Update-Knopf,
lokale KI-Tiefe, Selbstprüfung der Speichen, Erkennung per Fusion (Helligkeit + Hintergrund + KI-Tiefe).

Offen/unsicher: Felgenerkennung bei Fotos mit Reifen oder Schrägansicht (Felgenkreis wird falsch gesetzt, dann
stimmt die Speichenzahl nicht); sehr feine Speichen/Netzfelgen (BBS); Fusion nicht an allen 20 Testfotos
gleich gut (3, 6, 8, 10 schwach).

## Erledigt (0.25–0.26)
- Bremsen: Scheibe + Topf + Sattel als Mesh mit Foto-Textur, beidseitig hinten, Schrift rechts korrigiert
- Zoll-Regler vorn/hinten im Hauptpanel
- Zweiter Weg: 3D-Felge (FBX/OBJ/glTF) laden -> Achse/Vorderseite/Größe automatisch, auf die 4 Räder übertragen
  (Quelle umschalten: Foto | 3D-Datei im Hauptpanel)

## Nächste Schritte
1. FBX-Weg verfeinern: Nabe/ET der 3D-Felge an die Einpresstiefe anpassen, Breite an die Felgenbreite (J) koppeln,
   mehrere Teile/Materialien prüfen, echte Kunden-FBX testen.
2. **Felgenerkennung weiter verbessern**: Ellipse (Perspektive) statt Kreis, Reifen im Foto, Netzfelgen,
   mehr Testfotos; Kontrolle mit `testfelgen/` (Fusion ist drin, an 3, 6, 8, 10 noch schwach).
3. Alle Maße als Regler (Radstand, Spurweiten, Zoll vorn/hinten sind da; Reifenbreite/Querschnitt/ET liegen unter *Achsen*).
4. Reifen: Beschriftung/Profil feinjustieren (Regler `Beschriftung: Lage`, `Profil-Relief`).
