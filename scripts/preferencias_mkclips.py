"""Feedback local y ranking de preferencias, sin servicios externos."""
from __future__ import annotations

import json
import os
import time
import hashlib

try:
    from .ranker_editorial_mkclips import extraer_features, valor_de_feedback
except ImportError:  # usado como modulo suelto desde scripts/
    from ranker_editorial_mkclips import extraer_features, valor_de_feedback

try:
    from .rutas_app import datos_dir
except ImportError:
    from rutas_app import datos_dir
ARCHIVO_PREFERENCIAS = os.path.join(str(datos_dir()), "preferencias_usuario.json")
MAX_AJUSTE = 12.0


def cargar_preferencias(ruta=ARCHIVO_PREFERENCIAS):
    try:
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return datos if isinstance(datos, dict) and isinstance(datos.get("feedback"), list) else {"version": 1, "feedback": []}
    except (OSError, ValueError, TypeError):
        return {"version": 1, "feedback": []}


def identificador_clip(clip, fuente=None):
    """ID estable por clip y stream; evita mezclar títulos iguales."""
    identidad = (fuente or {}).get("fingerprint", "sin_fuente") if isinstance(fuente, dict) else "sin_fuente"
    partes = [identidad, clip.get("titulo", ""), clip.get("inicio"), clip.get("fin"), clip.get("ruta_archivo", clip.get("archivo", ""))]
    return hashlib.sha256(json.dumps(partes, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:24]


def feedback_por_clip(clip, fuente=None, preferencias=None):
    """Devuelve la última valoración del mismo clip y misma fuente."""
    clip_id = identificador_clip(clip, fuente)
    datos = preferencias if preferencias is not None else cargar_preferencias()
    for entrada in reversed(datos.get("feedback", [])):
        if entrada.get("clip_id") == clip_id:
            return entrada
    return None


# Por que el creador valoro asi un clip. Negativos (descartar o 1-2 estrellas) y positivos (4-5).
# "contenido" es el motivo generico de las versiones anteriores y se sigue entendiendo.
ETIQUETAS_MOTIVO = {
    "aburrido": "aburrido o sin gracia", "contexto": "falta contexto (no se entiende)",
    "repetitivo": "repetitivo o ya visto", "corte": "mal cortado", "tecnico": "problema tecnico",
    "contenido": "no le gusto el momento",
    "humor": "le hizo reir", "climax": "remate o climax fuerte", "habilidad": "jugada o habilidad destacada",
    "historia": "historia completa y facil de seguir", "reaccion": "reaccion o emocion genuina",
    "sorpresa": "sorpresa inesperada",
}
MOTIVOS_NEGATIVOS = ("aburrido", "contexto", "repetitivo", "corte", "tecnico", "contenido")
MOTIVOS_POSITIVOS = ("humor", "climax", "habilidad", "historia", "reaccion", "sorpresa")
MOTIVOS_DESCARTE = MOTIVOS_NEGATIVOS  # nombre anterior


def guardar_feedback(clip, rating=None, liked=None, contexto_juego=None, ruta=ARCHIVO_PREFERENCIAS,
                     fuente=None, discarded=False, comentario="", motivo=""):
    """Guarda la valoracion de un clip.

    ``motivo`` = por que lo valoro asi. Si es negativo (descartar o 1-2 estrellas):
    "aburrido", "contexto", "repetitivo" (le ensenan lo que no te gusta), o "corte" y
    "tecnico" (mal cortado / fallo de audio o video: NO ensenan gustos). Si es positivo
    (4-5 estrellas): "humor", "climax", "habilidad", "historia", "reaccion", "sorpresa"."""
    if rating is not None and (not isinstance(rating, int) or not 1 <= rating <= 5):
        raise ValueError("rating debe ser un entero entre 1 y 5")
    if discarded and rating is not None:
        raise ValueError("Un clip descartado no puede tener estrellas.")
    if liked is None and rating is not None:
        liked = rating >= 4
    if discarded:
        liked = False
    negativo = bool(discarded) or (rating is not None and rating <= 2)
    positivo = rating is not None and rating >= 4
    if negativo:
        motivo = motivo if motivo in MOTIVOS_NEGATIVOS else ("contenido" if discarded else "")
    elif positivo:
        motivo = motivo if motivo in MOTIVOS_POSITIVOS else ""
    else:
        motivo = ""
    try:
        # Las mismas caracteristicas que ve el ranker al puntuar candidatos nuevos.
        features = {k: round(float(v), 4) for k, v in extraer_features(dict(clip)).items()}
    except Exception:
        features = None
    datos = cargar_preferencias(ruta)
    entrada = {
        "timestamp": time.time(), "rating": rating, "liked": liked, "discarded": bool(discarded),
        "comentario": str(comentario or "").strip(), "clip_id": identificador_clip(clip, fuente),
        "fuente_fingerprint": (fuente or {}).get("fingerprint") if isinstance(fuente, dict) else None,
        "titulo": clip.get("titulo", ""), "razon": str(clip.get("razon", "") or "")[:300], "tipo": clip.get("tipo", ""),
        "motivo": motivo, "features": features,
        "score_bruto": clip.get("score_bruto"),
        "duracion": clip.get("duracion"), "score_intrinseco": clip.get("score_intrinseco", clip.get("score", 0)),
        "arco_narrativo": clip.get("arco_narrativo"), "rol_narrativo": clip.get("rol_narrativo"),
        "tipo_candidato": clip.get("tipo_candidato", "independiente"),
        "duracion_final": clip.get("duracion_final", clip.get("duracion")),
        "duracion_original_arco": clip.get("duracion_original_arco"),
        "ratio_compresion": clip.get("ratio_compresion"),
        "cantidad_segmentos": len(clip.get("segmentos", []) or []),
        "cantidad_momentos": len(clip.get("momentos_narrativos", []) or []),
        "densidad_cambios": clip.get("densidad_cambios"),
        "cobertura_eventos": clip.get("cobertura_eventos", {}),
        "continuidad_visual": clip.get("continuidad_visual"),
        "juego": (contexto_juego or {}).get("juego", "desconocido"),
        "situacion": (contexto_juego or {}).get("situacion", "incierta"),
    }
    datos["feedback"].append(entrada)
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)
    return entrada


