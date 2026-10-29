
"use strict";
const menuHerramientas=document.querySelector("#menuHerramientas");
const menusFijos=[menuHerramientas,...document.querySelectorAll(".barra-tl details")];
function actualizarMenu(d){const panel=d._panel||d.querySelector(":scope > div");if(!panel)return;d._panel=panel;if(d.open){if(panel.parentElement!==document.body){d._parent=panel.parentElement;d._next=panel.nextSibling;document.body.appendChild(panel);panel.classList.add("menu-portal");}const r=d.querySelector("summary").getBoundingClientRect();const ancho=Math.max(190,panel.offsetWidth);let top=d===menuHerramientas?r.bottom+4:r.top-panel.offsetHeight-6;if(top<8)top=r.bottom+4;if(top+panel.offsetHeight>innerHeight-8)top=Math.max(8,innerHeight-panel.offsetHeight-8);panel.style.left=Math.max(8,Math.min(r.left,innerWidth-ancho-8))+"px";panel.style.top=top+"px";}else if(panel.parentElement===document.body&&d._parent){panel.classList.remove("menu-portal");panel.style.removeProperty("left");panel.style.removeProperty("top");d._parent.insertBefore(panel,d._next&&d._next.parentElement===d._parent?d._next:null);}}
menusFijos.forEach(d=>{d.addEventListener("toggle",()=>actualizarMenu(d));d.addEventListener("click",e=>{if(e.target.closest(".menu-portal button"))queueMicrotask(()=>{d.open=false;});});});
addEventListener("resize",()=>menusFijos.filter(d=>d.open).forEach(actualizarMenu));
const $ = s => document.querySelector(s);
const ID = location.pathname.split("/").filter(Boolean).pop();
async function api(ruta, opc) {
  const r = await fetch(`/editor/api/${ID}/${ruta}`, opc);
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.ok === false) { const e = new Error(d.error || ("Error " + r.status)); e.datos = d; throw e; }
  return d;
}
const post = (ruta, cuerpo) => api(ruta, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(cuerpo || {})});
function abrirDialogoEtiqueta(){const s=$("#etFuente"),p=piezaSel();s.replaceChildren(...FUENTES.map(f=>new Option(f,f)));s.value=(E.subtitulos.estilo&&E.subtitulos.estilo.fuente)||"Arial";if(p&&p.tipo==="imagen"&&(p.nombre||"").startsWith("Etiqueta Â· ")){$("#etNombre").value=(p.nombre.split(" Â· ").slice(2).join(" Â· ")||"tu_nombre");$("#etPlataforma").value=p.nombre.split(" Â· ")[1]||"YouTube";}else{$("#etNombre").value="tu_nombre";}$("#dialogEtiqueta").showModal();}
$("#etCerrar").onclick=()=>$("#dialogEtiqueta").close();
$("#etCrear").onclick=async()=>{const b=$("#etCrear"),err=$("#etError"),existente=piezaSel(),editar=existente&&existente.tipo==="imagen"&&(existente.nombre||"").startsWith("Etiqueta Â· ");b.disabled=true;err.textContent="Generandoâ€¦";try{const d=await post("etiqueta",{plataforma:$("#etPlataforma").value.toLowerCase(),variante:$("#etVariante").value,forma:$("#etForma").value,nombre:$("#etNombre").value,fuente:$("#etFuente").value,tamano:+$("#etTamano").value});const f=d.medio,dur=editar?existente.dur:4,t=editar?existente.t:PZ.redondear(T),q=PZ.piezasDeMedio(f,t,dur,E.piezas)[0];if(editar){Object.assign(existente,{archivo:q.archivo,mid:q.mid,ancho:q.ancho,alto:q.alto,dur_medio:q.dur_medio,nombre:"Etiqueta Â· "+$("#etPlataforma").value+" Â· "+$("#etNombre").value});}else{const carril=carrilArriba(t,dur);if(!carril)throw new Error("No queda una pista de vÃ­deo libre.");q.carril=carril;q.nombre="Etiqueta Â· "+$("#etPlataforma").value+" Â· "+$("#etNombre").value;q.modo="recuadro";q.recuadro={x:.05,y:.05,w:.42};E.piezas.push(q);seleccionar([q.id]);}confirmar();refrescarTodo();$("#dialogEtiqueta").close();activarPestana("pistas");}catch(e){err.textContent=e.message;}finally{b.disabled=false;}};
$("#cerrarDiagnostico").onclick = () => $("#panelDiagnostico").close();
$("#bComprobar").onclick = async () => { try { const d=await fetch("/editor/api/version").then(r=>r.json()); alert("VersiÃ³n del editor: "+d.version+"\n"+Object.entries(d.sellos).map(([k,v])=>k+": "+v).join("\n")); } catch(e) { alert("No se pudo comprobar: "+e.message); } };
$("#bDiagnosticar").onclick = async () => {
  const dlg=$("#panelDiagnostico"), pre=$("#textoDiagnostico"), prog=$("#progresoDiagnostico"), bar=$("#barraDiagnostico"), link=$("#descargarDiagnostico");
  pre.textContent="";link.hidden=true;bar.style.width="0%";dlg.showModal();prog.textContent="Iniciando diagnÃ³sticoâ€¦";
  try { await post("diagnosticar"); const fin=Date.now()+30*60*1000; while(Date.now()<fin){ const d=await api("diagnosticar/estado");prog.textContent=d.mensaje||"Analizandoâ€¦";bar.style.width=Math.round((d.progreso||0)*100)+"%";if(d.resultado)pre.textContent=d.resultado;if(d.estado==="listo"){link.href=`/editor/api/${ID}/diagnosticar/descargar`;link.hidden=false;break;}if(d.estado==="error")throw new Error(d.mensaje);await new Promise(r=>setTimeout(r,700));} } catch(e){prog.textContent="No se pudo completar: "+e.message;}
};
$("#bReiniciar").onclick = async () => { const b=$("#bReiniciar");b.disabled=true;b.textContent="Reiniciandoâ€¦";try{await post("reiniciar");const fin=Date.now()+60000;while(Date.now()<fin){try{const d=await fetch("/editor/api/version?x="+Date.now(),{cache:"no-store"}).then(r=>r.json());if(d.version>=11){location.reload();return;}}catch(_){}await new Promise(r=>setTimeout(r,700));}}catch(e){alert("No se pudo reiniciar: "+e.message);}b.disabled=false;b.textContent="Reiniciar panel";};

// ------------------------------------------------------------------ estado
let E = null, INFO = null, FUENTES = [], CARA = {disponible: false, mensaje: ""}, IA = {disponible: false, mensaje: ""}, SUB_STREAM = false;
let T = 0;                       // cabezal: segundos de la LÃNEA DE TIEMPO DE SALIDA
let reproduciendo = false, sel = null, herramienta = "sel", PICOS = [], PICOS_POR_S = 20;
const SEL = new Set();           // ids de las piezas seleccionadas (sel.id es la principal)
let deshacer = [], rehacer = [], ultimoSnap = "", temporizadorGuardado = null, guardando = false;
const V = $("#v"), LZ = $("#lienzo"), CTX = LZ.getContext("2d");
const TLC = $("#tl"), TLX = TLC.getContext("2d");
const TL = {px: 60, margen: 12, altoRegla: 24, carriles: [], alto: 200, sx: 0, sy: 0, ancho: 100, altoVis: 100};
const OPC = {ripple: true, iman: true, enlazada: true, colocar: "superponer"};     // opciones de ediciÃ³n (se recuerdan)
const PICOS_MEDIO = {};
const URL_CLIP = `/editor/api/${ID}/video`;
const MAX_PIEZAS = 300, MAX_CARRILES = 8;
const nuevoId = () => "x" + Math.random().toString(36).slice(2, 8);

function errorCargaVideo(video) {
  const codigo = video.error?.code;
  const detalle = ({1: "La carga se canceló.", 2: "Falló la descarga del video.", 3: "El navegador no pudo decodificar el video.", 4: "El formato de video no es compatible."})[codigo];
  return detalle ? `No se pudo cargar la vista previa: ${detalle} (error ${codigo}).` : "No se pudo cargar la vista previa del video.";
}
function cargarPrimerFotograma(video, url, limiteMs = 45000) {
  return new Promise((resolve, reject) => {
    let terminado = false;
    const limpiar = () => {
      clearTimeout(limite);
      video.removeEventListener("loadeddata", listo);
      video.removeEventListener("canplay", listo);
      video.removeEventListener("error", fallo);
    };
    const acabar = fn => { if (terminado) return; terminado = true; limpiar(); fn(); };
    const listo = () => video.readyState >= 2 && video.videoWidth > 0 && acabar(resolve);
    const fallo = () => acabar(() => reject(new Error(errorCargaVideo(video))));
    const limite = setTimeout(() => acabar(() => reject(new Error("La vista previa no recibió un fotograma tras 45 segundos. Comprueba la conexión con el panel y vuelve a intentarlo."))), limiteMs);
    video.addEventListener("loadeddata", listo);
    video.addEventListener("canplay", listo);
    video.addEventListener("error", fallo);
    video.src = url;
    video.load();
    if (video.readyState >= 2 && video.videoWidth > 0) acabar(resolve);
  });
}

const durSalida = () => PZ.total(E.piezas);
const mapa = () => PZ.mapaClip(E.piezas);
const oriASal = t => PZ.salidaDeOrigen(mapa(), t);
const oriASalSuave = t => PZ.salidaDeOrigenSuave(mapa(), t);
const salAOri = t => PZ.origenDeSalida(mapa(), t);
const fmt = t => { t = Math.max(0, t); const m = Math.floor(t / 60), s = t - m * 60; return `${m}:${s.toFixed(2).padStart(5, "0")}`; };
const limitar = (v, a, b) => Math.min(b, Math.max(a, v));
const fps = () => E.origen.fps || 25;
const aFotograma = t => Math.round(t * fps()) / fps();

// selecciÃ³n y pistas
const piezaPorId = id => E.piezas.find(p => p.id === id) || null;
const piezaSel = () => (sel && sel.tipo === "pieza" ? piezaPorId(sel.id) : null);
const piezasSel = () => E.piezas.filter(p => SEL.has(p.id));
const bloqueadas = () => new Set(E.pistas.bloqueadas || []);
const ocultas = () => new Set(E.pistas.ocultas || []);
const silenciadas = () => new Set(E.pistas.silenciadas || []);
function seleccionar(ids, principal) {
  SEL.clear(); for (const i of ids) SEL.add(i);
  sel = ids.length ? {tipo: "pieza", id: principal !== undefined ? principal : ids[0]} : null;
  alCambiarSeleccion();
}
function seleccionarSub(i) { SEL.clear(); sel = {tipo: "sub", i}; alCambiarSeleccion(); }
let transformNodo=null;
function actualizarTransformBox() {
  const p=piezaSel(), ok=p&&(p.tipo==="video"||p.tipo==="imagen")&&p.fuente==="medio"&&p.modo!=="recuadro";
  if(!ok){if(transformNodo){transformNodo.remove();transformNodo=null;}return;}
  if(!transformNodo){transformNodo=document.createElement("div");transformNodo.className="transform-box";transformNodo.innerHTML='<button class="th s" title="Escalar"></button><button class="th r" title="Girar"></button>';transformNodo.addEventListener("pointerdown",e=>iniciarTransformacion(e));$("#overlaySalida").appendChild(transformNodo);}
  const box=transformNodo, W=E.salida.ancho,H=E.salida.alto,ar=p.alto&&p.ancho?p.alto/p.ancho:9/16;
  const zoom=parametro(p,"zoom"), bw=100/zoom, bh=Math.min(100,bw*W*ar/H), cx=50+parametro(p,"pos_x")*50+(p.tras_x||0)*100,cy=50+parametro(p,"pos_y")*50+(p.tras_y||0)*100;
  box.style.left=(cx-bw/2)+"%";box.style.top=(cy-bh/2)+"%";box.style.width=bw+"%";box.style.height=bh+"%";box.style.transform=`rotate(${parametro(p,"rotacion")}deg)`;
}
for(const [id,k] of [["iCropL","izquierda"],["iCropR","derecha"],["iCropT","arriba"],["iCropB","abajo"]])$("#"+id).addEventListener("input",e=>{const p=piezaSel();if(!p)return;p.recorte_bordes=p.recorte_bordes||{};p.recorte_bordes[k]=+e.target.value/100;dibujar();tocar();});
document.querySelector("#gTransformacion").addEventListener("change",e=>{if(e.target.matches("input[type=range]"))confirmar();});
$("#gTransformacion").addEventListener("change",e=>{const p=piezaSel();if(!p)return;if(e.target.id==="iFlipH")p.flip_h=e.target.checked;if(e.target.id==="iFlipV")p.flip_v=e.target.checked;confirmar();refrescarTodo();});
function sincronizarTransformacion(){const p=piezaSel(),v=p?.recorte_bordes||{};for(const [id,k] of [["iCropL","izquierda"],["iCropR","derecha"],["iCropT","arriba"],["iCropB","abajo"]])$("#"+id).value=Math.round((v[k]||0)*100);$("#iFlipH").checked=!!p?.flip_h;$("#iFlipV").checked=!!p?.flip_v;$("#gTransformacion").hidden=!(p&&(p.tipo==="video"||p.tipo==="imagen")&&p.fuente==="medio");}
function iniciarTransformacion(ev){const p=piezaSel();if(!p)return;ev.preventDefault();ev.stopPropagation();const b=LZ.getBoundingClientRect(),sx=ev.clientX,sy=ev.clientY,zoom=p.zoom||1,px=p.pos_x||0,py=p.pos_y||0,tx0=p.tras_x||0,ty0=p.tras_y||0,rot=p.rotacion||0,handle=ev.target.closest(".th")?.classList.contains("s")?"s":ev.target.closest(".th")?.classList.contains("r")?"r":"m",cx=b.left+b.width*(.5+px*.5+tx0),cy=b.top+b.height*(.5+py*.5+ty0),a0=Math.atan2(sy-cy,sx-cx);arrastrar(ev,transformNodo,e=>{if(handle==="m"){p.tras_x=limitar(tx0+(e.clientX-sx)/b.width,-1,1);p.tras_y=limitar(ty0+(e.clientY-sy)/b.height,-1,1);}else if(handle==="s"){const d=Math.hypot(e.clientX-cx,e.clientY-cy)/Math.max(1,Math.hypot(sx-cx,sy-cy));ponerParam(p,"zoom",limitar(zoom*d,1,4));}else{ponerParam(p,"rotacion",limitar(rot+(Math.atan2(e.clientY-cy,e.clientX-cx)-a0)*180/Math.PI,-180,180));}sincronizarTransformacion();actualizarTransformBox();valoresParametros();dibujar();tocar();},()=>{confirmar();refrescarTodo();});}
function alCambiarSeleccion() {
  actualizarAlcance(); sincronizarPieza(); sincronizarAlcance(); sincronizarModo(); marcarFilaSub(); actualizarTransformBox(); sincronizarTransformacion();
}

// ------------------------------------------------------------------ encuadre propio por tramo
// ENC(): el encuadre que se estÃ¡ VIENDO/editando (el del tramo si estÃ¡ en Â«Solo este tramoÂ»); ENCW(): lo mismo pero lo crea para escribir.
let ALCANCE = "todo";
const piezaClipSel = () => { const p = piezaSel(); return p && p.fuente === "clip" && p.tipo === "video" ? p : null; };
// Piezas de vÃ­deo que admiten plantilla propia: trozos del clip y vÃ­deos aÃ±adidos (con sus medidas conocidas).
const piezaEncSel = () => { const p = piezaSel(); return p && p.tipo === "video" && (p.fuente === "clip" || (p.fuente === "medio" && p.ancho > 0 && p.alto > 0)) ? p : null; };
const piezaMedioSel = () => { const p = piezaEncSel(); return p && p.fuente === "medio" ? p : null; };
const esEncuadrable = p => p.tipo === "video" && (p.fuente === "clip" || (p.fuente === "medio" && p.ancho > 0 && p.alto > 0));
// Medidas del vÃ­deo al que se refieren las zonas azules: el clip, o el vÃ­deo aÃ±adido que se estÃ¡ editando (o dibujando).
let ORI_OVR = null;
const ORI = () => { if (ORI_OVR) return ORI_OVR; const p = piezaMedioSel(); return p ? {ancho: p.ancho, alto: p.alto} : E.origen; };
const ENC = () => { const p = piezaEncSel(); return ALCANCE === "tramo" && p && p.encuadre ? p.encuadre : E.encuadre; };
function ENCW() {
  const p = piezaEncSel();
  if (ALCANCE === "tramo" && p) { if (!p.encuadre) p.encuadre = JSON.parse(JSON.stringify(E.encuadre)); return p.encuadre; }
  return E.encuadre;
}
function actualizarAlcance() { const p = piezaEncSel(); if (!p) ALCANCE = "todo"; else if (p.fuente === "medio" || p.encuadre) ALCANCE = "tramo"; }

// ------------------------------------------------------------------ historial y guardado
function foto() { return JSON.stringify(E); }
function confirmar() {
  const f = foto();
  if (f === ultimoSnap) return;
  if (ultimoSnap) { deshacer.push(ultimoSnap); if (deshacer.length > 100) deshacer.shift(); }
  ultimoSnap = f; rehacer = [];
  actualizarBotonesHistorial(); programarGuardado();
}
function aplicarFoto(f) {
  const pend = sel && sel.tipo === "pieza" ? [...SEL] : [];
  E = JSON.parse(f); ultimoSnap = f; SEL.clear(); sel = null;
  const vivos = pend.filter(id => piezaPorId(id)); if (vivos.length) { for (const i of vivos) SEL.add(i); sel = {tipo: "pieza", id: vivos[0]}; }
  T = limitar(T, 0, durSalida()); ir(T); refrescarTodo(); programarGuardado();
}
function deshacerAccion() { if (!deshacer.length) return; rehacer.push(foto()); aplicarFoto(deshacer.pop()); actualizarBotonesHistorial(); }
function rehacerAccion() { if (!rehacer.length) return; deshacer.push(foto()); aplicarFoto(rehacer.pop()); actualizarBotonesHistorial(); }
function actualizarBotonesHistorial() { $("#bDeshacer").disabled = !deshacer.length; $("#bRehacer").disabled = !rehacer.length; }
function programarGuardado() {
  $("#estadoGuardado").textContent = "Cambios sin guardarâ€¦";
  clearTimeout(temporizadorGuardado);
  temporizadorGuardado = setTimeout(guardar, 1200);
}
async function guardar() {
  clearTimeout(temporizadorGuardado);
  if (guardando) { temporizadorGuardado = setTimeout(guardar, 600); return; }
  guardando = true;
  try {
    const r = await post("guardar", E);
    if (r && r.edicion && (!Array.isArray(r.edicion.piezas) || r.edicion.encuadre.modo !== E.encuadre.modo || (E.encuadre.modo === "capas" && !(r.edicion.encuadre.capas || []).length))) avisarPanelViejo();
    else $("#estadoGuardado").textContent = "Guardado âœ“";
  }
  catch (e) { $("#estadoGuardado").textContent = "No se pudo guardar"; }
  guardando = false;
}

// ------------------------------------------------------------------ encuadre (misma matemÃ¡tica que el render)
function rectAspecto(r, W, H, asp) {
  const cx = (r.x + r.w / 2) * W, cy = (r.y + r.h / 2) * H;
  let w = r.w * W, h = r.h * H;
  if (w / h > asp) w = h * asp; else h = w / asp;
  const e = Math.min(1, W / w, H / h); w *= e; h *= e;
  const x = limitar(cx - w / 2, 0, W - w), y = limitar(cy - h / 2, 0, H - h);
  return {x: x / W, y: y / H, w: w / W, h: h / H};
}
const parPx = n => { n = Math.round(n); return Math.max(2, n - n % 2); };
const rectDe = (c, enc = ENC()) => (c.startsWith("capa:") ? (enc.capas || []).find(x => x.id === c.slice(5)).fuente : c.startsWith("tres.") ? enc.tres[c.slice(5)] : enc[c]);
const ponerRect = (c, v) => { const enc = ENCW(); if (c.startsWith("capa:")) capaPorId(c.slice(5)).fuente = v; else if (c.startsWith("tres.")) enc.tres[c.slice(5)] = v; else enc[c] = v; };
function franjas(enc = ENC()) {
  const oh = E.salida.alto; let alturas, claves;
  if (enc.modo === "tres") { const h1 = parPx(oh * enc.alturas_tres[0]), h2 = parPx(oh * enc.alturas_tres[1]); alturas = [h1, h2, oh - h1 - h2]; claves = enc.orden_tres.map(k => "tres." + k); }
  else { const a = parPx(oh * enc.proporcion_arriba); alturas = [a, oh - a]; claves = enc.invertido ? ["abajo", "arriba"] : ["arriba", "abajo"]; }
  let y = 0; return claves.map((clave, i) => { const f = {clave, y0: y, alto: alturas[i]}; y += alturas[i]; return f; });
}
const aspectos = () => ({recorte: E.salida.ancho / E.salida.alto});
const ETIQ_RECT = {arriba: ["Juego", ""], abajo: ["Cara", "b"], "tres.a": ["Pantalla A", ""], "tres.b": ["Pantalla B", "b"], "tres.c": ["Pantalla C", "c"]};
function rectasActivos() {
  const m = ENC().modo;
  if (m === "recorte") return [{clave: "recorte", clase: "", et: "Recorte", asp: aspectos().recorte}];
  if (m === "capas") { const c = capaActual(); return c ? [{clave: "capa:" + c.id, clase: "", et: "Zona de " + nombreCapa(c), asp: aspectoCapa(c)}] : []; }
  if (m === "dividido" || m === "tres") return franjas().map(f => ({clave: f.clave, clase: ETIQ_RECT[f.clave][1], et: ETIQ_RECT[f.clave][0], asp: E.salida.ancho / f.alto}));
  return [];
}



