"""Alle Seiten und JSON-Schnittstellen der Etappen 1 bis 3."""
import io
import math
import re
import time
from urllib.parse import urlsplit

from flask import (Blueprint, Response, abort, current_app, flash, redirect, render_template,
                   request, send_file, url_for)
from werkzeug.exceptions import HTTPException

from webapp import ausgabe, regeln, uebersicht
from webapp.verfahren import VERFAHREN, VOREINSTELLUNG, anzeigename, hindernis

seiten = Blueprint("seiten", __name__)

KATEGORIEN = uebersicht.FESTE_KATEGORIEN
EIGENE_HOSTS = ("127.0.0.1", "localhost")
VORSCHLAG_LAENGE = 200  # Zeichen; mehr passt in keine Randspalte
ZEICHEN_FELDER = ("id", "seite_id", "kategorie", "typ", "x", "y", "breite", "hoehe", "gelesen",
                  "vorschlag", "herkunft", "status", "bestaetigt_wie")


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


def _eigener_host(host):
    """Ob der Host-Kopf (mit beliebigem Port) diesen Rechner unter seinem lokalen Namen nennt."""
    try:
        return urlsplit(f"//{host}").hostname in EIGENE_HOSTS
    except ValueError:
        return False


@seiten.before_app_request
def _fremde_herkunft_ablehnen():
    """Die App hat keinen Login: Anfragen unter fremdem Namen oder von fremden Webseiten
    werden abgewiesen.

    Der Host-Kopf muss 127.0.0.1 oder localhost nennen. Sonst könnte eine fremde Webseite,
    deren Name auf diesen Rechner umgebogen wird (DNS-Rebinding), die App lesen und bedienen.
    """
    if not _eigener_host(request.host):
        abort(403)
    herkunft = request.headers.get("Origin")
    if request.method == "POST" and herkunft and urlsplit(herkunft).netloc != request.host:
        abort(403)


@seiten.after_app_request
def _nicht_zwischenspeichern(antwort):
    """Seiten und JSON-Antworten zeigen den Stand der Korrektur; der Browser soll sie nie
    aus einem Zwischenspeicher holen. Die Fotos regeln das selbst über ihre Kennung."""
    if antwort.mimetype in ("text/html", "application/json") and "ETag" not in antwort.headers:
        antwort.headers["Cache-Control"] = "no-store"
    return antwort


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

STATUSTEXT = {
    "neu": "noch nicht analysiert",
    "wartet": "wartet",
    "laeuft": "Analyse läuft",
    "fertig": "analysiert",
    "fehlgeschlagen": "fehlgeschlagen",
}


def _stand(aufgabe_id):
    """Der Stand der Analyse einer Aufgabe als einfache Daten für Seite und Abfrage."""
    arbeiten = []
    gesamt = {"seiten": 0, "fertig": 0, "fehlgeschlagen": 0, "unterwegs": 0, "offen": 0,
              "arbeiten": 0, "bestaetigt": 0}
    for arbeit in _speicher().arbeiten(aufgabe_id):
        seiten_der_arbeit = [{"id": s["id"], "nummer": s["nummer"], "status": s["analyse_status"],
                              "fehlermeldung": s["fehlermeldung"]} for s in arbeit["seiten"]]
        arbeiten.append({"id": arbeit["id"], "kuerzel": arbeit["kuerzel"],
                         "seitenzahl": len(seiten_der_arbeit),
                         "status_gesamt": arbeit["status_gesamt"], "offen": arbeit["offen"],
                         "bestaetigt_am": arbeit["bestaetigt_am"],
                         "bestaetigbar": arbeit["bestaetigbar"],
                         "seiten": seiten_der_arbeit})
        gesamt["offen"] += arbeit["offen"]
        gesamt["arbeiten"] += 1
        gesamt["bestaetigt"] += arbeit["bestaetigt_am"] is not None
        for seite in seiten_der_arbeit:
            gesamt["seiten"] += 1
            if seite["status"] in ("fertig", "fehlgeschlagen"):
                gesamt[seite["status"]] += 1
            elif seite["status"] in ("wartet", "laeuft"):
                gesamt["unterwegs"] += 1
    return {"arbeiten": arbeiten, "gesamt": gesamt, "aktiv": gesamt["unterwegs"] > 0}


