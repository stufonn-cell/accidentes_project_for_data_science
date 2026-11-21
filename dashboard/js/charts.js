/* Graficos SVG sin dependencias para el tablero: barras verticales, barras
 * horizontales, barras agrupadas, barras divergentes y mapa de calor.
 * Regla de color: lo que sostiene el mensaje va en amarillo; el resto en gris.
 * Todos los valores quedan escritos en la grafica; el tooltip solo amplia. */
(function (root) {
  'use strict';

  const C = {
    acento: '#f2b90f', acentoOscuro: '#8a6300', acentoClaro: '#fdf3cf',
    neutro: '#b3b7bd', neutroClaro: '#d9dce0', pista: '#eef0f2', oscuro: '#3a3e45',
    texto: '#1f2226', texto2: '#4a4f57', texto3: '#6b7078',
    rejilla: '#eceef0', base: '#a9adb3', fondo: '#ffffff',
  };
  const NS = 'http://www.w3.org/2000/svg';
  const FUENTE = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  const nf = (d) => new Intl.NumberFormat('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d });
  const n0 = (v) => nf(0).format(v);
  const pct = (v, d = 0) => nf(d).format(v * 100) + ' %';
  const HALO = { 'paint-order': 'stroke', stroke: '#fff', 'stroke-width': 4, 'stroke-linejoin': 'round' };

  function s(tag, attrs, parent, texto) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) n.setAttribute(k, attrs[k]);
    if (texto !== undefined) n.textContent = texto;
    if (parent) parent.appendChild(n);
    return n;
  }
  function t(parent, x, y, texto, extra) {
    return s('text', Object.assign({ x, y, 'font-size': 12, fill: C.texto3, 'font-family': FUENTE }, extra || {}), parent, texto);
  }
  /* Ancho de un texto sin tocar el DOM, para decidir donde cabe cada rotulo */
  const ctx = document.createElement('canvas').getContext('2d');
  function medir(texto, tam = 12, peso = 400) { ctx.font = `${peso} ${tam}px ${FUENTE}`; return ctx.measureText(String(texto)).width; }

  const ancho = (el) => Math.max(Math.floor(el.clientWidth) || 560, 280);
  function lienzo(el, alto, m, descripcion) {
    el.textContent = '';
    const w = ancho(el);
    const svg = s('svg', { viewBox: `0 0 ${w} ${alto}`, width: w, height: alto, role: 'img', 'aria-label': descripcion }, el);
    return { svg, w, h: alto, iw: w - m.l - m.r, ih: alto - m.t - m.b, m };
  }
  function vacio(el, texto) {
    el.textContent = '';
    const d = document.createElement('div');
    d.className = 'vacio'; d.textContent = texto || 'Sin siniestros con estos filtros';
    el.appendChild(d);
  }

  /* Marcas "redondas" del eje entre min y max */
  function marcas(min, max, n) {
    const rango = (max - min) || 1;
    const bruto = rango / n, p = Math.pow(10, Math.floor(Math.log10(bruto)));
    const paso = [1, 2, 2.5, 5, 10].map((k) => k * p).find((k) => k >= bruto);
    const a = Math.floor(min / paso) * paso, b = Math.ceil(max / paso - 1e-9) * paso;
    const out = [];
    for (let v = a; v <= b + paso / 2; v += paso) out.push(Math.round(v * 1e6) / 1e6);
    return out;
  }

  /* Escala de calor para el mapa de carga de trabajo: de amarillo claro a rojo oscuro */
  function hexRgb(h) { return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)); }
  function rampaDe(colores) {
    const rgb = colores.map(hexRgb);
    const f = (x) => {
      x = Math.max(0, Math.min(1, x)) * (rgb.length - 1);
      const i = Math.min(Math.floor(x), rgb.length - 2), k = x - i;
      return [0, 1, 2].map((j) => Math.round(rgb[i][j] + (rgb[i + 1][j] - rgb[i][j]) * k));
    };
    return { rgb: f, css: (x) => `rgb(${f(x).join(',')})`, gradiente: () => `linear-gradient(90deg, ${colores.join(',')})` };
  }
  const CALOR = rampaDe(['#fff4cc', '#fdd36a', '#f59a23', '#d9480f', '#8f1d0b']);
  /* Texto blanco o casi negro segun lo oscuro del fondo */
  function textoSobre(rgb) {
    const [r, g, b] = rgb.map((c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.28 ? '#ffffff' : C.texto;
  }

  /* ---------- Tooltip compartido ---------- */
  const tip = () => document.getElementById('tip');
  function mostrarTip(ev, titulo, filas) {
    const el = tip();
    el.textContent = '';
    const b = document.createElement('b'); b.textContent = titulo; el.appendChild(b);
    (filas || []).forEach((f) => {
      const d = document.createElement('div');
      d.appendChild(document.createTextNode(f.nombre));
      if (f.valor !== undefined) { const sp = document.createElement('span'); sp.textContent = f.valor; d.appendChild(sp); }
      el.appendChild(d);
    });
    el.hidden = false;
    const r = el.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
    el.style.left = Math.max(8, x) + 'px'; el.style.top = Math.max(8, y) + 'px';
  }
  function ocultarTip() { tip().hidden = true; }
  function conTip(nodo, titulo, filas) {
    nodo.addEventListener('mousemove', (ev) => mostrarTip(ev, titulo(), filas()));
    nodo.addEventListener('mouseleave', ocultarTip);
  }

  /* Leyenda en una o varias lineas: primero se planea (para saber su alto) y luego se dibuja */
  function planLeyenda(items, x, anchoMax) {
    let lx = x, linea = 0;
    const pos = items.map((it) => {
      const tw = medir(it.texto, 12.5, 500);
      if (lx > x && lx + 18 + tw > x + anchoMax) { lx = x; linea++; }
      const p = { x: lx, linea, it };
      lx += 18 + tw + 22;
      return p;
    });
    return { pos, alto: (linea + 1) * 20 };
  }
  function dibujarLeyenda(g, plan, y) {
    plan.pos.forEach(({ x, linea, it }) => {
      const yy = y + linea * 20;
      s('rect', { x, y: yy - 10, width: 12, height: 12, rx: 3, fill: it.color }, g);
      t(g, x + 18, yy, it.texto, { 'font-size': 12.5, 'font-weight': 500, fill: C.texto2 });
    });
  }

  function ejeY(g, ticks, y, x0, x1, fmt) {
    ticks.forEach((v) => {
      if (v !== 0) s('line', { x1: x0, x2: x1, y1: y(v), y2: y(v), stroke: C.rejilla }, g);
      t(g, x0 - 8, y(v) + 4, fmt(v), { 'text-anchor': 'end', 'font-size': 11.5 });
    });
  }
  /* Rectangulo con el extremo de datos redondeado y la base recta */
  function barraSup(x, y, w, h, r) {
    r = Math.min(r, w / 2, h); if (h <= 0) return '';
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  function barraDer(x, y, w, h, r) {
    r = Math.min(r, h / 2, w); if (w <= 0) return '';
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }
  function barraIzq(x, y, w, h, r) {
    r = Math.min(r, h / 2, w); if (w <= 0) return '';
    return `M${x + w},${y}H${x + r}Q${x},${y} ${x},${y + r}V${y + h - r}Q${x},${y + h} ${x + r},${y + h}H${x + w}Z`;
  }

  /* ---------- Barras verticales (una serie, con un segmento opcional encima) ----------
   * o: { valores, cats | grupos:[{desde, hasta, texto}], encima, colorEncima, leyenda:[{color, texto}],
   *      acento(i), colorDe(i), etiquetar(i), fmt, fmtEje, sinEje, ymax, alto, extra, xTitulo,
   *      referencia:{desde, hasta, valor, texto}, anotacion:{i, valor, lineas:[...]}, tip(i), descripcion } */
  function barrasV(el, o) {
    const n = o.valores.length, encima = o.encima || [];
    const tot = o.valores.map((v, i) => v + (encima[i] || 0));
    if (!n || !tot.some((v) => v > 0)) return vacio(el);
    const fmt = o.fmt || n0, w = ancho(el);
    const ml = o.sinEje ? 4 : 46, mr = 6;
    const ley = o.leyenda ? planLeyenda(o.leyenda, o.sinEje ? 0 : 4, w - 8) : null;
    const mt = (ley ? ley.alto + 6 : 0) + 20;
    const mb = 26 + (o.xTitulo ? 18 : 0);
    const alto = (o.alto || 260) + (o.extra || 0);
    const L = lienzo(el, alto, { t: mt, r: mr, b: mb, l: ml }, o.descripcion);
    const g = s('g', {}, L.svg);
    if (ley) dibujarLeyenda(g, ley, 14);
    let ymax, ticks = null;
    if (o.sinEje) ymax = (o.ymax || Math.max(...tot)) * 1.1;
    else { ticks = marcas(0, o.ymax || Math.max(...tot), 4); ymax = ticks[ticks.length - 1]; }
    const y = (v) => L.m.t + L.ih - (v / ymax) * L.ih;
    const banda = L.iw / n, bw = Math.min(110, banda * 0.66); // espacio entre barras = la mitad del ancho
    const cx = (i) => L.m.l + banda * (i + 0.5);
    if (ticks) ejeY(g, ticks, y, L.m.l, L.w - L.m.r, o.fmtEje || fmt);
    const r = bw > 14 ? 4 : 1.5;
    o.valores.forEach((v, i) => {
      const color = o.colorDe ? o.colorDe(i) : (o.acento && o.acento(i) ? C.acento : C.neutro);
      const e = encima[i] || 0, x0 = cx(i) - bw / 2;
      if (e > 0) {
        // Base recta y, encima, el segmento con el extremo redondeado; 1 px de fondo entre los dos
        s('rect', { x: x0, y: y(v), width: bw, height: Math.max(0, y(0) - y(v)), fill: color }, g);
        s('path', { d: barraSup(x0, y(v + e), bw, Math.max(0, y(v) - y(v + e) - 1), r), fill: o.colorEncima || C.acento }, g);
      } else if (v > 0) {
        s('path', { d: barraSup(x0, y(v), bw, Math.max(1, y(0) - y(v)), r), fill: color }, g);
      }
      if (o.etiquetar && o.etiquetar(i)) {
        const ac = o.acento && o.acento(i);
        t(g, cx(i), y(tot[i]) - 7, fmt(tot[i]), { 'text-anchor': 'middle', 'font-size': 13, 'font-weight': ac ? 750 : 600, fill: C.texto });
      }
      if (o.tip) {
        const hit = s('rect', { x: cx(i) - banda / 2, y: L.m.t, width: banda, height: L.ih, fill: 'transparent' }, g);
        conTip(hit, () => o.tip(i).titulo, () => o.tip(i).filas);
      }
    });
    s('line', { x1: L.m.l, x2: L.w - L.m.r, y1: y(0), y2: y(0), stroke: C.base }, g);
    // Rotulos del eje x: por grupos (un rotulo centrado por anio) o uno por barra
    if (o.grupos) {
      o.grupos.forEach((gr) => {
        const x0 = L.m.l + banda * gr.desde, x1 = L.m.l + banda * (gr.hasta + 1);
        if (gr.desde > 0) s('line', { x1: x0, x2: x0, y1: y(0), y2: y(0) + 7, stroke: C.base }, g);
        t(g, (x0 + x1) / 2, y(0) + 18, gr.texto, { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 600, fill: C.texto2 });
      });
    } else {
      o.cats.forEach((c, i) => t(g, cx(i), y(0) + 18, c, { 'text-anchor': 'middle', 'font-size': 12.5, 'font-weight': 500, fill: C.texto2 }));
    }
    if (o.xTitulo) t(g, L.m.l + L.iw / 2, alto - 4, o.xTitulo, { 'text-anchor': 'middle', 'font-size': 12, fill: C.texto3 });
    // Referencia: el promedio de un periodo, como una linea fina sobre sus barras
    if (o.referencia) {
      const R = o.referencia, x0 = cx(R.desde) - bw / 2, x1 = cx(R.hasta) + bw / 2, yv = y(R.valor);
      s('line', { x1: x0, x2: x1, y1: yv, y2: yv, stroke: C.oscuro, 'stroke-width': 1.5, 'pointer-events': 'none' }, g);
      t(g, x1 + 6, yv + 4, R.texto, Object.assign({ 'font-size': 12, 'font-weight': 700, fill: C.texto, 'pointer-events': 'none' }, HALO));
    }
    // Anotacion: una linea corta desde la barra y un texto breve al lado
    if (o.anotacion) {
      const A = o.anotacion, xa = cx(A.i), ya = y(A.valor), yb = y(tot[A.i]) - 4;
      s('line', { x1: xa, x2: xa, y1: yb, y2: ya - 4, stroke: C.oscuro, 'stroke-width': 1, 'pointer-events': 'none' }, g);
      s('circle', { cx: xa, cy: yb, r: 2.5, fill: C.oscuro, 'pointer-events': 'none' }, g);
      A.lineas.forEach((l, k) => t(g, xa + 7, ya + 4 + k * 16, l, Object.assign({ 'font-size': 12.5, 'font-weight': k === 0 ? 700 : 500, fill: k === 0 ? C.texto : C.texto2, 'pointer-events': 'none' }, HALO)));
    }
  }

  /* ---------- Barras horizontales (una serie) ----------
   * o: { items:[{clave, nombre, valor}], acento(d), fmt, xmax, referencia:{valor, texto}, pista (barra de fondo hasta xmax),
   *      nota(d), onClic(clave), activo, fila, extra, descripcion, tip(d) } */
  function barrasH(el, o) {
    if (!o.items.length) return vacio(el);
    const n = o.items.length, w = ancho(el);
    const fila = Math.min(44, (o.fila || 30) + (o.extra || 0) / n);
    const fmt = o.fmt || n0;
    const etiqueta = Math.min(Math.max(...o.items.map((d) => medir(d.nombre, 13, 500))) + 14, 180, w * 0.36);
    // A la derecha: el valor (y la nota) de la barra mas larga, medidos
    const textoDer = (d) => fmt(d.valor) + (o.nota ? '  ' + o.nota(d) : '');
    const derecha = o.pista ? Math.max(...o.items.map((d) => medir(textoDer(d), 13, 700))) + 14 : 12;
    const arriba = o.referencia ? 22 : 4;
    const alto = n * fila + arriba + 4;
    const L = lienzo(el, alto, { t: arriba, r: derecha, b: 4, l: etiqueta }, o.descripcion);
    const max = o.xmax || Math.max(...o.items.map((d) => d.valor), 1e-9);
    // Sin pista se deja espacio para el valor al final de la barra mas larga
    const espacio = o.pista ? 0 : Math.max(...o.items.map((d) => medir(textoDer(d), 13, 700))) + 12;
    const x = (v) => etiqueta + (v / max) * (L.iw - espacio);
    const g = s('g', {}, L.svg);
    const haySel = o.activo !== null && o.activo !== undefined;
    // La referencia va primero, detras de barras y rotulos, para no tapar ningun valor
    if (o.referencia) {
      const xr = x(o.referencia.valor);
      s('line', { x1: xr, x2: xr, y1: arriba - 4, y2: arriba + n * fila, stroke: C.oscuro, 'stroke-width': 1.25 }, g);
      const tw = medir(o.referencia.texto, 12, 600);
      const ancla = xr + tw / 2 > L.w - 2 ? 'end' : (xr - tw / 2 < etiqueta ? 'start' : 'middle');
      t(g, ancla === 'end' ? xr + 4 : (ancla === 'start' ? xr - 4 : xr), 13, o.referencia.texto, { 'text-anchor': ancla, 'font-size': 12, 'font-weight': 600, fill: C.texto2 });
    }
    o.items.forEach((d, i) => {
      const yc = arriba + i * fila + fila / 2, bh = fila * 0.64;
      const gi = s('g', { 'data-clic': o.onClic ? 1 : null }, g);
      s('rect', { x: 0, y: yc - fila / 2, width: L.w, height: fila, fill: 'transparent' }, gi);
      const sel = haySel && o.activo === d.clave, apagado = haySel && !sel;
      t(gi, etiqueta - 10, yc + 4.5, d.nombre, { 'text-anchor': 'end', 'font-size': 13, fill: C.texto, 'font-weight': sel ? 750 : 500 });
      if (o.pista) s('path', { d: barraDer(etiqueta, yc - bh / 2, x(max) - etiqueta, bh, 4), fill: C.pista }, gi);
      const ac = o.acento && o.acento(d);
      s('path', { d: barraDer(etiqueta, yc - bh / 2, Math.max(2, x(d.valor) - etiqueta), bh, 4), fill: o.colorDe ? o.colorDe(d) : (ac ? C.acento : C.neutro), opacity: apagado ? 0.35 : 1 }, gi);
      if (sel) s('path', { d: barraDer(etiqueta - 1, yc - bh / 2 - 1.5, Math.max(2, x(d.valor) - etiqueta) + 2.5, bh + 3, 5), fill: 'none', stroke: C.texto, 'stroke-width': 1.5 }, gi);
      const xv = o.pista ? x(max) + 10 : x(d.valor) + 7;
      const valor = t(gi, xv, yc + 4.5, fmt(d.valor), { 'font-size': 13, 'font-weight': ac || sel ? 750 : 600, fill: C.texto });
      if (o.nota) t(gi, xv + medir(fmt(d.valor), 13, 700) + 6, yc + 4.5, o.nota(d), { 'font-size': 12, fill: C.texto3 });
      if (o.tip) conTip(gi, () => d.nombre, () => o.tip(d));
      if (o.onClic) gi.addEventListener('click', () => { ocultarTip(); o.onClic(d.clave); });
      void valor;
    });
  }

  /* ---------- Barras agrupadas: dos o tres barras por grupo, una junto a la otra ----------
   * La forma mas familiar para comparar antes y despues. Valor encima de cada barra;
   * debajo, el nombre de cada barra (o una leyenda arriba), el del grupo y una nota.
   * o: { grupos:[{nombre, nota, valores:[...]}], series:[...], etiquetasBarra:true|false, colorDe(gi, k),
   *      fuerte(gi, k), fmt, alto, extra, xTitulo, tip(grupo, k)->filas, descripcion } */
  function barrasAgrupadas(el, o) {
    if (!o.grupos.length) return vacio(el, 'Sin datos');
    const w = ancho(el), fmt = o.fmt || n0, nb = o.series.length;
    const colorDe = o.colorDe || ((gi, k) => (k === nb - 1 ? C.acento : C.neutroClaro));
    const ley = o.etiquetasBarra ? null : planLeyenda(o.series.map((nombre, k) => ({ texto: nombre, color: colorDe(0, k) })), 0, w);
    const hayNota = o.grupos.some((gr) => gr.nota);
    const mt = (ley ? ley.alto + 8 : 0) + 24;
    const mb = (o.etiquetasBarra ? 20 : 0) + 24 + (hayNota ? 18 : 0) + (o.xTitulo ? 18 : 0);
    const alto = (o.alto || 260) + (o.extra || 0);
    const L = lienzo(el, alto, { t: mt, r: 4, b: mb, l: 4 }, o.descripcion);
    const g = s('g', {}, L.svg);
    if (ley) dibujarLeyenda(g, ley, 14);
    const max = Math.max(...o.grupos.flatMap((gr) => gr.valores), 1e-9);
    const y = (v) => L.m.t + L.ih - (v / max) * L.ih;
    const ng = o.grupos.length, sep = 3;
    // Barras de un grupo casi juntas (proximidad); entre grupos, un ancho de barra.
    // Si el ancho maximo limita, los grupos se juntan en el centro en vez de separarse mas.
    const bw = Math.min(96, (L.iw / ng - sep * (nb - 1)) / (nb + 1));
    const banda = nb * bw + sep * (nb - 1) + bw, desfase = (L.iw - ng * banda) / 2;
    const y0 = y(0);
    o.grupos.forEach((gr, gi) => {
      const cx = L.m.l + desfase + banda * (gi + 0.5);
      const x0 = cx - (nb * bw + (nb - 1) * sep) / 2;
      gr.valores.forEach((v, k) => {
        const x = x0 + k * (bw + sep), fuerte = o.fuerte ? o.fuerte(gi, k) : k === nb - 1;
        const gb = s('g', {}, g);
        s('rect', { x: x - sep / 2, y: L.m.t, width: bw + sep, height: L.ih, fill: 'transparent' }, gb);
        s('path', { d: barraSup(x, Math.min(y(v), y0 - 2), bw, Math.max(2, y0 - y(v)), 4), fill: colorDe(gi, k) }, gb);
        t(gb, x + bw / 2, Math.min(y(v), y0 - 2) - 8, fmt(v), { 'text-anchor': 'middle', 'font-size': 14, 'font-weight': fuerte ? 750 : 600, fill: C.texto });
        if (o.etiquetasBarra) t(gb, x + bw / 2, y0 + 17, o.series[k], { 'text-anchor': 'middle', 'font-size': 12, fill: C.texto3 });
        if (o.tip) conTip(gb, () => `${gr.nombre} · ${o.series[k]}`, () => o.tip(gr, k));
      });
      const yn = y0 + (o.etiquetasBarra ? 38 : 19);
      t(g, cx, yn, gr.nombre, { 'text-anchor': 'middle', 'font-size': 13.5, 'font-weight': 700, fill: C.texto });
      if (gr.nota) t(g, cx, yn + 18, gr.nota, { 'text-anchor': 'middle', 'font-size': 12.5, 'font-weight': 600, fill: C.texto2 });
    });
    s('line', { x1: L.m.l, x2: L.w - L.m.r, y1: y0, y2: y0, stroke: C.base }, g);
    if (o.xTitulo) t(g, L.m.l + L.iw / 2, alto - 4, o.xTitulo, { 'text-anchor': 'middle', 'font-size': 12, fill: C.texto3 });
  }

  /* ---------- Barras divergentes desde cero ----------
   * Lo que esta por encima de lo esperado va a la derecha en amarillo; lo de abajo, a la izquierda en gris.
   * A la derecha, una columna con el detalle de cada fila, para leerlo sin pasar el mouse.
   * o: { items:[{nombre, valor}], izquierda, derecha, fmt, detalle(d), tituloDetalle, tip(d), extra, descripcion } */
  function barrasDiv(el, o) {
    if (!o.items.length) return vacio(el, 'Sin datos');
    const n = o.items.length, w = ancho(el);
    const fila = Math.min(40, 28 + (o.extra || 0) / n);
    const etiqueta = Math.min(Math.max(...o.items.map((d) => medir(d.nombre, 13, 500))) + 16, 200);
    const det = o.detalle ? Math.min(Math.max(...o.items.map((d) => medir(o.detalle(d), 12.5, 400)), medir(o.tituloDetalle || '', 12, 600)) + 24, w * 0.32) : 0;
    const alto = n * fila + 30;
    const L = lienzo(el, alto, { t: 24, r: det, b: 6, l: etiqueta }, o.descripcion);
    const max = Math.max(...o.items.map((d) => Math.abs(d.valor)), 1e-9);
    const fmt = o.fmt || ((v) => nf(1).format(v));
    const hueco = Math.max(...o.items.map((d) => medir(fmt(d.valor), 13, 700))) + 12;
    const x0 = etiqueta + L.iw / 2, x = (v) => x0 + (v / max) * (L.iw / 2 - hueco);
    const g = s('g', {}, L.svg);
    t(g, x0 - 8, 13, o.izquierda, { 'text-anchor': 'end', 'font-size': 12, 'font-weight': 600, fill: C.texto3 });
    t(g, x0 + 8, 13, o.derecha, { 'font-size': 12, 'font-weight': 600, fill: C.texto });
    if (det && o.tituloDetalle) t(g, L.w - det + 18, 13, o.tituloDetalle, { 'font-size': 12, 'font-weight': 600, fill: C.texto3 });
    o.items.forEach((d, i) => {
      const yc = L.m.t + i * fila + fila / 2, bh = fila * 0.64;
      const gi = s('g', {}, g);
      s('rect', { x: 0, y: yc - fila / 2, width: L.w, height: fila, fill: 'transparent' }, gi);
      if (i % 2 === 0) s('rect', { x: 0, y: yc - fila / 2, width: L.w, height: fila, fill: '#f7f8f9', rx: 4 }, gi);
      t(gi, etiqueta - 10, yc + 4.5, d.nombre, { 'text-anchor': 'end', 'font-size': 13, fill: C.texto, 'font-weight': d.valor > 0 ? 600 : 500 });
      const wv = Math.abs(x(d.valor) - x0);
      s('path', { d: d.valor >= 0 ? barraDer(x0, yc - bh / 2, wv, bh, 4) : barraIzq(x0 - wv, yc - bh / 2, wv, bh, 4), fill: d.valor > 0 ? C.acento : C.neutro }, gi);
      t(gi, x(d.valor) + (d.valor >= 0 ? 7 : -7), yc + 4.5, fmt(d.valor), { 'text-anchor': d.valor >= 0 ? 'start' : 'end', 'font-size': 13, 'font-weight': d.valor > 0 ? 750 : 600, fill: C.texto });
      if (det) t(gi, L.w - det + 18, yc + 4.5, o.detalle(d), { 'font-size': 12.5, fill: C.texto2 });
      if (o.tip) conTip(gi, () => d.nombre, () => o.tip(d));
    });
    s('line', { x1: x0, x2: x0, y1: L.m.t - 4, y2: L.m.t + n * fila, stroke: C.oscuro, 'stroke-width': 1.5 }, g);
  }

  /* ---------- Mapa de calor: filas x columnas, con el numero en cada celda ----------
   * o: { filas, columnas, columnasPartidas:[[l1, l2]], intensidad(i, j)->0..1|null, textoDe(i, j),
   *      totales:{titulo, textos:[...]}, marcarFila, marcarColumna, tip(i, j)->{titulo, filas}, onClic(i, j), descripcion } */
  function matriz(el, o) {
    const nfil = o.filas.length, nc = o.columnas.length;
    const w = ancho(el);
    const ml = Math.min(Math.max(...o.filas.map((f) => medir(f, 13, 600))) + 14, 170);
    const mr = o.totales ? Math.max(70, medir(o.totales.titulo, 12, 700) + 18) : 0;
    const cw = (w - ml - mr) / nc;
    // Encabezados de columna arriba; si un nombre no cabe, se parte en dos lineas
    const partir = o.columnas.some((c) => medir(c, 12, 600) > cw - 6);
    const mt = partir ? 40 : 26, ch = o.altoFila || 30, gap = 2;
    const alto = mt + nfil * ch + 4;
    const L = lienzo(el, alto, { t: mt, r: mr, b: 4, l: ml }, o.descripcion);
    const g = s('g', {}, L.svg);
    o.columnas.forEach((c, j) => {
      const xc = ml + j * cw + cw / 2, sel = o.marcarColumna === j;
      const est = { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': sel ? 750 : 600, fill: sel ? C.texto : C.texto2 };
      if (partir && medir(c, 12, 600) > cw - 6 && o.columnasPartidas && o.columnasPartidas[j]) {
        t(g, xc, mt - 22, o.columnasPartidas[j][0], est); t(g, xc, mt - 8, o.columnasPartidas[j][1], est);
      } else t(g, xc, mt - 8, c, est);
    });
    if (o.totales) t(g, w - mr / 2, mt - 8, o.totales.titulo, { 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: C.texto });
    o.filas.forEach((f, i) => {
      const yc = mt + i * ch + ch / 2, selF = o.marcarFila === i;
      t(g, ml - 9, yc + 4.5, f, { 'text-anchor': 'end', 'font-size': 13, 'font-weight': selF ? 750 : 500, fill: C.texto });
      o.columnas.forEach((c, j) => {
        const v = o.intensidad(i, j);
        const fill = v === null ? '#ffffff' : CALOR.css(v);
        const gc = s('g', { 'data-clic': o.onClic ? 1 : null }, g);
        s('rect', { x: ml + j * cw + gap / 2, y: mt + i * ch + gap / 2, width: cw - gap, height: ch - gap, rx: 3, fill, stroke: v === null ? C.rejilla : null }, gc);
        const txt = o.textoDe(i, j);
        if (txt) t(gc, ml + j * cw + cw / 2, yc + 4.5, txt, { 'text-anchor': 'middle', 'font-size': 12.5, 'font-weight': 600, fill: v === null ? C.texto3 : textoSobre(CALOR.rgb(v)), 'pointer-events': 'none' });
        if (o.tip) conTip(gc, () => o.tip(i, j).titulo, () => o.tip(i, j).filas);
        if (o.onClic) gc.addEventListener('click', () => { ocultarTip(); o.onClic(i, j); });
      });
      if (o.totales) t(g, w - mr / 2, yc + 4.5, o.totales.textos[i], { 'text-anchor': 'middle', 'font-size': 12.5, 'font-weight': 700, fill: C.texto });
    });
    // El filtro activo se marca con un borde, sin cambiar los colores de la escala
    if (o.marcarFila !== null && o.marcarFila !== undefined && o.marcarFila >= 0) {
      s('rect', { x: 1, y: mt + o.marcarFila * ch, width: w - 2, height: ch, rx: 5, fill: 'none', stroke: C.texto, 'stroke-width': 1.75, 'pointer-events': 'none' }, g);
    }
    if (o.marcarColumna !== null && o.marcarColumna !== undefined && o.marcarColumna >= 0) {
      s('rect', { x: ml + o.marcarColumna * cw, y: 1, width: cw, height: alto - 3, rx: 5, fill: 'none', stroke: C.texto, 'stroke-width': 1.75, 'pointer-events': 'none' }, g);
    }
  }

  root.Graficos = { C, n0, nf, pct, CALOR, medir, barrasV, barrasH, barrasAgrupadas, barrasDiv, matriz, mostrarTip, ocultarTip, vacio };
})(window);
