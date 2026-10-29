# -*- coding: utf-8 -*-
"""Limpieza de archivos temporales de MKClips.

Solo toca archivos que el proyecto vuelve a generar solo. NUNCA toca tus clips, tu
configuracion, tus valoraciones (preferencias_usuario.json), el historial, el catalogo,
los criterios ni los resultados del ultimo stream.

Un archivo modificado hace poco (por defecto 10 min) se respeta: podria estar usandose en
un proceso en marcha.
"""
from __future__ import annotations

import os
import shutil
import time

BASE = os.path.dirname(os.path.abspath(__file__))
try:
    from .rutas_app import datos_dir
except ImportError:
    from rutas_app import datos_dir
RAIZ_CACHE = os.path.join(str(datos_dir()), ".mkclips_cache")
RESPETAR_SEGUNDOS = 600

# (id, nombre, descripcion, marcada por defecto)
CATEGORIAS = (
    ("audio", "Audio temporal de los streams",
     "Copia en WAV del audio de cada stream (suele ser lo que mas pesa). Se vuelve a crear sola si reprocesas ese stream.", True),
    ("miniaturas", "Miniaturas y vistas previas",
     "Imagenes de Validar clips. Se regeneran en segundos al abrir la pestana.", True),
    ("pycache", "Cache de Python (__pycache__)",
     "Se regenera sola al abrir la app.", True),
    ("residuos", "Residuos de procesos interrumpidos",
     "Archivos .tmp, recortes a medias y el registro de errores de la ventana de progreso.", True),
    ("etapas", "Resultados guardados de cada etapa",
     "Transcripcion, eventos, identificacion... de streams ya procesados. Si los borras y reprocesas un stream, "
     "se repite todo desde cero (varios minutos por stream). Solo para liberar mucho espacio.", False),
)


def _archivos_en(carpeta):
    for raiz, _dirs, nombres in os.walk(carpeta):
        for nombre in nombres:
            yield os.path.join(raiz, nombre)


def _reciente(ruta, ahora, segundos):
    try:
        return ahora - os.path.getmtime(ruta) < segundos
    except OSError:
        return True


def _candidatos(categoria, carpeta_clips=""):
    """Rutas de archivos de una categoria (sin filtrar por antiguedad)."""
    if categoria == "audio":
        return list(_archivos_en(os.path.join(RAIZ_CACHE, "audio"))) if os.path.isdir(os.path.join(RAIZ_CACHE, "audio")) else []
    if categoria == "miniaturas":
        carpeta = os.path.join(RAIZ_CACHE, "revision")
        return list(_archivos_en(carpeta)) if os.path.isdir(carpeta) else []
    if categoria == "etapas":
        carpeta = os.path.join(RAIZ_CACHE, "stages")
        return list(_archivos_en(carpeta)) if os.path.isdir(carpeta) else []
    if categoria == "pycache":
        salida = []
        for raiz in (BASE, os.path.join(os.path.dirname(BASE), "tests")):
            for dir_actual, dirs, _n in os.walk(raiz):
                dirs[:] = [d for d in dirs if d != ".mkclips_cache"]
                if os.path.basename(dir_actual) == "__pycache__":
                    salida.extend(_archivos_en(dir_actual))
        return salida
    if categoria == "residuos":
        salida = []
        for raiz in filter(None, (BASE, carpeta_clips)):
            if not os.path.isdir(raiz):
                continue
            for dir_actual, dirs, nombres in os.walk(raiz):
                dirs[:] = [d for d in dirs if d not in (".mkclips_cache", "__pycache__")]
                for nombre in nombres:
                    # .recorte_* solo se busca en la carpeta de clips, nunca junto al codigo.
                    en_clips = raiz == carpeta_clips
                    if nombre.endswith((".tmp", ".tmp.png", ".tmp.gif")) or (en_clips and nombre.startswith(".recorte_")) \
                            or (raiz == BASE and dir_actual == BASE and nombre == "notificacion_error.log"):
                        salida.append(os.path.join(dir_actual, nombre))
        return salida
    return []


def analizar(carpeta_clips="", respetar_segundos=RESPETAR_SEGUNDOS):
    """[{id, nombre, descripcion, marcada, archivos, bytes, omitidos}] para mostrar al usuario."""
    ahora = time.time()
    resultado = []
    for id_, nombre, descripcion, marcada in CATEGORIAS:
        archivos, omitidos, total = [], 0, 0
        for ruta in _candidatos(id_, carpeta_clips):
            if id_ != "pycache" and _reciente(ruta, ahora, respetar_segundos):
                omitidos += 1
                continue
            try:
                total += os.path.getsize(ruta)
            except OSError:
                continue
            archivos.append(ruta)
        resultado.append({"id": id_, "nombre": nombre, "descripcion": descripcion, "marcada": marcada,
                          "archivos": archivos, "bytes": total, "omitidos": omitidos})
    return resultado


def eliminar(ids, carpeta_clips="", respetar_segundos=RESPETAR_SEGUNDOS):
    """Elimina las categorias elegidas. Devuelve (archivos_borrados, bytes_liberados, errores)."""
    borrados, liberado, errores = 0, 0, []
    elegidas = {c["id"]: c for c in analizar(carpeta_clips, respetar_segundos)}
    for id_ in ids:
        categoria = elegidas.get(id_)
        if not categoria:
            continue
        for ruta in categoria["archivos"]:
            try:
                tam = os.path.getsize(ruta)
                os.remove(ruta)
                borrados += 1
                liberado += tam
            except FileNotFoundError:
                continue
            except OSError as exc:
                errores.append(f"{os.path.basename(ruta)}: {exc}")
        # Carpetas que quedaron vacias (no la raiz de la cache ni las carpetas del proyecto).
        for carpeta in {os.path.dirname(r) for r in categoria["archivos"]}:
            _quitar_vacias(carpeta)
    return borrados, liberado, errores


def _quitar_vacias(carpeta):
    protegidas = {os.path.normcase(os.path.abspath(p)) for p in (BASE, RAIZ_CACHE, os.path.join(RAIZ_CACHE, "audio"),
                                                                  os.path.join(RAIZ_CACHE, "revision"), os.path.join(RAIZ_CACHE, "stages"))}
    actual = os.path.abspath(carpeta)
    while os.path.normcase(actual) not in protegidas and os.path.isdir(actual):
        try:
            if os.listdir(actual):
                break
            shutil.rmtree(actual, ignore_errors=True)
        except OSError:
            break
        actual = os.path.dirname(actual)


def formatear_tamano(n):
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidad == "GB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024.0
