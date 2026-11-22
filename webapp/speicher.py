"""Datenzugriff der Web-App: die einzige Stelle mit SQL und Bilddateien.

Alle Methoden geben einfache `dict` und `list` zurück. Jede Methode öffnet eine eigene
Verbindung, weil die Warteschlange aus mehreren Threads schreibt.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS aufgabe (
    id INTEGER PRIMARY KEY,
    titel TEXT NOT NULL,
    fach TEXT NOT NULL,
    jahrgang INTEGER,
    kategorien TEXT NOT NULL DEFAULT '["R","Z","Gr"]',
    verfahren TEXT NOT NULL,
    vorschlag_in_ausgabe INTEGER NOT NULL DEFAULT 0,
    erstellt_am TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ablage (
    id INTEGER PRIMARY KEY,
    aufgabe_id INTEGER NOT NULL REFERENCES aufgabe(id) ON DELETE CASCADE,
    bilddatei TEXT NOT NULL,
    breite INTEGER NOT NULL,
    hoehe INTEGER NOT NULL,
    reihenfolge INTEGER NOT NULL,
    neue_arbeit INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS arbeit (
    id INTEGER PRIMARY KEY,
    aufgabe_id INTEGER NOT NULL REFERENCES aufgabe(id) ON DELETE CASCADE,
    kuerzel TEXT NOT NULL,
    reihenfolge INTEGER NOT NULL,
    bestaetigt_am TEXT,
    bestaetigung TEXT
);
CREATE TABLE IF NOT EXISTS seite (
    id INTEGER PRIMARY KEY,
    arbeit_id INTEGER NOT NULL REFERENCES arbeit(id) ON DELETE CASCADE,
    nummer INTEGER NOT NULL,
    bilddatei TEXT NOT NULL,
    breite INTEGER NOT NULL,
    hoehe INTEGER NOT NULL,
    analyse_status TEXT NOT NULL DEFAULT 'neu',
    fehlermeldung TEXT,
    transkription TEXT,
    dauer_s REAL,
    analysiert_am TEXT,
    lauf INTEGER NOT NULL DEFAULT 0,
    verworfen INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS zeichen (
    id INTEGER PRIMARY KEY,
    seite_id INTEGER NOT NULL REFERENCES seite(id) ON DELETE CASCADE,
    kategorie TEXT NOT NULL,
    typ TEXT NOT NULL DEFAULT 'wort',
    x REAL NOT NULL,
    y REAL NOT NULL,
    breite REAL NOT NULL,
    hoehe REAL NOT NULL,
    gelesen TEXT NOT NULL DEFAULT '',
    vorschlag TEXT NOT NULL DEFAULT '',
    herkunft TEXT NOT NULL DEFAULT 'ki',
    status TEXT NOT NULL DEFAULT 'offen',
    bestaetigt_wie TEXT,
    rahmen_ki TEXT
);
CREATE TABLE IF NOT EXISTS einstellung (
    id INTEGER PRIMARY KEY,
    schluessel TEXT UNIQUE,
    wert TEXT
);
CREATE INDEX IF NOT EXISTS ablage_aufgabe ON ablage(aufgabe_id);
CREATE INDEX IF NOT EXISTS arbeit_aufgabe ON arbeit(aufgabe_id);
CREATE INDEX IF NOT EXISTS seite_arbeit ON seite(arbeit_id);
CREATE INDEX IF NOT EXISTS zeichen_seite ON zeichen(seite_id);
"""

AUFGABE_FELDER = ("titel", "fach", "jahrgang", "kategorien", "verfahren", "vorschlag_in_ausgabe")


def _jetzt():
    return datetime.now().isoformat(timespec="seconds")


def _aufgabe_aus_zeile(zeile):
    aufgabe = dict(zeile)
    aufgabe["kategorien"] = json.loads(aufgabe["kategorien"])
    aufgabe["vorschlag_in_ausgabe"] = bool(aufgabe["vorschlag_in_ausgabe"])
    return aufgabe


