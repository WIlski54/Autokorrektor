import pytest

from webapp import regeln
from webapp.regeln import RegelFehler

ERLAUBTE = {"R", "Z", "Gr", "A", "Sb"}
BILD = (600, 400)


def _z(herkunft="ki", status="offen", bestaetigt_wie=None, **felder):
    return {"id": 1, "kategorie": "R", "typ": "wort", "x": 10, "y": 20, "breite": 30, "hoehe": 8,
            "gelesen": "Fahrad", "vorschlag": "Fahrrad", "herkunft": herkunft, "status": status,
            "bestaetigt_wie": bestaetigt_wie, **felder}


def _hand(**felder):
    return _z("hand", "bestaetigt", gelesen="", **felder)


def _meldung(fehler):
    """Die Meldung ist ein ganzer deutscher Satz für die Lehrkraft."""
    text = str(fehler.value)
    assert len(text) > 15 and text.endswith(".")
    return text


# --- Bestätigen, Verwerfen, Zurückholen ----------------------------------------------------

def test_einzeln_bestaetigen_eines_offenen_vorschlags():
    assert regeln.einzeln_bestaetigen(_z()) == {"status": "bestaetigt",
                                                "bestaetigt_wie": "einzeln"}


@pytest.mark.parametrize("zeichen, wort", [
    (_z(status="bestaetigt", bestaetigt_wie="gesammelt"), "bereits bestätigt"),
    (_z(status="verworfen"), "zurückholen"),
    (_hand(), "eigene"),
])
def test_einzeln_bestaetigen_unzulaessig(zeichen, wort):
    with pytest.raises(RegelFehler) as fehler:
        regeln.einzeln_bestaetigen(zeichen)
    assert wort in _meldung(fehler).lower()


@pytest.mark.parametrize("zeichen", [
    _z(), _z(status="bestaetigt", bestaetigt_wie="einzeln"),
    _z(status="bestaetigt", bestaetigt_wie="geaendert")])
def test_verwerfen_eines_offenen_oder_bestaetigten_vorschlags(zeichen):
    assert regeln.verwerfen(zeichen) == {"status": "verworfen", "bestaetigt_wie": None}


@pytest.mark.parametrize("zeichen, wort", [
    (_z(status="verworfen"), "bereits verworfen"),
    (_hand(), "gelöscht"),
])
def test_verwerfen_unzulaessig(zeichen, wort):
    with pytest.raises(RegelFehler) as fehler:
        regeln.verwerfen(zeichen)
    assert wort in _meldung(fehler)


@pytest.mark.parametrize("zeichen", [
    _z(status="verworfen"), _z(status="bestaetigt", bestaetigt_wie="einzeln"),
    _z(status="bestaetigt", bestaetigt_wie="gesammelt")])
def test_zurueckholen_macht_wieder_offen(zeichen):
    assert regeln.zurueckholen(zeichen) == {"status": "offen", "bestaetigt_wie": None}


@pytest.mark.parametrize("zeichen, wort", [(_z(), "offen"), (_hand(), "igene")])
def test_zurueckholen_unzulaessig(zeichen, wort):
    with pytest.raises(RegelFehler) as fehler:
        regeln.zurueckholen(zeichen)
    assert wort in _meldung(fehler)


def test_regelfehler_ist_ein_valueerror():
    assert issubclass(RegelFehler, ValueError)


# --- Ändern --------------------------------------------------------------------------------

def test_aendern_eines_ki_zeichens_bestaetigt_es_als_geaendert():
    assert regeln.aendern(_z(), kategorie="Gr", erlaubte=ERLAUBTE) == {
        "kategorie": "Gr", "status": "bestaetigt", "bestaetigt_wie": "geaendert"}
    assert regeln.aendern(_z(), vorschlag="Fahrräder", erlaubte=ERLAUBTE) == {
        "vorschlag": "Fahrräder", "status": "bestaetigt", "bestaetigt_wie": "geaendert"}
    einzeln = _z(status="bestaetigt", bestaetigt_wie="einzeln")
    assert regeln.aendern(einzeln, kategorie="A", vorschlag="", erlaubte=ERLAUBTE) == {
        "kategorie": "A", "vorschlag": "", "status": "bestaetigt", "bestaetigt_wie": "geaendert"}


