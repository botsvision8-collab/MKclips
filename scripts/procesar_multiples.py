import subprocess
import os
import glob
import sys
import json
import time

# Este modulo se usa de dos formas: como parte del paquete ``scripts`` (la GUI)
# y como modulo suelto desde los scripts del pipeline, que se lanzan con
# ``cwd=scripts``. Los imports funcionan en ambos casos.
try:
    from .rutas_app import comando_python, datos_dir
except ImportError:
    from rutas_app import comando_python, datos_dir

try:
    from . import cache_mkclips
    from .duracion_clips import validar_limites_duracion
except ImportError:
    import cache_mkclips
    from duracion_clips import validar_limites_duracion

try:
    try:
        from .config import CARPETA_STREAMS, CARPETA_RESULTADOS
    except ImportError:
        from config import CARPETA_STREAMS, CARPETA_RESULTADOS
except ImportError:
    print("ADVERTENCIA: no se encontro config.py, usando valor generico.")
    print("Copia config_ejemplo.py como config.py y personalizalo.\n")
    CARPETA_STREAMS = os.path.join(str(datos_dir()), "streams") if getattr(sys, "frozen", False) else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "streams")
    CARPETA_RESULTADOS = ""

EXTENSIONES = ("*.mp4", "*.mkv", "*.mov", "*.avi")

_CARPETA_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
_CARPETA_DATOS = str(datos_dir())
# Rutas absolutas: la app, los pasos del pipeline (cwd=scripts) y la ventana de
# progreso deben leer y escribir SIEMPRE los mismos archivos.
ARCHIVO_ESTADO_PROGRESO = os.path.join(str(datos_dir()), "estado_progreso.json")
ARCHIVO_LOCK_NOTIFICACION = os.path.join(str(datos_dir()), "notificacion.lock")
ARCHIVO_HISTORIAL_TIEMPOS = os.path.join(str(datos_dir()), "historial_tiempos_proceso.json")
RESULTADOS_DIR = os.path.abspath(CARPETA_RESULTADOS) if CARPETA_RESULTADOS else os.path.join(str(datos_dir()), "resultados")
os.makedirs(RESULTADOS_DIR, exist_ok=True)
RATIO_POR_DEFECTO = 0.4  # segundos de proceso por segundo de video, hasta tener historial real

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040

RAM_ESTIMADA_POR_PROCESO_WHISPER_GB = 2.5


