# -*- coding: utf-8 -*-
"""Recorte inteligente: quita lo menos importante de un momento que se pasa del maximo.

Antes, un momento bueno que duraba mas que ``DURACION_MAX_CLIP`` se eliminaba sin mas.
Aqui se le pide a la IA que decida QUE tramos intermedios sobran (conservando el
arranque y el remate) y el resultado se valida con reglas estrictas. Si la IA no
responde o propone algo invalido, el momento NO se pierde en silencio: queda
registrado como "fuera de rango" para que lo revises.

No importa identificar_clips.py (que es un script): recibe la funcion ``pedir``.
"""
from __future__ import annotations

import json

try:
    from .duracion_clips import maximo_efectivo
    from .narrativa_mkclips import normalizar_segmentos_sin_duplicados
except ImportError:  # usado como modulo suelto desde scripts/
    from duracion_clips import maximo_efectivo
    from narrativa_mkclips import normalizar_segmentos_sin_duplicados

MAX_SEGMENTOS = 6
SEGMENTO_MINIMO = 2.5          # un tramo mas corto que esto se siente como un tic
TOLERANCIA_BORDE = 0.6         # cuanto puede alejarse un corte del borde real de una linea
MAX_LINEAS_PROMPT = 400


def _duracion(segmentos):
    return sum(max(0.0, float(s["fin"]) - float(s["inicio"])) for s in segmentos)


def intervalos(candidato):
    segs = candidato.get("segmentos")
    if isinstance(segs, list) and segs:
        return [{"inicio": float(s["inicio"]), "fin": float(s["fin"])} for s in segs]
    return [{"inicio": float(candidato["inicio"]), "fin": float(candidato["fin"])}]


def lineas_del_candidato(candidato, linea_tiempo):
    """Lineas (habla y picos de audio) que caen dentro de los intervalos del candidato."""
    ivs = intervalos(candidato)
    salida = []
    for item in linea_tiempo:
        try:
            a, b = float(item["inicio"]), float(item["fin"])
        except (KeyError, TypeError, ValueError):
            continue
        if any(b > iv["inicio"] and a < iv["fin"] for iv in ivs):
            salida.append(item)
    return salida


def construir_prompt(candidato, lineas, maximo, minimo):
    texto = "\n".join(
        f"[{float(x['inicio']):.2f}s - {float(x['fin']):.2f}s] {'🔊 ' if x.get('tipo') == 'audio' else ''}{x.get('texto', '')}"
        for x in lineas[:MAX_LINEAS_PROMPT]
    )
    total = _duracion(intervalos(candidato))
    objetivo = f"entre {minimo:g} y {maximo:g} segundos" if minimo else f"como maximo {maximo:g} segundos"
    return f"""Este momento de un directo de gaming es muy bueno pero dura {total:.0f} s y debe quedar {objetivo} en total: "{candidato.get('titulo', '')}" ({candidato.get('razon', '')}).

Transcripcion con tiempos reales:

{texto}

Tu tarea: como editor de Shorts/Reels/TikTok, quita los tramos MENOS importantes DE EN MEDIO (explicaciones, pausas, relleno, repeticiones, tramos sin accion) para que quepa. Conserva:
- el ARRANQUE: lo que engancha en los primeros segundos y lo minimo para entender la situacion;
- el CLIMAX y el REMATE/reaccion final, completos (nunca cortes una frase importante);
- la continuidad: el resultado debe entenderse sin conocer el resto del stream.

Reglas estrictas:
- Devuelve entre 2 y {MAX_SEGMENTOS} tramos en orden cronologico, sin solaparse.
- Cada tramo empieza y termina en el borde de una linea de la transcripcion (usa sus tiempos exactos).
- Ningun tramo dura menos de {SEGMENTO_MINIMO:g} s.
- La suma de los tramos debe ser {objetivo}.
- No inventes tiempos fuera de la transcripcion.

Devuelve SOLO un JSON valido, sin texto extra:
{{"segmentos": [{{"inicio": 100.0, "fin": 120.0}}, {{"inicio": 145.0, "fin": 170.0}}], "quitado": "que se elimino y por que, en una frase"}}"""


