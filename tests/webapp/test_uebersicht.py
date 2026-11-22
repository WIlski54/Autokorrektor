"""Etappe 3: Zahlen der Stapelübersicht und ihr CSV-Export."""
import io

import pytest
from PIL import Image

from webapp import uebersicht
from webapp.speicher import Speicher


@pytest.fixture
def speicher(tmp_path):
    return Speicher(tmp_path / "daten")


def _jpeg():
    puffer = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(puffer, format="JPEG")
    return puffer.getvalue()


def _aufgabe(speicher, **felder):
    werte = {"titel": "Versuchsbeschreibung", "fach": "Deutsch", "jahrgang": 9,
             "kategorien": ["R", "Z", "Gr"], "verfahren": "gemini", **felder}
    return speicher.aufgabe_anlegen(**werte)


def _z(kategorie="R", gelesen="Fahrad", vorschlag="Fahrrad", typ="wort", status="bestaetigt",
       **felder):
    return {"kategorie": kategorie, "typ": typ, "x": 5, "y": 5, "breite": 20, "hoehe": 8,
            "gelesen": gelesen, "vorschlag": vorschlag, "herkunft": "ki", "status": status,
            "bestaetigt_wie": "einzeln" if status == "bestaetigt" else None, **felder}


def _arbeit(speicher, aufgabe_id, *zeichen, seitenzahl=1, bestaetigen=True, kuerzel=None):
    """Eine fertig analysierte Arbeit; die Zeichen stehen reihum auf ihren Seiten."""
    seiten = speicher.arbeit_anlegen(aufgabe_id, [(f"{i}.jpg", _jpeg())
                                                  for i in range(seitenzahl)])
    for seite_id in seiten:
        lauf = speicher.seite_lauf_beginnen(seite_id)
        assert speicher.zeichen_ersetzen(seite_id, lauf, []) is True
        speicher.seite_status(seite_id, "fertig", transkription="Text")
    for platz, z in enumerate(zeichen):
        speicher.zeichen_anlegen(seiten[platz % seitenzahl], z)
    arbeit_id = speicher.seite(seiten[0])["arbeit_id"]
    if kuerzel is not None:
        speicher.arbeit_kuerzel_setzen(arbeit_id, kuerzel)
    if bestaetigen:
        assert speicher.arbeit_bestaetigen(arbeit_id) is not None
    return arbeit_id


# --- stapel ---------------------------------------------------------------------------------

def test_aufgabe_ohne_arbeiten(speicher):
    nr = _aufgabe(speicher)
    assert uebersicht.stapel(speicher, nr) == {
        "arbeiten_gesamt": 0, "arbeiten_bestaetigt": 0, "kategorien": [], "woerter": [],
        "arbeiten": []}


def test_nur_bestaetigte_arbeiten_und_bestaetigte_zeichen_zaehlen(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z("R"), _z("Z", typ="luecke"), _z("R", status="verworfen"),
            seitenzahl=2)
    _arbeit(speicher, nr, _z("R"), _z("Gr"), _z("Gr"), bestaetigen=False)
    offen = _arbeit(speicher, nr, _z("R"), bestaetigen=False)
    seite_id = speicher.arbeit(offen)["seiten"][0]["id"]
    speicher.zeichen_anlegen(seite_id, _z("Z", status="offen"))
    daten = uebersicht.stapel(speicher, nr)
    assert (daten["arbeiten_gesamt"], daten["arbeiten_bestaetigt"]) == (3, 1)
    assert daten["kategorien"] == [
        {"kuerzel": "R", "bezeichnung": "Rechtschreibung", "anzahl": 1},
        {"kuerzel": "Z", "bezeichnung": "Zeichensetzung", "anzahl": 1}]
    assert daten["arbeiten"] == [
        {"kuerzel": "01", "seiten": 2, "je_kategorie": {"R": 1, "Z": 1}, "summe": 2}]


