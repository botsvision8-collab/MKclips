"""Seleccion por capas: ENRIQUECE el flujo de identificar_clips.py, no lo reemplaza.

Etapa 1 (este archivo): Capa 1 (pistas deterministas) y Capa 4 (pasos de validacion
que aun no existian). Las capas 2 y 3 (prompt y campos de viralidad) llegan en la etapa 2.

Principios:
- Todos los parametros viven en configuracion_central.DEFAULTS (una sola fuente);
  aqui no hay numeros magicos.
- Nada de lo publico lanza excepciones hacia el flujo: ante cualquier fallo se
  registra un aviso y se devuelve el dato original (degradacion a la logica actual).
- No se llama a ninguna IA desde este modulo.
"""
from __future__ import annotations

import bisect
import copy
import re

try:
    from .configuracion_central import DEFAULTS, leer_configuracion
except ImportError:  # importado como modulo suelto desde scripts/
    from configuracion_central import DEFAULTS, leer_configuracion

PREFIJO_LOG = "[capas]"

# Claves de configuracion que usa este modulo (todas definidas en DEFAULTS).
CLAVES_NUMERICAS = (
    "CAPA1_MAX_PISTAS", "CAPA1_PUNTAJE_MINIMO", "CAPA1_MAX_CHARS_LINEA",
    "PESO_FRASE_GATILLO", "PESO_PREGUNTA", "PESO_ENFASIS", "PESO_GIRO_HISTORIA",
    "PESO_LINEA_CORTA", "PESO_PAUSA_PREVIA", "PESO_PICO_AUDIO", "PESO_CAMBIO_HABLANTE",
    "UMBRAL_LINEA_CORTA_PALABRAS", "UMBRAL_PAUSA_SEG", "MARGEN_PICO_AUDIO_SEG",
    "CAPA2_DURACION_IDEAL_MIN", "CAPA2_DURACION_IDEAL_MAX",
    "VIRALIDAD_PUNTAJE_MAX", "PESO_VIRALIDAD_EN_SCORE",
    "GANCHO_MIN_PALABRAS", "GANCHO_MAX_PALABRAS", "CAPA4_ANCLA_TOLERANCIA_SEG",
)
CLAVES_LISTAS = ("FRASES_GATILLO", "FRASES_GIRO", "TIPOS_GANCHO")
CLAVES_BOOL = ("USAR_SELECCION_POR_CAPAS", "CAPA4_DESCARTAR_NO_ALINEADOS")
CLAVES_CAPAS = CLAVES_NUMERICAS + CLAVES_LISTAS + CLAVES_BOOL

# Subpuntajes de viralidad (campos opcionales del clip, en espanol).
SUBPUNTAJES_VIRALIDAD = ("gancho_puntaje", "engagement_puntaje", "valor_puntaje", "compartibilidad_puntaje")


def _log(mensaje):
    print(f"{PREFIJO_LOG} {mensaje}")


# --------------------------------------------------------------------------- parametros
def cargar_parametros(valores=None):
    """Devuelve los parametros de las capas, validados.

    Un valor invalido se reemplaza por el de DEFAULTS con un aviso; nunca lanza.
    ``valores`` permite inyectar una configuracion (pruebas); si es None se lee
    la configuracion real (DEFAULTS + config.py)."""
    try:
        origen = dict(valores) if valores is not None else leer_configuracion()
    except Exception as exc:  # config ilegible: se usan los valores por defecto
        _log(f"ADVERTENCIA: no se pudo leer la configuracion ({exc}); se usan los valores por defecto.")
        origen = {}
    params = {}
    for clave in CLAVES_CAPAS:
        defecto = DEFAULTS[clave]
        valor = origen.get(clave, defecto)
        try:
            if clave in CLAVES_NUMERICAS:
                valor = float(valor)
                if valor < 0:
                    raise ValueError("no puede ser negativo")
                if isinstance(defecto, int) and not isinstance(defecto, bool):
                    valor = int(valor)
            elif clave in CLAVES_LISTAS:
                if not isinstance(valor, (list, tuple)):
                    raise ValueError("debe ser una lista")
                valor = [str(x).strip().lower() for x in valor if str(x).strip()]
            else:
                valor = bool(valor)
        except (TypeError, ValueError) as exc:
            _log(f"ADVERTENCIA: {clave} invalido ({exc}); se usa el valor por defecto.")
            valor = defecto
        params[clave] = valor
    params["PESO_VIRALIDAD_EN_SCORE"] = min(1.0, params["PESO_VIRALIDAD_EN_SCORE"])
    return params


