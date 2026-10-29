# -*- coding: utf-8 -*-
"""FFmpeg para el editor nativo: sonda, vista previa ligera, onda de audio y render final.

El render sigue la misma lÃ­nea que el cortador del pipeline: NVENC (con respaldo a x264 si
no hay GPU o falla), todas las pistas de audio del clip por separado y escritura atÃ³mica.
El clip original nunca se modifica; el resultado va a una carpeta ``editados`` junto a Ã©l.
"""
from __future__ import annotations
SELLO = "2026-10-27-b"        # lo muestra el editor para comprobar que todos los archivos estÃ¡n actualizados

import contextlib
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

try:
    from . import editor_modelo as modelo, editor_fuentes as fuentes, editor_piezas as piezas_mod
except ImportError:  # mÃ³dulo suelto desde scripts/
    import editor_modelo as modelo
    import editor_fuentes as fuentes
    import editor_piezas as piezas_mod

_SIN_VENTANA = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
NVENC_ENCODER = os.environ.get("NVENC_ENCODER", "h264_nvenc")
NVENC_PRESET = os.environ.get("NVENC_PRESET", "p5")
NVENC_CQ = os.environ.get("NVENC_CQ", "21")
FORMATO_PROXY = os.environ.get("MKCLIPS_EDITOR_PROXY", "mp4")     # "webm" para navegadores sin H.264
CARPETA_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mkclips_cache", "editor")
_ESTADO_NVENC = {"ok": None}
_SONDA_CACHE = {}
_SONDA_BLOQUEO = threading.Lock()
# ----------------------------------------------------------------------------- sonda
def sondear(ruta):
    """Metadatos de video memorizados por ruta, tama?o y fecha de modificaci?n."""
    try:
        huella = _huella(ruta)
    except OSError:
        huella = None
    if huella:
        with _SONDA_BLOQUEO:
            cacheado = _SONDA_CACHE.get(huella)
            if cacheado is not None:
                return dict(cacheado)
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "stream=codec_type,codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate:format=duration,format_name",
                            "-of", "json", ruta], capture_output=True, text=True, timeout=60, creationflags=_SIN_VENTANA)
        datos = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ValueError(f"No se pudo leer el video: {exc}")
    streams = datos.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("width")), None)
    if not video:
        raise ValueError("El archivo no tiene video.")
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    pistas = len(audios)
    fps = 30.0
    for clave in ("avg_frame_rate", "r_frame_rate"):
        try:
            a, _, b = str(video.get(clave, "0/1")).partition("/")
            valor = float(a) / float(b or 1)
            if 1 <= valor <= 240:
                fps = valor
                break
        except (ValueError, ZeroDivisionError):
            continue
    try:
        duracion = float(datos.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        raise ValueError("No se pudo leer la duraciÃ³n del video.")
    info = {"ancho": int(video["width"]), "alto": int(video["height"]), "duracion": duracion, "pistas_audio": pistas, "fps": fps,
            "codec_video": video.get("codec_name", ""), "pix_fmt": video.get("pix_fmt", ""),
            "codecs_audio": [a.get("codec_name", "") for a in audios],
            "formato": datos.get("format", {}).get("format_name", "")}
    if huella:
        with _SONDA_BLOQUEO:
            _SONDA_CACHE[huella] = dict(info)
            while len(_SONDA_CACHE) > 128:
                _SONDA_CACHE.pop(next(iter(_SONDA_CACHE)))
    return info


# ----------------------------------------------------------------------------- vista previa y onda
def _huella(ruta):
    s = os.stat(ruta)
    return hashlib.sha1(f"{os.path.abspath(ruta)}|{s.st_size}|{s.st_mtime_ns}".encode()).hexdigest()[:20]


def ruta_proxy(ruta):
    return os.path.join(CARPETA_CACHE, _huella(ruta) + "_vista." + FORMATO_PROXY)


def tipo_proxy():
    return "video/webm" if FORMATO_PROXY == "webm" else "video/mp4"


def video_directo(ruta, info):
    """El origen es reproducible directamente por WebView2; no hay que convertirlo al abrir."""
    audios = info.get("codecs_audio") or []
    if len(audios) > 1 or info.get("pix_fmt") != "yuv420p":
        return False
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".mp4", ".m4v", ".mov"):
        return info.get("codec_video") == "h264" and (not audios or audios[0] in ("aac", "mp3"))
    if ext == ".webm":
        return info.get("codec_video") in ("vp8", "vp9", "av1") and (not audios or audios[0] in ("opus", "vorbis"))
    return False


def video_remuxable(ruta, info):
    """H.264/AAC en contenedor no web: puede pasar a MP4 con copia de streams, sin recodificar."""
    ext = os.path.splitext(ruta)[1].lower()
    audios = info.get("codecs_audio") or []
    return (FORMATO_PROXY == "mp4" and ext not in (".mp4", ".m4v", ".mov", ".webm")
            and info.get("codec_video") == "h264" and info.get("pix_fmt") == "yuv420p"
            and len(audios) <= 1 and (not audios or audios[0] in ("aac", "mp3")))


def tipo_video_directo(ruta):
    return "video/webm" if os.path.splitext(ruta)[1].lower() == ".webm" else "video/mp4"


def crear_proxy(ruta, info=None, ejecutar=subprocess.run):
    """MP4 ligero (540p, mezcla de todas las pistas, cuadros clave frecuentes) para el navegador.

    Los MKV con HEVC o varias pistas no se reproducen bien en el navegador; esta copia sÃ­, y
    permite arrastrar la lÃ­nea de tiempo con fluidez. Solo se usa para ver, nunca para el render."""
    destino = ruta_proxy(ruta)
    if os.path.isfile(destino):
        return destino
    info = info or sondear(ruta)
    os.makedirs(CARPETA_CACHE, exist_ok=True)
    temporal = destino + f".{os.getpid()}.{threading.get_ident()}.tmp.{FORMATO_PROXY}"
    if video_remuxable(ruta, info):
        remux = ["ffmpeg", "-y", "-v", "error", "-i", ruta, "-map", "0:v:0"]
        if info.get("pistas_audio", 0): remux += ["-map", "0:a:0"]
        remux += ["-map_metadata", "0", "-c", "copy", "-movflags", "+faststart", "-f", "mp4", temporal]
        r = ejecutar(remux, capture_output=True, text=True, creationflags=_SIN_VENTANA)
        if r.returncode == 0 and os.path.isfile(temporal):
            os.replace(temporal, destino)
            return destino
        with contextlib.suppress(OSError): os.remove(temporal)
    escala = "scale=w='min(720,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2:flags=bilinear,setsar=1,format=yuv420p"
    comando = ["ffmpeg", "-y", "-v", "error", "-i", ruta]
    n = info["pistas_audio"]
    if n > 1:
        entradas = "".join(f"[0:a:{i}]" for i in range(n))
        comando += ["-filter_complex", f"[0:v:0]{escala}[v];{entradas}amix=inputs={n}:duration=longest[a]", "-map", "[v]", "-map", "[a]"]
    else:
        comando += ["-map", "0:v:0", "-vf", escala] + (["-map", "0:a:0"] if n == 1 else [])
    if FORMATO_PROXY == "webm":
        comando += ["-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-crf", "36", "-b:v", "0", "-g", "12"]
        if n:
            comando += ["-c:a", "libopus", "-b:a", "96k", "-ac", "2"]
        comando += ["-f", "webm", temporal]
    else:
        comando += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "27", "-g", "12", "-keyint_min", "12"]
        if n:
            comando += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]
        comando += ["-movflags", "+faststart", "-f", "mp4", temporal]
    r = ejecutar(comando, capture_output=True, text=True, creationflags=_SIN_VENTANA)
    if r.returncode != 0 or not os.path.isfile(temporal):
        with contextlib.suppress(OSError):
            os.remove(temporal)
        raise RuntimeError("No se pudo preparar la vista previa: " + (r.stderr or "")[-300:])
    os.replace(temporal, destino)
    return destino


