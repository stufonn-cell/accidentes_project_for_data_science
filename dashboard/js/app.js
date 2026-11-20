/* Estado, filtros y composición del tablero de accidentalidad. */
(function () {
  'use strict';
  const G = window.Graficos, C = G.C, n0 = G.n0;
  const D = window.DATOS_ACCIDENTES;
  const $ = (id) => document.getElementById(id);

  /* ---------- Conexión con la fuente ---------- */
  if (!D || !D.filas) {
    const f = $('fuente');
    f.classList.add('error');
    f.innerHTML = '<b>Sin conexión con gold</b>No se encontró <code>data/datos.js</code>.';
    $('t-resumen').textContent = 'No se pudieron cargar los datos. Ejecuta python scripts/exportar_dashboard.py desde la raíz del proyecto.';
    return;
  }

  const F = D.filas, N = F.anio.length, Y0 = D.meta.desde, Y1 = D.meta.hasta;
  const DIC = D.dic;
  const GRAV = { danos: 0, heridos: 1, muertos: 2 };
  const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
  const DIAS_C = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  const MESES_C = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const SEV = [
    { nombre: 'Solo daños', color: C.t200 },
    { nombre: 'Con heridos', color: C.t500 },
    { nombre: 'Con muertos', color: C.t900 },
  ];
  const FECHA_MAX = new Date(D.meta.fecha_max + 'T00:00:00');
  const ANIO_PARCIAL = FECHA_MAX.getMonth() < 11 || FECHA_MAX.getDate() < 31 ? FECHA_MAX.getFullYear() : null;

  const nf = G.nf, pct = (v, d = 0) => nf(d).format(v * 100) + ' %';
  const titulo = (t) => t.toLowerCase().replace(/(^|[\s(.-])(\p{L})/gu, (m, a, b) => a + b.toUpperCase());
  const frase = (t) => { const s = t.toLowerCase().replace(/\s+/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); };
  const causaTxt = (t) => (/^otra-conductor$/i.test(t) ? 'Otra causa del conductor' : frase(t.replace(/-/g, ' - ')));
  const claseTxt = (t) => frase(t).replace('Caida', 'Caída');

  /* ---------- Estado ---------- */
  const inicial = () => ({ desde: Y0, hasta: Y1, gravedad: 'todas', area: -1, clase: -1, barrio: -1, serie: 'anual', vista: 'envigado', modelo: null });
  let st = inicial();

  /* ---------- Utilidades DOM ---------- */
  function el(tag, cls, texto) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (texto !== undefined) n.textContent = texto;
    return n;
  }
  function segmentos(cont, opciones, actual, alElegir) {
    cont.textContent = '';
    opciones.forEach(([v, txt]) => {
      const b = el('button', null, txt);
      b.type = 'button';
      b.setAttribute('aria-pressed', String(v === actual));
      b.addEventListener('click', () => alElegir(v));
      cont.appendChild(b);
    });
  }
  function leyenda(id, items) {
    const c = $(id); c.textContent = '';
    items.forEach((it) => {
      const s = el('span'), i = el('i', it.linea ? 'linea' + (it.solida ? ' solida' : '') : '');
      if (it.linea) i.style.borderColor = it.color; else i.style.background = it.color;
      s.append(i, document.createTextNode(it.nombre)); c.appendChild(s);
    });
  }
  const ICONOS = {
    reloj: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.5 2"/></svg>',
    calendario: '<svg viewBox="0 0 24 24"><rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/></svg>',
    tendencia: '<svg viewBox="0 0 24 24"><path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/></svg>',
  };

  /* ---------- Filtrado y agregación en una sola pasada ---------- */
  function pasa(i) {
    const a = F.anio[i] + Y0;
    if (a < st.desde || a > st.hasta) return false;
    const g = F.gravedad[i];
    if (st.gravedad === 'victimas' && g === 0) return false;
    if (st.gravedad === 'danos' && g !== 0) return false;
    if (st.gravedad === 'muertos' && g !== 2) return false;
    if (st.area >= 0 && F.area[i] !== st.area) return false;
    if (st.clase >= 0 && F.clase[i] !== st.clase) return false;
    if (st.barrio >= 0 && F.barrio[i] !== st.barrio) return false;
    return true;
  }

  function agregar() {
    const nY = Y1 - Y0 + 1;
    const A = {
      total: 0, grav: [0, 0, 0], victimas: 0, noche: 0, finde: 0,
      anio: Array.from({ length: nY }, () => [0, 0, 0]),
      mes: new Array(nY * 12).fill(0), mesV: new Array(nY * 12).fill(0),
      matriz: Array.from({ length: 7 }, () => new Array(24).fill(0)),
      matrizV: Array.from({ length: 7 }, () => new Array(24).fill(0)),
      clase: DIC.clase.map(() => [0, 0]), causa: DIC.causa.map(() => [0, 0]),
      barrio: DIC.barrio.map(() => [0, 0]), mascara: new Uint8Array(N),
    };
    for (let i = 0; i < N; i++) {
      if (!pasa(i)) continue;
      A.mascara[i] = 1;
      const g = F.gravedad[i], v = g > 0 ? 1 : 0, y = F.anio[i], h = F.hora[i], d = F.dia[i];
      A.total++; A.grav[g]++; A.victimas += v;
      A.anio[y][g]++;
      A.mes[y * 12 + F.mes[i] - 1]++; A.mesV[y * 12 + F.mes[i] - 1] += v;
      A.matriz[d][h]++; A.matrizV[d][h] += v;
      A.clase[F.clase[i]][v ? 0 : 1]++;
      A.causa[F.causa[i]][v ? 0 : 1]++;
      A.barrio[F.barrio[i]][0]++; if (g === 2) A.barrio[F.barrio[i]][1]++;
      if (h >= 18 || h < 6) A.noche++;
      if (d >= 5) A.finde++;
    }
    A.puntos = D.puntos.filter((p) => A.mascara[p[0]]).map((p) => [p[1], p[2]]);
    return A;
  }

  /* Días calendario cubiertos por el rango de años (el último año puede estar incompleto). */
  function diasPeriodo() {
    const ini = new Date(Math.max(new Date(st.desde, 0, 1), new Date(D.meta.fecha_min + 'T00:00:00')));
    const fin = new Date(Math.min(new Date(st.hasta, 11, 31), FECHA_MAX));
    return Math.round((fin - ini) / 864e5) + 1;
  }
  const etiquetaAnio = (y) => (y === ANIO_PARCIAL ? `${y}*` : String(y));

  /* ---------- Controles ---------- */
  function montarControles() {
    const anios = [];
    for (let y = Y0; y <= Y1; y++) anios.push(y);
    ['f-desde', 'f-hasta'].forEach((id) => {
      const s = $(id);
      anios.forEach((y) => s.add(new Option(y, y)));
      s.addEventListener('change', () => {
        let a = +$('f-desde').value, b = +$('f-hasta').value;
        if (a > b) { if (id === 'f-desde') b = a; else a = b; }
        st.desde = a; st.hasta = b; render();
      });
    });
    const clase = $('f-clase');
    clase.add(new Option('Todas', -1));
    DIC.clase.forEach((c, i) => clase.add(new Option(claseTxt(c), i)));
    clase.addEventListener('change', () => { st.clase = +clase.value; render(); });

    const dl = $('barrios');
    DIC.barrio.forEach((b) => dl.appendChild(new Option(titulo(b))));
    const buscar = $('f-barrio');
    const aplicarBusqueda = () => {
      const q = buscar.value.trim().toUpperCase();
      if (!q) { if (st.barrio >= 0) { st.barrio = -1; render(); } return; }
      const i = DIC.barrio.findIndex((b) => b.toUpperCase() === q);
      if (i >= 0 && i !== st.barrio) { st.barrio = i; render(); }
    };
    buscar.addEventListener('change', aplicarBusqueda);
    buscar.addEventListener('input', () => { if (!buscar.value) aplicarBusqueda(); });

    $('btn-reset').addEventListener('click', () => { const v = st.vista, s = st.serie; st = inicial(); st.vista = v; st.serie = s; render(); });

    // Menú: marca la sección visible
    const enlaces = [...document.querySelectorAll('.menu a')];
    const obs = new IntersectionObserver((ents) => {
      ents.forEach((e) => {
        if (!e.isIntersecting) return;
        enlaces.forEach((a) => a.classList.toggle('activo', a.getAttribute('href') === '#' + e.target.id));
      });
    }, { rootMargin: '-35% 0px -60% 0px' });
    document.querySelectorAll('main .bloque').forEach((b) => obs.observe(b));
  }

  function pintarControles() {
    $('f-desde').value = st.desde; $('f-hasta').value = st.hasta; $('f-clase').value = st.clase;
    const q = $('f-barrio');
    if (st.barrio < 0 && document.activeElement !== q) q.value = '';
    if (st.barrio >= 0) q.value = titulo(DIC.barrio[st.barrio]);
    segmentos($('f-gravedad'), [['todas', 'Todas'], ['victimas', 'Con víctimas'], ['danos', 'Solo daños'], ['muertos', 'Con muertos']], st.gravedad, (v) => { st.gravedad = v; render(); });
    const urb = DIC.area.indexOf('URBANA'), rur = DIC.area.indexOf('RURAL');
    segmentos($('f-area'), [[-1, 'Todas'], [urb, 'Urbana'], [rur, 'Rural']], st.area, (v) => { st.area = v; render(); });

    // Chips de filtros activos en la barra superior
    const chips = $('chips'); chips.textContent = '';
    const chip = (txt, quitar) => {
      const b = el('button', 'chip'); b.type = 'button';
      b.setAttribute('aria-label', `Quitar filtro ${txt}`);
      b.append(document.createTextNode(txt), Object.assign(el('i'), { textContent: '×' }));
      b.addEventListener('click', () => { quitar(); render(); });
      chips.appendChild(b);
    };
    if (st.barrio >= 0) chip(titulo(DIC.barrio[st.barrio]), () => { st.barrio = -1; });
    if (st.clase >= 0) chip(claseTxt(DIC.clase[st.clase]), () => { st.clase = -1; });
    if (st.gravedad !== 'todas') chip({ victimas: 'Con víctimas', danos: 'Solo daños', muertos: 'Con muertos' }[st.gravedad], () => { st.gravedad = 'todas'; });
    if (st.area >= 0) chip(frase(DIC.area[st.area]), () => { st.area = -1; });
    $('periodo').textContent = st.desde === st.hasta ? etiquetaAnio(st.desde) : `${st.desde} – ${etiquetaAnio(st.hasta)}`;
  }

  /* ---------- Render ---------- */
  let mapa = null;
  function render() {
    pintarControles();
    const A = agregar();
    resumen(A);
    cuando(A);
    porque(A);
  }

  function descripcionFiltro() {
    const p = [];
    if (st.clase >= 0) p.push(`de tipo ${claseTxt(DIC.clase[st.clase]).toLowerCase()}`);
    if (st.area >= 0) p.push(`en zona ${DIC.area[st.area].toLowerCase()}`);
    if (st.barrio >= 0) p.push(`en ${titulo(DIC.barrio[st.barrio])}`);
    return p.length ? ' ' + p.join(' ') : '';
  }

  function resumen(A) {
    const per = st.desde === st.hasta ? `En ${st.desde}` : `Entre ${st.desde} y ${st.hasta}`;
    const sufijo = { todas: '', victimas: ' con víctimas', danos: ' con solo daños', muertos: ' con muertos' }[st.gravedad];
    $('t-resumen').textContent = A.total
      ? `${per} Envigado registró ${n0(A.total)} siniestros${sufijo}${descripcionFiltro()}` +
        (st.gravedad === 'todas' ? `; ${pct(A.victimas / A.total)} dejó heridos o muertos.` : '.')
      : `${per} no hay siniestros${sufijo}${descripcionFiltro()}.`;

    // Mapa
    if (!mapa) {
      mapa = G.crearMapa($('g-mapa'), D.geo);
      mapa.vista(st.vista);
    }
    const r = mapa.actualizar(A.puntos);
    const aniosGeo = D.meta.anios_con_coordenadas;
    $('sub-mapa').textContent = `${n0(r.total)} siniestros con coordenadas · disponibles solo ${aniosGeo[0]}–${aniosGeo[aniosGeo.length - 1]}`;
    segmentos($('f-vista'), [['valle', 'Valle de Aburrá'], ['envigado', 'Envigado']], st.vista, (v) => { st.vista = v; mapa.vista(v); pintarVista(); });
    const esc = $('escala-mapa');
    esc.innerHTML = '<span>Menos</span><span class="rampa"></span><span>Más siniestros</span>';
    esc.querySelector('.rampa').style.background = G.calorCss();

    // Cifras clave
    const k = $('kpis'); k.textContent = '';
    const anios = [], valores = [], victAnio = [];
    for (let y = st.desde; y <= st.hasta; y++) {
      const a = A.anio[y - Y0];
      anios.push(etiquetaAnio(y)); valores.push(a[0] + a[1] + a[2]); victAnio.push(a[1] + a[2]);
    }
    // Variación entre los dos últimos años completos del rango
    let insignia = null;
    const ultimo = ANIO_PARCIAL && st.hasta === ANIO_PARCIAL ? st.hasta - 1 : st.hasta;
    if (ultimo - 1 >= st.desde) {
      const t = (y) => A.anio[y - Y0].reduce((a, b) => a + b, 0);
      const a = t(ultimo - 1), b = t(ultimo);
      if (a > 0) insignia = { cambio: (b - a) / a, txt: `${ultimo} vs ${ultimo - 1}` };
    }
    const kpi = (cls, t, v, small, pie, extra) => {
      const d = el('div', 'kpi ' + cls);
      const c = el('div', 'kpi-c'); c.appendChild(el('div', 'kpi-t', t));
      if (extra && extra.insignia) c.appendChild(extra.insignia);
      d.appendChild(c);
      const vv = el('div', 'kpi-v', v); if (small) vv.appendChild(el('small', null, small)); d.appendChild(vv);
      if (pie) d.appendChild(el('div', 'kpi-pie', pie));
      if (extra && extra.spark) d.appendChild(extra.spark);
      return d;
    };
    const ins = insignia ? el('span', 'insignia ' + (insignia.cambio >= 0 ? 'sube' : 'baja'), pct(Math.abs(insignia.cambio))) : null;
    if (ins) ins.title = insignia.txt;
    k.appendChild(kpi('n1', 'Siniestros', n0(A.total), null,
      insignia ? `${insignia.cambio >= 0 ? 'Aumento' : 'Caída'} ${insignia.txt}` : `${st.desde === st.hasta ? 'Un año' : anios.length + ' años'} en el filtro`,
      { insignia: ins, spark: G.sparkline(valores, '#ffffff', anios) }));
    k.appendChild(kpi('n2', 'Con víctimas', n0(A.victimas), A.total ? pct(A.victimas / A.total) : '',
      'Siniestros con heridos o muertos', { spark: G.sparkline(victAnio, C.t500, anios) }));
    const fila = el('div', 'kpi-fila');
    fila.appendChild(kpi('n3', 'Con heridos', n0(A.grav[1])));
    fila.appendChild(kpi('n4', 'Con muertos', n0(A.grav[2])));
    k.appendChild(fila);
    k.appendChild(kpi('n5', 'Promedio diario', nf(1).format(A.total / diasPeriodo()), 'siniestros / día', ANIO_PARCIAL && st.hasta === ANIO_PARCIAL ? `* ${ANIO_PARCIAL} con datos hasta ${FECHA_MAX.getDate()} de ${MESES_C[FECHA_MAX.getMonth()]}` : null));
  }
  function pintarVista() {
    segmentos($('f-vista'), [['valle', 'Valle de Aburrá'], ['envigado', 'Envigado']], st.vista, (v) => { st.vista = v; mapa.vista(v); pintarVista(); });
  }

  function cuando(A) {
    // Serie temporal
    segmentos($('f-serie'), [['anual', 'Anual'], ['mensual', 'Mensual']], st.serie, (v) => { st.serie = v; cuando(A); });
    const anios = [];
    for (let y = st.desde; y <= st.hasta; y++) anios.push(y);
    if (st.serie === 'anual') {
      $('t-serie').textContent = 'Siniestros por año y gravedad';
      $('sub-serie').textContent = ANIO_PARCIAL && st.hasta === ANIO_PARCIAL ? `* ${ANIO_PARCIAL} incompleto (datos hasta ${D.meta.fecha_max})` : 'Barras apiladas por la gravedad más alta del siniestro';
      leyenda('ley-serie', SEV.map((s) => ({ nombre: s.nombre, color: s.color })).concat([{ nombre: 'Promedio anual', color: C.ambar, linea: true }]));
      const completos = anios.filter((y) => y !== ANIO_PARCIAL);
      const tot = (y) => A.anio[y - Y0].reduce((a, b) => a + b, 0);
      G.columnas($('g-serie'), {
        descripcion: 'Siniestros por año, apilados por gravedad',
        cats: anios.map(etiquetaAnio),
        series: SEV.map((s, g) => ({ ...s, valores: anios.map((y) => A.anio[y - Y0][g]) })),
        promedio: completos.length ? completos.reduce((a, y) => a + tot(y), 0) / completos.length : 0,
      });
    } else {
      $('t-serie').textContent = 'Siniestros por mes';
      $('sub-serie').textContent = 'Total mensual y siniestros con víctimas';
      leyenda('ley-serie', [{ nombre: 'Siniestros', color: C.t600, linea: true, solida: true }, { nombre: 'Con víctimas', color: C.t300, linea: true, solida: true }, { nombre: 'Promedio mensual', color: C.ambar, linea: true }]);
      const idx = [];
      anios.forEach((y) => { for (let m = 0; m < 12; m++) { const fecha = new Date(y, m, 1); if (fecha <= FECHA_MAX) idx.push((y - Y0) * 12 + m); } });
      const total = idx.map((i, k) => [k, A.mes[i]]), vict = idx.map((i, k) => [k, A.mesV[i]]);
      const paso = Math.max(1, Math.ceil(anios.length / 7));
      G.lineas($('g-serie'), {
        descripcion: 'Siniestros por mes',
        series: [{ nombre: 'Siniestros', color: C.t600, puntos: total, area: true }, { nombre: 'Con víctimas', color: C.t300, puntos: vict }],
        xTicks: idx.map((i, k) => [k, i]).filter(([, i]) => i % 12 === 0 && (Math.floor(i / 12) - (st.desde - Y0)) % paso === 0).map(([k, i]) => [k, String(Y0 + i / 12)]),
        promedio: idx.length ? total.reduce((a, p) => a + p[1], 0) / idx.length : 0,
        tituloPunto: (k) => { const i = idx[k]; return `${MESES_C[i % 12]} ${Y0 + Math.floor(i / 12)}`; },
      });
    }

    // Día × hora
    const max = G.matriz($('g-matriz'), {
      descripcion: 'Siniestros por día de la semana y hora',
      filas: DIAS_C, filasLargas: DIAS, columnas: [...Array(24).keys()].map((h) => `${h}h`),
      columnasLargas: [...Array(24).keys()].map((h) => `${h}:00–${h}:59`), valores: A.matriz, victimas: A.matrizV,
    });
    const esc = $('escala-matriz');
    esc.innerHTML = '<span>0</span><span class="rampa"></span><span></span><span style="margin-left:auto">▢ Celda pico</span>';
    esc.querySelector('.rampa').style.background = G.rampaCss();
    esc.children[2].textContent = n0(max || 0);
    esc.children[3].style.color = C.ambar;

    // Hallazgos
    const porHora = new Array(24).fill(0), porDia = new Array(7).fill(0);
    A.matriz.forEach((f, d) => f.forEach((v, h) => { porHora[h] += v; porDia[d] += v; }));
    const hPico = porHora.indexOf(Math.max(...porHora)), dPico = porDia.indexOf(Math.max(...porDia));
    const totAnio = anios.map((y) => [y, A.anio[y - Y0].reduce((a, b) => a + b, 0)]);
    const yPico = totAnio.reduce((a, b) => (b[1] > a[1] ? b : a), [anios[0], -1]);
    const media = A.total / 7;
    $('t-cuando').textContent = A.total
      ? `La hora más crítica es de ${hPico}:00 a ${hPico + 1}:00 y el ${DIAS[dPico].toLowerCase()} concentra más siniestros que cualquier otro día.`
      : 'Sin siniestros para estos filtros.';
    const tar = $('tar-cuando'); tar.textContent = '';
    [
      { ico: ICONOS.reloj, t: 'Hora pico', v: A.total ? `${hPico}:00 – ${hPico + 1}:00` : '—', p: A.total ? `${n0(porHora[hPico])} siniestros · ${pct(porHora[hPico] / A.total, 1)} del total` : '', oscura: true },
      { ico: ICONOS.calendario, t: 'Día más crítico', v: A.total ? DIAS[dPico] : '—', p: A.total ? `${n0(porDia[dPico])} siniestros · ${pct(porDia[dPico] / media - 1)} por encima del día promedio` : '' },
      { ico: ICONOS.tendencia, t: 'Año con más siniestros', v: A.total ? etiquetaAnio(yPico[0]) : '—', p: A.total ? `${n0(yPico[1])} siniestros` : '' },
    ].forEach((c) => {
      const d = el('div', 'tarjeta' + (c.oscura ? ' oscura' : ''));
      const ico = el('div', 'ico'); ico.innerHTML = c.ico;
      const tx = el('div');
      tx.append(el('div', 'tarjeta-t', c.t), el('div', 'tarjeta-v', c.v), el('p', null, c.p));
      d.append(ico, tx); tar.appendChild(d);
    });
  }

  function porque(A) {
    const colores = [C.t600, C.t200], series = ['Con víctimas', 'Solo daños'];
    leyenda('ley-clase', series.map((n, k) => ({ nombre: n, color: colores[k] })));
    leyenda('ley-causa', series.map((n, k) => ({ nombre: n, color: colores[k] })));
    const items = (arr, txt) => arr.map((v, i) => ({ clave: i, nombre: txt(DIC[arr === A.clase ? 'clase' : 'causa'][i]), valores: v, tot: v[0] + v[1] }))
      .filter((d) => d.tot > 0).sort((a, b) => b.tot - a.tot);
    const extra = (d) => `${pct(d.valores[0] / (d.tot || 1))} víct.`;
    const clases = items(A.clase, claseTxt);
    G.barrasH($('g-clase'), {
      descripcion: 'Siniestros por clase de accidente', items: clases, colores, series, extra, activo: st.clase >= 0 ? st.clase : null,
      onClic: (c) => { st.clase = st.clase === c ? -1 : c; render(); },
    });
    const causas = items(A.causa, causaTxt).slice(0, 8);
    G.barrasH($('g-causa'), { descripcion: 'Causas más frecuentes', items: causas, colores, series, extra });

    // Titular
    const at = DIC.clase.indexOf('ATROPELLO'), atv = A.clase[at] || [0, 0];
    $('t-porque').textContent = A.total && clases.length
      ? `${clases[0].nombre} explica el ${pct(clases[0].tot / A.total)} de los siniestros` +
        (atv[0] + atv[1] > 0 && st.clase < 0 ? `, pero los atropellos son los más graves: ${pct(atv[0] / (atv[0] + atv[1]))} deja víctimas.` : '.')
      : 'Sin siniestros para estos filtros.';

    // Anillos
    const an = $('anillos'); an.textContent = '';
    [
      { v: A.victimas, t: 'Dejan víctimas', s: 'heridos o muertos', c: C.t600 },
      { v: A.noche, t: 'De noche', s: 'entre 6 p. m. y 6 a. m.', c: C.t500 },
      { v: A.finde, t: 'En fin de semana', s: 'sábado o domingo', c: C.t400 },
    ].forEach((r) => {
      const d = el('div', 'anillo');
      d.appendChild(G.anillo(A.total ? r.v / A.total : 0, r.c));
      d.append(el('strong', null, r.t), el('span', null, `${n0(r.v)} · ${r.s}`));
      an.appendChild(d);
    });

    // Rankings de barrios
    const rk = $('rankings'); rk.textContent = '';
    const lista = (tituloL, k, unidad) => {
      const box = el('div'); box.appendChild(el('h3', null, tituloL));
      const ol = el('ol');
      const top = A.barrio.map((v, i) => ({ i, v: v[k] })).filter((d) => d.v > 0).sort((a, b) => b.v - a.v).slice(0, 5);
      const max = top.length ? top[0].v : 1;
      if (!top.length) ol.appendChild(el('li', null, 'Sin datos'));
      top.forEach((d) => {
        const li = el('li'), b = el('button'); b.type = 'button';
        b.setAttribute('aria-pressed', String(st.barrio === d.i));
        b.title = `${titulo(DIC.barrio[d.i])}: ${n0(d.v)} ${unidad}`;
        const mini = el('span', 'mini'), bar = el('i'); bar.style.width = (d.v / max) * 100 + '%'; mini.appendChild(bar);
        b.append(el('span', 'nom', titulo(DIC.barrio[d.i])), el('span', 'val', n0(d.v)), mini);
        b.addEventListener('click', () => { st.barrio = st.barrio === d.i ? -1 : d.i; render(); });
        li.appendChild(b); ol.appendChild(li);
      });
      box.appendChild(ol); rk.appendChild(box);
    };
    lista('Más siniestros', 0, 'siniestros');
    lista('Más siniestros con muertos', 1, 'con muertos');
  }

  /* ---------- Modelo (no depende de los filtros) ---------- */
  const NOMBRES_MODELO = { regresion_logistica: 'Regresión logística', gradient_boosting: 'Gradient boosting' };
  function modelo() {
    const M = D.modelo, mets = M.metricas;
    if (st.modelo === null) st.modelo = Math.max(0, mets.findIndex((m) => m.es_mejor === 1));
    const mejor = mets.find((m) => m.es_mejor === 1) || mets[0];
    const ap = mejor.average_precision, prev = mejor.prevalencia_prueba;
    $('t-modelo').textContent = `${NOMBRES_MODELO[mejor.modelo] || mejor.modelo} anticipa qué siniestros dejan víctimas con un ROC AUC de ${nf(3).format(mejor.roc_auc)} y una precisión promedio ${nf(1).format(ap / prev)} veces la línea base.`;
    const anios = M.anios_prueba;
    $('anios-prueba').textContent = `${anios[0]}–${anios[anios.length - 1]}`;

    const cont = $('modelos'); cont.textContent = '';
    mets.forEach((m, k) => {
      const b = el('button', 'escenario' + (m.es_mejor === 1 ? ' mejor' : '')); b.type = 'button';
      b.setAttribute('aria-pressed', String(st.modelo === k));
      const n = el('div', 'esc-n', NOMBRES_MODELO[m.modelo] || m.modelo);
      if (m.es_mejor === 1) n.appendChild(el('em', null, 'Modelo principal'));
      const v = el('div', 'esc-v', nf(3).format(m.roc_auc)); v.appendChild(el('small', null, 'ROC AUC'));
      b.append(n, v);
      [['Precisión promedio', m.average_precision], ['Precisión', m.precision], ['Sensibilidad (recall)', m.recall]].forEach(([t, val]) => {
        const l = el('div', 'esc-l'); l.append(el('span', null, t), el('b', null, nf(3).format(val)));
        const bar = el('div', 'barra-m'), i = el('i'); i.style.width = val * 100 + '%'; bar.appendChild(i);
        b.append(l, bar);
      });
      const l = el('div', 'esc-l'); l.append(el('span', null, 'Brier (menor es mejor)'), el('b', null, nf(3).format(m.brier))); b.appendChild(l);
      b.addEventListener('click', () => { st.modelo = k; modelo(); });
      cont.appendChild(b);
    });

    // Matriz de confusión del modelo elegido
    const m = mets[st.modelo];
    $('t-confusion').textContent = `Matriz de confusión · ${NOMBRES_MODELO[m.modelo] || m.modelo}`;
    const cf = $('g-confusion'); cf.textContent = '';
    const celdas = [[m.verdaderos_negativos, m.falsos_positivos], [m.falsos_negativos, m.verdaderos_positivos]];
    const max = Math.max(...celdas.flat());
    const nombres = [['Verdaderos negativos', 'Falsos positivos'], ['Falsos negativos', 'Verdaderos positivos']];
    cf.append(el('div', 'eje esquina'), el('div', 'eje', 'Predice: sin víctimas'), el('div', 'eje', 'Predice: con víctimas'));
    ['Real: sin víctimas', 'Real: con víctimas'].forEach((r, i) => {
      cf.appendChild(el('div', 'eje', r));
      const filaTot = celdas[i][0] + celdas[i][1];
      celdas[i].forEach((v, j) => {
        const c = el('div', 'celda'), t = v / max;
        c.style.background = G.rampa(0.08 + 0.8 * t);
        c.style.color = t > 0.45 ? '#fff' : C.texto;
        c.append(el('b', null, n0(v)), el('span', null, `${nombres[i][j]} · ${pct(v / filaTot)} de la fila`));
        cf.appendChild(c);
      });
    });

    // Calibración
    leyenda('ley-calib', [{ nombre: 'Proporción observada', color: C.t600, linea: true, solida: true }, { nombre: 'Calibración perfecta', color: C.texto3, linea: true }]);
    const cal = M.calibracion;
    G.lineas($('g-calib'), {
      descripcion: 'Calibración del modelo por decil de probabilidad', alto: 280,
      series: [{ nombre: 'Observada', color: C.t600, puntos: cal.map((d) => [d.predicha, d.observada]), marcadores: true }],
      xmin: 0, xmax: 1, ymin: 0, ymax: 1, diagonal: true,
      xTicks: [0, 0.25, 0.5, 0.75, 1].map((v) => [v, pct(v)]), yFmt: (v) => pct(v), tipFmt: (v) => pct(v, 1),
      tituloPunto: (k) => `Decil ${k + 1} · predicha ${pct(cal[k].predicha, 1)} · ${n0(cal[k].n)} siniestros`,
    });

    // Tabla
    const filas = [['ROC AUC', 'roc_auc', 3], ['Precisión promedio', 'average_precision', 3], ['Brier', 'brier', 3], ['Precisión', 'precision', 3], ['Sensibilidad', 'recall', 3],
      ['Verdaderos positivos', 'verdaderos_positivos', 0], ['Falsos positivos', 'falsos_positivos', 0], ['Falsos negativos', 'falsos_negativos', 0], ['Verdaderos negativos', 'verdaderos_negativos', 0],
      ['Filas de entrenamiento', 'filas_entrenamiento', 0], ['Filas de prueba', 'filas_prueba', 0], ['Prevalencia en prueba', 'prevalencia_prueba', 3]];
    const tb = $('tabla');
    tb.innerHTML = '<thead><tr><th>Métrica</th>' + mets.map((x) => `<th>${NOMBRES_MODELO[x.modelo] || x.modelo}</th>`).join('') + '</tr></thead><tbody>' +
      filas.map(([t, c, d]) => `<tr><th>${t}</th>${mets.map((x) => `<td>${nf(d).format(x[c])}</td>`).join('')}</tr>`).join('') + '</tbody>';
  }

  function notas() {
    const m = D.meta;
    $('notas').innerHTML = [
      `Fuente: Accidentalidad Municipio de Envigado, datos abiertos de la Alcaldía de Envigado (datos.gov.co), del ${m.fecha_min} al ${m.fecha_max}. Cada siniestro aparece una vez con la gravedad más alta reportada (tabla gold <code>siniestros</code>).`,
      `Conexión: la página lee <code>dashboard/data/datos.js</code>, generado el ${m.generado} desde <code>${m.fuente}</code> con <code>python scripts/exportar_dashboard.py</code>. Antes de escribirlo, el script comprueba que los conteos coincidan con los agregados gold (${m.validado_con.join(', ')}). Con <code>DATA_DIR=s3://…</code> lee la misma capa gold del bucket.`,
      `Mapa: el CSV solo trae coordenadas de ${m.anios_con_coordenadas[0]} a ${m.anios_con_coordenadas[m.anios_con_coordenadas.length - 1]} (${n0(m.con_coordenadas)} siniestros), así que el mapa de calor muestra ese subconjunto aunque el filtro de años sea más amplio. Los límites municipales del Valle de Aburrá están simplificados y sirven como referencia visual.`,
      `Modelo: se entrena con 2010–2019 y se evalúa con ${D.modelo.anios_prueba[0]}–${D.modelo.anios_prueba[D.modelo.anios_prueba.length - 1]}; sus métricas no cambian con los filtros. La calibración usa las predicciones del modelo principal (tabla gold <code>predicciones</code>).`,
    ].map((p) => `<p>${p}</p>`).join('');
    const f = $('fuente');
    f.innerHTML = `<b>Capa gold conectada</b>${n0(m.siniestros)} siniestros · ${m.desde}–${m.hasta}<br>Exportado ${m.generado} · validado con ${m.validado_con.length} agregados`;
  }

  /* ---------- Inicio ---------- */
  montarControles();
  notas();
  render();
  modelo();
  let espera;
  addEventListener('resize', () => {
    clearTimeout(espera);
    espera = setTimeout(() => { render(); modelo(); if (mapa) mapa.relabel(); }, 150);
  });
})();
