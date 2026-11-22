// Hochladen und Zuordnen: Fotos ablegen, ordnen, per Trennmarke zu Arbeiten verbinden.
// Reihenfolge und Trennmarken werden nach jeder Änderung gespeichert, sobald kein Upload
// mehr läuft. Der Server entfernt dabei nur die Fotos, die hier ausdrücklich entfernt
// wurden; Fotos, die diese Seite nicht kennt, bleiben erhalten.
(function () {
  "use strict";

  var daten = JSON.parse(document.getElementById("zuordnen-daten").textContent);
  var eintraege = daten.eintraege.map(function (e) {
    return { id: e.id, neue_arbeit: !!e.neue_arbeit };
  });

  var reihe = document.getElementById("reihe");
  var leerhinweis = document.getElementById("leerhinweis");
  var zusammenfassung = document.getElementById("zusammenfassung");
  var speicherstand = document.getElementById("speicherstand");
  var speicherfehler = document.getElementById("speicherfehler");
  var fortschritt = document.getElementById("fortschritt");
  var abgelehnt = document.getElementById("abgelehnt");
  var ablegefeld = document.getElementById("ablegefeld");
  var dateiwahl = document.getElementById("dateien");
  var formular = document.getElementById("startformular");
  var startknopf = document.getElementById("start");

  var wartend = [];          // ausgewählte, noch nicht übertragene Dateien
  var laedt = false;         // gerade wird eine Datei übertragen
  var zahlGesamt = 0, zahlErledigt = 0;
  var geaendert = false;     // ungespeicherte Änderung an Reihenfolge oder Marken
  var speichert = false;
  var speichernGescheitert = false;
  var startGewuenscht = false;
  var gezogen = null;        // id des Fotos, das gerade gezogen wird
  var entfernt = [];         // ids entfernter Fotos, die der Server noch nicht gelöscht hat

  function element(name, klasse, text) {
    var e = document.createElement(name);
    if (klasse) { e.className = klasse; }
    if (text !== undefined) { e.textContent = text; }
    return e;
  }

  function zweistellig(zahl) {
    return zahl < 10 ? "0" + zahl : String(zahl);
  }

  function uploadsLaufen() {
    return laedt || wartend.length > 0;
  }

  // --- Zustand ändern ---------------------------------------------------------------

  function gruppen() {
    var liste = [];
    eintraege.forEach(function (e, platz) {
      if (platz === 0 || e.neue_arbeit) { liste.push([]); }
      liste[liste.length - 1].push(e.id);
    });
    return liste;
  }

  function ausGruppen(liste) {
    eintraege = [];
    liste.forEach(function (gruppe) {
      gruppe.forEach(function (id, platz) {
        eintraege.push({ id: id, neue_arbeit: platz === 0 });
      });
    });
  }

  function ohne(liste, id) {
    return liste.map(function (gruppe) {
      return gruppe.filter(function (andere) { return andere !== id; });
    }).filter(function (gruppe) { return gruppe.length > 0; });
  }

  function entfernen(id) {
    ausGruppen(ohne(gruppen(), id));
    if (entfernt.indexOf(id) < 0) { entfernt.push(id); }
    aenderung();
  }

  // Setzt das Foto vor oder hinter ein anderes; es gehört danach zu dessen Arbeit.
  function versetzen(id, zielId, dahinter) {
    if (id === zielId) { return; }
    var liste = ohne(gruppen(), id);
    liste.forEach(function (gruppe) {
      var platz = gruppe.indexOf(zielId);
      if (platz >= 0) { gruppe.splice(platz + (dahinter ? 1 : 0), 0, id); }
    });
    ausGruppen(liste);
    aenderung();
  }

  // Tauscht zwei benachbarte Fotos; die Trennmarken bleiben an ihrem Platz.
  function tauschen(platz, anderer) {
    if (anderer < 0 || anderer >= eintraege.length) { return; }
    var id = eintraege[platz].id;
    eintraege[platz].id = eintraege[anderer].id;
    eintraege[anderer].id = id;
    aenderung(id);
  }

  function markeUmschalten(platz) {
    eintraege[platz].neue_arbeit = !eintraege[platz].neue_arbeit;
    aenderung();
  }

  function aenderung(fokusId) {
    geaendert = true;
    zeichnen();
    if (fokusId !== undefined) {
      var karte = reihe.querySelector('[data-id="' + Number(fokusId) + '"] .griff');
      if (karte) { karte.focus(); }
    }
    speichernWennMoeglich();
  }

  // --- Zeichnen ---------------------------------------------------------------------

  function karteBauen(eintrag, platz, seite) {
    var karte = element("div", "karte");
    karte.setAttribute("data-id", eintrag.id);
    karte.draggable = true;

    var bild = element("img");
    bild.src = daten.url_bild + eintrag.id + "?b=300";
    bild.alt = "Foto " + (platz + 1);
    bild.loading = "lazy";
    bild.draggable = false;
    karte.appendChild(bild);

    var leiste = element("div", "kartenleiste");
    var vor = element("button", "griff", "‹");
    vor.type = "button";
    vor.setAttribute("aria-label", "Foto " + (platz + 1) + " nach vorn schieben");
    vor.disabled = platz === 0;
    vor.addEventListener("click", function () { tauschen(platz, platz - 1); });
    var seitenangabe = element("span", "seitenangabe", "S. " + seite);
    var zurueck = element("button", "griff", "›");
    zurueck.type = "button";
    zurueck.setAttribute("aria-label", "Foto " + (platz + 1) + " nach hinten schieben");
    zurueck.disabled = platz === eintraege.length - 1;
    zurueck.addEventListener("click", function () { tauschen(platz, platz + 1); });
    var weg = element("button", "griff weg", "✕");
    weg.type = "button";
    weg.setAttribute("aria-label", "Foto " + (platz + 1) + " entfernen");
    weg.title = "Foto entfernen";
    weg.addEventListener("click", function () { entfernen(eintrag.id); });
    leiste.appendChild(vor);
    leiste.appendChild(seitenangabe);
    leiste.appendChild(zurueck);
    leiste.appendChild(weg);
    karte.appendChild(leiste);

    karte.addEventListener("dragstart", function (ereignis) {
      gezogen = eintrag.id;
      ereignis.dataTransfer.effectAllowed = "move";
      ereignis.dataTransfer.setData("text/plain", String(eintrag.id));
      karte.classList.add("gezogen");
    });
    karte.addEventListener("dragend", function () {
      gezogen = null;
      zielLoeschen();
      karte.classList.remove("gezogen");
    });
    karte.addEventListener("dragover", function (ereignis) {
      if (gezogen === null || gezogen === eintrag.id) { return; }
      ereignis.preventDefault();
      ereignis.dataTransfer.dropEffect = "move";
      zielLoeschen();
      karte.classList.add(dahinter(karte, ereignis) ? "ziel-dahinter" : "ziel-davor");
    });
    karte.addEventListener("drop", function (ereignis) {
      if (gezogen === null) { return; }
      ereignis.preventDefault();
      var id = gezogen;
      gezogen = null;
      versetzen(id, eintrag.id, dahinter(karte, ereignis));
    });
    return karte;
  }

  function dahinter(karte, ereignis) {
    var kasten = karte.getBoundingClientRect();
    return ereignis.clientX > kasten.left + kasten.width / 2;
  }

  function zielLoeschen() {
    Array.prototype.forEach.call(reihe.querySelectorAll(".ziel-davor, .ziel-dahinter"),
      function (e) { e.classList.remove("ziel-davor", "ziel-dahinter"); });
  }

  function markeBauen(platz, aktiv) {
    var marke = element("button", "trennmarke" + (aktiv ? " aktiv" : ""));
    marke.type = "button";
    marke.setAttribute("aria-pressed", aktiv ? "true" : "false");
    marke.setAttribute("aria-label", aktiv
      ? "Trennmarke zwischen Foto " + platz + " und " + (platz + 1) +
        ": getrennt, hier beginnt eine neue Arbeit. Klicken zum Verbinden."
      : "Trennmarke zwischen Foto " + platz + " und " + (platz + 1) +
        ": verbunden, beide Fotos gehören zu einer Arbeit. Klicken zum Trennen.");
    marke.title = aktiv ? "Hier beginnt eine neue Arbeit – klicken zum Verbinden"
                        : "Gehört zur selben Arbeit – klicken zum Trennen";
    marke.appendChild(element("span", "strich"));
    marke.appendChild(element("span", "wort", aktiv ? "getrennt" : "verbunden"));
    marke.addEventListener("click", function () { markeUmschalten(platz); });
    return marke;
  }

  function zeichnen() {
    if (eintraege.length) { eintraege[0].neue_arbeit = true; }
    reihe.textContent = "";
    var gruppe = null, fotos = null, nummer = daten.naechste_nummer - 1, seite = 0, arbeiten = 0;
    var kopf = null;
    eintraege.forEach(function (eintrag, platz) {
      if (eintrag.neue_arbeit) {
        if (platz > 0) { reihe.appendChild(markeBauen(platz, true)); }
        nummer += 1; arbeiten += 1; seite = 0;
        gruppe = element("div", "gruppe");
        kopf = element("div", "gruppenkopf");
        gruppe.appendChild(kopf);
        fotos = element("div", "gruppenfotos");
        gruppe.appendChild(fotos);
        reihe.appendChild(gruppe);
      } else {
        fotos.appendChild(markeBauen(platz, false));
      }
      seite += 1;
      kopf.textContent = "Arbeit " + zweistellig(nummer) + " · " +
        (seite === 1 ? "1 Seite" : seite + " Seiten");
      fotos.appendChild(karteBauen(eintrag, platz, seite));
    });
    leerhinweis.hidden = eintraege.length > 0;
    zusammenfassung.textContent =
      (eintraege.length === 1 ? "1 Foto" : eintraege.length + " Fotos") + " in " +
      (arbeiten === 1 ? "1 Arbeit" : arbeiten + " Arbeiten");
    knopfStellen();
  }

  function knopfStellen() {
    startknopf.disabled = eintraege.length === 0 || uploadsLaufen() || speichernGescheitert;
  }

  // --- Speichern --------------------------------------------------------------------

  function speichernWennMoeglich() {
    if (speichert || uploadsLaufen()) { return; }
    if (!geaendert) { ruhig(); return; }
    geaendert = false;
    speichert = true;
    speicherstand.textContent = "Speichert …";
    var gesendet = entfernt.slice();
    fetch(daten.url_ordnen, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ eintraege: eintraege, entfernt: gesendet })
    }).then(function (antwort) {
      if (!antwort.ok) { throw new Error("Status " + antwort.status); }
      // Gelöscht ist, was mitgeschickt wurde; währenddessen Entferntes folgt beim nächsten Mal.
      entfernt = entfernt.filter(function (id) { return gesendet.indexOf(id) < 0; });
      speichernGescheitert = false;
      speicherfehler.hidden = true;
    }).catch(function () {
      speichernGescheitert = true;
      startGewuenscht = false;
      speicherfehler.hidden = false;
    }).then(function () {
      speichert = false;
      if (geaendert && !speichernGescheitert) { speichernWennMoeglich(); } else { ruhig(); }
    });
  }

  // Alles übertragen und gespeichert: Anzeige nachziehen, gewünschten Start ausführen.
  function ruhig() {
    speicherstand.textContent = speichernGescheitert ? "Nicht gespeichert"
      : (eintraege.length ? "Gespeichert" : "");
    knopfStellen();
    if (startGewuenscht && !speichernGescheitert && eintraege.length) {
      startGewuenscht = false;
      formular.submit();
    }
  }

  formular.addEventListener("submit", function (ereignis) {
    if (uploadsLaufen() || speichert || geaendert) {
      ereignis.preventDefault();
      startGewuenscht = true;
      speichernWennMoeglich();
    }
  });

  // --- Hochladen --------------------------------------------------------------------

  function ablehnen(dateiname, grund) {
    var zeile = element("li");
    zeile.appendChild(element("strong", "", dateiname));
    zeile.appendChild(document.createTextNode(" – " + grund));
    abgelehnt.querySelector("ul").appendChild(zeile);
    abgelehnt.hidden = false;
  }

  function fortschrittZeigen() {
    if (!uploadsLaufen()) {
      fortschritt.hidden = true;
      return;
    }
    fortschritt.hidden = false;
    fortschritt.textContent = "Lädt Foto " + Math.min(zahlErledigt + 1, zahlGesamt) +
      " von " + zahlGesamt + " hoch …";
  }

  function dateienAnnehmen(liste) {
    var dateien = Array.prototype.slice.call(liste);
    dateien.sort(function (a, b) {
      return a.name.localeCompare(b.name, "de", { numeric: true });
    });
    var grenze = Math.round(daten.max_datei / (1024 * 1024));
    dateien.forEach(function (datei) {
      if (datei.size > daten.max_datei) {
        ablehnen(datei.name, "zu groß (höchstens " + grenze + " MB je Datei)");
      } else {
        wartend.push(datei);
        zahlGesamt += 1;
      }
    });
    naechsteDatei();
  }

  // Eine Datei je Anfrage und nacheinander: so bleibt die Reihenfolge erhalten.
  function naechsteDatei() {
    if (laedt) { return; }
    var datei = wartend.shift();
    if (!datei) {
      zahlGesamt = 0; zahlErledigt = 0;
      fortschrittZeigen();
      knopfStellen();
      speichernWennMoeglich();
      return;
    }
    laedt = true;
    fortschrittZeigen();
    knopfStellen();
    var formulardaten = new FormData();
    formulardaten.append("fotos", datei, datei.name);
    fetch(daten.url_hochladen, {
      method: "POST", body: formulardaten, headers: { "Accept": "application/json" }
    }).then(function (antwort) {
      return antwort.json().then(function (inhalt) {
        if (!antwort.ok) {
          ablehnen(datei.name, inhalt.fehler || "Fehler beim Hochladen");
          return;
        }
        inhalt.angenommen.forEach(function (e) {
          eintraege.push({ id: e.id, neue_arbeit: true });
        });
        inhalt.abgelehnt.forEach(function (e) { ablehnen(e.dateiname, e.grund); });
        zeichnen();
      });
    }).catch(function () {
      ablehnen(datei.name, "Übertragung fehlgeschlagen");
    }).then(function () {
      laedt = false;
      zahlErledigt += 1;
      naechsteDatei();
    });
  }

  dateiwahl.addEventListener("change", function () {
    dateienAnnehmen(dateiwahl.files);
    dateiwahl.value = "";
  });

  function traegtDateien(ereignis) {
    var arten = ereignis.dataTransfer && ereignis.dataTransfer.types;
    return !!arten && Array.prototype.indexOf.call(arten, "Files") >= 0;
  }

  ablegefeld.addEventListener("dragover", function (ereignis) {
    if (!traegtDateien(ereignis)) { return; }
    ereignis.preventDefault();
    ereignis.dataTransfer.dropEffect = "copy";
    ablegefeld.classList.add("bereit");
  });
  ablegefeld.addEventListener("dragleave", function () {
    ablegefeld.classList.remove("bereit");
  });
  ablegefeld.addEventListener("drop", function (ereignis) {
    if (!traegtDateien(ereignis)) { return; }
    ereignis.preventDefault();
    ablegefeld.classList.remove("bereit");
    dateienAnnehmen(ereignis.dataTransfer.files);
  });
  // Daneben fallen gelassene Dateien sollen nicht die Seite ersetzen.
  ["dragover", "drop"].forEach(function (art) {
    window.addEventListener(art, function (ereignis) {
      if (traegtDateien(ereignis)) { ereignis.preventDefault(); }
    });
  });

  window.addEventListener("beforeunload", function (ereignis) {
    if (uploadsLaufen() || speichert || geaendert) {
      ereignis.preventDefault();
      ereignis.returnValue = "";
    }
  });

  zeichnen();
  ruhig();
})();
