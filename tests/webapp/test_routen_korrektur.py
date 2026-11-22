"""Etappe 2: JSON-Routen der Korrekturansicht, Gesamtbestätigung, Neuanalyse, Kürzel."""
import pytest

# Die Testhilfen und Vorrichtungen der Etappe 1 gelten unverändert.
from tests.webapp.test_routen import (  # noqa: F401
    _aufgabe, _bild, _daten, _mit_zeichen, _text, _zeichen, app, client, schein, schlange,
    speicher)

FEST = {"status": "bestaetigt", "bestaetigt_wie": "einzeln"}
HAND = {"herkunft": "hand", "status": "bestaetigt", "gelesen": "", "vorschlag": "",
        "rahmen_ki": None}
ARBEIT_FELDER = {"offen", "bestaetigt_am", "bestaetigbar", "grund"}
ZEICHEN_FELDER = {"id", "seite_id", "kategorie", "typ", "x", "y", "breite", "hoehe", "gelesen",
                  "vorschlag", "herkunft", "status", "bestaetigt_wie"}


def _arbeit(speicher, *zeichen, seitenzahl=1):
    """Eine Arbeit mit fertigen Seiten (600 × 400); die Zeichen stehen auf der ersten Seite.

    Gibt (arbeit_id, seiten_ids, zeichen_ids) zurück; die Zeichen in der genannten Reihenfolge.
    """
    nr = _aufgabe(speicher)
    seiten = speicher.arbeit_anlegen(nr, [(f"{i}.jpg", _bild()) for i in range(seitenzahl)])
    ids = []
    for seite_id in seiten:
        _mit_zeichen(speicher, seite_id)
    for z in zeichen:
        ids.append(speicher.zeichen_anlegen(seiten[0], z))
    return speicher.seite(seiten[0])["arbeit_id"], seiten, ids


def _bestaetigt(speicher, *zeichen):
    arbeit_id, seiten, ids = _arbeit(speicher, *zeichen)
    assert speicher.arbeit_bestaetigen(arbeit_id) is not None
    return arbeit_id, seiten, ids


def _ist_bestaetigt(speicher, arbeit_id):
    return speicher.arbeit(arbeit_id)["bestaetigt_am"] is not None


def _ok(antwort):
    """Prüft die gemeinsame Form einer schreibenden Antwort und gibt sie zurück."""
    assert antwort.status_code == 200, antwort.get_data(as_text=True)
    erg = antwort.get_json()
    assert set(erg["arbeit"]) == ARBEIT_FELDER
    assert erg["zeichen"] is None or set(erg["zeichen"]) == ZEICHEN_FELDER
    return erg


def _fehler(antwort, code):
    assert antwort.status_code == code, antwort.get_data(as_text=True)
    meldung = antwort.get_json()["fehler"]
    assert isinstance(meldung, str) and meldung
    return meldung


# --- Bestätigen, Verwerfen, Zurückholen ----------------------------------------------------

def test_bestaetigen_eines_vorschlags(client, speicher):
    arbeit_id, (seite_id,), (z1, z2) = _arbeit(speicher, _zeichen(), _zeichen(x=300))
    erg = _ok(client.post(f"/zeichen/{z1}/bestaetigen"))
    assert erg["zeichen"]["id"] == z1 and erg["zeichen"]["seite_id"] == seite_id
    assert erg["zeichen"]["status"] == "bestaetigt"
    assert erg["zeichen"]["bestaetigt_wie"] == "einzeln"
    assert erg["arbeit"]["offen"] == 1 and erg["arbeit"]["bestaetigt_am"] is None
    assert erg["arbeit"]["bestaetigbar"] is False and "offen" in erg["arbeit"]["grund"]
    assert speicher.zeichen_eintrag(z1)["bestaetigt_wie"] == "einzeln"
    erg = _ok(client.post(f"/zeichen/{z2}/bestaetigen"))
    assert erg["arbeit"] == {"offen": 0, "bestaetigt_am": None, "bestaetigbar": True, "grund": ""}


def test_verwerfen_und_zurueckholen(client, speicher):
    arbeit_id, _, (z1, z2) = _arbeit(speicher, _zeichen(), _zeichen(x=300, **FEST))
    for nr in (z1, z2):
        erg = _ok(client.post(f"/zeichen/{nr}/verwerfen"))
        assert (erg["zeichen"]["status"], erg["zeichen"]["bestaetigt_wie"]) == ("verworfen", None)
    assert erg["arbeit"]["offen"] == 0 and erg["arbeit"]["bestaetigbar"] is True
    erg = _ok(client.post(f"/zeichen/{z1}/zurueckholen"))
    assert (erg["zeichen"]["status"], erg["zeichen"]["bestaetigt_wie"]) == ("offen", None)
    assert erg["arbeit"]["offen"] == 1
    assert speicher.zeichen_eintrag(z1)["status"] == "offen"
    assert speicher.zeichen_eintrag(z2)["status"] == "verworfen"


@pytest.mark.parametrize("aktion, zeichen, wort", [
    ("bestaetigen", _zeichen(**FEST), "bereits bestätigt"),
    ("bestaetigen", _zeichen(status="verworfen"), "zurückholen"),  # erst zurückholen
    ("bestaetigen", _zeichen(**HAND), "igene"),
    ("verwerfen", _zeichen(status="verworfen"), "bereits verworfen"),
    ("verwerfen", _zeichen(**HAND), "gelöscht"),                   # eigenes Zeichen verwerfen
    ("zurueckholen", _zeichen(), "offen"),
    ("zurueckholen", _zeichen(**HAND), "igene"),
    ("loeschen", _zeichen(), "KI-Vorschläge werden verworfen, nicht gelöscht"),
    ("loeschen", _zeichen(**FEST), "KI-Vorschläge werden verworfen, nicht gelöscht"),
])
def test_regelverstoss_ergibt_409_und_aendert_nichts(client, speicher, aktion, zeichen, wort):
    arbeit_id, _, (z1,) = _arbeit(speicher, zeichen)
    vorher = speicher.zeichen_eintrag(z1)
    assert wort in _fehler(client.post(f"/zeichen/{z1}/{aktion}"), 409)
    assert speicher.zeichen_eintrag(z1) == vorher