def _ajustar_a_bordes(segmentos, lineas):
    """Pega cada corte al borde de linea mas cercano (si esta a menos de TOLERANCIA_BORDE)."""
    inicios = sorted({float(x["inicio"]) for x in lineas})
    fines = sorted({float(x["fin"]) for x in lineas})

    def cercano(valor, opciones):
        mejor = min(opciones, key=lambda o: abs(o - valor)) if opciones else valor
        return mejor if abs(mejor - valor) <= TOLERANCIA_BORDE else valor

    return [{"inicio": round(cercano(float(s["inicio"]), inicios), 2),
             "fin": round(cercano(float(s["fin"]), fines), 2)} for s in segmentos]


def validar_respuesta(contenido, candidato, lineas, maximo, minimo):
    """Devuelve (segmentos, motivo_de_rechazo). ``segmentos`` es None si no sirve."""
    try:
        datos = json.loads(contenido)
    except (TypeError, ValueError):
        return None, "respuesta_no_json"
    crudos = datos.get("segmentos") if isinstance(datos, dict) else None
    if not isinstance(crudos, list) or not crudos:
        return None, "sin_segmentos"
    ivs = intervalos(candidato)
    limpios = []
    for s in crudos:
        try:
            a, b = float(s["inicio"]), float(s["fin"])
        except (KeyError, TypeError, ValueError):
            return None, "segmento_invalido"
        # Todo tiempo debe caer dentro del momento original (con un margen pequeno).
        if not any(a >= iv["inicio"] - 1.0 and b <= iv["fin"] + 1.0 for iv in ivs):
            return None, "tiempos_fuera_del_momento"
        limpios.append({"inicio": a, "fin": b})
    limpios = _ajustar_a_bordes(limpios, lineas)
    limpios = normalizar_segmentos_sin_duplicados(limpios, duracion_minima=SEGMENTO_MINIMO)
    if not limpios or len(limpios) > MAX_SEGMENTOS:
        return None, "numero_de_segmentos_invalido"
    if any(float(s["fin"]) - float(s["inicio"]) < SEGMENTO_MINIMO for s in limpios):
        return None, "segmento_demasiado_corto"
    total = _duracion(limpios)
    tope = maximo_efectivo(maximo)
    if tope and total > tope:
        return None, f"sigue_excediendo_el_maximo ({total:.1f}s)"
    if minimo and total < minimo:
        return None, f"queda_bajo_el_minimo ({total:.1f}s)"
    return limpios, ""


def recortar(candidato, linea_tiempo, maximo, minimo, pedir, intentos=2):
    """Intenta que ``candidato`` quepa en el maximo quitando tramos intermedios.

    ``pedir(prompt, intentos=...)`` devuelve el texto JSON de la IA o None.
    Devuelve ``(candidato_nuevo, "")`` si lo logra o ``(None, motivo)`` si no."""
    lineas = lineas_del_candidato(candidato, linea_tiempo)
    if not lineas:
        return None, "sin_transcripcion_para_recortar"
    prompt = construir_prompt(candidato, lineas, maximo, minimo)
    motivo = "sin_respuesta_de_la_ia"
    for _ in range(max(1, intentos)):
        contenido = pedir(prompt, intentos=1)
        if not contenido:
            continue
        segmentos, motivo = validar_respuesta(contenido, candidato, lineas, maximo, minimo)
        if segmentos:
            nuevo = dict(candidato)
            nuevo["segmentos"] = segmentos
            nuevo["inicio"], nuevo["fin"] = segmentos[0]["inicio"], segmentos[-1]["fin"]
            nuevo["recortado_por_ia"] = True
            nuevo["duracion_original"] = round(_duracion(intervalos(candidato)), 2)
            try:
                nuevo["quitado"] = str(json.loads(contenido).get("quitado", ""))[:200]
            except (TypeError, ValueError, AttributeError):
                nuevo["quitado"] = ""
            return nuevo, ""
    return None, motivo
