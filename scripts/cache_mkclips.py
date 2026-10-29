import hashlib
import json
import os
import subprocess
import tempfile
from functools import lru_cache

CACHE_VERSION = 1
try:
    from .rutas_app import datos_dir
except ImportError:
    from rutas_app import datos_dir
CACHE_ROOT = os.path.join(str(datos_dir()), ".mkclips_cache")
AUDIO_CACHE_DIR = os.path.join(CACHE_ROOT, "audio")
STAGE_CACHE_DIR = os.path.join(CACHE_ROOT, "stages")
FINGERPRINT_VERSION = 1

CONTADOR_EJECUCIONES_PATH = os.path.join(CACHE_ROOT, "contador_ejecuciones.json")
UMBRAL_EJECUCIONES_PEQUENAS = 3
UMBRAL_EJECUCIONES_GRANDES = 2
DURACION_CORTE_GRANDE_SEGUNDOS = 30 * 60  # 30 min: por debajo es "pequeña", por encima "grande"


def _mkdir(path):
    os.makedirs(path, exist_ok=True)


def _sha256_file_edges(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        h.update(f.read(chunk_size))
        if size > chunk_size:
            f.seek(max(0, size - chunk_size))
            h.update(f.read(chunk_size))
    return h.hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


@lru_cache(maxsize=16)
def _fingerprint_cached(ruta_normalizada, size, mtime_ns):
    """Calcula la huella una sola vez por versión física del archivo dentro del proceso."""
    duracion = None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", ruta_normalizada],
            capture_output=True, text=True, check=False
        )
        duracion = round(float(r.stdout.strip()), 3)
    except Exception:
        pass

    payload = {
        "version": FINGERPRINT_VERSION,
        "size": size,
        "mtime_ns": mtime_ns,
        "duration": duracion,
        "edge_sha256": _sha256_file_edges(ruta_normalizada),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), payload


def fingerprint_video(video_path):
    """Huella estable: evita repetir ffprobe y SHA de extremos en la misma ejecución."""
    ruta = os.path.abspath(os.fspath(video_path))
    stat = os.stat(ruta)
    return _fingerprint_cached(ruta, stat.st_size, stat.st_mtime_ns)


def identidad_fuente(video_path):
    """Identidad que acompaña artefactos reutilizables entre etapas.

    Se mantiene fuera de los JSON de datos para conservar sus contratos de
    lista existentes; cada ``<artefacto>.meta.json`` es inseparable del dato.
    """
    ruta = os.path.normcase(os.path.normpath(os.path.abspath(video_path)))
    fingerprint, datos = fingerprint_video(video_path)
    return {
        "ruta_normalizada": ruta,
        "duracion_ffprobe": datos["duration"],
        "fingerprint": fingerprint,
        "fingerprint_version": FINGERPRINT_VERSION,
    }


def guardar_identidad_artefacto(ruta_artefacto, video_path, etapa):
    meta = {"etapa": etapa, "fuente": identidad_fuente(video_path)}
    ruta_meta = ruta_artefacto + ".meta.json"
    temporal = ruta_meta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(meta, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta_meta)
    return meta


def exigir_identidad_artefacto(ruta_artefacto, video_path, etapa=None):
    """Evita que una etapa consuma resultados de otro stream silenciosamente."""
    ruta_meta = ruta_artefacto + ".meta.json"
    if not os.path.exists(ruta_meta):
        raise RuntimeError(f"Falta proveniencia para {ruta_artefacto}: {ruta_meta}")
    with open(ruta_meta, "r", encoding="utf-8") as archivo:
        meta = json.load(archivo)
    actual = identidad_fuente(video_path)
    if etapa and meta.get("etapa") != etapa:
        raise RuntimeError(f"Etapa invalida para {ruta_artefacto}: {meta.get('etapa')!r}")
    if meta.get("fuente") != actual:
        raise RuntimeError(
            f"Proveniencia no coincide para {ruta_artefacto}; se rechaza mezclar streams."
        )
    return actual


def cache_dir_for_video(video_path):
    fingerprint, metadata = fingerprint_video(video_path)
    path = os.path.join(CACHE_ROOT, fingerprint)
    _mkdir(path)
    ruta_fingerprint = os.path.join(path, "fingerprint.json")
    if not os.path.exists(ruta_fingerprint):
        temporal = ruta_fingerprint + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        os.replace(temporal, ruta_fingerprint)
    return path, fingerprint


def audio_cache_path(video_path):
    _mkdir(AUDIO_CACHE_DIR)
    fingerprint, _ = fingerprint_video(video_path)
    base = os.path.splitext(os.path.basename(video_path))[0]
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)[:100]
    return os.path.join(AUDIO_CACHE_DIR, f"{safe}_{fingerprint[:16]}.wav")


def stage_cache_dir(video_path):
    path, _ = cache_dir_for_video(video_path)
    return path


def cached_stage_path(video_path, filename):
    return os.path.join(stage_cache_dir(video_path), filename)


def _stage_snapshot_dir(video_path, etapa):
    fingerprint, _ = fingerprint_video(video_path)
    return os.path.join(STAGE_CACHE_DIR, fingerprint, etapa)


