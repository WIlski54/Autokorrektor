"""Alle Seiten und JSON-Schnittstellen der Etappe 1."""
from urllib.parse import urlsplit

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   url_for)
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


# --- Hochladen und Zuordnen ---------------------------------------------------------------

@seiten.get("/aufgabe/<int:aufgabe_id>/hochladen")
def hochladen(aufgabe_id):
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    return render_template("zuordnen.html", aufgabe=aufgabe)