// ------------------------------------------------------------------ plantillas y capas
const COMPLETO = () => ({x: 0, y: 0, w: 1, h: 1});
const esVertical = () => E.origen.alto >= E.origen.ancho;
const esCompleto = q => q.x <= 0.001 && q.y <= 0.001 && q.w >= 0.999 && q.h >= 0.999;
const camRect = () => { const a = ENC().abajo; return esCompleto(a) ? (esVertical() ? COMPLETO() : {x: 0.7, y: 0.55, w: 0.28, h: 0.42}) : {...a}; };
const juegoRect = () => { const a = ENC().arriba; return esCompleto(a) ? COMPLETO() : {...a}; };
const capaBase = (id, rol, fuente, destino, extra = {}) => ({id, rol, fuente, destino, ajuste: "llenar", desenfoque: 0, oscurecer: 0, forma: "rect", radio: 0.1, borde: {ancho: 0, color: "#FFFFFF"}, ...extra});
const BLANCO = ancho => ({ancho, color: "#FFFFFF"});
const PLANTILLAS = [
  {id: "cam", nombre: "CÃ¡mara completa", mock: [[0, 0, 1, 1, "#3b82c4"]],
    aplicar(e) { e.modo = "recorte"; e.recorte = camRect(); }},
  {id: "flotante", nombre: "Juego + cÃ¡mara flotante", mock: [[0, 0, 1, 1, "#555"], [.2, .1, .6, .3, "#3b82c4", 1]],
    aplicar(e) { e.modo = "capas"; e.capas = [capaBase("juego", "juego", juegoRect(), COMPLETO()), capaBase("cam", "cam", camRect(), {x: 0.2, y: 0.08, w: 0.6, h: 0.3375}, {forma: "redondeado", radio: 0.1, borde: BLANCO(8)})]; }},
  {id: "mitad", nombre: "50 / 50 cÃ¡mara y juego", mock: [[0, 0, 1, .5, "#3b82c4"], [0, .5, 1, .5, "#555"]],
    aplicar(e) { e.modo = "dividido"; e.proporcion_arriba = 0.5; e.invertido = true; e.arriba = juegoRect(); e.abajo = camRect(); e.linea = BLANCO(6); }},
  {id: "mosaico", nombre: "Mosaico de 3 cÃ¡maras", mock: [[0, 0, 1, 1, "#2a3140"], [.08, .2, .84, .17, "#3b82c4"], [.08, .42, .84, .17, "#3b82c4"], [.08, .64, .84, .17, "#3b82c4"]],
    aplicar(e) { e.modo = "capas"; e.capas = [capaBase("fondo", "fondo", camRect(), COMPLETO(), {desenfoque: 40, oscurecer: 0.35}),
      ...[0, 1, 2].map(i => capaBase("m" + (i + 1), "otro", {x: i / 3, y: 0.15, w: 1 / 3, h: 0.7}, {x: 0.06, y: 0.2 + i * 0.22, w: 0.88, h: 0.2}, {borde: BLANCO(4)}))]; }},
  {id: "redonda", nombre: "Dividido + cÃ¡mara redondeada", mock: [[0, 0, 1, .5, "#2a3140"], [0, .5, 1, .5, "#555"], [.28, .1, .44, .25, "#3b82c4", 1]],
    aplicar(e) { e.modo = "capas"; e.capas = [capaBase("fondo", "fondo", camRect(), {x: 0, y: 0, w: 1, h: 0.5}, {desenfoque: 30, oscurecer: 0.3}), capaBase("juego", "juego", juegoRect(), {x: 0, y: 0.5, w: 1, h: 0.5}),
      capaBase("cam", "cam", camRect(), {x: 0.275, y: 0.09, w: 0.45, h: 0.253}, {forma: "redondeado", radio: 0.22, borde: BLANCO(6)})]; }},
  {id: "ampliada", nombre: "CÃ¡mara ampliada + fondo difuso", mock: [[0, 0, 1, 1, "#2a3140"], [0, .15, 1, .7, "#3b82c4"]],
    aplicar(e) { e.modo = "capas"; e.capas = [capaBase("fondo", "fondo", camRect(), COMPLETO(), {desenfoque: 40, oscurecer: 0.25}), capaBase("cam", "cam", camRect(), {x: 0, y: 0.1, w: 1, h: 0.8}, {ajuste: "contener"})]; }},
];
function sincronizarIA() {
  const c = E.mejora_ia || (E.mejora_ia = {activa: false, cam: true, juego: false, modelo: "rapido"}), ok = IA.disponible;
  $("#iaActiva").checked = ok && c.activa; $("#iaCam").checked = c.cam; $("#iaJuego").checked = c.juego; $("#iaModelo").value = c.modelo;
  for (const q of ["#iaActiva", "#iaCam", "#iaJuego", "#iaModelo"]) $(q).disabled = !ok;
  const av = $("#avisoIA"); av.hidden = ok; av.textContent = ok ? "" : IA.mensaje;
}
for (const [q, k] of [["#iaActiva", "activa"], ["#iaCam", "cam"], ["#iaJuego", "juego"]]) $(q).addEventListener("change", e => { E.mejora_ia[k] = e.target.checked; confirmar(); });
$("#iaModelo").addEventListener("change", e => { E.mejora_ia.modelo = e.target.value; confirmar(); });
function construirGaleria() {
  const g = $("#galeria"); g.innerHTML = "";
  for (const p of PLANTILLAS) {
    const b = document.createElement("button"); b.className = "plan"; b.dataset.id = p.id; b.title = p.nombre;
    b.innerHTML = `<div class="mock">${p.mock.map(([x, y, w, h, c, r]) => `<i style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%;background:${c}${r ? ";border-radius:30%;border:1px solid #fff" : ""}"></i>`).join("")}</div><b>${p.nombre}</b>`;
    b.onclick = () => aplicarPlantilla(p.id);
    g.appendChild(b);
  }
}
function aplicarPlantilla(id) {
  const p = PLANTILLAS.find(x => x.id === id); if (!p) return;
  const e = ENCW();
  if (e.modo === "dividido" || id !== "mitad") e.linea = {ancho: 0, color: e.linea ? e.linea.color : "#FFFFFF"};
  if (id !== "mitad") e.invertido = false;
  p.aplicar(e); e.plantilla = id;
  capaSel = null; const c = capaActual(); capaSel = c ? c.id : null;
  confirmar(); sincronizarModo(); ir(T);
}
let capaSel = null;
const capasE = () => { const e = ENC(); return e.capas || (e.capas = []); };
const capaPorId = id => capasE().find(c => c.id === id);
const capaActual = () => capaPorId(capaSel) || capasE().find(c => c.rol === "cam") || capasE()[capasE().length - 1] || null;
const NOMBRE_ROL = {juego: "Juego", cam: "CÃ¡mara", fondo: "Fondo", otro: "Capa"};
const nombreCapa = c => `${capasE().indexOf(c) + 1}. ${c.id.startsWith("m") && c.rol === "otro" ? "CÃ¡mara " + c.id.slice(1) : NOMBRE_ROL[c.rol] || "Capa"}`;
function aspectoCapa(c) {
  const ow = E.salida.ancho, oh = E.salida.alto, b = c.borde.ancho;
  const iw = Math.max(2, c.destino.w * ow - 2 * b), ih = Math.max(2, c.destino.h * oh - 2 * b);
  return c.ajuste === "llenar" ? iw / ih : (c.fuente.w * ORI().ancho) / (c.fuente.h * ORI().alto);
}
function sincronizarCapas() {
  const L = capasE(), c = capaActual(); capaSel = c ? c.id : null;
  document.querySelectorAll("#galeria .plan").forEach(b => b.classList.toggle("on", b.dataset.id === ENC().plantilla));
  const ch = $("#chipsCapas"); ch.innerHTML = "";
  L.forEach(x => { const b = document.createElement("button"); b.textContent = nombreCapa(x); b.className = x === c ? "activo" : ""; b.onclick = () => { capaSel = x.id; sincronizarCapas(); dibujarRecuadros(); dibujarDestino(); }; ch.appendChild(b); });
  const off = !c; for (const el of document.querySelectorAll("#gCapas select,#gCapas input,#bCapaCompleta,#bCapaCentro,#bCapaMenos,#bCapaSub,#bCapaBaj")) el.disabled = off;
  if (!c) return;
  $("#cpAjuste").value = c.ajuste; $("#cpForma").value = c.forma;
  $("#cpRadio").value = Math.round(c.radio * 100); $("#cpRadioV").textContent = Math.round(c.radio * 100) + "%"; $("#cpRadio").disabled = c.forma !== "redondeado";
  $("#cpBorde").value = c.borde.ancho; $("#cpBordeV").textContent = c.borde.ancho + "px"; $("#cpBordeColor").value = c.borde.color.toLowerCase();
  $("#cpDesenfoque").value = c.desenfoque; $("#cpDesV").textContent = Math.round(c.desenfoque);
  $("#cpOscurecer").value = Math.round(c.oscurecer * 100); $("#cpOscV").textContent = Math.round(c.oscurecer * 100) + "%";
  const primera = capasE()[0] === c; $("#cpForma").disabled = primera; if (primera) $("#cpRadio").disabled = true;
}
function enCapa(sel, ev, fn, final) {
  $(sel).addEventListener(ev, e => { ENCW(); const c = capaActual(); if (!c) return; fn(c, e.target); sincronizarCapas(); dibujarRecuadros(); dibujarDestino(); if (final) confirmar(); });
  if (!final) $(sel).addEventListener("change", confirmar);
}
enCapa("#cpAjuste", "change", (c, t) => { c.ajuste = t.value; }, true);
enCapa("#cpForma", "change", (c, t) => { c.forma = t.value; }, true);
enCapa("#cpRadio", "input", (c, t) => { c.radio = +t.value / 100; });
enCapa("#cpBorde", "input", (c, t) => { c.borde.ancho = +t.value; });
enCapa("#cpBordeColor", "input", (c, t) => { c.borde.color = t.value.toUpperCase(); });
enCapa("#cpDesenfoque", "input", (c, t) => { c.desenfoque = +t.value; });
enCapa("#cpOscurecer", "input", (c, t) => { c.oscurecer = +t.value / 100; });
$("#bCapaCompleta").onclick = () => { ENCW(); const c = capaActual(); if (c) { c.destino = COMPLETO(); confirmar(); sincronizarModo(); } };
$("#bCapaCentro").onclick = () => { ENCW(); const c = capaActual(); if (c) { c.destino.x = (1 - c.destino.w) / 2; confirmar(); sincronizarModo(); } };
$("#bCapaMas").onclick = () => {
  ENCW(); const L = capasE(); if (L.length >= 6) return;
  let n = 1; while (capaPorId("c" + n)) n++;
  const c = capaBase("c" + n, "otro", camRect(), {x: 0.25, y: 0.35, w: 0.5, h: 0.28}, {borde: BLANCO(4)}); L.push(c); capaSel = c.id;
  ENCW().modo = "capas"; confirmar(); sincronizarModo();
};
$("#bCapaMenos").onclick = () => { ENCW(); const L = capasE(), c = capaActual(); if (!c) return; L.splice(L.indexOf(c), 1); capaSel = null; confirmar(); sincronizarModo(); };
const moverCapa = d => { ENCW(); const L = capasE(), c = capaActual(); if (!c) return; const i = L.indexOf(c), j = i + d; if (j < 0 || j >= L.length) return; [L[i], L[j]] = [L[j], L[i]]; confirmar(); sincronizarModo(); };
$("#bCapaSub").onclick = () => moverCapa(1); $("#bCapaBaj").onclick = () => moverCapa(-1);
$("#bRestPlantilla").onclick = () => { if (ENC().plantilla) aplicarPlantilla(ENC().plantilla); else $("#notaCara2").textContent = "Elige primero una plantilla."; };
function dibujarDestino() {
  const cont = $("#ovCapa"); if (!E) return;
  const c = ENC().modo === "capas" ? capaActual() : null;
  if (!c) { cont.innerHTML = ""; cont.dataset.id = ""; return; }
  if (cont.dataset.id !== c.id) {
    cont.innerHTML = ""; cont.dataset.id = c.id;
    const d = document.createElement("div"); d.className = "recuadro c";
    d.innerHTML = `<span class="et"></span>` + ["nw", "ne", "sw", "se"].map(k => `<i class="m ${k}" data-c="${k}"></i>`).join("");
    d.addEventListener("pointerdown", empezarDestino); cont.appendChild(d);
  }
  const d = cont.firstChild, r = c.destino, pct = v => (v * 100).toFixed(3) + "%";
  d.style.left = pct(r.x); d.style.top = pct(r.y); d.style.width = pct(r.w); d.style.height = pct(r.h);
  d.querySelector(".et").textContent = "Colocar: " + nombreCapa(c);
}
function empezarDestino(ev) {
  ENCW(); const c = capaActual(); if (!c) return;
  const cj = LZ.getBoundingClientRect(), r0 = {...c.destino}, esq = ev.target.dataset.c || null, sx = ev.clientX, sy = ev.clientY;
  arrastrar(ev, ev.currentTarget, e => {
    const dx = (e.clientX - sx) / cj.width, dy = (e.clientY - sy) / cj.height; let x, y, w = r0.w, h = r0.h;
    if (!esq) {
      x = limitar(r0.x + dx, 0, 1 - w); y = limitar(r0.y + dy, 0, 1 - h);
      if (Math.abs(x + w / 2 - 0.5) < 0.012) x = 0.5 - w / 2;
    } else {
      let x1 = r0.x, y1 = r0.y, x2 = r0.x + r0.w, y2 = r0.y + r0.h;
      if (esq.includes("w")) x1 = limitar(r0.x + dx, 0, x2 - 0.05); else x2 = limitar(x2 + dx, x1 + 0.05, 1);
      if (esq.includes("n")) y1 = limitar(r0.y + dy, 0, y2 - 0.03); else y2 = limitar(y2 + dy, y1 + 0.03, 1);
      x = x1; y = y1; w = x2 - x1; h = y2 - y1;
    }
    c.destino = {x, y, w, h}; dibujarDestino(); posicionarRecuadros();
  }, confirmar);
}

// ------------------------------------------------------------------ visores
function ajustarVisores() {
  if (!E) return;
  const z = $("#zonaOrigen"), pm = piezaMedioSel(), W = pm ? pm.ancho : (V.videoWidth || E.origen.ancho), H = pm ? pm.alto : (V.videoHeight || E.origen.alto);
  const cw = z.clientWidth - 16, ch = z.clientHeight - 16, k = Math.min(cw / W, ch / H);
  const caja = $("#cajaOrigen"); caja.style.width = Math.max(10, W * k) + "px"; caja.style.height = Math.max(10, H * k) + "px";
  const zs = $("#zonaSalida"), ow = E.salida.ancho, oh = E.salida.alto, ks = Math.min((zs.clientWidth - 16) / ow, (zs.clientHeight - 16) / oh);
  const cwS = Math.max(10, Math.floor(ow * ks)), chS = Math.max(10, Math.floor(oh * ks));
  LZ.style.width = cwS + "px"; LZ.style.height = chS + "px";
  if (LZ.width !== Math.round(ow / 2) || LZ.height !== Math.round(oh / 2)) { LZ.width = Math.round(ow / 2); LZ.height = Math.round(oh / 2); }
  dibujarRecuadros();
}
window.addEventListener("resize", () => { ajustarVisores(); dibujarTimeline(); });

// Arrastre fluido: los nodos no se reconstruyen mientras se arrastra y los cambios se aplican como mucho una vez por fotograma.
function arrastrar(ev, nodo, fnMover, fnFin) {
  ev.preventDefault(); ev.stopPropagation();
  try { nodo.setPointerCapture(ev.pointerId); } catch (e) { /* sin captura */ }
  let ultimo = ev, pendiente = false;
  const pintar = () => { pendiente = false; fnMover(ultimo); };
  const mover = e => { ultimo = e; if (!pendiente) { pendiente = true; requestAnimationFrame(pintar); } };
  const fin = () => {
    nodo.removeEventListener("pointermove", mover); nodo.removeEventListener("pointerup", fin); nodo.removeEventListener("pointercancel", fin);
    if (pendiente) { pendiente = false; fnMover(ultimo); }
    fnFin();
  };
  nodo.addEventListener("pointermove", mover); nodo.addEventListener("pointerup", fin); nodo.addEventListener("pointercancel", fin);
}
const REC = {};
function dibujarRecuadros() {
  const ov = $("#overlay");
  if (!E) { ov.innerHTML = ""; ov.dataset.firma = ""; return; }
  const lista = rectasActivos(), firma = lista.map(r => r.clave).join("|");
  if (ov.dataset.firma !== firma) {
    ov.innerHTML = ""; ov.dataset.firma = firma;
    for (const k of Object.keys(REC)) delete REC[k];
    if (lista.length) for (const d of ["t", "b", "i", "d"]) { const q = document.createElement("div"); q.className = "dim"; q.dataset.d = d; ov.appendChild(q); }
    for (const r of lista) {
      const d = document.createElement("div"); d.className = "recuadro " + r.clase;
      d.innerHTML = `<span class="et">${r.et}</span>` + ["nw", "ne", "sw", "se"].map(c => `<i class="m ${c}" data-c="${c}"></i>`).join("");
      d.addEventListener("pointerdown", ev => empezarRecuadro(ev, r, d));
      ov.appendChild(d); REC[r.clave] = d;
    }
  }
  posicionarRecuadros();
}
function posicionarRecuadros() {
  if (!E) return;
  const W = ORI().ancho, H = ORI().alto, pct = v => (v * 100).toFixed(3) + "%";
  rectasActivos().forEach((r, n) => {
    const d = REC[r.clave]; if (!d) return;
    const rc = rectAspecto(rectDe(r.clave), W, H, r.asp);
    d.style.left = pct(rc.x); d.style.top = pct(rc.y); d.style.width = pct(rc.w); d.style.height = pct(rc.h);
    if (n === 0) {
      const f = (q, a, b, c, e) => { q.style.left = pct(a); q.style.top = pct(b); q.style.width = pct(c); q.style.height = pct(e); };
      for (const q of $("#overlay").querySelectorAll(".dim")) {
        if (q.dataset.d === "t") f(q, 0, 0, 1, rc.y);
        else if (q.dataset.d === "b") f(q, 0, rc.y + rc.h, 1, 1 - rc.y - rc.h);
        else if (q.dataset.d === "i") f(q, 0, rc.y, rc.x, rc.h);
        else f(q, rc.x + rc.w, rc.y, 1 - rc.x - rc.w, rc.h);
      }
    }
  });
}
function empezarRecuadro(ev, r0, nodo) {
  const r = rectasActivos().find(x => x.clave === r0.clave) || r0;      // la proporciÃ³n puede haber cambiado desde que se creÃ³ el nodo
  const W = ORI().ancho, H = ORI().alto, caja = $("#cajaOrigen").getBoundingClientRect();
  const ini = rectAspecto(rectDe(r.clave), W, H, r.asp), esq = ev.target.dataset.c || null;
  const px0 = {x: ini.x * W, y: ini.y * H, w: ini.w * W, h: ini.h * H};
  const sx = ev.clientX, sy = ev.clientY, escala = W / caja.width;
  arrastrar(ev, nodo, e => {
    const dx = (e.clientX - sx) * escala, dy = (e.clientY - sy) * escala;
    let x, y, w, h;
    if (!esq) { w = px0.w; h = px0.h; x = limitar(px0.x + dx, 0, W - w); y = limitar(px0.y + dy, 0, H - h); }
    else {
      const sgnx = esq.includes("e") ? 1 : -1, sgny = esq.includes("s") ? 1 : -1;
      const ax = sgnx === 1 ? px0.x : px0.x + px0.w, ay = sgny === 1 ? px0.y : px0.y + px0.h;
      const pxm = (e.clientX - caja.left) * escala;
      w = Math.max(W * 0.04, Math.abs(pxm - ax));
      w = Math.min(w, sgnx === 1 ? W - ax : ax, (sgny === 1 ? H - ay : ay) * r.asp);
      h = w / r.asp; x = sgnx === 1 ? ax : ax - w; y = sgny === 1 ? ay : ay - h;
    }
    ponerRect(r.clave, {x: x / W, y: y / H, w: w / W, h: h / H});
    posicionarRecuadros(); sincronizarZoom();
  }, confirmar);
}


// ------------------------------------------------------------------ dibujo del resultado
const OFFC = [];
const COM = $("#cOriMedio");                                // Â«OrigenÂ» cuando se edita la plantilla de un vÃ­deo aÃ±adido
let claveOri = "";
function dibujarOrigenMedio() {
  const p = piezaMedioSel(), usar = !!p && ALCANCE === "tramo", clave = usar ? p.id + "|" + p.ancho + "x" + p.alto : "";
  if (clave !== claveOri) {
    claveOri = clave; COM.hidden = !usar; V.style.visibility = usar ? "hidden" : ""; ajustarVisores(); dibujarRecuadros();
    $("#infoOrigen").textContent = usar ? `${p.nombre} Â· ${p.ancho}Ã—${p.alto}` : `${E.origen.ancho}Ã—${E.origen.alto} Â· ${fmt(E.origen.duracion)}`;
  }
  if (!usar) return;
  const W = p.ancho, H = p.alto, cw = Math.min(640, W), ch = Math.max(1, Math.round(cw * H / W));
  if (COM.width !== cw || COM.height !== ch) { COM.width = cw; COM.height = ch; }
  const c = COM.getContext("2d"), el = ELV[p.id];
  c.fillStyle = "#000"; c.fillRect(0, 0, cw, ch);
  if (el && el.readyState >= 2) c.drawImage(el, 0, 0, cw, ch);
  else { c.fillStyle = "#9aa"; c.font = "15px sans-serif"; c.textAlign = "center"; c.fillText("Pon el cabezal sobre esta pieza para verla aquÃ­", cw / 2, ch / 2); }
}
const OFFL = document.createElement("canvas");            // capa temporal para zoom / posiciÃ³n / transparencia
let ELV = {};                                              // id de pieza de video -> elemento <video> que le toca este instante
function rutaRedonda(ctx, x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h / 2)); ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, w, h, r);
  else { ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
}
function puntoSeguimiento(seg) {
  const pts = seg?.trayectoria || [];
  if (!pts.length) return null;
  const t = salAOri(T);
  if (t == null) return pts[0];
  let a = pts[0];
  for (let i = 1; i < pts.length; i++) {
    const b = pts[i];
    if (b.t >= t) {
      const u = b.t > a.t ? limitar((t - a.t) / (b.t - a.t), 0, 1) : 0;
      return {x:a.x+(b.x-a.x)*u, y:a.y+(b.y-a.y)*u, cara:u < .5 ? a.cara : b.cara};
    }
    a = b;
  }
  return a;
}
function dibujarCapas(enc, el, ctx, cw, ch, vw, vh) {
  const k = cw / E.salida.ancho, W = ORI().ancho, H = ORI().alto;
  (enc.capas || []).forEach((c, i) => {
    const d = c.destino, b = c.borde.ancho * k, dx = d.x * cw, dy = d.y * ch, dw = d.w * cw, dh = d.h * ch;
    const iw = Math.max(2, dw - 2 * b), ih = Math.max(2, dh - 2 * b);
    let rc, w, h;
    if (c.ajuste === "llenar") { rc = rectAspecto(c.fuente, W, H, iw / ih); w = iw; h = ih; }
    else { rc = c.fuente; const s = Math.min(iw / (rc.w * vw), ih / (rc.h * vh)); w = rc.w * vw * s; h = rc.h * vh * s; }
    const seg = enc.seguimiento_cara, seguimiento = c.rol === "cam" && seg?.activo && seg.trayectoria?.length;
    if (seguimiento) {
      const p = puntoSeguimiento(seg), zoom = limitar(+seg.zoom || 1.2, 1, 2.5);
      const sw = Math.min(c.fuente.w, c.fuente.w / zoom), sh = Math.min(c.fuente.h, c.fuente.h / zoom);
      rc = {x:limitar(p.x-sw/2,c.fuente.x,c.fuente.x+c.fuente.w-sw), y:limitar(p.y-sh/2,c.fuente.y,c.fuente.y+c.fuente.h-sh), w:sw,h:sh};
      if (c.ajuste === "llenar") rc = rectAspecto(rc, W, H, iw / ih);
      const s = c.ajuste === "llenar" ? Math.max(iw/(rc.w*vw),ih/(rc.h*vh)) : Math.min(iw/(rc.w*vw),ih/(rc.h*vh));
      w=rc.w*vw*s; h=rc.h*vh*s;
    }
    const ow_ = w + 2 * b, oh_ = h + 2 * b, ox = dx + (dw - ow_) / 2, oy = dy + (dh - oh_) / 2, ix = ox + b, iy = oy + b;
    const forma = i === 0 ? "rect" : c.forma, rad = forma === "circulo" ? Math.min(ow_, oh_) / 2 : forma === "redondeado" ? c.radio * Math.min(ow_, oh_) : 0;
    ctx.save();
    if (rad > 0) { rutaRedonda(ctx, ox, oy, ow_, oh_, rad); ctx.clip(); }
    if (b > 0) { ctx.fillStyle = c.borde.color; ctx.fillRect(ox, oy, ow_, oh_); }
    if (b > 0 && rad > 0) { rutaRedonda(ctx, ix, iy, w, h, Math.max(0, rad - b)); ctx.clip(); }
    else if (b > 0) { ctx.beginPath(); ctx.rect(ix, iy, w, h); ctx.clip(); }
    const sx = rc.x * vw, sy = rc.y * vh, sw = rc.w * vw, sh = rc.h * vh;
    if (c.desenfoque > 0) {
      const f = 6, ow2 = Math.max(8, Math.round(w / f)), oh2 = Math.max(8, Math.round(h / f)), sg = Math.max(0.5, c.desenfoque / 20), pad = Math.ceil(sg * 2);
      let o = OFFC[i]; if (!o) o = OFFC[i] = document.createElement("canvas");
      if (o.width !== ow2 || o.height !== oh2) { o.width = ow2; o.height = oh2; }
      const oc = o.getContext("2d"); oc.clearRect(0, 0, ow2, oh2); oc.filter = `blur(${sg}px)`;
      oc.drawImage(el, sx, sy, sw, sh, -pad, -pad, ow2 + 2 * pad, oh2 + 2 * pad); oc.filter = "none";
      ctx.drawImage(o, ix, iy, w, h);
    } else ctx.drawImage(el, sx, sy, sw, sh, ix, iy, w, h);
    if (c.oscurecer > 0) { ctx.fillStyle = `rgba(0,0,0,${c.oscurecer})`; ctx.fillRect(ix, iy, w, h); }
    ctx.restore();
  });
}
// El clip con una plantilla (la general o la propia de ese tramo) sobre ``ctx``.
function dibujarEncuadre(enc, el, ctx, cw, ch, corte={izquierda:0,derecha:0,arriba:0,abajo:0}) {
  const W = ORI().ancho, H = ORI().alto, vw = el.videoWidth, vh = el.videoHeight, m = enc.modo;
  const dib = (rc, dx, dy, dw, dh) => {const x=corte.izquierda+rc.x*(1-corte.izquierda-corte.derecha),y=corte.arriba+rc.y*(1-corte.arriba-corte.abajo),w=rc.w*(1-corte.izquierda-corte.derecha),h=rc.h*(1-corte.arriba-corte.abajo);ctx.drawImage(el,x*vw,y*vh,w*vw,h*vh,dx,dy,dw,dh);};
  if (m === "recorte") dib(rectAspecto(enc.recorte, W, H, aspectos().recorte), 0, 0, cw, ch);
  else if (m === "capas") dibujarCapas(enc, el, ctx, cw, ch, vw, vh);
  else if (m === "dividido" || m === "tres") {
    const k = ch / E.salida.alto, lin = enc.linea || {ancho: 0};
    franjas(enc).forEach((f, i) => {
      dib(rectAspecto(rectDe(f.clave, enc), W, H, E.salida.ancho / f.alto), 0, f.y0 * k, cw, f.alto * k);
      if (i > 0 && lin.ancho > 0) { ctx.fillStyle = lin.color; ctx.fillRect(0, f.y0 * k - lin.ancho * k / 2, cw, lin.ancho * k); }
      else if (i > 0) { ctx.fillStyle = "rgba(0,0,0,.6)"; ctx.fillRect(0, f.y0 * k - 1, cw, 2); }
    });
  } else {
    const pw = Math.max(8, cw / 8 | 0), ph = Math.max(8, ch / 8 | 0); let o = OFFC[9]; if (!o) o = OFFC[9] = document.createElement("canvas");
    if (o.width !== pw || o.height !== ph) { o.width = pw; o.height = ph; }
    const oc = o.getContext("2d"), cob = Math.max(pw / vw, ph / vh); oc.filter = "blur(2px)"; oc.drawImage(el, (pw - vw * cob) / 2, (ph - vh * cob) / 2, vw * cob, vh * cob); oc.filter = "none";
    ctx.drawImage(o, 0, 0, cw, ch);
    ctx.fillStyle = "rgba(0,0,0,.25)"; ctx.fillRect(0, 0, cw, ch);
    const fit = Math.min(cw / vw, ch / vh); ctx.drawImage(el, (cw - vw * fit) / 2, (ch - vh * fit) / 2, vw * fit, vh * fit);
  }
}
const rectParam = (p,k) => { const r = (p.encuadre || E.encuadre)?.recorte; return ({rec_x:r?.x||0,rec_y:r?.y||0,rec_w:r?.w||1,rec_h:r?.h||1})[k]; };
const parametro = (p, k) => { const v = k.startsWith("rec_") ? PZ.valorKf({...p,[k]:rectParam(p,k)},k,T-p.t) : PZ.valorKf(p,k,T-p.t); return Number.isFinite(v) ? v : (k === "rotacion" ? 0 : v); };
function factorFundido(p) {
  const tl = T - p.t, tr = PZ.fin(p) - T; let f = 1;
  if (p.fundido_in > 0) f = Math.min(f, tl / p.fundido_in);
  if (p.fundido_out > 0) f = Math.min(f, tr / p.fundido_out);
  return limitar(f, 0, 1);
}
function dibujarPieza(p, cw, ch) {
  let el, ew, eh;
  if (p.tipo === "imagen") { const fs = FUENTE[urlMedio(p)]; if (!fs || !fs.img) return; el = fs.img; ew = el.naturalWidth; eh = el.naturalHeight; }
  else { el = ELV[p.id]; if (!el || el.readyState < 2) return; ew = el.videoWidth; eh = el.videoHeight; }
  if (!ew) return;
  const recuadro = p.fuente === "medio" && p.modo === "recuadro";
  const z = recuadro ? 1 : parametro(p, "zoom"), px = recuadro ? 0 : parametro(p, "pos_x"), py = recuadro ? 0 : parametro(p, "pos_y");
  let alfa = parametro(p, "opacidad") * factorFundido(p), ox = 0, oy = 0;
  const tr = p.trans_in || {tipo: "ninguna", dur: 0.5}, tl = T - p.t;
  if (tr.tipo !== "ninguna" && tl < tr.dur) {
    const u = limitar(tl / tr.dur, 0, 1);
    if (tr.tipo === "disolver") alfa *= u;
    else if (!recuadro) {
      if (tr.tipo === "deslizar_izq") ox = -cw * (1 - u); else if (tr.tipo === "deslizar_der") ox = cw * (1 - u);
      else if (tr.tipo === "deslizar_arriba") oy = -ch * (1 - u); else if (tr.tipo === "deslizar_abajo") oy = ch * (1 - u);
    }
  }
  if (alfa <= 0.002) return;
  const trf=p.recorte_bordes||{izquierda:0,derecha:0,arriba:0,abajo:0},tx=(p.tras_x||0)*cw,ty=(p.tras_y||0)*ch,rot=parametro(p,"rotacion")||0;
  const simple = z <= 1.001 && Math.abs(px) < 1e-3 && Math.abs(py) < 1e-3 && !ox && !oy && !tx && !ty && !rot && !p.flip_h && !p.flip_v && !Object.values(trf).some(Boolean);
  let ctx = CTX;
  if (!simple) {
    if (OFFL.width !== cw || OFFL.height !== ch) { OFFL.width = cw; OFFL.height = ch; }
    ctx = OFFL.getContext("2d"); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cw, ch);
  }
  try {
    CTX.save();
    if (simple) CTX.globalAlpha = alfa;
    const rcx=recuadro?(p.recuadro.x+p.recuadro.w/2)*cw:cw/2,rcy=recuadro?(p.recuadro.y*ch+p.recuadro.w*cw*eh/ew/2):ch/2;
    ctx.translate(rcx,rcy);ctx.rotate(rot*Math.PI/180);ctx.scale(p.flip_h?-1:1,p.flip_v?-1:1);ctx.translate(-rcx,-rcy);
    const recAnim=(p.encuadre||E.encuadre)?.modo==="recorte"&&["rec_x","rec_y","rec_w","rec_h"].some(k=>p.kf?.[k]?.length);
    if (p.fuente === "clip" || (p.tipo === "video" && p.encuadre && p.ancho > 0)) {
      ORI_OVR = p.fuente === "clip" ? E.origen : {ancho: p.ancho, alto: p.alto};
      try { if(recAnim){const ra=rectAspecto({x:parametro(p,"rec_x"),y:parametro(p,"rec_y"),w:parametro(p,"rec_w"),h:parametro(p,"rec_h")},ORI().ancho,ORI().alto,aspectos().recorte),x=ra.x,y=ra.y,w=ra.w,h=ra.h;ctx.drawImage(el,(trf.izquierda+x*(1-trf.izquierda-trf.derecha))*ew,(trf.arriba+y*(1-trf.arriba-trf.abajo))*eh,w*(1-trf.izquierda-trf.derecha)*ew,h*(1-trf.arriba-trf.abajo)*eh,0,0,cw,ch);}else dibujarEncuadre(p.encuadre || E.encuadre, el, ctx, cw, ch, trf); } finally { ORI_OVR = null; }
    }
    else if (recuadro) { const w = p.recuadro.w * cw; ctx.drawImage(el,trf.izquierda*ew,trf.arriba*eh,ew*(1-trf.izquierda-trf.derecha),eh*(1-trf.arriba-trf.abajo),p.recuadro.x*cw,p.recuadro.y*ch,w,w*eh/ew); }
    else { const k = Math.max(cw / ew, ch / eh), w = ew * k, h = eh * k; ctx.drawImage(el,trf.izquierda*ew,trf.arriba*eh,ew*(1-trf.izquierda-trf.derecha),eh*(1-trf.arriba-trf.abajo),(cw-w)/2,(ch-h)/2,w,h); }
    if (!simple) {
      const zz = Math.max(1, z), sw = cw / zz, sh = ch / zz, sx = (cw - sw) / 2 * (1 + limitar(px, -1, 1)), sy = (ch - sh) / 2 * (1 + limitar(py, -1, 1));
      CTX.globalAlpha = alfa; CTX.drawImage(OFFL, sx, sy, sw, sh, ox+tx, oy+ty, cw, ch);
    }
    CTX.restore();
  } catch (e) { CTX.restore(); /* el vÃ­deo aÃºn no tiene fotograma */ }
}

