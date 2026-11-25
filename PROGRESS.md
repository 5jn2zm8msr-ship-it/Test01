# PROGRESS – Felgen-Add-on (Branch `dev`, niemals `main`)

Arbeitsweise: nächste offene Aufgabe umsetzen → Subagent `reviewer` prüft (max. 3 Nachbesserungen, sonst verwerfen + hier notieren) → nur bei BESTANDEN committen und auf `dev` pushen → diese Datei aktualisieren.

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
