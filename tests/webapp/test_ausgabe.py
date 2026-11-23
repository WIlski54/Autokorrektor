"""Etappe 3: Seiten für die Ausgabe zeichnen und als PDF zusammenfassen."""
import gc
import io
import re
import threading
import time
import weakref

import pytest
from PIL import Image, JpegImagePlugin, PdfParser

from webapp import ausgabe
from webapp.regeln import RegelFehler
from webapp.speicher import Speicher

B, H = 600, 400
WEISS = (255, 255, 255)


def _bild(groesse=(B, H)):
    return Image.new("RGB", groesse, "white")


def _z(kategorie="R", x=100, y=100, breite=80, hoehe=20, typ="wort", status="bestaetigt",
       **felder):
    return {"kategorie": kategorie, "typ": typ, "x": x, "y": y, "breite": breite, "hoehe": hoehe,
            "gelesen": "Fahrad", "vorschlag": "Fahrrad", "herkunft": "ki", "status": status,
            "bestaetigt_wie": "einzeln" if status == "bestaetigt" else None, **felder}


def _bunt(pixel):
    """Ob ein Pixel eine Farbe trägt (Grau, Schwarz und Weiß gelten als unbunt)."""
    return max(pixel[:3]) - min(pixel[:3]) > 40


def _bunte(img, kasten=None):
    """Die Koordinaten aller bunten Pixel im Kasten (links, oben, rechts, unten)."""
    links, oben, rechts, unten = kasten or (0, 0, img.width, img.height)
    daten = img.load()
    return [(x, y) for y in range(max(0, oben), min(img.height, unten))
            for x in range(max(0, links), min(img.width, rechts)) if _bunt(daten[x, y])]


# --- Größe der Ausgabe ----------------------------------------------------------------------

def test_ausgabe_ist_um_die_randspalte_breiter():
    aus = ausgabe.seite_zeichnen(_bild(), [])
    assert aus.size == (B + round(B * 0.16), H)
    assert ausgabe.randbreite(B) == round(B * 0.16)


def test_randspalte_mit_richtiger_schreibung_ist_breiter():
    aus = ausgabe.seite_zeichnen(_bild(), [], vorschlag_zeigen=True)
    assert aus.size == (B + round(B * 0.28), H)
    assert ausgabe.randbreite(B, True) == round(B * 0.28)


def test_kopf_macht_die_seite_hoeher_und_schiebt_das_foto_nach_unten():
    foto = _bild()
    foto.putpixel((0, 0), (10, 200, 10))
    aus = ausgabe.seite_zeichnen(foto, [], kopf="Versuchsbeschreibung · Arbeit 03 · Seite 1 von 2")
    kopf = ausgabe.kopfhoehe(B)
    assert kopf > 0 and aus.size == (B + ausgabe.randbreite(B), H + kopf)
    assert aus.getpixel((0, kopf)) == (10, 200, 10)
    # Im Kopf steht dunkle Schrift, aber keine Farbe.
    dunkel = [1 for y in range(kopf) for x in range(aus.width) if max(aus.getpixel((x, y))) < 140]
    assert dunkel and not _bunte(aus, (0, 0, aus.width, kopf))


def test_eingabebild_bleibt_unveraendert():
    foto = _bild()
    vorher = foto.tobytes()
    aus = ausgabe.seite_zeichnen(foto, [_z(), _z("Z", typ="luecke", x=300, breite=8)],
                                 vorschlag_zeigen=True, kopf="Kopf",
                                 uebersicht=[{"kuerzel": "R", "bezeichnung": "Rechtschreibung",
                                              "anzahl": 1}])
    assert aus is not foto and foto.tobytes() == vorher and foto.size == (B, H)


def test_ausgabe_ist_ein_rgb_bild_auch_bei_anderem_eingabemodus():
    aus = ausgabe.seite_zeichnen(Image.new("L", (B, H), 255), [_z()])
    assert aus.mode == "RGB" and _bunte(aus)


# --- Zeichen im Text ------------------------------------------------------------------------

@pytest.mark.parametrize("kategorie", ["R", "Z", "Gr", "A"])
def test_bestaetigtes_wort_bekommt_strich_in_der_farbe_der_kategorie(kategorie):
    z = _z(kategorie)
    aus = ausgabe.seite_zeichnen(_bild(), [z])
    farbe = ausgabe.farbe(kategorie)
    unterkante = z["y"] + z["hoehe"]
    # Knapp unter dem Rahmen liegt eine Zeile, die über die ganze Breite die Farbe trägt.
    zeilen = [y for y in range(unterkante, unterkante + 12)
              if all(aus.getpixel((x, y)) == farbe for x in range(z["x"], z["x"] + z["breite"]))]
    assert zeilen and len(zeilen) == ausgabe.strichstaerke(B)
    # Der Strich reicht nicht über die Breite des Rahmens hinaus, im Rahmen selbst steht nichts.
    assert aus.getpixel((z["x"] - 3, zeilen[0])) == WEISS
    assert aus.getpixel((z["x"] + z["breite"] + 3, zeilen[0])) == WEISS
    assert not _bunte(aus, (z["x"], z["y"], z["x"] + z["breite"], unterkante))


