"""Panel local de MKClips. Reutiliza el pipeline existente, no lo duplica."""
from __future__ import annotations
import json, os, subprocess, threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, jsonify, request
import control_grabacion, descargar_video, procesar_multiples
from cache_mkclips import exigir_identidad_artefacto, guardar_identidad_artefacto
from preferencias_mkclips import guardar_feedback
from configuracion_central import directorio_scripts, guardar_configuracion, leer_configuracion, limite_cpu_recomendado, normalizar_configuracion
from duracion_clips import validar_limites_duracion

app=Flask(__name__)
try:
    import editor_rutas;editor_rutas.registrar(app)
except Exception as _e:print("Editor no disponible:",_e)
try:
    import camara_rutas;camara_rutas.registrar(app)
except Exception as _e:print("Marcar camara no disponible:",_e)
try:
    import ui_rutas;ui_rutas.registrar(app)
except Exception as _e:print("Interfaz web no disponible:",_e)
ARCHIVOS=("clips_sugeridos.json","candidatos_todos.json","candidatos_cortos.json","scores_clips.json","resumen_plan.json","metricas_identificacion.json","juego_contexto.json","arcos_narrativos.json","metricas_proceso.json","eventos_visuales.json","metricas_visual.json","contexto_stream.json","validacion_segmentos.json")
estado={"grabando":False,"deteniendo":False,"modo":None,"snapshot":None,"solo_grabar":False,"borrar_original":False,"procesando":False,"descargando":False,"log":[],"ollama_api_key":None}
def nota(x): estado["log"].append(str(x));del estado["log"][:-200];print(x)
def resultados():
    return Path(leer_configuracion().get("CARPETA_RESULTADOS") or directorio_scripts()/"resultados")
def leer(r,d):
    try:return json.loads(r.read_text(encoding="utf-8"))
    except (OSError,ValueError):return d
def selector_windows(tipo, inicial="", multiple=False):
    """Abre el selector nativo local; no copia, mueve ni crea contenido."""
    import tkinter as tk
    from tkinter import filedialog
    raiz=tk.Tk();raiz.withdraw();raiz.attributes("-topmost",True)
    try:
        if tipo=="archivo":
            opciones=dict(initialdir=inicial or None,title="Selecciona uno o varios streams MKV o MP4",filetypes=[("Videos MKV/MP4","*.mkv *.mp4"),("Todos","*.*")])
            ruta=filedialog.askopenfilenames(**opciones) if multiple else filedialog.askopenfilename(**opciones)
        else:
            ruta=filedialog.askdirectory(initialdir=inicial or None, title="Selecciona carpeta")
        return ruta or ""
    finally:raiz.destroy()
def gpu():
    nombre=""
    try:
        p=subprocess.run(["nvidia-smi","--query-gpu=name","--format=csv,noheader"],capture_output=True,text=True,timeout=4);nombre=p.stdout.splitlines()[0].strip() if not p.returncode and p.stdout else ""
    except (OSError,subprocess.SubprocessError):pass
    try:
        import transcribir;ok=bool(transcribir._gpu_disponible())
    except Exception:ok=False
    return {"compatible":ok,"modelo":nombre or ("NVIDIA detectada" if ok else "No detectada")}
def publica():
    v=leer_configuracion();v.pop("OBS_WS_CONTRASENA",None);v["OBS_WS_CONTRASENA_CONFIGURADA"]=bool(os.environ.get("OBS_WS_CONTRASENA"));v["OLLAMA_API_KEY_CONFIGURADA"]=bool(estado["ollama_api_key"] or os.environ.get("OLLAMA_API_KEY"));v["cpu_logicos"]=os.cpu_count() or 1;v["cpu_limite_recomendado"]=limite_cpu_recomendado();v["gpu"]=gpu();return v
