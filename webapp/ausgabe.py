"""Ausgabe bestätigter Arbeiten: je Seite ein Bild aus Foto, Zeichen und Randspalte.

Das Foto wird nie verändert; jede Seite ist ein neues Bild. Im Text steht je bestätigtem
Zeichen eine Unterstreichung (`wort`) oder ein Einfügezeichen (`luecke`), rechts daneben eine
angefügte Randspalte mit den Kürzeln auf Höhe der Textzeile. Die Ausgabe zeigt nicht, ob ein
Zeichen von der KI stammt oder von Hand gesetzt ist, und sie bewertet nichts.

Alle Maße hängen an der Breite des Fotos, damit die Seite bei jeder Auflösung gleich aussieht.
Das PDF schreibt Pillow: je Seite ein Bild, keine weitere Abhängigkeit.
"""
import io
from collections import Counter
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from webapp.regeln import RegelFehler

# Die Farben je Kategorie, passend zur Korrekturansicht (`--kat-R`, `--kat-Z`, `--kat-Gr` in
# app.css). Eigene Kürzel tragen das Petrol der selbst gesetzten Zeichen.
FARBEN = {"R": (198, 40, 40), "Z": (21, 101, 192), "Gr": (123, 31, 162)}
FARBE_EIGEN = (0, 121, 107)
WEISS = (255, 255, 255)
DUNKEL = (31, 35, 40)        # Kopf, Zahlen
GRAU = (78, 84, 92)          # Vorschlag, Bezeichnungen
LINIE = (176, 176, 170)      # Trennlinie, Kasten

FESTE_KATEGORIEN = (("R", "Rechtschreibung"), ("Z", "Zeichensetzung"), ("Gr", "Grammatik"))

MAX_KANTE = 2400             # Pixel; längere Seiten werden für das PDF verkleinert
JPEG_QUALITAET = 85
# Eine Seite mit 2400 Pixeln langer Kante ist im PDF so lang wie ein A4-Blatt (297 mm).
AUFLOESUNG = MAX_KANTE / (297 / 25.4)

RAND_ANTEIL = 0.16           # Breite der Randspalte als Anteil der Fotobreite
RAND_ANTEIL_VORSCHLAG = 0.28  # mit „richtige Schreibung zeigen“

# Schriften mit Umlauten und ß, der Reihe nach versucht; zuletzt die Standardschrift von Pillow.
SCHRIFTEN = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
             "Arial.ttf", "Helvetica.ttc")
SCHRIFTEN_FETT = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf",
                  "LiberationSans-Bold.ttf", "Arial Bold.ttf")


def farbe(kategorie):
    """Die Farbe einer Kategorie als (r, g, b)."""
    return FARBEN.get(kategorie, FARBE_EIGEN)


def strichstaerke(breite):
    """Strichstärke der Zeichen im Text: etwa 0,25 % der Fotobreite, mindestens 2 Pixel."""
    return max(2, round(breite * 0.0025))


def randbreite(breite, vorschlag_zeigen=False):
    """Breite der angefügten Randspalte in Pixeln."""
    return round(breite * (RAND_ANTEIL_VORSCHLAG if vorschlag_zeigen else RAND_ANTEIL))


def _kuerzelgroesse(breite):
    return max(11, round(breite * 0.024))


def _vorschlaggroesse(breite):
    return max(9, round(breite * 0.017))


def _textgroesse(breite):
    return max(10, round(breite * 0.019))


def kopfhoehe(breite):
    """Höhe der Kopfzeile über dem Foto in Pixeln."""
    return round(_textgroesse(breite) * 2.1)


@lru_cache(maxsize=64)
def schrift(groesse, fett=False):
    """Eine skalierbare Schrift in der genannten Größe.

    Versucht gängige Systemschriften; fehlen alle, gilt die Standardschrift von Pillow (dann
    auch für fette Schrift).
    """
    for namen in ((SCHRIFTEN_FETT, SCHRIFTEN) if fett else (SCHRIFTEN,)):
        for name in namen:
            try:
                return ImageFont.truetype(name, groesse)
            except OSError:
                continue
    return ImageFont.load_default(size=groesse)


def _einzeilig(text):
    return " ".join(str(text or "").split())


def kuerzen(text, schriftart, breite):
    """Der Text, wenn er in die Breite passt; sonst gekürzt mit „…“, notfalls leer."""
    if schriftart.getlength(text) <= breite:
        return text
    for laenge in range(len(text) - 1, 0, -1):
        kurz = text[:laenge].rstrip() + "…"
        if schriftart.getlength(kurz) <= breite:
            return kurz
    return ""


