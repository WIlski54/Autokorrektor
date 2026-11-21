"""Ordnet Funde den Lösungsfehlern zu und berechnet die Messgrößen (Spezifikation Abschnitt 6)."""
import json
import re
from pathlib import Path

KATEGORIEN = ("R", "Z", "Gr")
ZAEHLER = ("seiten", "fehler_gesamt", "gefunden", "erfunden", "dubletten", "verworfen",
           "lesetreu", "lesetreue_gesamt", "fallen", "fallen_gesamt", "platz_sitzt",
           "platz_geprueft", "platz_offen", "ausfall", "dauer_s", "eingabe", "ausgabe")


def tokens(text):
    """Wörter und Satzzeichen, Groß-/Kleinschreibung bleibt erhalten."""
    return re.findall(r"\w+|[,.;:!?]", text or "")


def woerter(text):
    return re.findall(r"\w+", text or "")


def enthaelt(lang, kurz):
    """True, wenn `kurz` als zusammenhängende Folge in `lang` vorkommt."""
    n = len(kurz)
    return n > 0 and any(lang[i:i + n] == kurz for i in range(len(lang) - n + 1))


def kern(falsch, richtig):
    """Zerlegt einen Lösungseintrag in das, was sich ändert, und seinen Kontext.

    „kurz, das sie“ / „kurz, dass sie“ -> alt [das], neu [dass], davor „,“, danach „sie“.
    „Gefühl dass“ / „Gefühl, dass“     -> alt [],    neu [,],    davor „Gefühl“, danach „dass“.
    """
    f, r = tokens(falsch), tokens(richtig)
    vorn = 0
    while vorn < min(len(f), len(r)) and f[vorn] == r[vorn]:
        vorn += 1
    hinten = 0
    while hinten < min(len(f), len(r)) - vorn and f[-1 - hinten] == r[-1 - hinten]:
        hinten += 1
    return {"alt": f[vorn:len(f) - hinten], "neu": r[vorn:len(r) - hinten],
            "davor": r[vorn - 1] if vorn else None,
            "danach": r[len(r) - hinten] if hinten else None}


def _ist_wort(token):
    return re.match(r"\w", token) is not None


def _gemeinsam(a, b):
    return len(set(a) & set(b))


def trifft(fund, fehler):
    """Güte, mit der ein Fund zu einem Lösungsfehler passt; 0 heißt: passt nicht.

    Ersetzung (Wort ändert sich): Der Vorschlag muss ein neues Wort enthalten und die
    Lesung ein altes. Eingefügtes Satzzeichen: Der Vorschlag muss das Zeichen direkt
    neben einem der beiden Nachbarwörter enthalten; ein bloßes Komma genügt nicht.
    """
    k = kern(fehler["falsch"], fehler["richtig"])
    vorschlag, gelesen = tokens(fund["vorschlag"]), tokens(fund["gelesen"])
    alte = [t for t in k["alt"] if _ist_wort(t) and t not in k["neu"]]
    neue = [t for t in k["neu"] if _ist_wort(t) and t not in k["alt"]]
    if alte or neue:
        if neue and not any(t in vorschlag for t in neue):
            return 0
        if alte and not any(t in gelesen for t in alte):
            return 0
    else:
        if not k["neu"]:
            return 0
        nachbarn = []
        if k["davor"]:
            nachbarn.append([k["davor"]] + k["neu"])
        if k["danach"]:
            nachbarn.append(k["neu"] + [k["danach"]])
        if not any(enthaelt(vorschlag, folge) for folge in nachbarn):
            return 0
    guete = 1 + _gemeinsam(vorschlag, tokens(fehler["richtig"])) \
              + _gemeinsam(gelesen, tokens(fehler["falsch"]))
    return guete + (0.5 if fund["kategorie"] == fehler["kategorie"] else 0)


