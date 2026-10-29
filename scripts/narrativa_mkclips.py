"""Modelos y señales locales para la selección narrativa de MKClips.

No crea hechos: las etiquetas describen evidencia textual disponible y sirven
para ordenar candidatos que ya fueron detectados por el modelo.
"""
from __future__ import annotations

import os
import math
import re
from collections import Counter


_JUEGOS = {
    "zelda": ("The Legend of Zelda", "Zelda"),
    "minecraft": ("Minecraft", "Minecraft"),
    "pokemon": ("Pokémon", "Pokémon"),
    "roblox": ("Roblox", "Roblox"),
    "resident evil": ("Resident Evil", "Resident Evil"),
    "clash royale": ("Clash Royale", "Clash Royale"),
}
_EVENTOS = {
    "puzzle": r"\b(puzzle|acertijo|palanca|puerta|llave|resolver|soluci[oó]n)\b",
    "combate": r"\b(jefe|enemigo|combate|pelea|ataque|derrota|victoria|muri[oó]|matar)\b",
    "descubrimiento": r"\b(encuentra|descubre|objeto|cofre|recompensa|nuevo)\b",
    "decision": r"\b(decidimos|decide|vamos a|hay que|estrategia|intentar)\b",
    "historia": r"\b(historia|dialogo|di[aá]logo|misi[oó]n|personaje|revelaci[oó]n)\b",
    "construccion": r"\b(construir|construye|casa|base|material|recurso)\b",
    "reaccion": r"\b(jaj|risa|grito|wtf|nooo|incre[ií]ble|susto)\b",
}
_COMICO = re.compile(r"\b(jaj|risa|lol|meme|broma|gracioso|chiste|wtf|no manches)\b", re.I)
_CIERRE = re.compile(r"\b(al final|finalmente|termin[oó]|resuelto|ganamos|derrot[aé]|complet[oa])\b", re.I)
_INICIO = re.compile(r"\b(vamos a|objetivo|intentar|empezamos|primero|hay que)\b", re.I)


def _texto(linea_tiempo):
    return " ".join(str(x.get("texto", "")) for x in linea_tiempo if x.get("tipo") == "habla")


def construir_contexto_juego(video_path, contexto_usuario, linea_tiempo, eventos_visuales=None):
    """Infere contexto solo si hay evidencia repetida; de otro modo es incierto."""
    fuentes = " ".join((os.path.basename(video_path or ""), contexto_usuario or "", _texto(linea_tiempo)))
    bajo = fuentes.lower()
    coincidencias = [(clave, bajo.count(clave)) for clave in _JUEGOS if clave in bajo]
    coincidencias.sort(key=lambda x: x[1], reverse=True)
    if coincidencias:
        clave, cantidad = coincidencias[0]
        juego, franquicia = _JUEGOS[clave]
        confianza = min(0.95, 0.45 + 0.15 * cantidad + (0.15 if clave in (contexto_usuario or "").lower() else 0))
    else:
        juego, franquicia, confianza = "desconocido", "desconocida", 0.0
    eventos = [nombre for nombre, patron in _EVENTOS.items() if re.search(patron, bajo, re.I)]
    situacion = eventos[0] if eventos else "incierta"
    objetivo = "incierto"
    objetivo_match = re.search(r"(?:objetivo|vamos a|hay que|intentamos)\s+([^.!?]{3,100})", fuentes, re.I)
    if objetivo_match:
        objetivo = objetivo_match.group(1).strip()
    return {
        "version": 1,
        "juego": juego,
        "franquicia": franquicia,
        "tipo_contenido": "gaming" if linea_tiempo else "desconocido",
        "situacion": situacion,
        "objetivo_actual": objetivo,
        "confianza": round(confianza, 2),
        "evidencia": {"contexto_usuario": bool(contexto_usuario), "eventos_textuales": eventos, "eventos_visuales": len(eventos_visuales or [])},
    }