// ------------------------------------------------------------------ texto (Text+)
const CAJAS_TEXTO = {};
function dibujarTexto(p, cw, ch) {
  const tx = p.texto, k = cw / E.salida.ancho, tl = T - p.t, tr = PZ.fin(p) - T, d = tx.anim_dur, dd = Math.max(0.05, Math.min(d, p.dur));
  let alfa = parametro(p, "opacidad");
  const fi = Math.max(p.fundido_in, tx.anim_in === "fundido" ? d : 0), fo = Math.max(p.fundido_out, tx.anim_out === "fundido" ? d : 0);
  if (fi > 0) alfa *= limitar(tl / fi, 0, 1);
  if (fo > 0) alfa *= limitar(tr / fo, 0, 1);
  if (alfa <= 0.002) return;
  let dx = 0, dy = 0, esc = 1;
  if (tx.anim_in !== "ninguna" && tl < dd) {
    const u = limitar(tl / dd, 0, 1);
    if (tx.anim_in === "subir") dy = (1 - u) * E.salida.alto * 0.08; else if (tx.anim_in === "bajar") dy = -(1 - u) * E.salida.alto * 0.08;
    else if (tx.anim_in === "izquierda") dx = (1 - u) * E.salida.ancho * 0.15; else if (tx.anim_in === "derecha") dx = -(1 - u) * E.salida.ancho * 0.15;
    else if (tx.anim_in === "pop") esc = u < 0.7 ? 1.12 * u / 0.7 : 1.12 - 0.12 * (u - 0.7) / 0.3;
  }
  if (tx.anim_out === "pop" && tr < dd) esc *= limitar(tr / dd, 0, 1);
  let contenido = tx.mayusculas ? tx.contenido.toUpperCase() : tx.contenido;
  const lineas = contenido.split("\n");
  let visibles = Infinity;
  if (tx.anim_in === "maquina") {
    const n = Math.max(1, contenido.replace(/\n/g, "").length), paso = Math.max(0.03, Math.min(0.12, (d * 2) / n));
    visibles = Math.min(n, Math.floor(tl / paso) + 1);
  }
  CTX.save();
  CTX.globalAlpha = alfa;
  CTX.font = `${tx.cursiva ? "italic " : ""}${tx.negrita ? "bold " : ""}${tx.tamano * k}px "${tx.fuente}", "Segoe UI", Arial, sans-serif`;
  CTX.textBaseline = "middle"; CTX.textAlign = "left";
  if ("letterSpacing" in CTX) CTX.letterSpacing = (tx.espaciado * k) + "px";
  const lh = tx.tamano * k * 1.2, pre = "\u00a0".repeat(tx.icono_espacios || 0), anchos = lineas.map((l, i) => CTX.measureText((i ? "" : pre) + l).width), caja = tx.fondo === "caja";
  const X0 = tx.x * cw + dx * k, Y0 = tx.y * ch + dy * k, top = Y0 - lh * lineas.length / 2, pad = caja ? Math.max(10, tx.tamano / 6) * k : 0;
  CTX.translate(X0, Y0); CTX.scale(esc, esc); CTX.translate(-X0, -Y0);
  let restantes = visibles, minx = 1e9, maxx = -1e9;
  lineas.forEach((l, i) => {
    const y = top + lh * (i + 0.5), w = anchos[i], xs = tx.alineacion === "izquierda" ? X0 : tx.alineacion === "derecha" ? X0 - w : X0 - w / 2;
    minx = Math.min(minx, xs - pad); maxx = Math.max(maxx, xs + w + pad);
    const parte = restantes >= l.length ? l : l.slice(0, Math.max(0, restantes)); restantes -= l.length;
    if (!parte) return;
    if (caja) { CTX.fillStyle = tx.color_fondo + "d0"; CTX.fillRect(xs - pad, y - lh / 2, w + 2 * pad, lh); }
    if (tx.sombra > 0) { CTX.shadowColor = tx.color_sombra; CTX.shadowOffsetX = tx.sombra * k; CTX.shadowOffsetY = tx.sombra * k; }
    if (!caja && tx.grosor_contorno > 0) { CTX.lineJoin = "round"; CTX.lineWidth = tx.grosor_contorno * 2 * k; CTX.strokeStyle = tx.color_contorno; CTX.strokeText((i ? "" : pre) + parte, xs, y); }
    CTX.fillStyle = tx.color; CTX.fillText((i ? "" : pre) + parte, xs, y);
    CTX.shadowColor = "transparent";
  });
  CAJAS_TEXTO[p.id] = {x: minx, y: top, w: maxx - minx, h: lh * lineas.length, cw, ch};
  CTX.restore();
}

function dibujar() {
  if (!E) return;
  const cw = LZ.width, ch = LZ.height;
  CTX.setTransform(1, 0, 0, 1, 0, 0); CTX.globalAlpha = 1;
  CTX.fillStyle = "#000"; CTX.fillRect(0, 0, cw, ch);
  const oc = ocultas(), fin = PZ.fin;
  const activas = E.piezas.filter(p => (p.tipo === "video" || p.tipo === "imagen") && T >= p.t - 1e-6 && T < fin(p) && !oc.has(p.carril));
  activas.sort((a, b) => PZ.numero(a.carril) - PZ.numero(b.carril) || a.t - b.t);
  for (const p of activas) dibujarPieza(p, cw, ch);
  const textos = E.piezas.filter(p => p.tipo === "texto" && T >= p.t - 1e-6 && T < fin(p) && !oc.has(p.carril)).sort((a, b) => PZ.numero(a.carril) - PZ.numero(b.carril));
  for (const p of textos) dibujarTexto(p, cw, ch);
  const ts = salAOri(T);
  if (ts !== null) dibujarSubtitulo(cw, ch, ts);
}



function paginas(l, n) {
  const pal = l.palabras, out = [];
  for (let i = 0; i < pal.length; i += n) {
    const trozo = pal.slice(i, i + n), sig = pal[i + n];
    out.push({inicio: trozo[0].inicio, fin: sig ? sig.inicio : l.fin, palabras: trozo});
  }
  return out;
}
function dibujarSubtitulo(cw, ch, ts) {
  const sub = E.subtitulos; if (!sub.activos || !sub.lineas.length) return;
  const st = sub.estilo, k = cw / E.salida.ancho;
  const l = sub.lineas.find(x => ts >= x.inicio && ts < x.fin); if (!l) return;
  const pag = paginas(l, st.palabras_por_pagina).find(p => ts >= p.inicio && ts < Math.max(p.fin, p.inicio + 0.05)); if (!pag) return;
  let activa = -1;
  if (st.resaltar_palabra) pag.palabras.forEach((w, i) => { const sig = pag.palabras[i + 1]; if (ts >= w.inicio && ts < (sig ? sig.inicio : pag.fin)) activa = i; });
  CTX.save();
  CTX.font = `${st.cursiva ? "italic " : ""}${st.negrita ? "bold " : ""}${st.tamano * k}px "${st.fuente}", "Segoe UI", Arial, sans-serif`;
  CTX.textBaseline = "middle"; CTX.textAlign = "left";
  const palabras = pag.palabras.map(w => st.mayusculas ? w.texto.toUpperCase() : w.texto);
  const esp = CTX.measureText(" ").width, maxW = (E.salida.ancho - 80) * k;
  const lineas = []; let cur = [], ancho = 0;
  palabras.forEach((t, i) => {
    const ww = CTX.measureText(t).width;
    if (cur.length && ancho + esp + ww > maxW) { lineas.push({p: cur, w: ancho}); cur = []; ancho = 0; }
    ancho += (cur.length ? esp : 0) + ww; cur.push({t, ww, i, c: pag.palabras[i].color || (l.hablante && st.hablantes ? st.hablantes[l.hablante - 1] : st.color)});
  });
  if (cur.length) lineas.push({p: cur, w: ancho});
  const alto = st.tamano * k * 1.2, y0 = st.posicion_y * ch - (lineas.length * alto) / 2 + alto / 2;
  lineas.forEach((ln, j) => {
    const y = y0 + j * alto; let x = (cw - ln.w) / 2;
    if (st.fondo === "caja") { const pad = Math.max(10, st.tamano / 6) * k; CTX.fillStyle = st.color_fondo + "d0"; CTX.fillRect(x - pad, y - alto / 2, ln.w + 2 * pad, alto); }
    for (const w of ln.p) {
      if (st.fondo !== "caja" && st.grosor_contorno > 0) { CTX.lineJoin = "round"; CTX.lineWidth = st.grosor_contorno * 2 * k; CTX.strokeStyle = st.color_contorno; CTX.strokeText(w.t, x, y); }
      CTX.fillStyle = w.i === activa ? st.color_resaltado : w.c; CTX.fillText(w.t, x, y); x += w.ww + esp;
    }
  });
  CTX.restore();
}

// ------------------------------------------------------------------ fuentes de medios y reproducciÃ³n
// Cada fuente (el clip o un medio aÃ±adido) puede necesitar varios <video> a la vez (dos trozos del mismo clip en pistas distintas):
// FUENTE[url].els es un pequeÃ±o reparto de elementos; el 0 del clip es el visor Â«OrigenÂ» (#v).
const dormir = ms => new Promise(r => setTimeout(r, ms));
const FUENTE = {};
const urlMedio = p => `/editor/api/${ID}/medio/${p.mid}`;
const MAX_ELEMENTOS = 4;
function crearVideo(url) { const el = document.createElement("video"); el.preload = "auto"; el.playsInline = true; el.src = url; return el; }
function fuenteMedio(p) {
  if (!p.mid) return null;
  const url = urlMedio(p);
  if (!FUENTE[url]) { const fs = FUENTE[url] = {estado: "cargando", els: [], img: null, mensaje: ""}; cargarFuente(fs, p, url); }
  return FUENTE[url];
}
async function cargarFuente(fs, p, url) {
  try {
    for (;;) {
      const d = await api(`medio/${p.mid}/estado`);
      if (d.estado === "listo") break;
      if (d.estado === "error") throw new Error(d.mensaje || "No se pudo preparar el medio.");
      await dormir(600);
    }
    if (p.tipo === "imagen") {
      const el = new Image(); el.src = url;
      await new Promise(r => { el.onload = r; el.onerror = r; });
      if (!el.naturalWidth) throw new Error("No se pudo cargar la imagen.");
      fs.img = el;
    } else {
      const el = crearVideo(url);
      await new Promise(r => { el.onloadedmetadata = r; el.onerror = r; });
      if (el.error) throw new Error("El navegador no pudo reproducir este medio.");
      fs.els.push({el, clave: "", ultPlay: 0});
    }
    fs.estado = "listo";
  } catch (e) { fs.estado = "error"; fs.mensaje = e.message || String(e); }
}
const velDe = p => p.velocidad || 1;
const volumenEn = p => limitar(parametro(p, "volumen") * factorFundido(p), 0, 1);

// QuÃ© fuentes hacen falta ahora mismo. Un trozo de audio va Â«montadoÂ» en el elemento del video que estÃ¡ alineado con Ã©l (mismo origen y velocidad).
function necesidades() {
  const mud = silenciadas(), oc = ocultas(), fin = PZ.fin;
  const act = E.piezas.filter(p => (p.tipo === "video" || p.tipo === "audio") && T >= p.t - 1e-6 && T < fin(p) - 1e-6);
  const origen = p => p.desde + (T - p.t) * velDe(p), lista = [];
  const grupos = [
    {url: () => URL_CLIP, v: act.filter(p => p.fuente === "clip" && p.tipo === "video" && !oc.has(p.carril)), a: act.filter(p => p.fuente === "clip" && p.tipo === "audio")},
  ];
  const mids = [...new Set(act.filter(p => p.fuente === "medio" && p.mid).map(p => p.mid))];
  for (const mid of mids) grupos.push({url: () => `/editor/api/${ID}/medio/${mid}`, mid, v: act.filter(p => p.fuente === "medio" && p.mid === mid && p.tipo === "video" && !oc.has(p.carril)), a: act.filter(p => p.fuente === "medio" && p.mid === mid && p.tipo === "audio")});
  for (const g of grupos) {
    const usadas = new Set(), url = g.url();
    g.v.sort((a, b) => PZ.numero(a.carril) - PZ.numero(b.carril));
    for (const pv of g.v) {
      const m = g.a.find(pa => !usadas.has(pa.id) && Math.abs(velDe(pa) - velDe(pv)) < 1e-3 && Math.abs(origen(pa) - origen(pv)) < 0.03);
      if (m) usadas.add(m.id);
      lista.push({url, v: pv, a: m || null, src: origen(pv), vel: velDe(pv), clave: pv.id + "|" + (m ? m.id : ""), mid: g.mid});
    }
    for (const pa of g.a) if (!usadas.has(pa.id) && !mud.has(pa.carril)) lista.push({url, v: null, a: pa, src: origen(pa), vel: velDe(pa), clave: "|" + pa.id, mid: g.mid});
  }
  return lista;
}
function sincronizarMedia() {
  if (!E) return;
  const mud = silenciadas();
  for (const p of E.piezas) if (p.fuente === "medio" && p.mid) fuenteMedio(p);      // empieza a preparar todos los medios
  let lista = necesidades();
  if (!reproduciendo) lista = lista.filter(n => n.v);          // en pausa solo hace falta la imagen
  // el visor Â«OrigenÂ» sigue al tramo seleccionado si estÃ¡ a la vista, si no al primero que haya
  const p0 = piezaClipSel();
  lista.sort((a, b) => (b.url === URL_CLIP) - (a.url === URL_CLIP) || (b.v && p0 && b.v.id === p0.id) - (a.v && p0 && a.v.id === p0.id) || (!!b.v - !!a.v));
  ELV = {};
  const porUrl = {};
  for (const n of lista) (porUrl[n.url] = porUrl[n.url] || []).push(n);
  const tocados = new Set();
  for (const [url, ns] of Object.entries(porUrl)) {
    const fs = url === URL_CLIP ? FUENTE[URL_CLIP] : FUENTE[url] || (ns[0].v || ns[0].a ? fuenteMedio(ns[0].v || ns[0].a) : null);
    if (!fs || fs.estado !== "listo") continue;
    const libres = new Set(fs.els), asignados = new Map();
    if (url === URL_CLIP && ns[0].v) { asignados.set(ns[0], fs.els[0]); libres.delete(fs.els[0]); }
    for (const n of ns) if (!asignados.has(n)) { const h = fs.els.find(h => libres.has(h) && h.clave === n.clave); if (h) { asignados.set(n, h); libres.delete(h); } }
    for (const n of ns) {
      if (asignados.has(n)) continue;
      let h = [...libres][0];
      if (!h && fs.els.length < MAX_ELEMENTOS) { h = {el: crearVideo(url), clave: "", ultPlay: 0}; fs.els.push(h); }
      if (h) { asignados.set(n, h); libres.delete(h); }
    }
    for (const [n, h] of asignados) {
      tocados.add(h); h.clave = n.clave;
      const el = h.el;
      if (n.v) ELV[n.v.id] = el;
      const silencio = !n.a || mud.has(n.a.carril);
      el.muted = silencio; el.volume = silencio ? 0 : volumenEn(n.a);
      const ritmo = limitar(n.vel, 0.0625, 16); if (Math.abs(el.playbackRate - ritmo) > 1e-3) el.playbackRate = ritmo;
      if (reproduciendo) {
        if (el.paused) { const ahora = performance.now(); if (ahora - h.ultPlay > 400) { h.ultPlay = ahora; el.currentTime = n.src; el.play().catch(() => {}); } }
        else if (Math.abs(el.currentTime - n.src) > 0.3) el.currentTime = n.src;
      } else {
        if (!el.paused) el.pause();
        if (el.readyState > 0 && Math.abs(el.currentTime - n.src) > 0.035) el.currentTime = n.src;
      }
    }
  }
  for (const fs of Object.values(FUENTE)) for (const h of fs.els) if (!tocados.has(h)) { h.clave = ""; if (!h.el.paused) h.el.pause(); }
}
function pausarTodo() { for (const fs of Object.values(FUENTE)) for (const h of fs.els) if (!h.el.paused) h.el.pause(); }

// ------------------------------------------------------------------ reproducciÃ³n
function ir(t) {
  T = limitar(t, 0, durSalida());
  sincronizarMedia(); actualizarReloj(); actualizarTransformBox();
}
function actualizarReloj() { $("#reloj").textContent = `${fmt(T)} / ${fmt(durSalida())}`; }
let ultimoT = 0;
function avisoReproduccion(txt) { $("#estadoGuardado").textContent = txt; }
function marcarBoton() { $("#bPlay").textContent = reproduciendo ? "â¸" : "â–¶"; }
function reproducir() {
  if (!E) return;
  if (!V.videoWidth || V.error) { avisoReproduccion(V.error ? "La vista previa no se pudo cargar: recarga el editor." : "La vista previa aÃºn se estÃ¡ preparandoâ€¦"); return; }
  if (durSalida() < 0.05) return;
  if (T >= durSalida() - 0.05) T = 0;
  reproduciendo = true; ultimoT = performance.now(); marcarBoton(); sincronizarMedia();
}
function pausar() { reproduciendo = false; pausarTodo(); marcarBoton(); }
function alternar() { if (reproduciendo) pausar(); else reproducir(); }
function avanzarReproduccion(ahora) {
  const dt = Math.min(0.25, Math.max(0, (ahora - ultimoT) / 1000)); ultimoT = ahora;
  T += dt;
  if (T >= durSalida()) { T = durSalida(); pausar(); }
  actualizarReloj();
  const px = TL.margen + T * TL.px, sc = $("#scroll");
  if (px > sc.scrollLeft + sc.clientWidth - 40 || px < sc.scrollLeft) sc.scrollLeft = Math.max(0, px - 60);
}
let erroresBucle = 0, ultimaFirmaInsp = "";
function bucle(ahora) {
  requestAnimationFrame(bucle);                     // primero: un fallo en el cuerpo nunca puede detener el ciclo
  try {
    if (E) {
      if (reproduciendo) avanzarReproduccion(ahora || performance.now());
      sincronizarMedia(); dibujar(); actualizarTransformBox(); dibujarOrigenMedio(); dibujarTimeline(); posicionarNodoTexto();
      const firma = sel && sel.tipo === "pieza" ? T.toFixed(2) + "|" + sel.id : "";
      if (firma !== ultimaFirmaInsp) { ultimaFirmaInsp = firma; valoresParametros(); }
    }
  } catch (e) {
    if (erroresBucle++ < 5) { console.error(e); avisoReproduccion("Error interno al dibujar: " + (e.message || e)); }
  }
}

