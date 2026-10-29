# -*- coding: utf-8 -*-
"""Lo que la IA que elige los clips sabe de TI y de tu proyecto.

Tres piezas, todas en texto (funcionan con cualquier modelo, nube o local, grande
o pequeño, sin entrenar nada):

1. Objetivo del proyecto  - lo escribes una vez en Configuracion (``CONTEXTO_PROYECTO``).
2. Contexto del stream    - juego, estilo, que pasa en esa tanda (por cola y por stream).
3. Criterios del creador  - reglas cortas que la IA resume de tus valoraciones y notas.
                            Se guardan en ``criterios_creador.txt``: puedes leerlas y
                            editarlas, y se envian en cada analisis.
"""
from __future__ import annotations

import os
import re

try:
    from . import llm_cliente
    from .preferencias_mkclips import cargar_preferencias, ETIQUETAS_MOTIVO
    from .ranker_editorial_mkclips import valor_de_feedback
except ImportError:  # usado como modulo suelto desde scripts/
    import llm_cliente
    from preferencias_mkclips import cargar_preferencias, ETIQUETAS_MOTIVO
    from ranker_editorial_mkclips import valor_de_feedback

try:
    from .rutas_app import datos_dir
except ImportError:
    from rutas_app import datos_dir
ARCHIVO_CRITERIOS = os.path.join(str(datos_dir()), "criterios_creador.txt")
MAX_CONTEXTO = 2000           # caracteres de cada campo de contexto
MAX_CRITERIOS = 2500          # caracteres de la lista de criterios
MAX_REGLAS = 15
MINIMO_VALORACIONES = 10      # con menos, las reglas serian ruido
EJEMPLOS_POR_GRUPO = 40


# ----------------------------------------------------------------------
# Criterios (archivo editable)
# ----------------------------------------------------------------------
def leer_criterios(ruta=ARCHIVO_CRITERIOS):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            return archivo.read().strip()[:MAX_CRITERIOS]
    except OSError:
        return ""


def guardar_criterios(texto, ruta=ARCHIVO_CRITERIOS):
    texto = (texto or "").strip()[:MAX_CRITERIOS]
    if not texto:
        try:
            os.remove(ruta)
        except OSError:
            pass
        return ""
    temporal = f"{ruta}.{os.getpid()}.tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        archivo.write(texto + "\n")
    os.replace(temporal, ruta)
    return texto


# ----------------------------------------------------------------------
# Bloque que se agrega a la instruccion de la IA
# ----------------------------------------------------------------------
def _limpio(texto):
    return re.sub(r"\n{3,}", "\n\n", str(texto or "").strip())[:MAX_CONTEXTO]


def construir_bloque(contexto_proyecto="", contexto_stream="", criterios=""):
    """Texto para la instruccion de la IA; "" si no hay nada que decir."""
    partes = []
    proyecto, stream, reglas = _limpio(contexto_proyecto), _limpio(contexto_stream), str(criterios or "").strip()[:MAX_CRITERIOS]
    if proyecto:
        partes.append("Objetivo del proyecto (lo define el creador):\n" + proyecto)
    if stream:
        partes.append("Contexto de ESTE stream (lo define el creador):\n" + stream)
    if reglas:
        partes.append("Criterios del creador para elegir clips (aprendidos de sus valoraciones; tienen "
                      "prioridad sobre tu criterio general):\n" + reglas)
    return ("\n\n" + "\n\n".join(partes) + "\n") if partes else ""


# ----------------------------------------------------------------------
# Generar los criterios a partir de las valoraciones
# ----------------------------------------------------------------------
def _ultimas(preferencias):
    por_clip = {}
    for n, entrada in enumerate(preferencias.get("feedback", [])):
        por_clip[entrada.get("clip_id") or f"legado_{n}"] = entrada
    return sorted(por_clip.values(), key=lambda e: e.get("timestamp") or 0, reverse=True)


def valoraciones_utiles(preferencias=None):
    datos = preferencias if preferencias is not None else cargar_preferencias()
    return [e for e in _ultimas(datos) if valor_de_feedback(e) is not None and str(e.get("titulo") or "").strip()]


