"""Etappe 3: Routen für PDF-Ausgabe, Stapelübersicht und CSV; Knöpfe in Stapel und Korrektur."""
import re

import pytest
from werkzeug.http import parse_options_header

from webapp import routen, uebersicht
# Die Testhilfen und Vorrichtungen der Etappe 1 gelten unverändert.
from tests.webapp.test_routen import (  # noqa: F401
    _aufgabe, _bild, _daten, _mit_zeichen, _text, _zeichen, app, client, schein, schlange,
    speicher)

FEST = {"status": "bestaetigt", "bestaetigt_wie": "einzeln"}
BOM = b"\xef\xbb\xbf"


def _arbeit(speicher, aufgabe_id, *zeichen, seitenzahl=1, bestaetigen=True, kuerzel=None):
    """Eine fertig analysierte Arbeit (600 × 400) in der Aufgabe; gibt ihre id zurück."""
    seiten = speicher.arbeit_anlegen(aufgabe_id, [(f"{i}.jpg", _bild())
                                                  for i in range(seitenzahl)])
    for seite_id in seiten:
        _mit_zeichen(speicher, seite_id)
    for z in zeichen:
        speicher.zeichen_anlegen(seiten[0], z)
    arbeit_id = speicher.seite(seiten[0])["arbeit_id"]
    if kuerzel is not None:
        speicher.arbeit_kuerzel_setzen(arbeit_id, kuerzel)
    if bestaetigen:
        assert speicher.arbeit_bestaetigen(arbeit_id) is not None
    return arbeit_id


def _dateiname(antwort):
    art, angaben = parse_options_header(antwort.headers["Content-Disposition"])
    assert art == "attachment"
    return angaben["filename"]


def _seitenzahl(pdf):
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))


def _ist_fehlerseite(antwort, code):
    assert antwort.status_code == code
    assert antwort.mimetype == "text/html"
    text = _text(antwort)
    assert "Korrektor" in text and "Das hat nicht geklappt" in text
    return text


# --- PDF einer Arbeit -----------------------------------------------------------------------

def test_pdf_einer_bestaetigten_arbeit_als_download(client, speicher):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr, _zeichen(**FEST), seitenzahl=2)
    stand = speicher.arbeit(arbeit_id)["stand"]
    antwort = client.get(f"/arbeit/{arbeit_id}/pdf")
    assert antwort.status_code == 200
    assert antwort.mimetype == "application/pdf"
    assert antwort.headers["Cache-Control"] == "no-store"
    assert _dateiname(antwort) == "Arbeit-01.pdf"
    assert antwort.data.startswith(b"%PDF") and _seitenzahl(antwort.data) == 2
    # Die Ausgabe ändert nichts an der Arbeit.
    arbeit = speicher.arbeit(arbeit_id)
    assert arbeit["stand"] == stand and arbeit["bestaetigt_am"] is not None


@pytest.mark.parametrize("kuerzel, erwartet", [
    ("Ä 7/b", "Arbeit-Ä_7_b.pdf"),
    ('../x"y\\z', "Arbeit-x_y_z.pdf"),
    ("a.b;c\r\nd", "Arbeit-a_b_c_d.pdf"),
    ("Nr_3-b", "Arbeit-Nr_3-b.pdf"),
    ("…", "Arbeit.pdf"),
])
def test_dateiname_der_arbeit_wird_gesaeubert(client, speicher, kuerzel, erwartet):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr, kuerzel=kuerzel)
    antwort = client.get(f"/arbeit/{arbeit_id}/pdf")
    assert antwort.status_code == 200 and _dateiname(antwort) == erwartet
    kopf = antwort.headers["Content-Disposition"]
    assert "\r" not in kopf and "\n" not in kopf and "/" not in kopf and "\\" not in kopf


def test_pdf_einer_nicht_bestaetigten_arbeit_ergibt_409_mit_fehlerseite(client, speicher):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr, _zeichen(**FEST), bestaetigen=False)
    text = _ist_fehlerseite(client.get(f"/arbeit/{arbeit_id}/pdf"), 409)
    assert "nicht bestätigt" in text
    assert f'href="/arbeit/{arbeit_id}"' in text   # der Weg zurück zur Korrektur


def test_pdf_nach_verfallener_bestaetigung_ergibt_409(client, speicher):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr, _zeichen(**FEST))
    assert client.get(f"/arbeit/{arbeit_id}/pdf").status_code == 200
    seite_id = speicher.arbeit(arbeit_id)["seiten"][0]["id"]
    speicher.zeichen_anlegen(seite_id, _zeichen(x=300, **FEST))
    _ist_fehlerseite(client.get(f"/arbeit/{arbeit_id}/pdf"), 409)