@app.route("/")
def index():return PAGINA
@app.route("/estado")
def est():return jsonify(**{x:estado[x] for x in ("grabando","deteniendo","modo","procesando","descargando")},log=estado["log"][-50:],progreso=procesar_multiples.leer_estado_progreso() or {})
@app.route("/api/configuracion",methods=["GET","POST"])
def config():
    if request.method=="GET":return jsonify(publica())
    d=request.get_json(silent=True) or {};v=leer_configuracion()
    for k in v:
        if k in d and k!="OBS_WS_CONTRASENA":v[k]=d[k]
    if "OBS_WS_CONTRASENA" in d:
        if d["OBS_WS_CONTRASENA"]:os.environ["OBS_WS_CONTRASENA"]=str(d["OBS_WS_CONTRASENA"])
        else:os.environ.pop("OBS_WS_CONTRASENA",None)
    try:guardar_configuracion(normalizar_configuracion(v))
    except (ValueError,OSError) as e:return jsonify(ok=False,error=str(e)),400
    if d.get("OLLAMA_API_KEY"):
        os.environ["OLLAMA_API_KEY"]=str(d["OLLAMA_API_KEY"])
        estado["ollama_api_key"]=""
    return jsonify(ok=True,configuracion=publica())
@app.route("/api/seleccionar/<tipo>",methods=["POST"])
def seleccionar(tipo):
    if tipo not in {"archivo","carpeta"}:return jsonify(ok=False,error="Tipo de selector invalido."),400
    d=request.get_json(silent=True) or {};ruta=selector_windows(tipo,str(d.get("inicial") or ""),bool(d.get("multiple")))
    if not ruta:return jsonify(ok=True,cancelado=True,ruta="",rutas=[])
    if isinstance(ruta,(tuple,list)):
        rutas=[str(Path(x)) for x in ruta if Path(x).is_file() and Path(x).suffix.lower() in {".mkv",".mp4"}]
        if len(rutas)!=len(ruta):return jsonify(ok=False,error="Todos los streams deben ser MKV o MP4 existentes."),400
        return jsonify(ok=True,cancelado=False,ruta=rutas[0] if rutas else "",rutas=rutas)
    p=Path(ruta)
    if tipo=="archivo":
        if not p.is_file() or p.suffix.lower() not in {".mkv",".mp4"}:return jsonify(ok=False,error="Selecciona un archivo MKV o MP4 existente."),400
    elif not p.is_dir():return jsonify(ok=False,error="Selecciona una carpeta existente."),400
    return jsonify(ok=True,cancelado=False,ruta=str(p),rutas=[str(p)])
@app.route("/api/probar/obs",methods=["POST"])
def test_obs():
    try:
        c=control_grabacion._obtener_cliente_obs();c.get_record_status()
        if hasattr(c,"disconnect"):c.disconnect()
        return jsonify(ok=True,mensaje="Conexion con OBS WebSocket correcta.")
    except Exception as e:return jsonify(ok=False,error=str(e)),400
@app.route("/api/probar/ollama",methods=["POST"])
def test_ollama():
    d=request.get_json(silent=True) or {};v=leer_configuracion()
    try:
        import ollama
        if v["OLLAMA_MODO"]=="cloud":
            key=d.get("OLLAMA_API_KEY") or estado["ollama_api_key"] or os.environ.get("OLLAMA_API_KEY")
            if not key:raise RuntimeError("Ollama Cloud requiere OLLAMA_API_KEY del usuario.")
            c=ollama.Client(host="https://ollama.com",headers={"Authorization":"Bearer "+key})
        else:c=ollama.Client(host=v["OLLAMA_HOST"])
        c.list();return jsonify(ok=True,mensaje="Conexion con Ollama correcta.")
    except Exception as e:return jsonify(ok=False,error=str(e)),400
@app.route("/api/procesar",methods=["POST"])
def procesar():
    d=request.get_json(silent=True) or {};r=Path(str(d.get("ruta") or ""))
    if estado["procesando"] or estado["grabando"]:return jsonify(ok=False,error="Ya hay una operacion activa."),409
    if not r.is_file() or r.suffix.lower() not in {".mkv",".mp4"}:return jsonify(ok=False,error="Selecciona un MKV o MP4 existente."),400
    estado["procesando"]=True
    def t():
        try:nota("Proceso terminado." if procesar_multiples.procesar_un_video(str(r.resolve()),True,nota,str(d.get("contexto") or "")) else "Proceso terminado con error.")
        except Exception as e:nota("ERROR al procesar: "+str(e))
        finally:estado["procesando"]=False
    threading.Thread(target=t,daemon=True).start();return jsonify(ok=True)
