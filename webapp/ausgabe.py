"""Ausgabe bestätigter Arbeiten: je Seite ein Bild aus Foto, Zeichen und Randspalte.

Das Foto wird nie verändert; jede Seite ist ein neues Bild. Im Text steht je bestätigtem
Zeichen eine Unterstreichung (`wort`) oder ein Einfügezeichen (`luecke`), rechts daneben eine
angefügte Randspalte mit den Kürzeln auf Höhe der Textzeile. Die Ausgabe zeigt nicht, ob ein
Zeichen von der KI stammt oder von Hand gesetzt ist, und sie bewertet nichts.

Alle Maße hängen an der Breite des Fotos, damit die Seite bei jeder Auflösung gleich aussieht.
Das PDF schreibt Pillow: je Seite ein Bild, keine weitere Abhängigkeit.
"""
import io
import threading
from collections import Counter
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from webapp.regeln import RegelFehler
from webapp.uebersicht import kategorien_ordnen

# Die Farben je Kategorie, passend zur Korrekturansicht (`--kat-R`, `--kat-Z`, `--kat-Gr` in
# app.css). Eigene Kürzel tragen das Petrol der selbst gesetzten Zeichen.
FARBEN = {"R": (198, 40, 40), "Z": (21, 101, 192), "Gr": (123, 31, 162)}
FARBE_EIGEN = (0, 121, 107)
WEISS = (255, 255, 255)
DUNKEL = (31, 35, 40)        # Kopf, Zahlen
GRAU = (78, 84, 92)          # Vorschlag, Bezeichnungen
LINIE = (176, 176, 170)      # Trennlinie, Kasten

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


class AusgabeFehler(Exception):
    """Die Ausgabe scheitert an den Daten selbst: Ein Foto fehlt oder ist nicht lesbar.

    Anders als ein `RegelFehler` ist das kein Zustand, den die Lehrkraft in der Korrektur
    herstellt oder behebt; die Routen antworten mit 500.
    """


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
    def kurz(laenge):
        return text[:laenge].rstrip() + "…"

    # Die längste passende Kürzung, gesucht durch Halbieren (auch sehr lange Texte gehen schnell).
    passt, zu_lang = 0, len(text)
    while zu_lang - passt > 1:
        laenge = (passt + zu_lang) // 2
        if schriftart.getlength(kurz(laenge)) <= breite:
            passt = laenge
        else:
            zu_lang = laenge
    return kurz(passt) if passt else ""


# --- Textzeilen -----------------------------------------------------------------------------

HOHER_RAHMEN = 1.6           # ab dieser Höhe (mal mittlere Höhe) verbindet ein Rahmen nichts
NEIGUNG_GRENZE = 0.15        # größte angenommene Neigung der Textzeilen (15 %)
NEIGUNG_SCHRITT = 0.0025


def _mitte(z):
    return z["y"] + z["hoehe"] / 2


def _xmitte(z):
    return z["x"] + z["breite"] / 2


def _waagerechter_abstand(a, b):
    """Die Lücke zwischen zwei Rahmen in x (0, wenn sie übereinander liegen), dann die Mitten."""
    luecke = max(a["x"], b["x"]) - min(a["x"] + a["breite"], b["x"] + b["breite"])
    return max(0, luecke), abs(_xmitte(a) - _xmitte(b))


