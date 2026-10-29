import numpy as np
import librosa
import subprocess
import os
import json
import sys
import cv2
from scipy.signal import fftconvolve, find_peaks

SR = 8000
UMBRAL_CORRELACION_AUDIO = 0.45
UMBRAL_COINCIDENCIA_IMAGEN = 0.75
DISTANCIA_MIN_ENTRE_DETECCIONES = 3.0
SEGUNDOS_ENTRE_MUESTRAS_VIDEO = 1.0

CARPETA_SALIDA_CORTES_DEFECTO = "clips_referencias"


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


def buscar_sonido_en_audio(ref_path, audio_objetivo):
    temp = f"_ref_temp_{os.getpid()}.wav"
    extraer_audio_mono(ref_path, temp)
    referencia, _ = librosa.load(temp, sr=SR)
    os.remove(temp)

    ref_norm = normalizar(referencia)
    correlacion = fftconvolve(audio_objetivo, ref_norm[::-1], mode="valid")
    energia_local = np.sqrt(fftconvolve(audio_objetivo**2, np.ones(len(ref_norm)), mode="valid"))
    energia_local = np.maximum(energia_local, 1e-8)
    correlacion_normalizada = correlacion / energia_local

    tiempos = np.arange(len(correlacion_normalizada)) / SR
    picos, propiedades = find_peaks(
        correlacion_normalizada,
        height=UMBRAL_CORRELACION_AUDIO,
        distance=int(DISTANCIA_MIN_ENTRE_DETECCIONES * SR)
    )

    return [
        {"tiempo": round(float(tiempos[p]), 2), "score": round(float(propiedades["peak_heights"][i]), 3)}
        for i, p in enumerate(picos)
    ]


def buscar_imagenes_en_video(referencias_imagen, video_path, notificar=print):
    """Recorre el video UNA sola vez y compara cada frame muestreado contra
    TODAS las referencias de imagen a la vez (eficiente)."""
    templates = {}
    for ref in referencias_imagen:
        img = cv2.imread(ref["archivo"])
        if img is None:
            notificar(f"  ADVERTENCIA: no se pudo leer {ref['archivo']}, se omite.")
            continue
        templates[ref["nombre"]] = img

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"No se pudo abrir el video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        raise RuntimeError(f"No se pudo determinar el FPS del video: {video_path}")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    salto_frames = max(1, int(fps * SEGUNDOS_ENTRE_MUESTRAS_VIDEO))

    resultados = {nombre: [] for nombre in templates}
    frame_idx = 0
    muestras = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        for nombre, template in templates.items():
            resultado = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
            score = resultado.max()
            if score >= UMBRAL_COINCIDENCIA_IMAGEN:
                tiempo = frame_idx / fps
                resultados[nombre].append({"tiempo": round(tiempo, 2), "score": round(float(score), 3)})

        muestras += 1
        if muestras % 200 == 0 and total_frames:
            notificar(f"  ...progreso video: {(frame_idx/total_frames)*100:.0f}%")

        for _ in range(salto_frames - 1):
            if not cap.grab():
                break
        frame_idx += salto_frames

    cap.release()

    for nombre in resultados:
        resultados[nombre].sort(key=lambda x: x["tiempo"])
        fusionadas = []
        for d in resultados[nombre]:
            if fusionadas and d["tiempo"] - fusionadas[-1]["tiempo"] <= DISTANCIA_MIN_ENTRE_DETECCIONES:
                if d["score"] > fusionadas[-1]["score"]:
                    fusionadas[-1] = d
            else:
                fusionadas.append(d)
        resultados[nombre] = fusionadas

    return resultados


