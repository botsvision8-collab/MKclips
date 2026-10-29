import json
import os
import glob
import sys
import subprocess
import tempfile
import time
import contextlib
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

import procesar_multiples
import hardware_scheduler
from cache_mkclips import ensure_audio_cache

# Mantener vivos los handles de os.add_dll_directory().
# Si se pierden por garbage collection, Windows puede dejar de resolver las DLL
# cuando CTranslate2 intenta cargarlas.
_DLL_DIRECTORIOS_NVIDIA = []
_NVIDIA_DLLS_PREPARADAS = False

EXTENSIONES = ("*.mp4", "*.mkv", "*.mov", "*.avi")

MODELO_WHISPER = "large-v3"

try:
    from config import CARPETA_STREAMS, CONTEXTO_TRANSCRIPCION
except ImportError:
    print("ADVERTENCIA: no se encontro config.py, usando valores genericos.")
    print("Copia config_ejemplo.py como config.py y personalizalo.\n")
    CARPETA_STREAMS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "streams")
    CONTEXTO_TRANSCRIPCION = "Este es un directo de gaming en español."

try:
    from config import NUM_PROCESOS_TRANSCRIPCION
except ImportError:
    # En cuantos pedazos se parte el audio para transcribir en paralelo.
    # Solo aplica si NO se usa GPU (ver USAR_GPU_TRANSCRIPCION abajo).
    NUM_PROCESOS_TRANSCRIPCION = 3

try:
    from config import USAR_GPU_TRANSCRIPCION
except ImportError:
    USAR_GPU_TRANSCRIPCION = True

CONTEXTO_INICIAL = CONTEXTO_TRANSCRIPCION

# Frases que Whisper "alucina" (inventa) sobre todo en tramos de silencio,
# musica, o audio de baja confianza. Si aparecen, se descarta ese segmento
# por completo (no es contenido real).
HALLUCINACIONES_CONOCIDAS = [
    "amara.org",
    "subtitulos por la comunidad",
    "subtítulos por la comunidad",
    "subtitles by the amara",
    "www.euronews.com",
    "gracias por ver el video",
    "suscribete",
]

CORRECCIONES = {
    # "palabra mal transcrita": "palabra correcta",
}


def encontrar_video_mas_reciente(carpeta):
    archivos = []
    for ext in EXTENSIONES:
        archivos.extend(glob.glob(os.path.join(carpeta, ext)))
    archivos.sort(key=os.path.getmtime, reverse=True)
    return archivos


def elegir_video_interactivo(carpeta):
    archivos = encontrar_video_mas_reciente(carpeta)
    if not archivos:
        raise FileNotFoundError(f"No se encontró ningún video en: {carpeta}")

    print("Videos disponibles en la carpeta (mas reciente primero):\n")
    for idx, path in enumerate(archivos, start=1):
        print(f"  {idx}. {os.path.basename(path)}")

    print()
    seleccion = input("Elige un numero (o presiona Enter para usar el mas reciente): ").strip()
    if seleccion == "":
        return archivos[0]
    if seleccion.isdigit() and 1 <= int(seleccion) <= len(archivos):
        return archivos[int(seleccion) - 1]

    print("Seleccion invalida, se usa el mas reciente por defecto.")
    return archivos[0]


def resolver_video_path(argumento):
    if argumento:
        if os.path.isabs(argumento) and os.path.exists(argumento):
            return argumento
        candidato = os.path.join(CARPETA_STREAMS, argumento)
        if os.path.exists(candidato):
            return candidato
        raise FileNotFoundError(f"No se encontró el archivo especificado: {argumento}")
    return elegir_video_interactivo(CARPETA_STREAMS)


def aplicar_correcciones(texto, correcciones):
    for mal, bien in correcciones.items():
        texto = texto.replace(mal, bien)
    return texto


def es_alucinacion(texto):
    texto_lower = texto.lower()
    return any(frase in texto_lower for frase in HALLUCINACIONES_CONOCIDAS)


