# -*- coding: utf-8 -*-
"""Movimiento SOLO dentro del recuadro de la camara del streamer.

No usa IA ni mira el sonido: sirve para encontrar bailes, caidas o gestos que no dejan
rastro en la transcripcion (por ejemplo con el microfono suprimido). Compara fotogramas
consecutivos del recuadro (la zona vigente en cada momento) y mide que parte de los pixeles
cambia. Un movimiento sostenido es "movimiento_sostenido" (baile); uno breve y fuerte,
"pico_brusco" (caida, susto, salto). Es una pista, no un veredicto: puede confundir un
cambio de escena de OBS o un movimiento banal con algo gracioso.
"""
from __future__ import annotations

import json
import os
import subprocess

np = None

def _obtener_numpy():
    global np
    if np is None:
        import numpy as modulo_numpy
        np = modulo_numpy
    return np

try:
    from .camara_modelo import tramos
except ImportError:  # modulo suelto desde scripts/
    from camara_modelo import tramos

VERSION = 1
FPS_ANALISIS = 5.0           # muestras por segundo
LADO = 64                    # el recuadro se reduce a LADO x LADO (en gris)
CAMBIO_PIXEL = 16            # diferencia (0-255) a partir de la que un pixel "cambio"
VENTANA_SUAVIZADO = 1.0      # s
PISO_ABSOLUTO = 0.08         # al menos 8 % de pixeles cambiando para contar como movimiento
SIGMAS = 5.0                 # y 5 desviaciones por encima del ruido normal de esa camara
UNION_HUECO = 1.0            # dos movimientos separados por menos de esto son uno solo
DURACION_MINIMA = 0.6        # s
SOSTENIDO_DESDE = 3.0        # s con movimiento -> sostenido; menos -> pico brusco
MARGEN_CLIP = 4.0            # s de contexto antes y despues
MAX_EVENTOS = 80


class Cancelado(Exception):
    pass


