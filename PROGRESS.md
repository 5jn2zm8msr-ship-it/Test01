# PROGRESS – Felgen-Add-on (Branch `dev`, niemals `main`)

Arbeitsweise (seit 27.11.2026): nächste offene Aufgabe umsetzen → eigene Tests/Messung ausführen → committen und auf `dev` pushen (ohne Rückfrage, nie `main`) → diese Datei aktualisieren. Der Subagent `reviewer` ist auf Wunsch des Nutzers dauerhaft pausiert.

## Stand
- Version 0.43.0 (`dev`; Basis 0.42.0). Neu: Meshy als zweiter Cloud-Provider (siehe unten).
- Pipeline: Foto → Felgenkreis → Maske → N/Phase → Käfig (Subdivision) → Diamond-Cut je Fläche (Abstimmung ≥ N−1, Registrierung je Sektor) → Teller (Bézier, 3 Punkte) → Nabenmitte → Felgenhorn.
- Messung: `tests/diamond_cut/` (Ground Truth nur Volvo, **Entwurf aus Samen**).

## Letzte Messwerte
Diamond-Cut-Messung (`python tests/diamond_cut/eval_diamond_cut.py`), Ground Truth inkl. Nabe + Außenring, Kappe (r < 45 mm) ausgenommen:

| Bild | Flächengenauigkeit (Fläche) | Flächen (Anzahl) | Pixelgenauigkeit | IoU blank | Ring-IoU | Stand |
|---|---|---|---|---|---|---|
| Volvo (2352338.jpg) | 98,0 % | 95,5 % | 96,4 % | 87,6 % | 80,0 % | 0.42.0 |

Regression über die Testfelgen (Info-Text; „sicher“ = Flächenanteil mit Konfidenz ≥ 0,6), Stand 0.42.0:

| Foto | Speichen | poliert | Zuordnung sicher | Bemerkung |
|---|---|---|---|---|
| Porsche 992 (41411…) | 5 | 37 % | 94 % | 5 Spiegelungen als Material, Horn poliert; 20 offene Kanten (Stufe 2) |
| Volvo (2352338) | 5 | 35 % | 90 % | Horn poliert; offene Kanten 0–100 je Lauf |
| Audi RS (Nutzerfoto IMG_2691) | 5 | 37 % | 72 % ⚠ | gebürstetes Silber, helle Flächen in einzelnen Sektoren dunkler |
| Polestar (Original-Polestar…) | 5 | 46 % | 94 % | |
| Mercedes (a23640116…) | 5 | 33 % | 90 % | |
| images.jpeg | 10 | 33 % | 72 % ⚠ | |
| s-l1200.jpg | 5 | 43 % | 74 % ⚠ | |
| BBS (20 Speichen) | 20 | **100 %** | – | **Verschlechterung** (0.41.0: ~58 % zweifarbig) |

## Neue Testfotos (vom Nutzer auf `main` hochgeladen, jetzt in `tests/diamond_cut/neue_felgen/`)
Porsche-911-Turbo-Räder mit **lackiertem Stern und nur schmaler polierter Kante** (Fensterränder + Außenring, ca. 2–3 mm breit):

| Foto | Speichen (erkannt) | poliert | Beobachtung |
|---|---|---|---|
| graphit IMG_2694 | 11 ⚠ (vermutlich 5) | 0 % | Kante zu schmal, kein Diamond Cut erkannt; Speichenzahl falsch |
| gold IMG_2695 | 10 (vermutlich 5) | 100 % | ganzer Stern als „poliert“ gewertet (gold ist hell), Soll: nur weiße Kante + Ring |
| IMG_2697 (Nahaufnahme, schräg), IMG_2700 (Screenshot, perspektivisch) | – | – | nicht frontal, vom Add-on nicht unterstützt; nur Referenz |

Bilder: `progress/neu_gold_IMG_2695_abgleich_0.42.png`, `progress/neu_graphit_IMG_2694_abgleich_0.42.png`.