def capas_activas(params=None):
    p = params or cargar_parametros()
    return bool(p["USAR_SELECCION_POR_CAPAS"])


# --------------------------------------------------------------------------- Capa 1
def _compilar(frases):
    """Regex de palabra/frase completa (respeta acentos); un '*' final = 'empieza por'."""
    partes = []
    for frase in frases:
        prefijo = frase.endswith("*")
        palabras = frase.rstrip("*").split()
        if not palabras:
            continue
        cuerpo = r"\s+".join(re.escape(w) for w in palabras)
        partes.append(r"(?<!\w)" + cuerpo + (r"\w*" if prefijo else r"(?!\w)"))
    if not partes:
        return None
    return re.compile("|".join(partes), re.IGNORECASE)


def puntuar_lineas(linea_tiempo, params=None):
    """Puntua cada linea de HABLA de la linea de tiempo existente.

    Reutiliza los picos de audio ya integrados (items tipo "audio"); no recalcula audio.
    Devuelve [{indice, inicio, fin, texto, puntaje, motivos}] en orden cronologico.
    Ante un fallo devuelve [] (el flujo sigue sin pistas)."""
    try:
        p = params or cargar_parametros()
        patron_gatillo = _compilar(p["FRASES_GATILLO"])
        patron_giro = _compilar(p["FRASES_GIRO"])
        picos = sorted(
            (float(i["inicio"]), float(i["fin"])) for i in linea_tiempo if i.get("tipo") == "audio"
        )
        habla = sorted(
            (i for i in linea_tiempo if i.get("tipo", "habla") != "audio" and str(i.get("texto", "")).strip()),
            key=lambda i: float(i["inicio"]),
        )
        inicios_picos = [a for a, _ in picos]
        margen = p["MARGEN_PICO_AUDIO_SEG"]
        # Maximo acumulado de fines: hay coincidencia si algun pico que empieza antes de la
        # linea (+margen) termina despues de su inicio (-margen).
        fines_max = []
        for _, f in picos:
            fines_max.append(max(f, fines_max[-1]) if fines_max else f)
        resultado = []
        fin_previo = None
        hablante_previo = None
        for indice, linea in enumerate(habla):
            inicio, fin = float(linea["inicio"]), float(linea["fin"])
            texto = str(linea["texto"]).strip()
            puntos = {}
            if patron_gatillo and patron_gatillo.search(texto):
                puntos["gatillo"] = p["PESO_FRASE_GATILLO"]
            if "?" in texto:
                puntos["pregunta"] = p["PESO_PREGUNTA"]
            if "!" in texto:
                puntos["enfasis"] = p["PESO_ENFASIS"]
            if patron_giro and patron_giro.search(texto):
                puntos["giro"] = p["PESO_GIRO_HISTORIA"]
            if len(texto.split()) <= p["UMBRAL_LINEA_CORTA_PALABRAS"]:
                puntos["corta"] = p["PESO_LINEA_CORTA"]
            if fin_previo is not None and inicio - fin_previo >= p["UMBRAL_PAUSA_SEG"]:
                puntos["pausa"] = p["PESO_PAUSA_PREVIA"]
            k = bisect.bisect_right(inicios_picos, fin + margen)
            if k and fines_max[k - 1] >= inicio - margen:
                puntos["pico_audio"] = p["PESO_PICO_AUDIO"]
            hablante = linea.get("hablante")
            if (p["PESO_CAMBIO_HABLANTE"] > 0 and hablante is not None
                    and hablante_previo is not None and hablante != hablante_previo):
                puntos["cambio_hablante"] = p["PESO_CAMBIO_HABLANTE"]
            fin_previo, hablante_previo = fin, hablante
            resultado.append({
                "indice": indice, "inicio": inicio, "fin": fin, "texto": texto,
                "puntaje": round(sum(v for v in puntos.values() if v > 0), 3),
                "motivos": [k for k, v in puntos.items() if v > 0],
            })
        return resultado
    except Exception as exc:
        _log(f"ADVERTENCIA: Capa 1 fallo ({type(exc).__name__}: {exc}); se sigue sin pistas.")
        return []


