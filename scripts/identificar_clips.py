import contextlib
import json
import os
import re

from cache_mkclips import guardar_identidad_artefacto
from narrativa_mkclips import (
    anotar_narrativa, clasificar_segmentos, comprimir_arco_narrativo,
    construir_arcos, construir_contexto_juego, normalizar_segmentos_sin_duplicados,
    preparar_momento_independiente,
)
from preferencias_mkclips import cargar_preferencias, ejemplos_para_prompt
from contexto_ia import construir_bloque, leer_criterios
from diagnostico_selector import Diagnostico
try:
    import recorte_ia
except Exception as _exc_recorte:  # sin el modulo se conserva el comportamiento anterior
    recorte_ia = None
    print(f"ADVERTENCIA: recorte inteligente no disponible ({_exc_recorte}).")

DIAG = Diagnostico()

# En Windows, el Python embebido/standalone puede no incluir en certifi el
# certificado raíz de la red local. Se activa el almacén de certificados del
# sistema ANTES de conectar con la IA (afecta a urllib y a httpx).
try:
    import truststore
except ImportError as exc:
    raise RuntimeError(
        "Falta truststore; instala las dependencias con: pip install -r requirements.txt"
    ) from exc
truststore.inject_into_ssl()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
try:
    from config import CARPETA_RESULTADOS
except Exception:
    CARPETA_RESULTADOS = ""
CARPETA_RESULTADOS = CARPETA_RESULTADOS or os.path.join(BASE_DIR, "resultados")
os.makedirs(CARPETA_RESULTADOS, exist_ok=True)

import llm_cliente
from concurrent.futures import ThreadPoolExecutor

with open("transcripcion.json", "r", encoding="utf-8") as f:
    segmentos = json.load(f)

with open("ultimo_video.txt", "r", encoding="utf-8") as f:
    video_path = f.readline().strip()


eventos_audio = []
if os.path.exists("eventos_audio.json"):
    with open("eventos_audio.json", "r", encoding="utf-8") as f:
        eventos_audio = json.load(f)
    print(f"Usando {len(eventos_audio)} eventos de audio detectados como señal extra.")

# La vision es opcional: si falta o es invalida, el flujo sigue como antes.
RUTA_EVENTOS_VISUALES = os.path.join(CARPETA_RESULTADOS, "eventos_visuales.json")
eventos_visuales = []
if os.path.exists(RUTA_EVENTOS_VISUALES):
    try:
        with open(RUTA_EVENTOS_VISUALES, "r", encoding="utf-8") as f:
            datos_visuales = json.load(f)
        if not isinstance(datos_visuales, list):
            raise ValueError("la raiz debe ser una lista")
        eventos_visuales = [
            evento for evento in datos_visuales
            if isinstance(evento, dict) and "inicio" in evento and "fin" in evento
        ]
        print(f"Usando {len(eventos_visuales)} eventos visuales reales como señal complementaria.")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ADVERTENCIA: no se pudieron cargar eventos visuales ({exc}). Se continua sin vision.")
        eventos_visuales = []
else:
    print("No hay eventos visuales disponibles; se continua sin esa señal.")

linea_tiempo = []
for s in segmentos:
    linea_tiempo.append({"inicio": s["inicio"], "fin": s["fin"], "texto": s["texto"], "tipo": "habla"})
for e in eventos_audio:
    linea_tiempo.append({
        "inicio": e["inicio"], "fin": e["fin"],
        "texto": "REACCION FUERTE DE AUDIO DETECTADA (posible risa/grito/exclamacion)",
        "tipo": "audio"
    })
linea_tiempo.sort(key=lambda x: x["inicio"])
RUTA_CONTEXTO_STREAM = os.path.join(CARPETA_RESULTADOS, "contexto_stream.json")
contexto_usuario = ""
if os.path.exists(RUTA_CONTEXTO_STREAM):
    try:
        with open(RUTA_CONTEXTO_STREAM, "r", encoding="utf-8") as f:
            contexto_usuario = str(json.load(f).get("contexto", ""))
    except (OSError, ValueError, AttributeError):
        pass
CONTEXTO_JUEGO = construir_contexto_juego(video_path, contexto_usuario, linea_tiempo, eventos_visuales)
PREFERENCIAS_USUARIO = cargar_preferencias()
print(f"Contexto de juego: {CONTEXTO_JUEGO['juego']} (confianza {CONTEXTO_JUEGO['confianza']:.2f}; {len(PREFERENCIAS_USUARIO['feedback'])} feedbacks locales).")

ejemplos_opinion = []
if os.path.exists("ejemplos_buenos.json"):
    with open("ejemplos_buenos.json", "r", encoding="utf-8") as f:
        ejemplos_opinion = json.load(f)

resultados_reales = []
if os.path.exists("resultados_reales.json"):
    with open("resultados_reales.json", "r", encoding="utf-8") as f:
        resultados_reales = json.load(f)

def formatear_contexto_calibracion(ejemplos, resultados):
    partes = []
    if resultados:
        ordenados = sorted(resultados, key=lambda x: x["vistas"], reverse=True)
        mejores = ordenados[:5]
        peores = ordenados[-3:] if len(ordenados) > 5 else []
        bloque_mejores = "\n".join(
            f'- "{r["titulo"]}" ({r.get("razon","")}) -> {r["vistas"]:,} vistas REAL'
            for r in mejores
        )
        texto = f"\n\nDATOS REALES de desempeño de clips anteriores (la señal MÁS confiable):\nMEJOR DESEMPEÑO (imita este tipo de momento):\n{bloque_mejores}\n"
        if peores:
            bloque_peores = "\n".join(
                f'- "{r["titulo"]}" -> solo {r["vistas"]:,} vistas REAL (evita este tipo)'
                for r in peores
            )
            texto += f"\n{bloque_peores}\n"
        partes.append(texto)
    if ejemplos:
        bloque_ejemplos = "\n".join(
            f'- "{e["texto"]}" -> SI es gracioso porque: {e["razon"]}'
            for e in ejemplos[:8]
        )
        partes.append(f"\n\nEjemplos que el creador confirmó como buenos antes:\n{bloque_ejemplos}\n")
    return "".join(partes)

CONTEXTO_CALIBRACION = formatear_contexto_calibracion(ejemplos_opinion, resultados_reales)
# Lo que el creador aprobo y rechazo en Validar clips llega a la IA para que lo tenga en cuenta.
# Objetivo del proyecto, contexto de ESTE stream y criterios del creador (aprendidos de sus valoraciones).
try:
    from configuracion_central import leer_configuracion as _leer_cfg
    _contexto_proyecto = _leer_cfg().get("CONTEXTO_PROYECTO", "")
except Exception:
    _contexto_proyecto = ""
CONTEXTO_USUARIO_IA = construir_bloque(_contexto_proyecto, contexto_usuario, leer_criterios())
if CONTEXTO_USUARIO_IA:
    CONTEXTO_CALIBRACION += CONTEXTO_USUARIO_IA
    print("Usando el contexto del proyecto / stream / criterios del creador como guia para la IA.")
CONTEXTO_VALORACIONES = ejemplos_para_prompt(PREFERENCIAS_USUARIO, CONTEXTO_JUEGO.get("juego"))
if CONTEXTO_VALORACIONES:
    CONTEXTO_CALIBRACION += CONTEXTO_VALORACIONES
    print(f"Usando tus valoraciones anteriores como guia para la IA ({CONTEXTO_VALORACIONES.count(chr(10) + '- ')} ejemplos).")
