"""Scoring determinista de candidatos para MKClips - Fase 4.
No reemplaza al LLM: aporta una señal medible para comparar candidatos y
para calibrar posteriormente con resultados_reales.json.
"""

import re

try:
    from ranker_editorial_mkclips import puntuar_ranker_local
except Exception:
    puntuar_ranker_local = None

PESOS = {
    "reaccion_fuerte": 30,
    "punchline_reaccion": 25,
    "gameplay": 20,
    "contexto": 15,
    "interaccion": 10,
    "sorpresa": 10,
    # Senal complementaria: un cambio visual no debe dominar la narrativa.
    "visual": 8,
    "duracion_exceso": -20,
    "silencio_repeticion": -15,
    "repeticion": -10,
}

# Pesos visibles para la segunda capa. La señal clásica sigue siendo la base;
# estas señales nunca convierten un candidato sin historia en buen clip.
PESOS_NARRATIVA = {
    "narrative_completeness": 18,
    "story_importance": 14,
    "game_context_relevance": 10,
    "context_clarity": 10,
    "pacing": 10,
    "comic_value": 6,
    "irrelevant_content": -14,
    "weak_context": -8,
    "abrupt_cut": -8,
    "event_coverage": 12,
    "resolution": 10,
    "compression_efficiency": 8,
    "change_density": 6,
    "visual_continuity": 6,
    "redundancy": -10,
    "unnecessary_context": -8,
    "editorial_value": 18,
    "watchability": 14,
    "hook": 10,
    "payoff": 12,
    "standalone": 10,
    "routine": -12,
    "editorial_repetition": -12,
    "editorial_grounding": 8,
    "ungrounded_editorial": -10,
}

_REACCION = re.compile(r"\b(grito|grita|gritar|risa|risas|jaj|lol|wtf|no puede|dios|qué|que|incre[ií]ble|brutal|nooo|vamos|clutch|epic|caos|desastre|fail|muere|murió|ganamos|perdimos)\b", re.I)
_GAMEPLAY = re.compile(r"\b(ataque|atacar|mazo|carta|torre|mago|bola de fuego|tesla|renacuajo|partida|jugada|daño|victoria|derrota|ganar|perder|clonar|clon|caballero|globo|estrategia)\b", re.I)
_INTERACCION = re.compile(r"\b(te dije|mira|oye|escucha|vamos a|hay que|p[eé]gale|dime|qué haces|por qué|porque|juntos|nosotros|ellos|ustedes)\b", re.I)
_SORPRESA = re.compile(r"\b(de repente|sorpresa|inesperado|no esperaba|resulta que|terminó|acabó|fall[oó]|fallamos|funcionó|funciono|no dio|qué pasó|que paso)\b", re.I)
_NARRATIVA = re.compile(r"\b(primero|después|luego|entonces|al final|finalmente|termina|terminó|resultado|decidimos|decide|vamos a probar|intentamos|probamos|historia|anécdota|anecdota)\b", re.I)
_HOOK = re.compile(r"[?!]|\b(oye|mira|espera|escucha|atenci[oó]n|vamos a|no puede ser|qu[eé]|c[oó]mo|como|por qu[eé]|porque)\b", re.I)
_PAYOFF = re.compile(r"\b(al final|finalmente|resultado|termin[oó]|acab[oó]|ganamos|perdimos|fall[oó]|funcion[oó]|lo logramos|no puede ser|era esto|entonces)\b", re.I)
_REACCION_REAL = re.compile(r"\b(grito|grita|gritar|risa|risas|jaj|nooo|wtf|dios|incre[ií]ble|brutal|caos|fail|susto|madre)\b", re.I)
_RUTINA = re.compile(r"\b(caminando|caminar|explorar|explorando|inventario|loot|farmeando|espera|esperando|cargando|viajando|buscando|recoger|recogiendo)\b", re.I)


def _texto_candidato(c):
    return f"{c.get('titulo', '')} {c.get('razon', '')}".strip()


def _duracion(c):
    segmentos = c.get("segmentos")
    if isinstance(segmentos, list) and len(segmentos) > 1:
        return sum(
            max(0.0, float(segmento["fin"]) - float(segmento["inicio"]))
            for segmento in segmentos
            if isinstance(segmento, dict)
        )
    return max(0.0, float(c.get("fin", 0)) - float(c.get("inicio", 0)))


def _solape(a, b):
    segmentos = a.get("segmentos")
    intervalos_a = segmentos if isinstance(segmentos, list) and len(segmentos) > 1 else [a]
    return sum(
        max(0.0, min(float(intervalo["fin"]), float(b["fin"])) - max(float(intervalo["inicio"]), float(b["inicio"])))
        for intervalo in intervalos_a
        if isinstance(intervalo, dict)
    )