// ------------------------------------------------------------------ lÃ­nea de tiempo
const COLORES = {clipV: ["#2f6fb5", "#3d86d6"], clipA: ["#2a6e50", "#2f8a63"], medV: ["#b7782a", "#e0993f"], img: ["#b24f8c", "#d86eaa"], medA: ["#2f9c78", "#45c096"], txt: ["#8a6d1f", "#c4a030"]};
let tlSucio = true, ultimaFirmaTl = "";
const tocar = () => { tlSucio = true; };
function colorDe(p, elegida) {
  const c = p.tipo === "texto" ? COLORES.txt : p.tipo === "imagen" ? COLORES.img : p.fuente === "clip" ? (p.tipo === "audio" ? COLORES.clipA : COLORES.clipV) : (p.tipo === "audio" ? COLORES.medA : COLORES.medV);
  return c[elegida ? 1 : 0];
}
function colorEnlace(id) { let h = 0; for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 360; return `hsl(${h},85%,65%)`; }
function layout() {
  const L = [], pi = E.pistas;
  for (let n = pi.video; n >= 1; n--) L.push({id: "V" + n, fam: "v", n, alto: n === 1 ? 46 : 38});
  for (let n = 1; n <= pi.audio; n++) L.push({id: "A" + n, fam: "a", n, alto: n === 1 ? 46 : 38});
  L.push({id: "S", fam: "s", alto: 34});
  let y = TL.altoRegla + 4;
  for (const c of L) { c.y0 = y; c.y1 = y + c.alto; y = c.y1; }
  TL.carriles = L; TL.alto = y + 6;
  return L;
}
const carrilPorId = id => (TL.carriles.length ? TL.carriles : layout()).find(c => c.id === id) || null;
function carrilCercano(y, fam) {
  const L = (TL.carriles.length ? TL.carriles : layout()).filter(c => c.fam === fam);
  if (!L.length) return null;
  return L.reduce((m, c) => (Math.abs((c.y0 + c.y1) / 2 - y) < Math.abs((m.y0 + m.y1) / 2 - y) ? c : m));
}
function picosMedio(mid) {
  if (!mid) return [];
  if (!(mid in PICOS_MEDIO)) { PICOS_MEDIO[mid] = []; api(`medio/${mid}/onda`).then(o => { PICOS_MEDIO[mid] = o.picos || []; tocar(); }).catch(() => {}); }
  return PICOS_MEDIO[mid];
}
function construirEtiquetas() {
  const cont = $("#etiqInt"), L = layout(); cont.innerHTML = ""; cont.style.height = TL.alto + "px";
  const P = E.pistas;
  for (const c of L) {
    const d = document.createElement("div"); d.className = "et-carril"; d.style.top = c.y0 + "px"; d.style.height = c.alto + "px";
    d.innerHTML = `<span>${c.fam === "s" ? "Subs" : c.id}</span>`;
    if (c.fam !== "s") {
      const bt = document.createElement("div"); bt.className = "bt";
      const nuevo = (clave, on, txt, ayuda) => { const b = document.createElement("button"); b.textContent = txt; b.title = ayuda; b.className = on ? "on" : ""; b.onclick = () => alternarPista(c.id, clave); bt.appendChild(b); };
      const bloq = P.bloqueadas.includes(c.id), mudo = P.silenciadas.includes(c.id), oculto = P.ocultas.includes(c.id);
      nuevo("bloqueadas", bloq, bloq ? "ðŸ”’" : "ðŸ”“", bloq ? "Desbloquear la pista" : "Bloquear la pista (no se puede mover, cortar ni borrar nada en ella)");
      if (c.fam === "a") nuevo("silenciadas", mudo, mudo ? "ðŸ”‡" : "ðŸ”Š", mudo ? "Activar el sonido de la pista" : "Silenciar la pista");
      else nuevo("ocultas", oculto, oculto ? "ðŸš«" : "ðŸ‘", oculto ? "Mostrar la pista" : "Ocultar la pista");
      if (E.pistas[c.fam === "a" ? "audio" : "video"] > 1 && !E.piezas.some(q => q.carril === c.id)) {
        const x = document.createElement("button"); x.textContent = "âœ•"; x.title = "Quitar esta pista vacÃ­a"; x.onclick = () => quitarPista(c.id); bt.appendChild(x);
      }
      d.appendChild(bt);
    }
    cont.appendChild(d);
  }
  cont.style.transform = `translateY(${-$("#scroll").scrollTop}px)`;
}
function quitarPista(id) {      // quita una pista vacÃ­a y baja un puesto las que estÃ¡n encima
  const fam = id[0], n = PZ.numero(id), k = fam === "A" ? "audio" : "video";
  if (E.piezas.some(q => q.carril === id) || E.pistas[k] <= 1) return;
  const baja = c => (c[0] === fam && PZ.numero(c) > n) ? fam + (PZ.numero(c) - 1) : c;
  for (const q of E.piezas) q.carril = baja(q.carril);
  for (const l of ["bloqueadas", "silenciadas", "ocultas"]) E.pistas[l] = E.pistas[l].filter(c => c !== id).map(baja);
  E.pistas[k]--; confirmar(); refrescarTodo();
}
function alternarPista(id, clave) {
  const lista = E.pistas[clave], i = lista.indexOf(id);
  if (i < 0) lista.push(id); else lista.splice(i, 1);
  lista.sort(); confirmar(); construirEtiquetas(); tocar();
}
$("#scroll").addEventListener("scroll", () => { $("#etiqInt").style.transform = `translateY(${-$("#scroll").scrollTop}px)`; tocar(); });
function dimensionarTimeline() {
  layout();
  const sc = $("#scroll"), w = Math.max(50, sc.clientWidth), h = Math.max(50, sc.clientHeight), d = window.devicePixelRatio || 1;
  TL.ancho = w; TL.altoVis = h; TL.sx = sc.scrollLeft; TL.sy = sc.scrollTop; TL.dpr = d;
  const cw = Math.round(w * d), chh = Math.round(h * d);
  if (TLC.width !== cw || TLC.height !== chh) { TLC.width = cw; TLC.height = chh; TLC.style.width = w + "px"; TLC.style.height = h + "px"; tlSucio = true; }
  const sp = $("#tlSpacer"), sw = Math.round(Math.max(w, TL.margen * 2 + durSalida() * TL.px + 160)) + "px", sh = TL.alto + "px";
  if (sp.style.width !== sw) sp.style.width = sw; if (sp.style.height !== sh) sp.style.height = sh;
}
function firmaTimeline() {
  return [T.toFixed(3), TL.px, TL.sx, TL.sy, TL.ancho, TL.altoVis, SEL.size, sel ? (sel.id || sel.i) : "", drag ? 1 : 0, Object.values(FUENTE).map(f => f.estado[0]).join(""), PICOS.length, herramienta].join("|");
}
const etiquetaPieza = p => {
  let s = p.tipo === "texto" ? (p.texto ? p.texto.contenido.split("\n")[0] : "Texto") : p.nombre || (p.fuente === "clip" ? (p.tipo === "audio" ? "Audio del clip" : "Clip") : "Medio");
  if (p.fuente === "clip" && p.tipo === "video" && p.encuadre) s += " â—§";
  if (Math.abs(velDe(p) - 1) > 1e-3) s += ` Ã—${+velDe(p).toFixed(2)}`;
  return s;
};
function dibujarPiezaTl(X, p, c, sx, W) {
  const a = TL.margen + p.t * TL.px, w = Math.max(3, p.dur * TL.px);
  if (a > sx + W || a + w < sx) return;
  const y0 = c.y0 + 2, h = c.alto - 4, elegida = SEL.has(p.id);
  const fs = p.fuente === "medio" && p.mid ? FUENTE[urlMedio(p)] : null, mala = fs && fs.estado === "error";
  X.fillStyle = mala ? "#8a2f2f" : colorDe(p, elegida); X.fillRect(a, y0, w, h);
  if (p.tipo === "audio") {
    const pk = p.fuente === "clip" ? PICOS : picosMedio(p.mid), por = p.fuente === "clip" ? PICOS_POR_S : 20;
    if (pk.length) {
      X.fillStyle = p.fuente === "clip" ? "#8be0b4" : "rgba(255,255,255,.55)";
      const mitad = y0 + h / 2, alto = h / 2 - 3, i0 = Math.max(0, Math.floor((sx - a) / 2) * 2), i1 = Math.min(w, sx + W - a);
      for (let px = i0; px < i1; px += 2) {
        const v = pk[Math.min(pk.length - 1, Math.floor((p.desde + px / TL.px * velDe(p)) * por))] || 0, hh = Math.max(1, v * alto);
        X.fillRect(a + px, mitad - hh, 1.5, hh * 2);
      }
    }
  }
  X.fillStyle = "rgba(0,0,0,.4)";
  if (p.fundido_in > 0) { X.beginPath(); X.moveTo(a, y0 + h); X.lineTo(a + p.fundido_in * TL.px, y0); X.lineTo(a, y0); X.closePath(); X.fill(); }
  if (p.fundido_out > 0) { const b = a + w; X.beginPath(); X.moveTo(b, y0 + h); X.lineTo(b - p.fundido_out * TL.px, y0); X.lineTo(b, y0); X.closePath(); X.fill(); }
  X.save(); X.beginPath(); X.rect(a, y0, w, h); X.clip();
  X.fillStyle = "#fff"; X.font = "11px Segoe UI, sans-serif"; X.textBaseline = "middle";
  if (w > 24) X.fillText((mala ? "âš  " : "") + etiquetaPieza(p), Math.max(a, sx) + 5, y0 + 10);
  if (p.trans_in && p.trans_in.tipo !== "ninguna") { X.fillStyle = "rgba(255,255,255,.85)"; const tw = Math.min(w, p.trans_in.dur * TL.px); X.beginPath(); X.moveTo(a, y0 + h); X.lineTo(a + tw, y0 + h); X.lineTo(a, y0 + h - 8); X.closePath(); X.fill(); }
  if (p.enlace) { X.fillStyle = colorEnlace(p.enlace); X.fillRect(a, y0, w, 3); }
  X.restore();
  for (const k of Object.keys(p.kf || {})) for (const q of p.kf[k]) {
    const kx = a + q.t * TL.px, ky = y0 + h - 6; X.fillStyle = "#ffe066"; X.strokeStyle = "#000"; X.lineWidth = 1;
    X.beginPath(); X.moveTo(kx, ky - 4); X.lineTo(kx + 4, ky); X.lineTo(kx, ky + 4); X.lineTo(kx - 4, ky); X.closePath(); X.fill(); X.stroke();
  }
  X.strokeStyle = elegida ? "#fff" : "rgba(255,255,255,.35)"; X.lineWidth = elegida ? 2 : 1; X.strokeRect(a + 0.5, y0 + 0.5, w - 1, h - 1);
  if (!elegida && p.enlace && SEL.size) {
    const hermana = E.piezas.some(q => SEL.has(q.id) && q.enlace === p.enlace);
    if (hermana) { X.setLineDash([4, 3]); X.strokeStyle = "#fff"; X.strokeRect(a + 1.5, y0 + 1.5, w - 3, h - 3); X.setLineDash([]); }
  }
}
function dibujarTimeline() {
  if (!E) return;
  dimensionarTimeline();
  const firma = firmaTimeline();
  if (!tlSucio && firma === ultimaFirmaTl) return;
  tlSucio = false; ultimaFirmaTl = firma;
  const X = TLX, W = TL.ancho, H = TL.altoVis, sx = TL.sx, sy = TL.sy, d = TL.dpr;
  X.setTransform(d, 0, 0, d, 0, 0); X.clearRect(0, 0, W, H);
  X.fillStyle = "#1a1d22"; X.fillRect(0, 0, W, H);
  // carriles
  X.save(); X.translate(-sx, -sy);
  const P = E.pistas, M = mapa(), porCarril = {};
  for (const p of E.piezas) (porCarril[p.carril] = porCarril[p.carril] || []).push(p);
  TL.carriles.forEach((c, i) => { X.fillStyle = i % 2 ? "#1c1f25" : "#181b20"; X.fillRect(sx, c.y0, W, c.alto); X.fillStyle = "#2a2f3a"; X.fillRect(sx, c.y1 - 1, W, 1); });
  if (drag && drag.tipo === "mover" && drag.destino) { const c = carrilPorId(drag.destino); if (c) { X.fillStyle = "rgba(79,157,255,.16)"; X.fillRect(sx, c.y0, W, c.alto); } }
  for (const c of TL.carriles) {
    if (c.fam === "s") continue;
    for (const p of (porCarril[c.id] || [])) if (!SEL.has(p.id)) dibujarPiezaTl(X, p, c, sx, W);
    for (const p of (porCarril[c.id] || [])) if (SEL.has(p.id)) dibujarPiezaTl(X, p, c, sx, W);
    if (P.ocultas.includes(c.id)) { X.fillStyle = "rgba(0,0,0,.45)"; X.fillRect(sx, c.y0, W, c.alto); }
    if (P.silenciadas.includes(c.id)) { X.fillStyle = "#ff6464"; X.fillRect(sx, c.y0, W, 2); }
    if (P.bloqueadas.includes(c.id)) {
      X.fillStyle = "rgba(0,0,0,.38)"; X.fillRect(sx, c.y0, W, c.alto);
      X.strokeStyle = "rgba(255,255,255,.12)"; X.lineWidth = 1; X.beginPath();
      for (let x = Math.floor(sx / 12) * 12; x < sx + W + c.alto; x += 12) { X.moveTo(x, c.y1); X.lineTo(x + c.alto, c.y0); }
      X.stroke();
    }
  }
  // subtÃ­tulos
  const cs = TL.carriles.find(c => c.fam === "s");
  if (cs) {
    X.fillStyle = "#20232a"; X.fillRect(sx, cs.y0, W, cs.alto);
    const sub = E.subtitulos;
    if (sub.lineas.length) sub.lineas.forEach((l, i) => {
      const a = PZ.salidaDeOrigenSuave(M, l.inicio), b = PZ.salidaDeOrigenSuave(M, l.fin), x = TL.margen + a * TL.px, w = Math.max(3, (b - a) * TL.px);
      if (b - a < 0.001 || x > sx + W || x + w < sx) return;
      const s = sel && sel.tipo === "sub" && sel.i === i;
      X.fillStyle = s ? "#b57fe0" : "#7d4fa6"; X.fillRect(x, cs.y0 + 3, w, cs.alto - 6);
      if (l.hablante && estilo().hablantes) { X.fillStyle = estilo().hablantes[l.hablante - 1]; X.fillRect(x, cs.y0 + 3, Math.min(5, w), cs.alto - 6); }
      X.save(); X.beginPath(); X.rect(x, cs.y0, w, cs.alto); X.clip(); X.fillStyle = "#fff"; X.font = "11px Segoe UI, sans-serif"; X.textBaseline = "middle";
      X.fillText(l.texto, x + 8, (cs.y0 + cs.y1) / 2); X.restore();
      if (s) { X.strokeStyle = "#fff"; X.lineWidth = 2; X.strokeRect(x + 1, cs.y0 + 4, w - 2, cs.alto - 8); }
    }); else { X.fillStyle = "#6b7280"; X.font = "11px Segoe UI, sans-serif"; X.textBaseline = "middle"; X.fillText("Sin subtÃ­tulos â€” genera o aÃ±ade lÃ­neas en la pestaÃ±a SubtÃ­tulos", sx + 8, (cs.y0 + cs.y1) / 2); }
  }
  if (drag && drag.snapT !== undefined) { const x = TL.margen + drag.snapT * TL.px; X.strokeStyle = "#ffe066"; X.lineWidth = 1; X.beginPath(); X.moveTo(x + 0.5, TL.altoRegla); X.lineTo(x + 0.5, TL.alto); X.stroke(); }
  X.restore();
  // regla y cabezal (fijos arriba)
  X.save(); X.translate(-sx, 0);
  X.fillStyle = "#1a1d22"; X.fillRect(sx, 0, W, TL.altoRegla);
  const total = Math.max(durSalida(), (sx + W) / TL.px), paso = TL.px >= 150 ? 0.5 : TL.px >= 60 ? 1 : TL.px >= 28 ? 2 : TL.px >= 12 ? 5 : 10;
  X.fillStyle = "#9aa2b1"; X.font = "11px Segoe UI, sans-serif"; X.textBaseline = "top"; X.strokeStyle = "#444b59"; X.lineWidth = 1;
  const t0 = Math.max(0, Math.floor(((sx - TL.margen) / TL.px) / paso) * paso), t1 = (sx + W - TL.margen) / TL.px;
  for (let t = t0; t <= t1 + paso; t += paso) {
    const x = Math.round(TL.margen + t * TL.px) + 0.5; X.beginPath(); X.moveTo(x, 14); X.lineTo(x, TL.altoRegla); X.stroke();
    if (Math.abs(t % (paso < 1 ? 1 : paso)) < 1e-6) X.fillText(fmt(t).replace(/\.00$/, ""), x + 3, 2);
  }
  const px = TL.margen + T * TL.px; X.strokeStyle = "#ff5a5a"; X.lineWidth = 2; X.beginPath(); X.moveTo(px, 0); X.lineTo(px, H); X.stroke();
  X.fillStyle = "#ff5a5a"; X.beginPath(); X.moveTo(px - 6, 0); X.lineTo(px + 6, 0); X.lineTo(px, 9); X.closePath(); X.fill();
  X.restore();
  const nclip = E.piezas.filter(p => p.fuente === "clip" && p.tipo === "video").length, ntexto = E.piezas.filter(p => p.tipo === "texto").length;
  $("#infoTl").textContent = `${E.piezas.length} pieza(s) (${nclip} trozo(s) del clip${ntexto ? ", " + ntexto + " texto(s)" : ""}) Â· ${fmt(durSalida())} de salida Â· original ${fmt(E.origen.duracion)}`;
}