def _ram_disponible_gb():
    """Best-effort: RAM fisica libre en GB. Devuelve None si no se puede medir."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        estado = MEMORYSTATUSEX()
        estado.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado))
        return estado.ullAvailPhys / (1024 ** 3)
    except Exception:
        return None


def calcular_max_procesos_transcripcion_seguro():
    """
    Tope recomendado de procesos paralelos para transcribir: deja 1-2
    nucleos libres (para que navegador/Office no se traben) Y respeta la
    RAM disponible (cada proceso carga su propio modelo Whisper completo,
    ~2.5GB cada uno - de ahi salen los cuelgues si se pide un numero muy
    alto sin suficiente RAM).
    """
    nucleos = os.cpu_count() or 1
    max_por_cpu = max(1, int(nucleos * 0.75))

    ram_disp = _ram_disponible_gb()
    if ram_disp is not None:
        max_por_ram = max(1, int(ram_disp // RAM_ESTIMADA_POR_PROCESO_WHISPER_GB))
        return max(1, min(max_por_cpu, max_por_ram))
    return max_por_cpu

# (script, usa_nombre_del_archivo_como_argumento, mensaje_para_mostrar)
PASOS_PIPELINE = [
    ("transcribir.py", True, "Transcribiendo..."),
    ("detectar_eventos_audio.py", True, "Detectando eventos de audio..."),
    ("analizar_video_visual.py", True, "Analizando eventos visuales..."),
    ("identificar_clips.py", False, "Identificando clips..."),
    ("cortar_clips_nvenc.py", False, "Cortando clips con NVENC..."),
    ("verificar_segmentos.py", False, "Verificando clips por segmentos..."),
]


def _digest_archivo(ruta):
    ruta = os.path.abspath(ruta)
    if not os.path.isfile(ruta):
        return None
    return cache_mkclips._sha256_file(ruta)


def _valores_configuracion(claves):
    """Lee únicamente ajustes que realmente afectan una etapa de caché."""
    ruta = os.path.join(str(datos_dir()), "config.py")
    valores = {clave: None for clave in claves}
    try:
        import ast
        with open(ruta, "r", encoding="utf-8") as archivo:
            tree = ast.parse(archivo.read(), filename=ruta)
        for nodo in tree.body:
            if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name):
                if nodo.targets[0].id in valores:
                    valores[nodo.targets[0].id] = ast.literal_eval(nodo.value)
    except (OSError, SyntaxError, ValueError, TypeError):
        pass
    return valores


def _dependencias_cache(video_path, etapa):
    carpeta_scripts = os.path.dirname(os.path.abspath(__file__))
    carpeta_datos = str(datos_dir())
    dependencias = {
        "cache_schema": cache_mkclips.CACHE_VERSION,
        "script": _digest_archivo(os.path.join(carpeta_scripts, {
            "transcripcion": "transcribir.py",
            "eventos_audio": "detectar_eventos_audio.py",
            "eventos_visuales": "analizar_video_visual.py",
            "identificacion": "identificar_clips.py",
        }[etapa])),
    }
    if etapa == "transcripcion":
        dependencias["config_transcripcion"] = _valores_configuracion(
            ("CONTEXTO_TRANSCRIPCION", "NUM_PROCESOS_TRANSCRIPCION", "USAR_GPU_TRANSCRIPCION", "TRANSCRIPCION_MOTOR")
        )
        # Con Whisper local la clave no se incluye: asi las transcripciones ya guardadas siguen siendo validas.
        if dependencias["config_transcripcion"].get("TRANSCRIPCION_MOTOR") in (None, "whisper_local"):
            dependencias["config_transcripcion"].pop("TRANSCRIPCION_MOTOR", None)
    elif etapa == "eventos_audio":
        dependencias["transcripcion"] = _digest_archivo(os.path.join(carpeta_datos, "transcripcion.json"))
    elif etapa == "eventos_visuales":
        dependencias.update({"intervalo": 2.0, "ancho": 160, "alto": 90, "umbral": 0.16})
    elif etapa == "identificacion":
        resultados = RESULTADOS_DIR
        dependencias["transcripcion"] = _digest_archivo(os.path.join(carpeta_datos, "transcripcion.json"))
        dependencias["eventos_audio"] = _digest_archivo(os.path.join(carpeta_datos, "eventos_audio.json"))
        dependencias["eventos_visuales"] = _digest_archivo(os.path.join(resultados, "eventos_visuales.json"))
        dependencias["scoring"] = _digest_archivo(os.path.join(carpeta_scripts, "scoring_mkclips.py"))
        dependencias["narrativa"] = _digest_archivo(os.path.join(carpeta_scripts, "narrativa_mkclips.py"))
        dependencias["preferencias"] = _digest_archivo(os.path.join(carpeta_scripts, "preferencias_mkclips.py"))
        dependencias["feedback_usuario"] = _digest_archivo(os.path.join(carpeta_datos, "preferencias_usuario.json"))
        limites = _valores_configuracion(("DURACION_MIN_CLIP", "DURACION_MAX_CLIP"))
        try:
            minimo, maximo = validar_limites_duracion(
                limites["DURACION_MIN_CLIP"] or 0, limites["DURACION_MAX_CLIP"] or 0
            )
        except ValueError:
            minimo, maximo = "INVALIDO", "INVALIDO"
        dependencias["duracion_clips"] = {"minimo": minimo, "maximo": maximo}
        # Cambiar de IA (proveedor/modelo) debe volver a elegir los clips.
        dependencias["ia"] = _valores_configuracion(
            ("LLM_PROVEEDOR", "LLM_BASE_URL", "LLM_MODELO", "OLLAMA_MODO", "OLLAMA_MODELO", "CONTEXTO_PROYECTO")
        )
        # Los criterios del creador (texto editable) tambien cambian que clips se eligen.
        dependencias["criterios_creador"] = _digest_archivo(os.path.join(_CARPETA_DATOS, "criterios_creador.txt"))
        dependencias["contexto_stream"] = _digest_archivo(
            os.path.join(resultados, "contexto_stream.json")
        )
    return dependencias


def _especificacion_cache(video_path, script):
    carpeta_scripts = os.path.dirname(os.path.abspath(__file__))
    carpeta_datos = str(datos_dir())
    resultados = RESULTADOS_DIR
    definiciones = {
        "transcribir.py": (
            "transcripcion",
            [
                os.path.join(carpeta_datos, "transcripcion.json"),
                os.path.join(carpeta_datos, "transcripcion.json.meta.json"),
                os.path.join(carpeta_datos, "ultimo_video.txt"),
            ],
        ),
        "detectar_eventos_audio.py": (
            "eventos_audio",
            [
                os.path.join(carpeta_datos, "eventos_audio.json"),
                os.path.join(carpeta_datos, "eventos_audio.json.meta.json"),
            ],
        ),
        "analizar_video_visual.py": (
            "eventos_visuales",
            [
                os.path.join(resultados, "eventos_visuales.json"),
                os.path.join(resultados, "eventos_visuales.json.meta.json"),
                os.path.join(resultados, "metricas_visual.json"),
            ],
        ),
        "identificar_clips.py": (
            "identificacion",
            [
                os.path.join(resultados, "candidatos_todos.json"),
                os.path.join(resultados, "candidatos_todos.json.meta.json"),
                os.path.join(resultados, "candidatos_cortos.json"),
                os.path.join(resultados, "candidatos_cortos.json.meta.json"),
                os.path.join(resultados, "scores_clips.json"),
                os.path.join(resultados, "scores_clips.json.meta.json"),
                os.path.join(resultados, "clips_sugeridos.json"),
                os.path.join(resultados, "clips_sugeridos.json.meta.json"),
                os.path.join(resultados, "metricas_identificacion.json"),
                os.path.join(resultados, "metricas_identificacion.json.meta.json"),
                os.path.join(resultados, "juego_contexto.json"),
                os.path.join(resultados, "juego_contexto.json.meta.json"),
                os.path.join(resultados, "arcos_narrativos.json"),
                os.path.join(resultados, "arcos_narrativos.json.meta.json"),
                os.path.join(resultados, "resumen_plan.json"),
                os.path.join(resultados, "resumen_plan.json.meta.json"),
                os.path.join(resultados, "contexto_stream.json"),
            ],
        ),
    }
    return definiciones.get(script)


def _intentar_cache_etapa(video_path, script, paso, notificar):
    especificacion = _especificacion_cache(video_path, script)
    if not especificacion:
        return False
    etapa, artefactos = especificacion
    dependencias = _dependencias_cache(video_path, etapa)
    etiqueta = {
        "transcripcion": "Transcripcion",
        "eventos_audio": "Audio",
        "eventos_visuales": "Vision",
        "identificacion": "Identificacion",
    }[etapa]
    if cache_mkclips.validar_cache_etapa(video_path, etapa, artefactos, dependencias):
        cache_mkclips.restaurar_cache_etapa(video_path, etapa, artefactos)
        notificar(f"[{paso}/6] {etiqueta}: CACHE HIT")
        return True
    notificar(f"[{paso}/6] {etiqueta}: CACHE MISS -> ejecutando etapa")
    return False


def _guardar_cache_etapa(video_path, script):
    especificacion = _especificacion_cache(video_path, script)
    if not especificacion:
        return
    etapa, artefactos = especificacion
    dependencias = _dependencias_cache(video_path, etapa)
    if not cache_mkclips.guardar_cache_etapa(video_path, etapa, artefactos, dependencias):
        print(f"ADVERTENCIA: no se pudo guardar cache de {etapa}.")


def _guardar_contexto_stream(video_path, contexto):
    ruta = os.path.join(RESULTADOS_DIR, "contexto_stream.json")
    datos = {
        "version": 1,
        "creado": time.time(),
        "fuente": cache_mkclips.identidad_fuente(video_path),
        "contexto": (contexto or "").strip(),
    }
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)
    return ruta


def _evitar_suspension(activar):
    """
    Evita que Windows suspenda la PC mientras hay un proceso largo
    corriendo (transcribir/cortar clips puede tardar mucho). Se llama con
    True al empezar y False al terminar (o si algo falla).
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        flags = (ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED) if activar else ES_CONTINUOUS
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def _duracion_video_segundos(video_path):
    try:
        resultado = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True
        )
        return float(resultado.stdout.strip())
    except Exception:
        return None


