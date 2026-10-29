# -*- coding: utf-8 -*-
"""Seguimiento temporal de cara con OpenCV FaceDetectorYN (YuNet)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

try:
    import cv2
except Exception:  # detector opcional; el resto del editor debe iniciar igualmente
    cv2 = None

try:
    from .rutas_app import datos_dir, recursos_dir
except ImportError:
    from rutas_app import datos_dir, recursos_dir


def ruta_modelo():
    if cv2 is None:
        return None
    raiz = Path(recursos_dir())
    if not getattr(__import__("sys"), "frozen", False):
        raiz = raiz.parent
    candidatos = [raiz / "assets" / "models" / "face_detection_yunet_2023mar.onnx",
                  raiz / "assets" / "easteregg" / "face_detection_yunet_2023mar.onnx",
                  Path(cv2.__file__).resolve().parent / "data" / "face_detection_yunet_2023mar.onnx"]
    return next((p for p in candidatos if p.is_file()), None)


def disponible():
    if cv2 is None:
        return False, "El seguimiento de cara necesita OpenCV 4.8 o posterior."
    if not hasattr(cv2, "FaceDetectorYN"):
        return False, "Esta versión de OpenCV no incluye FaceDetectorYN. Instala opencv-python 4.8 o posterior."
    if ruta_modelo() is None:
        return False, "No se encontró el modelo YuNet ONNX. Coloca face_detection_yunet_2023mar.onnx en assets/models/."
    return True, ""


def _cache(ruta, suavidad, perdida, region):
    st = os.stat(ruta)
    key = hashlib.sha256(f"{os.path.normcase(os.path.abspath(ruta))}|{st.st_size}|{st.st_mtime_ns}|{suavidad:.3f}|{perdida}|{region}".encode()).hexdigest()
    carpeta = Path(datos_dir()) / ".mkclips_cache" / "seguimiento_cara"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / (key + ".json")


def analizar(ruta, duracion, suavidad=.7, perdida="mantener", region=None, cancelar=None, progreso=None):
    ok, msg = disponible()
    if not ok:
        raise RuntimeError(msg)
    region = region if isinstance(region, dict) else {"x":0,"y":0,"w":1,"h":1}
    try:
        rx, ry, rw, rh = (float(region.get(k, d)) for k,d in (("x",0),("y",0),("w",1),("h",1)))
    except (TypeError, ValueError):
        raise RuntimeError("La región de cámara no es válida.")
    rx, ry = max(0.0,min(.999,rx)), max(0.0,min(.999,ry))
    rw, rh = max(.01,min(1-rx,rw)), max(.01,min(1-ry,rh))
    region={"x":rx,"y":ry,"w":rw,"h":rh}
    cache = _cache(ruta, suavidad, perdida, region)
    try:
        return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    detector = cv2.FaceDetectorYN_create(str(ruta_modelo()), "", (320, 320), 0.75, 0.3, 5000)
    cap = cv2.VideoCapture(ruta)
    if not cap.isOpened():
        raise RuntimeError("No se pudo abrir el vídeo para analizar la cámara.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    salto = max(1, round(fps / 7.0))
    total = max(1, int(duracion * fps))
    trayectoria, ultimo, ultimo_t, suave = [], None, -999, None
    try:
        idx = 0
        while idx < total:
            if cancelar and cancelar.is_set():
                raise RuntimeError("Análisis cancelado.")
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            t = idx / fps
            if ret and frame is not None:
                h, w = frame.shape[:2]
                rx,ry,rw,rh=(float(region.get(k,d)) for k,d in (("x",0),("y",0),("w",1),("h",1)))
                x0,y0=max(0,int(rx*w)),max(0,int(ry*h)); x1,y1=min(w,int((rx+rw)*w)),min(h,int((ry+rh)*h))
                frame=frame[y0:y1,x0:x1]
                if frame.size == 0: raise RuntimeError("La región de cámara no es válida.")
                escala = min(1.0, 960 / frame.shape[1])
                if escala < 1:
                    frame = cv2.resize(frame, (round(frame.shape[1] * escala), round(frame.shape[0] * escala)), interpolation=cv2.INTER_AREA)
                detector.setInputSize((frame.shape[1], frame.shape[0]))
                _ok, caras = detector.detect(frame)
                if caras is not None and len(caras):
                    # Prioriza la cara mayor; cerca del último centro favorece continuidad.
                    def puntuar(c):
                        area = float(c[2] * c[3])
                        cx, cy = (c[0] + c[2]/2) / frame.shape[1], (c[1] + c[3]/2) / frame.shape[0]
                        dist = 0 if ultimo is None else ((cx-ultimo[0])**2 + (cy-ultimo[1])**2)**.5
                        return area / (1 + 2.5 * dist)
                    c = max(caras, key=puntuar)
                    punto = (rx+(float(c[0]+c[2]/2)/frame.shape[1])*rw, ry+(float(c[1]+c[3]/2)/frame.shape[0])*rh)
                    if suave is None:
                        suave = punto
                    else:
                        dx, dy = punto[0]-suave[0], punto[1]-suave[1]
                        # Zona muerta 1.5% de cuadro antes del filtro exponencial.
                        if abs(dx) > .015 or abs(dy) > .015:
                            a = max(.05, min(.8, 1.0-float(suavidad)))
                            if t-ultimo_t > 2.5:
                                a = max(a, .3)  # reenganche gradual tras una pérdida larga
                            suave = (suave[0]+a*dx, suave[1]+a*dy)
                    ultimo, ultimo_t = suave, t
                    trayectoria.append({"t": round(t, 3), "x": round(suave[0], 5), "y": round(suave[1], 5),
                                        "cara": [round(rx+float(c[0]/frame.shape[1])*rw,4), round(ry+float(c[1]/frame.shape[0])*rh,4), round(float(c[2]/frame.shape[1])*rw,4), round(float(c[3]/frame.shape[0])*rh,4)]})
                elif ultimo is not None:
                    if t-ultimo_t <= 2.5 or perdida == "mantener":
                        trayectoria.append({"t":round(t,3),"x":round(ultimo[0],5),"y":round(ultimo[1],5),"cara":None})
                    else:
                        # Regreso gradual hacia el centro una vez superado el margen de pérdida.
                        a = min(.25, (t-ultimo_t-2.5)*.08)
                        ultimo=(ultimo[0]+(.5-ultimo[0])*a,ultimo[1]+(.5-ultimo[1])*a)
                        trayectoria.append({"t":round(t,3),"x":round(ultimo[0],5),"y":round(ultimo[1],5),"cara":None})
            idx += salto
            if progreso: progreso(min(.99, idx/total))
    finally:
        cap.release()
    if not trayectoria:
        raise RuntimeError("No se encontró una cara en el clip.")
    cache.write_text(json.dumps(trayectoria,separators=(",",":")),encoding="utf-8")
    if progreso: progreso(1.0)
    return trayectoria
