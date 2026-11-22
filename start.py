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
from webapp.sperre import sperre_belegen
from webapp.verfahren import hindernis

WURZEL = Path(__file__).parent
ADRESSE, PORT = "127.0.0.1", 5001


def einstellungen_laden(wurzel):
    """Liest `einstellungen.toml`; endet mit einer klaren Meldung, wenn sie fehlt."""
    pfad = wurzel / "einstellungen.toml"
    try:
        with open(pfad, "rb") as datei:
            return tomllib.load(datei)
    except FileNotFoundError:
        raise SystemExit(
            f"Die Datei einstellungen.toml fehlt im Ordner {wurzel}. Ohne sie kann der "
            "Korrektor nicht starten. Bitte die Datei aus dem Projekt wiederherstellen; sie "
            "nennt die längste Bildkante (max_kante) und die Modelle.") from None
    except tomllib.TOMLDecodeError as fehler:
        raise SystemExit(
            f"Die Datei einstellungen.toml im Ordner {wurzel} ist nicht lesbar: {fehler}. "
            "Bitte den Eintrag an dieser Stelle berichtigen.") from None


def offene_analysen_aufnehmen(app):
    """Reiht unfertige Seiten wieder ein, soweit ihre Aufgabe analysiert werden kann.

    Fehlt etwa der Schlüssel des Verfahrens, gilt die Seite mit dieser Meldung als
    fehlgeschlagen: Der Grund steht dann im Stapel, und nach dem Beheben lässt sie sich
    dort erneut versuchen.
    """
    speicher, einst = app.extensions["speicher"], app.config["EINST"]
    gruende = {}  # je Aufgabe nur einmal prüfen

    def grund(seite_id):
        aufgabe = speicher.aufgabe_zur_seite(seite_id)
        if aufgabe is None:  # inzwischen gelöscht; die Warteschlange überspringt sie
            return None
        if aufgabe["id"] not in gruende:
            gruende[aufgabe["id"]] = hindernis(aufgabe["verfahren"], einst)
        return gruende[aufgabe["id"]]

    app.extensions["warteschlange"].wiederaufnehmen(hindernis=grund)


def app_bauen(wurzel=None):
    """Lädt Schlüssel und Einstellungen, erzeugt die App und nimmt offene Analysen wieder auf."""
    wurzel = WURZEL if wurzel is None else Path(wurzel)
    load_dotenv(wurzel / ".env")
    einst = einstellungen_laden(wurzel)
    app = app_erzeugen(wurzel / "daten", einst)
    offene_analysen_aufnehmen(app)
    return app


def main():
    url = f"http://{ADRESSE}:{PORT}/"
    browser = os.environ.get("KORREKTOR_KEIN_BROWSER") != "1"
    # Vor allem anderen: Eine zweite Instanz würde alle unfertigen Seiten noch einmal
    # analysieren. Die Sperre bleibt bis zum Ende des Prozesses in dieser Variablen offen.
    sperre = sperre_belegen(WURZEL / "daten")
    if sperre is None:
        print(f"Korrektor läuft bereits unter {url} Es wird keine zweite Instanz gestartet.")
        if browser:
            webbrowser.open(url)
        return
    app = app_bauen(WURZEL)
    if browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    print(f"Korrektor läuft unter {url} (Beenden mit Strg+C)")
    app.run(host=ADRESSE, port=PORT, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
