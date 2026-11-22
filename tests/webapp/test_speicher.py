import sqlite3

import pytest

from webapp.speicher import Speicher


@pytest.fixture
def speicher(tmp_path):
    return Speicher(tmp_path / "daten")


def _aufgabe(speicher, **felder):
    werte = {"titel": "Versuchsbeschreibung", "fach": "Deutsch", "jahrgang": 9,
             "kategorien": ["R", "Z", "Gr"], "verfahren": "gemini", **felder}
    return speicher.aufgabe_anlegen(**werte)


# --- Schema und Aufgaben ---------------------------------------------------------------

def test_speicher_legt_datenbank_und_bilderordner_an(tmp_path):
    Speicher(tmp_path / "daten")
    assert (tmp_path / "daten" / "korrektor.db").is_file()
    assert (tmp_path / "daten" / "bilder").is_dir()
    Speicher(tmp_path / "daten")  # zweites Öffnen legt nichts doppelt an


def test_schema_hat_alle_tabellen_und_wal(tmp_path):
    Speicher(tmp_path / "daten")
    db = sqlite3.connect(tmp_path / "daten" / "korrektor.db")
    try:
        tabellen = {z[0] for z in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"aufgabe", "ablage", "arbeit", "seite", "zeichen", "einstellung"} <= tabellen
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        db.close()


def test_aufgabe_anlegen_und_lesen(speicher):
    nr = _aufgabe(speicher, kategorien=["R", "Gr"])
    aufgabe = speicher.aufgabe(nr)
    assert aufgabe["id"] == nr
    assert aufgabe["titel"] == "Versuchsbeschreibung"
    assert aufgabe["fach"] == "Deutsch" and aufgabe["jahrgang"] == 9
    assert aufgabe["kategorien"] == ["R", "Gr"]
    assert aufgabe["verfahren"] == "gemini"
    assert aufgabe["vorschlag_in_ausgabe"] is False
    assert aufgabe["erstellt_am"]


def test_unbekannte_aufgabe_ist_none(speicher):
    assert speicher.aufgabe(999) is None


def test_aufgabe_aendern(speicher):
    nr = _aufgabe(speicher)
    speicher.aufgabe_aendern(nr, titel="Erörterung", kategorien=["Z"],
                             vorschlag_in_ausgabe=True, verfahren="claude")
    aufgabe = speicher.aufgabe(nr)
    assert aufgabe["titel"] == "Erörterung"
    assert aufgabe["kategorien"] == ["Z"]
    assert aufgabe["vorschlag_in_ausgabe"] is True
    assert aufgabe["verfahren"] == "claude"
    assert aufgabe["fach"] == "Deutsch"


def test_aufgabe_aendern_lehnt_unbekannte_felder_ab(speicher):
    nr = _aufgabe(speicher)
    with pytest.raises(ValueError):
        speicher.aufgabe_aendern(nr, erstellt_am="gestern")
    with pytest.raises(ValueError):
        speicher.aufgabe_aendern(nr, **{"titel = 'x' --": 1})


def test_aufgaben_liefert_zaehlwerte_null_fuer_leere_aufgabe(speicher):
    assert speicher.aufgaben() == []
    nr = _aufgabe(speicher)
    (aufgabe,) = speicher.aufgaben()
    assert aufgabe["id"] == nr and aufgabe["kategorien"] == ["R", "Z", "Gr"]
    for zaehler in ("arbeiten", "seiten", "seiten_fertig", "seiten_fehlgeschlagen",
                    "offen", "bestaetigt"):
        assert aufgabe[zaehler] == 0, zaehler


def test_aufgaben_neueste_zuerst(speicher):
    erste, zweite = _aufgabe(speicher, titel="A"), _aufgabe(speicher, titel="B")
    assert [a["id"] for a in speicher.aufgaben()] == [zweite, erste]