def info_video(ruta):
    """{"ancho", "alto", "duracion"} con ffprobe; lanza RuntimeError si no se puede."""
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(ruta)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        datos = json.loads(p.stdout or "{}")
        flujo = (datos.get("streams") or [{}])[0]
        info = {"ancho": int(flujo["width"]), "alto": int(flujo["height"]),
                "duracion": float(datos["format"]["duration"])}
    except FileNotFoundError as exc:
        raise RuntimeError("No se encontro ffprobe en PATH.") from exc
    except (KeyError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("No se pudo leer el video (ffprobe).") from exc
    if info["ancho"] <= 0 or info["alto"] <= 0 or info["duracion"] <= 0:
        raise RuntimeError("El video no tiene dimensiones o duracion validas.")
    return info


def _filtro(rect, ancho, alto):
    x, y = int(rect["x"] * ancho), int(rect["y"] * alto)
    w, h = int(rect["w"] * ancho), int(rect["h"] * alto)
    w, h = max(2, w - w % 2), max(2, h - h % 2)
    x, y = min(x, max(0, ancho - w)), min(y, max(0, alto - h))
    return f"crop={w}:{h}:{x}:{y},fps={FPS_ANALISIS:g},scale={LADO}:{LADO}:flags=area,format=gray"


def _fotogramas(ruta, desde, duracion, rect, ancho, alto, aceleracion):
    """Genera arrays LADOxLADO (uint8) del recuadro; ``aceleracion`` usa el decodificador por hardware."""
    orden = ["ffmpeg", "-v", "error", "-nostdin"]
    if aceleracion:
        orden += ["-hwaccel", "auto"]
    orden += ["-ss", f"{desde:.3f}", "-t", f"{duracion:.3f}", "-i", str(ruta), "-an", "-sn",
              "-vf", _filtro(rect, ancho, alto), "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proceso = subprocess.Popen(orden, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    tam = LADO * LADO
    try:
        while True:
            bloque = proceso.stdout.read(tam)
            if len(bloque) < tam:
                break
            yield np.frombuffer(bloque, dtype=np.uint8).reshape(LADO, LADO)
    finally:
        try:
            proceso.stdout.close()
        except OSError:
            pass
        proceso.kill() if proceso.poll() is None else None
        proceso.wait()


def serie_del_tramo(ruta, desde, hasta, rect, ancho, alto, cancelar=None, avance=None):
    """[(t, fraccion_de_pixeles_que_cambio)] de un tramo con una camara en ``rect``."""
    _obtener_numpy()
    salida = []
    for aceleracion in (True, False):
        salida, anterior, n = [], None, 0
        for cuadro in _fotogramas(ruta, desde, hasta - desde, rect, ancho, alto, aceleracion):
            if cancelar is not None and cancelar():
                raise Cancelado()
            if anterior is not None:
                cambio = float(np.mean(np.abs(cuadro.astype(np.int16) - anterior.astype(np.int16)) > CAMBIO_PIXEL))
                salida.append((desde + n / FPS_ANALISIS, cambio))
                if avance is not None and n % 50 == 0:
                    avance(desde + n / FPS_ANALISIS)
            anterior, n = cuadro, n + 1
        if salida or not aceleracion:
            break                                  # con aceleracion no salio nada: reintenta sin ella
    return salida


def suavizar(valores, fps=FPS_ANALISIS, ventana=VENTANA_SUAVIZADO):
    np = _obtener_numpy()
    n = max(1, int(round(ventana * fps)))
    if n == 1 or len(valores) < n:
        return np.asarray(valores, dtype=float)
    nucleo = np.ones(n) / n
    return np.convolve(np.asarray(valores, dtype=float), nucleo, mode="same")


def umbral_de(valores):
    """Umbral por camara: ruido normal + SIGMAS desviaciones, y nunca menos que PISO_ABSOLUTO."""
    np = _obtener_numpy()
    v = np.asarray(valores, dtype=float)
    if v.size == 0:
        return PISO_ABSOLUTO
    mediana = float(np.median(v))
    mad = float(np.median(np.abs(v - mediana))) * 1.4826
    return max(mediana + SIGMAS * mad, PISO_ABSOLUTO)


def detectar_eventos(tiempos, crudo, umbral, duracion):
    """Agrupa los instantes por encima del umbral en eventos (ver el docstring del modulo)."""
    np = _obtener_numpy()
    t = np.asarray(tiempos, dtype=float)
    c = np.asarray(crudo, dtype=float)
    if t.size == 0:
        return []
    s = suavizar(c)
    arriba = s > umbral
    grupos, i = [], 0
    while i < len(arriba):
        if not arriba[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(arriba) and arriba[j + 1]:
            j += 1
        grupos.append([i, j])
        i = j + 1
    unidos = []
    for g in grupos:
        if unidos and t[g[0]] - t[unidos[-1][1]] <= UNION_HUECO:
            unidos[-1][1] = g[1]
        else:
            unidos.append(g)
    eventos = []
    for i, j in unidos:
        ini, fin = float(t[i]), float(t[j]) + 1.0 / FPS_ANALISIS
        if fin - ini < DURACION_MINIMA:
            continue
        zona = s[i:j + 1]
        pico = int(np.argmax(zona)) + i
        eventos.append({
            "inicio": round(max(0.0, ini - MARGEN_CLIP), 2), "fin": round(min(float(duracion), fin + MARGEN_CLIP), 2),
            "movimiento_inicio": round(ini, 2), "movimiento_fin": round(fin, 2), "pico_t": round(float(t[pico]), 2),
            "tipo": "movimiento_sostenido" if fin - ini >= SOSTENIDO_DESDE else "pico_brusco",
            "fuerza": round(float(s[pico]) / umbral, 2), "energia_media": round(float(np.mean(zona)), 3),
            # Si casi todo el recuadro cambia de golpe y dura poco suele ser un cambio de escena de OBS.
            "sospechoso_cambio_de_escena": bool(float(np.max(c[i:j + 1])) > 0.9 and int(np.sum(c[i:j + 1] > 0.5)) <= 3),
        })
    eventos.sort(key=lambda e: -e["fuerza"])
    return sorted(eventos[:MAX_EVENTOS], key=lambda e: e["inicio"])


def analizar(ruta, zonas, progreso=None, cancelar=None, info=None):
    """Analiza todo el video con las zonas dadas. ``progreso(fraccion, texto)`` es opcional."""
    info = info or info_video(ruta)
    ancho, alto, duracion = info["ancho"], info["alto"], info["duracion"]
    partes = [(d, h, r) for d, h, r in tramos(zonas, duracion) if r is not None]
    if not partes:
        raise ValueError("No hay ninguna zona de camara marcada.")
    total = sum(h - d for d, h, _ in partes)
    hecho, tiempos, crudo = 0.0, [], []
    for d, h, rect in partes:
        def avance(t, base=hecho, d=d):
            if progreso is not None:
                progreso(min(0.99, (base + (t - d)) / total), f"Analizando {int(t // 60)}:{int(t % 60):02d} de {int(duracion // 60)}:{int(duracion % 60):02d}")
        serie = serie_del_tramo(ruta, d, h, rect, ancho, alto, cancelar, avance)
        tiempos += [t for t, _ in serie]
        crudo += [v for _, v in serie]
        hecho += h - d
    umbral = umbral_de(crudo)
    eventos = detectar_eventos(tiempos, crudo, umbral, duracion)
    # Serie a 1 muestra por segundo (maximo del segundo) para dibujar la linea de tiempo.
    por_segundo = {}
    for t, v in zip(tiempos, crudo):
        k = int(t)
        por_segundo[k] = max(por_segundo.get(k, 0.0), v)
    return {"version": VERSION, "video": str(ruta), "duracion": round(duracion, 2), "zonas": zonas, "umbral": round(umbral, 4),
            "muestras": len(crudo), "eventos": eventos,
            "serie": [[k, round(v, 3)] for k, v in sorted(por_segundo.items())]}


def guardar(resultados_dir, datos):
    os.makedirs(str(resultados_dir), exist_ok=True)
    ruta = os.path.join(str(resultados_dir), "eventos_camara.json")
    temporal = f"{ruta}.{os.getpid()}.tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(temporal, ruta)
    try:
        from cache_mkclips import guardar_identidad_artefacto
        guardar_identidad_artefacto(ruta, datos["video"], "eventos_camara")
    except Exception:
        pass                                         # el JSON ya esta; la huella es un extra
    return ruta
