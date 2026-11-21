"""Gemeinsamer Ablauf für die Verfahren, in denen ein Modell alles allein macht."""
import time
from pathlib import Path

from korrektor import bild
from korrektor.anweisung import anweisung, json_lesen
from korrektor.ergebnis import ergebnis, fund


def aus_antwort(roh, bildgroesse, umrechnen):
    funde = []
    for nr, f in enumerate(roh.get("funde", []), 1):
        funde.append(fund(nr, f["kategorie"], f.get("gelesen", ""), f.get("vorschlag", ""),
                          f.get("anker_typ", "wort"), umrechnen(f["rahmen"], bildgroesse),
                          bildgroesse, f.get("sicherheit")))
    return roh.get("transkription", ""), funde


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
            transkription, funde = aus_antwort(json_lesen(text), groesse, umrechnen)
            return ergebnis(bildpfad.name, name, modelle, groesse, transkription, funde,
                            time.time() - start, nutzung)
        except Exception as fehler:
            meldung = f"{type(fehler).__name__}: {fehler}"
    return ergebnis(bildpfad.name, name, modelle, groesse, dauer_s=time.time() - start,
                    fehlermeldung=meldung)
