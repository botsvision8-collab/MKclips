"""
Script de OBS Studio: al arrancar OBS, lanza panel_grabacion.py en segundo
plano (sin consola) para que el panel dentro de OBS (Custom Browser Dock,
http://localhost:5678) tenga el servidor corriendo.

IMPORTANTE: dentro de OBS, sys.executable es obs64.exe, NO Python. Este script
busca un Python real (ver _encontrar_python) y NUNCA lanza OBS de nuevo.

Ya NO dispara el pipeline por si mismo al detener grabacion - eso lo
maneja control_grabacion.py, llamado desde el panel. Tenerlo aca tambien
hacia que el pipeline pudiera correr DOS VECES sobre el mismo video.

INSTALACION:
1. En OBS: Herramientas > Scripts > pestaña "Python Settings" > apunta a tu
   instalacion de Python (si le faltan flask y obsws-python, el script los instala solo).
2. En la pestaña "Scripts", click en "+" y selecciona este archivo.
Si OBS no encuentra tu Python, escribe la ruta completa de python.exe en
scripts/OBS/python_panel.txt (una sola linea) o en la variable MKCLIPS_PYTHON.
El registro del panel queda en scripts/panel_obs.log.
"""

import configparser
import obspython as obs
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

PUERTO_PANEL = 5678
INTENTOS_VERIFICACION = 10  # una comprobacion por segundo
_proceso_panel = None
_verificacion_programada = False
_intentos = 0
_instalacion = None  # pip en curso: {proceso, contexto, inicio}
_instalacion_programada = False
LIMITE_INSTALACION_SEG = 300
_archivo_log = None  # panel_obs.log: lo que imprime el panel (errores de arranque incluidos)
CREAR_SIN_VENTANA = 0x08000000  # CREATE_NO_WINDOW (Windows)


def _registrar(nivel, mensaje):
    obs.script_log(nivel, f"[MKClips panel] {mensaje}")


def _carpeta_del_script():
    """Directorio real del script cargado desde Herramientas > Scripts.

    ``script_path()`` es una función que OBS inyecta en cada script. Se usa
    antes que ``__file__`` porque es la API estable de OBS para este caso.
    """
    try:
        ruta = Path(script_path()).resolve()
        return ruta if ruta.is_dir() else ruta.parent
    except Exception:
        return Path(__file__).resolve().parent


def _es_python(ruta):
    """True si ``ruta`` es un python.exe/pythonw.exe (nunca obs64.exe)."""
    try:
        p = Path(ruta)
        return p.is_file() and p.name.lower().startswith("python")
    except OSError:
        return False


def _python_de_obs_ini():
    """Python configurado en OBS (Python Settings), leido de global.ini/user.ini."""
    candidatos = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        for nombre in ("global.ini", "user.ini"):
            ini = Path(appdata) / "obs-studio" / nombre
            if ini.is_file():
                try:
                    cfg = configparser.ConfigParser(strict=False, interpolation=None)
                    cfg.read(ini, encoding="utf-8-sig")
                    for clave in ("Path64", "Path32"):
                        valor = cfg.get("Python", clave, fallback="").strip()
                        if valor:
                            base = Path(valor)
                            candidatos.append(base if base.suffix.lower() == ".exe" else base / "python.exe")
                except (configparser.Error, OSError, UnicodeDecodeError):
                    pass
    return candidatos


def _candidatos_python(carpeta_obs):
    """Lista ordenada de (origen, ruta) de posibles python.exe."""
    candidatos = []
    forzado = os.environ.get("MKCLIPS_PYTHON", "").strip()
    if forzado:
        candidatos.append(("variable MKCLIPS_PYTHON", Path(forzado)))
    archivo = Path(carpeta_obs) / "python_panel.txt"
    if archivo.is_file():
        try:
            linea = archivo.read_text(encoding="utf-8-sig").strip().splitlines()[0].strip().strip('"')
            candidatos.append(("python_panel.txt", Path(linea)))
        except (OSError, IndexError):
            pass
    candidatos.append(("sys.executable", Path(sys.executable)))
    for nombre in ("exec_prefix", "base_prefix", "base_exec_prefix"):
        prefijo = getattr(sys, nombre, "")
        if prefijo:
            candidatos.append((f"sys.{nombre}", Path(prefijo) / "python.exe"))
    for ruta in _python_de_obs_ini():
        candidatos.append(("ajustes de OBS (global.ini)", ruta))
    for nombre in ("python", "pythonw"):
        encontrado = shutil.which(nombre)
        if encontrado:
            candidatos.append(("PATH", Path(encontrado)))
    return candidatos


