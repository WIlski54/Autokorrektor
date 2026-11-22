"""Startet die Web-App des Korrektors und öffnet den Browser.

Start: python start.py   ->   http://127.0.0.1:5001
Mit KORREKTOR_KEIN_BROWSER=1 bleibt der Browser zu.
"""
import os
import threading
import tomllib
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

from webapp import app_erzeugen

WURZEL = Path(__file__).parent
ADRESSE, PORT = "127.0.0.1", 5001


def app_bauen():
    """Lädt Schlüssel und Einstellungen, erzeugt die App und nimmt offene Analysen wieder auf."""
    load_dotenv(WURZEL / ".env")
    with open(WURZEL / "einstellungen.toml", "rb") as datei:
        einst = tomllib.load(datei)
    app = app_erzeugen(WURZEL / "daten", einst)
    app.extensions["warteschlange"].wiederaufnehmen()
    return app


def main():
    app = app_bauen()
    url = f"http://{ADRESSE}:{PORT}/"
    if os.environ.get("KORREKTOR_KEIN_BROWSER") != "1":
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    print(f"Korrektor läuft unter {url} (Beenden mit Strg+C)")
    app.run(host=ADRESSE, port=PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