def test_andere_aufgaben_fliessen_nicht_ein(speicher):
    nr, andere = _aufgabe(speicher), _aufgabe(speicher, titel="Andere")
    _arbeit(speicher, nr, _z("R"))
    _arbeit(speicher, andere, _z("Gr"), _z("Gr"))
    daten = uebersicht.stapel(speicher, nr)
    assert [k["kuerzel"] for k in daten["kategorien"]] == ["R"]
    assert daten["arbeiten_gesamt"] == 1


def test_reihenfolge_der_kategorien(speicher):
    speicher.kuerzel_setzen([{"kuerzel": "W", "bezeichnung": "Wortwahl"},
                             {"kuerzel": "A", "bezeichnung": "Ausdruck"},
                             {"kuerzel": "sb", "bezeichnung": "Satzbau"}])
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z("W"), _z("sb"), _z("Gr"), _z("A"), _z("Z"), _z("R"), _z("A"))
    daten = uebersicht.stapel(speicher, nr)
    # R, Z, Gr zuerst, dann die eigenen alphabetisch; nur was vorkommt.
    assert daten["kategorien"] == [
        {"kuerzel": "R", "bezeichnung": "Rechtschreibung", "anzahl": 1},
        {"kuerzel": "Z", "bezeichnung": "Zeichensetzung", "anzahl": 1},
        {"kuerzel": "Gr", "bezeichnung": "Grammatik", "anzahl": 1},
        {"kuerzel": "A", "bezeichnung": "Ausdruck", "anzahl": 2},
        {"kuerzel": "sb", "bezeichnung": "Satzbau", "anzahl": 1},
        {"kuerzel": "W", "bezeichnung": "Wortwahl", "anzahl": 1}]
    assert list(daten["arbeiten"][0]["je_kategorie"]) == ["R", "Z", "Gr", "A", "sb", "W"]
    assert daten["arbeiten"][0]["summe"] == 7


def test_entferntes_kuerzel_zaehlt_weiter_ohne_bezeichnung(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z("T"))
    speicher.kuerzel_setzen([{"kuerzel": "A", "bezeichnung": "Ausdruck"}])
    assert uebersicht.stapel(speicher, nr)["kategorien"] == [
        {"kuerzel": "T", "bezeichnung": "", "anzahl": 1}]


def test_kategorien_ordnen_als_reine_funktion():
    eigene = [{"kuerzel": "W", "bezeichnung": "Wortwahl"}]
    assert uebersicht.kategorien_ordnen({"W": 2, "Gr": 1, "Z": 0, "R": 3}, eigene) == [
        {"kuerzel": "R", "bezeichnung": "Rechtschreibung", "anzahl": 3},
        {"kuerzel": "Gr", "bezeichnung": "Grammatik", "anzahl": 1},
        {"kuerzel": "W", "bezeichnung": "Wortwahl", "anzahl": 2}]
    assert uebersicht.kategorien_ordnen({}, eigene) == []


# --- Häufige Fehlerwörter -------------------------------------------------------------------

def test_woerter_fassen_gross_und_kleinschreibung_zusammen(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z(gelesen="Fahrad"), _z(gelesen="fahrad"), _z(gelesen="  Fahrad "))
    _arbeit(speicher, nr, _z(gelesen="FAHRAD", vorschlag="Fahrrad"),
            _z(gelesen="fahrad", vorschlag="fahrrad"))
    daten = uebersicht.stapel(speicher, nr)
    # Angezeigt wird die häufigste Schreibung, bei Gleichstand die im Stapel zuerst gesehene.
    assert daten["woerter"] == [
        {"gelesen": "Fahrad", "vorschlag": "Fahrrad", "anzahl": 5, "arbeiten": 2}]


