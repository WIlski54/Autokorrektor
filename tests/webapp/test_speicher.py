import io
import sqlite3

import pytest
from PIL import Image

from webapp.speicher import Speicher


@pytest.fixture
def speicher(tmp_path):
    return Speicher(tmp_path / "daten")


def _aufgabe(speicher, **felder):
    werte = {"titel": "Versuchsbeschreibung", "fach": "Deutsch", "jahrgang": 9,
             "kategorien": ["R", "Z", "Gr"], "verfahren": "gemini", **felder}
    return speicher.aufgabe_anlegen(**werte)


def _bild(groesse=(60, 40), farbe="white", format="JPEG", **zusatz):
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, format=format, **zusatz)
    return puffer.getvalue()


def _bilddateien(speicher):
    return sorted(p.name for p in speicher.bilder.iterdir())


def _fuenf_fotos(speicher, nr, marken=(1, 0, 1, 1, 0)):
    ids = [speicher.bild_ablegen(nr, f"{i}.jpg", _bild((60 + i, 40))) for i in range(len(marken))]
    speicher.ablage_ordnen(nr, [{"id": i, "neue_arbeit": bool(m)} for i, m in zip(ids, marken)])
    return ids


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


# --- Ablage, Arbeiten, Seiten ----------------------------------------------------------

def test_bild_ablegen_speichert_jpeg_mit_groesse(speicher):
    nr = _aufgabe(speicher)
    ablage_id = speicher.bild_ablegen(nr, "foto.png", _bild((60, 40), format="PNG"))
    (eintrag,) = speicher.ablage(nr)
    assert eintrag["id"] == ablage_id and eintrag["aufgabe_id"] == nr
    assert (eintrag["breite"], eintrag["hoehe"]) == (60, 40)
    assert eintrag["neue_arbeit"] is True
    pfad = speicher.bildpfad(eintrag["bilddatei"])
    assert pfad.parent == speicher.bilder and pfad.suffix == ".jpg"
    with Image.open(pfad) as img:
        assert img.format == "JPEG" and img.size == (60, 40)


def test_ablage_eintrag_liefert_einen_eintrag_oder_none(speicher):
    nr = _aufgabe(speicher)
    ablage_id = speicher.bild_ablegen(nr, "foto.jpg", _bild((60, 40)))
    eintrag = speicher.ablage_eintrag(ablage_id)
    assert eintrag == speicher.ablage(nr)[0]
    assert eintrag["neue_arbeit"] is True and eintrag["aufgabe_id"] == nr
    assert speicher.ablage_eintrag(999) is None


def test_bilddaten_liefert_original_oder_vorschau(speicher):
    nr = _aufgabe(speicher)
    eintrag = speicher.ablage_eintrag(speicher.bild_ablegen(nr, "foto.jpg", _bild((800, 400))))
    pfad = speicher.bildpfad(eintrag["bilddatei"])
    assert speicher.bilddaten(eintrag["bilddatei"]) == pfad.read_bytes()
    with Image.open(io.BytesIO(speicher.bilddaten(eintrag["bilddatei"], breite=200))) as img:
        assert img.format == "JPEG" and img.size == (200, 100)
    # nie größer als das Original
    assert speicher.bilddaten(eintrag["bilddatei"], breite=5000) == pfad.read_bytes()
    assert speicher.bilddaten("fehlt.jpg") is None


def test_bild_ablegen_nimmt_webp_und_vergibt_eindeutige_namen(speicher):
    nr = _aufgabe(speicher)
    speicher.bild_ablegen(nr, "gleich.jpg", _bild())
    speicher.bild_ablegen(nr, "gleich.jpg", _bild())
    speicher.bild_ablegen(nr, "foto.webp", _bild(format="WEBP"))
    eintraege = speicher.ablage(nr)
    assert len({e["bilddatei"] for e in eintraege}) == 3
    assert [e["reihenfolge"] for e in eintraege] == sorted({e["reihenfolge"] for e in eintraege})
    assert len(_bilddateien(speicher)) == 3


