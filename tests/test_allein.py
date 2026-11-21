import json

from PIL import Image

from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein

ANTWORT = json.dumps({
    "transkription": "Das Fahrad",
    "funde": [{"kategorie": "R", "gelesen": "Fahrad", "vorschlag": "Fahrrad",
               "anker_typ": "wort", "rahmen": [0.5, 0.1, 0.2, 0.05], "sicherheit": 0.9}],
})


def _foto(tmp_path):
    pfad = tmp_path / "C_1_gerade.jpg"
    Image.new("RGB", (1000, 2000), "white").save(pfad)
    return pfad


def test_erfolgreicher_lauf(tmp_path):
    def fragen(anweisung, jpeg, modell):
        return ANTWORT, {"eingabe": 10, "ausgabe": 5}

    erg = allein.ausfuehren(_foto(tmp_path), "claude", "modell-x", "hinweis",
                            anteil_zu_pixel, fragen, 2400)
    assert erg["verfahren"] == "claude" and erg["bild"] == "C_1_gerade.jpg"
    assert erg["modelle"] == {"lesen": "modell-x", "analyse": "modell-x"}
    assert erg["transkription"] == "Das Fahrad"
    assert erg["funde"][0]["anker"] == {"typ": "wort", "rahmen": [500, 200, 200, 100]}
    assert erg["nutzung"] == {"eingabe": 10, "ausgabe": 5}
    assert erg["fehlermeldung"] is None


def test_zweiter_versuch_nach_fehler(tmp_path):
    aufrufe = []

    def fragen(anweisung, jpeg, modell):
        aufrufe.append(1)
        if len(aufrufe) == 1:
            raise RuntimeError("Netz weg")
        return ANTWORT, {"eingabe": 1, "ausgabe": 1}

    erg = allein.ausfuehren(_foto(tmp_path), "gpt", "m", "h", anteil_zu_pixel, fragen, 2400)
    assert len(aufrufe) == 2 and erg["fehlermeldung"] is None


def test_ausfall_nach_zwei_fehlversuchen(tmp_path):
    def fragen(anweisung, jpeg, modell):
        return "kein JSON", {"eingabe": 1, "ausgabe": 1}

    erg = allein.ausfuehren(_foto(tmp_path), "gemini", "m", "h", anteil_zu_pixel, fragen, 2400)
    assert erg["funde"] == []
    assert "ValueError" in erg["fehlermeldung"]