// ------------------------------------------------------------------ pulsar y arrastrar en la lÃ­nea de tiempo
function golpe(x, y, yv) {
  if (yv < TL.altoRegla) return {z: "regla"};
  layout();
  const c = TL.carriles.find(q => y >= q.y0 && y < q.y1);
  if (!c) return {z: "vacio"};
  if (c.fam === "s") {
    const lineas = E.subtitulos.lineas, M = mapa();
    for (let i = lineas.length - 1; i >= 0; i--) {
      const a = TL.margen + PZ.salidaDeOrigenSuave(M, lineas[i].inicio) * TL.px, b = TL.margen + PZ.salidaDeOrigenSuave(M, lineas[i].fin) * TL.px;
      if (x >= a - 5 && x <= b + 5) return {z: "sub", i, borde: Math.abs(x - a) <= 5 ? "ini" : Math.abs(x - b) <= 5 ? "fin" : null};
    }
    return {z: "vacio"};
  }
  const lista = E.piezas.filter(p => p.carril === c.id).sort((a, b) => a.t - b.t);
  const dev = (p, a, b) => { const w = b - a, tol = Math.min(6, w / 3); return {z: "pieza", p, carril: c, borde: w > 14 ? (Math.abs(x - a) <= tol ? "ini" : Math.abs(x - b) <= tol ? "fin" : null) : null}; };
  for (let i=lista.length-1;i>=0;i--){const p=lista[i],a=TL.margen+p.t*TL.px,b=a+p.dur*TL.px,h=c.alto-4,ky=c.y0+2+h-6;for(const [k,pts] of Object.entries(p.kf||{}))for(const q of pts){if(Math.abs(x-(a+q.t*TL.px))<=7&&Math.abs(y-ky)<=8)return {z:"kf",p,k,q,carril:c};}}
  for (let i = lista.length - 1; i >= 0; i--) {           // primero la pieza que contiene el punto (en un corte, manda el lado donde estÃ¡ el ratÃ³n)
    const p = lista[i], a = TL.margen + p.t * TL.px, b = a + p.dur * TL.px;
    if (x >= a && x < b) return dev(p, a, b);
  }
  for (let i = lista.length - 1; i >= 0; i--) {
    const p = lista[i], a = TL.margen + p.t * TL.px, b = a + p.dur * TL.px;
    if (x >= a - 4 && x <= b + 4) return dev(p, a, b);
  }
  return {z: "hueco", carril: c};
}
function coordsTl(ev) {
  const r = TLC.getBoundingClientRect(), sc = $("#scroll");
  return {x: ev.clientX - r.left + sc.scrollLeft, y: ev.clientY - r.top + sc.scrollTop, yv: ev.clientY - r.top};
}
let drag = null;
TLC.addEventListener("pointermove", ev => {
  if (drag) return;
  const c = coordsTl(ev), g = golpe(c.x, c.y, c.yv);
  if(g.z==="kf"){const n=PARAMS[g.k]?.et||g.k;TLC.title=`${n}: ${g.q.v} Â· ${g.q.t.toFixed(2)} s. Arrastra para mover; clic derecho para borrar.`;TLC.style.cursor="grab";return;}
  TLC.title="";
  TLC.style.cursor = herramienta === "cuchilla" && g.z === "pieza" ? "crosshair" : g.borde ? "ew-resize" : g.z === "pieza" || g.z === "sub" ? "pointer" : "default";
});
function avisoEdicion(m) { const e = $("#errMedio"); e.hidden = !m; e.textContent = m || ""; if (m) { activarPestana("pistas"); clearTimeout(avisoEdicion.t); avisoEdicion.t = setTimeout(() => { e.hidden = true; }, 6000); } }
TLC.addEventListener("pointerdown", ev => {
  TLC.setPointerCapture(ev.pointerId);
  const c = coordsTl(ev), x = c.x, g = golpe(x, c.y, c.yv), tiempo = limitar((x - TL.margen) / TL.px, 0, durSalida());
  if(g.z!=="kf")kfSel=null;
  if(g.z==="kf"){seleccionar([g.p.id],g.p.id);kfSel={p:g.p.id,k:g.k,q:g.q};drag={tipo:"kf",id:g.p.id,k:g.k,q:g.q,x0:x,t0:g.q.t,mov:false};if(reproduciendo)pausar();return;}
  if (g.z === "regla" || g.z === "vacio" || g.z === "hueco") {
    if (g.z !== "regla" && !ev.shiftKey) seleccionar([]);
    drag = {tipo: "cabezal"}; if (reproduciendo) pausar(); ir(tiempo); tocar(); return;
  }
  if (g.z === "pieza") { empezarPieza(ev, g, x, c.y, tiempo); return; }
  if (g.z === "sub") {
    seleccionarSub(g.i); const l = E.subtitulos.lineas[g.i];
    drag = {tipo: g.borde ? "sub-borde" : "sub-mover", i: g.i, borde: g.borde, x0: x, ini: l.inicio, fin: l.fin, palabras: JSON.parse(JSON.stringify(l.palabras)), mov: false};
    if (reproduciendo) pausar();
    tocar(); return;
  }
});
function empezarPieza(ev, g, x, y, tiempo) {
  const p = g.p;
  if (herramienta === "cuchilla") { cortarClic(p, tiempo, ev); return; }
  const grupo = OPC.enlazada && !ev.altKey ? [...PZ.conEnlazadas(E.piezas, new Set([p.id]))] : [p.id];
  if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
    if (SEL.has(p.id)) { for (const i of grupo) SEL.delete(i); seleccionar([...SEL]); }
    else seleccionar([...SEL, ...grupo], p.id);
    return;
  }
  if (ev.altKey && !(SEL.size === 1 && SEL.has(p.id))) seleccionar([p.id], p.id);
  else if (!SEL.has(p.id)) seleccionar(grupo, p.id);
  else if (!sel || sel.tipo !== "pieza" || sel.id !== p.id) { sel = {tipo: "pieza", id: p.id}; alCambiarSeleccion(); }
  if (bloqueadas().has(p.carril)) { avisoEdicion("Esa pista estÃ¡ bloqueada: desbloquÃ©ala con el candado para editarla."); drag = {tipo: "cabezal"}; return; }
  if (reproduciendo) pausar();
  const trim = herramienta === "trim";
  if (g.borde) drag = {tipo: "borde", id: p.id, borde: g.borde, x0: x, base: JSON.stringify(E.piezas), ripple: OPC.ripple || trim, rodar: trim, mov: false, T0: T};
  else {
    const snap0 = {}; for (const q of piezasSel()) snap0[q.id] = {t: q.t, carril: q.carril};
    drag = {tipo: "mover", id: p.id, x0: x, y0: y, snap0, mov: false, destino: null, T0: T, pistas0: {video: E.pistas.video, audio: E.pistas.audio}};
  }
  tocar();
}
function bordeDe(p, borde) { return borde === "ini" ? p.t : PZ.fin(p); }
function moverArrastre(ev) {
  const c = coordsTl(ev), x = c.x, dt0 = (x - drag.x0) / TL.px;
  if (Math.abs(x - drag.x0) > 2 || (drag.y0 !== undefined && Math.abs(c.y - drag.y0) > 4)) drag.mov = true;
  if (!drag.mov) return;
  tocar();
  if (drag.tipo === "mover") {
    const ids = new Set(Object.keys(drag.snap0)), mov = E.piezas.filter(p => ids.has(p.id));
    let ini = Infinity, fin = -Infinity;
    for (const p of mov) { ini = Math.min(ini, drag.snap0[p.id].t); fin = Math.max(fin, drag.snap0[p.id].t + p.dur); }
    let dt = Math.max(dt0, -ini);
    drag.snapT = undefined;
    if (OPC.iman) {
      const pts = PZ.puntosImantados(E.piezas, ids, drag.T0), um = 8 / TL.px;
      const a = PZ.imantar(pts, ini + dt, um), b = PZ.imantar(pts, fin + dt, um);
      const da = a === null ? Infinity : Math.abs(a - (ini + dt)), db = b === null ? Infinity : Math.abs(b - (fin + dt));
      if (da <= db && a !== null) { dt = a - ini; drag.snapT = a; } else if (b !== null) { dt = b - fin; drag.snapT = b; }
    }
    for (const p of mov) p.t = PZ.redondear(drag.snap0[p.id].t + dt);
    const prim = piezaPorId(drag.id), fam = PZ.familia(prim.carril) === "A" ? "a" : "v", lane = carrilCercano(c.y, fam), bl = bloqueadas();
    let destino = lane && !bl.has(lane.id) ? lane.id : drag.snap0[prim.id].carril;
    {                  // arrastrar por encima de la Ãºltima pista de vÃ­deo (o por debajo de la de audio) crea una pista nueva
      const tv = carrilPorId("V" + drag.pistas0.video), ta = carrilPorId("A" + drag.pistas0.audio);
      if (fam === "v" && tv && c.y < tv.y0 - 6 && drag.pistas0.video < MAX_CARRILES) destino = "V" + (drag.pistas0.video + 1);
      if (fam === "a" && ta && c.y > ta.y1 + 6 && drag.pistas0.audio < MAX_CARRILES) destino = "A" + (drag.pistas0.audio + 1);
    }
    prim.carril = destino; drag.destino = destino;
    const usV = Math.max(1, ...E.piezas.filter(q => PZ.familia(q.carril) === "V").map(q => PZ.numero(q.carril))), usA = Math.max(1, ...E.piezas.filter(q => PZ.familia(q.carril) === "A").map(q => PZ.numero(q.carril)));
    const nv = Math.max(drag.pistas0.video, usV), na = Math.max(drag.pistas0.audio, usA);
    if (nv !== E.pistas.video || na !== E.pistas.audio) { E.pistas.video = nv; E.pistas.audio = na; construirEtiquetas(); }
    return;
  }
  if (drag.tipo === "kf") {
    const p=piezaPorId(drag.id),pts=p?.kf?.[drag.k];if(!p||!pts)return;
    let nt=limitar(drag.t0+dt0,0,p.dur);const otro=pts.find(q=>q!==drag.q&&Math.abs(q.t-nt)<.02);if(otro)nt=drag.t0;
    drag.q.t=+nt.toFixed(3);pts.sort((a,b)=>a.t-b.t);T=p.t+drag.q.t;actualizarReloj();return;
  }
  if (drag.tipo === "borde") {
    E.piezas = JSON.parse(drag.base);
    const p = piezaPorId(drag.id), borde = drag.borde, edge0 = bordeDe(p, borde);
    const ids = new Set([p.id]), coinciden = piezasSel().filter(q => q.id !== p.id && Math.abs(bordeDe(q, borde) - edge0) < 0.02);
    for (const q of coinciden) ids.add(q.id);
    let obj = edge0 + dt0; drag.snapT = undefined;
    if (OPC.iman) { const m = PZ.imantar(PZ.puntosImantados(E.piezas, ids, drag.T0), obj, 8 / TL.px); if (m !== null) { obj = m; drag.snapT = m; } }
    let dt = obj - edge0;
    const enlazadas = coinciden.filter(q => !bloqueadas().has(q.carril));
    if (drag.rodar) {
      const parejas = [];
      for (const q of [p, ...enlazadas]) {
        const izq = borde === "fin" ? q : E.piezas.find(o => o.id !== q.id && o.carril === q.carril && Math.abs(PZ.fin(o) - q.t) < 0.02);
        const der = borde === "fin" ? PZ.contiguaDerecha(E.piezas, q) : q;
        if (izq && der) parejas.push([izq, der]);
      }
      if (parejas.length) {
        let dc = dt;
        for (const [i, d] of parejas) { const a = PZ.clonar(i), b = PZ.clonar(d); dc = PZ.rodar([], a, b, dc); }
        for (const [i, d] of parejas) PZ.rodar(E.piezas, i, d, dc);
        dt = dc;
      } else PZ.ajustarBorde(E.piezas, p, borde, dt, true, enlazadas);
    } else dt = PZ.ajustarBorde(E.piezas, p, borde, dt, drag.ripple, enlazadas);
    T = limitar(bordeDe(piezaPorId(drag.id), borde), 0, durSalida()); sincronizarMedia(); actualizarReloj(); actualizarTransformBox();
    return;
  }
  if (drag.tipo === "sub-mover" || drag.tipo === "sub-borde") {
    const dt = dt0, l = E.subtitulos.lineas[drag.i];
    let ni = drag.ini, nf = drag.fin;
    if (drag.tipo === "sub-mover") { const d = limitar(dt, -drag.ini, E.origen.duracion - drag.fin); ni += d; nf += d; }
    else if (drag.borde === "ini") ni = limitar(drag.ini + dt, 0, drag.fin - 0.1); else nf = limitar(drag.fin + dt, drag.ini + 0.1, E.origen.duracion);
    const k = (nf - ni) / (drag.fin - drag.ini || 1);
    l.inicio = +ni.toFixed(3); l.fin = +nf.toFixed(3);
    l.palabras = drag.palabras.map(w => ({...w, inicio: +(ni + (w.inicio - drag.ini) * k).toFixed(3), fin: +(ni + (w.fin - drag.ini) * k).toFixed(3)}));
    refrescarFilaSub(drag.i);
  }
}
TLC.addEventListener("pointermove", ev => {
  if (!drag) return;
  if (drag.tipo === "cabezal") { const x = coordsTl(ev).x; ir((x - TL.margen) / TL.px); tocar(); return; }
  moverArrastre(ev);
});
function terminarArrastre() {
  if (!drag) return;
  const d = drag; drag = null; tocar();
  if (d.tipo === "cabezal") return;
  if (d.tipo === "kf") {if(!d.mov){const p=piezaPorId(d.id);if(p)ir(p.t+d.q.t);}else{confirmar();valoresParametros();refrescarTodo();}return;}
  if (d.tipo === "mover") {
    if (!d.mov) { const p = piezaPorId(d.id); if (p) ir(limitar((d.x0 - TL.margen) / TL.px, 0, durSalida())); return; }
    const ids = new Set(Object.keys(d.snap0));
    E.piezas = PZ.sobrescribir(E.piezas, ids);
    asegurarPistas(); confirmar(); refrescarTodo(); return;
  }
  if (d.tipo === "borde") {
    if (!d.mov) { E.piezas = JSON.parse(d.base); return; }
    confirmar(); refrescarTodo(); return;
  }
  if (d.tipo === "sub-mover" || d.tipo === "sub-borde") {
    if (d.mov) confirmar();
    else if (d.tipo === "sub-mover") ir(oriASalSuave(E.subtitulos.lineas[d.i].inicio));
    refrescarTodo();
  }
}
TLC.addEventListener("pointerup", terminarArrastre);
TLC.addEventListener("pointercancel", terminarArrastre);
let kfSel=null;
function borrarKfSeleccionado(){if(!kfSel)return false;const p=piezaPorId(kfSel.p),pts=p?.kf?.[kfSel.k];if(!pts)return false;const i=pts.indexOf(kfSel.q);if(i<0)return false;pts.splice(i,1);if(!pts.length)delete p.kf[kfSel.k];kfSel=null;confirmar();valoresParametros();refrescarTodo();return true;}
TLC.addEventListener("contextmenu",ev=>{const c=coordsTl(ev),g=golpe(c.x,c.y,c.yv);if(g.z!=="kf")return;ev.preventDefault();kfSel={p:g.p.id,k:g.k,q:g.q};borrarKfSeleccionado();});
TLC.addEventListener("dblclick", ev => {
  const c = coordsTl(ev), g = golpe(c.x, c.y, c.yv);
  if (g.z === "hueco") cerrarHuecoEn(g.carril.id, (c.x - TL.margen) / TL.px);
});
function asegurarPistas() {
  for (const p of E.piezas) { const n = PZ.numero(p.carril), k = PZ.familia(p.carril) === "A" ? "audio" : "video"; if (n > E.pistas[k]) E.pistas[k] = n; }
}

// ------------------------------------------------------------------ operaciones de ediciÃ³n
const hayEspacio = n => { if (E.piezas.length + n > MAX_PIEZAS) { avisoEdicion(`Hay demasiadas piezas (mÃ¡ximo ${MAX_PIEZAS}). Borra o une algunas antes.`); return false; } return true; };
function dividirAqui(t, objetivo) {
  if (!hayEspacio(4)) return false;
  const nuevas = PZ.dividirEn(E.piezas, t, objetivo, bloqueadas());
  if (!nuevas.length) return false;
  seleccionar(nuevas.map(q => q.id)); confirmar(); refrescarTodo(); return true;
}
function cortarClic(p, t, ev) {
  if (bloqueadas().has(p.carril)) { avisoEdicion("Esa pista estÃ¡ bloqueada."); return; }
  t = aFotograma(t);
  const obj = ev.shiftKey ? null : (OPC.enlazada && !ev.altKey ? [...PZ.conEnlazadas(E.piezas, new Set([p.id]))].map(piezaPorId) : [p]);
  if (!dividirAqui(t, obj)) avisoEdicion("AhÃ­ no se puede cortar: queda un trozo demasiado corto.");
}
function dividir() {
  let obj = null;
  if (SEL.size) {
    const o = piezasSel().filter(p => T > p.t + 1e-6 && T < PZ.fin(p) - 1e-6);
    if (o.length) obj = o;
  }
  return dividirAqui(aFotograma(T) > 0 ? aFotograma(T) : T, obj);
}
function borrarSel(inverso) {
  if (sel && sel.tipo === "sub") { E.subtitulos.lineas.splice(sel.i, 1); sel = null; confirmar(); refrescarTodo(); return; }
  if (!SEL.size) return;
  const bl = bloqueadas();
  if (!piezasSel().some(p => !bl.has(p.carril))) { avisoEdicion("Esas piezas estÃ¡n en una pista bloqueada."); return; }
  const ripple = inverso ? !OPC.ripple : OPC.ripple;
  E.piezas = PZ.borrar(E.piezas, new Set(SEL), ripple, bl);
  seleccionar([]); T = limitar(T, 0, durSalida()); confirmar(); refrescarTodo(); ir(T);
}
function alternarEnlace() {
  const ps = piezasSel();
  if (!ps.length) { avisoEdicion("Selecciona piezas (MayÃºs+clic para varias) para enlazarlas o separarlas."); return; }
  const ids = new Set(ps.map(p => p.id));
  if (ps.every(p => p.enlace)) PZ.desenlazar(E.piezas, ids);
  else if (ps.length >= 2) { PZ.enlazar(E.piezas, ids); PZ.limpiarEnlaces(E.piezas); }
  else { avisoEdicion("Para enlazar hacen falta dos o mÃ¡s piezas seleccionadas."); return; }
  confirmar(); refrescarTodo();
}
function cerrarHuecoEn(carril, t) {
  const bl = bloqueadas(); if (bl.has(carril)) return false;
  const hs = PZ.huecos(E.piezas, carril).find(h => t >= h.a - 0.01 && t <= h.b + 0.01);
  if (!hs) return false;
  const lanes = new Set([carril]);
  for (const c of TL.carriles) {
    if (c.fam === "s" || bl.has(c.id) || lanes.has(c.id)) continue;
    if (PZ.huecos(E.piezas, c.id).some(h => Math.abs(h.a - hs.a) < 0.02 && Math.abs(h.b - hs.b) < 0.02)) lanes.add(c.id);
  }
  for (const c of lanes) PZ.cerrarHueco(E.piezas, c, hs.a, hs.b);
  confirmar(); refrescarTodo(); return true;
}
function cerrarHuecoAntes() {
  const p = piezaSel(); if (!p) { avisoEdicion("Selecciona una pieza: se cierra el hueco que tiene justo antes."); return; }
  const h = PZ.huecos(E.piezas, p.carril).find(q => Math.abs(q.b - p.t) < 0.02);
  if (!h || !cerrarHuecoEn(p.carril, (h.a + h.b) / 2)) avisoEdicion("No hay un hueco justo antes de esa pieza.");
}
let PORTAPAPELES = null;
function copiar() { const ps = piezasSel(); if (!ps.length) return; PORTAPAPELES = {piezas: PZ.clonar(ps), t0: Math.min(...ps.map(p => p.t))}; }
function pegar() {
  if (!PORTAPAPELES || !hayEspacio(PORTAPAPELES.piezas.length)) return;
  const enl = {}, nuevas = [], bl = bloqueadas();
  for (const o of PORTAPAPELES.piezas) {
    const q = PZ.clonar(o); q.id = PZ.nuevoId(E.piezas.concat(nuevas)); q.t = PZ.redondear(T + o.t - PORTAPAPELES.t0);
    if (q.enlace) q.enlace = enl[q.enlace] || (enl[q.enlace] = PZ.nuevoEnlace());
    if (!bl.has(q.carril)) nuevas.push(q);
  }
  if (!nuevas.length) return;
  E.piezas = PZ.sobrescribir(E.piezas.concat(nuevas), new Set(nuevas.map(q => q.id)));
  asegurarPistas(); seleccionar(nuevas.map(q => q.id)); confirmar(); refrescarTodo();
}
function anadirPista(fam) {
  const k = fam === "A" ? "audio" : "video";
  if (E.pistas[k] >= MAX_CARRILES) { avisoEdicion("Ya tienes el mÃ¡ximo de pistas."); return; }
  E.pistas[k]++; confirmar(); refrescarTodo();
}

// ------------------------------------------------------------------ aÃ±adir medios (con su audio) y texto
function finDeCarriles(ids) { return Math.max(0, ...E.piezas.filter(p => ids.includes(p.carril)).map(PZ.fin)); }
// Pista de vÃ­deo justo por encima de todo lo que hay en ese tramo de tiempo (asÃ­ lo que se superpone siempre se ve), o null si ya no caben mÃ¡s.
function carrilArriba(t, dur, excluir) {
  let mx = 0;
  for (const q of E.piezas) if (q.tipo !== "audio" && !(excluir && excluir.has(q.id)) && q.t < t + dur && PZ.fin(q) > t) mx = Math.max(mx, PZ.numero(q.carril));
  const n = Math.max(2, mx + 1);
  if (n > MAX_CARRILES) return null;
  if (n > E.pistas.video) E.pistas.video = n;
  return "V" + n;
}
function colocarMedios(medios) {
  const modo = OPC.colocar, bl = bloqueadas(); let t = T, ultimas = [];
  for (const f of medios) {
    if (!hayEspacio(2)) break;
    const dur = Math.max(0.5, Math.min(f.tipo === "imagen" ? 3 : f.dur_medio, PZ.MAX_DURACION - t));
    const t0 = modo === "al_final" ? finDeCarriles(["V1", "A1"]) : t;
    const nuevas = PZ.piezasDeMedio(f, t0, dur, E.piezas);
    let fallo = false;
    for (const q of nuevas) {
      const fam = q.tipo === "audio" ? "A" : "V", k = fam === "A" ? "audio" : "video";
      if (modo === "superponer") {
        let c = fam === "V" ? carrilArriba(t0, dur) : PZ.carrilLibre(E.piezas, fam, t0, dur, E.pistas[k], 2);
        if (!c) { if (E.pistas[k] < MAX_CARRILES) { E.pistas[k]++; c = fam + E.pistas[k]; } else { fallo = true; break; } }
        q.carril = c;
      } else { q.carril = fam + "1"; if (bl.has(q.carril)) { fallo = true; break; } }
    }
    if (fallo) { avisoEdicion(`No hay hueco o pista libre para Â«${f.nombre}Â».`); continue; }
    if (modo === "insertar") E.piezas = PZ.insertarEn(E.piezas, t0, nuevas, bl);
    else if (modo === "superponer") E.piezas = E.piezas.concat(nuevas);
    else E.piezas = PZ.sobrescribir(E.piezas.concat(nuevas), new Set(nuevas.map(q => q.id)));
    ultimas = nuevas;
    if (modo !== "superponer") t = t0 + dur;
  }
  if (ultimas.length) { asegurarPistas(); seleccionar(ultimas.map(q => q.id), ultimas[0].id); confirmar(); refrescarTodo(); }
}
async function agregarMedios() {
  const botones = [$("#bMedio"), $("#bMedio2")], textos = botones.map(b => b.textContent);
  botones.forEach(b => { b.disabled = true; b.textContent = "Elige los archivosâ€¦"; });
  avisoEdicion("");
  try {
    let d;
    try { d = await post("medios/elegir"); }
    catch (e) {
      if (e.datos && e.datos.sin_selector) {
        const ruta = prompt("No se pudo abrir el selector de archivos. Pega la ruta completa del archivo (video, imagen o audio):");
        if (!ruta) throw new Error("");
        d = await post("medios/agregar", {rutas: [ruta]});
      } else throw e;
    }
    if (d.cancelado || !d.medios.length) return;
    colocarMedios(d.medios);
    if (d.errores && d.errores.length) avisoEdicion(d.errores.join("\n"));
    activarPestana("pistas");
  } catch (e) { if (e.message) avisoEdicion(/^Error 404/.test(e.message) ? "El panel abierto es de una versiÃ³n anterior: ciÃ©rralo y vuelve a pulsar Editar en la app." : e.message); }
  finally { botones.forEach((b, i) => { b.disabled = false; b.textContent = textos[i]; }); }
}
function agregarTexto() {
  if (!hayEspacio(1)) return;
  const dur = 3, t = PZ.redondear(T);
  let c = PZ.carrilLibre(E.piezas, "V", t, dur, E.pistas.video, 2);
  if (!c) { if (E.pistas.video < MAX_CARRILES) { E.pistas.video++; c = "V" + E.pistas.video; } else { avisoEdicion("No queda una pista de vÃ­deo libre para el texto."); return; } }
  const tx = PZ.textoBase(); tx.fuente = (E.subtitulos.estilo && E.subtitulos.estilo.fuente) || "Arial"; tx.y = 0.3;
  const p = PZ.piezaBase({id: PZ.nuevoId(E.piezas), tipo: "texto", fuente: "texto", carril: c, t, dur, nombre: "Texto", texto: tx});
  E.piezas.push(p); seleccionar([p.id]); confirmar(); refrescarTodo(); activarPestana("pistas");
  const a = $("#xTexto"); if (a) { a.focus(); a.select(); }
}

// ------------------------------------------------------------------ etiqueta de plataforma (caja con nombre + logo propio)
function agregarEtiqueta() {
  if (!hayEspacio(2)) return;
  const dur = 4, t = PZ.redondear(T);
  let c = PZ.carrilLibre(E.piezas, "V", t, dur, E.pistas.video, 2);
  if (!c) { if (E.pistas.video < MAX_CARRILES) { E.pistas.video++; c = "V" + E.pistas.video; } else { avisoEdicion("No queda una pista de vÃ­deo libre."); return; } }
  const tx = PZ.textoBase();
  Object.assign(tx, {contenido: "tu_nombre", fuente: (E.subtitulos.estilo && E.subtitulos.estilo.fuente) || "Arial", tamano: 46, negrita: true, color: "#5b3fa0", fondo: "caja", color_fondo: "#ece7fa",
    alineacion: "izquierda", x: 0.33, y: 0.45, anim_in: "pop", anim_out: "fundido", sombra: 0});
  const p = PZ.piezaBase({id: PZ.nuevoId(E.piezas), tipo: "texto", fuente: "texto", carril: c, t, dur, nombre: "Etiqueta", texto: tx});
  E.piezas.push(p); seleccionar([p.id]); confirmar(); refrescarTodo(); activarPestana("pistas");
  const a = $("#xTexto"); if (a) { a.focus(); a.select(); }
}
// Pone (o cambia) el logo de la etiqueta seleccionada: reserva un hueco a la izquierda del texto y coloca la imagen elegida ahÃ­, enlazada a la etiqueta.
async function logoEtiqueta() {
  const p = piezaSel();
  if (!p || p.tipo !== "texto") { avisoEdicion("Selecciona primero la etiqueta (o el texto) a la que va el logo."); return; }
  if (!hayEspacio(1)) return;
  let d;
  try { d = await post("medios/elegir"); } catch (e) { avisoEdicion(e.message || String(e)); return; }
  if (d.cancelado || !d.medios || !d.medios.length) return;
  const f = d.medios.find(m => m.tipo === "imagen");
  if (!f) { avisoEdicion("El logo debe ser una imagen (PNG, JPGâ€¦)."); return; }
  const tx = p.texto, ow = E.salida.ancho, oh = E.salida.alto, alto = tx.tamano * 1.3, ancho = alto * (f.ancho || 1) / (f.alto || 1);
  const pad = tx.fondo === "caja" ? Math.max(10, tx.tamano / 6) : 0, hueco = tx.tamano * 0.15;   // el texto va siempre por encima de las imÃ¡genes: el logo se coloca pegado a la izquierda de la caja
  tx.icono_espacios = 0;
  const q = PZ.piezasDeMedio(f, p.t, p.dur, E.piezas)[0];
  q.modo = "recuadro"; q.nombre = "Logo";
  q.recuadro = {x: Math.max(0, (tx.x * ow - pad - hueco - ancho) / ow), y: Math.max(0, tx.y - alto / oh / 2), w: Math.min(1, ancho / ow)};
  const c = carrilArriba(p.t, p.dur);          // el logo va por encima de cualquier vÃ­deo para que no quede tapado
  if (!c) { avisoEdicion("No queda una pista de vÃ­deo libre para el logo."); return; }
  q.carril = c;
  E.piezas.push(q); PZ.enlazar(E.piezas, new Set([p.id, q.id])); PZ.limpiarEnlaces(E.piezas);
  seleccionar([p.id]); confirmar(); refrescarTodo();
  avisoEdicion(tx.alineacion === "izquierda" ? "" : "Consejo: pon la alineaciÃ³n del texto en Â«Izq.Â» para que el logo quede pegado a la caja.");
}

