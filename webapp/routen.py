"""Alle Seiten und JSON-Schnittstellen der Etappe 1."""
from urllib.parse import urlsplit

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, url_for)
from werkzeug.exceptions import HTTPException

from webapp.verfahren import VERFAHREN, VOREINSTELLUNG, anzeigename, hindernis

seiten = Blueprint("seiten", __name__)

KATEGORIEN = (("R", "Rechtschreibung"), ("Z", "Zeichensetzung"), ("Gr", "Grammatik"))


def _speicher():
    return current_app.extensions["speicher"]


def _schlange():
    return current_app.extensions["warteschlange"]


def _aufgabe_oder_404(aufgabe_id):
    aufgabe = _speicher().aufgabe(aufgabe_id)
    if aufgabe is None:
        abort(404)
    return aufgabe


def _hindernis(aufgabe):
    return hindernis(aufgabe["verfahren"], current_app.config["EINST"])


@seiten.app_context_processor
def _fuer_vorlagen():
    return {"anzeigename": anzeigename}


@seiten.before_app_request
def _fremde_herkunft_ablehnen():
    """Die App hat keinen Login: Schreibende Anfragen fremder Webseiten werden abgewiesen."""
    herkunft = request.headers.get("Origin")
    if request.method == "POST" and herkunft and urlsplit(herkunft).netloc != request.host:
        abort(403)


@seiten.app_errorhandler(HTTPException)
def _fehlerseite(fehler):
    texte = {
        403: "Diese Anfrage ist nicht erlaubt.",
        404: "Diese Seite gibt es nicht (mehr).",
        405: "Diese Anfrage ist hier nicht vorgesehen.",
        413: "Die Anfrage ist zu groß. Bitte weniger Fotos auf einmal hochladen.",
    }
    text = texte.get(fehler.code, fehler.description)
    if request.accept_mimetypes.best == "application/json":
        return {"fehler": text}, fehler.code
    return render_template("fehler.html", text=text, code=fehler.code), fehler.code


# --- Aufgabenliste und Aufgabenformular ---------------------------------------------------

@seiten.get("/")
def aufgaben():
    return render_template("aufgaben.html", aufgaben=_speicher().aufgaben())


def _formular_lesen():
    """Liest das Aufgabenformular; gibt (werte, fehler) zurück."""
    werte = {
        "titel": request.form.get("titel", "").strip(),
        "fach": request.form.get("fach", "").strip(),
        "jahrgang": request.form.get("jahrgang", "").strip(),
        "kategorien": request.form.getlist("kategorien"),
        "verfahren": request.form.get("verfahren", ""),
        "vorschlag_in_ausgabe": bool(request.form.get("vorschlag_in_ausgabe")),
    }
    fehler = []
    if not werte["titel"]:
        fehler.append("Bitte einen Titel eintragen.")
    if not werte["fach"]:
        fehler.append("Bitte ein Fach eintragen.")
    try:
        jahrgang = int(werte["jahrgang"])
        if not 1 <= jahrgang <= 13:
            raise ValueError
        werte["jahrgang"] = jahrgang
    except ValueError:
        fehler.append("Bitte als Jahrgang eine Zahl von 1 bis 13 eintragen.")
    erlaubt = [kuerzel for kuerzel, _ in KATEGORIEN]
    if not werte["kategorien"]:
        fehler.append("Bitte mindestens eine Kategorie einschalten.")
    elif set(werte["kategorien"]) - set(erlaubt):
        fehler.append("Unbekannte Kategorie. Möglich sind R, Z und Gr.")
    else:
        werte["kategorien"] = [k for k in erlaubt if k in werte["kategorien"]]
    if werte["verfahren"] not in VERFAHREN:
        fehler.append("Bitte ein Verfahren aus der Liste wählen.")
    return werte, fehler


def _formular_zeigen(werte, fehler=(), aufgabe=None, status=200):
    hat_arbeiten = bool(aufgabe and _speicher().arbeiten(aufgabe["id"]))
    return render_template("aufgabe_formular.html", werte=werte, fehler=fehler,
                           aufgabe=aufgabe, hat_arbeiten=hat_arbeiten,
                           kategorien=KATEGORIEN, verfahren=VERFAHREN), status


@seiten.route("/aufgabe/neu", methods=["GET", "POST"])
def aufgabe_neu():
    if request.method == "GET":
        return _formular_zeigen({
            "titel": "", "fach": "Deutsch", "jahrgang": "", "verfahren": VOREINSTELLUNG,
            "kategorien": [kuerzel for kuerzel, _ in KATEGORIEN],
            "vorschlag_in_ausgabe": False})
    werte, fehler = _formular_lesen()
    if fehler:
        return _formular_zeigen(werte, fehler, status=400)
    aufgabe_id = _speicher().aufgabe_anlegen(**werte)
    return redirect(url_for("seiten.hochladen", aufgabe_id=aufgabe_id))


