"""Vistas web de la aplicación MKClips, conectadas a los módulos de negocio existentes."""
from __future__ import annotations
import json, os, subprocess, sys, socket
from pathlib import Path
from flask import Blueprint, Response, jsonify, request, send_file, abort
import catalogo_clips, contexto_ia, limpieza_temporales, pestana_editar, preferencias_mkclips
from configuracion_central import directorio_scripts, leer_configuracion, guardar_configuracion, normalizar_configuracion
from cola_procesamiento import QueueManager
from rutas_app import datos_dir, recursos_dir
import apoyo_config
import secrets
import edge_app

bp=Blueprint('ui_web',__name__,url_prefix='/app')
WEB=Path(__file__).resolve().parent/'ui_web'
_queues={}
_keys={}
_APP_LAUNCH_ID=secrets.token_urlsafe(18)

def _results():
    return Path(leer_configuracion().get('CARPETA_RESULTADOS') or directorio_scripts()/'resultados')
def _queue():
    path=str(_results())
    if path not in _queues:
        q=QueueManager(path,notificar=print);q.depurar_sesion_anterior();_queues[path]=q
    return _queues[path]
def _export_file(): return _results()/'exportados.json'
def _exports(): return pestana_editar.cargar_exportados(str(_export_file()))
def _json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def _ruta_script_obs():
    recursos=Path(getattr(sys,'_MEIPASS',directorio_scripts()))
    return recursos/'scripts'/'OBS'/'obs_disparar_pipeline.py' if getattr(sys,'frozen',False) else recursos/'OBS'/'obs_disparar_pipeline.py'

def _pagina(nombre):
    response=Response((WEB/nombre).read_text(encoding='utf-8'),mimetype='text/html')
    response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma']='no-cache'
    response.headers['Expires']='0'
    return response

def _solo_loopback():
    return request.remote_addr in {'127.0.0.1','::1'}

def _carpetas_easteregg():
    datos=datos_dir()/'easteregg';datos.mkdir(parents=True,exist_ok=True)
    raiz=recursos_dir()
    if raiz.name=='scripts':raiz=raiz.parent
    recurso=raiz/'assets'/'easteregg'
    return datos,recurso

_EASTER_EXT={'.mp4','.webm','.png','.jpg','.jpeg','.gif','.webp'}
def _easter_files():
    archivos=[]
    for carpeta in _carpetas_easteregg():
        try:
            archivos.extend(p.name for p in carpeta.iterdir() if p.is_file() and p.suffix.lower() in _EASTER_EXT and p.name not in archivos)
        except OSError:pass
    return archivos

_carpetas_easteregg()

@bp.get('')
@bp.get('/')
def workflow():return _pagina('workflow.html')
@bp.get('/editar')
def editar():return _pagina('editar.html')
@bp.get('/configuracion')
def configuracion():return _pagina('configuracion.html')
@bp.get('/validar')
def validar():return _pagina('validar.html')
@bp.get('/static/<path:nombre>')
def static(nombre):
    permitidos={
        'app.js','configuracion.js','editor_piezas.js','app.css','legacy_views.css',
        'mkclips_logo_oscuro.svg','mkclips_logo_claro.svg',
        'css/app.css','css/workflow.css','css/config.css','css/ajuste_pantalla.css',
        'js/feedback.js',
        'fonts/jetbrains-mono-latin-wght-normal.woff2',
        'fonts/montserrat-latin-wght-italic.woff2',
        'fonts/montserrat-latin-wght-normal.woff2',
        'fuentes/Montserrat[wght].ttf','fuentes/JetBrainsMono[wght].ttf',
        'fuentes/OFL-Montserrat.txt','fuentes/OFL-JetBrainsMono.txt',
    }
    if nombre not in permitidos:return ('No existe',404)
    ruta=(WEB/'static'/nombre) if nombre.startswith(('css/','fonts/','js/')) else WEB/nombre
    if not ruta.is_file() or WEB.resolve() not in ruta.resolve().parents:return ('No existe',404)
    return send_file(ruta,max_age=0 if nombre in {'css/ajuste_pantalla.css','js/feedback.js'} else 3600,conditional=True)

@bp.get('/api/tema')
def get_theme():
    d=_json(directorio_scripts()/'tema_usuario.json',{});v=str(d.get('tema','Modo oscuro')).lower();return jsonify(tema='claro' if 'claro' in v else 'oscuro')