@pytest.mark.parametrize("pfad, inhalt", [
    ("/zeichen/999/bestaetigen", None), ("/zeichen/999/verwerfen", None),
    ("/zeichen/999/zurueckholen", None), ("/zeichen/999/loeschen", None),
    ("/zeichen/999/aendern", {"kategorie": "Gr"}),
    ("/zeichen/999/rahmen", {"x": 1, "y": 1, "breite": 10, "hoehe": 10}),
    ("/seite/999/zeichen", {"kategorie": "R", "typ": "wort", "x": 1, "y": 1, "breite": 10,
                            "hoehe": 10}),
    ("/arbeit/999/rest-bestaetigen", None), ("/arbeit/999/bestaetigen", None),
    ("/arbeit/999/kuerzel", {"kuerzel": "x"}), ("/seite/999/neu-analysieren", None),
])
def test_unbekanntes_ergibt_404_als_json(client, pfad, inhalt):
    _fehler(client.post(pfad, json=inhalt), 404)


def test_unbekannte_arbeit_zahlen_ergibt_404(client):
    _fehler(client.get("/arbeit/999/zahlen"), 404)


@pytest.mark.parametrize("pfad", [
    "/zeichen/{z}/bestaetigen", "/zeichen/{z}/verwerfen", "/zeichen/{z}/loeschen",
    "/arbeit/{a}/rest-bestaetigen", "/arbeit/{a}/bestaetigen", "/seite/{s}/neu-analysieren"])
def test_neue_routen_weisen_fremde_herkunft_und_fremden_host_ab(client, speicher, schein, pfad):
    arbeit_id, (seite_id,), (z1,) = _arbeit(speicher, _zeichen())
    pfad = pfad.format(z=z1, a=arbeit_id, s=seite_id)
    assert client.post(pfad, headers={"Origin": "http://boese.example"}).status_code == 403
    assert client.post(pfad, headers={"Host": "boese.example"}).status_code == 403
    assert client.get(pfad).status_code == 405
    assert speicher.zeichen_eintrag(z1)["status"] == "offen" and schein.aufrufe == []
    assert speicher.seite(seite_id)["analyse_status"] == "fertig"


# --- Ändern --------------------------------------------------------------------------------

def test_aendern_von_kuerzel_und_vorschlag(client, speicher):
    arbeit_id, _, (z1, z2) = _arbeit(speicher, _zeichen(), _zeichen(x=300, **HAND))
    erg = _ok(client.post(f"/zeichen/{z1}/aendern", json={"kategorie": "A",
                                                           "vorschlag": "  Fahrräder "}))
    assert (erg["zeichen"]["kategorie"], erg["zeichen"]["vorschlag"]) == ("A", "Fahrräder")
    assert (erg["zeichen"]["status"], erg["zeichen"]["bestaetigt_wie"]) == (
        "bestaetigt", "geaendert")
    assert erg["arbeit"]["offen"] == 0
    erg = _ok(client.post(f"/zeichen/{z2}/aendern", json={"vorschlag": "treffender"}))
    assert erg["zeichen"]["vorschlag"] == "treffender"
    assert (erg["zeichen"]["status"], erg["zeichen"]["bestaetigt_wie"]) == ("bestaetigt", None)
    assert speicher.zeichen_eintrag(z1)["kategorie"] == "A"


def test_aendern_ohne_tatsaechliche_aenderung_laesst_alles_wie_es_ist(client, speicher):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    erg = _ok(client.post(f"/zeichen/{z1}/aendern", json={"kategorie": "R",
                                                           "vorschlag": "Fahrrad"}))
    assert erg["zeichen"]["status"] == "offen" and erg["arbeit"]["offen"] == 1
    speicher.zeichen_aendern(z1, **FEST)
    speicher.arbeit_bestaetigen(arbeit_id)
    erg = _ok(client.post(f"/zeichen/{z1}/aendern", json={"vorschlag": "Fahrrad"}))
    assert erg["zeichen"]["bestaetigt_wie"] == "einzeln" and erg["arbeit"]["bestaetigt_am"]
    assert _ist_bestaetigt(speicher, arbeit_id) is True


def test_aendern_mit_unbekanntem_oder_entferntem_kuerzel_ergibt_409(client, speicher):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    assert "Xy" in _fehler(client.post(f"/zeichen/{z1}/aendern", json={"kategorie": "Xy"}), 409)
    speicher.kuerzel_setzen([{"kuerzel": "St", "bezeichnung": "Stil"}])
    _fehler(client.post(f"/zeichen/{z1}/aendern", json={"kategorie": "A"}), 409)
    _ok(client.post(f"/zeichen/{z1}/aendern", json={"kategorie": "St"}))
    assert speicher.zeichen_eintrag(z1)["kategorie"] == "St"


@pytest.mark.parametrize("inhalt", [
    None, [], "x", {}, {"kategorie": 1}, {"kategorie": None}, {"vorschlag": 5},
    {"vorschlag": ["a"]}, {"kategorie": "Gr", "status": "verworfen"}, {"kategory": "Gr"},
    {"vorschlag": "x" * 201}, {"kategorie": ""}])
def test_aendern_mit_ungueltiger_eingabe_ergibt_400(client, speicher, inhalt):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    vorher = speicher.zeichen_eintrag(z1)
    _fehler(client.post(f"/zeichen/{z1}/aendern", json=inhalt), 400)
    assert speicher.zeichen_eintrag(z1) == vorher