def clasificar_segmentos(linea_tiempo, arcos):
    """Conserva silencios: solo etiqueta irrelevante cuando carece de señal."""
    resultado = []
    for item in linea_tiempo:
        inicio, fin = float(item["inicio"]), float(item["fin"])
        texto = str(item.get("texto", ""))
        arco = next((a for a in arcos if a["inicio"] <= inicio <= a["fin"]), None)
        if item.get("tipo") != "habla":
            etiqueta = "SILENCIO_NARRATIVO" if arco else "TRANSICION"
        elif _COMICO.search(texto):
            etiqueta = "COMICO"
        elif arco and any(re.search(_EVENTOS[e], texto, re.I) for e in _EVENTOS):
            etiqueta = "RELEVANTE"
        elif arco:
            etiqueta = "CONTEXTO"
        else:
            etiqueta = "IRRELEVANTE"
        resultado.append({"inicio": inicio, "fin": fin, "clasificacion": etiqueta})
    return resultado


def construir_arcos(unidades, candidatos, contexto_juego, linea_tiempo):
    """Descubre arcos desde la evidencia temporal, no solo desde candidatos.

    Los candidatos del LLM aportan evidencia editorial, pero no son requisito:
    así una historia puede descubrirse aunque ningún momento individual haya
    sido marcado previamente. Cada arco queda confinado a una unidad narrativa.
    """
    arcos = []
    candidatos = candidatos or []
    for unidad in unidades:
        uid = f"unidad_{unidad['id']}"
        inicio, fin = float(unidad["inicio"]), float(unidad["fin"])
        asociados = [c for c in candidatos if c.get("unidad_narrativa") == uid]
        evidencia_linea = [
            x for x in linea_tiempo
            if float(x.get("fin", 0)) > inicio and float(x.get("inicio", 0)) < fin
        ]
        texto_linea = " ".join(str(x.get("texto", "")) for x in evidencia_linea if x.get("tipo") == "habla")
        texto_candidatos = " ".join(f"{c.get('titulo', '')} {c.get('razon', '')}" for c in asociados)
        texto = f"{texto_linea} {texto_candidatos}".strip()
        eventos = [nombre for nombre, patron in _EVENTOS.items() if re.search(patron, texto, re.I)]
        cierres = bool(_CIERRE.search(texto))
        inicios = bool(_INICIO.search(texto))
        pausas = sum(1 for a, b in zip(evidencia_linea, evidencia_linea[1:])
                     if float(b.get("inicio", 0)) - float(a.get("fin", 0)) >= 2.0)
        senal = len(eventos) + (1 if cierres else 0) + (1 if inicios else 0) + min(2, pausas)
        # Sin candidatos previos, exigimos evidencia real de cambio narrativo.
        if not asociados and senal < 2:
            continue
        completo = bool(inicios and cierres)
        arcos.append({
            "id": f"arco_{unidad['id']}", "unidad_narrativa": uid,
            "juego": contexto_juego["juego"], "situacion": eventos[0] if eventos else contexto_juego["situacion"],
            "objetivo": contexto_juego["objetivo_actual"], "inicio": inicio, "fin": fin,
            "descripcion": texto[:500], "eventos_clave": eventos,
            "evidencia_temporal": {"lineas": len(evidencia_linea), "pausas": pausas, "candidatos_asociados": len(asociados)},
            "importancia": round(min(1.0, 0.25 + 0.10 * len(eventos) + 0.12 * completo + 0.04 * min(3, pausas)), 2),
            "confianza": contexto_juego["confianza"], "historia_completa": completo,
        })
    return arcos


def _valor_editorial(candidato):
    """Normaliza la evaluacion editorial opcional devuelta por el LLM."""
    valor = candidato.get("valor_editorial", {})
    if not isinstance(valor, dict):
        return {}
    out = {}
    for clave in ("impacto", "hook", "payoff", "autonomia", "contexto_suficiente", "sorpresa", "reaccion", "humor", "habilidad", "descubrimiento", "consecuencia", "watchability", "repeticion", "rutina", "contexto_excesivo"):
        try:
            if clave in valor:
                out[clave] = max(0.0, min(1.0, float(valor[clave])))
        except (TypeError, ValueError):
            pass
    return out


