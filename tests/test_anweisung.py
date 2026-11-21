import pytest

from korrektor.anweisung import RAHMEN_ANTEIL, anweisung, json_lesen


def test_anweisung_enthaelt_rahmenhinweis():
    text = anweisung(RAHMEN_ANTEIL)
    assert "buchstabengetreu" in text
    assert RAHMEN_ANTEIL in text


def test_json_lesen_mit_codezaun_und_vorrede():
    assert json_lesen('Hier:\n```json\n{"funde": []}\n```') == {"funde": []}


def test_json_lesen_ohne_json():
    with pytest.raises(ValueError):
        json_lesen("kein JSON")
