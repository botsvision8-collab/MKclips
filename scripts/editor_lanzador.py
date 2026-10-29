# -*- coding: utf-8 -*-
"""Arranca el panel local y abre las pantallas MKClips en la ventana de escritorio.

El editor es una página que sirve el panel de MKClips (http://localhost:5678). Esta utilidad no
depende de Flask para poder usarse desde la ventana Tkinter aunque Flask no esté instalado: en ese
caso explica qué instalar."""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    from . import editor_modelo as modelo
except ImportError:
    import editor_modelo as modelo

HOST, PUERTO = "127.0.0.1", 5678
try:
    from .rutas_app import datos_dir, recursos_dir
except ImportError:
    from rutas_app import datos_dir, recursos_dir
CARPETA = str(datos_dir()) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def url_editor(ruta_clip, puerto=PUERTO):
    return f"http://localhost:{puerto}/editor/{modelo.id_de_clip(ruta_clip)}"


def panel_activo(puerto=PUERTO, host=HOST):
    try:
        with socket.create_connection((host, puerto), timeout=0.6):
            return True
    except OSError:
        return False


VERSION_MINIMA = 14
VERSION_UI_MINIMA = 3


def version_del_panel(puerto=PUERTO, host=HOST):
    """Versión del editor que tiene el panel abierto (0 si no hay editor o es una versión antigua sin número)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{puerto}/editor/api/version", timeout=3) as r:
            return int(json.loads(r.read().decode("utf-8")).get("version", 0))
    except (OSError, ValueError, urllib.error.URLError):
        return 0


def version_ui_del_panel(puerto=PUERTO, host=HOST):
    """Versión de las rutas principales (tip page, recursos y UI), 0 si es antigua."""
    try:
        with urllib.request.urlopen(f"http://{host}:{puerto}/app/api/version", timeout=3) as r:
            return int(json.loads(r.read().decode("utf-8")).get("ui_version", 0))
    except (OSError, ValueError, urllib.error.URLError):
        return 0


def _panel_actual(puerto=PUERTO, host=HOST):
    return (version_del_panel(puerto, host) >= VERSION_MINIMA
            and version_ui_del_panel(puerto, host) >= VERSION_UI_MINIMA)


def _tiene_editor(id_clip, puerto=PUERTO, host=HOST):
    """True si el panel que responde incluye la versión actual del editor (uno arrancado antes de actualizar no la tiene)."""
    return version_del_panel(puerto, host) >= VERSION_MINIMA


def iniciar_panel(puerto=PUERTO, esperar_seg=15.0, lanzar=subprocess.Popen):
    """Arranca panel_grabacion.py con el Python actual. Devuelve (ok, mensaje)."""
    if panel_activo(puerto):
        if _panel_actual(puerto):
            return True, ""
        if panel_ocupado(puerto):
            return False, "El panel abierto está desactualizado, pero está procesando algo. Espera a que termine y vuelve a abrir MKClips."
        # El endpoint antiguo hace un reinicio controlado del servidor. Al
        # arrancar de nuevo importa los archivos actuales y evita matar procesos
        # ajenos que pudieran ocupar el puerto.
        try:
            req = urllib.request.Request(f"http://{HOST}:{puerto}/editor/api/apagar", data=b"{}", method="POST",
                                         headers={"X-MKClips-Apagar": "1", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=3).read()
        except (OSError, urllib.error.URLError, ValueError):
            return False, "El panel antiguo no aceptó el reinicio. Cierra MKClips y vuelve a abrirlo para cargar la versión actual."
        limite = time.time() + esperar_seg
        while time.time() < limite:
            if _panel_actual(puerto):
                return True, ""
            time.sleep(0.3)
        if panel_activo(puerto):
            return False, "El panel sigue respondiendo con una versión antigua. Cierra el panel y vuelve a abrir MKClips."
    faltan = [m for m in ("flask",) if importlib.util.find_spec(m) is None]
    if faltan:
        return False, "Falta instalar Flask para abrir el editor:\n    pip install flask"
    registro = os.path.join(CARPETA, "panel_obs.log")
    comando = [sys.executable, "--server"] if getattr(sys, "frozen", False) else [sys.executable, os.path.join(CARPETA, "panel_grabacion.py")]
    try:
        with open(registro, "ab") as salida:
            lanzar(comando, cwd=CARPETA, stdin=subprocess.DEVNULL, stdout=salida, stderr=subprocess.STDOUT,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError as exc:
        return False, f"No se pudo iniciar el panel: {exc}"
    limite = time.time() + esperar_seg
    while time.time() < limite:
        if _panel_actual(puerto):
            return True, ""
        time.sleep(0.3)
    return False, f"El panel no arrancó con la versión actual. Revisa el archivo {registro}"


def _ejecutar_texto(comando, ejecutar=subprocess.run):
    try:
        r = ejecutar(comando, capture_output=True, text=True, timeout=15,
                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def pid_de_netstat(texto, puerto):
    """PID del proceso en escucha en ``puerto`` según la salida de ``netstat -ano``."""
    for linea in texto.splitlines():
        partes = linea.split()
        if len(partes) >= 5 and (partes[3].upper() in ("LISTENING", "ESCUCHANDO") or partes[2].endswith(":0")) and partes[1].endswith(f":{puerto}") and partes[4].isdigit():
            return int(partes[4])
    return None


def pid_que_escucha(puerto=PUERTO, ejecutar=subprocess.run):
    """PID del proceso que tiene el puerto en escucha, o None."""
    if os.name == "nt":
        texto = _ejecutar_texto(["powershell", "-NoProfile", "-Command", f"(Get-NetTCPConnection -LocalPort {int(puerto)} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)"], ejecutar)
        for linea in texto.splitlines():
            if linea.strip().isdigit(): return int(linea.strip())
        return pid_de_netstat(_ejecutar_texto(["netstat", "-ano", "-p", "TCP"], ejecutar), puerto)
    for linea in _ejecutar_texto(["lsof", "-ti", f"tcp:{puerto}", "-sTCP:LISTEN"], ejecutar).split():
        if linea.isdigit():
            return int(linea)
    return None


def linea_de_comando(pid, ejecutar=subprocess.run):
    """Línea de comandos del proceso (para comprobar que de verdad es el panel de MKClips antes de cerrarlo)."""
    if os.name == "nt":
        return _ejecutar_texto(["powershell", "-NoProfile", "-Command", f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"], ejecutar).strip()
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def _terminar(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        import signal
        os.kill(int(pid), signal.SIGTERM)


def panel_ocupado(puerto=PUERTO, host=HOST):
    """True si el panel está grabando, procesando o descargando (no se debe interrumpir)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{puerto}/estado", timeout=3) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return any(bool(d.get(k)) for k in ("grabando", "deteniendo", "procesando", "descargando"))


