"""Einheitliches Ergebnisformat aller Verfahren (Spezifikation Abschnitt 5)."""
import json
from pathlib import Path


def beschneiden(rahmen, bildgroesse):
    """Hält einen Rahmen [x, y, breite, hoehe] innerhalb des Bildes."""
    x, y, b, h = rahmen
    bild_b, bild_h = bildgroesse
    x2 = min(max(x + b, 0), bild_b)
    y2 = min(max(y + h, 0), bild_h)
    x = min(max(x, 0), bild_b)
    y = min(max(y, 0), bild_h)
    return [round(x), round(y), round(x2 - x), round(y2 - y)]


def fund(nr, kategorie, gelesen, vorschlag, typ, rahmen, bildgroesse,
         sicherheit=None, unsicher=False):
    sauber = beschneiden(rahmen, bildgroesse)
    return {
        "id": nr,
        "kategorie": kategorie,
        "gelesen": gelesen,
        "vorschlag": vorschlag,
        "anker": {"typ": typ, "rahmen": sauber},
        "sicherheit": sicherheit,
        "unsicher_gelesen": unsicher,
        "rahmen_beschnitten": sauber != [round(v) for v in rahmen],
    }


def ergebnis(bild, verfahren, modelle, bildgroesse, transkription="", funde=None,
             dauer_s=0.0, nutzung=None, fehlermeldung=None):
    return {
        "bild": bild,
        "verfahren": verfahren,
        "modelle": modelle,
        "bildgroesse": list(bildgroesse),
        "transkription": transkription,
        "funde": funde or [],
        "dauer_s": round(dauer_s, 1),
        "nutzung": nutzung or {"eingabe": 0, "ausgabe": 0},
        "fehlermeldung": fehlermeldung,
    }


def pfad(wurzel, verfahren, bild):
    return Path(wurzel) / "ergebnisse" / verfahren / (Path(bild).stem + ".json")


def speichern(wurzel, erg):
    ziel = pfad(wurzel, erg["verfahren"], erg["bild"])
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(erg, ensure_ascii=False, indent=2), encoding="utf-8")
    return ziel