def _gpu_disponible():
    """Best-effort: hay una GPU NVIDIA (CUDA) que ctranslate2 puede usar."""
    _agregar_rutas_dll_nvidia()
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _agregar_rutas_dll_nvidia():
    """Prepara DLL NVIDIA una sola vez. nvjitlink es opcional en este entorno."""
    if os.name != "nt":
        return True
    global _DLL_DIRECTORIOS_NVIDIA, _NVIDIA_DLLS_PREPARADAS
    if _NVIDIA_DLLS_PREPARADAS:
        return True
    try:
        import importlib.util
        requeridos = ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime")
        opcionales = ("nvidia.nvjitlink",)
        rutas_agregadas = []
        faltantes = []
        for paquete in requeridos + opcionales:
            spec = importlib.util.find_spec(paquete)
            if not spec or not spec.submodule_search_locations:
                if paquete in requeridos:
                    faltantes.append(paquete)
                continue
            carpeta_base = list(spec.submodule_search_locations)[0]
            carpeta_bin = os.path.join(carpeta_base, "bin")
            if not os.path.isdir(carpeta_bin):
                if paquete in requeridos:
                    faltantes.append(paquete)
                continue
            if carpeta_bin not in rutas_agregadas:
                rutas_agregadas.append(carpeta_bin)
                _DLL_DIRECTORIOS_NVIDIA.append(os.add_dll_directory(carpeta_bin))
                os.environ["PATH"] = carpeta_bin + os.pathsep + os.environ.get("PATH", "")
        _NVIDIA_DLLS_PREPARADAS = bool(rutas_agregadas)
        if faltantes:
            print("[GPU] Faltan paquetes NVIDIA requeridos: " + ", ".join(faltantes))
            return False
        if rutas_agregadas:
            print(f"[GPU] DLL NVIDIA preparadas ({len(rutas_agregadas)} rutas).")
        return True
    except Exception as e:
        print(f"[GPU] Error preparando DLL NVIDIA: {e}")
        return False


def _cargar_whisper_model(device="cpu", compute_type="int8", cpu_threads=None):
    """
    Carga WhisperModel solo DESPUES de preparar CUDA cuando corresponde.
    """
    if device == "cuda":
        _agregar_rutas_dll_nvidia()

    # Import tardio intencional: CTranslate2 debe ver las DLL antes de cargarse.
    from faster_whisper import WhisperModel

    kwargs = {
        "device": device,
        "compute_type": compute_type,
    }

    if device == "cpu" and cpu_threads is not None:
        kwargs["cpu_threads"] = cpu_threads

    return WhisperModel(MODELO_WHISPER, **kwargs)


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


