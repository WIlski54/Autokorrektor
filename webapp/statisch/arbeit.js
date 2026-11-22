// Korrekturansicht: Rahmen der Zeichen über dem Foto, Liste daneben. Entscheiden, Ändern,
// Verschieben und eigene Zeichen per Maus, Stift, Finger und Tastatur; dazu „Rest bestätigen“,
// die Gesamtbestätigung der Arbeit, die Neuanalyse der Seite und das Kürzel der Arbeit.
// Jede Änderung wird sofort gespeichert; schlägt das Speichern fehl, kehrt die
// Anzeige zum vorherigen Zustand zurück.
// Der Stand der Arbeit (offene Vorschläge, Bestätigung, Zustand aller Seiten) kommt immer vom
// Server und trägt dessen Änderungszähler `stand`; ein älterer Stand überholt nie einen neueren.
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
  var foto = $("foto");
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
  var zug = null;          // laufendes Verschieben oder Größe-Ändern eines Rahmens
  var formularFuer = null; // id des Zeichens, dessen Formular „Ändern“ offen ist
  var setzen = false;      // Modus „Zeichen setzen“
  var aufzug = null;       // laufendes Aufziehen eines neuen Rahmens
  var entwurf = null;      // {lage, element} des aufgezogenen, noch nicht gespeicherten Rahmens
  var letztesKuerzel = null;
  var MINDESTKANTE = 4;    // Pixel des Bildes, wie in den Regeln
  var KLEINSTER_ENTWURF = 6;
  var SCHWELLE = 3;        // Bildschirmpixel; darunter gilt ein Zeigerdruck als Klick
  var laufend = 0;         // schreibende Anfragen, die noch unterwegs sind
  var laedtNach = false;   // der Stand der Arbeit wird gerade nachgeladen
  var nochmalLaden = false;
  var abfrageUhr = null;   // Wecker der nächsten Abfrage, solange eine Seite analysiert wird
  var sprungFaellig = false;  // nach einer Entscheidung steht der Sprung zum Nächsten noch aus
  var fragt = false;       // ein Dialog holt gerade den frischen Stand
  var ABSTAND_MS = 2000;
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
    // Ein Hinweis bleibt je nach Länge stehen, eine Fehlermeldung länger.
    meldungUhr = window.setTimeout(meldungSchliessen,
      art === "hinweis" ? Math.max(5000, 70 * text.length) : 15000);
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

  // Eine schreibende Anfrage. Ist danach keine mehr unterwegs, wird der Stand der Arbeit
  // einmal nachgeladen: Erst dann stimmen Kopfzeile, Fußleiste und der Sprung des Fokus sicher.
  function schreiben(url, koerper) {
    laufend++;
    function fertig() {
      laufend--;
      window.setTimeout(function () {  // erst nach den Schritten, die die Antwort auswerten
        if (laufend === 0) { nachladen(); }
      }, 0);
    }
    return senden("POST", url, koerper).then(function (antwort) {
      fertig();
      return antwort;
    }, function (fehler) {
      fertig();
      throw fehler;
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
    e.setAttribute("data-zeichen", z.id);
    e.appendChild(el("span", "etikett"));
    ["nw", "ne", "sw", "se"].forEach(function (ecke) {
      e.appendChild(el("span", "griffpunkt " + ecke)).setAttribute("data-ecke", ecke);
    });
    rahmenAnschliessen(e, z.id);
    return e;
  }

  function rahmenAnschliessen(e, id) {
    e.addEventListener("pointerdown", function (ereignis) { zugBeginnen(ereignis, id); });
    e.addEventListener("pointermove", zugBewegen);
    e.addEventListener("pointerup", function (ereignis) { zugBeenden(ereignis, true); });
    e.addEventListener("pointercancel", function (ereignis) { zugBeenden(ereignis, false); });
    e.addEventListener("lostpointercapture", function (ereignis) { zugBeenden(ereignis, false); });
    e.addEventListener("mouseenter", function () { nah(id, true); });
    e.addEventListener("mouseleave", function () { nah(id, false); });
  }

  // Die Stelle des Zeigers in Pixeln des Bildes; stimmt bei jedem Zoom und nach dem Rollen,
  // weil sie aus der Lage des Bildes im Fenster gerechnet wird.
  function bildpunkt(ereignis) {
    var r = foto.getBoundingClientRect();
    return { x: (ereignis.clientX - r.left) * seite.breite / r.width,
             y: (ereignis.clientY - r.top) * seite.hoehe / r.height };
  }

  function klemmen(wert, von, bis) {
    return Math.max(von, Math.min(bis, wert));
  }

  function zugBeginnen(ereignis, id) {
    var z = zeichen[id];
    if (!z || zug !== null || setzen) { return; }
    if (ereignis.pointerType === "mouse" && ereignis.button !== 0) { return; }
    // Mit dem Finger lässt sich nur der gewählte Rahmen bewegen; sonst rollt der Finger das Bild.
    var beweglich = !gesperrt && !unterwegs[id] && z.status !== "verworfen" &&
      (ereignis.pointerType !== "touch" || gewaehlt === id);
    zug = { id: id, zeiger: ereignis.pointerId, element: rahmen[id],
            art: ereignis.target.getAttribute("data-ecke") || "mitte",
            start: bildpunkt(ereignis), ort: { x: ereignis.clientX, y: ereignis.clientY },
            lage: { x: z.x, y: z.y, breite: z.breite, hoehe: z.hoehe },
            neu: null, bewegt: false, beweglich: beweglich };
    try { zug.element.setPointerCapture(ereignis.pointerId); } catch (fehler) { /* Zeiger schon weg */ }
  }

  function zugBewegen(ereignis) {
    if (zug === null || ereignis.pointerId !== zug.zeiger) { return; }
    if (!zug.bewegt) {
      var weg = Math.hypot(ereignis.clientX - zug.ort.x, ereignis.clientY - zug.ort.y);
      if (weg < SCHWELLE || !zug.beweglich) { return; }
      zug.bewegt = true;
      zug.element.classList.add("gezogen");
    }
    var p = bildpunkt(ereignis);
    var dx = p.x - zug.start.x;
    var dy = p.y - zug.start.y;
    var links = zug.lage.x, oben = zug.lage.y;
    var rechts = links + zug.lage.breite, unten = oben + zug.lage.hoehe;
    if (zug.art === "mitte") {
      links = klemmen(links + dx, 0, seite.breite - zug.lage.breite);
      oben = klemmen(oben + dy, 0, seite.hoehe - zug.lage.hoehe);
      rechts = links + zug.lage.breite;
      unten = oben + zug.lage.hoehe;
    } else {
      if (zug.art.charAt(1) === "w") {
        links = klemmen(links + dx, 0, rechts - MINDESTKANTE);
      } else {
        rechts = klemmen(rechts + dx, links + MINDESTKANTE, seite.breite);
      }
      if (zug.art.charAt(0) === "n") {
        oben = klemmen(oben + dy, 0, unten - MINDESTKANTE);
      } else {
        unten = klemmen(unten + dy, oben + MINDESTKANTE, seite.hoehe);
      }
    }
    var x = Math.round(links), y = Math.round(oben);
    zug.neu = { x: x, y: y, breite: Math.max(MINDESTKANTE, Math.round(rechts) - x),
                hoehe: Math.max(MINDESTKANTE, Math.round(unten) - y) };
    rahmenLegen(zug.element, zug.neu);
  }

  // Bricht das Ziehen ab: Der Rahmen liegt wieder, wo er war, und ein neuer Zug kann beginnen.
  // Nötig auch, wenn der Rahmen mitten im Zug verschwindet; sonst käme das Loslassen nie an.
  function zugAbbrechen() {
    if (zug === null) { return; }
    var ende = zug;
    zug = null;
    ende.element.classList.remove("gezogen");
    try { ende.element.releasePointerCapture(ende.zeiger); } catch (fehler) { /* schon frei */ }
    if (zeichen[ende.id]) { rahmenLegen(ende.element, zeichen[ende.id]); }
  }

  // Loslassen: ohne Bewegung nur auswählen, sonst den neuen Rahmen speichern.
  function zugBeenden(ereignis, gueltig) {
    if (zug === null || ereignis.pointerId !== zug.zeiger) { return; }
    if (!gueltig || !zeichen[zug.id] || !sichtbar(zeichen[zug.id])) {
      zugAbbrechen();
      return;
    }
    var ende = zug;
    zug = null;
    ende.element.classList.remove("gezogen");
    try { ende.element.releasePointerCapture(ereignis.pointerId); } catch (fehler) { /* schon frei */ }
    var z = zeichen[ende.id];
    if (gewaehlt !== ende.id) { waehlen(ende.id, "bild"); }
    ende.element.focus({ preventScroll: true });
    if (!ende.bewegt || ende.neu === null) { return; }
    var n = ende.neu;
    if (n.x === z.x && n.y === z.y && n.breite === z.breite && n.hoehe === z.hoehe) {
      rahmenLegen(ende.element, z);
      return;
    }
    if (!speichern(ende.id, "rahmen", n, n, false)) { rahmenLegen(ende.element, z); }
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
    if (e.hidden && zug !== null && zug.id === z.id) { zugAbbrechen(); }
    e.setAttribute("aria-label", beschreibung(z));
    e.firstChild.textContent = z.kategorie;
    if (!wirdGezogen(z.id)) { rahmenLegen(e, z); }
  }

  // Ob der Rahmen gerade mit dem Zeiger bewegt wird (dann bleibt seine Lage unberührt).
  function wirdGezogen(id) {
    return zug !== null && zug.id === id && zug.bewegt;
  }

  function nah(id, an) {
    if (rahmen[id]) { rahmen[id].classList.toggle("nah", an); }
    if (eintraege[id]) { eintraege[id].classList.toggle("nah", an); }
  }

  // --- Liste --------------------------------------------------------------------------------

  // Die Knöpfe eines Listenpunkts als [Aktion, Beschriftung, Klasse].
  function aktionenFuer(z) {
    if (gesperrt || formularFuer === z.id) { return []; }
    if (z.herkunft === "hand") {
      return [["aendern", "Ändern"], ["loeschen", "Löschen", "gefahr"]];
    }
    if (z.status === "offen") {
      return [["bestaetigen", "Bestätigen"], ["verwerfen", "Verwerfen"], ["aendern", "Ändern"]];
    }
    if (z.status === "verworfen") { return [["zurueckholen", "Zurückholen"]]; }
    return [["zurueckholen", "Zurückholen"], ["verwerfen", "Verwerfen"], ["aendern", "Ändern"]];
  }

  // `ohneFormular`: Das offene Formular „Ändern“ hängt der Aufrufer selbst um.
  function eintragBauen(z, ohneFormular) {
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
    if (!ohneFormular) { eintragErgaenzen(punkt, z); }
    return punkt;
  }

  // Hängt das Formular „Ändern“ an, wenn es für dieses Zeichen offen ist.
  function eintragErgaenzen(punkt, z) {
    if (formularFuer === z.id) { punkt.appendChild(aendernFormular(z)); }
  }

  // Auswahlfeld mit R, Z, Gr und den eigenen Kürzeln; ein Kürzel, das nicht mehr in der
  // Liste steht, bleibt als bisheriger Wert wählbar.
  function kuerzelFuellen(feld, aktuell) {
    feld.textContent = "";
    var bekannt = false;
    daten.kuerzel.forEach(function (k) {
      var wahl = el("option", null, k.kuerzel + " – " + k.bezeichnung);
      wahl.value = k.kuerzel;
      feld.appendChild(wahl);
      bekannt = bekannt || k.kuerzel === aktuell;
    });
    if (aktuell !== null && !bekannt) {
      var alt = el("option", null, aktuell + " (nicht mehr in der Liste)");
      alt.value = aktuell;
      feld.appendChild(alt);
    }
    if (aktuell !== null) { feld.value = aktuell; }
  }

  function beschriftet(text, feld) {
    var rahmung = el("label", "formfeld");
    rahmung.appendChild(el("span", null, text));
    rahmung.appendChild(feld);
    return rahmung;
  }

  // Im Formular bricht Esc ab; Enter schickt es auch aus einem Auswahlfeld ab.
  function formularTasten(formular, abbruch) {
    formular.addEventListener("keydown", function (ereignis) {
      if (ereignis.key === "Escape") {
        ereignis.preventDefault();
        ereignis.stopPropagation();
        abbruch();
      } else if (ereignis.key === "Enter" && ereignis.target.tagName === "SELECT") {
        ereignis.preventDefault();
        formular.requestSubmit();
      }
    });
  }

  function aendernFormular(z) {
    var formular = el("form", "zeichenformular");
    formular.noValidate = true;
    var kuerzel = el("select");
    kuerzelFuellen(kuerzel, z.kategorie);
    var vorschlag = el("input");
    vorschlag.type = "text";
    vorschlag.maxLength = 200;
    vorschlag.autocomplete = "off";
    vorschlag.value = z.vorschlag || "";
    formular.appendChild(beschriftet("Kürzel", kuerzel));
    formular.appendChild(beschriftet("Vorschlag", vorschlag));
    var reihe = el("div", "eintrag-knoepfe");
    var sichern = el("button", "knopf klein haupt", "Speichern");
    sichern.type = "submit";
    var zu = el("button", "knopf klein", "Abbrechen");
    zu.type = "button";
    zu.addEventListener("click", function () { aendernSchliessen(true); });
    reihe.appendChild(sichern);
    reihe.appendChild(zu);
    formular.appendChild(reihe);
    if (z.herkunft === "ki" && z.status === "offen") {
      formular.appendChild(el("p", "leise", "Ein geänderter Vorschlag gilt als bestätigt."));
    }
    var fehler = el("p", "formularfehler");
    fehler.setAttribute("role", "alert");
    fehler.hidden = true;
    formular.appendChild(fehler);
    formular.addEventListener("submit", function (ereignis) {
      ereignis.preventDefault();
      if (sichern.disabled) { return; }
      aendernSpeichern(z.id, kuerzel.value, vorschlag.value.trim(), formular);
    });
    formularTasten(formular, function () { aendernSchliessen(true); });
    return formular;
  }

  function eintragFokus(id) {
    if (eintraege[id]) { eintraege[id].querySelector(".eintrag-wahl").focus({ preventScroll: true }); }
  }

  function aendernOeffnen(id) {
    var z = zeichen[id];
    if (!z || gesperrt || unterwegs[id]) { return; }
    if (z.status === "verworfen") {
      melden("Dieser Vorschlag ist verworfen. Zum Ändern bitte erst zurückholen (Taste Z).", "hinweis");
      return;
    }
    if (setzen) { setzenStellen(false); }
    if (gewaehlt !== id) { waehlen(id, "liste"); }
    formularFuer = id;
    zeichnen(id);
    inSicht($("listenspalte"), eintraege[id], false);
    eintraege[id].querySelector("select").focus({ preventScroll: true });
  }

  function aendernSchliessen(mitFokus) {
    var id = formularFuer;
    if (id === null) { return; }
    formularFuer = null;
    zeichnen(id);
    if (mitFokus) { eintragFokus(id); }
  }

  // Zeigt im Formular, ob gerade gespeichert wird, und die Meldung eines gescheiterten Versuchs.
  function formularStellen(formular, beschaeftigt, meldungstext) {
    formular.querySelector('button[type="submit"]').disabled = beschaeftigt;
    var fehler = formular.querySelector(".formularfehler");
    fehler.textContent = meldungstext || "";
    fehler.hidden = !meldungstext;
  }

  // Speichert die Eingaben des Formulars. Es bleibt offen, bis die Route geantwortet hat:
  // Scheitert sie, stehen die Eingaben noch da, und das Formular nennt den Grund.
  function aendernSpeichern(id, kategorie, vorschlag, formular) {
    var z = zeichen[id];
    if (!z || unterwegs[id]) { return; }
    var koerper = {};
    if (kategorie !== z.kategorie) { koerper.kategorie = kategorie; }
    if (vorschlag !== (z.vorschlag || "")) { koerper.vorschlag = vorschlag; }
    if (!Object.keys(koerper).length) {
      aendernSchliessen(true);
      return;
    }
    var vorlaeufig = kopie(koerper);
    var warOffen = z.herkunft === "ki" && z.status === "offen";
    if (z.herkunft === "ki") {
      vorlaeufig.status = "bestaetigt";
      vorlaeufig.bestaetigt_wie = "geaendert";
    }
    formularStellen(formular, true, "");
    var begonnen = speichern(id, "aendern", vorlaeufig, koerper, warOffen, {
      gelungen: function () {
        if (formularFuer === id) { aendernSchliessen(gewaehlt === id); }
      },
      gescheitert: function (text) {
        if (formularFuer !== id || !formular.isConnected) { return false; }
        formularStellen(formular, false, text);
        inSicht($("listenspalte"), formular, false);
        formular.querySelector("input").focus({ preventScroll: true });
        return true;
      }
    });
    if (!begonnen) { formularStellen(formular, false, ""); }
  }

  // Zeichnet Rahmen und Listenpunkt eines Zeichens neu; der Fokus bleibt, wo er war.
  function zeichnen(id) {
    var z = zeichen[id];
    if (!z) {
      if (formularFuer === id) { formularFuer = null; }
      if (zug !== null && zug.id === id) { zugAbbrechen(); }
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
      if (formularFuer === id) { formularFuer = null; }
      if (alt) { alt.remove(); delete eintraege[id]; }
      return;
    }
    // Ein offenes Formular „Ändern“ bleibt mit Eingaben und Fokus stehen: Es wird nicht neu
    // gebaut, sondern der Rest des Listenpunkts um es herum erneuert.
    var formular = alt && formularFuer === id ? alt.querySelector("form.zeichenformular") : null;
    var neu = eintragBauen(z, formular !== null);
    var fokus = alt && alt.contains(document.activeElement) &&
      !(formular && formular.contains(document.activeElement))
      ? document.activeElement.getAttribute("data-akt") : null;
    if (formular) {
      alt.className = neu.className;
      while (alt.firstChild !== formular) { alt.removeChild(alt.firstChild); }
      while (neu.firstChild) { alt.insertBefore(neu.firstChild, formular); }
      neu = alt;
    } else if (alt) {
      liste.replaceChild(neu, alt);
    } else {
      liste.appendChild(neu);
    }
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
  }

  function arbeitZeigen() {
    $("arbeit-offen").textContent = "in der Arbeit: " + vorschlaege(arbeit.offen);
    var anzeige = $("bestaetigt-anzeige");
    anzeige.hidden = !arbeit.bestaetigt_am;
    $("bestaetigt-wann").textContent = arbeit.bestaetigt_am ? zeitpunkt(arbeit.bestaetigt_am) : "";
    fussleisteZeigen();
  }

  function seiteUnfertig() {
    return daten.seiten.some(function (s) { return s.status !== "fertig"; });
  }

  function seiteInAnalyse() {
    return daten.seiten.some(function (s) { return s.status === "wartet" || s.status === "laeuft"; });
  }

  // Die Knöpfe der Fußleiste folgen dem Stand der Arbeit.
  function fussleisteZeigen() {
    var bestaetigt = Boolean(arbeit.bestaetigt_am);
    $("gesamt-knopf").disabled = gesperrt || fragt || bestaetigt || !arbeit.bestaetigbar;
    $("gesamt-grund").textContent = bestaetigt ? "Die Korrektur ist bestätigt."
      : (arbeit.bestaetigbar ? "" : arbeit.grund || "");
    // Solange eine Seite der Arbeit nicht fertig analysiert ist, wird nichts gesammelt bestätigt.
    $("rest-knopf").disabled = gesperrt || fragt || arbeit.offen === 0 || seiteUnfertig();
    $("neu-analyse-knopf").disabled = seitenstatus !== "fertig" && seitenstatus !== "fehlgeschlagen";
    pdfKnopfZeigen(bestaetigt);
  }

  // „PDF ausgeben“ führt nur zum PDF, solange die Korrektur bestätigt ist. Verfällt die
  // Bestätigung, verliert der Knopf sofort sein Ziel.
  function pdfKnopfZeigen(bestaetigt) {
    var knopf = $("pdf-knopf");
    if (bestaetigt) {
      knopf.setAttribute("href", knopf.getAttribute("data-url"));
      knopf.removeAttribute("aria-disabled");
    } else {
      knopf.removeAttribute("href");
      knopf.setAttribute("aria-disabled", "true");
    }
    $("pdf-hinweis").hidden = bestaetigt;
  }

  // Übernimmt den Stand der Arbeit aus einer Antwort. Maßgeblich ist der Änderungszähler des
  // Servers: Ein Stand, der älter ist als der gezeigte, wird übergangen, gleich in welcher
  // Reihenfolge die Antworten eintreffen. Gibt zurück, ob der Stand übernommen wurde.
  function arbeitStellen(stand) {
    if (!stand || typeof stand.stand !== "number" || stand.stand < arbeit.stand) { return false; }
    arbeit.stand = stand.stand;
    arbeit.offen = stand.offen;
    arbeit.bestaetigt_am = stand.bestaetigt_am;
    arbeit.bestaetigbar = stand.bestaetigbar;
    arbeit.grund = stand.grund;
    if (Array.isArray(stand.seiten)) { daten.seiten = stand.seiten; }
    arbeitZeigen();
    seiteAbgleichen();
    abfragePlanen();
    return true;
  }

  // Hat sich der Analysestatus dieser Seite geändert (etwa eine Neuanalyse aus einem anderen
  // Fenster) oder passen ihre offenen Vorschläge nicht mehr zum Server, lädt die Ansicht neu.
  function seiteAbgleichen() {
    var hier = null;
    daten.seiten.forEach(function (s) { if (s.id === seite.id) { hier = s; } });
    if (hier === null) { return; }
    var anders = !gesperrt && laufend === 0 && !Object.keys(unterwegs).length &&
      hier.status === seitenstatus && hier.offen !== offeneAufDerSeite();
    if ((anders || hier.status !== seitenstatus) && !laedtSeite) {
      laedtSeite = true;
      // Eine Meldung, die gerade zu sehen ist, und der Grund des Neuladens überstehen es.
      var notiz = [];
      if (!meldung.hidden) { notiz.push($("meldung-text").textContent); }
      if (anders) {
        notiz.push("Die Zeichen dieser Seite wurden an anderer Stelle geändert. " +
          "Die Ansicht zeigt jetzt den aktuellen Stand.");
      }
      try {
        if (notiz.length) { window.sessionStorage.setItem(NOTIZ, notiz.join(" ")); }
      } catch (fehler) { /* ohne Speicher lädt die Ansicht ohne Hinweis neu */ }
      window.location.reload();
    }
  }

  var laedtSeite = false;
  var NOTIZ = "korrektor-notiz";

  // Zeigt nach dem Neuladen, was die Ansicht davor noch zu sagen hatte.
  function notizZeigen() {
    try {
      var text = window.sessionStorage.getItem(NOTIZ);
      window.sessionStorage.removeItem(NOTIZ);
      if (text) { melden(text, "hinweis"); }
    } catch (fehler) { /* kein Speicher, kein Hinweis */ }
  }

  // Holt den Stand der Arbeit vom Server. Läuft schon eine Abfrage, folgt danach noch eine,
  // damit nichts fehlt, was inzwischen geschah.
  function nachladen() {
    if (laedtNach) {
      nochmalLaden = true;
      return;
    }
    laedtNach = true;
    if (abfrageUhr !== null) { window.clearTimeout(abfrageUhr); }
    abfrageUhr = null;
    function fertig() {
      laedtNach = false;
      if (nochmalLaden) {
        nochmalLaden = false;
        nachladen();
        return;
      }
      if (sprungFaellig && laufend === 0) {
        sprungFaellig = false;
        weiterNachEntscheidung();
      }
      abfragePlanen();
    }
    senden("GET", "/arbeit/" + arbeit.id + "/zahlen").then(function (antwort) {
      arbeitStellen(antwort.arbeit);
      fertig();
    }, fertig);  // ohne Antwort bleibt der gezeigte Stand; die nächste Gelegenheit holt ihn nach
  }

  // Solange eine Seite der Arbeit wartet oder läuft, alle zwei Sekunden nachfragen; danach nicht mehr.
  function abfragePlanen() {
    if (abfrageUhr !== null || laedtNach || !seiteInAnalyse()) { return; }
    abfrageUhr = window.setTimeout(function () {
      abfrageUhr = null;
      nachladen();
    }, ABSTAND_MS);
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

  // Fokus und Auswahl sind stets dasselbe Zeichen: Erhält ein Listenpunkt oder ein Rahmen den
  // Fokus (etwa mit Tab), ist dieses Zeichen gewählt. Die Tasten wirken so nie auf ein anderes
  // Zeichen als das, auf dem der Fokus steht.
  function zeichenVon(element) {
    var traeger = element && element.closest ? element.closest("[data-zeichen]") : null;
    return traeger ? Number(traeger.getAttribute("data-zeichen")) : null;
  }

  liste.addEventListener("focusin", function (ereignis) {
    var id = zeichenVon(ereignis.target);
    if (id !== null && id !== gewaehlt && zeichen[id]) { waehlen(id, "liste"); }
  });
  ebene.addEventListener("focusin", function (ereignis) {
    var id = zeichenVon(ereignis.target);
    if (id !== null && id !== gewaehlt && zeichen[id]) { waehlen(id, "bild"); }
  });

  // Das Formular „Ändern“ gehört zum gewählten Zeichen; wechselt die Auswahl, schließt es sich.
  function auswahlGewechselt() {
    if (formularFuer !== null && formularFuer !== gewaehlt) { aendernSchliessen(false); }
  }

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
      if (s.id !== seite.id && s.offen > 0) { return s.nummer; }
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
  // Läuft erst, wenn keine Anfrage mehr unterwegs und der Stand der Arbeit nachgeladen ist.
  function weiterNachEntscheidung() {
    if (laufend > 0 || Object.keys(unterwegs).length || offeneDerSeite().length) { return; }
    var nummer = naechsteSeiteMitOffenen();
    if (nummer !== null) {
      window.location.href = seitenUrl(nummer);
    } else if (arbeit.offen === 0) {
      arbeitDurch();
    }
  }

  // Ist in der ganzen Arbeit nichts mehr offen, wartet der Fokus auf der Gesamtbestätigung.
  function arbeitDurch() {
    var knopf = $("gesamt-knopf");
    if (!knopf.disabled) { knopf.focus(); }
  }

  // --- Entscheiden: bestätigen, verwerfen, zurückholen --------------------------------------

  function kopie(z) {
    var neu = {};
    Object.keys(z).forEach(function (feld) { neu[feld] = z[feld]; });
    return neu;
  }

  // Zeigt die Änderung sofort, speichert sie und nimmt sie zurück, wenn das Speichern scheitert.
  // `vorlaeufig` sind die Felder, die sich voraussichtlich ändern; es gilt, was die Route meldet.
  // `formular` (für „Ändern“) nennt, was nach der Antwort mit dem offenen Formular geschieht:
  // `gelungen()` und `gescheitert(Meldung)`; die Auswahl wandert dann erst nach dem Speichern.
  function speichern(id, pfad, vorlaeufig, koerper, entscheidung, formular) {
    var z = zeichen[id];
    if (!z || unterwegs[id] || gesperrt) { return false; }
    var vorher = kopie(z);
    var ziel = naechsterOffener(id);  // vor der Änderung: danach fehlt ein Verworfenes in der Reihe
    Object.keys(vorlaeufig).forEach(function (feld) { z[feld] = vorlaeufig[feld]; });
    unterwegs[id] = true;
    zeichnen(id);
    zahlenZeigen();
    function weiter() {
      if (ziel !== null && zeichen[ziel] && zeichen[ziel].status === "offen") {
        waehlen(ziel, "taste");
      } else if (!zeichen[id] || !sichtbar(zeichen[id])) {
        waehlen(null);
      }
    }
    if (!formular && (entscheidung || !sichtbar(z))) { weiter(); }
    schreiben("/zeichen/" + id + "/" + pfad, koerper).then(function (antwort) {
      delete unterwegs[id];
      if (antwort.zeichen) { zeichen[id] = antwort.zeichen; }
      arbeitStellen(antwort.arbeit);
      zeichnen(id);
      listeOrdnen();
      zahlenZeigen();
      if (formular) {
        formular.gelungen();
        if (entscheidung && gewaehlt === id) { weiter(); }
      }
      if (entscheidung) { sprungFaellig = true; }
    }, function (fehler) {
      delete unterwegs[id];
      zeichen[id] = vorher;
      zeichnen(id);
      listeOrdnen();
      zahlenZeigen();
      if (formular && formular.gescheitert(fehlertext(fehler))) { return; }
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

  // Löscht ein eigenes Zeichen; scheitert das Speichern, steht es wieder da.
  function loeschen(id) {
    var z = zeichen[id];
    if (!z || unterwegs[id] || gesperrt) { return; }
    if (z.herkunft !== "hand") {
      melden("Vorschläge der KI werden verworfen, nicht gelöscht (Taste V).", "hinweis");
      return;
    }
    var ziel = naechsterOffener(id);
    unterwegs[id] = true;
    delete zeichen[id];
    zeichnen(id);
    zahlenZeigen();
    if (gewaehlt === id) { waehlen(ziel, "taste"); }
    schreiben("/zeichen/" + id + "/loeschen").then(function (antwort) {
      delete unterwegs[id];
      arbeitStellen(antwort.arbeit);
    }, function (fehler) {
      delete unterwegs[id];
      zeichen[id] = z;
      zeichnen(id);
      listeOrdnen();
      zahlenZeigen();
      melden(fehlertext(fehler));
      waehlen(id, "taste");
    });
  }

  // Die Taste Entf: verwirft einen Vorschlag der KI, löscht ein eigenes Zeichen.
  function entfernen(id) {
    var z = zeichen[id];
    if (z && z.herkunft === "hand") { loeschen(id); } else { verwerfen(id); }
  }

  var AKTIONEN = { bestaetigen: bestaetigen, verwerfen: verwerfen, zurueckholen: zurueckholen,
                   aendern: aendernOeffnen, loeschen: loeschen };

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

  // --- Zeichen selbst setzen -----------------------------------------------------------------

  var setzenKnopf = $("setzen-knopf");
  var neuFormular = $("neu-formular");

  function entwurfVerwerfen() {
    if (entwurf !== null) { entwurf.element.remove(); }
    entwurf = null;
    aufzug = null;
    neuFormular.hidden = true;
  }

  function setzenStellen(an) {
    if (an && gesperrt) { return; }
    setzen = an;
    ebene.classList.toggle("setzen", an);
    setzenKnopf.setAttribute("aria-pressed", an ? "true" : "false");
    $("setzen-hinweis").hidden = !an;
    if (an) { aendernSchliessen(false); } else { entwurfVerwerfen(); }
  }

  function entwurfLage(a, b) {
    var x = Math.round(Math.min(a.x, b.x)), y = Math.round(Math.min(a.y, b.y));
    return { x: x, y: y, breite: Math.round(Math.max(a.x, b.x)) - x,
             hoehe: Math.round(Math.max(a.y, b.y)) - y };
  }

  function imBild(p) {
    return { x: klemmen(p.x, 0, seite.breite), y: klemmen(p.y, 0, seite.hoehe) };
  }

  ebene.addEventListener("pointerdown", function (ereignis) {
    if (!setzen || aufzug !== null || $("neu-setzen").disabled) { return; }
    if (ereignis.pointerType === "mouse" && ereignis.button !== 0) { return; }
    ereignis.preventDefault();
    entwurfVerwerfen();
    var element = el("div", "rahmen kat-hand entwurf");
    element.appendChild(el("span", "etikett", "neu"));
    ebene.appendChild(element);
    var start = imBild(bildpunkt(ereignis));
    aufzug = { zeiger: ereignis.pointerId, start: start };
    entwurf = { element: element, lage: entwurfLage(start, start) };
    rahmenLegen(element, entwurf.lage);
    try { ebene.setPointerCapture(ereignis.pointerId); } catch (fehler) { /* Zeiger schon weg */ }
  });

  ebene.addEventListener("pointermove", function (ereignis) {
    if (aufzug === null || ereignis.pointerId !== aufzug.zeiger) { return; }
    entwurf.lage = entwurfLage(aufzug.start, imBild(bildpunkt(ereignis)));
    rahmenLegen(entwurf.element, entwurf.lage);
  });

  function aufzugBeenden(ereignis, gueltig) {
    if (aufzug === null || ereignis.pointerId !== aufzug.zeiger) { return; }
    aufzug = null;
    try { ebene.releasePointerCapture(ereignis.pointerId); } catch (fehler) { /* schon frei */ }
    if (!gueltig) {
      entwurfVerwerfen();
      return;
    }
    if (entwurf.lage.breite < KLEINSTER_ENTWURF || entwurf.lage.hoehe < KLEINSTER_ENTWURF) {
      entwurfVerwerfen();
      melden("Der Rahmen ist zu klein. Bitte mit gedrückter Taste einen größeren Rahmen aufziehen.",
        "hinweis");
      return;
    }
    kuerzelFuellen($("neu-kuerzel"), letztesKuerzel);
    $("neu-vorschlag").value = "";
    neuFormular.hidden = false;
    inSicht($("listenspalte"), neuFormular, false);
    $("neu-kuerzel").focus({ preventScroll: true });
  }

  ebene.addEventListener("pointerup", function (ereignis) { aufzugBeenden(ereignis, true); });
  ebene.addEventListener("pointercancel", function (ereignis) { aufzugBeenden(ereignis, false); });

  neuFormular.addEventListener("submit", function (ereignis) {
    ereignis.preventDefault();
    if (entwurf === null || $("neu-setzen").disabled) { return; }
    var lage = entwurf.lage;
    var koerper = { kategorie: $("neu-kuerzel").value, typ: $("neu-typ").value,
                    x: lage.x, y: lage.y, breite: lage.breite, hoehe: lage.hoehe };
    var vorschlag = $("neu-vorschlag").value.trim();
    if (vorschlag) { koerper.vorschlag = vorschlag; }
    $("neu-setzen").disabled = true;
    schreiben("/seite/" + seite.id + "/zeichen", koerper).then(function (antwort) {
      $("neu-setzen").disabled = false;
      letztesKuerzel = koerper.kategorie;
      setzenStellen(false);
      var z = antwort.zeichen;
      if (z) { zeichen[z.id] = z; }
      arbeitStellen(antwort.arbeit);
      if (!z) { return; }
      zeichnen(z.id);
      listeOrdnen();
      zahlenZeigen();
      waehlen(z.id, "taste");
    }, function (fehler) {
      $("neu-setzen").disabled = false;
      melden(fehlertext(fehler));
      if (!neuFormular.hidden) { $("neu-kuerzel").focus({ preventScroll: true }); }
    });
  });

  function setzenAbbrechen() {
    setzenStellen(false);
    setzenKnopf.focus({ preventScroll: true });
  }

  formularTasten(neuFormular, setzenAbbrechen);
  $("neu-abbrechen").addEventListener("click", setzenAbbrechen);
  setzenKnopf.addEventListener("click", function () { setzenStellen(!setzen); });
  setzenKnopf.disabled = gesperrt;
  ebene.classList.toggle("lesend", gesperrt);

  // --- Rückfragen, Rest bestätigen, Gesamtbestätigung, Neuanalyse -----------------------------

  // Öffnet die Rückfrage; Esc und „Abbrechen“ schließen sie ohne Wirkung.
  function fragen(dialog, beiJa) {
    // Das „Ja“ gilt mit dem Absenden des Formulars im Dialog, nicht erst mit dessen Schließen:
    // Das Ereignis `close` kommt in einem verdeckten Fenster verspätet.
    dialog.querySelector("form").onsubmit = function (ereignis) {
      if (ereignis.submitter && ereignis.submitter.value === "ja") { beiJa(); }
    };
    dialog.showModal();
  }

  // Holt vor einer Rückfrage den frischen Stand der Arbeit und gibt die Antwort an `weiter`.
  // Der Dialog zeigt so nie Zahlen, die inzwischen überholt sind, und schickt den Stand mit,
  // den er gezeigt hat; hat sich bis zum „Ja“ noch etwas geändert, lehnt die App ab.
  function frischFragen(weiter) {
    if (fragt) { return; }
    fragt = true;
    fussleisteZeigen();
    senden("GET", "/arbeit/" + arbeit.id + "/zahlen").then(function (antwort) {
      fragt = false;
      arbeitStellen(antwort.arbeit);
      fussleisteZeigen();
      weiter(antwort);
    }, function (fehler) {
      fragt = false;
      fussleisteZeigen();
      melden(fehlertext(fehler));
    });
  }

  $("rest-knopf").addEventListener("click", function () {
    if (gesperrt) { return; }
    frischFragen(function (antwort) {
      var stand = antwort.arbeit;
      var zahl = stand.offen;
      var hier = 0;
      var unfertig = false;
      stand.seiten.forEach(function (s) {
        if (s.id === seite.id) { hier = s.offen; }
        unfertig = unfertig || s.status !== "fertig";
      });
      if (unfertig) {
        melden((stand.grund ? stand.grund + " " : "") +
          "Bis alle Seiten fertig analysiert sind, wird nichts gesammelt bestätigt.", "hinweis");
        return;
      }
      if (!zahl) {
        melden("In dieser Arbeit ist kein Vorschlag mehr offen.", "hinweis");
        return;
      }
      $("rest-text").textContent = (zahl === 1
        ? "In dieser Arbeit ist noch 1 Vorschlag offen"
        : "In dieser Arbeit sind noch " + zahl + " Vorschläge offen") +
        (stand.seiten.length > 1 ? ", davon " + hier + " auf dieser Seite" : "") + ". " +
        (zahl === 1 ? "Diesen Vorschlag" : "Alle " + zahl + " Vorschläge") +
        " ungeprüft als bestätigt übernehmen?";
      $("rest-ja").textContent = zahl === 1 ? "1 Vorschlag bestätigen" : "Alle " + zahl + " bestätigen";
      fragen($("rest-dialog"), function () { restBestaetigen(stand.stand); });
    });
  });

  function offeneAufDerSeite() {
    return Object.keys(zeichen).filter(function (id) { return zeichen[id].status === "offen"; }).length;
  }

  // `stand` ist der Stand der Arbeit, den der Dialog gezeigt hat.
  function restBestaetigen(stand) {
    fragt = true;
    fussleisteZeigen();
    schreiben("/arbeit/" + arbeit.id + "/rest-bestaetigen", { stand: stand }).then(function (antwort) {
      fragt = false;
      (antwort.geaendert || []).forEach(function (id) {
        if (zeichen[id] && !unterwegs[id]) {
          zeichen[id].status = "bestaetigt";
          zeichen[id].bestaetigt_wie = "gesammelt";
        }
      });
      arbeitStellen(antwort.arbeit);
      allesZeichnen();
      fussleisteZeigen();
      sprungFaellig = true;  // nach dem Nachladen: zur Gesamtbestätigung
    }, function (fehler) {
      fragt = false;
      fussleisteZeigen();
      melden(fehlertext(fehler));  // den aktuellen Stand lädt die Ansicht gleich nach
    });
  }

  $("gesamt-knopf").addEventListener("click", function () {
    frischFragen(function (antwort) {
      if (antwort.arbeit.bestaetigt_am) { return; }  // inzwischen anderswo bestätigt
      if (!antwort.bestaetigbar) {
        melden(antwort.grund || "Die Arbeit lässt sich noch nicht bestätigen.", "hinweis");
        return;
      }
      ["einzeln", "gesammelt", "geaendert", "verworfen", "hand"].forEach(function (feld) {
        $("zahl-" + feld).textContent = antwort.zahlen[feld];
      });
      fragen($("gesamt-dialog"), function () { gesamtBestaetigen(antwort.arbeit.stand); });
    });
  });

  // `stand` ist der Stand der Arbeit, zu dem der Dialog die Zahlen gezeigt hat.
  function gesamtBestaetigen(stand) {
    fragt = true;
    fussleisteZeigen();
    schreiben("/arbeit/" + arbeit.id + "/bestaetigen", { stand: stand }).then(function (antwort) {
      fragt = false;
      arbeitStellen(antwort.arbeit);
      fussleisteZeigen();
      var weiter = $("arbeit-weiter");
      if (weiter && arbeit.bestaetigt_am) { weiter.focus(); }
    }, function (fehler) {
      fragt = false;
      fussleisteZeigen();
      melden(fehlertext(fehler));  // den aktuellen Stand lädt die Ansicht gleich nach
    });
  }

  $("neu-analyse-knopf").addEventListener("click", function () {
    fragen($("neu-analyse-dialog"), function () {
      var knopf = $("neu-analyse-knopf");
      knopf.disabled = true;
      schreiben("/seite/" + seite.id + "/neu-analysieren").then(function () {
        window.location.reload();  // die Seite zeigt dann den Lauf und wartet auf sein Ende
      }, function (fehler) {
        fussleisteZeigen();
        melden(fehlertext(fehler));
      });
    });
  });

  // --- Kürzel der Arbeit ---------------------------------------------------------------------

  var kuerzelFormular = $("kuerzel-formular");

  function kuerzelFormularStellen(offen) {
    kuerzelFormular.hidden = !offen;
    $("kuerzel-knopf").hidden = offen;
    if (offen) {
      $("kuerzel-feld").value = arbeit.kuerzel;
      $("kuerzel-feld").focus();
      $("kuerzel-feld").select();
    } else {
      $("kuerzel-knopf").focus();
    }
  }

  $("kuerzel-knopf").addEventListener("click", function () { kuerzelFormularStellen(true); });
  $("kuerzel-abbrechen").addEventListener("click", function () { kuerzelFormularStellen(false); });
  formularTasten(kuerzelFormular, function () { kuerzelFormularStellen(false); });

  kuerzelFormular.addEventListener("submit", function (ereignis) {
    ereignis.preventDefault();
    var neu = $("kuerzel-feld").value.trim();
    if (neu === arbeit.kuerzel) {
      kuerzelFormularStellen(false);
      return;
    }
    senden("POST", "/arbeit/" + arbeit.id + "/kuerzel", { kuerzel: neu }).then(function (antwort) {
      var alt = arbeit.kuerzel;
      arbeit.kuerzel = typeof antwort.kuerzel === "string" ? antwort.kuerzel : neu;
      Array.prototype.forEach.call(document.querySelectorAll('[data-rolle="arbeitskuerzel"]'),
        function (stelle) { stelle.textContent = arbeit.kuerzel; });
      document.title = document.title.replace("Arbeit " + alt, "Arbeit " + arbeit.kuerzel);
      kuerzelFormularStellen(false);
    }, function (fehler) {
      melden(fehlertext(fehler));
      $("kuerzel-feld").focus();
    });
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

  // Esc räumt von innen nach außen auf: Modus „Zeichen setzen“, Formular, Meldung, Auswahl.
  function abbrechen() {
    if (setzen) { setzenStellen(false); return; }
    if (formularFuer !== null) { aendernSchliessen(true); return; }
    if (!meldung.hidden) { meldungSchliessen(); return; }
    waehlen(null);
  }

  // Weitere Tasten; gibt true zurück, wenn die Taste verbraucht ist.
  function weitereTaste(taste) {
    if (taste === "e") {
      aendernOeffnen(gewaehlt);
    } else if (taste === "s") {
      setzenStellen(!setzen);
    } else {
      return false;
    }
    return true;
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

    // Solange ein Rahmen gezogen oder aufgezogen wird, ruhen die Tasten; Esc bricht ab.
    if (zug !== null || aufzug !== null) {
      ereignis.preventDefault();
      if (taste === "Escape") {
        zugAbbrechen();
        if (aufzug !== null) { abbrechen(); }
      }
      return;
    }
    // Eine gehaltene Taste entscheidet nicht Zeichen um Zeichen weiter.
    var aktion = taste === "b" || taste === "v" || taste === "Delete" || taste === "z" ||
      taste === "e" || taste === "s" || (taste === "Enter" && aufZeichen);
    if (aktion && ereignis.repeat) {
      ereignis.preventDefault();
      return;
    }
    // Die Tasten wirken auf das Zeichen, auf dem der Fokus steht; es ist dann auch das gewählte.
    var imFokus = zeichenVon(ziel);
    if (imFokus !== null && imFokus !== gewaehlt && zeichen[imFokus]) { waehlen(imFokus, "liste"); }

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
  // Wartet oder läuft eine Seite der Arbeit, fragt die Ansicht nach, bis alle fertig sind. Ist
  // es diese Seite, lädt die Ansicht danach neu und zeigt die neuen Vorschläge.
  abfragePlanen();
  notizZeigen();

  // Eine Ansicht, die geruht hat (aus dem Verlauf zurückgeholt oder wieder sichtbar geworden),
  // fragt den Stand einmal neu ab: Inzwischen kann in einem anderen Fenster korrigiert worden sein.
  window.addEventListener("pageshow", function (ereignis) {
    if (ereignis.persisted) { nachladen(); }
  });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") { nachladen(); }
  });
})();