## Erledigt (diese Sitzung, auf `main`)
Teller-Kurve, Nabenmitte, Spiegelungen, Käfig entlang der Speiche, Abgleich-Bild, Graustufen-Mapping mit Regler, Flächen-Klassifikation mit Abstimmung, Messung, Nabe/Ring in Zone und Messung.

## Meshy-Anbindung (0.43.0, Reviewer: BESTANDEN im 2. Versuch)
- Umgesetzt nach der aktuellen Doku (docs.meshy.ai/llms-full.txt, gelesen am 25.11.2026): `MeshyProvider` in `felge3d/cloud.py`; Image to 3D nur Mesh (`should_texture=false`, GLB), optional Multi-Image (Front + Schrägansicht, 1–4 Bilder), optional Remesh (`/v1/remesh`); Polling mit Retry-After, 429/Verbindungsfehler/5xx werden wiederholt; Create wird nie automatisch erneut gesendet; Guthaben `GET /v1/balance`; Kosten je Aufruf im Panel und im Bestätigungsdialog.
- `ai_model` ist eine Einstellung in den Preferences (Standard `latest`), wird immer gesendet; die Preistabelle dient nur der Kostenanzeige. Bei einem abgeschalteten Modell kommt eine klare Meldung mit Hinweis auf die Preferences.
- Key nur in den Preferences (maskiert), nie im Repo (geprüft per Suche).
- Vergleichsmodus (Panel „Mesh-Quelle“): dasselbe Foto Lokal / Tripo / Meshy, jede Quelle in eigener Collection „KI-Mesh | …“ seitlich versetzt.
- Tests: `python3.11 tests/cloud/test_meshy_mock.py` (32 Prüfungen, lokaler Mock-Server), `python3.11 tests/cloud/test_meshy_blender.py`. Regression Diamond-Cut unter Blender 5.3 (`/tmp/venv53/bin/python tests/diamond_cut/eval_diamond_cut.py`): Volvo 98,0 % / IoU 88,0 % / Ring-IoU 80,0 % – unverändert.
- **Meshy-Verbrauch (25.11.):** 3 Aufträge für die drei Porsche-Fotos (60 Credits, Guthaben 1100 → 1040); es ist dasselbe Felgendesign, ein Auftrag hätte gereicht. Seither: Gruppen in `tests/abgleich/fotos.json`, Cache nach Bild-Hash, Freigabe-Sperre im Skript, Regel in CLAUDE.md.
- **Grenzen:** Kein echter Meshy-Aufruf getestet (kein Key), nur Mock nach Doku; der Vergleichs-Operator ist nur registriert, nicht ausgeführt getestet; der Tripo-Upload ist weiter gesperrt (Doku nie erreichbar). `meshy-7` ist als Modell veraltet (Abschaltung 31.12.2026).

## Bildabgleich und Bewertungsmatrix (Reviewer: Werkzeug BESTANDEN im 3. Versuch)
- Werkzeug: `tests/abgleich/abgleich.py` (Blender 5.3): Kamera in der Perspektive des Fotos (Brennweite, Abstand, Verschiebung; Schrägansicht: Entzerrung der Ellipse und Drehung um die Hochachse, silber yaw 50°), Materialien aus den Foto-Farben (Lack/Blank, Metall/Rauheit je Foto), neutrales Studiolicht, schwarze Backplate. Blatt je Foto in `tests/abgleich/out/<foto>_vergleich.png`: Zeile 1 = 1 Foto | 2 Mesh lokal (KI-Mesh mit Foto-Textur) | 3 SubD lokal | 4 Meshy; Zeile 2 = Überlagerung | Kanten | Nabe 3x.
- Matrix: `tests/abgleich/kriterien.json` (Genauigkeit, Speichenform, Speichenfarbe, Zentrum, Wappen, Schrauben/Zentralverschluss, Skala 1–5), Noten in `bewertung.json` (Spalten Reviewer / Nutzer), `python3 tests/abgleich/auswertung.py` erzeugt `bewertung.md` mit Priorität (schlechtester Mittelwert zuerst, nur neueste Version je Foto; Abweichung ≥ 2 Punkte = „klären“).
- **Stand (Reviewer-Noten, Blatt v2/v3; Nutzer-Noten stehen noch aus):** Wappen 1,0 · Speichenform 1,7 · Genauigkeit 2,0 · Verschluss 2,0 · Zentrum 2,3 · Speichenfarbe 3,3. Zusatz Spalte 2/4 (Gesamtnote): KI-Mesh lokal 3 / 4 / 2 (graphit / gold / silber), Meshy 3 / 4 / 2.
- Messwerte sind nur Hilfen (Kanten-Präzision/Recall ±3 px, Farbabstand, Kappenradius grob ±30 %, Wappenfarben); bei Schrägbildern „n/a“. Es gibt keine Foto-Maske/IoU für diese Fotos.
- **Grenzen:** silber: Kappe ca. 15 % links der Foto-Kappe (Schüssel des Modells zu tief), Pitch/Roll fehlt; Kappenradius Gold weiter grob; `abgleich.py` überschreibt das Add-on im Blender-Benutzerordner (nur Testumgebung).

