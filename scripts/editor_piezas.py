# -*- coding: utf-8 -*-
"""Piezas del editor: la línea de tiempo al estilo de la pestaña «Edit» de DaVinci Resolve.

Antes el clip era UNA cinta (``segmentos``) y solo los extras flotaban libremente. Ahora todo es una *pieza*
colocada en una pista: trozos de video del clip, trozos de su audio, medios añadidos (video, imagen, audio)
y textos. Cada pieza guarda de dónde viene (``desde``), dónde está en la salida (``t``), cuánto dura (``dur``)
y en qué pista va (``carril``: V1…V8 para imagen, V2… para texto, A1…A8 para audio). Las piezas enlazadas
(``enlace``) se mueven juntas, como el video y su audio en DaVinci.

Este módulo solo contiene datos y matemática (sin FFmpeg): normaliza, migra ediciones antiguas y calcula
tiempos. El render está en ``editor_render_piezas.py``.
"""
from __future__ import annotations
SELLO = "2026-10-23-c"        # lo muestra el editor para comprobar que todos los archivos están actualizados

import os
import re

try:
    from . import editor_modelo as modelo
except ImportError:  # módulo suelto desde scripts/
    import editor_modelo as modelo

VERSION_PIEZAS = 2
MAX_PIEZAS = 300
MAX_CARRILES = 8
MAX_DURACION = 1800.0
DUR_MINIMA = 0.05
TIPOS = ("video", "audio", "imagen", "texto")
TRANSICIONES = ("ninguna", "disolver", "deslizar_izq", "deslizar_der", "deslizar_arriba", "deslizar_abajo")
ANIM_ENTRADA = ("ninguna", "fundido", "subir", "bajar", "izquierda", "derecha", "pop", "maquina")
ANIM_SALIDA = ("ninguna", "fundido", "pop")
ALINEACIONES = ("izquierda", "centro", "derecha")
# parámetros que se pueden animar con keyframes: (mínimo, máximo, valor por defecto)
PARAMS_KF = {"zoom": (1.0, 4.0, 1.0), "pos_x": (-1.0, 1.0, 0.0), "pos_y": (-1.0, 1.0, 0.0),
             "opacidad": (0.0, 1.0, 1.0), "volumen": (0.0, 2.0, 1.0), "rotacion": (-180.0, 180.0, 0.0),
             "rec_x": (0.0, 1.0, 0.0), "rec_y": (0.0, 1.0, 0.0), "rec_w": (0.01, 1.0, 1.0), "rec_h": (0.01, 1.0, 1.0)}
MAX_KF = 24

TEXTO_DEFECTO = {
    "contenido": "Texto", "fuente": "Arial", "tamano": 90, "color": "#FFFFFF", "color_contorno": "#000000", "grosor_contorno": 6,
    "sombra": 0, "color_sombra": "#000000", "negrita": True, "cursiva": False, "mayusculas": False, "alineacion": "centro",
    "x": 0.5, "y": 0.5, "fondo": "ninguno", "color_fondo": "#000000", "espaciado": 0, "icono_espacios": 0,
    "anim_in": "ninguna", "anim_out": "ninguna", "anim_dur": 0.4,
}


# ----------------------------------------------------------------------------- utilidades de pistas
def familia(carril):
    return "A" if str(carril).startswith("A") else "V"


def numero(carril):
    return int(str(carril)[1:])


def carril_valido(valor, tipo):
    """Carril coherente con el tipo de pieza (audio -> A, el resto -> V)."""
    quiere = "A" if tipo == "audio" else "V"
    m = re.fullmatch(r"([VA])([1-9])", str(valor or ""))
    if m and m.group(1) == quiere and 1 <= int(m.group(2)) <= MAX_CARRILES:
        return str(valor)
    return quiere + "1"


def fin_de(p):
    return round(p["t"] + p["dur"], 6)


def consumo(p):
    """Segundos de la fuente que gasta la pieza (la duración de salida × la velocidad)."""
    return p["dur"] * p.get("velocidad", 1.0)


def duracion_total(piezas):
    return round(max([fin_de(p) for p in piezas] or [0.0]), 3)