@bp.post('/api/tema')
def set_theme():
    v=str((request.json or {}).get('tema','oscuro')).lower();v='claro' if v=='claro' else 'oscuro';(directorio_scripts()/'tema_usuario.json').write_text(json.dumps({'tema':'Modo claro' if v=='claro' else 'Modo oscuro'},ensure_ascii=False),encoding='utf-8');return jsonify(ok=True,tema=v)

@bp.get('/api/version')
def get_version():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    try:version=(root/'VERSION').read_text(encoding='utf-8').strip()
    except OSError:version='1.0.0'
    # Firma funcional para que el lanzador no reutilice servidores locales
    # antiguos que todavía abren la Tip Page en una ventana WebView2 inestable.
    return jsonify(version=version, ui_version=3)

@bp.get('/api/support')
def support_state():
    if not _solo_loopback():abort(403)
    return jsonify(show=bool(leer_configuracion().get('MOSTRAR_AVISO_APOYO',True)),launch_id=_APP_LAUNCH_ID,sequence=apoyo_config.SECUENCIA_EASTER_EGG)

@bp.post('/api/support/open')
def support_open():
    if not _solo_loopback():abort(403)
    # La Tip Page usa el navegador predeterminado configurado por el usuario.
    ok,error=edge_app.abrir_en_navegador_predeterminado(apoyo_config.ENLACE_DONACION)
    return (jsonify(ok=True,url=apoyo_config.ENLACE_DONACION) if ok
            else (jsonify(ok=False,error=error,url=apoyo_config.ENLACE_DONACION),503))

@bp.get('/api/easteregg')
def easteregg_list():
    if not _solo_loopback():abort(403)
    return jsonify(files=_easter_files())

@bp.get('/easteregg/<path:nombre>')
def easteregg_media(nombre):
    if not _solo_loopback():abort(403)
    if not nombre or nombre in {'.','..'} or '/' in nombre or '\\' in nombre or Path(nombre).is_absolute():abort(404)
    if Path(nombre).suffix.lower() not in _EASTER_EXT:abort(404)
    for carpeta in _carpetas_easteregg():
        try:ruta=(carpeta/nombre).resolve()
        except OSError:continue
        if carpeta.resolve() not in ruta.parents or not ruta.is_file():continue
        mime={'.mp4':'video/mp4','.webm':'video/webm','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.webp':'image/webp'}[ruta.suffix.lower()]
        return send_file(ruta,mimetype=mime,conditional=True,max_age=0)
    abort(404)

@bp.get('/api/cola')
def queue_state():
    import procesar_multiples
    return jsonify(queue=_queue().get_queue(),running=_queue().is_running(),progress=procesar_multiples.leer_estado_progreso() or {})
@bp.post('/api/cola/add')
def queue_add():
    d=request.json or {};q=_queue();n=0
    for p in d.get('paths',[]):
        if os.path.isfile(p):q.add_stream(p,str(d.get('contexto') or ''));n+=1
    return jsonify(ok=True,added=n)
@bp.post('/api/cola/folder')
def queue_folder():_queue().add_folder(str((request.json or {}).get('path','')));return jsonify(ok=True)
@bp.post('/api/cola/context')
def queue_context():return jsonify(ok=True,updated=_queue().aplicar_contexto_pendientes(str((request.json or {}).get('contexto') or '')))
@bp.post('/api/cola/item')
def queue_item():
    d=request.json or {};return (jsonify(ok=True) if _queue().set_contexto(str(d.get('path','')),str(d.get('contexto') or '')) else (jsonify(ok=False,error='Ese stream no está pendiente.'),400))
@bp.post('/api/cola/<accion>')
def queue_action(accion):
    q=_queue();actions={'start':q.start,'pause':q.pause,'resume':q.resume,'cancel':q.cancel,'clear':q.limpiar_terminados}
    if accion not in actions:return jsonify(ok=False,error='Acción desconocida'),404
    actions[accion]();return jsonify(ok=True)

@bp.get('/api/historial')
def history():
    clips=_json(_results()/'catalogo_clips.json',[]);by={}
    for x in clips if isinstance(clips,list) else []:
        stream=x.get('stream') or Path(x.get('ruta_archivo','')).parent.name;by[stream]=by.get(stream,0)+1
    return jsonify(streams=[{'stream':k,'clips':v} for k,v in sorted(by.items(),key=lambda x:-x[1])],directory=str(_results()))
@bp.post('/api/open-results')
def open_results():
    p=_results();p.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':os.startfile(str(p))
    elif sys.platform=='darwin':subprocess.Popen(['open',str(p)])
    else:subprocess.Popen(['xdg-open',str(p)])
    return jsonify(ok=True)