## Fahrzeug-Paket umgebaut (26.11., Version 0.44.0)
- Vorgabe des Nutzers: Zentrum der Vorderachse per Empty (X und Z, Picker wie bei Collections), alle 4 Räder bewegen sich mit; Räder um 90° gedreht: **Achse = Y, Radstand = X**; neuer Reiter „Eigener Reifen“ wie bei der Felge, Anpassung an die Größe; Update-Feld bei geänderten Parametern.
- Umsetzung: `build_car` hängt die vier Räder an den Anker-Empty (Radstand X, Front +X, links +Y); `car.clear_old(keep=…)` erhält den Anker; Reifenquelle *Generiert/Eigener Reifen* (`fbx.tire_fit`/`fbx.bake_tire`: Radius linear von Wulstsitz → Felgenradius, Lauffläche → Reifenradius, Breite → Reifenbreite); `car_update`-Operator und Signatur (`car_signature`) für den Hinweis „Parameter geändert“.
- Tests: `tests/car/test_car_layout.py` (Blender 5.3, 38 Prüfungen: Lage, Achse, Anker verschieben, Update, eigener Reifen inkl. 19→21 Zoll, gewählter Empty), Sichtprüfung `tests/car/render_car.py`.
- Annahme: „Zentrum des Vorderreifens in X und Z“ = Mitte der Vorderachse auf der Fahrzeugmitte (Y des Empties = Fahrzeugmittellinie). Die Panel-Oberfläche selbst (Zeichnen der Felder) ist nur im laufenden Blender prüfbar und wurde hier nicht im GUI getestet.

## Standard-Spurweite 2,00 m / 2,10 m (27.11., Version 0.51.0)
- Vorgabe des Nutzers: „Standardbreite immer 2 Meter, hinten 2,10 Meter“. Gedeutet als Spurweite (Abstand der Radmitten links/rechts): `front_track` 2000 mm, `rear_track` 2100 mm (vorher 1630/1582 mm). Felgen- und Reifenbreiten bleiben unverändert. Test in `tests/car/test_car_layout.py`.

## Felge/Reifen: automatisch frei (27.11., Version 0.50.0)
- Problem (Nutzer): Die Meshy-Felge schnitt den Reifen und war nicht ganz zu sehen; es soll immer funktionieren, nicht nur mit festen 5 mm.
- Messung: Mit der echten 992-Meshy-Felge und dem Pirelli-Reifen überlappte die Felge trotz 5 mm Versatz vorn 5,95 mm, hinten 3,71 mm; auch Foto-Felge + generierter Reifen lag im Standard etwas zu tief (die Automatik schob dort ca. 4,6 mm nach).
- Umsetzung: `rim_tyre_overlap` (Vergleich der äußersten Lage von Felge und Reifenflanke je 2-mm-Radiusring am Felgenrand, im Radsystem, Teile über `felge3d_part` markiert) und automatische Verschiebung der Felge nach außen (+1 mm Luft), je Achse; `rim_auto_clear` (Standard an); Wert am Rad-Empty und in der Meldung. 992-Beispiel: vorn +6,9 mm, hinten +4,7 mm, danach Überlappung 0 mm.
- Tests: `tests/car/test_car_layout.py` (Standard, mitgelieferter Reifen, absichtlich zu weit innen −20 mm wird erkannt und behoben, Versatz am Empty) und `tests/methods/test_methods.py` (Meshy-Felge, alle vier Räder); Diamond-Cut Volvo unverändert 98,0 % / 88,0 % / 80,0 %.
- Grenze: gemessen wird nur der Randbereich (Lippe); innen liegende Teile der Felge (Fass, Speichenfüße) werden nicht geprüft. Die Bedienfelder wurden nicht im GUI geklickt.

