import io

from PIL import Image

from korrektor import bild


def _foto(tmp_path, groesse):
    pfad = tmp_path / "foto.jpg"
    Image.new("RGB", groesse, "white").save(pfad)
    return pfad


def test_laden_verkleinert_und_meldet_originalgroesse(tmp_path):
    daten, groesse, faktor = bild.laden(_foto(tmp_path, (4000, 3000)), 2000)
    assert groesse == (4000, 3000)
    assert faktor == 0.5
    assert Image.open(io.BytesIO(daten)).size == (2000, 1500)


def test_laden_vergroessert_nicht(tmp_path):
    daten, groesse, faktor = bild.laden(_foto(tmp_path, (800, 600)), 2000)
    assert faktor == 1.0
    assert Image.open(io.BytesIO(daten)).size == (800, 600)


def test_ausschnitt_mit_rand(tmp_path):
    daten = bild.ausschnitt(_foto(tmp_path, (1000, 1000)), [100, 100, 200, 40], rand=0.25)
    assert Image.open(io.BytesIO(daten)).size == (220, 60)