def test_farben_der_kategorien():
    assert ausgabe.farbe("R") == (198, 40, 40)
    assert ausgabe.farbe("Z") == (21, 101, 192)
    assert ausgabe.farbe("Gr") == (123, 31, 162)
    assert ausgabe.farbe("A") == ausgabe.farbe("Sb") == (0, 121, 107)


def test_strichstaerke_haengt_an_der_bildbreite():
    assert ausgabe.strichstaerke(400) == 2
    assert ausgabe.strichstaerke(2400) == 6


@pytest.mark.parametrize("status", ["offen", "verworfen"])
def test_offene_und_verworfene_zeichen_hinterlassen_keine_farbe(status):
    zeichen = [_z(status=status), _z("Z", typ="luecke", x=300, breite=8, status=status)]
    aus = ausgabe.seite_zeichnen(_bild(), zeichen, vorschlag_zeigen=True)
    assert not _bunte(aus)


def test_luecke_zeichnet_ein_einfuegezeichen_im_bereich_der_luecke():
    z = _z("Z", typ="luecke", x=300, y=100, breite=8, hoehe=24)
    aus = ausgabe.seite_zeichnen(_bild(), [z])
    bunt = _bunte(aus, (0, 0, B, H))
    assert bunt
    xs, ys = [p[0] for p in bunt], [p[1] for p in bunt]
    mitte = z["x"] + z["breite"] / 2
    # Das Zeichen sitzt mittig an der Unterkante der Lücke und bleibt in ihrer Nähe.
    assert min(xs) < mitte < max(xs) and abs((min(xs) + max(xs)) / 2 - mitte) <= 2
    assert min(xs) >= z["x"] - 20 and max(xs) <= z["x"] + z["breite"] + 20
    assert z["y"] + z["hoehe"] / 2 <= min(ys) and max(ys) <= z["y"] + z["hoehe"] + 12
    assert all(aus.getpixel(p) == ausgabe.farbe("Z") or _bunt(aus.getpixel(p)) for p in bunt)
    # Nach oben offen: oben liegen die Enden weiter auseinander als unten.
    oben = [x for x, y in bunt if y == min(ys)]
    unten = [x for x, y in bunt if y == max(ys)]
    assert max(oben) - min(oben) > max(unten) - min(unten)


def test_zeichen_am_bildrand_bleiben_im_bild():
    zeichen = [_z(x=B - 40, y=H - 10, breite=40, hoehe=10),
               _z("Z", typ="luecke", x=0, y=H - 20, breite=6, hoehe=20)]
    aus = ausgabe.seite_zeichnen(_bild(), zeichen)
    assert aus.size == (B + ausgabe.randbreite(B), H)
    assert _bunte(aus, (B - 40, H - 10, B, H)) and _bunte(aus, (0, H - 20, 30, H))


# --- Randzeilen -----------------------------------------------------------------------------

def test_randzeilen_gruppiert_zeichen_derselben_textzeile_von_links_nach_rechts():
    rechts, links = _z(x=400, y=104), _z("Z", x=50, y=100)
    assert ausgabe.randzeilen([rechts, links]) == [[links, rechts]]


def test_randzeilen_ordnet_verschiedene_zeilen_von_oben_nach_unten():
    unten, oben, mitte = _z(x=10, y=300), _z(x=500, y=40), _z(x=200, y=170)
    assert ausgabe.randzeilen([unten, oben, mitte]) == [[oben], [mitte], [unten]]


def test_randzeilen_trennt_bei_geringer_ueberlappung():
    # Die senkrechten Bereiche überlappen sich um 8 von 20 Pixeln: weniger als die Hälfte.
    a, b = _z(x=10, y=100, hoehe=20), _z(x=200, y=112, hoehe=20)
    assert ausgabe.randzeilen([a, b]) == [[a], [b]]
    # 12 von 20 Pixeln: mehr als die Hälfte der kleineren Höhe.
    c = _z(x=200, y=108, hoehe=20)
    assert ausgabe.randzeilen([c, a]) == [[a, c]]


def test_randzeilen_misst_an_der_kleineren_hoehe():
    # Eine schmale, hohe Lücke und ein flaches Wort auf derselben Zeile.
    wort = _z(x=10, y=110, hoehe=10)
    luecke = _z("Z", typ="luecke", x=200, y=95, breite=6, hoehe=30)
    assert ausgabe.randzeilen([luecke, wort]) == [[wort, luecke]]


def test_randzeilen_ohne_zeichen():
    assert ausgabe.randzeilen([]) == []


# --- Randspalte -----------------------------------------------------------------------------

def test_randspalte_traegt_farbe_auf_hoehe_der_textzeile():
    z = _z("Gr", x=100, y=200, hoehe=20)
    aus = ausgabe.seite_zeichnen(_bild(), [z])
    bunt = _bunte(aus, (B, 0, aus.width, H))
    assert bunt
    ys = [p[1] for p in bunt]
    mitte = z["y"] + z["hoehe"] / 2
    assert min(ys) >= mitte - 20 and max(ys) <= mitte + 20
    # Das Kürzel steht in der Farbe seiner Kategorie.
    assert any(aus.getpixel(p) == ausgabe.farbe("Gr") for p in bunt)
    # Abstand zur Trennlinie und zum rechten Rand.
    assert min(p[0] for p in bunt) > B + 2 and max(p[0] for p in bunt) < aus.width - 2


