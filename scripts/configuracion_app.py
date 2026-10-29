# -*- coding: utf-8 -*-
"""Ventana Tkinter de configuracion; config.py se gestiona solo centralmente."""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
try:
    from .rutas_app import comando_python, datos_dir, recursos_dir
except ImportError:
    from rutas_app import comando_python, datos_dir, recursos_dir

VERSION_ARCHIVO = recursos_dir() / "VERSION"
try:
    VERSION_APP = VERSION_ARCHIVO.read_text(encoding="utf-8").strip()
except OSError:
    VERSION_APP = "1.0.0"
if __package__ is None:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageTk, ImageSequence
except ImportError:
    Image = ImageTk = ImageSequence = None
cv2 = None
_CV2_INTENTADO = False

def _obtener_cv2():
    global cv2, _CV2_INTENTADO
    if not _CV2_INTENTADO:
        _CV2_INTENTADO = True
        try:
            import cv2 as modulo_cv2
            cv2 = modulo_cv2
        except Exception:
            cv2 = None
    return cv2

def _abrir_carpeta_sistema(ruta):
    destino = os.path.abspath(os.fspath(ruta))
    if sys.platform.startswith("win"):
        os.startfile(destino)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", destino])
    else:
        subprocess.Popen(["xdg-open", destino])

try:
    from .interfaz_mkclips import PALETAS, aplicar_tema, leer_tema, pagina_scroll, texto_adaptable
except Exception:
    from interfaz_mkclips import PALETAS, aplicar_tema, leer_tema, pagina_scroll, texto_adaptable
try:
    from .cache_mkclips import exigir_identidad_artefacto, identidad_fuente
except Exception:
    from cache_mkclips import exigir_identidad_artefacto, identidad_fuente
try:
    from .configuracion_central import (
        directorio_scripts, guardar_configuracion, leer_configuracion, limite_cpu_recomendado,
        normalizar_configuracion,
    )
except Exception:
    from configuracion_central import (
        directorio_scripts, guardar_configuracion, leer_configuracion, limite_cpu_recomendado,
        normalizar_configuracion,
    )
try:
    from .preferencias_mkclips import cargar_preferencias, feedback_por_clip, guardar_feedback, identificador_clip, indicador_acierto
except Exception:
    from preferencias_mkclips import cargar_preferencias, feedback_por_clip, guardar_feedback, identificador_clip, indicador_acierto
try:
    from . import llm_cliente, catalogo_clips, reproductor_sistema, contexto_ia, limpieza_temporales, transcripcion_assemblyai
except Exception:
    import llm_cliente, catalogo_clips, reproductor_sistema, contexto_ia, limpieza_temporales, transcripcion_assemblyai
try:
    from . import pestana_editar
except Exception:
    try:
        import pestana_editar
    except Exception:
        pestana_editar = None
abrir_captura = catalogo_clips.abrir_captura
ESTADO_APP = {"cola": None}  # la cola activa, para no limpiar temporales mientras procesa
RUTA_HISTORIAL_CLIPS = os.path.join(str(directorio_scripts()), "historial_clips.json")
# Etiqueta que ve el usuario -> codigo que se guarda. Cambian segun si valoras alto o bajo.
SIN_MOTIVO = "(opcional) Elige un motivo"
MOTIVOS_NEGATIVOS_UI = (
    ("Aburrido o sin gracia", "aburrido"),
    ("Falta contexto (no se entiende)", "contexto"),
    ("Repetitivo o ya lo vi", "repetitivo"),
    ("Mal cortado (inicio o final)", "corte"),
    ("Problema técnico (audio o video)", "tecnico"),
)
MOTIVOS_POSITIVOS_UI = (
    ("Me hizo reír", "humor"),
    ("Remate o clímax fuerte", "climax"),
    ("Jugada o habilidad destacada", "habilidad"),
    ("Historia completa, fácil de seguir", "historia"),
    ("Reacción o emoción genuina", "reaccion"),
    ("Sorpresa inesperada", "sorpresa"),
)


def _tipo_de_motivo(estado):
    """'positivo' (4-5 estrellas), 'negativo' (descartado o 1-2 estrellas) o None (sin motivo)."""
    if estado == "DESCARTADO" or estado in ("VALORADO_1", "VALORADO_2"):
        return "negativo"
    if estado in ("VALORADO_4", "VALORADO_5"):
        return "positivo"
    return None


def _codigo_motivo(estado, etiqueta):
    tipo = _tipo_de_motivo(estado)
    tabla = MOTIVOS_NEGATIVOS_UI if tipo == "negativo" else MOTIVOS_POSITIVOS_UI if tipo == "positivo" else ()
    return dict(tabla).get(etiqueta, "")


def detectar_gpu() -> dict:
    """Consulta NVIDIA/CTranslate2 sin instalar ni importar PyTorch."""
    modelo = ""
    try:
        resultado = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        if resultado.returncode == 0 and resultado.stdout:
            modelo = resultado.stdout.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        # Es la comprobacion que utiliza el panel y prepara DLL NVIDIA antes
        # de preguntar a CTranslate2.
        import transcribir
        compatible = bool(transcribir._gpu_disponible())
    except Exception:
        compatible = False
    return {"compatible": compatible, "modelo": modelo or ("NVIDIA detectada" if compatible else "No detectada")}


def probar_ia(configuracion: dict, api_key: str = "") -> str:
    """Prueba la IA configurada (sin guardar la clave) y devuelve un resumen."""
    mensaje, segundos = llm_cliente.probar(configuracion, clave=api_key or None)
    return f"{mensaje}\n({segundos:.1f} s)"


def probar_obs() -> None:
    """Usa el mismo cliente/configuracion OBS que el panel."""
    import control_grabacion
    cliente = control_grabacion._obtener_cliente_obs()
    try:
        cliente.get_record_status()
    finally:
        if hasattr(cliente, "disconnect"):
            cliente.disconnect()


