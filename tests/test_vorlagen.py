from korrektor.vorlagen import parsen


def test_parsen_zerlegt_fehler_und_fallen():
    markup = "Das [R:Fahrad|Fahrrad] steht da, [Z:weil es|, weil es] {Rhythmus} hat."
    ergebnis = parsen(markup)
    assert ergebnis["soll_text"] == "Das Fahrad steht da, weil es Rhythmus hat."
    assert ergebnis["fehler"] == [
        {"id": 1, "kategorie": "R", "falsch": "Fahrad", "richtig": "Fahrrad"},
        {"id": 2, "kategorie": "Z", "falsch": "weil es", "richtig": ", weil es"},
    ]
    assert ergebnis["fallen"] == ["Rhythmus"]


def test_parsen_ohne_markierung():
    assert parsen("Nur Text.") == {"soll_text": "Nur Text.", "fehler": [], "fallen": []}
