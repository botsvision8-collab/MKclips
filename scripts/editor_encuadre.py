# -*- coding: utf-8 -*-
"""Encuadre automático para videos horizontales: cara de la cámara + pantalla de juego.

Detecta la cara con el detector clásico de OpenCV (gratis, local, sin descargas) mirando unos
pocos fotogramas repartidos por el clip: la cámara de un stream suele estar fija, así que basta
con repetirse en varios fotogramas. Con eso propone el diseño de pantalla dividida (juego arriba,
cara abajo) que el editor muestra y que el usuario puede ajustar arrastrando los recuadros.

Límites honestos: no reconoce QUÉ juego es (usa el resto de la pantalla) y la detección puede
fallar con poca luz, la cara de perfil o una cámara muy pequeña. Si falla, el editor lo dice y
deja los recuadros para colocarlos a mano. OpenCV 5 retiró este detector: hace falta opencv-python 4.x.
"""
from __future__ import annotations

import os
import importlib.util
from importlib import metadata
from pathlib import Path

cv2 = None
_CV2_INTENTADO = False

def _obtener_cv2():
    global cv2, _CV2_INTENTADO
    if not _CV2_INTENTADO:
        _CV2_INTENTADO = True
        try:
            import cv2 as modulo_cv2
            cv2 = modulo_cv2
        except Exception:  # pragma: no cover - depende del entorno
            cv2 = None
    return cv2

try:
    from . import catalogo_clips, editor_modelo as modelo
except ImportError:
    import catalogo_clips
    import editor_modelo as modelo

MENSAJE_SIN_DETECTOR = ("La detección de cara necesita OpenCV 4 (el OpenCV 5 la retiró). "
                        'Instálalo con:  pip install "opencv-python<5"   Mientras tanto puedes colocar los recuadros a mano.')


def detector_disponible():
    """(ok, mensaje). ok=False si esta versión de OpenCV no trae el detector de caras."""
    spec = importlib.util.find_spec("cv2")
    if not spec or not spec.origin:
        return False, MENSAJE_SIN_DETECTOR
    version = ""
    for paquete in ("opencv-python", "opencv-python-headless", "opencv-contrib-python"):
        try:
            version = metadata.version(paquete)
            break
        except metadata.PackageNotFoundError:
            continue
    try:
        if version and int(version.split(".", 1)[0]) >= 5:
            return False, MENSAJE_SIN_DETECTOR
    except ValueError:
        pass
    data = Path(spec.origin).parent / "data"
    if not (data / "haarcascade_frontalface_default.xml").is_file():
        return False, MENSAJE_SIN_DETECTOR
    return True, ""


def _detector_opencv():
    ok, mensaje = detector_disponible()
    if not ok:
        raise RuntimeError(mensaje)
    cv2 = _obtener_cv2()
    if cv2 is None:
        raise RuntimeError(MENSAJE_SIN_DETECTOR)
    clasificador = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))

    realce = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    def detectar(gris):
        # Se prueba la imagen tal cual y, si no aparece nada, con contraste local (CLAHE). La
        # ecualización global del histograma empeora la detección en fotogramas oscuros.
        minimo = (max(20, int(gris.shape[0] * 0.03)),) * 2
        for imagen in (gris, realce.apply(gris)):
            cajas = clasificador.detectMultiScale(imagen, scaleFactor=1.1, minNeighbors=5, minSize=minimo)
            if len(cajas):
                return [tuple(int(v) for v in c) for c in cajas]
        return []
    return detectar