def test_aendern_eines_eigenen_zeichens_liefert_nur_die_geaenderten_felder():
    assert regeln.aendern(_hand(), kategorie="Sb", vorschlag="Fahrrad",
                          erlaubte=ERLAUBTE) == {"kategorie": "Sb"}
    assert regeln.aendern(_hand(), vorschlag="anders", erlaubte=ERLAUBTE) == {
        "vorschlag": "anders"}


@pytest.mark.parametrize("zeichen", [
    _z(), _z(status="bestaetigt", bestaetigt_wie="einzeln"), _hand()])
def test_aendern_ohne_tatsaechliche_aenderung_liefert_nichts(zeichen):
    assert regeln.aendern(zeichen, erlaubte=ERLAUBTE) == {}
    assert regeln.aendern(zeichen, kategorie="R", vorschlag="Fahrrad", erlaubte=ERLAUBTE) == {}
    assert regeln.aendern(zeichen, kategorie="R", erlaubte=ERLAUBTE) == {}


def test_aendern_mit_unbekanntem_kuerzel_ist_unzulaessig():
    for zeichen in (_z(), _hand()):
        with pytest.raises(RegelFehler) as fehler:
            regeln.aendern(zeichen, kategorie="Xy", erlaubte=ERLAUBTE)
        assert "Xy" in _meldung(fehler)


def test_aendern_laesst_ein_spaeter_entferntes_kuerzel_stehen():
    alt = _hand(kategorie="T")  # T ist kein erlaubtes Kürzel mehr
    assert regeln.aendern(alt, kategorie="T", vorschlag="neu", erlaubte=ERLAUBTE) == {
        "vorschlag": "neu"}


def test_aendern_eines_verworfenen_vorschlags_ist_unzulaessig():
    with pytest.raises(RegelFehler) as fehler:
        regeln.aendern(_z(status="verworfen"), kategorie="Gr", erlaubte=ERLAUBTE)
    assert "zurückholen" in _meldung(fehler)


# --- Verschieben -----------------------------------------------------------------------------

@pytest.mark.parametrize("zeichen", [
    _z(), _z(status="bestaetigt", bestaetigt_wie="einzeln"), _hand()])
def test_verschieben_liefert_nur_den_rahmen(zeichen):
    assert regeln.verschieben(zeichen, 100, 50, 40, 12, BILD) == {
        "x": 100, "y": 50, "breite": 40, "hoehe": 12}


@pytest.mark.parametrize("eingabe, erwartet", [
    ((-20, -5, 40, 12), (0, 0, 40, 12)),            # links oben hinaus
    ((590, 395, 40, 12), (560, 388, 40, 12)),       # rechts unten hinaus
    ((100, 50, 1, 0), (100, 50, 4, 4)),             # zu klein
    ((100, 50, -30, -3), (100, 50, 4, 4)),          # negative Größe
    ((599, 399, 2, 2), (596, 396, 4, 4)),           # zu klein und am Rand
    ((-50, -50, 5000, 5000), (0, 0, 600, 400)),     # größer als das Bild
])
def test_verschieben_klemmt_ins_bild_und_erzwingt_die_mindestgroesse(eingabe, erwartet):
    felder = regeln.verschieben(_z(), *eingabe, BILD)
    assert (felder["x"], felder["y"], felder["breite"], felder["hoehe"]) == erwartet


def test_verschieben_ohne_tatsaechliche_aenderung_liefert_nichts():
    assert regeln.verschieben(_z(), 10, 20, 30, 8, BILD) == {}


def test_verschieben_eines_verworfenen_vorschlags_ist_unzulaessig():
    with pytest.raises(RegelFehler) as fehler:
        regeln.verschieben(_z(status="verworfen"), 100, 50, 40, 12, BILD)
    assert "zurückholen" in _meldung(fehler)


# --- Eigene Zeichen ----------------------------------------------------------------------------

