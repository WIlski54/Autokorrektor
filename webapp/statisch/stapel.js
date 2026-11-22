// Stapelansicht: fragt den Stand ab, solange etwas wartet oder läuft, und zieht die Kacheln nach;
// ebenso einmal, wenn die Ansicht nach einer Pause wieder gezeigt wird.
(function () {
  "use strict";

  var daten = JSON.parse(document.getElementById("stapel-daten").textContent);
  var kacheln = document.getElementById("kacheln");
  var balken = document.getElementById("gesamtbalken");
  var gesamttext = document.getElementById("gesamttext");
  var fehlerfeld = document.getElementById("stapelfehler");
  var ABSTAND_MS = 2000;
  var ERNEUT_FEHLER = "Die Seite ließ sich nicht erneut einreihen. Läuft die App noch? " +
    "Bitte die Seite neu laden und noch einmal versuchen.";
  var geplant = null;
  var unterwegs = false;   // eine Abfrage läuft gerade
  var nochmal = false;     // danach gleich noch einmal abfragen

  function vorschlaege(zahl) {
    return zahl === 1 ? "1 offener Vorschlag" : zahl + " offene Vorschläge";
  }

  function fehlerZeigen(text) {
    fehlerfeld.textContent = text || "";
    fehlerfeld.hidden = !text;
  }

  function kachelStellen(kachel, arbeit) {
    var status = kachel.querySelector('[data-rolle="status"]');
    status.className = "status status-" + arbeit.status_gesamt;
    status.textContent = daten.statustext[arbeit.status_gesamt] || arbeit.status_gesamt;

    var offen = kachel.querySelector('[data-rolle="offen"]');
    offen.textContent = arbeit.offen ? vorschlaege(arbeit.offen)
      : (arbeit.status_gesamt === "fertig" ? "keine offenen Vorschläge" : "");

    var bestaetigt = kachel.querySelector('[data-rolle="bestaetigt"]');
    bestaetigt.textContent = "";
    if (arbeit.bestaetigt_am || arbeit.status_gesamt === "fertig") {
      var marke = document.createElement("span");
      marke.className = arbeit.bestaetigt_am ? "status status-fertig" : "leise";
      marke.textContent = arbeit.bestaetigt_am ? "Korrektur bestätigt" : "Korrektur noch nicht bestätigt";
      bestaetigt.appendChild(marke);
      if (arbeit.bestaetigt_am) {  // nur bestätigte Arbeiten lassen sich ausgeben
        var pdf = document.createElement("a");
        pdf.className = "pdf-verweis";
        pdf.href = daten.url_pdf.replace("/0/", "/" + Number(arbeit.id) + "/");
        pdf.textContent = "PDF";
        pdf.setAttribute("aria-label", "PDF der Arbeit " + arbeit.kuerzel + " ausgeben");
        bestaetigt.appendChild(document.createTextNode(" "));
        bestaetigt.appendChild(pdf);
      }
    }

    var liste = kachel.querySelector('[data-rolle="fehler"]');
    liste.textContent = "";
    arbeit.seiten.forEach(function (seite) {
      if (seite.status !== "fehlgeschlagen" && seite.status !== "neu") { return; }
      var zeile = document.createElement("li");
      var text = document.createElement("span");
      text.textContent = "Seite " + seite.nummer + ": " + (seite.status === "neu"
        ? "Die Analyse wurde nicht gestartet."
        : (seite.fehlermeldung || "Analyse fehlgeschlagen"));
      var knopf = document.createElement("button");
      knopf.type = "button";
      knopf.className = "knopf klein";
      knopf.textContent = "Erneut versuchen";
      knopf.setAttribute("data-seite", seite.id);
      zeile.appendChild(text);
      zeile.appendChild(knopf);
      liste.appendChild(zeile);
    });
  }

  function standZeigen(stand) {
    var vorhanden = kacheln.querySelectorAll("[data-arbeit]");
    if (vorhanden.length !== stand.arbeiten.length) {
      window.location.reload();  // Arbeiten sind anderswo hinzugekommen
      return false;
    }
    stand.arbeiten.forEach(function (arbeit) {
      var kachel = kacheln.querySelector('[data-arbeit="' + Number(arbeit.id) + '"]');
      if (kachel) { kachelStellen(kachel, arbeit); }
    });
    var g = stand.gesamt;
    balken.max = g.seiten;
    balken.value = g.fertig;
    var teile = [g.fertig + " von " + g.seiten + " Seiten analysiert"];
    if (g.unterwegs) { teile.push(g.unterwegs + " in Arbeit"); }
    if (g.fehlgeschlagen) { teile.push(g.fehlgeschlagen + " fehlgeschlagen"); }
    if (g.offen) { teile.push(vorschlaege(g.offen)); }
    teile.push(g.bestaetigt + " von " + g.arbeiten + " Arbeiten bestätigt");
    gesamttext.textContent = teile.join(" · ");
    sammelKnopfStellen(g);
    return true;
  }

  // Das Sammel-PDF enthält nur bestätigte Arbeiten; ohne eine solche hat der Knopf kein Ziel.
  function sammelKnopfStellen(g) {
    var knopf = document.getElementById("sammel-knopf");
    if (!knopf) { return; }
    document.getElementById("sammel-zahl").textContent =
      g.bestaetigt + " von " + g.arbeiten + " bestätigt";
    if (g.bestaetigt > 0) {
      knopf.setAttribute("href", knopf.getAttribute("data-url"));
      knopf.removeAttribute("aria-disabled");
      knopf.removeAttribute("title");
    } else {
      knopf.removeAttribute("href");
      knopf.setAttribute("aria-disabled", "true");
      knopf.setAttribute("title", "Noch ist keine Korrektur bestätigt.");
    }
  }

  // Es läuft immer nur eine Abfrage: So kann keine ältere Antwort eine neuere überschreiben.
  function abfragen() {
    geplant = null;
    if (unterwegs) {
      nochmal = true;
      return;
    }
    unterwegs = true;
    fetch(daten.url_stand, { headers: { "Accept": "application/json" } })
      .then(function (antwort) {
        if (!antwort.ok) { throw new Error("Status " + antwort.status); }
        return antwort.json();
      })
      .then(function (stand) {
        unterwegs = false;
        fehlerZeigen("");
        if (standZeigen(stand) && (stand.aktiv || nochmal)) { weiter(); }  // sonst: aufhören
      })
      .catch(function () {
        unterwegs = false;
        fehlerZeigen("Der Stand der Analyse lässt sich gerade nicht abrufen. Läuft die App noch?");
        weiter();
      });
  }

  function weiter() {
    if (nochmal) {
      nochmal = false;
      abfragen();
    } else {
      planen();
    }
  }

  function planen() {
    if (geplant === null) { geplant = window.setTimeout(abfragen, ABSTAND_MS); }
  }

  if (kacheln) {
    kacheln.addEventListener("click", function (ereignis) {
      var knopf = ereignis.target.closest("button[data-seite]");
      if (!knopf) { return; }
      knopf.disabled = true;
      var url = daten.url_erneut.replace("/0/", "/" + Number(knopf.getAttribute("data-seite")) + "/");
      fetch(url, { method: "POST", headers: { "Accept": "application/json" } })
        .then(function (antwort) {
          // Ist die Antwort kein JSON (etwa eine Fehlerseite), gilt der feste Text.
          return antwort.json().catch(function () { return null; }).then(function (inhalt) {
            if (!antwort.ok || !inhalt || !inhalt.ok) {
              return (inhalt && typeof inhalt.fehler === "string" && inhalt.fehler) || ERNEUT_FEHLER;
            }
            return "";
          });
        }, function () { return ERNEUT_FEHLER; })  // App nicht erreichbar
        .then(function (meldung) {
          fehlerZeigen(meldung);
          if (meldung) {
            knopf.disabled = false;
            return;
          }
          if (geplant !== null) { window.clearTimeout(geplant); }
          abfragen();
        });
    });
    if (daten.aktiv) { planen(); }

    // Eine Ansicht, die geruht hat (aus dem Verlauf zurückgeholt oder wieder sichtbar
    // geworden), fragt den Stand einmal neu ab; läuft noch etwas, geht die Abfrage weiter.
    var sofortAbfragen = function () {
      if (geplant !== null) { window.clearTimeout(geplant); }
      abfragen();
    };
    window.addEventListener("pageshow", function (ereignis) {
      if (ereignis.persisted) { sofortAbfragen(); }
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") { sofortAbfragen(); }
    });
  }
})();
