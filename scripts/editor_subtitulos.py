# -*- coding: utf-8 -*-
"""Subtítulos del editor: texto con tiempo por palabra.

Dos orígenes, ambos gratis y locales:
  * ``desde_whisper``: transcribe el clip con faster-whisper (el mismo large-v3 que usa el pipeline,
    así que no descarga nada nuevo) pidiendo el tiempo de cada palabra. Es lo más preciso.
  * ``desde_transcripcion``: reutiliza la transcripción del stream cuando el clip se montó con
    segmentos exactos (sin esperar). Los tiempos de cada palabra se reparten de forma proporcional.
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile

try:
    from . import editor_modelo as modelo
except ImportError:
    import editor_modelo as modelo

_SIN_VENTANA = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
MODELO_WHISPER = "large-v3"
FIN_DE_FRASE = (".", "?", "!", "…")


def agrupar_palabras(palabras, pausa=0.7, max_palabras=9, max_duracion=4.5):
    """Convierte palabras con tiempo en líneas de subtítulo.

    Se corta en una pausa larga, al terminar una frase (si la línea ya tiene 3+ palabras) o
    cuando la línea se hace demasiado larga."""
    lineas, actual = [], []

    def cerrar():
        if actual:
            lineas.append({"inicio": actual[0]["inicio"], "fin": actual[-1]["fin"], "texto": " ".join(p["texto"] for p in actual),
                           "palabras": [dict(p) for p in actual]})
            actual.clear()

    for palabra in palabras:
        texto = str(palabra.get("texto", "")).strip()
        if not texto:
            continue
        p = {"inicio": round(float(palabra["inicio"]), 3), "fin": round(float(palabra["fin"]), 3), "texto": texto}
        if actual:
            hueco = p["inicio"] - actual[-1]["fin"]
            if (hueco > pausa or len(actual) >= max_palabras or p["fin"] - actual[0]["inicio"] > max_duracion
                    or (len(actual) >= 3 and actual[-1]["texto"].endswith(FIN_DE_FRASE))):
                cerrar()
        actual.append(p)
    cerrar()
    return lineas


# ----------------------------------------------------------------------------- Whisper
def _dispositivo():
    """('cuda', 'float16') si hay GPU NVIDIA utilizable; si no ('cpu', 'int8')."""
    try:
        try:
            from . import transcribir
        except ImportError:
            import transcribir
        if transcribir._gpu_disponible():
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _cargar_modelo_whisper():
    dispositivo, tipo = _dispositivo()
    if dispositivo == "cuda":
        with contextlib.suppress(Exception):
            try:
                from . import transcribir
            except ImportError:
                import transcribir
            transcribir._agregar_rutas_dll_nvidia()
    from faster_whisper import WhisperModel      # import tardío: solo si se pide transcribir
    try:
        return WhisperModel(MODELO_WHISPER, device=dispositivo, compute_type=tipo)
    except Exception:
        if dispositivo == "cuda":                # la GPU falló al cargar: se reintenta en CPU
            return WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
        raise


def desde_whisper(ruta_clip, notificar=None, cargar_modelo=None):
    """Líneas con palabras cronometradas, transcribiendo la primera pista de audio del clip."""
    notificar = notificar or (lambda _m: None)
    with tempfile.TemporaryDirectory(prefix="mkclips_sub_") as trabajo:
        wav = os.path.join(trabajo, "audio.wav")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", ruta_clip, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", wav],
                           capture_output=True, text=True, creationflags=_SIN_VENTANA)
        if r.returncode != 0 or not os.path.isfile(wav):
            raise RuntimeError("El clip no tiene audio que transcribir.")
        notificar("Cargando el modelo de transcripción…")
        try:
            modelo_whisper = (cargar_modelo or _cargar_modelo_whisper)()
        except ImportError:
            raise RuntimeError("Falta faster-whisper (pip install faster-whisper), el mismo que usa la transcripción del pipeline.")
        notificar("Transcribiendo el clip…")
        segmentos, _info = modelo_whisper.transcribe(wav, word_timestamps=True, language="es", vad_filter=True, beam_size=5)
        palabras = []
        for segmento in segmentos:
            for w in (getattr(segmento, "words", None) or []):
                texto = str(w.word).strip()
                if texto:
                    palabras.append({"inicio": float(w.start), "fin": float(w.end), "texto": texto})
    if not palabras:
        raise RuntimeError("No se detectó voz en el clip.")
    return agrupar_palabras(palabras)


# ----------------------------------------------------------------------------- transcripción del stream
def desde_transcripcion(segmentos_clip, transcripcion):
    """Líneas del clip a partir de la transcripción del stream, o [] si el clip no tiene segmentos exactos.

    ``segmentos_clip``: [{"inicio","fin"}] en segundos del STREAM, en el orden en que se montó el clip."""
    if not segmentos_clip or not transcripcion:
        return []
    lineas, acumulado = [], 0.0
    for tramo in segmentos_clip:
        a, b = float(tramo["inicio"]), float(tramo["fin"])
        if b <= a:
            continue
        for seg in transcripcion:
            try:
                si, sf, texto = float(seg["inicio"]), float(seg["fin"]), str(seg["texto"]).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if not texto or sf <= a or si >= b:
                continue
            palabras = []
            for w in modelo.repartir_palabras(texto, si, sf):
                medio = (w["inicio"] + w["fin"]) / 2.0
                if a <= medio <= b:
                    palabras.append({"inicio": round(acumulado + w["inicio"] - a, 3), "fin": round(acumulado + w["fin"] - a, 3), "texto": w["texto"]})
            if palabras:
                lineas.append({"inicio": palabras[0]["inicio"], "fin": palabras[-1]["fin"],
                               "texto": " ".join(p["texto"] for p in palabras), "palabras": palabras})
        acumulado += b - a
    return lineas
