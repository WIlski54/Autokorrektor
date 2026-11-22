// Arbeit ansehen: Rahmen der Vorschläge über dem Foto, gegenseitiges Hervorheben, Zoom.
// Die Rahmen stehen in Prozent der Bildgröße; Fenstergröße und Zoom brauchen keine Umrechnung.
(function () {
  "use strict";

  var daten = JSON.parse(document.getElementById("arbeit-daten").textContent);
  var ebene = document.getElementById("rahmenebene");
  var buehne = document.getElementById("buehne");
  var rollfeld = document.getElementById("rollfeld");
  var liste = document.getElementById("zeichenliste");
  var anzeige = document.getElementById("zoom-anzeige");
  var FARBKLASSEN = { R: "kat-R", Z: "kat-Z", Gr: "kat-Gr" };
  var rahmen = {};      // id -> Element über dem Bild
  var eintraege = {};   // id -> Knopf in der Liste
  var gewaehlt = null;
  var zoom = 100;

  function prozent(wert, gesamt) {
    return (100 * wert / gesamt) + "%";
  }

  function rahmenBauen(zeichen) {
    var seite = daten.seite;
    var e = document.createElement("button");
    e.type = "button";
    e.className = "rahmen " + (FARBKLASSEN[zeichen.kategorie] || "kat-sonst") +
      (zeichen.typ === "luecke" ? " luecke" : "") +
      (zeichen.status === "offen" ? " offen" : " fest");
    e.style.left = prozent(zeichen.x, seite.breite);
    e.style.top = prozent(zeichen.y, seite.hoehe);
    e.style.width = prozent(zeichen.breite, seite.breite);
    e.style.height = prozent(zeichen.hoehe, seite.hoehe);
    e.setAttribute("aria-label", "Vorschlag " + zeichen.kategorie + ": " +
      (zeichen.gelesen || "") + (zeichen.vorschlag ? " → " + zeichen.vorschlag : ""));
    var etikett = document.createElement("span");
    etikett.className = "etikett" + (zeichen.y / seite.hoehe < 0.04 ? " unten" : "");
    etikett.textContent = zeichen.kategorie;
    e.appendChild(etikett);
    e.addEventListener("click", function (ereignis) {
      ereignis.stopPropagation();
      waehlen(zeichen.id, "bild");
    });
    e.addEventListener("mouseenter", function () { nah(zeichen.id, true); });
    e.addEventListener("mouseleave", function () { nah(zeichen.id, false); });
    return e;
  }

  function nah(id, an) {
    if (rahmen[id]) { rahmen[id].classList.toggle("nah", an); }
    if (eintraege[id]) { eintraege[id].classList.toggle("nah", an); }
  }

  // Hebt dasselbe Zeichen im Bild und in der Liste hervor.
  function waehlen(id, quelle) {
    if (gewaehlt !== null) {
      if (rahmen[gewaehlt]) { rahmen[gewaehlt].classList.remove("gewaehlt"); }
      if (eintraege[gewaehlt]) {
        eintraege[gewaehlt].classList.remove("gewaehlt");
        eintraege[gewaehlt].removeAttribute("aria-current");
      }
    }
    gewaehlt = id;
    if (id === null) { return; }
    if (rahmen[id]) {
      rahmen[id].classList.add("gewaehlt");
      if (quelle !== "bild") { rahmen[id].scrollIntoView({ block: "center", inline: "center" }); }
    }
    if (eintraege[id]) {
      eintraege[id].classList.add("gewaehlt");
      eintraege[id].setAttribute("aria-current", "true");
      if (quelle !== "liste") { eintraege[id].scrollIntoView({ block: "nearest" }); }
    }
  }

  daten.zeichen.forEach(function (zeichen) {
    var e = rahmenBauen(zeichen);
    rahmen[zeichen.id] = e;
    ebene.appendChild(e);
  });

  if (liste) {
    Array.prototype.forEach.call(liste.querySelectorAll("[data-zeichen]"), function (knopf) {
      var id = Number(knopf.getAttribute("data-zeichen"));
      eintraege[id] = knopf;
      knopf.addEventListener("click", function () { waehlen(id, "liste"); });
      knopf.addEventListener("mouseenter", function () { nah(id, true); });
      knopf.addEventListener("mouseleave", function () { nah(id, false); });
    });
  }

  ebene.addEventListener("click", function () { waehlen(null); });

  // --- Zoom: die Bühne wird breiter als das Rollfeld, die Prozentwerte wachsen mit ---

  function zoomStellen(wert) {
    zoom = Math.max(100, Math.min(400, Math.round(wert)));
    buehne.style.width = zoom + "%";
    anzeige.textContent = zoom + " %";
  }

  document.getElementById("zoom-groesser").addEventListener("click", function () {
    zoomStellen(zoom * 1.25);
  });
  document.getElementById("zoom-kleiner").addEventListener("click", function () {
    zoomStellen(zoom / 1.25);
  });
  document.getElementById("zoom-einpassen").addEventListener("click", function () {
    zoomStellen(100);
    rollfeld.scrollTo(0, 0);
  });

  // --- Tastatur ---

  document.addEventListener("keydown", function (ereignis) {
    if (ereignis.altKey || ereignis.ctrlKey || ereignis.metaKey || ereignis.shiftKey) { return; }
    var ziel = null;
    if (ereignis.key === "ArrowLeft") { ziel = document.getElementById("seite-zurueck"); }
    if (ereignis.key === "ArrowRight") { ziel = document.getElementById("seite-weiter"); }
    if (ereignis.key === "Escape") { waehlen(null); }
    if (ziel) {
      ereignis.preventDefault();
      window.location.href = ziel.href;
    }
  });
})();
