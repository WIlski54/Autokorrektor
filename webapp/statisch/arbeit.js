// Korrekturansicht: Rahmen der Zeichen über dem Foto, Liste daneben, Entscheiden per Maus
// und Tastatur. Jede Änderung wird sofort gespeichert; schlägt das Speichern fehl, kehrt die
// Anzeige zum vorherigen Zustand zurück.
// Die Rahmen stehen in Prozent der Bildgröße; Fenstergröße und Zoom brauchen keine Umrechnung.
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }

  function el(name, klasse, text) {
    var e = document.createElement(name);
    if (klasse) { e.className = klasse; }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }

  var daten = JSON.parse($("arbeit-daten").textContent);
  var seite = daten.seite;
  var arbeit = daten.arbeit;
  var ebene = $("rahmenebene");
  var buehne = $("buehne");
  var rollfeld = $("rollfeld");
  var liste = $("zeichenliste");
  var FARBKLASSEN = { R: "kat-R", Z: "kat-Z", Gr: "kat-Gr" };
  var FEHLER_NETZ = "Nicht gespeichert: Die App antwortet nicht. Läuft sie noch?";
  var FEHLER_ALLGEMEIN = "Nicht gespeichert: Die App hat unerwartet geantwortet.";

  var zeichen = {};        // id -> Zeichen dieser Seite, auch die verworfenen
  var rahmen = {};         // id -> Element über dem Bild
  var eintraege = {};      // id -> Listenpunkt
  var unterwegs = {};      // id -> true, solange eine Anfrage zu diesem Zeichen läuft
  var gewaehlt = null;
  var verworfeneZeigen = false;
  var zoom = 100;
  var folge = 0;           // laufende Nummer der Anfragen
  var angewandt = 0;       // Nummer der Anfrage, deren Stand der Arbeit zuletzt gezeigt wurde
  var seitenstatus = "fertig";

  daten.zeichen.concat(daten.verworfen).forEach(function (z) { zeichen[z.id] = z; });
  daten.seiten.forEach(function (s) {
    if (s.id === seite.id) { seitenstatus = s.status; }
  });
  // Solange die Analyse der Seite läuft, bleibt die Ansicht lesend: Die Analyse ersetzt
  // die offenen Vorschläge.
  var gesperrt = seitenstatus === "wartet" || seitenstatus === "laeuft";

  // --- Meldung ------------------------------------------------------------------------------

  var meldung = $("meldung");
  var meldungUhr = null;

  function melden(text, art) {
    $("meldung-text").textContent = text;
    meldung.className = "meldung schwebend " + (art || "fehler");
    meldung.hidden = false;
    if (meldungUhr !== null) { window.clearTimeout(meldungUhr); }
    meldungUhr = window.setTimeout(meldungSchliessen, art === "hinweis" ? 5000 : 15000);
  }

  function meldungSchliessen() {
    if (meldungUhr !== null) { window.clearTimeout(meldungUhr); }
    meldungUhr = null;
    meldung.hidden = true;
  }

  $("meldung-zu").addEventListener("click", meldungSchliessen);

  // --- Anfragen -----------------------------------------------------------------------------

  // Löst mit dem JSON-Inhalt ein; scheitert mit {meldung}, wenn das Netz, der Status oder
  // die Form der Antwort nicht stimmt.
  function senden(methode, url, koerper) {
    var auftrag = { method: methode, headers: { "Accept": "application/json" } };
    if (koerper !== undefined) {
      auftrag.headers["Content-Type"] = "application/json";
      auftrag.body = JSON.stringify(koerper);
    }
    return fetch(url, auftrag).then(function (antwort) {
      return antwort.json().catch(function () { return null; }).then(function (inhalt) {
        var brauchbar = inhalt !== null && typeof inhalt === "object";
        if (!antwort.ok || !brauchbar) {
          var text = brauchbar && typeof inhalt.fehler === "string" && inhalt.fehler;
          throw { meldung: text || FEHLER_ALLGEMEIN + " (Status " + antwort.status + ")" };
        }
        return inhalt;
      });
    }, function () {
      throw { meldung: FEHLER_NETZ };
    });
  }

  function fehlertext(fehler) {
    return (fehler && typeof fehler.meldung === "string" && fehler.meldung) || FEHLER_ALLGEMEIN;
  }

  // --- Texte und Klassen je Zeichen ---------------------------------------------------------

  function prozent(wert, gesamt) {
    return (100 * wert / gesamt) + "%";
  }

  function farbklasse(z) {
    if (z.herkunft === "hand") { return "kat-hand"; }
    return FARBKLASSEN[z.kategorie] || "kat-sonst";
  }

  function zustandsklasse(z) {
    if (z.status === "offen") { return "offen"; }
    return z.status === "verworfen" ? "verworfen" : "fest";
  }

  function zustandstext(z) {
    if (z.herkunft === "hand") { return "selbst gesetzt"; }
    if (z.status === "offen") { return "KI-Vorschlag, offen"; }
    if (z.status === "verworfen") { return "KI-Vorschlag, verworfen"; }
    if (z.bestaetigt_wie === "gesammelt") { return "KI-Vorschlag, gesammelt bestätigt"; }
    if (z.bestaetigt_wie === "geaendert") { return "KI-Vorschlag, geändert und bestätigt"; }
    return "KI-Vorschlag, bestätigt";
  }

  function bezeichnung(kuerzel) {
    var name = kuerzel;
    daten.kuerzel.forEach(function (k) {
      if (k.kuerzel === kuerzel) { name = k.bezeichnung; }
    });
    return name;
  }

  function beschreibung(z) {
    var text = z.kategorie + " (" + bezeichnung(z.kategorie) + ")";
    if (z.gelesen) { text += ": " + z.gelesen; }
    if (z.vorschlag) { text += (z.gelesen ? ", Vorschlag: " : ": ") + z.vorschlag; }
    return text + ", " + zustandstext(z);
  }

  function sichtbar(z) {
    return z.status !== "verworfen" || verworfeneZeigen;
  }

  // Lesereihenfolge wie auf dem Server: von oben nach unten, dann von links nach rechts.
  function geordnet() {
    return Object.keys(zeichen).map(function (id) { return zeichen[id]; })
      .filter(sichtbar)
      .sort(function (a, b) { return a.y - b.y || a.x - b.x || a.id - b.id; });
  }

  function offeneDerSeite() {
    return geordnet().filter(function (z) { return z.status === "offen"; });
  }

  // --- Rahmen über dem Bild -----------------------------------------------------------------

  function rahmenBauen(z) {
    var e = el("div", "rahmen");
    e.setAttribute("role", "button");
    e.tabIndex = -1;  // per Klick fokussierbar; der Weg mit der Tastatur führt über die Liste
    e.appendChild(el("span", "etikett"));
    rahmenAnschliessen(e, z.id);
    return e;
  }

  function rahmenAnschliessen(e, id) {
    e.addEventListener("click", function (ereignis) {
      ereignis.stopPropagation();
      waehlen(id, "bild");
    });
    e.addEventListener("mouseenter", function () { nah(id, true); });
    e.addEventListener("mouseleave", function () { nah(id, false); });
  }

  function rahmenLegen(e, lage) {
    e.style.left = prozent(lage.x, seite.breite);
    e.style.top = prozent(lage.y, seite.hoehe);
    e.style.width = prozent(lage.breite, seite.breite);
    e.style.height = prozent(lage.hoehe, seite.hoehe);
    e.firstChild.classList.toggle("unten", lage.y / seite.hoehe < 0.04);
  }

  function rahmenStellen(e, z) {
    e.className = "rahmen " + farbklasse(z) + " " + zustandsklasse(z) +
      (z.typ === "luecke" ? " luecke" : "") +
      (z.id === gewaehlt ? " gewaehlt" : "") +
      (unterwegs[z.id] ? " unterwegs" : "");
    e.hidden = !sichtbar(z);
    e.setAttribute("aria-label", beschreibung(z));
    e.firstChild.textContent = z.kategorie;
    if (!wirdGezogen(z.id)) { rahmenLegen(e, z); }
  }

  // Ob der Rahmen gerade mit dem Zeiger bewegt wird (dann bleibt seine Lage unberührt).
  function wirdGezogen() {
    return false;
  }

  function nah(id, an) {
    if (rahmen[id]) { rahmen[id].classList.toggle("nah", an); }
    if (eintraege[id]) { eintraege[id].classList.toggle("nah", an); }
  }

  // --- Liste --------------------------------------------------------------------------------

  // Die Knöpfe eines Listenpunkts als [Aktion, Beschriftung, Klasse].
  function aktionenFuer(z) {
    if (gesperrt) { return []; }
    if (z.herkunft === "hand") { return []; }
    if (z.status === "offen") {
      return [["bestaetigen", "Bestätigen"], ["verwerfen", "Verwerfen"]];
    }
    if (z.status === "verworfen") { return [["zurueckholen", "Zurückholen"]]; }
    return [["zurueckholen", "Zurückholen"], ["verwerfen", "Verwerfen"]];
  }

  function eintragBauen(z) {
    var punkt = el("li", "eintrag " + farbklasse(z) + " " + zustandsklasse(z) +
      (z.id === gewaehlt ? " gewaehlt" : "") + (unterwegs[z.id] ? " unterwegs" : ""));
    punkt.setAttribute("data-zeichen", z.id);

    var wahl = el("button", "eintrag-wahl");
    wahl.type = "button";
    wahl.setAttribute("data-akt", "waehlen");
    if (z.id === gewaehlt) { wahl.setAttribute("aria-current", "true"); }
    var kuerzel = el("span", "kuerzel", z.kategorie);
    kuerzel.title = bezeichnung(z.kategorie);
    wahl.appendChild(kuerzel);
    var wortlaut = el("span", "wortlaut");
    if (z.gelesen) { wortlaut.appendChild(el("span", "gelesen", z.gelesen)); }
    if (z.vorschlag) {
      if (z.gelesen) {
        var pfeil = el("span", "pfeil", "→");
        pfeil.setAttribute("aria-hidden", "true");
        wortlaut.appendChild(pfeil);
        wortlaut.appendChild(el("span", "nur-vorlesen", "Vorschlag: "));
      }
      wortlaut.appendChild(el("span", "vorschlag", z.vorschlag));
    }
    if (!z.gelesen && !z.vorschlag) {
      wortlaut.appendChild(el("span", "leise",
        z.herkunft === "hand" ? "(ohne Vorschlag)" : "(ohne Angabe)"));
    }
    wahl.appendChild(wortlaut);
    wahl.appendChild(el("span", "leise art",
      zustandstext(z) + (z.typ === "luecke" ? " · fehlendes Zeichen" : "")));
    punkt.appendChild(wahl);

    var aktionen = aktionenFuer(z);
    if (aktionen.length) {
      var reihe = el("div", "eintrag-knoepfe");
      aktionen.forEach(function (a) {
        var knopf = el("button", "knopf klein" + (a[2] ? " " + a[2] : ""), a[1]);
        knopf.type = "button";
        knopf.setAttribute("data-akt", a[0]);
        knopf.disabled = Boolean(unterwegs[z.id]);
        reihe.appendChild(knopf);
      });
      punkt.appendChild(reihe);
    }
    eintragErgaenzen(punkt, z);
    return punkt;
  }

  // Platz für das Formular „Ändern“ (siehe unten).
  function eintragErgaenzen() {}

  // Zeichnet Rahmen und Listenpunkt eines Zeichens neu; der Fokus bleibt, wo er war.
  function zeichnen(id) {
    var z = zeichen[id];
    if (!z) {
      if (rahmen[id]) { rahmen[id].remove(); delete rahmen[id]; }
      if (eintraege[id]) { eintraege[id].remove(); delete eintraege[id]; }
      return;
    }
    if (!rahmen[id]) {
      rahmen[id] = rahmenBauen(z);
      ebene.appendChild(rahmen[id]);
    }
    rahmenStellen(rahmen[id], z);

    var alt = eintraege[id];
    if (!sichtbar(z)) {
      if (alt) { alt.remove(); delete eintraege[id]; }
      return;
    }
    var neu = eintragBauen(z);
    var fokus = alt && alt.contains(document.activeElement)
      ? document.activeElement.getAttribute("data-akt") : null;
    if (alt) { liste.replaceChild(neu, alt); } else { liste.appendChild(neu); }
    eintraege[id] = neu;
    if (fokus) {
      (neu.querySelector('[data-akt="' + fokus + '"]:not(:disabled)') ||
        neu.querySelector(".eintrag-wahl")).focus({ preventScroll: true });
    }
  }

  // Bringt die Listenpunkte in Lesereihenfolge; rührt nichts an, was schon richtig steht.
  function listeOrdnen() {
    var soll = geordnet().map(function (z) { return eintraege[z.id]; }).filter(Boolean);
    soll.forEach(function (punkt, platz) {
      if (liste.children[platz] !== punkt) { liste.insertBefore(punkt, liste.children[platz] || null); }
    });
  }

  function allesZeichnen() {
    Object.keys(zeichen).forEach(function (id) { zeichnen(Number(id)); });
    listeOrdnen();
    zahlenZeigen();
  }

  // --- Zähler und Zustand der Arbeit --------------------------------------------------------

  function vorschlaege(zahl) {
    if (zahl === 0) { return "kein Vorschlag offen"; }
    return zahl === 1 ? "1 Vorschlag offen" : zahl + " Vorschläge offen";
  }

  function zeitpunkt(iso) {
    var teile = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)/.exec(iso || "");
    if (!teile) { return iso || ""; }
    return teile[3] + "." + teile[2] + "." + teile[1] + ", " + teile[4] + ":" + teile[5] + " Uhr";
  }

  function zahlenZeigen() {
    var alle = Object.keys(zeichen).map(function (id) { return zeichen[id]; });
    var verworfen = alle.filter(function (z) { return z.status === "verworfen"; }).length;
    var offen = alle.filter(function (z) { return z.status === "offen"; }).length;
    var gezeigt = alle.length - verworfen;
    $("seite-zahlen").textContent = (gezeigt === 1 ? "1 Zeichen" : gezeigt + " Zeichen") +
      " auf dieser Seite, " + (offen ? offen + " offen" : "keines offen");
    $("verworfen-zahl").textContent = "(" + verworfen + ")";
    $("liste-leer").hidden = liste.children.length > 0;
    daten.seiten.forEach(function (s) {
      if (s.id === seite.id) { s.offen = offen; }
    });
  }

  function arbeitZeigen() {
    $("arbeit-offen").textContent = "in der Arbeit: " + vorschlaege(arbeit.offen);
    var anzeige = $("bestaetigt-anzeige");
    anzeige.hidden = !arbeit.bestaetigt_am;
    $("bestaetigt-wann").textContent = arbeit.bestaetigt_am ? zeitpunkt(arbeit.bestaetigt_am) : "";
    fussleisteZeigen();
  }

  // Platz für die Knöpfe der Fußleiste (siehe unten).
  function fussleisteZeigen() {}

  // Übernimmt den Stand der Arbeit aus einer Antwort; ältere Antworten überholen neuere nicht.
  function arbeitStellen(stand, nummer) {
    if (!stand || nummer < angewandt) { return; }
    angewandt = nummer;
    arbeit.offen = stand.offen;
    arbeit.bestaetigt_am = stand.bestaetigt_am;
    arbeit.bestaetigbar = stand.bestaetigbar;
    arbeit.grund = stand.grund;
    arbeitZeigen();
  }

  // --- Auswahl ------------------------------------------------------------------------------

  // Rollt das Feld so, dass das Element darin zu sehen ist; die Seite selbst bleibt stehen.
  function inSicht(feld, element, mittig) {
    var f = feld.getBoundingClientRect();
    var e = element.getBoundingClientRect();
    var rand = 24;
    if (e.top < f.top + rand || e.bottom > f.bottom - rand) {
      feld.scrollTop += mittig ? (e.top + e.bottom) / 2 - (f.top + f.bottom) / 2
        : (e.top < f.top + rand ? e.top - f.top - rand : e.bottom - f.bottom + rand);
    }
    if (e.left < f.left + rand || e.right > f.right - rand) {
      feld.scrollLeft += (e.left + e.right) / 2 - (f.left + f.right) / 2;
    }
  }

  // Hebt dasselbe Zeichen im Bild und in der Liste hervor. `quelle` sagt, woher die Auswahl
  // kommt: "bild", "liste" oder "taste" (dann wandert auch der Fokus mit).
  function waehlen(id, quelle) {
    if (id !== null && (!zeichen[id] || !sichtbar(zeichen[id]))) { id = null; }
    var vorher = gewaehlt;
    gewaehlt = id;
    [vorher, id].forEach(function (nr) {
      if (nr === null) { return; }
      var an = nr === id;
      if (rahmen[nr]) { rahmen[nr].classList.toggle("gewaehlt", an); }
      if (eintraege[nr]) {
        eintraege[nr].classList.toggle("gewaehlt", an);
        var wahl = eintraege[nr].querySelector(".eintrag-wahl");
        if (an) { wahl.setAttribute("aria-current", "true"); } else { wahl.removeAttribute("aria-current"); }
      }
    });
    if (vorher !== id) { auswahlGewechselt(vorher); }
    if (id === null) { return; }
    if (rahmen[id] && quelle !== "bild") { inSicht(rollfeld, rahmen[id], true); }
    if (eintraege[id]) {
      if (quelle !== "liste") { inSicht($("listenspalte"), eintraege[id], false); }
      if (quelle === "taste") {
        eintraege[id].querySelector(".eintrag-wahl").focus({ preventScroll: true });
      }
    }
  }

  // Platz für das Schließen eines offenen Formulars beim Wechsel der Auswahl.
  function auswahlGewechselt() {}

  // Der nächste offene Vorschlag der Seite nach dem genannten Zeichen (rundum); sonst null.
  function naechsterOffener(nach) {
    var reihe = geordnet();
    var platz = -1;
    reihe.forEach(function (z, i) { if (z.id === nach) { platz = i; } });
    for (var i = 1; i <= reihe.length; i++) {
      var z = reihe[(platz + i + reihe.length) % reihe.length];
      if (z.status === "offen" && z.id !== nach) { return z.id; }
    }
    return null;
  }

  function seitenUrl(nummer) {
    return window.location.pathname + "?seite=" + nummer;
  }

  // Die nächste andere Seite mit offenen Vorschlägen (rundum); sonst null.
  function naechsteSeiteMitOffenen() {
    var zahl = daten.seiten.length;
    for (var i = 1; i < zahl; i++) {
      var s = daten.seiten[(seite.nummer - 1 + i) % zahl];
      if (s.offen > 0) { return s.nummer; }
    }
    return null;
  }

  function zumNaechstenOffenen() {
    var ziel = naechsterOffener(gewaehlt);
    if (ziel !== null) {
      waehlen(ziel, "taste");
      return;
    }
    if (gewaehlt !== null && zeichen[gewaehlt] && zeichen[gewaehlt].status === "offen") {
      waehlen(gewaehlt, "taste");  // der einzige offene ist schon gewählt
      return;
    }
    var nummer = naechsteSeiteMitOffenen();
    if (nummer !== null) {
      window.location.href = seitenUrl(nummer);
    } else {
      melden("In dieser Arbeit ist kein Vorschlag mehr offen.", "hinweis");
    }
  }

  // Nach einer gespeicherten Entscheidung: Ist auf der Seite nichts mehr offen, geht es zur
  // nächsten Seite mit offenen Vorschlägen; ist die ganze Arbeit durch, zur Gesamtbestätigung.
  function weiterNachEntscheidung() {
    if (Object.keys(unterwegs).length || offeneDerSeite().length) { return; }
    var nummer = naechsteSeiteMitOffenen();
    if (nummer !== null) {
      window.location.href = seitenUrl(nummer);
    } else if (arbeit.offen === 0) {
      arbeitDurch();
    }
  }

  // Platz für den Sprung zur Gesamtbestätigung (siehe unten).
  function arbeitDurch() {}

  // --- Entscheiden: bestätigen, verwerfen, zurückholen --------------------------------------

  function kopie(z) {
    var neu = {};
    Object.keys(z).forEach(function (feld) { neu[feld] = z[feld]; });
    return neu;
  }

  // Zeigt die Änderung sofort, speichert sie und nimmt sie zurück, wenn das Speichern scheitert.
  // `vorlaeufig` sind die Felder, die sich voraussichtlich ändern; es gilt, was die Route meldet.
  function speichern(id, pfad, vorlaeufig, koerper, entscheidung) {
    var z = zeichen[id];
    if (!z || unterwegs[id] || gesperrt) { return false; }
    var vorher = kopie(z);
    var nummer = ++folge;
    var ziel = naechsterOffener(id);  // vor der Änderung: danach fehlt ein Verworfenes in der Reihe
    Object.keys(vorlaeufig).forEach(function (feld) { z[feld] = vorlaeufig[feld]; });
    unterwegs[id] = true;
    zeichnen(id);
    zahlenZeigen();
    if (entscheidung || !sichtbar(z)) {
      if (ziel !== null) { waehlen(ziel, "taste"); } else if (!sichtbar(z)) { waehlen(null); }
    }
    senden("POST", "/zeichen/" + id + "/" + pfad, koerper).then(function (antwort) {
      delete unterwegs[id];
      if (antwort.zeichen) { zeichen[id] = antwort.zeichen; }
      arbeitStellen(antwort.arbeit, nummer);
      zeichnen(id);
      listeOrdnen();
      zahlenZeigen();
      if (entscheidung) { weiterNachEntscheidung(); }
    }, function (fehler) {
      delete unterwegs[id];
      zeichen[id] = vorher;
      zeichnen(id);
      listeOrdnen();
      zahlenZeigen();
      melden(fehlertext(fehler));
      waehlen(id, "taste");
    });
    return true;
  }

  function bestaetigen(id) {
    var z = zeichen[id];
    if (!z || z.herkunft !== "ki" || z.status !== "offen") { return; }
    speichern(id, "bestaetigen", { status: "bestaetigt", bestaetigt_wie: "einzeln" }, undefined, true);
  }

  function verwerfen(id) {
    var z = zeichen[id];
    if (!z || z.status === "verworfen") { return; }
    if (z.herkunft !== "ki") {
      melden("Eigene Zeichen werden gelöscht, nicht verworfen (Taste Entf).", "hinweis");
      return;
    }
    speichern(id, "verwerfen", { status: "verworfen", bestaetigt_wie: null }, undefined,
      z.status === "offen");
  }

  function zurueckholen(id) {
    var z = zeichen[id];
    if (!z || z.herkunft !== "ki" || z.status === "offen") { return; }
    speichern(id, "zurueckholen", { status: "offen", bestaetigt_wie: null });
  }

  // Die Taste Entf: verwirft einen Vorschlag der KI (eigene Zeichen siehe unten).
  function entfernen(id) {
    verwerfen(id);
  }

  var AKTIONEN = { bestaetigen: bestaetigen, verwerfen: verwerfen, zurueckholen: zurueckholen };

  liste.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-akt]");
    var punkt = ereignis.target.closest("li[data-zeichen]");
    if (!knopf || !punkt) { return; }
    var id = Number(punkt.getAttribute("data-zeichen"));
    var akt = knopf.getAttribute("data-akt");
    if (akt === "waehlen") {
      waehlen(id, "liste");
    } else if (AKTIONEN[akt]) {
      if (gewaehlt !== id) { waehlen(id, "liste"); }
      AKTIONEN[akt](id);
    }
  });

  liste.addEventListener("mouseover", function (ereignis) {
    var punkt = ereignis.target.closest("li[data-zeichen]");
    if (punkt) { nah(Number(punkt.getAttribute("data-zeichen")), true); }
  });
  liste.addEventListener("mouseout", function (ereignis) {
    var punkt = ereignis.target.closest("li[data-zeichen]");
    if (punkt && !punkt.contains(ereignis.relatedTarget)) {
      nah(Number(punkt.getAttribute("data-zeichen")), false);
    }
  });

  ebene.addEventListener("click", function (ereignis) {
    if (ereignis.target === ebene) { waehlen(null); }
  });

  $("verworfene-zeigen").addEventListener("change", function () {
    verworfeneZeigen = this.checked;
    if (gewaehlt !== null && !sichtbar(zeichen[gewaehlt])) { waehlen(null); }
    allesZeichnen();
  });

  // --- Zoom: die Bühne wird breiter als das Rollfeld, die Prozentwerte wachsen mit ----------

  function zoomStellen(wert) {
    zoom = Math.max(100, Math.min(400, Math.round(wert)));
    buehne.style.width = zoom + "%";
    $("zoom-anzeige").textContent = zoom + " %";
  }

  $("zoom-groesser").addEventListener("click", function () { zoomStellen(zoom * 1.25); });
  $("zoom-kleiner").addEventListener("click", function () { zoomStellen(zoom / 1.25); });
  $("zoom-einpassen").addEventListener("click", function () {
    zoomStellen(100);
    rollfeld.scrollTo(0, 0);
  });

  // --- Tastatur -----------------------------------------------------------------------------

  function gehen(kennung) {
    var ziel = $(kennung);
    if (ziel && ziel.href) { window.location.href = ziel.href; }
    return Boolean(ziel && ziel.href);
  }

  // Esc räumt von innen nach außen auf: erst die Meldung, dann die Auswahl.
  function abbrechen() {
    if (!meldung.hidden) { meldungSchliessen(); return; }
    waehlen(null);
  }

  // Weitere Tasten (siehe unten); gibt true zurück, wenn die Taste verbraucht ist.
  function weitereTaste() {
    return false;
  }

  document.addEventListener("keydown", function (ereignis) {
    if (ereignis.altKey || ereignis.ctrlKey || ereignis.metaKey || ereignis.shiftKey) { return; }
    if (document.querySelector("dialog[open]")) { return; }
    var ziel = ereignis.target;
    var name = ziel.tagName;
    if (name === "INPUT" || name === "SELECT" || name === "TEXTAREA" || ziel.isContentEditable) {
      return;
    }
    // Auf Knöpfen und Verweisen behalten Enter und Tab ihre gewohnte Wirkung; nur auf den
    // Zeichen selbst (Rahmen, Listenpunkt) und außerhalb davon gilt die Belegung der Ansicht.
    var aufZeichen = ziel === document.body || ziel.classList.contains("rahmen") ||
      ziel.classList.contains("eintrag-wahl");
    var taste = ereignis.key.length === 1 ? ereignis.key.toLowerCase() : ereignis.key;
    var verbraucht = true;

    if (taste === "n") {
      zumNaechstenOffenen();
    } else if (taste === "Tab") {
      var ziel_id = aufZeichen ? naechsterOffener(gewaehlt) : null;
      if (ziel_id === null) { return; }  // sonst wandert der Fokus wie gewohnt
      waehlen(ziel_id, "taste");
    } else if (taste === "b" || (taste === "Enter" && aufZeichen)) {
      bestaetigen(gewaehlt);
    } else if (taste === "v") {
      verwerfen(gewaehlt);
    } else if (taste === "Delete") {
      entfernen(gewaehlt);
    } else if (taste === "z") {
      zurueckholen(gewaehlt);
    } else if (taste === "ArrowLeft") {
      verbraucht = gehen("seite-zurueck");
    } else if (taste === "ArrowRight") {
      verbraucht = gehen("seite-weiter");
    } else if (taste === "PageUp") {
      verbraucht = gehen("arbeit-zurueck");
    } else if (taste === "PageDown") {
      verbraucht = gehen("arbeit-weiter");
    } else if (taste === "Escape") {
      abbrechen();
    } else {
      verbraucht = weitereTaste(taste);
    }
    if (verbraucht) { ereignis.preventDefault(); }
  });

  // --- Start --------------------------------------------------------------------------------

  allesZeichnen();
  arbeitZeigen();
  if (!gesperrt) {
    var erster = naechsterOffener(null);
    if (erster !== null) { waehlen(erster, "taste"); }
  }
})();