def _aufgabe_wert(feld, wert):
    if feld == "kategorien":
        return json.dumps(list(wert), ensure_ascii=False)
    if feld == "vorschlag_in_ausgabe":
        return int(bool(wert))
    return wert


class Speicher:
    def __init__(self, datenordner):
        self.ordner = Path(datenordner)
        self.bilder = self.ordner / "bilder"
        self.bilder.mkdir(parents=True, exist_ok=True)
        self.datenbank = self.ordner / "korrektor.db"
        self.schema_anlegen()

    @contextmanager
    def _verbindung(self):
        """Eigene Verbindung je Aufruf; schreibt am Ende fest oder nimmt alles zurück."""
        db = sqlite3.connect(self.datenbank, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def schema_anlegen(self):
        with self._verbindung() as db:
            db.execute("PRAGMA journal_mode = WAL")  # bleibt in der Datei gespeichert
            db.executescript(SCHEMA)

    def bildpfad(self, bilddatei):
        return self.bilder / Path(bilddatei).name

    # --- Aufgaben ---------------------------------------------------------------------

    def aufgabe_anlegen(self, titel, fach, jahrgang, kategorien, verfahren,
                        vorschlag_in_ausgabe=False):
        with self._verbindung() as db:
            return db.execute(
                "INSERT INTO aufgabe (titel, fach, jahrgang, kategorien, verfahren,"
                " vorschlag_in_ausgabe, erstellt_am) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (titel, fach, jahrgang, _aufgabe_wert("kategorien", kategorien), verfahren,
                 int(bool(vorschlag_in_ausgabe)), _jetzt())).lastrowid

    def aufgabe(self, id):
        with self._verbindung() as db:
            zeile = db.execute("SELECT * FROM aufgabe WHERE id = ?", (id,)).fetchone()
        return _aufgabe_aus_zeile(zeile) if zeile else None

    def aufgabe_aendern(self, id, **felder):
        unbekannt = set(felder) - set(AUFGABE_FELDER)
        if unbekannt:
            raise ValueError(f"unbekannte Felder: {', '.join(sorted(unbekannt))}")
        if not felder:
            return
        zuweisung = ", ".join(f"{feld} = ?" for feld in felder)
        werte = [_aufgabe_wert(feld, wert) for feld, wert in felder.items()]
        with self._verbindung() as db:
            db.execute(f"UPDATE aufgabe SET {zuweisung} WHERE id = ?", (*werte, id))

    def aufgaben(self):
        """Alle Aufgaben, neueste zuerst, mit Zählwerten für die Fortschrittsanzeige."""
        with self._verbindung() as db:
            zeilen = db.execute("""
                SELECT a.*,
                  (SELECT COUNT(*) FROM arbeit WHERE aufgabe_id = a.id) AS arbeiten,
                  (SELECT COUNT(*) FROM arbeit WHERE aufgabe_id = a.id
                     AND bestaetigt_am IS NOT NULL) AS bestaetigt,
                  (SELECT COUNT(*) FROM seite s JOIN arbeit ar ON ar.id = s.arbeit_id
                    WHERE ar.aufgabe_id = a.id) AS seiten,
                  (SELECT COUNT(*) FROM seite s JOIN arbeit ar ON ar.id = s.arbeit_id
                    WHERE ar.aufgabe_id = a.id AND s.analyse_status = 'fertig') AS seiten_fertig,
                  (SELECT COUNT(*) FROM seite s JOIN arbeit ar ON ar.id = s.arbeit_id
                    WHERE ar.aufgabe_id = a.id AND s.analyse_status = 'fehlgeschlagen')
                    AS seiten_fehlgeschlagen,
                  (SELECT COUNT(*) FROM zeichen z JOIN seite s ON s.id = z.seite_id
                     JOIN arbeit ar ON ar.id = s.arbeit_id
                    WHERE ar.aufgabe_id = a.id AND z.status = 'offen') AS offen
                FROM aufgabe a ORDER BY a.id DESC""").fetchall()
        return [_aufgabe_aus_zeile(zeile) for zeile in zeilen]
