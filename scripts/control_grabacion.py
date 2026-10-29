"""
control_grabacion.py - Logica para iniciar/detener la grabacion en OBS
(horizontal, vertical, o ambos via Aitum Vertical Canvas), opcionalmente
disparar el pipeline de clips, y opcionalmente borrar el original.

Requiere: pip install obsws-python
Necesita en config.py: OBS_WS_HOST, OBS_WS_PUERTO, OBS_WS_CONTRASENA
"""

import os
import json
import tkinter as tk
from tkinter import scrolledtext
import time

import procesar_multiples
import cache_mkclips

VENDOR_VERTICAL = "aitum-vertical-canvas"


def _obtener_cliente_obs():
    try:
        import obsws_python as obs
    except ImportError as e:
        raise RuntimeError(
            "Falta la libreria obsws-python. Instala con: pip install obsws-python"
        ) from e

    try:
        from config import OBS_WS_HOST, OBS_WS_PUERTO
    except ImportError as e:
        raise RuntimeError(
            "Faltan los datos de conexion a OBS en config.py (OBS_WS_HOST, OBS_WS_PUERTO)."
        ) from e
    OBS_WS_CONTRASENA = os.environ.get("OBS_WS_CONTRASENA", "")

    return obs.ReqClient(
        host=OBS_WS_HOST, port=int(OBS_WS_PUERTO), password=OBS_WS_CONTRASENA, timeout=5
    )


def _carpeta_streams():
    try:
        from config import CARPETA_STREAMS
    except ImportError:
        CARPETA_STREAMS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "streams")
    return CARPETA_STREAMS


def verificar_conflicto(modo):
    """
    Chequea si OBS ya esta grabando (nativo y/o vertical) ANTES de que
    nosotros mandemos la orden de iniciar - para avisar si el usuario le
    dio al boton nativo de OBS por error, en vez de bloquear la interfaz
    (mas fragil de implementar y de romper con updates de OBS).

    Devuelve None si no hay conflicto, o un mensaje de aviso si lo hay.
    """
    cliente = _obtener_cliente_obs()
    try:
        if modo in ("horizontal", "ambos"):
            estado = cliente.get_record_status()
            if getattr(estado, "output_active", False):
                return (
                    "OBS ya esta grabando en horizontal (probablemente le diste "
                    "al boton nativo de grabar). Detene esa grabacion desde OBS "
                    "antes de usar este panel."
                )
        if modo in ("vertical", "ambos"):
            resp = cliente.call_vendor_request(
                vendor_name=VENDOR_VERTICAL,
                request_type="status",
                request_data={"width": 0, "height": 0},
            )
            datos = getattr(resp, "response_data", {}) or {}
            if datos.get("recording"):
                return (
                    "El canvas vertical ya esta grabando (probablemente lo "
                    "iniciaste desde el panel de Aitum directamente). Detenelo "
                    "antes de usar este panel."
                )
    finally:
        if hasattr(cliente, "disconnect"):
            cliente.disconnect()
    return None


def _detectar_archivo_nuevo(carpeta, rutas_previas, excluir=None, intentos=7, espera=1.0):
    excluir_abs = os.path.abspath(excluir) if excluir else None
    for _ in range(intentos):
        for ruta in procesar_multiples.listar_videos(carpeta):
            ruta_abs = os.path.abspath(ruta)
            if excluir_abs and ruta_abs == excluir_abs:
                continue
            if ruta_abs in rutas_previas:
                continue
            try:
                tam1 = os.path.getsize(ruta_abs)
                time.sleep(0.5)
                tam2 = os.path.getsize(ruta_abs)
            except OSError:
                continue
            if tam1 == tam2:
                return ruta_abs
        time.sleep(espera)
    return None


def iniciar_grabacion(modo, notificar=print):
    """
    modo: "horizontal", "vertical" o "ambos".
    Lanza RuntimeError con mensaje claro si detecta un conflicto (algo ya
    estaba grabando por fuera del panel).
    Devuelve el snapshot de archivos existentes antes de grabar.
    """
    conflicto = verificar_conflicto(modo)
    if conflicto:
        raise RuntimeError(conflicto)

    procesar_multiples._evitar_suspension(True)

    carpeta_streams = _carpeta_streams()
    snapshot = {os.path.abspath(p) for p in procesar_multiples.listar_videos(carpeta_streams)}

    cliente = _obtener_cliente_obs()
    try:
        if modo in ("horizontal", "ambos"):
            cliente.start_record()
        if modo in ("vertical", "ambos"):
            cliente.call_vendor_request(
                vendor_name=VENDOR_VERTICAL,
                request_type="start_recording",
                request_data={"width": 0, "height": 0},
            )
    finally:
        if hasattr(cliente, "disconnect"):
            cliente.disconnect()

    notificar(f"Grabacion iniciada - modo: {modo}")
    return snapshot