def _neigung(zeichen, hoehe_mittel):
    """Schätzt die Neigung der Textzeilen (Anstieg in y je Pixel nach rechts).

    Für jede Neigung im Raster wird gezählt, wie viele Zeichen auf gemeinsamen Geraden liegen.
    Eine Neigung gilt nur, wenn sie deutlich mehr Zeichen aufreiht als die waagerechte Lage
    und als eine beliebige Neigung; sonst 0. Im Zweifel bleibt eine Textzeile lieber
    geteilt, als dass Zeichen benachbarter Zeilen zusammenfallen.
    """
    if len(zeichen) < 3:
        return 0.0
    toleranz = 0.2 * hoehe_mittel

    def aufgereiht(neigung):
        mitten = sorted(_mitte(z) - neigung * _xmitte(z) for z in zeichen)
        return sum(1 for oben, unten in zip(mitten, mitten[1:]) if unten - oben <= toleranz)

    schritte = round(NEIGUNG_GRENZE / NEIGUNG_SCHRITT)
    werte = {i: aufgereiht(i * NEIGUNG_SCHRITT) for i in range(-schritte, schritte + 1)}
    bestes = max(werte.values())
    ueblich = sorted(werte.values())[len(werte) // 2]
    if bestes < werte[0] + 2 or bestes < 2 * ueblich + 2:
        return 0.0
    # Die Mitte des zusammenhängenden besten Bereichs, der der Waagerechten am nächsten liegt.
    von = bis = min((i for i, wert in werte.items() if wert == bestes), key=abs)
    while werte.get(von - 1) == bestes:
        von -= 1
    while werte.get(bis + 1) == bestes:
        bis += 1
    return (von + bis) / 2 * NEIGUNG_SCHRITT


def _textzeilen(zeichen):
    """Die Textzeilen als ([(höhe, [zeichen])], neigung), von oben nach unten.

    `höhe` ist die Mitte der Textzeile am linken Bildrand (x = 0); bei x liegt sie um
    `neigung * x` tiefer. Verglichen wird ein Zeichen je Gruppe nur mit dem waagerecht
    nächsten Mitglied, und zwar nach Abzug der Neigung: So folgt die Gruppe einer schrägen
    oder gebogenen Zeile. Rahmen, die deutlich höher sind als üblich (etwa über zwei
    Textzeilen), verbinden keine Gruppen; sie kommen zu der Gruppe, die sie am stärksten
    überdecken.
    """
    if not zeichen:
        return [], 0.0
    hoehen = sorted(z["hoehe"] for z in zeichen)
    mittel = hoehen[(len(hoehen) - 1) // 2]
    neigung = _neigung(zeichen, mittel)

    def oben(z):
        return z["y"] - neigung * _xmitte(z)

    def gemeinsam(z, gruppe):
        """Senkrechte Überdeckung mit dem waagerecht nächsten Anker: (höhe, anteil)."""
        anker = min(gruppe["anker"], key=lambda a: _waagerechter_abstand(a, z))
        hoehe = (min(oben(z) + z["hoehe"], oben(anker) + anker["hoehe"])
                 - max(oben(z), oben(anker)))
        return hoehe, hoehe / max(1e-9, min(z["hoehe"], anker["hoehe"]))

    gruppen, hohe = [], []
    for z in sorted(zeichen, key=lambda z: (z["x"], z["y"])):
        if z["hoehe"] > HOHER_RAHMEN * mittel:
            hohe.append(z)
            continue
        passend = [(gemeinsam(z, gruppe)[1], -nr) for nr, gruppe in enumerate(gruppen)]
        anteil, nr = max(passend, default=(0, 0))
        if anteil > 0.5:
            gruppen[-nr]["anker"].append(z)
            gruppen[-nr]["alle"].append(z)
        else:
            gruppen.append({"anker": [z], "alle": [z]})
    for z in hohe:
        # Die stärkste Überdeckung entscheidet; bei Gleichstand die obere Zeile.
        passend = [(*gemeinsam(z, gruppe), -oben(gruppe["anker"][0]), nr)
                   for nr, gruppe in enumerate(gruppen)]
        passend = [eintrag for eintrag in passend if eintrag[1] > 0.5]
        if passend:
            gruppen[max(passend)[-1]]["alle"].append(z)
        else:
            gruppen.append({"anker": [z], "alle": [z]})

    zeilen = [(sum(_mitte(z) - neigung * _xmitte(z) for z in gruppe["anker"])
               / len(gruppe["anker"]), sorted(gruppe["alle"], key=lambda z: (z["x"], z["y"])))
              for gruppe in gruppen]
    zeilen.sort(key=lambda zeile: zeile[0])
    return zeilen, neigung


def randzeilen(zeichen):
    """Gruppiert die Zeichen nach Textzeilen: von oben nach unten, je Zeile von links nach rechts.

    Zwei Zeichen gehören zur selben Textzeile, wenn sich ihre senkrechten Bereiche zu mehr als
    der Hälfte der kleineren Höhe überlappen; schräge Zeilen und Rahmen über mehrere Zeilen
    behandelt `_textzeilen`. Alle übergebenen Zeichen werden eingeordnet; die Auswahl der
    bestätigten trifft `seite_zeichnen`.
    """
    return [zeile for _, zeile in _textzeilen(zeichen)[0]]


# --- Randspalte -----------------------------------------------------------------------------

def _entzerren(bloecke, abstand, hoehe):
    """Löst Überdeckungen der Blöcke mit möglichst kleiner Abweichung vom Wunsch auf.

    Ein Block ist [oben, höhe, …]; `oben` trägt den Wunsch und danach die Lage. Blöcke, die
    sich drängen, bilden eine Gruppe; die Gruppe liegt lückenlos um den Schwerpunkt ihrer
    Wünsche. Alles bleibt zwischen 0 und `hoehe`; reicht die Höhe insgesamt nicht, wird von
    oben gestapelt, und der letzte Block ragt über `hoehe` hinaus.
    """
    # Abzüglich dessen, was davor liegt, heißt „keine Überdeckung“: Die Werte fallen nie.
    davor, versatz = 0, []
    for block in bloecke:
        versatz.append(davor)
        davor += block[1] + abstand
    gruppen = []   # [summe der Wünsche, anzahl]
    for block, weg in zip(bloecke, versatz):
        gruppen.append([block[0] - weg, 1])
        while len(gruppen) > 1 and (gruppen[-2][0] / gruppen[-2][1]
                                    > gruppen[-1][0] / gruppen[-1][1]):
            summe, anzahl = gruppen.pop()
            gruppen[-1][0] += summe
            gruppen[-1][1] += anzahl
    grenze = max(0, hoehe - (davor - abstand))
    nr = 0
    for summe, anzahl in gruppen:
        lage = round(min(max(summe / anzahl, 0), grenze))
        for _ in range(anzahl):
            bloecke[nr][0] = lage + versatz[nr]
            nr += 1


def _randbloecke(zeichen, breite, hoehe, rand, vorschlag_zeigen, einzug=0):
    """Die Blöcke der Randspalte, je Textzeile einer: [oben, höhe, zeilenmitte, einträge].

    `oben` und `zeilenmitte` zählen ab der Oberkante des Fotos; `zeilenmitte` ist die Höhe,
    auf der die Textzeile den rechten Rand des Fotos erreicht. Ein Eintrag ist (x, zeile,
    kürzel, farbe, vorschlag) mit x ab dem linken Rand der Spalte. Die Einträge stehen
    nebeneinander; reicht der Platz nicht, wird umbrochen. `einzug` hält links einen Streifen
    für Führungslinien frei.

    Jeder Block liegt mittig auf seiner Textzeile. Wird ein Block mit Vorschlägen höher als
    der Abstand zu den Nachbarzeilen, werden seine Vorschläge so gekürzt, dass alles in eine
    Zeile passt, und notfalls weggelassen; die Kürzel bleiben immer. Was sich dann noch
    überdeckt, verteilt `_entzerren`.
    """
    fett = schrift(_kuerzelgroesse(breite), True)
    klein = schrift(_vorschlaggroesse(breite))
    zeilenhoehe = round(_kuerzelgroesse(breite) * 1.3)
    innen = max(3, round(rand * 0.07))            # Abstand zu Trennlinie und Rand
    platz = rand - 2 * innen - einzug
    zwischen = round(_kuerzelgroesse(breite) * 0.55)   # zwischen zwei Einträgen
    luft = round(_kuerzelgroesse(breite) * 0.28)       # zwischen Kürzel und Vorschlag
    abstand = round(zeilenhoehe * 0.3)                 # zwischen zwei Blöcken, die sich drängen

    def setzen(textzeile, stufe):
        """Stufe 0: Vorschläge ganz; 1: gekürzt auf eine Zeile; 2: ohne. → (höhe, einträge)"""
        kuerzel = [kuerzen(_einzeilig(z["kategorie"]), fett, platz) for z in textzeile]
        weiten = [fett.getlength(k) for k in kuerzel]
        texte = [_einzeilig(z.get("vorschlag")) if vorschlag_zeigen and stufe < 2 else ""
                 for z in textzeile]
        # Stufe 1: Was die Kürzel übrig lassen, teilen sich die Vorschläge; kurze behalten
        # ihre Länge, die langen bekommen den Rest zu gleichen Teilen.
        rest = platz - sum(weiten) - zwischen * (len(kuerzel) - 1) - (luft + 1) * len(kuerzel)
        offen = len(texte)
        for laenge in sorted(klein.getlength(text) for text in texte):
            if laenge > rest / offen:
                break
            rest, offen = rest - laenge, offen - 1
        je_vorschlag = rest / offen if offen else float("inf")
        x, zeile, eintraege = 0, 0, []
        for z, k, weite, vorschlag in zip(textzeile, kuerzel, weiten, texte):
            if vorschlag:
                ganz = vorschlag
                frei = platz - weite - luft
                vorschlag = kuerzen(vorschlag, klein, min(frei, je_vorschlag) if stufe else frei)
                if stufe and vorschlag != ganz and len(vorschlag) < 4:
                    vorschlag = ""    # ein oder zwei Buchstaben mit „…“ sagen nichts
            if vorschlag:
                weite += luft + klein.getlength(vorschlag)
            if x > 0 and x + weite > platz:
                x, zeile = 0, zeile + 1
            eintraege.append((innen + einzug + round(x), zeile, k, farbe(z["kategorie"]),
                              vorschlag))
            x += weite + zwischen
        return (zeile + 1) * zeilenhoehe, eintraege

    zeilen, neigung = _textzeilen(zeichen)
    mitten = [min(max(hoehe_links + neigung * breite, 0), hoehe) for hoehe_links, _ in zeilen]
    bloecke = []
    for nr, (_, textzeile) in enumerate(zeilen):
        nachbarn = [abs(mitten[nr] - mitten[i]) for i in (nr - 1, nr + 1) if 0 <= i < len(zeilen)]
        frei = min(nachbarn) - abstand if nachbarn else float("inf")
        block_h, eintraege = setzen(textzeile, 0)
        for stufe in (1, 2) if vorschlag_zeigen else ():
            if block_h <= frei:
                break
            enger = setzen(textzeile, stufe)
            if enger[0] < block_h:
                block_h, eintraege = enger
        bloecke.append([round(mitten[nr] - block_h / 2), block_h, mitten[nr], eintraege])
    _entzerren(bloecke, abstand, hoehe)
    return bloecke


def _randspalte_setzen(zeichen, breite, hoehe, rand, vorschlag_zeigen):
    """Legt fest, wo in der Randspalte was steht.

    Gibt (einträge, klammern, führungen, benötigte Höhe) zurück; ein Eintrag ist (x,
    grundlinie, kürzel, farbe, vorschlag) mit x ab dem linken Rand der Spalte und der
    Grundlinie ab der Oberkante des Fotos. Die Blöcke legt `_randbloecke` fest. Eine Klammer
    (x, oben, unten) fasst die Zeilen eines umbrochenen Blocks am linken Rand zusammen. Eine
    Führung (x1, y1, x2, y2) verbindet die Höhe der Textzeile mit ihrem Block, wenn der Block
    um mehr als seine halbe Höhe von der Textzeile abgerückt ist. Nur wenn die Blöcke
    insgesamt nicht neben das Foto passen, ist die benötigte Höhe größer als die des Fotos.
    """
    zeilenhoehe = round(_kuerzelgroesse(breite) * 1.3)
    grundlinie = round(zeilenhoehe * 0.76)
    innen = max(3, round(rand * 0.07))

    def abgerueckt(bloecke):
        return [block for block in bloecke
                if abs(block[0] + block[1] / 2 - block[2]) > block[1] / 2]

    einzug = 0
    bloecke = _randbloecke(zeichen, breite, hoehe, rand, vorschlag_zeigen)
    if abgerueckt(bloecke):
        # Die Führungslinien brauchen Platz: Die Blöcke rücken um einen Streifen nach rechts.
        einzug = round(zeilenhoehe * 0.8)
        bloecke = _randbloecke(zeichen, breite, hoehe, rand, vorschlag_zeigen, einzug)
    benoetigt = max([hoehe] + [block[0] + block[1] + innen for block in bloecke[-1:]
                               if block[0] + block[1] > hoehe])
    gesetzt = [(x, oben + zeile * zeilenhoehe + grundlinie, kuerzel, f, vorschlag)
               for oben, _, _, eintraege in bloecke
               for x, zeile, kuerzel, f, vorschlag in eintraege]
    kante = round(zeilenhoehe * 0.15)
    klammer_x = einzug + round(innen * 0.45)
    klammern = [(klammer_x, oben + kante, oben + block_h - kante)
                for oben, block_h, _, _ in bloecke if block_h > zeilenhoehe]
    anfang = max(1, round(breite / 1000)) + 1       # gleich rechts der Trennlinie
    ende = max(anfang + 1, einzug + round(innen * 0.3))
    fuehrungen = [(anfang, round(zeilenmitte), ende, round(oben + block_h / 2))
                  for oben, block_h, zeilenmitte, _ in abgerueckt(bloecke)]
    return gesetzt, klammern, fuehrungen, benoetigt


def _randspalte_zeichnen(stift, eintraege, klammern, fuehrungen, breite, links, oben):
    fett = schrift(_kuerzelgroesse(breite), True)
    klein = schrift(_vorschlaggroesse(breite))
    luft = round(_kuerzelgroesse(breite) * 0.28)
    staerke = max(1, strichstaerke(breite) // 2)
    for x1, y1, x2, y2 in fuehrungen:
        stift.line([(links + x1, oben + y1), (links + x2, oben + y2)], fill=LINIE, width=staerke)
    for x, grundlinie, kuerzel, f, vorschlag in eintraege:
        stift.text((links + x, oben + grundlinie), kuerzel, font=fett, fill=f, anchor="ls")
        if vorschlag:
            stift.text((links + x + fett.getlength(kuerzel) + luft, oben + grundlinie),
                       vorschlag, font=klein, fill=GRAU, anchor="ls")
    for x, k_oben, k_unten in klammern:
        stift.rectangle([links + x, oben + k_oben, links + x + staerke - 1, oben + k_unten],
                        fill=LINIE)


# --- Zeichen im Text ------------------------------------------------------------------------

def _strichhoehe(z, strich, hindernisse):
    """Die Oberkante der Unterstreichung: knapp unter dem Rahmen.

    Beginnt unmittelbar darunter der Rahmen eines anderen Zeichens (die nächste Textzeile,
    etwa wenn der eigene Rahmen Unterlängen einschließt), rückt der Strich so weit nach oben,
    dass er diesen Rahmen nicht berührt, höchstens bis an die Unterkante des eigenen Rahmens.
    """
    unterkante = round(z["y"] + z["hoehe"])
    y = unterkante + strich
    for anderes in hindernisse:
        darunter = anderes is not z and anderes["y"] > _mitte(z)
        if (darunter and anderes["x"] < z["x"] + z["breite"]
                and anderes["x"] + anderes["breite"] > z["x"]):
            y = min(y, int(anderes["y"]) - strich)
    return max(y, unterkante - strich)


def _im_text_zeichnen(stift, zeichen, breite, hoehe, oben, hindernisse=()):
    """Unterstreichung je `wort`, Einfügezeichen je `luecke`; alles bleibt im Foto.

    `hindernisse` sind alle Rahmen der Seite: Eine Unterstreichung weicht dem Rahmen der
    nächsten Textzeile aus.
    """
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
            y = max(0, min(_strichhoehe(z, strich, hindernisse), hoehe - strich))
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
    eintraege, klammern, fuehrungen, spalte_h = _randspalte_setzen(fest, breite, hoehe, rand,
                                                                   vorschlag_zeigen)
    kasten_h = 0
    if uebersicht is not None:
        gesetzt, kasten_h, kasten = _uebersicht_setzen(uebersicht, breite, gesamtbreite)

    seite = Image.new("RGB", (gesamtbreite, kopf_h + spalte_h + kasten_h), WEISS)
    seite.paste(bild if bild.mode == "RGB" else bild.convert("RGB"), (0, kopf_h))
    stift = ImageDraw.Draw(seite)
    _im_text_zeichnen(stift, fest, breite, hoehe, kopf_h, zeichen)
    stift.rectangle([breite, kopf_h, breite + max(1, round(breite / 1000)) - 1,
                     kopf_h + spalte_h - 1], fill=LINIE)
    _randspalte_zeichnen(stift, eintraege, klammern, fuehrungen, breite, breite, kopf_h)
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
    return kategorien_ordnen(zahl, eigene)


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


# Was Pillow bei einem fehlenden, abgeschnittenen oder sonst defekten Foto auslöst.
FOTO_FEHLER = (OSError, ValueError, SyntaxError, Image.DecompressionBombError)


def _foto_laden(pfad, vorschlag_zeigen, uebersicht):
    """Lädt das Foto aufrecht und in der Größe für die Ausgabe: (bild, faktor).

    Wird ein JPEG ohnehin verkleinert, entpackt Pillow es gleich in halber, viertel oder
    achtel Größe (`draft`), solange es dabei nicht kleiner wird als das Ziel. Das spart bei
    sehr großen Fotos Arbeitsspeicher und Zeit; die Seite sieht gleich aus.
    """
    with Image.open(pfad) as roh:
        breite, hoehe = roh.size
        gedreht = roh.getexif().get(0x0112) in (5, 6, 7, 8)   # liegt auf der Seite
        if gedreht:
            breite, hoehe = hoehe, breite
        ziel = _fotobreite(breite, hoehe, vorschlag_zeigen, uebersicht)
        ziel_h = max(1, round(hoehe * ziel / breite))
        if ziel < breite and roh.format == "JPEG":
            roh.draft("RGB", (ziel_h, ziel) if gedreht else (ziel, ziel_h))
        foto = ImageOps.exif_transpose(roh).convert("RGB")
    if ziel >= breite:
        return foto, 1
    klein = foto.resize((ziel, ziel_h), Image.LANCZOS)
    foto.close()
    return klein, ziel / breite


def _skaliert(zeichen, faktor):
    if faktor == 1:
        return zeichen
    return [{**z, **{feld: z[feld] * faktor for feld in ("x", "y", "breite", "hoehe")}}
            for z in zeichen]


def seitenbilder(speicher, aufgabe, arbeit, eigene=None):
    """Erzeugt nacheinander die Seiten einer Arbeit als Bilder für das PDF.

    `arbeit` ist eine Arbeit, wie `speicher.arbeit` sie liefert. Jede Seite trägt den Kopf
    mit Aufgabentitel, Kürzel der Arbeit und Seitenzahl, die letzte die Fehlerübersicht.
    Keine Kante ist länger als MAX_KANTE. `AusgabeFehler`, wenn das Foto einer Seite fehlt
    oder nicht lesbar ist.
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
        except FOTO_FEHLER as fehler:
            raise AusgabeFehler(f"Das Foto zu Seite {nummer} der Arbeit {arbeit['kuerzel']} fehlt "
                                "oder ist nicht lesbar. Das PDF wurde nicht erzeugt.") from fehler
        kopf = f"{aufgabe['titel']} · Arbeit {arbeit['kuerzel']} · Seite {nummer} von {seitenzahl}"
        bild = seite_zeichnen(foto, _skaliert(seite["zeichen"], faktor), vorschlag_zeigen, kopf,
                              uebersicht)
        foto.close()
        del foto
        if max(bild.size) > MAX_KANTE:   # etwa eine übervolle Randspalte
            bild.thumbnail((MAX_KANTE, MAX_KANTE), Image.LANCZOS)
        yield bild
        del bild   # die Seite ist geschrieben; nichts hält sie bis zur nächsten fest


def _seite_anhaengen(ziel, bild, titel, erste):
    """Schreibt ein Seitenbild als nächste Seite an das Ende des PDF in `ziel`."""
    ziel.seek(0)   # Pillow liest beim Anhängen das bisherige PDF von vorn
    angaben = {"title": titel} if erste else {}   # der Titel bleibt beim Anhängen erhalten
    bild.save(ziel, "PDF", resolution=AUFLOESUNG, quality=JPEG_QUALITAET, append=not erste,
              **angaben)


def _als_pdf(bilder, titel):
    """Fasst die Seitenbilder zu einem PDF zusammen, je Seite ein Bild.

    `bilder` wird nacheinander abgerufen: Jede Seite wird sofort an das PDF angehängt und
    danach freigegeben. Im Arbeitsspeicher liegt so immer nur ein Seitenbild, nicht der ganze
    Stapel. Ohne Bilder ist das Ergebnis leer.
    """
    puffer = io.BytesIO()
    erste = True
    for bild in bilder:
        _seite_anhaengen(puffer, bild, titel, erste)
        bild.close()
        del bild
        erste = False
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
    return _als_pdf(seitenbilder(speicher, aufgabe, arbeit),
                    f"{aufgabe['titel']} – Arbeit {arbeit['kuerzel']}")


# Höchstens ein Sammel-PDF zur selben Zeit je Prozess: Eine zweite Anfrage wartet, statt den
# Arbeitsspeicher ein zweites Mal zu belegen.
_SAMMEL_SPERRE = threading.Lock()


def aufgabe_als_pdf(speicher, aufgabe_id):
    """Das Sammel-PDF einer Aufgabe: (bytes, enthalten, fehlend).

    Enthält alle bestätigten Arbeiten in Stapelreihenfolge, jede ab einer neuen Seite.
    `enthalten` und `fehlend` zählen die aufgenommenen und die nicht bestätigten Arbeiten.
    `RegelFehler`, wenn keine Arbeit bestätigt ist.

    Die Seiten werden einzeln gezeichnet und sofort an das PDF angehängt; im Arbeitsspeicher
    liegen das wachsende PDF und ein Seitenbild. Es entsteht immer nur ein Sammel-PDF zur
    selben Zeit.
    """
    with _SAMMEL_SPERRE:
        aufgabe = speicher.aufgabe(aufgabe_id)
        reihe = speicher.arbeiten(aufgabe_id) if aufgabe else []
        eigene = speicher.kuerzel()
        enthalten = 0

        def seiten():
            nonlocal enthalten
            for eintrag in reihe:
                if eintrag["bestaetigt_am"] is None:
                    continue
                arbeit = _bestaetigte_arbeit(speicher, eintrag["id"])   # ein Stand je Arbeit
                if arbeit is None:
                    continue
                enthalten += 1
                yield from seitenbilder(speicher, aufgabe, arbeit, eigene)

        # Der Titel im PDF nennt nur die Aufgabe: Ein weitergegebenes PDF verrät nicht, wie
        # viele Arbeiten fehlen. Die Zahlen stehen im Dateinamen des Downloads.
        pdf = _als_pdf(seiten(), aufgabe["titel"] if aufgabe else "")
    if not enthalten:
        raise RegelFehler("In dieser Aufgabe ist noch keine Korrektur bestätigt. Das Sammel-PDF "
                          "enthält nur Arbeiten nach „Korrektur gesamt bestätigen“.")
    return pdf, enthalten, len(reihe) - enthalten
