"""Gemeinsamer Ablauf für die Verfahren, in denen ein Modell alles allein macht."""
import time
from pathlib import Path

from korrektor import bild
from korrektor.anweisung import anweisung, json_lesen
from korrektor.ergebnis import ergebnis, fund


def aus_antwort(roh, bildgroesse, umrechnen):
    """Gibt (Transkription, Funde, Zahl verworfener Funde) zurück.

    Ein einzelner kaputter Fund (fehlender oder falscher Rahmen) wird verworfen und
    gezählt, statt die ganze Seite ausfallen zu lassen.
    """
    funde, verworfen = [], 0
    for f in roh.get("funde") or []:
        try:
            typ = "luecke" if f.get("anker_typ") == "luecke" else "wort"
            funde.append(fund(len(funde) + 1, f.get("kategorie"), f.get("gelesen"),
                              f.get("vorschlag"), typ,
                              umrechnen([float(v) for v in f["rahmen"]], bildgroesse),
                              bildgroesse, f.get("sicherheit")))
        except (KeyError, TypeError, ValueError, AttributeError):
            verworfen += 1
    return roh.get("transkription"), funde, verworfen


def frist_erreicht(frist):
    """Ob der Zeitpunkt `frist` (ein Wert von `time.monotonic()`) erreicht ist; ohne Frist nie."""
    return frist is not None and time.monotonic() >= frist


def ausfuehren(bildpfad, name, modell, rahmenhinweis, umrechnen, fragen, max_kante,
               aufgabe=None, frist=None):
    """`fragen(anweisung, jpeg_bytes, modell)` liefert (Antworttext, Nutzung).

    `aufgabe` ({"fach", "jahrgang", "kategorien"}) fließt in die Anweisung ein.
    Ist `frist` (ein Wert von `time.monotonic()`) erreicht, beginnt nach einem Fehler
    kein zweiter Versuch mehr.
    """
    bildpfad = Path(bildpfad)
    daten, groesse, _ = bild.laden(bildpfad, max_kante)
    modelle = {"lesen": modell, "analyse": modell}
    start = time.time()
    meldung = None
    for versuch in range(2):
        if versuch and frist_erreicht(frist):
            break  # die Zeitgrenze des Aufrufers ist überschritten: kein zweiter Versuch
        try:
            text, nutzung = fragen(anweisung(rahmenhinweis, aufgabe), daten, modell)
            transkription, funde, verworfen = aus_antwort(json_lesen(text), groesse, umrechnen)
            return ergebnis(bildpfad.name, name, modelle, groesse, transkription, funde,
                            time.time() - start, nutzung, verworfen=verworfen)
        except Exception as fehler:
            meldung = f"{type(fehler).__name__}: {fehler}"
    return ergebnis(bildpfad.name, name, modelle, groesse, dauer_s=time.time() - start,
                    fehlermeldung=meldung)