def es_clip(p):
    return p.get("fuente") == "clip"


def tiene_audio_propio(p):
    """Los medios de video llevan su audio en una pieza de audio enlazada (no en la pieza de video)."""
    return p["tipo"] == "audio"


# ----------------------------------------------------------------------------- keyframes
def _kf_limpio(valor, dur):
    resultado = {}
    if not isinstance(valor, dict):
        return resultado
    for param, (lo, hi, _d) in PARAMS_KF.items():
        crudo = valor.get(param)
        if not isinstance(crudo, list):
            continue
        puntos = {}
        for q in crudo[:MAX_KF * 2]:
            if not isinstance(q, dict):
                continue
            t = modelo._num(q.get("t"), None, 0.0, dur)
            v = modelo._num(q.get("v"), None, lo, hi)
            if t is None or v is None:
                continue
            ease = q.get("ease") if q.get("ease") in ("lineal", "entrada", "salida", "ambos") else "lineal"
            puntos[round(t, 3)] = (round(v, 4), ease)
        if puntos:
            resultado[param] = [{"t": t, "v": puntos[t][0], **({"ease": puntos[t][1]} if puntos[t][1] != "lineal" else {})} for t in sorted(puntos)][:MAX_KF]
    return resultado


def valor_kf(pieza, param, t_local):
    """Valor de ``param`` en el instante ``t_local`` (segundos desde el inicio de la pieza), con keyframes si los hay."""
    base = pieza.get(param, PARAMS_KF[param][2]) if param in PARAMS_KF else 0.0
    puntos = (pieza.get("kf") or {}).get(param)
    if not puntos:
        return base
    if t_local <= puntos[0]["t"]:
        return puntos[0]["v"]
    for a, b in zip(puntos, puntos[1:]):
        if t_local < b["t"]:
            f = (t_local - a["t"]) / max(1e-9, b["t"] - a["t"])
            f = _ease_f(f, b.get("ease", "lineal"))
            return a["v"] + (b["v"] - a["v"]) * f
    return puntos[-1]["v"]


def expr_kf(puntos, var="t"):
    """Expresión de FFmpeg (lineal por tramos) para una lista de keyframes {t, v}."""
    def n(x):
        t = f"{x:.4f}".rstrip("0").rstrip(".") or "0"
        return f"({t})" if t.startswith("-") else t
    if len(puntos) == 1:
        return n(puntos[0]["v"])
    e = n(puntos[-1]["v"])
    for a, b in reversed(list(zip(puntos, puntos[1:]))):
        u = f"(({var}-{n(a['t'])})/{n(max(1e-6, b['t'] - a['t']))})"
        u = _ease_expr(u, b.get("ease", "lineal"))
        tramo = f"{n(a['v'])}+({n(b['v'])}-{n(a['v'])})*{u}"
        e = f"if(lt({var},{n(b['t'])}),{tramo},{e})"
    return f"if(lt({var},{n(puntos[0]['t'])}),{n(puntos[0]['v'])},{e})"


def _ease_f(f, tipo):
    f = max(0.0, min(1.0, f))
    if tipo == "entrada": return f * f
    if tipo == "salida": return 1 - (1 - f) * (1 - f)
    if tipo == "ambos": return f * f * (3 - 2 * f)
    return f


def _ease_expr(f, tipo):
    if tipo == "entrada": return f"(({f})*({f}))"
    if tipo == "salida": return f"(1-(1-({f}))*(1-({f})))"
    if tipo == "ambos": return f"(({f})*({f})*(3-2*({f})))"
    return f