def test_ungueltiges_json_ergibt_400(client, speicher):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    for daten in ("{kaputt", '{"x": NaN, "y": 1, "breite": 10, "hoehe": 10}',
                  '{"x": 1e999, "y": 1, "breite": 10, "hoehe": 10}'):
        _fehler(client.post(f"/zeichen/{z1}/rahmen", data=daten,
                            content_type="application/json"), 400)
    _fehler(client.post(f"/zeichen/{z1}/aendern", data="kategorie=Gr"), 400)
    assert speicher.zeichen_eintrag(z1)["x"] == 10


# --- Verschieben -----------------------------------------------------------------------------

def test_rahmen_rundet_auf_ganze_pixel_und_laesst_den_status(client, speicher):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    erg = _ok(client.post(f"/zeichen/{z1}/rahmen",
                          json={"x": 100.4, "y": 50.5, "breite": 39.6, "hoehe": 12}))
    z = erg["zeichen"]
    assert (z["x"], z["y"], z["breite"], z["hoehe"]) == (100, 51, 40, 12)
    assert z["status"] == "offen" and z["bestaetigt_wie"] is None
    eintrag = speicher.zeichen_eintrag(z1)
    assert (eintrag["x"], eintrag["y"], eintrag["breite"], eintrag["hoehe"]) == (100, 51, 40, 12)
    assert eintrag["rahmen_ki"] == [10, 20, 30, 8]


@pytest.mark.parametrize("rahmen, erwartet", [
    ({"x": -20, "y": -5, "breite": 40, "hoehe": 12}, (0, 0, 40, 12)),
    ({"x": 590, "y": 395, "breite": 40, "hoehe": 12}, (560, 388, 40, 12)),  # Bild: 600 × 400
    ({"x": 100, "y": 50, "breite": 1, "hoehe": 0.2}, (100, 50, 4, 4)),
    ({"x": 10**30, "y": -10**30, "breite": 10**30, "hoehe": 5}, (0, 0, 600, 5)),
])
def test_rahmen_klemmt_in_die_bildgroesse_der_seite(client, speicher, rahmen, erwartet):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    z = _ok(client.post(f"/zeichen/{z1}/rahmen", json=rahmen))["zeichen"]
    assert (z["x"], z["y"], z["breite"], z["hoehe"]) == erwartet


@pytest.mark.parametrize("inhalt", [
    None, {}, {"x": 1, "y": 1, "breite": 10}, {"x": "1", "y": 1, "breite": 10, "hoehe": 10},
    {"x": True, "y": 1, "breite": 10, "hoehe": 10}, {"x": None, "y": 1, "breite": 10, "hoehe": 10},
    {"x": 1, "y": 1, "breite": 10, "hoehe": 10, "status": "bestaetigt"}, [1, 1, 10, 10]])
def test_rahmen_mit_ungueltiger_eingabe_ergibt_400(client, speicher, inhalt):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    _fehler(client.post(f"/zeichen/{z1}/rahmen", json=inhalt), 400)
    assert speicher.zeichen_eintrag(z1)["x"] == 10


def test_rahmen_eines_verworfenen_vorschlags_ergibt_409(client, speicher):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen(status="verworfen"))
    _fehler(client.post(f"/zeichen/{z1}/rahmen",
                        json={"x": 1, "y": 1, "breite": 10, "hoehe": 10}), 409)


def test_rahmen_ohne_tatsaechliche_aenderung_laesst_die_bestaetigung(client, speicher):
    arbeit_id, _, (z1,) = _bestaetigt(speicher, _zeichen(**FEST))
    erg = _ok(client.post(f"/zeichen/{z1}/rahmen",
                          json={"x": 10.2, "y": 19.8, "breite": 30, "hoehe": 8}))
    assert erg["arbeit"]["bestaetigt_am"] and _ist_bestaetigt(speicher, arbeit_id) is True


# --- Eigene Zeichen ----------------------------------------------------------------------------

def test_eigenes_zeichen_setzen_und_loeschen(client, speicher):
    arbeit_id, (seite_id,), _ = _arbeit(speicher)
    erg = _ok(client.post(f"/seite/{seite_id}/zeichen", json={
        "kategorie": "Sb", "typ": "luecke", "x": 595.7, "y": 10, "breite": 2, "hoehe": 30.2,
        "vorschlag": " umstellen "}))
    z = erg["zeichen"]
    assert (z["kategorie"], z["typ"], z["vorschlag"], z["gelesen"]) == (
        "Sb", "luecke", "umstellen", "")
    assert (z["x"], z["y"], z["breite"], z["hoehe"]) == (596, 10, 4, 30)
    assert (z["herkunft"], z["status"], z["bestaetigt_wie"]) == ("hand", "bestaetigt", None)
    assert z["seite_id"] == seite_id and speicher.zeichen_eintrag(z["id"])["kategorie"] == "Sb"
    assert erg["arbeit"]["offen"] == 0 and erg["arbeit"]["bestaetigbar"] is True
    ohne = _ok(client.post(f"/seite/{seite_id}/zeichen", json={
        "kategorie": "R", "typ": "wort", "x": 1, "y": 1, "breite": 20, "hoehe": 10}))["zeichen"]
    assert ohne["vorschlag"] == "" and ohne["id"] != z["id"]

    erg = _ok(client.post(f"/zeichen/{z['id']}/loeschen"))
    assert erg["zeichen"] is None and speicher.zeichen_eintrag(z["id"]) is None
    assert speicher.zeichen_eintrag(ohne["id"]) is not None


@pytest.mark.parametrize("felder, wort", [
    ({"kategorie": "Xy"}, "Xy"), ({"typ": "satz"}, "Art"), ({"kategorie": "r"}, "Kürzel")])
