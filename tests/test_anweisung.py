import pytest

from korrektor.anweisung import AUFGABE, RAHMEN_ANTEIL, anpassen, anweisung, json_lesen


def test_anweisung_enthaelt_rahmenhinweis():
    text = anweisung(RAHMEN_ANTEIL)
    assert "buchstabengetreu" in text
    assert RAHMEN_ANTEIL in text


def test_json_lesen_mit_codezaun_und_vorrede():
    assert json_lesen('Hier:\n```json\n{"funde": []}\n```') == {"funde": []}


def test_json_lesen_mit_klammern_in_der_vorrede():
    assert json_lesen('Hinweis {so}: {"a": 1} Ende {x}') == {"a": 1}


def test_json_lesen_ohne_json():
    with pytest.raises(ValueError):
        json_lesen("kein JSON")


def test_anweisung_ohne_aufgabe_bleibt_wie_bisher():
    text = anweisung(RAHMEN_ANTEIL)
    assert text == AUFGABE.format(rahmenhinweis=RAHMEN_ANTEIL)
    assert "im Fach Deutsch, Jahrgang 9" in text
    for zeile in ("R (Rechtschreibung", "Z (Zeichensetzung)", "Gr (Grammatik)"):
        assert zeile in text
    assert anweisung(RAHMEN_ANTEIL, None) == text


def test_anweisung_mit_aufgabe_nennt_fach_jahrgang_und_nur_gewaehlte_kategorien():
    text = anweisung(RAHMEN_ANTEIL, {"fach": "Englisch", "jahrgang": 7, "kategorien": ["R"]})
    assert "im Fach Englisch, Jahrgang 7" in text
    assert "Deutsch" not in text
    assert "R (Rechtschreibung" in text
    assert "Z (Zeichensetzung)" not in text and "Gr (Grammatik)" not in text
    assert RAHMEN_ANTEIL in text and "buchstabengetreu" in text


def test_anweisung_mit_standardaufgabe_nennt_dasselbe_wie_ohne():
    text = anweisung(RAHMEN_ANTEIL, {"fach": "Deutsch", "jahrgang": 9,
                                     "kategorien": ["Gr", "R", "Z"]})
    assert " ".join(text.split()) == " ".join(anweisung(RAHMEN_ANTEIL).split())


def test_anweisung_beispiel_nennt_eine_gewaehlte_kategorie():
    text = anweisung(RAHMEN_ANTEIL, {"fach": "Deutsch", "jahrgang": 9, "kategorien": ["Z", "Gr"]})
    assert '"kategorie": "Z"' in text and '"kategorie": "R"' not in text
    assert "R (Rechtschreibung" not in text
    assert "Z (Zeichensetzung), Gr (Grammatik)." in text


def test_anpassen_wirkt_auch_auf_die_analyse_der_texterkennung():
    from korrektor.verfahren.vision_kombi import ANALYSE
    assert anpassen(ANALYSE, None) == ANALYSE
    text = anpassen(ANALYSE, {"fach": "Englisch", "jahrgang": "EF", "kategorien": ["R", "Gr"]})
    assert "im Fach Englisch, Jahrgang EF" in text
    assert "Z (Zeichensetzung)" not in text and "Gr (Grammatik)." in text
    assert text.endswith("Text:\n")


def test_fach_mit_sonderzeichen_bleibt_woertlich():
    text = anweisung(RAHMEN_ANTEIL, {"fach": r"D\1 {x}", "jahrgang": 9, "kategorien": ["R"]})
    assert r"im Fach D\1 {x}, Jahrgang 9" in text
