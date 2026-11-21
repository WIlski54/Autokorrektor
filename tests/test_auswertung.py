import json

from korrektor import auswertung as a

LOESUNG = {
    "soll_text": "Das Fahrad steht da weil es Rhythmus hat.",
    "fehler": [
        {"id": 1, "kategorie": "R", "falsch": "Fahrad", "richtig": "Fahrrad"},
        {"id": 2, "kategorie": "Z", "falsch": "da weil", "richtig": "da, weil"},
    ],
    "fallen": ["Rhythmus"],
}


def _fund(nr, kategorie, gelesen, vorschlag):
    return {"id": nr, "kategorie": kategorie, "gelesen": gelesen, "vorschlag": vorschlag,
            "anker": {"typ": "wort", "rahmen": [0, 0, 10, 10]}}


def _ergebnis(funde, transkription, fehlermeldung=None):
    return {"bild": "C_1_gerade.jpg", "verfahren": "x", "transkription": transkription,
            "funde": funde, "dauer_s": 2.0, "nutzung": {"eingabe": 100, "ausgabe": 50},
            "fehlermeldung": fehlermeldung}


def test_enthaelt_und_passt():
    assert a.enthaelt(["a", "b", "c"], ["b", "c"]) and not a.enthaelt(["a", "b"], ["b", "a"])
    assert a.passt("das Fahrrad", "Fahrrad") and a.passt("da, weil", "steht da, weil es")
    assert not a.passt("Fahrrad", "da, weil") and not a.passt("", "Fahrrad")


def test_alles_gefunden():
    funde = [_fund(1, "R", "Fahrad", "Fahrrad"), _fund(2, "Z", "da weil", "da, weil")]
    klicks = {"x/C_1_gerade/1": {"sitzt": True}, "x/C_1_gerade/2": {"sitzt": False}}
    w = a.bild_auswerten(_ergebnis(funde, LOESUNG["soll_text"]), LOESUNG, klicks)
    assert (w["gefunden"], w["fehler_gesamt"], w["erfunden"]) == (2, 2, 0)
    assert (w["lesetreu"], w["lesetreue_gesamt"]) == (1, 1)
    assert (w["platz_sitzt"], w["platz_geprueft"], w["platz_offen"]) == (1, 2, 0)
    assert w["nach_kategorie"] == {"R": [1, 1], "Z": [1, 1], "Gr": [0, 0]}
    assert w["fallen"] == 0 and w["fallen_gesamt"] == 1


def test_nichts_gefunden_und_still_berichtigt():
    w = a.bild_auswerten(_ergebnis([], "Das Fahrrad steht da, weil es Rhythmus hat."),
                         LOESUNG, {})
    assert (w["gefunden"], w["erfunden"], w["lesetreu"]) == (0, 0, 0)


def test_gemischt_mit_erfundenem_fund_und_falle():
    funde = [_fund(1, "R", "Fahrad", "Fahrrad"), _fund(2, "R", "Rhythmus", "Rythmus"),
             _fund(3, "R", "hat", "hatt")]
    klicks = {"x/C_1_gerade/3": {"echt": True, "sitzt": True}}
    w = a.bild_auswerten(_ergebnis(funde, LOESUNG["soll_text"]), LOESUNG, klicks)
    assert (w["gefunden"], w["erfunden"], w["fallen"]) == (1, 1, 1)
    assert w["erfundene"] == [funde[1]]
    assert (w["platz_sitzt"], w["platz_geprueft"], w["platz_offen"]) == (1, 1, 1)


def test_ausfall_wird_gezaehlt():
    w = a.bild_auswerten(_ergebnis([], "", "RuntimeError: x"), LOESUNG, {})
    assert w["ausfall"] == 1


def test_kennzahlen_und_schwelle():
    summe = a.summieren([
        {"seiten": 1, "fehler_gesamt": 10, "gefunden": 9, "erfunden": 1, "lesetreu": 6,
         "lesetreue_gesamt": 8, "fallen": 0, "fallen_gesamt": 4, "platz_sitzt": 9,
         "platz_geprueft": 9, "platz_offen": 0, "ausfall": 0, "dauer_s": 2.0, "eingabe": 1,
         "ausgabe": 1, "nach_kategorie": {"R": [5, 6], "Z": [3, 3], "Gr": [1, 1]},
         "erfundene": []}] * 2)
    k = a.kennzahlen(summe)
    assert k["gefunden"] == 0.9 and k["erfunden_pro_seite"] == 1.0
    assert k["platzierung"] == 1.0 and k["lesetreue"] == 0.75
    assert summe["nach_kategorie"]["R"] == [10, 12]
    schwellen = {"gefunden_min": 0.85, "erfunden_pro_seite_max": 1.0, "platzierung_min": 0.9}
    assert a.bestanden(k, schwellen) is True
    assert a.bestanden({**k, "gefunden": 0.8}, schwellen) is False
    assert a.bestanden({**k, "platzierung": None}, schwellen) is False


def test_loesung_laden_bevorzugt_abschrift(tmp_path):
    ordner = tmp_path / "vorlagen"
    ordner.mkdir()
    (ordner / "loesung_C.json").write_text(json.dumps({"k": "allgemein"}), encoding="utf-8")
    (ordner / "loesung_C_2.json").write_text(json.dumps({"k": "abschrift"}), encoding="utf-8")
    assert a.loesung_laden(tmp_path, "C_1_gerade.jpg") == {"k": "allgemein"}
    assert a.loesung_laden(tmp_path, "C_2_schraeg.jpg") == {"k": "abschrift"}
    assert a.loesung_laden(tmp_path, "X_1_gerade.jpg") is None