def test_bild_ablegen_dreht_exif_orientierung_aufrecht(speicher):
    nr = _aufgabe(speicher)
    roh = Image.new("RGB", (40, 20), "white")
    roh.paste((255, 0, 0), (0, 0, 20, 20))  # linke Hälfte rot: liegt nach dem Drehen oben
    exif = Image.Exif()
    exif[0x0112] = 6
    puffer = io.BytesIO()
    roh.save(puffer, format="JPEG", exif=exif, quality=95)
    speicher.bild_ablegen(nr, "quer.jpg", puffer.getvalue())
    (eintrag,) = speicher.ablage(nr)
    assert (eintrag["breite"], eintrag["hoehe"]) == (20, 40)
    with Image.open(speicher.bildpfad(eintrag["bilddatei"])) as img:
        assert img.size == (20, 40)
        assert img.getexif().get(0x0112) in (None, 1)
        oben, unten = img.getpixel((10, 5)), img.getpixel((10, 35))
    assert oben[0] > 200 and oben[1] < 60
    assert min(unten) > 200


def test_bild_ablegen_lehnt_nicht_bilder_ab(speicher):
    nr = _aufgabe(speicher)
    with pytest.raises(ValueError, match="notiz.txt"):
        speicher.bild_ablegen(nr, "notiz.txt", b"kein Bild")
    with pytest.raises(ValueError):
        speicher.bild_ablegen(nr, "leer.jpg", b"")
    with pytest.raises(ValueError):
        speicher.bild_ablegen(nr, "abgeschnitten.jpg", _bild((400, 400))[:200])
    assert speicher.ablage(nr) == [] and _bilddateien(speicher) == []


def test_bild_ablegen_ohne_aufgabe_hinterlaesst_keine_datei(speicher):
    with pytest.raises(ValueError):
        speicher.bild_ablegen(999, "foto.jpg", _bild())
    assert _bilddateien(speicher) == []


def test_ablage_ordnen_aendert_reihenfolge_und_trennmarken_und_loescht(speicher):
    nr = _aufgabe(speicher)
    a, b, c = (speicher.bild_ablegen(nr, f"{i}.jpg", _bild()) for i in range(3))
    datei_b = next(e["bilddatei"] for e in speicher.ablage(nr) if e["id"] == b)
    speicher.ablage_ordnen(nr, [{"id": c, "neue_arbeit": True}, {"id": a, "neue_arbeit": False}],
                           entfernt=[b])
    eintraege = speicher.ablage(nr)
    assert [(e["id"], e["neue_arbeit"]) for e in eintraege] == [(c, True), (a, False)]
    assert not speicher.bildpfad(datei_b).exists()
    assert len(_bilddateien(speicher)) == 2


def test_ablage_ordnen_beruehrt_andere_aufgaben_nicht(speicher):
    eins, zwei = _aufgabe(speicher), _aufgabe(speicher)
    speicher.bild_ablegen(eins, "a.jpg", _bild())
    b = speicher.bild_ablegen(zwei, "b.jpg", _bild())
    speicher.ablage_ordnen(eins, [{"id": b, "neue_arbeit": False}], entfernt=[b])
    assert len(speicher.ablage(eins)) == 1
    (fremd,) = speicher.ablage(zwei)
    assert fremd["id"] == b and fremd["neue_arbeit"] is True
    assert len(_bilddateien(speicher)) == 2


def test_ablage_ordnen_behaelt_ungenannte_fotos_und_haengt_sie_hinten_an(speicher):
    nr = _aufgabe(speicher)
    a, b, c, d = (speicher.bild_ablegen(nr, f"{i}.jpg", _bild()) for i in range(4))
    speicher.ablage_ordnen(nr, [{"id": a, "neue_arbeit": True}, {"id": b, "neue_arbeit": False},
                                {"id": c, "neue_arbeit": False}, {"id": d, "neue_arbeit": True}])
    # Ein anderes Fenster kennt nur d und a: b und c bleiben, in bisheriger Reihenfolge, hinten.
    speicher.ablage_ordnen(nr, [{"id": d, "neue_arbeit": True}, {"id": a, "neue_arbeit": False}])
    assert [(e["id"], e["neue_arbeit"]) for e in speicher.ablage(nr)] == [
        (d, True), (a, False), (b, False), (c, False)]
    assert [e["reihenfolge"] for e in speicher.ablage(nr)] == [1, 2, 3, 4]
    assert len(_bilddateien(speicher)) == 4
    speicher.ablage_ordnen(nr, [])  # ohne `entfernt` wird nie gelöscht
    assert [e["id"] for e in speicher.ablage(nr)] == [d, a, b, c]
    speicher.ablage_ordnen(nr, [{"id": c, "neue_arbeit": True}], entfernt=[d, 999])
    assert [e["id"] for e in speicher.ablage(nr)] == [c, a, b]
    assert len(_bilddateien(speicher)) == 3