def seleccionar_pistas(lineas_puntuadas, inicio=None, fin=None, params=None):
    """Mejores lineas (CAPA1_MAX_PISTAS) de un rango, en orden cronologico."""
    p = params or cargar_parametros()
    candidatas = [
        l for l in lineas_puntuadas
        if l["puntaje"] >= p["CAPA1_PUNTAJE_MINIMO"] and l["puntaje"] > 0
        and (inicio is None or l["inicio"] >= inicio) and (fin is None or l["inicio"] < fin)
    ]
    candidatas.sort(key=lambda l: (-l["puntaje"], l["inicio"]))
    return sorted(candidatas[: int(p["CAPA1_MAX_PISTAS"])], key=lambda l: l["inicio"])


def pistas_para_prompt(lineas_puntuadas, inicio=None, fin=None, params=None):
    """Texto de pistas para inyectar en el prompt de un bloque ('' si no hay ninguna)."""
    try:
        p = params or cargar_parametros()
        pistas = seleccionar_pistas(lineas_puntuadas, inicio, fin, p)
        if not pistas:
            return ""
        tope = int(p["CAPA1_MAX_CHARS_LINEA"])
        filas = []
        for l in pistas:
            texto = l["texto"] if len(l["texto"]) <= tope else l["texto"][: tope - 1].rstrip() + "…"
            filas.append(f"[{l['inicio']}s - {l['fin']}s] (señales: {', '.join(l['motivos'])}) {texto}")
        return (
            "PISTAS DETERMINISTAS (calculadas sin IA a partir de frases gatillo, preguntas, pausas y picos "
            "de audio). Son solo pistas para localizar momentos: NO son la decisión, y una pista por sí sola "
            "no convierte un fragmento en buen clip:\n" + "\n".join(filas)
        )
    except Exception as exc:
        _log(f"ADVERTENCIA: no se pudo armar el texto de pistas ({exc}); se sigue sin pistas.")
        return ""


# --------------------------------------------------------------------------- Capa 4
def preparar_anclas(linea_tiempo):
    """(inicios, fines) ordenados de las lineas reales de habla."""
    habla = [i for i in linea_tiempo if i.get("tipo", "habla") != "audio" and str(i.get("texto", "")).strip()]
    return (
        sorted(float(i["inicio"]) for i in habla),
        sorted(float(i["fin"]) for i in habla),
    )


def _mas_cercano(valor, ordenados, tolerancia):
    """Valor de ``ordenados`` mas cercano a ``valor`` si esta dentro de la tolerancia, si no None."""
    if not ordenados:
        return None
    k = bisect.bisect_left(ordenados, valor)
    mejores = [ordenados[j] for j in (k - 1, k) if 0 <= j < len(ordenados)]
    elegido = min(mejores, key=lambda x: abs(x - valor))
    return elegido if abs(elegido - valor) <= tolerancia else None


def texto_real_del_rango(linea_tiempo, inicio, fin):
    """Texto real del transcript que cae dentro del rango (para comprobar al modelo, nunca para reescribir)."""
    return " ".join(
        str(i["texto"]).strip() for i in sorted(linea_tiempo, key=lambda i: float(i["inicio"]))
        if i.get("tipo", "habla") != "audio" and float(i["fin"]) > inicio and float(i["inicio"]) < fin
        and str(i.get("texto", "")).strip()
    )