def _clips():
    entries=[e for e in catalogo_clips.cargar_catalogo(str(_results())) if os.path.isfile(e.get('ruta_archivo',''))]
    prefs=preferencias_mkclips.cargar_preferencias();view=pestana_editar.clips_valorados(entries,prefs,preferencias_mkclips.identificador_clip,preferencias_mkclips.feedback_por_clip);exports=_exports()
    result=[]
    for c in view:
        ruta=c['ruta'];clip=c['clip'];dur=clip.get('duracion_final',clip.get('duracion',0))
        result.append({'id':__import__('editor_rutas').id_de_clip(ruta),'title':c['titulo'],'stream':c['stream'] or Path(ruta).parent.name,'stars':c['estrellas'],'duration':dur,'done':pestana_editar.clave_ruta(ruta) in exports,'ruta':ruta,'clip':clip,'fuente':c.get('fuente'),'contexto_juego':clip.get('_contexto_juego')})
    return result
@bp.get('/api/clips')
def clips_api():return jsonify(clips=_clips())
@bp.get('/api/validation')
def validation_api():
    all_clips=_clips();prefs=preferencias_mkclips.cargar_preferencias();last={}
    entries=catalogo_clips.sincronizar(str(_results()),leer_configuracion().get('CARPETA_CLIPS_BASE') or '',
        clips_actuales=_json(_results()/'clips_sugeridos.json',[]),
        feedback=prefs.get('feedback',[]),contexto_actual=catalogo_clips.leer_contexto_juego(str(_results())))
    by_id={}
    for e in entries:
        ruta=e.get('ruta_archivo')
        if not ruta or not os.path.isfile(ruta):continue
        clip=dict(e.get('clip') or {});clip.setdefault('ruta_archivo',ruta)
        cid=preferencias_mkclips.identificador_clip(clip,e.get('fuente'))
        fb=preferencias_mkclips.feedback_por_clip(clip,e.get('fuente'),prefs)
        if fb is None and clip.get('clip_id_legado'):
            fb=next((x for x in reversed(prefs.get('feedback',[])) if x.get('clip_id')==clip['clip_id_legado']),None)
        tipo='Historia' if clip.get('tipo_candidato') in {'historia','completo'} or clip.get('tipo')=='completo' else 'Momento'
        by_id[__import__('editor_rutas').id_de_clip(ruta)]={'id':__import__('editor_rutas').id_de_clip(ruta),'feedback_id':cid,'title':pestana_editar.titulo_de(clip),'stream':e.get('stream') or Path(ruta).parent.name,'stars':(fb or {}).get('rating') or 0,'discarded':bool((fb or {}).get('discarded')),'type':tipo,'duration':clip.get('duracion_final',clip.get('duracion',0)),'clip':clip,'fuente':e.get('fuente'),'contexto_juego':e.get('contexto_juego')}
    for f in prefs.get('feedback',[]):
        if f.get('clip_id'):last[f['clip_id']]=f
    return jsonify(clips=sorted(by_id.values(),key=lambda c:(-float(c['clip'].get('score_bruto',c['clip'].get('score',0)) or 0),c['stream'],os.path.basename(c['clip'].get('ruta_archivo') or ''))))
@bp.post('/api/clips/mark')
def mark_clip():
    d=request.json or {};c=next((x for x in _clips() if x['id']==d.get('id')),None)
    if not c:return jsonify(ok=False,error='Clip no encontrado.'),404
    exports=_exports();k=pestana_editar.clave_ruta(c['ruta'])
    if d.get('done'):exports[k]={'ruta_clip':c['ruta'],'fecha':__import__('datetime').datetime.now().astimezone().isoformat(timespec='minutes'),'salida':'','manual':True}
    else:exports.pop(k,None)
    pestana_editar.guardar_exportados(str(_export_file()),exports);return jsonify(ok=True)
@bp.get('/api/thumb/<id_clip>')
def thumb(id_clip):
    c=next((x for x in _clips() if x['id']==id_clip),None)
    if not c:
        c=next((x for x in validation_api().json.get('clips',[]) if x['id']==id_clip),None)
    if not c:return ('',404)
    cache=Path(directorio_scripts())/'.mkclips_cache'/'revision'/'web';thumb=cache/(id_clip+'.jpg')
    if not thumb.is_file():
        try:
            import configuracion_app
            configuracion_app._generar_miniatura_revision(c.get('ruta') or c['clip'].get('ruta_archivo'),str(thumb))
        except Exception:return ('',404)
    return send_file(thumb,mimetype='image/png',max_age=3600)

