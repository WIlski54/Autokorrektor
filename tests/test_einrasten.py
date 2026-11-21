from korrektor.einrasten import einrasten


def _w(text, x, y, b=80, h=40):
    return {"text": text, "rahmen": [x, y, b, h]}


ZEILEN = [
    _w("Holz", 100, 100, 70), _w("sugel", 175, 100, 90), _w("hat", 290, 100, 50),
    _w("das", 360, 100, 50), _w("geleuchtet", 430, 100, 160),
    _w("weil", 100, 200, 60), _w("Holz", 180, 200, 70), _w("das", 270, 200, 50),
    _w(",", 322, 220, 6, 12), _w("leited", 340, 200, 100), _w(".", 442, 225, 5, 5),
]


def test_wort_rastet_auf_exakten_wortrahmen():
    ergebnis = einrasten("leited", "wort", [300, 180, 90, 50], ZEILEN)
    assert ergebnis["rahmen"] == [340, 200, 100, 40] and ergebnis["aehnlichkeit"] == 1.0


def test_zerlegtes_und_verlesenes_wort_wird_zusammengefasst():
    ergebnis = einrasten("Holzkugel", "wort", [120, 90, 150, 50], ZEILEN)
    assert ergebnis["rahmen"] == [100, 100, 165, 40]
    assert 0.6 <= ergebnis["aehnlichkeit"] < 1.0


def test_mehrfach_vorkommendes_wort_nimmt_das_naechste():
    assert einrasten("das", "wort", [350, 95, 60, 45], ZEILEN)["rahmen"] == [360, 100, 50, 40]
    assert einrasten("das", "wort", [250, 205, 60, 45], ZEILEN)["rahmen"] == [270, 200, 50, 40]


def test_luecke_liegt_zwischen_den_nachbarwoertern():
    # „geleuchtet“ steht am Zeilenende, „weil“ in der nächsten Zeile
    assert einrasten("geleuchtet weil", "luecke", [500, 110, 30, 40], ZEILEN)["rahmen"] == [590, 100, 12, 40]
    # beide Wörter in derselben Zeile
    assert einrasten("hat das", "luecke", [330, 100, 20, 40], ZEILEN)["rahmen"] == [340, 100, 20, 40]


def test_nichts_aehnliches_gibt_none():
    assert einrasten("Experiment", "wort", [0, 0, 10, 10], ZEILEN) is None
    assert einrasten("", "wort", [0, 0, 10, 10], ZEILEN) is None
    assert einrasten("das", "luecke", [0, 0, 10, 10], ZEILEN) is None
