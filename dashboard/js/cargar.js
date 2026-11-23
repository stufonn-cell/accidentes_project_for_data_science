/* Carga los datos del tablero y lo dibuja.
 * 1. GET /tablero de la API (ultima corrida del pipeline en AWS o en local).
 *    La pagina la sirve la misma API, asi que basta una ruta relativa;
 *    window.TABLERO_API permite apuntar a una API en otro dominio.
 * 2. Si no hay API (index.html abierto desde el disco o con http.server),
 *    usa la copia data/datos.js que genera scripts/exportar_tablero_runt.py. */
(function () {
  'use strict';
  const estado = document.getElementById('fuente');
  const avisar = (txt) => { if (estado) estado.textContent = txt; };
  const iniciar = (datos, origen) => {
    window.DATOS_RUNT = datos;
    document.documentElement.dataset.origenDatos = origen;
    avisar('');
    window.iniciarTablero(datos);
  };

  function copiaLocal() {
    const s = document.createElement('script');
    s.src = 'data/datos.js';
    s.onload = () => (window.DATOS_RUNT ? iniciar(window.DATOS_RUNT, 'copia') : avisar('Faltan los datos del tablero.'));
    s.onerror = () => avisar('No se pudieron cargar los datos del tablero: ni la API (/tablero) ni la copia data/datos.js responden.');
    document.head.appendChild(s);
  }

  avisar('Cargando datos…');
  if (location.protocol === 'file:') { copiaLocal(); return; }
  const base = (window.TABLERO_API || '').replace(/\/$/, '');
  fetch(base + '/tablero', { headers: { Accept: 'application/json' } })
    .then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then((datos) => iniciar(datos, 'api'))
    .catch(() => copiaLocal());
})();
