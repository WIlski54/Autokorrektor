import json

from korrektor import auswertung as a

LOESUNG = {
    "soll_text": "Das Fahrad steht da weil es Rhythmus hat. Mann kann sagen, das es den Weg nicht findet.",
    "fehler": [
        {"id": 1, "kategorie": "R", "falsch": "Fahrad", "richtig": "Fahrrad"},
        {"id": 2, "kategorie": "Z", "falsch": "da weil", "richtig": "da, weil"},
        {"id": 3, "kategorie": "R", "falsch": "Mann", "richtig": "Man"},
        {"id": 4, "kategorie": "R", "falsch": "sagen, das", "richtig": "sagen, dass"},
    ],
    "fallen": ["Rhythmus"],
}


def _fund(nr, kategorie, gelesen, vorschlag):
    return {"id": nr, "kategorie": kategorie, "gelesen": gelesen, "vorschlag": vorschlag,
            "anker": {"typ": "wort", "rahmen": [0, 0, 10, 10]}}


def _ergebnis(funde, transkription, fehlermeldung=None):
    return {"bild": "C_1_gerade.jpg", "verfahren": "x", "transkription": transkription,
            "funde": funde, "dauer_s": 2.0, "nutzung": {"eingabe": 100, "ausgabe": 50},
            "fehlermeldung": fehlermeldung}


def test_enthaelt():
    assert a.enthaelt(["a", "b", "c"], ["b", "c"]) and not a.enthaelt(["a", "b"], ["b", "a"])
    assert not a.enthaelt(["a"], [])


def test_kern_trennt_aenderung_und_kontext():
    assert a.kern("kurz, das sie", "kurz, dass sie") == {
        "alt": ["das"], "neu": ["dass"], "davor": ",", "danach": "sie"}
    assert a.kern("Gefühl dass", "Gefühl, dass") == {
        "alt": [], "neu": [","], "davor": "Gefühl", "danach": "dass"}
    assert a.kern("weg ging", "wegging") == {
        "alt": ["weg", "ging"], "neu": ["wegging"], "davor": None, "danach": None}


def test_trifft_bei_kontext_auf_der_anderen_seite():
    e = LOESUNG["fehler"][3]
    assert a.trifft(_fund(1, "R", "das es", "dass es"), e) > 0
    assert a.trifft(_fund(1, "Gr", "das", "dass"), e) > 0
    assert a.trifft(_fund(1, "R", "sagen, das", "sagen, dass."), e) > 0


def test_trifft_nicht_bei_blossem_komma_oder_unveraendertem_wort():
    komma = LOESUNG["fehler"][1]
    assert a.trifft(_fund(1, "Z", "es Rhythmus", ","), komma) == 0
    assert a.trifft(_fund(1, "Z", "da weil", ", weil"), komma) > 0
    assert a.trifft(_fund(1, "Z", "steht da weil", "steht da, weil es"), komma) > 0
    man = LOESUNG["fehler"][2]
    assert a.trifft(_fund(1, "Z", "Man kann", "Man, kann"), man) == 0


def test_zuordnen_ein_fund_deckt_zwei_nachbarfehler():
    funde = [_fund(1, "R", "Mann kann sagen, das", "Man kann sagen, dass")]
    zuordnung, dubletten = a.zuordnen(funde, LOESUNG["fehler"])
    assert sorted(zuordnung[1]) == [3, 4] and dubletten == set()


def test_zuordnen_dublette_ist_weder_gefunden_noch_erfunden():
    loesung = [{"id": 1, "kategorie": "R", "falsch": "großen und ganzen",
                "richtig": "Großen und Ganzen"}]
    funde = [_fund(1, "R", "großen", "Großen"), _fund(2, "R", "ganzen", "Ganzen")]
    zuordnung, dubletten = a.zuordnen(funde, loesung)
    assert zuordnung == {1: [1]} and dubletten == {2}


def test_zuordnen_waehlt_bei_gleichem_wort_den_passenden_kontext():
    loesung = [{"id": 1, "kategorie": "R", "falsch": "Leser, das", "richtig": "Leser, dass"},
               {"id": 2, "kategorie": "R", "falsch": "zeigen, das", "richtig": "zeigen, dass"}]
    zuordnung, _ = a.zuordnen([_fund(1, "R", "zeigen, das ein", "zeigen, dass ein")], loesung)
    assert zuordnung == {1: [2]}


