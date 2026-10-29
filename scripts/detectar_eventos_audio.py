import json
import os
import sys
import wave

import numpy as np
from cache_mkclips import ensure_audio_cache, guardar_identidad_artefacto


def cargar_wav_pcm_mono_16khz(ruta):
    """Carga el WAV PCM s16le de la cache compartida sin librosa/Numba."""
    try:
        with wave.open(ruta, "rb") as archivo:
            canales = archivo.getnchannels()
            frecuencia = archivo.getframerate()
            ancho_muestra = archivo.getsampwidth()
            compresion = archivo.getcomptype()
            if canales != 1 or frecuencia != 16000 or ancho_muestra != 2 or compresion != "NONE":
                raise RuntimeError(
                    "La cache de audio debe ser WAV PCM s16le, mono, 16 kHz; "
                    f"recibido: canales={canales}, frecuencia={frecuencia}, "
                    f"bytes_muestra={ancho_muestra}, compresion={compresion}."
                )
            frames = archivo.readframes(archivo.getnframes())
    except (OSError, wave.Error) as exc:
        raise RuntimeError(f"No se pudo leer el WAV cacheado: {ruta}") from exc

    if not frames:
        raise RuntimeError("El WAV cacheado no contiene muestras de audio.")
    # pcm_s16le: entero firmado de 16 bits normalizado al rango [-1, 1).
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0, frecuencia


def rms_y_tiempos(y, sr, frame_length, hop_length):
    """Equivalente NumPy de RMS centrado y timestamps usados antes con librosa."""
    y_centrado = np.pad(y, (frame_length // 2, frame_length // 2), mode="constant")
    ventanas = np.lib.stride_tricks.sliding_window_view(y_centrado, frame_length)[::hop_length]
    rms = np.sqrt(np.mean(ventanas * ventanas, axis=1))
    tiempos = np.arange(len(rms), dtype=np.float64) * hop_length / sr
    return rms, tiempos

def resolver_video_path(argumento_cli=None):
    """Prioriza la ruta explícita; conserva ultimo_video.txt para uso legacy."""
    if argumento_cli:
        video_path = os.path.abspath(os.path.expanduser(argumento_cli))
        if not os.path.isfile(video_path):
            raise FileNotFoundError(f"No se encontró el video indicado: {argumento_cli}")
        return video_path
    with open("ultimo_video.txt", "r", encoding="utf-8") as f:
        lineas = f.read().splitlines()
    if not lineas:
        raise RuntimeError("ultimo_video.txt está vacío; indica la ruta del video como argumento.")
    return lineas[0]


video_path = resolver_video_path(sys.argv[1] if len(sys.argv) > 1 else None)

# Detector conservador: combina intensidad relativa con un umbral absoluto
# adaptativo para reducir falsos positivos en ruido/musica constante.
UMBRAL_RATIO = 1.6
UMBRAL_RATIO_FUERTE = 2.2
PERCENTIL_ENERGIA_MIN = 55
DURACION_MIN_EVENTO = 0.30
SEPARACION_MERGE = 1.5
CIERRE_TOLERANCIA = 0.20

AUDIO_TEMP = ensure_audio_cache(video_path)

print("Analizando reacciones de audio con detector adaptativo...")
y, sr = cargar_wav_pcm_mono_16khz(AUDIO_TEMP)

frame_length = 2048
hop_length = 512
rms, tiempos = rms_y_tiempos(y, sr, frame_length, hop_length)

# Suavizado ligero: evita que un solo frame ruidoso cree un evento.
rms_suave = np.convolve(rms, np.ones(3) / 3.0, mode="same")

# Baseline robusto local. La mediana es menos sensible que la media a gritos
# aislados, por lo que el propio pico no infla tanto su referencia.
ventana_baseline = max(3, int(5 * sr / hop_length))
mitad = ventana_baseline // 2
padded = np.pad(rms_suave, (mitad, mitad), mode="edge")
ventanas = np.lib.stride_tricks.sliding_window_view(padded, ventana_baseline)
baseline = np.median(ventanas, axis=-1)[:len(rms_suave)]
baseline = np.maximum(baseline, 1e-6)

ratio = rms_suave / baseline
umbral_absoluto = np.percentile(rms_suave, PERCENTIL_ENERGIA_MIN)

# Un pico relativo necesita además una energía mínima. Los picos muy fuertes
# pueden entrar aunque la señal absoluta esté algo por debajo del percentil.
es_pico = (ratio > UMBRAL_RATIO) & (
    (rms_suave >= umbral_absoluto) | (ratio > UMBRAL_RATIO_FUERTE)
)

# Pequeño cierre morfológico temporal: rellena huecos muy cortos dentro de una
# reacción para no fragmentarla en varios eventos.
max_hueco_frames = max(1, int(CIERRE_TOLERANCIA * sr / hop_length))
for i in range(max_hueco_frames, len(es_pico) - max_hueco_frames):
    if not es_pico[i] and es_pico[i - max_hueco_frames] and es_pico[i + max_hueco_frames]:
        es_pico[i] = True

eventos = []
inicio_evento = None

for i, activo in enumerate(es_pico):
    if activo and inicio_evento is None:
        inicio_evento = tiempos[i]
    elif not activo and inicio_evento is not None:
        fin_evento = tiempos[i]
        if fin_evento - inicio_evento >= DURACION_MIN_EVENTO:
            eventos.append({"inicio": round(float(inicio_evento), 2), "fin": round(float(fin_evento), 2)})
        inicio_evento = None

if inicio_evento is not None and len(tiempos):
    fin_evento = tiempos[-1]
    if fin_evento - inicio_evento >= DURACION_MIN_EVENTO:
        eventos.append({"inicio": round(float(inicio_evento), 2), "fin": round(float(fin_evento), 2)})

# Fusionar eventos cercanos. El formato de salida permanece exactamente igual:
# [{
eventos_fusionados = []
for e in eventos:
    if eventos_fusionados and e["inicio"] - eventos_fusionados[-1]["fin"] <= SEPARACION_MERGE:
        eventos_fusionados[-1]["fin"] = e["fin"]
    else:
        eventos_fusionados.append(e)

with open("eventos_audio.json", "w", encoding="utf-8") as f:
    json.dump(eventos_fusionados, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto("eventos_audio.json", video_path, "eventos_audio")

print(f"\nListo. {len(eventos_fusionados)} eventos de audio guardados en eventos_audio.json")
for e in eventos_fusionados[:15]:
    print(f"  [{e['inicio']}s - {e['fin']}s]")
if len(eventos_fusionados) > 15:
    print(f"  ... y {len(eventos_fusionados) - 15} más.")