def anclar_a_lineas(candidato, anclas, params=None, limites=(0.0, 0.0)):
    """Ajusta inicio/fin (y cada segmento) a los limites de lineas reales cercanas.

    No existia en el flujo: normalizar_candidato valida el contrato temporal, pero no
    comprueba que los limites coincidan con lineas reales de transcripcion.json.
    - Un limite a <= CAPA4_ANCLA_TOLERANCIA_SEG de una linea real se ajusta a ella.
    - Si el ajuste dejara el clip fuera de ``limites`` (min, max; 0 = sin limite) estando
      antes dentro, se conserva el original.
    - Devuelve (candidato, avisos). Si CAPA4_DESCARTAR_NO_ALINEADOS esta activo y algun
      limite no tiene linea real cercana, devuelve (None, avisos)."""
    p = params or cargar_parametros()
    inicios, fines = anclas
    tolerancia = p["CAPA4_ANCLA_TOLERANCIA_SEG"]
    avisos = []
    piezas = candidato.get("segmentos") if isinstance(candidato.get("segmentos"), list) and candidato.get("segmentos") \
        else [{"inicio": candidato["inicio"], "fin": candidato["fin"]}]
    nuevas, sin_alinear = [], []
    previo_fin = None
    for pieza in piezas:
        i0, f0 = float(pieza["inicio"]), float(pieza["fin"])
        i1 = _mas_cercano(i0, inicios, tolerancia)
        f1 = _mas_cercano(f0, fines, tolerancia)
        if i1 is None:
            sin_alinear.append(f"inicio {i0}")
        if f1 is None:
            sin_alinear.append(f"fin {f0}")
        i1 = i0 if i1 is None else i1
        f1 = f0 if f1 is None else f1
        if f1 <= i1 or (previo_fin is not None and i1 < previo_fin):
            i1, f1 = i0, f0  # el ajuste rompe el orden: se conserva la pieza original
        previo_fin = f1
        nuevas.append({"inicio": round(i1, 2), "fin": round(f1, 2)})
    if sin_alinear and p["CAPA4_DESCARTAR_NO_ALINEADOS"]:
        avisos.append("descartado: limites sin linea real cercana (" + ", ".join(sin_alinear) + ")")
        return None, avisos
    if sin_alinear:
        avisos.append("limites sin linea real cercana, se conservan (" + ", ".join(sin_alinear) + ")")

    dur_antes = sum(float(x["fin"]) - float(x["inicio"]) for x in piezas)
    dur_despues = sum(x["fin"] - x["inicio"] for x in nuevas)
    minimo, maximo = limites
    rompe_max = maximo and dur_despues > maximo and dur_antes <= maximo
    rompe_min = minimo and dur_despues < minimo and dur_antes >= minimo
    if rompe_max or rompe_min:
        avisos.append(f"ajuste a lineas revertido: la duracion pasaria de {dur_antes:.1f}s a {dur_despues:.1f}s, fuera de limites")
        return candidato, avisos

    cambios = [
        f"{a['inicio']}-{a['fin']} -> {b['inicio']}-{b['fin']}"
        for a, b in zip(piezas, nuevas)
        if round(float(a["inicio"]), 2) != b["inicio"] or round(float(a["fin"]), 2) != b["fin"]
    ]
    if cambios:
        avisos.append("limites anclados a lineas reales (" + "; ".join(cambios) + ")")
        if isinstance(candidato.get("segmentos"), list) and candidato.get("segmentos"):
            candidato["segmentos"] = nuevas
        candidato["inicio"] = nuevas[0]["inicio"]
        candidato["fin"] = nuevas[-1]["fin"]
    return candidato, avisos