// ------------------------------------------------------------------ inspector de la pieza seleccionada
const NOMBRE_TIPO = {video: "VÃ­deo", audio: "Audio", imagen: "Imagen", texto: "Texto"};
const PARAMS = {
  zoom: {et: "Zoom", min: 100, max: 400, esc: 100, un: "%"}, pos_x: {et: "PosiciÃ³n X", min: -100, max: 100, esc: 100, un: "%"},
  pos_y: {et: "PosiciÃ³n Y", min: -100, max: 100, esc: 100, un: "%"}, opacidad: {et: "Opacidad", min: 0, max: 100, esc: 100, un: "%"},
  volumen: {et: "Volumen", min: 0, max: 200, esc: 100, un: "%"}, rotacion: {et: "RotaciÃ³n", min: -180, max: 180, esc: 1, un: "Â°"},
  rec_x:{et:"Recorte X",min:0,max:100,esc:100,un:"%"},rec_y:{et:"Recorte Y",min:0,max:100,esc:100,un:"%"},rec_w:{et:"Ancho",min:1,max:100,esc:100,un:"%"},rec_h:{et:"Alto",min:1,max:100,esc:100,un:"%"},
};
function paramsDe(p) {
  if (p.tipo === "audio") return ["volumen"];
  if (p.tipo === "texto") return ["opacidad"];
  const base=p.fuente === "medio" && p.modo === "recuadro"? ["opacidad","rotacion"]:["zoom","pos_x","pos_y","opacidad","rotacion"];
  if(p.tipo==="video"&&p.encuadre?.modo==="recorte")base.push("rec_x","rec_y","rec_w","rec_h");
  return base;
}
let filasPara = "";
function construirParametros(p) {
  const claves = paramsDe(p), firma = claves.join(",");
  if (firma === filasPara) return;
  filasPara = firma;
  const c = $("#paramFilas"); c.innerHTML = "";
  for (const k of claves) {
    const q = PARAMS[k], d = document.createElement("div"); d.className = "fila prm"; d.dataset.k = k;
    d.innerHTML = `<span>${q.et}</span><input type="range" min="${q.min}" max="${q.max}" step="1"><b class="v"></b><button class="kfp" title="Fotograma clave anterior">â—€</button><button class="kf" title="AÃ±adir o quitar un fotograma clave en el cabezal">â—†</button><button class="kfn" title="Fotograma clave siguiente">â–¶</button>`;
    d.innerHTML += '<select class="ease" title="Suavizado de esta propiedad"><option value="lineal">Lineal</option><option value="entrada">Suave entrada</option><option value="salida">Suave salida</option><option value="ambos">Suave ambos</option></select>';
    c.appendChild(d);
  }
}
const kfEnCabezal = (p, k) => (p.kf && p.kf[k] || []).find(q => Math.abs(q.t - (T - p.t)) < 0.02);
function valoresParametros() {
  const p = piezaSel(); if (!p) return;
  for (const d of document.querySelectorAll("#paramFilas .prm")) {
    const k = d.dataset.k, q = PARAMS[k], v = Math.round(parametro(p, k) * q.esc);
    const r = d.querySelector("input"); if (document.activeElement !== r) r.value = v;
    d.querySelector(".v").textContent = v + q.un;
    const tiene = p.kf && p.kf[k] && p.kf[k].length;
    d.querySelector(".kf").classList.toggle("on", !!kfEnCabezal(p, k)); d.querySelector(".kf").classList.toggle("tiene", !!tiene);
    d.querySelector(".kfp").disabled = d.querySelector(".kfn").disabled = !tiene;
    d.querySelector(".ease").value = (p.kf && p.kf[k] || []).find(q => q.ease)?.ease || "lineal";
  }
}
function ponerParam(p, k, v) {
  const pts = p.kf && p.kf[k];
  if (pts && pts.length) {
    const tl = +limitar(T - p.t, 0, p.dur).toFixed(3), e = pts.find(q => Math.abs(q.t - tl) < 0.02);
    if (e) e.v = v; else { pts.push({t: tl, v}); pts.sort((a, b) => a.t - b.t); }
  } else if(k.startsWith("rec_")&&p.encuadre?.recorte){p.encuadre.recorte[{rec_x:"x",rec_y:"y",rec_w:"w",rec_h:"h"}[k]]=v;} else p[k] = v;
}
function alternarKf(p, k) {
  p.kf = p.kf || {};
  const tl = +limitar(T - p.t, 0, p.dur).toFixed(3), pts = p.kf[k] || [], i = pts.findIndex(q => Math.abs(q.t - tl) < 0.02);
  if (i >= 0) { const v = pts[i].v; pts.splice(i, 1); if (!pts.length) { delete p.kf[k]; if(k.startsWith("rec_")&&p.encuadre?.recorte)p.encuadre.recorte[{rec_x:"x",rec_y:"y",rec_w:"w",rec_h:"h"}[k]]=v;else p[k] = v; } else p.kf[k] = pts; }
  else {
    if (pts.length >= 24) { avisoEdicion("MÃ¡ximo 24 fotogramas clave por parÃ¡metro."); return; }
    const v = k.startsWith("rec_") ? rectParam(p,k) : PZ.valorKf(p, k, tl), ease = document.querySelector('#paramFilas .prm[data-k="' + k + '"] .ease')?.value || "lineal"; pts.push({t: tl, v, ...(ease !== "lineal" ? {ease} : {})}); pts.sort((a, b) => a.t - b.t); p.kf[k] = pts;
  }
}
$("#paramFilas").addEventListener("input", e => {
  const d = e.target.closest(".prm"), p = piezaSel(); if (!d || !p || e.target.tagName !== "INPUT") return;
  const k = d.dataset.k, q = PARAMS[k]; ponerParam(p, k, +e.target.value / q.esc); d.querySelector(".v").textContent = e.target.value + q.un; tocar();
});
$("#paramFilas").addEventListener("change", e => { const d=e.target.closest(".prm"),p=piezaSel();if(e.target.classList.contains("ease")&&p&&d){for(const q of p.kf?.[d.dataset.k]||[]){if(e.target.value==="lineal")delete q.ease;else q.ease=e.target.value;}confirmar();tocar();}else if(e.target.tagName === "INPUT") { confirmar(); valoresParametros(); } });
$("#paramFilas").addEventListener("click", e => {
  const b = e.target.closest("button"), d = e.target.closest(".prm"), p = piezaSel(); if (!b || !d || !p) return;
  const k = d.dataset.k, pts = p.kf && p.kf[k] || [];
  if (b.classList.contains("kf")) { alternarKf(p, k); confirmar(); valoresParametros(); tocar(); }
  else if (b.classList.contains("kfp")) { const a = [...pts].reverse().find(q => q.t < T - p.t - 0.02); if (a) ir(p.t + a.t); }
  else if (b.classList.contains("kfn")) { const a = pts.find(q => q.t > T - p.t + 0.02); if (a) ir(p.t + a.t); }
});
$("#grupoAnimacion").addEventListener("click", e => {
  const b=e.target.closest("[data-preset]"); if(!b) return; const p=piezaSel(); if(!p) return;
  const fin=Math.max(.01,p.dur), mid=+(fin/2).toFixed(3), presets={
    "zoom-in":{"zoom":[[0,1],[fin,1.25]]}, "zoom-out":{"zoom":[[0,1.25],[fin,1]]},
    golpe:{"zoom":[[0,1],[Math.min(.25,fin),1.45],[fin,1]]},
    "pan-lr":{"pos_x":[[0,-.75],[fin,.75]]}, "pan-rl":{"pos_x":[[0,.75],[fin,-.75]]},
    vaiven:{"pos_x":[[0,-.45],[mid,.45],[fin,-.45]]}
  };
  const spec=presets[b.dataset.preset]; p.kf=p.kf||{};
  for(const [k,pts] of Object.entries(spec)) p.kf[k]=pts.map(([t,v])=>({t:+Math.min(fin,t).toFixed(3),v}));
  confirmar(); valoresParametros(); refrescarTodo();
});
$("#bQuitarAnimacion").onclick=()=>{const p=piezaSel();if(!p)return;p.kf={};confirmar();valoresParametros();refrescarTodo();};

function solapa(p) { return E.piezas.some(o => o.id !== p.id && o.carril === p.carril && o.t < PZ.fin(p) - 1e-3 && p.t < PZ.fin(o) - 1e-3); }
const parejasDe = p => (OPC.enlazada && p.enlace ? E.piezas.filter(q => q.id !== p.id && q.enlace === p.enlace) : []);
function cambiarPieza(fn, ripple) {
  const p = piezaSel(); if (!p) return;
  if (bloqueadas().has(p.carril)) { avisoEdicion("Esa pista estÃ¡ bloqueada."); sincronizarPieza(); return; }
  const copia = JSON.stringify(E.piezas), pars = parejasDe(p), grupo = [p, ...pars], fines = new Map(grupo.map(q => [q.id, PZ.fin(q)]));
  fn(p, pars);
  if (ripple && OPC.ripple) {                      // lo que sigue en esas pistas se desplaza lo que haya cambiado la pieza
    const ids = new Set(grupo.map(q => q.id));
    for (const q of grupo) { const d = PZ.fin(q) - fines.get(q.id); if (Math.abs(d) > 1e-6) for (const o of E.piezas) if (!ids.has(o.id) && o.carril === q.carril && o.t >= fines.get(q.id) - 1e-3) o.t = PZ.redondear(Math.max(0, o.t + d)); }
  }
  if ([p, ...pars].some(solapa)) { E.piezas = JSON.parse(copia); avisoEdicion("Ese cambio se solapa con otra pieza de la misma pista."); }
  else avisoEdicion("");
  asegurarPistas(); T = limitar(T, 0, durSalida()); confirmar(); sincronizarPieza(); tocar();
}
const sobreNumero = (id, fn, ripple) => $(id).addEventListener("change", e => cambiarPieza((p, pars) => fn(p, pars, parseFloat(e.target.value)), ripple));
sobreNumero("#iT", (p, pars, v) => { const t = PZ.redondear(Math.max(0, Math.min(v || 0, PZ.MAX_DURACION - p.dur))), d = t - p.t; for (const q of [p, ...pars]) q.t = PZ.redondear(Math.max(0, q.t + d)); });
sobreNumero("#iDur", (p, pars, v) => {
  const d = Math.max(0.1, v || 0.1) - p.dur;
  for (const q of [p, ...pars]) { if (Math.abs(PZ.fin(q) - PZ.fin(p)) > 0.02 && q !== p) continue; PZ.recortarFinal(q, Math.min(q.dur + d, PZ.topeFuente(q), PZ.MAX_DURACION - q.t)); }
}, true);
sobreNumero("#iVel", (p, pars, v) => {
  const vel = limitar((v || 100) / 100, 0.1, 10);
  for (const q of [p, ...pars]) { if (q.tipo !== "video" && q.tipo !== "audio") continue; const cons = PZ.consumo(q); q.velocidad = vel; PZ.recortarFinal(q, cons / vel); }
}, true);
sobreNumero("#iFi", (p, pars, v) => { p.fundido_in = +limitar(v || 0, 0, Math.max(0, p.dur - p.fundido_out)).toFixed(2); });
sobreNumero("#iFo", (p, pars, v) => { p.fundido_out = +limitar(v || 0, 0, Math.max(0, p.dur - p.fundido_in)).toFixed(2); });
$("#iTrans").addEventListener("change", e => cambiarPieza(p => { p.trans_in = {tipo: e.target.value, dur: (p.trans_in && p.trans_in.dur) || 0.5}; }));
sobreNumero("#iTransDur", (p, pars, v) => { p.trans_in = {tipo: (p.trans_in && p.trans_in.tipo) || "ninguna", dur: +limitar(v || 0.5, 0.1, Math.min(5, p.dur)).toFixed(2)}; });
$("#eModo").addEventListener("change", e => cambiarPieza(p => { p.modo = e.target.value; }));
$("#eRw").addEventListener("input", e => { const p = piezaSel(); if (!p) return; const k = E.salida.ancho * (p.ancho && p.alto ? p.alto / p.ancho : 9 / 16) / E.salida.alto; p.recuadro.w = Math.min(+e.target.value / 100, 1 - p.recuadro.x, (1 - p.recuadro.y) / k); tocar(); });
$("#eRw").addEventListener("change", confirmar);
$("#bEnlazar").onclick = alternarEnlace;
$("#bDividir2").onclick = () => { if (!dividir()) avisoEdicion("Coloca el cabezal en medio de la pieza para dividirla."); };
$("#bBorrar2").onclick = () => borrarSel(false);
$("#bAudioDe").onclick = () => {
  const p = piezaSel(); if (!p || p.tipo !== "video" || !p.tiene_audio) return;
  if (!hayEspacio(1)) return;
  let c = PZ.carrilLibre(E.piezas, "A", p.t, p.dur, E.pistas.audio, 2);
  if (!c) { if (E.pistas.audio < MAX_CARRILES) { E.pistas.audio++; c = "A" + E.pistas.audio; } else { avisoEdicion("No queda una pista de audio libre."); return; } }
  const a = PZ.piezaBase({...PZ.clonar(p), id: PZ.nuevoId(E.piezas), tipo: "audio", carril: c, kf: {}, trans_in: {tipo: "ninguna", dur: 0.5}, zoom: 1, pos_x: 0, pos_y: 0, opacidad: 1});
  delete a.encuadre;
  if (!p.enlace) p.enlace = PZ.nuevoEnlace(); a.enlace = p.enlace;
  E.piezas.push(a); confirmar(); refrescarTodo();
};
$("#bFrente").onclick = () => {
  const ps = piezasSel().filter(q => q.tipo === "video" || q.tipo === "imagen"); if (!ps.length) return;
  const ids = new Set(ps.map(q => q.id)), bl = bloqueadas();
  for (const q of ps) { if (bl.has(q.carril)) continue; const c = carrilArriba(q.t, q.dur, ids); if (!c) { avisoEdicion("No quedan pistas libres por encima."); break; } q.carril = c; }
  asegurarPistas(); confirmar(); refrescarTodo();
};
$("#bPlantillaTramo").onclick = () => {
  const p = piezaEncSel();
  ALCANCE = "tramo";
  for (const q of piezasSel()) if (esEncuadrable(q) && !q.encuadre) q.encuadre = JSON.parse(JSON.stringify(E.encuadre));      // varias seleccionadas: todas reciben la suya
  if (p && p.fuente === "medio" && (T < p.t || T >= PZ.fin(p))) ir(p.t + 0.05);                                       // para que Â«OrigenÂ» enseÃ±e esa pieza
  confirmar(); activarPestana("video"); sincronizarAlcance(); sincronizarModo();
};
function sincronizarPieza() {
  const p = piezaSel(); $("#gPieza").hidden = !p; $("#notaSinPieza").hidden = !!p; $("#gTexto").hidden = !(p && p.tipo === "texto");
  if (!p) return;
  construirParametros(p);
  $("#tPieza").textContent = `${NOMBRE_TIPO[p.tipo]} Â· ${etiquetaPieza(p)}  (${p.carril}${p.enlace ? ", enlazada" : ""})`;
  $("#iT").value = p.t.toFixed(2); $("#iDur").value = p.dur.toFixed(2);
  const av = p.tipo === "video" || p.tipo === "audio"; $("#fVel").hidden = !av; $("#iVel").value = Math.round(velDe(p) * 100);
  $("#iFi").value = p.fundido_in; $("#iFo").value = p.fundido_out;
  const visual = p.tipo === "video" || p.tipo === "imagen";
  $("#gTrans").hidden = !visual; $("#iTrans").value = (p.trans_in && p.trans_in.tipo) || "ninguna"; $("#iTransDur").value = (p.trans_in && p.trans_in.dur) || 0.5;
  $("#gModo").hidden = !(visual && p.fuente === "medio"); $("#eModo").value = p.modo; $("#gRecuadro").hidden = p.modo !== "recuadro"; $("#eRw").value = Math.round(p.recuadro.w * 100);
  $("#gPlantilla").hidden = !piezaEncSel(); $("#bPlantillaTramo").textContent = p.encuadre ? "Editar la plantilla de este tramo" : "Darle una plantilla propia a este tramo";
  const tieneAudio = p.enlace && E.piezas.some(q => q.enlace === p.enlace && q.tipo === "audio");
  $("#bAudioDe").hidden = !(p.fuente === "medio" && p.tipo === "video" && p.tiene_audio && !tieneAudio);
  $("#bFrente").hidden = !(p.tipo === "video" || p.tipo === "imagen"); $("#bEnlazar").textContent = piezasSel().length && piezasSel().every(q => q.enlace) ? "Separar audio y vÃ­deo" : "Enlazar seleccionadas";
  if (p.tipo === "texto") sincronizarTexto(p);
  valoresParametros(); actualizarRecExtra(); actualizarTransformBox(); sincronizarTransformacion();
}

// ------------------------------------------------------------------ texto (Text+)
const ANIM_IN = [["ninguna", "Ninguna"], ["fundido", "Fundido"], ["subir", "Sube"], ["bajar", "Baja"], ["izquierda", "Desde la derecha"], ["derecha", "Desde la izquierda"], ["pop", "Pop (rebote)"], ["maquina", "MÃ¡quina de escribir"]];
const ANIM_OUT = [["ninguna", "Ninguna"], ["fundido", "Fundido"], ["pop", "Pop (se encoge)"]];
function sincronizarTexto(p) {
  const tx = p.texto, sf = $("#xFuente");
  if (!sf.options.length || sf.dataset.n !== String(FUENTES.length)) {
    sf.innerHTML = ""; sf.dataset.n = String(FUENTES.length);
    for (const n of FUENTES) { const o = document.createElement("option"); o.value = n; o.textContent = n; sf.appendChild(o); }
    for (const [id, l] of [["#xAnimIn", ANIM_IN], ["#xAnimOut", ANIM_OUT]]) { const s = $(id); s.innerHTML = ""; for (const [v, t] of l) { const o = document.createElement("option"); o.value = v; o.textContent = t; s.appendChild(o); } }
  }
  if (!FUENTES.includes(tx.fuente)) { const o = document.createElement("option"); o.value = tx.fuente; o.textContent = tx.fuente; sf.appendChild(o); }
  if (document.activeElement !== $("#xTexto")) $("#xTexto").value = tx.contenido;
  sf.value = tx.fuente; $("#xTam").value = tx.tamano; $("#xTamV").textContent = tx.tamano;
  $("#xColor").value = tx.color.toLowerCase(); $("#xContorno").value = tx.color_contorno.toLowerCase(); $("#xGrosor").value = tx.grosor_contorno;
  $("#xSombra").value = tx.sombra; $("#xColSombra").value = tx.color_sombra.toLowerCase();
  $("#xNeg").checked = tx.negrita; $("#xCur").checked = tx.cursiva; $("#xMay").checked = tx.mayusculas;
  $("#xAlin").value = tx.alineacion; $("#xFondo").value = tx.fondo; $("#xColFondo").value = tx.color_fondo.toLowerCase(); $("#xEsp").value = tx.espaciado;
  $("#xX").value = Math.round(tx.x * 100); $("#xY").value = Math.round(tx.y * 100);
  $("#xAnimIn").value = tx.anim_in; $("#xAnimOut").value = tx.anim_out; $("#xAnimDur").value = tx.anim_dur;
}
function enTexto(id, evento, fn, final) {
  $(id).addEventListener(evento, e => { const p = piezaSel(); if (!p || p.tipo !== "texto") return; fn(p.texto, e.target, p); tocar(); if (final) { confirmar(); sincronizarPieza(); } });
  if (!final) $(id).addEventListener("change", () => { confirmar(); sincronizarPieza(); });
}
enTexto("#xTexto", "input", (t, el, p) => { t.contenido = el.value.slice(0, 400) || "Texto"; p.nombre = t.contenido.split("\n")[0].slice(0, 40); });
enTexto("#xFuente", "change", (t, el) => { t.fuente = el.value; }, true);
enTexto("#xTam", "input", (t, el) => { t.tamano = +el.value; $("#xTamV").textContent = el.value; });
enTexto("#xColor", "input", (t, el) => { t.color = el.value.toUpperCase(); });
enTexto("#xContorno", "input", (t, el) => { t.color_contorno = el.value.toUpperCase(); });
enTexto("#xGrosor", "input", (t, el) => { t.grosor_contorno = +el.value; });
enTexto("#xSombra", "input", (t, el) => { t.sombra = +el.value; });
enTexto("#xColSombra", "input", (t, el) => { t.color_sombra = el.value.toUpperCase(); });
enTexto("#xNeg", "change", (t, el) => { t.negrita = el.checked; }, true);
enTexto("#xCur", "change", (t, el) => { t.cursiva = el.checked; }, true);
enTexto("#xMay", "change", (t, el) => { t.mayusculas = el.checked; }, true);
enTexto("#xAlin", "change", (t, el) => { t.alineacion = el.value; }, true);
enTexto("#xFondo", "change", (t, el) => { t.fondo = el.value; }, true);
enTexto("#xColFondo", "input", (t, el) => { t.color_fondo = el.value.toUpperCase(); });
enTexto("#xEsp", "input", (t, el) => { t.espaciado = +el.value; });
enTexto("#xX", "input", (t, el) => { t.x = +el.value / 100; });
enTexto("#xY", "input", (t, el) => { t.y = +el.value / 100; });
enTexto("#xAnimIn", "change", (t, el) => { t.anim_in = el.value; }, true);
enTexto("#xAnimOut", "change", (t, el) => { t.anim_out = el.value; }, true);
enTexto("#xAnimDur", "change", (t, el) => { t.anim_dur = +limitar(parseFloat(el.value) || 0.4, 0.1, 5).toFixed(2); }, true);
$("#xTexto").addEventListener("change", () => { confirmar(); sincronizarPieza(); });
let nodoTexto = null;
function posicionarNodoTexto() {
  const p = piezaSel(), c = p && p.tipo === "texto" && T >= p.t && T < PZ.fin(p) ? CAJAS_TEXTO[p.id] : null;
  if (!c) { if (nodoTexto) nodoTexto.hidden = true; return; }
  if (!nodoTexto) {
    nodoTexto = document.createElement("div"); nodoTexto.className = "rec-texto"; nodoTexto.title = "Arrastra para mover el texto";
    nodoTexto.addEventListener("pointerdown", empezarArrastreTexto); $("#overlaySalida").appendChild(nodoTexto);
  }
  nodoTexto.hidden = false;
  const pct = v => (v * 100).toFixed(2) + "%";
  nodoTexto.style.left = pct(c.x / c.cw); nodoTexto.style.top = pct(c.y / c.ch); nodoTexto.style.width = pct(c.w / c.cw); nodoTexto.style.height = pct(c.h / c.ch);
}
function empezarArrastreTexto(ev) {
  const p = piezaSel(); if (!p || p.tipo !== "texto") return;
  const cj = LZ.getBoundingClientRect(), x0 = p.texto.x, y0 = p.texto.y, sx = ev.clientX, sy = ev.clientY;
  arrastrar(ev, nodoTexto, e => {
    p.texto.x = +limitar(x0 + (e.clientX - sx) / cj.width, 0, 1).toFixed(4); p.texto.y = +limitar(y0 + (e.clientY - sy) / cj.height, 0, 1).toFixed(4);
    $("#xX").value = Math.round(p.texto.x * 100); $("#xY").value = Math.round(p.texto.y * 100);
  }, () => { confirmar(); });
}

// recuadro rosa de una imagen/vÃ­deo en modo Â«recuadroÂ»
let recNodo = null;
function posicionarRecExtra(it) {
  const ar = it.ancho && it.alto ? it.alto / it.ancho : 9 / 16, pct = v => (v * 100).toFixed(3) + "%";
  recNodo.style.left = pct(it.recuadro.x); recNodo.style.top = pct(it.recuadro.y); recNodo.style.width = pct(it.recuadro.w);
  recNodo.style.height = pct(it.recuadro.w * E.salida.ancho * ar / E.salida.alto);
}
function actualizarRecExtra() {
  const it = piezaSel(), ver = it && (it.tipo === "video" || it.tipo === "imagen") && it.fuente === "medio" && it.modo === "recuadro";
  if (!ver) { if (recNodo) { recNodo.remove(); recNodo = null; } return; }
  if (!recNodo) {
    recNodo = document.createElement("div"); recNodo.className = "rec-extra"; recNodo.innerHTML = '<i class="m"></i>';
    recNodo.addEventListener("pointerdown", ev => empezarRecExtra(ev)); $("#overlaySalida").appendChild(recNodo);
  }
  posicionarRecExtra(it);
}
function empezarRecExtra(ev) {
  const it = piezaSel(); if (!it) return;
  const caja = LZ.getBoundingClientRect(), r0 = {...it.recuadro}, redim = ev.target.classList.contains("m"), sx = ev.clientX, sy = ev.clientY;
  const k = E.salida.ancho * (it.ancho && it.alto ? it.alto / it.ancho : 9 / 16) / E.salida.alto;
  arrastrar(ev, recNodo, e => {
    const dx = (e.clientX - sx) / caja.width, dy = (e.clientY - sy) / caja.height;
    if (!redim) { it.recuadro.x = limitar(r0.x + dx, 0, 1 - r0.w); it.recuadro.y = limitar(r0.y + dy, 0, Math.max(0, 1 - r0.w * k)); }
    else it.recuadro.w = limitar(r0.w + dx, 0.1, Math.min(1 - r0.x, (1 - r0.y) / k));
    posicionarRecExtra(it); $("#eRw").value = Math.round(it.recuadro.w * 100);
  }, confirmar);
}