def test_alles_gefunden():
    funde = [_fund(1, "R", "Fahrad", "Fahrrad"), _fund(2, "Z", "da weil", "da, weil"),
             _fund(3, "R", "Mann", "Man"), _fund(4, "R", "das", "dass")]
    klicks = {"x/C_1_gerade/1": {"sitzt": True}, "x/C_1_gerade/2": {"sitzt": False}}
    w = a.bild_auswerten(_ergebnis(funde, LOESUNG["soll_text"]), LOESUNG, klicks)
    assert (w["gefunden"], w["fehler_gesamt"], w["erfunden"]) == (4, 4, 0)
    assert (w["lesetreu"], w["lesetreue_gesamt"]) == (3, 3)
    assert (w["platz_sitzt"], w["platz_geprueft"], w["platz_offen"]) == (1, 2, 2)
    assert w["nach_kategorie"] == {"R": [3, 3], "Z": [1, 1], "Gr": [0, 0]}
    assert w["fallen"] == 0 and w["fallen_gesamt"] == 1


def test_nichts_gefunden_und_still_berichtigt():
    berichtigt = "Das Fahrrad steht da, weil es Rhythmus hat. Man kann sagen, dass es den Weg nicht findet."
    w = a.bild_auswerten(_ergebnis([], berichtigt), LOESUNG, {})
    assert (w["gefunden"], w["erfunden"], w["lesetreu"]) == (0, 0, 0)


def test_urteile_der_pruefseite():
    funde = [_fund(1, "R", "Farad", "Fahrrad"),      # verlesen: von Hand Fehler 1 zugewiesen
             _fund(2, "R", "Rhythmus", "Rythmus"),   # erfunden, löst Falle aus
             _fund(3, "R", "hat", "hatt"),           # echter Fehler außerhalb der Lösung
             _fund(4, "R", "findet", "findett")]     # unbewertet zählt als erfunden
    klicks = {"x/C_1_gerade/1": {"urteil": "fehler:1", "sitzt": True},
              "x/C_1_gerade/2": {"urteil": "erfunden"},
              "x/C_1_gerade/3": {"urteil": "echt"}}
    w = a.bild_auswerten(_ergebnis(funde, LOESUNG["soll_text"]), LOESUNG, klicks)
    assert (w["gefunden"], w["erfunden"], w["fallen"]) == (1, 2, 1)
    assert w["erfundene"] == [funde[1], funde[3]]
    assert (w["platz_sitzt"], w["platz_geprueft"], w["platz_offen"]) == (1, 1, 1)


def test_ausfall_zaehlt_nicht_fuer_lesetreue_und_null_felder_stoeren_nicht():
    erg = _ergebnis([], None, "RuntimeError: x")
    erg["nutzung"] = None
    w = a.bild_auswerten(erg, LOESUNG, {})
    assert w["ausfall"] == 1 and w["lesetreue_gesamt"] == 0 and w["eingabe"] == 0


def test_kennzahlen_und_schwelle():
    seite = {"seiten": 1, "fehler_gesamt": 10, "gefunden": 9, "erfunden": 1, "dubletten": 0,
             "verworfen": 0, "lesetreu": 6, "lesetreue_gesamt": 8, "fallen": 0,
             "fallen_gesamt": 4, "platz_sitzt": 9, "platz_geprueft": 9, "platz_offen": 0,
             "ausfall": 0, "dauer_s": 2.0, "eingabe": 1, "ausgabe": 1,
             "nach_kategorie": {"R": [5, 6], "Z": [3, 3], "Gr": [1, 1]}, "erfundene": []}
    summe = a.summieren([seite, seite])
    k = a.kennzahlen(summe)
    assert k["gefunden"] == 0.9 and k["erfunden_pro_seite"] == 1.0
    assert k["platzierung"] == 1.0 and k["lesetreue"] == 0.75
    assert summe["nach_kategorie"]["R"] == [10, 12]
    schwellen = {"gefunden_min": 0.85, "erfunden_pro_seite_max": 1.0, "platzierung_min": 0.9}
    assert a.bestanden(k, schwellen) is True
    assert a.bestanden({**k, "gefunden": 0.8}, schwellen) is False
    assert a.bestanden({**k, "platzierung": None}, schwellen) is False
    mit_ausfall = a.summieren([seite, {**seite, "ausfall": 1, "erfunden": 0}])
    assert a.kennzahlen(mit_ausfall)["erfunden_pro_seite"] == 1.0


def test_loesung_laden_bevorzugt_abschrift(tmp_path):
    ordner = tmp_path / "vorlagen"
    ordner.mkdir()
    (ordner / "loesung_C.json").write_text(json.dumps({"k": "allgemein"}), encoding="utf-8")
    (ordner / "loesung_C_2.json").write_text(json.dumps({"k": "abschrift"}), encoding="utf-8")
    assert a.loesung_laden(tmp_path, "C_1_gerade.jpg") == {"k": "allgemein"}
    assert a.loesung_laden(tmp_path, "C_2_schraeg.jpg") == {"k": "abschrift"}
    assert a.loesung_laden(tmp_path, "X_1_gerade.jpg") is None