## Meshy mit 1–3 Bildern (27.11., Version 0.49.0)
- Auftrag: im Felgen-Tool bis zu 3 Bilder für Meshy (Multi-Image), es soll aber auch mit einem funktionieren; statt zweier fester Felder ein kleines „+“, das das nächste Feld öffnet.
- Umsetzung: `meshy_views` (sichtbare Felder), Operatoren `felge3d.meshy_view_add` (+) / `meshy_view_remove` (−), Felder `meshy_image2`/`meshy_image3` (ersetzen `meshy_multi`), `meshy_extra_images`/`meshy_extra_problem` (Datei-Prüfung), Dialog nennt Bildanzahl und Ausgabe. 1 Bild = Image to 3D, 2–3 Bilder = Multi-Image to 3D (1 Aufruf).
- Tests: `tests/methods/test_methods.py` (Plus/Minus, Reihenfolge, Bild ohne Datei abgelehnt, Kosten gleich), `tests/cloud/test_meshy_mock.py` (3 Bilder = 3 image_urls, 1 Bild = Image to 3D).
- Grenze: Bedienfeld nicht im GUI geklickt (nur Code und Tests).

## Porsche-992-Test: Meshy mit Textur, 21 Zoll vorn / 22 Zoll hinten (27.11., Version 0.48.0)
- Auftrag: Beide Testbilder (Sideview IMG_2715 + Perspektive IMG_2714, dieselbe Felge) zu Meshy, mit Textur, als Felge 21 Zoll vorn / 22 Zoll hinten; Bremsen proportional.
- Meshy: **1 Aufruf** Multi-Image to 3D (Sideview als Vorderansicht + Ausschnitt der rechten Felge aus dem Vier-Räder-Foto `porsche_992_perspektive_ausschnitt_IMG_2714.jpg`), `latest` (Meshy 7.1), mit Textur: **30 Credits, Guthaben 1040 → 1010**. Ergebnis `tests/abgleich/out/meshy/porsche_992_einzeln_IMG_2715.glb` (25 MB, nur lokal, gitignored; im Meshy-Cache `out/meshy_cache`).
- Paket: texturierte Meshy-Felge (mattschwarz, blanke Speichenflächen, Wappen und Zentralverschluss als Textur) + mitgelieferter Reifen, vorn 21 Zoll, hinten 22 Zoll; Bremse skaliert proportional (`brake_scale`, Scheibe vorn 428 mm, hinten 398 mm, Dicke und Sattel folgen); Test `tests/car/test_car_layout.py`; Bilder per `FRONT_RIM=21 REAR_RIM=22 TIRE=BUNDLED MESHY_GLB=… tests/car/render_car.py`.
- Grenzen: Die Meshy-Felge ist ein einzelnes verschmolzenes Mesh (nicht parametrisch/editierbar); das GLB (25 MB) liegt nicht auf GitHub (Größe), bei Bedarf reduzierte Fassung ablegen.