def test_eigenes_zeichen_mit_unbekanntem_kuerzel_oder_typ_ergibt_409(client, speicher, felder,
                                                                    wort):
    arbeit_id, (seite_id,), _ = _arbeit(speicher)
    inhalt = {"kategorie": "R", "typ": "wort", "x": 1, "y": 1, "breite": 20, "hoehe": 10, **felder}
    assert wort in _fehler(client.post(f"/seite/{seite_id}/zeichen", json=inhalt), 409)
    assert speicher.arbeit(arbeit_id)["seiten"][0]["zeichen"] == []


@pytest.mark.parametrize("aenderung", [
    {"kategorie": None}, {"typ": None}, {"x": None}, {"hoehe": None}, {"kategorie": 3},
    {"typ": 1}, {"x": "1"}, {"breite": False}, {"vorschlag": 7}, {"vorschlag": "x" * 201},
    {"herkunft": "ki"}, {"gelesen": "x"}])
def test_eigenes_zeichen_mit_ungueltiger_eingabe_ergibt_400(client, speicher, aenderung):
    arbeit_id, (seite_id,), _ = _arbeit(speicher)
    inhalt = {"kategorie": "R", "typ": "wort", "x": 1, "y": 1, "breite": 20, "hoehe": 10,
              **aenderung}
    inhalt = {feld: wert for feld, wert in inhalt.items() if wert is not None}
    _fehler(client.post(f"/seite/{seite_id}/zeichen", json=inhalt), 400)
    _fehler(client.post(f"/seite/{seite_id}/zeichen", json=[inhalt]), 400)
    assert speicher.arbeit(arbeit_id)["seiten"][0]["zeichen"] == []


# --- Jede Änderung hebt die Gesamtbestätigung auf ----------------------------------------------------

@pytest.mark.parametrize("zeichen, pfad, inhalt", [
    (_zeichen(**FEST), "/zeichen/{z}/verwerfen", None),
    (_zeichen(**FEST), "/zeichen/{z}/zurueckholen", None),
    (_zeichen(status="verworfen"), "/zeichen/{z}/zurueckholen", None),
    (_zeichen(**FEST), "/zeichen/{z}/aendern", {"kategorie": "Gr"}),
    (_zeichen(**FEST), "/zeichen/{z}/aendern", {"vorschlag": "anders"}),
    (_zeichen(**HAND), "/zeichen/{z}/aendern", {"kategorie": "A"}),
    (_zeichen(**FEST), "/zeichen/{z}/rahmen", {"x": 11, "y": 20, "breite": 30, "hoehe": 8}),
    (_zeichen(**HAND), "/zeichen/{z}/rahmen", {"x": 10, "y": 20, "breite": 30, "hoehe": 9}),
    (_zeichen(**HAND), "/zeichen/{z}/loeschen", None),
    (_zeichen(**FEST), "/seite/{s}/zeichen",
     {"kategorie": "R", "typ": "wort", "x": 1, "y": 1, "breite": 20, "hoehe": 10}),
])
def test_aenderung_an_bestaetigter_arbeit_hebt_die_bestaetigung_auf(client, speicher, zeichen,
                                                                   pfad, inhalt):
    arbeit_id, (seite_id,), (z1,) = _bestaetigt(speicher, zeichen)
    assert _ist_bestaetigt(speicher, arbeit_id) is True
    erg = _ok(client.post(pfad.format(z=z1, s=seite_id), json=inhalt))
    assert erg["arbeit"]["bestaetigt_am"] is None
    arbeit = speicher.arbeit(arbeit_id)
    assert arbeit["bestaetigt_am"] is None and arbeit["bestaetigung"] is None


def test_abgelehnte_anfrage_laesst_die_bestaetigung_stehen(client, speicher):
    arbeit_id, (seite_id,), (z1,) = _bestaetigt(speicher, _zeichen(**FEST))
    _fehler(client.post(f"/zeichen/{z1}/bestaetigen"), 409)
    _fehler(client.post(f"/zeichen/{z1}/loeschen"), 409)
    _fehler(client.post(f"/zeichen/{z1}/aendern", json={"kategorie": "Xy"}), 409)
    _fehler(client.post(f"/zeichen/{z1}/rahmen", json={"x": 1}), 400)
    _fehler(client.post(f"/seite/{seite_id}/zeichen", json={"kategorie": "R"}), 400)
    assert _ist_bestaetigt(speicher, arbeit_id) is True


# --- Rest bestätigen und Gesamtbestätigung -------------------------------------------------------

def test_gesamtbestaetigung_scheitert_mit_offenem_zeichen_und_gelingt_nach_rest_bestaetigen(
        client, speicher):
    arbeit_id, seiten, (z1, z2, z3) = _arbeit(
        speicher, _zeichen(), _zeichen(x=300), _zeichen(y=200, **FEST), seitenzahl=2)
    z4 = speicher.zeichen_anlegen(seiten[1], _zeichen())
    assert "3" in _fehler(client.post(f"/arbeit/{arbeit_id}/bestaetigen"), 409)
    assert _ist_bestaetigt(speicher, arbeit_id) is False

    erg = _ok(client.post(f"/arbeit/{arbeit_id}/rest-bestaetigen"))
    assert sorted(erg["geaendert"]) == sorted([z1, z2, z4]) and erg["zeichen"] is None
    assert erg["arbeit"] == {"offen": 0, "bestaetigt_am": None, "bestaetigbar": True, "grund": ""}
    for nr in (z1, z2, z4):
        eintrag = speicher.zeichen_eintrag(nr)
        assert (eintrag["status"], eintrag["bestaetigt_wie"]) == ("bestaetigt", "gesammelt")
    assert speicher.zeichen_eintrag(z3)["bestaetigt_wie"] == "einzeln"

    erg = _ok(client.post(f"/arbeit/{arbeit_id}/bestaetigen"))
    assert erg["arbeit"]["bestaetigt_am"] and erg["arbeit"]["bestaetigbar"] is True
    assert erg["zahlen"] == {"einzeln": 1, "gesammelt": 3, "geaendert": 0, "verworfen": 0,
                             "hand": 0}
    arbeit = speicher.arbeit(arbeit_id)
    assert arbeit["bestaetigt_am"] == erg["arbeit"]["bestaetigt_am"]
    assert arbeit["bestaetigung"] == erg["zahlen"]