if resultados_reales:
    print(f"Usando {len(resultados_reales)} clips con datos REALES de desempeño.")
if ejemplos_opinion:
    print(f"Usando {len(ejemplos_opinion)} ejemplos de opinión confirmados.")
print()

BLOQUE_SEGUNDOS = 1500
SOLAPE_SEGUNDOS = 240

bloques = []
inicio_actual = 0
duracion_total = linea_tiempo[-1]["fin"] if linea_tiempo else 0

while inicio_actual < duracion_total:
    fin_bloque = inicio_actual + BLOQUE_SEGUNDOS
    bloque = [item for item in linea_tiempo if inicio_actual <= item["inicio"] < fin_bloque]
    if bloque:
        bloques.append(bloque)
    inicio_actual = fin_bloque - SOLAPE_SEGUNDOS

print(f"Transcripción dividida en {len(bloques)} bloques (con solape de {SOLAPE_SEGUNDOS}s entre ellos).")


# --- Unidades narrativas / anclas deterministas ---
def construir_anclas_narrativas(linea_tiempo, duracion_total):
    habla = [x for x in linea_tiempo if x.get("tipo") == "habla"]
    if not habla:
        return ([{"inicio": 0.0, "fin": float(duracion_total), "tipo": "inicio"}]
                if duracion_total else [])
    anclas = [{"inicio": float(habla[0]["inicio"]), "fin": float(habla[0]["fin"]), "tipo": "inicio"}]
    for anterior, actual in zip(habla, habla[1:]):
        pausa = float(actual["inicio"]) - float(anterior["fin"])
        if pausa >= 12.0:
            anclas.append({"inicio": float(actual["inicio"]), "fin": float(actual["fin"]), "tipo": "pausa"})
    paso = 420.0
    t = paso
    while t < float(duracion_total):
        if not any(abs(float(a["inicio"]) - t) < 30.0 for a in anclas):
            cercano = min(habla, key=lambda x: abs(float(x["inicio"]) - t))
            anclas.append({"inicio": float(cercano["inicio"]), "fin": float(cercano["fin"]), "tipo": "tramo_temporal"})
        t += paso
    return sorted(anclas, key=lambda x: x["inicio"])

def preparar_anclas_y_unidades(linea_tiempo, duracion_total):
    anclas = construir_anclas_narrativas(linea_tiempo, duracion_total)
    unidades = []
    for i, ancla in enumerate(anclas):
        inicio = float(ancla["inicio"])
        fin = float(anclas[i + 1]["inicio"]) if i + 1 < len(anclas) else float(duracion_total)
        if fin > inicio:
            unidades.append({"id": i + 1, "inicio": inicio, "fin": fin, "ancla_inicio": inicio, "tipo_ancla": ancla.get("tipo", "ancla")})
    return anclas, unidades

def asignar_unidad_narrativa(candidato, anclas, duracion_total):
    inicio = float(candidato.get("inicio", 0.0))
    if not anclas:
        candidato["unidad_narrativa"] = "sin_ancla"
        candidato["ancla_inicio"] = 0.0
        candidato["tipo_ancla"] = "inicio"
        return candidato
    idx = 0
    for i, ancla in enumerate(anclas):
        if float(ancla["inicio"]) <= inicio:
            idx = i
        else:
            break
    candidato["unidad_narrativa"] = f"unidad_{idx + 1}"
    candidato["ancla_inicio"] = float(anclas[idx]["inicio"])
    candidato["tipo_ancla"] = anclas[idx].get("tipo", "ancla")
    return candidato

def ajustar_inicio_a_ancla(candidato, margen=35.0):
    ancla = candidato.get("ancla_inicio")
    if ancla is None:
        return candidato
    inicio = float(candidato["inicio"])
    ancla = float(ancla)
    if abs(inicio - ancla) <= float(margen):
        candidato["inicio"] = round(max(0.0, min(inicio, ancla)), 2)
    return candidato

def limitar_a_unidad(candidato):
    inicio = max(0.0, float(candidato["inicio"]))
    fin = max(inicio, float(candidato["fin"]))
    unidad = UNIDADES_POR_ID.get(candidato.get("unidad_narrativa"))
    if unidad:
        inicio = max(inicio, float(unidad["inicio"]))
        fin = min(fin, float(unidad["fin"]))
        fin = max(fin, inicio)
    candidato["inicio"] = round(inicio, 2)
    candidato["fin"] = round(fin, 2)
    return candidato


def unidad_permite_minimo(candidato):
    """True si la unidad narrativa asignada tiene espacio suficiente para
    cumplir DURACION_MIN_CLIP sin cruzar a la siguiente unidad."""
    if DURACION_MIN_CLIP <= 0:
        return True
    unidad = UNIDADES_POR_ID.get(candidato.get("unidad_narrativa"))
    if not unidad:
        return True
    inicio_util = max(float(candidato["inicio"]), float(unidad["inicio"]))
    return (float(unidad["fin"]) - inicio_util) >= DURACION_MIN_CLIP


def cumple_duracion_configurada(candidato):
    duracion = duracion_candidato(candidato)
    if DURACION_MIN_CLIP > 0 and duracion < DURACION_MIN_CLIP:
        return False
    if DURACION_MAX_CLIP > 0 and duracion > DURACION_MAX_CLIP:
        return False
    return True

try:
    from scoring_mkclips import anotar_candidatos
except Exception:
    def anotar_candidatos(candidatos, segmentos, eventos_audio, eventos_visuales=None, *args):
        return candidatos

try:
    from config import DURACION_MIN_CLIP, DURACION_MAX_CLIP
except ImportError:
    # Si config.py no se puede importar se lee el archivo directamente: asi el
    # maximo configurado nunca se pierde en silencio (antes caia a 0 = sin limite).
    from configuracion_central import leer_configuracion
    _cfg = leer_configuracion()
    DURACION_MIN_CLIP = _cfg.get("DURACION_MIN_CLIP", 0)
    DURACION_MAX_CLIP = _cfg.get("DURACION_MAX_CLIP", 0)

anclas_narrativas, unidades_narrativas = preparar_anclas_y_unidades(linea_tiempo, duracion_total)
UNIDADES_POR_ID = {f"unidad_{u['id']}": u for u in unidades_narrativas}
print(f"Anclas narrativas detectadas: {len(anclas_narrativas)} | unidades: {len(unidades_narrativas)}")

# Regex de rescate: ahora tambien captura "tipo" (completo/corto)
PATRON_MOMENTO = re.compile(
    r'"tipo"\s*:\s*"([^"]*)"\s*,\s*"inicio"\s*:\s*([\d.]+)\s*,\s*"fin"\s*:\s*([\d.]+)\s*,\s*"titulo"\s*:\s*"([^"]*)"\s*,\s*"razon"\s*:\s*"([^"]*)"',
    re.DOTALL
)

DURACION_MIN = DURACION_MIN_CLIP
TEXTO_MAXIMO = f"{DURACION_MAX_CLIP:g} s" if DURACION_MAX_CLIP and DURACION_MAX_CLIP > 0 else "sin límite"
DURACION_MIN_SEGMENTO = 0.05

