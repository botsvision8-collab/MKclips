# -*- coding: utf-8 -*-
"""Modelo de edición no destructivo del editor nativo.

Las decisiones de edición se guardan en ``<clip>.edicion.json`` junto al clip; el clip
original no se toca nunca. Todos los tiempos de ``segmentos`` y de los subtítulos son
segundos del CLIP ORIGINAL; la línea de tiempo de salida se calcula quitando los huecos.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re

VERSION = 1
SALIDA_DEFECTO = {"ancho": 1080, "alto": 1920}
MODOS_ENCUADRE = ("recorte", "ajustar", "dividido", "tres", "capas")
ROLES_CAPA = ("juego", "cam", "fondo", "otro")
FORMAS_CAPA = ("rect", "redondeado", "circulo")
MAX_CAPAS = 6
DURACION_MINIMA_SEGMENTO = 0.2
MAX_HABLANTES = 4
COLORES_HABLANTES = ["#FFFFFF", "#6EC1FF", "#FFB347", "#9BE564"]
TIPOS_EXTRA = ("video", "audio", "imagen")
MAX_EXTRAS = 80
MAX_PISTAS = 6

ESTILO_DEFECTO = {
    "fuente": "Arial", "tamano": 84, "color": "#FFFFFF", "color_resaltado": "#FFE600",
    "color_contorno": "#000000", "grosor_contorno": 6, "fondo": "ninguno", "color_fondo": "#000000",
    "negrita": True, "cursiva": False, "mayusculas": False, "resaltar_palabra": True,
    "palabras_por_pagina": 3, "posicion_y": 0.72, "hablantes": COLORES_HABLANTES,
}


# ----------------------------------------------------------------------------- archivo
_RESERVADOS_WIN = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def limpiar_nombre(texto, defecto=""):
    """Nombre de archivo o carpeta válido en Windows: sin caracteres prohibidos, sin «.mp4» final ni nombres reservados."""
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(texto or "")).strip()
    t = re.sub(r"\.mp4$", "", t, flags=re.I).strip().rstrip(". ")
    if t.split(".")[0].upper() in _RESERVADOS_WIN:
        t = "_" + t
    return t[:120].rstrip(". ") or defecto


def id_de_clip(ruta):
    """Identificador estable de un clip (hash de su ruta); lo usan la app y las rutas del editor."""
    return hashlib.sha1(os.path.normcase(os.path.abspath(ruta)).encode("utf-8")).hexdigest()[:16]


def ruta_edicion(ruta_clip):
    return str(ruta_clip) + ".edicion.json"


def _num(valor, defecto, minimo=None, maximo=None):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return defecto
    if v != v or v in (float("inf"), float("-inf")):
        return defecto
    if minimo is not None:
        v = max(minimo, v)
    if maximo is not None:
        v = min(maximo, v)
    return v


def _color(valor, defecto):
    texto = str(valor or "").strip()
    return texto.upper() if re.fullmatch(r"#[0-9a-fA-F]{6}", texto) else defecto


def _rect(valor, defecto):
    if not isinstance(valor, dict):
        return dict(defecto)
    x = _num(valor.get("x"), defecto["x"], 0.0, 1.0)
    y = _num(valor.get("y"), defecto["y"], 0.0, 1.0)
    w = _num(valor.get("w"), defecto["w"], 0.02, 1.0)
    h = _num(valor.get("h"), defecto["h"], 0.02, 1.0)
    return {"x": min(x, 1.0 - w), "y": min(y, 1.0 - h), "w": w, "h": h}


def normalizar_segmentos(segmentos, duracion):
    """Segmentos ordenados, dentro de [0, duracion], sin solapes y de al menos 0.2 s."""
    limpios = []
    for s in segmentos or []:
        if not isinstance(s, dict):
            continue
        i = _num(s.get("inicio"), None, 0.0, duracion)
        f = _num(s.get("fin"), None, 0.0, duracion)
        if i is None or f is None or f - i < DURACION_MINIMA_SEGMENTO:
            continue
        limpios.append({"inicio": round(i, 3), "fin": round(f, 3)})
    limpios.sort(key=lambda s: s["inicio"])
    resultado = []
    for s in limpios:
        if resultado and s["inicio"] < resultado[-1]["fin"]:
            s = {"inicio": resultado[-1]["fin"], "fin": s["fin"]}
            if s["fin"] - s["inicio"] < DURACION_MINIMA_SEGMENTO:
                continue
        resultado.append(s)
    return resultado or [{"inicio": 0.0, "fin": round(duracion, 3)}]


def _normalizar_palabras(palabras, inicio, fin):
    resultado = []
    for p in palabras or []:
        if not isinstance(p, dict) or not str(p.get("texto", "")).strip():
            continue
        i = _num(p.get("inicio"), inicio, inicio, fin)
        f = _num(p.get("fin"), i, i, fin)
        palabra = {"inicio": round(i, 3), "fin": round(max(f, i), 3), "texto": str(p["texto"]).strip()}
        color = str(p.get("color") or "").strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            palabra["color"] = color.upper()
        resultado.append(palabra)
    return resultado


def repartir_palabras(texto, inicio, fin):
    """Palabras con tiempos repartidos en proporción a su longitud (cuando no hay tiempos reales)."""
    tokens = str(texto or "").split()
    if not tokens:
        return []
    pesos = [max(1, len(t)) for t in tokens]
    total, cursor, resultado = float(sum(pesos)), float(inicio), []
    for token, peso in zip(tokens, pesos):
        siguiente = cursor + (fin - inicio) * peso / total
        resultado.append({"inicio": round(cursor, 3), "fin": round(siguiente, 3), "texto": token})
        cursor = siguiente
    return resultado


def normalizar_lineas(lineas, duracion):
    resultado = []
    for linea in lineas or []:
        if not isinstance(linea, dict):
            continue
        texto = re.sub(r"\s+", " ", str(linea.get("texto", ""))).strip()
        i = _num(linea.get("inicio"), None, 0.0, duracion)
        f = _num(linea.get("fin"), None, 0.0, duracion)
        if not texto or i is None or f is None or f - i < 0.05:
            continue
        palabras = _normalizar_palabras(linea.get("palabras"), i, f)
        if not palabras or " ".join(p["texto"] for p in palabras) != texto:
            palabras = repartir_palabras(texto, i, f)
        linea_norm = {"inicio": round(i, 3), "fin": round(f, 3), "texto": texto, "palabras": palabras}
        hablante = int(_num(linea.get("hablante"), 0, 0, MAX_HABLANTES))
        if hablante:
            linea_norm["hablante"] = hablante
        resultado.append(linea_norm)
    resultado.sort(key=lambda l: l["inicio"])
    return resultado


def _colores_hablantes(valor):
    lista = list(valor) if isinstance(valor, (list, tuple)) else []
    return [_color(lista[i] if i < len(lista) else None, COLORES_HABLANTES[i]) for i in range(MAX_HABLANTES)]


def normalizar_estilo(estilo, fuente_por_defecto="Arial"):
    base = dict(ESTILO_DEFECTO, fuente=fuente_por_defecto)
    e = estilo if isinstance(estilo, dict) else {}
    return {
        "fuente": str(e.get("fuente") or base["fuente"])[:80],
        "tamano": int(_num(e.get("tamano"), base["tamano"], 20, 220)),
        "color": _color(e.get("color"), base["color"]),
        "color_resaltado": _color(e.get("color_resaltado"), base["color_resaltado"]),
        "color_contorno": _color(e.get("color_contorno"), base["color_contorno"]),
        "grosor_contorno": int(_num(e.get("grosor_contorno"), base["grosor_contorno"], 0, 24)),
        "fondo": "caja" if e.get("fondo") == "caja" else "ninguno",
        "color_fondo": _color(e.get("color_fondo"), base["color_fondo"]),
        "negrita": bool(e.get("negrita", base["negrita"])),
        "cursiva": bool(e.get("cursiva", base["cursiva"])),
        "mayusculas": bool(e.get("mayusculas", base["mayusculas"])),
        "resaltar_palabra": bool(e.get("resaltar_palabra", base["resaltar_palabra"])),
        "palabras_por_pagina": int(_num(e.get("palabras_por_pagina"), base["palabras_por_pagina"], 1, 12)),
        "posicion_y": _num(e.get("posicion_y"), base["posicion_y"], 0.05, 0.95),
        "hablantes": _colores_hablantes(e.get("hablantes")),
    }


def normalizar_extras(extras):
    """Elementos de las pistas extra (B-roll, imágenes y audios). Tiempos de ``t`` en la línea de tiempo de SALIDA."""
    resultado, vistos = [], set()
    for n, e in enumerate(extras if isinstance(extras, list) else []):
        if not isinstance(e, dict) or len(resultado) >= MAX_EXTRAS:
            continue
        tipo = e.get("tipo")
        archivo = str(e.get("archivo") or "").strip()[:1024]
        if tipo not in TIPOS_EXTRA or not archivo:
            continue
        ident = re.sub(r"[^a-zA-Z0-9_-]", "", str(e.get("id") or ""))[:40] or f"x{n}"
        while ident in vistos:
            ident += "_"
        vistos.add(ident)
        dur_medio = _num(e.get("dur_medio"), 0.0, 0.0, 86400.0)
        desde = _num(e.get("desde"), 0.0, 0.0, 86400.0)
        dur = _num(e.get("dur"), 1.0, 0.1, 86400.0)
        velocidad = 1.0 if tipo == "imagen" else _num(e.get("velocidad"), 1.0, 0.1, 10.0)
        if tipo != "imagen" and dur_medio > 0.2:
            desde = min(desde, dur_medio - 0.1)
            dur = max(0.1, min(dur, (dur_medio - desde) / velocidad))      # ``dur`` es de salida; el medio gasta dur × velocidad
        fi = _num(e.get("fundido_in"), 0.0, 0.0, 10.0)
        fo = _num(e.get("fundido_out"), 0.0, 0.0, 10.0)
        if fi + fo > dur:
            fi, fo = dur / 2.0, dur / 2.0
        rc = e.get("recuadro") if isinstance(e.get("recuadro"), dict) else {}
        w = _num(rc.get("w"), 0.4, 0.1, 1.0)
        resultado.append({
            "id": ident, "tipo": tipo, "archivo": archivo, "pista": int(_num(e.get("pista"), 1, 1, MAX_PISTAS)),
            "t": round(_num(e.get("t"), 0.0, 0.0, 36000.0), 3), "desde": round(desde, 3), "dur": round(dur, 3),
            "volumen": round(_num(e.get("volumen"), 1.0, 0.0, 2.0), 3), "velocidad": round(velocidad, 4),
            "audio": True if tipo == "audio" else (False if tipo == "imagen" else bool(e.get("audio", False))),
            "fundido_in": round(fi, 3), "fundido_out": round(fo, 3),
            "modo": "recuadro" if e.get("modo") == "recuadro" else "cubrir",
            "recuadro": {"x": _num(rc.get("x"), 0.55, 0.0, 1.0 - w), "y": _num(rc.get("y"), 0.05, 0.0, 1.0), "w": w},
            "dur_medio": round(dur_medio, 3), "ancho": int(_num(e.get("ancho"), 0, 0, 20000)), "alto": int(_num(e.get("alto"), 0, 0, 20000)),
            "tiene_audio": bool(e.get("tiene_audio", tipo == "audio")),
            "nombre": str(e.get("nombre") or os.path.basename(archivo))[:120],
            "mid": re.sub(r"[^a-f0-9]", "", str(e.get("mid") or ""))[:40],
        })
    return resultado


def normalizar_pistas(pistas, extras):
    p = pistas if isinstance(pistas, dict) else {}
    nv = int(_num(p.get("video"), 1, 1, MAX_PISTAS))
    na = int(_num(p.get("audio"), 1, 1, MAX_PISTAS))
    for e in extras:                                   # nunca hay elementos en pistas que no existen
        if e["tipo"] == "audio":
            na = max(na, e["pista"])
        else:
            nv = max(nv, e["pista"])
    valido = lambda lista: sorted({str(x) for x in (lista if isinstance(lista, list) else []) if re.fullmatch(r"[VA][1-9]", str(x))})
    return {"video": nv, "audio": na, "ocultas": valido(p.get("ocultas")), "silenciadas": valido(p.get("silenciadas")),
            "bloqueadas": valido(p.get("bloqueadas")), "bloqueo": bool(p.get("bloqueo", False))}


def edicion_nueva(ruta_clip, duracion, ancho, alto, pistas_audio=1, fps=30.0, fuente_por_defecto="Arial"):
    ancho_salida, alto_salida = SALIDA_DEFECTO["ancho"], SALIDA_DEFECTO["alto"]
    es_vertical = alto >= ancho
    try:
        from . import editor_piezas as piezas
    except ImportError:
        import editor_piezas as piezas
    return {
        "version": VERSION, "clip": str(ruta_clip),
        "origen": {"ancho": int(ancho), "alto": int(alto), "duracion": round(float(duracion), 3),
                   "pistas_audio": int(pistas_audio), "fps": round(float(fps), 3)},
        "salida": {"ancho": ancho_salida, "alto": alto_salida, "nombre": "", "no_sobrescribir": False},
        "segmentos": [{"inicio": 0.0, "fin": round(float(duracion), 3)}],
        "encuadre": {
            "modo": "recorte" if es_vertical else "ajustar",
            "recorte": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "arriba": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "abajo": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
            "proporcion_arriba": 0.6,
            "invertido": False,
            "tres": {"a": {"x": 0.2, "y": 0.0, "w": 0.6, "h": 1.0}, "b": {"x": 0.7, "y": 0.55, "w": 0.28, "h": 0.42},
                     "c": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}},
            "orden_tres": ["a", "b", "c"],
            "alturas_tres": [0.34, 0.33],
            "linea": {"ancho": 0, "color": "#FFFFFF"},
            "plantilla": "", "capas": [],
        },
        "subtitulos": {"activos": True, "estilo": normalizar_estilo({}, fuente_por_defecto), "lineas": []},
        "mejora_ia": {"activa": False, "cam": True, "juego": False, "modelo": "rapido"},
        "extras": [], "pistas": {"video": 1, "audio": 1, "ocultas": [], "silenciadas": [], "bloqueadas": [], "bloqueo": False},
        "piezas": piezas.piezas_iniciales(duracion, pistas_audio),
    }


def _orden_tres(valor, por_defecto):
    return list(valor) if isinstance(valor, list) and sorted(valor) == ["a", "b", "c"] else list(por_defecto)


def _alturas_tres(valor, por_defecto):
    v = valor if isinstance(valor, list) and len(valor) == 2 else por_defecto
    a, b = _num(v[0], por_defecto[0], 0.1, 0.7), _num(v[1], por_defecto[1], 0.1, 0.7)
    if a + b > 0.9:
        a, b = a * 0.9 / (a + b), b * 0.9 / (a + b)
    return [round(a, 4), round(b, 4)]


_COMPLETO = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}


def normalizar_capas(valor):
    """Capas del modo «capas» (plantillas): cada una recorta una zona del clip y la pone en un rectángulo de la salida.

    Se dibujan en orden: la primera es el fondo (se rellena de negro lo que no cubra)."""
    if not isinstance(valor, list):
        return []
    resultado = []
    for i, c in enumerate(valor[:MAX_CAPAS]):
        if not isinstance(c, dict):
            continue
        borde = c.get("borde") if isinstance(c.get("borde"), dict) else {}
        resultado.append({
            "id": re.sub(r"[^A-Za-z0-9_-]", "", str(c.get("id") or f"c{i}"))[:16] or f"c{i}",
            "rol": c.get("rol") if c.get("rol") in ROLES_CAPA else "otro",
            "fuente": _rect(c.get("fuente"), _COMPLETO),
            "destino": _rect(c.get("destino"), _COMPLETO),
            "ajuste": "contener" if c.get("ajuste") == "contener" else "llenar",
            "desenfoque": round(_num(c.get("desenfoque"), 0.0, 0.0, 60.0), 1),
            "oscurecer": round(_num(c.get("oscurecer"), 0.0, 0.0, 0.8), 2),
            "forma": c.get("forma") if c.get("forma") in FORMAS_CAPA else "rect",
            "radio": round(_num(c.get("radio"), 0.1, 0.0, 0.5), 3),
            "borde": {"ancho": int(_num(borde.get("ancho"), 0, 0, 40)), "color": _color(borde.get("color"), "#FFFFFF")},
        })
    return resultado


def normalizar_encuadre(enc, be):
    """Encuadre validado (el general del clip o el de una pieza); ``be`` aporta los valores por defecto."""
    enc = enc if isinstance(enc, dict) else {}
    seg = enc.get("seguimiento_cara") if isinstance(enc.get("seguimiento_cara"), dict) else {}
    return {
        "modo": enc.get("modo") if enc.get("modo") in MODOS_ENCUADRE else be["modo"],
        "recorte": _rect(enc.get("recorte"), be["recorte"]),
        "arriba": _rect(enc.get("arriba"), be["arriba"]),
        "abajo": _rect(enc.get("abajo"), be["abajo"]),
        "proporcion_arriba": _num(enc.get("proporcion_arriba"), be["proporcion_arriba"], 0.2, 0.8),
        "invertido": bool(enc.get("invertido", be["invertido"])),
        "tres": {k: _rect((enc.get("tres") or {}).get(k) if isinstance(enc.get("tres"), dict) else None, be["tres"][k]) for k in ("a", "b", "c")},
        "orden_tres": _orden_tres(enc.get("orden_tres"), be["orden_tres"]),
        "alturas_tres": _alturas_tres(enc.get("alturas_tres"), be["alturas_tres"]),
        "linea": {"ancho": int(_num((enc.get("linea") or {}).get("ancho") if isinstance(enc.get("linea"), dict) else None, be["linea"]["ancho"], 0, 40)),
                  "color": _color((enc.get("linea") or {}).get("color") if isinstance(enc.get("linea"), dict) else None, be["linea"]["color"])},
        "plantilla": re.sub(r"[^A-Za-z0-9_-]", "", str(enc.get("plantilla") or ""))[:32],
        "capas": normalizar_capas(enc.get("capas", be.get("capas"))),
        "seguimiento_cara": {
            "activo": bool(seg.get("activo", False)),
            "suavidad": round(_num(seg.get("suavidad"), .70, .05, .95), 3),
            "zoom": round(_num(seg.get("zoom"), 1.20, 1.0, 2.5), 3),
            "perdida": "centro" if seg.get("perdida") == "centro" else "mantener",
            "trayectoria": [{"t": round(_num(p.get("t"), 0, 0, 86400), 3),
                             "x": round(_num(p.get("x"), .5, 0, 1), 5),
                             "y": round(_num(p.get("y"), .5, 0, 1), 5),
                             "cara": p.get("cara") if isinstance(p.get("cara"), list) else None}
                            for p in seg.get("trayectoria", [])[:20000] if isinstance(p, dict)]
        },
    }


def normalizar_edicion(datos, base):
    """Mezcla ``datos`` (lo que llega del navegador o del disco) sobre ``base`` validando todo."""
    resultado = copy.deepcopy(base)
    if not isinstance(datos, dict):
        return resultado
    duracion = float(base["origen"]["duracion"])
    resultado["segmentos"] = normalizar_segmentos(datos.get("segmentos", base["segmentos"]), duracion)
    resultado["encuadre"] = normalizar_encuadre(datos.get("encuadre"), base["encuadre"])
    sub = datos.get("subtitulos") if isinstance(datos.get("subtitulos"), dict) else {}
    bs = base["subtitulos"]
    resultado["subtitulos"] = {
        "activos": bool(sub.get("activos", bs["activos"])),
        "estilo": normalizar_estilo(sub.get("estilo", bs["estilo"]), bs["estilo"]["fuente"]),
        "lineas": normalizar_lineas(sub.get("lineas", bs["lineas"]), duracion),
    }
    sal = datos.get("salida") if isinstance(datos.get("salida"), dict) else {}
    bsal = base.get("salida") or {}
    resultado["salida"] = {**resultado["salida"], "nombre": limpiar_nombre(sal.get("nombre", bsal.get("nombre", ""))),
                           "no_sobrescribir": bool(sal.get("no_sobrescribir", bsal.get("no_sobrescribir", False)))}
    ia = datos.get("mejora_ia") if isinstance(datos.get("mejora_ia"), dict) else {}
    bia = base.get("mejora_ia") or {"activa": False, "cam": True, "juego": False, "modelo": "rapido"}
    resultado["mejora_ia"] = {"activa": bool(ia.get("activa", bia["activa"])), "cam": bool(ia.get("cam", bia["cam"])), "juego": bool(ia.get("juego", bia["juego"])),
                              "modelo": ia.get("modelo") if ia.get("modelo") in ("rapido", "calidad") else bia["modelo"]}
    try:
        from . import editor_piezas as piezas
    except ImportError:
        import editor_piezas as piezas
    if isinstance(datos.get("piezas"), list):                      # edición nueva: la línea de tiempo son piezas
        lista = piezas.normalizar_piezas(datos["piezas"], base["origen"], resultado["encuadre"])
        pistas = piezas.normalizar_pistas(datos.get("pistas", base.get("pistas")), lista)
    elif "segmentos" not in datos and "extras" not in datos and isinstance(base.get("piezas"), list):
        lista = piezas.normalizar_piezas(base["piezas"], base["origen"], resultado["encuadre"])
        pistas = piezas.normalizar_pistas(datos.get("pistas", base.get("pistas")), lista)
    else:                                                           # edición antigua: tramos + extras -> piezas
        extras = normalizar_extras(datos.get("extras", base.get("extras", [])))
        lista = piezas.normalizar_piezas(piezas.migrar_legacy(resultado["segmentos"], extras, base["origen"]), base["origen"], resultado["encuadre"])
        crudas = datos.get("pistas") if isinstance(datos.get("pistas"), dict) else None
        pistas = piezas.normalizar_pistas(piezas.pistas_de_legacy(crudas) if crudas else base.get("pistas"), lista)
        if crudas:                                                  # silenciar V{n} antes = silenciar el audio de ese video extra
            for v in list(pistas["silenciadas"]):
                if v.startswith("V"):
                    enl = {p["enlace"] for p in lista if p["carril"] == v and p["tipo"] == "video" and p["enlace"]}
                    pistas["silenciadas"] = sorted(set(pistas["silenciadas"]) - {v} | {p["carril"] for p in lista if p["tipo"] == "audio" and p["enlace"] in enl})
    resultado["version"] = piezas.VERSION_PIEZAS
    resultado["piezas"] = lista
    resultado["pistas"] = pistas
    resultado["segmentos"] = piezas.segmentos_derivados(lista, duracion)     # solo para paneles antiguos
    resultado["extras"] = []
    return resultado


def cargar_edicion(ruta_clip):
    """Edición guardada del clip, o None si no hay o está corrupta."""
    try:
        with open(ruta_edicion(ruta_clip), "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


def guardar_edicion(ruta_clip, edicion):
    destino = ruta_edicion(ruta_clip)
    temporal = f"{destino}.{os.getpid()}.tmp"
    with open(temporal, "w", encoding="utf-8") as archivo:
        json.dump(edicion, archivo, ensure_ascii=False, indent=1)
    os.replace(temporal, destino)


# ----------------------------------------------------------------------------- tiempos
def duracion_salida(segmentos):
    return round(sum(s["fin"] - s["inicio"] for s in segmentos), 3)


def origen_a_salida(segmentos, t):
    """Tiempo del clip original -> tiempo de salida, o None si ``t`` cae en un tramo quitado."""
    acumulado = 0.0
    for s in segmentos:
        if s["inicio"] <= t <= s["fin"]:
            return round(acumulado + t - s["inicio"], 3)
        acumulado += s["fin"] - s["inicio"]
    return None


def salida_a_origen(segmentos, t):
    acumulado = 0.0
    for s in segmentos:
        largo = s["fin"] - s["inicio"]
        if t <= acumulado + largo + 1e-9:
            return round(s["inicio"] + max(0.0, t - acumulado), 3)
        acumulado += largo
    return segmentos[-1]["fin"] if segmentos else 0.0


def recortar_intervalo(segmentos, inicio, fin):
    """Parte de [inicio, fin] (tiempo original) que sigue en la salida, como lista de intervalos."""
    partes = []
    for s in segmentos:
        a, b = max(inicio, s["inicio"]), min(fin, s["fin"])
        if b - a > 1e-6:
            partes.append((a, b))
    return partes


# ----------------------------------------------------------------------------- subtítulos
def paginas_de_linea(linea, palabras_por_pagina):
    """Divide una línea en 'páginas' de N palabras (lo que se ve a la vez en pantalla)."""
    palabras = linea.get("palabras") or repartir_palabras(linea["texto"], linea["inicio"], linea["fin"])
    n = max(1, int(palabras_por_pagina))
    trozos = [palabras[i:i + n] for i in range(0, len(palabras), n)]
    paginas = []
    for indice, trozo in enumerate(trozos):
        inicio = trozo[0]["inicio"]
        fin = trozos[indice + 1][0]["inicio"] if indice + 1 < len(trozos) else linea["fin"]
        paginas.append({"inicio": inicio, "fin": max(fin, inicio + 0.05), "palabras": trozo})
    return paginas


def _ass_color(hex_color, alfa=0):
    r, g, b = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    return f"&H{alfa:02X}{b}{g}{r}&".upper()


def _ass_color6(hex_color):
    return f"&H{hex_color[5:7]}{hex_color[3:5]}{hex_color[1:3]}&".upper()


def _ass_tiempo(segundos):
    segundos = max(0.0, segundos)
    centesimas = int(round(segundos * 100))
    h, resto = divmod(centesimas, 360000)
    m, resto = divmod(resto, 6000)
    s, c = divmod(resto, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _texto_ass(texto):
    return texto.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def mapa_de_segmentos(segmentos):
    """[(desde, hasta, t_salida, velocidad)]: los tramos del clip y dónde caen en la salida (uno detrás de otro)."""
    mapa, acumulado = [], 0.0
    for s in segmentos:
        mapa.append((s["inicio"], s["fin"], acumulado, 1.0))
        acumulado += s["fin"] - s["inicio"]
    return mapa


def _partes_en_salida(mapa, inicio, fin):
    """Partes de [inicio, fin] (tiempo del clip) que siguen en la edición, ya en tiempo de SALIDA: [(a, b)]."""
    partes = []
    for a, b, t0, vel in mapa:
        x, y = max(inicio, a), min(fin, b)
        if y - x > 1e-6:
            partes.append((round(t0 + (x - a) / vel, 3), round(t0 + (y - a) / vel, 3)))
    return partes


def generar_ass(edicion, mapa=None, estilos_extra=(), eventos_extra=()):
    """Contenido de un archivo .ass con los subtítulos ya en el tiempo de SALIDA (huecos quitados).

    ``mapa`` (de ``mapa_de_segmentos`` o de las piezas) dice dónde cae cada instante del clip; ``estilos_extra`` y
    ``eventos_extra`` [(t, línea)] permiten añadir los textos de las piezas al mismo archivo."""
    mapa = mapa if mapa is not None else mapa_de_segmentos(edicion["segmentos"])
    salida = edicion["salida"]
    sub = edicion["subtitulos"]
    estilo = sub["estilo"]
    caja = estilo["fondo"] == "caja"
    y = int(round(salida["alto"] * estilo["posicion_y"]))
    x = salida["ancho"] // 2
    contorno = estilo["grosor_contorno"] if not caja else max(10, estilo["tamano"] // 6)
    color_borde = _ass_color(estilo["color_fondo"], 0x30) if caja else _ass_color(estilo["color_contorno"])
    cabecera = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {salida['ancho']}", f"PlayResY: {salida['alto']}",
        "WrapStyle: 1", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,"
        "Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Sub,{estilo['fuente']},{estilo['tamano']},{_ass_color(estilo['color'])},{_ass_color(estilo['color_resaltado'])},"
        f"{color_borde},&H00000000&,{-1 if estilo['negrita'] else 0},{-1 if estilo['cursiva'] else 0},0,0,100,100,0,0,"
        f"{3 if caja else 1},{contorno},0,5,40,40,40,1",
        *estilos_extra,
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    eventos = []
    mayus = estilo["mayusculas"]

    def color_de(palabra, linea):
        if palabra.get("color"):
            return palabra["color"]
        if linea.get("hablante"):
            return estilo["hablantes"][linea["hablante"] - 1]
        return estilo["color"]

    for linea in sub["lineas"]:
        for pagina in paginas_de_linea(linea, estilo["palabras_por_pagina"]):
            palabras = pagina["palabras"]
            instantes = []
            if estilo["resaltar_palabra"]:
                for k, palabra in enumerate(palabras):
                    fin = palabras[k + 1]["inicio"] if k + 1 < len(palabras) else pagina["fin"]
                    instantes.append((palabra["inicio"], fin, k))
            else:
                instantes.append((pagina["inicio"], pagina["fin"], -1))
            for inicio, fin, activa in instantes:
                partes = []
                for j, otra in enumerate(palabras):
                    t = _texto_ass(otra["texto"].upper() if mayus else otra["texto"])
                    color = estilo["color_resaltado"] if j == activa else color_de(otra, linea)
                    partes.append(f"{{\\c{_ass_color6(color)}}}{t}")
                eventos.append((inicio, fin, " ".join(partes)))
    lineas_ass = list(eventos_extra)
    for inicio, fin, texto in eventos:
        # Cada evento puede cruzar tramos quitados: se emite un evento por cada parte que sobrevive.
        for sa, sb in _partes_en_salida(mapa, inicio, fin):
            if sb - sa < 0.02:
                continue
            lineas_ass.append((sa, f"Dialogue: 0,{_ass_tiempo(sa)},{_ass_tiempo(sb)},Sub,,0,0,0,,{{\\an5\\pos({x},{y})}}{texto}"))
    lineas_ass.sort(key=lambda p: p[0])
    return "\n".join(cabecera + [l for _t, l in lineas_ass]) + "\n"


# ----------------------------------------------------------------------------- encuadre
def _par(n):
    n = int(round(n))
    return max(2, n - n % 2)


def rect_en_pixeles(rect, ancho, alto, aspecto):
    """(x, y, w, h) en píxeles de un recorte normalizado, forzando la proporción ``aspecto`` (ancho/alto).

    Se conserva el centro y se achica la dimensión que sobre, así que nunca se deforma la imagen.
    Todo sale par y dentro del video."""
    cx = (rect["x"] + rect["w"] / 2.0) * ancho
    cy = (rect["y"] + rect["h"] / 2.0) * alto
    w, h = rect["w"] * ancho, rect["h"] * alto
    if w / h > aspecto:
        w = h * aspecto
    else:
        h = w / aspecto
    escala = min(1.0, ancho / w, alto / h)       # si no cabe, se achica conservando la proporción
    w, h = _par(w * escala), _par(h * escala)
    if w > ancho:
        w = ancho - ancho % 2
    if h > alto:
        h = alto - alto % 2
    x = min(max(0, cx - w / 2.0), ancho - w)
    y = min(max(0, cy - h / 2.0), alto - h)
    return int(x) - int(x) % 2, int(y) - int(y) % 2, w, h


def franjas(enc, alto_salida):
    """Franjas verticales de la pantalla dividida, de arriba abajo: [{"clave", "y0", "alto"}].

    ``clave`` identifica el recuadro de origen: «arriba» (juego) / «abajo» (cara) en el modo dividido, y
    «tres.a» / «tres.b» / «tres.c» en el de tres pantallas. Con ``invertido`` el dividido pone la cara arriba."""
    if enc["modo"] == "tres":
        p1, p2 = enc["alturas_tres"]
        h1, h2 = _par(alto_salida * p1), _par(alto_salida * p2)
        alturas = [h1, h2, alto_salida - h1 - h2]
        claves = ["tres." + k for k in enc["orden_tres"]]
    else:
        arriba, abajo = alturas_dividido(alto_salida, enc["proporcion_arriba"])
        alturas = [arriba, abajo]
        claves = ["abajo", "arriba"] if enc.get("invertido") else ["arriba", "abajo"]
    resultado, y = [], 0
    for clave, alto in zip(claves, alturas):
        resultado.append({"clave": clave, "y0": y, "alto": alto})
        y += alto
    return resultado


def rect_de(enc, clave):
    return enc["tres"][clave[5:]] if clave.startswith("tres.") else enc[clave]


def geometria_capa(capa, ancho, alto, ow, oh):
    """Medidas en píxeles de una capa: (crop (x,y,w,h), destino (x,y,w,h)). Todo par y dentro de sus límites.

    «llenar» recorta la fuente a la proporción del destino (sin deformar); «contener» la deja entera y la encoge."""
    d = capa["destino"]
    dw, dh = _par(d["w"] * ow), _par(d["h"] * oh)
    dx, dy = int(round(d["x"] * ow)), int(round(d["y"] * oh))
    dw, dh = min(dw, ow), min(dh, oh)
    dx, dy = min(max(0, dx), ow - dw), min(max(0, dy), oh - dh)
    b = capa["borde"]["ancho"]
    iw_, ih_ = max(2, _par(dw - 2 * b)), max(2, _par(dh - 2 * b))
    if capa["ajuste"] == "llenar":
        recorte = rect_en_pixeles(capa["fuente"], ancho, alto, iw_ / ih_)
    else:
        f = capa["fuente"]
        w, h = _par(f["w"] * ancho), _par(f["h"] * alto)
        w, h = min(w, ancho - ancho % 2), min(h, alto - alto % 2)
        x = min(max(0, int(f["x"] * ancho)), ancho - w)
        y = min(max(0, int(f["y"] * alto)), alto - h)
        recorte = (x - x % 2, y - y % 2, w, h)
    return recorte, (dx, dy, dw, dh), (iw_, ih_)


def alturas_dividido(alto_salida, proporcion_arriba):
    arriba = _par(alto_salida * proporcion_arriba)
    return arriba, alto_salida - arriba