def _linea_ejemplo(entrada):
    partes = [f'- "{str(entrada.get("titulo")).strip()[:120]}"']
    razon = str(entrada.get("razon") or "").strip()
    if razon:
        partes.append(f"razon de la IA: {razon[:120]}")
    motivo = ETIQUETAS_MOTIVO.get(entrada.get("motivo") or "")
    if motivo:
        partes.append(f"motivo: {motivo}")
    nota = str(entrada.get("comentario") or "").strip()
    if nota:
        partes.append(f"nota del creador: {nota[:200]}")
    if entrada.get("juego") and entrada["juego"] not in ("desconocido", "incierta"):
        partes.append(f"juego: {entrada['juego']}")
    return " | ".join(partes)


def prompt_criterios(preferencias=None, criterios_actuales="", contexto_proyecto=""):
    """Instruccion para que la IA resuma tus valoraciones en reglas."""
    utiles = valoraciones_utiles(preferencias)
    buenos = [e for e in utiles if valor_de_feedback(e) > 0][:EJEMPLOS_POR_GRUPO]
    malos = [e for e in utiles if valor_de_feedback(e) < 0][:EJEMPLOS_POR_GRUPO]
    return (
        "Eres un editor de clips para redes sociales. Un creador de contenido valoro clips que otro sistema "
        "propuso. Resume SUS preferencias en reglas cortas para que ese sistema elija mejor la proxima vez.\n\n"
        f"Objetivo del proyecto (del creador): {_limpio(contexto_proyecto) or '(no indicado)'}\n\n"
        f"Criterios actuales (el creador puede haberlos editado; conserva los que sigan vigentes y corrige "
        f"los que las valoraciones nuevas contradigan):\n{str(criterios_actuales or '').strip() or '(ninguno)'}\n\n"
        "CLIPS QUE APROBO (4-5 estrellas):\n" + ("\n".join(_linea_ejemplo(e) for e in buenos) or "(ninguno)") + "\n\n"
        "CLIPS QUE RECHAZO (descartados por contenido o 1-2 estrellas):\n"
        + ("\n".join(_linea_ejemplo(e) for e in malos) or "(ninguno)") + "\n\n"
        f"Escribe entre 5 y {MAX_REGLAS} reglas en espanol, UNA por linea, empezando con \"- \". Cada regla debe "
        "describir un tipo concreto de momento que SI o NO le sirve y estar respaldada por al menos 2 ejemplos "
        "(salvo las que ya estaban en los criterios actuales). No inventes gustos que los ejemplos no muestren "
        "y no cites titulos. Responde SOLO con la lista, sin introduccion."
    )


def limpiar_respuesta_criterios(texto):
    """Se queda solo con las reglas ("- ...", "* ..." o "1. ...") y limita su cantidad y largo."""
    reglas = []
    for linea in str(texto or "").splitlines():
        linea = linea.strip()
        m = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*\S)$", linea)
        if m:
            reglas.append("- " + m.group(1).strip()[:260])
    return "\n".join(reglas[:MAX_REGLAS])[:MAX_CRITERIOS]


def generar_criterios(valores=None, preferencias=None, criterios_actuales=None, contexto_proyecto="", clave=None):
    """Pide a la IA configurada las reglas. Devuelve el texto (sin guardarlo).

    Lanza ``llm_cliente.ErrorLLM`` si la IA falla y ``ValueError`` si faltan valoraciones."""
    datos = preferencias if preferencias is not None else cargar_preferencias()
    utiles = valoraciones_utiles(datos)
    buenos = sum(1 for e in utiles if valor_de_feedback(e) > 0)
    malos = sum(1 for e in utiles if valor_de_feedback(e) < 0)
    if len(utiles) < MINIMO_VALORACIONES or buenos < 2 or malos < 2:
        raise ValueError(
            f"Hacen falta al menos {MINIMO_VALORACIONES} valoraciones utiles, con 2 o mas aprobadas y 2 o mas "
            f"rechazadas, para sacar reglas fiables. Ahora hay {len(utiles)} ({buenos} aprobadas, {malos} rechazadas)."
        )
    actuales = leer_criterios() if criterios_actuales is None else criterios_actuales
    respuesta = llm_cliente.pedir(prompt_criterios(datos, actuales, contexto_proyecto), valores=valores,
                                  clave=clave, max_tokens=1500)
    reglas = limpiar_respuesta_criterios(respuesta)
    if not reglas:
        raise llm_cliente.ErrorLLM("La IA no devolvio reglas con el formato esperado. Intentalo de nuevo.")
    return reglas