def test_randspalte_fuehrt_kuerzel_einer_zeile_nebeneinander_in_lesereihenfolge():
    zeichen = [_z("Z", x=400, y=100), _z("R", x=50, y=100)]
    aus = ausgabe.seite_zeichnen(_bild(), zeichen)

    def spalten(farbe):
        return [x for x in range(B, aus.width) for y in range(80, 140)
                if aus.getpixel((x, y)) == farbe]

    rot, blau = spalten(ausgabe.farbe("R")), spalten(ausgabe.farbe("Z"))
    assert rot and blau and max(rot) < min(blau)


def test_randspalte_hat_weissen_grund_und_trennlinie():
    aus = ausgabe.seite_zeichnen(Image.new("RGB", (B, H), (20, 20, 20)), [])
    assert aus.getpixel((aus.width - 3, H // 2)) == WEISS
    linie = aus.getpixel((B, H // 2))
    assert linie != WEISS and linie != (20, 20, 20) and not _bunt(linie)


def test_viele_zeichen_in_einer_zeile_brechen_um_und_bleiben_in_der_spalte():
    zeichen = [_z("Gr", x=10 + 45 * i, y=100, breite=40) for i in range(12)]
    aus = ausgabe.seite_zeichnen(_bild(), zeichen)
    bunt = _bunte(aus, (B, 0, aus.width, aus.height))
    assert max(p[0] for p in bunt) < aus.width - 2
    # Zwölf Kürzel passen nicht in eine Zeile der Spalte: Sie belegen mehrere Zeilen.
    hoehe_einer_zeile = len({p[1] for p in _bunte(
        ausgabe.seite_zeichnen(_bild(), zeichen[:1]), (B, 0, aus.width, H))})
    assert len({p[1] for p in bunt}) > 2 * hoehe_einer_zeile


def test_umbrochene_zeile_schiebt_die_naechste_nach_unten():
    oben = [_z("R", x=10 + 45 * i, y=100, breite=40) for i in range(12)]
    unten = _z("Z", x=10, y=125)
    aus = ausgabe.seite_zeichnen(_bild(), oben + [unten])
    rot = [p for p in _bunte(aus, (B, 0, aus.width, aus.height))
           if aus.getpixel(p) == ausgabe.farbe("R")]
    blau = [p for p in _bunte(aus, (B, 0, aus.width, aus.height))
            if aus.getpixel(p) == ausgabe.farbe("Z")]
    assert rot and blau and max(p[1] for p in rot) < min(p[1] for p in blau)


def test_volle_randspalte_laesst_nichts_ueber_den_rand_ragen():
    # Mehr Zeilen, als neben dem Foto Platz haben: Die Seite wächst nach unten.
    zeichen = [_z("R", x=10 + 45 * (i % 12), y=10 + 30 * (i // 12), breite=40)
               for i in range(12 * 12)]
    aus = ausgabe.seite_zeichnen(_bild(), zeichen)
    assert aus.height > H
    bunt = _bunte(aus, (B, 0, aus.width, aus.height))
    assert min(p[1] for p in bunt) >= 1 and max(p[1] for p in bunt) < aus.height - 2


def test_vorschlag_steht_neben_dem_kuerzel_nur_wenn_eingeschaltet():
    z = _z(vorschlag="Fahrrad")
    ohne = ausgabe.seite_zeichnen(_bild(), [z])
    mit = ausgabe.seite_zeichnen(_bild(), [z], vorschlag_zeigen=True)

    def grau(img):
        return [(x, y) for y in range(H) for x in range(B + 2, img.width)
                if max(img.getpixel((x, y))) < 150 and not _bunt(img.getpixel((x, y)))]

    assert not grau(ohne)
    dunkel = grau(mit)
    assert dunkel
    bunt = _bunte(mit, (B, 0, mit.width, H))
    # Der Vorschlag steht rechts vom Kürzel, in Grau, auf derselben Höhe.
    assert min(p[0] for p in dunkel) > max(p[0] for p in bunt)
    assert abs(sum(p[1] for p in dunkel) / len(dunkel) - sum(p[1] for p in bunt) / len(bunt)) < 12


def test_langer_vorschlag_wird_gekuerzt_und_bleibt_in_der_spalte():
    z = _z(vorschlag="Donaudampfschifffahrtsgesellschaftskapitänsmützenabzeichen " * 3)
    aus = ausgabe.seite_zeichnen(_bild(), [z], vorschlag_zeigen=True)
    belegt = [x for y in range(H) for x in range(B + 2, aus.width)
              if aus.getpixel((x, y)) != WEISS]
    assert belegt and max(belegt) < aus.width - 2
    assert len({y for y in range(H) for x in range(B + 2, aus.width)
                if aus.getpixel((x, y)) != WEISS}) < 40   # eine Zeile, kein Umbruch


def test_kuerzen_haengt_auslassungspunkte_an():
    schrift = ausgabe.schrift(20)
    assert ausgabe.kuerzen("kurz", schrift, 1000) == "kurz"
    gekuerzt = ausgabe.kuerzen("ein sehr langer Vorschlag für die Randspalte", schrift, 120)
    assert gekuerzt.endswith("…") and len(gekuerzt) < 40
    assert schrift.getlength(gekuerzt) <= 120
    assert ausgabe.kuerzen("egal", schrift, 0) == ""


# --- Fehlerübersicht ------------------------------------------------------------------------

UEBERSICHT = [{"kuerzel": "R", "bezeichnung": "Rechtschreibung", "anzahl": 5},
              {"kuerzel": "Gr", "bezeichnung": "Grammatik", "anzahl": 1},
              {"kuerzel": "A", "bezeichnung": "Ausdruck", "anzahl": 2}]


def test_uebersicht_macht_die_seite_um_den_kasten_hoeher():
    ohne = ausgabe.seite_zeichnen(_bild(), [_z()])
    mit = ausgabe.seite_zeichnen(_bild(), [_z()], uebersicht=UEBERSICHT)
    assert mit.width == ohne.width and mit.height > ohne.height
    # Der Kasten liegt unter dem Foto und nennt die Kürzel in ihrer Farbe.
    bunt = _bunte(mit, (0, H, mit.width, mit.height))
    farben = {mit.getpixel(p) for p in bunt}
    assert {ausgabe.farbe("R"), ausgabe.farbe("Gr"), ausgabe.farbe("A")} <= farben
    assert ausgabe.farbe("Z") not in farben
    assert max(p[0] for p in bunt) < mit.width - 2 and max(p[1] for p in bunt) < mit.height - 2


def test_leere_uebersicht_zeichnet_trotzdem_einen_kasten():
    ohne = ausgabe.seite_zeichnen(_bild(), [])
    mit = ausgabe.seite_zeichnen(_bild(), [], uebersicht=[])
    assert mit.height > ohne.height and not _bunte(mit)


def test_lange_uebersicht_bricht_um():
    viele = [{"kuerzel": f"K{i}", "bezeichnung": "Bezeichnung mit vierzig Zeichen Länge ....",
              "anzahl": i + 1} for i in range(12)]
    kurz = ausgabe.seite_zeichnen(_bild(), [], uebersicht=UEBERSICHT)
    lang = ausgabe.seite_zeichnen(_bild(), [], uebersicht=viele)
    assert lang.height > kurz.height
    belegt = [x for y in range(H, lang.height) for x in range(lang.width)
              if _bunt(lang.getpixel((x, y)))]
    assert max(belegt) < lang.width - 2


# --- Schrift --------------------------------------------------------------------------------

def test_text_mit_umlauten_und_eszett_loest_keinen_fehler_aus():
    z = _z("Ü", vorschlag="Größe, Äpfel, Öl – „Maß“")
    aus = ausgabe.seite_zeichnen(
        _bild(), [z], vorschlag_zeigen=True, kopf="Erörterung über Fußgänger · Arbeit Ä7",
        uebersicht=[{"kuerzel": "Ü", "bezeichnung": "Übung macht den Meißter", "anzahl": 1}])
    assert _bunte(aus)


def test_ohne_systemschrift_wird_die_standardschrift_genommen(monkeypatch):
    monkeypatch.setattr(ausgabe, "SCHRIFTEN", ("gibt-es-nicht.ttf",))
    monkeypatch.setattr(ausgabe, "SCHRIFTEN_FETT", ("gibt-es-auch-nicht.ttf",))
    ausgabe.schrift.cache_clear()
    try:
        aus = ausgabe.seite_zeichnen(_bild(), [_z(vorschlag="Größe")], vorschlag_zeigen=True,
                                     kopf="Kopf mit Ümlaut", uebersicht=UEBERSICHT)
        assert _bunte(aus, (B, 0, aus.width, H))
        assert max(p[0] for p in _bunte(aus)) < aus.width - 2
    finally:
        ausgabe.schrift.cache_clear()


# --- PDF je Arbeit und Sammel-PDF -----------------------------------------------------------

@pytest.fixture
def speicher(tmp_path):
    return Speicher(tmp_path / "daten")


def _jpeg(groesse=(B, H)):
    puffer = io.BytesIO()
    Image.new("RGB", groesse, "white").save(puffer, format="JPEG")
    return puffer.getvalue()


def _aufgabe(speicher, **felder):
    werte = {"titel": "Versuchsbeschreibung", "fach": "Deutsch", "jahrgang": 9,
             "kategorien": ["R", "Z", "Gr"], "verfahren": "gemini", **felder}
    return speicher.aufgabe_anlegen(**werte)


def _arbeit(speicher, aufgabe_id, *zeichen, seitenzahl=1, groesse=(B, H), bestaetigen=True):
    """Eine fertig analysierte Arbeit; die Zeichen stehen auf der ersten Seite.

    Gibt (arbeit_id, seiten_ids) zurück.
    """
    seiten = speicher.arbeit_anlegen(aufgabe_id, [(f"{i}.jpg", _jpeg(groesse))
                                                  for i in range(seitenzahl)])
    for seite_id in seiten:
        lauf = speicher.seite_lauf_beginnen(seite_id)
        assert speicher.zeichen_ersetzen(seite_id, lauf, []) is True
        speicher.seite_status(seite_id, "fertig", transkription="Text")
    for z in zeichen:
        speicher.zeichen_anlegen(seiten[0], z)
    arbeit_id = speicher.seite(seiten[0])["arbeit_id"]
    if bestaetigen:
        assert speicher.arbeit_bestaetigen(arbeit_id) is not None
    return arbeit_id, seiten


def _seitenzahl(pdf):
    """Die Zahl der Seiten im gültigen Seitenbaum, wie ein Leseprogramm sie sieht.

    Die Seiten werden einzeln angehängt; ältere Stände des Seitenbaums bleiben in der Datei
    stehen und zählen nicht.
    """
    with PdfParser.PdfParser(f=io.BytesIO(pdf), mode="rb") as leser:
        return len(leser.pages)


def _bildmasse(pdf):
    """Die Größen der eingebetteten Bilder als [(breite, hoehe)]."""
    breiten = [int(n) for n in re.findall(rb"/Width (\d+)", pdf)]
    hoehen = [int(n) for n in re.findall(rb"/Height (\d+)", pdf)]
    assert len(breiten) == len(hoehen)
    return list(zip(breiten, hoehen))


def test_arbeit_als_pdf_liefert_ein_pdf_mit_einer_seite_je_foto(speicher):
    nr = _aufgabe(speicher)
    arbeit_id, _ = _arbeit(speicher, nr, _z(), seitenzahl=2)
    pdf = ausgabe.arbeit_als_pdf(speicher, arbeit_id)
    assert isinstance(pdf, bytes) and pdf.startswith(b"%PDF") and b"%%EOF" in pdf[-64:]
    assert _seitenzahl(pdf) == 2
    # Je Seite ein Bild: das Foto mit Randspalte und Kopf; die letzte Seite trägt den Kasten.
    (b1, h1), (b2, h2) = _bildmasse(pdf)
    assert b1 == b2 == B + ausgabe.randbreite(B)
    assert h1 == H + ausgabe.kopfhoehe(B) and h2 > h1


def test_arbeit_als_pdf_laesst_fotos_und_bestaetigung_unberuehrt(speicher):
    nr = _aufgabe(speicher)
    arbeit_id, (seite_id,) = _arbeit(speicher, nr, _z())
    pfad = speicher.bildpfad(speicher.seite(seite_id)["bilddatei"])
    vorher, stand = pfad.read_bytes(), speicher.arbeit(arbeit_id)["stand"]
    ausgabe.arbeit_als_pdf(speicher, arbeit_id)
    assert pfad.read_bytes() == vorher
    assert speicher.arbeit(arbeit_id)["stand"] == stand
    assert speicher.arbeit(arbeit_id)["bestaetigt_am"] is not None


def test_nicht_bestaetigte_arbeit_wirft_regelfehler(speicher):
    nr = _aufgabe(speicher)
    arbeit_id, _ = _arbeit(speicher, nr, _z(), bestaetigen=False)
    with pytest.raises(RegelFehler, match="bestätigt"):
        ausgabe.arbeit_als_pdf(speicher, arbeit_id)


def test_verfallene_bestaetigung_wirft_regelfehler(speicher):
    nr = _aufgabe(speicher)
    arbeit_id, (seite_id,) = _arbeit(speicher, nr, _z())
    speicher.zeichen_anlegen(seite_id, _z("Z", x=300))   # jede Änderung hebt die Bestätigung auf
    with pytest.raises(RegelFehler):
        ausgabe.arbeit_als_pdf(speicher, arbeit_id)


def test_unbekannte_arbeit_wirft_regelfehler(speicher):
    with pytest.raises(RegelFehler):
        ausgabe.arbeit_als_pdf(speicher, 999)


def test_fehlendes_foto_wirft_ausgabefehler_mit_seitennummer(speicher):
    nr = _aufgabe(speicher)
    arbeit_id, (s1, s2) = _arbeit(speicher, nr, seitenzahl=2)
    speicher.bildpfad(speicher.seite(s2)["bilddatei"]).unlink()
    with pytest.raises(ausgabe.AusgabeFehler, match="Seite 2"):
        ausgabe.arbeit_als_pdf(speicher, arbeit_id)
    with pytest.raises(ausgabe.AusgabeFehler, match="Seite 2"):
        ausgabe.aufgabe_als_pdf(speicher, nr)
    assert not issubclass(ausgabe.AusgabeFehler, RegelFehler)


@pytest.mark.parametrize("inhalt", [b"", b"kein Bild", None])
def test_defektes_foto_wirft_ausgabefehler(speicher, inhalt):
    nr = _aufgabe(speicher)
    arbeit_id, (seite_id,) = _arbeit(speicher, nr)
    pfad = speicher.bildpfad(speicher.seite(seite_id)["bilddatei"])
    pfad.write_bytes(_jpeg()[:200] if inhalt is None else inhalt)   # None: abgeschnitten
    with pytest.raises(ausgabe.AusgabeFehler, match="Seite 1"):
        ausgabe.arbeit_als_pdf(speicher, arbeit_id)


def test_titel_im_pdf_nennt_nur_die_aufgabe(speicher):
    # Ein weitergegebenes Sammel-PDF verrät nicht, wie viele Arbeiten fehlen.
    nr = _aufgabe(speicher, titel="Versuch")
    _arbeit(speicher, nr)
    _arbeit(speicher, nr, bestaetigen=False)
    pdf, enthalten, fehlend = ausgabe.aufgabe_als_pdf(speicher, nr)
    assert (enthalten, fehlend) == (1, 1)
    (titel,) = re.findall(rb"/Title \((.*?)\)", pdf)
    assert titel.replace(b"\xfe\xff", b"").replace(b"\x00", b"") == b"Versuch"
    assert b" von " not in pdf and b"Arbeiten" not in pdf


def test_aufgabe_als_pdf_enthaelt_nur_bestaetigte_arbeiten(speicher):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, _z(), seitenzahl=2)
    _arbeit(speicher, nr, _z(), seitenzahl=3, bestaetigen=False)
    _arbeit(speicher, nr, seitenzahl=1)
    pdf, enthalten, fehlend = ausgabe.aufgabe_als_pdf(speicher, nr)
    assert pdf.startswith(b"%PDF") and _seitenzahl(pdf) == 3
    assert (enthalten, fehlend) == (2, 1)


def test_aufgabe_als_pdf_nimmt_nur_arbeiten_der_aufgabe(speicher):
    nr, andere = _aufgabe(speicher), _aufgabe(speicher, titel="Andere")
    _arbeit(speicher, nr, seitenzahl=1)
    _arbeit(speicher, andere, seitenzahl=2)
    pdf, enthalten, fehlend = ausgabe.aufgabe_als_pdf(speicher, nr)
    assert _seitenzahl(pdf) == 1 and (enthalten, fehlend) == (1, 0)


def test_aufgabe_als_pdf_ohne_bestaetigte_arbeit_wirft_regelfehler(speicher):
    nr = _aufgabe(speicher)
    with pytest.raises(RegelFehler, match="bestätigt"):
        ausgabe.aufgabe_als_pdf(speicher, nr)
    _arbeit(speicher, nr, _z(), bestaetigen=False)
    with pytest.raises(RegelFehler, match="bestätigt"):
        ausgabe.aufgabe_als_pdf(speicher, nr)
    with pytest.raises(RegelFehler):
        ausgabe.aufgabe_als_pdf(speicher, 999)


def test_sehr_grosse_bilder_werden_auf_2400_pixel_kante_verkleinert(speicher):
    nr = _aufgabe(speicher)
    quer, _ = _arbeit(speicher, nr, _z(), groesse=(4000, 3000))
    hoch, _ = _arbeit(speicher, nr, _z(), groesse=(3000, 4200))
    for arbeit_id in (quer, hoch):
        ((breite, hoehe),) = _bildmasse(ausgabe.arbeit_als_pdf(speicher, arbeit_id))
        assert 2390 <= max(breite, hoehe) <= 2400


def test_kleine_bilder_werden_nicht_vergroessert(speicher):
    nr = _aufgabe(speicher)
    arbeit_id, _ = _arbeit(speicher, nr)
    ((breite, hoehe),) = _bildmasse(ausgabe.arbeit_als_pdf(speicher, arbeit_id))
    assert breite == B + ausgabe.randbreite(B)


def test_seitenbilder_tragen_die_zeichen_an_der_verkleinerten_stelle(speicher):
    nr = _aufgabe(speicher)
    z = _z("Z", x=1000, y=2000, breite=800, hoehe=200)
    arbeit_id, _ = _arbeit(speicher, nr, z, _z("R", x=100, y=100, status="verworfen"),
                           groesse=(4000, 3000), seitenzahl=2)
    erste, zweite = ausgabe.seitenbilder(speicher, speicher.aufgabe(nr),
                                         speicher.arbeit(arbeit_id))
    assert max(erste.size) <= 2400 and max(zweite.size) <= 2400
    foto_b = round(erste.width / (1 + ausgabe.RAND_ANTEIL))
    faktor = foto_b / 4000
    kopf = ausgabe.kopfhoehe(foto_b)
    blau = [p for p in _bunte(erste, (0, kopf, foto_b, erste.height))
            if erste.getpixel(p) == ausgabe.farbe("Z")]
    assert blau
    xs, ys = [p[0] for p in blau], [p[1] for p in blau]
    assert abs(min(xs) - 1000 * faktor) <= 2 and abs(max(xs) - 1800 * faktor) <= 2
    assert 0 <= min(ys) - kopf - 2200 * faktor <= 3 * ausgabe.strichstaerke(foto_b)
    # Verworfenes erscheint nicht; die zweite Seite hat keine Zeichen, aber die Übersicht.
    assert not [p for p in _bunte(erste) if erste.getpixel(p) == ausgabe.farbe("R")]
    assert zweite.height > erste.height
    assert [p for p in _bunte(zweite) if zweite.getpixel(p) == ausgabe.farbe("Z")]


def test_richtige_schreibung_folgt_der_einstellung_der_aufgabe(speicher):
    nr = _aufgabe(speicher, vorschlag_in_ausgabe=True)
    arbeit_id, _ = _arbeit(speicher, nr, _z())
    ((breite, _),) = _bildmasse(ausgabe.arbeit_als_pdf(speicher, arbeit_id))
    assert breite == B + ausgabe.randbreite(B, True)


def _mitschreiben(monkeypatch):
    """Merkt sich Kopf und Übersicht jedes Aufrufs von `seite_zeichnen`."""
    aufrufe = []
    echt = ausgabe.seite_zeichnen

    def mitschreiben(bild, zeichen, vorschlag_zeigen=False, kopf="", uebersicht=None):
        aufrufe.append((kopf, uebersicht))
        return echt(bild, zeichen, vorschlag_zeigen, kopf, uebersicht)

    monkeypatch.setattr(ausgabe, "seite_zeichnen", mitschreiben)
    return aufrufe


def test_kopf_nennt_titel_kuerzel_und_seite(speicher, monkeypatch):
    nr = _aufgabe(speicher, titel="Erörterung")
    arbeit_id, _ = _arbeit(speicher, nr, _z("Gr"), seitenzahl=2)
    speicher.arbeit_kuerzel_setzen(arbeit_id, "Ä7")
    aufrufe = _mitschreiben(monkeypatch)
    ausgabe.arbeit_als_pdf(speicher, arbeit_id)
    # Die Fehlerübersicht steht nur auf der letzten Seite und zählt die ganze Arbeit.
    assert aufrufe == [
        ("Erörterung · Arbeit Ä7 · Seite 1 von 2", None),
        ("Erörterung · Arbeit Ä7 · Seite 2 von 2",
         [{"kuerzel": "Gr", "bezeichnung": "Grammatik", "anzahl": 1}])]


def test_sammel_pdf_beginnt_jede_arbeit_mit_seite_1_in_stapelreihenfolge(speicher, monkeypatch):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, seitenzahl=2)
    _arbeit(speicher, nr, seitenzahl=1)
    aufrufe = _mitschreiben(monkeypatch)
    ausgabe.aufgabe_als_pdf(speicher, nr)
    assert [(kopf, uebersicht is not None) for kopf, uebersicht in aufrufe] == [
        ("Versuchsbeschreibung · Arbeit 01 · Seite 1 von 2", False),
        ("Versuchsbeschreibung · Arbeit 01 · Seite 2 von 2", True),
        ("Versuchsbeschreibung · Arbeit 02 · Seite 1 von 1", True)]


# --- Speicherbedarf: Seiten einzeln schreiben -----------------------------------------------

def test_sammel_pdf_mit_zwoelf_seiten_ist_vollstaendig(speicher):
    nr = _aufgabe(speicher, titel="Zwölf Seiten")
    for seitenzahl in (5, 4, 3):
        _arbeit(speicher, nr, _z(), seitenzahl=seitenzahl)
    pdf, enthalten, fehlend = ausgabe.aufgabe_als_pdf(speicher, nr)
    assert (enthalten, fehlend) == (3, 0)
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")
    assert _seitenzahl(pdf) == 12 and len(_bildmasse(pdf)) == 12   # je Seite genau ein Bild
    with PdfParser.PdfParser(f=io.BytesIO(pdf), mode="rb") as leser:
        assert leser.info.Title == "Zwölf Seiten"


def test_pdf_einer_arbeit_mit_zwoelf_seiten(speicher):
    nr = _aufgabe(speicher)
    arbeit_id, _ = _arbeit(speicher, nr, _z(), seitenzahl=12)
    pdf = ausgabe.arbeit_als_pdf(speicher, arbeit_id)
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")
    assert _seitenzahl(pdf) == 12 and len(_bildmasse(pdf)) == 12


@pytest.mark.parametrize("sammel", [False, True])
def test_seiten_werden_einzeln_gezeichnet_geschrieben_und_freigegeben(speicher, monkeypatch,
                                                                      sammel):
    nr = _aufgabe(speicher)
    arbeit_id, _ = _arbeit(speicher, nr, _z(), seitenzahl=3)
    _arbeit(speicher, nr, seitenzahl=2)
    ablauf, bilder, lebend = [], [], []
    zeichnen, anhaengen = ausgabe.seite_zeichnen, ausgabe._seite_anhaengen

    def noch_da():
        gc.collect()
        return sum(1 for verweis in bilder if verweis() is not None)

    def gezeichnet(*args, **kwargs):
        lebend.append(noch_da())          # frühere Seiten, die beim Zeichnen noch leben
        ablauf.append("zeichnen")
        bild = zeichnen(*args, **kwargs)
        bilder.append(weakref.ref(bild))
        return bild

    def geschrieben(ziel, bild, titel, erste):
        ablauf.append("schreiben")
        assert erste == (len(ablauf) == 2)
        return anhaengen(ziel, bild, titel, erste)

    monkeypatch.setattr(ausgabe, "seite_zeichnen", gezeichnet)
    monkeypatch.setattr(ausgabe, "_seite_anhaengen", geschrieben)
    if sammel:
        pdf = ausgabe.aufgabe_als_pdf(speicher, nr)[0]
    else:
        pdf = ausgabe.arbeit_als_pdf(speicher, arbeit_id)
    seiten = 5 if sammel else 3
    assert _seitenzahl(pdf) == seiten
    # Nie werden zwei Seiten gezeichnet, ohne dass die erste geschrieben ist.
    assert ablauf == ["zeichnen", "schreiben"] * seiten
    # Beim Zeichnen einer Seite ist keine frühere mehr im Arbeitsspeicher, am Ende keine.
    assert lebend == [0] * seiten and noch_da() == 0


def test_hoechstens_ein_sammel_pdf_zur_selben_zeit(speicher, monkeypatch):
    nr = _aufgabe(speicher)
    _arbeit(speicher, nr, seitenzahl=2)
    echt = ausgabe.seitenbilder
    gleichzeitig, hoechstens, ergebnisse = [0], [0], []
    zaehler = threading.Lock()

    def langsam(*args, **kwargs):
        with zaehler:
            gleichzeitig[0] += 1
            hoechstens[0] = max(hoechstens[0], gleichzeitig[0])
        try:
            time.sleep(0.05)
            yield from echt(*args, **kwargs)
        finally:
            with zaehler:
                gleichzeitig[0] -= 1

    monkeypatch.setattr(ausgabe, "seitenbilder", langsam)
    faeden = [threading.Thread(target=lambda: ergebnisse.append(ausgabe.aufgabe_als_pdf(speicher,
                                                                                        nr)))
              for _ in range(3)]
    for faden in faeden:
        faden.start()
    for faden in faeden:
        faden.join(timeout=30)
    # Die zweite und dritte Anfrage haben gewartet; alle bekommen ihr vollständiges PDF.
    assert hoechstens[0] == 1
    assert [(_seitenzahl(pdf), enthalten) for pdf, enthalten, _ in ergebnisse] == [(2, 1)] * 3


def test_sperre_ist_nach_einem_fehler_wieder_frei(speicher):
    nr = _aufgabe(speicher)
    with pytest.raises(RegelFehler):
        ausgabe.aufgabe_als_pdf(speicher, nr)
    _, (seite_id,) = _arbeit(speicher, nr)
    pfad = speicher.bildpfad(speicher.seite(seite_id)["bilddatei"])
    inhalt = pfad.read_bytes()
    pfad.write_bytes(b"kein Bild")
    with pytest.raises(ausgabe.AusgabeFehler):
        ausgabe.aufgabe_als_pdf(speicher, nr)
    pfad.write_bytes(inhalt)
    assert _seitenzahl(ausgabe.aufgabe_als_pdf(speicher, nr)[0]) == 1


def test_grosses_jpeg_wird_schon_beim_laden_verkleinert(speicher, monkeypatch):
    # Bei 6000 × 8000 genügt das Entpacken in halber Größe; das Ergebnis bleibt gleich groß.
    nr = _aufgabe(speicher)
    arbeit_id, _ = _arbeit(speicher, nr, _z("Z", x=1500, y=3000, breite=1500, hoehe=300),
                           groesse=(6000, 8000))
    gezeichnet = []
    echt = ausgabe.seite_zeichnen
    monkeypatch.setattr(ausgabe, "seite_zeichnen",
                        lambda bild, *a, **k: gezeichnet.append(bild.size) or echt(bild, *a, **k))
    entwurf, draft = [], JpegImagePlugin.JpegImageFile.draft
    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft",
                        lambda self, *a, **k: entwurf.append(a) or draft(self, *a, **k))
    ((breite, hoehe),) = _bildmasse(ausgabe.arbeit_als_pdf(speicher, arbeit_id))
    assert 2390 <= max(breite, hoehe) <= 2400
    (foto_b, foto_h), = gezeichnet
    assert abs(foto_h / foto_b - 8000 / 6000) < 0.01
    # Verlangt wird nie weniger als die Zielgröße.
    assert entwurf and entwurf[0][1] == (foto_b, foto_h)


def test_fehleruebersicht_zaehlt_bestaetigte_zeichen_aller_seiten():
    eigene = [{"kuerzel": "W", "bezeichnung": "Wortwahl"},
              {"kuerzel": "A", "bezeichnung": "Ausdruck"}]
    seiten = [{"zeichen": [_z("W"), _z("Gr"), _z("R"), _z("R", status="verworfen"),
                           _z("Z", status="offen")]},
              {"zeichen": [_z("R", herkunft="hand"), _z("A"), _z("weg")]}]
    assert ausgabe.fehleruebersicht(seiten, eigene) == [
        {"kuerzel": "R", "bezeichnung": "Rechtschreibung", "anzahl": 2},
        {"kuerzel": "Gr", "bezeichnung": "Grammatik", "anzahl": 1},
        {"kuerzel": "A", "bezeichnung": "Ausdruck", "anzahl": 1},
        {"kuerzel": "W", "bezeichnung": "Wortwahl", "anzahl": 1},
        {"kuerzel": "weg", "bezeichnung": "", "anzahl": 1}]   # entferntes Kürzel: ohne Namen
    assert ausgabe.fehleruebersicht([{"zeichen": []}], eigene) == []