def _encontrar_python(carpeta_obs):
    """Devuelve (python_exe, pythonw_exe, origen) o (None, None, intentos) si no hay ninguno."""
    probados = []
    for origen, ruta in _candidatos_python(carpeta_obs):
        probados.append(f"{origen}: {ruta}")
        if _es_python(ruta):
            python_exe = ruta.with_name("python.exe") if ruta.name.lower() == "pythonw.exe" and ruta.with_name("python.exe").is_file() else ruta
            pythonw = python_exe.with_name("pythonw.exe")
            return python_exe, (pythonw if pythonw.is_file() else python_exe), origen
    return None, None, probados


def _resolver_rutas():
    carpeta_obs = _carpeta_del_script()
    carpeta_scripts = carpeta_obs.parent
    raiz_empaquetada = carpeta_scripts.parent.parent
    exe = raiz_empaquetada / "MKClips.exe"
    if exe.is_file():
        datos = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "MKClips"
        datos.mkdir(parents=True, exist_ok=True)
        ruta_panel = carpeta_scripts.parent / "scripts" / "panel_grabacion.py"
        return datos, ruta_panel, exe, exe, "MKClips empaquetado"
    ruta_panel = carpeta_scripts / "panel_grabacion.py"
    python_exe, ejecutable, origen = _encontrar_python(carpeta_obs)
    return carpeta_scripts, ruta_panel, python_exe, ejecutable, origen


def _faltan_librerias(python_exe):
    """Devuelve '' si flask y obsws_python se pueden importar, o el motivo."""
    if getattr(python_exe, "name", "").lower() == "mkclips.exe":
        return ""
    try:
        r = subprocess.run([str(python_exe), "-c", "import flask, obsws_python"], capture_output=True,
                           text=True, timeout=30, creationflags=CREAR_SIN_VENTANA if os.name == "nt" else 0)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"no se pudo ejecutar Python ({exc})"
    if r.returncode == 0:
        return ""
    return (r.stderr.strip().splitlines() or ["error desconocido"])[-1]


def _puerto_abierto():
    try:
        with socket.create_connection(("127.0.0.1", PUERTO_PANEL), timeout=0.4):
            return True
    except OSError:
        return False


def _detener_verificacion():
    global _verificacion_programada
    if _verificacion_programada:
        obs.timer_remove(_verificar_inicio_panel)
        _verificacion_programada = False


def _mostrar_log_del_panel():
    try:
        for linea in Path(_archivo_log).read_text(encoding="utf-8", errors="replace").strip().splitlines()[-8:]:
            _registrar(obs.LOG_ERROR, f"  panel_obs.log: {linea}")
    except Exception:
        pass


def _verificar_inicio_panel():
    """Comprueba cada segundo que el proceso sigue vivo Y que el puerto responde."""
    global _intentos
    if _proceso_panel is None:
        _detener_verificacion()
        return
    _intentos += 1
    codigo = _proceso_panel.poll()
    if codigo is not None:
        _registrar(obs.LOG_ERROR, f"El proceso del panel terminó (código {codigo}).")
        _mostrar_log_del_panel()
        _detener_verificacion()
    elif _puerto_abierto():
        _registrar(obs.LOG_INFO, f"Panel activo (PID {_proceso_panel.pid}) en http://localhost:{PUERTO_PANEL}")
        _detener_verificacion()
    elif _intentos >= INTENTOS_VERIFICACION:
        _registrar(obs.LOG_ERROR, f"El proceso del panel sigue vivo pero el puerto {PUERTO_PANEL} no responde.")
        _mostrar_log_del_panel()
        _detener_verificacion()


def script_description():
    return (
        "Al arrancar OBS, lanza panel_grabacion.py en segundo plano para "
        "que el panel de grabacion (Custom Browser Dock, "
        "http://localhost:5678) funcione. Registro: scripts/panel_obs.log"
    )


def _comando_instalacion(python_exe):
    return [str(python_exe), "-m", "pip", "install", "--disable-pip-version-check", "flask", "obsws-python"]


def _lanzar_panel(carpeta_scripts, ruta_panel, ejecutable):
    """Arranca el panel y programa la verificacion de su puerto."""
    global _proceso_panel, _verificacion_programada, _archivo_log, _intentos
    _archivo_log = str(carpeta_scripts / "panel_obs.log")
    salida_log = open(_archivo_log, "w", encoding="utf-8", errors="replace")
    comando = [str(ejecutable), "--server"] if Path(str(ejecutable)).name.lower() == "mkclips.exe" else [str(ejecutable), str(ruta_panel)]
    _proceso_panel = subprocess.Popen(
        comando,
        cwd=str(carpeta_scripts),
        stdout=salida_log, stderr=subprocess.STDOUT,
        env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
        creationflags=CREAR_SIN_VENTANA if os.name == "nt" else 0,
    )
    _registrar(obs.LOG_INFO, f"Proceso del panel iniciado: PID {_proceso_panel.pid}")
    _intentos = 0
    _verificacion_programada = True
    obs.timer_add(_verificar_inicio_panel, 1000)