def crear_ventana():
    valores = leer_configuracion()
    # La deteccion de GPU (nvidia-smi + CTranslate2) tarda segundos: se hace en
    # segundo plano para que la ventana abra al instante.
    gpu = {"compatible": False, "modelo": "Detectando...", "listo": False}
    root = tk.Tk()
    root.title("MKClips")
    root.minsize(900, 620)
    root.columnconfigure(0, weight=1); root.rowconfigure(1, weight=1)
    ttk.Label(root, text="MKClips", font=("Segoe UI", 16, "bold"), padding=(14, 8)).grid(row=0, column=0, sticky="w")
    panel = ttk.Frame(root, padding=(8, 0, 8, 8)); panel.grid(row=1, column=0, sticky="nsew")
    panel.columnconfigure(1, weight=1); panel.rowconfigure(0, weight=1)
    navegacion = ttk.Frame(panel, padding=(2, 8)); navegacion.grid(row=0, column=0, sticky="ns")
    contenido = ttk.Frame(panel); contenido.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
    contenido.columnconfigure(0, weight=1); contenido.rowconfigure(0, weight=1)
    pagina_config, frame = pagina_scroll(contenido)
    frame.columnconfigure(1, weight=1)
    entradas, variables = {}, {}

    def agregar_entrada(fila, clave, etiqueta, secreto=False, ancho=20):
        ttk.Label(frame, text=etiqueta).grid(row=fila, column=0, sticky="w", padx=(0, 8), pady=4)
        entrada = ttk.Entry(frame, width=ancho, show="*" if secreto else "")
        entrada.insert(0, str(valores.get(clave, "")))
        entrada.grid(row=fila, column=1, sticky="ew", pady=4)
        entradas[clave] = entrada
        return entrada

    def elegir(campo):
        ruta = filedialog.askdirectory(title=f"Selecciona carpeta para {campo}")
        if ruta:
            entradas[campo].delete(0, tk.END); entradas[campo].insert(0, ruta)

    ttk.Label(frame, text="Configuración", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(frame, text="Ajusta carpetas, recursos y conexiones. Estos valores se aplican en los próximos procesos.", wraplength=760).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))
    fila = 2
    ttk.Label(frame, text="CARPETAS", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w", pady=(0, 3)); fila += 1
    for clave, etiqueta in (("CARPETA_STREAMS", "Streams grabados"), ("CARPETA_CLIPS_BASE", "Clips generados"), ("CARPETA_RESULTADOS", "Resultados JSON (opcional)"), ("CARPETA_EDITADOS", "Clips editados (editor)")):
        agregar_entrada(fila, clave, etiqueta)
        ttk.Button(frame, text="Examinar", command=lambda c=clave: elegir(c)).grid(row=fila, column=2, padx=(6, 0)); fila += 1

    ttk.Separator(frame).grid(row=fila, columnspan=3, sticky="ew", pady=7); fila += 1
    ttk.Label(frame, text="OBS", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w"); fila += 1
    agregar_entrada(fila, "OBS_WS_HOST", "Host"); fila += 1
    agregar_entrada(fila, "OBS_WS_PUERTO", "Puerto", ancho=12); fila += 1
    agregar_entrada(fila, "OBS_WS_CONTRASENA", "Contrasena", secreto=True); fila += 1

    # --- Panel de grabacion dentro de OBS (Custom Browser Dock) ---
    URL_PANEL = "http://localhost:5678"  # puerto fijo de panel_grabacion.py
    RUTA_SCRIPT_OBS = str(Path(getattr(sys, "_MEIPASS", directorio_scripts())) / "OBS" / "obs_disparar_pipeline.py")
    ttk.Label(frame, text="Panel de grabación en OBS", font=("Segoe UI", 9, "bold")).grid(row=fila, column=0, sticky="w", pady=(8, 2)); fila += 1
    ttk.Label(frame, text="Sirve para grabar desde OBS y procesar tus grabaciones de inmediato; si grabas en MKV con varias pistas de audio, se procesan con las pistas separadas.", wraplength=640, justify="left").grid(row=fila, column=1, sticky="w"); fila += 1

    def fila_copiable(etiqueta, texto):
        ttk.Label(frame, text=etiqueta).grid(row=fila_actual[0], column=0, sticky="w", padx=(0, 8), pady=3)
        caja = ttk.Entry(frame, width=20); caja.insert(0, texto); caja.configure(state="readonly")
        caja.grid(row=fila_actual[0], column=1, sticky="ew", pady=3)
        def copiar():
            root.clipboard_clear(); root.clipboard_append(texto); root.update_idletasks()
            estado_panel.set(f"Copiado: {texto}")
        ttk.Button(frame, text="Copiar", command=copiar).grid(row=fila_actual[0], column=2, padx=(6, 0))
        fila_actual[0] += 1

    estado_panel = tk.StringVar()
    frame.estado_panel = estado_panel  # Tk borra la variable si Python la libera
    fila_actual = [fila]
    fila_copiable("Enlace del panel", URL_PANEL)
    fila_copiable("Script de OBS", RUTA_SCRIPT_OBS)
    fila = fila_actual[0]
    ttk.Label(frame, textvariable=estado_panel, wraplength=640, justify="left").grid(row=fila, column=1, sticky="w"); fila += 1

    def panel_activo():
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 5678), timeout=0.5):
                return True
        except OSError:
            return False

    def comprobar_panel():
        if panel_activo():
            estado_panel.set("El panel está en marcha: ya puedes añadirlo en OBS con el enlace.")
        else:
            estado_panel.set("El panel no está en marcha: pulsa \"Iniciar el panel ahora\" o abre OBS con el script instalado.")

    def iniciar_panel():
        """Arranca panel_grabacion.py (sin OBS) y avisa si falta alguna libreria."""
        import shutil
        if panel_activo():
            estado_panel.set("El panel ya está en marcha."); return
        script = recursos_dir() / "scripts" / "panel_grabacion.py" if getattr(sys, "frozen", False) else directorio_scripts() / "panel_grabacion.py"
        python = None if getattr(sys, "frozen", False) else (shutil.which("pythonw") or shutil.which("python") or sys.executable)
        if getattr(sys, "frozen", False):
            if not script.is_file():
                estado_panel.set("No se encontraron los recursos incluidos del panel."); return
            registro = open(directorio_scripts() / "panel_obs.log", "w", encoding="utf-8")
            subprocess.Popen([sys.executable, "--server"], cwd=str(directorio_scripts()), stdout=registro, stderr=subprocess.STDOUT)
            estado_panel.set("Iniciando el panel..."); root.after(2500, comprobar_panel); return
        if not python or not script.is_file():
            estado_panel.set("No se encontró Python o panel_grabacion.py. Ejecuta iniciar_panel.bat desde la carpeta del proyecto."); return
        prueba = subprocess.run([python.replace("pythonw", "python") if python.lower().endswith("pythonw.exe") else python, "-c", "import flask, obsws_python"],
                                capture_output=True, text=True)
        if prueba.returncode != 0:
            faltan = (prueba.stderr.strip().splitlines() or ["?"])[-1]
            estado_panel.set(f"Faltan librerías ({faltan}). Instálalas con: python -m pip install flask obsws-python"); return
        registro = open(directorio_scripts() / "panel_obs.log", "w", encoding="utf-8", errors="replace")
        subprocess.Popen([python, str(script)], cwd=str(directorio_scripts()), stdout=registro, stderr=subprocess.STDOUT,
                         env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
        estado_panel.set("Iniciando el panel...")
        root.after(2500, comprobar_panel)
    botones_panel = ttk.Frame(frame); botones_panel.grid(row=fila, column=1, sticky="w", pady=(2, 2)); fila += 1
    ttk.Button(botones_panel, text="Iniciar el panel ahora", command=iniciar_panel).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(botones_panel, text="Comprobar si está activo", command=comprobar_panel).grid(row=0, column=1, padx=(0, 6))
    ttk.Button(botones_panel, text="Abrir en el navegador", command=lambda: __import__("webbrowser").open(URL_PANEL)).grid(row=0, column=2)
    ttk.Label(frame, text=(
        "CÓMO AÑADIRLO EN OBS\n"
        "1. Script (una sola vez, para que el panel arranque con OBS): Herramientas > Scripts > pestaña \"Ajustes de Python\" "
        "(elige tu instalación de Python) > pestaña \"Scripts\" > \"+\" y selecciona el script de OBS de arriba.\n"
        "2. Panel: menú Ver (o Docks) > Acoples de navegador personalizados (Custom Browser Docks) > escribe un nombre, pega el enlace de arriba y pulsa Aplicar.\n"
        "3. Para pistas de audio separadas: Ajustes > Salida > Grabación > formato MKV y marca las pistas que quieras grabar."),
        wraplength=640, justify="left").grid(row=fila, column=1, sticky="w", pady=(2, 0)); fila += 1

    ttk.Separator(frame).grid(row=fila, columnspan=3, sticky="ew", pady=7); fila += 1
    ttk.Label(frame, text="POST-STREAM Y DURACION", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w"); fila += 1
    variables["MOSTRAR_CONTEXTO_POST_STREAM"] = tk.BooleanVar(value=bool(valores.get("MOSTRAR_CONTEXTO_POST_STREAM", True)))
    ttk.Checkbutton(frame, text="Mostrar contexto despues de detener grabacion", variable=variables["MOSTRAR_CONTEXTO_POST_STREAM"]).grid(row=fila, column=1, sticky="w"); fila += 1
    agregar_entrada(fila, "DURACION_MIN_CLIP", "Duracion minima (0 = sin limite)", ancho=12); fila += 1
    agregar_entrada(fila, "DURACION_MAX_CLIP", "Duración máxima (0 = sin límite; nunca se supera)", ancho=12); fila += 1

    ttk.Separator(frame).grid(row=fila, columnspan=3, sticky="ew", pady=7); fila += 1
    ttk.Label(frame, text="RECURSOS", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w"); fila += 1
    limite = limite_cpu_recomendado(); total = os.cpu_count() or 1
    ttk.Label(frame, text=f"CPU detectada: {total} hilos; limite seguro: {limite}").grid(row=fila, column=1, sticky="w"); fila += 1
    hilos = ttk.Spinbox(frame, from_=1, to=limite, width=10)
    hilos.set(str(min(int(valores.get("NUM_PROCESOS_TRANSCRIPCION", 1)), limite)))
    ttk.Label(frame, text="Hilos/procesos CPU").grid(row=fila, column=0, sticky="w"); hilos.grid(row=fila, column=1, sticky="w"); entradas["NUM_PROCESOS_TRANSCRIPCION"] = hilos; fila += 1
    variables["USAR_GPU_TRANSCRIPCION"] = tk.BooleanVar(value=bool(valores.get("USAR_GPU_TRANSCRIPCION", True)))
    check_gpu = ttk.Checkbutton(frame, text="Usar GPU para Whisper", variable=variables["USAR_GPU_TRANSCRIPCION"], state="disabled")
    check_gpu.grid(row=fila, column=1, sticky="w")
    texto_gpu = tk.StringVar(value="GPU: detectando...")
    frame.texto_gpu = texto_gpu  # evita que Tk la borre al liberarla Python
    # Debajo del check, no en la 3.ª columna: ese texto largo ensanchaba la columna de los botones
    # "Examinar" y encogia todos los campos de la izquierda.
    fila += 1
    ttk.Label(frame, textvariable=texto_gpu).grid(row=fila, column=1, sticky="w"); fila += 1
    resultado_gpu = {}
    threading.Thread(target=lambda: resultado_gpu.update(detectar_gpu()), daemon=True).start()

    def _aplicar_gpu():
        if not resultado_gpu:
            try: root.after(250, _aplicar_gpu)
            except tk.TclError: pass
            return
        gpu.update(resultado_gpu); gpu["listo"] = True
        texto_gpu.set(f"GPU: {gpu['modelo']} ({'compatible' if gpu['compatible'] else 'no compatible'})")
        if gpu["compatible"]:
            check_gpu.configure(state="normal")
        else:
            variables["USAR_GPU_TRANSCRIPCION"].set(False)
    root.after(250, _aplicar_gpu)

    ttk.Separator(frame).grid(row=fila, columnspan=3, sticky="ew", pady=7); fila += 1
    ttk.Label(frame, text="MOTOR DE TRANSCRIPCIÓN", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w"); fila += 1
    variables["TRANSCRIPCION_MOTOR"] = tk.StringVar(value=valores.get("TRANSCRIPCION_MOTOR") or "whisper_local")
    ttk.Radiobutton(frame, text="Whisper local (gratis, usa tu equipo)", value="whisper_local", variable=variables["TRANSCRIPCION_MOTOR"]).grid(row=fila, column=1, sticky="w"); fila += 1
    ttk.Radiobutton(frame, text="AssemblyAI (en la nube, requiere cuenta y API key)", value="assemblyai", variable=variables["TRANSCRIPCION_MOTOR"]).grid(row=fila, column=1, sticky="w"); fila += 1
    agregar_entrada(fila, "ASSEMBLYAI_API_KEY_ENV", "Variable con la API key de AssemblyAI", ancho=28); fila += 1
    api_key_asm = ttk.Entry(frame, width=20, show="*")
    ttk.Label(frame, text="API key de AssemblyAI").grid(row=fila, column=0, sticky="w"); api_key_asm.grid(row=fila, column=1, sticky="ew"); fila += 1
    ttk.Label(frame, text="Clave solo durante esta sesión; para conservarla, define la variable de entorno indicada.").grid(row=fila, column=1, sticky="w"); fila += 1
    ttk.Label(frame, text="Con AssemblyAI el audio del stream se envía a sus servidores (servicio externo, con su propio costo o crédito). Si falla o no hay clave, MKClips usa Whisper local automáticamente. Cambiar de motor vuelve a transcribir los streams ya procesados.", wraplength=640).grid(row=fila, column=1, sticky="w"); fila += 1

    ttk.Separator(frame).grid(row=fila, columnspan=3, sticky="ew", pady=7); fila += 1
    ttk.Label(frame, text="IA QUE ELIGE LOS CLIPS", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w"); fila += 1
    cfg_ia = llm_cliente.configuracion_llm(valores)
    variables["LLM_PROVEEDOR"] = tk.StringVar(value=cfg_ia["proveedor"])
    preset_var = tk.StringVar(value="Elegir proveedor...")
    ttk.Label(frame, text="Proveedor sugerido").grid(row=fila, column=0, sticky="w")
    combo_preset = ttk.Combobox(frame, textvariable=preset_var, values=tuple(llm_cliente.PRESETS), state="readonly", width=28)
    combo_preset.grid(row=fila, column=1, sticky="w"); fila += 1
    ttk.Label(frame, text="Tipo de API").grid(row=fila, column=0, sticky="w")
    ttk.Combobox(frame, textvariable=variables["LLM_PROVEEDOR"], values=llm_cliente.PROVEEDORES, state="readonly", width=28).grid(row=fila, column=1, sticky="w"); fila += 1
    valores = dict(valores, LLM_BASE_URL=valores.get("LLM_BASE_URL") or cfg_ia["base_url"], LLM_MODELO=valores.get("LLM_MODELO") or cfg_ia["modelo"], LLM_API_KEY_ENV=cfg_ia["clave_env"])
    agregar_entrada(fila, "LLM_BASE_URL", "URL base de la API"); fila += 1
    agregar_entrada(fila, "LLM_MODELO", "Modelo"); fila += 1
    agregar_entrada(fila, "LLM_API_KEY_ENV", "Variable con la API key", ancho=28); fila += 1
    api_key = ttk.Entry(frame, width=20, show="*")
    ttk.Label(frame, text="API key").grid(row=fila, column=0, sticky="w"); api_key.grid(row=fila, column=1, sticky="ew"); fila += 1
    ttk.Label(frame, text="Clave solo durante esta sesión; para conservarla, define la variable de entorno indicada.").grid(row=fila, column=1, sticky="w"); fila += 1
    estado_clave = tk.StringVar()
    ttk.Label(frame, textvariable=estado_clave, wraplength=640).grid(row=fila, column=1, sticky="w"); fila += 1
    agregar_entrada(fila, "LLM_MAX_TOKENS", "Maximo de tokens de respuesta", ancho=12); fila += 1
    agregar_entrada(fila, "LLM_TIMEOUT", "Tiempo limite por peticion (s)", ancho=12); fila += 1
    agregar_entrada(fila, "LLM_CONCURRENCIA", "Peticiones simultaneas a la IA (1-8)", ancho=12); fila += 1
    ttk.Label(frame, text="Con una API compatible con OpenAI sirve OpenAI, Gemini, DeepSeek, Groq, OpenRouter, Mistral, Kimi, LM Studio y otros: elige el proveedor, escribe el nombre exacto del modelo y tu API key.", wraplength=640).grid(row=fila, column=1, sticky="w"); fila += 1

    # ---------- Contexto para la IA ----------
    ttk.Separator(frame).grid(row=fila, column=0, columnspan=3, sticky="ew", pady=8); fila += 1
    ttk.Label(frame, text="CONTEXTO PARA LA IA", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w"); fila += 1
    ttk.Label(frame, text="Objetivo del proyecto").grid(row=fila, column=0, sticky="nw", pady=4)
    caja_contexto = tk.Text(frame, height=5, width=20, wrap="word")
    caja_contexto.insert("1.0", str(valores.get("CONTEXTO_PROYECTO", "")))
    caja_contexto.grid(row=fila, column=1, sticky="ew", pady=4); fila += 1
    ttk.Label(frame, text="Cuéntale a la IA qué buscas: tipo de contenido, tu audiencia, qué hace bueno un clip para ti y qué no quieres (por ejemplo: \"Clips de gameplay con humor para TikTok; prefiero reacciones genuinas y finales inesperados; nada de tiempos muertos\"). Se envía en cada análisis. El contexto de cada tanda o stream se escribe al agregarlo a la cola.", wraplength=640).grid(row=fila, column=1, sticky="w"); fila += 1

    ttk.Label(frame, text="Criterios del creador").grid(row=fila, column=0, sticky="nw", pady=(10, 4))
    caja_criterios = tk.Text(frame, height=9, width=20, wrap="word")
    caja_criterios.insert("1.0", contexto_ia.leer_criterios())
    caja_criterios.grid(row=fila, column=1, sticky="ew", pady=(10, 4)); fila += 1
    estado_criterios = tk.StringVar()
    frame.estado_criterios = estado_criterios  # Tk borra la variable si Python la libera: la etiqueta quedaria vacia
    ttk.Label(frame, textvariable=estado_criterios, wraplength=640, justify="left").grid(row=fila, column=1, sticky="w"); fila += 1
    botones_criterios = ttk.Frame(frame); botones_criterios.grid(row=fila, column=1, sticky="w", pady=(4, 0)); fila += 1
    ttk.Label(frame, text="Reglas cortas que la IA resume de tus valoraciones y notas. Revísalas y edítalas: lo que dejes aquí es lo que se envía en cada análisis, así que la IA (aunque sea pequeña o local) ya sabe qué buscas.", wraplength=640).grid(row=fila, column=1, sticky="w"); fila += 1

    def refrescar_estado_criterios():
        utiles = contexto_ia.valoraciones_utiles()
        acierto = indicador_acierto()
        if acierto["auc"] is not None:
            estado_acierto = f" Acierto del sistema: {acierto['auc'] * 100:.0f}% (50% = al azar; {acierto['n']} clips con puntaje)."
        else:
            estado_acierto = f" Acierto del sistema: aún sin datos suficientes ({acierto['n']} clips con puntaje; hacen falta 3 aprobados y 3 rechazados)."
        estado_criterios.set(f"{len(utiles)} valoraciones útiles (mínimo {contexto_ia.MINIMO_VALORACIONES} para generar reglas)." + estado_acierto)
    refrescar_estado_criterios()

    def guardar_criterios_ui():
        texto = contexto_ia.guardar_criterios(caja_criterios.get("1.0", "end"))
        messagebox.showinfo("Criterios", "Criterios guardados. Se usarán en el próximo análisis." if texto else "Criterios borrados.")

    def actualizar_criterios_ui():
        try:
            datos = valores_formulario()
        except Exception as exc:
            return messagebox.showerror("IA", str(exc))
        boton_generar.configure(state="disabled", text="Pensando...")
        # Todo lo que lee de la interfaz se toma ANTES de lanzar el hilo (Tk no admite llamadas desde otro hilo).
        actuales = caja_criterios.get("1.0", "end").strip()
        clave_ia = api_key.get().strip() or None
        resultado = {}

        def trabajo():
            try:
                resultado["ok"] = contexto_ia.generar_criterios(valores=datos, criterios_actuales=actuales,
                                                                contexto_proyecto=datos.get("CONTEXTO_PROYECTO", ""),
                                                                clave=clave_ia)
            except Exception as exc:
                resultado["error"] = str(exc)

        def terminar():
            if not resultado:
                return root.after(250, terminar)
            boton_generar.configure(state="normal", text="Actualizar con IA")
            if "ok" in resultado:
                caja_criterios.delete("1.0", "end"); caja_criterios.insert("1.0", resultado["ok"])
                messagebox.showinfo("Criterios", "Propuesta lista. Revísala y pulsa «Guardar criterios» para usarla.")
            else:
                messagebox.showerror("Criterios", resultado["error"])
        threading.Thread(target=trabajo, daemon=True).start()
        root.after(250, terminar)

    boton_generar = ttk.Button(botones_criterios, text="Actualizar con IA", command=actualizar_criterios_ui)
    boton_generar.grid(row=0, column=0, padx=(0, 6))
    ttk.Button(botones_criterios, text="Guardar criterios", command=guardar_criterios_ui).grid(row=0, column=1)

    # ---------- Limpieza de temporales ----------
    ttk.Separator(frame).grid(row=fila, column=0, columnspan=3, sticky="ew", pady=8); fila += 1
    ttk.Label(frame, text="MANTENIMIENTO", font=("Segoe UI", 10, "bold")).grid(row=fila, column=0, sticky="w"); fila += 1
    ttk.Button(frame, text="Limpiar archivos temporales...", command=lambda: abrir_limpieza()).grid(row=fila, column=1, sticky="w", pady=4); fila += 1
    ttk.Label(frame, text="Libera espacio borrando solo lo que MKClips vuelve a generar solo (audio temporal, miniaturas, residuos). Nunca toca tus clips, valoraciones ni configuración.", wraplength=640).grid(row=fila, column=1, sticky="w"); fila += 1

    def abrir_limpieza():
        cola_activa = ESTADO_APP.get("cola")
        if cola_activa is not None and cola_activa.is_running():
            return messagebox.showwarning("Limpieza", "Hay una cola procesando streams. Espera a que termine para limpiar.")
        carpeta_clips = str(valores_formulario().get("CARPETA_CLIPS_BASE") or "")
        dialogo = tk.Toplevel(root); dialogo.title("Limpiar archivos temporales"); dialogo.transient(root); dialogo.minsize(560, 300)
        dialogo.configure(background=ttk.Style().lookup("TFrame", "background") or "#222")
        cuerpo = ttk.Frame(dialogo, padding=14); cuerpo.pack(fill="both", expand=True); cuerpo.columnconfigure(0, weight=1)
        ttk.Label(cuerpo, text="Elige qué borrar:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        filas_limpieza = ttk.Frame(cuerpo); filas_limpieza.grid(row=1, column=0, sticky="ew", pady=(8, 0)); filas_limpieza.columnconfigure(0, weight=1)
        ttk.Label(filas_limpieza, text="Calculando tamaños...").grid(row=0, column=0, sticky="w")
        resumen = tk.StringVar(); dialogo.resumen = resumen; ttk.Label(cuerpo, textvariable=resumen, wraplength=520, justify="left").grid(row=2, column=0, sticky="w", pady=(10, 0))
        marcas, boton_borrar = {}, ttk.Button(cuerpo, text="Eliminar seleccionado", state="disabled")
        boton_borrar.grid(row=3, column=0, sticky="e", pady=(12, 0))
        resultado = {}

        def calcular():
            resultado["categorias"] = limpieza_temporales.analizar(carpeta_clips)

        def mostrar():
            if "categorias" not in resultado:
                return dialogo.after(150, mostrar)
            for hijo in filas_limpieza.winfo_children(): hijo.destroy()
            for numero, cat in enumerate(resultado["categorias"]):
                var = tk.BooleanVar(value=cat["marcada"] and cat["bytes"] > 0)
                marcas[cat["id"]] = var
                extra = f" ({cat['omitidos']} en uso reciente, se respetan)" if cat["omitidos"] else ""
                ttk.Checkbutton(filas_limpieza, text=f"{cat['nombre']} — {limpieza_temporales.formatear_tamano(cat['bytes'])}{extra}", variable=var,
                                state="normal" if cat["bytes"] else "disabled").grid(row=numero * 2, column=0, sticky="w", pady=(6, 0))
                etiqueta = ttk.Label(filas_limpieza, text=cat["descripcion"], justify="left"); etiqueta.grid(row=numero * 2 + 1, column=0, sticky="w", padx=(24, 0))
                texto_adaptable(filas_limpieza, etiqueta, 40)
            total = sum(c["bytes"] for c in resultado["categorias"])
            resumen.set(f"Total en temporales: {limpieza_temporales.formatear_tamano(total)}.")
            boton_borrar.configure(state="normal" if total else "disabled")

        def eliminar():
            elegidas = [i for i, v in marcas.items() if v.get()]
            if not elegidas:
                return messagebox.showinfo("Limpieza", "No hay nada seleccionado.", parent=dialogo)
            if "etapas" in elegidas and not messagebox.askyesno("Limpieza", "Vas a borrar los resultados guardados de las etapas. Si reprocesas un stream, se repetirá todo desde cero. ¿Continuar?", parent=dialogo):
                return
            n, liberado, errores = limpieza_temporales.eliminar(elegidas, carpeta_clips)
            texto = f"Se borraron {n} archivo(s) y se liberaron {limpieza_temporales.formatear_tamano(liberado)}."
            if errores:
                texto += "\nNo se pudo borrar: " + "; ".join(errores[:4])
            messagebox.showinfo("Limpieza", texto, parent=dialogo)
            dialogo.destroy()
        boton_borrar.configure(command=eliminar)
        threading.Thread(target=calcular, daemon=True).start()
        dialogo.after(150, mostrar)

    def aplicar_preset(_evento=None):
        nombre = preset_var.get()
        if nombre not in llm_cliente.PRESETS: return
        proveedor, url, modelo, env = llm_cliente.PRESETS[nombre]
        variables["LLM_PROVEEDOR"].set(proveedor)
        for clave, texto in (("LLM_BASE_URL", url), ("LLM_API_KEY_ENV", env)):
            entradas[clave].delete(0, tk.END); entradas[clave].insert(0, texto)
        if modelo or not entradas["LLM_MODELO"].get().strip():
            entradas["LLM_MODELO"].delete(0, tk.END); entradas["LLM_MODELO"].insert(0, modelo)
        refrescar_estado_clave()
    combo_preset.bind("<<ComboboxSelected>>", aplicar_preset)

    def refrescar_estado_clave(*_):
        env = entradas["LLM_API_KEY_ENV"].get().strip() or "LLM_API_KEY"
        if api_key.get().strip(): estado_clave.set("Se usará la clave escrita arriba.")
        elif os.environ.get(env, "").strip(): estado_clave.set(f"Clave encontrada en la variable de entorno {env}.")
        else: estado_clave.set(f"Sin clave: escríbela aquí o define la variable {env}.")
    entradas["LLM_API_KEY_ENV"].bind("<KeyRelease>", refrescar_estado_clave); api_key.bind("<KeyRelease>", refrescar_estado_clave)
    refrescar_estado_clave()

    def valores_formulario():
        datos = leer_configuracion()
        for clave, entrada in entradas.items():
            datos[clave] = entrada.get().strip()
        datos["MOSTRAR_CONTEXTO_POST_STREAM"] = variables["MOSTRAR_CONTEXTO_POST_STREAM"].get()
        # Si la deteccion aun no termino se conserva el valor ya guardado.
        if gpu["listo"]:
            datos["USAR_GPU_TRANSCRIPCION"] = variables["USAR_GPU_TRANSCRIPCION"].get() if gpu["compatible"] else False
        datos["LLM_PROVEEDOR"] = variables["LLM_PROVEEDOR"].get()
        datos["TRANSCRIPCION_MOTOR"] = variables["TRANSCRIPCION_MOTOR"].get()
        datos["CONTEXTO_PROYECTO"] = caja_contexto.get("1.0", "end").strip()
        # API key se excluye deliberadamente de este diccionario persistente.
        return normalizar_configuracion(datos)

    def aplicar_clave(datos):
        """Las claves y contraseñas solo viven en el entorno del proceso actual."""
        env = datos.get("LLM_API_KEY_ENV") or "LLM_API_KEY"
        clave = api_key.get().strip()
        if clave:
            os.environ[env] = clave
        clave_asm = api_key_asm.get().strip()
        if clave_asm:
            os.environ[datos.get("ASSEMBLYAI_API_KEY_ENV") or "ASSEMBLYAI_API_KEY"] = clave_asm
        clave_obs = datos.get("OBS_WS_CONTRASENA", "").strip()
        if "OBS_WS_CONTRASENA" in datos:
            if clave_obs:
                os.environ["OBS_WS_CONTRASENA"] = clave_obs
            else:
                os.environ.pop("OBS_WS_CONTRASENA", None)
        refrescar_estado_clave()

    def guardar():
        try:
            datos = valores_formulario()
            archivo = guardar_configuracion(datos)
            aplicar_clave(datos)
            messagebox.showinfo("MKClips", f"Configuracion guardada en {archivo}.")
        except Exception as exc:
            messagebox.showerror("Configuracion invalida", str(exc))

    def conectar_obs():
        try:
            # Guardar primero garantiza que control_grabacion lea la misma fuente central.
            guardar_configuracion(valores_formulario())
            probar_obs(); messagebox.showinfo("OBS", "Conexion con OBS WebSocket correcta.")
        except Exception as exc:
            messagebox.showerror("OBS", str(exc))

    def conectar_ia():
        try:
            datos = valores_formulario()
        except Exception as exc:
            return messagebox.showerror("IA", str(exc))
        clave = api_key.get().strip() or None
        boton_ia.configure(state="disabled", text="Probando...")
        resultado = {}

        def trabajo():
            try: resultado["ok"] = probar_ia(datos, clave or "")
            except Exception as exc: resultado["error"] = str(exc)

        def terminar():
            if not resultado:
                return root.after(200, terminar)
            boton_ia.configure(state="normal", text="Probar IA")
            if "ok" in resultado: messagebox.showinfo("IA", "Conexion correcta:\n" + resultado["ok"])
            else: messagebox.showerror("IA", resultado["error"])
        threading.Thread(target=trabajo, daemon=True).start()
        root.after(200, terminar)

    botones = ttk.Frame(frame); botones.grid(row=fila, column=1, sticky="e", pady=(12, 0))
    ttk.Button(botones, text="Probar OBS", command=conectar_obs).grid(row=0, column=0, padx=3)
    boton_ia = ttk.Button(botones, text="Probar IA", command=conectar_ia)
    boton_ia.grid(row=0, column=1, padx=3)
    ttk.Button(botones, text="Guardar configuracion", command=guardar).grid(row=0, column=2, padx=3)

    # Los nombres largos de la columna izquierda saltan de linea y los textos largos se ajustan al
    # ancho REAL de su celda (antes se median con un numero fijo y la rejilla los recortaba).
    ANCHO_ETIQUETAS = 210
    frame.columnconfigure(0, minsize=ANCHO_ETIQUETAS)

    def margen_de_celda(etiqueta):
        info = etiqueta.grid_info()
        columna, ancho_cols, fila_g = int(info["column"]), int(info.get("columnspan", 1)), int(info["row"])
        caja = frame.grid_bbox(columna, fila_g, columna + ancho_cols - 1, fila_g)
        return max(0, frame.winfo_width() - caja[2]) + 6
    for hijo in frame.winfo_children():
        info = hijo.grid_info()
        if not isinstance(hijo, ttk.Label) or not info:
            continue
        if int(info.get("column", 0)) == 0 and int(info.get("columnspan", 1)) == 1:
            hijo.configure(wraplength=ANCHO_ETIQUETAS, justify="left")
        elif int(info.get("column", 0)) == 1 or int(info.get("columnspan", 1)) > 1:
            if int(str(hijo.cget("wraplength")) or 0) or len(str(hijo.cget("text"))) > 40:
                hijo.configure(wraplength=300, justify="left")
                texto_adaptable(frame, hijo, lambda h=hijo: margen_de_celda(h))
    flujo, etapas = pagina_scroll(contenido)
    # "Flujo de trabajo" integra, en orden, las tres etapas: descargar el video,
    # procesarlo con la cola y consultar los resultados.
    etapas.columnconfigure(0, weight=1)
    fila_etapa = 0
    for construir in (crear_pestana_descargar, crear_pestana_procesar, crear_pestana_historial):
        widget = construir(etapas)
        if widget is None:
            continue
        if fila_etapa:
            ttk.Separator(etapas).grid(row=fila_etapa, column=0, sticky="ew", pady=8)
            fila_etapa += 1
        widget.grid(row=fila_etapa, column=0, sticky="ew", pady=3)
        fila_etapa += 1
    paginas = {
        "Flujo de trabajo": flujo,
        "Validar clips": crear_pestana_validar_clips(contenido),
        "Editar": crear_pestana_editar_segura(contenido),
        "Configuración": pagina_config,
    }
    def mostrar_pagina(pagina):
        for candidata in paginas.values(): candidata.grid_remove()
        pagina.grid(row=0, column=0, sticky="nsew")
    for fila_nav, (nombre, pagina) in enumerate(paginas.items()):
        ttk.Button(navegacion, text=nombre, width=19, command=lambda p=pagina: mostrar_pagina(p)).grid(row=fila_nav, column=0, sticky="ew", pady=3)
    tema = tk.StringVar(value=leer_tema())
    selector = ttk.Combobox(navegacion, textvariable=tema, values=tuple(PALETAS), state="readonly", width=17)
    selector.grid(row=len(paginas), column=0, pady=15)
    selector.bind("<<ComboboxSelected>>", lambda e: aplicar_tema(root, tema.get(), guardar=True))
    aplicar_tema(root, tema.get())
    def rueda(e):
        widget = e.widget
        while widget is not None:
            if hasattr(widget, "canvas_scroll"):
                widget.canvas_scroll.yview_scroll(-int(e.delta / 120), "units"); return
            widget = getattr(widget, "master", None)
    root.bind_all("<MouseWheel>", rueda)
    mostrar_pagina(flujo)
    return root


def crear_pestana_editar_segura(contenedor):
    """Pestaña «Editar». Si algo falla al crearla, la app sigue funcionando y la pestaña explica el problema."""
    try:
        if pestana_editar is None:
            raise RuntimeError("no se pudo cargar pestana_editar.py")
        return pestana_editar.crear_pestana_editar(contenedor, {
            "catalogo_clips": catalogo_clips, "cargar_preferencias": cargar_preferencias,
            "identificador_clip": identificador_clip, "feedback_por_clip": feedback_por_clip,
            "ruta_resultados": _ruta_resultados_actual, "generar_miniatura": _generar_miniatura_revision,
            "carpeta_cache": os.path.join(str(directorio_scripts()), ".mkclips_cache", "revision"),
        })
    except Exception as exc:  # noqa: BLE001
        marco = ttk.Frame(contenedor, padding=20)
        ttk.Label(marco, text=f"La pestaña Editar no está disponible: {exc}", wraplength=520).grid(row=0, column=0)
        return marco


def _ui_call(widget, callback, *args, **kwargs):
    """Ejecuta cambios Tkinter exclusivamente en el hilo de la interfaz."""
    try:
        if widget.winfo_exists():
            widget.after(0, callback, *args, **kwargs)
    except tk.TclError:
        pass


def crear_pestana_procesar(contenedor, resultados_dir=None):
    """Cola de streams. Se integra dentro de "Flujo de trabajo".

    ``resultados_dir`` permite apuntar a otra carpeta de estado (por defecto la
    carpeta de resultados configurada).
    """
    marco = ttk.Frame(contenedor, padding=14)
    marco.columnconfigure(0, weight=1)
    ttk.Label(marco, text="2. Procesar streams", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=5, sticky="w")
    descripcion_cola = ttk.Label(marco, text="Agrega uno o varios streams a la cola para procesarlos secuencialmente.", wraplength=760)
    descripcion_cola.grid(row=1, column=0, columnspan=5, sticky="w", pady=(0, 8))
    texto_adaptable(marco, descripcion_cola, 40)

    botones_add = ttk.Frame(marco); botones_add.grid(row=2, column=0, columnspan=5, sticky="w")
    ttk.Button(botones_add, text="Agregar streams", command=lambda: _agregar_stream()).grid(row=0, column=0, padx=(0, 6))
    ttk.Button(botones_add, text="Agregar carpeta", command=lambda: _agregar_carpeta()).grid(row=0, column=1)

    # Contexto de la tanda: se copia a cada stream que agregues (y se puede ajustar stream por stream).
    marco_contexto = ttk.Frame(marco); marco_contexto.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(8, 0)); marco_contexto.columnconfigure(0, weight=1)
    ttk.Label(marco_contexto, text="Contexto de esta tanda (opcional): juego, qué pasa en estos videos, qué buscar. Se aplica a los streams que agregues.", justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
    etiqueta_ayuda_contexto = marco_contexto.grid_slaves(row=0, column=0)[0]
    texto_adaptable(marco_contexto, etiqueta_ayuda_contexto, 20)
    caja_tanda = tk.Text(marco_contexto, height=3, width=20, wrap="word")
    caja_tanda.grid(row=1, column=0, sticky="ew", pady=(3, 0))
    botones_contexto = ttk.Frame(marco_contexto); botones_contexto.grid(row=1, column=1, sticky="n", padx=(8, 0), pady=(3, 0))
    ttk.Button(botones_contexto, text="Aplicar a toda la cola", command=lambda: _aplicar_a_cola()).grid(row=0, column=0, sticky="ew")
    ttk.Button(botones_contexto, text="Editar el del seleccionado...", command=lambda: _editar_contexto()).grid(row=1, column=0, sticky="ew", pady=(4, 0))

    # Aviso NO modal: solo aparece si de verdad quedan streams sin procesar.
    aviso = ttk.Frame(marco)
    aviso_texto = tk.StringVar()
    marco.aviso_texto = aviso_texto  # evita que Python libere la variable y la etiqueta quede vacía
    ttk.Label(aviso, textvariable=aviso_texto, style="aviso.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
    ttk.Button(aviso, text="Continuar", command=lambda: _aviso_continuar()).grid(row=0, column=1, padx=3)
    ttk.Button(aviso, text="Descartar", command=lambda: _aviso_descartar()).grid(row=0, column=2, padx=3)

    columnas = ("stream", "contexto", "estado")
    tree = ttk.Treeview(marco, columns=columnas, show="headings", height=6)
    tree.heading("stream", text="Stream")
    tree.heading("contexto", text="Contexto")
    tree.heading("estado", text="Estado")
    tree.column("stream", width=300, anchor="w", stretch=True)
    tree.column("contexto", width=80, anchor="center", stretch=False)
    tree.column("estado", width=120, anchor="center", stretch=False)
    tree.grid(row=5, column=0, columnspan=5, sticky="ew", pady=(6, 6))

    controles = ttk.Frame(marco); controles.grid(row=6, column=0, columnspan=5, sticky="w")
    for columna, (texto, comando) in enumerate((
        ("Iniciar cola", lambda: _iniciar_cola()), ("Pausar", lambda: _pausar_cola()),
        ("Reanudar", lambda: _reanudar_cola()), ("Cancelar", lambda: _cancelar_cola()),
        ("Limpiar terminados", lambda: _limpiar_terminados()),
    )):
        # En dos filas: en una sola, "Limpiar terminados" se salia de la ventana.
        ttk.Button(controles, text=texto, command=comando).grid(row=columna // 3, column=columna % 3, padx=(0, 6), pady=(0, 4), sticky="w")

    progress_var = tk.StringVar(value="Cola vacía")
    ttk.Label(marco, textvariable=progress_var).grid(row=7, column=0, columnspan=5, sticky="w")
    status_var = tk.StringVar(value="Sin procesamiento activo")
    etiqueta_estado_cola = ttk.Label(marco, textvariable=status_var, justify="left")
    etiqueta_estado_cola.grid(row=8, column=0, columnspan=5, sticky="w")
    texto_adaptable(marco, etiqueta_estado_cola, 40)
    marco.columnconfigure(0, weight=1)

    def mostrar_ruta_completa(_evento=None):
        """El nombre de un stream largo no cabe en la tabla: al elegirlo se lee entero aqui."""
        seleccion = tree.selection()
        if seleccion:
            indice = tree.index(seleccion[0])
            cola_actual = manager.get_queue()
            if indice < len(cola_actual):
                status_var.set(cola_actual[indice]["path"])
    tree.bind("<<TreeviewSelect>>", mostrar_ruta_completa)

    try:
        from scripts.cola_procesamiento import QueueManager
    except ModuleNotFoundError:
        from cola_procesamiento import QueueManager
    manager = QueueManager(resultados_dir or _ruta_resultados_actual(), notificar=lambda msg: _ui_call(marco, status_var.set, msg))
    ESTADO_APP["cola"] = manager

    estado_ui = {"snap": None, "job": None}

    def _refrescar():
        cola = manager.get_queue()
        snap = tuple((os.path.basename(i["path"]), "✎" if i.get("contexto") else "", i["status"]) for i in cola)
        if snap == estado_ui["snap"]:
            return
        estado_ui["snap"] = snap
        filas = tree.get_children()
        for n, valores_fila in enumerate(snap):
            if n < len(filas):
                tree.item(filas[n], values=valores_fila)
            else:
                tree.insert("", "end", values=valores_fila)
        for sobrante in filas[len(snap):]:
            tree.delete(sobrante)
        total = len(cola)
        if total == 0:
            progress_var.set("Cola vacía")
            return
        en_proceso = next((n for n, i in enumerate(cola) if i["status"] == "PROCESANDO"), None)
        if en_proceso is not None:
            progress_var.set(f"Procesando {en_proceso + 1} de {total}")
        else:
            terminados = sum(1 for i in cola if i["status"] in ("COMPLETADO", "ERROR", "CANCELADO", "OMITIDO"))
            progress_var.set(f"Completados {terminados} de {total}")

    def _ciclo():
        estado_ui["job"] = None
        try:
            if not marco.winfo_exists():
                return
            # Solo trabaja mientras la etapa es visible o la cola esta corriendo.
            if marco.winfo_ismapped() or manager.is_running():
                _refrescar()
            estado_ui["job"] = marco.after(1000, _ciclo)
        except tk.TclError:
            pass

    def _al_destruir(evento):
        if evento.widget is marco and estado_ui["job"]:
            try: marco.after_cancel(estado_ui["job"])
            except tk.TclError: pass
            estado_ui["job"] = None
    marco.bind("<Destroy>", _al_destruir, add="+")
    marco.bind("<Map>", lambda _e: _refrescar(), add="+")

    def _ocultar_aviso():
        aviso.grid_remove()

    def _aviso_continuar():
        _ocultar_aviso(); manager.start(); _refrescar()

    def _aviso_descartar():
        manager.descartar_todo(); _ocultar_aviso(); _refrescar()

    def _agregar_stream():
        paths = filedialog.askopenfilenames(filetypes=[("Videos", "*.mkv *.mp4 *.mov *.avi *.wmv *.flv *.webm *.mpeg *.mpg *.m4v *.3gp *.3g2")])
        contexto = caja_tanda.get("1.0", "end").strip()
        for p in paths:
            manager.add_stream(p, contexto)
        _refrescar()

    def _agregar_carpeta():
        carpeta = filedialog.askdirectory(title="Seleccionar carpeta de streams")
        if carpeta:
            manager.add_folder(carpeta, caja_tanda.get("1.0", "end").strip())
            _refrescar()

    def _aplicar_a_cola():
        n = manager.aplicar_contexto_pendientes(caja_tanda.get("1.0", "end").strip())
        status_var.set(f"Contexto aplicado a {n} stream(s) pendiente(s)." if n else "No hay streams pendientes en la cola.")
        _refrescar()

    def _editar_contexto(_evento=None):
        """Ventana para ajustar el contexto de UN stream (por ejemplo, si ese video es de otro juego)."""
        seleccion = tree.selection()
        if not seleccion:
            return status_var.set("Selecciona un stream de la tabla para editar su contexto.")
        cola_actual = manager.get_queue()
        indice = tree.index(seleccion[0])
        if indice >= len(cola_actual):
            return
        item = cola_actual[indice]
        if item["status"] != "ESPERANDO":
            return status_var.set("Solo se puede cambiar el contexto de streams que aún esperan.")
        dialogo = tk.Toplevel(marco.winfo_toplevel()); dialogo.title("Contexto del stream"); dialogo.transient(marco.winfo_toplevel()); dialogo.minsize(520, 240)
        cuerpo = ttk.Frame(dialogo, padding=12); cuerpo.pack(fill="both", expand=True); cuerpo.columnconfigure(0, weight=1); cuerpo.rowconfigure(1, weight=1)
        titulo = ttk.Label(cuerpo, text=os.path.basename(item["path"]), font=("Segoe UI", 10, "bold"), justify="left"); titulo.grid(row=0, column=0, sticky="w")
        texto_adaptable(cuerpo, titulo, 24)
        caja = tk.Text(cuerpo, height=7, width=20, wrap="word"); caja.grid(row=1, column=0, sticky="nsew", pady=8)
        caja.insert("1.0", item.get("contexto", "")); caja.focus_set()

        def aceptar():
            manager.set_contexto(item["path"], caja.get("1.0", "end"))
            dialogo.destroy(); _refrescar()
        ttk.Button(cuerpo, text="Guardar contexto", command=aceptar).grid(row=2, column=0, sticky="e")
    tree.bind("<Double-1>", _editar_contexto)

    def _iniciar_cola():
        _ocultar_aviso()
        if not manager.pending_count():
            status_var.set("No hay streams pendientes en la cola.")
            return
        manager.start()

    def _reanudar_cola():
        manager.resume()

    def _pausar_cola():
        manager.pause()

    def _cancelar_cola():
        manager.cancel()

    def _limpiar_terminados():
        manager.limpiar_terminados(); _refrescar()

    # Sesion anterior: se limpian los streams ya procesados y solo se avisa si
    # quedan pendientes reales.
    pendientes = manager.depurar_sesion_anterior()
    if pendientes:
        aviso_texto.set(f"Hay {pendientes} stream(s) pendiente(s) de la sesión anterior.")
        aviso.grid(row=4, column=0, columnspan=5, sticky="w", pady=(8, 0))
    _refrescar()
    estado_ui["job"] = marco.after(1000, _ciclo)
    return marco



def crear_pestana_descargar(contenedor):
    marco=ttk.Frame(contenedor,padding=14)
    ttk.Label(marco, text="1. Descargar video", font=("Segoe UI", 14, "bold")).grid(row=0,column=0,columnspan=3,sticky="w")
    descripcion_descarga = ttk.Label(marco, text="Descarga un video en la carpeta elegida para poder procesarlo posteriormente.", wraplength=760)
    descripcion_descarga.grid(row=1,column=0,columnspan=3,sticky="w",pady=(0,12))
    texto_adaptable(marco, descripcion_descarga, 40)
    url,destino,estado=tk.StringVar(),tk.StringVar(value=leer_configuracion().get("CARPETA_STREAMS", "")),tk.StringVar()
    descargando = {"valor": False}
    ttk.Label(marco,text="URL").grid(row=2,column=0,sticky="w");ttk.Entry(marco,textvariable=url,width=20).grid(row=2,column=1,sticky="ew",padx=(8,0))
    ttk.Label(marco,text="Destino").grid(row=3,column=0,sticky="w");ttk.Entry(marco,textvariable=destino,width=20).grid(row=3,column=1,sticky="ew",padx=(8,0))
    ttk.Button(marco,text="Examinar",command=lambda: destino.set(filedialog.askdirectory() or destino.get())).grid(row=3,column=2,padx=(6,0))
    def bajar():
        from urllib.parse import urlparse
        if urlparse(url.get().strip()).scheme not in {"http","https"} or not destino.get().strip():return messagebox.showerror("Descarga","URL o destino invalido.")
        if descargando["valor"]:
            return messagebox.showinfo("Descarga", "Ya hay una descarga en curso.")
        descargando["valor"] = True
        def actualizar_estado(valor):
            _ui_call(marco, estado.set, str(valor))
        def tarea():
            try:
                from descargar_video import descargar_video
                _ui_call(marco, estado.set, "Descargando...")
                archivo=descargar_video(url.get().strip(),destino.get().strip(),actualizar_estado)
                _ui_call(marco, estado.set, "Listo: "+archivo)
            except Exception as e:
                _ui_call(marco, estado.set, "ERROR: "+str(e))
            finally:
                descargando["valor"] = False
        threading.Thread(target=tarea,daemon=True).start()
    ttk.Button(marco,text="DESCARGAR",command=bajar).grid(row=4,column=1,sticky="w",pady=8);
    etiqueta_estado_descarga = ttk.Label(marco,textvariable=estado,wraplength=650)
    etiqueta_estado_descarga.grid(row=5,column=0,columnspan=3,sticky="w")
    texto_adaptable(marco, etiqueta_estado_descarga, 40)
    marco.columnconfigure(1, weight=1)  # los campos ocupan el ancho disponible: la ruta completa se lee
    return marco


def crear_pestana_historial(contenedor):
    marco=ttk.Frame(contenedor,padding=14)
    ttk.Label(marco, text="3. Historial / Resultados", font=("Segoe UI", 14, "bold")).grid(row=0,column=0,columnspan=2,sticky="w")
    descripcion_historial = ttk.Label(marco, text="Consulta los artefactos reales del último procesamiento sin modificar sus datos.", wraplength=760)
    descripcion_historial.grid(row=1,column=0,columnspan=2,sticky="w",pady=(0,8))
    texto_adaptable(marco, descripcion_historial, 40)
    marco.columnconfigure(0, weight=1)
    caja=tk.Text(marco,width=20,height=9,wrap="word");caja.grid(row=3,column=0,columnspan=2,sticky="nsew")
    nombres=("candidatos_todos.json","candidatos_cortos.json","clips_sugeridos.json","resumen_plan.json","scores_clips.json","metricas_identificacion.json","juego_contexto.json","arcos_narrativos.json","metricas_proceso.json","eventos_visuales.json","metricas_visual.json","transcripcion.json","eventos_audio.json")
    def refrescar():
        base=leer_configuracion().get("CARPETA_RESULTADOS") or os.path.join(str(directorio_scripts()),"resultados");caja.delete("1.0",tk.END);caja.insert(tk.END,"Resultados: "+base+"\n\n")
        for n in nombres:
            p=os.path.join(base,n);caja.insert(tk.END,f"{'OK' if os.path.isfile(p) else 'No existe'}  {n}\n")
    ttk.Button(marco,text="Refrescar",command=refrescar).grid(row=2,column=0,sticky="w");ttk.Button(marco,text="Abrir carpeta",command=lambda: _abrir_carpeta_sistema(leer_configuracion().get("CARPETA_RESULTADOS") or os.path.join(str(directorio_scripts()),"resultados"))).grid(row=2,column=1,sticky="w");marco.rowconfigure(3,weight=1);marco.columnconfigure(0,weight=1);refrescar()
    return marco


# La pestaña consume únicamente datos de salida y una lista blanca de metadatos.
# No se muestran campos de prompts, razonamientos ni explicaciones generadas.



def _ruta_resultados_actual():
    return leer_configuracion().get("CARPETA_RESULTADOS") or os.path.join(str(directorio_scripts()), "resultados")


def _video_actual():
    ruta = os.path.join(str(directorio_scripts()), "ultimo_video.txt")
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            video = archivo.readline().strip()
        return video if os.path.isfile(video) else ""
    except OSError:
        return ""


def _estado_feedback(entrada):
    if not entrada:
        return "SIN_VALORAR"
    if entrada.get("discarded"):
        return "DESCARTADO"
    rating = entrada.get("rating")
    return f"VALORADO_{rating}" if isinstance(rating, int) and 1 <= rating <= 5 else "SIN_VALORAR"


def _duracion_clip(clip):
    try:
        return float(clip.get("duracion", float(clip["fin"]) - float(clip["inicio"])))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _metadatos_visibles(clip, validacion):
    """Construye solo etiquetas controladas, nunca texto explicativo de modelos."""
    tipo = "Historia" if clip.get("tipo_candidato") in {"historia", "completo"} or clip.get("tipo") == "completo" else "Momento independiente"
    eventos = clip.get("eventos_visuales", [])
    segmentos = clip.get("segmentos", [])
    estado_tecnico = validacion.get("estado", "NO DISPONIBLE") if validacion else "NO DISPONIBLE"
    score = clip.get("score_bruto", clip.get("score_intrinseco", clip.get("score")))
    partes = [
        tipo,
        f"Duración: {_duracion_clip(clip):.1f}s",
        f"Segmentos: {len(segmentos) if isinstance(segmentos, list) else 0}",
        f"Eventos detectados: {len(eventos) if isinstance(eventos, list) else 0}",
        f"Validación técnica: {estado_tecnico}",
    ]
    if isinstance(score, (int, float)):
        partes.append(f"Puntuación: {score:.0f}")
    return tipo, partes


ANCHO_MAX_MINIATURA = 320
ALTO_MAX_MINIATURA = 320


@lru_cache(maxsize=128)
def _dimensiones_video_cache(ruta, size, mtime_ns):
    """Consulta ffprobe una sola vez por versión física del archivo."""
    try:
        resultado = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", ruta],
            capture_output=True, text=True, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        salida = resultado.stdout.strip()
        ancho_str, _, alto_str = salida.partition("x")
        ancho, alto = int(ancho_str), int(alto_str)
        if ancho > 0 and alto > 0:
            return ancho, alto
    except (OSError, ValueError):
        pass
    return None


def _dimensiones_video(archivo):
    """Ancho x alto reales, con caché por tamaño/mtime."""
    try:
        sello = os.stat(archivo)
    except OSError:
        return None
    return _dimensiones_video_cache(os.path.abspath(archivo), sello.st_size, sello.st_mtime_ns)


def _dimensiones_ajustadas(dimensiones, ancho_max=ANCHO_MAX_MINIATURA, alto_max=ALTO_MAX_MINIATURA):
    """'contain': el video entero cabe dentro de la caja maxima, sin
    deformar ni recortar, respetando su aspect ratio real. Sin
    dimensiones conocidas, cae a un 16:9 razonable por defecto."""
    if not dimensiones:
        return ancho_max, round(ancho_max * 9 / 16)
    ancho_real, alto_real = dimensiones
    escala = min(ancho_max / ancho_real, alto_max / alto_real)
    ancho_final = max(2, round(ancho_real * escala))
    alto_final = max(2, round(alto_real * escala))
    # ffmpeg exige dimensiones pares para varios codecs/filtros de escalado.
    ancho_final -= ancho_final % 2
    alto_final -= alto_final % 2
    return ancho_final, alto_final


def _escribir_atomico(destino, datos):
    temporal = destino + f".{os.getpid()}.{threading.get_ident()}.tmp"
    with open(temporal, "wb") as salida:
        salida.write(datos)
    os.replace(temporal, destino)


def _miniatura_cv2(archivo, miniatura):
    """Miniatura en el mismo proceso (sin lanzar ffprobe ni ffmpeg).
    Devuelve True si pudo generarla."""
    if _obtener_cv2() is None:
        return False
    cap = abrir_captura(archivo)
    try:
        if not cap.isOpened():
            return False
        cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
        ok, fotograma = cap.read()
        if not ok:  # clip de menos de 1 s
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, fotograma = cap.read()
        if not ok or fotograma is None:
            return False
        alto_real, ancho_real = fotograma.shape[:2]
        ancho, alto = _dimensiones_ajustadas((ancho_real, alto_real))
        reducido = cv2.resize(fotograma, (ancho, alto), interpolation=cv2.INTER_AREA)
        ok, png = cv2.imencode(".png", reducido, [cv2.IMWRITE_PNG_COMPRESSION, 1])
        if not ok:
            return False
        _escribir_atomico(miniatura, png.tobytes())
        return True
    except Exception:
        return False
    finally:
        cap.release()


def _preview_cv2(archivo, preview):
    """GIF de 3 s a 6 fps generado con OpenCV + Pillow. True si lo logra."""
    if _obtener_cv2() is None or Image is None:
        return False
    cap = abrir_captura(archivo)
    try:
        if not cap.isOpened():
            return False
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        if not 1 <= fps <= 240:
            fps = 30
        cap.set(cv2.CAP_PROP_POS_MSEC, 500)
        paso, leidos, cuadros, medidas = max(1, round(fps / 6)), 0, [], None
        while len(cuadros) < 18 and cap.grab():
            if leidos % paso == 0:
                ok, fotograma = cap.retrieve()
                if not ok:
                    break
                if medidas is None:
                    alto_real, ancho_real = fotograma.shape[:2]
                    medidas = _dimensiones_ajustadas((ancho_real, alto_real))
                reducido = cv2.resize(fotograma, medidas, interpolation=cv2.INTER_AREA)
                cuadros.append(Image.fromarray(cv2.cvtColor(reducido, cv2.COLOR_BGR2RGB)))
            leidos += 1
        if not cuadros:
            return False
        temporal = preview + f".{os.getpid()}.{threading.get_ident()}.tmp.gif"
        cuadros[0].save(temporal, save_all=True, append_images=cuadros[1:], duration=167, loop=0)
        os.replace(temporal, preview)
        return True
    except Exception:
        return False
    finally:
        cap.release()


def _generar_miniatura_revision(archivo, miniatura):
    """Genera solo la primera imagen; nunca bloquea la creación de tarjetas.
    Usa OpenCV en el propio proceso (rápido) y, si no está disponible, cae a
    ffmpeg. Respeta el aspect ratio real: nunca deforma ni recorta."""
    if not os.path.isfile(archivo):
        raise FileNotFoundError("El archivo del clip ya no existe.")
    os.makedirs(os.path.dirname(miniatura), exist_ok=True)
    if os.path.isfile(miniatura):
        return
    if _miniatura_cv2(archivo, miniatura):
        return
    ancho, alto = _dimensiones_ajustadas(_dimensiones_video(archivo))
    temporal = miniatura + f".{os.getpid()}.{threading.get_ident()}.tmp.png"
    resultado = subprocess.run([
        "ffmpeg", "-y", "-ss", "1", "-i", archivo, "-frames:v", "1",
        "-vf", f"scale={ancho}:{alto},format=rgb24", temporal,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False,
       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if resultado.returncode:
        raise RuntimeError("FFmpeg no pudo generar la miniatura.")
    os.replace(temporal, miniatura)


def _generar_preview_revision(archivo, preview):
    """GIF corto para el hover. Mismo cálculo 'contain' que la miniatura."""
    if not os.path.isfile(archivo):
        raise FileNotFoundError("El archivo del clip ya no existe.")
    os.makedirs(os.path.dirname(preview), exist_ok=True)
    if os.path.isfile(preview):
        return
    if _preview_cv2(archivo, preview):
        return
    ancho, alto = _dimensiones_ajustadas(_dimensiones_video(archivo))
    temporal = preview + f".{os.getpid()}.{threading.get_ident()}.tmp.gif"
    resultado = subprocess.run([
        "ffmpeg", "-y", "-ss", "0.5", "-t", "3", "-i", archivo,
        "-vf", f"fps=6,scale={ancho}:{alto},format=rgb24", temporal,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False,
       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    if resultado.returncode:
        raise RuntimeError("FFmpeg no pudo generar la vista previa.")
    os.replace(temporal, preview)


def _tooltip(widget, texto):
    """Tooltip ligero para metadatos compactos."""
    ventana = {"valor": None}
    def mostrar(_evento=None):
        if ventana["valor"]: return
        root = widget.winfo_toplevel()
        label = ttk.Label(root, text=texto, padding=(6, 3), relief="solid")
        label.place(x=max(0, min(widget.winfo_rootx() - root.winfo_rootx(), root.winfo_width() - 320)),
                    y=widget.winfo_rooty() - root.winfo_rooty() + widget.winfo_height() + 4)
        label.lift(); ventana["valor"] = label
    def ocultar(_evento=None):
        if ventana["valor"]:
            ventana["valor"].destroy(); ventana["valor"] = None
    widget.bind("<Enter>", mostrar, add="+"); widget.bind("<Leave>", ocultar, add="+")
    widget.bind("<Destroy>", ocultar, add="+")


def crear_pestana_validar_clips(contenedor):
    marco = ttk.Frame(contenedor, padding=10)
    marco.columnconfigure(0, weight=1); marco.rowconfigure(3, weight=1)
    estado = tk.StringVar(value="Carga resultados reales para valorar clips.")
    filtro_estado, filtro_tipo = tk.StringVar(value="Sin valorar"), tk.StringVar(value="Todos")
    cambios, tarjetas, clips_cargados = {}, [], []
    maximo_cfg = {"valor": 0.0}
    preview_activo = {"id": None}
    preview_en_proceso = threading.Lock()
    miniaturas_pool = ThreadPoolExecutor(max_workers=min(4, max(2, (os.cpu_count() or 2) // 2)))
    marco.bind("<Destroy>", lambda e: miniaturas_pool.shutdown(wait=False, cancel_futures=True) if e.widget is marco else None, add="+")
    # Los hilos NO tocan Tk: dejan aqui las miniaturas listas y la interfaz las pinta.
    miniaturas_listas = queue.SimpleQueue()
    drenaje = {"n": 0, "job": None}

    ttk.Label(marco, text="Validar clips", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
    leyenda = ttk.Label(marco, text="La validación técnica comprueba archivos y segmentos. Tu valoración de 1 (malo) a 5 (excelente) es independiente del score automático. Aquí aparecen los clips de TODOS los streams que aún no has valorado; al guardar, los valorados dejan de mostrarse y los descartados se borran de la carpeta de clips. Tus valoraciones guían la elección de los próximos clips: la IA recibe lo que aprobaste y rechazaste, y el puntaje baja o sube según cuánto se parezca a ello. Al valorar, indica el motivo (por qué te gustó o por qué no): le sirve a la IA para entenderte. Un mal corte o un fallo técnico no cuentan como gusto.", wraplength=700)
    leyenda.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    marco.bind("<Configure>", lambda e: leyenda.configure(wraplength=max(250, e.width - 30)))
    controles = ttk.Frame(marco); controles.grid(row=2, column=0, sticky="ew", pady=(0, 6))
    ttk.Label(controles, text="Estado:").grid(row=0, column=0, padx=(0, 4))
    ttk.Combobox(controles, textvariable=filtro_estado, values=("Todos", "Sin valorar", "Valorados", "Descartados"), state="readonly", width=15).grid(row=0, column=1)
    ttk.Label(controles, text="Tipo:").grid(row=0, column=2, padx=(14, 4))
    ttk.Combobox(controles, textvariable=filtro_tipo, values=("Todos", "Historias", "Momentos"), state="readonly", width=13).grid(row=0, column=3)

    zona = ttk.Frame(marco); zona.grid(row=3, column=0, sticky="nsew"); zona.columnconfigure(0, weight=1); zona.rowconfigure(0, weight=1)
    lienzo = tk.Canvas(zona, highlightthickness=0)
    barra = ttk.Scrollbar(zona, orient="vertical", command=lienzo.yview)
    contenido = ttk.Frame(lienzo)
    contenido.columnconfigure(0, weight=1)
    ventana_contenido = lienzo.create_window((0, 0), window=contenido, anchor="nw")
    lienzo.configure(yscrollcommand=barra.set)
    lienzo.grid(row=0, column=0, sticky="nsew"); barra.grid(row=0, column=1, sticky="ns")
    contenido.bind("<Configure>", lambda _e: lienzo.configure(scrollregion=lienzo.bbox("all")))
    lienzo.bind("<Configure>", lambda e: lienzo.itemconfigure(ventana_contenido, width=e.width))
    marco.canvas_scroll = lienzo
    vacio = ttk.Label(contenido, text="", anchor="center", justify="center", wraplength=520)
    def _abrir_clip(clip):
        """Abre el clip con el reproductor predeterminado del sistema operativo."""
        ok, mensaje = reproductor_sistema.abrir_en_reproductor(clip.get("ruta_archivo") or clip.get("archivo") or "")
        if not ok:
            messagebox.showerror("Reproducir clip", mensaje)

    def detener_preview():
        actual = preview_activo.get("id")
        if actual:
            actual["corriendo"] = False
            etiqueta = actual.get("miniatura")
            imagen = actual.get("imagen_estatica")
            if etiqueta and imagen:
                try: etiqueta.configure(image=imagen, text="")
                except tk.TclError: pass
            preview_activo["id"] = None


    def aplicar_filtros(*_):
        visibles = 0
        for tarjeta in tarjetas:
            clip, frame = tarjeta["clip"], tarjeta["frame"]
            estado_clip = cambios.get(tarjeta["id"], tarjeta["estado_inicial"])
            tipo, _ = _metadatos_visibles(clip, tarjeta["validacion"])
            # "Sin valorar" usa el estado ya guardado: un clip que acabas de puntuar
            # no desaparece hasta que pulses "Guardar valoraciones".
            coincide_estado = (filtro_estado.get() == "Todos"
                               or (filtro_estado.get() == "Sin valorar" and tarjeta["estado_inicial"] == "SIN_VALORAR")
                               or (filtro_estado.get() == "Valorados" and estado_clip.startswith("VALORADO_"))
                               or (filtro_estado.get() == "Descartados" and estado_clip == "DESCARTADO"))
            coincide_tipo = filtro_tipo.get() == "Todos" or (filtro_tipo.get() == "Historias" and tipo == "Historia") or (filtro_tipo.get() == "Momentos" and tipo != "Historia")
            if coincide_estado and coincide_tipo:
                frame.grid(); visibles += 1
            else:
                frame.grid_remove()
        if tarjetas and not visibles:
            vacio.configure(text="No hay clips con este filtro." if filtro_estado.get() != "Sin valorar" else "No hay clips pendientes de validar. Todos los clips ya están valorados.")
            vacio.grid(row=len(tarjetas) + 1, column=0, pady=30)
        else:
            vacio.grid_remove()
        marco.after_idle(_pedir_miniaturas)

    def construir_tarjetas():
        detener_preview()
        for hijo in contenido.winfo_children():
            if hijo is not vacio: hijo.destroy()
        tarjetas.clear()
        preferencias = cargar_preferencias()
        for fila, clip in enumerate(clips_cargados):
            validacion = clip.get("_validacion")
            fuente = clip.get("_fuente")
            clip_id = identificador_clip(clip, fuente)
            inicial = _estado_feedback(_feedback_de(clip, fuente, preferencias))
            nombre_stream = clip.get("_stream") or ""
            tarjeta = ttk.LabelFrame(contenido, padding=8)
            tarjeta.grid(row=fila, column=0, sticky="ew", padx=2, pady=3); tarjeta.columnconfigure(1, weight=1)
            marco_miniatura = ttk.Frame(tarjeta, relief="sunken")
            marco_miniatura.grid(row=0, column=0, rowspan=7, sticky="nw", padx=(0, 10))
            etiqueta_miniatura = ttk.Label(marco_miniatura, text="Cargando...", anchor="center", cursor="hand2")
            etiqueta_miniatura.pack()
            icono_play = ttk.Label(marco_miniatura, text="▶", font=("Segoe UI", 18, "bold"), cursor="hand2")
            icono_play.place(relx=0.5, rely=0.5, anchor="center")
            tipo, detalles = _metadatos_visibles(clip, validacion)
            # Titulo completo (varias lineas si hace falta) en vez del titulo del LabelFrame, que se cortaba.
            etiqueta_titulo = ttk.Label(tarjeta, text=(clip.get("titulo") or "").strip() or str(clip.get("razon") or "").strip()[:90] or "Clip sin título", font=("Segoe UI", 10, "bold"), justify="left", anchor="w")
            etiqueta_titulo.grid(row=0, column=1, sticky="w")
            estado_var = tk.StringVar(value=inicial)
            estado_label = ttk.Label(tarjeta, textvariable=estado_var)
            estado_label.grid(row=0, column=2, sticky="ne", padx=(8, 0))
            subtitulo = " · ".join(x for x in (tipo, nombre_stream) if x)
            etiqueta_sub = ttk.Label(tarjeta, text=subtitulo, justify="left", anchor="w")
            etiqueta_sub.grid(row=1, column=1, columnspan=2, sticky="w", pady=(1, 0))
            datos_iconos = (("⏱", detalles[1]), ("▣", detalles[2]), ("⚡", detalles[3]), ("✓", detalles[4]))
            if len(detalles) > 5: datos_iconos += (("🏆", detalles[5]),)
            fila_iconos = ttk.Frame(tarjeta); fila_iconos.grid(row=2, column=1, columnspan=2, sticky="w", pady=(3, 2))
            for columna, (icono, ayuda) in enumerate(datos_iconos):
                etiqueta = ttk.Label(fila_iconos, text=icono, cursor="question_arrow")
                etiqueta.grid(row=0, column=columna, padx=(0, 9)); _tooltip(etiqueta, ayuda)
            razon_clip = str(clip.get("razon") or "").strip()
            etiqueta_razon = ttk.Label(tarjeta, text=f"Por qué se eligió: {razon_clip}" if razon_clip else "", justify="left", anchor="w")
            etiqueta_razon.grid(row=3, column=1, columnspan=2, sticky="w", pady=(0, 3))
            duracion_real = _duracion_clip(clip)
            if maximo_cfg["valor"] and duracion_real > maximo_cfg["valor"] + 0.05:
                ttk.Label(tarjeta, text=f"⚠ Supera el máximo: {duracion_real:.0f}s > {maximo_cfg['valor']:g}s", style="error.TLabel").grid(row=6, column=1, columnspan=2, sticky="w", pady=(4, 0))
            # Los textos largos saltan de linea segun el ancho real de la tarjeta (nunca se cortan).
            texto_adaptable(tarjeta, etiqueta_titulo, lambda m=marco_miniatura, e=estado_label: m.winfo_reqwidth() + e.winfo_reqwidth() + 70)
            for ajustable in (etiqueta_sub, etiqueta_razon):
                texto_adaptable(tarjeta, ajustable, lambda m=marco_miniatura: m.winfo_reqwidth() + 50)
            datos_tarjeta = {"id": clip_id, "clip": clip, "frame": tarjeta, "validacion": validacion, "estado_inicial": inicial, "estado_var": estado_var, "miniatura": etiqueta_miniatura, "corriendo": False, "imagen_estatica": None, "fotogramas": []}
            tarjetas.append(datos_tarjeta)

            def cambiar_estado(nuevo, datos=datos_tarjeta):
                cambios[datos["id"]] = nuevo
                datos["estado_var"].set(nuevo)
                datos["actualizar_motivos"](nuevo)
                aplicar_filtros()

            fila_valoracion = ttk.Frame(tarjeta); fila_valoracion.grid(row=4, column=1, columnspan=2, sticky="w", pady=(2, 0))
            estrellas = ttk.Frame(fila_valoracion); estrellas.grid(row=0, column=0)
            botones_estrellas = []
            def pintar(valor, datos=datos_tarjeta, botones=botones_estrellas):
                for numero, boton in enumerate(botones, 1):
                    boton.configure(text="★" if numero <= valor else "☆")
            def restaurar_estrellas(_e=None, datos=datos_tarjeta, pintar_tarjeta=pintar):
                valor = cambios.get(datos["id"], datos["estado_inicial"])
                pintar_tarjeta(int(valor.rsplit("_", 1)[1]) if valor.startswith("VALORADO_") else 0)
            for numero in range(1, 6):
                boton = ttk.Button(estrellas, text="☆", width=3, command=lambda n=numero, cambiar=cambiar_estado, pintar_tarjeta=pintar: (cambiar(f"VALORADO_{n}"), pintar_tarjeta(n)))
                boton.grid(row=0, column=numero - 1)
                boton.bind("<Enter>", lambda _e, n=numero, pintar_tarjeta=pintar: pintar_tarjeta(n))
                boton.bind("<Leave>", restaurar_estrellas)
                botones_estrellas.append(boton)
            ttk.Button(estrellas, text="Descartar", command=lambda datos=datos_tarjeta, cambiar=cambiar_estado, pintar_tarjeta=pintar: (cambiar("SIN_VALORAR") if cambios.get(datos["id"], datos["estado_inicial"]) == "DESCARTADO" else cambiar("DESCARTADO"), pintar_tarjeta(0))).grid(row=0, column=5, padx=(10, 0))
            restaurar_estrellas()

            # Motivo de la valoracion: cambia segun valores alto (por que te gusto) o bajo/descartes
            # (por que no). Solo los motivos de gusto ensenan preferencias; mal corte o fallo tecnico no.
            fila_motivo = ttk.Frame(tarjeta); fila_motivo.columnconfigure(1, weight=1)
            etiqueta_motivo = ttk.Label(fila_motivo, text="")
            etiqueta_motivo.grid(row=0, column=0, padx=(0, 8))
            motivo_var = tk.StringVar()
            combo_motivo = ttk.Combobox(fila_motivo, textvariable=motivo_var, state="readonly", width=38)
            combo_motivo.grid(row=0, column=1, sticky="w")
            datos_tarjeta["motivo_var"] = motivo_var
            datos_tarjeta["tipo_motivo"] = None
            # Nota libre (opcional): lo que escribas aqui le llega a la IA junto al clip y alimenta los criterios.
            ttk.Label(fila_motivo, text="Tu nota:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(4, 0))
            nota_var = tk.StringVar()
            ttk.Entry(fila_motivo, textvariable=nota_var, width=44).grid(row=1, column=1, sticky="ew", pady=(4, 0))
            datos_tarjeta["nota_var"] = nota_var

            def actualizar_motivos(estado, datos=datos_tarjeta, fila_m=fila_motivo, etiq=etiqueta_motivo, combo=combo_motivo, var=motivo_var):
                tipo_nuevo = _tipo_de_motivo(estado)
                if tipo_nuevo is None:
                    fila_m.grid_remove(); datos["tipo_motivo"] = None; return
                if tipo_nuevo != datos["tipo_motivo"]:
                    # Cambio de lista (de gusto a rechazo o al reves): el motivo anterior ya no aplica.
                    if tipo_nuevo == "positivo":
                        etiq.configure(text="¿Por qué te gustó?")
                        combo.configure(values=[SIN_MOTIVO] + [e for e, _ in MOTIVOS_POSITIVOS_UI]); var.set(SIN_MOTIVO)
                    else:
                        etiq.configure(text="¿Por qué no?")
                        combo.configure(values=[e for e, _ in MOTIVOS_NEGATIVOS_UI]); var.set(MOTIVOS_NEGATIVOS_UI[0][0])
                    datos["tipo_motivo"] = tipo_nuevo
                fila_m.grid(row=5, column=1, columnspan=2, sticky="w", pady=(4, 0))
            datos_tarjeta["actualizar_motivos"] = actualizar_motivos
            actualizar_motivos(inicial)

            archivo = clip.get("ruta_archivo", clip.get("archivo", ""))
            try:
                sello_archivo = os.stat(archivo)
                version_media = f"{sello_archivo.st_size}_{sello_archivo.st_mtime_ns}"
            except OSError:
                version_media = "ausente"
            cache = os.path.join(str(directorio_scripts()), ".mkclips_cache", "revision", (fuente or {}).get("fingerprint", "sin_fuente"), f"{clip_id}_{version_media}_containfit_6fps_3s_v6")
            miniatura, preview = cache + ".png", cache + ".gif"
            def mostrar_miniatura(datos=datos_tarjeta, thumb=miniatura):
                if not datos["frame"].winfo_exists() or not os.path.isfile(thumb): return
                try:
                    datos["imagen_estatica"] = tk.PhotoImage(file=thumb)
                    datos["miniatura"].configure(image=datos["imagen_estatica"], text="▶")
                except tk.TclError: pass
            def solicitar_miniatura(datos=datos_tarjeta, ruta=archivo, thumb=miniatura, mostrar=mostrar_miniatura):
                if datos.get("imagen_estatica") is not None or datos.get("miniatura_pedida"): return
                datos["miniatura_pedida"] = True
                if os.path.isfile(thumb):
                    mostrar(); return
                def tarea_miniatura():
                    try:
                        _generar_miniatura_revision(ruta, thumb)
                    except Exception:
                        pass
                    miniaturas_listas.put(datos)
                drenaje["n"] += 1
                miniaturas_pool.submit(tarea_miniatura)
                _asegurar_drenaje()
            def cargar_preview(_e=None, datos=datos_tarjeta, ruta=archivo, thumb=miniatura, gif=preview, solicitar=solicitar_miniatura, mostrar_thumb=mostrar_miniatura):
                detener_preview()
                preview_activo["id"] = datos; datos["corriendo"] = True
                solicitar()
                bloqueo_adquirido = not os.path.isfile(gif)
                if bloqueo_adquirido and not preview_en_proceso.acquire(blocking=False): return
                def tarea():
                    try:
                        _generar_preview_revision(ruta, gif)
                        def instalar_fotogramas(frames):
                            if not datos["corriendo"] or preview_activo.get("id") is not datos:
                                return
                            mostrar_thumb()
                            datos["fotogramas"] = []
                            if ImageTk is not None:
                                try:
                                    datos["fotogramas"] = [ImageTk.PhotoImage(frame) for frame in frames]
                                except Exception:
                                    datos["fotogramas"] = []
                            if not datos["fotogramas"]:
                                # Fallback: una sola imagen GIF evita bloquear con 24 decodificaciones Tk.
                                try:
                                    datos["fotogramas"] = [tk.PhotoImage(file=gif)]
                                except tk.TclError:
                                    datos["corriendo"] = False
                                    return
                            def animar(indice=0):
                                if not datos["corriendo"] or preview_activo.get("id") is not datos: return
                                try:
                                    datos["miniatura"].configure(image=datos["fotogramas"][indice], text="")
                                except tk.TclError:
                                    return
                                marco.after(160, lambda: animar((indice + 1) % len(datos["fotogramas"])))
                            animar()

                        def decodificar_frames():
                            if Image is None or ImageSequence is None:
                                return None
                            try:
                                imagen = Image.open(gif)
                                frames = []
                                for indice, frame in enumerate(ImageSequence.Iterator(imagen)):
                                    if indice >= 12:
                                        break
                                    frames.append(frame.convert("RGBA").copy())
                                imagen.close()
                                return frames
                            except Exception:
                                return None

                        frames = decodificar_frames()
                        marco.after(0, instalar_fotogramas, frames)
                    except Exception as exc:
                        marco.after(0, lambda mensaje=str(exc), d=datos: d["miniatura"].configure(text=f"Preview no disponible\n{mensaje[:55]}") if d["miniatura"].winfo_exists() else None)
                    finally:
                        if bloqueo_adquirido: preview_en_proceso.release()
                threading.Thread(target=tarea, daemon=True).start()
            datos_tarjeta["hover_job"] = None
            # Botón de previsualización integrada (reproduce video en ventana interna o externa)
            def programar_preview(_e=None, datos=datos_tarjeta):
                job = datos.get("hover_job")
                if job:
                    try: marco.after_cancel(job)
                    except tk.TclError: pass
                datos["hover_job"] = marco.after(140, cargar_preview)
            def cancelar_preview(_e=None, datos=datos_tarjeta):
                job = datos.get("hover_job")
                if job:
                    try: marco.after_cancel(job)
                    except tk.TclError: pass
                    datos["hover_job"] = None
                detener_preview()
            for widget_hover in (marco_miniatura, etiqueta_miniatura, icono_play):
                widget_hover.bind("<Enter>", programar_preview)
                widget_hover.bind("<Leave>", cancelar_preview)
                widget_hover.bind("<Button-1>", lambda _e, c=clip: _abrir_clip(c))
            datos_tarjeta["solicitar_miniatura"] = solicitar_miniatura
            datos_tarjeta["mostrar_miniatura"] = mostrar_miniatura
        aplicar_filtros()
        marco.after_idle(_pedir_miniaturas)

    def _drenar_miniaturas():
        drenaje["job"] = None
        try:
            for _ in range(8):  # pocas por ciclo para no congelar la interfaz
                datos = miniaturas_listas.get_nowait()
                drenaje["n"] = max(0, drenaje["n"] - 1)
                datos["mostrar_miniatura"]()
        except queue.Empty:
            pass
        except tk.TclError:
            return
        if drenaje["n"] > 0 or not miniaturas_listas.empty():
            _asegurar_drenaje()

    def _asegurar_drenaje():
        if drenaje["job"] is None:
            try: drenaje["job"] = marco.after(30, _drenar_miniaturas)
            except tk.TclError: pass

    def _pedir_miniaturas():
        """Pide todas las miniaturas de golpe: primero las visibles y luego el
        resto en segundo plano, de modo que ya estén listas al desplazarse."""
        try:
            if not marco.winfo_exists(): return
            contenido.update_idletasks()
            superior = lienzo.winfo_rooty(); inferior = superior + max(lienzo.winfo_height(), 1)
            visibles, resto = [], []
            for datos in tarjetas:
                if datos.get("imagen_estatica") is not None or datos.get("miniatura_pedida"): continue
                w = datos["frame"]
                if not w.winfo_manager(): continue  # filtrada: no se genera hasta que se muestre
                en_pantalla = w.winfo_ismapped() and w.winfo_rooty() < inferior and w.winfo_rooty() + w.winfo_height() > superior
                (visibles if en_pantalla else resto).append(datos)
            for datos in visibles + resto:
                datos["solicitar_miniatura"]()
        except tk.TclError:
            pass

    def _ruta_clip(clip):
        return clip.get("ruta_archivo") or clip.get("archivo") or ""

    def _mostrar_vacio(texto):
        detener_preview()
        for hijo in contenido.winfo_children():
            if hijo is not vacio: hijo.destroy()
        tarjetas.clear(); clips_cargados.clear()
        vacio.configure(text=texto); vacio.grid(row=0, column=0, pady=40)
        estado.set(texto)
        boton_recorte.configure(state="disabled", text="Recortar al máximo")

    def _clips_del_ultimo_stream(base):
        """clips_sugeridos.json del último stream procesado (anterior al catálogo)."""
        ruta_clips = os.path.join(base, "clips_sugeridos.json")
        try:
            with open(ruta_clips, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
        except (OSError, ValueError):
            return [], None
        if not isinstance(datos, list): return [], None
        video = _video_actual()
        fuente = None
        if video:
            try: fuente = exigir_identidad_artefacto(ruta_clips, video, "clips_sugeridos")
            except Exception:
                try: fuente = identidad_fuente(video)
                except Exception: fuente = None
        return [c for c in datos if isinstance(c, dict)], fuente

    def _validaciones_tecnicas(base):
        validaciones = {}
        try:
            with open(os.path.join(base, "validacion_segmentos.json"), "r", encoding="utf-8") as archivo:
                for item in json.load(archivo).get("resultados", []):
                    if isinstance(item, dict) and item.get("archivo"): validaciones[item["archivo"]] = item
        except (OSError, ValueError, AttributeError): pass
        return validaciones

    def _feedback_de(clip, fuente, preferencias):
        entrada = feedback_por_clip(clip, fuente, preferencias)
        if entrada is None and clip.get("clip_id_legado"):
            # Clip de un stream anterior al catalogo: se enlaza con su valoracion previa.
            entrada = next((f for f in reversed(preferencias.get("feedback", [])) if f.get("clip_id") == clip["clip_id_legado"]), None)
        return entrada

    def _purgar_descartados_pendientes(entradas):
        """Reintenta borrar los clips ya descartados cuyo archivo siguio en disco
        (en Windows no se puede borrar un video mientras el reproductor lo tiene
        abierto). Devuelve las entradas que siguen existiendo."""
        preferencias = cargar_preferencias()
        base_clips = leer_configuracion().get("CARPETA_CLIPS_BASE") or ""
        restantes, borrados = [], []
        for entrada in entradas:
            if _estado_feedback(_feedback_de(entrada["clip"], entrada.get("fuente"), preferencias)) == "DESCARTADO":
                ok, _motivo = catalogo_clips.borrar_clip(entrada["ruta_archivo"])
                if ok:
                    borrados.append(entrada["ruta_archivo"])
                    catalogo_clips.limpiar_carpeta_vacia(entrada["ruta_archivo"], base_clips)
                    continue
            restantes.append(entrada)
        if borrados:
            catalogo_clips.quitar_clips(_ruta_resultados_actual(), borrados)
            catalogo_clips.quitar_del_historial(borrados, RUTA_HISTORIAL_CLIPS)
        return restantes

    def _firma_actual(entradas):
        return (len(cargar_preferencias().get("feedback", [])),
                tuple(sorted((e["ruta_archivo"], os.path.getsize(e["ruta_archivo"]) if os.path.isfile(e["ruta_archivo"]) else -1) for e in entradas)))
    firma_cargada = {"valor": None}

    def _cargar_original(silencioso=False):
        """Carga los clips de TODOS los streams cuyo archivo existe en disco.

        Con ``silencioso=True`` (carga automática al abrir la pestaña) los
        problemas se muestran en la propia pestaña en vez de en ventanas."""
        nonlocal clips_cargados
        config = leer_configuracion()
        base = _ruta_resultados_actual()
        try:
            maximo_cfg["valor"] = float(config.get("DURACION_MAX_CLIP") or 0)
        except (TypeError, ValueError):
            maximo_cfg["valor"] = 0.0
        ultimos, fuente_ultimo = _clips_del_ultimo_stream(base)
        try:
            entradas = catalogo_clips.sincronizar(
                base, config.get("CARPETA_CLIPS_BASE") or "", clips_actuales=ultimos,
                fuente_actual=fuente_ultimo, feedback=cargar_preferencias().get("feedback", []),
                contexto_actual=catalogo_clips.leer_contexto_juego(base),
            )
        except OSError as exc:
            if not silencioso: messagebox.showerror("Validar clips", str(exc))
            return _mostrar_vacio(f"No se pudieron leer los clips: {exc}")
        entradas = _purgar_descartados_pendientes(entradas)
        if not entradas:
            return _mostrar_vacio("No hay clips: no se encontró ningún video en la carpeta de clips.")
        firma_cargada["valor"] = _firma_actual(entradas)
        validaciones = _validaciones_tecnicas(base)
        clips_cargados = []
        for entrada in entradas:
            copia = dict(entrada["clip"])
            copia["_fuente"] = entrada.get("fuente")
            copia["_stream"] = entrada.get("stream") or ""
            copia["_contexto_juego"] = entrada.get("contexto_juego")
            validacion = validaciones.get(_ruta_clip(copia))
            copia["_validacion"] = validacion if validacion and validacion.get("segmentos") == copia.get("segmentos") else None
            clips_cargados.append(copia)
        # Los mejores primero: si validas solo unos cuantos, que sean los que mas importan.
        clips_cargados.sort(key=lambda c: (-float(c.get("score_bruto", c.get("score", 0)) or 0), c["_stream"], os.path.basename(_ruta_clip(c))))
        vacio.grid_remove(); cambios.clear(); construir_tarjetas(); aplicar_filtros()
        pendientes = sum(1 for t in tarjetas if t["estado_inicial"] == "SIN_VALORAR")
        streams = len({c["_stream"] for c in clips_cargados})
        largos = [c for c in clips_cargados if maximo_cfg["valor"] and _duracion_clip(c) > maximo_cfg["valor"] + 0.05]
        acierto = indicador_acierto()
        texto_acierto = f" Acierto del sistema: {acierto['auc'] * 100:.0f}% (50% = azar)." if acierto["auc"] is not None else ""
        estado.set(f"{pendientes} clip(s) pendientes de validar · {len(clips_cargados)} en total · {streams} stream(s)." + texto_acierto
                   + (f" {len(largos)} superan el máximo de {maximo_cfg['valor']:g}s." if largos else ""))
        boton_recorte.configure(state="normal" if largos else "disabled", text=f"Recortar al máximo ({len(largos)})" if largos else "Recortar al máximo")

    def _al_mostrar(evento):
        # Al abrir la pestaña se refleja lo que hay en disco, salvo que haya valoraciones sin guardar.
        if evento.widget is not marco or cambios: return
        try:
            if firma_cargada["valor"] is not None and _firma_actual(clips_en_catalogo()) == firma_cargada["valor"]: return
        except OSError: pass
        _cargar_original(silencioso=True)

    def clips_en_catalogo():
        return [e for e in catalogo_clips.cargar_catalogo(_ruta_resultados_actual()) if os.path.isfile(e["ruta_archivo"])]
    marco.bind("<Map>", _al_mostrar, add="+")

    def recortar_largos():
        largos = [c for c in clips_cargados if maximo_cfg["valor"] and _duracion_clip(c) > maximo_cfg["valor"] + 0.05]
        if not largos: return
        if not messagebox.askyesno("Recortar al máximo", f"Se recortará el final de {len(largos)} clip(s) para que no pasen de {maximo_cfg['valor']:g} s. El resto del clip no se modifica. ¿Continuar?"):
            return
        boton_recorte.configure(state="disabled", text="Recortando...")
        resultado = {}
        def trabajo():
            hechos, fallos = 0, []
            for clip in largos:
                ok, _real = catalogo_clips.recortar_a_maximo(_ruta_clip(clip), maximo_cfg["valor"])
                if ok: hechos += 1
                else: fallos.append(os.path.basename(_ruta_clip(clip)))
            resultado.update(hechos=hechos, fallos=fallos)
        def terminar():
            if not resultado: return marco.after(250, terminar)
            # Los clips recortados cambian de tamaño: se vuelve a leer su duración real.
            rutas = {os.path.normcase(os.path.abspath(_ruta_clip(c))) for c in largos}
            entradas = catalogo_clips.cargar_catalogo(_ruta_resultados_actual())
            for e in entradas:
                if os.path.normcase(os.path.abspath(e["ruta_archivo"])) in rutas:
                    real = round(catalogo_clips.duracion_archivo(e["ruta_archivo"]), 3)
                    e["clip"]["duracion"] = e["clip"]["duracion_final"] = real
            catalogo_clips.guardar_catalogo(_ruta_resultados_actual(), entradas)
            cargar_en_curso = list(cambios.items())
            _cargar_original(silencioso=True)
            cambios.update(cargar_en_curso)
            aplicar_filtros()
            if resultado["fallos"]:
                messagebox.showwarning("Recortar al máximo", f"{resultado['hechos']} recortado(s). No se pudo recortar: " + ", ".join(resultado["fallos"][:5]) + "\n\nSi alguno está abierto en el reproductor, ciérralo y vuelve a intentarlo.")
            else:
                messagebox.showinfo("Recortar al máximo", f"{resultado['hechos']} clip(s) recortado(s) al máximo configurado.")
        threading.Thread(target=trabajo, daemon=True).start()
        marco.after(250, terminar)

    cargar = lambda: _cargar_original()
    def guardar():
        if not cambios: return messagebox.showinfo("Validar clips", "No hay valoraciones modificadas para guardar.")
        por_id = {t["id"]: t["clip"] for t in tarjetas}
        descartados = [por_id[i] for i, v in cambios.items() if v == "DESCARTADO" and i in por_id]
        # Codigo del motivo segun el estado FINAL de cada clip (si cambiaste de 5 a 2 estrellas, vale la lista de rechazo).
        motivo_de = {t["id"]: _codigo_motivo(cambios.get(t["id"], t["estado_inicial"]), t["motivo_var"].get()) for t in tarjetas}
        nota_de = {t["id"]: (t["nota_var"].get().strip()[:300] if _tipo_de_motivo(cambios.get(t["id"], t["estado_inicial"])) else "") for t in tarjetas}
        if descartados and not messagebox.askyesno(
                "Guardar valoraciones",
                f"{len(descartados)} clip(s) descartado(s) se ELIMINARÁN de la carpeta de clips y no se pueden recuperar. ¿Continuar?"):
            return
        try:
            for clip_id, valor in cambios.items():
                clip = por_id.get(clip_id)
                if not clip: raise RuntimeError("Un clip modificado ya no pertenece a los resultados cargados.")
                fuente = clip.get("_fuente")
                if valor == "SIN_VALORAR":
                    guardar_feedback(clip, fuente=fuente, contexto_juego=clip.get("_contexto_juego"))
                    continue
                descartado = valor == "DESCARTADO"; rating = None if descartado else int(valor.rsplit("_", 1)[1])
                guardar_feedback(clip, rating=rating, fuente=fuente, discarded=descartado,
                                 motivo=motivo_de.get(clip_id, ""), comentario=nota_de.get(clip_id, ""),
                                 contexto_juego=clip.get("_contexto_juego"))
            cantidad = len(cambios)
            eliminados, fallos = [], []
            if descartados:
                base_clips = leer_configuracion().get("CARPETA_CLIPS_BASE") or ""
                for clip in descartados:
                    ruta = _ruta_clip(clip)
                    ok, motivo = catalogo_clips.borrar_clip(ruta)
                    if ok:
                        eliminados.append(ruta); catalogo_clips.limpiar_carpeta_vacia(ruta, base_clips)
                    else:
                        fallos.append(f"{os.path.basename(ruta)}: {motivo}")
                catalogo_clips.quitar_clips(_ruta_resultados_actual(), eliminados)
                catalogo_clips.quitar_del_historial(eliminados, RUTA_HISTORIAL_CLIPS)
            cambios.clear(); _cargar_original(silencioso=True)
            texto = f"{cantidad} valoración(es) guardada(s)."
            if eliminados: texto += f" {len(eliminados)} clip(s) descartado(s) eliminado(s) de la carpeta."
            estado.set(texto + " " + estado.get())
            if fallos:
                messagebox.showwarning("Validar clips", "Valoraciones guardadas, pero no se pudo eliminar:\n" + "\n".join(fallos[:6]))
            else:
                messagebox.showinfo("Validar clips", "Valoraciones guardadas." + (f"\n{len(eliminados)} clip(s) eliminado(s)." if eliminados else ""))
        except Exception as exc:
            messagebox.showerror("Validar clips", str(exc))

    # Los botones van en su propia fila: en una sola se salian de la ventana y se cortaban.
    botones = ttk.Frame(controles); botones.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
    ttk.Button(botones, text="Recargar", command=cargar).pack(side="left", padx=(0, 6))
    ttk.Button(botones, text="Guardar valoraciones", command=guardar).pack(side="left", padx=(0, 6))
    boton_recorte = ttk.Button(botones, text="Recortar al máximo", command=recortar_largos, state="disabled")
    boton_recorte.pack(side="left")
    ttk.Label(marco, textvariable=estado).grid(row=4, column=0, sticky="w", pady=(6, 0))
    filtro_estado.trace_add("write", aplicar_filtros); filtro_tipo.trace_add("write", aplicar_filtros)
    return marco


def _lanzar_interfaz_web(ruta_inicial="/app"):
    """Abre MKClips en una ventana de escritorio integrada (WebView2)."""
    if not ruta_inicial.startswith(("/app", "/editor/")):
        ruta_inicial = "/app"
    url = "http://127.0.0.1:5678" + ruta_inicial
    if ruta_inicial.startswith("/app"):
        url += ("&" if "?" in ruta_inicial else "?") + "launch=" + secrets.token_urlsafe(16)
    try:
        try:
            from . import editor_lanzador
        except ImportError:
            import editor_lanzador
        ok, mensaje = editor_lanzador.iniciar_panel()
        if not ok:
            raise RuntimeError(mensaje)
        try:
            import urllib.request
            with urllib.request.urlopen("http://127.0.0.1:5678/app", timeout=3):
                pass
        except Exception:
            # Un panel antiguo puede ocupar el puerto sin servir esta interfaz.
            ok, mensaje = editor_lanzador.detener_panel()
            if not ok:
                raise RuntimeError(mensaje)
            ok, mensaje = editor_lanzador.iniciar_panel()
            if not ok:
                raise RuntimeError(mensaje)

        import webview
        if not ruta_inicial.startswith(("/app", "/editor/")):
            ruta_inicial = "/app"
        url = "http://127.0.0.1:5678" + ruta_inicial
        if ruta_inicial.startswith("/app"):
            url += ("&" if "?" in ruta_inicial else "?") + "launch=" + secrets.token_urlsafe(16)
        ffmpeg_name = "ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg"
        if getattr(sys, "frozen", False) and not (Path(sys.executable).resolve().parent / "bin" / ffmpeg_name).is_file() and not shutil.which("ffmpeg"):
            messagebox.showwarning("Falta FFmpeg", "MKClips puede abrirse, pero el procesamiento necesita FFmpeg. Instálalo desde https://ffmpeg.org/download.html y añádelo al PATH.")
        webview.create_window(
            f"MKClips {VERSION_APP}" if getattr(sys, "frozen", False) else "MKClips", url, width=1360, height=860,
            min_size=(1024, 650), text_select=True,
            background_color="#0b0e0f",
        )
        if sys.platform.startswith("win"):
            datos = datos_dir() / "WebView2"
            datos.mkdir(parents=True, exist_ok=True)
            webview.start(gui="edgechromium", private_mode=False, storage_path=str(datos))
        elif sys.platform == "darwin":
            webview.start(private_mode=False)
        else:
            webview.start(gui="gtk", private_mode=False)
    except ImportError:
        _abrir_edge_app(url)
    except Exception:
        _abrir_edge_app(url)


def _abrir_edge_app(url):
    """Fallback to the system browser outside Windows; use Edge app mode on Windows."""
    if not sys.platform.startswith("win"):
        import webbrowser
        if webbrowser.open(url, new=1):
            return
        raise RuntimeError("No se pudo abrir MKClips en el navegador del sistema.")
    import tkinter as tk
    from tkinter import messagebox
    try:
        from . import edge_app
    except ImportError:
        import edge_app
    ok, error = edge_app.abrir_en_edge(url)
    if not ok:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Falta Microsoft Edge", error + "\n\nTambién puedes instalar Microsoft Edge WebView2 Runtime:\nhttps://developer.microsoft.com/microsoft-edge-webview2/")


if __name__ == "__main__":
    if "--tip-page" in sys.argv[1:]:
        try:
            from . import apoyo_config, edge_app
        except ImportError:
            import apoyo_config, edge_app
        ok, error = edge_app.abrir_en_navegador_predeterminado(apoyo_config.ENLACE_DONACION)
        print("Tip Page abierta en el navegador predeterminado." if ok else f"No se pudo abrir la Tip Page: {error}")
        raise SystemExit(0 if ok else 1)
    elif "--server" in sys.argv[1:]:
        import panel_grabacion
        panel_grabacion.app.run(host="127.0.0.1", port=5678, debug=False, threaded=True)
    elif "--clasico" in sys.argv:
        crear_ventana().mainloop()
    else:
        ruta = "/app"
        if "--url" in sys.argv:
            try:
                ruta = sys.argv[sys.argv.index("--url") + 1]
            except IndexError:
                pass
        _lanzar_interfaz_web(ruta)
