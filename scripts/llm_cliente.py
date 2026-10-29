# -*- coding: utf-8 -*-
"""Cliente de IA configurable para elegir clips.

Un único punto de entrada, ``pedir(prompt)``, que funciona con:

* ``ollama_cloud``  - Ollama Cloud (https://ollama.com) con API key.
* ``ollama_local``  - Ollama instalado en este equipo.
* ``openai``        - cualquier API compatible con OpenAI ("/chat/completions"):
                      OpenAI, Google Gemini, DeepSeek, Groq, OpenRouter, Mistral,
                      Moonshot (Kimi), Together, LM Studio, vLLM...
* ``anthropic``     - API de Anthropic (Claude).

Los ajustes no secretos se leen de config.py (claves ``LLM_*``) en cada llamada.
La API key se toma exclusivamente de la variable de entorno indicada en
``LLM_API_KEY_ENV``; MKClips nunca la persiste.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request

try:
    from .configuracion_central import leer_configuracion
except ImportError:  # usado como modulo suelto desde scripts/
    from configuracion_central import leer_configuracion

PROVEEDORES = ("ollama_cloud", "ollama_local", "openai", "anthropic")

# Valores sugeridos por la interfaz. Los nombres de modelo cambian con
# frecuencia: se dejan vacios salvo en Ollama, para que el usuario ponga el que
# quiera de la lista de su proveedor.
PRESETS = {
    "Ollama Cloud": ("ollama_cloud", "https://ollama.com", "gpt-oss:120b-cloud", "OLLAMA_API_KEY"),
    "Ollama local": ("ollama_local", "http://localhost:11434", "", ""),
    "OpenAI": ("openai", "https://api.openai.com/v1", "", "OPENAI_API_KEY"),
    "Google Gemini": ("openai", "https://generativelanguage.googleapis.com/v1beta/openai", "", "GEMINI_API_KEY"),
    "DeepSeek": ("openai", "https://api.deepseek.com", "", "DEEPSEEK_API_KEY"),
    "Groq": ("openai", "https://api.groq.com/openai/v1", "", "GROQ_API_KEY"),
    "OpenRouter": ("openai", "https://openrouter.ai/api/v1", "", "OPENROUTER_API_KEY"),
    "Mistral": ("openai", "https://api.mistral.ai/v1", "", "MISTRAL_API_KEY"),
    "Moonshot (Kimi)": ("openai", "https://api.moonshot.ai/v1", "", "MOONSHOT_API_KEY"),
    "Anthropic (Claude)": ("anthropic", "https://api.anthropic.com", "", "ANTHROPIC_API_KEY"),
    "Otra (compatible OpenAI)": ("openai", "", "", "LLM_API_KEY"),
}

class ErrorLLM(RuntimeError):
    """Fallo de configuración o de la API (con mensaje legible).

    ``fatal`` = reintentar o seguir con otro bloque no sirve (sin clave, sin
    modelo, clave inválida, modelo inexistente): hay que avisar y parar.
    """

    def __init__(self, mensaje, fatal=False):
        super().__init__(mensaje)
        self.fatal = fatal


def configuracion_llm(valores=None):
    """Configuración efectiva (con valores por defecto compatibles con Ollama)."""
    v = dict(valores) if valores is not None else leer_configuracion()
    proveedor = str(v.get("LLM_PROVEEDOR") or "").strip().lower()
    if proveedor not in PROVEEDORES:
        # Compatibilidad con la configuración anterior (OLLAMA_MODO).
        proveedor = "ollama_local" if str(v.get("OLLAMA_MODO", "cloud")).lower() == "local" else "ollama_cloud"
    base = str(v.get("LLM_BASE_URL") or "").strip().rstrip("/")
    modelo = str(v.get("LLM_MODELO") or "").strip()
    if proveedor == "ollama_cloud":
        base = base or "https://ollama.com"
        modelo = modelo or str(v.get("OLLAMA_MODELO") or "gpt-oss:120b-cloud").strip()
    elif proveedor == "ollama_local":
        base = base or str(v.get("OLLAMA_HOST") or "http://localhost:11434").strip().rstrip("/")
        modelo = modelo or str(v.get("OLLAMA_MODELO") or "").strip()
    elif proveedor == "anthropic":
        base = base or "https://api.anthropic.com"
    clave_env = str(v.get("LLM_API_KEY_ENV") or "").strip() or ("OLLAMA_API_KEY" if proveedor.startswith("ollama") else "LLM_API_KEY")
    try:
        max_tokens = max(256, int(v.get("LLM_MAX_TOKENS") or 8192))
    except (TypeError, ValueError):
        max_tokens = 8192
    try:
        timeout = max(10, int(v.get("LLM_TIMEOUT") or 300))
    except (TypeError, ValueError):
        timeout = 300
    try:
        concurrencia = min(8, max(1, int(v.get("LLM_CONCURRENCIA") or 3)))
    except (TypeError, ValueError):
        concurrencia = 3
    return {"proveedor": proveedor, "base_url": base, "modelo": modelo, "clave_env": clave_env,
            "max_tokens": max_tokens, "timeout": timeout, "concurrencia": concurrencia}


def leer_clave(cfg):
    """API key leída exclusivamente de la variable de entorno configurada."""
    return os.environ.get(cfg["clave_env"], "").strip()


def _validar(cfg, clave):
    if not cfg["modelo"]:
        raise ErrorLLM("No hay modelo configurado. Indícalo en Configuración > IA.", fatal=True)
    if cfg["proveedor"] != "ollama_local":
        if not cfg["base_url"]:
            raise ErrorLLM("Falta la URL base de la API. Indícala en Configuración > IA.", fatal=True)
        if not clave:
            raise ErrorLLM(
                f"Falta la API key: define la variable de entorno {cfg['clave_env']} "
                "o guárdala en Configuración > IA.", fatal=True,
            )


def _post_json(url, cuerpo, cabeceras, timeout):
    datos = json.dumps(cuerpo).encode("utf-8")
    peticion = urllib.request.Request(url, data=datos, method="POST",
                                      headers={"Content-Type": "application/json", **cabeceras})
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return json.loads(respuesta.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detalle = exc.read().decode("utf-8", "replace")[:600]
        except Exception:
            detalle = ""
        raise ErrorLLM(f"HTTP {exc.code}: {detalle or exc.reason}", fatal=exc.code in (401, 403, 404)) from exc
    except urllib.error.URLError as exc:
        raise ErrorLLM(f"No se pudo conectar con {url}: {exc.reason}") from exc


def _texto_openai(respuesta):
    try:
        contenido = respuesta["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ErrorLLM(f"Respuesta inesperada de la API: {str(respuesta)[:300]}") from exc
    if isinstance(contenido, list):  # algunos proveedores devuelven bloques
        contenido = "".join(b.get("text", "") for b in contenido if isinstance(b, dict))
    return (contenido or "").strip()


def _llamar_openai(cfg, clave, prompt, max_tokens):
    url = cfg["base_url"] + "/chat/completions"
    cabeceras = {"Authorization": f"Bearer {clave}"}
    base = {"model": cfg["modelo"], "messages": [{"role": "user", "content": prompt}]}
    # OpenAI exige max_completion_tokens en sus modelos nuevos; el resto de
    # proveedores compatibles usan max_tokens. Si uno rechaza el parametro se
    # prueba con el otro.
    primero = "max_completion_tokens" if "api.openai.com" in cfg["base_url"] else "max_tokens"
    segundo = "max_tokens" if primero == "max_completion_tokens" else "max_completion_tokens"
    try:
        return _texto_openai(_post_json(url, {**base, primero: max_tokens}, cabeceras, cfg["timeout"]))
    except ErrorLLM as exc:
        texto = str(exc)
        if "HTTP 400" in texto and ("max_tokens" in texto or "max_completion_tokens" in texto):
            return _texto_openai(_post_json(url, {**base, segundo: max_tokens}, cabeceras, cfg["timeout"]))
        raise


def _llamar_anthropic(cfg, clave, prompt, max_tokens):
    url = cfg["base_url"] + "/v1/messages"
    cabeceras = {"x-api-key": clave, "anthropic-version": "2023-06-01"}
    cuerpo = {"model": cfg["modelo"], "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]}
    respuesta = _post_json(url, cuerpo, cabeceras, cfg["timeout"])
    try:
        bloques = respuesta["content"]
        return "".join(b.get("text", "") for b in bloques if b.get("type") == "text").strip()
    except (KeyError, TypeError, AttributeError) as exc:
        raise ErrorLLM(f"Respuesta inesperada de la API: {str(respuesta)[:300]}") from exc


def _llamar_ollama(cfg, clave, prompt, max_tokens):
    try:
        import ollama
    except ImportError as exc:
        raise ErrorLLM("Falta el paquete 'ollama' (pip install ollama).") from exc
    cabeceras = {"Authorization": "Bearer " + clave} if cfg["proveedor"] == "ollama_cloud" else None
    cliente = ollama.Client(host=cfg["base_url"], headers=cabeceras, timeout=cfg["timeout"])
    respuesta = cliente.chat(model=cfg["modelo"], messages=[{"role": "user", "content": prompt}],
                             think=False, options={"num_predict": max_tokens})
    return (respuesta["message"]["content"] or "").strip()


def _llamar(cfg, clave, prompt, max_tokens):
    if cfg["proveedor"].startswith("ollama"):
        return _llamar_ollama(cfg, clave, prompt, max_tokens)
    if cfg["proveedor"] == "anthropic":
        return _llamar_anthropic(cfg, clave, prompt, max_tokens)
    return _llamar_openai(cfg, clave, prompt, max_tokens)


_SEMAFORO = {"limite": 0, "obj": None}
_CANDADO = threading.Lock()


def _semaforo(cfg):
    """Tope GLOBAL de peticiones simultáneas (LLM_CONCURRENCIA): todos los hilos
    comparten el mismo límite, así que paralelizar nunca excede lo que tu plan permite."""
    with _CANDADO:
        if _SEMAFORO["obj"] is None or _SEMAFORO["limite"] != cfg["concurrencia"]:
            _SEMAFORO.update(limite=cfg["concurrencia"], obj=threading.BoundedSemaphore(cfg["concurrencia"]))
        return _SEMAFORO["obj"]


def _es_limite_de_uso(exc):
    texto = str(exc).lower()
    return "429" in texto or "rate limit" in texto or "too many requests" in texto or "overloaded" in texto


def pedir(prompt, intentos=3, max_tokens=None, valores=None, clave=None, espera=3):
    """Envía ``prompt`` al modelo configurado y devuelve el texto de la respuesta.

    Reintenta ante errores de red, respuestas vacías y límites de uso (429, con
    espera creciente). Los errores de configuración (sin modelo, sin clave,
    clave inválida) se lanzan de inmediato con ``fatal=True``; si se agotan los
    intentos se lanza un ``ErrorLLM`` con ``fatal=False``.
    """
    cfg = configuracion_llm(valores)
    clave = clave if clave is not None else leer_clave(cfg)
    _validar(cfg, clave)
    limite = int(max_tokens or cfg["max_tokens"])
    semaforo = _semaforo(cfg)
    ultimo = None
    for intento in range(1, intentos + 1):
        try:
            with semaforo:
                texto = _llamar(cfg, clave, prompt, limite)
            if texto:
                return texto
            ultimo = ErrorLLM("la IA devolvió una respuesta vacía")
        except ErrorLLM as exc:
            ultimo = exc
            if exc.fatal:
                raise  # clave invalida o modelo inexistente: reintentar no ayuda
        except Exception as exc:  # errores de la libreria de Ollama, timeouts, etc.
            ultimo = ErrorLLM(str(exc))
            if "401" in str(exc) or "403" in str(exc) or "404" in str(exc):
                ultimo.fatal = True
                raise ultimo from exc
        print(f"     (La IA no respondió: {ultimo}. Reintento {intento}/{intentos}...)")
        if intento < intentos:
            # Un límite de uso pide esperar más; se escalona para no reintentar en bloque.
            time.sleep(espera * (4 * intento if _es_limite_de_uso(ultimo) else 1))
    raise ErrorLLM(f"La IA ({cfg['proveedor']} / {cfg['modelo']}) no respondió tras {intentos} intentos: {ultimo}")


def probar(valores=None, clave=None):
    """Prueba la conexión con una petición mínima. Devuelve (mensaje, segundos)."""
    cfg = configuracion_llm(valores)
    clave = clave if clave is not None else leer_clave(cfg)
    _validar(cfg, clave)
    inicio = time.time()
    texto = _llamar(cfg, clave, "Responde únicamente con la palabra OK.", 512)
    if not texto:
        raise ErrorLLM("La conexión funciona pero el modelo devolvió una respuesta vacía.")
    return f"{cfg['proveedor']} / {cfg['modelo']} respondió: {texto[:60]}", time.time() - inicio
