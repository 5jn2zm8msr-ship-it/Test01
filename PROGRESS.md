# PROGRESS – Felgen-Add-on (Branch `dev`, niemals `main`)

Arbeitsweise: nächste offene Aufgabe umsetzen → Subagent `reviewer` prüft (max. 3 Nachbesserungen, sonst verwerfen + hier notieren) → nur bei BESTANDEN committen und auf `dev` pushen → diese Datei aktualisieren.

## Stand
- Version 0.42.0 (Commit f6327a8 auf `main`, Basis von `dev`: 8f7c6aa).
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

## Erledigt (diese Sitzung, auf `main`)
Teller-Kurve, Nabenmitte, Spiegelungen, Käfig entlang der Speiche, Abgleich-Bild, Graustufen-Mapping mit Regler, Flächen-Klassifikation mit Abstimmung, Messung, Nabe/Ring in Zone und Messung.

## Nächste Aufgaben (Reihenfolge)
1. BBS-Regression beheben (20 Speichen werden komplett „poliert“, Ursache vermutlich `fill_reflections` / helle Löcher im Nabenbereich oder Bright-All-Pfad).
2. Punkt 4: mehrere Merkmale (Helligkeit, Sättigung, lokale Streuung, Glanzlicht) + einfacher Klassifikator, Konfidenz je Fläche; Ziel: Audi-RS-Foto „sicher“ ≥ 85 %.
3. Punkt 5: Kalibrierung per Klick (Blank-/Schwarz-Probe), unsichere Flächen markieren, Korrekturmodus (Fläche umschalten, gilt für alle Sektoren).
4. Offene Kanten am Ringübergang (Porsche 20, Volvo 0–100) auf 0 bringen.
5. Ground Truth für weitere Fotos (nach Rückmeldung zu Frage 1).

## Offene Fragen an dich
1. **Ground Truth:** `tests/diamond_cut/volvo/gt.png` ist nur ein Entwurf aus Samen. Bitte prüfen/nachmalen. Für welche weiteren Fotos soll ich Ground Truth anlegen (Vorschlag: Porsche 992, Audi-RS-Nutzerfoto, Mercedes)?
2. **Ringbreite:** Im Foto ist der polierte Außenring ca. 6 mm breit, die Horn-Lippe im Modell nur „Wandstärke“ (5 mm) + Toleranz. Soll die Lippenbreite pro Foto aus dem Ring abgeleitet werden?
3. **CLAUDE.md:** Die Modellier-Regeln (Punktzahl 300–600 je Sektor, 0 offene Kanten, Crease 1,0) sind aus deinen Aussagen abgeleitet – bitte korrigieren, wo sie nicht stimmen.
4. **BBS/Netzfelgen:** Soll Diamond Cut bei Netzfelgen (20 Speichen) überhaupt automatisch erkannt werden, oder reicht „kein Diamond Cut“ als Standard?