def _esperar_cierre(puerto, segundos=8.0):
    limite = time.time() + segundos
    while time.time() < limite:
        if not panel_activo(puerto):
            return True
        time.sleep(0.25)
    return not panel_activo(puerto)


def detener_panel(puerto=PUERTO, host=HOST):
    """Cierra el panel de MKClips que está abierto, sin tocar nada más. Devuelve (ok, mensaje).

    Primero se lo pide con cortesía (paneles recientes); si es antiguo, termina SOLO el proceso que escucha
    en el puerto y únicamente si su línea de comandos es panel_grabacion.py. No cierra nada si hay una grabación o un proceso en curso."""
    if not panel_activo(puerto):
        return True, ""
    if panel_ocupado(puerto, host):
        return False, "El panel está grabando o procesando algo ahora mismo. Espera a que termine y vuelve a pulsar Editar."
    try:
        req = urllib.request.Request(f"http://{host}:{puerto}/editor/api/apagar", data=b"{}", method="POST",
                                     headers={"X-MKClips-Apagar": "1", "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
    except (OSError, urllib.error.URLError, ValueError):
        pass
    if _esperar_cierre(puerto, 3.0):
        return True, ""
    pid = pid_que_escucha(puerto)
    if not pid:
        return False, "No pude identificar qué proceso es el panel. Ciérralo a mano (ventana negra del panel o Administrador de tareas)."
    linea = linea_de_comando(pid).replace("\\", "/").lower()
    exe_panel = (
        getattr(sys, "frozen", False)
        and os.path.normcase(os.path.abspath(sys.executable)).replace("\\", "/").lower() in linea
        and "--server" in linea
    )
    if "panel_grabacion" not in linea and not exe_panel:
        return False, ("El puerto 5678 lo usa otro programa que no es el panel de MKClips, así que no lo cierro. "
                       "Ciérralo tú o cambia el puerto.")
    try:
        _terminar(pid)
    except OSError as exc:
        return False, f"No se pudo cerrar el panel antiguo: {exc}"
    if not _esperar_cierre(puerto):
        return False, "Intenté cerrar el panel antiguo pero sigue abierto. Ciérralo a mano desde el Administrador de tareas."
    return True, ""


def abrir_editor(ruta_clip, puerto=PUERTO, lanzar=subprocess.Popen):
    """Prepara el panel y abre el editor del clip en una ventana de escritorio.

    Si el panel abierto es de una versión anterior (se arrancó antes de actualizar), lo cierra y arranca uno nuevo."""
    if not ruta_clip or not os.path.isfile(ruta_clip):
        return False, "El archivo del clip ya no existe."
    ok, mensaje = iniciar_panel(puerto)
    if not ok:
        return False, mensaje
    if not _tiene_editor(modelo.id_de_clip(ruta_clip), puerto):
        ok, mensaje = detener_panel(puerto)
        if not ok:
            return False, mensaje
        ok, mensaje = iniciar_panel(puerto)
        if not ok:
            return False, mensaje
        if not _tiene_editor(modelo.id_de_clip(ruta_clip), puerto):
            return False, "Reinicié el panel pero sigue sin tener la versión nueva del editor. Comprueba que descomprimiste la actualización en la carpeta correcta."
    ruta = f"/editor/{modelo.id_de_clip(ruta_clip)}"
    if getattr(sys, "frozen", False):
        comando = [sys.executable, "--url", ruta]
    else:
        comando = [sys.executable, os.path.join(CARPETA, "configuracion_app.py"), "--url", ruta]
    try:
        lanzar(comando, cwd=CARPETA,
               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except OSError as exc:
        return False, f"No se pudo abrir MKClips: {exc}"
    return True, ""