def test_ablage_zu_arbeiten_bildet_arbeiten_nach_trennmarken(speicher):
    nr = _aufgabe(speicher)
    _fuenf_fotos(speicher, nr)
    dateien = [e["bilddatei"] for e in speicher.ablage(nr)]
    seiten = speicher.ablage_zu_arbeiten(nr)
    assert len(seiten) == 5 and len(set(seiten)) == 5
    arbeiten = speicher.arbeiten(nr)
    assert [a["kuerzel"] for a in arbeiten] == ["01", "02", "03"]
    assert [len(a["seiten"]) for a in arbeiten] == [2, 1, 2]
    assert [[s["nummer"] for s in a["seiten"]] for a in arbeiten] == [[1, 2], [1], [1, 2]]
    alle = [s for a in arbeiten for s in a["seiten"]]
    assert [s["id"] for s in alle] == seiten
    assert [s["bilddatei"] for s in alle] == dateien
    assert [s["breite"] for s in alle] == [60, 61, 62, 63, 64]
    assert {s["analyse_status"] for s in alle} == {"wartet"}  # ein Neustart findet sie wieder
    assert speicher.seiten_unfertig() == seiten
    assert {s["lauf"] for s in alle} == {0}
    assert speicher.ablage(nr) == []
    assert len(_bilddateien(speicher)) == 5
    assert speicher.ablage_zu_arbeiten(nr) == []


def test_erstes_foto_beginnt_immer_eine_arbeit(speicher):
    nr = _aufgabe(speicher)
    _fuenf_fotos(speicher, nr, marken=(0, 0, 1))
    speicher.ablage_zu_arbeiten(nr)
    assert [len(a["seiten"]) for a in speicher.arbeiten(nr)] == [2, 1]


def test_arbeit_anlegen_setzt_nummerierung_fort(speicher):
    nr = _aufgabe(speicher)
    _fuenf_fotos(speicher, nr)
    speicher.ablage_zu_arbeiten(nr)
    seiten = speicher.arbeit_anlegen(nr, [("a.jpg", _bild((30, 50))),
                                          ("b.png", _bild(format="PNG"))])
    assert len(seiten) == 2
    arbeiten = speicher.arbeiten(nr)
    assert [a["kuerzel"] for a in arbeiten] == ["01", "02", "03", "04"]
    assert [s["id"] for s in arbeiten[-1]["seiten"]] == seiten
    assert [s["nummer"] for s in arbeiten[-1]["seiten"]] == [1, 2]
    seite = speicher.seite(seiten[0])
    assert (seite["breite"], seite["hoehe"]) == (30, 50)
    assert seite["arbeit_id"] == arbeiten[-1]["id"] and seite["analyse_status"] == "wartet"
    assert set(seiten) <= set(speicher.seiten_unfertig())
    # Auch eine spätere Ablage zählt weiter.
    speicher.bild_ablegen(nr, "c.jpg", _bild())
    speicher.ablage_zu_arbeiten(nr)
    assert [a["kuerzel"] for a in speicher.arbeiten(nr)][-1] == "05"


def test_arbeit_anlegen_mit_unlesbarem_bild_legt_nichts_an(speicher):
    nr = _aufgabe(speicher)
    with pytest.raises(ValueError, match="kaputt.jpg"):
        speicher.arbeit_anlegen(nr, [("gut.jpg", _bild()), ("kaputt.jpg", b"nichts")])
    with pytest.raises(ValueError):
        speicher.arbeit_anlegen(nr, [])
    with pytest.raises(ValueError):
        speicher.arbeit_anlegen(999, [("gut.jpg", _bild())])
    assert speicher.arbeiten(nr) == [] and _bilddateien(speicher) == []