@seiten.get("/aufgabe/<int:aufgabe_id>")
def stapel(aufgabe_id):
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    stand = _stand(aufgabe_id)
    daten = {
        "url_stand": url_for("seiten.stand", aufgabe_id=aufgabe_id),
        "url_erneut": url_for("seiten.seite_erneut", seite_id=0),
        "url_pdf": url_for("seiten.arbeit_pdf", arbeit_id=0),  # die 0 ersetzt das Skript
        "aktiv": stand["aktiv"],
        "statustext": STATUSTEXT,
    }
    return render_template("stapel.html", aufgabe=aufgabe, stand=stand, daten=daten,
                           statustext=STATUSTEXT, in_ablage=len(_speicher().ablage(aufgabe_id)))


@seiten.get("/aufgabe/<int:aufgabe_id>/stand")
def stand(aufgabe_id):
    _aufgabe_oder_404(aufgabe_id)
    return _stand(aufgabe_id)


@seiten.post("/seite/<int:seite_id>/erneut")
def seite_erneut(seite_id):
    """Reiht eine fehlgeschlagene oder nie begonnene Seite (neu) ein."""
    seite = _speicher().seite(seite_id)
    if seite is None:
        abort(404)
    if seite["analyse_status"] not in ("fehlgeschlagen", "neu"):
        return {"fehler": "Nur fehlgeschlagene oder noch nicht analysierte Seiten lassen sich "
                          "erneut analysieren."}, 409
    aufgabe = _speicher().aufgabe_zur_seite(seite_id)
    if aufgabe is None:  # inzwischen gelöscht
        abort(404)
    grund = _hindernis(aufgabe)
    if grund:
        return {"fehler": grund}, 409
    _schlange().einreihen(seite_id)
    return {"ok": True}


# --- Arbeit ansehen -----------------------------------------------------------------------

@seiten.get("/arbeit/<int:arbeit_id>")
def arbeit(arbeit_id):
    arbeit = _speicher().arbeit(arbeit_id)
    if arbeit is None:
        abort(404)
    nummer = request.args.get("seite", default=1, type=int)
    if not 1 <= nummer <= len(arbeit["seiten"]):
        abort(404)
    seite = arbeit["seiten"][nummer - 1]
    # Verworfene Zeichen stehen in den Daten in einem eigenen Feld; die Liste der Vorlage
    # zeigt sie nicht.
    zeichen = [z for z in seite["zeichen"] if z["status"] != "verworfen"]
    verworfen = [z for z in seite["zeichen"] if z["status"] == "verworfen"]
    aufgabe = _speicher().aufgabe(arbeit["aufgabe_id"])
    reihe = [a["id"] for a in _speicher().arbeiten(arbeit["aufgabe_id"])]
    if aufgabe is None or arbeit_id not in reihe:  # inzwischen gelöscht
        abort(404)
    platz = reihe.index(arbeit_id)
    daten = {
        "seite": {"id": seite["id"], "nummer": nummer, "breite": seite["breite"],
                  "hoehe": seite["hoehe"]},
        "zeichen": [_zeichen_daten(z) for z in zeichen],
        "verworfen": [_zeichen_daten(z) for z in verworfen],
        "arbeit": {"id": arbeit["id"], "kuerzel": arbeit["kuerzel"],
                   "bestaetigung": arbeit["bestaetigung"], **_arbeit_stand(arbeit)},
        "seiten": _seiten_stand(arbeit),
        "kuerzel": _kuerzelliste(),
        "url_stand": url_for("seiten.stand", aufgabe_id=aufgabe["id"]),
        "url_vorschau": url_for("seiten.seite_vorschau", seite_id=seite["id"]),
    }
    return render_template(
        "arbeit.html", aufgabe=aufgabe, arbeit=arbeit, seite=seite, nummer=nummer,
        seitenzahl=len(arbeit["seiten"]), zeichen=zeichen, daten=daten,
        statustext=STATUSTEXT, kategorien=dict(KATEGORIEN),
        vorige_arbeit=reihe[platz - 1] if platz > 0 else None,
        naechste_arbeit=reihe[platz + 1] if platz + 1 < len(reihe) else None)


# --- Korrektur: Zeichen bearbeiten (JSON) -------------------------------------------------
#
# Jede schreibende Antwort hat die Form
#   {"zeichen": <aktuelles Zeichen oder null>,
#    "arbeit": {"stand", "offen", "bestaetigt_am", "bestaetigbar", "grund",
#               "seiten": [{"id", "nummer", "status", "offen"}]}}
# `stand` ist der Änderungszähler der Arbeit. Alles in `arbeit` und das Zeichen stammen aus
# einem Lesevorgang nach dem Schreiben und gehören zu genau diesem Stand; die Ansicht
# übernimmt nie einen älteren Stand als den, den sie schon zeigt.
# Ein Regelverstoß ergibt 409, Unbekanntes 404, eine ungültige Eingabe 400, jeweils mit
# {"fehler": Meldung}.