// ------------------------------------------------------------------ alcance de la plantilla (todo el clip / solo este tramo)
function sincronizarAlcance() {
  const p = piezaEncSel(), g = $("#gAlcance"); g.hidden = !p;
  if (!p) return;
  const medio = p.fuente === "medio";
  document.querySelectorAll("input[name=alc]").forEach(r => { r.checked = r.value === ALCANCE; });
  document.querySelector("input[name=alc][value=todo]").parentElement.hidden = medio;
  $("#bAplicarTodos").hidden = medio;
  const n = E.piezas.filter(q => q.fuente === "clip" && q.tipo === "video" && q.encuadre).length;
  const otras = piezasSel().filter(q => q.id !== p.id && esEncuadrable(q)).length;
  $("#notaAlcance").textContent = medio
    ? (p.encuadre ? "Editas la plantilla de este vÃ­deo aÃ±adido (en Â«OrigenÂ» ves ESE vÃ­deo)." : "Este vÃ­deo se ve a pantalla completa. Elige una plantilla o ajusta las zonas y se crea una propia para Ã©l.")
    : ALCANCE === "tramo"
      ? (p.encuadre ? "Editas la plantilla PROPIA de este tramo." : "Este tramo usa la plantilla general: en cuanto cambies algo se crea una propia solo para Ã©l.")
      : "Los cambios valen para todos los tramos que no tengan plantilla propia." + (n ? ` (${n} tramo(s) tienen la suya.)` : "");
  $("#bQuitarPropia").disabled = !p.encuadre; $("#bAplicarTodos").disabled = !n && !p.encuadre;
  $("#bCopiarSel").hidden = !otras; $("#bCopiarSel").textContent = `Copiar esta plantilla a las otras ${otras} seleccionada(s)`;
}
document.querySelectorAll("input[name=alc]").forEach(r => r.addEventListener("change", () => { ALCANCE = r.value; sincronizarAlcance(); sincronizarModo(); }));
$("#bQuitarPropia").onclick = () => { const p = piezaEncSel(); if (!p || !p.encuadre) return; delete p.encuadre; if (p.fuente === "clip") ALCANCE = "todo"; confirmar(); sincronizarAlcance(); sincronizarModo(); tocar(); };
$("#bCopiarSel").onclick = () => {
  const p = piezaEncSel(); if (!p) return;
  const origen = JSON.parse(JSON.stringify(p.encuadre || E.encuadre)); let n = 0;
  for (const q of piezasSel()) if (q.id !== p.id && esEncuadrable(q)) { q.encuadre = JSON.parse(JSON.stringify(origen)); n++; }
  if (n) { confirmar(); sincronizarAlcance(); tocar(); avisoEdicion(`Plantilla copiada a ${n} pieza(s).`); }
};
$("#bAplicarTodos").onclick = () => {
  const p = piezaClipSel(); if (!p) return;
  if (!confirm("Se usarÃ¡ la plantilla que ves ahora en TODOS los tramos y se quitarÃ¡n las plantillas propias. Â¿Continuar?")) return;
  E.encuadre = JSON.parse(JSON.stringify(ENC()));
  for (const q of E.piezas) delete q.encuadre;
  ALCANCE = "todo"; confirmar(); refrescarTodo();
};

// ------------------------------------------------------------------ inspector: encuadre
function sincronizarZoom() {
  const m = ENC().modo; if (m !== "recorte") return;
  const rc = rectAspecto(ENC().recorte, ORI().ancho, ORI().alto, aspectos().recorte);
  const maxW = rectAspecto({x: 0, y: 0, w: 1, h: 1}, ORI().ancho, ORI().alto, aspectos().recorte).w;
  const z = Math.round(maxW / rc.w * 100); $("#zoomRecorte").value = z; $("#zoomVal").textContent = z + "%";
}
function sincronizarModo() {
  const m = ENC().modo;
  document.querySelectorAll("#modos label").forEach(l => { l.classList.toggle("on", l.dataset.m === m); l.querySelector("input").checked = l.dataset.m === m; });
  $("#gRecorte").hidden = m !== "recorte"; $("#gDividido").hidden = m !== "dividido"; $("#gTres").hidden = m !== "tres"; $("#gCapas").hidden = m !== "capas";
  const ln = ENC().linea || {ancho: 0, color: "#FFFFFF"}; $("#linAncho").value = ln.ancho; $("#linVal").textContent = ln.ancho + "px"; $("#linColor").value = ln.color.toLowerCase();
  sincronizarCapas(); dibujarDestino();
  const [a3, b3] = ENC().alturas_tres.map(v => Math.round(v * 100));
  $("#alt3a").value = a3; $("#alt3aVal").textContent = a3 + "%"; $("#alt3b").value = b3; $("#alt3bVal").textContent = b3 + "%"; $("#alt3c").textContent = `Franja 3: ${100 - a3 - b3}% (el resto). Orden de arriba abajo: ${ENC().orden_tres.map(k => k.toUpperCase()).join(" Â· ")}`;
  $("#bInvertir").classList.toggle("activo", !!ENC().invertido);
  $("#propArriba").value = Math.round(ENC().proporcion_arriba * 100); $("#propVal").textContent = Math.round(ENC().proporcion_arriba * 100) + "%";
  $("#bCara").disabled = !CARA.disponible;
  const av = $("#avisoCara"); if (!CARA.disponible) { av.hidden = false; av.textContent = CARA.mensaje; }
  sincronizarZoom(); dibujarRecuadros();
  $("#infoSalida").textContent = `${E.salida.ancho}Ã—${E.salida.alto}`;
}
document.querySelectorAll("#modos input").forEach(r => r.addEventListener("change", () => {
  ENCW().modo = r.value; ENCW().plantilla = "";
  const completo = q => q.x === 0 && q.y === 0 && q.w === 1 && q.h === 1;
  if (r.value === "dividido" && completo(ENCW().arriba) && completo(ENCW().abajo)) {
    // Primera vez: valores razonables (juego centrado arriba, esquina inferior derecha abajo) hasta detectar la cara.
    ENCW().arriba = {x: 0.2, y: 0, w: 0.6, h: 1}; ENCW().abajo = {x: 0.7, y: 0.55, w: 0.28, h: 0.42};
  }
  confirmar(); sincronizarModo();
}));
$("#zoomRecorte").addEventListener("input", e => {
  const z = +e.target.value / 100, asp = aspectos().recorte, W = ORI().ancho, H = ORI().alto;
  const cur = rectAspecto(ENCW().recorte, W, H, asp), max = rectAspecto({x: 0, y: 0, w: 1, h: 1}, W, H, asp);
  const w = max.w / z, h = max.h / z, cx = cur.x + cur.w / 2, cy = cur.y + cur.h / 2;
  ENCW().recorte = {x: limitar(cx - w / 2, 0, 1 - w), y: limitar(cy - h / 2, 0, 1 - h), w, h};
  $("#zoomVal").textContent = Math.round(z * 100) + "%"; dibujarRecuadros();
});
$("#zoomRecorte").addEventListener("change", confirmar);
$("#bCentrar").onclick = () => { const r = rectAspecto(ENCW().recorte, ORI().ancho, ORI().alto, aspectos().recorte); ENCW().recorte = {x: (1 - r.w) / 2, y: (1 - r.h) / 2, w: r.w, h: r.h}; confirmar(); sincronizarModo(); };
$("#bRestRecorte").onclick = () => { ENCW().recorte = {x: 0, y: 0, w: 1, h: 1}; confirmar(); sincronizarModo(); };
$("#bRestDiv").onclick = () => { ENCW().arriba = {x: 0.2, y: 0, w: 0.6, h: 1}; ENCW().abajo = {x: 0.7, y: 0.55, w: 0.28, h: 0.42}; confirmar(); sincronizarModo(); };
$("#linAncho").addEventListener("input", e => { ENCW().linea.ancho = +e.target.value; $("#linVal").textContent = e.target.value + "px"; });
$("#linAncho").addEventListener("change", confirmar);
$("#linColor").addEventListener("input", e => { ENCW().linea.color = e.target.value.toUpperCase(); });
$("#linColor").addEventListener("change", confirmar);
$("#propArriba").addEventListener("input", e => { ENCW().proporcion_arriba = +e.target.value / 100; $("#propVal").textContent = e.target.value + "%"; dibujarRecuadros(); });
$("#bInvertir").onclick = () => { ENCW().invertido = !ENCW().invertido; confirmar(); sincronizarModo(); };
const REST3 = () => ({a: {x: 0.2, y: 0, w: 0.6, h: 1}, b: {x: 0.7, y: 0.55, w: 0.28, h: 0.42}, c: {x: 0, y: 0, w: 1, h: 1}});
$("#bRest3").onclick = () => { ENCW().tres = REST3(); ENCW().orden_tres = ["a", "b", "c"]; ENCW().alturas_tres = [0.34, 0.33]; confirmar(); sincronizarModo(); };
$("#bRotar3").onclick = () => { const o = ENCW().orden_tres; ENCW().orden_tres = [o[1], o[2], o[0]]; confirmar(); sincronizarModo(); };
$("#bInv3").onclick = () => { ENCW().orden_tres = ENCW().orden_tres.slice().reverse(); confirmar(); sincronizarModo(); };
for (const [id, i] of [["#alt3a", 0], ["#alt3b", 1]]) {
  $(id).addEventListener("input", e => { const al = ENCW().alturas_tres, otro = al[1 - i]; al[i] = Math.min(+e.target.value / 100, 0.9 - otro); sincronizarModo(); });
  $(id).addEventListener("change", confirmar);
}
$("#propArriba").addEventListener("change", confirmar);
async function detectarCara(boton, nota) {
  const b = boton; b.disabled = true; nota.textContent = "Buscando la caraâ€¦";
  try {
    const capas = ENCW().modo === "capas";
    const d = await post("cara", {proporcion_arriba: capas ? 0.5 : (ENCW().invertido ? 1 - ENCW().proporcion_arriba : ENCW().proporcion_arriba), salida: E.salida});
    if (d.encontrada) {
      const camAnt = JSON.stringify(camRect());
      ENCW().arriba = d.arriba; ENCW().abajo = d.abajo;
      if (capas) for (const c of capasE()) { if (c.rol === "cam" || (c.rol === "fondo" && JSON.stringify(c.fuente) === camAnt)) c.fuente = {...d.abajo}; else if (c.rol === "juego") c.fuente = {...d.arriba}; }
      else ENCW().modo = "dividido";
      confirmar(); sincronizarModo(); nota.textContent = `Cara encontrada (fiabilidad ${Math.round(d.cara.confianza * 100)} %). Ajusta los recuadros si hace falta.`;
    } else nota.textContent = d.mensaje;
  } catch (e) { nota.textContent = e.message; }
  b.disabled = !CARA.disponible;
}
$("#bCara").onclick = () => detectarCara($("#bCara"), $("#notaCara"));
$("#bCara").hidden = true;
$("#notaCara").hidden = true;

// ------------------------------------------------------------------ inspector: subtÃ­tulos
const estilo = () => E.subtitulos.estilo;
function sincronizarSubs() {
  const s = E.subtitulos, st = s.estilo;
  $("#subActivos").checked = s.activos; $("#fTam").value = st.tamano; $("#fTamVal").textContent = st.tamano;
  $("#fNegrita").checked = st.negrita; $("#fCursiva").checked = st.cursiva; $("#fMayus").checked = st.mayusculas;
  $("#cTexto").value = st.color.toLowerCase(); $("#cResalt").value = st.color_resaltado.toLowerCase(); $("#cContorno").value = st.color_contorno.toLowerCase(); $("#cFondo").value = st.color_fondo.toLowerCase();
  $("#fResaltar").checked = st.resaltar_palabra; $("#fFondo").value = st.fondo; $("#fGrosor").value = st.grosor_contorno;
  $("#fPosY").value = Math.round(st.posicion_y * 100); $("#fPalabras").value = st.palabras_por_pagina;
  $("#filaContorno").style.display = st.fondo === "caja" ? "none" : "";
  llenarFuentes($("#fBuscar").value);
  construirHablantes();
  construirListaSub();
}
function construirHablantes() {
  const f = $("#filaHablantes"); f.innerHTML = ""; const st = estilo();
  if (!st.hablantes) st.hablantes = ["#FFFFFF", "#6EC1FF", "#FFB347", "#9BE564"];
  st.hablantes.forEach((c, i) => {
    const et = document.createElement("span"); et.className = "hab-et"; et.textContent = "H" + (i + 1); et.style.minWidth = "auto";
    const inp = document.createElement("input"); inp.type = "color"; inp.value = c.toLowerCase();
    inp.addEventListener("input", () => { st.hablantes[i] = inp.value.toUpperCase(); dibujar(); construirChips(); });
    inp.addEventListener("change", confirmar);
    f.append(et, inp);
  });
  const sw = $("#swatches"); sw.innerHTML = "";
  st.hablantes.forEach((c, i) => {
    const b = document.createElement("button"); b.className = "swatch"; b.style.background = c; b.title = "Color del hablante " + (i + 1);
    b.onclick = () => colorearPalabras(st.hablantes[i]); sw.appendChild(b);
  });
}
let PSEL = new Set(), PLINEA = -1, PULTIMA = -1;
const colorDePalabra = (l, w) => w.color || (l.hablante && estilo().hablantes ? estilo().hablantes[l.hablante - 1] : estilo().color);
function construirChips() {
  const g = $("#grupoPalabras"), l = sel && sel.tipo === "sub" ? E.subtitulos.lineas[sel.i] : null;
  g.hidden = !l; if (!l) { PLINEA = -1; return; }
  if (PLINEA !== sel.i) { PSEL = new Set(); PLINEA = sel.i; PULTIMA = -1; }
  const c = $("#chips"); c.innerHTML = "";
  l.palabras.forEach((w, i) => {
    const b = document.createElement("span"); b.className = "chip" + (PSEL.has(i) ? " on" : ""); b.textContent = w.texto; b.style.color = colorDePalabra(l, w);
    b.onclick = ev => {
      if (ev.shiftKey && PULTIMA >= 0) { for (let k = Math.min(PULTIMA, i); k <= Math.max(PULTIMA, i); k++) PSEL.add(k); }
      else { PSEL.has(i) ? PSEL.delete(i) : PSEL.add(i); PULTIMA = i; }
      construirChips();
    };
    c.appendChild(b);
  });
}
function colorearPalabras(hex) {
  const l = sel && sel.tipo === "sub" ? E.subtitulos.lineas[sel.i] : null;
  if (!l || !PSEL.size) { $("#notaSub").textContent = "Marca primero las palabras que quieres colorear."; return; }
  for (const i of PSEL) if (l.palabras[i]) { if (hex) l.palabras[i].color = hex.toUpperCase(); else delete l.palabras[i].color; }
  confirmar(); construirChips(); dibujar();
}
$("#pTodas").onclick = () => { const l = E.subtitulos.lineas[sel && sel.tipo === "sub" ? sel.i : -1]; if (l) { PSEL = new Set(l.palabras.map((_, i) => i)); construirChips(); } };
$("#pNinguna").onclick = () => { PSEL = new Set(); construirChips(); };
$("#pQuitar").onclick = () => colorearPalabras(null);
$("#pAplicar").onclick = () => colorearPalabras($("#cPalabra").value);
$("#cPalabra").addEventListener("input", e => { const l = sel && sel.tipo === "sub" ? E.subtitulos.lineas[sel.i] : null; if (!l) return; for (const i of PSEL) if (l.palabras[i]) l.palabras[i].color = e.target.value.toUpperCase(); dibujar(); });
$("#cPalabra").addEventListener("change", () => { confirmar(); construirChips(); });
function llenarFuentes(filtro) {
  const sel = $("#fFuente"), actual = estilo().fuente, f = (filtro || "").toLowerCase();
  const lista = FUENTES.filter(n => n.toLowerCase().includes(f));
  if (actual && !lista.includes(actual) && !f) lista.unshift(actual);
  sel.innerHTML = "";
  for (const n of lista) { const o = document.createElement("option"); o.value = n; o.textContent = n; o.style.fontFamily = `"${n}"`; if (n === actual) o.selected = true; sel.appendChild(o); }
  const o = sel.querySelector("option:checked"); if (o) o.scrollIntoView({block: "nearest"});
}
function enlazar(id, evento, fn, confirmarAlSoltar) {
  $(id).addEventListener(evento, e => { fn(e); dibujar(); });
  if (confirmarAlSoltar) $(id).addEventListener("change", confirmar);
}
enlazar("#subActivos", "change", e => { E.subtitulos.activos = e.target.checked; confirmar(); });
enlazar("#fTam", "input", e => { estilo().tamano = +e.target.value; $("#fTamVal").textContent = e.target.value; }, true);
enlazar("#fNegrita", "change", e => { estilo().negrita = e.target.checked; confirmar(); });
enlazar("#fCursiva", "change", e => { estilo().cursiva = e.target.checked; confirmar(); });
enlazar("#fMayus", "change", e => { estilo().mayusculas = e.target.checked; confirmar(); });
enlazar("#cTexto", "input", e => { estilo().color = e.target.value.toUpperCase(); }, true);
enlazar("#cResalt", "input", e => { estilo().color_resaltado = e.target.value.toUpperCase(); }, true);
enlazar("#cContorno", "input", e => { estilo().color_contorno = e.target.value.toUpperCase(); }, true);
enlazar("#cFondo", "input", e => { estilo().color_fondo = e.target.value.toUpperCase(); }, true);
enlazar("#fResaltar", "change", e => { estilo().resaltar_palabra = e.target.checked; confirmar(); });
enlazar("#fFondo", "change", e => { estilo().fondo = e.target.value; $("#filaContorno").style.display = e.target.value === "caja" ? "none" : ""; confirmar(); });
enlazar("#fGrosor", "input", e => { estilo().grosor_contorno = +e.target.value; }, true);
enlazar("#fPosY", "input", e => { estilo().posicion_y = +e.target.value / 100; }, true);
enlazar("#fPalabras", "change", e => { estilo().palabras_por_pagina = limitar(+e.target.value || 1, 1, 12); confirmar(); });
$("#fBuscar").addEventListener("input", e => llenarFuentes(e.target.value));
$("#fFuente").addEventListener("change", e => { estilo().fuente = e.target.value; confirmar(); dibujar(); });

function repartirPalabras(texto, ini, fin) {
  const tk = texto.split(/\s+/).filter(Boolean), pesos = tk.map(t => Math.max(1, t.length)), tot = pesos.reduce((a, b) => a + b, 0);
  let c = ini; return tk.map((t, i) => { const sig = c + (fin - ini) * pesos[i] / tot, w = {texto: t, inicio: +c.toFixed(3), fin: +sig.toFixed(3)}; c = sig; return w; });
}
function construirListaSub() {
  const cont = $("#listaSub"); cont.innerHTML = "";
  E.subtitulos.lineas.forEach((l, i) => {
    const fila = document.createElement("div"); fila.className = "fila-sub"; fila.dataset.i = i;
    fila.innerHTML = `<input type="number" step="0.05" min="0" class="ini"><input type="number" step="0.05" min="0" class="fin"><input type="text" class="txt"><select class="hab" title="Hablante de la lÃ­nea"><option value="0">H â€”</option><option value="1">H1</option><option value="2">H2</option><option value="3">H3</option><option value="4">H4</option></select><button title="Borrar lÃ­nea">Ã—</button>`;
    fila.querySelector(".hab").value = l.hablante || 0;
    fila.querySelector(".hab").addEventListener("change", e => { if (+e.target.value) l.hablante = +e.target.value; else delete l.hablante; confirmar(); construirChips(); dibujar(); });
    fila.querySelector(".ini").value = l.inicio.toFixed(2); fila.querySelector(".fin").value = l.fin.toFixed(2); fila.querySelector(".txt").value = l.texto;
    const cambiarTiempos = () => {
      const ni = limitar(parseFloat(fila.querySelector(".ini").value) || 0, 0, E.origen.duracion), nf = limitar(parseFloat(fila.querySelector(".fin").value) || 0, 0, E.origen.duracion);
      if (nf - ni < 0.1) { refrescarFilaSub(i); return; }
      const k = (nf - ni) / (l.fin - l.inicio || 1), o = l.inicio;
      l.palabras = l.palabras.map(w => ({...w, inicio: +(ni + (w.inicio - o) * k).toFixed(3), fin: +(ni + (w.fin - o) * k).toFixed(3)}));
      l.inicio = ni; l.fin = nf; confirmar(); dibujar();
    };
    fila.querySelector(".ini").addEventListener("change", cambiarTiempos); fila.querySelector(".fin").addEventListener("change", cambiarTiempos);
    const txt = fila.querySelector(".txt");
    txt.addEventListener("input", () => {
      const nuevo = txt.value.replace(/\s+/g, " ").trim(); if (!nuevo) return;
      const tk = nuevo.split(" ");
      if (tk.length === l.palabras.length) l.palabras.forEach((w, j) => w.texto = tk[j]); else l.palabras = repartirPalabras(nuevo, l.inicio, l.fin);
      l.texto = nuevo; dibujar();
    });
    txt.addEventListener("change", () => { confirmar(); construirChips(); });
    fila.addEventListener("focusin", () => { seleccionarSub(i); ir(oriASalSuave(l.inicio)); });
    fila.querySelector("button").onclick = () => { E.subtitulos.lineas.splice(i, 1); sel = null; SEL.clear(); confirmar(); refrescarTodo(); };
    cont.appendChild(fila);
  });
  marcarFilaSub();
}
function refrescarFilaSub(i) {
  const f = $(`#listaSub .fila-sub[data-i="${i}"]`), l = E.subtitulos.lineas[i]; if (!f) return;
  f.querySelector(".ini").value = l.inicio.toFixed(2); f.querySelector(".fin").value = l.fin.toFixed(2);
}
function marcarFilaSub() {
  document.querySelectorAll("#listaSub .fila-sub").forEach(f => f.classList.toggle("sel", !!sel && sel.tipo === "sub" && +f.dataset.i === sel.i));
  const f = $("#listaSub .fila-sub.sel"); if (f) f.scrollIntoView({block: "nearest"});
  construirChips();
}
$("#bNuevaLinea").onclick = () => {
  const o = salAOri(T); if (o === null) { $("#notaSub").textContent = "Coloca el cabezal sobre una parte del clip para aÃ±adir una lÃ­nea."; return; }
  const fin = Math.min(E.origen.duracion, o + 2); if (fin - o < 0.2) return;
  const lineas = E.subtitulos.lineas; lineas.push({inicio: +o.toFixed(3), fin: +fin.toFixed(3), texto: "Texto", palabras: [{texto: "Texto", inicio: +o.toFixed(3), fin: +fin.toFixed(3)}]});
  lineas.sort((a, b) => a.inicio - b.inicio); E.subtitulos.activos = true; const idx = lineas.findIndex(l => l.inicio === +o.toFixed(3) && l.texto === "Texto");
  confirmar(); refrescarTodo(); seleccionarSub(idx);
  const f = $("#listaSub .fila-sub.sel .txt"); if (f) { f.focus(); f.select(); }
};
async function generarSubs(origen) {
  const err = $("#errSub"), nota = $("#notaSub"); err.hidden = true;
  if (E.subtitulos.lineas.length && !confirm("Esto reemplaza los subtÃ­tulos actuales. Â¿Continuar?")) return;
  $("#bWhisper").disabled = $("#bStream").disabled = true;
  try {
    await post("subtitulos", {origen});
    for (;;) {
      await new Promise(r => setTimeout(r, 1000));
      const d = await api("subtitulos/estado");
      if (d.estado === "trabajando") { nota.textContent = d.mensaje || "Trabajandoâ€¦"; continue; }
      if (d.estado === "listo") { E.subtitulos.lineas = d.lineas; E.subtitulos.activos = true; confirmar(); refrescarTodo(); nota.textContent = `${d.lineas.length} lÃ­neas generadas. Edita el texto o los tiempos si quieres.`; break; }
      throw new Error(d.mensaje || "No se pudieron generar los subtÃ­tulos.");
    }
  } catch (e) { err.hidden = false; err.textContent = e.message; nota.textContent = ""; }
  $("#bWhisper").disabled = $("#bStream").disabled = false;
}
$("#bWhisper").onclick = () => generarSubs("whisper");
$("#bStream").onclick = () => generarSubs("stream");

// ------------------------------------------------------------------ exportar (resumen)
function resumenExport() {
  const sub = E.subtitulos.activos && E.subtitulos.lineas.length ? `${E.subtitulos.lineas.length} lÃ­neas de subtÃ­tulos` : "sin subtÃ­tulos";
  const modos = {recorte: "recortado", ajustar: "ajustado con fondo desenfocado", dividido: E.encuadre.invertido ? "pantalla dividida (cara arriba)" : "pantalla dividida", tres: "tres pantallas", capas: "plantilla de capas"};
  const nclip = E.piezas.filter(p => p.fuente === "clip" && p.tipo === "video").length, propias = E.piezas.filter(p => p.encuadre).length;
  const nmed = E.piezas.filter(p => p.fuente === "medio" && p.tipo !== "audio").length, ntxt = E.piezas.filter(p => p.tipo === "texto").length;
  $("#resumenExport").textContent = `${E.salida.ancho}Ã—${E.salida.alto} Â· ${fmt(durSalida())} Â· ${nclip} trozo(s) del clip Â· ${modos[E.encuadre.modo] || E.encuadre.modo}${propias ? ` (${propias} con plantilla propia)` : ""} Â· ${sub} Â· ${E.origen.pistas_audio} pista(s) de audio${nmed ? " Â· " + nmed + " medio(s)" : ""}${ntxt ? " Â· " + ntxt + " texto(s)" : ""}.`;
}