def test_neues_handzeichen_ist_vollstaendig_und_bestaetigt():
    zeichen = regeln.neues_handzeichen("A", "wort", 100, 50, 40, 12, "treffender", ERLAUBTE, BILD)
    assert zeichen == {"kategorie": "A", "typ": "wort", "x": 100, "y": 50, "breite": 40,
                       "hoehe": 12, "gelesen": "", "vorschlag": "treffender",
                       "herkunft": "hand", "status": "bestaetigt", "bestaetigt_wie": None}


def test_neues_handzeichen_klemmt_den_rahmen_und_duldet_fehlenden_vorschlag():
    zeichen = regeln.neues_handzeichen("Z", "luecke", 598, -3, 2, 30, None, ERLAUBTE, BILD)
    assert (zeichen["x"], zeichen["y"], zeichen["breite"], zeichen["hoehe"]) == (596, 0, 4, 30)
    assert zeichen["typ"] == "luecke" and zeichen["vorschlag"] == ""


@pytest.mark.parametrize("kategorie, typ, wort", [
    ("Xy", "wort", "Xy"), ("", "wort", "Kürzel"), ("r", "wort", "Kürzel"),
    ("R", "satz", "Art"), ("R", "", "Art")])
def test_neues_handzeichen_lehnt_unbekanntes_kuerzel_und_unbekannten_typ_ab(kategorie, typ, wort):
    with pytest.raises(RegelFehler) as fehler:
        regeln.neues_handzeichen(kategorie, typ, 1, 1, 10, 10, "", ERLAUBTE, BILD)
    assert wort in _meldung(fehler)


def test_loeschbar_nur_eigene_zeichen():
    assert regeln.loeschbar(_hand()) is True
    for zeichen in (_z(), _z(status="bestaetigt", bestaetigt_wie="einzeln"),
                    _z(status="verworfen")):
        with pytest.raises(RegelFehler) as fehler:
            regeln.loeschbar(zeichen)
        assert "KI-Vorschläge werden verworfen, nicht gelöscht" in _meldung(fehler)


# --- Rest bestätigen, Gesamtbestätigung, Zahlen --------------------------------------------------

def _gemischt():
    return [
        _z(id=1), _z(id=2),
        _z(id=3, status="bestaetigt", bestaetigt_wie="einzeln"),
        _z(id=4, status="bestaetigt", bestaetigt_wie="gesammelt"),
        _z(id=5, status="bestaetigt", bestaetigt_wie="gesammelt"),
        _z(id=6, status="bestaetigt", bestaetigt_wie="geaendert"),
        _z(id=7, status="verworfen"), _z(id=8, status="verworfen"), _z(id=9, status="verworfen"),
        _hand(id=10), _hand(id=11), _hand(id=12), _hand(id=13),
    ]


def test_offene_nennt_die_ids_der_offenen_zeichen():
    assert regeln.offene(_gemischt()) == [1, 2]
    assert regeln.offene([]) == []
    assert regeln.REST_BESTAETIGEN == {"status": "bestaetigt", "bestaetigt_wie": "gesammelt"}


def test_zahlen_zaehlt_nach_bestaetigt_wie_status_und_herkunft():
    assert regeln.zahlen(_gemischt()) == {
        "einzeln": 1, "gesammelt": 2, "geaendert": 1, "verworfen": 3, "hand": 4}
    assert regeln.zahlen([]) == {
        "einzeln": 0, "gesammelt": 0, "geaendert": 0, "verworfen": 0, "hand": 0}


def _seite(status="fertig", *zeichen):
    return {"analyse_status": status, "zeichen": list(zeichen)}


def test_bestaetigbar_wenn_alles_fertig_und_nichts_offen():
    seiten = [_seite("fertig", _z(status="bestaetigt", bestaetigt_wie="einzeln"), _hand()),
              _seite("fertig", _z(status="verworfen")), _seite("fertig")]
    assert regeln.bestaetigbar(seiten) == (True, "")


def test_bestaetigbar_verneint_bei_offenen_zeichen_mit_zahl():
    moeglich, grund = regeln.bestaetigbar([_seite("fertig", _z()), _seite("fertig", _z(), _hand())])
    assert moeglich is False and "2" in grund and "offen" in grund
    moeglich, grund = regeln.bestaetigbar([_seite("fertig", _z())])
    assert moeglich is False and "1" in grund and "offen" in grund


