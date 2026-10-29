# -*- coding: utf-8 -*-
"""Pagina /camara del panel: marcar donde esta la camara del streamer y ver sus picos de movimiento."""
from __future__ import annotations

import subprocess
import threading
import traceback
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

import camara_modelo
import camara_movimiento
from configuracion_central import directorio_scripts, leer_configuracion

bp = Blueprint("camara", __name__, url_prefix="/camara")
EXTENSIONES = {".mkv", ".mp4", ".mov", ".webm", ".ts", ".flv"}
_estado = {"activo": False, "fraccion": 0.0, "texto": "", "error": "", "listo": False, "ruta": "", "cancelar": False}
_candado = threading.Lock()


def _resultados():
    return Path(leer_configuracion().get("CARPETA_RESULTADOS") or directorio_scripts() / "resultados")


def _error(mensaje, codigo=400):
    return jsonify(ok=False, error=mensaje), codigo


def _ruta_pedida(datos=None):
    ruta = str((datos or {}).get("ruta") or request.args.get("ruta") or "").strip()
    if not ruta:
        try:
            with open(directorio_scripts() / "ultimo_video.txt", encoding="utf-8") as f:
                ruta = f.readline().strip()
        except OSError:
            ruta = ""
    return ruta


def _video(ruta):
    p = Path(ruta) if ruta else None
    if p is None or not p.is_file() or p.suffix.lower() not in EXTENSIONES:
        return None
    return p


@bp.route("/")
def pagina():
    return Response(PAGINA, mimetype="text/html")


@bp.route("/api/info")
def info():
    ruta = _ruta_pedida()
    video = _video(ruta)
    if video is None:
        return _error("Indica la ruta de un video existente (MKV, MP4...).")
    try:
        datos = camara_movimiento.info_video(video)
    except RuntimeError as exc:
        return _error(str(exc))
    return jsonify(ok=True, ruta=str(video), zonas=camara_modelo.zonas_de(_resultados(), video), **datos)


@bp.route("/api/fotograma")
def fotograma():
    video = _video(_ruta_pedida())
    if video is None:
        return _error("Video no encontrado.", 404)
    try:
        t = max(0.0, float(request.args.get("t", 0)))
        ancho = max(120, min(1920, int(float(request.args.get("w", 960)))))
    except ValueError:
        return _error("Parametros invalidos.")
    try:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
             "-vf", f"scale={ancho}:-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"],
            capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return _error("No se pudo extraer el fotograma (ffmpeg).", 500)
    if not p.stdout:
        return _error("No hay fotograma en ese instante.", 404)
    return Response(p.stdout, mimetype="image/jpeg", headers={"Cache-Control": "private, max-age=120"})


@bp.route("/api/zonas", methods=["POST"])
def guardar_zonas():
    datos = request.get_json(silent=True) or {}
    video = _video(_ruta_pedida(datos))
    if video is None:
        return _error("Video no encontrado.")
    try:
        duracion = camara_movimiento.info_video(video)["duracion"]
        zonas = camara_modelo.guardar_zonas(_resultados(), video, datos.get("zonas"), duracion)
    except (RuntimeError, OSError) as exc:
        return _error(str(exc))
    return jsonify(ok=True, zonas=zonas)


@bp.route("/api/analizar", methods=["POST"])
def analizar():
    datos = request.get_json(silent=True) or {}
    video = _video(_ruta_pedida(datos))
    if video is None:
        return _error("Video no encontrado.")
    zonas = camara_modelo.zonas_de(_resultados(), video)
    if not any(z["rect"] for z in zonas):
        return _error("Marca primero la camara (al menos una zona con recuadro).")
    with _candado:
        if _estado["activo"]:
            return _error("Ya hay un analisis en curso.", 409)
        _estado.update(activo=True, fraccion=0.0, texto="Preparando...", error="", listo=False, ruta=str(video), cancelar=False)

    def trabajo():
        try:
            resultado = camara_movimiento.analizar(
                video, zonas,
                progreso=lambda f, texto: _estado.update(fraccion=f, texto=texto),
                cancelar=lambda: _estado["cancelar"])
            camara_movimiento.guardar(_resultados(), resultado)
            _estado.update(listo=True, fraccion=1.0, texto="Listo.")
        except camara_movimiento.Cancelado:
            _estado.update(error="Analisis cancelado.")
        except Exception as exc:  # noqa: BLE001 - se muestra en la pagina, no tumba el panel
            traceback.print_exc()
            _estado.update(error=str(exc) or exc.__class__.__name__)
        finally:
            _estado["activo"] = False

    threading.Thread(target=trabajo, daemon=True).start()
    return jsonify(ok=True)