class Eingabefehler(Exception):
    """Der JSON-Körper einer Anfrage ist unbrauchbar (ergibt 400)."""


@seiten.app_errorhandler(Eingabefehler)
def _eingabefehler(fehler):
    return {"fehler": str(fehler)}, 400


@seiten.app_errorhandler(regeln.RegelFehler)
def _regelfehler(fehler):
    return {"fehler": str(fehler)}, 409


def _gibt_es_nicht(was):
    return {"fehler": f"{was} gibt es nicht (mehr). Bitte die Seite neu laden."}, 404


def _zeichen_daten(zeichen):
    return {feld: zeichen[feld] for feld in ZEICHEN_FELDER}


def _seiten_stand(arbeit):
    """Je Seite der Arbeit ihr Platz, ihr Analysestatus und die Zahl offener Vorschläge."""
    return [{"id": s["id"], "nummer": platz, "status": s["analyse_status"],
             "offen": len(regeln.offene(s["zeichen"]))}
            for platz, s in enumerate(arbeit["seiten"], start=1)]


def _arbeit_stand(arbeit):
    """Der Stand einer Arbeit (wie von `speicher.arbeit`) für Antworten und Ansicht."""
    seiten_der_arbeit = _seiten_stand(arbeit)
    return {"stand": arbeit["stand"],
            "offen": sum(seite["offen"] for seite in seiten_der_arbeit),
            "bestaetigt_am": arbeit["bestaetigt_am"],
            "bestaetigbar": arbeit["bestaetigbar"],
            "grund": arbeit["bestaetigbar_grund"],
            "seiten": seiten_der_arbeit}


def _kuerzelliste():
    """R, Z, Gr und die eigenen Kürzel, je mit Bezeichnung, in der Reihenfolge der Auswahl."""
    return ([{"kuerzel": k, "bezeichnung": b, "eigen": False} for k, b in KATEGORIEN]
            + [{**eintrag, "eigen": True} for eintrag in _speicher().kuerzel()])


def _erlaubte():
    return regeln.erlaubte_kuerzel(_speicher().kuerzel())


def _antwort(arbeit_id, zeichen_id=None, **zusatz):
    """Die gemeinsame Antwort nach einer Änderung; 404, wenn die Arbeit inzwischen fehlt.

    Arbeit und Zeichen stammen aus demselben Lesevorgang und passen zu `arbeit.stand`.
    """
    arbeit = _speicher().arbeit(arbeit_id)
    if arbeit is None:
        return _gibt_es_nicht("Diese Arbeit")
    zeichen = next((z for seite in arbeit["seiten"] for z in seite["zeichen"]
                    if z["id"] == zeichen_id), None)
    return {"zeichen": _zeichen_daten(zeichen) if zeichen else None,
            "arbeit": _arbeit_stand(arbeit), **zusatz}


def _koerper(pflicht=(), wahl=(), leer_erlaubt=False):
    """Der JSON-Körper als dict mit genau den vorgesehenen Feldern; sonst Eingabefehler."""
    if leer_erlaubt and not request.get_data():
        return {}
    inhalt = request.get_json(silent=True)
    if not isinstance(inhalt, dict):
        raise Eingabefehler("Die Angaben fehlen oder sind unlesbar.")
    fehlend = [feld for feld in pflicht if feld not in inhalt]
    if fehlend:
        raise Eingabefehler(f"Es fehlt die Angabe: {', '.join(fehlend)}.")
    fremd = sorted(set(inhalt) - set(pflicht) - set(wahl))
    if fremd:
        raise Eingabefehler(f"Unbekannte Angabe: {', '.join(fremd)}.")
    return inhalt


def _pixel(inhalt, feld):
    """Eine Zahl des Körpers, auf ganze Pixel gerundet (ab ,5 aufwärts)."""
    wert = inhalt[feld]
    if type(wert) is int:
        return wert
    if type(wert) is not float or not math.isfinite(wert):
        raise Eingabefehler(f"Die Angabe {feld} muss eine Zahl sein.")
    return math.floor(wert + 0.5)


def _rahmen(inhalt):
    return [_pixel(inhalt, feld) for feld in ("x", "y", "breite", "hoehe")]


