from korrektor import bericht

SUMME = {"seiten": 2, "fehler_gesamt": 20, "gefunden": 18, "erfunden": 2, "lesetreu": 12,
         "lesetreue_gesamt": 16, "fallen": 1, "fallen_gesamt": 8, "platz_sitzt": 17,
         "platz_geprueft": 18, "platz_offen": 0, "ausfall": 0, "dauer_s": 14.0,
         "eingabe": 4000, "ausgabe": 900,
         "nach_kategorie": {"R": [10, 12], "Z": [6, 6], "Gr": [2, 2]}}
SCHWELLEN = {"gefunden_min": 0.85, "erfunden_pro_seite_max": 1.0, "platzierung_min": 0.9}


def test_prozent():
    assert bericht.prozent(0.9) == "90 %" and bericht.prozent(None) == "–"


def test_html_enthaelt_kennzahlen_und_urteil():
    fund = {"id": 3, "kategorie": "R", "gelesen": "Rhythmus", "vorschlag": "Rythmus"}
    auswertung = {"claude": {"gesamt": SUMME, "gerade": SUMME, "schraeg": None,
                             "erfundene": [("C_1_gerade.jpg", fund)]}}
    html = bericht.html(auswertung, SCHWELLEN, {("claude", "C_1_gerade.jpg", 3): "bericht_bilder/x.jpg"})
    assert "claude" in html and "90 %" in html and "bestanden" in html
    assert "Rythmus" in html and "bericht_bilder/x.jpg" in html
    assert "10/12" in html