# --- Seleccion por capas (opcional, ver seleccion_capas.py). Con el flag en False no cambia nada. ---
CAPAS_ACTIVAS = False
CRONO = None
PARAMS_CAPAS = {}
ANCLAS_LINEAS = ([], [])
LINEAS_PUNTUADAS = []
try:
    import seleccion_capas
    PARAMS_CAPAS = seleccion_capas.cargar_parametros()
    CAPAS_ACTIVAS = bool(PARAMS_CAPAS["USAR_SELECCION_POR_CAPAS"])
    if CAPAS_ACTIVAS:
        CRONO = seleccion_capas.Cronometro()
        with CRONO.medir("capa1_seg"):
            ANCLAS_LINEAS = seleccion_capas.preparar_anclas(linea_tiempo)
            LINEAS_PUNTUADAS = seleccion_capas.puntuar_lineas(linea_tiempo, PARAMS_CAPAS)
        print(f"[capas] Seleccion por capas ACTIVA: {len(LINEAS_PUNTUADAS)} lineas puntuadas.")
except Exception as exc:
    CAPAS_ACTIVAS = False
    print(f"[capas] ADVERTENCIA: no se pudo iniciar la seleccion por capas ({exc}); se usa la logica actual.")


def _medir(nombre):
    """Cronometra una etapa de las capas; no hace nada con el flag apagado."""
    return CRONO.medir(nombre) if (CAPAS_ACTIVAS and CRONO is not None) else contextlib.nullcontext()


def duracion_candidato(candidato):
    segmentos_compuestos = candidato.get("segmentos")
    if isinstance(segmentos_compuestos, list) and len(segmentos_compuestos) > 1:
        return sum(
            max(0.0, float(segmento["fin"]) - float(segmento["inicio"]))
            for segmento in segmentos_compuestos
        )
    return max(0.0, float(candidato["fin"]) - float(candidato["inicio"]))


MARGEN_EVENTO_VISUAL = 6.0


def intervalos_candidato(candidato):
    """Devuelve intervalos reales, incluso para segmentos compuestos."""
    segmentos_compuestos = candidato.get("segmentos")
    if isinstance(segmentos_compuestos, list) and segmentos_compuestos:
        return [
            segmento for segmento in segmentos_compuestos
            if isinstance(segmento, dict) and "inicio" in segmento and "fin" in segmento
        ]
    return [candidato]


def asociar_eventos_visuales(candidato, eventos, margen=MARGEN_EVENTO_VISUAL):
    """Adjunta detecciones reales solapadas o cercanas al candidato."""
    asociados = []
    for evento in eventos:
        try:
            inicio_evento = float(evento["inicio"])
            fin_evento = float(evento["fin"])
        except (KeyError, TypeError, ValueError):
            continue
        for intervalo in intervalos_candidato(candidato):
            try:
                inicio = float(intervalo["inicio"])
                fin = float(intervalo["fin"])
            except (KeyError, TypeError, ValueError):
                continue
            if fin_evento >= inicio - margen and inicio_evento <= fin + margen:
                asociados.append(evento)
                break
    candidato["eventos_visuales"] = asociados
    return candidato


def texto_eventos_visuales(eventos):
    if not eventos:
        return "No hay eventos visuales disponibles para este bloque."
    lineas = []
    for evento in eventos:
        try:
            lineas.append(
                f"- {float(evento['inicio']):.2f}-{float(evento['fin']):.2f}: "
                f"{evento.get('descripcion', evento.get('tipo', 'cambio visual'))}"
            )
        except (KeyError, TypeError, ValueError):
            continue
    return "\n".join(lineas) if lineas else "No hay eventos visuales validos para este bloque."


def normalizar_candidato(candidato, duracion_stream):
    """Valida el contrato temporal y sincroniza inicio, fin y segmentos."""
    if not isinstance(candidato, dict):
        return None

    segmentos_compuestos = candidato.get("segmentos")
    if isinstance(segmentos_compuestos, list) and segmentos_compuestos:
        limpios = []
        for segmento in segmentos_compuestos:
            try:
                inicio = float(segmento["inicio"])
                fin = float(segmento["fin"])
            except (KeyError, TypeError, ValueError):
                continue
            if inicio < 0 or fin > duracion_stream or fin - inicio <= DURACION_MIN_SEGMENTO:
                continue
            limpios.append((inicio, fin))

        normalizados = normalizar_segmentos_sin_duplicados(
            [{"inicio": inicio, "fin": fin} for inicio, fin in limpios],
            duracion_minima=DURACION_MIN_SEGMENTO,
        )

        if len(normalizados) > 1:
            candidato["segmentos"] = normalizados
            candidato["inicio"] = normalizados[0]["inicio"]
            candidato["fin"] = normalizados[-1]["fin"]
            return candidato
        if len(normalizados) == 1:
            candidato["inicio"] = normalizados[0]["inicio"]
            candidato["fin"] = normalizados[0]["fin"]
        candidato.pop("segmentos", None)

    try:
        inicio = float(candidato["inicio"])
        fin = float(candidato["fin"])
    except (KeyError, TypeError, ValueError):
        return None
    if inicio < 0 or fin > duracion_stream or fin - inicio <= DURACION_MIN_SEGMENTO:
        return None
    candidato["inicio"] = round(inicio, 2)
    candidato["fin"] = round(fin, 2)
    return candidato

CRITERIOS = """Busca momentos que un editor humano realmente publicaría, no simplemente eventos detectados.

PRIORIZA:
- payoff claro: algo cambia, se resuelve, sorprende o remata.
- hook: hay una razón inmediata para seguir mirando.
- contexto suficiente: se entiende sin conocer todo el stream.
- reacción, humor, tensión, descubrimiento, habilidad o consecuencia real.
- momentos con identidad propia: una situación concreta que se puede contar en una frase.
- historias donde setup -> desarrollo -> giro/clímax -> reacción/payoff estén presentes.

RECHAZA O BAJA PRIORIDAD:
- caminar, explorar, lootear o combate rutinario sin giro.
- conversaciones normales sin remate.
- gritos sin causa/contexto.
- una reacción cuyo motivo ocurre fuera del candidato.
- relleno, espera, repetición o explicaciones largas que no cambian la historia.
- momentos importantes para el gameplay pero poco interesantes para un espectador.

Las líneas "REACCION FUERTE DE AUDIO DETECTADA" son evidencia real del audio: ayudan a localizar picos, pero nunca convierten por sí solas un momento en buen clip."""

