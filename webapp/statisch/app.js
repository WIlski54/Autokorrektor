// Gemeinsames Verhalten aller Seiten.
(function () {
  "use strict";

  // Formulare mit data-nachfrage fragen vor dem Absenden nach.
  document.addEventListener("submit", function (ereignis) {
    var formular = ereignis.target;
    var frage = formular.getAttribute && formular.getAttribute("data-nachfrage");
    if (frage && !window.confirm(frage)) {
      ereignis.preventDefault();
    }
  });
})();