@bp.post('/api/clips/ratings')
def ratings():
    # Same preference store and stable clip identity as the desktop validation view.
    changes=(request.json or {}).get('changes',[]);byid={c['id']:c for c in validation_api().json.get('clips',[])}
    for change in changes:
        c=byid.get(change.get('id'))
        if not c:continue
        entry=next((e for e in catalogo_clips.cargar_catalogo(str(_results())) if os.path.normcase(os.path.abspath(e['ruta_archivo']))==os.path.normcase(os.path.abspath(c['clip'].get('ruta_archivo') or ''))),{})
        clip=dict(c['clip']);clip.setdefault('ruta_archivo',c.get('ruta') or clip.get('ruta_archivo'));rating=change.get('rating')
        rating_value=int(rating) if rating else None;discarded=bool(change.get('discarded') or not rating)
        preferencias_mkclips.guardar_feedback(clip,rating=rating_value,discarded=discarded,fuente=c.get('fuente'),contexto_juego=c.get('contexto_juego'),motivo=str(change.get('motivo') or ''),comentario=str(change.get('comentario') or ''))
        if discarded:
            ruta=clip.get('ruta_archivo') or clip.get('archivo')
            ok,_motivo=catalogo_clips.borrar_clip(ruta)
            if ok:
                catalogo_clips.quitar_clips(str(_results()),[ruta])
                catalogo_clips.quitar_del_historial([ruta],str(directorio_scripts()/'historial_clips.json'))
        else:
            clip['_fuente']=c.get('fuente');clip['_contexto_juego']=c.get('contexto_juego')
            entradas=catalogo_clips.cargar_catalogo(str(_results()))
            for registro in entradas:
                if os.path.normcase(os.path.abspath(registro.get('ruta_archivo','')))==os.path.normcase(os.path.abspath(clip.get('ruta_archivo',''))):
                    registro['clip']=clip;break
            catalogo_clips.guardar_catalogo(str(_results()),entradas)
    return jsonify(ok=True)

@bp.post('/api/clips/trim')
def trim_clips():
    limit=float(leer_configuracion().get('DURACION_MAX_CLIP') or 0)
    if limit<=0:return jsonify(ok=False,error='Configura primero la duración m?xima.'),400
    count=0;errors=[]
    for c in validation_api().json.get('clips',[]):
        if float(c.get('duration') or 0)>limit+0.05:
            ok,_=catalogo_clips.recortar_a_maximo(c['clip'].get('ruta_archivo') or c['clip'].get('archivo'),limit)
            if ok:count+=1
            else:errors.append(c['title'])
    return jsonify(ok=True,recortados=count,errores=errors)

@bp.post('/api/clips/play')
def play_clip():
    d=request.json or {};c=next((x for x in validation_api().json.get('clips',[]) if x['id']==d.get('id')),None)
    if not c:return jsonify(ok=False,error='Clip no encontrado.'),404
    try:
        import reproductor_sistema
        ok,msg=reproductor_sistema.abrir_en_reproductor(c['clip'].get('ruta_archivo') or c['clip'].get('archivo') or '')
        return jsonify(ok=bool(ok),mensaje=msg)
    except Exception as e:return jsonify(ok=False,error=str(e)),400

@bp.get('/api/config')
def get_config():
    from configuracion_central import limite_cpu_recomendado
    d=leer_configuracion();d.pop('OBS_WS_CONTRASENA',None);d.pop('LLM_API_KEY',None);d['cpu_logicos']=os.cpu_count() or 1;d['cpu_limite_recomendado']=limite_cpu_recomendado();d['obs_script']=str(_ruta_script_obs());d['gpu']={'modelo':'GPU disponible' if d.get('USAR_GPU_TRANSCRIPCION') else 'No detectada'};return jsonify(d)
