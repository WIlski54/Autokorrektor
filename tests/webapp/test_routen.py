import io
import json
import threading
import time

import pytest
from PIL import Image

from webapp import app_erzeugen

EINST = {"max_kante": 2400,
         "modelle": {"gemini": "gemini-test", "gpt": "gpt-test", "claude": ""}}


def _zeichen(gelesen="Fahrad", vorschlag="Fahrrad", **felder):
    return {"kategorie": "R", "typ": "wort", "x": 10, "y": 20, "breite": 30, "hoehe": 8,
            "gelesen": gelesen, "vorschlag": vorschlag, "herkunft": "ki", "status": "offen",
            "rahmen_ki": [10, 20, 30, 8], **felder}


class Schein:
    """Ersetzt die Analyse: merkt sich die Aufrufe und liefert ein einstellbares Ergebnis."""

    def __init__(self):
        self.aufrufe = []
        self.ergebnis = {"zeichen": [_zeichen()], "transkription": "Das Fahrad",
                         "dauer_s": 0.1, "verworfen": 0, "fehlermeldung": None}
        self.frei = threading.Event()
        self.frei.set()

    def __call__(self, seite_id):
        self.aufrufe.append(seite_id)
        self.frei.wait(5)
        return self.ergebnis


@pytest.fixture
def schein():
    return Schein()