def _json_valido(ruta, etapa):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False

    nombre = os.path.basename(ruta)
    if nombre == "contexto_stream.json":
        return (
            isinstance(datos, dict)
            and datos.get("version") == 1
            and isinstance(datos.get("contexto"), str)
            and isinstance(datos.get("fuente"), dict)
        )
    if nombre.startswith("metricas_") or nombre in {"scores_clips.json", "resumen_plan.json"}:
        return isinstance(datos, dict)
    if etapa == "transcripcion":
        return isinstance(datos, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("texto"), str)
            and float(item["fin"]) > float(item["inicio"])
            for item in datos
        )
    if etapa == "eventos_audio":
        return isinstance(datos, list) and all(
            isinstance(item, dict) and float(item["fin"]) > float(item["inicio"])
            for item in datos
        )
    if etapa == "eventos_visuales":
        return isinstance(datos, list) and all(
            isinstance(item, dict)
            and item.get("tipo") == "cambio_visual"
            and float(item["fin"]) >= float(item["inicio"])
            for item in datos
        )
    if etapa == "identificacion" and nombre in {"candidatos_todos.json", "candidatos_cortos.json"}:
        return isinstance(datos, list) and all(
            isinstance(item, dict) and float(item["fin"]) >= float(item["inicio"])
            for item in datos
        )
    if etapa == "identificacion" and nombre == "clips_sugeridos.json":
        return isinstance(datos, list) and all(
            isinstance(item, dict)
            and isinstance(item.get("segmentos"), list)
            and item["segmentos"]
            and float(item["fin"]) >= float(item["inicio"])
            for item in datos
        )
    return isinstance(datos, (dict, list))


def _dependencias_digest(dependencias):
    raw = json.dumps(dependencias or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _copiar_atomico(origen, destino):
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    temporal = destino + ".tmp"
    with open(origen, "rb") as fuente, open(temporal, "wb") as salida:
        for bloque in iter(lambda: fuente.read(1024 * 1024), b""):
            salida.write(bloque)
    os.replace(temporal, destino)


def guardar_cache_etapa(video_path, etapa, artefactos, dependencias=None):
    """Guarda una instantanea validable de los artefactos de una etapa."""
    carpeta = _stage_snapshot_dir(video_path, etapa)
    os.makedirs(carpeta, exist_ok=True)
    archivos = []
    for ruta in artefactos:
        ruta = os.path.abspath(ruta)
        if not os.path.isfile(ruta):
            destino = os.path.join(carpeta, os.path.basename(ruta))
            try:
                os.remove(destino)
            except FileNotFoundError:
                pass
            archivos.append({"nombre": os.path.basename(ruta), "ausente": True})
            continue
        destino = os.path.join(carpeta, os.path.basename(ruta))
        _copiar_atomico(ruta, destino)
        archivos.append({
            "nombre": os.path.basename(ruta),
            "sha256": _sha256_file(ruta),
            "size": os.path.getsize(ruta),
        })
    if not any(not item.get("ausente") for item in archivos):
        return False
    fuente = identidad_fuente(video_path)
    _, fuente_datos = fingerprint_video(video_path)
    meta = {
        "cache_version": CACHE_VERSION,
        "etapa": etapa,
        "fuente": fuente,
        "fuente_datos": fuente_datos,
        "dependencias": dependencias or {},
        "dependencias_digest": _dependencias_digest(dependencias),
        "archivos": archivos,
    }
    ruta_meta = os.path.join(carpeta, "cache_meta.json")
    temporal = ruta_meta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(meta, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta_meta)
    return True


def validar_cache_etapa(video_path, etapa, artefactos, dependencias=None):
    """Valida una instantanea completa; nunca acepta solo por existir."""
    carpeta = _stage_snapshot_dir(video_path, etapa)
    ruta_meta = os.path.join(carpeta, "cache_meta.json")
    try:
        with open(ruta_meta, "r", encoding="utf-8") as archivo:
            meta = json.load(archivo)
        fuente = identidad_fuente(video_path)
        _, fuente_datos = fingerprint_video(video_path)
        if meta.get("cache_version") != CACHE_VERSION:
            return False
        if meta.get("etapa") != etapa or meta.get("fuente") != fuente:
            return False
        if meta.get("fuente_datos") != fuente_datos:
            return False
        if meta.get("dependencias_digest") != _dependencias_digest(dependencias):
            return False
        registrados = {item["nombre"]: item for item in meta.get("archivos", [])}
        for ruta in artefactos:
            nombre = os.path.basename(os.path.abspath(ruta))
            cacheado = os.path.join(carpeta, nombre)
            registro = registrados.get(nombre)
            if not registro:
                return False
            if registro.get("ausente"):
                if os.path.exists(cacheado):
                    return False
                continue
            if not os.path.isfile(cacheado):
                return False
            if os.path.getsize(cacheado) != registro.get("size"):
                return False
            if _sha256_file(cacheado) != registro.get("sha256"):
                return False
            if nombre.endswith(".json") and not nombre.endswith(".meta.json") and not _json_valido(cacheado, etapa):
                return False
            if nombre.endswith(".meta.json"):
                with open(cacheado, "r", encoding="utf-8") as meta_artefacto:
                    datos_meta = json.load(meta_artefacto)
                if datos_meta.get("fuente") != fuente:
                    return False
            if nombre == "contexto_stream.json":
                with open(cacheado, "r", encoding="utf-8") as contexto_artefacto:
                    datos_contexto = json.load(contexto_artefacto)
                if datos_contexto.get("fuente") != fuente:
                    return False
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return False
    return True


def restaurar_cache_etapa(video_path, etapa, artefactos):
    """Restaura una instantanea previamente validada en sus rutas activas."""
    carpeta = _stage_snapshot_dir(video_path, etapa)
    with open(os.path.join(carpeta, "cache_meta.json"), "r", encoding="utf-8") as archivo:
        meta = json.load(archivo)
    ausentes = {
        item["nombre"] for item in meta.get("archivos", []) if item.get("ausente")
    }
    for ruta in artefactos:
        destino = os.path.abspath(ruta)
        if os.path.basename(destino) in ausentes:
            try:
                os.remove(destino)
            except FileNotFoundError:
                pass
            continue
        origen = os.path.join(carpeta, os.path.basename(destino))
        _copiar_atomico(origen, destino)
    return True


def ensure_audio_cache(video_path, notificar=print):
    """Extrae una sola vez el WAV 16k mono compartido por Whisper y detector."""
    salida = audio_cache_path(video_path)
    if os.path.exists(salida) and os.path.getsize(salida) > 1024:
        notificar(f"Audio en caché reutilizado: {salida}")
        return salida

    tmp_fd, tmp = tempfile.mkstemp(prefix="mkclips_audio_", suffix=".wav")
    os.close(tmp_fd)
    try:
        notificar("Extrayendo audio una sola vez para la caché compartida...")
        resultado = subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", tmp
        ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if resultado.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) <= 1024:
            raise RuntimeError("FFmpeg no pudo crear la caché de audio.")
        os.replace(tmp, salida)
        return salida
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _cargar_contador_ejecuciones():
    if os.path.exists(CONTADOR_EJECUCIONES_PATH):
        try:
            with open(CONTADOR_EJECUCIONES_PATH, "r", encoding="utf-8") as f:
                datos = json.load(f)
                return {"pequenas": int(datos.get("pequenas", 0)), "grandes": int(datos.get("grandes", 0))}
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return {"pequenas": 0, "grandes": 0}


