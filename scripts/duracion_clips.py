"""Reglas deterministas de duración para clips narrativos.

No recorta timestamps de forma arbitraria: solo conserva un candidato ya
válido o lo amplía a su unidad narrativa completa cuando esa unidad cabe en el
rango configurado.
"""
from __future__ import annotations

import math


def validar_limites_duracion(minimo, maximo):
    try:
        minimo = float(minimo)
        maximo = float(maximo)
    except (TypeError, ValueError) as exc:
        raise ValueError("Las duraciones mínima y máxima deben ser números.") from exc
    if not math.isfinite(minimo) or not math.isfinite(maximo):
        raise ValueError("Las duraciones mínima y máxima deben ser números finitos.")
    if minimo < 0 or maximo < 0:
        raise ValueError("Las duraciones mínima y máxima deben ser mayores o iguales a 0.")
    if minimo > 0 and maximo > 0 and minimo > maximo:
        raise ValueError("La duración mínima no puede ser mayor que la máxima.")
    return minimo, maximo


# Margen que se resta al maximo configurado: al guardar el contenedor (mkv/mp4)
# la duracion real sale unas centesimas mayor que la planificada (en los
# resultados verificados llegaba a +0,03 s), asi que planificar justo en el
# limite lo superaria.
MARGEN_MAXIMO = 0.15


def maximo_efectivo(maximo):
    """Duracion maxima a planificar (0 = sin limite)."""
    maximo = float(maximo or 0)
    if maximo <= 0:
        return 0.0
    return max(0.1, maximo - MARGEN_MAXIMO)


def recortar_segmentos_a_maximo(segmentos, maximo):
    """Devuelve ``segmentos`` sin pasar de ``maximo`` segundos en total.

    Quita material del FINAL (descarta segmentos completos y recorta el ultimo)
    para no tocar el arranque del clip. ``segmentos`` es una lista de
    ``(inicio, fin)``; devuelve una lista nueva del mismo tipo. Con maximo 0 no
    cambia nada.
    """
    limite = maximo_efectivo(maximo)
    if limite <= 0:
        return [(float(i), float(f)) for i, f in segmentos]
    restante = limite
    salida = []
    for inicio, fin in segmentos:
        inicio, fin = float(inicio), float(fin)
        largo = fin - inicio
        if largo <= 0:
            continue
        if restante <= 0.05:
            break
        if largo <= restante:
            salida.append((inicio, fin))
            restante -= largo
        else:
            salida.append((inicio, round(inicio + restante, 3)))
            restante = 0
            break
    return salida


def duracion_candidato(candidato):
    segmentos = candidato.get("segmentos")
    if isinstance(segmentos, list) and len(segmentos) > 1:
        return sum(max(0.0, float(s["fin"]) - float(s["inicio"])) for s in segmentos)
    return max(0.0, float(candidato["fin"]) - float(candidato["inicio"]))


def esta_en_rango(candidato, minimo, maximo):
    duracion = duracion_candidato(candidato)
    return (minimo == 0 or duracion >= minimo) and (maximo == 0 or duracion <= maximo)


def _unidad_para(candidato, unidades_narrativas):
    nombre = candidato.get("unidad_narrativa")
    return next((u for u in unidades_narrativas if f"unidad_{u['id']}" == nombre), None)


def ajustar_a_limites_narrativos(candidato, unidades_narrativas, minimo, maximo):
    """Devuelve el candidato válido o ``None`` si no cabe sin romper su arco.

    Un candidato corto puede ampliarse únicamente a su unidad narrativa entera.
    Un candidato demasiado largo se rechaza: partirlo por duración produciría un
    clip incompleto. Los segmentos compuestos que ya cumplen se conservan tal
    cual.
    """
    minimo, maximo = validar_limites_duracion(minimo, maximo)
    if minimo == 0 and maximo == 0:
        return candidato
    if esta_en_rango(candidato, minimo, maximo):
        return candidato

    duracion = duracion_candidato(candidato)
    if maximo > 0 and duracion > maximo:
        return None
    if minimo == 0 or duracion >= minimo:
        return None

    unidad = _unidad_para(candidato, unidades_narrativas)
    if not unidad:
        return None
    inicio = round(float(unidad["inicio"]), 2)
    fin = round(float(unidad["fin"]), 2)
    if fin <= inicio:
        return None

    ampliado = dict(candidato)
    ampliado["inicio"] = inicio
    ampliado["fin"] = fin
    # Una unidad completa es un tramo narrativo continuo; no se conservan
    # saltos que dejarían fuera el contexto añadido.
    ampliado.pop("segmentos", None)
    if not esta_en_rango(ampliado, minimo, maximo):
        return None
    return ampliado
