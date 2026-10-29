/* Lógica pura de la línea de tiempo por piezas (sin DOM). Se usa en el navegador como `PZ` y en pruebas con Node.
 *
 * Una pieza: {id, tipo: video|audio|imagen|texto, fuente: clip|medio|texto, carril: "V1".."V8" | "A1".."A8",
 *   t (inicio en la salida), desde (inicio en la fuente), dur (en la salida), velocidad, enlace, ...}.
 * Las funciones que cambian la lista devuelven la lista nueva; las demás modifican las piezas en el sitio. */
(function (raiz) {
  "use strict";
  const MIN_DUR = 0.1;           // un trozo más corto que esto no se crea al dividir
  const DUR_MIN_PIEZA = 0.05;    // por debajo de esto una pieza se descarta
  const EPS = 1e-6;
  const MAX_DURACION = 1800;
  const MAX_CARRILES = 8;
  const clonar = o => JSON.parse(JSON.stringify(o));
  const redondear = x => Math.round(x * 1000) / 1000;
  const fin = p => p.t + p.dur;
  const vel = p => p.velocidad || 1;
  const consumo = p => p.dur * vel(p);
  const familia = c => c[0];
  const numero = c => +c.slice(1);
  const esMediaConFuente = p => p.tipo === "video" || p.tipo === "audio";
  const total = P => P.reduce((m, p) => Math.max(m, fin(p)), 0);
  const enCarril = (P, c) => P.filter(p => p.carril === c).sort((a, b) => a.t - b.t);
  const grupo = (P, p) => (p.enlace ? P.filter(q => q.enlace === p.enlace) : [p]);

  function nuevoId(P) {
    const usados = new Set((P || []).map(p => p.id));
    for (;;) { const id = "p" + Math.random().toString(36).slice(2, 8); if (!usados.has(id)) return id; }
  }
  function nuevoEnlace() { return "e" + Math.random().toString(36).slice(2, 8); }

  function piezaBase(extra) {
    return Object.assign({
      id: "", tipo: "video", fuente: "medio", archivo: "", carril: "V1", t: 0, desde: 0, dur: 1, velocidad: 1, volumen: 1,
      fundido_in: 0, fundido_out: 0, opacidad: 1, zoom: 1, pos_x: 0, pos_y: 0, enlace: "", modo: "cubrir",
      recuadro: {x: 0.55, y: 0.05, w: 0.4}, dur_medio: 0, ancho: 0, alto: 0, tiene_audio: false, nombre: "", mid: "",
      trans_in: {tipo: "ninguna", dur: 0.5}, kf: {},
    }, extra || {});
  }
  function textoBase() {
    return {contenido: "Texto", fuente: "Arial", tamano: 90, color: "#FFFFFF", color_contorno: "#000000", grosor_contorno: 6, sombra: 0,
      color_sombra: "#000000", negrita: true, cursiva: false, mayusculas: false, alineacion: "centro", x: 0.5, y: 0.5, fondo: "ninguno",
      color_fondo: "#000000", espaciado: 0, icono_espacios: 0, anim_in: "ninguna", anim_out: "ninguna", anim_dur: 0.4};
  }

  // ------------------------------------------------------------------ keyframes
  const POR_DEFECTO = {zoom: 1, pos_x: 0, pos_y: 0, opacidad: 1, volumen: 1};
  function valorKf(p, param, tl) {
    const pts = p.kf && p.kf[param];
    if (!pts || !pts.length) return p[param] !== undefined ? p[param] : POR_DEFECTO[param];
    if (tl <= pts[0].t) return pts[0].v;
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i], b = pts[i + 1];
      if (tl < b.t) {
        let f = (tl - a.t) / Math.max(1e-9, b.t - a.t);
        if (b.ease === "entrada") f *= f;
        else if (b.ease === "salida") f = 1 - (1 - f) * (1 - f);
        else if (b.ease === "ambos") f = f * f * (3 - 2 * f);
        return a.v + (b.v - a.v) * f;
      }
    }
    return pts[pts.length - 1].v;
  }
  function partirKf(p, corte) {
    const izq = {}, der = {};
    for (const k of Object.keys(p.kf || {})) {
      const pts = p.kf[k]; if (!pts.length) continue;
      const v = valorKf(p, k, corte);
      const a = pts.filter(q => q.t <= corte + EPS).map(q => ({...q}));
      if (pts.some(q => q.t > corte + EPS) && !a.some(q => Math.abs(q.t - corte) < EPS)) a.push({t: redondear(corte), v});
      const b = pts.filter(q => q.t > corte + EPS).map(q => ({...q, t: redondear(q.t - corte)}));
      if (pts.some(q => q.t <= corte + EPS)) b.unshift({t: 0, v: redondear(v)});
      if (a.length) izq[k] = a;
      if (b.length) der[k] = b;
    }
    return {izq, der};
  }
  function desplazarKf(p, delta) {   // la pieza pierde ``delta`` s al inicio: los keyframes se corren hacia atrás
    for (const k of Object.keys(p.kf || {})) {
      const v0 = valorKf(p, k, delta);
      const pts = p.kf[k].filter(q => q.t > delta + EPS).map(q => ({...q, t: redondear(q.t - delta)}));
      if (p.kf[k].some(q => q.t <= delta + EPS)) pts.unshift({t: 0, v: redondear(v0)});
      if (pts.length) p.kf[k] = pts; else delete p.kf[k];
    }
  }
  function acotarKf(p) {
    for (const k of Object.keys(p.kf || {})) {
      const pts = p.kf[k].filter(q => q.t <= p.dur + EPS);
      if (pts.length) p.kf[k] = pts; else delete p.kf[k];
    }
  }

  // ------------------------------------------------------------------ recortes de una pieza
  function topeFuente(p) {
    // cuánto puede durar (en la salida) como máximo esta pieza según lo que queda de su fuente
    if (esMediaConFuente(p) && p.dur_medio > 0.2) return Math.max(MIN_DUR, (p.dur_medio - p.desde) / vel(p));
    return MAX_DURACION;
  }
  function recortarFinal(p, nuevaDur) {
    p.dur = redondear(nuevaDur);
    p.fundido_out = Math.min(p.fundido_out || 0, p.dur);
    p.fundido_in = Math.min(p.fundido_in || 0, Math.max(0, p.dur - p.fundido_out));
    acotarKf(p);
  }
  function recortarInicio(p, delta) {   // quita ``delta`` s del principio (delta puede ser negativo: alarga hacia atrás)
    if (esMediaConFuente(p)) p.desde = redondear(Math.max(0, p.desde + delta * vel(p)));
    p.t = redondear(p.t + delta);
    p.dur = redondear(p.dur - delta);
    if (delta > 0) { p.fundido_in = 0; p.trans_in = {tipo: "ninguna", dur: 0.5}; desplazarKf(p, delta); }
    p.fundido_out = Math.min(p.fundido_out || 0, p.dur);
    acotarKf(p);
  }

  // ------------------------------------------------------------------ dividir
  function dividirPieza(P, p, t, mapaEnlaces) {
    const corte = t - p.t;
    if (corte < MIN_DUR - 1e-9 || p.dur - corte < MIN_DUR - 1e-9) return null;
    const b = clonar(p);
    const k = partirKf(p, corte);
    b.id = nuevoId(P); b.t = redondear(t); b.dur = redondear(p.dur - corte);
    if (esMediaConFuente(p)) b.desde = redondear(p.desde + corte * vel(p));
    p.dur = redondear(corte);
    p.fundido_out = 0; b.fundido_in = 0;
    b.trans_in = {tipo: "ninguna", dur: 0.5};
    p.kf = k.izq; b.kf = k.der;
    if (p.texto) { p.texto.anim_out = "ninguna"; b.texto.anim_in = "ninguna"; }
    if (p.enlace) {
      if (mapaEnlaces) { if (!mapaEnlaces[p.enlace]) mapaEnlaces[p.enlace] = nuevoEnlace(); b.enlace = mapaEnlaces[p.enlace]; }
      else b.enlace = "";
    }
    P.push(b);
    return b;
  }
  // Divide en el instante ``t`` las piezas de ``objetivo`` (o todas las que ocupan ese instante) que no estén en pistas bloqueadas.
  function dividirEn(P, t, objetivo, bloqueadas) {
    const bloq = bloqueadas || new Set();
    const cand = (objetivo || P.filter(p => t > p.t + EPS && t < fin(p) - EPS)).filter(p => !bloq.has(p.carril));
    const mapa = {}, nuevas = [];
    for (const p of cand.slice()) { const b = dividirPieza(P, p, t, mapa); if (b) nuevas.push(b); }
    limpiarEnlaces(P);
    return nuevas;
  }

  // ------------------------------------------------------------------ enlaces
  function limpiarEnlaces(P) {
    const n = {};
    for (const p of P) if (p.enlace) n[p.enlace] = (n[p.enlace] || 0) + 1;
    for (const p of P) if (p.enlace && n[p.enlace] < 2) p.enlace = "";
  }
  function enlazar(P, ids) {
    const sel = P.filter(p => ids.has(p.id));
    if (sel.length < 2) return false;
    const e = nuevoEnlace();
    for (const p of sel) p.enlace = e;
    return true;
  }
  function desenlazar(P, ids) {
    for (const p of P) if (ids.has(p.id)) p.enlace = "";
    limpiarEnlaces(P);
  }
  // Amplía una selección con las piezas enlazadas a ella.
  function conEnlazadas(P, ids) {
    const r = new Set(ids);
    for (const p of P) if (ids.has(p.id) && p.enlace) for (const q of P) if (q.enlace === p.enlace) r.add(q.id);
    return r;
  }

  // ------------------------------------------------------------------ sobrescribir (soltar una pieza encima de otras)
  function sobrescribir(P, movidas) {
    const eliminar = new Set(), nuevas = [];
    for (const m of P.filter(p => movidas.has(p.id))) {
      const a = m.t, b = fin(m);
      for (const o of P.concat(nuevas)) {
        if (movidas.has(o.id) || eliminar.has(o.id) || o.carril !== m.carril) continue;
        const oa = o.t, ob = fin(o);
        if (ob <= a + EPS || oa >= b - EPS) continue;
        if (oa >= a - EPS && ob <= b + EPS) { eliminar.add(o.id); continue; }
        if (oa < a - EPS && ob > b + EPS) {
          const der = clonar(o);
          der.id = nuevoId(P.concat(nuevas));
          der.fundido_in = 0; der.trans_in = {tipo: "ninguna", dur: 0.5};
          const k = partirKf(o, b - oa);
          der.kf = k.der; o.kf = k.izq;
          recortarInicio(der, b - oa);
          der.enlace = "";
          recortarFinal(o, a - oa);
          o.fundido_out = 0;
          nuevas.push(der);
        } else if (oa < a) recortarFinal(o, a - oa);
        else recortarInicio(o, b - oa);
      }
    }
    const resultado = P.concat(nuevas).filter(p => !eliminar.has(p.id) && p.dur >= DUR_MIN_PIEZA);
    limpiarEnlaces(resultado);
    return resultado;
  }

  // ------------------------------------------------------------------ borrar (con o sin cerrar el hueco)
  function borrar(P, ids, ripple, bloqueadas) {
    const bloq = bloqueadas || new Set();
    const quitar = P.filter(p => ids.has(p.id) && !bloq.has(p.carril));
    const fuera = new Set(quitar.map(p => p.id));
    const resto = P.filter(p => !fuera.has(p.id));
    if (ripple) {
      const porCarril = {};
      for (const p of quitar) (porCarril[p.carril] = porCarril[p.carril] || []).push([p.t, fin(p)]);
      for (const c of Object.keys(porCarril)) {
        const ivs = porCarril[c].sort((a, b) => a[0] - b[0]), unidos = [];
        for (const iv of ivs) {
          const u = unidos[unidos.length - 1];
          if (u && iv[0] <= u[1] + 1e-3) u[1] = Math.max(u[1], iv[1]); else unidos.push(iv.slice());
        }
        for (const [a, b] of unidos.reverse()) {
          for (const p of resto) if (p.carril === c && p.t >= b - 1e-3) p.t = redondear(Math.max(0, p.t - (b - a)));
        }
      }
    }
    limpiarEnlaces(resto);
    return resto;
  }
  function cerrarHueco(P, carril, a, b) {
    for (const p of P) if (p.carril === carril && p.t >= b - 1e-3) p.t = redondear(Math.max(0, p.t - (b - a)));
  }
  // Huecos de una pista: [{a, b}] (incluido el que hay antes de la primera pieza).
  function huecos(P, carril) {
    const lista = enCarril(P, carril), r = [];
    let cursor = 0;
    for (const p of lista) { if (p.t - cursor > 0.01) r.push({a: cursor, b: p.t}); cursor = Math.max(cursor, fin(p)); }
    return r;
  }

  // ------------------------------------------------------------------ recortar bordes (con ripple, sin él, o rodando)
  function limitesBorde(P, p, borde, ripple) {
    let lo = -Infinity, hi = Infinity;
    const lista = enCarril(P, p.carril), i = lista.findIndex(q => q.id === p.id);
    if (borde === "fin") {
      lo = MIN_DUR - p.dur;
      hi = topeFuente(p) - p.dur;
      hi = Math.min(hi, MAX_DURACION - fin(p));
      if (!ripple && lista[i + 1]) hi = Math.min(hi, lista[i + 1].t - fin(p));
    } else {
      hi = p.dur - MIN_DUR;
      lo = esMediaConFuente(p) ? -p.desde / vel(p) : -Infinity;
      if (!ripple) { lo = Math.max(lo, -p.t); if (lista[i - 1]) lo = Math.max(lo, fin(lista[i - 1]) - p.t); }
    }
    return {lo, hi};
  }
  // Recorta un borde de ``p`` (y el mismo borde de sus compañeras enlazadas) ``dt`` segundos.
  function ajustarBorde(P, p, borde, dt, ripple, enlazadas) {
    const conjunto = [p].concat((enlazadas || []).filter(q => q.id !== p.id));
    let lo = -Infinity, hi = Infinity;
    for (const q of conjunto) { const l = limitesBorde(P, q, borde, ripple); lo = Math.max(lo, l.lo); hi = Math.min(hi, l.hi); }
    if (lo > hi) return 0;
    dt = Math.min(hi, Math.max(lo, dt));
    const finesAntes = new Map(conjunto.map(q => [q.id, fin(q)]));
    const ids = new Set(conjunto.map(q => q.id));
    for (const q of conjunto) {
      if (borde === "fin") recortarFinal(q, q.dur + dt);
      else if (ripple) { const t0 = q.t; recortarInicio(q, dt); q.t = redondear(t0); }
      else recortarInicio(q, dt);
    }
    if (ripple) {
      for (const q of conjunto) {
        const desplazamiento = borde === "fin" ? dt : -dt;
        for (const o of P) if (!ids.has(o.id) && o.carril === q.carril && o.t >= finesAntes.get(q.id) - 1e-3) o.t = redondear(Math.max(0, o.t + desplazamiento));
      }
    }
    return dt;
  }
  // Mueve el corte entre dos piezas contiguas (``izq`` termina donde empieza ``der``).
  function rodar(P, izq, der, dt) {
    let lo = Math.max(MIN_DUR - izq.dur, esMediaConFuente(der) ? -der.desde / vel(der) : -Infinity);
    let hi = Math.min(topeFuente(izq) - izq.dur, der.dur - MIN_DUR);
    if (lo > hi) return 0;
    dt = Math.min(hi, Math.max(lo, dt));
    recortarFinal(izq, izq.dur + dt);
    der.t = redondear(der.t + dt);
    if (esMediaConFuente(der)) der.desde = redondear(der.desde + dt * vel(der));
    der.dur = redondear(der.dur - dt);
    return dt;
  }
  // Pieza contigua por la derecha (su inicio coincide con el final de ``p`` en la misma pista) o null.
  function contiguaDerecha(P, p) { return P.find(q => q.id !== p.id && q.carril === p.carril && Math.abs(q.t - fin(p)) < 0.02) || null; }

  // ------------------------------------------------------------------ colocar piezas nuevas
  function carrilLibre(P, fam, t, dur, nPistas, desde) {
    for (let n = desde || 1; n <= nPistas; n++) {
      const c = fam + n;
      if (!P.some(p => p.carril === c && p.t < t + dur - 1e-3 && t < fin(p) - 1e-3)) return c;
    }
    return null;
  }
  // Inserta ``nuevas`` (ya con su ``t``) en el instante ``T`` empujando lo que hay después en las pistas no bloqueadas.
  function insertarEn(P, T, nuevas, bloqueadas) {
    const bloq = bloqueadas || new Set();
    const D = nuevas.reduce((m, p) => Math.max(m, p.dur), 0);
    dividirEn(P, T, null, bloq);
    for (const p of P) if (p.t >= T - 1e-3 && !bloq.has(p.carril)) p.t = redondear(p.t + D);
    const r = P.concat(nuevas);
    return r;
  }

  // ------------------------------------------------------------------ tiempos del clip original (para los subtítulos)
  function mapaClip(P) {
    let el = P.filter(p => p.fuente === "clip" && p.tipo === "audio");
    if (!el.length) el = P.filter(p => p.fuente === "clip" && p.tipo === "video");
    return el.sort((a, b) => a.t - b.t).map(p => ({a: p.desde, b: p.desde + consumo(p), t0: p.t, vel: vel(p)}));
  }
  function salidaDeOrigen(mapa, t) {
    for (const m of mapa) if (t >= m.a - EPS && t <= m.b + EPS) return m.t0 + (t - m.a) / m.vel;
    return null;
  }
  // Como salidaDeOrigen, pero si ese instante ya no está, devuelve el más cercano (para dibujar subtítulos aproximados).
  function salidaDeOrigenSuave(mapa, t, haciaAdelante) {
    const e = salidaDeOrigen(mapa, t); if (e !== null) return e;
    let mejor = null, dist = Infinity;
    for (const m of mapa) {
      const d = t < m.a ? m.a - t : t - m.b;
      if (d < dist) { dist = d; mejor = t < m.a ? m.t0 : m.t0 + (m.b - m.a) / m.vel; }
    }
    return mejor === null ? 0 : mejor;
  }
  function origenDeSalida(mapa, t) {
    for (const m of mapa) { const f = m.t0 + (m.b - m.a) / m.vel; if (t >= m.t0 - EPS && t <= f + EPS) return m.a + (t - m.t0) * m.vel; }
    return null;
  }

  // ------------------------------------------------------------------ varios
  function puntosImantados(P, excluir, T) {
    const r = new Set([0]);
    if (T !== undefined) r.add(T);
    for (const p of P) { if (excluir && excluir.has(p.id)) continue; r.add(redondear(p.t)); r.add(redondear(fin(p))); }
    return Array.from(r).sort((a, b) => a - b);
  }
  function imantar(puntos, valor, umbral) {
    let mejor = null, d = umbral;
    for (const x of puntos) { const e = Math.abs(x - valor); if (e <= d) { d = e; mejor = x; } }
    return mejor;
  }
  // Piezas nuevas de un medio (video con su audio enlazado, imagen o audio). Los carriles los pone quien llama.
  function piezasDeMedio(f, t, dur, P) {
    const esAudio = f.tipo === "audio";
    const comun = {fuente: "medio", archivo: f.archivo, mid: f.mid, nombre: f.nombre, dur_medio: f.dur_medio, ancho: f.ancho, alto: f.alto, tiene_audio: f.tiene_audio, t: redondear(t), desde: 0, dur: redondear(dur)};
    const v = esAudio ? null : piezaBase(Object.assign({}, comun, {id: nuevoId(P), tipo: f.tipo === "imagen" ? "imagen" : "video", carril: "V2"}));
    const a = (esAudio || (f.tipo === "video" && f.tiene_audio)) ? piezaBase(Object.assign({}, comun, {id: nuevoId((P || []).concat(v ? [v] : [])), tipo: "audio", carril: "A2"})) : null;
    if (v && a) { const e = nuevoEnlace(); v.enlace = e; a.enlace = e; }
    return [v, a].filter(Boolean);
  }
  function normalizarIniciales(P) {   // por si llega una lista con huecos de campos (ediciones guardadas por versiones anteriores)
    return P.map(p => Object.assign(piezaBase(), p, {kf: p.kf || {}, trans_in: p.trans_in || {tipo: "ninguna", dur: 0.5}}));
  }

  const API = {MIN_DUR, DUR_MIN_PIEZA, MAX_DURACION, MAX_CARRILES, clonar, redondear, fin, vel, consumo, familia, numero, total, enCarril, grupo,
    nuevoId, nuevoEnlace, piezaBase, textoBase, valorKf, partirKf, desplazarKf, topeFuente, recortarFinal, recortarInicio, dividirPieza, dividirEn,
    limpiarEnlaces, enlazar, desenlazar, conEnlazadas, sobrescribir, borrar, cerrarHueco, huecos, limitesBorde, ajustarBorde, rodar, contiguaDerecha,
    carrilLibre, insertarEn, mapaClip, salidaDeOrigen, salidaDeOrigenSuave, origenDeSalida, puntosImantados, imantar, piezasDeMedio, normalizarIniciales};
  if (typeof module !== "undefined" && module.exports) module.exports = API; else raiz.PZ = API;
})(typeof window !== "undefined" ? window : globalThis);
