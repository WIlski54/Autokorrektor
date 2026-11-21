"""Lokale Prüfseite: zeigt Fotos mit Rahmen und speichert die Klicks zur Platzierung.

Start: python pruefseite.py   ->   http://127.0.0.1:5000
"""
import json
from pathlib import Path

from flask import Flask, Response, jsonify, request

from korrektor import bild
from korrektor.auswertung import klicks_laden, loesung_laden, zuordnen

WURZEL = Path(__file__).parent
app = Flask(__name__)

SEITE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Korrektor – Prüfseite</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; display: grid;
         grid-template-columns: minmax(0, 1fr) 420px; height: 100vh; }
  #links { overflow: auto; padding: 12px; background: #f3f3f3; }
  #rechts { overflow: auto; padding: 12px; border-left: 1px solid #ccc; }
  #buehne { position: relative; }
  #buehne img { width: 100%; display: block; }
  .rahmen { position: absolute; border: 2px solid #d00; background: rgba(221,0,0,.12);
            box-sizing: border-box; cursor: pointer; }
  .rahmen.luecke { border-color: #06c; background: rgba(0,102,204,.18); }
  .rahmen.aktiv { border-width: 4px; background: rgba(255,200,0,.35); }
  .fund { border: 1px solid #ccc; border-radius: 6px; padding: 8px; margin: 8px 0; }
  .fund.aktiv { border-color: #e6a700; background: #fff8e0; }
  .fund.offen { border-left: 6px solid #888; }
  button { margin: 4px 4px 0 0; padding: 4px 10px; }
  button.gewaehlt { background: #2a7; color: #fff; }
  select { width: 100%; padding: 6px; margin-bottom: 8px; }
  small { color: #555; }
</style></head><body>
<div id="links"><div id="buehne"><img id="foto"></div></div>
<div id="rechts">
  <select id="auswahl"></select>
  <div id="stand"></div>
  <div id="liste"></div>
</div>
<script>
let daten, aktuell = 0;
const el = id => document.getElementById(id);
const stamm = e => e.verfahren + "/" + e.bild.replace(/\\.[^.]+$/, "");

async function laden() {
  daten = await (await fetch("/daten")).json();
  el("auswahl").innerHTML = daten.ergebnisse.map((e, i) =>
    `<option value="${i}">${e.bild} – ${e.verfahren} (${e.funde.length} Funde)</option>`).join("");
  el("auswahl").onchange = ev => { aktuell = +ev.target.value; zeigen(); };
  zeigen();
}

function zeigen() {
  const e = daten.ergebnisse[aktuell];
  if (!e) { el("liste").textContent = "Keine Ergebnisse vorhanden."; return; }
  el("foto").src = "/foto/" + encodeURIComponent(e.bild);
  document.querySelectorAll(".rahmen").forEach(r => r.remove());
  const [bb, bh] = e.bildgroesse;
  let offen = 0;
  el("liste").innerHTML = "";
  for (const f of e.funde) {
    const schluessel = stamm(e) + "/" + f.id;
    const klick = daten.klicks[schluessel] || {};
    const [x, y, b, h] = f.anker.rahmen;
    const r = document.createElement("div");
    r.className = "rahmen " + f.anker.typ;
    r.id = "r" + f.id;
    r.style.cssText = `left:${x / bb * 100}%;top:${y / bh * 100}%;` +
                      `width:${b / bb * 100}%;height:${h / bh * 100}%`;
    r.onclick = () => hervorheben(f.id, true);
    el("buehne").appendChild(r);

    const braucht_echt = !f.zugeordnet;
    const fertig = "sitzt" in klick || (braucht_echt && klick.echt === false);
    if (!fertig) offen++;
    const karte = document.createElement("div");
    karte.className = "fund" + (fertig ? "" : " offen");
    karte.id = "f" + f.id;
    karte.onmouseenter = () => hervorheben(f.id, false);
    karte.innerHTML = `<b>${f.id}. ${f.kategorie}</b> „${f.gelesen}“ → „${f.vorschlag}“
      ${f.unsicher_gelesen ? "<br><small>unsicher gelesen</small>" : ""}
      ${braucht_echt ? "<br><small>steht nicht in der Lösung:</small><br>" +
        knopf(schluessel, "echt", true, "tatsächlich ein Fehler", klick) +
        knopf(schluessel, "echt", false, "erfunden", klick) : ""}
      <br><small>Platzierung:</small><br>
      ${knopf(schluessel, "sitzt", true, "sitzt", klick)}
      ${knopf(schluessel, "sitzt", false, "sitzt nicht", klick)}`;
    el("liste").appendChild(karte);
  }
  el("stand").innerHTML = `<small>${offen} von ${e.funde.length} Funden noch offen` +
    (e.fehlermeldung ? ` · Ausfall: ${e.fehlermeldung}` : "") + `</small>`;
}

function knopf(schluessel, feld, wert, text, klick) {
  const gewaehlt = klick[feld] === wert ? "gewaehlt" : "";
  return `<button class="${gewaehlt}" onclick="klicken('${schluessel}','${feld}',${wert})">${text}</button>`;
}

async function klicken(schluessel, feld, wert) {
  await fetch("/klick", {method: "POST", headers: {"Content-Type": "application/json"},
                         body: JSON.stringify({schluessel, feld, wert})});
  (daten.klicks[schluessel] ||= {})[feld] = wert;
  zeigen();
}

function hervorheben(id, rollen) {
  document.querySelectorAll(".aktiv").forEach(n => n.classList.remove("aktiv"));
  el("r" + id).classList.add("aktiv");
  el("f" + id).classList.add("aktiv");
  (rollen ? el("f" + id) : el("r" + id)).scrollIntoView({block: "nearest"});
}

laden();
</script></body></html>"""


@app.get("/")
def seite():
    return SEITE


@app.get("/daten")
def daten():
    ergebnisse = []
    for datei in sorted((WURZEL / "ergebnisse").glob("*/*.json")):
        erg = json.loads(datei.read_text(encoding="utf-8"))
        loesung = loesung_laden(WURZEL, erg["bild"])
        zuordnung = zuordnen(erg["funde"], loesung["fehler"]) if loesung else {}
        for f in erg["funde"]:
            f["zugeordnet"] = f["id"] in zuordnung
        ergebnisse.append(erg)
    return jsonify({"ergebnisse": ergebnisse, "klicks": klicks_laden(WURZEL)})


@app.get("/foto/<name>")
def foto(name):
    pfad = WURZEL / "fotos" / Path(name).name
    return Response(bild.als_jpeg(bild.offen(pfad)), mimetype="image/jpeg")


@app.post("/klick")
def klick():
    eingang = request.get_json()
    klicks = klicks_laden(WURZEL)
    klicks.setdefault(eingang["schluessel"], {})[eingang["feld"]] = eingang["wert"]
    datei = WURZEL / "pruefseite" / "klicks.json"
    datei.parent.mkdir(exist_ok=True)
    datei.write_text(json.dumps(klicks, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
