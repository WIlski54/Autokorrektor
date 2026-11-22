import io

import pytest
from PIL import Image

import start
from webapp.speicher import Speicher
from webapp.sperre import sperre_belegen

TOML = 'max_kante = 2400\n\n[modelle]\ngemini = "gemini-test"\ngpt = ""\nclaude = ""\n'


@pytest.fixture
def wurzel(tmp_path, monkeypatch):
    """Ein leerer Projektordner; der echte Ordner und sein `daten/` bleiben unberührt."""
    monkeypatch.setattr(start, "WURZEL", tmp_path)
    for name in ("GEMINI_API_KEY", "GOOGLE_VISION_API_KEY", "OPENAI_API_KEY",
                 "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _bild():
    puffer = io.BytesIO()
    Image.new("RGB", (100, 60), "white").save(puffer, format="JPEG")
    return puffer.getvalue()


# --- Einzelinstanz-Sperre -----------------------------------------------------------------

def test_sperre_laesst_nur_einen_zu_und_wird_wieder_frei(tmp_path):
    ordner = tmp_path / "daten"  # wird bei Bedarf angelegt
    erste = sperre_belegen(ordner)
    assert erste is not None and ordner.is_dir()
    assert sperre_belegen(ordner) is None
    assert sperre_belegen(ordner) is None
    erste.close()
    zweite = sperre_belegen(ordner)
    assert zweite is not None
    zweite.close()


def test_sperre_gilt_je_datenordner(tmp_path):
    eine, andere = sperre_belegen(tmp_path / "a"), sperre_belegen(tmp_path / "b")
    try:
        assert eine is not None and andere is not None
    finally:
        eine.close()
        andere.close()


def test_zweite_instanz_endet_mit_meldung_und_oeffnet_den_browser(wurzel, monkeypatch, capsys):
    (wurzel / "einstellungen.toml").write_text(TOML, encoding="utf-8")
    geoeffnet = []
    monkeypatch.delenv("KORREKTOR_KEIN_BROWSER", raising=False)
    monkeypatch.setattr(start.webbrowser, "open", geoeffnet.append)
    monkeypatch.setattr(start, "app_bauen", lambda *a, **k: pytest.fail("darf nicht starten"))
    laufende = sperre_belegen(wurzel / "daten")
    try:
        start.main()
    finally:
        laufende.close()
    assert "Korrektor läuft bereits" in capsys.readouterr().out
    assert geoeffnet == ["http://127.0.0.1:5001/"]
    assert not (wurzel / "daten" / "korrektor.db").exists()  # nichts angefasst


def test_zweite_instanz_laesst_den_browser_auf_wunsch_zu(wurzel, monkeypatch, capsys):
    geoeffnet = []
    monkeypatch.setenv("KORREKTOR_KEIN_BROWSER", "1")
    monkeypatch.setattr(start.webbrowser, "open", geoeffnet.append)
    laufende = sperre_belegen(wurzel / "daten")
    try:
        start.main()
    finally:
        laufende.close()
    assert "Korrektor läuft bereits" in capsys.readouterr().out and geoeffnet == []


# --- Einstellungen ------------------------------------------------------------------------

def test_fehlende_einstellungen_enden_mit_klarer_meldung(wurzel):
    with pytest.raises(SystemExit) as ende:
        start.app_bauen(wurzel)
    meldung = str(ende.value)
    assert "einstellungen.toml" in meldung and "fehlt" in meldung and str(wurzel) in meldung
    assert not (wurzel / "daten").exists()


def test_unlesbare_einstellungen_enden_mit_klarer_meldung(wurzel):
    (wurzel / "einstellungen.toml").write_text("max_kante = = 3\n", encoding="utf-8")
    with pytest.raises(SystemExit) as ende:
        start.app_bauen(wurzel)
    assert "einstellungen.toml" in str(ende.value) and "nicht lesbar" in str(ende.value)


# --- Wiederaufnahme -----------------------------------------------------------------------

def test_start_nimmt_nur_seiten_ohne_hindernis_wieder_auf(wurzel, monkeypatch):
    (wurzel / "einstellungen.toml").write_text(TOML, encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "schein-schluessel")
    speicher = Speicher(wurzel / "daten")
    geht = speicher.aufgabe_anlegen("A", "Deutsch", 9, ["R"], "gemini")
    geht_nicht = speicher.aufgabe_anlegen("B", "Deutsch", 9, ["R"], "gpt")  # Schlüssel fehlt
    (s1,) = speicher.arbeit_anlegen(geht, [("a.jpg", _bild())])
    s2, s3 = speicher.arbeit_anlegen(geht_nicht, [("b.jpg", _bild()), ("c.jpg", _bild())])
    speicher.seite_lauf_beginnen(s3)  # lief beim Abbruch gerade
    aufrufe = []
    echt = start.app_erzeugen
    monkeypatch.setattr(start, "app_erzeugen", lambda ordner, einst: echt(
        ordner, einst, analysieren=lambda nr: aufrufe.append(nr) or {"zeichen": []}))

    app = start.app_bauen(wurzel)
    try:
        assert app.extensions["warteschlange"].warten(5) is True
    finally:
        app.extensions["warteschlange"].beenden()
    assert aufrufe == [s1] and speicher.seite(s1)["analyse_status"] == "fertig"
    for seite_id in (s2, s3):
        seite = speicher.seite(seite_id)
        assert seite["analyse_status"] == "fehlgeschlagen"
        assert "OPENAI_API_KEY" in seite["fehlermeldung"]
    assert speicher.seiten_unfertig() == []
