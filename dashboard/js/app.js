/* Tablero para secretarias de movilidad y autoridades de transito: gravedad de
 * los siniestros viales en Colombia (RUNT, Ley 2251 de 2022).
 * Orden de lectura = orden de la exposicion. Solo la seccion 4 responde a los filtros.
 * Toda cifra que aparece en pantalla se calcula aqui a partir de los datos que
 * entrega js/cargar.js: GET /tablero de la API, o data/datos.js sin API. */
window.iniciarTablero = function (D) {
  'use strict';
  const G = window.Graficos, C = G.C, n0 = G.n0, nf = G.nf, pct = G.pct;
  const $ = (id) => document.getElementById(id);

  const M = D.dic.meses, DEP = D.dic.departamentos, TIP = D.dic.tipos, CLA = D.dic.clases, EDA = D.dic.edades;
  const CUBO = D.cubo; // [mes, depto, tipo, edad, vehiculos, con muertos], sin los meses con reporte incompleto o atrasado
  const ANIOS = [...new Set(M.map((m) => +m.slice(0, 4)))];
  const MES_TXT = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const MES_LARGO = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const ultimo = M[M.length - 1], ANIO_PARCIAL = +ultimo.slice(5) < 12 ? +ultimo.slice(0, 4) : null;
  const mesTxt = (m) => `${MES_TXT[+m.slice(5) - 1]} ${m.slice(0, 4)}`;
  const mesLargo = (m) => `${MES_LARGO[+m.slice(5) - 1]} de ${m.slice(0, 4)}`;
  const mayus = (x) => x.charAt(0).toUpperCase() + x.slice(1);
  const titulo = (s) => s.toLowerCase().replace(/(^|[\s(.-])(\p{L})/gu, (x, a, b) => a + b.toUpperCase());
  const DEP_TXT = { 'BOGOTA D.C.': 'Bogotá D.C.', NARINO: 'Nariño', BOLIVAR: 'Bolívar', CORDOBA: 'Córdoba', CAQUETA: 'Caquetá', BOYACA: 'Boyacá', ATLANTICO: 'Atlántico', QUINDIO: 'Quindío', GUAINIA: 'Guainía', 'SAN ANDRES': 'San Andrés', CHOCO: 'Chocó', VAUPES: 'Vaupés', 'VALLE DEL CAUCA': 'Valle del Cauca', 'NORTE DE SANTANDER': 'Norte de Santander', 'LA GUAJIRA': 'La Guajira' };
  const depto = (s) => DEP_TXT[s] || titulo(s);
  const TIPO_TXT = { MOTOCICLETA: 'Motocicleta', AUTOMOVIL: 'Automóvil', CAMIONETA: 'Camioneta', BUS: 'Bus', CAMION: 'Camión', CAMPERO: 'Campero', TRACTOCAMION: 'Tractocamión', MICROBUS: 'Microbús', BUSETA: 'Buseta', VOLQUETA: 'Volqueta', MOTOCARRO: 'Motocarro', OTROS: 'Otros' };
  const tipoTxt = (t) => TIPO_TXT[t] || titulo(t);
  /* Nombre en dos lineas para las columnas del mapa de calor, si no cabe en una */
  const PARTIDO = { Motocicleta: ['Moto-', 'cicleta'], 'Automóvil': ['Auto-', 'móvil'], Camioneta: ['Camio-', 'neta'], 'Tractocamión': ['Tracto-', 'camión'], 'Microbús': ['Micro-', 'bús'], Volqueta: ['Vol-', 'queta'], Motocarro: ['Moto-', 'carro'], Campero: ['Cam-', 'pero'], Buseta: ['Bu-', 'seta'] };
  const PLURAL = { MOTOCICLETA: 'motos', AUTOMOVIL: 'automóviles', CAMIONETA: 'camionetas', BUS: 'buses', CAMION: 'camiones', CAMPERO: 'camperos', TRACTOCAMION: 'tractocamiones', MICROBUS: 'microbuses', BUSETA: 'busetas', VOLQUETA: 'volquetas', MOTOCARRO: 'motocarros', OTROS: 'otros vehículos' };
  const plural = (cod) => PLURAL[cod] || tipoTxt(cod).toLowerCase();
  /* "De cada 100": un decimal por debajo de 10, sin decimales por encima */
  const de100 = (p) => nf(p * 100 < 10 ? 1 : 0).format(p * 100);
  const MODELO_TXT = { prevalencia: 'Sin modelo (al azar)', regresion_logistica: 'Regresión logística', gradient_boosting: 'Gradient boosting', bosque_aleatorio: 'Random forest' };
  const TILDES = { Medellin: 'Medellín', Bogota: 'Bogotá', Ibague: 'Ibagué', Cucuta: 'Cúcuta', Monteria: 'Montería', Itagui: 'Itagüí', Popayan: 'Popayán', Quibdo: 'Quibdó', Facatativa: 'Facatativá', Zipaquira: 'Zipaquirá', Chia: 'Chía', Fusagasuga: 'Fusagasugá', Jamundi: 'Jamundí', Tulua: 'Tuluá' };
  const muni = (s) => { const x = titulo(s.replace(/ \(.*\)$/, '')); return TILDES[x] || x; };
  const enLista = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(', ')} y ${xs[xs.length - 1]}` : xs.join(''));
  const el = (tag, cls, txt) => { const n = document.createElement(tag); if (cls) n.className = cls; if (txt !== undefined) n.textContent = txt; return n; };
  const anioDe = (i) => +M[i].slice(0, 4);
  const sum = (xs) => xs.reduce((a, b) => a + b, 0);
  /* Ultimo anio completo y el anterior: la comparacion de la seccion 2 */
  const A2 = (ANIO_PARCIAL || ANIOS[ANIOS.length - 1] + 1) - 1, A1 = A2 - 1;
  /* Tonos de la comparacion antes / despues: lo que importa en amarillo, el contexto en gris; tenue = antes */
  const TONO = { focoAntes: '#f9d877', focoDespues: C.acento, contextoAntes: '#dcdee1', contextoDespues: '#aeb2b8' };
  const GEO = window.GEO_COLOMBIA, CIU = D.ciudades;

  const inicial = () => ({ desde: ANIOS[0], hasta: ANIOS[ANIOS.length - 1], depto: -1, tipo: -1 });
  let st = inicial();

  /* Suma [vehiculos, con muertos] por una clave, con los filtros que se indiquen */
  function sumar(clave, n, usar) {
    const out = Array.from({ length: n }, () => [0, 0]);
    for (const [m, d, t, e, r, k] of CUBO) {
      const a = anioDe(m);
      if (usar.periodo && (a < st.desde || a > st.hasta)) continue;
      if (usar.depto && st.depto >= 0 && d !== st.depto) continue;
      if (usar.tipo && st.tipo >= 0 && t !== st.tipo) continue;
      const i = clave({ m, d, t, e, a });
      if (i < 0 || i >= n) continue;
      out[i][0] += r; out[i][1] += k;
    }
    return out;
  }
  const TODO = { periodo: true, depto: true, tipo: true };
  const total = (arr) => arr.reduce((s, x) => [s[0] + x[0], s[1] + x[1]], [0, 0]);

  /* Totales de todo el registro (todas las filas, tambien las de meses con reporte incompleto) */
  const F = D.fuentes;
  const N_TOTAL = sum(F.medellin.n) + sum(F.bogota.n) + sum(F.resto.n);
  const K_TOTAL = sum(F.medellin.k) + sum(F.bogota.k) + sum(F.resto.k);
  const porAnio = (serie, a) => sum(serie.filter((_, i) => anioDe(i) === a));

  /* Cada grafica ocupa el alto de su contenedor (su panel en la pagina): se mide antes de
   * dibujar y se traduce al parametro de alto de cada tipo de grafica. Se guarda como se
   * dibujo para poder redibujarla al cambiar el tamano de la ventana. */
  const dibujos = {};
  function ajustarAlto(el, fn, o) {
    const H = el.clientHeight;
    if (!H) return o;
    o.extra = 0;
    if (fn === G.barrasV || fn === G.barrasAgrupadas) o.alto = H;
    else if (fn === G.barrasH) o.fila = Math.max(16, (H - (o.referencia ? 22 : 4) - (o.xTitulo ? 26 : 4) - 4) / Math.max(1, o.items.length));
    else if (fn === G.barrasDiv) o.fila = Math.max(16, (H - 30 - (o.xTitulo ? 28 : 6)) / Math.max(1, o.items.length));
    return o;
  }
  function dibujar(id, fn, o) { dibujos[id] = { fn, o }; fn($(id), ajustarAlto($(id), fn, o)); }

  /* ---------- KPIs: responden a la pregunta de negocio, del mas importante al menos ----------
   * Principal: que tan mortales son los siniestros (letalidad). Medianos: donde y en que
   * vehiculos se concentra el riesgo. Menores: el contexto del volumen. */
  function kpis() {
    const [n, k] = total(sumar(() => 0, 1, TODO));
    const cont = $('kpis'), menores = $('kpis-menores');
    cont.textContent = ''; menores.textContent = '';
    const prom = k / (n || 1);
    const kpi = (cls, titulo, valor, unidad, sub) => {
      const d = el('div', 'kpi' + (cls ? ' ' + cls : ''));
      const v = el('div', 'kpi-v', valor); if (unidad) v.appendChild(el('small', null, unidad));
      const s = el('div', 'kpi-s'); s.innerHTML = sub;
      d.append(el('div', 'kpi-t', titulo), v, s);
      cont.appendChild(d);
    };
    kpi('principal', 'Letalidad', n ? nf(1).format(prom * 100) : '—', '%', `<b>${n0(k)}</b> de ${n0(n)} vehículos en siniestros con víctimas estuvieron en uno con muertos`);

    const pt = sumar((x) => x.t, TIP.length, { periodo: true, depto: true });
    const tipos = pt.map((v, i) => ({ i, n: v[0], p: v[1] / (v[0] || 1) })).filter((d) => d.n >= 300 && TIP[d.i] !== 'OTROS').sort((a, b) => b.p - a.p);
    const pa = total(pt), promT = pa[1] / (pa[0] || 1);
    if (tipos[0]) kpi('', 'Vehículo más letal', tipoTxt(TIP[tipos[0].i]), null, `<b>${pct(tipos[0].p, 1)}</b> · ${nf(1).format(tipos[0].p / (promT || 1))}× el promedio`);
    else kpi('', 'Vehículo más letal', '—', null, 'Pocos datos');

    const pd = sumar((x) => x.d, DEP.length, { periodo: true, tipo: true });
    const pdt = total(pd), promD = pdt[1] / (pdt[0] || 1);
    const deps = pd.map((v, i) => ({ i, n: v[0], p: v[1] / (v[0] || 1) })).filter((d) => d.n >= 1000).sort((a, b) => b.p - a.p);
    if (deps[0]) kpi('', 'Departamento más letal', depto(DEP[deps[0].i]), null, `<b>${pct(deps[0].p, 1)}</b> · ${nf(1).format(deps[0].p / (promD || 1))}× el promedio`);
    else kpi('', 'Departamento más letal', '—', null, 'Pocos datos');

    const im = TIP.indexOf('MOTOCICLETA'), kt = sum(pt.map((v) => v[1]));
    const moto = im >= 0 ? pt[im][1] / (kt || 1) : 0;
    kpi('', 'Casos mortales con moto', pct(moto, 0), null, `<b>${n0(im >= 0 ? pt[im][1] : 0)}</b> vehículos`);

    // Menores: volumen, municipios con casos, ciudad con mas casos y que logra el modelo
    const porCiudad = ciudades();
    const conCasos = porCiudad.filter((c) => c.k > 0);
    const top = conCasos.sort((a, b) => b.k - a.k)[0];
    const Mo = D.modelo, c20 = Mo && Mo.cobertura ? Mo.cobertura.find((c) => Math.abs(c.fraccion - 0.2) < 1e-9) : null;
    [
      [n0(n), 'vehículos en siniestros'],
      [n0(conCasos.length), 'municipios con casos mortales'],
      [top ? muni(top.nombre) : '—', top ? `más casos mortales (${n0(top.k)})` : 'ciudad con más casos'],
      c20 ? [pct(c20.recall, 0), `casos mortales hallados al revisar el ${pct(c20.fraccion, 0)}`] : [String(M.length), 'meses de datos'],
    ].forEach(([v, t]) => { const d = el('div', 'kpi-m'); d.append(el('span', 'v', v), el('span', 't', t)); d.title = `${v} ${t}`; menores.appendChild(d); });
  }

  function pintarCifras(cont, items) {
    cont.textContent = '';
    items.forEach((c) => {
      const d = el('div', 'cifra' + (c.acento ? ' acento' : ''));
      const v = el('div', 'cifra-v', c.v); if (c.s) v.appendChild(el('small', null, c.s));
      d.append(v, el('div', 'cifra-t', c.t)); cont.appendChild(d);
    });
  }

  /* ---------- 2. Calidad del dato (fija, todas las filas) ----------
   * Cuatro graficas: quien dejo de reportar, el caso de Medellin mes a mes,
   * por que el promedio de 2025 engana y que ciudades tienen meses incompletos. */
  function calidad() {
    const med = F.medellin.n, bog = F.bogota.n, resto = F.resto.n;
    const cambio = (d) => (d.b - d.a) / (d.a || 1);
    const enPalabras = (c) => (c < 0 ? `${pct(-c, 0)} menos` : `${pct(c, 0)} más`);

    // 1. Quien dejo de reportar: barras agrupadas, el anio anterior al lado del ultimo anio completo
    const fuentes = [
      { nombre: 'Medellín', a: porAnio(med, A1), b: porAnio(med, A2), foco: true },
      { nombre: 'Bogotá', a: porAnio(bog, A1), b: porAnio(bog, A2), foco: true },
      { nombre: 'Resto del país', a: porAnio(resto, A1), b: porAnio(resto, A2), foco: false },
    ];
    const [fm, fb, fr] = fuentes;
    void fm; void fb; void fr; void enPalabras;
    dibujar('g-caida', G.barrasAgrupadas, { xTitulo: 'Reportes por fuente y año', yTitulo: 'Vehículos reportados',
      descripcion: `Vehículos reportados en ${A1} y en ${A2}: Medellín, Bogotá y resto del país`, series: [String(A1), String(A2)], etiquetasBarra: true, alto: 230,
      grupos: fuentes.map((d) => ({ nombre: d.nombre, nota: cambio(d) < 0 ? `bajó ${pct(-cambio(d), 0)}` : `subió ${pct(cambio(d), 0)}`, valores: [d.a, d.b] })),
      colorDe: (gi, k) => (fuentes[gi].foco ? (k ? TONO.focoDespues : TONO.focoAntes) : (k ? TONO.contextoDespues : TONO.contextoAntes)),
      fuerte: (gi, k) => fuentes[gi].foco && k === 1,
      tip: (gr, k) => [{ nombre: 'Vehículos reportados', valor: n0(gr.valores[k]) }],
    });

    // 2. Medellin mes a mes: reportados en su mes (gris) y reportes atrasados que llegaron juntos (amarillo)
    const reub = F.medellin_reubicados || M.map(() => 0);
    const cm = D.meta.carga_masiva_medellin;
    const base = med.map((v, i) => v - reub[i]);
    const tipicos = med.filter((_, i) => anioDe(i) <= A1).sort((a, b) => a - b);
    const tipico = tipicos[Math.floor(tipicos.length / 2)];
    const iCm = cm ? M.indexOf(cm.periodo) : -1;
    const iCorte = med.findIndex((v, i) => i > iCm && v < tipico * 0.2);
    const antes = med.slice(0, iCorte > 0 ? iCorte : med.length);
    const promedio = sum(antes) / (antes.length || 1), redondo = Math.round(promedio / 100) * 100;
    const grupos = ANIOS.map((a) => ({ desde: M.findIndex((m) => +m.slice(0, 4) === a), hasta: M.length - 1 - [...M].reverse().findIndex((m) => +m.slice(0, 4) === a), texto: String(a) }));
    dibujar('g-medellin', G.barrasV, { xTitulo: 'Mes del siniestro', yTitulo: 'Vehículos reportados',
      descripcion: 'Vehículos reportados por mes en Medellín', valores: base, encima: reub, alto: 230, grupos,
      leyenda: [{ color: C.neutro, texto: 'En su mes' }].concat(cm ? [{ color: C.acento, texto: `Tarde (${mesTxt(cm.periodo)})` }] : []),
      referencia: iCorte > 0 ? { desde: 0, hasta: iCorte - 1, valor: promedio, texto: `~${n0(redondo)}/mes` } : null,
      anotacion: iCorte > 0 ? { i: iCorte, valor: promedio * 0.5, lineas: [mayus(mesTxt(M[iCorte])), `${n0(med[iCorte])}`] } : null,
      tip: (i) => ({ titulo: mesTxt(M[i]), filas: [{ nombre: 'Enviados en su mes', valor: n0(base[i]) }].concat(reub[i] ? [{ nombre: 'Enviados tarde', valor: n0(reub[i]) }] : [], [{ nombre: 'Total', valor: n0(med[i]) }]) }),
    });

    // 3. El promedio de 2025 engana: todo el pais contra el pais sin Medellin ni Bogota
    const tasa = (series, a) => { const n = sum(series.map((x) => porAnio(x.n, a))); return n ? sum(series.map((x) => porAnio(x.k, a))) / n : 0; };
    const filas = [
      { nombre: 'Todo el país', a: tasa([F.medellin, F.bogota, F.resto], A1), b: tasa([F.medellin, F.bogota, F.resto], A2), foco: false },
      { nombre: 'Sin Medellín ni Bogotá', a: tasa([F.resto], A1), b: tasa([F.resto], A2), foco: true },
    ];
    const igual = (d) => de100(d.a) === de100(d.b);
    const mov = (d) => (igual(d) ? 'igual' : (d.b > d.a ? 'sube' : 'baja'));
    dibujar('g-espejismo', G.barrasAgrupadas, { xTitulo: 'Conjunto de datos y año', yTitulo: 'Letalidad (%)',
      descripcion: `De cada 100 vehículos, cuántos en siniestros con muertos, ${A1} y ${A2}`, series: [String(A1), String(A2)], etiquetasBarra: true, alto: 230, fmt: de100,
      grupos: filas.map((d) => ({ nombre: d.nombre, nota: mov(d), valores: [d.a, d.b] })),
      colorDe: (gi, k) => (filas[gi].foco ? (k ? TONO.focoDespues : TONO.focoAntes) : (k ? TONO.contextoDespues : TONO.contextoAntes)),
      fuerte: (gi) => filas[gi].foco,
      tip: (gr, k) => [{ nombre: 'De cada 100, con muertos', valor: de100(gr.valores[k]) }],
    });

    // 4. Meses con reporte incompleto o atrasado por ciudad (de las que mas reportan)
    const cob = D.cobertura, ult = 6, nM = M.length;
    const todas = cob.municipios.map((m, i) => ({ clave: i, nombre: muni(m), valor: cob.estado[i].filter((x) => x > 0).length, recientes: cob.estado[i].slice(-ult).filter((x) => x > 0).length }))
      .sort((a, b) => b.valor - a.valor);
    const items = todas.filter((d) => d.valor > 0).slice(0, 12);
    const [p1, p2] = items;
    dibujar('g-anomalos', G.barrasH, { xTitulo: 'Meses con reporte incompleto (de 57)', yTitulo: 'Ciudad',
      descripcion: 'Meses con reporte incompleto o atrasado por ciudad', items: items.slice(0, 8), fmt: (v) => `${v}`, xmax: nM, pista: true, fila: 25,
      acento: (d) => d === p1 || d === p2, nota: () => `de ${nM}`,
      tip: (d) => [{ nombre: 'Meses con reporte incompleto o atrasado', valor: `${d.valor} de ${nM}` }, { nombre: `De ellos, en los últimos ${ult} meses`, valor: String(d.recientes) }],
    });

  }

  /* ---------- 3. Como lo tratamos (fijo) ---------- */
  function tratamiento() {
    const m = D.meta, desfase = m.desfase_edad_fuente || {}, cm = m.carga_masiva_medellin, ed = m.edicion_fuente;
    const anioEdad = Object.keys(desfase).sort()[0];
    pintarCifras($('cifras-tratamiento'), [
      cm ? { v: n0(cm.reubicados), t: `reportes atrasados de Medellín reubicados en su mes`, acento: true } : null,
      !cm && ed ? { v: n0(ed.reubicados), t: `vehículos de la carga masiva de Medellín (${mesTxt(ed.periodo)}) repartidos en ${mesTxt(ed.desde)}–${mesTxt(ed.hasta)}`, acento: true } : null,
      { v: n0(m.filas_anomalas), t: 'vehículos de meses incompletos, fuera del modelo' },
      anioEdad ? { v: `+${nf(0).format(desfase[anioEdad])} años`, t: `error de edad en la fuente (${anioEdad}), recalculada` } : null,
      m.filas_identicas !== null ? { v: n0(m.filas_identicas), t: 'filas idénticas con identificador propio' } : null,
    ].filter(Boolean));
    const etapas = [
      { t: 'Carga', s: `${n0(m.filas)} vehículos con identificador; se revisan columnas, fechas y gravedad` },
      { t: 'Limpieza', s: `Textos y marcas unificados; ${n0(m.municipios)} municipios con su departamento` },
      { t: 'Meses incompletos', s: 'Cada mes de cada municipio se compara con su mes típico', acento: true },
      { t: 'Edad', s: 'Año del siniestro − año del modelo' },
      { t: 'Prueba', s: 'Municipios y un año que el modelo no vio' },
      { t: 'Tablero', s: 'Tablas ya procesadas, no el archivo original' },
    ];
    const car = $('carretera'); car.textContent = '';
    etapas.forEach((e, i) => {
      const d = el('div', 'etapa' + (e.acento ? ' acento' : '')); d.title = e.s;
      d.append(el('i', null, String(i + 1)), el('strong', null, e.t)); car.appendChild(d);
    });
  }

  /* ---------- Controles de la seccion 4 ---------- */
  function montarControles() {
    ['f-desde', 'f-hasta'].forEach((id) => {
      const s = $(id);
      ANIOS.forEach((a) => s.add(new Option(a === ANIO_PARCIAL ? `${a}*` : a, a)));
      s.addEventListener('change', () => {
        let a = +$('f-desde').value, b = +$('f-hasta').value;
        if (a > b) { if (id === 'f-desde') b = a; else a = b; }
        st.desde = a; st.hasta = b; render();
      });
    });
    const dep = $('f-depto'); dep.add(new Option('Todos', -1));
    DEP.map((d, i) => [depto(d), i]).sort((x, y) => x[0].localeCompare(y[0], 'es')).forEach(([txt, i]) => dep.add(new Option(txt, i)));
    dep.addEventListener('change', () => { st.depto = +dep.value; render(); });
    const tip = $('f-tipo'); tip.add(new Option('Todos', -1));
    TIP.forEach((t, i) => tip.add(new Option(tipoTxt(t), i)));
    tip.addEventListener('change', () => { st.tipo = +tip.value; render(); });
    $('btn-reset').addEventListener('click', () => { st = inicial(); render(); });
    if (ANIO_PARCIAL) [...document.querySelectorAll('#f-desde option, #f-hasta option')].filter((op) => +op.value === ANIO_PARCIAL).forEach((op) => { op.title = `${ANIO_PARCIAL} llega hasta ${MES_LARGO[+ultimo.slice(5) - 1]}`; });

    montarPaginas();
  }

  /* ---------- Paginacion: una seccion por pantalla ----------
   * El menu, el paginador (flechas y puntos) y las teclas de flecha cambian de pagina;
   * el ancla de la URL (#calidad, ...) recuerda la pagina al recargar. */
  const PAGINAS = [...document.querySelectorAll('.paginas .bloque')];
  let pagina = 0;
  function irA(i) {
    pagina = Math.max(0, Math.min(PAGINAS.length - 1, i));
    PAGINAS.forEach((p, k) => { p.classList.toggle('activa', k === pagina); p.setAttribute('aria-hidden', String(k !== pagina)); });
    const menu = PAGINAS[pagina].dataset.menu;
    document.querySelectorAll('.menu a').forEach((a) => a.classList.toggle('activo', a.getAttribute('href') === '#' + menu));
    [...$('pag-puntos').children].forEach((b, k) => b.setAttribute('aria-current', String(k === pagina)));
    $('pag-texto').textContent = `${pagina + 1} / ${PAGINAS.length}`;
    $('pag-ant').disabled = pagina === 0; $('pag-sig').disabled = pagina === PAGINAS.length - 1;
    history.replaceState(null, '', '#' + PAGINAS[pagina].id);
    if (getComputedStyle(PAGINAS[pagina]).position === 'absolute') scrollTo(0, 0); // en modo paginado nunca hay scroll
    G.ocultarTip();
  }
  function montarPaginas() {
    PAGINAS.forEach((p, k) => {
      const b = el('button'); b.type = 'button'; b.setAttribute('aria-label', `Página ${k + 1}: ${p.querySelector('h2').textContent || p.querySelector('.paso').textContent}`);
      b.addEventListener('click', () => irA(k)); $('pag-puntos').appendChild(b);
    });
    $('pag-ant').addEventListener('click', () => irA(pagina - 1));
    $('pag-sig').addEventListener('click', () => irA(pagina + 1));
    document.querySelectorAll('.menu a').forEach((a) => a.addEventListener('click', (ev) => {
      ev.preventDefault(); irA(PAGINAS.findIndex((p) => '#' + p.dataset.menu === a.getAttribute('href')));
    }));
    addEventListener('keydown', (ev) => {
      if (ev.target.closest('select, input')) return;
      if (ev.key === 'ArrowRight' || ev.key === 'PageDown') { ev.preventDefault(); irA(pagina + 1); }
      if (ev.key === 'ArrowLeft' || ev.key === 'PageUp') { ev.preventDefault(); irA(pagina - 1); }
    });
    const ini = PAGINAS.findIndex((p) => '#' + p.id === location.hash);
    irA(ini >= 0 ? ini : 0);
  }

  function pintarControles() {
    $('f-desde').value = st.desde; $('f-hasta').value = st.hasta; $('f-depto').value = st.depto; $('f-tipo').value = st.tipo;
    const chips = $('chips'); chips.textContent = '';
    const hay = st.desde !== ANIOS[0] || st.hasta !== ANIOS[ANIOS.length - 1] || st.depto >= 0 || st.tipo >= 0;
    if (hay) chips.appendChild(el('span', null, 'Filtros:'));
    const chip = (txt, quitar) => {
      const b = el('button', 'chip'); b.type = 'button'; b.setAttribute('aria-label', `Quitar filtro ${txt}`);
      b.append(document.createTextNode(txt), Object.assign(el('i'), { textContent: '×' }));
      b.addEventListener('click', () => { quitar(); render(); }); chips.appendChild(b);
    };
    if (st.desde !== ANIOS[0] || st.hasta !== ANIOS[ANIOS.length - 1]) chip(st.desde === st.hasta ? `${st.desde}` : `${st.desde}–${st.hasta}`, () => { st.desde = ANIOS[0]; st.hasta = ANIOS[ANIOS.length - 1]; });
    if (st.depto >= 0) chip(depto(DEP[st.depto]), () => { st.depto = -1; });
    if (st.tipo >= 0) chip(tipoTxt(TIP[st.tipo]), () => { st.tipo = -1; });
  }

  /* ---------- Ciudades: suma [vehiculos, con muertos] por municipio con los filtros ---------- */
  function ciudades(usarDepto = true) {
    const out = CIU.nombres.map((nombre, i) => ({ i, nombre, d: CIU.departamento[i], n: 0, k: 0 }));
    for (const [a, c, t, r, k] of CIU.cubo) {
      if (a < st.desde || a > st.hasta) continue;
      if (st.tipo >= 0 && t !== st.tipo) continue;
      if (usarDepto && st.depto >= 0 && CIU.departamento[c] !== st.depto) continue;
      out[c].n += r; out[c].k += k;
    }
    return out;
  }

  /* ---------- Mapa de calor de Colombia: a donde enviar los controles ----------
   * Departamentos coloreados con la medida elegida; en gris, los que no tienen datos.
   * Dos vistas: cuantos casos (para repartir agentes) y que tan mortal es cada siniestro
   * (para operativos focalizados). Responde a los anios y al tipo de vehiculo; el
   * departamento elegido se marca con un borde y se elige con un clic. */
  let vistaMapa = 'casos';
  /* Alto del mapa: el 80 % del area que le deja su panel en la pagina */
  function altoMapa() {
    return Math.max(300, Math.round($('g-mapa').clientHeight * 0.8));
  }
  function mapaCalor() {
    const MIN_DEPTO = 500;
    const seg = $('vista-mapa'); seg.textContent = '';
    [['casos', 'Casos mortales'], ['tasa', 'Letalidad']].forEach(([v, txt]) => {
      const b = el('button', null, txt); b.type = 'button'; b.setAttribute('aria-pressed', String(v === vistaMapa));
      b.addEventListener('click', () => { vistaMapa = v; mapaCalor(); }); seg.appendChild(b);
    });
    const esCasos = vistaMapa === 'casos';
    const pd = sumar((x) => x.d, DEP.length, { periodo: true, tipo: true });
    const tasa = (v, min) => (v.n >= min ? v.k / v.n : null);
    const deps = pd.map(([n, k]) => ({ n, k }));
    const maxKD = Math.max(...deps.map((d) => d.k), 1), maxTD = Math.max(...deps.map((d) => tasa(d, MIN_DEPTO) || 0), 1e-9);
    const valDep = {};
    DEP.forEach((nombre, i) => {
      const d = deps[i];
      valDep[nombre] = esCasos ? (d.k ? Math.sqrt(d.k / maxKD) : null) : (tasa(d, MIN_DEPTO) === null ? null : tasa(d, MIN_DEPTO) / maxTD);
    });
    const filas = (n, k) => [{ nombre: 'Vehículos en siniestros', valor: n0(n) }, { nombre: 'Con muertos', valor: n0(k) }, { nombre: 'Letalidad', valor: n ? pct(k / n, 1) : '—' }];
    const opciones = {
      descripcion: 'Mapa de calor de Colombia por departamento', geo: GEO,
      altoMax: altoMapa(), deptos: valDep,
      marcarDepto: st.depto >= 0 ? DEP[st.depto] : null,
      tipDepto: (nombre) => { const i = DEP.indexOf(nombre); const d = deps[i] || { n: 0, k: 0 }; return { titulo: depto(nombre), filas: filas(d.n, d.k) }; },
      onDepto: (nombre) => { const i = DEP.indexOf(nombre); if (i < 0) return; st.depto = st.depto === i ? -1 : i; render(); },
    };
    dibujos['g-mapa'] = { fn: G.mapa, o: opciones };
    G.mapa($('g-mapa'), opciones);
    const esc = $('escala-mapa'); esc.textContent = '';
    const sinDatos = el('span', 'sin-datos'); sinDatos.append(Object.assign(el('i'), { style: `background:${G.C.tierra}` }), document.createTextNode('Sin datos'));
    esc.append(el('span', null, esCasos ? 'Pocos casos' : 'Baja letalidad'), Object.assign(el('span', 'rampa'), { style: `background:${G.CALOR.gradiente()}` }), el('span', null, esCasos ? 'Muchos casos' : 'Alta letalidad'), sinDatos);
  }

  /* ---------- 4. Hallazgos ---------- */
  function render() {
    pintarControles();
    kpis();
    const [n] = total(sumar(() => 0, 1, TODO));
    if (!n) {
      ['g-tipo', 'g-volumen', 'g-edad', 'g-depto'].forEach((id) => { delete dibujos[id]; G.vacio($(id)); });
      mapaCalor();
      return;
    }
    const iOtros = TIP.indexOf('OTROS');
    const ordenar = (items, campo) => items.sort((a, b) => (a.clave === iOtros) - (b.clave === iOtros) || b[campo] - a[campo]);
    const alClic = (campo) => (c) => { st[campo] = st[campo] === c ? -1 : c; render(); };

    // Que tan mortal es el siniestro segun el tipo de vehiculo (sin el filtro de tipo, para poder comparar y elegir)
    const pt = sumar((x) => x.t, TIP.length, { periodo: true, depto: true });
    const pa = total(pt), prom = pa[1] / (pa[0] || 1);
    const tipos = ordenar(pt.map((v, i) => ({ clave: i, cod: TIP[i], carga: CLA[i] === 'carga', nombre: tipoTxt(TIP[i]), valor: v[0] ? v[1] / v[0] : 0, n: v[0], k: v[1] }))
      .filter((d) => d.n >= 100), 'valor');
    if (!tipos.length) { delete dibujos['g-tipo']; G.vacio($('g-tipo'), 'Muy pocos vehículos'); } else {
      dibujar('g-tipo', G.barrasH, { xTitulo: 'Letalidad (%)', yTitulo: 'Tipo de vehículo',
        descripcion: 'De cada 100 vehículos, cuántos en siniestros con muertos, por tipo de vehículo', items: tipos, fmt: de100, fila: 25,
        acento: (d) => d.carga, activo: st.tipo >= 0 ? st.tipo : null,
        referencia: { valor: prom, texto: `Prom. ${de100(prom)}` },
        tip: (d) => [{ nombre: 'Vehículos en siniestros', valor: n0(d.n) }, { nombre: 'En siniestros con muertos', valor: n0(d.k) }, { nombre: 'De cada 100', valor: de100(d.valor) }],
        onClic: alClic('tipo'),
      });
    }

    // Cuantos casos mortales hay de cada tipo
    const vt = pt, kTot = sum(vt.map((v) => v[1])) || 1;
    const vol = ordenar(vt.map((v, i) => ({ clave: i, cod: TIP[i], nombre: tipoTxt(TIP[i]), valor: v[1], n: v[0] })).filter((d) => d.valor > 0), 'valor');
    if (vol.length) {
      dibujar('g-volumen', G.barrasH, { xTitulo: 'Vehículos en siniestros con muertos', yTitulo: 'Tipo de vehículo',
        descripcion: 'Vehículos en siniestros con muertos por tipo de vehículo', items: vol, fmt: n0, fila: 25,
        acento: (d) => d.cod === 'MOTOCICLETA', activo: st.tipo >= 0 ? st.tipo : null, nota: (d) => pct(d.valor / kTot, 0),
        tip: (d) => [{ nombre: 'En siniestros con muertos', valor: n0(d.valor) }, { nombre: 'Parte de los casos mortales', valor: pct(d.valor / kTot, 1) }, { nombre: 'Vehículos en siniestros', valor: n0(d.n) }],
        onClic: alClic('tipo'),
      });
    } else { delete dibujos['g-volumen']; G.vacio($('g-volumen'), 'Sin casos mortales'); }

    // Edad del vehiculo al momento del siniestro (escala ordinal, en su orden natural)
    const se = sumar((x) => x.e, EDA.length, TODO);
    const pe = se.map((v) => (v[0] ? v[1] / v[0] : 0)), ne = se.map((v) => v[0]);
    const con = pe.filter((_, i) => ne[i] > 0);
    const iMax = pe.indexOf(Math.max(...con));
    dibujar('g-edad', G.barrasV, { xTitulo: 'Edad del vehículo (años)', yTitulo: 'Letalidad (%)',
      descripcion: 'De cada 100 vehículos, cuántos en siniestros con muertos, por edad del vehículo', cats: EDA, valores: pe, fmt: de100, alto: 200, sinEje: true,
      acento: (i) => i === iMax, etiquetar: (i) => ne[i] > 0,
      tip: (i) => ({ titulo: `${EDA[i]} años`, filas: [{ nombre: 'Vehículos en siniestros', valor: n0(ne[i]) }, { nombre: 'De cada 100, con muertos', valor: de100(pe[i]) }] }),
    });

    // Departamentos (sin el filtro de departamento, para poder comparar y elegir)
    const pd = sumar((x) => x.d, DEP.length, { periodo: true, tipo: true });
    const dpa = total(pd), promD = dpa[1] / (dpa[0] || 1);
    const MIN_D = 1000;
    const deps = pd.map((v, i) => ({ clave: i, nombre: depto(DEP[i]), valor: v[0] ? v[1] / v[0] : 0, n: v[0], k: v[1] }))
      .filter((d) => d.n >= MIN_D).sort((a, b) => b.valor - a.valor).slice(0, 8);
    if (deps.length) {
      dibujar('g-depto', G.barrasH, { xTitulo: 'Letalidad (%)', yTitulo: 'Departamento',
        descripcion: 'De cada 100 vehículos, cuántos en siniestros con muertos, por departamento', items: deps, fmt: de100, fila: 25,
        acento: (d) => d === deps[0], activo: st.depto >= 0 ? st.depto : null,
        referencia: { valor: promD, texto: `Prom. ${de100(promD)}` },
        tip: (d) => [{ nombre: 'Vehículos en siniestros', valor: n0(d.n) }, { nombre: 'En siniestros con muertos', valor: n0(d.k) }, { nombre: 'De cada 100', valor: de100(d.valor) }],
        onClic: alClic('depto'),
      });
    } else {
      delete dibujos['g-depto']; G.vacio($('g-depto'), 'Muy pocos datos');
    }
    mapaCalor();
  }

  /* ---------- 5. Modelo (fijo) ---------- */
  function modelo() {
    const Mo = D.modelo;
    if (!Mo) { $('modelo').hidden = true; document.querySelector('.menu a[href="#modelo"]').hidden = true; return; }
    const base = Mo.metricas.find((r) => r.modelo === 'prevalencia');
    const prev = base ? base.pr_auc : Mo.metricas[0].prevalencia;
    const items = Mo.metricas.filter((r) => r.modelo !== 'prevalencia')
      .map((r) => ({ clave: r.modelo, nombre: MODELO_TXT[r.modelo] || r.modelo, valor: r.pr_auc, r }))
      .sort((a, b) => b.valor - a.valor);
    const mejor = items.find((d) => d.r.mejor) || items[0];
    if (base) items.push({ clave: 'prevalencia', nombre: MODELO_TXT.prevalencia, valor: prev, r: base });
    const sen = Object.fromEntries((Mo.sensibilidad || []).map((s) => [s.conjunto, s]));
    $('t-modelo').textContent = 'El modelo señala bien qué reportes revisar primero, aunque falla donde se reporta distinto';

    // 1. Como se usa: revisar primero los reportes que el modelo marca como mas riesgosos
    const cob = Mo.cobertura || [];
    const c20 = cob.find((c) => Math.abs(c.fraccion - 0.2) < 1e-9) || cob[Math.floor(cob.length / 2)];
    if (c20) {
      dibujar('g-cobertura', G.barrasAgrupadas, { xTitulo: 'Reportes revisados primero (% del total)', yTitulo: 'Casos mortales hallados (%)',
        descripcion: 'Casos mortales encontrados al revisar primero los reportes de mayor riesgo, frente al azar', series: ['Al azar', 'Con el modelo'], alto: 230, fmt: (v) => pct(v, 0),
        grupos: cob.map((c) => ({ nombre: `Revisando ${pct(c.fraccion, 0)}`, valores: [c.fraccion, c.recall] })),
        colorDe: (gi, k) => (k ? C.acento : C.neutro),
        tip: (gr, k) => [{ nombre: k ? 'Con el modelo' : 'Al azar', valor: `${de100(gr.valores[k])} de cada 100 casos mortales` }],
      });
    }

    // 2. Que modelo: calificacion de cada uno en la prueba con 2024, junto a no usar modelo
    dibujar('g-modelos', G.barrasH, { xTitulo: 'PR-AUC (de 0 a 1, más alto es mejor)', yTitulo: 'Modelo',
      descripcion: 'Calificación PR-AUC de cada modelo en la prueba con 2024', items, fmt: (v) => nf(3).format(v), fila: 38, extra: 36,
      acento: (d) => d === mejor, colorDe: (d) => (d === mejor ? C.acento : (d.clave === 'prevalencia' ? C.neutroClaro : C.neutro)),
      tip: (d) => [{ nombre: 'Calificación (PR-AUC)', valor: nf(3).format(d.r.pr_auc) }].concat(d.clave === 'prevalencia' ? [] : [
        { nombre: 'Casos mortales que detecta', valor: `${de100(d.r.recall)} de cada 100` }, { nombre: 'Aciertos entre sus alertas', valor: `${de100(d.r.precision)} de cada 100` }]),
    });
    void sen;

    // 3. Municipios con mas (o menos) casos mortales de los que el modelo espera
    const L = Mo.letalidad.map((d) => ({ ...d, nombre: muni(d.municipio), valor: d.diferencia })).sort((a, b) => b.valor - a.valor);
    const conSigno = (v) => `${v >= 0 ? '+' : '−'}${de100(Math.abs(v))}`;
    dibujar('g-letalidad', G.barrasDiv, { xTitulo: 'Casos mortales reales − esperados (de cada 100 vehículos)', yTitulo: 'Municipio',
      descripcion: 'Casos mortales reales menos esperados por municipio, de cada 100 vehículos',
      items: L.slice(0, 10), izquierda: '← menos', derecha: 'más →', fmt: conSigno, fila: 23,
      tip: (d) => [{ nombre: 'Real, de cada 100', valor: de100(d.observada) }, { nombre: 'Esperado, de cada 100', valor: de100(d.esperada) },
        { nombre: 'Diferencia', valor: conSigno(d.diferencia) }, { nombre: 'Vehículos en siniestros', valor: n0(d.registros) }],
    });

  }

  /* ---------- 6. Que hacer (fijo) ---------- */
  function conclusiones() {
    const pt = sumar((x) => x.t, TIP.length, {}), [n, k] = total(pt);
    const carga = pt.map((v, i) => ({ cod: TIP[i], carga: CLA[i] === 'carga', p: v[1] / (v[0] || 1), n: v[0] })).filter((d) => d.carga && d.n >= 1000).sort((a, b) => b.p - a.p);
    const im = TIP.indexOf('MOTOCICLETA'), moto = pt[im] || [0, 0];
    const Mo = D.modelo;
    const mejor = Mo ? Mo.metricas.filter((r) => r.modelo !== 'prevalencia').sort((a, b) => b.pr_auc - a.pr_auc)[0] : null;
    const prev = Mo ? (Mo.metricas.find((r) => r.modelo === 'prevalencia') || {}).pr_auc : null;
    const alto = Mo && Mo.letalidad.length ? Mo.letalidad.reduce((a, b) => (b.razon > a.razon ? b : a)) : null;
    const lista = $('lista-conclusiones'); lista.textContent = '';
    [
      carga.length ? [`Priorizar controles a vehículos de carga: ${plural(carga[0].cod)} ${pct(carga[0].p, 1)} de letalidad vs. ${pct(k / n, 1)} promedio.`, 'Es una asociación: la gravedad es del siniestro, no del vehículo; un camión queda «con muertos» aunque muera el motociclista.'] : null,
      [`Mantener campañas para motociclistas: ${pct(moto[1] / (k || 1), 0)} de los casos mortales.`, `Son ${de100(moto[0] / (n || 1))} de cada 100 vehículos en siniestros: aunque un siniestro de moto no sea más mortal que el promedio, son tantas que suman la mayoría de las muertes.`],
      [`Exigir reporte completo y a tiempo al RUNT: Medellín y Bogotá casi dejaron de reportar en ${A2}.`, 'Sin ese reporte el promedio del país se distorsiona; la sección 2 sirve para vigilar mes a mes qué tan completo reporta cada municipio.'],
      mejor ? [`Revisar primero lo que marca el modelo y municipios sobre lo esperado${alto ? `, como ${muni(alto.municipio)}` : ''}.`, `Ordena el riesgo ${nf(1).format(mejor.pr_auc / prev)} veces mejor que el azar en la prueba con 2024, pero no alcanza para decidir caso por caso.`] : null,
    ].filter(Boolean).forEach(([a, b]) => { const li = el('li'), d = el('div', null, a); li.title = b; li.appendChild(d); lista.appendChild(li); });
    const m = D.meta;
    $('pie').textContent = '';
    $('pie').appendChild(el('p', null, `Fuente: ${m.fuente} · ${mesTxt(M[0])} a ${mesTxt(ultimo)}${m.edicion_fuente ? ` · Editado: ${m.edicion_fuente.descripcion}` : ''} · Mapa: ${GEO.fuente} · CC BY-SA 4.0`));
  }

  calidad();
  tratamiento();
  montarControles();
  render();
  modelo();
  conclusiones();
  let espera, anchoPrevio = innerWidth, altoPrevio = innerHeight;
  addEventListener('resize', () => {
    clearTimeout(espera);
    espera = setTimeout(() => { if (innerWidth === anchoPrevio && innerHeight === altoPrevio) return; anchoPrevio = innerWidth; altoPrevio = innerHeight; calidad(); render(); modelo(); }, 150);
  });
};