def _guardar_contador_ejecuciones(contador):
    _mkdir(CACHE_ROOT)
    with open(CONTADOR_EJECUCIONES_PATH, "w", encoding="utf-8") as f:
        json.dump(contador, f)


def limpiar_cache_audio(notificar=print):
    """Borra todo lo que haya en la cache de audio compartida. Se
    regenera solo en la siguiente vez que haga falta (ensure_audio_cache)."""
    if not os.path.isdir(AUDIO_CACHE_DIR):
        return
    borrados = 0
    liberado_bytes = 0
    for nombre in os.listdir(AUDIO_CACHE_DIR):
        ruta = os.path.join(AUDIO_CACHE_DIR, nombre)
        try:
            liberado_bytes += os.path.getsize(ruta)
            os.remove(ruta)
            borrados += 1
        except OSError:
            pass
    if borrados:
        notificar(f"Cache de audio limpiada: {borrados} archivo(s), "
                  f"{liberado_bytes / (1024 * 1024):.0f} MB liberados.")


def registrar_ejecucion_y_limpiar_si_corresponde(duracion_video_segundos, notificar=print):
    """
    Cuenta ejecuciones del pipeline, separando 'pequeñas' (video de menos
    de 30 minutos) de 'grandes' (30 minutos o mas). Cada
    UMBRAL_EJECUCIONES_PEQUENAS pequeñas, o cada UMBRAL_EJECUCIONES_GRANDES
    grandes (lo que se cumpla primero), limpia la cache de audio
    compartida para que no crezca sin límite.

    Llamar UNA vez por video, al final de procesar_un_video - despues de
    que transcribir.py y detectar_eventos_audio.py ya usaron esa cache
    para este video, asi no se borra nada que todavia hiciera falta en
    esta misma corrida.
    """
    contador = _cargar_contador_ejecuciones()
    es_grande = bool(duracion_video_segundos and duracion_video_segundos >= DURACION_CORTE_GRANDE_SEGUNDOS)

    if es_grande:
        contador["grandes"] += 1
    else:
        contador["pequenas"] += 1

    limpiar = False
    if contador["pequenas"] >= UMBRAL_EJECUCIONES_PEQUENAS:
        limpiar = True
        contador["pequenas"] = 0
    if contador["grandes"] >= UMBRAL_EJECUCIONES_GRANDES:
        limpiar = True
        contador["grandes"] = 0

    if limpiar:
        limpiar_cache_audio(notificar)

    _guardar_contador_ejecuciones(contador)
