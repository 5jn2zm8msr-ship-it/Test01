# Rim Generator – Stand & nächste Schritte

## Stand (Version 0.33.0)
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
- 0.29.0: Schnittkurve = Leitlinie: mathematisch exakte Standardkurve (flach bis Nabenradius, dann 1 - u^2; 6 Punkte, mittlerer = Schwerpunkt),
  bei jedem neuen Foto neu gesetzt; Versatz Mitte (Nabenbund) und neu Versatz Außenring liegen als Offsets auf der Kurve.
  FBX/Collection-Felgen werden unverändert übernommen (nur gleichmäßig skaliert und in den Reifen gesetzt, per Test belegt).
- 0.29.1: FBX-Orientierung robuster: Achse = Hauptachse mit rundem Querschnitt, flächengewichtete Punkte, Außenrichtung = von der Bettmitte zur Nabe
  (auch bei flachen/konvexen Felgen; getestet in 14 Lagen: liegend, 90° gedreht, umgedreht, zufällig)
- 0.29.2: Standardkurve + Kurvenänderungen an 10 Testfotos geprüft (Netz stabil, Mindestdicke > 13 mm); ungenutzte Einstellungen entfernt;
  Windows: kein Konsolenfenster bei der KI-Installation; Python-3.10-Syntax geprüft (Blender 3.x)
- 0.30.0 (nur Blender 5.3, getestet mit bpy 5.3.0): Parametrische Quad-Felge per Geometry Nodes (paramrim.py/paramui.py/paramdetect.py):
  Bett, Außenring, Nabe (5 Radschrauben oder Zentralverschluss), Musterspeiche per Rotations-Instanzierung; Schnittkurve (Float Curve, live)
  + Slider Konkavität; Parameter-Erkennung aus dem KI-Mesh (Speichenzahl, Breite, Biegung, Nabe); Materialien prozedural inkl. Diamond Cut;
  Collections Felge_01, Felge_02 … (KI-Mesh ausgeblendet + parametrische Felge), Umschalten im Panel; Package nutzt die parametrische Felge.
  Grenzen: nur Einzelspeichen; Scheiben mit Fenstern, Doppel-/Y-/Netzspeichen werden nur grob angenähert (IoU zur KI-Maske 0,4–0,8).
- 0.31.0: Musterspeiche als „Pizzastück“ (Nabenkeil + Speiche + Ringkeil aus einem Gitter, runde Fenster, Nähte verschweißt: eine durchgehende,
  geschlossene Fläche, 0 offene Kanten, ~99,9 % Quads); eigenes sichtbares Objekt (Wireframe), Felge liest es per Object Info und skaliert es
  auf den Durchmesser; „Muster zum Bearbeiten anwenden“ (Edit Mode, wirkt live), „Muster neu erzeugen“; „Als neue Variante speichern“ (Felge_01_v2);
  die vier Räder teilen dieselbe Node-Group (live gekoppelt, eigene Zoll/Breite je Achse).
  Cloud-Mesh (cloud.py): Provider-Klassen, Key nur in den Preferences (maskiert), Kostenhinweis, asynchron, Fehlermeldungen, GLB-Import.
  OFFEN: Tripo-Bild-Upload ist gesperrt (Doku developers.tripo3d.com war nicht erreichbar; Upload/Fehlercodes ungeprüft) – nur TripoProvider._upload ergänzen.
- 0.32.0 (mehr Details): Speichenform direkt aus der Maske – linke/rechte Speichenkante und Nahtverlauf als Float-Curves über dem Radius
  (statt Breite/Biegung); die Naht läuft durch die Fenster-Mitte (auch bei gebogenen Speichen); Fensterformen, Nabe und Ring aus dem Foto.
  IoU zur KI-Maske 0,56–0,85 (vorher 0,42–0,78). Zusätzlich: Speichenrücken wie im KI-Mesh (1-|u|^2,2), Nabenbund, feineres Gitter (128×11),
  zweifarbige Speichen (polierte Fläche + Rahmen in Grundfarbe, Regler „Diamond-Cut Rand“). Restfehler: vereinzelt kleine offene Nahtkanten
  (0–10 je Felge, bei Netzfelgen mit 20 Speichen bis 160), Doppel-/Y-Speichen werden als eine Hüllspeiche erfasst.
- 0.33.0: **Bearbeitbare Geometrie direkt aus dem Foto, ohne KI-Mesh** (Ergebnis-Wahl: Bearbeitbar (SubD) | KI-Mesh (Textur)).
  Pipeline: Felgenkreis (Reifen ausgeschlossen, sector.refine_circle) -> Maske -> Polarfeld -> Speichenzahl N (Rotations-Score) ->
  Naht durch die Fenster -> Median über alle N Sektoren -> grober Käfig (Quads/Polygone, Randpunkte exakt auf der Kontur, 500-600
  Punkte je Sektor) -> Instanzierung + Verschweißen -> Subdivision Surface (Stufe 0-4) mit Creases (Oberkante 0,7, Unterkante 1,
  Regler „Kantenschärfe“). Fenster/Löcher/Y-/Doppelspeichen ergeben sich aus der Silhouette. Rücken/Bund aus Randabstand, Dicke aus
  Nabe/Speiche, Zweifarbigkeit (weich) aus der Helligkeit des Fotos (zweifarbig nur bei hellem, deutlich abgesetztem Bereich).
  Geprüft an Porsche/Audi/Volvo: 0 offene Kanten, 4-7 s. Offen: Zweifarbigkeit bei Volvo fleckig, dünne Speichen brauchen mehr
  Käfigpunkte (Auflösung steigt automatisch), Felgenhorn-Farbe separat fehlt, Netzfelgen (BBS) ungeprüft.

## Nächste Schritte
0. Nicht belegt: Blender 3.x und echtes Windows (kein bpy 3.x / kein Windows hier); echte Kunden-FBX; AVIF-Fotos werden nicht gelesen (als JPG/PNG speichern).
0. Bremse: Schlitze der Scheibe sind nur Bump aus dem Foto (keine echte Geometrie); Scheibe nutzt die linke Fotohälfte
   gespiegelt (Sattel im Foto verdeckt rechts). Kein freies 3D-Referenzmodell erreichbar -> Aufbau aus Kenntnis der Bauteile.
1. FBX-Weg verfeinern: Nabe/ET der 3D-Felge an die Einpresstiefe anpassen, Breite an die Felgenbreite (J) koppeln,
   mehrere Teile/Materialien prüfen, echte Kunden-FBX testen.
2. **Felgenerkennung weiter verbessern**: Ellipse (Perspektive) statt Kreis, Reifen im Foto, Netzfelgen,
   mehr Testfotos; Kontrolle mit `testfelgen/` (Fusion ist drin, an 3, 6, 8, 10 noch schwach).
3. Alle Maße als Regler (Radstand, Spurweiten, Zoll vorn/hinten sind da; Reifenbreite/Querschnitt/ET liegen unter *Achsen*).
4. Reifen: Beschriftung/Profil feinjustieren (Regler `Beschriftung: Lage`, `Profil-Relief`).
