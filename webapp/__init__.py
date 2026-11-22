"""Web-App des Korrektors: Flask-App mit Speicher und Warteschlange verdrahten."""
import secrets

from flask import Flask

from webapp.analyse import seite_analysieren
from webapp.speicher import Speicher
from webapp.warteschlange import Warteschlange

MAX_ANFRAGE = 200 * 1024 * 1024  # Bytes je Anfrage
MAX_DATEI = 25 * 1024 * 1024     # Bytes je hochgeladener Datei


def app_erzeugen(datenordner, einst, analysieren=None):
    """Erzeugt die App.

    `einst` ist das Wörterbuch aus `einstellungen.toml`. `analysieren(seite_id) -> dict`
    lässt sich für Tests ersetzen; sonst wird das Verfahren der Aufgabe aufgerufen.
    Speicher und Warteschlange hängen unter `app.extensions["speicher"]` und
    `app.extensions["warteschlange"]`.
    """
    app = Flask(__name__, template_folder="vorlagen", static_folder="statisch",
                static_url_path="/statisch")
    app.config["MAX_CONTENT_LENGTH"] = MAX_ANFRAGE
    app.config["MAX_DATEI"] = MAX_DATEI
    app.config["EINST"] = einst
    app.secret_key = secrets.token_hex(32)  # nur für Meldungen nach einer Weiterleitung

    speicher = Speicher(datenordner)
    if analysieren is None:
        def analysieren(seite_id):
            return seite_analysieren(speicher, seite_id, einst)
    app.extensions["speicher"] = speicher
    app.extensions["warteschlange"] = Warteschlange(speicher, analysieren)

    from webapp.routen import seiten
    app.register_blueprint(seiten)
    return app