def onda_de_audio(ruta, duracion, por_segundo=20):
    """Picos de audio. Persiste JSON por huella para no volver a decodificar clips ya abiertos."""
    huella = _huella(ruta)
    os.makedirs(CARPETA_CACHE, exist_ok=True)
    cache = os.path.join(CARPETA_CACHE, f"onda_{huella}_{int(por_segundo)}.json")
    try:
        with open(cache, "r", encoding="utf-8") as f:
            datos = json.load(f)
        if isinstance(datos, list) and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in datos):
            return datos
    except (OSError, ValueError):
        pass
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-map", "0:a:0", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                       capture_output=True, creationflags=_SIN_VENTANA)
    if r.returncode != 0 or not r.stdout:
        picos = []
    else:
        muestras = np.abs(np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)) / 32768.0
        ventana = max(1, 8000 // por_segundo)
        n = len(muestras) // ventana
        if n == 0:
            picos = []
        else:
            bloques = muestras[:n * ventana].reshape(n, ventana).max(axis=1)
            maximo = float(bloques.max()) or 1.0
            picos = [round(float(p) / maximo, 3) for p in bloques]
    temporal = cache + f".{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(picos, f, separators=(",", ":"))
        os.replace(temporal, cache)
    except OSError:
        with contextlib.suppress(OSError): os.remove(temporal)
    return picos


# ----------------------------------------------------------------------------- medios extra (B-roll, imÃ¡genes, audio)
EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
EXT_MEDIOS = EXT_IMAGEN | {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac"}


def sondear_medio(ruta):
    """{"tipo": video|audio|imagen, "duracion", "ancho", "alto", "tiene_audio"}; ValueError si no sirve."""
    if not os.path.isfile(ruta):
        raise ValueError("El archivo no existe.")
    if os.path.splitext(ruta)[1].lower() in EXT_IMAGEN:
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                "-of", "json", ruta], capture_output=True, text=True, timeout=60, creationflags=_SIN_VENTANA)
            v = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
            ancho, alto = int(v["width"]), int(v["height"])
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            raise ValueError("No se pudo leer la imagen.")
        return {"tipo": "imagen", "duracion": 5.0, "ancho": ancho, "alto": alto, "tiene_audio": False}
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt,width,height:format=duration,format_name",
                            "-of", "json", ruta], capture_output=True, text=True, timeout=60, creationflags=_SIN_VENTANA)
        datos = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ValueError(f"No se pudo leer el archivo: {exc}")
    flujos = datos.get("streams", [])
    video = next((x for x in flujos if x.get("codec_type") == "video" and x.get("width")), None)
    audios = [x for x in flujos if x.get("codec_type") == "audio"]
    audio = bool(audios)
    try:
        duracion = float(datos.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        raise ValueError("No se pudo leer la duraciÃ³n.")
    if not video and not audio:
        raise ValueError("El archivo no tiene video ni audio.")
    return {"tipo": "video" if video else "audio", "duracion": duracion, "ancho": int(video["width"]) if video else 0,
            "alto": int(video["height"]) if video else 0, "tiene_audio": audio, "pistas_audio": len(audios),
            "codec_video": video.get("codec_name", "") if video else "", "pix_fmt": video.get("pix_fmt", "") if video else "",
            "codecs_audio": [a.get("codec_name", "") for a in audios],
            "formato": datos.get("format", {}).get("format_name", "")}


def crear_proxy_medio(ruta, medio, ejecutar=subprocess.run):
    """Copia ligera para ver/oÃ­r un medio extra en el navegador. Devuelve (ruta, mimetype)."""
    os.makedirs(CARPETA_CACHE, exist_ok=True)
    if medio["tipo"] == "video":
        if video_directo(ruta, medio):
            return ruta, tipo_video_directo(ruta)
        return crear_proxy(ruta, {"pistas_audio": 1 if medio["tiene_audio"] else 0}, ejecutar), tipo_proxy()
    base = os.path.join(CARPETA_CACHE, _huella(ruta))
    if medio["tipo"] == "imagen":
        destino = base + "_img.jpg"
        comando = ["ffmpeg", "-y", "-v", "error", "-i", ruta, "-vf", "scale='min(1280,iw)':-2", "-frames:v", "1", "-q:v", "3", "-f", "mjpeg", "TMP"]
        tipo = "image/jpeg"
    elif FORMATO_PROXY == "webm":
        destino = base + "_aud.webm"
        comando = ["ffmpeg", "-y", "-v", "error", "-i", ruta, "-vn", "-map", "0:a:0", "-c:a", "libopus", "-b:a", "96k", "-f", "webm", "TMP"]
        tipo = "audio/webm"
    else:
        destino = base + "_aud.m4a"
        comando = ["ffmpeg", "-y", "-v", "error", "-i", ruta, "-vn", "-map", "0:a:0", "-c:a", "aac", "-b:a", "128k", "-f", "ipod", "TMP"]
        tipo = "audio/mp4"
    if os.path.isfile(destino):
        return destino, tipo
    temporal = destino + f".{os.getpid()}.{threading.get_ident()}.tmp"
    comando[-1] = temporal
    r = ejecutar(comando, capture_output=True, text=True, creationflags=_SIN_VENTANA)
    if r.returncode != 0 or not os.path.isfile(temporal):
        with contextlib.suppress(OSError):
            os.remove(temporal)
        raise RuntimeError("No se pudo preparar el medio: " + (r.stderr or "")[-300:])
    os.replace(temporal, destino)
    return destino, tipo


# ----------------------------------------------------------------------------- codificador
def nvenc_disponible(ejecutar=subprocess.run, refrescar=False):
    if _ESTADO_NVENC["ok"] is None or refrescar:
        try:
            r = ejecutar(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
                          "-c:v", NVENC_ENCODER, "-f", "null", "-"], capture_output=True, text=True, timeout=30,
                         creationflags=_SIN_VENTANA)
            _ESTADO_NVENC["ok"] = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _ESTADO_NVENC["ok"] = False
    return _ESTADO_NVENC["ok"]