## Felge/Reifen-Versatz, Sattelstellung (27.11., Version 0.47.0)
- Vorgabe des Nutzers: Felge in Y ca. 5 mm nach außen (wird sonst vom Reifen abgeschnitten); Sättel vorn auf 3 Uhr, hinten auf 9 Uhr, immer Richtung Fahrzeugmitte wie beim Porsche.
- Umsetzung: `rim_offset` (Standard 5 mm, alle Felgenwege: Foto-/KI-Felge, parametrisch, eigene/Meshy-Felge; Rückseitenprofil für die Bremse verschiebt mit); `front_caliper_angle` = 90°, `rear_caliper_angle` = −90° (ersetzen `caliper_angle`); `build_brake(..., caliper_deg)`.
- Tests (`tests/car/test_car_layout.py`): Versatz exakt 5,00 mm an allen vier Rädern, Sattel vorn hinter der Achse (−X), hinten vor der Achse (+X), Standardwerte. Sichtprüfung `tests/car/render_car.py` (Ansichten linke Seite und schräg).
- Offen: 3 Uhr/9 Uhr ist von der linken Fahrzeugseite gemeint (Front links im Bild); bei der rechten Seite ist es spiegelbildlich, beide zeigen zur Fahrzeugmitte.

## Mitgelieferter Reifen (27.11., Version 0.46.0)
- Auftrag: Reifen aus „car-tyre-game-ready-p-zero.zip“ herauslösen (Felge und Bremsen verwerfen) und als vorinstallierten Reifen im Add-on verwenden.
- Befund zum ZIP: abgeschnitten (kein Zentralverzeichnis, die letzte Textur fehlt zu ca. 31 KB); das Modell `Maserati_Granturismo_tyres_gltf.glb` ist vollständig, die Dateien wurden aus den Dateiköpfen gerettet (in einem eigenen Ordner, ohne Pfade aus dem Archiv). 13 Teile; Reifen = `masaretti_tyer_parts00_low` (3472 Vertices), der Rest sind Felge, Schrauben, Scheibe, Sattel.
- Umsetzung: `tools/extract_tyre_asset.py` → `felge3d/assets/reifen/pzero_gt.glb` (2,4 MB, mit Textur), `reifen.json`, `QUELLE.md`; Modul `assets.py` (einmaliger Import in verborgene Collection); Reifenquelle *Mitgelieferter Reifen* mit Auswahlliste; Update-Knopf kopiert `assets/`. Test: `tests/car/test_car_layout.py` (Radius, Breite, Wulstsitz, Textur, ein Import, alle 4 Räder); Test-Installer kopieren `assets/` mit.
- **Lizenz geklärt (Nutzerangabe):** CC BY 4.0, Iftekhar.Tushar, https://skfb.ly/oNqAJ → Namensnennung eingebaut (Code, reifen.json, QUELLE.md, Preferences, Panel). Marken (Pirelli, Maserati) auf dem Reifen bleiben Rechte der Inhaber.
- Der Standard-Reifen bleibt „Generierter Reifen“; der mitgelieferte ist eine Auswahl.
- Drehung (27.11.): Standard-Drehung des mitgelieferten Reifens −90° (`standard_drehung` in `reifen.json`): „P ZERO“ oben wie beim Porsche 992, Größe rechts, PIRELLI unten links, Außenseite = beschriftete Flanke; zusätzliche Drehung/Umdrehen im Panel addiert sich. Paket mit der Meshy-Felge (vorhandenes Mesh, grau) und diesem Reifen gerendert (`MESHY_GLB=… TIRE=BUNDLED tests/car/render_car.py`).
- Fehler behoben: verborgene Quell-Collections (Meshy-Quelle, 3D-Felge, 3D-Reifen) waren nur im Viewport, nicht im Rendering verborgen und tauchten beim Rendern in Original-Größe auf (`hide_render`); Tests ergänzt.

