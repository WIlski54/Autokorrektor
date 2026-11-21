"""Gibt Lesung und Funde je Verfahren für ein Foto aus (Hilfsskript zum Nachsehen)."""
import json
import sys
from pathlib import Path

from korrektor import auswertung as a

bild = sys.argv[1]
L = a.loesung_laden(".", bild)
for datei in sorted(Path("ergebnisse").glob(f"*/{Path(bild).stem}.json")):
    e = json.loads(datei.read_text(encoding="utf-8"))
    w = a.bild_auswerten(e, L, a.klicks_laden("."))
    z, d = a.zuordnen(e["funde"], L["fehler"])
    print(f"\n== {e['verfahren']}: gefunden {w['gefunden']}/{w['fehler_gesamt']}, "
          f"lesetreu {w['lesetreu']}/{w['lesetreue_gesamt']}, nicht zugeordnet {w['erfunden']}, "
          f"Dubletten {w['dubletten']}, Fallen {w['fallen']}/{w['fallen_gesamt']}, "
          f"Dauer {e['dauer_s']} s, Fehlermeldung {e['fehlermeldung']}")
    print("   LESUNG:", e["transkription"].replace("\n", " / "))
    gef = {n for ids in z.values() for n in ids}
    print("   nicht gefunden:", [f"{x['falsch']}→{x['richtig']}" for x in L["fehler"] if x["id"] not in gef])
    for f in e["funde"]:
        marke = "" if f["id"] in z else ("DUBLETTE" if f["id"] in d else "OFFEN")
        zusatz = f"unsicher; Gegenlesung={f.get('gegenlesung')!r}" if f.get("unsicher_gelesen") else ""
        print(f"   {f['id']:>2} {f['kategorie']:<2} {f['gelesen']!r} → {f['vorschlag']!r} {marke} {zusatz}")
