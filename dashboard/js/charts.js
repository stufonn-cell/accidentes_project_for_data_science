/* Gráficos SVG sin dependencias: columnas apiladas, líneas, matriz de calor,
 * barras horizontales apiladas, anillos, minigráficos y el mapa de calor. */
(function (root) {
  'use strict';

  const C = {
    t50: '#effbfa', t100: '#d7f4f1', t200: '#aee8e3', t300: '#72d5ce', t400: '#33bdb5', t500: '#13a19b',
    t600: '#0c8580', t700: '#0b6a67', t800: '#0c5350', t900: '#0a3c3b', ambar: '#f0a43a',
    texto: '#0a3c3b', texto2: '#47696a', texto3: '#7b9796', rejilla: '#e6f2f1', borde: '#d6ebe9', fondo: '#ffffff',
  };
  const NS = 'http://www.w3.org/2000/svg';
  const nf = (d) => new Intl.NumberFormat('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d });
  const n0 = (v) => nf(0).format(v);

  function s(tag, attrs, parent, texto) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) n.setAttribute(k, attrs[k]);
    if (texto !== undefined) n.textContent = texto;
    if (parent) parent.appendChild(n);
    return n;
  }

  function lienzo(el, alto, m, descripcion) {
    el.textContent = '';
    const w = Math.max(el.clientWidth || 560, 280);
    const svg = s('svg', { viewBox: `0 0 ${w} ${alto}`, width: w, height: alto, role: 'img', 'aria-label': descripcion }, el);
    return { svg, w, h: alto, iw: w - m.l - m.r, ih: alto - m.t - m.b, m };
  }

  function vacio(el, texto) {
    el.textContent = '';
    const d = document.createElement('div');
    d.className = 'vacio'; d.textContent = texto;
    el.appendChild(d);
  }

  /* Marcas "redondas" del eje entre min y max. */
  function marcas(min, max, n) {
    const rango = (max - min) || 1;
    const bruto = rango / n, p = Math.pow(10, Math.floor(Math.log10(bruto)));
    const paso = [1, 2, 2.5, 5, 10].map((k) => k * p).find((k) => k >= bruto);
    const a = Math.floor(min / paso) * paso, b = Math.ceil(max / paso - 1e-9) * paso;
    const out = [];
    for (let v = a; v <= b + paso / 2; v += paso) out.push(Math.round(v * 1e6) / 1e6);
    return out;
  }

  /* Rampa secuencial turquesa, de claro (poco) a oscuro (mucho). */
  const RAMPA = ['#e9f8f6', '#aee8e3', '#5ccdc5', '#13a19b', '#0b6a67', '#0a3c3b'];
  function hexRgb(h) { return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); }
  const RAMPA_RGB = RAMPA.map(hexRgb);
  function rampaRgb(t) {
    t = Math.max(0, Math.min(1, t)) * (RAMPA_RGB.length - 1);
    const i = Math.min(Math.floor(t), RAMPA_RGB.length - 2), f = t - i;
    const a = RAMPA_RGB[i], b = RAMPA_RGB[i + 1];
    return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
  }
  const rampa = (t) => `rgb(${rampaRgb(t).join(',')})`;
  const rampaCss = () => `linear-gradient(90deg, ${RAMPA.join(',')})`;

  /* Escala del mapa de calor: de blanco (poca concentración) a rojo intenso (mucha). */
  const CALOR = ['#ffffff', '#ffe3df', '#fcb3a7', '#f6735f', '#e0302a', '#a50f15'];
  const CALOR_RGB = CALOR.map(hexRgb);
  function calorRgb(t) {
    t = Math.max(0, Math.min(1, t)) * (CALOR_RGB.length - 1);
    const i = Math.min(Math.floor(t), CALOR_RGB.length - 2), f = t - i;
    const a = CALOR_RGB[i], b = CALOR_RGB[i + 1];
    return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
  }
  const calorCss = () => `linear-gradient(90deg, ${CALOR.join(',')})`;

  /* ---------- Tooltip compartido ---------- */
  const tip = () => document.getElementById('tip');
  function mostrarTip(ev, titulo, filas) {
    const t = tip();
    t.textContent = '';
    const b = document.createElement('b'); b.textContent = titulo; t.appendChild(b);
    (filas || []).forEach((f) => {
      const d = document.createElement('div');
      if (f.color) { const i = document.createElement('i'); i.style.background = f.color; d.appendChild(i); }
      d.appendChild(document.createTextNode(f.nombre));
      if (f.valor !== undefined) { const sp = document.createElement('span'); sp.textContent = f.valor; d.appendChild(sp); }
      t.appendChild(d);
    });
    t.hidden = false;
    const r = t.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
    t.style.left = Math.max(8, x) + 'px'; t.style.top = Math.max(8, y) + 'px';
  }
  function ocultarTip() { tip().hidden = true; }

  function ejeY(g, ticks, y, x0, x1, fmt) {
    ticks.forEach((v) => {
      s('line', { x1: x0, x2: x1, y1: y(v), y2: y(v), stroke: C.rejilla }, g);
      s('text', { x: x0 - 8, y: y(v) + 4, 'text-anchor': 'end', 'font-size': 11.5, fill: C.texto3 }, g, fmt(v));
    });
  }

  /* Rectángulo con las esquinas superiores redondeadas y la base recta. */
  function barraSup(x, y, w, h, r) {
    r = Math.min(r, w / 2, h);
    if (h <= 0) return '';
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  /* Igual, con el extremo derecho redondeado (barras horizontales). */
  function barraDer(x, y, w, h, r) {
    r = Math.min(r, h / 2, w);
    if (w <= 0) return '';
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }

  /* Línea de promedio punteada en ámbar, con su etiqueta. */
  function lineaPromedio(g, x0, x1, yv, texto) {
    s('line', { x1: x0, x2: x1, y1: yv, y2: yv, stroke: C.ambar, 'stroke-width': 2, 'stroke-dasharray': '6 5' }, g);
    const t = s('text', { x: x1, y: yv - 7, 'text-anchor': 'end', 'font-size': 11.5, 'font-weight': 600, fill: C.texto2 }, g, texto);
    t.setAttribute('paint-order', 'stroke'); t.setAttribute('stroke', '#fff'); t.setAttribute('stroke-width', 4);
  }

  /* ---------- Columnas apiladas ---------- */
  function columnas(el, o) {
    const alto = o.alto || 300;
    const L = lienzo(el, alto, { t: 18, r: 8, b: 30, l: 48 }, o.descripcion);
    const n = o.cats.length;
    if (!n) return vacio(el, 'Sin siniestros con estos filtros');
    const tot = o.cats.map((_, i) => o.series.reduce((a, se) => a + se.valores[i], 0));
    const ticks = marcas(0, Math.max(...tot, 1), 4);
    const ymax = ticks[ticks.length - 1];
    const y = (v) => L.m.t + L.ih - (v / ymax) * L.ih;
    const g = s('g', {}, L.svg);
    ejeY(g, ticks, y, L.m.l, L.w - L.m.r, n0);
    const banda = L.iw / n, bw = Math.min(46, banda * 0.62);
    const paso = Math.ceil(n / Math.floor(L.iw / 44));
    o.cats.forEach((c, i) => {
      const cx = L.m.l + banda * (i + 0.5);
      let acum = 0;
      const visibles = o.series.map((se, k) => ({ se, k, v: se.valores[i] })).filter((d) => d.v > 0);
      visibles.forEach((d, j) => {
        const y0 = y(acum), y1 = y(acum + d.v);
        const ultimo = j === visibles.length - 1;
        // 2 px de separación entre segmentos
        const h = Math.max(0, y0 - y1 - (j > 0 ? 2 : 0));
        s('path', { d: ultimo ? barraSup(cx - bw / 2, y1, bw, h, 4) : `M${cx - bw / 2},${y1}h${bw}v${h}h${-bw}Z`, fill: d.se.color }, g);
        acum += d.v;
      });
      if (i % paso === 0) s('text', { x: cx, y: alto - 10, 'text-anchor': 'middle', 'font-size': 11.5, fill: C.texto3 }, g, c);
      const hit = s('rect', { x: cx - banda / 2, y: L.m.t, width: banda, height: L.ih, fill: 'transparent' }, g);
      hit.addEventListener('mousemove', (ev) => mostrarTip(ev, o.titulos ? o.titulos[i] : c,
        o.series.map((se) => ({ nombre: se.nombre, color: se.color, valor: n0(se.valores[i]) }))
          .concat([{ nombre: 'Total', valor: n0(tot[i]) }])));
      hit.addEventListener('mouseleave', ocultarTip);
    });
    if (o.promedio) lineaPromedio(g, L.m.l, L.w - L.m.r, y(o.promedio), `Promedio ${n0(o.promedio)}`);
  }

  /* ---------- Líneas (eje x numérico) ---------- */
  function lineas(el, o) {
    const alto = o.alto || 300;
    const L = lienzo(el, alto, { t: 18, r: 12, b: 30, l: 48 }, o.descripcion);
    const todos = o.series.flatMap((se) => se.puntos);
    if (!todos.length) return vacio(el, 'Sin siniestros con estos filtros');
    const xs = todos.map((p) => p[0]), ys = todos.map((p) => p[1]);
    const xmin = o.xmin ?? Math.min(...xs), xmax = o.xmax ?? Math.max(...xs);
    const ticks = marcas(o.ymin ?? 0, o.ymax ?? Math.max(...ys, 1e-9), 4);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const x = (v) => L.m.l + ((v - xmin) / ((xmax - xmin) || 1)) * L.iw;
    const y = (v) => L.m.t + L.ih - ((v - y0) / ((y1 - y0) || 1)) * L.ih;
    const g = s('g', {}, L.svg);
    ejeY(g, ticks, y, L.m.l, L.w - L.m.r, o.yFmt || n0);
    (o.xTicks || []).forEach((t) => s('text', { x: x(t[0]), y: alto - 10, 'text-anchor': 'middle', 'font-size': 11.5, fill: C.texto3 }, g, t[1]));
    if (o.diagonal) s('line', { x1: x(xmin), y1: y(xmin), x2: x(xmax), y2: y(xmax), stroke: C.texto3, 'stroke-width': 1.5, 'stroke-dasharray': '4 5' }, g);
    if (o.promedio) lineaPromedio(g, L.m.l, L.w - L.m.r, y(o.promedio), `Promedio ${n0(o.promedio)}`);
    o.series.forEach((se) => {
      if (se.area) {
        const p = se.puntos;
        s('path', { d: `M${x(p[0][0])},${y(y0)}` + p.map((q) => `L${x(q[0])},${y(q[1])}`).join('') + `L${x(p[p.length - 1][0])},${y(y0)}Z`, fill: se.color, opacity: 0.12 }, g);
      }
      s('path', { d: se.puntos.map((q, i) => `${i ? 'L' : 'M'}${x(q[0]).toFixed(1)},${y(q[1]).toFixed(1)}`).join(''), fill: 'none', stroke: se.color, 'stroke-width': 2, 'stroke-linejoin': 'round', 'stroke-dasharray': se.punteada ? '5 4' : null }, g);
      if (se.marcadores) se.puntos.forEach((q) => s('circle', { cx: x(q[0]), cy: y(q[1]), r: 4, fill: se.color, stroke: '#fff', 'stroke-width': 2 }, g));
    });
    // Capa de cursor: línea vertical + tooltip con el punto más cercano
    const guia = s('line', { y1: L.m.t, y2: L.m.t + L.ih, stroke: C.t300, 'stroke-width': 1, visibility: 'hidden' }, g);
    const puntos = o.series.map((se) => s('circle', { r: 5, fill: se.color, stroke: '#fff', 'stroke-width': 2, visibility: 'hidden' }, g));
    const area = s('rect', { x: L.m.l, y: L.m.t, width: L.iw, height: L.ih, fill: 'transparent' }, g);
    area.addEventListener('mousemove', (ev) => {
      const r = L.svg.getBoundingClientRect();
      const px = ((ev.clientX - r.left) / r.width) * L.w;
      const base = o.series[0].puntos;
      let k = 0, mejor = Infinity;
      base.forEach((p, i) => { const d = Math.abs(x(p[0]) - px); if (d < mejor) { mejor = d; k = i; } });
      guia.setAttribute('x1', x(base[k][0])); guia.setAttribute('x2', x(base[k][0])); guia.setAttribute('visibility', 'visible');
      o.series.forEach((se, j) => {
        const p = se.puntos[k];
        if (!p) return;
        puntos[j].setAttribute('cx', x(p[0])); puntos[j].setAttribute('cy', y(p[1])); puntos[j].setAttribute('visibility', 'visible');
      });
      mostrarTip(ev, o.tituloPunto(k), o.series.filter((se) => se.puntos[k]).map((se) => ({ nombre: se.nombre, color: se.color, valor: (o.tipFmt || n0)(se.puntos[k][1]) })));
    });
    area.addEventListener('mouseleave', () => { ocultarTip(); guia.setAttribute('visibility', 'hidden'); puntos.forEach((p) => p.setAttribute('visibility', 'hidden')); });
  }

  /* ---------- Matriz de calor (filas × columnas) ---------- */
  function matriz(el, o) {
    const nf = o.filas.length, nc = o.columnas.length;
    const w = Math.max(el.clientWidth || 560, 280);
    const ml = 40, mt = 6, mb = 24, gap = 2;
    const cw = (w - ml) / nc, ch = Math.max(22, Math.min(34, cw * 1.25));
    const alto = mt + nf * ch + mb;
    const L = lienzo(el, alto, { t: mt, r: 0, b: mb, l: ml }, o.descripcion);
    const max = Math.max(...o.valores.flat(), 1);
    let pico = [0, 0];
    o.valores.forEach((fila, i) => fila.forEach((v, j) => { if (v > o.valores[pico[0]][pico[1]]) pico = [i, j]; }));
    o.filas.forEach((f, i) => {
      s('text', { x: ml - 8, y: mt + i * ch + ch / 2 + 4, 'text-anchor': 'end', 'font-size': 11.5, fill: C.texto3 }, L.svg, f);
      o.columnas.forEach((c, j) => {
        const v = o.valores[i][j];
        const r = s('rect', { x: ml + j * cw + gap / 2, y: mt + i * ch + gap / 2, width: cw - gap, height: ch - gap, rx: 3, fill: v ? rampa(v / max) : C.t50 }, L.svg);
        r.addEventListener('mousemove', (ev) => mostrarTip(ev, `${o.filasLargas[i]} · ${o.columnasLargas[j]}`, [{ nombre: 'Siniestros', valor: n0(v) }, { nombre: 'Con víctimas', valor: n0(o.victimas[i][j]) }]));
        r.addEventListener('mouseleave', ocultarTip);
      });
    });
    if (o.valores[pico[0]][pico[1]] > 0) {
      s('rect', { x: ml + pico[1] * cw, y: mt + pico[0] * ch, width: cw, height: ch, rx: 4, fill: 'none', stroke: C.ambar, 'stroke-width': 2, 'pointer-events': 'none' }, L.svg);
    }
    o.columnas.forEach((c, j) => {
      if (j % 3 === 0) s('text', { x: ml + j * cw + cw / 2, y: alto - 8, 'text-anchor': 'middle', 'font-size': 11, fill: C.texto3 }, L.svg, c);
    });
    return max;
  }

  /* ---------- Barras horizontales apiladas ---------- */
  function barrasH(el, o) {
    if (!o.items.length) return vacio(el, 'Sin siniestros con estos filtros');
    const fila = 34, w = Math.max(el.clientWidth || 560, 280);
    const etiqueta = Math.min(200, w * 0.36), derecha = 132;
    const alto = o.items.length * fila + 4;
    const L = lienzo(el, alto, { t: 0, r: derecha, b: 0, l: etiqueta }, o.descripcion);
    const max = Math.max(...o.items.map((d) => d.valores.reduce((a, b) => a + b, 0)), 1);
    const x = (v) => (v / max) * L.iw;
    o.items.forEach((d, i) => {
      const yc = i * fila + fila / 2, bh = 14, tot = d.valores.reduce((a, b) => a + b, 0);
      const g = s('g', { 'data-clic': o.onClic ? 1 : null, opacity: o.activo && o.activo !== d.clave ? 0.4 : 1 }, L.svg);
      s('rect', { x: 0, y: yc - fila / 2, width: L.w, height: fila, fill: 'transparent' }, g);
      const nom = d.nombre.length > 30 ? d.nombre.slice(0, 29) + '…' : d.nombre;
      s('text', { x: etiqueta - 10, y: yc + 4, 'text-anchor': 'end', 'font-size': 12.5, fill: C.texto, 'font-weight': o.activo === d.clave ? 700 : 500 }, g, nom);
      let acum = 0;
      d.valores.forEach((v, k) => {
        if (v <= 0) return;
        const x0 = etiqueta + x(acum) + (acum > 0 ? 2 : 0), wv = Math.max(0, x(v) - (acum > 0 ? 2 : 0));
        const ultimo = d.valores.slice(k + 1).every((z) => z <= 0);
        s('path', { d: ultimo ? barraDer(x0, yc - bh / 2, wv, bh, 4) : `M${x0},${yc - bh / 2}h${wv}v${bh}h${-wv}Z`, fill: o.colores[k] }, g);
        acum += v;
      });
      s('text', { x: etiqueta + x(tot) + 8, y: yc + 4, 'font-size': 12.5, 'font-weight': 700, fill: C.texto }, g, n0(tot));
      s('text', { x: etiqueta + x(tot) + 8 + (n0(tot).length * 7.4) + 6, y: yc + 4, 'font-size': 11.5, fill: C.texto3 }, g, o.extra ? o.extra(d) : '');
      g.addEventListener('mousemove', (ev) => mostrarTip(ev, d.nombre, o.series.map((nm, k) => ({ nombre: nm, color: o.colores[k], valor: n0(d.valores[k]) }))
        .concat([{ nombre: 'Total', valor: n0(tot) }])));
      g.addEventListener('mouseleave', ocultarTip);
      if (o.onClic) g.addEventListener('click', () => { ocultarTip(); o.onClic(d.clave); });
    });
  }

  /* ---------- Anillo de proporción ---------- */
  function anillo(valor, color) {
    const svg = s('svg', { viewBox: '0 0 120 120', role: 'img', 'aria-label': `${Math.round(valor * 100)} %` });
    const r = 46, c = 2 * Math.PI * r;
    s('circle', { cx: 60, cy: 60, r, fill: 'none', stroke: C.t100, 'stroke-width': 12 }, svg);
    s('circle', { cx: 60, cy: 60, r, fill: 'none', stroke: color, 'stroke-width': 12, 'stroke-linecap': 'round',
      'stroke-dasharray': `${Math.max(0.001, valor) * c} ${c}`, transform: 'rotate(-90 60 60)' }, svg);
    s('text', { x: 60, y: 67, 'text-anchor': 'middle', 'font-size': 22, 'font-weight': 800, fill: C.texto, 'font-family': 'Inter, system-ui, sans-serif' }, svg,
      nf(valor < 0.1 && valor > 0 ? 1 : 0).format(valor * 100) + '%');
    return svg;
  }

  /* ---------- Minigráfico de línea ---------- */
  function sparkline(valores, color, etiquetas) {
    const w = 240, h = 40, p = 3;
    const svg = s('svg', { class: 'spark', viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none', 'aria-hidden': 'true' });
    if (valores.length < 2) return svg;
    const min = Math.min(...valores), max = Math.max(...valores);
    const x = (i) => p + (i / (valores.length - 1)) * (w - 2 * p);
    const y = (v) => h - p - ((v - min) / ((max - min) || 1)) * (h - 2 * p);
    const d = valores.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
    s('path', { d: d + `L${x(valores.length - 1)},${h}L${x(0)},${h}Z`, fill: color, opacity: 0.16 }, svg);
    s('path', { d, fill: 'none', stroke: color, 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke', 'stroke-linejoin': 'round' }, svg);
    if (etiquetas) {
      valores.forEach((v, i) => {
        const r = s('rect', { x: x(i) - (w / valores.length) / 2, y: 0, width: w / valores.length, height: h, fill: 'transparent' }, svg);
        r.addEventListener('mousemove', (ev) => mostrarTip(ev, etiquetas[i], [{ nombre: 'Siniestros', valor: n0(v) }]));
        r.addEventListener('mouseleave', ocultarTip);
      });
      svg.removeAttribute('aria-hidden');
    }
    return svg;
  }

  /* ---------- Mapa de calor del Valle de Aburrá ----------
   * Proyección equirectangular corregida por coseno de la latitud.
   * La densidad se estima con un núcleo gaussiano sobre una rejilla de
   * ~40 m y se pinta en un canvas que se inserta como imagen en el SVG. */
  function crearMapa(el, geo) {
    const munis = geo.municipios;
    const todos = munis.flatMap((m) => m.anillos.flat());
    const lon0 = Math.min(...todos.map((p) => p[0])), lon1 = Math.max(...todos.map((p) => p[0]));
    const lat0 = Math.min(...todos.map((p) => p[1])), lat1 = Math.max(...todos.map((p) => p[1]));
    const kx = Math.cos(((lat0 + lat1) / 2) * Math.PI / 180);
    const ESC = 1000;
    const px = (lon) => (lon - lon0) * kx * ESC;
    const py = (lat) => (lat1 - lat) * ESC;
    const W = px(lon1), H = py(lat0);
    const ruta = (anillos) => anillos.map((a) => a.map((p, i) => `${i ? 'L' : 'M'}${px(p[0]).toFixed(2)},${py(p[1]).toFixed(2)}`).join('') + 'Z').join('');

    // Rejilla de densidad sobre la caja de los puntos de Envigado
    const G = { lon0: -75.625, lon1: -75.535, lat0: 6.125, lat1: 6.205, paso: 0.0004 };
    G.nx = Math.round((G.lon1 - G.lon0) / G.paso); G.ny = Math.round((G.lat1 - G.lat0) / G.paso);
    const SIGMA = 4.5, RAD = 14;
    const nucleo = [];
    for (let dy = -RAD; dy <= RAD; dy++) for (let dx = -RAD; dx <= RAD; dx++) {
      const w = Math.exp(-(dx * dx + dy * dy) / (2 * SIGMA * SIGMA));
      if (w > 0.01) nucleo.push([dx, dy, w]);
    }
    const lienzoCalor = document.createElement('canvas');
    lienzoCalor.width = G.nx; lienzoCalor.height = G.ny;

    el.textContent = '';
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, class: 'lienzo-mapa', role: 'img', 'aria-label': 'Mapa de calor de siniestros en el Valle de Aburrá' }, el);
    const defs = s('defs', {}, svg);
    const clip = s('clipPath', { id: 'clip-valle' }, defs);
    const filtro = s('filter', { id: 'difuminar-calor', x: '-10%', y: '-10%', width: '120%', height: '120%' }, defs);
    s('feGaussianBlur', { stdDeviation: 0.9 }, filtro);
    munis.forEach((m) => s('path', { d: ruta(m.anillos) }, clip));
    const base = s('g', {}, svg);
    const capas = munis.map((m) => {
      const esEnv = m.nombre === 'Envigado';
      const p = s('path', { d: ruta(m.anillos), fill: esEnv ? '#ffffff' : '#f9fefd', stroke: C.t300, 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke', 'stroke-linejoin': 'round' }, base);
      p.addEventListener('mousemove', (ev) => { if (!enCalor(ev)) mostrarTip(ev, m.nombre, esEnv ? [{ nombre: 'Siniestros con coordenadas', valor: n0(estado.total) }] : [{ nombre: 'Sin datos en este proyecto' }]); });
      p.addEventListener('mouseleave', ocultarTip);
      return p;
    });
    const imagen = s('image', { x: px(G.lon0), y: py(G.lat1), width: px(G.lon1) - px(G.lon0), height: py(G.lat0) - py(G.lat1), preserveAspectRatio: 'none', 'pointer-events': 'none', filter: 'url(#difuminar-calor)' }, s('g', { 'clip-path': 'url(#clip-valle)' }, svg));
    const env = munis.find((m) => m.nombre === 'Envigado');
    s('path', { d: ruta(env.anillos), fill: 'none', stroke: C.t700, 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke', 'pointer-events': 'none', 'stroke-dasharray': '5 3' }, svg);
    const etiquetas = s('g', { 'pointer-events': 'none' }, svg);
    munis.forEach((m) => {
      const t = s('text', { x: px(m.centro[0]), y: py(m.centro[1]), 'text-anchor': 'middle', fill: m.nombre === 'Envigado' ? C.t800 : C.texto3, 'font-weight': m.nombre === 'Envigado' ? 700 : 500, 'font-family': 'Inter, system-ui, sans-serif', 'paint-order': 'stroke', stroke: '#fff', 'stroke-linejoin': 'round' }, etiquetas, m.nombre);
      t.dataset.nombre = m.nombre;
    });
    const sinDatos = s('text', { 'text-anchor': 'middle', fill: C.texto2, 'font-weight': 600, 'font-family': 'Inter, system-ui, sans-serif', visibility: 'hidden', 'paint-order': 'stroke', stroke: '#fff' }, svg, 'Sin coordenadas para estos filtros');

    // Zoom con botones y rueda; encuadres predefinidos
    const zoom = document.createElement('div'); zoom.className = 'mapa-zoom';
    zoom.innerHTML = '<button type="button" aria-label="Acercar">+</button><button type="button" aria-label="Alejar">−</button>';
    el.appendChild(zoom);

    const VISTAS = {
      valle: { x: 0, y: 0, w: W, h: H },
      envigado: (() => { const b = { x0: px(-75.635), x1: px(-75.535), y0: py(6.212), y1: py(6.124) }; return { x: b.x0, y: b.y0, w: b.x1 - b.x0, h: b.y1 - b.y0 }; })(),
    };
    let vb = { ...VISTAS.valle }, anim = null;
    // Ajusta el contenedor a la proporción del encuadre elegido
    // Unidades del SVG por píxel de pantalla (el SVG usa 'meet')
    const upp = () => Math.max(vb.w / Math.max(el.clientWidth, 1), vb.h / Math.max(el.clientHeight, 1));
    function aSvg(ev) {
      const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY;
      return p.matrixTransform(svg.getScreenCTM().inverse());
    }
    function aplicar() {
      svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
      const u = upp(); // tamaño de letra constante en pantalla
      etiquetas.querySelectorAll('text').forEach((t) => { t.setAttribute('font-size', 12 * u); t.setAttribute('stroke-width', 3 * u); });
      sinDatos.setAttribute('x', vb.x + vb.w / 2); sinDatos.setAttribute('y', vb.y + vb.h / 2);
      sinDatos.setAttribute('font-size', 14 * u); sinDatos.setAttribute('stroke-width', 4 * u);
    }
    function ir(dest, ms = 450) {
      cancelAnimationFrame(anim);
      const ini = { ...vb }, t0 = performance.now();
      const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
      const paso = (t) => {
        const k = reducir ? 1 : Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
        ['x', 'y', 'w', 'h'].forEach((c) => { vb[c] = ini[c] + (dest[c] - ini[c]) * e; });
        aplicar();
        if (k < 1) anim = requestAnimationFrame(paso);
      };
      anim = requestAnimationFrame(paso);
    }
    function zoomEn(f, cx, cy) {
      const w = Math.min(W, Math.max(W / 14, vb.w * f)), h = w * (vb.h / vb.w);
      cx = cx ?? vb.x + vb.w / 2; cy = cy ?? vb.y + vb.h / 2;
      ir({ x: cx - (cx - vb.x) * (w / vb.w), y: cy - (cy - vb.y) * (h / vb.h), w, h }, 220);
    }
    zoom.children[0].addEventListener('click', () => zoomEn(0.66));
    zoom.children[1].addEventListener('click', () => zoomEn(1.5));
    svg.addEventListener('wheel', (ev) => {
      ev.preventDefault();
      const p = aSvg(ev);
      zoomEn(ev.deltaY < 0 ? 0.8 : 1.25, p.x, p.y);
    }, { passive: false });
    // Arrastrar para desplazar
    let arrastre = null;
    svg.addEventListener('pointerdown', (ev) => { arrastre = { x: ev.clientX, y: ev.clientY, vb: { ...vb }, u: upp() }; svg.setPointerCapture(ev.pointerId); svg.style.cursor = 'grabbing'; });
    svg.addEventListener('pointermove', (ev) => {
      if (!arrastre) return;
      vb.x = arrastre.vb.x - (ev.clientX - arrastre.x) * arrastre.u;
      vb.y = arrastre.vb.y - (ev.clientY - arrastre.y) * arrastre.u;
      aplicar();
    });
    const soltar = () => { arrastre = null; svg.style.cursor = ''; };
    svg.addEventListener('pointerup', soltar); svg.addEventListener('pointercancel', soltar);

    const estado = { cuentas: null, total: 0 };
    // Tooltip sobre la zona caliente: siniestros a ~120 m del cursor
    function enCalor(ev) {
      if (!estado.cuentas) return false;
      const q = aSvg(ev), sx = q.x, sy = q.y;
      const lon = sx / (kx * ESC) + lon0, lat = lat1 - sy / ESC;
      const i = Math.floor((lon - G.lon0) / G.paso), j = Math.floor((G.lat1 - lat) / G.paso);
      if (i < 0 || j < 0 || i >= G.nx || j >= G.ny) return false;
      let n = 0;
      for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) {
        const a = i + dx, b = j + dy;
        if (a >= 0 && b >= 0 && a < G.nx && b < G.ny) n += estado.cuentas[b * G.nx + a];
      }
      if (!n) return false;
      mostrarTip(ev, 'Envigado', [{ nombre: 'Siniestros a ~150 m', valor: n0(n) }, { nombre: 'Total en el mapa', valor: n0(estado.total) }]);
      return true;
    }
    svg.addEventListener('mousemove', (ev) => { if (!arrastre) enCalor(ev); });

    function actualizar(puntos) {
      const cuentas = new Float32Array(G.nx * G.ny);
      let total = 0;
      puntos.forEach(([lon, lat]) => {
        const i = Math.floor((lon - G.lon0) / G.paso), j = Math.floor((G.lat1 - lat) / G.paso);
        if (i < 0 || j < 0 || i >= G.nx || j >= G.ny) return;
        cuentas[j * G.nx + i] += 1; total++;
      });
      const dens = new Float32Array(G.nx * G.ny);
      let max = 0;
      for (let j = 0; j < G.ny; j++) for (let i = 0; i < G.nx; i++) {
        const c = cuentas[j * G.nx + i];
        if (!c) continue;
        for (const [dx, dy, w] of nucleo) {
          const a = i + dx, b = j + dy;
          if (a < 0 || b < 0 || a >= G.nx || b >= G.ny) continue;
          const k = b * G.nx + a; dens[k] += c * w;
          if (dens[k] > max) max = dens[k];
        }
      }
      const ctx = lienzoCalor.getContext('2d');
      const img = ctx.createImageData(G.nx, G.ny);
      for (let k = 0; k < dens.length; k++) {
        if (!dens[k]) continue;
        const t = Math.sqrt(dens[k] / max);
        if (t < 0.015) continue;
        const [r, g, b] = calorRgb(0.08 + 0.92 * t);
        img.data[k * 4] = r; img.data[k * 4 + 1] = g; img.data[k * 4 + 2] = b;
        img.data[k * 4 + 3] = Math.round(255 * 0.9 * Math.min(1, Math.pow(t, 0.75) * 1.15));
      }
      ctx.putImageData(img, 0, 0);
      imagen.setAttribute('href', lienzoCalor.toDataURL());
      estado.cuentas = cuentas; estado.total = total;
      sinDatos.setAttribute('visibility', total ? 'hidden' : 'visible');
      return { total, max };
    }

    aplicar();
    return { actualizar, vista: (nombre) => ir(VISTAS[nombre]), relabel: aplicar, capas };
  }

  root.Graficos = { C, n0, nf, rampa, rampaCss, calorCss, columnas, lineas, matriz, barrasH, anillo, sparkline, crearMapa, mostrarTip, ocultarTip, vacio };
})(window);