def _text(inhalt, feld, hoechstens=None):
    """Ein Text des Körpers ohne Rand-Leerzeichen."""
    wert = inhalt[feld]
    if not isinstance(wert, str):
        raise Eingabefehler(f"Die Angabe {feld} muss ein Text sein.")
    wert = wert.strip()
    if hoechstens is not None and len(wert) > hoechstens:
        raise Eingabefehler(f"Die Angabe {feld} ist zu lang (höchstens {hoechstens} Zeichen).")
    return wert


def _stand_aus(inhalt):
    """Der Stand der Arbeit, den die Ansicht zuletzt gezeigt hat."""
    stand = inhalt["stand"]
    if type(stand) is not int:
        raise Eingabefehler("Die Angabe stand muss eine ganze Zahl sein.")
    return stand


def _kuerzel_aus(inhalt):
    kuerzel = _text(inhalt, "kategorie")
    if not kuerzel:
        raise Eingabefehler("Bitte ein Kürzel wählen.")
    return kuerzel


def _uebergang(zeichen_id, regel):
    """Wendet einen Übergang ohne weitere Angaben an (bestätigen, verwerfen, zurückholen)."""
    zeichen = _speicher().zeichen_eintrag(zeichen_id)
    if zeichen is None:
        return _gibt_es_nicht("Dieses Zeichen")
    return _schreiben(zeichen, regel(zeichen))


def _schreiben(zeichen, felder):
    if not _speicher().zeichen_aendern(zeichen["id"], **felder):  # inzwischen gelöscht
        return _gibt_es_nicht("Dieses Zeichen")
    return _antwort(zeichen["arbeit_id"], zeichen["id"])


@seiten.post("/zeichen/<int:zeichen_id>/bestaetigen")
def zeichen_bestaetigen(zeichen_id):
    return _uebergang(zeichen_id, regeln.einzeln_bestaetigen)


@seiten.post("/zeichen/<int:zeichen_id>/verwerfen")
def zeichen_verwerfen(zeichen_id):
    return _uebergang(zeichen_id, regeln.verwerfen)


@seiten.post("/zeichen/<int:zeichen_id>/zurueckholen")
def zeichen_zurueckholen(zeichen_id):
    return _uebergang(zeichen_id, regeln.zurueckholen)


@seiten.post("/zeichen/<int:zeichen_id>/aendern")
def zeichen_aendern(zeichen_id):
    """Ändert Kürzel und/oder Vorschlag: {"kategorie"?, "vorschlag"?}, mindestens eines."""
    zeichen = _speicher().zeichen_eintrag(zeichen_id)
    if zeichen is None:
        return _gibt_es_nicht("Dieses Zeichen")
    inhalt = _koerper(wahl=("kategorie", "vorschlag"))
    if not inhalt:
        raise Eingabefehler("Es fehlt die Angabe: kategorie oder vorschlag.")
    kategorie = _kuerzel_aus(inhalt) if "kategorie" in inhalt else None
    vorschlag = _text(inhalt, "vorschlag", VORSCHLAG_LAENGE) if "vorschlag" in inhalt else None
    return _schreiben(zeichen, regeln.aendern(zeichen, kategorie=kategorie, vorschlag=vorschlag,
                                              erlaubte=_erlaubte()))


@seiten.post("/zeichen/<int:zeichen_id>/rahmen")
def zeichen_rahmen(zeichen_id):
    """Verschiebt den Rahmen oder ändert seine Größe: {"x", "y", "breite", "hoehe"}."""
    zeichen = _speicher().zeichen_eintrag(zeichen_id)
    seite = _speicher().seite(zeichen["seite_id"]) if zeichen else None
    if seite is None:
        return _gibt_es_nicht("Dieses Zeichen")
    rahmen = _rahmen(_koerper(pflicht=("x", "y", "breite", "hoehe")))
    return _schreiben(zeichen, regeln.verschieben(zeichen, *rahmen,
                                                  (seite["breite"], seite["hoehe"])))


@seiten.post("/zeichen/<int:zeichen_id>/loeschen")
def zeichen_loeschen(zeichen_id):
    """Löscht ein eigenes Zeichen; KI-Vorschläge werden verworfen, nicht gelöscht."""
    zeichen = _speicher().zeichen_eintrag(zeichen_id)
    if zeichen is None:
        return _gibt_es_nicht("Dieses Zeichen")
    regeln.loeschbar(zeichen)
    _speicher().zeichen_loeschen(zeichen_id)
    return _antwort(zeichen["arbeit_id"])