# ----------------------------------------------------------------------------- normalización
def normalizar_texto(valor):
    d = TEXTO_DEFECTO
    t = valor if isinstance(valor, dict) else {}
    contenido = str(t.get("contenido", d["contenido"]))[:400]
    contenido = "\n".join(contenido.replace("\r", "").split("\n")[:8])
    if not contenido.strip():
        contenido = d["contenido"]
    return {
        "contenido": contenido,
        "fuente": str(t.get("fuente") or d["fuente"])[:80],
        "tamano": int(modelo._num(t.get("tamano"), d["tamano"], 16, 400)),
        "color": modelo._color(t.get("color"), d["color"]),
        "color_contorno": modelo._color(t.get("color_contorno"), d["color_contorno"]),
        "grosor_contorno": int(modelo._num(t.get("grosor_contorno"), d["grosor_contorno"], 0, 30)),
        "sombra": int(modelo._num(t.get("sombra"), d["sombra"], 0, 30)),
        "color_sombra": modelo._color(t.get("color_sombra"), d["color_sombra"]),
        "negrita": bool(t.get("negrita", d["negrita"])),
        "cursiva": bool(t.get("cursiva", d["cursiva"])),
        "mayusculas": bool(t.get("mayusculas", d["mayusculas"])),
        "alineacion": t.get("alineacion") if t.get("alineacion") in ALINEACIONES else d["alineacion"],
        "x": round(modelo._num(t.get("x"), d["x"], 0.0, 1.0), 4),
        "y": round(modelo._num(t.get("y"), d["y"], 0.0, 1.0), 4),
        "fondo": "caja" if t.get("fondo") == "caja" else "ninguno",
        "color_fondo": modelo._color(t.get("color_fondo"), d["color_fondo"]),
        "espaciado": round(modelo._num(t.get("espaciado"), d["espaciado"], -10, 60), 1),
        "icono_espacios": int(modelo._num(t.get("icono_espacios"), 0, 0, 40)),
        "anim_in": t.get("anim_in") if t.get("anim_in") in ANIM_ENTRADA else "ninguna",
        "anim_out": t.get("anim_out") if t.get("anim_out") in ANIM_SALIDA else "ninguna",
        "anim_dur": round(modelo._num(t.get("anim_dur"), d["anim_dur"], 0.1, 5.0), 2),
    }


def _slug(valor, defecto, maximo=40):
    return re.sub(r"[^a-zA-Z0-9_-]", "", str(valor or ""))[:maximo] or defecto