def _iou(a, b):
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    ix = max(0.0, min(ax2, bx2) - max(a[0], b[0]))
    iy = max(0.0, min(ay2, by2) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def agrupar_detecciones(cajas, muestras):
    """Caja (x, y, w, h normalizadas) de la cara más constante entre fotogramas, o None.

    Se queda con el grupo de cajas que más se solapan entre sí (la cámara fija); un falso
    positivo suelto o una cara que aparece una sola vez se descarta."""
    if not cajas:
        return None
    mejor = []
    for caja in cajas:
        grupo = [c for c in cajas if _iou(caja, c) > 0.3]
        if len(grupo) > len(mejor):
            mejor = grupo
    minimo = max(2, int(muestras * 0.25 + 0.999))
    if len(mejor) < minimo:
        return None
    ordenado = lambda i: sorted(c[i] for c in mejor)[len(mejor) // 2]
    return {"x": ordenado(0), "y": ordenado(1), "w": ordenado(2), "h": ordenado(3), "confianza": round(len(mejor) / muestras, 2)}


def detectar_cara(ruta, duracion, muestras=10, detector=None, ancho_analisis=960):
    """Cara principal del clip como {"x","y","w","h","confianza"} (0..1 sobre el fotograma) o None."""
    detector = detector or _detector_opencv()
    cap = catalogo_clips.abrir_captura(ruta)
    cajas = []
    try:
        if not cap.isOpened():
            raise RuntimeError("No se pudo abrir el video para buscar la cara.")
        for i in range(muestras):
            cap.set(cv2.CAP_PROP_POS_MSEC, 1000.0 * duracion * (i + 0.5) / muestras)
            ok, cuadro = cap.read()
            if not ok or cuadro is None:
                continue
            alto, ancho = cuadro.shape[:2]
            escala = min(1.0, ancho_analisis / float(ancho))
            if escala < 1.0:
                cuadro = cv2.resize(cuadro, (int(ancho * escala), int(alto * escala)), interpolation=cv2.INTER_AREA)
            gris = cv2.cvtColor(cuadro, cv2.COLOR_BGR2GRAY)
            h, w = gris.shape[:2]
            for (x, y, cw, ch) in detector(gris):
                cajas.append((x / w, y / h, cw / w, ch / h))
    finally:
        cap.release()
    return agrupar_detecciones(cajas, muestras)


def proponer_dividido(cara, ancho, alto, ancho_salida=1080, alto_salida=1920, proporcion_arriba=0.6):
    """Recuadros normalizados {"arriba", "abajo"} para la pantalla dividida.

    abajo  = alrededor de la cara (ancho ~3 veces el de la cara), con la proporción de la mitad inferior.
    arriba = el juego: recorte a todo lo alto del fotograma, desplazado hacia el lado contrario a la cámara."""
    alto_a, alto_b = modelo.alturas_dividido(alto_salida, proporcion_arriba)
    asp_a, asp_b = ancho_salida / alto_a, ancho_salida / alto_b
    # Mitad inferior: cara.
    cx, cy = cara["x"] + cara["w"] / 2.0, cara["y"] + cara["h"] / 2.0
    wb = min(1.0, max(cara["w"] * 3.0, 0.12))
    hb = wb * ancho / asp_b / alto
    if hb > 1.0:
        hb = 1.0
        wb = hb * alto * asp_b / ancho
    xb = min(max(0.0, cx - wb / 2.0), 1.0 - wb)
    yb = min(max(0.0, cy - hb * 0.45), 1.0 - hb)
    # Mitad superior: juego.
    ha = 1.0
    wa = ha * alto * asp_a / ancho
    if wa > 1.0:
        wa = 1.0
        ha = wa * ancho / asp_a / alto
    xa = (1.0 - wa) / 2.0
    cara_x0, cara_x1 = cara["x"] - cara["w"], cara["x"] + cara["w"] * 2.0
    if xa < cara_x1 and xa + wa > cara_x0:                  # el recorte central pisaría la cámara
        xa = 0.0 if cx > 0.5 else 1.0 - wa
    ya = (1.0 - ha) / 2.0
    redondear = lambda r: {k: round(max(0.0, min(1.0, v)), 4) for k, v in r.items()}
    return {"arriba": redondear({"x": xa, "y": ya, "w": wa, "h": ha}),
            "abajo": redondear({"x": xb, "y": yb, "w": wb, "h": hb})}
