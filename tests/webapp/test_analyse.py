import io
import sys
import types

import pytest
from PIL import Image

from webapp.analyse import seite_analysieren
from webapp.speicher import Speicher

FUNDE = [
    {"id": 1, "kategorie": "R", "gelesen": "Fahrad", "vorschlag": "Fahrrad",
     "anker": {"typ": "wort", "rahmen": [10, 20, 30, 8]}, "sicherheit": 0.9},
    {"id": 2, "kategorie": "Z", "gelesen": "kam weil", "vorschlag": "kam, weil",
     "anker": {"typ": "luecke", "rahmen": [50, 20, 4, 8]}, "sicherheit": 0.8},
]


def _ergebnis(**felder):
    return {"transkription": "Das Fahrad kam weil", "funde": FUNDE, "dauer_s": 3.2,
            "verworfen": 1, "fehlermeldung": None, **felder}


@pytest.fixture
def speicher(tmp_path):
    return Speicher(tmp_path / "daten")


@pytest.fixture
def schein(monkeypatch):
    """Hängt ein Schein-Verfahren als korrektor.verfahren.schein ein und merkt sich Aufrufe."""
    modul = types.ModuleType("korrektor.verfahren.schein")
    modul.aufrufe = []
    modul.antwort = _ergebnis()

    def ausfuehren(bildpfad, einst):
        modul.aufrufe.append((bildpfad, einst))
        return modul.antwort

    modul.ausfuehren = ausfuehren
    monkeypatch.setitem(sys.modules, "korrektor.verfahren.schein", modul)
    return modul


def _seite(speicher, kategorien=("R", "Z", "Gr"), verfahren="schein"):
    nr = speicher.aufgabe_anlegen("Bericht", "Englisch", 7, list(kategorien), verfahren)
    puffer = io.BytesIO()
    Image.new("RGB", (100, 60), "white").save(puffer, format="JPEG")
    (seite_id,) = speicher.arbeit_anlegen(nr, [("a.jpg", puffer.getvalue())])
    return seite_id


def test_funde_werden_zu_zeichen(speicher, schein):
    seite_id = _seite(speicher)
    erg = seite_analysieren(speicher, seite_id, {"max_kante": 2400})
    assert erg["transkription"] == "Das Fahrad kam weil"
    assert erg["dauer_s"] == 3.2 and erg["verworfen"] == 1 and erg["fehlermeldung"] is None
    assert erg["zeichen"] == [
        {"kategorie": "R", "typ": "wort", "x": 10, "y": 20, "breite": 30, "hoehe": 8,
         "gelesen": "Fahrad", "vorschlag": "Fahrrad", "herkunft": "ki", "status": "offen",
         "rahmen_ki": [10, 20, 30, 8]},
        {"kategorie": "Z", "typ": "luecke", "x": 50, "y": 20, "breite": 4, "hoehe": 8,
         "gelesen": "kam weil", "vorschlag": "kam, weil", "herkunft": "ki", "status": "offen",
         "rahmen_ki": [50, 20, 4, 8]},
    ]


def test_zeichen_lassen_sich_speichern(speicher, schein):
    seite_id = _seite(speicher)
    erg = seite_analysieren(speicher, seite_id, {})
    lauf = speicher.seite_lauf_beginnen(seite_id)
    assert speicher.zeichen_ersetzen(seite_id, lauf, erg["zeichen"]) is True
    arbeit = speicher.arbeit(speicher.seite(seite_id)["arbeit_id"])
    assert [z["gelesen"] for z in arbeit["seiten"][0]["zeichen"]] == ["Fahrad", "kam weil"]


def test_verfahren_bekommt_bildpfad_und_aufgabe(speicher, schein):
    seite_id = _seite(speicher, kategorien=("R", "Gr"))
    einst = {"max_kante": 2400, "modelle": {"gemini": "m"}}
    seite_analysieren(speicher, seite_id, einst)
    ((bildpfad, uebergeben),) = schein.aufrufe
    assert bildpfad == speicher.bildpfad(speicher.seite(seite_id)["bilddatei"])
    assert bildpfad.is_file()
    assert uebergeben["aufgabe"] == {"fach": "Englisch", "jahrgang": 7, "kategorien": ["R", "Gr"]}
    assert uebergeben["max_kante"] == 2400 and uebergeben["modelle"] == {"gemini": "m"}
    assert "aufgabe" not in einst  # die übergebenen Einstellungen bleiben unberührt
    assert "frist" not in uebergeben


def test_verfahren_bekommt_die_frist(speicher, schein):
    seite_analysieren(speicher, _seite(speicher), {"max_kante": 2400, "frist": 123.5})
    ((_, uebergeben),) = schein.aufrufe
    assert uebergeben["frist"] == 123.5


def test_fund_einer_ausgeschalteten_kategorie_entfaellt(speicher, schein):
    seite_id = _seite(speicher, kategorien=("R",))
    erg = seite_analysieren(speicher, seite_id, {})
    assert [z["kategorie"] for z in erg["zeichen"]] == ["R"]
    assert erg["verworfen"] == 1


def test_fehlermeldung_des_verfahrens_wird_durchgereicht(speicher, schein):
    schein.antwort = _ergebnis(funde=[], transkription="", fehlermeldung="RuntimeError: Netz weg")
    erg = seite_analysieren(speicher, _seite(speicher), {})
    assert erg["fehlermeldung"] == "RuntimeError: Netz weg"
    assert erg["zeichen"] == []


def test_unbekanntes_verfahren_und_unbekannte_seite(speicher, schein):
    with pytest.raises(ValueError):
        seite_analysieren(speicher, _seite(speicher, verfahren="../boese"), {})
    with pytest.raises(ModuleNotFoundError):
        seite_analysieren(speicher, _seite(speicher, verfahren="gibt_es_nicht"), {})
    with pytest.raises(LookupError):
        seite_analysieren(speicher, 999, {})
    assert schein.aufrufe == []