def argumentos_codificador(usar_nvenc):
    if usar_nvenc:
        return ["-c:v", NVENC_ENCODER, "-preset", NVENC_PRESET, "-rc", "vbr", "-cq", NVENC_CQ, "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]


# ----------------------------------------------------------------------------- filtros
def _f(n):
    texto = f"{n:.3f}".rstrip("0").rstrip(".")
    return texto or "0"


_AMIX_NORMALIZE = {"ok": None}


def amix_tiene_normalize(ejecutar=subprocess.run):
    """FFmpeg 4.4+ permite ``amix=normalize=0`` (que no baja el volumen de la pista principal)."""
    if _AMIX_NORMALIZE["ok"] is None:
        try:
            r = ejecutar(["ffmpeg", "-hide_banner", "-h", "filter=amix"], capture_output=True, text=True, timeout=20,
                         creationflags=_SIN_VENTANA)
            _AMIX_NORMALIZE["ok"] = "normalize" in (r.stdout or "")
        except (OSError, subprocess.SubprocessError):
            _AMIX_NORMALIZE["ok"] = False
    return _AMIX_NORMALIZE["ok"]


def extras_activos(edicion):
    """Elementos extra que entran en el render: el archivo existe, su pista no estÃ¡ oculta y caen dentro del clip.

    Cada uno lleva ``indice`` (nÃºmero de entrada de FFmpeg, la 0 es el clip), ``dur`` ya recortada a la
    duraciÃ³n de salida y ``suena`` (si aporta audio)."""
    total = modelo.duracion_salida(edicion["segmentos"])
    pistas = edicion.get("pistas") or {}
    ocultas, mudas = set(pistas.get("ocultas", [])), set(pistas.get("silenciadas", []))
    resultado = []
    for e in edicion.get("extras") or []:
        carril = ("A" if e["tipo"] == "audio" else "V") + str(e["pista"] + 1)
        if carril in ocultas or e["t"] >= total - 0.05 or not os.path.isfile(e["archivo"]):
            continue
        x = dict(e)
        x["dur"] = round(min(e["dur"], total - e["t"]), 3)
        x["suena"] = bool(e["audio"] and e["tiene_audio"] and carril not in mudas and e["volumen"] > 0)
        x["indice"] = len(resultado) + 1
        resultado.append(x)
    return resultado


def argumentos_entradas_extra(extras):
    comando = []
    for e in extras:
        ruta = os.path.abspath(e["archivo"])
        if e["tipo"] == "imagen":
            comando += ["-loop", "1", "-framerate", "30", "-t", _f(e["dur"]), "-i", ruta]
        else:
            comando += ["-ss", _f(e["desde"]), "-t", _f(e["dur"] * e.get("velocidad", 1.0)), "-i", ruta]
    return comando


_ROL_FRANJA = {"arriba": "juego", "abajo": "cam", "tres.a": "juego", "tres.b": "cam", "tres.c": "juego"}


def regiones_encuadre(edicion):
    """Zonas del clip que se amplÃ­an en la salida: [{"clave", "rol" ("cam"/"juego"), "crop" (x, y, w, h en px), "destino" (w, h en px)}].

    Es la geometrÃ­a que usa el filtro y la que usa la mejora con IA, para que ambas coincidan. El fondo desenfocado no cuenta."""
    enc, o, sa = edicion["encuadre"], edicion["origen"], edicion["salida"]
    W, H, ow, oh = o["ancho"], o["alto"], sa["ancho"], sa["alto"]
    r = []
    if enc["modo"] == "recorte":
        r.append({"clave": "recorte", "rol": "cam", "crop": modelo.rect_en_pixeles(enc["recorte"], W, H, ow / oh), "destino": (ow, oh)})
    elif enc["modo"] in ("dividido", "tres"):
        for t in modelo.franjas(enc, oh):
            r.append({"clave": t["clave"], "rol": _ROL_FRANJA.get(t["clave"], "cam"), "crop": modelo.rect_en_pixeles(modelo.rect_de(enc, t["clave"]), W, H, ow / t["alto"]),
                      "destino": (ow, t["alto"])})
    elif enc["modo"] == "capas":
        for c in enc["capas"]:
            if c["rol"] == "fondo":
                continue
            if c["rol"] == "cam" and (enc.get("seguimiento_cara") or {}).get("activo") and (enc.get("seguimiento_cara") or {}).get("trayectoria"):
                # La fuente cambia fotograma a fotograma; la mejora IA precortada no sirve para este caso.
                continue
            crop, _dest, interior = modelo.geometria_capa(c, W, H, ow, oh)
            r.append({"clave": "capa:" + c["id"], "rol": "juego" if c["rol"] == "juego" else "cam", "crop": crop, "destino": interior})
    return r


def _color_ff(hex_color):
    return "0x" + hex_color.lstrip("#").upper()


def _exp_trayectoria(trayectoria, segmentos, eje, tam_crop, dimension):
    """Expresión FFmpeg lineal por tramos; los puntos de origen se proyectan al tiempo editado."""
    puntos = []
    cursor = 0.0
    for s in segmentos:
        ini, fin = float(s["inicio"]), float(s["fin"])
        dentro = [p for p in trayectoria if ini <= float(p.get("t", -1)) <= fin]
        cercano_ini = min(trayectoria, key=lambda p: abs(float(p.get("t", 0))-ini), default=None)
        puntos.append((cursor, ini, cercano_ini))
        puntos.extend((cursor + float(p["t"]) - ini, float(p["t"]), p) for p in dentro)
        cercano_fin = min(trayectoria, key=lambda p: abs(float(p.get("t", 0))-fin), default=None)
        puntos.append((cursor + fin - ini, fin, cercano_fin))
        cursor += fin - ini
    puntos.sort(key=lambda a: a[0])
    if len(puntos) > 160:
        puntos = puntos[::max(1, (len(puntos)-1+158)//159)] + [puntos[-1]]
    valores=[]
    for _out, _src, p in puntos:
        centro = float(p[eje]) if p else .5
        valores.append(max(0.0,min(float(dimension-tam_crop), centro * dimension - tam_crop/2)))
    expr = f"{valores[-1]:.3f}"
    for i in range(len(puntos)-2,-1,-1):
        t0, t1 = puntos[i][0], puntos[i+1][0]
        a, b = valores[i], valores[i+1]
        if t1 <= t0: continue
        interp = f"({a:.3f}+({b-a:.3f})*(t-{t0:.3f})/{t1-t0:.3f})"
        expr = f"if(lt(t,{t1:.3f}),{interp},{expr})"
    return expr


def _cadenas_capas(enc, W, H, ow, oh, mej=None, segmentos=None):
    """Filtros del modo Â«capasÂ»: parte de [vc] y deja el resultado en [vl]."""
    capas = enc["capas"] or [{"id": "c0", "rol": "juego", "fuente": {"x": 0, "y": 0, "w": 1, "h": 1}, "destino": {"x": 0, "y": 0, "w": 1, "h": 1},
                              "ajuste": "llenar", "desenfoque": 0, "oscurecer": 0, "forma": "rect", "radio": 0.1, "borde": {"ancho": 0, "color": "#FFFFFF"}}]
    mej = mej or {}
    n = len(capas)
    libres = [i for i, c in enumerate(capas) if "capa:" + c["id"] not in mej]
    if not libres:
        partes = ["[vc]nullsink"]
    elif len(libres) == 1:
        partes = [f"[vc]null[k{libres[0]}]"]
    else:
        partes = ["[vc]split=%d%s" % (len(libres), "".join(f"[k{i}]" for i in libres))]
    acumulado = None
    for i, c in enumerate(capas):
        (cx, cy, cw, ch), (dx, dy, dw, dh), (iw_, ih_) = modelo.geometria_capa(c, W, H, ow, oh)
        ia = mej.get("capa:" + c["id"])
        f = [] if ia is not None else [f"crop={cw}:{ch}:{cx}:{cy}"]
        seg = enc.get("seguimiento_cara") or {}
        tray = seg.get("trayectoria") or []
        if c.get("rol") == "cam" and seg.get("activo") and tray and segmentos:
            zoom = max(1.0, min(2.5, float(seg.get("zoom", 1.2))))
            tw, th = max(2, modelo._par(cw/zoom)), max(2, modelo._par(ch/zoom))
            ex = _exp_trayectoria(tray, segmentos, "x", tw, W)
            ey = _exp_trayectoria(tray, segmentos, "y", th, H)
            f = [f"crop={tw}:{th}:x='{ex}':y='{ey}':eval=frame"]
        if c["ajuste"] == "llenar":
            f.append(f"scale={iw_}:{ih_}:flags=lanczos")
        else:
            f.append(f"scale={iw_}:{ih_}:force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos")
        if c["desenfoque"] > 0:
            radio = max(1, int(round(c["desenfoque"] / 6.0)))
            if c["ajuste"] == "llenar":
                bw, bh = max(16, modelo._par(iw_ / 6)), max(16, modelo._par(ih_ / 6))
                f.append(f"scale={bw}:{bh}:flags=bilinear,boxblur={min(radio, bw // 2 - 1, bh // 2 - 1)}:2,scale={iw_}:{ih_}:flags=bilinear")
            else:
                f.append(f"boxblur={max(1, int(round(c['desenfoque'] / 2)))}:2")
        if c["oscurecer"] > 0:
            f.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{_f(c['oscurecer'])}:t=fill")
        b = c["borde"]["ancho"]
        if b > 0:
            f.append(f"pad=iw+{2 * b}:ih+{2 * b}:{b}:{b}:color={_color_ff(c['borde']['color'])}")
        if i > 0 and c["forma"] != "rect":
            R = "min(W,H)/2" if c["forma"] == "circulo" else f"{_f(c['radio'])}*min(W,H)"
            alfa = f"255*clip({R}-hypot(max(abs(X-W/2+0.5)-(W/2-{R}),0),max(abs(Y-H/2+0.5)-(H/2-{R}),0))+0.5,0,1)"

            def plano(nombre, sub):
                if b <= 0:
                    return f"{nombre}(X,Y)"
                # con borde, el vÃ­deo interior se redondea con radio (R - borde): el borde queda del mismo grosor tambiÃ©n en las esquinas
                ri = f"max({R}-{_f(b / sub)},0)"
                m = f"clip({ri}-hypot(max(abs(X-W/2+0.5)-(W/2-{_f(b / sub)}-{ri}),0),max(abs(Y-H/2+0.5)-(H/2-{_f(b / sub)}-{ri}),0))+0.5,0,1)"
                return f"{m}*{nombre}(X,Y)+(1-{m})*{nombre}(0,floor(H/2))"
            f.append(f"format=yuva420p,geq=lum='{plano('lum', 1)}':cb='{plano('cb', 2)}':cr='{plano('cr', 2)}':a='{alfa}'")
        f.append("setsar=1")
        origen_i = f"[{ia}:v]" if ia is not None else f"[k{i}]"
        if i == 0:
            f.append(f"pad={ow}:{oh}:{dx}+({dw}-iw)/2:{dy}+({dh}-ih)/2:color=black")
            partes.append(origen_i + ",".join(f) + "[a0]")
            acumulado = "a0"
        else:
            partes.append(origen_i + ",".join(f) + f"[l{i}]")
            sig = f"a{i}"
            partes.append(f"[{acumulado}][l{i}]overlay=x={dx}+({dw}-w)/2:y={dy}+({dh}-h)/2[{sig}]")
            acumulado = sig
    partes.append(f"[{acumulado}]null[vl]")
    return partes


def _cadenas_encuadre(enc, W, H, ow, oh, mej=None, segmentos=None):
    """Filtros que encuadran [vc] (el video ya recortado) a la salida; el resultado queda en [vl].

    ``mej`` asigna a cada zona la entrada de FFmpeg con esa zona ya mejorada por IA."""
    mej = mej or {}
    partes = []
    if enc["modo"] in ("dividido", "tres"):
        tiras = modelo.franjas(enc, oh)
        n_t = len(tiras)
        libres = [k for k, t in enumerate(tiras) if t["clave"] not in mej]
        if not libres:
            partes.append("[vc]nullsink")
        elif len(libres) == 1:
            partes.append(f"[vc]null[s{libres[0]}]")
        else:
            partes.append("[vc]split=%d%s" % (len(libres), "".join(f"[s{k}]" for k in libres)))
        for k, t in enumerate(tiras):
            if t["clave"] in mej:
                partes.append(f"[{mej[t['clave']]}:v]scale={ow}:{t['alto']}:flags=lanczos,setsar=1[t{k}]")
                continue
            x, y, w, h = modelo.rect_en_pixeles(modelo.rect_de(enc, t["clave"]), W, H, ow / t["alto"])
            partes.append(f"[s{k}]crop={w}:{h}:{x}:{y},scale={ow}:{t['alto']}:flags=lanczos,setsar=1[t{k}]")
        linea = enc.get("linea") or {"ancho": 0}
        if linea.get("ancho", 0) > 0:
            partes.append("".join(f"[t{k}]" for k in range(n_t)) + f"vstack=inputs={n_t}[vl0]")
            a = int(linea["ancho"])
            cajas = ",".join(f"drawbox=x=0:y={max(0, t['y0'] - a // 2)}:w=iw:h={a}:color={_color_ff(linea['color'])}:t=fill" for t in tiras[1:])
            partes.append(f"[vl0]{cajas}[vl]")
        else:
            partes.append("".join(f"[t{k}]" for k in range(n_t)) + f"vstack=inputs={n_t}[vl]")
    elif enc["modo"] == "capas":
        partes.extend(_cadenas_capas(enc, W, H, ow, oh, mej, segmentos))
    elif enc["modo"] == "ajustar":
        partes.append("[vc]split=2[sf][sg]")
        partes.append(f"[sf]scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},boxblur=24:6,setsar=1[fondo]")
        partes.append(f"[sg]scale={ow}:{oh}:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1[frente]")
        partes.append("[fondo][frente]overlay=(W-w)/2:(H-h)/2[vl]")
    elif "recorte" in mej:
        partes.append("[vc]nullsink")
        partes.append(f"[{mej['recorte']}:v]scale={ow}:{oh}:flags=lanczos,setsar=1[vl]")
    else:
        x, y, w, h = modelo.rect_en_pixeles(enc["recorte"], W, H, ow / oh)
        partes.append(f"[vc]crop={w}:{h}:{x}:{y},scale={ow}:{oh}:flags=lanczos,setsar=1[vl]")
    return partes


def construir_filtro(edicion, con_subtitulos, nombre_ass="subs.ass", carpeta_fuentes="fuentes", mejoradas=None):
    """(filter_complex, mapas) para recortar tramos, encuadrar y quemar subtÃ­tulos.

    Las rutas de ``ass`` son relativas: FFmpeg se ejecuta dentro de la carpeta de trabajo, lo que
    evita los problemas de escape de ``C:\\`` en Windows."""
    origen, salida = edicion["origen"], edicion["salida"]
    segmentos = edicion["segmentos"]
    enc = edicion["encuadre"]
    ow, oh = salida["ancho"], salida["alto"]
    partes, n = [], len(segmentos)
    for i, s in enumerate(segmentos):
        partes.append(f"[0:v]trim=start={_f(s['inicio'])}:end={_f(s['fin'])},setpts=PTS-STARTPTS[v{i}]")
    if n == 1:
        partes.append("[v0]null[vc]")
    else:
        partes.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]")

    W, H = origen["ancho"], origen["alto"]
    partes.extend(_cadenas_encuadre(enc, W, H, ow, oh, mejoradas, segmentos))

    ultimo = "vl"
    if "V1" in (edicion.get("pistas") or {}).get("ocultas", []):       # pista V1 oculta: el clip se ve negro
        partes.append("[vl]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill[vneg]")
        ultimo = "vneg"
    extras = extras_activos(edicion)
    capas = sorted((e for e in extras if e["tipo"] != "audio"), key=lambda e: (e["pista"], e["t"]))
    for k, e in enumerate(capas):
        i, t0, t1 = e["indice"], e["t"], e["t"] + e["dur"]
        if e["modo"] == "recuadro":
            rw = max(2, int(round(e["recuadro"]["w"] * ow / 2)) * 2)
            rx, ry = int(round(e["recuadro"]["x"] * ow)), int(round(e["recuadro"]["y"] * oh))
            ajuste = f"scale={rw}:-2:flags=lanczos"
        else:
            rx = ry = 0
            ajuste = f"scale={ow}:{oh}:force_original_aspect_ratio=increase:flags=lanczos,crop={ow}:{oh}"
        vel = e.get("velocidad", 1.0) if e["tipo"] != "imagen" else 1.0
        cadena = f"[{i}:v]fps=30,{ajuste},setsar=1,format=yuva420p"
        if abs(vel - 1.0) > 1e-4:
            cadena += f",setpts=(PTS-STARTPTS)/{_f(vel)}"
        if e["fundido_in"] > 0:
            cadena += f",fade=t=in:st=0:d={_f(e['fundido_in'])}:alpha=1"
        if e["fundido_out"] > 0:
            cadena += f",fade=t=out:st={_f(max(0.0, e['dur'] - e['fundido_out']))}:d={_f(e['fundido_out'])}:alpha=1"
        cadena += (f",setpts=PTS+{_f(t0)}/TB[ov{k}]" if abs(vel - 1.0) > 1e-4 else f",setpts=PTS-STARTPTS+{_f(t0)}/TB[ov{k}]")
        partes.append(cadena)
        siguiente = f"vm{k}"
        partes.append(f"[{ultimo}][ov{k}]overlay={rx}:{ry}:eof_action=pass:enable='between(t,{_f(t0)},{_f(t1)})'[{siguiente}]")
        ultimo = siguiente

    if con_subtitulos:
        partes.append(f"[{ultimo}]ass={nombre_ass}:fontsdir={carpeta_fuentes}[vout]")
    else:
        partes.append(f"[{ultimo}]null[vout]")
    mapas = ["[vout]"]
    total = modelo.duracion_salida(segmentos)
    sonoras = [e for e in extras if e["suena"]]
    canales_base = _canales(edicion["clip"]) if (sonoras and origen["pistas_audio"]) else 2
    silenciar_principal = "A1" in (edicion.get("pistas") or {}).get("silenciadas", [])
    for p in range(max(origen["pistas_audio"], 1 if sonoras else 0)):
        if p >= origen["pistas_audio"]:             # el clip no tiene audio: base de silencio para mezclar encima
            partes.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={_f(total)},asetpts=PTS-STARTPTS[a{p}out]")
            if p == 0:
                mapas.append("[a0mix]")
                partes.append(_mezcla_audio("a0out", sonoras, total, canales_base))
            continue
        for i, s in enumerate(segmentos):
            partes.append(f"[0:a:{p}]atrim=start={_f(s['inicio'])}:end={_f(s['fin'])},asetpts=PTS-STARTPTS[a{p}_{i}]")
        if n == 1:
            partes.append(f"[a{p}_0]anull[a{p}out]")
        else:
            partes.append("".join(f"[a{p}_{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a{p}out]")
        if p == 0 and (sonoras or silenciar_principal):
            if silenciar_principal:
                partes.append("[a0out]volume=0[a0out_m]")
                partes.append(_mezcla_audio("a0out_m", sonoras, total, canales_base))
            else:
                partes.append(_mezcla_audio("a0out", sonoras, total, canales_base))
            mapas.append("[a0mix]")
        else:
            mapas.append(f"[a{p}out]")
    return ";".join(partes), mapas


def _canales(ruta):
    """Canales de la primera pista de audio (2 si no se puede saber)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels",
                            "-of", "csv=p=0", ruta], capture_output=True, text=True, timeout=30, creationflags=_SIN_VENTANA)
        return int(r.stdout.strip().split(",")[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return 2


def _atempo(v):
    """Cadena de ``atempo`` (cada uno admite 0.5â€“2) que cambia la velocidad del audio conservando el tono."""
    if abs(v - 1.0) < 1e-4:
        return ""
    partes = []
    while v > 2.0:
        partes.append("atempo=2"); v /= 2.0
    while v < 0.5:
        partes.append("atempo=0.5"); v /= 0.5
    partes.append(f"atempo={v:.4f}")
    return "," + ",".join(partes)


def _a_estereo(canales):
    """Pasa a estÃ©reo sin bajar el volumen: el mono se duplica tal cual (el remezclado normal lo baja 3 dB)."""
    if canales == 1:
        return "pan=stereo|c0=c0|c1=c0"
    return "aformat=channel_layouts=stereo"


def _mezcla_audio(base, sonoras, total, canales_base=2):
    """Fragmentos de filtro que dejan en [a0mix] la pista principal mÃ¡s el audio de los elementos extra."""
    partes, etiquetas = [], []
    for e in sonoras:
        cadena = f"[{e['indice']}:a:0]aresample=48000,{_a_estereo(_canales(e['archivo']))},aformat=sample_fmts=fltp{_atempo(e.get('velocidad', 1.0))},volume={_f(e['volumen'])}"
        if e["fundido_in"] > 0:
            cadena += f",afade=t=in:st=0:d={_f(e['fundido_in'])}"
        if e["fundido_out"] > 0:
            cadena += f",afade=t=out:st={_f(max(0.0, e['dur'] - e['fundido_out']))}:d={_f(e['fundido_out'])}"
        retraso = int(round(e["t"] * 1000))
        if retraso > 0:
            cadena += f",adelay={retraso}|{retraso}"
        etiqueta = f"x{e['indice']}"
        partes.append(cadena + f"[{etiqueta}]")
        etiquetas.append(f"[{etiqueta}]")
    if not etiquetas:
        partes.append(f"[{base}]anull[a0mix]")
        return ";".join(partes)
    n = len(etiquetas) + 1
    norm = ":normalize=0" if amix_tiene_normalize() else ""
    compensa = "" if norm else f",volume={n}"
    partes.append(f"[{base}]aresample=48000,{_a_estereo(canales_base)},aformat=sample_fmts=fltp[ab];"
                  f"[ab]{''.join(etiquetas)}amix=inputs={n}:duration=first:dropout_transition=0{norm}{compensa},atrim=end={_f(total)}[a0mix]")
    return ";".join(partes)


def preparar_mejora_ia(edicion, ruta_clip, progreso=None, cancelar=None, mensaje=None):
    """Mejora con IA las zonas elegidas que lo necesiten. Devuelve {clave: ruta} (y "_trabajo" si hubo trabajo nuevo)."""
    cfg = edicion.get("mejora_ia") or {}
    if not cfg.get("activa"):
        return {}
    try:
        from . import editor_ia as ia
    except ImportError:
        import editor_ia as ia
    elegidas = [r for r in regiones_encuadre(edicion) if cfg.get(r["rol"])]
    if piezas_mod.tiene_piezas(edicion):
        trozos = [{"inicio": x["inicio"], "fin": x["fin"]} for x in piezas_mod.piezas_para_ia(edicion["piezas"])]
        if not trozos:
            return {}
    else:
        trozos = edicion["segmentos"]
    plan = []
    for r in elegidas:
        escala = ia.escala_necesaria(r["crop"], r["destino"], cfg.get("modelo", "rapido"))
        if escala:
            plan.append((r, escala))
    if not plan:
        return {}
    ok, ruta = ia.disponible()
    if not ok:
        raise RuntimeError(ruta)
    resultado, hubo_trabajo = {}, False
    for j, (r, escala) in enumerate(plan):
        destino = ia.ruta_cache(ruta_clip, trozos, r["crop"], escala, cfg.get("modelo", "rapido"))
        if not os.path.isfile(destino):
            hubo_trabajo = True
    for j, (r, escala) in enumerate(plan):
        etiqueta = "la cÃ¡mara" if r["rol"] == "cam" else "el juego"
        if mensaje:
            mensaje(f"Mejorando {etiqueta} con IA ({j + 1}/{len(plan)})â€¦")
        parte = lambda f, j=j: progreso and hubo_trabajo and progreso(0.6 * (j + f) / len(plan))
        try:
            resultado[r["clave"]] = ia.mejorar_region(ruta_clip, trozos, r["crop"], escala, cfg.get("modelo", "rapido"), progreso=parte, cancelar=cancelar)
        except ia.Cancelado:
            raise Cancelado()
    if mensaje:
        mensaje("Renderizandoâ€¦")
    if hubo_trabajo:
        resultado["_trabajo"] = True
    return resultado


def _libre(ruta):
    """Si ``ruta`` ya existe, devuelve Â«nombre (2).mp4Â», Â«nombre (3).mp4Â»â€¦ el primero que no exista."""
    if not os.path.exists(ruta):
        return ruta
    base, ext = os.path.splitext(ruta)
    n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def nombre_salida(ruta_clip, edicion=None, carpeta_editados="", stream="", numerar=True):
    """Ruta del clip editado.

    Con ``carpeta_editados``: <carpeta>/<stream>/<nombre>.mp4 (una carpeta por stream). Sin ella: Â«editadosÂ» junto al clip.
    El nombre es el que el usuario escribiÃ³ en el editor o, por defecto, Â«<clip>_editadoÂ». Con ``salida.no_sobrescribir``
    y ``numerar`` se aÃ±ade un nÃºmero si ya existe un archivo con ese nombre."""
    base = os.path.splitext(os.path.basename(ruta_clip))[0]
    sal = (edicion or {}).get("salida") or {}
    nombre = modelo.limpiar_nombre(sal.get("nombre"), f"{base}_editado")
    if carpeta_editados:
        carpeta = os.path.join(os.path.abspath(os.path.expanduser(carpeta_editados)), modelo.limpiar_nombre(stream, "sin_stream"))
    else:
        carpeta = os.path.join(os.path.dirname(os.path.abspath(ruta_clip)), "editados")
    destino = os.path.join(carpeta, nombre + ".mp4")
    return _libre(destino) if (numerar and sal.get("no_sobrescribir")) else destino


def _ranura_gpu(usar_nvenc):
    if usar_nvenc and os.name == "nt":
        try:
            try:
                from . import hardware_scheduler
            except ImportError:
                import hardware_scheduler
            return hardware_scheduler.gpu_slot("nvenc")
        except Exception:
            pass
    return contextlib.nullcontext()


class Cancelado(Exception):
    pass


def _entradas_danadas(entradas):
    """Prueba cada entrada de FFmpeg por separado (mismo -ss/-t) y devuelve un texto con las que no se pueden leer."""
    previos, malas = [], []
    for i, a in enumerate(entradas):
        previos.append(a)
        if a != "-i" or i + 1 >= len(entradas):
            continue
        ruta = entradas[i + 1]
        # solo las opciones que acompaÃ±an a esta entrada (desde la anterior -i)
        k = max((j for j, x in enumerate(previos[:-1]) if x == "-i"), default=-1)
        opciones = previos[k + 2:-1] if k >= 0 else previos[:-1]
        if len(malas) >= 5 or not os.path.isfile(ruta):
            if not os.path.isfile(ruta):
                malas.append(f"- No existe el archivo: {ruta}")
            continue
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", *opciones, "-i", ruta, "-f", "null", "-"], capture_output=True, text=True, timeout=90,
                               encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
            if r.returncode != 0 or r.stderr.strip():
                malas.append(f"- Entrada daÃ±ada o ilegible: {ruta} ({r.stderr.strip()[-200:]})")
        except Exception:
            pass
    return "Posible causa:\n" + "\n".join(malas) if malas else ""


def _volumen_max(ruta, opciones=(), pista=None, seek_salida=False):
    """Volumen mÃ¡ximo (dB) del audio de ``ruta``, o None si no tiene audio o no se pudo leer. Sirve para comprobar que el clip no saliÃ³ mudo."""
    try:
        if seek_salida and "-ss" in opciones:
            i = opciones.index("-ss")
            antes, despues = opciones[:i], opciones[i:]
            comando = ["ffmpeg", "-v", "info", "-nostats", *antes, "-i", ruta, *despues]
        else:
            comando = ["ffmpeg", "-v", "info", "-nostats", *opciones, "-i", ruta]
        r = subprocess.run(comando + ["-vn", *(["-map", f"0:a:{pista}"] if pista is not None else []), "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"max_volume:\s*(-?[0-9.]+|-inf)\s*dB", r.stderr or "")
    if not m:
        return None
    return -999.0 if m.group(1) == "-inf" else float(m.group(1))


def _piezas_audibles(edicion, ruta_clip, limite=8, excluir=(), sordas=None):
    """Piezas de audio sin silenciar cuya fuente suena de verdad en su tramo: lo que el clip final DEBE tener. [(pieza, segundos a comprobar)]."""
    mudas = set(edicion.get("pistas", {}).get("silenciadas", []))
    res = []
    for a in edicion.get("piezas", []):
        if a.get("tipo") != "audio" or a.get("carril") in mudas or a.get("volumen", 1.0) <= 0.05 or a.get("id") in excluir:
            continue
        archivo = ruta_clip if a.get("fuente") == "clip" else a.get("archivo")
        if not archivo or not os.path.isfile(archivo):
            continue
        ventana = min(float(a.get("dur", 5)), 10.0)
        op = ["-ss", f"{a.get('desde', 0):.3f}", "-t", f"{ventana:.3f}"]
        clip = a.get("fuente") == "clip"
        mx = _volumen_max(archivo, op, seek_salida=clip)
        if a.get("fuente") == "clip":          # un clip puede traer varias pistas: suena si suena cualquiera
            for p in range(1, min(int(edicion.get("origen", {}).get("pistas_audio", 1) or 1), 6)):
                m2 = _volumen_max(archivo, op, pista=p, seek_salida=True)
                if m2 is not None and (mx is None or m2 > mx):
                    mx = m2
        if mx is not None and mx > -50:
            res.append((a, ventana))
        elif sordas is not None:
            sordas.append(a.get("nombre") or a["id"])
        if len(res) >= limite:
            break
    return res


def _audios_que_faltan(audibles, ruta_salida):
    """Piezas que deberÃ­an oÃ­rse en el clip final pero su tramo sale (casi) mudo. Solo mira las que no se tapan con otro audio a la vez."""
    faltan = []
    for a, ventana in audibles:
        if abs(a.get("volumen", 1.0)) < 0.05 or a.get("kf", {}).get("volumen"):
            continue
        mx = _volumen_max(ruta_salida, ["-ss", f"{a['t']:.3f}", "-t", f"{ventana:.3f}"])
        if mx is None or mx < -55:
            faltan.append(a)
    return faltan


def _con_tolerancia(entradas):
    res = []
    for x in entradas:
        if x == "-i":
            res += ["-err_detect", "ignore_err", "-fflags", "+discardcorrupt+genpts"]
        res.append(x)
    return res


def _renderizar_audio(edicion, ia_listas, wavs, plano, tolerante, trabajo, nombre, hasta=None):
    """Monta SOLO el audio (sin vÃ­deo) a un WAV, con el mismo montaje que el render. Devuelve la ruta o None si FFmpeg falla."""
    try:
        from . import editor_render_piezas as rp
    except ImportError:
        import editor_render_piezas as rp
    try:
        plan = rp.planificar(edicion, ia_listas, audio_plano=plano, audio_wav=wavs or None, solo_audio=True)
    except Exception:
        return None
    if not plan["mapas"]:
        return None
    entradas = _con_tolerancia(plan["entradas"]) if tolerante else plan["entradas"]
    destino = os.path.join(trabajo, nombre)
    total = plan["total"] if hasta is None else min(plan["total"], hasta)
    comando = ["ffmpeg", "-y", "-v", "error", "-nostats"] + entradas + ["-filter_complex", plan["filtro"].replace("\n", ""), "-map", plan["mapas"][0],
                                                                       "-t", f"{total:.3f}", "-c:a", "pcm_s16le", destino]
    try:
        r = subprocess.run(comando, cwd=trabajo, capture_output=True, timeout=1800, creationflags=_SIN_VENTANA)
    except (OSError, subprocess.SubprocessError):
        return None
    return destino if r.returncode == 0 and os.path.isfile(destino) and os.path.getsize(destino) > 1000 else None


def _faltan_en_el_montaje(edicion, ia_listas, wavs, plano, tolerante, trabajo, audibles):
    """Comprueba cada pieza por SEPARADO (con las demÃ¡s quitadas) para que otro sonido no tape su ausencia. Devuelve las que no suenan."""
    faltan = []
    for n, (a, ventana) in enumerate(audibles):
        if abs(a.get("volumen", 1.0)) < 0.05 or a.get("kf", {}).get("volumen"):
            continue
        sola = copy.deepcopy(edicion)
        sola["piezas"] = [p for p in sola["piezas"] if p.get("tipo") != "audio" or p["id"] == a["id"]]
        wav = _renderizar_audio(sola, ia_listas, wavs, plano, tolerante, trabajo, f"solo_{n}.wav", hasta=a["t"] + ventana + 0.2)
        mx = _volumen_max(wav, ["-ss", f"{a['t']:.3f}", "-t", f"{ventana:.3f}"]) if wav else None
        if mx is None or mx < -55:
            faltan.append(a)
    return faltan


def _mezclar_audio(video, audio, salida):
    """Une el vÃ­deo ya renderizado (sin tocar la imagen) con un audio montado aparte. True si sale bien."""
    comando = ["ffmpeg", "-y", "-v", "error", "-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", "-shortest", "-f", "mp4", salida]
    try:
        r = subprocess.run(comando, capture_output=True, timeout=1800, creationflags=_SIN_VENTANA)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and os.path.isfile(salida) and os.path.getsize(salida) > 0


def _audio_salida_distinto(audibles, salida, referencia):
    """Piezas cuyo tramo suena en el montaje de referencia pero sale mucho mÃ¡s bajo (o mudo) en el clip final."""
    malas = []
    for a, ventana in audibles:
        if abs(a.get("volumen", 1.0)) < 0.05 or a.get("kf", {}).get("volumen"):
            continue
        op = ["-ss", f"{a['t']:.3f}", "-t", f"{ventana:.3f}"]
        ref = _volumen_max(referencia, op)
        if ref is None or ref < -50:
            continue
        out = _volumen_max(salida, op)
        if out is None or out < -55 or out < ref - 12:
            malas.append(a)
    return malas


def _detalle_audio(edicion, ruta_clip, ruta_salida):
    """Niveles por pieza del origen (pista a pista) y del tramo correspondiente de salida."""
    lineas = []
    for a in edicion.get("piezas", []):
        if a.get("tipo") != "audio":
            continue
        archivo = ruta_clip if a.get("fuente") == "clip" else a.get("archivo")
        if not archivo or not os.path.isfile(archivo):
            continue
        ventana = min(float(a.get("dur", 5)), 10.0)
        origen_op = ["-ss", f"{a.get('desde', 0):.3f}", "-t", f"{ventana:.3f}"]
        pistas = []
        n = _n_pistas_audio(archivo)
        for i in range(min(n, 6)):
            db = _volumen_max(archivo, origen_op, pista=i, seek_salida=a.get("fuente") == "clip")
            pistas.append("?" if db is None else f"{db:.1f} dB")
        salida_op = ["-ss", f"{a.get('t', 0):.3f}", "-t", f"{ventana:.3f}"]
        db_out = _volumen_max(ruta_salida, salida_op)
        nivel_out = "?" if db_out is None else f"{db_out:.1f} dB"
        lineas.append(f"  {a.get('carril', '?')} {a.get('nombre') or a.get('id')}: origen por pista [{', '.join(pistas)}]; salida {nivel_out}")
    return "\n".join(lineas)


def _n_pistas_audio(ruta):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", ruta],
                           capture_output=True, text=True, timeout=30, creationflags=_SIN_VENTANA)
        return max(1, len([x for x in r.stdout.split() if x.strip()]))
    except (OSError, subprocess.SubprocessError):
        return 1


def _extraer_audios(edicion, trabajo):
    """Decodifica aparte el audio de cada pieza de audio de un archivo aÃ±adido a un WAV limpio (48 kHz estÃ©reo, empezando en 0 y ya recortado).
    AsÃ­ ningÃºn audio problemÃ¡tico (marcas de tiempo raras, pistas mÃºltiples, datos daÃ±ados) rompe o silencia el montaje.
    Si la primera pista sale muda se prueban las demÃ¡s y se queda la que suena mÃ¡s. Devuelve {id de pieza: ruta del WAV}."""
    wavs, cache = {}, {}
    for a in edicion.get("piezas", []):
        if a.get("tipo") != "audio" or a.get("fuente") == "clip" or not a.get("archivo") or not os.path.isfile(a["archivo"]):
            continue
        clave = (a["archivo"], round(a.get("desde", 0), 3), round(piezas_mod.consumo(a), 3))
        if clave in cache:
            wavs[a["id"]] = cache[clave]
            continue
        mejor, mejor_db = None, None
        desde, dur = a.get("desde", 0), piezas_mod.consumo(a) + 0.1
        n = 0
        for i in range(min(_n_pistas_audio(a["archivo"]), 6)):
            variantes = [                      # de lo mÃ¡s simple a lo mÃ¡s tolerante; la primera que suena gana
                ["-err_detect", "ignore_err", "-ss", f"{desde:.3f}", "-i", a["archivo"], "-t", f"{dur:.3f}", "-vn", "-map", f"0:a:{i}"],
                ["-err_detect", "ignore_err", "-i", a["archivo"], "-ss", f"{desde:.3f}", "-t", f"{dur:.3f}", "-vn", "-map", f"0:a:{i}"],
                ["-err_detect", "ignore_err", "-fflags", "+genpts+discardcorrupt", "-ss", f"{desde:.3f}", "-i", a["archivo"], "-t", f"{dur:.3f}", "-vn", "-map", f"0:a:{i}",
                 "-af", "aresample=async=1000:first_pts=0"],
                ["-err_detect", "ignore_err", "-i", a["archivo"], "-vn", "-map", f"0:a:{i}", "-af", f"atrim=start={desde:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS"],
            ]
            if i == 0:         # la pista que FFmpeg elige por defecto (la de mÃ¡s canales) puede no ser la primera
                variantes.insert(0, ["-err_detect", "ignore_err", "-ss", f"{desde:.3f}", "-i", a["archivo"], "-t", f"{dur:.3f}", "-vn"])
            for v in variantes:
                n += 1
                destino = os.path.join(trabajo, f"aud_{a['id']}_{n}.wav")
                try:
                    subprocess.run(["ffmpeg", "-y", "-v", "error"] + v + ["-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le", destino],
                                   capture_output=True, timeout=1800, creationflags=_SIN_VENTANA)
                except (OSError, subprocess.SubprocessError):
                    continue
                if not (os.path.isfile(destino) and os.path.getsize(destino) > 2000):
                    continue
                db = _volumen_max(destino)
                if mejor is None or (db is not None and (mejor_db is None or db > mejor_db)):
                    mejor, mejor_db = destino, db
                if db is not None and db > -50:           # ya suena: basta
                    break
            if mejor_db is not None and mejor_db > -50:
                break
        if mejor and mejor_db is not None and mejor_db > -50:       # un WAV mudo no se usa: se deja la lectura directa del archivo
            wavs[a["id"]] = cache[clave] = mejor
    return wavs


def renderizar(edicion, ruta_clip, destino=None, progreso=None, cancelar=None, forzar_x264=False, mensaje=None):
    """Genera el clip editado. Devuelve {"archivo", "codificador", "duracion"}.

    ``progreso(fraccion)`` se llama a medida que avanza; ``cancelar`` es un threading.Event."""
    destino = destino or nombre_salida(ruta_clip)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    v2 = piezas_mod.tiene_piezas(edicion)
    duracion_total = piezas_mod.total_de(edicion)
    if duracion_total < 0.2:
        raise RuntimeError("No hay nada que renderizar: la lÃ­nea de tiempo estÃ¡ vacÃ­a.")
    sub = edicion["subtitulos"]
    con_subtitulos = bool(sub["activos"] and sub["lineas"])
    con_ass = con_subtitulos or (v2 and bool(piezas_mod.textos_activos(edicion)))
    usar_nvenc = (not forzar_x264) and nvenc_disponible()
    ia_listas = preparar_mejora_ia(edicion, ruta_clip, progreso, cancelar, mensaje)       # {clave: ruta del vÃ­deo mejorado}
    reparto = 0.0 if not ia_listas.get("_trabajo") else 0.6
    ia_listas.pop("_trabajo", None)
    with tempfile.TemporaryDirectory(prefix="mkclips_editor_") as trabajo:
        if con_ass:
            with open(os.path.join(trabajo, "subs.ass"), "w", encoding="utf-8") as f:
                f.write(piezas_mod.generar_ass(edicion) if v2 else modelo.generar_ass(edicion))
            os.makedirs(os.path.join(trabajo, "fuentes"), exist_ok=True)
            familias = ([sub["estilo"]["fuente"]] if con_subtitulos else []) + (piezas_mod.familias_de_texto(edicion) if v2 else [])
            for familia in dict.fromkeys(familias):
                fuentes.preparar_carpeta_fuentes(familia, os.path.join(trabajo, "fuentes"))
        claves_ia = sorted(ia_listas)
        if v2:
            try:
                from . import editor_render_piezas as rp
            except ImportError:
                import editor_render_piezas as rp
            plan = rp.planificar(edicion, {c: ia_listas[c] for c in claves_ia})
            filtro, mapas, entradas = plan["filtro"], plan["mapas"], plan["entradas"]
        else:
            base_idx = len(extras_activos(edicion)) + 1
            mejoradas = {clave: base_idx + j for j, clave in enumerate(claves_ia)}
            filtro, mapas = construir_filtro(edicion, con_subtitulos, mejoradas=mejoradas)
            entradas = ["-i", os.path.abspath(ruta_clip)] + argumentos_entradas_extra(extras_activos(edicion))
            for clave in claves_ia:
                entradas += ["-i", os.path.abspath(ia_listas[clave])]
        temporal = destino + f".{os.getpid()}.tmp.mp4"
        fps = min(60.0, max(24.0, round(edicion["origen"].get("fps", 30.0))))
        tolerante = False
        audio_plano = False
        wavs = _extraer_audios(edicion, trabajo) if v2 else {}                  # audios aÃ±adidos, ya decodificados aparte
        audio_wav = bool(wavs)
        sordas = []
        audibles = _piezas_audibles(edicion, ruta_clip, excluir=set(wavs), sordas=sordas) if v2 else []         # lo que el clip final debe tener sÃ­ o sÃ­
        for a in edicion.get("piezas", []) if v2 else []:
            if a["id"] in wavs and a.get("carril") not in set(edicion.get("pistas", {}).get("silenciadas", [])) and a.get("volumen", 1.0) > 0.05:
                db = _volumen_max(wavs[a["id"]])
                if db is not None and db > -50:
                    audibles.append((a, min(float(a.get("dur", 5)), 10.0)))
                else:
                    sordas.append(a.get("nombre") or a["id"])
        for a in edicion.get("piezas", []) if v2 else []:
            if a.get("tipo") == "audio" and a.get("fuente") != "clip" and a["id"] not in wavs and a.get("volumen", 1.0) > 0.05 and not any((a.get("nombre") or a["id"]) == x for x in sordas):
                sordas.append(a.get("nombre") or a["id"])
        silencio_final = False
        audio_aparte = False
        if v2 and wavs:                # el primer intento ya usa los WAV: se vuelve a planificar con ellos
            plan = rp.planificar(edicion, {c: ia_listas[c] for c in claves_ia}, audio_plano=False, audio_wav=wavs)
            filtro, mapas, entradas = plan["filtro"], plan["mapas"], plan["entradas"]
        entradas_base = list(entradas)
        for intento in range(6):
            if audio_plano and v2:     # reintento con el montaje de audio alternativo (sin concat)
                plan = rp.planificar(edicion, {c: ia_listas[c] for c in claves_ia}, audio_plano=True, audio_wav=wavs or None)
                filtro, mapas, entradas_base = plan["filtro"], plan["mapas"], plan["entradas"]
                entradas = list(entradas_base)
            if tolerante:      # Ãºltimo recurso: ignora paquetes daÃ±ados de las entradas en vez de abortar
                entradas = _con_tolerancia(entradas_base)
            comando = ["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1"] + entradas
            comando += ["-filter_complex", filtro.replace("\n", "")]
            for m in mapas:
                comando += ["-map", m]
            comando += argumentos_codificador(usar_nvenc) + ["-pix_fmt", "yuv420p", "-r", _f(fps), "-fps_mode", "cfr", "-t", _f(duracion_total),
                                                           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-f", "mp4", temporal]
            error_txt = os.path.join(trabajo, f"error{intento}.txt")
            with _ranura_gpu(usar_nvenc), open(error_txt, "w", encoding="utf-8", errors="replace") as ferr:
                proceso = subprocess.Popen(comando, cwd=trabajo, stdout=subprocess.PIPE, stderr=ferr, text=True,
                                           encoding="utf-8", errors="replace", creationflags=_SIN_VENTANA)
                try:
                    for linea in proceso.stdout:
                        if cancelar is not None and cancelar.is_set():
                            proceso.kill()
                            raise Cancelado()
                        if linea.startswith("out_time_us=") or linea.startswith("out_time_ms="):
                            try:
                                if progreso and duracion_total > 0:
                                    progreso(min(0.99, reparto + (1 - reparto) * float(linea.split("=")[1]) / 1e6 / duracion_total))
                            except ValueError:
                                pass
                    proceso.wait()
                except Cancelado:
                    proceso.wait()
                    with contextlib.suppress(OSError):
                        os.remove(temporal)
                    raise
                finally:
                    if proceso.poll() is None:
                        proceso.kill()
                    proceso.stdout.close()
            if proceso.returncode == 0 and os.path.isfile(temporal) and os.path.getsize(temporal) > 0:
                if audibles:
                    ia_a = {c: ia_listas[c] for c in claves_ia}
                    faltan = _faltan_en_el_montaje(edicion, ia_a, wavs, audio_plano, tolerante, trabajo, audibles)       # Â¿el montaje lleva cada audio?
                    if faltan and not (audio_plano and tolerante):       # debÃ­a sonar y no suena: se prueba otro montaje del audio
                        if not audio_plano:
                            audio_plano = True
                        else:
                            tolerante = True
                        with contextlib.suppress(OSError):
                            os.remove(temporal)
                        continue
                    if not faltan:              # el montaje es bueno: el clip final debe sonar igual; si no, se le pone el audio montado aparte
                        referencia = _renderizar_audio(edicion, ia_a, wavs, audio_plano, tolerante, trabajo, "referencia.wav")
                        if referencia:
                            malas = _audio_salida_distinto(audibles, temporal, referencia)
                            if malas:
                                arreglado = os.path.join(trabajo, "arreglado.mp4")
                                if _mezclar_audio(temporal, referencia, arreglado):
                                    os.replace(arreglado, temporal)
                                    audio_aparte = True
                                    malas = _audio_salida_distinto(audibles, temporal, referencia)
                                faltan = malas
                    silencio_final = bool(faltan)
                    nombres_faltan = ", ".join(a.get("nombre") or a["id"] for a in faltan)
                os.replace(temporal, destino)
                with contextlib.suppress(OSError):
                    if (audio_plano or tolerante or silencio_final or audio_aparte or sordas) and not os.environ.get("MKCLIPS_SIN_LOG"):      # solo si hubo que cambiar de montaje: ayuda a diagnosticar
                      with open(destino + ".log", "w", encoding="utf-8") as lg:
                        lg.write(f"codificador={'NVENC' if usar_nvenc else 'x264'} audio_alternativo={audio_plano} audio_wav={audio_wav} audio_aparte={audio_aparte} tolerante={tolerante} piezas_con_sonido={len(audibles)} mudo={silencio_final}\n")
                        if silencio_final:
                            lg.write("sin audio en: " + nombres_faltan + "\n")
                        if sordas:
                            lg.write("FFmpeg no ve sonido en el archivo de origen de: " + ", ".join(sordas) + "\n")
                        detalle = _detalle_audio(edicion, ruta_clip, destino)
                        if detalle:
                            lg.write("detalle del audio (origen por pista y salida por tramo):\n" + detalle + "\n")
                if progreso:
                    progreso(1.0)
                res = {"archivo": destino, "codificador": "NVENC" if usar_nvenc else "x264", "duracion": duracion_total}
                if sordas and not silencio_final:
                    res["aviso"] = "FFmpeg no detecta sonido en el origen de: " + ", ".join(sordas) + ". Mira el archivo .log junto al clip."
                if silencio_final:
                    res["aviso"] = "Falta el audio de: " + nombres_faltan + ". Revisa que ese archivo se reproduzca con sonido."
                return res
            with open(error_txt, "r", encoding="utf-8", errors="replace") as f:
                error = f.read()[-1500:]
            with contextlib.suppress(OSError):
                os.remove(temporal)
            if usar_nvenc:
                usar_nvenc = False  # NVENC fallÃ³ (sin GPU, sesiones agotadas...): se reintenta con x264
                continue
            if v2 and not audio_plano:
                audio_plano = True
                continue
            if not tolerante:
                tolerante = True
                continue
            culpables = _entradas_danadas(entradas)
            with contextlib.suppress(OSError):
                with open(destino + ".error.txt", "w", encoding="utf-8") as f:
                    f.write(" ".join(comando) + "\n\n" + error + "\n" + culpables)
            raise RuntimeError("FFmpeg no pudo generar el clip editado:\n" + error + ("\n" + culpables if culpables else "") + f"\n(Detalle guardado en {destino}.error.txt)")
    raise RuntimeError("No se pudo renderizar.")