def _cargar_ratio_historial():
    if os.path.exists(ARCHIVO_HISTORIAL_TIEMPOS):
        try:
            with open(ARCHIVO_HISTORIAL_TIEMPOS, "r", encoding="utf-8") as f:
                datos = json.load(f)
            return datos.get("ratio_promedio", RATIO_POR_DEFECTO), datos.get("muestras", 0)
        except Exception:
            pass
    return RATIO_POR_DEFECTO, 0


def _guardar_ratio_historial(ratio_esta_vez, muestras_previas, ratio_previo):
    muestras_nuevas = muestras_previas + 1
    ratio_actualizado = (ratio_previo * muestras_previas + ratio_esta_vez) / muestras_nuevas
    try:
        # Se conservan las claves opcionales que otras etapas anaden (p. ej. "capas").
        datos = {}
        if os.path.exists(ARCHIVO_HISTORIAL_TIEMPOS):
            try:
                with open(ARCHIVO_HISTORIAL_TIEMPOS, "r", encoding="utf-8") as f:
                    leido = json.load(f)
                if isinstance(leido, dict):
                    datos = leido
            except Exception:
                datos = {}
        datos["ratio_promedio"] = ratio_actualizado
        datos["muestras"] = muestras_nuevas
        temporal = f"{ARCHIVO_HISTORIAL_TIEMPOS}.{os.getpid()}.tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(datos, f)
        os.replace(temporal, ARCHIVO_HISTORIAL_TIEMPOS)
    except Exception:
        pass