# --- Textzeilen -----------------------------------------------------------------------------

def _selbe_zeile(a, b):
    """Ob sich die senkrechten Bereiche zu mehr als der Hälfte der kleineren Höhe überlappen."""
    gemeinsam = min(a["y"] + a["hoehe"], b["y"] + b["hoehe"]) - max(a["y"], b["y"])
    return gemeinsam > 0.5 * min(a["hoehe"], b["hoehe"])


def _mitte(z):
    return z["y"] + z["hoehe"] / 2


def randzeilen(zeichen):
    """Gruppiert die Zeichen nach Textzeilen: von oben nach unten, je Zeile von links nach rechts.

    Zwei Zeichen gehören zur selben Textzeile, wenn sich ihre senkrechten Bereiche zu mehr als
    der Hälfte der kleineren Höhe überlappen. Alle übergebenen Zeichen werden eingeordnet; die
    Auswahl der bestätigten trifft `seite_zeichnen`.
    """
    zeilen = []
    for z in sorted(zeichen, key=lambda z: (_mitte(z), z["x"])):
        for zeile in zeilen:
            if any(_selbe_zeile(z, anderes) for anderes in zeile):
                zeile.append(z)
                break
        else:
            zeilen.append([z])
    zeilen.sort(key=lambda zeile: sum(_mitte(z) for z in zeile) / len(zeile))
    return [sorted(zeile, key=lambda z: (z["x"], z["y"])) for zeile in zeilen]


# --- Randspalte -----------------------------------------------------------------------------

def _randspalte_setzen(zeichen, breite, hoehe, rand, vorschlag_zeigen):
    """Legt fest, wo in der Randspalte was steht.

    Gibt (einträge, klammern, benötigte Höhe) zurück; ein Eintrag ist (x, grundlinie, kürzel,
    farbe, vorschlag) mit x ab dem linken Rand der Spalte und der Grundlinie ab der Oberkante
    des Fotos. Je Textzeile stehen die Einträge nebeneinander; reicht der Platz nicht, wird
    umbrochen. Blöcke, die sich überdecken würden, rücken nach unten; reicht der Platz neben
    dem Foto nicht, zuerst nach oben und zuletzt über die Fotohöhe hinaus. Eine Klammer
    (x, oben, unten) fasst die Zeilen eines umbrochenen Blocks am linken Rand zusammen.
    """
    fett = schrift(_kuerzelgroesse(breite), True)
    klein = schrift(_vorschlaggroesse(breite))
    zeilenhoehe = round(_kuerzelgroesse(breite) * 1.3)
    grundlinie = round(zeilenhoehe * 0.76)
    innen = max(3, round(rand * 0.07))            # Abstand zu Trennlinie und Rand
    platz = rand - 2 * innen
    zwischen = round(_kuerzelgroesse(breite) * 0.55)   # zwischen zwei Einträgen
    luft = round(_kuerzelgroesse(breite) * 0.28)       # zwischen Kürzel und Vorschlag
    abstand = round(zeilenhoehe * 0.3)                 # zwischen zwei Blöcken, die sich drängen

    bloecke = []   # [wunsch_oben, hoehe, [(x, zeile, kuerzel, farbe, vorschlag)]]
    for textzeile in randzeilen(zeichen):
        x, zeile, eintraege = 0, 0, []
        for z in textzeile:
            kuerzel = kuerzen(_einzeilig(z["kategorie"]), fett, platz)
            weite = fett.getlength(kuerzel)
            vorschlag = _einzeilig(z.get("vorschlag")) if vorschlag_zeigen else ""
            if vorschlag:
                vorschlag = kuerzen(vorschlag, klein, platz - weite - luft)
            if vorschlag:
                weite += luft + klein.getlength(vorschlag)
            if x > 0 and x + weite > platz:
                x, zeile = 0, zeile + 1
            eintraege.append((innen + round(x), zeile, kuerzel, farbe(z["kategorie"]), vorschlag))
            x += weite + zwischen
        mitte = sum(_mitte(z) for z in textzeile) / len(textzeile)
        bloecke.append([round(mitte - zeilenhoehe / 2), (zeile + 1) * zeilenhoehe, eintraege])

    # Nach unten rücken, was sich überdecken würde.
    unten = 0
    for block in bloecke:
        block[0] = max(block[0], unten)
        unten = block[0] + block[1] + abstand
    # Ragt das Ende über das Foto hinaus, von unten her wieder nach oben schieben.
    grenze = hoehe
    for block in reversed(bloecke):
        if block[0] + block[1] <= grenze:
            break
        block[0] = grenze - block[1]
        grenze = block[0] - abstand
    # Reicht die Höhe insgesamt nicht, lückenlos von oben stapeln; die Seite wächst dann.
    if bloecke and bloecke[0][0] < 0:
        unten = 0
        for block in bloecke:
            block[0] = unten
            unten += block[1] + abstand
    benoetigt = max([hoehe] + [block[0] + block[1] + innen for block in bloecke[-1:]
                               if block[0] + block[1] > hoehe])
    gesetzt = [(x, oben + zeile * zeilenhoehe + grundlinie, kuerzel, f, vorschlag)
               for oben, _, eintraege in bloecke for x, zeile, kuerzel, f, vorschlag in eintraege]
    einzug = round(zeilenhoehe * 0.15)
    klammern = [(round(innen * 0.45), oben + einzug, oben + block_h - einzug)
                for oben, block_h, _ in bloecke if block_h > zeilenhoehe]
    return gesetzt, klammern, benoetigt