def test_rest_bestaetigen_ohne_offene_zeichen_aendert_nichts(client, speicher):
    arbeit_id, _, _ = _bestaetigt(speicher, _zeichen(**FEST), _zeichen(x=300, status="verworfen"))
    erg = _ok(client.post(f"/arbeit/{arbeit_id}/rest-bestaetigen"))
    assert erg["geaendert"] == [] and erg["arbeit"]["bestaetigt_am"]
    assert _ist_bestaetigt(speicher, arbeit_id) is True


def test_rest_bestaetigen_betrifft_nur_diese_arbeit_und_hebt_die_bestaetigung_auf(client,
                                                                                 speicher):
    arbeit_id, _, (z1,) = _arbeit(speicher, _zeichen())
    andere_id, _, (fremd,) = _arbeit(speicher, _zeichen())
    _ok(client.post(f"/arbeit/{arbeit_id}/rest-bestaetigen"))
    assert speicher.zeichen_eintrag(fremd)["status"] == "offen"
    # Eine bestätigte Arbeit bekommt etwa durch Zurückholen wieder ein offenes Zeichen.
    speicher.arbeit_bestaetigen(arbeit_id)
    speicher.zeichen_aendern(z1, status="offen", bestaetigt_wie=None)
    erg = _ok(client.post(f"/arbeit/{arbeit_id}/rest-bestaetigen"))
    assert erg["geaendert"] == [z1] and erg["arbeit"]["bestaetigt_am"] is None


def test_die_gespeicherten_zahlen_stimmen(client, speicher):
    arbeit_id, (seite_id,), z = _arbeit(speicher, *(_zeichen(x=40 * i) for i in range(9)))
    for nr in z[0:2]:
        _ok(client.post(f"/zeichen/{nr}/bestaetigen"))                       # 2 einzeln
    _ok(client.post(f"/zeichen/{z[2]}/aendern", json={"kategorie": "Gr"}))   # 1 geändert
    for nr in z[3:6]:
        _ok(client.post(f"/zeichen/{nr}/verwerfen"))                         # 3 verworfen
    for i in range(2):                                                       # 2 selbst gesetzt
        _ok(client.post(f"/seite/{seite_id}/zeichen", json={
            "kategorie": "A", "typ": "wort", "x": 10, "y": 100 + 30 * i, "breite": 40,
            "hoehe": 10}))
    erwartet = {"einzeln": 2, "gesammelt": 0, "geaendert": 1, "verworfen": 3, "hand": 2}
    antwort = client.get(f"/arbeit/{arbeit_id}/zahlen")
    assert antwort.status_code == 200
    stand = antwort.get_json()
    assert stand["zahlen"] == erwartet and stand["bestaetigbar"] is False
    assert "3" in stand["grund"] and stand["arbeit"]["offen"] == 3
    assert set(stand["arbeit"]) == ARBEIT_FELDER

    assert len(_ok(client.post(f"/arbeit/{arbeit_id}/rest-bestaetigen"))["geaendert"]) == 3
    erwartet["gesammelt"] = 3                                                # 3 gesammelt
    stand = client.get(f"/arbeit/{arbeit_id}/zahlen").get_json()
    assert stand["zahlen"] == erwartet and stand["bestaetigbar"] is True and stand["grund"] == ""
    erg = _ok(client.post(f"/arbeit/{arbeit_id}/bestaetigen", json={"zahlen": erwartet}))
    assert erg["zahlen"] == erwartet
    assert speicher.arbeit(arbeit_id)["bestaetigung"] == erwartet
    assert speicher.aufgaben()[0]["bestaetigt"] == 1


def test_gesamtbestaetigung_mit_veralteten_zahlen_ergibt_409(client, speicher):
    arbeit_id, _, _ = _arbeit(speicher, _zeichen(**FEST))
    veraltet = {"einzeln": 0, "gesammelt": 1, "geaendert": 0, "verworfen": 0, "hand": 0}
    assert "geändert" in _fehler(
        client.post(f"/arbeit/{arbeit_id}/bestaetigen", json={"zahlen": veraltet}), 409)
    assert _ist_bestaetigt(speicher, arbeit_id) is False


@pytest.mark.parametrize("inhalt", [
    [], "ja", {"zahlen": 3}, {"zahlen": {"einzeln": 1}}, {"ja": True},
    {"zahlen": {"einzeln": "1", "gesammelt": 0, "geaendert": 0, "verworfen": 0, "hand": 0}},
    {"zahlen": {"einzeln": True, "gesammelt": 0, "geaendert": 0, "verworfen": 0, "hand": 0}}])
def test_gesamtbestaetigung_mit_ungueltiger_eingabe_ergibt_400(client, speicher, inhalt):
    arbeit_id, _, _ = _arbeit(speicher, _zeichen(**FEST))
    _fehler(client.post(f"/arbeit/{arbeit_id}/bestaetigen", json=inhalt), 400)
    assert _ist_bestaetigt(speicher, arbeit_id) is False


@pytest.mark.parametrize("status, wort", [("fehlgeschlagen", "fehlgeschlagen"), ("wartet", "läuft"),
                                          ("neu", "analysiert")])
def test_gesamtbestaetigung_scheitert_bei_nicht_fertiger_seite(client, speicher, status, wort):
    arbeit_id, seiten, _ = _arbeit(speicher, seitenzahl=2)
    speicher.seite_status(seiten[1], status)
    grund = _fehler(client.post(f"/arbeit/{arbeit_id}/bestaetigen"), 409)
    assert wort in grund and "Seite 2" in grund
    assert _ist_bestaetigt(speicher, arbeit_id) is False