def normalizar_pieza(e, n, origen, encuadre_base):
    """Una pieza validada, o None si no sirve."""
    if not isinstance(e, dict):
        return None
    tipo = e.get("tipo")
    if tipo not in TIPOS:
        return None
    es_texto = tipo == "texto"
    es_del_clip = (e.get("fuente") == "clip") and tipo in ("video", "audio")
    archivo = "" if (es_texto or es_del_clip) else str(e.get("archivo") or "").strip()[:1024]
    if not es_texto and not es_del_clip and not archivo:
        return None
    if es_del_clip and tipo == "audio" and int(origen.get("pistas_audio", 0)) < 1:
        return None
    fuente = "texto" if es_texto else ("clip" if es_del_clip else "medio")
    vel = 1.0 if tipo in ("imagen", "texto") else modelo._num(e.get("velocidad"), 1.0, 0.1, 10.0)
    dur_medio = float(origen["duracion"]) if es_del_clip else (0.0 if es_texto or tipo == "imagen" else modelo._num(e.get("dur_medio"), 0.0, 0.0, 86400.0))
    desde = 0.0 if (es_texto or tipo == "imagen") else modelo._num(e.get("desde"), 0.0, 0.0, 86400.0)
    dur = modelo._num(e.get("dur"), 1.0, DUR_MINIMA, MAX_DURACION)
    if dur_medio > 0.2:
        desde = min(desde, max(0.0, dur_medio - 0.1))
        dur = max(DUR_MINIMA, min(dur, (dur_medio - desde) / vel))
    fi = modelo._num(e.get("fundido_in"), 0.0, 0.0, 10.0)
    fo = modelo._num(e.get("fundido_out"), 0.0, 0.0, 10.0)
    if fi + fo > dur:
        fi, fo = dur / 2.0, dur / 2.0
    rc = e.get("recuadro") if isinstance(e.get("recuadro"), dict) else {}
    w = modelo._num(rc.get("w"), 0.4, 0.1, 1.0)
    tr = e.get("trans_in") if isinstance(e.get("trans_in"), dict) else {}
    tr_tipo = tr.get("tipo") if tr.get("tipo") in TRANSICIONES else "ninguna"
    tr_dur = round(modelo._num(tr.get("dur"), 0.5, 0.1, min(5.0, dur)), 2)
    pieza = {
        "id": _slug(e.get("id"), f"p{n}"), "tipo": tipo, "fuente": fuente, "archivo": archivo,
        "carril": carril_valido(e.get("carril"), tipo),
        "t": round(modelo._num(e.get("t"), 0.0, 0.0, MAX_DURACION), 3), "desde": round(desde, 3), "dur": round(dur, 3),
        "velocidad": round(vel, 4), "volumen": round(modelo._num(e.get("volumen"), 1.0, 0.0, 2.0), 3),
        "fundido_in": round(fi, 3), "fundido_out": round(fo, 3),
        "opacidad": round(modelo._num(e.get("opacidad"), 1.0, 0.0, 1.0), 3),
        "zoom": round(modelo._num(e.get("zoom"), 1.0, 1.0, 4.0), 3),
        "pos_x": round(modelo._num(e.get("pos_x"), 0.0, -1.0, 1.0), 3), "pos_y": round(modelo._num(e.get("pos_y"), 0.0, -1.0, 1.0), 3),
        "tras_x": round(modelo._num(e.get("tras_x"), 0.0, -1.0, 1.0), 4), "tras_y": round(modelo._num(e.get("tras_y"), 0.0, -1.0, 1.0), 4),
        "rotacion": round(modelo._num(e.get("rotacion"), 0.0, -180.0, 180.0), 2),
        "flip_h": bool(e.get("flip_h", False)), "flip_v": bool(e.get("flip_v", False)),
        "recorte_bordes": _recorte_bordes(e.get("recorte_bordes")),
        "enlace": _slug(e.get("enlace"), "", 24),
        "modo": "recuadro" if e.get("modo") == "recuadro" else "cubrir",
        "recuadro": {"x": modelo._num(rc.get("x"), 0.55, 0.0, 1.0 - w), "y": modelo._num(rc.get("y"), 0.05, 0.0, 1.0), "w": w},
        "dur_medio": round(dur_medio, 3), "ancho": int(modelo._num(e.get("ancho"), 0, 0, 20000)), "alto": int(modelo._num(e.get("alto"), 0, 0, 20000)),
        "tiene_audio": bool(e.get("tiene_audio", tipo == "audio")),
        "nombre": (str(e.get("nombre") or (os.path.basename(archivo) if archivo else ("Texto" if es_texto else "Clip"))))[:120],
        "mid": re.sub(r"[^a-f0-9]", "", str(e.get("mid") or ""))[:40],
        "trans_in": {"tipo": tr_tipo, "dur": tr_dur},
        "kf": _kf_limpio(e.get("kf"), dur),
    }
    if tipo == "video" and isinstance(e.get("encuadre"), dict) and (es_del_clip or (fuente == "medio" and pieza["ancho"] > 0 and pieza["alto"] > 0)):
        pieza["encuadre"] = modelo.normalizar_encuadre(e["encuadre"], encuadre_base)      # plantilla propia (también en vídeos añadidos)
    if es_texto:
        pieza["texto"] = normalizar_texto(e.get("texto"))
    return pieza


def _recorte_bordes(valor):
    d = valor if isinstance(valor, dict) else {}
    izquierda = modelo._num(d.get("izquierda"), 0.0, 0.0, 0.45)
    derecha = min(modelo._num(d.get("derecha"), 0.0, 0.0, 0.45), 0.9 - izquierda)
    arriba = modelo._num(d.get("arriba"), 0.0, 0.0, 0.45)
    abajo = min(modelo._num(d.get("abajo"), 0.0, 0.0, 0.45), 0.9 - arriba)
    return {"izquierda": round(izquierda, 4), "derecha": round(max(0, derecha), 4), "arriba": round(arriba, 4), "abajo": round(max(0, abajo), 4)}


