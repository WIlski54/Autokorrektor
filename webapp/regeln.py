"""Zustandsregeln für Zeichen und Gesamtbestätigung (Spezifikation, Abschnitt 4).

Nur reine Funktionen: kein Speicher, kein Flask. Ein Zeichen ist ein `dict` mit
`kategorie, typ, x, y, breite, hoehe, gelesen, vorschlag, herkunft, status, bestaetigt_wie`.
Die Übergänge geben die zu setzenden Felder als `dict` zurück und werfen `RegelFehler`
mit einer Meldung für die Lehrkraft, wenn der Übergang nicht zulässig ist.
"""

FESTE_KUERZEL = ("R", "Z", "Gr")   # die Kategorien, die auch die KI vorschlägt
TYPEN = ("wort", "luecke")
MINDESTKANTE = 4                    # Pixel; kleinere Rahmen lassen sich nicht mehr greifen
REST_BESTAETIGEN = {"status": "bestaetigt", "bestaetigt_wie": "gesammelt"}

KUERZEL_LAENGE = 4
BEZEICHNUNG_LAENGE = 40
ARBEITSKUERZEL_LAENGE = 20

_NICHT_FERTIG = {
    "neu": "ist noch nicht analysiert",
    "wartet": "wird noch analysiert (die Analyse läuft)",
    "laeuft": "wird noch analysiert (die Analyse läuft)",
    "fehlgeschlagen": "konnte nicht analysiert werden (die Analyse ist fehlgeschlagen)",
}


class RegelFehler(ValueError):
    """Ein unzulässiger Übergang oder Wert; die Meldung ist für die Lehrkraft gedacht."""


def _ist_ki(zeichen):
    return zeichen["herkunft"] == "ki"


# --- Bestätigen, Verwerfen, Zurückholen ----------------------------------------------------

def einzeln_bestaetigen(zeichen):
    if not _ist_ki(zeichen):
        raise RegelFehler("Eigene Zeichen gelten schon als bestätigt.")
    if zeichen["status"] == "bestaetigt":
        raise RegelFehler("Dieser Vorschlag ist bereits bestätigt.")
    if zeichen["status"] == "verworfen":
        raise RegelFehler("Dieser Vorschlag ist verworfen. Bitte erst zurückholen.")
    return {"status": "bestaetigt", "bestaetigt_wie": "einzeln"}


def verwerfen(zeichen):
    if not _ist_ki(zeichen):
        raise RegelFehler("Eigene Zeichen werden gelöscht, nicht verworfen.")
    if zeichen["status"] == "verworfen":
        raise RegelFehler("Dieser Vorschlag ist bereits verworfen.")
    return {"status": "verworfen", "bestaetigt_wie": None}


def zurueckholen(zeichen):
    if not _ist_ki(zeichen):
        raise RegelFehler("Eigene Zeichen lassen sich nicht zurückholen, nur ändern oder löschen.")
    if zeichen["status"] == "offen":
        raise RegelFehler("Dieser Vorschlag ist bereits offen.")
    return {"status": "offen", "bestaetigt_wie": None}


# --- Ändern und Verschieben ------------------------------------------------------------------

def _kuerzel_pruefen(kategorie, erlaubte):
    if not isinstance(kategorie, str) or kategorie not in erlaubte:
        raise RegelFehler(f"Das Kürzel „{kategorie}“ gibt es nicht. Möglich sind: "
                          f"{', '.join(_geordnet(erlaubte))}.")


def _geordnet(erlaubte):
    feste = [k for k in FESTE_KUERZEL if k in erlaubte]
    return feste + sorted(set(erlaubte) - set(feste), key=str.casefold)


def _nicht_verworfen(zeichen):
    if zeichen["status"] == "verworfen":
        raise RegelFehler("Dieser Vorschlag ist verworfen. Bitte erst zurückholen.")