def zuordnen(funde, fehler):
    """Gibt ({fund_id: [fehler_ids]}, {fund_ids der Dubletten}) zurück.

    Jeder Fund bekommt den am besten passenden noch freien Fehler. Enthält sein Vorschlag
    die vollständige richtige Schreibung weiterer freier Fehler, deckt er diese mit ab
    (ein Fund für zwei benachbarte Fehler). Ein Fund, der nur auf schon vergebene Fehler
    passt, ist eine Dublette: weder gefunden noch erfunden.
    """
    zuordnung, dubletten, vergeben = {}, set(), set()
    for f in funde:
        guete = {e["id"]: trifft(f, e) for e in fehler}
        treffer = [e for e in fehler if guete[e["id"]] > 0]
        if not treffer:
            continue
        frei = [e for e in treffer if e["id"] not in vergeben]
        if not frei:
            dubletten.add(f["id"])
            continue
        bester = max(frei, key=lambda e: guete[e["id"]])
        vorschlag = tokens(f["vorschlag"])
        ids = [bester["id"]] + [e["id"] for e in frei
                                if e is not bester and enthaelt(vorschlag, tokens(e["richtig"]))]
        zuordnung[f["id"]] = ids
        vergeben.update(ids)
    return zuordnung, dubletten


def bild_auswerten(erg, loesung, klicks):
    """Messwerte für ein Ergebnis.

    Klicks je Fund: {"sitzt": bool, "urteil": "erfunden" | "echt" | "fehler:<id>"}.
    „urteil“ gibt es nur für Funde, die nicht automatisch zugeordnet wurden.
    """
    funde, fehler = erg["funde"], loesung["fehler"]
    zuordnung, dubletten = zuordnen(funde, fehler)
    stamm = f"{erg['verfahren']}/{Path(erg['bild']).stem}"
    ausfall = bool(erg.get("fehlermeldung"))

    def klick(f):
        return klicks.get(f"{stamm}/{f['id']}", {})

    gefundene_ids = {nr for ids in zuordnung.values() for nr in ids}
    zutreffend = [f for f in funde if f["id"] in zuordnung]
    erfundene = []
    for f in funde:
        if f["id"] in zuordnung or f["id"] in dubletten:
            continue
        urteil = klick(f).get("urteil") or ""
        if urteil == "echt":
            zutreffend.append(f)
        elif urteil.startswith("fehler:"):
            gefundene_ids.add(int(urteil.split(":")[1]))
            zutreffend.append(f)
        else:
            erfundene.append(f)
    geprueft = [f for f in zutreffend if "sitzt" in klick(f)]

    gelesen = woerter(erg.get("transkription"))
    lesbar = [] if ausfall else [e for e in fehler if e["kategorie"] in ("R", "Gr")]
    nutzung = erg.get("nutzung") or {}

    def ausgeloest(falle):
        w = woerter(falle)
        return any(enthaelt(woerter(f["gelesen"]), w) and not enthaelt(woerter(f["vorschlag"]), w)
                   for f in funde)

    return {
        "seiten": 1,
        "fehler_gesamt": len(fehler),
        "gefunden": len(gefundene_ids),
        "erfunden": len(erfundene),
        "erfundene": erfundene,
        "dubletten": len(dubletten),
        "verworfen": erg.get("verworfen", 0),
        "lesetreu": sum(enthaelt(gelesen, woerter(e["falsch"])) for e in lesbar),
        "lesetreue_gesamt": len(lesbar),
        "fallen": sum(ausgeloest(falle) for falle in loesung["fallen"]),
        "fallen_gesamt": len(loesung["fallen"]),
        "platz_sitzt": sum(klick(f)["sitzt"] is True for f in geprueft),
        "platz_geprueft": len(geprueft),
        "platz_offen": len(zutreffend) - len(geprueft),
        "ausfall": 1 if ausfall else 0,
        "dauer_s": erg.get("dauer_s", 0),
        "eingabe": nutzung.get("eingabe", 0),
        "ausgabe": nutzung.get("ausgabe", 0),
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
    """Erfundene Fehler werden nur auf Seiten ohne Ausfall bezogen."""
    return {
        "gefunden": _anteil(summe["gefunden"], summe["fehler_gesamt"]),
        "erfunden_pro_seite": _anteil(summe["erfunden"], summe["seiten"] - summe["ausfall"]),
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