def _resolver_solapes(piezas):
    """Dos piezas de la misma pista no pueden pisarse: la que empieza antes se acorta para terminar donde empieza la siguiente."""
    por_carril = {}
    for p in piezas:
        por_carril.setdefault(p["carril"], []).append(p)
    descartadas = set()
    for lista in por_carril.values():
        lista.sort(key=lambda p: (p["t"], p["id"]))
        anterior = None
        for p in lista:
            while anterior is not None and anterior["t"] + anterior["dur"] > p["t"] + 1e-3:
                nueva = round(p["t"] - anterior["t"], 3)
                if nueva < DUR_MINIMA:
                    descartadas.add(anterior["id"])
                    idx = lista.index(anterior)
                    anterior = None
                    for q in reversed(lista[:idx]):
                        if q["id"] not in descartadas:
                            anterior = q
                            break
                    continue
                anterior["dur"] = nueva
                anterior["fundido_out"] = min(anterior["fundido_out"], nueva)
                anterior["fundido_in"] = min(anterior["fundido_in"], max(0.0, nueva - anterior["fundido_out"]))
                break
            anterior = p
    return [p for p in piezas if p["id"] not in descartadas]


def normalizar_piezas(crudas, origen, encuadre_base):
    resultado, vistos = [], set()
    for n, e in enumerate(crudas if isinstance(crudas, list) else []):
        if len(resultado) >= MAX_PIEZAS:
            break
        p = normalizar_pieza(e, n, origen, encuadre_base)
        if p is None:
            continue
        while p["id"] in vistos:
            p["id"] += "_"
        vistos.add(p["id"])
        resultado.append(p)
    resultado = _resolver_solapes(resultado)
    for p in resultado:                                   # los keyframes no pueden pasarse de la duración ya recortada
        p["kf"] = _kf_limpio(p.get("kf"), p["dur"])
    cuenta = {}
    for p in resultado:
        if p["enlace"]:
            cuenta[p["enlace"]] = cuenta.get(p["enlace"], 0) + 1
    for p in resultado:
        if p["enlace"] and cuenta[p["enlace"]] < 2:
            p["enlace"] = ""
    resultado.sort(key=lambda p: (numero(p["carril"]), familia(p["carril"]), p["t"]))
    return resultado


def normalizar_pistas(pistas, piezas):
    """Pistas (semántica nueva): ``video`` y ``audio`` son el NÚMERO TOTAL de pistas, V1/A1 incluidas."""
    p = pistas if isinstance(pistas, dict) else {}
    nv = int(modelo._num(p.get("video"), 1, 1, MAX_CARRILES))
    na = int(modelo._num(p.get("audio"), 1, 1, MAX_CARRILES))
    for e in piezas:
        if familia(e["carril"]) == "A":
            na = max(na, numero(e["carril"]))
        else:
            nv = max(nv, numero(e["carril"]))

    def valido(lista):
        return sorted({str(x) for x in (lista if isinstance(lista, list) else []) if re.fullmatch(r"[VA][1-8]", str(x))})
    return {"video": nv, "audio": na, "ocultas": valido(p.get("ocultas")), "silenciadas": valido(p.get("silenciadas")),
            "bloqueadas": valido(p.get("bloqueadas")), "bloqueo": bool(p.get("bloqueo", False))}


# ----------------------------------------------------------------------------- creación y migración
def piezas_iniciales(duracion, pistas_audio):
    """El clip entero: una pieza de video en V1 y, si tiene sonido, su audio enlazado en A1."""
    d = round(float(duracion), 3)
    piezas = [{"id": "v1", "tipo": "video", "fuente": "clip", "carril": "V1", "t": 0.0, "desde": 0.0, "dur": d, "enlace": "e1" if pistas_audio else ""}]
    if pistas_audio:
        piezas.append({"id": "a1", "tipo": "audio", "fuente": "clip", "carril": "A1", "t": 0.0, "desde": 0.0, "dur": d, "enlace": "e1"})
    return piezas


def _libre(lista, t, fin):
    return not any(t < b - 1e-3 and a < fin - 1e-3 for a, b in lista)


