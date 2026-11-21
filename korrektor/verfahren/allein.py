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


def ausfuehren(bildpfad, name, modell, rahmenhinweis, umrechnen, fragen, max_kante):
    """`fragen(anweisung, jpeg_bytes, modell)` liefert (Antworttext, Nutzung)."""
    bildpfad = Path(bildpfad)
    daten, groesse, _ = bild.laden(bildpfad, max_kante)
    modelle = {"lesen": modell, "analyse": modell}
    start = time.time()
    meldung = None
    for _ in range(2):
        try:
            text, nutzung = fragen(anweisung(rahmenhinweis), daten, modell)
            transkription, funde, verworfen = aus_antwort(json_lesen(text), groesse, umrechnen)
            return ergebnis(bildpfad.name, name, modelle, groesse, transkription, funde,
                            time.time() - start, nutzung, verworfen=verworfen)
        except Exception as fehler:
            meldung = f"{type(fehler).__name__}: {fehler}"
    return ergebnis(bildpfad.name, name, modelle, groesse, dauer_s=time.time() - start,
                    fehlermeldung=meldung)