def _verificar_instalacion():
    """Espera (sin bloquear OBS) a que termine pip y entonces arranca el panel."""
    global _instalacion, _instalacion_programada
    if _instalacion is None:
        return
    proceso, contexto, inicio = _instalacion["proceso"], _instalacion["contexto"], _instalacion["inicio"]
    codigo = proceso.poll()
    if codigo is None:
        if time.time() - inicio < LIMITE_INSTALACION_SEG:
            return
        proceso.terminate()
        _registrar(obs.LOG_ERROR, "La instalación automática tardó demasiado y se canceló.")
    elif codigo == 0:
        carpeta_scripts, ruta_panel, python_exe, ejecutable = contexto
        motivo = _faltan_librerias(python_exe)
        if motivo:
            _registrar(obs.LOG_ERROR, f"Tras instalar, siguen faltando librerías ({motivo}).")
        else:
            _registrar(obs.LOG_INFO, "Librerías instaladas. Iniciando el panel...")
            try:
                _lanzar_panel(carpeta_scripts, ruta_panel, ejecutable)
            except Exception as e:
                _registrar(obs.LOG_ERROR, f"No se pudo lanzar el panel: {type(e).__name__}: {e}")
    else:
        _registrar(obs.LOG_ERROR, f"La instalación automática falló (código {codigo}). Instala a mano con:")
        _registrar(obs.LOG_ERROR, "  " + " ".join(f'"{x}"' if " " in x else x for x in _comando_instalacion(contexto[2])))
    if _instalacion_programada:
        obs.timer_remove(_verificar_instalacion)
        _instalacion_programada = False
    _instalacion = None


def script_load(settings):
    global _instalacion, _instalacion_programada
    try:
        if _proceso_panel and _proceso_panel.poll() is None:
            _registrar(obs.LOG_INFO, f"Panel ya activo (PID {_proceso_panel.pid}).")
            return
        if _puerto_abierto():
            _registrar(obs.LOG_INFO, f"El panel ya responde en http://localhost:{PUERTO_PANEL} (iniciado por otro medio).")
            return
        carpeta_scripts, ruta_panel, python_exe, ejecutable, origen = _resolver_rutas()
        _registrar(obs.LOG_INFO, f"Panel: {ruta_panel}")
        if not ruta_panel.is_file():
            _registrar(obs.LOG_ERROR, f"No existe panel_grabacion.py: {ruta_panel}")
            return
        if python_exe is None:
            _registrar(obs.LOG_ERROR, "No se encontró un Python real (dentro de OBS sys.executable es obs64.exe). Probado:")
            for linea in origen:
                _registrar(obs.LOG_ERROR, f"  {linea}")
            _registrar(obs.LOG_ERROR, "Solución: escribe la ruta completa de python.exe en scripts/OBS/python_panel.txt "
                       "o configura Herramientas > Scripts > Ajustes de Python.")
            return
        _registrar(obs.LOG_INFO, f"Python usado: {python_exe} (origen: {origen})")
        motivo = _faltan_librerias(python_exe)
        if motivo:
            # Se instalan solas (flask y obsws-python) sin congelar OBS; el panel arranca al terminar.
            _registrar(obs.LOG_WARNING, f"Faltan librerías ({motivo}). Instalándolas automáticamente (puede tardar un minuto)...")
            registro_pip = open(carpeta_scripts / "panel_obs_instalacion.log", "w", encoding="utf-8", errors="replace")
            proceso = subprocess.Popen(_comando_instalacion(python_exe), stdout=registro_pip, stderr=subprocess.STDOUT,
                                       creationflags=CREAR_SIN_VENTANA if os.name == "nt" else 0)
            _instalacion = {"proceso": proceso, "contexto": (carpeta_scripts, ruta_panel, python_exe, ejecutable), "inicio": time.time()}
            _instalacion_programada = True
            obs.timer_add(_verificar_instalacion, 2000)
            return
        _lanzar_panel(carpeta_scripts, ruta_panel, ejecutable)
    except Exception as e:
        _registrar(obs.LOG_ERROR, f"No se pudo lanzar el panel: {type(e).__name__}: {e}")


def script_unload():
    global _proceso_panel, _instalacion, _instalacion_programada
    _detener_verificacion()
    if _instalacion_programada:
        obs.timer_remove(_verificar_instalacion)
        _instalacion_programada = False
    _instalacion = None
    if _proceso_panel and _proceso_panel.poll() is None:
        try:
            _proceso_panel.terminate()
            _registrar(obs.LOG_INFO, f"Proceso del panel detenido: PID {_proceso_panel.pid}")
        except OSError:
            _registrar(obs.LOG_WARNING, "No se pudo detener el proceso del panel.")
    _proceso_panel = None