def migrar_legacy(segmentos, extras, origen):
    """Convierte una edición antigua (``segmentos`` + ``extras``) en piezas equivalentes.

    Cada tramo pasa a ser un trozo de video en V1 con su audio enlazado en A1, uno detrás de otro (como antes).
    Cada extra conserva su pista (V{n+1} / A{n+1}); el sonido de un video extra pasa a ser una pieza de audio enlazada."""
    piezas, t = [], 0.0
    hay_audio = int(origen.get("pistas_audio", 0)) > 0
    for i, s in enumerate(segmentos):
        dur = round(s["fin"] - s["inicio"], 3)
        enlace = f"e{i + 1}" if hay_audio else ""
        piezas.append({"id": f"v{i + 1}", "tipo": "video", "fuente": "clip", "carril": "V1", "t": round(t, 3), "desde": s["inicio"], "dur": dur, "enlace": enlace})
        if hay_audio:
            piezas.append({"id": f"a{i + 1}", "tipo": "audio", "fuente": "clip", "carril": "A1", "t": round(t, 3), "desde": s["inicio"], "dur": dur, "enlace": enlace})
        t += dur
    ocupado_a = {}
    for p in piezas:
        if p["tipo"] == "audio":
            ocupado_a.setdefault(p["carril"], []).append((p["t"], p["t"] + p["dur"]))
    comunes = ("desde", "dur", "t", "velocidad", "fundido_in", "fundido_out", "dur_medio", "ancho", "alto", "tiene_audio", "nombre", "mid", "archivo")
    for e in extras:
        base = {k: e[k] for k in comunes if k in e}
        base["fuente"] = "medio"
        if e["tipo"] == "audio":
            carril = f"A{e['pista'] + 1}"
            ocupado_a.setdefault(carril, []).append((e["t"], e["t"] + e["dur"]))
            piezas.append({**base, "id": e["id"], "tipo": "audio", "carril": carril, "volumen": e["volumen"]})
    for e in extras:
        if e["tipo"] == "audio":
            continue
        base = {k: e[k] for k in comunes if k in e}
        base["fuente"] = "medio"
        pieza = {**base, "id": e["id"], "tipo": e["tipo"], "carril": f"V{e['pista'] + 1}", "modo": e.get("modo", "cubrir"), "recuadro": e.get("recuadro")}
        if e["tipo"] == "video" and e.get("audio") and e.get("tiene_audio"):
            candidatos = [f"A{e['pista'] + 1}"] + [f"A{k}" for k in range(2, MAX_CARRILES + 1)]
            for c in candidatos:
                if _libre(ocupado_a.get(c, []), e["t"], e["t"] + e["dur"]):
                    ocupado_a.setdefault(c, []).append((e["t"], e["t"] + e["dur"]))
                    pieza["enlace"] = "l_" + _slug(e["id"], "x", 16)
                    piezas.append({**base, "id": e["id"] + "_a", "tipo": "audio", "carril": c, "volumen": e["volumen"], "enlace": pieza["enlace"]})
                    break
        piezas.append(pieza)
    return piezas


def pistas_de_legacy(pistas):
    """Las pistas antiguas contaban solo las EXTRA (sin V1/A1): ahora se cuenta el total."""
    p = dict(pistas) if isinstance(pistas, dict) else {}
    p["video"] = int(modelo._num(p.get("video"), 1, 1, MAX_CARRILES)) + 1
    p["audio"] = int(modelo._num(p.get("audio"), 1, 1, MAX_CARRILES)) + 1
    return p


# ----------------------------------------------------------------------------- tiempos y mapeos
def piezas_de(edicion):
    return edicion.get("piezas") or []


def tiene_piezas(edicion):
    return isinstance(edicion.get("piezas"), list)


def total_de(edicion):
    """Duración de la salida: lo que dura la edición (legacy: la suma de tramos)."""
    if tiene_piezas(edicion):
        return duracion_total(edicion["piezas"])
    return modelo.duracion_salida(edicion["segmentos"])