def _afinidad(entrada, candidato, contexto):
    claves = ("juego", "situacion", "tipo", "rol_narrativo", "tipo_candidato")
    valores = {"juego": contexto.get("juego"), "situacion": contexto.get("situacion"), "tipo": candidato.get("tipo"), "rol_narrativo": candidato.get("rol_narrativo"), "tipo_candidato": candidato.get("tipo_candidato", "independiente")}
    iguales = sum(entrada.get(k) == valores[k] and valores[k] not in (None, "", "desconocido", "incierta") for k in claves)
    return iguales / len(claves)


def calcular_preferencia_usuario(candidato, contexto_juego, preferencias=None):
    """Ajuste (-12..+12) segun cuanto se parece el candidato a lo que valoraste.

    Es RELATIVO: compara lo que te gusta de candidatos parecidos (mismo tipo, rol,
    juego...) con tu promedio general. Asi, si descartas mucho en general, todos los
    clips no pierden lo mismo: solo bajan los de un tipo que sueles rechazar.
    Descartar por contenido y las 1-2 estrellas restan; 5 estrellas suma; los descartes
    por mal corte o fallo tecnico se ignoran."""
    datos = preferencias if preferencias is not None else cargar_preferencias()
    muestras = []
    # Una correccion sustituye la valoracion anterior del mismo clip/stream.
    ultimas = {}
    for indice, entrada in enumerate(datos.get("feedback", [])):
        ultimas[entrada.get("clip_id") or f"legado_{indice}"] = entrada
    for entrada in ultimas.values():
        valor = valor_de_feedback(entrada)
        if valor is None:
            if entrada.get("liked") and not entrada.get("discarded"):
                valor = 1.0  # "me gusta" sin estrellas (formato antiguo)
            else:
                continue
        afinidad = _afinidad(entrada, candidato, contexto_juego or {})
        # Si la entrada no trae ninguno de los campos de comparacion, se trata como totalmente relevante.
        if afinidad <= 0:
            if not any(entrada.get(k) for k in ("juego", "situacion", "tipo", "rol_narrativo", "tipo_candidato")):
                afinidad = 1.0
            else:
                continue
        muestras.append((afinidad, valor))
    todas = [valor_de_feedback(e) for e in ultimas.values()]
    todas = [v for v in todas if v is not None]
    if not muestras or not todas:
        return {"score_preferencia_usuario": 0.0, "muestras": 0, "confianza": 0.0}
    peso = sum(a for a, _ in muestras)
    cercano = sum(a * v for a, v in muestras) / peso
    general = sum(todas) / len(todas)
    relativa = max(-1.0, min(1.0, cercano - general))
    confianza = min(1.0, len(muestras) / 8.0)
    return {"score_preferencia_usuario": round(MAX_AJUSTE * relativa * confianza, 2), "muestras": len(muestras), "confianza": round(confianza, 2)}


def _titulo_clave(texto):
    return "".join(c for c in str(texto or "").lower() if c.isalnum())