@seiten.route("/aufgabe/<int:aufgabe_id>/bearbeiten", methods=["GET", "POST"])
def aufgabe_bearbeiten(aufgabe_id):
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    if request.method == "GET":
        return _formular_zeigen(aufgabe, aufgabe=aufgabe)
    werte, fehler = _formular_lesen()
    if fehler:
        return _formular_zeigen(werte, fehler, aufgabe=aufgabe, status=400)
    _speicher().aufgabe_aendern(aufgabe_id, **werte)
    flash("Die Einstellungen der Aufgabe sind gespeichert.", "erfolg")
    return redirect(url_for("seiten.stapel", aufgabe_id=aufgabe_id))


@seiten.post("/aufgabe/<int:aufgabe_id>/loeschen")
def aufgabe_loeschen(aufgabe_id):
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    _speicher().aufgabe_loeschen(aufgabe_id)
    flash(f"Die Aufgabe „{aufgabe['titel']}“ wurde mit allen Fotos gelöscht.", "erfolg")
    return redirect(url_for("seiten.aufgaben"))


# --- Stapelansicht ------------------------------------------------------------------------

@seiten.get("/aufgabe/<int:aufgabe_id>")
def stapel(aufgabe_id):
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    return render_template("stapel.html", aufgabe=aufgabe)


# --- Bilder -------------------------------------------------------------------------------

def _bild_antwort(eintrag):
    """Liefert das Foto eines Ablage-Eintrags oder einer Seite; `?b=<Breite>` als Vorschau."""
    if eintrag is None:
        abort(404)
    breite = request.args.get("b", type=int)
    if breite is not None:
        breite = max(40, min(breite, 4000))
    # Die Bilddatei ändert sich nie; die Kennung erspart dem Browser das erneute Laden.
    kennung = f"{eintrag['bilddatei']}-{breite or 'voll'}"
    if request.if_none_match.contains(kennung):
        antwort = Response(status=304)
    else:
        daten = _speicher().bilddaten(eintrag["bilddatei"], breite)
        if daten is None:
            abort(404)
        antwort = Response(daten, mimetype="image/jpeg")
    antwort.set_etag(kennung)
    antwort.headers["Cache-Control"] = "private, no-cache"
    return antwort


@seiten.get("/bild/seite/<int:seite_id>")
def bild_seite(seite_id):
    return _bild_antwort(_speicher().seite(seite_id))


@seiten.get("/bild/ablage/<int:ablage_id>")
def bild_ablage(ablage_id):
    return _bild_antwort(_speicher().ablage_eintrag(ablage_id))


# --- Hochladen und Zuordnen ---------------------------------------------------------------

def _megabyte(zahl_bytes):
    return f"{zahl_bytes / (1024 * 1024):.0f} MB"


def _dateien_lesen():
    """Liest die hochgeladenen Dateien; gibt ([(dateiname, daten)], [abgelehnt]) zurück.

    Zu große Dateien werden mit Dateiname und Grund abgelehnt, die übrigen angenommen.
    """
    grenze = current_app.config["MAX_DATEI"]
    gelesen, abgelehnt = [], []
    for datei in request.files.getlist("fotos"):
        if not datei.filename:
            continue
        daten = datei.read()
        if len(daten) > grenze:
            abgelehnt.append({"dateiname": datei.filename,
                              "grund": f"zu groß (höchstens {_megabyte(grenze)} je Datei)"})
        else:
            gelesen.append((datei.filename, daten))
    return gelesen, abgelehnt


@seiten.get("/aufgabe/<int:aufgabe_id>/hochladen")
def hochladen(aufgabe_id):
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    arbeiten = _speicher().arbeiten(aufgabe_id)
    daten = {
        "eintraege": [{"id": e["id"], "neue_arbeit": e["neue_arbeit"]}
                      for e in _speicher().ablage(aufgabe_id)],
        "naechste_nummer": max((a["reihenfolge"] for a in arbeiten), default=0) + 1,
        "max_datei": current_app.config["MAX_DATEI"],
        "url_hochladen": url_for("seiten.ablage_hochladen", aufgabe_id=aufgabe_id),
        "url_ordnen": url_for("seiten.ablage_ordnen", aufgabe_id=aufgabe_id),
        "url_bild": url_for("seiten.bild_ablage", ablage_id=0)[:-1],  # Nummer hängt das Skript an
    }
    return render_template("zuordnen.html", aufgabe=aufgabe, daten=daten,
                           zahl_arbeiten=len(arbeiten), hindernis=_hindernis(aufgabe))