def sanear_viralidad(viralidad, params=None):
    """Valida el objeto "viralidad" del clip y recalcula el total como suma de subpuntajes.

    Es una AUTOEVALUACION del LLM, no una prediccion calibrada. Devuelve (dict|None, avisos);
    None si la estructura no es utilizable (el clip se conserva sin ese campo)."""
    p = params or cargar_parametros()
    avisos = []
    if not isinstance(viralidad, dict):
        return None, ["viralidad ignorada: no es un objeto"]
    tope = float(p["VIRALIDAD_PUNTAJE_MAX"])
    limpio = {}
    for clave in SUBPUNTAJES_VIRALIDAD:
        try:
            valor = float(viralidad[clave])
        except (KeyError, TypeError, ValueError):
            return None, [f"viralidad ignorada: falta o es invalido '{clave}'"]
        ajustado = max(0.0, min(tope, valor))
        if ajustado != valor:
            avisos.append(f"{clave} fuera de rango ({valor}) -> {ajustado:g}")
        limpio[clave] = int(round(ajustado))
    total = sum(limpio.values())
    if "total" in viralidad:
        try:
            if abs(float(viralidad["total"]) - total) > 1e-9:
                avisos.append(f"total corregido ({viralidad['total']} -> {total})")
        except (TypeError, ValueError):
            avisos.append(f"total invalido ({viralidad['total']!r}) -> {total}")
    limpio["total"] = total
    tipo = str(viralidad.get("tipo_gancho") or "").strip().lower()
    if tipo not in p["TIPOS_GANCHO"]:
        if tipo:
            avisos.append(f"tipo_gancho desconocido ({tipo!r}) -> 'ninguno'")
        tipo = "ninguno"
    limpio["tipo_gancho"] = tipo
    limpio["razon_viralidad"] = str(viralidad.get("razon_viralidad") or "").strip()[:300]
    return limpio, avisos


_RE_EMOJI = re.compile("[\U00010000-\U0010ffff←-⇿⌀-⏿☀-➿⬀-⯿️‍]")
_RE_HASHTAG = re.compile(r"#\w+")


def sanear_gancho(gancho, params=None):
    """Limpia el "gancho" (titulo corto de pantalla): sin emojis ni hashtags, 3-9 palabras.

    Devuelve (texto|None, avisos). Mas de GANCHO_MAX_PALABRAS se recorta; menos de
    GANCHO_MIN_PALABRAS se descarta el campo (el clip conserva su "titulo")."""
    p = params or cargar_parametros()
    if not isinstance(gancho, str):
        return None, ["gancho ignorado: no es texto"]
    texto = _RE_HASHTAG.sub("", _RE_EMOJI.sub("", gancho))
    texto = " ".join(texto.replace('"', "").split()).strip(" .,;:-")
    palabras = texto.split()
    avisos = []
    if len(palabras) < p["GANCHO_MIN_PALABRAS"]:
        return None, [f"gancho descartado: {len(palabras)} palabras (minimo {int(p['GANCHO_MIN_PALABRAS'])})"]
    if len(palabras) > p["GANCHO_MAX_PALABRAS"]:
        palabras = palabras[: int(p["GANCHO_MAX_PALABRAS"])]
        avisos.append(f"gancho recortado a {len(palabras)} palabras")
    texto = " ".join(palabras)
    if texto != gancho.strip():
        avisos.append("gancho limpiado (emojis/hashtags/comillas)")
    return texto, avisos


def mezclar_score(score, viralidad, params=None):
    """score*(1-peso) + total_viralidad*peso. Con peso 0 (por defecto) devuelve ``score`` intacto."""
    p = params or cargar_parametros()
    peso = p["PESO_VIRALIDAD_EN_SCORE"]
    if peso <= 0 or not isinstance(viralidad, dict) or "total" not in viralidad:
        return score
    try:
        return round(float(score) * (1 - peso) + float(viralidad["total"]) * peso, 3)
    except (TypeError, ValueError):
        return score


def enriquecer_candidato(candidato, anclas, params=None, limites=(0.0, 0.0), etiqueta=""):
    """Aplica los pasos de Capa 4 a UN candidato ya normalizado.

    Devuelve el candidato (modificado en una copia) o None si debe descartarse.
    Si algo falla devuelve el candidato original sin tocar. Registra cada correccion."""
    nombre = etiqueta or f"[{candidato.get('inicio')}s-{candidato.get('fin')}s]"
    try:
        p = params or cargar_parametros()
        c = copy.deepcopy(candidato)
        avisos = []
        c, av = anclar_a_lineas(c, anclas, p, limites)
        avisos += av
        if c is None:
            _log(f"{nombre}: " + "; ".join(avisos))
            return None
        if "gancho" in c:
            texto, av = sanear_gancho(c["gancho"], p)
            avisos += av
            if texto is None:
                c.pop("gancho", None)
            else:
                c["gancho"] = texto
        if "viralidad" in c:
            vir, av = sanear_viralidad(c["viralidad"], p)
            avisos += av
            if vir is None:
                c.pop("viralidad", None)
            else:
                c["viralidad"] = vir
        for aviso in avisos:
            _log(f"{nombre}: {aviso}")
        return c
    except Exception as exc:
        _log(f"ADVERTENCIA: {nombre}: Capa 4 fallo ({type(exc).__name__}: {exc}); se conserva el clip sin cambios.")
        return candidato


