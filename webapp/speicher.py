"""Datenzugriff der Web-App: die einzige Stelle mit SQL und Bilddateien.

Alle Methoden geben einfache `dict` und `list` zurück. Jede Methode öffnet eine eigene
Verbindung, weil die Warteschlange aus mehreren Threads schreibt.
"""
import io
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from PIL import Image

from korrektor import bild

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
ANALYSE_STATUS = ("neu", "wartet", "laeuft", "fertig", "fehlgeschlagen")
SEITE_FELDER = ("fehlermeldung", "transkription", "dauer_s", "verworfen")


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


def _zeichen_aus_zeile(zeile):
    zeichen = dict(zeile)
    zeichen["rahmen_ki"] = json.loads(zeichen["rahmen_ki"]) if zeichen["rahmen_ki"] else None
    return zeichen


def _ueberdeckt(neu, alt):
    """Ob der Rahmen `alt` mehr als die Hälfte der Fläche des Rahmens `neu` überdeckt."""
    x, y, b, h = neu
    ax, ay, ab, ah = alt
    breite = min(x + b, ax + ab) - max(x, ax)
    hoehe = min(y + h, ay + ah) - max(y, ay)
    if breite <= 0 or hoehe <= 0 or b <= 0 or h <= 0:
        return False
    return breite * hoehe > 0.5 * b * h


