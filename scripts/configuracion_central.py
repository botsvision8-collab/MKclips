"""Resolución y edición persistente de la configuración de MKClips.

Este módulo no importa ``config.py``: permite que la aplicación de
configuración funcione tanto con Python como empaquetada por PyInstaller sin
escribir nunca dentro de ``_MEIPASS``.
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

try:
    from .duracion_clips import validar_limites_duracion
except ImportError:  # importado como modulo suelto desde scripts/
    from duracion_clips import validar_limites_duracion


DEFAULTS = {
    "CARPETA_STREAMS": "",
    "CARPETA_CLIPS_BASE": "",
    # Reservada para una futura integración; hoy no tiene consumidor.
    "CARPETA_RESULTADOS": "",
    # Donde se guardan los clips editados con el editor (una subcarpeta por stream). Vacio = junto a cada clip, en «editados».
    "CARPETA_EDITADOS": "",
    "MOSTRAR_CONTEXTO_POST_STREAM": True,
    "MOSTRAR_AVISO_APOYO": True,
    # Defaults de la acción de grabación en Workflow; mantienen el flujo anterior.
    "OBS_MODO_GRABACION_DEFAULT": "horizontal",
    "OBS_PROCESAR_AL_TERMINAR": True,
    # Misma preferencia histórica, expresada como la casilla del panel de OBS.
    "OBS_SOLO_GRABAR_DEFAULT": False,
    "OBS_BORRAR_ORIGINAL_AL_TERMINAR": False,
    "OBS_WS_HOST": "localhost",
    "OBS_WS_PUERTO": 4455,
    "OBS_WS_CONTRASENA": "",
    "DURACION_MIN_CLIP": 0,
    "DURACION_MAX_CLIP": 0,
    "NUM_PROCESOS_TRANSCRIPCION": 1,
    "USAR_GPU_TRANSCRIPCION": True,
    # La API key no se guarda aqui: la variable canonica es OLLAMA_API_KEY.
    "OLLAMA_MODO": "cloud",
    "OLLAMA_HOST": "http://localhost:11434",
    "OLLAMA_MODELO": "gpt-oss:120b-cloud",
    # IA que elige los clips (ver llm_cliente.py). Proveedores: ollama_cloud,
    # ollama_local, openai (cualquier API compatible con OpenAI) y anthropic.
    # La API key solo se lee de la variable de entorno LLM_API_KEY_ENV.
    "LLM_PROVEEDOR": "ollama_cloud",
    "LLM_BASE_URL": "",
    "LLM_MODELO": "",
    "LLM_API_KEY_ENV": "OLLAMA_API_KEY",
    "LLM_MAX_TOKENS": 8192,
    "LLM_TIMEOUT": 300,
    # Peticiones simultaneas a la IA (bloques y refinado de clips). 1 = en serie.
    "LLM_CONCURRENCIA": 3,
    # Objetivo del proyecto y gustos del creador, en lenguaje natural. Se envia siempre a la IA.
    "CONTEXTO_PROYECTO": "",
    # Motor de transcripcion: "whisper_local" (gratis, usa tu equipo) o "assemblyai" (nube).
    # AssemblyAI es un servicio externo con su propia cuenta; si falla se usa Whisper local.
    # La API key solo se lee de la variable de entorno ASSEMBLYAI_API_KEY_ENV.
    "TRANSCRIPCION_MOTOR": "whisper_local",
    "ASSEMBLYAI_API_KEY_ENV": "ASSEMBLYAI_API_KEY",
            "ASSEMBLYAI_TERMINOS": [],         # palabras genéricas a reforzar (máximo 6 palabras cada una)
    "ASSEMBLYAI_MODELOS": [],          # vacio = el modelo por defecto del servicio
    "ASSEMBLYAI_PAUSA_SEG": 1.0,       # una pausa de esta duracion corta el segmento
    "ASSEMBLYAI_MAX_SEGMENTO_SEG": 25.0,  # duracion maxima de un segmento
    "ASSEMBLYAI_ESPERA_MAX_MIN": 180,  # minutos maximos esperando el resultado antes de usar Whisper local
    # ------------------------------------------------------------------
    # Seleccion por capas (seleccion_capas.py). Enriquece el flujo actual de
    # identificar_clips.py; NO lo reemplaza. Con el flag en False todo se comporta
    # exactamente como antes.
    # ------------------------------------------------------------------
    "USAR_SELECCION_POR_CAPAS": False,
    # --- Capa 1: pistas deterministas (sin IA) que se inyectan en el prompt de cada bloque ---
    # Puntaje que suma una linea del transcript por cada senal. Son PISTAS, no la decision.
    "CAPA1_MAX_PISTAS": 12,            # lineas mejor puntuadas que se envian por bloque
    "CAPA1_PUNTAJE_MINIMO": 1.0,       # una linea con menos puntaje no se envia aunque sobren plazas
    "CAPA1_MAX_CHARS_LINEA": 220,      # recorte del texto de cada pista en el prompt
    "PESO_FRASE_GATILLO": 2.0,         # contiene alguna frase de FRASES_GATILLO
    "PESO_PREGUNTA": 1.5,              # contiene "?"
    "PESO_ENFASIS": 1.0,               # contiene "!"
    "PESO_GIRO_HISTORIA": 1.0,         # contiene alguna frase de FRASES_GIRO
    "PESO_LINEA_CORTA": 0.5,           # linea con UMBRAL_LINEA_CORTA_PALABRAS palabras o menos
    "PESO_PAUSA_PREVIA": 1.0,          # silencio >= UMBRAL_PAUSA_SEG antes de la linea
    "PESO_PICO_AUDIO": 1.25,           # coincide con un pico de audio de eventos_audio.json
    # Inactivo: transcripcion.json no trae hablantes y no hay diarizacion. Solo suma si una
    # linea trae la clave "hablante" Y este peso es > 0 (valor sugerido si algun dia hay datos: 1.25).
    "PESO_CAMBIO_HABLANTE": 0.0,
    "UMBRAL_LINEA_CORTA_PALABRAS": 8,
    "UMBRAL_PAUSA_SEG": 1.0,
    "MARGEN_PICO_AUDIO_SEG": 1.0,      # tolerancia (s) para considerar que un pico coincide con la linea
    # Sintaxis: minusculas, se compara por palabra/frase completa y respetando acentos
    # ("qué" no coincide con "que"). Un * final significa "empieza por" ("jaja*" -> jajaja).
    "FRASES_GATILLO": [
        "espera", "no puede ser", "qué", "no manches", "no mames", "increíble", "loco", "error",
        "secreto", "nunca", "siempre", "nadie", "por qué", "cómo", "jaja*", "lol", "wow", "mira",
        "qué onda", "cabrón", "cabron", "vale verga", "wey", "güey", "no lo puedo creer",
        "dios mío", "madre mía", "qué fue eso", "no inventes", "ayuda", "auxilio", "cuidado",
        "ahí viene", "ya valió", "la cagué", "me mataron", "me morí", "ganamos", "perdimos",
        "clutch", "gg", "bug", "lag", "imposible", "épico", "qué locura", "increible",
    ],
    "FRASES_GIRO": ["pensé que", "pense que", "me di cuenta", "perdí", "perdi", "gané", "gane", "descubrí", "descubri"],
    # --- Capa 2: prompt (se usa desde la etapa 2) ---
    # Duracion IDEAL que se le sugiere a la IA. Los limites duros siguen siendo
    # DURACION_MIN_CLIP / DURACION_MAX_CLIP; esto solo orienta al modelo.
    "CAPA2_DURACION_IDEAL_MIN": 25,
    "CAPA2_DURACION_IDEAL_MAX": 50,
    # --- Capa 3: viralidad. Es una AUTOEVALUACION del LLM, no una prediccion calibrada ---
    "VIRALIDAD_PUNTAJE_MAX": 25,       # tope de cada subpuntaje (4 subpuntajes -> total 0-100)
    # Mezcla del total de viralidad en el score final: score*(1-peso) + total*peso. 0 = sin efecto
    # (ranking y aprendizaje actuales intactos). Rango valido 0..1.
    "PESO_VIRALIDAD_EN_SCORE": 0.0,
    "TIPOS_GANCHO": ["pregunta", "afirmación", "estadística", "historia", "contraste", "ninguno"],
    "GANCHO_MIN_PALABRAS": 3,
    "GANCHO_MAX_PALABRAS": 9,
    # --- Capa 4: pasos de validacion que NO existian (anclaje a lineas reales y viralidad) ---
    "CAPA4_ANCLA_TOLERANCIA_SEG": 3.0,     # un limite a menos de esto de una linea real se ajusta a ella
    "CAPA4_DESCARTAR_NO_ALINEADOS": False,  # True: descarta clips cuyos limites no estan cerca de ninguna linea real
    "TEMA_APP": "oscuro",
}


def limite_cpu_recomendado() -> int:
    """75% de los procesadores logicos, entre 1 y el total real."""
    total = os.cpu_count() or 1
    return max(1, min(total, int(total * 0.75)))


def normalizar_configuracion(valores: dict) -> dict:
    """Valida valores editables sin leer ni persistir secretos."""
    valores = dict(valores)
    modo_grabacion = str(valores.get("OBS_MODO_GRABACION_DEFAULT", "horizontal")).strip().lower()
    if modo_grabacion not in {"horizontal", "vertical", "ambos"}:
        raise ValueError("El modo de grabación debe ser Horizontal, Vertical o Ambos.")
    valores["OBS_MODO_GRABACION_DEFAULT"] = modo_grabacion
    for clave, default in (("MOSTRAR_CONTEXTO_POST_STREAM", True), ("MOSTRAR_AVISO_APOYO", True), ("OBS_PROCESAR_AL_TERMINAR", True), ("OBS_BORRAR_ORIGINAL_AL_TERMINAR", False)):
        valor = valores.get(clave, default)
        if isinstance(valor, str):
            limpio = valor.strip().lower()
            if limpio in {"true", "1", "si", "sí", "on"}: valor = True
            elif limpio in {"false", "0", "no", "off", ""}: valor = False
            else: raise ValueError(f"El ajuste {clave} debe ser verdadero o falso.")
        valores[clave] = bool(valor)
    solo_grabar = valores.get("OBS_SOLO_GRABAR_DEFAULT", not valores["OBS_PROCESAR_AL_TERMINAR"])
    if isinstance(solo_grabar, str):
        limpio = solo_grabar.strip().lower()
        if limpio in {"true", "1", "si", "sí", "on"}: solo_grabar = True
        elif limpio in {"false", "0", "no", "off", ""}: solo_grabar = False
        else: raise ValueError("El ajuste OBS_SOLO_GRABAR_DEFAULT debe ser verdadero o falso.")
    valores["OBS_SOLO_GRABAR_DEFAULT"] = bool(solo_grabar)
    valores["OBS_PROCESAR_AL_TERMINAR"] = not valores["OBS_SOLO_GRABAR_DEFAULT"]
    minimo, maximo = validar_limites_duracion(
        valores.get("DURACION_MIN_CLIP", 0), valores.get("DURACION_MAX_CLIP", 0)
    )
    valores["DURACION_MIN_CLIP"] = int(minimo) if minimo.is_integer() else minimo
    valores["DURACION_MAX_CLIP"] = int(maximo) if maximo.is_integer() else maximo
    try:
        puerto = int(valores.get("OBS_WS_PUERTO", 4455))
    except (TypeError, ValueError) as exc:
        raise ValueError("El puerto de OBS debe ser un numero entre 1 y 65535.") from exc
    if not 1 <= puerto <= 65535:
        raise ValueError("El puerto de OBS debe ser un numero entre 1 y 65535.")
    valores["OBS_WS_PUERTO"] = puerto
    for clave in ("CARPETA_STREAMS", "CARPETA_CLIPS_BASE", "CARPETA_RESULTADOS", "CARPETA_EDITADOS"):
        ruta = str(valores.get(clave) or "").strip()
        if ruta:
            valores[clave] = os.path.expanduser(os.path.expandvars(ruta))
    try:
        hilos = int(valores.get("NUM_PROCESOS_TRANSCRIPCION", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("Los hilos de CPU deben ser un numero entero.") from exc
    valores["NUM_PROCESOS_TRANSCRIPCION"] = max(1, min(hilos, limite_cpu_recomendado()))
    valores["USAR_GPU_TRANSCRIPCION"] = bool(valores.get("USAR_GPU_TRANSCRIPCION", True))
    modo = str(valores.get("OLLAMA_MODO", "cloud")).lower()
    if modo not in {"cloud", "local"}:
        raise ValueError("El modo de Ollama debe ser cloud o local.")
    valores["OLLAMA_MODO"] = modo
    host = str(valores.get("OLLAMA_HOST", "http://localhost:11434")).strip()
    if not host.startswith(("http://", "https://")):
        raise ValueError("El host de Ollama debe comenzar con http:// o https://.")
    valores["OLLAMA_HOST"] = host.rstrip("/")
    valores["OLLAMA_MODELO"] = str(valores.get("OLLAMA_MODELO", "")).strip()
    proveedor = str(valores.get("LLM_PROVEEDOR") or "").strip().lower()
    if proveedor not in {"ollama_cloud", "ollama_local", "openai", "anthropic"}:
        proveedor = "ollama_local" if modo == "local" else "ollama_cloud"
    valores["LLM_PROVEEDOR"] = proveedor
    base = str(valores.get("LLM_BASE_URL") or "").strip()
    if base and not base.startswith(("http://", "https://")):
        raise ValueError("La URL base de la IA debe comenzar con http:// o https://.")
    valores["LLM_BASE_URL"] = base.rstrip("/")
    valores["LLM_MODELO"] = str(valores.get("LLM_MODELO") or "").strip()
    if not valores["LLM_MODELO"] and not valores["OLLAMA_MODELO"]:
        raise ValueError("Debes indicar el modelo de IA.")
    if proveedor == "openai" and not valores["LLM_BASE_URL"]:
        raise ValueError("Indica la URL base de la API (por ejemplo https://api.openai.com/v1).")
    if proveedor in {"openai", "anthropic"} and not valores["LLM_MODELO"]:
        raise ValueError("Indica el nombre del modelo de tu proveedor de IA.")
    nombre_clave = str(valores.get("LLM_API_KEY_ENV") or "").strip()
    if nombre_clave and not nombre_clave.replace("_", "").isalnum():
        raise ValueError("El nombre de la variable de la API key solo puede tener letras, numeros y _.")
    valores["LLM_API_KEY_ENV"] = nombre_clave or ("OLLAMA_API_KEY" if proveedor.startswith("ollama") else "LLM_API_KEY")
    for clave, minimo, por_defecto in (("LLM_MAX_TOKENS", 256, 8192), ("LLM_TIMEOUT", 10, 300), ("LLM_CONCURRENCIA", 1, 3)):
        try:
            valores[clave] = max(minimo, int(valores.get(clave) or por_defecto))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{clave} debe ser un numero entero.") from exc
    valores["LLM_CONCURRENCIA"] = min(8, valores["LLM_CONCURRENCIA"])
    valores["CARPETA_EDITADOS"] = str(valores.get("CARPETA_EDITADOS") or "").strip()
    valores["CONTEXTO_PROYECTO"] = str(valores.get("CONTEXTO_PROYECTO") or "").strip()[:2000]
    # Mantiene coherente la configuracion antigua de Ollama (la usa el panel de OBS).
    if proveedor.startswith("ollama"):
        valores["OLLAMA_MODO"] = "local" if proveedor == "ollama_local" else "cloud"
        if valores["LLM_MODELO"]:
            valores["OLLAMA_MODELO"] = valores["LLM_MODELO"]
    motor = str(valores.get("TRANSCRIPCION_MOTOR") or "whisper_local").strip().lower()
    valores["TRANSCRIPCION_MOTOR"] = motor if motor in {"whisper_local", "assemblyai"} else "whisper_local"
    env_asm = str(valores.get("ASSEMBLYAI_API_KEY_ENV") or "").strip()
    if env_asm and not env_asm.replace("_", "").isalnum():
        raise ValueError("El nombre de la variable de la API key de AssemblyAI solo puede tener letras, numeros y _.")
    valores["ASSEMBLYAI_API_KEY_ENV"] = env_asm or "ASSEMBLYAI_API_KEY"
    tema = str(valores.get("TEMA_APP", "oscuro")).lower()
    if tema not in {"oscuro", "claro"}:
        raise ValueError("El tema debe ser 'oscuro' o 'claro'.")
    valores["TEMA_APP"] = tema
    return valores


def directorio_scripts() -> Path:
    """Carpeta editable de datos: proyecto en desarrollo, perfil en la app congelada."""
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent
    try:
        from .rutas_app import datos_dir
    except ImportError:
        from rutas_app import datos_dir
    return datos_dir()

def ruta_configuracion() -> Path:
    return directorio_scripts() / "config.py"


def leer_configuracion() -> dict:
    valores = DEFAULTS.copy()
    archivo = ruta_configuracion()
    if not archivo.exists():
        valores["OBS_WS_CONTRASENA"] = os.environ.get("OBS_WS_CONTRASENA", "")
        if getattr(sys, "frozen", False):
            guardar_configuracion(valores)
        return valores
    tiene_solo_grabar = False
    try:
        tree = ast.parse(archivo.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                nombre = node.targets[0].id
                if nombre in valores:
                    if nombre == "OBS_SOLO_GRABAR_DEFAULT":
                        tiene_solo_grabar = True
                    try:
                        valores[nombre] = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        pass
    except (OSError, SyntaxError, UnicodeDecodeError):
        pass
    if not tiene_solo_grabar:
        valores["OBS_SOLO_GRABAR_DEFAULT"] = not bool(valores.get("OBS_PROCESAR_AL_TERMINAR", True))
    # No permitir que una contraseña histórica guardada en config.py se use.
    valores["OBS_WS_CONTRASENA"] = os.environ.get("OBS_WS_CONTRASENA", "")
    for clave in ("CARPETA_STREAMS", "CARPETA_CLIPS_BASE", "CARPETA_RESULTADOS", "CARPETA_EDITADOS"):
        ruta = str(valores.get(clave) or "").strip()
        if ruta:
            valores[clave] = os.path.expanduser(os.path.expandvars(ruta))
    return valores


def guardar_configuracion(valores: dict) -> Path:
    """Actualiza solo claves conocidas y conserva líneas/campos desconocidos."""
    # Evita persistir una contraseña aunque el formulario la incluya.
    valores = dict(valores)
    valores.pop("OBS_WS_CONTRASENA", None)
    valores = normalizar_configuracion(valores)
    archivo = ruta_configuracion()
    texto = archivo.read_text(encoding="utf-8") if archivo.exists() else "# config.py - configuracion de MKClips\n"
    pendientes = dict(valores)
    encontrados = set()
    salida = []
    patron = re.compile(r"^(\s*)({})(?:\s*)=".format("|".join(re.escape(k) for k in pendientes)))
    for linea in texto.splitlines():
        if re.match(r"^\s*OBS_WS_CONTRASENA\s*=", linea):
            continue
        coincidencia = patron.match(linea)
        if coincidencia and coincidencia.group(2) in valores:
            sangria, nombre = coincidencia.groups()
            salida.append(f"{sangria}{nombre} = {valores[nombre]!r}")
            encontrados.add(nombre)
        else:
            salida.append(linea)
    if salida and salida[-1].strip():
        salida.append("")
    salida.extend(
        f"{nombre} = {valor!r}" for nombre, valor in pendientes.items()
        if nombre not in encontrados
    )
    archivo.parent.mkdir(parents=True, exist_ok=True)
    temporal = archivo.with_suffix(".py.tmp")
    temporal.write_text("\n".join(salida) + "\n", encoding="utf-8")
    temporal.replace(archivo)
    # El control de contexto de OBS consulta ``config`` en memoria. Mantén sus
    # valores sincronizados cuando el usuario guarda desde la web o Tk.
    modulo_config = sys.modules.get("config")
    if modulo_config is not None:
        for nombre, valor in valores.items():
            setattr(modulo_config, nombre, valor)
        modulo_config.OBS_WS_CONTRASENA = os.environ.get("OBS_WS_CONTRASENA", "")
    return archivo