# --------------------------------------------------------------------------- Capa 2 (prompt) y enganches
def construir_bloque_prompt(pistas, params=None):
    """Texto que se anade al prompt existente de cada bloque cuando el flag esta activo.

    Contiene: pistas de la Capa 1, principios de seleccion (Capa 2) y los campos
    opcionales extra (Capa 3). No cambia el formato base de la respuesta."""
    p = params or cargar_parametros()
    tope = int(p["VIRALIDAD_PUNTAJE_MAX"])
    tipos = " | ".join(p["TIPOS_GANCHO"])
    partes = []
    if pistas:
        partes.append(pistas)
    partes.append(f"""PRINCIPIOS DE SELECCIÓN (aplican a los candidatos "completo"; esto es SELECCIÓN de rangos del transcript, no un resumen ni una reescritura):
- Cada clip es un rango REAL del transcript con sus timestamps. No inventes contenido ni unas momentos lejanos o sin relación. El campo "segmentos" solo se usa en el caso ya descrito (salto editorial justificado dentro de la misma situación).
- Gancho fuerte al inicio, idea completa que se entienda sin contexto (setup, tensión, payoff), y momentos emocionales (sorpresa, humor, reacción) con lenguaje concreto.
- Evita saludos, intros, sponsors, llamadas a la acción, frases sueltas sin contexto, puntos repetidos y tiempo muerto.
- Prueba mental: ¿un espectador entendería y se interesaría sin ver el resto del stream?
- Si un momento fuerte es corto, expándelo a líneas vecinas para dar contexto y desenlace.
- Si hay conflicto entre "viral" y "exacto", gana la exactitud.
- Duración ideal: entre {p['CAPA2_DURACION_IDEAL_MIN']:g} y {p['CAPA2_DURACION_IDEAL_MAX']:g} segundos (los límites estrictos de duración siguen siendo los ya indicados).
- Pocos clips buenos; no rellenes una cuota.
- En gameplay, si hay un pico de audio fuerte puedes considerar el momento aunque haya poco texto.

CAMPOS EXTRA para cada candidato "completo" (opcionales; añádelos al mismo objeto JSON):
- "gancho": título corto para pantalla, de {int(p['GANCHO_MIN_PALABRAS'])} a {int(p['GANCHO_MAX_PALABRAS'])} palabras, en español, sin emojis, sin hashtags y sin inventar nada que no ocurra.
- "viralidad": {{"gancho_puntaje": 0-{tope}, "engagement_puntaje": 0-{tope}, "valor_puntaje": 0-{tope}, "compartibilidad_puntaje": 0-{tope}, "tipo_gancho": "{tipos}", "razon_viralidad": "breve"}}
  Rúbrica de cada subpuntaje: {tope * 4 // 5}-{tope} excelente, {tope * 3 // 5}-{tope * 4 // 5 - 1} bueno, {tope * 2 // 5}-{tope * 3 // 5 - 1} regular, 0-{tope * 2 // 5 - 1} débil. Es una autoevaluación tuya, no una predicción: sé estricto y usa valores bajos si la evidencia no está en el transcript.
""")
    return "\n" + "\n".join(partes)


def enriquecer_lista(momentos, anclas, params=None, limites=(0.0, 0.0), etiqueta=""):
    """Aplica enriquecer_candidato a los candidatos "completo"; los demas ("corto") pasan intactos."""
    salida = []
    for m in momentos:
        if isinstance(m, dict) and m.get("tipo") == "completo":
            r = enriquecer_candidato(m, anclas, params, limites, etiqueta=etiqueta or None)
            if r is not None:
                salida.append(r)
        else:
            salida.append(m)
    return salida