@bp.post('/api/config')
def save_config():
    data=request.json or {};v=leer_configuracion();secret=data.pop('OBS_WS_CONTRASENA',None);key=data.pop('API_KEY',None);assembly_key=data.pop('ASSEMBLYAI_API_KEY',None)
    for k in v:
        if k in data:v[k]=data[k]
    if 'OBS_WS_CONTRASENA' in request.json:
        if secret:os.environ['OBS_WS_CONTRASENA']=str(secret)
        else:os.environ.pop('OBS_WS_CONTRASENA',None)
    try:guardar_configuracion(normalizar_configuracion(v))
    except (ValueError,OSError) as e:
        message=str(e);lower=message.lower();field='configuracion'
        for needles,key in ((('modo de grabación','modo de grabacion'),'OBS_MODO_GRABACION_DEFAULT'),(('duración mínima','duracion minima'),'DURACION_MIN_CLIP'),(('duración máxima','duracion maxima'),'DURACION_MAX_CLIP'),(('puerto de obs',),'OBS_WS_PUERTO'),(('hilos de cpu','procesos de transcripción'),'NUM_PROCESOS_TRANSCRIPCION'),(('modo de ollama',),'OLLAMA_MODO'),(('host de ollama',),'OLLAMA_HOST'),(('url base de la ia','url base'),'LLM_BASE_URL'),(('modelo de ia','nombre del modelo'),'LLM_MODELO'),(('variable de la api key','variable de la clave'),'LLM_API_KEY_ENV'),(('assemblyai',),'ASSEMBLYAI_API_KEY_ENV')):
            if any(n in lower for n in needles):field=key;break
        return jsonify(ok=False,error=message,errors={field:message}),400
    if key:
        _keys['llm']=str(key)
        os.environ[str(v.get('LLM_API_KEY_ENV') or 'LLM_API_KEY')]=str(key)
    if assembly_key:
        _keys['assemblyai']=str(assembly_key)
        os.environ[str(v.get('ASSEMBLYAI_API_KEY_ENV') or 'ASSEMBLYAI_API_KEY')]=str(assembly_key)
    return jsonify(ok=True)
@bp.get('/api/criteria')
def get_criteria():
    p=Path(contexto_ia.ARCHIVO_CRITERIOS)
    try:return jsonify(texto=p.read_text(encoding='utf-8'))
    except OSError:return jsonify(texto='')
@bp.post('/api/criteria')
def save_criteria():return jsonify(ok=True,texto=contexto_ia.guardar_criterios(str((request.json or {}).get('texto',''))))
@bp.post('/api/update-criteria')
def update_criteria():
    d=request.json or {}
    try:
        texto=contexto_ia.generar_criterios(valores=leer_configuracion(),criterios_actuales=str(d.get('actuales') or ''),contexto_proyecto=leer_configuracion().get('CONTEXTO_PROYECTO',''),clave=str(d.get('key') or _keys.get('llm') or '') or None)
        return jsonify(ok=True,texto=texto)
    except Exception as e:return jsonify(ok=False,error=str(e)),400
@bp.post('/api/test-ai')
def test_ai():
    try:
        import configuracion_app
        msg=configuracion_app.probar_ia(leer_configuracion(),str((request.json or {}).get('key') or _keys.get('llm') or ''));return jsonify(ok=True,mensaje=msg)
    except Exception as e:return jsonify(ok=False,error=str(e)),400
@bp.post('/api/panel/start')
def start_panel():
    try:
        with socket.create_connection(('127.0.0.1',5678),timeout=0.35):
            return jsonify(ok=True,mensaje='El panel ya está activo.')
    except OSError:
        script=(Path(getattr(sys,'_MEIPASS',directorio_scripts()))/'scripts'/'panel_grabacion.py') if getattr(sys,'frozen',False) else directorio_scripts()/'panel_grabacion.py'
        if not script.is_file():return jsonify(ok=False,error='No se encontró panel_grabacion.py.'),404
        try:
            log=(directorio_scripts()/'panel_obs.log').open('a',encoding='utf-8')
            cmd=[sys.executable,'--server'] if getattr(sys,'frozen',False) else [sys.executable,str(script)]
            subprocess.Popen(cmd,cwd=str(directorio_scripts()),stdout=log,stderr=subprocess.STDOUT,
                             env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'))
            return jsonify(ok=True,mensaje='Se está iniciando el panel.')
        except OSError as e:return jsonify(ok=False,error=str(e)),500
@bp.get('/api/clean-preview')
def clean_preview():return jsonify(categorias=limpieza_temporales.analizar(leer_configuracion().get('CARPETA_CLIPS_BASE') or ''))
@bp.post('/api/clean')
def clean():
    ids=(request.json or {}).get('ids',[])
    if _queue().is_running():return jsonify(ok=False,error='La cola está activa.'),409
    n,b,errs=limpieza_temporales.eliminar(ids,leer_configuracion().get('CARPETA_CLIPS_BASE') or '')
    return jsonify(ok=True,archivos=n,bytes=b,errores=errs)

def registrar(app):
    app.register_blueprint(bp)
    app.add_url_rule('/static/js/feedback.js', endpoint='ui_web_feedback_static', view_func=lambda: static('js/feedback.js'))
