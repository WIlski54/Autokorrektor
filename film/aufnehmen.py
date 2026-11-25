"""Nimmt den stummen Präsentationsfilm des Korrektors auf.

Start (aus dem Projektordner):  .venv/Scripts/python.exe film/aufnehmen.py

Das Skript startet eine eigene Film-Instanz der Web-App (Port 5002, frischer Datenordner
`film/daten_film/`), bedient sie mit Playwright nach einem festen Drehbuch und schneidet
aus der Aufnahme `film/ausgabe/korrektor-demo.mp4` und je Kapitel eine eigene Datei.

Es geht dabei nichts an einen KI-Dienst: Der Aufruf des Verfahrens Gemini Carbon ist durch
eine Funktion ersetzt, die nach wenigen Sekunden ein früher gespeichertes Ergebnis aus
`ergebnisse/gemini/` zurückgibt. Die Datei `.env` wird nicht gelesen.
"""
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from pathlib import Path
from urllib.parse import urlencode

WURZEL = Path(__file__).resolve().parent.parent
FILM = Path(__file__).resolve().parent
DATEN = FILM / "daten_film"
AUSGABE = FILM / "ausgabe"
STANDBILDER = AUSGABE / "standbilder"
ADRESSE, PORT = "127.0.0.1", 5002
BASIS = f"http://{ADRESSE}:{PORT}"
BREITE, HOEHE, BILDRATE = 1920, 1080, 30
TEMPO = 0.88             # Faktor für die Pausen zwischen den Handgriffen (kleiner = zügiger)
SCHRIFT_PX = 20          # Grundschrift der App im Film (sonst 16): lesbar auf dem Beamer
# "betrachter": das PDF im eingebauten PDF-Betrachter von Chromium zeigen (braucht den
# vollen Browser); "bild": eine schlichte Seite mit den Seiten des PDF als Bild.
PDF_WEG = "betrachter"

sys.path.insert(0, str(WURZEL))

# Foto, Name beim Hochladen (bestimmt die Reihenfolge), künstliche Wartezeit in Sekunden
FOTOS = (
    ("E_1_gerade", "seite-1.jpg", 5.0),
    ("B_1_gerade", "seite-2.jpg", 6.4),
    ("B_2_gerade", "seite-3.jpg", 4.2),
    ("B_3_gerade", "seite-4.jpg", 4.6),
)

KAPITEL = (
    ("start", "Start", "Ein Prototyp, lokal auf dem eigenen Rechner"),
    ("aufgabe-anlegen", "Aufgabe anlegen", "Was soll die KI prüfen?"),
    ("fotos-zuordnen", "Fotos hochladen und zuordnen", "Keine Namen, nur Nummern"),
    ("analyse", "Analyse", "Nur das Bild geht an den Dienst"),
    ("vorschlaege-pruefen", "Vorschläge prüfen", "Die KI schlägt vor, der Mensch entscheidet"),
    ("gesamtbestaetigung", "Gesamtbestätigung", "Menschliche Aufsicht"),
    ("bestaetigung-verfaellt", "Die Bestätigung verfällt", "Jede Änderung hebt sie auf"),
    ("vorschau-und-ausgabe", "Vorschau und Ausgabe", "Keine Note, kein Hinweis auf KI"),
    ("stapeluebersicht", "Stapelübersicht", "Auswertung ohne Rangfolge"),
)
SCHLUSS = "Korrektor – Prototyp · github.com/WIlski54/Autokorrektor"


# --- Analyse aus der Konserve -----------------------------------------------------------------

def konserve_einrichten():
    """Ersetzt den Aufruf von Gemini Carbon durch gespeicherte Ergebnisse.

    Das Foto wird an seiner Bildgröße erkannt; die vier Fotos des Films sind verschieden groß.
    """
    from PIL import Image
    import korrektor.verfahren.gemini as gemini

    konserve = {}
    for name, _, wartezeit in FOTOS:
        ergebnis = json.loads((WURZEL / "ergebnisse" / "gemini" / f"{name}.json")
                              .read_text(encoding="utf-8"))
        with Image.open(WURZEL / "fotos" / f"{name}.jpg") as img:
            groesse = img.size
        if tuple(ergebnis["bildgroesse"]) != groesse:
            raise SystemExit(f"Das gespeicherte Ergebnis zu {name} passt nicht zur Bildgröße.")
        if groesse in konserve:
            raise SystemExit("Zwei Fotos des Films sind gleich groß; die Zuordnung ist nicht eindeutig.")
        konserve[groesse] = (ergebnis, wartezeit)

    def ausfuehren(bildpfad, einst):
        with Image.open(bildpfad) as img:
            groesse = img.size
        if groesse not in konserve:
            raise RuntimeError("Für dieses Foto gibt es im Film kein gespeichertes Ergebnis.")
        ergebnis, wartezeit = konserve[groesse]
        time.sleep(wartezeit)
        return {**ergebnis, "dauer_s": wartezeit, "fehlermeldung": None}

    gemini.ausfuehren = ausfuehren


# --- Film-Instanz der App ---------------------------------------------------------------------