@app.route("/api/descargar",methods=["POST"])
def descarga():
    d=request.get_json(silent=True) or {};u=str(d.get("url") or "").strip();p=urlparse(u);dest=str(d.get("destino") or leer_configuracion().get("CARPETA_STREAMS") or "")
    if estado["descargando"]:return jsonify(ok=False,error="Ya hay una descarga activa."),409
    if p.scheme not in {"http","https"} or not p.netloc:return jsonify(ok=False,error="Indica una URL http(s) valida."),400
    if not dest:return jsonify(ok=False,error="Indica una carpeta destino."),400
    estado["descargando"]=True
    def t():
        try:nota("Descarga lista: "+descargar_video.descargar_video(u,dest,nota))
        except Exception as e:nota("ERROR de descarga: "+str(e))
        finally:estado["descargando"]=False
    threading.Thread(target=t,daemon=True).start();return jsonify(ok=True)
@app.route("/api/historial")
def historial():
    r=resultados();ej=leer(r/"metricas_proceso.json",{}).get("ejecuciones",[]);g={}
    for x in ej:
        if not isinstance(x,dict) or not x.get("archivo"):continue
        z=g.setdefault(x["archivo"],{"stream":x["archivo"],"timestamp":0,"duracion_proceso_segundos":0,"estado":"desconocido"});z["timestamp"]=max(z["timestamp"],x.get("timestamp",0) or 0);z["duracion_proceso_segundos"]+=float(x.get("duracion_segundos",0) or 0);z["estado"]="error" if x.get("resultado")=="error" else ("ok" if x.get("resultado") in {"ok","cache_hit"} and z["estado"]!="error" else z["estado"])
    clips=leer(r/"clips_sugeridos.json",[]);can=leer(r/"candidatos_todos.json",[]);meta=leer(r/"clips_sugeridos.json.meta.json",{})
    for z in g.values():z["fecha_hora"]=datetime.fromtimestamp(z["timestamp"]).isoformat(sep=" ",timespec="seconds") if z["timestamp"] else None;z["candidatos"]=len(can) if isinstance(can,list) else None;z["clips_finales"]=len(clips) if isinstance(clips,list) else None;z["provenance"]=(meta.get("fuente") or meta.get("fingerprint")) if isinstance(meta,dict) else None;z["resultados"]=str(r)
    return jsonify(ejecuciones=sorted(g.values(),key=lambda x:x["timestamp"],reverse=True),archivos=[x for x in ARCHIVOS if (r/x).is_file()],resultados=str(r))
@app.route("/api/resultados/<nombre>")
def resultado(nombre):
    if nombre not in ARCHIVOS:return jsonify(error="Archivo no permitido."),404
    r=resultados()/nombre
    if not r.is_file():return jsonify(error="No existe."),404
    return jsonify(nombre=nombre,datos=leer(r,None))
@app.route("/api/feedback",methods=["POST"])
def feedback():
    """Registra rating local y vuelve a sellar el artefacto editado."""
    d=request.get_json(silent=True) or {};r=resultados()/"clips_sugeridos.json"
    try:
        indice=int(d.get("indice"));rating=d.get("rating");rating=int(rating) if rating is not None else None
        liked=d.get("liked");liked=bool(liked) if liked is not None else None
        with open(directorio_scripts()/"ultimo_video.txt",encoding="utf-8") as f:video=f.readline().strip()
        exigir_identidad_artefacto(str(r),video,"clips_sugeridos")
        clips=leer(r,[])
        if not isinstance(clips,list) or not 0<=indice<len(clips):raise ValueError("Indice de clip invalido.")
        contexto=leer(resultados()/"juego_contexto.json",{})
        entrada=guardar_feedback(clips[indice],rating,liked,contexto)
        clips[indice]["feedback"]={"rating":rating,"liked":entrada["liked"],"timestamp":entrada["timestamp"]}
        temporal=str(r)+".tmp"
        with open(temporal,"w",encoding="utf-8") as f:json.dump(clips,f,ensure_ascii=False,indent=2)
        os.replace(temporal,r);guardar_identidad_artefacto(str(r),video,"clips_sugeridos")
        return jsonify(ok=True,feedback=entrada)
    except (OSError,ValueError,TypeError,RuntimeError) as e:return jsonify(ok=False,error=str(e)),400