def status_gesamt(seitenstatus):
    """Fasst die Analysestatus der Seiten einer Arbeit zu einem Wort zusammen."""
    status = set(seitenstatus)
    if "fehlgeschlagen" in status:
        return "fehlgeschlagen"
    if status & {"wartet", "laeuft"}:
        return "laeuft"
    if status <= {"neu"}:
        return "neu"
    return "fertig"


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

    def aufgabe_loeschen(self, id):
        """Löscht die Aufgabe mit Ablage, Arbeiten, Seiten, Zeichen und allen Bilddateien."""
        with self._verbindung() as db:
            dateien = [z[0] for z in db.execute(
                "SELECT bilddatei FROM ablage WHERE aufgabe_id = ?"
                " UNION ALL SELECT s.bilddatei FROM seite s JOIN arbeit ar ON ar.id = s.arbeit_id"
                " WHERE ar.aufgabe_id = ?", (id, id))]
            db.execute("DELETE FROM aufgabe WHERE id = ?", (id,))
        self._dateien_loeschen(dateien)

    # --- Bilder -----------------------------------------------------------------------

    def _bild_speichern(self, dateiname, daten):
        """Speichert ein Foto aufrecht gedreht als JPEG; gibt (bilddatei, breite, hoehe) zurück."""
        try:
            img = bild.offen(io.BytesIO(daten))
            inhalt = bild.als_jpeg(img, qualitaet=95)
        except Exception as fehler:  # Pillow meldet Unlesbares mit wechselnden Ausnahmen
            raise ValueError(f"{dateiname}: kein lesbares Bild") from fehler
        bilddatei = f"{uuid.uuid4().hex}.jpg"
        self.bildpfad(bilddatei).write_bytes(inhalt)
        return bilddatei, img.width, img.height

    def bilddaten(self, bilddatei, breite=None):
        """JPEG-Bytes eines gespeicherten Fotos, mit `breite` als verkleinertes Vorschaubild.

        None, wenn die Datei fehlt. Das Vorschaubild wird nie größer als das Original.
        """
        pfad = self.bildpfad(bilddatei)
        if not pfad.is_file():
            return None
        if breite is not None:
            with Image.open(pfad) as img:
                if breite < img.width:
                    hoehe = max(1, round(img.height * breite / img.width))
                    img.draft("RGB", (breite, hoehe))  # JPEG schon beim Lesen verkleinern
                    return bild.als_jpeg(img.convert("RGB").resize((breite, hoehe)),
                                         qualitaet=85)
        return pfad.read_bytes()

    def _dateien_loeschen(self, dateien):
        for bilddatei in dateien:
            try:
                self.bildpfad(bilddatei).unlink(missing_ok=True)
            except OSError:  # etwa gerade geöffnet; eine verwaiste Datei schadet nicht
                pass

    def _aufgabe_pruefen(self, aufgabe_id):
        if self.aufgabe(aufgabe_id) is None:
            raise ValueError(f"Aufgabe {aufgabe_id} gibt es nicht")

    # --- Ablage -----------------------------------------------------------------------

    def bild_ablegen(self, aufgabe_id, dateiname, daten):
        """Legt ein hochgeladenes Foto in die Ablage; ValueError bei unlesbarem Bild."""
        self._aufgabe_pruefen(aufgabe_id)
        bilddatei, breite, hoehe = self._bild_speichern(dateiname, daten)
        try:
            with self._verbindung() as db:
                return db.execute(
                    "INSERT INTO ablage (aufgabe_id, bilddatei, breite, hoehe, reihenfolge)"
                    " VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(reihenfolge), 0) + 1"
                    " FROM ablage WHERE aufgabe_id = ?))",
                    (aufgabe_id, bilddatei, breite, hoehe, aufgabe_id)).lastrowid
        except BaseException:
            self._dateien_loeschen([bilddatei])
            raise

    def ablage(self, aufgabe_id):
        with self._verbindung() as db:
            zeilen = db.execute("SELECT * FROM ablage WHERE aufgabe_id = ?"
                                " ORDER BY reihenfolge, id", (aufgabe_id,)).fetchall()
        return [{**dict(zeile), "neue_arbeit": bool(zeile["neue_arbeit"])} for zeile in zeilen]

    def ablage_eintrag(self, id):
        """Ein einzelnes Foto der Ablage; None, wenn es das nicht (mehr) gibt."""
        with self._verbindung() as db:
            zeile = db.execute("SELECT * FROM ablage WHERE id = ?", (id,)).fetchone()
        return {**dict(zeile), "neue_arbeit": bool(zeile["neue_arbeit"])} if zeile else None

    def ablage_ordnen(self, aufgabe_id, eintraege):
        """Speichert Reihenfolge und Trennmarken; nicht genannte Fotos werden gelöscht."""
        with self._verbindung() as db:
            db.execute("BEGIN IMMEDIATE")
            vorhanden = dict(db.execute("SELECT id, bilddatei FROM ablage WHERE aufgabe_id = ?",
                                        (aufgabe_id,)).fetchall())
            for platz, eintrag in enumerate(eintraege, start=1):
                db.execute("UPDATE ablage SET reihenfolge = ?, neue_arbeit = ?"
                           " WHERE id = ? AND aufgabe_id = ?",
                           (platz, int(bool(eintrag.get("neue_arbeit", True))),
                            eintrag["id"], aufgabe_id))
                vorhanden.pop(eintrag["id"], None)
            db.executemany("DELETE FROM ablage WHERE id = ?", [(nr,) for nr in vorhanden])
        self._dateien_loeschen(vorhanden.values())

    def ablage_zu_arbeiten(self, aufgabe_id):
        """Bildet aus der Ablage Arbeiten nach den Trennmarken und leert die Ablage."""
        seiten = []
        with self._verbindung() as db:
            db.execute("BEGIN IMMEDIATE")
            fotos = db.execute("SELECT * FROM ablage WHERE aufgabe_id = ?"
                               " ORDER BY reihenfolge, id", (aufgabe_id,)).fetchall()
            arbeit_id = nummer = None
            for foto in fotos:
                if arbeit_id is None or foto["neue_arbeit"]:
                    arbeit_id, nummer = self._arbeit_einfuegen(db, aufgabe_id), 0
                nummer += 1
                seiten.append(self._seite_einfuegen(
                    db, arbeit_id, nummer, foto["bilddatei"], foto["breite"], foto["hoehe"]))
            db.execute("DELETE FROM ablage WHERE aufgabe_id = ?", (aufgabe_id,))
        return seiten

    # --- Arbeiten und Seiten ------------------------------------------------------------

    @staticmethod
    def _arbeit_einfuegen(db, aufgabe_id):
        """Neue Arbeit am Ende; Kürzel ist die fortlaufende zweistellige Nummer."""
        platz = db.execute("SELECT COALESCE(MAX(reihenfolge), 0) + 1 FROM arbeit"
                           " WHERE aufgabe_id = ?", (aufgabe_id,)).fetchone()[0]
        return db.execute("INSERT INTO arbeit (aufgabe_id, kuerzel, reihenfolge)"
                          " VALUES (?, ?, ?)", (aufgabe_id, f"{platz:02d}", platz)).lastrowid

    @staticmethod
    def _seite_einfuegen(db, arbeit_id, nummer, bilddatei, breite, hoehe):
        return db.execute("INSERT INTO seite (arbeit_id, nummer, bilddatei, breite, hoehe)"
                          " VALUES (?, ?, ?, ?, ?)",
                          (arbeit_id, nummer, bilddatei, breite, hoehe)).lastrowid

    def arbeit_anlegen(self, aufgabe_id, bilder):
        """Eine Arbeit aus mehreren Fotos [(dateiname, daten)]; ValueError bei unlesbarem Bild."""
        self._aufgabe_pruefen(aufgabe_id)
        if not bilder:
            raise ValueError("eine Arbeit braucht mindestens ein Foto")
        gespeichert = []
        try:
            for dateiname, daten in bilder:
                gespeichert.append(self._bild_speichern(dateiname, daten))
            with self._verbindung() as db:
                db.execute("BEGIN IMMEDIATE")
                arbeit_id = self._arbeit_einfuegen(db, aufgabe_id)
                return [self._seite_einfuegen(db, arbeit_id, nummer, *foto)
                        for nummer, foto in enumerate(gespeichert, start=1)]
        except BaseException:
            self._dateien_loeschen(foto[0] for foto in gespeichert)
            raise

    def arbeiten(self, aufgabe_id):
        """Arbeiten der Aufgabe in Stapelreihenfolge, je mit seiten, offen und status_gesamt."""
        with self._verbindung() as db:
            arbeiten = [dict(z) for z in db.execute(
                "SELECT * FROM arbeit WHERE aufgabe_id = ? ORDER BY reihenfolge, id",
                (aufgabe_id,))]
            seiten = db.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM zeichen z WHERE z.seite_id = s.id"
                " AND z.status = 'offen') AS offen"
                " FROM seite s JOIN arbeit ar ON ar.id = s.arbeit_id"
                " WHERE ar.aufgabe_id = ? ORDER BY s.nummer, s.id", (aufgabe_id,)).fetchall()
        je_arbeit = {arbeit["id"]: arbeit for arbeit in arbeiten}
        for arbeit in arbeiten:
            arbeit["seiten"], arbeit["offen"] = [], 0
        for zeile in seiten:
            seite = dict(zeile)
            je_arbeit[seite["arbeit_id"]]["offen"] += seite["offen"]
            je_arbeit[seite["arbeit_id"]]["seiten"].append(seite)
        for arbeit in arbeiten:
            arbeit["status_gesamt"] = status_gesamt(s["analyse_status"] for s in arbeit["seiten"])
        return arbeiten

    def arbeit(self, id):
        """Eine Arbeit mit ihren Seiten und je Seite den Zeichen."""
        with self._verbindung() as db:
            zeile = db.execute("SELECT * FROM arbeit WHERE id = ?", (id,)).fetchone()
            if zeile is None:
                return None
            arbeit = dict(zeile)
            arbeit["seiten"] = [dict(z) for z in db.execute(
                "SELECT * FROM seite WHERE arbeit_id = ? ORDER BY nummer, id", (id,))]
            for seite in arbeit["seiten"]:
                seite["zeichen"] = [_zeichen_aus_zeile(z) for z in db.execute(
                    "SELECT * FROM zeichen WHERE seite_id = ? ORDER BY y, x, id", (seite["id"],))]
        return arbeit

    def seite(self, id):
        with self._verbindung() as db:
            zeile = db.execute("SELECT * FROM seite WHERE id = ?", (id,)).fetchone()
        return dict(zeile) if zeile else None

    # --- Analysestatus, Lauf und Zeichen ---------------------------------------------------

    def seite_status(self, id, status, lauf=None, **felder):
        """Setzt den Analysestatus und die genannten Felder.

        Mit `lauf` wird nur geschrieben, wenn dieser Lauf noch der aktuelle der Seite ist.
        Gibt zurück, ob geschrieben wurde.
        """
        if status not in ANALYSE_STATUS:
            raise ValueError(f"unbekannter Status: {status}")
        unbekannt = set(felder) - set(SEITE_FELDER)
        if unbekannt:
            raise ValueError(f"unbekannte Felder: {', '.join(sorted(unbekannt))}")
        werte = {"analyse_status": status, **felder}
        if status == "fertig":
            werte["analysiert_am"] = _jetzt()
        zuweisung = ", ".join(f"{feld} = ?" for feld in werte)
        bedingung, zusatz = "id = ?", (id,)
        if lauf is not None:
            bedingung, zusatz = "id = ? AND lauf = ?", (id, lauf)
        with self._verbindung() as db:
            return db.execute(f"UPDATE seite SET {zuweisung} WHERE {bedingung}",
                              (*werte.values(), *zusatz)).rowcount > 0

    def seite_lauf_beginnen(self, id):
        """Beginnt einen neuen Analyselauf: erhöht `lauf`, setzt Status `laeuft`.

        Gibt die Nummer des Laufs zurück, None, wenn es die Seite nicht (mehr) gibt.
        """
        with self._verbindung() as db:
            db.execute("UPDATE seite SET lauf = lauf + 1, analyse_status = 'laeuft',"
                       " fehlermeldung = NULL WHERE id = ?", (id,))
            zeile = db.execute("SELECT lauf FROM seite WHERE id = ?", (id,)).fetchone()
        return zeile["lauf"] if zeile else None

    def zeichen_ersetzen(self, seite_id, lauf, zeichen):
        """Ersetzt die offenen KI-Zeichen der Seite durch neue Vorschläge.

        Schreibt nur, wenn `lauf` noch der aktuelle Lauf der Seite ist (sonst False).
        Bestätigte, verworfene und von Hand gesetzte Zeichen bleiben erhalten; ein neuer
        Vorschlag entfällt, wenn ein erhaltener Rahmen mehr als die Hälfte seiner Fläche
        überdeckt.
        """
        with self._verbindung() as db:
            db.execute("BEGIN IMMEDIATE")
            zeile = db.execute("SELECT lauf FROM seite WHERE id = ?", (seite_id,)).fetchone()
            if zeile is None or zeile["lauf"] != lauf:
                return False
            db.execute("DELETE FROM zeichen WHERE seite_id = ? AND herkunft = 'ki'"
                       " AND status = 'offen'", (seite_id,))
            erhalten = [tuple(z) for z in db.execute(
                "SELECT x, y, breite, hoehe FROM zeichen WHERE seite_id = ?", (seite_id,))]
            for z in zeichen:
                rahmen = (z["x"], z["y"], z["breite"], z["hoehe"])
                if any(_ueberdeckt(rahmen, alt) for alt in erhalten):
                    continue
                rahmen_ki = z.get("rahmen_ki")
                db.execute(
                    "INSERT INTO zeichen (seite_id, kategorie, typ, x, y, breite, hoehe, gelesen,"
                    " vorschlag, herkunft, status, bestaetigt_wie, rahmen_ki)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (seite_id, z["kategorie"], z.get("typ", "wort"), *rahmen,
                     z.get("gelesen") or "", z.get("vorschlag") or "",
                     z.get("herkunft", "ki"), z.get("status", "offen"), z.get("bestaetigt_wie"),
                     json.dumps(list(rahmen_ki)) if rahmen_ki is not None else None))
            return True

    def seiten_unfertig(self):
        """Seiten, deren Analyse noch aussteht oder unterbrochen wurde (wartet, laeuft)."""
        with self._verbindung() as db:
            return [z[0] for z in db.execute(
                "SELECT id FROM seite WHERE analyse_status IN ('wartet', 'laeuft') ORDER BY id")]