@pytest.mark.parametrize("defekt", [False, True])
def test_pdf_mit_fehlendem_oder_defektem_foto_ergibt_500_mit_fehlerseite(client, speicher, defekt):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr)
    seite = speicher.arbeit(arbeit_id)["seiten"][0]
    pfad = speicher.bildpfad(seite["bilddatei"])
    if defekt:
        pfad.write_bytes(b"kein Bild")
    else:
        pfad.unlink()
    # Kein Zustand der Korrektur (409), sondern ein Fehler der Daten: 500 mit derselben Seite.
    text = _ist_fehlerseite(client.get(f"/arbeit/{arbeit_id}/pdf"), 500)
    assert "Foto" in text and f'href="/arbeit/{arbeit_id}"' in text
    text = _ist_fehlerseite(client.get(f"/aufgabe/{nr}/pdf"), 500)
    assert "Foto" in text and f'href="/aufgabe/{nr}"' in text


# --- Antwortköpfe der Downloads -------------------------------------------------------------

SCHWIERIG = ["Łukasz", "Erörterung 日本", "Größe Äöü ß", 'An"führung\'s"zeichen', "Zeile\r\numbruch",
             "日本語" * 1700, "Ł" * 5000, "a" * 5000, "ä-" * 2500]


def _koepfe_pruefen(antwort):
    """Jeder Kopf lässt sich als Latin-1 senden (sonst bricht der Server die Antwort ab)."""
    assert antwort.status_code == 200
    for name, wert in antwort.headers:
        (name + ": " + wert).encode("latin-1")
        assert "\r" not in wert and "\n" not in wert
    kopf = antwort.headers["Content-Disposition"]
    assert kopf.startswith("attachment") and len(kopf) < 1500
    return kopf


@pytest.mark.parametrize("name", SCHWIERIG)
def test_koepfe_der_downloads_sind_latin_1_und_kurz(client, speicher, name):
    nr = _aufgabe(speicher, titel=name)
    arbeit_id = _arbeit(speicher, nr, kuerzel=name.strip()[:20])   # länger darf keines sein
    for url in (f"/arbeit/{arbeit_id}/pdf", f"/aufgabe/{nr}/pdf", f"/aufgabe/{nr}/uebersicht.csv"):
        antwort = client.get(url)
        kopf = _koepfe_pruefen(antwort)
        assert antwort.headers["Cache-Control"] == "no-store"
        # Der Name bleibt lesbar: höchstens 60 Zeichen je Teil.
        assert len(_dateiname(antwort)) <= 2 * 60 + len("-Uebersicht.csv")
        assert "filename=" in kopf


def test_dateiname_mit_zeichen_ausserhalb_von_latin_1(client, speicher):
    nr = _aufgabe(speicher, titel="Erörterung 日本")
    arbeit_id = _arbeit(speicher, nr, kuerzel="Łukasz")
    antwort = client.get(f"/arbeit/{arbeit_id}/pdf")
    kopf = _koepfe_pruefen(antwort)
    # Ein Ersatz in ASCII und daneben der volle Name nach RFC 5987.
    assert "filename*=UTF-8''" in kopf and re.search(r'filename="?Arbeit-ukasz\.pdf"?', kopf)
    assert _dateiname(antwort) == "Arbeit-Łukasz.pdf"
    assert _dateiname(client.get(f"/aufgabe/{nr}/pdf")) == "Erörterung_日本-Sammel.pdf"


def test_namensteile_werden_auf_60_zeichen_gekuerzt(client, speicher):
    nr = _aufgabe(speicher, titel="T" * 200)
    _arbeit(speicher, nr)
    _arbeit(speicher, nr, bestaetigen=False)
    assert _dateiname(client.get(f"/aufgabe/{nr}/pdf")) == "T" * 60 + "-Sammel-1-von-2.pdf"
    assert _dateiname(client.get(f"/aufgabe/{nr}/uebersicht.csv")) == "T" * 60 + "-Uebersicht.csv"
    assert routen._dateiname("a" * 61, "_" + "b" * 70, "…", endung="pdf") == (
        "a" * 60 + "-" + "b" * 60 + ".pdf")