@bp.route("/api/analisis/estado")
def estado_analisis():
    return jsonify(ok=True, **{k: _estado[k] for k in ("activo", "fraccion", "texto", "error", "listo", "ruta")})


@bp.route("/api/analisis/cancelar", methods=["POST"])
def cancelar():
    _estado["cancelar"] = True
    return jsonify(ok=True)


@bp.route("/api/eventos")
def eventos():
    import json
    ruta = _ruta_pedida()
    try:
        with open(_resultados() / "eventos_camara.json", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return jsonify(ok=True, datos=None)
    if ruta and camara_modelo.clave_video(datos.get("video", "")) != camara_modelo.clave_video(ruta):
        return jsonify(ok=True, datos=None)       # son de otro video
    return jsonify(ok=True, datos=datos)


def registrar(app):
    """Monta la pagina en la app Flask del panel. Nunca rompe el panel si algo falla."""
    try:
        app.register_blueprint(bp)
        return True
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return False


PAGINA = r'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Marcar cámara</title>
<style>
:root{--fondo:#1e1e1e;--caja:#252525;--borde:#555;--texto:#ddd;--suave:#999;--acento:#4aa3ff;--ok:#5cc97a;--aviso:#e0a43a}
@media (prefers-color-scheme:light){:root{--fondo:#f4f4f4;--caja:#fff;--borde:#bbb;--texto:#222;--suave:#666;--acento:#0b6bcb;--ok:#1c8a3d;--aviso:#a86a00}}
body{font:14px "Segoe UI",system-ui,sans-serif;background:var(--fondo);color:var(--texto);margin:0;padding:12px 16px}
a{color:var(--acento)}button,input{background:var(--caja);color:var(--texto);border:1px solid var(--borde);padding:6px 10px;border-radius:4px;font:inherit}
button{cursor:pointer}button.p{background:var(--acento);color:#fff;border-color:var(--acento)}button:disabled{opacity:.5;cursor:default}
.caja{background:var(--caja);border:1px solid var(--borde);border-radius:6px;padding:10px;margin:10px 0}
.fila{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.suave{color:var(--suave)}h1{font-size:18px;margin:0 0 8px}h2{font-size:15px;margin:0 0 6px}
#ruta{flex:1;min-width:260px}#marco{position:relative;display:inline-block;max-width:100%;line-height:0;background:#000}
#foto{max-width:100%;max-height:62vh;display:block}#capa{position:absolute;left:0;top:0;cursor:crosshair;touch-action:none}
#tiempo{width:100%}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid var(--borde);padding:4px 6px;text-align:left;vertical-align:middle}
.barra{height:8px;background:var(--borde);border-radius:4px;overflow:hidden;margin-top:6px}.barra div{height:100%;width:0;background:var(--acento)}
#linea{width:100%;height:70px;display:block;cursor:pointer}.etq{font-size:12px;padding:1px 6px;border-radius:9px;border:1px solid var(--borde)}
.err{color:#e5534b}img.mini{width:150px;height:auto;display:block;border-radius:3px}
</style></head><body>
<h1>Marcar la cámara del stream <a href="/" style="font-size:13px;font-weight:400">← volver al panel</a></h1>
<div class="caja"><div class="fila"><input id="ruta" placeholder="C:\Streams\mi_stream.mkv"><button id="bElegir">Elegir archivo…</button><button class="p" id="bCargar">Cargar</button></div><div id="aviso" class="suave" style="margin-top:6px"></div></div>
<div id="editor" style="display:none">
<div class="caja">
<h2>1. Dibuja un recuadro sobre la cámara</h2>
<div class="suave" style="margin-bottom:6px">Arrastra sobre la imagen. Si la cámara cambia de sitio más adelante, mueve el control de tiempo hasta ese momento, dibuja el nuevo recuadro y pulsa «Aplicar desde este momento».</div>
<div id="marco"><img id="foto" alt="fotograma"><canvas id="capa"></canvas></div>
<div class="fila" style="margin-top:8px"><input type="range" id="tiempo" min="0" max="100" step="1" value="0"></div>
<div class="fila" style="margin-top:6px"><button data-d="-60">−1 min</button><button data-d="-10">−10 s</button><button data-d="10">+10 s</button><button data-d="60">+1 min</button><b id="hora">0:00</b><span id="vigente" class="suave"></span></div>
<div class="fila" style="margin-top:8px"><button class="p" id="bAplicar">Aplicar desde este momento</button><button id="bSin">Aquí no hay cámara</button></div>
</div>
<div class="caja"><h2>Zonas guardadas</h2><div id="zonas" class="suave">Aún no hay ninguna.</div></div>
<div class="caja"><h2>2. Buscar movimiento en la cámara</h2>
<div class="suave" style="margin-bottom:6px">Mide cuánto se mueve la imagen solo dentro del recuadro (bailes, caídas, gestos), aunque no haya voz. No usa IA. Tarda aproximadamente lo que tardaría en decodificarse el video.</div>
<div class="fila"><button class="p" id="bAnalizar">Analizar movimiento</button><button id="bCancelar" style="display:none">Cancelar</button><span id="texto" class="suave"></span></div>
<div class="barra" id="barra" style="display:none"><div id="prog"></div></div></div>
<div class="caja" id="resultados" style="display:none"><h2>Picos encontrados</h2><canvas id="linea" height="70"></canvas>
<div class="suave" style="margin:6px 0">Haz clic en la línea de tiempo o en «Ver» para ver el fotograma. «Posible cambio de escena» marca los destellos de pantalla completa, que suelen ser OBS y no la persona.</div>
<table><thead><tr><th>Cuándo</th><th>Tipo</th><th>Fuerza</th><th>Fotograma</th><th></th></tr></thead><tbody id="filas"></tbody></table></div>
</div>
<script>
const $=id=>document.getElementById(id);
const S={ruta:'',dur:0,zonas:[],t:0,rect:null,datos:null,arrastre:null};
const fmt=t=>{t=Math.max(0,Math.round(t));const h=Math.floor(t/3600),m=Math.floor(t%3600/60),s=t%60;return(h?h+':'+String(m).padStart(2,'0'):m)+':'+String(s).padStart(2,'0')};
async function api(u,o){const r=await fetch(u,o);let d={};try{d=await r.json()}catch(e){}if(!r.ok||d.ok===false)throw Error(d.error||('Error '+r.status));return d}
const post=(u,b)=>api(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
const q=o=>new URLSearchParams(o).toString();
function aviso(t,mal){$('aviso').textContent=t||'';$('aviso').className=mal?'err':'suave'}
function zonaEn(t){let v=null;for(const z of S.zonas){if(z.desde<=t+1e-6)v=z;else break}return v}
async function cargar(){
  const ruta=$('ruta').value.trim();aviso('Leyendo el video…');
  try{const d=await api('/camara/api/info?'+q({ruta}));
    S.ruta=d.ruta;S.dur=d.duracion;S.zonas=d.zonas;$('ruta').value=d.ruta;$('tiempo').max=Math.floor(d.duracion);
    $('editor').style.display='block';aviso(d.ancho+'×'+d.alto+' · '+fmt(d.duracion));irA(0);pintarZonas();await cargarEventos()}
  catch(e){aviso(e.message,true);$('editor').style.display='none'}
}
let temporizador=null;
function irA(t){S.t=Math.max(0,Math.min(S.dur,t));$('tiempo').value=Math.floor(S.t);$('hora').textContent=fmt(S.t);
  const z=zonaEn(S.t);S.rect=z?z.rect:null;$('vigente').textContent=z?(z.rect?'Recuadro vigente desde '+fmt(z.desde):'Sin cámara desde '+fmt(z.desde)):'Sin zonas todavía';
  clearTimeout(temporizador);temporizador=setTimeout(()=>{$('foto').src='/camara/api/fotograma?'+q({ruta:S.ruta,t:S.t.toFixed(1),w:960})},120);dibujar()}
$('foto').onload=()=>{const c=$('capa');c.width=$('foto').clientWidth;c.height=$('foto').clientHeight;dibujar()};
function dibujar(){const c=$('capa'),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);const r=S.arrastre?S.arrastre.rect:S.rect;if(!r)return;
  x.fillStyle='rgba(74,163,255,.18)';x.strokeStyle='#4aa3ff';x.lineWidth=2;x.fillRect(r.x*c.width,r.y*c.height,r.w*c.width,r.h*c.height);x.strokeRect(r.x*c.width,r.y*c.height,r.w*c.width,r.h*c.height)}
const punto=e=>{const b=$('capa').getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)),y:Math.max(0,Math.min(1,(e.clientY-b.top)/b.height))}};
$('capa').addEventListener('pointerdown',e=>{$('capa').setPointerCapture(e.pointerId);const p=punto(e);S.arrastre={a:p,rect:{x:p.x,y:p.y,w:0,h:0}}});
$('capa').addEventListener('pointermove',e=>{if(!S.arrastre)return;const p=punto(e),a=S.arrastre.a;S.arrastre.rect={x:Math.min(a.x,p.x),y:Math.min(a.y,p.y),w:Math.abs(p.x-a.x),h:Math.abs(p.y-a.y)};dibujar()});
$('capa').addEventListener('pointerup',()=>{if(!S.arrastre)return;const r=S.arrastre.rect;S.arrastre=null;if(r.w>0.02&&r.h>0.02)S.rect=r;dibujar()});
async function guardarZonas(zonas){try{const d=await post('/camara/api/zonas',{ruta:S.ruta,zonas});S.zonas=d.zonas;pintarZonas();irA(S.t)}catch(e){aviso(e.message,true)}}
$('bAplicar').onclick=()=>{if(!S.rect)return aviso('Dibuja primero un recuadro sobre la cámara.',true);aviso('');
  const desde=S.zonas.length?Math.round(S.t*10)/10:0;guardarZonas(S.zonas.filter(z=>Math.abs(z.desde-desde)>0.05).concat([{desde,rect:S.rect}]))};
$('bSin').onclick=()=>{aviso('');if(!S.zonas.length)return aviso('Marca primero dónde está la cámara.',true);
  const desde=Math.round(S.t*10)/10;guardarZonas(S.zonas.filter(z=>Math.abs(z.desde-desde)>0.05).concat([{desde,rect:null}]))};
function pintarZonas(){const c=$('zonas');if(!S.zonas.length){c.textContent='Aún no hay ninguna.';return}
  c.innerHTML='<table>'+S.zonas.map((z,i)=>'<tr><td>Desde <b>'+fmt(z.desde)+'</b></td><td>'+(z.rect?'Cámara en x '+Math.round(z.rect.x*100)+'%, y '+Math.round(z.rect.y*100)+'%, '+Math.round(z.rect.w*100)+'%×'+Math.round(z.rect.h*100)+'%':'Sin cámara')+'</td><td><button data-ir="'+z.desde+'">Ver</button> <button data-quitar="'+i+'">Quitar</button></td></tr>').join('')+'</table>'}
$('zonas').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.ir!==undefined)irA(parseFloat(b.dataset.ir)+0.1);
  if(b.dataset.quitar!==undefined){const i=+b.dataset.quitar;guardarZonas(S.zonas.filter((_,k)=>k!==i))}});
$('tiempo').oninput=e=>irA(+e.target.value);
document.querySelectorAll('[data-d]').forEach(b=>b.onclick=()=>irA(S.t+(+b.dataset.d)));
$('bCargar').onclick=cargar;$('ruta').onkeydown=e=>{if(e.key==='Enter')cargar()};
$('bElegir').onclick=async()=>{try{const d=await post('/api/seleccionar/archivo',{inicial:$('ruta').value});if(d.ruta){$('ruta').value=d.ruta;cargar()}}catch(e){aviso('No se pudo abrir el selector: escribe la ruta a mano. ('+e.message+')',true)}};
// --- analisis
let sondeo=null;
async function sondear(){try{const d=await api('/camara/api/analisis/estado');$('texto').textContent=d.error||d.texto;$('texto').className=d.error?'err':'suave';
  $('barra').style.display=d.activo||d.listo?'block':'none';$('prog').style.width=Math.round(d.fraccion*100)+'%';$('bAnalizar').disabled=d.activo;$('bCancelar').style.display=d.activo?'':'none';
  if(!d.activo){clearInterval(sondeo);sondeo=null;if(d.listo)cargarEventos()}}catch(e){}}
$('bAnalizar').onclick=async()=>{try{await post('/camara/api/analizar',{ruta:S.ruta});$('barra').style.display='block';sondeo=sondeo||setInterval(sondear,1000);sondear()}catch(e){$('texto').textContent=e.message;$('texto').className='err'}};
$('bCancelar').onclick=()=>post('/camara/api/analisis/cancelar',{});
async function cargarEventos(){try{const d=await api('/camara/api/eventos?'+q({ruta:S.ruta}));S.datos=d.datos;pintarEventos()}catch(e){}}
const TIPOS={movimiento_sostenido:'Movimiento sostenido (¿baile?)',pico_brusco:'Pico brusco (¿caída o susto?)'};
function pintarEventos(){const d=S.datos;$('resultados').style.display=d?'block':'none';if(!d)return;
  $('filas').innerHTML=d.eventos.length?d.eventos.map((e,i)=>'<tr><td>'+fmt(e.movimiento_inicio)+' – '+fmt(e.movimiento_fin)+'</td><td>'+(TIPOS[e.tipo]||e.tipo)+(e.sospechoso_cambio_de_escena?' <span class="etq">Posible cambio de escena</span>':'')+'</td><td>×'+e.fuerza+'</td><td><img class="mini" loading="lazy" src="/camara/api/fotograma?'+q({ruta:S.ruta,t:e.pico_t,w:300})+'"></td><td><button data-v="'+e.pico_t+'">Ver</button></td></tr>').join(''):'<tr><td colspan="5">No se detectó movimiento destacado en el recuadro.</td></tr>';
  linea()}
$('filas').addEventListener('click',e=>{const b=e.target.closest('[data-v]');if(b){irA(+b.dataset.v);scrollTo({top:0,behavior:'smooth'})}});
function linea(){const d=S.datos,c=$('linea');if(!d)return;c.width=c.clientWidth||800;const x=c.getContext('2d'),W=c.width,H=c.height,sx=W/d.duracion;x.clearRect(0,0,W,H);
  x.fillStyle='rgba(224,164,58,.28)';d.eventos.forEach(e=>x.fillRect(e.movimiento_inicio*sx,0,Math.max(2,(e.movimiento_fin-e.movimiento_inicio)*sx),H));
  x.fillStyle='#4aa3ff';d.serie.forEach(([t,v])=>{const h=Math.min(1,v)*H;x.fillRect(t*sx,H-h,Math.max(1,sx),h)});x.strokeStyle='#e0a43a';x.beginPath();const y=H-Math.min(1,d.umbral)*H;x.moveTo(0,y);x.lineTo(W,y);x.stroke()}
$('linea').onclick=e=>{const b=e.target.getBoundingClientRect();if(S.datos){irA((e.clientX-b.left)/b.width*S.datos.duracion);scrollTo({top:0,behavior:'smooth'})}};
addEventListener('resize',linea);
fetch('/camara/api/info').then(r=>r.json()).then(d=>{if(d.ok){$('ruta').value=d.ruta;cargar()}}).catch(()=>{});
sondear();
</script></body></html>'''
