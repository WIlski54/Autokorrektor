"""Erzeugt bericht.html aus der Auswertung."""
from html import escape

from korrektor.auswertung import KATEGORIEN, bestanden, kennzahlen


def prozent(wert):
    return "–" if wert is None else f"{round(wert * 100)} %"


def _zeile(name, summe, schwellen, urteil):
    k = kennzahlen(summe)
    zellen = [
        escape(name), str(summe["seiten"]), prozent(k["lesetreue"]), prozent(k["gefunden"]),
        "–" if k["erfunden_pro_seite"] is None else f"{k['erfunden_pro_seite']:.1f}",
        prozent(k["platzierung"]) + (f" ({summe['platz_offen']} offen)" if summe["platz_offen"] else ""),
        prozent(k["fallen"]),
        " · ".join(f"{kat} {summe['nach_kategorie'][kat][0]}/{summe['nach_kategorie'][kat][1]}"
                   for kat in KATEGORIEN),
        str(summe["ausfall"]),
        f"{summe['dauer_s'] / summe['seiten']:.1f} s" if summe["seiten"] else "–",
        f"{summe['eingabe']} / {summe['ausgabe']}",
    ]
    if urteil:
        zellen.append("bestanden" if bestanden(k, schwellen) else "nicht bestanden")
    else:
        zellen.append("")
    return "<tr>" + "".join(f"<td>{z}</td>" for z in zellen) + "</tr>"


def html(auswertung, schwellen, ausschnitte):
    """`ausschnitte`: {(verfahren, bildname, fund_id): relativer Bildpfad}."""
    kopf = ["Verfahren", "Seiten", "Lesetreue", "Gefunden", "Erfunden/Seite", "Platzierung",
            "Fallen ausgelöst", "Nach Kategorie", "Ausfälle", "Dauer/Seite",
            "Tokens ein/aus", "Urteil"]
    zeilen, fehlgriffe = [], []
    for name, teil in sorted(auswertung.items()):
        zeilen.append(_zeile(name, teil["gesamt"], schwellen, True))
        for aufnahme in ("gerade", "schraeg"):
            if teil[aufnahme]:
                zeilen.append(_zeile(f"{name} – nur {aufnahme}", teil[aufnahme], schwellen, False))
        for bildname, fund in teil["erfundene"]:
            pfad = ausschnitte.get((name, bildname, fund["id"]))
            bild = f'<br><img src="{escape(pfad)}" style="max-height:80px">' if pfad else ""
            fehlgriffe.append(
                f"<li><b>{escape(name)}</b>, {escape(bildname)}: {escape(fund['kategorie'])} "
                f"„{escape(fund['gelesen'])}“ → „{escape(fund['vorschlag'])}“{bild}</li>")
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Korrektor – Bericht</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; }}
  table {{ border-collapse: collapse; }}
  td, th {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; }}
  th {{ background: #eee; }}
  li {{ margin: 10px 0; }}
</style></head><body>
<h1>Korrektor – Machbarkeitstest</h1>
<p>Schwellen: mindestens {prozent(schwellen['gefunden_min'])} gefunden, höchstens
{schwellen['erfunden_pro_seite_max']:.1f} erfundene Fehler pro Seite, mindestens
{prozent(schwellen['platzierung_min'])} richtig platziert. Text H zählt nicht mit.
Die Platzierung berücksichtigt nur Funde, die auf der Prüfseite bewertet wurden.</p>
<table><tr>{''.join(f'<th>{k}</th>' for k in kopf)}</tr>
{''.join(zeilen)}</table>
<h2>Erfundene Fehler</h2>
<ul>{''.join(fehlgriffe) or '<li>keine</li>'}</ul>
</body></html>"""