@pytest.fixture
def app(tmp_path, schein, monkeypatch):
    for name in ("GEMINI_API_KEY", "GOOGLE_VISION_API_KEY", "OPENAI_API_KEY",
                 "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "schein-schluessel")
    app = app_erzeugen(tmp_path / "daten", EINST, analysieren=schein)
    app.config["TESTING"] = True
    yield app
    schein.frei.set()
    app.extensions["warteschlange"].beenden()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def speicher(app):
    return app.extensions["speicher"]


@pytest.fixture
def schlange(app):
    return app.extensions["warteschlange"]


def _bild(groesse=(600, 400), format="JPEG"):
    puffer = io.BytesIO()
    Image.new("RGB", groesse, "white").save(puffer, format=format)
    return puffer.getvalue()


def _aufgabe(speicher, **felder):
    werte = {"titel": "Versuchsbeschreibung", "fach": "Deutsch", "jahrgang": 9,
             "kategorien": ["R", "Z", "Gr"], "verfahren": "gemini", **felder}
    return speicher.aufgabe_anlegen(**werte)


def _formular(**felder):
    werte = {"titel": "Erörterung", "fach": "Deutsch", "jahrgang": "9",
             "kategorien": ["R", "Gr"], "verfahren": "gpt", **felder}
    return {name: wert for name, wert in werte.items() if wert is not None}


def _text(antwort):
    return antwort.get_data(as_text=True)


# --- Task 7: Gerüst, Aufgabenliste, Aufgabenformular -------------------------------------

def test_app_haengt_speicher_und_warteschlange_an(app):
    assert app.extensions["speicher"].aufgaben() == []
    assert app.extensions["warteschlange"].warten(1) is True
    assert app.config["MAX_CONTENT_LENGTH"] == 200 * 1024 * 1024


def test_voreingestellte_analyse_ruft_seite_analysieren(tmp_path, monkeypatch):
    import webapp
    aufrufe = []
    monkeypatch.setattr(webapp, "seite_analysieren",
                        lambda speicher, seite_id, einst: aufrufe.append((seite_id, einst)) or {})
    app = app_erzeugen(tmp_path / "daten", EINST)
    schlange = app.extensions["warteschlange"]
    try:
        vorher = time.monotonic()
        schlange.analysieren(7)
        nachher = time.monotonic()
    finally:
        schlange.beenden()
    ((seite_id, einst),) = aufrufe
    assert seite_id == 7 and {**einst, "frist": None} == {**EINST, "frist": None}
    # Nach der Zeitgrenze der Warteschlange beginnt das Verfahren keinen zweiten Versuch.
    assert schlange.zeitgrenze_s == 240
    assert vorher + 240 <= einst["frist"] <= nachher + 240
    assert "frist" not in EINST


def test_startseite_zeigt_prototyp_hinweis_und_aufgabe(client, speicher):
    _aufgabe(speicher, titel="Versuch <b>eins</b>")
    antwort = client.get("/")
    text = _text(antwort)
    assert antwort.status_code == 200
    assert "Prototyp" in text and "Auftragsverarbeitung" in text and "Genehmigung" in text
    assert "Versuch &lt;b&gt;eins&lt;/b&gt;" in text and "<b>eins</b>" not in text
    assert "Deutsch" in text


def test_startseite_ohne_aufgaben(client):
    antwort = client.get("/")
    assert antwort.status_code == 200 and "Neue Aufgabe" in _text(antwort)


def test_formular_neu_zeigt_verfahren_mit_voreinstellung(client):
    text = _text(client.get("/aufgabe/neu"))
    assert "Gemini Carbon (empfohlen)" in text
    assert "Gemini Carbon mit Cloud-Vision-Rahmen" in text
    assert 'value="gemini" selected' in text


def test_anlegen_leitet_zum_hochladen_und_speichert(client, speicher):
    antwort = client.post("/aufgabe/neu", data=_formular(vorschlag_in_ausgabe="1"))
    (aufgabe,) = speicher.aufgaben()
    assert antwort.status_code == 302
    assert antwort.headers["Location"].endswith(f"/aufgabe/{aufgabe['id']}/hochladen")
    assert aufgabe["titel"] == "Erörterung" and aufgabe["fach"] == "Deutsch"
    assert aufgabe["jahrgang"] == 9 and aufgabe["kategorien"] == ["R", "Gr"]
    assert aufgabe["verfahren"] == "gpt" and aufgabe["vorschlag_in_ausgabe"] is True


@pytest.mark.parametrize("felder, meldung", [
    ({"titel": "  "}, "Titel"),
    ({"kategorien": None}, "Kategorie"),
    ({"verfahren": "unbekannt"}, "Verfahren"),
    ({"jahrgang": "neun"}, "Jahrgang"),
    ({"kategorien": ["R", "X"]}, "Kategorie"),
])
def test_anlegen_mit_fehlenden_angaben_meldet_fehler(client, speicher, felder, meldung):
    antwort = client.post("/aufgabe/neu", data=_formular(**felder))
    assert antwort.status_code == 400
    assert meldung in _text(antwort) and 'class="meldung fehler"' in _text(antwort)
    assert speicher.aufgaben() == []


def test_fehlerhaftes_formular_behaelt_eingaben(client):
    text = _text(client.post("/aufgabe/neu", data=_formular(titel="", fach="Englisch")))
    assert 'value="Englisch"' in text and 'value="gpt" selected' in text


def test_bearbeiten_aendert_die_werte(client, speicher):
    nr = _aufgabe(speicher)
    text = _text(client.get(f"/aufgabe/{nr}/bearbeiten"))
    assert 'value="Versuchsbeschreibung"' in text
    antwort = client.post(f"/aufgabe/{nr}/bearbeiten",
                          data=_formular(titel="Neu", jahrgang="7", kategorien=["Z"]))
    assert antwort.status_code == 302
    aufgabe = speicher.aufgabe(nr)
    assert aufgabe["titel"] == "Neu" and aufgabe["jahrgang"] == 7
    assert aufgabe["kategorien"] == ["Z"] and aufgabe["verfahren"] == "gpt"
    assert aufgabe["vorschlag_in_ausgabe"] is False


def test_bearbeiten_weist_nach_beginn_der_analyse_auf_die_folgen_hin(client, speicher):
    nr = _aufgabe(speicher)
    assert "bereits analysierte Seiten" not in _text(client.get(f"/aufgabe/{nr}/bearbeiten"))
    speicher.arbeit_anlegen(nr, [("a.jpg", _bild())])
    assert "bereits analysierte Seiten" in _text(client.get(f"/aufgabe/{nr}/bearbeiten"))


def test_loeschen_entfernt_die_aufgabe(client, speicher):
    nr = _aufgabe(speicher)
    speicher.bild_ablegen(nr, "a.jpg", _bild())
    antwort = client.post(f"/aufgabe/{nr}/loeschen")
    assert antwort.status_code == 302 and antwort.headers["Location"].endswith("/")
    assert speicher.aufgabe(nr) is None and list(speicher.bilder.iterdir()) == []


def test_loeschen_nur_per_post(client, speicher):
    nr = _aufgabe(speicher)
    assert client.get(f"/aufgabe/{nr}/loeschen").status_code == 405
    assert speicher.aufgabe(nr) is not None


@pytest.mark.parametrize("pfad", ["/aufgabe/999/bearbeiten", "/aufgabe/999"])
def test_unbekannte_aufgabe_ergibt_404(client, pfad):
    antwort = client.get(pfad)
    assert antwort.status_code == 404 and "Korrektor" in _text(antwort)


def test_post_von_fremder_herkunft_wird_abgelehnt(client, speicher):
    nr = _aufgabe(speicher)
    antwort = client.post(f"/aufgabe/{nr}/loeschen", headers={"Origin": "http://boese.example"})
    assert antwort.status_code == 403 and speicher.aufgabe(nr) is not None
    antwort = client.post(f"/aufgabe/{nr}/loeschen", headers={"Origin": "http://localhost"})
    assert antwort.status_code == 302


def test_verfahren_zuordnung(monkeypatch):
    from webapp import verfahren
    for name in ("GEMINI_API_KEY", "GOOGLE_VISION_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert list(verfahren.VERFAHREN) == ["gemini", "gemini_vision", "gpt", "claude"]
    assert verfahren.VOREINSTELLUNG == "gemini"
    assert "GEMINI_API_KEY" in verfahren.hindernis("gemini", EINST)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert verfahren.hindernis("gemini", EINST) is None
    assert "GOOGLE_VISION_API_KEY" in verfahren.hindernis("gemini_vision", EINST)
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", " ")
    assert "GOOGLE_VISION_API_KEY" in verfahren.hindernis("gemini_vision", EINST)
    monkeypatch.setenv("GOOGLE_VISION_API_KEY", "y")
    assert verfahren.hindernis("gemini_vision", EINST) is None
    assert "einstellungen.toml" in verfahren.hindernis("gemini", {"modelle": {"gemini": ""}})
    assert "einstellungen.toml" in verfahren.hindernis("gemini", {})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "z")
    assert "einstellungen.toml" in verfahren.hindernis("claude", EINST)
    assert verfahren.hindernis("unbekannt", EINST)


@pytest.mark.parametrize("einst", [
    {"modelle": EINST["modelle"]}, {**EINST, "max_kante": 0}, {**EINST, "max_kante": "2400"}])
def test_hindernis_meldet_fehlendes_max_kante(monkeypatch, einst):
    from webapp import verfahren
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    grund = verfahren.hindernis("gemini", einst)
    assert "max_kante" in grund and "einstellungen.toml" in grund
    assert verfahren.hindernis("gemini", {**einst, "max_kante": 2400}) is None


# --- Task 8: Hochladen und Zuordnen -------------------------------------------------------

def _hochladen(client, nr, *dateien):
    return client.post(f"/aufgabe/{nr}/ablage", content_type="multipart/form-data",
                       data={"fotos": [(io.BytesIO(daten), name) for name, daten in dateien]})


def _ablage_fuellen(speicher, nr, zahl=3):
    return [speicher.bild_ablegen(nr, f"{i}.jpg", _bild()) for i in range(zahl)]


def test_hochladen_nimmt_bilder_an_und_nennt_abgelehnte(client, speicher):
    nr = _aufgabe(speicher)
    antwort = _hochladen(client, nr, ("a.jpg", _bild()), ("notiz.txt", b"kein Bild"),
                         ("b.png", _bild((300, 200), "PNG")))
    assert antwort.status_code == 200
    erg = antwort.get_json()
    ablage = speicher.ablage(nr)
    assert [e["dateiname"] for e in erg["angenommen"]] == ["a.jpg", "b.png"]
    assert [e["id"] for e in erg["angenommen"]] == [e["id"] for e in ablage]
    assert erg["angenommen"][1]["breite"] == 300 and erg["angenommen"][1]["hoehe"] == 200
    assert [e["dateiname"] for e in erg["abgelehnt"]] == ["notiz.txt"]
    assert erg["abgelehnt"][0]["grund"]


def test_hochladen_lehnt_zu_grosse_datei_mit_namen_ab(app, client, speicher):
    nr = _aufgabe(speicher)
    app.config["MAX_DATEI"] = 2000
    gross = _bild((2000, 1500))
    assert len(gross) > 2000
    erg = _hochladen(client, nr, ("riesig.jpg", gross), ("klein.jpg", _bild((20, 20)))).get_json()
    assert [e["dateiname"] for e in erg["angenommen"]] == ["klein.jpg"]
    assert erg["abgelehnt"][0]["dateiname"] == "riesig.jpg"
    assert "groß" in erg["abgelehnt"][0]["grund"]
    assert len(speicher.ablage(nr)) == 1


def test_hochladen_zu_unbekannter_aufgabe_ergibt_404(client):
    assert _hochladen(client, 999, ("a.jpg", _bild())).status_code == 404


def test_hochladen_ohne_dateien_ergibt_400(client, speicher):
    nr = _aufgabe(speicher)
    assert client.post(f"/aufgabe/{nr}/ablage", data={}).status_code == 400


def test_ordnen_speichert_reihenfolge_trennmarken_und_entfernt(client, speicher):
    nr = _aufgabe(speicher)
    a, b, c = _ablage_fuellen(speicher, nr)
    antwort = client.post(f"/aufgabe/{nr}/ablage/ordnen", json={"eintraege": [
        {"id": c, "neue_arbeit": True}, {"id": a, "neue_arbeit": False}], "entfernt": [b]})
    assert antwort.status_code == 200
    assert antwort.get_json() == {"ok": True, "fotos": 2, "arbeiten": 1}
    ablage = speicher.ablage(nr)
    assert [(e["id"], e["neue_arbeit"]) for e in ablage] == [(c, True), (a, False)]
    assert len(list(speicher.bilder.iterdir())) == 2


@pytest.mark.parametrize("inhalt", [
    {}, {"eintraege": "x"}, {"eintraege": [{"neue_arbeit": True}]}, {"eintraege": [{"id": "1"}]},
    {"eintraege": [3]}, [1, 2]])
def test_ordnen_lehnt_unbrauchbare_angaben_ab(client, speicher, inhalt):
    nr = _aufgabe(speicher)
    _ablage_fuellen(speicher, nr)
    assert client.post(f"/aufgabe/{nr}/ablage/ordnen", json=inhalt).status_code == 400
    assert len(speicher.ablage(nr)) == 3


def test_ordnen_lehnt_fremde_und_doppelte_eintraege_ab(client, speicher):
    nr, andere = _aufgabe(speicher), _aufgabe(speicher)
    (a, b) = _ablage_fuellen(speicher, nr, 2)
    (fremd,) = _ablage_fuellen(speicher, andere, 1)
    for eintraege in ([{"id": a}, {"id": fremd}], [{"id": a}, {"id": a}]):
        antwort = client.post(f"/aufgabe/{nr}/ablage/ordnen", json={"eintraege": eintraege})
        assert antwort.status_code == 400
    assert len(speicher.ablage(nr)) == 2 and len(speicher.ablage(andere)) == 1


def _groesse(antwort):
    with Image.open(io.BytesIO(antwort.data)) as img:
        return img.format, img.size


def test_bildrouten_liefern_jpeg_und_vorschaubild(client, speicher):
    nr = _aufgabe(speicher)
    ablage_id = speicher.bild_ablegen(nr, "a.jpg", _bild((600, 400)))
    (seite_id,) = speicher.arbeit_anlegen(nr, [("b.jpg", _bild((500, 700)))])
    for pfad, groesse, klein in ((f"/bild/ablage/{ablage_id}", (600, 400), (300, 200)),
                                 (f"/bild/seite/{seite_id}", (500, 700), (300, 420))):
        antwort = client.get(pfad)
        assert antwort.status_code == 200 and antwort.mimetype == "image/jpeg"
        assert _groesse(antwort) == ("JPEG", groesse)
        vorschau = client.get(pfad + "?b=300")
        assert vorschau.status_code == 200 and vorschau.mimetype == "image/jpeg"
        assert _groesse(vorschau) == ("JPEG", klein)
        assert vorschau.headers["ETag"] != antwort.headers["ETag"]
        erneut = client.get(pfad + "?b=300", headers={"If-None-Match": vorschau.headers["ETag"]})
        assert erneut.status_code == 304 and erneut.data == b""


@pytest.mark.parametrize("pfad", ["/bild/seite/999", "/bild/ablage/999", "/bild/ablage/999?b=300"])
def test_bildrouten_unbekannte_nummer_ergibt_404(client, pfad):
    assert client.get(pfad).status_code == 404


def test_bildroute_begrenzt_unsinnige_breite(client, speicher):
    nr = _aufgabe(speicher)
    ablage_id = speicher.bild_ablegen(nr, "a.jpg", _bild((600, 400)))
    assert _groesse(client.get(f"/bild/ablage/{ablage_id}?b=1"))[1] == (40, 27)
    assert _groesse(client.get(f"/bild/ablage/{ablage_id}?b=abc"))[1] == (600, 400)


def test_hochladeseite_zeigt_ablage_als_daten(client, speicher):
    nr = _aufgabe(speicher)
    a, b = _ablage_fuellen(speicher, nr, 2)
    speicher.ablage_ordnen(nr, [{"id": a, "neue_arbeit": True}, {"id": b, "neue_arbeit": False}])
    speicher.arbeit_anlegen(nr, [("x.jpg", _bild())])
    antwort = client.get(f"/aufgabe/{nr}/hochladen")
    text = _text(antwort)
    assert antwort.status_code == 200 and "Analyse starten" in text
    anfang = text.index('<script type="application/json" id="zuordnen-daten">')
    daten = json.loads(text[text.index(">", anfang) + 1:text.index("</script>", anfang)])
    assert [(e["id"], e["neue_arbeit"]) for e in daten["eintraege"]] == [(a, True), (b, False)]
    assert daten["naechste_nummer"] == 2 and daten["max_datei"] == 25 * 1024 * 1024


def test_hochladeseite_meldet_fehlenden_schluessel_vorab(client, speicher):
    nr = _aufgabe(speicher, verfahren="gpt")
    assert "OPENAI_API_KEY" in _text(client.get(f"/aufgabe/{nr}/hochladen"))


def test_analyse_starten_bildet_arbeiten_und_reiht_alle_seiten_ein(client, speicher, schlange,
                                                                    schein):
    nr = _aufgabe(speicher)
    a, b, c = _ablage_fuellen(speicher, nr)
    speicher.ablage_ordnen(nr, [{"id": a, "neue_arbeit": True}, {"id": b, "neue_arbeit": False},
                                {"id": c, "neue_arbeit": True}])
    antwort = client.post(f"/aufgabe/{nr}/analyse-starten")
    assert antwort.status_code == 302 and antwort.headers["Location"].endswith(f"/aufgabe/{nr}")
    assert schlange.warten(5) is True
    arbeiten = speicher.arbeiten(nr)
    assert [(ar["kuerzel"], len(ar["seiten"])) for ar in arbeiten] == [("01", 2), ("02", 1)]
    seiten = [s["id"] for ar in arbeiten for s in ar["seiten"]]
    assert sorted(schein.aufrufe) == sorted(seiten)
    assert {ar["status_gesamt"] for ar in arbeiten} == {"fertig"}
    assert speicher.ablage(nr) == []


@pytest.mark.parametrize("verfahren, schluessel, erwartet", [
    ("claude", None, "ANTHROPIC_API_KEY"),
    ("claude", "ANTHROPIC_API_KEY", "einstellungen.toml"),
    ("gemini_vision", None, "GOOGLE_VISION_API_KEY"),
])
def test_analyse_starten_ohne_schluessel_oder_modell_reiht_nichts_ein(
        client, speicher, schlange, schein, monkeypatch, verfahren, schluessel, erwartet):
    if schluessel:
        monkeypatch.setenv(schluessel, "vorhanden")
    nr = _aufgabe(speicher, verfahren=verfahren)
    _ablage_fuellen(speicher, nr)
    antwort = client.post(f"/aufgabe/{nr}/analyse-starten", follow_redirects=True)
    text = _text(antwort)
    assert antwort.status_code == 200 and antwort.request.path == f"/aufgabe/{nr}/hochladen"
    assert erwartet in text and 'class="meldung fehler"' in text
    assert schlange.warten(1) is True and schein.aufrufe == []
    assert speicher.arbeiten(nr) == [] and len(speicher.ablage(nr)) == 3


def test_analyse_starten_ohne_fotos_meldet_das(client, speicher, schein):
    nr = _aufgabe(speicher)
    antwort = client.post(f"/aufgabe/{nr}/analyse-starten", follow_redirects=True)
    assert antwort.request.path == f"/aufgabe/{nr}/hochladen"
    assert "keine Fotos" in _text(antwort) and schein.aufrufe == []


def _arbeit_hinzufuegen(client, nr, *dateien, **zusatz):
    return client.post(f"/aufgabe/{nr}/arbeit", content_type="multipart/form-data",
                       data={"fotos": [(io.BytesIO(daten), name) for name, daten in dateien]},
                       **zusatz)


def test_arbeit_hinzufuegen_legt_eine_arbeit_mit_zwei_seiten_an(client, speicher, schlange,
                                                                 schein):
    nr = _aufgabe(speicher)
    antwort = _arbeit_hinzufuegen(client, nr, ("1.jpg", _bild()), ("2.jpg", _bild()))
    assert antwort.status_code == 302 and antwort.headers["Location"].endswith(f"/aufgabe/{nr}")
    assert schlange.warten(5) is True
    (arbeit,) = speicher.arbeiten(nr)
    assert arbeit["kuerzel"] == "01" and [s["nummer"] for s in arbeit["seiten"]] == [1, 2]
    assert sorted(schein.aufrufe) == [s["id"] for s in arbeit["seiten"]]
    assert arbeit["status_gesamt"] == "fertig"


def test_arbeit_hinzufuegen_mit_unlesbarer_datei_legt_nichts_an(client, speicher, schein):
    nr = _aufgabe(speicher)
    antwort = _arbeit_hinzufuegen(client, nr, ("1.jpg", _bild()), ("<notiz>.txt", b"nichts"),
                                  follow_redirects=True)
    text = _text(antwort)
    assert "&lt;notiz&gt;.txt" in text and "<notiz>" not in text
    assert speicher.arbeiten(nr) == [] and schein.aufrufe == []
    assert list(speicher.bilder.iterdir()) == []


def test_arbeit_hinzufuegen_ohne_dateien_meldet_das(client, speicher):
    nr = _aufgabe(speicher)
    antwort = client.post(f"/aufgabe/{nr}/arbeit", data={}, follow_redirects=True)
    assert "kein Foto" in _text(antwort) and speicher.arbeiten(nr) == []


def test_arbeit_hinzufuegen_ohne_schluessel_legt_nichts_an(client, speicher, schein):
    nr = _aufgabe(speicher, verfahren="gpt")
    antwort = _arbeit_hinzufuegen(client, nr, ("1.jpg", _bild()), follow_redirects=True)
    assert "OPENAI_API_KEY" in _text(antwort)
    assert speicher.arbeiten(nr) == [] and schein.aufrufe == []


def test_arbeit_hinzufuegen_ordnet_seiten_nach_dateinamen(client, speicher, schlange):
    nr = _aufgabe(speicher)
    _arbeit_hinzufuegen(client, nr, ("Foto 10.jpg", _bild((100, 50))),
                        ("foto 9.jpg", _bild((90, 50))))
    schlange.warten(5)
    (arbeit,) = speicher.arbeiten(nr)
    assert [s["breite"] for s in arbeit["seiten"]] == [90, 100]


# --- Task 9: Stapelansicht ----------------------------------------------------------------

def _zwei_arbeiten(speicher):
    """Aufgabe mit Arbeit 01 (zwei Seiten) und Arbeit 02 (eine Seite); gibt (nr, seiten) zurück."""
    nr = _aufgabe(speicher)
    seiten = speicher.arbeit_anlegen(nr, [("1.jpg", _bild()), ("2.jpg", _bild())])
    seiten += speicher.arbeit_anlegen(nr, [("3.jpg", _bild())])
    for seite_id in seiten:  # wie Seiten, deren Analyse nie begonnen wurde
        speicher.seite_status(seite_id, "neu")
    return nr, seiten


def _daten(text, kennung):
    anfang = text.index(f'<script type="application/json" id="{kennung}">')
    return json.loads(text[text.index(">", anfang) + 1:text.index("</script>", anfang)])


def test_stand_liefert_arbeiten_mit_seiten(client, speicher, schlange, schein):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    schlange.einreihen(s1)
    assert schlange.warten(5) is True
    speicher.seite_status(s2, "fehlgeschlagen", fehlermeldung="Dienst nicht erreichbar")
    antwort = client.get(f"/aufgabe/{nr}/stand")
    assert antwort.status_code == 200
    stand = antwort.get_json()
    erste, zweite = stand["arbeiten"]
    assert erste["kuerzel"] == "01" and erste["seitenzahl"] == 2
    assert erste["status_gesamt"] == "fehlgeschlagen" and erste["offen"] == 1
    assert erste["seiten"] == [
        {"id": s1, "nummer": 1, "status": "fertig", "fehlermeldung": None},
        {"id": s2, "nummer": 2, "status": "fehlgeschlagen",
         "fehlermeldung": "Dienst nicht erreichbar"}]
    assert zweite["kuerzel"] == "02" and zweite["seitenzahl"] == 1
    assert zweite["status_gesamt"] == "neu" and zweite["offen"] == 0
    assert zweite["seiten"] == [{"id": s3, "nummer": 1, "status": "neu", "fehlermeldung": None}]
    assert stand["gesamt"] == {"seiten": 3, "fertig": 1, "fehlgeschlagen": 1, "unterwegs": 0,
                               "offen": 1}
    assert stand["aktiv"] is False


def test_stand_ist_aktiv_solange_etwas_wartet_oder_laeuft(client, speicher, schlange, schein):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    schein.frei.clear()
    schlange.einreihen(s3)
    stand = client.get(f"/aufgabe/{nr}/stand").get_json()
    assert stand["aktiv"] is True and stand["gesamt"]["unterwegs"] == 1
    assert stand["arbeiten"][1]["status_gesamt"] == "laeuft"
    schein.frei.set()
    assert schlange.warten(5) is True
    stand = client.get(f"/aufgabe/{nr}/stand").get_json()
    assert stand["aktiv"] is False and stand["arbeiten"][1]["status_gesamt"] == "fertig"


def test_stand_unbekannte_aufgabe_ergibt_404(client):
    assert client.get("/aufgabe/999/stand").status_code == 404


def test_erneut_reiht_fehlgeschlagene_seite_neu_ein(client, speicher, schlange, schein):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    speicher.seite_status(s1, "fehlgeschlagen", fehlermeldung="Zeitüberschreitung")
    antwort = client.post(f"/seite/{s1}/erneut")
    assert antwort.status_code == 200 and antwort.get_json() == {"ok": True}
    assert schlange.warten(5) is True
    assert schein.aufrufe == [s1]
    seite = speicher.seite(s1)
    assert seite["analyse_status"] == "fertig" and seite["fehlermeldung"] is None


def test_erneut_lehnt_fertige_und_unbekannte_seite_ab(client, speicher, schlange, schein):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    speicher.seite_status(s1, "fertig")
    antwort = client.post(f"/seite/{s1}/erneut")
    assert antwort.status_code == 409 and antwort.get_json()["fehler"]
    speicher.seite_status(s2, "wartet")
    assert client.post(f"/seite/{s2}/erneut").status_code == 409  # steht schon an
    assert client.post("/seite/999/erneut").status_code == 404
    assert schlange.warten(1) is True and schein.aufrufe == []
    assert speicher.seite(s1)["analyse_status"] == "fertig"


def test_erneut_ohne_schluessel_reiht_nichts_ein(client, speicher, schein, monkeypatch):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    speicher.seite_status(s1, "fehlgeschlagen", fehlermeldung="x")
    monkeypatch.delenv("GEMINI_API_KEY")
    antwort = client.post(f"/seite/{s1}/erneut")
    assert antwort.status_code == 409 and "GEMINI_API_KEY" in antwort.get_json()["fehler"]
    assert schein.aufrufe == [] and speicher.seite(s1)["analyse_status"] == "fehlgeschlagen"


def test_stapelansicht_zeigt_kacheln(client, speicher, schlange):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    schlange.einreihen(s3)
    assert schlange.warten(5) is True
    speicher.seite_status(s2, "fehlgeschlagen", fehlermeldung="Dienst <b>weg</b>")
    antwort = client.get(f"/aufgabe/{nr}")
    text = _text(antwort)
    assert antwort.status_code == 200
    arbeiten = speicher.arbeiten(nr)
    for arbeit in arbeiten:
        assert f'href="/arbeit/{arbeit["id"]}"' in text
    assert f'src="/bild/seite/{s1}?b=300"' in text and f'src="/bild/seite/{s3}?b=300"' in text
    assert "Arbeit 01" in text and "Arbeit 02" in text and "2 Seiten" in text
    assert "Dienst &lt;b&gt;weg&lt;/b&gt;" in text and "<b>weg</b>" not in text
    assert "Erneut versuchen" in text and f'data-seite="{s2}"' in text
    assert "1 offener Vorschlag" in text
    assert "Arbeit hinzufügen" in text and f'action="/aufgabe/{nr}/arbeit"' in text
    daten = _daten(text, "stapel-daten")
    assert daten["url_stand"] == f"/aufgabe/{nr}/stand" and daten["aktiv"] is False
    assert "1 von 3 Seiten analysiert" in text


def test_leere_stapelansicht_fuehrt_zum_hochladen(client, speicher):
    nr = _aufgabe(speicher)
    text = _text(client.get(f"/aufgabe/{nr}"))
    assert "Noch keine Arbeiten" in text and f'href="/aufgabe/{nr}/hochladen"' in text


def test_stapelansicht_weist_auf_fotos_in_der_ablage_hin(client, speicher):
    nr = _aufgabe(speicher)
    assert "noch nicht zugeordnet" not in _text(client.get(f"/aufgabe/{nr}"))
    _ablage_fuellen(speicher, nr, 2)
    assert "2 Fotos sind noch nicht zugeordnet" in _text(client.get(f"/aufgabe/{nr}"))


# --- Task 10: Arbeit ansehen --------------------------------------------------------------

def _mit_zeichen(speicher, seite_id, *zeichen):
    lauf = speicher.seite_lauf_beginnen(seite_id)
    assert speicher.zeichen_ersetzen(seite_id, lauf, list(zeichen)) is True
    speicher.seite_status(seite_id, "fertig", transkription="Text")


def test_arbeit_zeigt_seite_mit_zeichen_als_daten(client, speicher):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    _mit_zeichen(speicher, s1, _zeichen(),
                 _zeichen("dass er", "dass, er", kategorie="Z", typ="luecke",
                          x=200, y=100, breite=6, hoehe=20))
    erste, zweite = speicher.arbeiten(nr)
    antwort = client.get(f"/arbeit/{erste['id']}")
    text = _text(antwort)
    assert antwort.status_code == 200
    daten = _daten(text, "arbeit-daten")
    assert daten["seite"] == {"id": s1, "nummer": 1, "breite": 600, "hoehe": 400}
    wort, luecke = daten["zeichen"]
    assert wort["kategorie"] == "R" and wort["typ"] == "wort" and wort["status"] == "offen"
    assert (wort["x"], wort["y"], wort["breite"], wort["hoehe"]) == (10, 20, 30, 8)
    assert wort["gelesen"] == "Fahrad" and wort["vorschlag"] == "Fahrrad" and wort["id"]
    assert luecke["typ"] == "luecke" and luecke["kategorie"] == "Z"
    assert f'src="/bild/seite/{s1}"' in text
    assert "Seite 1 von 2" in text and "Etappe 2" not in text and "Nur Ansicht" not in text
    assert f'href="/arbeit/{erste["id"]}?seite=2"' in text
    assert f'href="/arbeit/{zweite["id"]}"' in text
    # Die Korrekturansicht zeichnet Rahmen und Liste im Browser aus den Daten.
    assert 'id="zeichenliste"' in text and 'id="rahmenebene"' in text
    assert 'id="verworfene-zeigen"' in text and 'id="meldung"' in text
    assert "/statisch/arbeit.js" in text
    for taste in ("<kbd>N</kbd>", "<kbd>B</kbd>", "<kbd>V</kbd>", "<kbd>Z</kbd>", "<kbd>Entf</kbd>"):
        assert taste in text  # die Belegung steht sichtbar in der Ansicht


def test_arbeit_blaettert_zur_zweiten_seite(client, speicher):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    _mit_zeichen(speicher, s2, _zeichen("nähmlich", "nämlich"))
    erste, zweite = speicher.arbeiten(nr)
    text = _text(client.get(f"/arbeit/{erste['id']}?seite=2"))
    daten = _daten(text, "arbeit-daten")
    assert daten["seite"]["id"] == s2 and [z["gelesen"] for z in daten["zeichen"]] == ["nähmlich"]
    assert "Seite 2 von 2" in text and f'href="/arbeit/{erste["id"]}?seite=1"' in text
    text = _text(client.get(f"/arbeit/{zweite['id']}"))
    assert "Seite 1 von 1" in text and f'href="/arbeit/{erste["id"]}"' in text


@pytest.mark.parametrize("pfad", ["/arbeit/999", "/arbeit/{id}?seite=3", "/arbeit/{id}?seite=0"])
def test_unbekannte_arbeit_oder_seite_ergibt_404(client, speicher, pfad):
    nr, _ = _zwei_arbeiten(speicher)
    assert client.get(pfad.format(id=speicher.arbeiten(nr)[0]["id"])).status_code == 404


def test_arbeit_maskiert_texte_des_modells(client, speicher):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    _mit_zeichen(speicher, s1, _zeichen("<script>alert(1)</script>", "a<b & \"c\"",
                                        kategorie="<i>R</i>"))
    speicher.seite_status(s2, "fehlgeschlagen", fehlermeldung="<img src=x onerror=alert(2)>")
    arbeit_id = speicher.arbeiten(nr)[0]["id"]
    text = _text(client.get(f"/arbeit/{arbeit_id}"))
    # Die Texte stehen nur in den eingebetteten Daten, dort unschädlich geschrieben; das
    # Skript setzt sie als Text ein.
    assert "<script>alert(1)</script>" not in text and "a<b" not in text and "<i>R</i>" not in text
    assert "</script>alert" not in text and r"\u003cscript\u003ealert(1)" in text
    (zeichen,) = _daten(text, "arbeit-daten")["zeichen"]
    assert zeichen["gelesen"] == "<script>alert(1)</script>" and zeichen["vorschlag"] == 'a<b & "c"'
    text = _text(client.get(f"/arbeit/{arbeit_id}?seite=2"))
    assert "<img src=x" not in text and "&lt;img src=x onerror=alert(2)&gt;" in text


def test_arbeit_zeigt_verworfene_zeichen_nicht(client, speicher):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    _mit_zeichen(speicher, s1, _zeichen(), _zeichen("wier", "wir", x=300, status="verworfen"))
    text = _text(client.get(f"/arbeit/{speicher.arbeiten(nr)[0]['id']}"))
    daten = _daten(text, "arbeit-daten")
    assert [z["gelesen"] for z in daten["zeichen"]] == ["Fahrad"]
    # Seit Etappe 2 stehen verworfene Zeichen in den Daten, aber in einem eigenen Feld;
    # die sichtbare Seite nennt sie nicht.
    assert [z["gelesen"] for z in daten["verworfen"]] == ["wier"]
    sichtbar = text[:text.index('<script type="application/json" id="arbeit-daten">')]
    assert "wier" not in sichtbar and "Fahrad" not in sichtbar  # beides nur in den Daten


def test_arbeit_ohne_analyse_nennt_den_stand(client, speicher):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    text = _text(client.get(f"/arbeit/{speicher.arbeiten(nr)[1]['id']}"))
    assert "noch nicht analysiert" in text and _daten(text, "arbeit-daten")["zeichen"] == []


# --- Befunde der Durchsicht ---------------------------------------------------------------

@pytest.mark.parametrize("host", ["boese.example", "boese.example:5001", "127.0.0.1.boese.example",
                                  "localhost.boese.example:5001", "192.168.0.7:5001", "[::1"])
def test_fremder_host_wird_abgelehnt(client, speicher, host):
    nr = _aufgabe(speicher)
    assert client.get("/", headers={"Host": host}).status_code == 403
    assert client.get("/statisch/app.css", headers={"Host": host}).status_code == 403
    antwort = client.post(f"/aufgabe/{nr}/loeschen", headers={"Host": host})
    assert antwort.status_code == 403 and speicher.aufgabe(nr) is not None


@pytest.mark.parametrize("host", ["localhost", "localhost:5001", "127.0.0.1", "127.0.0.1:5001",
                                  "LOCALHOST:5001"])
def test_eigener_host_wird_angenommen(client, host):
    assert client.get("/", headers={"Host": host}).status_code == 200
    assert client.get("/statisch/app.css", headers={"Host": host}).status_code == 200


def test_ordnen_ohne_entfernt_loescht_nichts(client, speicher):
    nr = _aufgabe(speicher)
    a, b, c = _ablage_fuellen(speicher, nr)
    antwort = client.post(f"/aufgabe/{nr}/ablage/ordnen", json={"eintraege": [
        {"id": c, "neue_arbeit": True}, {"id": a, "neue_arbeit": False}]})
    assert antwort.status_code == 200
    # b kam etwa aus einem anderen Fenster: es bleibt und steht hinten.
    assert antwort.get_json() == {"ok": True, "fotos": 3, "arbeiten": 2}
    assert [(e["id"], e["neue_arbeit"]) for e in speicher.ablage(nr)] == [
        (c, True), (a, False), (b, True)]
    assert len(list(speicher.bilder.iterdir())) == 3


def test_ordnen_duldet_schon_entfernte_und_lehnt_unbrauchbares_entfernt_ab(client, speicher):
    nr, andere = _aufgabe(speicher), _aufgabe(speicher)
    a, b = _ablage_fuellen(speicher, nr, 2)
    (fremd,) = _ablage_fuellen(speicher, andere, 1)
    url = f"/aufgabe/{nr}/ablage/ordnen"
    for entfernt in ("x", [str(b)], [None], [a]):  # a steht zugleich in den Einträgen
        antwort = client.post(url, json={"eintraege": [{"id": a}], "entfernt": entfernt})
        assert antwort.status_code == 400, entfernt
    assert len(speicher.ablage(nr)) == 2
    # Ein wiederholtes Speichern nennt b noch einmal; fremde Fotos bleiben unberührt.
    for _ in range(2):
        antwort = client.post(url, json={"eintraege": [{"id": a}], "entfernt": [b, fremd]})
        assert antwort.status_code == 200
        assert antwort.get_json() == {"ok": True, "fotos": 1, "arbeiten": 1}
    assert [e["id"] for e in speicher.ablage(nr)] == [a]
    assert [e["id"] for e in speicher.ablage(andere)] == [fremd]


def test_analyse_starten_legt_seiten_wartend_an(client, speicher, schlange, schein):
    nr = _aufgabe(speicher)
    _ablage_fuellen(speicher, nr, 2)
    schein.frei.clear()
    client.post(f"/aufgabe/{nr}/analyse-starten")
    status = {s["analyse_status"] for ar in speicher.arbeiten(nr) for s in ar["seiten"]}
    assert status <= {"wartet", "laeuft"}
    schein.frei.set()
    assert schlange.warten(5) is True


def test_zweites_analyse_starten_fuehrt_zur_stapelansicht(client, speicher, schlange, schein):
    nr = _aufgabe(speicher)
    _ablage_fuellen(speicher, nr, 2)
    client.post(f"/aufgabe/{nr}/analyse-starten")
    antwort = client.post(f"/aufgabe/{nr}/analyse-starten", follow_redirects=True)  # Doppelklick
    assert antwort.status_code == 200 and antwort.request.path == f"/aufgabe/{nr}"
    assert "keine Fotos" not in _text(antwort)
    assert schlange.warten(5) is True
    assert len(speicher.arbeiten(nr)) == 2 and len(schein.aufrufe) == 2


def test_erneut_reiht_auch_nie_begonnene_seite_ein(client, speicher, schlange, schein):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    assert speicher.seite(s3)["analyse_status"] == "neu"
    antwort = client.post(f"/seite/{s3}/erneut")
    assert antwort.status_code == 200 and antwort.get_json() == {"ok": True}
    assert schlange.warten(5) is True
    assert schein.aufrufe == [s3] and speicher.seite(s3)["analyse_status"] == "fertig"


def test_stapelansicht_bietet_fuer_nie_begonnene_seite_den_start_an(client, speicher, schlange):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    schlange.einreihen(s1)
    assert schlange.warten(5) is True
    text = _text(client.get(f"/aufgabe/{nr}"))
    assert f'data-seite="{s2}"' in text and f'data-seite="{s3}"' in text
    assert f'data-seite="{s1}"' not in text
    stand = client.get(f"/aufgabe/{nr}/stand").get_json()
    assert stand["arbeiten"][0]["status_gesamt"] == "laeuft"  # nicht „fertig“
    assert stand["arbeiten"][1]["status_gesamt"] == "neu" and stand["aktiv"] is False


def test_zwischenzeitlich_geloeschtes_ergibt_404_statt_500(client, speicher, monkeypatch):
    nr, (s1, s2, s3) = _zwei_arbeiten(speicher)
    speicher.seite_status(s1, "fehlgeschlagen", fehlermeldung="x")
    arbeit_id = speicher.arbeiten(nr)[0]["id"]
    with monkeypatch.context() as m:  # Aufgabe verschwindet nach dem Lesen der Seite/Arbeit
        m.setattr(speicher, "aufgabe", lambda id: None)
        m.setattr(speicher, "aufgabe_zur_seite", lambda id: None)
        assert client.post(f"/seite/{s1}/erneut").status_code == 404
        assert client.get(f"/arbeit/{arbeit_id}").status_code == 404
    with monkeypatch.context() as m:  # Arbeit fehlt schon in der Reihe der Aufgabe
        m.setattr(speicher, "arbeiten", lambda aufgabe_id: [])
        assert client.get(f"/arbeit/{arbeit_id}").status_code == 404


def test_hochladen_und_hinzufuegen_bei_geloeschter_aufgabe_ergeben_404(client, speicher,
                                                                      monkeypatch):
    nr = _aufgabe(speicher)
    echt = speicher.aufgabe
    aufrufe = []

    def einmal(id):  # die Route sieht die Aufgabe noch, danach ist sie gelöscht
        aufrufe.append(id)
        if len(aufrufe) == 1:
            aufgabe = echt(id)
            speicher.aufgabe_loeschen(id)
            return aufgabe
        return echt(id)

    monkeypatch.setattr(speicher, "aufgabe", einmal)
    assert _hochladen(client, nr, ("a.jpg", _bild())).status_code == 404
    nr = _aufgabe(speicher)
    aufrufe.clear()
    assert _arbeit_hinzufuegen(client, nr, ("a.jpg", _bild())).status_code == 404
    assert list(speicher.bilder.iterdir()) == []