REGLAS_ESTRUCTURA = f"""Identifica DOS TIPOS de candidatos y piensa como editor profesional de clips publicables:

Antes de proponer un candidato reconstruye mentalmente la secuencia CAUSA/SETUP -> EVENTO/GIRO -> REACCION -> CONSECUENCIA/PAYOFF cuando exista. No es obligatorio que tenga todas las etapas: un momento instantáneo puede ser EVENTO -> REACCION y una historia puede tener SETUP -> DESARROLLO -> CLIMAX -> PAYOFF.

No confundas importancia para el jugador con valor para el espectador. Un momento solo es candidato fuerte si hay algo que el espectador pueda entender, sentir, anticipar, descubrir, reír o comentar.



TIPO "completo": un momento independiente o una historia que tenga valor editorial real. La duración mínima configurada es {DURACION_MIN} s y la máxima es {TEXTO_MAXIMO}; son límites de la pieza FINAL (la suma de sus tramos), no motivo para ignorar un gran momento. No descartes un evento porque inicialmente sea corto: primero intenta reconstruir el mínimo con causa, contexto, reacción o consecuencia que estén realmente cerca y sean útiles. Si no existe material útil suficiente dentro del máximo, descártalo.

TIPO "corto": momento breve que funciona como clip independiente o como beat útil para construir un resumen. No lo marques solo porque haya un cambio de escena o un pico de audio.

Para CADA candidato incluye además este objeto "valor_editorial" con números 0..1:
{{
  "impacto": 0..1, "hook": 0..1, "payoff": 0..1, "autonomia": 0..1,
  "contexto_suficiente": 0..1, "sorpresa": 0..1, "reaccion": 0..1,
  "humor": 0..1, "habilidad": 0..1, "descubrimiento": 0..1, "consecuencia": 0..1,
  "watchability": 0..1, "repeticion": 0..1, "rutina": 0..1, "contexto_excesivo": 0..1
}}

"watchability": si alguien que nunca vio el stream empieza aquí, ¿hay una razón clara para quedarse?
"autonomia": ¿se entiende el momento con el material seleccionado?
"payoff": alto solo si existe un resultado/remate/reacción real, no solo una promesa.
No inventes puntuaciones altas: si la evidencia no está en la transcripción, usa valores bajos.

Para inicio/fin: empieza antes de la causa o frase que haga comprensible el evento; termina después del resultado, remate o reacción útil. Nunca cortes una frase importante solo para cuadrar duración. Un silencio puede conservarse si funciona como tensión, expectativa o reacción.

Revisa todo el bloque antes de responder. Devuelve pocos candidatos pero de calidad. Es preferible devolver 4 momentos excelentes que 15 mediocres."""

CONTRATO_SEGMENTOS = """Cada candidato puede ser continuo o compuesto. El campo "segmentos" es OPCIONAL:
- Para un momento continuo, usa "inicio" y "fin" normalmente.
- Usa "segmentos" cuando haya partes intermedias poco relevantes (explicaciones, pausas, relleno, repeticiones) que se puedan quitar conservando un hook fuerte al inicio, el clímax y el remate. Si un gran momento se pasa del máximo, es MEJOR quitar esos tramos de en medio que descartar el momento o cortarle el final. La suma de los tramos debe respetar el máximo.
- Si usas "segmentos", entrega una lista ordenada de objetos {"inicio": número, "fin": número}; no deben solaparse. "inicio" debe ser el inicio del primer segmento y "fin" el fin del último.
- No generes segmentos para todos los clips: un intervalo continuo es la opción normal cuando no hay un salto editorial justificado.
"""

FORMATO_TITULO = """Para los momentos "completo", genera un "titulo" corto (máximo 6 palabras) tipo titular de noticia, describiendo QUÉ pasa.
Ejemplos de buen titulo: "Se cae del yate en la propuesta", "Clutch imposible en el ultimo segundo".
Para los momentos "corto", deja "titulo" como cadena vacía "" (no hace falta título individual, se le pondrá un título al resumen completo después)."""

def pedir_a_ia(prompt, intentos=3):
    """Pide una respuesta JSON a la IA configurada (Configuracion > IA).

    Un fallo pasajero (red, limite de uso, respuesta vacia) devuelve None y quien
    llama omite ese bloque. Un fallo de configuracion (sin clave, clave invalida,
    modelo inexistente) detiene el proceso, porque fallaria igual en todos los bloques."""
    try:
        contenido = llm_cliente.pedir(prompt, intentos=intentos)
    except llm_cliente.ErrorLLM as exc:
        if exc.fatal:
            print(f"\nERROR de configuracion de la IA: {exc}")
            raise SystemExit(1)
        print(f"     ({exc})")
        return None
    if "```" in contenido:
        contenido = contenido.split("```")[1].replace("json", "", 1).strip()
    return contenido


def en_paralelo(funcion, elementos):
    """Aplica ``funcion`` a cada elemento con hilos y devuelve los resultados EN ORDEN.

    Las peticiones a la IA son de red (no consumen CPU), asi que van en paralelo;
    el tope real lo fija LLM_CONCURRENCIA dentro de llm_cliente."""
    elementos = list(elementos)
    trabajadores = min(len(elementos), llm_cliente.configuracion_llm()["concurrencia"])
    if trabajadores <= 1:
        return [funcion(e) for e in elementos]
    with ThreadPoolExecutor(max_workers=trabajadores) as pool:
        return list(pool.map(funcion, elementos))

def parsear_momentos(contenido):
    try:
        datos = json.loads(contenido)
        for d in datos:
            d.setdefault("titulo", "clip")
            d.setdefault("razon", "")
            d.setdefault("tipo", "completo")
        return datos
    except json.JSONDecodeError:
        matches = PATRON_MOMENTO.findall(contenido)
        return [
            {"tipo": tipo, "inicio": float(ini), "fin": float(fin), "titulo": tit, "razon": razon}
            for tipo, ini, fin, tit, razon in matches
        ]

PATRON_FIN_REAL = re.compile(r'"fin_real"\s*:\s*([\d.]+)')

def refinar_final_real(candidato, linea_tiempo, margen_busqueda=240):
    inicio = candidato["inicio"]

    unidad = UNIDADES_POR_ID.get(candidato.get("unidad_narrativa"))
    limite_unidad = float(unidad["fin"]) if unidad else None

    # El limite superior real es el mas restrictivo entre: el margen de
    # busqueda de siempre, DURACION_MAX_CLIP (si esta configurado), y el
    # fin de la unidad narrativa asignada. Nunca se cruza a otra unidad.
    limite_max = inicio + margen_busqueda
    if DURACION_MAX_CLIP > 0:
        limite_max = min(limite_max, inicio + DURACION_MAX_CLIP)
    if limite_unidad is not None:
        limite_max = min(limite_max, limite_unidad)

    if limite_max <= inicio:
        candidato["fin"] = round(inicio, 2)
        return candidato

    ventana = [
        item for item in linea_tiempo
        if inicio - 10 <= item["inicio"] <= limite_max
    ]
    if not ventana:
        candidato["fin"] = round(min(float(candidato["fin"]), limite_max), 2)
        return candidato

    texto_ventana = "\n".join(
        f"[{item['inicio']}s - {item['fin']}s] {'🔊 ' if item['tipo']=='audio' else ''}{item['texto']}"
        for item in ventana
    )

    prompt = f"""Este es el inicio de un momento/historia detectado en un directo: "{candidato.get('titulo','')}" ({candidato.get('razon','')}), que arranca en el segundo {inicio}.

Aquí está la transcripción desde un poco antes de ese punto hasta el segundo {limite_max:.2f} (limite absoluto - el momento pertenece a una unidad narrativa que termina ahi, no puede pasar de ese punto):

{texto_ventana}

Tu tarea: encuentra el segundo EXACTO donde esta historia/momento específico realmente termina de resolverse (el remate del chiste, el resultado final de la jugada, el cierre natural de la anécdota), SIN pasar del segundo {limite_max:.2f}. No te quedes corto — sigue leyendo hasta encontrar la resolución real dentro de ese límite.

Devuelve SOLO un JSON válido, sin texto extra, con este formato:
{{"fin_real": 123.4, "cita": "la frase o linea exacta donde ocurre el remate/final, copiada del texto de arriba"}}

Si el momento termina dentro de los primeros segundos del texto (fue breve), pon ese timestamp igual. Si el límite de {limite_max:.2f} no alcanza para ver el final, pon el timestamp mas alto disponible en el texto (nunca superior a {limite_max:.2f})."""

    contenido = pedir_a_ia(prompt, intentos=2)
    if not contenido:
        candidato["fin"] = round(min(float(candidato["fin"]), limite_max), 2)
        return candidato

    try:
        datos = json.loads(contenido)
        fin_real = float(datos.get("fin_real", candidato["fin"]))
    except (json.JSONDecodeError, ValueError, TypeError):
        m = PATRON_FIN_REAL.search(contenido)
        fin_real = float(m.group(1)) if m else candidato["fin"]

    fin_real = min(fin_real, limite_max)

    if fin_real > inicio:
        candidato["fin"] = round(fin_real, 2)
    else:
        candidato["fin"] = round(min(float(candidato["fin"]), limite_max), 2)

    return candidato