def test_woerter_nur_rechtschreibung_und_nur_typ_wort(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr,
            _z("Gr", gelesen="den", vorschlag="dem"), _z("Gr", gelesen="den", vorschlag="dem"),
            _z("Z", gelesen="dass er", vorschlag="dass, er", typ="luecke"),
            _z("Z", gelesen="dass er", vorschlag="dass, er", typ="luecke"),
            _z("R", gelesen="weil er", vorschlag="weil, er", typ="luecke"),
            _z("R", gelesen="weil er", vorschlag="weil, er", typ="luecke"),
            _z("R", gelesen="", vorschlag="", herkunft="hand"),
            _z("R", gelesen="", vorschlag="", herkunft="hand"),
            _z("R", gelesen="villeicht", vorschlag="vielleicht"),
            _z("R", gelesen="villeicht", vorschlag="vielleicht"))
    assert uebersicht.stapel(speicher, nr)["woerter"] == [
        {"gelesen": "villeicht", "vorschlag": "vielleicht", "anzahl": 2, "arbeiten": 1}]


def test_woerter_schwelle_zweimal_oder_in_zwei_arbeiten(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z(gelesen="einmal", vorschlag="ein Mal"),
            _z(gelesen="zweimal"), _z(gelesen="zweimal"), _z(gelesen="verteilt"))
    _arbeit(speicher, nr, _z(gelesen="Verteilt"))
    _arbeit(speicher, nr, _z(gelesen="einmal"), bestaetigen=False)   # zählt nicht
    _arbeit(speicher, nr, _z(gelesen="einmal", status="verworfen"))  # zählt nicht
    woerter = uebersicht.stapel(speicher, nr)["woerter"]
    assert [(w["gelesen"], w["anzahl"], w["arbeiten"]) for w in woerter] == [
        ("verteilt", 2, 2), ("zweimal", 2, 1)]


def test_woerter_sortiert_nach_anzahl_dann_alphabetisch(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, *[_z(gelesen=w) for w in
                            ["zebra", "zebra", "Apfel", "apfel", "Öl", "Öl", "mitte", "mitte",
                             "mitte", "birne", "birne"]])
    woerter = uebersicht.stapel(speicher, nr)["woerter"]
    assert [(w["gelesen"], w["anzahl"]) for w in woerter] == [
        ("mitte", 3), ("Apfel", 2), ("birne", 2), ("Öl", 2), ("zebra", 2)]


def test_woerter_nennen_den_haeufigsten_vorschlag(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z(gelesen="das", vorschlag="dass"), _z(gelesen="das", vorschlag="Das"),
            _z(gelesen="das", vorschlag="dass"), _z(gelesen="das", vorschlag=""))
    assert uebersicht.stapel(speicher, nr)["woerter"] == [
        {"gelesen": "das", "vorschlag": "dass", "anzahl": 4, "arbeiten": 1}]


def test_hoechstens_zwanzig_woerter(speicher):
    nr = _aufgabe(speicher)
    zeichen = [_z(gelesen=f"wort{i:02d}") for i in range(25) for _ in range(2)]
    _arbeit(speicher, nr, *zeichen, _z(gelesen="wort24"))
    woerter = uebersicht.stapel(speicher, nr)["woerter"]
    assert len(woerter) == 20
    assert woerter[0]["gelesen"] == "wort24" and woerter[1]["gelesen"] == "wort00"
    assert woerter[-1]["gelesen"] == "wort18"


# --- Tabelle je Arbeit ----------------------------------------------------------------------

def test_arbeiten_stehen_in_stapelreihenfolge_nicht_nach_fehlerzahl(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z("R"), _z("R"), _z("Z"), kuerzel="Zeta")
    _arbeit(speicher, nr, kuerzel="Alpha", seitenzahl=3)
    _arbeit(speicher, nr, _z("R"), bestaetigen=False, kuerzel="Offen")
    _arbeit(speicher, nr, *[_z("Gr") for _ in range(9)], kuerzel="Mitte")
    daten = uebersicht.stapel(speicher, nr)
    assert daten["arbeiten"] == [
        {"kuerzel": "Zeta", "seiten": 1, "je_kategorie": {"R": 2, "Z": 1, "Gr": 0}, "summe": 3},
        {"kuerzel": "Alpha", "seiten": 3, "je_kategorie": {"R": 0, "Z": 0, "Gr": 0}, "summe": 0},
        {"kuerzel": "Mitte", "seiten": 1, "je_kategorie": {"R": 0, "Z": 0, "Gr": 9}, "summe": 9}]
    assert (daten["arbeiten_gesamt"], daten["arbeiten_bestaetigt"]) == (4, 3)