let temporizadorDestino = null;
async function refrescarDestino() {
  if (!E) return;
  try {
    const d = await post("destino", E);
    $("#expNombre").placeholder = d.nombre_defecto;
    $("#expCarpeta").value = d.carpeta_base || "(junto al clip, en la carpeta Â«editadosÂ»)";
    $("#expRuta").textContent = "Se guardarÃ¡ en: " + d.archivo + (d.existe ? (E.salida.no_sobrescribir ? "  (ya existe: se crearÃ¡ con un nÃºmero)" : "  (ya existe: se reemplazarÃ¡)") : "");
  } catch (e) { $("#expRuta").textContent = ""; }
}
function programarDestino() { clearTimeout(temporizadorDestino); temporizadorDestino = setTimeout(refrescarDestino, 350); }
$("#expNombre").addEventListener("input", e => { E.salida.nombre = e.target.value; programarDestino(); });
$("#expNombre").addEventListener("change", () => { confirmar(); });
$("#expNoSob").addEventListener("change", e => { E.salida.no_sobrescribir = e.target.checked; confirmar(); programarDestino(); });
$("#bCambiarCarpeta").onclick = async () => {
  const err = $("#errDestino"); err.hidden = true;
  try {
    const r = await fetch("/api/seleccionar/carpeta", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({inicial: $("#expCarpeta").value.startsWith("(") ? "" : $("#expCarpeta").value})});
    const d = await r.json(); if (!r.ok || d.ok === false) throw new Error(d.error || "No se pudo abrir el selector.");
    if (d.cancelado) return;
    const g = await fetch("/api/configuracion", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({CARPETA_EDITADOS: d.ruta})});
    const j = await g.json(); if (!g.ok || j.ok === false) throw new Error(j.error || "No se pudo guardar la carpeta.");
    refrescarDestino();
  } catch (e) { err.hidden = false; err.textContent = e.message; }
};
function sincronizarDestino() { $("#expNombre").value = E.salida.nombre || ""; $("#expNoSob").checked = !!E.salida.no_sobrescribir; }
let sondeoRender = null;
let PANEL_VIEJO = false;
const MSG_VIEJO = "El panel de MKClips que estÃ¡ abierto es una versiÃ³n anterior: no guarda las plantillas nuevas y el vÃ­deo exportado saldrÃ­a distinto. CiÃ©rralo por completo (cierra su ventana de consola) y vuelve a pulsar Â«EditarÂ» en MKClips.";
function avisarPanelViejo() { PANEL_VIEJO = true; $("#estadoGuardado").textContent = "âš  Panel desactualizado"; $("#estadoGuardado").style.color = "#ffb454"; if (!avisarPanelViejo.hecho) { avisarPanelViejo.hecho = true; setTimeout(() => alert(MSG_VIEJO), 300); } }
async function iniciarRender() {
  if (PANEL_VIEJO) { alert(MSG_VIEJO); return; }
  if ($("#bRender").disabled) return;
  const err = $("#errRender"); err.hidden = true; $("#filaAbrir").hidden = true;
  try { await post("renderizar", E); } catch (e) { err.hidden = false; err.textContent = e.message; return; }
  $("#bRender").disabled = true; $("#bCancelar").hidden = false; $("#barraRender").hidden = false;
  clearInterval(sondeoRender);
  sondeoRender = setInterval(async () => {
    try {
      const d = await api("render/estado");
      $("#barraRender i").style.width = Math.round((d.progreso || 0) * 100) + "%";
      $("#msgRender").textContent = d.estado === "trabajando" ? `${d.mensaje || "Renderizandoâ€¦"} ${Math.round((d.progreso || 0) * 100)} %` : "";
      if (d.estado !== "trabajando") {
        clearInterval(sondeoRender); $("#bRender").disabled = false; $("#bCancelar").hidden = true;
        if (d.estado === "listo") { $("#msgRender").textContent = `Listo (${d.codificador}, ${fmt(d.duracion)}). Guardado en: ${d.archivo}`; $("#filaAbrir").hidden = false; }
        else if (d.estado === "cancelado") { $("#msgRender").textContent = "Render cancelado."; $("#barraRender").hidden = true; }
        else { err.hidden = false; err.textContent = d.mensaje || "El render fallÃ³."; $("#barraRender").hidden = true; }
      }
    } catch (e) { /* se reintenta */ }
  }, 800);
}
$("#bRender").onclick = iniciarRender;
$("#bCancelar").onclick = () => post("render/cancelar");
$("#bAbrir").onclick = () => post("abrir").catch(e => alert(e.message));
$("#bCarpeta").onclick = () => post("abrir", {carpeta: true}).catch(e => alert(e.message));
$("#bIrExportar").onclick = () => { activarPestana("export"); iniciarRender(); };

// ------------------------------------------------------------------ pestaÃ±as, herramientas y atajos
function activarPestana(p) {
  document.querySelectorAll(".pestanas button").forEach(b => b.classList.toggle("activo", b.dataset.p === p));
  document.querySelectorAll(".panel").forEach(x => x.classList.toggle("on", x.id === "p-" + p));
  if (p === "export") { resumenExport(); sincronizarDestino(); refrescarDestino(); }
}
document.querySelectorAll(".pestanas button").forEach(b => b.onclick = () => activarPestana(b.dataset.p));
$("#bAnimar").onclick = () => {
  if (!piezaSel()) { avisoEdicion("Primero haz clic en una pieza de la lÃ­nea de tiempo."); return; }
  activarPestana("pistas");
  const g = $("#grupoAnimacion"); g.open = true; g.scrollIntoView({block: "nearest"});
};
function poner(h) {
  herramienta = h; tocar();
  $("#tSel").classList.toggle("activo", h === "sel"); $("#tCuchilla").classList.toggle("activo", h === "cuchilla"); $("#tTrim").classList.toggle("activo", h === "trim");
}
$("#tSel").onclick = () => poner("sel"); $("#tCuchilla").onclick = () => poner("cuchilla"); $("#tTrim").onclick = () => poner("trim");
function sincronizarOpciones() {
  $("#oRipple").classList.toggle("activo", OPC.ripple); $("#oIman").classList.toggle("activo", OPC.iman); $("#oEnlazada").classList.toggle("activo", OPC.enlazada);
  $("#oColocar").value = OPC.colocar;
}
function cambiarOpcion(k) { OPC[k] = !OPC[k]; guardado("opc", JSON.stringify(OPC)); sincronizarOpciones(); }
$("#oRipple").onclick = () => cambiarOpcion("ripple"); $("#oIman").onclick = () => cambiarOpcion("iman"); $("#oEnlazada").onclick = () => cambiarOpcion("enlazada");
$("#oColocar").addEventListener("change", e => { OPC.colocar = e.target.value; guardado("opc", JSON.stringify(OPC)); });
$("#bDividir").onclick = () => { if (!dividir()) avisoEdicion("Coloca el cabezal en medio de una pieza (o selecciÃ³nala) para dividirla."); };
$("#bBorrar").onclick = () => borrarSel(false);
$("#bEnlace").onclick = alternarEnlace;
$("#bHueco").onclick = cerrarHuecoAntes;
$("#bMedio").onclick = agregarMedios; $("#bMedio2").onclick = agregarMedios;
$("#bEtiqueta").onclick = $("#bEtiqueta2").onclick = $("#bEtiqueta3").onclick = abrirDialogoEtiqueta; $("#bLogo3").onclick = logoEtiqueta; $("#bImagen").onclick = agregarMedios;
$("#bTexto").onclick = agregarTexto; $("#bTexto2").onclick = agregarTexto; $("#bTexto3").onclick = agregarTexto;
$("#bPistaV").onclick = () => anadirPista("V"); $("#bPistaA").onclick = () => anadirPista("A");
$("#bDeshacer").onclick = deshacerAccion; $("#bRehacer").onclick = rehacerAccion;
$("#bPlay").onclick = alternar; $("#bInicio").onclick = () => { pausar(); ir(0); }; $("#bFin").onclick = () => { pausar(); ir(durSalida()); };
$("#zoomTl").addEventListener("input", e => { TL.px = +e.target.value; tocar(); });
document.addEventListener("keyup", ev => { if (ev.key === " " && ev.target.tagName === "BUTTON") ev.preventDefault(); });
document.addEventListener("click", ev => { const b = ev.target.closest && ev.target.closest("button"); if (b) b.blur(); });
document.addEventListener("keydown", ev => {
  const t = ev.target.tagName, escribiendo = t === "INPUT" && !["range", "checkbox", "radio", "color"].includes(ev.target.type) || t === "SELECT" || t === "TEXTAREA";
  const ctrl = ev.ctrlKey || ev.metaKey, k = ev.key, kl = k.toLowerCase();
  if (ctrl && kl === "z") { ev.preventDefault(); ev.shiftKey ? rehacerAccion() : deshacerAccion(); return; }
  if (ctrl && kl === "y") { ev.preventDefault(); rehacerAccion(); return; }
  if (ctrl && kl === "s") { ev.preventDefault(); guardar(); return; }
  if (escribiendo || !E) return;
  if (ctrl && kl === "c") { copiar(); return; }
  if (ctrl && kl === "v") { ev.preventDefault(); pegar(); return; }
  if (ctrl && kl === "l") { ev.preventDefault(); alternarEnlace(); return; }
  if (ctrl) return;
  if (k === " ") { ev.preventDefault(); alternar(); }
  else if (k === "ArrowLeft") { pausar(); ir(T - (ev.shiftKey ? 1 : 1 / fps())); }
  else if (k === "ArrowRight") { pausar(); ir(T + (ev.shiftKey ? 1 : 1 / fps())); }
  else if (k === "Home") { pausar(); ir(0); } else if (k === "End") { pausar(); ir(durSalida()); }
  else if (k === "Delete" || k === "Backspace") { ev.preventDefault(); if(!borrarKfSeleccionado())borrarSel(ev.shiftKey); }
  else if (kl === "s") { if (!dividir()) avisoEdicion("Coloca el cabezal en medio de una pieza (o selecciÃ³nala) para dividirla."); }
  else if (kl === "b") poner(herramienta === "cuchilla" ? "sel" : "cuchilla");
  else if (kl === "v") poner("sel");
  else if (kl === "t") poner(herramienta === "trim" ? "sel" : "trim");
  else if (kl === "n") cambiarOpcion("iman");
  else if(k==="["||k==="]"){const p=piezaSel();if(p){const pts=Object.entries(p.kf||{}).flatMap(([prop,qs])=>qs.map(q=>({prop,q}))).sort((a,b)=>a.q.t-b.q.t),now=T-p.t,a=k==="["?[...pts].reverse().find(x=>x.q.t<now-.02):pts.find(x=>x.q.t>now+.02);if(a)ir(p.t+a.q.t);}}
});

// ------------------------------------------------------------------ zonas seguras (solo guÃ­a visual)
const PERFILES_ZS = {
  tiktok: {seg: [61, 153, 1019, 1452], botones: [855, 853, 1019, 1452], radio: 50},
  reels: {seg: [60, 270, 1020, 1536], botones: [900, 1000, 1020, 1536], radio: 40},
  shorts: {seg: [60, 288, 1020, 1440], botones: [900, 1040, 1020, 1440], radio: 40},
};
function sincronizarSeguimiento(){const s=ENCW().seguimiento_cara||(ENCW().seguimiento_cara={activo:false,suavidad:.7,zoom:1.2,perdida:"mantener",trayectoria:[]});$("#seguirCara").checked=!!s.activo;for(const [id,key] of [["#suavidadCara","suavidad"],["#zoomCara","zoom"]]){$(id).value=Math.round((s[key]??(key==="zoom"?1.2:.7))*100);$(id+"Val").textContent=$(id).value+"%";}$("#perdidaCara").value=s.perdida||"mantener";const c=$("#vistaSeguimiento"),x=c.getContext("2d");x.clearRect(0,0,c.width,c.height);x.fillStyle="#080b0c";x.fillRect(0,0,c.width,c.height);const pts=s.trayectoria||[];if(pts.length){x.beginPath();pts.forEach((p,i)=>i?x.lineTo(p.x*c.width,p.y*c.height):x.moveTo(p.x*c.width,p.y*c.height));x.strokeStyle="#4ade80";x.lineWidth=2;x.stroke();const q=puntoSeguimiento(s);if(q?.cara){x.strokeStyle="#fff";x.lineWidth=2;x.strokeRect(q.cara[0]*c.width,q.cara[1]*c.height,q.cara[2]*c.width,q.cara[3]*c.height);}const cam=capasE().find(q=>q.rol==="cam");if(cam){const z=limitar(+s.zoom||1.2,1,2.5),w=cam.fuente.w/z,h=cam.fuente.h/z;x.strokeStyle="#38bdf8";x.lineWidth=2;x.strokeRect((q.x-w/2)*c.width,(q.y-h/2)*c.height,w*c.width,h*c.height);}}}
$("#seguirCara").addEventListener("change",e=>{const s=ENCW().seguimiento_cara;if(e.target.checked&&!s.trayectoria.length){e.target.checked=false;$("#notaSeguimiento").textContent="Pulsa Analizar para calcular la trayectoria antes de activar el seguimiento.";return;}s.activo=e.target.checked;confirmar();});for(const [id,key] of [["#suavidadCara","suavidad"],["#zoomCara","zoom"]])$(id).addEventListener("input",e=>{ENCW().seguimiento_cara[key]=+e.target.value/100;$(id+"Val").textContent=e.target.value+"%";});for(const id of ["#suavidadCara","#zoomCara"])$(id).addEventListener("change",confirmar);$("#perdidaCara").addEventListener("change",e=>{ENCW().seguimiento_cara.perdida=e.target.value;confirmar();});
let seguimientoTimer=null;$("#analizarCara").onclick=async()=>{const b=$("#analizarCara"),n=$("#notaSeguimiento"),c=$("#cancelarCara"),bar=$("#barraSeguimiento"),fill=$("#progresoSeguimiento");b.disabled=true;c.hidden=false;bar.hidden=false;try{const cam=capasE().find(q=>q.rol==="cam");await post("seguimiento/analizar",{region:cam?cam.fuente:{x:0,y:0,w:1,h:1},suavidad:+$("#suavidadCara").value/100,perdida:$("#perdidaCara").value});seguimientoTimer=setInterval(async()=>{try{const d=await api("seguimiento/estado");fill.style.width=Math.round(100*(d.progreso||0))+"%";n.textContent=d.mensaje||"Analizandoâ€¦";if(d.estado==="listo"){clearInterval(seguimientoTimer);ENCW().seguimiento_cara.trayectoria=d.trayectoria||[];ENCW().seguimiento_cara.activo=true;confirmar();sincronizarSeguimiento();n.textContent="AnÃ¡lisis listo.";b.disabled=false;c.hidden=true;}else if(d.estado==="error")throw Error(d.mensaje);}catch(e){clearInterval(seguimientoTimer);n.textContent=e.message;b.disabled=false;c.hidden=true;}},500);}catch(e){n.textContent=e.message;b.disabled=false;c.hidden=true;}};$("#cancelarCara").onclick=async()=>{clearInterval(seguimientoTimer);try{await post("seguimiento/cancelar");}catch{}$("#cancelarCara").hidden=true;$("#analizarCara").disabled=false;$("#notaSeguimiento").textContent="AnÃ¡lisis cancelado.";};
const guardado = (k, v) => { try { if (v === undefined) return localStorage.getItem("mkclips_editor_" + k); localStorage.setItem("mkclips_editor_" + k, v); } catch (e) { return null; } };
function dibujarZonas() {
  const svg = $("#zonas"), on = $("#zsOn").checked; svg.toggleAttribute("hidden", !on); if (!on) return;
  const pf = PERFILES_ZS[$("#zsPerfil").value] || PERFILES_ZS.tiktok, op = $("#zsOpa").value / 100, [x0, y0, x1, y1] = pf.seg, [bx0, by0, bx1, by1] = pf.botones, r = pf.radio;
  svg.innerHTML = `<defs><linearGradient id="zs-grad"><stop stop-color="#4ade80"/><stop offset="1" stop-color="#38bdf8"/></linearGradient></defs><path class="fuera" fill-opacity="${op}" fill-rule="evenodd" d="M0 0H1080V1920H0Z M${x0} ${y0}H${x1}V${y1}H${x0}Z"/><rect class="borde-zs" x="${x0}" y="${y0}" width="${x1-x0}" height="${y1-y0}" rx="24"/><text class="etiqueta-zs" x="${x0+14}" y="${y0+32}">Zona segura</text><path fill="#38bdf8" fill-opacity="${Math.min(0.35,op*.35)}" d="M${bx0} ${by0+r}Q${bx0} ${by0} ${bx0+r} ${by0}H${bx1}V${by1}H${bx0}Z"/>`;
}
for (const [id, clave, tipo] of [["#zsOn", "zsOn", "check"], ["#zsPerfil", "zsPerfil", "v"], ["#zsOpa", "zsOpa", "v"]]) {
  const g = guardado(clave);
  if (g !== null && g !== undefined) { if (tipo === "check") $(id).checked = g === "1"; else $(id).value = g; }
  $(id).addEventListener("input", () => { guardado(clave, tipo === "check" ? ($(id).checked ? "1" : "0") : $(id).value); dibujarZonas(); });
}
dibujarZonas();

// ------------------------------------------------------------------ distribuciÃ³n: visores a un lado, divisores arrastrables
const principal = $("#principal"), app = $("#app");
if (guardado("swap") === "1") app.classList.add("swap");
if (guardado("wIzq")) principal.style.setProperty("--wIzq", guardado("wIzq") + "px");
if (guardado("hTl")) principal.style.setProperty("--hTl", guardado("hTl") + "px");
$("#bIntercambiar").onclick = () => { app.classList.toggle("swap"); guardado("swap", app.classList.contains("swap") ? "1" : "0"); ajustarVisores(); dibujarTimeline(); };
function divisor(id, alAmover) {
  const el = $(id);
  el.addEventListener("pointerdown", ev => {
    ev.preventDefault(); el.setPointerCapture(ev.pointerId); el.classList.add("arr");
    const mover = e => { alAmover(e, principal.getBoundingClientRect()); ajustarVisores(); dibujarTimeline(); };
    const fin = () => { el.classList.remove("arr"); el.removeEventListener("pointermove", mover); el.removeEventListener("pointerup", fin); el.removeEventListener("pointercancel", fin); };
    el.addEventListener("pointermove", mover); el.addEventListener("pointerup", fin); el.addEventListener("pointercancel", fin);
  });
}
divisor("#splitV", (e, r) => {
  const w = limitar(app.classList.contains("swap") ? r.right - e.clientX : e.clientX - r.left, 380, Math.max(400, r.width - 420));
  principal.style.setProperty("--wIzq", w + "px"); guardado("wIzq", Math.round(w));
});
divisor("#splitH", (e, r) => {
  const h = limitar(r.bottom - e.clientY, 170, Math.max(200, r.height - 180));
  principal.style.setProperty("--hTl", h + "px"); guardado("hTl", Math.round(h));
});
if (window.ResizeObserver) {
  const ro = new ResizeObserver(() => { if (E) { ajustarVisores(); dibujarTimeline(); } });
  ro.observe($("#zonaOrigen")); ro.observe($("#zonaSalida")); ro.observe($("#scroll"));
}

function limpiarSeleccion() {
  for (const id of [...SEL]) if (!piezaPorId(id)) SEL.delete(id);
  if (sel && sel.tipo === "pieza" && !piezaPorId(sel.id)) { const r = [...SEL][0]; sel = r ? {tipo: "pieza", id: r} : null; }
}
function refrescarTodo() {
  limpiarSeleccion(); actualizarAlcance();
  sincronizarIA(); ajustarVisores(); sincronizarModo(); sincronizarSubs(); construirEtiquetas(); sincronizarPieza(); sincronizarAlcance(); resumenExport();
  actualizarReloj(); sincronizarOpciones(); sincronizarSeguimiento(); actualizarBotonesHistorial(); tocar();
}

// ------------------------------------------------------------------ arranque

async function comprobarArchivos() {      // avisa si algÃºn archivo de la actualizaciÃ³n no se copiÃ³ (el panel sigue con cÃ³digo viejo)
  let msg = "";
  try {
    const r = await fetch("/editor/api/version"), d = await r.json(), s = d.sellos;
    if (!s) msg = "El panel abierto usa archivos anteriores a esta versiÃ³n (no informa de su versiÃ³n).";
    else { const mal = Object.entries(s).filter(([k, v]) => SELLOS_ESPERADOS[k] && v !== SELLOS_ESPERADOS[k]).map(([k]) => k); if (mal.length) msg = "Estos archivos no estÃ¡n actualizados: " + mal.map(k => ({rutas: "editor_rutas.py", piezas: "editor_piezas.py", render: "editor_render.py", render_piezas: "editor_render_piezas.py"})[k]).join(", ") + "."; }
  } catch (e) { return; }
  if (!msg) return;
  const d = document.createElement("div");
  d.style.cssText = "position:fixed;left:0;right:0;top:0;z-index:99;background:#7a1f1f;color:#fff;padding:8px 12px;font-size:13px";
  d.innerHTML = "<b>ActualizaciÃ³n incompleta.</b> " + msg + " Copia de nuevo esos archivos, cierra el panel con reiniciar_panel.bat y abre Editar otra vez. El render puede no coincidir con lo que ves. <button style='margin-left:8px' onclick='this.parentNode.remove()'>Cerrar</button>";
  document.body.appendChild(d);
}
async function arrancar() {
  comprobarArchivos();
  let d;
  try { d = await api("estado"); }
  catch (e) { $("#msgCarga").textContent = e.message; document.querySelector("#cargando .giro").style.display = "none"; return; }
  E = d.edicion; INFO = d.info;
  if (!Array.isArray(E.piezas)) { $("#msgCarga").textContent = "El panel abierto es de una versiÃ³n anterior (sin la lÃ­nea de tiempo nueva). CiÃ©rralo por completo y vuelve a pulsar Â«EditarÂ» en MKClips."; document.querySelector("#cargando .giro").style.display = "none"; return; }
  if (!E.pistas) E.pistas = {video: 1, audio: 1, ocultas: [], silenciadas: [], bloqueadas: []};
  for (const k of ["ocultas", "silenciadas", "bloqueadas"]) if (!Array.isArray(E.pistas[k])) E.pistas[k] = [];
  E.piezas = PZ.normalizarIniciales(E.piezas);
  if (!E.encuadre.capas) E.encuadre.capas = [];
  if (E.salida.nombre === undefined) E.salida.nombre = "";
  if (!E.encuadre.linea) E.encuadre.linea = {ancho: 0, color: "#FFFFFF"};
  try { const o = JSON.parse(guardado("opc") || "{}"); for (const k of ["ripple", "iman", "enlazada"]) if (typeof o[k] === "boolean") OPC[k] = o[k]; if (["superponer", "sobrescribir", "insertar", "al_final"].includes(o.colocar)) OPC.colocar = o.colocar; } catch (e) { /* sin preferencias */ }
  construirGaleria();
  if (!E.mejora_ia) E.mejora_ia = {activa: false, cam: true, juego: false, modelo: "rapido"};
  if (!d.version || d.version < 7) avisarPanelViejo(); FUENTES = d.fuentes; CARA = d.cara; IA = d.ia || {disponible: false, mensaje: ""}; SUB_STREAM = d.subtitulos_stream;
  document.title = "Editor Â· " + d.titulo; $("#titulo").textContent = d.titulo;
  $("#infoOrigen").textContent = `${E.origen.ancho}Ã—${E.origen.alto} Â· ${fmt(E.origen.duracion)}`;
  $("#bStream").hidden = !SUB_STREAM;
  ultimoSnap = foto(); actualizarBotonesHistorial();
  const esperar = async () => {
    for (;;) {
      const v = await api("vista");
      if (v.estado === "listo") return;
      if (v.estado === "error") throw new Error(v.mensaje || "No se pudo preparar la vista previa.");
      $("#msgCarga").textContent = v.mensaje || "Preparando la vista previaâ€¦";
      await new Promise(r => setTimeout(r, 700));
    }
  };
  try { await esperar(); }
  catch (e) { $("#msgCarga").textContent = e.message; document.querySelector("#cargando .giro").style.display = "none"; return; }
  $("#msgCarga").textContent = "Cargando el primer fotograma de la vista previa…";
  try { await cargarPrimerFotograma(V, URL_CLIP); }
  catch (e) { $("#msgCarga").textContent = e.message; document.querySelector("#cargando .giro").style.display = "none"; avisoReproduccion(e.message); return; }
  FUENTE[URL_CLIP] = {estado: "listo", els: [{el: V, clave: "", ultPlay: 0}], img: null, mensaje: ""};
  $("#cargando").hidden = true;
  requestAnimationFrame(bucle);
  try { refrescarTodo(); ir(0); } catch (e) { console.error(e); }
  api("onda").then(o => { PICOS = o.picos || []; PICOS_POR_S = o.por_segundo || 20; tocar(); });
  if (!E.subtitulos.lineas.length) $("#notaSub").textContent = "AÃºn no hay subtÃ­tulos: pulsa Â«Generar subtÃ­tulos del clipÂ».";
}
V.addEventListener("seeked", () => { dibujar(); });
V.addEventListener("error", () => avisoReproduccion("Error del vÃ­deo de vista previa: " + ((V.error && V.error.message) || "formato no compatible")));
arrancar();