# --- Recoleccion de candidatos (completos + cortos) por bloque ---
candidatos_completos = []
candidatos_cortos = []

def analizar_bloque(par):
    i, bloque = par
    lineas_texto = []
    for item in bloque:
        if item["tipo"] == "audio":
            lineas_texto.append(f"[{item['inicio']}s - {item['fin']}s] 🔊 {item['texto']}")
        else:
            lineas_texto.append(f"[{item['inicio']}s - {item['fin']}s] {item['texto']}")
    texto = "\n".join(lineas_texto)
    inicio_bloque = min(float(item["inicio"]) for item in bloque)
    fin_bloque = max(float(item["fin"]) for item in bloque)
    visuales_bloque = [
        evento for evento in eventos_visuales
        if float(evento["fin"]) >= inicio_bloque - MARGEN_EVENTO_VISUAL
        and float(evento["inicio"]) <= fin_bloque + MARGEN_EVENTO_VISUAL
    ]
    contexto_visual = texto_eventos_visuales(visuales_bloque)

    bloque_capas = ""
    if CAPAS_ACTIVAS:
        try:
            with _medir("capa1_seg"):
                bloque_capas = seleccion_capas.construir_bloque_prompt(
                    seleccion_capas.pistas_para_prompt(LINEAS_PUNTUADAS, inicio_bloque, fin_bloque, PARAMS_CAPAS),
                    PARAMS_CAPAS,
                )
        except Exception as exc:
            print(f"[capas] ADVERTENCIA: no se pudo armar el bloque de capas ({exc}); este bloque usa el prompt actual.")

    prompt = f"""Esta es una transcripción de un directo/livestream de gaming (bloque {i} de {len(bloques)}), incluyendo diálogo y picos de audio detectados:

{texto}

Eventos visuales reales asociados a este bloque:
{contexto_visual}

Usa los eventos visuales solo como senal complementaria: un cambio visual por si solo NO hace que un momento sea buen clip. Prioriza siempre contexto, narrativa, reaccion y gameplay de la transcripcion.

Contexto de juego inferido (solo pista, no evidencia temporal): juego={CONTEXTO_JUEGO['juego']}, situacion={CONTEXTO_JUEGO['situacion']}, objetivo={CONTEXTO_JUEGO['objetivo_actual']}, confianza={CONTEXTO_JUEGO['confianza']}. Si es incierto, no inventes hechos ni el juego.

{CRITERIOS}

{REGLAS_ESTRUCTURA}

{CONTRATO_SEGMENTOS}

{FORMATO_TITULO}
{CONTEXTO_CALIBRACION}{bloque_capas}

Devuelve SOLO un JSON válido (sin texto extra), una lista con AMBOS tipos mezclados. Ejemplos válidos:
[{{"tipo": "completo", "inicio": 0.0, "fin": 55.0, "titulo": "titulo llamativo aqui", "razon": "breve descripcion"}}, {{"tipo": "corto", "inicio": 200.0, "fin": 208.0, "titulo": "", "razon": "breve descripcion"}}, {{"tipo": "completo", "inicio": 100.0, "fin": 200.0, "segmentos": [{{"inicio": 100.0, "fin": 120.0}}, {{"inicio": 145.0, "fin": 170.0}}, {{"inicio": 185.0, "fin": 200.0}}], "titulo": "titulo compuesto", "razon": "los saltos eliminan partes intermedias sin romper el arco"}}]

Si de verdad no hay nada que cumpla los criterios, devuelve: []
"""

    print(f"Analizando bloque {i}/{len(bloques)}...")
    with _medir("llm_seg"):
        contenido = pedir_a_ia(prompt)

    if not contenido:
        print(f"  -> Bloque {i}: sin respuesta tras varios intentos, se omite.")
        return [], []

    crudos = parsear_momentos(contenido)
    DIAG.propuesto(len(crudos))
    momentos = []
    for momento in crudos:
        candidato = normalizar_candidato(momento, duracion_total)
        if candidato is None:
            DIAG.perdido(momento if isinstance(momento, dict) and "inicio" in momento and "fin" in momento else {"inicio": 0, "fin": 0},
                         "lectura", "tiempos_invalidos")
        else:
            momentos.append(candidato)
    if CAPAS_ACTIVAS:
        # Capa 4 (solo "completo"; los "corto" no se tocan). Los limites de duracion aqui son
        # solo el maximo: el minimo se alcanza despues anadiendo contexto.
        with _medir("validacion_seg"):
            momentos = seleccion_capas.enriquecer_lista(
                momentos, ANCLAS_LINEAS, PARAMS_CAPAS, limites=(0.0, float(DURACION_MAX_CLIP or 0)), etiqueta=f"bloque {i}")
    # Un "completo" algo corto no se descarta aqui: mas adelante se le anade contexto
    # (preparar_momento_independiente). Solo los muy breves se tratan como "corto".
    piso_completo = min(float(DURACION_MIN or 0), 10.0)
    completos_bloque = [m for m in momentos if m.get("tipo") == "completo" and duracion_candidato(m) >= piso_completo]
    for m in momentos:
        if m.get("tipo") == "completo" and m not in completos_bloque:
            DIAG.perdido(m, "lectura", "demasiado_breve_para_completo")
    cortos_bloque = [m for m in momentos if m.get("tipo") == "corto" and 1.5 <= duracion_candidato(m) <= 30]

    print(f"  -> Bloque {i}: {len(completos_bloque)} completos, {len(cortos_bloque)} cortos encontrados.")
    return completos_bloque, cortos_bloque


# Los bloques son independientes entre si: se piden a la IA en paralelo (en orden al juntarlos).
for completos_bloque, cortos_bloque in en_paralelo(analizar_bloque, enumerate(bloques, start=1)):
    candidatos_completos.extend(completos_bloque)
    candidatos_cortos.extend(cortos_bloque)


# --- Asociar candidatos a unidades narrativas y deduplicar ---
for c in candidatos_completos:
    asignar_unidad_narrativa(c, anclas_narrativas, duracion_total)
for c in candidatos_cortos:
    asignar_unidad_narrativa(c, anclas_narrativas, duracion_total)

def _solape(a, b):
    return max(0.0, min(float(a["fin"]), float(b["fin"])) - max(float(a["inicio"]), float(b["inicio"])))

def _dur(c):
    return duracion_candidato(c)