def puntuar_valor_editorial(candidato):
    """Calcula una señal editorial 0-100 sin inventar evidencia."""
    v = _valor_editorial(candidato)
    if not v:
        return None
    positivos = [v[k] for k in ("impacto", "hook", "payoff", "autonomia", "sorpresa", "reaccion", "humor", "habilidad", "descubrimiento", "consecuencia", "watchability") if k in v]
    negativos = [v[k] for k in ("repeticion", "rutina", "contexto_excesivo") if k in v]
    if not positivos:
        return None
    base = sum(positivos) / len(positivos)
    penal = sum(negativos) / len(negativos) if negativos else 0.0
    return round(max(0.0, min(100.0, (base * 100.0) - penal * 30.0)), 1)


def anotar_narrativa(candidato, arcos, clasificaciones):
    """Aporta explicabilidad y penalizaciones; nunca modifica los segmentos."""
    inicio, fin = float(candidato["inicio"]), float(candidato["fin"])
    arco = next((a for a in arcos if a["inicio"] <= inicio and fin <= a["fin"]), None)
    etiquetas = [x["clasificacion"] for x in clasificaciones if x["fin"] > inicio and x["inicio"] < fin]
    conteo = Counter(etiquetas)
    total = max(1, sum(conteo.values()))
    texto = f"{candidato.get('titulo', '')} {candidato.get('razon', '')}"
    comic = bool(_COMICO.search(texto)) or conteo["COMICO"] > 0
    relevancia = (conteo["RELEVANTE"] + conteo["CONTEXTO"] + conteo["COMICO"]) / total
    completitud = 0.25 + 0.25 * bool(arco) + 0.25 * bool(_CIERRE.search(texto)) + 0.25 * bool(_INICIO.search(texto))
    editorial = _valor_editorial(candidato)
    editorial_score = puntuar_valor_editorial(candidato)
    return {
        "arco_narrativo": arco["id"] if arco else None,
        "valor_editorial": editorial,
        "score_editorial": editorial_score,
        "rol_narrativo": "historia_principal" if arco and candidato.get("tipo") == "completo" else ("momento_comico" if comic else "momento_secundario"),
        "comic_interlude": comic and bool(arco),
        "segmentos_narrativos": etiquetas,
        "narrativa": {
            "narrative_completeness": round(completitud, 2),
            "story_importance": arco["importancia"] if arco else 0.2,
            "game_context_relevance": arco["confianza"] if arco else 0.0,
            "context_clarity": round(relevancia, 2),
            "pacing": round(relevancia, 2),
            "comic_value": 0.75 if comic else 0.0,
            "irrelevant_content": round(conteo["IRRELEVANTE"] / total, 2),
            "weak_context": 0.0 if arco else 0.5,
            "abrupt_cut": 0.0 if _CIERRE.search(texto) else 0.25,
        },
    }


def _duracion_segmentos(segmentos):
    return sum(max(0.0, float(s["fin"]) - float(s["inicio"])) for s in segmentos)


