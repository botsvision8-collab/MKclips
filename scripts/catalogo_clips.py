# -*- coding: utf-8 -*-
"""Catálogo de clips de TODOS los streams procesados.

``clips_sugeridos.json`` se sobrescribe con cada stream, así que no sirve para
revisar clips de varios streams. Este catálogo (``catalogo_clips.json`` en la
carpeta de resultados) acumula los clips que el pipeline renderiza y la pestaña
"Validar clips" lo usa como fuente. Los clips de streams anteriores al
catálogo se recuperan escaneando la carpeta de clips.

Además contiene las utilidades de duración real de un archivo y el recorte de
un clip que supera el máximo configurado.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata

cv2 = None
_CV2_INTENTADO = False

def _obtener_cv2():
    """Carga OpenCV solo cuando una operaci?n de video realmente lo necesita."""
    global cv2, _CV2_INTENTADO
    if not _CV2_INTENTADO:
        _CV2_INTENTADO = True
        try:
            import cv2 as modulo_cv2
            cv2 = modulo_cv2
        except Exception:  # pragma: no cover - depende del entorno
            cv2 = None
    return cv2

NOMBRE_CATALOGO = "catalogo_clips.json"
EXTENSIONES_VIDEO = (".mkv", ".mp4", ".mov", ".webm", ".avi")
_SIN_VENTANA = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def abrir_captura(ruta):
    """VideoCapture forzando el backend FFmpeg (el de Media Foundation busca mal
    en MKV/HEVC). En Windows reintenta con la ruta corta 8.3 si el nombre tiene
    caracteres que OpenCV no sabe abrir."""
    modulo_cv2 = _obtener_cv2()
    if modulo_cv2 is None:
        raise RuntimeError("OpenCV no est? disponible para abrir este video.")
    cap = modulo_cv2.VideoCapture(ruta, modulo_cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap.release()
        cap = modulo_cv2.VideoCapture(ruta)
    if not cap.isOpened() and os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.kernel32.GetShortPathNameW(os.path.abspath(ruta), buf, len(buf)):
                cap.release()
                cap = modulo_cv2.VideoCapture(buf.value, modulo_cv2.CAP_FFMPEG)
        except Exception:
            pass
    return cap


def _clave(ruta):
    return os.path.normcase(os.path.abspath(ruta))


def ruta_catalogo(resultados_dir):
    return os.path.join(resultados_dir, NOMBRE_CATALOGO)


def cargar_catalogo(resultados_dir):
    try:
        with open(ruta_catalogo(resultados_dir), "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return [e for e in datos if isinstance(e, dict) and e.get("ruta_archivo")] if isinstance(datos, list) else []
    except (OSError, ValueError):
        return []


def guardar_catalogo(resultados_dir, entradas):
    os.makedirs(resultados_dir, exist_ok=True)
    destino = ruta_catalogo(resultados_dir)
    temporal = f"{destino}.{os.getpid()}.tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(entradas, archivo, ensure_ascii=False, indent=1, default=str)
    os.replace(temporal, destino)


def leer_contexto_juego(resultados_dir):
    """{"juego", "situacion"} del ultimo stream analizado (juego_contexto.json), o None."""
    try:
        with open(os.path.join(resultados_dir, "juego_contexto.json"), "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return {"juego": datos.get("juego") or "desconocido", "situacion": datos.get("situacion") or "incierta"}
    except (OSError, ValueError, AttributeError):
        return None


def registrar_clips(resultados_dir, clips, fuente=None, stream="", contexto_juego=None):
    """Agrega (o actualiza por ruta) los clips ya renderizados de un stream.

    ``contexto_juego`` = juego y situacion del stream: se guarda con cada clip porque
    juego_contexto.json se sobrescribe con cada stream y despues no se podria saber."""
    entradas = {_clave(e["ruta_archivo"]): e for e in cargar_catalogo(resultados_dir)}
    for clip in clips or []:
        ruta = clip.get("ruta_archivo") or clip.get("archivo")
        if not ruta or not os.path.isfile(ruta):
            continue
        limpio = {k: v for k, v in clip.items() if not str(k).startswith("_")}
        limpio["ruta_archivo"] = limpio["archivo"] = str(ruta)
        entradas[_clave(ruta)] = {
            "ruta_archivo": str(ruta), "stream": stream or os.path.basename(os.path.dirname(ruta)),
            "fuente": fuente if isinstance(fuente, dict) else None, "clip": limpio,
            "contexto_juego": contexto_juego if isinstance(contexto_juego, dict) else None,
        }
    guardar_catalogo(resultados_dir, list(entradas.values()))


def quitar_clips(resultados_dir, rutas):
    """Quita rutas del catálogo (no borra archivos)."""
    quitar = {_clave(r) for r in rutas}
    if not quitar:
        return
    restantes = [e for e in cargar_catalogo(resultados_dir) if _clave(e["ruta_archivo"]) not in quitar]
    guardar_catalogo(resultados_dir, restantes)


# ----------------------------------------------------------------------
# Duración real y recorte
# ----------------------------------------------------------------------
def duracion_archivo(ruta):
    """Duración real en segundos (0.0 si no se puede leer)."""
    modulo_cv2 = _obtener_cv2()
    if modulo_cv2 is not None:
        cap = abrir_captura(ruta)
        try:
            if cap.isOpened():
                fps = cap.get(modulo_cv2.CAP_PROP_FPS) or 0
                total = cap.get(modulo_cv2.CAP_PROP_FRAME_COUNT) or 0
                if fps > 0 and total > 0:
                    return float(total) / float(fps)
        finally:
            cap.release()
    try:
        salida = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", ruta],
            capture_output=True, text=True, timeout=30, check=False, creationflags=_SIN_VENTANA,
        )
        return float(salida.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def duracion_ffprobe(ruta):
    """Duración del contenedor según ffprobe (la que usan los reproductores)."""
    try:
        salida = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", ruta],
            capture_output=True, text=True, timeout=30, check=False, creationflags=_SIN_VENTANA,
        )
        return float(salida.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def recortar_a_maximo(ruta, maximo, margen=0.15):
    """Recorta ``ruta`` para que dure como máximo ``maximo`` s (quita el final).

    Copia los flujos sin recodificar, así que es rápido y no pierde calidad.
    Devuelve ``(ok, duracion_final)``; ``ok`` es True si el archivo ya cumplía o
    quedó dentro del límite. Si no se logra, el archivo original queda intacto.
    """
    maximo = float(maximo or 0)
    if maximo <= 0:
        return True, duracion_ffprobe(ruta)
    actual = duracion_ffprobe(ruta)
    if 0 < actual <= maximo:
        return True, actual
    objetivo = max(0.5, maximo - margen)
    carpeta = os.path.dirname(os.path.abspath(ruta))
    extension = os.path.splitext(ruta)[1] or ".mkv"
    descriptor, temporal = tempfile.mkstemp(suffix=extension, prefix=".recorte_", dir=carpeta)
    os.close(descriptor)
    try:
        resultado = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", ruta, "-t", f"{objetivo:.3f}",
             "-map", "0", "-c", "copy", "-map_metadata", "0", temporal],
            capture_output=True, text=True, check=False, creationflags=_SIN_VENTANA,
        )
        nueva = duracion_ffprobe(temporal) if resultado.returncode == 0 else 0.0
        if resultado.returncode != 0 or not (0 < nueva <= maximo):
            return False, actual
        os.replace(temporal, ruta)
        return True, nueva
    except OSError:
        return False, actual
    finally:
        if os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass


# ----------------------------------------------------------------------
# Streams anteriores al catálogo
# ----------------------------------------------------------------------
def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def _titulo_desde_archivo(ruta):
    base = os.path.splitext(os.path.basename(ruta))[0]
    base = re.sub(r"^\d+_", "", base)
    base = re.sub(r"_\d+$", "", base)
    return base.replace("_", " ").strip() or os.path.basename(ruta)


def escanear_carpeta_clips(carpeta_base):
    """Rutas de video dentro de ``carpeta_base`` (un nivel de subcarpetas)."""
    if not carpeta_base or not os.path.isdir(carpeta_base):
        return []
    encontrados = []
    for raiz, directorios, archivos in os.walk(carpeta_base):
        profundidad = os.path.relpath(raiz, carpeta_base).count(os.sep)
        if raiz != carpeta_base and profundidad >= 1:
            directorios[:] = []
        directorios[:] = [d for d in directorios if not d.startswith(".")]
        for nombre in archivos:
            if nombre.lower().endswith(EXTENSIONES_VIDEO) and not nombre.startswith("."):
                encontrados.append(os.path.join(raiz, nombre))
    return sorted(encontrados)


def sincronizar(resultados_dir, carpeta_clips_base, clips_actuales=None, fuente_actual=None, feedback=None,
                contexto_actual=None):
    """Deja el catálogo al día y lo devuelve.

    - Quita del catálogo los archivos que ya no existen.
    - Añade ``clips_actuales`` (clips_sugeridos.json del último stream) con su fuente.
    - Añade cualquier video de la carpeta de clips que el catálogo no conozca
      (streams procesados antes de que existiera el catálogo). Si el título del
      archivo coincide con una valoración ya guardada, se enlaza con ella para
      que no vuelva a aparecer como "sin valorar".
    Cada elemento devuelto: {"ruta_archivo", "stream", "fuente", "clip"}.
    """
    entradas = {}
    for e in cargar_catalogo(resultados_dir):
        if os.path.isfile(e["ruta_archivo"]):
            entradas[_clave(e["ruta_archivo"])] = e
    cambio = len(entradas) != len(cargar_catalogo(resultados_dir))

    for clip in clips_actuales or []:
        ruta = clip.get("ruta_archivo") or clip.get("archivo")
        if ruta and os.path.isfile(ruta) and _clave(ruta) not in entradas:
            limpio = {k: v for k, v in clip.items() if not str(k).startswith("_")}
            limpio["ruta_archivo"] = limpio["archivo"] = str(ruta)
            entradas[_clave(ruta)] = {
                "ruta_archivo": str(ruta), "stream": os.path.basename(os.path.dirname(ruta)),
                "fuente": fuente_actual if isinstance(fuente_actual, dict) else None, "clip": limpio,
                "contexto_juego": contexto_actual if isinstance(contexto_actual, dict) else None,
            }
            cambio = True

    titulos_valorados = {}
    for f in (feedback or []):
        if f.get("clip_id") and f.get("titulo"):
            titulos_valorados.setdefault(_normalizar(f["titulo"]), f["clip_id"])

    for ruta in escanear_carpeta_clips(carpeta_base=carpeta_clips_base):
        if _clave(ruta) in entradas:
            continue
        duracion = round(duracion_archivo(ruta), 3)
        titulo = _titulo_desde_archivo(ruta)
        clip = {
            "titulo": titulo, "ruta_archivo": ruta, "archivo": ruta, "inicio": 0, "fin": duracion,
            "duracion": duracion, "tipo": "completo", "segmentos": [], "origen": "escaneo_carpeta",
        }
        legado = titulos_valorados.get(_normalizar(titulo))
        if legado:
            clip["clip_id_legado"] = legado
        entradas[_clave(ruta)] = {
            "ruta_archivo": ruta, "stream": os.path.basename(os.path.dirname(ruta)), "fuente": None, "clip": clip,
        }
        cambio = True

    resultado = list(entradas.values())
    if cambio:
        guardar_catalogo(resultados_dir, resultado)
    return resultado


def quitar_del_historial(rutas, ruta_historial):
    """Quita de ``historial_clips.json`` los clips cuyos archivos se eliminaron.

    Solo lo lee ``registrar_resultado.py`` (para preguntarte cuantas vistas tuvo cada
    clip), asi que no deja de tener sentido ningun otro paso. Un clip ya registrado
    (``registrado: true``, con sus vistas anotadas) se conserva. Devuelve cuantas
    entradas quito.
    """
    if not rutas:
        return 0
    quitar = {_clave(r) for r in rutas}
    pares = {(os.path.basename(os.path.dirname(os.path.abspath(r))), os.path.basename(r)) for r in rutas}
    try:
        with open(ruta_historial, "r", encoding="utf-8") as archivo:
            historial = json.load(archivo)
    except (OSError, ValueError):
        return 0
    if not isinstance(historial, list):
        return 0

    def sobra(e):
        if not isinstance(e, dict) or str(e.get("registrado")).lower() == "true":
            return False
        ruta = e.get("ruta_archivo")
        if ruta and _clave(ruta) in quitar:
            return True
        return (e.get("stream"), e.get("archivo")) in pares

    restantes = [e for e in historial if not sobra(e)]
    if len(restantes) == len(historial):
        return 0
    temporal = f"{ruta_historial}.{os.getpid()}.tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(restantes, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta_historial)
    return len(historial) - len(restantes)


def borrar_clip(ruta):
    """Elimina el archivo de un clip. Devuelve (ok, mensaje)."""
    try:
        if os.path.isfile(ruta):
            os.remove(ruta)
        return True, ""
    except PermissionError:
        return False, "el archivo está en uso (ciérralo si lo tienes abierto en el reproductor)"
    except OSError as exc:
        return False, str(exc)


def limpiar_carpeta_vacia(ruta_archivo, carpeta_base):
    """Quita la carpeta del stream si quedó vacía (sin tocar la carpeta base)."""
    carpeta = os.path.dirname(os.path.abspath(ruta_archivo))
    if carpeta_base and _clave(carpeta) == _clave(carpeta_base):
        return
    try:
        if os.path.isdir(carpeta) and not os.listdir(carpeta):
            shutil.rmtree(carpeta, ignore_errors=True)
    except OSError:
        pass