def _guardar_estado_atomico(estado):
    """Escribe estado_progreso.json sin que un lector (la ventana de progreso
    lee cada 0,5 s) llegue a ver el archivo a medias."""
    temporal = f"{ARCHIVO_ESTADO_PROGRESO}.{os.getpid()}.tmp"
    try:
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        os.replace(temporal, ARCHIVO_ESTADO_PROGRESO)
    except Exception:
        try:
            os.remove(temporal)
        except OSError:
            pass


# Posicion dentro de una cola de varios streams; la ventana de progreso la usa
# para mostrar "Stream 2/5" y para no cerrarse entre un stream y el siguiente.
_INFO_COLA = {"indice": 0, "total": 0, "activa": False}


def establecer_info_cola(indice, total, activa=True):
    """Indica que se esta procesando el stream ``indice`` de ``total``."""
    _INFO_COLA.update(indice=int(indice), total=int(total), activa=bool(activa))


def finalizar_info_cola():
    """Marca la cola como terminada: la ventana de progreso ya puede cerrarse sola."""
    _INFO_COLA.update(activa=False)
    estado = leer_estado_progreso()
    if not estado:
        return
    estado.update(cola_activa=False, actualizado=time.time())
    _guardar_estado_atomico(estado)


def _escribir_estado_progreso(archivo, paso_actual, total_pasos, mensaje, inicio,
                               eta_segundos=None, terminado=False, error=False):
    estado = {
        "archivo": archivo,
        "paso_actual": paso_actual,
        "total_pasos": total_pasos,
        "mensaje": mensaje,
        "inicio": inicio,
        "eta_segundos": eta_segundos,
        "terminado": terminado,
        "error": error,
        "cola_indice": _INFO_COLA["indice"],
        "cola_total": _INFO_COLA["total"],
        "cola_activa": _INFO_COLA["activa"],
        "actualizado": time.time(),
    }
    _guardar_estado_atomico(estado)