def _extraer_audio_segmento(video_path, inicio, fin, salida_wav):
    comando = ["ffmpeg", "-y", "-ss", str(inicio)]
    if fin is not None:
        comando += ["-to", str(fin)]
    comando += ["-i", video_path, "-vn", "-ac", "1", "-ar", "16000", salida_wav]
    subprocess.run(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _transcribir_segmento(tarea):
    """
    Corre en un proceso APARTE (para paralelismo real en CPU): transcribe
    un pedazo de audio y devuelve los segmentos con el offset de tiempo ya
    sumado. No imprime nada linea por linea (el resultado solo vuelve
    cuando el pedazo entero termina).
    """
    ruta_audio, offset, contexto, hilos_cpu = tarea
    modelo = _cargar_whisper_model(device="cpu", compute_type="int8", cpu_threads=hilos_cpu)
    segments, _info = modelo.transcribe(
        ruta_audio, word_timestamps=False, language="es", vad_filter=True,
        initial_prompt=contexto, condition_on_previous_text=True,
        beam_size=5, best_of=5,
    )
    resultado = []
    for seg in segments:
        texto_limpio = seg.text.strip()
        if not texto_limpio or texto_limpio in [".", "...", ",", "-"]:
            continue
        if es_alucinacion(texto_limpio):
            continue
        texto_limpio = aplicar_correcciones(texto_limpio, CORRECCIONES)
        resultado.append({
            "inicio": round(seg.start + offset, 2),
            "fin": round(seg.end + offset, 2),
            "texto": texto_limpio,
        })
    return resultado


def _transcribir_secuencial_con_print(video_path, contexto, hilos_cpu, device="cpu", compute_type="int8"):
    """Un solo proceso, muestra cada linea segun se transcribe. Se usa
    siempre que hay GPU (rapido Y en vivo), o en CPU cuando
    NUM_PROCESOS_TRANSCRIPCION=1."""
    duracion_total = _duracion_video_segundos(video_path)

    resultado = []
    descartados = 0

    slot_gpu = hardware_scheduler.gpu_slot("whisper") if device == "cuda" else contextlib.nullcontext()
    with slot_gpu:
        modelo = _cargar_whisper_model(
            device=device,
            compute_type=compute_type,
            cpu_threads=hilos_cpu,
        )
        segments, _info = modelo.transcribe(
            video_path, word_timestamps=False, language="es", vad_filter=True,
            initial_prompt=contexto, condition_on_previous_text=True,
            beam_size=5, best_of=5,
        )
        for seg in segments:
            texto_limpio = seg.text.strip()
            if not texto_limpio or texto_limpio in [".", "...", ",", "-"]:
                continue
            if es_alucinacion(texto_limpio):
                descartados += 1
                continue
            texto_limpio = aplicar_correcciones(texto_limpio, CORRECCIONES)
            resultado.append({"inicio": round(seg.start, 2), "fin": round(seg.end, 2), "texto": texto_limpio})

            if duracion_total:
                porcentaje = max(0, min(99, round(100 * seg.end / duracion_total)))
                procesar_multiples.actualizar_porcentaje_progreso(porcentaje, f"Transcribiendo... {porcentaje}%")
                print(f"[{seg.start:.1f}s -> {seg.end:.1f}s] {seg.text}")
                print(f"  {procesar_multiples._barra_texto(porcentaje)}")
            else:
                print(f"[{seg.start:.1f}s -> {seg.end:.1f}s] {seg.text}")

    if descartados:
        print(f"({descartados} segmento(s) descartados por parecer alucinaciones de Whisper)")
    return resultado


def transcribir_video(video_path, num_procesos=NUM_PROCESOS_TRANSCRIPCION, notificar=print):
    """
    Si hay GPU NVIDIA (CUDA) disponible y USAR_GPU_TRANSCRIPCION esta
    activo: transcribe TODO de una en la GPU (mucho mas rapido que CPU, y
    ademas con texto en vivo - no hace falta partir el video). Si algo
    falla al usar la GPU (ej: faltan librerias cuDNN/cuBLAS), cae solo a
    CPU sin interrumpir el proceso.

    Si no hay GPU (o esta desactivada): igual que antes - num_procesos<=1
    transcribe en un solo proceso con texto en vivo; num_procesos>1 parte
    el audio cacheado en pedazos y los transcribe en paralelo en CPU.
    """
    audio_cache = ensure_audio_cache(video_path, notificar=notificar)

    if USAR_GPU_TRANSCRIPCION and _gpu_disponible():
        try:
            notificar("GPU NVIDIA (CUDA) detectada - transcribiendo con la tarjeta grafica "
                      "(rapido y en vivo, sin partir el video)...")
            return _transcribir_secuencial_con_print(
                audio_cache, CONTEXTO_INICIAL, os.cpu_count() or 1,
                device="cuda", compute_type="float16",
            )
        except Exception as e:
            notificar(f"No se pudo usar la GPU ({e}). Revisa que esten instaladas las "
                      "librerias: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12")
            notificar("Cayendo de vuelta a CPU...")

    n = max(1, min(num_procesos, os.cpu_count() or 1))
    n_seguro = procesar_multiples.calcular_max_procesos_transcripcion_seguro()
    if n > n_seguro:
        notificar(f"Se pidieron {num_procesos} procesos paralelos, pero se bajo a {n_seguro} "
                  f"(limite seguro segun tus nucleos y RAM libre - mas que eso puede colgar la PC).")
        n = n_seguro
    # ``n`` es el presupuesto total elegido para CPU. No entregar todos los
    # hilos logicos a CTranslate2 cuando el usuario eligio menos.
    hilos_totales = n

    if n <= 1:
        notificar("Transcribiendo en un solo proceso (con texto en vivo)...")
        return _transcribir_secuencial_con_print(audio_cache, CONTEXTO_INICIAL, hilos_totales)

    duracion = _duracion_video_segundos(video_path)
    if not duracion or duracion < 120:
        notificar("Video corto, no vale la pena partirlo - transcribiendo en un solo proceso...")
        return _transcribir_secuencial_con_print(audio_cache, CONTEXTO_INICIAL, hilos_totales)

    hilos_por_worker = max(1, hilos_totales // n)
    duracion_pedazo = duracion / n

    carpeta_temp = tempfile.mkdtemp(prefix="transcribir_")
    tareas = []
    for i in range(n):
        inicio = i * duracion_pedazo
        fin = None if i == n - 1 else (i + 1) * duracion_pedazo
        ruta_audio = os.path.join(carpeta_temp, f"pedazo_{i}.wav")
        notificar(f"Extrayendo audio del pedazo {i + 1}/{n}...")
        _extraer_audio_segmento(audio_cache, inicio, fin, ruta_audio)
        tareas.append((ruta_audio, inicio, CONTEXTO_INICIAL, hilos_por_worker))

    notificar(f"Transcribiendo {n} pedazos en paralelo ({hilos_por_worker} hilo(s) de CPU c/u)...")
    resultados_por_pedazo = [None] * n
    pendientes = set()
    with ProcessPoolExecutor(max_workers=n) as executor:
        futuros = {executor.submit(_transcribir_segmento, tarea): idx for idx, tarea in enumerate(tareas)}
        pendientes = set(futuros.keys())
        t_espera = time.time()

        while pendientes:
            completados, pendientes = wait(pendientes, timeout=15, return_when=FIRST_COMPLETED)

            if not completados:
                minutos = (time.time() - t_espera) / 60
                notificar(f"Sigue transcribiendo... ({minutos:.1f} min transcurridos, "
                          f"{len(pendientes)}/{n} pedazo(s) todavia trabajando)")
                continue

            for futuro in completados:
                idx = futuros[futuro]
                resultados_por_pedazo[idx] = futuro.result()
                completados_total = sum(1 for r in resultados_por_pedazo if r is not None)
                porcentaje = round(100 * completados_total / n)
                procesar_multiples.actualizar_porcentaje_progreso(
                    porcentaje, f"Transcribiendo... {completados_total}/{n} pedazos listos"
                )
                notificar(f"Pedazo {idx + 1}/{n} listo. {procesar_multiples._barra_texto(porcentaje)}")

    for ruta_audio, *_ in tareas:
        try:
            os.remove(ruta_audio)
        except OSError:
            pass
    try:
        os.rmdir(carpeta_temp)
    except OSError:
        pass

    combinado = [seg for pedazo in resultados_por_pedazo for seg in pedazo]
    combinado.sort(key=lambda s: s["inicio"])
    return combinado


def _main():
    argumento_cli = sys.argv[1] if len(sys.argv) > 1 else None
    video_path = resolver_video_path(argumento_cli)

    print(f"\nVideo seleccionado: {video_path}")
    print(f"Modelo Whisper: {MODELO_WHISPER}")
    print(f"Procesos paralelos: {NUM_PROCESOS_TRANSCRIPCION}\n")

    nombre_video = os.path.splitext(os.path.basename(video_path))[0]
    with open("ultimo_video.txt", "w", encoding="utf-8") as f:
        f.write(video_path + "\n" + nombre_video)

    t_inicio = time.time()
    resultado = transcribir_video(video_path, notificar=print)
    print(f"\nTranscripcion terminada en {time.time() - t_inicio:.0f}s.")

    with open("transcripcion.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    from cache_mkclips import guardar_identidad_artefacto
    guardar_identidad_artefacto("transcripcion.json", video_path, "transcripcion")

    print(f"\nListo. {len(resultado)} segmentos guardados en transcripcion.json")
    print(f"Video procesado: {nombre_video}")


if __name__ == "__main__":
    _main()