# --- Kürzel der Arbeit -----------------------------------------------------------------------------

def test_kuerzel_der_arbeit_umbenennen_laesst_die_bestaetigung(client, speicher):
    arbeit_id, _, _ = _bestaetigt(speicher, _zeichen(**FEST))
    erg = _ok(client.post(f"/arbeit/{arbeit_id}/kuerzel", json={"kuerzel": "  7b-03 "}))
    assert erg["kuerzel"] == "7b-03" and erg["arbeit"]["bestaetigt_am"]
    assert speicher.arbeit(arbeit_id)["kuerzel"] == "7b-03"
    assert _ist_bestaetigt(speicher, arbeit_id) is True
    _ok(client.post(f"/arbeit/{arbeit_id}/kuerzel", json={"kuerzel": "x" * 20}))


@pytest.mark.parametrize("inhalt", [
    None, {}, {"kuerzel": ""}, {"kuerzel": "   "}, {"kuerzel": "x" * 21}, {"kuerzel": 7},
    {"kuerzel": None}, {"kuerzel": "a", "reihenfolge": 1}, ["a"]])
def test_kuerzel_der_arbeit_mit_ungueltiger_eingabe_ergibt_400(client, speicher, inhalt):
    arbeit_id, _, _ = _arbeit(speicher)
    _fehler(client.post(f"/arbeit/{arbeit_id}/kuerzel", json=inhalt), 400)
    assert speicher.arbeit(arbeit_id)["kuerzel"] == "01"


# --- Neuanalyse ----------------------------------------------------------------------------------------

def test_neu_analysieren_erhaelt_entschiedenes_und_hebt_die_bestaetigung_auf(
        client, speicher, schlange, schein):
    arbeit_id, (seite_id,), (fest, weg, eigen) = _bestaetigt(
        speicher, _zeichen(**FEST), _zeichen("wier", "wir", x=300, status="verworfen"),
        _zeichen(y=200, kategorie="A", **HAND))
    schein.ergebnis = {**schein.ergebnis, "zeichen": [
        _zeichen(),                                  # deckt sich mit dem bestätigten: entfällt
        _zeichen("nähmlich", "nämlich", x=100, y=300)]}
    schein.frei.clear()
    erg = _ok(client.post(f"/seite/{seite_id}/neu-analysieren"))
    assert erg["zeichen"] is None and erg["arbeit"]["bestaetigt_am"] is None
    assert erg["arbeit"]["bestaetigbar"] is False and "läuft" in erg["arbeit"]["grund"]
    assert _ist_bestaetigt(speicher, arbeit_id) is False  # sofort, nicht erst mit dem Ergebnis
    assert speicher.seite(seite_id)["analyse_status"] in ("wartet", "laeuft")
    schein.frei.set()
    assert schlange.warten(5) is True

    assert schein.aufrufe == [seite_id]
    assert speicher.seite(seite_id)["analyse_status"] == "fertig"
    zeichen = {z["id"]: z for z in speicher.arbeit(arbeit_id)["seiten"][0]["zeichen"]}
    assert (zeichen[fest]["status"], zeichen[fest]["bestaetigt_wie"]) == ("bestaetigt", "einzeln")
    assert zeichen[weg]["status"] == "verworfen" and zeichen[weg]["gelesen"] == "wier"
    assert zeichen[eigen]["herkunft"] == "hand" and zeichen[eigen]["kategorie"] == "A"
    (neu,) = [z for nr, z in zeichen.items() if nr not in (fest, weg, eigen)]
    assert (neu["gelesen"], neu["status"], neu["herkunft"]) == ("nähmlich", "offen", "ki")
    assert _ist_bestaetigt(speicher, arbeit_id) is False


def test_neu_analysieren_ersetzt_offene_vorschlaege(client, speicher, schlange, schein):
    arbeit_id, (seite_id,), _ = _arbeit(speicher, _zeichen("alt", "alt", x=400))
    _ok(client.post(f"/seite/{seite_id}/neu-analysieren"))
    assert schlange.warten(5) is True
    (zeichen,) = speicher.arbeit(arbeit_id)["seiten"][0]["zeichen"]
    assert zeichen["gelesen"] == "Fahrad"  # der alte offene Vorschlag ist ersetzt


def test_neu_analysieren_auch_fuer_fehlgeschlagene_seite(client, speicher, schlange, schein):
    arbeit_id, (seite_id,), _ = _arbeit(speicher)
    speicher.seite_status(seite_id, "fehlgeschlagen", fehlermeldung="Zeitüberschreitung")
    _ok(client.post(f"/seite/{seite_id}/neu-analysieren"))
    assert schlange.warten(5) is True
    seite = speicher.seite(seite_id)
    assert seite["analyse_status"] == "fertig" and seite["fehlermeldung"] is None


@pytest.mark.parametrize("status", ["neu", "wartet", "laeuft"])
def test_neu_analysieren_nur_fuer_fertige_oder_fehlgeschlagene_seiten(client, speicher, schlange,
                                                                     schein, status):
    arbeit_id, (seite_id,), _ = _arbeit(speicher)
    speicher.seite_status(seite_id, status)
    _fehler(client.post(f"/seite/{seite_id}/neu-analysieren"), 409)
    assert schlange.warten(1) is True and schein.aufrufe == []
    assert speicher.seite(seite_id)["analyse_status"] == status


def test_neu_analysieren_ohne_schluessel_reiht_nichts_ein(client, speicher, schein, monkeypatch):
    arbeit_id, (seite_id,), _ = _bestaetigt(speicher, _zeichen(**FEST))
    monkeypatch.delenv("GEMINI_API_KEY")
    assert "GEMINI_API_KEY" in _fehler(client.post(f"/seite/{seite_id}/neu-analysieren"), 409)
    assert schein.aufrufe == [] and speicher.seite(seite_id)["analyse_status"] == "fertig"
    assert _ist_bestaetigt(speicher, arbeit_id) is True