def test_koepfe_gehen_durch_den_echten_server(app, speicher):
    """Am Werkzeug-Server selbst: Die Antwort kommt an, auch mit Ł und CJK im Namen."""
    import http.client
    import threading

    from werkzeug.serving import make_server

    nr = _aufgabe(speicher, titel="Erörterung 日本")
    arbeit_id = _arbeit(speicher, nr, kuerzel="Łukasz")
    server = make_server("127.0.0.1", 0, app)
    faden = threading.Thread(target=server.serve_forever, daemon=True)
    faden.start()
    try:
        for url in (f"/arbeit/{arbeit_id}/pdf", f"/aufgabe/{nr}/pdf",
                    f"/aufgabe/{nr}/uebersicht.csv"):
            verbindung = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=20)
            verbindung.request("GET", url)
            antwort = verbindung.getresponse()
            daten = antwort.read()
            verbindung.close()
            assert antwort.status == 200 and daten
            assert "UTF-8''" in antwort.getheader("Content-Disposition")
    finally:
        server.shutdown()
        faden.join(timeout=5)
        server.server_close()


# --- Sammel-PDF -----------------------------------------------------------------------------

def test_sammel_pdf_enthaelt_die_bestaetigten_arbeiten(client, speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _zeichen(**FEST), seitenzahl=2)
    _arbeit(speicher, nr, seitenzahl=3, bestaetigen=False)
    _arbeit(speicher, nr)
    antwort = client.get(f"/aufgabe/{nr}/pdf")
    assert antwort.status_code == 200
    assert antwort.mimetype == "application/pdf"
    assert antwort.headers["Cache-Control"] == "no-store"
    # Eine Arbeit fehlt: Der Dateiname sagt es, der Titel im PDF nicht.
    assert _dateiname(antwort) == "Versuchsbeschreibung-Sammel-2-von-3.pdf"
    assert antwort.data.startswith(b"%PDF") and _seitenzahl(antwort.data) == 3
    assert b" von " not in antwort.data


def test_sammel_pdf_ohne_fehlende_arbeiten_heisst_nur_sammel(client, speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr)
    _arbeit(speicher, nr)
    assert _dateiname(client.get(f"/aufgabe/{nr}/pdf")) == "Versuchsbeschreibung-Sammel.pdf"


def test_dateiname_des_sammel_pdf_wird_gesaeubert(client, speicher):
    nr = _aufgabe(speicher, titel='Erörterung: "Schule" / 9b')
    _arbeit(speicher, nr)
    assert _dateiname(client.get(f"/aufgabe/{nr}/pdf")) == "Erörterung_Schule_9b-Sammel.pdf"


def test_sammel_pdf_ohne_bestaetigte_arbeit_ergibt_409_mit_fehlerseite(client, speicher):
    nr = _aufgabe(speicher)
    text = _ist_fehlerseite(client.get(f"/aufgabe/{nr}/pdf"), 409)
    assert "keine Korrektur bestätigt" in text and f'href="/aufgabe/{nr}"' in text
    _arbeit(speicher, nr, bestaetigen=False)
    _ist_fehlerseite(client.get(f"/aufgabe/{nr}/pdf"), 409)


# --- Unbekanntes und Schutz -----------------------------------------------------------------

PFADE = ["/arbeit/{arbeit}/pdf", "/aufgabe/{aufgabe}/pdf", "/aufgabe/{aufgabe}/uebersicht",
         "/aufgabe/{aufgabe}/uebersicht.csv"]


@pytest.mark.parametrize("pfad", PFADE)
def test_unbekanntes_ergibt_404(client, pfad):
    antwort = client.get(pfad.format(arbeit=999, aufgabe=999))
    assert antwort.status_code == 404 and "Korrektor" in _text(antwort)


@pytest.mark.parametrize("pfad", PFADE)
def test_fremder_host_wird_abgelehnt(client, speicher, pfad):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr)
    url = pfad.format(arbeit=arbeit_id, aufgabe=nr)
    assert client.get(url).status_code == 200
    for host in ("boese.example", "localhost.boese.example:5001", "192.168.0.7:5001"):
        antwort = client.get(url, headers={"Host": host})
        assert antwort.status_code == 403 and not antwort.data.startswith(b"%PDF")
        assert BOM not in antwort.data


@pytest.mark.parametrize("pfad", PFADE)
def test_fremde_herkunft_wird_abgelehnt_und_schreiben_ist_nicht_vorgesehen(client, speicher, pfad):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr)
    url = pfad.format(arbeit=arbeit_id, aufgabe=nr)
    assert client.post(url, headers={"Origin": "http://boese.example"}).status_code == 403
    assert client.post(url).status_code == 405


