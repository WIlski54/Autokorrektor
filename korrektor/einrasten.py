"""Lässt den ungefähren Rahmen eines Funds auf die Wortrahmen der Texterkennung einrasten.

Das Sprachmodell liefert, was gelesen wurde, und einen groben Rahmen. Die Texterkennung
liefert exakte Rahmen je Wort, liest aber schlechter. Gesucht wird die Wortfolge der
Texterkennung, die dem Gelesenen am ähnlichsten ist; bei mehrfach vorkommenden Wörtern
entscheidet die Nähe zum groben Rahmen.
"""
import difflib
import re
import statistics

from korrektor.koordinaten import luecke, vereinigen


def _norm(text):
    return re.sub(r"[\W_]", "", text)


def _aehnlich(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _mitte(rahmen):
    return rahmen[0] + rahmen[2] / 2, rahmen[1] + rahmen[3] / 2


def einrasten(gelesen, typ, grob, woerter, min_aehnlichkeit=0.6):
    """Gibt {"rahmen": [x, y, b, h], "aehnlichkeit": 0..1} zurück oder None.

    `woerter`: Liste von {"text", "rahmen"} in Lesereihenfolge (Cloud Vision).
    `typ`: "wort" (Rahmen um die Wortfolge) oder "luecke" (Zwischenraum vor dem letzten
    Wort des Gelesenen).
    """
    inhalt = [w for w in woerter if _norm(w["text"])]
    teile = [_norm(t) for t in (gelesen or "").split() if _norm(t)]
    if not inhalt or not teile or (typ == "luecke" and len(teile) < 2):
        return None
    ziel = "".join(teile)
    gx, gy = _mitte(grob)
    zeilenhoehe = statistics.median(w["rahmen"][3] for w in inhalt) or 1
    links_ziel, rechts_ziel = "".join(teile[:-1]), teile[-1]

    def luecke_im(fenster):
        """Zwischenraum vor dem Teil des Fensters, der dem letzten Wort des Gelesenen entspricht."""
        schnitt = max(range(1, len(fenster)), key=lambda k: (
            _aehnlich("".join(_norm(w["text"]) for w in fenster[:k]), links_ziel)
            + _aehnlich("".join(_norm(w["text"]) for w in fenster[k:]), rechts_ziel)))
        return luecke(fenster[schnitt - 1]["rahmen"], fenster[schnitt]["rahmen"])

    bester = None
    for start in range(len(inhalt)):
        for laenge in range(2 if typ == "luecke" else 1, len(teile) + 3):
            fenster = inhalt[start:start + laenge]
            if len(fenster) < laenge:
                break
            aehnlichkeit = _aehnlich("".join(_norm(w["text"]) for w in fenster), ziel)
            if aehnlichkeit < min_aehnlichkeit:
                continue
            rahmen = luecke_im(fenster) if typ == "luecke" else vereinigen(
                [w["rahmen"] for w in fenster])
            fx, fy = _mitte(rahmen)
            abstand = ((fx - gx) ** 2 + (fy - gy) ** 2) ** 0.5 / zeilenhoehe
            wert = aehnlichkeit - 0.03 * min(abstand, 20)
            if bester is None or wert > bester[0]:
                bester = (wert, aehnlichkeit, rahmen)
    if bester is None:
        return None
    return {"rahmen": bester[2], "aehnlichkeit": bester[1]}
