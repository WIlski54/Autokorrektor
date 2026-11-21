"""Ordnet Funde den Lösungsfehlern zu und berechnet die Messgrößen (Spezifikation Abschnitt 6)."""
import json
import re
from pathlib import Path

KATEGORIEN = ("R", "Z", "Gr")
ZAEHLER = ("seiten", "fehler_gesamt", "gefunden", "erfunden", "lesetreu", "lesetreue_gesamt",
           "fallen", "fallen_gesamt", "platz_sitzt", "platz_geprueft", "platz_offen",
           "ausfall", "dauer_s", "eingabe", "ausgabe")


def tokens(text):
    """Wörter und Satzzeichen, Groß-/Kleinschreibung bleibt erhalten."""
    return re.findall(r"\w+|[,.;:!?]", text)


def woerter(text):
    return re.findall(r"\w+", text)


def enthaelt(lang, kurz):
    """True, wenn `kurz` als zusammenhängende Folge in `lang` vorkommt."""
    n = len(kurz)
    return n > 0 and any(lang[i:i + n] == kurz for i in range(len(lang) - n + 1))


def passt(vorschlag, richtig):
    v, r = tokens(vorschlag), tokens(richtig)
    return enthaelt(v, r) or enthaelt(r, v)


def zuordnen(funde, fehler):
    """Gibt {fund_id: fehler_id} zurück. Erst gleiche Kategorie, dann beliebig."""
    zuordnung, vergeben = {}, set()
    for gleiche_kategorie in (True, False):
        for f in funde:
            if f["id"] in zuordnung:
                continue
            for e in fehler:
                if e["id"] in vergeben:
                    continue
                if gleiche_kategorie and f["kategorie"] != e["kategorie"]:
                    continue
                if passt(f["vorschlag"], e["richtig"]):
                    zuordnung[f["id"]] = e["id"]
                    vergeben.add(e["id"])
                    break
    return zuordnung


def bild_auswerten(erg, loesung, klicks):
    funde, fehler = erg["funde"], loesung["fehler"]
    zuordnung = zuordnen(funde, fehler)
    stamm = f"{erg['verfahren']}/{Path(erg['bild']).stem}"

    def klick(f):
        return klicks.get(f"{stamm}/{f['id']}", {})

    offen = [f for f in funde if f["id"] not in zuordnung]
    echte = [f for f in offen if klick(f).get("echt") is True]
    erfundene = [f for f in offen if klick(f).get("echt") is not True]
    zutreffend = [f for f in funde if f["id"] in zuordnung] + echte
    geprueft = [f for f in zutreffend if "sitzt" in klick(f)]

    gelesen = woerter(erg["transkription"])
    lesbar = [e for e in fehler if e["kategorie"] in ("R", "Gr")]
    gefundene_ids = set(zuordnung.values())

    return {
        "seiten": 1,
        "fehler_gesamt": len(fehler),
        "gefunden": len(gefundene_ids),
        "erfunden": len(erfundene),
        "erfundene": erfundene,
        "lesetreu": sum(enthaelt(gelesen, woerter(e["falsch"])) for e in lesbar),
        "lesetreue_gesamt": len(lesbar),
        "fallen": sum(any(enthaelt(woerter(f["gelesen"]), woerter(falle)) for f in offen)
                      for falle in loesung["fallen"]),
        "fallen_gesamt": len(loesung["fallen"]),
        "platz_sitzt": sum(klick(f)["sitzt"] is True for f in geprueft),
        "platz_geprueft": len(geprueft),
        "platz_offen": len(zutreffend) - len(geprueft),
        "ausfall": 1 if erg["fehlermeldung"] else 0,
        "dauer_s": erg["dauer_s"],
        "eingabe": erg["nutzung"]["eingabe"],
        "ausgabe": erg["nutzung"]["ausgabe"],
        "nach_kategorie": {k: [sum(e["id"] in gefundene_ids for e in fehler if e["kategorie"] == k),
                               sum(e["kategorie"] == k for e in fehler)] for k in KATEGORIEN},
    }


def summieren(werte):
    summe = {name: sum(w[name] for w in werte) for name in ZAEHLER}
    summe["nach_kategorie"] = {
        k: [sum(w["nach_kategorie"][k][0] for w in werte),
            sum(w["nach_kategorie"][k][1] for w in werte)] for k in KATEGORIEN}
    return summe


def _anteil(teil, ganzes):
    return round(teil / ganzes, 3) if ganzes else None


def kennzahlen(summe):
    return {
        "gefunden": _anteil(summe["gefunden"], summe["fehler_gesamt"]),
        "erfunden_pro_seite": _anteil(summe["erfunden"], summe["seiten"]),
        "platzierung": _anteil(summe["platz_sitzt"], summe["platz_geprueft"]),
        "lesetreue": _anteil(summe["lesetreu"], summe["lesetreue_gesamt"]),
        "fallen": _anteil(summe["fallen"], summe["fallen_gesamt"]),
    }


def bestanden(k, schwellen):
    if None in (k["gefunden"], k["erfunden_pro_seite"], k["platzierung"]):
        return False
    return (k["gefunden"] >= schwellen["gefunden_min"]
            and k["erfunden_pro_seite"] <= schwellen["erfunden_pro_seite_max"]
            and k["platzierung"] >= schwellen["platzierung_min"])


def loesung_laden(wurzel, bildname):
    """Bevorzugt die Lösung für die einzelne Abschrift (loesung_C_2.json) vor loesung_C.json."""
    teile = Path(bildname).stem.split("_")
    kandidaten = [f"loesung_{teile[0]}.json"]
    if len(teile) > 1:
        kandidaten.insert(0, f"loesung_{teile[0]}_{teile[1]}.json")
    for name in kandidaten:
        datei = Path(wurzel) / "vorlagen" / name
        if datei.exists():
            return json.loads(datei.read_text(encoding="utf-8"))
    return None


def klicks_laden(wurzel):
    datei = Path(wurzel) / "pruefseite" / "klicks.json"
    return json.loads(datei.read_text(encoding="utf-8")) if datei.exists() else {}


def alles(wurzel):
    """Wertet alle Ergebnisse aus. Text H (Härtetest) zählt nicht mit.

    Rückgabe: {verfahren: {"gesamt": summe, "gerade": summe, "schraeg": summe,
                           "erfundene": [(bildname, fund), ...]}}
    """
    klicks = klicks_laden(wurzel)
    je_verfahren = {}
    for datei in sorted((Path(wurzel) / "ergebnisse").glob("*/*.json")):
        erg = json.loads(datei.read_text(encoding="utf-8"))
        loesung = loesung_laden(wurzel, erg["bild"])
        if loesung is None or erg["bild"].startswith("H_"):
            continue
        werte = bild_auswerten(erg, loesung, klicks)
        aufnahme = Path(erg["bild"]).stem.split("_")[-1]
        eintrag = je_verfahren.setdefault(erg["verfahren"],
                                          {"alle": [], "gerade": [], "schraeg": [], "erfundene": []})
        eintrag["alle"].append(werte)
        if aufnahme in ("gerade", "schraeg"):
            eintrag[aufnahme].append(werte)
        eintrag["erfundene"] += [(erg["bild"], f) for f in werte["erfundene"]]
    return {name: {"gesamt": summieren(e["alle"]),
                   "gerade": summieren(e["gerade"]) if e["gerade"] else None,
                   "schraeg": summieren(e["schraeg"]) if e["schraeg"] else None,
                   "erfundene": e["erfundene"]}
            for name, e in je_verfahren.items()}