def detener_grabacion_y_procesar(modo, snapshot, notificar=print, solo_grabar=False, borrar_original=False):
    """
    Detiene la grabacion segun 'modo' y detecta el/los archivo(s)
    resultante(s).

    solo_grabar=True: NO corre el pipeline de clips, solo detiene y
    reporta donde quedaron los archivos (para grabaciones de audio u
    otros usos que no son para clips).

    borrar_original=True: borra cada archivo despues de procesarlo
    exitosamente. Ignorado si solo_grabar=True (nunca se borra un archivo
    que no se proceso).

    Devuelve la lista de rutas encontradas.
    """
    carpeta_streams = _carpeta_streams()
    ruta_horizontal = None

    cliente = _obtener_cliente_obs()
    try:
        if modo in ("horizontal", "ambos"):
            resp = cliente.stop_record()
            ruta_horizontal = getattr(resp, "output_path", None)
            notificar("Grabacion horizontal detenida.")

        if modo in ("vertical", "ambos"):
            cliente.call_vendor_request(
                vendor_name=VENDOR_VERTICAL,
                request_type="stop_recording",
                request_data={"width": 0, "height": 0},
            )
            notificar("Grabacion vertical detenida.")
    finally:
        if hasattr(cliente, "disconnect"):
            cliente.disconnect()

    archivos = []

    if ruta_horizontal and os.path.exists(ruta_horizontal):
        archivos.append(ruta_horizontal)
        notificar(f"Archivo horizontal: {os.path.basename(ruta_horizontal)}")
    elif modo in ("horizontal", "ambos"):
        notificar(
            "No se pudo obtener la ruta del archivo horizontal automaticamente. "
            "Buscalo a mano en la carpeta de streams."
        )

    if modo in ("vertical", "ambos"):
        notificar("Buscando el archivo vertical recien generado...")
        ruta_vertical = _detectar_archivo_nuevo(carpeta_streams, snapshot, excluir=ruta_horizontal)
        if ruta_vertical:
            archivos.append(ruta_vertical)
            notificar(f"Archivo vertical: {os.path.basename(ruta_vertical)}")
        else:
            notificar(
                "No se encontro el archivo vertical automaticamente. "
                "Buscalo a mano en la carpeta de streams."
            )

    if solo_grabar:
        notificar("Modo 'solo grabar': no se genera ningun clip.")
        notificar("Listo.")
        procesar_multiples._evitar_suspension(False)
        return archivos

    contexto = _pedir_contexto_post_stream() if archivos else ""

    procesar_multiples.lanzar_notificacion_progreso()

    for ruta in archivos:
        nombre = os.path.basename(ruta)
        notificar(f"--- Procesando {nombre} ---")
        ok = procesar_multiples.procesar_un_video(
            ruta, modo_automatico=True, notificar=notificar, contexto_stream=contexto
        )
        if ok and borrar_original:
            try:
                os.remove(ruta)
                notificar(f"Original borrado: {nombre}")
            except OSError as e:
                notificar(f"No se pudo borrar el original: {e}")

    notificar("Listo.")
    procesar_multiples._evitar_suspension(False)
    return archivos


def _pedir_contexto_post_stream():
    """Muestra un diálogo opcional fuera del hilo de OBS y devuelve texto plano."""
    try:
        from config import MOSTRAR_CONTEXTO_POST_STREAM
    except Exception:
        MOSTRAR_CONTEXTO_POST_STREAM = True
    if not MOSTRAR_CONTEXTO_POST_STREAM:
        return ""

    resultado = {"texto": "", "decidido": False}
    ventana = tk.Tk()
    ventana.title("Contexto del stream")
    ventana.geometry("520x300")
    ventana.resizable(True, True)
    tk.Label(ventana, text="Contexto del stream (opcional)").pack(anchor="w", padx=12, pady=(12, 4))
    texto = scrolledtext.ScrolledText(ventana, wrap=tk.WORD, height=10)
    texto.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)
    botones = tk.Frame(ventana)
    botones.pack(anchor="e", padx=12, pady=10)

    def cerrar(valor):
        resultado["texto"] = texto.get("1.0", tk.END).strip() if valor else ""
        resultado["decidido"] = True
        ventana.destroy()

    tk.Button(botones, text="Omitir", command=lambda: cerrar(False)).pack(side=tk.LEFT, padx=4)
    tk.Button(botones, text="Procesar", command=lambda: cerrar(True)).pack(side=tk.LEFT, padx=4)
    ventana.protocol("WM_DELETE_WINDOW", lambda: cerrar(False))
    ventana.mainloop()
    return resultado["texto"]
