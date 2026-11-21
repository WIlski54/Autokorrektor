"""Einheitliches Ergebnisformat aller Verfahren (Spezifikation Abschnitt 5)."""
import json
from pathlib import Path


def beschneiden(rahmen, bildgroesse):
    """Hält einen Rahmen [x, y, breite, hoehe] innerhalb des Bildes."""
    x, y, b, h = rahmen
    bild_b, bild_h = bildgroesse
    # Vertauschte Ecken (negative Breite oder Höhe) werden sortiert.
    x1, x2 = sorted((x, x + b))
    y1, y2 = sorted((y, y + h))
    x1, x2 = (round(min(max(v, 0), bild_b)) for v in (x1, x2))
    y1, y2 = (round(min(max(v, 0), bild_h)) for v in (y1, y2))
    # Mindestens 1 Pixel, damit der Rahmen sichtbar und ausschneidbar bleibt.
    if x2 == x1:
        x1, x2 = (x1 - 1, x2) if x1 >= bild_b else (x1, x2 + 1)
    if y2 == y1:
        y1, y2 = (y1 - 1, y2) if y1 >= bild_h else (y1, y2 + 1)
    return [x1, y1, x2 - x1, y2 - y1]


def kategorie_normieren(kategorie):
    """Macht aus „Grammatik“, „z“ oder „Rechtschreibung“ die Kürzel Gr, Z, R."""
    text = str(kategorie or "").strip().lower()
    if text.startswith("g"):
        return "Gr"
    if text.startswith("z") or text.startswith("i"):  # Zeichensetzung, Interpunktion
        return "Z"
    return "R"


def fund(nr, kategorie, gelesen, vorschlag, typ, rahmen, bildgroesse,
         sicherheit=None, unsicher=False):
    rahmen = [float(v) for v in rahmen]
    if len(rahmen) != 4:
        raise ValueError("rahmen braucht vier Werte")
    sauber = beschneiden(rahmen, bildgroesse)
    return {
        "id": nr,
        "kategorie": kategorie_normieren(kategorie),
        "gelesen": str(gelesen or ""),
        "vorschlag": str(vorschlag or ""),
        "anker": {"typ": typ, "rahmen": sauber},
        "sicherheit": sicherheit,
        "unsicher_gelesen": unsicher,
        "rahmen_beschnitten": sauber != [round(v) for v in rahmen],
    }


def ergebnis(bild, verfahren, modelle, bildgroesse, transkription="", funde=None,
             dauer_s=0.0, nutzung=None, fehlermeldung=None, verworfen=0):
    return {
        "bild": bild,
        "verfahren": verfahren,
        "modelle": modelle,
        "bildgroesse": list(bildgroesse),
        "transkription": str(transkription or ""),
        "funde": funde or [],
        "verworfen": verworfen,
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
