# -*- coding: utf-8 -*-
"""Zonas de camara por video: donde esta la camara del streamer y cuando cambia de sitio.

Se guardan en ``camara_regiones.json`` (carpeta de resultados), una entrada por video.
Cada zona vale desde ``desde`` (segundos) hasta la siguiente zona. ``rect`` va normalizado
(0..1: x, y, w, h sobre el fotograma completo) o es ``None`` si en ese tramo no hay camara.
"""
from __future__ import annotations

import json
import os

VERSION = 1
LADO_MINIMO = 0.03          # una camara de menos del 3 % del ancho/alto no es una camara
NOMBRE = "camara_regiones.json"


def clave_video(ruta):
    return os.path.normcase(os.path.abspath(str(ruta)))


def _numero(valor, defecto=None):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return defecto
    return v if v == v and abs(v) != float("inf") else defecto


def normalizar_rect(rect):
    """Rect valido dentro del fotograma, o None."""
    if not isinstance(rect, dict):
        return None
    x, y, w, h = (_numero(rect.get(k)) for k in ("x", "y", "w", "h"))
    if None in (x, y, w, h):
        return None
    x, y = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    w, h = min(w, 1.0 - x), min(h, 1.0 - y)
    if w < LADO_MINIMO or h < LADO_MINIMO:
        return None
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def normalizar_zonas(zonas, duracion=None):
    """Ordena, limpia y garantiza que la primera zona empiece en 0.

    Una zona sin rect valido se trata como "sin camara desde aqui" solo si ``rect`` era
    None a proposito; un rect roto (ni None ni valido) se descarta."""
    limpias = {}
    for z in zonas if isinstance(zonas, list) else []:
        if not isinstance(z, dict):
            continue
        desde = _numero(z.get("desde"))
        if desde is None:
            continue
        desde = max(0.0, desde)
        if duracion is not None and desde >= float(duracion):
            continue
        if z.get("rect") is None:
            rect = None
        else:
            rect = normalizar_rect(z.get("rect"))
            if rect is None:
                continue
        limpias[round(desde, 2)] = rect          # misma marca de tiempo: gana la ultima
    ordenadas = sorted(limpias.items())
    if not ordenadas:
        return []
    ordenadas[0] = (0.0, ordenadas[0][1])         # la primera zona vale desde el principio
    salida = []
    for desde, rect in ordenadas:
        if salida and salida[-1]["rect"] == rect:
            continue                              # no cambia nada: no hace falta otra zona
        salida.append({"desde": desde, "rect": rect})
    return salida


def zona_en(zonas, t):
    """Zona vigente en el segundo ``t`` (None si no hay zonas)."""
    vigente = None
    for z in zonas:
        if z["desde"] <= t + 1e-6:
            vigente = z
        else:
            break
    return vigente


def tramos(zonas, duracion):
    """[(desde, hasta, rect)] cubriendo 0..duracion."""
    salida = []
    for i, z in enumerate(zonas):
        hasta = zonas[i + 1]["desde"] if i + 1 < len(zonas) else float(duracion)
        hasta = min(hasta, float(duracion))
        if hasta > z["desde"]:
            salida.append((z["desde"], hasta, z["rect"]))
    return salida


def ruta_archivo(resultados_dir):
    return os.path.join(str(resultados_dir), NOMBRE)


def leer_todo(resultados_dir):
    try:
        with open(ruta_archivo(resultados_dir), "r", encoding="utf-8") as f:
            datos = json.load(f)
        if isinstance(datos, dict) and isinstance(datos.get("videos"), dict):
            return datos
    except (OSError, ValueError):
        pass
    return {"version": VERSION, "videos": {}}


def zonas_de(resultados_dir, ruta_video):
    entrada = leer_todo(resultados_dir)["videos"].get(clave_video(ruta_video))
    return normalizar_zonas(entrada.get("zonas")) if isinstance(entrada, dict) else []


def guardar_zonas(resultados_dir, ruta_video, zonas, duracion=None):
    limpias = normalizar_zonas(zonas, duracion)
    datos = leer_todo(resultados_dir)
    clave = clave_video(ruta_video)
    if limpias:
        datos["videos"][clave] = {"video": str(ruta_video), "zonas": limpias}
    else:
        datos["videos"].pop(clave, None)
    datos["version"] = VERSION
    os.makedirs(str(resultados_dir), exist_ok=True)
    ruta = ruta_archivo(resultados_dir)
    temporal = f"{ruta}.{os.getpid()}.tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)
    return limpias
