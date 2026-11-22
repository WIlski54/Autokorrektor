import io
import threading
import time

import pytest
from PIL import Image

from webapp.speicher import Speicher
from webapp.warteschlange import Warteschlange


@pytest.fixture
def speicher(tmp_path):
    return Speicher(tmp_path / "daten")


def _seiten(speicher, zahl=1):
    nr = speicher.aufgabe_anlegen("Bericht", "Deutsch", 9, ["R", "Z", "Gr"], "schein")
    puffer = io.BytesIO()
    Image.new("RGB", (100, 60), "white").save(puffer, format="JPEG")
    return [speicher.arbeit_anlegen(nr, [("a.jpg", puffer.getvalue())])[0] for _ in range(zahl)]


def _zeichen(gelesen="Fahrad"):
    return {"kategorie": "R", "typ": "wort", "x": 10, "y": 20, "breite": 30, "hoehe": 8,
            "gelesen": gelesen, "vorschlag": "Fahrrad", "herkunft": "ki", "status": "offen",
            "rahmen_ki": [10, 20, 30, 8]}


def _ergebnis(**felder):
    return {"zeichen": [_zeichen()], "transkription": "Das Fahrad", "dauer_s": 1.5,
            "verworfen": 2, "fehlermeldung": None, **felder}


def _zeichen_der_seite(speicher, seite_id):
    return speicher.arbeit(speicher.seite(seite_id)["arbeit_id"])["seiten"][0]["zeichen"]


def test_erfolg_fuehrt_zu_fertig_und_gespeicherten_zeichen(speicher):
    (seite_id,) = _seiten(speicher)
    aufrufe = []

    def analysieren(nr):
        aufrufe.append((nr, speicher.seite(nr)["analyse_status"]))
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren)
    schlange.einreihen(seite_id)
    assert schlange.warten(5) is True
    assert aufrufe == [(seite_id, "laeuft")]
    seite = speicher.seite(seite_id)
    assert seite["analyse_status"] == "fertig" and seite["fehlermeldung"] is None
    assert seite["transkription"] == "Das Fahrad" and seite["dauer_s"] == 1.5
    assert seite["verworfen"] == 2 and seite["lauf"] == 1 and seite["analysiert_am"]
    assert [z["gelesen"] for z in _zeichen_der_seite(speicher, seite_id)] == ["Fahrad"]


def test_einreihen_setzt_status_wartet(speicher):
    (erste, zweite) = _seiten(speicher, 2)
    frei = threading.Event()

    def analysieren(nr):
        frei.wait(5)
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren, gleichzeitig=1)
    schlange.einreihen(erste)
    schlange.einreihen(zweite)
    assert speicher.seite(zweite)["analyse_status"] == "wartet"
    assert schlange.warten(0.05) is False
    frei.set()
    assert schlange.warten(5) is True
    assert speicher.seite(zweite)["analyse_status"] == "fertig"


def test_fehlermeldung_fuehrt_zu_fehlgeschlagen(speicher):
    (seite_id,) = _seiten(speicher)
    schlange = Warteschlange(speicher, lambda nr: _ergebnis(
        zeichen=[], fehlermeldung="RuntimeError: Netz weg"))
    schlange.einreihen(seite_id)
    assert schlange.warten(5)
    seite = speicher.seite(seite_id)
    assert seite["analyse_status"] == "fehlgeschlagen"
    assert seite["fehlermeldung"] == "RuntimeError: Netz weg"
    assert _zeichen_der_seite(speicher, seite_id) == []


def test_ausnahme_fuehrt_zu_fehlgeschlagen_und_der_rest_laeuft_weiter(speicher):
    kaputt, heil = _seiten(speicher, 2)

    def analysieren(nr):
        if nr == kaputt:
            raise KeyError("GEMINI_API_KEY")
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren, gleichzeitig=1)
    schlange.einreihen(kaputt)
    schlange.einreihen(heil)
    assert schlange.warten(5)
    seite = speicher.seite(kaputt)
    assert seite["analyse_status"] == "fehlgeschlagen"
    assert "KeyError" in seite["fehlermeldung"] and "GEMINI_API_KEY" in seite["fehlermeldung"]
    assert speicher.seite(heil)["analyse_status"] == "fertig"


def test_unbrauchbare_rueckgabe_fuehrt_zu_fehlgeschlagen(speicher):
    (seite_id,) = _seiten(speicher)
    schlange = Warteschlange(speicher, lambda nr: None)
    schlange.einreihen(seite_id)
    assert schlange.warten(5)
    seite = speicher.seite(seite_id)
    assert seite["analyse_status"] == "fehlgeschlagen" and seite["fehlermeldung"]