def mapa_clip(piezas):
    """[(desde, hasta, t_salida, velocidad)] de lo que se ve/oye del clip, para colocar los subtítulos.

    Los subtítulos siguen a la VOZ: se usan las piezas de audio del clip; si no hay ninguna, las de video."""
    elegidas = [p for p in piezas if es_clip(p) and p["tipo"] == "audio"] or [p for p in piezas if es_clip(p) and p["tipo"] == "video"]
    elegidas.sort(key=lambda p: p["t"])
    return [(p["desde"], round(p["desde"] + consumo(p), 6), p["t"], p["velocidad"]) for p in elegidas]


def salida_de_origen(mapa, t):
    """Tiempo de salida de un instante del clip original, o None si esa parte ya no está en la edición."""
    for a, b, t0, vel in mapa:
        if a <= t <= b:
            return round(t0 + (t - a) / vel, 3)
    return None


def origen_de_salida(mapa, t):
    for a, b, t0, vel in mapa:
        if t0 <= t <= t0 + (b - a) / vel + 1e-9:
            return round(a + (t - t0) * vel, 3)
    return None


def segmentos_derivados(piezas, duracion):
    """Lista ``segmentos`` equivalente (la leen las versiones antiguas del panel): trozos de video del clip por orden de salida."""
    trozos = sorted((p for p in piezas if es_clip(p) and p["tipo"] == "video"), key=lambda p: p["t"])
    segs = []
    for p in trozos:
        a, b = p["desde"], min(duracion, p["desde"] + consumo(p))
        if segs and abs(segs[-1]["fin"] - a) < 1e-3:
            segs[-1]["fin"] = round(b, 3)
        else:
            segs.append({"inicio": round(a, 3), "fin": round(b, 3)})
    return segs or [{"inicio": 0.0, "fin": round(float(duracion), 3)}]


def piezas_para_ia(piezas):
    """Trozos de video del clip que usan el encuadre general (sin plantilla propia) y velocidad normal, por orden de salida.

    La mejora con IA se calcula sobre ellos, uno detrás de otro; ``offset`` es dónde empieza cada uno en ese video."""
    elegidas = sorted((p for p in piezas if es_clip(p) and p["tipo"] == "video" and "encuadre" not in p and abs(p["velocidad"] - 1.0) < 1e-4), key=lambda p: p["t"])
    resultado, acumulado = [], 0.0
    for p in elegidas:
        resultado.append({"pieza": p, "offset": round(acumulado, 3), "inicio": p["desde"], "fin": round(p["desde"] + p["dur"], 3)})
        acumulado += p["dur"]
    return resultado


# ----------------------------------------------------------------------------- texto (ASS)
def _ass_color(hex_color, alfa=0):
    return modelo._ass_color(hex_color, alfa)


