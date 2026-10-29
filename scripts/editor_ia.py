# -*- coding: utf-8 -*-
"""Mejora opcional de resolución con IA (Real-ESRGAN ncnn-vulkan) para el editor nativo.

Solo se procesa la zona recortada del clip que luego se amplía en la salida (la cámara y/o el juego), no el
clip entero, y solo si esa zona es más pequeña que su destino. El resultado se guarda en una caché para no
repetir el trabajo al volver a renderizar. Si el programa no está instalado, todo sigue funcionando igual."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

_SIN_VENTANA = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
NOMBRE_EXE = "realesrgan-ncnn-vulkan"
try:
    from .rutas_app import datos_dir
except ImportError:
    from rutas_app import datos_dir
CARPETA_CACHE = os.path.join(str(datos_dir()), ".mkclips_cache", "ia")
if getattr(sys, "frozen", False):
    CARPETA_HERRAMIENTA = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "herramientas", "realesrgan")
else:
    CARPETA_HERRAMIENTA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "herramientas", "realesrgan")
FPS_IA = 30
# nombre en la interfaz -> (modelo de Real-ESRGAN, escalas que admite)
MODELOS = {"rapido": ("realesr-animevideov3", (2, 3, 4)), "calidad": ("realesrgan-x4plus", (4,))}
AYUDA_INSTALAR = ("Real-ESRGAN no está instalado. Descarga «realesrgan-ncnn-vulkan-…-windows.zip» de "
                  "github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases y descomprímelo en la carpeta MKClips/herramientas/realesrgan "
                  "(debe quedar realesrgan-ncnn-vulkan.exe junto a su carpeta models).")


class Cancelado(Exception):
    pass


def buscar_ejecutable():
    """Ruta del programa o None. Orden: variable MKCLIPS_REALESRGAN, carpeta herramientas/realesrgan, PATH."""
    candidatos = [os.environ.get("MKCLIPS_REALESRGAN", "")]
    for base in (CARPETA_HERRAMIENTA, os.path.join(CARPETA_HERRAMIENTA, "realesrgan-ncnn-vulkan")):
        candidatos += [os.path.join(base, NOMBRE_EXE + ".exe"), os.path.join(base, NOMBRE_EXE)]
    candidatos.append(shutil.which(NOMBRE_EXE) or "")
    for c in candidatos:
        if c and os.path.isfile(c):
            return os.path.abspath(c)
    return None


def disponible():
    ruta = buscar_ejecutable()
    return (True, ruta) if ruta else (False, AYUDA_INSTALAR)


def escala_necesaria(crop, destino, modelo="rapido"):
    """Factor de ampliación de la IA (2, 3 o 4) o 0 si el recorte ya tiene resolución de sobra para su destino."""
    cw, ch = crop[2], crop[3]
    dw, dh = destino
    if cw <= 0 or ch <= 0:
        return 0
    falta = max(dw / cw, dh / ch)
    if falta <= 1.05:
        return 0
    for s in MODELOS.get(modelo, MODELOS["rapido"])[1]:
        if s >= falta - 0.02:
            return s
    return MODELOS.get(modelo, MODELOS["rapido"])[1][-1]


def _huella(ruta):
    try:
        st = os.stat(ruta)
        base = f"{os.path.abspath(ruta)}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        base = os.path.abspath(ruta)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def ruta_cache(ruta_clip, segmentos, crop, escala, modelo):
    clave = json.dumps([_huella(ruta_clip), segmentos, list(crop), escala, modelo, FPS_IA], sort_keys=True)
    return os.path.join(CARPETA_CACHE, hashlib.sha1(clave.encode("utf-8")).hexdigest() + ".mp4")


def _f(n):
    return (f"{n:.3f}".rstrip("0").rstrip(".")) or "0"


def _contar(carpeta):
    try:
        return sum(1 for n in os.listdir(carpeta) if n.lower().endswith((".jpg", ".png")))
    except OSError:
        return 0


def _ejecutar(comando, cancelar, cwd=None, sondear=None, ferr=None):
    """Lanza un proceso, avisa del avance con ``sondear()`` y respeta la cancelación."""
    proc = subprocess.Popen(comando, cwd=cwd, stdout=subprocess.DEVNULL, stderr=ferr or subprocess.DEVNULL, creationflags=_SIN_VENTANA)
    try:
        while proc.poll() is None:
            if cancelar is not None and cancelar.is_set():
                proc.kill()
                proc.wait()
                raise Cancelado()
            if sondear:
                sondear()
            time.sleep(0.4)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    return proc.returncode


def mejorar_region(ruta_clip, segmentos, crop, escala, modelo="rapido", progreso=None, cancelar=None):
    """Devuelve la ruta de un vídeo (sin audio, 30 fps) con la zona ``crop`` = (x, y, w, h) ya ampliada ``escala`` veces.

    El vídeo sigue la línea de tiempo de salida (los tramos ya aplicados), así que se superpone sin más ajustes."""
    destino = ruta_cache(ruta_clip, segmentos, crop, escala, modelo)
    if os.path.isfile(destino):
        if progreso:
            progreso(1.0)
        return destino
    exe = buscar_ejecutable()
    if not exe:
        raise RuntimeError(AYUDA_INSTALAR)
    nombre_modelo = MODELOS.get(modelo, MODELOS["rapido"])[0]
    duracion = sum(s["fin"] - s["inicio"] for s in segmentos)
    n_total = max(1, int(duracion * FPS_IA))
    x, y, w, h = crop
    necesario = int(n_total * w * h * escala * escala * 0.5) + int(n_total * w * h * 0.4) + 300 * 1024 * 1024
    os.makedirs(CARPETA_CACHE, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mkclips_ia_") as trabajo:
        if shutil.disk_usage(trabajo).free < necesario:
            raise RuntimeError(f"No hay espacio en disco para la mejora con IA (hacen falta unos {necesario // (1024 * 1024)} MB libres).")
        entrada, salida = os.path.join(trabajo, "in"), os.path.join(trabajo, "out")
        os.makedirs(entrada)
        os.makedirs(salida)
        # 1) los fotogramas de la zona, con los tramos ya aplicados
        n = len(segmentos)
        partes = [f"[0:v]trim=start={_f(s['inicio'])}:end={_f(s['fin'])},setpts=PTS-STARTPTS[v{i}]" for i, s in enumerate(segmentos)]
        partes.append((f"[v0]null[vc]" if n == 1 else "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]"))
        partes.append(f"[vc]crop={w}:{h}:{x}:{y},fps={FPS_IA}[o]")
        err = os.path.join(trabajo, "err.txt")
        with open(err, "w", encoding="utf-8", errors="replace") as ferr:
            rc = _ejecutar(["ffmpeg", "-y", "-v", "error", "-i", os.path.abspath(ruta_clip), "-filter_complex", ";".join(partes), "-map", "[o]",
                            "-q:v", "2", os.path.join(entrada, "%06d.jpg")], cancelar, ferr=ferr,
                           sondear=lambda: progreso and progreso(0.1 * min(1.0, _contar(entrada) / n_total)))
        n_real = _contar(entrada)
        if rc != 0 or n_real == 0:
            raise RuntimeError("No se pudieron extraer los fotogramas para la mejora con IA.")
        # 2) la IA
        with open(err, "w", encoding="utf-8", errors="replace") as ferr:
            rc = _ejecutar([exe, "-i", entrada, "-o", salida, "-n", nombre_modelo, "-s", str(escala), "-f", "jpg"], cancelar,
                           cwd=os.path.dirname(exe), ferr=ferr,
                           sondear=lambda: progreso and progreso(0.1 + 0.8 * min(1.0, _contar(salida) / n_real)))
        if rc != 0 or _contar(salida) < n_real:
            with open(err, "r", encoding="utf-8", errors="replace") as f:
                detalle = f.read()[-400:].strip()
            raise RuntimeError("Real-ESRGAN no pudo mejorar la imagen (¿tarjeta gráfica sin Vulkan o modelo «" + nombre_modelo + "» ausente?). " + detalle)
        # 3) de vuelta a vídeo
        temporal = destino + f".{os.getpid()}.tmp.mp4"
        with open(err, "w", encoding="utf-8", errors="replace") as ferr:
            rc = _ejecutar(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS_IA), "-i", os.path.join(salida, "%06d.jpg"), "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "12", "-pix_fmt", "yuv420p", "-an", "-f", "mp4", temporal], cancelar, ferr=ferr)
        if rc != 0 or not os.path.isfile(temporal):
            with contextlib.suppress(OSError):
                os.remove(temporal)
            raise RuntimeError("No se pudo recomponer el vídeo mejorado.")
        os.replace(temporal, destino)
    if progreso:
        progreso(1.0)
    return destino