def test_zeitueberschreitung_und_verspaetetes_ergebnis(speicher):
    haengt, danach = _seiten(speicher, 2)
    spaet_fertig = threading.Event()

    def analysieren(nr):
        if nr == haengt:
            time.sleep(1)
            spaet_fertig.set()
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren, gleichzeitig=1, zeitgrenze_s=0.2)
    beginn = time.monotonic()
    schlange.einreihen(haengt)
    schlange.einreihen(danach)
    assert schlange.warten(5)
    # Der hängende Aufruf hat den einzigen Arbeiter nicht blockiert.
    assert time.monotonic() - beginn < 0.9 and not spaet_fertig.is_set()
    assert speicher.seite(danach)["analyse_status"] == "fertig"
    seite = speicher.seite(haengt)
    assert seite["analyse_status"] == "fehlgeschlagen"
    assert "Zeit" in seite["fehlermeldung"]

    assert spaet_fertig.wait(5)
    time.sleep(0.3)
    seite = speicher.seite(haengt)
    assert seite["analyse_status"] == "fehlgeschlagen"
    assert _zeichen_der_seite(speicher, haengt) == []


def test_neuer_versuch_gewinnt_gegen_verspaetetes_ergebnis(speicher):
    (seite_id,) = _seiten(speicher)
    aufrufe = []
    spaet_fertig = threading.Event()

    def analysieren(nr):
        aufrufe.append(nr)
        if len(aufrufe) == 1:
            time.sleep(0.8)
            spaet_fertig.set()
            return _ergebnis(zeichen=[_zeichen("alt")])
        return _ergebnis(zeichen=[_zeichen("neu")])

    schlange = Warteschlange(speicher, analysieren, zeitgrenze_s=0.2)
    schlange.einreihen(seite_id)
    assert schlange.warten(5)
    assert speicher.seite(seite_id)["analyse_status"] == "fehlgeschlagen"
    schlange.einreihen(seite_id)
    assert schlange.warten(5)
    assert spaet_fertig.wait(5)
    time.sleep(0.3)
    seite = speicher.seite(seite_id)
    assert seite["analyse_status"] == "fertig" and seite["lauf"] == 2
    assert [z["gelesen"] for z in _zeichen_der_seite(speicher, seite_id)] == ["neu"]


def test_hoechstens_gleichzeitig_viele_analysen(speicher):
    seiten = _seiten(speicher, 7)
    sperre = threading.Lock()
    stand = {"laufend": 0, "hoechstens": 0}

    def analysieren(nr):
        with sperre:
            stand["laufend"] += 1
            stand["hoechstens"] = max(stand["hoechstens"], stand["laufend"])
        time.sleep(0.1)
        with sperre:
            stand["laufend"] -= 1
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren, gleichzeitig=2)
    for seite_id in seiten:
        schlange.einreihen(seite_id)
    assert schlange.warten(10)
    assert stand["hoechstens"] == 2
    assert {speicher.seite(s)["analyse_status"] for s in seiten} == {"fertig"}


def test_doppelt_eingereihte_seite_wird_nur_einmal_bearbeitet(speicher):
    (seite_id,) = _seiten(speicher)
    aufrufe = []
    frei = threading.Event()

    def analysieren(nr):
        aufrufe.append(nr)
        frei.wait(5)
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren)
    schlange.einreihen(seite_id)
    schlange.einreihen(seite_id)
    frei.set()
    assert schlange.warten(5)
    assert aufrufe == [seite_id] and speicher.seite(seite_id)["lauf"] == 1


def test_wiederaufnehmen_reiht_unfertige_seiten_neu_ein(speicher):
    laeuft, wartet, fertig, neu = _seiten(speicher, 4)
    speicher.seite_lauf_beginnen(laeuft)  # Zustand nach einem Abbruch der App
    speicher.seite_status(wartet, "wartet")
    speicher.seite_status(fertig, "fertig")
    aufrufe = []

    def analysieren(nr):
        aufrufe.append(nr)
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren)
    schlange.wiederaufnehmen()
    assert schlange.warten(5)
    assert sorted(aufrufe) == [laeuft, wartet]
    assert speicher.seite(laeuft)["analyse_status"] == "fertig"
    assert speicher.seite(laeuft)["lauf"] == 2
    assert speicher.seite(wartet)["analyse_status"] == "fertig"
    assert speicher.seite(neu)["analyse_status"] == "neu"


def test_geloeschte_seite_wird_uebersprungen(speicher):
    (seite_id,) = _seiten(speicher)
    aufrufe = []
    schlange = Warteschlange(speicher, lambda nr: aufrufe.append(nr) or _ergebnis())
    speicher.aufgabe_loeschen(speicher.aufgaben()[0]["id"])
    schlange.einreihen(seite_id)
    assert schlange.warten(5)
    assert aufrufe == []


def test_beenden_gibt_wartende_arbeiter_frei(speicher):
    (seite_id,) = _seiten(speicher)
    frei = threading.Event()

    def analysieren(nr):
        frei.wait(5)
        return _ergebnis()

    schlange = Warteschlange(speicher, analysieren)
    schlange.einreihen(seite_id)
    time.sleep(0.1)
    schlange.beenden()
    assert schlange.warten(2) is True
    frei.set()
    # Die Seite bleibt unfertig und wird beim nächsten Start wieder aufgenommen.
    assert speicher.seiten_unfertig() == [seite_id]
