/* feedback.js — respuesta visible al presionar botones, sin tocar el código de cada pantalla.
   Cargar al final de <body> en todas las pantallas. */
(function () {
  "use strict";
  var ultimo = null, ultimoT = 0;

  // 1) Al presionar cualquier botón se oscurece un instante (clase .pulsado).
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("button, .bt");
    if (!b || b.disabled) return;
    ultimo = b; ultimoT = Date.now();
    b.classList.add("pulsado");
    setTimeout(function () { b.classList.remove("pulsado"); }, 320);
  }, true);

  // 2) Si el clic dispara una petición al servidor (Refrescar, Actualizar, Guardar, Probar…),
  //    el botón queda "ocupado" (atenuado con círculo girando) hasta que la petición termina.
  var fetchOriginal = window.fetch;
  if (fetchOriginal) {
    window.fetch = function () {
      var btn = (ultimo && Date.now() - ultimoT < 400) ? ultimo : null;
      var p = fetchOriginal.apply(this, arguments);
      if (btn) {
        btn._pend = (btn._pend || 0) + 1;
        btn.classList.add("is-busy");
        var fin = function (ok) {
          btn._pend = Math.max(0, (btn._pend || 1) - 1);
          if (!btn._pend) {
            btn.classList.remove("is-busy");
            if (ok) { btn.classList.add("is-ok"); setTimeout(function () { btn.classList.remove("is-ok"); }, 900); }
          }
        };
        p.then(function (r) { fin(r && r.ok !== false); }, function () { fin(false); });
      }
      return p;
    };
  }

  // 3) API opcional para operaciones sin fetch: mkBusy(boton, promesa)
  window.mkBusy = function (btn, promesa) {
    btn.classList.add("is-busy");
    return Promise.resolve(promesa).finally(function () { btn.classList.remove("is-busy"); });
  };
})();
