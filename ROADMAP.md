# Rim Generator – Stand & nächste Schritte

## Stand (Version 0.24.1)
Läuft: Foto → 3D-Felge → 4 Räder (GT3-RS-Maße) mit Reifen (Michelin-Flanke mit Relief, Profil), Update-Knopf,
lokale KI-Tiefe, Selbstprüfung der Speichen, Erkennung per Fusion (Helligkeit + Hintergrund + KI-Tiefe).

Offen/unsicher: Felgenerkennung bei Fotos mit Reifen oder Schrägansicht (Felgenkreis wird falsch gesetzt, dann
stimmt die Speichenzahl nicht); sehr feine Speichen/Netzfelgen (BBS); Fusion nicht an allen 20 Testfotos
gleich gut (3, 6, 8, 10 schwach).

## Nächste Schritte (Wünsche des Nutzers)
1. **Bremsen + Sattel** (Foto `assets/bremse_foto.png`): Scheibe/Topf als Mesh mit Foto-Textur, Sattel als Mesh mit
   Umriss aus dem Foto (Messung: Scheibenmitte 535.5/814.5 px, Radius 449 px, Sattel x 0.45–1.14 R, y −0.87…1.01 R;
   Reibring innen ~0.62 R). Beidseitig hinten; Schrift auf der Gegenseite korrigieren. `car.build_brake` ist vorbereitet.
2. **Zweiter Weg: FBX-Felge importieren** – eigener Reiter; die 3D-Felge wird auf die vier Räder übertragen
   (Skalierung auf Zollgröße, ET/Breite, Ausrichtung/Achse).
3. **Alle Maße als Regler**: Radstand, Spurweite vorn/hinten, **Zollgröße vorn/hinten** (Slider), Reifen- und Felgenbreite.
4. **Felgenerkennung weiter verbessern**: Ellipse (Perspektive) statt Kreis, Reifen im Foto, Netzfelgen,
   mehr Testfotos; Kontrolle mit `testfelgen/`.
5. Reifen: Beschriftung/Profil feinjustieren (Regler `Beschriftung: Lage`, `Profil-Relief`).