KARTE_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Korrektor</title>
<style>
  html, body { height: 100%; margin: 0; }
  body { background: #f6f6f3; color: #1f2328; display: grid; place-items: center;
         font-family: system-ui, "Segoe UI", sans-serif; }
  .karte { width: 1400px; }
  .nummer { font-size: 34px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
            color: #1f5f8b; margin: 0 0 22px; }
  .strich { width: 120px; height: 6px; background: #1f5f8b; border-radius: 3px; margin: 0 0 40px; }
  h1 { font-size: 92px; line-height: 1.12; font-weight: 600; margin: 0 0 34px; }
  .unter { font-size: 44px; color: #5d6570; margin: 0; }
  .marke { position: fixed; left: 0; right: 0; bottom: 56px; text-align: center; font-size: 26px;
           font-weight: 700; color: #5d6570; letter-spacing: .02em; }
  .schluss h1 { font-size: 110px; }
  .schluss { text-align: center; }
  .schluss .strich { margin: 0 auto 40px; }
</style></head><body>
{% if schluss %}
<div class="karte schluss"><h1>Korrektor</h1><div class="strich"></div>
  <p class="unter">Prototyp · github.com/WIlski54/Autokorrektor</p></div>
{% else %}
<div class="karte"><p class="nummer">Kapitel {{ n }}</p><div class="strich"></div>
  <h1>{{ titel }}</h1><p class="unter">{{ unter }}</p></div>
<p class="marke">Korrektor</p>
{% endif %}
</body></html>"""

PDF_HTML = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>PDF-Ausgabe</title>
<style>
  body { margin: 0; background: #52565c; color: #fff; font-family: system-ui, "Segoe UI", sans-serif; }
  header { position: sticky; top: 0; background: #2f3236; padding: 18px 40px; font-size: 30px;
           font-weight: 600; box-shadow: 0 2px 8px rgba(0,0,0,.4); display: flex; gap: 24px;
           align-items: baseline; }
  header span { font-size: 22px; font-weight: 400; color: #c9cdd3; }
  main { padding: 36px 0 60px; display: grid; gap: 36px; justify-items: center; }
  img { display: block; width: 1240px; height: auto; background: #fff;
        box-shadow: 0 6px 30px rgba(0,0,0,.5); }
</style></head><body>
<header>PDF-Ausgabe: {{ name }} <span>{{ seiten }} {{ 'Seite' if seiten == 1 else 'Seiten' }}</span></header>
<main>{% for nr in range(1, seiten + 1) %}
  <img src="/film/pdfbild/{{ arbeit_id }}/{{ nr }}.jpg" alt="Seite {{ nr }} des PDF">{% endfor %}
</main></body></html>"""


def app_bauen():
    """Die Film-Instanz: frischer Datenordner, Einstellungen aus der Datei, Schein-Schlüssel."""
    from flask import Blueprint, Response, abort, render_template_string, request, send_file

    from webapp import app_erzeugen, ausgabe

    os.environ["GEMINI_API_KEY"] = "film-ohne-schluessel"  # nur damit `hindernis` nichts meldet
    with open(WURZEL / "einstellungen.toml", "rb") as datei:
        einst = tomllib.load(datei)
    if DATEN.exists():
        shutil.rmtree(DATEN)
    DATEN.mkdir(parents=True)
    konserve_einrichten()
    app = app_erzeugen(DATEN, einst)
    speicher = app.extensions["speicher"]

    film = Blueprint("film", __name__)

    @film.get("/film/karte")
    def karte():
        return render_template_string(KARTE_HTML, n=request.args.get("n"),
                                      titel=request.args.get("titel"),
                                      unter=request.args.get("unter"), schluss=False)

    @film.get("/film/schluss")
    def schluss():
        return render_template_string(KARTE_HTML, schluss=True)

    @film.get("/film/pdf/<name>")
    def pdf_inline(name):
        pfad = DATEN / "pdf" / name
        if not pfad.is_file() or pfad.parent != DATEN / "pdf":
            abort(404)
        return send_file(pfad, mimetype="application/pdf", as_attachment=False)

    @film.get("/film/pdfseiten/<int:arbeit_id>")
    def pdf_seiten(arbeit_id):
        arbeit = speicher.arbeit(arbeit_id)
        if arbeit is None:
            abort(404)
        return render_template_string(PDF_HTML, arbeit_id=arbeit_id, seiten=len(arbeit["seiten"]),
                                      name=f"Arbeit-{arbeit['kuerzel']}.pdf")

    @film.get("/film/pdfbild/<int:arbeit_id>/<int:nr>.jpg")
    def pdf_bild(arbeit_id, nr):
        arbeit = speicher.arbeit(arbeit_id)
        aufgabe = speicher.aufgabe(arbeit["aufgabe_id"]) if arbeit else None
        if aufgabe is None:
            abort(404)
        for platz, bild in enumerate(ausgabe.seitenbilder(speicher, aufgabe, arbeit), start=1):
            if platz == nr:
                puffer = io.BytesIO()
                bild.save(puffer, "JPEG", quality=92)
                return Response(puffer.getvalue(), mimetype="image/jpeg")
        abort(404)

    app.register_blueprint(film)
    return app


def server_starten(app):
    import logging

    from werkzeug.serving import make_server

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    try:
        server = make_server(ADRESSE, PORT, app, threaded=True)
    except OSError as fehler:
        raise SystemExit(f"Port {PORT} ist belegt ({fehler}). Läuft noch eine Film-Instanz?") from None
    threading.Thread(target=server.serve_forever, daemon=True, name="film-app").start()
    return server


# --- Einblendungen im Browser: Zeiger, Klick-Ring, Tastenanzeige ------------------------------

INIT_SKRIPT = r"""
(() => {
  if (window.__film) { return; }
  // nur im Hauptfenster und nicht im PDF-Betrachter (der besteht aus mehreren Rahmen)
  if (window !== window.top || location.pathname.startsWith('/film/pdf/')) { return; }
  const KARTE = location.pathname.startsWith('/film/karte') || location.pathname.startsWith('/film/schluss');
  const stil = document.createElement('style');
  stil.textContent = `
    __SCHRIFT__
    #film-ebene { position: fixed; inset: 0; width: 100vw; height: 100vh; max-width: none;
      max-height: none; margin: 0; padding: 0; border: 0; background: transparent;
      pointer-events: none; overflow: visible; color: inherit; }
    #film-ebene::backdrop { background: transparent; }
    #film-zeiger { position: fixed; left: 0; top: 0; width: 44px; height: 44px; margin: 0;
      pointer-events: none; will-change: transform;
      filter: drop-shadow(0 2px 3px rgba(0,0,0,.45)); }
    #film-zeiger.gedrueckt svg { transform: scale(.86); transform-origin: 4px 3px; }
    .film-ring { position: fixed; width: 20px; height: 20px; margin: -10px 0 0 -10px;
      border-radius: 50%; border: 5px solid #f08a00; pointer-events: none;
      animation: film-ring .55s ease-out forwards; }
    @keyframes film-ring { from { transform: scale(.6); opacity: .95; }
                           to { transform: scale(3.6); opacity: 0; } }
    #film-taste { position: fixed; left: 50%; bottom: 38px; transform: translateX(-50%);
      display: flex; align-items: center; gap: 18px; padding: 14px 28px 14px 16px;
      background: rgba(31,35,40,.93); color: #fff; border-radius: 16px;
      font: 600 30px/1.2 system-ui, "Segoe UI", sans-serif; white-space: nowrap;
      box-shadow: 0 6px 24px rgba(0,0,0,.35); opacity: 0; transition: opacity .18s; }
    #film-taste.an { opacity: 1; }
    #film-taste kbd { min-width: 52px; padding: 6px 14px; text-align: center; background: #fff;
      color: #1f2328; border-radius: 9px; border-bottom: 5px solid #b9bec6;
      font: 700 32px/1.2 system-ui, "Segoe UI", sans-serif; }
  `;
  const ebene = document.createElement('div');
  ebene.id = 'film-ebene';
  ebene.setAttribute('popover', 'manual');
  ebene.setAttribute('aria-hidden', 'true');
  const zeiger = document.createElement('div');
  zeiger.id = 'film-zeiger';
  zeiger.innerHTML = '<svg width="44" height="44" viewBox="0 0 22 22"><path d="M3 2 L3 17.5 L7.2 13.8 L10 20 L12.6 18.8 L9.8 12.8 L15.5 12.8 Z" fill="#1f2328" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  const taste = document.createElement('div');
  taste.id = 'film-taste';
  ebene.appendChild(taste);
  ebene.appendChild(zeiger);

  let ort = { x: 960, y: 620 };
  try { ort = JSON.parse(sessionStorage.getItem('film-zeiger')) || ort; } catch (e) {}
  function legen() { zeiger.style.transform = 'translate(' + (ort.x - 6) + 'px,' + (ort.y - 4) + 'px)'; }
  legen();

  function heben() {  // über alles andere in der obersten Ebene (auch über Dialoge)
    try { if (ebene.matches(':popover-open')) { ebene.hidePopover(); } ebene.showPopover(); } catch (e) {}
  }
  function einbauen() {
    if (!document.documentElement) { return false; }
    (document.head || document.documentElement).appendChild(stil);
    if (!document.body) { return false; }
    document.body.appendChild(ebene);
    if (KARTE) { zeiger.style.display = 'none'; }
    heben();
    return true;
  }
  if (document.documentElement) { (document.head || document.documentElement).appendChild(stil); }
  if (!einbauen()) { document.addEventListener('DOMContentLoaded', einbauen); }

  const zeigen = HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.showModal = function () {
    const wert = zeigen.apply(this, arguments);
    heben();
    return wert;
  };

  window.addEventListener('mousemove', (e) => {
    ort = { x: e.clientX, y: e.clientY };
    legen();
    try { sessionStorage.setItem('film-zeiger', JSON.stringify(ort)); } catch (f) {}
  }, true);
  window.addEventListener('mousedown', (e) => {
    zeiger.classList.add('gedrueckt');
    const ring = document.createElement('div');
    ring.className = 'film-ring';
    ring.style.left = e.clientX + 'px';
    ring.style.top = e.clientY + 'px';
    ebene.appendChild(ring);
    setTimeout(() => ring.remove(), 700);
  }, true);
  window.addEventListener('mouseup', () => zeiger.classList.remove('gedrueckt'), true);

  let uhr = null;
  window.__film = {
    taste(kuerzel, text, dauer) {
      taste.textContent = '';
      const k = document.createElement('kbd');
      k.textContent = kuerzel;
      taste.appendChild(k);
      if (text) { taste.appendChild(document.createTextNode(text)); }
      taste.classList.add('an');
      clearTimeout(uhr);
      uhr = setTimeout(() => taste.classList.remove('an'), dauer || 2400);
    },
    // Ob das Element ganz im Fenster liegt und an seiner Mitte nicht verdeckt ist.
    frei(element) {
      const r = element.getBoundingClientRect();
      if (r.top < 8 || r.left < 0 || r.bottom > innerHeight - 8 || r.right > innerWidth) { return false; }
      const oben = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return !!oben && (element === oben || element.contains(oben) || oben.contains(element));
    }
  };
})();
"""


class Regie:
    """Bedient die Seite wie eine Hand an Maus und Tastatur und merkt sich die Zeitpunkte."""

    def __init__(self, page):
        self.page = page
        self.null = time.monotonic()   # die Aufnahme beginnt mit dem Öffnen der Seite
        self.ort = (960.0, 620.0)
        self.kapitel = []              # (Nummer, Zeit in der Rohaufnahme)
        self.marken = []               # (Name, Zeit in der Rohaufnahme)
        self.nummer = 0

    # --- Zeit -------------------------------------------------------------------------------

    def jetzt(self):
        return time.monotonic() - self.null

    def pause(self, sekunden, fest=False):
        """Wartet; `fest` nimmt die Pause vom allgemeinen Tempo aus (Karten, Dialoge)."""
        self.page.wait_for_timeout(int(sekunden * (1 if fest else TEMPO) * 1000))

    def marke(self, name):
        self.marken.append((f"k{self.nummer:02d}-{name}", self.jetzt()))

    # --- Maus -------------------------------------------------------------------------------

    def bewegen(self, x, y, dauer=None):
        x0, y0 = self.ort
        weg = math.hypot(x - x0, y - y0)
        if weg < 1.5:
            return
        if dauer is None:
            dauer = min(1.4, max(0.4, 0.3 + weg / 1300))
        schritte = max(6, int(dauer * 60))
        for i in range(1, schritte + 1):
            t = i / schritte
            s = t * t * (3 - 2 * t)  # sanft anfahren und abbremsen
            self.page.mouse.move(x0 + (x - x0) * s, y0 + (y - y0) * s)
            time.sleep(dauer / schritte)
        self.ort = (float(x), float(y))

    def _finden(self, ziel):
        return self.page.locator(ziel).first if isinstance(ziel, str) else ziel

    def in_sicht(self, ziel):
        """Rollt weich, bis das Element im Fenster liegt."""
        element = self._finden(ziel)
        element.wait_for(state="visible")
        if not element.evaluate("e => window.__film.frei(e)"):
            element.evaluate("e => e.scrollIntoView({behavior: 'smooth', block: 'center'})")
            self.pause(0.9)
        return element

    def mitte(self, ziel, dx=0.5, dy=0.5):
        kasten = self.in_sicht(ziel).bounding_box()
        return kasten["x"] + kasten["width"] * dx, kasten["y"] + kasten["height"] * dy

    def zu(self, ziel, dx=0.5, dy=0.5, dauer=None):
        x, y = self.mitte(ziel, dx, dy)
        self.bewegen(x, y, dauer)

    def druecken(self):
        self.page.mouse.down()
        time.sleep(0.09)
        self.page.mouse.up()

    def klick(self, ziel, davor=0.45, danach=0.8, dx=0.5, dy=0.5):
        self.zu(ziel, dx, dy)
        self.pause(davor)
        self.druecken()
        self.pause(danach)

    def ziehen(self, x, y, dauer=1.1, danach=0.8):
        """Zieht mit gedrückter Taste von der jetzigen Stelle zur Stelle (x, y)."""
        self.pause(0.4)
        self.page.mouse.down()
        self.pause(0.25)
        self.bewegen(x, y, dauer)
        self.pause(0.3)
        self.page.mouse.up()
        self.pause(danach)

    def rollen(self, weg, tempo=520):
        """Rollt an der Stelle des Zeigers weich um `weg` Pixel (negativ: nach oben)."""
        schritt = math.copysign(max(4.0, tempo / 60), weg)
        rest = abs(weg)
        while rest > 0.5:
            stueck = min(abs(schritt), rest)
            self.page.mouse.wheel(0, math.copysign(stueck, weg))
            rest -= stueck
            time.sleep(1 / 60)

    # --- Tastatur ---------------------------------------------------------------------------

    def taste(self, taste, kuerzel, text, davor=0.5, danach=1.2):
        self.page.evaluate("([k, t]) => window.__film.taste(k, t)", [kuerzel, text])
        self.pause(davor)
        self.page.keyboard.press(taste)
        self.pause(danach)

    def tippen(self, text, takt=110):
        self.page.keyboard.type(text, delay=takt)

    # --- Kapitel ----------------------------------------------------------------------------

    def titelkarte(self, hinter_der_karte=None):
        """Zeigt die Karte des nächsten Kapitels etwa drei Sekunden.

        `hinter_der_karte()` läuft, während die Karte steht (für das, was nicht ins Bild soll).
        """
        self.nummer += 1
        _, titel, unter = KAPITEL[self.nummer - 1]
        self.page.goto(f"{BASIS}/film/karte?" + urlencode({"n": self.nummer, "titel": titel,
                                                           "unter": unter}))
        beginn = self.jetzt()
        self.kapitel.append((self.nummer, beginn))
        print(f"  Kapitel {self.nummer} – {titel} ({beginn:6.1f} s)", flush=True)
        if hinter_der_karte:
            hinter_der_karte()
        self.pause(max(0.2, 3.0 - (self.jetzt() - beginn)), fest=True)

    def auftritt(self, adresse, warten_auf=None):
        """Die erste Ansicht des Kapitels; sie bleibt etwa zwei Sekunden stehen."""
        self.page.goto(BASIS + adresse)
        if warten_auf:
            self.page.locator(warten_auf).first.wait_for(state="visible")
        self.pause(2.0, fest=True)


# --- Drehbuch ---------------------------------------------------------------------------------

def drehen(page, regie, app, hochladeordner):
    speicher = app.extensions["speicher"]
    r = regie
    page.mouse.move(*r.ort)

    # 1 – Start
    r.titelkarte()
    r.auftritt("/", ".hinweis")
    r.zu(".hinweis", dx=0.04, dy=0.92)
    r.pause(2.0)
    r.zu(".hinweis", dx=0.5, dy=0.92, dauer=2.2)
    r.marke("hinweis")
    r.pause(2.4)
    r.zu(".hinweis", dx=0.86, dy=0.92, dauer=1.8)
    r.pause(2.6)

    # 2 – Aufgabe anlegen
    r.titelkarte()
    r.auftritt("/", ".hinweis")
    r.klick("a.knopf.haupt", danach=1.6)
    r.klick("#titel", danach=0.4)
    r.tippen("Versuchsbeschreibung 9b")
    r.pause(0.9)
    r.zu("#fach", dx=0.3)
    r.pause(1.2)
    r.klick("#jahrgang", danach=0.4, dx=0.35)
    r.tippen("9")
    r.pause(1.0)
    schalter = page.locator(".schalterreihe .schalter")
    r.zu(schalter.nth(0))
    r.pause(0.9)
    r.zu(schalter.nth(1))
    r.pause(0.7)
    r.zu(schalter.nth(2))
    r.pause(0.9)
    r.klick(schalter.nth(2), danach=1.5)   # Grammatik aus …
    r.marke("schalter-aus")
    r.klick(schalter.nth(2), danach=1.2)   # … und wieder ein
    r.zu("#verfahren", dx=0.2)
    r.marke("formular")
    r.pause(2.4)
    r.klick("form.formular button[type=submit]", danach=0.2)
    page.wait_for_url(re.compile(r"/aufgabe/\d+/hochladen"))
    aufgabe_id = int(re.search(r"/aufgabe/(\d+)/", page.url).group(1))
    r.pause(1.6)

    # 3 – Fotos hochladen und zuordnen
    hochladen = f"/aufgabe/{aufgabe_id}/hochladen"
    r.titelkarte()
    r.auftritt(hochladen, "#ablegefeld")
    r.zu("#ablegefeld", dy=0.3)
    r.pause(1.4)
    r.zu("label[for=dateien]")
    r.pause(0.7)
    page.set_input_files("#dateien", [str(hochladeordner / name) for _, name, _ in FOTOS])
    page.locator("#reihe .karte").nth(len(FOTOS) - 1).wait_for(state="visible")
    page.wait_for_function("document.getElementById('speicherstand').textContent === 'Gespeichert'")
    page.wait_for_function(
        "Array.from(document.querySelectorAll('#reihe img')).every(b => b.complete && b.naturalWidth)")
    r.pause(0.8)
    r.zu("#reihe", dy=0.5, dauer=1.2)
    r.marke("vier-fotos")
    r.pause(2.4)
    r.zu("#zusammenfassung")
    r.pause(1.6)
    marke = page.locator("#reihe .trennmarke").first
    r.zu(marke)
    r.pause(1.3)
    r.druecken()
    page.wait_for_function(
        "document.getElementById('zusammenfassung').textContent === '4 Fotos in 3 Arbeiten'")
    r.pause(2.2)
    r.zu("#reihe .gruppenkopf")
    r.marke("verbunden")
    r.pause(1.8)
    r.zu("#zusammenfassung")
    r.pause(2.6)

    # 4 – Analyse
    r.titelkarte()
    r.auftritt(hochladen, "#reihe .karte")
    r.zu("#start")
    r.pause(1.2)
    r.druecken()
    page.wait_for_url(re.compile(rf"/aufgabe/{aufgabe_id}$"))
    page.locator("#kacheln .kachel").nth(2).wait_for(state="visible")
    r.pause(1.2)
    r.zu("#gesamttext", dx=0.2)
    r.marke("analyse-laeuft")
    r.pause(1.8)
    r.zu(page.locator("#kacheln .kachel [data-rolle=status]").nth(1), dy=1.6, dauer=1.2)
    page.wait_for_function(
        "Array.from(document.querySelectorAll('#kacheln [data-rolle=status]'))"
        ".every(e => e.textContent === 'analysiert')", timeout=60000)
    r.pause(1.2)
    r.zu("#gesamttext", dx=0.25)
    r.marke("analysiert")
    r.pause(3.0)

    # 5 – Vorschläge prüfen
    stapel = f"/aufgabe/{aufgabe_id}"
    arbeiten = speicher.arbeiten(aufgabe_id)
    arbeit_id = arbeiten[1]["id"]
    r.titelkarte()
    r.auftritt(stapel, "#kacheln .kachel")
    r.klick(page.locator("#kacheln .kachel").nth(1).locator("h2 a"), danach=0.2)
    page.wait_for_url(re.compile(rf"/arbeit/{arbeit_id}"))
    page.locator("#zeichenliste li").first.wait_for(state="visible")
    r.pause(2.2)
    zeichen = {z["gelesen"]: z["id"] for z in
               json.loads(page.locator("#arbeit-daten").text_content())["zeichen"]}

    def rahmen(gelesen):
        return page.locator(f'#rahmenebene .rahmen[data-zeichen="{zeichen[gelesen]}"]')

    def eintrag(gelesen):
        return page.locator(f'#zeichenliste li[data-zeichen="{zeichen[gelesen]}"]')

    def gewaehlt(gelesen):
        page.wait_for_function(
            "id => { const e = document.querySelector('#zeichenliste li.gewaehlt');"
            " return e && e.getAttribute('data-zeichen') === String(id); }", arg=zeichen[gelesen])

    r.zu(rahmen("Baterie"), dy=1.5)
    r.pause(1.0)
    r.zu(eintrag("Baterie").locator(".eintrag-wahl"), dx=0.6)
    r.marke("erster-vorschlag")
    r.pause(1.6)
    r.taste("b", "B", "bestätigen")          # „Baterie“
    gewaehlt("Zu erst")
    r.pause(0.8)
    r.taste("b", "B", "bestätigen")          # „Zu erst“
    gewaehlt("enden")
    r.marke("zwei-bestaetigt")
    r.pause(1.0)
    r.taste("e", "E", "ändern", danach=1.0)  # „enden“: Vorschlag ergänzen
    feld = eintrag("enden").locator("form.zeichenformular input[type=text]")
    r.klick(feld, danach=0.3, dx=0.7)
    page.keyboard.press("End")
    r.tippen(" (Nomen)")
    r.marke("aendern")
    r.pause(1.2)
    r.klick(eintrag("enden").locator("form.zeichenformular button[type=submit]"), danach=0.3)
    gewaehlt("geleuchtet weil")
    r.pause(1.3)
    r.taste("n", "N", "nächster offener Vorschlag")
    gewaehlt("Büro klammer")
    r.zu(rahmen("Büro klammer"), dy=1.5)
    r.pause(1.4)
    r.taste("v", "V", "verwerfen")
    gewaehlt("leited")
    r.marke("verworfen")
    r.pause(1.0)

    # einen Rahmen mit der Maus ein Stück verschieben
    x, y = r.mitte(rahmen("leited"))
    r.bewegen(x, y)
    r.ziehen(x - 16, y + 8, dauer=0.9, danach=1.3)
    r.marke("verschoben")

    # ein eigenes Zeichen setzen: Rahmen um „war an“, Kürzel A (Ausdruck)
    r.taste("s", "S", "Zeichen setzen", danach=1.0)
    seite = speicher.arbeit(arbeit_id)["seiten"][0]

    def lage_lesen():
        return page.evaluate(
            "() => { const f = document.getElementById('foto').getBoundingClientRect();"
            " const r = document.getElementById('rollfeld').getBoundingClientRect();"
            " return {l: f.left, t: f.top, b: f.width, h: f.height, oben: r.top, unten: r.bottom,"
            " links: r.left, rechts: r.right}; }")

    def im_fenster(lage, bx, by):
        return (lage["l"] + bx * lage["b"] / seite["breite"],
                lage["t"] + by * lage["h"] / seite["hoehe"])

    stelle = (706, 1208, 928, 1304)   # „war an“ in Pixeln des Fotos
    lage = lage_lesen()
    mitte_y = im_fenster(lage, 0, (stelle[1] + stelle[3]) / 2)[1]
    versatz = mitte_y - (lage["oben"] + lage["unten"]) / 2
    if abs(versatz) > 60:             # die Stelle in die Mitte des Ausschnitts rollen
        r.bewegen((lage["links"] + lage["rechts"]) / 2 + 250, (lage["oben"] + lage["unten"]) / 2)
        r.rollen(versatz, tempo=380)
        r.pause(0.6)
        lage = lage_lesen()
    x1, y1 = im_fenster(lage, stelle[0], stelle[1])
    x2, y2 = im_fenster(lage, stelle[2], stelle[3])
    if y1 < lage["oben"] + 10 or y2 > lage["unten"] - 10:
        raise SystemExit("Die Stelle für das eigene Zeichen liegt nicht im sichtbaren Ausschnitt.")
    r.bewegen(x1, y1)
    r.ziehen(x2, y2, dauer=1.0, danach=0.9)
    page.locator("#neu-formular").wait_for(state="visible")
    r.zu("#neu-kuerzel", dx=0.4)
    r.pause(0.8)
    page.select_option("#neu-kuerzel", "A")
    r.pause(1.0)
    r.klick("#neu-vorschlag", danach=0.3, dx=0.4)
    r.tippen("leuchtete")
    r.marke("eigenes-zeichen")
    r.pause(1.0)
    r.klick("#neu-setzen", danach=1.8)
    r.marke("gesetzt")

    # Verworfene kurz zeigen
    page.locator("#listenspalte").evaluate("e => e.scrollTo({top: 0, behavior: 'smooth'})")
    r.pause(0.7)
    r.klick("label.schalter.schmal", danach=1.0, dx=0.3)
    r.zu(rahmen("Büro klammer"), dy=1.6)
    r.marke("verworfene-gezeigt")
    r.pause(2.2)
    r.klick("label.schalter.schmal", danach=1.8, dx=0.3)

    # 6 – Gesamtbestätigung
    arbeit_adresse = f"/arbeit/{arbeit_id}"
    r.titelkarte()
    r.auftritt(arbeit_adresse, "#zeichenliste li")
    r.zu("#arbeit-offen")
    r.pause(1.4)
    r.klick("#rest-knopf", davor=0.8, danach=0.3)
    page.locator("#rest-dialog[open]").wait_for(state="visible")
    r.marke("dialog-rest")
    r.pause(1.4)
    r.zu("#rest-text", dx=0.4, dy=0.6)
    r.pause(2.4)
    r.klick("#rest-ja", davor=0.8, danach=0.3)
    page.wait_for_function("document.getElementById('arbeit-offen').textContent.includes('kein Vorschlag')")
    r.pause(2.0)
    r.klick("#gesamt-knopf", davor=0.9, danach=0.3)
    page.locator("#gesamt-dialog[open]").wait_for(state="visible")
    r.pause(0.6)
    r.zu("#gesamt-dialog .zahlenliste", dx=0.75, dy=0.5)
    r.marke("dialog-gesamt")
    r.pause(5.0, fest=True)
    r.klick('#gesamt-dialog button[value="ja"]', davor=0.9, danach=0.3)
    page.locator("#bestaetigt-anzeige").wait_for(state="visible")
    r.pause(0.8)
    r.zu("#bestaetigt-anzeige", dy=0.9)
    r.marke("bestaetigt")
    r.pause(2.6)
    r.zu("#pdf-knopf", dy=-0.3)
    r.pause(2.0)

    # 7 – Die Bestätigung verfällt
    r.titelkarte()
    r.auftritt(arbeit_adresse, "#bestaetigt-anzeige")
    r.zu("#bestaetigt-anzeige", dy=0.9)
    r.pause(1.6)
    x, y = r.mitte(rahmen("Baterie"))
    r.bewegen(x, y)
    r.ziehen(x + 18, y + 10, dauer=0.9, danach=0.3)
    page.locator("#bestaetigt-anzeige").wait_for(state="hidden")
    r.pause(1.0)
    r.zu(".blaettern", dx=-0.25, dy=0.5)   # dorthin, wo die Anzeige eben noch stand
    r.marke("verfallen")
    r.pause(2.2)
    r.zu("#pdf-knopf")
    r.marke("pdf-inaktiv")
    r.pause(2.6)
    r.klick("#gesamt-knopf", davor=0.9, danach=0.3)
    page.locator("#gesamt-dialog[open]").wait_for(state="visible")
    r.marke("dialog-gesamt")
    r.pause(2.4)
    r.klick('#gesamt-dialog button[value="ja"]', davor=0.8, danach=0.3)
    page.locator("#bestaetigt-anzeige").wait_for(state="visible")
    r.pause(0.8)
    r.zu("#bestaetigt-anzeige", dy=0.9)
    r.pause(2.2)

    # 8 – Vorschau und Ausgabe
    r.titelkarte()
    r.auftritt(arbeit_adresse, "#bestaetigt-anzeige")
    r.zu("#ansicht-vorschau", dy=1.6)
    r.pause(0.8)
    r.taste("p", "P", "Vorschau der Ausgabe", danach=0.3)
    page.locator("#vorschaubild").wait_for(state="visible")
    r.pause(0.8)
    r.zu("#rollfeld", dx=0.5, dy=0.45)
    r.marke("vorschau-oben")
    r.pause(2.6)
    weg = page.evaluate("() => { const f = document.getElementById('rollfeld');"
                        " return f.scrollHeight - f.clientHeight; }")
    r.rollen(weg * 0.5, tempo=420)
    r.marke("vorschau-mitte")
    r.pause(1.8)
    r.rollen(weg * 0.5 + 20, tempo=420)
    r.marke("fehleruebersicht")
    r.pause(3.6)
    r.rollen(-(weg + 40), tempo=900)
    r.pause(1.2)
    pdf_ordner = DATEN / "pdf"
    pdf_ordner.mkdir(exist_ok=True)
    r.zu("#pdf-knopf")
    r.pause(1.0)
    with page.expect_download() as geladen:
        r.druecken()
    name = geladen.value.suggested_filename
    geladen.value.save_as(pdf_ordner / name)
    r.marke("pdf-ausgeben")
    r.pause(1.4)
    if PDF_WEG == "betrachter":
        page.goto(f"{BASIS}/film/pdf/{name}")
        r.pause(2.0)
        r.bewegen(1100, 560)   # im Betrachter gibt es den eingeblendeten Zeiger nicht
        r.marke("pdf")
        r.pause(3.4)
        r.rollen(420, tempo=260)
        r.marke("pdf-unten")
        r.pause(3.6)
        r.rollen(-420, tempo=500)
    else:
        page.goto(f"{BASIS}/film/pdfseiten/{arbeit_id}")
        page.wait_for_function(
            "Array.from(document.images).every(b => b.complete && b.naturalWidth)")
        r.pause(1.0)
        r.bewegen(1700, 520)
        r.marke("pdf")
        r.pause(3.0)
        weg = page.evaluate("document.documentElement.scrollHeight - innerHeight")
        r.rollen(weg * 0.55, tempo=420)
        r.pause(1.6)
        r.rollen(weg * 0.45 + 20, tempo=420)
        r.marke("pdf-unten")
        r.pause(3.2)
        r.rollen(-(weg + 40), tempo=1000)
    r.pause(1.2)

    # 9 – Stapelübersicht; hinter der Titelkarte wird Arbeit 01 vollständig bestätigt
    def arbeit_01_bestaetigen():
        erste = arbeiten[0]["id"]
        speicher.rest_bestaetigen(erste)
        speicher.arbeit_bestaetigen(erste)

    r.titelkarte(hinter_der_karte=arbeit_01_bestaetigen)
    r.auftritt(stapel, "#kacheln .kachel")
    r.zu("#gesamttext", dx=0.3)
    r.marke("zwei-von-drei")
    r.pause(2.6)
    r.zu(page.locator("#kacheln .kachel [data-rolle=bestaetigt]").nth(0), dx=0.3)
    r.pause(1.2)
    r.zu(page.locator("#kacheln .kachel [data-rolle=bestaetigt]").nth(2), dx=0.3)
    r.pause(1.4)
    r.klick(page.locator(".knopfreihe.oben a", has_text="Stapelübersicht"), danach=0.2)
    page.wait_for_url(re.compile(r"/uebersicht$"))
    r.pause(2.0)
    r.zu(".zahlkarten", dy=0.5)
    r.marke("fehlerarten")
    r.pause(3.0)
    weg = page.evaluate("document.documentElement.scrollHeight - innerHeight")
    if weg > 0:
        r.rollen(weg * 0.5, tempo=380)
    r.zu("#woerter-titel", dx=0.6, dy=2.5)
    r.marke("fehlerwoerter")
    r.pause(3.4)
    if weg > 0:
        r.rollen(weg * 0.5 + 20, tempo=380)
    r.zu("#arbeiten-titel + table", dx=0.5, dy=1.25)
    r.marke("tabelle")
    r.pause(4.0)
    page.goto(f"{BASIS}/film/schluss")
    r.marke("schluss")
    r.pause(4.2, fest=True)
    return r.jetzt()


# --- Schnitt ----------------------------------------------------------------------------------

def ffmpeg(*argumente):
    befehl = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, argumente)]
    subprocess.run(befehl, check=True)


def schneiden(roh, regie, ende):
    """Aus der Rohaufnahme: der Film mit Kapitelmarken, je Kapitel eine Datei, Standbilder."""
    beginn = regie.kapitel[0][1] + 0.25      # die erste Karte steht; davor ist die Seite leer
    zeiten = [max(0.0, zeit + 0.12 - beginn) for _, zeit in regie.kapitel]
    zeiten[0] = 0.0
    dauer = ende - beginn
    grenzen = zeiten + [dauer]

    meta = AUSGABE / "kapitel.ffmeta"
    zeilen = [";FFMETADATA1", "title=Korrektor – Demo"]
    for (nummer, _), von, bis in zip(regie.kapitel, grenzen, grenzen[1:]):
        zeilen += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={round(von * 1000)}",
                   f"END={round(bis * 1000)}", f"title={nummer} – {KAPITEL[nummer - 1][1]}"]
    meta.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    film = AUSGABE / "korrektor-demo.mp4"
    bild = f"fps={BILDRATE},scale={BREITE}:{HOEHE}:flags=lanczos,format=yuv420p"
    kodierung = ["-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
                 "-an", "-movflags", "+faststart"]
    ffmpeg("-ss", f"{beginn:.3f}", "-t", f"{dauer:.3f}", "-i", roh, "-i", meta,
           "-map", "0:v:0", "-map_metadata", "1", "-map_chapters", "1", "-vf", bild,
           *kodierung, film)

    for (nummer, _), von, bis in zip(regie.kapitel, grenzen, grenzen[1:]):
        ziel = AUSGABE / f"kapitel-{nummer:02d}-{KAPITEL[nummer - 1][0]}.mp4"
        ffmpeg("-ss", f"{von:.3f}", "-t", f"{bis - von:.3f}", "-i", film, "-map", "0:v:0",
               "-map_chapters", "-1", "-map_metadata", "-1",
               "-metadata", f"title=Korrektor – Kapitel {nummer}: {KAPITEL[nummer - 1][1]}",
               *kodierung, ziel)

    # Standbilder: je Kapitel Karte, erste Ansicht und Schluss, dazu die gemerkten Stellen.
    if STANDBILDER.exists():
        shutil.rmtree(STANDBILDER)
    STANDBILDER.mkdir(parents=True)
    stellen = []
    for (nummer, _), von, bis in zip(regie.kapitel, grenzen, grenzen[1:]):
        stellen += [(f"k{nummer:02d}-0-karte", von + 1.5), (f"k{nummer:02d}-1-anfang", von + 4.6),
                    (f"k{nummer:02d}-9-ende", bis - 0.6)]
    stellen += [(name, zeit - beginn + 0.35) for name, zeit in regie.marken]
    for name, zeit in sorted(stellen, key=lambda s: s[1]):
        zeit = min(max(zeit, 0.0), dauer - 0.1)
        ffmpeg("-ss", f"{zeit:.3f}", "-i", film, "-frames:v", "1", "-q:v", "3",
               STANDBILDER / f"{int(zeit):03d}s-{name}.jpg")
    return film, grenzen


def minuten(sekunden):
    return f"{int(sekunden // 60)}:{sekunden % 60:04.1f}"


def main():
    from playwright.sync_api import sync_playwright

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg fehlt im Suchpfad.")
    AUSGABE.mkdir(parents=True, exist_ok=True)
    roh_ordner = AUSGABE / "roh"
    if roh_ordner.exists():
        shutil.rmtree(roh_ordner)
    app = app_bauen()
    server = server_starten(app)
    auffaelliges = []
    print("Aufnahme läuft …", flush=True)
    with tempfile.TemporaryDirectory(prefix="korrektor-film-") as temp, sync_playwright() as pw:
        hochladeordner = Path(temp)
        for foto, name, _ in FOTOS:
            shutil.copyfile(WURZEL / "fotos" / f"{foto}.jpg", hochladeordner / name)
        # Der volle Browser (neuer Headless-Modus) hat den PDF-Betrachter und deutsche Texte.
        start = {"channel": "chromium"} if PDF_WEG == "betrachter" else {}
        browser = pw.chromium.launch(headless=True, args=["--lang=de-DE"], **start)
        context = browser.new_context(
            viewport={"width": BREITE, "height": HOEHE}, device_scale_factor=1, locale="de-DE",
            record_video_dir=str(roh_ordner), record_video_size={"width": BREITE, "height": HOEHE},
            accept_downloads=True)
        schrift = (f"html {{ font-size: {SCHRIFT_PX}px !important; }} "
                   f".inhalt {{ max-width: {round(1180 * SCHRIFT_PX / 16)}px; }}")
        context.add_init_script(INIT_SKRIPT.replace("__SCHRIFT__", schrift))
        page = context.new_page()
        regie = Regie(page)
        page.on("pageerror", lambda fehler: auffaelliges.append(f"Skriptfehler: {fehler}"))
        page.on("console", lambda m: m.type == "error" and auffaelliges.append(f"Konsole: {m.text}"))
        page.on("response", lambda a: a.status >= 400 and auffaelliges.append(
            f"Antwort {a.status}: {a.request.method} {a.url}"))
        try:
            ende = drehen(page, regie, app, hochladeordner)
        finally:
            video = page.video
            context.close()
            browser.close()
        roh = Path(video.path())
    server.shutdown()
    app.extensions["warteschlange"].beenden()

    print("Schnitt …", flush=True)
    film, grenzen = schneiden(roh, regie, ende)
    print(f"\nFilm: {film}  ({minuten(grenzen[-1])} min)")
    for (nummer, _), von in zip(regie.kapitel, grenzen):
        print(f"  {minuten(von):>7}  Kapitel {nummer} – {KAPITEL[nummer - 1][1]}")
    print(f"Standbilder: {STANDBILDER}")
    if auffaelliges:
        print("\nAuffälliges während der Aufnahme:")
        for zeile in auffaelliges:
            print("  " + zeile)


if __name__ == "__main__":
    main()