@seiten.post("/seite/<int:seite_id>/zeichen")
def zeichen_setzen(seite_id):
    """Setzt ein eigenes Zeichen: {"kategorie", "typ", "x", "y", "breite", "hoehe", "vorschlag"?}."""
    seite = _speicher().seite(seite_id)
    if seite is None:
        return _gibt_es_nicht("Diese Seite")
    inhalt = _koerper(pflicht=("kategorie", "typ", "x", "y", "breite", "hoehe"),
                      wahl=("vorschlag",))
    vorschlag = _text(inhalt, "vorschlag", VORSCHLAG_LAENGE) if "vorschlag" in inhalt else ""
    neu = regeln.neues_handzeichen(_kuerzel_aus(inhalt), _text(inhalt, "typ"), *_rahmen(inhalt),
                                   vorschlag, _erlaubte(), (seite["breite"], seite["hoehe"]))
    try:
        zeichen_id = _speicher().zeichen_anlegen(seite_id, neu)
    except ValueError:  # Seite inzwischen gelöscht
        return _gibt_es_nicht("Diese Seite")
    return _antwort(seite["arbeit_id"], zeichen_id)


# --- Korrektur: Arbeit insgesamt (JSON) ---------------------------------------------------

@seiten.post("/arbeit/<int:arbeit_id>/rest-bestaetigen")
def arbeit_rest_bestaetigen(arbeit_id):
    """Bestätigt alle offenen Zeichen der Arbeit gesammelt; nennt sie in `geaendert`.

    Der Körper nennt mit {"stand": Zahl} den Stand, den der Dialog gezeigt hat. 409, wenn
    die Arbeit seither geändert wurde oder eine ihrer Seiten nicht fertig analysiert ist.
    """
    if _speicher().arbeit(arbeit_id) is None:
        return _gibt_es_nicht("Diese Arbeit")
    stand = _stand_aus(_koerper(pflicht=("stand",)))
    geaendert = _speicher().rest_bestaetigen(arbeit_id, stand)  # prüft und schreibt in einem Zug
    if geaendert is None:
        return _gibt_es_nicht("Diese Arbeit")
    return _antwort(arbeit_id, geaendert=geaendert)


@seiten.get("/arbeit/<int:arbeit_id>/zahlen")
def arbeit_zahlen(arbeit_id):
    """Die fünf Zahlen für den Bestätigungsdialog und der Stand der Arbeit dazu."""
    arbeit = _speicher().arbeit(arbeit_id)
    if arbeit is None:
        return _gibt_es_nicht("Diese Arbeit")
    stand = _arbeit_stand(arbeit)
    return {"zahlen": regeln.zahlen([z for seite in arbeit["seiten"] for z in seite["zeichen"]]),
            "bestaetigbar": stand["bestaetigbar"], "grund": stand["grund"], "arbeit": stand}


@seiten.post("/arbeit/<int:arbeit_id>/bestaetigen")
def arbeit_bestaetigen(arbeit_id):
    """Gesamtbestätigung: {"stand": Zahl} nennt den Stand, den der Dialog gezeigt hat.

    409, wenn die Arbeit seither geändert wurde oder nicht bestätigbar ist. Die
    gespeicherten Zahlen berechnet der Server.
    """
    if _speicher().arbeit(arbeit_id) is None:
        return _gibt_es_nicht("Diese Arbeit")
    stand = _stand_aus(_koerper(pflicht=("stand",)))
    zahlen = _speicher().arbeit_bestaetigen(arbeit_id, stand)  # prüft und schreibt in einem Zug
    if zahlen is None:
        return _gibt_es_nicht("Diese Arbeit")
    return _antwort(arbeit_id, zahlen=zahlen)


@seiten.post("/arbeit/<int:arbeit_id>/kuerzel")
def arbeit_kuerzel(arbeit_id):
    """Benennt die Arbeit um: {"kuerzel"} mit 1 bis 20 Zeichen. Die Bestätigung bleibt."""
    if _speicher().arbeit(arbeit_id) is None:
        return _gibt_es_nicht("Diese Arbeit")
    inhalt = _koerper(pflicht=("kuerzel",))
    try:
        kuerzel = regeln.arbeitskuerzel_pruefen(inhalt["kuerzel"])
    except regeln.RegelFehler as fehler:
        raise Eingabefehler(str(fehler)) from fehler
    _speicher().arbeit_kuerzel_setzen(arbeit_id, kuerzel)
    return _antwort(arbeit_id, kuerzel=kuerzel)


