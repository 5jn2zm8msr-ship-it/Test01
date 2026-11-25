# SPDX-License-Identifier: GPL-3.0-or-later
"""
Bewertungsmatrix für den Bildabgleich (Foto <-> SubD-Nachbau).

Ablauf pro Screenshot:
  1. abgleich.py erzeugt Rendering + Vergleichsbild und legt in bewertung.json einen Eintrag mit Automesswerten an.
  2. Reviewer und Nutzer tragen je Kriterium 1–5 ein ("reviewer", "nutzer"), optional Kommentar.
  3. python tests/abgleich/auswertung.py  -> bewertung.md (Matrix) + Priorität (schlechteste zuerst) für die nächste Verbesserung.

Priorität = kleinster Mittelwert aus Reviewer und Nutzer (nur vorhandene Werte); bei Gleichstand die größere Meinungsverschiedenheit.
Meinungsverschiedenheit >= 2 Punkte wird als „klären“ markiert (dann zuerst gemeinsam ansehen, bevor etwas verbessert wird).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def mean(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def fmt(v):
    return "–" if v is None else ("%.1f" % v if isinstance(v, float) and v != int(v) else "%d" % v)


def latest_only(rows):
    """Je Foto zählt für die Priorität nur die neueste Version (letzter Eintrag im JSON); ältere bleiben im Verlauf sichtbar."""
    last = {}
    for ek in rows:
        last[ek.split(" [")[0]] = ek
    return set(last.values())


def build(rows, kriterien):
    """Gibt (markdown, prioritaetsliste) zurück."""
    ids = [k["id"] for k in kriterien]
    current = latest_only(rows)
    names = {k["id"]: k["name"] for k in kriterien}
    out = ["# Bewertungsmatrix Bildabgleich", "", "Skala: " + load("kriterien.json")["skala"], ""]
    agg = {i: [] for i in ids}
    for key, e in rows.items():
        out += ["## %s%s" % (key, (" – Version " + e["version"]) if e.get("version") else ""), ""]
        if e.get("bild"):
            out += ["![%s](%s)" % (key, e["bild"]), ""]
        out += ["| Kriterium | Auto-Messwert | Reviewer | Nutzer | Mittel | Hinweis |", "|---|---|---|---|---|---|"]
        for i in ids:
            b = e.get("bewertung", {}).get(i, {})
            r, n = b.get("reviewer"), b.get("nutzer")
            m = mean([r, n])
            note = []
            if isinstance(r, (int, float)) and isinstance(n, (int, float)) and abs(r - n) >= 2:
                note.append("**klären** (Reviewer %s, Nutzer %s)" % (r, n))
            if b.get("kommentar"):
                note.append(b["kommentar"])
            out.append("| %s | %s | %s | %s | %s | %s |" % (names[i], e.get("auto", {}).get(i, "–"), fmt(r), fmt(n), fmt(m), "; ".join(note)))
            if m is not None and key in current:
                agg[i].append((m, key, abs((r or 0) - (n or 0)) if r is not None and n is not None else 0))
        out.append("")
    prio = []
    for i in ids:
        if agg[i]:
            prio.append((mean([m for m, _, _ in agg[i]]), -max(d for _, _, d in agg[i]), i, sorted(agg[i])[0][1]))
    prio.sort()
    out += ["## Priorität für die nächste Verbesserung (schlechteste zuerst)", "", "| Rang | Kriterium | Mittel über alle Bilder | schlechtestes Bild |", "|---|---|---|---|"]
    for rank, (m, _, i, worst) in enumerate(prio, 1):
        out.append("| %d | %s | %.2f | %s |" % (rank, names[i], m, worst))
    if not prio:
        out.append("| – | noch keine Bewertung eingetragen | – | – |")
    return "\n".join(out) + "\n", prio


def main():
    rows = load("bewertung.json")
    md, prio = build(rows, load("kriterien.json")["kriterien"])
    with open(os.path.join(HERE, "bewertung.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
