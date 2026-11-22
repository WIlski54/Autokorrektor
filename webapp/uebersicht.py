"""Zahlen der Stapelübersicht und ihr CSV-Export.

Gezählt werden nur bestätigte Zeichen aus Arbeiten, deren Korrektur insgesamt bestätigt ist.
Die Übersicht beschreibt den Stapel; sie bewertet nicht, bildet keinen Quotienten und keine
Rangfolge. Arbeiten stehen immer in Stapelreihenfolge.
"""
import csv
import io
import re
from collections import Counter

FESTE_KATEGORIEN = (("R", "Rechtschreibung"), ("Z", "Zeichensetzung"), ("Gr", "Grammatik"))
MAX_WOERTER = 20
FORMELZEICHEN = ("=", "+", "-", "@", "\t", "\r")
# Text, den eine Tabellenkalkulation in eine Zahl oder ein Datum umwandeln würde: nur Ziffern
# (auch mit führenden Nullen), Ziffern mit Punkt, Komma, Schrägstrich, Bindestrich, Doppelpunkt
# oder Leerzeichen dazwischen, ein Prozentwert oder eine Zahl mit Exponent.
WIE_ZAHL = re.compile(r"\s*\d(?:[\d\s.,/:-]*\d)?[.,]?\s*%?\s*|\s*\d+(?:[.,]\d+)?[eE][+-]?\d+\s*")

_UMLAUTE = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def _alphabetisch(text):
    """Sortierschlüssel ohne Beachtung der Großschreibung; Umlaute bei ihren Grundbuchstaben."""
    return text.casefold().translate(_UMLAUTE), text


def kategorien_ordnen(zahl, eigene):
    """Die Zählung je Kürzel als `[{"kuerzel", "bezeichnung", "anzahl"}]`.

    `zahl` ordnet Kürzeln ihre Anzahl zu, `eigene` sind die eigenen Kürzel als
    `[{kuerzel, bezeichnung}]`. R, Z, Gr stehen zuerst, dann die übrigen Kürzel alphabetisch;
    aufgenommen wird nur, was mindestens einmal vorkommt. Ein Kürzel, das es in der Liste
    nicht mehr gibt, bleibt ohne Bezeichnung.
    """
    namen = {**{e["kuerzel"]: e["bezeichnung"] for e in eigene}, **dict(FESTE_KATEGORIEN)}
    fest = [kuerzel for kuerzel, _ in FESTE_KATEGORIEN if zahl.get(kuerzel)]
    uebrige = sorted((kuerzel for kuerzel, anzahl in zahl.items()
                      if anzahl and kuerzel not in fest), key=_alphabetisch)
    return [{"kuerzel": kuerzel, "bezeichnung": namen.get(kuerzel, ""), "anzahl": zahl[kuerzel]}
            for kuerzel in fest + uebrige]


def _bestaetigte_zeichen(arbeit):
    return [z for seite in arbeit["seiten"] for z in seite["zeichen"]
            if z["status"] == "bestaetigt"]


def _woerter(arbeiten):
    """Die häufigen Fehlerwörter: Rechtschreibzeichen vom Typ `wort`, nach `gelesen`.

    Zusammengefasst ohne Beachtung der Groß-/Kleinschreibung; gezeigt wird die häufigste
    Schreibung und der häufigste Vorschlag (bei Gleichstand die zuerst gesehenen). „ß“ und
    „ss“ bleiben getrennt (`lower`, nicht `casefold`): Gerade diese Verwechslung ist ein
    Rechtschreibfehler.
    """
    gruppen = {}   # gelesen in Kleinbuchstaben -> Schreibungen, Vorschläge, Arbeiten
    for platz, arbeit in enumerate(arbeiten):
        for z in _bestaetigte_zeichen(arbeit):
            gelesen = " ".join((z["gelesen"] or "").split())
            if z["kategorie"] != "R" or z["typ"] != "wort" or not gelesen:
                continue
            gruppe = gruppen.setdefault(gelesen.lower(), (Counter(), Counter(), set()))
            gruppe[0][gelesen] += 1
            vorschlag = " ".join((z["vorschlag"] or "").split())
            if vorschlag:
                gruppe[1][vorschlag] += 1
            gruppe[2].add(platz)
    woerter = []
    for schreibungen, vorschlaege, in_arbeiten in gruppen.values():
        anzahl = sum(schreibungen.values())
        if anzahl < 2 and len(in_arbeiten) < 2:
            continue
        woerter.append({"gelesen": schreibungen.most_common(1)[0][0],
                        "vorschlag": vorschlaege.most_common(1)[0][0] if vorschlaege else "",
                        "anzahl": anzahl, "arbeiten": len(in_arbeiten)})
    woerter.sort(key=lambda wort: (-wort["anzahl"], _alphabetisch(wort["gelesen"])))
    return woerter[:MAX_WOERTER]