# Se preservan las rutas usadas por el dock original de OBS.
@app.route("/iniciar",methods=["POST"])
def iniciar():
    if estado["grabando"]:return jsonify(ok=False,error="Ya esta grabando."),400
    d=request.get_json(silent=True) or {};cfg=leer_configuracion()
    # Las llamadas antiguas conservan sus parámetros explícitos. La Workflow
    # web omite los tres y usa los defaults persistidos en configuración.
    m=d.get("modo",cfg.get("OBS_MODO_GRABACION_DEFAULT","horizontal"))
    solo=d.get("solo_grabar",cfg.get("OBS_SOLO_GRABAR_DEFAULT",not cfg.get("OBS_PROCESAR_AL_TERMINAR",True)))
    borrar=d.get("borrar_original",cfg.get("OBS_BORRAR_ORIGINAL_AL_TERMINAR",False))
    try:s=control_grabacion.iniciar_grabacion(m,nota)
    except Exception as e:nota("ERROR al iniciar: "+str(e));return jsonify(ok=False,error=str(e)),500
    estado.update(grabando=True,modo=m,snapshot=s,solo_grabar=bool(solo),borrar_original=bool(borrar));return jsonify(ok=True,modo=m,solo_grabar=bool(solo),borrar_original=bool(borrar))
@app.route("/detener",methods=["POST"])
def detener():
    if not estado["grabando"] or estado["deteniendo"]:return jsonify(ok=False,error="No esta grabando."),400
    m,s,solo,b=estado["modo"],estado["snapshot"],estado["solo_grabar"],estado["borrar_original"];estado["deteniendo"]=True
    def t():
        try:control_grabacion.detener_grabacion_y_procesar(m,s,nota,solo,b)
        except Exception as e:nota("ERROR al detener: "+str(e))
        finally:estado.update(grabando=False,deteniendo=False,modo=None,snapshot=None)
    threading.Thread(target=t,daemon=True).start();return jsonify(ok=True)