@pytest.mark.parametrize("status, wort", [
    ("neu", "analysiert"), ("wartet", "läuft"), ("laeuft", "läuft"),
    ("fehlgeschlagen", "fehlgeschlagen")])
def test_bestaetigbar_verneint_bei_nicht_fertiger_seite(status, wort):
    moeglich, grund = regeln.bestaetigbar([_seite("fertig"), _seite(status)])
    assert moeglich is False and wort in grund and "Seite 2" in grund


def test_bestaetigbar_verneint_bei_arbeit_ohne_seiten():
    moeglich, grund = regeln.bestaetigbar([])
    assert moeglich is False and "keine Seiten" in grund


def test_bestaetigbar_rechnet_auch_mit_der_zahl_offener_zeichen():
    """Für Übersichten genügt je Seite die Zahl `offen` statt der Zeichenliste."""
    assert regeln.bestaetigbar([{"analyse_status": "fertig", "offen": 0}]) == (True, "")
    moeglich, grund = regeln.bestaetigbar([{"analyse_status": "fertig", "offen": 3}])
    assert moeglich is False and "3" in grund


# --- Kürzel ----------------------------------------------------------------------------------------

def test_erlaubte_kuerzel_sind_die_festen_und_die_eigenen():
    eigene = [{"kuerzel": "A", "bezeichnung": "Ausdruck"}]
    assert regeln.erlaubte_kuerzel(eigene) == {"R", "Z", "Gr", "A"}
    assert regeln.FESTE_KUERZEL == ("R", "Z", "Gr")


def test_kuerzelliste_pruefen_bereinigt_die_eintraege():
    liste = [{"kuerzel": " A ", "bezeichnung": "  Ausdruck "}, {"kuerzel": "Sb",
                                                                "bezeichnung": "Satzbau"}]
    assert regeln.kuerzelliste_pruefen(liste) == [
        {"kuerzel": "A", "bezeichnung": "Ausdruck"}, {"kuerzel": "Sb", "bezeichnung": "Satzbau"}]
    assert regeln.kuerzelliste_pruefen([]) == []


@pytest.mark.parametrize("liste, wort", [
    ([{"kuerzel": "R", "bezeichnung": "Rechtschreibung"}], "R"),
    ([{"kuerzel": "z", "bezeichnung": "Zeichen"}], "Z"),
    ([{"kuerzel": "GR", "bezeichnung": "Grammatik"}], "Gr"),
    ([{"kuerzel": "", "bezeichnung": "Ausdruck"}], "Kürzel"),
    ([{"kuerzel": "Ausdr", "bezeichnung": "Ausdruck"}], "4"),
    ([{"kuerzel": "A1", "bezeichnung": "Ausdruck"}], "Buchstaben"),
    ([{"kuerzel": "A b", "bezeichnung": "Ausdruck"}], "Buchstaben"),
    ([{"kuerzel": "A", "bezeichnung": "  "}], "Bezeichnung"),
    ([{"kuerzel": "A", "bezeichnung": "x" * 41}], "40"),
    ([{"kuerzel": "A", "bezeichnung": "Ausdruck"}, {"kuerzel": "a", "bezeichnung": "anders"}],
     "doppelt"),
    ([{"kuerzel": "A"}], "Bezeichnung"),
    ([{"kuerzel": 1, "bezeichnung": "Ausdruck"}], "Kürzel"),
    (["A"], "Kürzel"),
])
def test_kuerzelliste_pruefen_lehnt_unzulaessiges_ab(liste, wort):
    with pytest.raises(RegelFehler) as fehler:
        regeln.kuerzelliste_pruefen(liste)
    assert wort in _meldung(fehler)


def test_arbeitskuerzel_pruefen():
    assert regeln.arbeitskuerzel_pruefen("  7b-03 ") == "7b-03"
    assert regeln.arbeitskuerzel_pruefen("x" * 20) == "x" * 20
    for wert in ("", "   ", "x" * 21, None, 7):
        with pytest.raises(RegelFehler) as fehler:
            regeln.arbeitskuerzel_pruefen(wert)
        assert "20" in _meldung(fehler)