# --- Stapelübersicht ------------------------------------------------------------------------

def test_uebersichtsseite_zeigt_zahlen_und_nennt_die_bestaetigten(client, speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _zeichen("Fahrad", "Fahrrad", **FEST),
            _zeichen("fahrad", "Fahrrad", x=300, **FEST),
            _zeichen("dass er", "dass, er", kategorie="Z", typ="luecke", x=200, y=100,
                     breite=6, hoehe=20, **FEST), kuerzel="Anton")
    _arbeit(speicher, nr, _zeichen("Unbestätigt", "x", kategorie="Gr", **FEST),
            bestaetigen=False, kuerzel="Berta")
    antwort = client.get(f"/aufgabe/{nr}/uebersicht")
    text = _text(antwort)
    assert antwort.status_code == 200 and antwort.headers["Cache-Control"] == "no-store"
    assert "Stapelübersicht" in text and "1 von 2 Arbeiten bestätigt" in text
    assert "nur Arbeiten" in text and "bestätigt" in text      # Hinweis auf die Auswahl
    assert "Rechtschreibung" in text and "Zeichensetzung" in text
    assert "Grammatik" not in text and "Berta" not in text and "Unbestätigt" not in text
    assert "Fahrad" in text and "Fahrrad" in text and "Anton" in text
    assert f'href="/aufgabe/{nr}/uebersicht.csv"' in text and "Als CSV speichern" in text
    assert f'href="/aufgabe/{nr}"' in text
    # Keine Bewertung: weder Note noch Quotient noch Prozent.
    for wort in ("Note", "Quotient", "%", "Punkte", "Durchschnitt"):
        assert wort not in re.sub(r"<head>.*?</head>", "", text, flags=re.S)


def test_uebersichtsseite_zeigt_die_tabelle_in_stapelreihenfolge(client, speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, *[_zeichen(x=10 + 40 * i, **FEST) for i in range(5)], kuerzel="Zeta")
    _arbeit(speicher, nr, kuerzel="Alpha")
    _arbeit(speicher, nr, _zeichen(**FEST), kuerzel="Mitte")
    text = _text(client.get(f"/aufgabe/{nr}/uebersicht"))
    assert "3 von 3 Arbeiten bestätigt" in text
    assert text.index("Zeta") < text.index("Alpha") < text.index("Mitte")


def test_uebersichtsseite_ohne_bestaetigte_arbeit(client, speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _zeichen(**FEST), bestaetigen=False)
    antwort = client.get(f"/aufgabe/{nr}/uebersicht")
    text = _text(antwort)
    assert antwort.status_code == 200 and "0 von 1 Arbeiten bestätigt" in text
    assert "Noch ist keine Korrektur bestätigt" in text
    assert "uebersicht.csv" not in text


def test_uebersichtsseite_maskiert_texte(client, speicher):
    nr = _aufgabe(speicher, titel="Versuch <b>eins</b>")
    _arbeit(speicher, nr, _zeichen("<i>x</i>", "<u>y</u>", **FEST),
            _zeichen("<i>x</i>", "<u>y</u>", x=300, **FEST), kuerzel="<s>k</s>")
    text = _text(client.get(f"/aufgabe/{nr}/uebersicht"))
    for roh in ("<b>eins</b>", "<i>x</i>", "<u>y</u>", "<s>k</s>"):
        assert roh not in text
    assert "&lt;i&gt;x&lt;/i&gt;" in text and "&lt;s&gt;k&lt;/s&gt;" in text


def test_csv_download_mit_bom(client, speicher):
    nr = _aufgabe(speicher, titel="Erörterung 9b")
    _arbeit(speicher, nr, _zeichen(**FEST), kuerzel="Äpfel", seitenzahl=2)
    _arbeit(speicher, nr, _zeichen(**FEST), bestaetigen=False)
    _arbeit(speicher, nr, kuerzel="=1+1")
    antwort = client.get(f"/aufgabe/{nr}/uebersicht.csv")
    assert antwort.status_code == 200
    assert antwort.headers["Content-Type"] == "text/csv; charset=utf-8"   # genau ein charset
    assert antwort.headers["Cache-Control"] == "no-store"
    assert _dateiname(antwort) == "Erörterung_9b-Uebersicht.csv"
    assert antwort.data.startswith(BOM) and antwort.data.count(BOM) == 1
    inhalt = antwort.data[len(BOM):].decode("utf-8")
    assert inhalt == "Arbeit;Seiten;R;Summe\r\nÄpfel;2;1;1\r\n'=1+1;1;0;0\r\n"
    assert inhalt == uebersicht.als_csv(uebersicht.stapel(speicher, nr))


