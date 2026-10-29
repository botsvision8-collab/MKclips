import cv2
import numpy as np
import sys
import json
import os

UMBRAL_COINCIDENCIA = 0.75  # 0-1, que tan parecido debe ser (bajar si no detecta, subir si detecta de mas)
SEGUNDOS_ENTRE_MUESTRAS = 1.0  # cada cuanto revisa un frame (1 = revisa 1 vez por segundo)
SEPARACION_MERGE = 2.0  # detecciones a menos de esto se consideran el mismo evento

def buscar_imagen(ref_path, video_path):
    referencia = cv2.imread(ref_path)
    if referencia is None:
        raise FileNotFoundError(f"No se pudo leer la imagen de referencia: {ref_path}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"No se pudo abrir el video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        raise RuntimeError(f"No se pudo determinar el FPS del video: {video_path}")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duracion_total = total_frames / fps if fps > 0 else 0
    salto_frames = max(1, int(fps * SEGUNDOS_ENTRE_MUESTRAS))

    print(f"Video: {duracion_total/60:.1f} min, {fps:.1f} fps. Revisando 1 frame cada {SEGUNDOS_ENTRE_MUESTRAS}s...")

    detecciones = []
    frame_idx = 0
    muestras_analizadas = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        resultado = cv2.matchTemplate(frame, referencia, cv2.TM_CCOEFF_NORMED)
        score = resultado.max()

        if score >= UMBRAL_COINCIDENCIA:
            tiempo = frame_idx / fps
            detecciones.append({"tiempo": round(tiempo, 2), "score": round(float(score), 3)})

        muestras_analizadas += 1
        if muestras_analizadas % 100 == 0:
            progreso = (frame_idx / total_frames) * 100 if total_frames else 0
            print(f"  ...progreso: {progreso:.0f}%")

        for _ in range(salto_frames - 1):
            if not cap.grab():
                break
        frame_idx += salto_frames

    cap.release()

    # Fusionar detecciones cercanas (el mismo evento visto en varias muestras seguidas)
    detecciones.sort(key=lambda x: x["tiempo"])
    fusionadas = []
    for d in detecciones:
        if fusionadas and d["tiempo"] - fusionadas[-1]["tiempo"] <= SEPARACION_MERGE:
            if d["score"] > fusionadas[-1]["score"]:
                fusionadas[-1] = d
        else:
            fusionadas.append(d)

    return fusionadas

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python buscar_por_imagen.py <referencia.png> <video_objetivo.mp4>")
        print("\nLa referencia debe ser una captura de pantalla RECORTADA solo al elemento que quieres buscar")
        print("(ej: solo el cuadro de dialogo, no la pantalla completa).")
        sys.exit(1)

    ref_path = sys.argv[1]
    video_path = sys.argv[2]

    resultados = buscar_imagen(ref_path, video_path)

    print(f"\n{len(resultados)} coincidencias encontradas:")
    for r in resultados:
        minutos = int(r["tiempo"] // 60)
        segs = r["tiempo"] % 60
        print(f"  {minutos:02d}:{segs:05.2f} (segundo {r['tiempo']}) - score: {r['score']}")

    with open("resultados_busqueda_imagen.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\nGuardado en resultados_busqueda_imagen.json")