@seiten.post("/aufgabe/<int:aufgabe_id>/ablage")
def ablage_hochladen(aufgabe_id):
    _aufgabe_oder_404(aufgabe_id)
    gelesen, abgelehnt = _dateien_lesen()
    if not gelesen and not abgelehnt:
        return {"fehler": "Es wurde keine Datei übertragen."}, 400
    angenommen = []
    for dateiname, daten in gelesen:
        try:
            ablage_id = _speicher().bild_ablegen(aufgabe_id, dateiname, daten)
        except ValueError:
            abgelehnt.append({"dateiname": dateiname,
                              "grund": "kein lesbares Bild (erlaubt sind JPG, PNG und WebP)"})
            continue
        eintrag = _speicher().ablage_eintrag(ablage_id)
        angenommen.append({"id": ablage_id, "dateiname": dateiname,
                           "breite": eintrag["breite"], "hoehe": eintrag["hoehe"]})
    return {"angenommen": angenommen, "abgelehnt": abgelehnt}


@seiten.post("/aufgabe/<int:aufgabe_id>/ablage/ordnen")
def ablage_ordnen(aufgabe_id):
    """Speichert Reihenfolge und Trennmarken; nicht genannte Fotos werden entfernt."""
    _aufgabe_oder_404(aufgabe_id)
    inhalt = request.get_json(silent=True)
    eintraege = inhalt.get("eintraege") if isinstance(inhalt, dict) else None
    if not isinstance(eintraege, list):
        return {"fehler": "Die Angaben zur Reihenfolge fehlen."}, 400
    vorhanden = {e["id"] for e in _speicher().ablage(aufgabe_id)}
    sauber, gesehen = [], set()
    for eintrag in eintraege:
        nr = eintrag.get("id") if isinstance(eintrag, dict) else None
        if type(nr) is not int or nr not in vorhanden or nr in gesehen:
            return {"fehler": "Die Angaben zur Reihenfolge passen nicht zur Ablage. "
                              "Bitte die Seite neu laden."}, 400
        gesehen.add(nr)
        sauber.append({"id": nr, "neue_arbeit": bool(eintrag.get("neue_arbeit", True))})
    _speicher().ablage_ordnen(aufgabe_id, sauber)
    arbeiten = sum(1 for platz, e in enumerate(sauber) if platz == 0 or e["neue_arbeit"])
    return {"ok": True, "fotos": len(sauber), "arbeiten": arbeiten}


@seiten.post("/aufgabe/<int:aufgabe_id>/analyse-starten")
def analyse_starten(aufgabe_id):
    """Wandelt die Ablage in Arbeiten um und reiht alle Seiten ein."""
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    zurueck = redirect(url_for("seiten.hochladen", aufgabe_id=aufgabe_id))
    grund = _hindernis(aufgabe)
    if grund:
        flash(f"Die Analyse wurde nicht gestartet. {grund}", "fehler")
        return zurueck
    if not _speicher().ablage(aufgabe_id):
        flash("Es liegen noch keine Fotos in der Ablage.", "fehler")
        return zurueck
    for seite_id in _speicher().ablage_zu_arbeiten(aufgabe_id):
        _schlange().einreihen(seite_id)
    return redirect(url_for("seiten.stapel", aufgabe_id=aufgabe_id))


@seiten.post("/aufgabe/<int:aufgabe_id>/arbeit")
def arbeit_hinzufuegen(aufgabe_id):
    """Legt aus den übertragenen Fotos eine einzelne Arbeit an und reiht ihre Seiten ein."""
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    zurueck = redirect(url_for("seiten.stapel", aufgabe_id=aufgabe_id))
    grund = _hindernis(aufgabe)
    if grund:
        flash(f"Die Arbeit wurde nicht hinzugefügt. {grund}", "fehler")
        return zurueck
    gelesen, abgelehnt = _dateien_lesen()
    if abgelehnt:
        namen = ", ".join(f"„{a['dateiname']}“ ({a['grund']})" for a in abgelehnt)
        flash(f"Die Arbeit wurde nicht hinzugefügt: {namen}.", "fehler")
        return zurueck
    if not gelesen:
        flash("Es wurde kein Foto ausgewählt.", "fehler")
        return zurueck
    try:
        seiten_ids = _speicher().arbeit_anlegen(aufgabe_id, gelesen)
    except ValueError as fehler:
        flash(f"Die Arbeit wurde nicht hinzugefügt ({fehler}). "
              "Erlaubt sind JPG, PNG und WebP.", "fehler")
        return zurueck
    for seite_id in seiten_ids:
        _schlange().einreihen(seite_id)
    return zurueck