PAGINA='''<!doctype html><meta charset="utf-8"><style>body{font:14px Segoe UI;background:#1e1e1e;color:#ddd;padding:12px}button,input,textarea,select{background:#292929;color:#ddd;border:1px solid #555;padding:6px;margin:3px}section{display:none}.on{display:block}.row{display:grid;grid-template-columns:170px 1fr}.box,#log,#json{background:#252525;padding:9px;margin-top:8px;white-space:pre-wrap;max-height:300px;overflow:auto}textarea{width:95%;height:65px}</style><nav><button onclick="show('obs')">Grabación OBS</button><button onclick="show('cfg')">Configuración</button><button onclick="show('proc')">Procesar stream</button><button onclick="show('down')">Descargar video</button><button onclick="show('hist')">Historial</button><button onclick="location.href='/camara'">Marcar cámara</button></nav><section id="obs" class="on"><div class="box"><label><input type="radio" name="m" value="horizontal" checked>Horizontal</label><label><input type="radio" name="m" value="vertical">Vertical</label><label><input type="radio" name="m" value="ambos">Ambos</label><br><label><input id="solo" type="checkbox">Solo grabar</label><label><input id="bor" type="checkbox">Borrar original</label><br><button id="rec" onclick="record()">Iniciar grabación</button><span id="st"></span></div></section><section id="cfg"><div class="box" id="fields"></div><button onclick="save()">Guardar configuración</button><button onclick="test('/api/probar/obs')">Probar OBS</button><button onclick="test('/api/probar/ollama')">Probar Ollama</button><div id="msg"></div></section><section id="proc"><div class="box">Archivo <input id="video" placeholder="C:\\stream.mkv"><br>Contexto (solo identificación)<br><textarea id="ctx"></textarea><br><button onclick="run('/api/procesar',{ruta:video.value,contexto:ctx.value})">Procesar pipeline real</button></div></section><section id="down"><div class="box">URL <input id="url"><br>Destino <input id="dest"><br><button onclick="run('/api/descargar',{url:url.value,destino:dest.value})">Descargar</button></div></section><section id="hist"><button onclick="history()">Actualizar</button><div id="rows" class="box"></div><select id="file" onchange="read()"></select><div id="json"></div></section><h4>Actividad</h4><div id="log"></div><script>let C={},K=['CARPETA_STREAMS','CARPETA_CLIPS_BASE','CARPETA_RESULTADOS','CARPETA_EDITADOS','OBS_WS_HOST','OBS_WS_PUERTO','OBS_WS_CONTRASENA','DURACION_MIN_CLIP','DURACION_MAX_CLIP','NUM_PROCESOS_TRANSCRIPCION','USAR_GPU_TRANSCRIPCION','OLLAMA_MODO','OLLAMA_HOST','OLLAMA_MODELO','OLLAMA_API_KEY'];async function A(u,o={}){let r=await fetch(u,o),d=await r.json();if(!r.ok||d.ok===false)throw Error(d.error);return d}function show(x){document.querySelectorAll('section').forEach(e=>e.className='');document.getElementById(x).className='on';if(x==='cfg')load();if(x==='hist')history()}async function load(){C=await A('/api/configuracion');let modo=C.OBS_MODO_GRABACION_DEFAULT||'horizontal',radio=document.querySelector('[name=m][value="'+modo+'"]');if(radio)radio.checked=true;document.getElementById('solo').checked=!C.OBS_PROCESAR_AL_TERMINAR;document.getElementById('bor').checked=!!C.OBS_BORRAR_ORIGINAL_AL_TERMINAR;fields.innerHTML=K.map(k=>`<div class=row>${k}<input data-k=${k} type=${k.includes('CONTRASENA')||k.includes('KEY')?'password':k==='USAR_GPU_TRANSCRIPCION'?'checkbox':'text'} value="${k.includes('CONTRASENA')||k.includes('KEY')?'':C[k]??''}" ${k==='USAR_GPU_TRANSCRIPCION'&&C[k]?'checked':''}></div>`).join('')+`CPU ${C.cpu_logicos}; límite seguro ${C.cpu_limite_recomendado}. GPU ${C.gpu.modelo} (${C.gpu.compatible?'activa':'no compatible'}). API key: solo sesión, nunca se guarda.`;dest.value=C.CARPETA_STREAMS||''}async function save(){let d={};document.querySelectorAll('[data-k]').forEach(x=>d[x.dataset.k]=x.type==='checkbox'?x.checked:x.value);try{await A('/api/configuracion',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});msg.textContent='Guardado.';load()}catch(e){msg.textContent=e.message}}async function test(u){try{msg.textContent=(await A(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({OLLAMA_API_KEY:document.querySelector('[data-k=OLLAMA_API_KEY]')?.value||''})})).mensaje}catch(e){msg.textContent=e.message}}async function run(u,d){try{await A(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)})}catch(e){alert(e.message)}}async function record(){let e=await A('/estado');await run(e.grabando?'/detener':'/iniciar',e.grabando?{}:{modo:document.querySelector('[name=m]:checked').value,solo_grabar:solo.checked,borrar_original:bor.checked})}async function history(){let d=await A('/api/historial');rows.textContent=JSON.stringify(d.ejecuciones,null,2);file.innerHTML=d.archivos.map(x=>`<option>${x}</option>`).join('');read()}async function read(){if(file.value)json.textContent=JSON.stringify((await A('/api/resultados/'+file.value)).datos,null,2)}async function tick(){try{let d=await A('/estado');rec.textContent=d.grabando?'Detener grabación':'Iniciar grabación';st.textContent=d.procesando?d.progreso.mensaje||'Procesando':d.descargando?'Descargando':d.grabando?'Grabando '+d.modo:'Detenido';log.textContent=d.log.join('\\n')}catch(e){}}setInterval(tick,1000);load();tick()</script>'''
PAGINA += '''<script>
async function selector(tipo,inicial){let r=await fetch('/api/seleccionar/'+tipo,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inicial:inicial||''})}),d=await r.json();if(!r.ok||d.ok===false)throw Error(d.error);return d}
function botonSelector(input,tipo){if(input.nextElementSibling&&input.nextElementSibling.className==='selector')return;let b=document.createElement('button');b.className='selector';b.textContent=tipo==='archivo'?'Seleccionar archivo…':'Seleccionar carpeta…';b.onclick=async()=>{try{let d=await selector(tipo,input.value);if(!d.cancelado)input.value=d.ruta}catch(e){alert(e.message)}};input.after(b)}
function agregarSelectores(){let v=document.getElementById('video'),d=document.getElementById('dest');if(v)botonSelector(v,'archivo');if(d)botonSelector(d,'carpeta');document.querySelectorAll('[data-k]').forEach(x=>{if(['CARPETA_STREAMS','CARPETA_CLIPS_BASE','CARPETA_RESULTADOS','CARPETA_EDITADOS'].includes(x.dataset.k))botonSelector(x,'carpeta')})}
setInterval(agregarSelectores,400);agregarSelectores();
</script>'''
if __name__=="__main__":print("Panel de grabacion corriendo en http://localhost:5678");app.run(host="127.0.0.1",port=5678,debug=False)