## Drei Methoden + Sattelfarbe (26.11., Version 0.45.0)
- Vorgabe des Nutzers: oben das Bild, dann Auswahl aus **Lokale KI / Geometry Nodes (erkennt Materialien, Formen) / Meshy**; Bremssattel-Farbe nicht mehr grün, vorerst weiß.
- Umsetzung: Einstellung `method` (setzt `result_mode`/Anbieter), Operator `felge3d.create_rim` („Felge erstellen“; Meshy öffnet den Kosten-/Bestätigungsdialog), eigene Collection je Methode (`felge3d_method`), `make_meshy_rim` (GLB → sichtbare Felge in Rad-Größe, Quelle `meshy_source` für die vier Räder, die ‚Eigene Felge‘ des Nutzers wird nicht überschrieben); Meshy-Panel nur bei Methode Meshy; Sattelfarbe als Einstellung (`caliper_color`, Standard Weiß; Foto liefert nur noch die Helligkeitsstruktur).
- Tests: `tests/methods/test_methods.py` (22 Prüfungen), `tests/car/test_car_layout.py` (Sattelfarbe, rechtes Rad, Sturz, Außenseite, Anker-Z, Rad-Empty als Anker abgelehnt, `import_tire`).
- Meshy-Ausgabe wählbar (27.11.): *Mit Textur (30 Credits)* / *Nur Mesh (20 Credits)*, Credits live aus Modell/Remesh/Preisliste (`meshy_texture_mode`); Standard mit Textur; Meshy-Texturen bleiben in der Felge erhalten. Neues Testfoto IMG_2710 (Mercedes-AMG) in `fotos.json`; Lokale KI und Geometry Nodes getestet (SubD erst mit entzerrter Ellipse brauchbar), Meshy-Aufruf wartet auf Freigabe.
- Grenzen: Die Meshy-Felge ist grau (Farbe/Textur = Schritt B, noch offen); die Panel-Oberfläche wurde nicht im GUI geklickt, nur Code und Tests; der Meshy-Weg im GUI (Dialog, Job, Import) ist ohne Netz nicht ausgeführt, nur der Import aus einem GLB ist getestet.
- Reviewer-Auflagen zum Fahrzeug-Paket 0.44.0 umgesetzt: erzeugter Anker folgt der Zollgröße (Boden bei Z = 0), Rad-Empties können nicht Anker sein, zusätzliche Tests (rechtes Rad, Sturz, Außenseite, `import_tire`). Offen: Custom-Normals echter Reifen-Meshes nach der radialen Verformung nicht geprüft.

## Schritt A1 (25.11.): Meshy-Silhouette als Maske – verworfen
- Umsetzung nur im Testwerkzeug (`abgleich.py`, Option `maske_aus_meshy`, Ausrichtung der Silhouette auf die Foto-Kanten; Details und Zahlen in `tests/abgleich/experimente.md`, Blätter `out/A1_*_vergleich.png`). Add-on-Code unverändert.
- Ergebnis: **kein Gewinn → verworfen.** Fairer Vergleich bei gleichem N (gold, beide N = 10): F1 29 % → 26 %. Die größeren Abstände (26 % gegen 41 %, graphit 33 % gegen 54 %) mischen den Maskeneffekt mit dem Effekt der Speichenzahl, denn der Maskenbau wählt immer N = 10 (Meshy macht die Fenster gleichmäßig); die manuelle Symmetrie greift im Maskenbau nicht. Rohzahlen: `tests/abgleich/experimente.json`.
- Nebenbefund: Mit erzwungenem N=5 (Symmetrie MANUAL) steigt bei gold der Recall von 24 % auf 44 % und „Zuordnung sicher“ auf 85 %. Die Automatik `pick_n` wählt bei Y-Speichen N=10. Idee (noch nicht umgesetzt, braucht Regression über alle Testfelgen): bei Gleichstand das kleinere N bevorzugen, wenn die Drehung um 360°/N die Karte deckt.
- Noch offen aus dem Meshy-Plan: A2 (Tiefenprofil/Nabe aus dem Meshy-Mesh für Teller-Kurve und Nabenhöhe), B (Mesh per Foto-Projektion und Zonen-Materialien einfärben).

