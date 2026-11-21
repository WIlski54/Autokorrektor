"""Misst, wie weit die Rahmen eines Verfahrens von den Wortrahmen der Texterkennung abweichen.

Bezug sind die eingerasteten Cloud-Vision-Wortrahmen (nur Funde mit Ähnlichkeit >= 0,8).
Ausgabe je Verfahren und Foto: Fundquote, Zusatzmeldungen, mittlerer und größter Abstand
der Rahmenmitten in Vielfachen der Rahmenhöhe, Anteil der Funde mit Abstand über 0,5 Höhen.
"""
import json
import statistics
import sys
from pathlib import Path

from dotenv import load_dotenv

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from korrektor import auswertung as a  # noqa: E402
from korrektor import bild  # noqa: E402
from korrektor.einrasten import einrasten  # noqa: E402
from korrektor.verfahren.vision_kombi import vision_lesen, woerter_aus_antwort  # noqa: E402


def woerter_fuer(name):
    lager = WURZEL / "ergebnisse" / "_vision_woerter" / (Path(name).stem + ".json")
    if lager.exists():
        return json.loads(lager.read_text(encoding="utf-8"))
    daten, _, faktor = bild.laden(WURZEL / "fotos" / name, 2400)
    woerter = woerter_aus_antwort(vision_lesen(daten), faktor)
    lager.parent.mkdir(parents=True, exist_ok=True)
    lager.write_text(json.dumps(woerter, ensure_ascii=False), encoding="utf-8")
    return woerter


def main():
    load_dotenv(WURZEL / ".env")
    gesamt = {}
    for datei in sorted((WURZEL / "ergebnisse").glob("*/*.json")):
        if datei.parent.name.startswith("_"):
            continue
        e = json.loads(datei.read_text(encoding="utf-8"))
        loesung = a.loesung_laden(WURZEL, e["bild"])
        if loesung is None:
            continue
        woerter = woerter_fuer(e["bild"])
        w = a.bild_auswerten(e, loesung, {})
        abst, eingerastet = [], 0
        for f in e["funde"]:
            eigen = f.get("rahmen_modell") or f["anker"]["rahmen"]
            t = einrasten(f["gelesen"], f["anker"]["typ"], eigen, woerter)
            if not t or t["aehnlichkeit"] < 0.8:
                continue
            eingerastet += 1
            x, y, b, h = eigen
            bx, by, bb, bh = t["rahmen"]
            abst.append((((x + b / 2 - bx - bb / 2) ** 2 + (y + h / 2 - by - bh / 2) ** 2) ** 0.5) / bh)
        g = gesamt.setdefault(e["verfahren"], {"gef": 0, "ges": 0, "zus": 0, "abst": [], "funde": 0,
                                               "ein": 0, "dauer": []})
        g["gef"] += w["gefunden"]; g["ges"] += w["fehler_gesamt"]; g["zus"] += w["erfunden"]
        g["abst"] += abst; g["funde"] += len(e["funde"]); g["ein"] += eingerastet
        g["dauer"].append(e["dauer_s"])
    print(f"{'Verfahren':<15}{'gefunden':>10}{'zusätzl.':>10}{'Abstand':>9}{'max':>7}{'>0,5 H':>9}{'Bezug':>9}{'Dauer':>8}")
    for name, g in sorted(gesamt.items()):
        ab = g["abst"]
        print(f"{name:<15}{g['gef']:>5}/{g['ges']:<4}{g['zus']:>10}{statistics.mean(ab):>9.2f}{max(ab):>7.2f}"
              f"{sum(v > 0.5 for v in ab):>5}/{len(ab):<3}{g['ein']:>5}/{g['funde']:<3}{statistics.mean(g['dauer']):>7.0f}s")


if __name__ == "__main__":
    main()
