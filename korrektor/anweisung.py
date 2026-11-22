"""Gemeinsame Anweisung für die Verfahren 1–3 und JSON-Auslesen."""
import json
import re

RAHMEN_GEMINI = ('"rahmen" ist [ymin, xmin, ymax, xmax], normiert auf 0 bis 1000 '
                 "bezogen auf Bildhöhe und Bildbreite.")
RAHMEN_ANTEIL = ('"rahmen" ist [x, y, breite, hoehe] als Anteile zwischen 0 und 1 '
                 "bezogen auf Bildbreite und Bildhöhe; x und y bezeichnen die linke obere Ecke.")

AUFGABE = """Du unterstützt eine Lehrkraft bei der Korrektur im Fach Deutsch, Jahrgang 9.
Auf dem Foto steht ein handgeschriebener Text.

1. Schreibe den Text buchstabengetreu ab: genau so, wie er dasteht, mit allen Fehlern.
   Berichtige nichts, ergänze keine Satzzeichen. Durchgestrichenes lässt du weg.
   Zeichnungen, Gedrucktes und Randnotizen ignorierst du.
2. Melde alle Fehler dieser Kategorien: R (Rechtschreibung, auch Groß-/Kleinschreibung und
   Getrennt-/Zusammenschreibung), Z (Zeichensetzung), Gr (Grammatik).
   Melde keine Stil-, Ausdrucks- oder Inhaltsfragen. Melde nur, was du sicher gelesen hast.
3. Gib zu jedem Fehler einen Rahmen an, der genau die betroffene Stelle im Foto umschließt.
   Betrifft der Fehler ein Wort oder eine Wortgruppe, ist "anker_typ" gleich "wort".
   Fehlt ein Satzzeichen, ist "anker_typ" gleich "luecke" und der Rahmen umschließt den
   Zwischenraum, in den das Zeichen gehört.
   {rahmenhinweis}

Antworte ausschließlich mit JSON in dieser Form:
{{"transkription": "...",
  "funde": [{{"kategorie": "R", "gelesen": "wie es dasteht", "vorschlag": "richtige Schreibung",
             "anker_typ": "wort", "rahmen": [0, 0, 0, 0], "sicherheit": 0.9}}]}}
Bei "luecke" enthalten "gelesen" und "vorschlag" die beiden Nachbarwörter, einmal ohne und
einmal mit dem Satzzeichen. "sicherheit" liegt zwischen 0 und 1."""


# Stellen der Anweisungstexte, die sich mit der Aufgabe ändern (auch in vision_kombi.ANALYSE).
FACH_STANDARD = "im Fach Deutsch, Jahrgang 9"
KATEGORIEN = {
    "R": "R (Rechtschreibung, auch Groß-/Kleinschreibung und Getrennt-/Zusammenschreibung)",
    "Z": "Z (Zeichensetzung)",
    "Gr": "Gr (Grammatik)",
}
_KATEGORIEN_STANDARD = re.compile(r"R \(Rechtschreibung.*?Gr \(Grammatik\)", re.DOTALL)


def anpassen(text, aufgabe):
    """Setzt Fach, Jahrgang und die eingeschalteten Kategorien in einen Anweisungstext ein.

    `aufgabe` ist {"fach", "jahrgang", "kategorien"}; ohne `aufgabe` bleibt der Text
    unverändert (Deutsch, Jahrgang 9, R, Z, Gr). Unbekannte Kürzel zählen nicht; bleibt
    keines übrig, gelten alle drei.
    """
    if not aufgabe:
        return text
    gewaehlt = [k for k in KATEGORIEN if k in (aufgabe.get("kategorien") or [])]
    gewaehlt = gewaehlt or list(KATEGORIEN)
    text = text.replace(FACH_STANDARD,
                        f"im Fach {aufgabe.get('fach') or 'Deutsch'}, "
                        f"Jahrgang {aufgabe.get('jahrgang') or 9}")
    text = _KATEGORIEN_STANDARD.sub(lambda _: ", ".join(KATEGORIEN[k] for k in gewaehlt), text)
    return text.replace('"kategorie": "R"', f'"kategorie": "{gewaehlt[0]}"')


def anweisung(rahmenhinweis, aufgabe=None):
    return anpassen(AUFGABE.format(rahmenhinweis=rahmenhinweis), aufgabe)


def json_lesen(text):
    """Liest das erste JSON-Objekt aus einer Modellantwort, auch mit Vorrede oder Codezaun."""
    dekoder = json.JSONDecoder()
    anfang = text.find("{")
    while anfang != -1:
        try:
            objekt, _ = dekoder.raw_decode(text[anfang:])
            if isinstance(objekt, dict):
                return objekt
        except json.JSONDecodeError:
            pass
        anfang = text.find("{", anfang + 1)
    raise ValueError("Antwort enthält kein JSON-Objekt")