def _fuerza(c):
    # score_bruto no esta recortado a 100: si muchos candidatos saturan el score,
    # sin esto la duracion (0.01/s) decidia cual gana.
    base = c.get("score_bruto", c.get("score", 0))
    if CAPAS_ACTIVAS:
        base = seleccion_capas.mezclar_score(base, c.get("viralidad"), PARAMS_CAPAS)  # peso 0 = sin efecto
    return float(base) + min(_dur(c), 180.0) * 0.01

def deduplicar_narrativo(candidatos):
    unicos = []
    for c in sorted(candidatos, key=lambda x: x["inicio"]):
        repetido = False
        for u in unicos:
            solape = _solape(c, u)
            minimo = min(_dur(c), _dur(u))
            porcentaje = solape / minimo if minimo else 0
            misma_unidad = c.get("unidad_narrativa") == u.get("unidad_narrativa")
            if (solape >= 12 or porcentaje >= 0.35) and (misma_unidad or solape >= 20):
                if _fuerza(c) > _fuerza(u):
                    unicos.remove(u)
                    unicos.append(c)
                repetido = True
                break
        if not repetido:
            unicos.append(c)
    return sorted(unicos, key=lambda x: x["inicio"])

_antes_dedup = list(candidatos_completos)
candidatos_completos = deduplicar_narrativo(candidatos_completos)
DIAG.perdidos_entre(_antes_dedup, candidatos_completos, "duplicados", "solapado_con_otro_mas_fuerte")
candidatos_cortos = deduplicar_narrativo(candidatos_cortos)

# --- Recorte inteligente: un momento que se pasa del maximo se recorta (la IA decide que
# tramos intermedios sobran) en vez de descartarse. Lo que no se pueda recortar se registra.
MAX_RECORTES_IA = 25
CANDIDATOS_FUERA_DE_RANGO = []
if recorte_ia is not None and DURACION_MAX_CLIP and DURACION_MAX_CLIP > 0:
    _largos = [c for c in candidatos_completos if duracion_candidato(c) > DURACION_MAX_CLIP]
    # Primero los que menos se pasan: son los que mas probablemente se recortan bien.
    _largos.sort(key=lambda c: duracion_candidato(c))
    _a_recortar, _sin_cupo = _largos[:MAX_RECORTES_IA], _largos[MAX_RECORTES_IA:]
    if _a_recortar:
        print(f"Recortando con IA {len(_a_recortar)} momentos que superan el maximo de {DURACION_MAX_CLIP:g} s...")

    def _recortar_uno(c):
        try:
            return recorte_ia.recortar(c, linea_tiempo, DURACION_MAX_CLIP, DURACION_MIN_CLIP, pedir_a_ia)
        except Exception as exc:  # nunca debe tumbar la identificacion
            return None, f"error: {exc}"

    _reemplazos = {}
    for c, (nuevo, motivo) in zip(_a_recortar, en_paralelo(_recortar_uno, _a_recortar)):
        if nuevo is not None:
            _reemplazos[id(c)] = nuevo
        else:
            DIAG.perdido(c, "recorte_ia", motivo or "no_se_pudo_recortar")
            CANDIDATOS_FUERA_DE_RANGO.append({**{k: c.get(k) for k in ("titulo", "razon", "inicio", "fin")},
                                              "duracion": round(duracion_candidato(c), 1), "motivo": motivo})
    for c in _sin_cupo:
        DIAG.perdido(c, "recorte_ia", "sin_cupo_de_recortes_en_este_stream")
        CANDIDATOS_FUERA_DE_RANGO.append({**{k: c.get(k) for k in ("titulo", "razon", "inicio", "fin")},
                                          "duracion": round(duracion_candidato(c), 1), "motivo": "sin_cupo_de_recortes"})
    if _reemplazos:
        candidatos_completos = [_reemplazos.get(id(c), c) for c in candidatos_completos]
        print(f"  -> {len(_reemplazos)} recortados con exito, {len(_a_recortar) - len(_reemplazos)} no se pudieron recortar.")

ARCOS_NARRATIVOS = construir_arcos(
    unidades_narrativas, candidatos_completos + candidatos_cortos,
    CONTEXTO_JUEGO, linea_tiempo,
)
CLASIFICACIONES_NARRATIVAS = clasificar_segmentos(linea_tiempo, ARCOS_NARRATIVOS)
for candidato in candidatos_completos + candidatos_cortos:
    candidato.update(anotar_narrativa(candidato, ARCOS_NARRATIVOS, CLASIFICACIONES_NARRATIVAS))

# Dos descubrimientos en paralelo: los momentos autónomos se conservan como
# tales y cada arco aporta, cuando cabe, una versión comprimida por segmentos.
candidatos_independientes = []
for candidato in candidatos_completos + candidatos_cortos:
    independiente = preparar_momento_independiente(
        candidato, CLASIFICACIONES_NARRATIVAS, DURACION_MIN_CLIP, DURACION_MAX_CLIP
    )
    if independiente is not None:
        candidatos_independientes.append(independiente)
    elif candidato.get("tipo") == "completo":
        _dur_c = duracion_candidato(candidato)
        _motivo = "supera_el_maximo" if (DURACION_MAX_CLIP and _dur_c > DURACION_MAX_CLIP) else "no_alcanza_el_minimo_ni_con_contexto"
        DIAG.perdido(candidato, "validacion_de_duracion", _motivo)
historias_comprimidas = [
    historia for arco in ARCOS_NARRATIVOS
    if (historia := comprimir_arco_narrativo(
        arco, CLASIFICACIONES_NARRATIVAS, linea_tiempo,
        DURACION_MIN_CLIP, DURACION_MAX_CLIP,
    )) is not None
]
candidatos_independientes = deduplicar_narrativo(candidatos_independientes)

for candidato in candidatos_independientes + historias_comprimidas + candidatos_cortos:
    asociar_eventos_visuales(candidato, eventos_visuales)

# Scoring determinista para desempatar candidatos y registrar la señal.
try:
    candidatos_independientes = anotar_candidatos(candidatos_independientes, segmentos, eventos_audio, eventos_visuales, CONTEXTO_JUEGO, PREFERENCIAS_USUARIO)
    historias_comprimidas = anotar_candidatos(historias_comprimidas, segmentos, eventos_audio, eventos_visuales, CONTEXTO_JUEGO, PREFERENCIAS_USUARIO)
    candidatos_cortos = anotar_candidatos(candidatos_cortos, segmentos, eventos_audio, eventos_visuales, CONTEXTO_JUEGO, PREFERENCIAS_USUARIO)
    ruta_scores = os.path.join(CARPETA_RESULTADOS, "scores_clips.json")
    with open(ruta_scores, "w", encoding="utf-8") as f:
        json.dump({"independientes": candidatos_independientes, "historias": historias_comprimidas, "cortos": candidatos_cortos}, f, ensure_ascii=False, indent=2)
    guardar_identidad_artefacto(ruta_scores, video_path, "scores_clips")
except Exception as exc:
    print(f"ADVERTENCIA: no se pudo aplicar scoring determinista: {exc}")