def test_arbeit_und_seite_lesen(speicher):
    nr = _aufgabe(speicher)
    (seite_id,) = speicher.arbeit_anlegen(nr, [("a.jpg", _bild())])
    seite = speicher.seite(seite_id)
    arbeit = speicher.arbeit(seite["arbeit_id"])
    assert arbeit["aufgabe_id"] == nr and arbeit["kuerzel"] == "01"
    assert arbeit["bestaetigt_am"] is None
    assert [s["id"] for s in arbeit["seiten"]] == [seite_id]
    assert arbeit["seiten"][0]["zeichen"] == []
    assert speicher.arbeit(999) is None and speicher.seite(999) is None


def test_aufgabe_zur_seite(speicher):
    nr, andere = _aufgabe(speicher, titel="A"), _aufgabe(speicher, titel="B")
    (seite_id,) = speicher.arbeit_anlegen(nr, [("a.jpg", _bild())])
    (fremd,) = speicher.arbeit_anlegen(andere, [("b.jpg", _bild())])
    assert speicher.aufgabe_zur_seite(seite_id) == speicher.aufgabe(nr)
    assert speicher.aufgabe_zur_seite(fremd)["titel"] == "B"
    assert speicher.aufgabe_zur_seite(999) is None


def test_aufgabe_loeschen_entfernt_zeilen_und_bilddateien(speicher, tmp_path):
    nr, andere = _aufgabe(speicher), _aufgabe(speicher)
    _fuenf_fotos(speicher, nr)
    seiten = speicher.ablage_zu_arbeiten(nr)
    speicher.bild_ablegen(nr, "rest.jpg", _bild())
    (bleibt,) = speicher.arbeit_anlegen(andere, [("a.jpg", _bild())])
    assert len(_bilddateien(speicher)) == 7

    speicher.aufgabe_loeschen(nr)

    assert speicher.aufgabe(nr) is None and speicher.aufgabe(andere) is not None
    assert speicher.arbeiten(nr) == [] and speicher.ablage(nr) == []
    assert speicher.seite(seiten[0]) is None
    assert _bilddateien(speicher) == [speicher.seite(bleibt)["bilddatei"]]
    db = sqlite3.connect(tmp_path / "daten" / "korrektor.db")
    try:
        for tabelle, zahl in (("aufgabe", 1), ("arbeit", 1), ("seite", 1), ("ablage", 0)):
            assert db.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0] == zahl, tabelle
    finally:
        db.close()


def test_aufgaben_zaehlt_arbeiten_und_seiten(speicher):
    nr = _aufgabe(speicher)
    _fuenf_fotos(speicher, nr)
    speicher.ablage_zu_arbeiten(nr)
    (aufgabe,) = speicher.aufgaben()
    assert aufgabe["arbeiten"] == 3 and aufgabe["seiten"] == 5
    assert aufgabe["seiten_fertig"] == 0 and aufgabe["offen"] == 0


# --- Status, Lauf und Zeichen ------------------------------------------------------------

def _zeichen(x=100, y=100, breite=80, hoehe=30, **felder):
    return {"kategorie": "R", "typ": "wort", "x": x, "y": y, "breite": breite, "hoehe": hoehe,
            "gelesen": "Fahrad", "vorschlag": "Fahrrad", "herkunft": "ki", "status": "offen",
            "rahmen_ki": [x, y, breite, hoehe], **felder}


def _seiten(speicher, zahl=1):
    nr = _aufgabe(speicher)
    return nr, speicher.arbeit_anlegen(nr, [(f"{i}.jpg", _bild()) for i in range(zahl)])


def _zeichen_der_seite(speicher, seite_id):
    arbeit = speicher.arbeit(speicher.seite(seite_id)["arbeit_id"])
    return next(s["zeichen"] for s in arbeit["seiten"] if s["id"] == seite_id)


def test_seite_lauf_beginnen_erhoeht_lauf_und_setzt_laeuft(speicher):
    _, (seite_id,) = _seiten(speicher)
    speicher.seite_status(seite_id, "fehlgeschlagen", fehlermeldung="Netz weg")
    assert speicher.seite_lauf_beginnen(seite_id) == 1
    seite = speicher.seite(seite_id)
    assert seite["lauf"] == 1 and seite["analyse_status"] == "laeuft"
    assert seite["fehlermeldung"] is None
    assert speicher.seite_lauf_beginnen(seite_id) == 2
    assert speicher.seite_lauf_beginnen(999) is None