def estilo_y_eventos_texto(pieza, indice, salida):
    """(línea «Style:», [(t_inicio, línea «Dialogue:»)]) de una pieza de texto en el tiempo de SALIDA."""
    tx = pieza["texto"]
    ow, oh = salida["ancho"], salida["alto"]
    caja = tx["fondo"] == "caja"
    nombre = f"T{indice}"
    contorno = tx["grosor_contorno"] if not caja else max(10, tx["tamano"] // 6)
    color_borde = _ass_color(tx["color_fondo"], 0x30) if caja else _ass_color(tx["color_contorno"])
    estilo = (f"Style: {nombre},{tx['fuente']},{tx['tamano']},{_ass_color(tx['color'])},{_ass_color(tx['color'])},{color_borde},"
              f"{_ass_color(tx['color_sombra'], 0x40)},{-1 if tx['negrita'] else 0},{-1 if tx['cursiva'] else 0},0,0,100,100,{tx['espaciado']:g},0,"
              f"{3 if caja else 1},{contorno},{tx['sombra']},5,40,40,40,1")
    an = {"izquierda": 4, "centro": 5, "derecha": 6}[tx["alineacion"]]
    x, y = int(round(tx["x"] * ow)), int(round(tx["y"] * oh))
    t0, t1 = pieza["t"], pieza["t"] + pieza["dur"]
    d = tx["anim_dur"]
    ms = lambda s: int(round(s * 1000))
    fi = pieza["fundido_in"]
    fo = pieza["fundido_out"]
    if tx["anim_in"] == "fundido":
        fi = max(fi, d)
    if tx["anim_out"] == "fundido":
        fo = max(fo, d)
    etiquetas = f"\\an{an}"
    desplaza = {"subir": (0, int(oh * 0.08)), "bajar": (0, -int(oh * 0.08)), "izquierda": (int(ow * 0.15), 0), "derecha": (-int(ow * 0.15), 0)}.get(tx["anim_in"])
    if desplaza:
        etiquetas += f"\\move({x + desplaza[0]},{y + desplaza[1]},{x},{y},0,{ms(min(d, pieza['dur']))})"
    else:
        etiquetas += f"\\pos({x},{y})"
    if fi > 0 or fo > 0:
        etiquetas += f"\\fad({ms(fi)},{ms(fo)})"
    if pieza["opacidad"] < 0.999:
        etiquetas += f"\\alpha&H{int(round((1 - pieza['opacidad']) * 255)):02X}&"
    if tx["anim_in"] == "pop":
        d1 = ms(min(d, pieza["dur"]))
        etiquetas += f"\\fscx0\\fscy0\\t(0,{int(d1 * 0.7)},\\fscx112\\fscy112)\\t({int(d1 * 0.7)},{d1},\\fscx100\\fscy100)"
    if tx["anim_out"] == "pop":
        fin_ms = ms(pieza["dur"])
        etiquetas += f"\\t({max(0, fin_ms - ms(d))},{fin_ms},\\fscx0\\fscy0)"
    contenido = tx["contenido"].upper() if tx["mayusculas"] else tx["contenido"]
    contenido = contenido.replace("\\", "/").replace("{", "(").replace("}", ")")
    pre = "\\h" * tx.get("icono_espacios", 0)      # hueco a la izquierda para un logo (espacios duros)
    if tx["anim_in"] == "maquina":
        letras = [c for c in contenido]
        visibles = [i for i, c in enumerate(letras) if c != "\n"]
        paso = max(0.03, min(0.12, (d * 2) / max(1, len(visibles))))
        eventos = []
        for k in range(1, len(visibles) + 1):
            corte = visibles[k - 1] + 1
            a = t0 + (k - 1) * paso
            b = t1 if k == len(visibles) else min(t1, t0 + k * paso)
            if a >= t1:
                break
            parte = contenido[:corte].replace("\n", "\\N")
            resto = contenido[corte:].replace("\n", "\\N")
            texto = pre + parte + ("{\\alpha&HFF&}" + resto if resto else "")
            tags = f"\\an{an}\\pos({x},{y})" + (f"\\fad(0,{ms(fo)})" if fo > 0 and k == len(visibles) else "")
            eventos.append((a, f"Dialogue: 1,{modelo._ass_tiempo(a)},{modelo._ass_tiempo(b)},{nombre},,0,0,0,,{{{tags}}}{texto}"))
        return estilo, eventos
    texto = contenido.replace("\n", "\\N")
    return estilo, [(t0, f"Dialogue: 1,{modelo._ass_tiempo(t0)},{modelo._ass_tiempo(t1)},{nombre},,0,0,0,,{{{etiquetas}}}{pre}{texto}")]


def textos_activos(edicion):
    return sorted((p for p in piezas_de(edicion) if p["tipo"] == "texto" and f"V{numero(p['carril'])}" not in (edicion.get("pistas") or {}).get("ocultas", [])),
                  key=lambda p: (p["t"], numero(p["carril"])))


def generar_ass(edicion):
    """Archivo .ass con los subtítulos (siguiendo a la voz del clip) y los textos de las piezas, en el tiempo de SALIDA."""
    estilos, eventos = [], []
    for i, p in enumerate(textos_activos(edicion)):
        e, ev = estilo_y_eventos_texto(p, i, edicion["salida"])
        estilos.append(e)
        eventos.extend(ev)
    return modelo.generar_ass(edicion, mapa=mapa_clip(edicion["piezas"]), estilos_extra=estilos, eventos_extra=eventos)


def familias_de_texto(edicion):
    return sorted({p["texto"]["fuente"] for p in textos_activos(edicion)})