def aendern(zeichen, kategorie=None, vorschlag=None, *, erlaubte):
    """Kürzel und/oder Vorschlag ändern; `None` heißt: dieses Feld nicht anfassen.

    Ohne tatsächliche Änderung kommt `{}` zurück, ein offenes Zeichen bleibt dann offen.
    Das bisherige Kürzel darf stehen bleiben, auch wenn es inzwischen aus der Liste der
    eigenen Kürzel entfernt wurde.
    """
    _nicht_verworfen(zeichen)
    felder = {}
    if kategorie is not None and kategorie != zeichen["kategorie"]:
        _kuerzel_pruefen(kategorie, erlaubte)
        felder["kategorie"] = kategorie
    if vorschlag is not None and vorschlag != zeichen["vorschlag"]:
        felder["vorschlag"] = vorschlag
    if felder and _ist_ki(zeichen):
        felder.update(status="bestaetigt", bestaetigt_wie="geaendert")
    return felder


def _klemmen(x, y, breite, hoehe, bildgroesse):
    """Rahmen mit mindestens MINDESTKANTE je Kante, vollständig im Bild."""
    bildbreite, bildhoehe = bildgroesse
    breite = min(max(breite, MINDESTKANTE), max(bildbreite, MINDESTKANTE))
    hoehe = min(max(hoehe, MINDESTKANTE), max(bildhoehe, MINDESTKANTE))
    x = min(max(x, 0), max(bildbreite - breite, 0))
    y = min(max(y, 0), max(bildhoehe - hoehe, 0))
    return {"x": x, "y": y, "breite": breite, "hoehe": hoehe}


def verschieben(zeichen, x, y, breite, hoehe, bildgroesse):
    """Neuer Rahmen, ins Bild geklemmt; der Status bleibt unberührt.

    `bildgroesse` ist (Breite, Höhe) der Seite in Pixeln. Liegt der Rahmen danach genau
    dort, wo er war, kommt `{}` zurück.
    """
    _nicht_verworfen(zeichen)
    rahmen = _klemmen(x, y, breite, hoehe, bildgroesse)
    if all(rahmen[feld] == zeichen[feld] for feld in rahmen):
        return {}
    return rahmen


# --- Eigene Zeichen ----------------------------------------------------------------------------

def neues_handzeichen(kategorie, typ, x, y, breite, hoehe, vorschlag, erlaubte, bildgroesse):
    """Ein vollständiges, von Hand gesetztes Zeichen (gilt sofort als bestätigt)."""
    if not kategorie or not isinstance(kategorie, str):
        raise RegelFehler("Bitte ein Kürzel für das Zeichen wählen.")
    if kategorie not in erlaubte:
        raise RegelFehler(f"Das Kürzel „{kategorie}“ gibt es nicht. Bitte ein Kürzel aus der "
                          f"Liste wählen: {', '.join(_geordnet(erlaubte))}.")
    if typ not in TYPEN:
        raise RegelFehler("Die Art des Zeichens ist unbekannt. Möglich sind ein markiertes "
                          "Wort oder ein fehlendes Zeichen.")
    return {"kategorie": kategorie, "typ": typ, **_klemmen(x, y, breite, hoehe, bildgroesse),
            "gelesen": "", "vorschlag": vorschlag or "",
            "herkunft": "hand", "status": "bestaetigt", "bestaetigt_wie": None}


def loeschbar(zeichen):
    if _ist_ki(zeichen):
        raise RegelFehler("KI-Vorschläge werden verworfen, nicht gelöscht.")
    return True


# --- Rest bestätigen, Gesamtbestätigung, Zahlen --------------------------------------------------

def offene(zeichenliste):
    """Die ids der offenen Zeichen; „Rest bestätigen“ setzt auf sie REST_BESTAETIGEN."""
    return [z["id"] for z in zeichenliste if z["status"] == "offen"]


def unfertige_seite(seiten):
    """Nennt die erste Seite, die nicht fertig analysiert ist, als Satz; sonst ""."""
    for nummer, seite in enumerate(seiten, start=1):
        if seite["analyse_status"] != "fertig":
            warum = _NICHT_FERTIG.get(seite["analyse_status"], "ist noch nicht fertig analysiert")
            return f"Seite {seite.get('nummer', nummer)} {warum}."
    return ""


def bestaetigbar(seiten):
    """Ob sich die Arbeit insgesamt bestätigen lässt: (True, "") oder (False, Grund).

    `seiten` ist die Liste der Seiten mit `analyse_status` und `zeichen`; statt der
    Zeichenliste genügt auch die Zahl `offen`.
    """
    if not seiten:
        return False, "Die Arbeit hat keine Seiten."
    grund = unfertige_seite(seiten)
    if grund:
        return False, grund
    zahl = sum(len(offene(seite["zeichen"])) if "zeichen" in seite else seite["offen"]
               for seite in seiten)
    if zahl == 1:
        return False, "Noch 1 Vorschlag ist offen."
    if zahl:
        return False, f"Noch {zahl} Vorschläge sind offen."
    return True, ""


