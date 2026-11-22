// Stapelansicht: fragt den Stand ab, solange etwas wartet oder läuft, und zieht die Kacheln nach.
(function () {
  "use strict";

  var daten = JSON.parse(document.getElementById("stapel-daten").textContent);
  var kacheln = document.getElementById("kacheln");
  var balken = document.getElementById("gesamtbalken");
  var gesamttext = document.getElementById("gesamttext");
  var fehlerfeld = document.getElementById("stapelfehler");
  var ABSTAND_MS = 2000;
  var geplant = null;

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

    var liste = kachel.querySelector('[data-rolle="fehler"]');
    liste.textContent = "";
    arbeit.seiten.forEach(function (seite) {
      if (seite.status !== "fehlgeschlagen") { return; }
      var zeile = document.createElement("li");
      var text = document.createElement("span");
      text.textContent = "Seite " + seite.nummer + ": " +
        (seite.fehlermeldung || "Analyse fehlgeschlagen");
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
    gesamttext.textContent = teile.join(" · ");
    return true;
  }

  function abfragen() {
    geplant = null;
    fetch(daten.url_stand, { headers: { "Accept": "application/json" } })
      .then(function (antwort) {
        if (!antwort.ok) { throw new Error("Status " + antwort.status); }
        return antwort.json();
      })
      .then(function (stand) {
        fehlerZeigen("");
        if (standZeigen(stand) && stand.aktiv) { planen(); }  // sonst: aufhören
      })
      .catch(function () {
        fehlerZeigen("Der Stand der Analyse lässt sich gerade nicht abrufen. Läuft die App noch?");
        planen();
      });
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
          return antwort.json().then(function (inhalt) {
            if (!antwort.ok) { throw new Error(inhalt.fehler || "Das hat nicht geklappt."); }
          });
        })
        .then(function () {
          fehlerZeigen("");
          if (geplant !== null) { window.clearTimeout(geplant); }
          abfragen();
        })
        .catch(function (fehler) {
          knopf.disabled = false;
          fehlerZeigen(fehler.message);
        });
    });
    if (daten.aktiv) { planen(); }
  }
})();