def stapel(speicher, aufgabe_id):
    """Die Zahlen der Stapelübersicht einer Aufgabe.

    {"arbeiten_gesamt", "arbeiten_bestaetigt",
     "kategorien": [{"kuerzel", "bezeichnung", "anzahl"}],
     "woerter":    [{"gelesen", "vorschlag", "anzahl", "arbeiten"}],
     "arbeiten":   [{"kuerzel", "seiten", "je_kategorie": {kuerzel: anzahl}, "summe"}]}

    `arbeiten` nennt die bestätigten Arbeiten in Stapelreihenfolge; `je_kategorie` führt bei
    jeder Arbeit alle Kürzel aus `kategorien` in deren Reihenfolge, auch mit 0.
    """
    reihe = speicher.arbeiten(aufgabe_id)
    bestaetigt = []
    for eintrag in reihe:
        if eintrag["bestaetigt_am"] is None:
            continue
        arbeit = speicher.arbeit(eintrag["id"])   # ein Stand je Arbeit
        if arbeit is not None and arbeit["bestaetigt_am"] is not None:
            bestaetigt.append(arbeit)
    je_arbeit = [Counter(z["kategorie"] for z in _bestaetigte_zeichen(arbeit))
                 for arbeit in bestaetigt]
    kategorien = kategorien_ordnen(sum(je_arbeit, Counter()), speicher.kuerzel())
    return {
        "arbeiten_gesamt": len(reihe),
        "arbeiten_bestaetigt": len(bestaetigt),
        "kategorien": kategorien,
        "woerter": _woerter(bestaetigt),
        "arbeiten": [{"kuerzel": arbeit["kuerzel"], "seiten": len(arbeit["seiten"]),
                      "je_kategorie": {k["kuerzel"]: zahl[k["kuerzel"]] for k in kategorien},
                      "summe": sum(zahl.values())}
                     for arbeit, zahl in zip(bestaetigt, je_arbeit)],
    }


def _zelle(wert):
    """Eine Textzelle für die Tabellenkalkulation.

    Text, der wie eine Formel beginnt, wird mit einem Hochkomma entschärft. Text, der wie
    eine Zahl oder ein Datum aussieht (`01`, `1-2`, `3/4`, `1.5`), steht als `="01"`, damit
    Excel ihn nicht umwandelt. Zahlenspalten laufen nicht hier durch.
    """
    text = str(wert)
    if text.startswith(FORMELZEICHEN):
        return "'" + text
    if WIE_ZAHL.fullmatch(text):
        return f'="{text}"'
    return text


def als_csv(daten):
    """Die Tabelle je Arbeit als CSV-Text: Semikolon als Trennzeichen, Zeilenende `\\r\\n`.

    Kopfzeile `Arbeit;Seiten;<Kürzel…>;Summe`, dann eine Zeile je bestätigter Arbeit in
    Stapelreihenfolge. `daten` ist das Ergebnis von `stapel`. Die Kürzel sind Textzellen
    (siehe `_zelle`); Seiten, Anzahlen und Summe bleiben Zahlen.
    """
    kuerzel = [k["kuerzel"] for k in daten["kategorien"]]
    puffer = io.StringIO(newline="")
    tabelle = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    tabelle.writerow([_zelle(wert) for wert in ["Arbeit", "Seiten", *kuerzel, "Summe"]])
    for arbeit in daten["arbeiten"]:
        zahlen = [arbeit["je_kategorie"].get(k, 0) for k in kuerzel]
        tabelle.writerow([_zelle(arbeit["kuerzel"]), arbeit["seiten"], *zahlen, arbeit["summe"]])
    return puffer.getvalue()
