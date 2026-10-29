#!/usr/bin/env python3
"""Detector visual ligero e independiente para MKClips.

Muestrea el video con ffmpeg a baja frecuencia y detecta cambios mediante
comparacion de pixeles e histogramas. No usa modelos de vision ni modifica el
video ni ningun resultado de los modulos existentes.

Velocidad: si el video tiene fotogramas clave frecuentes (lo normal en OBS) solo
se decodifican esos fotogramas (``-skip_frame nokey``), unas 15 veces mas rapido
que decodificar todos para quedarse con uno cada 2 s. Si el video tiene pocos
fotogramas clave, o algo no cuadra, se usa el metodo completo de siempre.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from typing import Any

from cache_mkclips import guardar_identidad_artefacto


VERSION = "1.0.0"
ANCHO_MUESTRA = 160
ALTO_MUESTRA = 90
UMBRAL_CAMBIO = 0.16
# El muestreo por fotogramas clave solo se usa si estan, como mucho, a esta
# distancia mediana (s): con claves muy separadas se perderian cambios.
SEPARACION_MAXIMA_CLAVES = 5.0
MINIMO_CLAVES = 10


def obtener_duracion(video: Path) -> float:
    """Obtiene la duracion real con ffprobe y valida el resultado."""
    try:
        resultado = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(video),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("No se encontro ffprobe en PATH.") from exc

    valor = resultado.stdout.strip()
    try:
        duracion = float(valor)
    except ValueError as exc:
        detalle = resultado.stderr.strip() or "ffprobe no devolvio una duracion."
        raise RuntimeError(f"No se pudo obtener una duracion valida: {detalle}") from exc

    if resultado.returncode != 0 or not math.isfinite(duracion) or duracion <= 0:
        detalle = resultado.stderr.strip() or f"valor recibido: {valor!r}"
        raise RuntimeError(f"El video no tiene una duracion valida ({detalle}).")
    return duracion


def histograma_y_diferencia(actual: bytes, anterior: bytes) -> tuple[float, float]:
    """Distancias visuales vectorizadas con NumPy para evitar bucles Python por píxel."""
    a = np.frombuffer(actual, dtype=np.uint8)
    b = np.frombuffer(anterior, dtype=np.uint8)
    if a.size != b.size or a.size == 0:
        return 0.0, 0.0
    diferencia_pixeles = float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()) / 255.0
    bins_actual = np.bincount(a >> 4, minlength=16)
    bins_anterior = np.bincount(b >> 4, minlength=16)
    diferencia_histograma = float(np.abs(bins_actual - bins_anterior).sum()) / (2.0 * a.size)
    return diferencia_histograma, diferencia_pixeles


def agrupar_eventos(
    candidatos: list[dict[str, float]], intervalo: float, duracion: float
) -> list[dict[str, Any]]:
    """Agrupa cambios cercanos para reducir duplicados y ruido."""
    if not candidatos:
        return []

    grupos: list[list[dict[str, float]]] = [[candidatos[0]]]
    separacion_maxima = max(intervalo * 1.75, 0.0)
    for candidato in candidatos[1:]:
        if candidato["tiempo"] - grupos[-1][-1]["tiempo"] <= separacion_maxima:
            grupos[-1].append(candidato)
        else:
            grupos.append([candidato])

    eventos: list[dict[str, Any]] = []
    for grupo in grupos:
        inicio = max(0.0, grupo[0].get("desde", grupo[0]["tiempo"] - intervalo))
        fin = min(duracion, grupo[-1]["tiempo"])
        if fin <= inicio:
            fin = min(duracion, inicio + min(intervalo, 0.1))
        intensidad = max(item["puntaje"] for item in grupo)
        confianza = min(0.99, round(0.55 + intensidad * 1.8, 2))
        eventos.append(
            {
                "inicio": round(inicio, 3),
                "fin": round(fin, 3),
                "tipo": "cambio_visual",
                "descripcion": "Cambio visual importante detectado",
                "confianza": confianza,
            }
        )
    return eventos


def _filtro_escala() -> str:
    return (
        f"scale={ANCHO_MUESTRA}:{ALTO_MUESTRA}:force_original_aspect_ratio=decrease,"
        f"pad={ANCHO_MUESTRA}:{ALTO_MUESTRA}:(ow-iw)/2:(oh-ih)/2,format=gray"
    )


def tiempos_fotogramas_clave(video: Path) -> list[float]:
    """Instantes de los fotogramas clave, leidos de los paquetes (no decodifica nada)."""
    try:
        resultado = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
    except OSError:
        return []
    if resultado.returncode != 0:
        return []
    tiempos: list[float] = []
    for linea in resultado.stdout.splitlines():
        partes = linea.strip().split(",")
        if len(partes) >= 2 and "K" in partes[1]:
            try:
                valor = float(partes[0])
            except ValueError:
                continue
            if math.isfinite(valor):
                tiempos.append(valor)
    return sorted(tiempos)


def _claves_son_utiles(tiempos: list[float]) -> bool:
    if len(tiempos) < MINIMO_CLAVES:
        return False
    separaciones = [b - a for a, b in zip(tiempos, tiempos[1:]) if b > a]
    return bool(separaciones) and statistics.median(separaciones) <= SEPARACION_MAXIMA_CLAVES


def _leer_frames(comando: list[str], tamano_frame: int):
    """Genera los fotogramas (bytes) que ffmpeg escribe por stdout; al terminar comprueba su codigo."""
    try:
        proceso = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise RuntimeError("No se encontro ffmpeg en PATH.") from exc
    assert proceso.stdout is not None
    while True:
        frame = proceso.stdout.read(tamano_frame)
        if not frame:
            break
        if len(frame) != tamano_frame:
            proceso.kill()
            raise RuntimeError("ffmpeg devolvio un frame visual incompleto.")
        yield frame
    stderr = proceso.stderr.read().decode("utf-8", errors="replace") if proceso.stderr else ""
    codigo = proceso.wait()
    if codigo != 0:
        raise RuntimeError(f"ffmpeg no pudo analizar el video: {stderr.strip() or codigo}")


def _comparar(frames, tiempos: list[float]) -> tuple[list[dict[str, float]], int]:
    """Compara cada fotograma con el anterior; ``tiempos[i]`` es el instante del fotograma i."""
    anterior: bytes | None = None
    candidatos: list[dict[str, float]] = []
    total = 0
    for indice, frame in enumerate(frames):
        total += 1
        if anterior is not None and indice < len(tiempos):
            histograma, pixeles = histograma_y_diferencia(frame, anterior)
            puntaje = 0.65 * pixeles + 0.35 * histograma
            # La segunda condicion evita que variaciones leves de compresion creen ruido.
            if puntaje >= UMBRAL_CAMBIO and (histograma >= 0.045 or pixeles >= 0.20):
                candidatos.append({"tiempo": tiempos[indice], "desde": tiempos[indice - 1], "puntaje": puntaje})
        anterior = frame
    return candidatos, total


def _analizar_por_claves(video: Path, tiempos: list[float]) -> tuple[list[dict[str, float]], int]:
    """Decodifica solo los fotogramas clave. Lanza RuntimeError si ffmpeg no coincide con ffprobe."""
    ultimo_error: Exception | None = None
    for opcion in (["-fps_mode", "passthrough"], ["-vsync", "passthrough"]):
        comando = [
            "ffmpeg", "-v", "error", "-skip_frame", "nokey", "-i", str(video), "-an",
            "-vf", _filtro_escala(), *opcion, "-pix_fmt", "gray", "-f", "rawvideo", "-",
        ]
        try:
            candidatos, total = _comparar(_leer_frames(comando, ANCHO_MUESTRA * ALTO_MUESTRA), tiempos)
        except RuntimeError as exc:  # opcion no soportada por esta version de ffmpeg
            ultimo_error = exc
            continue
        if total != len(tiempos):
            raise RuntimeError(f"fotogramas clave: ffmpeg decodifico {total} y ffprobe listo {len(tiempos)}")
        return candidatos, total
    raise RuntimeError(str(ultimo_error))


class _TiemposRegulares:
    """Instante de la muestra ``i`` cuando se toma una cada ``intervalo`` segundos."""

    def __init__(self, intervalo: float, duracion: float):
        self.intervalo, self.duracion = intervalo, duracion

    def __len__(self) -> int:
        return 10**9

    def __getitem__(self, indice: int) -> float:
        return min(self.duracion, max(0, indice) * self.intervalo)


def _analizar_completo(video: Path, intervalo: float, duracion: float) -> tuple[list[dict[str, float]], int]:
    """Metodo de siempre: decodifica todo el video y se queda con un fotograma cada ``intervalo`` s."""
    comando = [
        "ffmpeg", "-v", "error", "-i", str(video), "-an", "-vf", f"fps=1/{intervalo},{_filtro_escala()}",
        "-pix_fmt", "gray", "-f", "rawvideo", "-",
    ]
    return _comparar(_leer_frames(comando, ANCHO_MUESTRA * ALTO_MUESTRA), _TiemposRegulares(intervalo, duracion))


def analizar(video: Path, intervalo: float, duracion: float) -> tuple[list[dict[str, Any]], int]:
    """Devuelve (eventos visuales, fotogramas analizados)."""
    tiempos = tiempos_fotogramas_clave(video)
    if _claves_son_utiles(tiempos):
        try:
            candidatos, frames = _analizar_por_claves(video, tiempos)
            return agrupar_eventos(candidatos, statistics.median([b - a for a, b in zip(tiempos, tiempos[1:]) if b > a]), duracion), frames
        except RuntimeError as exc:
            print(f"Aviso: muestreo por fotogramas clave no disponible ({exc}); se usa el metodo completo.", file=sys.stderr)
    candidatos, frames = _analizar_completo(video, intervalo, duracion)
    if frames == 0:
        raise RuntimeError("No se pudo extraer ningun frame del video.")
    return agrupar_eventos(candidatos, intervalo, duracion), frames


def escribir_json(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
        archivo.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detecta eventos visuales ligeros en un MP4/MKV.")
    parser.add_argument("video", help="Ruta absoluta o relativa del video MP4/MKV.")
    parser.add_argument(
        "--intervalo", type=float, default=2.0,
        help="Segundos entre muestras visuales (predeterminado: 2.0).",
    )
    args = parser.parse_args()
    if not math.isfinite(args.intervalo) or args.intervalo <= 0:
        parser.error("--intervalo debe ser un numero mayor que cero.")

    video = Path(args.video).expanduser().resolve()
    if not video.is_file():
        print(f"Error: no existe el archivo de video: {video}", file=sys.stderr)
        return 1

    inicio_analisis = time.perf_counter()
    try:
        duracion = obtener_duracion(video)
        eventos, frames = analizar(video, args.intervalo, duracion)
        tiempo_analisis = round(time.perf_counter() - inicio_analisis, 3)

        try:
            from config import CARPETA_RESULTADOS
        except Exception:
            CARPETA_RESULTADOS = ""
        if CARPETA_RESULTADOS:
            carpeta_resultados = Path(CARPETA_RESULTADOS)
        else:
            try:
                from rutas_app import datos_dir
            except ImportError:
                from .rutas_app import datos_dir
            carpeta_resultados = datos_dir() / "resultados"
        ruta_eventos = carpeta_resultados / "eventos_visuales.json"
        escribir_json(ruta_eventos, eventos)
        fuente = guardar_identidad_artefacto(str(ruta_eventos), str(video), "eventos_visuales")["fuente"]
        escribir_json(
            carpeta_resultados / "metricas_visual.json",
            {
                "video": str(video),
                "fuente": fuente,
                "duracion_video": round(duracion, 3),
                "frames_muestreados": frames,
                "eventos_detectados": len(eventos),
                "tiempo_analisis": tiempo_analisis,
                "metodo": "Muestreo FFmpeg en escala de grises; diferencia de pixeles e histogramas, con agrupacion temporal.",
                "version": VERSION,
            },
        )
    except (RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Analisis visual completado: {frames} frames, {len(eventos)} eventos, {tiempo_analisis:.3f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