@seiten.post("/seite/<int:seite_id>/neu-analysieren")
def seite_neu_analysieren(seite_id):
    """Reiht eine fertige oder fehlgeschlagene Seite neu ein.

    Bestätigte, verworfene und eigene Zeichen bleiben; die offenen Vorschläge werden
    ersetzt. Die Gesamtbestätigung der Arbeit verfällt sofort.
    """
    aufgabe = _speicher().aufgabe_zur_seite(seite_id)
    if aufgabe is None:
        return _gibt_es_nicht("Diese Seite")
    grund = _hindernis(aufgabe)
    if grund:
        return {"fehler": grund}, 409
    # Prüft den Status, setzt `wartet` und hebt die Bestätigung auf, alles in einem Zug.
    arbeit_id = _speicher().seite_neuanalyse_vormerken(seite_id)
    if arbeit_id is None:  # inzwischen gelöscht
        return _gibt_es_nicht("Diese Seite")
    # Der Arbeiter, der die Seite eben fertig gemeldet hat, gibt sie einen Augenblick
    # später frei; so lange nimmt die Warteschlange sie noch nicht an.
    for _ in range(100):
        if _schlange().einreihen(seite_id):
            break
        time.sleep(0.02)
    return _antwort(arbeit_id)


# --- Ausgabe und Stapelübersicht (Etappe 3) -----------------------------------------------
#
# Ausgegeben werden nur Arbeiten, deren Korrektur insgesamt bestätigt ist. Die Antworten
# sind Downloads und werden nie zwischengespeichert: Sie zeigen den Stand der Korrektur.
# Die Vorschau einer Seite zeigt dieselbe Zeichnung schon vor der Gesamtbestätigung.

NAMENSTEIL_LAENGE = 60  # Zeichen je Teil eines Dateinamens


def _dateiname(*teile, endung):
    """Ein Dateiname nur aus Buchstaben, Ziffern, Bindestrich und Unterstrich.

    Alles andere wird zu einem Unterstrich; Teile, von denen nichts bleibt, entfallen. Jeder
    Teil ist höchstens NAMENSTEIL_LAENGE Zeichen lang, damit der Antwortkopf kurz bleibt.
    """
    sauber = [re.sub(r"_+", "_", re.sub(r"[^\w-]", "_", str(teil))).strip("_")
              [:NAMENSTEIL_LAENGE].strip("_") for teil in teile]
    return "-".join(teil for teil in sauber if teil) + "." + endung


def _download(daten, mimetype, dateiname):
    """Die Bytes als Download.

    `send_file` nennt den Dateinamen so, dass der Kopf auch bei Zeichen außerhalb von
    Latin-1 gültig bleibt: ein Ersatz in ASCII und daneben `filename*=UTF-8''…`.
    """
    antwort = send_file(io.BytesIO(daten), mimetype=mimetype, as_attachment=True,
                        download_name=dateiname)
    antwort.headers["Cache-Control"] = "no-store"
    return antwort


def _nicht_ausgebbar(fehler, zurueck, zurueck_text, code=409):
    """Die Fehlerseite mit dem Weg zurück: 409, wenn (noch) nichts bestätigt ist; 500, wenn
    die Ausgabe selbst scheitert (Foto fehlt oder ist defekt)."""
    return render_template("fehler.html", text=str(fehler), code=code, zurueck=zurueck,
                           zurueck_text=zurueck_text), code


@seiten.get("/arbeit/<int:arbeit_id>/pdf")
def arbeit_pdf(arbeit_id):
    """Das PDF einer bestätigten Arbeit als Download; nicht bestätigt ergibt 409, ein
    fehlendes oder defektes Foto 500."""
    arbeit = _speicher().arbeit(arbeit_id)
    if arbeit is None:
        abort(404)
    zurueck = url_for("seiten.arbeit", arbeit_id=arbeit_id), "Zurück zur Korrektur der Arbeit"
    try:
        pdf = ausgabe.arbeit_als_pdf(_speicher(), arbeit_id)
    except regeln.RegelFehler as fehler:
        return _nicht_ausgebbar(fehler, *zurueck)
    except ausgabe.AusgabeFehler as fehler:
        return _nicht_ausgebbar(fehler, *zurueck, code=500)
    return _download(pdf, "application/pdf", _dateiname("Arbeit", arbeit["kuerzel"], endung="pdf"))