def cortar_detecciones(video_path, nombre_ref, detecciones, padding_antes, padding_despues, carpeta_salida, notificar=print):
    os.makedirs(carpeta_salida, exist_ok=True)
    rutas = []
    for idx, d in enumerate(detecciones, start=1):
        inicio = max(0, d["tiempo"] - padding_antes)
        fin = d["tiempo"] + padding_despues
        salida = os.path.join(carpeta_salida, f"{nombre_ref}_{idx:02d}.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-ss", str(inicio), "-to", str(fin),
            "-c:v", "libx264", "-c:a", "aac",
            salida
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        notificar(f"    Cortado: {os.path.basename(salida)} [{inicio:.1f}s - {fin:.1f}s]")
        rutas.append(salida)
    return rutas


def buscar_referencias(video_path, referencias, notificar=print):
    """
    referencias: lista de dicts {"nombre", "archivo", "tipo": "sonido"|"imagen"}
    Devuelve un dict {nombre: [{"tiempo":.., "score":..}, ...]}
    """
    referencias_sonido = [r for r in referencias if r["tipo"] == "sonido"]
    referencias_imagen = [r for r in referencias if r["tipo"] == "imagen"]

    resultado_final = {}

    if referencias_sonido:
        notificar(f"Extrayendo audio del video objetivo (para {len(referencias_sonido)} referencia(s) de sonido)...")
        temp = f"_objetivo_temp_{os.getpid()}.wav"
        extraer_audio_mono(video_path, temp)
        audio_objetivo, _ = librosa.load(temp, sr=SR)
        os.remove(temp)

        for ref in referencias_sonido:
            notificar(f"Buscando \"{ref['nombre']}\" (sonido)...")
            detecciones = buscar_sonido_en_audio(ref["archivo"], audio_objetivo)
            resultado_final[ref["nombre"]] = detecciones
            notificar(f"  {len(detecciones)} coincidencia(s) encontrada(s).")

    if referencias_imagen:
        notificar(f"Recorriendo video (para {len(referencias_imagen)} referencia(s) de imagen)...")
        detecciones_imagen = buscar_imagenes_en_video(referencias_imagen, video_path, notificar=notificar)
        for nombre, detecciones in detecciones_imagen.items():
            resultado_final[nombre] = detecciones
            notificar(f"  \"{nombre}\": {len(detecciones)} coincidencia(s) encontrada(s).")

    return resultado_final


def _main_interactivo():
    # Lista de referencias para uso directo por consola. Edita esta lista
    # con tus archivos de sonido/imagen antes de correr el script asi.
    REFERENCIAS = [
        # {"nombre": "jefe_derrotado", "archivo": "referencias/jefe_derrotado.wav", "tipo": "sonido", "padding_antes": 25, "padding_despues": 5},
        # {"nombre": "piedra_suerte", "archivo": "referencias/piedra_suerte.png", "tipo": "imagen", "padding_antes": 5, "padding_despues": 10},
    ]
    CORTAR_CLIPS_AUTOMATICAMENTE = False

    if len(sys.argv) < 2:
        print("Uso: python buscar_multiples_referencias.py <video_objetivo.mp4>")
        print("\nAntes de correr, edita la lista REFERENCIAS al inicio de _main_interactivo()")
        print("con tus archivos de sonido/imagen de referencia.")
        sys.exit(1)

    video_path = sys.argv[1]

    if not REFERENCIAS:
        print("No hay referencias configuradas. Edita la lista REFERENCIAS en este script.")
        sys.exit(1)

    resultado_final = buscar_referencias(video_path, REFERENCIAS, notificar=print)

    print("\n=== RESUMEN ===")
    for nombre, detecciones in resultado_final.items():
        print(f"\n{nombre} ({len(detecciones)} veces):")
        for d in detecciones:
            minutos = int(d["tiempo"] // 60)
            segs = d["tiempo"] % 60
            print(f"  {minutos:02d}:{segs:05.2f} - score: {d['score']}")

    with open("resultados_multiples_referencias.json", "w", encoding="utf-8") as f:
        json.dump(resultado_final, f, ensure_ascii=False, indent=2)
    print("\nGuardado en resultados_multiples_referencias.json")

    if CORTAR_CLIPS_AUTOMATICAMENTE:
        print("\nCortando clips con margenes configurados...")
        for ref in REFERENCIAS:
            detecciones = resultado_final.get(ref["nombre"], [])
            if detecciones:
                print(f"\n\"{ref['nombre']}\":")
                cortar_detecciones(
                    video_path, ref["nombre"], detecciones,
                    ref.get("padding_antes", 15), ref.get("padding_despues", 5),
                    CARPETA_SALIDA_CORTES_DEFECTO
                )
        print(f"\nListo. Clips guardados en: {CARPETA_SALIDA_CORTES_DEFECTO}")
    else:
        print("\n(CORTAR_CLIPS_AUTOMATICAMENTE esta en False.)")


if __name__ == "__main__":
    _main_interactivo()
