from types import SimpleNamespace as N

from korrektor.verfahren import vision_kombi as vk


def _wort(text, x, y, b, h, sicherheit):
    ecken = [N(x=x, y=y), N(x=x + b, y=y), N(x=x + b, y=y + h), N(x=x, y=y + h)]
    return N(symbols=[N(text=z) for z in text], bounding_box=N(vertices=ecken),
             confidence=sicherheit)


def _annotation(*woerter):
    return N(pages=[N(blocks=[N(paragraphs=[N(words=list(woerter))])])])


WOERTER = [
    {"text": "Das", "rahmen": [100, 100, 60, 40], "sicherheit": 0.99},
    {"text": "Fahrad", "rahmen": [180, 100, 120, 40], "sicherheit": 0.95},
    {"text": "steht", "rahmen": [320, 100, 90, 40], "sicherheit": 0.5},
]


def test_woerter_aus_antwort_rechnet_auf_originalgroesse():
    annotation = _annotation(_wort("Das", 50, 50, 30, 20, 0.99))
    assert vk.woerter_aus_antwort(annotation, 0.5) == [
        {"text": "Das", "rahmen": [100, 100, 60, 40], "sicherheit": 0.99}]


def test_nummerierter_text():
    assert vk.nummerierter_text(WOERTER) == "[0]Das [1]Fahrad [2]steht"


def test_funde_bauen_wort_und_luecke():
    roh = {"funde": [
        {"kategorie": "R", "gelesen": "Fahrad", "vorschlag": "Fahrrad",
         "anker_typ": "wort", "wort_von": 1, "wort_bis": 1, "sicherheit": 0.9},
        {"kategorie": "Z", "gelesen": "Das Fahrad", "vorschlag": "Das, Fahrad",
         "anker_typ": "luecke", "wort_von": 0, "wort_bis": 0, "sicherheit": 0.7},
        {"kategorie": "R", "gelesen": "x", "vorschlag": "y",
         "anker_typ": "wort", "wort_von": 7, "wort_bis": 9},
    ]}
    funde = vk.funde_bauen(roh, WOERTER, (1000, 1000))
    assert len(funde) == 2
    assert funde[0]["anker"] == {"typ": "wort", "rahmen": [180, 100, 120, 40]}
    assert funde[0]["woerter"] == [1, 1]
    assert funde[1]["anker"] == {"typ": "luecke", "rahmen": [160, 100, 20, 40]}


def test_ist_unsicher():
    assert vk.ist_unsicher("Fahrad", "Fahrad", [0.95], 0.6) is False
    assert vk.ist_unsicher("Fahrad", " Fahrad. ", [0.95], 0.6) is False
    assert vk.ist_unsicher("Fahrad", "Fahrrad", [0.95], 0.6) is True
    assert vk.ist_unsicher("steht", "steht", [0.5], 0.6) is True
