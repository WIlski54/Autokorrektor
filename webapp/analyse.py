"""Brücke zu den Verfahren aus Teilprojekt 1: aus einer Seite werden Zeichen."""
import importlib


def zeichen_aus_fund(fund):
    rahmen = [*fund["anker"]["rahmen"]]
    x, y, breite, hoehe = rahmen
    return {
        "kategorie": fund["kategorie"],
        "typ": fund["anker"]["typ"],
        "x": x, "y": y, "breite": breite, "hoehe": hoehe,
        "gelesen": fund.get("gelesen") or "",
        "vorschlag": fund.get("vorschlag") or "",
        "herkunft": "ki",
        "status": "offen",
        "rahmen_ki": rahmen,
    }


def seite_analysieren(speicher, seite_id, einst):
    """Ruft das Verfahren der Aufgabe für eine Seite auf; speichert selbst nichts.

    Gibt {"zeichen", "transkription", "dauer_s", "verworfen", "fehlermeldung"} zurück.
    Funde einer Kategorie, die in der Aufgabe nicht eingeschaltet ist, entfallen.
    """
    seite = speicher.seite(seite_id)
    if seite is None:
        raise LookupError(f"Seite {seite_id} gibt es nicht")
    aufgabe = speicher.aufgabe(speicher.arbeit(seite["arbeit_id"])["aufgabe_id"])
    name = aufgabe["verfahren"]
    if not name.isidentifier():
        raise ValueError(f"ungültiger Name eines Verfahrens: {name}")
    verfahren = importlib.import_module(f"korrektor.verfahren.{name}")
    einst_mit_aufgabe = {**einst, "aufgabe": {
        "fach": aufgabe["fach"], "jahrgang": aufgabe["jahrgang"],
        "kategorien": aufgabe["kategorien"]}}
    erg = verfahren.ausfuehren(speicher.bildpfad(seite["bilddatei"]), einst_mit_aufgabe)
    return {
        "zeichen": [zeichen_aus_fund(fund) for fund in erg.get("funde") or []
                    if fund["kategorie"] in aufgabe["kategorien"]],
        "transkription": erg.get("transkription") or "",
        "dauer_s": erg.get("dauer_s") or 0.0,
        "verworfen": erg.get("verworfen") or 0,
        "fehlermeldung": erg.get("fehlermeldung"),
    }