def test_seite_status_setzt_status_und_felder(speicher):
    _, (seite_id,) = _seiten(speicher)
    assert speicher.seite_status(seite_id, "fertig", transkription="Das Fahrad", dauer_s=12.5,
                                 verworfen=2) is True
    seite = speicher.seite(seite_id)
    assert seite["analyse_status"] == "fertig" and seite["transkription"] == "Das Fahrad"
    assert seite["dauer_s"] == 12.5 and seite["verworfen"] == 2
    assert seite["analysiert_am"]
    speicher.seite_status(seite_id, "fehlgeschlagen", fehlermeldung="Zeitüberschreitung")
    seite = speicher.seite(seite_id)
    assert seite["analyse_status"] == "fehlgeschlagen"
    assert seite["fehlermeldung"] == "Zeitüberschreitung"
    assert seite["transkription"] == "Das Fahrad"  # nicht genannte Felder bleiben


def test_seite_status_lehnt_unbekanntes_ab(speicher):
    _, (seite_id,) = _seiten(speicher)
    with pytest.raises(ValueError):
        speicher.seite_status(seite_id, "kaputt")
    with pytest.raises(ValueError):
        speicher.seite_status(seite_id, "fertig", bilddatei="x.jpg")


def test_seite_status_mit_veraltetem_lauf_schreibt_nichts(speicher):
    _, (seite_id,) = _seiten(speicher)
    alt = speicher.seite_lauf_beginnen(seite_id)
    neu = speicher.seite_lauf_beginnen(seite_id)
    assert speicher.seite_status(seite_id, "fehlgeschlagen", fehlermeldung="spät", lauf=alt) is False
    assert speicher.seite(seite_id)["analyse_status"] == "laeuft"
    assert speicher.seite_status(seite_id, "fertig", lauf=neu) is True
    assert speicher.seite(seite_id)["analyse_status"] == "fertig"


def test_zeichen_ersetzen_mit_aktuellem_lauf_schreibt(speicher):
    _, (seite_id,) = _seiten(speicher)
    lauf = speicher.seite_lauf_beginnen(seite_id)
    luecke = _zeichen(300, 100, 10, 30, kategorie="Z", typ="luecke", gelesen="a b",
                      vorschlag="a, b")
    assert speicher.zeichen_ersetzen(seite_id, lauf, [_zeichen(), luecke]) is True
    erstes, zweites = _zeichen_der_seite(speicher, seite_id)
    assert erstes["seite_id"] == seite_id and erstes["id"] != zweites["id"]
    assert (erstes["kategorie"], erstes["typ"]) == ("R", "wort")
    assert (erstes["x"], erstes["y"], erstes["breite"], erstes["hoehe"]) == (100, 100, 80, 30)
    assert (erstes["gelesen"], erstes["vorschlag"]) == ("Fahrad", "Fahrrad")
    assert (erstes["herkunft"], erstes["status"]) == ("ki", "offen")
    assert erstes["bestaetigt_wie"] is None
    assert erstes["rahmen_ki"] == [100, 100, 80, 30]
    assert (zweites["kategorie"], zweites["typ"]) == ("Z", "luecke")


def test_zeichen_ersetzen_mit_veraltetem_lauf_schreibt_nichts(speicher):
    _, (seite_id,) = _seiten(speicher)
    alt = speicher.seite_lauf_beginnen(seite_id)
    neu = speicher.seite_lauf_beginnen(seite_id)
    assert speicher.zeichen_ersetzen(seite_id, neu, [_zeichen()]) is True
    assert speicher.zeichen_ersetzen(seite_id, alt, [_zeichen(500, 500), _zeichen(700, 700)]) is False
    (bleibt,) = _zeichen_der_seite(speicher, seite_id)
    assert bleibt["x"] == 100
    assert speicher.zeichen_ersetzen(999, 1, [_zeichen()]) is False