# --- Einstellungen: eigene Kürzel ----------------------------------------------------------------------

def test_kuerzelseite_zeigt_die_voreinstellung(client):
    antwort = client.get("/einstellungen/kuerzel")
    text = _text(antwort)
    assert antwort.status_code == 200 and "Eigene Kürzel" in text
    for kuerzel, bezeichnung in (("A", "Ausdruck"), ("Sb", "Satzbau"), ("T", "Tempus"),
                                 ("W", "Wortwahl"), ("I", "Inhalt")):
        assert f'value="{kuerzel}"' in text and f'value="{bezeichnung}"' in text
    assert 'method="post"' in text and 'name="kuerzel"' in text and 'name="bezeichnung"' in text
    assert "Speichern" in text


def test_kuerzelseite_speichert_die_liste_und_uebergeht_leere_zeilen(client, speicher):
    antwort = client.post("/einstellungen/kuerzel", data={
        "kuerzel": [" St ", "", "A", "  "], "bezeichnung": ["Stil", "", " Ausdruck ", " "]})
    assert antwort.status_code == 302
    assert antwort.headers["Location"].endswith("/einstellungen/kuerzel")
    assert speicher.kuerzel() == [{"kuerzel": "St", "bezeichnung": "Stil"},
                                  {"kuerzel": "A", "bezeichnung": "Ausdruck"}]
    text = _text(client.get("/einstellungen/kuerzel"))
    assert "gespeichert" in text and 'value="St"' in text and 'value="Sb"' not in text
    assert client.post("/einstellungen/kuerzel", data={}).status_code == 302
    assert speicher.kuerzel() == []


@pytest.mark.parametrize("kuerzel, bezeichnung, wort", [
    (["R"], ["Rechtschreibung"], "fest vergeben"), (["z"], ["Zeichen"], "fest vergeben"),
    (["GR"], ["Grammatik"], "fest vergeben"), (["Ausdr"], ["Ausdruck"], "zu lang"),
    (["A1"], ["Ausdruck"], "Buchstaben"), (["A", "a"], ["eins", "zwei"], "doppelt"),
    (["A"], [""], "Bezeichnung"), ([""], ["Ausdruck"], "Kürzel"),
    (["A"], ["x" * 41], "zu lang"), (["A", "St"], ["nur eine"], "Bezeichnung")])
def test_kuerzelseite_lehnt_unzulaessiges_ab_und_behaelt_die_eingaben(client, speicher, kuerzel,
                                                                     bezeichnung, wort):
    antwort = client.post("/einstellungen/kuerzel", data={"kuerzel": kuerzel,
                                                          "bezeichnung": bezeichnung})
    text = _text(antwort)
    assert antwort.status_code == 400 and 'class="meldung fehler"' in text and wort in text
    assert f'value="{kuerzel[0]}"' in text
    assert [e["kuerzel"] for e in speicher.kuerzel()] == ["A", "Sb", "T", "W", "I"]


def test_kuerzelseite_maskiert_eingaben(client):
    text = _text(client.post("/einstellungen/kuerzel", data={
        "kuerzel": ['"><b>'], "bezeichnung": ["<script>alert(1)</script>"]}))
    assert "<script>alert(1)</script>" not in text and '"><b>' not in text


def test_kuerzelseite_weist_fremde_herkunft_ab(client, speicher):
    antwort = client.post("/einstellungen/kuerzel", data={"kuerzel": ["St"],
                                                          "bezeichnung": ["Stil"]},
                          headers={"Origin": "http://boese.example"})
    assert antwort.status_code == 403 and len(speicher.kuerzel()) == 5


# --- Daten der Ansicht -----------------------------------------------------------------------------------

def test_arbeit_bettet_die_daten_der_korrekturansicht_ein(client, speicher):
    arbeit_id, (s1, s2), (offen, fest, weg, eigen) = _arbeit(
        speicher, _zeichen(), _zeichen(x=100, **FEST),
        _zeichen("wier", "wir", x=300, status="verworfen"),
        _zeichen(y=200, kategorie="A", **{**HAND, "vorschlag": "treffender"}), seitenzahl=2)
    speicher.zeichen_anlegen(s2, _zeichen())
    speicher.seite_status(s2, "fehlgeschlagen", fehlermeldung="x")
    daten = _daten(_text(client.get(f"/arbeit/{arbeit_id}")), "arbeit-daten")

    assert daten["seite"] == {"id": s1, "nummer": 1, "breite": 600, "hoehe": 400}
    assert [z["id"] for z in daten["zeichen"]] == [offen, fest, eigen]
    assert [z["id"] for z in daten["verworfen"]] == [weg]
    for z in daten["zeichen"] + daten["verworfen"]:
        assert set(z) == ZEICHEN_FELDER and z["seite_id"] == s1
    je = {z["id"]: z for z in daten["zeichen"] + daten["verworfen"]}
    assert (je[offen]["herkunft"], je[offen]["status"], je[offen]["bestaetigt_wie"]) == (
        "ki", "offen", None)
    assert (je[fest]["status"], je[fest]["bestaetigt_wie"]) == ("bestaetigt", "einzeln")
    assert (je[weg]["status"], je[weg]["gelesen"]) == ("verworfen", "wier")
    assert (je[eigen]["herkunft"], je[eigen]["status"], je[eigen]["bestaetigt_wie"]) == (
        "hand", "bestaetigt", None)
    assert daten["arbeit"] == {
        "id": arbeit_id, "kuerzel": "01", "offen": 2, "bestaetigt_am": None,
        "bestaetigung": None, "bestaetigbar": False, "grund": daten["arbeit"]["grund"]}
    assert "Seite 2" in daten["arbeit"]["grund"] and "fehlgeschlagen" in daten["arbeit"]["grund"]
    assert daten["seiten"] == [
        {"id": s1, "nummer": 1, "status": "fertig", "offen": 1},
        {"id": s2, "nummer": 2, "status": "fehlgeschlagen", "offen": 1}]
    assert daten["kuerzel"][:4] == [
        {"kuerzel": "R", "bezeichnung": "Rechtschreibung", "eigen": False},
        {"kuerzel": "Z", "bezeichnung": "Zeichensetzung", "eigen": False},
        {"kuerzel": "Gr", "bezeichnung": "Grammatik", "eigen": False},
        {"kuerzel": "A", "bezeichnung": "Ausdruck", "eigen": True}]
    assert [k["kuerzel"] for k in daten["kuerzel"]] == ["R", "Z", "Gr", "A", "Sb", "T", "W", "I"]
    aufgabe_id = speicher.arbeit(arbeit_id)["aufgabe_id"]
    assert daten["url_stand"] == f"/aufgabe/{aufgabe_id}/stand"


