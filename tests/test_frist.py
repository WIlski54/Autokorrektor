"""Mit `einst["frist"]` beginnt ein Verfahren nach der Zeitgrenze keinen zweiten Versuch."""
import time

import pytest
from PIL import Image

from korrektor.koordinaten import anteil_zu_pixel
from korrektor.verfahren import allein, gemini, gemini_vision, vision_kombi

EINST = {"modelle": {"gemini": "m", "gpt": "m", "claude": "m", "vision_analyse": "m"},
         "max_kante": 2400, "vision": {"analyse_anbieter": "gemini", "sicherheit_schwelle": 0.6}}


def _foto(tmp_path):
    pfad = tmp_path / "C_1_gerade.jpg"
    Image.new("RGB", (1000, 2000), "white").save(pfad)
    return pfad


def _vorbei():
    return time.monotonic() - 1


def _spaeter():
    return time.monotonic() + 60


class Scheitert:
    """Ein Aufruf, der immer scheitert und seine Aufrufe zählt."""

    def __init__(self):
        self.zahl = 0

    def __call__(self, *args, **kwargs):
        self.zahl += 1
        raise RuntimeError("Netz weg")


def test_frist_erreicht():
    assert allein.frist_erreicht(None) is False
    assert allein.frist_erreicht(_vorbei()) is True
    assert allein.frist_erreicht(_spaeter()) is False


@pytest.mark.parametrize("frist, versuche", [(_vorbei, 1), (_spaeter, 2), (lambda: None, 2)])
def test_allein_beginnt_nach_der_frist_keinen_zweiten_versuch(tmp_path, frist, versuche):
    fragen = Scheitert()
    erg = allein.ausfuehren(_foto(tmp_path), "gpt", "m", "h", anteil_zu_pixel, fragen, 2400,
                            frist=frist())
    assert fragen.zahl == versuche
    assert "Netz weg" in erg["fehlermeldung"] and erg["funde"] == []


def test_erster_versuch_findet_auch_nach_der_frist_statt(tmp_path):
    fragen = Scheitert()
    allein.ausfuehren(_foto(tmp_path), "gpt", "m", "h", anteil_zu_pixel, fragen, 2400,
                      frist=_vorbei())
    assert fragen.zahl == 1


@pytest.mark.parametrize("name", ["gemini", "gpt", "claude"])
@pytest.mark.parametrize("frist, versuche", [(_vorbei, 1), (_spaeter, 2), (None, 2)])
def test_verfahren_reichen_die_frist_aus_den_einstellungen_durch(tmp_path, monkeypatch, name,
                                                                frist, versuche):
    import importlib
    modul = importlib.import_module(f"korrektor.verfahren.{name}")
    fragen = Scheitert()
    monkeypatch.setattr(modul, "fragen", fragen)
    einst = dict(EINST) if frist is None else {**EINST, "frist": frist()}
    erg = modul.ausfuehren(_foto(tmp_path), einst)
    assert fragen.zahl == versuche and "Netz weg" in erg["fehlermeldung"]


@pytest.mark.parametrize("frist, versuche", [(_vorbei, 1), (_spaeter, 2), (None, 2)])
def test_gemini_vision_beachtet_die_frist(tmp_path, monkeypatch, frist, versuche):
    fragen = Scheitert()
    monkeypatch.setattr(gemini, "fragen", fragen)
    monkeypatch.setattr(gemini_vision, "vision_lesen", lambda daten: None)
    einst = dict(EINST) if frist is None else {**EINST, "frist": frist()}
    erg = gemini_vision.ausfuehren(_foto(tmp_path), einst)
    assert fragen.zahl == versuche and "Netz weg" in erg["fehlermeldung"]


@pytest.mark.parametrize("frist, versuche", [(_vorbei, 1), (_spaeter, 2), (None, 2)])
def test_vision_kombi_beachtet_die_frist(tmp_path, monkeypatch, frist, versuche):
    lesen = Scheitert()
    monkeypatch.setattr(vision_kombi, "vision_lesen", lesen)
    einst = dict(EINST) if frist is None else {**EINST, "frist": frist()}
    erg = vision_kombi.ausfuehren(_foto(tmp_path), einst)
    assert lesen.zahl == versuche and "Netz weg" in erg["fehlermeldung"]