def test_zeichen_ersetzen_erhaelt_bestaetigte_verworfene_und_eigene(speicher):
    _, (seite_id,) = _seiten(speicher)
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [
        _zeichen(100, 100, gelesen="offen"),
        _zeichen(100, 200, gelesen="bestaetigt", status="bestaetigt", bestaetigt_wie="einzeln"),
        _zeichen(100, 300, gelesen="verworfen", status="verworfen"),
        _zeichen(100, 400, gelesen="hand", herkunft="hand", status="bestaetigt", kategorie="A",
                 rahmen_ki=None),
        _zeichen(100, 500, gelesen="hand offen", herkunft="hand"),
    ])
    lauf = speicher.seite_lauf_beginnen(seite_id)
    assert speicher.zeichen_ersetzen(seite_id, lauf, [_zeichen(600, 600, gelesen="neu")]) is True
    zeichen = {z["gelesen"]: z for z in _zeichen_der_seite(speicher, seite_id)}
    assert set(zeichen) == {"bestaetigt", "verworfen", "hand", "hand offen", "neu"}
    assert zeichen["bestaetigt"]["bestaetigt_wie"] == "einzeln"
    assert zeichen["hand"]["kategorie"] == "A" and zeichen["hand"]["rahmen_ki"] is None
    assert zeichen["neu"]["status"] == "offen"


def test_vorschlag_ueber_erhaltenem_rahmen_wird_nicht_angelegt(speicher):
    _, (seite_id,) = _seiten(speicher)
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [
        _zeichen(100, 100, 100, 40, gelesen="bestaetigt", status="bestaetigt"),
        _zeichen(100, 300, 100, 40, gelesen="verworfen", status="verworfen"),
        _zeichen(100, 500, 100, 40, gelesen="offen"),
    ])
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [
        _zeichen(110, 105, 100, 40, gelesen="fast deckungsgleich"),     # über „bestaetigt“
        _zeichen(120, 310, 40, 20, gelesen="liegt ganz im verworfenen"),
        _zeichen(150, 100, 100, 40, gelesen="genau die Hälfte"),        # nicht mehr als die Hälfte
        _zeichen(160, 300, 100, 40, gelesen="weniger als die Hälfte"),
        _zeichen(100, 500, 100, 40, gelesen="über dem alten offenen"),  # das alte ist ersetzt
        _zeichen(0, 0, 1000, 1000, gelesen="riesig"),  # umschließt erhaltene Rahmen ganz
        _zeichen(100, 100, 0, 40, gelesen="ohne Fläche"),  # Fläche 0 gilt nie als überdeckt
    ])
    assert {z["gelesen"] for z in _zeichen_der_seite(speicher, seite_id)} == {
        "bestaetigt", "verworfen", "genau die Hälfte", "weniger als die Hälfte",
        "über dem alten offenen", "ohne Fläche"}


def test_wortgruppe_ueber_bestaetigtem_wort_wird_nicht_angelegt(speicher):
    _, (seite_id,) = _seiten(speicher)
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [
        _zeichen(200, 100, 60, 40, gelesen="Wort", status="bestaetigt")])
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [
        _zeichen(100, 100, 300, 40, gelesen="Wortgruppe darüber")])
    assert [z["gelesen"] for z in _zeichen_der_seite(speicher, seite_id)] == ["Wort"]


def test_luecke_in_bestaetigter_wortgruppe_wird_angelegt(speicher):
    _, (seite_id,) = _seiten(speicher)
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [
        _zeichen(100, 100, 300, 40, gelesen="Wortgruppe", status="bestaetigt")])
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [
        _zeichen(200, 100, 8, 40, kategorie="Z", typ="luecke", gelesen="Komma fehlt"),
        _zeichen(210, 100, 8, 40, gelesen="schmales Wort")])  # gleicher Typ: entfällt
    assert {z["gelesen"] for z in _zeichen_der_seite(speicher, seite_id)} == {
        "Wortgruppe", "Komma fehlt"}


def test_neue_vorschlaege_duerfen_einander_ueberdecken(speicher):
    _, (seite_id,) = _seiten(speicher)
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [_zeichen(gelesen="a"), _zeichen(gelesen="b")])
    assert len(_zeichen_der_seite(speicher, seite_id)) == 2


def test_status_gesamt_mit_neuen_seiten():
    from webapp.speicher import status_gesamt
    assert status_gesamt(["neu", "neu"]) == "neu"
    assert status_gesamt([]) == "neu"
    assert status_gesamt(["fertig", "neu"]) == "laeuft"
    assert status_gesamt(["fertig", "fertig"]) == "fertig"
    assert status_gesamt(["neu", "fehlgeschlagen"]) == "fehlgeschlagen"
    assert status_gesamt(["neu", "wartet"]) == "laeuft"


