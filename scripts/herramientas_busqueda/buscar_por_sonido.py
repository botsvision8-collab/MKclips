import numpy as np
import librosa
import subprocess
import os
import json
import sys
from scipy.signal import fftconvolve, find_peaks

SR = 8000  # suficiente para reconocer sonidos/jingles, y mucho mas rapido que 16-44khz
UMBRAL_CORRELACION = 0.45  # que tan parecido debe ser (0-1). Bajar si no detecta, subir si detecta de mas.
DISTANCIA_MIN_ENTRE_DETECCIONES = 3  # segundos minimos entre dos detecciones distintas

def extraer_audio_mono(video_path, salida_wav, sr=SR):
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(sr),
        salida_wav
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def normalizar(x):
    x = x - np.mean(x)
    norma = np.linalg.norm(x)
    return x / norma if norma > 0 else x

def buscar_sonido(ref_path, video_objetivo_path):
    print("Extrayendo audio de referencia...")
    extraer_audio_mono(ref_path, "_ref_temp.wav")
    referencia, _ = librosa.load("_ref_temp.wav", sr=SR)
    os.remove("_ref_temp.wav")

    print("Extrayendo audio del video objetivo (puede tardar si es largo)...")
    extraer_audio_mono(video_objetivo_path, "_objetivo_temp.wav")
    objetivo, _ = librosa.load("_objetivo_temp.wav", sr=SR)
    os.remove("_objetivo_temp.wav")

    print(f"Referencia: {len(referencia)/SR:.1f}s | Video objetivo: {len(objetivo)/SR/60:.1f} min")
    print("Calculando correlacion (huella de audio)...")

    ref_norm = normalizar(referencia)
    correlacion = fftconvolve(objetivo, ref_norm[::-1], mode="valid")

    energia_local = np.sqrt(fftconvolve(objetivo**2, np.ones(len(ref_norm)), mode="valid"))
    energia_local = np.maximum(energia_local, 1e-8)
    correlacion_normalizada = correlacion / energia_local

    tiempos = np.arange(len(correlacion_normalizada)) / SR

    picos, propiedades = find_peaks(
        correlacion_normalizada,
        height=UMBRAL_CORRELACION,
        distance=int(DISTANCIA_MIN_ENTRE_DETECCIONES * SR)
    )

    resultados = []
    for idx, p in enumerate(picos):
        resultados.append({
            "tiempo": round(float(tiempos[p]), 2),
            "score": round(float(propiedades["peak_heights"][idx]), 3)
        })

    resultados.sort(key=lambda x: x["tiempo"])
    return resultados

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python buscar_por_sonido.py <referencia.wav_o_mp4> <video_objetivo.mp4>")
        print("\nLa referencia debe ser un archivo corto (2-5s) con SOLO el sonido que quieres buscar.")
        sys.exit(1)

    ref_path = sys.argv[1]
    video_path = sys.argv[2]

    resultados = buscar_sonido(ref_path, video_path)

    print(f"\n{len(resultados)} coincidencias encontradas:")
    for r in resultados:
        minutos = int(r["tiempo"] // 60)
        segs = r["tiempo"] % 60
        print(f"  {minutos:02d}:{segs:05.2f} (segundo {r['tiempo']}) - score: {r['score']}")

    with open("resultados_busqueda_sonido.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en resultados_busqueda_sonido.json")