def normalizar_segmentos_sin_duplicados(segmentos, tolerancia=0.35, duracion_minima=0.05):
    """Devuelve segmentos cronológicos sin repetir material de video.

    Los solapes, contenidos y copias temporalmente casi idénticas describen el
    mismo material y se representan por una sola unión. Los intervalos sin
    solape se conservan aunque estén muy cerca: pueden ser saltos narrativos
    deliberados. Si dos entradas declaran explícitamente el mismo ``evento_id``
    o ``id_narrativo``, se conserva la primera aun cuando estén separadas.
    """
    limpios = []
    vistos_semanticos = set()
    for segmento in segmentos or []:
        if not isinstance(segmento, dict):
            continue
        try:
            inicio, fin = float(segmento["inicio"]), float(segmento["fin"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(inicio) or not math.isfinite(fin) or inicio < 0 or fin - inicio <= duracion_minima:
            continue
        clave = segmento.get("evento_id", segmento.get("id_narrativo"))
        if clave not in (None, ""):
            # Un evento puede contener setup, reacción y resolución distintos.
            clave = (str(clave), str(segmento.get("rol_narrativo", segmento.get("tipo", ""))), str(segmento.get("fase", "")))
            if clave in vistos_semanticos:
                continue
            vistos_semanticos.add(clave)
        copia = dict(segmento)
        copia["inicio"], copia["fin"] = round(inicio, 3), round(fin, 3)
        limpios.append(copia)
    limpios.sort(key=lambda s: (s["inicio"], s["fin"]))
    normalizados = []
    for segmento in limpios:
        if not normalizados:
            normalizados.append(segmento)
            continue
        anterior = normalizados[-1]
        solapa = segmento["inicio"] <= anterior["fin"]
        contenido = segmento["inicio"] >= anterior["inicio"] and segmento["fin"] <= anterior["fin"]
        if solapa or contenido:
            anterior["inicio"] = min(anterior["inicio"], segmento["inicio"])
            anterior["fin"] = max(anterior["fin"], segmento["fin"])
        else:
            normalizados.append(segmento)
    return normalizados


def _en_rango(duracion, minimo, maximo):
    return (minimo == 0 or duracion >= minimo) and (maximo == 0 or duracion <= maximo)


def _compatible_para_unir_ventanas(anterior, actual, hueco_maximo=1.8):
    hueco = float(actual["inicio"]) - float(anterior["fin"])
    if hueco > hueco_maximo:
        return False
    if hueco < -0.05:
        return True
    la, lb = anterior.get("etiqueta"), actual.get("etiqueta")
    ea, eb = set(anterior.get("eventos", [])), set(actual.get("eventos", []))
    # Dos beats fuertes distintos no se fusionan solo porque ambos sean
    # RELEVANTE/COMICO. Solo se unen si comparten evento o si uno carece de
    # una señal concreta.
    if ea and eb and la not in {"CONTEXTO", "SILENCIO_NARRATIVO"} and lb not in {"CONTEXTO", "SILENCIO_NARRATIVO"}:
        return bool(ea & eb)
    if la == lb or la in {"CONTEXTO", "SILENCIO_NARRATIVO"} or lb in {"CONTEXTO", "SILENCIO_NARRATIVO"}:
        return True
    return not ea or not eb or bool(ea & eb)


def _score_ventana(v):
    """Score used for pruning windows when duration exceeds max.
    Mirrors the logic in _seleccionar_ventanas (valor) but exposed for reuse.
    """
    score = float(v.get("prioridad", 1))
    score += 5.0 * len(v.get("eventos", []))
    score += 4.0 if v.get("hook") else 0.0
    score += 5.0 if v.get("giro") else 0.0
    score += 5.0 if v.get("reaccion") else 0.0
    score += 8.0 if v.get("cierre") else 0.0
    score += 3.0 if v.get("consecuencia") else 0.0
    if v.get("etiqueta") == "COMICO":
        score += 4.0
    if v.get("etiqueta") == "SILENCIO_NARRATIVO":
        score += 2.0
    if v.get("etiqueta") == "CONTEXTO":
        score -= 4.0
    return score
def _consolidar_ventanas_narrativas(ventanas):
    """Fusiona ventanas contiguas cuando el hueco es pequeño o comparten eventos.
    Preserva orden cronológico y mantiene la información de eventos, cue, hook,
    reaccion, giro, consecuencia y prioridad.
    """
    if not ventanas:
        return []
    ordenadas = sorted(ventanas, key=lambda v: (v["inicio"], v["fin"]))
    salida = [dict(ordenadas[0])]
    prioridad_map = {"RELEVANTE": 5, "COMICO": 4, "SILENCIO_NARRATIVO": 3, "CONTEXTO": 2}
    for actual in ordenadas[1:]:
        anterior = salida[-1]
        if _compatible_para_unir_ventanas(anterior, actual):
            anterior["fin"] = max(float(anterior["fin"]), float(actual["fin"]))
            anterior["eventos"] = sorted(set(anterior.get("eventos", [])) | set(actual.get("eventos", [])))
            anterior["cierre"] = bool(anterior.get("cierre") or actual.get("cierre"))
            anterior["hook"] = bool(anterior.get("hook") or actual.get("hook"))
            anterior["reaccion"] = bool(anterior.get("reaccion") or actual.get("reaccion"))
            anterior["giro"] = bool(anterior.get("giro") or actual.get("giro"))
            anterior["consecuencia"] = bool(anterior.get("consecuencia") or actual.get("consecuencia"))
            anterior["texto"] = (str(anterior.get("texto", "")) + " " + str(actual.get("texto", ""))).strip()[:800]
            anterior["prioridad"] = max(int(anterior.get("prioridad", 1)), int(actual.get("prioridad", 1)))
            if prioridad_map.get(actual.get("etiqueta"), 1) > prioridad_map.get(anterior.get("etiqueta"), 1):
                anterior["etiqueta"] = actual.get("etiqueta")
        else:
            salida.append(dict(actual))
    return salida


def _ventanas_narrativas(arco, clasificaciones, linea_tiempo):
    """Convierte frases/eventos en ventanas conservables y ordenadas."""
    textos = {(float(x["inicio"]), float(x["fin"])): str(x.get("texto", "")) for x in linea_tiempo}
    ventanas = []
    for item in clasificaciones:
        inicio, fin = float(item["inicio"]), float(item["fin"])
        if inicio < arco["inicio"] or fin > arco["fin"]:
            continue
        etiqueta = item["clasificacion"]
        if etiqueta in {"IRRELEVANTE", "TRANSICION"}:
            continue
        texto = textos.get((inicio, fin), "")
        eventos = [nombre for nombre, patron in _EVENTOS.items() if re.search(patron, texto, re.I)]
        cierre = bool(_CIERRE.search(texto))
        hook = bool(_INICIO.search(texto) or re.search(r"[?!]|(oye|mira|escucha|espera|no puede ser|qué pas[aó])\b", texto, re.I))
        reaccion = bool(_COMICO.search(texto) or re.search(r"\b(grito|grita|nooo|wtf|dios|incre[ií]ble|risa|jaj)\b", texto, re.I))
        giro = bool(re.search(r"\b(de repente|pero|resulta que|sin embargo|inesperado|fall[oó]|funcion[oó])\b", texto, re.I))
        consecuencia = bool(re.search(r"\b(entonces|por eso|así que|as[ií] que|despu[eé]s|resultado|termin[oó]|ganamos|perdimos)\b", texto, re.I))
        prioridad = {"RELEVANTE": 5, "COMICO": 4, "SILENCIO_NARRATIVO": 3, "CONTEXTO": 2}.get(etiqueta, 1)
        prioridad += len(eventos) + (3 if cierre else 0) + (2 if hook else 0) + (2 if reaccion else 0) + (2 if giro else 0) + (1 if consecuencia else 0)
        ventanas.append({"inicio": inicio, "fin": fin, "etiqueta": etiqueta, "texto": texto, "eventos": eventos, "cierre": cierre, "hook": hook, "reaccion": reaccion, "giro": giro, "consecuencia": consecuencia, "prioridad": prioridad})
    return _consolidar_ventanas_narrativas(ventanas)


def _seleccionar_ventanas(ventanas, minimo, maximo):
    """Selecciona beats con lógica editorial y restricciones de historia.

    No optimiza solo por score: intenta conservar hook/setup, desarrollo, giro,
    climax y payoff. Si existe una resolución, exige contexto seleccionado
    suficientemente cercano para que la resolución no quede huérfana.
    """
    if not ventanas:
        return []
    techo = float("inf") if maximo == 0 else float(maximo)
    referencia = maximo or max(minimo * 1.5, 90.0)
    max_segmentos = max(3, min(8, int(math.ceil(referencia / 14.0))))
    ordenadas = sorted(ventanas, key=lambda v: (v["inicio"], v["fin"]))

    def valor(v):
        score = float(v.get("prioridad", 1))
        score += 5.0 * len(v.get("eventos", []))
        score += 4.0 if v.get("hook") else 0.0
        score += 5.0 if v.get("giro") else 0.0
        score += 5.0 if v.get("reaccion") else 0.0
        score += 8.0 if v.get("cierre") else 0.0
        score += 3.0 if v.get("consecuencia") else 0.0
        if v.get("etiqueta") == "COMICO": score += 4.0
        if v.get("etiqueta") == "SILENCIO_NARRATIVO": score += 2.0
        if v.get("etiqueta") == "CONTEXTO": score -= 4.0
        return score

    elegidas, vistos = [], set()
    setup_candidates = [v for v in ordenadas[:min(5, len(ordenadas))] if v.get("hook") or v.get("eventos") or v.get("etiqueta") != "CONTEXTO"]
    if setup_candidates:
        setup = max(setup_candidates, key=valor)
        if _duracion_segmentos([setup]) <= techo:
            elegidas.append(setup); vistos.update(setup.get("eventos", []))

    cierres = [v for v in ordenadas if v.get("cierre") or v.get("consecuencia")]
    cierre = max(cierres, key=valor) if cierres else None
    if cierre is not None and cierre not in elegidas and _duracion_segmentos(elegidas + [cierre]) <= techo:
        elegidas.append(cierre); vistos.update(cierre.get("eventos", []))

    restantes = [v for v in ordenadas if v not in elegidas]
    restantes.sort(key=lambda v: (len(set(v.get("eventos", [])) - vistos), valor(v)), reverse=True)
    for ventana in restantes:
        if len(elegidas) >= max_segmentos:
            break
        if _duracion_segmentos(elegidas + [ventana]) > techo:
            continue
        nuevos = set(ventana.get("eventos", [])) - vistos
        if ventana.get("etiqueta") == "CONTEXTO" and not nuevos and _duracion_segmentos(elegidas) >= minimo:
            continue
        if nuevos or ventana.get("hook") or ventana.get("giro") or ventana.get("reaccion") or ventana.get("consecuencia") or ventana.get("etiqueta") in {"COMICO", "RELEVANTE", "SILENCIO_NARRATIVO"}:
            elegidas.append(ventana); vistos.update(ventana.get("eventos", []))

    while minimo and _duracion_segmentos(elegidas) < minimo:
        extras = [v for v in restantes if v not in elegidas and _duracion_segmentos(elegidas + [v]) <= techo]
        if not extras:
            break
        siguiente = max(extras, key=lambda v: (valor(v), len(set(v.get("eventos", [])) - vistos)))
        elegidas.append(siguiente); vistos.update(siguiente.get("eventos", []))

    elegidas = sorted(elegidas, key=lambda v: v["inicio"])
    # Ensure total duration does not exceed maximo. If it does, prune optional windows
    # preserving editorial essentials (hook, giro, reaccion, cierre).
    if maximo:
        total = _duracion_segmentos(elegidas)
        if total > maximo:
            mandatory = [v for v in elegidas if v.get("hook") or v.get("giro") or v.get("reaccion") or v.get("cierre")]
            optional = [v for v in elegidas if v not in mandatory]
            # Sort optional by ascending score (least valuable first)
            optional.sort(key=_score_ventana)
            while total > maximo and optional:
                v = optional.pop(0)
                if v in elegidas:
                    elegidas.remove(v)
                total = _duracion_segmentos(elegidas)
            if total > maximo:
                # Cannot satisfy max constraint even after removing all optional windows
                return []
            # Recombine mandatory with any remaining optional and sort again
            elegidas = sorted(mandatory + optional, key=lambda v: v["inicio"])
    # Una resolución alejada sin puente narrativo produce una historia rota.
    if cierre is not None and cierre in elegidas:
        anteriores = [v for v in elegidas if v["fin"] <= cierre["inicio"]]
        if anteriores:
            ventana_contexto = max(45.0, min(90.0, (minimo or 60) * 1.5))
            if max(v["fin"] for v in anteriores) < cierre["inicio"] - ventana_contexto:
                return []
        elif cierre["inicio"] - ordenadas[0]["inicio"] > 30.0:
            return []
    return elegidas


def preparar_momento_independiente(candidato, clasificaciones, minimo, maximo):
    """Construye un momento autónomo y solo añade el contexto mínimo útil."""
    resultado = dict(candidato)
    resultado["tipo_candidato"] = "independiente"
    tenia_segmentos = bool(resultado.get("segmentos"))
    segmentos = [dict(s) for s in (resultado.get("segmentos") or [{"inicio": resultado["inicio"], "fin": resultado["fin"]}])]
    duracion = _duracion_segmentos(segmentos)
    if maximo and duracion > maximo:
        return None
    if minimo and duracion < minimo:
        inicio0, fin0 = float(resultado["inicio"]), float(resultado["fin"])
        candidatos_contexto = []
        for x in clasificaciones:
            if x.get("clasificacion") not in {"RELEVANTE", "CONTEXTO", "COMICO", "SILENCIO_NARRATIVO"}:
                continue
            xi, xf = float(x["inicio"]), float(x["fin"])
            if xf < inicio0 - 10 or xi > fin0 + 10:
                continue
            texto = str(x.get("texto", ""))
            antes = xf <= inicio0 + 0.25
            despues = xi >= fin0 - 0.25
            señal = 0
            señal += 5 if x.get("clasificacion") in {"RELEVANTE", "COMICO"} else 1
            señal += 3 if re.search(r"\b(antes|primero|vamos a|mira|oye|hay que|porque|por qu[eé])\b", texto, re.I) else 0
            señal += 4 if re.search(r"\b(grito|risa|jaj|nooo|wtf|reacci[oó]n|incre[ií]ble)\b", texto, re.I) else 0
            señal += 3 if re.search(r"\b(al final|finalmente|resultado|termin[oó]|ganamos|perdimos|fall[oó])\b", texto, re.I) else 0
            if antes: señal += 3
            if despues: señal += 4
            distancia = min(abs(xf - inicio0), abs(xi - fin0))
            candidatos_contexto.append((señal, -distancia, x))
        for _, _, x in sorted(candidatos_contexto, key=lambda t: (t[0], t[1]), reverse=True):
            segmento = {"inicio": round(float(x["inicio"]), 2), "fin": round(float(x["fin"]), 2)}
            nueva = _duracion_segmentos(segmentos + [segmento])
            if segmento in segmentos or nueva > (maximo or float("inf")):
                continue
            segmentos.append(segmento)
            if nueva >= minimo:
                break
    segmentos = normalizar_segmentos_sin_duplicados(segmentos)
    duracion = _duracion_segmentos(segmentos)
    if not _en_rango(duracion, minimo, maximo):
        return None
    if tenia_segmentos or len(segmentos) > 1:
        resultado["segmentos"] = segmentos
    else:
        resultado.pop("segmentos", None)
    resultado["inicio"], resultado["fin"] = segmentos[0]["inicio"], segmentos[-1]["fin"]
    resultado["duracion"] = round(duracion, 2)
    resultado["momentos_narrativos"] = [{"tipo": "momento_independiente", **s} for s in segmentos]
    resultado["duracion_final"] = resultado["duracion"]
    return resultado


def comprimir_arco_narrativo(arco, clasificaciones, linea_tiempo, minimo, maximo, continuidad_visual=0.5):
    """Construye una historia multi-segmento dentro del rango configurado.

    La selección usa solo ventanas ya clasificadas del propio arco. Los cortes
    corresponden al inicio/final de una frase, evento o silencio narrativo.
    """
    ventanas = _ventanas_narrativas(arco, clasificaciones, linea_tiempo)
    ventanas_utiles = [v for v in ventanas if v.get("etiqueta") != "CONTEXTO" or v.get("hook") or v.get("consecuencia")]
    if len(ventanas_utiles) < 2:
        return None
    elegidas = _seleccionar_ventanas(ventanas, minimo, maximo)
    # Si el arco contenía una resolución explícita pero no cabe junto con su
    # contexto, no se vende como historia completa: el caller puede conservar
    # un sub-arco o descartarlo.
    if any(v["cierre"] for v in ventanas) and not any(v["cierre"] for v in elegidas):
        return None
    segmentos = normalizar_segmentos_sin_duplicados(
        [{"inicio": round(v["inicio"], 2), "fin": round(v["fin"], 2)} for v in elegidas]
    )
    duracion = _duracion_segmentos(segmentos)
    if not segmentos or not _en_rango(duracion, minimo, maximo):
        return None
    eventos = sorted({e for v in elegidas for e in v["eventos"]})
    eliminados = [{"inicio": round(v["inicio"], 2), "fin": round(v["fin"], 2), "motivo": v["etiqueta"]} for v in ventanas if v not in elegidas]
    original = max(0.0, float(arco["fin"]) - float(arco["inicio"]))
    cambios = max(0, len(segmentos) - 1)
    return {
        "tipo": "completo", "tipo_candidato": "historia", "titulo": f"{arco.get('situacion', 'Historia')} resumida"[:60],
        "razon": f"Arco comprimido: {arco.get('objetivo', 'objetivo narrativo')}",
        "inicio": segmentos[0]["inicio"], "fin": segmentos[-1]["fin"], "segmentos": segmentos,
        "duracion": round(duracion, 2), "duracion_final": round(duracion, 2),
        "arco_narrativo": arco["id"], "unidad_narrativa": arco["unidad_narrativa"],
        "rol_narrativo": "historia_principal", "momentos_narrativos": elegidas,
        "segmentos_eliminados": eliminados,
        "duracion_original_arco": round(original, 2), "ratio_compresion": round(duracion / original, 3) if original else 1.0,
        "cobertura_eventos": {"eventos": eventos, "cantidad": len(eventos)},
        "densidad_cambios": round(cambios / duracion * 5, 3) if duracion else 0.0,
        "metricas_segmentacion": {
            "numero_segmentos": len(segmentos),
            "duracion_promedio_segmento": round(duracion / len(segmentos), 2) if segmentos else 0.0,
            "segmentos_menores_1_5s": sum(1 for s in segmentos if float(s["fin"]) - float(s["inicio"]) < 1.5),
            "segmentos_menores_3s": sum(1 for s in segmentos if float(s["fin"]) - float(s["inicio"]) < 3.0),
            "cortes_por_minuto": round(cambios / max(duracion, 1.0) * 60, 2),
        },
        "continuidad_visual": round(float(continuidad_visual), 2),
        "puntos_corte": [{"tiempo": s["inicio"], "motivo": "inicio_frase_evento"} for s in segmentos] + [{"tiempo": segmentos[-1]["fin"], "motivo": "fin_frase_evento"}],
        "compresion_narrativa": {"conserva_silencios_narrativos": any(v["etiqueta"] == "SILENCIO_NARRATIVO" for v in elegidas), "eventos_diversos": len(eventos), "resolucion": any(v["cierre"] for v in elegidas)},
    }