ruta_candidatos_todos = os.path.join(CARPETA_RESULTADOS, "candidatos_todos.json")
with open(ruta_candidatos_todos, "w", encoding="utf-8") as f:
    json.dump(candidatos_independientes + historias_comprimidas, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto(ruta_candidatos_todos, video_path, "candidatos_todos")
ruta_candidatos_cortos = os.path.join(CARPETA_RESULTADOS, "candidatos_cortos.json")
with open(ruta_candidatos_cortos, "w", encoding="utf-8") as f:
    json.dump(candidatos_cortos, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto(ruta_candidatos_cortos, video_path, "candidatos_cortos")

print(f"\nTotal momentos independientes: {len(candidatos_independientes)} | historias comprimidas: {len(historias_comprimidas)}")
print(f"Total candidatos cortos (sin duplicados): {len(candidatos_cortos)}")

# --- Selección final por unidades narrativas ---
MAX_CLIPS = 5

# Pool combinado: ninguna categoría tiene prioridad fija. Cada candidato ya
# cumple MIN/MAX por su propia construcción; las historias no cruzan arcos.
pool_narrativo = [
    c for c in candidatos_independientes if unidad_permite_minimo(c)
] + historias_comprimidas

unidades = {}
for c in pool_narrativo:
    unidades.setdefault(c.get("unidad_narrativa", "sin_ancla"), []).append(c)
for lista in unidades.values():
    lista.sort(key=_fuerza, reverse=True)

# Primera pasada: una pieza por unidad.
top_final = [lista[0] for lista in unidades.values() if lista]

# Si hay menos de 5 unidades, llenamos con candidatos adicionales, pero nunca
# con otro candidato cuyo comienzo esté a menos de 60s de uno ya elegido.
if len(top_final) < MAX_CLIPS:
    restantes = [c for lista in unidades.values() for c in lista[1:]]
    restantes.sort(key=_fuerza, reverse=True)
    for c in restantes:
        if len(top_final) >= MAX_CLIPS:
            break
        if not any(abs(float(c["inicio"]) - float(u["inicio"])) < 60 for u in top_final):
            top_final.append(c)

_ids_elegidos = {id(c) for c in top_final}
for _c in pool_narrativo:
    if id(_c) not in _ids_elegidos:
        DIAG.perdido(_c, "seleccion", "no_elegido_hay_otro_mejor_en_su_unidad_o_cerca")
top_final.sort(key=lambda x: x["inicio"])
print(f"\nSelección narrativa: {len(unidades)} unidades distintas -> {len(top_final)} clips finales.")
for idx, c in enumerate(top_final, 1):
    print(f"  {idx}. unidad={c.get('unidad_narrativa')} | ancla={c.get('ancla_inicio')}s | {c.get('tipo_ancla')}")

print(f"\nRefinando el punto final real de los {len(top_final)} clips completos finales...")


def refinar_clip_final(c):
    if c.get("tipo_candidato") == "historia":
        # Los límites y puntos de corte ya fueron fijados por la compresión.
        return
    fin_original = c["fin"]
    segmentos_original = [dict(s) for s in c["segmentos"]] if c.get("segmentos") else None
    duracion_original = duracion_candidato(c)
    if c.get("segmentos"):
        fin_previo = c["fin"]
        refinar_final_real(c, linea_tiempo)
        if c["fin"] != fin_previo:
            fin_nuevo = c["fin"]
            c["segmentos"][-1]["fin"] = fin_nuevo
            # Ampliar el final no puede hacer que el total supere el maximo (se perderia el clip).
            if DURACION_MAX_CLIP and DURACION_MAX_CLIP > 0 and duracion_candidato(c) > DURACION_MAX_CLIP:
                c["fin"] = fin_previo
                c["segmentos"][-1]["fin"] = fin_previo
    else:
        ajustar_inicio_a_ancla(c, 35.0)
        inicio_fijo = c["inicio"]
        limitar_a_unidad(c)
        refinar_final_real(c, linea_tiempo)
        c["inicio"] = inicio_fijo
        limitar_a_unidad(c)
    normalizar_candidato(c, duracion_total)
    # Si el ajuste del final deja el clip por debajo del minimo (la IA a veces responde un
    # fin_real casi pegado al inicio), se conserva el final que ya tenia: antes el clip se perdia.
    if (DURACION_MIN_CLIP and DURACION_MIN_CLIP > 0 and duracion_candidato(c) < DURACION_MIN_CLIP
            and duracion_original >= DURACION_MIN_CLIP):
        c["fin"] = fin_original
        if segmentos_original:
            c["segmentos"] = segmentos_original
        else:
            c.pop("segmentos", None)
        c["refinado_descartado"] = True


# Cada clip se refina de forma independiente (una peticion a la IA por clip): en paralelo.
en_paralelo(refinar_clip_final, top_final)

# Validacion final de duracion: usa DURACION_MIN_CLIP/DURACION_MAX_CLIP
# (0 = sin limite por ese lado), nunca el DURACION_MIN generico de 40s que
# antes se colaba como minimo oculto aqui.
_antes_final = list(top_final)
top_final = [c for c in top_final if c is not None and cumple_duracion_configurada(c)]
DIAG.perdidos_entre([c for c in _antes_final if c is not None], top_final, "validacion_final", "duracion_fuera_de_rango_tras_refinar")

# El refinamiento puede haber movido los limites: se repite la
# deduplicacion narrativa sobre el resultado final antes de continuar.
top_final = deduplicar_narrativo(top_final)
if CAPAS_ACTIVAS:
    # Capa 4: tras el refinado de la IA, los limites se vuelven a anclar a lineas reales.
    with _medir("validacion_seg"):
        top_final = seleccion_capas.anclar_final(
            top_final, ANCLAS_LINEAS, PARAMS_CAPAS, limites=(DURACION_MIN_CLIP, DURACION_MAX_CLIP))

# El refinamiento puede cambiar timestamps; el scoring y su duración deben
# corresponder siempre a la versión final que se manda al cutter.
for candidato in top_final:
    # Los limites pudieron cambiar durante el refinamiento temporal.
    asociar_eventos_visuales(candidato, eventos_visuales)
for candidato in top_final:
    candidato.update(anotar_narrativa(candidato, ARCOS_NARRATIVOS, CLASIFICACIONES_NARRATIVAS))
    candidato.setdefault("feedback", {"rating": None, "liked": None, "timestamp": None})
top_final = anotar_candidatos(top_final, segmentos, eventos_audio, eventos_visuales, CONTEXTO_JUEGO, PREFERENCIAS_USUARIO)

RUTA_CLIPS_SUGERIDOS = os.path.join(CARPETA_RESULTADOS, "clips_sugeridos.json")
with open(RUTA_CLIPS_SUGERIDOS, "w", encoding="utf-8") as f:
    json.dump(top_final, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto(RUTA_CLIPS_SUGERIDOS, video_path, "clips_sugeridos")

metricas_identificacion = {
    "version": "fase7_editor_profesional_1",
    "version_scoring": "fase7_editor_profesional_1",
    "anclas_narrativas": len(anclas_narrativas),
    "unidades_narrativas": len(unidades),
    "candidatos_completos": len(candidatos_independientes),
    "historias_comprimidas": len(historias_comprimidas),
    "candidatos_cortos": len(candidatos_cortos),
    "clips_finales": len(top_final),
    "duracion_total_clips_finales": round(sum(duracion_candidato(c) for c in top_final), 2),
    "eventos_visuales_disponibles": bool(eventos_visuales),
    "eventos_visuales_total": len(eventos_visuales),
    "candidatos_con_eventos_visuales": sum(
        1 for candidato in candidatos_independientes + historias_comprimidas + candidatos_cortos
        if candidato.get("eventos_visuales")
    ),
    "candidatos_sin_eventos_visuales": sum(
        1 for candidato in candidatos_independientes + historias_comprimidas + candidatos_cortos
        if not candidato.get("eventos_visuales")
    ),
    "juego": CONTEXTO_JUEGO["juego"],
    "confianza_contexto_juego": CONTEXTO_JUEGO["confianza"],
    "arcos_narrativos": len(ARCOS_NARRATIVOS),
    "feedback_historico": len(PREFERENCIAS_USUARIO["feedback"]),
}
if CAPAS_ACTIVAS:
    # Metricas de las capas: solo con el flag activo (con False los archivos quedan como siempre).
    _tiempos_capas = CRONO.resumen()
    _resumen_capas = seleccion_capas.resumen_clips(top_final)
    metricas_identificacion["capas"] = dict(_tiempos_capas, **_resumen_capas)
    seleccion_capas.guardar_metricas_tiempos(
        os.path.join(BASE_DIR, "historial_tiempos_proceso.json"), _tiempos_capas, _resumen_capas)
    print(f"[capas] Tiempos: capa 1 {_tiempos_capas['capa1_seg']}s | IA {_tiempos_capas['llm_seg']}s "
          f"({_tiempos_capas['llamadas_llm']} peticiones) | validacion {_tiempos_capas['validacion_seg']}s")
DIAG.guardar(os.path.join(CARPETA_RESULTADOS, "selector_diagnostico.json"),
             {"clips_finales": len(top_final), "recortados_por_ia": sum(1 for c in top_final if c.get("recortado_por_ia"))})
DIAG.imprimir()
if CANDIDATOS_FUERA_DE_RANGO:
    try:
        with open(os.path.join(CARPETA_RESULTADOS, "fuera_de_rango.json"), "w", encoding="utf-8") as f:
            json.dump(CANDIDATOS_FUERA_DE_RANGO, f, ensure_ascii=False, indent=2)
        print(f"[diagnostico] {len(CANDIDATOS_FUERA_DE_RANGO)} momentos buenos no cupieron en el maximo; revisa resultados/fuera_de_rango.json")
    except OSError:
        pass
ruta_metricas = os.path.join(CARPETA_RESULTADOS, "metricas_identificacion.json")
with open(ruta_metricas, "w", encoding="utf-8") as f:
    json.dump(metricas_identificacion, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto(ruta_metricas, video_path, "metricas_identificacion")

ruta_contexto_juego = os.path.join(CARPETA_RESULTADOS, "juego_contexto.json")
with open(ruta_contexto_juego, "w", encoding="utf-8") as f:
    json.dump(CONTEXTO_JUEGO, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto(ruta_contexto_juego, video_path, "juego_contexto")
ruta_arcos = os.path.join(CARPETA_RESULTADOS, "arcos_narrativos.json")
with open(ruta_arcos, "w", encoding="utf-8") as f:
    json.dump({"arcos": ARCOS_NARRATIVOS, "clasificaciones": CLASIFICACIONES_NARRATIVAS}, f, ensure_ascii=False, indent=2)
guardar_identidad_artefacto(ruta_arcos, video_path, "arcos_narrativos")

print(f"\nListo. Top {len(top_final)} clips completos guardados en clips_sugeridos.json")
for idx, c in enumerate(top_final, start=1):
    duracion = duracion_candidato(c)
    print(f"  {idx}. [{c['inicio']}s - {c['fin']}s] ({duracion:.0f}s) \"{c.get('titulo','')}\" - {c.get('razon','')}")

# --- Armar el "resumen de mejores momentos" con los cortos, en UNA sola llamada extra ---
if len(candidatos_cortos) >= 3:
    lista_cortos = "\n".join(
        f"{idx+1}. [{c['inicio']}s - {c['fin']}s] {c.get('razon','')}\n"
        f"   Eventos visuales asociados:\n{texto_eventos_visuales(c.get('eventos_visuales', []))}"
        for idx, c in enumerate(candidatos_cortos)
    )

    prompt_resumen = f"""Aquí tienes {len(candidatos_cortos)} momentos cortos/sueltos detectados en TODO un directo de gaming (pueden estar muy separados en el tiempo, de distintas partes del stream):

{lista_cortos}

Tu tarea: construye UN SOLO resumen editorial del stream, como lo haría un editor de Shorts. No hagas una lista de "mejores eventos" sin conexión. Elige entre 4 y 10 beats que juntos cuenten una mini-historia o recorrido claro. IMPORTANTE:
- Busca esta estructura cuando exista: HOOK -> contexto mínimo -> escalada/cambio -> momento fuerte -> reacción/payoff.
- Ordénalos normalmente CRONOLÓGICAMENTE, salvo que mover un beat inicial sea necesario para abrir con un hook claramente mejor.
- Elimina espera, caminar, explicaciones redundantes y momentos repetidos.
- No incluyas un beat solo porque sea "importante" para el gameplay: debe aportar comprensión, emoción, humor, tensión o consecuencia.
- No uses más segmentos de los necesarios. Cada beat debe justificar su presencia.
La duración TOTAL combinada debe respetar la configuración final del proyecto cuando exista; si no puede ser bueno dentro del máximo, reduce beats, no cortes arbitrariamente un beat importante.

Devuelve SOLO un JSON válido, sin texto extra, con este formato:
{{"titulo": "titulo llamativo para todo el resumen", "momentos": [{{"inicio": 12.0, "fin": 18.0, "razon": "breve descripcion"}}, ...]}}
"""

    print(f"\nArmando el resumen de mejores momentos a partir de {len(candidatos_cortos)} momentos cortos...")
    contenido_resumen = pedir_a_ia(prompt_resumen)

    resumen_plan = None
    if contenido_resumen:
        try:
            resumen_plan = json.loads(contenido_resumen)
        except json.JSONDecodeError:
            print("No se pudo interpretar el plan de resumen, se omite este extra esta vez.")

    if resumen_plan and resumen_plan.get("momentos"):
        momentos_originales = resumen_plan["momentos"]
        momentos_limpios = normalizar_segmentos_sin_duplicados(momentos_originales)
        if not momentos_limpios:
            print("El resumen contiene momentos temporales inválidos; se omite.")
            resumen_plan = None
        elif len(momentos_limpios) != len(momentos_originales):
            print("ADVERTENCIA: momentos repetidos/solapados en el resumen; se normalizan.")
            resumen_plan["momentos"] = momentos_limpios
        duracion_total_resumen = sum(m["fin"] - m["inicio"] for m in momentos_limpios)
        if resumen_plan and duracion_total_resumen >= DURACION_MIN:
            ruta_resumen_plan = os.path.join(CARPETA_RESULTADOS, "resumen_plan.json")
            with open(ruta_resumen_plan, "w", encoding="utf-8") as f:
                json.dump(resumen_plan, f, ensure_ascii=False, indent=2)
            guardar_identidad_artefacto(ruta_resumen_plan, video_path, "resumen_plan")
            print(f"Listo. Plan de resumen guardado: \"{resumen_plan.get('titulo','')}\" con {len(resumen_plan['momentos'])} momentos ({duracion_total_resumen:.0f}s total).")
        else:
            print(f"El resumen armado quedó muy corto ({duracion_total_resumen:.0f}s), no se genera esta vez.")
    else:
        print("No se generó un plan de resumen válido esta vez.")
else:
    print(f"\nSolo se encontraron {len(candidatos_cortos)} momentos cortos, no alcanza para armar un resumen (se necesitan al menos 3).")
