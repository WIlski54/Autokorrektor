"""Verfahren 4: Cloud Vision liest und verortet, ein Sprachmodell analysiert und prüft gegen."""
from korrektor.ergebnis import fund
from korrektor.koordinaten import ecken_zu_rahmen, luecke, vereinigen

NAME = "vision_kombi"

ANALYSE = """Du unterstützt eine Lehrkraft bei der Korrektur im Fach Deutsch, Jahrgang 9.
Unten steht ein handgeschriebener Text, den eine Texterkennung gelesen hat. Vor jedem Wort
und Satzzeichen steht seine Nummer in eckigen Klammern. Die Texterkennung kann sich verlesen
haben; melde nur, was nach einem echten Fehler des Schreibers aussieht.

Melde alle Fehler dieser Kategorien: R (Rechtschreibung, auch Groß-/Kleinschreibung und
Getrennt-/Zusammenschreibung), Z (Zeichensetzung), Gr (Grammatik).
Melde keine Stil-, Ausdrucks- oder Inhaltsfragen.

Betrifft der Fehler ein Wort oder eine Wortgruppe, ist "anker_typ" gleich "wort" und
"wort_von" bis "wort_bis" (einschließlich) nennen die betroffenen Nummern.
Fehlt ein Satzzeichen, ist "anker_typ" gleich "luecke" und "wort_von" sowie "wort_bis"
nennen beide die Nummer des Wortes VOR der Stelle, an die das Zeichen gehört.

Antworte ausschließlich mit JSON in dieser Form:
{"funde": [{"kategorie": "R", "gelesen": "wie es dasteht", "vorschlag": "richtige Schreibung",
            "anker_typ": "wort", "wort_von": 0, "wort_bis": 0, "sicherheit": 0.9}]}
Bei "luecke" enthalten "gelesen" und "vorschlag" die beiden Nachbarwörter, einmal ohne und
einmal mit dem Satzzeichen. "sicherheit" liegt zwischen 0 und 1.

Text:
"""

BUCHSTABIEREN = ("Auf dem Bild steht ein handgeschriebenes Wort oder eine kurze Wortgruppe. "
                 "Schreibe buchstabengetreu ab, was dasteht, auch wenn es falsch geschrieben ist. "
                 "Antworte nur mit dem Abgeschriebenen, ohne Anführungszeichen und ohne Erklärung.")


def woerter_aus_antwort(annotation, faktor):
    """Macht aus der Vision-Antwort eine flache Wortliste in Originalkoordinaten."""
    woerter = []
    for seite in annotation.pages:
        for block in seite.blocks:
            for absatz in block.paragraphs:
                for wort in absatz.words:
                    ecken = [(e.x, e.y) for e in wort.bounding_box.vertices]
                    woerter.append({
                        "text": "".join(zeichen.text for zeichen in wort.symbols),
                        "rahmen": ecken_zu_rahmen(ecken, faktor),
                        "sicherheit": wort.confidence,
                    })
    return woerter


def nummerierter_text(woerter):
    return " ".join(f"[{nr}]{wort['text']}" for nr, wort in enumerate(woerter))


def funde_bauen(roh, woerter, bildgroesse):
    funde = []
    for f in roh.get("funde", []):
        von = int(f["wort_von"])
        bis = int(f.get("wort_bis", von))
        if not 0 <= von <= bis < len(woerter):
            continue
        typ = f.get("anker_typ", "wort")
        if typ == "luecke":
            rechts = woerter[von + 1]["rahmen"] if von + 1 < len(woerter) else None
            rahmen = luecke(woerter[von]["rahmen"], rechts)
        else:
            rahmen = vereinigen([wort["rahmen"] for wort in woerter[von:bis + 1]])
        eintrag = fund(len(funde) + 1, f["kategorie"], f.get("gelesen", ""),
                       f.get("vorschlag", ""), typ, rahmen, bildgroesse, f.get("sicherheit"))
        eintrag["woerter"] = [von, bis]
        funde.append(eintrag)
    return funde


def ist_unsicher(ocr_text, buchstabiert, sicherheiten, schwelle):
    """Unsicher, wenn die Gegenlesung abweicht oder die Texterkennung selbst zweifelt."""
    gleich = ocr_text.strip() == buchstabiert.strip().strip(".,;:!?\"„“ ")
    return (not gleich) or min(sicherheiten) < schwelle
