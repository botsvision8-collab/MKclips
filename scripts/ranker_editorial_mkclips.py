"""Ranker editorial local para MKClips.

Aprende de las valoraciones existentes del usuario sin dependencias externas.
No reemplaza al LLM: aprende a ordenar candidatos parecidos a los que el
usuario ya ha aceptado o descartado. Se activa de forma conservadora tras
acumular suficientes ejemplos etiquetados.
"""
from __future__ import annotations

import math
import re

FEATURES = (
    "hook", "payoff", "reaccion", "sorpresa", "autonomia",
    "contexto_suficiente", "watchability", "humor", "habilidad",
    "descubrimiento", "consecuencia", "rutina", "repeticion",
    "contexto_excesivo", "densidad_cambios", "cobertura_eventos",
    "compresion", "duracion_normal", "es_historia", "es_independiente",
)

MIN_MUESTRAS = 12
MIN_CLASE = 4

_HOOK = re.compile(r"[?!]|\b(oye|mira|espera|escucha|atenci[oó]n|vamos a|no puede ser|qué|que|cómo|como|por qué|porque)\b", re.I)
_PAYOFF = re.compile(r"\b(al final|finalmente|resultado|termin[oó]|acab[oó]|ganamos|perdimos|fall[oó]|funcion[oó]|lo logramos|no puede ser)\b", re.I)
_REACCION = re.compile(r"\b(grito|grita|risa|risas|jaj|lol|wtf|nooo|dios|incre[ií]ble|brutal|susto|caos|fail)\b", re.I)
_RUTINA = re.compile(r"\b(caminando|caminar|explorar|explorando|inventario|loot|farmeando|espera|esperando|cargando|viajando|buscando|recoger|recogiendo)\b", re.I)