@seiten.get("/aufgabe/<int:aufgabe_id>/pdf")
def aufgabe_pdf(aufgabe_id):
    """Das Sammel-PDF aller bestätigten Arbeiten; ohne bestätigte Arbeit 409, ein fehlendes
    oder defektes Foto 500.

    Fehlen Arbeiten, weil sie nicht bestätigt sind, nennt der Dateiname die Zahlen:
    `<Titel>-Sammel-<enthalten>-von-<alle>.pdf`.
    """
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    zurueck = url_for("seiten.stapel", aufgabe_id=aufgabe_id), "Zurück zum Stapel"
    try:
        pdf, enthalten, fehlend = ausgabe.aufgabe_als_pdf(_speicher(), aufgabe_id)
    except regeln.RegelFehler as fehler:
        return _nicht_ausgebbar(fehler, *zurueck)
    except ausgabe.AusgabeFehler as fehler:
        return _nicht_ausgebbar(fehler, *zurueck, code=500)
    teile = [aufgabe["titel"], "Sammel"]
    if fehlend:
        teile.append(f"{enthalten}-von-{enthalten + fehlend}")
    return _download(pdf, "application/pdf", _dateiname(*teile, endung="pdf"))


@seiten.get("/seite/<int:seite_id>/vorschau")
def seite_vorschau(seite_id):
    """Die Seite als Bild, wie sie im PDF erschiene: nur mit den bestätigten Zeichen.

    Anders als das PDF braucht die Vorschau keine Gesamtbestätigung. Ein fehlendes oder
    defektes Foto ergibt 500. Das Bild zeigt den Stand der Korrektur und wird nie
    zwischengespeichert.
    """
    seite = _speicher().seite(seite_id)
    if seite is None:
        abort(404)
    try:
        bild = ausgabe.seite_als_vorschau(_speicher(), seite_id)
    except ausgabe.AusgabeFehler as fehler:
        return _nicht_ausgebbar(fehler, url_for("seiten.arbeit", arbeit_id=seite["arbeit_id"]),
                                "Zurück zur Korrektur der Arbeit", code=500)
    if bild is None:  # inzwischen gelöscht
        abort(404)
    antwort = Response(bild, mimetype="image/jpeg")
    antwort.headers["Cache-Control"] = "no-store"
    return antwort


@seiten.get("/aufgabe/<int:aufgabe_id>/uebersicht")
def stapeluebersicht(aufgabe_id):
    """Die Stapelübersicht: Zeichen je Kategorie, häufige Fehlerwörter, Tabelle je Arbeit."""
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    return render_template("uebersicht.html", aufgabe=aufgabe,
                           daten=uebersicht.stapel(_speicher(), aufgabe_id),
                           feste=[kuerzel for kuerzel, _ in KATEGORIEN])


@seiten.get("/aufgabe/<int:aufgabe_id>/uebersicht.csv")
def stapeluebersicht_csv(aufgabe_id):
    """Die Tabelle je Arbeit als CSV; UTF-8 mit BOM, damit Excel Umlaute richtig liest."""
    aufgabe = _aufgabe_oder_404(aufgabe_id)
    inhalt = uebersicht.als_csv(uebersicht.stapel(_speicher(), aufgabe_id))
    # Den Zeichensatz hängt Flask bei Textarten selbst an: genau ein `charset=utf-8`.
    return _download(inhalt.encode("utf-8-sig"), "text/csv",
                     _dateiname(aufgabe["titel"], "Uebersicht", endung="csv"))


# --- Einstellungen: eigene Kürzel ---------------------------------------------------------

LEERE_KUERZELZEILEN = 3


def _kuerzel_zeigen(zeilen, fehler=None, status=200):
    zeilen = list(zeilen) + [{"kuerzel": "", "bezeichnung": ""}] * LEERE_KUERZELZEILEN
    return render_template("kuerzel.html", zeilen=zeilen, fehler=fehler, feste=KATEGORIEN,
                           kuerzel_laenge=regeln.KUERZEL_LAENGE,
                           bezeichnung_laenge=regeln.BEZEICHNUNG_LAENGE), status


