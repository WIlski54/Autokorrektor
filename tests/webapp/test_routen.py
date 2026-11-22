import io
import json
import threading

import pytest
from PIL import Image

from webapp import app_erzeugen

EINST = {"modelle": {"gemini": "gemini-test", "gpt": "gpt-test", "claude": ""}}


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
    try:
        app.extensions["warteschlange"].analysieren(7)
    finally:
        app.extensions["warteschlange"].beenden()
    assert aufrufe == [(7, EINST)]


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