def _randspalte_zeichnen(stift, eintraege, klammern, breite, links, oben):
    fett = schrift(_kuerzelgroesse(breite), True)
    klein = schrift(_vorschlaggroesse(breite))
    luft = round(_kuerzelgroesse(breite) * 0.28)
    for x, grundlinie, kuerzel, f, vorschlag in eintraege:
        stift.text((links + x, oben + grundlinie), kuerzel, font=fett, fill=f, anchor="ls")
        if vorschlag:
            stift.text((links + x + fett.getlength(kuerzel) + luft, oben + grundlinie),
                       vorschlag, font=klein, fill=GRAU, anchor="ls")
    staerke = max(1, strichstaerke(breite) // 2)
    for x, k_oben, k_unten in klammern:
        stift.rectangle([links + x, oben + k_oben, links + x + staerke - 1, oben + k_unten],
                        fill=LINIE)


# --- Zeichen im Text ------------------------------------------------------------------------

def _im_text_zeichnen(stift, zeichen, breite, hoehe, oben):
    """Unterstreichung je `wort`, Einfügezeichen je `luecke`; alles bleibt im Foto."""
    strich = strichstaerke(breite)
    for z in zeichen:
        f = farbe(z["kategorie"])
        links = max(0, min(round(z["x"]), breite - 1))
        rechts = max(links, min(round(z["x"] + z["breite"]), breite) - 1)
        unterkante = round(z["y"] + z["hoehe"])
        if z.get("typ") == "luecke":
            # Ein nach oben offener Winkel, die Spitze knapp unter der Unterkante der Lücke.
            arm = max(3 * strich, round(z["hoehe"] * 0.3))
            halb = max(2 * strich, round(arm * 0.65))
            mitte = max(halb, min(round(z["x"] + z["breite"] / 2), breite - 1 - halb))
            spitze = max(arm, min(unterkante + strich, hoehe - 1 - strich // 2))
            stift.line([(mitte - halb, oben + spitze - arm), (mitte, oben + spitze),
                        (mitte + halb, oben + spitze - arm)], fill=f, width=strich, joint="curve")
        else:
            y = max(0, min(unterkante + strich, hoehe - strich))
            stift.rectangle([links, oben + y, rechts, oben + y + strich - 1], fill=f)


# --- Kopf und Fehlerübersicht ---------------------------------------------------------------

def _kopf_zeichnen(stift, text, breite, gesamtbreite):
    hoehe = kopfhoehe(breite)
    art = schrift(_textgroesse(breite))
    rand = round(_textgroesse(breite) * 0.7)
    stift.text((rand, hoehe // 2), kuerzen(_einzeilig(text), art, gesamtbreite - 2 * rand),
               font=art, fill=DUNKEL, anchor="lm")
    stift.line([(0, hoehe - 1), (gesamtbreite, hoehe - 1)], fill=LINIE, width=1)


def _uebersicht_setzen(uebersicht, breite, gesamtbreite):
    """Der Kasten der Fehlerübersicht: (textstücke, höhe, kasten).

    Ein Textstück ist (x, grundlinie, text, schrift, farbe) ab der Oberkante des Kastens.
    Die Einträge stehen nebeneinander und brechen um, wenn die Breite nicht reicht.
    """
    groesse = _textgroesse(breite)
    normal, fett = schrift(groesse), schrift(groesse, True)
    aussen = round(groesse * 0.7)
    innen = round(groesse * 0.8)
    zeilenhoehe = round(groesse * 1.6)
    links = aussen + innen
    platz = gesamtbreite - 2 * links
    wort = round(groesse * 0.35)        # zwischen den Teilen eines Eintrags
    zwischen = round(groesse * 1.5)     # zwischen zwei Einträgen

    eintraege = [[("Fehlerübersicht", fett, DUNKEL)]]
    for eintrag in uebersicht:
        eintraege.append([(_einzeilig(eintrag["kuerzel"]), fett, farbe(eintrag["kuerzel"])),
                          (_einzeilig(eintrag.get("bezeichnung")), normal, GRAU),
                          (str(eintrag["anzahl"]), fett, DUNKEL)])
    if uebersicht:
        summe = sum(eintrag["anzahl"] for eintrag in uebersicht)
        eintraege.append([("Summe", normal, GRAU), (str(summe), fett, DUNKEL)])
    else:
        eintraege.append([("keine Zeichen", normal, GRAU)])

    stuecke, x, zeile = [], 0, 0
    for teile in eintraege:
        teile = [teil for teil in teile if teil[0]]
        fest = sum(art.getlength(text) for text, art, _ in teile if art is fett)
        frei = platz - fest - wort * (len(teile) - 1)
        # Nur die Bezeichnung (normale Schrift) wird gekürzt, wenn ein Eintrag nicht passt.
        teile = [(text if art is fett else kuerzen(text, art, max(0, frei)), art, f)
                 for text, art, f in teile]
        teile = [teil for teil in teile if teil[0]]
        weite = sum(art.getlength(text) for text, art, _ in teile) + wort * (len(teile) - 1)
        if x > 0 and x + weite > platz:
            x, zeile = 0, zeile + 1
        stelle = x
        for text, art, f in teile:
            stuecke.append((links + round(stelle), zeile, text, art, f))
            stelle += art.getlength(text) + wort
        x += weite + zwischen
    hoehe = 2 * aussen + 2 * innen + (zeile + 1) * zeilenhoehe
    grundlinie = aussen + innen + round(zeilenhoehe * 0.72)
    gesetzt = [(sx, grundlinie + z * zeilenhoehe, text, art, f) for sx, z, text, art, f in stuecke]
    kasten = (aussen, aussen, gesamtbreite - 1 - aussen, hoehe - 1 - aussen)
    return gesetzt, hoehe, kasten


def _uebersicht_zeichnen(stift, gesetzt, kasten, breite, oben):
    links, k_oben, rechts, unten = kasten
    stift.rectangle([links, oben + k_oben, rechts, oben + unten], outline=LINIE,
                    width=max(1, strichstaerke(breite) // 2))
    for x, grundlinie, text, art, f in gesetzt:
        stift.text((x, oben + grundlinie), text, font=art, fill=f, anchor="ls")


# --- Seite ----------------------------------------------------------------------------------

def seite_zeichnen(bild, zeichen, vorschlag_zeigen=False, kopf="", uebersicht=None):
    """Zeichnet eine Seite der Ausgabe und gibt sie als neues RGB-Bild zurück.

    `bild` ist das aufrecht gedrehte Foto; es bleibt unverändert. `zeichen` sind die Zeichen
    der Seite mit Rahmen in Pixeln des Fotos; berücksichtigt werden nur die bestätigten.
    Mit `vorschlag_zeigen` steht die richtige Schreibung klein neben dem Kürzel. `kopf` ist
    der Text der Kopfzeile über dem Foto (leer: keine Kopfzeile). `uebersicht` ist die
    Fehlerübersicht als `[{"kuerzel", "bezeichnung", "anzahl"}]` in der Reihenfolge der
    Anzeige; sie steht als Kasten unter dem Foto (`None`: kein Kasten).
    """
    breite, hoehe = bild.size
    fest = [z for z in zeichen if z.get("status") == "bestaetigt"]
    rand = randbreite(breite, vorschlag_zeigen)
    gesamtbreite = breite + rand
    kopf_h = kopfhoehe(breite) if kopf else 0
    eintraege, klammern, spalte_h = _randspalte_setzen(fest, breite, hoehe, rand,
                                                       vorschlag_zeigen)
    kasten_h = 0
    if uebersicht is not None:
        gesetzt, kasten_h, kasten = _uebersicht_setzen(uebersicht, breite, gesamtbreite)

    seite = Image.new("RGB", (gesamtbreite, kopf_h + spalte_h + kasten_h), WEISS)
    seite.paste(bild if bild.mode == "RGB" else bild.convert("RGB"), (0, kopf_h))
    stift = ImageDraw.Draw(seite)
    _im_text_zeichnen(stift, fest, breite, hoehe, kopf_h)
    stift.rectangle([breite, kopf_h, breite + max(1, round(breite / 1000)) - 1,
                     kopf_h + spalte_h - 1], fill=LINIE)
    _randspalte_zeichnen(stift, eintraege, klammern, breite, breite, kopf_h)
    if kopf:
        _kopf_zeichnen(stift, kopf, breite, gesamtbreite)
    if uebersicht is not None:
        _uebersicht_zeichnen(stift, gesetzt, kasten, breite, kopf_h + spalte_h)
    return seite


# --- PDF ------------------------------------------------------------------------------------

def fehleruebersicht(seiten, eigene):
    """Die Zahl der bestätigten Zeichen je Kategorie über alle Seiten einer Arbeit.

    `seiten` sind Seiten mit ihren `zeichen`, `eigene` die eigenen Kürzel als
    `[{kuerzel, bezeichnung}]`. Gibt `[{"kuerzel", "bezeichnung", "anzahl"}]` zurück: nur
    Kategorien mit mindestens einem Zeichen, R, Z, Gr zuerst, dann die übrigen Kürzel
    alphabetisch. Keine Bewertung.
    """
    zahl = Counter(z["kategorie"] for seite in seiten for z in seite["zeichen"]
                   if z["status"] == "bestaetigt")
    namen = dict(FESTE_KATEGORIEN)
    fest = [kuerzel for kuerzel in namen if zahl[kuerzel]]
    namen = {**{e["kuerzel"]: e["bezeichnung"] for e in eigene}, **namen}
    uebrige = sorted((kuerzel for kuerzel in zahl if kuerzel not in fest),
                     key=lambda kuerzel: (kuerzel.casefold(), kuerzel))
    return [{"kuerzel": kuerzel, "bezeichnung": namen.get(kuerzel, ""), "anzahl": zahl[kuerzel]}
            for kuerzel in fest + uebrige]


def _fotobreite(breite, hoehe, vorschlag_zeigen, uebersicht):
    """Die Breite, auf die das Foto verkleinert wird, damit die Seite MAX_KANTE einhält.

    Nie größer als das Foto selbst.
    """
    def seite(b):
        gesamt = b + randbreite(b, vorschlag_zeigen)
        kasten = _uebersicht_setzen(uebersicht, b, gesamt)[1] if uebersicht is not None else 0
        return gesamt, round(hoehe * b / breite) + kopfhoehe(b) + kasten

    b = breite
    for _ in range(4):
        kante = max(seite(b))
        if kante <= MAX_KANTE:
            break
        b = max(1, int(b * MAX_KANTE / kante))
    return b


def _foto_laden(pfad, vorschlag_zeigen, uebersicht):
    """Lädt das Foto aufrecht und in der Größe für die Ausgabe: (bild, faktor)."""
    with Image.open(pfad) as roh:
        foto = ImageOps.exif_transpose(roh).convert("RGB")
    breite, hoehe = foto.size
    ziel = _fotobreite(breite, hoehe, vorschlag_zeigen, uebersicht)
    if ziel >= breite:
        return foto, 1
    faktor = ziel / breite
    return foto.resize((ziel, max(1, round(hoehe * faktor))), Image.LANCZOS), faktor


def _skaliert(zeichen, faktor):
    if faktor == 1:
        return zeichen
    return [{**z, **{feld: z[feld] * faktor for feld in ("x", "y", "breite", "hoehe")}}
            for z in zeichen]


def seitenbilder(speicher, aufgabe, arbeit, eigene=None):
    """Erzeugt nacheinander die Seiten einer Arbeit als Bilder für das PDF.

    `arbeit` ist eine Arbeit, wie `speicher.arbeit` sie liefert. Jede Seite trägt den Kopf
    mit Aufgabentitel, Kürzel der Arbeit und Seitenzahl, die letzte die Fehlerübersicht.
    Keine Kante ist länger als MAX_KANTE. `RegelFehler`, wenn das Foto einer Seite fehlt.
    """
    if eigene is None:
        eigene = speicher.kuerzel()
    vorschlag_zeigen = bool(aufgabe["vorschlag_in_ausgabe"])
    seitenzahl = len(arbeit["seiten"])
    for nummer, seite in enumerate(arbeit["seiten"], start=1):
        uebersicht = fehleruebersicht(arbeit["seiten"], eigene) if nummer == seitenzahl else None
        try:
            foto, faktor = _foto_laden(speicher.bildpfad(seite["bilddatei"]), vorschlag_zeigen,
                                       uebersicht)
        except OSError as fehler:
            raise RegelFehler(f"Das Foto zu Seite {nummer} der Arbeit {arbeit['kuerzel']} fehlt "
                              "oder ist nicht lesbar. Das PDF wurde nicht erzeugt.") from fehler
        kopf = f"{aufgabe['titel']} · Arbeit {arbeit['kuerzel']} · Seite {nummer} von {seitenzahl}"
        bild = seite_zeichnen(foto, _skaliert(seite["zeichen"], faktor), vorschlag_zeigen, kopf,
                              uebersicht)
        if max(bild.size) > MAX_KANTE:   # etwa eine übervolle Randspalte
            bild.thumbnail((MAX_KANTE, MAX_KANTE), Image.LANCZOS)
        yield bild


def _als_pdf(bilder, titel):
    """Fasst die Seitenbilder zu einem PDF zusammen, je Seite ein Bild."""
    erste, *weitere = bilder
    puffer = io.BytesIO()
    erste.save(puffer, "PDF", save_all=True, append_images=weitere, resolution=AUFLOESUNG,
               quality=JPEG_QUALITAET, title=titel)
    return puffer.getvalue()


def _bestaetigte_arbeit(speicher, arbeit_id):
    """Die Arbeit mit Seiten und Zeichen, wenn ihre Korrektur bestätigt ist; sonst None."""
    arbeit = speicher.arbeit(arbeit_id)
    if arbeit is None or arbeit["bestaetigt_am"] is None or not arbeit["seiten"]:
        return None
    return arbeit


def arbeit_als_pdf(speicher, arbeit_id):
    """Das PDF einer Arbeit als Bytes: je Foto eine Seite.

    `RegelFehler`, wenn die Korrektur der Arbeit nicht bestätigt ist (oder es die Arbeit
    nicht mehr gibt): Ausgegeben wird nur, was die Lehrkraft insgesamt bestätigt hat.
    """
    arbeit = _bestaetigte_arbeit(speicher, arbeit_id)
    aufgabe = speicher.aufgabe(arbeit["aufgabe_id"]) if arbeit else None
    if aufgabe is None:
        raise RegelFehler("Die Korrektur dieser Arbeit ist nicht bestätigt. Ein PDF gibt es "
                          "erst nach „Korrektur gesamt bestätigen“.")
    return _als_pdf(list(seitenbilder(speicher, aufgabe, arbeit)),
                    f"{aufgabe['titel']} – Arbeit {arbeit['kuerzel']}")


def aufgabe_als_pdf(speicher, aufgabe_id):
    """Das Sammel-PDF einer Aufgabe: (bytes, enthalten, fehlend).

    Enthält alle bestätigten Arbeiten in Stapelreihenfolge, jede ab einer neuen Seite.
    `enthalten` und `fehlend` zählen die aufgenommenen und die nicht bestätigten Arbeiten.
    `RegelFehler`, wenn keine Arbeit bestätigt ist.

    Alle Seiten liegen bis zum Schreiben als Bilder im Arbeitsspeicher (bis etwa 15 MB je
    Seite); für einen Klassensatz reicht das.
    """
    aufgabe = speicher.aufgabe(aufgabe_id)
    reihe = speicher.arbeiten(aufgabe_id) if aufgabe else []
    eigene = speicher.kuerzel()
    bilder, enthalten = [], 0
    for eintrag in reihe:
        if eintrag["bestaetigt_am"] is None:
            continue
        arbeit = _bestaetigte_arbeit(speicher, eintrag["id"])   # ein Stand je Arbeit
        if arbeit is None:
            continue
        bilder.extend(seitenbilder(speicher, aufgabe, arbeit, eigene))
        enthalten += 1
    if not enthalten:
        raise RegelFehler("In dieser Aufgabe ist noch keine Korrektur bestätigt. Das Sammel-PDF "
                          "enthält nur Arbeiten nach „Korrektur gesamt bestätigen“.")
    titel = f"{aufgabe['titel']} – {enthalten} von {len(reihe)} Arbeiten"
    return _als_pdf(bilder, titel), enthalten, len(reihe) - enthalten