def zahlen(zeichenliste):
    """Die fünf Zahlen der Gesamtbestätigung."""
    ergebnis = {"einzeln": 0, "gesammelt": 0, "geaendert": 0, "verworfen": 0, "hand": 0}
    for z in zeichenliste:
        if z["herkunft"] == "hand":
            ergebnis["hand"] += 1
        elif z["status"] == "verworfen":
            ergebnis["verworfen"] += 1
        elif z["status"] == "bestaetigt" and z["bestaetigt_wie"] in ergebnis:
            ergebnis[z["bestaetigt_wie"]] += 1
    return ergebnis


# --- Kürzel ----------------------------------------------------------------------------------------

def erlaubte_kuerzel(eigene):
    """Die Menge der zulässigen Kürzel: R, Z, Gr und die eigenen `[{kuerzel, bezeichnung}]`."""
    return set(FESTE_KUERZEL) | {eintrag["kuerzel"] for eintrag in eigene}


def kuerzelliste_pruefen(liste):
    """Prüft die Liste eigener Kürzel und gibt sie bereinigt zurück.

    Kürzel: 1 bis 4 Buchstaben, eindeutig ohne Beachtung der Groß-/Kleinschreibung,
    nicht R, Z oder Gr. Bezeichnung: 1 bis 40 Zeichen.
    """
    fest = {k.casefold(): k for k in FESTE_KUERZEL}
    gesehen, sauber = set(), []
    for eintrag in liste:
        kuerzel = eintrag.get("kuerzel") if isinstance(eintrag, dict) else None
        if not isinstance(kuerzel, str) or not kuerzel.strip():
            raise RegelFehler("Bitte zu jeder Bezeichnung ein Kürzel eintragen.")
        kuerzel = kuerzel.strip()
        if not kuerzel.isalpha():
            raise RegelFehler(f"Das Kürzel „{kuerzel}“ darf nur aus Buchstaben bestehen.")
        if len(kuerzel) > KUERZEL_LAENGE:
            raise RegelFehler(f"Das Kürzel „{kuerzel}“ ist zu lang. Erlaubt sind höchstens "
                              f"{KUERZEL_LAENGE} Buchstaben.")
        if kuerzel.casefold() in fest:
            raise RegelFehler(f"„{fest[kuerzel.casefold()]}“ ist fest vergeben und kann kein "
                              "eigenes Kürzel sein. R, Z und Gr gibt es immer.")
        if kuerzel.casefold() in gesehen:
            raise RegelFehler(f"Das Kürzel „{kuerzel}“ kommt doppelt vor. Groß- und "
                              "Kleinschreibung unterscheiden zwei Kürzel nicht.")
        bezeichnung = eintrag.get("bezeichnung")
        if not isinstance(bezeichnung, str) or not bezeichnung.strip():
            raise RegelFehler(f"Bitte zum Kürzel „{kuerzel}“ eine Bezeichnung eintragen.")
        bezeichnung = bezeichnung.strip()
        if len(bezeichnung) > BEZEICHNUNG_LAENGE:
            raise RegelFehler(f"Die Bezeichnung zum Kürzel „{kuerzel}“ ist zu lang. Erlaubt "
                              f"sind höchstens {BEZEICHNUNG_LAENGE} Zeichen.")
        gesehen.add(kuerzel.casefold())
        sauber.append({"kuerzel": kuerzel, "bezeichnung": bezeichnung})
    return sauber


def arbeitskuerzel_pruefen(kuerzel):
    """Das Kürzel einer Arbeit ohne Rand-Leerzeichen; 1 bis 20 Zeichen."""
    text = kuerzel.strip() if isinstance(kuerzel, str) else ""
    if not 1 <= len(text) <= ARBEITSKUERZEL_LAENGE:
        raise RegelFehler("Das Kürzel der Arbeit braucht mindestens 1 und höchstens "
                          f"{ARBEITSKUERZEL_LAENGE} Zeichen.")
    return text