@seiten.route("/einstellungen/kuerzel", methods=["GET", "POST"])
def einstellungen_kuerzel():
    """Die Liste der eigenen Kürzel: je Zeile die Felder `kuerzel` und `bezeichnung`."""
    if request.method == "GET":
        return _kuerzel_zeigen(_speicher().kuerzel())
    kuerzel = request.form.getlist("kuerzel")
    bezeichnungen = request.form.getlist("bezeichnung")
    laenge = max(len(kuerzel), len(bezeichnungen))
    zeilen = [{"kuerzel": k.strip(), "bezeichnung": b.strip()}
              for k, b in zip(kuerzel + [""] * (laenge - len(kuerzel)),
                              bezeichnungen + [""] * (laenge - len(bezeichnungen)))]
    zeilen = [z for z in zeilen if z["kuerzel"] or z["bezeichnung"]]  # leere Zeilen entfallen
    try:
        _speicher().kuerzel_setzen(zeilen)
    except regeln.RegelFehler as fehler:
        return _kuerzel_zeigen(zeilen, fehler=str(fehler), status=400)
    flash("Die eigenen Kürzel sind gespeichert.", "erfolg")
    return redirect(url_for("seiten.einstellungen_kuerzel"))


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

def _natuerlich(dateiname):
    """Sortierschlüssel, der Zahlen im Namen als Zahlen vergleicht (9 vor 10)."""
    return [int(teil) if teil.isdigit() else teil.casefold()
            for teil in re.split(r"(\d+)", dateiname)]


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
            _aufgabe_oder_404(aufgabe_id)  # inzwischen gelöscht: kein Fehler der Datei
            abgelehnt.append({"dateiname": dateiname,
                              "grund": "kein lesbares Bild (erlaubt sind JPG, PNG und WebP)"})
            continue
        eintrag = _speicher().ablage_eintrag(ablage_id)
        if eintrag is None:  # inzwischen entfernt oder Aufgabe gelöscht
            _aufgabe_oder_404(aufgabe_id)
            continue
        angenommen.append({"id": ablage_id, "dateiname": dateiname,
                           "breite": eintrag["breite"], "hoehe": eintrag["hoehe"]})
    return {"angenommen": angenommen, "abgelehnt": abgelehnt}


@seiten.post("/aufgabe/<int:aufgabe_id>/ablage/ordnen")
def ablage_ordnen(aufgabe_id):
    """Speichert Reihenfolge und Trennmarken als {"eintraege": [...], "entfernt": [...]}.

    Entfernt werden nur die in `entfernt` genannten Fotos. Was in keiner der beiden Listen
    steht (etwa aus einem anderen Fenster hochgeladen), bleibt und rückt ans Ende.
    """
    _aufgabe_oder_404(aufgabe_id)
    inhalt = request.get_json(silent=True)
    eintraege = inhalt.get("eintraege") if isinstance(inhalt, dict) else None
    if not isinstance(eintraege, list):
        return {"fehler": "Die Angaben zur Reihenfolge fehlen."}, 400
    entfernt = inhalt.get("entfernt", [])
    if not isinstance(entfernt, list) or any(type(nr) is not int for nr in entfernt):
        return {"fehler": "Die Angaben zu den entfernten Fotos sind unbrauchbar."}, 400
    vorhanden = {e["id"] for e in _speicher().ablage(aufgabe_id)}
    sauber, gesehen = [], set()
    for eintrag in eintraege:
        nr = eintrag.get("id") if isinstance(eintrag, dict) else None
        if type(nr) is not int or nr not in vorhanden or nr in gesehen or nr in entfernt:
            return {"fehler": "Die Angaben zur Reihenfolge passen nicht zur Ablage. "
                              "Bitte die Seite neu laden."}, 400
        gesehen.add(nr)
        sauber.append({"id": nr, "neue_arbeit": bool(eintrag.get("neue_arbeit", True))})
    # Schon entfernte oder fremde Kennungen in `entfernt` übergeht der Speicher.
    _speicher().ablage_ordnen(aufgabe_id, sauber, entfernt=entfernt)
    ablage = _speicher().ablage(aufgabe_id)
    arbeiten = sum(1 for platz, e in enumerate(ablage) if platz == 0 or e["neue_arbeit"])
    return {"ok": True, "fotos": len(ablage), "arbeiten": arbeiten}


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
        if _speicher().arbeiten(aufgabe_id):  # etwa ein Doppelklick: die Analyse läuft schon
            return redirect(url_for("seiten.stapel", aufgabe_id=aufgabe_id))
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
        seiten_ids = _speicher().arbeit_anlegen(
            aufgabe_id, sorted(gelesen, key=lambda datei: _natuerlich(datei[0])))
    except ValueError as fehler:
        _aufgabe_oder_404(aufgabe_id)  # inzwischen gelöscht
        flash(f"Die Arbeit wurde nicht hinzugefügt ({fehler}). "
              "Erlaubt sind JPG, PNG und WebP.", "fehler")
        return zurueck
    for seite_id in seiten_ids:
        _schlange().einreihen(seite_id)
    return zurueck
