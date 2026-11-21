import json

from korrektor import ergebnis


def test_beschneiden_haelt_rahmen_im_bild():
    assert ergebnis.beschneiden([-10, 20, 50, 30], (100, 40)) == [0, 20, 40, 20]
    assert ergebnis.beschneiden([10, 10, 20, 20], (100, 100)) == [10, 10, 20, 20]


def test_fund_merkt_beschneidung():
    f = ergebnis.fund(1, "R", "Fahrad", "Fahrrad", "wort", [90, 0, 30, 10], (100, 100), 0.9)
    assert f["anker"] == {"typ": "wort", "rahmen": [90, 0, 10, 10]}
    assert f["rahmen_beschnitten"] is True
    assert f["unsicher_gelesen"] is False


def test_speichern_schreibt_nach_verfahren_und_bild(tmp_path):
    erg = ergebnis.ergebnis("C_1_gerade.jpg", "gemini", {"lesen": "m", "analyse": "m"}, (100, 200))
    ziel = ergebnis.speichern(tmp_path, erg)
    assert ziel == tmp_path / "ergebnisse" / "gemini" / "C_1_gerade.json"
    gelesen = json.loads(ziel.read_text(encoding="utf-8"))
    assert gelesen["funde"] == [] and gelesen["fehlermeldung"] is None
    assert gelesen["bildgroesse"] == [100, 200]