def anclar_final(candidatos, anclas, params=None, limites=(0.0, 0.0)):
    """Ultimo ajuste a lineas reales sobre los clips finales (tras el refinado de la IA).

    Las "historias" comprimidas se omiten: sus puntos de corte ya los fijo la compresion."""
    p = params or cargar_parametros()
    salida = []
    for c in candidatos:
        if c.get("tipo_candidato") == "historia":
            salida.append(c)
            continue
        try:
            r, avisos = anclar_a_lineas(c, anclas, p, limites)
        except Exception as exc:
            _log(f"ADVERTENCIA: anclaje final fallo en [{c.get('inicio')}s-{c.get('fin')}s] ({exc}); se conserva.")
            salida.append(c)
            continue
        for aviso in avisos:
            _log(f"final [{c.get('inicio')}s-{c.get('fin')}s]: {aviso}")
        if r is not None:
            salida.append(r)
    return salida


# --------------------------------------------------------------------------- Etapa 3: metricas
import contextlib
import json
import os
import threading
import time
from datetime import datetime


class Cronometro:
    """Acumula segundos por nombre; seguro entre hilos (los bloques se piden en paralelo)."""

    def __init__(self):
        self._bloqueo = threading.Lock()
        self.segundos = {}
        self.llamadas = {}

    @contextlib.contextmanager
    def medir(self, nombre):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            with self._bloqueo:
                self.segundos[nombre] = self.segundos.get(nombre, 0.0) + dt
                self.llamadas[nombre] = self.llamadas.get(nombre, 0) + 1

    def resumen(self):
        with self._bloqueo:
            return {
                "capa1_seg": round(self.segundos.get("capa1_seg", 0.0), 3),
                # Suma de lo que tardo cada peticion de bloque: con concurrencia > 1 puede superar el tiempo real.
                "llm_seg": round(self.segundos.get("llm_seg", 0.0), 3),
                "llamadas_llm": self.llamadas.get("llm_seg", 0),
                "validacion_seg": round(self.segundos.get("validacion_seg", 0.0), 3),
            }


def resumen_clips(clips):
    """Cuantos clips finales traen los campos opcionales de las capas."""
    return {
        "clips_finales": len(clips),
        "con_gancho": sum(1 for c in clips if c.get("gancho")),
        "con_viralidad": sum(1 for c in clips if isinstance(c.get("viralidad"), dict)),
    }


def guardar_metricas_tiempos(ruta, tiempos, clips_resumen):
    """Anade la clave opcional "capas" a historial_tiempos_proceso.json sin tocar el resto.

    Conserva ratio_promedio y muestras tal cual (los lee procesar_multiples). Escritura atomica;
    cualquier fallo solo se registra. Devuelve True si guardo."""
    try:
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if not isinstance(datos, dict):
                datos = {}
        except (OSError, ValueError):
            datos = {}
        capas = datos.get("capas") if isinstance(datos.get("capas"), dict) else {}
        acumulado = capas.get("acumulado") if isinstance(capas.get("acumulado"), dict) else {}
        for clave in ("capa1_seg", "llm_seg", "validacion_seg"):
            acumulado[clave] = round(float(acumulado.get(clave, 0.0)) + float(tiempos.get(clave, 0.0)), 3)
        acumulado["ejecuciones"] = int(acumulado.get("ejecuciones", 0)) + 1
        capas["acumulado"] = acumulado
        capas["ultima"] = dict(tiempos, **clips_resumen, fecha=datetime.now().isoformat(timespec="seconds"))
        datos["capas"] = capas
        temporal = f"{ruta}.{os.getpid()}.tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(datos, f)
        os.replace(temporal, ruta)
        return True
    except Exception as exc:
        _log(f"ADVERTENCIA: no se pudieron guardar las metricas de tiempo ({type(exc).__name__}: {exc}).")
        return False