def test_csv_ohne_bestaetigte_arbeit_hat_nur_die_kopfzeile(client, speicher):
    nr = _aufgabe(speicher)
    antwort = client.get(f"/aufgabe/{nr}/uebersicht.csv")
    assert antwort.status_code == 200
    assert antwort.data == BOM + "Arbeit;Seiten;Summe\r\n".encode("utf-8")


# --- Knöpfe in der Korrekturansicht ---------------------------------------------------------

def _knopf(text, kennung):
    """Das öffnende Tag des Elements mit dieser id."""
    treffer = re.search(r'<a\b[^>]*\bid="' + kennung + r'"[^>]*>', text)
    assert treffer, kennung
    return treffer.group(0)


def test_korrekturansicht_hat_pdf_knopf_nur_aktiv_bei_bestaetigter_arbeit(client, speicher):
    nr = _aufgabe(speicher)
    arbeit_id = _arbeit(speicher, nr, _zeichen(**FEST), bestaetigen=False)
    text = _text(client.get(f"/arbeit/{arbeit_id}"))
    knopf = _knopf(text, "pdf-knopf")
    assert f'data-url="/arbeit/{arbeit_id}/pdf"' in knopf
    assert 'aria-disabled="true"' in knopf and " href=" not in knopf
    assert "PDF ausgeben" in text
    assert re.search(r'id="pdf-hinweis"(?![^>]*\bhidden)[^>]*>[^<]*bestätig', text)

    speicher.arbeit_bestaetigen(arbeit_id)
    text = _text(client.get(f"/arbeit/{arbeit_id}"))
    knopf = _knopf(text, "pdf-knopf")
    assert f'href="/arbeit/{arbeit_id}/pdf"' in knopf and "aria-disabled" not in knopf
    assert re.search(r'id="pdf-hinweis"[^>]*\bhidden', text)
    assert _daten(text, "arbeit-daten")["arbeit"]["bestaetigt_am"] is not None


# --- Knöpfe in der Stapelansicht ------------------------------------------------------------

def test_stapel_zeigt_sammel_pdf_uebersicht_und_pdf_je_bestaetigter_arbeit(client, speicher):
    nr = _aufgabe(speicher)
    fest = _arbeit(speicher, nr, _zeichen(**FEST))
    offen = _arbeit(speicher, nr, _zeichen(**FEST), bestaetigen=False)
    text = _text(client.get(f"/aufgabe/{nr}"))
    knopf = _knopf(text, "sammel-knopf")
    assert f'href="/aufgabe/{nr}/pdf"' in knopf and "aria-disabled" not in knopf
    assert re.search(r"Sammel-PDF\s*\(<span[^>]*>1 von 2 bestätigt</span>\)", text)
    assert f'href="/aufgabe/{nr}/uebersicht"' in text and "Stapelübersicht" in text
    assert f'href="/arbeit/{fest}/pdf"' in text
    assert f'href="/arbeit/{offen}/pdf"' not in text
    daten = _daten(text, "stapel-daten")
    assert daten["url_pdf"] == "/arbeit/0/pdf"


def test_stapel_sammel_pdf_ist_inaktiv_solange_nichts_bestaetigt_ist(client, speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _zeichen(**FEST), bestaetigen=False)
    text = _text(client.get(f"/aufgabe/{nr}"))
    knopf = _knopf(text, "sammel-knopf")
    assert f'data-url="/aufgabe/{nr}/pdf"' in knopf
    assert 'aria-disabled="true"' in knopf and " href=" not in knopf
    assert "0 von 1 bestätigt" in text
    assert not re.search(r'href="[^"]*/pdf"', text)   # auch kein Verweis je Arbeit


def test_stand_nennt_bestaetigung_fuer_die_knoepfe(client, speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr)
    _arbeit(speicher, nr, bestaetigen=False)
    stand = client.get(f"/aufgabe/{nr}/stand").get_json()
    assert (stand["gesamt"]["bestaetigt"], stand["gesamt"]["arbeiten"]) == (1, 2)
    assert [a["bestaetigt_am"] is not None for a in stand["arbeiten"]] == [True, False]
