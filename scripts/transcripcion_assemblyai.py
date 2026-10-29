"""Transcripcion en la nube con AssemblyAI (alternativa opcional a Whisper local).

Solo usa la libreria estandar. Flujo: subir el audio -> crear la transcripcion -> esperar ->
convertir las palabras con tiempos en segmentos {inicio, fin, texto} (el mismo formato que
produce Whisper, asi que el resto del pipeline no cambia).

El audio sale de tu equipo hacia AssemblyAI; el servicio es de pago o con credito limitado
(revisa tu cuenta en assemblyai.com). Ante cualquier fallo el pipeline vuelve a Whisper local.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

try:
    from .configuracion_central import leer_configuracion
except ImportError:  # modulo suelto desde scripts/
    from configuracion_central import leer_configuracion

BASE_URL = "https://api.assemblyai.com"
SEGMENTO_DESCARTABLE = {".", "...", ",", "-", ""}
FIN_DE_FRASE = (".", "?", "!", "…")
INTERVALO_ESPERA_SEG = 5.0
REINTENTOS = 3


class ErrorAssemblyAI(Exception):
    """``fatal`` = problema de configuracion/cuenta (clave, saldo): reintentar no sirve."""

    def __init__(self, mensaje, fatal=False):
        super().__init__(mensaje)
        self.fatal = fatal


# --------------------------------------------------------------------------- configuracion
def parametros(valores=None):
    cfg = dict(valores) if valores is not None else leer_configuracion()
    def num(clave, minimo, defecto):
        try:
            return max(minimo, float(cfg.get(clave, defecto)))
        except (TypeError, ValueError):
            return defecto
    return {
        "env": str(cfg.get("ASSEMBLYAI_API_KEY_ENV") or "ASSEMBLYAI_API_KEY"),
        "terminos": [str(t).strip() for t in (cfg.get("ASSEMBLYAI_TERMINOS") or []) if str(t).strip()],
        "modelos": [str(m).strip() for m in (cfg.get("ASSEMBLYAI_MODELOS") or []) if str(m).strip()],
        "pausa": num("ASSEMBLYAI_PAUSA_SEG", 0.1, 1.0),
        "max_segmento": num("ASSEMBLYAI_MAX_SEGMENTO_SEG", 5.0, 25.0),
        "espera_max_min": num("ASSEMBLYAI_ESPERA_MAX_MIN", 5.0, 180.0),
    }


def leer_clave(env="ASSEMBLYAI_API_KEY"):
    """API key leída exclusivamente de la variable de entorno indicada."""
    return os.environ.get(env, "").strip()


# --------------------------------------------------------------------------- HTTP
def _mensaje_error(cuerpo):
    try:
        datos = json.loads(cuerpo)
        return str(datos.get("error") or datos)[:300]
    except (ValueError, AttributeError):
        return cuerpo[:300].decode("utf-8", "replace") if isinstance(cuerpo, bytes) else str(cuerpo)[:300]


def _peticion(metodo, url, clave, cuerpo_json=None, datos=None, cabeceras=None, timeout=60, dormir=time.sleep):
    """Peticion con reintentos ante red/5xx/429. 401/402/403 -> ErrorAssemblyAI(fatal)."""
    cabeceras = dict(cabeceras or {}, authorization=clave)
    if cuerpo_json is not None:
        datos = json.dumps(cuerpo_json).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"
    ultimo = None
    for intento in range(REINTENTOS):
        if hasattr(datos, "seek"):
            datos.seek(0)
        try:
            req = urllib.request.Request(url, data=datos, headers=cabeceras, method=metodo)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            texto = _mensaje_error(exc.read())
            if exc.code in (401, 402, 403):
                raise ErrorAssemblyAI(f"AssemblyAI rechazo la peticion ({exc.code}): {texto}", fatal=True) from exc
            if exc.code == 429 or exc.code >= 500:
                ultimo = ErrorAssemblyAI(f"AssemblyAI respondio {exc.code}: {texto}")
            else:
                raise ErrorAssemblyAI(f"AssemblyAI respondio {exc.code}: {texto}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            ultimo = ErrorAssemblyAI(f"Sin conexion con AssemblyAI: {exc}")
        if intento < REINTENTOS - 1:
            dormir(3 * (intento + 1))
    raise ultimo


def probar_clave(clave, base_url=BASE_URL):
    """Comprueba la clave sin gastar credito (lista 1 transcripcion). Devuelve un texto."""
    _peticion("GET", f"{base_url}/v2/transcript?limit=1", clave, timeout=20)
    return "AssemblyAI respondio correctamente: la clave es valida."


# --------------------------------------------------------------------------- pasos
def _preparar_audio(ruta):
    """Devuelve (ruta_a_subir, temporal|None). FLAC sin perdida: ~la mitad que el WAV, subida mas rapida."""
    try:
        fd, tmp = tempfile.mkstemp(prefix="mkclips_asm_", suffix=".flac")
        os.close(fd)
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", ruta, "-vn", "-c:a", "flac", tmp],
                           capture_output=True, timeout=3600)
        if r.returncode == 0 and os.path.getsize(tmp) > 1024:
            return tmp, tmp
        os.remove(tmp)
    except Exception:
        pass
    return ruta, None


def subir_audio(ruta, clave, base_url=BASE_URL, dormir=time.sleep):
    with open(ruta, "rb") as f:
        r = _peticion("POST", f"{base_url}/v2/upload", clave, datos=f, timeout=900, dormir=dormir,
                      cabeceras={"Content-Type": "application/octet-stream",
                                 "Content-Length": str(os.path.getsize(ruta))})
    if not r.get("upload_url"):
        raise ErrorAssemblyAI("AssemblyAI no devolvio la direccion del audio subido.")
    return r["upload_url"]


def crear_transcripcion(url_audio, clave, cfg, base_url=BASE_URL, dormir=time.sleep, notificar=print):
    cuerpo = {"audio_url": url_audio, "language_code": "es", "punctuate": True, "format_text": True}
    if cfg["modelos"]:
        cuerpo["speech_models"] = cfg["modelos"]
    if cfg["terminos"]:
        cuerpo["keyterms_prompt"] = cfg["terminos"]
    try:
        r = _peticion("POST", f"{base_url}/v2/transcript", clave, cuerpo_json=cuerpo, dormir=dormir)
    except ErrorAssemblyAI as exc:
        if not cfg["terminos"] or exc.fatal:
            raise
        # Si el servicio no acepta los terminos clave (limite o modelo), se reintenta sin ellos.
        notificar(f"AssemblyAI no acepto los terminos clave ({exc}); se reintenta sin ellos.")
        cuerpo.pop("keyterms_prompt")
        r = _peticion("POST", f"{base_url}/v2/transcript", clave, cuerpo_json=cuerpo, dormir=dormir)
    if not r.get("id"):
        raise ErrorAssemblyAI("AssemblyAI no devolvio el identificador de la transcripcion.")
    return r["id"]


def esperar_resultado(id_transcripcion, clave, cfg, base_url=BASE_URL, dormir=time.sleep, reloj=time.time,
                      notificar=print, progreso=None):
    limite = reloj() + cfg["espera_max_min"] * 60
    inicio = reloj()
    while True:
        r = _peticion("GET", f"{base_url}/v2/transcript/{id_transcripcion}", clave, dormir=dormir)
        estado = r.get("status")
        if estado == "completed":
            return r
        if estado == "error":
            raise ErrorAssemblyAI(f"AssemblyAI no pudo transcribir: {r.get('error', 'error desconocido')}")
        if reloj() > limite:
            raise ErrorAssemblyAI(f"AssemblyAI tardo mas de {cfg['espera_max_min']:g} min; se cancela la espera.")
        if progreso:
            progreso(40, f"Transcribiendo en AssemblyAI ({estado})... {int((reloj() - inicio) // 60)} min")
        dormir(INTERVALO_ESPERA_SEG)


def palabras_a_segmentos(palabras, pausa=1.0, max_segmento=25.0, correcciones=None):
    """Agrupa palabras (tiempos en ms) en segmentos {inicio, fin, texto} en segundos.

    Corta al terminar una frase (. ? ! …), tras una pausa >= ``pausa`` s o al superar ``max_segmento`` s."""
    segmentos, actual = [], []

    def cerrar():
        if not actual:
            return
        texto = " ".join(str(p.get("text", "")).strip() for p in actual).strip()
        for mal, bien in (correcciones or {}).items():
            texto = texto.replace(mal, bien)
        if texto not in SEGMENTO_DESCARTABLE:
            segmentos.append({"inicio": round(actual[0]["start"] / 1000, 2),
                              "fin": round(actual[-1]["end"] / 1000, 2), "texto": texto})
        actual.clear()

    palabras = [p for p in (palabras or []) if isinstance(p, dict) and "start" in p and "end" in p and str(p.get("text", "")).strip()]
    for p in palabras:
        if actual and ((p["start"] - actual[-1]["end"]) / 1000 >= pausa
                       or (p["end"] - actual[0]["start"]) / 1000 > max_segmento):
            cerrar()
        actual.append(p)
        if str(p["text"]).strip().endswith(FIN_DE_FRASE) and (p["end"] - actual[0]["start"]) / 1000 >= 2.0:
            cerrar()
    cerrar()
    return segmentos


def transcribir(ruta_audio, clave=None, valores=None, correcciones=None, notificar=print, progreso=None,
                base_url=BASE_URL, dormir=time.sleep, reloj=time.time):
    """Transcribe ``ruta_audio`` y devuelve la lista de segmentos. Lanza ErrorAssemblyAI si falla."""
    cfg = parametros(valores)
    clave = clave or leer_clave(cfg["env"])
    if not clave:
        raise ErrorAssemblyAI(f"Falta la API key de AssemblyAI (variable {cfg['env']} o configuracion).", fatal=True)
    if progreso:
        progreso(5, "Preparando audio para AssemblyAI...")
    subir, temporal = _preparar_audio(ruta_audio)
    try:
        notificar(f"Subiendo audio a AssemblyAI ({os.path.getsize(subir) / 1e6:.0f} MB)...")
        if progreso:
            progreso(10, "Subiendo audio a AssemblyAI...")
        url = subir_audio(subir, clave, base_url, dormir)
    finally:
        if temporal:
            try:
                os.remove(temporal)
            except OSError:
                pass
    id_t = crear_transcripcion(url, clave, cfg, base_url, dormir, notificar)
    notificar("AssemblyAI esta transcribiendo (puede tardar unos minutos)...")
    r = esperar_resultado(id_t, clave, cfg, base_url, dormir, reloj, notificar, progreso)
    segmentos = palabras_a_segmentos(r.get("words"), cfg["pausa"], cfg["max_segmento"], correcciones)
    if progreso:
        progreso(99, "Transcripcion de AssemblyAI lista")
    return segmentos