def test_arbeiten_liefert_offen_und_status_gesamt(speicher):
    nr = _aufgabe(speicher)
    arbeit_id = {}
    seiten = {}
    for name in ("neu", "laeuft", "wartet", "fertig", "fehlgeschlagen", "teils_neu"):
        seiten[name] = speicher.arbeit_anlegen(nr, [("a.jpg", _bild()), ("b.jpg", _bild())])
        arbeit_id[name] = speicher.seite(seiten[name][0])["arbeit_id"]
    for seite_id in seiten["neu"]:
        speicher.seite_status(seite_id, "neu")
    speicher.seite_status(seiten["teils_neu"][0], "fertig")
    speicher.seite_status(seiten["teils_neu"][1], "neu")
    speicher.seite_status(seiten["laeuft"][0], "fertig")
    speicher.seite_lauf_beginnen(seiten["laeuft"][1])
    speicher.seite_status(seiten["wartet"][0], "wartet")
    speicher.seite_status(seiten["wartet"][1], "fertig")
    for seite_id in seiten["fertig"]:
        lauf = speicher.seite_lauf_beginnen(seite_id)
        speicher.zeichen_ersetzen(seite_id, lauf, [
            _zeichen(100, 100), _zeichen(100, 300),
            _zeichen(100, 500, status="bestaetigt"), _zeichen(100, 700, status="verworfen")])
        speicher.seite_status(seite_id, "fertig")
    speicher.seite_status(seiten["fehlgeschlagen"][0], "fehlgeschlagen", fehlermeldung="x")
    speicher.seite_status(seiten["fehlgeschlagen"][1], "laeuft")

    arbeiten = {a["id"]: a for a in speicher.arbeiten(nr)}
    for name in arbeit_id:
        # Eine Arbeit mit einer noch nicht analysierten Seite gilt nie als fertig.
        erwartet = "laeuft" if name in ("wartet", "teils_neu") else name
        assert arbeiten[arbeit_id[name]]["status_gesamt"] == erwartet, name
    assert arbeiten[arbeit_id["fertig"]]["offen"] == 4
    assert [s["offen"] for s in arbeiten[arbeit_id["fertig"]]["seiten"]] == [2, 2]
    assert arbeiten[arbeit_id["neu"]]["offen"] == 0

    (aufgabe,) = speicher.aufgaben()
    assert aufgabe["arbeiten"] == 6 and aufgabe["seiten"] == 12
    assert aufgabe["seiten_fertig"] == 5 and aufgabe["seiten_fehlgeschlagen"] == 1
    assert aufgabe["offen"] == 4 and aufgabe["bestaetigt"] == 0


def test_seiten_unfertig_liefert_wartende_und_laufende(speicher):
    _, seiten = _seiten(speicher, 5)
    speicher.seite_status(seiten[0], "neu")
    speicher.seite_status(seiten[1], "wartet")
    speicher.seite_lauf_beginnen(seiten[2])
    speicher.seite_status(seiten[3], "fertig")
    speicher.seite_status(seiten[4], "fehlgeschlagen", fehlermeldung="x")
    assert speicher.seiten_unfertig() == [seiten[1], seiten[2]]


def test_aufgabe_loeschen_entfernt_auch_zeichen(speicher, tmp_path):
    nr, (seite_id,) = _seiten(speicher)
    lauf = speicher.seite_lauf_beginnen(seite_id)
    speicher.zeichen_ersetzen(seite_id, lauf, [_zeichen()])
    speicher.aufgabe_loeschen(nr)
    db = sqlite3.connect(tmp_path / "daten" / "korrektor.db")
    try:
        assert db.execute("SELECT COUNT(*) FROM zeichen").fetchone()[0] == 0
    finally:
        db.close()


def test_gleichzeitiges_schreiben_aus_mehreren_threads(speicher):
    from concurrent.futures import ThreadPoolExecutor
    _, seiten = _seiten(speicher, 8)

    def schreiben(seite_id):
        lauf = speicher.seite_lauf_beginnen(seite_id)
        speicher.zeichen_ersetzen(seite_id, lauf, [_zeichen(), _zeichen(300, 300)])
        speicher.seite_status(seite_id, "fertig", lauf=lauf)

    with ThreadPoolExecutor(max_workers=8) as gleichzeitig:
        list(gleichzeitig.map(schreiben, seiten))
    assert speicher.seiten_unfertig() == []
    assert all(len(_zeichen_der_seite(speicher, s)) == 2 for s in seiten)