def _clamp(v, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _evidence(c, linea_tiempo):
    if not linea_tiempo:
        return {}
    ini = float(c.get('inicio', 0))
    fin = float(c.get('fin', ini))
    segs = c.get('segmentos') if isinstance(c.get('segmentos'), list) else [{"inicio": ini, "fin": fin}]
    items = [x for x in linea_tiempo if any(float(x.get('fin',0)) > float(s.get('inicio',0)) and float(x.get('inicio',0)) < float(s.get('fin',0)) for s in segs if isinstance(s,dict))]
    textos = [str(x.get('texto','')) for x in items if x.get('tipo') == 'habla']
    if not textos:
        return {}
    joined = ' '.join(textos)
    early = ' '.join(str(x.get('texto','')) for x in items if x.get('tipo') == 'habla' and float(x.get('inicio',0)) <= ini + min(10, max(4, (fin-ini)*0.2)))
    late = ' '.join(str(x.get('texto','')) for x in items if x.get('tipo') == 'habla' and float(x.get('fin',0)) >= fin - min(12, max(5, (fin-ini)*0.22)))
    return {
        'hook': 1.0 if _HOOK.search(early) else 0.0,
        'payoff': 1.0 if _PAYOFF.search(late) else 0.0,
        'reaccion': 1.0 if _REACCION.search(late) else 0.0,
        'rutina': _clamp(len(_RUTINA.findall(joined))/max(1,len(joined.split())/18)),
    }


def extraer_features(candidato, linea_tiempo=None):
    valor = candidato.get('valor_editorial') if isinstance(candidato.get('valor_editorial'), dict) else {}
    evidencia = candidato.get('evidencia_editorial') if isinstance(candidato.get('evidencia_editorial'), dict) else {}
    evidencia.update(_evidence(candidato, linea_tiempo or []))
    cobertura = candidato.get('cobertura_eventos') if isinstance(candidato.get('cobertura_eventos'), dict) else {}
    dur = max(0.0, float(candidato.get('duracion_final', candidato.get('duracion', float(candidato.get('fin',0))-float(candidato.get('inicio',0))))))
    feats = {k: 0.0 for k in FEATURES}
    for k in ('hook','payoff','reaccion','sorpresa','autonomia','contexto_suficiente','watchability','humor','habilidad','descubrimiento','consecuencia','rutina','repeticion','contexto_excesivo'):
        feats[k] = _clamp(valor.get(k, evidencia.get(k + '_evidencia', evidencia.get(k, 0.0))))
    feats['densidad_cambios'] = _clamp(float(candidato.get('densidad_cambios',0))/1.0)
    feats['cobertura_eventos'] = _clamp(float(cobertura.get('cantidad',0))/4.0)
    feats['compresion'] = 1.0 - _clamp(float(candidato.get('ratio_compresion',1.0))) if candidato.get('tipo_candidato') == 'historia' else 0.0
    feats['duracion_normal'] = math.exp(-((dur-75.0)/70.0)**2) if dur else 0.0
    feats['es_historia'] = 1.0 if candidato.get('tipo_candidato') == 'historia' else 0.0
    feats['es_independiente'] = 1.0 if candidato.get('tipo_candidato') == 'independiente' else 0.0
    return feats


# Descartar o puntuar bajo por estos motivos habla de un fallo del clip, no del gusto.
MOTIVOS_QUE_NO_ENSENAN = ('corte', 'tecnico')
MOTIVOS_CONTENIDO_NEGATIVO = ('contenido', 'aburrido', 'contexto', 'repetitivo')


def valor_de_feedback(feedback):
    """Etiqueta de una valoracion en [-1, +1]; None si no sirve para aprender.

    - Descartar por CONTENIDO (aburrido, falta de contexto, repetitivo o "contenido"): -1.
    - Estrellas: (n - 3) / 2 -> 1=-1, 3=0, 5=+1.
    - Mal corte o fallo tecnico (al descartar o con 1-2 estrellas): se ignora, no habla del gusto.
    - Descartes antiguos, de cuando aun no se preguntaba el motivo: se ignoran, porque
      pudieron ser por un fallo del clip y no por el momento.
    """
    motivo = feedback.get('motivo')
    if feedback.get('discarded') or feedback.get('descartado'):
        return -1.0 if motivo in MOTIVOS_CONTENIDO_NEGATIVO else None
    try:
        rating = int(feedback.get('rating') or 0)
    except (TypeError, ValueError):
        return None
    if rating <= 0:
        return None
    if rating <= 2 and motivo in MOTIVOS_QUE_NO_ENSENAN:
        return None
    return (min(5, rating) - 3) / 2.0


def _rating_value(feedback):  # nombre anterior, se conserva por compatibilidad
    return valor_de_feedback(feedback)


def _feedback_features(feedback):
    """Extrae las caracteristicas de la valoracion.

    Acepta tres formatos:
    - feedback guardado por ``guardar_feedback`` con ``features``;
    - feedback legado con ``valor_editorial``;
    - diccionarios de prueba/compatibilidad con los nombres de feature en raiz.
    """
    if not isinstance(feedback, dict):
        return None
    candidatos = [feedback.get('features'), feedback.get('valor_editorial'), feedback]
    for fuente in candidatos:
        if not isinstance(fuente, dict):
            continue
        valores = {k: _clamp(fuente.get(k, 0.0)) for k in FEATURES if k in fuente}
        if valores or any(k in fuente for k in FEATURES):
            return {k: valores.get(k, 0.0) for k in FEATURES}
    return None


def _ultimas_valoraciones(feedback):
    """Una sola valoracion por clip (la mas reciente): re-puntuar un clip no cuenta dos veces."""
    por_clip = {}
    for n, f in enumerate(feedback):
        por_clip[f.get('clip_id') or f"_{n}"] = f
    return list(por_clip.values())


def entrenar_ranker(preferencias):
    feedback = preferencias.get('feedback', []) if isinstance(preferencias, dict) else []
    datos = []
    for f in _ultimas_valoraciones(feedback):
        y = valor_de_feedback(f)
        x = _feedback_features(f)
        # Las valoraciones antiguas no guardaron sus caracteristicas: entrenar con ceros
        # le ensenaria al modelo cosas falsas, asi que se omiten.
        if y is None or x is None:
            continue
        datos.append((x, y))
    pos = sum(1 for _,y in datos if y > 0.15)
    neg = sum(1 for _,y in datos if y < -0.15)
    if len(datos) < MIN_MUESTRAS or pos < MIN_CLASE or neg < MIN_CLASE:
        return None
    w = {k: 0.0 for k in FEATURES}
    b = 0.0
    # Regresión logística pequeña y determinista, sin sklearn/PyTorch.
    for _ in range(80):
        for x, y in datos:
            z = b + sum(w[k] * (2*x[k]-1) for k in FEATURES)
            z = max(-8.0, min(8.0, z))
            p = 1.0 / (1.0 + math.exp(-z))
            target = (y + 1.0) / 2.0
            err = p - target
            lr = 0.025
            b -= lr * err
            for k in FEATURES:
                w[k] -= lr * (err * (2*x[k]-1) + 0.002*w[k])
    norma = math.sqrt(sum(v*v for v in w.values())) or 1.0
    w = {k: v/norma for k,v in w.items()}
    return {'weights': w, 'bias': b, 'muestras': len(datos), 'positivos': pos, 'negativos': neg}


def puntuar_ranker_local(candidato, linea_tiempo=None, preferencias=None):
    modelo = entrenar_ranker(preferencias or {})
    if not modelo:
        return {'score': 0.0, 'confianza': 0.0, 'muestras': 0, 'activo': False}
    x = extraer_features(candidato, linea_tiempo)
    # Solo la parte que depende del candidato (sin el sesgo): si descartas mas de lo que
    # apruebas, el sesgo bajaria a TODOS los clips por igual y no ayudaria a elegir.
    z = sum(modelo['weights'][k] * (2*x[k]-1) for k in FEATURES)
    # -1 rechazo, +1 aceptacion. La confianza crece con los datos (pleno efecto con 40).
    score = math.tanh(z)
    confianza = min(1.0, modelo['muestras'] / 40.0)
    return {'score': round(score,4), 'confianza': round(confianza,3), 'muestras': modelo['muestras'], 'positivos': modelo['positivos'], 'negativos': modelo['negativos'], 'activo': True}