def _editorial_evidencia(candidato, linea_tiempo):
    """Extrae señales editoriales de la evidencia real, no del título generado."""
    if not linea_tiempo:
        return {}
    inicio = float(candidato.get("inicio", 0.0)); fin = float(candidato.get("fin", inicio))
    dur = max(0.0, fin - inicio)
    segmentos = candidato.get("segmentos") if isinstance(candidato.get("segmentos"), list) else None
    intervalos = segmentos or [{"inicio": inicio, "fin": fin}]
    items = [x for x in linea_tiempo if any(float(x.get("fin", 0)) > float(seg["inicio"]) and float(x.get("inicio", 0)) < float(seg["fin"]) for seg in intervalos)]
    habla = [x for x in items if x.get("tipo") == "habla"]
    texto = " ".join(str(x.get("texto", "")) for x in habla)
    inicio_lim = inicio + min(10.0, max(4.0, dur * 0.18))
    final_lim = fin - min(12.0, max(5.0, dur * 0.22))
    inicio_items = [x for x in habla if float(x.get("inicio", 0)) <= inicio_lim]
    final_items = [x for x in habla if float(x.get("fin", 0)) >= final_lim]
    hook = 1.0 if any(_HOOK.search(str(x.get("texto", ""))) for x in inicio_items) else 0.0
    payoff = 1.0 if any(_PAYOFF.search(str(x.get("texto", ""))) for x in final_items) else 0.0
    reaccion = 1.0 if any(_REACCION_REAL.search(str(x.get("texto", ""))) for x in final_items) else 0.0
    rutina = 1.0 if dur >= 35 and _RUTINA.search(texto) and not (_PAYOFF.search(texto) or _REACCION_REAL.search(texto)) else 0.0
    cobertura = sum(max(0.0, min(float(x.get("fin", 0)), fin) - max(float(x.get("inicio", 0)), inicio)) for x in habla)
    senales = sum(1 for x in habla if _HOOK.search(str(x.get("texto", ""))) or _PAYOFF.search(str(x.get("texto", ""))) or _REACCION_REAL.search(str(x.get("texto", ""))))
    densidad = senales / max(dur / 30.0, 1.0)
    return {"hook_evidencia": hook, "payoff_evidencia": payoff, "reaccion_evidencia": reaccion, "rutina_evidencia": rutina, "cobertura_habla": round(min(1.0, cobertura / max(dur, 1.0)), 3), "densidad_senales": round(min(1.0, densidad / 2.0), 3)}


