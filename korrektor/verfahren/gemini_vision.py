"""Verfahren 5: Gemini liest und findet Fehler, Cloud Vision liefert die exakten Rahmen.

Beide Aufrufe laufen gleichzeitig. Jeder Fund rastet auf die Wortrahmen der Texterkennung
ein; gelingt das nicht (Texterkennung hat die Stelle zu stark verlesen oder ist
ausgefallen), bleibt der Rahmen von Gemini stehen.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from korrektor import bild
from korrektor.anweisung import RAHMEN_GEMINI, anweisung, json_lesen
from korrektor.einrasten import einrasten
from korrektor.ergebnis import beschneiden, ergebnis
from korrektor.koordinaten import gemini_zu_pixel
from korrektor.verfahren import gemini
from korrektor.verfahren.allein import aus_antwort
from korrektor.verfahren.vision_kombi import vision_lesen, woerter_aus_antwort

NAME = "gemini_vision"


def funde_einrasten(funde, woerter, groesse):
    """Ersetzt die Rahmen der Funde durch eingerastete; merkt sich die Herkunft."""
    for f in funde:
        f["rahmen_modell"] = f["anker"]["rahmen"]
        treffer = einrasten(f["gelesen"], f["anker"]["typ"], f["anker"]["rahmen"], woerter)
        if treffer:
            f["anker"]["rahmen"] = beschneiden(treffer["rahmen"], groesse)
            f["anker_quelle"] = "vision"
            f["einrast_aehnlichkeit"] = round(treffer["aehnlichkeit"], 2)
        else:
            f["anker_quelle"] = "modell"
    return funde


def ausfuehren(bildpfad, einst):
    bildpfad = Path(bildpfad)
    modell = einst["modelle"]["gemini"]
    modelle = {"lesen": modell, "analyse": modell, "rahmen": "cloud-vision-document-text"}
    daten, groesse, faktor = bild.laden(bildpfad, einst["max_kante"])
    start = time.time()
    meldung = None
    for _ in range(2):
        try:
            with ThreadPoolExecutor(max_workers=2) as gleichzeitig:
                vision_lauf = gleichzeitig.submit(vision_lesen, daten)
                gemini_lauf = gleichzeitig.submit(
                    gemini.fragen, anweisung(RAHMEN_GEMINI, einst.get("aufgabe")), daten, modell)
            text, nutzung = gemini_lauf.result()
            transkription, funde, verworfen = aus_antwort(json_lesen(text), groesse,
                                                          gemini_zu_pixel)
            try:
                woerter = woerter_aus_antwort(vision_lauf.result(), faktor)
            except Exception:  # Texterkennung ausgefallen: Rahmen von Gemini behalten
                woerter = []
            funde_einrasten(funde, woerter, groesse)
            return ergebnis(bildpfad.name, NAME, modelle, groesse, transkription, funde,
                            time.time() - start, nutzung, verworfen=verworfen)
        except Exception as fehler:
            meldung = f"{type(fehler).__name__}: {fehler}"
    return ergebnis(bildpfad.name, NAME, modelle, groesse, dauer_s=time.time() - start,
                    fehlermeldung=meldung)