def ejemplos_para_prompt(preferencias=None, juego=None, max_aprobados=6, max_rechazados=8, minimo=3):
    """Texto para la IA con lo que el creador aprobo y rechazo de verdad.

    Devuelve "" si hay menos de ``minimo`` ejemplos utiles (con muy pocos seria ruido).
    Solo cuentan los descartes por CONTENIDO y las valoraciones de 1-2 o 4-5 estrellas."""
    datos = preferencias if preferencias is not None else cargar_preferencias()
    ultimas = {}
    for indice, entrada in enumerate(datos.get("feedback", [])):
        ultimas[entrada.get("clip_id") or f"legado_{indice}"] = entrada
    aprobados, rechazados = [], []
    for entrada in sorted(ultimas.values(), key=lambda e: e.get("timestamp") or 0, reverse=True):
        valor = valor_de_feedback(entrada)
        if valor is None or not str(entrada.get("titulo") or "").strip():
            continue
        if valor >= 0.5:
            aprobados.append(entrada)
        elif valor <= -0.5:
            rechazados.append(entrada)
    # Mismo juego primero (estable: dentro de cada grupo siguen mandando los mas recientes).
    if juego and juego not in ("desconocido", "incierta"):
        aprobados.sort(key=lambda e: e.get("juego") != juego)
        rechazados.sort(key=lambda e: e.get("juego") != juego)

    def lineas(entradas, limite):
        vistos, salida = set(), []
        for e in entradas:
            clave = _titulo_clave(e.get("titulo"))
            if clave in vistos:
                continue
            vistos.add(clave)
            razon = str(e.get("razon") or "").strip()
            motivo = ETIQUETAS_MOTIVO.get(e.get("motivo") or "")
            nota = str(e.get("comentario") or "").strip()
            salida.append(f'- "{e["titulo"].strip()}"' + (f" - {razon[:140]}" if razon else "")
                          + (f" [{motivo}]" if motivo else "")
                          + (f' (el creador dijo: "{nota[:160]}")' if nota else ""))
            if len(salida) >= limite:
                break
        return salida

    buenos, malos = lineas(aprobados, max_aprobados), lineas(rechazados, max_rechazados)
    if len(buenos) + len(malos) < minimo:
        return ""
    partes = ["\n\nPreferencias reales del creador (aprendidas de sus valoraciones de clips anteriores). "
              "Usalas solo como pista de gusto: NO repitas estos titulos ni busques momentos identicos."]

    def frecuentes(entradas, validos):
        conteo = {}
        for e in entradas:
            if e.get("motivo") in validos:
                conteo[e["motivo"]] = conteo.get(e["motivo"], 0) + 1
        top = sorted(((n, m) for m, n in conteo.items() if n >= 2), reverse=True)[:3]
        return ", ".join(f"{ETIQUETAS_MOTIVO[m]} ({n})" for n, m in top)

    gusta, no_gusta = frecuentes(aprobados, MOTIVOS_POSITIVOS), frecuentes(rechazados, MOTIVOS_NEGATIVOS[:3] + ("contenido",))
    if gusta:
        partes.append("Lo que mas valora: " + gusta + ".")
    if no_gusta:
        partes.append("Lo que mas rechaza: " + no_gusta + ".")
    if buenos:
        partes.append("Momentos que APROBO (busca mas de este tipo):\n" + "\n".join(buenos))
    if malos:
        partes.append("Momentos que RECHAZO (evita este tipo de momento):\n" + "\n".join(malos))
    return "\n".join(partes) + "\n"


def indicador_acierto(preferencias=None, minimo_por_grupo=3):
    """Cuanto coincide el puntaje del sistema con TUS valoraciones.

    Devuelve {"auc", "n", "aprobados", "rechazados", "suficiente"}. ``auc`` es la
    probabilidad de que un clip que aprobaste tuviera MAS puntaje que uno que rechazaste:
    0.5 = el sistema no distingue (azar), 1.0 = siempre acierta. Solo cuentan las valoraciones
    guardadas con su puntaje (``score_bruto``), es decir, las hechas desde la version que lo guarda."""
    datos = preferencias if preferencias is not None else cargar_preferencias()
    ultimas = {}
    for indice, entrada in enumerate(datos.get("feedback", [])):
        ultimas[entrada.get("clip_id") or f"legado_{indice}"] = entrada
    buenos, malos = [], []
    for entrada in ultimas.values():
        valor = valor_de_feedback(entrada)
        puntaje = entrada.get("score_bruto")
        if valor is None or not isinstance(puntaje, (int, float)):
            continue
        if valor > 0:
            buenos.append(float(puntaje))
        elif valor < 0:
            malos.append(float(puntaje))
    resultado = {"auc": None, "n": len(buenos) + len(malos), "aprobados": len(buenos), "rechazados": len(malos),
                 "suficiente": len(buenos) >= minimo_por_grupo and len(malos) >= minimo_por_grupo}
    if resultado["suficiente"]:
        ganados = sum((b > m) + 0.5 * (b == m) for b in buenos for m in malos)
        resultado["auc"] = round(ganados / (len(buenos) * len(malos)), 3)
    return resultado