## Nächste Aufgaben (Reihenfolge)
0. **Verbesserungen nach Matrix-Priorität** (erst wenn die Nutzer-Noten da sind, Reihenfolge ggf. anpassen): (1) Wappen: Scheibe mit Wappen aus dem Foto auf die Kappe mappen (Material der Kappe, Foto-Ausschnitt, runde Maske); (2) Speichenform: lackierte Räder mit grauer Speichenfläche (Maske erkennt nur helle Kanten), Fenster/Speichenbreite; (3) Verschluss: Rändel (18–20 Noppen) und schwarzes Modul mit Ring; (4) Zentrum: geschlossene, weich auslaufende Nabe, Kappe vertieft; (5) Speichenfarbe: weißer/heller Lackrand.
0b. Meshy-Cache nachschärfen (Reviewer-Hinweise): `last_task_id` zu Beginn von `generate()` zurücksetzen; nach fehlgeschlagenem Remesh nicht unter dem Remesh-Schlüssel cachen; Polycount/Topologie nur bei aktivem Remesh in den Schlüssel; `meshy_erzeugen.py` mit `cache_dir`; Test zum Remesh-Fehler mit Cache.
1. ~~BBS-Regression~~ erledigt: kein Fehler, das Foto ist einfarbig silber (keine dunkle Klasse); die Änderung „gestufte Abstimmung“ wurde verworfen.
2. Punkt 4: mehrere Merkmale (Helligkeit, Sättigung, lokale Streuung, Glanzlicht) + einfacher Klassifikator, Konfidenz je Fläche; Ziel: Audi-RS-Foto „sicher“ ≥ 85 %.
3. Punkt 5: Kalibrierung per Klick (Blank-/Schwarz-Probe), unsichere Flächen markieren, Korrekturmodus (Fläche umschalten, gilt für alle Sektoren).
4. Offene Kanten am Ringübergang (Porsche 20, Volvo 0–100) auf 0 bringen.
5. Ground Truth für weitere Fotos (nach Rückmeldung zu Frage 1).

## Offene Fragen an dich
0. **Gleiche Felge?** graphit, gold und silber (Porsche 992 Turbo S, Zentralverschluss): bitte bestätigen, dass es dasselbe Design ist (dann bleibt es bei einem Meshy-Mesh für alle drei). Und: **5 oder 10 Speichen?** Der SubD-Bau erkennt bei gold 10, bei graphit 5; im Foto sieht es nach 5 Y-Speichen aus, die Fenster sind aber nicht alle gleich. Welche Symmetrie soll gelten?
0a. **„85 %“:** Ich lese deine Vorgabe als „Foto und Modell stimmen zu mindestens 85 % überein“ (IoU/Kanten). Stimmt das, oder meintest du maximal 85 % Abweichung? Aktuell erreicht nur die Kantendeckung bei graphit (Recall 80 %) in die Nähe; die übrigen Fotos liegen deutlich darunter.
1. **Ground Truth:** `tests/diamond_cut/volvo/gt.png` ist nur ein Entwurf aus Samen. Bitte prüfen/nachmalen. Für welche weiteren Fotos soll ich Ground Truth anlegen (Vorschlag: Porsche 992, Audi-RS-Nutzerfoto, Mercedes)?
2. **Ringbreite:** Im Foto ist der polierte Außenring ca. 6 mm breit, die Horn-Lippe im Modell nur „Wandstärke“ (5 mm) + Toleranz. Soll die Lippenbreite pro Foto aus dem Ring abgeleitet werden?
3. **CLAUDE.md:** Die Modellier-Regeln (Punktzahl 300–600 je Sektor, 0 offene Kanten, Crease 1,0) sind aus deinen Aussagen abgeleitet – bitte korrigieren, wo sie nicht stimmen.
5. **Lackierte Räder mit polierter Kante (neue Fotos):** Soll die schmale polierte Kante (2–3 mm) modelliert werden? Vorschlag: zusätzliche schmale Randband-Flächen entlang aller Außenkonturen (Fenster + Ring), je Foto nach Helligkeit blank/lackiert beschriftet, Crease auf beiden Seiten. Und: Soll die **Grundfarbe aus dem Foto** übernommen werden (gold, graphit), statt Schwarz?
6. **Perspektivische Fotos** (IMG_2697, IMG_2700): sollen sie unterstützt werden (Entzerrung der Ellipse) oder nur frontale Fotos?
4. **BBS/Netzfelgen:** Soll Diamond Cut bei Netzfelgen (20 Speichen) überhaupt automatisch erkannt werden, oder reicht „kein Diamond Cut“ als Standard?