def calcular_score(candidato, linea_tiempo=None, eventos_audio=None, eventos_visuales=None,
                   contexto_juego=None, preferencias=None):
    texto = _texto_candidato(candidato)
    dur = _duracion(candidato)
    puntos = {k: 0 for k in PESOS}

    if eventos_audio:
        max_audio = max((_solape(candidato, e) for e in eventos_audio), default=0.0)
        if max_audio >= 1.0:
            puntos["reaccion_fuerte"] = PESOS["reaccion_fuerte"]
        elif max_audio > 0:
            puntos["reaccion_fuerte"] = 15

    if _REACCION.search(texto):
        puntos["punchline_reaccion"] = PESOS["punchline_reaccion"]
    if _GAMEPLAY.search(texto):
        puntos["gameplay"] = PESOS["gameplay"]
    if len(texto.split()) >= 8 or _NARRATIVA.search(texto):
        puntos["contexto"] = PESOS["contexto"]
    if _INTERACCION.search(texto):
        puntos["interaccion"] = PESOS["interaccion"]
    if _SORPRESA.search(texto):
        puntos["sorpresa"] = PESOS["sorpresa"]

    # La asociacion se hace previamente con detecciones reales; nunca se
    # generan eventos visuales a partir del candidato.
    visuales_asociados = candidato.get("eventos_visuales", [])
    if isinstance(visuales_asociados, list) and visuales_asociados:
        confianzas = []
        for evento in visuales_asociados:
            if isinstance(evento, dict):
                try:
                    confianzas.append(max(0.0, min(1.0, float(evento.get("confianza", 0.0)))))
                except (TypeError, ValueError):
                    continue
        confianza_media = sum(confianzas) / len(confianzas) if confianzas else 0.0
        # Una senal aporta hasta 4 puntos; dos o mas, hasta el maximo de 8.
        puntos["visual"] = int(round(
            PESOS["visual"] * min(1.0, len(visuales_asociados) / 2.0) * confianza_media
        ))

    # Duración variable: no hay un máximo rígido, pero un clip muy largo
    # necesita una justificación narrativa clara para no dominar el ranking.
    if dur > 180 and not _NARRATIVA.search(texto):
        puntos["duracion_exceso"] = PESOS["duracion_exceso"]
    elif dur > 120 and not _NARRATIVA.search(texto):
        puntos["duracion_exceso"] = -10

    # Señal simple de repetición en el propio texto descriptivo.
    palabras = [w.lower() for w in re.findall(r"[a-záéíóúüñ]{4,}", texto, re.I)]
    if palabras:
        repetidas = len(palabras) - len(set(palabras))
        if repetidas >= 3:
            puntos["repeticion"] = PESOS["repeticion"]

    # Cobertura de habla: un candidato con muy poca transcripción útil
    # recibe una penalización pequeña, sin tratar los silencios como fallo.
    if linea_tiempo:
        habla = [x for x in linea_tiempo if x.get("tipo") == "habla" and _solape(candidato, x) > 0]
        cobertura = sum(_solape(candidato, x) for x in habla)
        if dur >= 40 and cobertura / max(dur, 1.0) < 0.18:
            puntos["silencio_repeticion"] = PESOS["silencio_repeticion"]

    score_base_bruto = 50 + sum(puntos.values())
    score_base = max(0, min(100, score_base_bruto))
    narrativa = candidato.get("narrativa", {}) if isinstance(candidato.get("narrativa"), dict) else {}
    compresion = candidato.get("compresion_narrativa", {}) if isinstance(candidato.get("compresion_narrativa"), dict) else {}
    cobertura = candidato.get("cobertura_eventos", {}) if isinstance(candidato.get("cobertura_eventos"), dict) else {}
    narrativa = dict(narrativa)
    evidencia_editorial = _editorial_evidencia(candidato, linea_tiempo)
    narrativa.update({
        "hook": max(float(narrativa.get("hook", 0.0)), evidencia_editorial.get("hook_evidencia", 0.0)),
        "payoff": max(float(narrativa.get("payoff", 0.0)), evidencia_editorial.get("payoff_evidencia", 0.0)),
        "routine": max(float(narrativa.get("routine", 0.0)), evidencia_editorial.get("rutina_evidencia", 0.0)),
        "watchability": max(float(narrativa.get("watchability", 0.0)), evidencia_editorial.get("densidad_senales", 0.0) * 0.7),
        "context_clarity": max(float(narrativa.get("context_clarity", 0.0)), evidencia_editorial.get("cobertura_habla", 0.0)),
    })
    editorial = candidato.get("valor_editorial", {}) if isinstance(candidato.get("valor_editorial"), dict) else {}
    if editorial:
        def ev(key, default=0.0):
            try:
                return max(0.0, min(1.0, float(editorial.get(key, default))))
            except (TypeError, ValueError):
                return default
        grounding = (
            evidencia_editorial.get("hook_evidencia", 0.0) +
            evidencia_editorial.get("payoff_evidencia", 0.0) +
            evidencia_editorial.get("reaccion_evidencia", 0.0) +
            evidencia_editorial.get("cobertura_habla", 0.0)
        ) / 4.0
        claimed = (ev("hook") + ev("payoff") + ev("watchability", ev("impacto")) + ev("autonomia", ev("contexto_suficiente"))) / 4.0
        unsupported = max(0.0, claimed - (0.30 + 0.70 * grounding))
        narrativa.update({
            # El LLM aporta criterio editorial; la evidencia real limita cuánto
            # puede pesar una afirmación que no esté respaldada temporalmente.
            "editorial_value": ev("impacto"),
            "watchability": 0.55 * ev("watchability", ev("impacto")) + 0.45 * evidencia_editorial.get("densidad_senales", 0.0),
            "hook": 0.55 * ev("hook") + 0.45 * evidencia_editorial.get("hook_evidencia", 0.0),
            "payoff": 0.55 * ev("payoff") + 0.45 * max(evidencia_editorial.get("payoff_evidencia", 0.0), evidencia_editorial.get("reaccion_evidencia", 0.0)),
            "standalone": ev("autonomia", ev("contexto_suficiente")),
            "routine": max(ev("rutina"), evidencia_editorial.get("rutina_evidencia", 0.0)),
            "editorial_repetition": ev("repeticion", ev("contexto_excesivo")),
            "editorial_grounding": grounding,
            "ungrounded_editorial": unsupported,
        })
    if candidato.get("tipo_candidato") == "historia":
        cantidad_segmentos = len(candidato.get("segmentos", []) or [])
        referencia_segmentos = max(3, min(8, round(dur / 12.0) if dur else 3))
        exceso_segmentos = max(0, cantidad_segmentos - referencia_segmentos)
        micro = sum(1 for seg in candidato.get("segmentos", []) if float(seg.get("fin", 0)) - float(seg.get("inicio", 0)) < 3.0) if cantidad_segmentos else 0
        redundancia_segmentacion = min(1.0, (exceso_segmentos / max(referencia_segmentos, 1)) * 0.7 + (micro / cantidad_segmentos) * 0.3)
        narrativa.update({
            "event_coverage": min(1.0, float(cobertura.get("cantidad", 0)) / 4.0),
            "resolution": 1.0 if compresion.get("resolucion") else 0.0,
            "compression_efficiency": 1.0 - min(1.0, float(candidato.get("ratio_compresion", 1.0))),
            "change_density": min(1.0, float(candidato.get("densidad_cambios", 0.0)) / 1.0),
            "visual_continuity": float(candidato.get("continuidad_visual", 0.0)),
            "redundancy": redundancia_segmentacion,
            "unnecessary_context": 0.0,
        })
    componentes_narrativos = {
        clave: round(PESOS_NARRATIVA[clave] * max(0.0, min(1.0, float(narrativa.get(clave, 0.0)))), 2)
        for clave in PESOS_NARRATIVA if PESOS_NARRATIVA[clave] > 0
    }
    componentes_narrativos.update({
        clave: round(PESOS_NARRATIVA[clave] * max(0.0, min(1.0, float(narrativa.get(clave, 0.0)))), 2)
        for clave in PESOS_NARRATIVA if PESOS_NARRATIVA[clave] < 0
    })
    score_intrinseco = max(0, min(100, round(score_base + sum(componentes_narrativos.values()))))
    try:
        from preferencias_mkclips import calcular_preferencia_usuario
        preferencia = calcular_preferencia_usuario(candidato, contexto_juego or {}, preferencias)
    except Exception:
        preferencia = {"score_preferencia_usuario": 0.0, "muestras": 0, "confianza": 0.0}

    ranker = {"score": 0.0, "confianza": 0.0, "muestras": 0, "activo": False}
    if puntuar_ranker_local is not None:
        try:
            ranker = puntuar_ranker_local(
                candidato,
                linea_tiempo=linea_tiempo,
                preferencias=preferencias,
            )
        except Exception:
            ranker = {"score": 0.0, "confianza": 0.0, "muestras": 0, "activo": False}

    # El ranker aprendido solo pesa cuando ya existe suficiente feedback.
    # No sustituye la lógica editorial ni contamina las primeras ejecuciones.
    aporte_ranker = 0.0
    if ranker.get("activo"):
        # Con pocas valoraciones el ranker aprende poco: su peso crece con la confianza.
        aporte_ranker = max(-8.0, min(8.0, float(ranker.get("score", 0.0)) * 8.0 * float(ranker.get("confianza", 1.0))))
    score_final = max(0, min(100, round(score_intrinseco + preferencia["score_preferencia_usuario"] + aporte_ranker)))
    # Puntaje SIN recortar a 100: con reaccion fuerte + remate + contexto casi todos los
    # clips llegan al tope y empatan. Este valor conserva la diferencia entre ellos y se
    # usa para desempatar al elegir y para ordenar la revision.
    score_bruto = round(score_base_bruto + sum(componentes_narrativos.values())
                        + preferencia["score_preferencia_usuario"] + aporte_ranker, 2)

    if dur < 60:
        clase = "corto"
    elif dur <= 150:
        clase = "medio"
    else:
        clase = "largo_narrativo" if _NARRATIVA.search(texto) else "largo_a_revisar"

    return {
        "score": int(score_final),
        "score_intrinseco": int(score_intrinseco),
        "score_preferencia_usuario": preferencia["score_preferencia_usuario"],
        "score_final": int(score_final),
        "score_bruto": score_bruto,
        "duracion": round(dur, 2),
        "clase_duracion": clase,
        "componentes": puntos,
        "componentes_narrativos": componentes_narrativos,
        "evidencia_editorial": evidencia_editorial,
        "preferencia": {"muestras": preferencia["muestras"], "confianza": preferencia["confianza"]},
        "ranker_local": ranker,
        "aporte_ranker_local": round(aporte_ranker, 2),
    }


def anotar_candidatos(candidatos, linea_tiempo=None, eventos_audio=None, eventos_visuales=None,
                      contexto_juego=None, preferencias=None):
    resultados = []
    for idx, c in enumerate(candidatos, start=1):
        r = calcular_score(
            c,
            linea_tiempo=linea_tiempo,
            eventos_audio=eventos_audio,
            eventos_visuales=eventos_visuales,
            contexto_juego=contexto_juego,
            preferencias=preferencias,
        )
        # El scoring es una anotación: no puede descartar el contrato del
        # candidato producido por Ollama (tipo, razón, unidad/ancla y futuros
        # segmentos compuestos). Esos campos los usa la selección posterior.
        anotado = dict(c)
        anotado["indice"] = idx
        anotado.update(r)
        resultados.append(anotado)
    return resultados