def leer_estado_progreso():
    """Lee el estado actual del proceso desde disco - usado por la app y
    por la ventanita de notificacion para mostrar progreso persistente
    (funciona aunque se haya cerrado y vuelto a abrir el programa)."""
    if not os.path.exists(ARCHIVO_ESTADO_PROGRESO):
        return None
    try:
        with open(ARCHIVO_ESTADO_PROGRESO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def actualizar_porcentaje_progreso(porcentaje, mensaje=None):
    """
    Actualiza SOLO el porcentaje (y opcionalmente el mensaje) del estado
    ya existente, sin tocar el resto (archivo, paso_actual, etc.) - para
    que un paso largo como transcribir pueda reportar avance fino desde
    adentro, sin ser quien controla el estado completo.
    """
    estado = leer_estado_progreso()
    if not estado:
        return
    estado["porcentaje"] = porcentaje
    if mensaje:
        estado["mensaje"] = mensaje
    estado["actualizado"] = time.time()
    _guardar_estado_atomico(estado)


def _barra_texto(porcentaje, ancho=20):
    """Barra de progreso en texto, ej: '████████░░░░░░░░ 42%'."""
    if porcentaje is None:
        return ""
    porcentaje = max(0, min(100, porcentaje))
    llenos = int(round(ancho * porcentaje / 100))
    return "█" * llenos + "░" * (ancho - llenos) + f" {porcentaje}%"


def _proceso_vivo(pid):
    """True si existe un proceso con ese PID (multiplataforma, sin dependencias)."""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = ctypes.c_void_p
            handle = kernel.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            codigo = ctypes.c_ulong()
            ok = kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(codigo))
            kernel.CloseHandle(ctypes.c_void_p(handle))
            return bool(ok) and codigo.value == 259  # STILL_ACTIVE
        except Exception:
            return True  # ante la duda, no relanzar una ventana duplicada
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def _lock_notificacion_vigente():
    """Un lock solo vale si el proceso que lo creo sigue vivo. Si la ventana
    se cayo (por ejemplo por un error de import) el lock queda huerfano y
    bloquearia para siempre las ventanas siguientes: se elimina."""
    if not os.path.exists(ARCHIVO_LOCK_NOTIFICACION):
        return False
    try:
        with open(ARCHIVO_LOCK_NOTIFICACION, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
        pid = int(contenido) if contenido.isdigit() else 0
    except OSError:
        return True
    # Los locks de versiones anteriores contenian solo "1": no identifican ningun proceso.
    if pid > 1 and _proceso_vivo(pid):
        return True
    if contenido == "persistente":
        return True  # lo gestiona el propio modo --persistente
    try:
        os.remove(ARCHIVO_LOCK_NOTIFICACION)
    except OSError:
        pass
    return False


def lanzar_notificacion_progreso():
    """
    Abre la ventanita de progreso si no hay una ya corriendo (best-effort:
    si algo falla, como no tener pystray/Pillow instalados, simplemente
    no se muestra - nunca interrumpe el pipeline). Es seguro llamarla antes de
    cada video: si la ventana sigue viva no abre otra. Los errores de la
    ventana quedan en notificacion_error.log.
    """
    if _lock_notificacion_vigente():
        return
    try:
        ruta_script = os.path.join(_CARPETA_SCRIPTS, "notificacion_progreso.py")
        comando = comando_python("notificacion_progreso.py", [ARCHIVO_ESTADO_PROGRESO])
        proceso = subprocess.Popen(
            comando, cwd=str(datos_dir()),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        with open(ARCHIVO_LOCK_NOTIFICACION, "w", encoding="utf-8") as f:
            f.write(str(proceso.pid))
    except Exception:
        pass


def listar_videos(carpeta):
    archivos = []
    for ext in EXTENSIONES:
        archivos.extend(glob.glob(os.path.join(carpeta, ext)))
    archivos.sort(key=os.path.getmtime, reverse=True)
    return archivos


def _motor_transcripcion():
    return str(_valores_configuracion(("TRANSCRIPCION_MOTOR",)).get("TRANSCRIPCION_MOTOR") or "whisper_local").lower()


def correr_paso(script, argumento=None, env_extra=None):
    # Resolver cada script desde la carpeta real de este orquestador.
    # Asi no depende de la carpeta desde la que se lance el programa.
    carpeta_scripts = os.path.dirname(os.path.abspath(__file__))
    ruta_script = script if os.path.isabs(script) else os.path.join(carpeta_scripts, script)
    if script == "transcribir.py" and _motor_transcripcion() == "assemblyai":
        alterno = os.path.join(carpeta_scripts, "transcribir_nube.py")
        if os.path.isfile(alterno):
            ruta_script = alterno  # si AssemblyAI falla, ese script ejecuta transcribir.py (Whisper local)

    if not os.path.isfile(ruta_script):
        print(f"ERROR: no se encontro el script del pipeline: {ruta_script}")
        return False, 0.0

    comando = comando_python(os.path.basename(ruta_script), [argumento] if argumento else [])
    entorno = os.environ.copy()
    if env_extra:
        entorno.update(env_extra)
    inicio = time.time()
    directorio_trabajo = str(datos_dir()) if getattr(sys, "frozen", False) else carpeta_scripts
    resultado = subprocess.run(comando, env=entorno, cwd=directorio_trabajo)
    return resultado.returncode == 0, time.time() - inicio



def _registrar_metrica_paso(nombre, script, duracion, resultado):
    try:
        resultados_dir = RESULTADOS_DIR
        ruta = os.path.join(resultados_dir, "metricas_proceso.json")
        datos = {}
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
        if not isinstance(datos, dict):
            datos = {}
        datos.setdefault("ejecuciones", [])
        datos["ejecuciones"].append({"archivo": nombre, "paso": os.path.basename(script), "duracion_segundos": round(duracion, 3), "resultado": resultado, "timestamp": time.time()})
        datos["ejecuciones"] = datos["ejecuciones"][-100:]
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def procesar_un_video(video_path, modo_automatico=False, notificar=print, contexto_stream=""):
    """
    Corre todas las etapas del pipeline sobre un solo video. Mientras corre:
    - evita que Windows suspenda la PC.
    - escribe el progreso a disco (estado_progreso.json) con un ETA
      estimado a partir del historial de veces anteriores, para que la
      app y la ventanita de notificacion lo puedan mostrar en cualquier
      momento, incluso si se cerraron y se volvieron a abrir.

    modo_automatico=True evita que cortar_clips.py se quede esperando un
    input() de consola. El original NUNCA se borra aqui dentro.

    Devuelve True si todas las etapas terminaron bien, False si alguna fallo.
    """
    nombre = os.path.basename(video_path)
    env_extra = {"PYTHONIOENCODING": "utf-8"}
    if modo_automatico:
        env_extra["MODO_AUTOMATICO"] = "1"

    _guardar_contexto_stream(video_path, contexto_stream)

    duracion_video = _duracion_video_segundos(video_path)
    ratio_historial, muestras_historial = _cargar_ratio_historial()
    estimado_total = duracion_video * ratio_historial if duracion_video else None
    t_inicio = time.time()

    _escribir_estado_progreso(nombre, 0, len(PASOS_PIPELINE), "Preparando...", t_inicio)
    lanzar_notificacion_progreso()

    pasos = [
        (
            script,
            (os.path.abspath(video_path) if script in {"detectar_eventos_audio.py", "analizar_video_visual.py"} else nombre)
            if usa_nombre else None,
            mensaje,
        )
        for script, usa_nombre, mensaje in PASOS_PIPELINE
    ]

    _evitar_suspension(True)
    try:
        for idx, (script, argumento, mensaje) in enumerate(pasos, start=1):
            transcurrido = time.time() - t_inicio
            eta = max(0, round(estimado_total - transcurrido)) if estimado_total else None
            _escribir_estado_progreso(nombre, idx, len(pasos), mensaje, t_inicio, eta_segundos=eta)
            notificar(f"[{nombre}] Paso {idx}/{len(pasos)}: {mensaje}")

            if _intentar_cache_etapa(video_path, script, idx, notificar):
                _registrar_metrica_paso(nombre, script, 0.0, "cache_hit")
                continue

            ok_paso, duracion_paso = correr_paso(script, argumento, env_extra)
            _registrar_metrica_paso(nombre, script, duracion_paso, "ok" if ok_paso else "error")
            if not ok_paso:
                notificar(f"[{nombre}] ERROR en {script}.")
                _escribir_estado_progreso(nombre, idx, len(pasos), f"ERROR en {script}",
                                           t_inicio, terminado=True, error=True)
                return False
            _guardar_cache_etapa(video_path, script)

        elapsed_total = time.time() - t_inicio
        if duracion_video and duracion_video > 0:
            _guardar_ratio_historial(elapsed_total / duracion_video, muestras_historial, ratio_historial)

        notificar(f"[{nombre}] Completado.")
        _escribir_estado_progreso(nombre, len(pasos), len(pasos), "Completado",
                                   t_inicio, eta_segundos=0, terminado=True)
        cache_mkclips.registrar_ejecucion_y_limpiar_si_corresponde(duracion_video, notificar)
        return True
    finally:
        _evitar_suspension(False)


def reanudar_ultimo_proceso(notificar=print):
    """
    Lee el ultimo estado guardado (estado_progreso.json) y, si quedo a
    medias (se cerro la ventana, se mato el proceso, fallo un paso), sigue
    desde el paso en el que se quedo - sin repetir pasos anteriores ya
    hechos (por ejemplo, no vuelve a transcribir si ya habia transcrito).

    Asume que el video sigue en CARPETA_STREAMS con el mismo nombre.
    Devuelve True/False, o None si no habia nada que reanudar.
    """
    estado = leer_estado_progreso()
    if not estado:
        notificar("No hay ningun proceso previo registrado (no existe estado_progreso.json).")
        return None

    if estado.get("terminado") and not estado.get("error"):
        notificar(f"El ultimo proceso (\"{estado.get('archivo')}\") ya habia terminado bien. Nada que reanudar.")
        return None

    nombre = estado.get("archivo")
    paso_guardado = estado.get("paso_actual", 1)
    video_path = os.path.join(CARPETA_STREAMS, nombre)

    if not os.path.exists(video_path):
        notificar(f"No se encontro el video original en la carpeta de streams: {video_path}")
        return False

    notificar(f"Reanudando \"{nombre}\" desde el paso {paso_guardado}/{len(PASOS_PIPELINE)} "
              f"(los pasos anteriores no se repiten)...")

    env_extra = {"PYTHONIOENCODING": "utf-8", "MODO_AUTOMATICO": "1"}
    t_inicio = time.time()
    lanzar_notificacion_progreso()

    pasos = [
        (
            script,
            (os.path.abspath(video_path) if script in {"detectar_eventos_audio.py", "analizar_video_visual.py"} else nombre)
            if usa_nombre else None,
            mensaje,
        )
        for script, usa_nombre, mensaje in PASOS_PIPELINE
    ]
    indice_inicio = max(0, paso_guardado - 1)

    for idx in range(indice_inicio, len(pasos)):
        script, argumento, mensaje = pasos[idx]
        _escribir_estado_progreso(nombre, idx + 1, len(pasos), mensaje, t_inicio)
        notificar(f"[{nombre}] Paso {idx + 1}/{len(pasos)}: {mensaje}")

        if _intentar_cache_etapa(video_path, script, idx + 1, notificar):
            _registrar_metrica_paso(nombre, script, 0.0, "cache_hit")
            continue

        ok_paso, duracion_paso = correr_paso(script, argumento, env_extra)
        _registrar_metrica_paso(nombre, script, duracion_paso, "ok" if ok_paso else "error")
        if not ok_paso:
            notificar(f"[{nombre}] ERROR en {script}.")
            _escribir_estado_progreso(nombre, idx + 1, len(pasos), f"ERROR en {script}",
                                       t_inicio, terminado=True, error=True)
            return False
        _guardar_cache_etapa(video_path, script)

    notificar(f"[{nombre}] Completado.")
    _escribir_estado_progreso(nombre, len(pasos), len(pasos), "Completado",
                               t_inicio, eta_segundos=0, terminado=True)
    return True


def _main_interactivo():
    archivos = listar_videos(CARPETA_STREAMS)
    if not archivos:
        print(f"No se encontró ningún video en: {CARPETA_STREAMS}")
        sys.exit(1)

    print("=== Procesar varios streams seguidos ===\n")
    print("Videos disponibles (mas reciente primero):\n")
    for idx, path in enumerate(archivos, start=1):
        print(f"  {idx}. {os.path.basename(path)}")

    print()
    seleccion = input(
        "Escribe los numeros de los streams a procesar, separados por coma (ej: 1,2,3,4): "
    ).strip()

    indices = []
    for parte in seleccion.split(","):
        parte = parte.strip()
        if parte.isdigit() and 1 <= int(parte) <= len(archivos):
            indices.append(int(parte) - 1)

    if not indices:
        print("No se selecciono ningun video valido, saliendo.")
        sys.exit(1)

    seleccionados = [archivos[i] for i in indices]

    print(f"\nSe van a procesar {len(seleccionados)} streams, en este orden:")
    for s in seleccionados:
        print(f"  - {os.path.basename(s)}")

    confirmar = input("\n¿Continuar? (s/n): ").strip().lower()
    if confirmar != "s":
        print("Cancelado.")
        sys.exit(0)

    exitosos = []
    fallidos = []

    for i, video_path in enumerate(seleccionados, start=1):
        nombre = os.path.basename(video_path)
        print(f"\n{'='*60}")
        print(f" STREAM {i}/{len(seleccionados)}: {nombre}")
        print(f"{'='*60}\n")

        ok = procesar_un_video(video_path, modo_automatico=False, notificar=print)

        if ok:
            exitosos.append(nombre)
            print(f"\n✔ Stream completado: {nombre}")
        else:
            fallidos.append(nombre)
            print("Se salta este stream y se continua con el siguiente.")

    print(f"\n{'='*60}")
    print(" RESUMEN FINAL")
    print(f"{'='*60}")
    print(f"Completados exitosamente ({len(exitosos)}):")
    for e in exitosos:
        print(f"  ✔ {e}")
    if fallidos:
        print(f"\nCon errores ({len(fallidos)}):")
        for f in fallidos:
            print(f"  ✘ {f}")
    print("\nRevisa la carpeta configurada de Clips para ver los resultados de cada stream.")


if __name__ == "__main__":
    _main_interactivo()
