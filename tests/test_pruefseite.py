import json

from PIL import Image

import pruefseite


def _aufbauen(tmp_path):
    (tmp_path / "fotos").mkdir()
    Image.new("RGB", (100, 50), "white").save(tmp_path / "fotos" / "C_1_gerade.jpg")
    (tmp_path / "vorlagen").mkdir()
    (tmp_path / "vorlagen" / "loesung_C.json").write_text(json.dumps({
        "soll_text": "Das Fahrad", "fallen": [],
        "fehler": [{"id": 1, "kategorie": "R", "falsch": "Fahrad", "richtig": "Fahrrad"}],
    }), encoding="utf-8")
    ziel = tmp_path / "ergebnisse" / "claude"
    ziel.mkdir(parents=True)
    fund = lambda nr, vorschlag: {"id": nr, "kategorie": "R", "gelesen": "x",
                                  "vorschlag": vorschlag,
                                  "anker": {"typ": "wort", "rahmen": [0, 0, 10, 10]}}
    (ziel / "C_1_gerade.json").write_text(json.dumps({
        "bild": "C_1_gerade.jpg", "verfahren": "claude", "bildgroesse": [100, 50],
        "funde": [fund(1, "Fahrrad"), fund(2, "Unsinn")]}), encoding="utf-8")
    pruefseite.WURZEL = tmp_path
    return pruefseite.app.test_client()


def test_daten_kennzeichnen_zuordnung(tmp_path):
    antwort = _aufbauen(tmp_path).get("/daten").get_json()
    funde = antwort["ergebnisse"][0]["funde"]
    assert [f["zugeordnet"] for f in funde] == [True, False]
    assert antwort["klicks"] == {}


def test_klick_wird_gespeichert(tmp_path):
    client = _aufbauen(tmp_path)
    client.post("/klick", json={"schluessel": "claude/C_1_gerade/2", "feld": "echt", "wert": True})
    client.post("/klick", json={"schluessel": "claude/C_1_gerade/2", "feld": "sitzt", "wert": False})
    gespeichert = json.loads((tmp_path / "pruefseite" / "klicks.json").read_text(encoding="utf-8"))
    assert gespeichert == {"claude/C_1_gerade/2": {"echt": True, "sitzt": False}}


def test_foto_wird_ausgeliefert(tmp_path):
    antwort = _aufbauen(tmp_path).get("/foto/C_1_gerade.jpg")
    assert antwort.status_code == 200 and antwort.mimetype == "image/jpeg"