def test_keine_bewertung_in_den_daten(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z("R"))
    daten = uebersicht.stapel(speicher, nr)
    assert set(daten) == {"arbeiten_gesamt", "arbeiten_bestaetigt", "kategorien", "woerter",
                          "arbeiten"}
    assert set(daten["arbeiten"][0]) == {"kuerzel", "seiten", "je_kategorie", "summe"}


# --- CSV ------------------------------------------------------------------------------------

def _daten(arbeiten, kuerzel=("R", "Z")):
    return {"arbeiten_gesamt": len(arbeiten), "arbeiten_bestaetigt": len(arbeiten),
            "kategorien": [{"kuerzel": k, "bezeichnung": "", "anzahl": 1} for k in kuerzel],
            "woerter": [], "arbeiten": arbeiten}


def test_csv_hat_kopfzeile_semikolon_und_crlf():
    daten = _daten([
        {"kuerzel": "01", "seiten": 2, "je_kategorie": {"R": 3, "Z": 0}, "summe": 3},
        {"kuerzel": "02", "seiten": 1, "je_kategorie": {"R": 0, "Z": 1}, "summe": 1}])
    assert uebersicht.als_csv(daten) == ("Arbeit;Seiten;R;Z;Summe\r\n"
                                         "01;2;3;0;3\r\n"
                                         "02;1;0;1;1\r\n")


def test_csv_aus_dem_speicher_in_stapelreihenfolge(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z("R"), _z("A"), kuerzel="Zeta", seitenzahl=2)
    _arbeit(speicher, nr, _z("Gr"), bestaetigen=False)
    _arbeit(speicher, nr, kuerzel="Äpfel")
    assert uebersicht.als_csv(uebersicht.stapel(speicher, nr)) == (
        "Arbeit;Seiten;R;A;Summe\r\nZeta;2;1;1;2\r\nÄpfel;1;0;0;0\r\n")


def test_csv_ohne_bestaetigte_arbeit_hat_nur_die_kopfzeile():
    assert uebersicht.als_csv(_daten([], kuerzel=())) == "Arbeit;Seiten;Summe\r\n"


def test_csv_fehlende_kategorie_einer_arbeit_ist_null():
    daten = _daten([{"kuerzel": "01", "seiten": 1, "je_kategorie": {"R": 2}, "summe": 2}])
    assert uebersicht.als_csv(daten).splitlines()[1] == "01;1;2;0;2"


@pytest.mark.parametrize("kuerzel, zelle", [
    ("=1+1", "'=1+1"), ("+49", "'+49"), ("-3", "'-3"), ("@SUM(A1)", "'@SUM(A1)"),
    ("\t=1", "'\t=1"), ("a=b", "a=b"), ("7b", "7b")])
def test_csv_schuetzt_vor_formeln(kuerzel, zelle):
    daten = _daten([{"kuerzel": kuerzel, "seiten": 1, "je_kategorie": {"R": 1, "Z": 0},
                     "summe": 1}])
    assert uebersicht.als_csv(daten).split("\r\n")[1] == f"{zelle};1;1;0;1"


def test_csv_schuetzt_auch_die_kopfzeile_und_setzt_anfuehrungszeichen():
    daten = _daten([{"kuerzel": 'a;b "c"', "seiten": 1, "je_kategorie": {"=X": 1}, "summe": 1}],
                   kuerzel=("=X",))
    assert uebersicht.als_csv(daten) == ('Arbeit;Seiten;\'=X;Summe\r\n'
                                         '"a;b ""c""";1;1;1\r\n')
