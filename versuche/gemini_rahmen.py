"""Versuch: Warum sitzen die Gemini-Rahmen daneben, und welche Variante behebt es?

Bezug sind die GPT-Rahmen desselben Fotos (nach Augenschein genau). Gemessen wird je
gefundenem Lösungsfehler der Abstand der Rahmenmitten, in Vielfachen der Rahmenhöhe.

Aufruf: python versuche/gemini_rahmen.py B_1_gerade.jpg [weitere Fotos]
"""
import json
import statistics
import sys
import tomllib
from pathlib import Path

from dotenv import load_dotenv

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from korrektor import auswertung as a  # noqa: E402
from korrektor import bild  # noqa: E402
from korrektor.anweisung import AUFGABE, RAHMEN_GEMINI, json_lesen  # noqa: E402
from korrektor.koordinaten import gemini_zu_pixel  # noqa: E402
from korrektor.verfahren import gemini  # noqa: E402
from korrektor.verfahren.allein import aus_antwort  # noqa: E402

ORTEN = """Im Bild steht ein handgeschriebener Text. Finde die unten nummerierten Stellen und gib
für jede einen eng anliegenden Rahmen zurück. Bei Stellen vom Typ "luecke" umschließt der
Rahmen nur den Zwischenraum zwischen den beiden genannten Wörtern.
Antworte ausschließlich mit JSON: [{{"nr": 1, "box_2d": [ymin, xmin, ymax, xmax]}}],
Koordinaten normiert auf 0 bis 1000.

Stellen:
{stellen}"""


def umfeld(transkription, gelesen, breite=3):
    w = transkription.split()
    g = gelesen.split()
    for i in range(len(w) - len(g) + 1):
        if [x.strip(".,;:!?") for x in w[i:i + len(g)]] == [x.strip(".,;:!?") for x in g]:
            return " ".join(w[max(0, i - breite):i + len(g) + breite])
    return gelesen


def variante_einschritt(jpeg, groesse, modell, schluessel):
    """Ein Aufruf wie bisher; `schluessel` ist der Name des Rahmenfelds in der Antwort."""
    text = AUFGABE.format(rahmenhinweis=RAHMEN_GEMINI).replace('"rahmen"', f'"{schluessel}"')
    antwort, _ = gemini.fragen(text, jpeg, modell)
    roh = json_lesen(antwort)
    for f in roh.get("funde") or []:
        if schluessel in f:
            f["rahmen"] = f.pop(schluessel)
    return aus_antwort(roh, groesse, gemini_zu_pixel)


def variante_zweischritt(jpeg, groesse, modell):
    """Erst lesen und analysieren, dann die Fundstellen in einem eigenen Aufruf orten."""
    transkription, funde, _ = variante_einschritt(jpeg, groesse, modell, "rahmen")
    stellen = "\n".join(
        f'{f["id"]}: "{f["gelesen"]}" (Typ {f["anker"]["typ"]}; im Zusammenhang: '
        f'"{umfeld(transkription, f["gelesen"])}")' for f in funde)
    antwort, _ = gemini.fragen(ORTEN.format(stellen=stellen), jpeg, modell)
    start = antwort.find("[")
    liste = json.loads(antwort[start:antwort.rfind("]") + 1])
    orte = {int(e["nr"]): e["box_2d"] for e in liste if "box_2d" in e}
    for f in funde:
        if f["id"] in orte:
            x, y, b, h = gemini_zu_pixel([float(v) for v in orte[f["id"]]], groesse)
            f["anker"]["rahmen"] = [round(x), round(y), round(b), round(h)]
    return transkription, funde, 0


def abstaende(funde, bezug, fehler):
    """Mittenabstand je Lösungsfehler in Vielfachen der Bezugshöhe: (dx, dy)."""
    zu, _ = a.zuordnen(funde, fehler)
    werte = []
    for f in funde:
        for nr in zu.get(f["id"], [])[:1]:
            if nr in bezug:
                x, y, b, h = f["anker"]["rahmen"]
                bx, by, bb, bh = bezug[nr]
                werte.append(((x + b / 2 - bx - bb / 2) / bh, (y + h / 2 - by - bh / 2) / bh))
    return werte


def main():
    load_dotenv(WURZEL / ".env")
    einst = tomllib.loads((WURZEL / "einstellungen.toml").read_text(encoding="utf-8"))
    modell = einst["modelle"]["gemini"]
    varianten = {
        "A bisher (Feld rahmen)": lambda j, g, k: variante_einschritt(j, g, modell, "rahmen"),
        "B Feld box_2d": lambda j, g, k: variante_einschritt(j, g, modell, "box_2d"),
        "C zwei Schritte": lambda j, g, k: variante_zweischritt(j, g, modell),
        "D box_2d, Kante 1536": None,
    }
    for name in sys.argv[1:]:
        loesung = a.loesung_laden(WURZEL, name)
        gpt = json.loads((WURZEL / "ergebnisse" / "gpt" / (Path(name).stem + ".json"))
                         .read_text(encoding="utf-8"))
        zu, _ = a.zuordnen(gpt["funde"], loesung["fehler"])
        bezug = {nr: f["anker"]["rahmen"] for f in gpt["funde"] for nr in zu.get(f["id"], [])[:1]}
        print(f"\n######## {name} ({len(bezug)} Bezugsrahmen von GPT)")
        for titel, lauf in varianten.items():
            kante = 1536 if titel.startswith("D") else einst["max_kante"]
            jpeg, groesse, _ = bild.laden(WURZEL / "fotos" / name, kante)
            if lauf is None:
                lauf = lambda j, g, k: variante_einschritt(j, g, modell, "box_2d")
            try:
                _, funde, _ = lauf(jpeg, groesse, kante)
            except Exception as fehler:
                print(f"{titel:<24} FEHLER {type(fehler).__name__}: {str(fehler)[:120]}")
                continue
            w = abstaende(funde, bezug, loesung["fehler"])
            if not w:
                print(f"{titel:<24} keine vergleichbaren Funde")
                continue
            dx = [v[0] for v in w]
            dy = [v[1] for v in w]
            betrag = [(x * x + y * y) ** 0.5 for x, y in w]
            print(f"{titel:<24} n={len(w):>2}  mittl. Abstand {statistics.mean(betrag):.2f} H  "
                  f"max {max(betrag):.2f} H  dx {statistics.mean(dx):+.2f}  dy {statistics.mean(dy):+.2f}  "
                  f"über 1 H daneben: {sum(v > 1 for v in betrag)}")


if __name__ == "__main__":
    main()
