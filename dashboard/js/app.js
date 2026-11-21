/* Tablero para secretarias de movilidad y autoridades de transito: gravedad de
 * los siniestros viales en Colombia (RUNT, Ley 2251 de 2022).
 * Orden de lectura = orden de la exposicion. Solo la seccion 4 responde a los filtros.
 * Toda cifra que aparece en pantalla se calcula aqui a partir de data/datos.js. */
(function () {
  'use strict';
  const G = window.Graficos, C = G.C, n0 = G.n0, nf = G.nf, pct = G.pct;
  const D = window.DATOS_RUNT;
  const $ = (id) => document.getElementById(id);
  if (!D) { document.querySelector('.portada h1').textContent = 'Faltan los datos del tablero (data/datos.js)'; return; }

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
  /* Tonos de la comparacion antes / despues: lo que importa en amarillo, el contexto en gris; claro = antes */
  const TONO = { focoAntes: '#f8dc8a', focoDespues: C.acento, contextoAntes: '#d6d9dd', contextoDespues: '#a3a7ad' };

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

  /* Cada grafica se dibuja una vez y se guarda como se dibujo, para poder igualar
   * la altura de las dos graficas de una misma fila sin dejar huecos */
  const dibujos = {};
  function dibujar(id, fn, o) { dibujos[id] = { fn, o }; fn($(id), o); }
  function altoContenido(p) {
    const top = p.getBoundingClientRect().top;
    return Math.max(...[...p.children].filter((c) => c.offsetParent !== null).map((c) => c.getBoundingClientRect().bottom - top));
  }
  function igualar(a, b) {
    const ids = [a, b].filter((id) => dibujos[id]);
    if (ids.length < 2) return;
    ids.forEach((id) => { const d = dibujos[id]; if (d.o.extra) { d.o.extra = 0; d.fn($(id), d.o); } });
    const paneles = ids.map((id) => $(id).closest('.panel'));
    if (Math.abs(paneles[0].getBoundingClientRect().top - paneles[1].getBoundingClientRect().top) > 2) return; // una debajo de la otra
    const h = paneles.map(altoContenido);
    const k = h[0] < h[1] ? 0 : 1, falta = Math.abs(h[0] - h[1]);
    if (falta < 6) return;
    const d = dibujos[ids[k]]; d.o.extra = falta; d.fn($(ids[k]), d.o);
  }

  /* ---------- Portada y 1. El problema ---------- */
  function problema() {
    $('sub-portada').textContent = `Tablero para secretarías de movilidad y autoridades de tránsito · Fuente: Ministerio de Transporte, RUNT (Ley 2251 de 2022), datos.gov.co · ${mesTxt(M[0])} a ${mesTxt(ultimo)}`;
    $('t-problema').textContent = `De ${n0(N_TOTAL)} vehículos en siniestros con víctimas, ${n0(K_TOTAL)} estuvieron en uno con muertos: ${de100(K_TOTAL / N_TOTAL)} de cada 100`;
    pintarCifras($('cifras'), [
      { v: n0(N_TOTAL), t: 'vehículos en siniestros con víctimas' },
      { v: n0(K_TOTAL), t: `estuvieron en siniestros con muertos: ${de100(K_TOTAL / N_TOTAL)} de cada 100`, acento: true },
      { v: n0(D.meta.municipios), t: `municipios de ${D.meta.departamentos} departamentos` },
      { v: String(M.length), s: 'meses', t: `de ${mesLargo(M[0])} a ${mesLargo(ultimo)}` },
    ]);
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
    $('t-caida').textContent = `En ${A2} Medellín reportó ${enPalabras(cambio(fm))} vehículos que en ${A1}, y Bogotá ${enPalabras(cambio(fb))}`;
    $('sub-caida').textContent = `Vehículos reportados en ${A1} y en ${A2}, según dónde ocurrió el siniestro · el resto del país reportó ${enPalabras(cambio(fr))}`;
    dibujar('g-caida', G.barrasAgrupadas, {
      descripcion: `Vehículos reportados en ${A1} y en ${A2}: Medellín, Bogotá y resto del país`, series: [String(A1), String(A2)], etiquetasBarra: true, alto: 280,
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
    $('t-medellin').textContent = iCorte > 0
      ? `Medellín reportaba unos ${n0(redondo)} vehículos al mes y desde ${mesLargo(M[iCorte])} casi no reporta`
      : `Medellín reporta unos ${n0(redondo)} vehículos al mes`;
    const grupos = ANIOS.map((a) => ({ desde: M.findIndex((m) => +m.slice(0, 4) === a), hasta: M.length - 1 - [...M].reverse().findIndex((m) => +m.slice(0, 4) === a), texto: String(a) }));
    dibujar('g-medellin', G.barrasV, {
      descripcion: 'Vehículos reportados por mes en Medellín', valores: base, encima: reub, alto: 270, grupos,
      leyenda: [{ color: C.neutro, texto: 'Enviados en su mes' }].concat(cm ? [{ color: C.acento, texto: `Enviados tarde, todos juntos en ${mesLargo(cm.periodo)}` }] : []),
      referencia: iCorte > 0 ? { desde: 0, hasta: iCorte - 1, valor: promedio, texto: `unos ${n0(redondo)} al mes` } : null,
      anotacion: iCorte > 0 ? { i: iCorte, valor: promedio * 0.5, lineas: [mayus(mesLargo(M[iCorte])), `solo ${n0(med[iCorte])} vehículos`] } : null,
      tip: (i) => ({ titulo: mesTxt(M[i]), filas: [{ nombre: 'Enviados en su mes', valor: n0(base[i]) }].concat(reub[i] ? [{ nombre: 'Enviados tarde', valor: n0(reub[i]) }] : [], [{ nombre: 'Total', valor: n0(med[i]) }]) }),
    });
    $('nota-medellin').textContent = cm
      ? `En amarillo, ${n0(cm.reubicados)} reportes atrasados que Medellín envió todos juntos en ${mesLargo(cm.periodo)}, mostrados en los meses en que probablemente ocurrieron.`
      : '';

    // 3. El promedio de 2025 engana: todo el pais contra el pais sin Medellin ni Bogota
    const tasa = (series, a) => { const n = sum(series.map((x) => porAnio(x.n, a))); return n ? sum(series.map((x) => porAnio(x.k, a))) / n : 0; };
    const filas = [
      { nombre: 'Todo el país', a: tasa([F.medellin, F.bogota, F.resto], A1), b: tasa([F.medellin, F.bogota, F.resto], A2), foco: false },
      { nombre: 'Sin Medellín ni Bogotá', a: tasa([F.resto], A1), b: tasa([F.resto], A2), foco: true },
    ];
    const igual = (d) => de100(d.a) === de100(d.b);
    const mov = (d) => (igual(d) ? 'se queda igual' : (d.b > d.a ? 'sube' : 'baja'));
    $('t-espejismo').textContent = igual(filas[1]) && filas[0].b > filas[0].a && !igual(filas[0])
      ? `En ${A2} los siniestros no se volvieron más mortales: cambió quién reporta`
      : `Sin Medellín ni Bogotá, de cada 100 vehículos en siniestros ${de100(filas[1].b)} estuvieron en uno con muertos en ${A2}`;
    $('sub-espejismo').textContent = `De cada 100 vehículos en siniestros, cuántos estuvieron en uno con muertos · Medellín casi no reporta muertes (${de100(tasa([F.medellin], A1))} de cada 100 en ${A1}): sin ella, el promedio del país sube solo`;
    dibujar('g-espejismo', G.barrasAgrupadas, {
      descripcion: `De cada 100 vehículos, cuántos en siniestros con muertos, ${A1} y ${A2}`, series: [String(A1), String(A2)], etiquetasBarra: true, alto: 280, fmt: de100,
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
    const [p1, p2] = items, demas = todas.slice(2);
    const fr6 = sum(demas.map((d) => d.recientes)) / (sum(demas.map((d) => d.valor)) || 1);
    const cuantos = fr6 >= 0.8 ? 'casi todos' : (fr6 >= 0.5 ? 'la mayoría' : null);
    $('t-anomalos').textContent = `${p1.nombre} (${p1.valor} meses) y ${p2.nombre} (${p2.valor}) son las ciudades con más meses de reporte incompleto`;
    $('sub-anomalos').textContent = `Meses, de ${nM}, con menos de la quinta parte de lo normal o más del triple por reportes atrasados${cuantos ? ` · en las demás ciudades, ${cuantos} son los últimos ${ult} meses, que aún no llegan completos` : ''}`;
    dibujar('g-anomalos', G.barrasH, {
      descripcion: 'Meses con reporte incompleto o atrasado por ciudad', items, fmt: (v) => `${v}`, xmax: nM, pista: true, fila: 27,
      acento: (d) => d === p1 || d === p2, nota: () => `de ${nM}`,
      tip: (d) => [{ nombre: 'Meses con reporte incompleto o atrasado', valor: `${d.valor} de ${nM}` }, { nombre: `De ellos, en los últimos ${ult} meses`, valor: String(d.recientes) }],
    });

    igualar('g-caida', 'g-medellin');
    igualar('g-espejismo', 'g-anomalos');
  }

  /* ---------- 3. Como lo tratamos (fijo) ---------- */
  function tratamiento() {
    const m = D.meta, desfase = m.desfase_edad_fuente || {}, cm = m.carga_masiva_medellin;
    const anioEdad = Object.keys(desfase).sort()[0];
    pintarCifras($('cifras-tratamiento'), [
      cm ? { v: n0(cm.reubicados), t: `reportes atrasados que Medellín envió juntos en ${mesLargo(cm.periodo)}: se cuentan en los meses en que probablemente ocurrieron`, acento: true } : null,
      { v: n0(m.filas_anomalas), t: `vehículos de meses con reporte incompleto o atrasado (${de100(m.filas_anomalas / m.filas)} de cada 100): el modelo no aprende con ellos` },
      anioEdad ? { v: `${nf(0).format(desfase[anioEdad])} años`, t: `de más tenía la edad del vehículo en la fuente en ${anioEdad}: la recalculamos con el año del siniestro` } : null,
      m.filas_identicas !== null ? { v: n0(m.filas_identicas), t: 'filas que en la fuente eran idénticas ahora tienen cada una su identificador (id_registro), aunque no se puede saber cuáles iban en el mismo siniestro' } : null,
    ].filter(Boolean));
    $('cifras-tratamiento').classList.add('tratamiento');
    const etapas = [
      { t: 'Carga', s: `<em>${n0(m.filas)}</em> vehículos, cada uno con su identificador; se revisan columnas, fechas y gravedad` },
      { t: 'Limpieza', s: `Textos y marcas unificados; <em>${n0(m.municipios)}</em> municipios con su departamento` },
      { t: 'Meses incompletos', s: 'Cada mes de cada municipio se compara con su mes típico: se marcan los incompletos y los reportes atrasados', acento: true },
      { t: 'Edad', s: 'Edad del vehículo = año del siniestro − año del modelo' },
      { t: 'Prueba', s: 'El modelo se prueba en municipios y en un año que no vio al aprender' },
      { t: 'Tablero', s: 'Muestra las tablas ya procesadas, no el archivo original' },
    ];
    const car = $('carretera'); car.textContent = '';
    etapas.forEach((e, i) => {
      const d = el('div', 'etapa' + (e.acento ? ' acento' : ''));
      const sp = el('span'); sp.innerHTML = e.s;
      d.append(el('i', null, String(i + 1)), el('strong', null, e.t), sp); car.appendChild(d);
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
    if (ANIO_PARCIAL) $('nota-parcial').textContent = `* ${ANIO_PARCIAL} llega hasta ${MES_LARGO[+ultimo.slice(5) - 1]}.`;

    const enlaces = [...document.querySelectorAll('.menu a')];
    const obs = new IntersectionObserver((ents) => ents.forEach((e) => {
      if (e.isIntersecting) enlaces.forEach((a) => a.classList.toggle('activo', a.getAttribute('href') === '#' + e.target.id));
    }), { rootMargin: '-30% 0px -65% 0px' });
    document.querySelectorAll('main .bloque').forEach((b) => obs.observe(b));
  }

  function pintarControles() {
    $('f-desde').value = st.desde; $('f-hasta').value = st.hasta; $('f-depto').value = st.depto; $('f-tipo').value = st.tipo;
    const chips = $('chips'); chips.textContent = '';
    const hay = st.desde !== ANIOS[0] || st.hasta !== ANIOS[ANIOS.length - 1] || st.depto >= 0 || st.tipo >= 0;
    chips.appendChild(el('span', null, hay ? 'Filtrando por:' : `Todo el país, todos los años: ${n0(D.meta.filas_limpias)} vehículos, sin los meses con reporte incompleto o atrasado.`));
    const chip = (txt, quitar) => {
      const b = el('button', 'chip'); b.type = 'button'; b.setAttribute('aria-label', `Quitar filtro ${txt}`);
      b.append(document.createTextNode(txt), Object.assign(el('i'), { textContent: '×' }));
      b.addEventListener('click', () => { quitar(); render(); }); chips.appendChild(b);
    };
    if (st.desde !== ANIOS[0] || st.hasta !== ANIOS[ANIOS.length - 1]) chip(st.desde === st.hasta ? `${st.desde}` : `${st.desde}–${st.hasta}`, () => { st.desde = ANIOS[0]; st.hasta = ANIOS[ANIOS.length - 1]; });
    if (st.depto >= 0) chip(depto(DEP[st.depto]), () => { st.depto = -1; });
    if (st.tipo >= 0) chip(tipoTxt(TIP[st.tipo]), () => { st.tipo = -1; });
  }

  /* ---------- Mapa de calor: a donde enviar los controles ----------
   * Filas: departamentos con mas casos mortales; columnas: tipos de vehiculo.
   * Dos vistas: cuantos casos (para repartir agentes) y que tan mortal es cada
   * siniestro (para operativos focalizados). Responde al filtro de anios; el
   * departamento y el tipo elegidos se marcan con un borde. */
  let vistaMapa = 'casos';
  function mapaCalor() {
    const MIN_CELDA = 200, FILAS = 15;
    const celdas = DEP.map(() => TIP.map(() => [0, 0]));
    for (const [m, d, t, e, r, k] of CUBO) {
      const a = anioDe(m);
      if (a < st.desde || a > st.hasta) continue;
      celdas[d][t][0] += r; celdas[d][t][1] += k;
    }
    const cols = TIP.map((t, j) => j).filter((j) => TIP[j] !== 'OTROS');
    const totDep = celdas.map((fila) => total(fila));
    const filas = totDep.map((v, i) => [v[1], i]).sort((a, b) => b[0] - a[0]).slice(0, FILAS).filter(([v]) => v > 0).map(([, i]) => i);
    const seg = $('vista-mapa'); seg.textContent = '';
    [['casos', 'Cuántos casos'], ['tasa', 'Qué tan mortal']].forEach(([v, txt]) => {
      const b = el('button', null, txt); b.type = 'button'; b.setAttribute('aria-pressed', String(v === vistaMapa));
      b.addEventListener('click', () => { vistaMapa = v; mapaCalor(); }); seg.appendChild(b);
    });
    if (!filas.length) { G.vacio($('g-mapa')); $('t-mapa').textContent = 'Sin siniestros en este periodo'; $('sub-mapa').textContent = ''; $('escala-mapa').textContent = ''; return; }

    const casos = filas.map((i) => cols.map((j) => celdas[i][j][1]));
    const tasa = filas.map((i) => cols.map((j) => (celdas[i][j][0] >= MIN_CELDA ? celdas[i][j][1] / celdas[i][j][0] : null)));
    const esCasos = vistaMapa === 'casos';
    const maxC = Math.max(...casos.flat(), 1), maxT = Math.max(...tasa.flat().filter((v) => v !== null), 1e-9);

    // Titulo: las celdas que mas pesan en la vista elegida, agrupadas por tipo de vehiculo
    const todas = [];
    filas.forEach((i, a) => cols.forEach((j, b) => todas.push({ i, j, casos: casos[a][b], tasa: tasa[a][b] })));
    const describir = (top) => {
      const porTipo = new Map();
      top.forEach((c) => { if (!porTipo.has(c.j)) porTipo.set(c.j, []); porTipo.get(c.j).push(depto(DEP[c.i])); });
      const partes = [...porTipo].map(([j, ds]) => `${plural(TIP[j])} en ${enLista(ds)}`);
      return partes.length > 1 ? `${partes.slice(0, -1).join(', ')}, y ${partes[partes.length - 1]}` : partes[0];
    };
    if (esCasos) {
      const top = [...todas].sort((x, y) => y.casos - x.casos).slice(0, 3);
      $('t-mapa').textContent = `Donde más casos mortales hay: ${describir(top)}`;
      $('sub-mapa').textContent = `Vehículos en siniestros con muertos, por departamento y tipo de vehículo · los ${filas.length} departamentos con más casos · clic en una celda para filtrar las gráficas de abajo`;
    } else {
      const top = todas.filter((c) => c.tasa !== null).sort((x, y) => y.tasa - x.tasa).slice(0, 3);
      $('t-mapa').textContent = top.length ? `Donde cada siniestro es más mortal: ${describir(top)}` : 'Muy pocos datos por celda en este periodo';
      $('sub-mapa').textContent = `De cada 100 vehículos en siniestros, cuántos estuvieron en uno con muertos · los ${filas.length} departamentos con más casos · clic en una celda para filtrar las gráficas de abajo`;
    }

    G.matriz($('g-mapa'), {
      descripcion: 'Mapa de calor por departamento y tipo de vehículo',
      filas: filas.map((i) => depto(DEP[i])), columnas: cols.map((j) => tipoTxt(TIP[j])), columnasPartidas: cols.map((j) => PARTIDO[tipoTxt(TIP[j])] || null),
      intensidad: (a, b) => (esCasos ? Math.sqrt(casos[a][b] / maxC) : (tasa[a][b] === null ? null : tasa[a][b] / maxT)),
      textoDe: (a, b) => (esCasos ? (casos[a][b] ? n0(casos[a][b]) : '') : (tasa[a][b] === null ? '' : de100(tasa[a][b]))),
      totales: { titulo: esCasos ? 'Total' : 'Todos', textos: filas.map((i) => (esCasos ? n0(totDep[i][1]) : de100(totDep[i][1] / (totDep[i][0] || 1)))) },
      marcarFila: filas.indexOf(st.depto), marcarColumna: cols.indexOf(st.tipo),
      tip: (a, b) => {
        const c = celdas[filas[a]][cols[b]];
        return { titulo: `${depto(DEP[filas[a]])} · ${tipoTxt(TIP[cols[b]])}`, filas: [{ nombre: 'Vehículos en siniestros', valor: n0(c[0]) }, { nombre: 'En siniestros con muertos', valor: n0(c[1]) }, { nombre: 'De cada 100', valor: c[0] ? de100(c[1] / c[0]) : '—' }] };
      },
      onClic: (a, b) => {
        const d = filas[a], tp = cols[b];
        if (st.depto === d && st.tipo === tp) { st.depto = -1; st.tipo = -1; } else { st.depto = d; st.tipo = tp; }
        render();
      },
    });
    const esc = $('escala-mapa'); esc.textContent = '';
    esc.append(el('span', null, esCasos ? 'Pocos casos' : 'Menos mortal'), Object.assign(el('span', 'rampa'), { style: `background:${G.CALOR.gradiente()}` }), el('span', null, esCasos ? 'Muchos casos' : 'Más mortal'));
    if (!esCasos) { const b = el('span', 'item'); b.append(el('span', 'muestra blanca'), document.createTextNode(`En blanco: menos de ${n0(MIN_CELDA)} vehículos, muy pocos para saberlo`)); esc.appendChild(b); }
    esc.appendChild(el('span', 'escala-nota', 'Responde al filtro de años; el departamento y el tipo elegidos se marcan con un borde.'));
  }

  /* ---------- 4. Hallazgos ---------- */
  function render() {
    pintarControles();
    mapaCalor();
    const [n] = total(sumar(() => 0, 1, TODO));
    if (!n) {
      ['t-tipo', 't-volumen', 't-edad', 't-depto'].forEach((id) => { $(id).textContent = 'Sin siniestros con estos filtros'; });
      ['sub-tipo', 'sub-volumen', 'sub-edad', 'sub-depto'].forEach((id) => { $(id).textContent = ''; });
      ['g-tipo', 'g-volumen', 'g-edad', 'g-depto'].forEach((id) => { delete dibujos[id]; G.vacio($(id)); });
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
    if (!tipos.length) { $('t-tipo').textContent = 'Muy pocos vehículos con estos filtros'; $('sub-tipo').textContent = ''; delete dibujos['g-tipo']; G.vacio($('g-tipo')); } else {
      const carga = tipos.filter((d) => d.carga && d.n >= 300).sort((a, b) => b.valor - a.valor).slice(0, 3);
      const primero = tipos[0];
      $('t-tipo').textContent = primero.carga ? 'Los siniestros con vehículos de carga son los más mortales' : `Los siniestros con ${plural(primero.cod)} son los más mortales`;
      $('sub-tipo').textContent = `De cada 100 vehículos de cada tipo en siniestros, cuántos estuvieron en uno con muertos${carga.length ? ' · en amarillo, los de carga' : ''} · clic en una barra para filtrar`;
      dibujar('g-tipo', G.barrasH, {
        descripcion: 'De cada 100 vehículos, cuántos en siniestros con muertos, por tipo de vehículo', items: tipos, fmt: de100,
        acento: (d) => d.carga, activo: st.tipo >= 0 ? st.tipo : null,
        referencia: { valor: prom, texto: `Promedio: ${de100(prom)}` },
        tip: (d) => [{ nombre: 'Vehículos en siniestros', valor: n0(d.n) }, { nombre: 'En siniestros con muertos', valor: n0(d.k) }, { nombre: 'De cada 100', valor: de100(d.valor) }],
        onClic: alClic('tipo'),
      });
    }

    // Cuantos casos mortales hay de cada tipo
    const vt = pt, kTot = sum(vt.map((v) => v[1])) || 1, nTot = sum(vt.map((v) => v[0])) || 1;
    const vol = ordenar(vt.map((v, i) => ({ clave: i, cod: TIP[i], nombre: tipoTxt(TIP[i]), valor: v[1], n: v[0] })).filter((d) => d.valor > 0), 'valor');
    const iMoto = TIP.indexOf('MOTOCICLETA'), moto = vol.find((d) => d.cod === 'MOTOCICLETA');
    const parte = moto ? moto.valor / kTot : 0;
    $('t-volumen').textContent = moto
      ? (parte > 0.5 ? `Pero más de la mitad de los casos mortales (${pct(parte, 0)}) involucra una moto` : `Pero el ${pct(parte, 0)} de los casos mortales involucra una moto`)
      : 'Casos mortales por tipo de vehículo';
    $('sub-volumen').textContent = `Vehículos en siniestros con muertos, por tipo, y su parte del total${iMoto >= 0 && vt[iMoto][0] ? ` · hay muchas más motos que cualquier otro vehículo: son ${de100(vt[iMoto][0] / nTot)} de cada 100 en siniestros` : ''} · clic para filtrar`;
    if (vol.length) {
      dibujar('g-volumen', G.barrasH, {
        descripcion: 'Vehículos en siniestros con muertos por tipo de vehículo', items: vol, fmt: n0,
        acento: (d) => d.cod === 'MOTOCICLETA', activo: st.tipo >= 0 ? st.tipo : null, nota: (d) => pct(d.valor / kTot, 0),
        tip: (d) => [{ nombre: 'En siniestros con muertos', valor: n0(d.valor) }, { nombre: 'Parte de los casos mortales', valor: pct(d.valor / kTot, 1) }, { nombre: 'Vehículos en siniestros', valor: n0(d.n) }],
        onClic: alClic('tipo'),
      });
    } else { delete dibujos['g-volumen']; G.vacio($('g-volumen'), 'Sin casos mortales con estos filtros'); }

    // Edad del vehiculo al momento del siniestro (escala ordinal, en su orden natural)
    const se = sumar((x) => x.e, EDA.length, TODO);
    const pe = se.map((v) => (v[0] ? v[1] / v[0] : 0)), ne = se.map((v) => v[0]);
    const con = pe.filter((_, i) => ne[i] > 0);
    const iMax = pe.indexOf(Math.max(...con)), iMin = pe.indexOf(Math.min(...con));
    $('t-edad').textContent = `Los siniestros con vehículos de ${EDA[iMax]} años son los más mortales`;
    $('sub-edad').textContent = `De cada 100 vehículos en siniestros, cuántos estuvieron en uno con muertos, según la edad del vehículo: ${de100(pe[iMax])} en los de ${EDA[iMax]} años y ${de100(pe[iMin])} en los de ${EDA[iMin]}`;
    dibujar('g-edad', G.barrasV, {
      descripcion: 'De cada 100 vehículos, cuántos en siniestros con muertos, por edad del vehículo', cats: EDA, valores: pe, fmt: de100, alto: 250, sinEje: true,
      acento: (i) => i === iMax, etiquetar: (i) => ne[i] > 0, xTitulo: 'Edad del vehículo, en años',
      tip: (i) => ({ titulo: `${EDA[i]} años`, filas: [{ nombre: 'Vehículos en siniestros', valor: n0(ne[i]) }, { nombre: 'De cada 100, con muertos', valor: de100(pe[i]) }] }),
    });

    // Departamentos (sin el filtro de departamento, para poder comparar y elegir)
    const pd = sumar((x) => x.d, DEP.length, { periodo: true, tipo: true });
    const dpa = total(pd), promD = dpa[1] / (dpa[0] || 1);
    const MIN_D = 1000;
    const deps = pd.map((v, i) => ({ clave: i, nombre: depto(DEP[i]), valor: v[0] ? v[1] / v[0] : 0, n: v[0], k: v[1] }))
      .filter((d) => d.n >= MIN_D).sort((a, b) => b.valor - a.valor).slice(0, 10);
    if (deps.length) {
      const veces = deps[0].valor / (promD || 1);
      $('t-depto').textContent = veces >= 1.5
        ? `En ${deps[0].nombre} los siniestros son ${nf(0).format(veces)} veces más mortales que el promedio del país`
        : `En ${deps[0].nombre}, ${de100(deps[0].valor)} de cada 100 vehículos en siniestros estuvieron en uno con muertos`;
      $('sub-depto').textContent = `De cada 100 vehículos en siniestros, cuántos estuvieron en uno con muertos: ${deps[0].nombre} ${de100(deps[0].valor)}; promedio ${de100(promD)} · los 10 departamentos más altos, con ${n0(MIN_D)} vehículos o más · clic para filtrar`;
      dibujar('g-depto', G.barrasH, {
        descripcion: 'De cada 100 vehículos, cuántos en siniestros con muertos, por departamento', items: deps, fmt: de100,
        acento: (d) => d === deps[0], activo: st.depto >= 0 ? st.depto : null,
        referencia: { valor: promD, texto: `Promedio: ${de100(promD)}` },
        tip: (d) => [{ nombre: 'Vehículos en siniestros', valor: n0(d.n) }, { nombre: 'En siniestros con muertos', valor: n0(d.k) }, { nombre: 'De cada 100', valor: de100(d.valor) }],
        onClic: alClic('depto'),
      });
    } else {
      $('t-depto').textContent = 'Muy pocos datos por departamento con estos filtros'; $('sub-depto').textContent = '';
      delete dibujos['g-depto']; G.vacio($('g-depto'));
    }
    igualar('g-tipo', 'g-volumen');
    igualar('g-edad', 'g-depto');
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
      $('t-cobertura').textContent = `Revisando ${de100(c20.fraccion)} de cada 100 reportes, el modelo encuentra ${de100(c20.recall)} de cada 100 casos mortales`;
      $('sub-cobertura').textContent = `De cada 100 casos mortales, cuántos encuentra la autoridad si revisa primero los reportes que el modelo marca como más riesgosos; al azar encontraría ${de100(c20.fraccion)} · probado en municipios que el modelo nunca vio`;
      dibujar('g-cobertura', G.barrasAgrupadas, {
        descripcion: 'Casos mortales encontrados al revisar primero los reportes de mayor riesgo, frente al azar', series: ['Al azar', 'Con el modelo'], alto: 290, fmt: de100,
        grupos: cob.map((c) => ({ nombre: `${de100(c.fraccion)} de cada 100`, valores: [c.fraccion, c.recall] })),
        colorDe: (gi, k) => (k ? C.acento : C.neutro), xTitulo: 'Reportes revisados primero',
        tip: (gr, k) => [{ nombre: k ? 'Con el modelo' : 'Al azar', valor: `${de100(gr.valores[k])} de cada 100 casos mortales` }],
      });
    }

    // 2. Que modelo: calificacion de cada uno en la prueba con 2024, junto a no usar modelo
    $('t-modelos').textContent = `El mejor modelo, ${mejor.nombre.toLowerCase()}, ordena el riesgo ${nf(1).format(mejor.valor / prev)} veces mejor que el azar`;
    dibujar('g-modelos', G.barrasH, {
      descripcion: 'Calificación PR-AUC de cada modelo en la prueba con 2024', items, fmt: (v) => nf(3).format(v), fila: 38,
      acento: (d) => d === mejor, colorDe: (d) => (d === mejor ? C.acento : (d.clave === 'prevalencia' ? C.neutroClaro : C.neutro)),
      tip: (d) => [{ nombre: 'Calificación (PR-AUC)', valor: nf(3).format(d.r.pr_auc) }].concat(d.clave === 'prevalencia' ? [] : [
        { nombre: 'Casos mortales que detecta', valor: `${de100(d.r.recall)} de cada 100` }, { nombre: 'Aciertos entre sus alertas', valor: `${de100(d.r.precision)} de cada 100` }]),
    });
    $('nota-modelos').textContent = sen.todos && sen.sin_medellin && sen.solo_medellin
      ? `Gradient boosting combina cientos de árboles de decisión pequeños; la regresión logística es el modelo simple de referencia. En municipios que el modelo nunca vio su calificación es ${nf(2).format(sen.todos.pr_auc)}; sin Medellín sube a ${nf(2).format(sen.sin_medellin.pr_auc)}, porque allí casi no se reportan muertes (${de100(sen.solo_medellin.prevalencia)} de cada 100).`
      : '';

    // 3. Municipios con mas (o menos) casos mortales de los que el modelo espera
    const L = Mo.letalidad.map((d) => ({ ...d, nombre: muni(d.municipio), valor: d.diferencia })).sort((a, b) => b.valor - a.valor);
    const alto = L.length ? L.reduce((a, b) => (b.razon > a.razon ? b : a), L[0]) : null;
    $('t-letalidad').textContent = alto
      ? `${muni(alto.municipio)} tiene ${nf(1).format(alto.razon)} veces más casos mortales de los esperados: es el primer municipio para revisar`
      : 'Sin municipios con datos suficientes';
    $('sub-letalidad').textContent = `De cada 100 vehículos en siniestros, cuántos más (o menos) estuvieron en uno con muertos de lo que el modelo esperaba por sus vehículos y su contexto · los ${L.length} municipios más alejados de lo esperado, con ${n0(Mo.letalidad_min_registros)} vehículos o más`;
    const conSigno = (v) => `${v >= 0 ? '+' : '−'}${de100(Math.abs(v))}`;
    dibujar('g-letalidad', G.barrasDiv, {
      descripcion: 'Casos mortales reales menos esperados por municipio, de cada 100 vehículos', items: L,
      izquierda: '← menos de los esperados', derecha: 'más de los esperados →', fmt: conSigno,
      tituloDetalle: 'Real frente a esperado', detalle: (d) => `${de100(d.observada)} frente a ${de100(d.esperada)}`,
      tip: (d) => [{ nombre: 'Real, de cada 100', valor: de100(d.observada) }, { nombre: 'Esperado, de cada 100', valor: de100(d.esperada) },
        { nombre: 'Diferencia', valor: conSigno(d.diferencia) }, { nombre: 'Vehículos en siniestros', valor: n0(d.registros) }],
    });
    $('nota-grupos').textContent = 'A la derecha (amarillo), municipios con más muertes de las que explican sus vehículos y su contexto: hay riesgos que revisar en la vía. A la izquierda, menos de las esperadas: puede ser menor riesgo o que no se reportan todas las muertes, y conviene verificarlo con la autoridad local.';

    igualar('g-cobertura', 'g-modelos');
  }

  /* ---------- 6. Que hacer (fijo) ---------- */
  function conclusiones() {
    const pt = sumar((x) => x.t, TIP.length, {}), [n, k] = total(pt);
    const carga = pt.map((v, i) => ({ cod: TIP[i], carga: CLA[i] === 'carga', p: v[1] / (v[0] || 1), n: v[0] })).filter((d) => d.carga && d.n >= 1000).sort((a, b) => b.p - a.p);
    const im = TIP.indexOf('MOTOCICLETA'), moto = pt[im] || [0, 0];
    const cm = D.meta.carga_masiva_medellin;
    const Mo = D.modelo;
    const mejor = Mo ? Mo.metricas.filter((r) => r.modelo !== 'prevalencia').sort((a, b) => b.pr_auc - a.pr_auc)[0] : null;
    const prev = Mo ? (Mo.metricas.find((r) => r.modelo === 'prevalencia') || {}).pr_auc : null;
    const alto = Mo && Mo.letalidad.length ? Mo.letalidad.reduce((a, b) => (b.razon > a.razon ? b : a)) : null;
    const lista = $('lista-conclusiones'); lista.textContent = '';
    [
      carga.length ? [`Priorizar controles y revisiones técnico-mecánicas en vehículos de carga: de cada 100 ${plural(carga[0].cod)} en siniestros, ${de100(carga[0].p)} terminan en uno con muertos${carga.length > 1 ? ` (${enLista(carga.slice(1).map((d) => `${plural(d.cod)} ${de100(d.p)}`))})` : ''}, frente a ${de100(k / n)} en promedio.`, 'Es una asociación: la gravedad es del siniestro, no del vehículo; un camión queda «con muertos» aunque muera el motociclista.'] : null,
      [`Mantener las campañas para motociclistas: están en el ${pct(moto[1] / (k || 1), 0)} de los casos mortales.`, `Son ${de100(moto[0] / (n || 1))} de cada 100 vehículos en siniestros: aunque un siniestro de moto no sea más mortal que el promedio, son tantas que suman la mayoría de las muertes.`],
      [`Reportar completo y a tiempo al RUNT: en ${A2} Medellín y Bogotá casi dejaron de reportar${cm ? `, y Medellín envió ${n0(cm.publicados)} reportes juntos en ${mesLargo(cm.periodo)}` : ''}.`, 'Sin ese reporte el promedio del país se distorsiona; la sección 2 sirve para vigilar mes a mes qué tan completo reporta cada municipio.'],
      mejor ? [`Usar el modelo para decidir qué revisar primero y para revisar municipios con más casos mortales de los esperados${alto ? `, como ${muni(alto.municipio)}` : ''}.`, `Ordena el riesgo ${nf(1).format(mejor.pr_auc / prev)} veces mejor que el azar en la prueba con 2024, pero no alcanza para decidir caso por caso.`] : null,
    ].filter(Boolean).forEach(([a, b]) => { const li = el('li'), d = el('div'); d.append(document.createTextNode(a), el('span', null, b)); li.appendChild(d); lista.appendChild(li); });
    const m = D.meta;
    $('pie').textContent = '';
    $('pie').appendChild(el('p', null, `Fuente: ${m.fuente}. Licencia CC BY-SA 4.0.`));
    $('fuente').innerHTML = '';
    $('fuente').append(el('b', null, 'Fuente:'), document.createTextNode(` Ministerio de Transporte, RUNT · ${n0(m.filas)} vehículos · datos de ${mesTxt(M[0])} a ${mesTxt(ultimo)}`));
  }

  problema();
  calidad();
  tratamiento();
  montarControles();
  render();
  modelo();
  conclusiones();
  let espera, anchoPrevio = innerWidth;
  addEventListener('resize', () => {
    clearTimeout(espera);
    espera = setTimeout(() => { if (innerWidth === anchoPrevio) return; anchoPrevio = innerWidth; calidad(); render(); modelo(); }, 150);
  });
})();
