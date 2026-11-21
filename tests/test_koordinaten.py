from korrektor import koordinaten as k

GROESSE = (1000, 2000)


def test_gemini_zu_pixel():
    assert k.gemini_zu_pixel([100, 200, 150, 500], GROESSE) == [200, 200, 300, 100]


def test_anteil_zu_pixel():
    assert k.anteil_zu_pixel([0.2, 0.1, 0.3, 0.05], GROESSE) == [200, 200, 300, 100]


def test_ecken_zu_rahmen_rechnet_verkleinerung_zurueck():
    ecken = [(100, 100), (250, 104), (250, 150), (100, 146)]
    assert k.ecken_zu_rahmen(ecken, 0.5) == [200, 200, 300, 100]


def test_vereinigen():
    assert k.vereinigen([[10, 10, 20, 10], [40, 5, 10, 20]]) == [10, 5, 40, 20]


def test_luecke_in_derselben_zeile():
    assert k.luecke([100, 50, 80, 40], [200, 52, 60, 40]) == [180, 50, 20, 40]


def test_luecke_am_zeilenende():
    assert k.luecke([900, 50, 80, 40], [20, 110, 60, 40]) == [980, 50, 12, 40]
    assert k.luecke([900, 50, 80, 40], None) == [980, 50, 12, 40]
