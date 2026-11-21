"""Gemeinsame Anweisung für die Verfahren 1–3 und JSON-Auslesen."""
import json

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


def anweisung(rahmenhinweis):
    return AUFGABE.format(rahmenhinweis=rahmenhinweis)


def json_lesen(text):
    """Liest das erste JSON-Objekt aus einer Modellantwort, auch mit Vorrede oder Codezaun."""
    anfang, ende = text.find("{"), text.rfind("}")
    if anfang == -1 or ende <= anfang:
        raise ValueError("Antwort enthält kein JSON-Objekt")
    return json.loads(text[anfang:ende + 1])