def test_arbeit_bettet_bestaetigung_und_geaenderte_kuerzel_ein(client, speicher):
    arbeit_id, _, _ = _bestaetigt(speicher, _zeichen(**FEST))
    speicher.kuerzel_setzen([{"kuerzel": "St", "bezeichnung": "Stil"}])
    daten = _daten(_text(client.get(f"/arbeit/{arbeit_id}")), "arbeit-daten")
    arbeit = speicher.arbeit(arbeit_id)
    assert daten["arbeit"]["bestaetigt_am"] == arbeit["bestaetigt_am"]
    assert daten["arbeit"]["bestaetigung"] == {"einzeln": 1, "gesammelt": 0, "geaendert": 0,
                                               "verworfen": 0, "hand": 0}
    assert daten["arbeit"]["bestaetigbar"] is True and daten["arbeit"]["grund"] == ""
    assert [k["kuerzel"] for k in daten["kuerzel"]] == ["R", "Z", "Gr", "St"]
    assert daten["verworfen"] == []


# --- Korrekturansicht, Stapelansicht und Aufgabenliste ---------------------------------------------------

def test_korrekturansicht_hat_fussleiste_dialoge_und_legende(client, speicher):
    arbeit_id, _, _ = _arbeit(speicher, _zeichen())
    text = _text(client.get(f"/arbeit/{arbeit_id}"))
    for kennung in ("setzen-knopf", "rest-knopf", "gesamt-knopf", "neu-analyse-knopf",
                    "kuerzel-knopf", "bestaetigt-anzeige", "meldung"):
        assert f'id="{kennung}"' in text, kennung
    for dialog in ("rest-dialog", "gesamt-dialog", "neu-analyse-dialog"):
        assert f'<dialog id="{dialog}"' in text, dialog
    for wort in ("Rest bestätigen", "Korrektur gesamt bestätigen", "Seite neu analysieren",
                 "Zeichen setzen", "einzeln bestätigt", "gesammelt bestätigt", "geändert",
                 "verworfen", "selbst gesetzt", "Richtigkeit der gesamten Korrektur"):
        assert wort in text, wort
    for taste in ("N", "Tab", "B", "Enter", "V", "Entf", "Z", "E", "S", "Esc"):
        assert f"<kbd>{taste}</kbd>" in text, taste
    assert "Etappe 2" not in text and "Sicherheit" not in text


def test_stand_nennt_den_bestaetigungsstatus(client, speicher):
    arbeit_id, _, _ = _bestaetigt(speicher, _zeichen(**FEST))
    aufgabe_id = speicher.arbeit(arbeit_id)["aufgabe_id"]
    (seite_id,) = speicher.arbeit_anlegen(aufgabe_id, [("x.jpg", _bild())])
    _mit_zeichen(speicher, seite_id, _zeichen())
    stand = client.get(f"/aufgabe/{aufgabe_id}/stand").get_json()
    erste, zweite = stand["arbeiten"]
    assert erste["bestaetigt_am"] == speicher.arbeit(arbeit_id)["bestaetigt_am"]
    assert erste["bestaetigt_am"] is not None and erste["bestaetigbar"] is True
    assert zweite["bestaetigt_am"] is None and zweite["bestaetigbar"] is False
    assert (stand["gesamt"]["arbeiten"], stand["gesamt"]["bestaetigt"]) == (2, 1)
    client.post(f"/zeichen/{speicher.arbeit(arbeit_id)['seiten'][0]['zeichen'][0]['id']}/verwerfen")
    stand = client.get(f"/aufgabe/{aufgabe_id}/stand").get_json()
    assert stand["arbeiten"][0]["bestaetigt_am"] is None and stand["gesamt"]["bestaetigt"] == 0


def test_stapelansicht_und_aufgabenliste_zeigen_die_bestaetigung(client, speicher):
    arbeit_id, _, _ = _bestaetigt(speicher, _zeichen(**FEST))
    aufgabe_id = speicher.arbeit(arbeit_id)["aufgabe_id"]
    (seite_id,) = speicher.arbeit_anlegen(aufgabe_id, [("x.jpg", _bild())])
    _mit_zeichen(speicher, seite_id, _zeichen())
    text = _text(client.get(f"/aufgabe/{aufgabe_id}"))
    assert "1 von 2 Arbeiten bestätigt" in text
    assert text.count("Korrektur bestätigt") == 1 and text.count("noch nicht bestätigt") == 1
    text = _text(client.get("/"))
    assert "1 von 2 Arbeiten bestätigt" in text
    assert 'href="/einstellungen/kuerzel"' in text and "Eigene Kürzel" in text


def test_kuerzelseite_nennt_die_festen_kuerzel_und_fuehrt_zurueck(client):
    text = _text(client.get("/einstellungen/kuerzel"))
    for name in ("Rechtschreibung", "Zeichensetzung", "Grammatik"):
        assert name in text
    assert 'value="R"' not in text  # die festen Kürzel sind keine Eingabefelder
    assert 'href="/"' in text
